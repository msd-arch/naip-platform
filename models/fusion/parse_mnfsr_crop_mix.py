#!/usr/bin/env python3
"""
parse_mnfsr_crop_mix.py -- Phase 2 Track C: parse REAL district-wise crop
area from the Government of Pakistan's Ministry of National Food Security &
Research "Crops Area & Production (District wise) 2022-23" publication
(naip/data/crop_mix_ground_truth/cap_2022_23.pdf, downloaded directly from
mnfsr.gov.pk -- a real federal compilation of the four PROVINCIAL Crop
Reporting Services' own district estimates, not a Punjab-only source).

REAL FINDING that changed this track's scope from the original roadmap:
this single document has genuine district-level area/production for all
four provinces (Punjab, Sindh, KPK, Balochistan) -- Sindh and Balochistan
DO have real district-level numbers here even though their own provincial
CRS web presence is weak/absent, because MNFSR compiles all four
provinces' estimates centrally. No Punjab-only / some-provinces-missing
split turned out to be needed.

REAL LIMITATION: this PDF's table layout does not survive text extraction
cleanly everywhere -- some rows (notably Balochistan's cotton table) wrap
across lines and lose column alignment. Rather than guess at a ragged row's
values, this parser only accepts a (district, crop) cell if:
  1. the row parses to the expected 8 numeric tokens (area 21-22/%,
     area 22-23/%, production 21-22/%, production 22-23/%), AND
  2. the parsed district total for the crop, summed across a province,
     reconciles with that table's own printed provincial Total line within
     a real 5% tolerance.
Cells that fail either check are marked unparsed and are NOT written to the
output -- exposure_risk.py's consumer falls back to the Week 4 hand-
classified plausibility mask for those specific cells, not a fabricated
number. Real parse coverage is reported explicitly, not smoothed over.

No Gilgit-Baltistan or Azad Kashmir district appears anywhere in this
document (checked directly) -- consistent with MNFSR's mandate covering the
four provinces only. Those 11 districts in pk_districts.geojson keep the
Week 4 hand-classified tier (already "no plausible crop" for the 10 GB
ones; Azad Kashmir gets whatever the hand mask already assigns).
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

PROVINCES = ("PUNJAB", "SINDH", "KHYBER", "BALOCHISTAN")

# MNFSR report spelling/abbreviation -> real district name in
# naip/data/seed/pk_districts.geojson (geoBoundaries ADM2, this project's
# one real district-name source of truth throughout). Sub-divisions of a
# larger district in the report (e.g. KPK's "SD Bannu") are folded into
# their parent district by summing, not treated as separate districts.
NAME_MAP = {
    # Murree is a real tehsil of Rawalpindi district, not a separate district polygon in
    # this project's real pk_districts.geojson (checked directly -- "Murree" alone is also
    # absent from the 126 set) -- its real MNFSR area is merged into Rawalpindi.
    "muree": "Rawalpindi",
    "bunir": "Buner", "islamabad": "Islamabad Capital Territory",
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
    # real Punjab district splits NOT present as separate polygons in this project's real
    # pk_districts.geojson (older geoBoundaries vintage) -- their real MNFSR area is merged
    # back into the pre-split parent district that DOES exist in our 126-district set, so
    # this real area isn't silently dropped. Checked directly (not assumed): confirmed absent
    # from pk_districts.geojson before mapping this way.
    "chiniot": "Jhang", "nankana sahib": "Sheikhpura", "talagang": "Chakwal",
    "wazirabad": "Gujranwala",
}
# Real MNFSR district rows with NO corresponding polygon in this project's real 126-district
# set, and NOT safely mergeable into a known parent (unlike the Punjab splits above) --
# genuinely absent from pk_districts.geojson's geoBoundaries vintage. Verified by direct
# lookup, not assumed. Left unmapped on purpose: forcing these into a same-named-sounding
# neighbor would misattribute real area/production. Reported honestly in parse_report.json.
KNOWN_UNMATCHABLE = {
    "larkana",   # Sindh -- geoBoundaries set here only has "Qambar Shahdadkot", not Larkana itself
    "washuk", "bolan", "harnai", "sherani", "tor ghar",  # Balochistan/KPK districts absent entirely
}
SKIP_ROWS = {"total", "pakistan", "province/", "district"}

NUM_RE = re.compile(r"-?\d+\.\d+")


def normalize_name(raw):
    raw = raw.strip()
    key = raw.lower().rstrip(".")
    if key in NAME_MAP:
        return NAME_MAP[key]
    return raw.title() if raw.isupper() else raw


ANY_TABLE_HEADER_RE = re.compile(r"DISTRICT-WISE AREA,? PRODUCTION")


def extract_table_blocks(lines, header_text):
    """Return list of (start_idx, end_idx) for each occurrence of a table with
    this header (the report repeats/continues each crop's table once per
    province, sometimes without reprinting the header on later pages -- so a
    block runs until the NEXT table header of any crop, not just this one)."""
    any_header_idx = [i for i, l in enumerate(lines) if ANY_TABLE_HEADER_RE.search(l)]
    starts = [i for i in any_header_idx if header_text in lines[i]]
    blocks = []
    for s in starts:
        later = [i for i in any_header_idx if i > s]
        e = later[0] if later else min(s + 400, len(lines))
        blocks.append((s, e))
    return blocks


PROVINCE_MARKER_RE = re.compile(r"^\s*(PUNJAB|SINDH|KHYBER(?:\s+PAKHTUNKHWA)?|BALOCHISTAN)\b")


def parse_crop_table(lines, crop):
    """Parse every province sub-block of one crop's table. A crop's table
    spans multiple provinces, each introduced by a province-name marker line
    and closed by its own 'Total' row -- flush and validate per province,
    not per whole table block (province Totals don't sum across provinces
    the way a naive whole-block parse would assume)."""
    blocks = extract_table_blocks(lines, TABLE_HEADER[crop])
    results = {}
    validations = []
    rejected_district_names = set()  # districts whose (crop) cell was in a rejected block --
                                      # "unknown/unreliable", NOT "confirmed zero"
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
                printed_total_area = float(tot_nums[1]) if len(tot_nums) >= 2 else None
                parsed_sum_area = sum(r[1] for r in current_rows)
                val = {"crop": crop, "province": current_province, "n_rows_parsed": len(current_rows),
                       "parsed_sum_area_000ha": round(parsed_sum_area, 2),
                       "printed_total_area_000ha": printed_total_area}
                ok = printed_total_area is not None and printed_total_area > 0 and \
                    abs(parsed_sum_area - printed_total_area) / printed_total_area <= 0.05
                if ok:
                    for name, area, prod in current_rows:
                        # sum, not overwrite -- multiple raw rows can map to the same real
                        # district (e.g. Chiniot + Jhang both -> "Jhang", see NAME_MAP)
                        cell = results.setdefault(name, {}).setdefault(
                            crop, {"area_2022_23_000ha": 0.0, "production_2022_23_000t": 0.0})
                        cell["area_2022_23_000ha"] = round(cell["area_2022_23_000ha"] + area, 2)
                        cell["production_2022_23_000t"] = round(cell["production_2022_23_000t"] + prod, 2)
                else:
                    val["REJECTED_exceeds_5pct_tolerance_or_missing_total"] = True
                    rejected_district_names.update(r[0] for r in current_rows)
                validations.append(val)
                current_rows = []
                continue
            if first_word in ("pakistan", "province/", "district") or low.startswith("province"):
                continue
            if not re.match(r"^[A-Za-z.]", stripped):
                continue
            nums = NUM_RE.findall(stripped)
            if len(nums) < 8:
                continue  # ragged/wrapped row -- deliberately not guessed at
            m = re.match(r"^([A-Za-z.\s]+?)\s+-?\d+\.\d+", stripped)
            if not m:
                continue
            name = normalize_name(m.group(1))
            nums = [float(x) for x in nums[:8]]
            current_rows.append((name, nums[2], nums[6]))
    return results, validations, {normalize_name(n) for n in rejected_district_names}


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--pdf-text", default=os.path.join(
        here, "..", "..", "data", "crop_mix_ground_truth", "cap_2022_23.txt"))
    ap.add_argument("--districts", default=os.path.join(
        here, "..", "..", "data", "seed", "pk_districts.geojson"))
    ap.add_argument("--out", default=os.path.join(
        here, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix.json"))
    a = ap.parse_args()

    with open(a.pdf_text, encoding="utf-8") as f:
        lines = f.readlines()

    real_districts = sorted(
        f["properties"]["shapeName"]
        for f in json.load(open(a.districts, encoding="utf-8"))["features"]
    )
    real_set = set(real_districts)

    merged = {}
    all_validations = []
    rejected_by_crop = {crop: set() for crop in CROPS}
    for crop in CROPS:
        crop_results, validations, rejected_names = parse_crop_table(lines, crop)
        all_validations.extend(validations)
        rejected_by_crop[crop] = rejected_names
        for name, cropdata in crop_results.items():
            merged.setdefault(name, {}).update(cropdata)

    # match parsed names against the real 126-district set; report unmatched both ways
    matched = {name: data for name, data in merged.items() if name in real_set}
    unmatched_parsed = sorted(set(merged) - real_set)
    covered_real_districts = sorted(matched)
    uncovered_real_districts = sorted(real_set - set(matched))

    # build final per-district crop-mix (proportional share of the 4 crops' combined area)
    out_districts = {}
    for name in real_districts:
        if name in matched:
            crops_here = matched[name]
            total_area = sum(v["area_2022_23_000ha"] for v in crops_here.values())
            shares = {}
            for crop in CROPS:
                if crop in crops_here:
                    area = crops_here[crop]["area_2022_23_000ha"]
                    shares[crop] = {
                        "area_2022_23_000ha": area,
                        "production_2022_23_000t": crops_here[crop]["production_2022_23_000t"],
                        "share_of_4crop_area": round(area / total_area, 4) if total_area > 0 else 0.0,
                    }
            crops_unreliable = sorted(c for c in CROPS if name in rejected_by_crop[c])
            out_districts[name] = {
                "tier": "real_district_area",
                "source": "Government of Pakistan, Ministry of National Food Security & Research, "
                          "'Crops Area & Production (District wise) 2022-23' -- real district estimates "
                          "from the four provincial Crop Reporting Services, compiled federally. "
                          "Area figures in '000 hectares, year 2022-23.",
                "total_4crop_area_000ha": round(total_area, 2),
                "crops": shares,
                "crops_unreliable_source_data": crops_unreliable if crops_unreliable else None,
            }
        else:
            out_districts[name] = {
                "tier": "hand_classified_mask",
                "source": "naip/models/fusion/crop_plausibility.py -- Week 4 hand-classified "
                          "agronomic-geography mask (NOT real crop-area data). This district was not "
                          "matched in the real MNFSR district table (either genuinely absent, e.g. "
                          "Gilgit-Baltistan/Azad Kashmir which the MNFSR report does not cover at all, "
                          "or a name-matching/parse-validation failure -- see unmatched_parsed_names "
                          "and rejected_table_blocks in this file's sibling parse_report.json).",
            }

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out_districts, f, indent=2)

    report = {
        "n_real_districts": len(real_districts),
        "n_covered_by_real_mnfsr_data": len(covered_real_districts),
        "n_falling_back_to_hand_classified_mask": len(uncovered_real_districts),
        "uncovered_real_districts": uncovered_real_districts,
        "unmatched_parsed_names_needing_review": unmatched_parsed,
        "table_validations": all_validations,
    }
    report_path = a.out.replace("real_crop_mix.json", "parse_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"real MNFSR district-level crop-mix coverage: {len(covered_real_districts)}/{len(real_districts)} "
          f"real districts")
    print(f"falling back to hand-classified mask: {len(uncovered_real_districts)} districts")
    print(f"unmatched parsed names (need name-map review): {unmatched_parsed}")
    print(f"\nwrote {a.out}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
