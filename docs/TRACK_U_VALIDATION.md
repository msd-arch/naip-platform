# Track U — formalized validation pipeline

Real, closed 2026-08-29. Two real deliverables: a shared validation module
extracted from the pattern every prior model already used by hand, and a
live automated regression check now running as its own scheduled task.

## 1. `naip/validation/standard_checks.py`

Five real, runnable functions (not a documentation-only checklist),
extracted from what Track E/F/D/O/L already did independently by hand:

- `check_no_identity_leak(feature_names, allow=())` — raises on a banned
  lat/lon/district-identity column in a real feature list, unless
  explicitly allowed with a reasoned exception (Track L's fixed-grid
  lat/lon pattern).
- `assert_no_group_overlap(splits, group_values)` — the general form of
  "whole districts/dates held out", confirms no group id appears in more
  than one split.
- `class_balance_report(y, ...)` / `regression_distribution_report(y, ...)`
  — real positive-rate or min/max/mean/std/near-zero/outlier report,
  printed before training.
- `permutation_importance_report(model, X_test, y_test, feature_names,
  scoring, flagged_features=(), ...)` — shared wrapper around sklearn's
  `permutation_importance`, with a loud warning if a flagged
  positional/identity feature dominates (the exact Track E lat/lon-leak
  pattern).
- `baseline_comparison_report(model_metric, baseline_metric, ...)` — prints
  and returns the real before/after line every prior model's script
  already printed by hand.

All five smoke-tested against synthetic data before use.

## 2. Retroactive audit — real findings

Read the real training scripts for all five named models directly (not
from memory or prior session logs) against the 5-item checklist above.

| Model | Result |
|---|---|
| Track E (fire, `train_fire_classifier.py`) | clean, all 5 checks present |
| Track F (crop-share, `train_crop_share_model.py`) | clean, all 5 present |
| Track D/I (flood v3, `train_flood_classifier*.py`) | clean, all 5 present |
| Track O (yield, `train_yield_model.py`) | **1 real gap found** — see below |
| Track L (fusion U-Net, `Downloads/ml_pipeline/`) | clean, all 5 present, including a reasoned lat/lon exception (fixed per-pixel grid encoding, not row identity — documented in `permutation_check_track_l.py`'s own docstring) |

**Real gap found and fixed**: Track O's distribution/outlier check (the
7 near-zero print-precision cells and 1 genuine outlier reported in
`STATUS_WEEK22.md`) was a one-off manual pass, not repeatable code — unlike
the other four models, which all print their distribution/balance check
inline. Retrofitted `regression_distribution_report()` into
`train_yield_model.py` (real yield-label distribution, computed per crop
before training, persisted into `track_o_yield_results.json` as
`real_yield_label_distribution`). Re-ran the real script end to end —
confirms real results unchanged in shape, adds genuinely new information
(e.g. rice: 49/2,719 real IQR outliers, sugarcane: 53/1,239) not previously
surfaced as a repeatable number. Note: this checks the real `label_yield`
field the model trains on directly, which is a different (also real, also
useful) field from the original `STATUS_WEEK22.md` note's `production`
figures further upstream in the MNFSR parsing step — not a literal
re-creation of that specific historical finding, a genuinely new check on
the field that actually matters for this training script.

## 3. `naip/validation/regression_check.py`

A real, narrow schema/freshness check over the ~18 files
`naip_dashboard/app/components/explore/ExploreView.tsx` actually fetches.
The field contract is sourced directly from
`naip_dashboard/app/explore/types.ts` (the dashboard's own real TypeScript
consumer interfaces), not re-derived from memory. Checks, per file:

1. **File exists and is valid JSON.**
2. **Required fields present** — both top-level and, for list-shaped data,
   across a real sample of rows (union of keys across up to 25 rows, not
   just row 0, so one atypical first row can't produce a false result).
   This is the exact real bug category Week 31 found by hand:
   `locust_risk.json` silently stopped emitting the field the dashboard's
   `LocustRegion` type expected (`vegetation_greenup_detected` →
   `vegetation_not_browning`), rendered as "No" for months undetected.
3. **Freshness** — for files carrying `last_computed_utc`, flags if real
   age exceeds that file's documented real cadence + slack: drought/flood/
   locust weeklies get 174h (weekly + 6h slack), the forecast layer gets
   30h (GFS's real 4x-daily/~6h cadence + slack), trigger summaries get 48h
   (tied to the live loop's optional trigger-eval step, generous slack
   since it doesn't run every cycle).

Exit code 0 = clean, 1 = at least one real error — same fail-loud
convention every scheduled script in this project already uses.

**First real run against live data**: 18 files checked, 0 errors, 1
warning (`audit_log_national.json` has 0 real rows to check row-level
fields against — confirmed this is the real, expected Week 20/21 state,
0 national-illustrative-threshold trigger events, not a bug).

## 4. Scheduling

`naip/pipelines/scheduler/regression_check_daily.py` wraps
`regression_check.py` in the same one-cycle-and-exit + `n_success`/
`n_failure`-style state-tracking pattern every other scheduled script in
this project uses (`regression_check_state.json`: `n_clean`, `n_findings`,
`n_script_error`, separated so a real script crash is never folded into
"found real findings").

**Real scheduled task**: `NAIP-RegressionCheck`, daily at 05:00, with the
battery-power fix (`AllowStartIfOnBatteries`) applied proactively from the
start this time, not rediscovered a fourth time. Daily, not weekly or tied
to Track H's 15-minute cadence: most watched files refresh weekly, so a
15-min check would just re-check unchanged data, but a weekly-only check
risks a silently-stopped producer going undetected for up to 6 real days —
daily is the real, honest middle ground.

**Real verification, not just a manual run**: triggered via
`Start-ScheduledTask`, confirmed `LastTaskResult = 0` from Task Scheduler
itself, and confirmed `regression_check_state.json`'s `n_clean` incremented
1→2 from that actual scheduled-task-triggered run (not just the direct
script invocation used to build/debug it). No conflict with Track H or the
three existing weeklies — this script only reads their real output files
and writes its own separate report/state/log files.
