import type { CompanionState } from "../CompanionOrb";

/**
 * Estados do orb dirigem UNIFORMS — nunca trocam o shader. O renderer
 * interpola os valores correntes em direção ao alvo a cada frame (lerp),
 * então transições de estado são sempre fluidas.
 */
export interface OrbUniformTargets {
  /** Velocidade do fluxo FBM interno. */
  flowSpeed: number;
  /** Amplitude do domain warp (turbulência da aurora). */
  turbulence: number;
  /** Intensidade da aurora interna (0 apaga, 1 plena). */
  aurora: number;
  /** Intensidade do glow externo. */
  glow: number;
  /** Amplitude da respiração (escala do raio). */
  breath: number;
  /** Pulso rítmico de brilho (thinking). */
  pulse: number;
  /** Tremor de posição (error). */
  shake: number;
  /** Espiral de partículas convergindo (ingesting). */
  ingest: number;
  /** Mistura para a cor de estado (success verde / error vermelho). */
  stateMix: number;
  /** Multiplicador de velocidade das luas keplerianas. */
  moonSpeed: number;
}

export const ORB_STATE_TARGETS: Record<CompanionState | "ingesting", OrbUniformTargets> = {
  idle: {
    flowSpeed: 0.12, turbulence: 0.8, aurora: 0.55, glow: 0.5,
    breath: 1, pulse: 0, shake: 0, ingest: 0, stateMix: 0, moonSpeed: 1,
  },
  alive: {
    flowSpeed: 0.2, turbulence: 1.1, aurora: 0.8, glow: 0.7,
    breath: 1, pulse: 0, shake: 0, ingest: 0, stateMix: 0, moonSpeed: 1.6,
  },
  thinking: {
    flowSpeed: 0.55, turbulence: 1.8, aurora: 1, glow: 0.9,
    breath: 1.4, pulse: 1, shake: 0, ingest: 0, stateMix: 0, moonSpeed: 4,
  },
  ingesting: {
    flowSpeed: 0.3, turbulence: 1.2, aurora: 0.85, glow: 0.8,
    breath: 1.2, pulse: 0.3, shake: 0, ingest: 1, stateMix: 0, moonSpeed: 2,
  },
  success: {
    flowSpeed: 0.25, turbulence: 0.9, aurora: 0.7, glow: 1.2,
    breath: 1, pulse: 0.4, shake: 0, ingest: 0, stateMix: 0.85, moonSpeed: 1,
  },
  error: {
    flowSpeed: 0.35, turbulence: 2.2, aurora: 0.6, glow: 0.8,
    breath: 1, pulse: 0.6, shake: 1, ingest: 0, stateMix: 0.9, moonSpeed: 1,
  },
};

/** Interpola todos os campos em direção ao alvo (k por frame ~60fps). */
export function lerpUniforms(
  current: OrbUniformTargets,
  target: OrbUniformTargets,
  k: number
): OrbUniformTargets {
  const out = { ...current };
  (Object.keys(target) as (keyof OrbUniformTargets)[]).forEach((key) => {
    out[key] = current[key] + (target[key] - current[key]) * k;
  });
  return out;
}
