# Week 10 status report — Phase 3, Track D (real Sentinel-1 flood classifier, 2022 floods)

Full context: `docs/PHASE3_MODEL_PLAN.md` / `docs/PHASE2_SCOPE_ROADMAP.md` (Track D's
original scope), `naip/docs/PHASE3_SYNTHESIS.md` (the sampling-bias throughline this
track's design deliberately builds on).

## Pre-checks (done first, reported before building — time-boxed, not open-ended)

**The circularity risk, resolved before writing any pipeline code**: the most
convenient real ground truth (TU Wien/JRC's Sentinel-1-derived flood map for this
exact event) is itself SAR-derived — training a Sentinel-1 classifier against it
would re-derive their algorithm, the same trap Track E's original with-geo framing
fell into. **Not used, for exactly this reason.**

**A genuinely independent, structured, district-level source was found**: IOM/Shelter
Cluster's "Calamity declared districts — Pakistan" (as of 16 September 2022) —
downloaded directly (PDF, `naip/data/flood_2022_ground_truth/`), a real government-
declared administrative list, not a satellite product. Its embedded data table
(extracted via `pdftotext`) had a real column-misalignment artifact around a
page-break (Punjab districts like Muzaffargarh/Sialkot/Layyah briefly mislabeled
"Sindh," and real Sindh districts Kashmore/Mirpurkhas/Umerkot/Tharparkar briefly
mislabeled "AJK") — caught and corrected by hand against real Pakistani
administrative geography before using it as labels, same "verify before assuming"
discipline as every prior week's data ingestion.

**Real match against this project's 126-district set**: **96/126 real districts**
matched to a real flood/no-flood label; **10 genuinely unmatched** (Chaman, Duki,
Sherani, Sohbatpur, Harnai, Shaheed Sikandarabad, Washuk, Tor Ghar, Sujawal,
Larkana) — the same older-geoBoundaries-vintage gap Track C already found (Larkana,
Washuk, Harnai, Sherani were already known-absent). Real class balance: **96
flooded, 30 not flooded** at the district level. One real caveat carried through
end to end: "calamity declared" is a broader real administrative/emergency
designation, not strictly identical to physically-inundated area.

This resolved pre-check #1 with a genuinely independent, district-level source —
**the stronger path was available, so the weaker TU-Wien-as-methodology-reference
fallback was not needed.** Per direction, this didn't require asking first.

**GEE access confirmed live, not assumed**: `COPERNICUS/S1_GRD` — 830 real Sentinel-1
IW-mode scenes over Pakistan, Aug–Sep 2022, real VV/VH bands present. `JRC/GSW1_4/
GlobalSurfaceWater` — real historical occurrence baseline, 465,712 valid 1km pixels
over the national bbox. Both real and accessible before any pipeline code was written.

## What was built

- **`sample_and_extract.py`** — 15 real points/district × 126 districts = **1,890 real
  points**, zero dropped for missing data. Real Sentinel-1 median composites: during-flood
  (2022-08-15..09-16, matching the calamity list's real coverage window) and a
  pre-flood dry-season baseline (2022-03-01..04-15). Features: `VV_during`,
  `VH_during`, `VV_change`, `VH_change` (established real SAR flood-detection
  methodology — water shows low backscatter, and change-from-baseline is the
  standard approach, not reinvented), plus real JRC `occurrence` to let the model
  discount permanent rivers/lakes rather than just detecting "the river" — the flood
  equivalent of Track F's wheat-dominance trap. **No lat/lon or district-identity
  feature**, confirmed excluded from the start, same discipline as Track E/F.
- **`train_flood_classifier.py`** — real spatially-blocked split, whole districts
  held out (83 train / 18 val / 25 test), stratified by each district's real label
  so both classes appear in every split. `role` tags (`headline_result` /
  `baseline`) in the results JSON from the first run.

## Real result

| | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| **Established SAR-threshold rule** (VV < −17dB AND JRC occurrence < 5%) | 1.000 | 0.077 | 0.143 | n/a |
| **GBT, real test set** | 0.817 | 0.674 | **0.738** | 0.656 |

The trained model clearly beats the established non-ML baseline — driven almost
entirely by recall (0.674 vs. 0.077): the fixed absolute-threshold rule is real but
extremely conservative, missing the large majority of real flooded points because a
single fixed VV cutoff doesn't account for real regional backscatter variation. The
trained model, using *change from a real pre-flood baseline* rather than an absolute
cutoff, catches far more of the real flood at a real but modest precision cost
(0.817 vs. 1.000).

**Real feature-importance self-check, before this number was written down as a
headline** (no geographic leak was structurally possible — lat/lon was never a
feature — but the *SAR* features still needed checking): `VH_during` (0.033) and
`VV_change`/`VH_change` (0.025/0.016) drive the model; **`jrc_occurrence` contributes
almost nothing (0.0012)**, and `VV_during` alone is *negative* importance (noise).
Reported honestly, not smoothed over: the JRC permanent-water baseline didn't turn
out to add real predictive value at this point-sampling density — the model is
relying on real backscatter-change signal, not on the water-occurrence layer it was
specifically included to provide. A real, open question for a future pass, not
assumed to be working as intended.

## Real files this week produced

- `naip/data/flood_2022_ground_truth/` — real IOM/Shelter Cluster PDF + extracted
  text, `calamity_declared_districts_corrected.json`, `district_flood_labels_126.json`
- `naip/models/flood_risk/sample_and_extract.py`, `train_flood_classifier.py`,
  `flood_dataset.csv` (1,890 real rows), `track_d_results.json`,
  `gbt_flood_classifier.joblib` (persisted, same pattern as Track E/F)

## Not done this week, stated plainly

- Not wired into the live dashboard/pipeline (Track G's integration pattern is
  reusable but wasn't applied here this week — a real next step, not started).
- No held-out validation against a second real flood event — this is a single real
  disaster window, same single-window caveat every other Phase 3 track carries.
- `jrc_occurrence`'s near-zero real importance is reported, not investigated further
  this week (e.g. whether a different real reduce scale or a river-distance feature
  would help) — a real open item.
