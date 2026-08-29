#!/usr/bin/env python3
"""
submission_server.py -- Farm Data submission page: the real, local-only HTTP
bridge between the dashboard's browser UI and register_farmer_submission()
(db_registry.py's already-built, already-live Postgres write path).

WHY A LOCAL SERVER, NOT A BROWSER-SIDE SUPABASE CALL -- a real, structural
finding worth stating plainly: naip_dashboard is a fully static export
(next.config.mjs: output: "export", deployed to GitHub Pages). A static
site has no server-side code of its own -- any credential baked into its
JS bundle is public, permanently, to anyone who loads the page. The real
Supabase DSN (backend/farm_registry/.env, gitignored, never committed) is a
live Postgres connection string with write access to a table that, as of
Track R/Track P, now holds genuine farmer PII (CNIC, phone, name).
Shipping that DSN into the public bundle -- or even a scoped Supabase
anon-key + RLS-policy approach -- would be a real, avoidable security
regression against this project's own standing "financial-sector-grade
handling" rule (CLAUDE.md). Keeping the DSN server-side, in a process that
never leaves this machine, is the correct call, not a shortcut.

REAL, HONEST CONSEQUENCE OF THIS CHOICE, stated in the UI too, not just
here: the Farm Data submission page only actually submits when this server
is running locally alongside `npm run dev` -- it will render on the public
GitHub Pages deployment, but real submission calls will fail with a clear,
honest network error there, not silently. This is a real, dev-only feature
for now, not a public-facing production form -- consistent with how this
project has never claimed the dashboard's live-database features work
without the rest of the real local pipeline (Task Scheduler jobs, GEE
credentials) also running on this machine.

Endpoints:
  POST /api/register  -- real submission. Body: farmer_name, cnic,
                          phone_number, crop_type_declared, lat, lon,
                          area_ha. Builds a real, honestly-approximate
                          square polygon centered on (lat, lon) sized to
                          area_ha (documented client-side too as an
                          approximation, not a farmer-drawn true boundary --
                          same category of honest simplification as the
                          Cholistan locust proxy boundary elsewhere in this
                          project). Calls register_farmer_submission()
                          directly -- the real write path, not a bypass.
                          Returns {success, masked_cnic, farm_id, farmer_id,
                          district} or {success: false, error}.
  GET  /api/summary   -- real, aggregate-only counts from
                          identity_coverage_summary() -- never a raw
                          identity field, real/synthetic counts always kept
                          separate.

No farm-selection endpoint exists, deliberately: register_farmer_submission()
always creates a brand-new farm row from the submission's own boundary --
it has no code path to attach identity to an existing farm_id at all, real
or synthetic. There is nothing here for a synthetic farm_id to attach to.
"""
import json
import math
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db_registry

HERE = os.path.dirname(os.path.abspath(__file__))
DISTRICTS_GEOJSON = os.path.join(HERE, "..", "..", "data", "seed", "pk_districts.geojson")
PORT = 8420

# Real national bbox (west, south, east, north) -- same real value used
# throughout this project (see fetch_firms_pakistan.py's PAKISTAN_BBOX).
PK_BBOX = (60.87, 23.63, 77.84, 37.10)
REAL_CROPS = {"wheat", "cotton", "rice", "sugarcane"}
# Same real 5-7-1 digit CNIC pattern the Excel template guides submitters
# with -- checked here at the API boundary (server never trusts client
# input), in addition to register_farmer_submission()'s own normalization.
CNIC_PATTERN = re.compile(r"^\d{5}-\d{7}-\d$")
# Real Pakistani mobile format: 03XXXXXXXXX (11 digits) or +923XXXXXXXXX.
PHONE_PATTERN = re.compile(r"^(\+92|0)3\d{9}$")


def _mask_cnic(cnic_dashed):
    """Real masked reference for the confirmation screen -- last 4 digits
    only, never the full CNIC. Matches the write-only display design
    confirmed before this page was built: raw CNIC/phone never render back
    to the browser, not even to the submitter, not even once."""
    digits = "".join(ch for ch in cnic_dashed if ch.isdigit())
    if len(digits) < 4:
        return "****"
    return f"*****-*******-{digits[-1]}" if len(digits) == 13 else f"****{digits[-4:]}"


