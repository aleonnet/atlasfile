# Testes do install.ps1 — executa o INSTALADOR INTEIRO contra stubs de winget,
# wsl, docker e ollama, no PowerShell real. Espelha o que tests/installer/run.sh
# faz para o bash.
#
# Existe porque três bugs seguidos escaparam por eu validar a FUNÇÃO e não a
# FORMA REAL DE USO: argumento com traço virando parâmetro, barra de progresso
# quebrada por pipe, stderr virando erro terminante. Os stubs reproduzem
# exatamente essas formas.
#
#   pwsh -File tests/installer/win/run.ps1
$ErrorActionPreference = "Stop"
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
if "%2"=="echo" echo atlasfile_wsl_ok
echo %*|findstr /c:"--plan-only" >nul
if not errorlevel 1 goto planonly
echo %*|findstr /c:"--uninstall" >nul
if not errorlevel 1 goto unexec
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
    $env:ATLASFILE_WSL_PROBE_MS = "2000"   # teto curto na bancada
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
$out = Run-Installer @("-Yes")
Assert-Match "reconhece o WSL como utilizavel" $out "WSL2 available"
Assert-Match "rodou wsl --update antes da verificacao" (Calls) "wsl --update"
Assert-Match "avisa que vai usar root" $out "using root for this install"
Assert-Match "delegou ao WSL com -u root" (Calls) "wsl -u root -e bash"

Write-Host "== A5. distro listada que NAO responde: nao trava e aponta virtualizacao =="
# Relato real: o usuario teve que dar Ctrl+C porque `wsl -e` ficou pendurado, na
# mesma maquina em que o Docker acusava "Virtualization support not detected".
$sb = New-Sandbox
$env:AF_WSL_HANG = "1"
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
Assert-NoMatch "-WithOllama nao e mais aceito" $out "WithOllama"

Write-Host "== H. o script entregue ao WSL chega INTEIRO, nao partido em palavras =="
# Medido na maquina do usuario: o -ArgumentList do Start-Process junta o array
# com espacos e NAO cita nada, entao o `bash -c "curl -fsSL <url> | bash -s --
# --no-open"` chegou como `bash -c curl` com o resto solto. O curl rodou sem
# argumento algum e a instalacao morreu em "curl: try 'curl --help'". A bancada
# nao pegava porque o stub registrava a chamada e devolvia 0 sem NUNCA conferir
# se o argumento tinha chegado inteiro.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-EnableAuth", "-Dir", "/root/Outro")
$calls = Calls
Assert-Match "o -c chega como UM argumento citado" $calls '-c "curl -fsSL'
Assert-Match "as flags do install.sh viajam no mesmo argumento" $calls 'bash -s -- --no-open --delegated --yes --enable-auth'
Assert-NoMatch "o curl nao roda pelado" $out "curl: try"
# Um banner por execucao: o do install.sh nao pode ser desenhado logo depois do
# nosso - eram dois desenhos diferentes na mesma tela.
Assert-Match "a delegacao silencia o banner do outro lado" $calls "--delegated"
# --no-ollama nao pode mais ser passada: a flag saiu junto com o recurso, e uma
# flag desconhecida faz o install.sh sair com "Unknown flag".
Assert-NoMatch "nao passa flag que o outro lado nao conhece mais" $calls "--no-ollama"
Assert-Match "-Dir viaja para o outro lado" $calls "--dir /root/Outro"
# O curl endurecido (mesma dureza do mac-env-setup): um solucao de rede nao pode
# virar instalacao pela metade.
Assert-Match "download com retry e protocolo pinado" $calls "--proto '=https' --tlsv1.2 --retry 3"

Write-Host "== K. o caminho ANIMADO executa e termina no quadro final =="
# Sem o ATLASFILE_FORCE_ANIM este caminho seria intestavel: redirecionado, o
# instalador escolhe o banner estatico, e um erro de indice na tabela da orbita
# ou um escape errado so apareceria na tela do usuario.
$sb = New-Sandbox
$env:ATLASFILE_FORCE_ANIM = "1"
$env:WT_SESSION = "harness"    # o truecolor e a outra metade da guarda de animacao
Remove-Item env:COLORTERM -ErrorAction SilentlyContinue
$out = Run-Installer @("-Yes")
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
$out = Run-Installer @("-Yes")
Assert-Match "o banner sai de qualquer jeito" $out "AtlasFile"
Assert-Match "a frase de chamada sai de qualquer jeito" $out "Your documents have gravity"
Assert-NoMatch "sem erro de Add-Type nem de tipo ausente" $out "Add-Type|Unable to find type|Nao foi possivel encontrar o tipo|CompilationErrors"

Write-Host "== J. saida de terceiro vai para o LOG, nunca para a tela =="
# A regra do benchmark (mac_env_install.sh:656 e run_step do install.sh): o
# comando roda com a saida redirecionada e a tela mostra so o nosso vocabulario.
# Sem esta checagem, "padronizamos a UI" seria afirmacao, nao propriedade.
$sb = New-Sandbox
Remove-Stub docker
$out = Run-Installer @("-Yes", "-InstallDeps")
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
Assert-Match "e no diretorio registrado, nao no default" $calls "--dir /root/Outro"
Assert-Match "a distro baixada por nos entra no plano" $calls "wsl_distro=created"

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

Write-Host ""
Write-Host "$script:Pass passaram, $script:Fail falharam"
if ($script:Fail -gt 0) { exit 1 }
