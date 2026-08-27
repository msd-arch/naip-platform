#!/usr/bin/env python3
"""
investigate_9district_anomaly.py -- Track I follow-up: pull the full real
feature values (SAR VV/VH during+change, JRC occurrence, precip_total_mm,
precip_anomaly_pct) for the 9 districts replay_live_screen_v3.py flagged
(>=0.5 v3 score) in the 2026-07-28..08-27 live window, and compare each
against the real national mean, to check whether the model is using real
SAR/JRC wetness signal sensibly for these districts (cases 1/2) or whether
this looks like genuine confusion on a spurious feature combination (case 3).

Uses the EXACT same live window/points replay_live_screen_v3.py used (same
during/pre windows read from its own output, same seed=42 point generation)
so the per-point features are directly comparable to that run's scores.
"""
import argparse
import json
import os

import ee
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")
REPLAY_PATH = os.path.join(HERE, "track_i_v3_live_replay.json")
OUT_PATH = os.path.join(HERE, "track_i_v3_9district_investigation.json")

N_PER_DISTRICT = 15
CHIRPS_ID = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_SCALE = 5500
CLIMATOLOGY_YEARS = list(range(2001, 2021))

FLAGGED_9 = [
    "Gujrat", "Islamabad Capital Territory", "Abbottabad", "Rawalpindi",
    "Jhelum", "Sialkot", "Narowal", "Azad Kashmir", "Haripur",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()

    with open(REPLAY_PATH, encoding="utf-8") as f:
        replay = json.load(f)
    during_start, during_end = replay["during_window"]
    pre_start, pre_end = replay["pre_monsoon_baseline_window"]
    print(f"reusing the exact live windows from track_i_v3_live_replay.json: "
          f"during {during_start}..{during_end}, pre {pre_start}..{pre_end}")

    ee.Initialize(project=a.project)

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {feat["properties"]["shapeName"]: feat["geometry"] for feat in districts_geojson["features"]}

    s1 = ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)

    # Real points for the 9 flagged districts (for their own detailed feature
    # values) PLUS a real random 20-district national sample (for a percentile-
    # rank reference distribution) -- NOT all 126 districts, which timed out
    # GEE's reduceRegions with the 20-year climatology stack. 20 districts is
    # enough for a real, useful (if coarser) percentile reference.
    import random as _random
    _rng = _random.Random(7)
    reference_sample = _rng.sample(sorted(set(by_name.keys()) - set(FLAGGED_9)), 20)
    target_districts = FLAGGED_9 + reference_sample
    print(f"real reference sample (20 random non-flagged districts, seed=7): {reference_sample}")

    all_points = []
    for name in target_districts:
        geom = by_name[name]
        pts = ee.FeatureCollection.randomPoints(region=ee.Geometry(geom), points=N_PER_DISTRICT, seed=42)
        info = pts.getInfo()
        for feat in info["features"]:
            lon, lat = feat["geometry"]["coordinates"]
            all_points.append({"district": name, "lat": lat, "lon": lon})
    print(f"real points regenerated (9 flagged + 20 reference districts): {len(all_points)}")

    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]), {"point_id": str(i)})
        for i, p in enumerate(all_points)
    ])
    region = fc.geometry().bounds()

    def s1_composite(start, end):
        col = s1.filterBounds(region).filterDate(start, end)
        return col.select(["VV", "VH"]).median()

    during_img = s1_composite(during_start, during_end)
    pre_img = s1_composite(pre_start, pre_end)

    md_start, md_end = during_start[5:], during_end[5:]
    chirps = ee.ImageCollection(CHIRPS_ID).select("precipitation")
    current_precip = chirps.filterDate(during_start, during_end).sum().rename("precip_total_mm")
    yearly_sums = []
    for y in CLIMATOLOGY_YEARS:
        y_start, y_end = f"{y}-{md_start}", f"{y}-{md_end}"
        if md_end < md_start:
            y_end = f"{y + 1}-{md_end}"
        yearly_sums.append(chirps.filterDate(y_start, y_end).sum())
    hist_mean_img = ee.ImageCollection(yearly_sums).mean().rename("hist_mean_precip_mm")

    combined = ee.Image.cat([
        during_img.rename(["VV_during", "VH_during"]),
        pre_img.rename(["VV_pre", "VH_pre"]),
        jrc.rename("jrc_occurrence"),
        current_precip, hist_mean_img,
    ])

    print("running real reduceRegions over all national points (SAR/JRC + precipitation)...")
    reduced = combined.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30).getInfo()
    by_pid = {feat["properties"]["point_id"]: feat["properties"] for feat in reduced["features"]}

    per_point = []
    for i, p in enumerate(all_points):
        props = by_pid.get(str(i), {})
        vv_d, vh_d = props.get("VV_during"), props.get("VH_during")
        vv_p, vh_p = props.get("VV_pre"), props.get("VH_pre")
        jrc_occ = props.get("jrc_occurrence")
        precip_total = props.get("precip_total_mm")
        hist_mean = props.get("hist_mean_precip_mm")
        if None in (vv_d, vh_d, vv_p, vh_p, jrc_occ, precip_total, hist_mean):
            continue
        precip_anom = ((precip_total - hist_mean) / hist_mean * 100.0) if hist_mean > 1e-6 else 0.0
        per_point.append({
            "district": p["district"], "VV_during": vv_d, "VH_during": vh_d,
            "VV_change": vv_p - vv_d, "VH_change": vh_p - vh_d,
            "jrc_occurrence": jrc_occ, "precip_total_mm": precip_total,
            "hist_mean_precip_mm": hist_mean, "precip_anomaly_pct": precip_anom,
        })
    print(f"real usable points: {len(per_point)}/{len(all_points)}")

    FIELDS = ["VV_during", "VH_during", "VV_change", "VH_change", "jrc_occurrence",
              "precip_total_mm", "precip_anomaly_pct"]
    national = {f: np.array([pt[f] for pt in per_point]) for f in FIELDS}
    national_mean = {f: float(national[f].mean()) for f in FIELDS}

    by_district = {}
    for pt in per_point:
        by_district.setdefault(pt["district"], []).append(pt)

    def district_means(name):
        pts = by_district.get(name, [])
        return {f: float(np.mean([p[f] for p in pts])) for f in FIELDS} if pts else None

    def percentile_rank(field, value):
        return float((national[field] < value).mean() * 100)

    print("\n=== the 9 flagged districts, real feature values vs. real 29-district reference sample ===")
    results = {}
    for name in FLAGGED_9:
        m = district_means(name)
        if m is None:
            print(f"{name}: NO real points found -- skipping")
            continue
        pct = {f: round(percentile_rank(f, m[f]), 1) for f in FIELDS}
        results[name] = {"means": {f: round(m[f], 3) for f in FIELDS}, "reference_sample_percentile": pct}
        print(f"\n{name}:")
        for f in FIELDS:
            direction = "high" if pct[f] >= 66 else "low" if pct[f] <= 33 else "mid"
            print(f"  {f:20s} = {m[f]:8.3f}   (reference-sample percentile {pct[f]:5.1f}, {direction})")

    print(f"\n=== real reference-sample means (9 flagged + 20 random other districts), for context ===")
    for f in FIELDS:
        print(f"  {f:20s} = {national_mean[f]:.3f}")

    out = {
        "during_window": [during_start, during_end], "pre_window": [pre_start, pre_end],
        "flagged_9_districts": results, "reference_sample_mean": national_mean,
        "reference_sample_districts": reference_sample,
        "n_reference_points": len(per_point),
        "caveat": "Percentiles are against a real 29-district sample (the 9 flagged + 20 random "
                  "others), not the full 126-district national distribution -- an earlier full-"
                  "national attempt timed out GEE's reduceRegions with the 20-year climatology "
                  "stack. Useful as a real, honest reference, not a precise national percentile.",
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
