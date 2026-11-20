# SPDX-License-Identifier: GPL-3.0-or-later
# Development only: walk the game through steps and save screenshots, for the README and the store listing.
#   ROTLINE_DEVSHOT='unlock_all()|main.start("2-2", false)|wait 8|shot("play")|quit()'
# Each step is a Godot Expression run on this node (with `main` and `world`), or "wait N".
extends Node

var main
var out_dir = "/tmp"


func run(m) -> void:
	main = m
	out_dir = OS.get_environment("ROTLINE_SHOTS") if OS.has_environment("ROTLINE_SHOTS") else "user://shots"
	DirAccess.make_dir_recursive_absolute(out_dir)
	_steps.call_deferred(OS.get_environment("ROTLINE_DEVSHOT").split("|"))


func _steps(steps: PackedStringArray) -> void:
	await get_tree().create_timer(1.0, true, false, true).timeout
	for s in steps:
		s = s.strip_edges()
		if s == "":
			continue
		if s.begins_with("wait "):
			await get_tree().create_timer(float(s.substr(5)), true, false, true).timeout
			continue
		var e = Expression.new()
		if e.parse(s, ["main", "world"]) != OK:
			printerr("DEVSHOT bad step: ", s, " ", e.get_error_text())
			continue
		e.execute([main, main.world], self)
		if e.has_execute_failed():
			printerr("DEVSHOT failed: ", s, " ", e.get_error_text())
		await get_tree().process_frame
	print("DEVSHOT done")


func shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	var img = get_viewport().get_texture().get_image()
	img.save_png(out_dir.path_join(name + ".png"))
	print("SHOT ", name, " ", img.get_size())


func unlock_all() -> void:
	var lv = {}
	for l in Levels.LEVELS:
		lv[l.key] = {"stars": 3}
	Game.data["levels"] = lv
	Game.data["weapons"] = ["shotgun", "smg", "rifle"]
	Game.save()


func progress(levels: int, scrap: int) -> void:
	var lv = {}
	for i in levels:
		lv[Levels.LEVELS[i].key] = {"stars": 3 - i % 2}
	Game.data["levels"] = lv
	Game.data["weapons"] = ["shotgun", "smg", "rifle"].slice(0, min(3, levels))
	Game.data["scrap"] = scrap
	Game.data["upgrades"] = {"health": 2, "damage": 1, "rate": 1}
	Game.save()


func own_all() -> void:
	Store.state = {"email": "", "entitlements": ["rotline_complete"]}
	Store.owned_changed.emit()


func touch_on() -> void:
	Game.touch_seen = true


func pick(w: String) -> void:
	main.world.player.select(w)


func hurt(n: float) -> void:
	main.world.player.hp -= n


func quit() -> void:
	get_tree().quit()
