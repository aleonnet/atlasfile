import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MOON_ORBITS, orbitalPosition, solveKepler } from "./kepler";
import { lerpUniforms, ORB_STATE_TARGETS } from "./orbStates";
import { _resetWebGL2Probe, Orb } from "./index";

describe("kepler", () => {
  it("solveKepler converge para a equação de Kepler", () => {
    const M = 1.3;
    const e = 0.3;
    const E = solveKepler(M, e);
    expect(E - e * Math.sin(E)).toBeCloseTo(M, 6);
  });

  it("órbita respeita periapsis/apoapsis (a(1±e))", () => {
    const p = MOON_ORBITS.moon2;
    let min = Infinity;
    let max = 0;
    for (let t = 0; t < p.period; t += p.period / 200) {
      const { r } = orbitalPosition(t, p);
      min = Math.min(min, r);
      max = Math.max(max, r);
    }
    expect(min).toBeGreaterThanOrEqual(p.a * (1 - p.e) - 0.01);
    expect(max).toBeLessThanOrEqual(p.a * (1 + p.e) + 0.01);
  });

  it("período fecha a órbita (posição em t=0 ≈ t=period)", () => {
    const p = MOON_ORBITS.moon1;
    const a = orbitalPosition(0, p);
    const b = orbitalPosition(p.period, p);
    expect(a.x).toBeCloseTo(b.x, 3);
    expect(a.y).toBeCloseTo(b.y, 3);
  });
});

describe("orbStates", () => {
  it("todos os estados têm alvos completos e finitos", () => {
    for (const targets of Object.values(ORB_STATE_TARGETS)) {
      for (const v of Object.values(targets)) {
        expect(Number.isFinite(v)).toBe(true);
      }
    }
  });

  it("thinking acelera fluxo e luas em relação a idle", () => {
    expect(ORB_STATE_TARGETS.thinking.flowSpeed).toBeGreaterThan(ORB_STATE_TARGETS.idle.flowSpeed);
    expect(ORB_STATE_TARGETS.thinking.moonSpeed).toBeGreaterThan(ORB_STATE_TARGETS.idle.moonSpeed);
  });

  it("error é o único com shake; ingesting o único com espiral", () => {
    const entries = Object.entries(ORB_STATE_TARGETS);
    expect(entries.filter(([, t]) => t.shake > 0).map(([k]) => k)).toEqual(["error"]);
    expect(entries.filter(([, t]) => t.ingest > 0).map(([k]) => k)).toEqual(["ingesting"]);
  });

  it("lerpUniforms converge para o alvo sem overshoot", () => {
    let cur = { ...ORB_STATE_TARGETS.idle };
    const target = ORB_STATE_TARGETS.thinking;
    for (let i = 0; i < 200; i++) cur = lerpUniforms(cur, target, 0.07);
    expect(cur.flowSpeed).toBeCloseTo(target.flowSpeed, 3);
    expect(cur.moonSpeed).toBeCloseTo(target.moonSpeed, 3);
  });
});

describe("Orb fallback", () => {
  it("sem WebGL2 (jsdom) renderiza o CompanionOrb SVG", () => {
    _resetWebGL2Probe();
    const { container } = render(<Orb state="idle" size={40} />);
    expect(container.querySelector(".companion-orb-svg")).toBeInTheDocument();
    expect(container.querySelector("canvas")).not.toBeInTheDocument();
  });

  it("ingesting degrada para thinking no SVG (aurora visível)", () => {
    _resetWebGL2Probe();
    const { container } = render(<Orb state="ingesting" size={40} />);
    expect(container.querySelector(".companion-orb-wrap.thinking")).toBeInTheDocument();
  });
});
