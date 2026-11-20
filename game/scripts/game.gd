# SPDX-License-Identifier: GPL-3.0-or-later
# Game (autoload): what you've done (levels, stars, scrap, upgrades, survivor, Endless record), settings, and the
# controls. One small JSON file in the app's own folder.
extends Node

signal changed

const DEFAULTS := {
	"auto_fire": true, "easy": false, "shake": true, "sfx": 0.8, "music": 0.55, "touch": "auto",
	"fullscreen": false, "updates": true, "flashes": true,
}

var path = "user://progress.json"
var data: Dictionary = {}
var touch_seen = false        # a finger touched the screen: show the touch controls
var tv = false                # the shell's TV posture (LUMA_POSTURE=tv), or a big screen far away


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if OS.has_environment("ROTLINE_PROGRESS"):
		path = OS.get_environment("ROTLINE_PROGRESS")
	load_progress()
	_controls()
	tv = OS.get_environment("LUMA_POSTURE") == "tv" or OS.get_environment("LUMA_DEVICE_CLASS") == "tv"
	if setting("fullscreen") and not OS.has_feature("headless"):
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)


func _controls() -> void:
	var keys = {
		"left": [KEY_A, KEY_LEFT], "right": [KEY_D, KEY_RIGHT], "up": [KEY_W, KEY_UP], "down": [KEY_S, KEY_DOWN],
		"dodge": [KEY_SPACE, KEY_SHIFT, KEY_ENTER, KEY_KP_ENTER], "grenade": [KEY_G],
		"next_weapon": [KEY_E, KEY_TAB, KEY_MENU], "prev_weapon": [KEY_Q],
		"pause": [KEY_ESCAPE, KEY_P], "fire_key": [KEY_F],
		"w1": [KEY_1], "w2": [KEY_2], "w3": [KEY_3], "w4": [KEY_4], "w5": [KEY_5], "w6": [KEY_6],
	}
	for action in keys:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.2)
		for k in keys[action]:
			var ev = InputEventKey.new()
			ev.physical_keycode = k
			InputMap.action_add_event(action, ev)
	# a gamepad read directly (outside TV posture the shell passes the pad through untouched)
	var pad = {
		"left": [JOY_BUTTON_DPAD_LEFT], "right": [JOY_BUTTON_DPAD_RIGHT], "up": [JOY_BUTTON_DPAD_UP],
		"down": [JOY_BUTTON_DPAD_DOWN], "dodge": [JOY_BUTTON_A, JOY_BUTTON_RIGHT_SHOULDER],
		"grenade": [JOY_BUTTON_X, JOY_BUTTON_LEFT_SHOULDER], "next_weapon": [JOY_BUTTON_Y], "pause": [JOY_BUTTON_START],
	}
	for action in pad:
		for b in pad[action]:
			var ev = InputEventJoypadButton.new()
			ev.button_index = b
			InputMap.action_add_event(action, ev)
	for spec in [["left", JOY_AXIS_LEFT_X, -1.0], ["right", JOY_AXIS_LEFT_X, 1.0], ["up", JOY_AXIS_LEFT_Y, -1.0],
			["down", JOY_AXIS_LEFT_Y, 1.0]]:
		var ev = InputEventJoypadMotion.new()
		ev.axis = spec[1]
		ev.axis_value = spec[2]
		InputMap.action_add_event(spec[0], ev)
	var trig = InputEventJoypadMotion.new()
	trig.axis = JOY_AXIS_TRIGGER_RIGHT
	trig.axis_value = 1.0
	if not InputMap.has_action("fire_pad"):
		InputMap.add_action("fire_pad", 0.3)
	InputMap.action_add_event("fire_pad", trig)


# ------------------------------------------------------------------------------------------------ the file
func load_progress() -> void:
	data = {}
	if FileAccess.file_exists(path):
		var f = FileAccess.open(path, FileAccess.READ)
		if f:
			var doc = JSON.parse_string(f.get_as_text())
			if doc is Dictionary:
				data = doc


func save() -> void:
	var f = FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_warning("Rotline: couldn't save progress to " + path)
		return
	f.store_string(JSON.stringify(data, " "))
	f.close()
	changed.emit()


func _abs(p: String) -> String:
	return ProjectSettings.globalize_path(p) if p.begins_with("user://") or p.begins_with("res://") else p


