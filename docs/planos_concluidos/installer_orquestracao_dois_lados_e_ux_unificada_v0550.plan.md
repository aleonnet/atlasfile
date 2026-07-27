# Instaladores: orquestração dos dois lados e UX unificada (v0.55.0)

**Status:** concluído em 2026-07-27 · **Pendente de prova real:** E2E na máquina Windows

---

## Contexto

Um `-Uninstall -RemoveDeps` rodado numa máquina Windows 11 real produziu um log que
mostrou quatro coisas erradas de uma vez: o plano dizia "Docker preserved" e o Docker era
apagado logo depois; o Ollama não aparecia em nenhuma seção do plano mas era removido; a
saída do desinstalador do Docker despejava na tela por cima do nosso spinner; e havia dois
banners diferentes na mesma execução.

Ao ler os dois instaladores por inteiro (`install.sh` 1457 linhas, `install.ps1` 1161)
apareceu um defeito pior, que ninguém tinha visto: **cancelar o plano não impedia a
remoção do Docker**.

## A raiz única

Existem **dois manifestos** e **dois motores de decisão**, e só um imprimia plano:

| Escopo | Manifesto | Decisão |
|---|---|---|
| Windows | `%LOCALAPPDATA%\AtlasFile\host-prereqs` | `install.ps1` |
| WSL/Linux | `~/.atlasfile/host-prereqs` | `un_build_plan` no `install.sh` |

O `install.ps1` delegava plano e confirmação ao `install.sh` e só depois agia sobre o
manifesto do Windows — **sem plano, sem confirmação e sem ler o código de saída**.

## Por que são dois instaladores (e por que não um)

São dois sistemas operacionais sem gerenciador de pacotes, raiz de filesystem, PATH ou
espaço de processos em comum. O caso decisivo: **o `install.sh` não pode instalar o WSL,
porque sem WSL não existe bash para executá-lo**. O `install.ps1` não é uma segunda
implementação — é o *bootstrapper* que cria as condições para o instalador de verdade
existir.

| Alternativa | Por que não |
|---|---|
| Só `install.sh`, rodado dentro do WSL | Exige WSL, distro, Docker Desktop e integração já prontos — o "passo 0" que a v0.43.0 removeu de propósito |
| Só `install.ps1`, tudo via `wsl -e` | Duas implementações completas do mesmo instalador. Os defeitos deste ciclo são o preço de um pedaço **pequeno** de lógica duplicada |
| Um binário multiplataforma | A alternativa SOTA real (é o que o Claude Code faz). Custa build, assinatura e distribuição por arquitetura; o produto aqui é um `docker-compose`. Registrado, não é este ciclo |

## Benchmark consultado

| Referência | Como atravessa a fronteira | Uninstall |
|---|---|---|
| **Claude Code** (`bootstrap.ps1`) | Não delega ao WSL: chama o binário nativo, captura `$LASTEXITCODE` e **propaga** | Dentro do binário |
| **cargo-dist / uv** | `installer.sh` e `installer.ps1` **gerados do mesmo template**, com unificação explícita de comportamento; **receipt JSON** por instalação | O receipt alimenta o desinstalador |
| **OpenClaw** | Self-contained; saída de terceiro capturada e mostrada só na falha | Não tem |
| **rustup** | Uma frase de plano + **um** `Continue? (y/N)`. O issue #3332 é a nossa classe de defeito: rodado de dentro do WSL, "reporta sucesso mas deixa arquivos para trás" | — |
| **apt / MSI** | Plano inteiro antes de **uma** confirmação; **1602** = usuário cancelou, **3010** = reinício pendente | — |

**Conclusão aplicada:** ninguém atravessa a fronteira Windows→WSL de forma interativa.
Quem atravessa, atravessa **não-interativo e propaga o código de saída**.

## Arquitetura entregue

```
install.ps1 -Uninstall
  ├─ 1. banner único (o install.sh não desenha sob --delegated)
  ├─ 2. FATOS: wsl -e … --uninstall --delegated --plan-only --host-extra k=v,…
  ├─ 3. UM plano, com a seção do WSL e a do Windows
  ├─ 4. UMA pergunta (volume de dados + "executar?")
  ├─ 5. execução não-interativa; exige exit 0 E a linha-sentinela
  ├─ 6. lado Windows executa só o que o plano confirmado mostrou
  └─ 7. UM veredito → 0 / 1602 (cancelado) / 3010 (reinício pendente)
```

**Decisão que substituiu uma medição.** A pesquisa não achou documentação oficial de que o
`wsl.exe` propague o código de saída do comando Linux, e o contrato inteiro dependeria
disso. Em vez de medir e torcer, o `install.sh` imprime `ATLASFILE_UNINSTALL: <estado>` nos
caminhos terminais e o `install.ps1` exige **as duas provas**. Um código engolido faz o
instalador **falhar fechado** — nunca remover nada. É mais robusto que a propriedade que
substitui.

**Detalhe factual:** `exit` em bash é truncado para 8 bits (1602 → 66), então o bash usa
**10** para "cancelado" e o `install.ps1` traduz para o código MSI.

