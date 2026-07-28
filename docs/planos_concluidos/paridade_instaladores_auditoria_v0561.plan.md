# Auditoria de paridade `install.sh` × `install.ps1` — v0.56.1

## Contexto

Os dois instaladores foram validados em máquinas reais (macOS e Windows 11) na
v0.56.0. A pergunta desta auditoria é outra: **as duas metades leem como o mesmo
produto?** Quem instala no Windows vê os DOIS na mesma tela — o `install.ps1`
desenha as fases 1–3 e entrega ao `install.sh` dentro do WSL, que desenha as
fases 1–4 —, então qualquer divergência aparece numa única sessão.

Método: leitura integral dos dois fontes (2.492 + 2.171 linhas), execução dos
caminhos read-only do `install.sh`, renderização dos quadros do banner pelas
funções reais, `check_consistency.py`, e leitura das duas bancadas.

**Achado estruturante: a guarda estava verde e 26 divergências viviam sob ela.**
`check_art_parity` compara TABELAS (órbita, cometa, rampa, hexes, índice de
repouso) e `check_ui_parity` compara EXISTÊNCIA de primitivas. O que divergia
eram os ALGORITMOS que consomem essas tabelas e o USO das primitivas — duas
camadas que nenhuma guarda olhava.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Linha `(Windows / WSL2)` no banner do `.ps1` | **Manter** | Decisão do dono. Os dois banners nunca aparecem juntos (o `install.sh` roda com `--delegated` e não desenha o dele), então a linha não custa paridade visível e identifica a plataforma. A guarda a perdoa explicitamente **e cobra que continue existindo** |
| Citação dos argumentos que viajam no `bash -c` | Aspas **duplas**, com `~` resolvido para `$HOME` antes | Aspas simples protegem o espaço mas matam o til, e o manifesto grava literalmente `~/AtlasFile`. Uma função só (`ConvertTo-AfShArg`), não duas regras |
| Guarda para a frase do `curl` no `--help` | **Não criar** | Guarda que casa prosa é frágil e daria falso positivo na própria correção, que agora cita `curl` numa cláusula negativa. A invariante aqui não é mecânica |
| Docker órfão com o WSL mudo | **Relatar, nunca remover** | Tentei remover automaticamente e a bancada Windows reprovou, com razão: "não li o plano" ≠ "não há instalação do outro lado". `install_dir` não desempata (só existe desde a v0.55.0, então ausente também significa instalação antiga). Medido na VM real |
| Citação dos argumentos | **Citar só quando precisa** | Citar sempre quebrou 6 assertivas e tirou a expansão do til. Caminho simples viaja nu, como na v0.56.0 já validada em máquina real; só espaço e til pedem aspas |
| `docs/roadmap/plan_one_line_installer.md` | **Marcar superado, não mover** | O CHANGELOG histórico referencia esse caminho; mover quebraria o registro |
| Bump | **patch** (0.56.1) | Correções e alinhamento visual. Sem feature nova, sem breaking change |

## Mudanças

### Funcionais
- `install.ps1` — Ollama fora do plano do `-DryRun` (a fase que o instalava saiu na v0.55.0)
- `install.ps1` — quando o lado WSL não responde, o que o manifesto registra como nosso (Docker Desktop, Ollama) é **relatado com os passos**, em vez de o instalador abortar em silêncio deixando um órfão sem pista
- `install.ps1` — `--verbose` encaminhado ao `install.sh`
- `install.ps1` — `ConvertTo-AfShArg` nos 4 pontos que montam `--dir` e no `--projects-root`
- `install.sh` — comentário do `RC_CANCELLED` descrevia uma tradução que o `install.ps1` nunca fez

### Trilho
- `install.sh` — plano do `--dry-run` na calha (`af_plan_row`, rótulo de largura fixa) e vão duplo removido
- `install.sh` — `rail_end` nas três saídas do `--uninstall` (nada a fazer, cancelado, falhou), respeitando `DELEGATED`
- `install.ps1` — 8 linhas vazias cruas → `Write-Gut ""`; separador antes da régua WSL2; placar do `-Doctor` numa linha só; manifesto com a calha na coluna 1 e campo de 16; barra de fase e `Wait-Spinner` na calha; blocos de orientação de falha via `Write-Wrapped`/`Write-Gut`

