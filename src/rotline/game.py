# SPDX-License-Identifier: GPL-3.0-or-later
"""Rotline's world: the survivor, the dead, shots, pickups and goals. No GTK, so it is unit tested.

The world runs in fixed steps of 1/60 s whatever the screen does. It never draws or plays anything itself: it
appends what happened to `events` (("sound", name), ("blood", x, y, angle), ...) and the window turns those into
pictures and sounds.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from . import levels as L

STEP = 1 / 60
SOLID = set("#ctx~fG")        # can't walk through
BLOCKS_SHOTS = set("#ctxG")   # shots stop (fences and water don't)
WALL_RADIUS = 0.42            # the big ones squeeze through doors like everyone else


@dataclass(frozen=True)
class Weapon:
    key: str
    name: str
    rate: float          # seconds between shots
    damage: float
    pellets: int
    spread: float        # radians either side
    speed: float         # tiles a second
    range: float         # tiles
    pierce: int          # how many it goes through after the first
    ammo: int            # start; 0 is unlimited
    max_ammo: int
    pickup: int          # from an ammo box
    knock: float
    sound: str
    shot: str = "bullet"  # bullet, flame, bolt
    extra: bool = False   # comes with the Arsenal pack


WEAPONS = {
    "pistol": Weapon("pistol", "Pistol", 0.30, 15, 1, 0.035, 24, 11, 0, 0, 0, 0, 0.25, "pistol"),
    "shotgun": Weapon("shotgun", "Shotgun", 0.85, 12, 7, 0.30, 22, 7, 0, 24, 48, 10, 0.55, "shotgun"),
    "smg": Weapon("smg", "SMG", 0.085, 8, 1, 0.09, 26, 10, 0, 160, 320, 70, 0.12, "smg"),
    "rifle": Weapon("rifle", "Rifle", 0.6, 60, 1, 0.006, 36, 18, 3, 24, 50, 10, 0.6, "rifle"),
    "flamer": Weapon("flamer", "Flamethrower", 0.045, 3.2, 1, 0.22, 9, 4.6, 99, 260, 520, 120, 0.02, "flame",
                     shot="flame", extra=True),
    "crossbow": Weapon("crossbow", "Crossbow", 0.7, 95, 1, 0.004, 28, 16, 8, 24, 48, 10, 0.9, "crossbow",
                       shot="bolt", extra=True),
}
ORDER = ("pistol", "shotgun", "smg", "rifle", "flamer", "crossbow")


@dataclass(frozen=True)
class Kind:
    key: str
    name: str
    hp: float
    speed: float
    radius: float
    damage: float
    scrap: int
    mass: float = 1.0


KINDS = {
    "walker": Kind("walker", "Walker", 32, 1.25, 0.36, 11, 1),
    "runner": Kind("runner", "Runner", 22, 2.85, 0.32, 8, 2, 0.8),
    "brute": Kind("brute", "Brute", 175, 1.0, 0.52, 24, 5, 3.0),
    "spitter": Kind("spitter", "Spitter", 42, 1.4, 0.36, 9, 3),
    "bloater": Kind("bloater", "Bloater", 46, 1.05, 0.46, 30, 3, 1.6),
    "tank": Kind("tank", "Tank", 2200, 1.15, 0.78, 30, 60, 12.0),
}

# upgrades bought with scrap: (name, what each level does)
UPGRADES = {
    "health": ("Toughness", "+15 health"),
    "damage": ("Firepower", "+10% damage"),
    "rate": ("Trigger finger", "+8% fire rate"),
    "speed": ("Running shoes", "+5% speed"),
    "ammo": ("Deep pockets", "+20% ammo"),
}
UPGRADE_COSTS = (30, 60, 100, 160, 240)
MAX_UPGRADE = len(UPGRADE_COSTS)


def upgrade_cost(level: int) -> int | None:
    return UPGRADE_COSTS[level] if 0 <= level < MAX_UPGRADE else None


def stars_for(fraction: float) -> int:
    return 3 if fraction >= 0.75 else 2 if fraction >= 0.4 else 1


class Input:
    """What the person is doing this moment. `aim` is an angle in radians, or None to aim for them."""

    __slots__ = ("mx", "my", "aim", "fire", "auto_fire")

    def __init__(self, mx=0.0, my=0.0, aim=None, fire=False, auto_fire=True):
        self.mx, self.my, self.aim, self.fire, self.auto_fire = mx, my, aim, fire, auto_fire


class Player:
    __slots__ = ("x", "y", "angle", "hp", "max_hp", "speed", "weapon", "ammo", "cool", "hurt", "radius", "walk",
                 "shots", "hits", "medkits", "target")

    def __init__(self, x, y, max_hp, speed):
        self.x, self.y, self.angle = x, y, 0.0
        self.hp = self.max_hp = max_hp
        self.speed = speed
        self.weapon = "pistol"
        self.ammo: dict[str, int] = {}
        self.cool = 0.0
        self.hurt = 0.0
        self.radius = 0.34
        self.walk = 0.0
        self.shots = self.hits = self.medkits = 0
        self.target = None


class Zombie:
    __slots__ = ("id", "kind", "x", "y", "vx", "vy", "hp", "max_hp", "angle", "cool", "spit", "burn", "flash", "los",
                 "los_t", "state", "state_t", "cx", "cy", "boss", "walk", "goes_for_gen", "lx", "ly", "stuck", "check")

    def __init__(self, zid, kind: Kind, x, y, hp_mult=1.0, boss=False):
        self.id, self.kind, self.x, self.y = zid, kind, x, y
        self.vx = self.vy = 0.0
        self.hp = self.max_hp = kind.hp * hp_mult
        self.angle = 0.0
        self.cool = 0.5
        self.spit = 1.5
        self.burn = 0.0
        self.flash = 0.0
        self.los = False
        self.los_t = (zid % 7) * 0.04
        self.state = "walk"      # walk, windup, charge (the tank)
        self.state_t = 3.0
        self.cx = self.cy = 0.0
        self.boss = boss
        self.walk = random.random() * 6
        self.goes_for_gen = zid % 3 == 0
        self.lx, self.ly = x, y
        self.stuck = 0.0
        self.check = 2.0 + (zid % 5) * 0.3


class Shot:
    __slots__ = ("x", "y", "dx", "dy", "speed", "damage", "life", "pierce", "hostile", "kind", "hit", "knock", "age")

    def __init__(self, x, y, angle, speed, damage, life, pierce, hostile=False, kind="bullet", knock=0.0):
        self.x, self.y = x, y
        self.dx, self.dy = math.cos(angle), math.sin(angle)
        self.speed, self.damage, self.life, self.pierce = speed, damage, life, pierce
        self.hostile, self.kind, self.knock = hostile, kind, knock
        self.hit: set[int] = set()
        self.age = 0.0


class Pickup:
    __slots__ = ("kind", "x", "y", "bob")

    def __init__(self, kind, x, y):
        self.kind, self.x, self.y = kind, x, y
        self.bob = random.random() * 6


class World:
    """One attempt at a level. `upgrades` {name: level}; `weapons` the weapons you have; `easy` halves the
    damage you take (Story mode)."""

    def __init__(self, level: L.Level, *, upgrades: dict | None = None, weapons=("pistol",), seed: int | None = None,
                 easy: bool = False):
        self.level = level
        self.rng = random.Random(seed)
        up = {k: max(0, min(MAX_UPGRADE, int((upgrades or {}).get(k, 0)))) for k in UPGRADES}
        self.dmg_mult = 1 + 0.10 * up["damage"]
        self.rate_mult = 1 / (1 + 0.08 * up["rate"])
        self.ammo_mult = 1 + 0.20 * up["ammo"]
        self.hurt_mult = 0.5 if easy else 1.0
        self.grid: list[list[str]] = []
        self.spawns: list[tuple[float, float]] = []
        self.exits: set[tuple[int, int]] = set()
        self.gen: tuple[float, float] | None = None
        self.pickups: list[Pickup] = []
        start = (1.5, 1.5)
        for j, row in enumerate(level.rows):
            out = []
            for i, ch in enumerate(row):
                cx, cy = i + 0.5, j + 0.5
                if ch == "P":
                    start = (cx, cy)
                elif ch == "S":
                    self.spawns.append((cx, cy))
                elif ch == "E":
                    self.exits.add((i, j))
                elif ch == "F":
                    self.pickups.append(Pickup("fuel", cx, cy))
                elif ch == "h":
                    self.pickups.append(Pickup("medkit", cx, cy))
                elif ch == "a":
                    self.pickups.append(Pickup("ammo", cx, cy))
                elif ch == "G":
                    self.gen = (cx, cy)
                    out.append("G")
                    continue
                out.append(ch if ch in "#ctx~f.,=" else self._floor_near(level.rows, i, j))
            self.grid.append(out)
        self.h = len(self.grid)
        self.w = len(self.grid[0])
        self.player = Player(start[0], start[1], 100 + 15 * up["health"], 4.0 * (1 + 0.05 * up["speed"]))
        self.weapons = [w for w in ORDER if w in weapons and w in WEAPONS] or ["pistol"]
        for w in self.weapons:
            spec = WEAPONS[w]
            if spec.ammo:
                self.player.ammo[w] = int(spec.ammo * self.ammo_mult)
        self.zombies: list[Zombie] = []
        self.shots: list[Shot] = []
        self.events: list[tuple] = []
        self.time = 0.0
        self.kills = 0
        self.scrap = 0
        self.spawned = 0
        self.fuel = 0
        self.fuel_needed = level.target if level.goal == "escape" else 0
        self.gen_hp = self.gen_max = float(level.gen_hp) if self.gen else 0.0
        self.bosses_left = level.bosses
        self.state = "play"       # play, won, lost
        self.why = ""             # why it ended
        self._acc = 0.0
        self._spawn_acc = 0.0
        self._next_id = 1
        self._field: list[list[int]] = []
        self._gen_field: list[list[int]] = []
        self._field_t = 0.0
        self._next_tank = 150.0
        self._groan = 2.0
        self._refield()
        if self.gen:
            self._gen_field = self._bfs(int(self.gen[0]), int(self.gen[1]), around=True)
        for _ in range(level.bosses):
            self._spawn(KINDS["tank"], boss=True)

    @staticmethod
    def _floor_near(rows, i, j) -> str:
        for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            jj, ii = j + dj, i + di
            if 0 <= jj < len(rows) and 0 <= ii < len(rows[jj]) and rows[jj][ii] in ".,=":
                return rows[jj][ii]
        return "."

    # ------------------------------------------------------------------ the grid
    def solid(self, i: int, j: int) -> bool:
        return not (0 <= i < self.w and 0 <= j < self.h) or self.grid[j][i] in SOLID

    def blocks(self, i: int, j: int) -> bool:
        return not (0 <= i < self.w and 0 <= j < self.h) or self.grid[j][i] in BLOCKS_SHOTS

    def clear_line(self, x0, y0, x1, y1) -> bool:
        """True when nothing that stops shots is between the two points."""
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(dist * 3))
        for k in range(1, n):
            t = k / n
            if self.blocks(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)):
                return False
        return True

    def _bfs(self, si: int, sj: int, around: bool = False) -> list[list[int]]:
        far = 1 << 20
        dist = [[far] * self.w for _ in range(self.h)]
        q = deque()
        starts = [(si, sj)]
        if around:   # the generator is solid: start from the tiles around it
            starts = [(si + a, sj + b) for a in (-1, 0, 1) for b in (-1, 0, 1) if (a or b)]
        for i, j in starts:
            if 0 <= i < self.w and 0 <= j < self.h and not self.solid(i, j):
                dist[j][i] = 0
                q.append((i, j))
        while q:
            i, j = q.popleft()
            d = dist[j][i] + 1
            for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ii, jj = i + a, j + b
                if 0 <= ii < self.w and 0 <= jj < self.h and dist[jj][ii] > d and self.grid[jj][ii] not in SOLID:
                    dist[jj][ii] = d
                    q.append((ii, jj))
        return dist

    def _refield(self):
        p = self.player
        self._field = self._bfs(int(p.x), int(p.y))

    def reachable(self, x: float, y: float) -> bool:
        return self._field[int(y)][int(x)] < (1 << 20)

    def _follow(self, field, x, y) -> tuple[float, float]:
        """Which way to walk to get closer along a distance field."""
        i, j = int(x), int(y)
        best, bx, by = field[j][i] if 0 <= j < self.h and 0 <= i < self.w else 1 << 20, 0.0, 0.0
        for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ii, jj = i + a, j + b
            if not (0 <= ii < self.w and 0 <= jj < self.h):
                continue
            if a and b and (self.solid(i + a, j) or self.solid(i, j + b)):
                continue   # no cutting corners
            d = field[jj][ii] + (0.4 if a and b else 0)
            if d < best:
                best, bx, by = d, ii + 0.5 - x, jj + 0.5 - y
        n = math.hypot(bx, by)
        return (bx / n, by / n) if n > 1e-6 else (0.0, 0.0)

    def _collide(self, x: float, y: float, r: float) -> tuple[float, float]:
        """Push a circle out of solid tiles."""
        for _ in range(2):
            for j in range(int(y - r) - 1, int(y + r) + 2):
                for i in range(int(x - r) - 1, int(x + r) + 2):
                    if not self.solid(i, j):
                        continue
                    nx, ny = min(max(x, i), i + 1), min(max(y, j), j + 1)
                    dx, dy = x - nx, y - ny
                    d2 = dx * dx + dy * dy
                    if d2 < r * r:
                        d = math.sqrt(d2)
                        if d < 1e-6:
                            # centre inside the tile: out the nearest side
                            opts = ((x - i, -1, 0), (i + 1 - x, 1, 0), (y - j, 0, -1), (j + 1 - y, 0, 1))
                            depth, ax, ay = min(opts)
                            x, y = x + ax * (depth + r), y + ay * (depth + r)
                        else:
                            push = r - d
                            x, y = x + dx / d * push, y + dy / d * push
        return x, y

    # ------------------------------------------------------------------ running
    def update(self, inp: Input, dt: float) -> None:
        """Run the world forward by `dt` seconds of real time, in fixed steps."""
        self._acc += min(dt, 0.1)
        while self._acc >= STEP:
            self._acc -= STEP
            if self.state != "play":
                break
            self.step(inp)

    def step(self, inp: Input) -> None:
        dt = STEP
        self.time += dt
        p = self.player
        self._field_t -= dt
        if self._field_t <= 0:
            self._refield()
            self._field_t = 0.25
        # the survivor
        mx, my = inp.mx, inp.my
        n = math.hypot(mx, my)
        if n > 1:
            mx, my = mx / n, my / n
        if n > 0.05:
            p.walk += dt * 9
        p.x, p.y = self._collide(p.x + mx * p.speed * dt, p.y + my * p.speed * dt, p.radius)
        p.cool = max(0.0, p.cool - dt)
        p.hurt = max(0.0, p.hurt - dt)
        target = None
        if inp.aim is not None:
            p.angle = inp.aim
        else:
            target = self._nearest_target()
            if target is not None:
                p.angle = math.atan2(target.y - p.y, target.x - p.x)
            elif n > 0.05:
                p.angle = math.atan2(my, mx)
        p.target = target
        firing = inp.fire or (inp.aim is None and inp.auto_fire and target is not None)
        if firing:
            self._fire()
        self._spawning(dt)
        self._move_zombies(dt)
        self._move_shots(dt)
        self._pickups()
        self._goals()
        self._groan -= dt
        if self._groan <= 0 and self.zombies:
            self.events.append(("sound", "groan"))
            self._groan = self.rng.uniform(2.5, 5.5)

    def _nearest_target(self) -> Zombie | None:
        p = self.player
        spec = WEAPONS[p.weapon]
        reach = spec.range * 1.05
        best, best_d = None, reach * reach
        for z in self.zombies:
            d = (z.x - p.x) ** 2 + (z.y - p.y) ** 2
            if d < best_d and z.los:
                best, best_d = z, d
        return best

    def _fire(self):
        p = self.player
        spec = WEAPONS[p.weapon]
        if p.cool > 0:
            return
        if spec.ammo:
            if p.ammo.get(p.weapon, 0) <= 0:
                self.events.append(("sound", "empty"))
                p.cool = 0.4
                self._switch_from_empty()
                return
            p.ammo[p.weapon] -= 1
        p.cool = spec.rate * self.rate_mult
        p.shots += 1
        mx, my = p.x + math.cos(p.angle) * 0.5, p.y + math.sin(p.angle) * 0.5
        if self.blocks(int(mx), int(my)):
            mx, my = p.x, p.y
        for _ in range(spec.pellets):
            a = p.angle + self.rng.uniform(-spec.spread, spec.spread)
            speed = spec.speed * (self.rng.uniform(0.8, 1.15) if spec.shot == "flame" else 1)
            self.shots.append(Shot(mx, my, a, speed, spec.damage * self.dmg_mult, spec.range / spec.speed,
                                   spec.pierce, kind=spec.shot, knock=spec.knock))
        self.events.append(("sound", spec.sound))
        if spec.shot != "flame":
            self.events.append(("muzzle", mx, my, p.angle))
        if spec.key in ("shotgun", "rifle", "crossbow"):
            self.events.append(("shake", 0.18 if spec.key == "shotgun" else 0.1))

    def _switch_from_empty(self):
        for w in reversed(self.weapons):
            if not WEAPONS[w].ammo or self.player.ammo.get(w, 0) > 0:
                if w != self.player.weapon:
                    self.select(w)
                return

    def select(self, weapon: str) -> bool:
        if weapon in self.weapons and weapon != self.player.weapon:
            self.player.weapon = weapon
            self.player.cool = max(self.player.cool, 0.15)
            self.events.append(("sound", "switch"))
            return True
        return False

    def cycle(self, d: int = 1) -> str:
        ws = self.weapons
        i = ws.index(self.player.weapon) if self.player.weapon in ws else 0
        for k in range(1, len(ws) + 1):
            w = ws[(i + d * k) % len(ws)]
            if not WEAPONS[w].ammo or self.player.ammo.get(w, 0) > 0:
                self.select(w)
                return w
        return self.player.weapon

    # ------------------------------------------------------------------ the dead
    def _rate(self) -> float:
        lv = self.level
        r0, r1 = lv.rate
        t = min(1.0, self.time / max(1, lv.ramp))
        return r0 + (r1 - r0) * t

    def _spawning(self, dt):
        lv = self.level
        if lv.goal == "clear" and self.spawned >= lv.target:
            return
        self._spawn_acc += self._rate() * dt
        alive = len(self.zombies)
        while self._spawn_acc >= 1:
            self._spawn_acc -= 1
            if alive >= lv.max_alive:
                self._spawn_acc = min(self._spawn_acc, 1.0)
                break
            if lv.goal == "clear" and self.spawned >= lv.target:
                break
            self._spawn(self._pick_kind())
            alive += 1
        if lv.endless and self.time >= self._next_tank:
            self._spawn(KINDS["tank"], boss=True)
            self._next_tank += 120

    def _pick_kind(self) -> Kind:
        opts = [(k, w) for k, w, t in self.level.mix if self.time >= t]
        total = sum(w for _, w in opts)
        r = self.rng.uniform(0, total)
        for k, w in opts:
            r -= w
            if r <= 0:
                return KINDS[k]
        return KINDS[opts[-1][0]]

    def _spawn(self, kind: Kind, boss: bool = False):
        p = self.player
        pts = [s for s in self.spawns if (s[0] - p.x) ** 2 + (s[1] - p.y) ** 2 > 49] or self.spawns
        if not pts:
            return
        if boss:
            x, y = max(pts, key=lambda s: (s[0] - p.x) ** 2 + (s[1] - p.y) ** 2 + self.rng.random())
        else:
            x, y = self.rng.choice(pts)
        x += self.rng.uniform(-0.3, 0.3)
        y += self.rng.uniform(-0.3, 0.3)
        hp_mult = 1.0
        if self.level.endless:
            hp_mult = 1 + min(1.5, self.time / 300)
        elif boss:
            hp_mult = 0.7 + 0.4 * (self.level.chapter - 1)   # 1540, 2420 and 3300
        z = Zombie(self._next_id, kind, x, y, hp_mult, boss)
        self._next_id += 1
        if boss:
            z.state_t = 4.0
        self.zombies.append(z)
        if not boss:
            self.spawned += 1

    def _move_zombies(self, dt):
        p = self.player
        cells: dict[tuple[int, int], list[Zombie]] = {}
        for z in self.zombies:
            cells.setdefault((int(z.x), int(z.y)), []).append(z)
        self._cells = cells
        dead = []
        for z in self.zombies:
            k = z.kind
            z.flash = max(0.0, z.flash - dt)
            z.cool = max(0.0, z.cool - dt)
            if z.burn > 0:
                z.burn -= dt
                z.hp -= 14 * dt
                if z.hp <= 0:
                    dead.append(z)
                    continue
            # what it's after
            tx, ty, field = p.x, p.y, self._field
            if self.gen and z.goes_for_gen and not z.boss:
                gd = (self.gen[0] - z.x) ** 2 + (self.gen[1] - z.y) ** 2
                pd = (p.x - z.x) ** 2 + (p.y - z.y) ** 2
                if gd < pd * 2.5:
                    tx, ty, field = self.gen[0], self.gen[1], self._gen_field
            dx, dy = tx - z.x, ty - z.y
            dist = math.hypot(dx, dy) or 1e-6
            z.los_t -= dt
            if z.los_t <= 0:
                z.los = dist < 20 and self.clear_line(z.x, z.y, p.x, p.y)
                z.los_t = 0.25
            sees = (z.los and field is self._field) or dist < 1.3
            ux, uy = (dx / dist, dy / dist) if sees else self._follow(field, z.x, z.y)
            speed = k.speed
            if k.key == "spitter" and z.los and field is self._field:
                z.spit -= dt
                if dist < 4.0:
                    ux, uy = -ux, -uy           # back off
                elif dist < 7.5:
                    ux, uy = -uy * 0.4, ux * 0.4  # circle
                if z.spit <= 0 and dist < 9:
                    a = math.atan2(dy, dx) + self.rng.uniform(-0.08, 0.08)
                    self.shots.append(Shot(z.x, z.y, a, 7.5, k.damage, 9 / 7.5, 0, hostile=True, kind="acid"))
                    self.events.append(("sound", "spit"))
                    z.spit = self.rng.uniform(1.8, 2.8)
            if k.key == "tank":
                speed = self._tank(z, dt, dx, dy, dist)
                if z.state == "charge":
                    ux, uy = z.cx, z.cy
                elif z.state == "windup":
                    ux = uy = 0.0
            z.angle = math.atan2(uy, ux) if (ux or uy) else z.angle
            # keep apart from the others
            sx = sy = 0.0
            ci, cj = int(z.x), int(z.y)
            for a in (-1, 0, 1):
                for b in (-1, 0, 1):
                    for o in cells.get((ci + a, cj + b), ()):
                        if o is z:
                            continue
                        ox, oy = z.x - o.x, z.y - o.y
                        rr = k.radius + o.kind.radius
                        d2 = ox * ox + oy * oy
                        if d2 < rr * rr and d2 > 1e-8:
                            d = math.sqrt(d2)
                            w = (rr - d) / rr * (o.kind.mass / (o.kind.mass + k.mass)) * 2
                            sx += ox / d * w
                            sy += oy / d * w
            z.vx += (ux * speed - z.vx) * min(1.0, dt * 8)
            z.vy += (uy * speed - z.vy) * min(1.0, dt * 8)
            nx = z.x + (z.vx + sx * 2.5) * dt
            ny = z.y + (z.vy + sy * 2.5) * dt
            z.x, z.y = self._collide(nx, ny, min(k.radius, WALL_RADIUS))
            z.walk += dt * speed * 3
            self._unstick(z, dt)
            # the survivor is solid too
            pdx, pdy = z.x - p.x, z.y - p.y
            pr = k.radius + p.radius
            pd2 = pdx * pdx + pdy * pdy
            if pd2 < pr * pr:
                d = math.sqrt(pd2) or 1e-6
                z.x, z.y = self._collide(p.x + pdx / d * pr, p.y + pdy / d * pr, min(k.radius, WALL_RADIUS))
            if pd2 < (pr + 0.12) ** 2 and z.cool <= 0:
                if k.key == "bloater":
                    z.hp = 0
                    dead.append(z)
                    continue
                self.hurt(k.damage * (1.3 if z.state == "charge" else 1))
                z.cool = 0.9
                if z.state == "charge":
                    z.state, z.state_t = "walk", 3.5
            if self.gen and (z.x - self.gen[0]) ** 2 + (z.y - self.gen[1]) ** 2 < (k.radius + 0.75) ** 2 and z.cool <= 0:
                self.gen_hp -= k.damage
                z.cool = 0.9
                self.events.append(("sound", "clang"))
                self.events.append(("spark", self.gen[0], self.gen[1]))
        for z in dead:
            self._kill(z)

    def _unstick(self, z: Zombie, dt):
        """One that hasn't got anywhere for a while (wedged, or somewhere it can't reach you from) walks back in
        from a spawn point, so a level never waits on it."""
        z.check -= dt
        if z.check > 0:
            return
        z.check = 2.0
        moved = (z.x - z.lx) ** 2 + (z.y - z.ly) ** 2
        z.lx, z.ly = z.x, z.y
        lost = not self.reachable(z.x, z.y) if 0 <= int(z.x) < self.w and 0 <= int(z.y) < self.h else True
        if (moved < 0.09 and not z.los and z.state == "walk") or lost:
            z.stuck += 2.0
        else:
            z.stuck = 0.0
        if z.stuck >= 6.0:
            p = self.player
            pts = [s for s in self.spawns if self.reachable(*s)] or self.spawns
            pts = [s for s in pts if (s[0] - p.x) ** 2 + (s[1] - p.y) ** 2 > 36] or pts
            z.x, z.y = self.rng.choice(pts)
            z.lx, z.ly = z.x, z.y
            z.stuck = 0.0

    def _tank(self, z: Zombie, dt, dx, dy, dist) -> float:
        z.state_t -= dt
        if z.state == "walk":
            if z.state_t <= 0 and z.los and dist < 11:
                z.state, z.state_t = "windup", 0.8
                self.events.append(("sound", "roar"))
            return z.kind.speed
        if z.state == "windup":
            if z.state_t <= 0:
                z.state, z.state_t = "charge", 1.1
                z.cx, z.cy = dx / dist, dy / dist
            return 0.0
        # charging
        if z.state_t <= 0:
            z.state, z.state_t = "walk", self.rng.uniform(3.0, 5.0)
        return 7.0

    def hurt(self, amount: float):
        p = self.player
        p.hp -= amount * self.hurt_mult
        p.hurt = 0.35
        self.events.append(("sound", "hurt"))
        self.events.append(("hurt", amount))
        self.events.append(("blood", p.x, p.y, self.rng.uniform(0, 6.28)))

    def _kill(self, z: Zombie):
        if z not in self.zombies:
            return
        self.zombies.remove(z)
        self.kills += 1
        self.scrap += z.kind.scrap
        self.events.append(("kill", z.kind.key, z.x, z.y, z.angle))
        self.events.append(("sound", "boom" if z.kind.key in ("bloater", "tank") else "splat"))
        if z.boss:
            self.bosses_left -= 1
            self.events.append(("shake", 0.6))
            for _ in range(3):
                self.pickups.append(Pickup(self.rng.choice(("ammo", "medkit")), z.x + self.rng.uniform(-1, 1),
                                           z.y + self.rng.uniform(-1, 1)))
        if z.kind.key == "bloater":
            self._explode(z.x, z.y, 2.3, 80, 32)
        r = self.rng.random()
        if r < 0.055:
            self.pickups.append(Pickup("ammo", z.x, z.y))
        elif r < 0.08:
            self.pickups.append(Pickup("medkit", z.x, z.y))
        # nudge drops out of walls
        for pk in self.pickups[-1:]:
            pk.x, pk.y = self._collide(pk.x, pk.y, 0.3)

    def _explode(self, x, y, radius, zdmg, pdmg):
        self.events.append(("explode", x, y, radius))
        self.events.append(("shake", 0.4))
        for o in list(self.zombies):
            d = math.hypot(o.x - x, o.y - y)
            if d < radius:
                o.hp -= zdmg * (1 - d / radius * 0.5)
                o.flash = 0.1
                if o.hp <= 0:
                    self._kill(o)
        p = self.player
        d = math.hypot(p.x - x, p.y - y)
        if d < radius:
            self.hurt(pdmg * (1 - d / radius * 0.6))

    # ------------------------------------------------------------------ shots
    def _move_shots(self, dt):
        p = self.player
        keep = []
        cells = getattr(self, "_cells", {})
        for s in self.shots:
            s.life -= dt
            s.age += dt
            if s.life <= 0:
                if s.kind == "acid":
                    self.events.append(("acid", s.x, s.y))
                continue
            sub = 2 if s.speed > 20 else 1
            alive = True
            for _ in range(sub):
                s.x += s.dx * s.speed * dt / sub
                s.y += s.dy * s.speed * dt / sub
                if self.blocks(int(s.x), int(s.y)):
                    alive = False
                    if s.kind == "acid":
                        self.events.append(("acid", s.x - s.dx * 0.2, s.y - s.dy * 0.2))
                    elif s.kind != "flame":
                        self.events.append(("spark", s.x - s.dx * 0.15, s.y - s.dy * 0.15))
                    break
                if s.hostile:
                    if (s.x - p.x) ** 2 + (s.y - p.y) ** 2 < (p.radius + 0.12) ** 2:
                        self.hurt(s.damage)
                        self.events.append(("acid", s.x, s.y))
                        alive = False
                        break
                    continue
                ci, cj = int(s.x), int(s.y)
                for a in (-1, 0, 1):
                    for b in (-1, 0, 1):
                        for z in cells.get((ci + a, cj + b), ()):
                            if z.id in s.hit or z.hp <= 0:
                                continue
                            rr = z.kind.radius + (0.25 if s.kind == "flame" else 0.08)
                            if (z.x - s.x) ** 2 + (z.y - s.y) ** 2 < rr * rr:
                                s.hit.add(z.id)
                                self._hit(z, s)
                                if s.kind == "flame":
                                    continue
                                s.pierce -= 1
                                if s.pierce < 0:
                                    alive = False
                                    break
                        if not alive:
                            break
                    if not alive:
                        break
                if not alive:
                    break
            if alive:
                keep.append(s)
        self.shots = keep

    def _hit(self, z: Zombie, s: Shot):
        z.hp -= s.damage
        z.flash = 0.08
        if s.kind == "flame":
            z.burn = 2.2
        else:
            self.player.hits += 1
            push = s.knock / z.kind.mass
            z.x, z.y = self._collide(z.x + s.dx * push, z.y + s.dy * push, min(z.kind.radius, WALL_RADIUS))
            self.events.append(("blood", z.x, z.y, math.atan2(s.dy, s.dx)))
            self.events.append(("sound", "hit"))
        if z.hp <= 0:
            self._kill(z)

    # ------------------------------------------------------------------ pickups and goals
    def _pickups(self):
        p = self.player
        keep = []
        for pk in self.pickups:
            pk.bob += STEP * 4
            if (pk.x - p.x) ** 2 + (pk.y - p.y) ** 2 > 0.6 ** 2:
                keep.append(pk)
                continue
            if pk.kind == "medkit":
                if p.hp >= p.max_hp:
                    keep.append(pk)
                    continue
                p.hp = min(p.max_hp, p.hp + 40)
                p.medkits += 1
            elif pk.kind == "ammo":
                full = all(p.ammo.get(w, 0) >= int(WEAPONS[w].max_ammo * self.ammo_mult)
                           for w in self.weapons if WEAPONS[w].ammo)
                if full and any(WEAPONS[w].ammo for w in self.weapons):
                    keep.append(pk)
                    continue
                for w in self.weapons:
                    spec = WEAPONS[w]
                    if spec.ammo:
                        cap = int(spec.max_ammo * self.ammo_mult)
                        p.ammo[w] = min(cap, p.ammo.get(w, 0) + int(spec.pickup * self.ammo_mult))
            elif pk.kind == "fuel":
                self.fuel += 1
            self.events.append(("pickup", pk.kind, pk.x, pk.y))
            self.events.append(("sound", "pickup"))
        self.pickups = keep

    @property
    def exit_open(self) -> bool:
        return self.level.goal == "escape" and self.fuel >= self.fuel_needed

    def _goals(self):
        lv = self.level
        p = self.player
        if p.hp <= 0:
            p.hp = 0
            self._end("lost", "You were overrun.")
            return
        if self.gen and self.gen_hp <= 0:
            self.gen_hp = 0
            self._end("lost", "The generator went down.")
            return
        if lv.endless:
            return
        if lv.goal in ("survive", "defend") and self.time >= lv.target:
            self._end("won", "You made it.")
        elif lv.goal == "clear" and self.kills >= lv.target:
            self._end("won", "That's all of them.")
        elif lv.goal == "boss" and self.bosses_left <= 0:
            self._end("won", "It's down.")
        elif lv.goal == "escape" and self.exit_open and (int(p.x), int(p.y)) in self.exits:
            self._end("won", "You got out.")

    def _end(self, state: str, why: str):
        self.state, self.why = state, why
        self.events.append(("sound", "win" if state == "won" else "lose"))

    # ------------------------------------------------------------------ for the window
    def progress(self) -> tuple[float, str]:
        """How far along the goal is (0..1) and the words for it."""
        lv = self.level
        if lv.endless:
            m, s = divmod(int(self.time), 60)
            return 0.0, f"{m}:{s:02d} · {self.kills} down"
        if lv.goal in ("survive", "defend"):
            left = max(0, math.ceil(lv.target - self.time))
            return min(1.0, self.time / lv.target), f"{left} s to go"
        if lv.goal == "clear":
            return min(1.0, self.kills / lv.target), f"{self.kills} of {lv.target} down"
        if lv.goal == "boss":
            done = lv.bosses - self.bosses_left
            boss = next((z for z in self.zombies if z.boss), None)
            frac = (done + (1 - boss.hp / boss.max_hp if boss else 0)) / max(1, lv.bosses)
            return min(1.0, frac), ("Big one" if lv.bosses == 1 else f"Big ones: {done} of {lv.bosses} down")
        if lv.goal == "escape":
            if self.exit_open:
                return 1.0, "Get to the way out"
            return self.fuel / max(1, self.fuel_needed), f"Fuel {self.fuel} of {self.fuel_needed}"
        return 0.0, ""

    def stars(self) -> int:
        if self.state != "won":
            return 0
        frac = self.player.hp / self.player.max_hp
        if self.gen:
            frac = min(frac, self.gen_hp / self.gen_max)
        return stars_for(frac)

    def bonus(self) -> int:
        """Scrap for finishing: more for later chapters and more stars."""
        if self.state != "won" or self.level.endless:
            return 0
        return 15 * self.level.chapter + 10 * self.stars()

    def drain_events(self) -> list[tuple]:
        ev, self.events = self.events, []
        return ev
