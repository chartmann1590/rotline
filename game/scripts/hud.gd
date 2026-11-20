# SPDX-License-Identifier: GPL-3.0-or-later
# The HUD in a level: health, the goal, weapon and ammo, grenades, the streak, the big one's health, banners, and
# arrows at the screen's edge toward what you're looking for.
extends Control

var main
var world: World
var hp_bar: ProgressBar
var goal_label: Label
var goal_bar: ProgressBar
var info: Label
var weapon_row: HBoxContainer
var weapon_labels = {}
var boss_box: VBoxContainer
var boss_bar: ProgressBar
var banner: Label
var combo_label: Label
var _flash = 0.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var top = MarginContainer.new()
	top.set_anchors_preset(Control.PRESET_TOP_WIDE)
	for s in ["left", "right", "top"]:
		top.add_theme_constant_override("margin_" + s, 18)
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(top)
	var row = UI.hbox(14)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top.add_child(row)
	var left = UI.vbox(4)
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(left)
	var hp_row = UI.hbox(8)
	var heart = UI.label("♥", 26, UI.RED)
	hp_row.add_child(heart)
	hp_bar = _bar(Color("#e5484d"), Vector2(260, 18))
	hp_row.add_child(hp_bar)
	left.add_child(hp_row)
	goal_label = UI.title("", 34)
	left.add_child(goal_label)
	goal_bar = _bar(UI.GREEN, Vector2(260, 8))
	left.add_child(goal_bar)
	info = UI.title("", 28, UI.INK)
	info.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	info.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	row.add_child(info)
	var pause = Button.new()
	pause.text = "II"
	pause.custom_minimum_size = Vector2(56, 56)
	pause.focus_mode = Control.FOCUS_NONE
	pause.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	pause.add_theme_font_size_override("font_size", 22)
	pause.pressed.connect(func(): main.pause())
	row.add_child(pause)
	boss_box = UI.vbox(4)
	boss_box.set_anchors_preset(Control.PRESET_CENTER_TOP)
	boss_box.position.y = 92
	boss_box.visible = false
	var bt = UI.title("THE TANK", 32, Color("#ff6a5a"))
	bt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	boss_box.add_child(bt)
	boss_bar = _bar(Color("#b0302a"), Vector2(420, 14))
	boss_box.add_child(boss_bar)
	add_child(boss_box)
	weapon_row = UI.hbox(6)
	weapon_row.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	weapon_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(weapon_row)
	banner = UI.title("", 76, UI.GOLD)
	banner.set_anchors_preset(Control.PRESET_CENTER)
	banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	banner.modulate.a = 0.0
	banner.add_theme_color_override("font_shadow_color", Color(0.5, 0.05, 0.05, 0.9))
	banner.add_theme_constant_override("shadow_outline_size", 20)
	add_child(banner)
	combo_label = UI.title("", 44, UI.GOLD)
	combo_label.set_anchors_preset(Control.PRESET_CENTER_RIGHT)
	combo_label.modulate.a = 0.0
	add_child(combo_label)
	world.hud.connect(_on_world)
	_build_weapons()


func _bar(col: Color, size: Vector2) -> ProgressBar:
	var b = ProgressBar.new()
	b.min_value = 0
	b.max_value = 1
	b.step = 0.001
	b.show_percentage = false
	b.custom_minimum_size = size
	b.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	b.add_theme_stylebox_override("fill", UI._box(col, 8, Color(0, 0, 0, 0), 0))
	b.add_theme_stylebox_override("background", UI._box(Color(0, 0, 0, 0.6), 8, Color(1, 1, 1, 0.15), 1))
	return b


func _build_weapons() -> void:
	for c in weapon_row.get_children():
		c.queue_free()
	weapon_labels.clear()
	var narrow = get_viewport_rect().size.x < 820
	for i in world.player.weapons.size():
		var wkey: String = world.player.weapons[i]
		var b = Button.new()
		b.focus_mode = Control.FOCUS_NONE
		b.custom_minimum_size = Vector2(0, 52)
		b.add_theme_font_size_override("font_size", 16 if narrow else 18)
		b.pressed.connect(func(): world.player.select(wkey))
		weapon_row.add_child(b)
		weapon_labels[wkey] = b


