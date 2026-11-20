# SPDX-License-Identifier: GPL-3.0-or-later
# Updates (autoload): asks GitHub, at most twice a day, whether a newer release is out, so the menu can say so with
# the release notes. It never downloads or installs anything: copies from Depot update through Depot (Luma review
# 1.3), and GitHub copies are pointed to the release page.
extends Node

signal found

const REPO := "chartmann1590/rotline"
const APP_ID := "com.charleshartmann.Rotline"
const VERSION := "1.0.0"
const EVERY := 12 * 3600

var api = "https://api.github.com"
var channel = "depot"
var latest: Dictionary = {}        # {version, notes, url} when newer than this one
var state_path = "user://updates.json"


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if OS.has_environment("HS_UPDATES_API"):
		api = OS.get_environment("HS_UPDATES_API").trim_suffix("/")
	var marker = "/app/share/%s/channel" % APP_ID
	if FileAccess.file_exists(marker):
		channel = FileAccess.get_file_as_string(marker).strip_edges()
	await get_tree().create_timer(6.0).timeout
	if Game.setting("updates"):
		check(false)


static func newer(a: String, b: String) -> bool:
	# True when version a is newer than b ("1.2.0" > "1.1.9").
	var pa = a.trim_prefix("v").split(".")
	var pb = b.trim_prefix("v").split(".")
	for i in max(pa.size(), pb.size()):
		var x = int(pa[i]) if i < pa.size() else 0
		var y = int(pb[i]) if i < pb.size() else 0
		if x != y:
			return x > y
	return false


func check(manual: bool) -> void:
	var st = _state()
	var now = Time.get_unix_time_from_system()
	if not manual and now - float(st.get("checked", 0)) < EVERY:
		if st.has("latest") and newer(str(st.latest.get("version", "")), VERSION):
			latest = st.latest
			found.emit()
		return
	var http = HTTPRequest.new()
	http.timeout = 15.0
	add_child(http)
	var err = http.request(api + "/repos/%s/releases/latest" % REPO,
		["Accept: application/vnd.github+json", "User-Agent: Rotline/" + VERSION])
	if err != OK:
		http.queue_free()
		return
	var res: Array = await http.request_completed
	http.queue_free()
	st["checked"] = now
	if res[0] == HTTPRequest.RESULT_SUCCESS and res[1] == 200:
		var doc = JSON.parse_string((res[3] as PackedByteArray).get_string_from_utf8())
		if doc is Dictionary and not doc.get("draft", false):
			var v = str(doc.get("tag_name", "")).trim_prefix("v")
			var info = {"version": v, "notes": str(doc.get("body", "")).left(1500), "url": str(doc.get("html_url", ""))}
			st["latest"] = info
			if newer(v, VERSION):
				latest = info
				found.emit()
			elif manual:
				latest = {}
	_save_state(st)


func _state() -> Dictionary:
	if FileAccess.file_exists(state_path):
		var doc = JSON.parse_string(FileAccess.get_file_as_string(state_path))
		if doc is Dictionary:
			return doc
	return {}


func _save_state(st: Dictionary) -> void:
	var f = FileAccess.open(state_path, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(st))
