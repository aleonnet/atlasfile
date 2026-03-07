---
name: Controle operacional + responsividade
overview: Redesenhar o card "Controle operacional" com layout compacto (projetos, docs indexados, extensoes, tabela por projeto, reconciliacao no rodape) e adicionar breakpoint intermediario (~1024px) em toda a aplicacao para eliminar problemas de layout entre 768px e 1200px.
todos:
  - id: backend-stats-project
    content: Adicionar by_project_id na aggregation de GET /api/stats
    status: completed
  - id: frontend-fetch-stats
    content: Garantir fetchStats() em api.ts e adicionar state no App.tsx
    status: completed
  - id: card-redesign
    content: Redesenhar card Controle operacional (metricas + tabela + rodape compacto)
    status: completed
  - id: css-card-classes
    content: Criar classes CSS do novo card (control-body, stat-big, ext-badge, mini-table, reconcile-footer)
    status: completed
  - id: breakpoint-1024-global
    content: Adicionar @media 1024px em styles.css (topbar, kpi-grid, controls select)
    status: completed
  - id: breakpoint-1024-templates
    content: Adicionar @media 1024px em templates.css (tmpl-grid-2, tmpl-grid-3)
    status: completed
  - id: breakpoint-1024-ingest
    content: Adicionar @media 1024px em ingestTriageCard.css (itc-llm-fields)
    status: completed
  - id: breakpoint-1024-chat
    content: Adicionar @media 1024px em ChatPanel.css (toolbar flex-wrap)
    status: completed
  - id: fix-768-deduplicate
    content: Mover regras de topbar-center/search-icon de 768px para 1024px
    status: completed
  - id: tests-update
    content: Atualizar testes backend (stats) e frontend (App card render)
    status: completed
isProject: false
---

# Redesign Controle Operacional + Responsividade Intermediaria

## Contexto

A aplicacao tem apenas 2 breakpoints CSS: 768px (mobile) e 400px (small mobile). Na faixa intermediaria (768-1200px), varios elementos quebram de forma indesejada: o KPI grid gera colunas orfas, a topbar fica apertada, grids de templates ficam estreitos, e a toolbar do chat pode estourar.

---

## Parte 1: Redesign do card "Controle operacional"

### 1.1 Backend: adicionar aggregation `by_project_id` no endpoint `/api/stats`

Em [backend/app/main.py](backend/app/main.py), linha 1127, adicionar ao dict `aggs`:

```python
"by_project_id": {"terms": {"field": "project_id", "size": 100}},
```

E na resposta (linha 1143), incluir:

```python
by_project_id=_buckets("by_project_id"),
```

Atualizar o modelo `StatsResponse` (provavelmente em types ou no mesmo arquivo) para incluir `by_project_id`.

### 1.2 Frontend: chamar `/api/stats` e `/api/setup/status` na view operacional

Em [frontend/src/App.tsx](frontend/src/App.tsx):

- Adicionar state `dashboardStats` e `setupStatus`
- Chamar `fetchStats()` e `fetchSetupStatus()` quando a view for "operacional"
- Usar os dados para popular o novo layout

Em [frontend/src/api.ts](frontend/src/api.ts):

- Adicionar `fetchStats(projectId?: string)` se nao existir, ou verificar se ja existe

### 1.3 Frontend: novo layout do card

Substituir o bloco `kpi-grid` (linhas 1066-1101 do App.tsx) pelo novo layout em 2 colunas:

**Coluna esquerda** (metricas):

- Numero grande: N projetos (com indicador "N inicializados")
- Numero grande: N documentos indexados
- Badges de extensao (PDF 8, DOCX 3, etc.) vindos de `stats.by_extension`

**Coluna direita** (tabela):

- Mini-tabela com doc count por projeto, vinda de `stats.by_project_id`

**Rodape** (linha unica):

- Ultima reconciliacao (data compacta) + Ajustes + Reindexados + Skip + Falhas + Orfaos (quando > 0)

### 1.4 CSS: novas classes para o layout compacto

Em [frontend/src/styles.css](frontend/src/styles.css), substituir `.kpi-grid` / `.kpi` pelo novo layout:

