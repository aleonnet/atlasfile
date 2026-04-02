# Plano Concluído: Classificação 4 modos + Pipeline de dados — v0.9.0

**Versão:** 0.9.0
**Período:** 2026-03-28 → 2026-04-02
**Commit anterior:** `663edd8` (v0.8.1)

---

## Resumo

Reestruturação completa da pipeline de dados do classificador (eliminação de data leakage, corpus unificado, splits estratificados). Expansão do stack de classificação de 3 para 4 modos com benchmark card definitivo. Fundamentação metodológica SOTA documentada. Frontend redesenhado com barras de progresso SSE, cancelamento de ciclo, herança de métricas e sync do modelo de triagem.

---

## 1. Análise Comparativa SOTA vs AtlasFile

### Schema de classificação

O AtlasFile classifica documentos em dois eixos independentes:
- **`business_domain`** (11 valores): societario, juridico, ativos, financeiro, fiscal, pessoas, ti, operacoes, regulatorio, compliance, suprimentos
- **`document_type`** (14 valores): contrato, aditivo, fato_relevante, parecer, procuracao, ata, relatorio, especificacao, edital, plano, apresentacao, planilha, email, nota_fiscal

Complementados por `topics` (74 valores) e `entities` (6 tipos: cnpj, email, contrato, valor, projeto, empresa).

### Validação contra standards
- **ISO 15489** (Records Management): classificação por funções de negócio (não organograma) — o eixo `business_domain` segue este princípio.
- **NARA (US National Archives)**: functional classification scheme com hierarquia função → atividade → transação — compatível com `business_domain → document_type`.
- **FAIR Data Principles**: metadata captura contexto, conteúdo e estrutura — AtlasFile preserva `entities`, `topics`, `correspondent`, `original_filename`.

### Métrica primária: F1-macro vs accuracy

Com 14 classes e classes minoritárias (`fato_relevante: 2, nota_fiscal: 2`), accuracy simples é enganosa — um modelo que ignora classes raras acerta >90% por dominância das majoritárias. **F1-macro** trata todas as classes com peso igual.

Referências:
- scikit-learn Model Evaluation Guide — Classification metrics
- TACL 2024: "macro-averaged F1 as the primary metric for imbalanced multi-class text classification" (doi:10.1162/tacl_a_00675)

### Critério de promoção: exact_match (não F1-macro)

O AtlasFile usa **exact_match_accuracy** como critério primário. Justificativa operacional: o roteamento para `02_AREAS/{business_domain}/{document_type}` exige que AMBOS os eixos estejam corretos. F1-macro pode premiar modelos que acertam um eixo mas erram o outro.

Lógica em `classifier_cycle.py:882–891`:
```python
key=lambda item: (
    -exact_match_accuracy,     # primário
    -business_domain_accuracy, # desempate 1
    -document_type_accuracy,   # desempate 2
)
```

### Cross-validation

`StratifiedKFold(n_splits=5)` para 258 docs — mantém proporção de classes em cada fold. Implementado em `_cross_validate_sparse()`.

---

## 2. Pipeline de dados — Reestruturação

### Problemas identificados
- 24 SHA256 idênticos em treino e validação (data leakage direto)
- 54 arquivos órfãos sem registro em `records.jsonl`
- 4 convenções de nomeação misturadas (`{doc_id}__`, `tp_`, `tp2_`, numeração VDR)
- Truncamentos sem base empírica: `[:4000]` no bootstrap, `[:8000]` nos supervisionados, `50000` na extração
- Validation set com 11 de 14 tipos abaixo de 15 exemplos (threshold Microsoft Custom Text Classification)

### Solução: corpus consolidado + splits estratificados

**Scripts criados:**

| Script | Linhas | Função |
|--------|--------|--------|
| `build_corpus.py` | 269 | Consolida training_pool + validation_set, dedup SHA256, normaliza filenames, gera `corpus.jsonl` |
| `build_splits.py` | 155 | Particionamento estratificado 70/15/15 via `StratifiedShuffleSplit` |
| `label_corpus_llm.py` | 314 | Rotulagem automática do corpus via LLM (GPT-4o-mini) |
| `inject_training_records.py` | 120 | Injeção manual de registros com verificação SHA256 (anti-leakage) |

**Estrutura resultante:**
```
_ATLASFILE/classifier/datasets/
├── corpus.jsonl               ← fonte única de verdade
├── corpus_files/              ← arquivos com nomes normalizados
└── splits/
    ├── train.jsonl            ← 70% (~258 docs)
    ├── validation.jsonl       ← 15% (~62 docs)
    └── test.jsonl             ← 15%
```

**Corpus:** ~363 documentos únicos (após dedup SHA256 de 401 arquivos), 14 tipos, 11 domínios.

