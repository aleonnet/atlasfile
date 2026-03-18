# Template de framework por projeto

## Estrutura de um projeto na 0.7.0

```text
/<PROJETO>/
├── _INBOX_DROP/                         # Entrada de novos documentos
├── _TRIAGE_REVIEW/
│   ├── pending/                         # Aguardando decisao humana
│   ├── resolved/                        # Aprovados/corrigidos
│   └── rejected/                        # Rejeitados
├── _PROFILE/
│   ├── profile.json                     # Profile V2
│   ├── ingest_history.json              # Historico das ultimas ingestoes
│   └── history/                         # Versoes anteriores do profile
├── 01_PROJECTS/
├── 02_AREAS/
│   ├── juridico/
│   │   ├── contrato/
│   │   ├── aditivo/
│   │   └── parecer/
│   ├── financeiro/
│   │   ├── planilha/
│   │   └── relatorio/
│   └── suprimentos/
│       └── edital/
├── 03_RESOURCES/
├── 04_ARCHIVE/
└── _INDEX.md                            # Registro local de documentos ingeridos
```

## Principios

- Cada projeto nasce de um template em `config/templates/` e materializa seu contrato em `_PROFILE/profile.json`.
- O eixo funcional e `business_domain`; o eixo formal e `document_type`.
- O destino fisico padrao de ingestao automatica e `02_AREAS/<business_domain>/<document_type>/`.
- `01_PROJECTS`, `03_RESOURCES` e `04_ARCHIVE` continuam existindo como roots PARA e entram no reconcile e na indexacao.
- `_INDEX.md` e o indice OpenSearch, em conjunto, preservam a rastreabilidade minima: nome original, nome canonico, path e SHA256.
- Triagem humana ocorre via frontend; o filesystem reflete o resultado da decisao.

## Ciclo de ingestao atual

1. Arquivo entra em `_INBOX_DROP`.
2. O sistema calcula SHA256 e elimina duplicatas precocemente.
3. O bootstrap detecta `document_type`.
4. O bootstrap extrai entidades deterministicas.
5. O bootstrap classifica `business_domain`.
6. O sistema deriva `topics` e calcula a confidence final.
7. Se atingir `auto_route_min`, move para `02_AREAS/<business_domain>/<document_type>/`.
8. Se nao atingir, move para `_TRIAGE_REVIEW/pending`.
9. O humano decide `Approve`, `Correct` ou `Reject`.
10. O documento e indexado no OpenSearch e registrado no `_INDEX.md`.

## Papel do template

O template define:

- roots PARA
- `business_domains`
- `document_types`
- thresholds de auto-route/triagem
- naming canonico
- configuracao de extracao
- politica opcional de LLM

`routing_rules` continuam suportadas no schema, mas nao sao pre-requisito do fluxo operacional atual.

## Inicializacao de projeto

Via UI ou via script:

```bash
python3 scripts/bootstrap_project.py --name "meu_projeto" --id "meu_projeto"
```

Ao inicializar, o sistema copia o template escolhido e cria a estrutura fisica do projeto. A partir dai, toda ingestao passa a obedecer ao `profile.json` local do projeto.
