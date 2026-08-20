#!/usr/bin/env python3
"""
load_seed_farms.py -- load the 120-farm Layyah/Muridke seed GeoJSON into the
farms table. Leaves farmer_id, district, crop_calendar all NULL/absent --
the source file has no farmer identity or crop attribute, only {id, date}
per feature (see CLAUDE.md decision: schema-only, no fabricated values).

Requires: pip install psycopg2-binary
Usage:
    python load_seed_farms.py \
        --geojson "C:\\Users\\USER\\Downloads\\farms_layyahMuridke_Kharif2025.geojson" \
        --dsn "postgresql://user:pass@localhost:5432/naip"
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--dsn", required=True, help="postgresql://user:pass@host:port/dbname")
    ap.add_argument("--source-dataset", default=None,
                     help="defaults to the geojson filename")
    a = ap.parse_args()

    import psycopg2

    with open(a.geojson, encoding="utf-8") as f:
        fc = json.load(f)

    source_dataset = a.source_dataset or a.geojson.replace("\\", "/").rsplit("/", 1)[-1]

    conn = psycopg2.connect(a.dsn)
    cur = conn.cursor()
    inserted, skipped = 0, 0
    for feat in fc["features"]:
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Polygon":
            skipped += 1
            continue
        source_feature_id = str(feat.get("id") or feat.get("properties", {}).get("id"))
        cur.execute(
            """
            INSERT INTO farms (boundary, source_dataset, source_feature_id)
            VALUES (ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s)
            """,
            (json.dumps(geom), source_dataset, source_feature_id),
        )
        inserted += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"loaded {inserted} farm polygons from {source_dataset} into farms "
          f"({skipped} skipped -- non-Polygon geometry). farmer_id and district left NULL.")


if __name__ == "__main__":
    main()
