---
name: ML ciclo e benchmarking
overview: Esclarecimento factual do benchmark atual (modo baseline vs bootstrap, métricas e produção) e plano incremental para evoluir a 0.7.x com ciclo de ingestão rotineiro, retreinamento e promoção controlada do melhor modelo — sem alterar código até aprovação explícita.
todos:
  - id: doc-baseline-metrics
    content: Documentar limitação das métricas document_type/exact para modo baseline (ou métrica só domínio) em docs/10_classifier_design.md + README após aprovação
    status: completed
  - id: classifier-manifest-api
    content: Definir manifest (active mode, artefato, hashes pool/validation) e endpoint/CLI de leitura após aprovação
    status: completed
  - id: persist-train-job
    content: Persistir pipeline sklearn + job de retreino/avaliação/promoção com gates explícitos após aprovação
    status: completed
  - id: ingestion-schedule
    content: Alinhar rotina de ingestão (cron/job) com observabilidade e alertas conforme ambiente de deploy após aprovação
    status: completed
isProject: false
---

# Benchmark atual, baseline e evolução para ciclo ML

## Entendimento do que você pediu

1. Confirmar se a arquitetura de benchmarking descrita é a **real no repositório** e o que significa **“fontes verificadas”**.
2. Esclarecer o que é `**baseline`** no script e se faz sentido manter, dado que historicamente a ênfase era `**area_key`**.
3. Explicar **como o usuário sabe** qual classificador está em uso e se o sistema **“aprende”** de forma automática.
4. Traçar direção para **evoluir a 0.7.x** com rotina de ingestão + retreinamento + promoção automática do melhor modelo (escopo de produto; execução de código só após sua aprovação explícita).

---

## Fatos verificados no código

### Onde o benchmark roda e o que compara

- Script canônico: `[backend/scripts/benchmark_classification.py](backend/scripts/benchmark_classification.py)`.
- **Ground truth**: entradas rotuladas em `[config/validation_set/expected.json](config/validation_set/expected.json)` (`business_domain`, `document_type`).
- **Modos**:
  - `**baseline`**: chama `classify()` de `[backend/app/ingestion.py](backend/app/ingestion.py)` (classificador legado por `routing_rules` + alias scoring em `work_areas`). A predição de domínio no benchmark é `legacy_map.get(area_key, area_key)` com mapa opcional `--legacy-area-map` (default `config/validation_set/legacy_area_to_business_domain.json` — **arquivo pode não existir**; nesse caso o mapa é vazio e usa-se o `area_key` cru).
  - `**bootstrap`**: chama `classify_bootstrap()` de `[backend/app/classification_bootstrap.py](backend/app/classification_bootstrap.py)` — **classificador operacional documentado**.
  - `**sparse_logreg` / `sparse_linear_svc`**: TF-IDF char n-grams + `LogisticRegression` / `LinearSVC` treinados só **em memória** no script, usando textos de `[config/training_pool/records.jsonl](config/training_pool/records.jsonl)`; **não há artefato de modelo persistido nem uso em produção**.
- **Gates**: disjunção `validation_set` ↔ `training_pool` via `compute_dataset_integrity`; overlap por SHA-256 → saída com código 2 e benchmarks vazios; gate supervisionado com mínimos (`_SPARSE_MIN_TRAINING_DOCS` = **100**, `_SPARSE_MIN_DOCS_PER_CLASS` = **5** por padrão).

### Por que `baseline` tem `document_type_accuracy` baixo ou zero

- `**classify()` legado** retorna, nos fluxos normais, apenas `area_key`, `confidence`, `reason`, `top_candidates` — **não define `document_type`** (`[ingestion.py` `classify`, ~linhas 109–144](backend/app/ingestion.py)).
- No benchmark, `_baseline_predict` faz `predicted_type = str(result.get("document_type") or "").strip()` → na prática **string vazia** → comparação com `expected_document_type` quase sempre errada → `**document_type_accuracy` e `exact_match_accuracy` do modo baseline não medem um “classificador de tipo legado”; medem um legado que não produz tipo nesse contrato** (**fato verificado**).

