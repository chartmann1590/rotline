# SPDX-License-Identifier: GPL-3.0-or-later
# The survivor: walks, dodge-rolls, aims (or lets the game aim), shoots six kinds of weapon, throws grenades and
# carries a torch whose beam casts real shadows off every wall, car and crate.
class_name Player
extends CharacterBody2D

var world
var hp = 100.0
var max_hp = 100.0
var speed = 4.0 * Data.TILE
var radius = 21.0
var weapon = "pistol"
var weapons: Array = ["pistol"]
var ammo = {}
var grenades = 2
var cool = 0.0
var hurt_t = 0.0
var dodge_t = 0.0
var dodge_cd = 0.0
var dodge_dir = Vector2.RIGHT
var aim = 0.0
var target: Zombie = null
var shots = 0
var hits = 0
var medkits = 0
var walk = 0.0
var firing = false
var dmg_mult = 1.0
var rate_mult = 1.0
var ammo_mult = 1.0
var hurt_mult = 1.0

var body: AnimatedSprite2D
var gun: Sprite2D
var torch: PointLight2D
var near: PointLight2D
var flash_light: PointLight2D
var flame: CPUParticles2D
var ghost_t = 0.0


func setup(w, pos: Vector2, survivor: String, have: Array, ups: Dictionary, easy: bool) -> void:
	world = w
	position = pos
	collision_layer = 2
	collision_mask = 1 | 32
	motion_mode = CharacterBody2D.MOTION_MODE_FLOATING
	max_hp = 100.0 + 15.0 * ups.get("health", 0)
	hp = max_hp
	speed = 4.0 * Data.TILE * (1.0 + 0.05 * ups.get("speed", 0))
	dmg_mult = 1.0 + 0.1 * ups.get("damage", 0)
	rate_mult = 1.0 / (1.0 + 0.08 * ups.get("rate", 0))
	ammo_mult = 1.0 + 0.2 * ups.get("ammo", 0)
	hurt_mult = 0.5 if easy else 1.0
	weapons = Data.ORDER.filter(func(x): return x in have)
	if weapons.is_empty():
		weapons = ["pistol"]
	for x in weapons:
		if Data.WEAPONS[x].ammo > 0:
			ammo[x] = int(Data.WEAPONS[x].ammo * ammo_mult)
	var cs = CollisionShape2D.new()
	var shape = CircleShape2D.new()
	shape.radius = radius
	cs.shape = shape
	add_child(cs)
	body = AnimatedSprite2D.new()
	var tex: Texture2D = load("res://assets/people/%s.png" % survivor)
	var sf = SpriteFrames.new()
	sf.add_animation("walk")
	sf.set_animation_speed("walk", 12.0)
	for i in 8:
		var a = AtlasTexture.new()
		a.atlas = tex
		a.region = Rect2(i * 128, 0, 128, 128)
		sf.add_frame("walk", a)
	sf.remove_animation("default")
	body.sprite_frames = sf
	body.animation = "walk"
	body.scale = Vector2.ONE * 1.2
	add_child(body)
	gun = Sprite2D.new()
	gun.scale = body.scale
	add_child(gun)
	_set_gun()
	torch = PointLight2D.new()
	torch.texture = load("res://assets/light/cone.png")
	torch.texture_scale = 1.15
	torch.energy = 1.25
	torch.color = Color(1.0, 0.93, 0.8)
	torch.shadow_enabled = true
	torch.shadow_filter = Light2D.SHADOW_FILTER_PCF5
	torch.shadow_filter_smooth = 3.0
	torch.shadow_color = Color(0, 0, 0, 0.85)
	add_child(torch)
	near = PointLight2D.new()
	near.texture = load("res://assets/light/round.png")
	near.texture_scale = 0.75
	near.energy = 0.7
	near.color = Color(0.9, 0.9, 1.0)
	near.shadow_enabled = true
	near.shadow_filter = Light2D.SHADOW_FILTER_PCF5
	add_child(near)
	flash_light = PointLight2D.new()
	flash_light.texture = load("res://assets/light/round.png")
	flash_light.texture_scale = 1.1
	flash_light.energy = 0.0
	flash_light.color = Color(1.0, 0.75, 0.4)
	add_child(flash_light)
	flame = CPUParticles2D.new()
	flame.emitting = false
	flame.amount = 90
	flame.lifetime = 0.42
	flame.local_coords = false
	flame.texture = load("res://assets/fx/fire.png")
	flame.direction = Vector2.RIGHT
	flame.spread = 14.0
	flame.initial_velocity_min = 430.0
	flame.initial_velocity_max = 560.0
	flame.damping_min = 300.0
	flame.damping_max = 500.0
	flame.scale_amount_min = 0.25
	flame.scale_amount_max = 0.45
	var curve = Curve.new()
	curve.add_point(Vector2(0, 0.4))
	curve.add_point(Vector2(1, 2.4))
	flame.scale_amount_curve = curve
	var ramp = Gradient.new()
	ramp.set_color(0, Color(1, 0.95, 0.6, 1))
	ramp.add_point(0.35, Color(1, 0.55, 0.12, 0.95))
	ramp.add_point(0.75, Color(0.75, 0.15, 0.05, 0.6))
	ramp.set_color(ramp.get_point_count() - 1, Color(0.15, 0.12, 0.1, 0))
	flame.color_ramp = ramp
	var mat = CanvasItemMaterial.new()
	mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	mat.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
	flame.material = mat
	flame.position = Vector2(40, 0)
	add_child(flame)


