import { Toaster as SonnerToaster, toast } from "sonner";

/**
 * Toaster global temado com os tokens do AtlasFile.
 * Substitui progressivamente o footer `.status` (morre na Fase 6).
 */
function Toaster(props: React.ComponentProps<typeof SonnerToaster>) {
  return (
    <SonnerToaster
      position="bottom-right"
      toastOptions={{
        style: {
          background: "var(--panel-strong)",
          border: "1px solid var(--border-subtle)",
          color: "var(--text)",
          boxShadow: "var(--shadow-lg)",
          fontFamily: "var(--font-body)",
          fontSize: "0.82rem",
          borderRadius: "var(--radius-lg)",
        },
        classNames: {
          success: "[&_[data-icon]]:!text-[var(--ok)]",
          error: "[&_[data-icon]]:!text-[var(--danger)]",
          info: "[&_[data-icon]]:!text-[var(--accent)]",
          warning: "[&_[data-icon]]:!text-[var(--accent-light)]",
        },
      }}
      {...props}
    />
  );
}

export { Toaster, toast };
