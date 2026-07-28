# Desinstalação em Linux com stack real — v0.56.2

## Contexto

A v0.56.1 fechou a paridade entre os dois instaladores. Sobrava um buraco de
validação que nenhuma versão anterior tinha coberto: **o `--uninstall` nunca
tinha sido exercitado contra uma stack de verdade**. As validações de v0.54.0 a
v0.56.1 usaram sandbox, stub ou máquina sem containers, e todas rodaram em
macOS ou Windows.

Isso foi possível agora porque a virtualização aninhada não é necessária para
containers Linux: uma VM Linux roda Docker nativo. A memória do projeto
generalizava "nenhuma VM aqui roda Docker" a partir de medições em convidados
Windows e macOS — a afirmação estava larga demais.

Ambiente: VM Ubuntu 24.04 ARM64 em **lima** (Apple Virtualization), 4 vCPU,
8 GiB, disco no SSD externo. Instalação do zero pelo one-liner, sem Docker.

## O defeito

Numa desinstalação logo após a instalação, o estado final medido foi:

| | |
|---|---|
| 5 containers | **ainda rodando** (API respondendo) |
| volume + 3 imagens construídas | **ainda lá** |
| clone `~/AtlasFile` | **apagado** |
| manifesto `~/.atlasfile/host-prereqs` | **apagado** |

**O desinstalador apagou os meios de reverter e falhou em reverter.**

Cadeia causal:

1. `un_collect` trancava todo o retrato do Docker atrás de `docker info` **sem
   sudo**. No Linux o grupo `docker` só vale no próximo login — janela em que
   alguém desinstala. Plano cego: `0 container(s)` com cinco no ar.
2. Volume invisível → a exigência headless de `--purge-data`/`--keep-data`
   evaporou, e o volume não aparecia em nenhuma das duas seções do plano.
3. `docker compose down` falhava por permissão e `un_execute` **seguia**,
   executando `rm-clone` e `rm-state`.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Reusar `ensure_docker_group_linux` no uninstall | **Não** | Ela roda `usermod -aG` e grava `docker_group created`. Desinstalar que cria grupo e registra artefato é o oposto do contrato |
| Como alcançar o socket no uninstall | **`af_docker_shim_linux`**, novo | Só o shim: sem grupo, sem manifesto, sem `fail`. Usa `sudo -n`; pede senha só em `run_uninstall`, com terminal, e nunca aborta |
| Falha ao descer a stack | **Barreira: para tudo** | Perder a ferramenta é pior que não usá-la. Clone e manifesto são exatamente o que se precisa para tentar de novo |
| Contradição `--keep-data` × instalação nova | **Registrar, não corrigir** | Precisa de decisão de desenho, não de conserto pontual |

## Mudanças

- `install.sh` — `af_docker_shim_linux` extraída; `ensure_docker_group_linux`
  passa a usá-la mantendo o `ensure_sudo` no caminho de instalação (onde não ter
  privilégio é fatal)
- `install.sh` — `run_uninstall` monta o retrato do Docker **antes** do
  `un_collect`, e avisa na tela quando não consegue
- `install.sh` — `un_execute` para quando `compose-down` falha, explicando a
  parada e o caminho de volta
- `tests/installer/run.sh` — 5 asserções novas (197 → 202)

## Verificação

`make test` verde. Na VM, com stack real, os cinco caminhos:

| caminho | resultado |
|---|---|
| `--uninstall --dry-run` | 5 containers e o volume no plano (antes: 0 e nenhum) |
| `--uninstall --yes` sem flag de dados | `rc=1` exigindo decisão; **nada tocado** |
| `--uninstall --yes --keep-data` | stack fora, **volume sobrevive**, upstream preservadas, documentos intactos |
| `--uninstall --yes --purge-data` | índice apagado |
| `--purge-data --remove-deps` | Docker (binário e pacote) e grupo revertidos, `git` preexistente preservado, documentos intactos |

Guardas provadas com mutante: remover a barreira do `un_execute` reprova; devolver
o `usermod` ao shim reprova com `USERMOD:1`.

**Erro de método registrado:** minha primeira espera pelo fim da instalação
olhava `~/.atlasfile/last-run.log`, que **sobrevive** ao `rm-state` (o `rmdir`
falha com o log dentro). Li estado velho como novo e agi sobre uma instalação
pela metade. Passou a esperar por `Install finished` no log da execução.

## Pendências

1. **`--keep-data` promete reuso que a instalação recusa** (`install.sh:1144`
   × `install.sh:2311`). O `--keep-data` remove o clone, então a instalação
   seguinte é sempre "nova" e a guarda de volume órfão dispara. Os remédios
   sugeridos anulam o reuso. Opções: marcar o volume preservado no estado do
   host e liberar a guarda para ele; ou perguntar em vez de falhar; ou parar de
   prometer reuso.
2. **A estimativa de tempo está calibrada para outro cenário.** O instalador
   fala em café e o `INSTALL.md` em ~15 min; medido aqui: **48s de build,
   2m10s no total**. Medir em mais uma máquina antes de mudar o texto.
3. `install.ps1` sem `-NoOpen`, `-RepoUrl`, `-NoOllama`; painel final usa
   `wsl -e` sem `-u root`. As 6 falhas pré-existentes da bancada Windows sob
   `prlctl exec`.
