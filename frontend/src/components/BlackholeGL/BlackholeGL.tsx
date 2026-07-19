import { useEffect, useRef } from "react";
import { BH_FRAG, BH_VERT } from "./blackholeShader";

type Props = {
  /** backdrop: preenche o pai (absoluto), deriva Lissajous; orb: quadrado centrado. */
  variant: "backdrop" | "orb";
  /** 0..1 — massa/atividade (tamanho, dilatação, brilho). */
  intensity?: number;
  /** Brilho do starfield lenteado (0 desliga). */
  starGain?: number;
  /** Lado do canvas na variante orb (px CSS). */
  size?: number;
  className?: string;
};

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    // eslint-disable-next-line no-console
    console.error("BlackholeGL shader:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

/**
 * Buraco negro de Schwarzschild (port do ghostty-blackhole, MIT) como elemento
 * vivo da UI. Mesmo contrato de ciclo de vida do OrbGL: pausa com aba oculta
 * ou fora do viewport; `prefers-reduced-motion` congela num frame estático
 * (a física continua correta, só não anima). Falha de WebGL degrada para nada
 * — o conteúdo por cima nunca depende do céu.
 */
export function BlackholeGL({ variant, intensity = 0.55, starGain = 0.55, size = 96, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const intensityRef = useRef(intensity);
  intensityRef.current = intensity;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl2", { alpha: true, antialias: false, premultipliedAlpha: true });
    if (!gl) return;

    const vs = compile(gl, gl.VERTEX_SHADER, BH_VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, BH_FRAG);
    if (!vs || !fs) return;
    const prog = gl.createProgram()!;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    // Saída premultiplicada do shader: luz soma, sombra oclui
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    const loc = {
      res: gl.getUniformLocation(prog, "uRes"),
      time: gl.getUniformLocation(prog, "uTime"),
      intensity: gl.getUniformLocation(prog, "uIntensity"),
      variant: gl.getUniformLocation(prog, "uVariant"),
      starGain: gl.getUniformLocation(prog, "uStarGain"),
    };

    // Custo por pixel é alto (N_STEPS geodésicos): DPR contido, sobretudo no backdrop
    const dpr = Math.min(window.devicePixelRatio || 1, variant === "backdrop" ? 1.25 : 2);
    const applySize = () => {
      const w = variant === "orb" ? size : canvas.clientWidth || 1;
      const h = variant === "orb" ? size : canvas.clientHeight || 1;
      canvas.width = Math.max(2, Math.round(w * dpr));
      canvas.height = Math.max(2, Math.round(h * dpr));
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    applySize();
    const ro = variant === "backdrop" ? new ResizeObserver(applySize) : null;
    ro?.observe(canvas);

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const start = performance.now();

    const draw = (t: number) => {
      gl.uniform2f(loc.res, canvas.width, canvas.height);
      gl.uniform1f(loc.time, t);
      gl.uniform1f(loc.intensity, intensityRef.current);
      gl.uniform1f(loc.variant, variant === "orb" ? 1 : 0);
      gl.uniform1f(loc.starGain, starGain);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    let visible = !document.hidden;
    let inViewport = true;
    let raf = 0;
    let running = false;

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      draw((now - start) / 1000);
    };

    const syncLoop = () => {
      if (reduced) return; // frame estático já desenhado
      const shouldRun = visible && inViewport;
      if (shouldRun && !running) {
        running = true;
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

    if (reduced) draw(11.7); // instante escolhido: disco bem posicionado
    else syncLoop();

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      io.disconnect();
      ro?.disconnect();
      gl.deleteProgram(prog);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      gl.deleteBuffer(quad);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant, size, starGain]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={className}
      style={variant === "orb" ? { width: size, height: size, display: "block" } : { width: "100%", height: "100%", display: "block" }}
    />
  );
}
