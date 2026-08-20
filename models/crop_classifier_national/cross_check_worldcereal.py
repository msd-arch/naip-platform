#!/usr/bin/env python3
"""
cross_check_worldcereal.py -- Phase 3 Track F: the one real, honest
cross-check this track can make between WorldCereal and Track C's real
MNFSR district crop-mix data.

WHY ONLY WHEAT: confirmed (not assumed) that WorldCereal has no crop-type
product for Pakistan at all -- the real global collection only ever has
temporarycrops/irrigation/maize/wintercereals/springcereals, nationally, not
just for Layyah/Muridke. There is nothing to cross-check MNFSR's real
cotton/rice/sugarcane shares against. 'wintercereals' is a real, defensible
proxy for wheat specifically, since wheat is the dominant real Rabi winter
cereal in Pakistan (crop_calendar.py's own real AIS Pakistan sourcing
already documents this). This script reports real agreement/disagreement
between the two independent real sources for wheat ONLY -- it does not
force a comparison for the other three crops where none is possible.

For each of the 115 real MNFSR-covered districts: real WorldCereal
wintercereals areal fraction (mean of classification==100 over the real
district polygon, 100m scale) vs. real MNFSR wheat area share.

Usage:
    python cross_check_worldcereal.py --project printtheory
"""
import argparse
import json
import os

import ee
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CROP_MIX_PATH = os.path.join(HERE, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json")
DISTRICTS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")
OUT_PATH = os.path.join(HERE, "worldcereal_mnfsr_wheat_crosscheck.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    ee.Initialize(project=a.project)

    with open(CROP_MIX_PATH, encoding="utf-8") as f:
        crop_mix = json.load(f)
    with open(DISTRICTS_PATH, encoding="utf-8") as f:
        districts_geojson = json.load(f)
    by_name = {f["properties"]["shapeName"]: f["geometry"] for f in districts_geojson["features"]}

    wintercereals = (ee.ImageCollection("ESA/WorldCereal/2021/MODELS/v100")
                      .filter(ee.Filter.eq("product", "wintercereals")).select("classification").mosaic())
    temporarycrops = (ee.ImageCollection("ESA/WorldCereal/2021/MODELS/v100")
                       .filter(ee.Filter.eq("product", "temporarycrops")).select("classification").mosaic())
    is_wc = wintercereals.eq(100)
    is_cropland = temporarycrops.eq(100)
    combined = ee.Image.cat([is_wc.rename("wc"), is_cropland.rename("cropland")])

    rows = []
    real_districts = [n for n, rec in crop_mix.items() if rec["tier"] == "real_district_area"
                       and "wheat" in rec["crops"]]
    print(f"{len(real_districts)} real districts with both a real MNFSR wheat share and a real polygon")

    for i, name in enumerate(real_districts):
        geom = ee.Geometry(by_name[name])
        stats = combined.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=100,
                                       maxPixels=1e10, bestEffort=True).getInfo()
        wc_frac_of_total_area = stats.get("wc")
        cropland_frac_of_total_area = stats.get("cropland")
        # denominator-matched comparison: WorldCereal wintercereals AS A SHARE OF CROPLAND,
        # not of total district area -- MNFSR's wheat share is itself a share of the 4
        # reported crops' area, not of the district's total area (a district can be mostly
        # non-arable desert/mountain with a small, 100%-wheat cropped patch -- comparing
        # against total-area fractions would spuriously read as disagreement there)
        wc_share_of_cropland = (wc_frac_of_total_area / cropland_frac_of_total_area
                                 if cropland_frac_of_total_area and cropland_frac_of_total_area > 0.01 else None)
        mnfsr_share = crop_mix[name]["crops"]["wheat"]["share_of_4crop_area"]
        rows.append({"district": name,
                      "worldcereal_wintercereals_frac_of_total_area": wc_frac_of_total_area,
                      "worldcereal_cropland_frac_of_total_area": cropland_frac_of_total_area,
                      "worldcereal_wintercereals_share_of_cropland": wc_share_of_cropland,
                      "mnfsr_wheat_share_of_4crop_area": mnfsr_share})
        print(f"[{i+1}/{len(real_districts)}] {name}: WC wintercereals/cropland="
              f"{wc_share_of_cropland}, MNFSR wheat_share={mnfsr_share}")

    valid = [r for r in rows if r["worldcereal_wintercereals_share_of_cropland"] is not None]
    wc_vals = np.array([r["worldcereal_wintercereals_share_of_cropland"] for r in valid])
    mn_vals = np.array([r["mnfsr_wheat_share_of_4crop_area"] for r in valid])
    corr = float(np.corrcoef(wc_vals, mn_vals)[0, 1]) if len(valid) > 2 else None
    mae = float(np.mean(np.abs(wc_vals - mn_vals)))

    out = {
        "n_districts_compared": len(valid),
        "pearson_correlation": round(corr, 3) if corr is not None else None,
        "mean_absolute_difference": round(mae, 3),
        "note": "WorldCereal 'wintercereals' SHARE OF CROPLAND (not of total district area -- "
                "denominator-matched to MNFSR's own share-of-cropped-area definition, after a "
                "first raw-area-fraction attempt gave a spurious negative correlation caused "
                "by exactly this denominator mismatch, see naip/docs/STATUS_WEEK8.md) vs. real "
                "MNFSR wheat area share -- the ONE crop both real sources can be compared on, "
                "WorldCereal has no cotton/rice/sugarcane product for Pakistan.",
        "records": rows,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nreal correlation (WorldCereal wintercereals vs MNFSR wheat share): {corr}")
    print(f"real mean absolute difference: {mae:.3f}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
