#!/usr/bin/env python3
"""
predict_gb_ajk.py -- Phase 3 Track G, Part 1: apply the trained Track F GBT
model to the 11 real districts Track C's real MNFSR data doesn't cover
(Gilgit-Baltistan's 10 + Azad Kashmir), using real phenology features
extracted the same way as the 115 training districts.

REAL OUT-OF-DISTRIBUTION CHECK, done before trusting any prediction: for
each GB/AJK point, compute a real z-score per feature against the model's
real training-set feature distribution (mean/std saved at train time in
gbt_crop_share_model.joblib). A district whose real mean |z-score| exceeds
2.0 is flagged as likely out-of-distribution -- its phenology genuinely
looks different from anything the model was trained on, and its prediction
should not be trusted at face value. This is expected and was flagged as a
real risk before this script ran: WorldCereal's own cropland coverage in the
10 GB districts is 0.02-0.18% of district area (near-zero, high-altitude
terrain), versus a training set built entirely from real lowland/plains
cropland. Azad Kashmir (4.4% real cropland) is a real, meaningfully
different case and is reported separately.
"""
import json
import os

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "gbt_crop_share_model.joblib")
FEATURES_PATH = os.path.join(HERE, "phenology_features_gb_ajk.csv")
OUT_PATH = os.path.join(HERE, "gb_ajk_predictions.json")

OOD_Z_THRESHOLD = 2.0


def main():
    bundle = joblib.load(MODEL_PATH)
    model, features, crops, stats = bundle["model"], bundle["features"], bundle["crops"], bundle["train_feature_stats"]

    df = pd.read_csv(FEATURES_PATH)
    print(f"real GB/AJK points with usable phenology features: {len(df)}, "
          f"{df['district'].nunique()} districts")

    X = df[features].values
    preds = model.predict(X)
    for i, c in enumerate(crops):
        df[f"pred_{c}"] = preds[:, i]

    # real z-score OOD check per point, per feature
    z = np.zeros_like(X)
    for j, f in enumerate(features):
        mu, sd = stats[f]["mean"], stats[f]["std"]
        z[:, j] = (X[:, j] - mu) / sd if sd > 0 else 0.0
    df["mean_abs_zscore"] = np.mean(np.abs(z), axis=1)

    district_summary = []
    for district, g in df.groupby("district"):
        mean_shares = {c: float(g[f"pred_{c}"].mean()) for c in crops}
        mean_z = float(g["mean_abs_zscore"].mean())
        ood = mean_z > OOD_Z_THRESHOLD
        district_summary.append({
            "district": district, "n_points": len(g),
            "predicted_shares": mean_shares,
            "mean_abs_zscore_vs_training_distribution": round(mean_z, 2),
            "flagged_out_of_distribution": bool(ood),
        })
        print(f"{district:12s} n={len(g):2d}  mean|z|={mean_z:.2f}  "
              f"{'OOD-FLAGGED' if ood else 'in-range':12s}  "
              f"pred={ {k: round(v,3) for k,v in mean_shares.items()} }")

    out = {
        "ood_z_threshold": OOD_Z_THRESHOLD,
        "note": "Districts flagged out_of_distribution have phenology that looks meaningfully "
                "different from the real lowland/plains training data (115 MNFSR districts) -- "
                "their predictions should be treated as unreliable extrapolation, not used as "
                "a real crop_mix_source tier without explicit review.",
        "districts": district_summary,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    n_ood = sum(1 for d in district_summary if d["flagged_out_of_distribution"])
    print(f"\n{n_ood}/{len(district_summary)} real districts flagged out-of-distribution "
          f"(mean|z| > {OOD_Z_THRESHOLD})")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
