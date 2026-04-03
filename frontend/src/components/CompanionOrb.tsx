import React, { useCallback, useEffect, useId, useRef } from "react";
import "./CompanionOrb.css";

export type CompanionState = "idle" | "thinking" | "success" | "error" | "alive";

interface CompanionOrbProps {
  state: CompanionState;
  size?: number;
  onClick?: () => void;
}

const AURORA_ELLIPSES = [
  { rx: 24, ry: 16, colorVar: "var(--orb-aurora-1)", rotDur: "8s",  pDur: "3s",   pAttr: "rx", pVals: "21;28;21", angle: 0   },
  { rx: 18, ry: 25, colorVar: "var(--orb-aurora-2)", rotDur: "11s", pDur: "4.5s", pAttr: "ry", pVals: "22;29;22", angle: 60  },
  { rx: 22, ry: 15, colorVar: "var(--orb-aurora-3)", rotDur: "14s", pDur: "5.5s", pAttr: "rx", pVals: "19;26;19", angle: 120 },
] as const;

// ── Keplerian orbital mechanics ──

interface OrbitalParams {
  a: number;        // semi-major axis (avg distance from focus)
  e: number;        // eccentricity (0=circle, 0.5=very elliptical)
  period: number;   // orbital period in ms
  tilt: number;     // orbital plane tilt in radians
  phase: number;    // initial phase offset (radians)
  baseR: number;    // base visual radius of the moon
}

const CX = 20, CY = 20;

