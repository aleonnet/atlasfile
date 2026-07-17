import { cn } from "../lib/utils";

/**
 * Wordmark "AtlasFile" com draw-on de stroke (uma vez, ~1.4s) e fill que
 * emerge ao final — usado no hero do onboarding ao lado do orb.
 * Com prefers-reduced-motion o CSS pula direto para o estado final.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 220 40" className={cn("block overflow-visible", className)} role="img" aria-label="AtlasFile">
      <text x="110" y="30" textAnchor="middle" className="atlas-wordmark">
        AtlasFile
      </text>
    </svg>
  );
}
