# SPDX-License-Identifier: GPL-3.0-or-later
# Rotline's root: the menus (over a live, lit street with the dead wandering it), the campaign map, the Armory,
# the Survivors, the store, settings, and playing a level with its briefing, pause and result.
extends Node

const HUD := preload("res://scripts/hud.gd")
const Touch := preload("res://scripts/touch.gd")
const Thumb := preload("res://scripts/ui/map_thumb.gd")

var world: World
var holder: Node
var ui: CanvasLayer
var screen: Control
var overlay: Control          # a card over the arena (brief, pause, result) or a dialog
var post: ColorRect
var hud: Control
var touch: Control
var toast_box: VBoxContainer
var playing = ""             # the level key while in a level
var where = "menu"
var chapter_tab = 1
var _last_size = Vector2.ZERO
var _hold = {}               # TV keys: arrow -> time to keep walking until
var _tap_chain = {}
var _pressed_at = {}
var mouse_t = -9.0
var mouse_down = false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	get_window().min_size = Vector2i(360, 300)
	holder = Node.new()
	holder.process_mode = Node.PROCESS_MODE_PAUSABLE
	add_child(holder)
	var post_layer = CanvasLayer.new()
	post_layer.layer = 5
	add_child(post_layer)
	post = ColorRect.new()
	post.set_anchors_preset(Control.PRESET_FULL_RECT)
	post.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var pm = ShaderMaterial.new()
	pm.shader = load("res://shaders/post.gdshader")
	post.material = pm
	post_layer.add_child(post)
	ui = CanvasLayer.new()
	ui.layer = 10
	add_child(ui)
	var root = Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UI.theme()
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(root)
	screen = Control.new()
	screen.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(screen)
	toast_box = UI.vbox(8)
	toast_box.set_anchors_preset(Control.PRESET_CENTER_TOP)
	toast_box.position.y = 18
	toast_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(toast_box)
	Store.message.connect(toast)
	Store.owned_changed.connect(_refresh)
	Store.catalog_loaded.connect(_refresh)
	Store.waiting_changed.connect(_refresh)
	Updates.found.connect(_refresh)
	get_tree().create_timer(1.5).timeout.connect(Store.load_catalog)
	_fit()
	if OS.has_environment("ROTLINE_TEST"):
		where = "test"
		var tests: Node = load("res://tests/run_tests.gd").new()
		add_child(tests)
		tests.run(self)
		return
	if OS.has_environment("ROTLINE_DEVSHOT"):
		var shot: Node = load("res://tests/devshot.gd").new()
		add_child(shot)
		shot.run(self)
	show_menu()


func _process(_delta: float) -> void:
	_fit()
	if world and playing != "" and post.material:
		var p = world.player
		post.material.set_shader_parameter("hurt", clamp(p.hurt_t * 2.0, 0.0, 1.0))
		post.material.set_shader_parameter("low", clamp(1.0 - p.hp / (p.max_hp * 0.35), 0.0, 1.0))
	elif post.material:
		post.material.set_shader_parameter("hurt", 0.0)
		post.material.set_shader_parameter("low", 0.0)


func _fit() -> void:
	# scale the interface to the screen: ~1 on a laptop, bigger on a TV, smaller but usable on a phone
	var s = Vector2(get_window().size)
	if s == _last_size:
		return
	_last_size = s
	var f: float = clamp(min(s.x / 1180.0, s.y / 700.0), 0.72, 2.4)
	if Game.tv:
		f = max(f, s.y / 620.0)
	get_window().content_scale_factor = f


func _refresh() -> void:
	if playing != "":
		return
	if overlay and is_instance_valid(overlay) and overlay.has_meta("store_item"):
		var key: String = overlay.get_meta("store_item")
		_close_overlay()
		buy_dialog(key)
		return
	match where:
		"menu":
			show_menu()
		"campaign":
			show_campaign(chapter_tab)
		"store":
			show_store()
		"armory":
			show_armory()
		"survivors":
			show_survivors()


# ------------------------------------------------------------------------------------------------ helpers
func _clear() -> void:
	for c in screen.get_children():
		c.queue_free()
	_close_overlay()


func _close_overlay() -> void:
	if overlay and is_instance_valid(overlay):
		overlay.queue_free()
	overlay = null


func _focus_first(node: Node) -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	if not is_instance_valid(node):
		return
	var b = _find_focusable(node)
	if b:
		b.grab_focus()


func _find_focusable(node: Node) -> Control:
	if node is Control and (node as Control).focus_mode == Control.FOCUS_ALL and node.is_visible_in_tree() and not (node is Button and node.disabled):
		return node
	for c in node.get_children():
		var f = _find_focusable(c)
		if f:
			return f
	return null


func toast(text: String, kind := "info") -> void:
	var c = UI.card(Color(0.08, 0.09, 0.1, 0.95), 14)
	var l = UI.label(text, 18, UI.GREEN if kind == "done" else (UI.RED if kind == "error" else UI.INK), true)
	l.custom_minimum_size = Vector2(min(520, get_viewport().get_visible_rect().size.x - 40), 0)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	c.add_child(l)
	toast_box.add_child(c)
	toast_box.position.x = (get_viewport().get_visible_rect().size.x - l.custom_minimum_size.x - 32) / 2
	var tw = c.create_tween()
	tw.tween_interval(3.5)
	tw.tween_property(c, "modulate:a", 0.0, 0.4)
	tw.tween_callback(c.queue_free)


