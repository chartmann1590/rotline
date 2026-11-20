# SPDX-License-Identifier: GPL-3.0-or-later
# Rotline's numbers: weapons, the dead, upgrades, survivors and what the store sells. Data only.
class_name Data
extends RefCounted

const TILE := 64.0

# rate: seconds between shots; range in tiles; pierce: how many it goes through after the first;
# ammo: start (0 = unlimited); kind: hitscan, flame, bolt
const WEAPONS := {
	"pistol": {"name": "Pistol", "rate": 0.28, "damage": 16.0, "pellets": 1, "spread": 0.035, "range": 11.0, "pierce": 0,
		"ammo": 0, "max_ammo": 0, "pickup": 0, "knock": 60.0, "kind": "hitscan", "shake": 0.12, "sound": "pistol"},
	"shotgun": {"name": "Shotgun", "rate": 0.8, "damage": 13.0, "pellets": 8, "spread": 0.3, "range": 7.5, "pierce": 0,
		"ammo": 24, "max_ammo": 48, "pickup": 10, "knock": 150.0, "kind": "hitscan", "shake": 0.45, "sound": "shotgun"},
	"smg": {"name": "SMG", "rate": 0.075, "damage": 8.0, "pellets": 1, "spread": 0.09, "range": 10.0, "pierce": 0,
		"ammo": 180, "max_ammo": 360, "pickup": 80, "knock": 28.0, "kind": "hitscan", "shake": 0.08, "sound": "smg"},
	"rifle": {"name": "Rifle", "rate": 0.55, "damage": 62.0, "pellets": 1, "spread": 0.004, "range": 20.0, "pierce": 4,
		"ammo": 24, "max_ammo": 50, "pickup": 10, "knock": 120.0, "kind": "hitscan", "shake": 0.3, "sound": "rifle"},
	"flamer": {"name": "Flamethrower", "rate": 0.05, "damage": 5.0, "pellets": 1, "spread": 0.32, "range": 4.6, "pierce": 99,
		"ammo": 300, "max_ammo": 600, "pickup": 140, "knock": 6.0, "kind": "flame", "shake": 0.03, "sound": "flame", "extra": true},
	"crossbow": {"name": "Crossbow", "rate": 0.65, "damage": 110.0, "pellets": 1, "spread": 0.0, "range": 18.0, "pierce": 10,
		"ammo": 24, "max_ammo": 48, "pickup": 10, "knock": 180.0, "kind": "bolt", "shake": 0.2, "sound": "crossbow", "extra": true},
}
const ORDER := ["pistol", "shotgun", "smg", "rifle", "flamer", "crossbow"]
const EARNED := {"1-1": "shotgun", "1-2": "smg", "1-3": "rifle"}
const ARSENAL := ["flamer", "crossbow"]

# radius in tiles; speed in tiles a second; damage a bite
const KINDS := {
	"walker": {"name": "Walker", "hp": 34.0, "speed": 1.3, "radius": 0.34, "damage": 11.0, "scrap": 1, "mass": 1.0, "scale": 0.8},
	"runner": {"name": "Runner", "hp": 22.0, "speed": 3.0, "radius": 0.3, "damage": 8.0, "scrap": 2, "mass": 0.8, "scale": 0.74},
	"brute": {"name": "Brute", "hp": 190.0, "speed": 1.05, "radius": 0.5, "damage": 24.0, "scrap": 5, "mass": 3.0, "scale": 0.8},
	"spitter": {"name": "Spitter", "hp": 44.0, "speed": 1.45, "radius": 0.34, "damage": 9.0, "scrap": 3, "mass": 1.0, "scale": 0.8},
	"bloater": {"name": "Bloater", "hp": 48.0, "speed": 1.05, "radius": 0.44, "damage": 30.0, "scrap": 3, "mass": 1.6, "scale": 0.8},
	"tank": {"name": "Tank", "hp": 2600.0, "speed": 1.2, "radius": 0.72, "damage": 30.0, "scrap": 60, "mass": 12.0, "scale": 0.8},
}

const UPGRADES := {
	"health": ["Toughness", "+15 health"],
	"damage": ["Firepower", "+10% damage"],
	"rate": ["Trigger finger", "+8% fire rate"],
	"speed": ["Running shoes", "+5% speed"],
	"ammo": ["Deep pockets", "+20% ammo"],
}
const UPGRADE_COSTS := [30, 60, 100, 160, 240]

