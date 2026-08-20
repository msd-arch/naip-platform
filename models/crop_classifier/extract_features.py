#!/usr/bin/env python3
"""
extract_features.py -- pull real Sentinel-2 NDVI monthly-composite features and
real ESA WorldCereal labels for the 120 Layyah/Muridke farm polygons.

Scope note (see naip/docs/architecture.md 6.3 vs. what this actually does):
WorldCereal's public product set has NO cotton/rice/sugarcane classes for
Pakistan -- confirmed by querying the real GEE catalog before writing this
script (23/19 tiles cover Layyah/Muridke; products available are only
temporarycrops, irrigation, maize, wintercereals, springcereals). So this
pulls real labels for two binary tasks instead of the 4-crop-type split the
architecture doc describes:
  - cropland  : WorldCereal 'temporarycrops' classification
  - irrigated : WorldCereal 'irrigation' classification
This is NOT a wheat/cotton/rice/sugarcane classifier. Say so in every report.

NDVI features: cloud-masked (SCL-based) monthly median composites,
Sentinel-2 SR Harmonized, Apr-Oct 2025 (Kharif season), per farm polygon
(reduceRegions, mean NDVI per farm per month -- real satellite data, real
polygons, no synthetic values).

Usage:
    python extract_features.py --project printtheory \
        --farms ../../data/seed/farms_layyahMuridke_Kharif2025.geojson \
        --out features_labels.csv
"""
import argparse
import json

import ee


MONTHS = [f"2025-{m:02d}-01" for m in range(4, 11)]  # Apr..Oct 2025 starts
CLOUD_MASK_SCL_EXCLUDE = [0, 1, 3, 8, 9, 10, 11]  # nodata/saturated/cloud-shadow/cloud-med/cloud-high/cirrus/snow


def mask_s2_clouds(img):
    scl = img.select("SCL")
    mask = scl.remap(CLOUD_MASK_SCL_EXCLUDE, [0] * len(CLOUD_MASK_SCL_EXCLUDE), 1)
    return img.updateMask(mask)


def monthly_ndvi_composite(start, end, region):
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .map(mask_s2_clouds)
    )
    composite = col.median()
    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("ndvi")
    return ndvi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--farms", required=True)
    ap.add_argument("--out", default="features_labels.csv")
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(a.farms, encoding="utf-8") as f:
        fc_geojson = json.load(f)

    features = []
    for feat in fc_geojson["features"]:
        fid = feat.get("id") or feat["properties"].get("id")
        features.append(ee.Feature(ee.Geometry(feat["geometry"]), {"farm_id": str(fid)}))
    farm_fc = ee.FeatureCollection(features)
    region = farm_fc.geometry().bounds()

    print(f"loaded {len(features)} real farm polygons from {a.farms}")

    # ---- NDVI monthly composites, per-farm mean ----
    ndvi_by_month = {}  # farm_id -> {month: ndvi}
    for i in range(len(MONTHS) - 1):
        start, end = MONTHS[i], MONTHS[i + 1]
        month_label = start[:7]
        ndvi_img = monthly_ndvi_composite(start, end, region)
        reduced = ndvi_img.reduceRegions(collection=farm_fc, reducer=ee.Reducer.mean(), scale=10)
        result = reduced.getInfo()
        n_valid = 0
        for f in result["features"]:
            fid = f["properties"]["farm_id"]
            val = f["properties"].get("mean")
            ndvi_by_month.setdefault(fid, {})[month_label] = val
            if val is not None:
                n_valid += 1
        print(f"  {month_label}: {n_valid}/{len(features)} farms with valid cloud-free NDVI")

    # ---- WorldCereal labels, per-farm mode ----
    wc = ee.ImageCollection("ESA/WorldCereal/2021/MODELS/v100")
    tc_img = wc.filter(ee.Filter.eq("product", "temporarycrops")).select("classification").mosaic()
    irr_img = wc.filter(ee.Filter.eq("product", "irrigation")).select("classification").mosaic()

    tc_reduced = tc_img.reduceRegions(collection=farm_fc, reducer=ee.Reducer.mode(), scale=10).getInfo()
    irr_reduced = irr_img.reduceRegions(collection=farm_fc, reducer=ee.Reducer.mode(), scale=10).getInfo()

    tc_labels = {f["properties"]["farm_id"]: f["properties"].get("mode") for f in tc_reduced["features"]}
    irr_labels = {f["properties"]["farm_id"]: f["properties"].get("mode") for f in irr_reduced["features"]}

    n_tc = sum(1 for v in tc_labels.values() if v is not None)
    n_irr = sum(1 for v in irr_labels.values() if v is not None)
    print(f"WorldCereal labels: {n_tc}/{len(features)} farms with cropland label, "
          f"{n_irr}/{len(features)} farms with irrigation label")

    # ---- write combined CSV ----
    month_cols = [m[:7] for m in MONTHS[:-1]]
    import csv
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["farm_id"] + month_cols + ["worldcereal_cropland", "worldcereal_irrigated"])
        for fid in ndvi_by_month:
            row = [fid] + [ndvi_by_month[fid].get(m) for m in month_cols]
            row += [tc_labels.get(fid), irr_labels.get(fid)]
            w.writerow(row)

    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
