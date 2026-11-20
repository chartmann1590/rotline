# SPDX-License-Identifier: GPL-3.0-or-later
"""What Rotline sells, and who owns what. No GTK, so it is unit tested.

Each item is bought once and kept: two chapters, the Arsenal (two weapons), the Survivors (four characters), and the
Complete pack with all four. No coins, no loot boxes, nothing that runs out. Prices live on the license server.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    icon: str
    line: str
    details: tuple
    includes: tuple = ()


ITEMS = (
    Item("rotline_chapter2", "Chapter 2: Downtown", "building", "Four night levels in the city.",
         ("Gridlock, Mercy General, Last Train and Rooftop Signal", "Spitters, and two big ones on the roof")),
    Item("rotline_chapter3", "Chapter 3: The Harbor", "waves", "Four levels in the fog, and the way out.",
         ("The Docks, Warehouse 9, The Lighthouse and The Ferry", "The ending")),
    Item("rotline_arsenal", "Arsenal", "zap", "The flamethrower and the crossbow.",
         ("Flamethrower: sets crowds alight", "Crossbow: one bolt through a whole line of them",
          "In every level and in Endless")),
    Item("rotline_survivors", "Survivors", "users", "Play as Rosa, Hank, Jules or Mo.",
         ("Four more survivors to play as", "Looks only: nobody is stronger")),
    Item("rotline_complete", "Complete pack", "package", "Everything above, for less than buying each.",
         ("Both chapters, the Arsenal and the Survivors",),
         includes=("rotline_chapter2", "rotline_chapter3", "rotline_arsenal", "rotline_survivors")),
)
BY_KEY = {i.key: i for i in ITEMS}
PRODUCTS = tuple(i.key for i in ITEMS)
COMPLETE = "rotline_complete"


def owns(billing, key: str) -> bool:
    """Owned outright, or through the Complete pack."""
    have = billing.entitlements()
    return key in have or (key != COMPLETE and COMPLETE in have and key in BY_KEY[COMPLETE].includes)
