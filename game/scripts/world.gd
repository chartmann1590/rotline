# SPDX-License-Identifier: GPL-3.0-or-later
# One attempt at a level: the map (tiles, props, lamps and weather), the survivor, the dead, shots and effects,
# spawning and the goal. Also runs the menu's background in demo mode (no survivor input, a drifting camera).
class_name World
extends Node2D

signal hud(what: String, value)
signal ended(won: bool)

const T := Data.TILE
const MAX_DECALS := 260
const MAX_CORPSES := 70

const LOOK := {
	"suburb": {"night": Color(0.42, 0.36, 0.42), "lamp": Color(1.0, 0.78, 0.5), "weather": "ash", "crate": 0},
	"downtown": {"night": Color(0.13, 0.15, 0.24), "lamp": Color(1.0, 0.72, 0.42), "weather": "rain", "crate": 0},
	"harbor": {"night": Color(0.24, 0.29, 0.34), "lamp": Color(0.85, 0.95, 1.0), "weather": "fog", "crate": 1},
	"endless": {"night": Color(0.2, 0.13, 0.13), "lamp": Color(1.0, 0.45, 0.3), "weather": "embers", "crate": 0},
}

var lv: Dictionary
var theme = "suburb"
var rows: Array = []
var w = 0
var h = 0
var demo = false
var state = "play"
var why = ""
var time = 0.0
var kills = 0
var scrap = 0
var spawned = 0
var fuel = 0
var fuel_needed = 0
var bosses_left = 0
var bosses_waiting = 0       # Tanks still to come: they arrive one at a time, the next a few seconds after one falls
var _boss_t = 0.0
var gen_pos = Vector2(-9999, -9999)
var gen_hp = 0.0
var gen_max = 1.0
var combo = 0
var combo_t = 0.0
var best_combo = 0
var shake = 0.0
var field = PackedInt32Array()
var gen_field = PackedInt32Array()
var spawns: Array = []
var exits: Array = []
var hordes_done = 0
var next_tank = 150.0

var player: Player
var zombies: Array = []
var pickups: Array = []      # [Node2D, kind]
var acids: Array = []        # [Node2D, velocity, life]
var bolts: Array = []        # [Node2D, dir, damage, pierce, hit ids, life]

var floor_layer: TileMapLayer
var water_layer: TileMapLayer
var decals: Node2D
var corpses: Node2D
var actors: Node2D
var fx: Node2D
var canopy: Node2D
var camera: Camera2D
var night: CanvasModulate
var exit_nodes: Array = []
var gen_bar: Node2D
var input_source: Callable    # returns {move, aim, fire, auto_fire, dodge, grenade, switch}
var easy = false
var flicker: Array = []

var _spawn_acc = 0.0
var _field_t = 0.0
var _groan = 2.0
var _demo_t = 0.0
var _demo_target = Vector2.ZERO
var _thunder = 12.0


func setup(key: String, opts := {}) -> void:
	lv = Levels.by_key(key)
	demo = opts.get("demo", false)
	easy = opts.get("easy", false)
	theme = "endless" if lv.endless else Levels.CHAPTERS[lv.chapter - 1].theme
	if opts.has("theme"):
		theme = opts.theme
	rows = lv.map
	h = rows.size()
	w = rows[0].length()
	seed(int(opts.get("seed", Time.get_ticks_usec())))
	fuel_needed = lv.target if lv.goal == "escape" else 0
	bosses_left = lv.bosses
	_build()
	var start = Vector2(w * T / 2, h * T / 2)
	for j in h:
		for i in w:
			if rows[j][i] == "P":
				start = Vector2(i * T + T / 2, j * T + T / 2)
	player = Player.new()
	player.setup(self, start, opts.get("survivor", "sam"), opts.get("weapons", ["pistol"]), opts.get("upgrades", {}), easy)
	actors.add_child(player)
	_demo_target = start
	_refield()
	if demo:
		player.visible = false
		player.process_mode = Node.PROCESS_MODE_DISABLED
		player.collision_layer = 0
		player.torch.enabled = false
		player.near.enabled = false
		_demo_target = start
		for i in 14:
			_spawn(_pick_kind(), false, true)
	camera.position = start
	camera.reset_smoothing()
	_refield()
	if gen_hp > 0:
		var around = []
		var gi = int(gen_pos.x / T)
		var gj = int(gen_pos.y / T)
		for a in [-1, 0, 1]:
			for b in [-1, 0, 1]:
				if a != 0 or b != 0:
					around.append(Vector2i(gi + a, gj + b))
		gen_field = Data.bfs(rows, around)
	if not demo and lv.bosses > 0:
		_spawn("tank", true)
		bosses_waiting = lv.bosses - 1


# ------------------------------------------------------------------------------------------------ building the map
func _floor_near(i: int, j: int) -> String:
	for o in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
		var ii = i + o.x
		var jj = j + o.y
		if jj >= 0 and jj < h and ii >= 0 and ii < w and ".,=".contains(rows[jj][ii]):
			return rows[jj][ii]
	return "."


func _cell(i: int, j: int) -> String:
	if j < 0 or j >= h or i < 0 or i >= w:
		return "#"
	return rows[j][i]


