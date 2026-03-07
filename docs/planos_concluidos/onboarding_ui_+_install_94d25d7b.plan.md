---
name: Onboarding UI + Install
overview: Simplificar a instalacao para um unico script que sobe containers com defaults sensiveis e mover toda a configuracao do usuario (projetos, LLM keys) para um wizard de onboarding na UI, alem de adicionar cleanup decremental de projetos orfaos no OpenSearch.
todos:
  - id: simplify-install-script
    content: "Reescrever atlasfile_install.sh: remover bootstrap Python, auto-gerar .env com defaults, abrir browser apos health check"
    status: completed
  - id: backend-setup-status
    content: Criar endpoint GET /api/setup/status em main.py (projects_root, initialized_projects, onboarding_suggested)
    status: completed
  - id: frontend-api-setup
    content: Adicionar fetchSetupStatus() em api.ts
    status: completed
  - id: onboarding-wizard
    content: "Criar OnboardingWizard.tsx com 3 steps: boas-vindas, criar projeto, LLM keys (opcional)"
    status: completed
  - id: app-tsx-onboarding
    content: Integrar OnboardingWizard em App.tsx com deteccao de first-run
    status: completed
  - id: cleanup-orphans-backend
    content: Implementar cleanup_orphan_projects() em reconcile.py + integrar em reconcile_service.py
    status: completed
  - id: cleanup-orphans-ui
    content: Exibir orphan_docs_deleted no summary do reconcile na UI (opcional)
    status: completed
  - id: test-backend-setup-status
    content: "Testes do endpoint GET /api/setup/status: cenarios com/sem projetos, com/sem profile"
    status: completed
  - id: test-backend-cleanup-orphans
    content: "Testes unitarios de cleanup_orphan_projects(): mock OpenSearch aggregation + delete_by_query"
    status: completed
  - id: test-frontend-onboarding
    content: "Testes do OnboardingWizard.tsx: renderizacao, navegacao entre steps, submit de projeto, skip LLM"
    status: completed
  - id: test-frontend-app-onboarding
    content: "Testes em App.test.tsx: condicional de onboarding (first-run vs returning user)"
    status: completed
isProject: false
---

# Onboarding UI, Install Simplificado e Cleanup Decremental

## Contexto e Problema

Hoje o usuario precisa editar `.env` manualmente (definir `PROJECTS_HOST_ROOT`, API keys, etc.) antes de rodar `docker compose up`. O script `atlasfile_install.sh` ainda faz bootstrap de projeto via Python no host, exigindo dependencias. Nao existe onboarding na UI. Alem disso, projetos deletados do disco deixam documentos orfaos no OpenSearch.

## Decisoes de Arquitetura

### PROJECTS_HOST_ROOT (chicken-and-egg)

O volume mount `${PROJECTS_HOST_ROOT}:/projects` precisa existir **antes** do `docker compose up`. Solucao escolhida:

- O install script auto-gera `.env` com `PROJECTS_HOST_ROOT=$HOME/Documents/Projects` (ou valor passado via `--projects-root`)
- O onboarding UI mostra o path atual (read-only, vem do backend) e explica como alterar (editar `.env` + `docker compose restart api`)
- Alteracao de `PROJECTS_HOST_ROOT` e operacao rara e power-user; nao justifica automacao de restart via UI na v0.3

### API Keys LLM

Ja funcionam via `localStorage` no frontend + headers `X-OpenAI-API-Key` / `X-Anthropic-API-Key`. O onboarding apenas guia o usuario a configura-las no wizard, reutilizando a logica existente do `AssistantSettingsModal`.

### Deteccao de First-Run

Criterio simples: `GET /api/projects` retorna lista vazia ou sem projetos inicializados => mostra onboarding. Flag `localStorage("atlasfile-onboarding-done")` permite dismiss persistente.

### Onboarding Idempotente (replay-safe)

O wizard e **nao-destrutivo**: se executado em uma instalacao existente, carrega os valores atuais (projetos, API keys) e so aplica mudancas se o usuario efetivamente alterar algo. Passar por todos os steps sem modificar nada = zero side-effects.

