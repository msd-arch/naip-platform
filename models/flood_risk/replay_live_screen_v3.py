#!/usr/bin/env python3
"""
replay_live_screen_v3.py -- Track I, precipitation attempt, Step 7: replay
Week 11/Track I's live national screening approach against REAL CURRENT
conditions, scoring with the ORIGINAL, v2, and v3 (precipitation-augmented)
models side by side -- does adding real precipitation produce a more
plausible live result than the original's 122/126 or v2's suppressed scores?

Same real feature construction as replay_live_screen_v2.py for SAR/JRC (15
real points/district, live during-window = last 30 real days, vs. this
year's real pre-monsoon dry baseline), PLUS real live CHIRPS precipitation:
total rainfall over that same live during-window, and the anomaly against
each point's real 20-year (2001-2020) climatological mean for the SAME
calendar day-range (a rolling comparison, since "last 30 days" itself rolls
forward -- the calendar window compared against history always matches
today's actual live window, not a fixed August date).

REAL, EXPLICIT CAUTION carried over from Track I's original finding: a
better-looking live-replay number alone is not evidence of a real fix --
Track I's v2 attempt looked better live (122->29) purely from global score
suppression, caught only by the fair 2024 test. This script's result is
reported alongside, never instead of, eval_2024_full_v3.py's fair test.
"""
import argparse
import datetime
import json
import os

import ee
import joblib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")
OUT_PATH = os.path.join(HERE, "track_i_v3_live_replay.json")