## Defeitos corrigidos

| # | Defeito | Evidência |
|---|---|---|
| S1 | **Cancelar não impedia a remoção do Docker**: `return 0` no cancelamento + código de saída nunca lido | Leitura de `install.sh:805` e `install.ps1:772` |
| S2 | Plano dizia "Docker preserved" e o Docker era removido | Log da máquina real + manifesto colado pelo usuário |
| S3 | Ollama em nenhuma das duas seções, e mesmo assim removido | `install.sh:618-628` com `st=""` |
| S4 | **A pasta de instalação nunca era removida** | `git check-ignore` reprovando `config/api_keys.json` e `backend/runs/` |
| S5 | Dois banners, artes diferentes, cauda de cometa no quadro final, luas trocadas | Traço de `New-AfFrame` com `N = Total-1`; `AF_ORBIT_START` 2 vs 10 |
| S6 | Saída de terceiro na tela com o spinner por cima | Log da máquina real (o instalador do Docker se relança do TEMP) |
| S7 | Dois vereditos finais, o primeiro falso | Log da máquina real |
| S8–S12 | Rótulo duplicado; lado Windows sem plano; `--dir` só de um lado; falha do Ollama sem diagnóstico | Leitura dos dois fontes |
| S13 | **Pergunta do Ollama reaparecia dentro da distro** e um "sim" instalava um duplicado | `install.ps1:1132-1135` não repassava nada que a silenciasse |

## UX: o que veio do `mac_env_install.sh`

O nosso instalador de ambiente (3390 linhas) foi lido por inteiro e virou a fonte da
linguagem visual, **em ANSI puro nos dois lados**.

Adotado: calha vertical (`│`), régua de fase varrida com a rampa do produto, barra de fase
viva apagada antes de cada mensagem, cards, placar final, "próximos passos" condicionais ao
que de fato aconteceu, relatório da execução em arquivo, `trap` global de cursor, `curl`
endurecido, e o padrão de **medir antes de prometer** (`winget list` antes de remover, como
ele faz com `brew list --cask`).

Rejeitado com motivo:

| Descartado | Por quê |
|---|---|
| **`gum`** | Baixa binário de terceiro a cada execução e **não tem equivalente no PowerShell** — recriaria a divergência de UX que este ciclo conserta |
| Catálogo/seleção por categorias | O AtlasFile instala uma stack só |
| `shimmer` em toda linha | 9 quadros por linha; com banner animado, vira ruído |

**Adaptação declarada:** o mac-env conta **itens** na barra porque instala N pacotes
discretos. Aqui o que é discreto e conhecido são as **5 fases**; inventar um total de
passos seria número arbitrário.

## Modos novos

`--doctor` / `-Doctor` (read-only, os dois lados, sai `!= 0` se algo está quebrado),
`--plan-only`, `--dry-run` / `-DryRun`, `--verbose` / `-Verbose`.

## Testes

- Bancada bash **79 → 119**; bancada PowerShell **73 → 100+**.
- O stub do `wsl` passou a **atravessar a fronteira** (devolve plano, fatos e sentinela).
  Sem isso o `install.sh` nunca rodava na bancada e o plano não existia em asserção
  nenhuma — **a razão estrutural de o defeito ter passado**.
- Cenários que travam o crítico: lado WSL cancelou → nenhum `winget uninstall`; código
  engolido → falha fechada; plano ilegível → para antes de tocar em qualquer coisa.
- `check_consistency.py`: paridade de **arte** e de **UI** entre os dois instaladores,
  ambas provadas numa cópia isolada (injetar a divergência e conferir que reprova).
- CI: guarda de `Invoke-Native` estendida ao `Invoke-NativeCapture`; a do `Stop-Installer`
  aceitava só um dígito e reprovava `1602`; passo novo cobrando que o git ignore o que o
  instalador gera.

## Defeitos que o próprio CI achou durante o ciclo

1. `Stop-Installer\s+\d` reprovava `1602` — a guarda nasceu quando os códigos tinham um
   dígito só.
2. `doc_version` dizia "ok" para ferramenta presente porém quebrada (o `| head -1`
   mascarava o código de saída), e o teste que cobria isso dependia do ambiente: apagar o
   stub do docker não simula ausência num runner que traz `/usr/bin/docker`.
3. `catch` vazio no `Write-Rule`, pego pelo PSScriptAnalyzer.

## O que continua sem prova

**O E2E na máquina Windows real.** Nenhuma VM aqui roda Docker, e elevação, `wsl --install`,
winget e o diálogo do Docker Desktop só existem lá. Roteiro:

1. Instalar pelo one-liner recomendado.
2. `-Doctor` — conferir que ele descreve os dois lados.
3. `-Uninstall -RemoveDeps`, **responder "n"** → nada pode ser removido, saída `1602`.
4. Repetir respondendo "y" → conferir que a pasta sumiu, o Docker saiu, e que o WSL e os
   documentos ficaram.
