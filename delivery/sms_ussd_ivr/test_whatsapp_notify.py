#!/usr/bin/env python3
"""
test_whatsapp_notify.py -- real unit tests for whatsapp_notify.py's
dedup/cap/rule logic, using synthetic events run through the REAL code
path (select_candidates/run), clearly labeled as tests -- never claimed
as a real fired alert. No real WhatsApp API call is made: sms_delivery.
send_one is monkeypatched to a fake that returns a controllable, fully
synthetic delivery record, so this tests the logic this module actually
owns (selection/dedup/cap/failure-handling), not sms_delivery.py's own
already-verified real API integration.

Usage:
    python test_whatsapp_notify.py
"""
import json
import os
import shutil
import tempfile
import unittest

import sms_delivery
import whatsapp_notify as wn


def synthetic_record(district, hazard, crop, date, score=0.05):
    return {
        "event_id": "TEST-" + district + hazard + crop + date,
        "district": district, "hazard": hazard, "crop": crop, "date": date,
        "crop_stage": "flowering", "hazard_confidence": 0.7, "exposure_score": score,
        "threshold": 0.02, "agronomically_plausible": True,
    }


class FakeSend:
    """Controllable stand-in for sms_delivery.send_one -- next_result is a
    queue of (status, whatsapp_message_id) the test sets up in advance."""
    def __init__(self):
        self.calls = []
        self.next_results = []

    def __call__(self, record, whatsapp_config, twilio_client, twilio_from, twilio_to):
        self.calls.append(record)
        status, msg_id = self.next_results.pop(0)
        return {
            "delivered_at_utc": "2026-08-31T00:00:00",
            "status": status,
            "district": record["district"], "hazard": record["hazard"], "crop": record["crop"],
            "whatsapp_message_id": msg_id,
            "note": None if status != "STUB_NO_CREDENTIALS" else "test: simulated no-credentials",
        }


