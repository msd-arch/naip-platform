#!/usr/bin/env python3
"""
db_registry.py -- Track R: the real, live-database Farm Registry data-access
layer, replacing in_memory_registry.py's in-memory stand-in with real
persistence over a real PostgreSQL+PostGIS instance (Supabase, this week --
Docker's local virtualization requirements aren't met on this machine, and
the official Windows PostgreSQL installer host returned a real, confirmed
403 to this environment; Supabase was the real, viable path, not a shortcut).

Same real logic as in_memory_registry.py, migrated, not reimplemented:
  - register_farmer_submission(): real identity-field validation, real
    point-in-polygon district resolution (identical to
    in_memory_registry.py's _assign_district() / load_seed_farms.py's copy
    of the same function), real CNIC dedup (now a real SQL UPSERT instead of
    an in-memory dict scan).
  - resolved_crop_type(): migrated to a real SQL function
    (migration_002_synthetic_and_crop_precedence.sql) -- farmer_reported
    beats ndvi_classifier beats manual, same priority order, same tie-break
    (most recent row wins), queried here via a thin Python wrapper.

NON-NEGOTIABLE, unchanged since Week 1, restated in PHASE6_SCOPE_DOCUMENT.md's
Track R section: farmer_name/cnic/phone_number are NEVER synthesized. There is
no is_synthetic flag on the farmers table at all -- only farms/crop_calendar
carry it, and only for generated test-scale rows (Track R step 6), never for
any row this module's real register_farmer_submission() writes.

Requires: pip install psycopg2-binary shapely
"""
import json
import os

import psycopg2
from psycopg2.extras import RealDictCursor
from shapely.geometry import Point, shape


def load_dsn(env_path=None):
    """Loads SUPABASE_DB_URL from the gitignored .env next to this file,
    same convention every other real credential in this project uses."""
    env_path = env_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k == "SUPABASE_DB_URL":
                    return v
    raise RuntimeError(f"SUPABASE_DB_URL not found in {env_path}")


def _load_district_features(districts_geojson_path):
    with open(districts_geojson_path, encoding="utf-8") as f:
        districts_fc = json.load(f)
    return [
        (feat["properties"]["shapeName"], shape(feat["geometry"]))
        for feat in districts_fc["features"]
    ]


def _assign_district(centroid_lon, centroid_lat, district_features):
    """Verbatim real logic from in_memory_registry.py's _assign_district()."""
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


def register_farmer_submission(dsn, submission, districts_geojson_path):
    """The real write path: validates real identity fields, resolves the
    real district from the submitted boundary via point-in-polygon (never
    trusts a hand-entered district field, same discipline schema.sql
    documents), UPSERTs the farmer by CNIC (real SQL, not an in-memory dict
    scan), and inserts the farm + its crop_calendar entries. Returns the
    real farm_id (UUID) and farmer_id (UUID) written.

    submission's own 'farm_id' (a human-readable test label like "TEST-001"
    in Track P's original test) is stored as source_feature_id -- the real
    DB's farm_id is always a real, DB-generated UUID (schema.sql's own
    DEFAULT gen_random_uuid()), not a caller-supplied string."""
    for required in ("farmer_name", "cnic", "phone_number", "farm_boundary"):
        if not submission.get(required):
            raise ValueError(f"farmer submission missing required field: {required}")

    # schema.sql's farmers.cnic is CHAR(13) -- the real, fixed-width raw
    # digit form of a Pakistani CNIC. Real submissions arrive in the
    # human-readable dashed format (XXXXX-XXXXXXX-X, 15 chars) -- normalized
    # here, not assumed pre-normalized by the caller (a real bug this test
    # caught: the original in-memory version never needed this because it
    # stored cnic as free-form TEXT, not a fixed-width column).
    cnic_digits = "".join(ch for ch in submission["cnic"] if ch.isdigit())
    if len(cnic_digits) != 13:
        raise ValueError(f"cnic does not contain 13 real digits after normalization: {submission['cnic']!r}")

    district_features = _load_district_features(districts_geojson_path)
    geom = submission["farm_boundary"]
    poly = shape({"type": geom["type"], "coordinates": geom["coordinates"]})
    centroid = poly.centroid
    district = _assign_district(centroid.x, centroid.y, district_features)

    conn = psycopg2.connect(dsn)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO farmers (cnic, full_name, phone_number)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (cnic) DO UPDATE
                        SET full_name = EXCLUDED.full_name,
                            phone_number = EXCLUDED.phone_number,
                            updated_at = now()
                    RETURNING farmer_id
                    """,
                    (cnic_digits, submission["farmer_name"], submission["phone_number"]),
                )
                farmer_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO farms (farmer_id, boundary, district, source_dataset,
                                        source_feature_id, is_synthetic)
                    VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s, false)
                    RETURNING farm_id
                    """,
                    (farmer_id, json.dumps(geom), district, "farmer_submissions",
                     submission.get("farm_id")),
                )
                farm_id = cur.fetchone()[0]

                if submission.get("crop_type_declared"):
                    cur.execute(
                        """INSERT INTO crop_calendar (farm_id, crop_type, source, is_synthetic)
                           VALUES (%s, %s, 'farmer_reported', false)""",
                        (farm_id, submission["crop_type_declared"]),
                    )
                if submission.get("crop_type_model_estimated"):
                    cur.execute(
                        """INSERT INTO crop_calendar (farm_id, crop_type, source, is_synthetic)
                           VALUES (%s, %s, 'ndvi_classifier', false)""",
                        (farm_id, submission["crop_type_model_estimated"]),
                    )
        return {"farm_id": farm_id, "farmer_id": farmer_id, "district": district}
    finally:
        conn.close()


