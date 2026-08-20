#!/usr/bin/env python3
"""
locust_breeding_risk.py -- Desert Locust breeding-risk monitor (module 6.6)
for the three named breeding grounds in architecture.md: Cholistan,
Tharparkar, Kharan.

METHODOLOGY (real, standard FAO Desert Locust Information Service logic, not
invented for this project): locust breeding needs (a) soil wet enough for
egg-laying, and (b) green vegetation for hopper survival after hatching. Both
signals are pulled from real satellite/reanalysis products:
  - soil moisture: NASA SMAP L4 (SPL4SMGP v008), sm_surface + the product's
    own built-in sm_surface_anomaly band (real anomaly vs. NASA's own
    climatology, not computed here).
  - vegetation green-up: real Sentinel-2 NDVI, same cloud-masked monthly
    approach as Week 2's crop classifier, current vs. a prior-month baseline.

BOUNDARY NOTE -- verified before assuming, same discipline as districts/
canals in prior weeks:
  - Tharparkar and Kharan are real Pakistani administrative districts and
    already exist as real polygons in naip/data/seed/pk_districts.geojson
    (Week 1's geoBoundaries ADM2 set) -- used directly, no approximation.
  - "Cholistan" is a desert region, not an administrative unit -- checked
    OSM (Overpass, name~Cholistan across relation/way/node) and found ZERO
    features. No official Cholistan boundary exists anywhere accessible.
    Real-world geographic knowledge places the Cholistan Desert within
    Punjab's Bahawalpur, Bahawalnagar, and Rahim Yar Khan districts -- all
    three ARE real polygons in pk_districts.geojson, so their union is used
    as a labeled coarse proxy region, not an invented bounding box. This
    substantially overstates Cholistan's true extent (it doesn't cover the
    full area of all three districts) -- flagged in every output record.

TIME WINDOW: real-time monitoring, so this uses the most recent 30 real days
of data available (not tied to the 2026-06-22..07-20 MSG archive used
elsewhere in this project -- SMAP/Sentinel-2 are independent, current data
sources).

Usage:
    python locust_breeding_risk.py --project printtheory \
        --districts ../../data/seed/pk_districts.geojson --out locust_risk.json
"""
import argparse
import datetime as dt
import json

import ee


REGIONS_FROM_DISTRICTS = {
    "Tharparkar": {"districts": ["Tharparkar"], "boundary_type": "real_district"},
    "Kharan": {"districts": ["Kharan"], "boundary_type": "real_district"},
    "Cholistan": {"districts": ["Bahawalpur", "Bahawalnagar", "Rahim Yar Khan"],
                  "boundary_type": "proxy_district_union"},
}

