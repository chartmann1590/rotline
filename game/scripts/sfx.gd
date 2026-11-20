# SPDX-License-Identifier: GPL-3.0-or-later
# Sfx (autoload): every sound effect, played with a little pitch wobble so repeats don't sound canned, and the music.
extends Node

const NAMES := ["boom", "clang", "crossbow", "dodge", "empty", "flame", "groan", "heart", "hit", "hurt", "lose",
	"pickup", "pin", "pistol", "rifle", "roar", "shotgun", "smg", "spit", "splat", "switch", "thunder", "ui_move",
	"ui_ok", "wave", "win"]
const GAP := {"smg": 0.05, "flame": 0.09, "hit": 0.04, "splat": 0.06, "groan": 0.5, "pickup": 0.05, "clang": 0.2,
	"heart": 0.5}
const VOLUME := {"groan": -6.0, "hit": -4.0, "flame": -3.0, "ui_move": -8.0, "thunder": 2.0, "heart": -2.0}

var players = {}
var last = {}
var music: AudioStreamPlayer
var music_name = ""


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for n in NAMES:
		var p = AudioStreamPlayer.new()
		p.stream = load("res://assets/sfx/%s.wav" % n)
		p.max_polyphony = 6
		p.bus = "Master"
		add_child(p)
		players[n] = p
	music = AudioStreamPlayer.new()
	add_child(music)
	apply_volume()


func apply_volume() -> void:
	var sv: float = Game.setting("sfx")
	for n in players:
		players[n].volume_db = (linear_to_db(max(0.001, sv)) + VOLUME.get(n, 0.0)) if sv > 0.001 else -80.0
	var mv: float = Game.setting("music")
	music.volume_db = linear_to_db(max(0.001, mv)) - 6.0 if mv > 0.001 else -80.0


func play(name: String, pitch_wobble := 0.08, volume := 0.0) -> void:
	if not players.has(name):
		return
	var now = Time.get_ticks_msec() / 1000.0
	if now - float(last.get(name, -9.0)) < GAP.get(name, 0.02):
		return
	last[name] = now
	var p: AudioStreamPlayer = players[name]
	p.pitch_scale = 1.0 + randf_range(-pitch_wobble, pitch_wobble)
	var sv: float = Game.setting("sfx")
	if sv <= 0.001:
		return
	p.volume_db = linear_to_db(sv) + VOLUME.get(name, 0.0) + volume
	p.play()


func play_music(name: String) -> void:
	if music_name == name and music.playing:
		return
	music_name = name
	var s: AudioStreamWAV = load("res://assets/sfx/%s.wav" % name)
	s.loop_mode = AudioStreamWAV.LOOP_FORWARD
	s.loop_begin = 0
	s.loop_end = int(s.get_length() * s.mix_rate)
	music.stream = s
	apply_volume()
	music.play()


func stop_music() -> void:
	music.stop()
	music_name = ""
