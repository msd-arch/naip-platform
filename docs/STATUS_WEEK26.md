# Week 26 status report — Track I, precipitation attempt (flood model, v3)

Full context: `naip/docs/STATUS_WEEK14.md` (Track I's v2, rejected), `naip/docs/STATUS_WEEK10.md`
(Track D's original training), `naip/docs/STATUS_WEEK11.md` (the live over-flagging finding
both attempts exist to fix).

## Why this attempt is different in kind, not degree

v2 added more non-disaster negative examples of the *same* feature type (SAR backscatter) and
failed because the model globally suppressed its scores rather than learning real
discrimination (mean score gap by true label collapsed from 0.096 to 0.012). SAR backscatter
change tells you "the ground got wetter," not why — ordinary monsoon rain and catastrophic
flood-producing rain can look similar in backscatter alone at this feature set's resolution.
This attempt adds a physically distinct signal the model has never had: real rainfall.

## Pre-check — real precipitation dataset choice, verified live via GEE before building

| Dataset | Resolution | Real coverage confirmed (2021/2022/2024) | Spot-check (Lahore point, 2022-08-15..09-16) |
|---|---|---|---|
| **CHIRPS Daily** | ~5.5km (0.05°) | Yes, 32-45 real images/window every year | 69.6mm total |
| ERA5-Land Daily Aggr | ~11km (0.1°) | Yes | 33.7mm (real, known regional dry bias) |
| GPM IMERG V07 | ~11km (0.1°) | Yes, shorter real historical depth (GPM era, ~2000+) | 129.7mm (real, known wet bias) |

**CHIRPS chosen**: finest real resolution of the three, longest real historical depth
(1981–present, used here for a 20-year 2001–2020 climatology baseline with zero overlap with
any test/positive year), and its Lahore-point spot-check landed between the other two rather
than at either bias extreme. **Honest resolution caveat, stated not hidden**: CHIRPS's ~5.5km
pixels are still far coarser than the ~30m SAR features — within a small/urban district,
several of the 15 sampled points can land in the same CHIRPS pixel and read identical
precipitation. This doesn't invalidate the feature (rainfall genuinely doesn't vary at 30m
scale the way SAR backscatter does), but it means precipitation adds less within-district
differentiation than the SAR/JRC features do.

## What was built

- `add_precipitation_features.py` — added `precip_total_mm` (real CHIRPS sum over each
  dataset's existing during-window) and `precip_anomaly_pct` (vs. each point's real 20-year
  2001–2020 CHIRPS climatological mean for the same calendar day-range) to all four existing
  datasets (`flood_dataset.csv`, `_2021.csv`, `_2024.csv`, `_2024_negatives.csv`) — **purely
  additive, existing SAR/JRC columns untouched**. None of the original CSVs persisted lat/lon;
  all four were previously confirmed zero-dropped, so this script exactly replayed each
  dataset's original district-order + `randomPoints(seed=42)` logic to regenerate identical
  coordinates, then asserted row-count and per-row district alignment before merging (not a
  best-effort spatial join) — verified aligned for all 5,565 real points across all four files.
- `train_flood_classifier_v3.py` — same architecture, same two evaluations (Eval 1: original
  2022 test districts with expanded 2021-negative training; Eval 2: cross-year 2024 recall),
  same spatial-blocking discipline, features = original 5 + `precip_total_mm` +
  `precip_anomaly_pct`.
- `eval_2024_full_v3.py` — the same fair, labeled, full 2024 test (14 positive + 112 negative
  districts) v2 used, scoring all three models (original/v2/v3) side by side, plus the exact
  score-separation-by-true-label diagnostic that caught v2's collapse.
- `replay_live_screen_v3.py` — the same live-replay approach, real current CHIRPS total +
  rolling same-calendar-range 20-year climatology anomaly, all three models scored side by side.

## Real result 1 — permutation importance (non-negotiable check, done first)

`precip_anomaly_pct` is the **single highest-importance feature** in the retrained model
(0.128), well above every SAR feature (`VH_change` 0.0165, `VV_change` 0.0105) and
`precip_total_mm` (0.0319) — a real, substantial, meaningfully-used signal, not noise added for
its own sake.

**Sanity-checked directly against the labeled data** (not just importance scores): mean
`precip_anomaly_pct` for flooded vs. not-flooded 2022 points is **+258.6% vs. +6.7%**; for the
2024 fair test, flooded vs. not-flooded is **+216.4% vs. +94.6%**. Both real, large, and in the
physically expected direction (flooded places really did get far more rain than their own
historical norm) — this is not a spurious correlation, it's the actual real-world mechanism the
feature was added to capture.

