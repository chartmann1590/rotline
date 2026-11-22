# SPDX-License-Identifier: GPL-3.0-or-later
# Rotline's tests, run inside the real game (autoloads and all), headless:
#   ROTLINE_TEST=all godot --headless --fixed-fps 60 --path game
# ROTLINE_TEST=store runs only the store checks, against a fake license server (tests/test_store.py starts one).
# Prints "ok"/"FAIL" per test and "N passed, M failed", and exits 1 on any failure.
extends Node

var main
var passed = 0
var failed = 0


func run(m) -> void:
	main = m
	await get_tree().process_frame
	var which = OS.get_environment("ROTLINE_TEST")
	Game.path = "user://test-progress-%d.json" % Time.get_ticks_usec()
	Game.data = {}
	if which in ["all", "unit"]:
		for t in ["maps_are_sound", "everything_can_be_reached", "chapters_and_goals", "store_logic", "numbers",
				"progress_records", "upgrades_cost_scrap", "endless_best_and_survivors", "updates_compare"]:
			_test(t, Callable(self, "t_" + t))
	if which in ["all", "sim"]:
		await _atest("rules_in_a_real_world", t_rules)
		await _atest("the_first_chapter_can_be_won", t_fair)
	if which in ["all", "chapters"]:
		await _atest("every_paid_level_can_be_won", t_paid_levels)
	if which == "store":
		await _atest("store_against_fake_server", t_store)
	print("%d passed, %d failed" % [passed, failed])
	get_tree().quit(1 if failed > 0 else 0)


func _test(name: String, fn: Callable) -> void:
	var err = fn.call()
	_report(name, err)


func _atest(name: String, fn: Callable) -> void:
	var err = await fn.call()
	_report(name, err)


func _report(name: String, err) -> void:
	if err == null or err == "":
		passed += 1
		print("ok   ", name)
	else:
		failed += 1
		print("FAIL ", name, ": ", err)


# ------------------------------------------------------------------------------------------------ unit
func t_maps_are_sound():
	var legal = "#.,=ctx~fPSEFGhag"
	for lv in Levels.LEVELS + [Levels.ENDLESS]:
		var rows: Array = lv.map
		var w: int = rows[0].length()
		var all = ""
		for r in rows:
			if r.length() != w:
				return "%s: rows differ in width" % lv.key
			if r[0] != "#" or r[w - 1] != "#":
				return "%s: no wall at the sides" % lv.key
			all += r
		if rows[0].replace("#", "") != "" or rows[-1].replace("#", "") != "":
			return "%s: no wall at the top or bottom" % lv.key
		if all.count("P") != 1:
			return "%s: needs one start" % lv.key
		if all.count("S") < 2:
			return "%s: needs spawn points" % lv.key
		for ch in all:
			if not legal.contains(ch):
				return "%s: unknown tile %s" % [lv.key, ch]
		if lv.goal == "escape" and (all.count("F") != lv.target or all.count("E") == 0):
			return "%s: fuel cans or the way out don't match" % lv.key
		if lv.goal == "defend" and all.count("G") != 1:
			return "%s: needs one generator" % lv.key
		if lv.goal == "boss" and lv.bosses != lv.target:
			return "%s: bosses don't match" % lv.key
	return null


func t_everything_can_be_reached():
	for lv in Levels.LEVELS + [Levels.ENDLESS]:
		var rows: Array = lv.map
		var w: int = rows[0].length()
		var start = Vector2i.ZERO
		for j in rows.size():
			var i = rows[j].find("P")
			if i >= 0:
				start = Vector2i(i, j)
		var d = Data.bfs(rows, [start])
		for j in rows.size():
			for i in w:
				if "SEFhag".contains(rows[j][i]) and d[j * w + i] >= (1 << 20):
					return "%s: %s at %d,%d can't be reached" % [lv.key, rows[j][i], i, j]
	return null


func t_chapters_and_goals():
	if Levels.LEVELS.size() != 12:
		return "12 levels"
	for n in [1, 2, 3]:
		if Levels.in_chapter(n).size() != 4:
			return "4 levels in chapter %d" % n
	var goals = {}
	for lv in Levels.LEVELS:
		goals[lv.goal] = true
	if goals.size() != 5:
		return "five kinds of goal"
	if Levels.next_level("1-4").key != "2-1" or not Levels.next_level("3-4").is_empty():
		return "next level"
	if Levels.goal_words(Levels.by_key("1-2")) != "Find 3 fuel cans, then get out":
		return "goal words"
	return null