func _build() -> void:
	night = CanvasModulate.new()
	night.color = LOOK[theme].night
	add_child(night)
	var ts = TileSet.new()
	ts.tile_size = Vector2i(64, 64)
	var src = TileSetAtlasSource.new()
	src.texture = load("res://assets/tiles/%s.png" % theme)
	src.texture_region_size = Vector2i(64, 64)
	ts.add_source(src, 0)
	for col in 24:
		src.create_tile(Vector2i(col, 0))
	floor_layer = TileMapLayer.new()
	floor_layer.tile_set = ts
	floor_layer.z_index = -20
	add_child(floor_layer)
	water_layer = TileMapLayer.new()
	water_layer.tile_set = ts
	water_layer.z_index = -19
	var wmat = ShaderMaterial.new()
	wmat.shader = load("res://shaders/water.gdshader")
	wmat.set_shader_parameter("noise", load("res://assets/fx/fog.png"))
	water_layer.material = wmat
	add_child(water_layer)
	decals = Node2D.new()
	decals.z_index = -10
	add_child(decals)
	corpses = Node2D.new()
	corpses.z_index = -9
	add_child(corpses)
	var props = Node2D.new()
	props.z_index = -5
	add_child(props)
	actors = Node2D.new()
	add_child(actors)
	fx = Node2D.new()
	fx.z_index = 10
	add_child(fx)
	canopy = Node2D.new()
	canopy.z_index = 20
	add_child(canopy)
	camera = Camera2D.new()
	camera.position_smoothing_enabled = true
	camera.position_smoothing_speed = 7.0
	add_child(camera)
	camera.make_current()
	var rng = RandomNumberGenerator.new()
	rng.seed = hash(lv.key)
	for j in h:
		for i in w:
			var ch: String = rows[j][i]
			var base = ch
			if not ".,=#~".contains(ch):
				base = _floor_near(i, j)
			var col = 0
			match base:
				"#":
					var mask = 0
					if _cell(i, j - 1) != "#":
						mask |= 1
					if _cell(i + 1, j) != "#":
						mask |= 2
					if _cell(i, j + 1) != "#":
						mask |= 4
					if _cell(i - 1, j) != "#":
						mask |= 8
					col = 8 + mask
				",":
					col = 3 if rng.randf() < 0.1 else 2
				"=":
					col = 5 if rng.randf() < 0.3 else 4
				"~":
					col = 7
				_:
					var by_road = _cell(i - 1, j) == "," or _cell(i + 1, j) == "," or _cell(i, j - 1) == "," or _cell(i, j + 1) == ","
					col = 6 if (theme == "downtown" and by_road) else (1 if rng.randf() < 0.3 else 0)
			if col == 7:
				water_layer.set_cell(Vector2i(i, j), 0, Vector2i(7, 0))
			else:
				floor_layer.set_cell(Vector2i(i, j), 0, Vector2i(col, 0))
			var at = Vector2(i * T + T / 2, j * T + T / 2)
			match ch:
				"c":
					var horiz = ",.".contains(_cell(i - 1, j)) and ",.".contains(_cell(i + 1, j))
					_prop(props, "res://assets/props/car%d.png" % rng.randi_range(0, 6), at,
						(0.0 if horiz else PI / 2) + rng.randf_range(-0.25, 0.25), Vector2(80, 50), 1, true, 0.62)
				"t":
					var trunk = StaticBody2D.new()
					trunk.position = at
					trunk.collision_layer = 1
					var cs = CollisionShape2D.new()
					var cc = CircleShape2D.new()
					cc.radius = 18
					cs.shape = cc
					trunk.add_child(cs)
					var occ = LightOccluder2D.new()
					var op = OccluderPolygon2D.new()
					var pts = PackedVector2Array()
					for n in 8:
						pts.append(Vector2.from_angle(n * TAU / 8) * 16)
					op.polygon = pts
					occ.occluder = op
					trunk.add_child(occ)
					props.add_child(trunk)
					var top = Sprite2D.new()
					top.texture = load("res://assets/props/tree%d.png" % rng.randi_range(0, 2))
					top.position = at
					top.rotation = rng.randf_range(0, TAU)
					top.scale = Vector2.ONE * rng.randf_range(0.85, 1.05)
					top.modulate = Color(1, 1, 1, 0.93)
					canopy.add_child(top)
				"x":
					var c = 0 if LOOK[theme].crate == 0 else rng.randi_range(1, 4)
					_prop(props, "res://assets/props/crate%d.png" % c, at, 0.0, Vector2(60, 60), 1, true, 1.0)
				"f":
					_prop(props, "res://assets/props/fence.png", at, 0.0, Vector2(64, 64), 32, false, 1.0)
				"G":
					gen_pos = at
					gen_hp = float(lv.gen_hp)
					gen_max = gen_hp
					_prop(props, "res://assets/props/generator.png", at, 0.0, Vector2(58, 52), 1, true, 1.0)
					var gl = _light(at, Color(0.4, 1.0, 0.6), 0.9, 0.6, false)
					props.add_child(gl)
					gen_bar = Node2D.new()
					gen_bar.position = at + Vector2(0, -48)
					gen_bar.z_index = 30
					gen_bar.draw.connect(_draw_gen_bar)
					add_child(gen_bar)
				"S":
					spawns.append(at)
				"E":
					exits.append(Vector2i(i, j))
					var g = Sprite2D.new()
					g.texture = load("res://assets/fx/glow.png")
					g.position = at
					g.scale = Vector2.ONE * 1.6
					var m = CanvasItemMaterial.new()
					m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
					g.material = m
					decals.add_child(g)
					var el = _light(at, Color(1, 0.2, 0.2), 0.6, 0.5, false)
					add_child(el)
					exit_nodes.append([g, el])
				"F":
					_pickup("fuel", at)
				"h":
					_pickup("medkit", at)
				"a":
					_pickup("ammo", at)
				"g":
					_pickup("grenade", at)
	_walls()
	_lamps(props, rng)
	_weather()


func _walls() -> void:
	# collision and shadows for walls (and collision for water), one rectangle per run of tiles in a row
	var body = StaticBody2D.new()
	body.collision_layer = 1
	body.collision_mask = 0
	add_child(body)
	var low = StaticBody2D.new()
	low.collision_layer = 32
	low.collision_mask = 0
	add_child(low)
	for j in h:
		var i = 0
		while i < w:
			var ch: String = rows[j][i]
			if ch != "#" and ch != "~":
				i += 1
				continue
			var start = i
			while i < w and rows[j][i] == ch:
				i += 1
			var rect = Rect2(start * T, j * T, (i - start) * T, T)
			var cs = CollisionShape2D.new()
			var rs = RectangleShape2D.new()
			rs.size = rect.size
			cs.shape = rs
			cs.position = rect.get_center()
			if ch == "#":
				body.add_child(cs)
				var occ = LightOccluder2D.new()
				var op = OccluderPolygon2D.new()
				op.polygon = PackedVector2Array([rect.position, Vector2(rect.end.x, rect.position.y), rect.end, Vector2(rect.position.x, rect.end.y)])
				occ.occluder = op
				add_child(occ)
			else:
				low.add_child(cs)


