import { useEffect } from "react";

export function useEscapeKey(onEscape: (() => void) | null | undefined) {
  useEffect(() => {
    if (!onEscape) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onEscape!();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onEscape]);
}
