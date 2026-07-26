# installer_uninstall_e_banner_orbital_v0540 — o instalador sabe se desinstalar + banner orbital (v0.54.0)

Concluído em 2026-07-26. Pedido do usuário registrado ao fim da sessão anterior: (1) os instaladores devem saber se desinstalar, revertendo tudo o que criaram **exceto o que já existia**, e (2) trocar a "carinha" do banner por animação no terminal no estilo do `mac-env-setup`, com tema e cores do AtlasFile. Benchmark declarado: `~/Development/mac-env-setup` (v4.2.0).

## Decisões (do usuário)

- **Entrada do uninstall**: flag no próprio `install.sh` (`--uninstall`), não script separado — um script só, zero duplicação das primitivas, mesmo one-liner, e paridade com o `--remove` do benchmark. Ganhou também `make uninstall`.
- **Volume de dados**: **sem default** — o uninstall pergunta sempre. Headless exige `--purge-data` ou `--keep-data`.
- **Profundidade**: reverte o que o manifesto marcar como `created`, incluindo o cask do Docker Desktop (com aviso em caixa alta de que apaga o app), git, Ollama e o modelo baixado. Homebrew nunca é removido automaticamente.
- **Banner**: órbita das duas luas + **cometa na diagonal** ("wow factor máximo" — pedido explícito). O cometa acende o wordmark ao passar.
- **Frase de chamada**: a mesma do site (`hero.title1 + hero.title2` em `atlasfile-website/js/i18n.js`) — *Your documents have gravity.*
- **VMs**: Windows liberada para teste sem snapshot, com credenciais fornecidas; VM macOS autorizada **com snapshot antes**.

## Desenho — banner orbital

Identidade do `CompanionOrb` do produto (núcleo + 2 luas keplerianas + cometa), sem carinha. Canvas de 7 linhas × 56 colunas: orbe nas linhas 1-5 centrado em (3,10), linhas 0 e 6 são o corredor da órbita, wordmark a partir da coluna 24.

Quatro atos em ~1,1 s: ignição linha a linha (5 quadros) → órbita (12) → cometa (8, ejetado de trás do orbe) → o wordmark acende no rastro do cometa.

**Restrições que moldaram o código:**

- **Bash 3.2** (o que o macOS traz): sem array associativo, sem `printf -v arr[i]`, **sem ponto flutuante** — por isso a órbita é uma tabela de 16 células inteiras (elipse rx=9, ry=3) e não trigonometria.
- **Locale**: `${#s}` e `${s:i:1}` contam **bytes** sob `LC_ALL=C`, o que destruiria toda a matemática de coluna com glifos multibyte. A arte é declarada como listas de glifos separadas por espaço e a composição é feita por índice inteiro.
- **Precedência por ordem de escrita** (cometa < orbe < texto < luas): o cometa sai de trás do orbe, a contagem de glifos do orbe fica invariante entre quadros (testável) e nenhuma letra pode ser sobrescrita.

**Corrigido na bancada, com medição:**

