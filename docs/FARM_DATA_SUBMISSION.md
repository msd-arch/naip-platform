# Farm Data submission page

Real UI surface for Track R's already-built, already-live
`register_farmer_submission()` (`db_registry.py`) — proven working since
Week 29/32-33, but previously unreachable through the browser. Closes that
gap only; no changes to the real write path's own logic.

## Real, structural finding that shaped this build

`naip_dashboard` is a fully static export (`next.config.mjs`:
`output: "export"`, deployed to GitHub Pages) — it has no server-side code
of its own. The real Supabase DSN is a live Postgres connection string with
write access to a table that now holds genuine farmer PII (CNIC, phone,
name). Baking that DSN into the public JS bundle — or a browser-side
Supabase anon-key/RLS approach — would be a real security regression
against this project's own "financial-sector-grade handling" rule.

**Resolution**: a small, local-only Python HTTP server
(`naip/backend/farm_registry/submission_server.py`, stdlib `http.server`,
no new dependency) bridges the browser to `register_farmer_submission()`.
The DSN never leaves this machine. **Real, honest consequence, stated in
the page's own UI, not hidden**: the Farm Data page renders on the public
GitHub Pages deployment, but real submissions only work while this server
is running locally alongside `npm run dev` — this is a dev-only feature for
now, the same real limitation every other live-database feature in this
project already carries.

## Running it

```
cd naip/backend/farm_registry
python submission_server.py
```

Listens on `http://127.0.0.1:8420`, CORS-restricted to
`http://localhost:3000` only (the dashboard's own dev server origin).

## Two real design decisions confirmed before building, not assumed

1. **Write-only display.** The raw CNIC/phone submitted is never rendered
   back to the browser, not even to the submitter, not even once. Success
   shows a masked reference only (last CNIC digit, real `farm_id`/
   `farmer_id` UUIDs) — implemented exactly as confirmed, no deviation.
2. **Farm attachment.** `register_farmer_submission()` (both the DB and the
   original in-memory version it was migrated from) always INSERTs a
   brand-new farm row from the submission's own boundary — it has no code
   path to attach identity to one of the 120 pre-existing real seed farms,
   real or synthetic. So there is no farm-selection dropdown; the form
   collects a farm location (lat/lon, with an optional "use my current
   location" convenience) and an approximate area in hectares, and the
   server generates an honestly-approximate square footprint sized to that
   area — documented in the UI as an approximation, not a drawn true
   boundary, the same honesty standard as this project's other proxy
   boundaries (e.g. the Cholistan locust region). Because every real
   submission creates its own new, always-real
   (`is_synthetic = false`, hardcoded in the real INSERT) row, the
   synthetic-attachment risk the original task description was concerned
   about cannot occur with this code path at all — there is no synthetic
   farm_id anywhere in the API surface for a client to submit.

## Real validation, server-side (never trusts the client)

- CNIC: real 5-7-1 digit format (`12345-1234567-1`), same guidance as the
  Excel template.
- Phone: real Pakistani mobile format (`03XXXXXXXXX` / `+923XXXXXXXXX`).
- Crop: constrained to the four real known crops (wheat/cotton/rice/
  sugarcane).
- Lat/lon: must fall inside Pakistan's real national bbox
  (`60.87,23.63,77.84,37.10`, the same real bbox `fetch_firms_pakistan.py`
  uses elsewhere in this project).
- Area: real, plausible farm size bounds (0.01-5000 ha).

## Real read-only summary (`GET /api/summary`, `identity_coverage_summary()`)

Counts only, real/synthetic always kept structurally separate — never a
raw identity field, even here: `n_real_farms_with_identity`,
`n_real_farms_pending`, `n_real_farms_total`,
`n_synthetic_farms_total_for_context_only`. **Flagged, not built**: a true
admin view with raw CNIC/phone read access would need a real, separate
authentication layer first — out of scope for this pass, a real future
need if ever wanted, not assumed away silently.

## Real verification performed

1. Server smoke-tested directly (`curl`): a real test submission
   succeeded; a second submission with the same CNIC (different farm
   location) returned the same `farmer_id` — real CNIC dedup confirmed
   through the actual HTTP path, not just the underlying SQL. Server-side
   validation confirmed rejecting a malformed CNIC and an unknown crop.
2. **Verified through the actual browser UI**, not just the backend
   script: filled and submitted the real form (auto-formatting CNIC input
   live-confirmed), got a real success card with a masked CNIC and real
   UUIDs, watched the real summary counts update live (4→5 with identity,
   124→125 total, pending unchanged at 120 — confirming synthetic/real
   separation held). Confirmed client-side validation blocks an incomplete
   submission before any network call. Zero console errors throughout,
   `npx tsc --noEmit -p .` clean.
3. **All test data deleted immediately after**, same discipline as every
   prior test in this project: 3 test farm rows + 2 test farmer rows
   (CNICs `0000000000000` and `1111112223334`, both clearly named "TEST
   ENTRY DELETE ME...") removed directly from the real database, confirmed
   via a fresh `identity_coverage_summary()` call showing the real state
   restored exactly to its pre-test baseline (122 total farms, 2 with
   identity — Muhammad Saad's real Track R test record — 120 pending, 630
   synthetic).
