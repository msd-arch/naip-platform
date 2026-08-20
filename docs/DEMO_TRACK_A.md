# Track A: Real Fire Ground Truth for Residue Burning

*A demo-day narrative. Every number below is pulled directly from the real output
files — `naip/docs/STATUS_WEEK5.md`'s addendum, `naip/data/fire_ground_truth/`, and
`naip/data/msg_oct_nov_2023/` — not from memory of how the work happened.*

> **Addendum (Week 7, Track E) — read this before citing the 83.3% figure below.**
> Track E built a real full-grid (183,150-cell) version of this same real
> cross-reference, not just the 6 district centroids Section 3 describes. Replaying
> `det_residue_burning()`'s unchanged logic on that full grid gives **precision
> 13.2%, recall 0.4%** (TP=99, FP=653, FN=21,991) — far below 83.3%. This is not an
> error in either number: district centroids sit in towns and administrative
> centers, which are disproportionately near real agricultural land, not a
> representative sample of the full national grid (which includes large arid/
> mountain areas where the rule's fixed threshold fires on bare-terrain heating, not
> fire). **The 83.3%/n=6 result below is real and was correctly computed — it was
> also, unknowingly at the time, computed on a location-biased sample that flattered
> the rule.** Treat Section 3's number as a real early signal that motivated
> building the full-grid evaluation, not as the detector's actual precision. Full
> detail: `naip/docs/STATUS_WEEK7.md`.

## 1. The problem

`det_residue_burning()` was built in Week 3: a contextual local-background anomaly
test on MSG's IR3.9−IR10.8 channel difference, designed to flag widespread
crop-residue burning at regional scale. It has one structural weakness that sat
unresolved for two sprints: **it had never been checked against a real fire.** The
only MSG/SEVIRI archive on disk covered 2026-06-22 to 2026-07-20 — Kharif sowing
season. Real Punjab crop-residue burning happens Oct–Nov, post-rice-harvest. Every
flagged alert has carried an explicit "DEMO MODE — wrong season" caveat since Week 3
because of this gap.

Week 5 made real, partial progress without new MSG data: cross-referencing Week 3's
46 originally-flagged national records against real FIRMS hotspots for the same
(wrong-season) dates. That gave a real but limited signal — **25/46 (54%)** of the
flagged records had *some* real fire nearby, and splitting by region showed
Balochistan flags confirmed at only **3/17 (17.6%)** versus non-Balochistan flags at
**22/29 (75.9%)** — real evidence that Balochistan's flags skew toward bare-terrain
noise. Useful, but still a proxy: it validated presence of *some* thermal anomaly on
the wrong season's data, not the detector's actual behavior on real burning-season
imagery.

This week closed that gap for real: sourced real MSG archive data for the actual
burning season, on the actual sensor, and ran the actual detector against it.

## 2. The real pipeline

1. **EUMETSAT Data Store** → 45 real MSG3 scenes, **2023-11-01 to 2023-11-15**
   (02:00 / 12:00 / 20:00 UTC daily), ~12GB, downloaded via `eumdac` (EUMETSAT's own
   CLI) using real API credentials. This exact 15-day window was chosen because it
   was already known, from Week 5's seasonal-timing check, to be the single
   highest-density real burning window on record — 15,310 real VIIRS hotspots in
   Punjab in that half-month alone, more than any other half-month checked across
   2023–2025.
2. **`export_hazard_grids.py`** — all 45 real frames processed cleanly (no channel
   failures), producing the 7 real hazard fields `det_residue_burning()` and the
   other detectors need, at the same 0.25° grid resolution used everywhere else in
   this project.
3. **`hazards.py --locations districts`** — the real detector engine, run exactly as
   it runs every other week, at the project's standard 126-district-centroid
   sampling resolution. Output: 43,722 real alerts across all hazard types, of which
   **6** are real `residue_burning` flags (out of 5,670 real district×timestep×hazard
   rows for that hazard alone).
4. **Cross-reference against real FIRMS ground truth** — a fresh national-bbox FIRMS
   pull for the identical real dates (`firms_national_2023nov_*.csv`, **26,311 real
   hotspots**). A national pull was necessary, not a Punjab-only one: the 6 flagged
   districts (Qambar Shahdadkot, Karachi, Pakpattan, Awaran, Dadu, Jhang) span all
   four provinces, not just Punjab. Same tolerance as every prior cross-reference
   this project has used: 50km, ±1 day.

## 3. The real result

**5 of 6 real flags (83.3%) had a real FIRMS-confirmed fire within 50km/±1 day.**

| District | Date | Real FIRMS matches nearby |
|---|---|---|
| Qambar Shahdadkot | 2023-11-04 | 4 |
| Karachi | 2023-11-04 | 5 |
| Pakpattan | 2023-11-10 | 16 |
| **Awaran** | 2023-11-12 | **0 — false positive** |
| Dadu | 2023-11-12 | 2 |
| Jhang | 2023-11-13 | **235** |

