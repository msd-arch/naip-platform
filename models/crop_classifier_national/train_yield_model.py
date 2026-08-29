#!/usr/bin/env python3
"""
train_yield_model.py -- Phase 5 Track O: real yield (tons/hectare) prediction
per district/crop, extending Track F's real Sentinel-2 phenology
infrastructure to a new real target.

REAL PRE-CHECK RESULT: production figures were already extracted by the
existing MNFSR parsers, just never independently cross-validated or used as
a training target -- see build_real_yield_dataset.py (Phase 5 Track O) for
the real gap found (production rode on the area check, never its own) and
closed (real, separate production-total cross-validation added, same 5%
discipline). Real coverage: 263/257 (district,crop) yield cells for
2022-23/2021-22 respectively, 115/126 real districts -- essentially the
same real scale as Track F's own crop-share work, zero new sourcing.

REAL, CONFIRMED-NOT-ASSUMED INFEASIBILITY: the task asked to test whether
real hazard co-occurrence (heat/drought exposure during the growing season,
from hazards.py) adds real signal via ablation. Checked directly: NAIP's
only real MSG archives are Nov 2021 (15 days) and Nov 2023 (15 days) --
neither gives meaningful coverage of either real yield-label growing season
(2021-22 = Nov 2021-Oct 2022; 2022-23 = Nov 2022-Oct 2023). A 15-day slice
at the very start of one season is not "heat/drought exposure during the
growing season" in any real sense. This ablation is real-data-infeasible
with what's on disk -- not attempted, not faked with a placeholder feature.

PER-CROP MODELS, not Track F's multi-output-across-4-crops shape: yield is
only DEFINED where a crop is actually grown (unlike crop-share, which is a
valid 0.0 for an ungrown crop) -- so each crop gets its own model, trained
only on real rows where that crop has a real, validated yield value.

Same rigor as every prior track: no lat/lon or district-identity feature,
real cross-year validation both directions, permutation-importance
self-check before any headline number, real naive-baseline comparison
(does the model beat "this year's yield = last year's real reported
yield for that district/crop"?).
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "validation"))
from standard_checks import regression_distribution_report  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FEATURES_2223_PATH = os.path.join(HERE, "phenology_features.csv")
FEATURES_2122_PATH = os.path.join(HERE, "phenology_features_2021_22.csv")
YIELD_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_yield.json")
OUT_PATH = os.path.join(HERE, "track_o_yield_results.json")

CROPS = ["wheat", "cotton", "rice", "sugarcane"]
FEATURES = [c for idx in ("ndvi", "ndwi", "evi") for c in (
    f"{idx}_peak_value", f"{idx}_peak_month", f"{idx}_trough_value", f"{idx}_trough_month",
    f"{idx}_green_up_slope", f"{idx}_senescence_slope", f"{idx}_annual_mean", f"{idx}_annual_std",
)]


def build_dataset(features_path, yield_year):
    df = pd.read_csv(features_path)
    with open(YIELD_PATH, encoding="utf-8") as f:
        yields = json.load(f)[yield_year]
    per_crop = {}
    for crop in CROPS:
        rows = []
        for _, r in df.iterrows():
            rec = yields.get(r["district"], {}).get(crop)
            if rec is None:
                continue
            row = dict(r)
            row["label_yield"] = rec["yield_tons_per_ha"]
            rows.append(row)
        data = pd.DataFrame(rows)
        n_before = len(data)
        if n_before:
            data = data.dropna(subset=FEATURES).reset_index(drop=True)
        per_crop[crop] = (data, n_before)
    return per_crop


def district_level_eval(test_df, pred):
    tmp = test_df[["district"]].copy()
    tmp["pred"] = pred
    district_pred = tmp.groupby("district")["pred"].mean()
    district_true = test_df.groupby("district")["label_yield"].first()
    yte_d = district_true.reindex(district_pred.index).values
    ypred_d = district_pred.values
    return yte_d, ypred_d


def eval_block(y_true, y_pred):
    return {
        "n": int(len(y_true)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)) if len(y_true) > 1 else None,
    }


def run_crop_direction(crop, name, train_df, test_df):
    if len(train_df) < 8 or len(test_df) < 8:
        return {"skipped": True, "reason": f"too few real rows (train={len(train_df)}, test={len(test_df)})"}

    Xtr, ytr = train_df[FEATURES].values, train_df["label_yield"].values
    Xte, yte = test_df[FEATURES].values, test_df["label_yield"].values

    gbt = HistGradientBoostingRegressor(max_depth=3, max_iter=150, random_state=0)
    gbt.fit(Xtr, ytr)
    pred_point = gbt.predict(Xte)

    point_level = eval_block(yte, pred_point)
    yte_d, ypred_d = district_level_eval(test_df, pred_point)
    district_level = eval_block(yte_d, ypred_d)

    imp = permutation_importance(gbt, Xte, yte, n_repeats=8, random_state=0, scoring="r2")
    importances = sorted(zip(FEATURES, imp.importances_mean), key=lambda x: -x[1])

    print(f"  [{crop}] {name}: point R2={point_level['r2']:.3f} MAE={point_level['mae']:.3f} | "
          f"district R2={district_level['r2']:.3f} MAE={district_level['mae']:.3f} "
          f"(n_district={district_level['n']})")

    return {
        "n_train_rows": len(train_df), "n_test_rows": len(test_df),
        "n_train_districts": int(train_df["district"].nunique()),
        "n_test_districts": int(test_df["district"].nunique()),
        "point_level": point_level, "district_level": district_level,
        "feature_importance_top5": {f: float(v) for f, v in importances[:5]},
    }


def naive_baseline(crop, year_a_yields, year_b_yields, direction_label):
    """Real, cheap baseline: this district's OTHER real year's reported yield,
    used directly as the prediction for the target year -- no model at all.
    Only computable for districts with a real reported yield in BOTH years."""
    common = set(year_a_yields) & set(year_b_yields)
    if not common:
        return {"skipped": True, "reason": "no districts with real yield in both years"}
    y_true = np.array([year_b_yields[d] for d in sorted(common)])
    y_pred = np.array([year_a_yields[d] for d in sorted(common)])
    out = eval_block(y_true, y_pred)
    out["n_districts"] = len(common)
    print(f"  [{crop}] naive baseline ({direction_label}): "
          f"R2={out['r2']:.3f} MAE={out['mae']:.3f} (n={out['n_districts']} districts)")
    return out


def main():
    per_crop_2223 = build_dataset(FEATURES_2223_PATH, "2022-23")
    per_crop_2122 = build_dataset(FEATURES_2122_PATH, "2021-22")

    with open(YIELD_PATH, encoding="utf-8") as f:
        yields = json.load(f)

    results = {"features_used": FEATURES, "crops": {}}
    for crop in CROPS:
        print(f"\n=== {crop} ===")
        data_2223, n_before_2223 = per_crop_2223[crop]
        data_2122, n_before_2122 = per_crop_2122[crop]
        print(f"  real rows: 2022-23={len(data_2223)} (of {n_before_2223} candidate), "
              f"2021-22={len(data_2122)} (of {n_before_2122} candidate)")

        # Track U retrofit: real distribution/outlier check on the real yield
        # label, before training -- makes STATUS_WEEK22.md's one-off manual
        # finding (7 near-zero print-precision cells, 1 genuine outlier)
        # repeatable code instead of a session-log-only claim.
        all_yield = pd.concat([data_2223["label_yield"], data_2122["label_yield"]], ignore_index=True)
        yield_distribution = regression_distribution_report(all_yield.values)

        result = {
            "n_real_yield_cells_2022_23": len(data_2223),
            "n_real_yield_cells_2021_22": len(data_2122),
            "real_yield_label_distribution": yield_distribution,
        }
        result["direction_A_train2122_test2223"] = run_crop_direction(
            crop, "train=2021-22, test=2022-23", data_2122, data_2223)
        result["direction_B_train2223_test2122"] = run_crop_direction(
            crop, "train=2022-23, test=2021-22", data_2223, data_2122)

        y2223 = {d: v[crop]["yield_tons_per_ha"] for d, v in yields["2022-23"].items() if crop in v}
        y2122 = {d: v[crop]["yield_tons_per_ha"] for d, v in yields["2021-22"].items() if crop in v}
        result["naive_baseline_A_predict2223_from2122"] = naive_baseline(
            crop, y2122, y2223, "predict 2022-23 from 2021-22's real reported yield")
        result["naive_baseline_B_predict2122_from2223"] = naive_baseline(
            crop, y2223, y2122, "predict 2021-22 from 2022-23's real reported yield")

        results["crops"][crop] = result

    results["real_hazard_ablation"] = {
        "attempted": False,
        "reason": "Checked directly, not assumed: NAIP's only real MSG archives are Nov 2021 "
                  "(15 days) and Nov 2023 (15 days) -- neither gives meaningful coverage of "
                  "either real yield-label growing season (2021-22 = Nov 2021-Oct 2022; "
                  "2022-23 = Nov 2022-Oct 2023). A 15-day slice at the start of one season is "
                  "not real 'heat/drought exposure during the growing season'. Real-data-"
                  "infeasible with what's on disk -- not attempted, not faked with a "
                  "placeholder feature. See STATUS_WEEK22.md.",
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
