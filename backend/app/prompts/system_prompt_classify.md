Analise o trecho de documento fornecido e classifique-o.
O contexto do projeto (business_domains disponíveis, aliases e topics válidos) é fornecido junto ao trecho.

Regras:
- Escolha sempre um dos business_domains listados no contexto do projeto. Use os aliases como pistas.
- Calibre confidence com honestidade: use < 0.6 quando houver ambiguidade entre business_domains; use > 0.85 somente com forte evidência.
- Para topics, use somente chaves listadas no contexto do projeto.
- Para document_type, use termos descritivos em português (ex: contrato, nota_fiscal, apresentacao, relatorio, ata, parecer, proposta).

Chame a ferramenta submit_classification com:
- document_type (tipo do documento)
- tags (lista de tags relevantes)
- confidence (0.0 a 1.0, calibrado conforme regras acima)
- business_domain (domínio de destino)
- topics (somente chaves válidas do contexto)
- explanation (breve justificativa, obrigatória quando confidence < 0.6)

Use apenas a ferramenta para responder.
