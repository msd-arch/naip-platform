#!/usr/bin/env python3
"""
parse_mnfsr_crop_mix_2021_22.py -- Phase 4 Track J: real 2021-22 MNFSR
district crop-mix labels for the genuine temporal-holdout cross-year test.

REAL SOURCE DECISION, checked before building (not assumed): the standalone
`cap_2021_22.pdf/.txt` document has a genuinely different, messier table
structure (4 numeric columns not 8, no percentages, severe real
text-extraction corruption -- merged multi-district rows, missing values)
that would need a real from-scratch parser with uncertain real coverage.
Checked a cheaper real alternative first: `cap_2022_23.txt` (the document
`parse_mnfsr_crop_mix.py` already parses and cross-validates) prints BOTH
the 2021-22 AND 2022-23 area/production side by side in the SAME row --
this script extracts the 2021-22 columns (index 0 area, index 4 production)
instead of the 2022-23 ones (index 2, index 6), reusing the exact same
table-detection/row-parsing/validation logic.

REAL CROSS-CHECK, done before trusting this approach (not assumed):
Attock wheat, 2021-22 -- cap_2021_22.txt (standalone doc): area 182.92,
production 310.34. cap_2022_23.txt's embedded 21-22 column: area 182.92,
production 310.34. Exact match. Punjab wheat provincial total, 2021-22 --
cap_2021_22.txt: area 6559.83, production 20031.81. cap_2022_23.txt's
embedded 21-22 total (same Total row the 22-23 parser already validates
against): area 6559.83, production 20031.81. Exact match. Two independent
real government documents agree exactly -- the embedded column is real,
trustworthy 2021-22 data, not some other value being misread.

Same real cross-validation-against-printed-totals discipline as the
original 2022-23 parser (5% tolerance, reject rather than guess on blocks
that don't reconcile) -- applied here against the REAL 2021-22 total
(the Total row's first numeric column), not the 2022-23 one.
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

# Identical to parse_mnfsr_crop_mix.py's real name map -- same source document,
# same district-name spellings, same real geoBoundaries-vintage gaps.
NAME_MAP = {
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
    "chiniot": "Jhang", "nankana sahib": "Sheikhpura", "talagang": "Chakwal",
    "wazirabad": "Gujranwala",
}
KNOWN_UNMATCHABLE = {
    "larkana", "washuk", "bolan", "harnai", "sherani", "tor ghar",
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
    """Same real per-province flush/validate logic as the 2022-23 parser --
    REAL DIFFERENCE: reads index 0 (area) / index 4 (production) -- the
    embedded 2021-22 columns -- instead of index 2/6 (2022-23), and
    validates against the Total row's own index 0 (2021-22 total), not
    index 1 (2022-23 total)."""
    blocks = extract_table_blocks(lines, TABLE_HEADER[crop])
    results = {}
    validations = []
    rejected_district_names = set()
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
                # REAL DIFFERENCE from the 2022-23 parser: index 0 is the real
                # 2021-22 total (index 1 is 2022-23, which we don't want here).
                printed_total_area = float(tot_nums[0]) if len(tot_nums) >= 1 else None
                parsed_sum_area = sum(r[1] for r in current_rows)
                val = {"crop": crop, "province": current_province, "n_rows_parsed": len(current_rows),
                       "parsed_sum_area_000ha": round(parsed_sum_area, 2),
                       "printed_total_area_2021_22_000ha": printed_total_area}
                ok = printed_total_area is not None and printed_total_area > 0 and \
                    abs(parsed_sum_area - printed_total_area) / printed_total_area <= 0.05
                if ok:
                    for name, area, prod in current_rows:
                        cell = results.setdefault(name, {}).setdefault(
                            crop, {"area_2021_22_000ha": 0.0, "production_2021_22_000t": 0.0})
                        cell["area_2021_22_000ha"] = round(cell["area_2021_22_000ha"] + area, 2)
                        cell["production_2021_22_000t"] = round(cell["production_2021_22_000t"] + prod, 2)
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
                continue
            m = re.match(r"^([A-Za-z.\s]+?)\s+-?\d+\.\d+", stripped)
            if not m:
                continue
            name = normalize_name(m.group(1))
            nums = [float(x) for x in nums[:8]]
            # REAL DIFFERENCE: nums[0]=area_2021_22, nums[4]=production_2021_22
            # (vs. nums[2]/nums[6] for 2022-23 in the original parser).
            current_rows.append((name, nums[0], nums[4]))
    return results, validations, {normalize_name(n) for n in rejected_district_names}


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--pdf-text", default=os.path.join(
        here, "..", "..", "data", "crop_mix_ground_truth", "cap_2022_23.txt"),
        help="REAL: same source file as the 2022-23 parser -- it embeds both years")
    ap.add_argument("--districts", default=os.path.join(
        here, "..", "..", "data", "seed", "pk_districts.geojson"))
    ap.add_argument("--out", default=os.path.join(
        here, "..", "..", "data", "crop_mix_ground_truth", "real_crop_mix_2021_22.json"))
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

    matched = {name: data for name, data in merged.items() if name in real_set}
    unmatched_parsed = sorted(set(merged) - real_set)
    covered_real_districts = sorted(matched)
    uncovered_real_districts = sorted(real_set - set(matched))

    out_districts = {}
    for name in real_districts:
        if name in matched:
            crops_here = matched[name]
            total_area = sum(v["area_2021_22_000ha"] for v in crops_here.values())
            shares = {}
            for crop in CROPS:
                if crop in crops_here:
                    area = crops_here[crop]["area_2021_22_000ha"]
                    shares[crop] = {
                        "area_2021_22_000ha": area,
                        "production_2021_22_000t": crops_here[crop]["production_2021_22_000t"],
                        "share_of_4crop_area": round(area / total_area, 4) if total_area > 0 else 0.0,
                    }
            crops_unreliable = sorted(c for c in CROPS if name in rejected_by_crop[c])
            out_districts[name] = {
                "tier": "real_district_area",
                "source": "Government of Pakistan, Ministry of National Food Security & Research, "
                          "'Crops Area & Production (District wise) 2022-23' publication's OWN "
                          "embedded 2021-22 comparison column -- real district estimates, year "
                          "2021-22, cross-validated against the real standalone cap_2021_22.pdf "
                          "(exact match at both district and provincial-total level, see module "
                          "docstring). Area figures in '000 hectares.",
                "total_4crop_area_000ha": round(total_area, 2),
                "crops": shares,
                "crops_unreliable_source_data": crops_unreliable if crops_unreliable else None,
            }
        else:
            out_districts[name] = {
                "tier": "hand_classified_mask",
                "source": "Not matched in the real MNFSR 2021-22 column -- same real "
                          "genuinely-absent-or-parse-failed reasons as the 2022-23 parse.",
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
    report_path = a.out.replace("real_crop_mix_2021_22.json", "parse_report_2021_22.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"real MNFSR 2021-22 district-level crop-mix coverage: {len(covered_real_districts)}/"
          f"{len(real_districts)} real districts")
    print(f"falling back to hand-classified mask: {len(uncovered_real_districts)} districts")
    print(f"unmatched parsed names (need name-map review): {unmatched_parsed}")
    print(f"\nwrote {a.out}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
