# SPDX-License-Identifier: GPL-3.0-or-later
"""Rotline's rules, maps, progress and store logic. No GTK: run with plain pytest."""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rotline import catalog, game as G, levels as L  # noqa: E402
from rotline.progress import ARSENAL, EARNED, SURVIVORS, Progress  # noqa: E402

ALL = list(L.LEVELS) + [L.ENDLESS]


# ------------------------------------------------------------------------------------------------ maps
def test_every_map_is_sound():
    for lv in ALL:
        rows = lv.rows
        assert len({len(r) for r in rows}) == 1, lv.key
        assert all(r[0] == "#" and r[-1] == "#" for r in rows), lv.key
        assert set(rows[0]) == {"#"} and set(rows[-1]) == {"#"}, lv.key
        text = "".join(rows)
        assert text.count("P") == 1, lv.key
        assert text.count("S") >= 2, lv.key
        assert set(text) <= set("#.,=ctx~fPSEFGha"), (lv.key, set(text) - set("#.,=ctx~fPSEFGha"))
        if lv.goal == "escape":
            assert text.count("F") == lv.target, lv.key
            assert "E" in text, lv.key
        if lv.goal == "defend":
            assert text.count("G") == 1, lv.key
        if lv.goal == "boss":
            assert lv.bosses == lv.target >= 1, lv.key


def test_everything_on_every_map_can_be_reached():
    for lv in ALL:
        w = G.World(lv, seed=1)
        for j, row in enumerate(lv.rows):
            for i, ch in enumerate(row):
                if ch in "SEFha":
                    assert w.reachable(i + 0.5, j + 0.5), (lv.key, ch, i, j)


def test_twelve_levels_in_three_chapters_and_only_the_first_is_free():
    assert len(L.LEVELS) == 12
    assert [len(L.in_chapter(n)) for n in (1, 2, 3)] == [4, 4, 4]
    assert L.FREE_CHAPTER == 1 and set(L.CHAPTER_PRODUCTS) == {2, 3}
    assert {lv.goal for lv in L.LEVELS} == {"survive", "clear", "escape", "defend", "boss"}
    assert L.next_level("1-4").key == "2-1" and L.next_level("3-4") is None
    assert L.goal_words(L.BY_KEY["1-2"]) == "Find 3 fuel cans, then get out"


# ------------------------------------------------------------------------------------------------ rules
def quiet(key="1-1", **kw):
    """A world with nobody coming, to test one thing at a time."""
    w = G.World(L.BY_KEY[key], seed=3, **kw)
    w._spawning = lambda dt: None
    w.zombies.clear()
    return w


def put(w, kind, dx, dy=0.0):
    z = G.Zombie(w._next_id, G.KINDS[kind], w.player.x + dx, w.player.y + dy)
    w._next_id += 1
    w.zombies.append(z)
    return z


def run(w, seconds, inp=None):
    inp = inp or G.Input()
    for _ in range(int(seconds / G.STEP)):
        if w.state != "play":
            break
        w.step(inp)


def test_it_aims_and_fires_for_you_and_puts_one_down():
    w = quiet()
    z = put(w, "walker", 4)
    run(w, 3)
    assert z not in w.zombies and w.kills == 1 and w.scrap == 1
    assert w.player.shots >= 2 and w.player.hits >= 2
    names = [e[1] for e in w.drain_events() if e[0] == "sound"]
    assert "pistol" in names and "splat" in names


def test_no_auto_fire_when_turned_off_and_aiming_by_hand():
    w = quiet()
    put(w, "walker", 6)
    run(w, 0.5, G.Input(auto_fire=False))
    assert w.player.shots == 0
    run(w, 0.5, G.Input(aim=0.0, fire=True))   # aiming right, at it
    assert w.player.shots >= 1


def test_ammo_runs_out_and_it_falls_back_to_the_pistol():
    w = quiet(weapons=("pistol", "shotgun"))
    assert w.select("shotgun")
    w.player.ammo["shotgun"] = 2
    run(w, 3, G.Input(aim=0.0, fire=True))
    assert w.player.ammo["shotgun"] == 0
    assert w.player.weapon == "pistol"


