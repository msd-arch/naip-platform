# Exposure Risk / Trigger Engine — live evaluation architecture (Part 3)

## What changed, real and specific

Historically `exposure_risk.py`/`trigger_engine.py` scored against
`naip/backend/alerts/hazards_district_national.json` — a file that was **not** kept in
sync with Track H's 15-min live loop. It last got a real update 2026-08-27 08:58 (a
one-off manual/scripted pass, confirmed by reading its own coverage_notes and file
mtime) and everything since then required a manual rerun. This closes that gap:

1. **`naip/backend/alerts/merge_live_into_hazards_national.py`** (new) — upserts Track
   H's live rolling-window alerts (`data/live_nowcast/hazards_district_live.json`) into
   `hazards_district_national.json`, keyed by `(date, hazard, district, slot)`. Same
   real pattern `merge_flood_into_hazards_alerts.py` already established for flood_risk
   (Week 27), generalized to every hazard the live loop produces. Never touches a
   historical row the live rolling window doesn't currently cover.
2. **`live_nowcast_cycle.py`** gained a new, gated step (`run_trigger_eval_step()`),
   run *after* the existing hazard-detection success is already saved to
   `cycle_state.json` — so a Part 3 failure never costs Track H's own real historical
   continuity (the scene still gets marked processed either way). It runs, in order:
   the merge script above, `exposure_risk.py`, `trigger_engine.py` twice (national
   0.225 + demo 0.0216 thresholds), then a second `prepare_data.py` resync.
3. **Crop weights are read, not recomputed.** `exposure_risk.py`'s `resolve_crop_weight()`
   already only reads `real_crop_mix.json`/`real_crop_mix_interim_estimates.json` (static
   files) — confirmed by reading the code, not assumed. No new work was needed to satisfy
   "don't recompute crop weights every cycle" because the existing design never did.
4. **`trigger_engine.py`'s summary output** (`trigger_summary_national.json`/`_demo.json`)
   gained a real `last_computed_utc` + `refresh_cadence_note`, rendered in the Explore
   view's Trigger Engine panel — same visibility standard as drought/flood/locust.

## Status: LIVE in production (resolved 2026-08-28)

Enabled per your direction (Option 1 below). See "Resolution" section at the bottom
for the real fix and verification — the cost/margin analysis immediately below is
kept as-written since it's the real reasoning that drove the decision.

## Real measured cost — why this needed a decision before going live

Measured against the real, then-current merged archive (2026-08-28, 43,218 alerts),
through the actual `live_nowcast_cycle.py` code path (real subprocess calls, not a
faster in-process shortcut):

| Step | Real time |
|---|---|
| `merge_live_into_hazards_national.py` | ~2s |
| `exposure_risk.py` | ~4s |
| `trigger_engine.py` (national threshold) | ~6s |
| `trigger_engine.py` (demo threshold) | ~8s |
| `prepare_data.py` (second resync) | ~1s |
| **Total** | **~22s** |

On its own, cheap. The real problem is headroom on top of Track H's **existing**
cycle-time variance, which was re-measured (not assumed) before building anything:

- Last 20 real successful `live_nowcast_cycle.py` cycles (2026-08-28): 164–**696s**,
  mean 328s. The 696s outlier is driven by `export_hazard_grids.py` reprocessing a
  full 8-scene rolling window (`PRUNE_KEEP_LAST=8`) — unrelated to this change.
- `NAIP-LiveNowcast`'s real configured `ExecutionTimeLimit` is **720s (12 min)**
  (confirmed via `Get-ScheduledTask`).
- **696s of 720s = only 24s of real margin, before Part 3 adds anything.**
- Adding the real ~22s measured above shrinks that to **~2s of margin on the
  worst-case cycle** — Task Scheduler would very plausibly hard-kill a full-window
  cycle mid-run, the same silent "looks like a hang, no exception, no log line"
  failure mode Track H's own Week 13 postmortem already found once at the old 10-min
  limit.

Gated behind `ENABLE_TRIGGER_EVAL` so this wasn't pushed live silently the moment the
file was saved — `live_nowcast_cycle.py` is Track H's production script, already
firing every ~15 real minutes.

## Verified real, end-to-end (2026-08-28)

Ran `run_trigger_eval_step()` directly against the real live data before any
scheduling decision: the merge correctly folded a real 2026-08-28 alert (Tando
Allahyar, cloud_burst x cotton) into the scoring archive, `exposure_risk.json`'s top
events reflect it, and the demo-threshold trigger count moved 16 → 17 — real
end-to-end correctness, proven before touching the live task at all.

## Resolution — Option 1 chosen, real fix, real verification

You chose to raise `ExecutionTimeLimit` (Option 1) over decoupling Part 3 onto its
own schedule (Option 3, rejected — it would defeat the actual point of running
trigger evaluation inside the same cycle as the freshest hazard data) or shrinking
`PRUNE_KEEP_LAST` (Option 2, deferred — a legitimate but separate root-cause fix for
the 696s outlier itself, deserving its own testing, not bundled into unblocking this).

1. **`NAIP-LiveNowcast`'s `ExecutionTimeLimit` raised 12→15 min** — real headroom
   instead of a ~2s razor's edge, no change to what the pipeline computes.
2. **A real, second Windows-scheduling gotcha found while enabling this**: setting
   `NAIP_ENABLE_TRIGGER_EVAL=1` as a User-scope PowerShell environment variable did
   **not** propagate to Task Scheduler's spawned process — confirmed by a real
   unattended fire completing with zero Part 3 log lines despite the variable being
   set. Fixed by adding a real `--enable-trigger-eval` CLI flag to
   `live_nowcast_cycle.py` and baking it directly into `NAIP-LiveNowcast`'s own
   Action argument string (the env var still works for ad-hoc manual runs, just not
   for the scheduled task itself) — command-line arguments don't have the same
   inheritance problem environment variables set outside a task's own definition do.
3. **Real verification, two consecutive cycles**: first (Start-ScheduledTask
   triggered, but a genuine execution through the real scheduler) — 369s total, Part
   3 added 46s. Second — **fired entirely on its own**, no manual trigger, at the
   scheduler's own predicted time (00:51:51 UTC) — 364s total, Part 3 added 51s. Both
   comfortably under the new 900s limit; real margin ~530s+ on these cycles, a real
   projected ~154s even replaying the historical 696s worst case.

**Part 3 is live in production as of 2026-08-28.**

## What was deliberately NOT scheduled

Per direction: Crop Intelligence and AI Models pages are trained-model *validation
snapshots* (Track F's crop-share model, Track E's fire classifier, Track D/I's flood
classifier's fair-test numbers) — meaningful to refresh only when a model is genuinely
retrained on new real ground truth (for the crop-share model, a new MNFSR report; for
the others, a new labeled year of imagery). No scheduled task exists for these, and
none should be added reflexively — this is a stated decision, not an oversight.
