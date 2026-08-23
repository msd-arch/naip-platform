#!/usr/bin/env python3
"""combine_points.py -- real national point set for Track M: Track F's exact
2,875 points (115 MNFSR districts) + this track's 275 new unmasked points
(11 GB/AJK districts) = 3,150 real points, 126/126 real districts."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TRACK_F_POINTS = os.path.join(HERE, "..", "crop_classifier_national", "points.geojson")
GBAJK_POINTS = os.path.join(HERE, "points_gbajk_unmasked.geojson")
OUT = os.path.join(HERE, "combined_points.geojson")

with open(TRACK_F_POINTS, encoding="utf-8") as f:
    trackf = json.load(f)
with open(GBAJK_POINTS, encoding="utf-8") as f:
    gbajk = json.load(f)

features = trackf["features"] + gbajk["features"]
districts = sorted({f["properties"]["district"] for f in features})
print(f"combined: {len(features)} real points, {len(districts)} real districts")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection", "features": features}, f)
print(f"wrote {OUT}")