/** Solve Kepler's equation M = E - e*sin(E) via Newton-Raphson (5 iterations). */
function solveKepler(M: number, e: number): number {
  let E = M;
  for (let i = 0; i < 5; i++) {
    E = E - (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
  }
  return E;
}

/** Compute true anomaly from eccentric anomaly. */
function trueAnomaly(E: number, e: number): number {
  return 2 * Math.atan2(
    Math.sqrt(1 + e) * Math.sin(E / 2),
    Math.sqrt(1 - e) * Math.cos(E / 2)
  );
}

/** Compute position & distance for a Keplerian orbit at time t (ms). */
function orbitalPosition(t: number, p: OrbitalParams) {
  const M = ((t / p.period) * 2 * Math.PI + p.phase) % (2 * Math.PI);
  const E = solveKepler(M, p.e);
  const theta = trueAnomaly(E, p.e);
  const r = p.a * (1 - p.e * Math.cos(E));
  const x = CX + r * Math.cos(theta + p.tilt);
  const y = CY + r * Math.sin(theta + p.tilt);
  return { x, y, r, theta };
}

// Moon 1: inner orbit, moderate eccentricity
// Moon 2: outer orbit, higher eccentricity → more dramatic speed variation
const ORBIT_PARAMS: Record<string, { idle: OrbitalParams; alive: OrbitalParams; thinking: OrbitalParams }> = {
  moon1: {
    idle:     { a: 13, e: 0.18, period: 8000,  tilt: 0.3,  phase: 0,    baseR: 2.5 },
    alive:    { a: 13, e: 0.18, period: 5000,  tilt: 0.3,  phase: 0,    baseR: 2.5 },
    thinking: { a: 13, e: 0.18, period: 2000,  tilt: 0.3,  phase: 0,    baseR: 2.5 },
  },
  moon2: {
    idle:     { a: 18, e: 0.30, period: 12000, tilt: 2.4,  phase: Math.PI, baseR: 1.8 },
    alive:    { a: 18, e: 0.30, period: 8000,  tilt: 2.4,  phase: Math.PI, baseR: 1.8 },
    thinking: { a: 18, e: 0.30, period: 2600,  tilt: 2.4,  phase: Math.PI, baseR: 1.8 },
  },
};

function randomCometTrajectory() {
  const angleDeg = 25 + Math.random() * 130;
  const angle = angleDeg * Math.PI / 180;
  const r = 32;
  const x1 = CX + r * Math.cos(angle + Math.PI);
  const y1 = CY + r * Math.sin(angle + Math.PI);
  const x2 = CX + r * Math.cos(angle);
  const y2 = CY + r * Math.sin(angle);
  const dir = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;
  return { x1, y1, x2, y2, dir };
}

export function CompanionOrb({ state, size = 40, onClick }: CompanionOrbProps) {
  const uid = useId().replace(/:/g, "");
  const gradId = `orb-grad-${uid}`;
  const glowFilterId = `orb-glow-${uid}`;
  const auroraFilterId = `orb-aurora-${uid}`;

  const isNegative = state === "error";
  const isPositive = state === "success";
  const showAurora = state === "thinking" || state === "alive";
  const auroraOpacity = state === "alive" ? 0.5 : 0.7;

  const coreColor = isPositive
    ? "var(--ok, #22c55e)"
    : isNegative
      ? "var(--danger, #ff6b7f)"
      : "var(--accent, #ff5a36)";

  const coreColorLight = isPositive
    ? "var(--ok, #22c55e)"
    : isNegative
      ? "var(--danger, #ff6b7f)"
      : "var(--accent-light, #ff8a6b)";

  // ── Refs for imperative animation ──
  const moon1Ref = useRef<SVGCircleElement>(null);
  const moon2Ref = useRef<SVGCircleElement>(null);
  const coreRef = useRef<SVGCircleElement>(null);
  const cometRef = useRef<SVGGElement>(null);
  const orbitRafRef = useRef<number>();
  const cometRafRef = useRef<number>();

  // ── Keplerian orbit loop ──
  useEffect(() => {
    const orbiting = state === "idle" || state === "alive" || state === "thinking";
    if (!orbiting) {
      if (orbitRafRef.current) cancelAnimationFrame(orbitRafRef.current);
      return;
    }

    const modeKey = state as "idle" | "alive" | "thinking";
    const p1 = ORBIT_PARAMS.moon1[modeKey];
    const p2 = ORBIT_PARAMS.moon2[modeKey];
    const startTime = performance.now();

    const frame = (now: number) => {
      const t = now - startTime;
      const m1 = moon1Ref.current;
      const m2 = moon2Ref.current;
      const core = coreRef.current;
      if (!m1 || !m2) { orbitRafRef.current = requestAnimationFrame(frame); return; }

      // Compute Keplerian positions
      const pos1 = orbitalPosition(t, p1);
      const pos2 = orbitalPosition(t, p2);

      // Distance between moons
      const dx = pos1.x - pos2.x;
      const dy = pos1.y - pos2.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      // Proximity factor: 0 when far, peaks at 1 when moons touch
      // Interaction radius ≈ 10 SVG units
      const proximity = Math.max(0, 1 - dist / 12);

      // Apply positions
      m1.setAttribute("cx", pos1.x.toFixed(1));
      m1.setAttribute("cy", pos1.y.toFixed(1));
      m2.setAttribute("cx", pos2.x.toFixed(1));
      m2.setAttribute("cy", pos2.y.toFixed(1));

      // Proximity glow: moons brighten and grow when close
      const r1 = p1.baseR + proximity * 0.8;
      const r2 = p2.baseR + proximity * 0.6;
      m1.setAttribute("r", r1.toFixed(2));
      m2.setAttribute("r", r2.toFixed(2));
      m1.setAttribute("opacity", (0.85 + proximity * 0.15).toFixed(2));
      m2.setAttribute("opacity", (0.70 + proximity * 0.30).toFixed(2));

      // Tidal effect on core: subtle scale when moon 1 is at periapsis
      if (core) {
        const periapsisProximity1 = 1 - pos1.r / (p1.a * (1 + p1.e));
        const periapsisProximity2 = 1 - pos2.r / (p2.a * (1 + p2.e));
        const tidalScale = 1 + Math.max(periapsisProximity1 * 0.03, periapsisProximity2 * 0.02) + proximity * 0.02;
        core.setAttribute("r", (10 * tidalScale).toFixed(2));
      }

      orbitRafRef.current = requestAnimationFrame(frame);
    };

    orbitRafRef.current = requestAnimationFrame(frame);
    return () => { if (orbitRafRef.current) cancelAnimationFrame(orbitRafRef.current); };
  }, [state]);

  // ── Comet animation ──
  const fireComet = useCallback(() => {
    if (!cometRef.current) return;

    const { x1, y1, x2, y2, dir } = randomCometTrajectory();
    const duration = 900;
    const startTime = performance.now();
    const g = cometRef.current;

    const frame = (now: number) => {
      const t = Math.min((now - startTime) / duration, 1);
      const x = x1 + (x2 - x1) * t;
      const y = y1 + (y2 - y1) * t;

      let opacity: number;
      if (t < 0.08) opacity = t / 0.08;
      else if (t < 0.6) opacity = 1;
      else opacity = Math.max(0, 1 - (t - 0.6) / 0.4);

      g.setAttribute("transform", `translate(${x.toFixed(1)},${y.toFixed(1)}) rotate(${dir.toFixed(1)})`);
      g.setAttribute("opacity", opacity.toFixed(2));

      if (t < 1) {
        cometRafRef.current = requestAnimationFrame(frame);
      } else {
        g.setAttribute("opacity", "0");
      }
    };

    if (cometRafRef.current) cancelAnimationFrame(cometRafRef.current);
    cometRafRef.current = requestAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (state !== "alive") return;

    let timerId: ReturnType<typeof setTimeout>;
    function scheduleNext() {
      const delay = 5000 + Math.random() * 10000;
      timerId = setTimeout(() => { fireComet(); scheduleNext(); }, delay);
    }
    timerId = setTimeout(() => { fireComet(); scheduleNext(); }, 2000 + Math.random() * 2000);
    return () => { clearTimeout(timerId); if (cometRafRef.current) cancelAnimationFrame(cometRafRef.current); };
  }, [state, fireComet]);

  const handleClick = useCallback(() => {
    fireComet();
    onClick?.();
  }, [fireComet, onClick]);

  return (
    <div
      className={`companion-orb-wrap ${state}`}
      style={{ width: size, height: size, cursor: state === "alive" ? "pointer" : undefined }}
      aria-hidden="true"
      onClick={state === "alive" ? handleClick : onClick}
    >
      <svg
        className="companion-orb-svg"
        width={size}
        height={size}
        viewBox="0 0 40 40"
      >
        <defs>
          <radialGradient id={gradId} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={coreColorLight} />
            <stop offset="100%" stopColor={coreColor} />
          </radialGradient>
          <filter id={glowFilterId}>
            <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" />
          </filter>
          <filter id={auroraFilterId}>
            <feGaussianBlur in="SourceGraphic" stdDeviation="6" />
          </filter>
          <linearGradient id={`tail-${uid}`} gradientUnits="userSpaceOnUse" x1="-12" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--orb-comet-tail-start)" />
            <stop offset="50%" stopColor="var(--orb-comet-tail-mid)" />
            <stop offset="85%" stopColor="var(--orb-comet-tail-end)" />
            <stop offset="100%" stopColor="var(--orb-comet-head)" />
          </linearGradient>
        </defs>

        {/* Aurora */}
        {showAurora && (
          <g filter={`url(#${auroraFilterId})`} opacity={auroraOpacity}>
            {AURORA_ELLIPSES.map((e, i) => (
              <ellipse
                key={i}
                className="orb-aurora-ellipse"
                cx="20" cy="20" rx={e.rx} ry={e.ry}
                fill={e.colorVar}
              >
                <animateTransform
                  attributeName="transform" type="rotate"
                  from={`${e.angle} 20 20`} to={`${e.angle + 360} 20 20`}
                  dur={e.rotDur} repeatCount="indefinite"
                />
                <animate attributeName={e.pAttr} values={e.pVals} dur={e.pDur} repeatCount="indefinite" />
              </ellipse>
            ))}
          </g>
        )}

        {/* Glow layer */}
        <circle cx="20" cy="20" r="11" fill={`url(#${gradId})`} filter={`url(#${glowFilterId})`} opacity="var(--orb-glow-opacity)" />

        {/* Core */}
        <circle ref={coreRef} className="orb-core" cx="20" cy="20" r="10" fill={`url(#${gradId})`} />

        {/* Moon 1 — inner Keplerian orbit */}
        <circle
          ref={moon1Ref}
          className="orb-moon orb-moon-1"
          cx="32" cy="15" r="2.5"
          fill="var(--orb-moon-1-fill)"
          opacity="var(--orb-moon-1-opacity)"
          style={{ "--burst-x": "6px", "--burst-y": "-6px" } as React.CSSProperties}
        />
        {/* Moon 2 — outer Keplerian orbit */}
        <circle
          ref={moon2Ref}
          className="orb-moon orb-moon-2"
          cx="3" cy="27" r="1.8"
          fill="var(--orb-moon-2-fill)"
          opacity="var(--orb-moon-2-opacity)"
          style={{ "--burst-x": "-5px", "--burst-y": "5px" } as React.CSSProperties}
        />

        {/* Comet */}
        <g ref={cometRef} opacity="0">
          <polygon points="-12,-0.2 -12,0.2 0,1.2 0,-1.2" fill={`url(#tail-${uid})`} />
          <circle cx="0.5" cy="0" r="1.5" fill="var(--orb-comet-head)" />
        </g>
      </svg>
    </div>
  );
}
