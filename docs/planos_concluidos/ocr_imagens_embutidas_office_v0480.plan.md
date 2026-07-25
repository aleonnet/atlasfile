# OCR de imagens embutidas em Office — docx/pptx/xlsx "envelope" (v0.48.0)

**Concluído em 2026-07-25.** Origem: caso real na instância — DOCX com zero runs de
texto e um único PNG embutido (screenshot de e-mail Outlook com o scan das atas do
RCA) saía como "sem texto extraível", triagem com confiança 0 e Aprovar desabilitado,
sem o sistema jamais tentar OCR (fato verificado: OCR existia só para PDF escaneado
e imagem solta).

## Decisões

- **Gancho no lugar certo, achado durante a implementação**: o plano inicial mirava o
  branch `if not paragraphs:` do `_extract_docx`, mas o coletor registra TODO `<w:p>`
  (mesmo sem `<w:t>`) — um docx com imagem inline tem parágrafos, só que vazios, e
  passaria reto pelo branch. O gancho real é no return final, quando `chunk_rows`
  fica vazio. O branch `not paragraphs` (docx sem nenhum `<w:p>`) também ganhou o
  mesmo tratamento.
- **Escopo ampliado pelo usuário no aprovado**: além de docx/pptx, xlsx (pedido
  mid-implementação: "vale para ppt* e .xls* também"). Fato do dispatch: toda a
  família moderna `.xlsx/.xlsm/.xltx/.xltm` roteia para `_extract_xlsx` — coberta.
  Legados `.doc/.xls/.ppt` são OLE2 (não zip) — fora do alcance, registrados no
  ROADMAP com gatilho.
- **Custo controlado**: OCR embutido SÓ roda quando o documento não tem texto próprio
  (documentos normais não pagam nada — teste garante). Cap de 10 imagens
  (envelopes reais têm 1–3; decks com dezenas de ícones não viram fatura de OCR),
  nunca silencioso: `embedded_images_ocr_capped` no metadata.
- **Mesmo motor, mesmo padrão**: `pytesseract` por+eng (idêntico ao PDF escaneado e
  à imagem solta), status `ok_ocr`/`partial`, locations `image:N`, degradação
  `ocr_unavailable` quando pytesseract falta.
- **Ingestão intocada**: `read_text_excerpt → extract_document_content` — com texto
  vindo do OCR, classificação/LLM/indexação fluem sem nenhuma mudança;
  `sem_texto_extraivel` agora só ocorre quando é factualmente verdade (OCR rodou e
  não achou texto). `embedded_images_found/ocr` no metadata ficam como insumo para a
  UI dizer a causa real (item próprio no ROADMAP).

## Implementação

`backend/app/document_extractor.py`: helper `_ocr_embedded_images(path, media_prefix,
max_chars)` (zip → `word/media/*` | `ppt/media/*` | `xl/media/*` filtrado por
`_IMAGE_EXTS` → PIL via BytesIO → pytesseract; imagem individual que falhar é pulada,
zip ilegível → `zip_error`) + ganchos nos returns de `_extract_docx` (2 caminhos),
`_extract_pptx` e `_extract_xlsx`.

## Validações

- 7 testes novos em `tests/unit/test_embedded_image_ocr.py` com Tesseract REAL
  (padrão da casa de `test_image_extraction.py`, skipif sem binário): envelope
  docx/pptx/xlsx extraem texto; ilegível segue `partial` com contadores; documento
  com texto próprio NUNCA roda OCR embutido; cap registrado (aprendizado: python-docx
  deduplica imagens byte-idênticas em um media part — teste usa dimensões variadas);
  pytesseract ausente degrada limpo.
- Backend 672/672.
- **Arquivo real que motivou o item**: reextração do docx original das atas do RCA →
  `ok_ocr`, `embedded_images_found: 1`, 1.698 chars legíveis ("RES: Paggo Soluções…").
  A resposta à pergunta do usuário ficou comprovada: com OCR embutido, o envelope
  legível classifica normalmente e "(OCR vazio)" só resta onde é verdade.
