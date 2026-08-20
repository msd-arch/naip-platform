#!/usr/bin/env python3
"""
canal_water_stress.py -- satellite-ET-only water-equity index for one real
canal distributary near the Muridke pilot cluster.

SCOPE, read before trusting any number this produces:
  - Canal-command geometry: no official WAPDA/PID canal-command polygon
    dataset exists anywhere accessible (checked HDX, geoBoundaries, GEE
    catalog -- all empty/absent for Pakistan irrigation infrastructure, see
    Week 2 status report). What IS real: OpenStreetMap has an actual,
    named "Muridke Distributary" centerline (15 way segments, verified via
    Overpass API). This script stitches those into one line and buffers it
    by an ASSUMED 500m half-width (1km total corridor) -- a labeled
    approximation of a command area, not a surveyed or official one. Every
    output row says so.
  - Head/tail ordering: derived from the stitched line's own topology (the
    one endpoint with no matching neighbor = one end, the other = the other
    end). This has NOT been verified against real flow direction / canal
    offtake records -- it is a geometric ordering, not a hydraulically
    confirmed head-to-tail direction. Flagged in the output.
  - Water balance: real MODIS MOD16A2 actual-ET and potential-ET (8-day,
    500m, real satellite product), summed over the real Apr-Oct 2025 Kharif
    window. Stress index = 1 - (ET/PET) per segment -- standard evaporative-
    deficit framing, no invented formula.
  - No IRSA/PID canal allocation records are used or compared against --
    architecture.md 6.4 requires those for the full module and NAIP doesn't
    have that partnership. This is satellite-ET-only demo mode, explicitly.

Usage:
    python canal_water_stress.py --project printtheory --canal-raw muridke_distributary_raw.json --out water_stress.json
"""
import argparse
import json
import math

import ee
from shapely.geometry import LineString, Point, mapping
from shapely.ops import transform
import pyproj


SEGMENT_LENGTH_M = 3000.0  # sample the canal every 3km, head to tail
BUFFER_HALFWIDTH_M = 500.0  # ASSUMED corridor half-width, not measured
SEASON_START, SEASON_END = "2025-04-01", "2025-11-01"  # Kharif 2025, matches 6.3


