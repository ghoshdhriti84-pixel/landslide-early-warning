"""
model.py
========
Landslide risk scoring + machine-learning pipeline for the
"AI-Based Early Warning and Landslide Risk Monitoring System (NER India)" prototype.

IMPORTANT SCIENTIFIC LIMITATION (read before using any number from this file)
-----------------------------------------------------------------------------
Real landslide hazard depends on many coupled factors: rainfall intensity AND
antecedent rainfall history, slope angle, lithology/geology, structural
discontinuities, soil depth and permeability, land cover/deforestation, road-cut
slopes, seismic shaking and local drainage. A handful of sensor readings can NOT
reproduce that.

Therefore this file contains TWO clearly separated things:

1. `compute_risk_index()` - a TRANSPARENT, THRESHOLD-BASED DEMONSTRATION INDEX.
   It is a simple weighted rule (documented below). It is *not* a validated
   scientific model and must not be used for real evacuation decisions.

2. A scikit-learn Random Forest classifier (`train_random_forest`) that learns to
   reproduce that same demonstration index from data.
   * If a real labelled dataset is supplied at `data/dataset.csv` it trains on it.
   * Otherwise it trains on SYNTHETIC data generated from the demonstration index
     and reports `mode = "demo"`. Accuracy numbers in demo mode only describe how
     well the model reproduces our own synthetic rule - they are NOT real-world
     predictive accuracy and must never be presented as such.

No accuracy figure is invented anywhere in this project: every metric is computed
at runtime from the data actually used, and the data source is always reported.
"""

from __future__ import annotations

import os
import pickle
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Feature definition
# ---------------------------------------------------------------------------

FEATURES: List[str] = [
    "rainfall_24h",    # mm
    "rainfall_72h",    # mm  (3-day antecedent rainfall - a key real-world driver)
    "humidity",        # %
    "soil_moisture",   # %
    "temperature",     # degrees C
    "susceptibility",  # static terrain factor 0.55 - 1.00 (slope/geology proxy)
]

FEATURE_LABELS: Dict[str, str] = {
    "rainfall_24h": "Rainfall (last 24 h)",
    "rainfall_72h": "Rainfall (last 72 h)",
    "humidity": "Humidity",
    "soil_moisture": "Soil moisture",
    "temperature": "Temperature",
    "susceptibility": "Terrain susceptibility",
}

# Normalisation references used by the demonstration index.
# R24_REF / R72_REF: order-of-magnitude "heavy" monsoon rainfall totals for NER India.
R24_REF = 150.0   # mm in 24 h
R72_REF = 300.0   # mm in 72 h

# Weights of the demonstration index (must sum to 1.0). Rainfall dominates,
# as in most rainfall-triggered landslide literature.
WEIGHTS: Dict[str, float] = {
    "rainfall_24h": 0.34,
    "rainfall_72h": 0.24,
    "soil_moisture": 0.20,
    "humidity": 0.12,
    "temperature": 0.10,
}

# Risk bands (score 0-100 -> category)
RISK_BANDS: List[Tuple[str, float, float]] = [
    ("Low", 0.0, 30.0),
    ("Moderate", 30.0, 55.0),
    ("High", 55.0, 75.0),
    ("Very High", 75.0, 101.0),
]

RISK_CLASSES: List[str] = [b[0] for b in RISK_BANDS]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATASET_PATH = os.path.join(DATA_DIR, "dataset.csv")
MODEL_CACHE_PATH = os.path.join(DATA_DIR, "demo_model.pkl")


def band_for_score(score: float) -> str:
    """Map a 0-100 demonstration score onto a risk category."""
    for name, low, high in RISK_BANDS:
        if low <= score < high:
            return name
    return "Very High" if score >= 100 else "Low"


# ---------------------------------------------------------------------------
# 1. Transparent demonstration risk index
# ---------------------------------------------------------------------------

def _term(name: str, value: float) -> float:
    """Normalise one input to 0..1 using documented reference values."""
    value = float(value)
    if name == "rainfall_24h":
        return min(max(value, 0.0) / R24_REF, 1.0)
    if name == "rainfall_72h":
        return min(max(value, 0.0) / R72_REF, 1.0)
    if name == "soil_moisture":
        return min(max(value, 0.0), 100.0) / 100.0
    if name == "humidity":
        return min(max(value, 0.0), 100.0) / 100.0
    if name == "temperature":
        # Weak proxy only: cooler + wetter conditions increase the term.
        # 30 C -> 0.0, 5 C -> 1.0. This is a rough convention, not physics.
        return min(max((30.0 - value) / 25.0, 0.0), 1.0)
    return 0.0


