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
exit /b 0
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

Write-Host "== E. -WithOllama chama o pull com array explicito =="
$sb = New-Sandbox
$env:AF_OLLAMA_PRESENT = "1"
$out = Run-Installer @("-Yes", "-WithOllama", "-OllamaModel", "gemma3:1b")
Assert-Match "chamou ollama list" (Calls) "ollama list"
Assert-Match "chamou ollama pull do modelo pedido" (Calls) "ollama pull gemma3:1b"
Assert-NoMatch "sem erro de binding no ollama" $out "AmbiguousParameter|ParameterBindingException"

Write-Host "== H. o script entregue ao WSL chega INTEIRO, nao partido em palavras =="
# Medido na maquina do usuario: o -ArgumentList do Start-Process junta o array
# com espacos e NAO cita nada, entao o `bash -c "curl -fsSL <url> | bash -s --
# --no-open"` chegou como `bash -c curl` com o resto solto. O curl rodou sem
# argumento algum e a instalacao morreu em "curl: try 'curl --help'". A bancada
# nao pegava porque o stub registrava a chamada e devolvia 0 sem NUNCA conferir
# se o argumento tinha chegado inteiro.
$sb = New-Sandbox
$out = Run-Installer @("-Yes", "-EnableAuth")
$calls = Calls
Assert-Match "o -c chega como UM argumento citado" $calls '-c "curl -fsSL'
Assert-Match "as flags do install.sh viajam no mesmo argumento" $calls 'bash -s -- --no-open --yes --enable-auth"'
Assert-NoMatch "o curl nao roda pelado" $out "curl: try"

Write-Host "== I. Ollama instalado, servico ainda de pe atras: espera e segue =="
# Medido na maquina do usuario, logo apos "Successfully installed":
#   Error: Head "http://127.0.0.1:11434/": ... recusou ativamente
# O binario existia; o servico ainda nao. Mesma classe do daemon do Docker.
$sb = New-Sandbox
$env:AF_OLLAMA_DOWN = "1"
$env:ATLASFILE_OLLAMA_WAIT = "4"
$out = Run-Installer @("-Yes", "-WithOllama", "-OllamaModel", "gemma3:1b")
Assert-Match "anuncia a espera pelo servico" $out "waiting for the Ollama service"
Assert-Match "avisa sem travar a instalacao" $out "Ollama service did not answer"
Assert-Match "a instalacao segue ate a fase do WSL" $out "Installing AtlasFile inside WSL"

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

Write-Host "== F. -Uninstall -RemoveDeps remove so o que o manifesto marca =="
$sb = New-Sandbox
$mf = Join-Path $env:LOCALAPPDATA "AtlasFile\host-prereqs"
New-Item -ItemType Directory -Path (Split-Path $mf) -Force | Out-Null
@("schema`t1", "docker`tcreated", "ollama`tpreexisting") | Set-Content $mf
$out = Run-Installer @("-Yes", "-Uninstall", "-RemoveDeps", "-KeepData")
$calls = Calls
Assert-Match "removeu o Docker, que o manifesto marca created" $calls "winget uninstall.*Docker.DockerDesktop"
Assert-Match "remocao tambem evita a msstore" $calls "winget uninstall.*--source winget"
Assert-NoMatch "NAO removeu o Ollama, que era preexisting" $calls "winget uninstall.*Ollama"
Assert-Match "avisa que o WSL nunca e removido" $out "WSL is never removed"
Assert-NoMatch "sem erro de binding na desinstalacao" $out "AmbiguousParameter|ParameterBindingException"
# stderr de comando nativo vira ErrorRecord NAO-terminante por design; o criterio
# e a desinstalacao CONCLUIR, nao a ausencia do texto na tela.
Assert-Match "a desinstalacao chegou ao fim" $out "What already existed on this machine was preserved"

Write-Host ""
Write-Host "$script:Pass passaram, $script:Fail falharam"
if ($script:Fail -gt 0) { exit 1 }
