# Scripts e Operações do AtlasFile

Esta página consolida os scripts do repositório e explica, de forma operacional, o que cada um faz, quando usar, pré-requisitos, entrada/saída e em que etapa do processo ele entra.

## Visão rápida por etapa

| Etapa | Scripts principais |
|---|---|
| Instalação e desinstalação da máquina | `install.sh` (macOS/Linux), `install.ps1` (Windows/WSL2) |
| Bootstrap do ambiente e projeto | `scripts/bootstrap_project.py`, `scripts/smoke-project-init.sh` |
| Preparação manual de datasets do classificador | `backend/scripts/bootstrap_validation_set.py`, `backend/scripts/backfill_training_pool.py` |
| Benchmark, ciclo e inspeção do classificador | `backend/scripts/benchmark_classification.py`, `backend/scripts/run_classifier_cycle.py`, `backend/scripts/classifier_status.py`, `backend/scripts/trace_classification.py` |
| Operação e manutenção do stack | `scripts/reset-opensearch-index.sh`, `scripts/import-dashboards.sh` |
| Testes e automação técnica | `scripts/ci.sh`, `scripts/e2e_layout_scenarios.py` |

## Instaladores (`install.sh` / `install.ps1`)

São os dois únicos scripts que rodam **antes** de existir um repositório clonado, e por isso vivem na raiz e não em `scripts/`. Ficavam de fora desta página, que se apresenta como a visão consolidada dos scripts do repositório.

| Script | Plataforma | O que faz |
|---|---|---|
| `install.sh` | macOS / Linux | Verifica e (com confirmação) instala Docker e git, clona em `~/AtlasFile`, gera o `.env`, sobe a stack. Idempotente. |
| `install.ps1` | Windows | Prepara o lado Windows (WSL2 + Docker Desktop via winget) e **delega** ao `install.sh` dentro da distro — um instalador real, sem lógica duplicada. |

Modos que não alteram nada: `--doctor` / `-Doctor` (diagnóstico read-only; no Windows cobre os dois lados) e `--dry-run` / `-DryRun` (mostre, não faça). `--uninstall` / `-Uninstall` imprime um plano do que remove e do que preserva, e só age após confirmação — reverte apenas o que o manifesto prova que o instalador criou.

Documentação de uso: [`INSTALL.md`](../INSTALL.md). Lista completa de flags: `install.sh --help` / `install.ps1 -Help`. Bancadas: `tests/installer/run.sh` (bash), `tests/installer/win/run.ps1` (PowerShell) e `tests/installer/check_consistency.py` (paridade entre os dois), todas em `make test-installer`.

## Pré-requisitos gerais

- Docker Desktop ativo para qualquer script que dependa do stack local ou de containers.
- `.env` configurado, em especial `PROJECTS_HOST_ROOT`, para qualquer fluxo operacional do produto.
- Virtualenv do backend para scripts Python que rodam fora do container em `backend/scripts/`.
- Stack local no ar para scripts que chamam API HTTP, OpenSearch ou Dashboards.

## `backend/scripts`

### `backend/scripts/bootstrap_validation_set.py`

- O que faz: copia arquivos reais para o `validation_set` operacional em `_ATLASFILE/classifier/datasets/validation_set/files/` e sincroniza `expected.json`.
- Quando usar: ao montar ou expandir manualmente o conjunto de validação do classificador para benchmark oficial.
- Pré-requisitos: virtualenv do backend; acesso a uma pasta com documentos reais; `CLASSIFIER_DATASETS_ROOT` resolvendo para o root operacional desejado.
- Entrada:
  - argumento posicional `source`: arquivo ou diretório-fonte
  - opcionais `--limit` e `--extensions`
- Saída:
  - arquivos copiados para o dataset operacional
  - atualização de `expected.json`
  - saída em stdout com `staged_files=<n>` e nomes copiados
- Etapa do processo: preparação manual do dataset de validação antes de benchmark/ciclo.

### `backend/scripts/backfill_training_pool.py`

- O que faz: lê `_TRIAGE_REVIEW/resolved` de um projeto, materializa snapshots estáveis no `training_pool` operacional e grava/mescla `records.jsonl`.
- Quando usar: para importar histórico revisado de um projeto já existente ou recompor o `training_pool` a partir de triagens resolvidas.
- Pré-requisitos: virtualenv do backend; projeto AtlasFile já inicializado; metadados em `_TRIAGE_REVIEW/resolved`.
- Entrada:
  - argumento posicional `project_root`
  - opcional `--replace-project-records`
  - opcional `--dry-run`
