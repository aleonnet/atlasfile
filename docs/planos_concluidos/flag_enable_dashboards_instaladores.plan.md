# Flag `--enable-dashboards` / `--no-dashboards` nos instaladores

- **Data**: 2026-07-31
- **Branch**: `flag-enable-dashboards` (base: main `06fd8ae`)
- **Versão**: sem bump — mudança de instalador não altera a versão do app
  (decisão registrada de 2026-07-31); os instaladores viajam por
  `raw.githubusercontent.com/main`, sem re-emissão de release.
- **Origem**: o site publicou uma linha ensinando o caminho manual de `.env`
  para o Dashboards; a experiência devida era uma flag de instalador. A
  arqueologia git provou que a flag **nunca existiu**: pré-v0.57.0 o
  Dashboards era serviço default; a v0.43.1 imprimia URL+credencial no
  painel; a v0.44.0 introduziu a chave de cookie (gerada incondicionalmente
  até hoje); o opt-in por `.env` da Fase 2 nunca ganhou superfície de
  instalador.
- **Processo**: plano formal revisado por 2 revisores adversariais locais
  (~30 achados, 6 mudaram o desenho), aprovação nominal, TDD com baseline
  por nome, mutantes, E2E real em VM lima.

## Decisões (D1–D8)

- **D1** — nomes `--enable-dashboards · -EnableDashboards` e inverso
  `--no-dashboards · -NoDashboards`; o par junto é recusado CEDO nos dois
  instaladores (echo+exit pós-parser no sh; molde `-Version`+`-FromSource`
  no ps1), nunca via `--help`.
- **D2** — painel com URL + credencial lendo
  **`OPENSEARCH_INITIAL_ADMIN_PASSWORD`** (fonte de verdade do compose;
  `OPENSEARCH_PASSWORD` só como fallback) e **só com o dashboards ligado**
  — a versão v0.43.1 imprimia sempre (vazamento) e lia a chave que pode
  divergir num `.env` herdado.
- **D3** — estado desejado por precedência `flag > COMPOSE_PROFILES do
  processo > .env` (a mesma do compose). Merge/remoção da CSV token-wise
  (`dashboards-extra` intocado); o último token remove a LINHA. Ordem do
  desligar: `up -d` PRIMEIRO, teardown depois — o app novo nasce antes de o
  dashboards morrer.
- **D4** — `af_resolve_dash_port` (env `DASHBOARDS_PORT` > `.env` > 5601);
  guarda de portas só cobra a 5601 quando o estado desejado é ligado; braço
  de mensagem próprio ensina `DASHBOARDS_PORT`; `--no-dashboards` não checa
  a 5601 (é a porta do container que vai morrer).
- **D5** — site: substituir a linha publicada pelas flags, EN+PT; push SÓ
  após merge do produto E com o texto aprovado pelo dono (pendente — T7).
- **D6** — riscos declarados (prefixos ambíguos, contagem dinâmica,
  guardas de consistência acordadas).
- **D7** — uninstall derruba o serviço com profile:
  `un_compose_down` passa `--profile dashboards` no `down`.
- **D8** — `--enable-dashboards` em re-run NÃO re-gera
  `DASHBOARDS_COOKIE_PASSWORD` (rotacionar invalidaria sessões SSO).
- **Correção pega pelo E2E (dentro do escopo — o contrato já estava no
  plano)**: `--no-dashboards` numa instalação que nunca ligou não cria
  chave nenhuma no `.env`. A primeira implementação gravava
  `DASHBOARDS_ENABLED=false` incondicionalmente; o E2E real reprovou
  (`.env` deixou de ser byte-idêntico), a bancada ganhou o caso (vermelho
  351/1), o braço `0)` do `af_dash_apply` ganhou a guarda "reverte só o que
  existe", e 2 mutantes (condição sempre-verdadeira e invertida) morreram
  na asserção nova.

## Arquitetura testável

Todo comportamento novo é função ACIMA do gate de biblioteca do
`install.sh` (precedente `af_stack_up`): `af_csv_has`, `af_env_csv_add`,
`af_env_csv_remove`, `af_dash_desired`, `af_dash_apply`,
`af_dash_teardown`, `af_resolve_dash_port`, `af_panel_dash`. As fases
apenas as chamam.

## Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `install.sh` | defaults + parser + validação do par; 8 funções novas acima do gate; fase 3 chama `af_dash_apply`; `af_stack_up` com contagem dinâmica (2/3) + teardown pós-up; painel chama `af_panel_dash`; next steps condicional; doctor com linha de estado + contrapositivo; guarda com braço `DASHBOARDS_PORT`; `un_compose_down` com `--profile dashboards` |
| `install.ps1` | `[switch]$EnableDashboards`/`[switch]$NoDashboards`, validação cedo do par, forwards, header+usage (ASCII puro) |
| `tests/installer/run.sh` | +15 blocos (~50 asserts): parser, par, CSV (6 fixtures), precedência, apply (incl. never-enabled), painel divergente + contrapositivo, teardown/ordem, guarda, doctor, uninstall |
| `tests/installer/win/run.ps1` | bloco H9: forwards com nome inteiro, contrapositivos, par com `Calls` vazio |
| `.env.example` | flag como caminho primário na seção Dashboards |
| `INSTALL.md`, `README.md`, `README.pt-BR.md` | flag documentada (tabela de serviços cita a flag) |
| `CHANGELOG.md` | seção "Instalador — 2026-07-31 (flag do Dashboards)" |

