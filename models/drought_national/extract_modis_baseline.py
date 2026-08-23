#!/usr/bin/env python3
"""
extract_modis_baseline.py -- Phase 4 Track M: real historical NDVI baseline
per point, from MODIS MOD13Q1 (250m, 16-day composite, real record confirmed
back to Feb 2000 via GEE before building anything against it).

WHY MODIS FOR THE BASELINE, NOT SENTINEL-2: a trend-deviation drought signal
needs a real multi-year history to compare against, not just the current
season. Sentinel-2's own usable Pakistan record only starts ~2015-2017 --
too thin (7-8 years) for a defensible climatology. MODIS's real ~24-year
record (2001-2021 used here, 21 years, deliberately excluding 2022-23 --
the current/test period Track F's Sentinel-2 features cover -- so the
baseline and the current-year observation are never the same data) is the
appropriate real source for this specific purpose. The CURRENT signal stays
real Sentinel-2 at 10m (reused directly from Track F's already-extracted
phenology_features.csv) -- MODIS is used only for historical context, not
as the primary observation, so real resolution at the current observation
is not degraded.

Real, efficient design: builds 21 real yearly-mean-NDVI images server-side
(one per real year, 2001-2021), then reduces ONCE over all real points --
not 21 separate downloads.

Usage:
    python extract_modis_baseline.py --project printtheory \
        --points combined_points.geojson --out modis_baseline.csv
"""
import argparse
import json
import os

import ee

HERE = os.path.dirname(os.path.abspath(__file__))
HIST_YEARS = list(range(2001, 2022))  # 21 real years, excludes 2022-23 (the current period)
MODIS_NDVI_SCALE = 0.0001  # real MOD13Q1 scale factor, raw -2000..10000 -> -0.2..1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--points", required=True, help="combined national points geojson")
    ap.add_argument("--out", default=os.path.join(HERE, "modis_baseline.csv"))
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(a.points, encoding="utf-8") as f:
        points_geojson = json.load(f)
    features = []
    for i, feat in enumerate(points_geojson["features"]):
        lon, lat = feat["geometry"]["coordinates"]
        features.append(ee.Feature(ee.Geometry.Point([lon, lat]),
                                    {"point_id": str(i), "district": feat["properties"]["district"]}))
    fc = ee.FeatureCollection(features)
    n_points = len(features)
    print(f"loaded {n_points} real national points")

    modis = ee.ImageCollection("MODIS/061/MOD13Q1").select("NDVI")

    yearly_mean_imgs = []
    for y in HIST_YEARS:
        yearly_col = modis.filterDate(f"{y}-01-01", f"{y}-12-31")
        yearly_mean = yearly_col.mean().multiply(MODIS_NDVI_SCALE)
        yearly_mean_imgs.append(yearly_mean)
    stack = ee.ImageCollection(yearly_mean_imgs)
    baseline_mean = stack.mean().rename("hist_mean_ndvi")
    baseline_std = stack.reduce(ee.Reducer.stdDev()).rename("hist_std_ndvi")
    combined = ee.Image.cat([baseline_mean, baseline_std])

    print(f"running real reduceRegions over {n_points} points, {len(HIST_YEARS)} real historical "
          f"years ({HIST_YEARS[0]}-{HIST_YEARS[-1]}) aggregated server-side...")
    reduced = combined.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=250).getInfo()

    rows = []
    n_dropped = 0
    for feat in reduced["features"]:
        props = feat["properties"]
        hm, hs = props.get("hist_mean_ndvi"), props.get("hist_std_ndvi")
        if hm is None or hs is None:
            n_dropped += 1
            continue
        rows.append({"point_id": props["point_id"], "district": props["district"],
                      "hist_mean_ndvi": hm, "hist_std_ndvi": hs})

    import csv
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["point_id", "district", "hist_mean_ndvi", "hist_std_ndvi"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\nreal usable rows: {len(rows)} (dropped {n_dropped} with no real MODIS coverage)")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