1. A trajetória original do cometa cruzava as linhas do texto e corrompia as letras (`y·ur ·ocuments`). Nova trajetória sobe e cruza a coluna 24 já nas linhas 0-1.
2. A cauda amostrava células da trajetória e ficava com buracos de 3 a 5 colunas — lia como respingos. Passou a ser **contígua atrás da cabeça**, na direção do movimento.
3. Render a 20 ms/quadro (uma chamada de função por célula, 336 por quadro) deixaria a animação em 1,56 s. Reescrito para preencher a linha por atribuição direta: **6 ms/quadro**.
4. A rampa horizontal atravessava as 48 colunas e quase não variava dentro das 11 do orbe — a esfera saía chapada e lavada em terminal real. Trocada por **brilho especular** que percorre a esfera em onda triangular, com queda por distância.
5. O tom mais escuro (#2e100a) sumia no fundo do terminal e recortava a silhueta; subiu para 35% de luminância do accent.
6. O fallback 256 com 4 paradas bandava; passou para a rampa quente monotônica de 8 degraus do xterm.

**Cores** derivadas dos tokens do produto (`frontend/src/styles.css`), nunca inventadas: rampa = `--accent` a 35%, `--accent`, `--accent-light`, `--accent-light` clareado 60% rumo ao branco; luas = `--orb-moon-1-fill`/`--orb-moon-2-fill`; cabeça do cometa = `--orb-comet-head`.

**Guardas**: `COLOR_OK` (TTY + `NO_COLOR` ausente + `TERM` != dumb), `TRUECOLOR` só com `COLORTERM` anunciado, `ANIM_OK` (sem CI, com `tput`), largura mínima de 60 colunas, e `trap` que restaura o cursor no Ctrl-C.

## Desenho — manifesto e uninstall

**Dois manifestos, porque os escopos são diferentes de verdade:**

| Arquivo | Escopo | Por quê |
|---|---|---|
| `~/.atlasfile/host-prereqs` | host | Há **um** Docker por máquina. Gravado no instante em que cada `ensure_*` decide — se a instalação morrer depois de instalar o Docker, a re-execução veria "presente" e gravaria a mentira `preexisting` |
| `<instalação>/.atlasfile-install-manifest` | instalação | `install_dir`, `projects_root(+created)`, `repo_clone`, `env_file`, `api_keys_file` |

Vocabulário `created`/`preexisting`. **`created` nunca é rebaixado** numa reinstalação e chave ausente lê `preexisting` — na dúvida, preserva. A escrita é best-effort: contabilidade nunca derruba instalação.

**Fluxo**: coleta só-leitura → plano em texto (REMOVIDO / PRESERVADO, com motivo) → pergunta do volume → confirmação → execução passo a passo (falha de um passo é reportada, não aborta os outros) → resumo.

**Guardas que valeram por si:**

- Stack removido com `docker compose down --remove-orphans --rmi local` rodado **de dentro da instalação**, para o compose resolver o projeto sozinho (respeita `COMPOSE_PROJECT_NAME`, coisa que a derivação por basename em `install.sh:~420` não fazia). `--rmi local` remove só as imagens sem `image:` no compose — as `opensearchproject/*` (2,7 GB, compartilháveis) ficam. **Nunca por nome de container**: os nomes `atlasfile-*` são fixos e podem ser de outra instalação.
- Pasta apagada só se `repo_clone=created`, `install_dir` bater e não houver alteração local (`--force` para forçar) — **um clone de desenvolvimento é preservado por construção**, o que torna `make uninstall` seguro no repositório.
- Pasta de projetos nunca apagada; a exceção é um diretório criado pelo instalador e ainda vazio, removido com `rmdir` (que se recusa se algo tiver aparecido entre o plano e a execução).
- Docker preservado se sobrar qualquer outro artefato AtlasFile na máquina.
- Ollama no Linux é **listado, não executado** (o instalador oficial não traz desinstalador; executar `userdel`/`rm -r` às cegas seria chute).

## Bugs preexistentes encontrados e corrigidos

Todos com evidência medida, não inferidos:

1. **`--help` quebrado sob `curl | bash`** — fazia `grep '^#' "$0"` e nesse caminho `$0` é `bash`. Saída real da versão do main: `grep: bash: No such file or directory`.
2. **Shim do grupo docker no Linux** — `sudo command docker "$@"` depende de um executável `command`, que **não existe** no Debian/Ubuntu (verificado em `ubuntu:24.04`; existe no macOS, onde o shim nem roda). Todo `docker ...` seguinte falharia.
3. **`install.ps1` não fazia parse no PowerShell 5.1 como arquivo** — UTF-8 sem BOM lido como ANSI; o `✔` vira sequência com aspa embutida que encerra a string. Medido na VM que **o BOM conserta `-File` e quebra `irm | iex`**; a solução que sobrevive aos dois é fonte ASCII pura com glifos por code point.
4. **`install.ps1` morria numa máquina sem WSL** — `wsl.exe` acompanha o Windows mesmo sem a feature, então `Get-Command wsl` sempre acha; `wsl --status` escreve no stderr e sai 0, virando `NativeCommandError` terminante sob `ErrorActionPreference = Stop`. A detecção passou a olhar o conteúdo, normalizando o UTF-16 do `wsl.exe` (os NULs faziam todo `-match` falhar em silêncio).
5. **`install.ps1` abortava com `$env:LOCALAPPDATA` nulo** (sessão não interativa) — `Join-Path` lançava antes de qualquer passo.
6. **`make test-installer` estava vermelho no main** com shellcheck instalado (duas advertências do shim + uma constante órfã).

## Testes

`tests/installer/run.sh`: **17 → 70 casos**. Banner (arte sem carinha, 7 linhas por quadro, órbita fechada de 16 células distintas, contagem de glifos do orbe invariante, janela do cometa, cauda contígua, revelação monotônica do wordmark, `NO_COLOR` sem escapes, truecolor só com `COLORTERM`, render determinístico, orçamento de tempo ≤ 1,2 s). Manifesto (não rebaixa `created`, promove `preexisting`→`created`, chave/arquivo ausente lê vazio, mapa do contrato 0/100). Plano (tudo preexistente não remove nada, cask com aviso de `/Applications`, outra instalação preserva o Docker, sem manifesto nada de sistema é removível, Homebrew nunca vira ação, projects root com arquivos nunca entra, vazio+criado entra, volume segue a decisão, `--yes` sozinho não remove dependência, clone sujo preservado sem `--force`, diretório não criado pelo instalador preservado, nunca por nome de container, projeto honra `COMPOSE_PROJECT_NAME`, `un_dir_is_safe` recusa `/` e `$HOME`, headless exige decisão sobre o volume). Mais `--help` sob pipe.

Suíte completa verde: backend pytest, frontend 252, installer 70, shellcheck limpo.

## Validações reais (não são testes verdes)

- **Banner em terminal real**: capturas no Ghostty (truecolor) e com `COLORTERM` removido (fallback 256), mais o caminho sem TTY e com `NO_COLOR` (zero escapes). As correções 4, 5 e 6 do banner nasceram dessas capturas.
- **Uninstall contra o clone dev real**: projeto resolvido como `atlasfile-dev` pelo `COMPOSE_PROJECT_NAME`, 5 containers contados, clone preservado por não ter manifesto, 1133 itens do projects root preservados.
- **VM Windows 11 (build 26200) limpa, sem WSL e sem Docker**: os três caminhos de entrega do `install.ps1` (arquivo, `irm|iex` com `charset=utf-8`, e servidor sem charset) passam com a fonte ASCII; a detecção de WSL degrada com instrução acionável em vez de stack trace; os code points produzem `▄█▀▐▌●•✔✘` corretos no PowerShell 5.1.

## Limites declarados

- **Instalação completa no Windows não foi exercida**: exige WSL2 + Docker Desktop, elevação (a conta de teste não é administradora) e o diálogo de EULA do Docker Desktop no primeiro launch, que não é automatizável — o mesmo limite já registrado no plano da v0.43.0.
- **Remoção real de dependência de sistema** (`created` → removido) tem cobertura por stubs; nesta máquina Docker, git e Ollama são todos preexistentes, então o caminho executado de fato é o de preservação.
- Ollama no Linux fica listado, não executado (ver acima).
