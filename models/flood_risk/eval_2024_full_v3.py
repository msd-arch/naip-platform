#!/usr/bin/env python3
"""
eval_2024_full_v3.py -- Track I, precipitation attempt: the same fair,
labeled, full 2024 cross-year test Track I's v2 attempt used (14 real
calamity-declared positive districts + 112 real non-declared negative
districts, same within-season methodology as the original 2022 dataset),
now scoring THREE models side by side -- original, v2 (2021-expanded), and
v3 (precipitation-augmented) -- for a fair three-way comparison.

Also reproduces the exact score-separation-by-true-label diagnostic that
caught v2's global suppression (STATUS_WEEK14.md, Real result 2b) -- mean
model score for the flooded vs. not-flooded class. A model that "improves"
the live replay number without real separation here would be repeating v2's
mistake, not fixing it.
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
OUT_PATH = os.path.join(HERE, "track_i_v3_2024_full_eval.json")

ORIG_FEATURES = ["VV_during", "VH_during", "VV_change", "VH_change", "jrc_occurrence"]
V3_FEATURES = ORIG_FEATURES + ["precip_total_mm", "precip_anomaly_pct"]
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
    print(f"  {name:32s} TP={tp:4d} FP={fp:4d} FN={fn:4d} TN={tn:4d}  "
          f"P={out['precision']:.3f} R={out['recall']:.3f} F1={out['f1']:.3f} AUC={auc_s}")
    return out


def score_separation(name, y_true, y_score):
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    mean_pos = float(y_score[y_true == 1].mean()) if (y_true == 1).any() else None
    mean_neg = float(y_score[y_true == 0].mean()) if (y_true == 0).any() else None
    gap = (mean_pos - mean_neg) if (mean_pos is not None and mean_neg is not None) else None
    print(f"  {name:32s} mean score flooded={mean_pos:.3f} not-flooded={mean_neg:.3f} gap={gap:.3f}")
    return {"mean_score_flooded": mean_pos, "mean_score_not_flooded": mean_neg, "separation_gap": gap}


def main():
    pos = pd.read_csv(POS_PATH)
    neg = pd.read_csv(NEG_PATH)
    df = pd.concat([pos, neg], ignore_index=True)
    print(f"real full 2024 test set: {len(df)} points, {df[LABEL].sum()} flooded "
          f"({df['district'].nunique()} districts)")

    y = df[LABEL].values
    X_orig = df[ORIG_FEATURES].values
    X_v3 = df[V3_FEATURES].values

    orig_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier.joblib"))
    v2_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier_v2_2021neg.joblib"))
    v3_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier_v3_precip.joblib"))

    print("\nreal fair cross-year comparison, three models, same real 2024 test set:")
    orig_score = orig_bundle["model"].predict_proba(X_orig)[:, 1]
    v2_score = v2_bundle["model"].predict_proba(X_orig)[:, 1]
    v3_score = v3_bundle["model"].predict_proba(X_v3)[:, 1]

    result_orig = eval_block("Original (Track D, 2022-only)", y, orig_bundle["model"].predict(X_orig), orig_score)
    result_v2 = eval_block("v2 (2021-expanded)", y, v2_bundle["model"].predict(X_orig), v2_score)
    result_v3 = eval_block("v3 (precip-augmented)", y, v3_bundle["model"].predict(X_v3), v3_score)

    print("\nreal score-separation-by-true-label diagnostic (the check that caught v2's collapse):")
    sep_orig = score_separation("Original", y, orig_score)
    sep_v2 = score_separation("v2", y, v2_score)
    sep_v3 = score_separation("v3 (precip)", y, v3_score)

    out = {
        "n_test_points": len(df), "n_positive": int(df[LABEL].sum()),
        "n_districts": int(df["district"].nunique()),
        "original_model_on_2024": result_orig,
        "v2_model_on_2024": result_v2,
        "v3_model_on_2024": result_v3,
        "score_separation_diagnostic": {
            "original": sep_orig, "v2": sep_v2, "v3_precip": sep_v3,
            "note": "v2's real failure mode (STATUS_WEEK14.md) was a near-zero separation gap "
                    "(0.012) despite a real precision/recall drop -- a globally suppressed, "
                    "barely-discriminative score, not genuine learned discrimination. Checked "
                    "here for v3 specifically so an apparent live-replay improvement isn't "
                    "mistaken for a real fix without this same diagnostic passing.",
        },
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
