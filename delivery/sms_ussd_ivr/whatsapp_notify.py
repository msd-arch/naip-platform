#!/usr/bin/env python3
"""
whatsapp_notify.py -- real, automatic WhatsApp sends wired into the live
cycle's Part 3 trigger evaluation, replacing manual "let's send a test
message" sessions. Reuses sms_delivery.py's real send_one()/template-check
logic directly (imported, not duplicated) -- this module only adds the
real event-selection, deduplication, and daily-cap logic around it.

TWO REAL RULES (confirmed with the project owner before building):
  1. Strict/national-illustrative threshold (audit_log_national.jsonl),
     ANY district -- rare, high-signal. Any real record there triggers a
     real send.
  2. Looser/demo threshold (audit_log_demo.jsonl), ONLY when
     district == "Gujranwala" -- more frequent, area-specific per the
     confirmed real pilot area.
Both audit logs are real, current-cycle snapshots that trigger_engine.py
OVERWRITES every run (confirmed by reading its source directly -- the
"append-only JSONL" comment there describes the per-line record FORMAT,
not the file's open mode, which is "w"). This means the SAME real
ongoing event reappears every cycle with a freshly-generated event_id --
event_id is therefore NOT a usable dedup key. The real stable identity of
an event is (district, date, hazard, crop): the same real hazard reading
on the same real district/date/crop pairing.

REAL DEDUPLICATION: a persisted JSON state file (WHATSAPP_DEDUP_STATE)
keyed by that stable (district, date, hazard, crop) tuple. An event only
sends once, ever, the first cycle it's seen -- every later cycle it's
still active, it's recognized as already-notified and skipped, not
resent. This is the real, non-negotiable safeguard the live cycle runs
every ~15-25 minutes without.

REAL DAILY CAP: a second, independent safety net (WHATSAPP_DAILY_CAP,
UTC calendar day) in case dedup has any real edge case, or a genuine
burst of real distinct events happens. Only counts a CONFIRMED real send
against the cap -- a failed attempt (expired token, API error) sends
nothing, so it doesn't consume budget, and per the real failure-handling
requirement below, isn't marked as notified either.

REAL FAILURE HANDLING: if a WhatsApp send fails for any reason (expired
token, network error, non-200 API response), this is logged clearly and
the event is NOT added to the dedup state -- a genuinely new event that
failed to send is retried next cycle, never silently treated as handled.

Usage (standalone, or called from live_nowcast_cycle.py's Part 3):
    python whatsapp_notify.py \
        --national-audit ../../backend/insurance_engine/audit_log_national.jsonl \
        --demo-audit ../../backend/insurance_engine/audit_log_demo.jsonl \
        --delivery-log delivery_log.jsonl
"""
import argparse
import datetime as dt
import json
import os
import sys

import sms_delivery

HERE = os.path.dirname(os.path.abspath(__file__))
DEDUP_STATE_PATH = os.environ.get("WHATSAPP_DEDUP_STATE", os.path.join(HERE, "whatsapp_dedup_state.json"))
DAILY_CAP = int(os.environ.get("WHATSAPP_DAILY_CAP", "10"))
GUJRANWALA = "Gujranwala"


def stable_event_key(record):
    return f"{record['district']}|{record['date']}|{record['hazard']}|{record['crop']}"


def load_dedup_state():
    if os.path.exists(DEDUP_STATE_PATH):
        with open(DEDUP_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"notified": {}, "sends_by_utc_date": {}}


