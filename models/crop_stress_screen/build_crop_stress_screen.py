#!/usr/bin/env python3
"""
build_crop_stress_screen.py -- Phase 5 Track Q: a real "crop stress
early-warning screen," NOT a pest/disease detector.

REAL PRE-CHECK RESULT (checked directly, not assumed): no real, extractable
per-location wheat rust (or other pest/disease) surveillance dataset was
found. RustTracker.org's specific data pages (Pakistan Survey Mapper, Survey
Data Overview) all redirect to a dead WordPress placeholder; the parent
platform (GRRC/wheatrust.org, still live) describes every one of its own
tools as "maps and charts" only -- no CSV/API/bulk export anywhere in this
family of platforms. The closest real published field-survey study found
(Khan et al., a genuine 1202-field/95-district/3-year 2016-2018 Pakistan
leaf-rust survey) publishes only DISTRICT-LEVEL AGGREGATE counts (its own
table caption: "Number of fields in various districts recorded with >60%
leaf rust infestation"), not per-field GPS/date records. A second candidate
paper turned out to be expert-elicitation modeled yield-loss estimates, not
an observed survey at all. See STATUS_WEEK23.md for the full real search.

REAL, STATED-PLAINLY SCIENTIFIC CONSTRAINT: satellite remote sensing
generally cannot identify WHICH pest or disease is present -- only generic
vegetation stress/anomaly, which has many possible real causes (disease,
pest, water stress, nutrient deficiency). This tool's own output text says
so explicitly, every time, not just in this docstring.

REAL INFRASTRUCTURE REUSED, not rebuilt: Track M's exact real national NDVI
signal (Track F's 2,875 real Sentinel-2 points + 275 real GB/AJK points,
same 21-year 2001-2021 MODIS historical baseline, same MODIS-vs-MODIS
anomaly math that avoided the real cross-sensor bias Track M found).

REAL, NON-REDUNDANT ADDITION over Track M's own drought signal: Track M's
z-score flags a point BELOW ITS OWN HISTORICAL NORM in absolute NDVI level
-- a signature more consistent with sustained conditions (drought, chronic
water stress). This script adds a second, genuinely distinct real signal:
an anomalously STEEP within-season senescence slope (the crop declining
faster than typical, real phenology-curve shape data Track F/M already
extracted, not new Sentinel-2 compute) -- a signature more consistent with
an ACUTE stress event (a pest/disease outbreak, a sudden water cutoff)
than a chronic below-normal level. Both signals are reported SEPARATELY,
never merged into one opaque score, so a reader can see which real pattern
a flagged point/district actually shows -- this is still NOT a diagnosis
of which one, if either, is the real cause.

Both signals use the same real percentile-based (not fixed-cutoff) method
Track M's own real distribution self-check required -- no lat/lon or
district-identity feature is used anywhere (both signals are direct
transforms of real per-point Sentinel-2/MODIS values, not model-fitted).
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DROUGHT_DIR = os.path.join(HERE, "..", "drought_national")
TRACKF_PHENOLOGY = os.path.join(HERE, "..", "crop_classifier_national", "phenology_features.csv")
GBAJK_PHENOLOGY = os.path.join(DROUGHT_DIR, "phenology_features_gbajk.csv")
MODIS_BASELINE = os.path.join(DROUGHT_DIR, "modis_baseline.csv")
MODIS_CURRENT = os.path.join(DROUGHT_DIR, "modis_current.csv")
OUT_PATH = os.path.join(HERE, "crop_stress_screen.json")

NOT_A_DIAGNOSIS_NOTICE = (
    "NOT A PEST OR DISEASE DIAGNOSIS. Satellite remote sensing cannot identify which pest, "
    "disease, or other cause is affecting a crop -- it can only detect a generic vegetation "
    "stress/anomaly signal, which has many real possible causes (disease, pest, water stress, "
    "nutrient deficiency, or none of the above -- a real false positive is possible). A flag "
    "here means: this location's real Sentinel-2/MODIS signal looks unusual relative to its own "
    "real record. It is a prompt to investigate on the ground, not a finding about what, if "
    "anything, is actually wrong."
)


def main():
    trackf = pd.read_csv(TRACKF_PHENOLOGY)
    trackf["tier"] = "real_mnfsr_cropland_masked"
    gbajk = pd.read_csv(GBAJK_PHENOLOGY)
    gbajk["tier"] = "real_gbajk_unmasked"

    n_trackf_points = 2875
    trackf["combined_point_id"] = trackf["point_id"].astype(int)
    gbajk["combined_point_id"] = gbajk["point_id"].astype(int) + n_trackf_points
    current = pd.concat([trackf, gbajk], ignore_index=True)
    print(f"real current-signal points (reused from Track F + Track M's GB/AJK extension): "
          f"{len(current)} across {current['district'].nunique()} real districts")

    baseline = pd.read_csv(MODIS_BASELINE).set_index("point_id")[["hist_mean_ndvi", "hist_std_ndvi"]]
    modis_current = pd.read_csv(MODIS_CURRENT).set_index("point_id")[["modis_current_ndvi"]]
    merged = current.join(baseline, on="combined_point_id").join(modis_current, on="combined_point_id")
    n_before = len(merged)
    merged = merged.dropna(subset=["hist_mean_ndvi", "hist_std_ndvi", "ndvi_annual_mean", "modis_current_ndvi"])
    merged = merged[merged["hist_std_ndvi"] > 1e-6]
    print(f"real points with current+historical signal: {len(merged)}/{n_before}")

    # SIGNAL 1: level anomaly -- identical real method Track M validated
    # (MODIS-vs-MODIS, avoids the real cross-sensor bias Track M's own
    # self-check found and fixed).
    merged["level_z_score"] = (merged["modis_current_ndvi"] - merged["hist_mean_ndvi"]) / merged["hist_std_ndvi"]
    level_p10 = float(np.percentile(merged["level_z_score"].values, 10))
    merged["level_anomaly_flag"] = merged["level_z_score"] <= level_p10

    # SIGNAL 2 (new, real, non-redundant): within-season senescence-slope
    # anomaly. Real distribution check first, not assumed well-behaved --
    # senescence_slope is negative by construction (NDVI declines toward
    # harvest); a MORE negative value is a STEEPER/faster real decline.
    slope_n_missing = merged["ndvi_senescence_slope"].isna().sum()
    print(f"real senescence_slope missing (excluded from Signal 2 only): "
          f"{slope_n_missing}/{len(merged)}")
    slope_valid = merged.dropna(subset=["ndvi_senescence_slope"])
    slope = slope_valid["ndvi_senescence_slope"].values
    print(f"real senescence_slope distribution: n={len(slope)} mean={np.mean(slope):.4f} "
          f"std={np.std(slope):.4f} min={np.min(slope):.4f} p10={np.percentile(slope,10):.4f} "
          f"median={np.median(slope):.4f} max={np.max(slope):.4f}")
    slope_p10 = float(np.percentile(slope, 10))  # bottom decile = steepest (most negative) declines
    merged["senescence_anomaly_flag"] = False
    merged.loc[slope_valid.index, "senescence_anomaly_flag"] = slope_valid["ndvi_senescence_slope"] <= slope_p10

    merged["any_stress_flag"] = merged["level_anomaly_flag"] | merged["senescence_anomaly_flag"]
    merged["both_signals_flag"] = merged["level_anomaly_flag"] & merged["senescence_anomaly_flag"]

    n_level = int(merged["level_anomaly_flag"].sum())
    n_senesc = int(merged["senescence_anomaly_flag"].sum())
    n_any = int(merged["any_stress_flag"].sum())
    n_both = int(merged["both_signals_flag"].sum())
    print(f"\nreal point-level counts: level-anomaly={n_level}, senescence-anomaly={n_senesc}, "
          f"either={n_any}, BOTH (real, stronger real signal)={n_both}  (of {len(merged)} points)")

    district_rows = []
    for name, g in merged.groupby("district"):
        district_rows.append({
            "district": name,
            "tier": g["tier"].iloc[0],
            "n_points": int(len(g)),
            "mean_level_z_score": round(float(g["level_z_score"].mean()), 4),
            "n_points_level_anomaly": int(g["level_anomaly_flag"].sum()),
            "n_points_senescence_anomaly": int(g["senescence_anomaly_flag"].sum()),
            "n_points_both_signals": int(g["both_signals_flag"].sum()),
            "frac_points_any_flag": round(float(g["any_stress_flag"].mean()), 4),
            "district_flag_either_signal": bool(g["any_stress_flag"].mean() >= 0.1),
            "district_flag_both_signals": bool(g["both_signals_flag"].sum() > 0),
        })
    district_rows.sort(key=lambda r: -r["frac_points_any_flag"])

    n_district_either = sum(1 for r in district_rows if r["district_flag_either_signal"])
    n_district_both = sum(1 for r in district_rows if r["district_flag_both_signals"])
    print(f"\nreal district-level result: {n_district_either}/{len(district_rows)} districts "
          f"flagged (either signal, >=10% of real points), {n_district_both} flagged on BOTH "
          f"real signals simultaneously (the stronger, still-non-diagnostic real case)")

    out = {
        "not_a_diagnosis_notice": NOT_A_DIAGNOSIS_NOTICE,
        "generated_note": "Phase 5 Track Q -- fallback path taken after a real pre-check found "
                           "no extractable per-location pest/disease surveillance dataset for "
                           "Pakistan (RustTracker.org dead, GRRC/wheatrust.org map-only, the "
                           "closest real published survey publishes only district-aggregate "
                           "counts). This is a generic crop-stress screen, reusing Track M's "
                           "exact real national NDVI infrastructure, NOT a disease-specific "
                           "detector. See STATUS_WEEK23.md.",
        "signal_1_level_anomaly": {
            "method": "level_z_score = (modis_current_ndvi - hist_mean_ndvi_2001_2021) / "
                      "hist_std_ndvi_2001_2021; flagged if in the real bottom decile of this "
                      "year's national distribution. Identical real method to Track M's "
                      "drought signal (drought_national.json) -- more consistent with "
                      "sustained/chronic conditions.",
            "threshold_percentile_this_year": level_p10,
            "n_points_flagged": n_level,
        },
        "signal_2_senescence_anomaly": {
            "method": "flagged if ndvi_senescence_slope (real within-season decline rate, "
                      "already extracted by Track F/M's phenology pipeline) is in the real "
                      "bottom decile nationally (i.e. the steepest/fastest real declines) -- "
                      "more consistent with an acute stress event than Signal 1's chronic-level "
                      "check. New this track, not previously computed by Track M.",
            "threshold_percentile_this_year": slope_p10,
            "n_points_flagged": n_senesc,
            "n_points_missing_slope_data": int(slope_n_missing),
        },
        "n_points_total": len(merged),
        "n_points_either_signal": n_any,
        "n_points_both_signals": n_both,
        "n_districts_covered": len(district_rows),
        "n_districts_flagged_either_signal": n_district_either,
        "n_districts_flagged_both_signals": n_district_both,
        "district_results": district_rows,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