### Metodologia de cobertura (baseada em Microsoft Custom Text Classification)
- Mínimo 15 exemplos rotulados por classe no training set
- Ratio máximo 10:1 entre classe mais e menos representada
- Classes com <2 amostras: excluídas do treino supervisionado mas incluídas com `class_weight="balanced"` e gate warning

### Truncamento fundamentado
- `_MAX_EXTRACT_CHARS`: 50.000 → 20.000 (alinhado ao "Lost in the Middle" ACL 2024 — LLMs perdem informação no meio de contextos longos)
- `extract_feature_text`: truncamento arbitrário `[:4000]` removido — passa texto completo ao modelo
- Impacto direto: bootstrap de ~52% para 87.1% domain accuracy após receber 20k chars

**`evaluation_dataset.py` — novas funções:**
- `splits_available()` — detecta se corpus-based splits existem
- `load_split_as_training_records(split_name)` / `load_split_as_validation_entries(split_name)`
- `resolve_corpus_validation_file(file_name)` — resolve path em `corpus_files/`
- `TrainingPoolRecord.synthetic_text` — campo para dados sintéticos (augmentation)

---

## 3. Classificação — Expansão para 4 modos

### 3a. Bootstrap (campeão)

**Resultado:** 87.1% domain / 93.5% type / 82.3% exact match.

Configuração: aliases do profile + filename + texto integral (20k chars). O fix `extract_feature_text` (remoção do truncamento `[:4000]`) foi decisivo — resultado anterior com 4000 chars: ~52% domain.

### 3b. LLM Classifier (segundo lugar)

**Resultado:** 83.9% domain / 95.2% type / 79.0% exact.

Configuração: gpt-4o-mini (OpenAI), texto integral (20k chars). Nova função `benchmark_llm_candidate()` integrada ao ciclo. Melhor em document_type (95.2%). O único modo sem treino que entende contexto semântico. Custo: ~$0.0001/doc com gpt-4o-mini. F1-macro de domínio (74.4%) inferior ao bootstrap (88.6%) — sensível a classes raras.

### 3c. sparse_logreg (melhorado)

**Resultado:** 58.1% domain / 82.3% type / 50.0% exact.

Mudanças em `classifier_supervised.py`:
- `FeatureUnion` char n-grams (3-5, 50k features) + word n-grams (1-2, 20k features): captura morfologia + semântica
- Gate graduado: classes com ≥2 amostras elegíveis com warning; <2 excluídas sem bloquear treino
- `SPARSE_MIN_DOCS_PER_CLASS`: 5 → 2 (mais permissivo com datasets pequenos)
- `class_weight="balanced"` no `LogisticRegression`
- `LinearSVC` removido dos modos suportados (`SPARSE_MODEL_FAMILIES = ("sparse_logreg",)`)

**Justificativa LogisticRegression vs alternativas:**
- **vs LinearSVC**: LR produz probabilidades calibradas (`predict_proba`) necessárias para o sistema de confiança. LinearSVC não produz probabilidades nativas. Ref: arXiv:2412.21022 (2024)
- **vs XGBoost/tree-based**: TF-IDF gera vetores esparsos de alta dimensão (50k+ features). Trees não escalam bem nesse espaço. Modelos lineares são O(n × d). Ref: scikit-learn docs
- **vs fine-tuned BERT/BERTimbau**: com 258 docs e 11 domínios (~23 docs/domínio), risco alto de overfitting. Literatura recomenda >1000 docs/classe. Ref: arXiv:2412.21022, BERTimbau (Souza et al., 2020)

### 3d. SetFit/ModernBERT (novo)

**Resultado:** 38.7% domain / 82.3% type / 32.3% exact.

**Arquivo:** `classifier_setfit.py` (489 linhas).

**Problema resolvido — OOM:** O código original alimentava todos os textos ao `generate_pairs()` contrastivo (C(n,2) pares em memória). Solução: separar as duas fases do SetFit conforme o paper (Tunstall et al., 2022):

```
Fase 1 (subprocess spawn): contrastive body tuning
  → amostra estratificada: max 16 exemplos/classe (~176 textos)
  → truncagem: 1000 chars (contrastive learning aprende de padrões semânticos)
  → subprocess isolado com timeout 1800s
  → subprocess morre após salvar body tuned

Fase 2 (processo pai): head training
  → encode de TODOS os dados (forward-only, sem gradientes)
  → truncagem: 2000 chars (fase de encode + predict)
  → sklearn head fit nos embeddings
```

**Modelo base:** `nomic-ai/modernbert-embed-base` (8192 tokens, vs 128 do MiniLM-L12-v2).

**Bottleneck de domain accuracy:** truncagem em 2000 chars para Phase 2 + predict. O sinal de domínio nos documentos corporativos está distribuído ao longo do corpo — não apenas nos primeiros 2000 chars. Document_type (82.3%) é competitivo porque o sinal está concentrado nos cabeçalhos/títulos (~500 chars).

