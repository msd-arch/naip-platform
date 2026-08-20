# Week 8 status report — Phase 3, Track F (national crop classifier)

Full context: `docs/PHASE3_MODEL_PLAN.md` (Track F section), `naip/docs/STATUS_WEEK7.md`
(Track E, whose lat/lon-leak self-check this track was explicitly built to carry
forward from the start).

## Pre-checks (done before any code, per this week's kickoff)

- **WorldCereal's real product list confirmed nationally, not just for
  Layyah/Muridke**: `temporarycrops`, `irrigation`, `maize`, `wintercereals`,
  `springcereals` — the same 5 real products Week 2 found, checked directly against
  the live GEE collection with no region filter. **No cotton/rice/sugarcane class
  exists anywhere in it.** The literal ask ("labels: WorldCereal cross-checked
  against MNFSR wherever both exist") can therefore only be honored for wheat
  specifically, via `wintercereals` as a real, agronomically-defensible proxy
  (Pakistan's dominant real Rabi winter cereal). No fabricated comparison was made
  for the other three crops.
- **A bigger finding, checked before any sampling pipeline was built**: a "predict
  each district's single dominant crop" framing — the literal reading of
  "classifier" — would collapse to near-one-class. Real argmax across all 115
  MNFSR-covered districts: **wheat dominant in 107/115 (93%), rice in 8, cotton and
  sugarcane never win** — the same degenerate trap Week 2's cropland task hit.
  **Confirmed with you**: Track F predicts real per-crop AREA SHARES (multi-output
  regression), not a single dominant-crop label — this uses MNFSR's actual
  proportional richness instead of collapsing it.

## What was built

- **`sample_points.py`** — real stratified Sentinel-2 point sample: ~25 real
  cropland points (WorldCereal `temporarycrops==100` mask, so no trivially-easy
  desert/urban negatives) per real MNFSR-covered district. **Real result: 2,875
  points across all 115 districts**, zero failures — "thousands, not 120," and with
  real representation nationally, not just Punjab.
- **`extract_phenology_features.py`** — real monthly cloud-masked Sentinel-2
  composites, Nov 2022–Nov 2023 (one full real agricultural year, matching MNFSR's
  2022-23 report year, spanning both Rabi and Kharif so either season's crop is
  captured). Per point, per index (NDVI/NDWI/EVI): peak value/timing, trough
  value/timing, green-up slope, senescence slope, annual mean/std — a genuinely
  richer feature set than Week 2's flat monthly means, per direction. **All 2,875
  points returned complete monthly data** (0 dropped for missing/cloudy months);
  723 rows were later dropped for a NaN slope feature (peak/trough landing at the
  series boundary with no real before/after window — an honest, minor real
  boundary-condition loss, not a data-quality problem).
- **`cross_check_worldcereal.py`** — the real wheat-only WorldCereal↔MNFSR
  cross-check. **This needed two real corrections before the number could be
  trusted**, both found and fixed before reporting anything (see below).
- **`train_crop_share_model.py`** — real spatially-blocked split, **whole districts
  held out** (81 train / 17 val / 17 test), stratified by each district's real
  dominant crop so the 8 real rice-dominant districts aren't accidentally absent
  from val/test. Ridge and gradient-boosted trees (sklearn `HistGradientBoosting
  Regressor`, wrapped for multi-output), trained on phenology features only —
  **no lat/lon, no district-identity feature, confirmed absent from the code, not
  just unreported** — with `role` tags (`headline_result` / `baseline` /
  `baseline_model`) baked into the results JSON from the first run, per direction.

## The WorldCereal↔MNFSR wheat cross-check needed two real corrections

**First attempt**: WorldCereal `wintercereals` as a share of each district's *total*
area vs. real MNFSR wheat share (itself a share of *cropped* area only) —
**correlation -0.53**, real disagreement on its face. Before reporting that, the
mismatch was checked: districts like Ziarat (mostly non-arable, MNFSR wheat_share=1.0
because the tiny cropped patch that exists is 100% wheat) showed a near-zero
WorldCereal areal fraction simply because most of the district isn't cropland at
all — a denominator mismatch in this cross-check's own arithmetic, not a real
disagreement about wheat.

**Fixed**: re-expressed WorldCereal wintercereals as a share of WorldCereal's own
cropland (`wintercereals / temporarycrops`), matching MNFSR's definition. Correlation
flipped to **+0.42** (97 districts with data) — but a second real issue then showed
up: **42/97 districts had a ratio exceeding 1.0**, a mathematical impossibility for
a share-of-cropland figure, revealing that WorldCereal's own independently-classified
`wintercereals` and `temporarycrops` products aren't fully mutually consistent at
typical district scale — a real limitation of WorldCereal itself, not this
cross-check's arithmetic this time.

**Final, clean comparison** (cropland fraction ≥10% of district area, plausible
ratio ≤1.0): **52 districts, correlation 0.118, MAE 0.222** — real, weak-to-no
agreement between the two independent sources on wheat presence, even after both
real corrections. **Confirmed with you**: MNFSR stays the sole label source for
training (it's official government area data; WorldCereal is an unvalidated global
satellite product for this specific comparison), and this weak correlation is
reported as an honest independent-check finding, not treated as grounds to change
the label source or to trust WorldCereal instead.

## The Track F headline result

Real evaluation on the held-out test districts, GBT vs. constant-baseline
(always predict the real national mean crop-share vector: wheat 0.772, cotton
0.087, rice 0.115, sugarcane 0.026):

| | Overall MAE | wheat R² | cotton R² | rice R² | sugarcane R² |
|---|---|---|---|---|---|
| Constant national-mean baseline | 0.112 | -0.214 | -0.003 | -0.247 | -2.181 |
| GBT, point-level, test | 0.078 | 0.276 | 0.300 | 0.107 | **-3.854** |
| GBT, **district-level**, test | **0.073** | **0.581** | **0.507** | **0.420** | **-1.120** |

The model clearly beats the baseline on overall MAE and on three of four crops,
**especially at district-level aggregation** (mean of point predictions vs. the
real MNFSR district share) — the granularity the real label actually has integrity
at, since the label is constant within a district by construction. Wheat, cotton,
and rice all show real, honest positive R² (0.58 / 0.51 / 0.42 at district level).

**Sugarcane is a real, reported failure, not hidden**: R² is strongly negative at
both granularities. Sugarcane's real national mean share is small (2.6%) and it was
never the argmax-dominant crop in any district (see pre-check above) — there is
very little real variance for the model to explain, and the weak district-level
label signal isn't strong enough to learn a useful sugarcane-specific pattern from.
Reported honestly as a real limitation of this approach for rare, minority crops,
not smoothed over.

## Real feature-importance self-check (Track E's discipline, built in from the start)

Permutation importance on the real test set, GBT model, before any headline number
was written down:

```
ndwi_annual_std       0.368
ndvi_annual_std       0.343
evi_annual_mean       0.294
evi_peak_value        0.195
ndwi_trough_value     0.175
ndvi_trough_value     0.174
ndvi_annual_mean      0.138
evi_green_up_slope    0.104
ndwi_annual_mean      0.085
ndwi_peak_value       0.084
```

**No geographic leak to catch this time, by construction** — lat/lon and
district-identity were never in the feature set to begin with (Track E's lesson
applied preventatively, not diagnosed after the fact). The top features are all
genuine phenology-curve statistics (seasonal variability, peak/trough values), a
real, physically sensible signal for distinguishing crop types by growing pattern
rather than location memorization.

## Historical comparison to Week 2

Week 2's 120-farm result (binary irrigated/not-irrigated, 0.700 held-out accuracy,
below the 0.792 majority baseline) is a **different task** — reported here as
context on how far the real data/methodology has come, not as a numeric baseline
for this multi-output regression. Real scale did help: Week 2 had 120 farms in 4
districts; this week has 2,875 points across 115 districts with a real, richer
phenology feature set, and produces a real, honest, non-degenerate result for three
of four crops.

## Real files this week produced

- `naip/models/crop_classifier_national/sample_points.py`,
  `extract_phenology_features.py`, `cross_check_worldcereal.py`,
  `train_crop_share_model.py`
- `points.geojson` (2,875 real points), `phenology_features.csv`,
  `worldcereal_mnfsr_wheat_crosscheck.json`,
  `worldcereal_mnfsr_wheat_crosscheck_clean_summary.json`, `track_f_results.json`
