/**
 * Port WebGL2 do blackhole.glsl (ghostty-blackhole, MIT © s13k —
 * s13k.dev/blackhole), por sua vez modelado no shader de Bruneton. A física é
 * a mesma do original: cada pixel próximo do buraco integra sua geodésica nula
 * na métrica de Schwarzschild (aceleração de Binet a = -3/2 h² x/r⁵), disco de
 * acreção fino com perfil de temperatura Shakura–Sunyaev, Doppler/beaming
 * relativístico e dilatação temporal. O que saiu no port: modos
 * token/pomodoro/demo, decode de cursor OSC e o sampling do texto do terminal
 * (iChannel0) — na UI o "céu" é o starfield procedural e a saída é
 * premultiplicada (luz soma sobre a página; a sombra oclui de verdade).
 */

export const BH_VERT = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

export const BH_FRAG = `#version 300 es
precision highp float;
out vec4 outColor;

uniform vec2  uRes;
uniform float uTime;
uniform float uIntensity; // 0..1 — massa/tamanho/atividade do buraco
uniform float uVariant;   // 0 = backdrop (deriva Lissajous), 1 = orb (centrado)
uniform float uStarGain;  // brilho do starfield lenteado

// ------------------------------------------------------------- tunables ----
const float DILATION_MIN = 0.2;
#define N_STEPS 40
#define B_CRIT 2.5980762

// O look completo do disco num pacote (estrutura do shader original) — o tour
// do backdrop faz crossfade entre presets do tuner; o orb fica no Inferno
// (o Quasar tem rout 14 e estouraria um canvas de 40px).
struct DiskLook {
  float temp, incl, roll, inner, outer, opac, dopp, beam, gain, contr, wind, speed, expo;
};
//                                        temp     incl  roll  inner outer opac  dopp  beam gain contr wind speed expo
const DiskLook LOOK_INFERNO   = DiskLook( 5500.0,  1.50, 0.35, 1.8,  8.0,  0.90, 0.60, 2.5, 2.2, 1.6,  7.0, 5.0,  1.40);
const DiskLook LOOK_GARGANTUA = DiskLook( 4500.0,  1.52, 0.10, 2.2,  7.0,  0.85, 0.35, 2.0, 1.4, 0.5,  7.0, 5.0,  1.20);
const DiskLook LOOK_QUASAR    = DiskLook(15000.0,  1.30, 0.35, 3.0, 14.0,  0.35, 1.00, 4.0, 1.2, 1.3,  8.0, 5.0,  0.80);

// Tour contemplativo: Inferno → Gargantua → Quasar, TOUR_SLOT_SEC por look
// com crossfade suave — ajuste fino num número só.
const float TOUR_SLOT_SEC = 14.0;
const float TOUR_XFADE    = 2.5 / TOUR_SLOT_SEC;

DiskLook mixLook(DiskLook a, DiskLook b, float f) {
  return DiskLook(
    mix(a.temp, b.temp, f), mix(a.incl, b.incl, f), mix(a.roll, b.roll, f),
    mix(a.inner, b.inner, f), mix(a.outer, b.outer, f), mix(a.opac, b.opac, f),
    mix(a.dopp, b.dopp, f), mix(a.beam, b.beam, f), mix(a.gain, b.gain, f),
    mix(a.contr, b.contr, f), mix(a.wind, b.wind, f), mix(a.speed, b.speed, f),
    mix(a.expo, b.expo, f));
}

DiskLook tourLook(float t) {
  DiskLook looks[3] = DiskLook[3](LOOK_INFERNO, LOOK_GARGANTUA, LOOK_QUASAR);
  float u = mod(t, TOUR_SLOT_SEC * 3.0) / TOUR_SLOT_SEC;   // 0..3, relógio de slots
  int i = int(min(u, 2.999));
  float f = smoothstep(1.0 - TOUR_XFADE, 1.0, fract(u));   // crossfade no fim do slot
  return mixLook(looks[i], looks[(i + 1) % 3], f);
}

// --------------------------------------------------------------- helpers ---
float hash21(vec2 p) {
  p = fract(p * vec2(234.34, 435.345));
  p += dot(p, p + 34.23);
  return fract(p.x * p.y);
}

float vnoiseWrapY(vec2 p, float perY) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float y0 = mod(i.y, perY), y1 = mod(i.y + 1.0, perY);
  return mix(mix(hash21(vec2(i.x, y0)), hash21(vec2(i.x + 1.0, y0)), f.x),
             mix(hash21(vec2(i.x, y1)), hash21(vec2(i.x + 1.0, y1)), f.x),
             f.y);
}

vec2 rot(vec2 v, float a) {
  float c = cos(a), s = sin(a);
  return vec2(c * v.x - s * v.y, s * v.x + c * v.y);
}

vec2 lissa(float t) {
  return vec2(0.75 * sin(t * 0.37) + 0.25 * sin(t * 0.83 + 1.0),
              0.70 * sin(t * 0.54 + 2.1) + 0.30 * sin(t * 1.07));
}

vec3 blackbody(float T) {
  float t = clamp(T, 1500.0, 40000.0) / 100.0;
  float r = t <= 66.0 ? 1.0 : clamp(1.292936 * pow(t - 60.0, -0.1332047), 0.0, 1.0);
  float g = t <= 66.0 ? clamp(0.3900816 * log(t) - 0.6318414, 0.0, 1.0)
                      : clamp(1.1298909 * pow(t - 60.0, -0.0755148), 0.0, 1.0);
  float b = t >= 66.0 ? 1.0
                      : (t <= 19.0 ? 0.0 : clamp(0.5432068 * log(t - 10.0) - 1.1962540, 0.0, 1.0));
  return vec3(r, g, b);
}

// Mais denso e brilhante que o original (0.92/0.10/1x): no Ghostty as
// estrelas eram um detalhe sobre o texto; aqui elas SÃO o céu.
vec3 stars(vec3 d) {
  vec2 sph = vec2(atan(d.x, -d.z), asin(clamp(d.y, -1.0, 1.0)));
  vec2 g = sph * 40.0;
  vec2 id = floor(g);
  float h = hash21(id);
  if (h < 0.86) return vec3(0.0);
  vec2 f = fract(g) - 0.5;
  vec2 off = (vec2(hash21(id + 17.3), hash21(id + 31.7)) - 0.5) * 0.7;
  float spark = smoothstep(0.16, 0.0, length(f - off));
  float tw = 0.75 + 0.25 * sin(uTime * (0.5 + 2.0 * hash21(id + 5.1)) + 40.0 * h);
  vec3 tint = mix(vec3(1.0, 0.85, 0.65), vec3(0.78, 0.87, 1.0), hash21(id + 2.9));
  return tint * spark * tw * (0.35 + 1.3 * (h - 0.86) / 0.14);
}

// ------------------------------------------------------------------ main ---
void main() {
  vec2 res = uRes;
  vec2 uv = gl_FragCoord.xy / res;    // WebGL: y-up nativo (sem o flip do Ghostty)
  float aspect = res.x / res.y;
  float t = uTime;

  float I = mix(0.10, 1.0, clamp(uIntensity, 0.0, 1.0));
  float vis = smoothstep(0.0, 0.10, I);
  if (vis <= 0.0) { outColor = vec4(0.0); return; }

  float rh;                            // raio da sombra em unidades de altura
  vec2 center;
  if (uVariant > 0.5) {
    // orb: centrado, tamanho estável, respiração sutil
    rh = 0.15 + 0.02 * I + 0.006 * sin(t * 0.9);
    center = vec2(0.5) + 0.015 * vec2(sin(t * 0.31), cos(t * 0.23));
  } else {
    // backdrop: deriva lenta pela metade superior, tamanho segue I
    rh = mix(0.055, 0.085, I);
    vec2 wander = lissa(t * 0.12);
    center = vec2(0.5 + wander.x * 0.30, 0.62 + wander.y * 0.16);
  }

  // Look ativo: backdrop faz o tour com crossfade; orb fica no Inferno.
  DiskLook L;
  if (uVariant > 0.5) L = LOOK_INFERNO;
  else L = tourLook(t);

  float rin = max(L.inner, 1.6);
  float rout = max(L.outer, rin + 0.5);
  float dil = mix(1.0, DILATION_MIN, I);
  float shield = vis;

  vec2 p = (uv - center) * vec2(aspect, 1.0);
  float plen = length(p);

  // Sem o flip de y do original: o gl_FragCoord do WebGL já é y-up (no
  // Ghostty o -p.y convertia o uv top-down) — mantê-lo espelhava o disco.
  float W = B_CRIT / max(rh, 1e-4);
  vec2 pr = rot(p, L.roll) * W;
  float b = length(pr);

  float window = exp(-pow(plen / (7.0 * rh), 2.0));
  float bmax = rout + 3.0;
  float Z0 = max(14.0, rout + 5.0);

  // Céu FIXO NA TELA (não no buraco): as estrelas ficam paradas e é a lente
  // que passa por cima distorcendo — papel do texto do terminal no original.
  // Só o desvio gravitacional é relativo ao buraco.
  vec2 skyBase = (uv - 0.5) * vec2(aspect, 1.0) * 1.6;
  float starVis = mix(0.70, 1.0, window) * shield;

  // far field: deflexão fraca analítica sobre o céu fixo.
  // Alfa = luminância: premultiplicado com rgb > alfa é INVÁLIDO por spec e o
  // compositor Metal do Chrome clampa para preto (o headless/software deixava
  // passar — foi assim que este bug se escondeu dos screenshots).
  if (b >= bmax) {
    vec3 d = normalize(vec3(skyBase - (pr / b) * (2.0 / b), -1.0));
    vec3 st = stars(d) * uStarGain * starVis;
    outColor = vec4(st, clamp(max(st.r, max(st.g, st.b)), 0.0, 1.0));
    return;
  }

  // near field: geodésica integrada (leapfrog kick-drift-kick)
  vec3 x = vec3(pr, Z0);
  vec3 v = vec3(0.0, 0.0, -1.0);
  float h2 = dot(pr, pr);

  float ci = cos(L.incl), si = sin(L.incl);
  vec3 n = vec3(0.0, si, ci);
  vec3 e2 = vec3(0.0, ci, -si);

  vec3 emitc = vec3(0.0);
  float trans = 1.0;
  bool captured = false;
  float sPrev = dot(x, n);
  vec3 xPrev = x;

  for (int i = 0; i < N_STEPS; i++) {
    float r2 = dot(x, x);
    if (r2 < 1.0) { captured = true; break; }
    if (x.z < -Z0 && v.z < 0.0) break;
    if (r2 > 4.0 * Z0 * Z0) break;
    float r = sqrt(r2);
    float dt = clamp(0.16 * r, 0.03, 1.5);
    vec3 a = -1.5 * h2 * x / (r2 * r2 * r);
    v += a * (0.5 * dt);
    x += v * dt;
    r2 = dot(x, x);
    r = sqrt(r2);
    a = -1.5 * h2 * x / (r2 * r2 * r);
    v += a * (0.5 * dt);

    float s = dot(x, n);
    if (s * sPrev < 0.0 && trans > 0.02) {
      float tc = sPrev / (sPrev - s);
      vec3 xc = mix(xPrev, x, tc);
      float rc = length(xc);
      if (rc > rin && rc < rout) {
        float band = smoothstep(rin, rin * 1.25, rc) * (1.0 - smoothstep(rout * 0.70, rout, rc));
        float phi = atan(dot(xc, e2), xc.x);
        float turns = phi / 6.2831853;
        float kep = pow(rin / rc, 1.5);
        float gloc = sqrt(max(1.0 - 1.5 / rc, 0.02));
        float swirl = rc * L.wind * 0.12 - t * kep * L.speed * gloc * dil;
        float streaks = vnoiseWrapY(vec2(rc * 2.8, turns * 19.0 + swirl * 3.0), 19.0) * 0.65 +
                        vnoiseWrapY(vec2(rc * 1.0, turns * 9.0 + swirl * 1.5 + 7.0), 9.0) * 0.35;
        streaks = 0.35 + L.contr * streaks * streaks;

        vec3 gasdir = normalize(cross(n, xc));
        float beta = clamp(inversesqrt(max(2.0 * (rc - 1.0), 0.2)), 0.0, 0.99);
        float g = gloc / max(1.0 + beta * dot(gasdir, normalize(v)), 0.05);
        g = mix(1.0, g, L.dopp);

        float xpr = max(1.0 - sqrt(rin / rc), 0.0);
        float tprof = pow(rin / rc, 0.75) * pow(xpr, 0.25) / 0.488;
        vec3 cbb = blackbody(L.temp * tprof * g);
        float boost = pow(g, L.beam);

        float density = band * streaks;
        emitc += trans * cbb * (L.gain * 2.2 * density * tprof * tprof * boost);
        trans *= 1.0 - clamp(L.opac * density, 0.0, 1.0);
      }
    }
    sPrev = s;
    xPrev = x;
  }
  if (!captured && dot(x, x) < 4.0) captured = true;

  vec3 bg = vec3(0.0);
  if (!captured) {
    // Projeção do raio dobrado sobre o céu fixo: perto do anel de fótons
    // nv.z → 0 e a deflexão explode — estrelas esticam em arcos (Einstein).
    vec3 nv = normalize(v);
    vec2 defl = nv.xy / max(-nv.z, 0.06);
    bg = stars(normalize(vec3(skyBase + defl, -1.0))) * uStarGain * starVis;
  }

  // Saída premultiplicada VÁLIDA (alfa >= max componente da luz): a luz do
  // disco/estrelas quase-soma sobre a página; sombra e disco opaco ocluem.
  // blend: ONE, 1-SRC_ALPHA.
  vec3 light = (bg * trans + (vec3(1.0) - exp(-emitc * L.expo))) * vis;
  float occ = clamp((captured ? 0.94 : 0.0) + (1.0 - trans) * 0.85, 0.0, 1.0) * vis * window;
  float alpha = clamp(max(occ, max(light.r, max(light.g, light.b))), 0.0, 1.0);
  outColor = vec4(light, alpha);
}
`;