- Step 1: read-only, sempre seguro.
- Step 2: se ja existem projetos inicializados, exibe-os como cards com check verde ("Ja configurado") e oferece **opcao** de criar um novo. O botao muda de "Criar e Continuar" para apenas "Continuar" quando nao ha projeto novo a criar.
- Step 3: carrega keys existentes do `localStorage` (mascaradas). Se o usuario nao alterar, persiste os mesmos valores (no-op efetivo).

### Botao "Replay Onboarding" (dev mode)

Visivel apenas quando `APP_ENV=dev` (vem do endpoint `/api/setup/status`). Adicionado nas Configuracoes do Assistente (ou como item no header). Ao clicar, limpa o flag `localStorage("atlasfile-onboarding-done")` e renderiza o wizard. Permite testar o fluxo completo em instalacao existente sem side-effects.

---

## Mudancas Planejadas

### 1. Simplificar `atlasfile_install.sh`

**Arquivo:** [atlasfile_install.sh](atlasfile_install.sh)

Remover:

- `bootstrap_project_if_enabled()` e toda logica de Python bootstrap
- Flags: `--project-name`, `--project-id`, `--no-create-project`
- Dependencia de `scripts/bootstrap_project.py` no fluxo de install

Adicionar:

- Funcao `generate_env_if_missing()`: gera `.env` a partir de `.env.example` com defaults sensiveis, substituindo `PROJECTS_HOST_ROOT` pelo valor detectado (`$HOME/Documents/Projects`)
- Manter `--projects-root <path>` como unica flag de configuracao
- Apos health check, abrir browser automaticamente (`open http://localhost:5173` no macOS, `xdg-open` no Linux)
- Logica idempotente: se `.env` ja existe, nao sobrescreve (log informativo)
- Remover `ensure_prereqs` check de `bootstrap_project.py`

Fluxo simplificado:

```
detect_os -> check_docker -> generate_env_if_missing -> docker compose up -d --build -> health_check -> open_browser
```

### 2. Backend: Endpoint de setup status

**Arquivo:** [backend/app/main.py](backend/app/main.py)

Novo endpoint:

```python
@app.get("/api/setup/status")
def setup_status() -> dict:
    roots = list_project_roots(Path(settings.projects_root))
    initialized = []
    for r in roots:
        try:
            load_project_profile(r)
            initialized.append(r.name)
        except Exception:
            pass
    return {
        "app_env": settings.app_env,
        "projects_root": settings.projects_root,
        "total_project_dirs": len(roots),
        "initialized_projects": len(initialized),
        "onboarding_suggested": len(initialized) == 0,
    }
```

- `app_env` permite ao frontend exibir o botao "Replay Onboarding" somente em dev.

Impacto: ~18 linhas, sem dependencias novas.

### 3. Frontend: Componente de Onboarding Wizard

**Novo arquivo:** `frontend/src/features/onboarding/OnboardingWizard.tsx`

Wizard de 3 passos, exibido condicionalmente em `App.tsx`:

- **Step 1 - Boas-vindas**: Logo, descricao breve, exibe `projects_root` (read-only, vem do backend). Botao "Comecar".
- **Step 2 - Criar primeiro projeto**: Nome do projeto + selecao de template (reutilizar logica de `TemplateSelectModal` e `initializeProject` de `api.ts`). O usuario pode criar a pasta de projeto diretamente pelo wizard ou apontar para uma ja existente.
- **Step 3 - Assistente LLM (opcional)**: Formulario de API keys (reutilizar campos de `AssistantSettingsModal.tsx`). Botao "Pular" + "Salvar".
- **Conclusao**: Mensagem de sucesso + botao "Abrir Dashboard" que faz `setOnboardingDone(true)`.

**Arquivo modificado:** [frontend/src/App.tsx](frontend/src/App.tsx)