func t_store_logic():
	var keys = Data.products()
	if keys != ["rotline_chapter2", "rotline_chapter3", "rotline_arsenal", "rotline_survivors", "rotline_complete"]:
		return "products %s" % [keys]
	for k in keys:
		if not Data.owns(["rotline_complete"], k):
			return "complete pack should include %s" % k
	if Data.owns(["rotline_arsenal"], "rotline_chapter2") or not Data.owns(["rotline_arsenal"], "rotline_arsenal"):
		return "single item"
	if Data.owns(["rotline_arsenal"], "rotline_complete"):
		return "an item isn't the pack"
	for it in Data.ITEMS:
		var words: String = (it.name + it.line + " ".join(PackedStringArray(it.details))).to_lower()
		for bad in ["coin", "gem", "scrap", "boost", "loot", "random"]:
			if words.contains(bad):
				return "%s mentions %s" % [it.key, bad]
	if Data.price_words({"amount": 199, "interval": null}) != "$1.99 once":
		return "price words: " + Data.price_words({"amount": 199, "interval": null})
	if Store.token_exp("eyJleHAiOjEyM30.sig") != 123:
		return "token exp"
	if not Store.valid_email("a@b.co") or Store.valid_email("nope"):
		return "email check"
	return null


func t_numbers():
	if [Data.stars_for(1.0), Data.stars_for(0.75), Data.stars_for(0.5), Data.stars_for(0.1)] != [3, 3, 2, 1]:
		return "stars"
	if Data.upgrade_cost(0) != 30 or Data.upgrade_cost(5) != -1:
		return "upgrade cost"
	for w in Data.ARSENAL:
		if not Data.WEAPONS[w].get("extra", false):
			return "arsenal weapons are extras"
	for k in Data.EARNED:
		if Levels.by_key(k).chapter != 1:
			return "earned weapons come from free levels"
	return null


func t_progress_records():
	Game.data = {}
	if not Game.unlocked("1-1") or Game.unlocked("1-2") or not Game.unlocked("endless"):
		return "unlocking"
	var news = Game.finish("1-1", true, 2, 60.0, 30, 55)
	if not news.get("more_stars", false) or news.get("weapon", "") != "shotgun":
		return "news %s" % [news]
	if not Game.unlocked("1-2") or Game.current() != "1-2" or Game.scrap() != 55:
		return "after a win"
	if not Game.finish("1-1", true, 1, 50.0, 1, 0).is_empty() or Game.stars("1-1") != 2:
		return "fewer stars don't count"
	Game.finish("1-2", false, 0, 20.0, 8, 8)
	if Game.done("1-2") or Game.scrap() != 63:
		return "a loss keeps scrap"
	if Game.weapons(true) != ["pistol", "shotgun", "flamer", "crossbow"]:
		return "weapons %s" % [Game.weapons(true)]
	Game.load_progress()
	if Game.stars("1-1") != 2 or Game.kills() != 39:
		return "saved and loaded: %s at %s" % [Game.data, Game.path]
	return null


func t_upgrades_cost_scrap():
	Game.data = {}
	if Game.buy_upgrade("health"):
		return "no scrap, no upgrade"
	Game.data["scrap"] = 1000
	for i in 5:
		if not Game.buy_upgrade("health"):
			return "buy %d" % i
	if Game.buy_upgrade("health"):
		return "maxed"
	var spent = 0
	for c in Data.UPGRADE_COSTS:
		spent += c
	if Game.scrap() != 1000 - spent or Game.reset_upgrades() != spent or Game.scrap() != 1000:
		return "spent and given back"
	return null


func t_endless_best_and_survivors():
	Game.data = {}
	if not Game.finish("endless", false, 0, 95.4, 60, 60).get("best", false):
		return "first is best"
	Game.finish("endless", false, 0, 50.0, 70, 70)
	var best = Game.endless_best()
	if abs(best[0] - 95.4) > 0.01 or best[1] != 70:
		return "best %s" % [best]
	Game.set_survivor("rosa")
	Game.set_survivor("nobody")
	if Game.survivor() != "rosa":
		return "survivor"
	return null


func t_updates_compare():
	if not Updates.newer("1.2.0", "1.1.9") or Updates.newer("1.0.0", "1.0.0") or not Updates.newer("v2.0", "1.9.9"):
		return "version compare"
	return null


# ------------------------------------------------------------------------------------------------ in a real world
func _world(key: String, weapons := ["pistol"]) -> World:
	var w = World.new()
	main.holder.add_child(w)
	w.setup(key, {"weapons": weapons, "seed": 1})
	return w


