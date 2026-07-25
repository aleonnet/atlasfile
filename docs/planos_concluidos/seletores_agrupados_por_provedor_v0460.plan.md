# Combo rápido de modelos com curadoria + optgroup (v0.46.0)

**Concluído em 2026-07-25.** Origem: proposta do usuário ("combos em dois níveis
provedor → modelo"); a forma final saiu de discussão com dados.

## Decisão de design (registrada com os números)

- Fato medido na API viva: **68 modelos** no catálogo (OpenAI 36, Moonshot 22, Anthropic 10)
  + customs — o usuário estava certo: `<optgroup>` sozinho organiza mas não encurta.
- **Cascata provedor→modelo rejeitada com critério**: o gesto frequente é alternar entre
  favoritos de provedores DIFERENTES (ex.: ollama local ↔ openai barato) — pior caso da
  cascata (2 interações).
- **Forma final = dois níveis de FREQUÊNCIA, não de clique** (benchmark real: ChatGPT/
  Claude.ai expõem ~5 modelos; Cursor = recentes + busca): combo rápido curto e agrupado;
  catálogo completo com busca continua no settings (engrenagem ao lado, que já existia)
  — agora alcançável também pela opção sentinela "Todos os modelos…" dentro do próprio combo.

## Entregue

- `lib/modelGroups.ts`: `groupQuickModelValues(values, catalog)` — dedup na ordem
  atual → recentes → customs; grupos na ordem do registro `PROVIDERS` (desconhecidos ao
  final); label da opção sem a marca redundante (strip só quando a 1ª palavra do label ==
  provider — formato "OpenAI gpt-4-turbo" verificado na API). Sentinela `ALL_MODELS_OPTION`.
- `SettingsContext`: `recentModels` persistido (`atlasfile-recent-models`, cap 5 —
  referência dos players), alimentado por toda seleção efetiva de chat/triagem.
- ChatPanel + IngestTriageCard: selects com `<optgroup>` (labels de grupo via i18n
  `settings:providerGroup.*` nos 2 idiomas; marcas idênticas, "Ollama (local)");
  sentinela abre o settings SEM trocar o modelo selecionado. Valor salvo no profile
  sempre entra no combo mesmo fora do catálogo (select nativo mostraria a 1ª opção).
- Combobox do settings intocado — a busca é o princípio organizador de lá (68 itens).
- "Estrutura de Layout" do perfil inicia fechada (pedido do usuário; `defaultOpen`
  removido — sem persistKey, o default vale para todos).

## Testes e validações

`modelGroups.test.ts` (ordem/dedup/strip/provider desconhecido/valores inválidos);
ChatPanel (grupos, dedup + sentinela presente, sentinela abre settings sem trocar
modelo); triagem (valor do profile agrupado). Suite 250/250, `tsc` limpo, smoke real
no browser (optgroups no picker nativo, recentes acumulando entre chat e triagem).
