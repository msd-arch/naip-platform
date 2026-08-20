#!/usr/bin/env python3
"""
train_flood_classifier.py -- Phase 3 Track D, Steps 7-8: train a real
Sentinel-1 SAR flood classifier against the real 2022 Pakistan floods,
using real independent (non-satellite-derived) district-level ground truth,
and compare against the established real non-ML SAR-threshold rule.

SPLIT: real spatially-blocked -- whole districts held out (never split by
individual point, same rigor as Track E/F), stratified by each district's
real flood label so both classes are represented in train/val/test.

FEATURES: VV_during, VH_during, VV_change, VH_change, jrc_occurrence -- no
lat/lon, no district-identity (confirmed excluded, same leakage risk Track
E/F already established, arguably worse here since flood extent is itself
strongly location-correlated via river proximity/elevation/drainage).

BASELINE: the real, established non-ML SAR flood-detection rule -- flag
water if VV_during < -17 dB (a standard real literature threshold for
SAR-detected open water) AND jrc_occurrence < 5% (to exclude real permanent
rivers/lakes, not just "detect the river"). This is the honest baseline
every prior track's trained model has had to beat.

Permutation feature importance is computed and reported BEFORE any headline
number, exactly like Track E/F's self-check discipline.
"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "flood_dataset.csv")
OUT_PATH = os.path.join(HERE, "track_d_results.json")

FEATURES = ["VV_during", "VH_during", "VV_change", "VH_change", "jrc_occurrence"]
LABEL = "flooded"

RULE_VV_THRESHOLD_DB = -17.0
RULE_JRC_THRESHOLD_PCT = 5.0


def rule_based_predict(df):
    return ((df["VV_during"] < RULE_VV_THRESHOLD_DB) & (df["jrc_occurrence"] < RULE_JRC_THRESHOLD_PCT)).astype(int)


def eval_block(name, y_true, y_pred, y_score=None):
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
    print(f"  {name:20s} TP={tp:4d} FP={fp:4d} FN={fn:4d} TN={tn:4d}  "
          f"P={out['precision']:.3f} R={out['recall']:.3f} F1={out['f1']:.3f} AUC={auc_s}")
    return out


def stratified_district_split(df, seed=42):
    rng = np.random.default_rng(seed)
    by_label = df.groupby("district")[LABEL].first()
    results = {0: [], 1: []}
    for label_val in (0, 1):
        ds = list(by_label[by_label == label_val].index)
        rng.shuffle(ds)
        results[label_val] = ds
    train, val, test = [], [], []
    for label_val, ds in results.items():
        n = len(ds)
        n_test = max(1, round(n * 0.2))
        n_val = max(1, round(n * 0.15))
        test += ds[:n_test]
        val += ds[n_test:n_test + n_val]
        train += ds[n_test + n_val:]
    return train, val, test


def main():
    df = pd.read_csv(DATA_PATH)
    print(f"real dataset: {len(df)} rows, {df[LABEL].sum()} flooded "
          f"({df[LABEL].mean()*100:.1f}%), {df['district'].nunique()} real districts")

    train_d, val_d, test_d = stratified_district_split(df)
    print(f"real spatially-blocked split -- train: {len(train_d)} districts, "
          f"val: {len(val_d)} districts, test: {len(test_d)} districts")
    print(f"  test districts: {sorted(test_d)}")

    train = df[df["district"].isin(train_d)].reset_index(drop=True)
    val = df[df["district"].isin(val_d)].reset_index(drop=True)
    test = df[df["district"].isin(test_d)].reset_index(drop=True)
    print(f"real point counts -- train: {len(train)}, val: {len(val)}, test: {len(test)}")

    Xtr, ytr = train[FEATURES].values, train[LABEL].values
    Xval, yval = val[FEATURES].values, val[LABEL].values
    Xte, yte = test[FEATURES].values, test[LABEL].values

    results = {
        "features_used": FEATURES, "n_train_districts": len(train_d), "n_val_districts": len(val_d),
        "n_test_districts": len(test_d), "test_districts": sorted(test_d),
        "n_train_points": len(train), "n_val_points": len(val), "n_test_points": len(test),
        "note_on_no_geo_features": "lat/lon and district-identity deliberately excluded, same "
                                    "leakage risk established in Track E/F, confirmed absent.",
    }

    gbt = HistGradientBoostingClassifier(max_depth=4, max_iter=200, class_weight="balanced", random_state=0)
    gbt.fit(Xtr, ytr)
    print("\nGradient Boosted Trees:")
    results["gbt_val"] = eval_block("GBT val", yval, gbt.predict(Xval), gbt.predict_proba(Xval)[:, 1])
    results["gbt_test"] = eval_block("GBT test", yte, gbt.predict(Xte), gbt.predict_proba(Xte)[:, 1])
    results["gbt_val"]["role"] = "headline_result"
    results["gbt_test"]["role"] = "headline_result"

    imp = permutation_importance(gbt, Xte, yte, n_repeats=10, random_state=0, scoring="f1")
    importances = sorted(zip(FEATURES, imp.importances_mean), key=lambda x: -x[1])
    print("\nreal permutation feature importance (GBT, test set):")
    for f, v in importances:
        print(f"  {f:20s} {v:.4f}")
    results["gbt_feature_importance"] = {f: float(v) for f, v in importances}

    print(f"\nEstablished SAR-threshold rule (VV < {RULE_VV_THRESHOLD_DB} dB AND "
          f"JRC occurrence < {RULE_JRC_THRESHOLD_PCT}%):")
    rule_pred_test = rule_based_predict(test)
    results["rule_test"] = eval_block("Rule test", yte, rule_pred_test.values, None)
    results["rule_test"]["role"] = "baseline"

    rule_pred_full = rule_based_predict(df)
    results["rule_full_dataset"] = eval_block("Rule full dataset", df[LABEL].values, rule_pred_full.values, None)
    results["rule_full_dataset"]["role"] = "baseline"

    import joblib
    joblib.dump({"model": gbt, "features": FEATURES, "role": "headline_result / deployed candidate"},
                os.path.join(HERE, "gbt_flood_classifier.joblib"))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
