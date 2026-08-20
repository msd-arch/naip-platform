#!/usr/bin/env python3
"""
crop_calendar.py -- regional (province-average, NOT per-farm) Punjab crop
calendar for wheat, cotton, rice, and sugarcane, used to approximate
"crop-stage" for the 6.5 exposure-risk fusion model.

WHY THIS EXISTS (read before trusting a stage label): Week 2 confirmed there
is no real wheat/cotton/rice/sugarcane classification and no populated
per-farm crop_calendar data anywhere in NAIP. The architecture doc's literal
"crop-stage-specific exposure risk" framing is unbuildable with real
per-farm data this week. Per direction: this uses a REGIONAL AVERAGE
calendar instead -- every date this module assigns a "stage" to is telling
you what stage the average Punjab field of that crop is probably in, not
what any specific farm's field is in. Never presented as farm-specific.

SOURCE, two levels of confidence -- read the split, it matters:
  1. SOWING/HARVEST WINDOWS -- real, cited, not invented:
     AIS Pakistan (joint FAO/USDA/Punjab & Sindh Agriculture Depts/SUPARCO
     project), http://dwms.fao.org/~test/dat_crops_en.asp (provided directly,
     could not independently re-fetch this session -- see Week 3 status
     report for the access attempts that failed). Rabi: sown Oct-Dec,
     harvested Mar-Apr (wheat). Kharif: officially Apr16-Oct15; sowing
     staggered by crop (sugarcane from Feb, cotton Mar-May, rice Jun-Jul,
     maize Jul-Aug); harvest starts Sep, continues through Dec (sugarcane
     the exception, can run to Mar+).
  2. SUB-STAGE SPLITS (establishment / vegetative / flowering / maturation)
     WITHIN each sowing-harvest window -- NOT separately sourced. This is a
     proportional interpolation using standard, generic crop-growth-stage
     agronomy (roughly: ~35-40% establishment/vegetative, ~20-25%
     flowering/reproductive -- the most hazard-vulnerable stage, ~20-25%
     grain-fill/maturation, remainder harvest). Flagged explicitly wherever
     a stage label is used -- this is the least-certain part of this module.

VULNERABILITY WEIGHTS below (which hazard matters most at which stage) are
similarly illustrative agronomic knowledge (frost/heat during flowering or
grain-fill is the classically damaging combination; the same hazard during
establishment is far less costly), NOT locally fitted or validated against
any real yield-loss data this week -- same "illustrative thresholds, tune
against real climatology before treating as operational" caveat hazards.py
already uses for det_hail.
"""
import datetime as dt


# (month_start, month_end) inclusive, 1-12, plus an EXPLICIT wraps_year flag
# (whether harvest_end's month falls in the calendar year AFTER sow_start's
# month -- can't be inferred from "end < start" alone, e.g. sugarcane's
# sow=Feb(2)/harvest_end=Mar(3) still wraps into the next year because it's
# a ~13-month crop, even though 3 > 2 numerically). Sourced (see docstring
# point 1); sugarcane's real harvest start is Sep per the same source
# ("harvesting starts September... sugarcane is the exception, can continue
# to March or beyond") -- stored here as the harvest END month since that's
# what defines the season boundary this module needs; the Sep-onward start
# of sugarcane harvest overlaps its own grain_fill_maturation/harvest stage
# split below rather than being tracked as a separate date.
SOWING_HARVEST = {
    "wheat":     {"sow": (10, 12), "harvest": (3, 4), "wraps_year": True},
    "cotton":    {"sow": (3, 5), "harvest": (9, 12), "wraps_year": False},
    "rice":      {"sow": (6, 7), "harvest": (9, 12), "wraps_year": False},
    "sugarcane": {"sow": (2, 2), "harvest": (9, 3), "wraps_year": True},
}

# Proportional stage split within [sow_start .. harvest_end] (NOT sourced,
# see docstring point 2). Fractions of the full sow->harvest span.
STAGE_FRACTIONS = [
    ("establishment", 0.20),
    ("vegetative", 0.20),
    ("flowering", 0.25),
    ("grain_fill_maturation", 0.20),
    ("harvest", 0.15),
]

