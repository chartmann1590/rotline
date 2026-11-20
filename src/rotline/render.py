# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing Rotline: every picture is painted once with cairo into a GPU texture (the map, the survivors, the dead,
pickups), and each frame only places textures with a GtkSnapshot, so it stays smooth on a phone and on a TV.

`Arena` is the game's widget. It owns the world, runs it from the frame clock, keeps the effects that are only for
looking at (blood, sparks, corpses, the camera shake) and turns the world's events into sounds.
"""
from __future__ import annotations

import math
import random

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

from . import game as G  # noqa: E402
from .progress import SURVIVOR  # noqa: E402

PX = 48           # map texture pixels a tile
CH = 1.4          # people are drawn a bit bigger than they are, so they read at a glance
SP = 96           # sprite texture pixels a tile


def rgb(hexstr: str, a: float = 1.0) -> tuple[float, float, float, float]:
    h = hexstr.lstrip("#")
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a


def rgba(hexstr: str, a: float = 1.0) -> Gdk.RGBA:
    r, g, b, a = rgb(hexstr, a)
    return Gdk.RGBA(red=r, green=g, blue=b, alpha=a)


def texture(w: int, h: int, draw) -> Gdk.Texture:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, w), max(1, h))
    cr = cairo.Context(surf)
    draw(cr)
    surf.flush()
    data = GLib.Bytes.new(bytes(surf.get_data()))
    return Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, data, surf.get_stride())


def _circle(cr, x, y, r):
    cr.new_sub_path()
    cr.arc(x, y, r, 0, 2 * math.pi)


def _rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


# ------------------------------------------------------------------------------------------------ themes
THEMES = {
    "suburb": dict(ground="#4d6b3c", ground2="#567642", road="#3c3e42", floor="#8a6a4c", floor2="#7d5f43",
                   wall="#6e4b3b", wall_top="#8a5f4a", water="#24506b", crate="#8b6a3e", dark=0.6,
                   tint=(0.95, 0.55, 0.25, 0.08)),
    "downtown": dict(ground="#6a6b69", ground2="#626361", road="#2c2e31", floor="#8d9196", floor2="#7f8388",
                     wall="#353a45", wall_top="#474d5a", water="#1d3a4f", crate="#7a6a50", dark=0.86,
                     tint=(0.2, 0.3, 0.6, 0.12)),
    "harbor": dict(ground="#596064", ground2="#535a5e", road="#34373a", floor="#6a675f", floor2="#625f58",
                   wall="#46576a", wall_top="#56697e", water="#1b3c52", crate="#9a4a32", dark=0.7,
                   tint=(0.75, 0.8, 0.85, 0.14)),
    "endless": dict(ground="#4a5a3e", ground2="#526444", road="#38393c", floor="#7a6a55", floor2="#6f604c",
                    wall="#4c4a52", wall_top="#5e5b66", water="#22445a", crate="#7d6440", dark=0.75,
                    tint=(0.6, 0.15, 0.1, 0.08)),
}
CAR_COLOURS = ("#9b2d2d", "#2d5a9b", "#c9c2b0", "#2f2f33", "#4f7d4a", "#b88a2a", "#6b6f78")


def theme_for(level) -> dict:
    if level.endless:
        return THEMES["endless"]
    return THEMES[("suburb", "downtown", "harbor")[level.chapter - 1]]


def draw_map(cr, world, theme) -> None:
    rng = random.Random(world.level.key)
    g = world.grid
    W, H = world.w, world.h

    def fill(hexstr, x, y, w=1, h=1, a=1.0):
        cr.set_source_rgba(*rgb(hexstr, a))
        cr.rectangle(x * PX, y * PX, w * PX, h * PX)
        cr.fill()

    # the ground
    for j in range(H):
        for i in range(W):
            ch = g[j][i]
            base = {",": theme["road"], "=": theme["floor"], "~": theme["water"]}.get(ch, theme["ground"])
            fill(base, i, j)
            if ch in ".tcxfG":
                for _ in range(5):
                    cr.set_source_rgba(*rgb(theme["ground2"], 0.8))
                    cr.rectangle(i * PX + rng.random() * PX, j * PX + rng.random() * PX, 3 + rng.random() * 5, 2 + rng.random() * 3)
                    cr.fill()
            elif ch == ",":
                for _ in range(3):
                    cr.set_source_rgba(1, 1, 1, 0.03)
                    _circle(cr, i * PX + rng.random() * PX, j * PX + rng.random() * PX, 1 + rng.random() * 3)
                    cr.fill()
                if (i + j) % 7 == 0 and rng.random() < 0.6:
                    cr.set_source_rgba(0.9, 0.8, 0.3, 0.5)
                    cr.rectangle(i * PX + PX * 0.3, j * PX + PX * 0.46, PX * 0.4, PX * 0.08)
                    cr.fill()
            elif ch == "=":
                cr.set_source_rgba(*rgb(theme["floor2"]))
                cr.set_line_width(1.5)
                for k in range(1, 4):
                    cr.move_to(i * PX, j * PX + k * PX / 4)
                    cr.line_to(i * PX + PX, j * PX + k * PX / 4)
                cr.stroke()
            elif ch == "~":
                cr.set_source_rgba(1, 1, 1, 0.07)
                cr.set_line_width(2)
                for k in range(2):
                    y = j * PX + PX * (0.3 + 0.4 * k) + rng.uniform(-3, 3)
                    cr.move_to(i * PX + 6, y)
                    cr.curve_to(i * PX + PX * 0.35, y - 4, i * PX + PX * 0.65, y + 4, i * PX + PX - 6, y)
                cr.stroke()
    # shadows from walls, then the walls
    cr.set_source_rgba(0, 0, 0, 0.32)
    for j in range(H):
        for i in range(W):
            if g[j][i] == "#":
                cr.rectangle(i * PX + PX * 0.18, j * PX + PX * 0.22, PX, PX)
    cr.fill()
    for j in range(H):
        for i in range(W):
            if g[j][i] != "#":
                continue
            fill(theme["wall"], i, j)
            # a lighter top edge where the wall meets open ground above
            if j > 0 and g[j - 1][i] != "#":
                fill(theme["wall_top"], i, j, 1, 0.18)
            if i > 0 and g[j][i - 1] != "#":
                fill(theme["wall_top"], i, j, 0.12, 1)
            if rng.random() < 0.08:
                cr.set_source_rgba(0, 0, 0, 0.18)
                cr.rectangle(i * PX + PX * 0.25, j * PX + PX * 0.25, PX * 0.5, PX * 0.5)
                cr.fill()
    # things
    for j in range(H):
        for i in range(W):
            ch = g[j][i]
            x, y = i * PX, j * PX
            if ch == "c":
                col = rng.choice(CAR_COLOURS)
                horiz = (i > 0 and g[j][i - 1] in ",.") and (i + 1 < W and g[j][i + 1] in ",.")
                cr.save()
                cr.translate(x + PX / 2, y + PX / 2)
                if not horiz:
                    cr.rotate(math.pi / 2)
                cr.rotate(rng.uniform(-0.25, 0.25))
                cr.set_source_rgba(0, 0, 0, 0.35)
                _rrect(cr, -PX * 0.62 + 4, -PX * 0.36 + 5, PX * 1.24, PX * 0.72, 9)
                cr.fill()
                cr.set_source_rgba(*rgb(col))
                _rrect(cr, -PX * 0.62, -PX * 0.36, PX * 1.24, PX * 0.72, 9)
                cr.fill()
                cr.set_source_rgba(0.12, 0.16, 0.2, 0.9)
                _rrect(cr, PX * 0.12, -PX * 0.28, PX * 0.22, PX * 0.56, 4)
                cr.fill()
                _rrect(cr, -PX * 0.46, -PX * 0.26, PX * 0.16, PX * 0.52, 4)
                cr.fill()
                cr.set_source_rgba(1, 1, 1, 0.12)
                _rrect(cr, -PX * 0.25, -PX * 0.3, PX * 0.34, PX * 0.6, 5)
                cr.fill()
                cr.restore()
            elif ch == "t":
                cr.set_source_rgba(0, 0, 0, 0.3)
                _circle(cr, x + PX * 0.62, y + PX * 0.62, PX * 0.55)
                cr.fill()
                for r, a, col in ((0.55, 1, "#2f4f25"), (0.42, 1, "#3c6330"), (0.25, 1, "#4b7a3c")):
                    cr.set_source_rgba(*rgb(col, a))
                    _circle(cr, x + PX * 0.5 + rng.uniform(-2, 2), y + PX * 0.5 + rng.uniform(-2, 2), PX * r)
                    cr.fill()
            elif ch == "x":
                harbor = theme is THEMES["harbor"]
                col = rng.choice(("#9a4a32", "#2f6b8a", "#7b8a3a", "#b58a2a")) if harbor else theme["crate"]
                cr.set_source_rgba(0, 0, 0, 0.3)
                cr.rectangle(x + 6, y + 7, PX - 4, PX - 4)
                cr.fill()
                cr.set_source_rgba(*rgb(col))
                cr.rectangle(x + 2, y + 2, PX - 4, PX - 4)
                cr.fill()
                cr.set_source_rgba(0, 0, 0, 0.25)
                cr.set_line_width(2.5)
                if harbor:
                    for k in range(1, 5):
                        cr.move_to(x + 2 + k * (PX - 4) / 5, y + 4)
                        cr.line_to(x + 2 + k * (PX - 4) / 5, y + PX - 4)
                else:
                    cr.rectangle(x + 5, y + 5, PX - 10, PX - 10)
                    cr.move_to(x + 5, y + 5)
                    cr.line_to(x + PX - 5, y + PX - 5)
                    cr.move_to(x + PX - 5, y + 5)
                    cr.line_to(x + 5, y + PX - 5)
                cr.stroke()
            elif ch == "f":
                cr.set_source_rgba(0.75, 0.77, 0.8, 0.55)
                cr.set_line_width(1.2)
                for k in range(0, PX + 1, 8):
                    cr.move_to(x + k, y)
                    cr.line_to(x + PX - k, y + PX)
                cr.stroke()
                cr.set_source_rgba(0.55, 0.57, 0.6, 1)
                cr.set_line_width(3)
                cr.rectangle(x + 1.5, y + 1.5, PX - 3, PX - 3)
                cr.stroke()


# ------------------------------------------------------------------------------------------------ sprites
def survivor_sprite(cr, jacket, skin, hair):
    c = SP / 2
    cr.translate(c, c)
    cr.set_source_rgba(0, 0, 0, 0.3)
    _circle(cr, 3, 4, SP * 0.3)
    cr.fill()
    # arms forward, to the gun
    cr.set_source_rgba(*rgb(jacket))
    cr.set_line_width(SP * 0.1)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(-SP * 0.02, -SP * 0.2)
    cr.line_to(SP * 0.26, -SP * 0.04)
    cr.move_to(-SP * 0.02, SP * 0.2)
    cr.line_to(SP * 0.26, SP * 0.04)
    cr.stroke()
    cr.set_source_rgba(*rgb(skin))
    _circle(cr, SP * 0.27, 0, SP * 0.06)
    cr.fill()
    # shoulders
    cr.set_source_rgba(*rgb(jacket))
    cr.save()
    cr.scale(0.62, 1)
    _circle(cr, 0, 0, SP * 0.27)
    cr.restore()
    cr.fill()
    cr.set_source_rgba(0, 0, 0, 0.18)
    cr.save()
    cr.scale(0.62, 1)
    cr.set_line_width(3)
    _circle(cr, 0, 0, SP * 0.27)
    cr.restore()
    cr.stroke()
    # head
    cr.set_source_rgba(*rgb(skin))
    _circle(cr, SP * 0.02, 0, SP * 0.14)
    cr.fill()
    cr.set_source_rgba(*rgb(hair))
    cr.arc(SP * 0.0, 0, SP * 0.14, math.pi * 0.55, math.pi * 1.45)
    cr.close_path()
    cr.fill()


def gun_sprite(cr, weapon):
    c = SP / 2
    cr.translate(c, c)
    length, width, col = {"pistol": (0.2, 0.06, "#2a2a2a"), "shotgun": (0.44, 0.075, "#4a3222"),
                          "smg": (0.32, 0.08, "#1e1e1e"), "rifle": (0.5, 0.06, "#3a3a2a"),
                          "flamer": (0.42, 0.11, "#b23a1c"), "crossbow": (0.36, 0.06, "#6b4a2a")}[weapon]
    cr.set_source_rgba(*rgb(col))
    cr.rectangle(SP * 0.22, -SP * width / 2, SP * length, SP * width)
    cr.fill()
    if weapon == "crossbow":
        cr.set_line_width(3)
        cr.move_to(SP * 0.44, -SP * 0.16)
        cr.curve_to(SP * 0.5, -SP * 0.05, SP * 0.5, SP * 0.05, SP * 0.44, SP * 0.16)
        cr.stroke()
    if weapon == "flamer":
        cr.set_source_rgba(0.95, 0.6, 0.1, 1)
        _circle(cr, SP * (0.22 + length), 0, SP * 0.035)
        cr.fill()


ZOMBIE_LOOK = {
    # shirt, skin, scale
    "walker": ("#5a4e66", "#8fa37a", 1.0),
    "runner": ("#8a2f2f", "#9fb08a", 0.9),
    "brute": ("#3b3b3b", "#728a62", 1.45),
    "spitter": ("#4b6b3a", "#a6b85a", 1.0),
    "bloater": ("#8a8a4a", "#b5bb6a", 1.3),
    "tank": ("#4a3a32", "#6b7d58", 2.2),
}


def zombie_sprite(cr, kind, flash=False):
    shirt, skin, scale = ZOMBIE_LOOK[kind]
    cr.translate(SP * 1.25, SP * 1.25)   # sprites are 2.5 tiles across, for the big ones
    cr.scale(scale, scale)
    if flash:
        shirt = skin = "#ffffff"
    else:
        cr.set_source_rgba(0, 0, 0, 0.3)
        _circle(cr, 3, 4, SP * 0.3)
        cr.fill()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    # arms reaching
    cr.set_source_rgba(*rgb(skin))
    cr.set_line_width(SP * 0.09)
    cr.move_to(0, -SP * 0.2)
    cr.line_to(SP * 0.36, -SP * 0.16)
    cr.move_to(0, SP * 0.2)
    cr.line_to(SP * 0.34, SP * 0.2)
    cr.stroke()
    # body
    cr.set_source_rgba(*rgb(shirt))
    cr.save()
    cr.scale(0.65 if kind != "bloater" else 0.95, 1)
    _circle(cr, 0, 0, SP * 0.27)
    cr.restore()
    cr.fill()
    if not flash:
        # tears and stains
        cr.set_source_rgba(0.35, 0.05, 0.05, 0.55)
        _circle(cr, -SP * 0.05, SP * 0.1, SP * 0.06)
        cr.fill()
        if kind == "spitter":
            cr.set_source_rgba(0.6, 0.85, 0.2, 0.8)
            _circle(cr, SP * 0.12, 0, SP * 0.05)
            cr.fill()
        if kind == "bloater":
            cr.set_source_rgba(0.75, 0.8, 0.35, 0.8)
            for a, b in ((-0.1, -0.12), (0.06, 0.14), (-0.14, 0.08)):
                _circle(cr, SP * a, SP * b, SP * 0.05)
                cr.fill()
    cr.set_source_rgba(*rgb(skin))
    _circle(cr, SP * 0.04, 0, SP * 0.13)
    cr.fill()
    if not flash:
        cr.set_source_rgba(0.9, 0.1, 0.05, 0.9)
        _circle(cr, SP * 0.13, -SP * 0.05, SP * 0.022)
        _circle(cr, SP * 0.13, SP * 0.05, SP * 0.022)
        cr.fill()


def pickup_sprite(cr, kind):
    c = SP / 2
    cr.translate(c, c)
    cr.set_source_rgba(0, 0, 0, 0.3)
    _rrect(cr, -SP * 0.2 + 3, -SP * 0.16 + 4, SP * 0.4, SP * 0.32, 5)
    cr.fill()
    if kind == "medkit":
        cr.set_source_rgba(0.95, 0.95, 0.95, 1)
        _rrect(cr, -SP * 0.2, -SP * 0.16, SP * 0.4, SP * 0.32, 5)
        cr.fill()
        cr.set_source_rgba(0.85, 0.1, 0.1, 1)
        cr.rectangle(-SP * 0.04, -SP * 0.12, SP * 0.08, SP * 0.24)
        cr.rectangle(-SP * 0.12, -SP * 0.04, SP * 0.24, SP * 0.08)
        cr.fill()
    elif kind == "ammo":
        cr.set_source_rgba(*rgb("#5a6b2f"))
        _rrect(cr, -SP * 0.2, -SP * 0.16, SP * 0.4, SP * 0.32, 4)
        cr.fill()
        cr.set_source_rgba(0.9, 0.75, 0.25, 1)
        for k in range(4):
            cr.rectangle(-SP * 0.14 + k * SP * 0.075, -SP * 0.1, SP * 0.045, SP * 0.2)
        cr.fill()
    elif kind == "fuel":
        cr.set_source_rgba(*rgb("#c42a1c"))
        _rrect(cr, -SP * 0.17, -SP * 0.2, SP * 0.34, SP * 0.4, 5)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.set_line_width(3)
        cr.move_to(-SP * 0.12, -SP * 0.12)
        cr.line_to(SP * 0.12, SP * 0.12)
        cr.move_to(SP * 0.12, -SP * 0.12)
        cr.line_to(-SP * 0.12, SP * 0.12)
        cr.stroke()
        cr.set_source_rgba(0.85, 0.75, 0.2, 1)
        cr.rectangle(SP * 0.06, -SP * 0.27, SP * 0.08, SP * 0.08)
        cr.fill()


def generator_sprite(cr):
    cr.set_source_rgba(0, 0, 0, 0.35)
    _rrect(cr, 6, 8, SP - 6, SP - 6, 8)
    cr.fill()
    cr.set_source_rgba(*rgb("#c9a227"))
    _rrect(cr, 4, 4, SP - 8, SP - 8, 8)
    cr.fill()
    cr.set_source_rgba(0.15, 0.15, 0.15, 1)
    cr.rectangle(SP * 0.2, SP * 0.25, SP * 0.6, SP * 0.18)
    cr.fill()
    cr.set_source_rgba(0.2, 0.2, 0.2, 1)
    for k in range(4):
        cr.rectangle(SP * 0.22 + k * SP * 0.15, SP * 0.55, SP * 0.08, SP * 0.25)
    cr.fill()


def soft_dot(cr, size, col, hard=0.0):
    r, g, b, a = col
    grad = cairo.RadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    grad.add_color_stop_rgba(0, r, g, b, a)
    grad.add_color_stop_rgba(max(0.01, hard), r, g, b, a)
    grad.add_color_stop_rgba(1, r, g, b, 0)
    cr.set_source(grad)
    cr.paint()


def splat(cr, size, rng, col):
    r, g, b, a = col
    cr.set_source_rgba(r, g, b, a)
    for _ in range(9):
        _circle(cr, size / 2 + rng.gauss(0, size * 0.14), size / 2 + rng.gauss(0, size * 0.14), rng.uniform(size * 0.04, size * 0.16))
        cr.fill()


def vignette(cr, size, dark):
    grad = cairo.RadialGradient(size / 2, size / 2, size * 0.06, size / 2, size / 2, size / 2)
    grad.add_color_stop_rgba(0, 0, 0, 0, 0)
    grad.add_color_stop_rgba(0.35, 0, 0, 0.02, dark * 0.45)
    grad.add_color_stop_rgba(0.7, 0, 0, 0.03, dark * 0.85)
    grad.add_color_stop_rgba(0.92, 0, 0, 0.03, dark)
    grad.add_color_stop_rgba(1, 0, 0, 0.03, dark)
    cr.set_source(grad)
    cr.paint()
    # the corners outside the circle are as dark as its rim, so the square's edge never shows
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.rectangle(0, 0, size, size)
    _circle(cr, size / 2, size / 2, size / 2)
    cr.set_source_rgba(0, 0, 0.03, dark)
    cr.fill()


class Sprites:
    """All the textures, made once."""

    def __init__(self):
        self.survivors: dict[str, Gdk.Texture] = {}
        self.guns = {w: texture(SP, SP, lambda cr, w=w: gun_sprite(cr, w)) for w in G.WEAPONS}
        Z = int(SP * 2.5)
        self.zombies = {k: texture(Z, Z, lambda cr, k=k: zombie_sprite(cr, k)) for k in ZOMBIE_LOOK}
        self.flash = {k: texture(Z, Z, lambda cr, k=k: zombie_sprite(cr, k, True)) for k in ZOMBIE_LOOK}
        self.pickups = {k: texture(SP, SP, lambda cr, k=k: pickup_sprite(cr, k)) for k in ("medkit", "ammo", "fuel")}
        self.generator = texture(SP, SP, generator_sprite)
        self.glow = texture(64, 64, lambda cr: soft_dot(cr, 64, (1, 0.9, 0.5, 0.5)))
        self.fire = texture(64, 64, lambda cr: soft_dot(cr, 64, (1, 0.55, 0.1, 0.9), 0.2))
        self.smoke = texture(64, 64, lambda cr: soft_dot(cr, 64, (0.25, 0.25, 0.25, 0.5)))
        self.acid = texture(48, 48, lambda cr: soft_dot(cr, 48, (0.55, 0.85, 0.15, 0.95), 0.5))
        self.flare = texture(64, 64, lambda cr: soft_dot(cr, 64, (1, 0.95, 0.7, 1), 0.15))
        rng = random.Random(3)
        self.blood = [texture(64, 64, lambda cr: splat(cr, 64, rng, (0.45, 0.03, 0.03, 0.85))) for _ in range(4)]
        self.goo = [texture(64, 64, lambda cr: splat(cr, 64, rng, (0.45, 0.65, 0.1, 0.8))) for _ in range(2)]
        self.vignettes: dict[float, Gdk.Texture] = {}

    def survivor(self, key: str) -> Gdk.Texture:
        if key not in self.survivors:
            s = SURVIVOR.get(key) or SURVIVOR["sam"]
            self.survivors[key] = texture(SP, SP, lambda cr: survivor_sprite(cr, s[3], s[4], s[5]))
        return self.survivors[key]

    def vignette(self, dark: float) -> Gdk.Texture:
        key = round(dark, 2)
        if key not in self.vignettes:
            self.vignettes[key] = texture(256, 256, lambda cr: vignette(cr, 256, key))
        return self.vignettes[key]


_SPRITES: Sprites | None = None


def sprites() -> Sprites:
    global _SPRITES
    if _SPRITES is None:
        _SPRITES = Sprites()
    return _SPRITES


# ------------------------------------------------------------------------------------------------ the widget
def _r(x, y, w, h):
    return Graphene.Rect().init(x, y, w, h)


def _p(x, y):
    return Graphene.Point().init(x, y)


class Arena(Gtk.Widget):
    """The game's view. `on_event(kind, *args)` hears about the world's events after they are drawn (sounds,
    ends); `inputs()` returns this frame's game.Input."""

    __gtype_name__ = "RotlineArena"

    def __init__(self, world: G.World, *, survivor: str, inputs, on_event, shake: bool = True):
        super().__init__(hexpand=True, vexpand=True, focusable=True, can_focus=True)
        self.set_accessible_role(Gtk.AccessibleRole.APPLICATION)
        self.world = world
        self.survivor = survivor
        self.inputs = inputs
        self.on_event = on_event
        self.shake_on = shake
        self.sp = sprites()
        self.theme = theme_for(world.level)
        self.map_tex = texture(world.w * PX, world.h * PX, lambda cr: draw_map(cr, world, self.theme))
        self.paused = False
        self.particles: list[list] = []   # x, y, vx, vy, life, max, tex, size, grow
        self.decals: list[list] = []      # x, y, tex, size, angle, born
        self.corpses: list[list] = []     # x, y, kind, angle, born
        self.flashes: list[list] = []     # x, y, angle, life
        self.shake = 0.0
        self.hurt = 0.0
        self.tile = 48.0
        self.cam = (0.0, 0.0)
        self.clock = 0.0
        self.stick = None                 # (ox, oy, x, y) in pixels, while a finger drives
        self.show_stick = False
        self.rng = random.Random()
        self._last = None
        self._tick = self.add_tick_callback(self._on_tick)

    # ------------------------------------------------------------------ running
    def _on_tick(self, _widget, clock) -> bool:
        now = clock.get_frame_time() / 1e6
        dt = 0.0 if self._last is None else min(0.1, now - self._last)
        self._last = now
        if not self.paused:
            self.clock += dt
            if self.world.state == "play":
                self.world.update(self.inputs(), dt)
            self._effects(dt)
            for ev in self.world.drain_events():
                self._event(ev)
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def stop(self):
        if self._tick:
            self.remove_tick_callback(self._tick)
            self._tick = 0

    def _event(self, ev):
        kind = ev[0]
        rnd = self.rng
        if kind == "blood":
            _, x, y, a = ev
            for _ in range(5):
                sp = rnd.uniform(1.5, 4)
                aa = a + rnd.uniform(-0.6, 0.6)
                self.particles.append([x, y, math.cos(aa) * sp, math.sin(aa) * sp, 0.3, 0.3, "blood", 0.12, 0])
            if len(self.decals) < 220:
                self.decals.append([x + rnd.uniform(-0.2, 0.2), y + rnd.uniform(-0.2, 0.2), rnd.choice(self.sp.blood),
                                    rnd.uniform(0.4, 0.8), rnd.uniform(0, 360), self.clock])
        elif kind == "kill":
            _, k, x, y, a = ev
            if k != "bloater":
                self.corpses.append([x, y, k, math.degrees(a) + 180 + rnd.uniform(-30, 30), self.clock])
                if len(self.corpses) > 70:
                    self.corpses.pop(0)
            self.decals.append([x, y, rnd.choice(self.sp.blood), 1.0 if k != "tank" else 2.2, rnd.uniform(0, 360), self.clock])
        elif kind == "spark":
            _, x, y = ev
            for _ in range(4):
                a = rnd.uniform(0, 6.28)
                self.particles.append([x, y, math.cos(a) * 3, math.sin(a) * 3, 0.15, 0.15, "glow", 0.18, 0])
        elif kind == "acid":
            _, x, y = ev
            self.decals.append([x, y, rnd.choice(self.sp.goo), 0.7, rnd.uniform(0, 360), self.clock])
        elif kind == "explode":
            _, x, y, r = ev
            for _ in range(26):
                a = rnd.uniform(0, 6.28)
                sp = rnd.uniform(1, 6)
                self.particles.append([x, y, math.cos(a) * sp, math.sin(a) * sp, 0.55, 0.55, "fire", 0.7, 1.2])
            for _ in range(10):
                a = rnd.uniform(0, 6.28)
                self.particles.append([x, y, math.cos(a), math.sin(a), 1.4, 1.4, "smoke", 0.9, 1.5])
            self.decals.append([x, y, rnd.choice(self.sp.goo), r, rnd.uniform(0, 360), self.clock])
        elif kind == "muzzle":
            _, x, y, a = ev
            self.flashes.append([x, y, a, 0.05])
        elif kind == "shake":
            if self.shake_on:
                self.shake = max(self.shake, ev[1])
        elif kind == "hurt":
            self.hurt = 0.5
        elif kind == "pickup":
            _, k, x, y = ev
            for _ in range(8):
                a = rnd.uniform(0, 6.28)
                self.particles.append([x, y, math.cos(a) * 2, math.sin(a) * 2, 0.35, 0.35, "glow", 0.25, 0])
        self.on_event(ev)

    def _effects(self, dt):
        keep = []
        for p in self.particles:
            p[4] -= dt
            if p[4] > 0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[2] *= 0.9
                p[3] *= 0.9
                p[7] += p[8] * dt
                keep.append(p)
        self.particles = keep[-400:]
        self.flashes = [f for f in self.flashes if (f.__setitem__(3, f[3] - dt) or f[3] > 0)]
        self.shake = max(0.0, self.shake - dt * 1.8)
        self.hurt = max(0.0, self.hurt - dt * 1.5)
        # flames leave a little smoke
        for s in self.world.shots:
            if s.kind == "flame" and self.rng.random() < 0.08:
                self.particles.append([s.x, s.y, 0, 0, 0.6, 0.6, "smoke", 0.3, 0.8])
        for z in self.world.zombies:
            if z.burn > 0 and self.rng.random() < 0.4:
                self.particles.append([z.x + self.rng.uniform(-0.2, 0.2), z.y + self.rng.uniform(-0.2, 0.2), 0, -0.6,
                                       0.4, 0.4, "fire", 0.35, 0.3])
        cutoff = self.clock - 40
        if self.decals and self.decals[0][5] < cutoff:
            self.decals = [d for d in self.decals if d[5] >= cutoff]

    # ------------------------------------------------------------------ drawing
    def do_snapshot(self, s):
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return
        world = self.world
        # about 12 tiles on the short side; a little closer on a phone held upright
        self.tile = t = max(22.0, min(w, h) / (11.0 if min(w, h) < 520 else 13.5))
        p = world.player
        cx, cy = p.x * t - w / 2, p.y * t - h / 2
        mw, mh = world.w * t, world.h * t
        cx = (mw - w) / 2 if mw <= w else max(0, min(mw - w, cx))
        cy = (mh - h) / 2 if mh <= h else max(0, min(mh - h, cy))
        if self.shake > 0:
            amp = self.shake * t * 0.35
            cx += self.rng.uniform(-amp, amp)
            cy += self.rng.uniform(-amp, amp)
        self.cam = (cx, cy)
        s.append_color(rgba("#101214"), _r(0, 0, w, h))
        s.save()
        s.translate(_p(-cx, -cy))
        s.append_texture(self.map_tex, _r(0, 0, mw, mh))
        view = (cx / t - 2, cy / t - 2, (cx + w) / t + 2, (cy + h) / t + 2)

        def visible(x, y):
            return view[0] < x < view[2] and view[1] < y < view[3]

        # the way out
        if world.exits:
            pulse = 0.5 + 0.5 * math.sin(self.clock * 4)
            col = rgba("#3ddc84", 0.25 + 0.25 * pulse) if world.exit_open else rgba("#dc3d3d", 0.18)
            for i, j in world.exits:
                s.append_color(col, _r(i * t, j * t, t, t))
        for d in self.decals:
            if visible(d[0], d[1]):
                self._sprite(s, d[2], d[0], d[1], d[3], d[4])
        for c in self.corpses:
            if visible(c[0], c[1]):
                tex = self.sp.zombies[c[2]]
                size = 2.5
                s.push_opacity(0.55)
                self._sprite(s, tex, c[0], c[1], size * CH, c[3])
                s.pop()
        if world.gen:
            gx, gy = world.gen
            s.append_texture(self.sp.generator, _r((gx - 0.5) * t, (gy - 0.5) * t, t, t))
            frac = max(0.0, world.gen_hp / world.gen_max)
            s.append_color(rgba("#000000", 0.6), _r((gx - 0.6) * t, (gy - 0.85) * t, 1.2 * t, 0.14 * t))
            s.append_color(rgba("#3ddc84" if frac > 0.35 else "#e5484d"), _r((gx - 0.6) * t, (gy - 0.85) * t, 1.2 * t * frac, 0.14 * t))
        for pk in world.pickups:
            if visible(pk.x, pk.y):
                bob = math.sin(pk.bob) * 0.06
                s.push_opacity(0.35 + 0.15 * math.sin(pk.bob * 1.3))
                self._sprite(s, self.sp.glow, pk.x, pk.y, 1.0, 0)
                s.pop()
                self._sprite(s, self.sp.pickups[pk.kind], pk.x, pk.y + bob, 1.0, 0)
        # the dead
        for z in world.zombies:
            if not visible(z.x, z.y):
                continue
            sway = math.sin(z.walk) * 9
            ang = math.degrees(z.angle) + sway
            if z.state == "windup":
                ang += math.sin(self.clock * 60) * 6
            self._sprite(s, self.sp.zombies[z.kind.key], z.x, z.y, 2.5 * CH, ang)
            if z.flash > 0:
                s.push_opacity(0.8)
                self._sprite(s, self.sp.flash[z.kind.key], z.x, z.y, 2.5 * CH, ang)
                s.pop()
            if z.kind.key in ("brute",) and z.hp < z.max_hp:
                self._bar(s, z.x, z.y - z.kind.radius - 0.25, 0.8, z.hp / z.max_hp, "#e5484d")
        # the survivor
        if world.state != "lost":
            ang = math.degrees(p.angle)
            bob = 1 + math.sin(p.walk) * 0.03
            self._sprite(s, self.sp.survivor(self.survivor), p.x, p.y, CH * bob, ang)
            self._sprite(s, self.sp.guns[p.weapon], p.x, p.y, CH * bob, ang)
            if p.hurt > 0:
                s.push_opacity(p.hurt)
                self._sprite(s, self.sp.blood[0], p.x, p.y, 0.8, 0)
                s.pop()
        for f in self.flashes:
            x, y = f[0] + math.cos(f[2]) * 0.15, f[1] + math.sin(f[2]) * 0.15
            self._sprite(s, self.sp.flare, x, y, 0.75, 0)
        # shots
        for sh in world.shots:
            if not visible(sh.x, sh.y):
                continue
            if sh.kind == "flame":
                life = min(1.0, sh.age / 0.5)
                s.push_opacity(max(0.0, 0.9 - life * 0.6))
                self._sprite(s, self.sp.fire, sh.x, sh.y, 0.35 + life * 0.9, 0)
                s.pop()
            elif sh.kind == "acid":
                self._sprite(s, self.sp.acid, sh.x, sh.y, 0.35, 0)
            else:
                ln = 0.55 if sh.kind == "bolt" else 0.4
                col = rgba("#c8a060") if sh.kind == "bolt" else rgba("#fff3b0", 0.9)
                s.save()
                s.translate(_p(sh.x * t, sh.y * t))
                s.rotate(math.degrees(math.atan2(sh.dy, sh.dx)))
                s.append_color(col, _r(-ln * t, -0.03 * t, ln * t, 0.06 * t))
                s.restore()
        for q in self.particles:
            if not visible(q[0], q[1]):
                continue
            a = q[4] / q[5]
            name = q[6]
            if name == "blood":
                s.append_color(rgba("#7a0a0a", a), _r((q[0] - 0.04) * t, (q[1] - 0.04) * t, 0.08 * t, 0.08 * t))
                continue
            tex = {"glow": self.sp.glow, "fire": self.sp.fire, "smoke": self.sp.smoke}[name]
            s.push_opacity(a)
            self._sprite(s, tex, q[0], q[1], q[7], 0)
            s.pop()
        s.restore()
        # light: dark around the edges, centred on the survivor
        dark = self.theme["dark"]
        px, py = p.x * t - cx, p.y * t - cy
        size = max(w, h) * 1.35
        s.append_texture(self.sp.vignette(dark), _r(px - size / 2, py - size / 2, size, size))
        # beyond the light's square, it's all dark
        x0, y0, x1, y1 = px - size / 2, py - size / 2, px + size / 2, py + size / 2
        edge = rgba("#000008", dark)
        if y0 > 0:
            s.append_color(edge, _r(0, 0, w, y0))
        if y1 < h:
            s.append_color(edge, _r(0, y1, w, h - y1))
        if x0 > 0:
            s.append_color(edge, _r(0, max(0, y0), x0, min(h, y1) - max(0, y0)))
        if x1 < w:
            s.append_color(edge, _r(x1, max(0, y0), w - x1, min(h, y1) - max(0, y0)))
        r, g, b, a = self.theme["tint"]
        s.append_color(Gdk.RGBA(red=r, green=g, blue=b, alpha=a), _r(0, 0, w, h))
        if self.hurt > 0 or (p.hp < p.max_hp * 0.25 and world.state == "play"):
            low = 0.12 + 0.08 * math.sin(self.clock * 5) if p.hp < p.max_hp * 0.25 else 0
            s.append_color(rgba("#a00000", max(self.hurt * 0.45, low)), _r(0, 0, w, h))
        self._pointers(s, w, h, t, cx, cy)
        if self.stick and self.show_stick:
            ox, oy, x, y = self.stick
            s.push_opacity(0.35)
            self._disc(s, ox, oy, 56, "#ffffff")
            s.pop()
            s.push_opacity(0.6)
            self._disc(s, x, y, 26, "#ffffff")
            s.pop()

    def _sprite(self, s, tex, x, y, size_tiles, angle_deg):
        t = self.tile
        half = size_tiles * t / 2
        s.save()
        s.translate(_p(x * t, y * t))
        if angle_deg:
            s.rotate(angle_deg)
        s.append_texture(tex, _r(-half, -half, half * 2, half * 2))
        s.restore()

    def _bar(self, s, x, y, width, frac, col):
        t = self.tile
        s.append_color(rgba("#000000", 0.6), _r((x - width / 2) * t, y * t, width * t, 0.09 * t))
        s.append_color(rgba(col), _r((x - width / 2) * t, y * t, width * t * max(0.0, frac), 0.09 * t))

    def _disc(self, s, x, y, r, col):
        rr = Gsk.RoundedRect()
        rr.init_from_rect(_r(x - r, y - r, r * 2, r * 2), r)
        s.push_rounded_clip(rr)
        s.append_color(rgba(col), _r(x - r, y - r, r * 2, r * 2))
        s.pop()

    def _pointers(self, s, w, h, t, cx, cy):
        """Arrows at the edge of the screen toward what you're looking for, when it's out of sight."""
        world = self.world
        targets = []
        if world.level.goal == "escape":
            if world.exit_open:
                i, j = min(world.exits, key=lambda e: (e[0] - world.player.x) ** 2 + (e[1] - world.player.y) ** 2)
                targets.append((i + 0.5, j + 0.5, "#3ddc84"))
            else:
                targets += [(pk.x, pk.y, "#ff6a4a") for pk in world.pickups if pk.kind == "fuel"]
        if world.gen:
            targets.append((world.gen[0], world.gen[1], "#f0c419"))
        targets += [(z.x, z.y, "#e5484d") for z in world.zombies if z.boss]
        m = 26
        for x, y, col in targets:
            sx, sy = x * t - cx, y * t - cy
            if m < sx < w - m and m < sy < h - m:
                continue
            ex = min(max(sx, m), w - m)
            ey = min(max(sy, m), h - m)
            ang = math.degrees(math.atan2(sy - h / 2, sx - w / 2))
            s.save()
            s.translate(_p(ex, ey))
            s.rotate(ang)
            s.rotate(45)
            s.append_color(rgba(col, 0.9), _r(-7, -7, 14, 14))
            s.restore()

    # ------------------------------------------------------------------ for input
    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        cx, cy = self.cam
        return (x + cx) / self.tile, (y + cy) / self.tile

    def player_on_screen(self) -> tuple[float, float]:
        p = self.world.player
        return p.x * self.tile - self.cam[0], p.y * self.tile - self.cam[1]
