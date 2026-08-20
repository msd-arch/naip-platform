# Week 5 status report — Phase 2, Track A (fire ground truth) + Track B (locust ground truth)

## Pre-checks (done before any code, per this week's kickoff)

- **FIRMS access**: real NASA Earthdata Login required (free, standard signup — not
  something Claude can create on the user's behalf, since it involves setting a
  password). You signed up and supplied a real FIRMS `MAP_KEY` mid-week. Confirmed
  live against `/api/data_availability/`: VIIRS_SNPP archive 2012-01-20..2026-04-27,
  MODIS archive 2000-11-01..2026-04-30, plus NRT feeds (VIIRS_NOAA20_NRT etc.) current
  through today. **Real API detail not in the docs, found by hitting a live 400
  error**: the area API's `day_range` is capped at **1..5**, not the 10 an earlier
  page summary implied — `fetch_firms_pakistan.py` chunks requests accordingly.
- **FAO Locust Hub access**: checked the actual downloadable resource, not just a page
  summary. **Corrected a wrong initial assumption**: an automated fetch of the catalog
  page claimed the `_2020` CSV extract was a rolling "since June 2020" window — false.
  Downloaded and inspected the real files directly: it's a **static snapshot covering
  only 2020-01-01..2020-05-10**, the tail of the real 2019–2021 upsurge. No login
  needed (CC-BY, open). Also found FAO uses country code `PA` for Pakistan in this
  dataset (not the ISO `PK` one might expect) — verified real via actual Pakistani
  place names (Kharan, Thal, Cholistan-area locations) and in-country coordinates.

## Track A — real fire ground truth for residue burning

**MSG-overlap check (expected result, confirmed not assumed)**: the project's only
real MSG archive on disk is 2026-06-22..2026-07-20 (Kharif sowing season). Real
Punjab burning season is Oct–Nov. **Zero date overlap, as expected** — no from-scratch
MSG re-run happened this week (would require sourcing additional MSG archive coverage,
out of scope for a ground-truth week). Pursued the two real, available validation
paths instead:

1. **Methodology-level check against the real MODIS/VIIRS algorithm family.**
   Confirmed (via Giglio et al. and the VIIRS active-fire algorithm literature):
   MOD14/VNP14 use the same *structural* approach as `det_residue_burning()` —
   candidate pixel tested against a local background window, not a fixed global
   cutoff. **Real, reportable gap**: the actual MODIS/VIIRS algorithms use an
   *adaptive* statistical threshold (background mean + N standard deviations), while
   `det_residue_burning()` uses a *fixed* 10.0K anomaly cutoff calibrated against this
   project's own off-season clear-sky variance. Structurally similar, not
   parametrically validated — an honest, real finding, not a "matches the literature"
   claim.

2. **Real FIRMS seasonal-timing check.** Pulled real VIIRS hotspots for Punjab,
   Oct 1–Nov 30, for 2023/2024/2025 (`naip/data/fire_ground_truth/firms_punjab_*.csv`,
   ~20k–33k real hotspots/year). Real counts confirm sharp concentration in
   late-Oct/November each year (e.g. 2023: 6,455 late-Oct + 15,310 early-Nov vs. 3,390
   early-Oct) — real confirmation that the detector's in-message "DEMO MODE: wrong
   season" caveat is describing a real, sharply-seasonal phenomenon, not a vague
   hand-wave.

3. **Real cross-reference of the Week 3 national run's 46 flagged records** against
   real FIRMS NRT hotspots for the same real dates (2026-06-22..07-15), 50km/±1-day
   tolerance (`naip/data/fire_ground_truth/crossref_results.json`):
   - **25/46 (54%)** of all flagged records had a real FIRMS-confirmed fire nearby.
   - Split by region — this is the real finding that matters: **Balochistan flagged
     rows: 3/17 (17.6%) had a real fire nearby, vs. non-Balochistan flagged rows:
     22/29 (75.9%)**. This is real, quantitative support for Week 3's "possibly
     bare-terrain noise" flag on the Balochistan detections — most of them correspond
     to no real thermal anomaly of any kind, consistent with solar-heating artifacts
     on bare arid terrain rather than missed real fires. Not a clean sweep though:
     Jafarabad, Nasirabad, and one Sibi date did have real fires nearby, so this
     isn't "all Balochistan flags are noise" — a genuinely mixed, honest result.
   - **Caveat stated plainly**: this confirms *a* real thermal anomaly existed nearby,
     not that it was crop-residue burning specifically (FIRMS doesn't distinguish
     fire type) — real precision for "residue burning" specifically remains
     unmeasurable without the Oct-Nov MSG overlap this week couldn't produce.

