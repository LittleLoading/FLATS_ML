# Flats ML – Flat Buy Advisor

## 1. Project Title
**Flats ML** – Machine Learning based flat price prediction and buyer category advisor

---

## 2. Project Description

Flats ML is a web application that helps real estate agents and buyers make smarter decisions when evaluating flat listings. The user fills in flat attributes (location, size, floor, amenities) and the system provides two predictions:

- **Is the price fair?** – The model estimates what the flat should cost
- **Who is this flat best for?** – The model classifies the flat as ideal for **seniors** (need hospitals and supermarkets nearby), **families with children** (need schools and kindergartens), or **adults/others** (prioritize public transport for work and commuting)

---

## 3. Features

- Data scraping from 3 real estate websites (sreality.cz, reality.idnes.cz, bezrealitky.cz)
- Consumer-worker architecture for fast parallel scraping
- POI distance enrichment via OpenStreetMap (Overpass)
- Data merging, cleaning, normalisation and deduplication
- Feature engineering (distance scores, price per m², has balcony, connectivity...)
- ML regression model – **HistGradientBoostingRegressor** (price prediction)
- ML classification model – **RandomForestClassifier** (buyer category)
- Interactive Flask web application

---

## 4. Installation

### Requirements

```
pip install -r requirements.txt
```

### Run the application

```
python main.py
```

Or on Windows double-click `run.bat`.

The application opens at `http://localhost:8081`.

---

## 5. How to Run with New Data

### 5.1 Data Collection

Run scrapers to collect fresh listings:

```bash
python scraping/sreality_scraping.py
python scraping/idnes_scraper.py
python scraping/bezrealitky_scraper.py
```

### 5.2 Data Processing

Merge, clean and normalise all sources:

```bash
python transform_data/transform_data.py
```

### 5.3 POI Enrichment

Download POI data from Overpass API (bus stops, schools, hospitals, supermarkets) and calculate distances:

```bash
python lib/transformGeojsons_to_csv.py
python lib/addCategoriesToListings.py
```

### 5.4 Model Training

Open Google Colab, upload `listings_enriched.csv` and run both notebooks:

- **Price model** – trains HistGradientBoostingRegressor, saves `model_price.pkl`
- **Classification model** – trains RandomForestClassifier, saves `model_group.pkl`

Download all `.pkl` files and place them in `UI/ModelsAndScalers/`.

### 5.5 Launch App

```bash
python main.py
```

---

## 6. Overview – What the System Does

The system collects flat listings including:

| Attribute | Description |
|---|---|
| `price` | Asking price in CZK |
| `area_m2` | Floor area in m² |
| `flat_rooms` | Number of rooms (e.g. 2+kk) |
| `has_lift` | Elevator present (0/1) |
| `has_balcony` | Balcony or loggia present (0/1) |
| `has_parking` | Parking space or garage (0/1) |
| `floor` | Floor number |
| `condition` | Flat condition (novostavba / velmi dobre / dobre) |
| `furnished` | Furnished state (vybavene / castecne / nevybavene) |
| `locality` | City name |
| `lat / lon` | GPS coordinates |
| `closest_stop_km` | Distance to nearest bus/tram stop |
| `closest_train_km` | Distance to nearest train station |
| `closest_school_km` | Distance to nearest school |
| `closest_kinder_km` | Distance to nearest kindergarten |
| `closest_market_km` | Distance to nearest supermarket |
| `closest_hospital_km` | Distance to nearest hospital or doctor |

---

## 7. Technology Decision Table