# RECALIBRATED Phase 2 Week 5, against real ground truth (was: standard FAO
# DLIS-style qualitative bands, not fitted to any local data -- see git
# history for the original SM_ANOMALY_FAVORABLE=0.02/NDVI_GREENUP_DELTA=0.03
# pair). Real backtest: 49 real confirmed PK hopper/band events from the FAO
# Desert Locusts Observations dataset (data.apps.fao.org, CC-BY), real 2020
# upsurge tail (Jan-May 2020, the only window in the open extract), same
# SMAP+Sentinel-2 method run with each event's own date substituted as
# "asof". Original thresholds (SM>=0.02 AND NDVI delta>=0.03) would have
# flagged only 3/49 (6.1%) of these real events -- NDVI delta was the
# binding constraint: real median NDVI delta AT the real events was -0.011
# (vegetation slightly browning, not greening) in these arid breeding
# regions, not the cropland-style green-up the original threshold assumed.
# SM alone at >=0.02 catches 22/49 (44.9%) but dropping the vegetation
# check entirely has UNKNOWN false-positive cost -- this backtest only has
# real positive events, no real confirmed-absence cases, so precision/
# false-alarm rate cannot be estimated from it, only recall. Relaxing (not
# dropping) NDVI delta to -0.05 -- i.e. "not visibly browning much", not
# "greening" -- raises the real hit rate to 12/49 (24.5%), a real 4x
# improvement over the original 6.1%, while still requiring some
# vegetation signal. See naip/data/locust_ground_truth/backtest_results.json
# for the full real per-event data this was calibrated against.
SM_ANOMALY_FAVORABLE = 0.02    # m3/m3 above SMAP's own climatological mean -- unchanged, real backtest supports it
NDVI_GREENUP_DELTA = -0.05     # recent-30d mean NDVI minus prior-30d mean NDVI -- relaxed from 0.03


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--districts", default="../../data/seed/pk_districts.geojson")
    ap.add_argument("--out", default="locust_risk.json")
    ap.add_argument("--asof", default=None, help="ISO date to treat as 'now' (default: today)")
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(a.districts, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {f["properties"]["shapeName"]: f["geometry"] for f in districts_geojson["features"]}

    now = dt.datetime.fromisoformat(a.asof) if a.asof else dt.datetime.utcnow()
    recent_start = (now - dt.timedelta(days=30)).strftime("%Y-%m-%d")
    recent_end = now.strftime("%Y-%m-%d")
    prior_start = (now - dt.timedelta(days=60)).strftime("%Y-%m-%d")
    prior_end = recent_start

    print(f"as-of: {now:%Y-%m-%d}  recent window: {recent_start}..{recent_end}  "
          f"prior window: {prior_start}..{prior_end}")

    smap = ee.ImageCollection("NASA/SMAP/SPL4SMGP/008")
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")

    def mask_s2_clouds(img):
        scl = img.select("SCL")
        mask = scl.remap([0, 1, 3, 8, 9, 10, 11], [0, 0, 0, 0, 0, 0, 0], 1)
        return img.updateMask(mask)

    def mean_ndvi(geom, start, end):
        col = s2.filterBounds(geom).filterDate(start, end).map(mask_s2_clouds)
        composite = col.median()
        ndvi = composite.normalizedDifference(["B8", "B4"])
        val = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=100,
                                 maxPixels=1e9, bestEffort=True).get("nd")
        return val

    results = []
    for region_name, cfg in REGIONS_FROM_DISTRICTS.items():
        geoms = [ee.Geometry(by_name[d]) for d in cfg["districts"] if d in by_name]
        missing = [d for d in cfg["districts"] if d not in by_name]
        if missing:
            print(f"WARNING: {region_name}: district(s) not found in boundary set: {missing}")
        if not geoms:
            print(f"SKIP {region_name}: no real boundary geometry available")
            continue
        geom = geoms[0]
        for g in geoms[1:]:
            geom = geom.union(g, 1)

        sm_recent = smap.filterDate(recent_start, recent_end).select(
            ["sm_surface", "sm_surface_anomaly"]).mean()
        sm_vals = sm_recent.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=11000,
                                          maxPixels=1e9, bestEffort=True).getInfo()

        ndvi_recent = mean_ndvi(geom, recent_start, recent_end).getInfo()
        ndvi_prior = mean_ndvi(geom, prior_start, prior_end).getInfo()
        ndvi_delta = (ndvi_recent - ndvi_prior) if (ndvi_recent is not None and ndvi_prior is not None) else None

        sm_anomaly = sm_vals.get("sm_surface_anomaly")
        sm_surface = sm_vals.get("sm_surface")

        soil_favorable = sm_anomaly is not None and sm_anomaly >= SM_ANOMALY_FAVORABLE
        greenup = ndvi_delta is not None and ndvi_delta >= NDVI_GREENUP_DELTA
        flag = bool(soil_favorable and greenup)
        # confidence: both real signals present and clearly over threshold -> higher;
        # any missing input -> 0, same "no data, no flag" discipline as hazards.py
        if sm_anomaly is None or ndvi_delta is None:
            conf = 0.0
        else:
            conf = 0.35 + (0.3 if soil_favorable else 0.0) + (0.3 if greenup else 0.0)

        results.append({
            "region": region_name,
            "boundary_type": cfg["boundary_type"],
            "boundary_note": (
                "real district polygon(s) from geoBoundaries ADM2" if cfg["boundary_type"] == "real_district"
                else "NO official Cholistan boundary exists anywhere accessible (checked OSM, zero results) -- "
                     "this is the real-geometry union of the 3 Punjab districts (Bahawalpur, Bahawalnagar, "
                     "Rahim Yar Khan) reported to contain the Cholistan Desert, NOT a Cholistan-specific "
                     "boundary. Substantially overstates true desert extent."
            ),
            "window_recent": [recent_start, recent_end],
            "window_prior": [prior_start, prior_end],
            "sm_surface_m3m3": round(sm_surface, 4) if sm_surface is not None else None,
            "sm_surface_anomaly_m3m3": round(sm_anomaly, 4) if sm_anomaly is not None else None,
            "ndvi_recent_30d": round(ndvi_recent, 3) if ndvi_recent is not None else None,
            "ndvi_prior_30d": round(ndvi_prior, 3) if ndvi_prior is not None else None,
            "ndvi_delta": round(ndvi_delta, 3) if ndvi_delta is not None else None,
            "soil_favorable_for_egglaying": soil_favorable,
            "vegetation_not_browning": greenup,  # renamed from vegetation_greenup_detected (Phase 2 recalibration:
                                                   # threshold is now -0.05, i.e. "not markedly browning", not true green-up
            "breeding_risk_flag": flag,
            "confidence": round(conf, 2),
            "source": "NASA SMAP L4 SPL4SMGP v008 (real, ~11km, own built-in anomaly) + "
                      "Sentinel-2 SR Harmonized NDVI (real, cloud-masked, 100m reduce scale)",
        })
        print(f"{region_name}: sm_anomaly={sm_anomaly}, ndvi_delta={ndvi_delta}, "
              f"flag={flag}, conf={conf:.2f}")

    out = {
        "generated": now.isoformat(),
        "scope": (
            "Real-time desert-locust breeding-risk screen using real SMAP soil-moisture-anomaly "
            "and real Sentinel-2 NDVI signal, standard FAO DLIS-style logic. Thresholds "
            "(SM anomaly >= 0.02 m3/m3, NDVI delta >= -0.05) were RECALIBRATED in Phase 2 Week 5 "
            "against a real backtest of 49 confirmed PK hopper/band events from the FAO Desert "
            "Locusts Observations dataset (2020 upsurge tail, Jan-May 2020) -- the original "
            "NDVI delta >= 0.03 'green-up' requirement only caught 3/49 (6.1%) of real events "
            "because real median NDVI delta at confirmed events was -0.011 (slightly browning, "
            "not greening, in these arid regions); relaxed to -0.05 raises real recall to 12/49 "
            "(24.5%). NOTE: this backtest only had real positive events, no real confirmed-absence "
            "cases, so it validates recall only -- false-alarm rate/precision is still unvalidated. "
            "Cholistan has no official boundary anywhere (see per-region boundary_note) -- proxy "
            "geometry substantially overstates true desert extent."
        ),
        "regions": results,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
