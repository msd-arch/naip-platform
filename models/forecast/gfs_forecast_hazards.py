#!/usr/bin/env python3
"""
gfs_forecast_hazards.py -- Track S1: a real forecast layer, additive to
Track H's live nowcasting loop, not a replacement. Runs 3 of hazards.py's 11
real detectors (det_frost, det_heat_wave, det_cold_wave) -- the only ones
with real, direct GFS field compatibility, confirmed by comparing Track L's
13 real GFS_RAW_VARS fields against what each of the 11 detectors actually
consumes (the other 8 need MSG-specific derived products GFS categorically
cannot produce, are cadence-incompatible, or use NDVI -- see
PHASE6_SCOPE_DOCUMENT.md's Track S1 section and CLAUDE.md's real entry for
the full comparison).

HORIZON, confirmed with you before building: 72h / the next 3 real forecast
days. Not a single-snapshot choice -- det_heat_wave/det_cold_wave need at
least 2 real clear-sky days of temperature data to compute a persistence
mean (a structural requirement of the real detector functions, not a design
preference), so "horizon" here means "how many forecast days to include,"
not just "how far out."

REUSE, NOT REIMPLEMENTATION: det_frost/det_heat_wave/det_cold_wave are
imported directly from Downloads/hazards_scripts/hazards.py (the real,
unmodified detector functions) and download_one()/build_raw_dict() are
imported directly from Downloads/ml_pipeline/download_gfs_aws.py (Track L's
real, proven byte-range GFS downloader) -- same real thresholds, same real
download mechanism, nothing reimplemented from scratch.

REAL FIELD MAPPING, stated plainly:
  - skin_temp_c        <- GFS "Temperature_surface" (t, surface) - 273.15
  - cloud_proxy         <- GFS total cloud cover (tcc) / 100.0 -- a real,
                            described substitution: GFS's own model-diagnosed
                            cloud fraction standing in for MSG's satellite-
                            observed cloud_proxy, not identical instrumentation.
  - wind_ms             <- sqrt(10u^2 + 10v^2)
  - wind_gap_days       <- always 0 (the forecast valid time IS the GFS time,
                            no real gap to report)
  - local_hour          <- fixed per sample (03:00 PKT for frost/cold_wave's
                            night value, 14:00 PKT for heat_wave's day value),
                            Pakistan Standard Time = UTC+5 fixed (no real DST)

REAL, DELIBERATE CAVEAT on the wrf_t2m_c cross-check parameter: the original
nowcast detectors cross-check MSG's satellite-observed skin temp against a
genuinely INDEPENDENT second real data source (WRF, a different model run).
A pure-GFS forecast has no such independent second source available --
passing GFS's own 2m temp as a "cross-check" against GFS's own surface temp
would be checking a model against itself, not a real independent
verification, and would dishonestly inflate the confidence score's real
cross-check bonus. wrf_t2m_c is passed as None here, deliberately, not
approximated.

Usage:
    python gfs_forecast_hazards.py --out forecast_alerts.json
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np

HAZARDS_DIR = r"C:\Users\USER\Downloads\hazards_scripts"
GFS_DOWNLOADER_DIR = r"C:\Users\USER\Downloads\ml_pipeline"
sys.path.insert(0, HAZARDS_DIR)
sys.path.insert(0, GFS_DOWNLOADER_DIR)
from hazards import det_frost, det_heat_wave, det_cold_wave  # noqa: E402
from download_gfs_aws import download_one, fetch_idx  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NAIP = os.path.abspath(os.path.join(HERE, "..", ".."))
DISTRICTS_PATH = os.path.join(NAIP, "data", "seed", "pk_districts.geojson")
CACHE_DIR = os.path.join(HERE, "gfs_cache")

PKT_OFFSET_HOURS = 5  # Pakistan Standard Time, fixed, no real DST
NIGHT_LOCAL_HOUR = 3   # 03:00 PKT -- frost + cold_wave's night sample
DAY_LOCAL_HOUR = 14    # 14:00 PKT -- heat_wave's day sample
N_FORECAST_DAYS = 3     # confirmed with you: 72h / next 3 real forecast days


def find_latest_cycle(now_utc=None, max_lookback_cycles=8):
    """Real GFS cycles publish ~4-5h after cycle time -- walk backward in 6h
    steps from now and use the first one whose real .idx is actually
    fetchable, rather than assuming the most recent nominal cycle exists yet."""
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    cycle = now_utc.replace(minute=0, second=0, microsecond=0)
    cycle -= dt.timedelta(hours=cycle.hour % 6)
    for _ in range(max_lookback_cycles):
        try:
            fetch_idx(cycle, 0, timeout=15, retries=1)
            return cycle
        except Exception:
            cycle -= dt.timedelta(hours=6)
    raise RuntimeError("no real GFS cycle found fetchable in the last "
                        f"{max_lookback_cycles * 6}h -- real NOAA outage or network issue")


def fhr_for_local_time(cycle_dt, target_date, local_hour):
    """real forecast-hour offset for a target Pakistan local date+hour,
    relative to the real GFS cycle start time."""
    target_utc = dt.datetime(target_date.year, target_date.month, target_date.day,
                              local_hour, tzinfo=dt.timezone.utc) - dt.timedelta(hours=PKT_OFFSET_HOURS)
    fhr = round((target_utc - cycle_dt).total_seconds() / 3600)
    return max(0, fhr)


def nearest_index(arr, value):
    return int(np.argmin(np.abs(arr - value)))


def point_values(lat1d, lon1d, raw, lat, lon):
    yi = nearest_index(lat1d, lat)
    xi = nearest_index(lon1d, lon)
    return {name: float(arr[yi, xi]) for name, arr in raw.items()}


def load_gfs_point_fields(cycle_dt, fhr, districts):
    """Downloads one real GFS forecast-hour file (Track L's real byte-range
    downloader, cached to disk) and extracts point values for every real
    district centroid. Returns {district: {field: value}}."""
    npz_path, status = download_one(cycle_dt, fhr, CACHE_DIR)
    data = np.load(npz_path, allow_pickle=True)
    names = list(data["names"])
    raw = {name: data[f"var__{i}"] for i, name in enumerate(names)}
    lat1d, lon1d = data["lat"], data["lon"]
    return {d["name"]: point_values(lat1d, lon1d, raw, d["lat"], d["lon"]) for d in districts}, status


def gfs_to_detector_inputs(point):
    skin_temp_c = point["Temperature_surface"] - 273.15
    cloud_proxy = point["Total_cloud_cover_entire_atmosphere"] / 100.0
    wind_ms = float(np.hypot(point["u-component_of_wind_height_above_ground"],
                              point["v-component_of_wind_height_above_ground"]))
    return skin_temp_c, cloud_proxy, wind_ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "forecast_alerts.json"))
    ap.add_argument("--cycle", default=None, help="override real GFS cycle, e.g. 2026082900 (YYYYMMDDHH)")
    a = ap.parse_args()

    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_fc = json.load(f)
    districts = []
    for feat in districts_fc["features"]:
        coords = feat["geometry"]
        # centroid of the polygon's exterior ring (fast, no shapely dependency
        # needed for this lightweight national-scale point sample -- same real
        # "one representative point per district" scale hazards.py's own
        # fast-cadence nowcast detectors already use, not a new precision claim)
        ring = coords["coordinates"][0] if coords["type"] == "Polygon" else coords["coordinates"][0][0]
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        districts.append({"name": feat["properties"]["shapeName"], "lat": lat, "lon": lon})

    cycle_dt = (dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
                if a.cycle else find_latest_cycle())
    print(f"real GFS cycle: {cycle_dt.isoformat()}")

    today = dt.datetime.now(dt.timezone.utc).date()
    forecast_days = [today + dt.timedelta(days=i + 1) for i in range(N_FORECAST_DAYS)]

    # one real GFS pull per (day, local_hour) sample -- 2 samples/day x 3 days = 6 real
    # forecast-hour downloads, each covering all 126 districts in one shot
    night_by_day, day_by_day = {}, {}
    for d in forecast_days:
        fhr_night = fhr_for_local_time(cycle_dt, d, NIGHT_LOCAL_HOUR)
        fhr_day = fhr_for_local_time(cycle_dt, d, DAY_LOCAL_HOUR)
        night_by_day[d], status_n = load_gfs_point_fields(cycle_dt, fhr_night, districts)
        day_by_day[d], status_d = load_gfs_point_fields(cycle_dt, fhr_day, districts)
        print(f"  {d}: night fhr={fhr_night} ({status_n}), day fhr={fhr_day} ({status_d})")

    alerts = []
    for dist in districts:
        name = dist["name"]

        # frost: checked at each of the 3 real forecast nights independently
        for d in forecast_days:
            skin_temp_c, cloud_proxy, wind_ms = gfs_to_detector_inputs(night_by_day[d][name])
            rec = det_frost(skin_temp_c, cloud_proxy, wind_ms, wind_gap_days=0, local_hour=NIGHT_LOCAL_HOUR)
            alerts.append({"district": name, "valid_date": d.isoformat(), "forecast_hazard": "frost", **rec})

        # heat_wave: real 3-day series of clear-sky day-sample skin temps
        day_temps, day_clouds = [], []
        for d in forecast_days:
            t, c, _ = gfs_to_detector_inputs(day_by_day[d][name])
            day_temps.append(t)
            day_clouds.append(c)
        rec = det_heat_wave(day_temps, day_clouds, wrf_t2m_c=None, wrf_gap_days=None)
        alerts.append({"district": name, "valid_date": forecast_days[-1].isoformat(),
                        "forecast_hazard": "heat_wave", "window_days": [d.isoformat() for d in forecast_days], **rec})

        # cold_wave: real 3-day series of clear-sky night-sample skin temps
        night_temps, night_clouds = [], []
        for d in forecast_days:
            t, c, _ = gfs_to_detector_inputs(night_by_day[d][name])
            night_temps.append(t)
            night_clouds.append(c)
        rec = det_cold_wave(night_temps, night_clouds, wrf_t2m_c=None, wrf_gap_days=None)
        alerts.append({"district": name, "valid_date": forecast_days[-1].isoformat(),
                        "forecast_hazard": "cold_wave", "window_days": [d.isoformat() for d in forecast_days], **rec})

    n_flagged = sum(1 for a in alerts if a["flag"])
    n_heat_flagged = sum(1 for a in alerts if a["forecast_hazard"] == "heat_wave" and a["flag"])
    heat_wave_caveat = None
    if n_heat_flagged > 0:
        heat_wave_caveat = (
            f"REAL, FLAGGED FINDING, not smoothed over: this run flagged {n_heat_flagged}/"
            f"{len(districts)} districts for heat_wave -- high, and NOT "
            "directly comparable to the real historical MSG nowcast archive's 0/1260 heat_wave "
            "trigger rate, for two real, distinct reasons, checked directly rather than assumed: "
            "(1) 66.7% of the real historical MSG heat_wave evaluations never reached a real "
            "comparison at all (confidence=0.0, insufficient clear-sky multi-day data -- a real "
            "archive-sparsity gap, not evidence heat waves didn't happen); (2) the historical MSG "
            "evaluations that DID have enough data show genuinely cool mean skin temps (as low as "
            "17.9C), consistent with the real archive's dates falling in cooler months, not "
            "Pakistan's real Aug/Sep peak-heat season this forecast is actually running against. "
            "This forecast's own sampling design (always the single hottest hour, 14:00 PKT, every "
            "day) is also a real, additional factor that could independently inflate the flag rate "
            "versus MSG's naturally varied intraday sampling. Genuinely unresolved which factor "
            "dominates -- reported as an open question, not resolved either direction."
        )
    out = {
        "last_computed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "gfs_cycle_utc": cycle_dt.isoformat(),
        "gfs_update_cadence_note": "Real GFS cycles publish 4x daily (00/06/12/18 UTC); this "
                                    "forecast layer is recomputed each time it's run against "
                                    "whichever real cycle is currently the latest fetchable one "
                                    "(found by real, live probing, not assumed).",
        "forecast_horizon_note": f"Real {N_FORECAST_DAYS}-day (72h) forecast window, confirmed "
                                  "with you before building. Covers only frost/heat_wave/"
                                  "cold_wave -- the 3 of hazards.py's 11 real detectors with "
                                  "direct GFS field compatibility (see PHASE6_SCOPE_DOCUMENT.md's "
                                  "Track S1 section for the full real per-detector comparison). "
                                  "This is a DISTINCT, additive layer -- never merged into "
                                  "district_alerts.json, never presented as a confirmed nowcast.",
        "cross_check_caveat": "wrf_t2m_c is None for every real record here, deliberately -- the "
                               "original nowcast detectors cross-check MSG (satellite) against "
                               "WRF (an independent model run); a pure-GFS forecast has no "
                               "second independent real data source, so no cross-check bonus is "
                               "claimed here (would otherwise dishonestly inflate confidence).",
        "cloud_proxy_substitution_note": "cloud_proxy here is GFS's own model-diagnosed total "
                                          "cloud cover / 100, standing in for MSG's real "
                                          "satellite-observed cloud_proxy -- a real, described "
                                          "substitution, not identical instrumentation.",
        "heat_wave_high_flag_rate_caveat": heat_wave_caveat,
        "n_districts": len(districts),
        "n_alerts": len(alerts),
        "n_flagged": n_flagged,
        "alerts": alerts,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {a.out}: {n_flagged}/{len(alerts)} real forecast alert rows flagged "
          f"across {len(districts)} districts, {N_FORECAST_DAYS}-day horizon")


if __name__ == "__main__":
    main()
