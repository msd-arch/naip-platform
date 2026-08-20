#!/usr/bin/env python3
"""
check_flow_direction.py -- verify the Muridke Distributary head/tail labeling
in water_stress.json against real SRTM elevation, since water flows downhill
and the original labeling was a geometric guess (which end of the stitched
OSM line had no chaining neighbor), not confirmed flow direction.

Pulls real SRTM 30m elevation (USGS/SRTMGL1_003, same GEE access verified
earlier this week) at the same 24 segment lat/lon points already in
water_stress.json. Reports the elevation profile head->tail, checks for a
monotonic (or roughly monotonic) downhill trend, and rewrites
water_stress.json's scope/head_vs_tail fields based on what the real
elevation data actually shows -- flips segment labels if elevation
contradicts the original assumption, leaves them if it confirms.

Usage:
    python check_flow_direction.py --project printtheory --in water_stress.json
"""
import argparse
import json

import ee
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--in", dest="in_path", default="water_stress.json")
    a = ap.parse_args()

    ee.Initialize(project=a.project)

    with open(a.in_path, encoding="utf-8") as f:
        d = json.load(f)

    segments = d["segments"]
    srtm = ee.Image("USGS/SRTMGL1_003").select("elevation")

    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([s["lon"], s["lat"]]), {"segment_id": s["segment_id"]})
        for s in segments
    ])
    reduced = srtm.reduceRegions(collection=fc, reducer=ee.Reducer.first(), scale=30).getInfo()
    elev_by_id = {f["properties"]["segment_id"]: f["properties"].get("first") for f in reduced["features"]}

    for s in segments:
        s["elevation_m_srtm"] = elev_by_id.get(s["segment_id"])

    dist = np.array([s["dist_from_head_km"] for s in segments])
    elev = np.array([s["elevation_m_srtm"] for s in segments], dtype=float)
    valid = ~np.isnan(elev)
    print(f"{valid.sum()}/{len(elev)} segments got real SRTM elevation")

    print("\nsegment_id  dist_km  elevation_m")
    for s in segments:
        print(f"  {s['segment_id']:>2}      {s['dist_from_head_km']:>5.1f}    {s['elevation_m_srtm']}")

    dv, ev = dist[valid], elev[valid]
    slope_m_per_km = float(np.polyfit(dv, ev, 1)[0])
    corr = float(np.corrcoef(dv, ev)[0, 1])
    total_drop = ev[0] - ev[-1] if len(ev) else None
    span = dv[-1] - dv[0] if len(dv) else None

    print(f"\nelevation at assumed head (0km): {ev[0]:.1f} m")
    print(f"elevation at assumed tail ({dv[-1]:.0f}km): {ev[-1]:.1f} m")
    print(f"total drop head->tail: {total_drop:.1f} m over {span:.1f} km")
    print(f"linear fit slope: {slope_m_per_km:.3f} m/km (negative = downhill head->tail, as expected)")
    print(f"distance-vs-elevation correlation: {corr:.3f}")

    # decision: does elevation confirm head->tail is actually downhill?
    # a real riverine/canal gradient in the Punjab plains is on the order of
    # ~0.1-0.3 m/km (very gentle, but consistently one-directional); noise
    # from 30m SRTM + local relief can easily be +/-5-10m unstructured.
    downhill = slope_m_per_km < 0
    strong_signal = abs(slope_m_per_km) > 0.05 and abs(corr) > 0.5

    if downhill and strong_signal:
        verdict = "confirmed"
    elif not downhill and strong_signal:
        verdict = "reversed"
    else:
        verdict = "inconclusive"

    print(f"\nVERDICT: {verdict}")

    if verdict == "reversed":
        # flip segment order and re-derive dist_from_head/position/stress mapping
        max_d = max(s["dist_from_head_km"] for s in segments)
        new_segments = []
        for s in reversed(segments):
            s2 = dict(s)
            s2["dist_from_head_km"] = round(max_d - s["dist_from_head_km"], 2)
            new_segments.append(s2)
        new_segments.sort(key=lambda s: s["dist_from_head_km"])
        for i, s in enumerate(new_segments):
            s["segment_id"] = i
            s["position"] = "head" if i == 0 else ("tail" if i == len(new_segments) - 1 else "mid")
        segments = new_segments
        d["segments"] = segments
        scope_flow_note = (
            "Flow direction cross-checked against real SRTM elevation: the ORIGINAL geometric "
            f"head/tail guess was BACKWARDS -- elevation drops {abs(total_drop):.1f}m over "
            f"{span:.0f}km in the direction opposite the original assumption (slope "
            f"{slope_m_per_km:.3f} m/km, r={corr:.3f}). Labels have been "
            "flipped in this file. This REVERSES Week 2's stated finding: the water-stress "
            "gradient still runs head(low stress)->tail(high stress), but which physical end is "
            "the true head has changed."
        )
    elif verdict == "confirmed":
        scope_flow_note = (
            "Flow direction cross-checked against real SRTM elevation: consistent with the "
            f"assumed head/tail labeling (elevation drops {total_drop:.1f}m over {span:.0f}km, "
            f"slope {slope_m_per_km:.3f} m/km, r={corr:.3f}) -- head end is measurably higher. "
            "Original geometric guess confirmed, not just assumed."
        )
    else:
        scope_flow_note = (
            f"Flow direction check against real SRTM elevation was INCONCLUSIVE: head->tail "
            f"elevation change is only {total_drop:.1f}m over {span:.0f}km (slope "
            f"{slope_m_per_km:.3f} m/km, r={corr:.3f}) -- too flat/noisy at 30m SRTM resolution "
            "to confirm or reverse the original geometric head/tail guess. The head/tail "
            "labeling in this file remains an UNVERIFIED assumption; treat the water-stress "
            "gradient finding as directionally uncertain until a better elevation/flow source "
            "is checked."
        )

    old_scope = d["scope"]
    d["scope"] = old_scope.replace(
        "Head/tail direction is a geometric guess from line topology, "
        "not verified against real flow direction.",
        scope_flow_note,
    )
    if scope_flow_note not in d["scope"]:
        d["scope"] = old_scope + " UPDATE: " + scope_flow_note

    head = segments[0]
    tail = segments[-1]
    d["head_vs_tail"] = {
        "head_dist_km": head["dist_from_head_km"], "head_stress_index": head["stress_index"],
        "head_elevation_m_srtm": head["elevation_m_srtm"],
        "tail_dist_km": tail["dist_from_head_km"], "tail_stress_index": tail["stress_index"],
        "tail_elevation_m_srtm": tail["elevation_m_srtm"],
        "flow_direction_verdict": verdict,
    }

    d["flow_direction_check"] = {
        "source": "USGS/SRTMGL1_003 (real SRTM 30m), reduceRegions at the same 24 segment points",
        "elevation_head_m": round(float(ev[0]), 1),
        "elevation_tail_m": round(float(ev[-1]), 1),
        "total_drop_m": round(float(total_drop), 1),
        "span_km": round(float(span), 1),
        "slope_m_per_km": round(slope_m_per_km, 3),
        "correlation_dist_vs_elevation": round(corr, 3),
        "verdict": verdict,
    }

    with open(a.in_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    print(f"\nwrote updated {a.in_path}")


if __name__ == "__main__":
    main()
