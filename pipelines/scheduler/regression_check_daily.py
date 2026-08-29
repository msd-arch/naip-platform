#!/usr/bin/env python3
"""
regression_check_daily.py -- Track U step 5: runs naip/validation/
regression_check.py once and records the real result, on the same real
one-cycle-and-exit pattern every scheduled task in this project already
uses (Track H's live_nowcast_cycle.py, drought/flood/locust_weekly_refresh.py)
-- Task Scheduler provides the repetition, this script does not loop/sleep.

WHY DAILY, NOT WEEKLY OR TIED TO TRACK H'S 15-MIN LOOP: most of the files
this check watches refresh weekly (drought/flood/locust) or are updated by
Track H's live loop only when trigger-eval is enabled -- a real 15-min
cadence would just re-check data that provably has not changed and adds
needless noise; a weekly-only cadence risks a silently-stopped scheduled
task going undetected for up to 6 real days. Daily is the real, honest
middle ground for "catch a stale/broken producer within about a day,
without checking data that can't have changed since yesterday."

REAL, NO-CONFLICT NOTE vs. every other scheduled task: this script only
reads naip_dashboard/public/data/*.json (the real files every weekly/live
job already writes) and writes its own report + state files under
naip/validation/ -- no shared write target with Track H, DroughtWeekly,
FloodWeekly, or LocustWeekly, so no file-lock/timing conflict regardless of
what time this fires.
"""
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
VALIDATION_DIR = os.path.join(NAIP, "validation")
CHECK_SCRIPT = os.path.join(VALIDATION_DIR, "regression_check.py")
REPORT_PATH = os.path.join(VALIDATION_DIR, "regression_check_report.json")
LOG_PATH = os.path.join(NAIP, "logs", "regression_check_daily.log")
STATE_PATH = os.path.join(VALIDATION_DIR, "regression_check_state.json")


def log(msg):
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"n_clean": 0, "n_findings": 0, "n_script_error": 0,
             "last_run_utc": None, "last_clean_utc": None, "last_findings_utc": None}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def main():
    state = load_state()
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    log(f"=== regression check cycle starting, {started} ===")
    state["last_run_utc"] = started

    result = subprocess.run(
        [sys.executable, CHECK_SCRIPT], cwd=VALIDATION_DIR,
        capture_output=True, text=True, timeout=120,
    )
    if result.stdout:
        log(result.stdout.strip())
    if result.stderr:
        log(result.stderr.strip())

    if result.returncode not in (0, 1):
        # anything other than a clean run (0) or "real findings reported" (1)
        # means the checker itself crashed -- distinct failure mode, logged
        # separately so it isn't silently folded into "found real findings".
        state["n_script_error"] += 1
        save_state(state)
        log(f"=== cycle FAILED -- regression_check.py itself errored (exit {result.returncode}) ===")
        return

    n_errors = 0
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, encoding="utf-8") as f:
            report = json.load(f)
        n_errors = report.get("n_errors", 0)

    if n_errors:
        state["n_findings"] += 1
        state["last_findings_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log(f"=== cycle FOUND {n_errors} real error(s) -- see {REPORT_PATH} ===")
    else:
        state["n_clean"] += 1
        state["last_clean_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle SUCCESS -- clean, no real schema/freshness errors ===")


if __name__ == "__main__":
    main()
