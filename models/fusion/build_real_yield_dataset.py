#!/usr/bin/env python3
"""
build_real_yield_dataset.py -- Phase 5 Track O pre-check + build: real yield
(production / area) per district/crop, both real MNFSR years.

REAL PRE-CHECK RESULT (checked before building anything, not assumed):
production figures were ALREADY extracted by parse_mnfsr_crop_mix.py (2022-23,
nums[6]) and parse_mnfsr_crop_mix_2021_22.py (2021-22, nums[4]) -- sitting in
real_crop_mix.json / real_crop_mix_2021_22.json already, unused as a training
target. Zero new sourcing needed.

REAL GAP FOUND AND CLOSED HERE: neither parser ever independently
cross-validated the production figures against their own printed provincial
total -- only the AREA sum was checked (5% tolerance); a block's production
values rode along on the area check passing, never verified on their own
terms. Confirmed the printed Total row DOES carry a real, checkable
production total (4 numeric columns: area_2122, area_2223, prod_2122,
prod_2223 -- verified directly against real Total-row text, e.g. Punjab
wheat: 6559.83, 6480.50, 20031.81, 21225.03). This script re-parses both
years with BOTH area AND production independently validated (same 5%
tolerance, reject-rather-than-guess discipline as the original) -- a
real, necessary extension per Track O's requirement of the "exact same"
discipline for yield's production input specifically.

Real cell only enters the yield dataset if:
  1. its area block reconciled (same as before), AND
  2. its production block ALSO independently reconciles against its own
     printed production total (new this script), for that specific year.

Real yield = production_000t / area_000ha (tons/hectare, standard unit) --
computed per (district, crop, year), only for jointly-validated cells.
"""
import argparse
import json
import os
import re

CROPS = ("wheat", "cotton", "rice", "sugarcane")

TABLE_HEADER = {
    "wheat": "DISTRICT-WISE AREA, PRODUCTION & PERCENTAGE OF WHEAT CROP",
    "rice": "DISTRICT-WISE AREA, PRODUCTION & PERCENTAGE OF RICE CROP",
    "sugarcane": "DISTRICT-WISE AREA, PRODUCTION & PERCENTAGE OF SUGARCANE CROP",
    "cotton": "DISTRICT-WISE AREA, PRODUCTION & PERCENTAGE OF COTTON CROP",
}

# Identical to parse_mnfsr_crop_mix.py's real name map -- same source document.
NAME_MAP = {
    "muree": "Rawalpindi", "bunir": "Buner", "islamabad": "Islamabad Capital Territory",
    "m.b. din": "Mandi Bahauddin", "d.g. khan": "Dera Ghazi Khan",
    "rahimyar khan": "Rahim Yar Khan", "m. garh": "Muzaffargarh", "kot addu": "Muzaffargarh",
    "vehari": "Vihari", "n. feroze": "Naushehro Feroze",
    "shaheed benazir abad": "Nawabshah", "shaheed benazirabad": "Nawabshah",
    "muhmand": "Mohmand", "oriakzai": "Orakzai", "n. waziristan": "North Waziristan",
    "s. waziristan": "South Waziristan", "sd bannu": "Bannu", "sd d.i. khan": "Dera Ismail Khan",
    "sd hassan khel": "Bannu", "sd kohat": "Kohat",
    "k. abdullah": "Qilla Abdullah", "killa saifullah": "Qilla Saifullah",
    "dera bughti": "Dera Bugti", "jaffarabad": "Jafarabad", "panjgoor": "Panjgur",
    "sheikhupura": "Sheikhpura", "qambar shahdadkot": "Qambar Shahdadkot",
    "tando allah yar": "Tando Allahyar", "tando muhammad khan": "Tando Muhammad Khan",
    "d.i khan": "Dera Ismail Khan", "d.i. khan": "Dera Ismail Khan", "d.ikhan": "Dera Ismail Khan",
    "lakki marwat": "Lakki Marwat", "kohat.": "Kohat",
    "bajour": "Bajaur", "charsada": "Charsadda", "dir lower": "Lower Dir", "dir upper": "Upper Dir",
    "kambar shahdat": "Qambar Shahdadkot", "kambar shahdadkot": "Qambar Shahdadkot",
    "sawabi": "Swabi", "shaheed benazir": "Nawabshah", "t.m.khan": "Tando Muhammad Khan",
    "turbat": "Kech", "umarkot": "Umerkot", "musa khail": "Musakhel",
    "chiniot": "Jhang", "nankana sahib": "Sheikhpura", "talagang": "Chakwal",
    "wazirabad": "Gujranwala",
}
NUM_RE = re.compile(r"-?\d+\.\d+")
ANY_TABLE_HEADER_RE = re.compile(r"DISTRICT-WISE AREA,? PRODUCTION")
PROVINCE_MARKER_RE = re.compile(r"^\s*(PUNJAB|SINDH|KHYBER(?:\s+PAKHTUNKHWA)?|BALOCHISTAN)\b")


