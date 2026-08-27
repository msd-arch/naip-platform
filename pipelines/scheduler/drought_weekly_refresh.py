#!/usr/bin/env python3
"""
drought_weekly_refresh.py -- Track M's real scheduled refresh. Meant to be
invoked once a week by Windows Task Scheduler (task "NAIP-DroughtWeekly", see
naip/docs/TRACK_M_SCHEDULING.md for setup/start/stop/check) -- like Track H's
live_nowcast_cycle.py, this script runs ONE real cycle and exits; Task
Scheduler provides the repetition, not an internal loop/sleep.

WHY WEEKLY, NOT TRACK H'S 15-MINUTE CADENCE -- stated here, not just in docs:
Track H's 15-min cadence matches MSG/SEVIRI's real ~12-15 min repeat cycle --
polling any less often would miss real new scenes. Track M's real inputs are
different in kind: Sentinel-2 itself only revisits a given point roughly
every 5 real days, and the vegetation/drought trends this signal is meant to
capture develop over weeks, not minutes. A 15-min refresh here would just
re-check data that provably has not changed -- weekly is the real, honest,
appropriate cadence for THIS signal, not a lesser version of Track H's, a
correctly different one for a genuinely different real data-refresh rate.

REAL, HONEST LIMITATION OF THIS FIRST VERSION, STATED PLAINLY: this cycle
re-runs compute_drought_signal.py's real math against the SAME real
current-period Sentinel-2/MODIS extraction Track M was originally built on
(both bound to a fixed Nov 2022-Oct 2023 season, not a rolling window --
confirmed by reading extract_modis_current.py/phenology_features.csv's own
generation code, not assumed). That means the FIRST several real weekly
fires will write an updated last_computed_utc (the pipeline genuinely does
run again) but an IDENTICAL district_results/z_score distribution to the
last run, because the underlying satellite observations have not themselves
been re-extracted for a new season yet. last_computed_utc honestly answers
"when did this computation last run" -- it does NOT yet mean "the underlying
satellite data changed this week." Rebuilding the current-period extraction
itself for a rolling/new-season window is real, separate, larger scope
(a new Sentinel-2 + MODIS GEE pull, matching Track F's own extraction
methodology) -- not attempted here, flagged for a future track rather than
silently implied by this refresh's existence.

REAL, NO-CONFLICT NOTE vs. Track H: this script never touches
naip/data/live_nowcast/ or district_alerts.json, and makes zero GEE/network
calls (compute_drought_signal.py reads only local CSVs already on disk) --
there is no real resource, file-lock, or API-quota overlap with Track H's
15-min MSG download loop, regardless of what time this fires.
"""
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
DASHBOARD = r"C:\Users\USER\Downloads\naip_dashboard"

DROUGHT_DIR = os.path.join(NAIP, "models", "drought_national")
DROUGHT_SCRIPT = os.path.join(DROUGHT_DIR, "compute_drought_signal.py")
DROUGHT_JSON = os.path.join(DROUGHT_DIR, "drought_national.json")
LOG_PATH = os.path.join(NAIP, "logs", "drought_weekly_refresh.log")
STATE_PATH = os.path.join(DROUGHT_DIR, "weekly_refresh_state.json")


def log(msg):
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name, cmd, cwd=None):
    log(f"--- {name} ---")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
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
    log(f"=== drought weekly refresh cycle starting, {started} ===")

    ok = run_step("compute_drought_signal.py (recompute national drought/NDVI signal)",
                   [sys.executable, DROUGHT_SCRIPT], cwd=DROUGHT_DIR)
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (compute step) ===")
        return

    ok = run_step("prepare_data.py (dashboard resync)",
                   [sys.executable, os.path.join(DASHBOARD, "prepare_data.py")])
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (dashboard resync step) ===")
        return

    with open(DROUGHT_JSON, encoding="utf-8") as f:
        out = json.load(f)
    last_computed = out.get("last_computed_utc")

    state["n_success"] += 1
    state["last_success_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    state["last_computed_utc_written"] = last_computed
    save_state(state)
    log(f"=== cycle SUCCESS -- drought_national.json last_computed_utc={last_computed} ===")


if __name__ == "__main__":
    main()
