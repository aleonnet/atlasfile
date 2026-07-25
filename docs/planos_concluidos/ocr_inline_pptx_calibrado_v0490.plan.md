# OCR inline de imagens no PPTX, calibrado no corpus real (v0.49.0)

**Concluído em 2026-07-25.** Origem: pergunta do usuário sobre a v0.48.0 — "se o
documento tiver texto E imagens, o OCR roda?" (não rodava: modo envelope era
tudo-ou-nada). Decisão de custo-benefício do usuário: modo "sempre" **só no PPTX**
(onde imagem É conteúdo — diagramas, screenshots); docx/xlsx seguem só-envelope.

## Decisões

- **Caminho por `slide.shapes`, não por zip**: shape PICTURE → `shape.image.blob` →
  tesseract, âncora exata `slide:N:image:M` na ordem visual (top, left) já usada.
  Bônus comprovado na medição: imagens herdadas do slide master/layout NÃO aparecem
  em `slide.shapes` — logo de timbre não conta nem custa OCR (o teste de unidade
  disso é irrealizável: `MasterShapes` do python-pptx não tem `add_picture`; o fato
  ficou provado pela medição nos decks reais timbrados do corpus).
- **Corte de ruído MEDIDO, não arbitrado** (regra do usuário): 12 decks reais do
  corpus do classificador, 40 imagens OCRizadas → distribuição bimodal: logos/ícones
  = 0–14 chars, conteúdo real (diagramas) = 513+. Corte em **85 chars = média
  geométrica dos extremos medidos** (`_EMBEDDED_OCR_MIN_CHARS`). O corte NÃO se
  aplica ao modo envelope (documento sem nenhum texto: OCR fraco é o único sinal).
- **WMF/EMF pulados com registro**: fato medido no corpus (`image/x-wmf` →
  `TypeError: Unsupported image format` no PIL); try/except por imagem pula e segue.
- **Cap global de 10 por deck mantido** com `embedded_images_ocr_capped` no metadata.
- **Fallback envelope preservado**: `chunk_rows` vazio após shapes → zip
  `ppt/media/*` como antes (cobre conteúdo só no master e texto curto de envelope).
- **Status honesto**: texto nativo presente → `ok` (mesmo com chunks de imagem);
  só OCR → `ok_ocr`; nada → `partial`.

## Validações

- Backend 674/674 (2 novos: deck misto extrai nativo + imagem com âncora
  `slide:1:image:1`; logo curto filtrado como ruído com contadores honestos
  `found=1, ocr=0`).
- **Deck real do corpus** (`doc_0075__sistemas_v4`): `ok`, 9 slides,
  `embedded_images_found: 4, embedded_images_ocr: 2` — os DOIS diagramas de
  topologia de sistemas viraram chunks pesquisáveis (`slide:2:image:1`,
  `slide:8:image:1`: FPW/SISJUR, GED360, NEOGRID, MEDIA HUB…), os dois ruídos
  ficaram fora. Conteúdo antes invisível à busca.
