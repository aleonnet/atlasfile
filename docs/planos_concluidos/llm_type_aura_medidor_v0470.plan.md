# LLM document_type governado, aura blackhole e medidor de contexto honesto (v0.47.0)

**Concluído em 2026-07-25.** Origem: dois achados do usuário no teste da v0.46.x.

## A — document_type do LLM (caso real: gpt-5 respondeu 'outro' em tag_only)

Cadeia do bug: o prompt INSTRUÍA a sentinela `'outro'` (`orchestrator.py`) → a aplicação
validava `business_domain` mas **não** `document_type` (assimetria em `_apply_llm_policy`)
→ o resolvedor de pastas lançava `document_type folder is not configured: outro` → arquivo
inteiro em FALHA. Decisões do usuário: LLM pode sugerir tipo; NUNCA 'outro'; aplicar só se
existir na taxonomia.

Entregue: prompt reescrito (sentinela banida; "OMITA o campo e justifique"); validação
espelho no `_apply_llm_policy` (`llm_proposed_document_type` registra o que não foi
aplicado, visível ao revisor); degradação para TRIAGEM (`routing_unconfigured`) se algum
rótulo chegar ao roteamento sem pasta — nunca FALHA do arquivo. 2 testes antigos
atualizados (asseravam o prompt antigo/fixture sem tipos) + 3 novos.

## B — Aura de processamento com blackhole (2 iterações com o usuário)

v1: halo arco-íris → orb pequeno + borda ("sem wow factor", e o brilho que o halo
espalhava fora do card fazia papel de separação — feedback). **v2 final**: o card focal
ganha o **shader backdrop com lensing** (deriva do buraco, a arte do hero/gate) atrás do
conteúdo + borda em respiração + orb no rótulo; e como o processamento é UM arquivo por
vez, o cursor vira "progress" (pedido do usuário). Véu global + bloqueio de cliques foram
implementados e depois DISPENSADOS pelo próprio usuário após análise factual: botões de
todos os cards já desabilitam durante decisão e o backend serializa por claim atômico
(rename; 409 TRIAGE_DECISION_IN_PROGRESS) — as duas camadas de defesa já existiam.
O progresso do ciclo do classificador também ganhou o lensing. Scrim local do Painel
removido (os disables + cursor cumprem o papel); `.atlas-aura` e CSS mortos removidos;
`MiniOrb` permanece (variante compact + 4 usos). Flagrado ao vivo via Playwright:
2 canvas (lensing + orb) + cursor progress a 100ms do clique de aprovação.

## B2 — Extensão banida como critério de tipo no prompt (achado do usuário)

O briefing listava "extensões esperadas" por tipo e o gpt-5 as tratou como critério
eliminatório (recusou tipo para um diagrama .png, com confissão na justificativa).
Extensões saíram da lista e o prompt instrui: gênero pelo CONTEÚDO, nunca pela extensão.
Reversão registrada de uma decisão pré-v0.39 (o teste antigo documentava o racional da
época; reescrito com o contexto das duas eras).

## C — Medidor de contexto (auditoria factual pedida pelo usuário)

Fatos verificados antes do fix: estimativa = chars÷4 por request no backend; janela do
catálogo LiteLLM; fallback 128k para modelos fora do catálogo (TODOS os customs Ollama);
percentual só atualizava na mensagem seguinte à troca de modelo.

Entregue: (1) janela real do Ollama via `/api/show` (`model_info.*.context_length`; fato
medido: gemma4:12b = 262.144 — 2× o fallback), com cache em processo incluindo falhas;
(2) recálculo imediato no client ao trocar de modelo (estimativa da última resposta ÷
janela do modelo novo; custom espelha o fallback até a próxima resposta); (3) tooltip do
gauge documenta janela e heurística nos 2 idiomas.

## Validações

Backend 663/663 (novos: sentinela banida do prompt, tipo inválido não aplicado/registrado,
tipo válido aplicado, janela Ollama viva + falha cacheada); frontend 250/250 (aura sem
`.atlas-aura`, com canvas + respiração); `tsc` limpo.
