#!/usr/bin/env python3
"""
sample_and_extract_cross_year.py -- Phase 4 Track I: real non-disaster negative
class (2021) + real second-disaster-year positive class (2024) for the flood
classifier, using sample_and_extract.py's EXACT feature construction (VV_during,
VH_during, VV_change, VH_change, jrc_occurrence) -- reused, not reinvented.

REAL PRE-CHECKS (naip/docs/STATUS_WEEK14.md has full detail):
  1. 2021 chosen as the real non-disaster negative-class year -- PMD's own real
     monsoon summary reports the 2021 season as slightly below average
     nationally (-11.3%), no NDMA national emergency was declared (unlike 2022's
     declared national emergency or 2023/2024's provincial calamity
     declarations), and no district-level "calamity declared" list exists for
     2021 anywhere found -- itself real corroborating evidence this wasn't
     treated as a disaster year at the government level. NOT perfectly clean:
     real, documented localized events excluded explicitly below, not silently
     included as false negatives.
  2. 2024 chosen (over 2023, confirmed with you) as the real second disaster
     year for cross-year positive validation -- national-scale monsoon flooding
     (306 deaths, Balochistan/Sindh/Punjab all significantly above-normal
     rainfall), with a real PDMA Balochistan calamity-declared district list
     (13 districts) plus real Sindh coastal cyclone-flood districts, both
     corroborated across multiple real news/PDMA sources.

REAL 2021 EXCLUSIONS (documented localized flood events, NOT included as clean
negatives -- dropped from the dataset entirely, not labeled 0):
  - Islamabad Capital Territory: real cloudburst flooding, 28 Jul 2021
  - Karachi: real urban drainage flooding, Sept 2021, 187 deaths (national monsoon
    death toll) -- a different mechanism (urban drainage) than the riverine/
    agricultural inundation this model targets, excluded out of caution anyway
  - Lower Dir, Abbottabad, Tank, Dera Ismail Khan, Kohistan: real flash-flood/
    landslide deaths, 11-15 Jul 2021 (KP)

REAL 2024 POSITIVE-CLASS DISTRICTS (PDMA Balochistan's real 13-district calamity
list + real Sindh coastal cyclone-flood districts; 14/17 matched to this
project's 126-district set, 3 absent -- Sohbatpur, Usta Muhammad, Sujawal --
same real geoBoundaries-vintage gap this project has found before):
  Balochistan: Kalat, Loralai, Ziarat, Awaran, Kachhi, Lasbela, Khuzdar, Chagai,
    Jhal Magsi, Jafarabad, Qilla Saifullah
  Sindh: Thatta, Badin, Mirpurkhas

Usage:
    python sample_and_extract_cross_year.py --project printtheory --year 2021 --role negative --out flood_dataset_2021.csv
    python sample_and_extract_cross_year.py --project printtheory --year 2024 --role positive --out flood_dataset_2024.csv
"""
import argparse
import json
import os

import ee

HERE = os.path.dirname(os.path.abspath(__file__))
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")

N_PER_DISTRICT = 15  # same as sample_and_extract.py / training

EXCLUDE_2021 = [
    "Islamabad Capital Territory", "Karachi", "Lower Dir", "Abbottabad",
    "Tank", "Dera Ismail Khan", "Kohistan",
]
POSITIVE_2024 = [
    "Kalat", "Loralai", "Ziarat", "Awaran", "Kachhi", "Lasbela", "Khuzdar",
    "Chagai", "Jhal Magsi", "Jafarabad", "Qilla Saifullah",
    "Thatta", "Badin", "Mirpurkhas",
]

YEAR_WINDOWS = {
    2021: {"during": ("2021-08-15", "2021-09-16"), "pre": ("2021-03-01", "2021-04-15")},
    2024: {"during": ("2024-08-01", "2024-09-15"), "pre": ("2024-03-01", "2024-04-15")},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--year", type=int, required=True, choices=[2021, 2024])
    ap.add_argument("--role", required=True, choices=["negative", "positive", "negative_2024"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {feat["properties"]["shapeName"]: feat["geometry"] for feat in districts_geojson["features"]}

    if a.role == "negative":
        target_districts = sorted(set(by_name.keys()) - set(EXCLUDE_2021))
        label = 0
        print(f"real 2021 negative-class run: {len(target_districts)}/126 districts "
              f"({len(EXCLUDE_2021)} excluded for real documented localized flood events)")
    elif a.role == "positive":
        target_districts = [d for d in POSITIVE_2024 if d in by_name]
        missing = [d for d in POSITIVE_2024 if d not in by_name]
        label = 1
        print(f"real 2024 positive-class run: {len(target_districts)}/{len(POSITIVE_2024)} "
              f"real calamity-declared districts matched (missing: {missing})")
    else:  # negative_2024 -- same within-season methodology Track D's original 2022 dataset used:
        # districts NOT declared calamity-hit in the same real monsoon season = real negatives.
        matched_positive = {d for d in POSITIVE_2024 if d in by_name}
        target_districts = sorted(set(by_name.keys()) - matched_positive)
        label = 0
        print(f"real 2024 negative-class run: {len(target_districts)}/126 districts "
              f"(126 - {len(matched_positive)} real calamity-declared districts, same "
              "within-season methodology as the original 2022 dataset)")

    during_start, during_end = YEAR_WINDOWS[a.year]["during"]
    pre_start, pre_end = YEAR_WINDOWS[a.year]["pre"]
    print(f"real during window: {during_start}..{during_end}, real pre window: {pre_start}..{pre_end}")

    s1 = ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)

    all_points = []
    for i, name in enumerate(target_districts):
        geom = ee.Geometry(by_name[name])
        pts = ee.FeatureCollection.randomPoints(region=geom, points=N_PER_DISTRICT, seed=42)
        info = pts.getInfo()
        for feat in info["features"]:
            lon, lat = feat["geometry"]["coordinates"]
            all_points.append({"district": name, "flooded": label, "lat": lat, "lon": lon})
        if (i + 1) % 10 == 0 or i == len(target_districts) - 1:
            print(f"[{i + 1}/{len(target_districts)}] sampled points through {name}")

    print(f"\nreal total points sampled: {len(all_points)}")

    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]), {"point_id": str(i)})
        for i, p in enumerate(all_points)
    ])
    region = fc.geometry().bounds()

    def s1_composite(start, end):
        col = s1.filterBounds(region).filterDate(start, end)
        return col.select(["VV", "VH"]).median()

    during_img = s1_composite(during_start, during_end)
    pre_img = s1_composite(pre_start, pre_end)
    combined = ee.Image.cat([
        during_img.rename(["VV_during", "VH_during"]),
        pre_img.rename(["VV_pre", "VH_pre"]),
        jrc.rename("jrc_occurrence"),
    ])

    print("running real reduceRegions over all points (single real composite image)...")
    reduced = combined.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30).getInfo()
    by_pid = {feat["properties"]["point_id"]: feat["properties"] for feat in reduced["features"]}

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
            "district": p["district"], "flooded": p["flooded"],
            "VV_during": vv_d, "VH_during": vh_d,
            "VV_change": vv_p - vv_d, "VH_change": vh_p - vh_d,
            "jrc_occurrence": jrc_occ, "year": a.year,
        })

    import csv
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\nreal usable rows: {len(rows)} (dropped {n_dropped} with missing real S1/JRC data)")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
