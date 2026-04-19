
import json
import csv
import os
POI_FILES = {
    "stop":     "../scraping/data/geojsons/bus_tram.geojson",
    "train":    "../scraping/data/geojsons/railway_stations.geojson",
    "school":   "../scraping/data/geojsons/school.geojson",
    "kinder":   "../scraping/data/geojsons/kindergarden.geojson",
    "market":   "../scraping/data/geojsons/supermarkets.geojson",
    "hospital": "../scraping/data/geojsons/hospits.s",
}


OUTPUT_FILE = "../scraping/data/geojsons/geojsons.csv"


def extract(path: str, poi_type: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        features = json.load(f)["features"]

    records = []
    for feat in features:
        coords = feat["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        records.append({"type": poi_type, "lat": lat, "lon": lon})

    return records


if __name__ == "__main__":
    all_records = []

    for poi_type, path in POI_FILES.items():
        records = extract(path, poi_type)
        print(f"{poi_type}: {len(records)} zaznamu")
        all_records.extend(records)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["type", "lat", "lon"])
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nUlozeno {len(all_records)} zaznamu -> {OUTPUT_FILE}")