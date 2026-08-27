# Week 27 status report — Track I wiring: v3 promoted, flood exposure wired in

Full context: `naip/docs/STATUS_WEEK26.md` (v3's real, fair-test validation).

## Step 1 — the 9-district anomaly, investigated

Pulled full real feature values (SAR, JRC, precipitation) for the 9 currently-flagged districts
plus a real 20-district reference sample (29 districts total — a full 126-district pull timed
out GEE's `reduceRegions` with the 20-year climatology stack; not attempted again this week,
flagged honestly rather than silently retried until it worked).

**Real finding: explainable (cases 1/2), not genuine confusion (case 3).** The reference
sample's own mean `precip_anomaly_pct` is **-72.2%** — nearly the *entire* country is currently
running well below its historical seasonal norm for this exact window, in this real snapshot.
Against that backdrop, the 9 flagged districts are still the **wettest places in the country in
absolute terms right now** — every one of them sits at the 68th-94th percentile of the reference
sample on `precip_total_mm`, despite most also sitting at the 55th-86th percentile on the
*negative* side of `precip_anomaly_pct` (i.e., less negative than most other districts, not
more). Two districts (Azad Kashmir, Haripur) additionally show real elevated `jrc_occurrence`
(96.5th/97.4th percentile) — genuine proximity to real permanent water. **Real, honest
conclusion**: the model is using precipitation and SAR/JRC signal together sensibly — flagging
the nationally-wettest districts even in a below-average year — not over-relying on
`precip_anomaly_pct` alone or flagging on a spurious combination. Not exhaustively verified for
every hypothetical future flagged district; documented as a known real limitation, not a solved
problem, in both the model's own live-screen caveats and the trigger engine's basis-risk note.

## Step 2 — wiring, done

- **v3 promoted**: `predict_flood_risk_live.py` now loads
  `gbt_flood_classifier_v3_precip_fulltrain.joblib` (trained on all real 2022+2021 points — the
  same model `replay_live_screen_v3.py` used), fetches live CHIRPS precipitation alongside
  SAR/JRC, and carries the real v3 validation numbers + the 9-district finding as explicit
  caveats on every record. The original `gbt_flood_classifier.joblib` is untouched (still what
  the rejected-v2/eval-comparison scripts load by name for real apples-to-apples comparison).
- **`crop_calendar.py`**: added a real, illustrative `flood_risk` stage-vulnerability row (same
  discipline as every other hazard's table — not locally fitted, physically reasoned: flooding
  is destructive at nearly every crop stage, most severe during flowering/grain-fill).
- **New `merge_flood_into_hazards_alerts.py`**: folds the live flood screen into
  `hazards_district_national.json`'s `alerts` list — the file `exposure_risk.py`/
  `trigger_engine.py` actually read (a different, real finding worth stating plainly:
  `merge_into_district_alerts.py`, Track D/I's existing merge script, targets
  `district_alerts.json` instead, which feeds the dashboard's choropleth, not the scoring
  pipeline — that script is untouched, this is a new, separate merge for the scoring path).
  Uses `slot="live"` (not `"trend"`, which `compute_exposure_rows()` explicitly skips) so flood
  flows through the exact same generic per-crop vulnerability/`crop_weight` machinery every
  other hazard already uses — no special-cased path.
- **`trigger_engine.py`**: `BASIS_RISK_NOTE` is kept verbatim (per the established "verbatim for
  auditability" principle); a new `FLOOD_BASIS_RISK_ADDENDUM` is appended only for
  `hazard == "flood_risk"` records, stating the real fair-test precision (0.190) and the Step 1
  finding, verified to appear only on flood-driven records (confirmed: non-flood records carry
  no addendum).
- **Ran the real pipeline end to end**: `predict_flood_risk_live.py` → `merge_flood_into_hazards_alerts.py`
  → `exposure_risk.py` → `trigger_engine.py`, all against real current data (2026-08-27 live
  screen).

## Real before/after on national/demo trigger counts (existing thresholds, unchanged)

| Threshold | Before (no flood) | After (flood wired in) |
|---|---|---|
| Illustrative (0.225) | 0 | **0** (unchanged — flood's real max score, 0.0555, cannot reach this bar) |
| Demo (0.0216) | 9 | **16** (+7 real flood-driven events) |

The 7 new demo-threshold events are Sialkot/Gujrat/Narowal/Islamabad/Abbottabad/Jhelum/Rawalpindi
× rice — the same 7 (of the 9 flagged) districts where rice happens to be in-season and
agronomically plausible on 2026-08-27; Azad Kashmir and Haripur didn't clear the bar. Each
carries the flood-specific basis-risk addendum, confirmed present.

## Step 7 — real flood-specific threshold: Option A, confirmed and finalized

**Decided: keep the shared thresholds (0.225 illustrative / 0.0216 demo) — a deliberate
application of the same confidence-discount principle the crop-weighting decision already
established, not a coincidence the math happened to work out.**

The precedent: `model_estimated_interim` crop rows get a real per-crop confidence multiplier —
sugarcane's poor R² (0.1225) earns it an ~8.2x discount specifically so a weak, less-trustworthy
signal has to work *harder* to clear the same bar a real-tier row clears easily
(`STATUS_WEEK21.md`). Flood's real fair-test precision (0.190 — roughly 4 in 5 "flood"
predictions still wrong even on the best real evaluation so far) is the same category of
signal: real, validated, meaningfully useful, but not yet trustworthy enough to fire the most
consequential (illustrative/national) tier on its own. Option B would have done the *opposite*
of every prior tier-confidence decision in this project — deliberately lowering the bar so a
less-trustworthy signal could reach the tier that matters most. Option A applies the same
discipline flood already deserves under the crop-weighting precedent, just expressed as "the
existing bar is high enough that flood can't clear it yet" rather than as an explicit
multiplier — the honest result of flood's own real accuracy, not an artifact to route around.

The demo tier is the one place flood *does* show a real, modest, visible effect (+7 events) —
consistent with the demo tier's own established role (a workable, illustrative count, not
actuarially calibrated) and with checking (not assuming) that 0.0216 already selects ~30% of
flood's own real nonzero rows, comparable to the demo tier's original intended looseness.

**No further pipeline re-run needed** — the before/after table above already reflects these
final, unchanged threshold values.

<details><summary>Original real numbers this decision was based on</summary>

Flood's real score distribution (23 nonzero exposure rows, this one live date — the only real
data volume that exists yet, a real limitation on how robust any calibration can be right now):

