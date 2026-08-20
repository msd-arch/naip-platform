#!/usr/bin/env python3
"""
analyze_firms_ground_truth.py -- Phase 2 Track A analysis, real data only.

Part 1: real Punjab Oct-Nov FIRMS VIIRS hotspot counts for 2023/2024/2025 --
confirms (or not) the real seasonal timing det_residue_burning()'s in-message
"DEMO MODE" caveat describes, using real fire counts, not an assumption.

Part 2: cross-reference the 46 real district/date records
det_residue_burning() flagged in the Week 3 national run (Kharif season,
2026-06-22..2026-07-15, includes the Balochistan districts flagged as
possible bare-terrain noise) against real FIRMS NRT hotspots for Pakistan
over the same real dates -- for each flagged record, was there a real
FIRMS-confirmed fire within a real spatial/temporal tolerance (50km, +/-1
day, matching the ~27km MSG pixel this detector runs on plus one day of
satellite-revisit slack)?
"""
import csv
import glob
import json
import math
from collections import defaultdict


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def load_firms_csvs(pattern):
    pts = []
    for fp in glob.glob(pattern):
        with open(fp, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    pts.append({
                        "lat": float(r["latitude"]), "lon": float(r["longitude"]),
                        "date": r["acq_date"], "confidence": r.get("confidence"),
                        "frp": float(r["frp"]) if r.get("frp") else None,
                        "daynight": r.get("daynight"),
                    })
                except (KeyError, ValueError):
                    continue
    return pts


def part1_seasonal_profile():
    print("=" * 70)
    print("PART 1 -- real Punjab Oct-Nov VIIRS hotspot counts by year (real burning season)")
    print("=" * 70)
    for yr in (2023, 2024, 2025):
        pts = load_firms_csvs(f"../../data/fire_ground_truth/firms_punjab_{yr}_*.csv")
        by_period = defaultdict(int)
        for p in pts:
            d = p["date"]
            month = d[5:7]
            half = "early" if int(d[8:10]) <= 15 else "late"
            by_period[f"{month}-{half}"] += 1
        total = len(pts)
        print(f"\n{yr}: {total} real VIIRS hotspots, Oct 1 - Nov 30, Punjab bbox")
        for k in sorted(by_period):
            print(f"  {k}: {by_period[k]}")
    # also pull the Kharif-archive-equivalent window (Jun22-Jul20) count for direct contrast,
    # reusing the already-downloaded Week 3 cross-check pull (national bbox, not Punjab-only,
    # so not a perfectly matched comparison -- noted, not smoothed over)
    kharif_pts = load_firms_csvs("../../data/fire_ground_truth/firms_pk_week3window*.csv")
    print(f"\nFor contrast: real Jun22-Jul20 2026 national-bbox VIIRS hotspot count: {len(kharif_pts)}")
    print("(national bbox, not Punjab-only -- not a clean apples-to-apples count, directional only)")


def part2_crossref():
    print("\n" + "=" * 70)
    print("PART 2 -- real cross-reference: Week 3 flagged records vs real FIRMS hotspots")
    print("=" * 70)
    with open("../../data/fire_ground_truth/residue_burning_flagged_records.json", encoding="utf-8") as f:
        flagged = json.load(f)
    firms = load_firms_csvs("../../data/fire_ground_truth/firms_pk_week3window*.csv")
    print(f"real flagged records: {len(flagged)}, real FIRMS points loaded for the window: {len(firms)}")

    import datetime as dt
    results = []
    for rec in flagged:
        d = dt.datetime.strptime(rec["date"], "%Y%m%d").date()
        window_dates = {(d + dt.timedelta(days=off)).isoformat() for off in (-1, 0, 1)}
        matches = []
        for p in firms:
            if p["date"] not in window_dates:
                continue
            dist = haversine_km(rec["lat"], rec["lon"], p["lat"], p["lon"])
            if dist <= 50:
                matches.append({"dist_km": round(dist, 1), **p})
        matches.sort(key=lambda m: m["dist_km"])
        results.append({**rec, "n_real_firms_matches_within_50km_1day": len(matches),
                         "nearest_match": matches[0] if matches else None})

    n_confirmed = sum(1 for r in results if r["n_real_firms_matches_within_50km_1day"] > 0)
    print(f"\n{n_confirmed}/{len(results)} flagged records have >=1 real FIRMS hotspot within 50km/+-1day")
    for r in results:
        tag = "REAL-FIRE-NEARBY" if r["n_real_firms_matches_within_50km_1day"] else "no-real-fire-nearby"
        print(f"  {r['district']:20s} {r['date']}  {tag:20s} n_matches={r['n_real_firms_matches_within_50km_1day']}")

    with open("../../data/fire_ground_truth/crossref_results.json", "w", encoding="utf-8") as f:
        json.dump({"n_flagged": len(results), "n_confirmed_real_fire_nearby": n_confirmed,
                   "tolerance": "50km, +/-1 day", "records": results}, f, indent=2)
    print("\nwrote ../../data/fire_ground_truth/crossref_results.json")


if __name__ == "__main__":
    part1_seasonal_profile()
    part2_crossref()
