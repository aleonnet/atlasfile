import { useMemo, useState } from "react";
import { CompanionOrb, type CompanionState } from "../CompanionOrb";
import { OrbGL, type OrbGLState } from "./OrbGL";

let webgl2Support: boolean | null = null;

/** Detecção cacheada de WebGL2 (uma sonda por sessão). */
export function hasWebGL2(): boolean {
  if (webgl2Support !== null) return webgl2Support;
  try {
    const canvas = document.createElement("canvas");
    webgl2Support = !!canvas.getContext("webgl2");
  } catch {
    webgl2Support = false;
  }
  return webgl2Support;
}

/** Reset da sonda (apenas para testes). */
export function _resetWebGL2Probe(): void {
  webgl2Support = null;
}

interface OrbProps {
  state: OrbGLState;
  size?: number;
  onClick?: () => void;
}

/**
 * Orb da marca: WebGL (esfera viva com aurora FBM, fresnel, luas keplerianas)
 * com fallback integral para o CompanionOrb SVG quando não há WebGL2, quando
 * o usuário prefere motion reduzido, ou se o contexto GL cair em runtime.
 */
export function Orb({ state, size = 40, onClick }: OrbProps) {
  const [glFailed, setGlFailed] = useState(false);
  const reducedMotion = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  const useFallback = glFailed || reducedMotion || !hasWebGL2();

  if (useFallback) {
    // O SVG não conhece "ingesting" — degrada para thinking (movimento interno)
    const svgState: CompanionState = state === "ingesting" ? "thinking" : state;
    return <CompanionOrb state={svgState} size={size} onClick={onClick} />;
  }

  return <OrbGL state={state} size={size} onClick={onClick} onContextLost={() => setGlFailed(true)} />;
}

export type { OrbGLState };
