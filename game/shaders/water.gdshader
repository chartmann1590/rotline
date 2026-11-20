// SPDX-License-Identifier: GPL-3.0-or-later
// Rotline: moving light on the water, sampled in world space so tiles join up.
shader_type canvas_item;
uniform sampler2D noise : repeat_enable, filter_linear;
varying vec2 world;

void vertex() {
	world = (MODEL_MATRIX * vec4(VERTEX, 0.0, 1.0)).xy;
}

void fragment() {
	vec4 base = texture(TEXTURE, UV);
	float a = texture(noise, world / 380.0 + vec2(TIME * 0.02, TIME * 0.013)).a;
	float b = texture(noise, world / 230.0 - vec2(TIME * 0.031, -TIME * 0.017)).a;
	float caustic = smoothstep(0.42, 0.62, a + b * 0.8 - 0.25);
	vec3 deep = base.rgb * (0.85 + 0.3 * b);
	COLOR = vec4(deep + vec3(0.16, 0.24, 0.28) * caustic, base.a);
}
