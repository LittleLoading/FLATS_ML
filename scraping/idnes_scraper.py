import requests
from bs4 import BeautifulSoup
import csv
import re
import time
import os
from queue import Queue
from threading import Thread, Lock

OUTPUT_FILE = "data/raw/idnes.csv"
DELAY       = 0.5
MAX_PAGES   = 150
NUM_WORKERS = 15

LIST_URL = "https://reality.idnes.cz/s/prodej/byty/?page={}"
BASE     = "https://reality.idnes.cz"
HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "cs",
    "Referer":         "https://reality.idnes.cz/",
}

CZ_BBOX = (48.55, 51.06, 12.09, 18.87)


def fetch_detail(href):
    """
    Fetches detail page and extracts listing attributes from <dl> tag
    :param href: relative or absolute URL of the listing detail page
    :return: dict with lat, lon, has_lift, has_balcony, has_parking, floor, condition, furnished
    """
    result = {"lat": None, "lon": None, "has_lift": 0, "has_balcony": 0,
              "has_parking": 0, "floor": None, "condition": None, "furnished": None}
    try:
        url  = href if href.startswith("http") else BASE + href
        soup = BeautifulSoup(requests.get(url, headers=HEADERS, timeout=10).text, "html.parser")
        html = soup.get_text()

        m = re.search(r'"center"\s*:\s*\[([\d.]+),\s*([\d.]+)\]', str(soup))
        if m:
            result["lon"], result["lat"] = float(m.group(1)), float(m.group(2))

        dl     = soup.select_one("dl")
        params = {dt.get_text(strip=True): dd.get_text(strip=True)
                  for dt, dd in zip(dl.select("dt"), dl.select("dd"))} if dl else {}

        result["has_lift"]    = int("Výtah" in params)
        result["has_balcony"] = int(any(k in params for k in ["Balkón", "Balkon", "Lodžie", "Lodzie", "Terasa"]))

        parking = params.get("Parkování", "").lower()
        result["has_parking"] = int(bool(parking) and "ulici" not in parking and "okolí" not in parking)

        floor_match = re.search(r"(\d+)", params.get("Podlaží", ""))
        result["floor"] = int(floor_match.group(1)) if floor_match else None

        result["condition"] = params.get("Stav bytu") or params.get("Stav budovy")

        furnished = params.get("Vybavení", "").lower()
        if furnished:
            if "nezař" in furnished or "nevybav" in furnished:
                result["furnished"] = "nevybaveny"
            elif "částečně" in furnished:
                result["furnished"] = "castecne vybaveny"
            else:
                result["furnished"] = "vybaveny"

    except Exception:
        pass
    return result


def parse_page(html):
    """
    Parses listing page HTML and extracts basic listing info from article tags
    :param html: raw HTML string of the listing page
    :return: list of partial listing dicts (without detail page attributes)
    """
    soup    = BeautifulSoup(html, "html.parser")
    records = []

    for article in soup.select("article"):
        link = article.select_one("a.c-products__link")
        if not link:
            continue

        title_tag = article.select_one("h2.c-products__title")
        title= " ".join(title_tag.get_text(separator=" ", strip=True).split()) if title_tag else ""
        title= title[0].upper() + title[1:] if title else ""

        locality_tag = article.select_one("p.c-products__info")
        price_tag= article.select_one(".c-products__price strong")
        raw = re.sub(r"[^\d]", "", price_tag.get_text()) if price_tag else ""
        price = int(raw) if raw else None

        if not title and not price:
            continue

        flat_match = re.search(r"(\d+\+(?:kk|\d+))", title, re.IGNORECASE)
        area_match = re.search(r"(\d+)\s*m", title)

        records.append({
            "href":link.get("href", ""),
            "source":"idnes",
            "price_czk":price,
            "area_m2":int(area_match.group(1)) if area_match else None,
            "flat_type":flat_match.group(1) if flat_match else None,
            "locality": locality_tag.get_text(strip=True) if locality_tag else "",
            "lat": None, "lon": None,
            "has_lift": 0, "has_balcony": 0, "has_parking": 0,
            "floor": None, "condition": None, "furnished": None,
        })
    return records


def worker(task_queue, result_list, lock, counter):
    """
    Worker thread - fetches detail page for each listing and saves result
    :param task_queue: Queue of partial listing dicts
    :param result_list: shared list where completed records are appended
    :param lock: threading Lock to prevent race conditions on result_list
    :param counter: single-element list [int] used as a shared mutable counter
    :return: None
    """
    while True:
        rec = task_queue.get()
        if rec is None:
            task_queue.task_done()
            break
        rec.update(fetch_detail(rec.pop("href")))
        with lock:
            counter[0] += 1
           #print(f"  [{counter[0]}] balkon:{rec['has_balcony']} park:{rec['has_parking']} cond:{rec['condition']}")
            result_list.append(rec)
        task_queue.task_done()


def scrape(max_pages=MAX_PAGES):
    """
    Main scraping loop - fetches all listing pages and enriches with detail pages in parallel
    :param max_pages: maximum number of listing pages to scrape
    :return: list of all collected listing dicts
    """
    all_results = []
    session     = requests.Session()
    session.headers.update(HEADERS)

    for page in range(max_pages):
        print(f"\n idnes Page {page + 1} / {max_pages}")
        try:
            r = session.get(LIST_URL.format(page), timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"Error {e}"); break

        records = parse_page(r.text)
        if not records:
            print("No records, stopping"); break

        task_queue = Queue()
        result_list = []
        lock = Lock()
        counter = [0]


        for rec in records:
            task_queue.put(rec)
        for i in range(NUM_WORKERS):
            task_queue.put(None)

        threads = [Thread(target=worker, args=(task_queue, result_list, lock, counter)) for i in range(NUM_WORKERS)]
        for t in threads: t.start()
        task_queue.join()
        for t in threads: t.join()

        for rec in result_list:
            lat, lon = rec["lat"], rec["lon"]
            if lat is None or (CZ_BBOX[0] <= lat <= CZ_BBOX[1] and CZ_BBOX[2] <= lon <= CZ_BBOX[3]):
                all_results.append(rec)

        print(f"Total {len(all_results)}")

        if not BeautifulSoup(r.text, "html.parser").select("p.paginator a.paging__item"): # []
            print("Last page"); break

        time.sleep(DELAY)

    return all_results


def save_csv(records, path):
    """
    Saves a list of record dicts to a CSV file
    :param records: list of flat listing dicts
    :param path: output file path, e.g. 'data/raw/idnes.csv'
    :return: None
    """
    if not records:
        print("No data"); return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"Saved {len(records)} records{path}")


if __name__ == "__main__":
    save_csv(scrape(), OUTPUT_FILE)