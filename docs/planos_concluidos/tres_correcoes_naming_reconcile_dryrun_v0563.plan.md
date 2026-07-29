# Três correções independentes: naming canônico, reconcile pós-setup, `--dry-run` — v0.56.3

Três defeitos apurados durante a análise de distribuição de build (que seguiu em
plano próprio), sem relação entre si. Todos reproduzidos contra o código real
antes de qualquer linha ser escrita, e todos com guarda provada contra mutante.

---

## 1. Nome do usuário confundido com canônico (perda de informação)

### Reproduzido antes de corrigir

```
pattern : {date}__{project}__{original_name}        (utils.py:66)
entrada : DocuSign_Project_Neptune___SPA__Anexos_v_A__v01__v01.pdf
saída   : Anexos_v_A__v01.pdf
```

`DocuSign_Project_Neptune___SPA` era descartado — o documento perdia o
identificador. Relatado pelo usuário a partir de arquivo real.

### Causa

O arquivo chega ao INBOX com nome **do usuário** que já termina em `__v01.pdf`
(versionamento manual, convenção comum em documento real) e contém `__` no meio:

1. `_CANONICAL_TAIL_RE` (`utils.py:65`) casa a cauda → o nome é tratado como
   canônico sem nunca ter sido embrulhado
2. `extract_original_name_from_canonical` calcula `n_skip = 2` e reparte em
   `["DocuSign_Project_Neptune", "_SPA", "Anexos_v_A__v01"]`, devolvendo o terceiro
3. `has_residue` (`ingestion.py`) validava o **candidato de saída**, não a entrada:
   `Anexos_v_A` não é data, nem `project_id`, nem domínio → passava

**O caminho legítimo sempre esteve correto**: `test_caso_real_embrulho_duplo` usa
este mesmo arquivo **com** prefixo canônico e preserva tudo. O defeito era só no
caso sem prefixo.

### Correção — prova positiva na entrada

`_prefix_proves_canonical` (novo, `ingestion.py`) checa cada segmento do prefixo
contra o campo que ele deveria ser, usando **fatos do profile**: `{date}` casa
`\d{8}`, `{project}` casa o `project_id` (via `sanitize_token`, como o
`build_canonical_filename` grava), `{area}`/`{business_domain}` e
`{document_type}` casam chaves conhecidas. Campo que o profile não conhece não
bloqueia — o pattern é configurável.

Dois filtros em ordem, e a ordem importa:
1. a prova positiva decide **quais patterns podem ser aplicados**
2. entre os que sobraram, `has_residue` desempata (resolve migração de naming)

Em `utils.py`, a contagem de segmentos virou `split_canonical` +
`canonical_prefix_fields` — **fonte única**, consumida tanto pelo
`extract_original_name_from_canonical` (comportamento idêntico) quanto pela prova
nova, em vez de duplicar a aritmética de separadores.

### Por que não mexeu em disco

`build_canonical_filename` não mudou: nenhum arquivo é renomeado e o formato
canônico é o mesmo. No `reconcile.py`, um nome que deixa de parsear cai em
`orig_fn = f.name` — degradação segura, sem perda. **Escapar o `__` no build foi
descartado**: seria correto na raiz, mas mudaria o formato e exigiria migração
dos arquivos já canonizados.

### Guarda

Dois testes novos em `test_ingest_canonical_reingest.py`: o arquivo real do
usuário, e um canônico de **outro** projeto (data válida, projeto errado).
**Mutante provado**: neutralizando `_prefix_proves_canonical`, o defeito volta
(`Anexos_v_A__v01.pdf`) e os testes ficam vermelhos. Os 5 testes existentes
seguem verdes — dois deles agora até por motivo melhor, porque a prova descarta
candidatos espúrios que antes passavam por sorte.

---

## 2. Reconcile: o primeiro ciclo nunca rodava na subida

### O fato, com uma correção ao diagnóstico inicial

`config.py:30` traz `auto_reconcile_interval_seconds: int = 0`, mas
`docker-compose.yml:67` define `AUTO_RECONCILE_INTERVAL_SECONDS:-600`. **Em
Docker o default efetivo é 600s, não 0** — o reconcile automático está ligado.

O defeito real é `main.py`: `while not _reconcile_stop.wait(interval)` faz o
`wait` **antes** do corpo. Mesmo ligado, o primeiro ciclo só sai 10 minutos após
a subida. Numa instalação nova apontada para uma pasta que já tem documentos, a
UI mostrava zero até lá e "Reconciliar agora" era o único caminho.

### Correção — condicionada ao estado

`_start_setup_reconcile_if_needed` (novo) dispara um ciclo na subida **apenas
quando há projeto no disco E o índice está vazio**, chamado no `lifespan` logo
após `_start_auto_reconcile_if_enabled`.

