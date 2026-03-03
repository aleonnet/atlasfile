# Gap analysis: estado atual vs framework AtlasFile

## Base analisada

- Snapshot: `folder_snapshot_2026_03_01.json`
- Escala observada:
  - ~20.531 pastas
  - ~73.081 arquivos
  - profundidade maxima 14

## Gaps principais

1. **Padrao de topo heterogeneo**
   - coexistem prefixos numericos, sublinhados tecnicos e nomes livres.
   - impacto: baixa previsibilidade para automacao e busca.

2. **Nomeacao inconsistente**
   - presenca de espacos, formatos de versao variados, simbolos especiais.
   - impacto: colisao, dificuldade de parsing e risco operacional em multiplas plataformas.

3. **Duplicidade de nomes**
   - repeticao alta de nomes como `Summary.pdf`, `image1.png`, etc.
   - impacto: ambiguidade de referencia e erro humano.

4. **Caminhos longos**
   - volume relevante de caminhos acima de limites praticos.
   - impacto: risco de falha em sync, scripts e transferencias.

5. **Sem camada padrao de indexacao local**
   - busca depende de estrutura manual e ferramentas dispersas.
   - impacto: latencia para encontrar evidencias e documentos criticos.

6. **Rastreabilidade parcial**
   - sem padrao unico para vincular origem e nome canonico.
   - impacto: risco de perda de cadeia de custodia em casos sensiveis.

## Estado alvo

- Ingestao por projeto (`_INBOX_DROP`)
- Classificacao orientada por `/_PROJECT_PROFILE.md`
- Triagem humana minima para baixa confianca
- `_INDEX.md` com trilha de decisao
- Busca local OpenSearch BM25 com filtros por metadados

## KPI de fechamento de gap

- Aumentar taxa de acerto automatico de classificacao (sem triagem)
- Reduzir tempo medio de busca de documento critico
- Reduzir volume de caminhos fora de padrao
- Manter rastreabilidade minima em 100% dos documentos ingeridos
