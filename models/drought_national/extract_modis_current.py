#!/usr/bin/env python3
"""
extract_modis_current.py -- Phase 4 Track M follow-up fix: real MODIS
current-period NDVI (same 2022-11..2023-10 window as Track F's Sentinel-2
extraction), same sensor/resolution as the historical baseline.

WHY THIS WAS NEEDED (found via the real degenerate-collapse check in
compute_drought_signal.py, not assumed clean): comparing 10m Sentinel-2
current values directly against 250m MODIS historical values gave a real
z-score distribution centered at +1.31, not ~0 -- a real cross-sensor/
cross-resolution bias (fine-resolution, often cropland-focused points read
systematically greener than coarse-resolution area averages around the same
point), not a genuine 20-year national greening signal. Real fix: compute
the anomaly using MODIS-vs-MODIS (same sensor, same resolution, no cross-
sensor bias) for the actual z-score math; Sentinel-2's real fine-resolution
value stays in the output as the real farm-level display value (that is
what genuinely fixes the "dominated by non-farm land" spatial problem, not
the anomaly statistic itself).
"""
import argparse
import json
import os

import ee

HERE = os.path.dirname(os.path.abspath(__file__))
MODIS_NDVI_SCALE = 0.0001


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--points", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "modis_current.csv"))
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
    print(f"loaded {len(features)} real national points")

    modis = ee.ImageCollection("MODIS/061/MOD13Q1").select("NDVI")
    current_img = modis.filterDate("2022-11-01", "2023-11-01").mean().multiply(MODIS_NDVI_SCALE)

    reduced = current_img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=250).getInfo()
    rows = []
    n_dropped = 0
    for feat in reduced["features"]:
        props = feat["properties"]
        v = props.get("mean")
        if v is None:
            n_dropped += 1
            continue
        rows.append({"point_id": props["point_id"], "district": props["district"], "modis_current_ndvi": v})

    import csv
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["point_id", "district", "modis_current_ndvi"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"real usable rows: {len(rows)} (dropped {n_dropped})")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