func _page(title: String, back: Callable) -> VBoxContainer:
	# a full-screen page over the darkened background: a header with Back, and a scrolling body
	var bg = ColorRect.new()
	bg.color = Color(0.03, 0.03, 0.04, 0.78)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.add_child(bg)
	var margin = MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 28)
	screen.add_child(margin)
	var col = UI.vbox(16)
	margin.add_child(col)
	var head = UI.hbox(18)
	head.add_child(UI.button("‹  Back", back))
	head.add_child(UI.title(title, 54))
	col.add_child(head)
	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	col.add_child(scroll)
	var body = UI.vbox(16)
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(body)
	return body


func _grid(min_card := 280.0) -> GridContainer:
	var g = GridContainer.new()
	var width = get_viewport().get_visible_rect().size.x - 80
	g.columns = max(1, int(width / min_card))
	g.add_theme_constant_override("h_separation", 14)
	g.add_theme_constant_override("v_separation", 14)
	g.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return g


func _background() -> void:
	# the menu's backdrop: Endless's street at night with the dead wandering it
	if world and world.demo:
		return
	_free_world()
	world = World.new()
	holder.add_child(world)
	world.setup("endless", {"demo": true, "theme": "downtown"})
	Sfx.play_music("music_menu")


func _free_world() -> void:
	if world:
		world.queue_free()
		world = null
	Engine.time_scale = 1.0


# ------------------------------------------------------------------------------------------------ the menu
func show_menu() -> void:
	where = "menu"
	playing = ""
	get_tree().paused = false
	_background()
	_clear()
	_hide_hud()
	var shade = TextureRect.new()
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	var grad = GradientTexture2D.new()
	var g = Gradient.new()
	g.set_color(0, Color(0.02, 0.02, 0.03, 0.92))
	g.set_color(1, Color(0.02, 0.02, 0.03, 0.0))
	grad.gradient = g
	grad.fill_from = Vector2(0, 0.5)
	grad.fill_to = Vector2(0.85, 0.5)
	shade.texture = grad
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	screen.add_child(shade)
	var margin = MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 56)
	margin.add_theme_constant_override("margin_top", 40)
	margin.add_theme_constant_override("margin_bottom", 32)
	margin.add_theme_constant_override("margin_right", 28)
	screen.add_child(margin)
	var scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	margin.add_child(scroll)
	var col = UI.vbox(10)
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(col)
	var logo = UI.title("ROTLINE", 112, Color("#e9e2d4"))
	logo.add_theme_color_override("font_shadow_color", Color(0.6, 0.05, 0.05, 0.85))
	logo.add_theme_constant_override("shadow_offset_x", 0)
	logo.add_theme_constant_override("shadow_offset_y", 0)
	logo.add_theme_constant_override("shadow_outline_size", 28)
	col.add_child(logo)
	col.add_child(UI.label("Hold out. Find a way out. Don't get bitten.", 22, UI.DIM))
	col.add_child(UI.spacer())
	var buttons = UI.vbox(7)
	buttons.custom_minimum_size = Vector2(380, 0)
	buttons.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	var cur = Levels.by_key(Game.current())
	var cont = "Continue  ·  %s %s" % [cur.key, cur.name]
	if Game.total_stars() == 0:
		cont = "Play  ·  1-1 First Night"
	buttons.add_child(UI.button(cont, continue_campaign, true, 24))
	buttons.add_child(UI.button("Campaign", func(): show_campaign(Levels.by_key(Game.current()).chapter)))
	buttons.add_child(UI.button("Endless", func(): start("endless")))
	buttons.add_child(UI.button("Armory  ·  %d scrap" % Game.scrap(), show_armory))
	buttons.add_child(UI.button("Survivors", show_survivors))
	buttons.add_child(UI.button("Store", show_store))
	buttons.add_child(UI.button("Settings", show_settings))
	if not OS.has_environment("FLATPAK_ID") or OS.get_name() != "Linux":
		buttons.add_child(UI.button("Quit", func(): get_tree().quit()))
	col.add_child(buttons)
	if not Updates.latest.is_empty():
		var up = UI.button("Rotline %s is out  ·  What's new" % Updates.latest.version, update_dialog)
		up.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		col.add_child(up)
	var foot = UI.label("%d of 36 stars  ·  %d put down  ·  v%s" % [Game.total_stars(), Game.kills(), Updates.VERSION], 16, UI.DIM)
	col.add_child(foot)
	_focus_first(buttons)


func continue_campaign() -> void:
	var lv = Levels.by_key(Game.current())
	if lv.chapter > 1 and not Store.owns(Levels.CHAPTER_PRODUCTS[lv.chapter]):
		buy_dialog(Levels.CHAPTER_PRODUCTS[lv.chapter])
		return
	start(lv.key)


