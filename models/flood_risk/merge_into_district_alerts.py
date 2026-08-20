#!/usr/bin/env python3
"""
merge_into_district_alerts.py -- fold the real live flood-risk screen
(flood_risk_live_national.json, produced by predict_flood_risk_live.py) into
naip/backend/alerts/district_alerts.json as a new hazard type ("flood_risk"),
using the EXACT SAME row schema district_aggregate.py already produces for
the 11 rule-based detectors and residue_burning -- no bespoke format, so it
flows through prepare_data.py and the dashboard's existing aggregation
(district_hazard_summary.json) without any changes there.

Re-running this script replaces any prior flood_risk rows rather than
appending duplicates, so it's safe to re-run after a fresh live screen.
"""
import argparse
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_SCREEN_PATH = os.path.join(HERE, "flood_risk_live_national.json")
ALERTS_JSON_PATH = os.path.join(HERE, "..", "..", "backend", "alerts", "district_alerts.json")
ALERTS_CSV_PATH = os.path.join(HERE, "..", "..", "backend", "alerts", "district_alerts.csv")

HAZARD_NAME = "flood_risk"

MSG_EN_TEMPLATE = (
    "Live Sentinel-1 SAR screen ({window}): mean model flood-risk score {score:.3f} "
    "over {n} real sampled points ({flagged_pct:.0f}% of points >= 0.5). "
    "Trained on the real Aug-Sep 2022 flood disaster only, not validated against a "
    "second real flood event -- read as a relative risk signal, not a calibrated "
    "probability. The JRC permanent-water baseline this model was built to use for "
    "discounting rivers/lakes was found to contribute almost nothing to it "
    "(0.0012 importance) -- score is driven mainly by real SAR backscatter change."
)
MSG_UR_TEMPLATE = (
    "لائیو سیٹلائٹ (Sentinel-1) اسکین: سیلاب کے خطرے کا اوسط اسکور {score:.3f} "
    "({n} حقیقی پوائنٹس پر مبنی)۔ ماڈل صرف 2022 کے حقیقی سیلاب پر تربیت یافتہ ہے، "
    "دوسرے واقعے پر تصدیق شدہ نہیں -- اسے ایک نسبتی اشارہ سمجھیں، حتمی امکان نہیں۔"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-screen", default=LIVE_SCREEN_PATH)
    ap.add_argument("--alerts-json", default=ALERTS_JSON_PATH)
    ap.add_argument("--alerts-csv", default=ALERTS_CSV_PATH)
    a = ap.parse_args()

    with open(a.live_screen, encoding="utf-8") as f:
        live = json.load(f)
    with open(a.alerts_json, encoding="utf-8") as f:
        alerts = json.load(f)

    date_str = live["generated"][:10].replace("-", "")
    window = f"{live['during_window'][0]}..{live['during_window'][1]}"

    new_rows = []
    for d in live["district_results"]:
        if d["n_points"] == 0:
            continue  # real data gap this run -- not asserting zero risk, so no row
        score = d["mean_model_score"]
        flagged_pct = d["frac_points_flagged"] * 100
        new_rows.append({
            "district": d["district"],
            "date": date_str,
            "hazard": HAZARD_NAME,
            "any_flag": d["flag"],
            "max_confidence": round(score, 2),
            "n_observations": d["n_points"],
            "n_triggered": round(d["frac_points_flagged"] * d["n_points"]),
            "message_en": MSG_EN_TEMPLATE.format(window=window, score=score, n=d["n_points"], flagged_pct=flagged_pct),
            "message_ur": MSG_UR_TEMPLATE.format(score=score, n=d["n_points"]),
            "lat": d["lat"], "lon": d["lon"],
        })

    rows = alerts["district_day_hazard_rows"]
    n_before = len(rows)
    rows = [r for r in rows if r["hazard"] != HAZARD_NAME]
    n_removed = n_before - len(rows)
    rows.extend(new_rows)
    rows.sort(key=lambda r: (r["district"], r["date"], r["hazard"]))
    alerts["district_day_hazard_rows"] = rows
    alerts["coverage_notes"] = alerts.get("coverage_notes", []) + [
        f"flood_risk ({HAZARD_NAME}) added Phase 3 Track D integration -- {len(new_rows)} real "
        f"district rows from a LIVE Sentinel-1 screen ({window}), not derived from the same "
        "MSG archive as the other 11 hazards -- see flood_risk_live_national.json for full "
        "per-point detail and caveats."
    ]

    with open(a.alerts_json, "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2, ensure_ascii=False)

    fieldnames = list(rows[0].keys())
    with open(a.alerts_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"replaced {n_removed} prior flood_risk rows with {len(new_rows)} new real rows")
    print(f"wrote {a.alerts_json} ({len(rows)} total rows) and {a.alerts_csv}")


if __name__ == "__main__":
    main()