func _prop(parent: Node, tex: String, at: Vector2, rot: float, size: Vector2, layer: int, occlude: bool, scl: float) -> void:
	var body = StaticBody2D.new()
	body.position = at
	body.rotation = rot
	body.collision_layer = layer
	body.collision_mask = 0
	var cs = CollisionShape2D.new()
	var rs = RectangleShape2D.new()
	rs.size = size
	cs.shape = rs
	body.add_child(cs)
	var spr = Sprite2D.new()
	spr.texture = load(tex)
	spr.scale = Vector2.ONE * scl
	body.add_child(spr)
	if occlude:
		var occ = LightOccluder2D.new()
		var op = OccluderPolygon2D.new()
		var hx = size.x / 2 + 2
		var hy = size.y / 2 + 2
		op.polygon = PackedVector2Array([Vector2(-hx, -hy), Vector2(hx, -hy), Vector2(hx, hy), Vector2(-hx, hy)])
		occ.occluder = op
		body.add_child(occ)
	parent.add_child(body)


func _light(at: Vector2, col: Color, energy: float, scl: float, shadows: bool) -> PointLight2D:
	var l = PointLight2D.new()
	l.texture = load("res://assets/light/round.png")
	l.position = at
	l.color = col
	l.energy = energy
	l.texture_scale = scl
	l.shadow_enabled = shadows
	if shadows:
		l.shadow_filter = Light2D.SHADOW_FILTER_PCF5
		l.shadow_filter_smooth = 2.0
	return l


func _lamps(props: Node, rng: RandomNumberGenerator) -> void:
	# street lamps: open tiles next to a road or a wall, kept well apart, a warm pool of light each
	var cands = []
	for j in range(1, h - 1):
		for i in range(1, w - 1):
			var ch: String = rows[j][i]
			if not ".,=".contains(ch):
				continue
			var near_edge = false
			for o in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var n = _cell(i + o.x, j + o.y)
				if n == "#" or (ch == "." and n == ","):
					near_edge = true
			if near_edge:
				cands.append(Vector2i(i, j))
	cands.shuffle()
	var placed = []
	for c in cands:
		if placed.size() >= 9:
			break
		var ok = true
		for p in placed:
			if (p - c).length() < 8:
				ok = false
				break
		if not ok:
			continue
		placed.append(c)
		var at = Vector2(c.x * T + T / 2, c.y * T + T / 2)
		var l = _light(at, LOOK[theme].lamp, 1.15, 1.25, true)
		if rng.randf() < 0.25:
			flicker.append(l)
		props.add_child(l)
		var bulb = Sprite2D.new()
		bulb.texture = load("res://assets/fx/glow.png")
		bulb.position = at
		bulb.scale = Vector2.ONE * 0.35
		bulb.modulate = LOOK[theme].lamp
		var m = CanvasItemMaterial.new()
		m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
		m.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
		bulb.material = m
		canopy.add_child(bulb)


func _weather() -> void:
	var layer = CanvasLayer.new()
	layer.layer = 2
	add_child(layer)
	var kind: String = LOOK[theme].weather
	if kind == "fog":
		var fogs = TextureRect.new()
		fogs.texture = load("res://assets/fx/fog.png")
		fogs.stretch_mode = TextureRect.STRETCH_TILE
		fogs.set_anchors_preset(Control.PRESET_FULL_RECT)
		fogs.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var mat = ShaderMaterial.new()
		mat.shader = load("res://shaders/fog.gdshader")
		fogs.material = mat
		layer.add_child(fogs)
		return
	var p = CPUParticles2D.new()
	p.amount = 260 if kind == "rain" else 70
	p.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
	p.emission_rect_extents = Vector2(1400, 40)
	p.position = Vector2(640, -60)
	p.lifetime = 1.1 if kind == "rain" else 6.0
	p.preprocess = 3.0
	p.local_coords = false
	if kind == "rain":
		p.texture = load("res://assets/fx/rain.png")
		p.direction = Vector2(0.18, 1)
		p.spread = 2
		p.initial_velocity_min = 900
		p.initial_velocity_max = 1150
		p.gravity = Vector2.ZERO
		p.particle_flag_align_y = true
		p.color = Color(0.7, 0.8, 1.0, 0.55)
		p.scale_amount_min = 0.8
		p.scale_amount_max = 1.4
	else:
		p.texture = load("res://assets/fx/dot.png")
		p.direction = Vector2(0.3, 1)
		p.spread = 40
		p.initial_velocity_min = 25
		p.initial_velocity_max = 70
		p.gravity = Vector2(8, 6)
		p.scale_amount_min = 0.04
		p.scale_amount_max = 0.1
		p.color = Color(1.0, 0.55, 0.25, 0.8) if kind == "embers" else Color(0.75, 0.72, 0.7, 0.55)
		p.emission_rect_extents = Vector2(1400, 800)
		p.position = Vector2(640, 360)
		var m = CanvasItemMaterial.new()
		m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
		p.material = m
	layer.add_child(p)


func _pickup(kind: String, at: Vector2) -> void:
	var n = Node2D.new()
	n.position = at
	n.z_index = -4
	var glow = Sprite2D.new()
	glow.texture = load("res://assets/fx/glow.png")
	glow.scale = Vector2.ONE * 0.9
	var col = {"medkit": Color(1, 0.4, 0.4), "ammo": Color(1, 0.85, 0.4), "fuel": Color(1, 0.35, 0.2), "grenade": Color(0.6, 1, 0.4)}[kind]
	glow.modulate = Color(col, 0.5)
	var m = CanvasItemMaterial.new()
	m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	m.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
	glow.material = m
	n.add_child(glow)
	var spr = Sprite2D.new()
	spr.texture = load("res://assets/pickups/%s.png" % kind)
	spr.scale = Vector2.ONE * 0.8
	spr.name = "item"
	n.add_child(spr)
	var tw = n.create_tween().set_loops()
	tw.tween_property(spr, "position:y", -5.0, 0.6).set_trans(Tween.TRANS_SINE)
	tw.tween_property(spr, "position:y", 3.0, 0.6).set_trans(Tween.TRANS_SINE)
	actors.add_child(n)
	pickups.append([n, kind])