| Layer | Technology | Purpose | Why Chosen | Alternatives |
|---|---|---|---|---|
| Data collection (flats) | Python + requests / BeautifulSoup | Scraping sreality, iDnes, bezrealitky | Handles HTML and JSON APIs, no extra browser needed | Selenium, Scrapy |
| Scraping architecture | Consumer-Worker (Queue + Threading) | Parallel detail page fetching | 6–8× faster than sequential scraping | asyncio + aiohttp |
| GraphQL data collection | requests + GraphQL | Bezrealitky API | Public API, no auth required | HTML scraping |
| POI data | Overpass API (OpenStreetMap) | Download schools, stops, hospitals for whole CZ | Free, no API key, full CZ coverage | Google Maps API |
| POI distance calculation | Python + math (haversine) | Distance from flat to nearest POI | No external dependency, runs fully offline | geopy |
| Data processing | Pandas | Merging, cleaning, normalisation, feature engineering | Industry standard for tabular data | Polars |
| ML model – price | HistGradientBoostingRegressor (sklearn) | Predict flat price | Handles missing values natively, very accurate on tabular data | XGBoost, LightGBM |
| ML model – classification | RandomForestClassifier (sklearn) | Classify flat for senior/family/adult | Robust, interpretable, handles mixed feature types | XGBoost, SVM |
| Encoding – categorical | LabelEncoder + Target Encoding | Convert condition, locality etc. | Target encoding captures locality price signal | One-hot encoding |
| Scaling | StandardScaler (sklearn) | Normalise numeric features | Required for gradient-based models | MinMaxScaler |
| Model persistence | joblib | Save models and scalers | Standard for sklearn objects, fast serialisation | pickle |
| Visualisation | matplotlib | Training graphs (scatter, feature importance) | Simple integration with sklearn | Plotly, Seaborn |
| Web application | Flask | Serve predictions via web UI | Lightweight, Python-native, easy to run without IDE | Django, FastAPI |
| Frontend | HTML + Jinja2 templates | User input form and results display | Built into Flask, no JS framework needed | React, Vue |

---

## 8. System Architecture

```
Scrapers
├── sreality_scraping.py     ← Sreality JSON API + detail pages
├── idnes_scraper.py         ← iDnes HTML scraping (consumer-worker)
└── bezrealitky_scraper.py   ← Bezrealitky GraphQL API (consumer-worker)
        │
        ▼
Raw CSV datasets (data/raw/)
        │
        ▼
transform_data.py            ← merge, clean, normalise, deduplicate
        │
        ▼
POI Enrichment
├── transformGeojsons_to_csv.py   ← parse Overpass GeoJSON exports
└── addCategoriesToListings.py    ← haversine distance to nearest POI
        │
        ▼
listings_enriched.csv        ← final dataset for training
        │
        ▼
Google Colab – Model Training
├── Notebook 1: preprocessing + feature engineering → .pkl artifacts
├── Notebook 2: HistGradientBoostingRegressor (price)
└── Notebook 3: RandomForestClassifier (group)
        │
        ▼
UI/ModelsAndScalers/
├── model_price.pkl
├── model_group.pkl
├── scaler.pkl
├── label_encoders.pkl
├── target_enc.pkl
└── features.pkl
        │
        ▼
Flask Web Application (app.py)
└── User fills in flat attributes → model predicts price + buyer group
```

---

## 9. Machine Learning Pipeline

### 9.1 Data Preparation



```python
# Price cap and log transform
q_low  = df["price"].quantile(0.02)
df     = df[(df["price"] >= q_low) & (df["price"] <= 15_000_000)]
df["log_price"] = np.log1p(df["price"])   # log transform stabilises variance

# Categorical encoding
for col in ["condition", "furnished", "ownership"]:
    df[col + "_enc"] = LabelEncoder().fit_transform(df[col])

# Target encoding for locality (captures average price per city)
locality_means   = df.groupby("locality")["log_price"].mean()
df["locality_te"] = df["locality"].map(locality_means)

# Feature engineering
df["price_per_m2"]        = df["price"] / df["area_m2"]
df["locality_median_pm2"] = df.groupby("locality")["price_per_m2"].transform("median")
df["rooms_per_m2"]        = df["flat_rooms"] / df["area_m2"]
df["total_connectivity"]  = (df["closest_stop_km"] + df["closest_train_km"]) / 2
df["family_score"]        = (df["closest_school_km"] + df["closest_kinder_km"]) / 2
df["senior_score"]        = (df["closest_market_km"] + df["closest_hospital_km"]) / 2
df["comfort_score"]       = df["has_lift"] * df["floor"]
df["all_services_avg"]    = (df[["closest_stop_km","closest_train_km",
                                  "closest_school_km","closest_kinder_km",
                                  "closest_market_km","closest_hospital_km"]].mean(axis=1))
```

