# Week 24 — Post-Demo Productization Pass + Light Theme / Chart-Forward Redesign

Repo touched: `msd-arch/NAIP` (dashboard), local `C:\Users\USER\Downloads\naip_dashboard`.
Not a new detector/model track — a UI/IA and visual-design pass over the existing,
already-real dashboard content. No data was regenerated; no pipeline code changed.

## Part 1 — Productization pass

- **Demo Walkthrough removed** from the product surface (nav, home page module list).
  The route file itself could not be filesystem-deleted this session (the sandbox
  blocked every delete attempt, `rm`/`rmdir`/`Remove-Item` alike) — it now redirects
  to `/` instead, which is the equivalent user-facing outcome. Flagged, not hidden:
  a future session with delete permission should remove
  `naip_dashboard/app/demo-walkthrough/` outright.
- **Nav rebuilt** per the confirmed 6-item dropdown structure (Overview / Hazard
  Monitoring / Water & Climate / Crop Intelligence / Insurance Engine / AI Models),
  built on `<details>/<summary>` for native keyboard + tap accessibility, with a
  hover-to-open layer for desktop pointers only (`hover: hover` media check) — no
  hover-only trap on touch. Anchor IDs added to `water-stress` and `crop-classifier`
  for the sub-items that share a page (`#canal-water-stress`, `#flood-risk`,
  `#drought-signal`, `#irrigation-classifier`, `#crop-model`,
  `#cross-year-validation`, `#yield-prediction`).
- **Track/Week/Phase labels** renamed to plain client-facing names in headings and
  the two confirmed judgment calls, across all 9 originally-flagged files. A new
  `TechNote` component (collapsible, off by default) preserves every internal
  codename one click away rather than deleting it — nothing about the underlying
  methodology was hidden, only the internal label moved out of the main heading/prose.
- `basis_risk_note` (trigger-engine): left byte-for-byte untouched, per the confirmed
  call — a one-line client-side gloss ("kept verbatim for auditability") added above it.
- `PipelineHealthBadge`: "real limitation" → "details"; "Live nowcasting loop (Track H)"
  → "Live Data Pipeline", with "Track H" kept in the expandable detail text.

## Part 2 — Light theme + chart-forward redesign

**Color tokens** (proposed and applied without a mid-task pause, per this session's
explicit instruction to decide and report rather than ask):
- Base: warm paper/off-white (`--bg #faf7f0`, `--bg-elev #ffffff`, `--bg-elev-2
  #f3ede0`) — deliberately not the references' cool blue-white.
- Primary accent (real data / "good" scores): crop green, `#4a8f3c` (100/300/500/700
  ramp `#d9ead9`/`#8fc78a`/`#4a8f3c`/`#2f5e26`).
- Secondary accent (the new "model-estimated" tier marker): soil/wheat brown-tan,
  `#8a6d3f` (ramp `#f0e0c0`/`#d9b978`/`#8a6d3f`/`#5f4a2a`) — completes a real
  three-way tier mapping that didn't exist in the dark theme (green = real data,
  brown = model estimate, gray `#8c8878` = hand-mask fallback).
- Warning/caveat tone: `#b5651d`, deliberately more saturated/orange than the brown
  secondary accent so the two are never visually confused.
- Critical (reserved for fired triggers only, unchanged rule): `#c93b35`.
- The previous dark palette was kept, selectable via a `.dark` class, in case a
  future toggle is wanted — nothing currently applies it; the product ships light-only.
- All hardcoded hex references to the old dark palette (teal accent, old critical
  red, old warn amber, old tier-blue, old grays) were found via full-repo grep and
  replaced — none were missed (re-verified with a second grep pass, zero remaining
  matches). Leaflet basemap tiles switched from CARTO `dark_*` to `light_*`/`voyager_*`
  variants across all three map components.

