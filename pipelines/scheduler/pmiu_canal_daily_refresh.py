#!/usr/bin/env python3
"""
pmiu_canal_daily_refresh.py -- Track V Part 1, real daily refresh of the
PMIU channel-gauge coverage extension (see fetch_pmiu_channel_expansion.py,
CLAUDE.md's Track V entries). Meant to be invoked once a day by Windows Task
Scheduler (task "NAIP-PMIUCanal") -- runs ONE real cycle and exits, same
one-cycle-per-invocation pattern as drought/flood/locust weekly refresh and
the daily regression check.

WHY DAILY, CONFIRMED NOT ASSUMED (see fetch_pmiu_channel_expansion.py's own
docstring for the full real check): PMIU's getTailStatus endpoint holds
exactly one real snapshot at a time -- "yesterday" relative to the actual
current date, refreshed once daily. Any cadence other than daily either
refetches the same unchanged real snapshot (more often) or misses real days
outright, since there is no real backfill/history available from this
endpoint.

REAL NO-CONFLICT NOTE: pure HTTP fetch to PMIU's real WCF service, zero GEE
calls -- shares no real quota with drought/flood/locust weekly refresh
(all GEE-based) or Track H's live nowcast (EUMETSAT-based). Nothing here
touches district_alerts.json, drought_national.json, or flood_risk_live_
national.json.
"""
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
DASHBOARD = r"C:\Users\USER\Downloads\naip_dashboard"

WATER_STRESS_DIR = os.path.join(NAIP, "models", "water_stress")
FETCH_SCRIPT = os.path.join(WATER_STRESS_DIR, "fetch_pmiu_channel_expansion.py")
OUT_JSON = os.path.join(WATER_STRESS_DIR, "pmiu_channel_expansion.json")

LOG_PATH = os.path.join(NAIP, "logs", "pmiu_canal_daily_refresh.log")
STATE_PATH = os.path.join(WATER_STRESS_DIR, "pmiu_daily_refresh_state.json")


def log(msg):
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name, cmd, cwd=None, timeout=180):
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
    log(f"=== PMIU canal daily refresh cycle starting, {started} ===")

    ok = run_step("fetch_pmiu_channel_expansion.py (real PMIU tail-gauge pull)",
                   [sys.executable, FETCH_SCRIPT], cwd=WATER_STRESS_DIR)
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
    n_included = out.get("n_channels_included")

    state["n_success"] += 1
    state["last_success_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    state["last_computed_utc_written"] = last_computed
    state["last_n_channels_included"] = n_included
    save_state(state)
    log(f"=== cycle SUCCESS -- pmiu_channel_expansion.json last_computed_utc={last_computed}, "
        f"n_channels_included={n_included} ===")


if __name__ == "__main__":
    main()
