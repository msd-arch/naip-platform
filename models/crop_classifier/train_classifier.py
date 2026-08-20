#!/usr/bin/env python3
"""
train_classifier.py -- train + validate a scikit-learn classifier on real
Sentinel-2 NDVI monthly-composite features (features_labels.csv, produced by
extract_features.py) against real ESA WorldCereal irrigation labels.

Honest scope note: this is NOT the wheat/cotton/rice/sugarcane classifier
architecture.md 6.3 describes -- no public dataset has those classes for
Pakistan (see extract_features.py docstring). This trains/validates a single
real binary task: irrigated vs. not, using WorldCereal's irrigation product
as ground truth. The cropland task was dropped -- all 120 farms are labeled
'cropland' by WorldCereal (they're farm polygons by construction), so there
is no negative class to validate a cropland classifier against; reporting an
accuracy number for it would be a meaningless 100%-majority-class artifact,
not a real result.

Usage:
    python train_classifier.py --features features_labels.csv --out report.json
"""
import argparse
import csv
import json

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_binary_irrigated(v):
    # WorldCereal mode-reducer output for a 0/100 categorical band lands on
    # 0, 100, or float noise very close to 100 (99.9999999999...) from
    # floating-point reduction -- round rather than treat as a third class.
    return 1 if round(float(v)) == 100 else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="features_labels.csv")
    ap.add_argument("--out", default="report.json")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    rows = load_rows(a.features)
    month_cols = [c for c in rows[0].keys() if c.startswith("2025-")]

    X, y, farm_ids, dropped = [], [], [], []
    for r in rows:
        vals = [r[m] for m in month_cols]
        if any(v == "" or v is None for v in vals):
            dropped.append(r["farm_id"])
            continue
        X.append([float(v) for v in vals])
        y.append(to_binary_irrigated(r["worldcereal_irrigated"]))
        farm_ids.append(r["farm_id"])
    X = np.array(X)
    y = np.array(y)

    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    print(f"n samples: {len(y)} (dropped {len(dropped)} with missing NDVI months: {dropped})")
    print(f"class balance: irrigated={n_pos}, not_irrigated={n_neg}")

    # held-out validation split -- real accuracy, not a training-set number
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=a.seed, stratify=y
    )
    print(f"train n={len(y_train)}, test n={len(y_test)} (stratified 75/25 split)")

    models = {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=4,
                                                  class_weight="balanced", random_state=a.seed),
    }

    results = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        prec, rec, f1, _ = precision_recall_fscore_support(
            y_test, y_pred, average="binary", zero_division=0
        )
        cm = confusion_matrix(y_test, y_pred, labels=[0, 1]).tolist()

        # 5-fold CV on the full 120-farm set (small-n: single held-out split
        # alone is noisy at this sample size, report both honestly)
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=a.seed)
        cv_scores = cross_val_score(model, X, y, cv=skf, scoring="accuracy")

        results[name] = {
            "held_out_test_accuracy": round(float(acc), 3),
            "held_out_test_precision_irrigated": round(float(prec), 3),
            "held_out_test_recall_irrigated": round(float(rec), 3),
            "held_out_test_f1_irrigated": round(float(f1), 3),
            "held_out_confusion_matrix_rows_actual_cols_pred": cm,
            "cv_5fold_accuracy_mean": round(float(cv_scores.mean()), 3),
            "cv_5fold_accuracy_std": round(float(cv_scores.std()), 3),
            "cv_5fold_scores": [round(float(s), 3) for s in cv_scores],
        }
        print(f"{name}: held-out test acc={acc:.3f}, 5-fold CV acc={cv_scores.mean():.3f} "
              f"(+/-{cv_scores.std():.3f})")

    majority_baseline = max(n_pos, n_neg) / len(y)

    out = {
        "task": "irrigated vs. not-irrigated (binary) -- NOT the 4-crop-type classifier",
        "scope_note": (
            "architecture.md 6.3 specifies a wheat/cotton/rice/sugarcane classifier. "
            "No public crop-type dataset (checked: ESA WorldCereal) has those classes "
            "for Pakistan -- confirmed against the real GEE catalog, not assumed. This "
            "report covers the one real, non-degenerate binary task available: WorldCereal "
            "irrigation status, predicted from real Sentinel-2 NDVI monthly composites. "
            "The 'cropland' task was dropped -- all 120 farms are WorldCereal-labeled "
            "cropland (zero variance, nothing to validate)."
        ),
        "n_farms_total": len(rows),
        "n_farms_used": len(y),
        "n_farms_dropped_missing_data": len(dropped),
        "class_balance": {"irrigated": n_pos, "not_irrigated": n_neg},
        "majority_class_baseline_accuracy": round(float(majority_baseline), 3),
        "features": f"Sentinel-2 SR Harmonized, cloud-masked (SCL), monthly median NDVI, "
                     f"{month_cols[0]}..{month_cols[-1]}, per-farm mean (reduceRegions, scale=10m)",
        "labels": "ESA WorldCereal 2021 v100 'irrigation' product, per-farm mode (reduceRegions, scale=10m)",
        "train_test_split": "stratified 75/25 held-out, seed=" + str(a.seed),
        "models": results,
    }

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"\nmajority-class baseline (always predict '{'irrigated' if n_pos > n_neg else 'not_irrigated'}'): "
          f"{majority_baseline:.3f}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
