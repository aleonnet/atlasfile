---
name: DOCX pagina-paragrafo
overview: Implementar localização amigável para DOCX no formato Página/Parágrafo com estratégia híbrida (marcadores reais + fallback estimado), preservando comportamento atual de PDF/XLSX/PPTX e minimizando risco de regressão.
todos:
  - id: bench-docx-strategy
    content: Consolidar benchmark local e referências para estratégia híbrida de paginação DOCX
    status: completed
  - id: backend-docx-location
    content: Planejar alteração de _extract_docx para emitir location docx_page/docx_page_est com parágrafo
    status: completed
  - id: frontend-friendly-labels
    content: Planejar parser/labels amigáveis no App.tsx sem impactar agrupamento PDF
    status: completed
  - id: tests-non-regression
    content: Planejar testes backend/frontend cobrindo DOCX novo formato e regressão de PDF
    status: completed
isProject: false
---

# Implementar DOCX com Página/Parágrafo

## Entendimento e objetivo de negócio
- Objetivo: substituir `section:x:y` em DOCX por um localizador compreensível para humano (`Página N / parágrafo M`), aceitando risco controlado quando não houver informação de paginação confiável.
- Restrição: manter intacto o comportamento atual de PDF/XLSX/PPTX e não quebrar ranking/snippets já corrigidos.

## Benchmarkings reais levantados
- **Benchmark local (runtime, pipeline atual):** em DOCX sintético com 2.400 parágrafos e quebras explícitas, o mapeamento de página/parágrafo por inspeção do DOCX adiciona custo baixo (~64.55ms) frente à extração DOCX atual (~1463.08ms), com acurácia 100% quando há marcadores explícitos.
- **Benchmark de detecção python-docx:** `Paragraph.contains_page_break` retornou 0 em DOCX com quebras explícitas (hard page-break), enquanto inspeção XML capturou 29 quebras explícitas; conclusão: para robustez, precisamos ler também `w:br w:type="page"`.
- **Benchmark sem marcadores:** sem `w:br` e sem `w:lastRenderedPageBreak`, cobertura de marcadores foi 0%; sem fallback, toda ocorrência cai na página 1.
- **Benchmark de fallback estimado:** heurísticas de densidade (chars/parágrafos por página) funcionam em alguns perfis, mas têm drift em documentos com variação de layout; portanto devem ser classificadas como **estimadas**.
- **Referências técnicas:**
  - OOXML `lastRenderedPageBreak` é marcador de paginação da última renderização (não garante presença/atualidade): https://ooxml.info/docs/17/17.3/17.3.3/17.3.3.13/
  - python-docx oferece APIs de rendered breaks, mas hard break e rendered break têm semânticas diferentes: https://python-docx.readthedocs.io/en/latest/api/text.html

## Estratégia recomendada (simples e efetiva)
- Estratégia híbrida por confiança para DOCX:
  1. **Confiável:** usar `w:br type="page"` (quebra explícita) e `w:lastRenderedPageBreak` quando existirem.
  2. **Fallback estimado:** quando não houver marcador, inferir página por densidade e marcar como estimada.
- Formato de localização DOCX (string, sem quebrar schema):
  - Confiável: `docx_page:<n>:paragraph:<m>[:part:<k>]`
  - Estimado: `docx_page_est:<n>:paragraph:<m>[:part:<k>]`
- UI converte para label amigável:
  - `docx_page` -> `Página N / Mº parágrafo`
  - `docx_page_est` -> `Página ~N / Mº parágrafo (estimada)`
- Compatibilidade:
  - `page:<n>` de PDF continua igual (agrupamento por página permanece intacto)
  - `sheet/slide` idem
  - `section:*` legado continua suportado para documentos já indexados

## Mudanças por arquivo (mínimas)
- Backend extração DOCX: [`/Users/alessandro/Development/AtlasFile/backend/app/document_extractor.py`](/Users/alessandro/Development/AtlasFile/backend/app/document_extractor.py)
  - Introduzir mapeamento de parágrafo com contador de página/parágrafo por página.
  - Gerar `location` DOCX no novo padrão (confiável/estimado).
- Backend parsing/ordenação de location (se necessário para manter ordenação estável): [`/Users/alessandro/Development/AtlasFile/backend/app/main.py`](/Users/alessandro/Development/AtlasFile/backend/app/main.py)
  - Expandir ordenação para `docx_page`/`docx_page_est` sem alterar prioridade de PDF.
- Frontend formatação de localizações: [`/Users/alessandro/Development/AtlasFile/frontend/src/App.tsx`](/Users/alessandro/Development/AtlasFile/frontend/src/App.tsx)
  - Adicionar parser/formatter para novo padrão DOCX.
  - Manter `pageKeyFromLocation` focado em PDF (`^page:`), evitando regressão no agrupamento.
- Tipos (apenas se adicionar campos auxiliares): [`/Users/alessandro/Development/AtlasFile/frontend/src/types.ts`](/Users/alessandro/Development/AtlasFile/frontend/src/types.ts)

## Testes e critérios de aceite
- Backend unit tests: [`/Users/alessandro/Development/AtlasFile/backend/tests/unit/test_document_extractor.py`](/Users/alessandro/Development/AtlasFile/backend/tests/unit/test_document_extractor.py)
  - DOCX com quebra explícita: validar mapeamento `docx_page` e parágrafo.
  - DOCX sem marcador: validar uso de `docx_page_est`.
- Frontend tests: [`/Users/alessandro/Development/AtlasFile/frontend/src/App.test.tsx`](/Users/alessandro/Development/AtlasFile/frontend/src/App.test.tsx)
  - Label exibido: `Página N / Mº parágrafo`.
  - Sem regressão na exibição de `page:N (X ocorrências)` para PDF.
- Aceite funcional:
  - No exemplo informado, exibir `Página 135 / 1º parágrafo` (ou `~135` se estimado).
  - Não alterar comportamento de PDF/XLSX/PPTX.
  - Sem erro de lint/testes.

## Riscos e mitigação
- Risco principal: DOCX sem marcadores de paginação gera estimativa imperfeita.
- Mitigação: sinalizar explicitamente quando estimado (`~` + sufixo), manter parágrafo determinístico e preservar compatibilidade total com legado.

## Rollout incremental
- Passo 1: suportar leitura/formatação dual (legado + novo) no frontend.
- Passo 2: gerar novo formato no extrator DOCX.
- Passo 3: reindex apenas DOCX alterados via reconcile incremental (sha256).