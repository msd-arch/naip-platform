#!/usr/bin/env python3
"""
build_dashboard_summary.py -- Week 27 REWRITE: turns the real v3
(precipitation-augmented) flood model's live screen + fair-test validation
into a dashboard-ready summary. The original version of this script (Phase 3
Track D / Track I v2 era) reported a real generalization-gap finding (live
2026 stats sitting on the training data's "flooded" centroid, 122/126
over-flagging) that v3 has since resolved differently -- not by recalibrating
the same confounded SAR-only score, but by adding a real, physically distinct
signal (precipitation) that the fair 2024 test confirms genuinely
discriminates (score-separation gap 0.332 vs. the original's own 0.096).
That old domain_shift_finding narrative no longer describes v3's real
behavior -- replaced here, not just re-captioned.

Week 27 STATUS CHANGE, stated plainly: flood risk is no longer
informational-only. It is real, wired into exposure_risk.py/trigger_engine.py,
and has produced 7 real trigger events at the demo threshold. It still
cannot clear the illustrative/national threshold -- a deliberate result of
the same tier-confidence discipline applied to crop_weight (STATUS_WEEK27.md),
not a bug.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_SCREEN_PATH = os.path.join(HERE, "flood_risk_live_national.json")
FAIR_EVAL_PATH = os.path.join(HERE, "track_i_v3_2024_full_eval.json")
INVESTIGATION_PATH = os.path.join(HERE, "track_i_v3_9district_investigation.json")
OUT_PATH = os.path.join(HERE, "track_d_dashboard_summary.json")


def main():
    with open(LIVE_SCREEN_PATH, encoding="utf-8") as f:
        live = json.load(f)
    with open(FAIR_EVAL_PATH, encoding="utf-8") as f:
        fair_eval = json.load(f)
    with open(INVESTIGATION_PATH, encoding="utf-8") as f:
        investigation = json.load(f)

    results = live["district_results"]
    scores = sorted(d["mean_model_score"] for d in results if d["mean_model_score"] is not None)
    n = len(scores)

    def pct(p):
        return scores[min(n - 1, int(p * n))]

    n_flagged = sum(1 for d in results if d["flag"])
    below = sorted([d for d in results if d["mean_model_score"] is not None and d["mean_model_score"] < 0.5],
                    key=lambda d: d["mean_model_score"])
    top5 = sorted(results, key=lambda d: -(d["mean_model_score"] or -1))[:5]

    summary = {
        "generated_note": "Week 27 (Track I, precipitation attempt): v3 (real Sentinel-1 SAR + "
                           "JRC + CHIRPS precipitation) PROMOTED and WIRED into "
                           "exposure_risk.py/trigger_engine.py, real fair-test validated "
                           "(STATUS_WEEK26.md). No longer informational-only.",
        "last_computed_utc": live.get("last_computed_utc"),
        "refresh_cadence_note": live.get("refresh_cadence_note"),
        "model_version": "v3_precip (promoted Week 27, Track I)",
        "status": "wired_into_trigger_engine",
        "real_fair_test_validation": {
            "note": "The decisive real test (2024, 14 positive + 112 negative districts, never "
                    "seen in training) -- the same structural cross-year validation Track K did "
                    "for the fire model.",
            "original_model": fair_eval["original_model_on_2024"],
            "v2_model_rejected": fair_eval["v2_model_on_2024"],
            "v3_model_deployed": fair_eval["v3_model_on_2024"],
            "score_separation_diagnostic": fair_eval["score_separation_diagnostic"],
        },
        "during_window": live["during_window"],
        "pre_monsoon_baseline_window": live["pre_monsoon_baseline_window"],
        "flag_threshold": live["flag_threshold"],
        "n_districts_flagged_raw": n_flagged,
        "n_districts_total": live["n_districts_total"],
        "score_distribution": {
            "n": n, "min": round(scores[0], 4), "max": round(scores[-1], 4),
            "p10": round(pct(0.10), 4), "p25": round(pct(0.25), 4), "median": round(pct(0.5), 4),
            "p75": round(pct(0.75), 4), "p90": round(pct(0.9), 4),
            "mean": round(sum(scores) / n, 4),
        },
        "districts_below_threshold": [
            {"district": d["district"], "mean_model_score": d["mean_model_score"]} for d in below
        ],
        "top5_by_score": [
            {"district": d["district"], "mean_model_score": d["mean_model_score"],
             "mean_precip_anomaly_pct": d.get("mean_precip_anomaly_pct"),
             "n_rule_flagged": d["n_rule_flagged"], "n_points": d["n_points"]} for d in top5
        ],
        "nine_district_investigation": {
            "headline": "The districts currently flagged do not always show the positive "
                        "rainfall anomaly the training data's own signal points toward -- "
                        "investigated (not assumed sound), found explainable: this real "
                        "snapshot's national reference sample averages -72% anomaly (nearly "
                        "the whole country is running below its historical norm right now), "
                        "and every flagged district still sits at the 68th-94th percentile on "
                        "ABSOLUTE precipitation despite that -- the wettest places in the "
                        "country, even in a below-average year. Two districts additionally show "
                        "real elevated JRC permanent-water signal.",
            "caveat": "Not exhaustively verified for every hypothetical future flagged district "
                     "-- a known, real, honestly-carried-forward limitation, not a closed case.",
            "full_detail": "track_i_v3_9district_investigation.json, STATUS_WEEK27.md",
        },
        "threshold_decision": {
            "national_illustrative": 0.225,
            "demo": 0.0216,
            "note": "Same shared thresholds as every other hazard, kept deliberately -- the same "
                    "tier-confidence discipline crop_weight's per-crop R2 discount already "
                    "established (a weak/less-trustworthy signal should work harder to fire the "
                    "most consequential tier, not get a custom-lowered bar). Flood's real "
                    "fair-test precision (0.190) structurally cannot clear the illustrative tier "
                    "yet -- the honest result of its own real accuracy. It DOES clear the demo "
                    "tier (7 real events) -- see STATUS_WEEK27.md for the full reasoning.",
        },
        "district_results": [
            {"district": d["district"], "mean_model_score": d["mean_model_score"],
             "flag": d["flag"], "mean_precip_anomaly_pct": d.get("mean_precip_anomaly_pct"),
             "lat": d.get("lat"), "lon": d.get("lon")} for d in results
        ],
        "caveats": live["caveats"],
        "wired_into_trigger_engine": True,
        "trigger_engine_effect": "7 real demo-threshold trigger events (0 at the illustrative/"
                                  "national threshold) -- see naip/backend/insurance_engine/"
                                  "trigger_summary_demo.json and trigger_summary_national.json.",
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_PATH}")
    print(f"n_flagged_raw={n_flagged}/126, score range [{scores[0]:.4f}, {scores[-1]:.4f}]")


if __name__ == "__main__":
    main()
