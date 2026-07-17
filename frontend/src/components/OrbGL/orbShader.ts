/**
 * Shaders do OrbGL — um quad fullscreen + fragment shader (sem three.js).
 *
 * A esfera é resolvida analiticamente no fragment (normal fake por
 * profundidade), com aurora FBM domain-warped em 3 cores da marca, fresnel
 * com dispersão cromática na borda, glow externo analítico (sem multipass),
 * espiral de ingestão, luas keplerianas (posições vêm da CPU como uniforms)
 * e cometa. Estados nunca trocam o shader — só uniforms.
 */

export const ORB_VERT = `#version 300 es
in vec2 aPos;
void main() {
  gl_Position = vec4(aPos, 0.0, 1.0);
}
`;

export const ORB_FRAG = `#version 300 es
precision highp float;

uniform vec2 uRes;
uniform float uTime;
uniform vec3 uC1;         // accent
uniform vec3 uC2;         // accent-light
uniform vec3 uC3;         // accent-purple
uniform vec3 uStateColor; // success/error
uniform vec3 uMoon1Color;
uniform vec3 uMoon2Color;
uniform float uFlow;
uniform float uTurb;
uniform float uAurora;
uniform float uGlow;
uniform float uBreath;
uniform float uPulse;
uniform float uShake;
uniform float uIngest;
uniform float uStateMix;
uniform vec4 uMoon1;      // x, y (NDC), raio (NDC), frente(0..1)
uniform vec4 uMoon2;
uniform vec4 uComet;      // x, y, direção(rad), alpha

out vec4 fragColor;

// ── Value noise 3D + FBM ──
float hash(vec3 p) {
  p = fract(p * 0.3183099 + 0.1);
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(hash(i + vec3(0, 0, 0)), hash(i + vec3(1, 0, 0)), f.x),
        mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
    mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
        mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y),
    f.z);
}

float fbm(vec3 p) {
  float v = 0.0;
  float amp = 0.55;
  for (int i = 0; i < 4; i++) {
    v += amp * noise(p);
    p = p * 2.03 + vec3(11.7, 5.3, 7.1);
    amp *= 0.5;
  }
  return v;
}

// Disco luminoso de uma lua (aditivo), atenuado quando "atrás" da esfera.
vec3 moonLight(vec2 p, vec4 moon, vec3 color, float sphereMask, float aa) {
  float md = length(p - moon.xy);
  float disc = smoothstep(moon.z + aa, moon.z * 0.35, md);
  float halo = exp(-md * 26.0) * 0.7;
  // Atrás da esfera: some onde a esfera cobre; na frente: brilho pleno.
  float occlusion = mix(1.0 - sphereMask * 0.92, 1.0, moon.w);
  return color * (disc + halo) * occlusion;
}

void main() {
  vec2 p = (gl_FragCoord.xy * 2.0 - uRes) / uRes.y;
  float t = uTime;

  // Tremor (error): desloca o espaço, não o DOM
  p += uShake * 0.028 * vec2(sin(t * 43.0), cos(t * 37.0));

  float d = length(p);
  float R = 0.56 * (1.0 + 0.028 * uBreath * sin(t * 1.35));

  // Suavização proporcional ao pixel (anti-aliasing das bordas em qualquer tamanho)
  float aa = 2.4 / uRes.y;

  vec3 col = vec3(0.0);
  float alpha = 0.0;

  float sphereMask = smoothstep(R + aa, R - aa, d);

  // ── Interior da esfera ──
  if (d < R + aa) {
    float nz = sqrt(max(R * R - d * d, 0.0)) / R; // profundidade fake [0..1]
    vec3 n = vec3(p / R, nz);                      // normal da esfera

    // Aurora FBM com domain warp — o fluido interno
    vec3 q = vec3(p * 2.6, t * uFlow);
    float warp = fbm(q + vec3(3.7, 9.2, 1.4));
    float v1 = fbm(q + uTurb * vec3(warp, warp * 0.7, 0.0));
    float v2 = fbm(q.yxz * 1.35 + vec3(warp * uTurb * 0.8, 0.0, 2.7));

    // Faixas estreitas = contraste visível mesmo em 28px
    vec3 aurora = mix(uC1, uC2, smoothstep(0.38, 0.62, v1));
    aurora = mix(aurora, uC3, smoothstep(0.42, 0.72, v2));
    vec3 base = mix(uC1, aurora, uAurora);

    // Iluminação direcional (o "3D" real): luz do alto-esquerda + especular
    vec3 L = normalize(vec3(-0.38, 0.5, 0.78));
    float diffuse = 0.5 + 0.5 * max(dot(n, L), 0.0);
    vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
    float spec = pow(max(dot(n, H), 0.0), 52.0) * 0.55;

    col = base * (0.45 + 0.75 * diffuse);

    // Highlight quente interno + especular frio (vidro)
    col += uC2 * pow(nz, 3.0) * 0.3;
    col += vec3(1.0, 0.96, 0.92) * spec;

    // Fresnel com dispersão cromática (expoentes distintos por canal),
    // tingido na marca — sem branco puro na borda
    float f = 1.0 - nz;
    vec3 rim = vec3(pow(f, 2.2), pow(f, 2.7), pow(f, 3.3));
    col += rim * mix(uC2, uC3, 0.4) * 0.8;

    // Cor de estado (success/error) preservando a textura
    col = mix(col, uStateColor * (0.55 + 0.6 * nz), uStateMix);

    // Pulso (thinking)
    col *= 1.0 + uPulse * 0.18 * sin(t * 6.2);

    alpha = sphereMask;
  }

  // ── Glow externo analítico ──
  if (d >= R - 0.02) {
    float g = exp(-(d - R) * 7.5) * 0.55 * uGlow;
    vec3 glowColor = mix(mix(uC1, uC2, 0.4), uStateColor, uStateMix);
    col += glowColor * g * (1.0 + uPulse * 0.3 * sin(t * 6.2));
    alpha = max(alpha, g);
  }

  // ── Espiral de ingestão: faixas convergindo para o núcleo ──
  if (uIngest > 0.01) {
    float ang = atan(p.y, p.x);
    float spiral = fract(ang * 0.477 - d * 2.2 + t * 0.9); // 3 braços
    float streak = smoothstep(0.12, 0.0, abs(spiral - 0.5) - 0.02);
    float fade = smoothstep(1.05, R * 0.4, d) * smoothstep(R * 0.25, R * 0.8, d);
    col += uC2 * streak * fade * 0.55 * uIngest;
    alpha = max(alpha, streak * fade * 0.5 * uIngest);
  }

  // ── Luas keplerianas ──
  vec3 m1 = moonLight(p, uMoon1, uMoon1Color, sphereMask, aa);
  vec3 m2 = moonLight(p, uMoon2, uMoon2Color, sphereMask, aa);
  col += m1 + m2;
  alpha = max(alpha, min(max(max(m1.r, m1.g), m1.b) + max(max(m2.r, m2.g), m2.b), 1.0));

  // ── Cometa: risco luminoso com cauda ──
  if (uComet.w > 0.01) {
    vec2 cp = p - uComet.xy;
    vec2 dir = vec2(cos(uComet.z), sin(uComet.z));
    float along = dot(cp, dir);
    float across = abs(dot(cp, vec2(-dir.y, dir.x)));
    float tail = smoothstep(0.0, -0.45, along) * 0.0
      + smoothstep(0.02, 0.0, across) * smoothstep(-0.4, 0.0, along) * step(along, 0.02);
    float head = exp(-length(cp) * 60.0);
    float comet = (tail * 0.5 + head) * uComet.w;
    col += mix(uC2, vec3(1.0), 0.4) * comet;
    alpha = max(alpha, comet);
  }

  fragColor = vec4(col, clamp(alpha, 0.0, 1.0));
}
`;
