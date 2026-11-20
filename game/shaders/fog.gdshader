// SPDX-License-Identifier: GPL-3.0-or-later
// Rotline: two layers of fog drifting across the screen at different speeds.
shader_type canvas_item;
render_mode unshaded;

void fragment() {
	vec2 uv = SCREEN_UV * vec2(1.6, 0.9);
	float a = texture(TEXTURE, uv + vec2(TIME * 0.012, TIME * 0.004)).a;
	float b = texture(TEXTURE, uv * 1.7 - vec2(TIME * 0.02, -TIME * 0.006)).a;
	float f = clamp(a * 0.9 + b * 0.7, 0.0, 1.0);
	COLOR = vec4(0.78, 0.84, 0.9, f * 0.42);
}