# ------------------------------------------------------------------------------------------------ the campaign
func show_campaign(tab := 1) -> void:
	where = "campaign"
	chapter_tab = tab
	_background()
	_clear()
	var body = _page("Campaign", show_menu)
	var tabs = UI.hbox(10)
	for ch in Levels.CHAPTERS:
		var n: int = ch.number
		var got = 0
		for lv in Levels.in_chapter(n):
			got += Game.stars(lv.key)
		var b = UI.button("%d  %s   %d★" % [n, ch.name, got], func(): show_campaign(n), n == tab, 20)
		tabs.add_child(b)
	body.add_child(tabs)
	var ch: Dictionary = Levels.CHAPTERS[tab - 1]
	var open = tab == 1 or Store.owns(Levels.CHAPTER_PRODUCTS[tab])
	body.add_child(UI.label(ch.blurb, 20, UI.DIM, true))
	if not open:
		var key: String = Levels.CHAPTER_PRODUCTS[tab]
		var p = Store.price(key)
		body.add_child(UI.button("Get Chapter %d%s" % [tab, ("  ·  " + p) if p != "" else ""], func(): buy_dialog(key), true))
	var grid = _grid(300)
	for lv in Levels.in_chapter(tab):
		grid.add_child(_level_card(lv, open))
	body.add_child(grid)
	_focus_first(tabs.get_child(tab - 1))


func _level_card(lv: Dictionary, open: bool) -> Button:
	var unlocked = Game.unlocked(lv.key)
	var b = Button.new()
	b.focus_mode = Control.FOCUS_ALL
	b.custom_minimum_size = Vector2(280, 260)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v = UI.vbox(6)
	v.set_anchors_preset(Control.PRESET_FULL_RECT)
	v.offset_left = 14
	v.offset_right = -14
	v.offset_top = 12
	v.offset_bottom = -12
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var thumb = Thumb.new()
	thumb.level = lv
	thumb.locked = not (open and unlocked)
	thumb.custom_minimum_size = Vector2(0, 120)
	thumb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(thumb)
	var head = UI.hbox(8)
	head.mouse_filter = Control.MOUSE_FILTER_IGNORE
	head.add_child(UI.title(lv.key, 30, UI.GOLD))
	head.add_child(UI.title(lv.name, 30))
	v.add_child(head)
	var goal = UI.label(Levels.goal_words(lv), 17, UI.DIM, true)
	v.add_child(goal)
	if not open:
		v.add_child(UI.label("In Chapter %d, from the store" % lv.chapter, 16, UI.GOLD))
	elif not unlocked:
		v.add_child(UI.label("Finish the level before first", 16, UI.DIM))
	else:
		v.add_child(UI.stars(Game.stars(lv.key), 24))
	for c in v.get_children():
		c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(v)
	b.tooltip_text = lv.brief
	b.pressed.connect(func():
		Sfx.play("ui_ok", 0.02)
		if not open:
			buy_dialog(Levels.CHAPTER_PRODUCTS[lv.chapter])
		elif not unlocked:
			toast("Finish the level before this one first")
		else:
			start(lv.key))
	b.focus_entered.connect(func(): Sfx.play("ui_move", 0.03))
	return b


# ------------------------------------------------------------------------------------------------ the Armory
func show_armory() -> void:
	where = "armory"
	_background()
	_clear()
	var body = _page("Armory", show_menu)
	body.add_child(UI.title("%d SCRAP" % Game.scrap(), 44, UI.GOLD))
	body.add_child(UI.label("Earned from every one you put down, and for finishing levels. You keep it even when you lose.", 18, UI.DIM, true))
	var ups = Game.upgrades()
	var first: Control = null
	for key in Data.UPGRADES:
		var lvl: int = ups[key]
		var cost = Data.upgrade_cost(lvl)
		var row = UI.card()
		var h = UI.hbox(16)
		row.add_child(h)
		var words = UI.vbox(2)
		words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		words.add_child(UI.title(Data.UPGRADES[key][0], 30))
		words.add_child(UI.label("%s a level  ·  level %d of 5" % [Data.UPGRADES[key][1], lvl], 17, UI.DIM, true))
		h.add_child(words)
		var pips = UI.label("●".repeat(lvl) + "○".repeat(5 - lvl), 24, UI.GOLD)
		h.add_child(pips)
		var btn: Button
		if cost < 0:
			btn = UI.button("Maxed", func(): pass)
			btn.disabled = true
		else:
			btn = UI.button("Upgrade  ·  %d" % cost, func(): _upgrade(key), Game.scrap() >= cost)
			btn.disabled = Game.scrap() < cost
		btn.custom_minimum_size.x = 200
		h.add_child(btn)
		body.add_child(row)
		if first == null and not btn.disabled:
			first = btn
	var reset = UI.button("Give back all upgrade scrap", func():
		var back = Game.reset_upgrades()
		toast("%d scrap back to spend" % back if back > 0 else "No upgrades to undo")
		show_armory())
	reset.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	body.add_child(reset)
	body.add_child(UI.title("WEAPONS", 40))
	var have = Game.weapons(Store.owns("rotline_arsenal"))
	var grid = _grid(300)
	for wkey in Data.ORDER:
		var spec: Dictionary = Data.WEAPONS[wkey]
		var c = UI.card()
		var v = UI.vbox(6)
		c.add_child(v)
		var top = UI.hbox(10)
		var icon = TextureRect.new()
		icon.texture = load("res://assets/guns/%s.png" % wkey)
		icon.custom_minimum_size = Vector2(80, 80)
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.modulate = Color.WHITE if wkey in have else Color(1, 1, 1, 0.35)
		top.add_child(icon)
		top.add_child(UI.title(spec.name, 32))
		v.add_child(top)
		var dmg = "%d" % spec.damage + ("×%d" % spec.pellets if spec.pellets > 1 else "")
		v.add_child(UI.label("Damage %s · %.1f a second · reach %d" % [dmg, 1.0 / spec.rate, spec.range], 16, UI.DIM, true))
		var state = ""
		if wkey in have:
			state = "Unlimited ammo" if spec.ammo == 0 else "Starts with %d rounds" % spec.ammo
		elif spec.get("extra", false):
			state = "In the Arsenal pack"
		else:
			for lk in Data.EARNED:
				if Data.EARNED[lk] == wkey:
					state = "Found when you finish %s" % lk
		v.add_child(UI.label(state, 17, UI.INK if wkey in have else UI.GOLD))
		grid.add_child(c)
	body.add_child(grid)
	if not Store.owns("rotline_arsenal"):
		var get_it = UI.button("See the Arsenal", func(): buy_dialog("rotline_arsenal"))
		get_it.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		body.add_child(get_it)
	_focus_first(first if first else body)


