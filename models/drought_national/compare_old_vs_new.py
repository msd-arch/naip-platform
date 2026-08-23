#!/usr/bin/env python3
"""
compare_old_vs_new.py -- Phase 4 Track M, Step 5: real side-by-side
comparison of the OLD 27km MSG-grid drought signal vs. the NEW 10m
Sentinel-2 signal, at the SAME real locations -- the original Layyah and
Muridke farm clusters (naip/data/seed/farms_layyahMuridke_Kharif2025.geojson,
the exact real 120-farm seed the old signal's bbox was built from).

OLD signal: read directly from the real, already-generated
naip/backend/alerts/district_alerts.json's drought_trends_region_level_only
(computed at 0.25deg/27km MSG grid resolution, real Kharif 2026 archive).

NEW signal: real Sentinel-2 NDVI sampled directly AT the real farm
centroids (not a district-level random sample) -- the most direct possible
apples-to-apples test of whether fine resolution actually changes the
answer at the exact same real place the old signal covered.
"""
import argparse
import json
import os

import ee

HERE = os.path.dirname(os.path.abspath(__file__))
FARMS_PATH = os.path.join(HERE, "..", "..", "data", "seed", "farms_layyahMuridke_Kharif2025.geojson")
DISTRICT_ALERTS_PATH = os.path.join(HERE, "..", "..", "backend", "alerts", "district_alerts.json")
OUT_PATH = os.path.join(HERE, "old_vs_new_comparison.json")

MONTHS = [f"{y}-{m:02d}-01" for y, m in
          [(2022, 11), (2022, 12), (2023, 1), (2023, 2), (2023, 3), (2023, 4),
           (2023, 5), (2023, 6), (2023, 7), (2023, 8), (2023, 9), (2023, 10), (2023, 11)]]
CLOUD_MASK_SCL_EXCLUDE = [0, 1, 3, 8, 9, 10, 11]


def mask_s2_clouds(img):
    scl = img.select("SCL")
    mask = scl.remap(CLOUD_MASK_SCL_EXCLUDE, [0] * len(CLOUD_MASK_SCL_EXCLUDE), 1)
    return img.updateMask(mask)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()

    with open(FARMS_PATH, encoding="utf-8") as f:
        farms = json.load(f)
    cents = []
    for feat in farms["features"]:
        coords = feat["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        cents.append((sum(lons) / len(lons), sum(lats) / len(lats)))
    lons_sorted = sorted(c[0] for c in cents)
    med_lon = lons_sorted[len(lons_sorted) // 2]
    layyah = [c for c in cents if c[0] <= med_lon]
    muridke = [c for c in cents if c[0] > med_lon]
    print(f"real farm centroids: {len(layyah)} Layyah-cluster, {len(muridke)} Muridke-cluster")

    with open(DISTRICT_ALERTS_PATH, encoding="utf-8") as f:
        district_alerts = json.load(f)
    old_trends = {t["region_en"]: t for t in district_alerts.get("drought_trends_region_level_only", [])}

    ee.Initialize(project=a.project)

    def sample_cluster(name, points):
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([lon, lat]), {"point_id": str(i)})
            for i, (lon, lat) in enumerate(points)
        ])
        monthly_ndvi = {i: [] for i in range(len(points))}
        for m in range(len(MONTHS) - 1):
            start, end = MONTHS[m], MONTHS[m + 1]
            col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                   .filterBounds(fc).filterDate(start, end).map(mask_s2_clouds))
            ndvi = col.median().normalizedDifference(["B8", "B4"]).rename("ndvi")
            reduced = ndvi.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=10).getInfo()
            for feat in reduced["features"]:
                pid = int(feat["properties"]["point_id"])
                # NOTE: reduceRegions on a single-band image names the output
                # property after the REDUCER ("mean"), not the band name --
                # confirmed by direct inspection, unlike the multi-band case
                # extract_phenology_features.py uses (which preserves band names).
                v = feat["properties"].get("mean")
                if v is not None:
                    monthly_ndvi[pid].append(v)
            print(f"  [{name}] month {m + 1}/{len(MONTHS) - 1} ({start[:7]}) done")
        all_vals = [v for series in monthly_ndvi.values() for v in series]
        return all_vals

    layyah_vals = sample_cluster("Layyah", layyah)
    muridke_vals = sample_cluster("Muridke", muridke)

    def summarize(vals):
        import statistics
        return {"n_real_farm_month_samples": len(vals), "mean_ndvi": round(statistics.mean(vals), 4),
                "min_ndvi": round(min(vals), 4), "max_ndvi": round(max(vals), 4),
                "stdev_ndvi": round(statistics.pstdev(vals), 4) if len(vals) > 1 else None}

    out = {
        "note": "Real side-by-side comparison at the exact same real locations (the original "
                "120-farm Layyah/Muridke seed) -- OLD = 0.25deg/27km MSG-grid regional bbox "
                "signal (real Kharif 2026 archive), NEW = real 10m Sentinel-2 NDVI sampled "
                "directly at real farm centroids (Nov 2022-Oct 2023, real cloud-masked composites).",
        "layyah": {
            "old_msg_27km": old_trends.get("Layyah farm cluster"),
            "new_s2_10m_at_real_farms": summarize(layyah_vals),
        },
        "muridke": {
            "old_msg_27km": old_trends.get("Muridke farm cluster"),
            "new_s2_10m_at_real_farms": summarize(muridke_vals),
        },
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT_PATH}")
    print(json.dumps(out, indent=2, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
