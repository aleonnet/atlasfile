# Testes do install.ps1 — executa o INSTALADOR INTEIRO contra stubs de winget,
# wsl, docker e ollama, no PowerShell real. Espelha o que tests/installer/run.sh
# faz para o bash.
#
# Existe porque três bugs seguidos escaparam por eu validar a FUNÇÃO e não a
# FORMA REAL DE USO: argumento com traço virando parâmetro, barra de progresso
# quebrada por pipe, stderr virando erro terminante. Os stubs reproduzem
# exatamente essas formas.
#
#   powershell -File tests/installer/win/run.ps1   (5.1, o mesmo do CI e da VM)
$ErrorActionPreference = "Stop"
# O canal prlctl (VM Parallels) abre o console em codepage 437: o PowerShell
# 5.1 decodifica a saida CAPTURADA dos processos-filho com essa codepage, e
# cada glifo UTF-8 multibyte do trilho (U+2570, U+2502) vira tres bytes de
# lixo — eram exatamente as 6 assercoes do grupo "fechamento de trilho" que
# falhavam SO nesse canal (item 4 do ROADMAP; a hipotese anterior, queda de
# $AfTrueColor, estava ERRADA: a saida capturada mostra o desenho perfeito).
# UTF-8 explicito decodifica igual em qualquer canal; em host sem console o
# setter pode recusar, e ai nao ha o que corrigir.
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
} catch {
    Write-Verbose "sem console para configurar encoding: $($_.Exception.Message)"
}
$script:Pass = 0
$script:Fail = 0
# GetFullPath e nao Resolve-Path: em caminho UNC (\\servidor\share) o
# Resolve-Path devolve o prefixo do provider e mantem os "..", e o
# `powershell -File` recusa esse formato.
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))
$installer = Join-Path $repo "install.ps1"

function Ok($name) { $script:Pass++; Write-Host "  OK   $name" }
function No($name, $detail) {
    $script:Fail++
    Write-Host "  FALHA $name -- $detail" -ForegroundColor Red
    # A evidencia vai junto: diagnosticar falha de CI sem a saida capturada e
    # adivinhacao, e o arquivo cru fica na maquina efemera do runner.
    if ($script:CurrentOut) {
        Write-Host "      --- saida capturada (20 primeiras linhas) ---"
        ($script:CurrentOut -split "`r?`n" | Select-Object -First 20) |
            ForEach-Object { Write-Host "      | $_" }
        Write-Host "      --- resolucao das ferramentas nesta sessao ---"
        foreach ($tool in @("docker", "winget", "wsl", "ollama")) {
            $c = Get-Command $tool -ErrorAction SilentlyContinue
            Write-Host ("      | {0,-7} -> {1}" -f $tool, $(if ($c) { $c.Source } else { "(ausente)" }))
        }
        Write-Host "      | PATH: $env:Path"
        Write-Host "      --- chamadas registradas ---"
        (Calls) -split "`r?`n" | Where-Object { $_ } | ForEach-Object { Write-Host "      | $_" }
    }
}
function Assert-True($name, $cond, $detail = "") { if ($cond) { Ok $name } else { No $name $detail } }
function Assert-Match($name, $text, $pattern) {
    if ($text -match $pattern) { Ok $name } else { No $name "nao casou /$pattern/" }
}
function Assert-NoMatch($name, $text, $pattern) {
    if ($text -notmatch $pattern) { Ok $name } else { No $name "casou /$pattern/ e nao devia" }
}

# --- fabrica de stubs -------------------------------------------------------
# Cada stub registra a chamada em $env:AF_CALLS e obedece variaveis de ambiente
# para simular presenca, saida e codigo de retorno.
function New-Sandbox {
    $sb = Join-Path ([IO.Path]::GetTempPath()) ("afwin_" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Path (Join-Path $sb "bin") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $sb "home") -Force | Out-Null
    # Zera TODO o estado entre cenarios: variavel vazada de um cenario para o
    # seguinte fazia a bancada reprovar um caminho que funciona (comprovado
    # rodando o mesmo cenario isolado, onde todas as chamadas acontecem).
    Get-ChildItem env: | Where-Object { $_.Name -like 'AF_*' -or $_.Name -like 'ATLASFILE_*' } |
        ForEach-Object { Remove-Item "env:$($_.Name)" -ErrorAction SilentlyContinue }
    $env:AF_CALLS = Join-Path $sb "calls.log"
    "" | Set-Content $env:AF_CALLS
    $env:LOCALAPPDATA = Join-Path $sb "home"

    # winget: desenha progresso com retorno de carro e escreve aviso no stderr,
    # que foi exatamente o que quebrou na maquina real.
    @'
@echo off
>>"%AF_CALLS%" echo winget %*
if "%AF_WINGET_PRESENT%"=="0" exit /b 9009
echo %*|findstr /c:"list" >nul
if not errorlevel 1 exit /b %AF_WINGET_LIST_RC%
if defined AF_WINGET_STDERR echo Failed when searching source: msstore 1>&2
<nul set /p "=Downloading  10%%"
<nul set /p "=Downloading  55%%"
echo Successfully installed
exit /b %AF_WINGET_RC%
'@ | Set-Content (Join-Path $sb "bin\winget.cmd") -Encoding ASCII

    @'
@echo off
>>"%AF_CALLS%" echo wsl %*
if not "%AF_WSL_NO_DOCKER%"=="1" goto dispatch
echo %*|findstr /c:"docker info" >nul
if errorlevel 1 goto dispatch
exit /b 1
:dispatch
if "%AF_WSL_INSTALLED%"=="0" goto notinstalled
if "%1"=="--install" goto install
if "%1"=="--update" goto update
if "%1"=="--status" goto status
if "%1"=="-l" goto list
if "%1"=="-u" goto asroot
if "%1"=="-e" goto exec
exit /b 0
:notinstalled
echo The Windows Subsystem for Linux is not installed. 1>&2
exit /b 0
:install
echo Instalando o componente opcional do Windows: VirtualMachinePlatform
exit /b %AF_WSL_INSTALL_RC%
:update
echo A versao mais recente do WSL ja esta instalada.
exit /b 0
:status
if not "%AF_WSL_NOT_INSTALLED%"=="1" goto status_ok
REM Windows 11 zerado: wsl.exe EXISTE (vem com o sistema), escreve isto na
REM STDERR e ainda assim sai 0 - por isso nem o codigo de saida nem o redirect
REM servem de sinal, so o texto. Medido num build limpo.
echo The Windows Subsystem for Linux is not installed. 1>&2
exit /b 0
:status_ok
echo WSL version: 2.0.0
exit /b 0
:list
if "%AF_WSL_NO_DISTRO%"=="1" exit /b 0
echo Ubuntu
exit /b 0
:asroot
if not "%AF_WSL_INSTALL_FIXES%"=="1" goto asroot_normal
findstr /c:"--install" "%AF_CALLS%" >nul
if errorlevel 1 goto asroot_normal
echo atlasfile_wsl_ok
exit /b 0
:asroot_normal
if "%AF_WSL_DEAD_DISTRO%"=="1" exit /b 1
if "%AF_WSL_NO_DISTRO%"=="1" exit /b 1
echo atlasfile_wsl_ok
exit /b 0
:exec
if "%AF_WSL_HANG%"=="1" ping -n 30 127.0.0.1 >nul
if "%AF_WSL_NO_DISTRO%"=="1" exit /b 1
if "%AF_WSL_DEAD_DISTRO%"=="1" exit /b 1
if "%AF_WSL_UNINIT%"=="1" exit /b 1
if "%2"=="wslpath" goto wslpath
REM Leitura do .env pelo orquestrador (porta instalada): o grep real sai 1
REM sem match, e so responde a linha quando a bancada define a porta.
echo %*|findstr /c:"ATLASFILE_PORT" >nul
if not errorlevel 1 goto envport
if "%2"=="echo" echo atlasfile_wsl_ok
echo %*|findstr /c:"--plan-only" >nul
if not errorlevel 1 goto planonly
echo %*|findstr /c:"--uninstall" >nul
if not errorlevel 1 goto unexec
exit /b 0
:wslpath
echo /mnt/c/Users/tester/Documents/AtlasFileProjects
exit /b 0
:envport
if "%AF_WSL_ENV_PORT%"=="" exit /b 1
echo ATLASFILE_PORT=%AF_WSL_ENV_PORT%
exit /b 0
:planonly
echo.
echo   Removal plan - /root/AtlasFile
echo.
echo   WILL BE REMOVED
echo   * stack 'atlasfile': containers, network and the images built here
echo.
echo   WILL BE PRESERVED
echo   * %AF_SH_PLAN_KEEP%
echo.
echo ATLASFILE_FACT: volume=%AF_SH_VOLUME%
echo ATLASFILE_FACT: actions=%AF_SH_ACTIONS%
echo ATLASFILE_UNINSTALL: plan-only
exit /b 0
:unexec
echo   removing the stack (containers, network, local images)
echo ATLASFILE_UNINSTALL: %AF_SH_SENTINEL%
exit /b %AF_SH_RC%
'@ | Set-Content (Join-Path $sb "bin\wsl.cmd") -Encoding ASCII

    @'
@echo off
>>"%AF_CALLS%" echo dism %*
echo A operacao foi concluida com exito.
exit /b 0
'@ | Set-Content (Join-Path $sb "bin\dism.cmd") -Encoding ASCII

    @'
@echo off
>>"%AF_CALLS%" echo docker %*
if "%AF_DOCKER_PRESENT%"=="0" exit /b 9009
if "%AF_DOCKER_INFO_RC%"=="1" exit /b 1
exit /b 0
'@ | Set-Content (Join-Path $sb "bin\docker.cmd") -Encoding ASCII

    @'
@echo off
>>"%AF_CALLS%" echo ollama %*
if "%AF_OLLAMA_PRESENT%"=="0" exit /b 9009
if "%AF_OLLAMA_DOWN%"=="1" exit /b 1
if not "%1"=="list" goto fim
echo NAME ID SIZE
:fim
exit /b 0
'@ | Set-Content (Join-Path $sb "bin\ollama.cmd") -Encoding ASCII

    # PATH minimo: stubs primeiro, e o System32 para cmd/powershell
    $env:Path = (Join-Path $sb "bin") + ";" + "$env:SystemRoot\System32;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    # defaults
    $env:AF_WINGET_PRESENT = "1"; $env:AF_WINGET_RC = "0"; $env:AF_WINGET_STDERR = "1"
    # `winget list` responde 0 por padrao: o pacote ESTA registrado. O caminho
    # em que ele nao esta e o do Ollama que falhou na maquina real.
    $env:AF_WINGET_LIST_RC = "0"
    # O lado de dentro do WSL, simulado: plano, fatos e a linha-sentinela que o
    # orquestrador exige antes de encostar em qualquer pacote do Windows.
    $env:AF_SH_VOLUME = "atlasfile_opensearch_data"
    $env:AF_SH_ACTIONS = "1"
    $env:AF_SH_SENTINEL = "confirmed"
    $env:AF_SH_RC = "0"
    $env:AF_SH_PLAN_KEEP = "your documents in /root/Documents/AtlasFileProjects - never touched"
    $env:AF_WSL_INSTALLED = "1"; $env:AF_WSL_RC = "0"; $env:AF_WSL_INSTALL_RC = "0"; $env:AF_WSL_INSTALL_FIXES = "0"; $env:AF_WSL_NO_DOCKER = "0"
    $env:AF_WSL_NO_DISTRO = "0"; $env:AF_WSL_DEAD_DISTRO = "0"; $env:AF_WSL_UNINIT = "0"; $env:AF_WSL_HANG = "0"
    # Teto GENEROSO por padrao. Ele era 2000 para todos os cenarios, e isso
    # tornava FLAKY todo caminho que espera o WSL funcionar: o stub responde na
    # hora, mas num runner do CI carregado o proprio Start-Process + WaitForExit
    # passa de 2s. Aconteceu — o job Windows reprovou com "the distro is
    # installed but did not answer in time" contra um stub que so faz `echo`, e
    # a falha apareceu vinte cenarios adiante, no teste do arquivo de
    # preferencias do Docker, porque a fase 2 nunca chegou a rodar.
    #
    # Quem precisa de teto curto e SO o cenario que testa o estouro, e ele o
    # define por conta propria.
    $env:ATLASFILE_WSL_PROBE_MS = "20000"
    $env:AF_DOCKER_PRESENT = "1"; $env:AF_DOCKER_INFO_RC = "0"
    $env:AF_OLLAMA_PRESENT = "1"; $env:AF_OLLAMA_DOWN = "0"
    $env:ATLASFILE_DOCKER_WAIT = "3"   # sem isso o cenario D esperaria 5 minutos reais
    $script:Sandbox = $sb
    $env:ATLASFILE_FAKE_MISSING = ""
    $env:ATLASFILE_LOG = Join-Path $sb "install.log"
    return $sb
}

