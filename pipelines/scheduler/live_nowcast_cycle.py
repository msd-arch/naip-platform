#!/usr/bin/env python3
"""
live_nowcast_cycle.py -- Phase 4 Track H: one real cycle of the live nowcasting
loop. Meant to be invoked repeatedly by Windows Task Scheduler (see
naip/docs/TRACK_H_SCHEDULING.md for setup/start/stop/check instructions) --
this script does not loop or sleep itself, one process invocation = one cycle.

REAL LIMITATION, STATED HERE AND NOT JUST IN THE DOCS: this runs on a personal
Windows machine, not a server. The schedule only fires while this machine is
on, awake, and not otherwise blocked -- there is no guaranteed uptime, no
retry-on-a-different-host, no SLA. Every log line and the pipeline_health.json
this writes carries that same caveat forward, so nothing downstream implies
production-grade reliability that doesn't exist.

REAL PIPELINE, ORCHESTRATION ONLY -- NO DETECTOR LOGIC CHANGED:
  1. eumdac search for the latest real MSG3 HRSEVIRI scene at least
     MIN_LATENCY_HOURS old (see the licence note below).
  2. Download + unzip that one real scene into a rolling live nat_in/ dir.
  3. export_hazard_grids.py, then export_skin_temp.py (unchanged scripts) --
     the manifest naturally rebuilds over whatever scenes are currently in
     the rolling nat_in/ dir, see PRUNE_KEEP_LAST below.
  4. hazards.py --locations districts (unchanged) -- this already attaches
     Track E's real fire model_score internally (Week 9/Track G wiring),
     nothing extra needed here for that.
  5. district_aggregate.py (unchanged) -- produces a live-only hazards/
     district-alerts pair.
  6. Merge the live district-day-hazard rows into the REAL production
     naip/backend/alerts/district_alerts.json by upserting on
     (district, date, hazard) -- this EXTENDS the real feed forward with a
     new live date, it does not touch or remove any historical
     Week-1-archive row the rest of the product (demo scenario, trigger
     engine, exposure risk) depends on.
  7. Resync the dashboard (naip_dashboard/prepare_data.py, unchanged) and
     write pipeline_health.json so the dashboard can show real liveness.

REAL LICENCE NOTE: the EUMETSAT NRT licence returned a real, specific 403
("NRTLicense required to access this collection") on the first API test
during this track's build, despite being accepted and browsable in the Data
Store web UI -- a genuine web-vs-API authorization propagation delay, not a
permanent block. A single bounded 45-minute wait-and-retry (per direction)
came back 200 -- real access confirmed, but only down to a real empirically-
bracketed ~30 minute minimum latency (a scene 32 min old downloaded fine; one
17 min old still 403'd; nothing newer existed yet to narrow it further in
that session). MIN_LATENCY_HOURS reflects that real bracket with a safety
margin, not the ideal sub-15-min case -- see naip/docs/STATUS_WEEK13.md.
"""
import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
HAZARDS_SCRIPTS = r"C:\Users\USER\Downloads\hazards_scripts"
DASHBOARD = r"C:\Users\USER\Downloads\naip_dashboard"

LIVE_DIR = os.path.join(NAIP, "data", "live_nowcast")
NAT_DIR = os.path.join(LIVE_DIR, "nat_in")
WEB_DATA_DIR = os.path.join(LIVE_DIR, "web_data")
LIVE_HAZARDS_JSON = os.path.join(LIVE_DIR, "hazards_district_live.json")
LIVE_ALERTS_JSON = os.path.join(LIVE_DIR, "district_alerts_live.json")
LIVE_ALERTS_CSV = os.path.join(LIVE_DIR, "district_alerts_live.csv")
STATE_PATH = os.path.join(LIVE_DIR, "cycle_state.json")

MASTER_ALERTS_JSON = os.path.join(NAIP, "backend", "alerts", "district_alerts.json")
MASTER_ALERTS_CSV = os.path.join(NAIP, "backend", "alerts", "district_alerts.csv")
DISTRICTS_GEOJSON = os.path.join(NAIP, "data", "seed", "pk_districts.geojson")

