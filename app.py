"""
app.py
======
Flask backend for the prototype:
"AI-Based Early Warning and Landslide Risk Monitoring System in the
 North Eastern Region (NER) of India".

Run (Windows PowerShell):
    python -m venv .venv ; .\\.venv\\Scripts\\Activate.ps1
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000

SCOPE / HONESTY NOTES
---------------------
* Readings are SIMULATED by default (see `seed_database`) so the prototype runs
  without any sensors or API keys. Every simulated row is flagged in the
  `data_source` column and surfaced in the UI as "Simulated".
* Alerts come from a configurable threshold rule (ALERT_THRESHOLDS below) on a
  demonstration risk index - they are NOT scientific forecasts.
* The ML pipeline in model.py is a separate, clearly-labelled component. It never
  claims real-world accuracy, and its training data provenance is always shown.
* No secrets/API keys are stored or read. Data lives in a local SQLite file.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

import model as ml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DATABASE_DIR, "landslide.db")
LOCATIONS_PATH = os.path.join(DATA_DIR, "locations.json")

# --------------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------------

# Risk-score thresholds (0-100 demonstration index) that trigger an alert.
# Change these values to re-tune the prototype's early-warning behaviour.
ALERT_THRESHOLDS: Dict[str, float] = {
    "Advisory": 45.0,   # elevated - stay alert
    "Warning": 60.0,    # high - prepare to act
    "Severe": 75.0,     # very high - act now
}

# Recommended safety action shown with each alert level.
ALERT_ACTIONS: Dict[str, str] = {
    "Advisory": (
        "Stay alert. Avoid steep cut slopes, fresh road cuttings and gully beds "
        "during continued rainfall. Keep monitoring local weather updates."
    ),
    "Warning": (
        "Prepare to move. Shift to a safer, flatter location if rainfall continues; "
        "keep documents, medicines and a torch ready; avoid travel on hill roads "
        "and watch for new cracks, tilting trees or muddy springs."
    ),
    "Severe": (
        "Act now. Evacuate low-lying and steep-slope settlements, move to a "
        "pre-identified safe shelter, and follow instructions from the district "
        "administration / State Disaster Management Authority. Call 112 in an "
        "emergency."
    ),
}

ALERT_ORDER = ["Advisory", "Warning", "Severe"]

# Hours within which a duplicate alert (same location + same level) is suppressed.
ALERT_COOLDOWN_HOURS = 6

# Rolling window used for antecedent (multi-day) rainfall, in hours.
ANTECEDENT_WINDOW_HOURS = 72

SIMULATED = "simulated"
OBSERVED = "observed"

TIME_FMT = "%Y-%m-%d %H:%M:%S"


# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------

def now_str() -> str:
    return datetime.now().strftime(TIME_FMT)


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, TIME_FMT)


def load_locations() -> List[Dict[str, Any]]:
    with open(LOCATIONS_PATH, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["locations"]


def get_conn() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def query(sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
    return get_conn().execute(sql, params).fetchall()


def query_one(sql: str, params: Tuple = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, params).fetchone()


def execute(sql: str, params: Tuple = ()) -> int:
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


# --------------------------------------------------------------------------
# Schema + seeding
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    state           TEXT NOT NULL,
    lat             REAL NOT NULL,
    lng             REAL NOT NULL,
    susceptibility  REAL NOT NULL,
    slope_deg       REAL,
    terrain_note    TEXT
);

CREATE TABLE IF NOT EXISTS readings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    location_code TEXT NOT NULL REFERENCES locations(code),
    temperature   REAL,
    rainfall_24h  REAL,
    rainfall_72h  REAL,
    humidity      REAL,
    soil_moisture REAL,
    risk_score    REAL,
    risk_level    TEXT,
    data_source   TEXT NOT NULL DEFAULT 'simulated',
    recorded_at   TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    location_code TEXT NOT NULL REFERENCES locations(code),
    reading_id    INTEGER REFERENCES readings(id),
    alert_level   TEXT NOT NULL,
    risk_score    REAL,
    message       TEXT NOT NULL,
    action        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    acknowledged  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_readings_loc_time ON readings(location_code, recorded_at);
CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(created_at);
"""

