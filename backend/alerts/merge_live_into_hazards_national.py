#!/usr/bin/env python3
"""
merge_live_into_hazards_national.py -- Part 3 architecture: upserts Track
H's live rolling-window alert-level hazards
(data/live_nowcast/hazards_district_live.json, hazards.py's direct
districts-mode output, PRUNE_KEEP_LAST=8 scenes) into
naip/backend/alerts/hazards_district_national.json -- the file
exposure_risk.py/trigger_engine.py actually score against. This is a
DIFFERENT file from district_alerts.json, which live_nowcast_cycle.py's own
merge_live_into_master() already keeps in sync for the dashboard's
choropleth (that's day-hazard AGGREGATED); this one is the full per-alert
detail exposure/trigger scoring needs, and until this script existed it was
never kept in sync with Track H's live loop at all -- it was last built
2026-08-27 08:58 by a separate, manual, one-off process (confirmed by
reading its own contents: real alerts through 20260827, nothing since).

Same real upsert-by-key pattern models/flood_risk/merge_flood_into_hazards_
alerts.py already established for flood_risk (Week 27) -- never duplicate,
never touch a historical row this cycle's live window doesn't cover. Keyed
by (date, hazard, city_en, slot) rather than merge_flood's (date, hazard)
only, because Track H's rolling window genuinely carries multiple real
timestamped readings per district per day (each MSG slot is its own real
observation), not one row to replace outright.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
LIVE_HAZARDS_JSON = os.path.join(NAIP, "data", "live_nowcast", "hazards_district_live.json")
NATIONAL_HAZARDS_JSON = os.path.join(HERE, "hazards_district_national.json")


def merge(live_path=LIVE_HAZARDS_JSON, national_path=NATIONAL_HAZARDS_JSON):
    with open(live_path, encoding="utf-8") as f:
        live = json.load(f)
    with open(national_path, encoding="utf-8") as f:
        national = json.load(f)

    live_alerts = live["alerts"]
    live_keys = {(a["date"], a["hazard"], a["city_en"], a.get("slot")) for a in live_alerts}
    kept = [a for a in national["alerts"]
            if (a["date"], a["hazard"], a["city_en"], a.get("slot")) not in live_keys]
    merged = kept + live_alerts
    national["alerts"] = merged

    marker = "Part 3: Track H live rolling-window merge"
    national["coverage_notes"] = [n for n in national.get("coverage_notes", []) if marker not in n]
    live_dates = sorted(set(a["date"] for a in live_alerts))
    national["coverage_notes"].append(
        f"{marker}: {len(live_alerts)} real alert rows from the current live rolling window "
        f"(dates {live_dates}) upserted by (date, hazard, district, slot) into the archive "
        f"exposure_risk.py/trigger_engine.py score against -- extends it forward every ~15 real "
        "minutes, never removes a historical row this cycle's rolling window doesn't cover."
    )

    with open(national_path, "w", encoding="utf-8") as f:
        json.dump(national, f, indent=2, ensure_ascii=False)

    return len(live_alerts), len(merged)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-hazards-json", default=LIVE_HAZARDS_JSON)
    ap.add_argument("--national-hazards-json", default=NATIONAL_HAZARDS_JSON)
    a = ap.parse_args()
    n_live, n_total = merge(a.live_hazards_json, a.national_hazards_json)
    print(f"merged {n_live} real live alert rows into hazards_district_national.json ({n_total} total alerts)")


if __name__ == "__main__":
    main()
