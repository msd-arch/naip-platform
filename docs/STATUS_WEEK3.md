# Week 3 status report — Fusion (6.5) + Locust (6.6) + Residue Burning (6.7)

## Pre-checks (done before any code, per this week's kickoff)

- **Fusion methodology (6.5) is real, not a doc-only claim.** `Downloads/ml_pipeline/`
  (`train.py`, `nwp2msg_common.py`, `evaluate.py`, `predict.py`, `build_ml_dataset.py`)
  has real, working code for all three named techniques: patch-sizing
  (`sample_patch_origins`, `--patch-size`), masked-loss (`masked_mse`, real NaN +
  per-channel masking), curriculum-training (`--init-from`, loads a prior checkpoint's
  encoder weights). A real trained checkpoint exists (`checkpoints/gfs_msg_ir108.pt`,
  small U-Net, GFS→MSG IR10.8). Two things worth knowing: (1) this code's own docstring
  says it was reconstructed after a prior session lost the originals from an ephemeral
  scratchpad — real and runnable today, not an unbroken original; (2) the real eval
  report (`eval_report_gfs_msg_ir108.json`, trained on 12 samples: 10 train/2 val) shows
  the model does **not** beat a simple linear-regression baseline on RMSE at any of 3
  smoothing scales (e.g. 19.28 vs 17.98 K at scale 1). `train.py` also has a real,
  structural safeguard: it refuses to train on the MTG dataset
  (`usable_for_training: false`, 2 samples) without `--allow-tiny-dataset`, and prints a
  "not evidence of learned skill" warning if overridden. `forecast_cloud.py` is a
  separate, real, deterministic (non-ML) WRF→synthetic-IR physical renderer — not part
  of this ML pipeline, not to be confused with it.
- **Crop-stage framing confirmed unbuildable literally**, as expected from Week 2 (no
  crop-type classification, no populated `crop_calendar`). Per your direction, built a
  **regional (province-average, not per-farm) crop calendar** instead of the
  irrigated/not shortcut — see below.
- **Residue-burning fire detector: zero code existed anywhere**, confirmed by grep
  across `hazards.py`, `export_hazard_grids.py`, `derived_lib.py`. What's real is
  channel-selection knowledge only: `product_info.json` correctly documents IR_039 (and
  its BT-difference derivatives) as fire-hot-spot-flagging channels. Built the detector
  from scratch this week (see below). **Season mismatch confirmed real**: the 71-file
  archive (2026-06-22..07-20) is Kharif sowing season; real Punjab residue burning is
  Oct-Nov, post-rice-harvest. This week's run cannot demonstrate a true positive —
  stated in the code's own output, not just this report.

## What's actually working end-to-end

### 6.7 — Crop-Residue Burning Detection

New `det_residue_burning()` in `hazards.py`, reusing the real `night_fog_diff`
(IR3.9-IR10.8) field `det_fog` already samples — no new grid export needed. **First
version was wrong and I caught it before shipping it**: an absolute threshold
(nfd ≥ 6.0K) fired on 95/243 daytime clear-sky city-observations in the pilot run —
obviously not 95 simultaneous fires, just ordinary daytime solar heating of dry June
soil. Real fire algorithms (MODIS/VIIRS) test a candidate pixel against its *local*
background, not a fixed cutoff — rebuilt it that way: anomaly = point value − mean
value over a ±3° box around the same point at the same timestamp. Threshold (10.0K)
calibrated against this archive's own real off-season clear-sky anomaly distribution
(243 samples: mean −2.7K, std 4.9K, p99 9.6K) — grounded in real data, but still **not
validated against actual fire ground truth** (none exists in this off-season archive).

- Pilot (12 cities): 2 triggers (Hyderabad, Peshawar — both >13K anomalies, genuine
  statistical outliers).
- National (126 districts): 46 triggers, concentrated somewhat in Balochistan
  (Kalat, Khuzdar, Nushki, Panjgur, Gwadar, Dera Bugti, Kohlu, Qilla Saifullah) — arid,
  sparsely-vegetated terrain where the local background itself is noisier, so some of
  these are plausibly bare-rock/sand heating variance rather than fire. Not resolved
  this week — flagged, not hidden.
- Resolution caveat, real and structural: 0.25° (~27km) grid. A single field's fire is
  a few hundred metres across — invisible at this resolution unless burning is
  widespread and simultaneous, which is the actual real-world smog-corridor pattern
  the module targets, but means this can never localize to one farm's fire.

### 6.6 — Desert Locust Breeding-Risk Monitor

Real SMAP L4 (SPL4SMGP v008) soil-moisture-anomaly + real Sentinel-2 NDVI green-up,
standard FAO DLIS-style logic (wet soil for egg-laying + green vegetation for hopper
survival), over the most recent real 30-day window (2026-07-19..08-18 — this uses
current real-time data, independent of the MSG archive).

