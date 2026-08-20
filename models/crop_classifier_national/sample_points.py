#!/usr/bin/env python3
"""
sample_points.py -- Phase 3 Track F, Step 1: real national stratified
Sentinel-2 point sample, restricted to real cropland (WorldCereal
'temporarycrops' product, same real product Week 2 used) so points aren't
trivially-easy non-agricultural terrain (desert, mountain, urban).

REAL PRE-CHECK FINDINGS THAT SHAPED THIS DESIGN (see naip/docs/STATUS_WEEK8.md
for full detail -- summarised here since they directly determine what this
script builds):
  1. WorldCereal has NO crop-type product for Pakistan anywhere in the
     collection (confirmed nationally: temporarycrops, irrigation, maize,
     wintercereals, springcereals -- same 5 products Week 2 found for
     Layyah/Muridke specifically). No cotton/rice/sugarcane class exists.
     'wintercereals' is used as a real wheat proxy for the one real
     cross-check this track can honestly make (see cross_check_worldcereal.py).
  2. A "predict each district's single dominant crop" framing would collapse
     to ~93% one class (wheat dominant in 107/115 real MNFSR-covered
     districts) -- the same degenerate trap Week 2's cropland task hit.
     Confirmed with you: this track predicts real per-crop AREA SHARES
     (multi-output regression), not a single dominant-crop label.

Stratified sample: ~25 real cropland points per real MNFSR-covered district
(115 districts -> ~2,875 points, "thousands, not 120" per direction), using
ee.Image.stratifiedSample restricted to each district's real polygon,
masked to WorldCereal temporarycrops == 100 (real cropland only).

Usage:
    python sample_points.py --project printtheory --out points.geojson
"""
import argparse
import json
import os

import ee

HERE = os.path.dirname(os.path.abspath(__file__))
CROP_MIX_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json")
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")

N_PER_DISTRICT = 25


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "points.geojson"))
    ap.add_argument("--n_per_district", type=int, default=N_PER_DISTRICT)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(CROP_MIX_PATH, encoding="utf-8") as f:
        crop_mix = json.load(f)
    real_districts = {name for name, rec in crop_mix.items() if rec["tier"] == "real_district_area"}
    print(f"{len(real_districts)} real MNFSR-covered districts to sample from")

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {f["properties"]["shapeName"]: f["geometry"] for f in districts_geojson["features"]
               if f["properties"]["shapeName"] in real_districts}
    print(f"{len(by_name)} district polygons matched")

    wc_cropland = (ee.ImageCollection("ESA/WorldCereal/2021/MODELS/v100")
                   .filter(ee.Filter.eq("product", "temporarycrops")).select("classification").mosaic())
    cropland_mask = wc_cropland.eq(100)

    all_features = []
    for i, (name, geom) in enumerate(by_name.items()):
        region = ee.Geometry(geom)
        masked = cropland_mask.selfMask().clip(region)
        try:
            sample = masked.addBands(ee.Image.pixelLonLat()).stratifiedSample(
                numPoints=a.n_per_district, classBand="classification", region=region,
                scale=100, seed=a.seed, geometries=True, dropNulls=True,
            )
            info = sample.getInfo()
            n = len(info["features"])
        except Exception as e:
            print(f"  [{i+1}/{len(by_name)}] {name}: FAILED ({str(e)[:100]})")
            continue
        for feat in info["features"]:
            feat["properties"]["district"] = name
        all_features.extend(info["features"])
        print(f"  [{i+1}/{len(by_name)}] {name}: {n} real cropland points sampled")

    out = {"type": "FeatureCollection", "features": all_features}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"\nreal total points sampled: {len(all_features)}, across {len(by_name)} real districts")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