- Saída:
  - snapshots em `_ATLASFILE/classifier/datasets/training_pool/files/`
  - atualização de `_ATLASFILE/classifier/datasets/training_pool/records.jsonl`
  - resumo JSON em stdout com contagens e itens ignorados
- Etapa do processo: alimentação/migração do dataset supervisionado após revisão humana.

### `backend/scripts/benchmark_classification.py`

- O que faz: executa o benchmark oficial do classificador sobre o dataset operacional, comparando `bootstrap`, `sparse_logreg` e `sparse_linear_svc`.
- Quando usar: para medir desempenho atual, validar gates do supervisionado e inspecionar integridade/manifests antes de promover mudança no classificador.
- Pré-requisitos: virtualenv do backend; `validation_set` rotulado; `training_pool` operacional disponível para modos supervisionados.
- Entrada:
  - opcional `--mode` (`bootstrap`, `sparse_logreg`, `sparse_linear_svc`, `all`)
  - opcional `--profile`
  - opcionais `--min-training-docs`, `--min-docs-per-class`
  - opcional `--json`
- Saída:
  - texto resumido ou payload JSON com `dataset_integrity`, `dataset_manifest`, gates e benchmarks
  - código `2` se houver erro de integridade no dataset
- Etapa do processo: avaliação oficial do classificador e gate de qualidade do ciclo ML.

### `backend/scripts/run_classifier_cycle.py`

- O que faz: executa o ciclo oficial de benchmark + treino + promoção do classificador.
- Quando usar: para rodar o ciclo operacional completo de ML quando o dataset já estiver preparado.
- Pré-requisitos: virtualenv do backend; datasets operacionais válidos; root `_ATLASFILE` acessível.
- Entrada:
  - opcional `--profile`
  - opcionais `--min-training-docs`, `--min-docs-per-class`
- Saída:
  - payload JSON do ciclo em stdout
  - atualização de reports, models e `registry` em `_ATLASFILE/classifier/`
- Etapa do processo: operação de retreino/promoção do classificador.

### `backend/scripts/classifier_status.py`

- O que faz: imprime o estado atual do registry do classificador e o resumo do último report.
- Quando usar: para inspeção rápida do estado operacional sem abrir a UI.
- Pré-requisitos: virtualenv do backend; root `_ATLASFILE/classifier/` acessível.
- Entrada: sem argumentos.
- Saída:
  - JSON em stdout com `registry`, `latest_report_summary` e `latest_report_id`
- Etapa do processo: observabilidade/diagnóstico do classificador em operação.

### `backend/scripts/trace_classification.py`

- O que faz: trace completo do bootstrap para UM arquivo contra UM projeto — caminho vencedor do document_type (e a conta do √N no caminho alias), e por domínio: aliases carregados, filtrados por colisão de léxico, hits por campo (filename/texto/entidades), overlap com o tipo (pontuado ou ignorado pela regra de conteúdo, v0.44.0), score e a conta da confiança; fecha com o `classify_bootstrap` real como cross-check.
- Quando usar: sempre que uma classificação "não fizer sentido" — antes de mexer em alias, threshold ou scoring (zero trial-and-error). Foi a ferramenta que diagnosticou o caso do kit marítimo (v0.44.0).
- Pré-requisitos: virtualenv do backend; profile do projeto acessível; arquivo legível pelo extrator.
- Entrada:
  - obrigatórios `--project-root` e `--file`
  - opcional `--json` (resultado bruto ao final)
- Saída: relatório legível em stdout com os hits por domínio e a decomposição da confiança.
- Etapa do processo: diagnóstico de classificação em operação e em E2E.

## `scripts`

### `scripts/bootstrap_project.py`

- O que faz: inicializa um projeto AtlasFile pela CLI usando os mesmos módulos do backend/API.
- Quando usar: para criar projeto fora da UI, em automação local ou setup assistido.
- Pré-requisitos: Python local com dependências do backend resolvidas; `PROJECTS_HOST_ROOT` ou `--projects-root`.
- Entrada:
  - obrigatório `--name`
  - opcionais `--id`, `--label`, `--template`, `--projects-root`
- Saída:
  - cria estrutura física do projeto
  - gera `profile.json` e histórico
  - imprime confirmação em stdout
