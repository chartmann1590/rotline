# SPDX-License-Identifier: GPL-3.0-or-later
# One of the dead. Walks the world's distance field to you (or the generator), bites, and some do more:
# spitters keep their distance and spit, bloaters burst, and the Tank winds up and charges.
class_name Zombie
extends CharacterBody2D

static var _frames = {}

var world
var kind = "walker"
var k: Dictionary
var hp = 1.0
var max_hp = 1.0
var boss = false
var state = "walk"          # walk, windup, charge
var state_t = 3.0
var charge_dir = Vector2.ZERO
var cool = 0.6
var spit = 1.5
var burn = 0.0
var flash = 0.0
var los = false
var los_t = 0.0
var goes_for_gen = false
var stuck = 0.0
var check = 2.0
var last_pos = Vector2.ZERO
var radius = 20.0
var dead = false
var rising = 0.35
var body: AnimatedSprite2D
var speed_mult = 1.0


static func frames_for(which: String) -> SpriteFrames:
	if _frames.has(which):
		return _frames[which]
	var tex: Texture2D = load("res://assets/dead/%s.png" % which)
	var cell = tex.get_height()
	var sf = SpriteFrames.new()
	sf.add_animation("walk")
	sf.set_animation_speed("walk", 9.0)
	for i in 8:
		var a = AtlasTexture.new()
		a.atlas = tex
		a.region = Rect2(i * cell, 0, cell, cell)
		sf.add_frame("walk", a)
	sf.add_animation("bite")
	var b = AtlasTexture.new()
	b.atlas = tex
	b.region = Rect2(8 * cell, 0, cell, cell)
	sf.add_frame("bite", b)
	sf.remove_animation("default")
	_frames[which] = sf
	return sf


func setup(w, which: String, pos: Vector2, hp_mult := 1.0, is_boss := false) -> void:
	world = w
	kind = which
	k = Data.KINDS[which]
	boss = is_boss
	hp = k.hp * hp_mult
	max_hp = hp
	radius = k.radius * Data.TILE
	position = pos
	last_pos = pos
	goes_for_gen = randi() % 3 == 0
	los_t = randf() * 0.25
	speed_mult = randf_range(0.9, 1.12)
	collision_layer = 4
	collision_mask = 1 | 2 | 4 | 32
	motion_mode = CharacterBody2D.MOTION_MODE_FLOATING
	var shape = CircleShape2D.new()
	shape.radius = min(radius, 26.0)   # the big ones squeeze through doors like everyone else
	var cs = CollisionShape2D.new()
	cs.shape = shape
	add_child(cs)
	body = AnimatedSprite2D.new()
	body.sprite_frames = frames_for(which)
	body.play("walk")
	body.frame = randi() % 8
	# how wide the body is drawn in its sheet, so every kind comes out at its own size
	var drawn = {"walker": 40.0, "runner": 40.0, "spitter": 40.0, "brute": 100.0, "bloater": 138.0, "tank": 156.0}
	body.scale = Vector2.ONE * (radius * 2.5) / drawn[which]
	add_child(body)
	if boss:
		state_t = 4.0
	modulate = Color(1, 1, 1, 0)
	scale = Vector2.ONE * 0.6


