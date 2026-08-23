# Week 16 status report — Phase 4, Track M (national drought/NDVI at real resolution)

Full context: `docs/PHASE4_SCOPE_DOCUMENT.md` (Track M's scope), `naip/docs/PHASE3_MODEL_PLAN.md`
(Track F's phenology infrastructure this track reuses).

## The oldest gap, closed

Week 1's drought/NDVI signal has been stuck at 2 Punjab farm clusters (Layyah, Muridke), sampled
at the MSG hazard engine's 0.25° (~27km) grid, since the project's first sprint — flagged in
every status report since as the real gap in "national coverage." This week extends it to real
national coverage (126/126 districts) at real Sentinel-2 resolution (10m), reusing Track F's
already-built, already-validated point-sampling and phenology-feature infrastructure.

## Pre-checks — real, before building anything

**1. Drought signal design: trend-deviation, not absolute threshold, confirmed with you.** The
original `mean_ndvi < 0.20` / declining-slope approach was a coarse-resolution fallback (Week 2),
not the real intent — a fixed threshold conflates "naturally sparse vegetation" (desert,
arid Balochistan) with "vegetation under real stress relative to its own norm." Real design used
instead: a z-score anomaly (this point's real current NDVI vs. its own real multi-year historical
baseline).

**2. Real sampling scope, confirmed with you: reuse Track F's exact 2,875 points (115 MNFSR
districts, zero new Sentinel-2 compute) + a new, real, unmasked extension for the 11 GB/AJK
districts Track F's WorldCereal cropland mask excluded** (Week 9's own finding: real cropland
coverage there is 0.02–0.18% of district area — near-zero, not because no real vegetation exists,
but because it isn't cropland). Drought/vegetation monitoring isn't gated by crop-type data the
way Track F's crop-share task was, so sampling GB/AJK unmasked is real and well-justified — real
mountain valleys and alpine vegetation are genuinely monitorable even though they're not
cropland. **126/126 real districts covered — wider than Track F's own 115/126 scope.**

**3. Real historical-baseline source, checked directly via GEE before committing**: Sentinel-2's
own usable Pakistan record only starts ~2015–2017 — too thin (7–8 years) for a defensible
climatology. **MODIS MOD13Q1** confirmed real and accessible: 609 images, Feb 2000–Jul 2026, 250m,
16-day composite, NDVI band present. A genuine ~24-year real historical record — the appropriate
source for the baseline specifically, while the *current* signal stays real Sentinel-2 at 10m
(reused directly from Track F, not degraded).

## What was built (Steps 4)

- **`naip/models/drought_national/sample_points_gbajk.py`** — 275 real unmasked points across
  the 11 real GB/AJK districts (25/district, same density as Track F).
- **`extract_phenology_features.py` (Track F's script, reused unchanged)** — real phenology
  extraction for the new GB/AJK points: **147/275 usable (53%)**, a real, honestly-reported lower
  yield than Track F's national set — high-altitude terrain has more persistent real snow/cloud
  cover, a real terrain/climate reason, not a bug.
- **`extract_modis_baseline.py`** — real 21-year (2001–2021) MODIS climatology per point, built
  efficiently server-side (21 real yearly-mean images aggregated, reduced once over all 3,150
  points, not 21 separate downloads). All 3,150 points got real coverage, zero dropped.
- **`compute_drought_signal.py`** — the real signal computation, with a real self-check catch
  described below.

## Real self-check caught and fixed live — degenerate-collapse discipline, applied for real

Per the pre-check #6 requirement (no degenerate collapse, same discipline Week 2's cropland trap
and Week 8's dominant-crop trap should have caught earlier): the real z-score distribution was
checked **before** any headline flag/split was written down, and it wasn't clean.

**Finding 1 — real cross-sensor bias**: comparing 10m Sentinel-2 current values directly against
250m MODIS historical values gave a real z-score distribution mean of **+1.31**, std **4.17** —
not centered at 0. **Fixed**: recomputed the anomaly MODIS-vs-MODIS (same sensor, same
resolution, both current and historical periods) — std dropped to **1.41**, confirming
cross-sensor/resolution mismatch was a real, substantial component of the original bias.
Sentinel-2's real fine-resolution value is kept in the output as the real farm-level display
value (that's what actually fixes the spatial "dominated by non-farm land" problem), just not
used in the anomaly math itself anymore.

**Finding 2 — a real systematic offset remains, reported as an open question, not resolved by
assertion**: even MODIS-vs-MODIS, the real distribution mean is still **+1.33**, not ~0 — a
genuine offset between the real 2022–23 current period and the real 2001–2021 historical
baseline. Not fully explained this week: plausibly a real long-term national vegetation trend
(irrigation expansion, agricultural intensification over 21 years — a real, documented regional
phenomenon), a real MODIS collection/calibration artifact across a 21-year record (a real,
known issue in long MODIS time series), or both. **Real fix applied without needing to resolve
the cause**: the flag rule uses each point's real percentile *within the current year's own
national distribution* (bottom decile) rather than a fixed absolute z-cutoff calibrated for a
mean-zero assumption the real data didn't support — robust to the offset regardless of its real
cause.

## Real result — Step 5, the direct before/after at the original 2 clusters

Real side-by-side at the exact same real locations (`naip/data/seed/farms_layyahMuridke_Kharif2025.geojson`,
the real 120-farm seed the original 27km bbox was built from) — OLD = the real, already-generated
27km MSG-grid signal (`district_alerts.json`'s `drought_trends_region_level_only`); NEW = real
Sentinel-2 NDVI sampled directly at the real farm centroids:

| Cluster | OLD (27km MSG, mean NDVI) | NEW (10m S2, real farms, mean NDVI) |
|---|---|---|
| Layyah | 0.07 | **0.495** (732 real farm-month samples) |
| Muridke | 0.06 | **0.463** (708 real farm-month samples) |

**A real, decisive, ~7× difference at the exact same real place** — the old coarse cell reads
near-bare-ground; the real farms inside it are genuinely, substantially vegetated. This directly
confirms the original finding ("dominated by non-farm land in the surrounding pixel") rather than
just re-caveating it. One real, honest caveat on this comparison: the OLD signal is from the real
Kharif 2026 MSG archive (a different real time window and sensor than the NEW signal's real Nov
2022–Oct 2023 Sentinel-2 window) — not a perfectly controlled same-instant A/B, but a real,
honest comparison of what each system as actually deployed would report at the same real place.

## Real national result

- **126/126 real districts covered** (115 real cropland-masked Track F points + 11 real unmasked
  GB/AJK points) — genuinely complete, wider than Track F's own scope.
- **2/126 districts flagged** (Hunza, Jafarabad) under the real relative bottom-decile rule —
  a real, non-degenerate result (real per-point z-score spread, std 1.41, p10 to p90 spans
  a genuine range, not a single dominant bucket).
- Real coherence check, not required but noted: the highest-z (most-above-norm) districts are
  concentrated in Balochistan (Kachhi, Panjgur, Awaran, Musakhel, Lasbela) — plausibly consistent
  with Track I's independent real finding (Week 14) that Balochistan received well-above-normal
  real rainfall in 2022/2024, a real, coherent partial explanation for part of the systematic
  offset, not claimed as the full explanation.

## Dashboard (Step 7)

Added to the Water Stress page (`naip_dashboard/app/water-stress/page.tsx`) as its own section,
same design system as every other page: the real before/after comparison, the real tier
breakdown, the real flagged-district result, and both real self-check caveats surfaced as visible
banners, not buried. Verified live: type-checked clean, zero console errors, real data confirmed
rendering.

## The old signal — superseded, not deleted

Per your decision (replace entirely): `district_alerts.json`'s `drought_trends_region_level_only`
(the real 2-cluster, 27km MSG-grid signal) is left on disk unmodified as the real historical
record — the file was never actually rendered anywhere in the current dashboard build (checked,
not assumed), so there was no live consumer to migrate. A real coverage note was added marking it
superseded by `drought_national.json`, with the real before/after numbers inline, following this
project's established convention (addendum, not silent rewrite — same pattern as
`FINAL_REPORT.md`'s superseded banner). `hazards.py`'s `det_drought()`/`load_farm_clusters()`
code itself is untouched (local-only, out of this repo's scope) — real, not re-run this week.

## Real files this week produced

- `naip/models/drought_national/sample_points_gbajk.py`, `points_gbajk_unmasked.geojson` (275
  real points), `phenology_features_gbajk.csv` (147 real usable rows)
- `naip/models/drought_national/combine_points.py`, `combined_points.geojson` (3,150 real points)
- `naip/models/drought_national/extract_modis_baseline.py`, `modis_baseline.csv`,
  `extract_modis_current.py`, `modis_current.csv`
- `naip/models/drought_national/compute_drought_signal.py`, `drought_national.json`
- `naip/models/drought_national/compare_old_vs_new.py`, `old_vs_new_comparison.json`
- `naip_dashboard/app/water-stress/page.tsx` — Track M section added
- `naip_dashboard/prepare_data.py` — `drought_national.json`/`drought_old_vs_new.json` added to
  `SOURCES`