SEED_INTERVAL_HOURS = 6
SEED_DAYS = 7


def init_db() -> None:
    os.makedirs(DATABASE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _climate_profile(loc: Dict[str, Any], hour_of_day: int, rng: random.Random) -> Dict[str, float]:
    """Very simple simulated monsoon regime per location (NOT observational data)."""
    base_rain = 4.0 + 16.0 * loc["susceptibility"]          # heavier in steep/wet zones
    diurnal = 1.0 + 0.8 * max(0.0, -1 * abs(hour_of_day - 16) / 8.0 + 1.0)
    # wet spell / dry spell alternation to create realistic looking trends
    wet_spell = rng.random() < 0.35
    rainfall = max(0.0, rng.gauss(base_rain * diurnal * (2.4 if wet_spell else 0.5), 5.0))
    temperature = rng.gauss(26.5 - 0.05 * loc["lat"] + 3.5 * (1 if 10 <= hour_of_day <= 16 else -1), 1.6)
    humidity = min(99.0, max(45.0, rng.gauss(72 + 0.25 * rainfall, 6.0)))
    soil = min(100.0, max(
        12.0,
        35.0 + 0.55 * rainfall + 0.35 * humidity - 0.35 * (temperature - 20.0) + rng.gauss(0, 3.0),
    ))
    return {
        "temperature": round(temperature, 1),
        "rainfall_24h": round(rainfall, 1),
        "humidity": round(humidity, 1),
        "soil_moisture": round(soil, 1),
    }


def seed_database() -> None:
    """
    Populate a fresh database with the monitored locations and 7 days of
    SIMULATED readings so every page and chart works with no sensors attached.
    """
    conn = get_conn()
    existing = conn.execute("SELECT COUNT(*) AS c FROM readings").fetchone()["c"]
    if existing:
        return

    locations = load_locations()
    for loc in locations:
        conn.execute(
            "INSERT OR REPLACE INTO locations "
            "(code, name, state, lat, lng, susceptibility, slope_deg, terrain_note) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                loc["code"], loc["name"], loc["state"], loc["lat"], loc["lng"],
                loc["susceptibility"], loc.get("slope_deg"), loc.get("terrain_note"),
            ),
        )
    conn.commit()

    rng = random.Random(2026)
    start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=SEED_DAYS)
    steps = int(SEED_DAYS * 24 / SEED_INTERVAL_HOURS)

    for loc in locations:
        history: List[Tuple[datetime, float]] = []
        for step in range(steps + 1):
            ts = start + timedelta(hours=step * SEED_INTERVAL_HOURS)
            profile = _climate_profile(loc, ts.hour, rng)
            history.append((ts, profile["rainfall_24h"]))
            window_start = ts - timedelta(hours=ANTECEDENT_WINDOW_HOURS)
            rain_72h = sum(r for t, r in history if t >= window_start)

            risk = ml.compute_risk_index(
                rainfall_24h=profile["rainfall_24h"],
                rainfall_72h=rain_72h,
                humidity=profile["humidity"],
                soil_moisture=profile["soil_moisture"],
                temperature=profile["temperature"],
                susceptibility=loc["susceptibility"],
            )
            cur = conn.execute(
                "INSERT INTO readings (location_code, temperature, rainfall_24h, rainfall_72h, "
                "humidity, soil_moisture, risk_score, risk_level, data_source, recorded_at, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    loc["code"], profile["temperature"], profile["rainfall_24h"],
                    round(rain_72h, 1), profile["humidity"], profile["soil_moisture"],
                    risk["score"], risk["level"], SIMULATED,
                    ts.strftime(TIME_FMT), now_str(),
                ),
            )
            # Only create alerts for the most recent simulated day, so the
            # notification panel is not flooded with a week of old alerts.
            if step >= steps - 4:
                _maybe_create_alert(conn, loc, cur.lastrowid, risk, ts.strftime(TIME_FMT))
    conn.commit()


