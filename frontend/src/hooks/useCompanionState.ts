import { useEffect, useRef, useState } from "react";
import type { CompanionState } from "../components/CompanionOrb";

/**
 * Derives the companion orb visual state from chat sending/error status.
 *
 * - error → "error"
 * - sending → "thinking"
 * - just finished (sending went false without error) → "success" for 600ms → "idle"
 * - default → "idle"
 */
export function useCompanionState(
  sending: boolean,
  error: string | null
): CompanionState {
  const [state, setState] = useState<CompanionState>("idle");
  const wasSendingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (error) {
      setState("error");
      wasSendingRef.current = false;
      return;
    }

    if (sending) {
      setState("thinking");
      wasSendingRef.current = true;
      return;
    }

    // sending just went false without error → show success briefly
    if (wasSendingRef.current) {
      wasSendingRef.current = false;
      setState("success");
      timerRef.current = setTimeout(() => setState("idle"), 600);
      return;
    }

    setState("idle");
  }, [sending, error]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return state;
}
