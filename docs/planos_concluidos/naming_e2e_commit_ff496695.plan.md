---
name: naming e2e commit
overview: Fechar o corte final de naming para `business_domain`, reescrever o E2E `0.8.0` como delta do `0.7.0` e isolar a limpeza estrutural em commit próprio, sempre com gate de testes 100% antes de avançar.
todos:
  - id: naming-business-domain-cut
    content: Fechar a análise cirúrgica e ajustar o contrato de naming de `{area}` para `{business_domain}` em template, backend, frontend e testes.
    status: completed
  - id: rewrite-e2e-080-delta
    content: Reescrever `docs/plano_teste_e2e_v0.8.0.md` como delta do `0.7.0`, com premissas/dúvidas registradas e sem duplicar os 11 blocos completos.
    status: completed
  - id: quality-gates-and-commit
    content: Executar testes atuais e novos, build, benchmark e só então isolar a limpeza estrutural em commit próprio.
    status: completed
isProject: false
---

# Fechar Naming, E2E 0.8.0 e Commit Estrutural

## Entendimento

O ciclo atual precisa de 3 entregas separadas e coerentes:

- cortar o contrato público de naming de `{area}` para `{business_domain}`;
- corrigir `docs/plano_teste_e2e_v0.8.0.md` para ser um plano delta do `0.7.0`, não uma regressão completa dos 11 blocos;
- isolar toda a limpeza estrutural em um commit próprio antes de qualquer ajuste novo do classificador.

## Fatos verificados no código

- `config/templates/default.json` ainda expõe `"area"` em `naming._available_fields`.
- `backend/app/utils.py` ainda resolve naming via `resolved["area"]` em `build_canonical_filename()`.
- `backend/app/ingestion.py` ainda chama `build_canonical_filename()` com `fields={"area": business_domain, ...}`.
- `frontend/src/features/profile-layout/ProfileLayoutEditor.tsx` ainda mostra o hint `{"{area}"}` no editor de naming.
- `frontend/src/features/templates/TemplateEditorView.tsx` ainda mostra o hint `{"{area}"}` no editor de template.
- `backend/app/reconcile.py` já implementa migração one-way do formato legado `YYYYMMDD__proj__area__titulo__vNN.ext` para o formato novo sem esse segmento.
- `docs/plano_teste_e2e_v0.8.0.md` foi criado como plano standalone amplo; para este ciclo ele deve virar delta do `0.7.0`.

## Decisões registradas

- Não manter `{area}` como alias público do produto.
- Manter somente a migração one-way do nome legado em `backend/app/reconcile.py`.
- `docs/plano_teste_e2e_v0.8.0.md` deve testar apenas o delta do último ciclo e referenciar o `0.7.0` para a cobertura já consolidada.
- Não repetir os 11 blocos completos por padrão.
- Regressão completa de 11 blocos só entra se houver pedido explícito do usuário para full regression antes do release.

## Dúvidas/Premissas registradas no plano

- Premissa atual: `0.8.0` será delta-only + smoke mínimo dos fluxos afetados.
- Premissa atual: o commit estrutural só acontece depois de backend, frontend, build, benchmark e testes novos passarem em `100%`.
- Limitação conhecida: documentação histórica em `docs/planos_concluidos/` e arquivos `.old.md` pode manter nomenclatura antiga sem impacto operacional.

## Arquivos a alterar

- `config/templates/default.json`
- `backend/app/utils.py`
- `backend/app/ingestion.py`
- `frontend/src/features/profile-layout/ProfileLayoutEditor.tsx`
- `frontend/src/features/templates/TemplateEditorView.tsx`
- `backend/tests/unit/test_utils.py`
- `backend/tests/unit/test_reconcile.py`
- `backend/tests/integration/test_api_projects.py`
- `frontend` tests afetados pelos hints de naming
- `docs/plano_teste_e2e_v0.8.0.md`

## Escopo do novo E2E 0.8.0

O `0.8.0` deve conter apenas:

- setup mínimo e projeto novo;
- validação de template/profile/naming com `{business_domain}`;
- ingestão/triagem suficiente para provar o naming gerado em disco;
- busca/chat/Telegram apenas onde o delta afetar metadados e nomenclatura visível;
- templates/profile/layout apenas no que mudou;
- bloco final obrigatório com testes automatizados e benchmark.

O `0.8.0` não deve duplicar integralmente os 11 blocos do `0.7.0`; deve referenciar o `0.7.0` como baseline validada e listar só o que precisa ser reexecutado por causa do delta.

## Validação obrigatória antes de commit

- `cd backend && .venv/bin/pytest -q`
- `cd frontend && npm test`
- `cd frontend && npm run build`
- `cd backend && .venv/bin/python scripts/benchmark_classification.py --mode all --json`
- Executar o `docs/plano_teste_e2e_v0.8.0.md` e registrar resultado final

## Estratégia de commit

Criar um commit exclusivo da limpeza estrutural somente após todos os gates acima passarem. Esse commit não deve misturar tuning do classificador, novos heurísticos ou mudanças de benchmark policy.