func _set_gun() -> void:
	gun.texture = load("res://assets/guns/%s.png" % weapon)


func select(w: String) -> bool:
	if w in weapons and w != weapon:
		weapon = w
		_set_gun()
		cool = max(cool, 0.15)
		Sfx.play("switch", 0.02)
		world.emit_signal("hud", "weapon", w)
		return true
	return false


func cycle(d: int) -> void:
	var i = weapons.find(weapon)
	for n in range(1, weapons.size() + 1):
		var w: String = weapons[(i + d * n + weapons.size() * 4) % weapons.size()]
		if Data.WEAPONS[w].ammo == 0 or ammo.get(w, 0) > 0:
			select(w)
			return


func has_ammo(w: String) -> bool:
	return Data.WEAPONS[w].ammo == 0 or ammo.get(w, 0) > 0


func step(delta: float, inp: Dictionary) -> void:
	cool = max(0.0, cool - delta)
	hurt_t = max(0.0, hurt_t - delta)
	dodge_cd = max(0.0, dodge_cd - delta)
	var move: Vector2 = inp.move
	if move.length() > 1.0:
		move = move.normalized()
	if inp.dodge and dodge_cd <= 0 and dodge_t <= 0:
		dodge_dir = move.normalized() if move.length() > 0.2 else Vector2.from_angle(aim)
		dodge_t = 0.28
		dodge_cd = 0.85
		Sfx.play("dodge", 0.1)
		world.fx_dust(global_position)
	if dodge_t > 0:
		dodge_t -= delta
		velocity = dodge_dir * speed * 2.6
		ghost_t -= delta
		if ghost_t <= 0:
			ghost_t = 0.04
			world.fx_ghost(body, global_position, rotation)
	else:
		velocity = velocity.lerp(move * speed, min(1.0, delta * 14.0))
	move_and_slide()
	if velocity.length() > 20:
		walk += delta
		body.play("walk")
		body.speed_scale = velocity.length() / speed
	else:
		body.pause()
	# aiming: by hand, or at the nearest one it can see
	target = null
	if inp.aim != null:
		aim = inp.aim
	else:
		target = _nearest()
		if target:
			aim = (target.global_position - global_position).angle()
		elif move.length() > 0.1:
			aim = move.angle()
	rotation = lerp_angle(rotation, aim, min(1.0, delta * 22.0))
	firing = inp.fire or (inp.aim == null and inp.auto_fire and target != null)
	if firing and dodge_t <= 0:
		fire()
	flame.emitting = firing and weapon == "flamer" and has_ammo("flamer") and dodge_t <= 0
	flash_light.energy = max(0.0, flash_light.energy - delta * 18.0)
	if flame.emitting:
		flash_light.energy = randf_range(0.9, 1.4)
		flash_light.color = Color(1.0, 0.55, 0.2)
	if inp.grenade and grenades > 0:
		var to: Vector2 = Vector2.from_angle(aim) * 5.5 * Data.TILE
		if target:
			to = target.global_position - global_position
		if to.length() > 7 * Data.TILE:
			to = to.normalized() * 7 * Data.TILE
		grenades -= 1
		world.throw_grenade(global_position, global_position + to)
	if inp.switch != 0:
		cycle(inp.switch)