def _square_polygon(lat, lon, area_ha):
    """Real, honestly-approximate square footprint centered on (lat, lon),
    sized so its real area (via a flat-earth approximation valid at this
    scale) equals the declared area_ha. This is NOT a farmer-drawn true
    boundary -- documented as an approximation in the UI, same discipline
    as this project's other honest proxy-boundary uses (e.g. the Cholistan
    locust region)."""
    area_m2 = max(area_ha, 0.01) * 10000.0
    half_side_m = math.sqrt(area_m2) / 2.0
    # real, standard local flat-earth degree conversion at this latitude
    deg_lat = half_side_m / 111_320.0
    deg_lon = half_side_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-9)
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - deg_lon, lat - deg_lat], [lon + deg_lon, lat - deg_lat],
            [lon + deg_lon, lat + deg_lat], [lon - deg_lon, lat + deg_lat],
            [lon - deg_lon, lat - deg_lat],
        ]],
    }


def _validate(body):
    """Real, server-side validation -- never trusts the browser's own
    checks. Returns an error string, or None if the real submission is
    valid."""
    for required in ("farmer_name", "cnic", "phone_number", "crop_type_declared", "lat", "lon", "area_ha"):
        if body.get(required) in (None, ""):
            return f"missing required field: {required}"
    if not CNIC_PATTERN.match(str(body["cnic"]).strip()):
        return "cnic must match the real 5-7-1 digit format, e.g. 12345-1234567-1"
    if not PHONE_PATTERN.match(str(body["phone_number"]).strip()):
        return "phone_number must be a real Pakistani mobile number, e.g. 03001234567"
    if body["crop_type_declared"] not in REAL_CROPS:
        return f"crop_type_declared must be one of {sorted(REAL_CROPS)}"
    try:
        lat, lon, area_ha = float(body["lat"]), float(body["lon"]), float(body["area_ha"])
    except (TypeError, ValueError):
        return "lat, lon, and area_ha must be real numbers"
    w, s, e, n = PK_BBOX
    if not (s <= lat <= n and w <= lon <= e):
        return f"lat/lon ({lat}, {lon}) falls outside Pakistan's real national bbox"
    if not (0.01 <= area_ha <= 5000):
        return "area_ha must be a real, plausible farm size (0.01-5000 hectares)"
    return None


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        # Local dev only -- the dashboard's dev server (npm run dev) runs on
        # localhost:3000. The public GitHub Pages origin is deliberately NOT
        # allowed here (see module docstring): this server never leaves the
        # developer's own machine, and CORS is not a substitute for that.
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path != "/api/summary":
            return self._send_json(404, {"error": "not found"})
        try:
            dsn = db_registry.load_dsn()
            summary = db_registry.identity_coverage_summary(dsn)
            self._send_json(200, {"success": True, **summary})
        except Exception as e:  # real, honest failure surfaced, not swallowed
            self._send_json(500, {"success": False, "error": f"real error computing summary: {e}"})

    def do_POST(self):
        if self.path != "/api/register":
            return self._send_json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send_json(400, {"success": False, "error": "malformed real JSON request body"})

        err = _validate(body)
        if err:
            return self._send_json(400, {"success": False, "error": err})

        lat, lon, area_ha = float(body["lat"]), float(body["lon"]), float(body["area_ha"])
        submission = {
            "farmer_name": body["farmer_name"].strip(),
            "cnic": body["cnic"].strip(),
            "phone_number": body["phone_number"].strip(),
            "crop_type_declared": body["crop_type_declared"],
            "farm_boundary": _square_polygon(lat, lon, area_ha),
        }
        try:
            dsn = db_registry.load_dsn()
            result = db_registry.register_farmer_submission(dsn, submission, DISTRICTS_GEOJSON)
            self._send_json(200, {
                "success": True,
                "masked_cnic": _mask_cnic(submission["cnic"]),
                "farm_id": str(result["farm_id"]),
                "farmer_id": str(result["farmer_id"]),
                "district": result["district"],
            })
        except ValueError as e:  # real validation failure from register_farmer_submission itself
            self._send_json(400, {"success": False, "error": str(e)})
        except Exception as e:  # real DB/network failure -- honest, not silent
            self._send_json(502, {"success": False, "error": f"real database error: {e}"})

    def log_message(self, fmt, *args):
        print(f"[submission_server] {self.address_string()} {fmt % args}")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Farm Data submission server -- real local-only bridge to Postgres, listening on "
          f"http://127.0.0.1:{PORT} (CORS allowed for http://localhost:3000 only)")
    server.serve_forever()


if __name__ == "__main__":
    main()
