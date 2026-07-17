# UI de conflitos de rótulo + criação governada de taxonomia (v0.22.0)

Registro de decisões dos dois pacotes iterativos entregues em 2026-07-17, na sequência do plano `instalador_e_reconciliacao_rotulos_v0210` (evolução dirigida em conversa, sem arquivo de plano prévio).

## Problema

1. A arbitragem de conflitos de rótulo (reconciliação por SHA) exigia editar markdown e rodar CLI — fora do padrão do produto.
2. Sugestões aprovadas podiam usar `document_type`/`business_domain` inexistentes na taxonomia (ex.: o catch-all `outro` do prompt), e o guardrail do move as rejeitava sem oferecer caminho.

## Decisões

- **Arbitragem na UI, mesmo músculo da Triagem**: card "Conflitos de rótulo" no Painel; proposta do LLM em painel púrpura (semântica de inteligência) com justificativa; resolução em um clique com proveniência (`human` / `human_confirmed_llm`).
- **Resolução propaga por SHA** a fontes (validation/training) e derivados existentes (corpus/splits) direto no backend (`app/label_conflicts.py`) — sem depender dos scripts de dataset (não empacotados na imagem).
- **Taxonomia cresce só por aprovação humana** (`app/taxonomy.py`): criação atualiza o template `default` no volume (`_ATLASFILE/templates/`, sobrepõe o builtin, proveniência em `template_meta.notes`) e propaga aos profiles de todos os projetos inicializados. `outro` é bloqueado como chave.
- **Fundamento verificado**: `bootstrap` e `llm` consomem a taxonomia do profile em runtime — tipo novo com aliases classifica imediatamente; `sparse_logreg` só conhece classes vistas no treino (aprende no ciclo seguinte com exemplos da triagem).
- **Aliases são o contrato**: o diálogo de criação expõe label + aliases ("é o que o bootstrap usa para classificar").
- Re-execuções do `reconcile_labels.py` **preservam resoluções prévias** (nunca reabrem nem re-arbitram o decidido).
- Gotcha registrado: `template_store.get_template()` retorna wrapper `{meta..., profile: raw}` — o template editável é `["profile"]` (dois bugs nasceram disso).

## Validação

- 495 testes backend (+8: taxonomy/label_conflicts) e 140 frontend (+5: card com fluxo de criação).
- E2E real: conflito sintético resolvido via UI (toast + propagação); fluxo de criação validado até o diálogo com tipo sintético (cancelado para não sujar a taxonomia real); os 4 conflitos reais foram arbitrados pelo usuário na UI; rehome aplicado — 20/20 arquivos realinhados, descasamento zero.
