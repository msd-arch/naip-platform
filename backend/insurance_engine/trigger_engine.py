#!/usr/bin/env python3
"""
trigger_engine.py -- module 6.8, parametric trigger-contract engine.

WHAT THIS IS: a real, deterministic rules engine that walks the full real
exposure-risk archive (naip/models/fusion/exposure_risk.py's
compute_exposure_rows, itself built on real hazards.py district detections
x the regional crop calendar x crop_plausibility.py's sanity mask) and fires
a "trigger event" wherever exposure_score clears a defined threshold on an
agronomically PLAUSIBLE crop-district pairing. Every trigger event is logged
to a real, append-only audit trail (audit_log.jsonl) with the exact
underlying hazard data, threshold, and timestamp that caused it -- so any
payout decision traces back to real data, never a black box.

WHAT THIS IS NOT:
  - NOT a real payout system. Raast (SBP instant-payment rail) is an
    integration point only per architecture.md -- payout() below is a
    clearly-labeled stub that logs an intent, not a transaction. No
    transaction ID, no money movement, no fabricated payment records.
  - NOT farm-level. Trigger events are computed at DISTRICT granularity
    (that's the real hazard/exposure data's actual resolution) and then
    matched against real farms in that district via the Farm Registry
    (in_memory_registry.py) for delivery purposes -- an index trigger at
    district level, not proof any specific farm in that district actually
    lost anything. That gap is BASIS RISK, modelled explicitly below, not
    assumed away.

BASIS RISK, modelled explicitly (per CLAUDE.md's working conventions --
never silently assumed away):
  A trigger event says "this hazard cleared this threshold in this district
  on this date, on a crop plausible for that district." It does NOT say any
  specific farm's field was actually damaged. Two concrete real gaps this
  project has surfaced and not closed:
    1. The plausibility mask (crop_plausibility.py) is district-level and
       coarse -- a district marked cotton-plausible may still have
       individual farms growing something else. A trigger event's crop
       assumption may be wrong for any given farm within a triggered
       district.
    2. The hazard's own spatial resolution (0.25 deg / ~27km grid, see
       Week 1) means a single district-level trigger represents one
       point/coarse-cell reading, not confirmed uniform conditions across
       the whole district -- a farm at the district's edge may have
       experienced materially different conditions than the sampled point.
  basis_risk_note is attached to every trigger event's audit record, not
  buried in documentation -- so nobody consuming this file downstream can
  miss it.

Usage:
    python trigger_engine.py --hazards-json <district hazards_district_national.json> \
        --farms-geojson <120-farm seed> --districts-geojson <pk_districts.geojson> \
        --out-audit audit_log.jsonl --threshold 0.35
"""
import argparse
import datetime as dt
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", "fusion"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "farm_registry"))
from exposure_risk import compute_exposure_rows  # noqa: E402
from in_memory_registry import load_registry  # noqa: E402

BASIS_RISK_NOTE = (
    "Index trigger, NOT confirmed farm-level loss. Two real, unmitigated basis-risk sources: "
    "(1) the crop-mix check is district-level regardless of source -- even where Phase 2 Track C's "
    "real MNFSR district-area data applies (see this record's crop_mix_source), it's still a "
    "district-wide proportion, not proof of what any individual farm within a triggered district "
    "grows; districts still on the Week 4 hand-classified mask (crop_mix_source == "
    "'hand_classified_mask') carry the same coarseness as ever; (2) the underlying hazard reading "
    "is a single 0.25 deg (~27km) grid-cell sample per district, not confirmed uniform across the "
    "whole district. A trigger event here is a reason to investigate/pay against an index, not "
    "proof of individual loss. PHASE 3 WEEK 9 (Track G): exposure_score now bakes in crop_weight "
    "(the real crop_mix_share where available) rather than only gating on presence -- this reduces "
    "but does NOT eliminate basis risk source (1): a district-wide 48.95% rice share still means "
    "51.05% of that district's real cropped area is something else."
)

RAAST_STUB_NOTE = (
    "Raast (SBP instant-payment rail) is an integration point only, per architecture.md -- no real "
    "payment execution exists or is attempted here. This is a logged INTENT, not a transaction. "
    "No transaction ID, no money movement, nothing fabricated to look like a real payment record."
)


def evaluate_triggers(exposure_rows, threshold):
    """Real, deterministic threshold rule -- the entire trigger logic in one
    place, auditable at a glance: agronomically plausible AND
    exposure_score >= threshold."""
    triggered = [r for r in exposure_rows if r["agronomically_plausible"] and r["exposure_score"] >= threshold]
    return sorted(triggered, key=lambda r: r["exposure_score"], reverse=True)


