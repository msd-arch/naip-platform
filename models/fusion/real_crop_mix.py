#!/usr/bin/env python3
"""
real_crop_mix.py -- Phase 2 Track C, extended Phase 4 (final item): thin
accessor over naip/data/crop_mix_ground_truth/real_crop_mix.json (built by
parse_mnfsr_crop_mix.py from the real Government of Pakistan MNFSR
district-wise crop area publication, season 2022-23 -- MNFSR's only real
report on disk) and, now, real_crop_mix_interim_estimates.json (built by
Track J's predict_interim_estimate.py: Track F's deployed crop-share model
applied to real Sentinel-2 features for season 2024-25).

THREE REAL TIERS, resolved in this order, PER (district, crop, DATE) --
date-awareness is new this week, see below:
  1. real_district_area  -- real MNFSR data, ONLY for the season it actually
     covers (2022-23). Always wins where it applies. Never overridden.
  2. model_estimated_interim -- Track F's trained model's real prediction,
     used ONLY to fill a real temporal gap: districts real MNFSR covers, for
     any growing season AFTER 2022-23 (MNFSR has no real report for those
     seasons at all). This is a trained model's ESTIMATE, not a government
     survey -- per Track J's own finding, unvalidatable until a future real
     MNFSR report arrives to check it against. It never competes with real
     MNFSR data for the season MNFSR actually covers.
  3. hand_classified_mask -- Week 4's coarse manual mask, for the 11 real
     districts neither real MNFSR nor Track F's model covers at all
     (Gilgit-Baltistan's 10 districts + Azad Kashmir, outside MNFSR's
     mandate -- Track G's real, deliberate rejection of extrapolating the
     model there stands unchanged, see STATUS_WEEK9.md), regardless of date.

WHY DATE MATTERS NOW: every function below previously ignored the alert
date entirely and applied real_district_area's single 2022-23 snapshot to
every row regardless of when the alert actually happened -- a real
simplification never explicitly flagged as such. NAIP's actual real hazard
archives (Week 1 onward) all postdate 2022-23 (they start mid-2026), so this
was silently applying a 2022-23-season crop-mix reading to alerts from a
completely different season the whole time. This week's change makes that
choice explicit and, wherever Track F's interim model has a real estimate,
better-grounded for the season the alert is actually in.

TIER FIELD, propagated end to end (exposure_risk.py rows -> trigger_engine.py
audit records): a district running on real MNFSR data, one running on Track
F's interim model estimate, and one still running Week 4's hand-classified
guess must never be indistinguishable downstream.
"""
import datetime as dt
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json")
_INTERIM_PATH = os.path.join(_HERE, "..", "..", "data", "crop_mix_ground_truth",
                              "real_crop_mix_interim_estimates.json")

# MNFSR's real, only report on disk covers exactly this one season.
MNFSR_LAST_REAL_SEASON = "2022-23"
MNFSR_LAST_REAL_SEASON_START_YEAR = 2022

# Threshold recalibration (real, tier-aware, crop-aware): per-crop confidence
# multiplier applied to model_estimated_interim rows only, derived directly
# from Track F's own validated cross-year R² (STATUS_WEEK17.md's real
# district-level cross-year table -- the fairer, harder-tested numbers, NOT
# the original within-year figures which never held out a genuinely
# different year). Each crop's value here is the mean of the two real
# cross-year directions (train2122->test2223, train2223->test2122) --
# neither direction is more "correct" than the other, both are real,
# equally-valid temporal holdouts, so the mean is the natural single-number
# summary rather than picking one arbitrarily.
#   wheat:     (0.475 + 0.470) / 2 = 0.4725
#   cotton:    (0.467 + 0.389) / 2 = 0.428
#   rice:      (0.289 + 0.239) / 2 = 0.264
#   sugarcane: (0.116 + 0.129) / 2 = 0.1225
# Mapping formula, confirmed with you before wiring into live trigger logic:
# multiplier = clamp(mean_r2, 0, 1) -- the direct R² value itself, no
# additional transform. R² already IS a real 0-1 "fraction of variance
# explained" quantity for a non-negative value, so this is the most literal,
# least-arbitrary use of the validated statistic (no free parameter to
# separately justify, unlike sqrt(R²) or a relative-to-best-crop rescaling,
# both considered and rejected -- see STATUS_WEEK21.md). Real, deliberate
# consequence: even wheat (the model's best-performing crop) still needs
# ~2.1x the raw exposure_score of a real-tier row to clear the same
# threshold, because R²=0.4725 means more than half the real variance is
# still unexplained -- a genuinely modest result, not near-ground-truth.
# Sugarcane (R²~0.12, barely above zero) needs ~8.2x -- discounted hard
# enough that it essentially cannot fire on a marginal score alone, exactly
# the real, intended effect.
INTERIM_CROP_R2_MEAN = {
    "wheat": 0.4725,
    "cotton": 0.428,
    "rice": 0.264,
    "sugarcane": 0.1225,
}