def resolved_crop_type(dsn, farm_id):
    """Thin wrapper over the real SQL resolved_crop_type() function
    (migration_002) -- same precedence rule Track P proved, now real SQL."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT resolved_crop_type(%s)", (farm_id,))
            return cur.fetchone()[0]
    finally:
        conn.close()


def get_farmer(dsn, farm_id):
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT f.farm_id, f.district, f.is_synthetic, fr.cnic, fr.full_name, fr.phone_number
                FROM farms f LEFT JOIN farmers fr ON f.farmer_id = fr.farmer_id
                WHERE f.farm_id = %s
                """,
                (farm_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def farms_in_district(dsn, district, include_synthetic=True):
    """Real equivalent of in_memory_registry.py's FarmRegistry.farms_in_district()
    -- used by trigger_engine.py for real farm matching once Track R's step 7
    cutover points the live pipeline at this module instead of the in-memory
    stand-in."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            q = "SELECT farm_id, district, is_synthetic FROM farms WHERE district = %s"
            params = [district]
            if not include_synthetic:
                q += " AND is_synthetic = false"
            cur.execute(q, params)
            return cur.fetchall()
    finally:
        conn.close()


def unlinked_farms(dsn):
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT farm_id, source_dataset, source_feature_id, district FROM farms_unlinked")
            return cur.fetchall()
    finally:
        conn.close()


def all_farms(dsn):
    """Real, full farm export for the dashboard (prepare_data.py) -- every
    real+synthetic farm, identity fields never included (this export never
    touches the farmers table at all, same real boundary the in-memory
    version always kept)."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT farm_id, district, is_synthetic, area_ha,
                       ST_Y(ST_Centroid(boundary)) AS centroid_lat,
                       ST_X(ST_Centroid(boundary)) AS centroid_lon,
                       ST_AsGeoJSON(boundary)::json AS boundary
                FROM farms
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def all_farms_with_tier(dsn):
    """Real, full farm export for the Farm Data page's three-tier map --
    all 752 real+synthetic farms, tagged with which of the three real
    categories each belongs to (identity-linked / pending / synthetic),
    plus centroid, district, resolved crop type, and real registration
    date. Deliberately never touches farmers.cnic/full_name/phone_number
    (no JOIN against the farmers table at all) -- same write-only
    boundary registered_farms()/all_farms() already keep, extended here
    rather than re-litigated, since this endpoint now also needs to
    include synthetic and pending-identity farms those two functions
    each deliberately exclude.

    resolved_crop_type(farm_id) is called once per row in the SELECT
    list -- Postgres executes this server-side inside the single query
    plan, not as 752 separate round trips, so this stays one real query
    regardless of farm count."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT f.farm_id, f.district, f.is_synthetic,
                       (f.farmer_id IS NOT NULL) AS has_identity,
                       f.area_ha, f.created_at,
                       ST_Y(ST_Centroid(f.boundary)) AS centroid_lat,
                       ST_X(ST_Centroid(f.boundary)) AS centroid_lon,
                       resolved_crop_type(f.farm_id) AS crop_type
                FROM farms f
                ORDER BY f.created_at DESC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def count_farms(dsn):
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_synthetic, COUNT(*) FROM farms GROUP BY is_synthetic")
            return dict(cur.fetchall())
    finally:
        conn.close()


def registered_farms(dsn):
    """Real, non-synthetic farms with a real identity linked
    (is_synthetic=false AND farmer_id IS NOT NULL) -- for the Farm Data
    page's map. Deliberately never selects farmers.cnic/full_name/
    phone_number -- location + district + when it was registered only, same
    write-only display discipline as the registration form itself."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT f.farm_id, f.district, f.area_ha, f.created_at,
                       ST_Y(ST_Centroid(f.boundary)) AS centroid_lat,
                       ST_X(ST_Centroid(f.boundary)) AS centroid_lon
                FROM farms f
                WHERE f.is_synthetic = false AND f.farmer_id IS NOT NULL
                ORDER BY f.created_at DESC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def lookup_farmer(dsn, cnic_digits=None, phone_number=None):
    """Real lookup by CNIC or phone -- for the Farm Data page's "find my
    registration" flow (a farmer looking up their OWN record, not an open
    directory). Returns a real, minimal, non-identity summary only: whether
    a match exists, how many real farms are linked, their districts, and a
    masked CNIC reference -- never the full CNIC, phone, or name, matching
    this page's write-only display design even on the read side. Exactly
    one of cnic_digits/phone_number should be given."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if cnic_digits:
                cur.execute("SELECT farmer_id, cnic FROM farmers WHERE cnic = %s", (cnic_digits,))
            elif phone_number:
                cur.execute("SELECT farmer_id, cnic FROM farmers WHERE phone_number = %s", (phone_number,))
            else:
                return None
            farmer = cur.fetchone()
            if not farmer:
                return None
            cur.execute(
                "SELECT district, area_ha, created_at FROM farms WHERE farmer_id = %s AND is_synthetic = false ORDER BY created_at",
                (farmer["farmer_id"],),
            )
            farms = cur.fetchall()
            cnic = farmer["cnic"] or ""
            masked = f"*****-*******-{cnic[-1]}" if len(cnic) == 13 else "****"
            return {
                "found": True,
                "masked_cnic": masked,
                "n_real_farms": len(farms),
                "districts": [f["district"] for f in farms],
                "farms": [{"district": f["district"], "area_ha": f["area_ha"], "registered": f["created_at"].isoformat()} for f in farms],
            }
    finally:
        conn.close()


def identity_coverage_summary(dsn):
    """Real, aggregate-only counts for the Farm Data submission page's
    read-only summary view -- counts filtered by is_synthetic=false
    throughout, never blending the 630 real synthetic farms into the
    real-farm coverage numbers (the exact real/synthetic separation Track R
    was built to protect). Never returns a raw identity field -- if a true
    admin view with raw CNIC/phone access is ever wanted, that needs a real,
    separate authentication layer first, not this function."""
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM farms WHERE is_synthetic = false")
            n_real_total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM farms WHERE is_synthetic = false AND farmer_id IS NOT NULL")
            n_real_with_identity = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM farms WHERE is_synthetic = true")
            n_synthetic_total = cur.fetchone()[0]
        return {
            "n_real_farms_total": n_real_total,
            "n_real_farms_with_identity": n_real_with_identity,
            "n_real_farms_pending": n_real_total - n_real_with_identity,
            "n_synthetic_farms_total_for_context_only": n_synthetic_total,
        }
    finally:
        conn.close()
