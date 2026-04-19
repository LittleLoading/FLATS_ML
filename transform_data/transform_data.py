import pandas as pd
import os

INPUT_FILES = [
    "../scraping/data/raw/sreality.csv",
    "../scraping/data/raw/idnes.csv",
    "../scraping/data/raw/bezrealitky.csv",
]
OUTPUT_FILE = "../data/processed/listings.csv"

MIN_LOCALITY_COUNT = 30

CITIES = [
    "Praha 10", "Praha 1", "Praha 2", "Praha 3", "Praha 4",
    "Praha 5", "Praha 6", "Praha 7", "Praha 8", "Praha 9", "Praha",
    "České Budějovice", "Český Krumlov", "Jindřichův Hradec", "Písek",
    "Prachatice", "Strakonice", "Tábor",
    "Brno", "Blansko", "Břeclav", "Hodonín", "Vyškov", "Znojmo",
    "Karlovy Vary", "Cheb", "Sokolov",
    "Havlíčkův Brod", "Jihlava", "Pelhřimov", "Třebíč", "Žďár nad Sázavou",
    "Hradec Králové", "Rychnov nad Kněžnou", "Jičín", "Náchod", "Trutnov",
    "Jablonec nad Nisou", "Česká Lípa", "Liberec", "Semily",
    "Ostrava", "Frýdek-Místek", "Bruntál", "Karviná", "Nový Jičín", "Opava",
    "Olomouc", "Jeseník", "Prostějov", "Přerov", "Šumperk",
    "Ústí nad Orlicí", "Chrudim", "Pardubice", "Svitavy",
    "Plzeň", "Domažlice", "Klatovy", "Rokycany", "Tachov",
    "Mladá Boleslav", "Kutná Hora", "Benešov", "Beroun", "Kladno",
    "Kolín", "Mělník", "Nymburk", "Příbram", "Rakovník",
    "Ústí nad Labem", "Děčín", "Chomutov", "Litoměřice", "Louny",
    "Most", "Teplice",
    "Uherské Hradiště", "Kroměříž", "Vsetín", "Zlín",
]


CONDITION_MAP = {
    "novostavba":                  "novostavba",
    "ve vystavbe":                 "novostavba",
    "ve výstavbě":                 "novostavba",
    "projekt":                     "novostavba",
    "project":                     "novostavba",
    "construction":                "novostavba",
    "in_reconstruction":           "novostavba",
    "po rekonstrukci":             "velmi dobre",
    "after_reconstruction":        "velmi dobre",
    "after_partial_reconstruction":"velmi dobre",
    "velmi dobry":                 "velmi dobre",
    "velmi dobrý":                 "velmi dobre",
    "velmi dobrý stav":            "velmi dobre",
    "very_good":                   "velmi dobre",
    "dobry":                       "dobre",
    "dobrý":                       "dobre",
    "dobrý stav":                  "dobre",
    "good":                        "dobre",
    "puvodni stav":                "dobre",
    "pred rekonstrukci":           "spatne",
    "před rekonstrukcí":           "spatne",
    "k rekonstrukci":              "spatne",
    "spatny":                      "spatne",
    "špatný stav":                 "spatne",
    "bad":                         "spatne",
}

FURNISHED_MAP = {
    "vybaveny":           "vybavene",
    "partly_furnished":   "castecne vybavene",
    "castecne vybaveny":  "castecne vybavene",
    "not_furnished":      "nevybavene",
    "nevybaveny":         "nevybavene",
    "plně vybaven":       "vybavene",
    "vybavený":           "vybavene",
    "částečně vybaven":   "castecne vybavene",
    "nezařízený":         "nevybavene",
    "zařízený":           "vybavene",
    "částečně":           "castecne vybavene",
    "nezařízeno":         "nevybavene",
    "nezařízený byt":     "nevybavene",
}

OWNERSHIP_MAP = {
    "osobni":      "osobni",
    "osobní":      "osobni",
    "personal":    "osobni",
    "druzstevni":  "druzstevni",
    "družstevní":  "druzstevni",
    "cooperative": "druzstevni",
    "statni":      "statni",
    "státní":      "statni",
    "state":       "statni",
}


def clean_city(locality_text):
    """
    extracts name of the city from text by list of names of CITIES
    :param locality_text: text of locality, scraped raw
    :return: name of the city or Ostatni
    """
    loc = str(locality_text)
    for city in CITIES:
        if city in loc:
            return city
    return "Ostatní"


def parse_flat_type(flat_type):
    """
    Parses type of flat (3+kk) to (3, true)
    :param flat_type: string 3+kk or 3+1
    :return: returns int and bool, or None None
    """
    if not isinstance(flat_type, str):
        return None, None
    has_kk = flat_type.lower().endswith("kk")
    try:
        rooms = int(flat_type.split("+")[0])
    except (ValueError, IndexError):
        rooms = None
    return rooms, has_kk