def compute_risk_index(
    rainfall_24h: float,
    rainfall_72h: float,
    humidity: float,
    soil_moisture: float,
    temperature: float,
    susceptibility: float = 1.0,
) -> Dict[str, object]:
    """
    Compute the DEMONSTRATION risk index.

    score = 100 * susceptibility * SUM(weight_i * normalised_input_i)

    Returns a dict with the score, category and per-factor contributions
    (contribution_i = the percentage points that factor added to the score).
    """
    values = {
        "rainfall_24h": rainfall_24h,
        "rainfall_72h": rainfall_72h,
        "humidity": humidity,
        "soil_moisture": soil_moisture,
        "temperature": temperature,
    }
    susc = min(max(float(susceptibility), 0.0), 1.0)

    contributions: Dict[str, float] = {}
    raw = 0.0
    for name, weight in WEIGHTS.items():
        raw += weight * _term(name, values[name])
    # susceptibility acts as the terrain multiplier, reported as its own factor
    contributions = {
        name: round(100.0 * susc * weight * _term(name, values[name]), 2)
        for name, weight in WEIGHTS.items()
    }
    contributions["susceptibility"] = round(100.0 * (susc - 1.0) * raw, 2)

    score = max(0.0, min(100.0 * susc * raw, 100.0))
    return {
        "score": round(score, 2),
        "level": band_for_score(score),
        "contributions": contributions,
        "susceptibility": round(susc, 3),
    }


# ---------------------------------------------------------------------------
# 2. Synthetic demonstration dataset
# ---------------------------------------------------------------------------

def generate_synthetic_dataset(n_samples: int = 4000, seed: int = 42) -> pd.DataFrame:
    """
    Create a clearly-labelled SYNTHETIC dataset that mimics a NER-India monsoon
    regime, then label it with the demonstration index above (+ noise).

    These rows are simulated. They are not field measurements and must never be
    described as real observations.
    """
    rng = np.random.default_rng(seed)

    # Season mix: dry-season, wet-season and extreme-monsoon samples.
    season = rng.choice(["dry", "wet", "extreme"], size=n_samples, p=[0.35, 0.45, 0.20])
    rain_scale = np.where(season == "dry", 25.0, np.where(season == "wet", 110.0, 230.0))

    susceptibility = rng.uniform(0.55, 1.0, size=n_samples)
    rainfall_24h = np.clip(rng.gamma(2.0, rain_scale / 2.0, size=n_samples), 0.0, 600.0)
    rainfall_72h = np.clip(rainfall_24h * rng.uniform(1.2, 3.2, size=n_samples), 0.0, 1200.0)
    soil_moisture = np.clip(
        30.0 + 0.22 * rainfall_72h + rng.normal(0, 7, size=n_samples), 5.0, 100.0
    )
    humidity = np.clip(
        55.0 + 0.16 * rainfall_24h + 0.10 * soil_moisture + rng.normal(0, 6, size=n_samples),
        20.0, 100.0,
    )
    temperature = np.clip(
        np.where(season == "dry", 27.0, 22.0) - 0.03 * rainfall_24h + rng.normal(0, 3, size=n_samples),
        2.0, 40.0,
    )

    df = pd.DataFrame(
        {
            "rainfall_24h": rainfall_24h.round(1),
            "rainfall_72h": rainfall_72h.round(1),
            "humidity": humidity.round(1),
            "soil_moisture": soil_moisture.round(1),
            "temperature": temperature.round(1),
            "susceptibility": susceptibility.round(3),
        }
    )

    scores = np.array(
        [
            compute_risk_index(**row)["score"]
            for row in df.to_dict(orient="records")
        ]
    )
    # Label noise: sensors are imperfect and the rule is coarse.
    noisy = np.clip(scores + rng.normal(0, 4.0, size=n_samples), 0.0, 100.0)
    df["risk_score"] = scores.round(2)
    df["risk_level"] = [band_for_score(s) for s in noisy]
    return df