function Calls { Get-Content $env:AF_CALLS -Raw -ErrorAction SilentlyContinue }

# Ausencia se simula REMOVENDO o stub. Fazer o stub sair 9009 nao adianta:
# Get-Command checa EXISTENCIA, nao codigo de saida — foi o que mascarou os
# cenarios B e C na primeira rodada desta bancada.
function Remove-Stub([string]$Name) {
    Remove-Item (Join-Path $script:Sandbox "bin\$Name.cmd") -Force -ErrorAction SilentlyContinue
    # PATH nao basta: o runner do CI traz docker.exe em System32, que precisa
    # estar no PATH. O override de teste do instalador garante a ausencia.
    $atual = @($env:ATLASFILE_FAKE_MISSING -split ',' | Where-Object { $_ })
    $env:ATLASFILE_FAKE_MISSING = (($atual + $Name) | Select-Object -Unique) -join ','
}

# Roda o instalador em processo FILHO (ele termina com `exit`) e devolve a saida.
function Run-Installer([string[]]$InstallerArgs) {
    $psi = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $installer) + $InstallerArgs
    # Continue e nao Stop: o proprio harness caiu no bug que testa — o stderr do
    # processo filho virava NativeCommandError terminante e matava a bancada.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $out = & powershell @psi 2>&1 | Out-String } catch { $out = $_ | Out-String }
    $ErrorActionPreference = $prev
    # a saida crua fica em disco: diagnosticar falha sem ela e adivinhacao
    $script:LastRaw = Join-Path ([IO.Path]::GetTempPath()) ("afwin_last_" + [Guid]::NewGuid().ToString("N").Substring(0,6) + ".txt")
    $out | Set-Content $script:LastRaw -Encoding UTF8
    $script:CurrentOut = $out
    return $out
}

Write-Host "== A. sem WSL: degrada com mensagem, nunca com excecao =="
$sb = New-Sandbox
$env:AF_WSL_INSTALLED = "0"
$out = Run-Installer @("-Yes")
Assert-Match "diz que o WSL2 nao e utilizavel" $out "WSL2 is not usable"
Assert-NoMatch "sem NativeCommandError" $out "NativeCommandError"
Assert-NoMatch "sem excecao nao tratada" $out "Unhandled|ParameterBindingException|AmbiguousParameter"

Write-Host "== A2. --status responde mas NAO HA DISTRO: nao pode dizer que esta pronto =="
# Caso real relatado num Windows 11: o instalador disse "WSL2 available", pulou a
# instalacao do WSL, e o Docker Desktop acusou "WSL not installed" logo depois.
$sb = New-Sandbox
$env:AF_WSL_NO_DISTRO = "1"
$out = Run-Installer @("-Yes")
Assert-NoMatch "NAO declara WSL2 pronto sem distro" $out "WSL2 available"
Assert-Match "diz que o WSL2 nao e utilizavel" $out "WSL2 is not usable"
Assert-Match "explica que falta a distro" $out "NO DISTRO is installed"

Write-Host "== A3. distro existe mas nao executa =="
$sb = New-Sandbox
$env:AF_WSL_DEAD_DISTRO = "1"
$out = Run-Installer @("-Yes")
Assert-NoMatch "NAO declara pronto com distro que nao roda" $out "WSL2 available"
Assert-Match "explica que a distro nao executa" $out "does not run"

Write-Host "== A4. distro instalada mas NAO inicializada: segue como root, sem assistente =="
# `wsl --install --no-launch` deixa a distro registrada e sem usuario. Sem este
# caminho a instalacao desatendida travaria no assistente de criacao de conta.
$sb = New-Sandbox
$env:AF_WSL_UNINIT = "1"
$out = Run-Installer @("-Yes", "-NoOpen")
Assert-Match "reconhece o WSL como utilizavel" $out "WSL2 available"
Assert-Match "rodou wsl --update antes da verificacao" (Calls) "wsl --update"
Assert-Match "avisa que vai usar root" $out "using root for this install"
Assert-Match "delegou ao WSL com -u root" (Calls) "wsl -u root -e bash"
# Item 3 do ROADMAP: o comando ENSINADO pelo painel tem de ser o que funciona
# nesta instalacao - feita como root, um `wsl -e` sem usuario cai no usuario
# padrao da distro e o comando colado falharia.
Assert-Match "o painel ensina o comando com -u root" $out "wsl -u root -e"

Write-Host "== A5. distro listada que NAO responde: nao trava e aponta virtualizacao =="
# Relato real: o usuario teve que dar Ctrl+C porque `wsl -e` ficou pendurado, na
# mesma maquina em que o Docker acusava "Virtualization support not detected".
$sb = New-Sandbox
$env:AF_WSL_HANG = "1"
# ESTE cenario e o dono do teto curto: e ele que prova que a sonda desiste em
# vez de pendurar. Nos demais o teto e generoso, senao um runner lento reprova
# caminhos que nao tem nada de errado.
$env:ATLASFILE_WSL_PROBE_MS = "2000"
$inicio = Get-Date
$out = Run-Installer @("-Yes")
$decorrido = ((Get-Date) - $inicio).TotalSeconds
Assert-True "nao trava (respeitou o teto de tempo)" ($decorrido -lt 25) "levou $([int]$decorrido)s"
Assert-NoMatch "NAO declara WSL2 pronto" $out "WSL2 available"
Assert-Match "tentou wsl --update ANTES de diagnosticar" (Calls) "wsl --update"
Assert-Match "nao crava causa, lista o que verificar" $out "Check, in this order"
Assert-Match "sugere wsl --shutdown" $out "wsl --shutdown"

Write-Host "== A6. instalou o WSL: caminho de SUCESSO nao pode virar erro vermelho =="
# Relatado numa maquina real: depois de instalar o WSL com exito o instalador
# imprimia "AtlasFile installer stopped with exit code 0." como excecao.
$sb = New-Sandbox
$env:AF_WSL_NO_DISTRO = "1"
$out = Run-Installer @("-InstallDeps")
Assert-Match "instalou o WSL" (Calls) "wsl --install"
Assert-Match "pede o reinicio" $out "restart Windows"
Assert-NoMatch "sem excecao no caminho de sucesso" $out "installer stopped with exit code|OperationStopped|RuntimeException"