func _upgrade(key: String) -> void:
	if Game.buy_upgrade(key):
		Sfx.play("pickup", 0.0)
		toast("%s upgraded" % Data.UPGRADES[key][0], "done")
		show_armory()


# ------------------------------------------------------------------------------------------------ survivors
func show_survivors() -> void:
	where = "survivors"
	_background()
	_clear()
	var body = _page("Survivors", show_menu)
	body.add_child(UI.label("Who you play as. It's only looks: everyone is as tough as everyone else.", 18, UI.DIM, true))
	var grid = _grid(230)
	var focus: Control = null
	for s in Data.SURVIVORS:
		var key: String = s[0]
		var open: bool = not s[3] or Store.owns("rotline_survivors")
		var chosen = Game.survivor() == key
		var b = Button.new()
		b.focus_mode = Control.FOCUS_ALL
		b.custom_minimum_size = Vector2(210, 280)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if chosen:
			b.add_theme_stylebox_override("normal", UI._box(Color("#2b2616"), 12, UI.GOLD, 2))
		var v = UI.vbox(4)
		v.set_anchors_preset(Control.PRESET_FULL_RECT)
		v.offset_left = 12
		v.offset_right = -12
		v.offset_top = 10
		v.offset_bottom = -10
		var a = AtlasTexture.new()
		a.atlas = load("res://assets/people/%s.png" % key)
		a.region = Rect2(0, 0, 128, 128)
		var pic = TextureRect.new()
		pic.texture = a
		pic.custom_minimum_size = Vector2(0, 150)
		pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		pic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		pic.modulate = Color.WHITE if open else Color(1, 1, 1, 0.35)
		v.add_child(pic)
		v.add_child(UI.title(s[1] + ("  ✓" if chosen else ""), 34, UI.GOLD if chosen else UI.INK))
		v.add_child(UI.label(s[2], 16, UI.DIM, true))
		if not open:
			v.add_child(UI.label("In the Survivors pack", 16, UI.GOLD))
		for c in v.get_children():
			c.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		b.add_child(v)
		b.pressed.connect(func():
			Sfx.play("ui_ok", 0.02)
			if open:
				Game.set_survivor(key)
				toast("Playing as %s" % s[1], "done")
				show_survivors()
			else:
				buy_dialog("rotline_survivors"))
		b.focus_entered.connect(func(): Sfx.play("ui_move", 0.03))
		grid.add_child(b)
		if chosen:
			focus = b
	body.add_child(grid)
	_focus_first(focus if focus else grid)


# ------------------------------------------------------------------------------------------------ the store
func show_store() -> void:
	where = "store"
	_background()
	_clear()
	if Store.catalog.is_empty() and not Store.catalog_loading:
		Store.load_catalog()
	var body = _page("Store", show_menu)
	body.add_child(UI.label("One-time unlocks that are yours to keep. Chapter 1, Endless and every upgrade are free, and scrap is only earned by playing. No ads, no coins, no boxes of chance.", 18, UI.DIM, true))
	if Store.catalog_error != "":
		var note = UI.card(Color("#24201a"))
		note.add_child(UI.label(Store.catalog_error, 18, UI.INK, true))
		body.add_child(note)
	var grid = _grid(320)
	var first: Control = null
	for it in Data.ITEMS:
		var c = UI.card(Color("#2a2414") if it.key == Data.COMPLETE else UI.CARD)
		var v = UI.vbox(8)
		c.add_child(v)
		v.add_child(UI.title(it.name, 34, UI.GOLD if it.key == Data.COMPLETE else UI.INK))
		v.add_child(UI.label(it.line, 18, UI.INK, true))
		for d in it.details:
			v.add_child(UI.label("•  " + d, 16, UI.DIM, true))
		v.add_child(UI.spacer())
		var b: Button
		if Store.owns(it.key):
			b = UI.button("✓  Yours", func(): pass)
			b.disabled = true
		else:
			var p = Store.price(it.key)
			var key: String = it.key
			b = UI.button("Get" + (("  ·  " + p) if p != "" else ""), func(): buy_dialog(key), it.key == Data.COMPLETE)
			if first == null:
				first = b
		v.add_child(b)
		grid.add_child(c)
	body.add_child(grid)
	var restore = UI.button("Restore purchases", restore_dialog)
	restore.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	body.add_child(restore)
	_focus_first(first if first else restore)


