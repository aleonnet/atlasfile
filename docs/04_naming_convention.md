# Convencao de nomes

## Objetivo

Padronizar nomes para:

- facilitar busca,
- reduzir colisao,
- melhorar interoperabilidade.

## Padrao canonico (arquivo)

O formato canonico e **configuravel** via `naming.canonical_pattern` no template/profile do projeto.

### Campos disponiveis

| Campo | Descricao |
|-------|-----------|
| `{date}` | Data de ingestao (formato em `naming.date_format`, default `%Y%m%d`) |
| `{project}` | ID do projeto (normalizado: lowercase, sem acentos) |
| `{area}` | Area classificada (ex: financeiro, juridica) |
| `{original_name}` | Nome original do arquivo sem extensao (**preservado intacto**) |
| `{document_type}` | Tipo classificado (ex: contrato, relatorio, ata) |

### Sufixo obrigatorio

`__v{version}{ext}` e sempre adicionado automaticamente pelo sistema.

### Pattern default

```
{date}__{project}__{original_name}__v{version}{ext}
```

Exemplo: `20260301__kaido__Contrato_Migracao_Clientes__v01.xlsx`

### Outros exemplos de patterns

| Pattern | Resultado |
|---------|-----------|
| `{date}__{project}__{area}__{original_name}` | `20260301__kaido__financeiro__DRE_2026__v01.xlsx` (formato legado) |
| `{original_name}` | `DRE_2026__v01.xlsx` (minimalista) |
| `{project}__{document_type}__{original_name}` | `kaido__contrato__Contrato_SPA__v01.pdf` |

### Formato legado (pre-0.4.0)

`YYYYMMDD__<project_id>__<area_key>__<sanitized_title>__vNN.<ext>`

Arquivos neste formato sao migrados automaticamente durante a reconciliacao.

## Regras

- Separar blocos com `__`;
- `{original_name}` preserva case, acentos e underscores do arquivo original;
- Apenas caracteres invalidos de filesystem sao removidos (`/ \ : * ? < > |`);
- `{project}`, `{area}` e `{document_type}` usam `sanitize_token` (lowercase, sem acentos);
- Versao com `vNN` (`v01`, `v02`...);
- `{original_name}` e obrigatorio no pattern.

## Escopo de indexacao (PARA roots)

Todas as roots PARA definidas em `layout.roots` sao escaneadas na reconciliacao:

| Root | area_key | Descricao |
|------|----------|-----------|
| `01_PROJECTS` | `projects` | Projetos ativos com deadline |
| `02_AREAS` | Inferido da subpasta (ex: `04_financeiro` → `financeiro`) | Responsabilidades continuos |
| `03_RESOURCES` | `resources` | Material de referencia |
| `04_ARCHIVE` | `archive` | Itens inativos |

Documentos em qualquer root sao incluidos no `_INDEX.md` e indexados no OpenSearch. A ingestao automatica (INBOX) continua roteando exclusivamente para `02_AREAS/`; as demais roots recebem arquivos colocados manualmente.

## Rastreabilidade

Mesmo com nome canonico, manter:

- `original_filename`
- `canonical_filename`
- `doc_id`
- `sha256`

no `_INDEX.md` e no indice de busca.
