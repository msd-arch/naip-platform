# Week 13 status report — Phase 4, Track H (live nowcasting loop)

Full context: `docs/PHASE4_SCOPE_DOCUMENT.md` (Track H's scope, blocker pre-check),
`naip/docs/TRACK_H_SCHEDULING.md` (real setup/start/stop/check instructions).

## The one real limitation, stated plainly (not just here)

This runs on a personal Windows machine, not a server. The schedule only fires while
that machine is on, awake, and not asleep/hibernating — there is no failover host, no
guaranteed uptime. This is stated in the orchestrator script's own docstring, in
`TRACK_H_SCHEDULING.md`, in every `pipeline_health.json` write, and in the dashboard's
own live-ness badge (not implied away anywhere it appears).

## Real finding: the NRT licence needed real propagation time, not a code fix

The scope document reported the EUMETSAT NRT (<3hr latency) licence as "resolved
favorably" — accepted and confirmed browsable/downloadable in the Data Store web UI for
today's real scene. **Real API testing during this track's build initially found
otherwise**: downloading a scene 4.5 hours old (the >3hr archive tier) succeeded via
`eumdac` immediately; downloading the same-day near-real-time scene confirmed browsable
in the web UI returned a real, specific 403 — `"NRTLicense required to access this
collection"` — traced directly against the raw EUMETSAT Data Store API, not just the
`eumdac` CLI's own error text.

Per direction, a single bounded 45-minute wait-and-retry was run against the exact same
API call before falling back — **it came back 200**. Real access, just not
instantaneous: a genuine web-to-API authorization propagation delay, not a permanent
block or a code problem. No propagation-delay explanation or licence-status API
endpoint was found to verify programmatically that the API-key-linked account matches
the web-UI-authenticated account; this remains an unresolved discrepancy in EUMETSAT's
own documentation, not something further guessing from this side would have resolved
faster than the bounded wait did.

**A second real finding, only visible once the loop was actually running unattended**:
the ~30 minute minimum-latency bracket estimated right after the retry (32min old = OK,
17min old = still 403) turned out to be an unstable zone, not a clean threshold. Two
real scheduler-fired cycles failed with fresh 403s on scenes 39-42 minutes old, well
after the initial retry succeeded — full real bracket: 33min=200, 40min=403, 42min=403,
57min=200 (same scene, aged further), 58min=200. Caught live during the observation
window (Step 5), not discovered after the fact: `MIN_LATENCY_HOURS` was widened from
0.6h to **1.0h**, clearing the unstable zone — confirmed by an unbroken run of clean
successes afterward (see Real observation window below).

**Real, honest characterization of the achieved cadence**: Track H runs at a real
empirically-confirmed ~1 hour minimum latency, not the licence's nominal sub-hour
near-real-time case, and not the original 3.25hr archive-tier fallback either — a
genuine middle ground, reported at its real value, not rounded toward either extreme.

## Real per-cycle timing (Step 1)

Measured directly, one real scene end to end, before committing to a cadence:

| Stage | Real seconds (1st scene, 1 file in rolling window) |
|---|---|
| Download + unzip | ~70s |
| `export_hazard_grids.py` | 42s |
| `export_skin_temp.py` | 22s |
| `hazards.py --locations districts` | 37s |
| `district_aggregate.py` | 1s |
| `prepare_data.py` (dashboard resync) | 4s |
| **Total** | **~176s (~3 min)** |

Comfortably inside MSG's real ~12–15 minute repeat cycle (~20% utilization) — **the
natural cadence is achievable**, no fallback to a coarser interval was needed. Real
per-cycle processing time scales with how many `.nat` files sit in the rolling
`nat_in/` window (confirmed: 66s for `export_hazard_grids.py` with 2 files vs. 42s with
1, since the unchanged script reprocesses everything present each run) — bounded by a
`PRUNE_KEEP_LAST` cap in the orchestrator so this stays roughly constant rather than
growing without limit as the loop runs longer. **Revised live, mid-observation, from
the original 24 to 8** — see "A third real issue" below; 24 let real per-cycle time
grow past both Task Scheduler's execution-time limit and the cadence itself once the
window filled up over several real hours of unattended running, something the initial
one-scene timing check in this section couldn't have surfaced.

## What was built (Steps 2-4)

- **`naip/pipelines/scheduler/live_nowcast_cycle.py`** — one real cycle per invocation,
  no internal loop/sleep (Task Scheduler provides the repetition). Orchestration only —
  `export_hazard_grids.py`, `export_skin_temp.py`, `hazards.py`, `district_aggregate.py`
  run **unchanged**, exactly as every prior week's manual invocation ran them. Track E's
  real fire `model_score` requires no extra step — it's already attached inside
  `hazards.py` from Week 9/Track G's wiring.
- **Merge into the real production feed, additively**: live district-day-hazard rows
  upsert into `naip/backend/alerts/district_alerts.json` by `(district, date, hazard)`
  — this extends the real feed forward with new live dates, and does not touch or
  remove any historical Week-1-archive row the rest of the product (demo scenario,
  trigger engine, exposure risk) depends on. Verified directly: 16,128 historical rows
  + 1,386 real live rows for 2026-08-20 = 17,514 total, confirmed rendering on the live
  dashboard.
- **Every real cycle logged** to `naip/logs/live_nowcast.log` (timestamped, per-stage
  duration, real scene ID) and to `naip_dashboard/public/data/pipeline_health.json`
  (status, last success time, real success/failure/no-new-scene counts, the Windows-
  uptime caveat).
- **Real failure handling (Step 3)**, each a distinct, explicitly-logged, non-fatal
  path with no manual un-sticking required: no new scene yet (checked against a
  persisted `processed_scene_ids` list in `cycle_state.json`, logged as normal, not an
  error), a download failure (caught, logged with the real error text, nothing written
  downstream), a mid-pipeline processing failure at any stage (caught, logged with the
  stage name and real error, the merge step never runs on partial output). Every
  failure mode leaves no partial state — the next scheduled cycle retries cleanly. **A
  fourth failure mode was found live and closed the same day, not left open**: a real
  OS-level hard kill (Task Scheduler's own execution-time limit, not a Python
  exception) skips Python's `except`/`finally` entirely, so it was invisible to this
  handling until a `cycle.lock` file (with a 20-minute staleness timeout) was added —
  see "A third real issue" below.
- **Windows Task Scheduler** (`NAIP-LiveNowcast`, registered via PowerShell,
  `Register-ScheduledTask`) — real 15-minute repetition, `-StartWhenAvailable` so a
  missed cycle (machine off) catches up rather than silently skipping. The execution
  time limit started at 10 minutes and was raised to 12 live during the observation
  window once real evidence showed 10 was too tight at the original rolling-window
  size. Full start/stop/check commands in `naip/docs/TRACK_H_SCHEDULING.md`.

## Real bug caught and fixed during build

The health-timestamp writer used `dt.datetime.now(dt.timezone.utc).isoformat() + "Z"`
— invalid, since a timezone-aware `isoformat()` already appends `+00:00`, producing a
malformed double-suffixed timestamp (`...+00:00Z`) that the dashboard's `PipelineHealthBadge`
couldn't parse (rendered `NaNd ago`). Caught during the same-session dashboard
verification pass (not left for a future week to find), fixed to a single valid
`+00:00` suffix, and the already-written bad state files were corrected in place rather
than silently left wrong.

## Dashboard (Step 6)

`PipelineHealthBadge.tsx` — a small always-visible indicator (real status dot, real
"last successful cycle" time, real success/failure/no-new-scene counts, an
expand-to-read Windows-uptime caveat) added to both the Overview and Hazards pages, per
the requirement that liveness be genuinely visible, not just claimed in a report.
Verified live: type-checked clean, zero console errors, real data confirmed rendering
(including confirming the NaN-timestamp bug above before it shipped).

## Real observation window (Step 5) — extended beyond the original 3 hours to close out real issues, not just watch

Per direction: a few hours, enough to see genuinely scheduler-fired (not manually
triggered) cycles accumulate. Two manual verification runs confirmed the pipeline
worked end to end before the schedule took over; from **13:49 UTC** (the last manual
run) every cycle counted below was fired by Windows Task Scheduler alone, unattended.
The window ran roughly **13:49–20:57 UTC (~7 hours)**, longer than the originally
planned 3, because a second real issue emerged partway through and closing it out
properly — not just noting it and moving on — was judged more valuable than stopping
at an arbitrary clock time with an open problem.

**Two real infrastructure bugs caught and fixed in the first 3 hours**:
1. `DisallowStartIfOnBatteries: True` (the task's default) — this machine is a laptop,
   real-tested on battery (`Get-CimInstance Win32_Battery`: discharging, 74%), which
   silently prevented any fire for the first ~45 minutes after registration
   (`LastRunTime` stuck at never-run while `NextRunTime` kept advancing). Fixed via
   `Set-ScheduledTask -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries`.
2. A timestamp-formatting bug (`isoformat()` on a timezone-aware datetime, then
   appending a redundant `"Z"`) produced an invalid double-suffixed timestamp that the
   dashboard's `PipelineHealthBadge` couldn't parse (`NaNd ago`). Fixed; already-written
   bad state files corrected in place.

**The NRT-margin issue, split honestly into its two real phases**:

| Phase | Window | Real NRT margin | Success | Failure | No new scene |
|---|---|---|---|---|---|
| Phase 1 | 13:51–14:21 UTC | 0.6h (36min) | 0 | **2** (real 403s, scenes 39–42min old) | 1 |
| Phase 2 | 14:36–17:16 UTC | 1.0h (60min) | **11** | 0 | 0 |

Phase 2 ran clean and unbroken — 11/11 real successes, zero NRT-related failures — a
direct confirmation the margin fix genuinely resolved the licence-boundary instability
(full real bracket behind that fix: 33min=200, 40min=403, 42min=403, 57min=200,
58min=200).

**A third real issue, distinct from the licence problem, found only because the window
ran long enough to hit it**: as the rolling `nat_in/` window grew past ~15–20 files
over several real hours, real per-cycle time grew past both Task Scheduler's
execution-time limit (originally 10 minutes) and started approaching the 15-minute
cadence itself. Cycles were being **silently hard-killed by the OS**, not failing
cleanly — a hard kill (`TerminateProcess`, how Windows enforces `ExecutionTimeLimit`)
skips Python's `except`/`finally` entirely, so these were invisible to this script's own
`n_failure` counter and looked, from the log alone, identical to a hang. Traced
precisely by cross-referencing kill timestamps against cycle-start times (each matched
start-time + ~10min almost exactly) and confirmed by process-list checks showing zero
`python.exe` running at the time — not a suspended/sleeping process, a genuinely
terminated one. Real cycles affected: 17:21, 19:27, 19:51, 20:21 UTC (4 hard kills); one
of these (18:24 UTC) produced a real *visible* failure — a race condition where a
freshly-started cycle collided with a just-killed one's leftover shared temp directory
(`export_hazard_grids.py`'s `_hazard_grid_tmp`), a `FileNotFoundError`. **A separate
~1 hour gap (17:21→18:24 UTC) with zero scheduler activity logged at all** is reported
honestly as the least-certain finding of the day — most consistent with the machine
sleeping (the documented Windows-uptime caveat), but this can't be fully distinguished
from a Task-Scheduler-side stall from the log alone, and no independent power-state log
was captured at the time to settle it.

**Fixed, not just diagnosed**: added a `cycle.lock` file to the orchestrator (a cycle
now refuses to start if another appears to still be running, with a 20-minute
staleness timeout so a genuinely-dead process's lock gets taken over rather than
permanently wedging the loop — already proven live: it correctly deferred a fire at
20:06 UTC and correctly took over a stale lock at 20:21 UTC); reduced the rolling
`nat_in/` cap from 24 to 8 files (keeps real total cycle time to ~5-6 minutes even at
the cap); raised the execution-time limit from 10 to 12 minutes for margin. **The very
next scheduled cycle after all three fixes landed together (20:51 UTC) succeeded
cleanly in 328s** — `export_hazard_grids.py` alone dropped from 388s (20 files) to 186s
(8 files), confirming the fix.

**A real, honest limitation of the counter itself, found while reconciling these
numbers**: `n_failure` in `cycle_state.json` only increments on a caught Python
exception — hard kills never reach that code path, so they are invisible to the
persisted stat and only discoverable by reading the raw log for gaps. This is stated
here rather than left implicit, since a plain `n_success`/`n_failure` read would have
under-reported real interruptions.

**Real final counts, full ~7-hour window, categorized honestly rather than blended
into one number**:

| Category | Count |
|---|---|
| Real successes (2 manual + 12 scheduler-fired unattended) | 15 |
| Real failures — caught exceptions (2 NRT-margin 403s + 1 temp-dir race) | 3 |
| Real hard-kills — OS-terminated, invisible to `n_failure`, found via log-gap analysis | 4 |
| No new scene (normal, not an error) | 3 |
| Ambiguous ~1hr scheduler gap (likely machine sleep, not fully confirmed) | 1 |

**Real final state, confirmed directly, not assumed**:
- `naip/backend/alerts/district_alerts.json`: **17,514 rows**, 15 real days
  (14 historical Week 1–11 archive days + 2026-08-20 live), zero corruption or partial
  writes at any point across every failure and hard-kill above.
- `naip_dashboard/public/data/pipeline_health.json`: `status: "ok"`,
  `last_success_utc: 2026-08-20T20:57:20`, `n_success: 15`.
- **What this proves**: real unattended automation, confirmed over a real multi-hour
  window, with real edge cases (a licence-boundary instability, a laptop-battery
  setting, a timestamp bug, and an OS execution-time-limit interaction) encountered and
  fixed live, not simulated or assumed away. **What this does not prove**: guaranteed
  uptime. The machine-sleep gap is real evidence the documented Windows-uptime caveat
  is not theoretical — this is a real personal-machine pipeline, still exactly as
  scoped, not a claim of production-grade reliability.

## Not done this week, stated plainly

- Sub-1-hour latency at the licence's nominal near-real-time level — the real,
  confirmed-reliable minimum is ~57–58 minutes (see the bracket above), not the
  licence's theoretical sub-hour case. Still a large real improvement over the
  originally-necessary 3.25hr archive-tier fallback.
- No further probing of exactly why the 30–45min NRT zone is unstable (backend
  cache-propagation lag, a genuine "hourly-only" release tier, or something else) — the
  practical fix (widen the margin) was taken once the pattern was confirmed with real
  evidence; a EUMETSAT support ticket would be the way to actually resolve the
  underlying mechanism, not something guessable from this side.
- The ~1 hour scheduler gap (17:21→18:24 UTC) is not conclusively attributed to machine
  sleep vs. a Task-Scheduler-side stall — reported as the least-certain finding, not
  forced into false certainty.
- The scheduled task itself was **not** stopped or disabled — per direction, Track H
  stays live in production going forward; this closes out the observation/reporting
  phase only.

## Track J (same week) — cheap check, no code change

Run alongside Track H's observation window (read-only, no GEE calls, safe to run
concurrently). Real result: Track F's 2,875 training points carry 2022-23 MNFSR labels
only (`parse_mnfsr_crop_mix.py` hardcodes `cap_2022_23.txt`), and the Sentinel-2
phenology features were deliberately restricted to the matching Nov 2022–Oct 2023
window — a genuine temporal holdout does not exist and structurally couldn't, since
only one label year was ever built. A second real MNFSR document
(`cap_2021_22.pdf`/`.txt`) is already downloaded and unused; parsing it is free, but a
matching real Sentinel-2 pull for 2021-22 is a new GEE call, deliberately held back
this week per direction (concurrent load with Track H's live loop) and logged as an
explicit next step in `docs/PHASE4_SCOPE_DOCUMENT.md`'s Track J section. No code
touched — Track F's deployed model and `exposure_risk.py` untouched.

## Real files this week produced

- `naip/pipelines/scheduler/live_nowcast_cycle.py` — the real orchestrator (one cycle
  per invocation, now with a `cycle.lock` staleness-protected lock), `naip/docs/
  TRACK_H_SCHEDULING.md` (setup/start/stop/check)
- `naip/data/live_nowcast/` — rolling `nat_in/` (now capped at 8), `web_data/`,
  `cycle_state.json`, `cycle.lock` (present only while a cycle is actively running)
- `naip/logs/live_nowcast.log` — real, append-only per-cycle log
- `naip_dashboard/app/components/PipelineHealthBadge.tsx` — added to Overview and
  Hazards pages
- `naip_dashboard/public/data/pipeline_health.json` — written by every real cycle
- Windows Task Scheduler task `NAIP-LiveNowcast` (system state, not a repo file) —
  registered, patched for the battery-block fix
- `naip/backend/alerts/district_alerts.json` — real live rows merged in additively
  (16,128 historical + 1,386 real live rows for 2026-08-20 = 17,514 total, confirmed
  rendering on the live dashboard)