func _draw_gen_bar() -> void:
	var frac: float = clamp(gen_hp / gen_max, 0.0, 1.0)
	gen_bar.draw_rect(Rect2(-36, -5, 72, 10), Color(0, 0, 0, 0.7))
	gen_bar.draw_rect(Rect2(-34, -3, 68 * frac, 6), Color(0.24, 0.86, 0.52) if frac > 0.35 else Color(0.9, 0.28, 0.3))


# ------------------------------------------------------------------------------------------------ the grid
func _tile(p: Vector2) -> Vector2i:
	return Vector2i(int(p.x / T), int(p.y / T))


func _refield() -> void:
	var t = _tile(player.global_position if not demo else _demo_target)
	field = Data.bfs(rows, [t])


func reachable(p: Vector2) -> bool:
	var t = _tile(p)
	if t.x < 0 or t.y < 0 or t.x >= w or t.y >= h:
		return false
	if field.size() != w * h:
		return true
	return field[t.y * w + t.x] < (1 << 20)


func follow(f: PackedInt32Array, p: Vector2) -> Vector2:
	var t = _tile(p)
	var best = (1 << 20) + 1
	if t.x >= 0 and t.y >= 0 and t.x < w and t.y < h:
		best = f[t.y * w + t.x]
	var bv = Vector2.ZERO
	for o in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1), Vector2i(1, 1), Vector2i(1, -1), Vector2i(-1, 1), Vector2i(-1, -1)]:
		var n = t + o
		if n.x < 0 or n.y < 0 or n.x >= w or n.y >= h:
			continue
		if o.x != 0 and o.y != 0 and (Data.is_solid(rows, t.x + o.x, t.y) or Data.is_solid(rows, t.x, t.y + o.y)):
			continue
		var d = f[n.y * w + n.x] + (0 if o.x == 0 or o.y == 0 else 0)
		if d < best or (d == best and o.x != 0 and o.y != 0 and bv == Vector2.ZERO):
			best = d
			bv = Vector2(n.x * T + T / 2, n.y * T + T / 2) - p
	return bv.normalized() if bv.length() > 0.01 else Vector2.ZERO


func clear_line(a: Vector2, b: Vector2) -> bool:
	var q = PhysicsRayQueryParameters2D.create(a, b, 1)
	return get_world_2d().direct_space_state.intersect_ray(q).is_empty()


func spawn_point(far := false) -> Vector2:
	var p = player.global_position if not demo else _demo_target
	var pts = spawns.filter(func(s): return s.distance_to(p) > 7 * T and reachable(s))
	if pts.is_empty():
		pts = spawns
	if far:
		pts.sort_custom(func(a, b): return a.distance_to(p) > b.distance_to(p))
		return pts[0] + Vector2(randf_range(-12, 12), randf_range(-12, 12))
	return pts[randi() % pts.size()] + Vector2(randf_range(-14, 14), randf_range(-14, 14))


# ------------------------------------------------------------------------------------------------ running
func _physics_process(delta: float) -> void:
	if state != "play":
		_effects(delta)
		return
	if demo:
		_demo(delta)
		_effects(delta)
		return
	time += delta
	_field_t -= delta
	if _field_t <= 0:
		_refield()
		_field_t = 0.25
	var inp: Dictionary = input_source.call() if input_source.is_valid() else {"move": Vector2.ZERO, "aim": null,
		"fire": false, "auto_fire": true, "dodge": false, "grenade": false, "switch": 0}
	player.step(delta, inp)
	if bosses_waiting > 0 and _boss_t > 0:
		_boss_t -= delta
		if _boss_t <= 0:
			bosses_waiting -= 1
			_spawn("tank", true)
	_spawning(delta)
	_projectiles(delta)
	_pickups()
	combo_t -= delta
	if combo_t <= 0 and combo > 0:
		combo = 0
		hud.emit("combo", 0)
	_groan -= delta
	if _groan <= 0 and not zombies.is_empty():
		Sfx.play("groan", 0.15)
		_groan = randf_range(2.0, 5.0)
	if player.hp < player.max_hp * 0.3:
		Sfx.play("heart", 0.0)
	_goals()
	_effects(delta)


func _effects(delta: float) -> void:
	shake = max(0.0, shake - delta * 1.6)
	if camera:
		var target = player.global_position + Vector2.from_angle(player.aim) * 70.0 if not demo else _demo_target
		camera.position = target
		var amp: float = shake * shake * 22.0 if Game.setting("shake") else 0.0
		camera.offset = Vector2(randf_range(-amp, amp), randf_range(-amp, amp))
		var vs = get_viewport().get_visible_rect().size
		var z: float = min(vs.x, vs.y) / ((9.5 if min(vs.x, vs.y) < 520 else 11.0) * T)
		if demo:
			z *= 1.15
		camera.zoom = Vector2.ONE * z
	if gen_bar:
		gen_bar.queue_redraw()
	for e in exit_nodes:
		var open = exit_open()
		var pulse = 0.6 + 0.4 * sin(time * 5.0)
		e[0].modulate = Color(0.25, 1, 0.5, 0.55 * pulse) if open else Color(1, 0.2, 0.2, 0.25)
		e[1].color = Color(0.3, 1, 0.5) if open else Color(1, 0.2, 0.2)
		e[1].energy = 0.9 * pulse if open else 0.35
	if LOOK[theme].weather == "rain" and not demo:
		_thunder -= delta
		if _thunder <= 0 and Game.setting("flashes"):
			_thunder = randf_range(14, 28)
			_lightning()