### 9.2 Price Model – HistGradientBoostingRegressor

```python
model = HistGradientBoostingRegressor(
    max_iter=500,
    learning_rate=0.05,
    min_samples_leaf=5,
    random_state=42,
)
model.fit(X_train, y_train)

# Evaluation (predictions converted back from log scale)
y_pred = np.expm1(model.predict(X_test))
y_true = np.expm1(y_test)
```

**Evaluation metrics:**

| Metric | Description |
|---|---|
| MAE (Kč) | Average absolute error in CZK |
| R² | Proportion of price variance explained by the model |

### 9.3 Classification Model – RandomForestClassifier

Buyer groups are assigned by weighted POI proximity scores:

```python
def blizko(km):
    return 1 / (1 + km)   # closer = higher score

df["score_rodina"]  = (0.40 * blizko(closest_kinder_km) +
                       0.40 * blizko(closest_school_km) +
                       0.20 * blizko(closest_stop_km))

df["score_senior"]  = (0.40 * blizko(closest_market_km) +
                       0.35 * blizko(closest_hospital_km) +
                       0.25 * blizko(closest_stop_km))

df["score_ostatni"] = (0.50 * blizko(closest_stop_km) +
                       0.50 * blizko(closest_train_km))
```

```python
model = RandomForestClassifier(
    n_estimators=300,
    max_depth=15,
    min_samples_leaf=2,
    class_weight="balanced",
    random_state=42,
)
```

**Evaluation:** accuracy, precision, recall, F1 per class, confusion matrix.

---

## 10. Model Output Logic

| Model | Output | Meaning |
|---|---|---|
| Price model | Estimated price in CZK | Compare with asking price – if asking > predicted, the flat may be overpriced |
| Classification | `rodina` | Flat is best suited for families with children – schools and kindergartens nearby |
| Classification | `senior` | Flat is best suited for elderly – supermarket and hospital in close walking distance |
| Classification | `ostatni` | Flat is best suited for working adults – excellent public transport and train connection |

---

## 11. Key Insights from Data

- **Location is the strongest price predictor** – locality target encoding captures city-level price differences more accurately than one-hot encoding
- **Floor area and number of rooms** drive price more than most amenities
- **Proximity to public transport** is the most universally important POI feature across all buyer groups
- **Flat condition** (novostavba vs. dobre) has significant impact on price – new builds command a premium of roughly 30–50% over comparable older flats
- **Balcony and elevator** add measurable value especially in higher floors
- **Praha districts** (Praha 1–10) show the widest price spread in the dataset

---

## 12. Future Improvements

- Add more scraping sources (e.g. RealityMix, Reality.cz) to increase dataset size
- Collect `total_floors` attribute to better contextualise floor number
- Scrape historical listings over multiple weeks to detect price trends
- Replace target encoding with cross-validated target encoding to prevent data leakage
- Add SHAP value explanations to the web app so users can see why a price was predicted
- Deploy on a VPS with automatic weekly re-scraping via cron job

---

## 13. Data Sources

| Source | Method | Data obtained |
|---|---|---|
| sreality.cz | Unofficial JSON API + detail pages | Price, area, rooms, condition, furnished, lift, GPS |
| reality.idnes.cz | HTML scraping (BeautifulSoup) | Price, area, rooms, balcony, parking, floor, condition |
| bezrealitky.cz | GraphQL API + detail pages | Price, area, rooms, lift, floor, condition, GPS |
| OpenStreetMap (Overpass API) | GeoJSON export + haversine | Distances to stops, schools, hospitals, supermarkets |



colab:
https://colab.research.google.com/drive/1_iSFMk_l6IWR9QVsqQA3apXELxfQONuX?usp=sharing



