# Track M — national drought/NDVI signal: scheduling setup

## Why this is weekly, not Track H's 15-minute cadence

Track H's 15-min cadence matches MSG/SEVIRI's real ~12-15 min repeat cycle — polling
less often would miss real new scenes. Track M's real inputs are different in kind:
Sentinel-2 itself only revisits a given point roughly every 5 real days, and the
vegetation/drought trends this signal is meant to capture develop over weeks, not
minutes. A 15-min refresh here would just re-poll data that provably has not changed.
Weekly is the real, honest, appropriate cadence for **this** signal — a correctly
different cadence for a genuinely different real data-refresh rate, not a lesser
version of Track H's.

## What the job actually does, once per invocation

`naip/pipelines/scheduler/drought_weekly_refresh.py` runs **one real cycle** and
exits, same pattern as `live_nowcast_cycle.py` — Task Scheduler provides the
repetition. Each cycle: re-runs `compute_drought_signal.py` (which now writes a real
`last_computed_utc` into `drought_national.json`), then resyncs the dashboard via
`naip_dashboard/prepare_data.py` (unchanged, copies `drought_national.json` through
like every other source file). Logged to `naip/logs/drought_weekly_refresh.log` and
`naip/models/drought_national/weekly_refresh_state.json` (success/failure counts,
last success time — same pattern as Track H's `cycle_state.json`).

## Real, honest limitation of this first version — stated here, not hidden

Recomputing `compute_drought_signal.py` weekly re-runs the real anomaly math against
the **same** current-period Sentinel-2/MODIS extraction Track M was originally built
on — both `models/crop_classifier_national/phenology_features.csv` (Track F's,
reused) and `models/drought_national/modis_current.csv` are bound to a fixed
Nov 2022–Oct 2023 season, not a rolling window (confirmed by reading
`extract_modis_current.py`'s own hardcoded date filter, not assumed). That means the
first several real weekly fires write an updated `last_computed_utc` — the pipeline
genuinely does run again — but an **identical** `district_results`/z-score
distribution each time, because the underlying satellite observations have not
themselves been re-extracted for a new season. `last_computed_utc` honestly answers
"when did this computation last run," not yet "did the underlying satellite data
change this week." Rebuilding the current-period extraction for a rolling/new-season
window is real, separate, larger scope (a new Sentinel-2 + MODIS GEE pull matching
Track F's own extraction methodology) — not attempted here, flagged for a future
track rather than silently implied by this refresh's existence.

## Real no-conflict confirmation vs. Track H

`drought_weekly_refresh.py` never touches `naip/data/live_nowcast/` or
`district_alerts.json`, and makes zero GEE/network calls — `compute_drought_signal.py`
reads only local CSVs already on disk. There is no real resource, file-lock, or
API-quota overlap with Track H's 15-min MSG download loop, regardless of what time
this fires. Both tasks were confirmed independently `Ready`/running after this task
was registered.

## Set up the scheduled task

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\USER\AppData\Local\Programs\Python\Python311\python.exe" `
  -Argument "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler\drought_weekly_refresh.py" `
  -WorkingDirectory "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler"

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:00AM

# REAL GOTCHA, hit again here (same one Track H's Week 13 build found on this same
# machine): New-ScheduledTaskSettingsSet defaults to DisallowStartIfOnBatteries=True,
# which silently queues every fire on this real battery-powered laptop instead of
# running it. Track H's task already had this fixed; this new task did NOT inherit
# that fix automatically -- it must be set explicitly, every time a new task is
# registered on this machine.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "NAIP-DroughtWeekly" -Action $action -Trigger $trigger -Settings $settings `
  -Description "NAIP Track M: real weekly recompute of the national drought/NDVI signal. Independent of NAIP-LiveNowcast (Track H) -- no shared files, no GEE/network calls, no resource overlap."
```

If a task was already registered without the battery-power flags (as happened during
this track's own build — confirmed via `Get-ScheduledTaskInfo` showing `Status:
Queued` instead of `Ready` even after `Start-ScheduledTask`), fix it in place rather
than re-registering:
```powershell
Set-ScheduledTask -TaskName "NAIP-DroughtWeekly" -Settings (New-ScheduledTaskSettingsSet `
  -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)
```

## Start / stop / check

```powershell
Start-ScheduledTask -TaskName "NAIP-DroughtWeekly"          # run one cycle now
Disable-ScheduledTask -TaskName "NAIP-DroughtWeekly"        # stop future fires
Enable-ScheduledTask -TaskName "NAIP-DroughtWeekly"         # re-enable
Unregister-ScheduledTask -TaskName "NAIP-DroughtWeekly" -Confirm:$false   # remove
Get-ScheduledTask -TaskName "NAIP-DroughtWeekly" | Get-ScheduledTaskInfo  # status, last/next run
```

To check real results rather than just scheduler status:
```powershell
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\logs\drought_weekly_refresh.log" -Tail 20
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\models\drought_national\weekly_refresh_state.json"
```

## Verification performed when this was built (2026-08-27)

1. Ran `compute_drought_signal.py` directly — confirmed `last_computed_utc` is
   written and the district-level result is byte-identical to the prior run (as
   expected against frozen inputs — see limitation above).
2. Ran `drought_weekly_refresh.py` directly (not via Task Scheduler) — confirmed
   both pipeline steps succeed and the dashboard's `public/data/drought_national.json`
   resyncs.
3. Registered `NAIP-DroughtWeekly` and called `Start-ScheduledTask` — found the real
   battery-power gotcha above (task queued, did not actually run). Fixed the task's
   settings in place, re-triggered, and confirmed via `weekly_refresh_state.json`
   (`n_success` incremented, `last_success_utc`/`last_computed_utc_written` both
   real and current) that the task genuinely executes through Task Scheduler itself,
   not just when run as a plain script.
4. Confirmed `NAIP-LiveNowcast` (Track H) remained `Ready`/running throughout, with
   no shared state touched by the new task.
5. **Not yet observed**: a real *unattended* weekly fire (the task is registered for
   Sunday 3:00 AM; as of this build it has only been run via explicit
   `Start-ScheduledTask` calls, not by the schedule itself firing on its own). Check
   `NextRunTime`/`LastRunTime` via `Get-ScheduledTaskInfo` after the coming Sunday to
   confirm.