def test_the_dead_walk_to_you_round_walls_and_bite():
    w = quiet()
    z = put(w, "walker", 6)
    hp = w.player.hp
    run(w, 6, G.Input(auto_fire=False))
    assert w.player.hp < hp
    assert math.hypot(z.x - w.player.x, z.y - w.player.y) < 1.2


def test_story_mode_halves_the_damage():
    a, b = quiet(), quiet(easy=True)
    a.hurt(20)
    b.hurt(20)
    assert a.player.hp == a.player.max_hp - 20 and b.player.hp == b.player.max_hp - 10


def test_a_bloater_bursts_and_hurts_those_near_it():
    w = quiet()
    bl = put(w, "bloater", 1.2)
    other = put(w, "walker", 1.2, 1.0)
    bl.hp = 1
    w._hit(bl, G.Shot(w.player.x, w.player.y, 0, 20, 10, 1, 0))
    assert any(e[0] == "explode" for e in w.events)
    assert other.hp < other.max_hp or other not in w.zombies
    assert w.player.hp < w.player.max_hp


def test_survive_ends_when_the_time_is_up():
    w = quiet("1-1")
    w.time = 59.99
    run(w, 0.1)
    assert w.state == "won" and w.stars() == 3 and w.bonus() == 15 + 30


def test_stars_follow_your_health():
    assert [G.stars_for(f) for f in (1.0, 0.75, 0.5, 0.4, 0.1)] == [3, 3, 2, 2, 1]


def test_escape_needs_every_can_then_the_way_out():
    w = quiet("1-2")
    exit_tile = next(iter(w.exits))
    w.player.x, w.player.y = exit_tile[0] + 0.5, exit_tile[1] + 0.5
    run(w, 0.2)
    assert w.state == "play" and not w.exit_open
    for pk in [p for p in w.pickups if p.kind == "fuel"]:
        w.player.x, w.player.y = pk.x, pk.y
        run(w, 0.05)
    assert w.fuel == 3 and w.exit_open
    w.player.x, w.player.y = exit_tile[0] + 0.5, exit_tile[1] + 0.5
    run(w, 0.1)
    assert w.state == "won"


def test_defend_is_lost_when_the_generator_goes():
    w = quiet("2-2")
    w.gen_hp = 1
    gx, gy = w.gen
    z = G.Zombie(99, G.KINDS["walker"], gx + 0.9, gy)
    z.cool = 0
    w.zombies.append(z)
    run(w, 0.5, G.Input(auto_fire=False))
    assert w.state == "lost" and "generator" in w.why


def test_clear_counts_kills_and_stops_spawning_at_the_target():
    w = G.World(L.BY_KEY["1-3"], seed=2)
    w.spawned = w.level.target
    n = len(w.zombies)
    w._spawning(5)
    assert len(w.zombies) == n
    w.kills = w.level.target
    w._goals()
    assert w.state == "won"


def test_a_boss_level_is_won_when_the_big_ones_are_down():
    w = G.World(L.BY_KEY["2-4"], seed=2)
    bosses = [z for z in w.zombies if z.boss]
    assert len(bosses) == 2 and all(z.kind.key == "tank" for z in bosses)
    assert bosses[0].max_hp > G.KINDS["tank"].hp   # tougher after chapter 1
    for z in bosses:
        w._kill(z)
    w._goals()
    assert w.state == "won"


def test_you_lose_when_your_health_is_gone():
    w = quiet()
    w.player.hp = 0
    w._goals()
    assert w.state == "lost" and w.stars() == 0 and w.bonus() == 0


def test_a_wedged_one_walks_back_in_from_a_spawn_point():
    w = quiet()
    z = put(w, "walker", 0, 0)
    z.x, z.y = 3.5, 3.5
    w._refield()
    w._field[3][3] = 1 << 20     # pretend it can't get to you from there
    z.los = False
    for _ in range(4):
        z.check = 0
        w._unstick(z, 0.01)
    assert (round(z.x - 0.5, 1), round(z.y - 0.5, 1)) != (3.0, 3.0)
    assert any(math.hypot(z.x - s[0], z.y - s[1]) < 0.01 for s in w.spawns)


def test_walls_hold():
    w = quiet()
    x, y = w._collide(0.6, 5.5, 0.35)     # pushed out of the left wall
    assert x >= 1.35 - 1e-6