Write-Host "== A7. wsl --install FALHA: nao pode mandar reiniciar =="
# Relatado num Windows 11 real: o instalador imprimia "restart Windows and run
# this installer again" sem olhar o codigo de saida, entao o usuario reiniciava
# so para reencontrar exatamente a mesma tela. Loop.
$sb = New-Sandbox
$env:AF_WSL_NO_DISTRO = "1"
$env:AF_WSL_INSTALL_RC = "1"
$out = Run-Installer @("-InstallDeps")
Assert-Match "declara a falha com o codigo" $out "wsl --install failed \(exit code"
Assert-NoMatch "NAO manda reiniciar depois de falhar" $out "restart Windows and run this installer again"
Assert-Match "aponta o log de servicing" $out "dism.log"

Write-Host "== A8. segunda tentativa: acao DIFERENTE, nao o mesmo comando =="
# O manifesto ja registra que este instalador rodou wsl --install aqui. Repetir
# o mesmo passo era o que fechava o loop na maquina do usuario.
$sb = New-Sandbox
$env:AF_WSL_NO_DISTRO = "1"
$manifesto = Join-Path $env:LOCALAPPDATA "AtlasFile\host-prereqs"
New-Item -ItemType Directory -Path (Split-Path $manifesto) -Force | Out-Null
@("schema`t1", "wsl`tcreated") | Set-Content $manifesto -Encoding UTF8
$out = Run-Installer @("-InstallDeps")
$calls = Calls
Assert-Match "diz que ja tentou antes" $out "already ran here"
Assert-Match "liga o VirtualMachinePlatform explicitamente" $calls "featurename:VirtualMachinePlatform"
Assert-Match "liga a feature do WSL explicitamente" $calls "featurename:Microsoft-Windows-Subsystem-Linux"
Assert-Match "avisa o que fazer se a tela voltar" $out "not sticking"

Write-Host "== A9. instalacao ja deixa o WSL utilizavel: SEGUE, nao manda reiniciar =="
# Quando as features ja estavam ligadas e faltava so a distro, o wsl --install
# resolve na hora. Mandar reiniciar ai custa mais uma volta identica a anterior
# — indistinguivel do loop, do ponto de vista de quem esta na frente da tela.
$sb = New-Sandbox
$env:AF_WSL_NO_DISTRO = "1"
$env:AF_WSL_INSTALL_FIXES = "1"
$out = Run-Installer @("-InstallDeps")
Assert-Match "instalou o WSL" (Calls) "wsl --install"
Assert-Match "constatou que ja funciona" $out "no restart needed"
Assert-NoMatch "NAO manda reiniciar quando ja funciona" $out "restart Windows and run this installer again"
Assert-Match "seguiu para a fase seguinte" $out "Docker Desktop"

Write-Host "== G. Docker fora do alcance dentro do WSL: espera antes de reprovar =="
# Medido num Windows 11 real: o daemon do lado Windows respondeu em 52s e esta
# verificacao, feita no instante seguinte, reprovou — o Docker Desktop ainda nao
# tinha injetado o CLI dentro da distro. O lado Windows tinha 300s de paciencia,
# este tinha ZERO.
$sb = New-Sandbox
$env:AF_WSL_NO_DOCKER = "1"
$env:ATLASFILE_DOCKER_WAIT = "6"
$out = Run-Installer @("-Yes")
$tentativas = ([regex]::Matches((Calls), "docker info")).Count
Assert-Match "anuncia que esta esperando a integracao" $out "waiting for Docker.s WSL integration"
Assert-True "tentou mais de uma vez antes de desistir (tentativas=$tentativas)" ($tentativas -ge 2)
Assert-Match "so entao aponta a integracao do WSL" $out "not reachable inside WSL"

Write-Host "== B. WSL ok, Docker ausente, sem autorizacao: recusa com instrucao =="
$sb = New-Sandbox
Remove-Stub docker
$out = Run-Installer @("-Yes")
Assert-Match "aponta o Docker Desktop ausente" $out "Docker Desktop not found"
Assert-NoMatch "nao chamou o winget sem autorizacao" (Calls) "winget install"

Write-Host "== C. -InstallDeps instala pelo winget com os argumentos certos =="
$sb = New-Sandbox
Remove-Stub docker
$out = Run-Installer @("-Yes", "-InstallDeps")
$calls = Calls
Assert-Match "chamou winget install" $calls "winget install"
Assert-Match "passou -e (o argumento que quebrava o binding)" $calls "\-e "
Assert-Match "passou --id Docker.DockerDesktop" $calls "--id Docker.DockerDesktop"
Assert-Match "passou --source winget (evita a msstore)" $calls "--source winget"
Assert-Match "passou --disable-interactivity" $calls "--disable-interactivity"
Assert-NoMatch "nenhum erro de binding de parametro" $out "AmbiguousParameter|ParameterBindingException"
# O stub sai 0: o instalador NAO pode declarar falha. Este caso pegou um bug real
# — sem pipe, o stdout do winget entrava na saida da funcao e `$rc` virava array.
Assert-NoMatch "nao declara falha quando o winget sai 0" $out "could not install Docker Desktop"
Assert-Match "seguiu ADIANTE apos o winget" $out "docker CLI is not on PATH yet|starting Docker Desktop|daemon did not come up"
# progresso do winget nao pode aparecer picotado, uma linha por atualizacao
$linhasProgresso = ([regex]::Matches($out, "Downloading")).Count
Assert-True "progresso do winget nao vira uma linha por atualizacao" ($linhasProgresso -le 2) "apareceu $linhasProgresso vezes"

Write-Host "== D. daemon nao sobe: mensagem nomeia as duas causas =="
$sb = New-Sandbox
$env:AF_DOCKER_INFO_RC = "1"
$out = Run-Installer @("-Yes")
Assert-Match "cita o dialogo do primeiro launch" $out "first-launch"
Assert-Match "cita virtualizacao indisponivel" $out "[Vv]irtualization is not available"
Assert-NoMatch "sem excecao" $out "Unhandled|ParameterBindingException"

Write-Host "== E. o Ollama saiu do instalador: nada de pull, nada de flag =="
# Puxar um modelo eram varios GB dentro de uma instalacao que precisa ter duracao
# previsivel. E a flag --no-ollama, que existia so para conter o efeito colateral
# desse recurso nos DOIS sistemas operacionais, tambem deixou de existir - passa-la
# agora faria o install.sh sair com "Unknown flag".
$sb = New-Sandbox
$env:AF_OLLAMA_PRESENT = "1"
$out = Run-Installer @("-Yes", "-InstallDeps")
$calls = Calls
Assert-NoMatch "nao puxa modelo nenhum" $calls "ollama pull"
Assert-NoMatch "nem pergunta sobre Ollama" $out "Also install Ollama"
Assert-NoMatch "e nao passa a flag que nao existe mais" $calls "--no-ollama"

# O site publica -WithOllama ha meses. PowerShell recusa parametro desconhecido
# com erro TERMINANTE: quem colasse o comando do site nao veria nem o banner.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-InstallDeps", "-WithOllama", "-OllamaModel", "gemma3:1b")
Assert-Match "a flag antiga do site nao quebra a instalacao" $out "no longer used"
Assert-NoMatch "e nao faz nada de Ollama acontecer" (Calls) "ollama pull"
Assert-NoMatch "sem erro de parametro desconhecido" $out "ParameterBindingException|A parameter cannot be found"

Write-Host "== H. o script entregue ao WSL chega INTEIRO, nao partido em palavras =="
# Medido na maquina do usuario: o -ArgumentList do Start-Process junta o array
# com espacos e NAO cita nada, entao o `bash -c "curl -fsSL <url> | bash -s --
# --no-open"` chegou como `bash -c curl` com o resto solto. O curl rodou sem
# argumento algum e a instalacao morreu em "curl: try 'curl --help'". A bancada
# nao pegava porque o stub registrava a chamada e devolvia 0 sem NUNCA conferir
# se o argumento tinha chegado inteiro.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-EnableAuth", "-Dir", "/root/Outro", "-NoOpen")
$calls = Calls
# Ancorada na PROPRIEDADE (a aspa que abre logo depois do -c), e nao no que vem
# dentro: a largura do trilho passou a viajar antes do curl e a versao anterior,
# presa a "-c \"curl -fsSL", reprovou codigo correto.
Assert-Match "o -c chega como UM argumento citado" $calls '-c "[^"]*curl -fsSL'
Assert-Match "as flags do install.sh viajam no mesmo argumento" $calls 'bash -s -- --no-open --delegated --yes --enable-auth'
Assert-NoMatch "o curl nao roda pelado" $out "curl: try"
# Um banner por execucao: o do install.sh nao pode ser desenhado logo depois do
# nosso - eram dois desenhos diferentes na mesma tela.
Assert-Match "a delegacao silencia o banner do outro lado" $calls "--delegated"
# --no-ollama nao pode mais ser passada: a flag saiu junto com o recurso, e uma
# flag desconhecida faz o install.sh sair com "Unknown flag".
Assert-NoMatch "nao passa flag que o outro lado nao conhece mais" $calls "--no-ollama"
Assert-Match "-Dir viaja para o outro lado" $calls '--dir /root/Outro'
# Sem a URL sobrescrivivel e o -Branch, uma branch NAO pode ser testada de ponta
# a ponta no Windows: o .ps1 da branch buscaria o .sh do main.
$sb = New-Sandbox
$env:ATLASFILE_SH_URL = "https://exemplo.invalido/branch/install.sh"
$out = Run-Installer @("-Yes", "-Branch", "minha-branch", "-NoOpen")
$calls = Calls
Assert-Match "a URL do install.sh vem do ambiente" $calls "exemplo.invalido/branch/install.sh"
Assert-Match "e o -Branch viaja junto" $calls "--branch minha-branch"
# O curl endurecido (mesma dureza do mac-env-setup): um solucao de rede nao pode
# virar instalacao pela metade.
Assert-Match "download com retry e protocolo pinado" $calls "--proto '=https' --tlsv1.2 --retry 3"