- Importar `OnboardingWizard`
- Novo estado `onboardingDone` (lido de `localStorage`)
- Chamar `GET /api/setup/status` no mount
- Se `onboarding_suggested && !onboardingDone`: renderizar `OnboardingWizard` ao inves do dashboard
- Callback `onComplete` do wizard: atualiza `localStorage`, faz `fetchProjects()`, seta `selectedProject`

**Novo arquivo:** `frontend/src/api.ts` (adicao)

```typescript
export async function fetchSetupStatus(): Promise<{
  app_env: string;
  projects_root: string;
  total_project_dirs: number;
  initialized_projects: number;
  onboarding_suggested: boolean;
}> {
  const res = await fetch(`${API_URL}/api/setup/status`);
  if (!res.ok) throw new Error("Falha ao verificar status de setup");
  return res.json();
}
```

### 4. Cleanup Decremental (projetos orfaos no OpenSearch)

**Arquivo:** [backend/app/reconcile.py](backend/app/reconcile.py)

Nova funcao:

```python
def cleanup_orphan_projects(
    client: OpenSearch,
    valid_project_ids: set[str],
    valid_project_roots: list[Path],
) -> dict[str, int]:
```

Logica:

1. Aggregation query no OpenSearch: `terms` em `project_id` (size=1000) para listar todos os project_ids indexados
2. Para cada `project_id` no indice que NAO esta em `valid_project_ids`:
  - `delete_by_query` com filtro `term: { project_id: <orphan> }`
3. Retornar `{ orphan_projects_found, orphan_docs_deleted }`

**Arquivo:** [backend/app/services/reconcile_service.py](backend/app/services/reconcile_service.py)

- Chamar `cleanup_orphan_projects()` no final de `run_reconcile()` quando `reindex_search=True`
- Incluir resultado no report/summary

**Arquivo:** [backend/app/main.py](backend/app/main.py) (endpoint existente)

- O reconcile endpoint `POST /api/reconcile` ja suporta `reindex_search` e `reindex_mode`
- Nao precisa de novo endpoint; o cleanup roda automaticamente como parte do reconcile
- Adicionar campo `orphan_docs_deleted` no response summary

**Frontend:** Nenhuma mudanca necessaria para o cleanup. Os numeros aparecerao no summary do reconcile existente na UI. Opcionalmente, adicionar label "docs orfaos removidos: N" no card de status.

---

## Mockups da UI

### Onboarding Wizard - Estrutura Visual

O wizard ocupa a tela inteira (substituindo o dashboard), com layout centralizado, card unico e stepper visual no topo.

**Step 1 - Boas-vindas**

```
  ┌─────────────────────────────────────────────────┐
  │         (logo AtlasFile)                        │
  │                                                 │
  │   Bem-vindo ao AtlasFile                        │
  │                                                 │
  │   Sistema de gestao documental inteligente      │
  │   para projetos.                                │
  │                                                 │
  │   Pasta de projetos:                            │
  │   ┌───────────────────────────────────────┐     │
  │   │ /Users/you/Documents/Projects   (i)   │     │
  │   └───────────────────────────────────────┘     │
  │   Configurado na instalacao. Para alterar,      │
  │   edite .env e reinicie os containers.          │
  │                                                 │
  │                          [ Comecar  -> ]        │
  └─────────────────────────────────────────────────┘
       (1)·────·(2)·────·(3)
```

- `(i)` = tooltip explicativo sobre o path
- Stepper inferior mostra progresso: (1) ativo, (2) e (3) pendentes

**Step 2 - Projetos (condicional)**

Variante A -- First-run (sem projetos):