func _dialog(title: String) -> VBoxContainer:
	_close_overlay()
	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.6)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.get_parent().add_child(dim)
	overlay = dim
	var center = CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.add_child(center)
	var panel = PanelContainer.new()
	var vs = get_viewport().get_visible_rect().size
	panel.custom_minimum_size = Vector2(min(560, vs.x - 32), 0)
	center.add_child(panel)
	var v = UI.vbox(12)
	panel.add_child(v)
	v.add_child(UI.title(title, 46))
	return v


func buy_dialog(key: String) -> void:
	var it = Data.item(key)
	var v = _dialog(it.name)
	overlay.set_meta("store_item", key)
	v.add_child(UI.label(it.line, 19, UI.INK, true))
	for d in it.details:
		v.add_child(UI.label("•  " + d, 16, UI.DIM, true))
	if Store.owns(key):
		v.add_child(UI.label("It's yours. Thank you for supporting Hartmann Studios.", 18, UI.GREEN, true))
		v.add_child(UI.button("Close", _close_overlay, true))
		_focus_first(v)
		return
	if Store.waiting_for != "":
		v.add_child(UI.label("Finish paying in your browser. This unlocks by itself as soon as Stripe confirms it.", 18, UI.INK, true))
		v.add_child(UI.button("Cancel", func():
			Store.cancel_wait()
			_close_overlay()))
		_focus_first(v)
		return
	var p = Store.price(key)
	if p == "":
		v.add_child(UI.label(Store.catalog_error if Store.catalog_error != "" else "Getting the price…", 18, UI.DIM, true))
		v.add_child(UI.button("Try again", func():
			Store.catalog_error = ""
			Store.load_catalog()))
		v.add_child(UI.button("Close", _close_overlay))
		_focus_first(v)
		return
	v.add_child(UI.title(p + "  ·  yours to keep", 32, UI.GOLD))
	var mail = LineEdit.new()
	mail.placeholder_text = "Email for your receipt"
	mail.text = Store.email()
	mail.virtual_keyboard_type = LineEdit.KEYBOARD_TYPE_EMAIL_ADDRESS
	mail.custom_minimum_size = Vector2(0, 52)
	mail.focus_mode = Control.FOCUS_ALL
	v.add_child(mail)
	var note = "Checkout opens in your browser and is run by Stripe. Your email goes to the Hartmann Studios license server and to Stripe, for your receipt and to restore your purchase. It's a one-time payment: nothing renews."
	if Store.catalog.get(key, {}).get("promo_codes", false):
		note += " Have a promotion code? Enter it on Stripe's checkout page."
	v.add_child(UI.label(note, 15, UI.DIM, true))
	var row = UI.hbox(10)
	var go = UI.button("Continue to Stripe", func(): Store.buy(key, mail.text), true)
	go.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(go)
	row.add_child(UI.button("Not now", _close_overlay))
	v.add_child(row)
	if key != Data.COMPLETE and not Store.owns(Data.COMPLETE) and Store.price(Data.COMPLETE) != "":
		v.add_child(UI.label("Or get the Complete pack (%s): both chapters, the Arsenal and the Survivors." % Store.price(Data.COMPLETE), 15, UI.GOLD, true))
	var restore = UI.button("Restore purchases", restore_dialog)
	v.add_child(restore)
	_focus_first(mail if mail.text == "" else go)


func restore_dialog() -> void:
	var v = _dialog("Restore purchases")
	v.add_child(UI.label("Type the email from your receipt. Rotline asks the license server what that email owns.", 18, UI.INK, true))
	var mail = LineEdit.new()
	mail.placeholder_text = "Email from your receipt"
	mail.text = Store.email()
	mail.custom_minimum_size = Vector2(0, 52)
	v.add_child(mail)
	var row = UI.hbox(10)
	var go = UI.button("Restore", func():
		Store.restore(mail.text)
		_close_overlay(), true)
	go.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(go)
	row.add_child(UI.button("Not now", _close_overlay))
	v.add_child(row)
	_focus_first(v)


func update_dialog() -> void:
	var info = Updates.latest
	var v = _dialog("Rotline %s" % info.version)
	var notes = RichTextLabel.new()
	notes.text = info.notes
	notes.fit_content = true
	notes.custom_minimum_size = Vector2(0, 160)
	notes.scroll_active = true
	v.add_child(notes)
	if Updates.channel == "github":
		v.add_child(UI.button("Open the release page", func(): OS.shell_open(info.url), true))
	else:
		v.add_child(UI.label("Update Rotline from Depot, Luma's app store.", 18, UI.INK, true))
	v.add_child(UI.button("Close", _close_overlay))
	_focus_first(v)