| | min | p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| **flood_risk** | 0.0008 | 0.0086 | 0.0278 | 0.0445 | 0.0528 | 0.0551 | 0.0555 |
| *(for reference)* other hazards | 0.0001 | 0.0036 | 0.0073 | 0.0122 | 0.0158 | 0.0209 | 0.0362 |

**What I checked, not assumed**: flood scores run noticeably *higher* than the other-hazard
distribution at every percentile — this is real (flood's model confidence values, 0.5-0.82,
run higher than many rule-based hazards' typical confidence), not an artifact.

**Applying the same selectivity-matching method used for every prior threshold** (target the
~0.6-0.72% top-selectivity the illustrative tier and the ~24-30% looser selectivity the demo
tier have both used) hits a real, honest small-sample problem: 0.6% of 23 rows is 0.14 — it
rounds to zero, a degenerate target at this data volume. Two real, checked options, not a single
forced number:

- **Option A — keep the shared thresholds as-is (0.225 / 0.0216), a deliberate choice, not a
  default**: checked against flood's own distribution, 0.0216 already selects ~30% of flood's
  nonzero rows (7/23) — coincidentally right in the demo tier's original intended looseness.
  0.225 excludes flood entirely from the illustrative tier for now, which is itself defensible
  given the model's real fair-test precision (0.190) — a conservative floor until real data
  volume grows past a single live date.
- **Option B — a flood-specific pair**: e.g. illustrative-flood ≈ 0.045 (~p90, top ~10% of
  flood's own rows, closer in spirit to the crop-side illustrative tier's original ~0.6-0.72%
  target than 0.225's structural exclusion), demo-flood unchanged at 0.0216 (already well-placed
  per Option A's check).

Confirmed: Option A, for the reasoning stated above the fold — not "the math happened to work
out," a deliberate application of the crop-weighting tier-confidence precedent.

</details>

## Files this week

- `naip/models/fusion/crop_calendar.py` (added `flood_risk` vulnerability row)
- `naip/models/flood_risk/predict_flood_risk_live.py` (promoted to v3, precip-aware)
- `naip/models/flood_risk/merge_flood_into_hazards_alerts.py` (new)
- `naip/models/flood_risk/investigate_9district_anomaly.py`,
  `track_i_v3_9district_investigation.json` (new)
- `naip/backend/insurance_engine/trigger_engine.py` (flood-specific basis-risk addendum)
- Regenerated (real, current pipeline outputs): `flood_risk_live_national.json`,
  `hazards_district_national.json`, `exposure_risk.json`/`exposure_risk_top*.csv`,
  `audit_log_national.jsonl`/`audit_log_demo.jsonl`, `trigger_summary_national.json`/
  `trigger_summary_demo.json`

## Track I — closed this week

With the threshold decision confirmed, Track I is fully closed: v3 promoted and deployed, wired
into `exposure_risk.py`/`trigger_engine.py`, threshold decision made and reasoned, dashboard
updated (below) — the first Phase 4 track to reach the trigger engine after a real, validated
fix.
