---
name: Naming Pattern Migration
overview: Plano para tratar a mudanca de canonical_pattern em projetos existentes, com 3 opcoes analisadas (rename automatico, pattern per-file, hibrido) e recomendacao.
todos:
  - id: phase1-index-col
    content: "Fase 1: Adicionar coluna naming_pattern ao _INDEX.md (header + write + parse)"
    status: completed
  - id: phase1-reconcile
    content: "Fase 1: reconcile_project_index usa pattern da row para extract_original_name"
    status: completed
  - id: phase1-ingest
    content: "Fase 1: ingestion.py grava naming_pattern junto com metadados"
    status: completed
  - id: phase1-tests
    content: "Fase 1: Testes unitarios para nova coluna e parsing com pattern misto"
    status: completed
  - id: phase2-plan
    content: "Fase 2 (futuro): Endpoint + UI para migracao de nomes com dry-run/preview"
    status: cancelled
isProject: false
---

# Plano: Migração de Naming Pattern

## Problema

Quando o usuario muda `naming.canonical_pattern` no profile/template, arquivos existentes no disco mantem o formato antigo. Isso causa:

1. **Nomes mistos** no mesmo projeto (antigos e novos com patterns diferentes)
2. **Parsing incorreto** do `original_filename` se `_INDEX.md` for reconstruido (reconcile usa o pattern novo para parsear filenames gerados com o pattern antigo)
3. **Confusao visual** para o usuario

### Arquivos-chave

- [backend/app/utils.py](backend/app/utils.py) -- `build_canonical_filename`, `extract_original_name_from_canonical`
- [backend/app/reconcile.py](backend/app/reconcile.py) -- `_try_migrate_old_format`, `reconcile_project_index` (linhas 175-212)
- [backend/app/ingestion.py](backend/app/ingestion.py) -- usa `naming.canonical_pattern` do profile (linhas 432-445)
- `_INDEX.md` -- colunas atuais: `doc_id | project_id | area | original_filename | canonical_filename | decision | confidence | path`

---

## Opcoes

### Opcao A: Rename automatico ao mudar pattern

Ao salvar um novo `canonical_pattern` no profile, executar uma migracao que renomeia todos os arquivos existentes no disco.

**Fluxo:**

1. Usuario altera `canonical_pattern` no profile e salva
2. Backend calcula o novo nome canonical para cada arquivo usando `original_filename` do `_INDEX.md`
3. Renomeia cada arquivo no disco (com tratamento de colisao)
4. Atualiza `canonical_filename` e `path` no `_INDEX.md`
5. Marca docs alterados para reindex no OpenSearch

**Pros:**

- Estado limpo: todos os arquivos seguem o mesmo pattern
- Parsing reverso sempre funciona
- Experiencia mais intuitiva para o usuario

**Cons:**

- Operacao de I/O pesada em projetos grandes
- Risco de colisao de nomes (dois arquivos gerando o mesmo canonical)
- Requer rollback se algo falhar no meio
- Complexity: precisa de dry-run/preview antes de executar (similar ao layout plan/apply existente)

### Opcao B: Guardar pattern por arquivo no `_INDEX.md`

Adicionar coluna `naming_pattern` ao `_INDEX.md`. Cada arquivo registra o pattern que o gerou. `extract_original_name_from_canonical` usa o pattern da row, nao o do profile.

**Fluxo:**

1. Coluna `naming_pattern` adicionada ao `_INDEX.md`
2. Na ingestao, grava o pattern atual do profile junto com o doc
3. No reconcile/reconstrucao, usa o pattern da row para parsing
4. Arquivos antigos sem a coluna usam fallback: tenta pattern atual, depois legado

**Pros:**

- Zero risco de I/O (nenhum arquivo e movido)
- Parsing reverso sempre correto (cada arquivo sabe seu pattern)
- Simples de implementar (1 coluna nova + ajuste no parser)
- Backward compatible (fallback para pattern antigo)

**Cons:**

- Nomes mistos no disco permanecem para sempre
- `_INDEX.md` fica mais largo (mais uma coluna)
- Nao resolve a confusao visual do usuario

### Opcao C: Hibrida (pattern per-file + migracao opcional)

Combina B + A: guarda pattern por arquivo, mas oferece acao explicita "Migrar nomes" na UI.

**Fluxo:**

1. Implementar Opcao B (pattern per-file) como base
2. Adicionar endpoint `POST /api/projects/{id}/naming/migrate` com dry-run
3. UI: botao "Migrar nomes para pattern atual" na secao Naming do profile
4. Preview mostra: `arquivo_antigo.pdf -> arquivo_novo.pdf` (similar ao layout plan)
5. Confirmar executa o rename + atualiza `_INDEX.md` + reindex

**Pros:**

- Melhor dos dois mundos: seguranca (B) + limpeza sob demanda (A)
- Usuario controla quando/se migrar
- Dry-run previne surpresas
- Reutiliza pattern do layout plan/apply existente

**Cons:**

- Maior esforco de implementacao (B + A + UI de preview)
- Dois fluxos para o usuario entender

---

## Comparativo

- **Seguranca de dados**: B > C > A
- **Consistencia visual no disco**: A > C > B
- **Esforco de implementacao**: B (baixo) < A (medio) < C (alto)
- **Risco operacional**: B (zero) < C (baixo, controlado) < A (medio)
- **Experiencia do usuario**: C > A > B

---

## Recomendacao

**Opcao C (hibrida)**, implementada em 2 fases:

- **Fase 1** (rapida, resolve o parsing): Opcao B -- adicionar `naming_pattern` per-file ao `_INDEX.md` e ao fluxo de reconcile/ingestao. Isso elimina o risco de corrupcao de `original_filename` imediatamente.
- **Fase 2** (posterior): Acao "Migrar nomes" com dry-run/preview e execucao, reutilizando o padrao de plan/apply do layout existente.

### Fase 1 -- Detalhamento

**Arquivos a alterar:**

- `backend/app/reconcile.py`:
  - Header do `_INDEX.md`: adicionar coluna `naming_pattern` apos `canonical_filename`
  - `reconcile_project_index`: gravar `naming_pattern` do profile em cada row
  - Parse de rows existentes: ler `naming_pattern` da row (fallback para `DEFAULT_CANONICAL_PATTERN`)
  - `extract_original_name_from_canonical`: usar o pattern da row, nao o do profile
- `backend/app/ingestion.py`:
  - Gravar `naming_pattern` junto com os demais metadados ao processar inbox
- `backend/tests/unit/test_reconcile.py`:
  - Atualizar testes existentes para nova coluna
  - Novo teste: reconstrucao de `original_filename` com pattern diferente do profile atual
- `backend/tests/unit/test_utils.py`:
  - Teste de `extract_original_name_from_canonical` com patterns diferentes

