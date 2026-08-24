# Week 20 — Phase 4, final item: wire model_estimated_interim into exposure_risk.py

## What this closes

The last open item on Phase 4's original roadmap. `model_estimated_interim` (built
in Track J, Week 17) already existed as a real, tested output -- Track F's
deployed crop-share model applied to real Sentinel-2 features for Nov 2024-Oct
2025 -- but sat in its own file, unconsumed by the live exposure/trigger
pipeline. This wires it in as a real third tier, with the same three-tier
honesty discipline `crop_mix_source` has carried since Track G.

## The tiering rule, implemented exactly as scoped

`real_crop_mix.py` (single source of truth for all three tiers now) resolves,
per **(district, crop, date)** -- date-awareness is new this week:

1. `real_district_area` -- real MNFSR data, but **only for the 2022-23 season
   it actually covers**. Always wins there, never overridden.
2. `model_estimated_interim` -- Track F's real model prediction, used only
   when the district has real MNFSR coverage (i.e. isn't one of the 11
   GB/AJK districts) AND the alert's growing season is chronologically after
   2022-23.
3. `hand_classified_mask` -- the 11 GB/AJK districts, unchanged, regardless
   of date, per Track G's standing rejection of the model there.

A real, necessary correction this surfaced: `exposure_risk.py`'s tiering
functions had **never been date-aware at all** -- every row, regardless of
its actual alert date, silently used the single 2022-23 MNFSR snapshot. This
week is the first time the pipeline asks "which season is this alert
actually in?" at all.

## Build

