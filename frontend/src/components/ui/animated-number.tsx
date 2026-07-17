import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

type Props = {
  value: number;
  className?: string;
  /** Duração da contagem em segundos. */
  duration?: number;
};

/** Número que conta até o valor (direção de arte: "números que contam"). */
export function AnimatedNumber({ value, className, duration = 0.8 }: Props) {
  const reducedMotion = useReducedMotion();
  const previous = useRef(0);
  const [display, setDisplay] = useState(() => (reducedMotion ? value : 0));

  useEffect(() => {
    if (reducedMotion) {
      previous.current = value;
      setDisplay(value);
      return;
    }
    const controls = animate(previous.current, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => setDisplay(Math.round(latest)),
    });
    previous.current = value;
    return () => controls.stop();
  }, [value, duration, reducedMotion]);

  return <span className={className}>{display.toLocaleString("pt-BR")}</span>;
}
