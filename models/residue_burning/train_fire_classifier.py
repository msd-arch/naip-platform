#!/usr/bin/env python3
"""
train_fire_classifier.py -- Phase 3 Track E, Steps 2-3: train real
classifiers on the real grid dataset (build_grid_dataset.py), evaluate on a
real held-out split, and compare directly against det_residue_burning()'s
existing rule-based logic run UNCHANGED on the same full-grid dataset -- an
apples-to-apples comparison Track A's 126-district-centroid sampling could
not produce (see naip/docs/DEMO_TRACK_A.md Section 4).

SPLIT: real spatially/temporally-blocked -- whole real dates held out, not
random individual grid cells (nearby cells on the same day are strongly
correlated; a random split would leak information and inflate scores).
Chronological forward split (train on earlier real dates, test on later
ones):
  train = 2023-11-01..2023-11-10 (10 real dates)
  val   = 2023-11-11..2023-11-12 (2 real dates, model selection only)
  test  = 2023-11-13..2023-11-15 (3 real dates, final reported numbers)

TWO FEATURE SETS, both trained, DIFFERENT ROLES -- decided after review, not
left as an open toss-up:
  - thermal_only: night_fog_diff, nfd_local_bg, nfd_anomaly, cloud_proxy,
    local_hour -- **the headline result and the deployed candidate.** This
    is the fair test of whether a learnable thermal signal exists at all,
    consistent with what det_residue_burning() itself uses. It's the only
    feature set that actually answers Track E's real question: does NAIP's
    real sensor (MSG thermal channels) carry real fire signal.
  - with_geo: thermal_only + lat, lon -- **kept as a secondary ablation
    finding only, explicitly NOT a candidate result.** A first with-geo run
    looked outstanding (F1=0.728) until real permutation feature importance
    showed lat/lon at 0.61/0.52 versus ~0 for every thermal feature -- the
    model was mostly memorizing WHERE fires happened in this window (a
    static geographic prior any Pakistani would already know: Punjab burns
    in November, Balochistan mostly doesn't), not reading the MSG signature.
    A model that answers "what is this seeing" with "mostly nothing from
    the satellite that day" quietly reintroduces the same circularity
    problem Track E exists to avoid -- through a back door (a memorized
    geographic prior instead of re-deriving FIRMS's own algorithm, but the
    same underlying issue: not really using the sensor). Reported here as a
    methodological finding worth presenting on its own terms -- catching and
    diagnosing this is arguably worth more than either F1 number alone --
    not as an alternative headline to pick between.

RULE-BASED BASELINE REPLAY: det_residue_burning()'s actual real logic
(hazards.py) is: flag = clear_sky(cloud_proxy < 0.3) AND anomaly >= 10.0,
where anomaly = night_fog_diff - nfd_local_bg. Reproduced here EXACTLY --
not re-approximated -- and evaluated on the identical real rows the trained
models are evaluated on.
"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix,
)
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2023", "grid_dataset.parquet")
OUT_REPORT = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2023", "track_e_results.json")

FEATURE_SETS = {
    "thermal_only": ["night_fog_diff", "nfd_local_bg", "nfd_anomaly", "cloud_proxy", "local_hour"],
    "with_geo": ["night_fog_diff", "nfd_local_bg", "nfd_anomaly", "cloud_proxy", "local_hour", "lat", "lon"],
}
LABEL = "label_real_fire_nearby"

TRAIN_DATES = [f"202311{d:02d}" for d in range(1, 11)]
VAL_DATES = [f"202311{d:02d}" for d in range(11, 13)]
TEST_DATES = [f"202311{d:02d}" for d in range(13, 16)]

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
    print(f"  {name:28s} TP={tp:5d} FP={fp:5d} FN={fn:5d} TN={tn:6d}  "
          f"P={out['precision']:.3f} R={out['recall']:.3f} F1={out['f1']:.3f} AUC={auc_s}")
    return out


def train_and_eval(df, train, val, test, feats, label):
    Xtr, ytr = train[feats].values, train[LABEL].astype(int).values
    Xval, yval = val[feats].values, val[LABEL].astype(int).values
    Xte, yte = test[feats].values, test[LABEL].astype(int).values

    out = {}

    scaler = StandardScaler().fit(Xtr)
    lr = LogisticRegression(max_iter=2000, class_weight="balanced")
    lr.fit(scaler.transform(Xtr), ytr)
    out["lr_val"] = eval_block(f"LR [{label}] val", yval, lr.predict(scaler.transform(Xval)),
                                lr.predict_proba(scaler.transform(Xval))[:, 1])
    out["lr_test"] = eval_block(f"LR [{label}] test", yte, lr.predict(scaler.transform(Xte)),
                                 lr.predict_proba(scaler.transform(Xte))[:, 1])

    gbt = HistGradientBoostingClassifier(max_depth=4, max_iter=200, class_weight="balanced", random_state=0)
    gbt.fit(Xtr, ytr)
    out["gbt_val"] = eval_block(f"GBT [{label}] val", yval, gbt.predict(Xval), gbt.predict_proba(Xval)[:, 1])
    out["gbt_test"] = eval_block(f"GBT [{label}] test", yte, gbt.predict(Xte), gbt.predict_proba(Xte)[:, 1])

    imp = permutation_importance(gbt, Xte[:8000], yte[:8000], n_repeats=5, random_state=0,
                                  scoring="average_precision")
    out["gbt_feature_importance"] = {f: float(v) for f, v in zip(feats, imp.importances_mean)}

    if label == "thermal_only":
        # persist the headline/deployed candidate only -- the with_geo run is an
        # ablation finding, never a deployment candidate (see module docstring)
        import joblib
        model_path = os.path.join(HERE, "gbt_fire_classifier_thermal_only.joblib")
        joblib.dump({"model": gbt, "features": feats, "label_threshold_default": 0.5,
                     "role": "headline_result / deployed candidate"}, model_path)
        print(f"  saved deployed candidate model to {model_path}")

    return out


def main():
    df = pd.read_parquet(DATA_PATH)
    print(f"real dataset: {len(df)} rows, {df[LABEL].sum()} positive "
          f"({df[LABEL].mean()*100:.2f}%), {df['date'].nunique()} real distinct dates")

    train = df[df["date"].isin(TRAIN_DATES)].reset_index(drop=True)
    val = df[df["date"].isin(VAL_DATES)].reset_index(drop=True)
    test = df[df["date"].isin(TEST_DATES)].reset_index(drop=True)
    print(f"real split -- train: {len(train)} rows ({int(train[LABEL].sum())} pos)")
    print(f"real split -- val:   {len(val)} rows ({int(val[LABEL].sum())} pos)")
    print(f"real split -- test:  {len(test)} rows ({int(test[LABEL].sum())} pos)")

    results = {
        "n_train": len(train), "n_val": len(val), "n_test": len(test),
        "train_dates": TRAIN_DATES, "val_dates": VAL_DATES, "test_dates": TEST_DATES,
    }

    ROLE = {
        "thermal_only": "HEADLINE RESULT / deployed candidate -- answers Track E's real question",
        "with_geo": "ABLATION FINDING ONLY -- not a candidate result, see module docstring",
    }
    for label, feats in FEATURE_SETS.items():
        print(f"\n=== feature set: {label} ({feats}) -- {ROLE[label]} ===")
        results[label] = train_and_eval(df, train, val, test, feats, label)
        results[label]["role"] = ROLE[label]

    print("\n=== Rule-based det_residue_burning() logic (unchanged), same real test rows ===")
    yte = test[LABEL].astype(int).values
    results["rule_test"] = eval_block("Rule test", yte, rule_based_predict(test), None)

    print("\n=== Rule-based logic, FULL real 15-day grid dataset (fair full-grid recall) ===")
    y_full = df[LABEL].astype(int).values
    results["rule_full_grid"] = eval_block("Rule full-grid", y_full, rule_based_predict(df), None)

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