func t_rules():
	var w = _world("1-1")
	w._spawn_acc = -9999.0
	for z in w.zombies.duplicate():
		w.kill(z)
	var start_kills = w.kills
	var z = Zombie.new()
	z.setup(w, "walker", w.player.global_position + Vector2(4 * Data.TILE, 0))
	w.actors.add_child(z)
	w.zombies.append(z)
	w.input_source = func(): return {"move": Vector2.ZERO, "aim": null, "fire": false, "auto_fire": true, "dodge": false, "grenade": false, "switch": 0}
	for i in 240:
		await get_tree().physics_frame
		w._spawn_acc = -9999.0
	if w.kills <= start_kills:
		w.queue_free()
		return "it should aim, fire and put the walker down (kills %d)" % w.kills
	if w.player.shots < 2:
		w.queue_free()
		return "shots"
	w.time = w.lv.target - 0.05
	for i in 10:
		await get_tree().physics_frame
	var ok = w.state == "won" and w.stars() == 3 and w.bonus() == 45
	w.queue_free()
	if not ok:
		return "survive should end the level: %s" % w.state
	var e = _world("1-2")
	e._spawn_acc = -9999.0
	for pk in e.pickups.duplicate():
		if pk[1] == "fuel":
			e.player.global_position = pk[0].global_position
			for i in 3:
				await get_tree().physics_frame
	if e.fuel != 3 or not e.exit_open():
		var left = e.pickups.filter(func(pk): return pk[1] == "fuel").map(func(pk): return pk[0].global_position)
		var at = e.player.global_position
		var q = PhysicsPointQueryParameters2D.new()
		q.position = Vector2(288, 1056)
		q.collision_mask = 0xFFFF
		var hits = e.get_world_2d().direct_space_state.intersect_point(q)
		print("     cell ", e.floor_layer.get_cell_atlas_coords(Vector2i(4, 16)), " water ", e.water_layer.get_cell_atlas_coords(Vector2i(4, 16)), " row ", e.rows[16], " below ", e.floor_layer.get_cell_atlas_coords(Vector2i(4, 17)))
		for hh in hits:
			var co = hh.collider
			var owner = co.shape_find_owner(hh.shape)
			var sh = co.shape_owner_get_owner(owner)
			print("     hit ", co.get_parent().name, " body at ", co.global_position, " rot ", co.rotation, " shape at ", sh.position, " ", sh.shape, " size ", sh.shape.size if sh.shape is RectangleShape2D else sh.shape.radius)
		e.queue_free()
		return "fuel %d; left %s; player %s; state %s; ts %s" % [e.fuel, left, at, e.state, Engine.time_scale]
	var ex: Vector2i = e.exits[0]
	e.player.global_position = Vector2(ex.x * Data.TILE + 32, ex.y * Data.TILE + 32)
	for i in 4:
		await get_tree().physics_frame
	var won = e.state == "won"
	e.queue_free()
	if not won:
		return "escape"
	var d = _world("2-2")
	d.gen_hp = 0.5
	d.hit_generator(1.0)
	for i in 2:
		await get_tree().physics_frame
	var lost = d.state == "lost" and d.why.contains("generator")
	d.queue_free()
	if not lost:
		return "defend should be lost with the generator"
	return null


func _bot(w: World, cache: Dictionary) -> Dictionary:
	var p = w.player
	var away = Vector2.ZERO
	for z in w.zombies:
		var dv: Vector2 = p.global_position - z.global_position
		var d = dv.length()
		if d < 4.5 * Data.TILE and d > 0.1:
			away += dv / d * (4.5 * Data.TILE - d) / (4.5 * Data.TILE) * (2.0 if z.kind in ["tank", "bloater"] else 1.0)
	var goal = Vector2.ZERO
	var tgt = null
	if w.lv.goal == "escape":
		var best = INF
		for pk in w.pickups:
			if pk[1] == "fuel" and pk[0].global_position.distance_to(p.global_position) < best:
				best = pk[0].global_position.distance_to(p.global_position)
				tgt = pk[0].global_position
		if tgt == null:
			tgt = Vector2(w.exits[0].x * Data.TILE + 32, w.exits[0].y * Data.TILE + 32)
	if tgt != null:
		var key = Vector2i(int(tgt.x / Data.TILE), int(tgt.y / Data.TILE))
		if cache.get("k") != key:
			cache["k"] = key
			cache["f"] = Data.bfs(w.rows, [key])
		goal = w.follow(cache["f"], p.global_position)
	for i in range(p.weapons.size() - 1, -1, -1):
		if p.has_ammo(p.weapons[i]):
			if p.weapon != p.weapons[i]:
				p.select(p.weapons[i])
			break
	return {"move": goal + away * 1.5, "aim": null, "fire": false, "auto_fire": true, "dodge": false, "grenade": false, "switch": 0}


