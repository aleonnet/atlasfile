# Validação dos instaladores em máquina real — macOS e Windows 11 (v0.56.0)

**Concluído:** 2026-07-28
**Antecessor:** `installer_orquestracao_dois_lados_e_ux_unificada_v0550.plan.md`

## Contexto

A v0.55.0 entregou a orquestração dos dois lados, 6 jobs de CI verdes e uma bancada
de 116 asserções no bash e 73 no Windows. Faltava a única prova que o CI não dá:
**instalar e desinstalar numa máquina de verdade**.

Foram sete rodadas — quatro no macOS do dono do projeto, três num Windows 11 real.
**Nenhum** dos defeitos abaixo aparecia na bancada. Este documento registra o que o
uso real encontrou e por quê a bancada não via.

## O que a máquina real encontrou

### Impediam a instalação ou a desinstalação

| Defeito | Causa |
|---|---|
| `winget` instalava o Docker com **interface**, esperando clique em "Close" | faltava `--silent`; `--disable-interactivity` desliga os prompts *do winget*, não a janela do instalador |
| Contrato do Docker pedido no primeiro uso | faltava `--accept-license`, que aceita **na instalação** |
| Integração Docker↔WSL não subia sozinha | numa instalação recém-feita o Docker ainda não escreveu as preferências, e a função desistia calada |
| `git pull --ff-only` matava a instalação | clone divergente de um histórico reescrito; recusar está certo, morrer não |
| Desinstalar sem nada instalado abortava | e deixava o Docker instalado, porque o orquestrador parava antes do próprio escopo |
| Tecla de seta corrompia o caminho da pasta | `read` sem readline; escapes entravam no `.env` e derrubavam o compose |

### Diziam coisas que não eram verdade

- O **log era acumulado** entre execuções: "last lines of…" mostrava evidência de *outra* execução, logo abaixo de "Nothing was removed."
- **"Ollama preserved"** dito sem olhar a máquina
- O **volume de dados** apagado em silêncio, sem linha própria
- **`--doctor` dizia "package manager: none"** em qualquer macOS
- **"has local changes"** nunca dizia *qual* — e o que travava a pasta era um `.env.backup` do próprio instalador

### Onde os documentos ficam

No Windows eles nasciam em `/root/Documents` **dentro da distro**: invisíveis no
Explorer e reféns de um `wsl --unregister`. Passam a ficar na pasta Documentos do
Windows. A conversão é **léxica** e o resultado é **conferido pelo nome da pasta** —
numa reinstalação o `wslpath` devolveu um ponto de montagem do Docker Desktop.

### A tela

Um trilho só atravessando a fronteira (largura, `TERM`, `COLORTERM` e cor-sob-captura
viajam na delegação), divisória de handover tracejada e rotulada, régua do Windows
varrendo a rampa do produto, e falha de rede explicada em vez de despejada.

## Por que a bancada não via

| Classe | Por que escapava |
|---|---|
| Fonte do console, encoding, janelas de terceiros | não existem sob stub |
| Estado herdado entre execuções | a bancada sempre parte de sandbox limpo |
| Capacidades do terminal | sob captura não há tty, e a bancada não comparava as duas metades |
| Guardas cobrindo **um** fluxo | a varredura de calha rodava só na instalação; cinco buracos sobreviveram no uninstall |

## Método que passou a valer

1. **Toda guarda é provada contra uma cópia mutada.** Se não reprova o defeito que
   diz guardar, não entra. Três guardas foram descartadas ou reescritas por isso.
2. **Guarda de tela, não de fonte.** Regex de uma linha não pegou um `Write-Host ""`
   depois de um `}`. A varredura passou a olhar a saída.
3. **Assertiva ancorada no fato, não na forma.** Quatro reprovaram código correto por
   estarem presas a um literal ou a uma distância em caracteres.
4. **Divergência entre plataformas se reproduz em container**, não por hipótese.
5. **O que só o CI enxergava virou guarda local**: substantivo plural
   (`PSUseSingularNouns`), aspa não fechada, e variável sombreando glifo global.

## Resultado

- Bancada: **196** asserções no bash (eram 116), **~200** no Windows (eram 73)
- CI verde nos 6 jobs
- Instalação e desinstalação validadas ponta a ponta nas duas plataformas, incluindo
  a propriedade que nunca tivera prova real: **Docker Desktop instalado do zero
  (`created`) e removido pela desinstalação**

## Pendências herdadas

- Site (`~/Development/atlasfile-website`) ainda publica `--with-ollama` em 4 lugares;
  funciona pelo caminho de depreciação, mas deveria ser atualizado
- `docs/ROADMAP.md` tem duas linhas desatualizadas (v0.52.0 e v0.53.0)
- Branch protection no `main` continua desligada