def _alert_level_for_score(score: float) -> str | None:
    """Highest matching threshold; None when the score is below all thresholds."""
    level = None
    for name in ALERT_ORDER:
        if score >= ALERT_THRESHOLDS[name]:
            level = name
    return level


def _maybe_create_alert(
    conn: sqlite3.Connection,
    loc: Dict[str, Any],
    reading_id: int,
    risk: Dict[str, Any],
    timestamp: str,
) -> int | None:
    """Create an alert when a threshold is crossed, with a dedupe cooldown."""
    level = _alert_level_for_score(float(risk["score"]))
    if level is None:
        return None

    since = (parse_time(timestamp) - timedelta(hours=ALERT_COOLDOWN_HOURS)).strftime(TIME_FMT)
    dup = conn.execute(
        "SELECT id FROM alerts WHERE location_code=? AND alert_level=? AND created_at>=?",
        (loc["code"], level, since),
    ).fetchone()
    if dup:
        return None

    message = (
        f"{loc['name']}, {loc['state']}: demonstration risk score "
        f"{risk['score']} / 100 ({risk['level']}) crossed the '{level}' threshold "
        f"of {ALERT_THRESHOLDS[level]:.0f}."
    )
    return conn.execute(
        "INSERT INTO alerts (location_code, reading_id, alert_level, risk_score, message, "
        "action, created_at, acknowledged) VALUES (?,?,?,?,?,?,?,0)",
        (loc["code"], reading_id, level, risk["score"], message, ALERT_ACTIONS[level], timestamp),
    ).lastrowid


# --------------------------------------------------------------------------
# Domain helpers
# --------------------------------------------------------------------------

def location_map() -> Dict[str, Dict[str, Any]]:
    return {loc["code"]: loc for loc in load_locations()}


def latest_reading_for(code: str) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM readings WHERE location_code=? ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (code,),
    )


def antecedent_rainfall(code: str, since: datetime, exclude_last: bool = False) -> Tuple[float, bool]:
    """
    Sum stored rainfall over the antecedent window for a location.
    Returns (sum_mm, has_full_history). Sparse history is reported, never invented.
    """
    rows = query(
        "SELECT rainfall_24h, recorded_at FROM readings WHERE location_code=? AND recorded_at>=? "
        "ORDER BY recorded_at ASC",
        (code, since.strftime(TIME_FMT)),
    )
    if exclude_last and rows:
        rows = rows[:-1]
    total = sum(float(r["rainfall_24h"] or 0.0) for r in rows)
    has_full = len(rows) >= 2
    return round(total, 1), has_full


def reading_to_dict(row: sqlite3.Row, loc: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = {
        "id": row["id"],
        "location_code": row["location_code"],
        "temperature": row["temperature"],
        "rainfall_24h": row["rainfall_24h"],
        "rainfall_72h": row["rainfall_72h"],
        "humidity": row["humidity"],
        "soil_moisture": row["soil_moisture"],
        "risk_score": row["risk_score"],
        "risk_level": row["risk_level"],
        "data_source": row["data_source"],
        "recorded_at": row["recorded_at"],
    }
    if loc:
        data["location"] = {
            "code": loc["code"], "name": loc["name"], "state": loc["state"],
            "lat": loc["lat"], "lng": loc["lng"],
            "susceptibility": loc["susceptibility"], "slope_deg": loc.get("slope_deg"),
            "terrain_note": loc.get("terrain_note"),
        }
    return data


def overall_level(scores: List[float]) -> str:
    """
    Regional indicator = mean of the latest per-location scores, banded.
    The peak location is reported separately in the API response.
    """
    if not scores:
        return "No data"
    return ml.band_for_score(sum(scores) / len(scores))


def validate_reading(payload: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, str]]:
    """
    Validate a submitted reading. Returns (clean_values, errors).
    Bounds are deliberately wide but reject physically impossible input.
    """
    errors: Dict[str, str] = {}
    rules = {
        "temperature": (-20.0, 55.0, "Temperature must be between -20 and 55 deg C."),
        "rainfall_24h": (0.0, 1000.0, "Rainfall must be between 0 and 1000 mm."),
        "humidity": (0.0, 100.0, "Humidity must be between 0 and 100 %."),
        "soil_moisture": (0.0, 100.0, "Soil moisture must be between 0 and 100 %."),
    }
    clean: Dict[str, float] = {}
    for field, (low, high, message) in rules.items():
        raw = payload.get(field)
        if raw is None or raw == "":
            errors[field] = f"{ml.FEATURE_LABELS.get(field, field)} is required."
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors[field] = f"{ml.FEATURE_LABELS.get(field, field)} must be a number."
            continue
        if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
            errors[field] = f"{ml.FEATURE_LABELS.get(field, field)} must be a finite number."
            continue
        if not (low <= value <= high):
            errors[field] = message
            continue
        clean[field] = round(value, 2)

    code = (payload.get("location_code") or "").strip()
    if not code:
        errors["location_code"] = "Please choose a monitoring location."
    elif code not in location_map():
        errors["location_code"] = "Unknown monitoring location."
    return clean, errors


