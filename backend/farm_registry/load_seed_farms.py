#!/usr/bin/env python3
"""
load_seed_farms.py -- load the 120-farm Layyah/Muridke seed GeoJSON into the
farms table. farmer_id/crop_calendar are left NULL/absent -- the source file
has no farmer identity or crop attribute, only {id, date} per feature (see
CLAUDE.md decision: schema-only, no fabricated values).

Track R (real DB deployment): district is now resolved via the exact same
real point-in-polygon logic in_memory_registry.py's _assign_district()
already proved (centroid-in-polygon against the real national district set,
nearest-centroid fallback for edge cases) -- reused here via direct
duplication of that small function rather than a cross-module import, since
in_memory_registry.py is the in-memory stand-in this track is replacing and
importing from it here would create a real, confusing dependency in the
wrong direction. Same real logic, not reimplemented from scratch.

Requires: pip install psycopg2-binary shapely
Usage:
    python load_seed_farms.py \
        --geojson "C:\\Users\\USER\\Downloads\\farms_layyahMuridke_Kharif2025.geojson" \
        --districts-geojson "..\\..\\data\\seed\\pk_districts.geojson" \
        --dsn "postgresql://user:pass@localhost:5432/naip"
"""
import argparse
import json


def _assign_district(centroid_lon, centroid_lat, district_features):
    """Verbatim real logic from in_memory_registry.py's _assign_district()."""
    from shapely.geometry import Point
    pt = Point(centroid_lon, centroid_lat)
    for name, geom in district_features:
        if geom.contains(pt):
            return name
    best, best_dist = None, None
    for name, geom in district_features:
        d = geom.distance(pt)
        if best_dist is None or d < best_dist:
            best, best_dist = name, d
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--districts-geojson", required=True)
    ap.add_argument("--dsn", required=True, help="postgresql://user:pass@host:port/dbname")
    ap.add_argument("--source-dataset", default=None,
                     help="defaults to the geojson filename")
    a = ap.parse_args()

    import psycopg2
    from shapely.geometry import shape

    with open(a.geojson, encoding="utf-8") as f:
        fc = json.load(f)
    with open(a.districts_geojson, encoding="utf-8") as f:
        districts_fc = json.load(f)
    district_features = [
        (feat["properties"]["shapeName"], shape(feat["geometry"]))
        for feat in districts_fc["features"]
    ]

    source_dataset = a.source_dataset or a.geojson.replace("\\", "/").rsplit("/", 1)[-1]

    conn = psycopg2.connect(a.dsn)
    cur = conn.cursor()
    inserted, skipped = 0, 0
    for feat in fc["features"]:
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Polygon":
            skipped += 1
            continue
        centroid = shape(geom).centroid
        district = _assign_district(centroid.x, centroid.y, district_features)
        source_feature_id = str(feat.get("id") or feat.get("properties", {}).get("id"))
        cur.execute(
            """
            INSERT INTO farms (boundary, district, source_dataset, source_feature_id)
            VALUES (ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s)
            """,
            (json.dumps(geom), district, source_dataset, source_feature_id),
        )
        inserted += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"loaded {inserted} farm polygons from {source_dataset} into farms "
          f"({skipped} skipped -- non-Polygon geometry), real point-in-polygon district "
          "resolved for each. farmer_id left NULL.")


if __name__ == "__main__":
    main()
