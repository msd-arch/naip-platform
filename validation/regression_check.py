#!/usr/bin/env python3
"""
regression_check.py -- Track U step 4/5: a lightweight, real sanity check for
the live pipeline's actual output, run alongside the existing scheduled
tasks (Track H's live loop, the drought/flood/locust weeklies). NOT a model-
retraining test -- three narrow, real things:

1. Data freshness -- flags any real dashboard data file whose own
   last_computed_utc is older than that file's documented real refresh
   cadence (plus slack), so a silently-stopped scheduled task is caught
   automatically instead of by luck during an unrelated future session.
2. Expected field presence -- catches the exact real bug category Week 31
   found by hand: a script that stops emitting a field the dashboard still
   expects (locust_risk.json's `vegetation_greenup_detected` -> the renamed
   `vegetation_not_browning`, silently rendered as "No" for months).
3. No silent schema drift -- the field contract below is sourced directly
   from naip_dashboard/app/explore/types.ts, the real TypeScript interfaces
   the dashboard's own components read against, not re-derived from memory.

This is intentionally a real, narrow contract over the ~18 files
naip_dashboard/app/components/explore/ExploreView.tsx actually fetches --
not a full JSON-schema validator, not a type checker. It is meant to be
cheap enough to run on every invocation of the live loop or a weekly job
without adding meaningful runtime, and specific enough that a real failure
names the exact file/field/age that broke, not "something's wrong somewhere".

Usage:
    python regression_check.py [--data-dir PATH] [--out PATH]

Exit code 0 = clean. Exit code 1 = at least one real check failed -- the
same fail-loud convention Track R's db_registry.py and every scheduled
weekly-refresh script in this project already uses, so a scheduled task
wrapper can alert on it without extra parsing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# naip_dashboard is a real sibling of this project under the user's actual
# Downloads folder (C:\Users\USER\Downloads\naip_dashboard), not nested
# under this repo -- see CLAUDE.md's real local paths table.
DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "naip_dashboard", "public", "data")

# Sourced directly from naip_dashboard/app/explore/types.ts (the dashboard's
# own real consumer contract) -- re-read from that file, not re-derived from
# memory, when this contract needs updating for a new field/layer.
CONTRACT = [
    {
        "file": "district_hazard_summary.json", "kind": "dict",
        "required_top_level": ["districts"],
        "row_field": "districts",
        "required_row_fields": ["district", "lat", "lon", "n_rows", "n_triggered_rows", "hazards_triggered"],
    },
    {
        "file": "drought_national.json", "kind": "dict",
        "required_top_level": ["n_districts_covered", "n_districts_flagged", "district_results"],
        "row_field": "district_results",
        "required_row_fields": ["district", "tier", "n_points", "mean_z_score", "mean_current_ndvi",
                                 "mean_historical_ndvi", "district_flag"],
        "freshness_field": "last_computed_utc", "max_age_hours": 174,
        "cadence_note": "weekly, NAIP-DroughtWeekly (Sunday 03:00)",
    },
    {
        "file": "crop_stress_screen.json", "kind": "dict",
        "required_top_level": ["n_points_total", "n_districts_covered", "n_districts_flagged_either_signal",
                                "n_districts_flagged_both_signals", "district_results"],
        "row_field": "district_results",
        "required_row_fields": ["district", "tier", "n_points", "mean_level_z_score", "n_points_level_anomaly",
                                 "n_points_senescence_anomaly", "n_points_both_signals", "frac_points_any_flag",
                                 "district_flag_either_signal", "district_flag_both_signals"],
    },
    {
        "file": "real_crop_mix.json", "kind": "dict_of_dicts",
        "required_row_fields": ["tier", "source", "total_4crop_area_000ha", "crops", "crops_unreliable_source_data"],
    },
    {
        "file": "water_stress.json", "kind": "dict",
        "required_top_level": ["canal_name", "n_segments", "segments", "head_vs_tail"],
        "row_field": "segments",
        "required_row_fields": ["segment_id", "dist_from_head_km", "position", "lat", "lon", "season_et_mm",
                                 "season_pet_mm", "stress_index", "elevation_m_srtm"],
    },
    {
        "file": "locust_risk.json", "kind": "dict",
        "required_top_level": ["scope", "regions"],
        "row_field": "regions",
        # exactly the field set Week 31's real dead-field bug involved --
        # vegetation_not_browning is the CURRENT real name; a script that
        # regresses to emitting the old vegetation_greenup_detected name (or
        # drops the field) is exactly what this check exists to catch.
        "required_row_fields": ["region", "boundary_type", "boundary_note", "sm_surface_m3m3",
                                 "sm_surface_anomaly_m3m3", "ndvi_recent_30d", "ndvi_prior_30d", "ndvi_delta",
                                 "soil_favorable_for_egglaying", "vegetation_not_browning", "breeding_risk_flag",
                                 "confidence", "source"],
        "freshness_field": "last_computed_utc", "max_age_hours": 174,
        "cadence_note": "weekly, NAIP-LocustWeekly (Sunday 04:00)",
    },
    {
        "file": "track_d_dashboard_summary.json", "kind": "dict",
        "required_top_level": ["model_version", "status", "n_districts_flagged_raw", "n_districts_total",
                                "flag_threshold", "district_results", "real_fair_test_validation",
                                "nine_district_investigation", "threshold_decision", "caveats"],
        "row_field": "district_results",
        "required_row_fields": ["district", "mean_model_score", "flag", "mean_precip_anomaly_pct", "lat", "lon"],
        "freshness_field": "last_computed_utc", "max_age_hours": 174,
        "cadence_note": "weekly, NAIP-FloodWeekly (Sunday 03:30)",
    },
    {
        "file": "exposure_risk.json", "kind": "dict",
        "required_top_level": ["n_rows", "n_nonzero_exposure", "n_nonzero_exposure_implausible",
                                "top_exposure_events", "top_plausible_exposure_events"],
        "row_field": "top_exposure_events",
        "required_row_fields": ["district", "date", "hazard", "hazard_confidence", "crop", "crop_stage",
                                 "vulnerability_weight", "exposure_score", "agronomically_plausible"],
    },
    {
        "file": "audit_log_national.json", "kind": "list",
        "required_row_fields": ["event_id", "district", "date", "hazard", "hazard_confidence", "crop",
                                 "crop_stage", "exposure_score", "threshold", "n_real_farms_matched_in_district",
                                 "matched_farm_ids", "basis_risk_note", "payout"],
    },
    {
        "file": "audit_log_demo.json", "kind": "list",
        "required_row_fields": ["event_id", "district", "date", "hazard", "hazard_confidence", "crop",
                                 "crop_stage", "exposure_score", "threshold", "n_real_farms_matched_in_district",
                                 "matched_farm_ids", "basis_risk_note", "payout"],
    },
    {
        "file": "crop_classifier_report.json", "kind": "dict",
        "required_top_level": ["n_farms_total", "n_farms_used", "class_balance",
                                "majority_class_baseline_accuracy", "models"],
    },
    {
        "file": "track_f_results.json", "kind": "dict",
        "required_top_level": ["gbt_test_district_level"],
    },
    {
        "file": "track_j_crossyear_results.json", "kind": "dict",
        "required_top_level": ["direction_A_train2122_test2223", "direction_B_train2223_test2122",
                                "original_week8_within_year_district_level"],
    },
    {
        "file": "track_o_yield_results.json", "kind": "dict",
        "required_top_level": ["crops"],
    },
    {
        "file": "track_g_dashboard_summary.json", "kind": "dict",
        "required_top_level": ["crop_share_model", "fire_classifier"],
    },
    {
        "file": "trigger_summary_national.json", "kind": "dict",
        "required_top_level": ["n_triggered"],
        "freshness_field": "last_computed_utc", "max_age_hours": 48,
        "cadence_note": "tied to the live loop's trigger-eval step (Track U's Part 3, Week 31) -- "
                         "generous slack since trigger-eval only runs when explicitly enabled per cycle",
    },
    {
        "file": "trigger_summary_demo.json", "kind": "dict",
        "required_top_level": ["n_triggered"],
        "freshness_field": "last_computed_utc", "max_age_hours": 48,
        "cadence_note": "same as trigger_summary_national.json",
    },
    {
        "file": "forecast_alerts.json", "kind": "dict",
        "required_top_level": ["last_computed_utc", "gfs_cycle_utc", "gfs_update_cadence_note",
                                "forecast_horizon_note", "cross_check_caveat", "cloud_proxy_substitution_note",
                                "n_districts", "n_alerts", "n_flagged", "alerts"],
        "row_field": "alerts",
        "required_row_fields": ["district", "valid_date", "forecast_hazard", "hazard", "flag", "confidence",
                                 "message_en", "message_ur", "source"],
        "freshness_field": "last_computed_utc", "max_age_hours": 30,
        "cadence_note": "GFS publishes 4x daily (~6h cadence)",
    },
]


def _age_hours(iso_str: str) -> float:
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def check_file(spec: dict, data_dir: str) -> list[dict]:
    """Returns a list of real finding dicts (empty = clean) for one file."""
    findings = []
    path = os.path.join(data_dir, spec["file"])
    if not os.path.exists(path):
        return [{"file": spec["file"], "severity": "error", "check": "file_exists",
                  "detail": f"real file not found at {path}"}]

    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [{"file": spec["file"], "severity": "error", "check": "valid_json", "detail": str(e)}]

    kind = spec["kind"]

    # --- required top-level fields ---
    if kind == "dict":
        for key in spec.get("required_top_level", []):
            if key not in payload:
                findings.append({"file": spec["file"], "severity": "error", "check": "field_presence",
                                  "detail": f"top-level field '{key}' missing (dashboard's types.ts expects it)"})

    # --- required row fields ---
    rows = None
    if kind == "list":
        rows = payload if isinstance(payload, list) else None
    elif kind == "dict_of_dicts":
        rows = list(payload.values()) if isinstance(payload, dict) else None
    elif spec.get("row_field"):
        rf = spec["row_field"]
        val = payload.get(rf) if isinstance(payload, dict) else None
        rows = val if isinstance(val, list) else None

    if spec.get("required_row_fields") is not None:
        if not rows:
            findings.append({"file": spec["file"], "severity": "warn", "check": "row_presence",
                              "detail": f"no real rows found to check row-level fields against "
                                        f"(row_field={spec.get('row_field', '<top-level list>')})"})
        else:
            # Real rows can legitimately vary (e.g. nullable fields) -- check
            # against the union of keys across a real sample, not just row 0,
            # so one atypical first row doesn't produce a false pass/fail.
            sample = rows[: min(len(rows), 25)]
            seen_keys = set()
            for r in sample:
                if isinstance(r, dict):
                    seen_keys |= set(r.keys())
            missing = [k for k in spec["required_row_fields"] if k not in seen_keys]
            if missing:
                findings.append({"file": spec["file"], "severity": "error", "check": "field_presence",
                                  "detail": f"row field(s) {missing} missing across a sample of "
                                            f"{len(sample)} real rows in '{spec.get('row_field', '<rows>')}' "
                                            f"-- a producer script may have stopped emitting them"})

    # --- freshness ---
    if spec.get("freshness_field"):
        ts = payload.get(spec["freshness_field"]) if isinstance(payload, dict) else None
        if not ts:
            findings.append({"file": spec["file"], "severity": "warn", "check": "freshness",
                              "detail": f"'{spec['freshness_field']}' missing or empty -- cannot check real age"})
        else:
            try:
                age = _age_hours(ts)
            except ValueError as e:
                findings.append({"file": spec["file"], "severity": "error", "check": "freshness",
                                  "detail": f"'{spec['freshness_field']}'={ts!r} is not a real parseable "
                                            f"ISO timestamp: {e}"})
            else:
                max_age = spec["max_age_hours"]
                if age > max_age:
                    findings.append({"file": spec["file"], "severity": "error", "check": "freshness",
                                      "detail": f"real data is {age:.1f}h old, exceeds expected max "
                                                f"{max_age}h ({spec.get('cadence_note', 'no cadence note')}) "
                                                f"-- the scheduled task producing this file may have stopped"})
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    ap.add_argument("--out", default=os.path.join(HERE, "regression_check_report.json"))
    a = ap.parse_args()

    data_dir = os.path.abspath(a.data_dir)
    print(f"Track U regression check -- real data dir: {data_dir}")

    all_findings = []
    for spec in CONTRACT:
        findings = check_file(spec, data_dir)
        all_findings.extend(findings)
        status = "OK" if not findings else f"{len(findings)} finding(s)"
        print(f"  [{status:>14}] {spec['file']}")
        for f in findings:
            print(f"      {f['severity'].upper():5} {f['check']:16} {f['detail']}")

    errors = [f for f in all_findings if f["severity"] == "error"]
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "data_dir": data_dir,
        "n_files_checked": len(CONTRACT),
        "n_findings": len(all_findings),
        "n_errors": len(errors),
        "findings": all_findings,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {a.out}")
    print(f"real result: {len(CONTRACT)} files checked, {len(errors)} error(s), "
          f"{len(all_findings) - len(errors)} warning(s)")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
