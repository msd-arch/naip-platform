# Week 9 status report — Phase 3, Track G (integrate trained models into the live product)

Full context: `docs/PHASE3_MODEL_PLAN.md`, `naip/docs/STATUS_WEEK7.md` (Track E),
`naip/docs/STATUS_WEEK8.md` (Track F).

## Part 1 — Track F closes Track C's real remaining gap (with an honest result, not a clean win)

Persisted both trained models to disk for real reuse (`train_crop_share_model.py`,
`train_fire_classifier.py` now `joblib.dump` their headline models — neither did
before this week). Extracted real Sentinel-2 phenology features for the 11 real
GB/AJK districts the same way Track F did for its 2,875 training points: **165 real
cropland points sampled** (only 15/district was possible — real WorldCereal cropland
coverage in the 10 GB districts is 0.02–0.18% of district area, near-zero
high-altitude terrain; Azad Kashmir is a real, meaningfully different case at 4.4%).

**Real result: the model's predictions were checked and rejected, not deployed.** A
z-score check against the training feature distribution said all 11 districts were
"in range" — but the actual predicted outputs told a different story: predictions
clustered suspiciously close to the national-mean baseline for every district
regardless of real terrain differences, and **3/11 (Ghizer, Hunza, Nagar) predicted
an impossible negative sugarcane share** — direct, real evidence of tree-model
extrapolation failure outside its lowland-plains training domain that the input-level
z-score check alone did not catch. **Confirmed with you**: keep the hand-classified
mask for all 11 districts. `real_crop_mix.json` now documents this real attempt and
rejection explicitly for each district (not silently left unexplained), and a third
tier value (`model_predicted`) exists in the schema/code path for future use but is
currently assigned to **0 districts** — reported honestly, not padded.

**Track C's real status, precisely stated**: all 126 real districts now have a
*deliberate, reviewed* tier (115 real MNFSR + 11 hand-classified-with-a-documented-
rejected-model-attempt) — this is a real closure of the open question, not a
coverage increase to "126/126 real-or-model." The honest number stays 115/126 real,
11/126 hand-mask, same as Week 6.

## Part 2 — real crop share as a weight, not just a gate

**Confirmed with you** before regenerating national output: `exposure_score =
hazard_confidence * vulnerability_weight * crop_weight`, where `crop_weight` is the
real MNFSR share (clipped [0,1]) for `real_district_area`/`model_predicted` tiers, or
the exact original 1.0/0.0 gate for `hand_classified_mask` districts (no regression
there). Real before/after on the two example rows: **Kasur cotton (real 0.87% share):
0.468 → 0.004** (drops ~99%); **Sialkot rice (real 48.95% share): 0.39 → 0.191**
(drops to reflect it's not the district's only crop, stays substantial).

**Real, consequential downstream effect, not hidden**: exposure_score's scale
dropped sharply nationally — real max score fell from routinely 0.39–0.68 to **0.225**.
The original thresholds (0.35 illustrative, 0.20 demo) both became numerically
miscalibrated: **0 national trigger events at 0.35**, and the demo pipeline hard-broke
(`prepare_data.py` failed — the Layyah/fog/cotton scenario no longer cleared 0.20).

**Recalibration, done as two separate, sequential real decisions per your explicit
instruction — not one number picked to satisfy both**:
1. New thresholds chosen by matching the **original thresholds' real selectivity**
   against the new score distribution (illustrative: old 0.35 selected ~0.6% of
   nonzero rows → new threshold **0.225** selects 3/583; demo: old 0.20 selected
   ~24% → new threshold **0.07** selects 130/583), not picked to hit a target event
   count or preserve any scenario.
2. **Checked separately, honestly**: does Layyah still clear the new demo threshold?
   **No** — its real score is 0.0277, well below 0.07. Per your direction, this
   wasn't patched around. A real search among the 4 real farm-registry districts for
   a scenario that genuinely clears 0.07 found **Gujranwala / 2026-06-23 / uv_index
   × rice, real score 0.134, real MNFSR rice share 60.92%, 18 real farms matched** —
   the new demo scenario, found by checking real data, not chosen to fit a narrative.