def interim_confidence_multiplier(crop):
    """Real per-crop confidence multiplier for model_estimated_interim rows
    -- 1.0 (no discount) for real_district_area and hand_classified_mask
    tiers, which are unaffected by this (see resolve_interim_confidence
    below, the actual per-row entry point). Clamped to [0, 1] as a safety
    bound even though every real value here already falls in that range."""
    r2 = INTERIM_CROP_R2_MEAN.get(crop)
    if r2 is None:
        return 1.0  # unknown crop -- no real R² to discount by, don't invent one
    return max(0.0, min(1.0, r2))


def resolve_interim_confidence(district, crop, date):
    """The real per-row entry point: returns 1.0 for real_district_area and
    hand_classified_mask tiers (current effective bar unchanged, per
    direction), the real per-crop multiplier only for model_estimated_interim
    rows."""
    if crop_mix_tier(district, date) == "model_estimated_interim":
        return interim_confidence_multiplier(crop)
    return 1.0


_cache = None
_interim_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def _load_interim():
    global _interim_cache
    if _interim_cache is None:
        with open(_INTERIM_PATH, encoding="utf-8") as f:
            _interim_cache = json.load(f)
    return _interim_cache


def season_of(date):
    """Real growing-season label for a calendar date, Nov-Oct convention --
    matches Track F's own season boundary (extract_phenology_features*.py:
    season 'YYYY-(YY+1)' runs Nov YYYY -- Oct (YYYY+1)). E.g. 2026-06-22 is
    in season '2025-26' (started Nov 2025); 2023-11-02 is in season
    '2023-24' (started Nov 2023), NOT '2022-23'."""
    start_year = date.year if date.month >= 11 else date.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def season_after_mnfsr(date):
    """True if `date`'s real growing season is chronologically after
    MNFSR's last real report (2022-23) -- the real temporal-gap condition
    model_estimated_interim exists to fill. False for 2022-23 itself or
    earlier (real MNFSR data, where it exists, always wins there)."""
    start_year = date.year if date.month >= 11 else date.year - 1
    return start_year > MNFSR_LAST_REAL_SEASON_START_YEAR


def _real_rec(district_name):
    data = _load()
    rec = data.get(district_name)
    return rec if rec and rec["tier"] == "real_district_area" else None


def _interim_rec(district_name):
    data = _load_interim()
    return data.get(district_name)


def crop_mix_tier(district_name, date):
    """'real_district_area', 'model_estimated_interim', or
    'hand_classified_mask' -- see module docstring for the real precedence
    rule. `date` is required: this is a real (district, DATE) question now,
    not just (district)."""
    if _real_rec(district_name) is not None and not season_after_mnfsr(date):
        return "real_district_area"
    if _interim_rec(district_name) is not None and season_after_mnfsr(date):
        return "model_estimated_interim"
    return "hand_classified_mask"


def crop_share(district_name, crop, date):
    """Real share_of_4crop_area for (district, crop, date), from whichever
    real tier applies -- UNCLIPPED (Track F's interim predictions can be
    slightly negative for near-zero crops, e.g. cotton -0.0035; clipping to
    [0,1] happens once, centrally, in exposure_risk.py's resolve_crop_weight,
    same as it already does for real_district_area). None if no real tier
    answers this cell (falls through to the hand-classified boolean gate)."""
    tier = crop_mix_tier(district_name, date)
    if tier == "real_district_area":
        rec = _real_rec(district_name)
        crop_rec = rec["crops"].get(crop)
        return crop_rec["share_of_4crop_area"] if crop_rec else None
    if tier == "model_estimated_interim":
        rec = _interim_rec(district_name)
        return rec["predicted_shares"].get(crop)
    return None


def crop_unreliable(district_name, crop):
    """True if this (district, crop) cell's real MNFSR source table existed
    but failed the parser's 5% cross-validation against its own printed
    total -- i.e. genuinely unknown, NOT a confirmed real zero. Applies only
    to the real_district_area tier itself (a structural issue in that one
    source table) -- Track F's interim model was trained on the same real
    labels but makes its own real prediction for every crop regardless, so
    this does NOT gate the interim tier."""
    rec = _real_rec(district_name)
    if rec is None:
        return False
    unreliable = rec.get("crops_unreliable_source_data") or []
    return crop in unreliable


def is_plausible_real(district_name, crop, date):
    """True/False from whichever real tier (real_district_area or
    model_estimated_interim) applies for (district, crop, date), or None if
    no real tier can answer this cell (district not covered by either, or --
    real_district_area only -- this crop's table was rejected). Callers
    should fall back to the hand-classified mask only on None, not on False
    (a real False -- crop genuinely not grown there -- must NOT be
    overridden by the coarser hand mask saying 'plausible')."""
    tier = crop_mix_tier(district_name, date)
    if tier == "real_district_area" and crop_unreliable(district_name, crop):
        return None
    if tier == "hand_classified_mask":
        return None
    share = crop_share(district_name, crop, date)
    if share is None:
        return False  # real/interim tier covered this district but this crop had zero real area
    return share > 0
