# NAIP — Phase 3 Synthesis (Weeks 5b–11): Real Trained Models, Validated and Deployed

*This is the connected story underneath six weeks of separate status reports —
`STATUS_WEEK5.md`'s addendum, `STATUS_WEEK7.md`, `STATUS_WEEK8.md`, `STATUS_WEEK9.md`,
`STATUS_WEEK10.md`, `STATUS_WEEK11.md`, and `DEMO_TRACK_A.md`. Every number below is
pulled from those documents, not from memory of how the work happened; go there for
full detail, not repeated here. Updated Week 11 to fold in Track D (flood risk) and
its live-integration result — the phase's third trained model.*

## What Phase 3 set out to do

Phase 1–2 produced real, calibrated, rule-based detectors and threshold-tuned
screening logic — not a trained model. For evaluators asking, specifically, for "a
real AI model, trained on a real dataset, with demonstrated applicability and
testing," a validated rule is not the same answer, however honestly reported. Phase
3's actual goal, stated plainly in `PHASE3_MODEL_PLAN.md`: produce a result that
survives that specific scrutiny — real labels, real held-out evaluation, honest
baselines, no circular validation. Two tracks were scoped for this (Track E: fire
classifier; Track F: crop classifier), sequenced so Track E's methodology — and its
mistakes — could inform Track F before it started.

## The throughline: sampling density silently shapes evaluation results

The single strongest finding across this phase isn't in any one track's numbers —
it's a bias that was discovered three separate times, in three different systems,
because of one consistent habit: check the real number at the real resolution being
deployed at, not wherever it's convenient to measure.

1. **Track A** validated `det_residue_burning()` — the existing rule — against real
   FIRMS ground truth for the first time, at the project's standard sampling
   resolution: 126 district centroids. Result: **83.3% precision (5/6 flags
   confirmed)**.
2. **Track E**, needing a real trainable dataset, was forced to build one at full
   0.25° grid resolution (183,150 real cells) instead of the 126-centroid sample.
   Replaying the *same unchanged rule* on that full grid gave **13.2% precision,
   0.4% recall** — nowhere near 83.3%. The cause: district centroids sit in towns
   near real agricultural land, a real but invisible sampling bias, not a
   representative sample of a national grid that also includes large arid and
   mountain areas where the rule's fixed threshold fires on bare-terrain heating.
   Track E didn't just report this — it went back and corrected `DEMO_TRACK_A.md`'s
   already-published 83.3% figure rather than leaving two contradictory real numbers
   standing.
3. **Track G**, wiring the trained model back into the live district-centroid
   pipeline, found the *same bias, independently, in the opposite direction*: the
   model flags 69.3% of records at district centroids, versus 13.2% on its own real
   full-grid test set. Different model, same root cause, rediscovered without
   knowing in advance it would reappear.

Sampling density biased a rule-based precision figure upward and a trained model's
positive rate upward, at the same sampling resolution, for related but distinct
reasons — and the project caught both because it kept checking the number that
actually matched the resolution being deployed at, not the resolution that was
already computed. That discipline, not any single F1 score, is Phase 3's real
methodological result — and Week 11's Track D integration found a fourth instance of
the same underlying discipline paying off, in a genuinely different shape: not a
*where*-you-sample bias, but a *when*-you-compare-to bias. The live flood screen
flagged 122/126 districts; checked before being reported, the cause turned out to be
that the model's only real non-flood training examples came from the same 2022
monsoon as its flood examples, so it cannot yet tell an ordinary monsoon apart from a
disaster one. Same root habit — check the real number against the real conditions
being deployed into, not the conditions the model was validated under — different
axis of the problem (time, not space). See "Track D" below.

## Track A — the validation that made everything after it possible

Not a trained model — real validation of the existing rule, and the reason Track E
had real ground truth to build on at all. Sourced 45 real MSG3 scenes for Nov 1–15,
2023 (the real burning-season window with the highest known FIRMS hotspot density,
15,310 real hotspots in that half-month) via `eumdac`, the first time this project's
MSG archive covered the season `det_residue_burning()` was built for. Cross-referenced
6 real flags against a real national FIRMS pull (26,311 hotspots): **5/6 (83.3%)
precision** — later revealed, by Track E, to be a real number computed on a
sampling-biased set of points, not a wrong one. Full detail: `DEMO_TRACK_A.md`
(including its own Week 7 correction addendum).

## Track E — the first real trained model

Built a real 183,150-row grid-cell dataset (national 0.25° grid, 45 real MSG frames,
real FIRMS labels, 50km/±1-day tolerance, 12.06% positive) and a real temporally-blocked
split (train Nov 1–10, val 11–12, test 13–15 — whole dates held out, not individual
points).

**The near-miss, caught before it shipped**: a model trained with lat/lon as features
scored F1=0.728 (P=0.603, R=0.919) — outstanding, and wrong to report as-is. Real
permutation feature importance showed lat/lon at 0.57–0.61 versus every thermal
feature at ≤0.006: the model was mostly memorizing *where* November fires happen, not
reading the MSG thermal signature. Shipping that number would have been an honest
mistake with a dishonest-looking outcome — a "satellite fire detector" that's mostly
memorizing geography.

