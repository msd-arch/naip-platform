# Week 1 status report — Data fabric + Nowcasting national extension

## Addendum: clear-sky gate fix (post-report)

Applied the `cloud_proxy < 0.3` clear-sky gate (same one `det_frost` already used)
to `det_heat_wave` and `det_cold_wave` — cloud-contaminated frames (IR10.8 reading
cloud-top brightness temp, not ground temp) are now excluded from the multi-day
mean before either detector evaluates its threshold. No other threshold in either
detector changed.

Re-ran `hazards.py --locations districts` against the same real archive
(71 timesteps, 126 districts) and regenerated the district feed:

| hazard | before | after | delta |
|---|---|---|---|
| cold_wave | 30 | 2 | **-28** |
| heat_wave | 0 | 0 | 0 |
| fog | 213 | 213 | 0 |
| frost | 58 | 58 | 0 |
| uv_index | 124 | 124 | 0 |
| hail | 3 | 3 | 0 |
| thunderstorm | 2 | 2 | 0 |
| **total triggered** | **430** | **402** | **-28** |
| **trigger rate** | **1.39%** | **1.30%** | -0.09pp |

The fix was isolated to `cold_wave` — every other hazard's count is byte-identical
before/after, confirming no unintended side effects.

**Spot-check (the two districts that motivated the fix):**
- Abbottabad, 2026-06-22 night: was flagged `cold_wave=True` at mean skin temp
  **-14.2°C**; after the gate, cloud-contaminated frames are excluded and the
  clear-sky mean is **11.4°C** — not flagged, and the corrected number is
  physically sane for a June night in Abbottabad.
- Astore, 2026-06-22 night: was **-10.1°C** flagged; after the gate, clear-sky
  mean is **3.2°C** — not flagged, also sane.

**The 2 remaining cold_wave triggers are Shigar and Chitral** — both high-altitude
northern districts, mean clear-sky night temps of 1.2°C and 1.6°C respectively.
These are plausible near-freezing June nights at elevation, not contamination
artifacts — the gate did not over-suppress.

**Updated national baseline for Week 2 comparisons** (supersedes the table
below, which still has the pre-fix `cold_wave` numbers baked into the pilot
column — see note):

| | Pilot (12 cities) | National (126 districts) |
|---|---|---|
| Alert records | 2,952 | 30,996 |
| Triggered | 42 (unfixed — see note) | **402 (post-fix)** |
| Trigger rate | 1.42% (unfixed) | **1.30% (post-fix)** |

**Open item, not resolved here:** this fix only reran district mode, per the
explicit scope of the request. The live dashboard's `public/hazards.json`
(12-city pilot, feeding the deployed frontend) still has the pre-fix
`cold_wave` logic baked in (4 of its 42 triggered alerts) — same bug, not yet
re-run. Flagging rather than silently fixing it, since touching the pilot's
production output wasn't in scope for this task.

## What's actually working end-to-end

- **Hazard engine, national sampling.** `Downloads/hazards_scripts/hazards.py` (the
  real, already-existing engine — 11 detector functions, unchanged) now supports
  `--locations districts` alongside the original `--locations cities` (default,
  unchanged, still the 12-city pilot). Ran against the full real MSG archive
  (71 timesteps, 2026-06-22..07-20) at 126 district centroids:
  **30,996 alerts, 430 triggered (1.39%)**, in ~3m26s.
  Output: `naip/backend/alerts/hazards_district_national.json`.
- **District-level alert feed.** `naip/backend/alerts/district_aggregate.py`
  collapses that per-timestep output into a district-day-hazard summary —
  **14,364 rows**, `district_alerts.json` + `district_alerts.csv`. This is the
  pluggable feed for a future alert channel (Week 4 builds delivery, not this).
- **Farm Registry schema.** `naip/backend/farm_registry/schema.sql` — `farmers`,
  `farms` (PostGIS `Polygon` boundary + GIST index), `crop_calendar`, with
  `plra_owner_ref`/`plra_khasra_ref`/`kissan_card_ref` as link-out-only fields
  (no PLRA/Kissan Card data duplicated). `load_seed_farms.py` loads the real
  120-farm Layyah/Muridke GeoJSON, leaving farmer/CNIC/crop fields NULL.
- **District boundaries.** `naip/data/seed/pk_districts.geojson` — 126 districts
  (geoBoundaries ADM2, open dataset), used both for hazard-sampling centroids
  and (once run) for tagging `farms.district`.

## What's stubbed / not real yet

- **Farm Registry is schema-only, not deployed.** No PostgreSQL/PostGIS instance
  exists on this machine (no Docker either) — confirmed by checking, not
  assumed. `schema.sql` has not been executed against a live database. You
  chose "schema-only for now" — install Docker Desktop (or hand me a remote
  Postgres DSN) and I'll run the migration + loader next session.
