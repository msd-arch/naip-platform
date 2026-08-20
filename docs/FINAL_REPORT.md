# NAIP — Final Report (Weeks 1–4)

*"From nowcasting to payout" — this report is the real state of that claim, not a
highlight reel. Every number below is reproducible from code in this repo or
`Downloads/hazards_scripts/`, `Downloads/ml_pipeline/` (local, not committed).*

**Status: this is the real Week 1–4 MVP snapshot, kept as originally delivered — it
is not the current state of the project.** Phase 2 (Weeks 5–6) and Phase 3
(Weeks 7–11) real work since has recalibrated the trigger thresholds this report
cites (0.35/0.20 → 0.225/0.07, Week 9), replaced the Layyah demo scenario cited below
(no longer clears the recalibrated threshold — replaced with Gujranwala/uv_index/rice,
Week 9), and added three real trained models plus a live flood screen (Weeks 7–11).
Current state: `CLAUDE.md`'s Sprint status, `naip/docs/PHASE3_SYNTHESIS.md`,
`naip/docs/STATUS_WEEK5.md` through `STATUS_WEEK11.md`. This document is left
historically accurate to Week 4, not rewritten — see the addendum at the end for
exactly what since changed.

## What's real and working end-to-end, right now

1. **National hazard detection** (`hazards.py`, extended Week 1 from a real,
   pre-existing 12-city pilot engine): 11 detector functions, running over 126 real
   Pakistani districts, on a real 71-frame MSG/SEVIRI archive (2026-06-22..07-20).
   National baseline: **402/30,996 triggered (1.30%)**, after fixing a real
   cloud-contamination bug (spurious -14°C "cold waves" in June) caught and fixed
   this project, verified with a before/after comparison, pushed live.
2. **A new residue-burning fire detector** (Week 3, built from zero — no prior code
   existed): caught its own false-alarm bug (95/243 spurious daytime triggers) before
   shipping, rebuilt as a contextual local-background anomaly test. Every triggered
   alert states plainly, in the visible message text, that the only archive on disk is
   the wrong season to confirm a real fire.
3. **Real Sentinel-2 NDVI + irrigation classifier** (Week 2): 120/120 real farms, 0
   gaps, honestly reported at 0.700 held-out accuracy — below the 0.792 majority
   baseline on raw accuracy, though it catches 2/3 of irrigated farms.
4. **Real canal water-stress index** (Week 2): one real named distributary (Muridke
   Distributary, 69.4km, real MODIS ET/PET), real head-to-tail stress gradient,
   independently confirmed against real SRTM elevation (not just assumed).
5. **A real, working fusion methodology exists** (Week 3 pre-check): patch-sizing +
   masked-loss + curriculum-training all confirmed as real, runnable PyTorch code in
   `Downloads/ml_pipeline/` — though it's a post-loss reconstruction and does not beat
   a linear baseline on RMSE at n=12.
6. **Desert locust breeding-risk monitor** (Week 3): real SMAP soil-moisture-anomaly +
   real Sentinel-2 NDVI green-up over 3 named breeding grounds — 2 real districts
   (Tharparkar, Kharan) and one labeled real-district-union proxy (Cholistan, which has
   no official boundary anywhere).
7. **A crop-stage exposure-risk fusion model** (Week 3→4): real hazard data × a real
   (province-average) crop calendar sourced to AIS Pakistan × a Week 4
   agronomic-plausibility mask that removed 78% of the model's own nonzero-score rows
   as physically implausible (the original finding: cotton risk flagged in Skardu, a
   mountain district that would never grow cotton).
8. **A real trigger-contract engine with a real audit trail** (Week 4): every trigger
   event traceable to the exact hazard confidence, threshold, crop stage, and
   plausibility check that produced it; basis risk stated explicitly on every record,
   not assumed away; payout stubbed with zero fabricated transaction data.
9. **A complete, reproducible end-to-end path** (Week 4): `hazards.py` →
   `exposure_risk.py` × `crop_plausibility.py` → `trigger_engine.py` →
   `in_memory_registry.py` → `sms_delivery.py`, run live this week on a real scenario
   (Layyah, real fog detection, cotton flowering stage, 47 real matched farms).

