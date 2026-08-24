# Week 22 — Phase 5, Track O (real yield prediction)

## Pre-check result — production data already existed, a real gap was found and closed

Read `parse_mnfsr_crop_mix.py` and `real_crop_mix.json` directly, per direction.
**Production figures were already extracted** by both the 2022-23 and 2021-22
parsers (`nums[6]`/`nums[4]` respectively) and sitting in `real_crop_mix.json`
/ `real_crop_mix_2021_22.json` already — zero new sourcing needed, exactly
the "possibly cheaper than expected" scenario the scope doc named.

**A real gap was found in the same pass, not assumed away**: neither parser
ever independently cross-validated production against its own printed
provincial total — only the area sum was checked (5% tolerance); production
values rode along on the area check passing, never verified on their own
terms. Confirmed the printed `Total` row does carry a real, checkable
production total (verified directly against real text: Punjab wheat Total
row = `6559.83, 6480.50, 20031.81, 21225.03` = area21-22, area22-23,
prod21-22, prod22-23). Built `build_real_yield_dataset.py`, re-parsing both
years with **both** area and production independently validated (same 5%
tolerance, reject-rather-than-guess discipline as the original).

**This closed a real, previously-invisible risk**: the new production check
caught 1 real province-crop block (2021-22) that passed the area check but
failed independently on production — it would have silently entered the old
pipeline's production figures uncaught before this week.

## Real coverage

| Year | Districts covered | (district,crop) yield cells | Real data-quality exclusions |
|---|---:|---:|---:|
| 2022-23 | 115/126 | 263 | 3 |
| 2021-22 | 115/126 | 257 | 4 |

Same real 115/126 scale as Track F/C's own crop-area work. Real, expected
zero-area cells (crop genuinely not grown in a district — 78-83 per year)
are reported separately from genuine data-quality exclusions, not
conflated into one alarming-looking number.

**Real distribution check, done before building anything** (per direction):
wheat/cotton/rice yields cluster 0.5-8 t/ha (agronomically sane for
Pakistan); sugarcane 36-100+ t/ha (also sane — a much bulkier crop). Found
and excluded, with reasons documented, not silently dropped:
- 7 cells (both years combined) where `production_000t` rounds to exactly
  `0.000` — a real print-precision floor (the source table rounds to 2
  decimal places; true production between 0 and 5 tons rounds to "0.00"),
  not a genuine zero. A yield ratio from it would be meaningless.
- 1 real, genuine outlier: Nasirabad rice, 2022-23 — area=48.78 (substantial,
  real), yield=0.221 t/ha, implausibly low for rice by any real agronomic
  standard. Excluded and documented, not investigated further (can't verify
  the specific cause without a source not on disk).

## Build

- No lat/lon or district-identity feature — same discipline as every prior
  model, enforced by construction (the feature set is Track F's exact 24
  real Sentinel-2 phenology metrics only).
- **Per-crop models, not Track F's multi-output shape**: yield is only
  *defined* where a crop is grown (unlike crop-share, where 0.0 is a valid
  value for an ungrown crop) — each crop gets its own
  `HistGradientBoostingRegressor`, trained only on real rows with a real,
  validated yield value for that crop.
- **Real cross-year validation, both directions**, same methodology as
  Track J's resumed work: train on one real MNFSR year, test on the other.
- **Real hazard-co-occurrence ablation: confirmed real-data-infeasible,
  checked not assumed.** NAIP's only real MSG archives are Nov 2021 (15
  days) and Nov 2023 (15 days) — neither gives meaningful coverage of
  either real yield-label growing season (2021-22 = Nov 2021-Oct 2022;
  2022-23 = Nov 2022-Oct 2023). A 15-day slice at the very start of one
  season isn't real "heat/drought exposure during the growing season" in
  any meaningful sense. Not attempted, not faked with a placeholder feature
  — reported as a real, checked negative rather than silently skipped.

## Real result — mostly negative, reported plainly

| Crop | Direction | Model R² (district) | Naive baseline R² | Winner |
|---|---|---:|---:|---|
| Wheat | A (train 21-22→test 22-23) | 0.380 | **0.769** | naive |
| Wheat | B (train 22-23→test 21-22) | 0.414 | **0.779** | naive |
| Cotton | A | **-2.307** | -2.645 | model (both poor) |
| Cotton | B | **-1.364** | -1.599 | model (both poor) |
| Rice | A | 0.057 | **0.141** | naive |
| Rice | B | **-0.110** | -0.766 | model (both poor) |
| Sugarcane | A | 0.103 | **0.352** | naive |
| Sugarcane | B | 0.080 | **0.123** | naive |

**A real, cheap, zero-model naive baseline ("this district's yield this
year = its real reported yield the other real year") beats the trained
Sentinel-2 phenology model in 6 of 8 crop×direction combinations** — for
wheat and sugarcane in both directions, and rice in one. The 2 cases the
model "wins" (cotton both directions, rice direction B) are both cases
where *both* model and baseline score clearly negative R² — a real "which
one is less bad" result, not a genuine win for either.

**Why, concretely, not hand-waved**: real district-level wheat yield is
highly persistent year-over-year in this specific real data (naive
baseline R²≈0.77-0.78) — a genuinely high bar. Satellite phenology from a
*different* year, predicting a target that mostly just repeats itself, has
little room to add value over simple persistence. This is a real, useful
finding about the task's real difficulty, not a modeling failure to fix by
tuning harder.

**Real permutation-importance self-check, before any of these numbers were
reported**: confirmed the model is learning genuine phenology signal where
it has any skill at all — top features across crops/directions are real
metrics (`evi_annual_mean`, `ndwi_peak_value`, `ndvi_green_up_slope`,
`evi_senescence_slope`), never a location proxy (impossible by construction
— lat/lon/district-identity were never in the feature set).

## What this doesn't claim

Stated explicitly, per direction: yield prediction is a real, useful input
to exposure risk, **not** a substitute for the actuarial claims/loss-data
gap flagged as unresolved since Week 4. This track's existence does not
imply that gap is closed.

## Dashboard

Added to the Crop/Irrigation page, below Track F/J's crop-share results:
real per-crop, per-direction model-vs-naive-baseline table (naive wins
visually flagged, not hidden), the real hazard-ablation infeasibility
finding stated in full, and the "what this doesn't claim" caveat kept
visible. Verified live in the browser — all real numbers render exactly as
computed.

## Real files this week produced

- `naip/models/fusion/build_real_yield_dataset.py` (production
  cross-validation extension + real yield dataset builder)
- `naip/data/crop_mix_ground_truth/real_crop_yield.json`,
  `real_crop_yield_report.json`
- `naip/models/crop_classifier_national/train_yield_model.py`,
  `track_o_yield_results.json`
- Dashboard: `app/crop-classifier/page.tsx`, `prepare_data.py`
  (new source wired in), regenerated `public/data/*`
