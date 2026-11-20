# SPDX-License-Identifier: GPL-3.0-or-later
"""Drives the real Rotline window inside the Luma runtime, offline (needs a display; run with xvfb-run).

    xvfb-run flatpak run --command=python3 org.projectluma.Sdk//44 tests/test_ui.py

The license server and GitHub are local fakes. Nothing reaches Stripe: the checkout address is only recorded.
"""
import base64
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
TMP = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = os.path.join(TMP, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(TMP, "cache")
os.environ["ROTLINE_AUDIO_SINK"] = "fakesink"
os.environ["HS_UPDATES_API"] = "http://127.0.0.1:1"   # never reach GitHub from tests

STORE = {"paid": [], "polls": 0}
PRICES = {"rotline_chapter2": 199, "rotline_chapter3": 199, "rotline_arsenal": 99, "rotline_survivors": 99,
          "rotline_complete": 399}


def token(exp):
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp, "app": "rotline"}).encode()).decode().rstrip("=")
    return body + ".signature"


class License(BaseHTTPRequestHandler):
    """Answers like the Hartmann Studios license server's /v2 API for app "rotline"."""

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
                    "display": {"label": k, "amount": v, "interval": None, "consumable": False}}
                for k, v in PRICES.items()}})
        self._send(404, {"error": "Unknown app"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/v2/checkout":
            STORE["checkout"] = body
            return self._send(200, {"checkoutUrl": "https://checkout.stripe.com/c/pay/cs_test_ROT123#x"})
        if self.path == "/v2/entitlement":
            if body.get("sessionId"):
                STORE["polls"] += 1
                if STORE["polls"] < 2:
                    return self._send(200, {"entitlements": [], "pending": True})
                STORE["paid"].append(STORE["checkout"]["product"])
            return self._send(200, {"email": "qa@example.com", "entitlements": list(STORE["paid"]),
                                    "licenseToken": token(int(time.time()) + 86400), "revalidateAfter": 0})
        self._send(404, {"error": "Not found"})


SRV = ThreadingHTTPServer(("127.0.0.1", 0), License)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
os.environ["HS_BILLING_URL"] = f"http://127.0.0.1:{SRV.server_port}"

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

RESULTS = []
OPENED = []


def pump(seconds=0.3):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        ctx.iteration(False)
        time.sleep(0.004)


def wait_for(cond, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pump(0.05)
        if cond():
            return True
    return False


def texts(widget):
    out, stack = [], [widget]
    while stack:
        w = stack.pop()
        if isinstance(w, Gtk.Label):
            out.append(w.get_text())
        c = w.get_first_child()
        while c is not None:
            stack.append(c)
            c = c.get_next_sibling()
    return " | ".join(out)


def page_text(w):
    return texts(w.stack.get_visible_child())


def card_text(w):
    return texts(w.overlay_card) if isinstance(w.overlay_card, Gtk.Widget) else ""


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, None))
    except Exception:
        RESULTS.append((name, traceback.format_exc()))


def key(w, name, down=True):
    kv = Gdk.keyval_from_name(name)
    return w._key_down(None, kv, 0, 0) if down else w._key_up(None, kv, 0, 0)


def run(w):
    from rotline import game as G

    w.open_uri = w.shop.open_uri = OPENED.append

    def pages():
        w.go("campaign")
        pump(0.5)
        t = page_text(w)
        for words in ("Chapter 1: Maple Street", "Chapter 2: Downtown", "Chapter 3: The Harbor", "First Night",
                      "Continue: 1-1 First Night", "Survive 60 seconds"):
            assert words in t, (words, t)
        assert wait_for(lambda: w.shop.catalog is not None, 10), w.shop.catalog_error
        pump(0.5)
        assert "Get Chapter 2 · $1.99 once" in page_text(w), page_text(w)
        w.go("store")
        pump(0.4)
        t = page_text(w)
        assert "Get · $3.99 once" in t and "Complete pack" in t and "no coins" in t, t
        w.go("armory")
        pump(0.4)
        t = page_text(w)
        assert "0 scrap" in t and "Toughness" in t and "Found when you finish 1-1" in t and "In the Arsenal pack" in t, t
        w.go("survivors")
        pump(0.4)
        assert "Sam  ✓" in page_text(w) and "In the Survivors pack" in page_text(w)
        w.go("endless")
        pump(0.4)
        assert "Longest you've lasted" in page_text(w)

    def play_pause_and_win():
        w.start("1-1")
        pump(0.5)
        assert w.playing.key == "1-1" and not w.sidebar.get_visible()
        assert "First Night" in card_text(w) and "Survive 60 seconds." in card_text(w), card_text(w)
        w._resume()
        assert w.overlay_card is None and not w.arena.paused
        x0 = w.world.player.x
        key(w, "d")
        pump(1.0)
        key(w, "d", down=False)
        assert w.world.player.x > x0 + 1.5, (x0, w.world.player.x)
        assert w.world.time > 0.8
        assert wait_for(lambda: w.sound.src is not None and w.sound._pts > 0, 5), "no sound stream"
        n = w.sound._pts
        w.sound.play("pistol", time.monotonic() + 99)
        assert wait_for(lambda: w.sound._pts > n, 3)
        key(w, "Escape")
        pump(0.2)
        assert w.arena.paused and "Paused" in card_text(w), card_text(w)
        t = w.world.time
        pump(0.5)
        assert w.world.time == t                  # paused means paused
        key(w, "Escape")
        pump(0.3)
        assert not w.arena.paused and w.overlay_card is None
        # the HUD tracks the world
        assert "s to go" in w.goal_label.get_text() and "Pistol" in texts(w.weapon_row)
        w.world.time = 59.95
        assert wait_for(lambda: isinstance(w.overlay_card, Gtk.Widget), 5), w.overlay_card
        t = card_text(w)
        assert "Made it" in t and "You found the Shotgun" in t and "Next: Supply Run" in t, t
        assert w.progress.stars("1-1") >= 1 and "shotgun" in w.progress.weapons(False)
        assert w.progress.scrap >= 15

    def next_level_and_tv_keys():
        # "Next" from the result card
        nxt = w.overlay_card.get_last_child().get_first_child()
        nxt.emit("clicked")
        pump(0.4)
        assert w.playing.key == "1-2" and "Supply Run" in card_text(w)
        w._resume()
        # a remote or a gamepad sends whole presses (down and up at once) that repeat while held
        w.world.zombies.clear()
        w.world._spawning = lambda dt: None
        x0 = w.world.player.x
        key(w, "Right")
        key(w, "Right", down=False)
        pump(0.25)
        assert w.world.player.x > x0 + 0.4, "a tap should keep walking until the next repeat"
        pump(0.6)
        x1 = w.world.player.x
        pump(0.3)
        assert abs(w.world.player.x - x1) < 0.05, "and stop when the repeats stop"
        # OK switches weapon, numbers pick one
        assert w.world.weapons == ["pistol", "shotgun"]
        key(w, "Return")
        assert w.world.player.weapon == "shotgun"
        key(w, "1")
        assert w.world.player.weapon == "pistol"

    def losing_keeps_scrap():
        before = w.progress.scrap
        w.world.scrap = 7
        w.world.player.hp = 0
        assert wait_for(lambda: isinstance(w.overlay_card, Gtk.Widget), 5)
        t = card_text(w)
        assert "Overrun" in t and "You kept the 7 scrap" in t and "Try again" in t, t
        assert w.progress.scrap == before + 7 and not w.progress.done("1-2")
        key(w, "Escape")
        pump(0.4)
        assert w.playing is None and w.sidebar.get_visible() and w.trail.current.view == "campaign"

    def locked_chapter_and_buying_it():
        w.progress.data["levels"].update({k: {"stars": 1} for k in ("1-2", "1-3", "1-4")})
        w.start("2-1")
        pump(0.6)
        assert w.playing is None and w.trail.current.view == "store"
        assert wait_for(lambda: w.center.grown == "item-rotline_chapter2", 5), w.center.grown
        t = texts(w.shop.box)
        assert "Chapter 2: Downtown" in t and "$1.99 once" in t and "nothing renews" in t, t
        w.shop.email_field.text = "qa@example.com"
        w.shop.buy("rotline_chapter2")
        assert wait_for(lambda: OPENED, 5), "checkout never opened"
        assert OPENED[-1].startswith("https://checkout.stripe.com/"), OPENED
        assert STORE["checkout"]["product"] == "rotline_chapter2" and STORE["checkout"]["app"] == "rotline"
        assert wait_for(lambda: w.owns("rotline_chapter2"), 25), STORE
        assert not w.owns("rotline_chapter3") and not w.owns("rotline_arsenal")
        w.center.fold()
        pump(0.3)
        w.start("2-1")
        pump(0.4)
        assert w.playing is not None and w.playing.key == "2-1"
        w.back_to_levels()
        pump(0.3)

    def the_complete_pack_unlocks_all():
        STORE["paid"].append("rotline_complete")
        w.shop.restore("qa@example.com")
        assert wait_for(lambda: w.owns("rotline_arsenal"), 10)
        assert w.owns("rotline_chapter3") and w.owns("rotline_survivors")
        assert w.weapons()[-2:] == ["flamer", "crossbow"]
        w.go("survivors")
        pump(0.4)
        assert "In the Survivors pack" not in page_text(w)
        w._choose("rosa")
        assert w.progress.survivor == "rosa"
        w.go("store")
        pump(0.4)
        assert page_text(w).count("Yours") == 5, page_text(w)

    def endless_and_upgrades():
        w.start("endless", brief=False)
        pump(1.0)
        assert w.world.level.endless and "down" in w.goal_label.get_text()
        w.world.time = 75
        w.world.kills = 40
        w.world.scrap = 40
        w.world.player.hp = 0
        assert wait_for(lambda: isinstance(w.overlay_card, Gtk.Widget), 5)
        assert "You lasted 1:15" in card_text(w) and "best yet" in card_text(w), card_text(w)
        assert w.progress.endless_best()[0] >= 75
        w.go("armory")
        pump(0.3)
        assert w.playing is None
        scrap = w.progress.scrap
        assert scrap >= G.UPGRADE_COSTS[0]
        w._upgrade("health")
        assert w.progress.upgrades()["health"] == 1 and w.progress.scrap == scrap - G.UPGRADE_COSTS[0]
        w.start("1-1", brief=False)
        assert w.world.player.max_hp == 115
        w.back_to_levels()

    def settings_and_story_mode():
        w.center.grow("settings", w._settings_panel)
        pump(0.3)
        t = texts(w.center)
        assert "Story mode" in t and "Aim and fire for me" in t, t
        w.center.fold()
        w.progress.set_setting("easy", True)
        w.start("1-1", brief=False)
        w.world.hurt(20)
        assert w.world.player.hp == w.world.player.max_hp - 10
        w.back_to_levels()
        w.progress.set_setting("easy", False)

    for name, fn in (("pages", pages), ("play, pause and win", play_pause_and_win),
                     ("next level and TV keys", next_level_and_tv_keys), ("losing keeps scrap", losing_keeps_scrap),
                     ("a locked chapter, and buying it", locked_chapter_and_buying_it),
                     ("the Complete pack unlocks everything", the_complete_pack_unlocks_all),
                     ("endless and upgrades", endless_and_upgrades), ("settings and Story mode", settings_and_story_mode)):
        check(name, fn)
    check("updates", lambda: updates_flow(w))


def updates_flow(w):
    """The update panel against a LOCAL FAKE GitHub: GitHub build downloads + verifies; Depot build doesn't."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_updates as tu
    srv, _u = tu.setup("github")
    try:
        tu.STATE["tag"] = "v1.3.0"
        w.updates.channel, w.updates.state = "github", {}
        w.updater.release = None
        w.updater.check(manual=True)
        assert wait_for(lambda: w.center.grown == "updates", 15), "panel didn't open"
        text = texts(w.updater.box)
        assert "1.3.0 is available" in text and "Download and install" in text, text
        w.updater._download()
        assert wait_for(lambda: bool(w.updater.downloaded), 20), (w.updater.error, w.updater.downloading)
        assert open(w.updater.downloaded, "rb").read() == tu.BUNDLE
        w.center.fold()
        pump(0.3)
        w.updates.channel, w.updater.downloaded = "depot", ""
        w.updater.open()
        pump(0.5)
        text = texts(w.updater.box)
        assert "Depot" in text and "Download and install" not in text, text
        w.center.fold()
    finally:
        srv.shutdown()


class TestApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.charleshartmann.RotlineTest")
        self.window = None

    def do_activate(self):
        from rotline import app as A
        self.window = A.Window(self)
        self.window.present()
        pump(0.6)
        try:
            run(self.window)
        finally:
            if self.window.sound is not None:
                self.window.sound.stop()
            self.quit()


TestApp().run([])
bad = 0
for name, err in RESULTS:
    print(("ok   " if err is None else "FAIL ") + name)
    if err:
        bad += 1
        print(err)
print(f"{len(RESULTS) - bad} passed, {bad} failed")
sys.exit(1 if bad else 0)
