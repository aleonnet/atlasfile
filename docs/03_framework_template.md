# Template de framework por projeto

## Estrutura de um projeto

```text
/<PROJETO>/
├── _INBOX_DROP/                         # Ponto de entrada de documentos
├── _TRIAGE_REVIEW/
│   ├── pending/                         # Aguardando decisão humana
│   ├── resolved/                        # Aprovados/corrigidos
│   └── rejected/                        # Rejeitados
├── _PROFILE/
│   ├── profile.json                     # Profile V2 (JSON) — schema completo
│   ├── ingest_history.json              # Histórico de ingestões (FIFO, cap 50)
│   └── history/                         # Versões anteriores do profile
├── 01_contratos_comunicacao/            # Áreas de trabalho (JD numbering)
├── 02_financeiro/
├── ...
├── 09_entregaveis/
└── _INDEX.md                            # Registro local de documentos ingeridos
```

## Princípios

- Cada projeto define suas áreas, regras e políticas no `_PROFILE/profile.json` (Profile V2, JSON).
- Templates globais em `config/templates/` servem de base para inicialização de novos projetos.
- Áreas de trabalho ficam na raiz do projeto com prefixo JD (`NN_area_key`).
- Triagem humana ocorre no frontend, não por navegação manual em pasta.
- `_INDEX.md` mantém rastreabilidade local (nome original → canônico → SHA256).

## Ciclo de ingestão

1. Arquivo entra em `_INBOX_DROP`.
2. Dedup por SHA256 — se já existe, registra e remove da inbox.
3. Routing rules verificam path e filename (word boundary matching).
4. Alias scoring calcula confiança por área (sqrt normalization).
5. LLM (se habilitado) enriquece: area override, tags, document_type, topics.
6. Alta confiança (>= `auto_route_min`): move para `NN_<area>/`.
7. Baixa confiança: move para `_TRIAGE_REVIEW/pending`.
8. Humano decide no frontend: `Approve`, `Correct` ou `Reject`.
9. Documento indexado no OpenSearch com metadados completos.

## Inicialização de projeto

Via UI (seletor de projetos → template) ou via script:

```bash
python3 scripts/bootstrap_project.py --name "meu_projeto" --id "meu_projeto"
```

O template define: áreas de trabalho, routing rules, confidence thresholds, LLM policy e configuração de indexação.