```
  ┌─────────────────────────────────────────────────┐
  │   Crie seu primeiro projeto                     │
  │                                                 │
  │   Nome do projeto *                             │
  │   ┌───────────────────────────────────────┐     │
  │   │ meu_projeto_ma                        │     │
  │   └───────────────────────────────────────┘     │
  │   Sera criado como subpasta em Projects/        │
  │                                                 │
  │   Label (exibicao)                              │
  │   ┌───────────────────────────────────────┐     │
  │   │ Meu Projeto M&A                       │     │
  │   └───────────────────────────────────────┘     │
  │                                                 │
  │   Template                                      │
  │   ┌───────────────────────────────────────┐     │
  │   │  (o) M&A / Carve-out (default)        │     │
  │   │  ( ) Due Diligence                    │     │
  │   │  ( ) Compliance                       │     │
  │   └───────────────────────────────────────┘     │
  │                                                 │
  │          [ <- Voltar ]    [ Criar e Continuar ] │
  └─────────────────────────────────────────────────┘
       (1)·────·(2)·────·(3)
                 ^ativo
```

Variante B -- Replay (projetos ja existem):

```
  ┌─────────────────────────────────────────────────┐
  │   Seus projetos                                 │
  │                                                 │
  │   ┌─────────────────────────────────────┐       │
  │   │  check  Meu Projeto M&A             │       │
  │   │         meu_projeto_ma - default     │       │
  │   └─────────────────────────────────────┘       │
  │   ┌─────────────────────────────────────┐       │
  │   │  check  Due Diligence Alfa          │       │
  │   │         due_diligence - default      │       │
  │   └─────────────────────────────────────┘       │
  │                                                 │
  │   [ + Criar novo projeto ]                      │
  │                                                 │
  │          [ <- Voltar ]       [ Continuar -> ]   │
  └─────────────────────────────────────────────────┘
       (1)·────·(2)·────·(3)
                 ^ativo
```

- Variante A: ao clicar "Criar e Continuar", chama `initializeProject(name, template)` via API. Validacao: nome obrigatorio, slug-safe. Erro inline se API falhar.
- Variante B: "Continuar" avanca sem side-effects. "Criar novo projeto" expande o formulario da Variante A abaixo da lista.
- Qual variante exibir: se `fetchSetupStatus().initialized_projects > 0` => Variante B, senao => Variante A.

**Step 3 - Assistente LLM (opcional)**

```
  ┌─────────────────────────────────────────────────┐
  │   Configure o assistente (opcional)             │
  │                                                 │
  │   O AtlasFile pode usar um LLM para             │
  │   classificar documentos e responder            │
  │   perguntas sobre seus projetos.                │
  │                                                 │
  │   Provedor                                      │
  │   ┌───────────────────────────────────────┐     │
  │   │  (o) OpenAI                           │     │
  │   │  ( ) Anthropic                        │     │
  │   └───────────────────────────────────────┘     │
  │                                                 │
  │   API Key                                       │
  │   ┌───────────────────────────────────────┐     │
  │   │ sk-••••••••••••••••                   │     │
  │   └───────────────────────────────────────┘     │
  │   Salva localmente no navegador.                │
  │   Voce pode configurar depois em                │
  │   Configuracoes do Assistente.                  │
  │                                                 │
  │          [ Pular ]        [ Salvar e Concluir ] │
  └─────────────────────────────────────────────────┘
       (1)·────·(2)·────·(3)
                          ^ativo
```

- "Pular" finaliza sem salvar keys
- "Salvar e Concluir" persiste em localStorage (mesma logica do AssistantSettingsModal)

**Tela de Conclusao (breve, nao e um step separado)**

```
  ┌─────────────────────────────────────────────────┐
  │         (check icon verde)                      │
  │                                                 │
  │   Tudo pronto!                                  │
  │                                                 │
  │   Projeto "Meu Projeto M&A" criado.             │
  │   Coloque seus arquivos em:                     │
  │   Projects/meu_projeto_ma/_INBOX_DROP/          │
  │                                                 │
  │   Proximo passo: clique em "Processar INBOX"    │
  │   para iniciar a ingestao.                      │
  │                                                 │
  │              [ Abrir Dashboard ]                │
  └─────────────────────────────────────────────────┘
```

### Reconcile Summary - Campo Adicional (cleanup)

No card de status do reconcile existente, apos a execucao:

```
  Reconciliacao concluida
  ─────────────────────────
  Projetos processados:  3
  Docs indexados:       45
  Docs ignorados (sha): 12
  Docs orfaos removidos: 8    <-- NOVO
  Duracao: 4.2s
```