- `real_crop_mix.py`: added `season_of(date)` (Nov-Oct convention, matching
  Track F's own `extract_phenology_features*.py` season boundary) and
  `season_after_mnfsr(date)`. `crop_mix_tier`, `crop_share`, `is_plausible_real`
  now all take `date` and implement the real 3-tier precedence centrally.
  Verified against the same 115 districts in both `real_crop_mix.json` and
  `real_crop_mix_interim_estimates.json` (exact match, confirmed before
  writing any resolution code) -- the 11 GB/AJK districts are automatically
  excluded from tier 2 with zero extra code, preserving Track G's rejection.
- `exposure_risk.py`: `resolve_plausibility`/`resolve_crop_weight` now take
  `date`; every row's `crop_mix_source`/`crop_mix_share_of_4crop_area` field
  is resolved through the real 3-tier logic. Added a real, full-archive
  `crop_mix_source_breakdown` count to the JSON output (row-level, not the
  static 126-district coverage count Track G's summary already had).
- `trigger_engine.py`: zero logic changes needed (it already reads
  `crop_mix_source`/`crop_mix_share_of_4crop_area` straight from each row) --
  `BASIS_RISK_NOTE` updated to name the interim tier as a third, explicit
  basis-risk source: a trained model's estimate, not a government survey,
  genuinely unvalidatable (per Track J's own finding) until a future real
  MNFSR report arrives.

## Real before/after -- reported plainly, including the part that ran counter to expectation

Ran the real full pipeline (`exposure_risk.py` -> `trigger_engine.py`)
against the real operational archive (`hazards_district_national.json`,
35,532 real alerts, 2026-06-22 to 2026-07-20). Computed the true "before"
baseline by running the old, pre-this-week code against the same real
archive (not estimated) for an honest comparison.

**Row-level tier resolution, full archive (141,120 rows)**:

| Tier | Before | After |
|---|---:|---:|
| `real_district_area` | 128,800 | 0 |
| `model_estimated_interim` | (didn't exist) | 128,800 |
| `hand_classified_mask` | 12,320 | 12,320 (unchanged) |

**Real, structurally significant, and expected once you see it**: every real
alert in NAIP's operational archives postdates 2022-23 -- the archives start
mid-2026, NAIP simply has no hazard data from MNFSR's covered season at all.
So essentially every MNFSR-covered row shifts to `model_estimated_interim`.
This is not a data-quality regression -- it is the correct, honest
consequence of making the pipeline season-aware for the first time; the
*previous* behavior (silently applying a 2022-23 snapshot to 2026 alerts)
was the real gap being closed.

**Plausibility and exposure-score effects**: zero flips from plausible ->
implausible (safety-preserving direction). 22,428 flips from implausible ->
plausible -- because Track F's continuous model rarely predicts an exact
zero the way MNFSR's table did for many (district, crop) cells; many tiny
near-zero real predictions (0.001-0.03 range) newly clear the `share > 0`
plausibility bar. Nonzero exposure-score rows: 583 -> 1,243.

**Real trigger events -- the unexpected part, flagged and confirmed with you
before finalizing**: rather than rising (the direction anticipated when this
track was scoped), real trigger events at both operational thresholds
**fell**:

| Threshold | Before | After |
|---|---:|---:|
| Illustrative (0.225) | 3 | **0** |
| Demo (0.07) | 130 | **9** |

**Why, concretely, not hand-waved**: the interim model's real predictions
for the specific districts that drove the old (stale-season) triggers are
genuinely different from the 2022-23 snapshot. E.g. Sialkot's real 2022-23
rice share was 48.95%; Track F's real 2024-25 estimate for the same
district is 35.14% -- a real, meaningful drop consistent with Track F's own
validated accuracy (rice R²=0.420 on held-out districts, moderate, not
perfect), not a bug. Confirmed with you: proceed as specified, report this
plainly, leave threshold recalibration as an explicit separate decision --
matching Week 9's own precedent of not conflating a data-source change with
a threshold change in the same pass.

## Dashboard

- **Exposure Risk page**: new warning panel explaining the three-tier rule
  and the interim tier's real caveat up front; a new row-level tier-breakdown
  bar sourced from the live `exposure_risk.json` (`crop_mix_source_breakdown`,
  the real current archive's actual resolution); the old district-coverage
  bar kept but re-labeled "season-independent" and clearly distinguished from
  the row-level one, so the two real, different questions ("which districts
  does real data cover at all" vs. "which tier is this real archive's alerts
  actually resolving to") are never conflated.
- **Trigger Engine page**: `crop_mix_source` now shown per trigger event (table
  column + detail-panel row + real crop-mix share %), with an explicit
  inline caveat whenever a selected event is `model_estimated_interim`-tier.
  `basis_risk_note` already carries the new tier-3 language verbatim (no
  page code needed there -- it renders whatever the audit record contains).
- **Real bug found and fixed while wiring this through**: `prepare_data.py`'s
  `audit_log_national.json` source was still pointed at the stale
  `audit_log.jsonl` (Week 4, threshold 0.35) even after Week 12's
  doc-consistency pass fixed `trigger_summary_national.json`'s own mapping.
  The Trigger Engine page's summary stats were correct; the actual
  audit-record table below them was silently showing stale 0.35-threshold
  events the whole time. Fixed: now sources `audit_log_national.jsonl` (the
  real, current, threshold-0.225 file).
- Verified live in the browser (dev server, not just eyeballing the JSON):
  Exposure Risk page's three panels render the real 0/128,800/12,320 and
  115/0/11 splits exactly as computed; Trigger Engine's national tab now
  correctly shows 0 events, demo tab shows the real 9, each tagged
  `model-estimated interim`, detail panel showing Sialkot's real 35.14%
  share and the new basis-risk text.

## What this doesn't change

The 11 GB/AJK districts' resolution is untouched -- still the hand mask,
regardless of date, per Track G's standing rejection. No season MNFSR
actually covers is ever overridden by the interim tier. Threshold
recalibration (0.225/0.07) was explicitly NOT revisited this week, per
direction -- a separate decision if wanted, now that the real post-interim
score distribution is known.

## Real files this week produced/changed

- `naip/models/fusion/real_crop_mix.py`, `exposure_risk.py`
- `naip/backend/insurance_engine/trigger_engine.py`
- `naip/models/fusion/exposure_risk.json`, `exposure_risk_top*.csv`
  (regenerated)
- `naip/backend/insurance_engine/trigger_summary_national.json`,
  `trigger_summary_demo.json`, `audit_log_national.jsonl`,
  `audit_log_demo.jsonl` (regenerated)
- Dashboard: `app/exposure-risk/page.tsx`, `app/trigger-engine/page.tsx`,
  `prepare_data.py` (bug fix), regenerated `public/data/*`
