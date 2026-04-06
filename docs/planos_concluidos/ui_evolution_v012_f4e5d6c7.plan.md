# Plano: Evolução UI — AtlasFile v0.12.0

**ID:** ui_evolution_v012_f4e5d6c7
**Status:** Concluído
**Data:** 2026-04-06

## Contexto

O frontend (v0.11.0) acumulava dívida em arquitetura de informação: a view "Operacional" misturava operações diárias com configuração rara; "Templates" era view isolada sem relação contextual; IngestTriageCard (1.322 linhas) misturava 5 domínios; App.tsx (1.774 linhas) era monólito.

## Decisões

### Navegação: separar operação de configuração
- **Operacional → Painel**: foco em KPIs, triagem pendente (destaque), scan INBOX, reconcile
- **Templates deixa de ser view top-level** → sub-tab em Configuração
- **Nova view Configuração**: sub-tabs Perfil do projeto, Classificador, Templates
- **Busca (⌘K)**: experiência dedicada, não mais inline na Operacional

### Decomposição de componentes
- IngestTriageCard: triage queue extraída para TriageQueue (standalone no Painel), scan extraído para InboxScanCard, hooks SSE (useIngestMonitor, useClassifierCycleMonitor)
- App.tsx: Topbar, SearchModal, AssistenteView extraídos como componentes

### Refinamentos visuais
- Tipografia: DM Sans como body font (15px), Fragment Mono reservado para dados/código
- Espaçamento: content/cards com mais padding e gap
- Motion: hover elevation em cards, button active feedback, entrance animation
- Componentes: Skeleton (loading shimmer), EmptyState, Toast system (ToastContext)
- Charts: animações Recharts ativadas, gradient background nos containers
- Tabelas: row hover, header normalizado uppercase, zebra striping

### Decisões descartadas
- Sidebar: não justificada para 3 views top-level
- React Router: não necessário para navegação baseada em state
- Context API (extração completa dos 85 useState): adiada — risco elevado para uma única fase

## Arquivos criados

```
src/layouts/Topbar.tsx
src/layouts/SearchModal.tsx
src/views/ConfigView.tsx
src/views/AssistenteView.tsx
src/features/triage/TriageQueue.tsx
src/features/ingest/InboxScanCard.tsx
src/features/ingest/hooks/useIngestMonitor.ts
src/features/ingest/hooks/useClassifierCycleMonitor.ts
src/components/Skeleton.tsx
src/components/EmptyState.tsx
src/contexts/ToastContext.tsx
```

## Verificação

- 94 testes passam (vitest run)
- Build TypeScript limpo (tsc -b)
- Smoke test visual em Docker (container web rebuilded da worktree)
- Dark/light theme sem artefatos
