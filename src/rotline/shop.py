# SPDX-License-Identifier: GPL-3.0-or-later
"""Rotline's store: one-time unlocks paid with Stripe Checkout through the Hartmann Studios license server.

Each item is bought once and kept: two chapters, the Arsenal (two weapons), the Survivors (four characters), and
the Complete pack with all four. No coins, no loot boxes, nothing that runs out, no ads: scrap for upgrades is
only ever earned by playing.

Honest by design (Luma review 3.4 and 3.6): prices come from the store and are never written in the app; nothing
is pre-selected or counted down; the panel says, before anything is sent, that checkout is run by Stripe and
where the email goes.
"""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from luma_appkit import PanelHeading, PanelRow, TypeLabel, icons  # noqa: E402

from .catalog import BY_KEY, COMPLETE, ITEMS, Item, owns  # noqa: E402
from .hsbilling import BillingError, price_words  # noqa: E402


def _ui(fn, *args):
    GLib.idle_add(lambda: (fn(*args), False)[1], priority=GLib.PRIORITY_DEFAULT)


def _bg(work, done, fail):
    def run():
        try:
            result = work()
        except BillingError as ex:
            _ui(fail, str(ex))
            return
        except Exception as ex:
            _ui(fail, f"Something went wrong: {ex}")
            return
        _ui(done, result)
    threading.Thread(target=run, daemon=True).start()