# ------------------------------------------------------------------------------------------------ settings
func show_settings() -> void:
	where = "settings"
	_background()
	_clear()
	var body = _page("Settings", show_menu)
	body.add_child(_toggle("Aim and fire for me", "When you're not using a mouse", "auto_fire"))
	body.add_child(_toggle("Story mode", "You take half the damage", "easy"))
	body.add_child(_toggle("Screen shake", "", "shake"))
	body.add_child(_toggle("Lightning flashes", "Turn off if flashing light bothers you", "flashes"))
	body.add_child(_slider("Sound effects", "sfx"))
	body.add_child(_slider("Music", "music"))
	var touch_row = UI.card()
	var th = UI.hbox(12)
	touch_row.add_child(th)
	var tl = UI.label("Touch controls", 20, UI.INK)
	tl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	th.add_child(tl)
	for opt in [["auto", "Automatic"], ["always", "Always"], ["never", "Never"]]:
		var o: String = opt[0]
		th.add_child(UI.button(opt[1], func():
			Game.set_setting("touch", o)
			show_settings(), Game.setting("touch") == o, 18))
	body.add_child(touch_row)
	var fs = UI.button("Leave full screen" if Game.setting("fullscreen") else "Full screen", func():
		var on: bool = not Game.setting("fullscreen")
		Game.set_setting("fullscreen", on)
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if on else DisplayServer.WINDOW_MODE_WINDOWED)
		show_settings())
	fs.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	body.add_child(fs)
	body.add_child(_toggle("Check for updates automatically", "Asks GitHub at most twice a day", "updates"))
	var check = UI.button("Check for updates now  ·  v%s" % Updates.VERSION, func():
		await Updates.check(true)
		if Updates.latest.is_empty():
			toast("Rotline is up to date.", "done")
		else:
			update_dialog())
	check.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	body.add_child(check)
	body.add_child(UI.label("Rotline is free software (GPL-3.0-or-later) by Hartmann Studios. Made with Godot Engine. Fonts: Bebas Neue and Rubik (SIL Open Font License). Art and sound are made in code for Rotline.", 15, UI.DIM, true))
	_focus_first(body)


func _toggle(title: String, sub: String, key: String) -> Control:
	var c = UI.card()
	var h = UI.hbox(12)
	c.add_child(h)
	var words = UI.vbox(2)
	words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	words.add_child(UI.label(title, 20))
	if sub != "":
		words.add_child(UI.label(sub, 15, UI.DIM, true))
	h.add_child(words)
	var t = CheckButton.new()
	t.button_pressed = bool(Game.setting(key))
	t.focus_mode = Control.FOCUS_ALL
	t.toggled.connect(func(on):
		Sfx.play("ui_ok", 0.02)
		Game.set_setting(key, on))
	h.add_child(t)
	return c


func _slider(title: String, key: String) -> Control:
	var c = UI.card()
	var h = UI.hbox(12)
	c.add_child(h)
	var l = UI.label(title, 20)
	l.custom_minimum_size = Vector2(180, 0)
	h.add_child(l)
	var s = HSlider.new()
	s.min_value = 0
	s.max_value = 1
	s.step = 0.05
	s.value = float(Game.setting(key))
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.custom_minimum_size = Vector2(160, 32)
	s.focus_mode = Control.FOCUS_ALL
	s.value_changed.connect(func(v):
		Game.set_setting(key, v)
		Sfx.apply_volume())
	s.drag_ended.connect(func(_c): Sfx.play("pickup", 0.0))
	h.add_child(s)
	return c


# ------------------------------------------------------------------------------------------------ playing
func start(key: String, brief := true) -> void:
	var lv = Levels.by_key(key)
	if not lv.endless and lv.chapter > 1 and not Store.owns(Levels.CHAPTER_PRODUCTS[lv.chapter]):
		buy_dialog(Levels.CHAPTER_PRODUCTS[lv.chapter])
		return
	if not Game.unlocked(key):
		toast("Finish the level before this one first")
		return
	_free_world()
	_clear()
	playing = key
	where = "play"
	var surv = Game.survivor()
	if surv != "sam" and not Store.owns("rotline_survivors"):
		surv = "sam"
	world = World.new()
	holder.add_child(world)
	world.setup(key, {"survivor": surv, "weapons": Game.weapons(Store.owns("rotline_arsenal")),
		"upgrades": Game.upgrades(), "easy": Game.setting("easy")})
	world.input_source = _inputs
	world.ended.connect(_ended)
	_show_hud()
	_hold.clear()
	Sfx.play_music("music_play")
	DisplayServer.screen_set_keep_on(true)
	if brief:
		get_tree().paused = true
		_card(lv.name if lv.endless else "%s  %s" % [lv.key, lv.name], [lv.brief, Levels.goal_words(lv) + "."] + _tips(lv),
			[["Start", _resume, true], ["Back", back_to_map, false]], "brief")
	else:
		get_tree().paused = false


func _tips(lv: Dictionary) -> Array:
	if lv.key != "1-1":
		return lv.tips.slice(0, 1)
	if Game.touch_seen:
		return ["Drag on the left to move. It aims and fires for you; drag on the right to aim yourself. Tap ROLL to dodge."]
	if Game.tv:
		return ["Move with the arrows or the stick. It aims and fires for you. OK dodge-rolls, Back pauses."]
	return ["WASD or arrows move. Aim with the mouse and hold the button to shoot (or let it aim for you). Space rolls, G throws a grenade, 1–6 or the wheel switch weapons."]