LOG_PATH = os.path.join(NAIP, "logs", "live_nowcast.log")
HEALTH_OUT = os.path.join(DASHBOARD, "public", "data", "pipeline_health.json")
LOCK_PATH = os.path.join(LIVE_DIR, "cycle.lock")

# Real bug found live during the Week 13 observation window: a cycle suspended
# mid-run by the machine sleeping (not killed, just paused) can still be
# "running" when a later scheduled cycle starts after wake -- both then race
# on export_hazard_grids.py's shared _hazard_grid_tmp dir (one process's
# unconditional cleanup rmtree deletes files the other is still writing),
# producing a real FileNotFoundError. Task Scheduler's own MultipleInstances
# protection doesn't catch this because the suspended process was never
# actually killed. STALE_LOCK_MINUTES is generous -- well beyond any real
# cycle's worst-case duration at the PRUNE_KEEP_LAST cap -- so a lock is only
# ever taken over from a process that's genuinely gone, not one still working.
STALE_LOCK_MINUTES = 20

# Real, confirmed-working default -- REVISED during the Week 13 observation
# window after 0.6h (36min) produced two real, consecutive 403s on scenes at
# ~40min old. Full real bracket observed: 33min=200, 40min=403, 42min=403,
# 57min=200 (same scene, re-tested older), 58min=200 -- the ~30-45min zone is
# genuinely unstable/inconsistent, not a clean deterministic threshold
# (naip/docs/STATUS_WEEK13.md has the full real timeline). 1.0h clears the
# observed unstable zone with margin while still beating the 3.25h archive
# tier substantially. Override with --min-latency-hours.
MIN_LATENCY_HOURS = 1.0

# Reprocessing cost scales with how many .nat files sit in NAT_DIR (every
# cycle reruns export_hazard_grids.py/export_skin_temp.py over ALL of them,
# unchanged scripts, not something this orchestrator can partially rerun) --
# so the rolling window is capped. REVISED during real unattended operation
# (naip/docs/STATUS_WEEK13.md): the original cap of 24 let real per-cycle
# time grow past ~18 minutes (measured: export_hazard_grids.py alone took
# 388s at 20 files) -- past both the 10-min Task Scheduler ExecutionTimeLimit
# (silently killing legit in-progress cycles, no exception, no log line,
# looked identical to a hang) and uncomfortably close to the 15-min cadence
# itself. 8 keeps real total cycle time to roughly 5-6 minutes even at the
# cap -- comfortable margin under both.
PRUNE_KEEP_LAST = 8

