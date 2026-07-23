# projects_root_resilience_v0380 — Resiliência à perda da raiz de projetos

> **CONCLUÍDO em 2026-07-23.** Origem: teste destrutivo do usuário (deletou
> `~/Documents/AtlasFileProjects` com o stack no ar) durante a travessia E2E.
> Branch: `feature/projects-root-resilience-v0380` (empilhado no v0.37.0).

## Sintomas observados (instância real)

1. API viva (`/health` 200) mas toda operação de projeto → `PermissionError:
   Operation not permitted: '/projects/meu_projeto'` → 500 cru → "NetworkError"
   no browser, sem pista para o usuário.
2. Dashboard exibindo 7 docs indexados de um projeto que não existia mais —
   órfãos imortais.
3. Modal de inicialização sem NENHUM template (nem o default builtin).

## Diagnóstico (fatos do código)

- `cleanup_orphan_projects` ERA chamado (`services/reconcile_service.py:107`) —
  diagnóstico inicial de "código morto" estava errado (grep não cobriu
  `services/`). O culpado: guard `if reindex_search and valid_projects and
  cleanup_orphans` — com a raiz VAZIA (pós-deleção), `valid_projects=[]` pulava
  a limpeza para sempre. O guard tinha mérito (mount quebrado não pode custar o
  índice) mas não distinguia "saudável e vazia" de "inacessível".
- Templates builtin existem no container (`config/templates/`), mas o scan do
  diretório user (dentro da raiz quebrada) estourava OSError sem tratamento.
- Nenhum código estável para o estado "raiz indisponível".

## Solução (a mesma sonda une os três fixes)

1. **`backend/app/projects_root.py`** — `projects_root_health()`: existe + é
   diretório + `os.listdir` (denuncia mount quebrado que `os.path.exists` não
   pega) + gravável. Nunca levanta exceção.
2. **Guard corrigido** (`reconcile_service`): limpeza de órfãos liberada com a
   raiz saudável MESMO vazia (instância recomeçada zera o índice antigo);
   pulada com `skipped_reason` no relatório quando a raiz está indisponível.
3. **Código estável**: handler global de `OSError` → sonda reprova → **503
   `PROJECTS_ROOT_UNAVAILABLE`** com instrução (recriar pasta + down/up);
   sonda aprova → 500 `INTERNAL_ERROR` (sem mascarar erros alheios).
4. **`/api/setup/status`** ganha `projects_root_ok`/`projects_root_error`;
   `onboarding_suggested` exige raiz saudável (mount quebrado ≠ instância nova).
5. **Banner global na UI** (poll de 20s do setup-status): título + instrução,
   i18n PT/EN; teste garante que o wizard NÃO abre nesse estado.
6. **Templates resilientes**: `_scan_dir`/`_resolve_template_path` tolerantes a
   OSError — builtin sempre disponível.

## Testes

7 unit backend (sonda saudável/vazia/ausente/arquivo; cleanup liberado com raiz
vazia e pulado com raiz quebrada; setup-status expõe saúde; handler 503/500;
templates builtin sobrevivem) + 1 frontend (banner renderiza e wizard não abre).
Suíte completa verde.

## Verificação E2E (adicionada ao roteiro como estágio 34)

Com o stack no ar: deletar a pasta de projetos do host → banner claro em ≤20s
(nunca "NetworkError"); recriar a pasta + `docker compose down && up -d` →
wizard reabre com o template default; após criar projeto, Reconcile INDEX →
`orphan_docs_deleted > 0` e os fantasmas somem do Dashboard.