### Banner
- `install.ps1` — ordem de escrita passa a ser a do `af_row_cells`: cometa < orbe < texto < luas (o cometa sai de TRÁS do orbe)
- `install.ps1` — cauda contígua de 3 células com cabeça branca, no lugar da amostragem do trajeto que o `install.sh` registra como medida e rejeitada
- `install.ps1` — órbita avança em todo quadro a partir da ignição (as luas congelavam durante o voo do cometa)
- `install.ps1` — ignição `row < n+2` e brilho especular com a fórmula e a linha de destaque do bash
- `install.ps1` — revelação do texto conta CARACTERES (`hc - 24`), não colunas

### Documentação
- `install.sh` — cabeçalho e `--help` deixam de prometer instalar `curl`; parágrafo PT-BR sai do meio da lista de flags; uninstall/doctor/dry-run entram no sumário
- `INSTALL.md` — bloco `-DryRun` do Windows; lista de flags do `.ps1` completada com ponteiro para `-Help`; bullet órfão removido; exemplos de `PROJECTS_HOST_ROOT` passam a usar `AtlasFileProjects`
- `README.md` / `README.pt-BR.md` — ponteiro para `install.ps1 -Help`; default recomendado alinhado ao do instalador
- `docs/roadmap/plan_one_line_installer.md` — banner SUPERADO com tabela do rascunho × entregue
- `docs/ROADMAP.md` — menção a `--with-ollama` corrigida
- `docs/11_scripts_and_operations.md` — seção dos instaladores (o `INSTALL.md` aponta para essa página como a visão consolidada dos scripts)

### Guardas — todas provadas com mutante
| Guarda | Mutante que a prova |
|---|---|
| `check_frame_parity` (nova) | luas congeladas; ignição adiantada; linha de plataforma removida |
| Varredura de calha do bash, ampliada | `printf '    • repository …'` reintroduzido |
| Fechamento do trilho, cobrindo `--uninstall` real | `rail_end` removido do caminho "nothing to do" |
| `check_gutter_holes` na faixa inteira do `.ps1` | `Write-Host ""` numa régua; marca apagada; faixa curta |
| Cores do cometa na paridade de arte | cabeça `ffd0c4`; cauda com cor trocada |
| `make test-installer` | roda `check_consistency.py` e o parse do `.ps1`, que só existiam no CI |

**Lição:** `check_gutter_holes` nasceu **cega** nesta rodada — a busca pela marca
casava com a menção a ela dentro do próprio comentário de abertura, e a faixa
varrida virou 1 linha; dois mutantes passaram verdes. Ganhou âncora de início de
comentário e um **piso de sanidade** que grita se a faixa for pequena demais.
Guarda que pode varrer nada precisa dizer quando varre nada.

## Verificação

```bash
make test-installer          # 197 bash + 12 checagens + parse do .ps1
```

Executado e verde. Os caminhos medidos na tela (`--dry-run`, `--uninstall`
nothing-to-do, delegado) foram re-executados e conferidos linha a linha.

### Validação na VM Windows 11 real

Rodada na VM Parallels (`prlctl exec`, Windows PowerShell **5.1.26100.8875**),
sempre contra a baseline da `main` no mesmo canal:

| | passou | falhou |
|---|---|---|
| `main` (baseline) | 183 | 6 |
| 1ª rodada da branch | 179 | 13 → **7 minhas** |
| 2ª rodada (citação corrigida) | 185 | 7 → **1 minha** |
| **3ª rodada (final)** | **186** | **6 → zero minhas** |

As duas reprovações foram achadas **só** porque a bancada rodou em Windows real:
a citação sempre-com-aspas e a remoção automática do órfão passavam no macOS.

## Pendências

1. **6 falhas pré-existem na `main`** neste canal (grupo do fechamento de
   trilho/calha). Hipótese **não provada**: sob `prlctl exec` a saída é
   redirecionada e roda como `nt authority\system`, então `$AfTrueColor` é falso
   e o desenho degrada. Não investigadas.
2. **Superfície de flags (achado A4, fora do escopo aprovado):** o `install.ps1`
   não tem `-NoOpen`, `-RepoUrl`/`ATLASFILE_REPO_URL` (impede testar um *fork*
   E2E; uma *branch* funciona via `ATLASFILE_SH_URL` + `-Branch`) nem
   `-NoOllama` depreciada.
3. **`--dry-run` do `install.sh` se contradiz:** diz `✘ Docker … daemon does not
   answer` e, quatro linhas abaixo, `✔ none — everything needed is already
   here`, porque a checagem de "faltando" só testa `command -v docker`. Fora do
   escopo aprovado.
4. **`pwsh` passou a ser dependência opcional da bancada local** (instalado nesta
   máquina via `brew install powershell`). Sem ele, `check_frame_parity` se
   anuncia pulado — nunca some calado.