class Shop:
    """`billing` is an hsbilling.Billing over PRODUCTS. `open_uri(url)`, `toast(text, kind)`, and `changed()` when
    what you own changes."""

    def __init__(self, billing, *, open_uri, toast, changed):
        self.billing, self.open_uri, self.toast, self.changed = billing, open_uri, toast, changed
        self.catalog: dict | None = None
        self.catalog_error = ""
        self.cancel = threading.Event()
        self.box: Gtk.Box | None = None
        self.item: Item | None = None
        self.email_field = None
        self.waiting_for = ""
        self.listeners: list = []
        billing.listeners.append(lambda: _ui(self._owned_changed))

    # ---------------------------------------------------------------- prices
    def load(self, then=None):
        """Fetch the prices (once); `then()` runs after, either way."""
        def done(cat):
            self.catalog, self.catalog_error = cat or {}, ("" if cat else "Nothing to buy right now.")
            self._fill()
            for fn in list(self.listeners):
                fn()
            if then:
                then()

        def fail(msg):
            self.catalog_error = msg
            self._fill()
            for fn in list(self.listeners):
                fn()
            if then:
                then()
        _bg(self.billing.catalog, done, fail)

    def price(self, key: str) -> str:
        if self.catalog and key in self.catalog:
            return price_words(self.catalog[key])
        return ""

    def owns(self, key: str) -> bool:
        return owns(self.billing, key)

    # ---------------------------------------------------------------- the panel for one item
    def panel(self, key: str) -> Gtk.Widget:
        self.item = BY_KEY[key]
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.box.add_css_class("hs-paywall")
        self._fill()
        if self.catalog is None:
            self.load()
        return self.box

    def _clear(self):
        child = self.box.get_first_child()
        while child is not None:
            self.box.remove(child)
            child = self.box.get_first_child()

    def _fill(self):
        if self.box is None or self.item is None:
            return
        self._clear()
        b, it = self.box, self.item
        owned = self.owns(it.key)
        b.append(PanelHeading(f"You have {it.name}" if owned else it.name))
        b.append(self._feature(it.icon, it.line, " · ".join(it.details)))
        if owned:
            word = "Thank you for supporting Hartmann Studios."
            if self.billing.email:
                word += f" It's tied to {self.billing.email}: use that to restore it on another device."
            b.append(self._words(word))
            b.append(PanelRow("Check my purchases again", icon="refresh-cw", closes=False, on_activate=lambda: self.restore()))
            return
        if self.waiting_for:
            row = Gtk.Box(spacing=10, margin_top=8, margin_bottom=8, margin_start=6)
            row.append(Gtk.Spinner(spinning=True))
            row.append(self._words("Finish paying in your browser. This unlocks by itself as soon as Stripe confirms it."))
            b.append(row)
            b.append(PanelRow("Cancel", icon="x", closes=False, on_activate=self._stop_waiting))
            return
        from luma_appkit import TextField
        self.email_field = TextField("Email for your receipt", value=self.billing.email, placeholder="you@example.com",
                                     purpose="email", size="panel")
        if self.catalog is None and not self.catalog_error:
            b.append(Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER, margin_top=10, margin_bottom=10))
        elif self.catalog_error or it.key not in (self.catalog or {}):
            b.append(self._words(self.catalog_error or "This isn't for sale yet."))
            b.append(PanelRow("Try again", icon="refresh-cw", closes=False, on_activate=self._retry))
        else:
            p = self.catalog[it.key]
            words = price_words(p) + " · once, yours to keep"
            if p.get("promo_codes"):
                words += " · codes accepted"
            b.append(self.email_field)
            b.append(PanelRow(f"Buy {it.name}", icon="credit-card", subtitle=words, closes=False,
                              on_activate=lambda: self.buy(it.key)))
            if it.key != COMPLETE and not self.owns(COMPLETE) and COMPLETE in self.catalog:
                b.append(self._words(f"Or get the Complete pack ({price_words(self.catalog[COMPLETE])}): both chapters, "
                                     "the Arsenal and the Survivors."))
            note = ("Checkout opens in your browser and is run by Stripe. Your email goes to the Hartmann Studios "
                    "license server and to Stripe, for your receipt and to restore your purchase. It's a one-time "
                    "payment: nothing renews.")
            if p.get("promo_codes"):
                note += " Have a promotion code? Enter it on Stripe's checkout page, under the price."
            b.append(self._words(note))
        b.append(PanelRow("Restore purchases", icon="download", closes=False, on_activate=lambda: self.restore()))

    @staticmethod
    def _feature(icon: str, title: str, detail: str) -> Gtk.Widget:
        row = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        img = icons.image(icon, pixel_size=18)
        img.set_valign(Gtk.Align.START)
        row.append(img)
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        t = Gtk.Label(label=title, xalign=0, wrap=True)
        t.add_css_class("hs-feature-title")
        words.append(t)
        d = Gtk.Label(label=detail, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        d.add_css_class("dim-label")
        d.add_css_class("caption")
        words.append(d)
        row.append(words)
        row.update_property([Gtk.AccessibleProperty.LABEL], [f"{title}: {detail}"])
        return row

    @staticmethod
    def _words(text: str) -> Gtk.Widget:
        t = TypeLabel(text, role="caption", wrap=True)
        for side in ("start", "end"):
            getattr(t, f"set_margin_{side}")(6)
        t.set_margin_top(6)
        t.set_margin_bottom(4)
        return t

    # ---------------------------------------------------------------- actions
    def _retry(self):
        self.catalog, self.catalog_error = None, ""
        self._fill()
        self.load()

    def buy(self, key: str):
        email = self.email_field.text if self.email_field is not None else self.billing.email

        def opened(result):
            url, session = result
            self.open_uri(url)
            if not session:
                self.toast("Finish paying in your browser, then use Restore purchases.", "opening")
                return
            self.waiting_for = session
            self.cancel = threading.Event()
            self._fill()
            cancel = self.cancel
            _bg(lambda: self.billing.wait_for_session(session, cancel), self._waited, self._wait_failed)

        _bg(lambda: self.billing.checkout(key, email), opened, lambda m: self.toast(m, "error"))

    def _waited(self, ok: bool):
        self.waiting_for = ""
        name = self.item.name if self.item else "Your purchase"
        if ok:
            self.toast(f"{name} is unlocked. Thank you!", "done")
        elif not self.cancel.is_set():
            self.toast("Still waiting on the payment. If you paid, use Restore purchases in a minute.", "warning")
        self._fill()

    def _wait_failed(self, msg: str):
        self.waiting_for = ""
        self.toast(msg, "error")
        self._fill()

    def _stop_waiting(self):
        self.cancel.set()
        self.waiting_for = ""
        self._fill()

    def restore(self, email: str = ""):
        email = email or (self.email_field.text if self.email_field is not None and self.email_field.text else "") \
            or self.billing.email

        def done(_owned):
            have = [i.name for i in ITEMS if self.owns(i.key)]
            if have:
                self.toast("Restored: " + ", ".join(have) + ". Thank you!", "done")
            else:
                self.toast(f"No purchases found for {email}.", "warning")
            self._fill()
        _bg(lambda: self.billing.restore(email), done, lambda m: self.toast(m, "error"))

    def _owned_changed(self):
        self._fill()
        self.changed()
