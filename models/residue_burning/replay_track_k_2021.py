#!/usr/bin/env python3
"""
replay_track_k_2021.py -- Track K: replay the EXISTING trained thermal-only fire
classifier (gbt_fire_classifier_thermal_only.joblib, trained on Nov 2023 data only)
against the real 2021 grid dataset. No retraining -- this is a validation check of
whether Track E's original result generalizes to a second real burning-season year
the model has never seen. Also replays the unchanged rule-based det_residue_burning()
logic on the same real 2021 full grid, for the same direct comparison the original
Track E report used.
"""
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_2021 = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2021", "grid_dataset.parquet")
DATA_2023 = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2023", "grid_dataset.parquet")
MODEL_PATH = os.path.join(HERE, "gbt_fire_classifier_thermal_only.joblib")
OUT_REPORT = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2021", "track_k_results.json")

LABEL = "label_real_fire_nearby"
RULE_ANOMALY_THRESHOLD = 10.0
RULE_CLOUD_PROXY_THRESHOLD = 0.3


def rule_based_predict(df):
    clear_sky = df["cloud_proxy"] < RULE_CLOUD_PROXY_THRESHOLD
    hot_signature = df["nfd_anomaly"] >= RULE_ANOMALY_THRESHOLD
    return (clear_sky & hot_signature).astype(int).values


def eval_block(name, y_true, y_pred, y_score=None):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    out = {
        "n": int(len(y_true)), "n_positive": int(y_true.sum()),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }
    out["roc_auc"] = float(roc_auc_score(y_true, y_score)) if (
        y_score is not None and len(np.unique(y_true)) > 1) else None
    auc_s = f"{out['roc_auc']:.3f}" if out["roc_auc"] is not None else "n/a"
    print(f"  {name:38s} TP={tp:5d} FP={fp:5d} FN={fn:5d} TN={tn:6d}  "
          f"P={out['precision']:.3f} R={out['recall']:.3f} F1={out['f1']:.3f} AUC={auc_s}")
    return out


def main():
    df_2021 = pd.read_parquet(DATA_2021)
    print(f"real 2021 dataset: {len(df_2021)} rows, {int(df_2021[LABEL].sum())} positive "
          f"({df_2021[LABEL].mean()*100:.2f}%), {df_2021['date'].nunique()} real distinct dates")

    ck = joblib.load(MODEL_PATH)
    model = ck["model"]
    feats = ck["features"]
    print(f"loaded existing trained model (no retraining), features={feats}, role={ck.get('role')}")

    X = df_2021[feats].values
    y = df_2021[LABEL].astype(int).values
    y_pred = model.predict(X)
    y_score = model.predict_proba(X)[:, 1]

    results = {
        "note": "VALIDATION REPLAY ONLY -- model trained on Nov 2023 data, not retrained here",
        "model_trained_on": "Nov 2023 (Track E original)",
        "evaluated_on": "Nov 2021 (Track K, full 15-day grid, never seen during training)",
        "n_2021_rows": len(df_2021), "n_2021_positive": int(y.sum()),
        "n_2021_dates": int(df_2021["date"].nunique()),
    }

    print("\n=== Trained thermal-only GBT (Nov 2023 model, UNCHANGED), real full 2021 grid ===")
    results["gbt_thermal_only_2021_full"] = eval_block("GBT thermal-only [2021 full grid]", y, y_pred, y_score)

    print("\n=== Rule-based det_residue_burning() logic, real full 2021 grid ===")
    y_rule = rule_based_predict(df_2021)
    results["rule_2021_full_grid"] = eval_block("Rule [2021 full grid]", y, y_rule, None)

    # Original Nov 2023 numbers, for direct side-by-side (not recomputed, copied from
    # the persisted Track E report so this file is self-contained for comparison).
    te_path = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2023", "track_e_results.json")
    if os.path.exists(te_path):
        te = json.load(open(te_path))
        results["original_2023_thermal_only_test"] = te["thermal_only"]["gbt_test"]
        results["original_2023_rule_full_grid"] = te["rule_full_grid"]

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {OUT_REPORT}")

    print("\n=== Side-by-side ===")
    o = results.get("original_2023_thermal_only_test", {})
    n = results["gbt_thermal_only_2021_full"]
    print(f"  Model on 2023 test (original headline): P={o.get('precision'):.3f} R={o.get('recall'):.3f} "
          f"F1={o.get('f1'):.3f} AUC={o.get('roc_auc')}")
    print(f"  Model on 2021 full grid (this replay):  P={n['precision']:.3f} R={n['recall']:.3f} "
          f"F1={n['f1']:.3f} AUC={n['roc_auc']:.3f}")


if __name__ == "__main__":
    main()
