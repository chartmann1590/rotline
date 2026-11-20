#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Makes every sound in Rotline from noise and tones, into game/assets/sfx/*.wav, plus the music loops.

    python3 tools/make_sounds.py

No recordings: everything here is synthesised, so it is all ours to licence.
"""
from __future__ import annotations

import math
import os
import random
import struct
import wave

RATE = 22050
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "game", "assets", "sfx")


def _env(n, attack, decay):
    a = max(1, int(attack * RATE))
    return [min(1.0, i / a) * math.exp(-i / RATE * decay) for i in range(n)]


def _noise(rng, n):
    return [rng.uniform(-1, 1) for _ in range(n)]


def _lowpass(x, k):
    out, y = [], 0.0
    for v in x:
        y += (v - y) * k
        out.append(y)
    return out


def _tone(n, f0, f1=None, wave="sin"):
    f1 = f0 if f1 is None else f1
    out, ph = [], 0.0
    for i in range(n):
        f = f0 + (f1 - f0) * i / n
        ph += 2 * math.pi * f / RATE
        if wave == "sin":
            out.append(math.sin(ph))
        elif wave == "saw":
            out.append(((ph / math.pi) % 2) - 1)
        else:
            out.append(1.0 if math.sin(ph) > 0 else -1.0)
    return out


def _mix(*parts):
    n = max(len(p) for p in parts)
    return [sum(p[i] for p in parts if i < len(p)) for i in range(n)]


def _shot(rng, length, cut, decay, boom, gain):
    n = int(length * RATE)
    noise = _lowpass(_noise(rng, n), cut)
    env = _env(n, 0.001, decay)
    thump = _tone(n, boom, boom * 0.4)
    return [(noise[i] * 1.0 + thump[i] * 0.6) * env[i] * gain for i in range(n)]


def make_all(seed: int = 7) -> dict[str, list[float]]:
    rng = random.Random(seed)
    s: dict[str, list[float]] = {}
    s["pistol"] = _shot(rng, 0.22, 0.55, 22, 160, 0.55)
    s["smg"] = _shot(rng, 0.12, 0.6, 35, 190, 0.38)
    s["shotgun"] = _shot(rng, 0.5, 0.35, 9, 90, 0.8)
    s["rifle"] = _shot(rng, 0.45, 0.7, 11, 120, 0.7)
    n = int(0.25 * RATE)
    s["crossbow"] = [v * e * 0.5 for v, e in zip(_tone(n, 320, 140, "saw"), _env(n, 0.002, 18))]
    n = int(0.12 * RATE)
    s["flame"] = [v * 0.22 * (1 - i / n) for i, v in enumerate(_lowpass(_noise(rng, n), 0.18))]
    n = int(0.09 * RATE)
    s["hit"] = [v * e * 0.35 for v, e in zip(_lowpass(_noise(rng, n), 0.12), _env(n, 0.002, 40))]
    n = int(0.3 * RATE)
    s["splat"] = [(a * 0.5 + b * 0.4) * e * 0.5 for a, b, e in
                  zip(_lowpass(_noise(rng, n), 0.08), _tone(n, 120, 50), _env(n, 0.003, 14))]
    n = int(0.9 * RATE)
    s["boom"] = [(a + b * 0.8) * e * 0.85 for a, b, e in
                 zip(_lowpass(_noise(rng, n), 0.05), _tone(n, 70, 30), _env(n, 0.004, 5))]
    for name, f, length in (("groan", 95, 1.1), ("roar", 60, 1.0)):
        n = int(length * RATE)
        base = _tone(n, f, f * 0.75, "saw")
        wob = [1 + 0.25 * math.sin(2 * math.pi * 5.5 * i / RATE) for i in range(n)]
        env = [math.sin(math.pi * i / n) for i in range(n)]
        filt = _lowpass([b * w for b, w in zip(base, wob)], 0.09)
        rough = _lowpass(_noise(rng, n), 0.05)
        g = 0.55 if name == "groan" else 1.0
        s[name] = [(a * 1.6 + r * 0.6) * e * g for a, r, e in zip(filt, rough, env)]
    n = int(0.25 * RATE)
    s["hurt"] = [(a * 0.6 + b * 0.3) * e * 0.6 for a, b, e in
                 zip(_tone(n, 220, 140, "square"), _lowpass(_noise(rng, n), 0.2), _env(n, 0.002, 10))]
    n = int(0.18 * RATE)
    s["pickup"] = [v * e * 0.3 for v, e in zip(_mix(_tone(n, 660, 990), _tone(n, 990, 1320)), _env(n, 0.003, 12))]
    n = int(0.06 * RATE)
    s["switch"] = [v * e * 0.3 for v, e in zip(_tone(n, 1400, 900, "square"), _env(n, 0.001, 60))]
    s["empty"] = [v * e * 0.25 for v, e in zip(_tone(n, 800, 700, "square"), _env(n, 0.001, 80))]
    n = int(0.3 * RATE)
    s["spit"] = [v * e * 0.35 for v, e in zip(_lowpass(_noise(rng, n), 0.3), _env(n, 0.01, 12))]
    n = int(0.2 * RATE)
    s["clang"] = [v * e * 0.35 for v, e in zip(_mix(_tone(n, 520), _tone(n, 1310)), _env(n, 0.001, 18))]
    notes = (523.3, 659.3, 784.0, 1046.5)
    win = []
    for k, f in enumerate(notes):
        n = int(0.16 * RATE) if k < 3 else int(0.7 * RATE)
        win += [v * e * 0.35 for v, e in zip(_mix(_tone(n, f), [0.3 * x for x in _tone(n, f * 2)]), _env(n, 0.005, 5))]
    s["win"] = win
    lose = []
    for f in (392.0, 349.2, 311.1, 233.1):
        n = int(0.3 * RATE)
        lose += [v * e * 0.35 for v, e in zip(_tone(n, f, f * 0.98, "saw"), _env(n, 0.01, 4))]
    s["lose"] = _lowpass(lose, 0.25)
    return s




def extra(s, rng):
    n = int(0.35 * RATE)
    s["dodge"] = [v * (math.sin(math.pi * i / n) ** 2) * 0.35 for i, v in enumerate(_lowpass(_noise(rng, n), 0.25))]
    n = int(2.6 * RATE)
    boom = _lowpass(_noise(rng, n), 0.03)
    s["thunder"] = [v * math.exp(-i / RATE * 1.2) * min(1, i / (0.05 * RATE)) * 2.2 for i, v in enumerate(boom)]
    n = int(0.05 * RATE)
    s["ui_move"] = [v * e * 0.18 for v, e in zip(_tone(n, 900, 1100), _env(n, 0.002, 50))]
    n = int(0.12 * RATE)
    s["ui_ok"] = [v * e * 0.25 for v, e in zip(_mix(_tone(n, 660, 880), _tone(n, 990, 1320)), _env(n, 0.002, 25))]
    n = int(0.08 * RATE)
    s["pin"] = [v * e * 0.3 for v, e in zip(_tone(n, 2400, 1800, "square"), _env(n, 0.001, 50))]
    n = int(1.2 * RATE)
    horn = _mix(_tone(n, 110, 104, "saw"), [0.6 * x for x in _tone(n, 164.8, 156, "saw")])
    s["wave"] = [v * min(1, i / (0.08 * RATE)) * max(0, 1 - i / n) * 0.35 for i, v in enumerate(_lowpass(horn, 0.08))]
    n = int(0.5 * RATE)
    s["heart"] = [v * e * 0.9 for v, e in zip(_mix(_tone(n, 55, 40), [0] * int(0.18 * RATE) + _tone(n, 50, 38)), _env(n, 0.005, 9))]


def music(rng, seconds, root, dark):
    """A slow, uneasy pad: two detuned saws through a moving filter, a low pulse, and far-off metal."""
    n = int(seconds * RATE)
    out = [0.0] * n
    chord = [root, root * 1.189, root * 1.498] if not dark else [root, root * 1.059, root * 1.414]
    for f in chord:
        for det in (0.997, 1.003):
            ph = rng.random() * 6.28
            y = 0.0
            for i in range(n):
                t = i / RATE
                ph += 2 * math.pi * f * det / RATE
                v = ((ph / math.pi) % 2) - 1
                k = 0.02 + 0.015 * math.sin(2 * math.pi * t / seconds * 2 + f)
                y += (v - y) * k
                out[i] += y * 0.11
    beat = 60 / 52
    for b in range(int(seconds / beat)):
        s0 = int(b * beat * RATE)
        for i in range(int(0.4 * RATE)):
            if s0 + i < n:
                t = i / RATE
                out[s0 + i] += math.sin(2 * math.pi * (48 - 20 * t) * t) * math.exp(-t * 9) * 0.25
    for _ in range(int(seconds / 6)):
        s0 = rng.randrange(0, n - RATE * 2)
        f = rng.choice((622, 830, 1245))
        for i in range(int(1.8 * RATE)):
            t = i / RATE
            out[s0 + i] += math.sin(2 * math.pi * f * t) * math.sin(2 * math.pi * f * 2.76 * t) * math.exp(-t * 2.5) * 0.04
    # loop seamlessly: fade the tail into the head
    x = int(1.5 * RATE)
    for i in range(x):
        a = i / x
        out[i] = out[i] * a + out[n - x + i] * (1 - a)
    return out[: n - x]


def write(name, samples):
    os.makedirs(OUT, exist_ok=True)
    peak = max(1e-6, max(abs(v) for v in samples))
    g = min(1.0, 0.95 / peak)
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v * g)) * 32000)) for v in samples))


def main():
    rng = random.Random(7)
    s = make_all()
    extra(s, rng)
    for k, v in s.items():
        write(k, v)
    write("music_menu", music(rng, 40, 55.0, False))
    write("music_play", music(rng, 40, 49.0, True))
    print("sounds written to", os.path.normpath(OUT), len(s) + 2)


if __name__ == "__main__":
    main()
