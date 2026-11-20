#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Paints every picture in Rotline with cairo, into game/assets/. Run it again after changing it:

    python3 tools/make_art.py

All art is original and drawn in code: survivors and the dead (walk cycles, lit from the top left), weapons,
tiles for three places, cars, trees, crates and containers, pickups, splats, smoke and fire, and the textures for
the lights. Needs pycairo (it's in the Luma SDK).
"""
from __future__ import annotations

import math
import os
import random

import cairo

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "game", "assets")
T = 64           # a tile, in pixels
TAU = math.tau


def rgb(h, a=1.0):
    h = h.lstrip("#")
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a


def mix(a, b, t):
    ca, cb = rgb(a), rgb(b)
    return "#%02x%02x%02x" % tuple(int((ca[i] * (1 - t) + cb[i] * t) * 255) for i in range(3))


def shade(h, k):
    """k < 0 darker, k > 0 lighter."""
    return mix(h, "#000000", -k) if k < 0 else mix(h, "#ffffff", k)


def surface(w, h):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    return s, cairo.Context(s)


def save(s, name):
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    s.write_to_png(path)


def circle(cr, x, y, r):
    cr.new_sub_path()
    cr.arc(x, y, r, 0, TAU)


def ellipse(cr, x, y, rx, ry, angle=0.0):
    cr.save()
    cr.translate(x, y)
    cr.rotate(angle)
    cr.scale(rx, ry)
    cr.new_sub_path()
    cr.arc(0, 0, 1, 0, TAU)
    cr.restore()


def rrect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def ball(cr, x, y, r, col, outline=True, light=0.35, dark=0.4):
    """A shaded sphere, lit from the top left."""
    g = cairo.RadialGradient(x - r * 0.35, y - r * 0.4, r * 0.1, x, y, r * 1.05)
    g.add_color_stop_rgba(0, *rgb(shade(col, light)))
    g.add_color_stop_rgba(0.55, *rgb(col))
    g.add_color_stop_rgba(1, *rgb(shade(col, -dark)))
    circle(cr, x, y, r)
    cr.set_source(g)
    cr.fill_preserve()
    if outline:
        cr.set_source_rgba(0.06, 0.05, 0.05, 0.9)
        cr.set_line_width(max(1.5, r * 0.09))
        cr.stroke()
    else:
        cr.new_path()


def blob(cr, x, y, rx, ry, col, angle=0.0, outline=True, light=0.3, dark=0.45):
    cr.save()
    cr.translate(x, y)
    cr.rotate(angle)
    cr.scale(rx, ry)
    g = cairo.RadialGradient(-0.35, -0.45, 0.1, 0, 0, 1.08)
    g.add_color_stop_rgba(0, *rgb(shade(col, light)))
    g.add_color_stop_rgba(0.6, *rgb(col))
    g.add_color_stop_rgba(1, *rgb(shade(col, -dark)))
    cr.new_sub_path()
    cr.arc(0, 0, 1, 0, TAU)
    cr.set_source(g)
    cr.fill_preserve()
    cr.restore()
    if outline:
        cr.set_source_rgba(0.06, 0.05, 0.05, 0.9)
        cr.set_line_width(max(1.5, min(rx, ry) * 0.1))
        cr.stroke()
    else:
        cr.new_path()


def limb(cr, x0, y0, x1, y1, w, col):
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_source_rgba(0.06, 0.05, 0.05, 0.9)
    cr.set_line_width(w + 3)
    cr.move_to(x0, y0)
    cr.line_to(x1, y1)
    cr.stroke()
    g = cairo.LinearGradient(x0, y0 - w, x0, y0 + w)
    g.add_color_stop_rgba(0, *rgb(shade(col, 0.25)))
    g.add_color_stop_rgba(1, *rgb(shade(col, -0.25)))
    cr.set_source(g)
    cr.set_line_width(w)
    cr.move_to(x0, y0)
    cr.line_to(x1, y1)
    cr.stroke()


def soft_shadow(cr, x, y, rx, ry, a=0.35):
    cr.save()
    cr.translate(x, y)
    cr.scale(rx, ry)
    g = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    g.add_color_stop_rgba(0, 0, 0, 0, a)
    g.add_color_stop_rgba(1, 0, 0, 0, 0)
    cr.arc(0, 0, 1, 0, TAU)
    cr.set_source(g)
    cr.fill()
    cr.restore()


# ------------------------------------------------------------------------------------------------ people
SURVIVORS = {
    # jacket, trousers, skin, hair, extra
    "sam": ("#3f6aa8", "#2b3340", "#e0b18c", "#3a2a1c", "cap"),  # red cap
    "rosa": ("#e6e6e6", "#28408a", "#a8714f", "#1c1410", "cross"),
    "hank": ("#5c6b3a", "#4a3b28", "#d9a37c", "#8a8a8a", "hat"),
    "jules": ("#262626", "#1e1e24", "#f0c8a0", "#c4502e", "stripe"),
    "mo": ("#d6a51c", "#3a3020", "#7a4c2e", "#141414", "helmet"),
}
FRAMES = 8
CELL = 128      # a person cell; the body is ~0.62 tile across at this scale (1 tile = 64 world px drawn at 2x)


def survivor_frame(cr, look, phase, cell=CELL):
    jacket, trousers, skin, hair, extra = look
    c = cell / 2
    s = cell / 128
    cr.save()
    cr.translate(c, c)
    cr.scale(s, s)
    step = math.sin(phase)
    soft_shadow(cr, 4, 6, 34, 30, 0.4)
    # feet, stepping along the facing (+x)
    for side, ph in ((-1, step), (1, -step)):
        blob(cr, ph * 13 - 2, side * 13, 11, 7, shade(trousers, -0.2), 0, True, 0.2, 0.4)
    # shoulders and torso
    sway = step * 0.08
    cr.save()
    cr.rotate(sway)
    blob(cr, -2, 0, 20, 30, jacket, 0, True, 0.35, 0.45)
    if extra == "cross":
        cr.set_source_rgba(*rgb("#d42c2c"))
        cr.rectangle(-8, -3, 12, 6)
        cr.rectangle(-5, -6, 6, 12)
        cr.fill()
    if extra == "stripe":
        cr.set_source_rgba(*rgb("#e0a82e", 0.9))
        cr.rectangle(-14, -28, 5, 56)
        cr.fill()
    if extra == "helmet":
        cr.set_source_rgba(*rgb("#f2f2f2", 0.85))
        cr.rectangle(-16, -26, 4, 52)
        cr.rectangle(4, -24, 4, 48)
        cr.fill()
    # arms to the gun, forward
    limb(cr, 2, -22, 30, -5, 9, jacket)
    limb(cr, 2, 22, 30, 5, 9, jacket)
    ball(cr, 32, -4, 6, skin, True, 0.3, 0.3)
    ball(cr, 32, 4, 6, skin, True, 0.3, 0.3)
    cr.restore()
    # head
    ball(cr, 2, 0, 15, skin, True, 0.35, 0.35)
    cr.save()
    circle(cr, 2, 0, 15)
    cr.clip()
    if extra == "cap":
        blob(cr, -2, 0, 15, 16, "#b8352a", 0, False, 0.35, 0.4)
        cr.set_source_rgba(*rgb("#7a2018"))
        rrect(cr, 8, -11, 12, 22, 5)
        cr.fill()
    elif extra == "hat":
        blob(cr, 0, 0, 18, 18, "#7a5a32", 0, False, 0.3, 0.4)
    elif extra == "helmet":
        blob(cr, -1, 0, 16, 16, "#c8961a", 0, False, 0.5, 0.4)
    else:
        blob(cr, -6, 0, 12, 15, hair, 0, False, 0.3, 0.4)
    cr.restore()
    if extra == "hat":
        cr.set_source_rgba(0.06, 0.05, 0.05, 0.9)
        cr.set_line_width(2)
        ellipse(cr, 1, 0, 20, 20)
        cr.stroke()
        blob(cr, 0, 0, 12, 12, "#8a6a3e", 0, True, 0.4, 0.4)
    cr.restore()


def gun(cr, kind, cell=CELL):
    c = cell / 2
    s = cell / 128
    cr.save()
    cr.translate(c, c)
    cr.scale(s, s)
    spec = {"pistol": (16, 7, "#2a2a2c"), "shotgun": (40, 8, "#4a3222"), "smg": (30, 10, "#1e1e22"),
            "rifle": (46, 7, "#3a3a2a"), "flamer": (38, 13, "#b23a1c"), "crossbow": (32, 7, "#6b4a2a")}
    ln, w, col = spec[kind]
    x0 = 30
    cr.set_source_rgba(0.05, 0.05, 0.05, 0.95)
    rrect(cr, x0 - 2, -w / 2 - 2, ln + 4, w + 4, 3)
    cr.fill()
    g = cairo.LinearGradient(0, -w / 2, 0, w / 2)
    g.add_color_stop_rgba(0, *rgb(shade(col, 0.35)))
    g.add_color_stop_rgba(1, *rgb(shade(col, -0.3)))
    cr.set_source(g)
    rrect(cr, x0, -w / 2, ln, w, 2)
    cr.fill()
    if kind == "shotgun":
        cr.set_source_rgba(*rgb("#2a2a2c"))
        cr.rectangle(x0 + 14, -2, ln - 12, 4)
        cr.fill()
    if kind == "rifle":
        cr.set_source_rgba(*rgb("#141414"))
        rrect(cr, x0 + 12, -6, 14, 5, 2)
        cr.fill()
    if kind == "flamer":
        ball(cr, x0 + 8, 0, 8, "#c84a20", True, 0.4, 0.3)
        cr.set_source_rgba(1, 0.65, 0.15, 1)
        circle(cr, x0 + ln + 1, 0, 3)
        cr.fill()
    if kind == "crossbow":
        cr.set_source_rgba(0.06, 0.05, 0.05, 0.95)
        cr.set_line_width(5)
        cr.move_to(x0 + ln - 6, -18)
        cr.curve_to(x0 + ln + 4, -6, x0 + ln + 4, 6, x0 + ln - 6, 18)
        cr.stroke()
        cr.set_source_rgba(*rgb("#8a6a40"))
        cr.set_line_width(3)
        cr.move_to(x0 + ln - 6, -18)
        cr.curve_to(x0 + ln + 4, -6, x0 + ln + 4, 6, x0 + ln - 6, 18)
        cr.stroke()
        cr.set_source_rgba(0.85, 0.85, 0.8, 0.8)
        cr.set_line_width(1)
        cr.move_to(x0 + ln - 6, -18)
        cr.line_to(x0 + 4, 0)
        cr.line_to(x0 + ln - 6, 18)
        cr.stroke()
    cr.restore()


ZOMBIES = {
    # shirt, trousers, skin, size (radius px at 128), kind of body
    "walker": ("#5a4e66", "#2f3340", "#8fa37a", 1.0),
    "runner": ("#8a2f2f", "#2a2a30", "#a3b48e", 0.92),
    "brute": ("#3b3b3b", "#26262a", "#728a62", 1.5),
    "spitter": ("#4b6b3a", "#2e3326", "#a6b85a", 1.0),
    "bloater": ("#8a8a4a", "#3a3a28", "#b5bb6a", 1.35),
    "tank": ("#4a3a32", "#2a2420", "#6b7d58", 1.0),   # drawn in its own bigger cell
}


def zombie_frame(cr, kind, phase, cell=CELL, attack=False):
    shirt, trousers, skin, size = ZOMBIES[kind]
    c = cell / 2
    s = cell / 128
    cr.save()
    cr.translate(c, c)
    cr.scale(s, s)
    if kind == "tank":
        cr.scale(1.0, 1.0)
    step = math.sin(phase)
    rng = random.Random(hash(kind) & 0xffff)
    scale = {"brute": 1.25, "bloater": 1.15}.get(kind, 1.0)
    if kind == "tank":
        scale = 1.5
    cr.scale(scale, scale)
    soft_shadow(cr, 4, 6, 34, 30, 0.45)
    for side, ph in ((-1, step), (1, -step)):
        blob(cr, ph * 10 - 4, side * 13, 10, 7, shade(trousers, -0.1), 0.2 * side, True, 0.2, 0.4)
    sway = step * 0.12
    cr.save()
    cr.rotate(sway)
    # arms reaching forward, one ahead of the other
    reach = 40 if attack else 34
    a1 = (step * 5, -20, reach + step * 4, -16)
    a2 = (-step * 5, 20, reach - step * 4, 17)
    if kind == "tank":
        a1 = (0, -26, 30 + step * 4, -30)
        a2 = (0, 26, 30 - step * 4, 30)
    for x0, y0, x1, y1 in (a1, a2):
        limb(cr, x0, y0, x1, y1, 10 if kind != "tank" else 15, skin)
        ball(cr, x1 + 2, y1, 6 if kind != "tank" else 10, shade(skin, -0.1), True, 0.2, 0.3)
    wide = {"bloater": 30, "tank": 26}.get(kind, 20)
    blob(cr, -3, 0, wide, 30, shirt, 0, True, 0.3, 0.5)
    # torn cloth and stains
    for _ in range(3):
        cr.set_source_rgba(0.32, 0.03, 0.03, 0.55)
        ellipse(cr, rng.uniform(-12, 8), rng.uniform(-18, 18), rng.uniform(3, 7), rng.uniform(2, 5), rng.uniform(0, 3))
        cr.fill()
    if kind == "bloater":
        for x, y, r in ((-10, -14, 6), (6, 14, 7), (-14, 9, 5), (8, -6, 5)):
            ball(cr, x, y, r, "#c9cf72", True, 0.5, 0.3)
    if kind == "spitter":
        cr.set_source_rgba(0.6, 0.9, 0.2, 0.85)
        ellipse(cr, 16, 2, 5, 9)
        cr.fill()
    if kind == "brute":
        cr.set_source_rgba(*rgb("#1e1e1e", 0.9))
        rrect(cr, -18, -26, 10, 52, 4)
        cr.fill()
    if kind == "tank":
        for y in (-18, 0, 18):
            ball(cr, -10, y, 7, shade(skin, -0.15), True, 0.3, 0.4)
    cr.restore()
    hr = 14 if kind != "tank" else 15
    ball(cr, 4, 0, hr, skin, True, 0.3, 0.4)
    # sunken eyes
    cr.set_source_rgba(0.08, 0.02, 0.02, 0.9)
    circle(cr, 12, -5, 3.4)
    circle(cr, 12, 5, 3.4)
    cr.fill()
    cr.set_source_rgba(0.95, 0.2, 0.1, 0.95)
    circle(cr, 12.5, -5, 1.6)
    circle(cr, 12.5, 5, 1.6)
    cr.fill()
    cr.set_source_rgba(*rgb(shade(skin, -0.45), 0.9))
    ellipse(cr, -2, -2, 7, 9)
    cr.fill()
    cr.restore()


def sheet(name, frames, cell, draw):
    s, cr = surface(cell * frames, cell)
    for i in range(frames):
        cr.save()
        cr.translate(i * cell, 0)
        draw(cr, i)
        cr.restore()
    save(s, name)


# ------------------------------------------------------------------------------------------------ tiles
THEMES = {
    "suburb": dict(ground="#4b6b3a", ground2="#3f5e31", road="#3b3d41", floor="#8a6a4c", floor2="#77583d",
                   wall="#7a4a38", roof="#94604a", trim="#5a3528"),
    "downtown": dict(ground="#6a6b69", ground2="#5c5d5b", road="#2c2e31", floor="#8d9196", floor2="#7a7e83",
                     wall="#353a45", roof="#474e5c", trim="#262a33"),
    "harbor": dict(ground="#5a6166", ground2="#4e555a", road="#33363a", floor="#6c6960", floor2="#5d5a52",
                   wall="#46576a", roof="#5a6e84", trim="#33414f"),
    "endless": dict(ground="#4a573c", ground2="#3f4b33", road="#37383b", floor="#7a6a55", floor2="#6a5b48",
                    wall="#4c4a52", roof="#615e6a", trim="#38363d"),
}
# atlas columns: 0 ground, 1 ground2, 2 road, 3 road with a line, 4 floor, 5 floor2, 6 sidewalk, 7 water base,
# then 8..23 the wall for each mask of open sides (N=1, E=2, S=4, W=8)
ATLAS_COLS = 24


def noise_fill(cr, x, y, w, h, base, speck, rng, n=40, size=(1, 3), alpha=0.5):
    cr.set_source_rgba(*rgb(base))
    cr.rectangle(x, y, w, h)
    cr.fill()
    for _ in range(n):
        cr.set_source_rgba(*rgb(speck, alpha * rng.uniform(0.4, 1)))
        r = rng.uniform(*size)
        circle(cr, x + rng.uniform(0, w), y + rng.uniform(0, h), r)
        cr.fill()


def tile(cr, kind, th, rng):
    if kind == "ground":
        noise_fill(cr, 0, 0, T, T, th["ground"], th["ground2"], rng, 70, (1, 3.5), 0.7)
        for _ in range(10):
            cr.set_source_rgba(*rgb(shade(th["ground"], 0.15), 0.5))
            x, y = rng.uniform(0, T), rng.uniform(0, T)
            cr.set_line_width(1.2)
            cr.move_to(x, y)
            cr.line_to(x + rng.uniform(-2, 2), y - rng.uniform(3, 6))
            cr.stroke()
    elif kind == "ground2":
        noise_fill(cr, 0, 0, T, T, mix(th["ground"], th["ground2"], 0.5), th["ground"], rng, 60, (1, 4), 0.7)
    elif kind in ("road", "road_line"):
        noise_fill(cr, 0, 0, T, T, th["road"], shade(th["road"], 0.12), rng, 120, (0.5, 1.6), 0.6)
        noise_fill(cr, 0, 0, 0, 0, th["road"], th["road"], rng, 0)
        if rng.random() < 0.4:
            cr.set_source_rgba(0, 0, 0, 0.25)
            cr.set_line_width(1.2)
            x, y = rng.uniform(5, T - 5), rng.uniform(5, T - 5)
            cr.move_to(x, y)
            for _ in range(4):
                x += rng.uniform(-8, 8)
                y += rng.uniform(-8, 8)
                cr.line_to(x, y)
            cr.stroke()
        if kind == "road_line":
            cr.set_source_rgba(0.88, 0.75, 0.25, 0.75)
            cr.rectangle(T * 0.25, T / 2 - 2, T * 0.5, 4)
            cr.fill()
    elif kind in ("floor", "floor2"):
        base = th[kind]
        cr.set_source_rgba(*rgb(base))
        cr.rectangle(0, 0, T, T)
        cr.fill()
        for k in range(4):
            g = cairo.LinearGradient(0, k * 16, 0, k * 16 + 16)
            g.add_color_stop_rgba(0, *rgb(shade(base, 0.08)))
            g.add_color_stop_rgba(1, *rgb(shade(base, -0.08)))
            cr.set_source(g)
            cr.rectangle(0, k * 16, T, 15)
            cr.fill()
            cr.set_source_rgba(0, 0, 0, 0.3)
            off = rng.uniform(0, T)
            cr.rectangle(off, k * 16, 1.2, 15)
            cr.fill()
        for _ in range(30):
            cr.set_source_rgba(0, 0, 0, 0.06)
            cr.rectangle(rng.uniform(0, T), rng.uniform(0, T), rng.uniform(4, 10), 1)
            cr.fill()
    elif kind == "sidewalk":
        noise_fill(cr, 0, 0, T, T, shade(th["ground"], 0.1), shade(th["ground"], -0.05), rng, 40, (0.5, 1.5), 0.5)
        cr.set_source_rgba(0, 0, 0, 0.18)
        cr.set_line_width(1.5)
        cr.rectangle(1, 1, T - 2, T - 2)
        cr.stroke()
    elif kind == "water":
        cr.set_source_rgba(*rgb("#173a50"))
        cr.rectangle(0, 0, T, T)
        cr.fill()


def wall_tile(cr, th, mask, rng):
    """A building seen from above: a roof with a lit rim where it meets open ground."""
    roof, wall, trim = th["roof"], th["wall"], th["trim"]
    g = cairo.LinearGradient(0, 0, T, T)
    g.add_color_stop_rgba(0, *rgb(shade(roof, 0.06)))
    g.add_color_stop_rgba(1, *rgb(shade(roof, -0.1)))
    cr.set_source(g)
    cr.rectangle(0, 0, T, T)
    cr.fill()
    for _ in range(25):
        cr.set_source_rgba(0, 0, 0, 0.07)
        cr.rectangle(rng.uniform(0, T), rng.uniform(0, T), rng.uniform(2, 6), rng.uniform(2, 6))
        cr.fill()
    rim = 9
    # N and W edges catch the light; S and E fall into shade
    if mask & 1:
        g = cairo.LinearGradient(0, 0, 0, rim)
        g.add_color_stop_rgba(0, *rgb(shade(roof, 0.35)))
        g.add_color_stop_rgba(1, *rgb(roof, 0))
        cr.set_source(g)
        cr.rectangle(0, 0, T, rim)
        cr.fill()
        cr.set_source_rgba(*rgb(trim))
        cr.rectangle(0, 0, T, 2)
        cr.fill()
    if mask & 8:
        g = cairo.LinearGradient(0, 0, rim, 0)
        g.add_color_stop_rgba(0, *rgb(shade(roof, 0.25)))
        g.add_color_stop_rgba(1, *rgb(roof, 0))
        cr.set_source(g)
        cr.rectangle(0, 0, rim, T)
        cr.fill()
        cr.set_source_rgba(*rgb(trim))
        cr.rectangle(0, 0, 2, T)
        cr.fill()
    if mask & 4:
        g = cairo.LinearGradient(0, T - rim * 1.6, 0, T)
        g.add_color_stop_rgba(0, *rgb(wall, 0))
        g.add_color_stop_rgba(1, *rgb(shade(wall, -0.25)))
        cr.set_source(g)
        cr.rectangle(0, T - rim * 1.6, T, rim * 1.6)
        cr.fill()
        cr.set_source_rgba(*rgb(trim))
        cr.rectangle(0, T - 2, T, 2)
        cr.fill()
    if mask & 2:
        g = cairo.LinearGradient(T - rim, 0, T, 0)
        g.add_color_stop_rgba(0, *rgb(wall, 0))
        g.add_color_stop_rgba(1, *rgb(shade(wall, -0.3)))
        cr.set_source(g)
        cr.rectangle(T - rim, 0, rim, T)
        cr.fill()
        cr.set_source_rgba(*rgb(trim))
        cr.rectangle(T - 2, 0, 2, T)
        cr.fill()
    if rng.random() < 0.12 and mask == 0:
        # rooftop clutter: a vent or an AC unit
        cr.set_source_rgba(0, 0, 0, 0.3)
        rrect(cr, 18, 20, 30, 26, 3)
        cr.fill()
        cr.set_source_rgba(*rgb(shade(roof, 0.25)))
        rrect(cr, 16, 17, 30, 26, 3)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.35)
        circle(cr, 31, 30, 8)
        cr.fill()


def atlas(theme):
    th = THEMES[theme]
    rng = random.Random(theme)
    s, cr = surface(T * ATLAS_COLS, T)
    kinds = ["ground", "ground2", "road", "road_line", "floor", "floor2", "sidewalk", "water"]
    for i, k in enumerate(kinds):
        cr.save()
        cr.translate(i * T, 0)
        cr.rectangle(0, 0, T, T)
        cr.clip()
        tile(cr, k, th, rng)
        cr.restore()
    for mask in range(16):
        cr.save()
        cr.translate((8 + mask) * T, 0)
        cr.rectangle(0, 0, T, T)
        cr.clip()
        wall_tile(cr, th, mask, rng)
        cr.restore()
    save(s, f"tiles/{theme}.png")


# ------------------------------------------------------------------------------------------------ props
CAR_COLOURS = ("#9b2d2d", "#2d5a9b", "#c9c2b0", "#2f2f33", "#4f7d4a", "#b88a2a", "#6b6f78")


def car(cr, col, wrecked=False):
    # 128 x 72, facing right
    w, h = 120, 64
    x, y = 4, 4
    soft_shadow(cr, 64 + 4, 36 + 6, 64, 36, 0.55)
    cr.set_source_rgba(0.04, 0.04, 0.05, 1)
    for wx in (22, 92):
        for wy in (4, 60):
            rrect(cr, wx - 9, wy - 5, 18, 10, 3)
            cr.fill()
    rrect(cr, x, y, w, h, 16)
    g = cairo.LinearGradient(0, y, 0, y + h)
    g.add_color_stop_rgba(0, *rgb(shade(col, 0.3)))
    g.add_color_stop_rgba(0.5, *rgb(col))
    g.add_color_stop_rgba(1, *rgb(shade(col, -0.45)))
    cr.set_source(g)
    cr.fill_preserve()
    cr.set_source_rgba(0.05, 0.05, 0.05, 0.9)
    cr.set_line_width(2.5)
    cr.stroke()
    # glass and roof
    cr.set_source_rgba(*rgb("#1b2530"))
    rrect(cr, 74, 10, 20, 52, 6)
    cr.fill()
    rrect(cr, 22, 12, 14, 48, 5)
    cr.fill()
    g = cairo.LinearGradient(36, 0, 74, 0)
    g.add_color_stop_rgba(0, *rgb(shade(col, 0.15)))
    g.add_color_stop_rgba(1, *rgb(shade(col, -0.1)))
    cr.set_source(g)
    rrect(cr, 36, 12, 38, 48, 6)
    cr.fill()
    cr.set_source_rgba(1, 1, 1, 0.22)
    rrect(cr, 76, 13, 6, 46, 3)
    cr.fill()
    cr.set_source_rgba(1, 0.95, 0.75, 0.9)
    rrect(cr, 116, 10, 6, 10, 2)
    rrect(cr, 116, 52, 6, 10, 2)
    cr.fill()
    cr.set_source_rgba(0.7, 0.08, 0.08, 0.9)
    rrect(cr, 4, 10, 4, 10, 2)
    rrect(cr, 4, 52, 4, 10, 2)
    cr.fill()
    if wrecked:
        rng = random.Random(col)
        for _ in range(6):
            cr.set_source_rgba(0, 0, 0, 0.3)
            ellipse(cr, rng.uniform(20, 110), rng.uniform(12, 60), rng.uniform(4, 10), rng.uniform(3, 7))
            cr.fill()
        cr.set_source_rgba(0.85, 0.9, 0.95, 0.7)
        cr.set_line_width(1)
        for _ in range(5):
            cr.move_to(84, 36)
            cr.line_to(84 + rng.uniform(-9, 9), 36 + rng.uniform(-24, 24))
        cr.stroke()


def tree(cr, rng):
    # 160 x 160 canopy
    c = 80
    soft_shadow(cr, c + 10, c + 12, 70, 66, 0.5)
    cols = ("#24401f", "#2f5228", "#3c6532", "#4c7a3e")
    for k, col in enumerate(cols):
        r = 62 - k * 13
        for _ in range(7 - k):
            a = rng.uniform(0, TAU)
            d = rng.uniform(0, 18 - k * 3)
            ball(cr, c + math.cos(a) * d - k * 3, c + math.sin(a) * d - k * 3, r * rng.uniform(0.55, 0.75), col,
                 k == 0, 0.25, 0.35)


def crate(cr, harbor, col, rng):
    # 64 x 64
    soft_shadow(cr, 36, 38, 36, 36, 0.5)
    if harbor:
        g = cairo.LinearGradient(0, 0, 64, 64)
        g.add_color_stop_rgba(0, *rgb(shade(col, 0.2)))
        g.add_color_stop_rgba(1, *rgb(shade(col, -0.3)))
        cr.set_source(g)
        cr.rectangle(2, 2, 60, 60)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.set_line_width(2.5)
        for k in range(1, 6):
            cr.move_to(2 + k * 10, 4)
            cr.line_to(2 + k * 10, 60)
        cr.stroke()
        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.rectangle(2, 2, 60, 3)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.set_line_width(2)
        cr.rectangle(2, 2, 60, 60)
        cr.stroke()
    else:
        g = cairo.LinearGradient(0, 0, 64, 64)
        g.add_color_stop_rgba(0, *rgb(shade(col, 0.25)))
        g.add_color_stop_rgba(1, *rgb(shade(col, -0.3)))
        cr.set_source(g)
        cr.rectangle(4, 4, 56, 56)
        cr.fill()
        cr.set_source_rgba(*rgb(shade(col, -0.45)))
        cr.set_line_width(4)
        cr.rectangle(7, 7, 50, 50)
        cr.move_to(8, 8)
        cr.line_to(56, 56)
        cr.stroke()
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.set_line_width(2)
        cr.rectangle(4, 4, 56, 56)
        cr.stroke()
        for _ in range(12):
            cr.set_source_rgba(0, 0, 0, 0.1)
            cr.rectangle(rng.uniform(8, 50), rng.uniform(8, 50), rng.uniform(4, 12), 1)
            cr.fill()


def fence(cr):
    cr.set_source_rgba(0.72, 0.75, 0.78, 0.55)
    cr.set_line_width(1.2)
    for k in range(-64, 128, 9):
        cr.move_to(k, 0)
        cr.line_to(k + 64, 64)
        cr.move_to(k + 64, 0)
        cr.line_to(k, 64)
    cr.stroke()
    cr.set_source_rgba(0.45, 0.47, 0.5, 1)
    cr.set_line_width(4)
    cr.rectangle(2, 2, 60, 60)
    cr.stroke()
    for x, y in ((2, 2), (62, 2), (2, 62), (62, 62)):
        ball(cr, x, y, 4, "#8a8f96", True, 0.4, 0.4)


def generator(cr):
    soft_shadow(cr, 36, 40, 40, 36, 0.5)
    rrect(cr, 4, 8, 56, 48, 7)
    g = cairo.LinearGradient(0, 8, 0, 56)
    g.add_color_stop_rgba(0, *rgb("#e2b93a"))
    g.add_color_stop_rgba(1, *rgb("#9a7a16"))
    cr.set_source(g)
    cr.fill_preserve()
    cr.set_source_rgba(0.05, 0.05, 0.05, 0.9)
    cr.set_line_width(2.5)
    cr.stroke()
    cr.set_source_rgba(0.12, 0.12, 0.12, 1)
    rrect(cr, 12, 16, 40, 12, 3)
    cr.fill()
    for k in range(5):
        cr.rectangle(13 + k * 8, 34, 4, 16)
    cr.fill()
    cr.set_source_rgba(0.2, 1, 0.5, 1)
    circle(cr, 50, 22, 3)
    cr.fill()


def pickup(cr, kind):
    c = 32
    soft_shadow(cr, c + 2, c + 5, 22, 18, 0.5)
    if kind == "medkit":
        rrect(cr, 12, 16, 40, 32, 6)
        g = cairo.LinearGradient(0, 16, 0, 48)
        g.add_color_stop_rgba(0, 1, 1, 1, 1)
        g.add_color_stop_rgba(1, 0.78, 0.8, 0.82, 1)
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.9)
        cr.set_line_width(2)
        cr.stroke()
        cr.set_source_rgba(*rgb("#d42c2c"))
        cr.rectangle(28, 20, 8, 24)
        cr.rectangle(20, 28, 24, 8)
        cr.fill()
    elif kind == "ammo":
        rrect(cr, 12, 18, 40, 28, 4)
        g = cairo.LinearGradient(0, 18, 0, 46)
        g.add_color_stop_rgba(0, *rgb("#6e8238"))
        g.add_color_stop_rgba(1, *rgb("#3f4c1e"))
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.9)
        cr.set_line_width(2)
        cr.stroke()
        for k in range(4):
            g = cairo.LinearGradient(17 + k * 8, 0, 22 + k * 8, 0)
            g.add_color_stop_rgba(0, *rgb("#f2d16b"))
            g.add_color_stop_rgba(1, *rgb("#a87c1c"))
            cr.set_source(g)
            rrect(cr, 17 + k * 8, 12, 5, 22, 2)
            cr.fill()
    elif kind == "fuel":
        rrect(cr, 16, 12, 32, 40, 6)
        g = cairo.LinearGradient(16, 0, 48, 0)
        g.add_color_stop_rgba(0, *rgb("#e8402c"))
        g.add_color_stop_rgba(1, *rgb("#8a1a10"))
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(0.1, 0.05, 0.05, 0.9)
        cr.set_line_width(2)
        cr.stroke()
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.set_line_width(3)
        cr.move_to(21, 20)
        cr.line_to(43, 44)
        cr.move_to(43, 20)
        cr.line_to(21, 44)
        cr.stroke()
        cr.set_source_rgba(*rgb("#e0b030"))
        rrect(cr, 36, 6, 8, 8, 2)
        cr.fill()
    elif kind == "grenade":
        ball(cr, 32, 34, 13, "#4f5e2c", True, 0.4, 0.4)
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.set_line_width(1.5)
        for k in (-6, 0, 6):
            cr.move_to(20, 34 + k)
            cr.line_to(44, 34 + k)
        cr.stroke()
        cr.set_source_rgba(*rgb("#9a9a9a"))
        rrect(cr, 28, 16, 9, 8, 2)
        cr.fill()


def splat(cr, size, rng, col, n=11):
    r, g, b, a = col
    cx = size / 2
    for _ in range(n):
        x, y = cx + rng.gauss(0, size * 0.13), cx + rng.gauss(0, size * 0.13)
        rad = rng.uniform(size * 0.04, size * 0.15)
        grad = cairo.RadialGradient(x, y, 0, x, y, rad)
        grad.add_color_stop_rgba(0, r, g, b, a)
        grad.add_color_stop_rgba(0.8, r * 0.8, g * 0.8, b * 0.8, a)
        grad.add_color_stop_rgba(1, r, g, b, 0)
        cr.set_source(grad)
        circle(cr, x, y, rad)
        cr.fill()
    for _ in range(8):
        a2 = rng.uniform(0, TAU)
        d = rng.uniform(size * 0.2, size * 0.45)
        cr.set_source_rgba(r, g, b, a)
        circle(cr, cx + math.cos(a2) * d, cx + math.sin(a2) * d, rng.uniform(1, size * 0.03))
        cr.fill()


def soft(cr, size, col, hard=0.0, a=1.0):
    r, g, b, _ = rgb(col)
    grad = cairo.RadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    grad.add_color_stop_rgba(0, r, g, b, a)
    if hard:
        grad.add_color_stop_rgba(hard, r, g, b, a * 0.8)
    grad.add_color_stop_rgba(1, r, g, b, 0)
    cr.set_source(grad)
    cr.paint()


def light_round(cr, size):
    grad = cairo.RadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    for t, a in ((0, 1), (0.25, 0.75), (0.55, 0.32), (0.8, 0.09), (1, 0)):
        grad.add_color_stop_rgba(t, 1, 1, 1, a)
    cr.set_source(grad)
    cr.paint()


def light_cone(cr, size, spread=0.42):
    """A torch beam pointing right from the centre, soft at the sides and the far end."""
    c = size / 2
    for k in range(24):
        t = k / 23
        half = spread * (1 - t * 0.35)
        a = 0.055 * (1 - t * 0.6)
        cr.move_to(c, c)
        cr.arc(c, c, c * (0.35 + 0.65 * (1 - t * 0.0)), -half * (0.4 + 0.6 * (1 - t)), half * (0.4 + 0.6 * (1 - t)))
        cr.close_path()
        grad = cairo.RadialGradient(c, c, 0, c, c, c)
        grad.add_color_stop_rgba(0, 1, 1, 1, a * 1.6)
        grad.add_color_stop_rgba(0.6, 1, 1, 1, a)
        grad.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(grad)
        cr.fill()


def muzzle(cr, size, rng):
    c = size / 2
    cr.translate(c * 0.3, c)
    for k in range(3):
        r, g, b = (1, 0.95, 0.7) if k == 2 else (1, 0.7 - k * 0.1, 0.2)
        cr.set_source_rgba(r, g, b, 0.75 + k * 0.1)
        cr.move_to(0, 0)
        ln = size * (0.62 - k * 0.15)
        w = size * (0.16 - k * 0.04)
        cr.line_to(ln * 0.5, -w)
        cr.line_to(ln, 0)
        cr.line_to(ln * 0.5, w)
        cr.close_path()
        cr.fill()
    for _ in range(5):
        a = rng.uniform(-0.9, 0.9)
        cr.set_source_rgba(1, 0.85, 0.4, 0.8)
        cr.move_to(0, 0)
        cr.line_to(math.cos(a) * size * 0.4, math.sin(a) * size * 0.4)
        cr.set_line_width(2)
        cr.stroke()


def fog(size, rng):
    """A tileable cloud texture for fog and smoke, from layered soft blobs wrapped at the edges."""
    s, cr = surface(size, size)
    for _ in range(140):
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        r = rng.uniform(size * 0.05, size * 0.2)
        a = rng.uniform(0.04, 0.12)
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                g = cairo.RadialGradient(x + dx, y + dy, 0, x + dx, y + dy, r)
                g.add_color_stop_rgba(0, 1, 1, 1, a)
                g.add_color_stop_rgba(1, 1, 1, 1, 0)
                cr.set_source(g)
                circle(cr, x + dx, y + dy, r)
                cr.fill()
    return s


def main():
    os.makedirs(OUT, exist_ok=True)
    for key, look in SURVIVORS.items():
        sheet(f"people/{key}.png", FRAMES, CELL, lambda cr, i, look=look: survivor_frame(cr, look, i / FRAMES * TAU))
    for kind in ZOMBIES:
        cell = 256 if kind == "tank" else CELL * (2 if kind in ("brute", "bloater") else 1)
        sheet(f"dead/{kind}.png", FRAMES + 1, cell,
              lambda cr, i, kind=kind, cell=cell: zombie_frame(cr, kind, i / FRAMES * TAU, cell * (1 if cell == CELL else 1), i == FRAMES))
    for w in ("pistol", "shotgun", "smg", "rifle", "flamer", "crossbow"):
        s, cr = surface(CELL, CELL)
        gun(cr, w)
        save(s, f"guns/{w}.png")
    for th in THEMES:
        atlas(th)
    for i, col in enumerate(CAR_COLOURS):
        s, cr = surface(128, 72)
        car(cr, col, wrecked=i % 2 == 1)
        save(s, f"props/car{i}.png")
    rng = random.Random(9)
    for i in range(3):
        s, cr = surface(160, 160)
        tree(cr, rng)
        save(s, f"props/tree{i}.png")
    for i, col in enumerate(("#8b6a3e", "#9a4a32", "#2f6b8a", "#7b8a3a", "#b58a2a")):
        s, cr = surface(64, 64)
        crate(cr, i > 0, col, rng)
        save(s, f"props/crate{i}.png")
    s, cr = surface(64, 64)
    fence(cr)
    save(s, "props/fence.png")
    s, cr = surface(64, 64)
    generator(cr)
    save(s, "props/generator.png")
    for k in ("medkit", "ammo", "fuel", "grenade"):
        s, cr = surface(64, 64)
        pickup(cr, k)
        save(s, f"pickups/{k}.png")
    for i in range(6):
        s, cr = surface(96, 96)
        splat(cr, 96, rng, (0.42, 0.02, 0.02, 0.9))
        save(s, f"fx/blood{i}.png")
    for i in range(2):
        s, cr = surface(96, 96)
        splat(cr, 96, rng, (0.45, 0.68, 0.1, 0.85))
        save(s, f"fx/goo{i}.png")
    s, cr = surface(128, 128)
    splat(cr, 128, rng, (0.05, 0.04, 0.03, 0.75), 16)
    save(s, "fx/scorch.png")
    for name, col, hard in (("spark", "#ffe08a", 0.15), ("fire", "#ff8a2a", 0.25), ("smoke", "#5a5a5a", 0.0),
                            ("dot", "#ffffff", 0.5), ("glow", "#ffffff", 0.0)):
        s, cr = surface(64, 64)
        soft(cr, 64, col, hard)
        save(s, f"fx/{name}.png")
    s, cr = surface(12, 6)
    cr.set_source_rgba(*rgb("#d9a83a"))
    rrect(cr, 0, 0, 12, 6, 2)
    cr.fill()
    save(s, "fx/shell.png")
    for i in range(3):
        s, cr = surface(96, 96)
        muzzle(cr, 96, rng)
        save(s, f"fx/muzzle{i}.png")
    s, cr = surface(512, 512)
    light_round(cr, 512)
    save(s, "light/round.png")
    s, cr = surface(1024, 1024)
    light_cone(cr, 1024)
    save(s, "light/cone.png")
    save(fog(512, rng), "fx/fog.png")
    s, cr = surface(4, 32)
    g = cairo.LinearGradient(0, 0, 0, 32)
    g.add_color_stop_rgba(0, 0.75, 0.82, 0.95, 0)
    g.add_color_stop_rgba(1, 0.75, 0.82, 0.95, 0.55)
    cr.set_source(g)
    cr.paint()
    save(s, "fx/rain.png")
    print("art written to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
