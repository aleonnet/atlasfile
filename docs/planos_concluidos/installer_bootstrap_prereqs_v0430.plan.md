# installer_bootstrap_prereqs_v0430 — instalador bootstrapa pré-requisitos + Ollama opt-in (v0.43.0)

Concluído em 2026-07-23. Fecha o item do ROADMAP "Instalador bootstrapa os próprios pré-requisitos" e remove o step 0 ("Before you start") do site — o one-liner virou de fato autossuficiente.

## Decisões (do usuário)

- **Política `--yes` conservadora**: `--yes` sozinho NUNCA instala software de sistema (falha com instrução, sugerindo a flag); `--install-deps` autoriza o bootstrap headless. Automação nunca ganha sudo por acidente.
- **Ollama sempre opt-in**: `--with-ollama` ou pergunta interativa (default "n"); modelo `--ollama-model` (default `gemma4:12b` — existência confirmada ao vivo na Ollama local do usuário; override por `ATLASFILE_OLLAMA_MODEL`). Falha do Ollama nunca derruba a instalação (a stack já está no ar).
- **Idioma padrão dos instaladores: en-US** — todas as mensagens do `install.sh` e `install.ps1` traduzidas nesta rodada (alinhado ao README EN default).
- **Idempotência com sinalização**: itens presentes imprimem ✔ com versão; upgrades disponíveis viram aviso informativo (`hint_upgrades`) — com a lição do mac-env-setup: casks auto-atualizáveis (Docker Desktop, Ollama) ficam FORA dos hints de upgrade (receipt do brew atrasa e daria falso positivo).
- **Paridade mínima do Windows**: `install.ps1` ganhou `param(-Yes,-InstallDeps,-WithOllama,-OllamaModel)`, oferta de `wsl --install` (só elevado; nunca auto-eleva sob `iex`), Docker Desktop via winget + espera do daemon (300s), Ollama via winget no lado Windows (containers alcançam via host.docker.internal) — resto segue delegado ao install.sh no WSL.

## Práticas emprestadas do mac-env-setup

Contrato `0/100/1` (instalou/já presente/falhou) com presença-primeiro; `BREW_PREFIX` por arquitetura + `brew shellenv`; Homebrew com `NONINTERACTIVE=1`; dupla checagem app-em-/Applications OU cask (cobrindo o nome legado); nunca sudo no macOS; confirmação explícita antes de tocar o sistema. A lacuna do mac-env-setup (espera do daemon) foi escrita aqui: `launch_docker_desktop_mac` (open -g -a) + `wait_docker_daemon` (loop `docker info`, 300s no primeiro launch com aviso do diálogo EULA/helper — não automatizável; timeout orienta re-rodar, idempotente).

## Achados pagos em campo (smoke real)

1. **Container/CI roda como root sem sudo** — `sudo` hard-coded quebrava; helper `as_root` cobre root e não-root.
2. **Sem systemd, `systemctl` não pode ser fatal** — vira aviso; `--bootstrap-only` valida INSTALAÇÃO (não daemon): com daemon inverificável, avisa e sai 0.
3. `/Applications/Docker.app` real da máquina não é stubável em teste — caminho virou injetável (`DOCKER_APP_PATH`), mesmo padrão do `TTY_DEV`.

## Testes

- `make test-installer` (novo, no `make test`): `bash -n` + shellcheck (skip com aviso se ausente) + runner puro-bash `tests/installer/run.sh` — **17 casos** com PATH de stubs (fakes de brew/docker/apt/ollama gravando chamadas): detect_os, política do confirm (--yes recusa / --install-deps autoriza / interativo y/N via `TTY_DEV`), contrato 0/100/1 (git, docker mac presente/ausente, ollama), skip de modelo já baixado, parser de flags. O script é sourceável como lib via guarda `ATLASFILE_INSTALL_LIB=1`.
- **Smoke Linux real** em `ubuntu:24.04` limpo: `--yes --install-deps --bootstrap-only` → apt→git instalado, get.docker.com executado de verdade (17s), limite do daemon (sem systemd) tratado com aviso e EXIT=0.
- **Smoke host completo** (máquina com tudo): mesmos ✔ de sempre + hints, zero prompts novos.
- Matriz E2E manual (documentada aqui): (a) máquina completa = regressão zero-prompt; (b) `env PATH=/usr/bin:/bin` = smoke de UX de recusa; (c) VM macOS limpa antes de release que toque o instalador (único teste verdadeiro de Homebrew→cask→primeiro-launch); (d) Windows em VM/snapshot; (e) Ollama com modelo pequeno (`--ollama-model gemma3:1b`) para validar fluxo sem 8 GB.

## Companheiros

- `docker-compose.yml`: `extra_hosts: host.docker.internal:host-gateway` no serviço api — sem isso o `OLLAMA_BASE_URL` default não resolve em Docker Engine Linux (inócuo no Desktop).
- **Site**: step 0 removido (`install.html`), 6 chaves `install.req.*` fora dos 2 dicionários, step 1 reescrito ("no prerequisites to prepare"), flags `--install-deps`/`--with-ollama` no bloco de flags, troubleshooting do Docker atualizado, simulação do terminal com o título novo do passo 1 — validado em browser real nos 2 idiomas.
- ROADMAP consolidado como documento único de pendências (dashboard/observabilidade, E2E pendentes, website, decisões aguardando o usuário).

## Limites conhecidos

Primeiro launch do Docker Desktop (mac/win) exige aceitar diálogos GUI (EULA/helper) — o instalador abre o app, espera 300s e orienta; distros sem apt/dnf caem no fail com link (sem regressão); grupo docker no Linux vale a partir do próximo login (shim `sudo docker` cobre o script); PSScriptAnalyzer não rodado (sem PowerShell no host de dev).
