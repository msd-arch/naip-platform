# Week 2 status report — Crop Intelligence (6.3) + Water Accounting v1 (6.4)

## What's actually working end-to-end

- **Google Earth Engine credential path is live.** Was a hard blocker at the
  start of the week (no CDSE or GEE credentials existed on this machine,
  confirmed by checking, not assumed). `earthengine-api`/`geemap` installed,
  OAuth completed, GCP project `printtheory` registered for Earth Engine.
  Verified with a real server round-trip and a real Sentinel-2 query before
  building anything on top of it.
- **Real Sentinel-2 NDVI time series, 120/120 farms, 0 gaps.** Cloud-masked
  (SCL-based) monthly median composites, Apr–Sep 2025 (6 months), Sentinel-2
  SR Harmonized, per-farm mean via `reduceRegions`. Every farm got a valid
  cloud-free NDVI value every month — no padding needed, real coverage was
  complete. `naip/models/crop_classifier/features_labels.csv`.
- **Real WorldCereal labels, 120/120 farms, 0 gaps.** ESA WorldCereal 2021
  v100 `temporarycrops` + `irrigation` products, per-farm mode.
- **Irrigation classifier trained and validated on real held-out data.**
  scikit-learn (LogisticRegression + RandomForest), stratified 75/25 split
  plus 5-fold CV. `naip/models/crop_classifier/train_classifier.py` +
  `report.json`.
- **Water-stress index computed for one real, named canal distributary.**
  "Muridke Distributary" (OSM, 15 way segments, 69.4km stitched length),
  sampled every 3km (24 points), real MODIS MOD16A2 ET/PET summed over the
  same Apr–Oct 2025 window as 6.3. 22/24 segments got a valid stress index.
  `naip/models/water_stress/water_stress.json` + `.geojson`.

## What's stubbed / scoped down / not what the architecture doc describes

- **The crop classifier is NOT a wheat/cotton/rice/sugarcane classifier.**
  Checked ESA WorldCereal's real product catalog against the real GEE
  catalog before writing any code (not assumed): it has no cotton, rice, or
  sugarcane class for Pakistan — only `temporarycrops` (binary cropland),
  `irrigation` (binary), `maize`, `wintercereals`, `springcereals`. No other
  public global crop-type dataset covers Pakistan at usable resolution
  either. Per your call, this narrowed to two binary tasks; the
  **cropland task was then dropped entirely** — all 120 farms are
  WorldCereal-labeled cropland (zero variance, nothing to validate, a
  reported accuracy there would be a meaningless artifact). What actually
  got trained and validated: **irrigated vs. not-irrigated**, from real
  NDVI phenology features.
- **Canal-command geometry is an approximation, not an official boundary.**
  Checked HDX, geoBoundaries, and the GEE catalog — no WAPDA/PID
  canal-command polygon dataset exists anywhere accessible for Pakistan
  (same category of gap as Week 1's district boundaries, confirmed rather
  than assumed). Per your call, used a real OSM canal centerline buffered by
  an **assumed** 500m half-width — real canal location, invented corridor
  width. Every output row carries this caveat.
- **Head/tail direction is a geometric guess, not verified flow direction.**
  Derived from which end of the stitched OSM line has no chaining neighbor.
  This has not been cross-checked against any real hydraulic/offtake record.
- **No IRSA/PID allocation data used or compared, by design.** Per
  architecture.md §5, that partnership doesn't exist. This is
  satellite-ET-only demo mode — the water-stress index reflects an
  evaporative deficit signal (1 − ET/PET), not an allocation-vs-entitlement
  comparison. Labeled as such in the output JSON itself, not just this report.

## Real validation numbers — stated plainly, not smoothed over

### 6.3 — irrigation classifier

| | value |
|---|---|
| n farms total | 120 |
| n farms used (0 dropped — full NDVI coverage) | 120 |
| class balance | 25 irrigated / 95 not-irrigated |
| majority-class baseline accuracy | **0.792** |
| LogisticRegression — held-out test accuracy | **0.700** |
| LogisticRegression — 5-fold CV accuracy | 0.767 ± 0.062 |
| RandomForest — held-out test accuracy | **0.700** |
| RandomForest — 5-fold CV accuracy | 0.800 ± 0.122 |
| held-out recall on irrigated class (both models) | 0.667 |
| held-out precision on irrigated class (both models) | 0.364 |

**Honest read**: held-out accuracy (0.700) is *below* the naive majority-class
baseline (0.792) for both models — a raw-accuracy comparison says the
classifier is not clearly better than always guessing "not irrigated." What
it does do that the baseline can't: catch 2/3 of actually-irrigated farms
(0.667 recall) at the cost of some false positives (0.364 precision) — a
real, if modest, discrimination signal from 6 months of NDVI shape alone,
not nothing, but not a result to lead with either. 5-fold CV means sit above
baseline (0.767–0.800) but with high variance (±0.062 to ±0.122) at n=120 —
too small a sample to trust the CV number over the single held-out split.
**This is not a wheat/cotton/rice/sugarcane accuracy number and should never
be reported as one** — see the scope note above.

### 6.4 — canal water-stress index (Muridke Distributary)

| | value |
|---|---|
| canal length (OSM-derived) | 69.4 km |
| segments sampled | 24 (every 3km) |
| segments with valid ET/PET | 22/24 |
| mean stress index (1 − ET/PET) | 0.863 (std 0.028) |
| head segment (0km) stress index | 0.868 |
| tail segment (69km) stress index | 0.914 |
| distance-vs-stress correlation | 0.569 |

**Honest read**: there's a real, moderate head-to-tail gradient — the tail
segment shows more evaporative deficit than the head, consistent with the
tail-end-deprivation pattern irrigation-equity literature expects, and the
0.569 correlation across all 22 valid segments backs it up as more than a
two-point coincidence. But: (a) head/tail direction is an unverified
geometric guess, not confirmed flow direction — if it's backwards, the
finding reverses; (b) the 500m-buffer corridor at MODIS's 500m native pixel
size means each sample cell is only 1–2 real MODIS pixels, mixing canal +
cropland + bare land + built-up area — the ET signal is diluted by
non-agricultural land the same way Week 1's drought NDVI was diluted by the
27km MSG grid, just at a smaller scale. This is a real signal worth
investigating further, not yet a validated equity index.

## What's blocked

- Real wheat/cotton/rice/sugarcane crop-type classification — blocked on
  ground-truth availability, not code. Would need either farmer-reported
  labels for the 120 farms or a Pakistan-specific crop-type product neither
  WorldCereal nor any other public dataset provides.
- Official canal-command boundaries — blocked on data availability, same as
  Week 1's district-boundary gap. No WAPDA/PID source found anywhere
  accessible.
- Verified canal flow direction — would need either a DEM-based hydraulic
  check or an actual PID/WAPDA offtake record, neither pulled this week.
- IRSA/PID allocation cross-check for 6.4 — explicitly out of MVP scope per
  architecture.md §5 (partnership dependency), not attempted.

## Files produced this week

- `naip/data/seed/farms_layyahMuridke_Kharif2025.geojson` — copied into repo
  structure (was previously only referenced from Downloads).
- `naip/models/crop_classifier/extract_features.py`, `train_classifier.py`,
  `features_labels.csv`, `report.json`.
- `naip/models/water_stress/canal_water_stress.py`,
  `muridke_distributary_raw.json`, `water_stress.json`,
  `water_stress_segments.geojson`.