N_PER_DISTRICT = 15
FLAG_THRESHOLD = 0.5
CHIRPS_ID = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_SCALE = 5500
CLIMATOLOGY_YEARS = list(range(2001, 2021))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()

    today = datetime.date.today()
    during_end = today.isoformat()
    during_start = (today - datetime.timedelta(days=30)).isoformat()
    pre_start = f"{today.year}-03-01"
    pre_end = f"{today.year}-04-15"
    print(f"real live during-window: {during_start}..{during_end}")
    print(f"real pre-monsoon dry baseline: {pre_start}..{pre_end}")

    ee.Initialize(project=a.project)

    orig_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier.joblib"))
    v2_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier_v2_2021neg.joblib"))
    v3_bundle = joblib.load(os.path.join(HERE, "gbt_flood_classifier_v3_precip_fulltrain.joblib"))
    orig_features = orig_bundle["features"]
    v3_features = v3_bundle["features"]
    assert orig_features == v2_bundle["features"]

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {feat["properties"]["shapeName"]: feat["geometry"] for feat in districts_geojson["features"]}

    s1 = ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)

    all_points = []
    for i, (name, geom) in enumerate(sorted(by_name.items())):
        pts = ee.FeatureCollection.randomPoints(region=ee.Geometry(geom), points=N_PER_DISTRICT, seed=42)
        info = pts.getInfo()
        for feat in info["features"]:
            lon, lat = feat["geometry"]["coordinates"]
            all_points.append({"district": name, "lat": lat, "lon": lon})
        if (i + 1) % 25 == 0 or i == len(by_name) - 1:
            print(f"[{i + 1}/{len(by_name)}] sampled points through {name}")

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

    # real live precipitation: current total + rolling 20-year same-calendar-range climatology
    md_start, md_end = during_start[5:], during_end[5:]
    chirps = ee.ImageCollection(CHIRPS_ID).select("precipitation")
    current_precip = chirps.filterDate(during_start, during_end).sum().rename("precip_total_mm")
    yearly_sums = []
    for y in CLIMATOLOGY_YEARS:
        # handle a during-window that spans a year boundary (Dec->Jan) the same
        # way every year in the climatology, using the SAME month-day range
        y_start, y_end = f"{y}-{md_start}", f"{y}-{md_end}"
        if md_end < md_start:  # window wraps New Year's -- shift the end year forward
            y_end = f"{y + 1}-{md_end}"
        yearly_sums.append(chirps.filterDate(y_start, y_end).sum())
    hist_mean_img = ee.ImageCollection(yearly_sums).mean().rename("hist_mean_precip_mm")

    combined = ee.Image.cat([
        during_img.rename(["VV_during", "VH_during"]),
        pre_img.rename(["VV_pre", "VH_pre"]),
        jrc.rename("jrc_occurrence"),
        current_precip, hist_mean_img,
    ])

    print("running real reduceRegions over all live points (SAR/JRC + precipitation)...")
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
            "district": p["district"],
            "VV_during": vv_d, "VH_during": vh_d,
            "VV_change": vv_p - vv_d, "VH_change": vh_p - vh_d,
            "jrc_occurrence": jrc_occ,
            "precip_total_mm": precip_total, "precip_anomaly_pct": precip_anom,
        })
    print(f"real usable live points: {len(per_point)}/{len(all_points)}")

    X_orig = np.array([[pt[f] for f in orig_features] for pt in per_point])
    X_v3 = np.array([[pt[f] for f in v3_features] for pt in per_point])
    orig_scores = orig_bundle["model"].predict_proba(X_orig)[:, 1]
    v2_scores = v2_bundle["model"].predict_proba(X_orig)[:, 1]
    v3_scores = v3_bundle["model"].predict_proba(X_v3)[:, 1]
    for pt, so, sv, s3 in zip(per_point, orig_scores, v2_scores, v3_scores):
        pt["orig_score"] = round(float(so), 4)
        pt["v2_score"] = round(float(sv), 4)
        pt["v3_score"] = round(float(s3), 4)

    by_district = {}
    for pt in per_point:
        by_district.setdefault(pt["district"], []).append(pt)

    district_results = []
    for name in sorted(by_name.keys()):
        pts = by_district.get(name, [])
        if not pts:
            continue
        district_results.append({
            "district": name, "n_points": len(pts),
            "orig_mean_score": round(float(np.mean([p["orig_score"] for p in pts])), 4),
            "v2_mean_score": round(float(np.mean([p["v2_score"] for p in pts])), 4),
            "v3_mean_score": round(float(np.mean([p["v3_score"] for p in pts])), 4),
            "mean_precip_anomaly_pct": round(float(np.mean([p["precip_anomaly_pct"] for p in pts])), 2),
        })

    def summarize(key):
        vals = [d[key] for d in district_results]
        n_flagged = sum(1 for v in vals if v >= FLAG_THRESHOLD)
        return n_flagged, float(np.mean(vals)), float(min(vals)), float(max(vals))

    n_o, mean_o, min_o, max_o = summarize("orig_mean_score")
    n_v2, mean_v2, min_v2, max_v2 = summarize("v2_mean_score")
    n_v3, mean_v3, min_v3, max_v3 = summarize("v3_mean_score")

    print(f"\nreal live national result:")
    print(f"  ORIGINAL model: {n_o}/{len(district_results)} flagged, mean {mean_o:.4f}, range [{min_o:.4f}, {max_o:.4f}]")
    print(f"  V2 model:       {n_v2}/{len(district_results)} flagged, mean {mean_v2:.4f}, range [{min_v2:.4f}, {max_v2:.4f}]")
    print(f"  V3 model:       {n_v3}/{len(district_results)} flagged, mean {mean_v3:.4f}, range [{min_v3:.4f}, {max_v3:.4f}]")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "during_window": [during_start, during_end],
        "pre_monsoon_baseline_window": [pre_start, pre_end],
        "flag_threshold": FLAG_THRESHOLD,
        "n_districts_total": len(district_results),
        "original_model": {"n_flagged": n_o, "mean_score": mean_o, "min_score": min_o, "max_score": max_o},
        "v2_model": {"n_flagged": n_v2, "mean_score": mean_v2, "min_score": min_v2, "max_score": max_v2},
        "v3_model": {"n_flagged": n_v3, "mean_score": mean_v3, "min_score": min_v3, "max_score": max_v3},
        "district_results": district_results,
        "caution_note": "A better-looking live-replay number alone is not evidence of a real "
                         "fix -- v2 looked better live (122->29) purely from global score "
                         "suppression, caught only by the fair 2024 labeled test "
                         "(track_i_v3_2024_full_eval.json). Read this alongside that file, not "
                         "instead of it.",
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