def test_pickups_heal_and_restock_but_not_when_full():
    w = quiet(weapons=("pistol", "smg"))
    p = w.player
    med = G.Pickup("medkit", p.x, p.y)
    w.pickups = [med]
    run(w, 0.05)
    assert med in w.pickups                # full health: left for later
    p.hp = 30
    run(w, 0.05)
    assert med not in w.pickups and p.hp == 70
    p.ammo["smg"] = 0
    w.pickups = [G.Pickup("ammo", p.x, p.y)]
    run(w, 0.05)
    assert p.ammo["smg"] == G.WEAPONS["smg"].pickup


def test_upgrades_change_the_numbers():
    base = quiet()
    up = quiet(upgrades={"health": 2, "speed": 5, "damage": 1, "rate": 3, "ammo": 1})
    assert up.player.max_hp == base.player.max_hp + 30
    assert up.player.speed > base.player.speed
    assert up.dmg_mult == 1.1 and up.rate_mult < 1 and up.ammo_mult == 1.2
    assert quiet(upgrades={"health": 99}).player.max_hp == 100 + 15 * G.MAX_UPGRADE


def test_endless_keeps_going_and_gets_tougher():
    w = G.World(L.ENDLESS, seed=1)
    w.time = 400
    w._goals()
    assert w.state == "play"
    w._spawn(G.KINDS["walker"])
    assert w.zombies[-1].max_hp > G.KINDS["walker"].hp


def test_same_seed_same_game():
    def play(seed):
        w = G.World(L.BY_KEY["1-1"], seed=seed)
        run(w, 20)
        return w.kills, round(w.player.hp, 3), len(w.zombies)
    assert play(5) == play(5)


def bot(w, cache):
    """Kites away from the dead and heads for what the goal needs; it aims and fires for itself."""
    p = w.player
    rx = ry = 0.0
    for z in w.zombies:
        dx, dy = p.x - z.x, p.y - z.y
        d = math.hypot(dx, dy) or 1e-3
        if d < 4.5:
            k = (4.5 - d) / 4.5 * (2 if z.kind.key in ("tank", "bloater") else 1)
            rx, ry = rx + dx / d * k, ry + dy / d * k
    tgt = None
    if w.level.goal == "escape":
        fuels = [pk for pk in w.pickups if pk.kind == "fuel"]
        if fuels:
            f = min(fuels, key=lambda f: (f.x - p.x) ** 2 + (f.y - p.y) ** 2)
            tgt = (f.x, f.y)
        else:
            e = next(iter(w.exits))
            tgt = (e[0] + 0.5, e[1] + 0.5)
    gx = gy = 0.0
    if tgt:
        key = (int(tgt[0]), int(tgt[1]))
        if cache.get("k") != key:
            cache["k"], cache["f"] = key, w._bfs(*key)
        gx, gy = w._follow(cache["f"], p.x, p.y)
    for wp in reversed(w.weapons):        # the best weapon that still has ammo
        if not G.WEAPONS[wp].ammo or p.ammo.get(wp, 0) > 0:
            if p.weapon != wp:
                w.select(wp)
            break
    return G.Input(gx + rx * 1.5, gy + ry * 1.5)


def test_the_first_chapter_can_be_won():
    """A simple bot clears the free levels with no upgrades, so they're fair, not impossible."""
    weapons = {"1-1": ["pistol"], "1-2": ["pistol", "shotgun"], "1-3": ["pistol", "shotgun", "smg"],
               "1-4": ["pistol", "shotgun", "smg", "rifle"]}
    for key, ws in weapons.items():
        results = []
        for seed in (1, 2, 3):
            w = G.World(L.BY_KEY[key], weapons=ws, seed=seed)
            cache = {}
            while w.state == "play" and w.time < 300:
                w.step(bot(w, cache))
                w.drain_events()
            results.append(w.state)
        assert results.count("won") >= 2, (key, results)


