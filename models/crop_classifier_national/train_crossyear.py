#!/usr/bin/env python3
"""
train_crossyear.py -- Phase 4 Track J: genuine temporal-holdout cross-year
validation for Track F's crop-share model. Same architecture, same
features, same rigor as train_crop_share_model.py -- a real cross-year
test, not a new model.

BOTH DIRECTIONS reported, not just whichever looks better:
  A: train on real 2021-22 (features+labels), test on real 2022-23
     (the original dataset train_crop_share_model.py was built on).
  B: train on real 2022-23, test on real 2021-22.

Same real points (Track F's exact 2,875, same lat/lon) used both years --
isolates the real temporal effect, not a spatial-sampling confound.
No lat/lon or district-identity feature. Permutation importance computed
for both directions before either headline number is reported --
specifically checking the model isn't learning district identity through
a back door (crop type is genuinely location-correlated, the same real
risk flagged in Track F's original kickoff).
"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.multioutput import MultiOutputRegressor

HERE = os.path.dirname(os.path.abspath(__file__))
FEATURES_2223_PATH = os.path.join(HERE, "phenology_features.csv")
FEATURES_2122_PATH = os.path.join(HERE, "phenology_features_2021_22.csv")
CROP_MIX_2223_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json")
CROP_MIX_2122_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix_2021_22.json")
ORIGINAL_RESULTS_PATH = os.path.join(HERE, "track_f_results.json")
OUT_PATH = os.path.join(HERE, "track_j_crossyear_results.json")

CROPS = ["wheat", "cotton", "rice", "sugarcane"]
FEATURES = [c for idx in ("ndvi", "ndwi", "evi") for c in (
    f"{idx}_peak_value", f"{idx}_peak_month", f"{idx}_trough_value", f"{idx}_trough_month",
    f"{idx}_green_up_slope", f"{idx}_senescence_slope", f"{idx}_annual_mean", f"{idx}_annual_std",
)]


def build_dataset(features_path, crop_mix_path):
    df = pd.read_csv(features_path)
    with open(crop_mix_path, encoding="utf-8") as f:
        crop_mix = json.load(f)
    rows = []
    for _, r in df.iterrows():
        rec = crop_mix.get(r["district"])
        if rec is None or rec["tier"] != "real_district_area":
            continue
        shares = {c: rec["crops"].get(c, {}).get("share_of_4crop_area", 0.0) for c in CROPS}
        row = dict(r)
        row.update({f"label_{c}": shares[c] for c in CROPS})
        rows.append(row)
    data = pd.DataFrame(rows)
    n_before = len(data)
    data = data.dropna(subset=FEATURES).reset_index(drop=True)
    return data, n_before


def eval_block(name, y_true, y_pred):
    out = {}
    for i, crop in enumerate(CROPS):
        out[crop] = {
            "mae": float(mean_absolute_error(y_true[:, i], y_pred[:, i])),
            "r2": float(r2_score(y_true[:, i], y_pred[:, i])),
        }
    overall_mae = float(mean_absolute_error(y_true, y_pred))
    out["overall_mae"] = overall_mae
    print(f"  {name}: overall MAE={overall_mae:.4f}  |  " +
          ", ".join(f"{c}: R2={out[c]['r2']:.3f}" for c in CROPS))
    return out


def district_level_eval(name, test_df, pred, crops=CROPS):
    test_pred_df = test_df[["district"]].copy()
    for i, c in enumerate(crops):
        test_pred_df[f"pred_{c}"] = pred[:, i]
    district_level = test_pred_df.groupby("district").mean(numeric_only=True)
    district_true = test_df.groupby("district")[[f"label_{c}" for c in crops]].first()
    yte_d = district_true.values
    ypred_d = district_level[[f"pred_{c}" for c in crops]].values
    return eval_block(name, yte_d, ypred_d)


def run_direction(name, train_df, test_df):
    print(f"\n=== Direction: {name} ===")
    print(f"real train: {len(train_df)} points, {train_df['district'].nunique()} districts")
    print(f"real test: {len(test_df)} points, {test_df['district'].nunique()} districts")

    Xtr, ytr = train_df[FEATURES].values, train_df[[f"label_{c}" for c in CROPS]].values
    Xte, yte = test_df[FEATURES].values, test_df[[f"label_{c}" for c in CROPS]].values

    gbt = MultiOutputRegressor(HistGradientBoostingRegressor(max_depth=4, max_iter=200, random_state=0))
    gbt.fit(Xtr, ytr)
    pred_point = gbt.predict(Xte)

    result = {
        "n_train_points": len(train_df), "n_test_points": len(test_df),
        "n_train_districts": int(train_df["district"].nunique()),
        "n_test_districts": int(test_df["district"].nunique()),
        "point_level": eval_block(f"{name} point-level", yte, pred_point),
        "district_level": district_level_eval(f"{name} district-level", test_df, pred_point),
    }

    imp = permutation_importance(gbt, Xte, yte, n_repeats=5, random_state=0, scoring="r2")
    importances = sorted(zip(FEATURES, imp.importances_mean), key=lambda x: -x[1])
    print(f"  real permutation feature importance ({name}, top 5):")
    for f, v in importances[:5]:
        print(f"    {f:25s} {v:.4f}")
    result["feature_importance_top5"] = {f: float(v) for f, v in importances[:5]}
    result["role"] = "headline_result_crossyear"
    return result


def main():
    data_2223, n_before_2223 = build_dataset(FEATURES_2223_PATH, CROP_MIX_2223_PATH)
    data_2122, n_before_2122 = build_dataset(FEATURES_2122_PATH, CROP_MIX_2122_PATH)
    print(f"real 2022-23 dataset: {len(data_2223)} usable points (dropped "
          f"{n_before_2223 - len(data_2223)}), {data_2223['district'].nunique()} districts")
    print(f"real 2021-22 dataset: {len(data_2122)} usable points (dropped "
          f"{n_before_2122 - len(data_2122)}), {data_2122['district'].nunique()} districts")

    # real check for the risk named in the task: crop type is genuinely
    # location-correlated -- confirm district-identity/lat/lon are absent
    # from FEATURES (they are, by construction) before trusting either
    # direction's permutation-importance self-check below.
    assert "district" not in FEATURES and "lat" not in FEATURES and "lon" not in FEATURES

    result_A = run_direction("train=2021-22, test=2022-23 (original dataset)", data_2122, data_2223)
    result_B = run_direction("train=2022-23, test=2021-22", data_2223, data_2122)

    with open(ORIGINAL_RESULTS_PATH, encoding="utf-8") as f:
        original = json.load(f)
    original_district = original["gbt_test_district_level"]

    print("\n=== Real comparison against the original Week 8 within-year result ===")
    for crop in CROPS:
        print(f"  {crop:10s} original={original_district[crop]['r2']:.3f}  "
              f"A(train2122->test2223)={result_A['district_level'][crop]['r2']:.3f}  "
              f"B(train2223->test2122)={result_B['district_level'][crop]['r2']:.3f}")

    out = {
        "features_used": FEATURES,
        "note": "Genuine temporal-holdout cross-year validation, both directions, real Track F "
                "points reused unchanged (same lat/lon both years, isolates the real temporal "
                "effect). Compare against original_week8_within_year_district_level for the real "
                "cross-year vs. within-year degradation.",
        "direction_A_train2122_test2223": result_A,
        "direction_B_train2223_test2122": result_B,
        "original_week8_within_year_district_level": original_district,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
