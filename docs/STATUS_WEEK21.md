# Week 21 — Threshold recalibration: tier-aware, crop-aware

## What this closes

Week 20's `model_estimated_interim` wiring left the exposure/trigger threshold
question deliberately deferred: a flat threshold treats every interim-tier
prediction as equally trustworthy regardless of which crop it's for, even
though Track F's own validated accuracy differs sharply by crop (rice/
sugarcane meaningfully weaker than wheat/cotton). This closes that gap with a
real, crop-differentiated confidence discount derived directly from Track F's
own numbers — not an arbitrary re-pick of a single flat value.

## The mapping, proposed and confirmed before wiring into live logic

Per direction, three candidate R²-to-multiplier formulas were computed and
presented before any of them touched live trigger logic:

- **Option A — direct R² clamp** (`multiplier = clamp(mean_r2, 0, 1)`): no
  free parameters, uses the validated statistic literally.
- Option B — `sqrt(clamp(r2, 0, 1))`: gentler, but the choice of sqrt over
  R² itself has no statistical justification beyond producing softer numbers.
- Option C — relative-to-wheat rescaling: treats wheat (the model's best
  crop) as a ~1.0x trust ceiling, which undercuts the reason for a
  discount at all.

**Confirmed: Option A.** Reasoning (yours, recorded here for the audit
trail): R² is already a genuine 0-1 variance-explained quantity, so using it
directly needs no additional transform to defend later — the same
no-free-parameters discipline this project applied when rejecting a
threshold picked to preserve the Layyah scenario, and when rejecting Track
I's v2 flood model's suppressed scores as a real improvement. The
conservative bias (wheat still needing ~2.1x the raw score of a real-tier
row) is treated as a feature, not a flaw, given this feeds a system whose
eventual purpose is real payouts.

**Real per-crop values used** — the mean of Track F's own two real cross-year
holdout directions (`STATUS_WEEK17.md`'s district-level table, not the
original within-year figures):

| Crop | R² (direction A) | R² (direction B) | Mean (used) | Required-score multiplier |
|---|---:|---:|---:|---:|
| Wheat | 0.475 | 0.470 | 0.4725 | needs 2.1x |
| Cotton | 0.467 | 0.389 | 0.4280 | needs 2.3x |
| Rice | 0.289 | 0.239 | 0.2640 | needs 3.8x |
| Sugarcane | 0.116 | 0.129 | 0.1225 | needs 8.2x |

## Build

- `real_crop_mix.py`: `INTERIM_CROP_R2_MEAN`, `interim_confidence_multiplier(crop)`,
  `resolve_interim_confidence(district, crop, date)` — returns 1.0 for
  `real_district_area`/`hand_classified_mask` tiers (current effective bar
  unchanged, unaffected by this change), the real per-crop multiplier only
  for `model_estimated_interim` rows.
- `exposure_risk.py`: confirmed the real current architecture first, per
  direction — `exposure_score` is computed and persisted entirely here;
  `trigger_engine.py` only does a bare `>= threshold` comparison, unaware of
  crop/tier. Baking the discount into `exposure_score` itself (not a
  side-channel in `trigger_engine.py`) matches the established Week 9
  pattern (fold real signal into the score, not a parallel gate) and keeps
  `trigger_engine.py`'s comparison logic completely unchanged. Every row now
  carries `interim_confidence_multiplier` and
  `exposure_score_before_confidence_discount` — nothing silently lost.
- `trigger_engine.py`: zero logic changes (as expected, confirmed not
  assumed). `BASIS_RISK_NOTE` and `build_audit_record` updated to surface the
  multiplier as a real, structural part of basis risk, not just prose.

## Real before/after — reported plainly, including the severe part

**Empirical confirmation the crop-differential effect is real, not just
theoretical** (per direction, checked directly): at nearly identical raw
scores (~0.049-0.052), cotton rows end up with final scores ~0.021-0.022
while rice rows end up at ~0.013 — cotton's lighter discount visibly wins at
matched inputs.

