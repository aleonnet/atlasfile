# Correção — reuso do volume guardado depois de `--uninstall --keep-data`

- **Data**: 2026-08-01
- **Branch**: `flag-enable-dashboards` (mesmo PR do plano do Dashboards — foi o
  E2E dele que revelou o defeito)
- **Versão**: sem bump (mudança de instalador)
- **Processo**: plano formal → **3 revisores adversariais locais** (9
  bloqueantes; 5 mudaram o desenho e **2 corrigiram fatos que eu tinha
  errado**) → duas decisões do dono → TDD com baseline por nome → 9 mutantes →
  E2E real em VM.

## O defeito (medido, não inferido)

Depois de `--uninstall --keep-data` que **preserva a pasta**, a instalação
seguinte gerava senha NOVA de OpenSearch contra o volume VELHO: stack inteiro
no ar, 401 em tudo, sem uma linha de aviso.

Cadeia: o portão era `if af_fresh_install_dir "$DIR" && volume existe`.
`af_fresh_install_dir` reprova dir com `.git` **ou**
`.atlasfile-install-manifest`, e o uninstall nunca remove o manifesto do
diretório quando a pasta sobrevive (o único `rm` de manifesto é do escopo
HOST). O `&&` curto-circuitava, `af_kept_volume_claim` nunca rodava, o registro
em `~/.atlasfile/kept-volumes` continuava intacto e `af_os_password` gerava
senha nova. Primeira medição: registro `Af!t14MkXVEWm2BhkLc8ecN9` vivo enquanto
o `.env` novo trazia `Af!5s29Ll1HL6gE4Me2B1Fg9`.

## Por que NÃO foi "apagar o manifesto no uninstall"

Era o reflexo, e a banca o derrubou com três fatos do código:

1. **Não conserta**: `.git` também reprova o `fresh` — quem instalou por clone
   continuaria quebrado.
2. **Regressão**: `af_own_pathspec` lê `env_backup` do manifesto para excluir os
   `.env.backup.*` do `git status`; o `.gitignore` ignora `.env`, **não** os
   backups. Sem o manifesto, um `af_update_clone` com histórico divergente
   passaria a ver os backups como trabalho do usuário e recusaria realinhar.
3. **Regressão 2**: sem `bundle_sha`, o update seguinte classificaria os nossos
   próprios arquivos como editados pelo usuário (backups espúrios + warn
   acusando quem não fez nada).

A raiz é outra: **"dir fresh" nunca foi critério para REUSAR** — é critério para
saber de quem é um volume que ninguém reclamou. O critério honesto de reuso é
*"a fase 3 vai gerar senha nova?"*, isto é, a **ausência do `.env`**. As duas
perguntas coincidiam só por acidente (dir novo nunca tem `.env`).

## Decisões

- **D1** — decide só quando o `.env` está ausente; com `.env` no lugar nada é
  decidido e **nada é consumido**.
- **D2** — reuso exige senha não-vazia (registro sem senha não é reuso).
- **D3 (dono)** — volume nosso + senha desconhecida **falha cedo**, ensinando
  restaurar `.env.backup.*` ou `--uninstall --purge-data`. A mensagem da guarda
  antiga ("outra instância") fica intacta.
- **D4 (dono)** — o consumo sai da fase 1: `af_kept_volume_claim` vira
  `af_kept_volume_peek` (só lê) e o `af_kept_volume_forget` passa a ser chamado
  na fase 3, depois do `.env` escrito. Falha de rede/checksum entre decidir e
  usar deixa de custar a senha do volume.
- **D5** — a decisão inteira (inclusive a existência do volume e a atribuição de
  `AF_REUSE_OS_PASS`) mora acima do gate de biblioteca; o call site só traduz em
  tela. Sem isso, o mutante "implementa a função e não fia o call site"
  sobrevive.
