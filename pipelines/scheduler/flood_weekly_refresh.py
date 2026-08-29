#!/usr/bin/env python3
"""
flood_weekly_refresh.py -- Part 1 of "make everything live": real weekly
refresh of the flood-risk screen, same real pattern Track M established for
drought (see drought_weekly_refresh.py, naip/docs/TRACK_M_SCHEDULING.md).
Meant to be invoked once a week by Windows Task Scheduler (task
"NAIP-FloodWeekly") -- runs ONE real cycle and exits, Task Scheduler
provides the repetition, not an internal loop/sleep.

WHY WEEKLY, NOT TRACK H'S 15-MINUTE CADENCE: unlike drought's real
limitation (its current-period Sentinel-2/MODIS extraction is frozen to a
fixed season), predict_flood_risk_live.py genuinely recomputes its
during_window/pre_monsoon_baseline_window fresh from today's real date on
every run, and DOES pull live Sentinel-1/CHIRPS data via GEE each time -- so
in principle this signal changes more often than drought's. It is NOT run at
Track H's 15-min cadence anyway, for a different real reason: it makes a
real, several-minute GEE network call across 126 districts x 15 points each
(measured: ~4m48s end to end) -- a 15-min cadence would spend roughly a
third of every cycle on a screen whose real underlying SAR/precipitation
signal (a rolling 30-day window) does not meaningfully change minute to
minute. Weekly is the real, appropriate cadence for this signal's true
refresh rate, not a lesser version of Track H's.

REAL NO-CONFLICT NOTE vs. Track H and Track M: this script never touches
naip/data/live_nowcast/, district_alerts.json, or naip/models/drought_national/
-- the only real resource it shares with anything is its own GEE project
quota (same "printtheory" project Track H's own hazard pipeline does NOT
use -- Track H is pure MSG/EUMETSAT, no GEE calls at all). Staggered 30
minutes after NAIP-DroughtWeekly's Sunday 3:00 AM slot purely out of caution
(no real evidence they'd conflict -- drought makes zero GEE/network calls --
but staggering costs nothing and removes any doubt).
"""
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
DASHBOARD = r"C:\Users\USER\Downloads\naip_dashboard"

FLOOD_DIR = os.path.join(NAIP, "models", "flood_risk")
PREDICT_SCRIPT = os.path.join(FLOOD_DIR, "predict_flood_risk_live.py")
BUILD_SUMMARY_SCRIPT = os.path.join(FLOOD_DIR, "build_dashboard_summary.py")
LIVE_SCREEN_JSON = os.path.join(FLOOD_DIR, "flood_risk_live_national.json")
GEE_PROJECT = "printtheory"

LOG_PATH = os.path.join(NAIP, "logs", "flood_weekly_refresh.log")
STATE_PATH = os.path.join(FLOOD_DIR, "weekly_refresh_state.json")


def log(msg):
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name, cmd, cwd=None, timeout=900):
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
    log(f"=== flood weekly refresh cycle starting, {started} ===")

    ok = run_step("predict_flood_risk_live.py (real Sentinel-1/JRC/CHIRPS live screen, v3 model)",
                   [sys.executable, PREDICT_SCRIPT, "--project", GEE_PROJECT], cwd=FLOOD_DIR)
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (predict step) ===")
        return

    ok = run_step("build_dashboard_summary.py (real dashboard-ready summary)",
                   [sys.executable, BUILD_SUMMARY_SCRIPT], cwd=FLOOD_DIR)
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (dashboard summary step) ===")
        return

    ok = run_step("prepare_data.py (dashboard resync)",
                   [sys.executable, os.path.join(DASHBOARD, "prepare_data.py")])
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (dashboard resync step) ===")
        return

    with open(LIVE_SCREEN_JSON, encoding="utf-8") as f:
        out = json.load(f)
    last_computed = out.get("last_computed_utc")

    state["n_success"] += 1
    state["last_success_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    state["last_computed_utc_written"] = last_computed
    save_state(state)
    log(f"=== cycle SUCCESS -- flood_risk_live_national.json last_computed_utc={last_computed} ===")


if __name__ == "__main__":
    main()
