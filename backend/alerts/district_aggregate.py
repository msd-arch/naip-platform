#!/usr/bin/env python3
"""
district_aggregate.py -- collapse the per-timestep, per-district hazards.json
(produced by hazards.py --locations districts) into a district-day-hazard
summary feed: one row per (district, date, hazard) instead of one row per
15-min timestep.

This is an aggregation step only -- it does not add or change any detection
logic, and it does not build delivery (SMS/dashboard); that is Week 4 per
CLAUDE.md's sprint plan. Output is meant to be pluggable into a future
alert channel: a small JSON/CSV, not a live feed.

Drought/NDVI trend is carried through as-is (2 Punjab farm clusters,
Layyah/Muridke) -- it is NOT computed per-district. Every other district's
`drought` field is explicitly null/absent, not a fabricated "no drought"
default. See the placeholder note in the output.

Usage:
    python district_aggregate.py --hazards-json <path to hazards_district_national.json> \
        --out-json district_alerts.json --out-csv district_alerts.csv
"""
import argparse
import csv
import json
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hazards-json", required=True)
    ap.add_argument("--out-json", default="district_alerts.json")
    ap.add_argument("--out-csv", default="district_alerts.csv")
    a = ap.parse_args()

    with open(a.hazards_json, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("locations_mode") != "districts":
        raise SystemExit(
            f"{a.hazards_json} was generated with locations_mode="
            f"{data.get('locations_mode')!r}, not 'districts' -- run hazards.py "
            "with --locations districts first."
        )

    # group: (district, date, hazard) -> list of alert records
    groups = defaultdict(list)
    for al in data["alerts"]:
        key = (al["city_en"], al["date"], al["hazard"])
        groups[key].append(al)

    rows = []
    for (district, date, hazard), recs in sorted(groups.items()):
        any_flag = any(r["flag"] for r in recs)
        triggered = [r for r in recs if r["flag"]]
        best = max(triggered, key=lambda r: r["confidence"]) if triggered else \
            max(recs, key=lambda r: r["confidence"])
        rows.append({
            "district": district,
            "date": date,
            "hazard": hazard,
            "any_flag": any_flag,
            "max_confidence": round(best["confidence"], 2),
            "n_observations": len(recs),
            "n_triggered": len(triggered),
            "message_en": best["message_en"],
            "message_ur": best["message_ur"],
            "lat": recs[0]["lat"],
            "lon": recs[0]["lon"],
        })

    districts_with_drought = {t["region_en"] for t in data.get("trends", [])}
    all_districts = sorted({al["city_en"] for al in data["alerts"]})
    drought_coverage_note = (
        f"drought/NDVI trend computed for {len(districts_with_drought)} region(s) only "
        f"({', '.join(sorted(districts_with_drought)) or 'none'}) out of {len(all_districts)} "
        "districts in this feed -- national NDVI trend coverage is not built yet (needs "
        "per-district farm-cluster bboxes or a national NDVI grid pass, neither exists as of "
        "Week 1). Districts with no drought row are NOT asserting 'no drought risk' -- they are "
        "simply not evaluated."
    )

    out = {
        "generated": data["generated"],
        "source_hazards_json": a.hazards_json,
        "period": {"days": data["days"]},
        "n_districts": len(all_districts),
        "district_day_hazard_rows": rows,
        "drought_trends_region_level_only": data.get("trends", []),
        "coverage_notes": [drought_coverage_note] + data.get("stubbed", []),
    }

    with open(a.out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    with open(a.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                            ["district", "date", "hazard", "any_flag", "max_confidence",
                             "n_observations", "n_triggered", "message_en", "message_ur",
                             "lat", "lon"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    triggered_rows = sum(1 for r in rows if r["any_flag"])
    print(f"wrote {a.out_json} and {a.out_csv}: {len(rows)} district-day-hazard rows "
          f"({triggered_rows} with at least one triggered observation), "
          f"{len(all_districts)} districts, drought coverage: "
          f"{len(districts_with_drought)}/{len(all_districts)} districts")


if __name__ == "__main__":
    main()