- **D6** — barra final no `--dir` normalizada (`af_dir_key`) nos dois lados da
  chave: sem isso `--dir ~/AtlasFile/` seria **barrado** pela guarda nova.

## Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `install.sh` | `af_dir_key` (nova); `af_kept_volume_record` normaliza a chave; `af_kept_volume_claim` → `af_kept_volume_peek` (sem consumo); `af_volume_decide` (nova, 4 estados: reuse/refuse/nopass/proceed); call site da fase 1 vira `case`; fase 3 chama `af_kept_volume_forget` após escrever o `.env` |
| `tests/installer/run.sh` | +20 blocos: matriz da decisão (11 asserções), **7 execuções do instalador inteiro** sob stubs, registro gravado pelo `--uninstall --keep-data` de verdade; 5 blocos existentes trocam de corpo (`peek`), **zero troca de nome** |
| `CHANGELOG.md` | entrada própria (sem bump) |

## Prova (números reais)

- **Baseline**: 352 asserções / 194 nomes → **383 / 214**, `comm -23` da lista
  de nomes **vazio** (zero nome perdido).
- **Vermelho FORTE antes da correção** (canal do artefato inteiro, ~1,4 s por
  corrida): dir com manifesto + registro + volume → nenhuma mensagem de reuso,
  `.env` com senha gerada, registro intacto. E dir com registro **sem senha** →
  a tela anunciava "reusing" e a fase 3 dizia "generated" (defeito extra que a
  banca reproduziu).
- **9 mutantes, um por vez**, cada um matando a asserção-alvo nomeada:
  M1 = *o código antigo* (fresh como pré-condição) · M2 ordem invertida ·
  M3 `nopass`→`proceed` · M4 sempre reusa · M5 call site sem o braço ·
  M6 sem a checagem de volume · M7 argumentos trocados · M8 uninstall grava o
  dir errado · M9 consumo de volta para a fase 1. Colateral declarado: M6
  também derruba a guarda de 5601 (o `fail` acontece antes). Restauração
  byte-exata por `cmp`.
- **`check_consistency.py`**: 13 guardas verdes.
- **E2E real (VM lima)** com pré-condições **aferidas** (pasta sobreviveu,
  manifesto ficou, `.env` sumiu, registro com os 3 campos e a senha):
  reinstalação diz `password restored from the volume you kept`, senha do `.env`
  **idêntica**, **mesmo** volume (`CreatedAt` igual, não recriado), documento
  plantado antes volta (`count:1`), senha errada → 401, app `health=200`,
  registro consumido. `--purge-data`: senha nova, volume novo, índice ausente,
  sem registro órfão. **Janela do consumo (D4) provada duas vezes**, uma delas
  com falha de rede real: registro intacto após a fase 2 falhar e reuso no
  retry. E a convivência com a flag do Dashboards: `--enable-dashboards` sobe
  3 serviços com `os_auth=200` e o dado no lugar.
- Nota de método: numa das corridas o log do OpenSearch trouxe **uma**
  ocorrência de `Authentication finally failed` no boot, não reproduzida no
  ciclo idêntico seguinte (0), ambas com `os_auth=200` e dado legível — corrida
  transiente de inicialização, não a assinatura do defeito (que é 401
  **persistente**). O sinal confiável é o `os_auth` + o dado, não a contagem de
  linhas do log.

## Limitações declaradas

- `COMPOSE_PROJECT_NAME` no `.env`: a instalação deriva o nome do projeto do
  basename e a desinstalação prefere a chave do `.env`; com o `.env` apagado não
  há como saber o nome escolhido, então o reuso não acontece (e também não
  bloqueia — o volume procurado não existe com esse nome).
- Dois installs simultâneos podem perder uma linha do registro (sem lock).
- Manifesto residual do diretório continua lá (`projects_root_created`,
  `bundle_files`): pode fazer um uninstall futuro anunciar um `rmdir` da pasta
  de projetos, que recusa pasta não-vazia. Cosmético.
