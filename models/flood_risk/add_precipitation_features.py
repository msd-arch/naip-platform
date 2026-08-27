#!/usr/bin/env python3
"""
add_precipitation_features.py -- Track I, precipitation attempt (Steps 1-3):
adds two new real precipitation features to the existing flood datasets
(flood_dataset.csv/2021/2024/2024_negatives), reusing their EXACT SAME points
-- additive, not a replacement of the SAR/JRC features already there.

WHY THIS IS A GENUINELY DIFFERENT ATTEMPT, NOT A REPEAT OF v2: v2 added more
non-disaster examples of the SAME feature type (SAR backscatter) and failed
because the model globally suppressed its scores rather than learning real
discrimination -- SAR backscatter change tells you "the ground got wetter,"
not why. Real precipitation adds a physically distinct signal: how much rain
actually fell, over what period -- a much more direct predictor of flood risk
than inferring wetness from radar reflectance alone.

REAL PRE-CHECK (dataset choice), done via live GEE queries before building
anything, not assumed:
  - CHIRPS Daily (UCSB-CHG/CHIRPS/DAILY): 0.05 deg (~5.5km) resolution, daily,
    confirmed real coverage for every required window (2021/2022/2024 during
    + pre) via a live query, real historical depth back to 1981 (this script
    uses 2001-2020 for the climatology baseline, 20 years, no overlap with
    any test/positive year). CHOSEN.
  - ERA5-Land Daily Aggr: coarser (0.1 deg, ~11km), confirmed real coverage
    too, but a live spot-check at the same Lahore-area test point showed a
    real ~2x DRIER total than CHIRPS for the identical 2022 monsoon window
    (33.7mm vs 69.6mm) -- a known real regional dry bias, not investigated
    further since CHIRPS's finer resolution was already preferable.
  - GPM IMERG V07: same 0.1 deg resolution as ERA5-Land, real coverage
    confirmed, but a live spot-check showed a real ~2x WETTER total than
    CHIRPS at the same point (129.7mm vs 69.6mm) -- a known real IMERG wet
    bias in complex/convective terrain -- and IMERG's real historical depth
    (GPM era, ~2000-present) is shorter than CHIRPS's (1981-present), a real
    disadvantage for building the 20-year climatology baseline below.
  CHIRPS's real ~5.5km resolution is finer than either alternative and still
  coarser than the ~30m SAR features -- a real, honestly-stated resolution
  mismatch: within a small/urban district, several of the 15 sampled points
  may fall inside the same CHIRPS pixel and read identical precipitation
  values. This does not invalidate the feature (rainfall genuinely doesn't
  vary at 30m scale the way SAR backscatter does), but it does mean
  precipitation adds less within-district differentiation than SAR/JRC do.

FEATURES ADDED (both real, both additive -- existing VV/VH/jrc columns are
never touched):
  - precip_total_mm: real CHIRPS daily precipitation, summed over the exact
    same during-window each dataset's SAR features already use.
  - precip_anomaly_pct: (precip_total_mm - hist_mean_precip_mm) / hist_mean_precip_mm
    * 100, where hist_mean_precip_mm is this point's real 20-year (2001-2020)
    CHIRPS climatological mean for the SAME calendar day-range (e.g. Aug15-Sep16
    every year 2001-2020), built server-side once per calendar window (same
    efficient yearly-stack-then-reduce-once pattern as Track M's
    extract_modis_baseline.py), not 20 separate downloads.

REPRODUCING THE EXACT SAME POINTS: none of the original 4 CSVs persisted
lat/lon. All four confirmed zero rows dropped during their original
extraction (STATUS_WEEK10.md, STATUS_WEEK14.md), so each CSV's row order is
exactly the deterministic GEE randomPoints(seed=42) sequence, in the same
per-district iteration order the original scripts used -- reproduced here
verbatim (same district lists, same order, same seed) to regenerate identical
coordinates and merge the new columns back on by position, not by a
best-effort spatial join.
"""
import argparse
import json
import os

import ee
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")
LABELS_PATH = os.path.join(HERE, "..", "..", "data", "flood_2022_ground_truth", "district_flood_labels_126.json")

N_PER_DISTRICT = 15
CHIRPS_ID = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_SCALE = 5500
CLIMATOLOGY_YEARS = list(range(2001, 2021))  # 20 real years, no overlap with 2021/2022/2024

EXCLUDE_2021 = [
    "Islamabad Capital Territory", "Karachi", "Lower Dir", "Abbottabad",
    "Tank", "Dera Ismail Khan", "Kohistan",
]
POSITIVE_2024 = [
    "Kalat", "Loralai", "Ziarat", "Awaran", "Kachhi", "Lasbela", "Khuzdar",
    "Chagai", "Jhal Magsi", "Jafarabad", "Qilla Saifullah",
    "Thatta", "Badin", "Mirpurkhas",
]

# (csv filename, during-window used by that dataset's SAR features, district-order fn)
DATASETS = [
    ("flood_dataset.csv", ("2022-08-15", "2022-09-16"), "order_2022"),
    ("flood_dataset_2021.csv", ("2021-08-15", "2021-09-16"), "order_2021"),
    ("flood_dataset_2024.csv", ("2024-08-01", "2024-09-15"), "order_2024_positive"),
    ("flood_dataset_2024_negatives.csv", ("2024-08-01", "2024-09-15"), "order_2024_negative"),
]


