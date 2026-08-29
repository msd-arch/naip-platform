#!/usr/bin/env python3
"""
locust_weekly_refresh.py -- Part 2 of "make everything live": real weekly
refresh of the desert-locust breeding-risk screen, same real pattern as
flood_weekly_refresh.py / drought_weekly_refresh.py.

WHY WEEKLY, NOT TRACK H'S 15-MINUTE CADENCE: locust_breeding_risk.py pulls
real SMAP soil-moisture and Sentinel-2 NDVI via GEE, both real but slow-
moving signals -- SMAP L4 is itself a ~3-hourly product but the breeding-risk
question ("has soil moisture/vegetation shifted enough over 30 real days to
favor egg-laying") is inherently a weeks-scale question, not a minutes-scale
one, same real reasoning Track M/flood use for their own weekly cadence.

REAL NO-CONFLICT NOTE: this script never touches naip/data/live_nowcast/,
district_alerts.json, or either of the other two weekly refresh scripts'
output directories. Shares only the same "printtheory" GEE project quota as
flood_weekly_refresh.py -- staggered a further 30 minutes after
NAIP-FloodWeekly (itself 30 min after NAIP-DroughtWeekly) purely out of
caution.
"""
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
DASHBOARD = r"C:\Users\USER\Downloads\naip_dashboard"

LOCUST_DIR = os.path.join(NAIP, "models", "locust_risk")
LOCUST_SCRIPT = os.path.join(LOCUST_DIR, "locust_breeding_risk.py")
LOCUST_JSON = os.path.join(LOCUST_DIR, "locust_risk.json")
DISTRICTS_PATH = os.path.join(NAIP, "data", "seed", "pk_districts.geojson")
GEE_PROJECT = "printtheory"

LOG_PATH = os.path.join(NAIP, "logs", "locust_weekly_refresh.log")
STATE_PATH = os.path.join(LOCUST_DIR, "weekly_refresh_state.json")


def log(msg):
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name, cmd, cwd=None, timeout=600):
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
    log(f"=== locust weekly refresh cycle starting, {started} ===")

    ok = run_step("locust_breeding_risk.py (real SMAP + Sentinel-2 breeding-risk screen)",
                   [sys.executable, LOCUST_SCRIPT, "--project", GEE_PROJECT,
                    "--districts", DISTRICTS_PATH, "--out", LOCUST_JSON],
                   cwd=LOCUST_DIR)
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (locust screen step) ===")
        return

    ok = run_step("prepare_data.py (dashboard resync)",
                   [sys.executable, os.path.join(DASHBOARD, "prepare_data.py")])
    if not ok:
        state["n_failure"] += 1
        state["last_failure_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(state)
        log("=== cycle FAILED (dashboard resync step) ===")
        return

    with open(LOCUST_JSON, encoding="utf-8") as f:
        out = json.load(f)
    last_computed = out.get("last_computed_utc")

    state["n_success"] += 1
    state["last_success_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    state["last_computed_utc_written"] = last_computed
    save_state(state)
    log(f"=== cycle SUCCESS -- locust_risk.json last_computed_utc={last_computed} ===")


if __name__ == "__main__":
    main()
