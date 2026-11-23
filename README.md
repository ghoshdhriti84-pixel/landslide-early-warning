# AI-Based Early Warning and Landslide Risk Monitoring System
### North Eastern Region (NER) of India — web prototype

A beginner-friendly Flask + SQLite + Chart.js + Leaflet web application that monitors
landslide-risk indicators for selected locations in Northeast India, displays risk levels,
raises threshold-based demonstration alerts, and includes a machine-learning prediction module.

> **This is a prototype, not an official emergency-warning service.**
> Readings are simulated/sample data unless a user submits them. Alerts are threshold
> crossings on a *transparent demonstration index*, not validated scientific forecasts.
> Always follow IMD, GSI and your State Disaster Management Authority for real decisions.

---

## 1. What the application does

| Page | Route | Purpose |
|---|---|---|
| Dashboard | `/` | Current temperature, rainfall, humidity, soil moisture; overall risk level; monitored-location & active-alert counts; rainfall/risk trend charts; risk-band chart; notification panel |
| Interactive Risk Map | `/map` | Leaflet + OpenStreetMap map of NER locations, colour-coded markers by risk level, click for readings + last update, risk filter, legend, location list |
| Early Warning System | `/alerts` | Alert log with affected location, alert level, timestamp and recommended safety action; configured thresholds; safety guidance |
| Data Monitoring | `/monitoring` | Validated data-entry form (temperature, rainfall, humidity, soil moisture); stored in SQLite; dashboard/map/charts/alerts update immediately |
| Prediction Module | `/prediction` | Random-Forest classifier + transparent index cross-check; predicted category, class probabilities, factor influences, honest model provenance |

Key honesty features built into the UI:

* A permanent banner stating that this is a demonstration system.
* Every stored reading carries `data_source` = `simulated` or `observed`; the UI shows which.
* The prediction page reports **data provenance** and explicitly states that metrics from
  synthetic data are *not* real-world accuracy.
* Missing data is shown as “No data” — never estimated or invented.

---

## 2. Technology stack (all free)

* **Frontend:** HTML5, CSS3, vanilla JavaScript
* **Backend:** Python 3 + Flask
* **Data / ML:** Pandas, NumPy, scikit-learn (Random Forest)
* **Database:** SQLite (file-based, no server needed)
* **Charts:** Chart.js (CDN)
* **Map:** Leaflet.js with OpenStreetMap tiles (CDN)

No API keys, no secrets, no paid services. Internet is only needed for the two CDN
libraries and the OSM map tiles — everything else runs locally.

---

## 3. Project structure

```
landslide/
├── app.py                     # Flask backend: routes, validation, SQLite, alerts
├── model.py                   # demonstration risk index + Random Forest pipeline
├── requirements.txt           # Python dependencies
├── README.md                  # this file
├── data/
│   ├── locations.json         # sample NER monitoring locations + terrain metadata
│   ├── demo_model.pkl         # cached demo model (auto-created, safe to delete)
│   └── dataset.csv            # OPTIONAL: your own labelled dataset (see §7)
├── database/
│   └── landslide.db           # SQLite database (auto-created on first run)
├── templates/
│   ├── base.html              # shared layout: logo, nav, notification panel, banner
│   ├── dashboard.html
│   ├── map.html
│   ├── alerts.html
│   ├── monitoring.html
│   ├── prediction.html
│   └── error.html
└── static/
    ├── css/style.css          # dark-blue/black professional theme, responsive
    └── js/
        ├── script.js          # shared helpers: API, toasts, notification panel, colours
        ├── dashboard.js
        ├── map.js
        ├── alerts.js
        ├── monitoring.js
        └── prediction.js
```

---

## 4. Install and run (Windows, PowerShell)

