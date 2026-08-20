#!/usr/bin/env python3
"""
build_grid_dataset.py -- Phase 3 Track E, Step 1: real pixel/grid-level
dataset for training a fire classifier on NAIP's actual MSG sensor, and for
giving det_residue_burning()'s existing rule a fair full-grid recall
evaluation (which Track A's 126-district-centroid sampling could not give
it -- see naip/docs/DEMO_TRACK_A.md Section 4).

REUSES, does not re-pull:
  - the 45 real MSG3 scenes already processed by export_hazard_grids.py into
    naip/data/msg_oct_nov_2023/web_data/msg_hazard/ (0.25deg grid, national
    bbox 55-85E/20-40N, 81x121 = 9801 cells/timestep)
  - the real national FIRMS pull for the same window,
    naip/data/fire_ground_truth/firms_national_2023nov_*.csv (26,311 real
    hotspots)

CANDIDATE UNIVERSE (same hard gates det_residue_burning() itself applies,
so the rule-based baseline evaluated on this dataset later is evaluated on
exactly the universe it would actually run on -- not a different one):
  - daytime only (local_hour 6-19, PKT = UTC+5), same as det_residue_burning()
  - night_fog_diff and cloud_proxy both present (not NaN) at that cell/time
Cloud_proxy is NOT used as a pre-filter here (that's part of the rule's own
internal clear-sky gate, and a design choice this script deliberately leaves
to whichever consumer -- rule replay or trained model -- decides how to use
it, so both see the identical candidate set).

LABEL: a candidate cell is POSITIVE if a real FIRMS hotspot falls within
50km and +/-1 day of that cell's centroid -- the SAME tolerance already used
throughout this project's real cross-references (Week 5, the Track A
addendum), kept for consistency rather than introducing a new methodology.
Uses a haversine BallTree for a real, exact spatial join (not brute force).

FEATURES written per candidate row: night_fog_diff, nfd_local_bg (+/-3deg
box mean, same field/method det_residue_burning() itself uses for its
contextual test), the raw anomaly (night_fog_diff - nfd_local_bg),
cloud_proxy, lat, lon, local_hour, date -- consistent with what
det_residue_burning() already computes, so a trained model is a genuine,
explainable upgrade path for it, not an unrelated black box.
"""
import glob
import json
import os

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

HERE = os.path.dirname(os.path.abspath(__file__))
MSG_HAZARD_DIR = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2023", "web_data", "msg_hazard")
FIRMS_GLOB = os.path.join(HERE, "..", "..", "data", "fire_ground_truth", "firms_national_2023nov_*.csv")
OUT_PATH = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2023", "grid_dataset.parquet")
OUT_CSV_SAMPLE = os.path.join(HERE, "..", "..", "data", "msg_oct_nov_2023", "grid_dataset_sample.csv")

TOLERANCE_KM = 50.0
EARTH_R_KM = 6371.0
BOX_DEG = 3.0  # same +/-3deg local-background box det_residue_burning() uses


def load_grid_json(path):
    d = json.load(open(path, encoding="utf-8"))
    lat = np.array(d["lat"])
    lon = np.array(d["lon"])
    values = np.array([[np.nan if v is None else v for v in row] for row in d["values"]], dtype="float64")
    return lat, lon, values


def local_background_box_mean(values, lat, lon, box_deg):
    """+/-box_deg box mean around every grid cell, vectorised. lat is
    descending (north->south), lon ascending -- matches export_hazard_grids.py."""
    res = abs(lat[1] - lat[0])
    n_cells = int(round(box_deg / res))
    ny, nx = values.shape
    # pad with NaN, use nanmean via cumulative-sum-of-finite trick for speed
    padded = np.pad(values, n_cells, mode="constant", constant_values=np.nan)
    out = np.full_like(values, np.nan)
    finite = np.isfinite(padded)
    padded_zero = np.where(finite, padded, 0.0)
    csum = np.cumsum(np.cumsum(padded_zero, axis=0), axis=1)
    ccount = np.cumsum(np.cumsum(finite.astype("float64"), axis=0), axis=1)
    csum = np.pad(csum, ((1, 0), (1, 0)))
    ccount = np.pad(ccount, ((1, 0), (1, 0)))
    for i in range(ny):
        for j in range(nx):
            y0, y1 = i, i + 2 * n_cells + 1
            x0, x1 = j, j + 2 * n_cells + 1
            s = csum[y1, x1] - csum[y0, x1] - csum[y1, x0] + csum[y0, x0]
            c = ccount[y1, x1] - ccount[y0, x1] - ccount[y1, x0] + ccount[y0, x0]
            out[i, j] = s / c if c > 0 else np.nan
    return out


def main():
    manifest = json.load(open(os.path.join(MSG_HAZARD_DIR, "manifest.json"), encoding="utf-8"))
    print(f"{len(manifest['timesteps'])} real MSG timesteps found")

    # --- load real FIRMS points, build a haversine BallTree per real date ---
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
        local_hour = (hh + 5) % 24  # PKT = UTC+5, same convention as hazards.py
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

        # candidate dates for FIRMS label tolerance (+/-1 real day)
        import datetime as dt
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