func _show_hud() -> void:
	_hide_hud()
	hud = HUD.new()
	hud.main = self
	hud.world = world
	hud.set_anchors_preset(Control.PRESET_FULL_RECT)
	hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	screen.get_parent().add_child(hud)
	screen.get_parent().move_child(hud, 0)
	touch = Touch.new()
	touch.main = self
	touch.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.get_parent().add_child(touch)
	screen.get_parent().move_child(touch, 1)


func _hide_hud() -> void:
	if hud and is_instance_valid(hud):
		hud.queue_free()
	if touch and is_instance_valid(touch):
		touch.queue_free()
	hud = null
	touch = null


func _resume() -> void:
	_close_overlay()
	get_tree().paused = false


func pause() -> void:
	if playing == "" or world == null or world.state != "play" or get_tree().paused:
		return
	get_tree().paused = true
	var pr = world.progress()
	var lv = world.lv
	_card("Paused", [Levels.goal_words(lv) + ".", pr[1]], [["Resume", _resume, true],
		["Start over", func(): start(playing, false), false],
		["Settings", func(): _settings_in_game(), false],
		["Quit to the map", back_to_map, false]], "pause")


func _settings_in_game() -> void:
	var v = _dialog("Settings")
	v.add_child(_toggle("Aim and fire for me", "", "auto_fire"))
	v.add_child(_toggle("Screen shake", "", "shake"))
	v.add_child(_slider("Sound effects", "sfx"))
	v.add_child(_slider("Music", "music"))
	v.add_child(UI.button("Back", func(): pause_again(), true))
	_focus_first(v)


func pause_again() -> void:
	_close_overlay()
	get_tree().paused = false
	pause()


func back_to_map() -> void:
	var lv_endless = playing == "endless"
	_leave()
	if lv_endless:
		show_menu()
	else:
		show_campaign(chapter_tab)


func _leave() -> void:
	if world and playing != "" and world.state == "play" and (world.time > 3 or world.kills > 0):
		Game.finish(playing, false, 0, world.time, world.kills, world.scrap)
	get_tree().paused = false
	playing = ""
	DisplayServer.screen_set_keep_on(false)
	_hide_hud()
	_free_world()


func _card(title: String, lines: Array, buttons: Array, kind := "", stars := -1) -> void:
	_close_overlay()
	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.45)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.get_parent().add_child(dim)
	overlay = dim
	overlay.set_meta("kind", kind)
	var center = CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.add_child(center)
	var panel = PanelContainer.new()
	var vs = get_viewport().get_visible_rect().size
	panel.custom_minimum_size = Vector2(min(560, vs.x - 32), 0)
	if kind == "won":
		panel.add_theme_stylebox_override("panel", UI._box(Color(UI.PANEL, 0.95), 22, UI.GREEN, 2))
	elif kind == "lost":
		panel.add_theme_stylebox_override("panel", UI._box(Color(UI.PANEL, 0.95), 22, UI.RED, 2))
	center.add_child(panel)
	var v = UI.vbox(12)
	panel.add_child(v)
	var t = UI.title(title, 60)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(t)
	if stars >= 0:
		var s = UI.stars(stars, 54)
		s.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		s.pivot_offset = Vector2(120, 30)
		v.add_child(s)
		s.scale = Vector2.ONE * 0.2
		var tw = s.create_tween()
		tw.tween_property(s, "scale", Vector2.ONE, 0.45).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	for line in lines:
		var l = UI.label(line, 19, UI.INK, true)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(l)
	var first: Control = null
	for b in buttons:
		var btn = UI.button(b[0], b[1], b[2])
		v.add_child(btn)
		if first == null:
			first = btn
	panel.modulate.a = 0.0
	panel.create_tween().tween_property(panel, "modulate:a", 1.0, 0.2)
	_focus_first(first)


func _ended(won: bool) -> void:
	await get_tree().create_timer(1.1, true, false, true).timeout
	if world == null or playing == "":
		return
	DisplayServer.screen_set_keep_on(false)
	var lv = world.lv
	var stars = world.stars()
	var bonus = world.bonus()
	var news = Game.finish(playing, won, stars, world.time, world.kills, world.scrap + bonus)
	var t = "%d:%02d" % [int(world.time) / 60, int(world.time) % 60]
	get_tree().paused = true
	if lv.endless:
		var lines = [world.why, "You lasted %s and put down %d." % [t, world.kills], "+%d scrap  ·  best streak %d" % [world.scrap, world.best_combo]]
		if news.get("best", false):
			lines.insert(1, "That's your best yet.")
		_card("Overrun", lines, [["Again", func(): start("endless", false), true], ["Armory", func():
			_leave()
			show_armory(), false], ["Menu", func():
			_leave()
			show_menu(), false]], "lost")
		return
	if won:
		var lines = [world.why, "%s  ·  %d down  ·  +%d scrap" % [t, world.kills, world.scrap + bonus]]
		if news.has("weapon"):
			lines.append("You found the %s. It's yours from now on." % Data.WEAPONS[news.weapon].name)
		var buttons = []
		var nxt = Levels.next_level(playing)
		if not nxt.is_empty():
			if nxt.chapter == 1 or Store.owns(Levels.CHAPTER_PRODUCTS[nxt.chapter]):
				buttons.append(["Next: " + nxt.name, func(): start(nxt.key), true])
			else:
				var key: String = Levels.CHAPTER_PRODUCTS[nxt.chapter]
				var p = Store.price(key)
				lines.append("Chapter %d picks up from here." % nxt.chapter)
				buttons.append(["Get Chapter %d%s" % [nxt.chapter, ("  ·  " + p) if p != "" else ""], func():
					_leave()
					show_campaign(nxt.chapter)
					buy_dialog(key), true])
		else:
			lines.append("That's the end of the road. For now. Endless is always open.")
		buttons.append(["Play again", func(): start(playing, false), false])
		buttons.append(["Back to the map", back_to_map, false])
		_card("Made it" if lv.goal != "boss" else "It's down", lines, buttons, "won", stars)
	else:
		var lines = [world.why, "You kept the %d scrap you picked up." % world.scrap]
		if not Game.setting("easy"):
			lines.append("Upgrades in the Armory help, and Story mode in Settings halves the damage.")
		_card("Overrun", lines, [["Try again", func(): start(playing, false), true], ["Armory", func():
			_leave()
			show_armory(), false], ["Back to the map", back_to_map, false]], "lost")