# ------------------------------------------------------------------------------------------------ progress
def test_progress_records_stars_scrap_and_weapons():
    pr = Progress(os.path.join(tempfile.mkdtemp(), "p.json"))
    assert pr.unlocked("1-1") and not pr.unlocked("1-2") and pr.unlocked("endless")
    assert pr.weapons(False) == ["pistol"]
    news = pr.finish("1-1", won=True, stars=2, time=60, kills=30, scrap=55)
    assert news == {"more_stars": True, "weapon": "shotgun"}
    assert pr.unlocked("1-2") and pr.current() == "1-2" and pr.scrap == 55
    assert pr.finish("1-1", won=True, stars=1, time=50, kills=1, scrap=0) == {}
    assert pr.stars("1-1") == 2 and pr.level("1-1")["time"] == 50
    pr.finish("1-2", won=False, stars=0, time=20, kills=8, scrap=8)
    assert not pr.done("1-2") and pr.scrap == 63            # scrap kept even when you lose
    assert pr.weapons(True) == ["pistol", "shotgun"] + list(ARSENAL)
    again = Progress(pr.path)
    assert again.stars("1-1") == 2 and again.kills() == 39


def test_every_earned_weapon_comes_from_a_free_level():
    assert all(L.BY_KEY[k].chapter == L.FREE_CHAPTER for k in EARNED)
    assert {L.BY_KEY[k].unlocks for k in EARNED} == set(EARNED.values())
    assert set(G.ORDER) == {"pistol", *EARNED.values(), *ARSENAL}
    assert all(G.WEAPONS[w].extra for w in ARSENAL)


def test_upgrades_cost_scrap_and_can_be_given_back():
    pr = Progress(os.path.join(tempfile.mkdtemp(), "p.json"))
    assert not pr.buy_upgrade("health")
    pr.data["scrap"] = 1000
    for _ in range(G.MAX_UPGRADE):
        assert pr.buy_upgrade("health")
    assert not pr.buy_upgrade("health")                     # maxed
    assert pr.scrap == 1000 - sum(G.UPGRADE_COSTS)
    assert pr.reset_upgrades() == sum(G.UPGRADE_COSTS)
    assert pr.scrap == 1000 and pr.upgrades()["health"] == 0


def test_endless_best_and_survivors():
    pr = Progress(os.path.join(tempfile.mkdtemp(), "p.json"))
    assert pr.finish("endless", won=False, stars=0, time=95.4, kills=60, scrap=60) == {"best": True}
    assert pr.finish("endless", won=False, stars=0, time=50, kills=70, scrap=70) == {}
    assert pr.endless_best() == (95.4, 70)
    assert pr.survivor == "sam"
    pr.set_survivor("rosa")
    pr.set_survivor("nobody")
    assert pr.survivor == "rosa"
    assert [s[0] for s in SURVIVORS if not s[6]] == ["sam"]  # one free survivor, four in the pack


def test_a_broken_progress_file_starts_fresh():
    path = os.path.join(tempfile.mkdtemp(), "p.json")
    with open(path, "w") as f:
        f.write("{not json")
    assert Progress(path).scrap == 0


# ------------------------------------------------------------------------------------------------ the store
class FakeBilling:
    def __init__(self, *owned):
        self.owned = set(owned)

    def entitlements(self):
        return self.owned


def test_the_complete_pack_includes_everything_else():
    assert catalog.PRODUCTS == ("rotline_chapter2", "rotline_chapter3", "rotline_arsenal", "rotline_survivors",
                                "rotline_complete")
    assert set(catalog.BY_KEY[catalog.COMPLETE].includes) == set(catalog.PRODUCTS) - {catalog.COMPLETE}
    b = FakeBilling("rotline_complete")
    assert all(catalog.owns(b, k) for k in catalog.PRODUCTS)
    b = FakeBilling("rotline_arsenal")
    assert catalog.owns(b, "rotline_arsenal") and not catalog.owns(b, "rotline_chapter2")
    assert not catalog.owns(b, catalog.COMPLETE)
    assert set(L.CHAPTER_PRODUCTS.values()) <= set(catalog.PRODUCTS)


def test_nothing_in_the_store_is_a_currency_or_a_subscription():
    # one-time unlocks only: no coins, no boosts, nothing that runs out or renews
    for it in catalog.ITEMS:
        assert ":" not in it.key
        words = (it.name + it.line + " ".join(it.details)).lower()
        assert not any(w in words for w in ("coin", "gem", "scrap", "boost", "loot", "random"))
