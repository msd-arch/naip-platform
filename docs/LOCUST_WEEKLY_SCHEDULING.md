# Desert Locust Breeding-Risk Monitor — scheduling setup (Part 2 of "make everything live")

## Why this is weekly, not Track H's 15-minute cadence

`locust_breeding_risk.py` pulls real SMAP soil-moisture and Sentinel-2 NDVI via GEE —
both real but slow-moving signals. The breeding-risk question ("has soil
moisture/vegetation shifted enough over 30 real days to favor egg-laying") is
inherently a weeks-scale question, same real reasoning Track M and the flood screen
use for their own weekly cadence, not a lesser version of Track H's 15-min loop.

## What the job actually does, once per invocation

`naip/pipelines/scheduler/locust_weekly_refresh.py` runs **one real cycle** and exits.
Each cycle: `locust_breeding_risk.py --project printtheory` (writes a real
`last_computed_utc` into `locust_risk.json`), then `naip_dashboard/prepare_data.py`.
Logged to `naip/logs/locust_weekly_refresh.log` and
`naip/models/locust_risk/weekly_refresh_state.json`.

## Real bug found and fixed in the same pass

The dashboard's `LocustRegion` type/JSX (both the Explore view's panel and the legacy
`/locust` page) referenced `vegetation_greenup_detected` — a field name the real
Python script stopped emitting at some earlier point (it now writes
`vegetation_not_browning`, per its own in-code comment: the recalibrated threshold is
"not markedly browning," not true green-up). This silently rendered as `undefined` →
always "No" regardless of the real value. Fixed in both places, and the display label
corrected to match what the threshold actually checks.

## Real no-conflict note

Never touches `naip/data/live_nowcast/`, `district_alerts.json`, or either other
weekly refresh script's output directory. Shares only the same `printtheory` GEE
project quota as `flood_weekly_refresh.py` — staggered a further 30 min after it
(1hr total after `NAIP-DroughtWeekly`).

## Set up the scheduled task

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\USER\AppData\Local\Programs\Python\Python311\python.exe" `
  -Argument "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler\locust_weekly_refresh.py" `
  -WorkingDirectory "C:\Users\USER\Desktop\NASTP\Project\naip\pipelines\scheduler"

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 4:00AM

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "NAIP-LocustWeekly" -Action $action -Trigger $trigger -Settings $settings `
  -Description "NAIP Part 2: real weekly recompute of the desert-locust breeding-risk screen. Independent of NAIP-LiveNowcast/NAIP-DroughtWeekly/NAIP-FloodWeekly."
```

## Start / stop / check

```powershell
Start-ScheduledTask -TaskName "NAIP-LocustWeekly"
Disable-ScheduledTask -TaskName "NAIP-LocustWeekly"
Enable-ScheduledTask -TaskName "NAIP-LocustWeekly"
Get-ScheduledTask -TaskName "NAIP-LocustWeekly" | Get-ScheduledTaskInfo
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\logs\locust_weekly_refresh.log" -Tail 20
Get-Content "C:\Users\USER\Desktop\NASTP\Project\naip\models\locust_risk\weekly_refresh_state.json"
```

## Verification performed when this was built (2026-08-28)

1. Ran `locust_weekly_refresh.py` directly (not via Task Scheduler) — confirmed the
   real SMAP+Sentinel-2 screen still works and `last_computed_utc` is written.
2. Registered `NAIP-LocustWeekly` with the battery-power fix applied from the start.
3. Triggered a real unattended fire via `Start-ScheduledTask` — see the session report
   for the real outcome.
4. Confirmed `NAIP-LiveNowcast`/`NAIP-DroughtWeekly`/`NAIP-FloodWeekly` remained
   `Ready`/`Running` throughout, no shared state touched.
