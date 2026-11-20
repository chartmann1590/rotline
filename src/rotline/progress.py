# SPDX-License-Identifier: GPL-3.0-or-later
"""What you've done in Rotline: levels and stars, scrap and upgrades, your survivor, the endless records and
settings. One small JSON file in the app's own folder. No GTK.
"""
from __future__ import annotations

import json
import os

from . import game as G
from . import levels as L

# weapons you earn by finishing levels; the Arsenal pack adds the rest
EARNED = {"1-1": "shotgun", "1-2": "smg", "1-3": "rifle"}
ARSENAL = ("flamer", "crossbow")

SURVIVORS = (
    # key, name, line, jacket, skin, hair, needs the Survivors pack
    ("sam", "Sam", "Out of work, never out of luck.", "#3f6aa8", "#e0b18c", "#3a2a1c", False),
    ("rosa", "Rosa", "Paramedic. Patches people. Not those people.", "#e8e8e8", "#a8714f", "#1c1410", True),
    ("hank", "Hank", "Park ranger. Knows the woods, hates the city.", "#5c6b3a", "#d9a37c", "#8a8a8a", True),
    ("jules", "Jules", "Courier. Fastest bike in town, before.", "#2b2b2b", "#f0c8a0", "#b0452a", True),
    ("mo", "Mo", "Firefighter. Ran in when everyone ran out.", "#d6a51c", "#7a4c2e", "#141414", True),
)
SURVIVOR = {s[0]: s for s in SURVIVORS}

DEFAULTS = {
    "sound": True, "shake": True, "auto_fire": True, "easy": False, "touch": "auto", "volume": 0.8,
}


class Progress:
    def __init__(self, path: str):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                doc = json.load(f)
            if isinstance(doc, dict):
                return doc
        except (OSError, ValueError):
            pass
        return {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    # ---------------------------------------------------------------- settings
    def setting(self, key: str):
        return self.data.get("settings", {}).get(key, DEFAULTS.get(key))

    def set_setting(self, key: str, value) -> None:
        self.data.setdefault("settings", {})[key] = value
        self.save()

    # ---------------------------------------------------------------- levels
    def level(self, key: str) -> dict:
        return self.data.get("levels", {}).get(key, {})

    def stars(self, key: str) -> int:
        return int(self.level(key).get("stars", 0))

    def done(self, key: str) -> bool:
        return self.stars(key) > 0

    def total_stars(self) -> int:
        return sum(self.stars(lv.key) for lv in L.LEVELS)

    def unlocked(self, key: str) -> bool:
        """Open to play (ignoring whether the chapter is bought): the first level, or the one before is done."""
        keys = [lv.key for lv in L.LEVELS]
        if key == "endless":
            return True
        if key not in keys:
            return False
        i = keys.index(key)
        return i == 0 or self.done(keys[i - 1])

    def current(self) -> str:
        """The first level not finished yet (the last one when all are)."""
        for lv in L.LEVELS:
            if not self.done(lv.key):
                return lv.key
        return L.LEVELS[-1].key

    def finish(self, key: str, *, won: bool, stars: int, time: float, kills: int, scrap: int) -> dict:
        """Record an attempt. Scrap from kills is kept win or lose; the bonus comes with the win. Returns what's new
        ({"weapon": "shotgun", "best": True, ...})."""
        news: dict = {}
        self.data["scrap"] = self.scrap + max(0, int(scrap))
        stats = self.data.setdefault("stats", {})
        stats["kills"] = int(stats.get("kills", 0)) + kills
        stats["played"] = int(stats.get("played", 0)) + 1
        if key == "endless":
            rec = self.data.setdefault("endless", {})
            if time > float(rec.get("time", 0)):
                rec["time"] = round(time, 1)
                news["best"] = True
            rec["kills"] = max(int(rec.get("kills", 0)), kills)
        elif won:
            rec = self.data.setdefault("levels", {}).setdefault(key, {})
            if stars > int(rec.get("stars", 0)):
                rec["stars"] = stars
                news["more_stars"] = True
            if not rec.get("time") or time < rec["time"]:
                rec["time"] = round(time, 1)
            w = EARNED.get(key)
            if w and w not in self.data.setdefault("weapons", []):
                self.data["weapons"].append(w)
                news["weapon"] = w
        self.save()
        return news

    # ---------------------------------------------------------------- scrap and upgrades
    @property
    def scrap(self) -> int:
        return int(self.data.get("scrap", 0))

    def upgrades(self) -> dict:
        return {k: int(self.data.get("upgrades", {}).get(k, 0)) for k in G.UPGRADES}

    def buy_upgrade(self, key: str) -> bool:
        lvl = self.upgrades().get(key, 0)
        cost = G.upgrade_cost(lvl)
        if cost is None or self.scrap < cost:
            return False
        self.data["scrap"] = self.scrap - cost
        self.data.setdefault("upgrades", {})[key] = lvl + 1
        self.save()
        return True

    def reset_upgrades(self) -> int:
        """Give back all the scrap spent on upgrades, to spend again."""
        back = sum(sum(G.UPGRADE_COSTS[:n]) for n in self.upgrades().values())
        self.data["upgrades"] = {}
        self.data["scrap"] = self.scrap + back
        self.save()
        return back

    # ---------------------------------------------------------------- weapons and survivors
    def weapons(self, arsenal: bool) -> list[str]:
        have = ["pistol"] + [w for w in self.data.get("weapons", []) if w in G.WEAPONS]
        if arsenal:
            have += list(ARSENAL)
        return [w for w in G.ORDER if w in have]

    @property
    def survivor(self) -> str:
        return self.data.get("survivor", "sam")

    def set_survivor(self, key: str) -> None:
        if key in SURVIVOR:
            self.data["survivor"] = key
            self.save()

    def endless_best(self) -> tuple[float, int]:
        rec = self.data.get("endless", {})
        return float(rec.get("time", 0)), int(rec.get("kills", 0))

    def kills(self) -> int:
        return int(self.data.get("stats", {}).get("kills", 0))
