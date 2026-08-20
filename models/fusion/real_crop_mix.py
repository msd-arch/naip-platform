#!/usr/bin/env python3
"""
real_crop_mix.py -- Phase 2 Track C: thin accessor over
naip/data/crop_mix_ground_truth/real_crop_mix.json (built by
parse_mnfsr_crop_mix.py from the real Government of Pakistan MNFSR
district-wise crop area publication).

WHAT THIS ADDS: a real, per-district, per-crop proportional area share for
115/126 real districts (the other 11 are Gilgit-Baltistan's 10 districts +
Azad Kashmir, which the MNFSR report does not cover at all -- confirmed, not
assumed). This REPLACES the boolean plausibility GATE that
crop_plausibility.py (Week 4) provided with a real, sourced one wherever
real data exists, while keeping the exact same boolean contract
(`is_plausible`) that exposure_risk.py and trigger_engine.py already consume
-- no restructuring of the exposure_score formula itself this week (that's a
separate decision, deferred per direction, since trigger_engine.py already
ships and depends on the current formula shape).

TIER FIELD, propagated end to end (exposure_risk.py rows -> trigger_engine.py
audit records), per direction: a district running on real MNFSR data and a
district still running Week 4's hand-classified guess must never be
indistinguishable downstream.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json")

_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def crop_mix_tier(district_name):
    """'real_district_area' or 'hand_classified_mask'."""
    data = _load()
    rec = data.get(district_name)
    if rec is None:
        return "hand_classified_mask"
    return rec["tier"]


def crop_share(district_name, crop):
    """Real share_of_4crop_area for (district, crop), or None if unavailable
    (either the district has no real data, or this specific crop's source
    table failed cross-validation -- see crop_unreliable())."""
    data = _load()
    rec = data.get(district_name)
    if rec is None or rec["tier"] != "real_district_area":
        return None
    crop_rec = rec["crops"].get(crop)
    return crop_rec["share_of_4crop_area"] if crop_rec else None


def crop_unreliable(district_name, crop):
    """True if this (district, crop) cell's real source table existed but
    failed the parser's 5% cross-validation against its own printed total --
    i.e. genuinely unknown, NOT a confirmed real zero."""
    data = _load()
    rec = data.get(district_name)
    if rec is None or rec["tier"] != "real_district_area":
        return False
    unreliable = rec.get("crops_unreliable_source_data") or []
    return crop in unreliable


def is_plausible_real(district_name, crop):
    """True/False from real data, or None if real data can't answer this
    cell (district not covered, or this crop's table was rejected) -- callers
    should fall back to the hand-classified mask only on None, not on False
    (a real False -- crop genuinely not grown there -- must NOT be
    overridden by the coarser hand mask saying 'plausible')."""
    if crop_mix_tier(district_name) != "real_district_area":
        return None
    if crop_unreliable(district_name, crop):
        return None
    share = crop_share(district_name, crop)
    if share is None:
        return False  # real table covered this district but this crop had zero real area
    return share > 0
