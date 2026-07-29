# Teste do instalador num Windows 11 real — roteiro de comandos

Fecha o item **"`install.ps1` com stack real no ar"** do `ROADMAP.md`, que no Mac
está bloqueado por hardware (exige Hyper-V → virtualização aninhada em convidado
Windows, que Parallels e UTM não entregam em Apple Silicon).

Todos os comandos abaixo saíram do `install.ps1` desta branch — nenhum foi
inventado. Rode tudo em **PowerShell como Administrador**, salvo onde indicado.

---

## 0. Antes de começar

| | |
|---|---|
| Sessão | PowerShell **Administrador** (o `wsl --install` e o `dism` exigem) |
| Reinícios | Zerar o WSL pede **2 reinícios**. Reserve tempo |
| Rede | O primeiro install baixa ~500 MB de Ubuntu + Docker Desktop + as imagens |
| Idioma | O instalador é en-US de propósito, mesmo em Windows pt-BR |

> ⚠️ **`wsl --unregister` APAGA a distro inteira e tudo dentro dela, sem lixeira.**
> Se houver qualquer coisa sua dentro do WSL, tire antes. Num Windows de teste,
> sem problema.

---

## 1. Zerar o WSL (partir do absoluto zero)

### Jeito rápido: rode o script

`scripts/reset-wsl-windows.bat` faz tudo desta seção de uma vez. Baixe e rode
**como Administrador** (ele recusa rodar sem elevação):

```powershell
irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/scripts/reset-wsl-windows.bat -OutFile "$env:TEMP\reset-wsl-windows.bat"
Start-Process -Verb RunAs "$env:TEMP\reset-wsl-windows.bat"
```

Ele mostra o que existe na máquina, **exige que você digite `RESET`** para
seguir, e então: derruba o WSL, desregistra cada distro, desliga os dois
recursos do Windows, limpa o manifesto do instalador e — se você quiser —
desinstala o Docker Desktop pelo desinstalador próprio da Docker (o
`winget uninstall` não serve aqui: medido num Windows 11 real, ele abre janela e
fica esperando clique).

**Depois reinicie o Windows** e pule para a seção 2.

Se preferir fazer à mão, ou se algo falhar, os comandos avulsos estão abaixo.

### Jeito manual

**Ver o que existe hoje:**

```powershell
wsl --list --verbose
wsl --status
```

**Derrubar e remover cada distro** (repita o `--unregister` para cada nome que
apareceu na lista; `Ubuntu` é a que o AtlasFile instala):

```powershell
wsl --shutdown
wsl --unregister Ubuntu
```

**Remover o próprio WSL e os recursos do Windows:**

```powershell
wsl --uninstall
dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart
dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart
```

> `wsl --uninstall` só existe nas versões em que o WSL vem como app da Store
> (Windows 11 recente). Se ele responder que o parâmetro é inválido, **ignore** e
> siga com os dois `dism` — são eles que desligam os recursos de verdade, e são
> exatamente os que o `install.ps1` reabilita quando precisa
> (`Microsoft-Windows-Subsystem-Linux` e `VirtualMachinePlatform`).

**Reinicie o Windows.**

**Se o Docker Desktop também estiver instalado e você quiser o zero absoluto:**

```powershell
winget list -e --id Docker.DockerDesktop
winget uninstall -e --id Docker.DockerDesktop
```

**Apagar o manifesto do instalador** (é o que ele usa para saber o que criou —
sem apagar, um teste novo herda decisões do anterior):

```powershell
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\AtlasFile"
```

### Conferir que ficou zerado

```powershell
wsl --list --verbose      # deve dizer que não há distribuições instaladas
wsl --status              # deve falhar ou dizer que o WSL não está instalado
Test-Path "$env:LOCALAPPDATA\AtlasFile"   # deve ser False
```

---

## 2. Ver o que o instalador FARIA, sem fazer nada

Nenhum destes toca na máquina. Rode antes de instalar:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -DryRun
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -Doctor
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -Help
```

**O que observar:** sem WSL na máquina, o `-DryRun` tem de dizer que instalaria
WSL2 e Docker Desktop — e **nunca** terminar com stack trace do PowerShell.

---

## 3. Instalar do zero

O comando publicado (interativo — ele pergunta e mostra o plano):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -EnableAuth
```

Sem WSL na máquina, ele vai **oferecer** instalar. Para autorizar sem perguntas:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -EnableAuth -Yes -InstallDeps
```

> `-Yes` sozinho **não** instala dependência de sistema — falha com instrução.
> Quem autoriza o WSL2 e o Docker Desktop é o `-InstallDeps`.

**Vai pedir reinício** depois do `wsl --install`. Reinicie e rode o mesmo comando
de novo — ele retoma de onde parou.

**Com verbosidade** (mostra a saída de cada ferramenta em vez de esconder no log):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -EnableAuth -Yes -InstallDeps -Verbose
```

