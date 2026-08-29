#!/usr/bin/env python3
"""
SUPERSEDED 2026-08-29 (Track R cutover) -- kept for historical reference and
as the documented origin of the real logic db_registry.py migrated (the
write path, CNIC dedup, resolved_crop_type() precedence rule), NOT imported
by any real live code path anymore. trigger_engine.py, run_end_to_end_demo.py,
and naip_dashboard/prepare_data.py all now use backend/farm_registry/
db_registry.py against the real live PostgreSQL+PostGIS database (Supabase).
Do not reach for this module for anything real going forward -- if you find
yourself about to import in_memory_registry, that's a sign something didn't
get migrated to db_registry.py and should be, not a sign to fall back to this.

in_memory_registry.py -- Farm Registry, in-memory this week.

WHY: no Docker/PostGIS on this machine since Week 1 (checked again this
week, still absent). Deploying Postgres this week would not fix the real
blocker anyway -- "this farm, this hazard, this crop" needs a per-farm crop
type, which no data source has provided in any of the 4 sprints. So this
mirrors schema.sql's real structure (same tables, same columns, same
nullability) as plain Python dataclasses loaded from the real 120-farm
GeoJSON + the real district boundary set, instead of standing up a database
that would sit on the same NULL crop_type/cnic columns a live Postgres
instance would.

If/when Docker+Postgres gets deployed post-MVP, `load_seed_farms.py`
(already written, Week 1) loads the identical source file into the identical
schema -- this module is not a divergent design, it is schema.sql without a
database underneath it.

Every field here is real: real farm polygons (Downloads/farms_layyahMuridke_
Kharif2025.geojson, 120 features), real district assignment (point-in-
polygon against data/seed/pk_districts.geojson, same source Week 1 used for
national hazard sampling). farmer_id, cnic, crop_type remain None/NULL --
same honest gap as the SQL schema, not hidden by this being in-memory.
"""
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import shape


@dataclass
class Farmer:
    farmer_id: Optional[str] = None
    cnic: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    kissan_card_ref: Optional[str] = None
    plra_owner_ref: Optional[str] = None


@dataclass
class CropCalendarEntry:
    season_label: Optional[str] = None
    crop_type: Optional[str] = None
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    actual_harvest_date: Optional[str] = None
    source: str = "manual"


@dataclass
class Farm:
    farm_id: str
    boundary_geojson: dict
    centroid_lat: float
    centroid_lon: float
    area_ha: float
    district: Optional[str]
    source_dataset: str
    source_feature_id: str
    farmer_id: Optional[str] = None
    plra_khasra_ref: Optional[str] = None
    crop_calendar: list = field(default_factory=list)  # list[CropCalendarEntry], empty = real gap

    def resolved_crop_type(self) -> Optional[str]:
        """Track P precedence rule: a real farmer-reported crop_calendar entry
        always wins over an ndvi_classifier (model-estimated) one for the same
        farm, per schema.sql's documented crop_calendar.source enum ('manual'
        | 'ndvi_classifier' | 'farmer_reported'). Multiple entries of the same
        source are allowed (Kharif/Rabi over time) -- this takes the most
        recently appended entry of the winning source, not the first."""
        by_source: dict[str, str] = {}
        for entry in self.crop_calendar:
            if entry.crop_type:
                by_source[entry.source] = entry.crop_type
        return by_source.get("farmer_reported") or by_source.get("ndvi_classifier") or by_source.get("manual")


class FarmRegistry:
    def __init__(self):
        self.farmers: dict[str, Farmer] = {}
        self.farms: dict[str, Farm] = {}

    def farms_in_district(self, district_name):
        return [f for f in self.farms.values() if f.district == district_name]

    def unlinked_farms(self):
        """Mirrors schema.sql's farms_unlinked view."""
        return [f for f in self.farms.values() if f.farmer_id is None]


def _assign_district(centroid_lon, centroid_lat, district_features):
    """Point-in-polygon district assignment, matching schema.sql's documented
    approach (ST_Within against the admin2 set) -- done here with shapely
    since there's no live PostGIS to run ST_Within in."""
    from shapely.geometry import Point
    pt = Point(centroid_lon, centroid_lat)
    for name, geom in district_features:
        if geom.contains(pt):
            return name
    # fall back to nearest district centroid if the farm point falls just
    # outside every polygon (simplified/coarse boundary edge case) -- still
    # real geometry, just a nearest-match fallback, not a fabricated value
    best, best_dist = None, None
    for name, geom in district_features:
        d = geom.distance(pt)
        if best_dist is None or d < best_dist:
            best, best_dist = name, d
    return best


def _default_submissions_path(farms_geojson_path):
    return os.path.join(os.path.dirname(os.path.abspath(farms_geojson_path)), "farmer_submissions.json")


def _load_submissions(submissions_path):
    if not submissions_path or not os.path.exists(submissions_path):
        return []
    with open(submissions_path, encoding="utf-8") as f:
        return json.load(f)


