# Week 15 status report — Phase 4, Track N (infrastructure debt status check)

Full context: `docs/PHASE4_SCOPE_DOCUMENT.md`'s Track N section. A status check, not a build —
report what's real before deciding whether either item is worth closing this session.

## 1. Docker / PostGIS — still not installed, real read on whether it's worth it

**Real-checked, not assumed**: `Get-Command docker` (not found), Docker Desktop's standard
install path (`C:\Program Files\Docker\Docker\Docker Desktop.exe`, absent), running processes
and Windows services matching `*docker*` (none). **Unchanged since Week 1** — Docker is not on
this machine.

`naip/backend/farm_registry/schema.sql` and `load_seed_farms.py` are still real, present, and
unmodified — but with no Docker/Postgres instance available, they could not be run against a
live database this week either (same real constraint, not newly discovered).

**The real question the task actually asked — does anything since Week 1 change whether this is
worth deploying?** Checked, not assumed: Track C (Week 6) and Track F (Week 8) did add real
crop-mix data since Week 1, already wired into `exposure_risk.py`. But that data is
**district-level** (a district's aggregate real MNFSR crop-area share), not **per-farm** — it
does not populate `schema.sql`'s `crop_calendar.crop_type` column, which needs a real value tied
to an individual `farm_id`, and it does nothing for the CNIC/farmer-identity gap a live database
would need for the project's actual payout north star. `in_memory_registry.py` already gives the
demo/trigger-engine path (real 120-farm polygons, real point-in-polygon district assignment)
everything a live database would provide right now — no real capability is currently blocked on
the database not being live.

**Real recommendation**: the original reasoning for deferring this still holds. Not worth
deploying reflexively just because it's mechanically straightforward — the real value case
hasn't materially changed since Week 1. Worth doing only if closing the "in-memory, not live"
caveat has value on its own (e.g. for a demo/evaluation audience), independent of unlocking new
functionality — a real judgment call, flagged rather than decided here.

## 2. Twilio / real SMS — signup still not resolved, activation logic re-verified

**Real-checked, not assumed**: Windows environment variables at User and Machine scope
(`[Environment]::GetEnvironmentVariable`), current process environment, and a search for `.env`
files anywhere under `naip/` — **no `TWILIO_*` credentials exist anywhere on this machine.** The
phone-verification signup issue from early in the project was never resolved; this remains
exactly where it was left, not newly re-attempted or newly blocked.

**Re-verified the "zero-code-change path to live" claim by code review** (not assumed to still
be accurate): `sms_delivery.py`'s `get_twilio_client()` correctly checks all four required env
vars (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_TEST_TO_NUMBER`)
and only imports/constructs a real `twilio.rest.Client` when every one is set — the real stub/live
branch logic in `send_one()` is sound. The `twilio` Python package (9.11.0) is installed and
`from twilio.rest import Client` imports cleanly. **The claim holds**: setting the 4 real env
vars from an actual Twilio account is genuinely the only remaining step, no code changes needed.
Real delivery log (`delivery_log.jsonl`, 4 records, most recent 2026-08-19) confirms every
attempt to date is still `STUB_NO_CREDENTIALS`.

**Did not attempt Twilio signup or troubleshooting** — per direction, this needs the same manual
account-creation step as before, not something to do autonomously.

## Recommendation

Neither item is worth actively closing this session. Docker/PostGIS: the real value case is
still weak (district-level crop data doesn't close the per-farm gap that made this low-priority
originally). Twilio: blocked on a real manual step outside this session's ability to complete.
Both remain known, accepted, explicitly-stated gaps — not silently carried forward.
