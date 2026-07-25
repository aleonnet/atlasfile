# Ciclo 1 — estado vivo do Ollama, link Observabilidade, órfão do pending e naming de reingestão (v0.45.0)

**Concluído em 2026-07-25.** Sequência executada: W-D → W-C → W-B → W-A.

## W-D — Reingestão não re-canoniza nome canônico

**Caso real** (2026-07-25): `20260725__taxonomia_e2e_v080__20260320__taxonomia_e2e_v080__societario__DocuSign_...__v01__v01` — a ingestão usava `inbox_file.stem` cru como `original_name` e como `title_token` do `_find_latest_version` (prefixo duplicado + linhagem de versão quebrada).

**Entregue**: `_unwrap_canonical_stem()` na ingestão — age só com a cauda de sistema `__vNN`; iterativo (embrulhos aninhados, até por patterns diferentes pós-migração de naming); cadeia de patterns do reconcile reutilizada; candidato com resíduo (data, project_id ou domínio conhecido — fatos do profile) é preterido. Nome desembrulhado alimenta original_name, título, linhagem de versão, `_INDEX` e metas. Sem parse → comportamento anterior.

**Validação**: 5 unit (incluindo o caso real completo e título com `__` interno) + **smoke real na stack dev**: canônico fabricado reingerido virou `20260725__e2e_v0200__ata_arrendamento_gleba3__v01.docx` — limpo, sem `__v01__v01`, auto-roteado para `juridico/ata` pelos aliases agro aprovados (loop de aprendizado visível de brinde).

**Observação registrada (fora de escopo)**: a classificação ainda vê o NOME embrulhado como sinal de filename (o texto interno contém tokens de projeto/domínio) — candidato a ciclo futuro com benchmark próprio.

## W-C — Órfão físico em `_TRIAGE_REVIEW/pending`

**Entregue**: `_sweep_orphan_pending_files()` no reconcile por projeto — arquivo não-.json sem meta que o referencie, com mtime além de `AUTO_RECONCILE_INTERVAL_SECONDS` (600s — guarda derivada do intervalo real, cobre a janela move→meta da ingestão), vai para `rejected/` com meta sidecar (`orphaned_missing_metadata`) — visível e reversível na UI, nunca deletado; dotfiles ignorados. Contador `orphan_pending_files_moved` no report, summary agregado e toast (PT/EN). Espelha o self-healing inverso pré-existente (`triage.list_pending`).

**Validação**: unit com 4 cenários (órfão velho movido; referenciado/recente/dotfile intocados; idempotência).

## W-B — Link "Observabilidade" no Painel

**Fato decisivo**: `DASHBOARDS_URL` é endereço interno da rede Docker — inútil no browser. **Entregue**: link no Painel derivando `http(s)://<host-atual>:5601`; env opcional `DASHBOARDS_PUBLIC_URL` (compose + `.env.example`) exposta em `/api/setup/status` para proxy/acesso remoto; tooltip com a dica de login. **Validação**: integração backend (default vazio + configurado verbatim), teste do App (href derivado + `_blank`), smoke real no browser (href `http://localhost:5601` confirmado).

## W-A — Estado vivo do modelo custom no seletor

**Problema** (achado do usuário, v0.44.0): selo "(validado por você)" era localStorage estático — o usuário podia achar que tinha modelo up com o Ollama parado, "e a culpa parecia dele".

**Entregue**:
- Storage `atlasfile-custom-models` evolui de `string[]` para `[{value, validatedAt}]` com migração transparente dos legados (sem data → selo sem data inventada); API pública `customModels: string[]` preservada + `customModelsMeta` novo; re-validar um modelo atualiza a data.
- `useCustomModelStatus` (TanStack Query; falha NUNCA bloqueia a UI): `available` | `model_missing` (dica `ollama pull`) | `endpoint_down` (dica `ollama serve`; mapeado por `*_REQUEST_FAILED`) | `unknown`. **Cheque vivo estrutural** calibrado por DUAS reproduções reais do usuário durante o teste: (1) "só reload verificava" → `refetchInterval`; (2) "fechei o Ollama com o chat aberto e ficou verde um bom tempo" → o intervalo default pausa com a janela desfocada e o focus-refetch era barrado pelo staleTime de 60s — final: 15s de intervalo **com `refetchIntervalInBackground`** (olhar o browser enquanto mexe no terminal é o fluxo real) + staleTime 10s (refocar re-verifica na hora). GET local, custo desprezível.
- **Estado no próprio seletor** (`useCustomModelStatusText`) — design fechado por DESENHO ANOTADO do usuário após 4 iterações ao vivo (texto inline quebrava layout → LED de canto "weird" → botão-ícone Plug → **sem ícone novo: o estado vai no elemento**): seletor esmaecido (`opacity-50`) = indisponível, `border-accent text-accent` = disponível, tooltip com a dica; nunca desabilita. O botão do Telegram na toolbar adota a MESMA gramática (esmaecido/laranja, sem LED de bolinha). Lições registradas na memória de padrões: padrão da casa > benchmark externo; gramática de estado do Brain para elementos interativos; LED com glow reservado a linhas de status rotuladas (sidebar, modal de canais). A opção do select mostra só o valor; a proveniência com data vive no combobox de settings.
- Decisão de UX mantida do plano: modelo indisponível continua selecionável — o aviso educa, não bloqueia.

**Validação**: 8 unit/컴포넌트 (migração legado, formato novo com data, estados vivo/morto/ausente) + **smoke real involuntariamente perfeito**: durante o teste o Ollama do host caiu de verdade entre duas medições e o badge reportou "○ unavailable now — is Ollama running? run: ollama serve" — o estado vivo refletiu a realidade no exato cenário que motivou o item.

**Fora de escopo confirmado**: auto-start do daemon (impossível do container; registrado no roadmap com o limite arquitetural).

## Extra do ciclo — padronização dos botões de ação de linha (pedido do usuário)

Varredura completa: canônicas `rowDeleteButtonClass` (existente) + `rowActionButtonClass`
(nova, accent) em `collapsible-section.tsx`; divergentes convertidos (✕ ghost do
ProfileLayoutEditor; ⇄ do histórico ganhou coluna própria); rótulo "Ação"/"Action"
(`common:table.actionColumn`) em TODAS as colunas de ação (histórico, evolução, template ×2,
layout). DE/PARA de reclassificação do histórico: célula limpa + `*`, DE→PARA no tooltip e
linha no bloco "Detalhes da Classificação" (as duas sugestões do usuário combinadas).
Auditoria de CSS: zero classe órfã (script de auditoria definida×usada; 2 falsos positivos =
classes runtime do Recharts com override documentado). Dead export do hook de status removido.

## Validações do ciclo

`make test` (backend **652**, frontend **246/33 arquivos** após ajuste do ChatPanel.test para renderizar sob SettingsProvider — composição real do app), `tsc` limpo, smoke real na stack dev (reingestão, link, badge). Achado ambiental fora de escopo: `host.docker.internal:11434` inalcançável do container no momento do teste (medição feita com o Ollama já caído — inconclusiva; re-testar com Ollama up antes de abrir item).
