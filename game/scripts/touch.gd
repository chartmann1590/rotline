# SPDX-License-Identifier: GPL-3.0-or-later
# Touch controls: a stick on the left to move, a stick on the right to aim and fire (or leave it and the game aims
# for you), and buttons to roll, throw a grenade and switch weapon. Shown when a finger touches the screen.
extends Control

var main
var move_vec = Vector2.ZERO
var aim_vec = Vector2.ZERO
var _move_id = -1
var _aim_id = -1
var _move_origin = Vector2.ZERO
var _aim_origin = Vector2.ZERO
var _move_at = Vector2.ZERO
var _aim_at = Vector2.ZERO
var _pressed = {}
var _buttons = {}
const R := 70.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _shown() -> bool:
	var mode: String = Game.setting("touch")
	return mode == "always" or (mode == "auto" and Game.touch_seen)


func take(name: String) -> bool:
	if _pressed.get(name, false):
		_pressed[name] = false
		return true
	return false


func _layout() -> void:
	var s = size
	var r: float = clamp(s.y * 0.075, 40.0, 70.0)
	_buttons = {
		"dodge": [Vector2(s.x - r * 1.5, s.y - r * 3.8), r * 0.8, "ROLL"],
		"grenade": [Vector2(s.x - r * 3.4, s.y - r * 4.4), r * 0.62, "NADE"],
		"switch": [Vector2(s.x - r * 1.5, s.y - r * 5.9), r * 0.62, "SWAP"],
	}


func _input(event: InputEvent) -> void:
	if not _shown() or get_tree().paused:
		return
	_layout()
	var xf = get_global_transform_with_canvas().affine_inverse()
	if event is InputEventScreenTouch:
		var pos: Vector2 = xf * event.position
		if event.pressed:
			for b in _buttons:
				if pos.distance_to(_buttons[b][0]) < _buttons[b][1] * 1.2:
					_pressed[b] = true
					get_viewport().set_input_as_handled()
					return
			if pos.y < 90:
				return
			if pos.x < size.x * 0.5 and _move_id < 0:
				_move_id = event.index
				_move_origin = pos
				_move_at = pos
			elif pos.x >= size.x * 0.5 and _aim_id < 0:
				_aim_id = event.index
				_aim_origin = pos
				_aim_at = pos
		else:
			if event.index == _move_id:
				_move_id = -1
				move_vec = Vector2.ZERO
			if event.index == _aim_id:
				_aim_id = -1
				aim_vec = Vector2.ZERO
		queue_redraw()
	elif event is InputEventScreenDrag:
		var pos: Vector2 = xf * event.position
		if event.index == _move_id:
			_move_at = pos
			move_vec = ((_move_at - _move_origin) / R).limit_length(1.0)
		elif event.index == _aim_id:
			_aim_at = pos
			aim_vec = ((_aim_at - _aim_origin) / R).limit_length(1.0)
		queue_redraw()


func _process(_delta: float) -> void:
	if _shown():
		queue_redraw()


func _draw() -> void:
	if not _shown():
		return
	_layout()
	if _move_id >= 0:
		draw_circle(_move_origin, R, Color(1, 1, 1, 0.12))
		draw_arc(_move_origin, R, 0, TAU, 48, Color(1, 1, 1, 0.3), 3)
		draw_circle(_move_origin + move_vec * R, R * 0.42, Color(1, 1, 1, 0.45))
	else:
		draw_arc(Vector2(R * 1.6, size.y - R * 1.8), R, 0, TAU, 48, Color(1, 1, 1, 0.12), 3)
	if _aim_id >= 0:
		draw_circle(_aim_origin, R, Color(1, 0.5, 0.3, 0.12))
		draw_arc(_aim_origin, R, 0, TAU, 48, Color(1, 0.6, 0.4, 0.35), 3)
		draw_circle(_aim_origin + aim_vec * R, R * 0.42, Color(1, 0.6, 0.4, 0.5))
	var font = UI.title_font
	for b in _buttons:
		var spec: Array = _buttons[b]
		draw_circle(spec[0], spec[1], Color(0, 0, 0, 0.45))
		draw_arc(spec[0], spec[1], 0, TAU, 40, Color(1, 1, 1, 0.35), 2)
		if font:
			var fs = int(spec[1] * 0.5)
			var w = font.get_string_size(spec[2], HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
			draw_string(font, spec[0] + Vector2(-w / 2, fs * 0.35), spec[2], HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(1, 1, 1, 0.85))
