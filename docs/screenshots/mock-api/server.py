"""A stub of the PulsoWeb REST API, for the documentation screenshot harness.

It answers the two calls this plugin makes, so a capture run exercises the real
client, the real parsing and the real diagnostics without a live account:

    POST <base>/get_context/   the catalogue and the station roster
    POST <base>/get_data/      one series per requested observation code

payloads/get_context.json was recorded from a real service and then
anonymised -- vendor catalogue verbatim (it is the same for every customer and
is what the guide teaches operators to read), customer station names, ids and
coordinates replaced with demo values. Recording rather than inventing is the
point: a hand-written catalogue would happily serve codes the real API does not
have, and the docs would look green while documenting a fiction.

Observations are synthesised at request time, not stored, so the newest reading
is always "now" and the freshness layer of the ingestion diagnostic is honest.

Environment: MOCK_TOKEN (the key the stub accepts, default "demo-token"),
MOCK_PORT (default 8000), SAMPLE_TZ (unused; timestamps are naive local, as the
real service returns them).
"""

import json
import math
import os
import random
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAYLOADS = Path(__file__).with_name("payloads")
CONTEXT = json.loads((PAYLOADS / "get_context.json").read_text())
TOKEN = os.environ.get("MOCK_TOKEN", "demo-token")
PORT = int(os.environ.get("MOCK_PORT", "8000"))

# A plausible curve per observation code, so charts look like weather. The unit
# of each code is the one the recorded catalogue declares.
CURVES = {
    "32000": (26.0, 6.0, 1),    # air temperature, degC
    "32008": (65.0, -20.0, 0),  # relative humidity, %
    "32015": (1012.0, 1.5, 1),  # station pressure, hPa
    "32213": (0.0, 0.0, 1),     # hourly rainfall, mm
    "32028": (2.5, 1.5, 1),     # wind speed, m/s
    "32030": (180.0, 40.0, 0),  # wind direction, degrees
}


def series(code, start, end):
    """Hourly points in [start, end], on a diurnal curve seeded by the code."""
    base, amp, digits = CURVES.get(code, (10.0, 2.0, 1))
    out = []
    moment = start.replace(minute=0, second=0, microsecond=0)
    while moment <= end:
        rng = random.Random(f"{code}-{moment:%Y%m%d%H}")
        hour = moment.hour + moment.minute / 60
        diurnal = math.sin((hour - 9) / 24 * 2 * math.pi)
        if code == "32213":                       # rain: mostly dry, showers late
            value = round(rng.choice([0, 0, 0, 0, 0.2, 0.8]) if 14 <= hour <= 17 else 0, 1)
        else:
            value = round(base + amp * diurnal + rng.uniform(-0.3, 0.3), digits)
            if code == "32030":
                value = round(value % 360)
            if code == "32008":
                value = max(0, min(100, value))
        out.append({"date": moment.strftime("%Y-%m-%dT%H:%M:%S"), "value": value})
        moment += timedelta(hours=1)
    return out


def parse(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return fallback


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send(400, {"error": "malformed JSON"})

        # The stub checks the key, so an operator's "wrong token" failure and the
        # diagnostic it produces are capturable deliberately.
        if payload.get("key") != TOKEN:
            return self.send(401, {"error": "invalid key"})

        path = self.path.rstrip("/").rsplit("/", 1)[-1]
        if path == "get_context":
            return self.send(200, CONTEXT)
        if path == "get_data":
            now = datetime.now()
            start = parse(payload.get("from"), now - timedelta(hours=6))
            end = parse(payload.get("to"), now)
            codes = [str(c) for c in payload.get("observations") or []]
            return self.send(200, {code: series(code, start, end) for code in codes})
        return self.send(404, {"error": f"no such path: {self.path}"})

    def send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        print(f"[mock-pulsoweb] {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"[mock-pulsoweb] {len(CONTEXT['stations'])} stations, "
          f"{len(CONTEXT['observations'])} observation definitions, port {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