WINDOWS_UPTIME_CAVEAT = (
    "This pipeline only runs while this personal Windows machine is on, "
    "awake, and Task Scheduler fires -- there is no server-grade uptime "
    "guarantee, no failover host. A gap in cycles most likely means the "
    "machine was off/asleep, not a silent pipeline failure -- check the log "
    "for the real reason either way."
)


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat()}  {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def acquire_lock():
    """Returns True if this process now holds the lock. A stale lock (older
    than STALE_LOCK_MINUTES -- a process that died/was suspended without
    cleaning up, e.g. the machine slept mid-cycle) is taken over, not
    respected forever -- otherwise one bad cycle would permanently wedge the
    whole loop, which is exactly the "no manual intervention required"
    guarantee this script exists to provide."""
    if os.path.exists(LOCK_PATH):
        age_min = (dt.datetime.now().timestamp() - os.path.getmtime(LOCK_PATH)) / 60.0
        if age_min < STALE_LOCK_MINUTES:
            return False
        log(f"found a stale lock ({age_min:.0f} min old, likely a cycle suspended by "
            "machine sleep, not cleanly finished) -- taking over")
    os.makedirs(LIVE_DIR, exist_ok=True)
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    try:
        os.remove(LOCK_PATH)
    except FileNotFoundError:
        pass


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"processed_scene_ids": [], "last_success_utc": None, "last_success_scene": None,
            "n_success": 0, "n_failure": 0, "n_no_new_scene": 0}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def find_latest_scene(min_latency_hours):
    """Real eumdac search, filtered to scenes old enough for the licence tier
    that's actually authorized -- deterministic, not a doomed-download retry
    loop against a tier we already know 403s."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=min_latency_hours)
    window_start = now - dt.timedelta(hours=min_latency_hours + 2)
    cmd = ["eumdac", "search", "-c", "EO:EUM:DAT:MSG:HRSEVIRI",
           "--start", window_start.strftime("%Y-%m-%dT%H:%M"),
           "--end", cutoff.strftime("%Y-%m-%dT%H:%M")]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    ids = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    if not ids:
        return None
    ids.sort()  # product IDs are timestamp-prefixed -- last is most recent
    return ids[-1]


def download_scene(product_id):
    os.makedirs(NAT_DIR, exist_ok=True)
    result = subprocess.run(
        ["eumdac", "download", "-c", "EO:EUM:DAT:MSG:HRSEVIRI", "-p", product_id,
         "-o", NAT_DIR, "-y"],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0 or "Unauthorised" in result.stdout or "didn't finish" in result.stdout:
        raise RuntimeError(f"eumdac download failed: {result.stdout[-500:]} {result.stderr[-500:]}")
    zip_path = os.path.join(NAT_DIR, f"{product_id}.zip")
    if not os.path.exists(zip_path):
        raise RuntimeError(f"expected zip not found after download: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        nat_names = [n for n in zf.namelist() if n.endswith(".nat")]
        if not nat_names:
            raise RuntimeError(f"no .nat file inside {zip_path}")
        zf.extract(nat_names[0], NAT_DIR)
    os.remove(zip_path)
    for extra in glob.glob(os.path.join(NAT_DIR, "*.xml")):
        os.remove(extra)
    return os.path.join(NAT_DIR, nat_names[0])


def prune_nat_dir(keep_last):
    files = sorted(glob.glob(os.path.join(NAT_DIR, "*.nat")))
    if len(files) > keep_last:
        for f in files[:-keep_last]:
            os.remove(f)
            log(f"pruned old scene from rolling window: {os.path.basename(f)}")


def run_step(name, cmd, timeout=600):
    t0 = dt.datetime.now()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    dur = (dt.datetime.now() - t0).total_seconds()
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed (exit {result.returncode}, {dur:.0f}s): {result.stdout[-800:]} {result.stderr[-800:]}")
    log(f"  {name}: OK ({dur:.0f}s)")
    return dur


def merge_live_into_master(live_alerts_path, master_path, master_csv_path):
    """Upsert on (district, date, hazard) -- extends the real feed forward
    with the live date's rows, never touches or removes a historical row."""
    with open(live_alerts_path, encoding="utf-8") as f:
        live = json.load(f)
    with open(master_path, encoding="utf-8") as f:
        master = json.load(f)

    live_rows = live["district_day_hazard_rows"]
    live_keys = {(r["district"], r["date"], r["hazard"]) for r in live_rows}
    master_rows = [r for r in master["district_day_hazard_rows"]
                   if (r["district"], r["date"], r["hazard"]) not in live_keys]
    master_rows.extend(live_rows)
    master_rows.sort(key=lambda r: (r["district"], r["date"], r["hazard"]))
    master["district_day_hazard_rows"] = master_rows

    live_days = set(live.get("period", {}).get("days", []))
    days = set(master.get("period", {}).get("days", [])) | live_days
    master["period"] = {"days": sorted(days)}
    master["n_districts"] = len({r["district"] for r in master_rows})

    live_note_marker = "Track H live nowcasting loop"
    master["coverage_notes"] = [n for n in master.get("coverage_notes", [])
                                 if live_note_marker not in n]
    master["coverage_notes"].append(
        f"{live_note_marker}: {sorted(live_days)} added/refreshed from real live MSG scenes "
        f"(>{MIN_LATENCY_HOURS}hr archive tier, NRT blocked -- see live_nowcast.log), "
        "merged additively by (district, date, hazard) -- historical Week 1-11 archive "
        "rows untouched. " + WINDOWS_UPTIME_CAVEAT
    )

    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    import csv
    with open(master_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(master_rows[0].keys()))
        w.writeheader()
        for r in master_rows:
            w.writerow(r)

    return len(live_rows)