**Real trigger counts, both thresholds**:

| Threshold | Before this change (flat, Week 20) | After (crop-aware) |
|---|---:|---:|
| Illustrative (0.225) | 0 | 0 (unchanged — already 0 after Week 20) |
| Demo (0.07, then re-derived) | 9 (all rice) | **0** at the original 0.07 |

**The severe, unexpected consequence, flagged before finalizing**: applying
the real per-crop discount pushed every one of Week 20's 9 demo events below
the *original* 0.07 threshold too — the real max score anywhere fell to
0.0362. This broke `prepare_data.py`'s demo-scenario step, which hard-stopped
(`SystemExit(1)`) if it couldn't find the Gujranwala/20260623 record.

**Two real fixes, kept as separate decisions, per direction**:
1. **Mandatory bug fix**: `prepare_data.py` no longer crashes when a real,
   legitimate demo-threshold result is zero events — that's valid output,
   not a pipeline error. Writes an honest empty `demo_scenario.json` instead.
2. **Separate, explicit re-derivation**: the demo threshold was re-derived
   using the *same real selectivity-matching method* Week 9 used — not
   picked to preserve the Gujranwala scenario. Target: Week 20's real demo
   selectivity immediately before this change (9/1243 nonzero plausible
   rows, ≈0.72%). Re-matched against the new post-discount distribution:
   **new demo threshold = 0.0216** (the score of the 9th-highest real row).

**Real result at the re-derived demo threshold (0.0216): 9 events**, and the
crop-differential effect is now directly visible in which events they are —
**6/9 cotton, 3/9 rice** (was 9/9 rice under the flat-threshold version).
Cotton's lighter discount (0.428 vs. rice's 0.264) is doing real, observable
work, not just existing in a formula. The Gujranwala/uv_index/rice demo
scenario happens to still clear the new threshold (checked, not assumed) —
no scenario swap needed.

Illustrative threshold (0.225) stays at 0 real events both before and after
this change — the real score ceiling (0.0362) is far below it regardless of
the crop discount; this threshold's own recalibration was explicitly not
revisited this week, per Week 20's standing deferral.

## Dashboard

- **Exposure Risk page**: new panel showing the real per-crop multiplier and
  its "needs Nx raw score" consequence for all four crops; new `Confidence ×`
  table column.
- **Trigger Engine page**: threshold button label updated (0.07 → 0.0216);
  `Confidence ×` table column; detail panel shows the raw pre-discount score
  and the specific crop's R²-derived multiplier; `basis_risk_note` (shown
  verbatim) now explains the structural mechanism, not just names the tier.
- Verified live in the browser: Exposure Risk's confidence-multiplier panel
  renders the real wheat/cotton/rice/sugarcane values and "needs Nx" text
  exactly as computed; Trigger Engine's demo tab shows the real 9 events
  (6 cotton / 3 rice) with correct per-row multipliers, and the detail panel
  for Sialkot/rice shows raw=0.1371, multiplier=×0.264, final=0.0362.

## What this doesn't change

The 11 GB/AJK hand-mask districts are unaffected — no discount logic applies
to them, unchanged from every prior week. Real MNFSR-tier rows keep
multiplier 1.0 (no change to how confidently real government data is
trusted). The illustrative (0.225) threshold's own value was not revisited.

## Real files this week produced/changed

- `naip/models/fusion/real_crop_mix.py`, `exposure_risk.py`
- `naip/backend/insurance_engine/trigger_engine.py`
- `naip/run_end_to_end_demo.py` (default threshold + docstring updated)
- `naip/models/fusion/exposure_risk.json`, `exposure_risk_top*.csv`
  (regenerated)
- `naip/backend/insurance_engine/trigger_summary_national.json`,
  `trigger_summary_demo.json`, `audit_log_national.jsonl`,
  `audit_log_demo.jsonl` (regenerated)
- Dashboard: `app/exposure-risk/page.tsx`, `app/trigger-engine/page.tsx`,
  `prepare_data.py` (crash fix), regenerated `public/data/*`
