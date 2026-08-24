#!/usr/bin/env python3
"""
build_grid_dataset_2021.py -- Track K: real second validation year for Track E's
fire classifier. Reuses build_grid_dataset.py's exact methodology (candidate
universe, FIRMS 50km/+-1day label tolerance, local-background box-mean feature
construction) unchanged -- only the source paths differ (2021 archive instead of
2023). See build_grid_dataset.py's own docstring for the full methodology notes;
not repeated here.
"""
import datetime as dt
import glob
import json
import os

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from build_grid_dataset import load_grid_json, local_background_box_mean

HERE = os.path.dirname(os.path.abspath(__file__))
MSG_HAZARD_DIR = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2021", "web_data", "msg_hazard")
FIRMS_GLOB = os.path.join(HERE, "..", "..", "data", "fire_ground_truth", "firms_national_2021nov_*.csv")
OUT_PATH = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2021", "grid_dataset.parquet")
OUT_CSV_SAMPLE = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2021", "grid_dataset_sample.csv")

TOLERANCE_KM = 50.0
EARTH_R_KM = 6371.0
BOX_DEG = 3.0


def main():
    manifest = json.load(open(os.path.join(MSG_HAZARD_DIR, "manifest.json"), encoding="utf-8"))
    print(f"{len(manifest['timesteps'])} real MSG timesteps found")

    firms_by_date = {}
    n_firms = 0
    for fp in glob.glob(FIRMS_GLOB):
        df = pd.read_csv(fp)
        for date_s, sub in df.groupby("acq_date"):
            pts = np.radians(sub[["latitude", "longitude"]].values)
            firms_by_date.setdefault(date_s, []).append(pts)
            n_firms += len(sub)
    firms_by_date = {d: np.vstack(v) for d, v in firms_by_date.items()}
    firms_trees = {d: BallTree(pts, metric="haversine") for d, pts in firms_by_date.items()}
    print(f"real FIRMS points loaded: {n_firms}, across {len(firms_by_date)} real dates")

    rows = []
    for i, step in enumerate(manifest["timesteps"]):
        stamp = step["stamp"]
        date_s, hhmm = stamp.split("_")
        hh = int(hhmm[:2])
        local_hour = (hh + 5) % 24
        is_day = 6 <= local_hour < 19
        if not is_day:
            continue

        nfd_path = os.path.join(MSG_HAZARD_DIR, step["grids"]["night_fog_diff"])
        cp_path = os.path.join(MSG_HAZARD_DIR, step["grids"]["cloud_proxy"])
        if not (os.path.exists(nfd_path) and os.path.exists(cp_path)):
            continue
        lat, lon, nfd = load_grid_json(nfd_path)
        _, _, cloud_proxy = load_grid_json(cp_path)
        nfd_bg = local_background_box_mean(nfd, lat, lon, BOX_DEG)

        d0 = dt.datetime.strptime(date_s, "%Y%m%d").date()
        cand_dates = [(d0 + dt.timedelta(days=off)).isoformat() for off in (-1, 0, 1)]
        cand_trees = [(dd, firms_trees[dd]) for dd in cand_dates if dd in firms_trees]

        LAT, LON = np.meshgrid(lat, lon, indexing="ij")
        radius_rad = TOLERANCE_KM / EARTH_R_KM

        label = np.zeros(nfd.shape, dtype=bool)
        if cand_trees:
            query = np.radians(np.column_stack([LAT.ravel(), LON.ravel()]))
            any_hit = np.zeros(query.shape[0], dtype=bool)
            for dd, tree in cand_trees:
                counts = tree.query_radius(query, r=radius_rad, count_only=True)
                any_hit |= counts > 0
            label = any_hit.reshape(nfd.shape)

        valid = np.isfinite(nfd) & np.isfinite(cloud_proxy)
        idx = np.where(valid)
        for yy, xx in zip(*idx):
            rows.append({
                "stamp": stamp, "date": date_s, "local_hour": local_hour,
                "lat": float(lat[yy]), "lon": float(lon[xx]),
                "night_fog_diff": float(nfd[yy, xx]),
                "nfd_local_bg": float(nfd_bg[yy, xx]) if np.isfinite(nfd_bg[yy, xx]) else None,
                "nfd_anomaly": float(nfd[yy, xx] - nfd_bg[yy, xx]) if np.isfinite(nfd_bg[yy, xx]) else None,
                "cloud_proxy": float(cloud_proxy[yy, xx]),
                "label_real_fire_nearby": bool(label[yy, xx]),
            })
        print(f"[{i+1}/{len(manifest['timesteps'])}] {stamp} (day) -> {len(idx[0])} valid cells, "
              f"{int(label[idx].sum())} positive")

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["nfd_anomaly"]).reset_index(drop=True)
    print(f"\nfinal real dataset: {len(df)} rows, {df['label_real_fire_nearby'].sum()} positive "
          f"({df['label_real_fire_nearby'].mean()*100:.3f}%), {df['date'].nunique()} real distinct dates")

    df.to_parquet(OUT_PATH, index=False)
    df.sample(min(500, len(df)), random_state=0).to_csv(OUT_CSV_SAMPLE, index=False)
    print(f"wrote {OUT_PATH}")
    print(f"wrote sample preview {OUT_CSV_SAMPLE}")


if __name__ == "__main__":
    main()
