#!/usr/bin/env python3
"""
backtest_locust_thresholds.py -- Phase 2 Track B: real historical backtest of
locust_breeding_risk.py's SM-anomaly/NDVI-greenup thresholds against real FAO
Desert Locust Hub observation records for Pakistan.

GROUND TRUTH: data.apps.fao.org "Desert Locusts Observations" dataset (CC-BY,
no login required). VERIFIED FINDING, not assumed: the "_2020" extract is a
STATIC snapshot covering only 2020-01-01..2020-05-10 (the tail of the real
2019-2021 upsurge), not a rolling "since 2020" window as an earlier automated
page summary claimed -- checked the actual downloaded CSVs directly. FAO uses
country code "PA" for Pakistan in this dataset (verified via real Pakistani
place names + in-Pakistan lat/lon, not the ISO "PK" one might expect).

Used HOPPER + BAND records only (not adults/swarms) because these are the
categories that directly confirm successful local breeding (egg-laying ->
hatching -> hopper) at that location, which is what the SM/NDVI thresholds
are meant to predict -- adults/swarms represent migratory presence, not
necessarily local breeding.

METHOD: for each real confirmed event, run the exact same logic
locust_breeding_risk.py uses in real-time mode, with the event's own
observation date substituted as "asof" -- recent 30d window ending at the
event date, prior 30d window before that, same SMAP L4 + Sentinel-2 NDVI
sources, same reduce scale. This tests: "if this algorithm had been running
in real time, would it have flagged breeding risk in the window immediately
preceding this real confirmed event?"

SAMPLE SIZE CAVEAT (stated plainly, not smoothed over): 291 distinct
week x 0.3deg location clusters exist in the real PK hopper+band records.
This script systematically samples a subset (default stride-based, evenly
spread across the real Jan-May 2020 date range) to keep GEE query volume
practical -- the exact N actually run is reported in the output JSON, not
just claimed here.
"""
import argparse
import datetime as dt
import json

import ee

SM_ANOMALY_FAVORABLE = 0.02
NDVI_GREENUP_DELTA = 0.03


def mask_s2_clouds(img):
    scl = img.select("SCL")
    mask = scl.remap([0, 1, 3, 8, 9, 10, 11], [0, 0, 0, 0, 0, 0, 0], 1)
    return img.updateMask(mask)


def mean_ndvi(s2, geom, start, end):
    col = s2.filterBounds(geom).filterDate(start, end).map(mask_s2_clouds)
    composite = col.median()
    ndvi = composite.normalizedDifference(["B8", "B4"])
    val = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=100,
                             maxPixels=1e9, bestEffort=True).get("nd")
    return val


