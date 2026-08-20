# Week 6 status report — Phase 2, Track C (real crop-mix data)

## Pre-checks (done before any code, per this week's kickoff)

- **PBS Agriculture Statistics granularity**: the province-level PBS tables are real and
  easy to find, as expected — but the real find was a different, better federal source:
  the **Ministry of National Food Security & Research (MNFSR)**'s own publication,
  "Crops Area & Production (District wise) 2022-23"
  (`mnfsr.gov.pk/SiteImage/Downloads/Crops Area AND Production by 2022-23.pdf`, and a
  2021-22 companion PDF), downloaded directly (2.5MB + 6.3MB real files,
  `naip/data/crop_mix_ground_truth/`). Its own foreword states the source: "crop
  estimates supplied by the Crop Reporting Services of Provinces and compiled by the
  Ministry... (Economic Wing)" — i.e. **this single federal document already compiles
  all four provincial CRSs' real district estimates**, including Sindh and
  Balochistan, whose own CRS web presence is weak/absent (confirmed by checking their
  websites directly — Balochistan's CRS has no working web presence, matching what
  the original roadmap suspected). **This changed Track C's scope for the better**: no
  Punjab-only / some-provinces-missing split turned out to be necessary. Real district
  rows for Balochistan (verified directly, e.g. Nasirabad, Jaffarabad, Khuzdar all have
  genuine nonzero wheat area/production, not placeholder zeros) confirm this isn't
  degenerate coverage.
- **Kaggle Punjab dataset**: confirmed Punjab-only by its own title
  ("Crop District level dataset(Punjab, Pakistan)") — not used, since the MNFSR
  document already covers Punjab at the same granularity plus the other three
  provinces, making a second Punjab-only source redundant this week.
- **Time range**: only **2 real years** (2021-22, 2022-23) in the MNFSR district-wise
  table. Combined with hazards.py's real MSG archive being a single ~1-month window
  (2026-06-22..07-20), there is no multi-year hazard-frequency series to correlate
  against yield at all — **the exploratory hazard-frequency-vs-yield-dip analysis from
  the roadmap was confirmed structurally unbuildable this week**, not just
  data-thin. Per your direction, skipped rather than forcing a spurious n=1 result.
- **51 crops, both years, all 4 provinces** are in the document — genuinely rich, not
  a coarse summary table.

## What was built