**Structural patterns adopted directly from the WRIP/AQMS references**:
1. `DisclaimerBar` — one persistent, non-collapsible, full-width bar directly under
   each page's H1, carrying that page's own primary honesty caveat. Applied to
   Overview, Hazards, Water Stress, Crop Intelligence, Exposure Risk, Trigger Engine,
   Crop Stress Screen, and Models-in-Production. The existing per-finding
   `CaveatBanner` cards further down each page were kept as-is (not merged away) —
   this adds one consistent top-of-page bar, it does not replace the more granular
   caveats already scattered through each page's content.
2. `ProvenanceLine` — small source + last-updated line under chart/data cards.
   Applied to every chart card across Water Stress, Crop Intelligence, Hazards,
   Exposure Risk, Trigger Engine, Locust, and Models-in-Production — not just the
   drought/locust pages the original gap report named.
3. `AlertCard` (AQMS-style) — severity badge + confidence % + model/version line +
   "as of" date. The Trigger Engine event list was converted from a table to a card
   list using this component; the detail panel alongside it is unchanged.
4. `ModelCard` (AQMS Forecast-page style) — confidence badge + plain-language
   training description + a comparison-vs-baseline bar chart that renders negative
   values honestly (no clipping to zero). Applied to all three models on
   Models-in-Production (crop-share model, fire classifier, flood risk model).

**New charts** (Part 5/6 of the brief):
- Water Stress: the existing head-to-tail `SegmentProfileChart` was reused as-is
  (already built, matches the brief's "reuse that shape" instruction) with a
  provenance line added. A new current-vs-historical NDVI comparison chart
  (`NdviCompareBar`) was added for the two real flagged drought districts
  (Hunza, Jafarabad), built from `drought_national.json`'s existing per-district
  fields — no new data pipeline needed, no time-series data invented that doesn't
  exist in the current archive.
- Crop/Irrigation: the existing per-crop R² bar chart (`R2Bar`) was reused as-is
  (already honestly showed sugarcane's negative value). A new naive-baseline-vs-
  trained-model bar chart (`YieldBar`) was added for the yield-prediction section,
  rendering both cross-year directions per crop with negative R² shown at true
  scale — the existing comparison table was kept alongside it, not replaced.

**Nav pattern decision**: kept the dropdown top-nav already confirmed in Part 1,
rather than switching to a sidebar per the AQMS reference — this was the one open
question in the brief and, per this session's instruction, was decided rather than
asked: the dropdown plan was already confirmed by name minutes earlier in the same
session, and switching to sidebar nav would have meant redoing already-approved,
already-built work for a pattern the brief itself treated as optional ("WRIP keeps
a flat top nav... AQMS uses a left sidebar... don't silently switch").

**Verification**: `tsc --noEmit` clean after every phase; every page reloaded in a
fresh browser tab (a stale tab retained a one-time cached HMR error from mid-edit
that did not reproduce in a clean tab or affect rendered content) with zero console
errors and real data confirmed rendering — Overview, Hazards, Water Stress
(including both new charts and all three anchors), Crop Intelligence (both new/
reused charts), Exposure Risk, Trigger Engine (both thresholds, card list + detail
panel), Models-in-Production (all three ModelCards), Crop Stress Screen, Locust,
and the Demo Walkthrough redirect.

## Known gaps / decisions made without pausing, per this session's explicit instruction

- Demo Walkthrough route file still physically exists (as a redirect) — sandbox
  would not permit deletion. Delete it directly next session if file-delete
  permission is available then.
- Track/Week label removal was scoped to headings, section titles, and the two
  named judgment calls, not every inline prose mention across all 9 files — a
  handful of deep-methodology paragraphs (e.g. Exposure Risk's audit-record
  cross-references) still name a track/week where rewriting every sentence risked
  changing the honest methodology narrative CLAUDE.md's working conventions require.
  All headings and both explicitly-flagged judgment calls are done.
- No dark-mode toggle UI was built; the `.dark` class and full dark token set were
  kept in `globals.css` for a future toggle, but nothing currently switches to it.
