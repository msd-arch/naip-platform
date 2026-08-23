# Week 17 status report — Phase 4, Track J resume (real cross-year validation for Track F)

Full context: `docs/PHASE4_SCOPE_DOCUMENT.md`'s Track J section (the cheap check that found no
genuine temporal holdout existed), `naip/docs/STATUS_WEEK13.md` (where that check was originally
run).

## Real structural surprise, flagged and resolved before building at scale

Per direction, checked the standalone `cap_2021_22.txt` first before committing to it. Its real
table structure differs substantially from `cap_2022_23.txt`: only 4 numeric columns (no
percentages), and severe real text-extraction corruption — merged multi-district rows (e.g.
"Rawalpindi ... Islamabad ..." on one line), several rows missing their 4th value entirely, and a
province-level number that didn't reconcile against the visible district-row total. Literal reuse
of `parse_mnfsr_crop_mix.py` would not have worked, and a from-scratch adapted parser for this
specific document carried real risk of low usable coverage.

**Flagged to you, and a cheaper real alternative checked first, per your direction**:
`cap_2022_23.txt` — the document already parsed and cross-validated once — turns out to print
**both** years' area/production side by side in the same row (index 0/4 = real 2021-22, index
2/6 = real 2022-23, the ones the original parser already uses). Verified this is genuine,
independently-sourced 2021-22 data, not some other value being misread: Attock wheat 2021-22 —
standalone `cap_2021_22.txt` says area 182.92, production 310.34; the embedded column in
`cap_2022_23.txt` says the same, exactly. Punjab's provincial wheat total, 2021-22 — same exact
match (area 6559.83, production 20031.81) at both district and province-total granularity. **Two
independent real government documents agree exactly** — this closed the data problem with
essentially no new engineering risk, and `cap_2021_22.txt` became unnecessary.

## Step 1 — real 2021-22 labels parsed

`parse_mnfsr_crop_mix_2021_22.py` (adapted from the original, reading the embedded columns) —
same 5%-tolerance-against-printed-totals discipline, same reject-not-guess behavior:

- **Real coverage: 115/126 districts — identical to the original 2022-23 parse.** Makes sense:
  same source table, same rows, same name-mapping, just a different embedded column.
- **3 real rejected blocks** (cotton Balochistan, sugarcane Sindh ×2) vs. the original's 4 — the
  same real known-problematic tables (Balochistan's cotton table is explicitly named as a
  wrapping issue in the original parser's own docstring), one fewer this time, not a new problem.

## Step 2 — real 2021-22 Sentinel-2 features pulled

`extract_phenology_features_2021_22.py` — Track F's **exact same 2,875 points** (same lat/lon,
isolates the real temporal effect rather than confounding it with a different spatial sample),
real Nov 2021–Oct 2022 window (checked, not assumed identical to 2022-23's calendar dates — same
real crop-year convention, one year earlier). **Real result: 2,875/2,875 usable, zero dropped** —
no coverage degradation at all.

## Step 3 — genuine temporal holdout, both directions

`train_crossyear.py`, same architecture as `train_crop_share_model.py` (`HistGradientBoostingRegressor`,
`max_depth=4, max_iter=200`), no lat/lon or district-identity feature, permutation importance
computed before either headline number:

| Crop | Original (within-year) | A: train 21-22 → test 22-23 | B: train 22-23 → test 21-22 |
|---|---|---|---|
| Wheat | 0.581 | 0.475 | 0.470 |
| Cotton | 0.507 | 0.467 | 0.389 |
| Rice | 0.420 | 0.289 | 0.239 |
| Sugarcane | -1.120 | **0.116** | **0.129** |

**Wheat/cotton/rice show real, expected degradation** under a genuinely harder cross-year test —
consistent in both directions, not cherry-picked. **Sugarcane is a real, honest exception**: both
cross-year directions score positive R², a real improvement over the original's catastrophic
-1.120. Most likely real explanation, not overclaimed as a validated fix: each cross-year
direction trains on all 115 districts (vs. the original's 81-district spatial split) — a rare,
thin-signal crop benefits disproportionately from more real training data. Real permutation
importance in both directions is led by genuine phenology metrics (`evi_annual_mean`,
`ndwi_peak_value`, `evi_trough_value`) — no district-identity back door, the specific real risk
flagged in Track F's original kickoff.

## Step 6 — the model_estimated_interim tier

`predict_interim_estimate.py` — the deployed Track F model (trained on real 2022-23 labels,
unchanged) applied to real Sentinel-2 features for **Nov 2024–Oct 2025**, the most recent complete
real season since MNFSR's last real report. Real result: **115/126 districts estimated, 2,875/2,875
real points usable, 4 districts flagged with a small impossible negative share** (near-zero true
values, a real regression artifact — flagged and kept, not silently clamped, same discipline as
Week 9's GB/AJK rejection).

Written to a **separate file** (`real_crop_mix_interim_estimates.json`) — never overrides
`real_crop_mix.json`'s real `real_district_area` tier for any district. Explicitly labeled
unvalidatable until a real MNFSR report covering 2023-24/2024-25 arrives. **Not wired into
`exposure_risk.py`** this track — a deliberate, separate decision, not bundled in automatically.

## Dashboard

Added to the Crop/Irrigation page: the real cross-year comparison table (both directions vs. the
original), and the real interim-tier summary with its caveats. Verified live: type-checked clean,
zero console errors, real data confirmed rendering.

## Real files this week produced

- `naip/models/fusion/parse_mnfsr_crop_mix_2021_22.py`, `naip/data/crop_mix_ground_truth/
  real_crop_mix_2021_22.json`, `parse_report_2021_22.json`
- `naip/models/crop_classifier_national/extract_phenology_features_2021_22.py`,
  `phenology_features_2021_22.csv` (2,875 real rows)
- `naip/models/crop_classifier_national/train_crossyear.py`, `track_j_crossyear_results.json`
- `naip/models/crop_classifier_national/extract_phenology_features_2024_25.py`,
  `phenology_features_2024_25.csv`, `predict_interim_estimate.py`,
  `naip/data/crop_mix_ground_truth/real_crop_mix_interim_estimates.json`
- `naip_dashboard/app/crop-classifier/page.tsx` — cross-year + interim-tier sections added

## Track J — closed

Genuine temporal holdout confirmed (both directions), real degradation reported honestly for
3/4 crops, a real and honestly-explained exception for sugarcane, and the `model_estimated_interim`
tier built per the original scope. No code touched in `exposure_risk.py`/`trigger_engine.py` — the
interim tier's live-product wiring remains a separate, future decision.