A condição é o índice vazio, e não "algum projeto sem documento", porque precisa
ser **falsa em todo `docker compose restart` de rotina** — senão um corpus grande
pagaria um reconcile completo a cada reinício. Projeto novo em instalação já
povoada segue coberto pelo laço periódico e pelo watcher.

Reusa o que já existia: `_index_has_documents()`, `list_project_roots`,
`_run_reconcile_background`. Qualquer falha ao decidir vira "não dispara" — o
código roda dentro do `lifespan` e uma exceção levaria a API junto.

### Guarda

`test_setup_reconcile.py` (novo, 4 testes): dispara com índice vazio; **não**
dispara com índice povoado; não dispara sem projeto; não derruba o boot quando a
decisão falha. **Mutante provado**: removida a condição de índice vazio, o teste
do restart de rotina fica vermelho.

---

## 3. `--dry-run` se contradizia (item 1 do `ROADMAP.md`)

### O defeito, pior do que o registrado

O roadmap descrevia `✘ ... daemon does not answer` + `✔ none — everything needed
is already here`. Medido, o desacordo é maior: com um binário que existe mas não
responde `--version`, a tela mostra **`✘ docker not found`** e, oito linhas
abaixo, **`✔ none — everything needed is already here`**. As duas seções
discordavam sobre a *existência* do Docker, não só sobre o daemon.

### Causa — e por que não era a correção de 1 linha registrada

Duas fontes de verdade: `doc_prereqs` pergunta ao daemon (e exige que a
ferramenta responda `--version`, ver `doc_version`), enquanto `run_dry_run`
repergunta com `command -v docker` — que tem sucesso com o daemon parado **e** com
binário mudo. Remendar o `command -v` deixaria a duplicação de pé.

### Correção — uma fonte de verdade

`doc_prereqs` passa a registrar **o que** faltou, não só quantos:
- `DOC_MISSING` — o instalador resolve sozinho (git, docker, compose plugin)
- `DOC_BLOCKERS` — só o usuário resolve (daemon parado, curl ausente)

`run_dry_run` consome essas listas em vez de remedir a máquina. A separação
também resolve a UX que o roadmap não mencionava: `!` para o que o instalador
instalaria, `✘` para o que exige ação do usuário. `curl` fica em `DOC_BLOCKERS`
de propósito — não existe `ensure_curl`.

**Paridade:** o `install.ps1` delega o lado Linux para `install.sh --dry-run
--delegated`, então a correção vale para o Windows sem tocar no `.ps1`.

### Guarda

Duas asserções novas em `tests/installer/run.sh`, com stubs que respondem
`--version` de verdade (sem isso `doc_version` os declara "not found" e o teste
mediria a contradição errada): daemon parado **não** pode anunciar tudo pronto; e
o contrapositivo — com tudo no lugar a frase **tem** de continuar aparecendo, que
é o que impede a correção preguiçosa de simplesmente apagar a mensagem. A
primeira **reprovava antes da correção**.

Os três cenários conferidos na tela real: daemon parado → `✘ the Docker daemon is
not answering`; tudo no lugar → `✔ none — everything needed is already here`;
docker ausente → `! Docker would be installed`.

---

## Resultado

| Bancada | Antes | Depois |
|---|---:|---:|
| Backend (pytest) | 725 | **731** |
| Instalador (`run.sh`) | 211 | **214** |
| Frontend (vitest) | 252 | 252 (intocado) |

`shellcheck -S warning` limpo, sintaxe validada no bash 3.2 do macOS,
`check_consistency.py` verde, `install.ps1` parseia limpo.

## Fora deste plano

**CI travando 6h no job macOS.** Correlação forte com `e9553be6` (último verde:
`950820c1`), mas causa **não provada**: não reproduz local (214 passed em 47s) nem
no job Linux, que roda a mesma bancada. O log só traz stderr porque o stdout fica
preso no buffer de bloco do pipe. A contenção (`timeout-minutes` no job) é
independente do diagnóstico e segue pendente de decisão.

## Verificação

```bash
cd /Users/alessandro/Development/AtlasFile
make test
```

**E2E com stack real** (não executado — exige a stack no ar):
1. `PROJECTS_HOST_ROOT` para pasta com documentos e índice zerado → a UI mostra
   os documentos sem clicar em "Reconciliar agora"
2. `DocuSign_Project_Neptune___SPA__Anexos_v_A__v01__v01.pdf` no `_INBOX_DROP` →
   o canônico gerado contém `DocuSign_Project_Neptune___SPA__Anexos_v_A`
3. reingestão do já canonizado → sobe para `__v02` sem re-embrulhar o prefixo