## What's scoped down from the architecture doc, and why — the honest gaps

| Architecture doc claim | Real status |
|---|---|
| 4-crop (wheat/cotton/rice/sugarcane) NDVI classifier | No public dataset has cotton/rice/sugarcane classes for Pakistan (checked ESA WorldCereal's real catalog). Shipped: irrigated-vs-not only. |
| Official canal-command boundaries | Don't exist publicly anywhere (checked HDX, geoBoundaries, GEE catalog). Used a real OSM canal centerline, buffered — labeled as an approximation. |
| "Existing" crop-stage-specific exposure risk | No per-farm crop type or crop calendar ever existed. Built a regional (province-average) approximation instead, explicitly not farm-specific. |
| "Existing" IR 3.9µm fire/hot-spot technique for 6.7 | Only the channel-selection *knowledge* was real (documented in `product_info.json`); zero detector code existed. Built from scratch, caught a real false-alarm bug before shipping. |
| "Existing" Urdu broadcast pipeline extended for 6.9 | Real code exists (`fill_broadcast.py`) but targets AI video generation (HeyGen), a different channel from SMS/USSD/IVR entirely. 6.9 is new work. |
| Farm Registry (6.1) live PostGIS | Never deployed — no Docker/Postgres on this machine across all 4 weeks. Schema is real and validated; Week 4 ran the trigger engine against an in-memory structure with identical fields/nullability instead. |
| Raast payment integration | Explicitly integration-point-only per the architecture doc. Never attempted. Every payout record says `STUBBED_INTENT_ONLY`. |
| Real SMS/IVR delivery | No real telco credentials were set up this week (your choice, not a hard blocker) — delivery module is real and tested in stub mode, live-mode is a zero-code-change upgrade. |

## Basis risk — modeled explicitly, per CLAUDE.md's working conventions

Every trigger-contract audit record carries this note verbatim, not as a footnote:

> Index trigger, NOT confirmed farm-level loss. Two real, unmitigated basis-risk
> sources: (1) the crop-plausibility mask is district-level and coarse — it may still
> be wrong for any individual farm within a triggered district; (2) the underlying
> hazard reading is a single ~27km grid-cell sample per district, not confirmed
> uniform across the whole district.

This is the single most important caveat in the whole system for anyone thinking about
real money: **a trigger is a reason to investigate or pay against an index, not proof
that any specific farmer actually lost anything.**

## Real baseline numbers across the project (not smoothed over)

| Module | Real number |
|---|---|
| National hazard trigger rate | 402/30,996 (1.30%) |
| Irrigation classifier held-out accuracy | 0.700 (below 0.792 majority baseline) |
| Canal water-stress head→tail gradient | 0.868 → 0.914 (r=0.569; elevation-confirmed) |
| Fusion U-Net vs. linear baseline (RMSE, n=12) | Model loses (19.28 vs 17.98 K at scale 1) |
| Residue-burning false-alarm fix | 95/243 → 2 (pilot) / 46 (national) after contextual redesign |
| Locust breeding risk, current | Flagged in 0/3 regions (partial: green-up detected in 2/3) |
| Exposure-risk rows removed as implausible | 1,041/1,338 (78%) |
| Trigger events, illustrative threshold (0.35) | 6 (0 farm-matched) — Week 4 number |
| Trigger events, demo threshold (0.20) | 192 (12 farm-matched) — this is actually the **Week 6** number after Track C's real crop-mix data landed, not a Week 4 result; included here for continuity but not internally consistent with the rest of this Week 1–4 snapshot. See the addendum for the current, further-recalibrated number. |
| Real farms loaded | 120/120, across 4/126 districts |

## Demo-day walkthrough (Week 4, as originally run — see addendum for the current scenario)

```
python naip/run_end_to_end_demo.py --district Layyah --threshold 0.20
```

**This exact command no longer reproduces a triggered event** — Week 9's real
crop-weighting recalibration dropped Layyah's real score to 0.0277, below even the
recalibrated 0.07 demo threshold. Left here as the literal Week 4 record of what was
run; see the addendum for the command that reproduces a real trigger today.

This ran the real, complete, reproducible path live, as of Week 4:

1. Reads the real national hazard archive (`hazards_district_national.json`) —
   real MSG-derived fog detection, Layyah district, 2026-07-06.
2. Fuses it with the real regional crop calendar (cotton, flowering stage on that
   date) and the Week 4 agronomic-plausibility mask (Layyah is a real cotton-belt
   district — this pairing is plausible).
3. `trigger_engine.py` fires a real, audited trigger event (`exposure_score=0.225`
   under the Week 4 formula — not comparable to Week 9's rescaled `exposure_score`,
   which tops out at 0.225 nationally), with basis risk stated on the record and
   payout stubbed.
4. `in_memory_registry.py` matches it against 47 real farm polygons in Layyah.
5. `sms_delivery.py` attempts delivery — real bilingual message formatted, sent via
   Twilio if credentials are set, otherwise an honestly-labeled stub record.

## What Week 5+ (post-MVP) would need to close the real remaining gaps

- Real per-farm crop-type ground truth (farmer-reported or a Pakistan-specific
  remote-sensing product that doesn't currently exist) — the single gap that would
  unlock genuine per-farm exposure risk instead of the district-level plausibility
  mask.
- A live PostGIS deployment — mechanically straightforward once Docker is available;
  does not by itself resolve the crop-type gap.
- Real telco credentials for live SMS/IVR delivery.
- Real WRF output that temporally overlaps the MSG archive, to make the frost/
  heat-wave/cold-wave WRF cross-check meaningful (zero date overlap since Week 1).
- Real 15-min-cadence MSG data, to unstub `cloud_burst`/`heavy_rain`.
- Real locust survey ground truth, to validate the SMAP/NDVI screening thresholds.
- Real claims/loss data, to actuarially calibrate the trigger threshold instead of
  the current illustrative 0.35/0.20 values.

None of these are code problems. All of them are the same pattern this project
surfaced honestly every single week: real satellite/model infrastructure, genuinely
missing ground-truth and partnership data.

## Addendum (Week 11) — what has changed since this report

This report is kept as the real Week 1–4 snapshot, not rewritten. The real current
state, for anyone reading this after Week 4:

- **Trigger thresholds recalibrated** (Week 9): 0.35 illustrative → **0.225**;
  0.20 demo → **0.07**. `exposure_score` now bakes in the real MNFSR crop-mix share
  as a weight, not just a gate — this rescaled the national max score to 0.225, which
  is why the old 0.35/0.20 numbers above no longer apply.
- **Demo scenario replaced**: Layyah/fog/cotton no longer clears the recalibrated
  threshold (real score 0.0277). Current real scenario: **Gujranwala / 2026-06-23 /
  uv_index × rice** (60.92% real MNFSR rice share, 18 real farms matched). Reproduce
  with `python naip/run_end_to_end_demo.py --district Gujranwala --threshold 0.07`.
- **Crop-mix data upgraded** (Week 6/9): 115/126 real districts now carry real
  MNFSR crop-area data (up from the Week 4 hand-classified mask everywhere); the
  remaining 11 (Gilgit-Baltistan + Azad Kashmir) stay on the hand mask after a
  trained model was tried and honestly rejected there (Week 9).
- **Three real trained models added** (Weeks 7, 8, 10–11): a fire classifier
  (F1=0.346 vs. the rule's F1=0.004, Week 7), a national crop-share regressor
  (wheat R²=0.581, cotton R²=0.507, rice R²=0.420, sugarcane R²=-1.120, Week 8), and
  a Sentinel-1 flood classifier (F1=0.738 vs. the rule's F1=0.143, Week 10) — the
  flood model's real live national screen (Week 11) found it currently can't tell
  ordinary monsoon wetting from 2022-flood-level change, and was deliberately kept
  out of the trigger-facing feed as a result. Full detail:
  `naip/docs/PHASE3_SYNTHESIS.md`.