func _lightning() -> void:
	var tw = create_tween()
	var base: Color = LOOK[theme].night
	tw.tween_property(night, "color", Color(0.85, 0.88, 1.0), 0.05)
	tw.tween_property(night, "color", base, 0.12)
	tw.tween_property(night, "color", Color(0.6, 0.65, 0.8), 0.04)
	tw.tween_property(night, "color", base, 0.5)
	get_tree().create_timer(0.6).timeout.connect(func(): Sfx.play("thunder", 0.1))


func _demo(delta: float) -> void:
	_demo_t -= delta
	if _demo_t <= 0:
		_demo_t = 6.0
		var open = []
		for j in h:
			for i in w:
				if ".,=".contains(rows[j][i]):
					open.append(Vector2(i * T + T / 2, j * T + T / 2))
		_demo_target = open[randi() % open.size()]
		_refield()
	camera.position_smoothing_speed = 0.6
	if zombies.size() < 14:
		_spawn(_pick_kind(), false, true)


# ------------------------------------------------------------------------------------------------ the dead
func _rate() -> float:
	var t: float = clamp(time / max(1.0, float(lv.ramp)), 0.0, 1.0)
	return lerp(float(lv.rate[0]), float(lv.rate[1]), t)


func _spawning(delta: float) -> void:
	if lv.goal == "clear" and spawned >= lv.target:
		return
	# While a Tank is up the horde thins out, so the fight is about the Tank, not about being buried while dodging it.
	_spawn_acc += _rate() * delta * (0.6 if lv.goal == "boss" and lv.chapter >= 2 and boss() != null else 1.0)
	while _spawn_acc >= 1.0:
		_spawn_acc -= 1.0
		if zombies.size() >= lv.max_alive:
			_spawn_acc = min(_spawn_acc, 1.0)
			break
		if lv.goal == "clear" and spawned >= lv.target:
			break
		_spawn(_pick_kind())
	# hordes: a rush at the halfway and late marks of timed levels, and every 45 seconds in Endless
	var marks = []
	if lv.endless:
		if time >= 45.0 * (hordes_done + 1):
			marks.append(true)
	elif lv.goal in ["survive", "defend"]:
		if (hordes_done == 0 and time >= lv.target * 0.5) or (hordes_done == 1 and time >= lv.target * 0.82):
			marks.append(true)
	if not marks.is_empty():
		hordes_done += 1
		var n = 5 + hordes_done * 2 if lv.endless else 7
		for i in n:
			if zombies.size() < lv.max_alive + 8:
				_spawn(_pick_kind())
		Sfx.play("wave", 0.0)
		hud.emit("banner", ("WAVE %d" % (hordes_done + 1)) if lv.endless else "HORDE INCOMING")
	if lv.endless and time >= next_tank:
		_spawn("tank", true)
		next_tank += 120.0


func _pick_kind() -> String:
	var opts = []
	var total = 0.0
	for m in lv.mix:
		if time >= float(m[2]) or demo:
			opts.append(m)
			total += float(m[1])
	var r = randf() * total
	for m in opts:
		r -= float(m[1])
		if r <= 0:
			return m[0]
	return opts[-1][0]


func _spawn(kind: String, boss := false, anywhere := false) -> void:
	if spawns.is_empty():
		return
	var at = spawn_point(boss)
	if anywhere:
		var open = []
		for j in h:
			for i in w:
				if ".,".contains(rows[j][i]):
					open.append(Vector2(i * T + T / 2, j * T + T / 2))
		at = open[randi() % open.size()]
	var hp_mult = 1.0
	if lv.endless:
		hp_mult = 1.0 + min(1.5, time / 300.0)
	elif boss:
		hp_mult = 0.7 + 0.15 * (lv.chapter - 1)
	var z = Zombie.new()
	z.setup(self, kind, at, hp_mult, boss)
	actors.add_child(z)
	zombies.append(z)
	if not boss:
		spawned += 1
	if boss and not demo:
		hud.emit("banner", "THE TANK")
		Sfx.play("roar", 0.0)


func kill(z: Zombie) -> void:
	if z.dead:
		return
	z.dead = true
	zombies.erase(z)
	kills += 1
	scrap += int(z.k.scrap)
	combo += 1
	combo_t = 1.8
	best_combo = max(best_combo, combo)
	if combo in [5, 10, 20, 35, 50]:
		var bonus = {5: 2, 10: 5, 20: 10, 35: 15, 50: 25}[combo]
		scrap += bonus
		hud.emit("banner", "%d IN A ROW  +%d" % [combo, bonus])
	hud.emit("combo", combo)
	var pos = z.global_position
	fx_blood(pos, z.rotation + PI, 1.6 if z.kind in ["brute", "tank"] else 1.0)
	Sfx.play("boom" if z.kind in ["bloater", "tank"] else "splat", 0.12)
	if z.kind == "bloater":
		explode(pos, 2.3 * T, 80.0, 32.0)
	else:
		_corpse(z)
	if z.boss:
		bosses_left -= 1
		if bosses_waiting > 0:
			_boss_t = 4.0
		_hitstop(0.12)
		add_shake(0.9)
		for i in 3:
			_pickup(["ammo", "medkit", "grenade"][i], pos + Vector2(randf_range(-40, 40), randf_range(-40, 40)))
	elif z.kind == "brute":
		_hitstop(0.05)
	var r = randf()
	if not demo:
		if r < 0.05:
			_pickup("ammo", pos)
		elif r < 0.075:
			_pickup("medkit", pos)
		elif r < 0.088:
			_pickup("grenade", pos)
	z.queue_free()


func _corpse(z: Zombie) -> void:
	var s = Sprite2D.new()
	s.texture = z.body.sprite_frames.get_frame_texture("walk", 2)
	s.global_position = z.global_position
	s.rotation = z.rotation + PI + randf_range(-0.5, 0.5)
	s.scale = z.body.scale * 1.05
	s.modulate = Color(0.55, 0.45, 0.45, 0.95)
	corpses.add_child(s)
	var tw = s.create_tween()
	tw.tween_interval(25.0)
	tw.tween_property(s, "modulate:a", 0.0, 4.0)
	tw.tween_callback(s.queue_free)
	if corpses.get_child_count() > MAX_CORPSES:
		corpses.get_child(0).queue_free()


