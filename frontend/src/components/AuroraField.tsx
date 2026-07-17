import { useEffect, useRef } from "react";

type AuroraBlob = {
  x: number;
  y: number;
  /** Posição-base relativa (0..1). */
  bx: number;
  by: number;
  radius: number;
  color: string;
  /** Rigidez da mola (menor = mais "atrasado", cria parallax). */
  stiffness: number;
  /** Quanto o blob é atraído pelo pointer (0..1). */
  pull: number;
  phase: number;
  freqX: number;
  freqY: number;
  ampX: number;
  ampY: number;
};

/**
 * Campo aurora em canvas 2D: blobs nas cores da marca (tokens --orb-aurora-*)
 * derivam lentamente e são atraídos pelo pointer com física de mola — cada blob
 * com rigidez diferente, criando parallax. Aditivo ("lighter"), sem WebGL.
 * Com prefers-reduced-motion renderiza um frame estático.
 */
export function AuroraField({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;

    const resize = () => {
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const styles = getComputedStyle(document.documentElement);
    const token = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
    const isLight = document.documentElement.getAttribute("data-theme") === "light";

    // Blend por tema: no dark, "lighter" (aditivo) faz as cores brilharem sobre
    // o fundo escuro; sobre branco o aditivo satura para branco e os blobs
    // somem — no light usa "multiply" (pigmento sobre papel) com alpha
    // reforçado, sem alterar nada do comportamento dark.
    const composite: GlobalCompositeOperation = isLight ? "multiply" : "lighter";
    const boostAlpha = (rgba: string, factor: number, cap: number): string => {
      const m = rgba.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
      if (!m) return rgba;
      const a = Math.min(cap, (m[4] ? parseFloat(m[4]) : 1) * factor);
      return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${a})`;
    };
    const tone = (c: string) => (isLight ? boostAlpha(c, 2.2, 0.6) : c);
    const c1 = tone(token("--orb-aurora-1", "rgba(255, 90, 54, 0.28)"));
    const c2 = tone(token("--orb-aurora-2", "rgba(201, 123, 255, 0.24)"));
    const c3 = tone(token("--orb-aurora-3", "rgba(255, 138, 107, 0.22)"));

    const blobs: AuroraBlob[] = [
      { bx: 0.30, by: 0.22, radius: 0.42, color: c1, stiffness: 0.045, pull: 0.16, phase: 0.0, freqX: 0.21, freqY: 0.17, ampX: 0.06, ampY: 0.05 },
      { bx: 0.72, by: 0.30, radius: 0.36, color: c2, stiffness: 0.028, pull: 0.24, phase: 1.9, freqX: 0.16, freqY: 0.23, ampX: 0.07, ampY: 0.04 },
      { bx: 0.50, by: 0.78, radius: 0.40, color: c3, stiffness: 0.02, pull: 0.32, phase: 3.7, freqX: 0.13, freqY: 0.19, ampX: 0.05, ampY: 0.06 },
      { bx: 0.14, by: 0.68, radius: 0.30, color: c2, stiffness: 0.036, pull: 0.12, phase: 5.1, freqX: 0.24, freqY: 0.14, ampX: 0.04, ampY: 0.05 },
    ].map((b) => ({ ...b, x: b.bx, y: b.by }));

    // Pointer em coordenadas relativas; começa no centro superior (posição do orb).
    let px = 0.5;
    let py = 0.35;
    const onPointerMove = (e: PointerEvent) => {
      if (w === 0 || h === 0) return;
      const rect = canvas.getBoundingClientRect();
      px = (e.clientX - rect.left) / Math.max(1, rect.width);
      py = (e.clientY - rect.top) / Math.max(1, rect.height);
    };
    window.addEventListener("pointermove", onPointerMove, { passive: true });

    let t = 0;
    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = composite;
      const scale = Math.max(w, h);
      for (const b of blobs) {
        const wanderX = Math.sin(t * b.freqX * Math.PI * 2 + b.phase) * b.ampX;
        const wanderY = Math.cos(t * b.freqY * Math.PI * 2 + b.phase) * b.ampY;
        const targetX = b.bx + wanderX + (px - 0.5) * b.pull;
        const targetY = b.by + wanderY + (py - 0.5) * b.pull;
        b.x += (targetX - b.x) * b.stiffness;
        b.y += (targetY - b.y) * b.stiffness;

        const cx = b.x * w;
        const cy = b.y * h;
        const r = b.radius * scale;
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        grad.addColorStop(0, b.color);
        grad.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    let raf = 0;
    const frame = () => {
      t += 1 / 60;
      draw();
      raf = requestAnimationFrame(frame);
    };

    if (reduced) {
      draw();
    } else {
      raf = requestAnimationFrame(frame);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointerMove);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden />;
}
