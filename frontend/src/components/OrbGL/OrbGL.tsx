import { useEffect, useRef } from "react";
import type { CompanionState } from "../CompanionOrb";
import { MOON_ORBITS, orbitalPosition } from "./kepler";
import { lerpUniforms, ORB_STATE_TARGETS, type OrbUniformTargets } from "./orbStates";
import { ORB_FRAG, ORB_VERT } from "./orbShader";

export type OrbGLState = CompanionState | "ingesting";

interface OrbGLProps {
  state: OrbGLState;
  size?: number;
  onClick?: () => void;
  onContextLost?: () => void;
}

type Rgb = [number, number, number];

function cssColorToRgb(color: string): Rgb {
  // Normaliza qualquer cor CSS via canvas 2D (aceita #hex, rgb(), nomes)
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d");
  if (!ctx) return [1, 0.35, 0.21];
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return [r / 255, g / 255, b / 255];
}

function readBrandColors() {
  const styles = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
  return {
    c1: cssColorToRgb(token("--accent", "#ff5a36")),
    c2: cssColorToRgb(token("--accent-light", "#ff8a6b")),
    c3: cssColorToRgb(token("--accent-purple", "#c97bff")),
    ok: cssColorToRgb(token("--ok", "#22c55e")),
    danger: cssColorToRgb(token("--danger", "#ff6b7f")),
    moon1: cssColorToRgb(token("--orb-moon-1-fill", "#ff5a36")),
    moon2: cssColorToRgb(token("--orb-moon-2-fill", "#c97bff")),
  };
}

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    // eslint-disable-next-line no-console
    console.error("OrbGL shader:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

/** viewBox 40x40 do SVG → NDC do shader (y invertido, escala pelo raio 20). */
function svgToNdc(x: number, y: number): [number, number] {
  return [(x - 20) / 20, (20 - y) / 20];
}

/**
 * Renderer WebGL do orb: quad + fragment shader, uniforms interpolados por
 * frame, luas keplerianas calculadas na CPU. Pausa o loop quando a aba está
 * oculta ou o canvas fora do viewport (zero GPU idle).
 */
export function OrbGL({ state, size = 40, onClick, onContextLost }: OrbGLProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<OrbGLState>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl2", { alpha: true, antialias: true, premultipliedAlpha: false });
    if (!gl) {
      onContextLost?.();
      return;
    }

    const vs = compile(gl, gl.VERTEX_SHADER, ORB_VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, ORB_FRAG);
    if (!vs || !fs) {
      onContextLost?.();
      return;
    }
    const prog = gl.createProgram()!;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      onContextLost?.();
      return;
    }
    gl.useProgram(prog);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const u = (name: string) => gl.getUniformLocation(prog, name);
    const loc = {
      res: u("uRes"), time: u("uTime"),
      c1: u("uC1"), c2: u("uC2"), c3: u("uC3"),
      stateColor: u("uStateColor"), moon1Color: u("uMoon1Color"), moon2Color: u("uMoon2Color"),
      flow: u("uFlow"), turb: u("uTurb"), aurora: u("uAurora"), glow: u("uGlow"),
      breath: u("uBreath"), pulse: u("uPulse"), shake: u("uShake"), ingest: u("uIngest"),
      stateMix: u("uStateMix"), moon1: u("uMoon1"), moon2: u("uMoon2"), comet: u("uComet"),
    };

    let colors = readBrandColors();
    const themeObserver = new MutationObserver(() => {
      colors = readBrandColors();
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const px = Math.max(2, Math.round(size * dpr));
    canvas.width = px;
    canvas.height = px;
    gl.viewport(0, 0, px, px);

    // Uniforms correntes (lerp em direção ao alvo do estado)
    let current: OrbUniformTargets = { ...ORB_STATE_TARGETS.idle };
    // Velocidade orbital acumulada por integração (mudar período direto “teleporta” a lua)
    let moonPhase = 0;
    let lastNow = performance.now();
    const start = lastNow;

    // Cometa (alive + click)
    const comet = { x: 0, y: 0, dir: 0, alpha: 0, t0: 0, active: false };
    const fireComet = () => {
      const angleDeg = 25 + Math.random() * 130;
      const angle = (angleDeg * Math.PI) / 180;
      comet.dir = angle;
      comet.t0 = performance.now();
      comet.active = true;
    };
    let cometTimer: ReturnType<typeof setTimeout> | null = null;
    const scheduleComet = () => {
      cometTimer = setTimeout(() => {
        if (stateRef.current === "alive") fireComet();
        scheduleComet();
      }, 5000 + Math.random() * 9000);
    };
    scheduleComet();

    const clickHandler = () => {
      if (stateRef.current === "alive") fireComet();
    };
    canvas.addEventListener("click", clickHandler);

    // Pausa: aba oculta ou fora do viewport
    let visible = !document.hidden;
    let inViewport = true;
    let raf = 0;
    let running = false;

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(now - lastNow, 100);
      lastNow = now;
      const t = (now - start) / 1000;

      const targets = ORB_STATE_TARGETS[stateRef.current] ?? ORB_STATE_TARGETS.idle;
      current = lerpUniforms(current, targets, 0.07);

      // Fase orbital integrada (velocidade contínua nas transições)
      moonPhase += dt * current.moonSpeed;

      const p1 = orbitalPosition(moonPhase, MOON_ORBITS.moon1);
      const p2 = orbitalPosition(moonPhase, MOON_ORBITS.moon2);
      const [m1x, m1y] = svgToNdc(p1.x, p1.y);
      const [m2x, m2y] = svgToNdc(p2.x, p2.y);
      // Proximidade entre luas (efeito do SVG): brilham e crescem ao se cruzar
      const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
      const proximity = Math.max(0, 1 - dist / 12);
      const front1 = Math.sin(p1.theta + MOON_ORBITS.moon1.tilt) > 0 ? 1 : 0;
      const front2 = Math.sin(p2.theta + MOON_ORBITS.moon2.tilt) > 0 ? 1 : 0;

      // Cometa: 900ms, fade in/out
      let cometAlpha = 0;
      let cx = 0;
      let cy = 0;
      if (comet.active) {
        const ct = (now - comet.t0) / 900;
        if (ct >= 1) {
          comet.active = false;
        } else {
          const r = 1.6;
          cx = -r * Math.cos(comet.dir) + 2 * r * Math.cos(comet.dir) * ct;
          cy = -r * Math.sin(comet.dir) + 2 * r * Math.sin(comet.dir) * ct;
          cometAlpha = ct < 0.08 ? ct / 0.08 : ct < 0.6 ? 1 : Math.max(0, 1 - (ct - 0.6) / 0.4);
        }
      }

      const isSuccess = stateRef.current === "success";
      const stateColor = isSuccess ? colors.ok : colors.danger;

      gl.uniform2f(loc.res, px, px);
      gl.uniform1f(loc.time, t);
      gl.uniform3fv(loc.c1, colors.c1);
      gl.uniform3fv(loc.c2, colors.c2);
      gl.uniform3fv(loc.c3, colors.c3);
      gl.uniform3fv(loc.stateColor, stateColor);
      gl.uniform3fv(loc.moon1Color, colors.moon1);
      gl.uniform3fv(loc.moon2Color, colors.moon2);
      gl.uniform1f(loc.flow, current.flowSpeed);
      gl.uniform1f(loc.turb, current.turbulence);
      gl.uniform1f(loc.aurora, current.aurora);
      gl.uniform1f(loc.glow, current.glow);
      gl.uniform1f(loc.breath, current.breath);
      gl.uniform1f(loc.pulse, current.pulse);
      gl.uniform1f(loc.shake, current.shake);
      gl.uniform1f(loc.ingest, current.ingest);
      gl.uniform1f(loc.stateMix, current.stateMix);
      gl.uniform4f(loc.moon1, m1x, m1y, ((MOON_ORBITS.moon1.baseR + proximity * 0.8) / 20) * 1.0, front1);
      gl.uniform4f(loc.moon2, m2x, m2y, ((MOON_ORBITS.moon2.baseR + proximity * 0.6) / 20) * 1.0, front2);
      gl.uniform4f(loc.comet, cx, cy, comet.dir, cometAlpha);

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const syncLoop = () => {
      const shouldRun = visible && inViewport;
      if (shouldRun && !running) {
        running = true;
        lastNow = performance.now();
        raf = requestAnimationFrame(frame);
      } else if (!shouldRun && running) {
        running = false;
        cancelAnimationFrame(raf);
      }
    };

    const onVisibility = () => {
      visible = !document.hidden;
      syncLoop();
    };
    document.addEventListener("visibilitychange", onVisibility);

    const io = new IntersectionObserver((entries) => {
      inViewport = entries[0]?.isIntersecting ?? true;
      syncLoop();
    });
    io.observe(canvas);

    const onLost = (e: Event) => {
      e.preventDefault();
      onContextLost?.();
    };
    canvas.addEventListener("webglcontextlost", onLost);

    syncLoop();

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      if (cometTimer) clearTimeout(cometTimer);
      document.removeEventListener("visibilitychange", onVisibility);
      canvas.removeEventListener("click", clickHandler);
      canvas.removeEventListener("webglcontextlost", onLost);
      io.disconnect();
      themeObserver.disconnect();
      gl.deleteProgram(prog);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      gl.deleteBuffer(quad);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size, display: "block", cursor: state === "alive" ? "pointer" : undefined }}
      aria-hidden="true"
      onClick={onClick}
    />
  );
}