func _hitstop(seconds: float) -> void:
	Engine.time_scale = 0.08
	get_tree().create_timer(seconds, true, false, true).timeout.connect(func(): Engine.time_scale = 1.0)


func add_shake(amount: float) -> void:
	shake = min(1.2, max(shake, amount))


func hit_generator(dmg: float) -> void:
	gen_hp -= dmg
	Sfx.play("clang", 0.1)
	fx_sparks(gen_pos, 6)


func explode(pos: Vector2, radius: float, zdmg: float, pdmg: float) -> void:
	fx_explosion(pos, radius)
	add_shake(0.6)
	for o in zombies.duplicate():
		var d = o.global_position.distance_to(pos)
		if d < radius:
			o.hurt(zdmg * (1.0 - d / radius * 0.5), (o.global_position - pos).normalized(), 260.0)
	var dp = player.global_position.distance_to(pos)
	if dp < radius and not demo:
		player.hurt(pdmg * (1.0 - dp / radius * 0.6), pos)


# ------------------------------------------------------------------------------------------------ shots
func hitscan(from: Vector2, angle: float, reach: float, damage: float, pierce: int, knock: float) -> void:
	var dir = Vector2.from_angle(angle)
	var to = from + dir * reach
	var exclude = [player.get_rid()]
	var end = to
	var left = pierce
	var space = get_world_2d().direct_space_state
	for n in 12:
		var q = PhysicsRayQueryParameters2D.create(from, to, 1 | 4, exclude)
		var hit = space.intersect_ray(q)
		if hit.is_empty():
			end = to
			break
		var c = hit.collider
		if c is Zombie:
			player.hits += 1
			c.hurt(damage, dir, knock)
			fx_blood(hit.position, angle, 0.5)
			Sfx.play("hit", 0.15)
			exclude.append(hit.rid)
			left -= 1
			if left < 0:
				end = hit.position
				break
		else:
			end = hit.position
			fx_sparks(hit.position - dir * 4, 5)
			break
	fx_tracer(from, end)


func flame_tick(from: Vector2, angle: float, reach: float, spread: float, damage: float) -> void:
	var dir = Vector2.from_angle(angle)
	for z in zombies.duplicate():
		var to: Vector2 = z.global_position - from
		var d = to.length()
		if d > reach + z.radius or d < 1:
			continue
		if abs(dir.angle_to(to)) > spread * 1.4 + z.radius / max(d, 1.0):
			continue
		if not clear_line(from, z.global_position):
			continue
		z.hurt(damage, dir, 6.0, true)


func shoot_bolt(from: Vector2, angle: float, damage: float, pierce: int, knock: float) -> void:
	var n = Line2D.new()
	n.points = PackedVector2Array([Vector2(-22, 0), Vector2(10, 0)])
	n.width = 4
	n.default_color = Color(0.8, 0.65, 0.4)
	n.position = from
	n.rotation = angle
	fx.add_child(n)
	bolts.append([n, Vector2.from_angle(angle), damage, pierce, [], 1.2, knock])


func spit(from: Vector2, angle: float, damage: float) -> void:
	var n = Sprite2D.new()
	n.texture = load("res://assets/fx/glow.png")
	n.modulate = Color(0.5, 1.0, 0.2)
	n.scale = Vector2.ONE * 0.32
	n.position = from
	var m = CanvasItemMaterial.new()
	m.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
	n.material = m
	fx.add_child(n)
	acids.append([n, Vector2.from_angle(angle) * 7.5 * T, 9.0 / 7.5, damage])
	Sfx.play("spit", 0.1)


func throw_grenade(from: Vector2, to: Vector2) -> void:
	var n = Sprite2D.new()
	n.texture = load("res://assets/pickups/grenade.png")
	n.scale = Vector2.ONE * 0.5
	n.position = from
	fx.add_child(n)
	Sfx.play("pin", 0.05)
	var tw = n.create_tween().set_parallel(true)
	tw.tween_property(n, "position", to, 0.55).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tw.tween_property(n, "rotation", 9.0, 0.55)
	var up = n.create_tween()
	up.tween_property(n, "scale", Vector2.ONE * 0.8, 0.27).set_ease(Tween.EASE_OUT)
	up.tween_property(n, "scale", Vector2.ONE * 0.5, 0.28).set_ease(Tween.EASE_IN)
	up.tween_interval(0.45)
	up.tween_callback(func():
		explode(n.position, 2.8 * T, 140.0, 25.0)
		n.queue_free())


func _projectiles(delta: float) -> void:
	var space = get_world_2d().direct_space_state
	for b in bolts.duplicate():
		var n: Line2D = b[0]
		b[5] -= delta
		var step: Vector2 = b[1] * 28.0 * T * delta
		var from = n.position
		var to = from + step
		var stopped = false
		var exclude = [player.get_rid()]
		for z in b[4]:
			if is_instance_valid(z):
				exclude.append(z.get_rid())
		for i in 8:
			var hit = space.intersect_ray(PhysicsRayQueryParameters2D.create(from, to, 1 | 4, exclude))
			if hit.is_empty():
				break
			if hit.collider is Zombie:
				var z: Zombie = hit.collider
				b[4].append(z)
				exclude.append(hit.rid)
				player.hits += 1
				z.hurt(b[2], b[1], b[6])
				fx_blood(hit.position, b[1].angle(), 0.6)
				b[3] -= 1
				if b[3] < 0:
					stopped = true
					break
			else:
				to = hit.position
				stopped = true
				fx_sparks(to, 4)
				break
		n.position = to
		if stopped or b[5] <= 0:
			bolts.erase(b)
			var tw = n.create_tween()
			tw.tween_interval(0.8)
			tw.tween_property(n, "modulate:a", 0.0, 0.3)
			tw.tween_callback(n.queue_free)
	for a in acids.duplicate():
		var n: Sprite2D = a[0]
		a[2] -= delta
		n.position += a[1] * delta
		var dead = a[2] <= 0 or Data.BLOCKS_SHOTS.contains(_cell(int(n.position.x / T), int(n.position.y / T)))
		if not dead and n.position.distance_to(player.global_position) < player.radius + 8:
			player.hurt(a[3], n.position - a[1])
			dead = true
		if dead:
			fx_decal("goo", n.position, 0.5)
			acids.erase(a)
			n.queue_free()