Write-Host "== H2. -Version viaja como --version; sem a flag, nada viaja =="
# Fase 4b: o caminho padrao instala a RELEASE. Os contrapositivos existem
# porque um encaminhamento incondicional (o mutante obvio) passaria em
# qualquer assercao so de presenca.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-Version", "1.2.3", "-NoOpen")
$calls = Calls
Assert-Match "-Version viaja como --version" $calls "--version 1.2.3"
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-NoOpen")
$calls = Calls
Assert-NoMatch "sem -Version nao ha --version" $calls "--version"
Assert-NoMatch "sem -FromSource nao ha --from-source" $calls "--from-source"
Assert-NoMatch "sem -RepoUrl nao ha --repo-url" $calls "--repo-url"

Write-Host "== H3. -FromSource mantem o caminho de contribuidor vivo no Windows =="
# Regressao da 4a: o install.sh passou a instalar a release por padrao e o ps1
# ficou sem como pedir o caminho fonte - um -Branch de fork virou warn+ignore
# do outro lado. As tres flags viajam juntas.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-FromSource", "-RepoUrl", "https://github.com/fulano/atlasfile", "-Branch", "minha-branch", "-NoOpen")
$calls = Calls
Assert-Match "-FromSource viaja como --from-source" $calls "--from-source"
Assert-Match "-RepoUrl viaja como --repo-url" $calls "--repo-url https://github.com/fulano/atlasfile"
Assert-Match "-Branch viaja no caminho fonte" $calls "--branch minha-branch"
Assert-Match "a fase 3 anuncia build local no caminho fonte" $out "clones and builds locally"

Write-Host "== H4. o que mentiria falha CEDO, antes de tocar a maquina =="
# Um typo em -Version so explodiria DENTRO do WSL, depois das fases 1 e 2
# (minutos, gigabytes). E o install.sh IGNORA --version no caminho fonte -
# ignorar em silencio o que o usuario digitou e mentira.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-Version", "banana")
Assert-Match "versao fora do shape e recusada" $out "is not a release number"
Assert-True "e nenhuma ferramenta chegou a ser chamada" (-not ((Calls) -match '\S')) "houve chamada de ferramenta apos -Version invalida"
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-Version", "1.2.3", "-FromSource")
Assert-Match "-Version com -FromSource e recusado" $out "cannot be combined"
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-RepoUrl", "https://exemplo.invalido/x")
Assert-Match "-RepoUrl sem -FromSource e recusado" $out "only makes sense with -FromSource"

Write-Host "== H5. o browser tem anuncio observavel e -NoOpen o desliga =="
# O Start-Process nao passa por stub e a mensagem do catch so aparece quando
# ele FALHA - um sinal que so existe na falha nao prova nada. O anuncio sai
# ANTES da tentativa e independe do canal.
$sb = New-Sandbox
$out = Run-Installer @("-Yes")
Assert-Match "sem -NoOpen o instalador anuncia a abertura" $out "opening http://localhost:"
Assert-True "e sem porta custom o anuncio e da 8000" ($out -match "opening http://localhost:8000 ") "anunciou outra porta sem ninguem pedir"
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-NoOpen")
Assert-NoMatch "com -NoOpen nao ha anuncio nem abertura" $out "opening http://localhost:"

Write-Host "== H8. -Port viaja, valida cedo, e o browser abre a porta REAL =="
# A porta e a do usuario: -Port quando dado; senao a que o .env da instalacao
# anterior carrega (lida via wsl grep); senao 8000.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-Port", "8090", "-NoOpen")
$calls = Calls
Assert-Match "-Port viaja como --port" $calls "--port 8090"
$sb = New-Sandbox
$out = Run-Installer @("-Yes")
$calls = Calls
Assert-NoMatch "sem -Port nao ha --port" $calls "--port"
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-Port", "abc")
Assert-Match "porta fora do shape e recusada" $out "is not a valid TCP port"
Assert-True "e nenhuma ferramenta chegou a ser chamada" (-not ((Calls) -match '\S')) "houve chamada de ferramenta apos -Port invalido"
$sb = New-Sandbox
$env:AF_WSL_ENV_PORT = "8123"
$out = Run-Installer @("-Yes")
$calls = Calls
Assert-Match "sem -Port o instalador consulta o .env do outro lado" $calls "ATLASFILE_PORT"
Assert-True "e o anuncio abre a porta da instalacao, nao a default" ($out -match "opening http://localhost:8123 ") "anuncio nao acompanhou a porta do .env"

Write-Host "== H6. a ajuda conta a historia da release, nao a do clone =="
# O gap declarado da 4a: o help prometia clone que o outro lado ja nao faz por
# padrao. -Force segue falando de clone (uninstall de instalacao fonte/legada,
# que E um clone) - por isso a assercao ancora na linha do -Branch.
$sb = New-Sandbox
$out = Run-Installer @("-Help")
Assert-Match "a ajuda documenta -Version" $out "-Version X.Y.Z"
Assert-Match "a ajuda documenta -FromSource" $out "-FromSource"
Assert-Match "a ajuda documenta -NoOpen" $out "-NoOpen"
Assert-Match "-Branch virou caminho de contribuidor" $out "only with -FromSource"
# A forma INCONDICIONAL antiga ("Branch to clone (default: main)") e o que nao
# pode voltar; "Branch to clone (only with -FromSource...)" e honesto - no
# caminho fonte e um clone mesmo, e o positivo acima cobra o qualificador.
Assert-True "-Branch nao promete mais clone por padrao" ($out -notmatch "Branch to clone \(default") "a linha do -Branch ainda promete clone incondicional"

Write-Host "== K. o caminho ANIMADO executa e termina no quadro final =="
# Sem o ATLASFILE_FORCE_ANIM este caminho seria intestavel: redirecionado, o
# instalador escolhe o banner estatico, e um erro de indice na tabela da orbita
# ou um escape errado so apareceria na tela do usuario.
$sb = New-Sandbox
$env:ATLASFILE_FORCE_ANIM = "1"
$env:WT_SESSION = "harness"    # o truecolor e a outra metade da guarda de animacao
Remove-Item env:COLORTERM -ErrorAction SilentlyContinue
$out = Run-Installer @("-Yes", "-NoOpen")
Remove-Item env:WT_SESSION -ErrorAction SilentlyContinue
Assert-Match "o wordmark chega ao quadro final" $out "AtlasFile"
Assert-Match "a frase de chamada chega inteira" $out "Your documents have gravity"
Assert-Match "a linha da plataforma chega inteira" $out "Windows / WSL2"
Assert-NoMatch "sem excecao no caminho animado" $out "Unhandled|IndexOutOfRange|MethodInvocation|OutOfBounds|cannot be converted|nao pode ser convertido"

Write-Host "== L. sem Windows Terminal: habilitar VT nao pode quebrar nada =="
# O usuario roda na janela CLASSICA do PowerShell (prompt em C:\WINDOWS\system32),
# onde WT_SESSION nao existe. Ali o instalador tenta LIGAR o VT via kernel32, e
# isso compila C# em tempo de execucao: politica de execucao, .NET podado ou
# console sem handle tem que degradar para o banner estatico, nunca derrubar.
$sb = New-Sandbox
$env:ATLASFILE_FORCE_ANIM = "1"
Remove-Item env:WT_SESSION, env:COLORTERM -ErrorAction SilentlyContinue
$out = Run-Installer @("-Yes", "-NoOpen")
Assert-Match "o banner sai de qualquer jeito" $out "AtlasFile"
Assert-Match "a frase de chamada sai de qualquer jeito" $out "Your documents have gravity"
Assert-NoMatch "sem erro de Add-Type nem de tipo ausente" $out "Add-Type|Unable to find type|Nao foi possivel encontrar o tipo|CompilationErrors"

Write-Host "== J. saida de terceiro vai para o LOG, nunca para a tela =="
# A regra do benchmark (mac_env_install.sh:656 e run_step do install.sh): o
# comando roda com a saida redirecionada e a tela mostra so o nosso vocabulario.
# Sem esta checagem, "padronizamos a UI" seria afirmacao, nao propriedade.
$sb = New-Sandbox
Remove-Stub docker
$out = Run-Installer @("-Yes", "-InstallDeps", "-NoOpen")
$log = (Get-Content $env:ATLASFILE_LOG -Raw -ErrorAction SilentlyContinue)
Assert-NoMatch "o texto do winget NAO chega na tela" $out "Successfully installed"
Assert-Match "no lugar dele, o nosso rotulo" $out "downloading and installing Docker Desktop"
Assert-Match "e o texto do winget esta no log" $log "Successfully installed"

function New-UninstallSandbox([string[]]$Manifesto) {
    $sb = New-Sandbox
    $mf = Join-Path $env:LOCALAPPDATA "AtlasFile\host-prereqs"
    New-Item -ItemType Directory -Path (Split-Path $mf) -Force | Out-Null
    (@("schema`t1") + $Manifesto) | Set-Content $mf
    return $sb
}

Write-Host "== F. -Uninstall -RemoveDeps: UM plano cobrindo os dois lados =="
# O defeito de origem: o plano descrevia so a distro, e o lado Windows agia
# depois sem plano e sem confirmacao. Aqui o stub do wsl DEVOLVE um plano, e a
# bancada cobra que ele chegue a tela ANTES de qualquer remocao.
$sb = New-UninstallSandbox @("docker`tcreated", "ollama`tpreexisting", "wsl`tcreated")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
$calls = Calls
Assert-Match "pediu os FATOS antes de agir" $calls "--plan-only"
Assert-Match "os fatos do Windows viajam para o plano" $calls "--host-extra docker=created,ollama=preexisting,wsl=created"
Assert-Match "a delegacao silencia o banner do outro lado" $calls "--delegated"
Assert-Match "o plano do outro lado chega a tela" $out "Removal plan"
Assert-Match "com as duas secoes" $out "WILL BE PRESERVED"
Assert-NoMatch "as linhas de maquina nao vazam para o usuario" $out "ATLASFILE_FACT"
Assert-Match "removeu o Docker, que o manifesto marca created" $calls "winget uninstall.*Docker.DockerDesktop"
Assert-Match "remocao tambem evita a msstore" $calls "winget uninstall.*--source winget"
Assert-Match "conferiu no winget ANTES de remover" $calls "winget list.*Docker.DockerDesktop"
Assert-NoMatch "NAO removeu o Ollama, que era preexisting" $calls "winget uninstall.*Ollama"
Assert-Match "e disse por que o preservou" $out "was already on this machine before AtlasFile - preserved"
Assert-NoMatch "sem erro de binding na desinstalacao" $out "AmbiguousParameter|ParameterBindingException"
Assert-Match "um unico veredito, no fim" $out "AtlasFile removed. What already existed on this machine was preserved"

