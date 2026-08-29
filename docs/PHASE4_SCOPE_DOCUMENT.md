# Phase 4 Scope Document

**Reconstructed 2026-08-29, not an original planning document.** This file has been
cited repeatedly by `CLAUDE.md`'s own Sprint log (Weeks 25, 26, 27) and by prior
session status reports as if it already existed — it never did, confirmed by a
direct, case-insensitive search of the repo. Rebuilt here from `CLAUDE.md`'s real,
already-closed Sprint history (Weeks 13–21), not from memory or invention. Where
`CLAUDE.md`'s own entry is the authoritative source, this document summarizes and
cross-references it rather than duplicating it — read the numbered Week entry for
full real detail.

## Real scope: seven tracks (confirmed explicitly at Week 20's close)

> "Phase 4's original seven-item scope (Tracks H, I, J, K, L, M, N) plus this final
> integration item are all now closed." — `CLAUDE.md`, Week 20

| Track | What it is | Closed | Real status (see `CLAUDE.md` for full detail) |
|---|---|---|---|
| **H** | Live nowcasting loop — Track H's own script (`live_nowcast_cycle.py`) fires on a real ~15-min Task Scheduler cadence, downloading and processing real MSG scenes | Week 13 | Live in production since Week 13, still running as of this document (Week 31's Part 3 work extended it further). |
| **I** | Flood model, real non-disaster negative class | Week 14 (v2 rejected), resumed Week 26 (v3, precipitation features), fully closed Week 27 | v3 (`gbt_flood_classifier_v3_precip_fulltrain.joblib`) promoted and wired into `exposure_risk.py`/`trigger_engine.py`. Real fair-test result: F1 0.229→0.312 vs. the original, on the 2024 held-out year that caught v2's collapse. |
| **J** | Temporal-holdout / cross-year validation check for Track F's crop-share model | Opened Week 13 (found no genuine holdout existed), resumed Week 17 | Real cross-year result: wheat/cotton/rice degrade as expected; sugarcane a real, honest exception (positive R² both directions, vs. the original's -1.120) — not claimed as a validated fix. |
| **K** | Fire model, real second validation year (2021) | Week 19 | Unchanged 2023-trained thermal-only GBT replayed against a real, entirely unseen 2021 archive: F1 essentially unchanged (0.354→0.354), recall meaningfully higher — real evidence the original result wasn't a fluke. |
| **L** | Retrain the nowcast-to-forecast fusion U-Net at real scale | Week 18 | Real n=81 (up from the original n=12 bottleneck, which was a download-count limit, not a real date-overlap problem). Real result: trained U-Net beats the linear baseline by ~29% RMSE on a temporally-blocked test (entire Nov 2023 archive, never touched in training). |
| **M** | National drought/NDVI signal at real (10m Sentinel-2) resolution | Week 16, real weekly scheduling added Week 25 | Real self-caught cross-sensor bias fixed twice before any headline number was reported. Real result: 126/126 districts covered, 2 flagged (Hunza, Jafarabad). `NAIP-DroughtWeekly` scheduled task, real `last_computed_utc` visible on the dashboard. |
| **N** | Infrastructure debt status check (Docker/PostGIS, Twilio) | Week 15 | Both real-checked directly (not assumed stale): neither worth deploying/pursuing at the time, both explicitly revisited rather than left to rot. Docker/PostGIS status changed later — see Track P's `in_memory_registry.py` work, Week 29. |
| *(final item, no track letter)* | Wire `model_estimated_interim` (Track F's model-estimated crop-mix tier) into `exposure_risk.py`/`trigger_engine.py` | Week 20 | Real, date-aware three-tier resolution (real MNFSR data → model-estimated interim → hand-classified mask). Real, structurally significant consequence: most real hazard archive rows now resolve to the interim tier, since NAIP's real hazard data postdates the 2022-23 MNFSR season. |

## Real post-Phase-4 follow-on (not part of the original seven-item scope)

- **Week 21**: threshold recalibration (tier-aware, crop-aware) — a real per-crop
  confidence discount for `model_estimated_interim` rows, using Track F's own
  validated cross-year R² per crop. Explicitly framed in `CLAUDE.md` as a
  "post-Phase-4 follow-on," not a retroactive addition to the seven-item scope above.

## What Phase 4 explicitly did NOT cover

Crop Intelligence and AI Models pages are trained-model *validation snapshots*
(Tracks E/F/I's own fair-test numbers) — real, but meaningful to refresh only on a
genuine model retrain against new real ground truth, not on any calendar cadence. No
Phase 4 track scheduled these, and none should be added reflexively (restated
explicitly in Week 31's Part 3 work, since the same question came up again there).