# ------------------------------------------------------------------------------------------------ settings
func setting(key: String):
	return data.get("settings", {}).get(key, DEFAULTS.get(key))


func set_setting(key: String, value) -> void:
	if not data.has("settings"):
		data["settings"] = {}
	data.settings[key] = value
	save()


# ------------------------------------------------------------------------------------------------ levels
func level(key: String) -> Dictionary:
	return data.get("levels", {}).get(key, {})


func stars(key: String) -> int:
	return int(level(key).get("stars", 0))


func done(key: String) -> bool:
	return stars(key) > 0


func total_stars() -> int:
	var n = 0
	for lv in Levels.LEVELS:
		n += stars(lv.key)
	return n


func unlocked(key: String) -> bool:
	# Open to play (ignoring whether the chapter is bought): the first level, or the one before is done.
	if key == "endless":
		return true
	for i in Levels.LEVELS.size():
		if Levels.LEVELS[i].key == key:
			return i == 0 or done(Levels.LEVELS[i - 1].key)
	return false


func current() -> String:
	for lv in Levels.LEVELS:
		if not done(lv.key):
			return lv.key
	return Levels.LEVELS[-1].key


func finish(key: String, won: bool, got_stars: int, time: float, kills: int, scrap: int) -> Dictionary:
	# Record an attempt. Scrap is kept win or lose; returns what's new ({"weapon": "shotgun", "best": true, ...}).
	var news = {}
	data["scrap"] = self.scrap() + max(0, scrap)
	var st: Dictionary = data.get("stats", {})
	st["kills"] = int(st.get("kills", 0)) + kills
	st["played"] = int(st.get("played", 0)) + 1
	data["stats"] = st
	if key == "endless":
		var rec: Dictionary = data.get("endless", {})
		if time > float(rec.get("time", 0)):
			rec["time"] = snappedf(time, 0.1)
			news["best"] = true
		rec["kills"] = max(int(rec.get("kills", 0)), kills)
		data["endless"] = rec
	elif won:
		if not data.has("levels"):
			data["levels"] = {}
		var rec: Dictionary = data.levels.get(key, {})
		if got_stars > int(rec.get("stars", 0)):
			rec["stars"] = got_stars
			news["more_stars"] = true
		if not rec.has("time") or time < float(rec.time):
			rec["time"] = snappedf(time, 0.1)
		data.levels[key] = rec
		var w: String = Data.EARNED.get(key, "")
		if w != "":
			var have: Array = data.get("weapons", [])
			if not w in have:
				have.append(w)
				data["weapons"] = have
				news["weapon"] = w
	save()
	return news


# ------------------------------------------------------------------------------------------------ scrap and upgrades
func scrap() -> int:
	return int(data.get("scrap", 0))


func upgrades() -> Dictionary:
	var out = {}
	var have: Dictionary = data.get("upgrades", {})
	for k in Data.UPGRADES:
		out[k] = int(have.get(k, 0))
	return out


func buy_upgrade(key: String) -> bool:
	var lvl: int = upgrades()[key]
	var cost = Data.upgrade_cost(lvl)
	if cost < 0 or scrap() < cost:
		return false
	data["scrap"] = scrap() - cost
	var have: Dictionary = data.get("upgrades", {})
	have[key] = lvl + 1
	data["upgrades"] = have
	save()
	return true


func reset_upgrades() -> int:
	var back = 0
	for k in upgrades():
		for i in upgrades()[k]:
			back += Data.UPGRADE_COSTS[i]
	data["upgrades"] = {}
	data["scrap"] = scrap() + back
	save()
	return back


# ------------------------------------------------------------------------------------------------ weapons and survivors
func weapons(arsenal: bool) -> Array:
	var have = ["pistol"]
	for w in data.get("weapons", []):
		if Data.WEAPONS.has(w):
			have.append(w)
	if arsenal:
		have.append_array(Data.ARSENAL)
	return Data.ORDER.filter(func(w): return w in have)


func survivor() -> String:
	return str(data.get("survivor", "sam"))


func set_survivor(key: String) -> void:
	for s in Data.SURVIVORS:
		if s[0] == key:
			data["survivor"] = key
			save()


func endless_best() -> Array:
	var rec: Dictionary = data.get("endless", {})
	return [float(rec.get("time", 0.0)), int(rec.get("kills", 0))]


func kills() -> int:
	return int(data.get("stats", {}).get("kills", 0))
