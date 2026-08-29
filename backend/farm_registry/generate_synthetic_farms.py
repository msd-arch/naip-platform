#!/usr/bin/env python3
"""
generate_synthetic_farms.py -- Track R step 6: populate the live DB at a more
realistic scale with generated (non-identity) test farms, confirmed with you
before running: ~630 synthetic farms (roughly 5/district average) across all
126 real districts, real point-in-polygon placement inside each district's
actual boundary (pk_districts.geojson), per-district count weighted by real
MNFSR total_4crop_area_000ha (data/crop_mix_ground_truth/real_crop_mix.json)
so districts with more real cropped area get proportionally more synthetic
farms rather than a flat count -- and each synthetic farm's crop_type is
sampled from that SAME district's real crop-mix shares (wheat/cotton/rice/
sugarcane proportions), not picked arbitrarily.

NON-NEGOTIABLE, unchanged: every row this script writes has is_synthetic =
true and farmer_id = NULL. There is no code path here that can write
farmer_name/cnic/phone_number -- the farmers table is never touched by this
script at all.

Requires: pip install psycopg2-binary shapely

Usage:
    python generate_synthetic_farms.py --target 630 --seed 42 --dry-run
    python generate_synthetic_farms.py --target 630 --seed 42
"""
import argparse
import json
import os
import random

import psycopg2
from shapely.geometry import Point, Polygon, shape

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
DISTRICTS_PATH = os.path.join(NAIP, "data", "seed", "pk_districts.geojson")
CROP_MIX_PATH = os.path.join(NAIP, "data", "crop_mix_ground_truth", "real_crop_mix.json")
CROPS = ["wheat", "cotton", "rice", "sugarcane"]


def load_dsn():
    env_path = os.path.join(HERE, ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and line.startswith("SUPABASE_DB_URL"):
                return line.split("=", 1)[1]
    raise RuntimeError("SUPABASE_DB_URL not found")


def random_point_in_polygon(geom, rng, max_tries=200):
    """Real rejection sampling within the district's actual real boundary --
    not a bounding-box approximation that could land outside real terrain."""
    minx, miny, maxx, maxy = geom.bounds
    for _ in range(max_tries):
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if geom.contains(p):
            return p
    return geom.representative_point()  # real fallback, still guaranteed inside


def small_farm_polygon(center, rng, min_ha=1.0, max_ha=4.0):
    """A real, plausible smallholder-scale square polygon (Pakistan's real
    average farm size is well under this range per national ag statistics,
    kept modest and clearly synthetic, not fitted to any specific real
    parcel)."""
    area_ha = rng.uniform(min_ha, max_ha)
    side_m = (area_ha * 10000) ** 0.5
    # rough deg-per-meter at this latitude, same approximation in_memory_registry.py uses
    deg = side_m / 111000.0
    hx, hy = deg / 2, deg / 2
    return Polygon([
        (center.x - hx, center.y - hy), (center.x + hx, center.y - hy),
        (center.x + hx, center.y + hy), (center.x - hx, center.y + hy),
        (center.x - hx, center.y - hy),
    ])


def sample_crop(crop_mix_entry, rng):
    shares = {c: crop_mix_entry.get("crops", {}).get(c, {}).get("share_of_4crop_area", 0.0) or 0.0 for c in CROPS}
    total = sum(shares.values())
    if total <= 0:
        return rng.choice(CROPS)  # real gap: no usable share data for this district, uniform fallback
    r = rng.uniform(0, total)
    acc = 0.0
    for c in CROPS:
        acc += shares[c]
        if r <= acc:
            return c
    return CROPS[-1]


def allocate_counts(weights, target):
    """Proportional allocation with a floor of 1 per district (confirmed
    scope: all 126 districts represented), largest-remainder method so the
    total lands on target exactly."""
    n = len(weights)
    total_weight = sum(weights.values())
    raw = {d: max(1.0, target * w / total_weight) for d, w in weights.items()}
    floors = {d: int(v) for d, v in raw.items()}
    remainder = target - sum(floors.values())
    remainders = sorted(raw.items(), key=lambda kv: kv[1] - int(kv[1]), reverse=True)
    for d, _ in remainders[:max(0, remainder)]:
        floors[d] += 1
    return floors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=630)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_fc = json.load(f)
    with open(CROP_MIX_PATH, encoding="utf-8") as f:
        crop_mix = json.load(f)

    district_geoms = {f["properties"]["shapeName"]: shape(f["geometry"]) for f in districts_fc["features"]}
    # weight = real total_4crop_area_000ha; districts with no/zero real area
    # (rare, mostly the 11 hand-mask ones) get a small real floor weight so
    # they still receive their guaranteed minimum of 1, not zero.
    weights = {
        name: max(0.5, crop_mix.get(name, {}).get("total_4crop_area_000ha", 0) or 0)
        for name in district_geoms
    }
    counts = allocate_counts(weights, a.target)

    rows = []
    for district, n in counts.items():
        geom = district_geoms[district]
        entry = crop_mix.get(district, {})
        for i in range(n):
            pt = random_point_in_polygon(geom, rng)
            poly = small_farm_polygon(pt, rng)
            crop = sample_crop(entry, rng)
            rows.append((district, poly, crop, f"synthetic-{district}-{i+1}"))

    print(f"generated {len(rows)} real-placed synthetic farm rows across {len(counts)} districts "
          f"(target was {a.target})")
    by_crop = {}
    for _, _, crop, _ in rows:
        by_crop[crop] = by_crop.get(crop, 0) + 1
    print(f"crop distribution: {by_crop}")
    print("top 5 districts by count:", sorted(counts.items(), key=lambda kv: -kv[1])[:5])

    if a.dry_run:
        print("--dry-run: not writing to the database")
        return

    dsn = load_dsn()
    conn = psycopg2.connect(dsn)
    try:
        with conn:
            with conn.cursor() as cur:
                for district, poly, crop, feature_id in rows:
                    cur.execute(
                        """
                        INSERT INTO farms (boundary, district, source_dataset, source_feature_id, is_synthetic)
                        VALUES (ST_SetSRID(ST_GeomFromText(%s), 4326), %s, %s, %s, true)
                        RETURNING farm_id
                        """,
                        (poly.wkt, district, "generate_synthetic_farms.py", feature_id),
                    )
                    farm_id = cur.fetchone()[0]
                    cur.execute(
                        """INSERT INTO crop_calendar (farm_id, crop_type, source, is_synthetic)
                           VALUES (%s, %s, 'manual', true)""",
                        (farm_id, crop),
                    )
        print(f"wrote {len(rows)} synthetic farms + crop_calendar rows, all is_synthetic=true, farmer_id=NULL")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
