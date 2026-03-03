# Convencao de nomes

## Objetivo

Padronizar nomes para:

- facilitar busca,
- reduzir colisao,
- melhorar interoperabilidade.

## Padrao canonico (arquivo)

`YYYYMMDD__<project_id>__<area_key>__<short_title>__vNN.<ext>`

Exemplo:

`20260301__kaido_upi_tahto__contratos_comunicacao__migracao_clientes__v01.xlsx`

## Regras

- usar lowercase no nome canonico;
- separar blocos com `__`;
- sem espacos; usar `_`;
- sem caracteres especiais fora de `_` e `-`;
- versao com `vNN` (`v01`, `v02`...).

## Rastreabilidade

Mesmo com nome canonico, manter:

- `original_filename`
- `canonical_filename`
- `doc_id`
- `sha256`

no `_INDEX.md` e no indice de busca.
