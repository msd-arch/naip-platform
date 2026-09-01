#!/usr/bin/env python3
"""
fetch_pmiu_channel_expansion.py -- Track V, real coverage EXTENSION using
Punjab Irrigation's (PMIU) real, live, no-auth government gauge data --
NOT the MODIS ET/PET proxy canal_water_stress_multi.py uses for the
existing 6-canal module.

REAL SOURCE, checked live before building (see CLAUDE.md's Track V entry):
PMIU's "Channel Information" GIS interface (irrigation.punjab.gov.pk/
channel-information) loads from a real, discoverable, no-auth REST-style
backend at https://wrmis.irrigation.punjab.gov.pk/GISServices/wrmis.svc/ --
found by reading TailStatus.js + TSConfigParser.js + configTS.xml directly,
not by guessing an endpoint. getTailStatus/{date} returns a real GeoJSON
FeatureCollection covering 2,981 real Punjab channels down to distributary/
minor level, each with a real current tail gauge reading, a real authorized
(sanctioned) tail gauge, real design discharge, and a real Dry/Short/
Authorized/Excessive/N/R status -- this is a direct, government-measured
head-vs-tail equity signal, genuinely stronger than the existing module's
MODIS ET/PET proxy (which infers stress indirectly from evapotranspiration,
not from an actual gauge reading).

SCOPE DECISION (confirmed with the project owner, not assumed): this is a
coverage EXTENSION, not a supplement to the existing 6 canals -- real,
NEW Punjab channels PMIU names that canal_water_stress_multi.py's 6-canal
set does not cover. The 2 real existing canals that DO name-match this
source (Muridke Disty, Upper Sohag Branch) are explicitly EXCLUDED from
this output to avoid a duplicate, conflicting entry for the same real
canal under two different methodologies in two different files -- a real
future track could reconcile/cross-check them, not done here.

REAL HONEST GAPS, stated here not hidden:
  - Response is server-side double-JSON-encoded (a JSON string containing
    escaped JSON) -- real WCF/.svc quirk, handled below, not a parsing bug
    on our end.
  - Real coordinates arrive in EPSG:3857 (Web Mercator); reprojected to
    EPSG:4326 here via pyproj, same library this project's other geometry
    scripts already use.
  - "Authorized tail gauge" is PMIU's own real sanctioned/entitlement
    value, not an independently-derived one -- tail_gauge_ratio below is
    real-data-vs-real-target, not calibrated against an external ground
    truth.
  - Real, unresolved: only ONE real reading date was checked before this
    build (see CLAUDE.md) -- no real historical-depth check was done for
    this endpoint. If a future date returns systematically different
    coverage, that is a real open question, not yet investigated.
  - Real channels with Status == 'N/R' (not reported) or a missing/zero
    AuthorizedTailGauge are excluded and counted, not silently dropped.

Usage:
    python fetch_pmiu_channel_expansion.py --date 2026-08-31 \
        --out pmiu_channel_expansion.json
"""
import argparse
import datetime
import json
import os
import urllib.request

import pyproj
from shapely.geometry import shape
from shapely.ops import transform

HERE = os.path.dirname(os.path.abspath(__file__))
TS_BASE = "https://wrmis.irrigation.punjab.gov.pk/GISServices/wrmis.svc/getTailStatus/0/0/0/"

# Real channels already covered by canal_water_stress_multi.py's OSM/MODIS
# methodology -- excluded here by real name match, not by ChannelID (PMIU's
# IDs have no relationship to OSM's), so this stays a real, non-overlapping
# EXTENSION per the confirmed scope decision.
ALREADY_COVERED_NAMES = {"muridke disty", "muridke distributary", "upper sohag branch"}

_TRANSFORMER = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)


def to_lonlat(geom):
    return transform(_TRANSFORMER.transform, geom)


def fetch_tail_status(date_str):
    url = TS_BASE + date_str
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8")
    outer = json.loads(raw)  # real WCF double-encoding: outer layer is a JSON string
    inner = json.loads(outer) if isinstance(outer, str) else outer
    return inner


