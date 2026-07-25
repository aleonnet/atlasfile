# Causa real de "sem texto extraível" + toggle de idioma na sidebar (v0.52.0)

**Concluído em 2026-07-25.** Dois itens pequenos executados juntos: um do
roadmap (registrado na v0.48.0) e um pedido do usuário no meio do ciclo.

## A — A triagem passa a dizer POR QUE não houve texto

A mensagem era sempre "(OCR vazio) — decida manualmente": genérica e às vezes
**falsa**, porque o OCR podia nem ter rodado (formato sem extrator, tesseract
ausente, arquivo corrompido). O `ExtractionResult` já sabia a resposta — ela
morria dentro do extrator porque a ingestão usava `read_text_excerpt()`, que
devolve só a string.

Entregue: `process_inbox_file` passa a usar `extract_document_content()` e o
novo `_no_text_cause()` deriva um código estável a partir de
`extraction_status` + `content_type` + metadata:

| Código | Quando | Mensagem (pt-BR) |
|---|---|---|
| `only_embedded_image` | Office "envelope": havia imagem embutida, o OCR rodou e não achou texto | contém apenas imagem embutida sem texto legível |
| `image_without_text` | Imagem solta sem texto | imagem sem texto legível (OCR não encontrou nada) |
| `scan_unreadable` | PDF escaneado que o OCR não leu | PDF escaneado sem texto legível pelo OCR |
| `ocr_unavailable` | Tesseract ausente — **não é "OCR vazio"**, é OCR que não rodou | OCR indisponível no servidor |
| `unsupported_format` | Sem extrator para a extensão | formato sem extrator disponível |
| `extraction_error` | Arquivo ilegível/corrompido | falha ao ler o arquivo (pode estar corrompido) |
| `empty_document` | Documento de texto genuinamente vazio | documento sem conteúdo de texto |

Precedência decidida com critério: `ocr_unavailable` vence
`only_embedded_image` — com o motor fora do ar, culpar a imagem mentiria sobre
a causa. Código desconhecido (meta antigo ou versão futura) cai na mensagem
genérica, nunca em branco.

Fluxo: `classification["no_text_cause"]` → meta pending → `TriageItem` →
`triage:queue.noText.*` nos dois idiomas.

## B — Idioma ganha ícone na sidebar (pedido do usuário)

Já existiam o seletor em Configuração e o `LanguageQuickSwitch` das telas de
primeiro acesso — faltava o acesso rápido do dia a dia. Botão com as **mesmas
classes** dos vizinhos (tema e colapso), ícone `Languages` (o mesmo que já
representa idioma no app). Como são dois idiomas, o clique alterna direto —
mesma gramática do tema, que cicla; o tooltip diz o destino ("Mudar para
English (US)").

## Validações

- Backend 717/717 (9 testes novos parametrizados por causa, incluindo a
  precedência do OCR indisponível). Três testes antigos mockavam
  `app.ingestion.read_text_excerpt` e passaram a mockar
  `extract_document_content` com um `ExtractionResult` de verdade.
- Frontend 252/252 + `tsc` limpo.
- Medição viva: PNG em branco → `status=no_text`, `content_type=image` →
  `image_without_text`. Toggle de idioma exercitado no browser real: o menu
  vai de "Dashboard" para "Painel" e volta, sem reload, com o tooltip trocando
  de destino.