# ------------------------------------------------------------------------------------------------ controls
func _inputs() -> Dictionary:
	var now = Time.get_ticks_msec() / 1000.0
	var move = Input.get_vector("left", "right", "up", "down")
	for dir in _hold:
		if _hold[dir] > now:
			move += {"left": Vector2.LEFT, "right": Vector2.RIGHT, "up": Vector2.UP, "down": Vector2.DOWN}[dir]
	var aim = null
	var fire = Input.is_action_pressed("fire_key") or Input.is_action_pressed("fire_pad")
	if touch and touch.move_vec != Vector2.ZERO:
		move += touch.move_vec
	if touch and touch.aim_vec.length() > 0.3:
		aim = touch.aim_vec.angle()
		fire = true
	var mouse_active = mouse_down or now - mouse_t < 2.5
	if aim == null and mouse_active and world:
		var mp = world.get_global_mouse_position()
		aim = (mp - world.player.global_position).angle()
		fire = fire or mouse_down
	var pad = Vector2(Input.get_joy_axis(0, JOY_AXIS_RIGHT_X), Input.get_joy_axis(0, JOY_AXIS_RIGHT_Y))
	if pad.length() > 0.4:
		aim = pad.angle()
		fire = true
	var inp = {"move": move, "aim": aim, "fire": fire, "auto_fire": bool(Game.setting("auto_fire")),
		"dodge": Input.is_action_just_pressed("dodge") or (touch != null and touch.take("dodge")),
		"grenade": Input.is_action_just_pressed("grenade") or (touch != null and touch.take("grenade")),
		"switch": 0}
	if Input.is_action_just_pressed("next_weapon") or (touch != null and touch.take("switch")):
		inp.switch = 1
	elif Input.is_action_just_pressed("prev_weapon"):
		inp.switch = -1
	for i in 6:
		if Input.is_action_just_pressed("w%d" % (i + 1)) and world and i < world.player.weapons.size():
			world.player.select(world.player.weapons[i])
	return inp


func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch or event is InputEventScreenDrag:
		Game.touch_seen = true
	if event is InputEventMouseMotion and not Game.touch_seen:
		mouse_t = Time.get_ticks_msec() / 1000.0
	if event is InputEventMouseButton and playing != "" and not get_tree().paused:
		if event.button_index == MOUSE_BUTTON_LEFT:
			mouse_down = event.pressed
			mouse_t = Time.get_ticks_msec() / 1000.0
		elif event.pressed and event.button_index == MOUSE_BUTTON_RIGHT and world:
			Input.action_press("grenade")   # right-click throws a grenade
			get_tree().create_timer(0.05).timeout.connect(func(): Input.action_release("grenade"))
		elif event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and world:
			world.player.cycle(1 if event.button_index == MOUSE_BUTTON_WHEEL_DOWN else -1)
	# TV keys: a remote or a gamepad in TV posture sends whole presses (down and up at once) that repeat while
	# held. Keep walking until the next repeat should have come.
	if event is InputEventKey and playing != "" and not event.echo:
		var dir = ""
		for d in ["left", "right", "up", "down"]:
			if event.is_action(d):
				dir = d
		if dir != "":
			var now = Time.get_ticks_msec() / 1000.0
			if event.pressed:
				_pressed_at[dir] = now
			else:
				if now - float(_pressed_at.get(dir, now)) < 0.05:
					var chained = now - float(_tap_chain.get(dir, -9.0)) < 0.6
					_hold[dir] = now + (0.17 if chained else 0.42)
					_tap_chain[dir] = now
				else:
					_hold.erase(dir)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_F11:
		var fs = DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED if fs else DisplayServer.WINDOW_MODE_FULLSCREEN)
		return
	var back = event.is_action_pressed("ui_cancel") or event.is_action_pressed("pause")
	if not back:
		return
	get_viewport().set_input_as_handled()
	if overlay and is_instance_valid(overlay):
		var kind: String = overlay.get_meta("kind", "")
		if playing != "":
			if kind == "pause":
				_resume()
			elif kind in ["won", "lost"]:
				back_to_map()
			elif kind == "brief":
				back_to_map()
			else:
				pause_again()
		else:
			_close_overlay()
		return
	if playing != "":
		pause()
	elif where != "menu":
		show_menu()


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT and playing != "":
		pause()