func _pickups() -> void:
	var p = player.global_position
	for pk in pickups.duplicate():
		var n: Node2D = pk[0]
		if n.global_position.distance_to(p) > 38:
			continue
		var kind: String = pk[1]
		var took = true
		match kind:
			"medkit":
				took = player.heal(40.0)
			"ammo":
				took = player.restock()
			"grenade":
				player.grenades += 2
			"fuel":
				fuel += 1
				hud.emit("banner", "FUEL %d / %d" % [fuel, fuel_needed] if fuel < fuel_needed else "GET TO THE WAY OUT")
		if not took:
			continue
		pickups.erase(pk)
		Sfx.play("pickup", 0.05)
		fx_sparks(n.global_position, 10, Color(1, 0.95, 0.6))
		hud.emit("pickup", kind)
		n.queue_free()


# ------------------------------------------------------------------------------------------------ goals
func exit_open() -> bool:
	return lv.goal == "escape" and fuel >= fuel_needed


func _goals() -> void:
	if player.hp <= 0:
		player.hp = 0
		_end("lost", "You were overrun.")
		return
	if gen_max > 1 and gen_hp <= 0 and lv.goal == "defend":
		gen_hp = 0
		_end("lost", "The generator went down.")
		return
	if lv.endless:
		return
	match lv.goal:
		"survive", "defend":
			if time >= lv.target:
				_end("won", "You made it.")
		"clear":
			if kills >= lv.target:
				_end("won", "That's all of them.")
		"boss":
			if bosses_left <= 0:
				_end("won", "It's down.")
		"escape":
			if exit_open() and _tile(player.global_position) in exits:
				_end("won", "You got out.")


func _end(s: String, words: String) -> void:
	state = s
	why = words
	player.flame.emitting = false
	if s == "won":
		Engine.time_scale = 0.35
		get_tree().create_timer(0.8, true, false, true).timeout.connect(func(): Engine.time_scale = 1.0)
	Sfx.play("win" if s == "won" else "lose", 0.0)
	ended.emit(s == "won")


func progress() -> Array:
	# [fraction, words]
	if lv.endless:
		return [0.0, "%d:%02d  ·  %d down" % [int(time) / 60, int(time) % 60, kills]]
	match lv.goal:
		"survive", "defend":
			return [min(1.0, time / lv.target), "%d s to go" % max(0, ceil(lv.target - time))]
		"clear":
			return [min(1.0, float(kills) / lv.target), "%d of %d down" % [kills, lv.target]]
		"boss":
			var done: int = lv.bosses - bosses_left
			var frac = float(done)
			for z in zombies:
				if z.boss:
					frac += 1.0 - z.hp / z.max_hp
					break
			return [min(1.0, frac / lv.bosses), "Big one" if lv.bosses == 1 else "Big ones: %d of %d down" % [done, lv.bosses]]
		"escape":
			if exit_open():
				return [1.0, "Get to the way out"]
			return [float(fuel) / max(1, fuel_needed), "Fuel %d of %d" % [fuel, fuel_needed]]
	return [0.0, ""]


func stars() -> int:
	if state != "won":
		return 0
	var frac = player.hp / player.max_hp
	if gen_max > 1:
		frac = min(frac, gen_hp / gen_max)
	return Data.stars_for(frac)


func bonus() -> int:
	if state != "won" or lv.endless:
		return 0
	return 15 * int(lv.chapter) + 10 * stars()


func boss() -> Zombie:
	for z in zombies:
		if z.boss:
			return z
	return null


func objectives() -> Array:
	# [world position, colour] of what you're looking for, for the arrows at the edge of the screen
	var out = []
	if lv.goal == "escape":
		if exit_open():
			for e in exits:
				out.append([Vector2(e.x * T + T / 2, e.y * T + T / 2), Color(0.3, 1, 0.5)])
				break
		else:
			for pk in pickups:
				if pk[1] == "fuel":
					out.append([pk[0].global_position, Color(1, 0.4, 0.25)])
	if gen_max > 1:
		out.append([gen_pos, Color(0.95, 0.8, 0.2)])
	for z in zombies:
		if z.boss:
			out.append([z.global_position, Color(0.9, 0.2, 0.2)])
	return out


# ------------------------------------------------------------------------------------------------ effects
func _burst(pos: Vector2, tex: String, amount: int, col: Color, spd: Vector2, life: float, scl: Vector2,
		dir := Vector2.RIGHT, spread := 180.0, additive := false, grow := false) -> void:
	var p = CPUParticles2D.new()
	p.position = pos
	p.one_shot = true
	p.explosiveness = 0.95
	p.amount = amount
	p.lifetime = life
	p.texture = load(tex)
	p.direction = dir
	p.spread = spread
	p.initial_velocity_min = spd.x
	p.initial_velocity_max = spd.y
	p.damping_min = spd.y * 1.2
	p.damping_max = spd.y * 2.0
	p.scale_amount_min = scl.x
	p.scale_amount_max = scl.y
	p.gravity = Vector2.ZERO
	var ramp = Gradient.new()
	ramp.set_color(0, col)
	ramp.set_color(1, Color(col, 0.0))
	p.color_ramp = ramp
	if grow:
		var c = Curve.new()
		c.add_point(Vector2(0, 0.5))
		c.add_point(Vector2(1, 1.8))
		p.scale_amount_curve = c
	if additive:
		var m = CanvasItemMaterial.new()
		m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
		m.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
		p.material = m
	p.emitting = true
	fx.add_child(p)
	p.finished.connect(p.queue_free)


func fx_blood(pos: Vector2, angle: float, amount := 1.0) -> void:
	_burst(pos, "res://assets/fx/dot.png", int(10 * amount) + 4, Color(0.55, 0.03, 0.03), Vector2(90, 330), 0.5,
		Vector2(0.06, 0.13), Vector2.from_angle(angle), 45.0)
	fx_decal("blood", pos + Vector2.from_angle(angle) * randf_range(4, 22), randf_range(0.45, 0.85) * amount)


