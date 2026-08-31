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

# ---- Part 3 ("make everything live"): exposure/trigger evaluation, real
# added step after hazard detection. OFF BY DEFAULT (env-var gated, same
# pattern real credentials use throughout this project -- never silently on)
# because this script is Track H's live production loop, already firing
# every ~15 real minutes: saving this file takes effect on the very next
# scheduled fire, so a new step here goes live immediately unless gated.
# Real measured added cost (2026-08-28, against the real, then-current
# 43,218-row merged archive): merge ~1.9s, exposure_risk.py ~4.1s,
# trigger_engine.py x2 (national + demo threshold) ~4.5s + ~4.4s = ~15s
# total -- cheap on its own. The real open question is headroom against
# Task Scheduler's 12-min ExecutionTimeLimit: the last 20 real successful
# cycles ranged 164-696s (mean 328s) BEFORE this step existed -- the 696s
# outlier (driven by export_hazard_grids.py reprocessing a full 8-scene
# rolling window, not by anything this step adds) already leaves only ~24s
# of real margin under the 720s limit. Adding ~15s shrinks that to ~9s on
# the worst-case cycle -- flagged to you rather than enabled silently; set
# NAIP_ENABLE_TRIGGER_EVAL=1 once you've decided how to handle the margin
# (e.g. raising ExecutionTimeLimit) to turn this step on.
ENABLE_TRIGGER_EVAL = os.environ.get("NAIP_ENABLE_TRIGGER_EVAL") == "1"
MERGE_LIVE_HAZARDS_SCRIPT = os.path.join(NAIP, "backend", "alerts", "merge_live_into_hazards_national.py")
NATIONAL_HAZARDS_JSON = os.path.join(NAIP, "backend", "alerts", "hazards_district_national.json")
FUSION_DIR = os.path.join(NAIP, "models", "fusion")
EXPOSURE_SCRIPT = os.path.join(FUSION_DIR, "exposure_risk.py")
EXPOSURE_OUT_JSON = os.path.join(FUSION_DIR, "exposure_risk.json")
EXPOSURE_OUT_CSV = os.path.join(FUSION_DIR, "exposure_risk_top.csv")
TRIGGER_ENGINE_DIR = os.path.join(NAIP, "backend", "insurance_engine")
TRIGGER_ENGINE_SCRIPT = os.path.join(TRIGGER_ENGINE_DIR, "trigger_engine.py")
NATIONAL_THRESHOLD = 0.225
DEMO_THRESHOLD = 0.0216

# WhatsApp automation, real trigger-driven alerts -- gated the same way
# ENABLE_TRIGGER_EVAL is (env var AND a CLI flag baked into the scheduled
# task's own Action, for the same real Windows env-var-inheritance reason
# documented on --enable-trigger-eval below). Off by default: this can
# send a REAL WhatsApp message to a real device, so it must never turn on
# silently just because this file was saved. Real measured added cost
# (2026-08-31, against the real current audit logs, 0 national + 1
# Gujranwala-demo candidate, one real failed send attempt due to an
# expired token): ~1.5s -- negligible against Part 3's own ~15s and the
# 900s ExecutionTimeLimit headroom established for Part 3 itself.
ENABLE_WHATSAPP_NOTIFY = os.environ.get("NAIP_ENABLE_WHATSAPP_NOTIFY") == "1"
WHATSAPP_DIR = os.path.join(NAIP, "delivery", "sms_ussd_ivr")
WHATSAPP_NOTIFY_SCRIPT = os.path.join(WHATSAPP_DIR, "whatsapp_notify.py")
AUDIT_LOG_NATIONAL = os.path.join(TRIGGER_ENGINE_DIR, "audit_log_national.jsonl")
AUDIT_LOG_DEMO = os.path.join(TRIGGER_ENGINE_DIR, "audit_log_demo.jsonl")
WHATSAPP_DELIVERY_LOG = os.path.join(WHATSAPP_DIR, "delivery_log.jsonl")

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


