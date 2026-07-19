import common from "./common.json";
import labels from "./labels.json";
import triage from "./triage.json";

/** Bundle PT-BR — fonte da verdade (extração 1:1 do texto do app).
 *  Namespaces entram por onda (F4): common/labels/triage → painel/ingest →
 *  usage/settings/templates/profileLayout → onboarding → chat. */
export const ptBR = {
  common,
  labels,
  triage,
};
