# Week 11 status report — Phase 3, Track D integration (live national flood screen)

Full context: `docs/PHASE3_MODEL_PLAN.md` (Track D integration section), `naip/docs/STATUS_WEEK10.md`
(Track D's original training result), `naip/docs/STATUS_WEEK9.md` (Track G, the integration
pattern this reuses).

## The one real architectural difference from Track E's integration, acted on

Track E's fire classifier is bound to a fixed historical MSG archive (Nov 2023) — it can only ever
replay that past event. Track D's real inputs (Sentinel-1 via GEE, JRC Global Surface Water) are
live and continuously updating, the same as the locust monitor's SMAP/NDVI inputs. This
integration therefore runs the trained classifier against **real current conditions**
(`predict_flood_risk_live.py`), not a replay — a genuine live national screen, checked honestly
rather than assumed to show either "no risk" or a curated positive finding.

## What was built

- **`naip/models/flood_risk/predict_flood_risk_live.py`** — real live national screen. Loads the
  persisted `gbt_flood_classifier.joblib` (confirmed it loads and predicts correctly before
  building anything around it), reuses `sample_and_extract.py`'s exact feature construction
  (VV_during, VH_during, VV_change, VH_change, jrc_occurrence; 15 real points/district, same
  random-point seed), samples 1,890 real live points across all 126 real districts. Real live
  during-window: last 30 days (2026-07-20..2026-08-19, real Sentinel-1 coverage confirmed at 403
  scenes before committing to it — no need to ask about a patchy-window fallback). Real pre-monsoon
  dry-season baseline: this year's Mar 1–Apr 15 (2026), same seasonal construction Track D used in
  2022. 1,878/1,890 real points usable (12 dropped for missing data), all 126 districts had at
  least one usable point — no coverage gaps.
- **Deliberately built as a standalone script, not a hook inside `hazards.py`'s per-15-min-frame
  loop**: Sentinel-1 revisit over Pakistan is on the order of days, not 15 minutes — querying GEE
  once per MSG frame would be architecturally wrong (thousands of redundant identical calls). This
  is the same real reason the locust-breeding-risk monitor (6.6) was never folded into `hazards.py`
  either.
- **`naip/models/flood_risk/merge_into_district_alerts.py`** — written and tested (reuses
  `district_alerts.json`'s exact existing row schema, so it would flow into the dashboard's
  existing aggregation with no bespoke format), but **deliberately not run this week** — see below.
- **`naip/models/flood_risk/build_dashboard_summary.py`** — turns the live screen into
  `track_d_dashboard_summary.json`, same pattern as Track G's `track_g_dashboard_summary.json`.
- **`naip_dashboard/app/models-in-production/page.tsx`** — new "Flood risk model: live national
  screen" section. Verified live: type-checked clean (`npx tsc --noEmit`), zero console errors,
  real data confirmed rendering.

## Real result — reported honestly, including why it isn't a flood alert

At the model's own 0.5 probability cutoff, the live screen flagged **122/126 districts**
(Gwadar 0.938, Ghanche 0.908, Shigar 0.871, Jhal Magsi 0.853, Nagar 0.851 highest; Malakand 0.445,
Bannu 0.454, Sargodha 0.478, Lodhran 0.487 the only four below threshold). The rule-based baseline
barely agrees (e.g. Ghanche: model 0.908, rule flags only 2/15 points) — the same kind of
rule/model divergence Track G found for the fire classifier, but far larger here.

**This was checked before being treated as a finding, per the same honesty discipline the locust
monitor's three prior "no risk flagged" results follow** — 122/126 is not reported as evidence of
real current national flooding. A real national-aggregate Sentinel-1/JRC check (single
`reduceRegion` over the national bbox, not per-point) found:

| | VV_during | VH_during | VV_change | VH_change | jrc_occurrence |
|---|---|---|---|---|---|
| 2022 training: **flooded** class centroid | -10.564 | -18.197 | -0.405 | -0.327 | 1.063 |
| 2022 training: **not-flooded** class centroid | -9.899 | -16.949 | -1.977 | -1.808 | 0.133 |
| **Live 2026 national mean** | -10.259 | -18.904 | -0.305 | -0.346 | 2.392 |

The live national average sits almost exactly on the *flooded* class centroid, not the
*not-flooded* one — the real reason this run over-flags. **The real structural explanation**:
Track D's non-flooded training examples were other real Pakistani districts during the SAME 2022
monsoon, never an ordinary non-disaster monsoon year. There is no example in training data of
"normal monsoon wetting, no disaster," so the model currently cannot tell that apart from
2022-flood-level change. This is a genuinely new limitation — **temporal generalization, not the
spatial centroid-sampling bias** Tracks A/E/G already found — and it was only visible by running
the model live; it does not show up in the frozen 2022 backtest.

**Per your explicit instruction, the real score distribution is reported, not just the binary flag
count** — there is a real gradient under the near-universal flag: min 0.445, p10 0.559, median
0.683, p90 0.816, max 0.938. That range is a real signal worth keeping for a future recalibration
pass, even though it is not clean enough to trigger on today.

## Decided with you after seeing this result

Presented with the raw result and its explanation, you chose: report only, do not merge into
`district_alerts.json`'s trigger feed, and make sure the score distribution — not just the 122/126
count — lands in the write-up. Implemented exactly that:

- `flood_risk` rows were **not** merged into `district_alerts.json`. Near-universal flags in the
  same schema as the other 11 real hazard detectors risked being read as a genuine national flood
  alert. `merge_into_district_alerts.py` exists, is tested, and remains available for a future week
  once the generalization gap above is addressed — it was not run this week.
- The dashboard section leads with a "not a flood alert" banner before any numbers, states the
  domain-shift finding plainly with the real comparison table, and shows the full score
  distribution alongside the raw flag count.

## Not done this week, stated plainly

- Not extended into the insurance/trigger engine (`exposure_risk.py`/`trigger_engine.py`) — flagged
  as a proposal, not built. Wiring a currently false-alarm-prone signal into real payout logic would
  be actively wrong; a future pass needs a genuine non-disaster-monsoon negative class first.
- The generalization gap itself is not fixed this week — reported, not resolved, same as Track
  D's original `jrc_occurrence` finding was reported and not resolved in Week 10.
- No recalibration of the 0.5 threshold was attempted to produce a cleaner-looking number — doing
  so on the same confounded score would not fix the underlying problem, only hide it.

## Real files this week produced

- `naip/models/flood_risk/predict_flood_risk_live.py`, `merge_into_district_alerts.py` (written,
  not run), `build_dashboard_summary.py`
- `naip/models/flood_risk/flood_risk_live_national.json` (1,878 real live points, 126 districts),
  `live_national_aggregate_stats.json`, `track_d_dashboard_summary.json`
- `naip_dashboard/app/models-in-production/page.tsx` — Track D section added
- `naip_dashboard/prepare_data.py` — `track_d_dashboard_summary.json` added to `SOURCES`
- `docs/PHASE3_MODEL_PLAN.md` — Track D integration section added
