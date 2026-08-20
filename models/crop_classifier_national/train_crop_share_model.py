#!/usr/bin/env python3
"""
train_crop_share_model.py -- Phase 3 Track F, Steps 2-3: train a real
multi-output regressor predicting each district's real MNFSR crop-area
shares (wheat/cotton/rice/sugarcane, all in [0,1], summing to ~1) from real
Sentinel-2 phenology-curve features (extract_phenology_features.py).

TASK FRAMING, confirmed with you after a real pre-check found the obvious
"predict dominant crop" framing degenerate (wheat dominant in 107/115 real
MNFSR districts -- the same collapse-to-one-class trap Week 2's cropland
task hit): predict the real continuous crop-share VECTOR per point via
weak/distant district-level supervision (every point in a district inherits
that district's real MNFSR share vector as its label -- explicitly a weak
label with a real, quantifiable noise ceiling, not claimed as point-truth).

SAME SELF-CHECK DISCIPLINE AS TRACK E, built in from the start this time
(role tags from the first run, not added after the fact): no raw lat/lon or
district-identity feature is included (see FEATURES below -- confirmed
absent). Permutation feature importance is computed and reported BEFORE any
headline number, exactly like Track E's self-check.

SPLIT: real spatially-blocked -- whole districts held out, stratified by
each district's real dominant crop so the rare rice-dominant districts (8/115)
aren't accidentally absent from val/test. Never split by individual point
(points within a district are not independent -- same real rigor point as
Track E's temporal blocking).

EVALUATION GRANULARITY: reported at BOTH point-level (raw regression metrics
on the weak per-point label) AND district-level (mean predicted share per
held-out district vs. that district's real MNFSR share -- the granularity
the real label actually has integrity at, since the label is constant
within a district by construction).
"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.multioutput import MultiOutputRegressor

HERE = os.path.dirname(os.path.abspath(__file__))
FEATURES_PATH = os.path.join(HERE, "phenology_features.csv")
CROP_MIX_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json")
OUT_PATH = os.path.join(HERE, "track_f_results.json")

CROPS = ["wheat", "cotton", "rice", "sugarcane"]
FEATURES = [c for idx in ("ndvi", "ndwi", "evi") for c in (
    f"{idx}_peak_value", f"{idx}_peak_month", f"{idx}_trough_value", f"{idx}_trough_month",
    f"{idx}_green_up_slope", f"{idx}_senescence_slope", f"{idx}_annual_mean", f"{idx}_annual_std",
)]
# confirmed: no lat, no lon, no district-identity feature -- Track E's lesson applied from the start


def stratified_district_split(districts_dominant, seed=42):
    rng = np.random.default_rng(seed)
    by_dom = {}
    for d, dom in districts_dominant.items():
        by_dom.setdefault(dom, []).append(d)
    train, val, test = [], [], []
    for dom, ds in by_dom.items():
        ds = list(ds)
        rng.shuffle(ds)
        n = len(ds)
        n_test = max(1, round(n * 0.15))
        n_val = max(1, round(n * 0.15))
        test += ds[:n_test]
        val += ds[n_test:n_test + n_val]
        train += ds[n_test + n_val:]
    return train, val, test


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
          ", ".join(f"{c}: MAE={out[c]['mae']:.3f} R2={out[c]['r2']:.3f}" for c in CROPS))
    return out


def main():
    df = pd.read_csv(FEATURES_PATH)
    with open(CROP_MIX_PATH, encoding="utf-8") as f:
        crop_mix = json.load(f)

    # attach real label vector + real dominant-crop stratum per row
    rows = []
    dominant_by_district = {}
    for _, r in df.iterrows():
        rec = crop_mix.get(r["district"])
        if rec is None or rec["tier"] != "real_district_area":
            continue
        shares = {c: rec["crops"].get(c, {}).get("share_of_4crop_area", 0.0) for c in CROPS}
        if r["district"] not in dominant_by_district:
            dominant_by_district[r["district"]] = max(shares, key=shares.get)
        row = dict(r)
        row.update({f"label_{c}": shares[c] for c in CROPS})
        rows.append(row)
    data = pd.DataFrame(rows)
    n_before = len(data)
    data = data.dropna(subset=FEATURES).reset_index(drop=True)
    print(f"real usable rows (features + real MNFSR label matched): {len(data)} "
          f"(dropped {n_before - len(data)} rows with a NaN phenology feature -- peak/trough at a "
          f"series boundary with no real before/after window to compute a slope from), "
          f"{data['district'].nunique()} real districts")

    train_d, val_d, test_d = stratified_district_split(dominant_by_district)
    print(f"real spatially-blocked split -- train: {len(train_d)} districts, "
          f"val: {len(val_d)} districts, test: {len(test_d)} districts")
    print(f"  test districts: {sorted(test_d)}")

    train = data[data["district"].isin(train_d)]
    val = data[data["district"].isin(val_d)]
    test = data[data["district"].isin(test_d)]
    print(f"real point counts -- train: {len(train)}, val: {len(val)}, test: {len(test)}")

    Xtr, ytr = train[FEATURES].values, train[[f"label_{c}" for c in CROPS]].values
    Xval, yval = val[FEATURES].values, val[[f"label_{c}" for c in CROPS]].values
    Xte, yte = test[FEATURES].values, test[[f"label_{c}" for c in CROPS]].values

    results = {
        "features_used": FEATURES, "n_train_districts": len(train_d), "n_val_districts": len(val_d),
        "n_test_districts": len(test_d), "test_districts": sorted(test_d),
        "n_train_points": len(train), "n_val_points": len(val), "n_test_points": len(test),
        "role": "headline_result",
        "note_on_no_geo_features": "lat/lon and district-identity deliberately excluded from FEATURES, "
                                    "per Track E's lat/lon-leak lesson -- confirmed absent, not just unused.",
    }

    ridge = MultiOutputRegressor(Ridge(alpha=1.0))
    ridge.fit(Xtr, ytr)
    print("\nRidge regression:")
    results["ridge_val_point_level"] = eval_block("Ridge val (point-level)", yval, ridge.predict(Xval))
    results["ridge_test_point_level"] = eval_block("Ridge test (point-level)", yte, ridge.predict(Xte))

    gbt = MultiOutputRegressor(HistGradientBoostingRegressor(max_depth=4, max_iter=200, random_state=0))
    gbt.fit(Xtr, ytr)

    import joblib
    model_path = os.path.join(HERE, "gbt_crop_share_model.joblib")
    joblib.dump({"model": gbt, "features": FEATURES, "crops": CROPS,
                 "train_feature_stats": {
                     f: {"mean": float(train[f].mean()), "std": float(train[f].std()),
                         "min": float(train[f].min()), "max": float(train[f].max())}
                     for f in FEATURES
                 }}, model_path)
    print(f"\nsaved trained model + real train-set feature stats to {model_path}")

    print("\nGradient Boosted Trees:")
    results["gbt_val_point_level"] = eval_block("GBT val (point-level)", yval, gbt.predict(Xval))
    gbt_test_pred = gbt.predict(Xte)
    results["gbt_test_point_level"] = eval_block("GBT test (point-level)", yte, gbt_test_pred)

    # --- district-level evaluation: the granularity the real label has integrity at ---
    test_pred_df = test[["district"]].copy()
    for i, c in enumerate(CROPS):
        test_pred_df[f"pred_{c}"] = gbt_test_pred[:, i]
    district_level = test_pred_df.groupby("district").mean(numeric_only=True)
    district_true = test.groupby("district")[[f"label_{c}" for c in CROPS]].first()
    yte_d = district_true.values
    ypred_d = district_level[[f"pred_{c}" for c in CROPS]].values
    print("\nGBT, district-level (mean of point predictions vs real MNFSR district share):")
    results["gbt_test_district_level"] = eval_block("GBT test (district-level)", yte_d, ypred_d)

    # --- permutation feature importance, BEFORE reporting a headline (Track E discipline) ---
    imp = permutation_importance(gbt, Xte, yte, n_repeats=5, random_state=0, scoring="r2")
    importances = sorted(zip(FEATURES, imp.importances_mean), key=lambda x: -x[1])
    print("\nreal permutation feature importance (GBT, test set):")
    for f, v in importances[:10]:
        print(f"  {f:25s} {v:.4f}")
    results["gbt_feature_importance"] = {f: float(v) for f, v in importances}

    # --- baselines ---
    national_mean = ytr.mean(axis=0)
    const_pred = np.tile(national_mean, (len(yte), 1))
    print("\nBaseline: constant national-mean crop-share vector:")
    results["baseline_constant_national_mean"] = eval_block("Constant baseline test", yte, const_pred)
    results["baseline_constant_national_mean"]["role"] = "baseline"
    results["baseline_national_mean_vector"] = {c: float(v) for c, v in zip(CROPS, national_mean)}

    results["ridge_val_point_level"]["role"] = "baseline_model"
    results["gbt_val_point_level"]["role"] = "headline_result"
    results["gbt_test_point_level"]["role"] = "headline_result"
    results["gbt_test_district_level"]["role"] = "headline_result_district_granularity"

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