## Real result 2 — Eval 1 (original 2022 test districts, expanded training)

| | Precision | Recall | F1 | AUC |
|---|---|---|---|---|
| Original (Track D) | 0.817 | 0.674 | 0.738 | — |
| v2 (2021-expanded) | 0.783 | 0.418 | 0.545 | — |
| **v3 (precip-augmented)** | **0.974** | 0.670 | **0.794** | 0.872 |

Unlike v2, v3 does not trade recall for a worse overall result — precision rises sharply
(0.817→0.974), recall holds roughly level (0.674→0.670), and F1 improves (0.738→0.794).

## Real result 3 — the decisive test: fair, labeled, full 2024 cross-year eval

| | Precision | Recall | F1 | AUC | Score-separation gap |
|---|---|---|---|---|---|
| Original (Track D) | 0.134 | 0.776 | 0.229 | 0.602 | 0.096 |
| v2 (2021-expanded) | 0.107 | 0.371 | 0.166 | 0.519 | **0.012 (collapsed)** |
| **v3 (precip-augmented)** | **0.190** | **0.862** | **0.312** | **0.761** | **0.332** |

**A real, substantial improvement on the exact fair test that caught v2's collapse** — every
metric improves over the original, and the score-separation gap (0.332) is not just larger than
v2's collapsed 0.012, it's more than 3x the *original* model's own gap (0.096). This is the
opposite of v2's failure mode: genuine, strengthened discrimination between flooded and
not-flooded conditions, confirmed on data neither model was trained on.

## Real result 4 — live national screen replay (2026-07-28..08-27)

| | Districts flagged (≥0.5) | Mean score | Score range |
|---|---|---|---|
| Original | 118/126 | 0.669 | [0.424, 0.925] |
| v2 | 41/126 | 0.478 | [0.355, 0.637] |
| **v3** | **9/126** | **0.190** | **[0.023, 0.823]** |

A far more plausible national picture than either prior version, with real per-district spread
(0.80-point range) rather than v2's compressed 0.28-point band — consistent with genuine
discrimination, not suppression, matching the fair-test finding above.

**Real, honestly-flagged open question, not smoothed over**: the 9 currently-flagged districts
(Gujrat, Islamabad, Abbottabad, Rawalpindi, Jhelum, Sialkot, Narowal, Azad Kashmir, Haripur — all
northern Punjab/KP/AJK) all show a **negative** real precipitation anomaly right now (-46% to
-70% vs. their own historical norm for this exact calendar window) — the opposite direction of
the strong positive correlation the training data itself shows. This is a real, not-fully-
explained pattern: it may reflect these historically wetter northern districts still carrying
substantial *absolute* rainfall despite being below their own seasonal average, a genuine
SAR-driven signal independent of precipitation, or a real GBT non-monotonic interaction between
features — not investigated further this week, flagged honestly as an open question rather than
asserted either way. Per the caution built into this track's own design: a live-replay number is
not evidence on its own — the fair 2024 test above is.

## Decision point — flagged, not decided

Per your explicit instruction, this is *not* an automatic green light to wire v3 into
`exposure_risk.py`/`trigger_engine.py`. What's real and decisive here: v3 shows genuine,
fair-test improvement across every metric, passes the exact diagnostic that caught v2's
failure, and the precipitation feature is confirmed both highly-important and physically
sensible in direction. What's still open: absolute precision (0.190) means most "flooded"
predictions on a genuinely new year are still wrong, and the live-replay anomaly-direction
question above is unresolved. **This is your call to make**, not something built automatically
in response to a good result.

## Files this week

- `naip/models/flood_risk/add_precipitation_features.py`
- `naip/models/flood_risk/train_flood_classifier_v3.py`, `track_i_v3_precip_results.json`,
  `gbt_flood_classifier_v3_precip.joblib`, `gbt_flood_classifier_v3_precip_fulltrain.joblib`
  (candidates only, **not deployed** — `gbt_flood_classifier.joblib`, the file every other part
  of the product references, is untouched)
- `naip/models/flood_risk/eval_2024_full_v3.py`, `track_i_v3_2024_full_eval.json` (the decisive
  evaluation)
- `naip/models/flood_risk/replay_live_screen_v3.py`, `track_i_v3_live_replay.json`
- `flood_dataset.csv`, `flood_dataset_2021.csv`, `flood_dataset_2024.csv`,
  `flood_dataset_2024_negatives.csv` — each gained `precip_total_mm`, `hist_mean_precip_mm`,
  `precip_anomaly_pct` columns; every original column untouched.