def normalize_name(raw):
    raw = raw.strip()
    key = raw.lower().rstrip(".")
    if key in NAME_MAP:
        return NAME_MAP[key]
    return raw.title() if raw.isupper() else raw


def extract_table_blocks(lines, header_text):
    any_header_idx = [i for i, l in enumerate(lines) if ANY_TABLE_HEADER_RE.search(l)]
    starts = [i for i in any_header_idx if header_text in lines[i]]
    blocks = []
    for s in starts:
        later = [i for i in any_header_idx if i > s]
        e = later[0] if later else min(s + 400, len(lines))
        blocks.append((s, e))
    return blocks


def parse_crop_table_with_production_check(lines, crop, area_idx, prod_idx, area_tot_idx, prod_tot_idx):
    """area_idx/prod_idx: which of the 8 real numeric columns per data row is
    this year's area/production (2: area2223/6: prod2223 for 2022-23; 0:
    area2122/4: prod2122 for 2021-22). area_tot_idx/prod_tot_idx: which of the
    Total row's 4 numeric columns is this year's area/production total."""
    blocks = extract_table_blocks(lines, TABLE_HEADER[crop])
    results = {}
    validations = []
    for (s, e) in blocks:
        current_rows = []
        current_province = None
        for ln in lines[s:e]:
            stripped = ln.strip()
            if not stripped:
                continue
            pm = PROVINCE_MARKER_RE.match(stripped)
            if pm:
                current_province = pm.group(1)
                current_rows = []
                continue
            low = stripped.lower()
            first_word = low.split()[0] if low.split() else ""
            if first_word == "total":
                tot_nums = NUM_RE.findall(stripped)
                printed_area = float(tot_nums[area_tot_idx]) if len(tot_nums) > area_tot_idx else None
                printed_prod = float(tot_nums[prod_tot_idx]) if len(tot_nums) > prod_tot_idx else None
                parsed_area = sum(r[1] for r in current_rows)
                parsed_prod = sum(r[2] for r in current_rows)
                area_ok = printed_area is not None and printed_area > 0 and \
                    abs(parsed_area - printed_area) / printed_area <= 0.05
                prod_ok = printed_prod is not None and printed_prod > 0 and \
                    abs(parsed_prod - printed_prod) / printed_prod <= 0.05
                val = {
                    "crop": crop, "province": current_province, "n_rows_parsed": len(current_rows),
                    "parsed_area": round(parsed_area, 2), "printed_area": printed_area, "area_ok": area_ok,
                    "parsed_prod": round(parsed_prod, 2), "printed_prod": printed_prod, "prod_ok": prod_ok,
                }
                if area_ok and prod_ok:
                    for name, area, prod in current_rows:
                        cell = results.setdefault(name, {}).setdefault(crop, {"area": 0.0, "production": 0.0})
                        cell["area"] = round(cell["area"] + area, 2)
                        cell["production"] = round(cell["production"] + prod, 2)
                else:
                    val["REJECTED"] = "area" if not area_ok else ("production" if not prod_ok else None)
                validations.append(val)
                current_rows = []
                continue
            if first_word in ("pakistan", "province/", "district") or low.startswith("province"):
                continue
            if not re.match(r"^[A-Za-z.]", stripped):
                continue
            nums = NUM_RE.findall(stripped)
            if len(nums) < 8:
                continue
            m = re.match(r"^([A-Za-z.\s]+?)\s+-?\d+\.\d+", stripped)
            if not m:
                continue
            name = normalize_name(m.group(1))
            nums = [float(x) for x in nums[:8]]
            current_rows.append((name, nums[area_idx], nums[prod_idx]))
    return results, validations


