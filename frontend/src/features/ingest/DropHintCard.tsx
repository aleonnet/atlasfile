import { Command, FileUp, Search, Sparkles } from "lucide-react";
import { Card, CardContent } from "../../components/ui/card";

/**
 * Convite ao drag'n'drop global — o "estado pronto" do Painel quando não há
 * pendências: o mini-portal (mesmo anel cônico do overlay de upload) lembra
 * que soltar um arquivo em QUALQUER tela alimenta o pipeline inteiro.
 */
export function DropHintCard() {
  return (
    <Card className="overflow-hidden">
      <CardContent className="relative flex flex-col items-center gap-4 px-6 py-10 text-center sm:flex-row sm:text-left">
        {/* Mini-portal: anel cônico girando (assinatura do upload global) */}
        <div className="relative grid size-24 shrink-0 place-items-center">
          <div
            aria-hidden
            className="absolute inset-0 rounded-full opacity-80 [animation:atlas-portal-spin_6s_linear_infinite] motion-reduce:animate-none"
            style={{
              background:
                "conic-gradient(from 0deg, transparent 0%, var(--accent-soft) 25%, var(--accent) 50%, var(--accent-soft) 75%, transparent 100%)",
              mask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2px))",
              WebkitMask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2px))",
            }}
          />
          <div
            aria-hidden
            className="absolute inset-3 rounded-full"
            style={{ background: "radial-gradient(circle, var(--accent-soft), transparent 70%)" }}
          />
          <FileUp className="relative size-8 text-accent" aria-hidden />
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="font-display text-base font-bold text-foreground-strong">
            Solte arquivos em qualquer lugar
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Arraste PDF, DOCX, XLSX, PPTX, MSG ou EML para <strong className="text-foreground">qualquer tela</strong> —
            o portal envia à INBOX e o pipeline cuida do resto: classificação, roteamento, indexação e busca.
          </p>
          <div className="mt-3 flex flex-wrap justify-center gap-2 sm:justify-start">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-panel px-2.5 py-1 font-mono text-[0.68rem] text-muted-foreground">
              <Command className="size-3 text-accent" aria-hidden /> ⌘K busca tudo
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-panel px-2.5 py-1 font-mono text-[0.68rem] text-muted-foreground">
              <Sparkles className="size-3 text-accent-purple" aria-hidden /> classificação automática
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-panel px-2.5 py-1 font-mono text-[0.68rem] text-muted-foreground">
              <Search className="size-3 text-accent" aria-hidden /> busca híbrida com citações
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
