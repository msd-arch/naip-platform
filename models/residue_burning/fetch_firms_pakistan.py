#!/usr/bin/env python3
"""
fetch_firms_pakistan.py -- Phase 2 Track A: pull real NASA FIRMS MODIS/VIIRS
archived active-fire hotspots for Pakistan over a real date range, for
cross-referencing against det_residue_burning()'s Week 3 national run.

Requires a free FIRMS MAP_KEY (tied to a NASA Earthdata Login account --
https://urs.earthdata.nasa.gov/, then https://firms.modaps.eosdis.nasa.gov/api/map_key/).
Not something Claude can create on the user's behalf -- pass the key in via
--map_key or the FIRMS_MAP_KEY env var once you have it.

Uses the FIRMS "area" API (country/bbox + date range, CSV), documented at
https://firms.modaps.eosdis.nasa.gov/api/area/ -- day_range is capped per
request (historically 1-10 days), so this script loops in chunks.

Two real use cases this project needs, both real dates, no fabrication:
  1. Punjab, real historical Oct-Nov windows (2023, 2024, 2025) -- to check
     whether the contextual-anomaly *methodology* correlates with real fires
     in Punjab's real burning season (the season the current MSG archive does
     NOT cover).
  2. The exact districts/dates det_residue_burning() flagged in the Week 3
     national run (models/../data/fire_ground_truth/residue_burning_flagged_records.json,
     real dates 2026-06-22..2026-07-15) -- to check whether those flagged
     Balochistan districts had ANY real FIRMS-confirmed fire (of any kind,
     not necessarily crop residue) on/near the same real dates, which would
     tell us whether the false-positive-risk flag was "a real thermal
     anomaly, just not from our sensor/season" vs. pure noise.
"""
import argparse
import os
import time
import urllib.request

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
PAKISTAN_BBOX = "60.87,23.63,77.84,37.10"  # west,south,east,north, real national bbox


def fetch_chunk(map_key, source, bbox, day_range, start_date, out_path):
    url = f"{BASE}/{map_key}/{source}/{bbox}/{day_range}/{start_date}"
    print(f"GET {url.replace(map_key, 'REDACTED')}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    with open(out_path, "wb") as f:
        f.write(data)
    n_lines = data.count(b"\n")
    print(f"  -> {out_path} ({n_lines} lines incl header)")
    return n_lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map_key", default=os.environ.get("FIRMS_MAP_KEY"))
    ap.add_argument("--source", default="VIIRS_SNPP_SP",
                     help="VIIRS_SNPP_SP (375m, 2012+) or MODIS_SP (1km, 2000+) or VIIRS_NOAA20_SP")
    ap.add_argument("--bbox", default=PAKISTAN_BBOX)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--n_days", type=int, required=True)
    ap.add_argument("--chunk_days", type=int, default=5,
                     help="real FIRMS area API cap, confirmed via a live 400 error: day_range must be 1..5")
    ap.add_argument("--out_prefix", default="../../data/fire_ground_truth/firms")
    a = ap.parse_args()

    if not a.map_key:
        raise SystemExit(
            "No FIRMS MAP_KEY. Get one (free) at https://firms.modaps.eosdis.nasa.gov/api/map_key/ "
            "after creating a free Earthdata Login at https://urs.earthdata.nasa.gov/ -- "
            "then pass --map_key or set FIRMS_MAP_KEY."
        )

    import datetime as dt
    cur = dt.date.fromisoformat(a.start)
    remaining = a.n_days
    part = 0
    while remaining > 0:
        chunk = min(a.chunk_days, remaining)
        out_path = f"{a.out_prefix}_{a.source}_{cur.isoformat()}_{chunk}d.csv"
        fetch_chunk(a.map_key, a.source, a.bbox, chunk, cur.isoformat(), out_path)
        cur += dt.timedelta(days=chunk)
        remaining -= chunk
        part += 1
        time.sleep(1)  # polite pacing, real FIRMS rate limit is 5000/10min so this is generous


if __name__ == "__main__":
    main()
