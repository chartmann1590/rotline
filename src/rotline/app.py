# SPDX-License-Identifier: GPL-3.0-or-later
"""Rotline: a top-down zombie survival game for Luma.

Shape: places and content, like every LumaUI app. The sidebar holds the places (Campaign, Endless, Armory,
Survivors, Store); the island holds the page. Playing a level takes the whole window: the arena, a small HUD over
it, and cards for the briefing, the pause and the result. Keyboard and mouse, touch, a TV remote and a gamepad (the
shell turns a pad into arrows, OK and Back) all play it: with no mouse, it aims and fires for you.
"""
from __future__ import annotations

import math
import os
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from luma_appkit import (  # noqa: E402
    ActionCenter, AppWindow, BarAction, Command, CommandGroup, CommandRegistry, EmptyState, Island, NavigationSidebar,
    NavigationTrail, PageHeader, PanelHeading, PanelRow, Place, RowLead, SidebarRow, SidebarToggle, TextButton,
    TitleIsland, Toast, ToastHost, icons,
)

from . import game as G, levels as L  # noqa: E402
from .hsbilling import Billing  # noqa: E402
from .hsupdates import Updates  # noqa: E402
from .progress import EARNED, SURVIVOR, SURVIVORS, Progress  # noqa: E402
from .catalog import BY_KEY as ITEM, ITEMS, PRODUCTS  # noqa: E402
from .shop import Shop  # noqa: E402
from .updates_ui import Updater  # noqa: E402

APP_ID = "com.charleshartmann.Rotline"
APP_NAME = "Rotline"
VERSION = "1.0.0"
PLACES = (("campaign", "Campaign", "map"), ("endless", "Endless", "hourglass"), ("armory", "Armory", "wrench"),
          ("survivors", "Survivors", "users"), ("store", "Store", "package"))
SHORT = {"pistol": "Pistol", "shotgun": "Shotgun", "smg": "SMG", "rifle": "Rifle", "flamer": "Flame", "crossbow": "Bow"}
TOUCH_TIP = "Drag on the left side to move. It aims and fires for you. Tap the right side to switch weapons."
PAD_TIP = "Move with the arrows or the stick. It aims and fires for you. OK switches weapons, Back pauses."
GOAL_ICON = {"survive": "hourglass", "clear": "triangle-alert", "escape": "car", "defend": "zap", "boss": "shield"}
MOVE_KEYS = {
    "left": ("a", "Left", "KP_Left"), "right": ("d", "Right", "KP_Right"),
    "up": ("w", "Up", "KP_Up"), "down": ("s", "Down", "KP_Down"),
}


def data_dir() -> str:
    return os.path.join(GLib.get_user_data_dir(), "rotline")


def cache_dir() -> str:
    return os.path.join(GLib.get_user_cache_dir(), "rotline")


def esc(text: str) -> str:
    return GLib.markup_escape_text(text or "")


def big(label: Gtk.Label, text: str, points: float, weight: int = 700, colour: str = ""):
    """Set text at an absolute size (the TV theme overrides CSS sizes; Pango attributes survive)."""
    fg = f' foreground="{colour}"' if colour else ""
    label.set_markup(f'<span size="{int(points * 1024)}" weight="{weight}"{fg}>{esc(text)}</span>')