---

## Testes

### Backend

#### `backend/tests/integration/test_api_setup_status.py` (novo)

Testes do endpoint `GET /api/setup/status` usando `client` (TestClient) + mocks:

- `test_setup_status_no_projects`: mock `list_project_roots` retornando `[]` => `onboarding_suggested: true`, `initialized_projects: 0`
- `test_setup_status_with_uninitialized_project`: mock `list_project_roots` retornando 1 root, `load_project_profile` levanta Exception => `total_project_dirs: 1`, `initialized_projects: 0`, `onboarding_suggested: true`
- `test_setup_status_with_initialized_project`: mock `list_project_roots` + `load_project_profile` ok => `initialized_projects: 1`, `onboarding_suggested: false`
- `test_setup_status_mixed_projects`: 2 roots, 1 inicializado + 1 nao => `total_project_dirs: 2`, `initialized_projects: 1`, `onboarding_suggested: false`
- `test_setup_status_returns_projects_root`: verifica que `projects_root` contem o valor de `settings.projects_root`

Padrao: mesmo dos testes em `test_api_projects.py` -- `patch("app.main.list_project_roots")` + `patch("app.main.load_project_profile")`.

#### `backend/tests/unit/test_cleanup_orphans.py` (novo)

Testes unitarios de `cleanup_orphan_projects()`:

- `test_cleanup_no_orphans`: mock aggregation retorna `project_ids` que existem em `valid_project_ids` => `orphan_docs_deleted: 0`
- `test_cleanup_removes_orphan_project`: aggregation retorna `["proj_a", "proj_b"]`, valid = `{"proj_a"}` => `delete_by_query` chamado com `term: { project_id: "proj_b" }`, verifica retorno `orphan_projects_found: 1`
- `test_cleanup_multiple_orphans`: 3 no indice, 1 valido => 2 orphans deletados
- `test_cleanup_empty_index`: aggregation retorna buckets vazios => nada deletado
- `test_cleanup_delete_by_query_failure`: mock `delete_by_query` levanta Exception => funcao nao quebra, loga erro, retorna contagem parcial

Padrao: `MagicMock` para OpenSearch client, `mock_client.search.return_value = { "aggregations": { "project_ids": { "buckets": [...] } } }`.

#### `backend/tests/unit/test_reconcile.py` (adicao)

Adicionar caso ao arquivo existente:

- `test_sync_search_index_deletes_orphan_docs_for_project`: verifica que `sync_search_index_for_project` deleta docs cujo `doc_id` nao esta no `_INDEX.md`

### Frontend

#### `frontend/src/features/onboarding/OnboardingWizard.test.tsx` (novo)

Testes do componente com `@testing-library/react`:

**Navegacao e renderizacao:**

- `test_renders_welcome_step_by_default`: verifica texto "Bem-vindo ao AtlasFile", botao "Comecar", path de projetos visivel
- `test_navigates_to_create_project_step`: click em "Comecar" => mostra "Crie seu primeiro projeto"
- `test_back_button_returns_to_previous_step`: no step 2, click "Voltar" => volta ao step 1

**Step 2 - Variante A (first-run, sem projetos):**

- `test_create_project_validates_name`: campo vazio + click "Criar" => mensagem de erro inline
- `test_create_project_calls_api`: preenche nome + seleciona template + click "Criar" => `initializeProject` chamado com args corretos
- `test_create_project_api_error_shows_message`: mock `initializeProject` rejeitando => mensagem de erro visivel
- `test_navigates_to_llm_step_after_project`: apos criar projeto com sucesso => mostra "Configure o assistente"

**Step 2 - Variante B (replay, projetos existem):**

- `test_shows_existing_projects_on_replay`: quando `projects` passado como prop com items inicializados => mostra cards com check verde
- `test_continue_without_creating_project_on_replay`: click "Continuar" sem criar nada => avanca para step 3, nenhuma chamada de API
- `test_expand_create_form_on_replay`: click "+ Criar novo projeto" => formulario expande, botao muda para "Criar e Continuar"