**Performance medida em CPU:**
- Phase 1 (contrastive): ~40s
- Phase 2 (encode 258 docs): ~2min

**Gatilho para migrar para BERT/dense:**
- Corpus >1000 docs por classe (hoje: ~23/domínio)
- GPU disponível para encoding sem truncagem
- Performance do bootstrap insuficiente

---

## 4. Ciclo ML — Refatoração

**Mudanças em `classifier_cycle.py` (+649 linhas):**

- `run_classifier_cycle()` aceita `benchmark_enabled_modes: list[str] | None`
- Progresso dinâmico: `progress_total = len(enabled_modes)` (não mais fixo)
- Phases granulares: `"extracting"`, `"baseline:{mode}"`, `"benchmark:{mode}"`
- `_cross_validate_sparse()`: `StratifiedKFold(n_splits=5, min=2)`
- `compute_dataset_integrity`: pula registros com `synthetic_text`
- Cancelamento: `threading.Event` + `InterruptedError` no `progress_callback`
- Herança de métricas: modos pulados preservam valores do ciclo anterior via `load_classifier_report(registry.latest_report_id)`

**Registry (`classifier_registry.py`):**
- `SUPPORTED_CLASSIFIER_MODES` = `("bootstrap", "sparse_logreg", "setfit", "llm")`
- `DEFAULT_BENCHMARK_ENABLED_MODES` = `["bootstrap", "sparse_logreg"]`
- `ClassifierRegistry.benchmark_enabled_modes` — persistido no `registry.json`

**Runtime (`classifier_runtime.py`):**
- Path SetFit: `classifier_models_dir() / "setfit"`
- `artifact_exists` verifica `metadata.json` para SetFit
- Caminho classify SetFit: `load_setfit_artifact()` + `classify_with_setfit_artifact()`

---

## 5. API

**Novos endpoints em `main.py`:**
- `PUT /api/classifier/benchmark-modes` — configurar modos habilitados (validação: pelo menos 1)
- `DELETE /api/classifier/cycle` — cancelar ciclo em andamento (202; 409 se nenhum ativo)
- `DELETE /api/classifier/reports/{report_id}` — excluir relatório (protege campeão: 409; 404 se inexistente)
- `GET /api/classifier/status` — resposta inclui `benchmark_enabled_modes`

---

## 6. Profile, Config e Augmentation

**`profile_schema_v2.py`:**
- `AugmentationConfig(BaseModel)` — configuração de augmentation (enabled, min/max_synthetic_per_class, target_balance_ratio)
- `ProjectProfileV2.classification.augmentation: AugmentationConfig`
- `sparse_linear_svc` removido do enum de modos

**`config.py`:** `classification_augmentation_enabled: bool = False`

**`classifier_augmentation.py`** (novo, 453 linhas):
- Augmentação de dados sintéticos via LLM para classes sub-representadas
- Integração preparada mas não ativada (feature flag desabilitada)

**`config/templates/default.json`:** +38 linhas — `augmentation` config e tipos documentais adicionados.

---

## 7. System Prompt de Classificação

**`system_prompt_classify.md`:**
- Instrução explícita: "Analise o CONTEÚDO do documento, não apenas o nome do arquivo"
- `document_types` do projeto injetados no contexto (antes não era feito)
- `explanation` (justificativa) obrigatória em todos os casos (antes só quando confidence < 0.6)
- Instrução: usar "outro" se nenhum domain/type se encaixar

**`orchestrator.py`:** `_build_project_context()` inclui `document_types` disponíveis no projeto.

---

## 8. Frontend

### Ingestão e triagem (`IngestTriageCard.tsx`)

**Cabeçalho:**
- Removidos campos técnicos opacos (Versão, Última atualização)
- Adicionado contador de pendentes: `taxonomia_e2e_v080 · 2 pendentes`

**Barras de progresso SSE** (padrão visual de Reconciliar INDEX):
- Scan INBOX: barra animada com fase + N/M arquivos + nome do arquivo atual
- Ciclo classificador: mesma barra dentro do colapsável "Classificador operacional"
- Concluído: barra desaparece. Falhou: texto de erro em `var(--danger)`.

**Cancelar ciclo:**
- Botão "Cancelar ciclo" (danger) quando ciclo ativo
- Popover de confirmação (Confirmar/Não)
- Estado "Cancelando..." com `useEffect` auto-reset

**Modos de benchmark:**
- Checkboxes por modo — todos desmarcáveis (inclusive bootstrap)
- Modos pulados esmaecidos (opacity 0.45) com métricas reais do ciclo anterior
- `inherited_from_report_id` no `ClassifierBenchmarkSummary`

