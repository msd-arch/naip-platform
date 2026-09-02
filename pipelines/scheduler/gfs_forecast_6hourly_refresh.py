#!/usr/bin/env python3
"""
gfs_forecast_6hourly_refresh.py -- real scheduled refresh of Track S1's GFS
forecast layer (frost/heat_wave/cold_wave, 3-day horizon). Meant to be
invoked every 6 hours by Windows Task Scheduler (task "NAIP-GFSForecast") --
runs ONE real cycle and exits, same one-cycle-per-invocation pattern as
drought/flood/locust weekly refresh, the daily regression check, and the
daily PMIU canal refresh.

WHY 6-HOURLY, NOT TRACK H'S 15-MIN CADENCE (checked, not assumed): GFS is a
forecast MODEL, not a continuous observation stream -- NOAA publishes a new
real GFS cycle only 4x/day (00Z/06Z/12Z/18Z), confirmed by this project's
own regression checker, which already flags forecast_alerts.json stale past
30h using this exact real cadence. Running more often than every 6h would
just refetch byte-identical data from the same still-current cycle; MSG's
15-min cadence exists because MSG is a real continuous geostationary
observation stream with genuinely new data every 15 min -- GFS has no
equivalent. gfs_forecast_hazards.py's own find_latest_cycle() already walks
backward safely until it finds a real, actually-published cycle (handles
the "just-issued cycle isn't published yet" case that caused a real 404
the first time this script was run manually, Week 34) -- called here with
no --cycle override, so it self-corrects every real invocation.

REAL NO-CONFLICT NOTE: pure HTTP fetch to NOAA's public AWS Open Data
archive, zero GEE calls -- shares no real quota with the GEE-based weekly
refreshes, and touches only forecast_alerts.json (never district_alerts.json
or any other live-nowcast output).
"""
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
DASHBOARD = r"C:\Users\USER\Downloads\naip_dashboard"

FORECAST_DIR = os.path.join(NAIP, "models", "forecast")
FETCH_SCRIPT = os.path.join(FORECAST_DIR, "gfs_forecast_hazards.py")
OUT_JSON = os.path.join(FORECAST_DIR, "forecast_alerts.json")

LOG_PATH = os.path.join(NAIP, "logs", "gfs_forecast_6hourly_refresh.log")
STATE_PATH = os.path.join(FORECAST_DIR, "gfs_6hourly_refresh_state.json")


def log(msg):
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name, cmd, cwd=None, timeout=300):
    log(f"--- {name} ---")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        log(result.stdout.strip())
    if result.returncode != 0:
        log(f"FAILED ({name}): {result.stderr.strip()}")
        return False
    return True


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"n_success": 0, "n_failure": 0, "last_success_utc": None, "last_failure_utc": None}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def main():
    state = load_state()
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    log(f"=== GFS forecast 6-hourly refresh cycle starting, {started} ===")

    ok = run_step("gfs_forecast_hazards.py (real GFS forecast pull, auto-latest cycle)",
                   [sys.executable, FETCH_SCRIPT], cwd=FORECAST_DIR)
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (fetch step) ===")
        return

    ok = run_step("prepare_data.py (dashboard resync)",
                   [sys.executable, os.path.join(DASHBOARD, "prepare_data.py")])
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (dashboard resync step) ===")
        return

    with open(OUT_JSON, encoding="utf-8") as f:
        out = json.load(f)
    last_computed = out.get("last_computed_utc")
    gfs_cycle = out.get("gfs_cycle_utc")

    state["n_success"] += 1
    state["last_success_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    state["last_computed_utc_written"] = last_computed
    state["last_gfs_cycle_utc"] = gfs_cycle
    save_state(state)
    log(f"=== cycle SUCCESS -- forecast_alerts.json last_computed_utc={last_computed}, "
        f"gfs_cycle_utc={gfs_cycle} ===")


if __name__ == "__main__":
    main()