def stitch_ways(ways):
    """Chain OSM way segments end-to-start into one ordered polyline.
    Ways in Overpass output are not guaranteed pre-ordered -- match shared
    endpoints greedily. Real coordinates throughout, no interpolation
    beyond simple endpoint-chaining."""
    remaining = [list(map(tuple, w)) for w in ways]
    chain = remaining.pop(0)
    changed = True
    while remaining and changed:
        changed = False
        head, tail = chain[0], chain[-1]
        for i, w in enumerate(remaining):
            if w[0] == tail:
                chain = chain + w[1:]
                remaining.pop(i); changed = True; break
            if w[-1] == tail:
                chain = chain + list(reversed(w))[1:]
                remaining.pop(i); changed = True; break
            if w[-1] == head:
                chain = w[:-1] + chain
                remaining.pop(i); changed = True; break
            if w[0] == head:
                chain = list(reversed(w))[:-1] + chain
                remaining.pop(i); changed = True; break
    if remaining:
        print(f"WARNING: {len(remaining)} way segment(s) did not chain onto the main line "
              f"(disconnected in OSM data) -- excluded from the stitched canal, not fabricated in.")
    return chain


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--canal-raw", default="muridke_distributary_raw.json")
    ap.add_argument("--out", default="water_stress.json")
    ap.add_argument("--out-geojson", default="water_stress_segments.geojson")
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(a.canal_raw, encoding="utf-8") as f:
        raw = json.load(f)
    chain = stitch_ways(raw["ways"])
    print(f"stitched {len(raw['ways'])} OSM ways into one line, {len(chain)} vertices, "
          f"head={chain[0]}, tail={chain[-1]}")

    line_wgs84 = LineString(chain)

    # project to UTM 43N (covers this part of Punjab) for real metre-based
    # length/buffer/sampling instead of doing distance math in degrees
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
    to_wgs = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform
    line_utm = transform(to_utm, line_wgs84)
    total_len_m = line_utm.length
    print(f"canal length (stitched, OSM-derived): {total_len_m/1000:.1f} km")

    n_segments = max(2, int(total_len_m // SEGMENT_LENGTH_M) + 1)
    sample_dists = [min(i * SEGMENT_LENGTH_M, total_len_m) for i in range(n_segments)]

    segments = []
    for i, d in enumerate(sample_dists):
        pt_utm = line_utm.interpolate(d)
        pt_wgs = transform(to_wgs, pt_utm)
        cell_utm = pt_utm.buffer(BUFFER_HALFWIDTH_M)
        cell_wgs = transform(to_wgs, cell_utm)
        segments.append({
            "segment_id": i,
            "dist_from_head_km": round(d / 1000.0, 2),
            "position": "head" if i == 0 else ("tail" if i == n_segments - 1 else "mid"),
            "lat": pt_wgs.y, "lon": pt_wgs.x,
            "cell_geom": mapping(cell_wgs),
        })
    print(f"sampled {n_segments} segments along the canal every {SEGMENT_LENGTH_M/1000:.0f}km")

    # ---- real MODIS MOD16A2 ET/PET, season sum ----
    mod16 = (ee.ImageCollection("MODIS/061/MOD16A2")
             .filterDate(SEASON_START, SEASON_END))

    def scale_mask(img):
        # MOD16A2: scale 0.1 kg/m2/8day == 0.1 mm/8day; ET_QC bit 0 = 0 -> good
        qc = img.select("ET_QC")
        good = qc.bitwiseAnd(1).eq(0)
        et = img.select("ET").multiply(0.1).updateMask(good)
        pet = img.select("PET").multiply(0.1).updateMask(good)
        return et.rename("et_mm").addBands(pet.rename("pet_mm"))

    season_sum = mod16.map(scale_mask).sum()  # sum of real valid 8-day composites -> season total mm

    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry(s["cell_geom"]), {"segment_id": s["segment_id"]}) for s in segments
    ])
    reduced = season_sum.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=500).getInfo()

    by_id = {f["properties"]["segment_id"]: f["properties"] for f in reduced["features"]}
    for s in segments:
        props = by_id.get(s["segment_id"], {})
        et = props.get("et_mm")
        pet = props.get("pet_mm")
        s["season_et_mm"] = round(et, 1) if et is not None else None
        s["season_pet_mm"] = round(pet, 1) if pet is not None else None
        s["stress_index"] = round(1 - (et / pet), 3) if (et is not None and pet is not None and pet > 0) else None
        del s["cell_geom"]

    valid = [s for s in segments if s["stress_index"] is not None]
    print(f"{len(valid)}/{len(segments)} segments got a real ET/PET stress index")

    head = segments[0]
    tail = segments[-1]

    out = {
        "canal_name": raw["name"],
        "scope": (
            "SATELLITE-ET-ONLY DEMO MODE. No official WAPDA/PID canal-command boundary "
            "exists (checked, none found) -- geometry is a real OSM canal centerline "
            f"buffered by an assumed {BUFFER_HALFWIDTH_M:.0f}m half-width, not a surveyed "
            "command area. Head/tail direction is a geometric guess from line topology, "
            "not verified against real flow direction. No IRSA/PID allocation records are "
            "used or compared -- that partnership doesn't exist yet, per architecture.md §5. "
            "Do not treat stress_index as validated against any ground allocation truth."
        ),
        "geometry_source": "OpenStreetMap, waterway=canal, name='Muridke Distributary', "
                            f"{len(raw['ways'])} way segments stitched, {total_len_m/1000:.1f} km total",
        "et_source": "MODIS MOD16A2 (real, 8-day composite, 500m native), QC-masked, "
                      f"summed over {SEASON_START}..{SEASON_END} (Kharif 2025, same window as 6.3)",
        "stress_index_definition": "1 - (season ET mm / season PET mm) per segment -- higher = more water-stressed",
        "n_segments": len(segments),
        "n_segments_with_valid_index": len(valid),
        "segments": segments,
        "head_vs_tail": {
            "head_dist_km": head["dist_from_head_km"], "head_stress_index": head["stress_index"],
            "tail_dist_km": tail["dist_from_head_km"], "tail_stress_index": tail["stress_index"],
        },
    }

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {a.out}")

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
             "properties": {k: v for k, v in s.items() if k not in ("lat", "lon")}}
            for s in segments
        ],
    }
    with open(a.out_geojson, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)
    print(f"wrote {a.out_geojson}")


if __name__ == "__main__":
    main()
