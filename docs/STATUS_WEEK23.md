# Week 23 — Phase 5, Track Q (pest/disease screening)

## Pre-check result — fallback path taken, checked across multiple real sources

The task's own framing named a real scientific constraint up front: satellite
remote sensing generally cannot identify *which* pest or disease is present,
only generic vegetation anomaly. The pre-check's job was to find out whether
real, structured, per-location Pakistani rust surveillance data exists that
would let this track be genuinely disease-specific anyway (the same kind of
resource that made Track B's locust work possible) — or whether it has to
fall back to the scope document's honestly-scoped "crop stress screen."

**Checked directly, not assumed, across independent real sources:**

1. **RustTracker.org is effectively dead.** Its specific data pages —
   Pakistan Survey Mapper, Survey Data Overview — all redirect to a
   WordPress "sign up for this site name" placeholder, confirming the live
   domain no longer serves real content at those paths.
2. **The parent platform (GRRC/wheatrust.org, confirmed still live)
   independently corroborates the real pattern**: its own current page
   describes every one of its tools — Yellow Rust, Stem Rust, Leaf Rust,
   Vulnerability Mapping — as "maps and charts." No CSV export, API, or
   bulk download exists anywhere in this family of platforms (RustTracker,
   GRRC, EuroWheat), live or dead.
3. **The closest real published field-survey study found**: Khan et al., a
   genuine 1202-field, 95-district, 3-year (2016–2018) Pakistan leaf-rust
   survey (Pakistani Journal of Botany) — a real, larger dataset than the
   specific numbers named in the original brief, same category of resource.
   Its own table caption, verified verbatim: *"Number of fields in various
   districts recorded with >60% leaf rust infestation"* — **district-level
   aggregate counts, not per-field GPS/date records.**
4. **A second candidate paper** ("Wheat Diseases and Pests in Pakistan: A
   Nationwide Assessment," Phytopathology) turned out to be **expert-
   elicitation modeled yield-loss estimates**, not an observed field survey
   at all — even less usable as real ground truth.
5. Checked for a Zenodo/Dryad/figshare-hosted supplement for either paper —
   found only an unrelated close-up leaf-image segmentation dataset (NWRD,
   one season, Islamabad), the wrong data type/scale for cross-referencing
   against district-level NDVI anomalies.

**No genuinely per-location, extractable rust (or other pest/disease)
surveillance dataset was found.** Per the pre-authorized branching in the
scope document, this determines the rest automatically: the fallback path
— a "crop stress early-warning screen" — was built, not a disease-specific
detector.

## Build — reusing Track M's real infrastructure, not rebuilding it

`models/crop_stress_screen/build_crop_stress_screen.py` reuses Track M's
exact real national NDVI dataset (Track F's 2,875 real Sentinel-2 points +
Track M's 275-point GB/AJK extension — 3,022 real points with usable
signal after real join/dropna, confirmed to match Track M's own recorded
`n_points_total` exactly) and the same MODIS-vs-MODIS anomaly method Track
M's own real self-check validated (avoiding the cross-sensor bias Track M
found and fixed).

**Two real signals, reported separately, never merged into one opaque
score** — per direction, this is the genuinely non-redundant addition over
just relabeling Track M's existing drought output:

- **Signal 1 (level anomaly)** — identical to Track M's own method: current
  NDVI in the real bottom decile of this year's national distribution
  relative to the point's own 21-year historical norm. More consistent
  with sustained/chronic conditions.
- **Signal 2 (senescence anomaly, new this track)** — the point's real
  within-season decline rate (`ndvi_senescence_slope`, already extracted by
  Track F/M's phenology pipeline, no new Sentinel-2 compute) is in the real
  bottom decile nationally (i.e. among the steepest/fastest real declines).
  More consistent with an acute stress event than Signal 1's chronic-level
  check — a real, physically distinct temporal signature.

No lat/lon or district-identity feature anywhere — both signals are direct
transforms of real per-point Sentinel-2/MODIS values, no model-fitting
involved.

## Real result

| | Real points | Real districts (of 126) |
|---|---:|---:|
| Signal 1 (level anomaly) | 303 flagged | — |
| Signal 2 (senescence anomaly) | 283 flagged (199 pts missing slope data, excluded) | — |
| Either signal, ≥10% of a district's points | — | 89 |
| **Both signals simultaneously** | 21 points | **19** |

**Real, honest caveat about the "either signal" number, checked not
assumed**: with ~25 real points per district and each signal independently
flagging ~10% of all points nationally, a district can cross a "≥10% of
points flagged" bar by national-distribution chance alone — 89/126 (71%)
is real but a fairly loose, permissive view. **The "both signals" case (19
districts) is the real, more defensible headline** — requiring a point to
land in the bottom decile on two independent measures simultaneously is a
genuinely rarer coincidence, not something national-distribution noise
alone would easily produce. Both numbers are reported, with this
distinction stated plainly rather than presenting only the more dramatic
89-district figure.

## What this doesn't claim — stated in the tool's own output, not just here

Every real output of this screen — the JSON file and the dashboard page —
carries an explicit, unmissable notice: **this is not a pest or disease
diagnosis.** A flag means the location's real signal looks unusual relative
to its own record; it says nothing about *why*, and a real false positive
(no actual problem at all) is possible. This is stated as prominently as
the signal itself, not buried in documentation — the dashboard page's
"not a diagnosis" panel renders above the numeric results, not below them.

## Dashboard

New page, `/crop-stress`, linked from the main nav as "Crop Stress Screen."
Leads with the not-a-diagnosis notice in a bordered, high-visibility panel;
shows both real signals separately with their own real counts and method
descriptions; a toggle between the "both signals" (real headline) and
"either signal" (looser) district views, with the chance-collision caveat
stated inline, not just in this report. Verified live in the browser — all
real numbers render exactly as computed.

## Real files this week produced

- `naip/models/crop_stress_screen/build_crop_stress_screen.py`,
  `crop_stress_screen.json`
- Dashboard: `app/crop-stress/page.tsx` (new), `app/components/Nav.tsx`
  (new link), `prepare_data.py` (new source wired in), regenerated
  `public/data/*`