**Evolução recente:**
- Tabela compacta: data (dd/mm/aa HH:MM), campeão, exact, bd F1
- Botão delete × (desabilitado para o campeão ativo)
- Até 8 linhas (vs 5 na lista anterior)

**Badges:** accent pill (`var(--accent-soft)`) em "Classificador operacional" e "Processamentos".

**Sync modelo triagem:** combobox bidirecional entre card ITC e modal Configurações via `selectedModelTriage` / `onChangeModelTriage` props.

### Perfil e Organização (`ProfileLayoutWorkspace.tsx`)
- Card renomeado de "Profile & Layout por projeto" para "Perfil e Organização"
- Empty state alinhado ao estilo ITC (mesma fonte/peso)
- Espaçamentos dos colapsáveis alinhados: removido `margin-top: 10px` e `padding-top: 10px` do `.pl-collapsible`

### Outros
- `App.tsx`: topbar scroll listener (`is-opaque`), search modal fecha ao clicar backdrop, `topbar-inner` wrapper
- `styles.css`: ~217 linhas alteradas (topbar, search modal, classifier benchmark UI)
- `api.ts`: `updateBenchmarkEnabledModes()`, `cancelClassifierCycle()`, `deleteClassifierReport()`
- `types.ts`: `inherited_from_report_id?: string | null` em `ClassifierBenchmarkSummary`
- Removido: `frontend/mockup-chat-ui.html`

---

## 9. Benchmark Card Completo

**Relatório:** `cycle_20260401_194500_343482` — 4 modos, mesmo corpus, mesma rodada.
**Corpus:** 258 docs treino / 62 docs validação. 14 tipos, 11 domínios.
**Gate warnings:** `fato_relevante: 2, nota_fiscal: 2` — incluídos com `class_weight="balanced"`.

| Modo | Configuração | bd acc | bd F1 | dt acc | dt F1 | exact | Status |
|------|-------------|:------:|:-----:|:------:|:-----:|:-----:|:------:|
| **bootstrap** | aliases + filename + texto integral (20k chars) | **87.1%** | **88.6%** | 93.5% | 90.6% | **82.3%** | **CAMPEÃO** |
| llm | gpt-4o-mini · texto integral (20k chars) | 83.9% | 74.4% | **95.2%** | **89.4%** | 79.0% | |
| sparse_logreg | TF-IDF FeatureUnion [char_wb(3-5) 50k + word(1-2) 20k] · LR max_iter=3000 · balanced | 58.1% | 52.9% | 82.3% | 74.4% | 50.0% | |
| setfit | modernbert-embed-base · contrastive 1k / head 2k chars · epochs=1 · batch=4 | 38.7% | 21.0% | 82.3% | 73.4% | 32.3% | |

**Critério de promoção:** exact_match (primário) → bd_accuracy (desempate 1) → dt_accuracy (desempate 2).

### Notas de análise

**Bootstrap (87.1% domain, 82.3% exact):** O fix `extract_feature_text` (remoção do truncamento `[:4000]`) foi decisivo. Resultado anterior com 4000 chars: ~52% domain. Com 20.000 chars: 87.1%.

**LLM (83.9% domain, 79.0% exact):** Melhor em document_type (95.2%). Único modo sem treino com entendimento semântico. F1-macro de domínio (74.4%) inferior ao bootstrap (88.6%) — sensível a classes raras.

**sparse_logreg (58.1% domain, 50.0% exact):** FeatureUnion char+word correto para o espaço de features. Corpus de 258 docs / 11 domínios é pequeno demais para separação linear confiável. Gate warning: `fato_relevante` e `nota_fiscal` com 2 exemplos cada.

**SetFit/ModernBERT (38.7% domain, 32.3% exact):** Bottleneck de domain: truncagem em 2000 chars — sinal de domínio distribuído no corpo. Document_type competitivo (82.3%) porque sinal concentrado nos primeiros ~500 chars. Potencial com corpus maior e GPU (sem truncagem).

---

## 10. Testes

**Novos arquivos:**
- `test_classifier_augmentation.py`
- `test_classifier_setfit.py`
- `test_corpus_splits.py`
- `test_inject_training_records.py`

**Modificados:**
- `test_benchmark_classification.py` (+125 linhas): SetFit gate, LLM benchmark, FeatureUnion, cross-validation
- `test_classifier_cycle.py` (+37): modos configuráveis, corpus splits
- `test_classifier_registry.py` (+36): benchmark_enabled_modes
- `test_classifier_runtime.py` (+25): SetFit runtime path
- `test_classify_context.py` (+14): document_types no contexto
- `test_template_store.py` (+1): augmentation config

**Total: 403 backend + 71 frontend = 474 testes** (era 436 na v0.8.1).