func _physics_process(delta: float) -> void:
	if dead or world == null or world.state != "play":
		return
	if rising > 0:
		rising -= delta
		var t: float = clamp(1.0 - rising / 0.35, 0.0, 1.0)
		modulate.a = t
		scale = Vector2.ONE * lerp(0.6, 1.0, t)
	flash = max(0.0, flash - delta)
	body.self_modulate = Color(6, 6, 6) if flash > 0 else (Color(1.5, 0.75, 0.4) if burn > 0 else Color.WHITE)
	cool = max(0.0, cool - delta)
	if burn > 0:
		burn -= delta
		hp -= 16.0 * delta
		if randf() < 0.35:
			world.fx_fire_puff(global_position + Vector2(randf_range(-12, 12), randf_range(-12, 12)))
		if hp <= 0:
			world.kill(self)
			return
	var p = world.player
	var target: Vector2 = p.global_position
	var field: PackedInt32Array = world.field
	if world.gen_hp > 0 and goes_for_gen and not boss:
		var gd = global_position.distance_squared_to(world.gen_pos)
		var pd = global_position.distance_squared_to(target)
		if gd < pd * 2.5:
			target = world.gen_pos
			field = world.gen_field
	var to = target - global_position
	var dist = to.length()
	los_t -= delta
	if los_t <= 0:
		los = dist < 20 * Data.TILE and world.clear_line(global_position, p.global_position)
		los_t = 0.25
	var sees = (los and field == world.field) or dist < 1.3 * Data.TILE
	var dir: Vector2 = to / max(dist, 0.001) if sees else world.follow(field, global_position)
	var speed: float = k.speed * Data.TILE * speed_mult
	if kind == "spitter" and los and field == world.field:
		spit -= delta
		if dist < 4.0 * Data.TILE:
			dir = -dir
		elif dist < 7.5 * Data.TILE:
			dir = dir.orthogonal() * 0.5
		if spit <= 0 and dist < 9 * Data.TILE:
			world.spit(global_position, to.angle() + randf_range(-0.08, 0.08), k.damage)
			spit = randf_range(1.8, 2.8)
	if kind == "tank":
		speed = _tank(delta, to, dist)
		if state == "charge":
			dir = charge_dir
		elif state == "windup":
			dir = Vector2.ZERO
	if dir != Vector2.ZERO:
		rotation = lerp_angle(rotation, dir.angle(), min(1.0, delta * 10))
	velocity = velocity.lerp(dir * speed, min(1.0, delta * 8))
	move_and_slide()
	body.speed_scale = clamp(velocity.length() / (Data.TILE * 1.3), 0.4, 2.5)
	if state == "charge" and get_slide_collision_count() > 0:
		var c = get_slide_collision(0)
		if c.get_collider() is StaticBody2D or c.get_collider() is TileMapLayer:
			state = "walk"
			state_t = 2.5
			world.add_shake(0.5)
			Sfx.play("boom", 0.1, -6)
	_unstick(delta)
	# biting
	var reach = radius + p.radius + 8.0
	if global_position.distance_to(p.global_position) < reach and cool <= 0:
		if kind == "bloater":
			world.kill(self)
			return
		body.play("bite")
		get_tree().create_timer(0.18).timeout.connect(func(): if is_instance_valid(body): body.play("walk"))
		p.hurt(k.damage * (1.3 if state == "charge" else 1.0), global_position)
		cool = 0.9
		if state == "charge":
			state = "walk"
			state_t = 3.5
	if world.gen_hp > 0 and global_position.distance_to(world.gen_pos) < radius + 44 and cool <= 0:
		world.hit_generator(k.damage)
		cool = 0.9


func _tank(delta: float, to: Vector2, dist: float) -> float:
	state_t -= delta
	match state:
		"walk":
			if state_t <= 0 and los and dist < 11 * Data.TILE:
				state = "windup"
				state_t = 0.8
				Sfx.play("roar", 0.05)
				world.add_shake(0.25)
			return k.speed * Data.TILE
		"windup":
			body.position = Vector2(randf_range(-3, 3), randf_range(-3, 3))
			if state_t <= 0:
				state = "charge"
				state_t = 1.1
				charge_dir = to.normalized()
				body.position = Vector2.ZERO
			return 0.0
	if randf() < 0.5:
		world.fx_dust(global_position - charge_dir * 30)
	if state_t <= 0:
		state = "walk"
		state_t = randf_range(3.0, 5.0)
	return 7.0 * Data.TILE


func _unstick(delta: float) -> void:
	# One that hasn't got anywhere for a while walks back in from a spawn point, so a level never waits on it.
	check -= delta
	if check > 0:
		return
	check = 2.0
	var moved = global_position.distance_to(last_pos)
	last_pos = global_position
	var lost: bool = not world.reachable(global_position)
	if (moved < 18.0 and not los and state == "walk") or lost:
		stuck += 2.0
	else:
		stuck = 0.0
	if stuck >= 6.0:
		global_position = world.spawn_point(true)
		last_pos = global_position
		stuck = 0.0


func hurt(amount: float, dir: Vector2, knock: float, burning := false) -> void:
	if dead:
		return
	hp -= amount
	flash = 0.07
	if burning:
		burn = 2.4
	else:
		velocity += dir * knock / k.mass * 6.0
	if hp <= 0:
		world.kill(self)
