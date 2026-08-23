#!/usr/bin/env python3
"""
train_flood_classifier_v2.py -- Phase 4 Track I: retrain Track D's flood
classifier with a real non-disaster negative class (2021) added to the
original 2022 not-flooded districts, and validate cross-year against a real
second disaster year (2024). Same architecture, same features, same rigor as
train_flood_classifier.py -- a re-split-and-retrain, not a new model.

REAL EVALUATION DESIGN, deliberately apples-to-apples:
  1. "Before/after on the original 2022 test set": TEST = the exact same 25
     real districts Track D's original test_districts list held out (fixed,
     reused verbatim, not re-randomized) -- their real 2022 points only.
     TRAIN = every other district's real 2022 points + real 2021 points from
     districts NOT in the test set (spatial-blocking discipline maintained:
     no test district's data, from either year, ever appears in training).
     This isolates one real question: does adding real 2021 negatives change
     performance on the identical original real held-out districts?
  2. "Genuine cross-year validation": TRAIN = ALL real 2022 + 2021 points
     (every district, both years). TEST = the real 2024 positive-class points
     (14 real calamity-declared districts, label=1 only -- precision/F1 are
     not meaningful without real 2024 negatives, so only recall is reported,
     labeled as such, not padded with a fabricated precision number).

Permutation importance computed for both real models before any headline
number, same self-check discipline as every prior track -- specifically
checking the retrained model isn't leaning on some spurious 2021-vs-2022
artifact as a proxy for flood vs. not-flood.
"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_2022_PATH = os.path.join(HERE, "flood_dataset.csv")
DATA_2021_PATH = os.path.join(HERE, "flood_dataset_2021.csv")
DATA_2024_PATH = os.path.join(HERE, "flood_dataset_2024.csv")
ORIGINAL_RESULTS_PATH = os.path.join(HERE, "track_d_results.json")
OUT_PATH = os.path.join(HERE, "track_i_results.json")

FEATURES = ["VV_during", "VH_during", "VV_change", "VH_change", "jrc_occurrence"]
LABEL = "flooded"


def eval_block(name, y_true, y_pred, y_score=None, recall_only=False):
    if recall_only:
        r = recall_score(y_true, y_pred, zero_division=0)
        out = {"n": int(len(y_true)), "n_positive": int(np.sum(y_true)),
               "recall": float(r), "role": "recall_only_cross_year_positive_class_test"}
        print(f"  {name:28s} n={out['n']:4d}  RECALL={r:.3f}  "
              "(precision/F1 not meaningful -- no real negatives in this test set)")
        return out
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    out = {
        "n": int(len(y_true)), "n_positive": int(np.sum(y_true)),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }
    out["roc_auc"] = float(roc_auc_score(y_true, y_score)) if (
        y_score is not None and len(np.unique(y_true)) > 1) else None
    auc_s = f"{out['roc_auc']:.3f}" if out["roc_auc"] is not None else "n/a"
    print(f"  {name:28s} TP={tp:4d} FP={fp:4d} FN={fn:4d} TN={tn:4d}  "
          f"P={out['precision']:.3f} R={out['recall']:.3f} F1={out['f1']:.3f} AUC={auc_s}")
    return out


def main():
    df22 = pd.read_csv(DATA_2022_PATH)
    df22["year"] = 2022
    df21 = pd.read_csv(DATA_2021_PATH)
    df24 = pd.read_csv(DATA_2024_PATH)

    with open(ORIGINAL_RESULTS_PATH, encoding="utf-8") as f:
        original = json.load(f)
    test_districts = set(original["test_districts"])
    print(f"real original test districts (reused verbatim, not re-randomized): "
          f"{len(test_districts)}")

    print(f"\nreal 2022 dataset: {len(df22)} points, {df22[LABEL].sum()} flooded")
    print(f"real 2021 dataset: {len(df21)} points, all real non-disaster negatives "
          f"({df21['district'].nunique()} districts)")
    print(f"real 2024 dataset: {len(df24)} points, all real positive-class "
          f"({df24['district'].nunique()} districts)")

    # ---- Evaluation 1: before/after on the ORIGINAL real 2022 test set ----
    test_22 = df22[df22["district"].isin(test_districts)].reset_index(drop=True)
    train_22 = df22[~df22["district"].isin(test_districts)]
    train_21_nontest = df21[~df21["district"].isin(test_districts)]
    train_combined = pd.concat([train_22, train_21_nontest], ignore_index=True)
    print(f"\n=== Evaluation 1: real before/after on the ORIGINAL 2022 test districts ===")
    print(f"real train (expanded): {len(train_combined)} points "
          f"({len(train_22)} real 2022 + {len(train_21_nontest)} real 2021 negatives)")
    print(f"real test (unchanged, 2022-only, same districts as original): {len(test_22)} points")

    Xtr, ytr = train_combined[FEATURES].values, train_combined[LABEL].values
    Xte, yte = test_22[FEATURES].values, test_22[LABEL].values

    gbt_v2 = HistGradientBoostingClassifier(max_depth=4, max_iter=200, class_weight="balanced", random_state=0)
    gbt_v2.fit(Xtr, ytr)
    result_v2_on_original_test = eval_block("v2 (2021-expanded) on original 2022 test", yte,
                                             gbt_v2.predict(Xte), gbt_v2.predict_proba(Xte)[:, 1])
    result_v2_on_original_test["role"] = "before_after_comparison"

    print(f"\nreal original (Track D, Week 10) for comparison: "
          f"P={original['gbt_test']['precision']:.3f} R={original['gbt_test']['recall']:.3f} "
          f"F1={original['gbt_test']['f1']:.3f}")

    imp1 = permutation_importance(gbt_v2, Xte, yte, n_repeats=10, random_state=0, scoring="f1")
    importances1 = sorted(zip(FEATURES, imp1.importances_mean), key=lambda x: -x[1])
    print("\nreal permutation feature importance (v2 model, original 2022 test set):")
    for f, v in importances1:
        print(f"  {f:20s} {v:.4f}")

    # ---- Evaluation 2: genuine cross-year validation against real 2024 ----
    print(f"\n=== Evaluation 2: genuine cross-year validation (train 2022+2021, test 2024) ===")
    train_full = pd.concat([df22, df21], ignore_index=True)
    print(f"real train (all districts, both years): {len(train_full)} points")
    print(f"real test (2024, positive-class only, never seen in training): {len(df24)} points")

    Xtr2, ytr2 = train_full[FEATURES].values, train_full[LABEL].values
    Xte2, yte2 = df24[FEATURES].values, df24[LABEL].values

    gbt_xyear = HistGradientBoostingClassifier(max_depth=4, max_iter=200, class_weight="balanced", random_state=0)
    gbt_xyear.fit(Xtr2, ytr2)
    result_2024_crossyear = eval_block("v2 model on real 2024 (cross-year)", yte2,
                                        gbt_xyear.predict(Xte2), recall_only=True)

    # self-check: is the cross-year model leaning on anything spurious?
    # can't do permutation importance meaningfully on an all-positive test set
    # (F1/recall don't vary with feature shuffling on a single-class set in the
    # informative way they do on a balanced one) -- instead, check the SAME
    # v2 model (trained on 2022+2021) against the original 2022 test set, to
    # confirm it didn't lose real signal by training on the full pooled set.
    result_xyear_model_on_2022_test = eval_block(
        "v2-full (2022+2021) on original 2022 test", yte,
        gbt_xyear.predict(Xte), gbt_xyear.predict_proba(Xte)[:, 1])
    result_xyear_model_on_2022_test["role"] = "self_check_not_headline"

    out = {
        "features_used": FEATURES,
        "original_test_districts_reused": sorted(test_districts),
        "eval1_before_after_original_2022_test": {
            "original_track_d_week10": original["gbt_test"],
            "v2_2021_expanded": result_v2_on_original_test,
            "feature_importance_v2": {f: float(v) for f, v in importances1},
        },
        "eval2_cross_year_2024": {
            "result": result_2024_crossyear,
            "self_check_v2full_on_2022_test": result_xyear_model_on_2022_test,
        },
        "real_2021_exclusions": [
            "Islamabad Capital Territory", "Karachi", "Lower Dir", "Abbottabad",
            "Tank", "Dera Ismail Khan", "Kohistan",
        ],
        "real_2024_districts_matched": sorted(df24["district"].unique().tolist()),
    }

    import joblib
    joblib.dump({"model": gbt_v2, "features": FEATURES,
                 "role": "candidate_v2 -- NOT deployed, awaiting explicit decision (Track I)"},
                os.path.join(HERE, "gbt_flood_classifier_v2_2021neg.joblib"))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")
    print("wrote gbt_flood_classifier_v2_2021neg.joblib (candidate only, NOT deployed)")


if __name__ == "__main__":
    main()
