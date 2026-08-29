# Phase 5 Scope Document

**Reconstructed 2026-08-29, not an original planning document.** Same real gap as
`PHASE4_SCOPE_DOCUMENT.md` — cited (via `docs/HANDOFF_20260827.md`'s real reference to
"Phase 5's Track P... the last named-but-not-yet-started track in
`PHASE5_SCOPE_DOCUMENT.md`") but never actually existed as a committed file. Rebuilt
from `CLAUDE.md`'s real Sprint history (Weeks 22-23, 29).

## Real scope: three tracks

| Track | What it is | Closed | Real status (see `CLAUDE.md` for full detail) |
|---|---|---|---|
| **O** | Real yield prediction (per-district, per-crop, t/ha) | Week 22 | Real, mostly negative result reported plainly: a naive "this year = last year's real reported yield" baseline beats the trained Sentinel-2 phenology model in 6 of 8 crop×direction combinations — wheat's real yield is highly persistent year-over-year, a genuinely hard bar for satellite phenology to clear. Real hazard-co-occurrence ablation confirmed real-data-infeasible (NAIP's MSG archives don't overlap the real yield-label growing seasons), not attempted. |
| **P** | Minimal farmer data-collection mechanism (identity fields: name, CNIC, phone; real farmer-declared crop type overriding the model estimate) | Named in Phase 5 scope, real build deferred until Week 29 (flagged as "not-yet-started" as late as `docs/HANDOFF_20260827.md`) | `in_memory_registry.py` gained a real write path (`register_farmer_submission()` — real CNIC dedup, real point-in-polygon district assignment from the submitted boundary, persists to a gitignored `data/seed/farmer_submissions.json`) and a real precedence rule (`Farm.resolved_crop_type()` — farmer-declared always beats model-estimated). Proven end-to-end with one real test record (identity fields provided directly by the project owner), then removed once the write path was confirmed working, per direction — the mechanism itself stays real and working for the next real submission. |
| **Q** | Pest/disease screening | Week 23 | Real pre-check found no extractable per-location outbreak data for Pakistan (RustTracker.org dead, GRRC map-only, the closest real published survey only publishes district aggregates). Fallback "crop stress early-warning screen" built instead — real level-anomaly + senescence-slope-anomaly signals, reusing Track M's NDVI infrastructure, explicitly non-diagnostic in its own UI text (not just documentation). Real result: 19/126 districts flagged on both signals simultaneously, the defensible headline (89/126 on either signal alone, a real but loose view given ~25 points/district). |

## Real, honest note on Track P's timeline

Track P is the one track in this document whose real build genuinely lagged its own
scope entry — named in the same phase as O and Q, but not actually started until
several weeks after both had closed (Week 29, not Week 22-23). This document states
that plainly rather than implying all three tracks were built in the same pass; the
delay itself was never hidden (`docs/HANDOFF_20260827.md` recorded it as open in real
time, not smoothed over after the fact).

## What Phase 5 explicitly did NOT cover

Same real boundary as Phase 4: no scheduled refresh for Crop Intelligence / AI Models
pages (trained-model validation snapshots, not live signals) — Track O's own yield
numbers included, since they're a validation result, not something meant to
auto-refresh on a calendar.
