#!/usr/bin/env python3
"""
predict_interim_estimate.py -- Phase 4 Track J, Step 6: the
model_estimated_interim tier. Runs the DEPLOYED Track F model (trained on
real 2022-23 MNFSR labels, unchanged) against real Sentinel-2 phenology
features for a real growing season AFTER MNFSR's most recent real report
(2022-23) -- Nov 2024-Oct 2025, the most recent COMPLETE real season as of
this track's build -- to produce a real per-district crop-share ESTIMATE
bridging the gap until the next real government report.

REAL, EXPLICIT LIMITS ON THIS TIER, stated here and carried into the output:
  - This is a MODEL ESTIMATE, not real MNFSR data. It never overrides
    real_crop_mix.json's real_district_area tier for any district -- this
    writes to a SEPARATE file, real_crop_mix_interim_estimates.json, and
    exposure_risk.py's resolve_crop_weight() is NOT modified to consume it
    automatically (a real, deliberate non-decision -- wiring this into the
    live product is a separate call, not bundled into this track).
  - Unvalidatable until a real MNFSR report covering 2023-24/2024-25
    eventually arrives to check it against -- stated as a real, structural
    limitation of this tier, not a flaw to fix now.
  - Real, honest context for how much to trust it: Track J's own real
    cross-year validation (train2022-23->test2021-22) found wheat/cotton/
    rice R^2 in the 0.24-0.47 range at district level, real degradation
    from the original within-year 0.42-0.58 -- this interim estimate is
    real model output produced the same way, carrying the same real
    cross-year uncertainty, now projected two years past its last real
    label year instead of one.
"""
import argparse
import json
import os

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "gbt_crop_share_model.joblib")
CROP_MIX_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json")
OUT_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix_interim_estimates.json")

CROPS = ["wheat", "cotton", "rice", "sugarcane"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="phenology_features_2024_25.csv")
    ap.add_argument("--season-label", default="2024-25")
    a = ap.parse_args()

    bundle = joblib.load(MODEL_PATH)
    model, features = bundle["model"], bundle["features"]
    print(f"loaded deployed Track F model (trained on real 2022-23 MNFSR labels, unchanged)")

    df = pd.read_csv(a.features)
    n_before = len(df)
    df = df.dropna(subset=features).reset_index(drop=True)
    print(f"real {a.season_label} features: {len(df)}/{n_before} usable points, "
          f"{df['district'].nunique()} districts")

    with open(CROP_MIX_PATH, encoding="utf-8") as f:
        real_crop_mix = json.load(f)

    X = df[features].values
    pred = model.predict(X)
    for i, c in enumerate(CROPS):
        df[f"pred_{c}"] = pred[:, i]

    district_level = df.groupby("district")[[f"pred_{c}" for c in CROPS]].mean()

    out = {}
    n_negative_flagged = 0
    for district, row in district_level.iterrows():
        shares = {c: float(row[f"pred_{c}"]) for c in CROPS}
        any_negative = any(v < 0 for v in shares.values())
        if any_negative:
            n_negative_flagged += 1
        real_tier = real_crop_mix.get(district, {}).get("tier")
        out[district] = {
            "tier": "model_estimated_interim",
            "season": a.season_label,
            "source": f"Track F's deployed GBT crop-share model (trained on real 2022-23 MNFSR "
                      f"labels, unchanged) applied to real Sentinel-2 phenology features for "
                      f"{a.season_label} -- a MODEL ESTIMATE, not real MNFSR data. Unvalidatable "
                      "until a real MNFSR report covering this season arrives. Never overrides "
                      f"real_crop_mix.json's real_district_area tier (this district's real "
                      f"authoritative tier there: {real_tier}).",
            "predicted_shares": shares,
            "flagged_negative_share": any_negative,
            "n_real_s2_points": int((df["district"] == district).sum()),
        }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"\nreal model_estimated_interim tier: {len(out)} districts, "
          f"{n_negative_flagged} with an impossible negative predicted share (flagged, kept, "
          "not silently clamped)")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
