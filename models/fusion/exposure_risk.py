#!/usr/bin/env python3
"""
exposure_risk.py -- module 6.5, scoped-down per Week 3 direction.

WHAT THIS IS: fuses two real signals --
  1. Real district-level hazard detections from hazards.py (Week 1's engine,
     unchanged detector logic, national district-mode output).
  2. The regional (province-average, NOT per-farm) crop calendar +
     illustrative stage-vulnerability weights from crop_calendar.py.
into a per-(district, date, hazard, crop) exposure-risk score:
    exposure_score = hazard_confidence * stage_vulnerability_weight   (0 if not flagged)

WHAT THIS IS NOT, stated plainly:
  - NOT a retrained version of the real ml_pipeline/ U-Net (patch-sizing +
    masked-loss + curriculum-training all confirmed real and working in
    Week 3's pre-check, see STATUS_WEEK3.md). That pipeline predicts MSG
    imagery FROM GFS/WRF fields -- a different task (image synthesis) from
    what 6.5 needs here (a risk score). Retraining it wouldn't produce this
    output; the "extend existing methodology" instruction is honored by
    NOT rebuilding a parallel one-off ML system for this scoped task, and by
    confirming/reporting the real pipeline's status rather than ignoring it.
  - NOT farm-specific or crop-specific-per-district. NAIP does not know
    which district grows which crop in what proportion (same gap as Week
    2's missing crop-type classification) -- so this computes exposure risk
    for ALL FOUR crops at every district, as a "if this district were
    growing crop X" hypothetical, not a claim about actual local crop mix.
    Never read a single district's wheat-exposure number as "this district's
    real exposure" -- it's one hypothetical column among four.

Usage:
    python exposure_risk.py --hazards-json <district hazards_district_national.json> \
        --out exposure_risk.json --out-csv exposure_risk_top.csv
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crop_calendar import SOWING_HARVEST, vulnerability  # noqa: E402
from crop_plausibility import is_plausible  # noqa: E402
from real_crop_mix import crop_mix_tier, crop_share, is_plausible_real, resolve_interim_confidence  # noqa: E402


def resolve_plausibility(district, crop, date):
    """PHASE 2 WEEK 6 (Track C), extended PHASE 4 final item (real
    model_estimated_interim tier): agronomically_plausible now prefers real
    MNFSR district-area data for the season it covers (2022-23), then Track
    F's real model-estimated interim tier for any later season, over Week
    4's hand-classified mask -- the hand mask is now a fallback only for
    cells neither real tier can cover (the 11 GB/AJK districts), not the
    default everywhere."""
    real = is_plausible_real(district, crop, date)
    if real is not None:
        return real
    return is_plausible(district, crop)


def resolve_crop_weight(district, crop, plausible, date):
    """PHASE 3 WEEK 9 (Track G), extended PHASE 4 final item: exposure_score's
    crop factor. Real crop_mix_share (real_district_area for the 2022-23
    season it covers, model_estimated_interim for any later season, clipped
    to [0,1] -- the interim tier's predictions can be slightly negative for
    near-zero crops) is used as a real proportional weight wherever either
    real tier applies; hand_classified_mask districts (no proportional data
    -- the 11 GB/AJK districts, Track G's real model-predicted attempt there
    was reviewed and rejected as unreliable extrapolation, see
    STATUS_WEEK9.md -- unaffected by this week's change) keep the exact
    original boolean gate (1.0 plausible / 0.0 not)."""
    share = crop_share(district, crop, date)
    if share is not None:
        return max(0.0, min(1.0, share))
    return 1.0 if plausible else 0.0


def parse_alert_date(date_str):
    # hazards.py alert "date" fields are YYYYMMDD strings
    return dt.datetime.strptime(date_str, "%Y%m%d").date()


def compute_exposure_rows(hazards_json_path):
    """Reusable core: returns (data, rows) for the full district hazard
    archive -- ALL (district, date, hazard, crop) rows, not just the top-N
    written to disk by main() below. The Week 4 trigger-contract engine
    imports this directly so it evaluates the complete real archive, not
    only the top-50 exposure_risk_top.csv snapshot."""
    with open(hazards_json_path, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("locations_mode") != "districts":
        raise SystemExit(f"{hazards_json_path} was generated with locations_mode="
                          f"{data.get('locations_mode')!r}, not 'districts'.")

    crops = list(SOWING_HARVEST.keys())
    rows = []
    skipped_dates = 0
    for al in data["alerts"]:
        if al["slot"] == "trend":  # drought is farm-cluster-scoped, not district/date-comparable here
            continue
        try:
            d = parse_alert_date(al["date"])
        except ValueError:
            skipped_dates += 1
            continue
        for crop in crops:
            weight, stage, note = vulnerability(al["hazard"], crop, d)
            plausible = resolve_plausibility(al["city_en"], crop, d)
            crop_weight = resolve_crop_weight(al["city_en"], crop, plausible, d)
            raw_score = round(al["confidence"] * weight * crop_weight, 4) if al["flag"] else 0.0
            confidence_multiplier = resolve_interim_confidence(al["city_en"], crop, d)
            score = round(raw_score * confidence_multiplier, 4)
            rows.append({
                "district": al["city_en"], "date": al["date"], "hazard": al["hazard"],
                "hazard_flag": al["flag"], "hazard_confidence": al["confidence"],
                "crop": crop, "crop_stage": stage, "vulnerability_weight": weight,
                "crop_weight": round(crop_weight, 4),
                "interim_confidence_multiplier": round(confidence_multiplier, 4),  # threshold
                        # recalibration: 1.0 for real_district_area/hand_classified_mask (current
                        # effective bar unchanged); Track F's real, validated per-crop cross-year
                        # R2 for model_estimated_interim rows -- see real_crop_mix.py
                "exposure_score_before_confidence_discount": raw_score,
                "exposure_score": score,
                "agronomically_plausible": plausible,
                "crop_mix_source": crop_mix_tier(al["city_en"], d),
                "crop_mix_share_of_4crop_area": crop_share(al["city_en"], crop, d),
                "lat": al.get("lat"), "lon": al.get("lon"),
            })
    data["_skipped_dates"] = skipped_dates
    return data, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hazards-json", required=True)
    ap.add_argument("--out", default="exposure_risk.json")
    ap.add_argument("--out-csv", default="exposure_risk_top.csv")
    ap.add_argument("--top-n", type=int, default=50)
    a = ap.parse_args()

    data, rows = compute_exposure_rows(a.hazards_json)
    skipped_dates = data.pop("_skipped_dates")
    crops = list(SOWING_HARVEST.keys())

    n_flagged_source_alerts = sum(1 for al in data["alerts"] if al["flag"] and al["slot"] != "trend")
    n_nonzero = sum(1 for r in rows if r["exposure_score"] > 0)
    print(f"{len(rows)} (district, date, hazard, crop) rows from {len(data['alerts'])} source alerts "
          f"({n_flagged_source_alerts} flagged) -- {n_nonzero} with nonzero exposure_score "
          f"({skipped_dates} alerts skipped: unparseable date, e.g. multi-day 'trend' stamps)")

    top = sorted(rows, key=lambda r: r["exposure_score"], reverse=True)[:a.top_n]
    plausible_rows = [r for r in rows if r["agronomically_plausible"]]
    top_plausible = sorted(plausible_rows, key=lambda r: r["exposure_score"], reverse=True)[:a.top_n]
    n_implausible_nonzero = sum(1 for r in rows if r["exposure_score"] > 0 and not r["agronomically_plausible"])

    crop_mix_source_breakdown = {}
    for r in rows:
        crop_mix_source_breakdown[r["crop_mix_source"]] = crop_mix_source_breakdown.get(r["crop_mix_source"], 0) + 1

    out = {
        "generated": dt.datetime.utcnow().isoformat(),
        "scope": (
            "Fuses real hazards.py district detections with the regional (province-average, "
            "NOT per-farm/per-district) crop calendar. Computed for ALL FOUR crops at every "
            "district as a hypothetical ('if this district grew crop X') -- NAIP has no real "
            "per-district crop-mix data to pick one. Stage-vulnerability weights are illustrative "
            "agronomic knowledge, not locally fitted or validated this week. This is NOT the real "
            "ml_pipeline/ U-Net (that predicts imagery, a different task) -- see STATUS_WEEK3.md "
            "for that pipeline's own real, separately-reported status. "
            "WEEK 4 ADDITION: every row carries 'agronomically_plausible'. "
            "PHASE 2 TRACK C ADDITION: that boolean is now sourced from REAL Government of "
            "Pakistan MNFSR district-wise crop-area data (115/126 real districts) wherever it "
            "covers this (district, crop) cell; crop_plausibility.py's Week 4 hand-classified mask "
            "is now a fallback for the 11 districts real data can't cover (Gilgit-Baltistan + Azad "
            "Kashmir, outside MNFSR's mandate) plus any (district, crop) cell whose real source "
            "table failed cross-validation. Every row also carries 'crop_mix_source' "
            "('real_district_area' vs 'hand_classified_mask') and 'crop_mix_share_of_4crop_area' "
            "(the real proportional area share, or null) -- so a district running on real data and "
            "one still on the hand mask are never indistinguishable downstream. See "
            "naip/data/crop_mix_ground_truth/parse_report.json for real parse coverage/rejections. "
            "'top_exposure_events' below is the UNFILTERED ranking (kept for transparency, "
            "includes physically-impossible pairings like cotton in Skardu). "
            "'top_plausible_exposure_events' is the filtered ranking the trigger-contract engine "
            "(6.8) actually consumes -- never wire 6.8 to the unfiltered list. "
            "PHASE 3 WEEK 9 (Track G) ADDITION: exposure_score = hazard_confidence * "
            "vulnerability_weight * crop_weight (was: hazard_confidence * vulnerability_weight, "
            "with crop presence only a pass/fail gate). crop_weight is now the real MNFSR "
            "crop_mix_share (clipped [0,1]) wherever real_district_area data covers this cell; "
            "hand_classified_mask districts (currently all 11 GB/AJK, unchanged from Week 6) keep "
            "the exact original 1.0/0.0 gate -- no regression there. Confirmed with you before this "
            "regenerated the national output: e.g. Kasur cotton (real 0.87% share) dropped from "
            "0.468 to ~0.004, Sialkot rice (real 48.95% share) from 0.39 to ~0.191 -- see "
            "naip/docs/STATUS_WEEK9.md for the full real before/after. "
            "PHASE 4 FINAL ITEM ADDITION: 'crop_mix_source' is now THREE-TIER, resolved per "
            "(district, crop, date): 'real_district_area' (real MNFSR data, ONLY for the 2022-23 "
            "season it actually covers) -> 'model_estimated_interim' (Track F's trained model's "
            "real per-district crop-share prediction, for any growing season AFTER 2022-23 that "
            "real MNFSR has no report for at all -- a trained model's ESTIMATE, not a government "
            "survey, unvalidatable until a future real MNFSR report arrives, see "
            "naip/docs/STATUS_WEEK20.md) -> 'hand_classified_mask' (the 11 GB/AJK districts neither "
            "real tier covers, unchanged from Track G's standing rejection there, regardless of "
            "date). Real, structurally significant consequence: NAIP's actual hazard archives all "
            "postdate 2022-23 (they start mid-2026), so essentially every real_district_area row "
            "this pipeline previously produced now resolves to model_estimated_interim instead -- "
            "not a regression, but the correct real consequence of adding date-awareness for the "
            "first time (previously every row silently used the 2022-23 snapshot regardless of the "
            "alert's actual date). See STATUS_WEEK20.md for the full real before/after. "
            "THRESHOLD RECALIBRATION ADDITION (real, tier-and-crop-aware): every row now carries "
            "'interim_confidence_multiplier' and 'exposure_score_before_confidence_discount'. "
            "real_district_area/hand_classified_mask rows keep multiplier=1.0 (current effective "
            "bar unchanged). model_estimated_interim rows get a real per-crop discount = the mean "
            "of Track F's own validated cross-year R2 (STATUS_WEEK17.md's district-level table, "
            "not the original within-year figures) -- wheat 0.4725, cotton 0.428, rice 0.264, "
            "sugarcane 0.1225 -- applied directly (multiplier = clamp(mean_r2, 0, 1), no further "
            "transform). 'exposure_score' is the discounted, threshold-comparable value; "
            "'exposure_score_before_confidence_discount' is what it would have been without this "
            "crop's real confidence discount -- kept so nothing is silently lost. Real, deliberate "
            "consequence: an interim-tier wheat row needs ~2.1x the raw score of a real-tier row "
            "to clear the same threshold; sugarcane needs ~8.2x, discounted hard enough to "
            "essentially not fire on a marginal score alone. See STATUS_WEEK21.md for the full "
            "real before/after."
        ),
        "source_hazards_json": a.hazards_json,
        "crops": crops,
        "n_rows": len(rows),
        "n_nonzero_exposure": n_nonzero,
        "n_nonzero_exposure_implausible": n_implausible_nonzero,
        "n_source_alerts": len(data["alerts"]),
        "n_source_alerts_flagged": n_flagged_source_alerts,
        "crop_mix_source_breakdown": crop_mix_source_breakdown,  # PHASE 4 FINAL ITEM: real, full-
                        # archive row-level tier counts (not a per-126-districts data-coverage
                        # count -- this reflects the actual dates in source_hazards_json)
        "top_exposure_events": top,
        "top_plausible_exposure_events": top_plausible,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    with open(a.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(top[0].keys()) if top else [])
        w.writeheader()
        for r in top:
            w.writerow(r)

    plausible_csv = a.out_csv.replace(".csv", "_plausible.csv")
    with open(plausible_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(top_plausible[0].keys()) if top_plausible else [])
        w.writeheader()
        for r in top_plausible:
            w.writerow(r)

    print(f"wrote {a.out}, {a.out_csv} (unfiltered), {plausible_csv} (plausible-only)")
    print(f"{n_implausible_nonzero} nonzero-score rows were agronomically implausible (e.g. Skardu-cotton) "
          f"and excluded from top_plausible_exposure_events")
    print("\ntop 10 UNFILTERED exposure events (includes implausible pairings):")
    for r in top[:10]:
        flag = "" if r["agronomically_plausible"] else "  [IMPLAUSIBLE]"
        print(f"  {r['district']:20s} {r['date']} {r['hazard']:16s} x {r['crop']:10s} "
              f"({r['crop_stage']})  score={r['exposure_score']}{flag}")
    print("\ntop 10 PLAUSIBLE exposure events (what 6.8 actually consumes):")
    for r in top_plausible[:10]:
        print(f"  {r['district']:20s} {r['date']} {r['hazard']:16s} x {r['crop']:10s} "
              f"({r['crop_stage']})  score={r['exposure_score']}")


if __name__ == "__main__":
    main()
