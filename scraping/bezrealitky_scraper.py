import requests
import csv
import re
import time
import os
from queue import Queue
from threading import Thread, Lock

OUTPUT_FILE = "data/raw/bezrealitky.csv"
DELAY       = 1.5
LIMIT       = 100
MAX_PAGES   = 40
NUM_WORKERS = 8

GRAPHQL_URL = "https://api.bezrealitky.cz/graphql/"
DETAIL_BASE = "https://www.bezrealitky.cz/nemovitosti-byty-domy/{}"

HEADERS_API = {
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Origin":       "https://www.bezrealitky.cz",
    "Referer":      "https://www.bezrealitky.cz/",
}
HEADERS_WEB = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "cs",
    "Referer":         "https://www.bezrealitky.cz/",
}

QUERY = """
query AdvertList(
  $locale: Locale!, $estateType: [EstateType], $offerType: [OfferType],
  $regionOsmIds: [ID], $limit: Int = 15, $offset: Int = 0,
  $order: ResultOrder = TIMEORDER_DESC, $currency: Currency
) {
  listAdverts(
    offerType: $offerType estateType: $estateType limit: $limit
    regionOsmIds: $regionOsmIds offset: $offset order: $order currency: $currency
  ) {
    list { id uri disposition address(locale: $locale) surface price gps { lat lng } tags(locale: $locale) ownership }
    totalCount
  }
}
"""

DISPOSITION_MAP = {
    "DISP_1_KK": "1+kk", "DISP_1_1": "1+1", "DISP_2_KK": "2+kk", "DISP_2_1": "2+1",
    "DISP_3_KK": "3+kk", "DISP_3_1": "3+1", "DISP_4_KK": "4+kk", "DISP_4_1": "4+1",
    "DISP_5_KK": "5+kk", "DISP_5_1": "5+1", "DISP_6_AND_MORE": "6+", "DISP_ATYPICAL": "atypicky",
}
OWNERSHIP_MAP = {
    "OSOBNI": "osobni", "DRUZSTEVNI": "druzstevni", "STATNI": "statni", "UNDEFINED": None,
}
CONDITION_MAP = {
    "NEW": "novostavba", "GOOD": "dobry", "VERY_GOOD": "velmi dobry",
    "AFTER_RECONSTRUCTION": "po rekonstrukci", "BEFORE_RECONSTRUCTION": "pred rekonstrukci",
    "UNDER_CONSTRUCTION": "ve vystavbe", "BAD": "spatny",
}

CZ_BBOX = (48.55, 51.06, 12.09, 18.87)


def parse_furnished(text):
    """
    gets furnished status from raw text
    :param text: raw string from listing tags or html page
    :return: 'vybaveny', 'castecne vybaveny', 'nevybaveny', or None if not detected
    """
    text = text.lower()
    if "plně vybaven" in text or "vybavený" in text:
        return "vybaveny"
    if "částečně vybaven" in text:
        return "castecne vybaveny"
    if "nevybaven" in text or "nezařízený" in text:
        return "nevybaveny"
    return None


def fetch_detail(uri):
    """
    fetches the listing detail page and extracts additional atributs with rgex
    :param uri: listing url like 'prodej-bytu-3-kk-Praha-9'
    :return: dictionary with flor, condition, funrished, has_balcony, has_parkign
    """
    try:
        r = requests.get(DETAIL_BASE.format(uri), headers=HEADERS_WEB, timeout=10)
        r.raise_for_status()
        html = r.text

        floor_match = re.search(r'"etage"\s*:\s*(\d+)', html)
        cond_match  = re.search(r'"condition"\s*:\s*"([^"]+)"', html)

        def get_bool(key):
            m = re.search(rf'"{key}"\s*:\s*(true|false)', html)
            return m and m.group(1) == "true"

        return {
            "floor":       int(floor_match.group(1)) if floor_match else None,
            "condition":   CONDITION_MAP.get(cond_match.group(1), cond_match.group(1).lower()) if cond_match else None,
            "furnished":   parse_furnished(html),
            "has_balcony": int(get_bool("balcony") or get_bool("terrace") or get_bool("loggia")),
            "has_parking": int(get_bool("parking") or get_bool("garage")),
        }
    except Exception:
        return {"floor": None, "condition": None, "furnished": None, "has_balcony": 0, "has_parking": 0}


