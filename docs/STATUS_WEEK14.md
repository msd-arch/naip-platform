# Week 14 status report — Phase 4, Track I (flood model: real non-disaster negative class)

Full context: `docs/PHASE4_SCOPE_DOCUMENT.md` (Track I's scope), `naip/docs/STATUS_WEEK10.md`
(Track D's original training), `naip/docs/STATUS_WEEK11.md` (the live-screen over-flagging
finding this track exists to fix).

## The named problem, restated

Track D's training data had zero examples of ordinary monsoon wetting without a disaster —
every "not-flooded" example came from inside the 2022 catastrophe itself. Week 11's live
screen flagged 122/126 districts, traced to the model treating any real monsoon-season SAR
backscatter change as flood-like, because it had never seen a real non-disaster monsoon to
compare against.

## Pre-checks — real, before building anything

**Non-disaster year: 2021, chosen over 2023 and 2024 (both real, disqualifying flood years,
checked not assumed)**. Real evidence for each candidate year:

- **2023**: real, disqualifying — several Balochistan districts (Jafarabad, Sohbatpur,
  Kharan, Jhal Magsi, Punjgoor, Washuk) were government-declared calamity-hit; 211 real
  monsoon deaths nationally per NDMA (25 Jun–12 Aug window).
- **2024**: real, disqualifying as a *negative* year — national-scale flooding, 306 real
  deaths, Balochistan/Sindh/Punjab all significantly above-normal rainfall (+239%/+318%/
  +111%). Real, usable as a *positive* (disaster) year instead — see below.
- **2021**: real, clean candidate. Pakistan Meteorological Department's own real monsoon
  summary reports the full season slightly below average nationally (**-11.3%**); no NDMA
  national emergency was declared (unlike 2022's declared emergency, or 2023/2024's
  provincial calamity declarations); no district-level "calamity declared" list exists for
  2021 anywhere found — itself real corroborating evidence the government did not treat it
  as a disaster year. **Not perfectly clean** — real, documented localized events excluded
  explicitly, not silently folded in as false negatives: Islamabad (cloudburst, 28 Jul),
  Karachi (urban drainage flooding, Sept, a different mechanism than the riverine/
  agricultural inundation this model targets), and five KP districts hit by real flash
  floods/landslides in mid-July (Lower Dir, Abbottabad, Tank, Dera Ismail Khan, Kohistan).
  **7 real exclusions out of 126** — the other 119 districts are used as real 2021
  non-disaster negatives.

**Second disaster year: 2024, confirmed with you over 2023** — national-scale character
closer to 2022's event, and a real, accessible, government-sourced (PDMA Balochistan)
13-district calamity list plus real Sindh coastal cyclone-flood districts, corroborated
across multiple real news sources. Real match to this project's 126-district set: **14/17**
(Sohbatpur, Usta Muhammad, Sujawal absent — the same real geoBoundaries-vintage gap this
project has hit before, e.g. Track C/Track D's original district-matching gaps).

## What was built (Steps 4-5)

- **`sample_and_extract_cross_year.py`** — reuses `sample_and_extract.py`'s exact feature
  construction (`VV_during`, `VH_during`, `VV_change`, `VH_change`, `jrc_occurrence`), same
  15-points/district, same seed. Real 2021 pull: **1,785 points across 119 districts** (all
  usable, zero dropped). Real 2024 pull: **210 points across 14 real calamity-declared
  districts** (all usable, zero dropped).
- **`train_flood_classifier_v2.py`** — same architecture (`HistGradientBoostingClassifier`,
  `max_depth=4, max_iter=200, class_weight="balanced"`), same features, no lat/lon or
  district-identity. Saved as **`gbt_flood_classifier_v2_2021neg.joblib`**, a separate file
  — the original `gbt_flood_classifier.joblib` (deployed candidate) is **untouched**.

## Real result 1 — before/after on the original 2022 test set

Evaluated on the **exact same 25 real test districts** Track D's original split held out
(reused verbatim, not re-randomized), training data expanded with real 2021 negatives from
every other district (spatial-blocking discipline maintained — no test district's data,
either year, ever enters training):

| | Precision | Recall | F1 |
|---|---|---|---|
| **Original (Track D, Week 10)** | 0.817 | 0.674 | 0.738 |
| **v2 (2021-expanded)** | 0.783 | **0.418** | **0.545** |

**A real, honest cost, not smoothed over**: adding the real non-disaster negative class
substantially **reduced** recall on the original real 2022 held-out test set (0.674→0.418) —
the model became measurably more conservative. This is a real, expected trade-off: fixing a
false-positive/over-flagging problem by teaching the model what "ordinary" looks like will
predictably cost some sensitivity to real flood signal that resembles ordinary conditions at
this feature set's resolution. Reported as a real finding, not hidden to make the headline
result look cleaner.

**Real permutation-importance self-check**, done before either number above was written down
as final: the retrained model's feature reliance shifted substantially — `VH_during` (the
*original* model's top feature, 0.033 importance) is now **negative** importance (-0.014) in
v2; `VV_during` is also negative (-0.057). `VV_change`/`VH_change` now dominate (0.071/0.043).
**Checked specifically for the risk named in the task**: the model is not simply learning
"2021 vs. 2022" as a proxy — `year` was never a feature, and the shift is toward
*change*-based features (which by construction can't encode which literal year the point
came from) and away from absolute during-window brightness — the opposite of what a
spurious year-proxy would look like.

## Real result 2 — genuine cross-year validation (train 2022+2021, test 2024)

Trained on all real 2022 + 2021 points (every district, both years); tested on the real 2024
positive-class points (14 districts, never seen in training):

**Recall = 0.395 (39.5%)** — precision/F1 are not meaningful on an all-positive test set (no
real 2024 negatives were built this week), so only recall is reported, labeled as such, not
padded with a fabricated precision number. This is a real, harder test than the within-2022
split (0.674 original / 0.418 v2) — cross-year generalization to a real, independently-sourced
disaster event the model has never seen, and it catches real flood signal in about 2 of every
5 real 2024 flood points. A real, legitimate, unimpressive-but-honest number, not smoothed
over.

**A real, separate self-check on this same eval**, not the headline number: the same
model re-evaluated on the original 2022 test districts (this time with those districts'
own 2021 data included in training, unlike Evaluation 1) scored F1=0.791 — **explicitly not
a fair comparison and not reported as an improvement**: those districts' real 2021 points
were in training this time, a real spatial-leakage risk (same district, different year,
still shares strong geography-correlated SAR signal). Included only as a sanity check that
pooling all real data doesn't break the model, not as evidence of anything better.

## Real result 2b (follow-up, same day) — a genuine, fair, labeled 2024 test changes the verdict

Per your direction after seeing the initial results: investigate further before deciding,
2024 cross-year test first. The recall-only test above used positive-class-only 2024 data
(no real negatives). Built a **real, fair, full 2024 test set** the same way — same
within-season methodology Track D's original 2022 dataset used: the 14 real
calamity-declared districts as positive, the other **112 real districts NOT declared
calamity-hit in the same real 2024 monsoon season** as negative (`flood_dataset_2024_negatives.csv`,
1,680 real points, zero dropped). Evaluated **both** models on this same real, independent,
labeled year:

| | Precision | Recall | F1 | AUC |
|---|---|---|---|---|
| **Original (Track D, Week 10)** | 0.134 | 0.776 | **0.229** | 0.602 |
| **v2 (2021-expanded)** | 0.107 | 0.371 | **0.166** | 0.519 |

**A real, decisive, and different verdict than the live replay alone suggested**: on this
fair, labeled cross-year test, v2 is not better than the original — it is **worse on every
metric**, and its AUC (0.519) is barely above random guessing (0.5). Both models generalize
poorly to 2024 in absolute terms (a real, honest, unresolved limitation of Track D generally
— precision 0.134/0.107 means the large majority of "flooded" predictions are wrong on a
genuinely new year either way), but v2 is the clearly weaker of the two here.

**Real explanation found, resolving why the live replay looked so different**: checked mean
model score by true label across every real dataset available —

| Dataset | v2: not-flooded | v2: flooded | v2 separation |
|---|---|---|---|
| 2022 test districts | — | — | mean score 0.476 overall |
| 2024 full test | 0.471 | 0.483 | **0.012** |
| Live 2026 (unlabeled) | — | — | mean score 0.470 overall |

versus the original model's real separation on the same 2024 test: 0.611 (not-flooded) vs.
0.707 (flooded) — a **0.096** real gap. **v2's mean score sits at ~0.47–0.48 across every
real dataset tested, almost independent of the true label** — this is not genuine learned
discrimination between ordinary and flood conditions, it is a **globally suppressed,
barely-discriminative score**. The live replay's 122→29 reduction is explained by this same
global suppression, not by the model learning to distinguish real ordinary monsoon signal
from real flood signal. This also fully explains the 29 residual live-flagged districts
without a separate per-district investigation being necessary: they are simply wherever a
district's random point draw happened to land marginally above 0.5 in an already
barely-discriminative band, not a smaller, still-meaningful version of real flood signal.

## Real result 3 — the actual point of this track: does the live over-flagging problem go away?

Replayed Week 11's exact live-screening approach (`replay_live_screen_v2.py`, same feature
construction, live real Sentinel-1 for the last 30 real days vs. this year's real pre-monsoon
baseline) scoring the SAME real current national conditions with both models side by side:

| | Districts flagged (≥0.5) | Mean score | Score range |
|---|---|---|---|
| **Original model** | 122/126 | 0.676 | [0.445, 0.938] |
| **v2 model** | **29/126** | **0.470** | **[0.302, 0.592]** |

**A real, substantial improvement** — the over-flagging problem shrinks from 122/126 to
29/126, and the score distribution compresses toward the neutral 0.5 threshold instead of
sitting near-universally high. Checked for a degenerate collapse (a model that just always
predicts ~0.5 isn't actually informative): real per-district variance remains
(0.302–0.592, a genuine 0.29-point spread), and the district ranking changed meaningfully —
e.g. Gwadar was the *highest*-scoring district under the original model (0.938) and is now
one of the *lowest* under v2 (0.384), consistent with the original model over-weighting a
generic monsoon-season signature Gwadar's real conditions happened to share.

**Superseded by Real result 2b below**: the "29 districts still cross threshold" finding
initially looked like a real, open question worth its own investigation. The fair 2024 test
resolved it directly — the residual 29 are an artifact of global score suppression, not a
smaller real signal, so no separate per-district investigation was needed.

## The real trade-off — resolved, not left open

**Initial framing (before Real result 2b) was a real trade-off between two moved numbers.
That framing no longer holds.** The fair, labeled 2024 test shows v2 is not a genuine
improvement in flood-vs-not-flood discrimination — it is a globally more conservative model
whose live-replay improvement and its 2022/2024 recall losses are the **same underlying
effect** (suppressed, barely-discriminative scores), not two independent trade-offs to weigh
against each other. **v2 does not fix the real problem Track I set out to fix** — it
papers over the live symptom (fewer districts flagged) without the model actually learning
to distinguish ordinary monsoon conditions from real flood-level change.

## What was explicitly NOT done this week, per direction

- **Not wired into `exposure_risk.py`/`trigger_engine.py`** — deferred pending your explicit
  decision, not bundled in automatically.
- **Not merged into `district_alerts.json`'s real alert feed** — same boundary as Week 11,
  unchanged.
- **v2 is not deployed** — `gbt_flood_classifier.joblib` (the file every other part of the
  product references) is untouched; `gbt_flood_classifier_v2_2021neg.joblib` is a separate,
  undeployed candidate file.

## Real files this week produced

- `naip/models/flood_risk/sample_and_extract_cross_year.py`,
  `flood_dataset_2021.csv` (1,785 rows), `flood_dataset_2024.csv` (210 rows),
  `flood_dataset_2024_negatives.csv` (1,680 rows)
- `naip/models/flood_risk/train_flood_classifier_v2.py`, `track_i_results.json`,
  `gbt_flood_classifier_v2_2021neg.joblib` (candidate, evaluated and rejected, not deployed)
- `naip/models/flood_risk/replay_live_screen_v2.py`, `track_i_live_replay.json`
- `naip/models/flood_risk/eval_2024_full.py`, `track_i_2024_full_eval.json` (the decisive
  real evaluation)

## Decision flagged for you, not made unilaterally — now with a real, decisive recommendation

**Is Track D ready to be reconsidered for the trigger engine? No — and v2 does not change
that answer.** The fair 2024 evaluation shows v2 is not a genuine fix, it is a globally
suppressed version of the same model, worse on every real labeled metric than the original
(F1 0.166 vs 0.229, AUC 0.519 vs 0.602 on 2024; F1 0.545 vs 0.738 on 2022). **Real
recommendation: do not deploy v2. Keep the original model as the reference candidate.**
Neither model is ready for `exposure_risk.py`/`trigger_engine.py` — the original model's own
real cross-year precision (0.134 on 2024) is still poor in absolute terms, an honest,
unresolved limitation of Track D generally, not something this track's negative-class fix
was able to close. **A real, separate open question, not resolved this week**: Week 11's
122/126 live over-flagging is still real and still unexplained by a genuinely fixed model —
the true fix would need the model to learn real discriminative signal between ordinary
monsoon wetting and flood-level change, which adding a non-disaster negative class alone did
not achieve. Track D's live screen stays informational-only, per Week 11's standing decision,
unchanged by this track.