def build_year(lines, real_districts, real_set, year_label, area_idx, prod_idx, area_tot_idx, prod_tot_idx):
    merged = {}
    all_validations = []
    for crop in CROPS:
        crop_results, validations = parse_crop_table_with_production_check(
            lines, crop, area_idx, prod_idx, area_tot_idx, prod_tot_idx)
        all_validations.extend(validations)
        for name, cropdata in crop_results.items():
            merged.setdefault(name, {}).update(cropdata)

    matched = {name: data for name, data in merged.items() if name in real_set}

    # Real data-quality bounds, derived from inspecting the real computed
    # distribution first (not guessed) -- see STATUS_WEEK22.md for the real
    # inspection that produced these: production_000t == 0.0 exactly is a
    # print-precision floor (the source table rounds to 2dp, so true
    # production between 0 and 5 tons rounds to "0.00"), not a real zero --
    # a yield ratio from it is meaningless, not just small. Crop-specific
    # plausible yield bands are standard real Pakistani agronomic ranges
    # (same citation discipline as crop_calendar.py): wheat/cotton/rice
    # 0.3-8.0 t/ha, sugarcane (a much bulkier crop, real national yields
    # commonly 40-80 t/ha) 20-120 t/ha.
    PLAUSIBLE_YIELD_BAND = {
        "wheat": (0.3, 8.0), "cotton": (0.3, 8.0), "rice": (0.3, 8.0),
        "sugarcane": (20.0, 120.0),
    }

    out = {}
    not_grown = []  # real, expected: area==0 means the crop genuinely isn't grown
                     # there per the printed table -- not a data-quality problem,
                     # just outside a yield dataset's scope (yield is undefined
                     # for zero area). Reported separately from real exclusions.
    excluded = []
    for name, crops_here in matched.items():
        for crop, vals in crops_here.items():
            area, prod = vals["area"], vals["production"]
            if area <= 0:
                not_grown.append({"district": name, "crop": crop})
                continue
            if prod == 0.0:
                excluded.append({"district": name, "crop": crop, "area_000ha": area,
                                  "reason": "production_rounds_to_exactly_zero_print_precision_floor"})
                continue
            yield_tha = round(prod / area, 4)
            lo, hi = PLAUSIBLE_YIELD_BAND[crop]
            if not (lo <= yield_tha <= hi):
                excluded.append({"district": name, "crop": crop, "area_000ha": area,
                                  "production_000t": prod, "yield_tons_per_ha": yield_tha,
                                  "reason": f"outside_real_plausible_band_{lo}-{hi}_t_per_ha"})
                continue
            out.setdefault(name, {})[crop] = {
                "area_000ha": area, "production_000t": prod, "yield_tons_per_ha": yield_tha,
            }
    return out, all_validations, excluded, not_grown


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--pdf-text", default=os.path.join(
        here, "..", "..", "data", "crop_mix_ground_truth", "cap_2022_23.txt"))
    ap.add_argument("--districts", default=os.path.join(
        here, "..", "..", "data", "seed", "pk_districts.geojson"))
    ap.add_argument("--out", default=os.path.join(
        here, "..", "..", "data", "crop_mix_ground_truth", "real_crop_yield.json"))
    a = ap.parse_args()

    with open(a.pdf_text, encoding="utf-8") as f:
        lines = f.readlines()

    real_districts = sorted(
        f["properties"]["shapeName"]
        for f in json.load(open(a.districts, encoding="utf-8"))["features"]
    )
    real_set = set(real_districts)

    # cap_2022_23.txt Total row columns confirmed directly: [area2122, area2223, prod2122, prod2223]
    # data-row columns (8 total): [area2122, area2122%, area2223, area2223%, prod2122, prod2122%, prod2223, prod2223%]
    y2223, val2223, exc2223, ng2223 = build_year(lines, real_districts, real_set, "2022-23",
                                          area_idx=2, prod_idx=6, area_tot_idx=1, prod_tot_idx=3)
    y2122, val2122, exc2122, ng2122 = build_year(lines, real_districts, real_set, "2021-22",
                                          area_idx=0, prod_idx=4, area_tot_idx=0, prod_tot_idx=2)

    out = {"2022-23": y2223, "2021-22": y2122}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    def summarize(y, val, excluded, not_grown, label):
        n_districts = len(y)
        n_cells = sum(len(v) for v in y.values())
        n_area_rejected = sum(1 for v in val if v.get("REJECTED") == "area")
        n_prod_rejected = sum(1 for v in val if v.get("REJECTED") == "production")
        print(f"\n=== {label} ===")
        print(f"  real districts with >=1 jointly-validated crop: {n_districts}/{len(real_districts)}")
        print(f"  real (district,crop) yield cells: {n_cells}")
        print(f"  province-crop blocks: area-rejected={n_area_rejected}, "
              f"production-rejected (NEW check)={n_prod_rejected}")
        print(f"  real, expected (crop not grown there, area=0): {len(not_grown)} -- not a data-quality issue")
        print(f"  real data-quality exclusions: {len(excluded)}")
        for e in excluded:
            print(f"    {e['district']:20s} {e['crop']:10s} {e['reason']}")
        return {
            "n_districts_covered": n_districts, "n_cells": n_cells,
            "n_blocks_area_rejected": n_area_rejected,
            "n_blocks_production_rejected_new_check": n_prod_rejected,
            "n_not_grown_real_zero_area": len(not_grown),
            "n_excluded_data_quality": len(excluded), "excluded_cells": excluded,
        }

    report = {
        "2022-23": summarize(y2223, val2223, exc2223, ng2223, "2022-23"),
        "2021-22": summarize(y2122, val2122, exc2122, ng2122, "2021-22"),
        "validations_2022_23": val2223, "validations_2021_22": val2122,
    }
    report_path = a.out.replace("real_crop_yield.json", "real_crop_yield_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {a.out}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