def district_order(kind, by_name, labels):
    if kind == "order_2022":
        return list(labels["all_126_flags"].keys())
    if kind == "order_2021":
        return sorted(set(by_name.keys()) - set(EXCLUDE_2021))
    if kind == "order_2024_positive":
        return [d for d in POSITIVE_2024 if d in by_name]
    if kind == "order_2024_negative":
        matched_positive = {d for d in POSITIVE_2024 if d in by_name}
        return sorted(set(by_name.keys()) - matched_positive)
    raise ValueError(kind)


def regenerate_points(districts, by_name):
    """Exact replay of the original scripts' point generation: same district
    order, same N_PER_DISTRICT, same seed=42 -- reproduces identical coordinates."""
    all_points = []
    for name in districts:
        geom = ee.Geometry(by_name[name])
        pts = ee.FeatureCollection.randomPoints(region=geom, points=N_PER_DISTRICT, seed=42)
        info = pts.getInfo()
        for feat in info["features"]:
            lon, lat = feat["geometry"]["coordinates"]
            all_points.append({"district": name, "lat": lat, "lon": lon})
    return all_points


def build_climatology_image(during_start, during_end):
    """Real 20-year (2001-2020) CHIRPS climatological mean total precip for
    the SAME calendar day-range as during_start/during_end -- built as one
    stacked-then-reduced server-side operation, not 20 separate downloads."""
    md_start = during_start[5:]  # "MM-DD"
    md_end = during_end[5:]
    chirps = ee.ImageCollection(CHIRPS_ID).select("precipitation")
    yearly_sums = []
    for y in CLIMATOLOGY_YEARS:
        y_start = f"{y}-{md_start}"
        y_end = f"{y}-{md_end}"
        yearly_sums.append(chirps.filterDate(y_start, y_end).sum())
    stack = ee.ImageCollection(yearly_sums)
    return stack.mean().rename("hist_mean_precip_mm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {feat["properties"]["shapeName"]: feat["geometry"] for feat in districts_geojson["features"]}
    with open(LABELS_PATH, encoding="utf-8") as f:
        labels = json.load(f)

    for csv_name, (during_start, during_end), order_kind in DATASETS:
        csv_path = os.path.join(HERE, csv_name)
        print(f"\n=== {csv_name} (during {during_start}..{during_end}) ===")
        df = pd.read_csv(csv_path)

        districts = district_order(order_kind, by_name, labels)
        all_points = regenerate_points(districts, by_name)
        print(f"regenerated {len(all_points)} real points (existing CSV has {len(df)} rows)")
        assert len(all_points) == len(df), (
            f"real point-count mismatch for {csv_name}: regenerated {len(all_points)} vs "
            f"existing {len(df)} rows -- refusing to merge misaligned data"
        )
        # sanity-check district alignment position-by-position, not just counts
        mismatches = sum(1 for p, d in zip(all_points, df["district"]) if p["district"] != d)
        assert mismatches == 0, f"{mismatches} real district-order mismatches in {csv_name} -- refusing to merge"
        print("real point regeneration verified aligned with existing CSV row order")

        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]), {"point_id": str(i)})
            for i, p in enumerate(all_points)
        ])

        chirps = ee.ImageCollection(CHIRPS_ID).select("precipitation")
        current_total = chirps.filterDate(during_start, during_end).sum().rename("precip_total_mm")
        hist_mean_img = build_climatology_image(during_start, during_end)
        combined = ee.Image.cat([current_total, hist_mean_img])

        print("running real reduceRegions for precipitation (current total + 20yr climatology)...")
        reduced = combined.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=CHIRPS_SCALE).getInfo()
        by_pid = {feat["properties"]["point_id"]: feat["properties"] for feat in reduced["features"]}

        precip_total, precip_hist, precip_anom = [], [], []
        n_dropped = 0
        for i in range(len(all_points)):
            props = by_pid.get(str(i), {})
            total = props.get("precip_total_mm")
            hist = props.get("hist_mean_precip_mm")
            if total is None or hist is None:
                n_dropped += 1
                precip_total.append(None)
                precip_hist.append(None)
                precip_anom.append(None)
                continue
            precip_total.append(total)
            precip_hist.append(hist)
            precip_anom.append(((total - hist) / hist * 100.0) if hist > 1e-6 else 0.0)

        print(f"real precipitation rows with usable data: {len(all_points) - n_dropped}/{len(all_points)} "
              f"({n_dropped} missing -- CHIRPS coverage gap, if any)")

        df["precip_total_mm"] = precip_total
        df["hist_mean_precip_mm"] = precip_hist
        df["precip_anomaly_pct"] = precip_anom

        n_before = len(df)
        df = df.dropna(subset=["precip_total_mm", "precip_anomaly_pct"]).reset_index(drop=True)
        if len(df) < n_before:
            print(f"dropped {n_before - len(df)} rows with no real precipitation data "
                  f"(kept {len(df)}/{n_before})")

        df.to_csv(csv_path, index=False)
        print(f"wrote {csv_path} ({len(df)} rows, columns: {list(df.columns)})")


if __name__ == "__main__":
    main()