Write-Host "== F2. a identidade da instalacao e RECUPERADA do manifesto =="
# $script:WslUser so era decidido na fase 1, que roda DEPOIS deste bloco: nos
# caminhos de uninstall/doctor/dry-run ele estava sempre vazio, e o `wsl -e`
# rodava como usuario PADRAO. Instalacao feita como root (o caso de quem deixou
# o AtlasFile instalar o WSL) morava em /root e simplesmente nao era encontrada.
$sb = New-UninstallSandbox @("docker`tcreated", "wsl_user`troot", "install_dir`t/root/Outro", "wsl_distro`tUbuntu")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
$calls = Calls
Assert-Match "fala com o WSL como o dono da instalacao" $calls "wsl -u root -e bash"
Assert-Match "e no diretorio registrado, nao no default" $calls '--dir /root/Outro'
Assert-Match "a distro baixada por nos entra no plano" $calls "wsl_distro=created"

# O TIL tem de viajar NU. O manifesto grava literalmente "~/AtlasFile" e o bash
# so expande `~` FORA de aspas: citar (o reflexo natural para proteger espaco)
# faria o install.sh procurar uma pasta chamada "~" e nao achar instalacao
# nenhuma. Aspas simples sao a armadilha obvia; as duplas tambem matam o til,
# porque o bash nao expande `~` dentro delas.
$sb = New-UninstallSandbox @("docker`tcreated", "install_dir`t~/AtlasFile")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
$calls = Calls
Assert-Match "o til viaja nu, para o bash expandir" $calls '--dir ~/AtlasFile'
Assert-NoMatch "e nunca citado, que mataria a expansao" $calls '--dir [\\''"]~'

# Espaco no -Dir e o caso que PRECISA de aspas, e ai elas aparecem escapadas na
# linha de comando (o Invoke-Native escapa as aspas internas antes de montar o
# -ArgumentList). O que importa e o caminho chegar INTEIRO.
$sb = New-UninstallSandbox @("docker`tcreated")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData", "-Dir", "/root/Meus Docs")
$calls = Calls
Assert-Match "-Dir com espaco viaja inteiro" $calls '--dir \\"/root/Meus Docs\\"'

Write-Host "== F3. -Uninstall -DryRun mostra o plano dos dois lados e para =="
$sb = New-UninstallSandbox @("docker`tcreated")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData", "-DryRun")
$calls = Calls
Assert-Match "o plano chega a tela" $out "Removal plan"
Assert-Match "e declara que nada foi tocado" $out "nothing was touched"
Assert-NoMatch "nao removeu pacote nenhum" $calls "winget uninstall"
Assert-NoMatch "nem mandou o outro lado executar" $calls "--uninstall --delegated --remove-deps --host-extra[^|]*--yes"

Write-Host "== M. o lado WSL CANCELOU: nada pode ser removido no Windows =="
# Este e o teste que faltava. Responder "n" ao plano devolvia 0, o install.ps1
# lia sucesso e apagava o Docker Desktop de uma maquina cujo dono tinha acabado
# de dizer nao.
$sb = New-UninstallSandbox @("docker`tcreated", "ollama`tcreated")
$env:AF_SH_SENTINEL = "cancelled"
$env:AF_SH_RC = "10"
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
$calls = Calls
Assert-NoMatch "NENHUM pacote do Windows foi removido" $calls "winget uninstall"
Assert-Match "e o instalador diz isso com todas as letras" $out "Nothing was removed on the Windows side"
Assert-NoMatch "sem veredito de sucesso" $out "AtlasFile removed. What already existed"

Write-Host "== N. codigo de saida engolido: falha fechada, nao remocao =="
# Nao ha documentacao oficial de que o wsl.exe propague o codigo de saida do
# comando Linux. Se ele for engolido, o instalador NAO pode ler isso como
# confirmacao - a sentinela e a segunda prova, e sem ela nada acontece.
$sb = New-UninstallSandbox @("docker`tcreated")
$env:AF_SH_SENTINEL = "nada"
$env:AF_SH_RC = "0"
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
Assert-NoMatch "sem a sentinela, nada e removido" (Calls) "winget uninstall"
Assert-Match "e a falha e explicita" $out "did not confirm the removal"

Write-Host "== O. plano ilegivel: para antes de tocar em qualquer coisa =="
$sb = New-UninstallSandbox @("docker`tcreated")
$env:AF_WSL_DEAD_DISTRO = "1"
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
Assert-NoMatch "nao removeu nada sem ter lido o plano" (Calls) "winget uninstall"
Assert-Match "diz que nao conseguiu ler o plano" $out "could not read the removal plan"

Write-Host "== P. pacote ausente do winget: mensagem util, nao falha crua =="
# Na maquina real o Ollama saiu com -1978335107 e a unica orientacao era
# "remove it from Settings > Apps", sem dizer por que.
$sb = New-UninstallSandbox @("ollama`tcreated")
$env:AF_WINGET_LIST_RC = "1"
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
Assert-NoMatch "nem tentou remover o que o winget nao conhece" (Calls) "winget uninstall"
Assert-Match "explica o motivo" $out "is not registered with winget under"

Write-Host "== Q. nada a remover: o instalador para sem inventar acao =="
$sb = New-UninstallSandbox @("docker`tpreexisting")
$env:AF_SH_ACTIONS = "0"
$out = Run-Installer @("-Yes", "-Uninstall", "-KeepData")
Assert-Match "diz que nao ha o que remover" $out "nothing to remove"
Assert-NoMatch "e nao chama o winget" (Calls) "winget uninstall"

Write-Host "== T. o relatorio final sai FORA do trilho, como no install.sh =="
# O `[N/N]` nao e um estagio de trabalho e o resumo nao pode ficar pendurado na
# calha depois que o trilho fecha. Mesmo desenho dos dois lados.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-EnableAuth", "-NoOpen")
Assert-Match "o trilho fecha antes do resumo" $out ([string][char]0x2570)
Assert-Match "e o resumo aparece" $out "AtlasFile is up in"
# a calha nao pode preceder o resumo: o trilho ja fechou
Assert-True "o resumo sai sem a calha" ($out -match ("(?m)^  AtlasFile is up in")) "o resumo veio com a calha na frente"
Assert-NoMatch "nada de resumo pendurado na calha" $out ("(?m)^" + [string][char]0x2502 + " .*AtlasFile is up")
# Contrapositivo do painel root (cenario A4): instalacao de usuario padrao
# ensina `wsl -e` SEM `-u root`. Assert-True porque a string e montada em
# tempo de execucao e nao existe contigua no fonte.
Assert-True "o painel ensina wsl -e sem -u root para usuario padrao" ($out -match [regex]::Escape("logs   wsl -e bash -c 'cd")) "painel sem o comando esperado para usuario padrao"
# Fase 4b: a unica frase que ainda prometia BUILD ao usuario do Windows.
Assert-Match "a fase 3 anuncia pull da imagem publicada" $out "published image pull"

Write-Host "== R. -Doctor diagnostica os DOIS lados e nao muda nada =="
$sb = New-UninstallSandbox @("docker`tcreated", "wsl`tcreated")
$out = Run-Installer @("-Doctor")
$calls = Calls
Assert-Match "relata o lado Windows" $out "Install manifest .Windows side."
Assert-Match "e delega o diagnostico do outro lado" $calls "--doctor"
Assert-Match "com o placar no fim" $out "Diagnosis .Windows side."
Assert-NoMatch "nao instalou nada" $calls "winget install"
Assert-NoMatch "nem removeu nada" $calls "winget uninstall"

Write-Host "== S. -DryRun nao instala nada, nem do lado Windows =="
$sb = New-Sandbox
Remove-Stub docker
$out = Run-Installer @("-Yes", "-DryRun")
$calls = Calls
Assert-Match "diz o que faria no Windows" $out "WOULD BE INSTALLED"
Assert-Match "e delega o plano do outro lado" $calls "--dry-run"
Assert-NoMatch "sem instalar coisa alguma" $calls "winget install"
Assert-Match "declara que nada foi instalado" $out "nothing was installed"

Write-Host "== S2. modo read-only numa maquina SEM WSL nao pode chamar 'wsl -e' =="
# Achado num Windows 11 REAL, recem-zerado com scripts/reset-wsl-windows.bat
# (2026-07-29): o -DryRun anunciou "WSL2 is already here", abriu "Pressione
# qualquer tecla para instalar o Subsistema do Windows para Linux" e terminou
# com "-DryRun: nothing was installed".
#
# Duas causas no mesmo bloco:
#  1. a deteccao era `Get-Tool wsl`, e wsl.exe VEM COM O WINDOWS 11 mesmo com a
#     feature desligada - sempre existia, sempre dizia "already here";
#  2. para montar o plano do lado Linux ele invocava `wsl -e`, e num Windows sem
#     WSL quem responde a essa chamada e o PROPRIO WINDOWS, com o instalador.
$sb = New-Sandbox
$env:AF_WSL_NOT_INSTALLED = "1"
$out = Run-Installer @("-Yes", "-DryRun")
$calls = Calls
Assert-NoMatch "nao chama wsl -e sem WSL (era o que abria o instalador do Windows)" $calls "-e bash"
Assert-NoMatch "nao mente dizendo que o WSL2 ja esta aqui" $out "WSL2 is already here"
Assert-Match "diz que o WSL2 SERIA instalado" $out "WOULD BE INSTALLED"
Assert-Match "explica que o lado Linux nao pode ser inspecionado" $out "Linux side cannot be inspected"
Assert-Match "segue declarando que nada foi instalado" $out "nothing was installed"
$env:AF_WSL_NOT_INSTALLED = ""

