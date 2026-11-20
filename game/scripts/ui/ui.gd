# SPDX-License-Identifier: GPL-3.0-or-later
# Rotline's look outside the arena: a dark theme with a gold accent, Bebas Neue for titles and Rubik for words, and
# a clear focus ring on every control so a TV remote, a gamepad or a keyboard always shows where you are.
class_name UI
extends RefCounted

const GOLD := Color("#e0a82e")
const RED := Color("#e5484d")
const GREEN := Color("#3ddc84")
const INK := Color("#f2ede4")
const DIM := Color("#a9a39a")
const PANEL := Color("#15171a")
const CARD := Color("#1e2125")

static var _theme: Theme
static var title_font: Font
static var body_font: Font


static func theme() -> Theme:
	if _theme:
		return _theme
	title_font = load("res://assets/fonts/BebasNeue-Regular.ttf")
	body_font = load("res://assets/fonts/Rubik.ttf")
	var t = Theme.new()
	t.default_font = body_font
	t.default_font_size = 20
	t.set_color("font_color", "Label", INK)
	var normal = _box(Color("#24272c"), 12, Color("#33373d"), 1)
	var hover = _box(Color("#2e3238"), 12, Color("#4a4f57"), 1)
	var pressed = _box(GOLD, 12, GOLD, 1)
	var focus = _box(Color(0, 0, 0, 0), 12, GOLD, 3)
	focus.expand_margin_left = 3
	focus.expand_margin_right = 3
	focus.expand_margin_top = 3
	focus.expand_margin_bottom = 3
	var disabled = _box(Color("#1c1e22"), 12, Color("#26292e"), 1)
	for cls in ["Button"]:
		t.set_stylebox("normal", cls, normal)
		t.set_stylebox("hover", cls, hover)
		t.set_stylebox("pressed", cls, pressed)
		t.set_stylebox("hover_pressed", cls, pressed)
		t.set_stylebox("focus", cls, focus)
		t.set_stylebox("disabled", cls, disabled)
		t.set_color("font_color", cls, INK)
		t.set_color("font_hover_color", cls, Color.WHITE)
		t.set_color("font_focus_color", cls, Color.WHITE)
		t.set_color("font_pressed_color", cls, Color("#17130b"))
		t.set_color("font_hover_pressed_color", cls, Color("#17130b"))
		t.set_color("font_disabled_color", cls, Color("#6b6760"))
		t.set_constant("h_separation", cls, 10)
	t.set_stylebox("panel", "PanelContainer", _box(Color(PANEL, 0.94), 22, Color("#2a2d33"), 1))
	var line = _box(Color("#101215"), 10, Color("#3a3e45"), 1)
	t.set_stylebox("normal", "LineEdit", line)
	t.set_stylebox("focus", "LineEdit", _box(Color("#101215"), 10, GOLD, 2))
	t.set_color("font_color", "LineEdit", INK)
	t.set_color("font_placeholder_color", "LineEdit", Color("#6b6760"))
	var sb_bg = _box(Color("#0e0f11"), 6, Color(0, 0, 0, 0), 0)
	var sb_fill = _box(GOLD, 6, Color(0, 0, 0, 0), 0)
	t.set_stylebox("background", "ProgressBar", sb_bg)
	t.set_stylebox("fill", "ProgressBar", sb_fill)
	t.set_stylebox("slider", "HSlider", _box(Color("#2a2d33"), 4, Color(0, 0, 0, 0), 0))
	t.set_stylebox("grabber_area", "HSlider", _box(GOLD, 4, Color(0, 0, 0, 0), 0))
	t.set_stylebox("grabber_area_highlight", "HSlider", _box(GOLD, 4, Color(0, 0, 0, 0), 0))
	t.set_stylebox("focus", "HSlider", focus)
	t.set_stylebox("focus", "CheckButton", focus)
	t.set_color("font_color", "CheckButton", INK)
	t.set_color("font_hover_color", "CheckButton", Color.WHITE)
	t.set_color("font_focus_color", "CheckButton", Color.WHITE)
	t.set_color("font_pressed_color", "CheckButton", INK)
	t.set_color("font_hover_pressed_color", "CheckButton", Color.WHITE)
	t.set_stylebox("panel", "TooltipPanel", _box(PANEL, 8, GOLD, 1))
	_theme = t
	return t


static func _box(bg: Color, radius: int, border: Color, bw: int) -> StyleBoxFlat:
	var s = StyleBoxFlat.new()
	s.bg_color = bg
	s.set_corner_radius_all(radius)
	s.border_color = border
	s.set_border_width_all(bw)
	s.content_margin_left = 18
	s.content_margin_right = 18
	s.content_margin_top = 10
	s.content_margin_bottom = 10
	s.anti_aliasing = true
	return s


static func title(text: String, size := 64, col := INK) -> Label:
	var l = Label.new()
	l.text = text
	l.add_theme_font_override("font", title_font if title_font else theme().default_font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))
	l.add_theme_constant_override("shadow_offset_y", 3)
	l.add_theme_constant_override("shadow_outline_size", 6)
	return l


static func label(text: String, size := 20, col := INK, wrap := false) -> Label:
	var l = Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


static func button(text: String, on_press: Callable, primary := false, size := 22) -> Button:
	var b = Button.new()
	b.text = text
	b.add_theme_font_size_override("font_size", size)
	b.focus_mode = Control.FOCUS_ALL
	b.custom_minimum_size = Vector2(0, 48)
	if primary:
		b.add_theme_stylebox_override("normal", _box(GOLD, 12, GOLD, 1))
		b.add_theme_stylebox_override("hover", _box(Color("#ecb83f"), 12, Color("#ecb83f"), 1))
		b.add_theme_color_override("font_color", Color("#17130b"))
		b.add_theme_color_override("font_hover_color", Color("#17130b"))
		b.add_theme_color_override("font_focus_color", Color("#17130b"))
	b.pressed.connect(func():
		Sfx.play("ui_ok", 0.02)
		on_press.call())
	b.focus_entered.connect(func(): Sfx.play("ui_move", 0.03))
	return b


static func card(bg := CARD, radius := 18) -> PanelContainer:
	var p = PanelContainer.new()
	var s = _box(bg, radius, Color("#2c3036"), 1)
	s.content_margin_left = 16
	s.content_margin_right = 16
	s.content_margin_top = 14
	s.content_margin_bottom = 14
	p.add_theme_stylebox_override("panel", s)
	return p


static func vbox(sep := 10) -> VBoxContainer:
	var v = VBoxContainer.new()
	v.add_theme_constant_override("separation", sep)
	return v


static func hbox(sep := 10) -> HBoxContainer:
	var v = HBoxContainer.new()
	v.add_theme_constant_override("separation", sep)
	return v


static func stars(n: int, size := 26) -> Label:
	var l = Label.new()
	l.text = "★".repeat(n) + "☆".repeat(3 - n)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", GOLD)
	return l


static func spacer() -> Control:
	var c = Control.new()
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	c.size_flags_vertical = Control.SIZE_EXPAND_FILL
	return c
