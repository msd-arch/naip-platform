#!/usr/bin/env python3
"""
crop_plausibility.py -- coarse, hardcoded agronomic plausibility mask for the
4 crops in crop_calendar.py (wheat/cotton/rice/sugarcane), keyed by the 126
real district names in naip/data/seed/pk_districts.geojson.

WHY THIS EXISTS: Week 3's exposure_risk.json computes exposure hypothetically
for all 4 crops at every district (NAIP has no real per-district crop-mix
data) -- which surfaced cotton risk in Skardu, a district that would never
grow cotton. This module is the fix: a manual sanity filter so the Week 4
trigger-contract engine can never fire on a physically impossible
crop-district pairing.

THIS IS NOT REAL CROP-MIX DATA. It is standard, general knowledge of
Pakistan's agricultural geography (Punjab's cotton belt in the south, rice
belt in the centre-north, Sindh's Indus-valley cropping, KPK/Balochistan's
plains-vs-mountains split, Gilgit-Baltistan as non-arable at scale) encoded
by hand, district by district. It has NOT been checked against any real
agricultural census or remote-sensing crop-mix product -- that data doesn't
exist accessibly for this project (same root gap as Week 2/3). Treat this as
a coarse "could this crop conceivably grow here" filter, not a "this
district's actual crop mix" claim. A district being marked plausible for a
crop does NOT mean any specific farm there grows it.

Wheat is deliberately treated more permissively than the other three, per
direction: wheat is grown at least marginally across almost all of Pakistan's
inhabited plains, hills, and valleys (unlike cotton/rice/sugarcane, which
need specific irrigation/climate conditions) -- excluded only in the most
extreme high-altitude Karakoram/Himalayan terrain (Gilgit-Baltistan's glacial
valley districts), where cultivation is negligible to nonexistent.
"""

CROPS = ("wheat", "cotton", "rice", "sugarcane")

# Extreme high-altitude Karakoram/Himalayan districts (Gilgit-Baltistan) --
# excluded from ALL FOUR crops, including wheat, per the permissive-wheat rule's
# own stated exception.
NO_ARABLE_HIGH_ALTITUDE = {
    "Astore", "Diamer", "Ghanche", "Ghizer", "Gilgit", "Hunza",
    "Kharmang", "Nagar", "Shigar", "Skardu",
}

# Punjab's real cotton belt (south/central Punjab) -- standard agronomic knowledge.
COTTON_DISTRICTS = {
    "Multan", "Bahawalpur", "Bahawalnagar", "Rahim Yar Khan", "Vihari",
    "Khanewal", "Lodhran", "Muzaffargarh", "Dera Ghazi Khan", "Rajanpur",
    "Layyah", "Bhakkar", "Pakpattan", "Jhang", "Faisalabad", "Toba Tek Singh",
    "Sahiwal", "Okara", "Kasur",
    # Sindh's cotton belt
    "Sanghar", "Nawabshah", "Naushehro Feroze", "Khairpur", "Ghotki",
    "Umerkot", "Hyderabad", "Tando Allahyar", "Tando Muhammad Khan", "Matiari",
    "Badin", "Sukkur", "Jacobabad", "Kashmore",
    # Balochistan's irrigated plains ("food bowl") -- real, often-overlooked exception
    "Nasirabad", "Jafarabad", "Kachhi",
}

# Punjab/Sindh rice belt -- standard agronomic knowledge (Kallar tract, Larkana
# "rice bowl of Sindh", Indus delta paddy districts).
RICE_DISTRICTS = {
    "Gujranwala", "Sheikhpura", "Hafizabad", "Sialkot", "Narowal",
    "Mandi Bahauddin", "Kasur", "Okara", "Sahiwal",
    # Sindh
    "Larkana", "Shikarpur", "Qambar Shahdadkot", "Jacobabad", "Kashmore",
    "Dadu", "Jamshoro", "Sukkur", "Ghotki", "Thatta", "Badin",
    "Tando Muhammad Khan",
    # Balochistan plains
    "Jafarabad", "Nasirabad", "Jhal Magsi", "Lasbela", "Sibi",
}

# Punjab/Sindh/KPK sugarcane belt.
SUGARCANE_DISTRICTS = {
    "Faisalabad", "Jhang", "Toba Tek Singh", "Sargodha", "Gujranwala",
    "Sheikhpura", "Rahim Yar Khan", "Bahawalpur", "Bahawalnagar", "Vihari",
    "Khanewal",
    # Sindh
    "Hyderabad", "Tando Allahyar", "Matiari", "Badin", "Mirpurkhas",
    "Naushehro Feroze", "Nawabshah",
    # KPK Peshawar valley -- real, less commonly known sugarcane belt
    "Peshawar", "Charsadda", "Mardan", "Nowshera", "Swabi", "Bannu",
    "Dera Ismail Khan",
}


def plausible_crops(district_name):
    """Return the set of crops considered agronomically plausible for a
    district. Wheat is included everywhere except NO_ARABLE_HIGH_ALTITUDE;
    cotton/rice/sugarcane only where explicitly listed above."""
    if district_name in NO_ARABLE_HIGH_ALTITUDE:
        return set()
    crops = {"wheat"}
    if district_name in COTTON_DISTRICTS:
        crops.add("cotton")
    if district_name in RICE_DISTRICTS:
        crops.add("rice")
    if district_name in SUGARCANE_DISTRICTS:
        crops.add("sugarcane")
    return crops


def is_plausible(district_name, crop):
    return crop in plausible_crops(district_name)


if __name__ == "__main__":
    import json
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    districts_path = os.path.join(here, "..", "..", "data", "seed", "pk_districts.geojson")
    d = json.load(open(districts_path, encoding="utf-8"))
    names = sorted(f["properties"]["shapeName"] for f in d["features"])

    print(f"{len(names)} real districts checked against the mask\n")
    n_no_crops = 0
    for n in names:
        crops = plausible_crops(n)
        if not crops:
            n_no_crops += 1
        print(f"  {n:28s} {sorted(crops)}")
    print(f"\n{n_no_crops} districts with NO plausible crop (high-altitude exclusion)")
    for crop in CROPS:
        n = sum(1 for name in names if is_plausible(name, crop))
        print(f"  {crop}: plausible in {n}/{len(names)} districts")