Write-Host "== S3. feature ligada e ZERO distro tambem cai no instalador do Windows =="
# O outro estado que engana: `wsl --status` responde normalmente, mas nao ha
# distro registrada - e `wsl -e` ali tambem faz o Windows oferecer instalar.
$sb = New-Sandbox
$env:AF_WSL_NO_DISTRO = "1"
$out = Run-Installer @("-Yes", "-DryRun")
Assert-NoMatch "sem distro, tambem nao chama wsl -e" (Calls) "-e bash"
Assert-Match "e trata como WSL ausente" $out "WOULD BE INSTALLED"
$env:AF_WSL_NO_DISTRO = ""

Write-Host "== S4. -Doctor sem WSL relata em vez de disparar o instalador =="
$sb = New-Sandbox
$env:AF_WSL_NOT_INSTALLED = "1"
$out = Run-Installer @("-Doctor")
Assert-NoMatch "o -Doctor nao chama wsl -e sem WSL" (Calls) "-e bash"
Assert-Match "relata o WSL indisponivel" $out "WSL is not usable"
$env:AF_WSL_NOT_INSTALLED = ""

Write-Host "== S6. sem WSL, nem o list e chamado (curto-circuito no --status) =="
# A PRIMEIRA versao de Test-WslUsable chamava --status e -l em sequencia, sempre.
# Isso so trocava a origem do prompt: medido no Windows 11 real, `wsl --list`
# TAMBEM dispara "Pressione qualquer tecla para instalar Subsistema do Windows
# para Linux" quando a feature esta ligada sem distro. Se o --status ja disse
# "is not installed", nao ha nada a listar - e listar custa um prompt de 60s.
$sb = New-Sandbox
$env:AF_WSL_NOT_INSTALLED = "1"
$out = Run-Installer @("-Yes", "-DryRun")
$calls = Calls
Assert-Match "consultou o --status" $calls "wsl --status"
Assert-NoMatch "e NAO listou distros depois de saber que nao ha WSL" $calls "wsl -l"
$env:AF_WSL_NOT_INSTALLED = ""

Write-Host "== S7. -KeepData: o plano diz que o volume FICA, nao 'still your call' =="
# Visto no Windows 11 real: o usuario passou -KeepData e o plano respondeu
# "data volume ... - still your call (--purge-data erases the index, --keep-data
# keeps it)". O texto de "ainda em aberto" e honesto quando nada foi decidido, e
# mentira quando a decisao veio na linha de comando - a flag nao chegava ao
# --plan-only.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-Uninstall", "-KeepData", "-DryRun")
Assert-Match "a decisao de manter chega ao plano" (Calls) "--keep-data"

Write-Host "== S5. CONTRAPOSITIVO: com WSL, os read-only continuam delegando =="
# Sem esta assertiva, a correcao acima passaria mesmo se alguem simplesmente
# parasse de falar com o lado Linux em qualquer situacao.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-DryRun")
Assert-Match "com WSL presente, delega o plano ao install.sh" (Calls) "-e bash"
Assert-Match "e reconhece o WSL2 que esta la" $out "WSL2 is already here"

Write-Host "== U. todo fluxo que abre o trilho tambem o fecha, e o veredito sai fora =="
# O -DryRun e o -Uninstall abriam o trilho com a regua e nunca fechavam, e o
# veredito da desinstalacao ficava pendurado na calha. Delegado, o install.sh
# PULA o un_report de proposito (para nao dar veredito antes de o lado Windows
# terminar), entao o fechamento e responsabilidade daqui.
$fecha = [string][char]0x2570
$calha = [string][char]0x2502

$sb = New-UninstallSandbox @("docker`tcreated", "wsl`tcreated")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
Assert-Match "o uninstall fecha o trilho" $out $fecha
Assert-True "e o veredito sai FORA da calha" ($out -match "(?m)^  AtlasFile removed") "veredito veio com a calha na frente"
Assert-NoMatch "nada de veredito pendurado na calha" $out ("(?m)^" + $calha + " .*AtlasFile removed")

$sb = New-Sandbox
Remove-Stub docker
$out = Run-Installer @("-Yes", "-DryRun")
Assert-Match "o -DryRun fecha o trilho" $out $fecha

# O caminho de RECUSA tambem fecha: a tela nao pode ficar com o trilho aberto so
# porque a remocao nao aconteceu. Mesmo mecanismo do cenario M.
$sb = New-UninstallSandbox @("docker`tcreated")
$env:AF_SH_SENTINEL = "cancelled"
$env:AF_SH_RC = "10"
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
Remove-Item Env:AF_SH_SENTINEL, Env:AF_SH_RC -ErrorAction SilentlyContinue
Assert-Match "o caminho de recusa tambem fecha o trilho" $out $fecha
Assert-Match "e a explicacao pendura na calha, sem furo" $out ("(?m)^" + $calha + "\s+Nothing was removed")

Write-Host "== V. defeitos vistos num Windows 11 real =="
# Todos medidos na maquina do dono do projeto, nao inferidos.
$fonte = Get-Content $installer -Raw

# A grade da animacao imprimia so ate a ultima coluna com conteudo, entao a lua
# que saia pela direita deixava RASTRO do quadro anterior. O install.sh nao tem
# o problema porque emite todas as colunas, inclusive as vazias.
Assert-Match "a grade apaga ate o fim da linha (sem rastro)" $fonte ([regex]::Escape('$esc[K'))

# Write-Gut JA emite a quebra de linha; o Write-Host "" seguinte produzia uma
# linha VAZIA, que aparecia como buraco na calha entre um passo e outro.
$dobradas = ([regex]::Matches($fonte, 'Write-Gut(?![^\r\n]*-NoNewline)[^\r\n]*Write-Host ""')).Count
Assert-True "nenhum Write-Gut seguido de Write-Host vazio" ($dobradas -eq 0) "$dobradas par(es) ainda dobram a linha"

# A guarda ACIMA olha o FONTE e nao bastou: o caso que sobreviveu no Windows
# real estava depois de um `}`, no fim do Invoke-Step, e nenhuma regex de uma
# linha o alcancava. Esta olha a TELA, que e o que o usuario ve: nenhuma linha
# VAZIA pode aparecer ENTRE duas linhas de calha.
#
# E ela rodava so no fluxo de INSTALACAO: cinco buracos sobreviveram no
# UNINSTALL, que ela nunca olhava. Guarda que cobre um caminho so da a impressao
# de cobrir todos - agora ela roda nos dois.
$calhaV = [string][char]0x2502
function Get-BuracosNaCalha([string]$Saida) {
    $linhas = $Saida -split "`r?`n"
    $achados = @()
    for ($i = 1; $i -lt $linhas.Count - 1; $i++) {
        if ($linhas[$i].Trim() -eq "" -and
            $linhas[$i-1].TrimStart().StartsWith($script:calhaV) -and
            $linhas[$i+1].TrimStart().StartsWith($script:calhaV)) {
            $achados += $linhas[$i-1].Trim()
        }
    }
    return ,$achados
}

$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-EnableAuth", "-NoOpen")
$buracos = Get-BuracosNaCalha $out
Assert-True "instalacao: nenhuma linha vazia ENTRE duas linhas de calha" ($buracos.Count -eq 0) ("depois de: " + ($buracos -join " | "))

$sb = New-UninstallSandbox @("docker`tcreated", "wsl`tcreated")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
$buracos = Get-BuracosNaCalha $out
Assert-True "desinstalacao: nenhuma linha vazia ENTRE duas linhas de calha" ($buracos.Count -eq 0) ("depois de: " + ($buracos -join " | "))

# Guardas presas ao CORPO da funcao, nunca a uma distancia em caracteres. A
# primeira versao usava .{0,600} e reprovou o codigo CORRETO: o alvo ficava a
# 715 chars porque um comentario de seis linhas entrou no meio. Numero magico em
# guarda so avisa que alguem escreveu um comentario.
$corpoConfirm = [regex]::Match($fonte, '(?s)function Confirm-Step.*?\n\}').Value
$corpoLogTail = [regex]::Match($fonte, '(?s)function Show-LogTail.*?\n\}').Value

# A pergunta era a unica linha do trilho que nao pendurava nele.
Assert-Match "a pergunta sai na calha" $corpoConfirm 'Write-Host \$script:Gut'
# E o rabo do log saia como um bloco inteiro fora do trilho.
Assert-Match "o rabo do log sai na calha" $corpoLogTail 'Write-Gut'
# Sem --silent o winget roda o instalador do Docker com INTERFACE e ele espera
# um clique em "Close": o Docker instala e o winget devolve falha assim mesmo.
Assert-Match "a instalacao do Docker e silenciosa" $fonte ([regex]::Escape('"--silent", "--disable-interactivity"'))

# A barra viva ocupa a ultima linha: sem apaga-la a pergunta sai grudada nela.
Assert-Match "Confirm-Step limpa a barra antes de perguntar" $fonte '(?s)function Confirm-Step.{0,400}?Clear-AfBar'
Assert-Match "Confirm-Plan limpa a barra antes de perguntar" $fonte '(?s)function Confirm-Plan.{0,400}?Clear-AfBar'