**Step 3 - LLM keys:**

- `test_skip_llm_completes_onboarding`: click "Pular" => callback `onComplete` chamado
- `test_save_llm_key_and_complete`: preenche key + click "Salvar e Concluir" => `onComplete` chamado, key persistida
- `test_shows_existing_keys_masked_on_replay`: quando keys ja existem em localStorage => campo exibe valor mascarado, "Salvar e Concluir" sem alterar = no-op

Mocks: `vi.mock("../../api")` para `initializeProject`, `listTemplates`, `fetchSetupStatus`, `fetchProjects`.

#### `frontend/src/App.test.tsx` (adicao)

Adicionar cenarios ao arquivo existente:

- `test_shows_onboarding_when_no_projects`: mock `fetchProjects` retornando `[]`, `fetchSetupStatus` retornando `onboarding_suggested: true` => wizard visivel, dashboard oculto
- `test_shows_dashboard_when_projects_exist`: mock `fetchProjects` retornando projetos, `fetchSetupStatus` retornando `onboarding_suggested: false` => dashboard visivel, wizard oculto
- `test_shows_dashboard_after_onboarding_complete`: mock `fetchSetupStatus` retornando `onboarding_suggested: true`, mas `localStorage` tem `atlasfile-onboarding-done: "true"` => dashboard visivel (belt-and-suspenders: backend diz sim, localStorage diz ja feito, confia no backend que tera projetos)
- `test_onboarding_complete_transitions_to_dashboard`: simular callback onComplete do wizard => dashboard aparece, fetchProjects re-chamado
- `test_replay_onboarding_button_visible_in_dev`: mock `fetchSetupStatus` com `app_env: "dev"` + projetos existentes => botao "Replay Onboarding" visivel
- `test_replay_onboarding_button_hidden_in_prod`: mock `fetchSetupStatus` com `app_env: "production"` => botao nao renderizado

Mocks: adicionar `fetchSetupStatus` ao bloco `vi.mock("./api")` existente.

---

## Resumo de Arquivos


| Acao       | Arquivo                                                       |
| ---------- | ------------------------------------------------------------- |
| Reescrever | `atlasfile_install.sh`                                        |
| Novo       | `frontend/src/features/onboarding/OnboardingWizard.tsx`       |
| Novo       | `frontend/src/features/onboarding/OnboardingWizard.test.tsx`  |
| Novo       | `backend/tests/integration/test_api_setup_status.py`          |
| Novo       | `backend/tests/unit/test_cleanup_orphans.py`                  |
| Editar     | `frontend/src/App.tsx` (condicional de onboarding)            |
| Editar     | `frontend/src/App.test.tsx` (cenarios de onboarding)          |
| Editar     | `frontend/src/api.ts` (novo endpoint)                         |
| Editar     | `frontend/src/api.test.ts` (teste do fetchSetupStatus)        |
| Editar     | `backend/app/main.py` (endpoint `/api/setup/status`)          |
| Editar     | `backend/app/reconcile.py` (funcao `cleanup_orphan_projects`) |
| Editar     | `backend/app/services/reconcile_service.py` (chamar cleanup)  |
| Editar     | `backend/tests/unit/test_reconcile.py` (caso de orphan docs)  |


## Trade-offs

- **PROJECTS_HOST_ROOT nao editavel via UI**: Simplifica muito a v0.3. Mudanca de path e rara e requer restart de container. Futuro: endpoint que reescreve `.env` e chama `docker compose restart`.
- **Cleanup decremental acoplado ao reconcile**: Evita endpoint separado e garante que sempre roda junto. Se quisermos cleanup standalone no futuro, basta extrair para um endpoint proprio.
- **Onboarding flag no localStorage (nao no backend)**: Se o usuario limpar o browser, vera o wizard de novo (mas como ja tera projetos, o backend retorna `onboarding_suggested: false`). Belt-and-suspenders.

