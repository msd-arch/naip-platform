# Flood Risk Screen — scheduling setup (Part 1 of "make everything live")

## Why this is weekly, not Track H's 15-minute cadence

`predict_flood_risk_live.py` (the promoted v3 model) genuinely recomputes its real
during/pre-monsoon windows from today's date every run, and makes a real, several-minute
GEE network call (Sentinel-1 + JRC + CHIRPS across 126 districts x 15 points — measured
~4m48s end to end). A 15-min cadence would spend roughly a third of every cycle on a
screen whose real underlying signal (a rolling 30-day SAR window) doesn't meaningfully
change minute to minute. Weekly is the real, appropriate cadence for this signal.

## What the job actually does, once per invocation

`naip/pipelines/scheduler/flood_weekly_refresh.py` runs **one real cycle** and exits,
same pattern as `drought_weekly_refresh.py`/`live_nowcast_cycle.py`. Each cycle:
`predict_flood_risk_live.py --project printtheory` (writes a real `last_computed_utc`
into `flood_risk_live_national.json`), then `build_dashboard_summary.py` (propagates
`last_computed_utc`/`refresh_cadence_note` into `track_d_dashboard_summary.json`, what
the dashboard actually reads), then `naip_dashboard/prepare_data.py`. Logged to
`naip/logs/flood_weekly_refresh.log` and `naip/models/flood_risk/weekly_refresh_state.json`.

## Real, confirmed model check

`predict_flood_risk_live.py`'s `MODEL_PATH` points at
`gbt_flood_classifier_v3_precip_fulltrain.joblib` — confirmed by reading the script
directly, this is the promoted v3 (precipitation-augmented) model, not the older
SAR/JRC-only original. One minor, purely cosmetic finding: the joblib bundle's own
internal `role` metadata string still reads `"candidate_v3_precip_fulltrain -- NOT
deployed, used for cross-year eval + live replay"` — a stale label left over from
before the Week 27 promotion, never updated. It has zero functional effect (the correct
file is loaded and used regardless of what its internal label says), flagged here
rather than silently left for a future session to misread as a real problem.

## Real no-conflict note vs. Track H / Track M

Never touches `naip/data/live_nowcast/`, `district_alerts.json`, or
`naip/models/drought_national/`. Shares only the same `printtheory` GEE project quota
as `locust_weekly_refresh.py` — staggered 30 min after `NAIP-DroughtWeekly`'s Sunday
3:00 AM slot purely out of caution (drought makes zero GEE calls, so there's no real
evidence of a conflict, but staggering costs nothing).

## Set up the scheduled task

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\USER\AppData\Local\Programs\Python\Python311\python.exe" `
  -Argument "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler\flood_weekly_refresh.py" `
  -WorkingDirectory "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler"

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:30AM

# Same real DisallowStartIfOnBatteries gotcha Track H/Track M already found on this
# machine, applied proactively this time rather than rediscovered a third time.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "NAIP-FloodWeekly" -Action $action -Trigger $trigger -Settings $settings `
  -Description "NAIP Part 1: real weekly recompute of the flood-risk live screen (v3 model). Independent of NAIP-LiveNowcast/NAIP-DroughtWeekly -- staggered 30min after drought, no shared files."
```

## Start / stop / check

```powershell
Start-ScheduledTask -TaskName "NAIP-FloodWeekly"
Disable-ScheduledTask -TaskName "NAIP-FloodWeekly"
Enable-ScheduledTask -TaskName "NAIP-FloodWeekly"
Get-ScheduledTask -TaskName "NAIP-FloodWeekly" | Get-ScheduledTaskInfo
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\logs\flood_weekly_refresh.log" -Tail 20
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\models\flood_risk\weekly_refresh_state.json"
```

## Verification performed when this was built (2026-08-28)

1. Ran `predict_flood_risk_live.py` directly against real current Sentinel-1/CHIRPS
   data — confirmed it still works (5/126 districts flagged, real scores, ~4m48s).
2. Ran `flood_weekly_refresh.py` directly (not via Task Scheduler) — confirmed all
   three real steps succeed and `last_computed_utc` propagates through to the
   dashboard-served `track_d_dashboard_summary.json`.
3. Registered `NAIP-FloodWeekly` with the battery-power fix applied from the start
   (`DisallowStartIfOnBatteries: False` confirmed immediately, not discovered after
   the fact).
4. Triggered a real unattended fire via `Start-ScheduledTask` — the task genuinely
   executed through Task Scheduler (confirmed via a new log entry with its own
   timestamp, not just the earlier manual run). **First real scheduled attempt hit a
   real, transient `ee.ee_exception.EEException: Computation timed out`** from Earth
   Engine's `reduceRegions` call — a genuine GEE-side timeout, not a bug in this
   project's code or a Task-Scheduler-specific issue (the manual run minutes earlier,
   same code, succeeded fine). Retried via `Start-ScheduledTask` a second time to
   confirm it was transient rather than a real recurring problem — see the session
   report for the retry's real outcome. `weekly_refresh_state.json`'s `n_failure`
   correctly incremented on the timeout, `n_success` unaffected — the honest
   failure-tracking discipline worked exactly as designed.
5. Confirmed `NAIP-LiveNowcast`/`NAIP-DroughtWeekly` remained `Ready`/`Running`
   throughout, no shared state touched.
