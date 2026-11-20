# SPDX-License-Identifier: GPL-3.0-or-later
# A little map of a level for its card: walls, roads, water, cars, the start and where the dead come from.
extends Control

var level: Dictionary
var locked = false

const COLOURS := {
	"#": Color("#6e5448"), ",": Color("#3a3c40"), ".": Color("#4a6638"), "=": Color("#7d6448"), "~": Color("#1d4a66"),
	"c": Color("#a33a30"), "t": Color("#2e5a26"), "x": Color("#8b6a3e"), "f": Color("#8a8f96"), "P": Color("#3ddc84"),
	"S": Color("#e5484d"), "E": Color("#3ddc84"), "F": Color("#ff7a3a"), "G": Color("#e0b12e"), "h": Color("#ffffff"),
	"a": Color("#d9c060"), "g": Color("#88aa44"),
}


func _draw() -> void:
	if level.is_empty():
		return
	var rows: Array = level.map
	var h = rows.size()
	var w: int = rows[0].length()
	var cell: float = min(size.x / w, size.y / h)
	var off = (size - Vector2(w, h) * cell) / 2
	draw_rect(Rect2(Vector2.ZERO, size), Color("#101214"))
	for j in h:
		for i in w:
			var ch: String = rows[j][i]
			var col: Color = COLOURS.get(ch, COLOURS["."])
			if "PSEFGhag".contains(ch):
				draw_rect(Rect2(off + Vector2(i, j) * cell, Vector2(cell, cell)), COLOURS["."])
				draw_circle(off + Vector2(i + 0.5, j + 0.5) * cell, cell * 0.6, col)
			else:
				draw_rect(Rect2(off + Vector2(i, j) * cell, Vector2(cell, cell)), col)
	if locked:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, 0, 0.6))
		var font = UI.title_font
		if font:
			var t = "LOCKED"
			var fs = 34
			var tw = font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
			draw_string(font, Vector2((size.x - tw) / 2, size.y / 2 + 12), t, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(1, 1, 1, 0.85))
