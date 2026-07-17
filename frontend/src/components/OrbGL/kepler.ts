/**
 * Mecânica orbital kepleriana das luas do orb — a assinatura matemática do
 * CompanionOrb SVG (Newton-Raphson sobre a equação de Kepler), extraída pura
 * para o renderer WebGL reutilizar. Coordenadas no espaço do viewBox 40x40
 * (CX/CY = 20), como no SVG original.
 */

export interface OrbitalParams {
  /** Semi-eixo maior (distância média ao foco). */
  a: number;
  /** Excentricidade (0 = círculo). */
  e: number;
  /** Período orbital em ms. */
  period: number;
  /** Inclinação do plano orbital (rad). */
  tilt: number;
  /** Fase inicial (rad). */
  phase: number;
  /** Raio visual base da lua. */
  baseR: number;
}

export const CX = 20;
export const CY = 20;

/** Resolve a equação de Kepler M = E - e·sin(E) via Newton-Raphson (5 iterações). */
export function solveKepler(M: number, e: number): number {
  let E = M;
  for (let i = 0; i < 5; i++) {
    E = E - (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
  }
  return E;
}

/** Anomalia verdadeira a partir da anomalia excêntrica. */
export function trueAnomaly(E: number, e: number): number {
  return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(1 - e) * Math.cos(E / 2));
}

/** Posição e distância ao foco de uma órbita kepleriana no tempo t (ms). */
export function orbitalPosition(t: number, p: OrbitalParams) {
  const M = ((t / p.period) * 2 * Math.PI + p.phase) % (2 * Math.PI);
  const E = solveKepler(M, p.e);
  const theta = trueAnomaly(E, p.e);
  const r = p.a * (1 - p.e * Math.cos(E));
  const x = CX + r * Math.cos(theta + p.tilt);
  const y = CY + r * Math.sin(theta + p.tilt);
  return { x, y, r, theta };
}

/** Órbitas base das duas luas (mesmos parâmetros do SVG; período é dividido
 * pelo multiplicador de velocidade do estado no renderer). */
export const MOON_ORBITS: { moon1: OrbitalParams; moon2: OrbitalParams } = {
  moon1: { a: 13, e: 0.18, period: 8000, tilt: 0.3, phase: 0, baseR: 2.5 },
  moon2: { a: 18, e: 0.3, period: 12000, tilt: 2.4, phase: Math.PI, baseR: 1.8 },
};