# U+25B0/U+25B1 saem como [?] no console do Windows; Block Elements saem.
# Divergencia deliberada: no mac/Linux o par original renderiza e fica melhor.
Assert-Match "a barra usa Block Elements" $fonte '0x2588'
Assert-NoMatch "e nao os paralelogramos" $fonte '0x25B0'

Write-Host "== V2. defeitos da segunda rodada no Windows 11 real =="
$corpoSpinner = [regex]::Match($fonte, '(?s)function Wait-Spinner.*?\n\}').Value
$corpoPanel   = [regex]::Match($fonte, '(?s)function Write-Panel.*?\n\}').Value

# Saia "True waiting for Docker's WSL integration": o local $ok sombreava o
# glifo global $OK, porque o PowerShell ignora maiusculas em nomes de variavel.
# `\$ok\s*=` e nao `\$ok\b`: o comentario que explica o defeito CITA $ok, e a
# segunda forma casaria com a prosa. Guarda tem de olhar atribuicao, nao texto.
Assert-NoMatch "o spinner nao usa um local que sombreia o glifo" $corpoSpinner '\$ok\s*='

# A caixa tinha largura fixa e o comando do WSL vazava por fora dela.
Assert-NoMatch "a caixa nao tem largura fixa" $corpoPanel 'PadRight\(55\)'
Assert-Match "a caixa cresce com o conteudo" $corpoPanel '\$l\.Length -gt \$largura'

# A barra ficava encalhada no meio da saida do outro instalador.
Assert-Match "a barra e apagada antes de delegar ao WSL" $fonte '(?s)takes over from here.{0,400}?Clear-AfBar'

# O trilho fechava DEPOIS da caixa, deixando uma calha solta no fim.
# ORDEM, medida por posicao: o veredito sai antes da caixa. A versao anterior
# casava o texto exato do fechamento e reprovou quando ele virou condicional -
# a propriedade nao tinha mudado, so a forma.
$posNota  = $fonte.IndexOf('Write-Note ("AtlasFile is up')
$posCaixa = $fonte.IndexOf('Write-Panel @(')
Assert-True "o veredito sai ANTES da caixa" (($posNota -gt 0) -and ($posCaixa -gt $posNota)) "nota em $posNota, caixa em $posCaixa"

# Sem --accept-license o contrato do Docker e pedido no PRIMEIRO USO, e e ali
# que o usuario precisa clicar - o --silent so cala o instalador.
#
# Literal inteiro, e nao um bloco delimitado por parenteses: os comentarios
# vizinhos tem parenteses e encerravam a captura antes dos argumentos. Ja
# aconteceu duas vezes nesta bancada.
Assert-Match "o contrato do Docker e aceito na instalacao" $fonte ([regex]::Escape('"--custom", "--accept-license --backend=wsl-2 --always-run-service"'))

Write-Host "== X. os documentos ficam no disco do WINDOWS, nao dentro da distro =="
# Sem --projects-root o install.sh usava o default dele e, como a distro nao
# inicializada nos faz rodar como root, os documentos nasciam em
# /root/Documents/AtlasFileProjects: fora de qualquer pasta do Explorer e
# refens de um `wsl --unregister` que o nosso --uninstall nao controla.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-EnableAuth", "-NoOpen")
$calls = Calls
Assert-Match "a delegacao carrega a raiz de projetos" $calls "--projects-root"
Assert-Match "e ela aponta para um disco do Windows" $calls '--projects-root /mnt/'
Assert-NoMatch "nunca para dentro da distro" $calls '--projects-root .{0,2}/root'

# Caminho do Windows dado a mao tambem e convertido - o help promete os dois.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-ProjectsRoot", "D:\Meus Documentos\Atlas", "-NoOpen")
$calls = Calls
# Este caminho TEM espaco ("D:\Meus Documentos\Atlas"), entao ele vem citado.
Assert-Match "converte o caminho que o usuario deu" $calls '--projects-root \\"/mnt/d/'
# O espaco no caminho tem de sobreviver: a linha viaja dentro de um bash -c.
Assert-NoMatch "sem quebrar no espaco do caminho" $calls '--projects-root \\"?/mnt/d/Meus\s*$'

Write-Host "== V3. o que a desinstalacao no Windows 11 real mostrou =="
$corpoBar  = [regex]::Match($fonte, '(?s)function Show-AfBar.*?\n\}').Value
$corpoConfP= [regex]::Match($fonte, '(?s)function Confirm-Plan.*?\n\}').Value

# A tela inteira saiu com mojibake: Get-Content -Raw decodifica com a code page
# ANSI no PowerShell 5.1, e os bytes UTF-8 do WSL viravam lixo.
Assert-Match "a captura decide a codificacao pelos bytes" $fonte 'function Get-AfText'
Assert-NoMatch "e ninguem mais le com a code page ANSI" $fonte 'Get-Content \$f -Raw'

# A barra conta FASES; no uninstall ela aparecia como "fase 0/3".
Assert-Match "sem fase, sem barra" $corpoBar '\$script:BarDone -le 0'

# A pergunta do plano era a unica linha sem calha.
Assert-Match "a confirmacao do plano sai na calha" $corpoConfP 'Write-Host \$script:Gut'

# O desinstalador do Docker se relanca do TEMP e o NETO escreve em CONOUT$, que
# nenhum redirecionamento do pai captura: o log dele vazou por cima do spinner.
Assert-Match "o passo com spinner roda em console proprio" $fonte ([regex]::Escape('-WindowStyle Hidden -PassThru'))

Write-Host "== V4. o que a segunda desinstalacao no Windows real mostrou =="
$corpoEnable = [regex]::Match($fonte, '(?s)function Set-AfDockerSetting.*?\n\}').Value

# O log era ACUMULADO entre execucoes: o "last lines" mostrou um winget
# uninstall bem-sucedido de OUTRA execucao, logo abaixo de "Nothing was removed".
Assert-Match "o log e zerado a cada execucao" $fonte 'WriteAllText\(\$script:AfLog'
# E era gravado com a code page ANSI, quebrando a calha dentro do proprio log.
Assert-Match "e gravado em UTF-8 sem BOM" $fonte 'AppendAllText'
Assert-NoMatch "sem Add-Content no log" $fonte 'Add-Content -Path \$script:AfLog'

# Parar so porque o lado WSL nao tem acao deixava o Docker instalado.
Assert-Match "o orquestrador olha os DOIS escopos" $fonte '\$temAcoesWindows'

# Numa instalacao recem-feita o Docker ainda nao escreveu as preferencias.
Assert-Match "a integracao cria o arquivo quando ele nao existe" $corpoEnable 'New-Item -ItemType Directory -Path \$base'
Assert-Match "e acrescenta a chave quando ela falta" $corpoEnable 'Add-Member -NotePropertyName \$chave'

Write-Host "== V5. handover, Ollama ausente e Docker sem clique =="
# As duas metades da tela desenhavam trilhos de larguras DIFERENTES, porque o
# install.sh media com tput e o orquestrador com Get-AfRuleWidth.
# Contada por PROPORCAO, e nao por um literal: a versao anterior procurava a
# string "export COLUMNS=", que deixou de existir quando o prefixo virou funcao
# - e reprovou codigo correto. O fato e "TODA delegacao leva o prefixo", nao
# "existe tal string N vezes".
$delegacoes = ([regex]::Matches($fonte, '\$AF_CURL \$AF_SH_URL')).Count
$comPrefixo = ([regex]::Matches($fonte, '\$\(Get-AfEnvPrefix\)\$AF_CURL')).Count
Assert-True "toda delegacao leva o ambiente do orquestrador" (($delegacoes -ge 5) -and ($comPrefixo -eq $delegacoes)) "$comPrefixo de $delegacoes"

# Dois fechamentos: o do install.sh e o daqui, com uma calha solta entre eles.
Assert-Match "o trilho fecha uma vez so" $fonte '\$script:TrilhoFechadoNoWsl'

# "Ollama preserved" era dito sem olhar a maquina - o usuario o tinha removido
# por conta propria ANTES de instalar o AtlasFile.
# Literal, e nao bloco delimitado por chave: capturar "ate o primeiro }" para
# no primeiro fechamento aninhado. Ja errei assim duas vezes nesta bancada.
Assert-Match "so afirma preservacao do que esta aqui" $fonte ([regex]::Escape('if (Get-Tool $item.Key) {'))

# winget uninstall nao aceita --override nem --custom, entao --silent nao
# alcanca o instalador do Docker: ele abria janela esperando um clique.
Assert-Match "o Docker e removido pelo desinstalador dele, com --quiet" $fonte ([regex]::Escape('DiretoArgs = @("uninstall", "--quiet")'))
Assert-Match "com o winget como reserva" $fonte '\$item.Direto -and \(Test-Path \$item.Direto\)'

Write-Host "== V6. a regua do Windows varre a rampa, como a do WSL =="
$corpoRegua = [regex]::Match($fonte, '(?s)function Write-Rule\(.*?\n\}').Value
# Tres cores fixas de 16 de um lado e degrade do outro: as duas metades da tela
# nao pareciam o mesmo produto.
Assert-Match "a regua usa a rampa do produto" $corpoRegua 'Get-AfRampHex'
Assert-Match "e o fechamento tambem" $fonte ([regex]::Escape('(Get-AfEsc (Get-AfRampHex 1))'))
# Degradado sem truecolor viraria lixo na tela: a queda para 16 cores continua.
Assert-Match "com queda para cor chapada quando nao ha truecolor" $corpoRegua 'if \(-not \$AfTrueColor -or \$AfPlain\)'
# A conversao hex->escape estava escrita a mao em dois lugares e seria um
# terceiro; tres copias divergem na primeira alteracao.
$copias = ([regex]::Matches($fonte, '38;2;\$')).Count
Assert-True "a conversao para escape de 24 bits vive num lugar so" ($copias -le 1) "$copias copias"