# key, name, line, needs the Survivors pack
const SURVIVORS := [
	["sam", "Sam", "Out of work, never out of luck.", false],
	["rosa", "Rosa", "Paramedic. Patches people. Not those people.", true],
	["hank", "Hank", "Park ranger. Knows the woods, hates the city.", true],
	["jules", "Jules", "Courier. Fastest bike in town, before.", true],
	["mo", "Mo", "Firefighter. Ran in when everyone ran out.", true],
]

# One-time unlocks, kept for good. Prices live on the license server, never here.
const ITEMS := [
	{"key": "rotline_chapter2", "name": "Chapter 2: Downtown", "line": "Four night levels in the city.",
		"details": ["Gridlock, Mercy General, Last Train and Rooftop Signal", "Spitters, rain, and two big ones on the roof"]},
	{"key": "rotline_chapter3", "name": "Chapter 3: The Harbor", "line": "Four levels in the fog, and the way out.",
		"details": ["The Docks, Warehouse 9, The Lighthouse and The Ferry", "The ending"]},
	{"key": "rotline_arsenal", "name": "Arsenal", "line": "The flamethrower and the crossbow.",
		"details": ["Flamethrower: sets crowds alight", "Crossbow: one bolt through a whole line of them", "In every level and in Endless"]},
	{"key": "rotline_survivors", "name": "Survivors", "line": "Play as Rosa, Hank, Jules or Mo.",
		"details": ["Four more survivors to play as", "Looks only: nobody is stronger"]},
	{"key": "rotline_complete", "name": "Complete pack", "line": "Everything above, for less than buying each.",
		"details": ["Both chapters, the Arsenal and the Survivors"],
		"includes": ["rotline_chapter2", "rotline_chapter3", "rotline_arsenal", "rotline_survivors"]},
]
const COMPLETE := "rotline_complete"


static func item(key: String) -> Dictionary:
	for it in ITEMS:
		if it.key == key:
			return it
	return {}


static func products() -> Array:
	return ITEMS.map(func(it): return it.key)


static func owns(entitlements: Array, key: String) -> bool:
	# Owned outright, or through the Complete pack.
	if key in entitlements:
		return true
	return key != COMPLETE and COMPLETE in entitlements and key in item(COMPLETE).includes


static func upgrade_cost(level: int) -> int:
	return UPGRADE_COSTS[level] if level >= 0 and level < UPGRADE_COSTS.size() else -1


static func stars_for(fraction: float) -> int:
	if fraction >= 0.75:
		return 3
	return 2 if fraction >= 0.4 else 1


static func price_words(p: Dictionary) -> String:
	# $1.99 once (or a month / a year).
	var amount = p.get("amount")
	if not (amount is float or amount is int):
		return str(p.get("label", ""))
	var money = "$%.2f" % (float(amount) / 100.0)
	var interval = p.get("interval")
	var words = (money + " a " + str(interval)) if interval else (money + " once")
	if int(p.get("trial_days", 0)) > 0:
		words += ", first %d days free" % int(p.trial_days)
	return words


# ------------------------------------------------------------------------------------------------ the grid
const SOLID := "#ctx~fG"        # can't walk through
const BLOCKS_SHOTS := "#ctxG"   # shots stop (fences and water don't)


static func grid_of(lv: Dictionary) -> Array:
	var g = []
	for row in lv.map:
		g.append(row)
	return g


static func is_solid(rows: Array, i: int, j: int) -> bool:
	if j < 0 or j >= rows.size() or i < 0 or i >= rows[j].length():
		return true
	return SOLID.contains(rows[j][i])


static func bfs(rows: Array, starts: Array) -> PackedInt32Array:
	# Steps from the nearest start to every tile (4-way), or a big number where it can't get to.
	var h = rows.size()
	var w: int = rows[0].length()
	var far = 1 << 20
	var dist = PackedInt32Array()
	dist.resize(w * h)
	dist.fill(far)
	var q = PackedInt32Array()
	for s in starts:
		var i: int = s.x
		var j: int = s.y
		if i >= 0 and j >= 0 and i < w and j < h and not is_solid(rows, i, j):
			dist[j * w + i] = 0
			q.append(j * w + i)
	var head = 0
	while head < q.size():
		var cur = q[head]
		head += 1
		var ci = cur % w
		var cj = cur / w
		var d = dist[cur] + 1
		for o in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var ni = ci + o.x
			var nj = cj + o.y
			if ni < 0 or nj < 0 or ni >= w or nj >= h:
				continue
			var k = nj * w + ni
			if dist[k] > d and not SOLID.contains(rows[nj][ni]):
				dist[k] = d
				q.append(k)
	return dist