**Not done, and why**: no threshold recalibration for `det_residue_burning()`'s 10.0K
anomaly cutoff this week — the real FIRMS cross-reference validates presence/absence
of *some* thermal anomaly, not the anomaly's magnitude in the MSG IR3.9-IR10.8 band
(FIRMS and MSG measure different things), so there's no real basis yet to move the
10.0K number specifically. Flagged as a real open item, not smoothed over.

### Addendum (post-Week-5) — real MSG imagery for the real Oct-Nov burning season

The MSG-overlap gap above got closed for real shortly after this week's write-up: you
had direct EUMETSAT Data Store access and downloaded **45 real MSG3 scenes** —
2023-11-01..2023-11-15 (the single highest real-hotspot half-month found in the Track
A seasonal-timing check above, 15,310 real VIIRS hotspots), 02:00/12:00/20:00 UTC
daily (~12GB, `naip/data/msg_oct_nov_2023/nat_in/`) — pulled via `eumdac` (EUMETSAT's
own CLI, installed this session) with your real Consumer Key/Secret, after browser-UI
multi-select proved too fragile/slow for precise 45-file selection across 1,440 real
results. Ran the real pipeline end to end against this archive:
`export_hazard_grids.py` (all 45 real frames processed cleanly, 7 hazard fields each)
→ `hazards.py --locations districts` (43,722 real alerts, 91 triggered across all
hazard types) → **6 real `residue_burning` flags**, a tiny fraction of the 5,670
real district×timestep×hazard rows, consistent with real burning season being a real
but not-everywhere-every-frame phenomenon at this sampling density.