def evaluate_event(smap, s2, lat, lon, asof_str, buffer_m=15000):
    now = dt.datetime.strptime(asof_str, "%Y-%m-%d")
    recent_start = (now - dt.timedelta(days=30)).strftime("%Y-%m-%d")
    recent_end = now.strftime("%Y-%m-%d")
    prior_start = (now - dt.timedelta(days=60)).strftime("%Y-%m-%d")
    prior_end = recent_start

    geom = ee.Geometry.Point([lon, lat]).buffer(buffer_m)

    sm_recent = smap.filterDate(recent_start, recent_end).select(
        ["sm_surface", "sm_surface_anomaly"]).mean()
    sm_vals = sm_recent.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=11000,
                                      maxPixels=1e9, bestEffort=True).getInfo()

    ndvi_recent = mean_ndvi(s2, geom, recent_start, recent_end).getInfo()
    ndvi_prior = mean_ndvi(s2, geom, prior_start, prior_end).getInfo()
    ndvi_delta = (ndvi_recent - ndvi_prior) if (ndvi_recent is not None and ndvi_prior is not None) else None

    sm_anomaly = sm_vals.get("sm_surface_anomaly")
    sm_surface = sm_vals.get("sm_surface")

    soil_favorable = sm_anomaly is not None and sm_anomaly >= SM_ANOMALY_FAVORABLE
    greenup = ndvi_delta is not None and ndvi_delta >= NDVI_GREENUP_DELTA
    flag = bool(soil_favorable and greenup)
    data_complete = sm_anomaly is not None and ndvi_delta is not None

    return {
        "window_recent": [recent_start, recent_end],
        "window_prior": [prior_start, prior_end],
        "sm_surface_anomaly_m3m3": round(sm_anomaly, 4) if sm_anomaly is not None else None,
        "ndvi_delta": round(ndvi_delta, 3) if ndvi_delta is not None else None,
        "soil_favorable": soil_favorable,
        "vegetation_greenup": greenup,
        "would_have_flagged": flag,
        "data_complete": data_complete,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--events", default="../../data/locust_ground_truth/pk_locust_events_2020.json")
    ap.add_argument("--out", default="../../data/locust_ground_truth/backtest_results.json")
    ap.add_argument("--stride", type=int, default=6,
                     help="take every Nth event from the sorted real event list, to cap GEE query volume")
    ap.add_argument("--buffer_m", type=int, default=15000)
    a = ap.parse_args()

    ee.Initialize(project=a.project)
    smap = ee.ImageCollection("NASA/SMAP/SPL4SMGP/008")
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")

    with open(a.events, encoding="utf-8") as f:
        all_events = json.load(f)
    all_events.sort(key=lambda e: e["date"])
    sample = all_events[::a.stride]

    print(f"real distinct PK hopper/band event clusters available: {len(all_events)}")
    print(f"sampling every {a.stride}th -> running backtest on {len(sample)} real events")

    results = []
    n_flagged = 0
    n_complete = 0
    for i, ev in enumerate(sample):
        try:
            r = evaluate_event(smap, s2, ev["lat"], ev["lon"], ev["date"], a.buffer_m)
        except Exception as e:
            r = {"error": str(e), "data_complete": False, "would_have_flagged": False}
        rec = {**ev, **r}
        results.append(rec)
        if rec.get("data_complete"):
            n_complete += 1
            if rec["would_have_flagged"]:
                n_flagged += 1
        print(f"[{i+1}/{len(sample)}] {ev['date']} {ev['sample_location_name']!r} "
              f"cats={ev['categories']} -> flagged={rec.get('would_have_flagged')} "
              f"complete={rec.get('data_complete')} sm_anom={r.get('sm_surface_anomaly_m3m3')} "
              f"ndvi_delta={r.get('ndvi_delta')}")

    hit_rate = (n_flagged / n_complete) if n_complete else None

    out = {
        "generated": dt.datetime.utcnow().isoformat(),
        "ground_truth_source": "FAO Desert Locusts Observations (data.apps.fao.org, CC-BY, no login), "
                                "hopper+band records, Country ISO2 Code == 'PA' (verified = Pakistan via "
                                "real place names/coordinates), real static extract 2020-01-01..2020-05-10 "
                                "(the tail of the real 2019-2021 upsurge -- NOT a rolling since-2020 window, "
                                "that was a wrong initial assumption corrected by checking the actual file).",
        "n_real_distinct_event_clusters_available": len(all_events),
        "n_sampled_and_run": len(sample),
        "stride": a.stride,
        "n_data_complete": n_complete,
        "n_would_have_flagged": n_flagged,
        "hit_rate_existing_thresholds": round(hit_rate, 3) if hit_rate is not None else None,
        "thresholds_tested": {"sm_anomaly_favorable": SM_ANOMALY_FAVORABLE, "ndvi_greenup_delta": NDVI_GREENUP_DELTA},
        "caveat": "Small real sample (see n_sampled_and_run) from a single real upsurge episode -- "
                  "do not over-generalize a threshold recalibration from this alone.",
        "events": results,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nn_complete={n_complete} n_flagged={n_flagged} hit_rate={hit_rate}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
