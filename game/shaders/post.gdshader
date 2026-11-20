// SPDX-License-Identifier: GPL-3.0-or-later
// Rotline: the last pass over the picture: a vignette, a little film grain, red when you're hurt, and the colour
// draining away when you're nearly gone.
shader_type canvas_item;
render_mode unshaded;
uniform sampler2D screen : hint_screen_texture, filter_linear;
uniform float hurt = 0.0;
uniform float low = 0.0;
uniform float grain = 0.035;

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void fragment() {
	vec3 c = texture(screen, SCREEN_UV).rgb;
	float grey = dot(c, vec3(0.299, 0.587, 0.114));
	c = mix(c, vec3(grey), low * 0.75);
	vec2 d = SCREEN_UV - 0.5;
	float v = smoothstep(0.85, 0.25, length(d * vec2(1.15, 1.0)));
	c *= mix(0.55, 1.0, v);
	c = mix(c, vec3(0.75, 0.02, 0.02), hurt * (1.0 - v * 0.7) * 0.6);
	c += (hash(SCREEN_UV * 900.0 + TIME) - 0.5) * grain;
	COLOR = vec4(c, 1.0);
}
