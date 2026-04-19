import pandas as pd
import numpy as np

# 1. Načtení dat
df_listings = pd.read_csv('../scraping/data/processed/listings.csv').dropna(subset=['lat', 'lon'])
df_geo = pd.read_csv('../scraping/data/geojsons/geojsons.csv').dropna(subset=['lat', 'lon'])



def get_min_distance(lat, lon, amenity_lats, amenity_lons):
    R = 6371.0  # Poloměr Země v km

    # Převod stupňů na radiány (nutné pro matematické funkce sin/cos)
    lat1, lon1, lat2, lon2 = map(np.radians, [lat, lon, amenity_lats, amenity_lons])

    # Výpočet rozdílů
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Výpočet vzdušné čáry (Haversine formula)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    distances = R * c

    # Vrátíme tu úplně nejmenší vzdálenost (k nejbližšímu bodu)
    return np.min(distances)


# 3. Zpracování pro každý typ občanské vybavenosti
amenity_types = df_geo['type'].unique()

for amenity in amenity_types:
    df_amenity = df_geo[df_geo['type'] == amenity]

    if len(df_amenity) == 0:
        continue

    # Vytáhneme si všechny souřadnice dané vybavenosti (např. všech zastávek)
    amenity_lats = df_amenity['lat'].values
    amenity_lons = df_amenity['lon'].values

    # Pro každý byt aplikujeme naši funkci – spočítá vzdálenost ke VŠEM zastávkám a vrátí tu nejmenší
    df_listings[f'closest_{amenity}_km'] = df_listings.apply(
        lambda row: get_min_distance(row['lat'], row['lon'], amenity_lats, amenity_lons),
        axis=1
    )

# 4. Uložení
df_listings.to_csv('../scraping/data/finished/listings_enriched.csv', index=False)