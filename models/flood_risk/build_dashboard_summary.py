#!/usr/bin/env python3
"""
build_dashboard_summary.py -- turn the real live national flood screen
(flood_risk_live_national.json) into a dashboard-ready summary, same pattern
as Track G's track_g_dashboard_summary.json.

DECIDED WITH YOU after seeing the real result (122/126 districts flagged at
the raw 0.5 cutoff): this is NOT reported as a national flood alert. National-
aggregate live Sentinel-1 stats sit almost exactly on the 2022 TRAINING
DATA'S "flooded" class centroid, not the "not-flooded" one -- because Track
D's non-flooded training examples were other Pakistani districts during the
SAME 2022 monsoon, never an ordinary non-disaster monsoon year. The model
cannot currently tell "normal monsoon wetting" apart from "2022-flood-level
change." This is a real, newly-discovered generalization gap (temporal, not
the spatial centroid-sampling bias Tracks A/E/G found) -- reported as the
headline finding of this integration, not smoothed into a trigger.

Per your explicit instruction: report the full score DISTRIBUTION, not just
the binary flag count -- there is a real gradient (0.44 to 0.94) that is
useful signal for a future recalibration pass even though it is not clean
enough to trigger on today.
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_SCREEN_PATH = os.path.join(HERE, "flood_risk_live_national.json")
TRAIN_DATA_PATH = os.path.join(HERE, "flood_dataset.csv")
NATIONAL_AGG_PATH = os.path.join(HERE, "live_national_aggregate_stats.json")
OUT_PATH = os.path.join(HERE, "track_d_dashboard_summary.json")

FEATURES = ["VV_during", "VH_during", "VV_change", "VH_change", "jrc_occurrence"]


def class_centroids():
    import csv
    sums = {0: {f: 0.0 for f in FEATURES}, 1: {f: 0.0 for f in FEATURES}}
    counts = {0: 0, 1: 0}
    with open(TRAIN_DATA_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c = int(row["flooded"])
            counts[c] += 1
            for feat in FEATURES:
                sums[c][feat] += float(row[feat])
    return {c: {feat: sums[c][feat] / counts[c] for feat in FEATURES} for c in (0, 1)}


def main():
    with open(LIVE_SCREEN_PATH, encoding="utf-8") as f:
        live = json.load(f)
    with open(NATIONAL_AGG_PATH, encoding="utf-8") as f:
        national_agg = json.load(f)

    results = live["district_results"]
    scores = sorted(d["mean_model_score"] for d in results if d["mean_model_score"] is not None)
    n = len(scores)

    def pct(p):
        return scores[min(n - 1, int(p * n))]

    n_flagged = sum(1 for d in results if d["flag"])
    below = sorted([d for d in results if d["mean_model_score"] is not None and d["mean_model_score"] < 0.5],
                    key=lambda d: d["mean_model_score"])
    top5 = sorted(results, key=lambda d: -(d["mean_model_score"] or -1))[:5]
    bottom5 = sorted(results, key=lambda d: (d["mean_model_score"] if d["mean_model_score"] is not None else 2))[:5]

    centroids = class_centroids()

    summary = {
        "generated_note": "Phase 3 Track D integration -- real live national Sentinel-1/JRC "
                           "screen using the trained Week 10 flood classifier. Decision made "
                           "with you after seeing this result: NOT merged into "
                           "district_alerts.json as trigger rows -- reported here instead.",
        "during_window": live["during_window"],
        "pre_monsoon_baseline_window": live["pre_monsoon_baseline_window"],
        "flag_threshold": live["flag_threshold"],
        "n_districts_flagged_raw": n_flagged,
        "n_districts_total": live["n_districts_total"],
        "score_distribution": {
            "n": n, "min": round(scores[0], 4), "max": round(scores[-1], 4),
            "p10": round(pct(0.10), 4), "p25": round(pct(0.25), 4), "median": round(pct(0.5), 4),
            "p75": round(pct(0.75), 4), "p90": round(pct(0.9), 4),
            "mean": round(statistics.mean(scores), 4),
        },
        "districts_below_threshold": [
            {"district": d["district"], "mean_model_score": d["mean_model_score"]} for d in below
        ],
        "top5_by_score": [
            {"district": d["district"], "mean_model_score": d["mean_model_score"],
             "n_rule_flagged": d["n_rule_flagged"], "n_points": d["n_points"]} for d in top5
        ],
        "bottom5_by_score": [
            {"district": d["district"], "mean_model_score": d["mean_model_score"],
             "n_rule_flagged": d["n_rule_flagged"], "n_points": d["n_points"]} for d in bottom5
        ],
        "domain_shift_finding": {
            "headline": "Live 2026 national-average Sentinel-1 stats sit almost exactly on the "
                         "2022 TRAINING DATA's 'flooded' class centroid, not the 'not-flooded' "
                         "one -- the real reason 122/126 districts flag, and why this is read as "
                         "a generalization gap, not evidence of real current flooding.",
            "training_flooded_class_centroid": centroids[1],
            "training_not_flooded_class_centroid": centroids[0],
            "live_2026_national_mean": {f: national_agg[f] for f in FEATURES},
            "explanation": "Track D's non-flooded training examples were other real Pakistani "
                            "districts during the SAME 2022 monsoon -- there is no example in "
                            "training data of an ordinary, non-disaster monsoon year. The model "
                            "learned 'monsoon-season SAR change' more than 'flood-disaster-"
                            "specific SAR change' at this sampling density, and cannot yet tell "
                            "them apart.",
        },
        "caveats": live["caveats"] + [
            "This integration did not attempt to recalibrate the 0.5 threshold to force a "
            "cleaner-looking result -- the real gradient (min 0.44, max 0.94) is reported "
            "as-is. A future recalibration pass would need a genuine non-disaster-monsoon "
            "negative class (e.g. Sentinel-1 from a Pakistani monsoon year with no declared "
            "calamity), not just a lower cutoff on the same confounded score.",
        ],
        "not_merged_into_district_alerts": True,
        "not_merged_reason": "Merging near-universal flags into the same district_alerts.json "
                              "schema as the other 11 real hazard detectors risked this being "
                              "read as a genuine national flood alert. merge_into_district_alerts.py "
                              "exists and is real/tested but was deliberately not run this week.",
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_PATH}")
    print(f"n_flagged_raw={n_flagged}/126, score range [{scores[0]:.4f}, {scores[-1]:.4f}], "
          f"median={statistics.median(scores):.4f}")


if __name__ == "__main__":
    main()
