import requests
import csv
import re
import time
import os
from concurrent.futures import ThreadPoolExecutor

OUTPUT_FILE = "data/raw/sreality.csv"
DELAY    = 1.5
PER_PAGE = 100
MAX_PAGES = 60

BASE_URL   = "https://www.sreality.cz/api/cs/v2/estates?category_main_cb=1&category_type_cb=1&per_page={}&page={}"
DETAIL_URL = "https://www.sreality.cz/api/cs/v2/estates/{}"
HEADERS    = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept":     "application/json",
    "Referer":    "https://www.sreality.cz/",
}

OWNERSHIP_MAP = {"personal": "osobni", "cooperative": "druzstevni", "state": "statni"}
CONDITION_MAP = {
    "new_building": "novostavba", "after_reconstruction": "po rekonstrukci",
    "very_good": "velmi dobry",   "good": "dobry",
    "before_reconstruction": "pred rekonstrukci",
    "project": "projekt",         "under_construction": "ve vystavbe",
}
FURNISHED_MAP = {"furnished": "vybaveny", "partly_furnished": "castecne vybaveny", "not_furnished": "nevybaveny"}


def find_value(items, *names):
    """
    Searches sreality items list for a parameter by name
    :param items: list of dicts from the detail API response
    :param names: one or more parameter names to search like 'Podlaží', 'Stav'
    :return: parameter value as string, or None if not found
    """
    for item in items:
        if item.get("name") in names:
            val = item.get("value")
            return " ".join(str(v) for v in val) if isinstance(val, list) else str(val) if val else None
    return None


def fetch_detail(session, hash_id):
    """
    Fetches listing detail page and extracts floor and condition
    :param session: requests.Session with headers already set
    :param hash_id: sreality listing ID
    :return: dict with floor and condition
    """
    try:
        items = session.get(DETAIL_URL.format(hash_id), timeout=10).json().get("items", [])
        floor_match = re.search(r"(\d+)", find_value(items, "Podlaží", "Podlazi") or "")
        return {
            "floor":int(floor_match.group(1)) if floor_match else None,
            "condition": find_value(items, "Stav objektu", "Stav bytu", "Stav"),
        }
    except Exception:
        return {"floor": None, "condition": None}


def parse_listing(item):
    """
    Parses a single listing from the sreality list API into a flat record dict
    :param item: dict representing one listing from the API response
    :return: flat record dict with all listing attributes
    """
    name_raw = item.get("name", "")
    if isinstance(name_raw, dict):
        name = name_raw.get("value", "")
    else:
        name = str(name_raw)

    locality_raw = item.get("locality", "")
    if isinstance(locality_raw, dict):
        locality = locality_raw.get("value", "")
    else:
        locality = str(locality_raw)

    gps = item.get("gps", {})


    labels_all = item.get("labelsAll") or [[]]
    first = labels_all[0]

    if isinstance(first, list):
        labels = [l.lower() for l in first]
    else:
        labels = []

    area_match = re.search(r"(\d+)\s*m", name)
    type_match = re.search(r"(\d+\+(?:kk|\d+))", name, re.IGNORECASE)

    def from_labels(mapping):
        for k, v in mapping.items():
            if k in labels:
                return v
        return None

    return {
        "hash_id":     item.get("hash_id"),
        "source":      "sreality",
        "price_czk":   item.get("price"),
        "area_m2":     int(area_match.group(1)) if area_match else None,
        "flat_type":   type_match.group(1) if type_match else None,
        "locality":    locality,
        "lat":         gps.get("lat"),
        "lon":         gps.get("lon"),
        "has_lift":    int("elevator" in labels or "lift" in labels),
        "has_balcony": int(any(l in labels for l in ["balcony", "loggia", "terrace"])),
        "has_parking": int(any(l in labels for l in ["parking_lots", "garage", "parking"])),
        "floor":       None,
        "condition":   from_labels(CONDITION_MAP),
        "furnished":   from_labels(FURNISHED_MAP),
        "ownership":   from_labels(OWNERSHIP_MAP),
    }


def scrape(max_pages=MAX_PAGES):
    """
    Main scraping loop - fetches all listing pages and enriches with detail pages in parallel
    :param max_pages: maximum number of pages to scrape
    :return: list of all collected listing dicts
    """
    results = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for page in range(1, max_pages + 1):
        print(f"sreality Page {page} / {max_pages}")
        try:
            r = session.get(BASE_URL.format(PER_PAGE, page), timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"Error {e}"); break

        items = r.json().get("_embedded", {}).get("estates", []) #one estate record
        if not items:
            print("No more records "); break

        records = [parse_listing(item) for item in items]

        def enrich(rec):
            detail = fetch_detail(session, rec.pop("hash_id"))
            rec["floor"] = detail["floor"]
            if detail["condition"]:
                rec["condition"] = detail["condition"]
            return rec

        with ThreadPoolExecutor(max_workers=4) as ex:
            results.extend(ex.map(enrich, records))

        print(f"Total {len(results)}")

        if page * PER_PAGE >= r.json().get("result_size", 0):
            print("End of results"); break

        time.sleep(DELAY)

    return results


def save_csv(records, path):
    """
    Saves a list of record dicts to a CSV file
    :param records: list of flat listing dicts (all must have same keys)
    :param path: output file path e.g. 'data/raw/sreality.csv'
    :return: None
    """
    if not records:
        print("No data."); return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"Saved {len(records)} records -> {path}")


if __name__ == "__main__":
    save_csv(scrape(), OUTPUT_FILE)