**Escolhendo onde as coisas ficam** (opcional):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) `
    -EnableAuth -Yes -InstallDeps `
    -Dir '~/AtlasFile' `
    -ProjectsRoot 'C:\Users\SEU_USUARIO\Documents\AtlasFileProjects'
```

Defaults: instalação em `~/AtlasFile` **dentro do WSL**; documentos na sua pasta
**Documentos do Windows**, para aparecerem no Explorer.

### Conferir que subiu de verdade

```powershell
wsl -l -v                                     # Ubuntu deve estar Running
wsl -u root -e bash -c 'docker ps'            # espera-se 5 containers
```

Abra no navegador:

- `http://localhost:5173` — a interface
- `http://localhost:8000/health` — deve responder `{"status":"ok"}`
- `http://localhost:5601` — o painel de observabilidade

> 🐞 **Bug conhecido a confirmar** (`ROADMAP.md`, painel final do `install.ps1`):
> a caixa final imprime `wsl -e bash -c '...'` **sem `-u root`**. Hoje funciona
> porque distro não inicializada usa root por padrão. **Se você completar o
> assistente de conta do Ubuntu** (criar usuário e senha), esses comandos passam
> a rodar como aquele usuário e **quebram**. Vale testar de propósito.

---

## 4. Reinstalar por cima (idempotência)

Rode **o mesmo comando da instalação** de novo, com tudo no ar:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -EnableAuth -Yes
```

**O que tem de acontecer:** não duplica nada, preserva o `.env` e a chave de API
já gerada, reaproveita o volume do índice, e a instalação segue funcionando.
Note que aqui **não** vai `-InstallDeps` — as dependências já estão lá.

---

## 5. Desinstalar

### Ver o plano sem tocar em nada

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -Uninstall -DryRun
```

Cobre **os dois lados** da máquina: o Windows e o Linux dentro do WSL.

### Os caminhos, do mais conservador ao mais completo

```powershell
# 1) Remove a stack, PRESERVA o índice de busca
& ([scriptblock]::Create((irm .../install.ps1))) -Uninstall -KeepData -Yes

# 2) Remove a stack e APAGA o índice
& ([scriptblock]::Create((irm .../install.ps1))) -Uninstall -PurgeData -Yes

# 3) Idem, e ainda remove o que o instalador instalou (Docker Desktop, WSL2)
& ([scriptblock]::Create((irm .../install.ps1))) -Uninstall -PurgeData -RemoveDeps -Yes

# 4) Se a pasta dentro do WSL tiver alterações locais e ele se recusar a apagar
& ([scriptblock]::Create((irm .../install.ps1))) -Uninstall -PurgeData -Force -Yes
```

> Substitua `.../install.ps1` pela URL completa do bloco acima.

**Regra sem default:** em modo não-interativo, `-Uninstall -Yes` **exige**
`-PurgeData` ou `-KeepData`. Sem um dos dois ele para e pede a decisão — o índice
nunca é apagado por omissão.

**O que ele nunca remove:** seus documentos, e qualquer Docker/WSL/git que já
existia antes (isso está no manifesto, gravado na instalação).

### Depois de desinstalar com `-KeepData`, reinstalar tem de reusar o volume

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -EnableAuth -Yes
```

Os documentos indexados antes têm de reaparecer, com a **mesma senha** do
OpenSearch (ela é gravada junto do volume preservado).

---

## 6. Testar uma branch em vez da `main`

```powershell
$env:ATLASFILE_SH_URL = "https://raw.githubusercontent.com/aleonnet/atlasfile/NOME-DA-BRANCH/install.sh"
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/NOME-DA-BRANCH/install.ps1))) -Branch NOME-DA-BRANCH -Yes -InstallDeps
```

---

## 7. O que trazer de volta

Se algo falhar, estes três artefatos são o que permite diagnosticar sem
adivinhação:

```powershell
# 1) o relatório da última execução
Get-Content "$env:LOCALAPPDATA\AtlasFile\last-run.log" -Tail 120

# 2) o manifesto (o que o instalador diz que criou nesta máquina)
Get-Content "$env:LOCALAPPDATA\AtlasFile\host-prereqs"

# 3) o retrato dos dois lados
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -Doctor
```

E, quando a stack estiver no ar, o log do lado Linux:

```powershell
wsl -u root -e bash -c 'cd ~/AtlasFile && docker compose logs --tail 100'
```

---

## 8. O que este teste prova (e que nenhum outro canal prova)

- Instalação **do zero absoluto**, sem WSL, com os dois reinícios reais
- Os **5 containers no ar** num Windows — hoje só os caminhos sem daemon são
  validados (VM Parallels e CI)
- Desinstalação com a stack **rodando**, nos dois escopos da máquina
- O ciclo `-KeepData` → reinstalar → **reusar volume com a senha certa**
- Se o bug do painel final (`wsl -e` sem `-u root`) aparece de verdade quando a
  conta do Ubuntu é criada