def parse_listing(item):
    """
    parses a single graphql listing item into a flat record dictionary
    :param item: dict from graphql response = one listing
    :return: flat record dictionary or NOne
    """
    gps = item.get("gps") or {}
    lat, lon = gps.get("lat"), gps.get("lng")
    if lat and lon and not (CZ_BBOX[0] <= lat <= CZ_BBOX[1] and CZ_BBOX[2] <= lon <= CZ_BBOX[3]):
        return None

    tags      = item.get("tags") or []
    flat_type = DISPOSITION_MAP.get(item.get("disposition", ""), "")

    try:
        area_m2 = int(float(item["surface"])) if item.get("surface") else None
    except ValueError:
        area_m2 = None

    return {
        "uri":       item.get("uri", ""),
        "source":    "bezrealitky",
        "id":        item.get("id", ""),
        "name":      f"Prodej bytu {flat_type}",
        "price_czk": item.get("price"),
        "area_m2":   area_m2,
        "flat_type": flat_type,
        "locality":  item.get("address", ""),
        "lat":       lat,
        "lon":       lon,
        "has_lift":  int(any("výtah" in t.lower() for t in tags)),
        "furnished": parse_furnished(" ".join(tags)),
        "ownership": OWNERSHIP_MAP.get(str(item.get("ownership", "")), None),
        "has_balcony": 0, "has_parking": 0, "floor": None, "condition": None,
    }


def worker(task_queue, result_list, lock, counter):
    """
    worker thread - takes records from queue, fetches details of pages and saves result
    :param task_queue: queue of listing from dict to process
    :param result_list: shared list with completed records
    :param lock: threading lock to prevent race condition or result_list
    :param counter: single element list as counter
    :return: None
    """
    while True:
        rec = task_queue.get()
        if rec is None:
            task_queue.task_done()
            break

        detail = fetch_detail(rec.pop("uri"))
        rec.update({k: v for k, v in detail.items() if k != "furnished" or not rec["furnished"]})

        with lock:
            counter[0] += 1
            print(f"  [{counter[0]}] {rec['name'][:35]} → floor:{rec['floor']} balkon:{rec['has_balcony']} park:{rec['has_parking']} cond:{rec['condition']}")
            result_list.append(rec)

        task_queue.task_done()


def fetch_page(session, offset):
    """
    fetches one page listing from graphql api
    :param session: requests.Session with API headers already set
    :param offset: page * limit
    :return: tuple (list of listing dicts, total listing count)
    """
    payload = {
        "operationName": "AdvertList",
        "query": QUERY,
        "variables": {
            "locale": "CS", "offerType": ["PRODEJ"], "estateType": ["BYT"],
            "limit": LIMIT, "offset": offset, "order": "TIMEORDER_DESC",
            "regionOsmIds": [], "currency": "CZK",
        },
    }
    r = session.post(GRAPHQL_URL, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise ValueError(f"GraphQL chyba: {data['errors']}")
    adverts = data.get("data", {}).get("listAdverts", {})
    return adverts.get("list", []), adverts.get("totalCount", 0)


def scrape(max_pages=MAX_PAGES):
    """
    main scraping loop for bezrealitky, fetches all pages and processs details parael
    :param max_pages: maximum number of pages to scrape
    :return: list of all collected and enriched listing diccs
    """
    all_results = []
    session = requests.Session()
    session.headers.update(HEADERS_API)

    for page in range(max_pages):
        offset = page * LIMIT
        print(f"\nbezrealitky page: {page + 1} / {max_pages}")

        try:
            items, total = fetch_page(session, offset)
        except Exception as e:
            print(f"  Error  {e}"); break

        if not items:
            print("  no other records"); break

        records = []
        for item in items:
            p = parse_listing(item)
            if p is not None:
                records.append(p)

        task_queue = Queue()
        result_list =[]
        lock = Lock()
        counter = [0]

        for rec in records:
            task_queue.put(rec)
        for i in range(NUM_WORKERS):
            task_queue.put(None)

        threads = [Thread(target=worker, args=(task_queue, result_list, lock, counter)) for x in range(NUM_WORKERS)]
        for t in threads: t.start()
        task_queue.join()
        for t in threads: t.join()

        all_results.extend(result_list)
        print(f" Pagre done, collected: {len(all_results)} / {total}")

        if offset + LIMIT >= total:
            print("  end"); break

        time.sleep(DELAY)

    return all_results


def save_csv(records, path):
    """
    saves a list of record dicts to csv file
    :param records: list of record dicts (all must have same atributs)
    :param path: output file path
    :return: saves csv file, returns nothing
    """
    if not records:
        print("no data"); return
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"saved {len(records)} records -> {path}")



if __name__ == "__main__":
    save_csv(scrape(), OUTPUT_FILE)