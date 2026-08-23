# Track H — live nowcasting loop: scheduling setup

## The one thing to understand before anything else

**This runs on a personal Windows machine, not a server.** Windows Task Scheduler fires
the job on the configured cadence *only while this machine is on, awake, and not asleep/
hibernating*. There is no failover host, no guaranteed uptime, no retry-elsewhere if the
machine is off. A gap in `naip/logs/live_nowcast.log` most likely means the machine was
off or asleep — check the log for the real reason either way, don't assume a silent
pipeline bug. This is a real, permanent constraint of this project's actual
infrastructure, not a temporary setup step to fix later.

## What the job actually does, once per invocation

`naip/pipelines/scheduler/live_nowcast_cycle.py` runs **one real cycle** and exits — it
does not loop or sleep internally. Task Scheduler is what provides the repetition. Each
cycle: searches for the latest real MSG3 scene old enough for the currently-authorized
licence tier, downloads it, runs the unchanged `export_hazard_grids.py` →
`export_skin_temp.py` → `hazards.py` (which already attaches Track E's real fire
`model_score`) → `district_aggregate.py`, merges the result into the real
`district_alerts.json` (additively, by `(district, date, hazard)` — never touches
historical rows), and resyncs the dashboard. Every cycle is logged to
`naip/logs/live_nowcast.log` and to `naip_dashboard/public/data/pipeline_health.json`
(what the dashboard's live-ness indicator reads).

## Real licence-tier note

The EUMETSAT near-real-time licence returned a real 403
(`"NRTLicense required to access this collection"`) on the first API test during this
track's build, despite being accepted and browsable in the Data Store web UI. A single
bounded 45-minute wait-and-retry came back **200** — real access confirmed, just not
instantaneously (a real web-to-API authorization propagation delay, not a permanent
block). Real follow-up testing bracketed the actual minimum latency at **~30 minutes**
(a scene 32 min old downloaded fine; one 17 min old still 403'd). The script defaults
to `MIN_LATENCY_HOURS = 0.6` (36 min, a real margin above the confirmed-working point).
See `naip/docs/STATUS_WEEK13.md` for the full real timeline. To force the older,
more-conservative archive tier instead:
```
python live_nowcast_cycle.py --min-latency-hours 3.25
```

## Set up the scheduled task

Run once, from an elevated PowerShell (Run as Administrator) or a regular one — creating
a task for the current user does not require admin rights:

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\USER\AppData\Local\Programs\Python\Python311\python.exe" `
  -Argument "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler\live_nowcast_cycle.py" `
  -WorkingDirectory "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
# Note: [TimeSpan]::MaxValue fails registration ("Duration:P99999999DT23H59M59S" out of
# range for the Task Scheduler XML schema) -- 3650 days (10 years) is the real value
# that actually registered during this track's build.

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "NAIP-LiveNowcast" -Action $action -Trigger $trigger -Settings $settings -Description "NAIP Track H: one real MSG nowcast cycle every 15 min. Only fires while this machine is on."
```

Notes on the flags:
- `-RepetitionInterval 15 min` matches the real per-cycle processing time measured
  during this track's build (~106s pipeline + ~70s download ≈ 3 min), which comfortably
  fits inside MSG's real ~12–15 min repeat cycle with headroom — no coarser cadence is
  needed.
- `-StartWhenAvailable` means a missed cycle (machine was off) runs as soon as the
  machine is next on, rather than being silently skipped until the next scheduled slot.
- `-ExecutionTimeLimit 10 min` kills a genuinely hung cycle rather than letting it block
  every future one indefinitely — a hung cycle logs nothing further and the next
  scheduled cycle starts fresh regardless (the script holds no lock a killed process
  could leave stuck).

## Start / stop / check

```powershell
# Start (or resume after Disable)
Start-ScheduledTask -TaskName "NAIP-LiveNowcast"

# Stop the schedule from firing again (does not kill a currently-running cycle)
Disable-ScheduledTask -TaskName "NAIP-LiveNowcast"

# Re-enable
Enable-ScheduledTask -TaskName "NAIP-LiveNowcast"

# Remove entirely
Unregister-ScheduledTask -TaskName "NAIP-LiveNowcast" -Confirm:$false

# Check current status (Ready/Running/Disabled) and last/next run time
Get-ScheduledTask -TaskName "NAIP-LiveNowcast" | Get-ScheduledTaskInfo

# Run one cycle immediately, outside the schedule (for testing)
Start-ScheduledTask -TaskName "NAIP-LiveNowcast"
```

To check real results rather than just scheduler status:
```powershell
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\logs\live_nowcast.log" -Tail 40
Get-Content "C:\Users\USER\Downloads\naip_dashboard\public\data\pipeline_health.json"
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\data\live_nowcast\cycle_state.json"
```

## Recovery — no manual intervention should ever be required

Every failure mode (no new scene yet, a download failure, a mid-pipeline processing
failure) is caught, logged with a specific reason, and leaves no partial state — the
next scheduled cycle retries cleanly on its own. If cycles stop appearing in the log
entirely, the real cause is almost always the machine being off/asleep, not a stuck
job — `Get-ScheduledTaskInfo`'s `LastTaskResult` and `LastRunTime` confirm which.
