#!/usr/bin/env python3
"""
replay_live_screen_v2.py -- Phase 4 Track I, Step 6: replay Week 11's live
national screening approach against REAL CURRENT conditions, scoring with
BOTH the original Track D model and the v2 (2021-expanded) candidate model
side by side -- the real point of this track: does the retrained model
correctly distinguish ordinary conditions from flood-level signal, instead
of the 122/126 over-flagging Week 11 found?

Same real feature construction as predict_flood_risk_live.py (Week 11):
15 real points/district, live during-window (last 30 real days) vs. this
year's real pre-monsoon dry baseline.
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
OUT_PATH = os.path.join(HERE, "track_i_live_replay.json")

N_PER_DISTRICT = 15
FLAG_THRESHOLD = 0.5


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
    features = orig_bundle["features"]
    assert features == v2_bundle["features"]

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
    combined = ee.Image.cat([
        during_img.rename(["VV_during", "VH_during"]),
        pre_img.rename(["VV_pre", "VH_pre"]),
        jrc.rename("jrc_occurrence"),
    ])

    print("running real reduceRegions over all live points...")
    reduced = combined.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30).getInfo()
    by_pid = {feat["properties"]["point_id"]: feat["properties"] for feat in reduced["features"]}

    per_point = []
    for i, p in enumerate(all_points):
        props = by_pid.get(str(i), {})
        vv_d, vh_d = props.get("VV_during"), props.get("VH_during")
        vv_p, vh_p = props.get("VV_pre"), props.get("VH_pre")
        jrc_occ = props.get("jrc_occurrence")
        if None in (vv_d, vh_d, vv_p, vh_p, jrc_occ):
            continue
        per_point.append({
            "district": p["district"],
            "VV_during": vv_d, "VH_during": vh_d,
            "VV_change": vv_p - vv_d, "VH_change": vh_p - vh_d,
            "jrc_occurrence": jrc_occ,
        })
    print(f"real usable live points: {len(per_point)}")

    X = np.array([[pt[f] for f in features] for pt in per_point])
    orig_scores = orig_bundle["model"].predict_proba(X)[:, 1]
    v2_scores = v2_bundle["model"].predict_proba(X)[:, 1]
    for pt, so, sv in zip(per_point, orig_scores, v2_scores):
        pt["orig_score"] = round(float(so), 4)
        pt["v2_score"] = round(float(sv), 4)

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
        })

    n_orig_flagged = sum(1 for d in district_results if d["orig_mean_score"] >= FLAG_THRESHOLD)
    n_v2_flagged = sum(1 for d in district_results if d["v2_mean_score"] >= FLAG_THRESHOLD)
    orig_scores_all = [d["orig_mean_score"] for d in district_results]
    v2_scores_all = [d["v2_mean_score"] for d in district_results]

    print(f"\nreal live national result:")
    print(f"  ORIGINAL model: {n_orig_flagged}/{len(district_results)} districts flagged, "
          f"mean score {np.mean(orig_scores_all):.4f}, range [{min(orig_scores_all):.4f}, {max(orig_scores_all):.4f}]")
    print(f"  V2 model:       {n_v2_flagged}/{len(district_results)} districts flagged, "
          f"mean score {np.mean(v2_scores_all):.4f}, range [{min(v2_scores_all):.4f}, {max(v2_scores_all):.4f}]")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "during_window": [during_start, during_end],
        "pre_monsoon_baseline_window": [pre_start, pre_end],
        "flag_threshold": FLAG_THRESHOLD,
        "n_districts_total": len(district_results),
        "original_model": {
            "n_flagged": n_orig_flagged,
            "mean_score": float(np.mean(orig_scores_all)),
            "min_score": float(min(orig_scores_all)), "max_score": float(max(orig_scores_all)),
        },
        "v2_model": {
            "n_flagged": n_v2_flagged,
            "mean_score": float(np.mean(v2_scores_all)),
            "min_score": float(min(v2_scores_all)), "max_score": float(max(v2_scores_all)),
        },
        "district_results": district_results,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