**The real, defensible headline**: thermal-only features (no lat/lon), same held-out
test set — **P=0.245, R=0.587, F1=0.346, ROC-AUC=0.737** — clearly and substantially
beating the unchanged rule-based detector evaluated on identical data: **P=0.200,
R=0.002, F1=0.004** (and, at the full-grid resolution Track A couldn't reach:
**P=13.2%, R=0.4%**). The with-geo run stayed in the record as a named ablation
finding — "geography alone is a strong prior, thermal signal alone is real but
harder, combining carelessly lets a model coast on geography" — not a competing
result. Full detail: `STATUS_WEEK7.md`.

## Track F — the second real trained model

**The collapse correctly avoided before building anything**: the literal
"classifier" framing — predict each district's single dominant crop — was checked
against real MNFSR data before any sampling pipeline was built, and found
degenerate: wheat dominant in 107/115 (93%) real districts, the same single-class
collapse Week 2's cropland task hit. Redesigned, confirmed with direction, as
multi-output regression on real per-crop area shares instead.

**Real national sample**: 2,875 real Sentinel-2 cropland points across all 115
MNFSR-covered districts, real NDVI/NDWI/EVI phenology-curve features, no lat/lon or
district-identity feature *from the start* — Track E's lesson applied preventatively.

**The WorldCereal↔MNFSR wheat cross-check needed two self-caught corrections before
it could be trusted**: a first raw-area-fraction comparison gave a spurious -0.53
correlation, caused by comparing WorldCereal's share of *total district area*
against MNFSR's share of *cropped area* — a denominator bug in the cross-check's own
arithmetic, found before reporting it. Fixed, the correlation flipped to +0.42 — and
then revealed a second, real issue: 42/97 districts showed WorldCereal's own
`wintercereals` and `temporarycrops` products disagreeing with each other (a ratio
exceeding 1.0, a mathematical impossibility). Final clean comparison: 52 districts,
correlation **0.118** — real, weak agreement, reported as a finding; MNFSR stayed
the sole label source, confirmed with direction.

**Real headline (GBT, district-level, held-out test districts)**: wheat R²=0.581,
cotton R²=0.507, rice R²=0.420, all clearly beating the constant-baseline. **Sugarcane
R²=-1.120 — a real, reported failure**, not folded into an average: the crop's small
real national share (2.6%) and thin weak-label signal weren't enough to learn from.
Full detail: `STATUS_WEEK8.md`.

## Track G — closing the loop

Both trained models now run inside the real pipeline, not just in benchmark reports.

- **The GB/AJK model attempt**: Track F's crop-share model was built, tested, and
  correctly rejected for the 11 real districts MNFSR data doesn't cover — predictions
  clustered near the national mean regardless of real terrain, and 3/11 districts
  predicted an impossible negative crop share. Confirmed with direction: all 11 stay
  on the Week 4 hand-classified mask. Track C's real, final status: **115/126 real,
  11/126 hand-mask, deliberately reviewed** — not the 126/126 "real-or-model"
  coverage a first guess might have hoped for.
- **Exposure-score reweighting**: `crop_weight` (real MNFSR share) now multiplies
  into `exposure_score` instead of only gating it — confirmed with real before/after
  first (Kasur cotton 0.87% share: 0.468→0.004; Sialkot rice 48.95% share:
  0.39→0.191). The real consequence: national max score fell to 0.225, breaking the
  old 0.35/0.20 thresholds and the demo pipeline outright. Recalibrated as two
  *separate* decisions, not one number picked to satisfy both: new thresholds
  (0.225 illustrative, 0.07 demo) chosen by matching the *old* thresholds' real
  selectivity against the new distribution; then, separately, an honest check of
  whether the Layyah/fog/cotton demo scenario still qualified. It didn't (real score
  0.0277). Rather than patch around that, the demo scenario changed to
  **Gujranwala/uv_index/rice** (60.92% real rice share, 18 real farms matched),
  found by searching real qualifying data, not chosen to preserve a story.
- **The fire classifier in production**: added alongside `det_residue_burning()` in
  `hazards.py` — the rule itself verified unchanged (identical 43,722 alerts / 6
  flags). This is where the throughline closed: the model's real score, run at
  district centroids against the real Nov 2023 archive, showed a 69.3% positive rate
  versus 13.2% on its own full-grid test evaluation — the same sampling bias, this
  time discovered in a trained model rather than a rule, and reported as a real
  ranking-only caveat rather than a calibrated rate. Full detail: `STATUS_WEEK9.md`.

## Track D — the third real trained model, and the first live one