class Window(AppWindow):
    def __init__(self, app):
        self.app_ref = app
        self.progress = Progress(os.path.join(data_dir(), "progress.json"))
        self.billing = Billing("rotline", PRODUCTS, os.path.join(data_dir(), "license.json"))
        self.sound = None
        self.arena = None
        self.world: G.World | None = None
        self.playing: L.Level | None = None
        self.overlay_card = None
        self.keys: dict[str, float | None] = {}
        self._pressed_at: dict[str, float] = {}
        self._tap_chain: dict[str, float] = {}
        self.pointer = None
        self.pointer_t = -9.0
        self.mouse_down = False
        self.fire_key = False
        self.touching = False
        self.tv = False
        self._inhibit = 0
        self._hud_t = 0
        self._card_role = ""
        self._place_rows: dict = {}
        self._thumbs: dict = {}

        commands = CommandRegistry([
            CommandGroup("Play", (
                Command("play.continue", "Continue the campaign", self.continue_campaign, icon="play",
                        shortcut=("Ctrl", "Return")),
                Command("play.endless", "Play Endless", lambda: self.start("endless"), icon="hourglass"),
            )),
            CommandGroup("Go to", tuple(
                Command(f"go.{k}", t, (lambda k=k: self.go(k)), icon=i) for k, t, i in PLACES)),
            CommandGroup("App", (
                Command("app.restore", "Restore purchases", lambda: self.shop.restore(), icon="download"),
                Command("app.updates", "Check for updates…", lambda: self.updater.open(), icon="refresh-cw"),
            )),
        ])
        super().__init__(application=app, app_id=APP_ID, title=APP_NAME, icon_name=APP_ID, commands=commands,
                         default_width=1280, default_height=800, minimum_width=360, minimum_height=294)
        self.commands_registry = commands
        self._css()

        self.sidebar = NavigationSidebar(variant="files")
        self.sidebar.list.connect("row-activated", self._row_activated)
        self.island = Island()
        self.stack = Gtk.Stack(hexpand=True, vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        from luma_appkit.lumaui import reduced_motion
        self.stack.set_transition_duration(0 if reduced_motion() else 140)
        self.island.append(self.stack)
        self.host = ToastHost(self.island)
        body = Gtk.Box()
        body.append(self.sidebar)
        main = Gtk.Box(hexpand=True)
        main.append(self.host)
        body.append(main)
        self.title_island = TitleIsland(APP_NAME, "", lead="menu")
        self.title_island.add_trailing(TitleIsland.button("play", "Continue", self.continue_campaign))
        self.title_island.add_trailing(TitleIsland.button("ellipsis", "More", self._island_more))
        self.sidebar_toggle = SidebarToggle(self.sidebar, island=self.title_island)
        self.set_leading(self.sidebar_toggle)
        self.set_body(body)
        self.title_island.float_over(body)
        self.center = ActionCenter().attach(self.host)

        self.shop = Shop(self.billing, open_uri=self.open_uri, toast=lambda t, k="done": self.toast(t, k),
                         changed=self._owned_changed)
        self.shop.listeners.append(self._prices_loaded)
        if self.billing.needs_revalidation():
            threading.Thread(target=self.billing.revalidate, daemon=True).start()
        GLib.timeout_add_seconds(2, lambda: (self.shop.load(), False)[1])
        self.updates = Updates(APP_ID, "chartmann1590/rotline", VERSION, os.path.join(data_dir(), "updates.json"),
                               os.path.join(cache_dir(), "updates"))
        self.updater = Updater(self, self.updates, APP_NAME, grow=lambda k, w: self.center.grow(k, w, wide=True),
                               fold=lambda: self.center.fold(),
                               toast=lambda t, k="done", action=None: self.toast(t, k, **({"action": action} if action else {})))
        GLib.timeout_add_seconds(8, self._updates_start)

        self.trail = NavigationTrail(Place("campaign", "Campaign"), on_change=lambda place, _d: self._show(place))
        self.tier_watch.connect("tier-changed", lambda *_: self._tiered())
        try:
            from luma_appkit.lumaui import watch_posture
            self._unwatch_tv = watch_posture(self._posture)
        except Exception:
            self._unwatch_tv = None
        self.connect("close-request", self._closing)
        self.connect("notify::is-active", self._active_changed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key_down)
        keys.connect("key-released", self._key_up)
        self.add_controller(keys)
        self.refresh_sidebar()
        self.go("campaign")
        self._tiered()

    # ================================================================ helpers
    def _css(self):
        from luma_appkit import add_style_sheet
        path = os.path.join(os.path.dirname(__file__), "rotline.css")
        if os.path.exists(path):
            add_style_sheet(path)

    def toast(self, text, kind="done", **kw):
        Toast.show(self.host, text, kind=kind, **kw)

    def open_uri(self, url: str):
        Gtk.UriLauncher.new(url).launch(self, None, None, None)

    def _updates_start(self):
        if self.playing is None:
            self.updater.start()
        else:
            GLib.timeout_add_seconds(30, self._updates_start)
        return False

    def ensure_sound(self):
        if self.sound is None:
            from .sound import Sound
            self.sound = Sound(volume=float(self.progress.setting("volume")), enabled=bool(self.progress.setting("sound")))
        return self.sound

    # ================================================================ owning things
    def owns(self, key: str) -> bool:
        return self.shop.owns(key)

    def chapter_open(self, n: int) -> bool:
        return n == L.FREE_CHAPTER or self.owns(L.CHAPTER_PRODUCTS[n])

    def weapons(self) -> list[str]:
        return self.progress.weapons(self.owns("rotline_arsenal"))

    def survivor_open(self, key: str) -> bool:
        s = SURVIVOR[key]
        return not s[6] or self.owns("rotline_survivors")

    def open_item(self, key: str):
        if self.playing is not None:
            self.leave_game()
        if self.trail.current.view != "store":
            self.go("store")
        GLib.idle_add(lambda: (self.center.grow(f"item-{key}", lambda: self.shop.panel(key), wide=True), False)[1])

    def _owned_changed(self):
        if self.playing is None:
            self._show(self.trail.current)

    def _prices_loaded(self):
        if self.playing is None and self.trail.current.view in ("store", "campaign") and self.center.grown is None:
            self._show(self.trail.current)

    # ================================================================ navigation
    def go(self, view: str, title: str | None = None, subject=None):
        if self.playing is not None:
            self.leave_game()
        names = dict((k, t) for k, t, _ in PLACES)
        self.trail.start(Place(view, title or names.get(view, view), subject))
        if self.trail.current.view == view and self.trail.current.subject == subject:
            self._show(self.trail.current)

    def _show(self, place: Place):
        builders = {"campaign": self._page_campaign, "endless": self._page_endless, "armory": self._page_armory,
                    "survivors": self._page_survivors, "store": self._page_store}
        try:
            page = builders[place.view](place)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            page = EmptyState("Couldn't show this page", str(ex), "lumaui-circle-alert-symbolic")
        self._swap(page)
        self._select_rows()
        self.show_bar()
        self.title_island.set_title(place.title, "")

    def _swap(self, page):
        old = self.stack.get_visible_child()
        self.stack.add_named(page, f"p{time.monotonic_ns()}")
        self.stack.set_visible_child(page)
        if old is not None:
            GLib.timeout_add(400, lambda: (old.get_parent() is self.stack and self.stack.remove(old), False)[1])

    def _posture(self, tv: bool):
        changed = bool(tv) != self.tv
        self.tv = bool(tv)
        if not changed:
            return
        if self.playing is not None:
            self._hud_sizes()
        elif getattr(self, "trail", None) is not None and self.stack.get_visible_child() is not None:
            self._show(self.trail.current)

    def _tiered(self):
        if self.playing is None:
            self.stack.set_margin_top(64 if self.tier == "phone" else 0)
            if getattr(self, "_last_tier", None) not in (None, self.tier):
                self._show(self.trail.current)
        self._last_tier = self.tier

    def _island_more(self):
        from luma_appkit import MenuDrawer
        MenuDrawer.present(self, self.commands_registry)

    def page(self, place: Place, content: list[Gtk.Widget], *, meta=(), wide: int = 1080):
        side = 12 if self.tier == "phone" else 22
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=side, margin_end=side,
                      margin_top=14, margin_bottom=150)
        box.append(PageHeader(self.trail, meta=list(meta)))
        for w in content:
            box.append(w)
        clamp = Adw.Clamp(maximum_size=wide, tightening_threshold=wide - 100, child=box)
        return Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True, child=clamp)

    # ================================================================ sidebar and bar
    def refresh_sidebar(self):
        self.sidebar.clear()
        self._place_rows = {}
        trail = {"campaign": f"{self.progress.total_stars()}★", "armory": f"{self.progress.scrap}"}
        for key, title, icon in PLACES:
            row = SidebarRow(title, lead=RowLead.icon(icon), trail=trail.get(key))
            row.place = key
            self._place_rows[key] = row
            self.sidebar.append_row(row)
        self._select_rows()

    def _select_rows(self):
        if not self._place_rows:
            return
        root = self.trail.places[0]
        self.sidebar.list.unselect_all()
        for key, row in self._place_rows.items():
            on = key == root.view
            row.set_state_flags(Gtk.StateFlags.CHECKED, False) if on else row.unset_state_flags(Gtk.StateFlags.CHECKED)

    def _row_activated(self, _list, row):
        if getattr(row, "place", None):
            self.go(row.place)
        if self.tier == "phone" and hasattr(self.sidebar_toggle, "set_active"):
            self.sidebar_toggle.set_active(False)

    def show_bar(self):
        if self.playing is not None:
            self.center.hide_bar()
            return
        view = self.trail.current.view
        items = []
        if view == "campaign":
            items.append(BarAction("play", "Continue", primary=True, on_activate=self.continue_campaign))
        elif view == "endless":
            items.append(BarAction("play", "Play Endless", primary=True, on_activate=lambda: self.start("endless")))
        elif view == "store":
            items.append(BarAction("download", "Restore purchases", on_activate=lambda: self.shop.restore()))
        items.append(BarAction("settings", tooltip="Settings", panel=self._settings_panel, key="settings"))
        more = [BarAction("hourglass", "Play Endless", on_activate=lambda: self.start("endless")),
                BarAction("download", "Restore purchases", on_activate=lambda: self.shop.restore()),
                BarAction("refresh-cw", "Check for updates…", on_activate=lambda: self.updater.open())]
        self.center.show_bar(items, more=more, fill=True)

    def _settings_panel(self):
        p = self.progress
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(PanelHeading("Playing"))
        box.append(PanelRow("Aim and fire for me", icon="mouse-pointer-2", toggle=bool(p.setting("auto_fire")),
                            subtitle="When you're not using a mouse",
                            on_toggle=lambda on: p.set_setting("auto_fire", on)))
        box.append(PanelRow("Story mode", icon="heart", toggle=bool(p.setting("easy")),
                            subtitle="You take half the damage",
                            on_toggle=lambda on: p.set_setting("easy", on)))
        box.append(PanelRow("Screen shake", icon="vibrate", toggle=bool(p.setting("shake")),
                            on_toggle=lambda on: p.set_setting("shake", on)))
        box.append(PanelRow("Sound effects", icon="volume-2", toggle=bool(p.setting("sound")),
                            on_toggle=self._set_sound))
        box.append(PanelHeading("Progress"))
        box.append(PanelRow("Give back upgrade scrap", icon="rotate-ccw", subtitle="Undo every upgrade and spend it again",
                            on_activate=self._reset_upgrades))
        box.append(PanelHeading("Updates"))
        box.append(PanelRow(f"Check for {APP_NAME} updates automatically", icon="download", toggle=self.updates.automatic,
                            on_toggle=self.updates.set_automatic))
        box.append(PanelRow("Check now", icon="refresh-cw", detail=VERSION, on_activate=lambda: self.updater.check(manual=True)))
        return box

    def _set_sound(self, on: bool):
        self.progress.set_setting("sound", on)
        if self.sound is not None:
            self.sound.enabled = on

    def _reset_upgrades(self):
        back = self.progress.reset_upgrades()
        self.toast(f"{back} scrap back to spend" if back else "No upgrades to undo")
        self.refresh_sidebar()
        if self.trail.current.view == "armory":
            self._show(self.trail.current)

    # ================================================================ pages
    @staticmethod
    def _heading(text: str, sub: str = "") -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=18, margin_bottom=6)
        t = Gtk.Label(label=text, xalign=0, wrap=True)
        t.add_css_class("rl-heading")
        box.append(t)
        if sub:
            s = Gtk.Label(label=sub, xalign=0, wrap=True)
            s.add_css_class("dim-label")
            box.append(s)
        return box

    @staticmethod
    def _grid(children: list[Gtk.Widget], min_width: int = 230) -> Gtk.Widget:
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, row_spacing=12, column_spacing=12,
                           min_children_per_line=1, max_children_per_line=4)
        for c in children:
            flow.append(c)
            c.get_parent().set_focusable(False)
        return flow

    def _thumb(self, lv: L.Level) -> Gdk.Texture:
        if lv.key not in self._thumbs:
            from . import render as R
            world = G.World(lv, seed=1)
            scale = 6 / R.PX
            theme = R.theme_for(lv)

            def draw(cr):
                cr.scale(scale, scale)
                R.draw_map(cr, world, theme)
            self._thumbs[lv.key] = R.texture(int(world.w * 6), int(world.h * 6), draw)
        return self._thumbs[lv.key]

    def _level_card(self, lv: L.Level) -> Gtk.Widget:
        open_ch = self.chapter_open(lv.chapter)
        unlocked = self.progress.unlocked(lv.key)
        stars = self.progress.stars(lv.key)
        btn = Gtk.Button()
        btn.add_css_class("rl-card")
        btn.add_css_class("flat")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pic = Gtk.Picture.new_for_paintable(self._thumb(lv))
        pic.set_content_fit(Gtk.ContentFit.COVER)
        pic.set_size_request(-1, 110)
        pic.add_css_class("rl-thumb")
        frame = Gtk.Overlay(child=pic)
        tag = Gtk.Label(label=lv.key, halign=Gtk.Align.START, valign=Gtk.Align.START, margin_start=8, margin_top=8)
        tag.add_css_class("rl-tag")
        frame.add_overlay(tag)
        if not open_ch or not unlocked:
            lock = icons.image("lock", pixel_size=22)
            lock.set_halign(Gtk.Align.CENTER)
            lock.set_valign(Gtk.Align.CENTER)
            lock.add_css_class("rl-lock")
            frame.add_overlay(lock)
            pic.set_opacity(0.45)
        box.append(frame)
        title = Gtk.Label(label=lv.name, xalign=0)
        title.add_css_class("rl-card-title")
        box.append(title)
        line = Gtk.Box(spacing=6)
        line.append(icons.image(GOAL_ICON[lv.goal], pixel_size=14))
        goal = Gtk.Label(label=L.goal_words(lv), xalign=0, wrap=True, hexpand=True)
        goal.add_css_class("caption")
        goal.add_css_class("dim-label")
        line.append(goal)
        box.append(line)
        st = Gtk.Label(label="★" * stars + "☆" * (3 - stars), xalign=0)
        st.add_css_class("rl-stars")
        box.append(st)
        btn.set_child(box)
        if not open_ch:
            words = f"{lv.name}: in Chapter {lv.chapter}, from the store"
            btn.connect("clicked", lambda *_: self.open_item(L.CHAPTER_PRODUCTS[lv.chapter]))
        elif not unlocked:
            words = f"{lv.name}: locked until you finish the level before"
            btn.connect("clicked", lambda *_: self.toast("Finish the level before this one first", "done"))
        else:
            words = f"Play {lv.key}, {lv.name}. {L.goal_words(lv)}. {stars} of 3 stars."
            btn.connect("clicked", lambda *_: self.start(lv.key))
        btn.update_property([Gtk.AccessibleProperty.LABEL], [words])
        btn.set_tooltip_text(lv.brief)
        return btn

    def _page_campaign(self, place):
        content = []
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6)
        hero.add_css_class("rl-hero")
        t = Gtk.Label(label="Rotline", xalign=0)
        big(t, "Rotline", 34 if self.tv else 28, 800)
        hero.append(t)
        sub = Gtk.Label(label="Hold out. Find a way out. Don't get bitten.", xalign=0, wrap=True)
        sub.add_css_class("rl-hero-sub")
        hero.append(sub)
        cur = L.BY_KEY[self.progress.current()]
        row = Gtk.Box(spacing=10, margin_top=6)
        go = TextButton(f"Continue: {cur.key} {cur.name}", icon="play", style="fill", size="large",
                        on_click=self.continue_campaign)
        go.add_css_class("rl-go")
        row.append(go)
        row.append(TextButton("Endless", icon="hourglass", style="raised", size="large", on_click=lambda: self.start("endless")))
        hero.append(row)
        content.append(hero)
        for ch in L.CHAPTERS:
            open_ch = self.chapter_open(ch.number)
            got = sum(self.progress.stars(lv.key) for lv in L.in_chapter(ch.number))
            sub = ch.blurb + (f"  ·  {got} of 12 stars" if open_ch else "")
            content.append(self._heading(f"Chapter {ch.number}: {ch.name}", sub))
            if not open_ch:
                key = L.CHAPTER_PRODUCTS[ch.number]
                price = self.shop.price(key)
                words = f"Get Chapter {ch.number}" + (f" · {price}" if price else "")
                b = TextButton(words, icon="lock-open", style="key", on_click=lambda k=key: self.open_item(k))
                b.set_halign(Gtk.Align.START)
                content.append(b)
            content.append(self._grid([self._level_card(lv) for lv in L.in_chapter(ch.number)]))
        return self.page(place, content)

    def _stat(self, value: str, label: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        box.add_css_class("rl-stat")
        v = Gtk.Label(label=value, xalign=0)
        v.add_css_class("rl-stat-value")
        box.append(v)
        lab = Gtk.Label(label=label, xalign=0)
        lab.add_css_class("dim-label")
        box.append(lab)
        return box

    def _page_endless(self, place):
        best, kills = self.progress.endless_best()
        m, s = divmod(int(best), 60)
        pic = Gtk.Picture.new_for_paintable(self._thumb(L.ENDLESS))
        pic.set_content_fit(Gtk.ContentFit.COVER)
        pic.set_size_request(-1, 220)
        pic.add_css_class("rl-thumb")
        stats = Gtk.Box(spacing=12, homogeneous=True, margin_top=12)
        stats.append(self._stat(f"{m}:{s:02d}" if best else "None yet", "Longest you've lasted"))
        stats.append(self._stat(str(kills), "Most in one go"))
        stats.append(self._stat(str(self.progress.kills()), "Put down, all time"))
        words = Gtk.Label(label="No way out and no end. They come faster and tougher the longer you last, and every few "
                                "minutes something big comes with them. Every one you put down is scrap for the Armory.",
                          xalign=0, wrap=True, margin_top=12)
        play = TextButton("Play Endless", icon="play", style="fill", size="large", on_click=lambda: self.start("endless"))
        play.set_halign(Gtk.Align.START)
        play.set_margin_top(12)
        return self.page(place, [pic, stats, words, play], wide=900)

    def _page_armory(self, place):
        p = self.progress
        content = [self._heading(f"{p.scrap} scrap", "Earned from every one you put down, and for finishing levels.")]
        ups = p.upgrades()
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for key, (name, each) in G.UPGRADES.items():
            lvl = ups[key]
            cost = G.upgrade_cost(lvl)
            row = Gtk.Box(spacing=12)
            row.add_css_class("rl-row")
            words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            t = Gtk.Label(label=name, xalign=0)
            t.add_css_class("rl-card-title")
            words.append(t)
            d = Gtk.Label(label=f"{each} a level  ·  level {lvl} of {G.MAX_UPGRADE}", xalign=0, wrap=True)
            d.add_css_class("dim-label")
            words.append(d)
            row.append(words)
            pips = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
            for k in range(G.MAX_UPGRADE):
                pip = Gtk.Box()
                pip.add_css_class("rl-pip")
                if k < lvl:
                    pip.add_css_class("on")
                pips.append(pip)
            row.append(pips)
            if cost is None:
                btn = TextButton("Maxed", style="plain", sensitive=False)
            else:
                btn = TextButton(f"Upgrade · {cost}", icon="plus", style="fill" if p.scrap >= cost else "raised",
                                 sensitive=p.scrap >= cost, on_click=lambda k=key: self._upgrade(k))
                btn.update_property([Gtk.AccessibleProperty.LABEL], [f"Upgrade {name} for {cost} scrap"])
            row.append(btn)
            rows.append(row)
        content.append(rows)
        content.append(self._heading("Weapons", "Pick them in a level with 1 to 6, Q and E, or tap them."))
        have = set(self.weapons())
        cards = []
        for w in G.ORDER:
            spec = G.WEAPONS[w]
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.add_css_class("rl-card")
            box.add_css_class("rl-weapon")
            t = Gtk.Label(label=spec.name, xalign=0)
            t.add_css_class("rl-card-title")
            box.append(t)
            dps = spec.damage * spec.pellets / spec.rate
            d = Gtk.Label(label=f"Damage {int(spec.damage)}{'×' + str(spec.pellets) if spec.pellets > 1 else ''} · "
                                f"{round(1 / spec.rate, 1)} a second · reach {int(spec.range)}"
                                + (f" · goes through {spec.pierce}" if 0 < spec.pierce < 50 else ""),
                          xalign=0, wrap=True)
            d.add_css_class("caption")
            d.add_css_class("dim-label")
            box.append(d)
            bar = Gtk.LevelBar(min_value=0, max_value=200, value=min(200, dps))
            bar.add_css_class("rl-power")
            box.append(bar)
            if w in have:
                state = "Unlimited ammo" if not spec.ammo else f"Starts with {spec.ammo} rounds"
            elif spec.extra:
                state = "In the Arsenal pack"
            else:
                lv = next(k for k, v in EARNED.items() if v == w)
                state = f"Found when you finish {lv}"
            s = Gtk.Label(label=state, xalign=0)
            s.add_css_class("rl-weapon-state")
            if w not in have:
                s.add_css_class("dim-label")
            box.append(s)
            if w not in have and spec.extra:
                b = TextButton("See the Arsenal", style="key", small=True, on_click=lambda: self.open_item("rotline_arsenal"))
                b.set_halign(Gtk.Align.START)
                box.append(b)
            cards.append(box)
        content.append(self._grid(cards))
        return self.page(place, content, wide=980)

    def _upgrade(self, key):
        if self.progress.buy_upgrade(key):
            self.ensure_sound().play("pickup", time.monotonic())
            self.toast(f"{G.UPGRADES[key][0]} upgraded")
            self.refresh_sidebar()
            self._show(self.trail.current)

    def _page_survivors(self, place):
        from . import render as R
        cards = []
        for key, name, line, *_rest, paid in SURVIVORS:
            open_ = self.survivor_open(key)
            chosen = self.progress.survivor == key
            btn = Gtk.Button()
            btn.add_css_class("rl-card")
            btn.add_css_class("flat")
            if chosen:
                btn.add_css_class("chosen")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            pic = Gtk.Picture.new_for_paintable(R.sprites().survivor(key))
            pic.set_size_request(-1, 120)
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_opacity(1 if open_ else 0.4)
            box.append(pic)
            t = Gtk.Label(label=name + ("  ✓" if chosen else ""), xalign=0)
            t.add_css_class("rl-card-title")
            box.append(t)
            d = Gtk.Label(label=line, xalign=0, wrap=True)
            d.add_css_class("caption")
            d.add_css_class("dim-label")
            box.append(d)
            if not open_:
                s = Gtk.Label(label="In the Survivors pack", xalign=0)
                s.add_css_class("rl-weapon-state")
                box.append(s)
            btn.set_child(box)
            if open_:
                btn.connect("clicked", lambda *_, k=key: self._choose(k))
                btn.update_property([Gtk.AccessibleProperty.LABEL], [f"Play as {name}" + (" (chosen)" if chosen else "")])
            else:
                btn.connect("clicked", lambda *_: self.open_item("rotline_survivors"))
                btn.update_property([Gtk.AccessibleProperty.LABEL], [f"{name}: in the Survivors pack"])
            cards.append(btn)
        words = Gtk.Label(label="Who you play as. It's only looks: everyone is as tough as everyone else.", xalign=0,
                          wrap=True)
        words.add_css_class("dim-label")
        return self.page(place, [words, self._grid(cards, 180)], wide=980)

    def _choose(self, key):
        self.progress.set_survivor(key)
        self.toast(f"Playing as {SURVIVOR[key][1]}")
        self._show(self.trail.current)

    def _page_store(self, place):
        content = []
        words = Gtk.Label(label="Everything here is a one-time purchase that's yours to keep. Chapter 1, Endless and "
                                "every upgrade are free, and scrap is only earned by playing. No ads, no coins, no "
                                "boxes of chance.", xalign=0, wrap=True)
        words.add_css_class("dim-label")
        content.append(words)
        if self.shop.catalog_error:
            note = Gtk.Label(label=self.shop.catalog_error, xalign=0, wrap=True, margin_top=8)
            note.add_css_class("rl-note")
            content.append(note)
        cards = []
        for it in ITEMS:
            owned = self.owns(it.key)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.add_css_class("rl-card")
            box.add_css_class("rl-item")
            if it.key == "rotline_complete":
                box.add_css_class("best")
            head = Gtk.Box(spacing=8)
            head.append(icons.image(it.icon, pixel_size=20))
            t = Gtk.Label(label=it.name, xalign=0, hexpand=True, wrap=True)
            t.add_css_class("rl-card-title")
            head.append(t)
            box.append(head)
            d = Gtk.Label(label=it.line, xalign=0, wrap=True)
            box.append(d)
            for line in it.details:
                li = Gtk.Label(label="• " + line, xalign=0, wrap=True)
                li.add_css_class("caption")
                li.add_css_class("dim-label")
                box.append(li)
            spacer = Gtk.Box(vexpand=True)
            box.append(spacer)
            if owned:
                b = TextButton("Yours", icon="check", style="plain", sensitive=False)
            else:
                price = self.shop.price(it.key)
                b = TextButton(f"Get · {price}" if price else "Get", style="fill" if it.key == "rotline_complete" else "key",
                               on_click=lambda k=it.key: self.open_item(k))
                if it.key == "rotline_complete":
                    b.add_css_class("rl-go")
                b.update_property([Gtk.AccessibleProperty.LABEL], [f"Get {it.name}" + (f" for {price}" if price else "")])
            b.set_halign(Gtk.Align.START)
            box.append(b)
            cards.append(box)
        content.append(self._grid(cards, 240))
        restore = TextButton("Restore purchases", icon="download", style="plain", on_click=lambda: self.shop.restore())
        restore.set_halign(Gtk.Align.START)
        restore.set_margin_top(10)
        content.append(restore)
        return self.page(place, content, wide=1080)

    # ================================================================ playing
    def continue_campaign(self):
        key = self.progress.current()
        lv = L.BY_KEY[key]
        if not self.chapter_open(lv.chapter):
            self.open_item(L.CHAPTER_PRODUCTS[lv.chapter])
            return
        self.start(key)

    def start(self, key: str, *, brief: bool = True):
        lv = L.BY_KEY[key]
        if not lv.endless and not self.chapter_open(lv.chapter):
            self.open_item(L.CHAPTER_PRODUCTS[lv.chapter])
            return
        if not self.progress.unlocked(key):
            self.toast("Finish the level before this one first")
            return
        from .render import Arena
        self.ensure_sound()
        if self.arena is not None:
            self.arena.stop()
        self.playing = lv
        self.world = G.World(lv, upgrades=self.progress.upgrades(), weapons=self.weapons(),
                             easy=bool(self.progress.setting("easy")))
        self.keys.clear()
        self.mouse_down = self.fire_key = False
        self.arena = Arena(self.world, survivor=self.progress.survivor if self.survivor_open(self.progress.survivor) else "sam",
                           inputs=self._inputs, on_event=self._world_event, shake=bool(self.progress.setting("shake")))
        self.arena.paused = True
        self._wire_arena(self.arena)
        self._close_card()
        self.game_overlay = Gtk.Overlay(child=self.arena)
        self.game_overlay.add_css_class("rl-game")
        self._build_hud()
        self.sidebar.set_visible(False)
        self.sidebar_toggle.set_visible(False)
        self.title_island.set_visible(False)
        self.center.fold()
        self.center.hide_bar()
        self.stack.set_margin_top(0)
        self._swap(self.game_overlay)
        self._keep_awake(True)
        if brief:
            self._card_brief()
        else:
            self._resume()
        self.arena.grab_focus()

    def leave_game(self):
        if self.playing is None:
            return
        w = self.world
        if w is not None and w.state == "play" and (w.time > 3 or w.kills):
            self.progress.finish(self.playing.key, won=False, stars=0, time=w.time, kills=w.kills, scrap=w.scrap)
        if self.arena is not None:
            self.arena.stop()
        self.arena = None
        self.world = None
        self.playing = None
        self.overlay_card = None
        if self._hud_t:
            GLib.source_remove(self._hud_t)
            self._hud_t = 0
        self._keep_awake(False)
        if self.is_fullscreen() and not self.tv:
            self.unfullscreen()
        self.sidebar.set_visible(True)
        self.sidebar_toggle.set_visible(True)
        self.title_island.set_visible(True)
        self.stack.set_margin_top(64 if self.tier == "phone" else 0)
        self.refresh_sidebar()

    def back_to_levels(self):
        lv = self.playing
        self.leave_game()
        self.go("endless" if lv is not None and lv.endless else "campaign")

    def _keep_awake(self, on: bool):
        app = self.get_application()
        if on and not self._inhibit and app is not None:
            self._inhibit = app.inhibit(self, Gtk.ApplicationInhibitFlags.IDLE, "Playing Rotline")
        elif not on and self._inhibit and app is not None:
            app.uninhibit(self._inhibit)
            self._inhibit = 0

    def _active_changed(self, *_):
        if not self.is_active() and self.playing is not None and self.world.state == "play" and self.overlay_card is None:
            self.pause()

    # ---------------------------------------------------------------- the HUD
    def _build_hud(self):
        o = self.game_overlay
        top = Gtk.Box(spacing=10, halign=Gtk.Align.FILL, valign=Gtk.Align.START, margin_top=12, margin_start=12, margin_end=12)
        top.add_css_class("rl-hud")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True, halign=Gtk.Align.START)
        hp_line = Gtk.Box(spacing=8)
        hp_line.append(icons.image("heart-filled", pixel_size=16))
        self.hp_bar = Gtk.LevelBar(min_value=0, max_value=1, value=1, valign=Gtk.Align.CENTER)
        self.hp_bar.add_css_class("rl-hp")
        self.hp_bar.set_size_request(180, 12)
        self.hp_bar.update_property([Gtk.AccessibleProperty.LABEL], ["Health"])
        hp_line.append(self.hp_bar)
        left.append(hp_line)
        self.goal_label = Gtk.Label(xalign=0)
        self.goal_label.add_css_class("rl-hud-text")
        left.append(self.goal_label)
        self.goal_bar = Gtk.LevelBar(min_value=0, max_value=1, value=0)
        self.goal_bar.add_css_class("rl-goal")
        self.goal_bar.set_size_request(180, 6)
        left.append(self.goal_bar)
        top.append(left)
        self.kill_label = Gtk.Label(xalign=1, valign=Gtk.Align.START)
        self.kill_label.add_css_class("rl-hud-text")
        top.append(self.kill_label)
        pause = Gtk.Button(valign=Gtk.Align.START)
        pause.set_child(icons.image("pause", pixel_size=20))
        pause.add_css_class("rl-hud-button")
        pause.set_tooltip_text("Pause (Esc)")
        pause.update_property([Gtk.AccessibleProperty.LABEL], ["Pause"])
        pause.connect("clicked", lambda *_: self.pause())
        pause.set_focusable(False)
        top.append(pause)
        o.add_overlay(top)
        self.boss_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.CENTER,
                                valign=Gtk.Align.START, margin_top=64, visible=False)
        self.boss_label = Gtk.Label()
        self.boss_label.add_css_class("rl-hud-text")
        self.boss_box.append(self.boss_label)
        self.boss_bar = Gtk.LevelBar(min_value=0, max_value=1, value=1)
        self.boss_bar.add_css_class("rl-boss")
        self.boss_bar.set_size_request(320, 10)
        self.boss_box.append(self.boss_bar)
        o.add_overlay(self.boss_box)
        self.weapon_row = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER, valign=Gtk.Align.END, margin_bottom=14)
        self.weapon_row.add_css_class("rl-weapons")
        self.weapon_buttons = {}
        for n, w in enumerate(self.world.weapons, 1):
            b = Gtk.Button()
            b.add_css_class("rl-weapon-button")
            b.set_focusable(False)
            lab = Gtk.Label()
            b.set_child(lab)
            b.connect("clicked", lambda *_, w=w: self.world and self.world.select(w))
            b.update_property([Gtk.AccessibleProperty.LABEL], [f"{G.WEAPONS[w].name} ({n})"])
            self.weapon_buttons[w] = (b, lab, n)
            self.weapon_row.append(b)
        o.add_overlay(self.weapon_row)
        self.tip_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, halign=Gtk.Align.CENTER,
                                   valign=Gtk.Align.END, margin_bottom=76, max_width_chars=60, visible=False)
        self.tip_label.add_css_class("rl-tip")
        o.add_overlay(self.tip_label)
        for wdg in (top, self.boss_box, self.weapon_row, self.tip_label):
            o.set_measure_overlay(wdg, False)
        self._hud_sizes()
        self._update_hud()
        self._hud_t = GLib.timeout_add(100, self._update_hud)

    def _hud_sizes(self):
        if not hasattr(self, "hp_bar"):
            return
        w = 300 if self.tv else 180
        self.hp_bar.set_size_request(w, 16 if self.tv else 12)
        self.goal_bar.set_size_request(w, 8 if self.tv else 6)
        self.boss_bar.set_size_request(520 if self.tv else 320, 12)

    def _update_hud(self):
        w = self.world
        if w is None:
            self._hud_t = 0
            return False
        pts = 20 if self.tv else 13 if self.tier != "phone" else 11
        p = w.player
        self.hp_bar.set_value(max(0.0, p.hp / p.max_hp))
        self.hp_bar.set_tooltip_text(f"Health {int(p.hp)} of {p.max_hp}")
        frac, words = w.progress()
        big(self.goal_label, words, pts, 700)
        self.goal_bar.set_value(frac)
        self.goal_bar.set_visible(not w.level.endless)
        big(self.kill_label, f"{w.kills} down · {w.scrap} scrap", pts, 600)
        boss = next((z for z in w.zombies if z.boss), None)
        self.boss_box.set_visible(boss is not None)
        if boss is not None:
            big(self.boss_label, "TANK", pts, 800)
            self.boss_bar.set_value(max(0.0, boss.hp / boss.max_hp))
        narrow = self.get_width() < 40 + 100 * len(self.weapon_buttons)
        wpts = 15 if self.tv else 10 if narrow else 11
        for wk, (b, lab, n) in self.weapon_buttons.items():
            spec = G.WEAPONS[wk]
            ammo = "∞" if not spec.ammo else str(p.ammo.get(wk, 0))
            if narrow:   # a phone: short names, ammo underneath
                lab.set_markup(f'<span size="{int(wpts * 1024)}"><b>{SHORT[wk]}</b>\n{ammo}</span>')
                lab.set_justify(Gtk.Justification.CENTER)
            else:
                lab.set_markup(f'<span size="{int(wpts * 1024)}"><b>{n}  {esc(spec.name)}</b>  {ammo}</span>')
            if wk == p.weapon:
                b.add_css_class("current")
            else:
                b.remove_css_class("current")
            if spec.ammo and p.ammo.get(wk, 0) <= 0:
                b.add_css_class("empty")
            else:
                b.remove_css_class("empty")
        if self.arena is not None:
            mode = self.progress.setting("touch")
            self.arena.show_stick = mode == "always" or (mode == "auto" and self.touching)
        return True

    def _tip(self, text: str, seconds: float = 6):
        if not hasattr(self, "tip_label"):
            return
        self.tip_label.set_text(text)
        self.tip_label.set_visible(bool(text))
        token = object()
        self._tip_token = token
        GLib.timeout_add(int(seconds * 1000), lambda: (getattr(self, "_tip_token", None) is token
                                                       and self.tip_label.set_visible(False), False)[1])

    # ---------------------------------------------------------------- cards over the arena
    def _card(self, title: str, lines: list[str], buttons: list[tuple], *, stars: int | None = None, kind: str = "",
              role: str = ""):
        self._close_card()
        self._card_role = role
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER,
                       valign=Gtk.Align.CENTER, margin_start=16, margin_end=16)
        card.add_css_class("rl-panel")
        if kind:
            card.add_css_class(kind)
        card.set_size_request(min(460, max(280, self.get_width() - 40)), -1)
        t = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        big(t, title, 30 if self.tv else 22, 800)
        card.append(t)
        if stars is not None:
            s = Gtk.Label()
            big(s, "★" * stars + "☆" * (3 - stars), 34 if self.tv else 26, 400, "#e0a82e")
            s.add_css_class("rl-stars")
            s.update_property([Gtk.AccessibleProperty.LABEL], [f"{stars} of 3 stars"])
            card.append(s)
        for line in lines:
            lab = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=48)
            big(lab, line, 17 if self.tv else 12, 400)
            lab.add_css_class("rl-panel-text")
            card.append(lab)
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6)
        first = None
        for label, icon, fn, style in buttons:
            b = TextButton(label, icon=icon, style=style, size="large", on_click=fn)
            b.set_hexpand(True)
            row.append(b)
            first = first or b
        card.append(row)
        self.game_overlay.add_overlay(card)
        self.overlay_card = card
        if first is not None:
            GLib.idle_add(lambda: (first.grab_focus(), False)[1])
        return card

    def _close_card(self):
        card = self.overlay_card
        if isinstance(card, Gtk.Widget) and isinstance(card.get_parent(), Gtk.Overlay):
            card.get_parent().remove_overlay(card)
        self.overlay_card = None

    def _card_brief(self):
        lv = self.playing
        lines = [lv.brief, L.goal_words(lv) + "."]
        if lv.endless:
            best, _k = self.progress.endless_best()
            if best:
                m, s = divmod(int(best), 60)
                lines.append(f"Your best: {m}:{s:02d}")
        title = lv.name if lv.endless else f"{lv.key}  {lv.name}"
        self._card(title, lines, [("Start", "play", self._resume, "fill"),
                                  ("Back", "chevron-left", self.back_to_levels, "plain")])

    def pause(self):
        if self.world is None or self.world.state != "play":
            return
        self.arena.paused = True
        self.keys.clear()
        self.mouse_down = self.fire_key = False
        frac, words = self.world.progress()
        self._card("Paused", [L.goal_words(self.playing) + ".", words],
                   [("Resume", "play", self._resume, "fill"),
                    ("Start over", "rotate-ccw", lambda: self.start(self.playing.key, brief=False), "raised"),
                    ("Full screen" if not self.is_fullscreen() else "Leave full screen", "maximize-2",
                     self._toggle_fullscreen, "plain"),
                    ("Sound: on" if self.progress.setting("sound") else "Sound: off", "volume-2", self._toggle_sound, "plain"),
                    ("Quit to the map", "map", self.back_to_levels, "plain")], role="pause")

    def _toggle_fullscreen(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()
        GLib.timeout_add(150, lambda: (self.playing is not None and self.world.state == "play" and self.pause(), False)[1])

    def _toggle_sound(self):
        self._set_sound(not self.progress.setting("sound"))
        self.pause()

    def _resume(self):
        self._close_card()
        if self.arena is None:
            return
        self.arena.paused = False
        self.arena._last = None
        self.arena.grab_focus()
        lv = self.playing
        if lv.tips and self.world.time < 1:
            tips = list(lv.tips)
            if lv.key == "1-1":
                if self.tier == "phone" or self.touching:
                    tips = [TOUCH_TIP]
                elif self.tv:
                    tips = [PAD_TIP]
            self._tip("  ".join(tips), 8)

    def _world_event(self, ev):
        kind = ev[0]
        if kind == "sound" and self.sound is not None:
            self.sound.play(ev[1], time.monotonic())
        if self.world is not None and self.world.state != "play" and self.overlay_card is None:
            GLib.timeout_add(900, self._finished)
            self.overlay_card = "ending"

    def _finished(self):
        w, lv = self.world, self.playing
        if w is None or lv is None:
            return False
        self.overlay_card = None
        won = w.state == "won"
        stars = w.stars()
        bonus = w.bonus()
        news = self.progress.finish(lv.key, won=won, stars=stars, time=w.time, kills=w.kills, scrap=w.scrap + bonus)
        self.keys.clear()
        self.mouse_down = self.fire_key = False
        m, s = divmod(int(w.time), 60)
        if lv.endless:
            lines = [w.why, f"You lasted {m}:{s:02d} and put down {w.kills}.", f"+{w.scrap} scrap"]
            if news.get("best"):
                lines.insert(1, "That's your best yet.")
            self._card("Overrun", lines, [("Again", "rotate-ccw", lambda: self.start("endless", brief=False), "fill"),
                                          ("Armory", "wrench", lambda: self.go("armory"), "raised"),
                                          ("Back", "chevron-left", self.back_to_levels, "plain")], kind="lost")
            return False
        if won:
            lines = [w.why, f"{m}:{s:02d}  ·  {w.kills} down  ·  +{w.scrap + bonus} scrap"]
            if news.get("weapon"):
                lines.append(f"You found the {G.WEAPONS[news['weapon']].name}. It's yours from now on.")
            nxt = L.next_level(lv.key)
            buttons = []
            if nxt is not None:
                if self.chapter_open(nxt.chapter):
                    buttons.append((f"Next: {nxt.name}", "play", lambda: self.start(nxt.key), "fill"))
                else:
                    item = ITEM[L.CHAPTER_PRODUCTS[nxt.chapter]]
                    price = self.shop.price(item.key)
                    lines.append(f"Chapter {nxt.chapter} picks up from here.")
                    buttons.append((f"Get {item.name}" + (f" · {price}" if price else ""), "lock-open",
                                    lambda: self.open_item(item.key), "fill"))
            else:
                lines.append("That's the end of the road. For now. Endless is always open.")
            buttons.append(("Play again", "rotate-ccw", lambda: self.start(lv.key, brief=False), "raised"))
            buttons.append(("Back to the map", "map", self.back_to_levels, "plain"))
            self._card("Made it" if lv.goal != "boss" else "It's down", lines, buttons, stars=stars, kind="won")
        else:
            lines = [w.why, f"You kept the {w.scrap} scrap you picked up."]
            if not self.progress.setting("easy"):
                lines.append("Upgrades in the Armory help, and Story mode in Settings halves the damage.")
            self._card("Overrun", lines, [("Try again", "rotate-ccw", lambda: self.start(lv.key, brief=False), "fill"),
                                          ("Armory", "wrench", lambda: self.go("armory"), "raised"),
                                          ("Back to the map", "map", self.back_to_levels, "plain")], kind="lost")
        return False

    # ---------------------------------------------------------------- input
    def _wire_arena(self, arena):
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._motion)
        motion.connect("leave", lambda *_: setattr(self, "pointer", None))
        arena.add_controller(motion)
        click = Gtk.GestureClick(button=0)
        click.connect("pressed", self._click_down)
        click.connect("released", self._click_up)
        arena.add_controller(click)
        drag = Gtk.GestureDrag(touch_only=True)
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        arena.add_controller(drag)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        scroll.connect("scroll", lambda _c, _dx, dy: (self.world and self.world.cycle(1 if dy > 0 else -1), True)[1])
        arena.add_controller(scroll)

    @staticmethod
    def _is_touch(controller) -> bool:
        dev = controller.get_current_event_device()
        return dev is not None and dev.get_source() == Gdk.InputSource.TOUCHSCREEN

    def _motion(self, controller, x, y):
        if self._is_touch(controller):
            return
        self.pointer = (x, y)
        self.pointer_t = time.monotonic()
        self.touching = False

    def _click_down(self, gesture, _n, x, y):
        if self._is_touch(gesture):
            return
        btn = gesture.get_current_button()
        if btn == 1:
            self.mouse_down = True
            self.pointer = (x, y)
            self.pointer_t = time.monotonic()
        elif btn == 3 and self.world is not None:
            self.world.cycle(1)

    def _click_up(self, gesture, _n, _x, _y):
        if gesture.get_current_button() == 1:
            self.mouse_down = False

    def _drag_begin(self, _g, x, y):
        self.touching = True
        if self.arena is None:
            return
        if x > self.arena.get_width() * 0.62 and self.world is not None:
            self.world.cycle(1)   # a tap on the right switches weapon; it aims and fires for you
            self._drag_origin = None
            return
        self._drag_origin = (x, y)
        self.arena.stick = (x, y, x, y)

    def _drag_update(self, _g, dx, dy):
        o = getattr(self, "_drag_origin", None)
        if o is None or self.arena is None:
            return
        d = math.hypot(dx, dy)
        if d > 56:
            dx, dy = dx / d * 56, dy / d * 56
        self.arena.stick = (o[0], o[1], o[0] + dx, o[1] + dy)

    def _drag_end(self, _g, _dx, _dy):
        self._drag_origin = None
        if self.arena is not None:
            self.arena.stick = None

    def _held(self, name: str, now: float) -> bool:
        for k in MOVE_KEYS[name]:
            if k in self.keys:
                exp = self.keys[k]
                if exp is None or exp > now:
                    return True
        return False

    def _inputs(self) -> G.Input:
        now = time.monotonic()
        mx = (1 if self._held("right", now) else 0) - (1 if self._held("left", now) else 0)
        my = (1 if self._held("down", now) else 0) - (1 if self._held("up", now) else 0)
        stick = self.arena.stick if self.arena is not None else None
        if stick:
            ox, oy, x, y = stick
            mx += (x - ox) / 56
            my += (y - oy) / 56
        aim = None
        mouse = self.pointer is not None and (self.mouse_down or now - self.pointer_t < 2.5)
        if mouse and self.arena is not None:
            px, py = self.arena.player_on_screen()
            aim = math.atan2(self.pointer[1] - py, self.pointer[0] - px)
        return G.Input(mx, my, aim, self.mouse_down or self.fire_key, bool(self.progress.setting("auto_fire")))

    def _keyname(self, keyval) -> str:
        name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or ""
        return name

    def _key_down(self, _c, keyval, _code, state):
        if self.playing is None:
            return False
        name = self._keyname(keyval)
        now = time.monotonic()
        playing = self.world is not None and self.world.state == "play" and not self.arena.paused
        if self.overlay_card is not None:
            if name in ("Escape", "Menu", "p", "Pause"):
                if self.overlay_card == "ending":
                    return True
                if self._card_role == "pause":
                    self._resume()
                else:
                    self.back_to_levels()
                return True
            if name != "F11":
                return False   # arrows and OK move between the card's buttons
        if name == "F11":
            self.unfullscreen() if self.is_fullscreen() else self.fullscreen()
            return True
        if not playing:
            return False
        if name in ("Escape", "p", "Menu", "Pause"):
            self.pause()
            return True
        if any(name in keys for keys in MOVE_KEYS.values()):
            if self.keys.get(name, "absent") is None:
                return True     # the keyboard's own repeat
            self.keys[name] = None
            self._pressed_at[name] = now
            return True
        if name == "space":
            self.fire_key = True
            return True
        if name in ("Return", "KP_Enter", "Tab", "e"):
            self.world.cycle(1)
            return True
        if name == "q" or name == "ISO_Left_Tab":
            self.world.cycle(-1)
            return True
        if name in ("1", "2", "3", "4", "5", "6"):
            ws = self.world.weapons
            i = int(name) - 1
            if i < len(ws):
                self.world.select(ws[i])
            return True
        return False

    def _key_up(self, _c, keyval, _code, _state):
        name = self._keyname(keyval)
        now = time.monotonic()
        if name == "space":
            self.fire_key = False
            return
        if name in self.keys:
            held = now - self._pressed_at.get(name, now)
            if held < 0.05:
                # a whole press at once: the shell's TV keys from a remote or a gamepad, which repeat while held.
                # Keep walking until the next repeat should have come.
                chained = now - self._tap_chain.get(name, -9) < 0.6
                self.keys[name] = now + (0.17 if chained else 0.42)
                self._tap_chain[name] = now
            else:
                self.keys.pop(name, None)

    # ================================================================ closing
    def _closing(self, *_):
        if self.playing is not None:
            self.leave_game()
        self._keep_awake(False)
        if self.sound is not None:
            self.sound.stop()
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        GLib.set_application_name(APP_NAME)

    def do_activate(self):
        if self.window is None:
            self.window = Window(self)
        self.window.set_visible(True)
        self.window.present()


def main() -> int:
    return App().run(sys.argv)