def run_trigger_eval_step():
    """Part 3: fold this cycle's live hazard alerts into the archive
    exposure_risk.py/trigger_engine.py actually score against, then re-run
    both -- reusing whatever crop-weight data currently exists in
    real_crop_mix.json (a static file, read not recomputed; it only changes
    when a new real MNFSR report or a Track F model retrain happens, weekly
    at most, effectively annual for real government data -- re-deriving it
    every 15 real minutes against unchanged inputs would be real wasted
    compute). Returns real wall-clock seconds spent, for cycle-time logging."""
    t0 = dt.datetime.now()

    run_step("merge_live_into_hazards_national.py (Part 3: fold live alerts into scoring archive)",
              ["python", MERGE_LIVE_HAZARDS_SCRIPT])

    run_step("exposure_risk.py (Part 3)",
              ["python", EXPOSURE_SCRIPT, "--hazards-json", NATIONAL_HAZARDS_JSON,
               "--out", EXPOSURE_OUT_JSON, "--out-csv", EXPOSURE_OUT_CSV])

    # Track R cutover: trigger_engine.py now matches farms against the real
    # live database itself (db_registry.py) -- no --farms-geojson/
    # --districts-geojson args anymore. If the DB is unreachable this raises
    # inside trigger_engine.py, run_step() surfaces it as a real failure with
    # the real traceback in the log, and the outer try/except around this
    # whole function logs it clearly without crashing the core hazard cycle
    # -- loud and visible, never a silent revert to a stand-in.
    run_step("trigger_engine.py (Part 3, national/illustrative threshold)",
              ["python", TRIGGER_ENGINE_SCRIPT,
               "--hazards-json", NATIONAL_HAZARDS_JSON,
               "--out-audit", os.path.join(TRIGGER_ENGINE_DIR, "audit_log_national.jsonl"),
               "--out-summary", os.path.join(TRIGGER_ENGINE_DIR, "trigger_summary_national.json"),
               "--threshold", str(NATIONAL_THRESHOLD)])

    run_step("trigger_engine.py (Part 3, demo threshold)",
              ["python", TRIGGER_ENGINE_SCRIPT,
               "--hazards-json", NATIONAL_HAZARDS_JSON,
               "--out-audit", os.path.join(TRIGGER_ENGINE_DIR, "audit_log_demo.jsonl"),
               "--out-summary", os.path.join(TRIGGER_ENGINE_DIR, "trigger_summary_demo.json"),
               "--threshold", str(DEMO_THRESHOLD)])

    # WhatsApp automation: real, automatic sends for real qualifying
    # trigger events, right after trigger evaluation as required. Own gate
    # (ENABLE_WHATSAPP_NOTIFY), separate from ENABLE_TRIGGER_EVAL -- this
    # can send a real message, trigger evaluation alone cannot, so being
    # able to run Part 3 (dashboard scoring) without WhatsApp turned on is
    # a real, deliberate degree of freedom, not an oversight. Real
    # dedup/cap/failure-handling all live inside whatsapp_notify.py itself
    # (its own module docstring); this call just wires it into the cycle.
    # Its own failures are handled internally and logged (never raised),
    # so a send failure here surfaces in the log without this run_step()
    # treating it as a Part 3 failure -- only a genuine crash would.
    if ENABLE_WHATSAPP_NOTIFY:
        run_step("whatsapp_notify.py (Part 3: real trigger-driven WhatsApp alerts)",
                  ["python", WHATSAPP_NOTIFY_SCRIPT,
                   "--national-audit", AUDIT_LOG_NATIONAL,
                   "--demo-audit", AUDIT_LOG_DEMO,
                   "--delivery-log", WHATSAPP_DELIVERY_LOG])
    else:
        log("  whatsapp_notify.py: SKIPPED (NAIP_ENABLE_WHATSAPP_NOTIFY not set / "
            "--enable-whatsapp-notify not passed)")

    # a second resync -- the first prepare_data.py call (in main(), before
    # this function runs) already happened for the hazard/district_alerts
    # update; exposure_risk.json/audit_log_*.json need their own pass so a
    # new trigger event appears on the dashboard without manual intervention.
    run_step("prepare_data.py (Part 3 dashboard resync)",
              ["python", os.path.join(DASHBOARD, "prepare_data.py")])

    return (dt.datetime.now() - t0).total_seconds()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-latency-hours", type=float, default=MIN_LATENCY_HOURS)
    ap.add_argument("--enable-trigger-eval", action="store_true",
                     help="Part 3: also run exposure/trigger evaluation after hazard "
                          "detection. Same real gate as NAIP_ENABLE_TRIGGER_EVAL=1 -- "
                          "a CLI flag baked into the scheduled task's own Action is used "
                          "instead of relying on that env var for the real production "
                          "task, because a User-scope env var set via PowerShell did NOT "
                          "propagate to Task Scheduler's spawned process on a real test "
                          "(confirmed 2026-08-28: a real unattended fire completed with "
                          "no Part 3 log lines at all despite the var being set) -- a "
                          "real, concrete Windows env-var-inheritance gotcha, not assumed "
                          "away. The env var still works for ad-hoc manual runs.")
    ap.add_argument("--enable-whatsapp-notify", action="store_true",
                     help="Part 3: also send real WhatsApp alerts for real qualifying "
                          "trigger events (see whatsapp_notify.py). Same real "
                          "CLI-flag-baked-into-the-task's-own-Action reason as "
                          "--enable-trigger-eval -- a User-scope env var alone did not "
                          "survive into Task Scheduler's spawned process on a real test. "
                          "Requires --enable-trigger-eval (or its env var) too, since "
                          "there's nothing to notify on without Part 3's own trigger "
                          "evaluation having just run.")
    a = ap.parse_args()
    global ENABLE_TRIGGER_EVAL, ENABLE_WHATSAPP_NOTIFY
    ENABLE_TRIGGER_EVAL = ENABLE_TRIGGER_EVAL or a.enable_trigger_eval
    ENABLE_WHATSAPP_NOTIFY = ENABLE_WHATSAPP_NOTIFY or a.enable_whatsapp_notify

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

        # Part 3, isolated from the core hazard-detection guarantee above:
        # this scene is already marked processed regardless of what happens
        # here, so a Part 3 failure never costs Track H's own real
        # historical continuity (same principle as everything else in this
        # script -- one real failure doesn't wedge the whole loop).
        if ENABLE_TRIGGER_EVAL:
            try:
                trigger_dur = run_trigger_eval_step()
                log(f"  Part 3 (exposure/trigger eval): OK ({trigger_dur:.0f}s)")
            except Exception as e:
                log(f"  Part 3 (exposure/trigger eval): FAILED, not fatal to this cycle: {e}")

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
