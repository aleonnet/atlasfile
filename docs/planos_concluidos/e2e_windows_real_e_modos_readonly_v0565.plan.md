# E2E do instalador em Windows 11 real, e os defeitos que ele achou — v0.56.5

Primeiro teste do `install.ps1` **com a stack de verdade no ar num Windows 11
real**. Estava bloqueado por hardware desde a v0.54.0: exige Hyper-V →
virtualização aninhada em convidado Windows, que nem Parallels nem UTM entregam
em Apple Silicon.

## O que passou

| Cenário | Resultado |
|---|---|
| Instalação do zero (sem WSL, sem Docker) | ✅ 15m56s — WSL2, Docker Desktop e os 5 containers |
| Reinstalação por cima | ✅ 26s — `.env`, senha do OpenSearch e API key **preservados** |
| `-Uninstall -DryRun` | ✅ plano dos dois lados, nada tocado |
| `-Uninstall -KeepData` | ✅ removeu stack/clone/backups; preservou volume, documentos e Docker |

Medições novas: build **1m05s**, lado Linux **1m54s**, Docker Desktop **10m54s**.

## Os quatro defeitos

### 1. Os modos read-only disparavam o instalador do WSL do Windows

Já corrigido na v0.56.4, mas **a correção estava incompleta** e o teste provou:
`Test-WslUsable` chamava `--status` e `-l -q` em sequência, sempre. Medido: **o
`wsl --list` também dispara** o prompt "Pressione qualquer tecla para instalar
Subsistema do Windows para Linux" quando a feature está ligada sem distro. A
correção só trocava a origem do prompt.

Agora há **curto-circuito obrigatório**: se o `--status` já disse "is not
installed", a função retorna antes de tocar em `-l`.

### 2. O próprio script de reset disparava o mesmo prompt

`scripts/reset-wsl-windows.bat` chamava `wsl --list --verbose` e `wsl --shutdown`
sem guarda — o mesmo defeito que eu tinha acabado de corrigir no `install.ps1` e
reproduzi no meu próprio script. Duas vezes na tela do usuário.

Substituído por fontes **read-only de verdade**:
- `dism /online /get-featureinfo` para saber se a feature está ligada
- **o registro** (`HKCU\...\Lxss`, chave `DistributionName`) para listar distros

Nenhuma das duas toca no `wsl.exe`. E o `--shutdown`/`--unregister` só são
chamados quando há o que parar ou remover.

### 3. O reset dizia "Docker Desktop IS installed" e "done" sem remover nada

`winget list ... >nul` + `if errorlevel 1`: **o winget sai 0 mesmo quando não
acha** o pacote — escreve "No installed package found matching input criteria" e
considera que o comando funcionou. Numa máquina sem Docker o script anunciou que
estava instalado, tentou remover, não achou o desinstalador, caiu no winget que
não achou o pacote, e imprimiu **"done"**.

Mesma classe do `Get-Tool wsl` e do `wsl --status`: **usar código de saída onde só
a mensagem serve**. Agora a detecção casa o id na **saída**, e o resultado é
conferido depois de remover, em vez de anunciado.

### 4. O plano do uninstall ignorava a decisão já tomada

Com `-KeepData` na linha de comando, o plano imprimia `data volume ... — still
your call (--purge-data erases the index, --keep-data keeps it)`. O texto de
"ainda em aberto" é honesto quando nada foi decidido e mentira quando já foi: a
flag não chegava ao `--plan-only`. Agora chega.

## Duas correções de texto

- **Estimativas de tempo** (item 5 do roadmap, gatilho atingido com a 3ª
  medição): `~15 min` acertava o total por coincidência e o atribuía ao **build**,
  quando ~11 dos 16 minutos eram o download do Docker Desktop. Recalibrado para
  `~1-2 min`, com as três medições registradas no comentário.
- **A mensagem do café** saía igual na reinstalação, onde o build levou 3s. Passou
  a depender de `CLONE_STATE`.

## Uma mudança de default

Os documentos nasceram em `C:\Users\<user>\OneDrive\Documentos\AtlasFileProjects`
— a pasta Documentos do Windows estava redirecionada para o OneDrive, então os
documentos **e o estado operacional `_ATLASFILE`** ficaram dentro de uma pasta
sincronizada, que o AtlasFile reescreve com frequência.

`Get-AfProjectsRoot` passa a detectar Documentos dentro do OneDrive (pelas
variáveis `OneDrive*` e pelo caminho) e cai para `%USERPROFILE%`. Segue visível no
Explorer, sem sincronização. Quem quer na nuvem passa `-ProjectsRoot`.

## Guardas

Na bancada Windows, provadas na ordem certa — **o commit dos testes foi ao CI
sozinho e reprovou** (`casou /-e bash/ e nao devia`, três vezes), e só o commit
seguinte ficou verde:

- `-DryRun`/`-Doctor` sem WSL não chamam `wsl -e`
- feature ligada com zero distro conta como inutilizável
- **curto-circuito**: sem WSL, nem `wsl -l` é chamado
- `-KeepData` chega ao `--plan-only`
- **contrapositivo**: com WSL presente, os read-only continuam delegando — sem
  ele, a correção passaria mesmo se alguém parasse de falar com o lado Linux

Stub novo `AF_WSL_NOT_INSTALLED`, que replica o estado real medido: mensagem na
stderr e **código de saída 0**, por isso nem o exit code nem o redirect servem de
sinal.

## O que continua pendente

O bug do painel final (`wsl -e` sem `-u root`, item 3 do roadmap) **não se
manifestou**: a distro ficou sem conta inicializada e roda como root, então o log
mostra `/root/AtlasFile` e os comandos funcionam. Confirmá-lo exige completar o
assistente de conta do Ubuntu.

Também não foram exercitados: `-PurgeData`, `-RemoveDeps`, e o ciclo
`-KeepData` → reinstalar reusando o volume com a senha certa.