class TestWhatsappNotify(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="naip_whatsapp_test_")
        self.national_path = os.path.join(self.tmpdir, "audit_national.jsonl")
        self.demo_path = os.path.join(self.tmpdir, "audit_demo.jsonl")
        self.delivery_path = os.path.join(self.tmpdir, "delivery_log.jsonl")
        wn.DEDUP_STATE_PATH = os.path.join(self.tmpdir, "dedup_state.json")
        self._real_send_one = sms_delivery.send_one
        self.fake_send = FakeSend()
        sms_delivery.send_one = self.fake_send

    def tearDown(self):
        sms_delivery.send_one = self._real_send_one
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_jsonl(self, path, records):
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_rule2_excludes_non_gujranwala(self):
        """TEST (synthetic): a demo-threshold event outside Gujranwala must
        never become a candidate -- rule 2 is Gujranwala-only, by design."""
        self._write_jsonl(self.national_path, [])
        self._write_jsonl(self.demo_path, [synthetic_record("Sialkot", "flood_risk", "rice", "20260830")])
        national = wn.load_jsonl(self.national_path)
        demo = wn.load_jsonl(self.demo_path)
        candidates = wn.select_candidates(national, demo)
        self.assertEqual(len(candidates), 0, "non-Gujranwala demo event must not be a candidate")

    def test_rule1_any_district(self):
        """TEST (synthetic): a national-threshold event in ANY district
        (not just Gujranwala) must become a real candidate."""
        self._write_jsonl(self.national_path, [synthetic_record("Chitral", "hail", "wheat", "20260830")])
        self._write_jsonl(self.demo_path, [])
        national = wn.load_jsonl(self.national_path)
        demo = wn.load_jsonl(self.demo_path)
        candidates = wn.select_candidates(national, demo)
        self.assertEqual(len(candidates), 1)

    def test_dedup_sends_once_then_skips(self):
        """TEST (synthetic): the SAME real-shaped event across two
        consecutive cycles (identical audit log content, simulating an
        ongoing trigger) must send exactly once, not on the second pass."""
        self._write_jsonl(self.national_path, [])
        self._write_jsonl(self.demo_path, [synthetic_record("Gujranwala", "uv_index", "rice", "20260830")])
        self.fake_send.next_results = [("SENT_REAL_WHATSAPP_MESSAGE", "TEST-msg-1")]

        summary1 = wn.run(self.national_path, self.demo_path, self.delivery_path)
        self.assertEqual(summary1["n_sent"], 1)
        self.assertEqual(summary1["n_already_notified"], 0)
        self.assertEqual(len(self.fake_send.calls), 1, "real send attempted exactly once on cycle 1")

        # cycle 2: identical still-active event, no new send() call should happen
        summary2 = wn.run(self.national_path, self.demo_path, self.delivery_path)
        self.assertEqual(summary2["n_sent"], 0)
        self.assertEqual(summary2["n_already_notified"], 1)
        self.assertEqual(len(self.fake_send.calls), 1, "no second real send for the same ongoing event")

    def test_failed_send_not_marked_notified_and_retried(self):
        """TEST (synthetic): a failed send (e.g. expired token) must NOT be
        recorded as notified -- the same genuinely-new event must be
        retried, and attempted again, on the next cycle."""
        self._write_jsonl(self.national_path, [synthetic_record("Kasur", "frost", "wheat", "20260830")])
        self._write_jsonl(self.demo_path, [])
        self.fake_send.next_results = [("WHATSAPP_API_ERROR", None)]

        summary1 = wn.run(self.national_path, self.demo_path, self.delivery_path)
        self.assertEqual(summary1["n_sent"], 0)
        self.assertEqual(summary1["n_failed"], 1)

        # cycle 2: same event, this time succeeds -- must be retried since
        # the failure was never marked notified
        self.fake_send.next_results = [("SENT_REAL_WHATSAPP_MESSAGE", "TEST-msg-2")]
        summary2 = wn.run(self.national_path, self.demo_path, self.delivery_path)
        self.assertEqual(summary2["n_sent"], 1, "the previously-failed event must be retried and sent")
        self.assertEqual(len(self.fake_send.calls), 2, "two real send attempts total for one real event")

    def test_daily_cap_blocks_and_does_not_mark_notified(self):
        """TEST (synthetic): once the daily cap is reached, further
        genuinely-new distinct events must be skipped, NOT sent, and NOT
        marked notified (so they're picked up again once the cap resets
        or headroom exists)."""
        wn.DAILY_CAP = 1
        try:
            events = [
                synthetic_record("Kasur", "frost", "wheat", "20260830"),
                synthetic_record("Jhelum", "cold_wave", "wheat", "20260830"),
            ]
            self._write_jsonl(self.national_path, events)
            self._write_jsonl(self.demo_path, [])
            self.fake_send.next_results = [("SENT_REAL_WHATSAPP_MESSAGE", "TEST-msg-3")]

            summary = wn.run(self.national_path, self.demo_path, self.delivery_path)
            self.assertEqual(summary["n_sent"], 1, "only cap-many real sends in one pass")
            self.assertEqual(summary["n_cap_skipped"], 1)
            self.assertEqual(len(self.fake_send.calls), 1)

            state = wn.load_dedup_state()
            self.assertEqual(len(state["notified"]), 1, "the cap-skipped event must NOT be in dedup state")
        finally:
            wn.DAILY_CAP = int(os.environ.get("WHATSAPP_DAILY_CAP", "10"))

    def test_same_event_clearing_both_rules_sends_once(self):
        """TEST (synthetic): a Gujranwala event that clears BOTH the
        strict national bar AND the looser demo bar is one real event --
        must send exactly once, tagged with both matched rules."""
        rec = synthetic_record("Gujranwala", "hail", "cotton", "20260830")
        self._write_jsonl(self.national_path, [rec])
        self._write_jsonl(self.demo_path, [rec])
        self.fake_send.next_results = [("SENT_REAL_WHATSAPP_MESSAGE", "TEST-msg-4")]

        summary = wn.run(self.national_path, self.demo_path, self.delivery_path)
        self.assertEqual(summary["n_sent"], 1)
        self.assertEqual(len(summary["events"][0]["rules"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