func _nearest() -> Zombie:
	var reach: float = Data.WEAPONS[weapon].range * Data.TILE * 1.05
	var best: Zombie = null
	var best_d = reach * reach
	for z in world.zombies:
		if z.dead or not z.los or z.rising > 0.2:
			continue
		var d: float = global_position.distance_squared_to(z.global_position)
		if d < best_d:
			best = z
			best_d = d
	return best


func fire() -> void:
	if cool > 0:
		return
	var spec: Dictionary = Data.WEAPONS[weapon]
	if spec.ammo > 0:
		if ammo.get(weapon, 0) <= 0:
			Sfx.play("empty", 0.0)
			cool = 0.35
			_switch_from_empty()
			return
		ammo[weapon] -= 1
	cool = spec.rate * rate_mult
	shots += 1
	var muzzle = global_position + Vector2.from_angle(aim) * 40.0
	if not world.clear_line(global_position, muzzle):
		muzzle = global_position
	match spec.kind:
		"hitscan":
			for i in spec.pellets:
				var a = aim + randf_range(-spec.spread, spec.spread)
				world.hitscan(muzzle, a, spec.range * Data.TILE * randf_range(0.92, 1.0), spec.damage * dmg_mult, spec.pierce, spec.knock)
			world.fx_muzzle(muzzle, aim)
			world.fx_shell(global_position, aim)
			flash_light.energy = 1.8
			flash_light.color = Color(1.0, 0.8, 0.45)
		"flame":
			world.flame_tick(muzzle, aim, spec.range * Data.TILE, spec.spread, spec.damage * dmg_mult)
		"bolt":
			world.shoot_bolt(muzzle, aim, spec.damage * dmg_mult, spec.pierce, spec.knock)
	Sfx.play(spec.sound, 0.06)
	world.add_shake(spec.shake)


func _switch_from_empty() -> void:
	for i in range(weapons.size() - 1, -1, -1):
		var w: String = weapons[i]
		if has_ammo(w):
			if w != weapon:
				select(w)
			return


func hurt(amount: float, from: Vector2) -> void:
	if dodge_t > 0 or hp <= 0:
		return
	hp -= amount * hurt_mult
	hurt_t = 0.35
	Sfx.play("hurt", 0.1)
	world.add_shake(0.35)
	world.fx_blood(global_position, (global_position - from).angle(), 0.8)
	world.emit_signal("hud", "hurt", amount)
	velocity += (global_position - from).normalized() * 160.0


func heal(amount: float) -> bool:
	if hp >= max_hp:
		return false
	hp = min(max_hp, hp + amount)
	medkits += 1
	return true


func restock() -> bool:
	var full = true
	for w in weapons:
		var spec: Dictionary = Data.WEAPONS[w]
		if spec.ammo > 0 and ammo.get(w, 0) < int(spec.max_ammo * ammo_mult):
			full = false
	if full and weapons.any(func(w): return Data.WEAPONS[w].ammo > 0):
		return false
	for w in weapons:
		var spec: Dictionary = Data.WEAPONS[w]
		if spec.ammo > 0:
			ammo[w] = min(int(spec.max_ammo * ammo_mult), ammo.get(w, 0) + int(spec.pickup * ammo_mult))
	return true