# --------------------------------------------------------------------------
# Flask application
# --------------------------------------------------------------------------

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


@app.teardown_appcontext
def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.after_request
def add_headers(response):
    """Allow the prototype to be opened from any local page and stay cache-free."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ---------------------------- Page routes --------------------------------

@app.route("/")
def page_dashboard():
    return render_template("dashboard.html", active="dashboard")


@app.route("/map")
def page_map():
    return render_template("map.html", active="map")


@app.route("/alerts")
def page_alerts():
    return render_template("alerts.html", active="alerts")


@app.route("/monitoring")
def page_monitoring():
    return render_template("monitoring.html", active="monitoring")


@app.route("/prediction")
def page_prediction():
    return render_template("prediction.html", active="prediction")


# ---------------------------- API routes ---------------------------------

@app.get("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "time": now_str(),
        "database": DB_PATH,
        "mode": ml.get_model_bundle()["mode"],
    })


@app.get("/api/summary")
def api_summary():
    locations = load_locations()
    latests = []
    for loc in locations:
        row = latest_reading_for(loc["code"])
        if row is not None:
            latests.append((loc, row))

    if latests:
        scores = [float(r["risk_score"]) for _, r in latests]
        temps = [float(r["temperature"]) for _, r in latests if r["temperature"] is not None]
        rain = [float(r["rainfall_24h"]) for _, r in latests if r["rainfall_24h"] is not None]
        hum = [float(r["humidity"]) for _, r in latests if r["humidity"] is not None]
        soil = [float(r["soil_moisture"]) for _, r in latests if r["soil_moisture"] is not None]
        level = overall_level(scores)
        peak_loc, peak_row = max(latests, key=lambda item: float(item[1]["risk_score"]))
        peak = {
            "name": peak_loc["name"], "state": peak_loc["state"],
            "risk_score": peak_row["risk_score"], "risk_level": peak_row["risk_level"],
        }
    else:
        scores, temps, rain, hum, soil = [], [], [], [], []
        level, peak = "No data", None

    active_alerts = query_one(
        "SELECT COUNT(*) AS c FROM alerts WHERE acknowledged=0"
    )["c"]

    counts = {name: 0 for name in ml.RISK_CLASSES}
    for _, row in latests:
        counts[row["risk_level"]] = counts.get(row["risk_level"], 0) + 1

    def avg(values):
        return round(sum(values) / len(values), 1) if values else None

    return jsonify({
        "project_title": "AI-Based Early Warning and Landslide Risk Monitoring System - NER India",
        "monitored_locations": len(locations),
        "locations_reporting": len(latests),
        "active_alerts": active_alerts,
        "overall_risk_level": level,
        "risk_distribution": counts,
        "current": {
            "temperature": avg(temps),
            "rainfall_24h": avg(rain),
            "humidity": avg(hum),
            "soil_moisture": avg(soil),
            "risk_score": avg(scores),
        },
        "highest_risk_location": peak,
        "data_mode": "simulated" if any(r["data_source"] == SIMULATED for _, r in latests) else "observed",
        "last_update": max((r["recorded_at"] for _, r in latests), default=None),
        "disclaimer": (
            "Prototype using simulated/sample data. Demonstration alerts are generated from a "
            "configurable threshold rule, not from a validated forecast. This is NOT an official "
            "emergency-warning service."
        ),
    })


@app.get("/api/locations")
def api_locations():
    lmap = location_map()
    out = []
    for loc in load_locations():
        row = latest_reading_for(loc["code"])
        item = {
            "code": loc["code"], "name": loc["name"], "state": loc["state"],
            "lat": loc["lat"], "lng": loc["lng"],
            "susceptibility": loc["susceptibility"],
            "slope_deg": loc.get("slope_deg"),
            "terrain_note": loc.get("terrain_note"),
            "reading": None,
        }
        if row is not None:
            item["reading"] = {
                "temperature": row["temperature"],
                "rainfall_24h": row["rainfall_24h"],
                "rainfall_72h": row["rainfall_72h"],
                "humidity": row["humidity"],
                "soil_moisture": row["soil_moisture"],
                "risk_score": row["risk_score"],
                "risk_level": row["risk_level"],
                "data_source": row["data_source"],
                "recorded_at": row["recorded_at"],
            }
        out.append(item)
    return jsonify({"locations": out, "count": len(out), "disclaimer": lmap and
                    "Coordinates are approximate and used for prototype mapping only."})


@app.get("/api/trends")
def api_trends():
    """Regional trend series for the dashboard charts (default: last 7 days)."""
    try:
        hours = min(max(int(request.args.get("hours", 168)), 12), 24 * 30)
    except ValueError:
        hours = 168

    since = (datetime.now() - timedelta(hours=hours)).strftime(TIME_FMT)
    rows = query(
        "SELECT date(recorded_at) AS day, AVG(rainfall_24h) AS rain, AVG(risk_score) AS risk, "
        "AVG(temperature) AS temp, AVG(humidity) AS hum, AVG(soil_moisture) AS soil, "
        "COUNT(*) AS samples "
        "FROM readings WHERE recorded_at>=? GROUP BY day ORDER BY day ASC",
        (since,),
    )
    series = {
        "labels": [r["day"] for r in rows],
        "rainfall": [round(r["rain"] or 0, 1) for r in rows],
        "risk_score": [round(r["risk"] or 0, 2) for r in rows],
        "temperature": [round(r["temp"] or 0, 1) for r in rows],
        "humidity": [round(r["hum"] or 0, 1) for r in rows],
        "soil_moisture": [round(r["soil"] or 0, 1) for r in rows],
        "samples": [r["samples"] for r in rows],
    }

    level_rows = query(
        "SELECT date(recorded_at) AS day, risk_level, COUNT(*) AS c FROM readings "
        "WHERE recorded_at>=? GROUP BY day, risk_level ORDER BY day ASC",
        (since,),
    )
    level_counts = {name: [0] * len(rows) for name in ml.RISK_CLASSES}
    day_index = {r["day"]: i for i, r in enumerate(rows)}
    for r in level_rows:
        idx = day_index.get(r["day"])
        if idx is not None:
            level_counts[r["risk_level"]][idx] = r["c"]

    alert_rows = query(
        "SELECT date(created_at) AS day, COUNT(*) AS c FROM alerts WHERE created_at>=? "
        "GROUP BY day ORDER BY day ASC",
        (since,),
    )
    alert_counts = {r["day"]: r["c"] for r in alert_rows}
    series["alerts"] = [alert_counts.get(d, 0) for d in series["labels"]]
    series["level_counts"] = level_counts
    series["data_note"] = "Computed from stored readings (simulated unless submitted as observed)."
    return jsonify(series)


@app.get("/api/readings")
def api_readings():
    code = request.args.get("location_code", "").strip()
    try:
        limit = min(max(int(request.args.get("limit", 48)), 1), 1000)
    except ValueError:
        limit = 48
    if not code or code not in location_map():
        return jsonify({"errors": {"location_code": "Unknown monitoring location."}}), 400
    rows = query(
        "SELECT * FROM readings WHERE location_code=? ORDER BY recorded_at DESC, id DESC LIMIT ?",
        (code, limit),
    )
    loc = location_map()[code]
    return jsonify({
        "location": {"code": loc["code"], "name": loc["name"], "state": loc["state"]},
        "readings": [reading_to_dict(r) for r in rows],
        "data_source": rows[0]["data_source"] if rows else "none",
    })


@app.get("/api/readings/recent")
def api_recent_readings():
    """Most recent readings across all locations (for the monitoring page table)."""
    try:
        limit = min(max(int(request.args.get("limit", 25)), 1), 200)
    except ValueError:
        limit = 25
    rows = query(
        "SELECT * FROM readings ORDER BY recorded_at DESC, id DESC LIMIT ?", (limit,)
    )
    lmap = location_map()
    out = []
    for row in rows:
        item = reading_to_dict(row)
        loc = lmap.get(row["location_code"], {})
        item["location_name"] = loc.get("name", row["location_code"])
        item["state"] = loc.get("state")
        out.append(item)
    return jsonify({"readings": out, "count": len(out)})


@app.post("/api/readings")
def api_create_reading():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    clean, errors = validate_reading(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    code = payload["location_code"]
    loc = location_map()[code]

    rain_72h, full_history = antecedent_rainfall(
        code, datetime.now() - timedelta(hours=ANTECEDENT_WINDOW_HOURS), exclude_last=True
    )
    rain_72h = round(rain_72h + clean["rainfall_24h"], 1)

    risk = ml.compute_risk_index(
        rainfall_24h=clean["rainfall_24h"],
        rainfall_72h=rain_72h,
        humidity=clean["humidity"],
        soil_moisture=clean["soil_moisture"],
        temperature=clean["temperature"],
        susceptibility=loc["susceptibility"],
    )

    recorded_at = payload.get("recorded_at") or now_str()
    conn = get_conn()
    reading_id = conn.execute(
        "INSERT INTO readings (location_code, temperature, rainfall_24h, rainfall_72h, humidity, "
        "soil_moisture, risk_score, risk_level, data_source, recorded_at, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            code, clean["temperature"], clean["rainfall_24h"], rain_72h,
            clean["humidity"], clean["soil_moisture"], risk["score"], risk["level"],
            OBSERVED, recorded_at, now_str(),
        ),
    ).lastrowid
    conn.commit()

    alert_id = _maybe_create_alert(conn, loc, reading_id, risk, recorded_at)
    conn.commit()

    new_alert = None
    if alert_id:
        row = query_one("SELECT * FROM alerts WHERE id=?", (alert_id,))
        new_alert = alert_to_dict(row)

    return jsonify({
        "ok": True,
        "reading": {
            "id": reading_id, "location_code": code, "location_name": loc["name"],
            "temperature": clean["temperature"], "rainfall_24h": clean["rainfall_24h"],
            "rainfall_72h": rain_72h, "humidity": clean["humidity"],
            "soil_moisture": clean["soil_moisture"], "risk_score": risk["score"],
            "risk_level": risk["level"], "data_source": OBSERVED, "recorded_at": recorded_at,
        },
        "risk_explanation": {
            "method": "Transparent threshold-based demonstration index (not a validated model).",
            "contributions": risk["contributions"],
            "susceptibility": risk["susceptibility"],
            "rainfall_72h_note": (
                f"Antecedent 3-day rainfall = {rain_72h} mm, summed from stored readings."
                + ("" if full_history else " Sparse history: only the available readings were used.")
            ),
        },
        "alert": new_alert,
    }), 201


def alert_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    loc = location_map().get(row["location_code"], {})
    return {
        "id": row["id"],
        "location_code": row["location_code"],
        "location_name": loc.get("name", row["location_code"]),
        "state": loc.get("state"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "alert_level": row["alert_level"],
        "risk_score": row["risk_score"],
        "message": row["message"],
        "action": row["action"],
        "created_at": row["created_at"],
        "acknowledged": bool(row["acknowledged"]),
    }


@app.get("/api/alerts")
def api_alerts():
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 500)
    except ValueError:
        limit = 50
    include_ack = request.args.get("include_ack", "1") != "0"
    sql = "SELECT * FROM alerts"
    params: Tuple = ()
    if not include_ack:
        sql += " WHERE acknowledged=0"
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params = (limit,) if not params else params + (limit,)
    rows = query(sql, params)
    counts = {
        r["alert_level"]: r["c"]
        for r in query("SELECT alert_level, COUNT(*) AS c FROM alerts WHERE acknowledged=0 GROUP BY alert_level")
    }
    return jsonify({
        "alerts": [alert_to_dict(r) for r in rows],
        "unacknowledged_by_level": counts,
        "total_unacknowledged": sum(counts.values()),
        "thresholds": ALERT_THRESHOLDS,
        "actions": ALERT_ACTIONS,
        "notice": (
            "Demonstration alerts from a configurable threshold rule. This prototype is NOT an "
            "official emergency-warning service; always follow government advisories."
        ),
    })


@app.post("/api/alerts/<int:alert_id>/ack")
def api_ack_alert(alert_id: int):
    row = query_one("SELECT * FROM alerts WHERE id=?", (alert_id,))
    if row is None:
        return jsonify({"ok": False, "error": "Alert not found."}), 404
    execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))
    return jsonify({"ok": True, "id": alert_id, "acknowledged": True})


@app.post("/api/alerts/ack-all")
def api_ack_all():
    conn = get_conn()
    cur = conn.execute("UPDATE alerts SET acknowledged=1 WHERE acknowledged=0")
    conn.commit()
    return jsonify({"ok": True, "acknowledged_count": cur.rowcount})


@app.get("/api/model-info")
def api_model_info():
    bundle = ml.get_model_bundle()
    mode = bundle["mode"]
    return jsonify({
        "mode": mode,
        "mode_label": ("Demonstration mode - trained on SYNTHETIC data"
                       if mode == "demo" else "Trained on a user-supplied labelled dataset"),
        "dataset_description": bundle["dataset_description"],
        "trained_on_rows": bundle["trained_on_rows"],
        "metrics": bundle["metrics"],
        "metrics_note": (
            "Metrics are computed at runtime by this project on the data actually used. "
            + ("They measure how well the model reproduces our own synthetic threshold rule - "
               "they are NOT real-world predictive accuracy."
               if mode == "demo" else
               "They describe this specific dataset only and may not transfer to other regions.")
        ),
        "feature_importances": bundle["importances"],
        "algorithm": "RandomForestClassifier (scikit-learn), 200 trees, max_depth=12",
        "index_details": {
            "weights": ml.WEIGHTS,
            "reference_values": {"rainfall_24h_mm": ml.R24_REF, "rainfall_72h_mm": ml.R72_REF},
            "risk_bands": [{"level": n, "min": lo, "max": hi} for n, lo, hi in ml.RISK_BANDS],
            "alert_thresholds": ALERT_THRESHOLDS,
        },
        "limitations": [
            "Landslide occurrence depends on slope angle, geology, structure, soil depth, "
            "land cover, road cuts, drainage and antecedent rainfall - not only the sensors used here.",
            "The demonstration index is a simple weighted rule, not a calibrated or validated model.",
            "No ground-truth landslide inventory has been used unless you supply data/dataset.csv.",
            "Alerts are threshold crossings, not forecast probabilities of failure.",
        ],
    })


@app.post("/api/predict")
def api_predict():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    code = (payload.get("location_code") or "").strip()

    lmap = location_map()
    if code and code not in lmap:
        return jsonify({"ok": False, "errors": {"location_code": "Unknown monitoring location."}}), 400

    # Optionally reuse the latest stored reading for the chosen location.
    use_latest = str(payload.get("use_latest", "1")) not in ("0", "false", "False", "")

    raw_features = {
        "rainfall_24h": payload.get("rainfall_24h"),
        "rainfall_72h": payload.get("rainfall_72h"),
        "humidity": payload.get("humidity"),
        "soil_moisture": payload.get("soil_moisture"),
        "temperature": payload.get("temperature"),
    }
    errors: Dict[str, str] = {}
    features: Dict[str, float] = {}
    for field, value in raw_features.items():
        if value is None or value == "":
            errors[field] = f"{ml.FEATURE_LABELS[field]} is required for a prediction."
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            errors[field] = f"{ml.FEATURE_LABELS[field]} must be a number."
            continue
        if num != num or num in (float("inf"), float("-inf")):
            errors[field] = f"{ml.FEATURE_LABELS[field]} must be a finite number."
            continue
        features[field] = num

    # Fill any missing field from the location's latest stored reading.
    latest_row = latest_reading_for(code) if (code and use_latest) else None
    if latest_row is not None:
        for field in list(errors.keys()):
            if latest_row[field] is not None:
                features[field] = float(latest_row[field])
                errors.pop(field, None)

    if code:
        terrain = float(lmap[code]["susceptibility"])
    else:
        try:
            terrain = float(payload.get("susceptibility") or 0.85)
        except (TypeError, ValueError):
            terrain = 0.85
    features["susceptibility"] = min(max(terrain, 0.55), 1.0)

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    risk = ml.compute_risk_index(**features)
    prediction, probabilities, influences = ml.explain_prediction(features)
    bundle = ml.get_model_bundle()
    mode = bundle["mode"]

    top_factors = list(influences.items())[:3]
    explanation = (
        f"The classifier predicts '{prediction}'. Its strongest inputs for this reading were "
        + ", ".join(f"{name} ({pct}% of approximate influence)" for name, pct in top_factors)
        + ". These influence values are a simple importance-weighted deviation heuristic, not a "
          "causal attribution."
    )

    return jsonify({
        "ok": True,
        "mode": mode,
        "mode_notice": (
            "DEMONSTRATION MODE: this model was trained on synthetic data generated by this "
            "project. Its output is not a real-world landslide prediction."
            if mode == "demo" else
            "Model trained on the user-supplied dataset. Treat results as indicative only."
        ),
        "inputs": {k: round(v, 2) for k, v in features.items()},
        "location_code": code or None,
        "predicted_category": prediction,
        "class_probabilities": probabilities,
        "heuristic_index": {"score": risk["score"], "level": risk["level"],
                            "contributions": risk["contributions"]},
        "agreement": prediction == risk["level"],
        "influences": influences,
        "influences_note": (
            "Approximate influence = Random-Forest feature importance x standardised distance "
            "from the training mean, normalised to 100%. Illustrative only."
        ),
        "explanation": explanation,
        "model_metrics": bundle["metrics"],
        "metrics_note": bundle["dataset_description"],
    }), 200


# ------------------------- Error handlers ---------------------------------

@app.errorhandler(HTTPException)
def handle_http_error(err: HTTPException):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": err.description, "status": err.code}), err.code
    return render_template("error.html", code=err.code, message=err.description), err.code


@app.errorhandler(Exception)
def handle_unexpected_error(err: Exception):
    app.logger.exception("Unhandled error: %s", err)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Internal server error."}), 500
    return render_template(
        "error.html", code=500, message="Something went wrong while processing the request."
    ), 500


# --------------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------------

def bootstrap() -> None:
    init_db()
    with app.app_context():
        seed_database()
    ml.get_model_bundle()  # train/cache the demo model up front


if __name__ == "__main__":
    bootstrap()
    # Local development only: no API keys, no external services.
    app.run(host="127.0.0.1", port=5000, debug=True)