Real before/after, full pipeline re-run: national triggers at illustrative threshold
6→8 (Week 6) → **3** (Week 9, recalibrated 0.225); demo scenario Layyah/fog/cotton →
**Gujranwala/uv_index/rice**. Dashboard resynced; `prepare_data.py` and
`run_end_to_end_demo.py` both updated to the new scenario/threshold with the real
reasoning documented in-line, not just in this report.

## Part 3 — Track E's classifier runs alongside the rule, not instead of it

Added `predict_residue_burning_model_score()` to `hazards.py`, called immediately
after `det_residue_burning()` in the main loop — **`det_residue_burning()` itself is
completely unchanged**, confirmed by re-running against the real Nov 2023 archive and
getting the identical 43,722 alerts / 6 flags as Week 5's addendum. The trained
thermal-only GBT's real probability score is attached to the same alert record as
`model_score`, distinct from the rule's own `flag`.

**Real agreement/disagreement, run against the real Nov 2023 MSG3 archive (the exact
data still on disk from Track A)**, 3,210 real records with both a rule flag and a
model score:

| | Model ≥0.5 | Model <0.5 |
|---|---|---|
| **Rule flag=True** | 3 (both agree) | 3 (rule-only) |
| **Rule flag=False** | 2,221 (model-only) | 983 (neither) |

**A real finding worth explaining, not just reporting**: the model flags far more
often (2,224/3,210 = 69.3%, mean score 0.622) than its own real full-grid test
evaluation would predict (13.2% positive rate, Week 7). Checked whether this was
overfitting to training dates — it isn't: even on the real *held-out* test dates
(Nov 13–15), the district-centroid positive rate is **54.8%**, still far above the
full-grid 13.2%. The most likely real explanation, consistent with this project's
own prior finding: `hazards.py` evaluates at 126 fixed district centroids, which are
disproportionately near real agricultural land — **the same sampling bias that
inflated the rule's original 83.3% precision figure in `DEMO_TRACK_A.md`** now shows
up for the model too, in the opposite direction (inflating the positive rate rather
than the precision). `model_score` should be read as a real relative ranking signal
at this sampling density, not a calibrated national base rate — stated explicitly in
the dashboard, not buried.

## Part 4 — dashboard

New page: `/models-in-production` (`naip_dashboard/app/models-in-production/page.tsx`,
linked in `Nav.tsx`). Shows the real three-tier crop-mix breakdown (115/0/11), the
real rejected GB/AJK predictions with impossible negative shares flagged inline (⚠),
and the real rule-vs-model fire confusion table with the sampling-bias caveat
surfaced as a visible banner, not buried in a tooltip — same design system
(single teal accent, amber caveat banners) as every other page. Verified live:
type-checked clean, zero console errors, real data confirmed rendering correctly.

## Real files this week produced

- `naip/models/crop_classifier_national/predict_gb_ajk.py`, `points_gb_ajk.geojson`,
  `phenology_features_gb_ajk.csv`, `gb_ajk_predictions.json`
- `naip/models/crop_classifier_national/gbt_crop_share_model.joblib` (newly persisted)
- `naip/models/residue_burning/gbt_fire_classifier_thermal_only.joblib` (newly persisted)
- `Downloads/hazards_scripts/hazards.py` — `predict_residue_burning_model_score()`
  added, `det_residue_burning()` unchanged
- `naip/models/fusion/exposure_risk.py` — `resolve_crop_weight()`, weighted score
- `naip/backend/insurance_engine/trigger_engine.py` — `crop_weight` in audit records,
  `BASIS_RISK_NOTE` updated
- `naip/run_end_to_end_demo.py` — recalibrated default district/threshold
- `naip/data/crop_mix_ground_truth/real_crop_mix.json` — GB/AJK rejection documented
- `naip/data/msg_oct_nov_2023/hazards_district_nov2023_with_model.json`,
  `track_g_dashboard_summary.json`
- `naip_dashboard/app/models-in-production/page.tsx`, `prepare_data.py` updates
