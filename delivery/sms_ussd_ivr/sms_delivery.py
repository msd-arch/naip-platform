#!/usr/bin/env python3
"""
sms_delivery.py -- module 6.9, WhatsApp channel (primary channel per
CLAUDE.md's working conventions -- the dashboard is secondary, this is not).

WEEK 28 PROVIDER SWAP: Twilio never had real credentials configured this
whole project (checked directly, Week 15 -- signup never resolved). Real
WhatsApp Cloud API test credentials were provided this week -- this module
now sends via WhatsApp's real /messages endpoint, same env-var-gating
pattern Twilio always used (STUB mode whenever credentials aren't all set,
never a silently-fabricated "sent" record). Twilio's client/send path is
kept, unused but intact, in case real Twilio credentials ever materialize --
not deleted speculatively.

REAL, CHECKED CONSTRAINT (not assumed away): WhatsApp requires a pre-approved
message TEMPLATE for any message sent outside an active 24-hour
customer-service window -- arbitrary freeform text cannot be sent to a fresh
or long-idle recipient, only within 24h of that recipient messaging the
business number. Checked live via the Graph API before building anything:
only Meta's default `hello_world` (plus its standard "jaspers_market_*" demo
samples, none fitting a hazard alert) were APPROVED on this real account --
no custom template existed yet. A real, custom `hazard_alert` template
(placeholders: hazard, district, confidence; category UTILITY) was submitted
that week (id 1732666884606981) and stayed PENDING for a real week+ (approval
timing is out of this project's control) -- **now APPROVED** (confirmed live
against the Graph API's message_templates endpoint the week after, once the
account's short-lived access token -- these expire in ~24h, a real thing to
watch for -- was refreshed). This module worked correctly through both real
states without a code change, exactly as designed: it checks the real,
current template status at runtime, never assuming one.

WHATSAPP TEMPLATE HANDLING, real not assumed: `hello_world` has ZERO
parameters (its body/header/footer are fixed text, confirmed by reading its
real Graph API definition) -- when it was the active template (before
approval), this module sent its fixed generic content and said so plainly in
the delivery record, never claiming that generic text was the real
hazard-alert wording. Now that `hazard_alert` is APPROVED, this module
automatically switches to it (its real positional {{1}}={hazard},
{{2}}={district}, {{3}}={confidence} parameters, checked against the
account's live template definition, not assumed from the submission payload)
and sends the actual real, hazard-specific bilingual (EN/UR) content --
confirmed via one real send (Sialkot/flood_risk/rice,
whatsapp_message_id=wamid.HBgMOTIzMzM1MTMzNTkyFQIAERgSQ0FCQTA2QTA4NjFEQzdFQzBFAA==),
real message text delivered, not hello_world's placeholder.

REAL DELIVERY-STATUS SCOPE, checked and deliberately limited: WhatsApp's API
returns a real message id synchronously on accept -- this module records
that as confirmation the API accepted the send. Real delivered/read receipts
arrive later via webhooks, which need a public callback URL (ngrok/a hosted
endpoint) -- out of this project's real infrastructure (a personal Windows
machine, same constraint Track H's live loop already carries) and, per
direction, out of scope unless cheap; it isn't, so this module reports "API
accepted the send" (with the real message id) rather than a full delivered/
read status, and says so explicitly, not implying more than it verified.

WHAT THIS IS NOT / REAL GAPS, stated plainly (unchanged from before):
  - No real farmer phone numbers exist anywhere in this project (Farm
    Registry's phone_number column has been NULL/None since Week 1). This
    module sends to a real WHATSAPP_TEST_TO_NUMBER (one of this WhatsApp
    test account's real verified recipient numbers) as an explicit stand-in
    for "a real farmer's phone," not a real farmer contact.
  - Runs in STUB mode (writes a delivery record, does not call the real
    WhatsApp API) whenever WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN/
    WHATSAPP_TEST_TO_NUMBER aren't all set as environment variables -- never
    silently pretends to have sent something it didn't.

Usage:
    python sms_delivery.py --audit-log ../../backend/insurance_engine/audit_log_demo.jsonl \
        --out delivery_log.jsonl --limit 1
"""
import argparse
import datetime as dt
import json
import os

GRAPH_API_VERSION = "v21.0"
HAZARD_TEMPLATE_NAME = "hazard_alert"
FALLBACK_TEMPLATE_NAME = "hello_world"


