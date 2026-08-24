# Week 19 — Phase 4, Track K (fire model: real second validation year)

## What this closes

Track E (Week 7) trained a thermal-only GBT fire classifier on a single real
15-day window (Nov 2023) and reported F1=0.346 on a 3-date held-out test
split within that same window. Track K's question: does that result hold up
on a second real burning-season year the model has never seen at all, or was
it specific to that one window's conditions? This is a validation replay,
not a retrain — the persisted `gbt_fire_classifier_thermal_only.joblib`
checkpoint was used exactly as-is.

## Step 0 — live loop paused, real and confirmed

Confirmed the real scheduled task name first (`Get-ScheduledTask`):
`NAIP-LiveNowcast`. No cycle was mid-run (`cycle.lock` absent) before
pausing. `Disable-ScheduledTask -TaskName "NAIP-LiveNowcast"`, confirmed
`State: Disabled` via `Get-ScheduledTask` before starting any EUMETSAT
pull -- no contention with a live cycle firing mid-download.

## Pre-check -- real, before pulling a full archive

**A real credential gap found and closed first**: the FIRMS `MAP_KEY` set up
in Week 5 was never persisted anywhere accessible this session -- checked
shell env, PowerShell process env, User/Machine-level Windows env vars,
`.env` files across the project and home directory, and both PowerShell/bash
profile scripts, all clean. You supplied the real key directly; verified
live against the FIRMS API before using it further.

**Real candidate-year check, all four verified rather than assumed**:
EUMETSAT archive availability confirmed live for 2020/2021/2022/2024 (a real
scene exists for each). Real FIRMS VIIRS hotspot density, national bbox,
Nov 1-15:

| Year | Real hotspot count |
|---|---:|
| 2020 | 54,491 |
| **2021** | **75,957** |
| 2022 | 35,603 |
| 2024 | 11,208 |
| (2023, for reference — the original window) | 26,311 |

**2021 picked** -- not a close call needing a check-in: nearly 3x the
original 2023 window's density and clearly ahead of every other candidate.
Real, full 15-minute-cadence EUMETSAT coverage confirmed across the entire
2021-11-01..15 window before committing to the pull.

## Build

- Real archive pull via `eumdac` (same credentials/product as every prior
  pull, `EO:EUM:DAT:MSG:HRSEVIRI`): 45 real MSG4 scenes, 3x daily
  (02/12/20 UTC), matching the original 2023 pull's exact scale. **Real
  operational bug found and fixed**: the download script's `while read`
  loop shared its stdin file descriptor with the `eumdac` subprocess it
  called inside the loop (`< "$IDS_FILE"` on the loop, no stdin redirect on
  the inner command) -- `eumdac` was silently consuming the *remaining
  product-ID lines* meant for the loop's own `read`, producing an
  "unrecognized arguments" error on the very first iteration. Fixed with
  `< /dev/null` on the inner command. **Real result: 45/45 downloaded**
  (~12GB, matching the 2023 archive's real scale) once fixed.
- Ran `export_hazard_grids.py` unchanged against the new archive -- 45/45
  real timesteps processed, all 7 hazard fields exported per timestep.
- Real FIRMS pull for the matching window (with the ±1-day tolerance buffer
  Track E's own label methodology needs): 83,066 real hotspot rows across
  17 real dates.
- **`build_grid_dataset_2021.py`**: reuses `build_grid_dataset.py`'s exact
  candidate-universe/label/feature logic (50km/±1day FIRMS tolerance, ±3°
  local-background box mean, no lat/lon in the feature set) unchanged --
  only the source paths differ. **Real result: 183,150 rows, 20,986
  positive (11.46%), 15 real distinct dates** -- essentially the same real
  scale and class balance as the original 2023 dataset (183,150 rows,
  12.06% positive), a clean apples-to-apples setup.
- **`replay_track_k_2021.py`**: loads the persisted 2023-trained model,
  makes no further training calls, predicts on the real full 2021 grid.

## Real result -- the model generalizes

| | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|
| GBT thermal-only, **2023 test** (original headline, 3 held-out dates) | 0.245 | 0.587 | 0.346 | 0.737 |
| **GBT thermal-only, 2021 full grid (this replay, 15 dates, never seen)** | **0.230** | **0.763** | **0.354** | **0.786** |
| Rule-based (`det_residue_burning()`, unchanged), 2023 full grid (original) | 0.132 | 0.004 | 0.0087 | n/a |
| Rule-based (`det_residue_burning()`, unchanged), 2021 full grid (this replay) | 0.065 | 0.001 | 0.002 | n/a |

**F1 is essentially unchanged (0.354 vs. 0.346)** on a real year the model
never trained on -- recall is meaningfully higher (0.763 vs. 0.587), ROC-AUC
slightly higher (0.786 vs. 0.737), precision very slightly lower (0.230 vs.
0.245). Reported honestly, not cherry-picked: the 2021 comparison uses the
*full* 15-date grid vs. the original's 3-date *test* split, a wider real
sample rather than a narrower one, which is if anything a harder bar to
clear, not an easier one -- the model cleared it. **This is real, direct
evidence the original result was not a one-off fluke of the 2023 window's
specific conditions.**

The rule-based baseline, replayed completely unchanged, stays poor on both
real years (F1 0.0087 on 2023's full grid, 0.002 on 2021's) -- confirming
its full-grid weakness is a structural property of the fixed 10.0K
threshold, not something specific to one year's data either.

## What this doesn't settle

Two real years is real, useful evidence of generalization, not a permanent
proof across every possible burning-season condition -- the same caution
every other single-second-year validation in this project carries (Track
I's 2024 cross-year check, Track J's cross-year crop-mix result). Both real
years share the same national bbox and the same MSG sensor/product; a third
year, or a genuinely different region, would still add real information.

## Step Final -- live loop resumed, confirmed

`Enable-ScheduledTask -TaskName "NAIP-LiveNowcast"`, confirmed `State:
Ready` via `Get-ScheduledTask`, `NextRunTime` populated
(`2026-08-23T23:06:06`). **Waited for and confirmed a real successful cycle
fired after resuming, not assumed**: watched the task transition to
`State: Running` at the scheduled time, confirmed via `cycle.lock` and the
live log (`naip/logs/live_nowcast.log`) that it found a real new scene
(`MSG3-SEVI-MSG15-0100-NA-20260824051242.951000000Z-NA`), ran the full
pipeline (download → `export_hazard_grids.py` → `export_skin_temp.py` →
`hazards.py` → district aggregate → merge → dashboard resync), and logged
`=== cycle SUCCESS ..., 226s total ===`. `cycle_state.json` confirms:
`n_success` 71→72, `last_success_utc` updated to the real new timestamp,
task back to `State: Ready` with `LastTaskResult: 0` and a normal
`NextRunTime` for the following cycle. The pause/resume process behaved
exactly as expected throughout -- no unexpected behavior, no need to check
in before resuming.

## Real files this week produced

- `naip/models/residue_burning/build_grid_dataset_2021.py`,
  `replay_track_k_2021.py`
- `naip/data/msg_oct_nov_2021/nat_in/` (45 real .nat scenes, gitignored,
  same convention as the other MSG archives)
- `naip/data/msg_oct_nov_2021/web_data/msg_hazard/` (real exported hazard
  grids, 45 timesteps)
- `naip/data/fire_ground_truth/firms_national_2021nov_*.csv` (real FIRMS
  pull, 4 chunk files)
- `naip/data/msg_oct_nov_2021/grid_dataset.parquet`,
  `grid_dataset_sample.csv`, `track_k_results.json`