**The circularity avoided before building anything**: the most convenient real label
source, TU Wien/JRC's Sentinel-1-derived flood map for the 2022 event, was
deliberately not used — it's built from the same instrument as the model's own
input, the Track E with-geo trap in a different shape. A genuinely independent
source was found instead: IOM/Shelter Cluster's real government-declared "Calamity
declared districts" list (16 Sept 2022) — 96/126 real districts matched, after
catching and fixing a real PDF-extraction column-misalignment bug.

**Real headline (training, `STATUS_WEEK10.md`)**: GBT F1=0.738 (P=0.817, R=0.674) on
a real spatially-blocked district split, clearly beating the established
SAR-threshold rule's F1=0.143 (P=1.000, R=0.077 — real but far too conservative).
Real, reported, unresolved limitation from the start: `jrc_occurrence` contributed
almost nothing (0.0012 importance) — the permanent-water baseline the model was
built to use for discounting rivers/lakes isn't doing what it was included to do.

**The integration (`STATUS_WEEK11.md`) is where Track D diverges from Track E/F**:
Track D's real inputs are live, not frozen, so Week 11 ran the trained classifier
against real *current* Sentinel-1/JRC conditions instead of replaying 2022 —
something Track E's fire model, bound to a fixed archive, cannot do. The real result
was 122/126 districts flagged — checked before being reported, and traced to a real,
newly-discovered limitation: the live 2026 national-average Sentinel-1 signature
sits almost exactly on the 2022 training data's *flooded*-class centroid, not the
*not-flooded* one, because the model's non-flooded training examples were other
districts during the same 2022 monsoon — it has never seen an ordinary,
non-disaster monsoon to compare against. **Decided after seeing this result**: not
merged into `district_alerts.json`'s trigger feed (a tested merge script exists but
was deliberately not run) — reported instead on `/models-in-production`, including
the real score distribution (min 0.445, median 0.683, max 0.938), not just the
binary flag count, since a real gradient exists under the near-universal flag that
may be useful for a future recalibration.

## What this phase actually proves

Three real trained models exist. Each was evaluated with a real held-out split
matched to its own autocorrelation risk (temporal for Track E, spatial-district for
Track F and Track D), a real baseline (the unchanged rule for Track E and Track D;
majority/constant-share and a historical Week 2 comparison for Track F), and a real
self-check discipline that caught three near-misses before they shipped or were
deployed as claimed: Track E's lat/lon leak, Track F's GB/AJK extrapolation failure,
and Track D's live monsoon-vs-disaster confusion. Two of the three (Track E, Track F)
are running inside the live product's scoring/alerting logic
(`hazards.py`/`exposure_risk.py`); Track D's live screen runs and reports honestly
but was deliberately kept out of the trigger-facing feed once its real limitation
was found — a difference in deployment status, stated plainly, not glossed as
parity with the other two.

**What this does not claim**: none of the three models is a finished, deployable
system. `model_score` (Track E) is a real relative-ranking signal at current
sampling density, not a calibrated probability — stated explicitly, not implied. The
crop-share model's sugarcane prediction is a real, unresolved failure. Track D's
live score is currently unable to distinguish ordinary monsoon wetting from a real
flood disaster and is not currently trustworthy as a trigger input. All three models
were trained on a single real time window (a 15-day fire season, a one-year crop
cycle, a single 2022 flood event); none has been validated against a second real
season, year, or disaster. These are real, validated, honestly-scoped research
results — two wired into a working demo, one intentionally held back after its own
integration surfaced why it isn't ready — not production-grade classifiers with a
service-level guarantee.

## Open items carried forward

- **Track D's live-vs-training generalization gap**: real and unresolved. The model
  needs a genuine non-disaster-monsoon negative class (e.g. Sentinel-1 from a
  Pakistani monsoon year with no declared calamity) before its live score is
  trustworthy enough to trigger on — not just a lower probability cutoff on the same
  confounded score.
- **Track D / insurance engine**: not extended into `exposure_risk.py`/
  `trigger_engine.py` — flagged as a proposal, not built, until the generalization
  gap above is addressed. Wiring a currently false-alarm-prone signal into real
  payout logic would be premature.
- **Fire classifier calibration**: `model_score` is validated as a real relative
  ranking at the 126-district-centroid sampling density Track G evaluated it at, not
  as a calibrated national base rate — a full-grid deployment (matching Track E's
  training resolution) would be needed before treating raw score values as
  meaningful probabilities.
- **Sugarcane share prediction**: real, negative R² at both point- and
  district-level; the crop's rarity and thin weak-label signal make it a genuinely
  harder case than wheat/cotton/rice with this approach — unresolved, not silently
  dropped from the reported average.
- **Single-window validation**: both trained models' real results come from one real
  time window each (Nov 2023 fire season; Nov 2022–Nov 2023 crop year). Neither
  claim has been checked against a second real year — the next honest validation
  step for either model, not assumed to generalize.
- **GB/AJK crop-mix coverage**: still genuinely unresolved. The hand-classified mask
  is the honest fallback, not a fix — real district-level ground truth for these 11
  districts doesn't exist anywhere this project has found.
