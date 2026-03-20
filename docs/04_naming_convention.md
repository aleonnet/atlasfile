# Convencao de nomes

## Objetivo

Padronizar nomes para:

- facilitar busca
- reduzir colisao
- preservar rastreabilidade

## Padrao canonico do arquivo

O nome canonico e configuravel via `naming.canonical_pattern` no template/profile do projeto.

### Campos disponiveis no formatter

| Campo | Descricao |
|-------|-----------|
| `{date}` | Data de ingestao no formato `naming.date_format` |
| `{project}` | ID do projeto normalizado |
| `{business_domain}` | Valor do `business_domain` normalizado |
| `{original_name}` | Nome original do arquivo sem extensao, preservado ao maximo |
| `{document_type}` | Tipo documental normalizado |

Observacao importante:

- o contrato atual do runtime usa `{business_domain}`
- o placeholder legado `{area}` existe apenas para parsing/migracao de nomes antigos no reconcile

### Sufixo obrigatorio

O sistema sempre adiciona:

```text
__v{version}{ext}
```

### Pattern default da 0.8.0

```text
{date}__{project}__{original_name}
```

Exemplo:

```text
20260316__smoke_cycle__CT 4600052462_Contrato_Servicos_TI__v01.pdf
```

### Outros patterns validos

| Pattern | Resultado |
|---------|-----------|
| `{date}__{project}__{business_domain}__{original_name}` | `20260316__smoke_cycle__juridico__Contrato_SPA__v01.pdf` |
| `{project}__{document_type}__{original_name}` | `smoke_cycle__contrato__Contrato_SPA__v01.pdf` |
| `{date}__{project}__{business_domain}__{document_type}__{original_name}` | `20260316__smoke_cycle__financeiro__planilha__UPI Receita Tri__v01.xlsx` |

## Regras

- separar blocos com `__`
- `{original_name}` e obrigatorio
- `{project}`, `{business_domain}` e `{document_type}` passam por `sanitize_token`
- `{original_name}` passa por `fs_safe`, preservando ao maximo o nome humano
- apenas caracteres invalidos de filesystem sao removidos
- a versao sempre segue `vNN`

## Layout fisico relacionado ao nome

O nome do arquivo e independente da pasta, mas o destino operacional padrao na 0.8.0 e:

```text
02_AREAS/<business_domain>/<document_type>/
```

Exemplo:

```text
02_AREAS/juridico/contrato/20260316__smoke_cycle__CT 4600052462_Contrato_Servicos_TI__v01.pdf
```

## Escopo de indexacao das roots PARA

Todas as roots definidas em `layout.roots` entram no reconcile:

| Root | Descricao |
|------|-----------|
| `01_PROJECTS` | Projetos ativos e material de execucao |
| `02_AREAS` | Acervo operacional classificado por `business_domain/document_type` |
| `03_RESOURCES` | Material de referencia |
| `04_ARCHIVE` | Itens inativos |

A ingestao automatica continua roteando para `02_AREAS/`. As demais roots tambem sao indexadas quando contem documentos.

## Rastreabilidade minima

Mesmo com nome canonico, o sistema deve preservar:

- `original_filename`
- `canonical_filename`
- `doc_id`
- `sha256`

no `_INDEX.md` e no indice de busca, conforme o campo estiver disponivel em cada camada.