def write_health(status, detail, duration_s, state, scene_id=None):
    os.makedirs(os.path.dirname(HEALTH_OUT), exist_ok=True)
    payload = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "detail": detail,
        "last_cycle_duration_seconds": round(duration_s, 1) if duration_s is not None else None,
        "last_scene_processed": scene_id,
        "last_success_utc": state.get("last_success_utc"),
        "last_success_scene": state.get("last_success_scene"),
        "n_success": state.get("n_success", 0),
        "n_failure": state.get("n_failure", 0),
        "n_no_new_scene": state.get("n_no_new_scene", 0),
        "min_latency_hours_tier": MIN_LATENCY_HOURS,
        "windows_uptime_caveat": WINDOWS_UPTIME_CAVEAT,
    }
    with open(HEALTH_OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-latency-hours", type=float, default=MIN_LATENCY_HOURS)
    a = ap.parse_args()

    if not acquire_lock():
        log("another cycle appears to still be running (lock held, < "
            f"{STALE_LOCK_MINUTES}min old) -- skipping this fire, normal, not an error")
        return 0

    state = load_state()
    t_start = dt.datetime.now()
    log("=== cycle start ===")

    try:
        scene_id = find_latest_scene(a.min_latency_hours)
        if scene_id is None:
            state["n_no_new_scene"] += 1
            save_state(state)
            log("no real scene found in the searched window -- normal, not an error")
            write_health("no_new_scene", "no real scene available this cycle", 0.0, state)
            return 0
        if scene_id in state["processed_scene_ids"]:
            state["n_no_new_scene"] += 1
            save_state(state)
            log(f"latest available scene {scene_id} already processed -- normal, waiting for next real scene")
            write_health("no_new_scene", f"latest scene {scene_id} already processed", 0.0, state)
            return 0

        log(f"new real scene found: {scene_id}")
        download_scene(scene_id)
        log("  download+unzip: OK")
        prune_nat_dir(PRUNE_KEEP_LAST)

        run_step("export_hazard_grids.py",
                  ["python", os.path.join(HAZARDS_SCRIPTS, "export_hazard_grids.py"),
                   "--nat-dir", NAT_DIR, "--out", os.path.join(WEB_DATA_DIR, "msg_hazard")])
        run_step("export_skin_temp.py",
                  ["python", os.path.join(HAZARDS_SCRIPTS, "export_skin_temp.py"),
                   "--nat-dir", NAT_DIR, "--out", os.path.join(WEB_DATA_DIR, "msg_hazard")])
        run_step("hazards.py",
                  ["python", os.path.join(HAZARDS_SCRIPTS, "hazards.py"),
                   "--web-data", WEB_DATA_DIR, "--locations", "districts",
                   "--districts", DISTRICTS_GEOJSON, "--out", LIVE_HAZARDS_JSON])
        run_step("district_aggregate.py",
                  ["python", os.path.join(NAIP, "backend", "alerts", "district_aggregate.py"),
                   "--hazards-json", LIVE_HAZARDS_JSON,
                   "--out-json", LIVE_ALERTS_JSON, "--out-csv", LIVE_ALERTS_CSV])

        n_merged = merge_live_into_master(LIVE_ALERTS_JSON, MASTER_ALERTS_JSON, MASTER_ALERTS_CSV)
        log(f"  merge into master district_alerts.json: OK ({n_merged} real rows upserted)")

        run_step("prepare_data.py (dashboard resync)",
                  ["python", os.path.join(DASHBOARD, "prepare_data.py")])

        state["processed_scene_ids"] = (state["processed_scene_ids"] + [scene_id])[-200:]
        state["last_success_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        state["last_success_scene"] = scene_id
        state["n_success"] += 1
        save_state(state)

        dur = (dt.datetime.now() - t_start).total_seconds()
        log(f"=== cycle SUCCESS: {scene_id}, {dur:.0f}s total ===")
        write_health("ok", f"processed {scene_id}", dur, state, scene_id)
        return 0

    except Exception as e:
        dur = (dt.datetime.now() - t_start).total_seconds()
        state["n_failure"] += 1
        save_state(state)
        log(f"=== cycle FAILED after {dur:.0f}s: {e} ===")
        write_health("error", str(e)[:500], dur, state)
        return 1

    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