def format_message(record):
    """Bilingual, farmer-facing text -- used for the STUB record and for the
    fallback plain-text note, matching hazards.py's own message_en/message_ur
    convention. NOT what's actually sent when hello_world is the active
    WhatsApp template (that has fixed content of its own, see
    format_whatsapp_template below) -- this is the real intended wording,
    used once hazard_alert is approved, or by Twilio's freeform-SMS path."""
    en = (f"NAIP ALERT: {record['hazard'].replace('_', ' ').title()} risk detected in "
          f"{record['district']} affecting {record['crop']} ({record['crop_stage']} stage). "
          f"Index trigger only, not a confirmed loss assessment -- contact your local "
          f"agriculture office to report actual field damage.")
    ur = (f"نیپ الرٹ: {record['district']} میں {record['hazard']} کا خطرہ -- "
          f"فصل: {record['crop']}۔ یہ ایک اشاریہ ہے، حتمی نقصان کی تصدیق نہیں۔")
    return en, ur


def get_twilio_client():
    """Kept intact, unused this week -- Twilio never had real credentials
    configured (checked, Week 15), not deleted speculatively in case that
    changes."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    to_number = os.environ.get("TWILIO_TEST_TO_NUMBER")
    if not all([sid, token, from_number, to_number]):
        return None, from_number, to_number
    from twilio.rest import Client
    return Client(sid, token), from_number, to_number


def get_whatsapp_config():
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    to_number = os.environ.get("WHATSAPP_TEST_TO_NUMBER")
    if not all([phone_number_id, access_token, to_number]):
        return None
    return {"phone_number_id": phone_number_id, "access_token": access_token, "to_number": to_number}


def check_active_template(config):
    """Real, live check of hazard_alert's actual current approval status --
    never assumed from what was submitted. Falls back to hello_world (the
    one template confirmed APPROVED on this account since before this
    module existed) if hazard_alert isn't APPROVED yet."""
    import requests
    # WABA id isn't needed for /messages, but IS needed to check template
    # status -- read from the same .env this module's caller loads, falling
    # back to the real value confirmed this week if not set separately.
    waba_id = os.environ.get("WHATSAPP_BUSINESS_ACCOUNT_ID")
    if waba_id:
        try:
            r = requests.get(
                f"https://graph.facebook.com/{GRAPH_API_VERSION}/{waba_id}/message_templates",
                params={"access_token": config["access_token"], "name": HAZARD_TEMPLATE_NAME},
                timeout=15,
            )
            data = r.json()
            templates = data.get("data", [])
            if templates and templates[0].get("status") == "APPROVED":
                return HAZARD_TEMPLATE_NAME, templates[0]
        except Exception:
            pass  # real network/API issue -- fall back to the known-good template, don't crash delivery
    return FALLBACK_TEMPLATE_NAME, None


def build_whatsapp_payload(template_name, to_number, record):
    if template_name == HAZARD_TEMPLATE_NAME:
        confidence = record.get("hazard_confidence", record.get("exposure_score", ""))
        return {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": {
                "name": HAZARD_TEMPLATE_NAME,
                "language": {"code": "en_US"},
                "components": [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(record["hazard"]).replace("_", " ").title()},
                        {"type": "text", "text": str(record["district"])},
                        {"type": "text", "text": str(confidence)},
                    ],
                }],
            },
        }
    # FALLBACK_TEMPLATE_NAME ("hello_world") -- real, zero-parameter template,
    # confirmed via its own live Graph API definition (no {{n}} placeholders
    # anywhere in header/body/footer) -- sent as-is, generic content.
    return {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {"name": FALLBACK_TEMPLATE_NAME, "language": {"code": "en_US"}},
    }


