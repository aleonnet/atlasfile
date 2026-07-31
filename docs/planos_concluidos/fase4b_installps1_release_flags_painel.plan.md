# Fase 4b — `install.ps1` alinhado à release: flags, ajuda e painel

**Status:** CONCLUÍDO em 2026-07-31 · **Sem bump** (regra do instalador; a
versão do app segue 1.0.0, release interna) · Branch
`fase4b-installps1-release-flags` a partir da main `68220b5`.

Fecha o lado Windows do plano de distribuição
(`docs/roadmap/distribuicao_build_imagens_ghcr.md`, seção "Fase 4b") e os
itens 2 e 3 da tabela de pendências do `docs/ROADMAP.md`. Plano revisado ANTES
da aprovação por 3 revisores adversariais locais (~40 achados; 3 mudaram o
desenho — ver "O que a revisão derrubou").

## Contexto

Desde a Fase 4a (PR #15) o comportamento real no Windows já era bundle+pull —
o `install.ps1` delega ao `install.sh` de raw/main via `--delegated` — mas o
ps1 ainda prometia clone na ajuda (`:16`, `:101`), não tinha como pedir o
caminho de contribuidor (regressão: `--from-source` inacessível do Windows,
`-Branch` de trabalho virava warn+ignore no `.sh`), não expunha `-Version`, e
o painel final ensinava `wsl -e` sem o usuário (item 3 do ROADMAP).

## Decisões (aprovadas nominalmente em 2026-07-31)

- **D1 — `-Registry` não nasceu.** Divergência declarada do texto do roadmap
  ("vira -Version/-Registry"): o `install.sh` não tem `--registry` — o
  override de imagem é `ATLASFILE_IMAGE` no `docker-compose.yml` (via de
  smoke, não alavanca de usuário); criar o seam reabriria a 4a validada. O
  texto do roadmap foi recalibrado na entrega.
- **D2 — `-FromSource` nasceu como correção de regressão** (não "paridade"):
  o caminho contribuidor no Windows estava quebrado desde o merge da 4a.
  `-Branch` continua, re-documentado "only with -FromSource"; encaminhamento
  segue incondicional (a regra warn+ignore vive no `.sh`, fonte única).
- **D3 — `-RepoUrl` nasceu, válido só com `-FromSource`** (aprovada a
  recomendação): fecha a dor real do item 2 (testar fork E2E no Windows). A
  premissa do roadmap "sem clone não há repo URL" só vale para o caminho
  release. Nasceu estrito (recusa sem `-FromSource`) porque não tem base
  instalada — diferente de `-Branch`, que tem histórico publicado e por isso
  mantém o tratamento leniente do `.sh`.
- **D4 — `-NoOllama` não nasceu**: flag já-depreciada que nunca existiu no
  ps1. De carona, corrigido o comentário falso do ps1 que dizia que o `.sh`
  sai com "Unknown flag" para `--no-ollama` (ele aceita e ignora).
- **D5 — CHANGELOG em seção própria** ("Instalador — … sem bump"), precedente
  da 4a; dentro de `[1.0.0]` ficam só correções de app.
- **D6 — `-Version` valida cedo no ps1** (mesmo regex do
  `af_validate_version`) e `-Version`+`-FromSource` é recusado na entrada.
  Limitação declarada: instalação legada com `.git` ignora `--version` em
  silêncio no lado `.sh` (não reaberto na 4b).
- **D7 — nome `-Version` mantido; custo declarado**: abreviações `-V/-Ve/-Ver`
  ficam ambíguas com `-Verbose` (idem `-F/-Fo` com `-Force`). Nada no
  repo/site publica abreviações.
- **D8 — errata, não reescrita**: o registro da 4a
  (`fase4a_installsh_sem_clone_bundle_pull.plan.md:36`) afirma que o ps1
  encaminhava `--repo-url` — **falso** (zero ocorrências de `RepoUrl` no ps1
  até esta fase). Fica registrado aqui; o histórico não foi editado.

## O que a revisão adversarial derrubou do rascunho

1. **A guarda `check_flags` NÃO cobria o header** (medição: extração devolvia
   conjunto vazio — linhas com `#` nunca casavam a âncora `\s{2,}`). O
   rascunho apoiava nela a garantia de que o clone não voltava à ajuda; o
   conserto da guarda virou entrega da fase.
2. **A asserção de `-NoOpen` como rascunhada seria falso-verde**: o
   `Start-Process` não passa por stub e o único observável era a mensagem do
   `catch` — que só aparece na falha. Caminho intestável virou mudança no
   produto (seam `Open-AfBrowser` com anúncio).
3. **D2 reclassificada de "paridade" para regressão em produção**, com data
   (merge do PR #15) — mudou a prioridade e o texto da fase.

## Mudanças entregues

- `install.ps1` — `param()` +4 (`-Version`, `-FromSource`, `-RepoUrl`,
  `-NoOpen`); validação cedo (shape + combinações) antes de qualquer fase;
  encaminhamento após o bloco existente (preserva a sequência literal que a
  bancada assere); header e `Show-Usage` reescritos (release por padrão,
  clone só atrás de `-FromSource`; parêntese do header fechado); fase 3
  anuncia pull (~290 MB, sem minutos) ou clone+build conforme `-FromSource`;
  `Open-AfBrowser` com anúncio e `-NoOpen`; painel com prefixo literal
  `wsl -u root -e`/`wsl -e` decidido por `$script:WslUser` (string única —
  join de array vazio geraria espaço duplo); comentários envelhecidos
  corrigidos (dry-run "git", "Unknown flag" do Ollama).
- `tests/installer/win/run.ps1` — cenários H2–H6 (22 asserções novas:
  encaminhamento + contrapositivos, validação cedo com Calls vazio, browser
  por anúncio, `-Help` — cenário que não existia), painel root no A4 +
  contrapositivo no T; `-NoOpen` nos 15 cenários de instalação completa (a
  bancada abria Edge real a cada rodada); comentários `:10` (powershell, não
  pwsh) e `:1087` (contagem hardcoded) corrigidos. Tudo ASCII.
- `tests/installer/check_consistency.py` — `option_flags` aceita `#` inicial:
  a metade "header" do `check_flags` volta a existir.
- Docs — `INSTALL.md` (lista nominal de flags do ps1), `README.md` /
  `README.pt-BR.md` (`-FromSource` no texto de contribuidor), `docs/ROADMAP.md`
  (itens 2 e 3 encerrados; **item 7 novo**: prova E2E do fluxo release no
  Windows físico, dono/gatilho/critério), roadmap de distribuição (Fase 4b
  entregue + recalibração da previsão `-Registry`), `CHANGELOG.md` (seção
  própria, D5).

## Prova (canal prlctl/SYSTEM na VM Parallels — o canal de registro do PR #17)

| Rodada | Resultado | Leitura |
|---|---|---|
| Baseline main (SYSTEM) | **206/0** | bate com o registro do PR #17; nomes salvos p/ diff |
| Baseline main (--current-user) | 194/12 | canal NÃO-elevado medido: as 12 falhas são a digital do caminho `wsl --install` que exige elevação — não usar este canal como baseline |
| Vermelho (bancada nova + ps1 vigente) | 212/16 | 16 falhas = só asserções novas; 206 da baseline intactas. Fato novo medido: `-Version banana` via `-File` rodava a instalação inteira (encaixe posicional) |
| Verde 1 | 226/2 | 2 defeitos meus, diagnosticados sem chute: needle partido pelo `Write-Wrapped` (mensagem da fase 3 encurtada) e asserção do help contradizendo a própria ajuda honesta (re-ancorada na forma incondicional) |
| **Verde final** | **228/0** | zero nomes da baseline perdidos (diff por nome, não por total) |
| Mutantes (6 no ps1, 1 rodada) | **221/7 — as 7 previstas** | M1 fwd `--version` removido; M7 `--from-source` incondicional; M2 painel sem `-u root`; M3 help com clone incondicional; M5 `-NoOpen` ignorado; M6 validação removida (mata 2). Zero dano colateral |
| Mutante M4 (local) | check_flags reprova `-Fake` | a guarda do header ressuscitada prova que reprova; bônus: o `check_assertions` local também pegou M2 (o literal `wsl -u root -e` sumiu do fonte) |

Restauração pós-mutantes **byte-exata** contra a cópia que produziu o 228/0;
`check_consistency.py` verde no final. Execution policy: o canal prlctl exige
`-ExecutionPolicy Bypass` no filho para script servido por `\\Mac\Home`
(UNC = remoto), medido nesta fase.

## Limitações declaradas

- A VM não roda WSL2/Docker (sem virtualização aninhada): o caminho
  `-Version → bundle → pull` de ponta a ponta no Windows só será provado no
  teste 100% do zero na máquina física — item 7 do ROADMAP, no fechamento do
  plano de distribuição (junto do re-tag da 1.0.0).
- CI roda a bancada win (powershell 5.1) e o `check_consistency` (job Linux)
  no push — validação pós-ordem de commit.
- `--version` segue ignorado em silêncio pelo `.sh` no caminho fonte/legado
  (`af_source_mode`); mitigado no Windows pela recusa cedo do ps1 (D6).