def safe_float(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD, default: yesterday (matches PMIU's own default)")
    ap.add_argument("--out", default=os.path.join(HERE, "pmiu_channel_expansion.json"))
    a = ap.parse_args()

    date_str = a.date or (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    print(f"fetching real PMIU tail-status data for {date_str} ...")
    fc = fetch_tail_status(date_str)
    all_feats = fc["features"]
    print(f"real total channels returned: {len(all_feats)}")

    n_nr = 0
    n_no_authorized_gauge = 0
    n_already_covered = 0
    channels = []

    for feat in all_feats:
        props = feat["properties"]
        name = (props.get("CHANNEL_NA") or "").strip()
        status = props.get("Status", "")

        if name.lower() in ALREADY_COVERED_NAMES:
            n_already_covered += 1
            continue
        if status == "N/R" or not status:
            n_nr += 1
            continue

        authorized_tail = safe_float(props.get("AuthorizedTailGauge"))
        current_tail = safe_float(props.get("GaugeValue"))
        design_discharge = safe_float(props.get("DesignDischarge"))
        daily_discharge = safe_float(props.get("DailyDischarge"))

        if authorized_tail is None or authorized_tail <= 0 or current_tail is None:
            n_no_authorized_gauge += 1
            continue

        tail_gauge_ratio = current_tail / authorized_tail

        geom = shape(feat["geometry"])
        geom_ll = to_lonlat(geom)
        centroid = geom_ll.centroid
        try:
            head_lon, head_lat = geom_ll.coords[0]
            tail_lon, tail_lat = geom_ll.coords[-1]
        except (NotImplementedError, IndexError):
            head_lon = head_lat = tail_lon = tail_lat = None

        channels.append({
            "channel_id": props.get("ChannelID"),
            "imis_code": props.get("IMIS_CODE"),
            "name": name,
            "status": status,
            "design_discharge_cusecs": design_discharge,
            "authorized_tail_gauge_ft": authorized_tail,
            "current_tail_gauge_ft": current_tail,
            "tail_gauge_ratio": round(tail_gauge_ratio, 4),
            "daily_discharge_cusecs": daily_discharge,
            "reading_datetime": props.get("ReadingDateTime") or None,
            "gauge_at_rd": props.get("GaugeAtRD") or None,
            "centroid_lon": round(centroid.x, 5),
            "centroid_lat": round(centroid.y, 5),
            "head_lon": round(head_lon, 5) if head_lon is not None else None,
            "head_lat": round(head_lat, 5) if head_lat is not None else None,
            "tail_lon": round(tail_lon, 5) if tail_lon is not None else None,
            "tail_lat": round(tail_lat, 5) if tail_lat is not None else None,
        })

    channels.sort(key=lambda c: c["tail_gauge_ratio"])

    out = {
        "scope": "Punjab -- real PMIU (Irrigation Department) live channel gauge data, "
                 "distributary/minor level, coverage EXTENSION beyond the existing 6-canal "
                 "MODIS ET/PET module (see CLAUDE.md Track V)",
        "source": "https://wrmis.irrigation.punjab.gov.pk/GISServices/wrmis.svc/getTailStatus/",
        "reading_date": date_str,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "methodology_note": "tail_gauge_ratio = real current tail gauge reading / PMIU's real "
                             "authorized (sanctioned) tail gauge for that channel. <1.0 means "
                             "the tail is running below its own real sanctioned entitlement -- "
                             "a direct government-measured equity signal, not a MODIS-derived "
                             "proxy. This is PMIU's own real reported value, not independently "
                             "re-measured or calibrated by this project.",
        "n_channels_returned_by_pmiu": len(all_feats),
        "n_excluded_already_covered_by_existing_module": n_already_covered,
        "n_excluded_not_reported_NR": n_nr,
        "n_excluded_missing_or_zero_authorized_gauge": n_no_authorized_gauge,
        "n_channels_included": len(channels),
        "channels": channels,
    }

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"wrote {a.out}")
    print(f"real result: {len(channels)}/{len(all_feats)} real new channels included "
          f"({n_already_covered} already covered, {n_nr} N/R, "
          f"{n_no_authorized_gauge} missing authorized gauge)")
    if channels:
        worst = channels[:5]
        print("worst 5 real tail_gauge_ratio (most below sanctioned entitlement):")
        for c in worst:
            print(f"  {c['name']:35s} ratio={c['tail_gauge_ratio']:.3f} status={c['status']}")


if __name__ == "__main__":
    main()