```css
.control-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.control-metrics { display: flex; flex-direction: column; gap: 12px; }
.control-projects { display: flex; flex-direction: column; gap: 0; }

.stat-big { display: flex; align-items: baseline; gap: 8px; }
.stat-big .value { font-size: 1.5rem; font-weight: 700; }
.stat-big .label { font-size: 0.82rem; color: var(--muted); }

.ext-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.ext-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
}

.mini-table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }
.mini-row { display: flex; justify-content: space-between; padding: 6px 12px; font-size: 0.82rem; border-bottom: 1px solid var(--border); }
.mini-row:last-child { border-bottom: none; }
.mini-row.header { background: var(--bg-elevated); font-weight: 600; font-size: 0.75rem; color: var(--muted); }

.reconcile-footer {
  display: flex; gap: 16px; flex-wrap: wrap;
  font-size: 0.78rem; color: var(--muted);
  padding-top: 10px; border-top: 1px solid var(--border); margin-top: 12px;
}
.reconcile-footer .meta-value { color: var(--text); font-weight: 600; }
```

---

## Parte 2: Breakpoint intermediario global (~1024px)

Adicionar um novo `@media (max-width: 1024px)` em [frontend/src/styles.css](frontend/src/styles.css) ANTES do breakpoint 768px existente. Este breakpoint cobre a faixa intermediaria (tablets landscape, janelas redimensionadas).

### 2.1 Topbar

```css
@media (max-width: 1024px) {
  .topbar-center { display: none; }
  .topbar-search-icon { display: grid; }
  .topbar-nav .view-tab-label { display: none; }
}
```

Esconder a search bar inline e os labels das tabs (manter so icones) libera espaco. O icone de busca ja existe para mobile; reutiliza-lo aqui.

### 2.2 KPI grid (legado, se mantido em outros lugares)

```css
@media (max-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
```

### 2.3 Novo card Controle operacional

```css
@media (max-width: 1024px) {
  .control-body { grid-template-columns: 1fr; }
}
```

### 2.4 Templates grids

Em [frontend/src/features/templates/templates.css](frontend/src/features/templates/templates.css):

```css
@media (max-width: 1024px) {
  .tmpl-grid-3 { grid-template-columns: 1fr 1fr; }
  .tmpl-grid-2 { grid-template-columns: 1fr; }
}
```

### 2.5 IngestTriageCard

Em [frontend/src/features/ingest/ingestTriageCard.css](frontend/src/features/ingest/ingestTriageCard.css):

```css
@media (max-width: 1024px) {
  .itc-llm-fields { grid-template-columns: 1fr; }
}
```

### 2.6 ChatPanel toolbar

Em [frontend/src/components/ChatPanel.css](frontend/src/components/ChatPanel.css):

```css
@media (max-width: 1024px) {
  .chat-panel-toolbar { flex-wrap: wrap; }
}
```

### 2.7 Controls select

```css
@media (max-width: 1024px) {
  .controls select { min-width: 140px; }
}
```

---

## Parte 3: Mover breakpoint de `.topbar-center` para 1024px

Atualmente `.topbar-center { display: none }` esta no breakpoint 768px. Mover para 1024px e manter o resto do 768px inalterado. Isso resolve o problema do header-search-card com `min-width: 280px` competindo por espaco em telas intermediarias.

No breakpoint 768px existente, remover as regras de `.topbar-center` e `.topbar-search-icon` que ja estarao no 1024px.

---

## Arquivos a alterar


| Arquivo                                             | Mudanca                                                      |
| --------------------------------------------------- | ------------------------------------------------------------ |
| `backend/app/main.py`                               | Adicionar `by_project_id` na aggregation de `/api/stats`     |
| `frontend/src/api.ts`                               | Garantir que `fetchStats()` existe e retorna `by_project_id` |
| `frontend/src/App.tsx`                              | Redesenhar card Controle operacional + carregar stats        |
| `frontend/src/styles.css`                           | Novas classes do card + breakpoint 1024px + ajuste 768px     |
| `frontend/src/features/templates/templates.css`     | Breakpoint 1024px para grids                                 |
| `frontend/src/features/ingest/ingestTriageCard.css` | Breakpoint 1024px para llm-fields                            |
| `frontend/src/components/ChatPanel.css`             | Breakpoint 1024px para toolbar                               |


## Testes

- Testes existentes do endpoint `/api/stats` verificam aggregations; adicionar check de `by_project_id`
- Testes de `App.test.tsx` verificam render do card operacional; atualizar para novo layout
- Testes visuais manuais: verificar em 1024px, 900px, 768px, 400px