- Etapa do processo: bootstrap de projeto.

### `scripts/smoke-project-init.sh`

- O que faz: executa um smoke curto pós-rebuild validando template, `initialize`, endpoint de profile e estrutura mínima de pastas.
- Quando usar: após `make docker-update` ou quando quiser checar se o stack sobe e inicializa projetos corretamente.
- Pré-requisitos: Docker ativo; containers `api` e demais serviços acessíveis; API respondendo em `http://localhost:8000` ou via env correspondente.
- Entrada:
  - usa variáveis opcionais `ATLASFILE_SMOKE_API_URL`, `ATLASFILE_SMOKE_API_CONTAINER`, `ATLASFILE_SMOKE_PROJECTS_ROOT`
- Saída:
  - logs de validação no terminal
  - código de erro se qualquer etapa falhar
- Etapa do processo: validação técnica pós-build/pós-deploy local.

### `scripts/reset-opensearch-index.sh`

- O que faz: remove os índices do OpenSearch para que o backend os recrie com mapping atualizado.
- Quando usar: após mudança de mapping, reset controlado de ambiente ou limpeza local de documentos/chat.
- Pré-requisitos: OpenSearch local acessível; credenciais válidas.
- Entrada:
  - opcional `chat`
  - opcional `all`
  - default: índice de documentos
- Saída:
  - chamadas `DELETE` no OpenSearch
  - logs no terminal
- Etapa do processo: manutenção operacional de busca/índices.

### `scripts/import-dashboards.sh`

- O que faz: importa o arquivo NDJSON de saved objects no OpenSearch Dashboards.
- Quando usar: depois de subir o stack, para disponibilizar dashboard programático local.
- Pré-requisitos: Dashboards acessível; arquivo NDJSON disponível; credenciais válidas.
- Entrada:
  - opcional caminho do arquivo `.ndjson`
  - variáveis opcionais `DASHBOARDS_URL`, `DASHBOARDS_USER`, `DASHBOARDS_PASSWORD`
- Saída:
  - import dos saved objects
  - link final para abrir o dashboard
- Etapa do processo: setup de observabilidade.

### `scripts/ci.sh`

- O que faz: roda a suíte backend + frontend em sequência.
- Quando usar: como atalho local para validação rápida antes de commit ou rebuild.
- Pré-requisitos: Python/virtualenv do backend; dependências do frontend instaladas.
- Entrada: sem argumentos.
- Saída:
  - logs de testes backend e frontend
  - exit code diferente de zero se qualquer suíte falhar
- Etapa do processo: automação técnica de validação.

### `scripts/e2e_layout_scenarios.py`

- O que faz: executa cenários E2E de migração/layout contra a API Docker ao vivo, incluindo plan/apply e verificação de paths no container.
- Quando usar: ao validar mudanças no fluxo de layout de pastas e migração estrutural de projetos.
- Pré-requisitos: stack local no ar; container `atlasfile-api` disponível; Docker CLI funcional.
- Entrada: sem argumentos formais; usa `http://localhost:8000` e interage diretamente com `docker exec`.
- Saída:
  - relatório de cenários `PASS/FAIL` no terminal
  - exit code diferente de zero em caso de falha
- Etapa do processo: teste técnico específico de layout, não operação rotineira do usuário final.

## Fluxo operacional e scripts

```text
1. Criar projeto
   -> scripts/bootstrap_project.py

2. Subir/revalidar stack
   -> make docker-update
   -> scripts/smoke-project-init.sh

3. Operar ingestão e triagem
   -> UI / API
   -> triagem alimenta training_pool operacional automaticamente

4. Preparar datasets manualmente quando necessário
   -> backend/scripts/bootstrap_validation_set.py
   -> backend/scripts/backfill_training_pool.py

5. Medir e evoluir o classificador
   -> backend/scripts/benchmark_classification.py
   -> backend/scripts/run_classifier_cycle.py
   -> backend/scripts/classifier_status.py

6. Manutenção e observabilidade
   -> scripts/reset-opensearch-index.sh
   -> scripts/import-dashboards.sh
   -> scripts/ci.sh
```

## Referências cruzadas

- `INSTALL.md`: setup do zero, bootstrap do stack e uso inicial.
- `docs/10_classifier_design.md`: contrato operacional do classificador e ciclo ML.
- `README.md`: visão geral do monorepo e do runtime.