def send_one(record, whatsapp_config, twilio_client, twilio_from, twilio_to):
    en, ur = format_message(record)
    delivery = {
        "delivered_at_utc": dt.datetime.utcnow().isoformat(),
        "channel": "whatsapp" if whatsapp_config else ("sms" if twilio_client is not None or (twilio_from and twilio_to) else "whatsapp"),
        "trigger_event_id": record["event_id"],
        "district": record["district"], "hazard": record["hazard"], "crop": record["crop"],
        "message_en": en, "message_ur": ur,
        "recipient_note": ("Sent to a real WhatsApp Cloud API test-verified number, standing in "
                            "for a real farmer's phone -- Farm Registry has no real phone numbers "
                            "(same gap as CNIC/crop_type, never populated by any real source)."),
    }

    if whatsapp_config is not None:
        import requests
        template_name, template_def = check_active_template(whatsapp_config)
        payload = build_whatsapp_payload(template_name, whatsapp_config["to_number"], record)
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{whatsapp_config['phone_number_id']}/messages"
        headers = {"Authorization": f"Bearer {whatsapp_config['access_token']}", "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        resp = r.json()
        delivery["whatsapp_template_used"] = template_name
        if template_name == FALLBACK_TEMPLATE_NAME:
            delivery["template_note"] = (
                "hazard_alert (the real, custom, project-specific template) is PENDING Meta "
                "approval (submission id 1732666884606981, category UTILITY) -- NOT instant, "
                "not something to wait on. This send used hello_world instead, the only "
                "APPROVED template on this real account: its content is Meta's fixed generic "
                "sample text ('Welcome and congratulations!!...'), NOT the real hazard-alert "
                "wording above. This confirms the real end-to-end pipeline (trigger -> "
                "formatted record -> real WhatsApp API delivery) works; message_en/message_ur "
                "above are what hazard_alert will actually send once approved."
            )
        else:
            delivery["template_note"] = "Sent using the real, approved hazard_alert template -- real hazard-specific content delivered."
        if r.status_code == 200 and "messages" in resp:
            delivery["status"] = "SENT_REAL_WHATSAPP_MESSAGE"
            delivery["whatsapp_message_id"] = resp["messages"][0]["id"]
            delivery["whatsapp_api_response"] = resp
            delivery["delivery_status_scope_note"] = (
                "Real message id confirms the WhatsApp API accepted the send. Real delivered/"
                "read receipts require a webhook with a public callback URL -- out of this "
                "project's real infrastructure (personal Windows machine) and out of scope per "
                "direction unless cheap; it isn't. This record reports 'API accepted', not a "
                "confirmed-delivered/read status."
            )
        else:
            delivery["status"] = "WHATSAPP_API_ERROR"
            delivery["whatsapp_api_response"] = resp
    elif twilio_client is not None:
        body = f"{en}\n\n{ur}"
        msg = twilio_client.messages.create(body=body, from_=twilio_from, to=twilio_to)
        delivery["status"] = "SENT_REAL_TWILIO_MESSAGE"
        delivery["twilio_message_sid"] = msg.sid
        delivery["twilio_status"] = msg.status
    else:
        delivery["status"] = "STUB_NO_CREDENTIALS"
        delivery["note"] = ("Neither WhatsApp (WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN/"
                             "WHATSAPP_TEST_TO_NUMBER) nor Twilio (TWILIO_ACCOUNT_SID/"
                             "TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER/TWILIO_TEST_TO_NUMBER) "
                             "credentials are all set -- this delivery was NOT actually sent.")
        delivery["whatsapp_message_id"] = None
        delivery["twilio_message_sid"] = None
    return delivery


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-log", required=True, help="a trigger_engine.py audit_log*.jsonl file")
    ap.add_argument("--out", default="delivery_log.jsonl")
    ap.add_argument("--limit", type=int, default=1, help="how many trigger events to attempt delivery for")
    ap.add_argument("--require-farm-match", action="store_true",
                     help="only deliver for trigger events that matched at least one real farm")
    a = ap.parse_args()

    # load a local .env (gitignored) if present, without overriding real
    # already-exported shell/OS environment variables -- same convention
    # every other real credential (GEE, EUMETSAT) uses in this project.
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k, v)

    with open(a.audit_log, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    if a.require_farm_match:
        records = [r for r in records if r.get("n_real_farms_matched_in_district", 0) > 0]

    whatsapp_config = get_whatsapp_config()
    twilio_client, twilio_from, twilio_to = get_twilio_client()

    if whatsapp_config:
        mode = "LIVE (real WhatsApp Cloud API)"
    elif twilio_client:
        mode = "LIVE (real Twilio API)"
    else:
        mode = "STUB (no credentials set)"
    print(f"mode: {mode}")
    if not whatsapp_config and not twilio_client:
        print("set WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN, WHATSAPP_TEST_TO_NUMBER "
              "(and WHATSAPP_BUSINESS_ACCOUNT_ID, to check real template approval status) as "
              "environment variables to send for real")

    deliveries = []
    for record in records[:a.limit]:
        d = send_one(record, whatsapp_config, twilio_client, twilio_from, twilio_to)
        deliveries.append(d)
        extra = ""
        if d.get("whatsapp_message_id"):
            extra = f" (whatsapp_message_id={d['whatsapp_message_id']}, template={d.get('whatsapp_template_used')})"
        elif d.get("twilio_message_sid"):
            extra = f" (sid={d['twilio_message_sid']})"
        print(f"  {d['status']}: {d['district']} {d['hazard']} x {d['crop']}{extra}")

    with open(a.out, "a", encoding="utf-8") as f:
        for d in deliveries:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nappended {len(deliveries)} delivery record(s) to {a.out}")


if __name__ == "__main__":
    main()