The one false positive is **Awaran, Balochistan** — and this is what makes the
result credible rather than a lucky draw: it lands exactly where Week 5's
independently-derived finding said it would. Week 5 found, from a completely
different dataset and a completely different (wrong-season) time window, that
Balochistan flags confirm at 17.6% versus 75.9% elsewhere. This week's single
Balochistan flag, on real burning-season data, on the real sensor, was the one that
missed. Two independent checks, two weeks apart, pointing the same direction.

The strongest confirmed true positive is **Jhang, Punjab, 2023-11-13** — 235 real
FIRMS hotspots within the tolerance window. Jhang is a real, major Punjab
agricultural district; this isn't a marginal one-hotspot coincidence, it's a
dense, unambiguous real fire signature.

## 4. What's deliberately not claimed: recall

Recall was computed, not skipped — and then deliberately excluded from the headline
result. Checking all 3,210 real daytime attempted checks (data available,
non-nighttime) against real FIRMS presence gives a confusion matrix of
**TP=5, FP=1, FN=1989, TN=1215** → a raw recall of **~0.25%**.

This number is not reported as "the detector's recall" because it isn't a fair one.
It's an artifact of this project's sampling design: `hazards.py` samples 126 fixed
district centroids, 3 times a day — not a full 0.25° national grid, and not every
15-minute frame. On any given real day in this window, real fires are numerous and
scattered across the country; a district centroid landing >50km from one of them is
the expected outcome of sparse point-sampling, not evidence the detector "missed" a
fire it was never actually run on. A fair recall estimate would require running
`det_residue_burning()` at full grid resolution — matching `export_hazard_grids.py`'s
native output grid rather than 126 centroids — which is real, acknowledged, unbuilt
scope, not a result papered over here.

## 5. Sample-size framing

Said once, plainly, so it doesn't need restating defensively later: this is
**83% precision on this real 15-day window, n=6** — not "the detector achieves 83%
precision." One window, one year (2023), six flagged records. A second real
burning-season window — a different year, or an extended date range — would be
needed before this becomes a general claim about the detector's precision.

## 6. Anticipated questions

**"Isn't n=6 too small to mean anything?"**
Yes, on its own. Six data points alone would not be a persuasive result. Its value
comes from being *consistent with* an independently-derived finding from two weeks
earlier — the Balochistan noise pattern — not from the raw sample size. Two small,
independent, differently-sourced checks landing on the same conclusion is a
stronger signal than either alone, even though neither is individually large.

**"Why not report recall?"**
Because the honest recall number here (~0.25%) measures sampling density, not
detection capability — see Section 4. Reporting it as a headline figure would be
actively misleading about what the detector can do; reporting it at all, with the
real explanation, is more honest than omitting it.

**"Is this circular with the FIRMS ground truth?"**
No — and this is the important distinction, not just a disclaimer. `PHASE3_MODEL_PLAN.md`
flags a real circularity risk for Track E: training a classifier on
MODIS/VIIRS-*derived* features to predict MODIS/VIIRS-derived FIRMS labels would be
re-deriving FIRMS's own algorithm, not a real result. This week's validation is the
opposite case: `det_residue_burning()` runs entirely on MSG/SEVIRI thermal channels
— a geostationary instrument with a different sensor, different orbit, different
spatial/temporal sampling than the polar-orbiting MODIS/VIIRS instruments FIRMS is
built from. Checking MSG-derived detections against FIRMS ground truth is genuine
cross-sensor validation, not a model checking its own labels.

**Known loose end, logged rather than hidden**: `det_residue_burning()`'s in-message
"DEMO MODE: this archive is Kharif sowing season, not Punjab's real Oct-Nov burning
season" caveat is hardcoded and fired on every one of this week's real flags too —
even though this archive genuinely *is* real Nov burning-season data. The message is
now factually wrong when the detector runs against real burning-season input,
because it has no notion of which archive/date range it's actually processing.
Flagged, not yet patched — deliberately, to avoid a rushed change to the real
detector code without proper testing.

## 7. What this does — and doesn't — settle for Phase 3 / Track E

This result is real validation of the **existing rule-based detector**: a genuine,
non-circular precision estimate against independent, cross-sensor ground truth, on
real burning-season data, on the sensor NAIP actually operates. In the loose sense of
"show me the detector tested against real data," this is already a strong, defensible
answer — 83% precision on a real window is not a weak result to present.

It is **not** the trained classifier `PHASE3_MODEL_PLAN.md`'s Track E describes. No
model was fit; no held-out spatial/temporal split was constructed; no comparison
against a trained baseline exists. The plan's specific concern was evaluators asking
for "a real AI model, trained on a real dataset, with demonstrated applicability and
testing" — a rule-based detector's real validation result, however credible, does not
answer that specific question, even though it substantially strengthens the case that
a validated rule-based detector already exists as a real baseline for a future model
to beat.

**This is flagged as an open question, not decided here**: does this week's real
result change whether Track E (training a real classifier) is still worth building,
or does it now serve primarily as Track E's honest baseline to beat (Step 3 of the
Track E plan already calls for comparing a trained model against "the current fixed
10.0K contextual-anomaly cutoff" — that comparison is now backed by a real number,
83% precision, rather than an unvalidated rule)? Waiting for direction before Track E
starts.