**Boundary check, same discipline as districts/canals in prior weeks**: Tharparkar and
Kharan are real Pakistani districts, already real polygons in Week 1's
`pk_districts.geojson` — used directly. **Cholistan has zero OSM representation**
(checked: `name~Cholistan` across relation/way/node, zero results) and no official
boundary anywhere. Used the real-geometry union of the 3 Punjab districts
(Bahawalpur, Bahawalnagar, Rahim Yar Khan) known to contain the Cholistan Desert —
labeled explicitly as substantially overstating the true desert extent.

Real result: no breeding risk currently flagged in any of the 3 regions. Soil-moisture
anomaly is near-neutral-to-negative everywhere (Tharparkar +0.0007, Kharan −0.017,
Cholistan −0.002 m³/m³ — none clear the +0.02 favorable threshold), even though
vegetation green-up **is** real and detected in Tharparkar (+0.047) and Cholistan
(+0.049) — a genuinely partial, non-trivial result (one axis triggers, the other
doesn't), not a uniform "nothing happening" output.

### 6.5 — Fusion / crop-stage exposure-risk model

Scoped per your direction: real regional crop calendar (wheat/cotton/rice/sugarcane
sowing-harvest windows, source: AIS Pakistan, provided directly — could not
independently re-fetch this session, see "Blocked" below) × real `hazards.py` district
detections. **Two-tier honesty on this module's own inputs**:
1. Sowing/harvest windows: real, cited (AIS Pakistan).
2. Stage sub-splits (establishment/vegetative/flowering/maturation) within those
   windows: **not separately sourced** — a proportional interpolation using generic
   crop-growth-stage agronomy. Flagged in the code's own docstring as the
   least-certain part of this module.

`exposure_score = hazard_confidence × stage_vulnerability_weight` (vulnerability
weights are illustrative agronomic knowledge, not locally fitted). Computed for **all
four crops at every district** as a "if this district grew crop X" hypothetical — NAIP
has no real per-district crop-mix data (same gap as Week 2's missing crop-type
classification), so this does not claim to know what any district actually grows.

Real result from the national district data: 141,120 (district, date, hazard, crop)
rows, 1,338 with nonzero exposure score. Top exposure events are all frost/hail hitting
cotton at "flowering" stage in late June/July — but the top 5 are Zhob, Chakwal, Upper
Dir, Lower Dir, and **Skardu** — mountainous/high-altitude districts that would never
actually grow cotton in reality. **This is an honest, important limitation, not a bug
to silently patch**: the model doesn't know which crops are agronomically plausible per
district, only that *if* a district grew crop X, hazard Y at date Z would matter this
much. Reading any single number here as "this district's real exposure" would be a
mistake — same discipline as not reading WorldCereal's cropland/irrigation labels as a
real crop-type classifier in Week 2.

This is **not** the real `ml_pipeline/` U-Net retrained — that pipeline predicts MSG
imagery from GFS/WRF fields, a different task from a risk score. Its real, separately-
confirmed status is reported above rather than silently ignored.

## Real baseline numbers, national vs. pilot, including the new detector

| | Pilot (12 cities) | National (126 districts) |
|---|---|---|
| Alert records | 3,384 | 35,532 |
| Triggered | 40 | 448 |
| residue_burning triggers | 2 | 46 |
| Runtime | ~17s | **6m54s** (up from ~3m26s pre-Week-3 — the new detector's local-background `bbox_mean` call roughly doubled per-location compute cost) |

## What's blocked

- Could not independently re-fetch the AIS Pakistan crop-calendar source this session —
  tried the Punjab Agriculture Dept PDF (DNS resolution failure) and the FAO-hosted URL
  (HTTP 521, origin down) you provided; used the numbers you pasted directly instead,
  cited to AIS Pakistan.
- Fusion model's per-district crop-mix is unknown — would need either real agricultural
  census data or the (still-nonexistent) per-farm crop-type classification from Week 2.
- Residue-burning detector has no fire ground truth to validate against this week
  (wrong season in the only real archive on disk) — cannot confirm true-positive rate,
  only confirmed it doesn't flood on off-season clear data after the contextual-anomaly
  fix.
- Locust thresholds (SM anomaly ≥0.02, NDVI delta ≥0.03) are standard qualitative FAO
  DLIS bands, not locally fitted against real locust survey records.

## Files produced this week

- `Downloads/hazards_scripts/hazards.py` — `det_residue_burning()` added (real engine,
  outside repo per convention), regenerated both pilot and district `hazards.json`
  output.
- `msg_dashboard/app/components/HazardCard.tsx` — added label/icon for the new
  `residue_burning` hazard type (had a safe fallback already, added proper entries).
- `naip/models/fusion/crop_calendar.py`, `exposure_risk.py`, `exposure_risk.json`,
  `exposure_risk_top.csv`.
- `naip/models/locust_risk/locust_breeding_risk.py`, `locust_risk.json`.
- `naip/backend/alerts/hazards_district_national.json`, `district_alerts.json/.csv` —
  regenerated with the new detector.
