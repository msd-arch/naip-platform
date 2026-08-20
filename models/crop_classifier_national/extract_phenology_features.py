#!/usr/bin/env python3
"""
extract_phenology_features.py -- Phase 3 Track F, Step 3: real
NDVI/NDWI/EVI phenology-curve features per sampled point, a genuinely richer
feature set than Week 2's flat monthly means (per PHASE3_MODEL_PLAN.md).

Real monthly cloud-masked Sentinel-2 composites, Nov 2022 - Oct 2023 (12
real months -- one full real agricultural year, chosen to match MNFSR's
2022-23 crop-area report year so the phenology signal and the real label
year are temporally consistent, and to span both Rabi wheat and Kharif
cotton/rice/sugarcane so a point's real dominant-season signature is
captured either way).

Per point, per index (NDVI, NDWI, EVI), derives:
  - peak_value, peak_month (0-11)
  - trough_value, trough_month
  - green_up_slope: (peak_value - value_3mo_before_peak) / 3
  - senescence_slope: (value_3mo_after_peak - peak_value) / 3
  - annual_mean, annual_std
No raw lat/lon or district identity is written as a feature -- confirmed
deliberately excluded per direction (Track E's lat/lon leak lesson).

Usage:
    python extract_phenology_features.py --project printtheory \
        --points points.geojson --out phenology_features.csv
"""
import argparse
import json
import os

import ee
import numpy as np

MONTHS = [f"{y}-{m:02d}-01" for y, m in
          [(2022, 11), (2022, 12), (2023, 1), (2023, 2), (2023, 3), (2023, 4),
           (2023, 5), (2023, 6), (2023, 7), (2023, 8), (2023, 9), (2023, 10), (2023, 11)]]
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
    ap.add_argument("--out", default="phenology_features.csv")
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
    print(f"loaded {n_points} real cropland points")

    monthly_values = {}  # point_id -> {month_idx: {ndvi, ndwi, evi}}
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
        if np.sum(np.isfinite(vals)) < 6:  # need a real usable amount of the year covered
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

    print(f"\nreal usable rows: {len(rows)} (dropped {n_dropped} with too much missing/cloudy data)")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