Write-Host "== V7. a captura nao vaza linhas em branco para a tela =="
# O texto capturado era montado como (stdout + quebra) + (stderr + quebra). Com
# o stderr vazio, o split por linha produzia varias entradas vazias no fim, e
# cada uma virava uma linha em branco - antes da pergunta do volume e antes de
# "removing Docker Desktop". A guarda de tela nao pegava porque as vazias
# ficavam ENTRE uma linha de calha e uma pergunta sem calha.
Assert-Match "so entra no texto o arquivo que tem conteudo" $fonte ([regex]::Escape('if ($parte.Trim()) { $texto += ($parte.TrimEnd()'))
$semTrim = ([regex]::Matches($fonte, 'foreach \(\$linha in \(\$\w+ -split')).Count
Assert-True "e quem ecoa apara o fim antes de dividir" ($semTrim -eq 0) "$semTrim laco(s) ecoam sem aparar"

# Prova na TELA, e nao so no fonte: a desinstalacao nao pode ter duas linhas em
# branco seguidas em lugar nenhum.
$sb = New-UninstallSandbox @("docker`tcreated", "wsl`tcreated")
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
# A partir do TRILHO, e nao do topo da tela: o banner emoldura a arte com uma
# linha em branco de cada lado, e a propria grade tem a fileira vazia de cima
# (por onde o cometa passa) e a de baixo (as luas). Isso e desenho, nao buraco -
# a primeira versao desta guarda acusava justamente essas quatro e reprovava
# codigo correto. O assunto dela e o trilho.
$linhasU = $out -split "`r?`n"
$inicio = 0
for ($i = 0; $i -lt $linhasU.Count; $i++) {
    if ($linhasU[$i].TrimStart().StartsWith($calhaV)) { $inicio = $i; break }
}
$duplas = 0
for ($i = $inicio + 1; $i -lt $linhasU.Count; $i++) {
    if ($linhasU[$i].Trim() -eq "" -and $linhasU[$i-1].Trim() -eq "") { $duplas++ }
}
Assert-True "sem linhas em branco seguidas depois que o trilho comeca" ($duplas -eq 0) "$duplas ocorrencia(s)"

Write-Host "== V8. o outro lado recebe o que precisa para desenhar igual =="
$corpoWrap = [regex]::Match($fonte, '(?s)function Write-Wrapped.*?\n\}').Value
$corpoHand = [regex]::Match($fonte, '(?s)function Write-Handover.*?\n\}').Value

# Nada disso atravessa o wsl.exe sozinho, e sem os tres o install.sh se degrada
# em silencio: reguas brancas, e a desinstalacao (capturada) toda branca.
Assert-Match "o prefixo leva a largura" $fonte 'COLUMNS=\$\(Get-AfRuleWidth\)'
Assert-Match "leva o TERM" $fonte 'TERM=xterm-256color'
Assert-Match "leva o COLORTERM" $fonte 'COLORTERM=truecolor'
Assert-Match "e diz que ha cor mesmo sob captura" $fonte 'ATLASFILE_FORCE_COLOR=1'
# Anunciar truecolor sem ter seria mentir para o outro lado.
Assert-Match "so quando ESTE lado tem truecolor" $fonte 'if \(\$AfTrueColor -and -not \$AfPlain\)'

# A divisoria do handover: onde um instalador entrega ao outro.
Assert-True "existe a divisoria de handover" ($corpoHand.Length -gt 0) "Write-Handover nao existe"
Assert-Match "ela varre a rampa como as reguas" $corpoHand 'Get-AfRampHex'
Assert-Match "e e chamada antes de delegar" $fonte '(?s)Write-Handover "handover.*?\n\$argsSh'

# So o glifo colorido, como o ok() do install.sh e o do mac-env.
Assert-Match "so o glifo recebe cor" $corpoWrap 'Write-Host \$Glifo -ForegroundColor \$Cor -NoNewline'
Assert-NoMatch "o texto nao e pintado junto" $corpoWrap 'Write-Host \("  " \+ \$linhas\[\$i\]\) -ForegroundColor'

Write-Host "== V9. o caminho dos documentos nao depende do que esta montado =="
$corpoConv = [regex]::Match($fonte, '(?s)function ConvertTo-AfWslPath.*?\n\}').Value
$corpoRaiz = [regex]::Match($fonte, '(?s)function Get-AfProjectsRoot.*?\n\}').Value

# Numa reinstalacao real o wslpath devolveu
# /mnt/wsl/docker-desktop-bind-mounts/Ubuntu/<hash> para a pasta de documentos.
# A conversao lexica vem PRIMEIRO porque nao depende de estado nenhum.
$posLexica = $corpoConv.IndexOf('/mnt/')
$posWslpath = $corpoConv.IndexOf('wslpath')
Assert-True "a conversao lexica vem antes do wslpath" (($posLexica -gt 0) -and ($posWslpath -gt $posLexica)) "lexica em $posLexica, wslpath em $posWslpath"

# E o resultado e CONFERIDO: traducao que perde o nome da pasta nao e traducao
# daquela pasta.
Assert-Match "o resultado e conferido antes de ser usado" $corpoRaiz 'EndsWith\("/AtlasFileProjects"\)'
Assert-Match "e recusado devolve vazio, para o padrao do Linux valer" $corpoRaiz 'return ""'

Write-Host "== W. a integracao Docker<->WSL e ligada sozinha =="
# Pelo caminho REAL: o stub do wsl diz que o docker nao responde la dentro, que
# e exatamente o estado da maquina real, e o instalador tem de ligar a chave em
# vez de mandar clicar num menu.
$sb = New-Sandbox
$env:AF_WSL_NO_DOCKER = "1"
$dirCfg = Join-Path $sb "dockercfg"
New-Item -ItemType Directory -Path $dirCfg -Force | Out-Null
'{ "enableIntegrationWithDefaultWslDistro": false, "outraChave": 1 }' |
    Set-Content (Join-Path $dirCfg "settings-store.json") -Encoding UTF8
$env:ATLASFILE_DOCKER_SETTINGS_DIR = $dirCfg
$out = Run-Installer @("-Yes", "-NoOpen")
$depois = Get-Content (Join-Path $dirCfg "settings-store.json") -Raw | ConvertFrom-Json
Assert-True "ligou a integracao no arquivo do Docker" ($depois.enableIntegrationWithDefaultWslDistro -eq $true) "ficou $($depois.enableIntegrationWithDefaultWslDistro)"
Assert-True "preservando o resto do arquivo" ($depois.outraChave -eq 1) "perdeu outraChave"
Assert-Match "e disse o que fez" $out "adjusting Docker Desktop"

# O questionario de boas-vindas do Docker sai do caminho pela chave DOCUMENTADA.
# A tela de LOGIN continua: nao ha chave documentada para ela, e inventar uma
# sobre esquema alheio e palpite.
Assert-True "e o questionario de boas-vindas tambem foi suprimido" ($depois.displayedOnboarding -eq $true) "ficou $($depois.displayedOnboarding)"

# Arquivo AUSENTE: foi o caso da maquina real - Docker recem-instalado ainda
# nao tinha escrito preferencia nenhuma, e a funcao desistia calada.
$sb = New-Sandbox
$env:AF_WSL_NO_DOCKER = "1"
$dirCfg = Join-Path $sb "dockercfg0"
$env:ATLASFILE_DOCKER_SETTINGS_DIR = $dirCfg   # nem o diretorio existe
$out = Run-Installer @("-Yes", "-NoOpen")
$arqCriado = Join-Path $dirCfg "settings-store.json"
Assert-True "cria o arquivo de preferencias que faltava" (Test-Path $arqCriado) "nao criou $arqCriado"
if (Test-Path $arqCriado) {
    $novo = Get-Content $arqCriado -Raw | ConvertFrom-Json
    Assert-True "ja nascendo com a integracao ligada" ($novo.enableIntegrationWithDefaultWslDistro -eq $true) "ficou $($novo.enableIntegrationWithDefaultWslDistro)"
}

# Esquema desconhecido ou arquivo ilegivel NAO podem derrubar a instalacao: o
# formato e interno do Docker e nao tem contrato publico. Cai na mensagem
# manual, que continua existindo.
$sb = New-Sandbox
$env:AF_WSL_NO_DOCKER = "1"
$dirCfg = Join-Path $sb "dockercfg2"
New-Item -ItemType Directory -Path $dirCfg -Force | Out-Null
'nao e json' | Set-Content (Join-Path $dirCfg "settings-store.json") -Encoding UTF8
$env:ATLASFILE_DOCKER_SETTINGS_DIR = $dirCfg
$out = Run-Installer @("-Yes")
Assert-NoMatch "nao explode com JSON invalido" $out "Unhandled|ParameterBindingException|ConvertFrom-Json"
Assert-Match "e ainda ensina o caminho manual" $out "WSL Integration"
Remove-Item Env:ATLASFILE_DOCKER_SETTINGS_DIR -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "$script:Pass passaram, $script:Fail falharam"
# exit EXPLICITO tambem no sucesso. Sem ele a bancada nao define codigo de saida
# e o $LASTEXITCODE que o CI le e o do ULTIMO comando nativo executado — ou seja,
# o do instalador do cenario final. Bastou o ultimo cenario passar a exercitar um
# caminho de RECUSA (onde sair com 1 e o comportamento correto) para o CI
# reprovar uma bancada inteira sem falha nenhuma. O contrato da bancada nao
# pode vazar o codigo de saida do que ela testa.
if ($script:Fail -gt 0) { exit 1 }
exit 0