Conclusão sobre sua memória: **faz sentido** lembrar que o legado é **centrado em `area_key`**. O benchmark **força o mesmo eixo de avaliação** que o resto do sistema (`business_domain` + `document_type`): domínio é aproximado via `area_key` (+ mapa legado opcional); tipo é, para o legado, **artefato da métrica**, não capacidade real do legado.

**Manter `baseline`?** Documentação já posiciona como **referência histórica**, não produção (`[docs/10_classifier_design.md](docs/10_classifier_design.md)`, `[CHANGELOG.md](CHANGELOG.md)`). **Recomendação**: manter para regressão/comparável “antes vs depois”, mas **documentar explicitamente** que métricas de tipo/exato no `baseline` são **não informativas** até o legado passar a emitir `document_type` ou até o benchmark passar a reportar **só acurácia de domínio** para esse modo (**inferência de produto**: segunda opção evita confusão operacional).

### O que roda em produção na ingestão

- Fluxo de ingestão usa `**classify_bootstrap`**, não `classify` legado (`[ingestion.py` ~413](backend/app/ingestion.py)).
- O JSON do benchmark inclui `"operational_classifier_mode": "bootstrap"` **fixo** no payload (`[benchmark_classification.py` ~621–626](backend/scripts/benchmark_classification.py)) — reflete o desenho atual, não um switch dinâmico lido de config.

### “Aprendizado” e `training_pool`

- **Não há retreinamento nem promoção automática** no runtime: `[docs/10_classifier_design.md](docs/10_classifier_design.md)` e `[CHANGELOG.md](CHANGELOG.md)` dizem explicitamente que `sparse`_* são candidatos de benchmark e promoção é manual.
- **Dados para um futuro supervisionado**: em triagem, `approve` / `correct` chamam `append_training_pool_record` (`[main.py](backend/app/main.py)` ~2155–2167) — ou seja, há **acúmulo de rótulos revisados**, mas isso **não altera** o classificador em produção até existir pipeline de treino/persistência/promoção.

### Visibilidade para o usuário final

- Busca rápida no frontend: **sem** referências a `bootstrap`, `benchmark` ou `training_pool` — **não há UI dedicada** ao modo de classificador ou ao ciclo ML (**fato verificado** no repo para o escopo pesquisado).
- O usuário técnico pode inferir uso do bootstrap pela documentação/README e rodar o script; **não há endpoint** que exponha “versão do modelo supervisionado” ou “último benchmark”, além do que já existir em metadados de documento (confidence, reasons, etc.).

### Sobre “fontes verificadas” vs números (0.40, 0.60, …)

- `**[docs/01_benchmarking.md](docs/01_benchmarking.md)`** lista referências externas (NARA, ISO, OpenSearch/BM25, artigos sobre classificação linear esparsa, etc.) para **justificar decisões de arquitetura** — **não** são citações que “provam” um único número de acurácia do seu ambiente.
- Números concretos dependem de **execução local** com o `expected.json` e `training_pool` atuais; o repositório registra exemplos em `[docs/plano_teste_e2e_v0.7.0.md](docs/plano_teste_e2e_v0.7.0.md)` que **diferem** dos valores que você citou do chat anterior → **os números do chat não são artefato versionado**; só são válidos após **reproduzir** `python backend/scripts/benchmark_classification.py --mode all --json` no seu checkout (**limitação / fato**).

---

## Objetivo de negócio (implícito)

Ter **ciclo fechado**: dados entram → rótulos/confiança → (opcional) retreino → decisão mensurável → **promoção só com gate** (sem IA como decisor sozinho: humano ou política explícita aprova promoção).

---

## Alternativas de desenho (alto nível)


