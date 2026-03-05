Analise o trecho de documento fornecido e classifique-o.
O contexto do projeto (áreas disponíveis, aliases e topics válidos) é fornecido junto ao trecho.

Regras:
- Prefira classificar em uma das áreas listadas no contexto do projeto. Use os aliases como pistas.
- Se nenhuma área existente for adequada, proponha uma nova area_key descritiva e justifique em "explanation".
- Calibre confidence com honestidade: use < 0.6 quando houver ambiguidade entre áreas; use > 0.85 somente com forte evidência.
- Para topics, use somente chaves listadas no contexto do projeto.
- Para document_type, use termos descritivos em português (ex: contrato, nota_fiscal, apresentacao, relatorio, ata, parecer, proposta).

Chame a ferramenta submit_classification com:
- document_type (tipo do documento)
- tags (lista de tags relevantes)
- confidence (0.0 a 1.0, calibrado conforme regras acima)
- area_key (área de destino ou nova proposta)
- topics (somente chaves válidas do contexto)
- explanation (breve justificativa, obrigatória quando propor área nova ou confidence < 0.6)

Use apenas a ferramenta para responder.