## Prova (números reais)

- **T0 pre-flight A–G** (medido em VM antes de codar): `.env` com profile
  sobe 3; CSV `outra,dashboards` sobe 3; contrapositivo 2;
  `DASHBOARDS_PORT` custom renderiza; **`--remove-orphans` NÃO derruba
  serviço com profile** (justificativa do teardown); `rm -sf` de serviço
  nunca-criado é rc 0. Piso: docker compose v5.3.1.
- **T2 bancada sh**: baseline main 310/0 (180 nomes TRACE) → vermelho
  322/28 → verde 350/0 → (fix do E2E) vermelho 351/1 → **352/0 final**,
  zero nome de baseline perdido em todos os passos.
- **T3 mutantes sh**: **15 em 5 rodadas** (forwards, braços trocados,
  validação do par, merge cego, remove substring, teardown removido/nome
  trocado, painel incondicional/sem credencial, doctor, guarda dois lados,
  contagem re-hardcoded, condição do never-enabled sempre-verdadeira e
  invertida) — todos mortos exatamente pela guarda-alvo, restauração
  byte-exata provada por `cmp`.
- **T4 bancada win** (canal prlctl/SYSTEM): 235→**241/0**, zero nome
  perdido; **3 mutantes ps1** mortos.
- **T1 consistência**: 13 guardas verdes (needles×fonte, ajuda×parser,
  ASCII, funções vivas).
- **T5 E2E real** (VM lima `atlas-e2e`, release local bundle+pull):
  - install `--enable-dashboards --port 8090` → **3 serviços**, chaves
    gravadas, painel com URL + credencial que **loga de verdade**
    (OpenSearch 200 via HTTPS autenticado, 401 sem auth; Dashboards
    `/api/status` 200 autenticado);
  - SSO `/api/observability/open` → 302 **com `Set-Cookie`** e deep-link do
    dashboard de operação; desligado → 302 **sem** `Set-Cookie` e location
    genérico (o discriminador que o plano exigiu — 302 sozinho é
    falso-positivo);
  - re-run sem flag → `.env` **byte-idêntico**, 3 containers;
  - `--no-dashboards` → container **removido** (`docker ps -a`), ordem
    up→rm visível no log real, `DASHBOARDS_ENABLED=false`, linha
    `COMPOSE_PROFILES` removida (CSV limpa após A→B→A);
  - `--no-dashboards` sem nunca ter ligado → rc 0, `.env` byte-idêntico,
    stack intocada (após o fix acima);
  - guarda: 5601 ocupada por terceiro → `--enable-dashboards` falha rc 1
    ensinando `DASHBOARDS_PORT`; `--no-dashboards` NÃO bloqueia (rc 0);
  - uninstall com dashboards no ar → plano de remoção lista 3 containers,
    **zero** `atlasfile*` ao final (D7);
  - D8: `DASHBOARDS_COOKIE_PASSWORD` idêntico (md5) antes/depois do
    enable.
- **T6 CI**: pendente do PR (7 jobs). **T7 site**: pendente de merge +
  aprovação do texto pelo dono.

## Descoberta fora de escopo — CORRIGIDA em plano próprio

> Resolvida em [`correcao_reuso_volume_pos_keep_data`](correcao_reuso_volume_pos_keep_data.plan.md),
> no mesmo PR. A investigação mostrou que o fix candidato abaixo (apagar o
> manifesto) **não resolveria** — `.git` também reprova o `af_fresh_install_dir`
> — e criaria duas regressões. A correção entregue ataca o portão do volume: a
> decisão passa a depender da ausência do `.env`, não da "frescura" do
> diretório. O texto original fica abaixo como registro do diagnóstico.

O E2E revelou um **bug real pré-existente** (interação Fase 4a ×
uninstall): quando o uninstall preserva o diretório ("kept: what already
existed"), o `.atlasfile-install-manifest` do diretório **sobrevive** — a
única remoção de manifesto é a do host (`rm -f "$AF_HOST_MANIFEST"` no
`rm-state`). Uma reinstalação após `--uninstall --keep-data` vê o manifesto
órfão, `af_fresh_install_dir` responde "não é fresh", o gate do claim do
volume guardado é pulado, e nasce senha nova contra o volume velho →
401 em tudo, sem mensagem de erro. Provado em VM com logs (registro em
`~/.atlasfile/kept-volumes` nunca consumido). Fix candidato: o uninstall
remover o manifesto do diretório também no caminho preservado. NÃO foi
corrigido neste plano (escopo aprovado não cobria); aguarda decisão do
dono.
