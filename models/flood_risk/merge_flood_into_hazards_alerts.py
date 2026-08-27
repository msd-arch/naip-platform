#!/usr/bin/env python3
"""
merge_flood_into_hazards_alerts.py -- Week 27 (Track I wiring): folds the
real live flood-risk screen (flood_risk_live_national.json, produced by the
PROMOTED v3 predict_flood_risk_live.py) into
naip/backend/alerts/hazards_district_national.json's "alerts" list -- the
SAME file exposure_risk.py/trigger_engine.py actually consume (a DIFFERENT
file from district_alerts.json, which merge_into_district_alerts.py targets
for the dashboard's choropleth -- that script is separate and unchanged;
this one exists because flood needs to enter the actual scoring pipeline,
not just the map display).

Uses the same "alerts" row schema every other hazard already has (date,
slot, city_en, lat, lon, hazard, flag, confidence, message_en/ur, source) --
no bespoke format, so exposure_risk.py's compute_exposure_rows() picks it up
automatically via the same generic per-crop vulnerability/crop_weight
machinery every other hazard already goes through. slot="live" (not "trend",
which compute_exposure_rows() explicitly skips).

Re-running this script replaces any prior flood_risk alert rows for the SAME
date rather than duplicating them, so it's safe to re-run after a fresh live
screen.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_SCREEN_PATH = os.path.join(HERE, "flood_risk_live_national.json")
HAZARDS_JSON_PATH = os.path.join(HERE, "..", "..", "backend", "alerts", "hazards_district_national.json")

HAZARD_NAME = "flood_risk"

MSG_EN_TEMPLATE = (
    "Live Sentinel-1 SAR + CHIRPS precipitation screen ({window}): mean model flood-risk "
    "score {score:.3f} over {n} real sampled points ({flagged_pct:.0f}% of points >= 0.5, "
    "mean real precipitation anomaly {precip_anom:.0f}% vs. this location's own 20-year "
    "historical norm for this window). v3 model (promoted Week 27, real fair-2024-test "
    "precision 0.190 -- most 'flooded' predictions are still wrong even in this model's "
    "best real evaluation so far; read as a meaningfully-improved relative risk ranking, "
    "not a calibrated probability)."
)
MSG_UR_TEMPLATE = (
    "لائیو سیٹلائٹ (Sentinel-1 + CHIRPS بارش) اسکین: سیلاب کے خطرے کا اوسط اسکور {score:.3f} "
    "({n} حقیقی پوائنٹس پر مبنی)۔ حتمی امکان نہیں، ایک نسبتی خطرے کا اشارہ سمجھیں۔"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-screen", default=LIVE_SCREEN_PATH)
    ap.add_argument("--hazards-json", default=HAZARDS_JSON_PATH)
    a = ap.parse_args()

    with open(a.live_screen, encoding="utf-8") as f:
        live = json.load(f)
    with open(a.hazards_json, encoding="utf-8") as f:
        hz = json.load(f)

    date_str = live["generated"][:10].replace("-", "")
    window = f"{live['during_window'][0]}..{live['during_window'][1]}"

    new_alerts = []
    for d in live["district_results"]:
        if d["n_points"] == 0:
            continue  # real data gap this run -- not asserting zero risk, so no row
        score = d["mean_model_score"]
        new_alerts.append({
            "date": date_str, "slot": "live", "stamp": f"{date_str}_live",
            "city_en": d["district"], "city_ur": d["district"],
            "lat": d["lat"], "lon": d["lon"],
            "category": "flood", "hazard": HAZARD_NAME,
            "flag": bool(d["flag"]), "confidence": round(score, 4),
            "message_en": MSG_EN_TEMPLATE.format(
                window=window, score=score, n=d["n_points"],
                flagged_pct=d["frac_points_flagged"] * 100,
                precip_anom=d.get("mean_precip_anomaly_pct", 0.0)),
            "message_ur": MSG_UR_TEMPLATE.format(score=score, n=d["n_points"]),
            "source": "Sentinel-1 SAR + JRC + CHIRPS, GBT v3 (precip-augmented), live screen",
        })

    alerts = hz["alerts"]
    n_before = len(alerts)
    alerts = [al for al in alerts if not (al["hazard"] == HAZARD_NAME and al["date"] == date_str)]
    n_removed = n_before - len(alerts)
    alerts.extend(new_alerts)
    hz["alerts"] = alerts
    hz["coverage_notes"] = hz.get("coverage_notes", []) + [
        f"flood_risk added Week 27 (Track I v3 wiring) -- {len(new_alerts)} real district rows "
        f"from a LIVE Sentinel-1+CHIRPS screen ({window}), NOT derived from the same MSG archive "
        "as the other 11 hazards (real date range: this alert's own 'date' field, not the MSG "
        "archive window in data_quality above) -- see flood_risk_live_national.json for full "
        "per-district detail and caveats, STATUS_WEEK26.md/WEEK27.md for the model's real "
        "validation and known limitations."
    ]

    with open(a.hazards_json, "w", encoding="utf-8") as f:
        json.dump(hz, f, indent=2, ensure_ascii=False)

    print(f"replaced {n_removed} prior flood_risk alerts for date={date_str} with {len(new_alerts)} new real rows")
    print(f"wrote {a.hazards_json} ({len(alerts)} total alerts)")


if __name__ == "__main__":
    main()