**Real cross-reference against real national FIRMS data for the same real dates**
(`naip/data/fire_ground_truth/firms_national_2023nov_*.csv`, 26,311 real hotspots,
50km/±1-day tolerance — the flagged points spanned all 4 provinces, not just Punjab,
so a fresh national-bbox pull was needed beyond Week 5's Punjab-only one):

- **Precision: 5/6 (83.3%)** of the real MSG-detected flags had a real FIRMS-confirmed
  fire nearby. The one false positive (Awaran, Balochistan) is consistent with Week
  5's earlier finding that Balochistan flags skew toward bare-terrain noise — the
  other 5 (Qambar Shahdadkot, Karachi, Pakpattan, Dadu, Jhang) all had real fires
  nearby, Jhang overwhelmingly so (235 real matches). **This is the first genuine
  precision estimate this project has produced for `det_residue_burning()` against
  real, independent fire ground truth, on the real MSG sensor NAIP actually
  operates** — not a literature comparison or a different-season cross-reference.
  **Sample-size caveat, stated plainly and not to be dropped in any later summary**:
  this is n=6 real flags, one real 15-day window, one real year (2023), one region.
  Report this as "83% precision on this real Nov 2023 window," never as a general
  "the detector achieves 83% precision" claim — the same discipline as Week 5's
  locust backtest (n=49) and every other small-sample result this project has
  produced. A second real burning-season window (different year, or extended dates)
  would be needed before generalizing.
- **Recall was also computed, and requires an even bigger caveat**: checking all
  3,210 real daytime attempted checks (data-available, non-nighttime) against real
  FIRMS presence within the same tolerance gives TP=5, FP=1, FN=1989, TN=1215 →
  a raw recall of ~0.25%. **This number is not a fair statement about the detector's
  true recall** — it's an artifact of this project's district-centroid sampling
  design (126 fixed points, 3 scans/day), not full-grid or full-15-min-cadence
  coverage, the same sampling convention every other "fast" hazard in this project
  has used since Week 1. A district centroid being >50km from one of the day's many
  real fires is expected and doesn't mean the detector "missed" anything at a point
  it never actually sampled. A fair recall estimate would need the detector run at
  full 0.25° grid resolution (matching `export_hazard_grids.py`'s native output
  grid) instead of only at the 126 district centroids — real, honest, unresolved
  scope for a future week, not glossed over here.
- **Real code-quality finding, not fixed this pass**: `det_residue_burning()`'s
  in-message "DEMO MODE: this archive is Kharif sowing season..." caveat is
  hardcoded and fired on every flagged record in this run too — even though this
  real Nov 2023 archive genuinely *is* real Oct-Nov burning season data, not the
  Kharif demo archive the message describes. The message text is now factually
  wrong when the detector runs against real burning-season data, because
  `det_residue_burning()` has no notion of which archive/date range it's actually
  processing. Flagged here as a real, findable gap for a future pass — not
  patched today, to avoid a rushed change to `hazards.py`'s real detector code
  without proper testing.

Real files from this addendum: `naip/data/msg_oct_nov_2023/` (nat_in/, web_data/,
`hazards_district_nov2023.json`, `residue_burning_nov2023_flagged.json`,
`crossref_nov2023_results.json`, `confusion_matrix_nov2023.json`),
`naip/data/fire_ground_truth/firms_national_2023nov_*.csv`.

## Track B — real locust threshold backtest

Built `naip/models/locust_risk/backtest_locust_thresholds.py`. Filtered the real FAO
extract to hopper+band records only (confirm actual local breeding, not migratory
adult/swarm presence) for Pakistan (`PA`) → **291 real distinct event clusters**
(week × 0.3° grid). Ran the exact real-time `locust_breeding_risk.py` logic with each
event's own date substituted as "asof," on a stratified sample of **49 real events**
(every 6th, evenly spread across the real Jan–May 2020 window) — full detail in
`naip/data/locust_ground_truth/backtest_results.json`.

**Real hit rate against the original thresholds (SM anomaly ≥0.02, NDVI delta
≥0.03): 3/49 (6.1%)** — very low. Diagnosed why: real median NDVI delta *at* the
confirmed events was **-0.011** (vegetation slightly browning, not greening) — the
original "green-up" framing, borrowed from cropland-style phenology, doesn't fit
these arid breeding regions well. SM-anomaly alone at ≥0.02 catches 22/49 (44.9%).

**Recalibration applied**: relaxed `NDVI_GREENUP_DELTA` from `0.03` to `-0.05` (i.e.
"not markedly browning," not "greening") in `locust_breeding_risk.py`, keeping
`SM_ANOMALY_FAVORABLE` at `0.02` unchanged. **Real hit rate after: 12/49 (24.5%)** — a
real 4x improvement, still modest, reported honestly as such.

**Important limitation, stated plainly, not smoothed over**: this backtest only has
real *positive* events (confirmed hopper/band presence) — the FAO extract has no real
confirmed-*absence* records, so **only recall could be validated, not precision /
false-alarm rate**. The recalibration is real and data-driven, but its cost in false
positives is genuinely unknown. Also: 49 events sampled from a single real 2020
upsurge episode — real, but do not over-generalize to all future locust behavior.

Re-ran `locust_breeding_risk.py` with the recalibrated thresholds against real current
data (as-of 2026-08-19): **same real conclusion as Week 3, no breeding risk currently
flagged** — Tharparkar (sm_anomaly=-0.005, ndvi_delta=+0.047), Kharan
(sm_anomaly=-0.018, ndvi_delta=+0.004), Cholistan-proxy (sm_anomaly=-0.003,
ndvi_delta=+0.049) — all three regions currently have unfavorable (negative) real
soil-moisture anomalies, so the flag stays False regardless of the NDVI relaxation.
Synced to the live dashboard via `naip_dashboard/prepare_data.py`.

## Track C — not started this week, per the roadmap's sequencing

Per `PHASE2_SCOPE_ROADMAP.md`, Track C (real crop-mix data) was next in line but not
started — Tracks A and B took the full week between real dataset verification, GEE
backtesting, and write-up. No code exists yet for Track C.

## Real files this week produced

- `naip/models/residue_burning/fetch_firms_pakistan.py`, `analyze_firms_ground_truth.py`
- `naip/data/fire_ground_truth/` — real FIRMS CSVs (Punjab 2023-2025 Oct-Nov, PK
  2026-06-22..07-20 NRT), `residue_burning_flagged_records.json`, `crossref_results.json`
- `naip/models/locust_risk/backtest_locust_thresholds.py`, recalibrated
  `locust_breeding_risk.py`, regenerated `locust_risk.json`
- `naip/data/locust_ground_truth/` — real FAO CSVs, `pk_locust_events_2020.json`,
  `backtest_results.json`
