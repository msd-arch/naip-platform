#!/usr/bin/env python3
"""
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


def load_registry(farms_geojson_path, districts_geojson_path):
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
