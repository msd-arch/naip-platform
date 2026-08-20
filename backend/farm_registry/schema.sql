-- NAIP Farm Registry (module 6.1) — PostGIS schema
--
-- Scope: fields NAIP needs to run hazard/insurance/advisory logic against a farm,
-- plus a link-out reference to the external system of record. This is NOT a
-- land-records system — it does not attempt to replicate PLRA parcel history,
-- ownership chains, or Kissan Card eligibility rules. Where NAIP needs a fact
-- that PLRA/Kissan Card already own, we store a reference ID and link out,
-- not a duplicated copy.
--
-- Status: schema-only as of Week 1 — no Docker/Postgres available on the dev
-- machine this session, so this has not been executed against a live instance.
-- Run against any PostGIS >= 3.x instance:
--   psql -d naip -f schema.sql

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ---------------------------------------------------------------- farmers
-- CNIC is the de-duplication key. One farmer can own/operate multiple farms.
-- CNIC is sensitive PII (per CLAUDE.md: financial-sector-grade handling) —
-- store it, but callers outside the registry/insurance/subsidy path should
-- query by farmer_id, not cnic.
CREATE TABLE farmers (
    farmer_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cnic               CHAR(13) UNIQUE,            -- nullable: not every seed record has one yet
    full_name          TEXT,
    phone_number       TEXT,                        -- for SMS/USSD/IVR delivery (6.9), primary channel
    kissan_card_ref    TEXT,                         -- external Kissan Card ID, link-out only, not validated here
    plra_owner_ref     TEXT,                         -- external PLRA owner/CNIC-linked record ID, link-out only
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN farmers.cnic IS
  'De-duplication key. Nullable because seed data (120-farm Layyah/Muridke set) has no farmer identity attached yet — only polygon + date.';
COMMENT ON COLUMN farmers.plra_owner_ref IS
  'Reference/link-out to Punjab Land Records Authority record — NAIP does not store or reconcile PLRA ownership history itself.';

-- ---------------------------------------------------------------- farms
-- One row per field/farm polygon. A farmer can have many; a farm can (rarely,
-- during transfer/dispute) have an unresolved farmer_id — kept nullable.
CREATE TABLE farms (
    farm_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id          UUID REFERENCES farmers(farmer_id) ON DELETE SET NULL,
    boundary           GEOMETRY(Polygon, 4326) NOT NULL,
    area_ha            DOUBLE PRECISION GENERATED ALWAYS AS
                          (ST_Area(boundary::geography) / 10000.0) STORED,
    district           TEXT,                         -- filled by a join against the admin2 boundary set, not hand-entered
    plra_khasra_ref    TEXT,                          -- external PLRA khasra/khewat number, link-out only
    source_dataset     TEXT NOT NULL,                 -- provenance, e.g. 'farms_layyahMuridke_Kharif2025.geojson'
    source_feature_id  TEXT,                          -- original feature id/properties.id from the source file
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX farms_boundary_gix ON farms USING GIST (boundary);
CREATE INDEX farms_farmer_id_idx ON farms (farmer_id);
CREATE INDEX farms_district_idx ON farms (district);

COMMENT ON COLUMN farms.district IS
  'Populated via ST_Within/ST_Intersects against the national admin2 boundary set (data/seed/pk_districts.geojson) — see backend/alerts/district_aggregate.py. Not authoritative for land-record purposes.';
COMMENT ON COLUMN farms.source_dataset IS
  'Always set — every row must be traceable to the file/import batch it came from. No fabricated farm rows.';

-- ---------------------------------------------------------------- crop_calendar
-- Per-farm, per-season crop record. A farm can have multiple seasons over time
-- (Kharif/Rabi), so this is a child table, not columns on farms.
CREATE TABLE crop_calendar (
    crop_calendar_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id            UUID NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
    season_label       TEXT,                          -- e.g. 'Kharif 2025', 'Rabi 2025-26'
    crop_type          TEXT,                          -- nullable: unknown until an NDVI-phenology classifier (6.3) or manual entry fills it
    sowing_date        DATE,
    expected_harvest_date DATE,
    actual_harvest_date   DATE,
    source              TEXT NOT NULL DEFAULT 'manual', -- 'manual' | 'ndvi_classifier' | 'farmer_reported'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX crop_calendar_farm_id_idx ON crop_calendar (farm_id);

COMMENT ON TABLE crop_calendar IS
  'Empty of real crop_type data as of Week 1 — the 120-farm seed file has no crop attribute, only {id, date}. Populate once 6.3 (NDVI phenology classifier) exists or farmer-reported data is collected.';

-- ---------------------------------------------------------------- dedup helper view
-- Farmers with the same CNIC but multiple farmer_id rows should not happen
-- (CNIC is UNIQUE), but farms with no farmer_id (unlinked seed data) are
-- expected at this stage — this view makes that visible rather than hiding it.
CREATE VIEW farms_unlinked AS
    SELECT farm_id, source_dataset, source_feature_id, district
    FROM farms
    WHERE farmer_id IS NULL;

COMMENT ON VIEW farms_unlinked IS
  'Farms with no linked farmer identity. Expect this to be ~all 120 seed rows until CNIC-linked identity is collected — that is Week 1''s honest starting state, not a bug.';