def load_dataset() -> Tuple[pd.DataFrame, str, str]:
    """
    Load training data. Returns (dataframe, mode, description).

    mode = "dataset"  -> a real CSV provided at data/dataset.csv was used
    mode = "demo"     -> synthetic data generated from the demonstration index
    """
    if os.path.exists(DATASET_PATH):
        try:
            df = pd.read_csv(DATASET_PATH)
            required = set(FEATURES + ["risk_level"])
            if required.issubset(df.columns) and len(df) >= 200:
                df = df.dropna(subset=FEATURES + ["risk_level"])
                df = df[df["risk_level"].isin(RISK_CLASSES)]
                present = [c for c in RISK_CLASSES if c in set(df["risk_level"])]
                if len(df) >= 200 and len(present) >= 2:
                    return (
                        df[FEATURES + ["risk_level"]],
                        "dataset",
                        f"User-supplied dataset ({DATASET_PATH}), {len(df)} labelled rows, "
                        f"classes present: {', '.join(present)}.",
                    )
        except Exception:  # corrupt / unreadable CSV -> fall back to demo mode
            pass

    df = generate_synthetic_dataset()
    return (
        df[FEATURES + ["risk_level"]],
        "demo",
        "SYNTHETIC demonstration data generated from the threshold-based "
        "index in model.py. Not real field measurements.",
    )


# ---------------------------------------------------------------------------
# 3. Machine-learning pipeline
# ---------------------------------------------------------------------------

def train_random_forest() -> Dict[str, object]:
    """
    Train a Random Forest classifier and return a bundle with honest,
    runtime-computed metrics and the provenance of the training data.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
    from sklearn.model_selection import cross_val_score, train_test_split

    df, mode, description = load_dataset()
    X = df[FEATURES].astype(float)
    y = df["risk_level"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_test, y_pred, average="macro")), 4),
        "test_rows": int(len(y_test)),
        "classes": list(clf.classes_),
        "confusion_matrix": confusion_matrix(y_test, y_pred, labels=list(clf.classes_)).tolist(),
    }
    try:
        cv = cross_val_score(clf, X, y, cv=3, scoring="accuracy")
        metrics["cv_accuracy_mean"] = round(float(cv.mean()), 4)
        metrics["cv_accuracy_std"] = round(float(cv.std()), 4)
        metrics["cv_folds"] = 3
    except Exception:
        metrics["cv_accuracy_mean"] = None
        metrics["cv_accuracy_std"] = None
        metrics["cv_folds"] = 0

    importances = {
        FEATURE_LABELS[f]: round(float(v), 4)
        for f, v in sorted(
            zip(FEATURES, clf.feature_importances_), key=lambda kv: kv[1], reverse=True
        )
    }
    stats = {
        f: {"mean": float(X[f].mean()), "std": float(X[f].std() or 1.0)} for f in FEATURES
    }

    return {
        "clf": clf,
        "mode": mode,
        "dataset_description": description,
        "metrics": metrics,
        "importances": importances,
        "feature_stats": stats,
        "trained_on_rows": int(len(df)),
        "features": FEATURES,
        "feature_labels": FEATURE_LABELS,
    }


_BUNDLE: Dict[str, object] | None = None


def get_model_bundle() -> Dict[str, object]:
    """Train once per process (and cache to disk) to keep requests fast."""
    global _BUNDLE
    if _BUNDLE is not None:
        return _BUNDLE

    if os.path.exists(MODEL_CACHE_PATH):
        try:
            with open(MODEL_CACHE_PATH, "rb") as fh:
                cached = pickle.load(fh)
            if cached.get("mode") == "demo" and cached.get("trained_on_rows") == 4000:
                _BUNDLE = cached
                return _BUNDLE
        except Exception:
            pass  # retrain below

    bundle = train_random_forest()
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(MODEL_CACHE_PATH, "wb") as fh:
            pickle.dump(bundle, fh)  # local, key-free artefact; safe to delete
    except Exception:
        pass
    _BUNDLE = bundle
    return _BUNDLE


def explain_prediction(features: Dict[str, float]) -> Tuple[str, Dict[str, float], Dict[str, float]]:
    """
    Predict a risk category from a feature dict and give an APPROXIMATE local
    explanation: feature importance x standardised deviation from the training
    mean, normalised to percentages. This is a simple heuristic explanation,
    not SHAP and not a causal analysis.
    """
    bundle = get_model_bundle()
    clf = bundle["clf"]
    stats = bundle["feature_stats"]
    importances = clf.feature_importances_

    row = pd.DataFrame([{f: float(features[f]) for f in FEATURES}])
    prediction = str(clf.predict(row)[0])
    proba = {
        cls: round(float(p), 4) for cls, p in zip(clf.classes_, clf.predict_proba(row)[0])
    }

    raw_scores = {}
    for idx, f in enumerate(FEATURES):
        z = abs(float(features[f]) - stats[f]["mean"]) / stats[f]["std"]
        raw_scores[FEATURE_LABELS[f]] = float(importances[idx]) * z
    total = sum(raw_scores.values()) or 1.0
    influences = {
        k: round(100.0 * v / total, 1)
        for k, v in sorted(raw_scores.items(), key=lambda kv: kv[1], reverse=True)
    }
    return prediction, proba, influences
