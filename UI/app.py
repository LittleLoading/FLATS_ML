from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
import joblib, json, os

app = Flask(__name__, template_folder='../lib/templates')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS   = os.path.join(BASE_DIR, "ModelsAndScalers")
GEOJSONS = os.path.join(BASE_DIR, "..", "scraping", "data", "geojsons")

scaler         = joblib.load(f"{MODELS}/scaler.pkl")
label_encoders = joblib.load(f"{MODELS}/label_encoders.pkl")
target_enc     = joblib.load(f"{MODELS}/target_enc.pkl")
features       = joblib.load(f"{MODELS}/features.pkl")
model_price    = joblib.load(f"{MODELS}/model_price.pkl")
model_group    = joblib.load(f"{MODELS}/model_group.pkl")


def load_geojson(path):
    """
    Loads .geojson file and returns numpy field [[lat,lon], ...]
    :param path: path to .geojson file
    :return: numpy field [[lat,lon], ...]
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    pts = []
    for feat in data["features"]:
        g = feat["geometry"]
        if not g: continue
        c = g["coordinates"]
        if g["type"] == "Point":
            pts.append((c[1], c[0]))
        else:
            while isinstance(c[0], list): c = c[0]  # Polygon → vezmeme první bod
            pts.append((c[1], c[0]))
    return np.array(pts)


POI = {
    "stop":     load_geojson(f"{GEOJSONS}/bus_tram.geojson"),
    "train":    load_geojson(f"{GEOJSONS}/railway_stations.geojson"),
    "school":   load_geojson(f"{GEOJSONS}/school.geojson"),
    "kinder":   load_geojson(f"{GEOJSONS}/kindergarden.geojson"),
    "market":   load_geojson(f"{GEOJSONS}/supermarkets.geojson"),
    "hospital": load_geojson(f"{GEOJSONS}/hospits.geojson"),
}

CITY_BOUNDS = {
    "Brno":             (49.10, 49.30, 16.45, 16.75),
    "Karlovy Vary":     (50.17, 50.28, 12.80, 12.95),
    "Kladno":           (50.10, 50.20, 14.05, 14.20),
    "Liberec":          (50.72, 50.82, 14.98, 15.12),
    "Olomouc":          (49.55, 49.62, 17.20, 17.35),
    "Ostrava":          (49.77, 49.88, 18.15, 18.40),
    "Pardubice":        (49.99, 50.08, 15.73, 15.85),
    "Plzeň":            (49.70, 49.78, 13.32, 13.45),
    "Praha":            (49.94, 50.18, 14.22, 14.71),
    "Praha 1":          (50.07, 50.10, 14.40, 14.46),
    "Praha 2":          (50.06, 50.09, 14.41, 14.46),
    "Praha 3":          (50.07, 50.10, 14.44, 14.50),
    "Praha 4":          (49.99, 50.06, 14.40, 14.52),
    "Praha 5":          (50.02, 50.08, 14.33, 14.42),
    "Praha 6":          (50.07, 50.13, 14.31, 14.42),
    "Praha 8":          (50.09, 50.15, 14.43, 14.53),
    "Praha 9":          (50.09, 50.16, 14.49, 14.60),
    "Trutnov":          (50.58, 50.68, 15.88, 16.00),
    "Zlín":             (49.20, 49.27, 17.64, 17.72),
    "České Budějovice": (48.95, 49.02, 14.43, 14.53),
    "Český Krumlov":    (48.66, 48.73, 14.29, 14.35),
}

def nearest_km(lat, lon, poi_array):
    """
    returns nearest point in poi_array, got big help from CLAUDE!
    :param lat: latitude
    :param lon: longitude
    :param poi_array: array of [lat,lon] and names
    :return: nearest point in poi_array [lat,lon]
    """
    dlat = np.radians(poi_array[:, 0] - lat)
    dlon = np.radians(poi_array[:, 1] - lon)
    a    = (np.sin(dlat/2)**2 +
            np.cos(np.radians(lat)) * np.cos(np.radians(poi_array[:, 0])) *
            np.sin(dlon/2)**2)
    return float(6371 * 2 * np.arcsin(np.sqrt(a.clip(0, 1))).min())

def blizko(km):
    """
    convert distance to score 0km -> 1.0, 1km to 0.5, etc
    :param km: distance from point
    :return: score from 0 too 1
    """
    return 1 / (1 + km)

@app.route("/")
def index():
    """
    Main page, sends dropdown of cities and their borders to html
    :return: index page with data cities and borders
    """
    cities = sorted(CITY_BOUNDS.keys())
    bounds = {city: {"lat_min": b[0], "lat_max": b[1], "lon_min": b[2], "lon_max": b[3]}
              for city, b in CITY_BOUNDS.items()}
    return render_template("index.html", cities=cities, bounds=bounds)

@app.route("/predict", methods=["POST"])
def predict():
    """
    gets json form, calculates distance predicts values and returns them
    :return: jsonify predictions of value and categories
    """
    d        = request.json
    locality = d["locality"]
    lat      = float(d["lat"])
    lon      = float(d["lon"])

    b = CITY_BOUNDS.get(locality)
    if b and not (b[0] <= lat <= b[1] and b[2] <= lon <= b[3]):
        return jsonify({"error": f"Coordinets outside of the selected city {locality}"}), 400

    dist = {key: nearest_km(lat, lon, arr) for key, arr in POI.items()}

    area        = float(d["area"])
    rooms       = int(d["rooms"])
    floor       = int(d["floor"])
    has_kk      = int(d["has_kk"])
    has_lift    = int(d["has_lift"])
    has_balcony = int(d["has_balcony"])
    has_parking = int(d["has_parking"])
    condition   = d["condition"]
    furnished   = d["furnished"]
    ownership   = d["ownership"]


    te_val  = target_enc["locality_means"].get(locality, target_enc["global_mean"])
    med_pm2 = np.expm1(te_val) * 0.9

    price_row = pd.DataFrame([{
        "area_m2":             area,
        "flat_rooms":          rooms,
        "has_kk":              has_kk,
        "has_lift":            has_lift,
        "has_balcony":         has_balcony,
        "has_parking":         has_parking,
        "floor":               floor,
        "condition_enc":       label_encoders["condition"].transform([condition])[0],
        "furnished_enc":       label_encoders["furnished"].transform([furnished])[0],
        "ownership_enc":       label_encoders["ownership"].transform([ownership])[0],
        "locality_te":         te_val,
        "locality_median_pm2": med_pm2,
        "closest_stop_km":     dist["stop"],
        "closest_train_km":    dist["train"],
        "closest_school_km":   dist["school"],
        "closest_kinder_km":   dist["kinder"],
        "closest_market_km":   dist["market"],
        "closest_hospital_km": dist["hospital"],
        "rooms_per_m2":        rooms / area,
        "total_connectivity":  (dist["stop"] + dist["train"]) / 2,
        "family_score":        (dist["school"] + dist["kinder"]) / 2,
        "senior_score":        (dist["market"] + dist["hospital"]) / 2,
        "comfort_score":       has_lift * floor,
        "all_services_avg":    sum(dist.values()) / 6,
    }])

    price_scaled    = pd.DataFrame(scaler.transform(price_row[features]), columns=features)
    predicted_price = int(np.expm1(model_price.predict(price_scaled)[0]))


    le_loc  = label_encoders.get("locality")
    loc_enc = int(le_loc.transform([locality])[0]) if le_loc and locality in le_loc.classes_ else 0

    group_row = pd.DataFrame([{
        "score_rodina": 0.40*blizko(dist["kinder"]) + 0.40*blizko(dist["school"])   + 0.20*blizko(dist["stop"]),
        "score_senior": 0.40*blizko(dist["market"]) + 0.35*blizko(dist["hospital"]) + 0.25*blizko(dist["stop"]),
        "score_ostatni":0.50*blizko(dist["stop"])   + 0.50*blizko(dist["train"]),
        "closest_stop_km":  dist["stop"],
        "closest_train_km": dist["train"],
        "closest_school_km":dist["school"],
        "closest_kinder_km":dist["kinder"],
        "closest_market_km":dist["market"],
        "closest_hospital_km": dist["hospital"],
        "area_m2": area,
        "flat_rooms":  rooms,
        "price_per_m2":predicted_price / area,
        "floor":floor,
        "has_lift":has_lift,
        "has_balcony":has_balcony,
        "has_parking":has_parking,
        "condition_enc":label_encoders["condition"].transform([condition])[0],
        "furnished_enc":label_encoders["furnished"].transform([furnished])[0],
        "ownership_enc":label_encoders["ownership"].transform([ownership])[0],
        "locality_enc":loc_enc,
    }])

    GROUP_FEATURES = [
        "score_rodina",
        "score_senior",
        "score_ostatni",
        "closest_stop_km",
        "closest_train_km",
        "closest_school_km",
        "closest_kinder_km",
        "closest_market_km",
        "closest_hospital_km",
        "area_m2",
        "flat_rooms",
        "price_per_m2",
        "floor",
        "has_lift",
        "has_balcony",
        "has_parking",
        "condition_enc",
        "furnished_enc",
        "ownership_enc",
        "locality_enc",
    ]

    predicted_group = model_group.predict(group_row[GROUP_FEATURES])[0]
    proba           = model_group.predict_proba(group_row[GROUP_FEATURES])[0]
    proba_dict      = {cls: round(float(p)*100, 1) for cls, p in zip(model_group.classes_, proba)}

    return jsonify({
        "price":     predicted_price,
        "group":     predicted_group,
        "proba":     proba_dict,
        "distances": {k: round(v, 3) for k, v in dist.items()},
    })

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8081)