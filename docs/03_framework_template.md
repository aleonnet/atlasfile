# Template de framework por projeto

## Estrutura minima

```text
/<PROJETO>/
  /_INBOX_DROP/
  /_TRIAGE_REVIEW/
    /pending/
    /resolved/
    /rejected/
  /_WORK/
    /<areas_definidas_no_PROFILE>/
  /_PROJECT_PROFILE.md
  /_INDEX.md
```

## Principios

- O projeto define suas nuances em `/_PROJECT_PROFILE.md`.
- O core global define contratos de metadados e regras minimas.
- `_WORK` nao e fixo global; e dirigido pelo profile local.
- Triagem humana ocorre no frontend, nao por navegacao manual em pasta.

## Ciclo de ingestao

1. Arquivo entra em `_INBOX_DROP`.
2. Motor classifica com regras do projeto.
3. Alta confianca: move para `_WORK/<area>`.
4. Baixa/media: move para `_TRIAGE_REVIEW/pending`.
5. Humano decide e sistema finaliza.