func t_fair():
	# A simple bot wins every free level with no upgrades (2 of 3 tries), so Chapter 1 is fair, not impossible.
	var weapons = {"1-1": ["pistol"], "1-2": ["pistol", "shotgun"], "1-3": ["pistol", "shotgun", "smg"],
		"1-4": ["pistol", "shotgun", "smg", "rifle"]}
	for key in weapons:
		var wins = 0
		for s in 3:
			var w = World.new()
			main.holder.add_child(w)
			w.setup(key, {"weapons": weapons[key], "seed": s + 1})
			var cache = {}
			w.input_source = func(): return _bot(w, cache)
			var frames = 0
			while w.state == "play" and w.time < 300 and frames < 300 * 60:
				await get_tree().physics_frame
				frames += 1
			if w.state == "won":
				wins += 1
			print("     %s try %d: %s at %.0f s, %d down, %.0f hp, spawned %d, at %s, ts %s" % [key, s + 1, w.state, w.time, w.kills, w.player.hp, w.spawned, w.player.global_position, Engine.time_scale])
			w.queue_free()
			await get_tree().process_frame
		if wins < 2:
			return "%s won %d of 3" % [key, wins]
	return null


func _bot_skilled(w: World, cache: Dictionary) -> Dictionary:
	# _bot plus the two things a player does against the Tank: roll sideways out of its windup/charge, and throw
	# grenades at it.
	var inp = _bot(w, cache)
	var p = w.player
	for z in w.zombies:
		if z.kind != "tank":
			continue
		var dv: Vector2 = z.global_position - p.global_position
		if z.state in ["windup", "charge"] and dv.length() < 7.0 * Data.TILE:
			inp["move"] = dv.orthogonal().normalized()
			inp["dodge"] = true
		elif dv.length() < 6.0 * Data.TILE and dv.length() > 2.5 * Data.TILE and p.grenades > 0:
			inp["grenade"] = true
	return inp


func t_paid_levels():
	# A bot with the Chapter 1 guns and two levels of every Armory upgrade (450 scrap: Chapter 1 plus a replay or two)
	# plays Chapters 2 and 3. Every level, each Tank fight included, must be won at least once in 5 tries. The bot only
	# kites, rolls sideways when a Tank winds up and throws its grenades; a player does far better. Before 1.0.1 the
	# Tanks came all at once and 2-4 and 3-4 could not be won even with every upgrade bought.
	var guns = ["pistol", "shotgun", "smg", "rifle"]
	var bad = []
	var only = OS.get_environment("ROTLINE_LEVELS")
	for key in (only.split(",") if only != "" else ["2-1", "2-2", "2-3", "2-4", "3-1", "3-2", "3-3", "3-4"]):
		var wins = 0
		for s in 5:
			var w = World.new()
			main.holder.add_child(w)
			var u = int(OS.get_environment("ROTLINE_UPG")) if OS.get_environment("ROTLINE_UPG") != "" else 2
			var g = OS.get_environment("ROTLINE_GUNS").split(",") if OS.get_environment("ROTLINE_GUNS") != "" else guns
			w.setup(key, {"weapons": g, "seed": s + 1, "upgrades": {"health": u, "damage": u, "rate": u, "speed": u, "ammo": u}})
			var cache = {}
			w.input_source = func(): return _bot_skilled(w, cache)
			var frames = 0
			while w.state == "play" and w.time < 420 and frames < 420 * 60:
				await get_tree().physics_frame
				frames += 1
			if w.state == "won":
				wins += 1
			var tanks = []
			for z in w.zombies:
				if z.kind == "tank":
					tanks.append(int(z.hp))
			print("     %s try %d: %s at %.0f s, %d down, %.0f hp, spawned %d, tanks left %s" % [key, s + 1, w.state, w.time, w.kills, w.player.hp, w.spawned, tanks])
			w.queue_free()
			await get_tree().process_frame
			if wins > 0:
				break
		if wins < 1:
			bad.append(key)
	return null if bad.is_empty() else "won 0 of 5: %s" % ", ".join(bad)


# ------------------------------------------------------------------------------------------------ the store
func t_store():
	Store.open_in_browser = false
	Store.path = "user://test-license-%d.json" % Time.get_ticks_usec()
	Store.state = {}
	await Store.load_catalog()
	if Store.price("rotline_chapter2") != "$1.99 once" or Store.price("rotline_complete") != "$3.99 once":
		return "catalog: %s %s" % [Store.catalog, Store.catalog_error]
	await Store.buy("rotline_chapter2", "qa@example.com")
	if Store.opened.is_empty() or not Store.opened[-1].begins_with("https://checkout.stripe.com/"):
		return "checkout not opened"
	if Store.waiting_for == "":
		return "not waiting for the session"
	var t = 0
	while not Store.owns("rotline_chapter2") and t < 200:
		await get_tree().create_timer(0.1).timeout
		t += 1
	if not Store.owns("rotline_chapter2") or Store.owns("rotline_chapter3"):
		return "chapter 2 should be owned, chapter 3 not: %s" % [Store.entitlements()]
	await Store.restore("qa@example.com")
	if not Store.owns("rotline_complete") or not Store.owns("rotline_arsenal"):
		return "restore should bring the complete pack: %s" % [Store.entitlements()]
	return null
