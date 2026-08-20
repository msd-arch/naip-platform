#!/usr/bin/env python3
"""
sample_and_extract.py -- Phase 3 Track D, Steps 1-6: real Sentinel-1 SAR
flood-detection dataset for the real Aug-Sept 2022 Pakistan floods.

REAL PRE-CHECK FINDINGS THAT SHAPED THIS DESIGN (naip/docs/STATUS_WEEK10.md
has full detail):
  1. CIRCULARITY AVOIDED: labels come from IOM/Shelter Cluster's real
     "Calamity declared districts" list (as of 16 Sept 2022) -- a real,
     independent, GOVERNMENT-DECLARED administrative dataset, NOT derived
     from Sentinel-1 or any other satellite product. This is genuinely
     independent ground truth for the Sentinel-1-based classifier below,
     unlike the TU Wien/JRC Sentinel-1-derived flood map (which was
     confirmed to exist but deliberately NOT used as a label, precisely
     because it's built from the same instrument used as model input --
     the same circularity Track E's original with-geo framing had to be
     corrected out of).
  2. Real match: 96/126 real districts matched to this list (10 genuinely
     absent from this project's real 126-district set entirely -- the same
     older-geoBoundaries-vintage gap Track C already found for Larkana,
     Washuk, Harnai, Sherani).
  3. Real caveat, carried through: "calamity declared" is a broader real
     administrative/emergency designation, not strictly identical to
     physically-inundated area -- correlates with but isn't the same as a
     pixel-level flood mask.

FEATURES, the established real SAR flood-detection methodology (water = low
backscatter), not reinvented: VV/VH during the real flood window
(2022-08-15..2022-09-15, the real period the calamity-declared list covers),
VV/VH change vs. a real pre-flood dry-season baseline (2022-03-01..2022-04-15),
and real JRC Global Surface Water occurrence (to let the model discount
permanent rivers/lakes rather than just detecting "the river" -- the flood
equivalent of Track F's wheat-dominance trap). NO lat/lon or district-identity
feature -- same leakage risk as Track E/F, confirmed excluded.
"""
import argparse
import json
import os

import ee

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS_PATH = os.path.join(HERE, "..", "..", "data", "flood_2022_ground_truth", "district_flood_labels_126.json")
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")

N_PER_DISTRICT = 15
DURING_START, DURING_END = "2022-08-15", "2022-09-16"
PRE_START, PRE_END = "2022-03-01", "2022-04-15"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "flood_dataset.csv"))
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(LABELS_PATH, encoding="utf-8") as f:
        labels = json.load(f)
    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {f["properties"]["shapeName"]: f["geometry"] for f in districts_geojson["features"]}

    s1 = ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)

    all_points = []
    for i, (name, flooded) in enumerate(labels["all_126_flags"].items()):
        geom = ee.Geometry(by_name[name])
        pts = ee.FeatureCollection.randomPoints(region=geom, points=N_PER_DISTRICT, seed=42)
        info = pts.getInfo()
        for feat in info["features"]:
            lon, lat = feat["geometry"]["coordinates"]
            all_points.append({"district": name, "flooded": flooded, "lat": lat, "lon": lon})
        print(f"[{i+1}/126] {name}: {len(info['features'])} points (flooded={flooded})")

    print(f"\nreal total points sampled: {len(all_points)}")

    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]), {"point_id": str(i)})
        for i, p in enumerate(all_points)
    ])
    region = fc.geometry().bounds()

    def s1_composite(start, end):
        col = s1.filterBounds(region).filterDate(start, end)
        return col.select(["VV", "VH"]).median()

    during_img = s1_composite(DURING_START, DURING_END)
    pre_img = s1_composite(PRE_START, PRE_END)
    combined = ee.Image.cat([
        during_img.rename(["VV_during", "VH_during"]),
        pre_img.rename(["VV_pre", "VH_pre"]),
        jrc.rename("jrc_occurrence"),
    ])

    print("running real reduceRegions over all points (single real composite image)...")
    reduced = combined.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30).getInfo()

    by_pid = {f["properties"]["point_id"]: f["properties"] for f in reduced["features"]}

    rows = []
    n_dropped = 0
    for i, p in enumerate(all_points):
        props = by_pid.get(str(i), {})
        vv_d, vh_d = props.get("VV_during"), props.get("VH_during")
        vv_p, vh_p = props.get("VV_pre"), props.get("VH_pre")
        jrc_occ = props.get("jrc_occurrence")
        if None in (vv_d, vh_d, vv_p, vh_p, jrc_occ):
            n_dropped += 1
            continue
        rows.append({
            "district": p["district"], "flooded": int(p["flooded"]),
            "VV_during": vv_d, "VH_during": vh_d,
            "VV_change": vv_p - vv_d, "VH_change": vh_p - vh_d,
            "jrc_occurrence": jrc_occ,
        })

    import csv
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\nreal usable rows: {len(rows)} (dropped {n_dropped} with missing real S1/JRC data)")
    print(f"real class balance: flooded={sum(r['flooded'] for r in rows)}, "
          f"not_flooded={len(rows) - sum(r['flooded'] for r in rows)}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