func fx_decal(kind: String, pos: Vector2, scl: float) -> void:
	var s = Sprite2D.new()
	s.texture = load("res://assets/fx/%s%d.png" % [kind, randi() % (6 if kind == "blood" else 2)]) if kind != "scorch" else load("res://assets/fx/scorch.png")
	s.position = pos
	s.rotation = randf() * TAU
	s.scale = Vector2.ONE * scl
	decals.add_child(s)
	if decals.get_child_count() > MAX_DECALS:
		decals.get_child(exit_nodes.size()).queue_free()


func fx_sparks(pos: Vector2, n := 6, col := Color(1, 0.85, 0.45)) -> void:
	_burst(pos, "res://assets/fx/spark.png", n, col, Vector2(120, 380), 0.22, Vector2(0.08, 0.16), Vector2.RIGHT, 180.0, true)


func fx_fire_puff(pos: Vector2) -> void:
	_burst(pos, "res://assets/fx/fire.png", 2, Color(1, 0.6, 0.2, 0.9), Vector2(10, 40), 0.45, Vector2(0.2, 0.35), Vector2.UP, 30.0, true, true)


func fx_dust(pos: Vector2) -> void:
	_burst(pos, "res://assets/fx/smoke.png", 5, Color(0.6, 0.56, 0.5, 0.5), Vector2(20, 80), 0.6, Vector2(0.3, 0.55), Vector2.RIGHT, 180.0, false, true)


func fx_muzzle(pos: Vector2, angle: float) -> void:
	var s = Sprite2D.new()
	s.texture = load("res://assets/fx/muzzle%d.png" % (randi() % 3))
	s.position = pos + Vector2.from_angle(angle) * 6
	s.rotation = angle
	s.offset = Vector2(14, 0)
	s.scale = Vector2.ONE * randf_range(0.45, 0.6)
	var m = CanvasItemMaterial.new()
	m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	m.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
	s.material = m
	fx.add_child(s)
	get_tree().create_timer(0.045).timeout.connect(s.queue_free)


func fx_shell(pos: Vector2, angle: float) -> void:
	var s = Sprite2D.new()
	s.texture = load("res://assets/fx/shell.png")
	s.position = pos
	s.rotation = randf() * TAU
	decals.add_child(s)
	var side = Vector2.from_angle(angle + PI / 2) * randf_range(26, 44) + Vector2.from_angle(angle + PI) * randf_range(0, 12)
	var tw = s.create_tween().set_parallel(true)
	tw.tween_property(s, "position", pos + side, 0.25).set_ease(Tween.EASE_OUT)
	tw.tween_property(s, "rotation", s.rotation + randf_range(6, 12), 0.25)
	if decals.get_child_count() > MAX_DECALS:
		decals.get_child(exit_nodes.size()).queue_free()


func fx_tracer(a: Vector2, b: Vector2) -> void:
	var l = Line2D.new()
	l.points = PackedVector2Array([a, b])
	l.width = 3.0
	var g = Gradient.new()
	g.set_color(0, Color(1, 0.9, 0.55, 0.0))
	g.set_color(1, Color(1, 0.95, 0.75, 0.9))
	l.gradient = g
	var m = CanvasItemMaterial.new()
	m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	m.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
	l.material = m
	fx.add_child(l)
	var tw = l.create_tween()
	tw.tween_property(l, "modulate:a", 0.0, 0.07)
	tw.tween_callback(l.queue_free)


func fx_ghost(body: AnimatedSprite2D, pos: Vector2, rot: float) -> void:
	var s = Sprite2D.new()
	s.texture = body.sprite_frames.get_frame_texture(body.animation, body.frame)
	s.position = pos
	s.rotation = rot
	s.scale = body.scale
	s.modulate = Color(0.6, 0.8, 1.0, 0.45)
	fx.add_child(s)
	var tw = s.create_tween()
	tw.tween_property(s, "modulate:a", 0.0, 0.25)
	tw.tween_callback(s.queue_free)


func fx_explosion(pos: Vector2, radius: float) -> void:
	_burst(pos, "res://assets/fx/fire.png", 36, Color(1, 0.7, 0.25), Vector2(80, radius * 2.4), 0.6, Vector2(0.5, 1.0), Vector2.RIGHT, 180, true, true)
	_burst(pos, "res://assets/fx/smoke.png", 18, Color(0.25, 0.22, 0.2, 0.75), Vector2(40, radius * 1.4), 1.4, Vector2(0.8, 1.4), Vector2.RIGHT, 180, false, true)
	_burst(pos, "res://assets/fx/spark.png", 24, Color(1, 0.9, 0.5), Vector2(200, 700), 0.45, Vector2(0.06, 0.12), Vector2.RIGHT, 180, true)
	fx_decal("scorch", pos, radius / 64.0 * 0.9)
	var l = _light(pos, Color(1, 0.6, 0.25), 2.5, radius / 160.0, false)
	fx.add_child(l)
	var tw = l.create_tween()
	tw.tween_property(l, "energy", 0.0, 0.5)
	tw.tween_callback(l.queue_free)
	var ring = Sprite2D.new()
	ring.texture = load("res://assets/fx/glow.png")
	ring.position = pos
	ring.modulate = Color(1, 0.8, 0.5, 0.6)
	var m = CanvasItemMaterial.new()
	m.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	ring.material = m
	fx.add_child(ring)
	var tr = ring.create_tween().set_parallel(true)
	tr.tween_property(ring, "scale", Vector2.ONE * radius / 22.0, 0.3)
	tr.tween_property(ring, "modulate:a", 0.0, 0.3)
	tr.chain().tween_callback(ring.queue_free)


func _process(_delta: float) -> void:
	# a few lamps flicker, like they're on their last bulb
	for l in flicker:
		if randf() < 0.06:
			l.energy = randf_range(0.2, 0.6) if l.energy > 0.8 else 1.15
