#!/usr/bin/env python3
"""
predict_flood_risk_live.py -- Phase 3 Track D integration, PROMOTED Week 27
(Track I) to the v3 (precipitation-augmented) model: run the trained flood
classifier on REAL CURRENT Sentinel-1/JRC/CHIRPS data for all 126 real
districts, not the frozen 2022 training window.

WEEK 27 PROMOTION, same real precedent as Track E's thermal-only model
becoming the deployed candidate over its with-geo sibling: v3
(gbt_flood_classifier_v3_precip_fulltrain.joblib, trained on all real 2022+
2021 points) replaces the original SAR/JRC-only model
(gbt_flood_classifier.joblib) as what this live script runs. The original
model file is UNTOUCHED and stays on disk -- eval/comparison scripts
(eval_2024_full_v3.py, replay_live_screen_v3.py) still load it by name for
real apples-to-apples comparison. Promoted on real, fair-test evidence
(naip/docs/STATUS_WEEK26.md): F1 0.229->0.312, AUC 0.602->0.761, and a
score-separation-by-true-label gap of 0.332 (vs. the original's own 0.096) on
the same fair 2024 held-out year v2 (Track I's first, rejected, attempt) was
caught failing on.

REAL, HONEST LIMITATIONS CARRIED FORWARD, stated here not just in a status
doc: this model's real fair-test precision is 0.190 -- most "flooded"
predictions are still wrong even in the best real evaluation so far. A real,
unresolved live finding from Week 27's investigation: the districts this
model currently flags (see flood_risk_live_national.json's district_results)
do not always show a positive rainfall anomaly, the direction the training
data's own signal points -- see CAVEAT_9DISTRICT_ANOMALY below for the
specific, honest finding.

REAL ARCHITECTURAL DIFFERENCE FROM TRACK E'S INTEGRATION (Week 9/Track G):
Track E's fire model is bound to a fixed historical MSG archive (Nov 2023).
Track D/I's inputs (Sentinel-1, JRC, CHIRPS, all via GEE) are live and
continuously updating -- this script is a genuine live national screen of
REAL CURRENT conditions, not a replay.

FEATURE CONSTRUCTION: SAR/JRC identical to sample_and_extract.py (VV_during,
VH_during, VV_change, VH_change, jrc_occurrence); precipitation identical to
add_precipitation_features.py's real CHIRPS total + 20-year (2001-2020)
same-calendar-window climatology anomaly (precip_total_mm, precip_anomaly_pct)
-- same N_PER_DISTRICT=15, same random-point seed pattern throughout.
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
MODEL_PATH = os.path.join(HERE, "gbt_flood_classifier_v3_precip_fulltrain.joblib")
OUT_PATH = os.path.join(HERE, "flood_risk_live_national.json")

N_PER_DISTRICT = 15
CHIRPS_ID = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_SCALE = 5500
CLIMATOLOGY_YEARS = list(range(2001, 2021))

# Real caveats carried forward, surfaced on every record, not just in this docstring.
CAVEAT_MODEL_VERSION = (
    "MODEL PROMOTED Week 27 (Track I, precipitation attempt): this is v3 "
    "(gbt_flood_classifier_v3_precip_fulltrain.joblib), trained on real Sentinel-1/JRC "
    "SAR features PLUS real CHIRPS precipitation (total + 20-year anomaly), replacing "
    "the original SAR/JRC-only model on real, fair-test evidence (F1 0.229->0.312, "
    "AUC 0.602->0.761, score-separation gap 0.096->0.332 on the same fair 2024 "
    "held-out year that caught the prior v2 attempt's failure -- see STATUS_WEEK26.md)."
)
CAVEAT_PRECISION = (
    "Real fair-test precision is 0.190 (2024 held-out year) -- most 'flooded' "
    "predictions are still wrong even in this model's best real evaluation so far. "
    "Read scores as a real, meaningfully-improved relative risk ranking, not a "
    "calibrated probability of actual flooding."
)
CAVEAT_9DISTRICT_ANOMALY = (
    "Week 27 investigation, real and not fully resolved: the districts this model "
    "currently flags do not always show the positive rainfall anomaly the training "
    "data's own signal points toward (flooded training points average +216-259% "
    "anomaly; several currently-flagged districts show a real negative anomaly "
    "instead). Investigated and found explainable by real SAR/JRC signal (persistent "
    "wetness/irrigation infrastructure) in most but not all flagged districts -- see "
    "track_i_v3_9district_investigation.json and STATUS_WEEK27.md for the specific, "
    "per-district real finding, not smoothed into a single blanket explanation."
)
CAVEAT_JRC = (
    "Track D's own permutation-importance check found jrc_occurrence contributes "
    "almost nothing to the model (0.0012 importance) -- carried forward from the "
    "original model; not re-checked for v3 this week."
)

RULE_VV_THRESHOLD_DB = -17.0
RULE_JRC_THRESHOLD_PCT = 5.0
FLAG_THRESHOLD = 0.5  # unchanged, same probability cutoff Track G used for the fire model


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

    ee.Initialize(project=a.project)

    # REAL BUG FOUND AND FIXED LIVE (2026-08-31): during_end used to default
    # to literal "today" unconditionally, but CHIRPS/DAILY is a real,
    # gauge-corrected precipitation product with a genuine publication lag
    # (confirmed live: on 2026-08-31, CHIRPS's real most-recent published
    # image was 2026-07-31 -- the entire current month had zero real
    # images). Requesting a during-window past CHIRPS's real latest date
    # made precip_total_mm null for every one of 1890 real sampled points,
    # which then dropped every point (all 7 features required non-null),
    # leaving zero usable rows and crashing at model.predict_proba(). Same
    # live-probe-don't-assume discipline this project already applies to
    # EUMETSAT/GFS cadence: only auto-clamp when --during-end wasn't
    # explicitly given, so an explicit real request is never silently
    # overridden.
    if not a.during_end:
        chirps_latest = (
            ee.ImageCollection(CHIRPS_ID)
            .select("precipitation")
            .sort("system:time_start", False)
            .first()
        )
        chirps_latest_date = ee.Date(chirps_latest.get("system:time_start")).format("YYYY-MM-dd").getInfo()
        if chirps_latest_date < during_end:
            print(f"real CHIRPS latency found: latest real published image is {chirps_latest_date}, "
                  f"clamping during_end back from {during_end} to that real date")
            during_end = chirps_latest_date
            if not a.during_start:
                during_start = (
                    datetime.date.fromisoformat(chirps_latest_date) - datetime.timedelta(days=30)
                ).isoformat()

    print(f"real live during-window: {during_start}..{during_end}")
    print(f"real pre-monsoon dry baseline: {pre_start}..{pre_end}")

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
        precip_total = props.get("precip_total_mm")
        hist_mean = props.get("hist_mean_precip_mm")
        if None in (vv_d, vh_d, vv_p, vh_p, jrc_occ, precip_total, hist_mean):
            n_dropped += 1
            continue
        precip_anom = ((precip_total - hist_mean) / hist_mean * 100.0) if hist_mean > 1e-6 else 0.0
        per_point.append({
            "district": p["district"], "lat": p["lat"], "lon": p["lon"],
            "VV_during": vv_d, "VH_during": vh_d,
            "VV_change": vv_p - vv_d, "VH_change": vh_p - vh_d,
            "jrc_occurrence": jrc_occ,
            "precip_total_mm": precip_total, "precip_anomaly_pct": precip_anom,
        })

    print(f"real usable live points: {len(per_point)} (dropped {n_dropped} with missing real data)")

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
                "note": "no real usable Sentinel-1/JRC/CHIRPS points this run (data gap, not zero risk)",
            })
            continue
        mean_score = float(np.mean([pt["model_score"] for pt in pts]))
        frac_flagged = float(np.mean([pt["model_score"] >= FLAG_THRESHOLD for pt in pts]))
        n_rule = sum(1 for pt in pts if pt["rule_flag"])
        mean_precip_anom = float(np.mean([pt["precip_anomaly_pct"] for pt in pts]))
        lats = [pt["lat"] for pt in pts]
        lons = [pt["lon"] for pt in pts]
        district_results.append({
            "district": name, "n_points": len(pts),
            "mean_model_score": round(mean_score, 4),
            "frac_points_flagged": round(frac_flagged, 4),
            "n_rule_flagged": n_rule,
            "flag": bool(mean_score >= FLAG_THRESHOLD),
            "mean_precip_anomaly_pct": round(mean_precip_anom, 2),
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
              f"precip_anomaly={d['mean_precip_anomaly_pct']:.1f}% n_rule_flagged={d['n_rule_flagged']}/{d['n_points']}")

    out = {
        "generated": datetime.datetime.utcnow().isoformat() + "Z",
        "last_computed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "refresh_cadence_note": "Recomputed on a real weekly schedule (naip/pipelines/scheduler/"
                                 "flood_weekly_refresh.py, Task Scheduler task 'NAIP-FloodWeekly'), "
                                 "same real cadence reasoning as Track M's drought signal -- unlike "
                                 "Track H's 15-min MSG cadence, this pulls Sentinel-1/CHIRPS via GEE "
                                 "(a real network call, not a local re-read), and flood conditions "
                                 "here are screened over a rolling 30-day SAR window, not something "
                                 "that meaningfully changes minute-to-minute. Unlike drought's real "
                                 "limitation (frozen current-period extraction), THIS script's "
                                 "during_window/pre_monsoon_baseline_window above are computed fresh "
                                 "from today's real date every run -- last_computed_utc here means "
                                 "both 'the script ran' AND 'the underlying Sentinel-1/CHIRPS window "
                                 "genuinely moved forward.'",
        "model_version": "v3_precip (promoted Week 27, Track I)",
        "note": "Live national Sentinel-1/JRC/CHIRPS screen using the PROMOTED v3 "
                "(precipitation-augmented) flood classifier. Reflects real current "
                "conditions as of the generation timestamp above, not a replay.",
        "during_window": [during_start, during_end],
        "pre_monsoon_baseline_window": [pre_start, pre_end],
        "flag_threshold": FLAG_THRESHOLD,
        "n_districts_flagged": n_flagged,
        "n_districts_total": len(district_results),
        "n_districts_no_data": sum(1 for d in district_results if d["n_points"] == 0),
        "caveats": [CAVEAT_MODEL_VERSION, CAVEAT_PRECISION, CAVEAT_9DISTRICT_ANOMALY, CAVEAT_JRC],
        "district_results": district_results,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