func _on_world(what: String, value) -> void:
	match what:
		"banner":
			banner.text = str(value)
			banner.pivot_offset = banner.size / 2
			var tw = banner.create_tween()
			banner.modulate.a = 0.0
			banner.scale = Vector2.ONE * 1.4
			tw.set_parallel(true)
			tw.tween_property(banner, "modulate:a", 1.0, 0.15)
			tw.tween_property(banner, "scale", Vector2.ONE, 0.25).set_trans(Tween.TRANS_BACK)
			tw.chain().tween_interval(1.4)
			tw.chain().tween_property(banner, "modulate:a", 0.0, 0.5)
		"combo":
			if int(value) >= 3:
				combo_label.text = "×%d  " % int(value)
				combo_label.modulate.a = 1.0
				combo_label.scale = Vector2.ONE * 1.25
				combo_label.pivot_offset = combo_label.size / 2
				combo_label.create_tween().tween_property(combo_label, "scale", Vector2.ONE, 0.15)
			else:
				combo_label.create_tween().tween_property(combo_label, "modulate:a", 0.0, 0.4)


func _process(_delta: float) -> void:
	if world == null or not is_instance_valid(world):
		return
	var p = world.player
	hp_bar.value = p.hp / p.max_hp
	var pr = world.progress()
	goal_label.text = pr[1]
	goal_bar.value = pr[0]
	goal_bar.visible = not world.lv.endless
	info.text = "%d DOWN  ·  %d SCRAP  ·  %d GRENADE%s" % [world.kills, world.scrap, p.grenades, "" if p.grenades == 1 else "S"]
	var b = world.boss()
	boss_box.visible = b != null
	if b:
		boss_bar.value = b.hp / b.max_hp
		boss_box.position.x = (size.x - boss_box.size.x) / 2
	var narrow = size.x < 820
	for i in p.weapons.size():
		var wkey: String = p.weapons[i]
		if not weapon_labels.has(wkey):
			continue
		var btn: Button = weapon_labels[wkey]
		var spec: Dictionary = Data.WEAPONS[wkey]
		var ammo = "∞" if spec.ammo == 0 else str(p.ammo.get(wkey, 0))
		btn.text = ("%s\n%s" % [spec.name.split(" ")[0].left(7), ammo]) if narrow else ("%d  %s   %s" % [i + 1, spec.name, ammo])
		var cur = wkey == p.weapon
		btn.add_theme_stylebox_override("normal", UI._box(Color(0.95, 0.92, 0.86, 0.95) if cur else Color(0, 0, 0, 0.55), 26, Color(0, 0, 0, 0), 0))
		btn.add_theme_color_override("font_color", Color("#15171a") if cur else (Color("#ff8a80") if ammo == "0" else Color(1, 1, 1, 0.8)))
	weapon_row.position = Vector2((size.x - weapon_row.size.x) / 2, size.y - weapon_row.size.y - 18)
	banner.position = Vector2((size.x - banner.size.x) / 2, size.y * 0.3)
	combo_label.position = Vector2(size.x - combo_label.size.x - 24, size.y * 0.42)
	queue_redraw()


func _draw() -> void:
	if world == null or not is_instance_valid(world):
		return
	# arrows at the edge toward the goal, the generator and the big ones
	var xf = world.get_viewport().get_canvas_transform()
	var scale_f = get_viewport().get_visible_rect().size.x / max(1.0, get_viewport().get_visible_rect().size.x)
	var m = 34.0
	var c = size / 2
	for o in world.objectives():
		var sp: Vector2 = xf * o[0] * scale_f
		if sp.x > m and sp.y > m and sp.x < size.x - m and sp.y < size.y - m:
			continue
		var d = (sp - c)
		var k: float = min(abs((c.x - m) / max(abs(d.x), 0.001)), abs((c.y - m) / max(abs(d.y), 0.001)))
		var at = c + d * k
		var a = d.angle()
		var pts = PackedVector2Array([at + Vector2.from_angle(a) * 16, at + Vector2.from_angle(a + 2.5) * 12, at + Vector2.from_angle(a - 2.5) * 12])
		draw_colored_polygon(pts, o[1])