def normalize_condition(val):
    """
    Converts conditions into normalized values like 'dobre', or 'rekonstrukce'
    :param val: string of condition like 'po rekonstruci'
    :return: normalized condition or None
    """
    if pd.isna(val) or not str(val).strip():
        return None
    v = str(val).lower().strip()
    for key, normalized in CONDITION_MAP.items():
        if key in v:
            return normalized
    return None


def normalize_furnished(val):
    """
    Converts statis of furnished into normalised value
    :param val: string of furnished like 'castecne Vybaveny', raw scraped
    :return: string normalized furnished or None
    """
    if pd.isna(val) or not str(val).strip():
        return None
    v = str(val).lower().strip()
    if v in FURNISHED_MAP:
        return FURNISHED_MAP[v]
    if "částečně vybaven" in v or "castecne vybaven" in v:
        return "castecne vybavene"
    if "nevybaven" in v or "nezařízený" in v or "nezarizen" in v:
        return "nevybavene"
    if v in ("vybaveno", "zařízeno", "vybaven"):
        return "vybavene"
    return None


def normalize_ownership(val):
    """
    converts different types of ownership to normalized values
    osobni or personal conerts to 'osobni'
    :param val: input string of ownership raw scraped
    :return: string normalized ownership or None
    """
    if pd.isna(val) or not str(val).strip():
        return None
    v = str(val).lower().strip()
    for key, normalized in OWNERSHIP_MAP.items():
        if key in v:
            return normalized
    return None


def load_and_merge(files):
    """
     loads csv files from a list of paths and merges them into one dataframe
    :param files: list of paths to csv files
    :return: dataframe of merged data
    """
    frames = []
    for f in files:
        if not os.path.exists(f):
            continue
        df = pd.read_csv(f)
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No input files found")
    return pd.concat(frames, ignore_index=True)


def preprocess(df):
    """
    cleands and prepares raw listing data for model training:
    preperes flat type, normalizes locality, condition, furnished, ownership
    drop rows with some None attributes
    filters extreme weird prices and aread or bad listings
    removes duplicates and locations with less than 30
    :param df: pandas dataframe of flats
    :return: pandas dataframe of cleaned data
    """
    df = df.rename(columns={"price_czk": "price", "flat_type": "flat_rooms_raw"})

    parsed = df["flat_rooms_raw"].apply(parse_flat_type)
    df["flat_rooms"] = parsed.apply(lambda x: x[0])
    df["has_kk"] = parsed.apply(lambda x: x[1])

    df["locality"] = df["locality"].apply(clean_city)
    df["condition"] = df.get("condition", pd.Series()).apply(normalize_condition)
    df["furnished"] = df.get("furnished", pd.Series()).apply(normalize_furnished)
    df["ownership"] = df.get("ownership", pd.Series()).apply(normalize_ownership)

    for col in ["has_lift", "has_balcony", "has_parking"]:
        df[col] = df[col].fillna(0).astype(int) if col in df.columns else 0

    if "floor" not in df.columns:
        df["floor"] = None

    df = df[["source", "price", "area_m2", "flat_rooms", "has_kk", "has_lift", "has_balcony", "has_parking", "floor", "condition", "furnished", "ownership", "locality", "lat", "lon"]]

    df = df.dropna(subset=["source", "price", "area_m2", "flat_rooms", "has_kk", "locality", "lat", "lon"])

    df = df[df["price"] >= 100_000]
    df = df[df["area_m2"].between(15, 300)]
    df = df[df["locality"] != "Ostatní"]
    df = df[df["condition"] != "spatne"]

    df["floor"] = pd.to_numeric(df["floor"], errors="coerce")
    df = df.dropna(subset=["floor"])

    int_cols = ["price", "area_m2", "flat_rooms", "has_kk", "has_lift", "has_balcony", "has_parking", "floor"]
    df[int_cols] = df[int_cols].astype(int)
    df["lat"] = df["lat"].astype(float).round(6)
    df["lon"] = df["lon"].astype(float).round(6)

    df = df.drop_duplicates(subset=["price", "area_m2", "flat_rooms", "lat", "lon"])
    df = df.dropna()

    valid = df["locality"].value_counts()
    valid = valid[valid >= MIN_LOCALITY_COUNT].index
    df = df[df["locality"].isin(valid)]

    return df.reset_index(drop=True)


def save(df, path):
    """
    from te
    :param df:
    :param path:
    :return:
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


if __name__ == "__main__":
    df = load_and_merge(INPUT_FILES)
    df = preprocess(df)
    save(df, OUTPUT_FILE)