Open the project folder in **VS Code** or **TRAE** (`File → Open Folder` → select `landslide`),
then in the integrated terminal (`` Ctrl+` ``):

```powershell
# 1) Go to the project folder (adjust if your path differs)
cd c:\Users\DHRITI\Documents\trae_projects\landslide

# 2) Create a virtual environment
python -m venv .venv

# 3) Activate it (PowerShell)
.\\.venv\\Scripts\\Activate.ps1
#    If activation is blocked, run once:
#    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 4) Install dependencies
pip install -r requirements.txt

# 5) Start the application
python app.py
```

You should see:

```
 * Running on http://127.0.0.1:5000
```

Open **http://127.0.0.1:5000** in your browser.
Stop the server with `Ctrl + C`.

Notes:

* On first start the app creates `database/landslide.db`, seeds 14 NER locations and
  **7 days of simulated readings** (every 6 hours), and trains the demo model once
  (a few seconds; later starts reuse `data/demo_model.pkl`).
* VS Code alternative: select the `.venv` interpreter (`Ctrl+Shift+P` →
  “Python: Select Interpreter”) and press **F5** / use
  “Python: Run Flask app”. Debug mode is already enabled in `app.py`.

---

## 5. Step-by-step testing of every feature

1. **Dashboard loads** → open `http://127.0.0.1:5000`.
   * Check the four metric cards show numbers (regional averages).
   * Check “Overall Landslide Risk Level” pill shows one of Low / Moderate / High / Very High.
   * Check “Monitored locations” = 14 and “Active alerts” ≥ 0.
   * Check the Rainfall & Risk Trend chart, Risk Band doughnut and Risk-by-Location bar chart.
2. **Notification panel** → click the 🔔 bell in the top bar.
   * The red counter shows unread alerts; clicking an alert’s **Mark read** removes it from the count.
   * Click **Mark all read** → toast “n alert(s) marked as read”, counter disappears.
3. **Risk map** → click **Risk Map** in the sidebar.
   * Confirm the Northeast-India map, coloured circular markers, and the legend.
   * Click a marker → popup shows location name, temperature, rainfall 24 h/72 h, humidity,
     soil moisture, risk index, **last update** and data source; the right-hand panel shows details.
   * Change **Filter by risk** → only that risk level’s markers remain.
   * Click a row in “All locations” → map zooms to it.
4. **Early warning system** → click **Early Warnings**.
   * Advisory / Warning / Severe counters and the threshold table appear.
   * Each alert card shows location, level, timestamp and **recommended safety action**.
   * Tick “Show acknowledged” to see alerts you marked read.
5. **Data monitoring (form validation)** → click **Data Monitoring**.
   * Press **Submit reading** with an empty form → red field messages, nothing saved.
   * Type `temperature = 500` → “Temperature must be between -20 and 55 deg C.”
   * Type `humidity = 150` → range error. Fix the values → submission succeeds.
   * Click **Fill example values** for a quick monsoon-style example, then submit.
6. **New reading updates everything** → after a successful submit:
   * The green message and the “Result of Last Submission” card show the new risk index,
     risk level, contributions per factor and the auto-computed 72-hour rainfall.
   * The badge in “Latest Stored Readings” shows **Observed** for your row.
   * Go back to the **Dashboard** (or press Refresh dashboard) → cards, charts, counts and
     alerts reflect the new reading. A new alert appears if the risk index crossed a threshold.
7. **Prediction module** → click **Prediction**.
   * “Model Status” states the mode (demo or user dataset), row count and metrics.
      In demo mode a badge says the model was trained on synthetic data.
   * Choose a location, leave the fields blank, tick “Use the latest stored reading”, press
     **Predict risk category** → predicted category, class probabilities, factor influences
     and an agreement check against the transparent index.
   * Enter unrealistic values (e.g. humidity 500) → validation error, no prediction.
   * Try with an external location blank + manual values to see an independent prediction.
8. **Error handling** → open `http://127.0.0.1:5000/unknown-page` → styled “Error 404” page.
9. **REST API quick checks** (optional, in PowerShell):

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health        | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:5000/api/summary       | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:5000/api/trends        | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:5000/api/model-info    | ConvertTo-Json -Depth 4

# submit a reading (Observed) and see the recalculated risk + any new alert
$body = @{ location_code="MZ-AIZ"; temperature=23.5; rainfall_24h=180; humidity=94; soil_moisture=82 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/readings -Body $body -ContentType "application/json" | ConvertTo-Json -Depth 6

# invalid reading -> HTTP 400 with field errors
$bad = @{ location_code="MZ-AIZ"; temperature=500; rainfall_24h=-5; humidity=140; soil_moisture=90 } | ConvertTo-Json
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/readings -Body $bad -ContentType "application/json" }
catch { $_.ErrorDetails.Message }

# prediction
$p = @{ location_code="ML-SOH"; use_latest=1 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/predict -Body $p -ContentType "application/json" | ConvertTo-Json -Depth 6
```

10. **Reset the sample data** → stop the server, delete `database/landslide.db`
    (and optionally `data/demo_model.pkl`), then start again.

---

## 6. REST API reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Service status, database path, model mode |
| GET | `/api/summary` | Averages, overall risk level, counts, peak-risk location |
| GET | `/api/locations` | All locations with coordinates, terrain factor and latest reading |
| GET | `/api/trends?hours=168` | Regional time series: rainfall, risk score, alerts, level counts |
| GET | `/api/readings?location_code=CODE&limit=48` | Historical readings for one location |
| GET | `/api/readings/recent?limit=25` | Newest readings across all locations |
| POST | `/api/readings` | Validate + store a reading, recalculate risk, maybe raise an alert |
| GET | `/api/alerts?limit=50&include_ack=1` | Alert log, unread counts, thresholds and actions |
| POST | `/api/alerts/<id>/ack` | Mark one alert as read |
| POST | `/api/alerts/ack-all` | Mark every unread alert as read |
| GET | `/api/model-info` | Model mode, provenance, runtime metrics, importances, index details |
| POST | `/api/predict` | Predicted risk category + class probabilities + factor influences |

Validation errors are returned as HTTP 400 with `{"ok": false, "errors": {"field": "message"}}`.

---

## 7. Configuration

**Alert thresholds** — edit `ALERT_THRESHOLDS` at the top of `app.py`:

```python
ALERT_THRESHOLDS = {"Advisory": 45.0, "Warning": 60.0, "Severe": 75.0}
```

**Risk index weights / bands / reference rainfall** — edit `WEIGHTS`, `RISK_BANDS`,
`R24_REF`, `R72_REF` in `model.py`.

**Monitoring locations** — add or edit entries in `data/locations.json`
(any number of locations; `susceptibility` is 0.55–1.00).

**Using a real labelled dataset instead of synthetic data** — place a CSV at
`data/dataset.csv` with these columns:

```
rainfall_24h, rainfall_72h, humidity, soil_moisture, temperature, susceptibility, risk_level
```

* at least 200 rows and at least 2 distinct `risk_level` values
  (`Low`, `Moderate`, `High`, `Very High`);
* delete `data/demo_model.pkl` afterwards and restart so the model retrains;
* the UI then switches from “Demonstration mode (synthetic)” to “Trained on a user-supplied
  labelled dataset”, and the Prediction page reports that provenance automatically.

**Integrating live data later (documented, not implemented)** — the intended integration
points are:

1. Add a small service module that fetches rainfall from IMD / open weather APIs and slope,
   geology and land-cover layers from Bhuvan/GSI WMS services, using an API key stored in an
   environment variable (never in the repository).
2. Insert those values through the same `readings` table with `data_source='observed'`.
3. Replace the demonstration index in `model.py` with a calibrated rainfall-threshold or
   logistic-regression model trained on a real landslide inventory (`dataset.csv`).
4. Mount the API key read as `os.environ["MY_API_KEY"]`; the current code deliberately reads
   no credentials at all.

Free data sources worth exploring: IMD rainfall data, GSI landslide susceptibility maps,
Bhuvan (ISRO) land use/slope layers, OpenStreetMap, SRTM/Copernicus DEM for slope,
and district landslide inventories published by State Disaster Management Authorities.

---

## 8. Scientific limitations (please read)

1. Landslide occurrence depends on **rainfall intensity and antecedent rainfall, slope angle,
   lithology and structure, soil depth and permeability, land cover, road cuts, drainage,
   seismic shaking and human activity**. Four sensor readings cannot represent all of that.
2. The risk index used here is a **simple weighted rule** (`model.py`), documented and
   transparent, but not calibrated against observed landslides.
3. The Random Forest learns to reproduce that rule from **synthetic data unless you supply a
   real labelled dataset**. Reported metrics therefore describe reproduction of the rule, not
   real predictive skill — that is why no accuracy figure is hard-coded anywhere in this project.
4. Alerts are **threshold crossings**, not probabilities of slope failure.
5. Terrain susceptibility values in `data/locations.json` are coarse indicative proxies for a
   prototype, not survey-grade geotechnical parameters.
6. **Do not use this application for evacuation, land-use or life-safety decisions.**

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `python` not found | Install Python 3.10+ from python.org (tick “Add Python to PATH”) or use `py -m venv .venv` |
| Charts are blank / map is grey | No internet: Chart.js, Leaflet and OSM tiles come from CDNs. Data and validation still work; a toast explains this. |
| `Address already in use` | Another server is on port 5000: change the port in `app.py` (`app.run(..., port=5001)`) |
| Model takes a few seconds on first run | Expected — the Random Forest trains once and is cached in `data/demo_model.pkl` |
| Want a clean database | Delete `database/landslide.db` and restart |
| `ModuleNotFoundError: No module named 'flask'` | The virtual environment is not active: run `.\.venv\Scripts\Activate.ps1` then `pip install -r requirements.txt` |
| `ImportError: DLL load failed ... An Application Control policy has blocked this file` | Windows Smart App Control / WDAC is blocking unsigned NumPy/pandas/scikit-learn binaries. Run once with the venv inactive: `Get-ChildItem .\.venv -Recurse -File -Include *.pyd,*.dll \| Unblock-File`, then retry (reputation may take one or two attempts). If it persists, turn Smart App Control **off** in *Windows Security → App & browser control → Smart App Control settings* and reboot. |

---

## 10. License / attribution

Prototype for academic and demonstration use. Map tiles © OpenStreetMap contributors;
map data and tiles are used under the OpenStreetMap license. Sample location coordinates
are approximate settlement centroids used only for prototype mapping.
