#!/usr/bin/env python3
"""
predict_flood_risk_live.py -- Phase 3 Track D integration: run the trained
Track D flood classifier (gbt_flood_classifier.joblib, STATUS_WEEK10.md) on
REAL CURRENT Sentinel-1/JRC data for all 126 real districts, not the frozen
2022 training window.

REAL ARCHITECTURAL DIFFERENCE FROM TRACK E'S INTEGRATION (Week 9/Track G),
stated explicitly because it drove a design choice below: Track E's fire
model is bound to a fixed historical MSG archive (Nov 2023) -- it can only
ever replay that past event. Track D's inputs (Sentinel-1 via GEE, JRC) are
live and continuously updating, the same as the locust monitor's SMAP/NDVI
inputs. This script is a genuine live national screen of REAL CURRENT
conditions, not a replay.

WHY THIS IS A STANDALONE SCRIPT, NOT A HOOK INSIDE hazards.py'S PER-15-MIN
FRAME LOOP: Sentinel-1 revisit over Pakistan is on the order of days, not
15 minutes -- querying GEE once per MSG frame would be architecturally wrong
(thousands of redundant identical calls) and slow. This is the same real
reason the locust-breeding-risk monitor (6.6) was never folded into
hazards.py either -- it is a standalone module with its own output file,
consumed by prepare_data.py the same way. merge_into_district_alerts.py
(same folder) is the piece that reuses district_alerts.json's existing
row schema so this still "flows into district_alerts.json ... without a
bespoke format," per the actual requirement -- just via a merge step
rather than a live per-frame call.

FEATURE CONSTRUCTION: identical to sample_and_extract.py (VV_during,
VH_during, VV_change, VH_change, jrc_occurrence; same N_PER_DISTRICT=15,
same random-point seed pattern) -- reused, not reinvented, so the live
inputs sit on the same distribution the model was trained on.

HONESTY DISCIPLINE (same as every prior track, same as the locust monitor's
three prior honest "no risk flagged" results): this script reports whatever
the real current data says. It does not assume active flooding just because
it is monsoon season, and it does not suppress a real positive score if one
appears.
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
MODEL_PATH = os.path.join(HERE, "gbt_flood_classifier.joblib")
OUT_PATH = os.path.join(HERE, "flood_risk_live_national.json")

N_PER_DISTRICT = 15  # same as sample_and_extract.py / training

# Real caveats carried forward from STATUS_WEEK10.md, surfaced on every record,
# not just in this docstring.
CAVEAT_TRAINING_WINDOW = (
    "Trained on a single real disaster window (Aug-Sep 2022) and not validated "
    "against a second real flood event -- same single-window caveat every "
    "other Phase 3 track carries."
)
CAVEAT_JRC = (
    "Track D's own permutation-importance check found jrc_occurrence contributes "
    "almost nothing to the model (0.0012 importance) -- the permanent-water "
    "baseline discounting it was included to provide may not be doing what it "
    "was designed to do. Score is driven mainly by real SAR backscatter change."
)

# Rule threshold from train_flood_classifier.py, applied here too for a live
# rule-vs-model comparison consistent with Track G's fire-model precedent.
RULE_VV_THRESHOLD_DB = -17.0
RULE_JRC_THRESHOLD_PCT = 5.0

FLAG_THRESHOLD = 0.5  # same probability cutoff Track G used for the fire model


def rule_flag(vv_during, jrc_occ):
    return bool(vv_during < RULE_VV_THRESHOLD_DB and jrc_occ < RULE_JRC_THRESHOLD_PCT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--during-start", default=None,
                     help="default: 30 real days before --during-end")
    ap.add_argument("--during-end", default=None,
                     help="default: today (UTC), real current date")
    ap.add_argument("--pre-start", default=None,
                     help="default: this year's real pre-monsoon dry baseline, Mar 1")
    ap.add_argument("--pre-end", default=None,
                     help="default: this year's real pre-monsoon dry baseline, Apr 15")
    ap.add_argument("--out", default=OUT_PATH)
    a = ap.parse_args()

    today = datetime.date.today()
    during_end = a.during_end or today.isoformat()
    during_start = a.during_start or (today - datetime.timedelta(days=30)).isoformat()
    pre_start = a.pre_start or f"{today.year}-03-01"
    pre_end = a.pre_end or f"{today.year}-04-15"

    print(f"real live during-window: {during_start}..{during_end}")
    print(f"real pre-monsoon dry baseline: {pre_start}..{pre_end}")

    ee.Initialize(project=a.project)

    bundle = joblib.load(MODEL_PATH)
    model, features = bundle["model"], bundle["features"]
    print(f"loaded real trained model: {bundle['role']}, features={features}")

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

    print(f"\nreal total live points sampled: {len(all_points)}")

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

    print("running real reduceRegions over all live points (single real composite image)...")
    reduced = combined.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30).getInfo()
    by_pid = {feat["properties"]["point_id"]: feat["properties"] for feat in reduced["features"]}

    per_point = []
    n_dropped = 0
    for i, p in enumerate(all_points):
        props = by_pid.get(str(i), {})
        vv_d, vh_d = props.get("VV_during"), props.get("VH_during")
        vv_p, vh_p = props.get("VV_pre"), props.get("VH_pre")
        jrc_occ = props.get("jrc_occurrence")
        if None in (vv_d, vh_d, vv_p, vh_p, jrc_occ):
            n_dropped += 1
            continue
        per_point.append({
            "district": p["district"], "lat": p["lat"], "lon": p["lon"],
            "VV_during": vv_d, "VH_during": vh_d,
            "VV_change": vv_p - vv_d, "VH_change": vh_p - vh_d,
            "jrc_occurrence": jrc_occ,
        })

    print(f"real usable live points: {len(per_point)} (dropped {n_dropped} with missing real S1/JRC data)")

    X = np.array([[pt[f] for f in features] for pt in per_point])
    scores = model.predict_proba(X)[:, 1]
    for pt, sc in zip(per_point, scores):
        pt["model_score"] = round(float(sc), 4)
        pt["rule_flag"] = rule_flag(pt["VV_during"], pt["jrc_occurrence"])

    by_district = {}
    for pt in per_point:
        by_district.setdefault(pt["district"], []).append(pt)

    district_results = []
    for name in sorted(by_name.keys()):
        pts = by_district.get(name, [])
        if not pts:
            district_results.append({
                "district": name, "n_points": 0, "mean_model_score": None,
                "frac_points_flagged": None, "n_rule_flagged": 0, "flag": False,
                "note": "no real usable Sentinel-1/JRC points this run (data gap, not zero risk)",
            })
            continue
        mean_score = float(np.mean([pt["model_score"] for pt in pts]))
        frac_flagged = float(np.mean([pt["model_score"] >= FLAG_THRESHOLD for pt in pts]))
        n_rule = sum(1 for pt in pts if pt["rule_flag"])
        # district centroid, same convention as pk_districts.geojson consumers elsewhere
        lats = [pt["lat"] for pt in pts]
        lons = [pt["lon"] for pt in pts]
        district_results.append({
            "district": name, "n_points": len(pts),
            "mean_model_score": round(mean_score, 4),
            "frac_points_flagged": round(frac_flagged, 4),
            "n_rule_flagged": n_rule,
            "flag": bool(mean_score >= FLAG_THRESHOLD),
            "lat": round(float(np.mean(lats)), 4), "lon": round(float(np.mean(lons)), 4),
        })

    n_flagged = sum(1 for d in district_results if d["flag"])
    scored = [d for d in district_results if d["mean_model_score"] is not None]
    top5 = sorted(scored, key=lambda d: -d["mean_model_score"])[:5]

    print(f"\nreal live national result: {n_flagged}/126 districts flagged "
          f"(mean_model_score >= {FLAG_THRESHOLD})")
    print("top 5 real district scores (whatever they are, not curated):")
    for d in top5:
        print(f"  {d['district']:20s} mean_model_score={d['mean_model_score']:.4f} "
              f"n_rule_flagged={d['n_rule_flagged']}/{d['n_points']}")

    out = {
        "generated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": "Phase 3 Track D integration -- real live national Sentinel-1/JRC screen "
                "using the trained Week 10 flood classifier. Unlike Track E's fire model "
                "(bound to a fixed 2023 historical archive), this reflects real current "
                "conditions as of the generation timestamp above, not a replay.",
        "during_window": [during_start, during_end],
        "pre_monsoon_baseline_window": [pre_start, pre_end],
        "flag_threshold": FLAG_THRESHOLD,
        "n_districts_flagged": n_flagged,
        "n_districts_total": len(district_results),
        "n_districts_no_data": sum(1 for d in district_results if d["n_points"] == 0),
        "caveats": [CAVEAT_TRAINING_WINDOW, CAVEAT_JRC],
        "district_results": district_results,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
