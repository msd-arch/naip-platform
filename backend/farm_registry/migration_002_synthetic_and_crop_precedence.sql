-- Track R migration 002: real, incremental additions on top of the original
-- Week 1 schema.sql -- kept as a separate, clearly-labeled migration rather
-- than silently rewriting schema.sql, so schema.sql stays the real record of
-- what Week 1 actually shipped.
--
-- 1. is_synthetic on farms/crop_calendar: the real, non-negotiable boundary
--    restated in PHASE6_SCOPE_DOCUMENT.md's Track R section -- synthetic
--    farm polygons/districts/crop calendars are fine for populating the DB
--    at a realistic scale, structurally tagged and separable from the 120
--    real seed farms. farmers.* (name/cnic/phone) has NO such flag and NEVER
--    gets one -- there is no synthetic-identity path, by design; identity
--    fields stay NULL until a real Track P submission fills them.
-- 2. resolved_crop_type(): a real SQL function implementing the exact
--    precedence rule Track P proved in in_memory_registry.py's
--    Farm.resolved_crop_type() -- farmer_reported beats ndvi_classifier
--    beats manual, most-recently-created row wins within a tied source.
--    Same real logic, real persistence.

ALTER TABLE farms ADD COLUMN IF NOT EXISTS is_synthetic BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE crop_calendar ADD COLUMN IF NOT EXISTS is_synthetic BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN farms.is_synthetic IS
  'true only for generated test-scale farms (Track R step 6) -- the 120 real Layyah/Muridke seed farms are always false. Never true for any row with a non-NULL farmer_id linked to real identity data.';
COMMENT ON COLUMN crop_calendar.is_synthetic IS
  'true only for generated test-scale crop calendars attached to a synthetic farm. Independent of farms.is_synthetic in principle (a real farm could theoretically get a synthetic calendar row) but Track R never actually does that -- kept as its own flag for honesty, not inferred from the parent farm.';

CREATE INDEX IF NOT EXISTS farms_is_synthetic_idx ON farms (is_synthetic);

CREATE OR REPLACE FUNCTION resolved_crop_type(p_farm_id UUID)
RETURNS TEXT AS $$
    SELECT crop_type
    FROM crop_calendar
    WHERE farm_id = p_farm_id AND crop_type IS NOT NULL
    ORDER BY
        CASE source
            WHEN 'farmer_reported' THEN 1
            WHEN 'ndvi_classifier' THEN 2
            WHEN 'manual' THEN 3
            ELSE 4
        END,
        created_at DESC
    LIMIT 1;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION resolved_crop_type IS
  'Track P''s real precedence rule, migrated to SQL: a real farmer-reported crop_calendar entry always wins over an ndvi_classifier (model-estimated) one for the same farm -- verbatim port of in_memory_registry.py''s Farm.resolved_crop_type(), same source-tag priority order, not re-derived.';