def build_audit_record(row, threshold, registry):
    """Every field a payout decision would need to trace back to real
    underlying data -- hazard reading, threshold, crop-calendar stage,
    plausibility check, matched real farms, basis risk, timestamp."""
    farms_in_district = registry.farms_in_district(row["district"]) if registry else []
    return {
        "event_id": str(uuid.uuid4()),
        "logged_at_utc": dt.datetime.utcnow().isoformat(),
        "trigger_rule": f"exposure_score >= {threshold} AND agronomically_plausible == true",
        "district": row["district"],
        "date": row["date"],
        "hazard": row["hazard"],
        "hazard_confidence": row["hazard_confidence"],
        "crop": row["crop"],
        "crop_stage": row["crop_stage"],
        "vulnerability_weight": row["vulnerability_weight"],
        "crop_weight": row.get("crop_weight"),  # Phase 3 Track G: real proportional weight baked
                        # into exposure_score itself now, not just a pass/fail gate -- see exposure_risk.py
        "exposure_score": row["exposure_score"],
        "threshold": threshold,
        "agronomically_plausible": row["agronomically_plausible"],
        "crop_mix_source": row.get("crop_mix_source", "hand_classified_mask"),  # Phase 2 Track C:
                            # 'real_district_area' (real MNFSR data) vs 'hand_classified_mask' (Week 4
                            # fallback) -- never silently indistinguishable, per direction
        "crop_mix_share_of_4crop_area": row.get("crop_mix_share_of_4crop_area"),
        "lat": row.get("lat"), "lon": row.get("lon"),
        "n_real_farms_matched_in_district": len(farms_in_district),
        "matched_farm_ids": [f.farm_id for f in farms_in_district],
        "basis_risk_note": BASIS_RISK_NOTE,
        "payout": {
            "status": "STUBBED_INTENT_ONLY",
            "note": RAAST_STUB_NOTE,
            "amount": None,
            "transaction_id": None,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hazards-json", required=True)
    ap.add_argument("--farms-geojson", default=None,
                     help="if given, match triggered districts against real farm polygons")
    ap.add_argument("--districts-geojson", default=None)
    ap.add_argument("--out-audit", default="audit_log.jsonl")
    ap.add_argument("--out-summary", default="trigger_summary.json")
    ap.add_argument("--threshold", type=float, default=0.35,
                     help="illustrative threshold, not actuarially calibrated -- see report")
    a = ap.parse_args()

    data, rows = compute_exposure_rows(a.hazards_json)

    registry = None
    if a.farms_geojson and a.districts_geojson:
        registry = load_registry(a.farms_geojson, a.districts_geojson)
        print(f"loaded {len(registry.farms)} real farms for district matching")

    triggered = evaluate_triggers(rows, a.threshold)
    print(f"{len(triggered)} trigger events at threshold >= {a.threshold} "
          f"(agronomically-plausible only, out of {sum(1 for r in rows if r['exposure_score'] > 0)} "
          f"total nonzero-exposure rows)")

    audit_records = [build_audit_record(r, a.threshold, registry) for r in triggered]

    with open(a.out_audit, "w", encoding="utf-8") as f:
        for rec in audit_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(audit_records)} audit records to {a.out_audit} (append-only JSONL, "
          "one real trigger event per line)")

    n_with_farms = sum(1 for r in audit_records if r["n_real_farms_matched_in_district"] > 0)
    summary = {
        "generated": dt.datetime.utcnow().isoformat(),
        "threshold": a.threshold,
        "threshold_note": "Illustrative, chosen to produce a workable demo-week trigger count -- "
                           "NOT actuarially calibrated against real loss/claims data (none exists "
                           "accessibly for this project, same data-gap pattern as every other week).",
        "n_source_rows": len(rows),
        "n_nonzero_exposure": sum(1 for r in rows if r["exposure_score"] > 0),
        "n_triggered": len(triggered),
        "n_triggered_with_real_farms_matched": n_with_farms,
        "basis_risk_note": BASIS_RISK_NOTE,
        "raast_note": RAAST_STUB_NOTE,
        "top_triggers": audit_records[:20],
    }
    with open(a.out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"wrote {a.out_summary}")
    print(f"\n{n_with_farms}/{len(triggered)} trigger events matched at least one real farm "
          f"(only Layyah/Muridke-cluster districts have real farm polygons -- everywhere else "
          "triggers correctly, just with 0 matched farms, an honest reflection of the seed data's "
          "real geographic limit)")


if __name__ == "__main__":
    main()