# Illustrative stage-vulnerability weight (0-1) per hazard, keyed to the
# generic stage names above -- applies to every crop the same way (a real
# per-crop table would differ; scoped down to one shared table this week,
# flagged as a simplification).
HAZARD_STAGE_VULNERABILITY = {
    "frost":        {"establishment": 0.3, "vegetative": 0.4, "flowering": 0.9,
                      "grain_fill_maturation": 0.7, "harvest": 0.3},
    "cold_wave":    {"establishment": 0.3, "vegetative": 0.4, "flowering": 0.85,
                      "grain_fill_maturation": 0.7, "harvest": 0.3},
    "heat_wave":    {"establishment": 0.2, "vegetative": 0.4, "flowering": 0.85,
                      "grain_fill_maturation": 0.9, "harvest": 0.4},
    "hail":         {"establishment": 0.4, "vegetative": 0.6, "flowering": 0.9,
                      "grain_fill_maturation": 0.8, "harvest": 0.6},
    "thunderstorm": {"establishment": 0.3, "vegetative": 0.4, "flowering": 0.6,
                      "grain_fill_maturation": 0.6, "harvest": 0.7},
    "dust_storm":   {"establishment": 0.3, "vegetative": 0.4, "flowering": 0.8,
                      "grain_fill_maturation": 0.5, "harvest": 0.4},
    "heavy_rain":   {"establishment": 0.5, "vegetative": 0.4, "flowering": 0.6,
                      "grain_fill_maturation": 0.7, "harvest": 0.9},
    "fog":          {"establishment": 0.2, "vegetative": 0.2, "flowering": 0.3,
                      "grain_fill_maturation": 0.3, "harvest": 0.5},
    "drought":      {"establishment": 0.6, "vegetative": 0.6, "flowering": 0.9,
                      "grain_fill_maturation": 0.8, "harvest": 0.3},
}
DEFAULT_VULNERABILITY = 0.4  # hazard/stage combos not in the table above (uv_index, cloud_burst, etc.)


def _month_span_days(start_month, end_month, year, wraps_year):
    """Days from the 1st of start_month to the last day of end_month.
    wraps_year is explicit (see SOWING_HARVEST comment) rather than inferred
    from month numbers, since a same-numeric-order span can still be a
    multi-year crop (sugarcane: Feb -> Mar is 13 months, not 1)."""
    start = dt.date(year, start_month, 1)
    end_year = year + 1 if wraps_year else year
    if end_month == 12:
        end = dt.date(end_year, 12, 31)
    else:
        end = dt.date(end_year, end_month + 1, 1) - dt.timedelta(days=1)
    return start, end


def crop_stage_on(crop, date):
    """Return (stage_name, days_into_season, season_length_days) for `crop`
    on `date`, or None if the date falls outside that crop's real sow->
    harvest window for the season containing it."""
    if crop not in SOWING_HARVEST:
        raise ValueError(f"unknown crop {crop!r}, expected one of {list(SOWING_HARVEST)}")
    sow_m = SOWING_HARVEST[crop]["sow"][0]
    harvest_m = SOWING_HARVEST[crop]["harvest"][1]
    wraps = SOWING_HARVEST[crop]["wraps_year"]

    # try the season anchored at date.year and at date.year-1 (a date early
    # in the calendar year may belong to a season that started the prior year)
    for anchor_year in (date.year, date.year - 1):
        start, end = _month_span_days(sow_m, harvest_m, anchor_year, wraps)
        if start <= date <= end:
            total_days = (end - start).days + 1
            days_in = (date - start).days
            frac = days_in / total_days
            cum = 0.0
            for stage, f in STAGE_FRACTIONS:
                cum += f
                if frac <= cum:
                    return stage, days_in, total_days
            return STAGE_FRACTIONS[-1][0], days_in, total_days
    return None


def vulnerability(hazard, crop, date):
    """Illustrative 0-1 vulnerability weight for `hazard` hitting `crop` on
    `date`, using the regional-average calendar above. Returns
    (weight, stage_or_None, note)."""
    result = crop_stage_on(crop, date)
    if result is None:
        return 0.0, None, f"{date} is outside {crop}'s regional Kharif/Rabi sow-harvest window -- not in season"
    stage, days_in, total_days = result
    weight = HAZARD_STAGE_VULNERABILITY.get(hazard, {}).get(stage, DEFAULT_VULNERABILITY)
    note = (f"{crop} regional-average stage '{stage}' ({days_in}/{total_days} days into season) -- "
            f"illustrative vulnerability weight, not locally validated")
    return weight, stage, note


if __name__ == "__main__":
    # smoke test / demonstration
    import datetime as _dt
    test_dates = [_dt.date(2026, 2, 15), _dt.date(2026, 6, 22), _dt.date(2026, 9, 1)]
    for crop in SOWING_HARVEST:
        for d in test_dates:
            r = crop_stage_on(crop, d)
            print(f"{crop:10s} {d}  ->  {r}")
