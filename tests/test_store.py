#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs the game's store against a fake Hartmann Studios license server (the same /v2 API), headless.

    GODOT=/path/to/godot python3 tests/test_store.py
    GODOT="flatpak run --command=/path/godot org.projectluma.Platform//44" python3 tests/test_store.py

Nothing reaches Stripe: the checkout address is only recorded by the game.
"""
import base64
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRICES = {"rotline_chapter2": 199, "rotline_chapter3": 199, "rotline_arsenal": 99, "rotline_survivors": 99,
          "rotline_complete": 399}
STATE = {"paid": [], "polls": 0, "checkout": {}}


def token(exp):
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp, "app": "rotline"}).encode()).decode().rstrip("=")
    return body + ".signature"


class License(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, doc):
        raw = json.dumps(doc).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/v2/catalog") and "app=rotline" in self.path:
            return self._send(200, {"app": "rotline", "products": {
                k: {"mode": "payment", "trial_days": 0, "implies": [],
                    "display": {"label": k, "amount": v, "interval": None, "consumable": False}} for k, v in PRICES.items()}})
        self._send(404, {"error": "Unknown app"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        assert body.get("app") == "rotline", body
        if self.path == "/v2/checkout":
            assert body["email"] == "qa@example.com" and body["product"] in PRICES, body
            STATE["checkout"] = body
            return self._send(200, {"checkoutUrl": "https://checkout.stripe.com/c/pay/cs_test_ROT123#x"})
        if self.path == "/v2/entitlement":
            if body.get("sessionId"):
                assert body["sessionId"] == "cs_test_ROT123", body
                STATE["polls"] += 1
                if STATE["polls"] < 2:
                    return self._send(200, {"entitlements": [], "pending": True})
                if STATE["checkout"]["product"] not in STATE["paid"]:
                    STATE["paid"].append(STATE["checkout"]["product"])
            else:
                STATE["paid"].append("rotline_complete")   # a restore on a device that bought the pack elsewhere
            return self._send(200, {"email": "qa@example.com", "entitlements": list(STATE["paid"]),
                                    "licenseToken": token(int(time.time()) + 86400), "revalidateAfter": 0})
        self._send(404, {"error": "Not found"})


def main():
    godot = shlex.split(os.environ.get("GODOT", "godot"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), License)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ, ROTLINE_TEST="store", HS_BILLING_URL=f"http://127.0.0.1:{srv.server_port}",
               HS_UPDATES_API="http://127.0.0.1:1")
    game = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "game")
    if godot[0] == "flatpak":   # pass the test's environment into the sandbox
        godot = godot[:2] + [f"--env={k}={env[k]}" for k in ("ROTLINE_TEST", "HS_BILLING_URL", "HS_UPDATES_API")] + godot[2:]
    r = subprocess.run(godot + ["--headless", "--path", game], env=env, capture_output=True, text=True, timeout=180)
    out = "\n".join(line for line in r.stdout.splitlines() if line.startswith(("ok", "FAIL", " ")) or "passed" in line)
    print(out)
    if r.returncode != 0:
        print(r.stderr[-3000:])
    srv.shutdown()
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