- **CNIC / farmer identity / crop calendar: entirely empty.** The 120-farm seed
  file has only `{id, date}` per polygon — no farmer, no crop, no CNIC. Per
  your call, these stay NULL rather than fabricated. De-duplication logic
  (`farmers.cnic UNIQUE`) is designed but has nothing to deduplicate yet.
- **Drought/NDVI trend has NOT been extended nationally.** It still only covers
  the 2 original Punjab farm clusters (Layyah, Muridke) — 2 out of 126
  districts. Every other district's drought status in the feed is absent, not
  a fabricated "no drought." Extending this needs either per-district
  farm-cluster bboxes (none exist outside Punjab) or a national NDVI grid pass
  — neither is built. This is the single biggest real gap in "national
  coverage" as of Week 1.
- **`cloud_burst` and part of `heavy_rain` remain self-labeled "STUBBED"** in
  every district row, same as in the original pilot — the 71-file archive
  doesn't have true 15-min-cadence consecutive frames for any location,
  national or not. Detector logic is real; data cadence is the blocker.
- **WRF cross-check has zero date overlap with MSG data at any scope.** Only
  real WRF output on disk is 2026-07-20; real MSG archive is 06-22..07-15.
  Every frost/heat-wave/cold-wave alert reports this gap explicitly rather
  than pretending same-day alignment — this was true in the pilot and is
  unchanged by national extension.
- **District-level alert output is a feed, not delivery.** No SMS/dashboard
  wiring — that's Week 4 by design.

## Real baseline numbers: national vs. pilot bbox

| | Pilot (12 cities) | National (126 districts) |
|---|---|---|
| Alert records | 2,952 | 30,996 |
| Triggered | 42 | 430 |
| Trigger rate | 1.42% | 1.39% |
| Runtime | ~20s (estimated, not re-timed) | 3m26s |

Trigger rate barely moved — a reasonable sanity check that district sampling
didn't inflate or deflate detections mechanically. Per-hazard triggered counts
scaled roughly with location count (fog 18→213, uv_index 12→124, frost 5→58,
cold_wave 4→30), consistent with genuine geographic spread rather than an
artifact.

**Two honest red flags found while producing these numbers, not smoothed over:**

1. **`cold_wave` false-alarm risk.** Some district rows show `cold_wave=True`
   with mean skin temps around -10 to -14°C **in June** (e.g. Abbottabad,
   Astore). `det_heat_wave`/`det_cold_wave` have no clear-sky gate (unlike
   `det_frost`, which requires `cloud_proxy < 0.3`) — under cloud, IR10.8
   "skin temp" reads the cold cloud-top brightness temperature, not the
   ground, and can trigger the cold-wave threshold spuriously. This existed
   in the pilot too (4 triggers) but is now visible at volume (30 triggers).
   Recommend adding the same clear-sky gate to `det_heat_wave`/`det_cold_wave`
   before treating either as operational — flagging, not fixing, since you
   said don't redesign the detectors this week.
2. **Drought/NDVI resolution mismatch.** Both Layyah and Muridke clusters show
   `flag=True` via the `mean_ndvi < 0.20` branch (mean NDVI 0.06–0.07) — not
   the declining-trend branch (slope is actually positive, +0.012 to
   +0.016/day). The NDVI grid is 0.25° (~27km) resolution; the actual farm
   polygons are sub-hectare. A 27km-average NDVI is dominated by whatever
   non-farm land surrounds the cluster, not the farms themselves — so this
   flag is not really measuring farm-level vegetation health yet. Coarse but
   honestly-labeled in the code's own comment ("sparse vegetation baseline,
   not necessarily a trend").

## What's blocked

- Farm Registry live deployment — needs Docker Desktop install or a remote
  Postgres DSN from you.
- National drought/NDVI coverage — needs either more farm-cluster regions or
  a genuine national NDVI grid-based trend pass (new work, not scoped this
  week).
- `cloud_burst`/`heavy_rain` full signal — needs true 15-min-cadence MSG
  archive data, which doesn't exist on disk yet.
- WRF-based cross-checks at any real confidence — needs WRF output that
  temporally overlaps the MSG archive dates.

## Compute/scale note for national extension

Going from 12 points to 126 districts was a ~10.5x increase in sample count
and produced a ~10x runtime increase (20s → 3m26s) — roughly linear, no
blowup, because the underlying 0.25° grid was already national-sized and
precomputed; district mode only adds nearest-neighbor lookups. The real
scaling risk is elsewhere: if district-level coverage is later upgraded from
centroid points to per-district area averages (`sample_bbox_mean`, already
in `hazards.py`) for lower spatial-resolution error, cost stays similar since
it's still one grid lookup per district-field-timestep, not a new grid.
