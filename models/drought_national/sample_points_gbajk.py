#!/usr/bin/env python3
"""
sample_points_gbajk.py -- Phase 4 Track M: real point sample for the 11
real GB/AJK districts Track F's WorldCereal cropland mask excluded (Week 9's
own finding: real WorldCereal cropland coverage there is 0.02-0.18% of
district area -- near-zero, high-altitude terrain, not because no real
vegetation exists there). Drought/vegetation-stress monitoring is not gated
by crop-type data the way Track F's crop-share task was, so this samples
real, unmasked points directly -- same real random-point method as
sample_points.py, minus the cropland mask.

Usage:
    python sample_points_gbajk.py --project printtheory --out points_gbajk_unmasked.geojson
"""
import argparse
import json
import os

import ee

HERE = os.path.dirname(os.path.abspath(__file__))
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")

GBAJK_DISTRICTS = [
    "Astore", "Azad Kashmir", "Diamer", "Ghanche", "Ghizer", "Gilgit",
    "Hunza", "Kharmang", "Nagar", "Shigar", "Skardu",
]
N_PER_DISTRICT = 25  # same density as Track F's sample_points.py


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "points_gbajk_unmasked.geojson"))
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {feat["properties"]["shapeName"]: feat["geometry"] for feat in districts_geojson["features"]
               if feat["properties"]["shapeName"] in GBAJK_DISTRICTS}
    print(f"{len(by_name)}/{len(GBAJK_DISTRICTS)} real GB/AJK district polygons matched")

    all_features = []
    for i, (name, geom) in enumerate(by_name.items()):
        region = ee.Geometry(geom)
        pts = ee.FeatureCollection.randomPoints(region=region, points=N_PER_DISTRICT, seed=a.seed)
        info = pts.getInfo()
        for feat in info["features"]:
            feat["properties"]["district"] = name
        all_features.extend(info["features"])
        print(f"  [{i+1}/{len(by_name)}] {name}: {len(info['features'])} real points sampled (unmasked)")

    out = {"type": "FeatureCollection", "features": all_features}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"\nreal total points sampled: {len(all_features)}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