| Abordagem                                                                                  | Prós                                 | Contras                                |
| ------------------------------------------------------------------------------------------ | ------------------------------------ | -------------------------------------- |
| **A) Manter hoje + relatórios**                                                            | Baixo risco; zero mudança de runtime | Sem “evolução” automática percebida    |
| **B) Treino offline + promoção manual** (artefato versionado, flag em config)              | Reversível; auditável                | Exige disciplina operacional           |
| **C) Pipeline agendado + promoção automática com gates** (validação + limiares + rollback) | Escala operacional                   | Mais engenharia, risco se gates fracos |


**Recomendação incremental**: **B → C**: primeiro persistir modelo + metadata + endpoint/CLI “modo ativo”; depois automatizar job com **mesmos gates do benchmark** + exigência de **não regressão** frente ao bootstrap em métricas acordadas.

---

## Plano de implementação (após sua aprovação explícita)

1. **Contrato e observabilidade**
  - Definir fonte da verdade: ex. `config/classifier_active.json` ou variável de ambiente + versão/hash do `training_pool` e do `validation_set`.
  - Expor em API (e opcionalmente UI): `active_classifier`, `last_benchmark_at`, `last_promotion_decision`, métricas resumidas.
2. **Persistência do supervisionado**
  - Salvar `sklearn` `Pipeline` (joblib) por família + manifest (versão sklearn, contagem de amostras, checksum do pool).
  - Carregar em worker apenas se flag ativa; fallback **sempre** para `classify_bootstrap` se arquivo inválido ou gate falhar.
3. **Rotina de ingestão**
  - Se “rotina” = agendamento: job/cron que processa inbox (já existente no produto) com métricas e alertas; alinhar com documentação de deploy (Docker/Makefile).
  - Garantir que `training_pool` continue alimentado só por **revisão humana** (já é o caso) ou explicitar política se quiser auto-rótulo.
4. **Retreinamento**
  - Script ou job: validar integridade → treinar `sparse`_* → avaliar no `validation_set` → comparar com bootstrap → registrar JSON de decisão.
  - Testes: unitários para gates + integração mínima com fixture pequena (padrão já em `[test_benchmark_classification.py](backend/tests/unit/test_benchmark_classification.py)`).
5. **Promoção automática “do melhor modelo”**
  - Política explícita: ex. exigir `exact_match_accuracy` (ou composto) **≥** bootstrap + margem mínima + `dataset_integrity == ok`.
  - **Nunca** promover sem validação em holdout; opcional: aprovação humana em fila para o primeiro ciclo.
6. **Documentação**
  - Atualizar `[docs/10_classifier_design.md](docs/10_classifier_design.md)`, README e `[docs/07_rollout_kpis.md](docs/07_rollout_kpis.md)` com: significado do `baseline`, limitação de métricas de tipo, e fluxo de promoção.

**Arquivos centrais a tocar** (quando autorizado): `[backend/scripts/benchmark_classification.py](backend/scripts/benchmark_classification.py)`, `[backend/app/ingestion.py](backend/app/ingestion.py)`, `[backend/app/classification_bootstrap.py](backend/app/classification_bootstrap.py)` ou um novo módulo fino `classifier_runtime.py`, `[backend/app/main.py](backend/app/main.py)`, possivelmente `[backend/app/models.py](backend/app/models.py)`, configs em `config/`, e frontend se quiser visibilidade.

---

## Grau de certeza (resumo)


| Afirmação                                                                     | Certeza                                 |
| ----------------------------------------------------------------------------- | --------------------------------------- |
| Produção usa `classify_bootstrap` na ingestão                                 | **Verificado no código**                |
| `baseline` no benchmark = `classify()` legado; tipo previsto vazio na prática | **Verificado no código**                |
| `sparse`_* só no script; sem promoção automática hoje                         | **Verificado no código + docs**         |
| Números 0.40/0.60 do chat = estado versionado do repo                         | **Desconhecido / não reproduzido aqui** |
| Referências em `01_benchmarking.md` sustentam desenho, não um run específico  | **Verificado na leitura do doc**        |


