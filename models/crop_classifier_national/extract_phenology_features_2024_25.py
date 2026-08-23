#!/usr/bin/env python3
"""
extract_phenology_features_2024_25.py -- Phase 4 Track J, Step 6: real
Sentinel-2 phenology features for the most recent COMPLETE real growing
season after MNFSR's last real report (2022-23) -- Nov 2024-Oct 2025, the
real season that feeds the model_estimated_interim tier. Same methodology,
same Track F points, as the 2021-22 cross-year extraction.
"""
import argparse
import json
import os

import ee
import numpy as np

MONTHS = [f"{y}-{m:02d}-01" for y, m in
          [(2024, 11), (2024, 12), (2025, 1), (2025, 2), (2025, 3), (2025, 4),
           (2025, 5), (2025, 6), (2025, 7), (2025, 8), (2025, 9), (2025, 10), (2025, 11)]]
CLOUD_MASK_SCL_EXCLUDE = [0, 1, 3, 8, 9, 10, 11]


def mask_s2_clouds(img):
    scl = img.select("SCL")
    mask = scl.remap(CLOUD_MASK_SCL_EXCLUDE, [0] * len(CLOUD_MASK_SCL_EXCLUDE), 1)
    return img.updateMask(mask)


def monthly_indices(start, end, region):
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(region).filterDate(start, end).map(mask_s2_clouds))
    composite = col.median()
    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("ndvi")
    ndwi = composite.normalizedDifference(["B3", "B8"]).rename("ndwi")
    evi = composite.expression(
        "2.5 * (NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1)",
        {"NIR": composite.select("B8"), "RED": composite.select("B4"), "BLUE": composite.select("B2")},
    ).rename("evi")
    return ee.Image.cat([ndvi, ndwi, evi])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--points", default="points.geojson")
    ap.add_argument("--out", default="phenology_features_2024_25.csv")
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
    region = fc.geometry().bounds()
    n_points = len(features)
    print(f"loaded {n_points} real points, real Nov2024-Oct2025 window")

    monthly_values = {}
    for m in range(len(MONTHS) - 1):
        start, end = MONTHS[m], MONTHS[m + 1]
        img = monthly_indices(start, end, region)
        reduced = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=10).getInfo()
        n_valid = 0
        for f in reduced["features"]:
            pid = f["properties"]["point_id"]
            ndvi = f["properties"].get("ndvi")
            ndwi = f["properties"].get("ndwi")
            evi = f["properties"].get("evi")
            monthly_values.setdefault(pid, {})[m] = {"ndvi": ndvi, "ndwi": ndwi, "evi": evi}
            if ndvi is not None:
                n_valid += 1
        print(f"  month {m+1}/{len(MONTHS)-1} ({start[:7]}): {n_valid}/{n_points} points valid")

    def phenology_stats(series, prefix):
        vals = np.array([v if v is not None else np.nan for v in series], dtype="float64")
        if np.sum(np.isfinite(vals)) < 6:
            return None
        peak_idx = int(np.nanargmax(vals))
        trough_idx = int(np.nanargmin(vals))
        peak_val = vals[peak_idx]
        trough_val = vals[trough_idx]
        before = vals[max(0, peak_idx - 3):peak_idx]
        after = vals[peak_idx + 1:peak_idx + 4]
        green_up = (peak_val - np.nanmean(before)) / 3.0 if np.sum(np.isfinite(before)) else np.nan
        senesc = (np.nanmean(after) - peak_val) / 3.0 if np.sum(np.isfinite(after)) else np.nan
        return {
            f"{prefix}_peak_value": float(peak_val), f"{prefix}_peak_month": peak_idx,
            f"{prefix}_trough_value": float(trough_val), f"{prefix}_trough_month": trough_idx,
            f"{prefix}_green_up_slope": float(green_up) if np.isfinite(green_up) else None,
            f"{prefix}_senescence_slope": float(senesc) if np.isfinite(senesc) else None,
            f"{prefix}_annual_mean": float(np.nanmean(vals)),
            f"{prefix}_annual_std": float(np.nanstd(vals)),
        }

    rows = []
    district_by_pid = {str(i): feat["properties"]["district"] for i, feat in enumerate(points_geojson["features"])}
    n_dropped = 0
    for pid, months in monthly_values.items():
        row = {"point_id": pid, "district": district_by_pid[pid]}
        ok = True
        for idx_name in ("ndvi", "ndwi", "evi"):
            series = [months.get(m, {}).get(idx_name) for m in range(len(MONTHS) - 1)]
            stats = phenology_stats(series, idx_name)
            if stats is None:
                ok = False
                break
            row.update(stats)
        if ok:
            rows.append(row)
        else:
            n_dropped += 1

    import csv
    fieldnames = list(rows[0].keys()) if rows else []
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\nreal usable rows: {len(rows)} (dropped {n_dropped})")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