- `naip/models/fusion/parse_mnfsr_crop_mix.py` — parses the real MNFSR PDF text
  (via `pdftotext -layout`) into real per-district, per-crop area/production for
  wheat/cotton/rice/sugarcane. **Cross-validates every parsed province+crop block
  against that block's own printed provincial Total line (5% tolerance)** — a cell is
  only accepted as real if it reconciles; rows that fail (the report's raw table
  layout doesn't survive text extraction cleanly everywhere, notably Balochistan's
  cotton table) are rejected and reported, not guessed at. Real result:
  **4 of ~16 province×crop blocks rejected** (Sindh cotton had a duplicate/garbled
  extraction alongside a valid one — the valid one was kept; Sindh sugarcane failed
  cross-validation in both attempts and stayed unreliable; Balochistan cotton's table
  layout doesn't survive extraction). District name matching required a real mapping
  table (abbreviations like "M.B. Din"→Mandi Bahauddin, "Rahimyar Khan"→Rahim Yar
  Khan) plus **a genuine finding about this project's own district set**: several real
  Pakistani districts the MNFSR report names (Larkana, Washuk, Bolan, Harnai,
  Sherani, Tor Ghar) have **no corresponding polygon at all** in
  `pk_districts.geojson` (an older geoBoundaries vintage) — their real MNFSR rows are
  reported but correctly left unmapped rather than force-matched to a wrong
  neighboring district. Separately, 5 newer Punjab district splits present in MNFSR
  but absent from our polygon set (Chiniot, Nankana Sahib, Kot Addu, Talagang,
  Wazirabad) were correctly merged into their real pre-split parent district (Jhang,
  Sheikhpura, Muzaffargarh, Chakwal, Gujranwala respectively) so their real area isn't
  silently dropped.
- **Real coverage result**: **115/126 real districts** now have real MNFSR
  district-area data for at least one of the 4 crops (up from 0 real districts before
  this week — Week 4's mask was 100% hand-classified). The 11 uncovered are exactly
  Gilgit-Baltistan's 10 districts + Azad Kashmir — **confirmed, not assumed**: no GB or
  AJK district appears anywhere in the MNFSR document, consistent with it being a
  four-province federal compilation. These 11 keep the Week 4 hand-classified mask
  (already correctly "no plausible crop" for the 10 GB ones).
- **Tier field propagated end to end**, per direction: `naip/models/fusion/
  real_crop_mix.py` exposes `crop_mix_tier()`/`crop_share()`/`is_plausible_real()`.
  `exposure_risk.py`'s `resolve_plausibility()` prefers real data over the hand mask
  wherever real data actually answers the (district, crop) question, falling back to
  the mask only where real data can't (the 11 uncovered districts, or a specific
  rejected crop table for an otherwise-covered district). Every exposure_risk.json row
  now carries `crop_mix_source` (`real_district_area` / `hand_classified_mask`) and
  `crop_mix_share_of_4crop_area` (the real proportion, or null). `trigger_engine.py`'s
  audit records carry both fields through to the final trigger-contract log —
  confirmed: **all 8 real national trigger events at threshold 0.35 now trace to
  `crop_mix_source: "real_district_area"`**, with real shares ranging from 0.87%
  (Kasur cotton — real, but a minor crop there) to 48.95% (Sialkot rice — a real
  dominant crop). `BASIS_RISK_NOTE` updated to explain the tier distinction rather
  than implying every trigger still runs on the coarse hand mask.
- **No change to `exposure_score`'s formula shape** this week, per direction —
  `agronomically_plausible` is still a boolean gate, just now backed by real data
  where available. Using the real proportional share as a scoring *weight* (not just a
  gate) is a real, natural next step but was explicitly deferred pending your
  confirmation, not done unilaterally.

## Real effect on existing numbers (honest before/after, not smoothed over)

Re-ran the full pipeline against the same real hazard archive Week 4 used
(`hazards_district_national.json`, 35,532 alerts, 1,338 nonzero-exposure rows —
identical row count confirms this is a like-for-like real comparison, not a different
run):
- **Agronomically-implausible nonzero rows**: Week 4 (hand mask only) 1,041/1,338
  (78%) → Week 6 (real data preferred) **750/1,338 (56%)**. The real crop-mix data is
  measurably more permissive/precise than the hand-classified guess in both
  directions — some hand-mask "implausible" pairings turned out to have real
  (if small) area, and some hand-mask "plausible" ones turned out to be real zeros.
- **National trigger events at threshold 0.35**: Week 4 **6 events, 0 farm-matched** →
  Week 6 **8 events, 0 farm-matched** (still zero farm matches — the 120-farm seed
  still only covers 4/126 districts, an unrelated real gap Track C doesn't touch).
- **Demo-threshold (0.20) run** (`run_end_to_end_demo.py --district Layyah`): Week 4
  **192 events, 12 farm-matched** → Week 6 **320 events, 16 farm-matched**. The
  headline Layyah/fog/cotton demo scenario itself is unchanged (Layyah is a real
  cotton district in both the hand mask and the real MNFSR data) — the shift is in
  the broader national trigger count, a real consequence of more accurate
  district-crop matching elsewhere.
- Dashboard synced (`naip_dashboard/prepare_data.py`) — `exposure_risk.json`,
  `trigger_summary_national.json`, `trigger_summary_demo.json`, both audit logs all
  reflect the real Track C data now.

## Real files this week produced

- `naip/data/crop_mix_ground_truth/` — real MNFSR PDFs + extracted text,
  `real_crop_mix.json` (115-district real proportional crop-mix), `parse_report.json`
  (real coverage/validation detail, including the 4 rejected province×crop blocks)
- `naip/models/fusion/parse_mnfsr_crop_mix.py`, `real_crop_mix.py`
- `naip/models/fusion/exposure_risk.py` — `resolve_plausibility()` added, new
  `crop_mix_source`/`crop_mix_share_of_4crop_area` fields
- `naip/backend/insurance_engine/trigger_engine.py` — audit records + `BASIS_RISK_NOTE`
  updated to carry the tier field
- Regenerated: `exposure_risk.json`, `exposure_risk_top*.csv`, `audit_log.jsonl`,
  `audit_log_demo.jsonl`, `trigger_summary_national.json`, `trigger_summary_demo.json`,
  `delivery_log.jsonl` (+1 record), synced dashboard `public/data/`

## Decisions confirmed with you this week

- **Provinces with no real district-level source**: turned out not to be a real
  question — all four provinces have real district-level data via the single MNFSR
  compilation. The only real fallback-to-hand-mask cases are the 11 GB/AJK districts
  (outside MNFSR's mandate entirely) and a handful of rejected crop-table cells —
  handled with the default (fall back to Week 4's hand-classified mask) since no
  alternative was needed.
- **Yield-correlation analysis**: confirmed skipped, real reason reported above (the
  hazard side has no multi-year real data regardless of the crop side's year range).
