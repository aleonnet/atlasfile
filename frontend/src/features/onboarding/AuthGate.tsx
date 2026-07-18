import { KeyRound, Loader2 } from "lucide-react";
import { useState } from "react";
import { fetchSetupStatus, setApiKey } from "../../api";
import { Orb } from "../../components/OrbGL";
import { Wordmark } from "../../components/Wordmark";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

/**
 * Gate de autenticação: quando o backend está com API_AUTH_ENABLED=true e o
 * navegador não tem key válida, esta tela é a PRIMEIRA coisa que o usuário vê
 * — captura a key (exibida ao final do install --enable-auth) antes de
 * qualquer outro fluxo (onboarding incluído). Validada contra a API na hora.
 */
export function AuthGate() {
  const [keyValue, setKeyValue] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    const trimmed = keyValue.trim();
    if (!trimmed) return;
    setChecking(true);
    setError("");
    setApiKey(trimmed);
    try {
      await fetchSetupStatus();
      // Key válida persistida — boot limpo com todos os fetches autenticados
      window.location.reload();
    } catch {
      setApiKey("");
      setError("API key inválida ou sem permissão. Confira a key exibida ao final da instalação.");
      setChecking(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-xl border border-border bg-panel p-8 shadow-[0_18px_48px_rgba(0,0,0,0.35)]">
        <div className="flex flex-col items-center gap-2 text-center">
          <Orb state="alive" size={96} />
          <Wordmark className="h-12 w-64" />
        </div>
        <h2 className="mt-5 flex items-center justify-center gap-2 font-display text-lg font-bold text-foreground-strong">
          <KeyRound className="size-4 text-accent" aria-hidden />
          Esta instalação exige uma API key
        </h2>
        <p className="mt-1 text-center text-sm text-muted-foreground">
          A autenticação está habilitada neste servidor. Cole a key exibida ao final da instalação
          (<code className="rounded bg-panel-strong px-1 py-0.5 font-mono text-[0.72rem] text-accent-light">install.sh --enable-auth</code>).
          Ela fica somente neste navegador.
        </p>
        <div className="mt-4">
          <Input
            type="password"
            className="font-mono"
            value={keyValue}
            placeholder="atlas_sk_..."
            autoComplete="off"
            autoFocus
            onChange={(e) => setKeyValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
          {error && <p className="mt-1.5 text-[0.8rem] text-destructive">{error}</p>}
        </div>
        <Button className="mt-3 w-full" disabled={checking || !keyValue.trim()} onClick={() => void handleSubmit()}>
          {checking ? <Loader2 className="animate-spin" /> : <KeyRound />}
          {checking ? "Validando..." : "Entrar"}
        </Button>
      </div>
    </div>
  );
}
