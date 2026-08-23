#!/usr/bin/env python3
"""
eval_2024_full.py -- Phase 4 Track I follow-up: a genuine, fair, real
precision/recall/F1 cross-year test against the FULL real 2024 season
(positive = 14 real calamity-declared districts, negative = the other 112
real districts NOT declared calamity-hit in the same real monsoon season --
the identical within-season methodology Track D's original 2022 dataset
used). Evaluates BOTH the original Track D model and the v2 (2021-expanded)
candidate on this same real held-out year, for a fair side-by-side.
"""
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

HERE = os.path.dirname(os.path.abspath(__file__))
POS_PATH = os.path.join(HERE, "flood_dataset_2024.csv")
NEG_PATH = os.path.join(HERE, "flood_dataset_2024_negatives.csv")
OUT_PATH = os.path.join(HERE, "track_i_2024_full_eval.json")

FEATURES = ["VV_during", "VH_during", "VV_change", "VH_change", "jrc_occurrence"]
LABEL = "flooded"


def eval_block(name, y_true, y_pred, y_score):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    out = {
        "n": int(len(y_true)), "n_positive": int(np.sum(y_true)),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_score)) if len(np.unique(y_true)) > 1 else None,
    }
    auc_s = f"{out['roc_auc']:.3f}" if out["roc_auc"] is not None else "n/a"
    print(f"  {name:30s} TP={tp:4d} FP={fp:4d} FN={fn:4d} TN={tn:4d}  "
          f"P={out['precision']:.3f} R={out['recall']:.3f} F1={out['f1']:.3f} AUC={auc_s}")
    return out


def main():
    pos = pd.read_csv(POS_PATH)
    neg = pd.read_csv(NEG_PATH)
    df = pd.concat([pos, neg], ignore_index=True)
    print(f"real full 2024 test set: {len(df)} points, {df[LABEL].sum()} flooded "
          f"({df['district'].nunique()} districts)")

    X = df[FEATURES].values
    y = df[LABEL].values

    orig_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier.joblib"))
    v2_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier_v2_2021neg.joblib"))

    print("\nreal fair cross-year comparison, both models, same real 2024 test set:")
    result_orig = eval_block("Original (Track D, 2022-only)", y, orig_bundle["model"].predict(X),
                              orig_bundle["model"].predict_proba(X)[:, 1])
    result_v2 = eval_block("v2 (2021-expanded)", y, v2_bundle["model"].predict(X),
                            v2_bundle["model"].predict_proba(X)[:, 1])

    out = {
        "n_test_points": len(df), "n_positive": int(df[LABEL].sum()),
        "n_districts": int(df["district"].nunique()),
        "original_model_on_2024": result_orig,
        "v2_model_on_2024": result_v2,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