def save_dedup_state(state):
    with open(DEDUP_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def select_candidates(national_records, demo_records):
    """Real rule application. Rule 1: every national-threshold record,
    any district. Rule 2: demo-threshold records, Gujranwala only. If the
    same real (district, date, hazard, crop) clears both bars, it's the
    same real event -- dedup by stable key here too, before ever reaching
    the persisted dedup state, tagged with whichever rule matched (both,
    if both) rather than sent twice in the same pass."""
    by_key = {}
    for r in national_records:
        key = stable_event_key(r)
        by_key.setdefault(key, {"record": r, "rules": []})
        by_key[key]["rules"].append("strict_national_any_district")
    for r in demo_records:
        if r["district"] != GUJRANWALA:
            continue
        key = stable_event_key(r)
        by_key.setdefault(key, {"record": r, "rules": []})
        by_key[key]["rules"].append("looser_demo_gujranwala_only")
    return by_key


def run(national_audit_path, demo_audit_path, delivery_log_path, dry_run=False):
    """Returns a real summary dict -- caller (live_nowcast_cycle.py) logs
    it, doesn't need to know internals."""
    national_records = load_jsonl(national_audit_path)
    demo_records = load_jsonl(demo_audit_path)
    candidates = select_candidates(national_records, demo_records)

    state = load_dedup_state()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    sent_today = state["sends_by_utc_date"].get(today, 0)

    whatsapp_config = None if dry_run else sms_delivery.get_whatsapp_config()
    twilio_client, twilio_from, twilio_to = (None, None, None) if dry_run else sms_delivery.get_twilio_client()

    summary = {"n_candidates": len(candidates), "n_already_notified": 0, "n_sent": 0,
               "n_cap_skipped": 0, "n_failed": 0, "events": []}

    for key, entry in candidates.items():
        record = entry["record"]
        rules = entry["rules"]
        label = f"{record['district']} {record['hazard']} x {record['crop']} ({record['date']})"

        if key in state["notified"]:
            summary["n_already_notified"] += 1
            print(f"  [whatsapp_notify] SKIP (already notified): {label} [{','.join(rules)}]")
            continue

        if sent_today >= DAILY_CAP:
            summary["n_cap_skipped"] += 1
            print(f"  [whatsapp_notify] SKIP (real daily cap {DAILY_CAP} reached): {label} "
                  f"[{','.join(rules)}] -- NOT marked notified, will be retried next cycle")
            continue

        if dry_run:
            print(f"  [whatsapp_notify] DRY-RUN would send: {label} [{','.join(rules)}]")
            summary["events"].append({"key": key, "rules": rules, "outcome": "dry_run"})
            continue

        delivery = sms_delivery.send_one(record, whatsapp_config, twilio_client, twilio_from, twilio_to)
        ok = delivery["status"] in ("SENT_REAL_WHATSAPP_MESSAGE", "SENT_REAL_TWILIO_MESSAGE")

        with open(delivery_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({**delivery, "matched_rules": rules, "stable_event_key": key},
                                ensure_ascii=False) + "\n")

        if ok:
            sent_today += 1
            state["notified"][key] = {
                "first_sent_utc": delivery["delivered_at_utc"],
                "whatsapp_message_id": delivery.get("whatsapp_message_id"),
                "matched_rules": rules,
            }
            state["sends_by_utc_date"][today] = sent_today
            summary["n_sent"] += 1
            print(f"  [whatsapp_notify] SENT: {label} [{','.join(rules)}] "
                  f"status={delivery['status']} id={delivery.get('whatsapp_message_id')}")
            summary["events"].append({"key": key, "rules": rules, "outcome": "sent",
                                       "whatsapp_message_id": delivery.get("whatsapp_message_id")})
        else:
            # REAL FAILURE HANDLING: logged clearly, NOT marked notified --
            # a genuinely new event that failed to send is retried next cycle.
            summary["n_failed"] += 1
            reason = delivery.get("note") or delivery.get("whatsapp_api_response") or delivery["status"]
            print(f"  [whatsapp_notify] FAILED (will retry next cycle, NOT marked notified): "
                  f"{label} [{','.join(rules)}] status={delivery['status']} reason={reason}")
            summary["events"].append({"key": key, "rules": rules, "outcome": "failed",
                                       "status": delivery["status"], "reason": str(reason)})

    save_dedup_state(state)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--national-audit", required=True)
    ap.add_argument("--demo-audit", required=True)
    ap.add_argument("--delivery-log", default=os.path.join(HERE, "delivery_log.jsonl"))
    ap.add_argument("--dry-run", action="store_true",
                     help="real selection/dedup/cap logic, no real WhatsApp API call -- for testing")
    a = ap.parse_args()

    env_path = os.path.join(HERE, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k, v)

    print(f"whatsapp_notify: daily cap={DAILY_CAP}, dedup state={DEDUP_STATE_PATH}, dry_run={a.dry_run}")
    summary = run(a.national_audit, a.demo_audit, a.delivery_log, dry_run=a.dry_run)
    print(f"whatsapp_notify summary: {summary['n_candidates']} real candidate(s), "
          f"{summary['n_sent']} sent, {summary['n_already_notified']} already-notified, "
          f"{summary['n_cap_skipped']} cap-skipped, {summary['n_failed']} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
