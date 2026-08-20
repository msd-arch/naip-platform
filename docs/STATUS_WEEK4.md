# Week 4 status report — Insurance Engine (6.8) + Multi-Channel Delivery (6.9) + Integration

## Pre-checks (done before any code, per this week's kickoff)

- **Crop-mix problem resolved with a coarse, hardcoded plausibility mask**
  (`naip/models/fusion/crop_plausibility.py`) — every district gets a hand-classified
  set of plausible crops from standard knowledge of Pakistan's agricultural geography
  (Punjab cotton belt, rice belt, Sindh's Indus-valley cropping, KPK/Balochistan
  plains-vs-mountains, GB excluded entirely). **Not real crop-mix data** — stated in the
  module's own docstring and every consumer of it. Wired directly into
  `exposure_risk.py`: every row now carries `agronomically_plausible`; the original
  Skardu-cotton problem is gone (`plausible_crops('Skardu') == set()`). Effect was
  large and real: **1041 of 1338 nonzero-exposure rows (78%) were agronomically
  implausible** and are now excluded from what the trigger engine sees.
- **Urdu broadcast pipeline checked properly, found real but wrong-channel.**
  `Downloads/fill_broadcast.py` is real, working code — but its own docstring says the
  output goes "before it goes anywhere near **HeyGen**" (an AI video generator). This
  is a video-broadcast pipeline, not SMS/USSD/IVR — a different channel entirely from
  what 6.9 needs. Its one required input file doesn't exist on disk either, so even
  this real pipeline can't currently run. No SMS/telco package, credential, or config
  was found anywhere on this machine. **6.9 is new work, not an extension of anything
  real** — confirmed, not assumed.
- **Farm Registry decision made for real**: still no Docker/Postgres (rechecked this
  week — still absent). Per your direction, proceeded with an **in-memory structure**
  (`naip/backend/farm_registry/in_memory_registry.py`) that mirrors `schema.sql`
  exactly — same fields, same nullability (crop_type/CNIC still None, same honest gap
  as every prior week) — loaded from the real 120-farm GeoJSON with real
  point-in-polygon district assignment. Result was a genuine sanity check: farms
  resolved to **Sheikhpura (54), Layyah (47), Gujranwala (18), Bhakkar (1)** —
  Sheikhpura is correct because Muridke (the dataset's other named cluster) is a town
  *within* Sheikhpura district, not its own district. Real geography, not a bug.

## What's actually working end-to-end

- **Trigger-contract engine** (`naip/backend/insurance_engine/trigger_engine.py`):
  deterministic rule — `exposure_score >= threshold AND agronomically_plausible` —
  evaluated against the **full** real national exposure archive (141,120 rows, not
  just a top-N snapshot; `exposure_risk.py` was refactored this week to expose
  `compute_exposure_rows()` for exactly this reuse). Every trigger writes a real,
  append-only JSONL audit record with the exact hazard confidence, threshold, crop
  stage, plausibility check, matched real farm IDs, an explicit `basis_risk_note`
  (two concrete real sources: the district-level plausibility mask's coarseness, and
  the underlying hazard's single 0.25°/~27km grid-cell reading), and a stubbed
  `payout` block (`STUBBED_INTENT_ONLY`, no transaction ID, no fabricated payment
  record — Raast is integration-point-only per architecture.md, never attempted for
  real).
  - At threshold **0.35** (illustrative, not actuarially calibrated — no real
    claims/loss data exists to calibrate against, same data-gap pattern as every
    other week): **6 national trigger events**, **0 matched real farms** — an honest
    finding, not a bug: the 120-farm seed covers 4 of 126 districts, so most national
    triggers naturally fall outside farm-registry coverage.
  - At threshold **0.20** (explicitly labeled as a demo threshold chosen to land
    inside real farm-registry coverage, not a recalibration): **192 trigger events**,
    **12 matched at least one real farm**.
- **SMS delivery** (`naip/delivery/sms_ussd_ivr/sms_delivery.py`): real bilingual
  message formatting (English + Urdu, matching `hazards.py`'s own convention), a real
  Twilio integration that activates automatically once 4 env vars are set — **not set
  this week** (you chose to proceed in stub mode rather than sign up now). Every
  delivery record honestly says `STUB_NO_CREDENTIALS`, with no message SID, because no
  message was sent. No real farmer phone numbers exist anywhere in this project
  (Farm Registry's `phone_number` has been NULL since Week 1) — the module is
  designed to send to one Twilio-verified test number as an explicit stand-in, labeled
  as such in every record, not a real farmer contact.
- **Full integration** (`naip/run_end_to_end_demo.py`): chains every real stage —
  `hazards.py` → `exposure_risk.py` × `crop_plausibility.py` → `trigger_engine.py` →
  `in_memory_registry.py` → `sms_delivery.py` — for one real, reproducible scenario:
  **Layyah, 2026-07-06, fog × cotton (flowering stage), exposure_score 0.225, 47 real
  matched farms.** Ran clean end-to-end this week; this is the demo-day scenario.

## What's stubbed / scoped down, stated plainly

- Payout is `STUBBED_INTENT_ONLY` — no real money movement, no transaction ID, by
  design per architecture.md §5's Raast integration-point-only scope.
- SMS delivery ran in stub mode this week — real Twilio code path exists and is
  tested (stub branch), but no live send happened. Zero-code-change upgrade path if
  credentials get set before demo day.
- Trigger threshold (0.35 national / 0.20 demo) is illustrative, not actuarially
  calibrated — stated in `trigger_summary.json`'s own `threshold_note`.
- Farm Registry remains schema-only for deployment purposes — in-memory this week,
  same real data, same real gaps (crop_type/CNIC still None) a live Postgres instance
  would also have.
- Basis risk is real and unresolved, not hidden: an index trigger is not proof of
  individual farm loss. Stated on every single audit record, not just in this report.

## Real numbers, this week

| | value |
|---|---|
| Nonzero-exposure rows before plausibility mask | 1,338 |
| Removed as agronomically implausible | 1,041 (78%) |
| National trigger events (threshold 0.35) | 6 |
| — matched to real farms | 0 |
| Demo trigger events (threshold 0.20) | 192 |
| — matched to real farms | 12 |
| Real farms loaded (in-memory registry) | 120/120 |
| Districts with real farm coverage | 4/126 (Sheikhpura, Layyah, Gujranwala, Bhakkar) |

## What's blocked

- Real SMS send — needs Twilio (or equivalent) credentials, not set up this week by
  your choice.
- Real payout — architecturally out of scope this sprint (Raast integration-point-only,
  per architecture.md).
- Actuarial threshold calibration — no real claims/loss data exists anywhere
  accessible for this project.
- Live PostGIS deployment — still no Docker on this machine; in-memory structure is a
  faithful stand-in, not a workaround for a data gap that would persist either way.

## Demo-day scenario (see `naip/docs/FINAL_REPORT.md` for the full walkthrough)

`python naip/run_end_to_end_demo.py --district Layyah --threshold 0.20` — runs the
real, complete path live: real MSG-derived fog detection in Layyah on 2026-07-06 →
fused with the real (province-average) crop calendar's cotton-flowering stage →
passed through the real agronomic plausibility mask → trigger-contract audit record
with basis risk stated → matched against 47 real farm polygons → SMS delivery attempt
(stub, honestly labeled).
