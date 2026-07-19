import { IngestTriageCard } from "../features/ingest/IngestTriageCard";
import type { TriageItem } from "../types";

type Props = {
  selectedProject: string;
  selectedProjectLabel: string;
  triageItems: TriageItem[];
  onStatus: (msg: string) => void;
  openaiApiKey: string;
  anthropicApiKey: string;
  onOpenSettings: () => void;
  selectedModelTriage: string;
  onChangeModelTriage: (model: string) => void;
};

/** Classificador como view de primeiro nível (F4.5): é um agente operacional,
 *  par do Assistente — saiu da aba de Configuração para a sidebar. */
export function ClassificadorView(props: Props) {
  return (
    <section className="flex flex-col gap-4">
      <IngestTriageCard {...props} />
    </section>
  );
}