def _apply_submission(registry, submission, district_features):
    """The one real place a farmer submission becomes Farmer/Farm rows --
    used both to replay persisted submissions on every load_registry() call
    and by register_farmer_submission() for a brand-new one, so there is
    exactly one code path, not a parallel "real" one and a test bypass.

    Required identity fields (farmer_name, cnic, phone_number) are real PII,
    provided directly by the person they describe -- validated as present,
    never fabricated or defaulted. district is ALWAYS recomputed from the
    real boundary via point-in-polygon (schema.sql: "Populated via
    ST_Within... not hand-entered"), never trusted from the submission's own
    (possibly test-placeholder) district field.
    """
    for required in ("farmer_name", "cnic", "phone_number", "farm_id", "farm_boundary"):
        if not submission.get(required):
            raise ValueError(f"farmer submission missing required field: {required}")

    cnic = submission["cnic"]
    existing_farmer_id = next(
        (fid for fid, f in registry.farmers.items() if f.cnic == cnic), None
    )
    if existing_farmer_id:
        farmer_id = existing_farmer_id
        farmer = registry.farmers[farmer_id]
        farmer.full_name = submission["farmer_name"]
        farmer.phone_number = submission["phone_number"]
    else:
        farmer_id = f"farmer-{uuid.uuid4().hex[:12]}"
        registry.farmers[farmer_id] = Farmer(
            farmer_id=farmer_id,
            cnic=cnic,
            full_name=submission["farmer_name"],
            phone_number=submission["phone_number"],
        )

    geom = submission["farm_boundary"]
    poly = shape({"type": geom["type"], "coordinates": geom["coordinates"]})
    centroid = poly.centroid
    district = _assign_district(centroid.x, centroid.y, district_features)

    crop_calendar = []
    if submission.get("crop_type_declared"):
        crop_calendar.append(CropCalendarEntry(
            crop_type=submission["crop_type_declared"], source="farmer_reported"))
    if submission.get("crop_type_model_estimated"):
        crop_calendar.append(CropCalendarEntry(
            crop_type=submission["crop_type_model_estimated"], source="ndvi_classifier"))

    farm_id = submission["farm_id"]
    registry.farms[farm_id] = Farm(
        farm_id=farm_id,
        boundary_geojson=geom,
        centroid_lat=centroid.y,
        centroid_lon=centroid.x,
        area_ha=poly.area * 111.0 * 111.0 * 100,
        district=district,
        source_dataset="farmer_submissions.json",
        source_feature_id=farm_id,
        farmer_id=farmer_id,
        crop_calendar=crop_calendar,
    )
    return registry.farms[farm_id]


def register_farmer_submission(registry, submission, districts_geojson_path, submissions_path=None):
    """Track P Part 1: the real write path for a farmer-submitted identity +
    farm record. Validates, applies via _apply_submission (real district
    point-in-polygon, real CNIC dedup), then persists to submissions_path
    (append-only JSON list) so the record survives a fresh load_registry()
    call, not just this process. submissions_path defaults next to the real
    120-farm seed file, gitignored (data/seed/farmer_submissions.json) --
    real PII, never committed."""
    with open(districts_geojson_path, encoding="utf-8") as f:
        districts_fc = json.load(f)
    district_features = [
        (feat["properties"]["shapeName"], shape(feat["geometry"]))
        for feat in districts_fc["features"]
    ]

    farm = _apply_submission(registry, submission, district_features)

    if submissions_path is None:
        submissions_path = os.path.join(os.path.dirname(os.path.abspath(districts_geojson_path)), "farmer_submissions.json")
    existing = _load_submissions(submissions_path)
    existing = [s for s in existing if s.get("farm_id") != submission["farm_id"]]
    existing.append(submission)
    os.makedirs(os.path.dirname(submissions_path), exist_ok=True)
    with open(submissions_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    return farm


def load_registry(farms_geojson_path, districts_geojson_path, submissions_path=None):
    registry = FarmRegistry()

    with open(districts_geojson_path, encoding="utf-8") as f:
        districts_fc = json.load(f)
    district_features = [
        (feat["properties"]["shapeName"], shape(feat["geometry"]))
        for feat in districts_fc["features"]
    ]

    with open(farms_geojson_path, encoding="utf-8") as f:
        farms_fc = json.load(f)

    source_dataset = os.path.basename(farms_geojson_path)
    for feat in farms_fc["features"]:
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Polygon":
            continue
        poly = shape(geom)
        centroid = poly.centroid
        source_feature_id = str(feat.get("id") or feat.get("properties", {}).get("id"))
        district = _assign_district(centroid.x, centroid.y, district_features)
        farm_id = f"farm-{source_feature_id}"
        registry.farms[farm_id] = Farm(
            farm_id=farm_id,
            boundary_geojson=geom,
            centroid_lat=centroid.y,
            centroid_lon=centroid.x,
            area_ha=poly.area * 111.0 * 111.0 * 100,  # rough deg^2->ha, fine for this scale/purpose
            district=district,
            source_dataset=source_dataset,
            source_feature_id=source_feature_id,
            crop_calendar=[],  # real gap: no crop_type source exists, not fabricated
        )

    # Real Track P farmer submissions (identity-collection path), if any exist
    # yet -- replayed on every load so a registered farmer/farm is visible to
    # every consumer (trigger_engine.py, run_end_to_end_demo.py) that calls
    # load_registry() fresh, not just the process that wrote them.
    if submissions_path is None:
        submissions_path = _default_submissions_path(farms_geojson_path)
    for submission in _load_submissions(submissions_path):
        _apply_submission(registry, submission, district_features)

    return registry


if __name__ == "__main__":
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    farms_path = os.path.join(here, "..", "..", "data", "seed", "farms_layyahMuridke_Kharif2025.geojson")
    districts_path = os.path.join(here, "..", "..", "data", "seed", "pk_districts.geojson")

    reg = load_registry(farms_path, districts_path)
    print(f"loaded {len(reg.farms)} real farm polygons")
    from collections import Counter
    by_district = Counter(f.district for f in reg.farms.values())
    print("district assignment (real point-in-polygon):")
    for d, n in by_district.most_common():
        print(f"  {d}: {n}")
    print(f"\nunlinked (no farmer_id): {len(reg.unlinked_farms())}/{len(reg.farms)} "
          "-- expected, same honest gap as schema.sql's farms_unlinked view")
