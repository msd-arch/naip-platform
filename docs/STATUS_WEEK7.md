# Week 7 status report — Phase 3, Track E (MSG-native fire classifier)

Full context: `docs/PHASE3_MODEL_PLAN.md` (Track E section), `naip/docs/DEMO_TRACK_A.md`
(the real 83.3%/n=6 rule-based result this week builds on and, honestly, partly
revises).

## What was built

Reused, not re-pulled, per direction: the 45 real MSG3 scenes and their
`export_hazard_grids.py` output (`naip/data/msg_oct_nov_2023/`), and the real
national FIRMS pull for the same window (`firms_national_2023nov_*.csv`, 26,311 real
hotspots).

- **`naip/models/residue_burning/build_grid_dataset.py`** — a real pixel/grid-level
  dataset, not the 6-district-centroid sample Track A used. Candidate universe: every
  0.25° grid cell (9,801/timestep, national bbox) at every real daytime timestep
  (local_hour 6–19, same gate `det_residue_burning()` itself applies) where
  night_fog_diff and cloud_proxy data exist. Label: a real FIRMS hotspot within 50km
  and ±1 day — the same tolerance used throughout this project, kept for consistency
  rather than inventing a new one. Local-background box mean (±3°, same field/method
  `det_residue_burning()` uses) computed per cell via a real vectorised box filter.
  **Real result: 183,150 candidate rows, 22,090 positive (12.06%)** — a workable class
  balance, not thin enough to need the negative-sampling-ratio question you flagged;
  15 real distinct dates, well beyond "too small to train or evaluate meaningfully,"
  so the second question (extend beyond this window) also didn't need asking.
- **`naip/models/residue_burning/train_fire_classifier.py`** — real spatially/
  temporally-blocked split (whole real dates held out, not random cells): train =
  Nov 1–10 (10 dates, 122,100 rows), val = Nov 11–12 (2 dates, 24,420 rows), test =
  Nov 13–15 (3 dates, 36,630 rows) — a forward-in-time split, the most defensible
  simulation of real deployment for a single 15-day window. Trained logistic
  regression and `HistGradientBoostingClassifier` (sklearn; xgboost/lightgbm not
  installed, sklearn's own GBT implementation used instead, noted for reproducibility)
  on **two feature sets, both reported, not just the flattering one** (see below for
  why). Replayed `det_residue_burning()`'s exact real logic (`clear_sky = cloud_proxy
  < 0.3`, `anomaly = night_fog_diff - nfd_local_bg >= 10.0`) unchanged, on the
  identical real rows, for a genuine apples-to-apples comparison.

## The real result that needed a second look before reporting

The first real run included lat/lon as features (`with_geo`) and looked
outstanding: GBT test set — **P=0.603, R=0.919, F1=0.728, ROC-AUC=0.968**, dwarfing
the rule's real test-set score (P=0.200, R=0.002, F1=0.004). Before reporting that as
"the model beats the rule," real permutation feature importance (scored on the real
held-out test rows) was checked — standard due diligence for any model this strong on
a 15-day sample — and it showed **lat/lon at 0.566 and 0.610 importance, versus every
thermal feature at ≤0.006**. The model was overwhelmingly using *where* a cell was,
not *what its thermal signature looked like*, to predict the label. That's a real,
important finding: a with-geo model on this data is closer to memorizing "Punjab
burns in November, Balochistan mostly doesn't" than learning to read the MSG
IR3.9−IR10.8 signature — a materially weaker and different claim than "trained fire
detector," even though the metric alone looked like a clean win.

**So both feature sets are reported, not the stronger one alone**:

| | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| Rule-based (`det_residue_burning()`, unchanged), real test set | 0.200 | 0.002 | 0.004 | n/a |
| GBT, **thermal-only** features, real test set | **0.245** | **0.587** | **0.346** | **0.737** |
| GBT, thermal + lat/lon, real test set | 0.603 | 0.919 | 0.728 | 0.968 |
| Logistic regression, thermal-only, real test set | 0.095 | 0.210 | 0.131 | 0.554 |
| Logistic regression, thermal + lat/lon, real test set | 0.353 | 0.827 | 0.495 | 0.859 |

**The headline, defensible result: even the fair, thermal-only GBT clearly and
substantially beats the unchanged rule-based detector on the same real held-out
data** — F1 0.346 vs 0.004, recall 58.7% vs 0.2%, a real, large margin that isn't an
artifact of geographic memorization. The with-geo numbers are reported too, honestly
labeled as boosted by a geographic prior rather than sensor learning.

## A real correction to last week's headline number

Replaying the unchanged rule on the **full 183,150-row real grid** (not just the 6
district centroids Track A sampled) gives **precision 13.2%, recall 0.4%**
(TP=99, FP=653, FN=21,991) — far below the 83.3% precision `DEMO_TRACK_A.md` reported.
This is not a contradiction or an error in either result; it's what a fairer,
77×-larger real sample reveals: **district centroids are systematically located in
towns and administrative centers, which are disproportionately near real agricultural
land — not a representative sample of the full national grid**, which includes large
arid/mountain areas (Balochistan's interior, the north) where the rule's fixed 10.0K
threshold fires on bare-terrain solar heating rather than real fire. The 83.3%/n=6
number was real and correctly computed, but the sample it was computed on was
implicitly biased toward locations more likely to confirm. `DEMO_TRACK_A.md` has been
updated with this addendum rather than left to stand uncorrected.

## What this does and doesn't settle

A trained model, even restricted to real thermal features only, real full-grid data,
and a real held-out temporal split, clearly outperforms the existing rule-based
detector — this is the real result `PHASE3_MODEL_PLAN.md` asked Track E to produce,
and it held up under the honest feature-importance check rather than needing one.

**Decided (confirmed with you)**: thermal-only is Track E's closing headline and
deployed candidate — **F1=0.346 (P=0.245, R=0.587) vs. the unchanged rule's F1=0.004
on identical held-out real data.** The with-geo run is kept in this report as a
named ablation finding, explicitly not a candidate result: it demonstrates that
geography alone is a strong real prior, that the thermal signal alone is real but
harder, and that combining them carelessly lets a model coast on geography instead
of reading the sensor — a methodological finding worth presenting on its own terms,
not a stronger number to prefer. The reasoning: Track E exists to answer whether
NAIP's actual sensor (MSG thermal channels) carries real fire signal, not whether
Pakistani geography predicts where fires happen (it obviously does, and a model that
mostly learns that quietly reintroduces the same circularity problem Track E was
built to avoid — a memorized geographic prior standing in for genuinely reading the
instrument, the same underlying issue as re-deriving FIRMS's own algorithm, just via
a different mechanism). `train_fire_classifier.py` and `track_e_results.json` now
carry explicit `role` tags (`HEADLINE RESULT / deployed candidate` vs
`ABLATION FINDING ONLY`) so this distinction survives in the code, not just this
document.

## Real files this week produced

- `naip/models/residue_burning/build_grid_dataset.py`, `train_fire_classifier.py`
- `naip/data/msg_oct_nov_2023/grid_dataset.parquet` (183,150 real rows),
  `grid_dataset_sample.csv` (500-row preview), `track_e_results.json` (full real
  metrics, both feature sets, rule baseline on test set and full grid, GBT feature
  importances)
- `naip/docs/DEMO_TRACK_A.md` — addendum added correcting the 83.3% framing with the
  full-grid 13.2%/0.4% context
