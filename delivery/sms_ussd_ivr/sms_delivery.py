#!/usr/bin/env python3
"""
sms_delivery.py -- module 6.9, SMS channel (primary channel per CLAUDE.md's
working conventions -- the dashboard is secondary, this is not).

WHAT THIS IS: the real, first delivery channel for a trigger-contract audit
record (from insurance_engine/trigger_engine.py), formatted bilingually
(English + Urdu, matching hazards.py's own message_en/message_ur convention)
and sent via a real Twilio account -- not a fabricated "sent" log entry.

WHAT THIS IS NOT / REAL GAPS, stated plainly:
  - The "Urdu broadcast-generation pipeline" referenced in CLAUDE.md since
    Week 1 turned out real (fill_broadcast.py exists) but targets a
    completely different channel (HeyGen AI video generation, not SMS/IVR)
    and its own required template file doesn't exist on disk either --
    checked this week, not assumed. 6.9 is NEW WORK, not an extension of
    that pipeline. Reusing hazards.py's real bilingual message convention
    (message_en/message_ur) is the actual continuity with prior work.
  - No real farmer phone numbers exist anywhere in this project (Farm
    Registry's phone_number column has been NULL/None since Week 1, same
    root gap as CNIC/crop_type -- no source ever populated it). This module
    sends to a single Twilio-VERIFIED TEST number (env TWILIO_TEST_TO_NUMBER)
    as an explicit stand-in for "a real farmer's phone," not a real farmer
    contact. Every delivery record says this.
  - Runs in STUB mode (writes a delivery record, does not call the real
    Twilio API) whenever TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/
    TWILIO_FROM_NUMBER/TWILIO_TEST_TO_NUMBER aren't all set as environment
    variables -- never silently pretends to have sent something it didn't.
    Set those 4 env vars to switch to LIVE mode with zero code changes.

Usage:
    python sms_delivery.py --audit-log ../../backend/insurance_engine/audit_log_demo.jsonl \
        --out delivery_log.jsonl --limit 1
"""
import argparse
import datetime as dt
import json
import os


def format_message(record):
    """Bilingual SMS text from a real trigger-contract audit record --
    farmer-facing, short (SMS-length), not the full audit JSON."""
    en = (f"NAIP ALERT: {record['hazard'].replace('_', ' ').title()} risk detected in "
          f"{record['district']} affecting {record['crop']} ({record['crop_stage']} stage). "
          f"Index trigger only, not a confirmed loss assessment -- contact your local "
          f"agriculture office to report actual field damage.")
    ur = (f"نیپ الرٹ: {record['district']} میں {record['hazard']} کا خطرہ -- "
          f"فصل: {record['crop']}۔ یہ ایک اشاریہ ہے، حتمی نقصان کی تصدیق نہیں۔")
    return en, ur


def get_twilio_client():
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    to_number = os.environ.get("TWILIO_TEST_TO_NUMBER")
    if not all([sid, token, from_number, to_number]):
        return None, from_number, to_number
    from twilio.rest import Client
    return Client(sid, token), from_number, to_number


def send_one(record, client, from_number, to_number):
    en, ur = format_message(record)
    body = f"{en}\n\n{ur}"
    delivery = {
        "delivered_at_utc": dt.datetime.utcnow().isoformat(),
        "channel": "sms",
        "trigger_event_id": record["event_id"],
        "district": record["district"], "hazard": record["hazard"], "crop": record["crop"],
        "message_en": en, "message_ur": ur,
        "recipient_note": ("Sent to a Twilio-VERIFIED TEST number, standing in for a real "
                            "farmer's phone -- Farm Registry has no real phone numbers (same "
                            "gap as CNIC/crop_type, never populated by any real source)."),
    }
    if client is None:
        delivery["status"] = "STUB_NO_CREDENTIALS"
        delivery["note"] = ("TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER/"
                             "TWILIO_TEST_TO_NUMBER not all set -- this delivery was NOT "
                             "actually sent. No message SID exists because no message was sent.")
        delivery["twilio_message_sid"] = None
    else:
        msg = client.messages.create(body=body, from_=from_number, to=to_number)
        delivery["status"] = "SENT_REAL_TWILIO_MESSAGE"
        delivery["twilio_message_sid"] = msg.sid
        delivery["twilio_status"] = msg.status
    return delivery


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-log", required=True, help="a trigger_engine.py audit_log*.jsonl file")
    ap.add_argument("--out", default="delivery_log.jsonl")
    ap.add_argument("--limit", type=int, default=1, help="how many trigger events to attempt delivery for")
    ap.add_argument("--require-farm-match", action="store_true",
                     help="only deliver for trigger events that matched at least one real farm")
    a = ap.parse_args()

    with open(a.audit_log, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    if a.require_farm_match:
        records = [r for r in records if r.get("n_real_farms_matched_in_district", 0) > 0]

    client, from_number, to_number = get_twilio_client()
    mode = "LIVE (real Twilio API)" if client else "STUB (no credentials set)"
    print(f"mode: {mode}")
    if client is None:
        print("set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, "
              "TWILIO_TEST_TO_NUMBER as environment variables to send for real")

    deliveries = []
    for record in records[:a.limit]:
        d = send_one(record, client, from_number, to_number)
        deliveries.append(d)
        print(f"  {d['status']}: {d['district']} {d['hazard']} x {d['crop']}"
              + (f" (sid={d['twilio_message_sid']})" if d.get("twilio_message_sid") else ""))

    with open(a.out, "a", encoding="utf-8") as f:
        for d in deliveries:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nappended {len(deliveries)} delivery record(s) to {a.out}")


if __name__ == "__main__":
    main()
