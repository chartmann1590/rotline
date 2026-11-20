# SPDX-License-Identifier: GPL-3.0-or-later
"""Rotline's sound: every effect is made here from noise and tones (no sound files), mixed in a few lines of
Python and played through one GStreamer stream (appsrc → the system's audio).

One stream, not one player per shot: shots come ten a second, and a fresh player each time is slow to start.
Without GStreamer or an audio device the game is silent and carries on.
"""
from __future__ import annotations

import math
import os
import random
import threading
from array import array
from itertools import zip_longest

RATE = 22050
BLOCK = 441          # 20 ms
MAX_VOICES = 10


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


# How often each may start again (seconds): shots fire fast, the dead shouldn't all moan at once.
GAP = {"smg": 0.06, "flame": 0.1, "hit": 0.05, "splat": 0.07, "groan": 0.8, "pickup": 0.05, "clang": 0.25}


class Sound:
    def __init__(self, volume: float = 0.8, enabled: bool = True):
        self.enabled = enabled
        self.volume = volume
        self.voices: list[list] = []        # [samples, position]
        self.samples: dict[str, array] = {}
        self._raw: dict[str, list[float]] = {}
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self.pipe = None
        self.src = None
        self.clock = 0.0
        threading.Thread(target=self._build, daemon=True).start()

    def _build(self):
        try:
            self._raw = make_all()
            self._scale()
            self._start_stream()
        except Exception as ex:  # no audio: play on in silence
            print("rotline: no sound:", ex)

    def _scale(self):
        v = max(0.0, min(1.0, self.volume))
        with self._lock:
            self.samples = {k: array("h", (int(max(-1, min(1, x * v)) * 30000) for x in raw))
                            for k, raw in self._raw.items()}

    def set_volume(self, v: float):
        self.volume = v
        if self._raw:
            threading.Thread(target=self._scale, daemon=True).start()

    def _start_stream(self):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        self.Gst = Gst
        sink_name = os.environ.get("ROTLINE_AUDIO_SINK", "")
        pipe = Gst.Pipeline.new("rotline-sound")
        src = Gst.ElementFactory.make("appsrc", "src")
        conv = Gst.ElementFactory.make("audioconvert", None)
        res = Gst.ElementFactory.make("audioresample", None)
        sink = None
        if sink_name:
            sink = Gst.ElementFactory.make(sink_name, None)
            if sink is not None and sink.find_property("sync") is not None:
                sink.set_property("sync", True)   # a test sink keeps real time, like a sound card
        if sink is None:
            sink = Gst.ElementFactory.make("pulsesink", None)
            if sink is not None:
                sink.set_property("buffer-time", 60000)
                sink.set_property("latency-time", 10000)
        if sink is None:
            sink = Gst.ElementFactory.make("autoaudiosink", None)
        if None in (src, conv, res, sink):
            raise RuntimeError("GStreamer elements missing")
        caps = Gst.Caps.from_string(f"audio/x-raw,format=S16LE,rate={RATE},channels=1,layout=interleaved")
        src.set_property("caps", caps)
        src.set_property("format", Gst.Format.TIME)
        src.set_property("is-live", True)
        src.set_property("block", False)
        src.set_property("max-bytes", BLOCK * 2 * 3)
        src.connect("need-data", self._need)
        for e in (src, conv, res, sink):
            pipe.add(e)
        src.link(conv)
        conv.link(res)
        res.link(sink)
        self.pipe, self.src = pipe, src
        self._pts = 0
        pipe.set_state(Gst.State.PLAYING)

    def _need(self, src, _length):
        Gst = self.Gst
        with self._lock:
            parts = []
            keep = []
            for v in self.voices:
                smp, pos = v
                parts.append(smp[pos:pos + BLOCK])
                v[1] = pos + BLOCK
                if v[1] < len(smp):
                    keep.append(v)
            self.voices = keep
        if parts:
            mixed = array("h", (max(-32767, min(32767, x)) for x in map(sum, zip_longest(*parts, fillvalue=0))))
            if len(mixed) < BLOCK:
                mixed.extend([0] * (BLOCK - len(mixed)))
        else:
            mixed = array("h", bytes(BLOCK * 2))
        buf = Gst.Buffer.new_wrapped(mixed.tobytes())
        dur = Gst.SECOND * BLOCK // RATE
        buf.pts = self._pts
        buf.duration = dur
        self._pts += dur
        src.emit("push-buffer", buf)

    def play(self, name: str, now: float):
        if not self.enabled or self.src is None:
            return
        gap = GAP.get(name, 0.03)
        if now - self._last.get(name, -9) < gap:
            return
        smp = self.samples.get(name)
        if smp is None:
            return
        self._last[name] = now
        with self._lock:
            if len(self.voices) >= MAX_VOICES:
                self.voices.pop(0)
            self.voices.append([smp, 0])

    def stop(self):
        if self.pipe is not None:
            self.pipe.set_state(self.Gst.State.NULL)
            self.pipe = None
            self.src = None
