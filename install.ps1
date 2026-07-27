# AtlasFile - Windows installer (via WSL2)
#
#   irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex
#
# Strategy: AtlasFile runs in Linux containers; on Windows the supported path is
# WSL2 + Docker Desktop (WSL backend). This script checks prerequisites - and
# OFFERS to install what is missing (wsl --install, Docker Desktop via winget,
# then delegates to install.sh inside the default WSL distro:
# one real installer, no duplicated logic.
#
# Parameters (when saved and run as a file; under `iex` the prompts cover it):
#   -Yes           non-interactive (accept defaults; does NOT install deps)
#   -InstallDeps   authorize installing missing prerequisites without prompting
#   -EnableAuth    enable API authentication (forwarded to install.sh)
#   -Uninstall     print a removal plan and, once confirmed, revert what this
#                  installer created (delegates the Linux side to install.sh
#                  inside WSL and reverts the Windows side from the manifest)
#   -PurgeData     uninstall: also erase the OpenSearch volume (the index)
#   -KeepData      uninstall: keep the OpenSearch volume
#   -RemoveDeps    uninstall: also remove Windows-side deps this script installed
#   -Help          this help
param(
    [switch]$Yes,
    [switch]$InstallDeps,
    [switch]$EnableAuth,
    [switch]$Uninstall,
    [switch]$PurgeData,
    [switch]$KeepData,
    [switch]$RemoveDeps,
    [switch]$Force,
    [switch]$Doctor,
    [switch]$DryRun,
    [switch]$Verbose,
    [switch]$Help,
    [string]$Dir = ""
)

$ErrorActionPreference = "Stop"

# Console em UTF-8: sem isto a barra de progresso do winget desenha "?" no lugar
# dos glifos (visto num Windows real, com o percentual saindo como "?" enquanto
# os megabytes apareciam certos). Falha aqui e irrelevante para a instalacao.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 }
catch { Write-Verbose "console encoding unchanged: $($_.Exception.Message)" }

# --- Glyphs by code point, so THIS FILE STAYS PURE ASCII --------------------
# Measured on Windows 11 (build 26200) with Windows PowerShell 5.1:
#   * UTF-8 without a BOM is read as ANSI when run with -File, and the parser
#     dies on the first multi-byte glyph ("Missing closing ')'" cascade) - the
#     version on main does not even start that way;
#   * adding a BOM fixes -File but breaks `irm | iex`, because the string then
#     begins with U+FEFF and the leading '#' is no longer the first character.
# An ASCII-only source is the only form that survives BOTH delivery paths, and
# it is immune to a server that omits charset=utf-8 as well.
$BLK_LO    = [string][char]0x2584   # lower half block
$BLK_FU    = [string][char]0x2588   # full block
$BLK_UP    = [string][char]0x2580   # upper half block
$BLK_RT    = [string][char]0x2590   # right half block
$BLK_LF    = [string][char]0x258C   # left half block
$MOON_NEAR = [string][char]0x25CF   # near moon
$MOON_FAR  = [string][char]0x2022   # far moon
$OK        = [string][char]0x2714
$BAD       = [string][char]0x2718
$DOT       = [string][char]0x00B7

function Show-Usage {
    Write-Host @"
AtlasFile installer (Windows / WSL2)

Usage:
  irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex
  & ([scriptblock]::Create((irm .../install.ps1))) -EnableAuth

AtlasFile runs in Linux containers, so on Windows the supported path is
WSL2 + Docker Desktop. This script prepares the Windows side and then runs the
real installer inside WSL.

Install options:
  -Dir PATH       Where AtlasFile lives inside WSL (default: ~/AtlasFile).
                  Forwarded to install.sh as --dir, install and uninstall alike
  -Yes            Non-interactive. On its own it NEVER installs system
                  dependencies - see -InstallDeps
  -InstallDeps    Authorize installing WSL2 and Docker Desktop
  -EnableAuth     Enable API authentication (forwarded to install.sh)

Uninstall options:
  -Uninstall      Print a removal plan and, once confirmed, revert what this
                  installer created. What already existed is preserved
  -PurgeData      Uninstall: also erase the OpenSearch volume (the index)
  -KeepData       Uninstall: keep the OpenSearch volume
  -RemoveDeps     Uninstall: also remove the Windows-side dependencies that the
                  manifest records as installed by AtlasFile
  -Force          Uninstall: remove the clone inside WSL even with local changes

Diagnostics:
  -Doctor         Read-only report of BOTH sides of this machine: Windows
                  prerequisites and manifest, then the Linux side inside WSL.
                  Installs nothing, changes nothing
  -DryRun         Show, do not do. On its own: what an install would find and do
                  on this machine. With -Uninstall: the removal plan for BOTH
                  sides, and nothing is touched
  -Verbose        Show the output of every tool as it runs, instead of hiding
                  it in the log

Other:
  -Help           This help

Manifest: %LOCALAPPDATA%\AtlasFile\host-prereqs
"@
}

# Padrao adotado do instalador do OpenClaw (openclaw.ai/install.ps1), que resolve
# isto ha muito tempo: guarda o codigo num script-scope e termina conforme o MODO
# DE ENTREGA - `exit` quando roda como arquivo ($PSCommandPath preenchido) e
# `throw` quando veio por `irm | iex`, caso em que `exit` FECHARIA a janela do
# usuario levando junto a mensagem de erro (relatado numa maquina real).
$script:InstallExitCode = 0
# Inicializado aqui, antes de qualquer uso: o bloco -Uninstall referencia isto
# ANTES da deteccao do WSL, e um $null vira argumento vazio na chamada do wsl.
$script:WslUser = @()

function Stop-Installer([int]$Code) {
    $script:InstallExitCode = $Code
    # Arquivo: encerra com o codigo, que e o que automacao espera.
    if ($PSCommandPath) { exit $Code }
    # Sob `irm | iex` o script roda na sessao do usuario: `exit` FECHARIA a
    # janela e `throw` pinta de vermelho ate o caminho de SUCESSO - foi o que
    # aconteceu depois de instalar o WSL com exito ("AtlasFile installer stopped
    # with exit code 0." em vermelho). Quem chama faz `return` logo em seguida,
    # que e como o instalador do OpenClaw encerra (Complete-Install; return).
}

# `return` and not `exit`: under `irm | iex` this runs in the user's own
# session, so `exit` would close their window right after printing the help.
if ($Help) { Show-Usage; return }

function Confirm-Step([string]$Question) {
    if ($InstallDeps) { return $true }
    if ($Yes) { return $false }  # conservative: -Yes alone never installs system deps
    if (-not [Environment]::UserInteractive) { return $false }
    $answer = Read-Host "  ? $Question [y/N]"
    return $answer -match '^(y|yes|s)$'
}

# -- Manifest: what THIS script installed on the Windows side ----------------
# Same contract as install.sh: created | preexisting, `created` is never
# downgraded, and an absent key reads as preexisting - so -Uninstall can only
# remove what it can prove it installed.
# LOCALAPPDATA is NOT guaranteed: it is unset in non-interactive spawns (proved
# on the test VM, where Join-Path threw and, with ErrorActionPreference=Stop,
# killed the installer before it did anything). Bookkeeping must never do that.
$AfStateBase = $env:LOCALAPPDATA
if (-not $AfStateBase -and $env:USERPROFILE) { $AfStateBase = Join-Path $env:USERPROFILE "AppData\Local" }
if (-not $AfStateBase) { $AfStateBase = $env:TEMP }
if (-not $AfStateBase) { $AfStateBase = "." }
$AfStateDir = Join-Path $AfStateBase "AtlasFile"
$AfManifest = Join-Path $AfStateDir "host-prereqs"

function Get-AfState([string]$Key) {
    if (-not (Test-Path $AfManifest)) { return "" }
    foreach ($line in (Get-Content $AfManifest -ErrorAction SilentlyContinue)) {
        $parts = $line -split "`t", 2
        if ($parts.Count -eq 2 -and $parts[0] -eq $Key) { return $parts[1] }
    }
    return ""
}

function Set-AfState([string]$Key, [string]$Value) {
    try {
        if ((Get-AfState $Key) -eq "created") { return }
        if (-not (Test-Path $AfStateDir)) { New-Item -ItemType Directory -Path $AfStateDir -Force | Out-Null }
        $kept = @()
        if (Test-Path $AfManifest) {
            $kept = Get-Content $AfManifest | Where-Object { ($_ -split "`t", 2)[0] -ne $Key }
        } else {
            $kept = @("# AtlasFile manifest - key<TAB>value. Consumed by install.ps1 -Uninstall.", "schema`t1")
        }
        ($kept + "$Key`t$Value") | Set-Content -Path $AfManifest -Encoding UTF8
    } catch {
        # Bookkeeping must never break an install: the failure is recorded for
        # -Verbose and swallowed on purpose.
        Write-Verbose "manifest write failed for '$Key': $($_.Exception.Message)"
    }
}

# PATH is inherited when this process starts, so anything installed DURING this
# run (Docker Desktop, Ollama) is invisible to it until refreshed. Measured on a
# clean Windows 11 VM: right after winget reported "Successfully installed", the
# next line `docker info` died with "The term 'docker' is not recognized" and,
# under ErrorActionPreference=Stop, killed the whole installer.
function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $extra = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin"),
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama")
    ) | Where-Object { $_ -and (Test-Path $_) }
    # ACRESCENTA, nunca substitui: o PATH desta sessao vem primeiro. Trocar o
    # PATH inteiro por Machine+User descartaria o que o usuario tivesse na
    # propria sessao pelo resto da instalacao. Medido no runner do CI, onde essa
    # troca fazia o instalador passar a enxergar um docker diferente no meio do
    # fluxo.
    $parts = @($env:Path) + @($machine, $user) + $extra |
        Where-Object { $_ } |
        ForEach-Object { $_.TrimEnd(';') }
    $seen = @{}
    $ordered = foreach ($p in ($parts -join ';') -split ';') {
        if ($p -and -not $seen.ContainsKey($p)) { $seen[$p] = $true; $p }
    }
    $env:Path = $ordered -join ';'
}

# Comando nativo NUNCA pode derrubar o instalador.
# Native tools write warnings to stderr as a matter of course - winget does it
# for every source it cannot reach - and under ErrorActionPreference=Stop
# PowerShell turns that stderr into a TERMINATING NativeCommandError. Measured
# on a real Windows 11: answering "y" to the Docker question printed
# "Failed when searching source: msstore" and the whole installer died there,
# closing the window before the user could read anything.
# Returns the exit code and never throws; output keeps flowing to the console.
# Os argumentos vem SEMPRE como array explicito na posicao 1. Com
# ValueFromRemainingArguments o PowerShell ainda oferece cada argumento iniciado
# por `-` aos parametros da FUNCAO, e `-e` (do winget) e ambiguo com
# -ErrorAction/-ErrorVariable: "O parametro nao pode ser processado porque o nome
# de parametro 'e' e ambiguo" - medido num Windows 11 real.
# Padrao do OpenClaw (Invoke-InteractiveOpenClawCommand): Start-Process com
# -NoNewWindow -Wait -PassThru. O processo herda o console, entao qualquer barra
# de progresso renderiza normal; o codigo vem de $process.ExitCode, sem pipeline
# e portanto sem a saida do comando poluindo o retorno - que foi exatamente o bug
# que fazia o instalador declarar falha com o winget saindo 0.
function Invoke-Native {
    param(
        [Parameter(Mandatory, Position = 0)][string]$File,
        [Parameter(Position = 1)][string[]]$Arguments = @()
    )
    $caminho = Resolve-ToolPath $File
    if (-not $caminho) { $script:NativeExitCode = 9009; return }
    # ASPAS SAO NOSSAS. O -ArgumentList do Start-Process junta os elementos do
    # array com espaco e NAO cita nenhum deles, entao um argumento com espacos
    # chega ao programa partido em varios. Medido na maquina do usuario: o
    # `wsl -e bash -c "curl -fsSL <url> | bash -s -- --no-open"` virou
    # `bash -c curl` com o resto solto, o curl rodou sem argumento algum e a
    # instalacao morreu em "curl: try 'curl --help'".
    $citados = @($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    })
    try {
        $proc = Start-Process -FilePath $caminho -ArgumentList $citados -NoNewWindow -Wait -PassThru
        $script:NativeExitCode = $proc.ExitCode
    } catch {
        Write-Warn "$File : $($_.Exception.Message)"
        $script:NativeExitCode = 1
    }
}

# A mesma URL em tres lugares (plano, execucao e instalacao) vira uma constante:
# tres literais divergem no dia em que um deles for editado sozinho.
$AF_SH_URL = "https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh"
# --proto '=https' --tlsv1.2 e retry: mesma dureza do mac-env-setup. Um curl sem
# retry transforma um soluco de rede em instalacao pela metade.
$AF_CURL = "curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --retry-delay 1 --retry-connrefused"

# O manifesto do Windows traduzido para o vocabulario do plano do outro lado.
# Sem isto o install.sh so conhecia a distro, e o plano que o usuario confirmava
# nao dizia uma palavra sobre o Docker Desktop e o Ollama que este script
# instalou - mas que ele removia logo depois.
function Get-AfHostExtra {
    $pares = @()
    foreach ($chave in @("docker", "ollama", "wsl", "wsl_distro")) {
        $valor = Get-AfState $chave
        if (-not $valor) { continue }
        # wsl_distro guarda o NOME da distro (para o -Doctor); no plano o que
        # importa e a procedencia, e o vocabulario la e created/preexisting.
        if ($chave -eq "wsl_distro") { $pares += "wsl_distro=created"; continue }
        $pares += "$chave=$valor"
    }
    return ($pares -join ",")
}

# QUEM e o dono da instalacao do outro lado da fronteira.
#
# $script:WslUser so era decidido na FASE 1, que roda DEPOIS dos blocos
# -Uninstall/-Doctor/-DryRun. Nesses caminhos ele estava sempre vazio, entao o
# `wsl -e` rodava como usuario PADRAO da distro. Quando a instalacao tinha sido
# feita como root - que e exatamente o que acontece quando o proprio AtlasFile
# instala o WSL com --no-launch - tudo morava em /root/AtlasFile e
# /root/.atlasfile, e a desinstalacao olhava para outro $HOME: nao achava
# instalacao, nao achava manifesto, e NADA era revertido. Funcionava por sorte
# em distro cujo usuario padrao ainda e root; bastava completar o assistente de
# conta do Ubuntu para quebrar.
$script:AfDir = ""
function Restore-AfInstallIdentity {
    if ((Get-AfState "wsl_user") -eq "root") { $script:WslUser = @("-u", "root") }
    $script:AfDir = $Dir
    if (-not $script:AfDir) { $script:AfDir = Get-AfState "install_dir" }
}

# Comando nativo com a saida CAPTURADA, e nao apenas escondida no log: o
# orquestrador precisa LER o plano do outro lado e a linha-sentinela antes de
# encostar em qualquer pacote do Windows. Mesmo contrato do Invoke-Native
# (nunca lanca, codigo em $script:NativeExitCode) e as aspas continuam sendo
# nossas. So para comando NAO interativo.
function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory, Position = 0)][string]$File,
        [Parameter(Position = 1)][string[]]$Arguments = @()
    )
    $caminho = Resolve-ToolPath $File
    if (-not $caminho) { $script:NativeExitCode = 9009; return "" }
    $citados = @($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    })
    $fOut = [IO.Path]::GetTempFileName()
    $fErr = [IO.Path]::GetTempFileName()
    $texto = ""
    try {
        $proc = Start-Process -FilePath $caminho -ArgumentList $citados -NoNewWindow -PassThru `
            -RedirectStandardOutput $fOut -RedirectStandardError $fErr
        # Tocar no Handle ANTES de o processo morrer, senao o ExitCode se perde.
        $null = $proc.Handle
        $proc.WaitForExit()
        $script:NativeExitCode = $proc.ExitCode
        if ($null -eq $script:NativeExitCode) { $script:NativeExitCode = 1 }
    } catch {
        $script:NativeExitCode = 1
        Write-Verbose "$File : $($_.Exception.Message)"
    }
    foreach ($f in @($fOut, $fErr)) {
        if (Test-Path $f) {
            # wsl.exe emite UTF-16: sem tirar os NULs todo -match falha calado.
            $texto += (((Get-Content $f -Raw -ErrorAction SilentlyContinue) -replace "`0", "") + "`n")
        }
    }
    Write-LogSection ("$File " + ($Arguments -join " ")) @($fOut, $fErr)
    Remove-Item $fOut, $fErr -Force -ErrorAction SilentlyContinue
    return $texto
}

# Confirmacao de um plano DESTRUTIVO. Diferente do Confirm-Step: ali -Yes
# significa "nao instale software de sistema por conta propria"; aqui -Yes e a
# resposta do usuario a uma pergunta que ele mesmo pediu ao passar -Uninstall.
function Confirm-Plan([string]$Pergunta) {
    if ($Yes) { return $true }
    if (-not [Environment]::UserInteractive) { return $false }
    $resposta = Read-Host "  ? $Pergunta [y/N]"
    return $resposta -match '^(y|yes|s)$'
}

# Sondagem do WSL com TETO DE TEMPO. Provar que a distro executa exige inicia-la,
# e numa maquina fria isso pode levar MINUTOS - bloquear a instalacao nisso e
# inaceitavel (relatado num teste real, onde o usuario cancelou). Aqui a sonda
# tem prazo; estourou, o instalador SEGUE e diz por que.
# Devolve: "ok" | "falhou" | "lento"
function Invoke-WslProbe([string[]]$Prefixo) {
    $limite = 20000
    if ($env:ATLASFILE_WSL_PROBE_MS) { $limite = [int]$env:ATLASFILE_WSL_PROBE_MS }
    $saida = [IO.Path]::GetTempFileName()
    try {
        $lista = @($Prefixo) + @("-e", "echo", "atlasfile_wsl_ok")
        $proc = Start-Process -FilePath "wsl" -ArgumentList $lista -NoNewWindow -PassThru `
            -RedirectStandardOutput $saida -RedirectStandardError ([IO.Path]::GetTempFileName())
        if (-not $proc.WaitForExit($limite)) {
            # Arvore inteira: matar so o processo direto deixa filhos vivos
            # segurando a saida redirecionada, e a espera continua na pratica
            # (medido na bancada: 31s com teto de 2s).
            try { & taskkill /PID $proc.Id /T /F *> $null }
            catch { Write-Verbose "taskkill falhou: $($_.Exception.Message)" }
            try { if (-not $proc.HasExited) { $proc.Kill() } }
            catch { Write-Verbose "kill falhou: $($_.Exception.Message)" }
            return "lento"
        }
        $texto = (Get-Content $saida -Raw -ErrorAction SilentlyContinue) -replace "`0", ""
        if ($texto -match "atlasfile_wsl_ok") { return "ok" }
        return "falhou"
    } catch {
        return "falhou"
    } finally {
        Remove-Item $saida -Force -ErrorAction SilentlyContinue
    }
}

# Descoberta de ferramenta com override SO PARA TESTE, mesmo padrao de
# DOCKER_APP_PATH/TTY_DEV no install.sh. Necessario porque nao da para simular
# ausencia por PATH numa maquina onde a ferramenta existe em System32 - medido
# no runner do CI, que traz docker.exe em C:\Windows\System32 e obriga o
# System32 a estar no PATH (e de la que vem o cmd.exe).
# Resolucao no padrao do OpenClaw (Resolve-CommandPath): devolve o CAMINHO
# COMPLETO e tenta os sufixos de executavel, em vez de depender do nome nu. Com
# o caminho resolvido a invocacao vira `& $path @args`, o que elimina de uma vez
# a extensao explicita e a ambiguidade de parametro.
# O override ATLASFILE_FAKE_MISSING existe SO PARA TESTE (mesmo espirito de
# TTY_DEV/DOCKER_APP_PATH no install.sh): nao da para simular ausencia por PATH
# numa maquina onde a ferramenta mora em System32.
function Resolve-ToolPath([string]$Name) {
    if ($env:ATLASFILE_FAKE_MISSING) {
        $faltando = $env:ATLASFILE_FAKE_MISSING -split ',' | ForEach-Object { $_.Trim() }
        if ($faltando -contains $Name) { return $null }
    }
    # Nome NU primeiro: e assim que o Windows resolve quando o usuario digita o
    # comando - a ordem do PATH manda, e o PATHEXT so decide dentro de cada
    # diretorio. Comecar por "$Name.exe" (como faz o OpenClaw, onde faz sentido
    # porque npm e um shim .cmd) inverte isso: um wsl.exe do System32 passa na
    # frente de algo que esta ANTES no PATH. Medido no CI.
    foreach ($candidato in @($Name, "$Name.exe", "$Name.cmd", "$Name.bat")) {
        $c = Get-Command $candidato -ErrorAction SilentlyContinue
        if ($c -and $c.Source) { return $c.Source }
    }
    return $null
}

function Get-Tool([string]$Name) { return (Resolve-ToolPath $Name) }


# Never lets a missing native command become a terminating error.
function Test-DockerDaemon {
    if (-not (Get-Tool docker)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $caminho = Resolve-ToolPath docker
    try { & $caminho info *> $null; $ok = ($LASTEXITCODE -eq 0) } catch { $ok = $false }
    $ErrorActionPreference = $prev
    return $ok
}

# Pronto = o servico responde; ter o binario nao prova nada. O `ollama list`
# conversa com o daemon em 127.0.0.1:11434, que e exatamente quem recusava a
# conexao logo apos a instalacao.
function Test-OllamaReady {
    $caminho = Resolve-ToolPath ollama
    if (-not $caminho) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $caminho list *> $null; $ok = ($LASTEXITCODE -eq 0) } catch { $ok = $false }
    $ErrorActionPreference = $prev
    return $ok
}

# Docker alcancavel de DENTRO da distro. Definida aqui, junto das outras sondas,
# e nao la embaixo perto de quem a usa na instalacao: o -Doctor tambem a chama, e
# no PowerShell uma funcao so existe depois que a linha que a declara ROda. O CI
# mostrou o resultado - o diagnostico morria calado no meio da secao do Docker.
function Test-DockerInWsl {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $alcancavel = $false
    # Splat de array (@nome) e nao expressao (@(...)): a expressao com array
    # vazio chega ao comando como ARGUMENTO VAZIO, e o wsl passa a receber "" no
    # lugar de nada.
    $argsWslDocker = @($script:WslUser) + @("-e", "sh", "-c", "docker info")
    $caminhoWsl = Resolve-ToolPath wsl
    try { & $caminhoWsl @argsWslDocker *> $null; $alcancavel = ($LASTEXITCODE -eq 0) } catch { $alcancavel = $false }
    $ErrorActionPreference = $prev
    return $alcancavel
}

# -- Banner: the orb, its two moons and the comet it fires (no face) ---------
# Same art, palette and moon rest positions as install.sh. Truecolor is used
# only when the host announces it (Windows Terminal sets WT_SESSION and
# supports VT); otherwise this falls back to the classic console colors, and
# with NO_COLOR nothing is emitted at all. The animation itself lives in
# install.sh: this banner is printed once, and seconds later the WSL side
# prints the animated one - two moving banners in a row would be noise.
# O console CLASSICO do Windows (conhost) entende VT desde o Windows 10 1511,
# mas so quando o bit ENABLE_VIRTUAL_TERMINAL_PROCESSING esta ligado - e ninguem
# o liga por voce. Detectar truecolor apenas por WT_SESSION reprovava quem roda
# na janela normal do PowerShell (o caso do usuario: prompt em
# C:\WINDOWS\system32), que via o banner estatico sem que nada estivesse errado
# na maquina dele. Aqui a capacidade e HABILITADA e o resultado dessa tentativa
# e que decide, em vez de adivinhar pelo nome do terminal.
function Enable-VtMode {
    if ($env:NO_COLOR) { return $false }
    if ($null -ne $env:WT_SESSION -or $env:COLORTERM -in @("truecolor", "24bit")) { return $true }
    # Redirecionado nao ha console para configurar. A excecao e a bancada, que
    # precisa EXECUTAR este caminho: Add-Type compila C# em tempo de execucao e
    # uma falha ali (politica, .NET podado) so apareceria na maquina do usuario.
    if ([Console]::IsOutputRedirected -and $env:ATLASFILE_FORCE_ANIM -ne "1") { return $false }
    try {
        if (-not ("AtlasFileVt" -as [type])) {
            Add-Type -Name AtlasFileVt -Namespace "" -MemberDefinition @"
[DllImport("kernel32.dll", SetLastError = true)] public static extern IntPtr GetStdHandle(int nStdHandle);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
"@
        }
        $handle = [AtlasFileVt]::GetStdHandle(-11)   # STD_OUTPUT_HANDLE
        $modo = 0
        if (-not [AtlasFileVt]::GetConsoleMode($handle, [ref]$modo)) { return $false }
        return [AtlasFileVt]::SetConsoleMode($handle, $modo -bor 0x0004)
    } catch {
        # Politica de terminal, .NET podado, console sem handle: qualquer um
        # deles significa apenas "sem VT", nunca instalacao interrompida.
        Write-Verbose "VT not enabled: $($_.Exception.Message)"
        return $false
    }
}
$AfTrueColor = Enable-VtMode
$AfPlain = [bool]$env:NO_COLOR
# Animar (banner e spinner) exige console de verdade. Com a saida redirecionada
# - bancada, CI, `| Tee-Object` - cada quadro viraria uma linha no arquivo: o
# mesmo picotado que a barra do winget produzia na tela do usuario. Espelha o
# IS_TTY/ANIM_OK do install.sh.
# ATLASFILE_FORCE_ANIM existe porque o caminho animado seria INTESTAVEL de outro
# jeito: redirecionado, a bancada nunca o executaria, e um erro de indice ou de
# escape so apareceria na maquina do usuario. Intestavel nao e caracteristica,
# e divida.
$script:AfAnim = ($env:ATLASFILE_FORCE_ANIM -eq "1") -or
                 ((-not [Console]::IsOutputRedirected) -and (-not $env:CI))

# Write-AfLine saiu daqui: ela existia para o banner estatico escrito a mao, e o
# banner estatico agora e o quadro final da animacao. A degradacao de cor que ela
# fazia (truecolor / cor de console / sem cor) vive no Write-AfGrid, que e por
# onde os dois caminhos passam.

# O banner estatico E o quadro final da propria animacao, exatamente como no
# install.sh (que usa `af_frame_paint "$AF_LAST"` nos dois caminhos). Antes isto
# era arte escrita a mao: luas em posicoes que a animacao nunca produz e uma
# terceira linha de texto que o outro instalador nao tem. Duas artes para o
# mesmo produto e o defeito; uma funcao de composicao so e a correcao.
function Show-BannerStatic {
    Write-Host ""
    $total = $AF_IGNITE + $AF_ORBIT_FRAMES + $AF_COMET.Count + 1
    Write-AfGrid (New-AfFrame ($total - 1) $total)
    Write-Host ""
}

# --- Banner animado: mesma coreografia do install.sh -------------------------
# Tabelas identicas as do bash (AF_ORBIT / AF_COMET), porque a arte, as posicoes
# de repouso e o quadro final tem que ser OS MESMOS nos dois instaladores - quem
# instala no Windows ve este banner e, na fase 4, ve o do install.sh dentro do
# WSL. Duas coreografias diferentes seriam duas identidades.
# Aqui e mais simples que no bash: o PowerShell tem array de verdade e ponto
# flutuante, entao a rampa nao precisa da aritmetica inteira em milesimos.
$AF_ROWS = 7
$AF_COLS = 60
$AF_ORBIT = @(@(3, 19), @(4, 18), @(5, 16), @(6, 13), @(6, 10), @(6, 7), @(5, 4), @(4, 2),
              @(3, 1), @(2, 2), @(1, 4), @(0, 7), @(0, 10), @(0, 13), @(1, 16), @(2, 18))
# O cometa sai do orbe e SOBE: ao alcancar a coluna do wordmark (24) ja esta nas
# linhas 0-1, acima do texto. Um trajeto cruzando as linhas de texto corrompia
# as letras - medido no install.sh, onde virou "y.ur .ocs".
$AF_COMET = @(@(4, 17), @(3, 20), @(2, 22), @(1, 25), @(1, 31), @(0, 38), @(0, 46), @(0, 54))
$AF_RAMP = @("592013", "ff5a36", "ff8a6b", "ffd0c4")
$AF_IGNITE = 5
$AF_ORBIT_FRAMES = 12
# 10, o MESMO do install.sh (AF_ORBIT_START). Com 2 as duas luas trocavam de
# lugar em relacao ao bash - as posicoes eram as mesmas, mas a laranja aparecia
# onde a roxa devia estar. Medido: (10 + AF_LAST - AF_IGNITE) % 16 = 14, que e
# exatamente o indice de repouso abaixo.
$AF_ORBIT_START = 10
$AF_ORBIT_REST = 14
$AF_DELAY_MS = 45

function Get-AfRampHex([double]$Pos) {
    if ($Pos -lt 0) { $Pos = 0 }
    if ($Pos -gt 1) { $Pos = 1 }
    $span = $AF_RAMP.Count - 1
    $seg = [Math]::Min([int]($Pos * $span), $span - 1)
    $frac = ($Pos * $span) - $seg
    $a = $AF_RAMP[$seg]; $b = $AF_RAMP[$seg + 1]
    $out = ""
    foreach ($i in 0, 2, 4) {
        $ca = [Convert]::ToInt32($a.Substring($i, 2), 16)
        $cb = [Convert]::ToInt32($b.Substring($i, 2), 16)
        $out += "{0:x2}" -f [int]($ca + ($cb - $ca) * $frac)
    }
    return $out
}

function New-AfGrid {
    $glifos = New-Object 'string[,]' $AF_ROWS, $AF_COLS
    $cores = New-Object 'string[,]' $AF_ROWS, $AF_COLS
    for ($r = 0; $r -lt $AF_ROWS; $r++) {
        for ($c = 0; $c -lt $AF_COLS; $c++) { $glifos[$r, $c] = " "; $cores[$r, $c] = "" }
    }
    return @{ G = $glifos; C = $cores }
}

function Set-AfText($Grid, [int]$Row, [int]$Col, [string]$Texto, [string]$Hex, [int]$RevealTo = 999) {
    for ($i = 0; $i -lt $Texto.Length; $i++) {
        $c = $Col + $i
        if ($c -ge $AF_COLS -or $c -gt $RevealTo) { break }
        $Grid.G[$Row, $c] = [string]$Texto[$i]
        $Grid.C[$Row, $c] = $Hex
    }
}

# Degrada em TRES niveis, porque este mesmo desenho serve ao caminho animado E
# ao banner estatico - e o estatico existe justamente para quem NAO tem
# truecolor. Emitir escape de 24 bits ali encheria a tela de lixo.
function Write-AfGrid($Grid) {
    $esc = [char]27
    for ($r = 0; $r -lt $AF_ROWS; $r++) {
        $linha = ""
        $corAtual = $null
        $ultimo = 0
        for ($c = 0; $c -lt $AF_COLS; $c++) { if ($Grid.G[$r, $c] -ne " ") { $ultimo = $c } }
        if (-not $AfTrueColor) {
            for ($c = 0; $c -le $ultimo; $c++) { $linha += $Grid.G[$r, $c] }
            if ($AfPlain) { Write-Host $linha } else { Write-Host $linha -ForegroundColor DarkYellow }
            continue
        }
        for ($c = 0; $c -le $ultimo; $c++) {
            $cor = $Grid.C[$r, $c]
            if ($cor -ne $corAtual) {
                if ($cor) {
                    $rr = [Convert]::ToInt32($cor.Substring(0, 2), 16)
                    $gg = [Convert]::ToInt32($cor.Substring(2, 2), 16)
                    $bb = [Convert]::ToInt32($cor.Substring(4, 2), 16)
                    $linha += "$esc[38;2;$rr;$gg;${bb}m"
                } else { $linha += "$esc[0m" }
                $corAtual = $cor
            }
            $linha += $Grid.G[$r, $c]
        }
        Write-Host ($linha + "$esc[0m")
    }
}

# Um quadro: orbe com brilho especular varrendo, duas luas em oposicao, cometa
# com cauda e o texto revelado pela passagem dele.
function New-AfFrame([int]$N, [int]$Total) {
    $grid = New-AfGrid
    # brilho especular: um ponto varre a esfera numa onda triangular, e cada
    # celula escurece conforme a distancia ate ele. Uma rampa horizontal fixa
    # deixava a esfera chapada.
    $tri = $N % 20; if ($tri -gt 10) { $tri = 20 - $tri }
    $hlCol = 5 + $tri
    $arte = @(
        @{ Row = 1; Col = 8;  Glifos = (, $BLK_LO * 5) },
        @{ Row = 2; Col = 6;  Glifos = @($BLK_LO) + (, $BLK_FU * 7) + @($BLK_LO) },
        @{ Row = 3; Col = 5;  Glifos = @($BLK_RT) + (, $BLK_FU * 9) + @($BLK_LF) },
        @{ Row = 4; Col = 6;  Glifos = @($BLK_UP) + (, $BLK_FU * 7) + @($BLK_UP) },
        @{ Row = 5; Col = 8;  Glifos = (, $BLK_UP * 5) }
    )
    # ignicao: o orbe ocupa as linhas 1..5 e nasce de dentro para fora
    $revelaAte = if ($N -lt $AF_IGNITE) { $N + 2 } else { $AF_ROWS }
    foreach ($a in $arte) {
        if ($a.Row -gt $revelaAte) { continue }
        for ($i = 0; $i -lt $a.Glifos.Count; $i++) {
            $col = $a.Col + $i
            $dist = [Math]::Abs($col - $hlCol) + [Math]::Abs($a.Row - 3)
            $pos = 1.0 - [Math]::Min($dist / 11.0, 1.0)
            $grid.G[$a.Row, $col] = $a.Glifos[$i]
            $grid.C[$a.Row, $col] = Get-AfRampHex $pos
        }
    }
    # luas: em oposicao na mesma tabela de 16 celulas
    $idx = $AF_ORBIT_REST
    if ($N -ge $AF_IGNITE -and $N -lt ($AF_IGNITE + $AF_ORBIT_FRAMES)) {
        $idx = ($AF_ORBIT_START + ($N - $AF_IGNITE)) % 16
    }
    if ($N -ge $AF_IGNITE) {
        # Glifo pela LINHA (a lua do lado de tras e menor e mais escura) e cor
        # POR LUA - a regra do install.sh (af_row_cells). Antes o glifo e a cor
        # eram fixos por indice de lua, o que dava profundidade invertida em
        # metade da orbita.
        $m1 = $AF_ORBIT[$idx]
        $m2 = $AF_ORBIT[($idx + 8) % 16]
        if ($m1[0] -le 2) { $g1 = $MOON_FAR;  $c1 = "b23f26" } else { $g1 = $MOON_NEAR; $c1 = "ff5a36" }
        if ($m2[0] -le 2) { $g2 = $MOON_FAR;  $c2 = "8d56b2" } else { $g2 = $MOON_NEAR; $c2 = "c97bff" }
        $grid.G[$m1[0], $m1[1]] = $g1; $grid.C[$m1[0], $m1[1]] = $c1
        $grid.G[$m2[0], $m2[1]] = $g2; $grid.C[$m2[0], $m2[1]] = $c2
    }
    # cometa e o texto que ele revela
    $primeiroCometa = $AF_IGNITE + $AF_ORBIT_FRAMES
    $revelaCol = -1
    # O QUADRO FINAL NAO TEM COMETA. No install.sh isso e regra
    # (af_frame_prepare so emite cometa enquanto n < AF_LAST) e ha teste para
    # isso; aqui o laco continuava pintando tres celulas de cauda na linha 0, e
    # eram exatamente as tres reticencias que sobravam no topo do banner.
    if ($N -ge $primeiroCometa -and $N -lt ($primeiroCometa + $AF_COMET.Count)) {
        $j = $N - $primeiroCometa
        $caudaHex = @("ffd0c4", "ff8a6b", "ff5a36", "b23f26")
        for ($t = 0; $t -lt 4; $t++) {
            $k = $j - $t
            if ($k -lt 0 -or $k -ge $AF_COMET.Count) { continue }
            $cel = $AF_COMET[$k]
            $grid.G[$cel[0], $cel[1]] = if ($t -eq 0) { $MOON_NEAR } else { $DOT }
            $grid.C[$cel[0], $cel[1]] = $caudaHex[$t]
        }
        $ultimo = [Math]::Min($j, $AF_COMET.Count - 1)
        $revelaCol = $AF_COMET[$ultimo][1]
    }
    if ($N -eq $Total - 1) { $revelaCol = $AF_COLS }
    if ($revelaCol -ge 0) {
        Set-AfText $grid 2 24 "AtlasFile" "ff5a36" $revelaCol
        Set-AfText $grid 3 24 "Your documents have gravity." "8a8a8a" $revelaCol
        Set-AfText $grid 4 23 "(Windows / WSL2)" "8a8a8a" $revelaCol
    }
    return $grid
}

# Animar exige console de verdade E truecolor. Sem os dois, o banner estatico -
# que e exatamente o quadro final desta animacao.
if ($script:AfAnim -and $AfTrueColor) {
    $esc = [char]27
    $total = $AF_IGNITE + $AF_ORBIT_FRAMES + $AF_COMET.Count + 1
    Write-Host ""
    Write-Host "$esc[?25l" -NoNewline
    try {
        for ($n = 0; $n -lt $total; $n++) {
            if ($n -gt 0) { Write-Host "$esc[${AF_ROWS}A" -NoNewline }
            Write-AfGrid (New-AfFrame $n $total)
            if ($n -lt $total - 1) { Start-Sleep -Milliseconds $AF_DELAY_MS }
        }
    } finally {
        # Ctrl-C no meio da animacao nao pode deixar o cursor invisivel na
        # sessao do usuario - o mesmo cuidado do trap no install.sh.
        Write-Host "$esc[?25h" -NoNewline
    }
    Write-Host ""
} else {
    Show-BannerStatic
}


# --- UI: mesma gramatica visual do install.sh (fases, passos, painel) -------
# A calha vertical, a regua de fase, a barra viva e o placar sao os MESMOS do
# install.sh, que por sua vez os tomou do mac_env_install.sh. Dois instaladores
# com duas gramaticas visuais foi um dos defeitos deste ciclo, nao uma escolha.
$script:PhaseTotal = 3
$script:StepStart = $null
$BOX_V   = [string][char]0x2502   # |
$BOX_H   = [string][char]0x2500   # -
$BOX_T   = [string][char]0x251C   # |-
$BAR_ON  = [string][char]0x25B0   # bloco cheio
$BAR_OFF = [string][char]0x25B1   # bloco vazio
$script:Gut = $BOX_V + " "

function Write-Gut([string]$Texto, [string]$Cor = "Gray", [switch]$NoNewline) {
    Write-Host $script:Gut -ForegroundColor DarkGray -NoNewline
    Write-Host $Texto -ForegroundColor $Cor -NoNewline:$NoNewline
}

# --- Barra de fase, viva na ultima linha ------------------------------------
# Espelha a do install.sh: contagem por FASE (o que e discreto e conhecido dos
# dois lados), apagada ANTES de qualquer mensagem. Esse `bar_clear` e tambem a
# unica coisa que impede o spinner de escrever por cima da saida de um
# desinstalador de terceiro - foi assim que o do Docker embaralhou a tela.
$script:BarDone = 0
$script:BarVisible = $false

function Show-AfBar {
    if (-not $script:AfAnim -or -not $AfTrueColor) { return }
    $largura = 24
    $cheio = [int]($script:BarDone * $largura / $script:PhaseTotal)
    $esc = [char]27
    $linha = ""
    for ($i = 0; $i -lt $largura; $i++) {
        if ($i -lt $cheio) {
            $hex = Get-AfRampHex ([double]$i / [Math]::Max(1, $largura - 1))
            $r = [Convert]::ToInt32($hex.Substring(0, 2), 16)
            $g = [Convert]::ToInt32($hex.Substring(2, 2), 16)
            $b = [Convert]::ToInt32($hex.Substring(4, 2), 16)
            $linha += "$esc[38;2;$r;$g;${b}m$BAR_ON"
        } else {
            $linha += "$esc[38;5;240m$BAR_OFF"
        }
    }
    Write-Host ("  " + $linha + "$esc[0m " + "fase $($script:BarDone)/$($script:PhaseTotal)") -NoNewline
    $script:BarVisible = $true
}

function Clear-AfBar {
    if ($script:BarVisible) {
        Write-Host ("`r" + (" " * 78) + "`r") -NoNewline
        $script:BarVisible = $false
    }
}

function Write-Phase([int]$Numero, [string]$Titulo) {
    Clear-AfBar
    Write-Host ""
    Write-Gut "" -NoNewline
    Write-Host ""
    $cabecalho = "[{0}/{1}] {2}" -f $Numero, $script:PhaseTotal, $Titulo
    Write-Rule $cabecalho
    $script:BarDone = $Numero
    Show-AfBar
}

# Regua que varre da esquerda para a direita com a rampa do produto. O conector
# tem largura FIXA e conhecida, entao entra na conta como constante - a mesma
# disciplina do install.sh, onde indexar string multibyte contaria bytes.
function Write-Rule([string]$Cabecalho) {
    $largura = 76
    # Host sem RawUI (sessao redirecionada, ISE, runspace) nao tem largura para
    # dar: a regua cai na largura padrao e a instalacao segue.
    try { if ($Host.UI.RawUI.WindowSize.Width -gt 40) { $largura = [Math]::Min(92, $Host.UI.RawUI.WindowSize.Width - 4) } }
    catch { Write-Verbose "console width unavailable: $($_.Exception.Message)" }
    $tracos = $largura - $Cabecalho.Length - 8
    if ($tracos -lt 4) { $tracos = 4 }
    Write-Host ($script:Gut + $BOX_T + ($BOX_H * 2) + " ") -ForegroundColor DarkGray -NoNewline
    Write-Host $Cabecalho -ForegroundColor White -NoNewline
    Write-Host (" " + ($BOX_H * $tracos)) -ForegroundColor DarkYellow
}

function Start-Step([string]$Texto) {
    $script:StepStart = Get-Date
    Clear-AfBar
    Write-Gut ("{0} {1}..." -f $DOT, $Texto) DarkGray
    Write-Host ""
}
function Format-Elapsed {
    if (-not $script:StepStart) { return "" }
    $s = [int]((Get-Date) - $script:StepStart).TotalSeconds
    $script:StepStart = $null
    if ($s -ge 60) { return (" ({0}m{1:d2}s)" -f [int]($s / 60), ($s % 60)) }
    return " (${s}s)"
}
function Write-Ok([string]$Texto)   { Clear-AfBar; Write-Gut ("{0} {1}{2}" -f $OK, $Texto, (Format-Elapsed)) Green; Write-Host ""; Show-AfBar }
function Write-Info([string]$Texto) { Clear-AfBar; Write-Gut ("{0} {1}" -f $DOT, $Texto) DarkGray; Write-Host ""; Show-AfBar }
function Write-Warn([string]$Texto) { Clear-AfBar; Write-Gut ("! {0}" -f $Texto) DarkYellow; Write-Host ""; Show-AfBar }
function Write-Fail([string]$Texto) { Clear-AfBar; Write-Gut ("{0} {1}" -f $BAD, $Texto) Red; Write-Host "" }
function Write-Panel([string[]]$Linhas) {
    Write-Host ""
    Write-Host ("  " + [char]0x256D + ([string][char]0x2500) * 57 + [char]0x256E) -ForegroundColor DarkYellow
    foreach ($l in $Linhas) {
        Write-Host ("  " + [char]0x2502) -ForegroundColor DarkYellow -NoNewline
        Write-Host ("  " + $l.PadRight(55)) -NoNewline
        Write-Host ([char]0x2502) -ForegroundColor DarkYellow
    }
    Write-Host ("  " + [char]0x2570 + ([string][char]0x2500) * 57 + [char]0x256F) -ForegroundColor DarkYellow
    Write-Host ""
}

# --- Saida nossa aparece; saida de terceiro vai para o log -------------------
# E a regra do benchmark. No mac_env_install.sh:656 o comando roda como
#   run_with_spinner "$title" bash -c "<cmd> > <log> 2>&1"
# e no nosso install.sh o run_step faz `"$@" >>"$LOG_FILE" 2>&1` com spinner
# braille e tempo decorrido. Sem essa regra o console vira colcha de retalhos:
# dism no idioma do Windows, winget em ingles, tres estilos de barra de
# progresso e o nosso vocabulario no meio - foi o que o usuario viu.
# ATLASFILE_LOG existe para a bancada poder LER o que foi escondido da tela - sem
# isso a regra "terceiro vai para o log" seria inverificavel - e serve de escape
# para suporte, quando o TEMP do usuario nao e o lugar mais pratico.
$script:AfLog = if ($env:ATLASFILE_LOG) { $env:ATLASFILE_LOG }
                else { Join-Path ([IO.Path]::GetTempPath()) "atlasfile-install.log" }
# Placar e relatorio da execucao, como no install.sh: o log guarda a saida das
# FERRAMENTAS, e o que o instalador fez nao ficava em lugar nenhum.
$script:StepsDone = 0
$script:StepsFailed = 0
$script:RunSteps = @()
$script:RunStart = Get-Date
# Mesmos quadros braille do install.sh, por code point (o arquivo e ASCII puro).
$AF_SPIN = @(0x280B, 0x2819, 0x2839, 0x2838, 0x283C, 0x2834, 0x2826, 0x2827, 0x2807, 0x280F) |
    ForEach-Object { [string][char]$_ }
# Animar so quando ha console de verdade. Com a saida redirecionada (bancada, CI,
# `| Tee-Object`) cada quadro viraria uma linha no arquivo - o mesmo picotado que
# a barra do winget produzia. Espelha o IS_TTY do install.sh.

function Format-Since($T0) {
    $s = [int]((Get-Date) - $T0).TotalSeconds
    if ($s -ge 60) { return ("{0}m{1:d2}s" -f [int]($s / 60), ($s % 60)) }
    return "${s}s"
}

function Write-LogSection([string]$Titulo, [string[]]$Arquivos) {
    try {
        Add-Content -Path $script:AfLog -Value ("=== " + $Titulo + " ===") -ErrorAction Stop
        foreach ($f in $Arquivos) {
            if (Test-Path $f) {
                $texto = (Get-Content $f -Raw -ErrorAction SilentlyContinue) -replace "`0", ""
                if ($texto) { Add-Content -Path $script:AfLog -Value $texto }
            }
        }
    } catch {
        Write-Verbose "log write failed: $($_.Exception.Message)"
    }
}

# Ultimas linhas do log quando algo falha: sem isto, esconder a saida de terceiro
# transformaria uma falha em misterio. E o fail_with_log do install.sh.
function Show-LogTail([int]$Linhas = 15) {
    if (-not (Test-Path $script:AfLog)) { return }
    Write-Host "    last lines of $script:AfLog" -ForegroundColor DarkGray
    foreach ($l in (Get-Content $script:AfLog -Tail $Linhas -ErrorAction SilentlyContinue)) {
        Write-Host ("    | " + $l) -ForegroundColor DarkGray
    }
}

# Comando nativo com spinner: a saida vai para o log, a tela mostra so o rotulo,
# o tempo correndo e o resultado. Mesmo contrato do Invoke-Native (nunca lanca,
# codigo em $script:NativeExitCode) - e as aspas continuam sendo nossas.
# So para comando NAO interativo: stdin nao e repassado, entao um comando que
# pergunte algo ficaria pendurado sem a pergunta aparecer.
function Invoke-Step {
    param(
        [Parameter(Mandatory, Position = 0)][string]$Label,
        [Parameter(Mandatory, Position = 1)][string]$File,
        [Parameter(Position = 2)][string[]]$Arguments = @()
    )
    $caminho = Resolve-ToolPath $File
    if (-not $caminho) {
        $script:NativeExitCode = 9009
        Write-Fail "$Label - $File not found"
        return
    }
    $citados = @($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    })
    # Start-Process exige arquivos DIFERENTES para stdout e stderr.
    # -Verbose devolve a saida para a tela: o Invoke-Native herda o console, o
    # comando desenha a propria barra de progresso e nada e escondido.
    if ($script:AfVerbose) {
        Clear-AfBar
        Write-Gut ("{0} {1}..." -f $DOT, $Label) DarkGray; Write-Host ""
        $tv = Get-Date
        Invoke-Native $File $Arguments
        if ($script:NativeExitCode -eq 0) {
            Write-Gut ("{0} {1} ({2})" -f $OK, $Label, (Format-Since $tv)) Green
            $script:StepsDone++
        } else {
            Write-Gut ("{0} {1} (exit {2})" -f $BAD, $Label, $script:NativeExitCode) Red
            $script:StepsFailed++
        }
        Write-Host ""
        return
    }
    $fOut = [IO.Path]::GetTempFileName()
    $fErr = [IO.Path]::GetTempFileName()
    $t0 = Get-Date
    if (-not $script:AfAnim) { Write-Host ("  {0} {1}..." -f $DOT, $Label) -ForegroundColor DarkGray }
    try {
        $proc = Start-Process -FilePath $caminho -ArgumentList $citados -NoNewWindow -PassThru `
            -RedirectStandardOutput $fOut -RedirectStandardError $fErr
        # Tocar no Handle ANTES de o processo terminar. Sem isto o Start-Process
        # -PassThru sem -Wait devolve ExitCode NULO: o handle e fechado quando o
        # processo morre e o codigo se perde. Medido no CI - o instalador
        # declarou "(exit )" e tratou como falha nove passos que tinham dado
        # certo, inclusive o wsl --install.
        $null = $proc.Handle
        $i = 0
        while (-not $proc.HasExited) {
            if ($script:AfAnim) {
                Write-Host ("`r" + $script:Gut) -ForegroundColor DarkGray -NoNewline
                Write-Host ($AF_SPIN[$i % $AF_SPIN.Count]) -ForegroundColor DarkYellow -NoNewline
                Write-Host (" {0} {1}   " -f $Label, (Format-Since $t0)) -ForegroundColor DarkGray -NoNewline
                $i++
            }
            Start-Sleep -Milliseconds 120
        }
        $proc.WaitForExit()
        $script:NativeExitCode = $proc.ExitCode
        # Codigo ausente e ANOMALIA, nao sucesso: tratar nulo como 0 esconderia
        # uma falha real, e foi por um nulo lido como falha que nove passos bons
        # foram declarados quebrados.
        if ($null -eq $script:NativeExitCode) {
            $script:NativeExitCode = 1
            Write-Verbose "$File returned no exit code"
        }
    } catch {
        $script:NativeExitCode = 1
        Write-Verbose "$File : $($_.Exception.Message)"
    }
    Write-LogSection ("$File " + ($Arguments -join " ")) @($fOut, $fErr)
    Remove-Item $fOut, $fErr -Force -ErrorAction SilentlyContinue
    if ($script:AfAnim) { Write-Host ("`r" + (" " * 78) + "`r") -NoNewline }
    if ($script:NativeExitCode -eq 0) {
        Write-Gut ("{0} {1} ({2})" -f $OK, $Label, (Format-Since $t0)) Green
        $script:StepsDone++
    } else {
        Write-Gut ("{0} {1} (exit {2})" -f $BAD, $Label, $script:NativeExitCode) Red
        $script:StepsFailed++
    }
    Write-Host ""
    $script:RunSteps += ("{0}|{1}|{2}" -f $Label, [int]((Get-Date) - $t0).TotalSeconds, $script:NativeExitCode)
    Show-AfBar
}

# Espera com spinner: o usuario ve que esta vivo e ha quanto tempo. Sem isto, os
# 52s do daemon do Docker eram um cursor piscando - relatado como travamento.
function Wait-Spinner {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Test,
        [int]$TimeoutSeconds = 60
    )
    if (& $Test) { return $true }
    $t0 = Get-Date
    $i = 0
    if (-not $script:AfAnim) { Write-Host ("  {0} {1}..." -f $DOT, $Label) -ForegroundColor DarkGray }
    $ok = $false
    while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSeconds) {
        if ($script:AfAnim) {
            Write-Host ("`r  " + $AF_SPIN[$i % $AF_SPIN.Count]) -ForegroundColor DarkYellow -NoNewline
            Write-Host (" {0} {1}   " -f $Label, (Format-Since $t0)) -ForegroundColor DarkGray -NoNewline
            $i++
        }
        Start-Sleep -Milliseconds 700
        if (& $Test) { $ok = $true; break }
    }
    if ($script:AfAnim) { Write-Host ("`r" + (" " * 78) + "`r") -NoNewline }
    if ($ok) { Write-Gut ("{0} {1} ({2})" -f $OK, $Label, (Format-Since $t0)) Green; Write-Host ""; Show-AfBar }
    return $ok
}

# -Verbose: a saida das ferramentas volta para a tela. Esconde-la e a regra (e o
# que separa uma tela limpa de uma colcha de retalhos com dism em portugues,
# winget em ingles e tres estilos de barra), mas quando algo da errado ver o que
# a ferramenta diz, na hora, vale mais.
if ($Verbose) { $VerbosePreference = "Continue"; $script:AfVerbose = $true }

# --- -Doctor: diagnostico read-only dos DOIS lados --------------------------
# Nao existia, e era exatamente o que faltou quando a instalacao falhou numa
# maquina real: sem log, sem manifesto a mao, a conversa virou adivinhacao. Aqui
# ele mede o lado Windows e DELEGA o lado Linux ao mesmo install.sh - um comando
# para diagnosticar a maquina inteira.
function Test-AfDoctor {
    # $nOk e nao $ok: o PowerShell NAO diferencia maiusculas em nome de
    # variavel, entao um contador chamado $ok e literalmente o mesmo $OK do
    # glifo de check. O CI mostrou o resultado: a tela saiu com "0 Microsoft
    # Windows", "1 elevated session", "2 distro(s)" no lugar dos vistos.
    $nOk = 0; $nAviso = 0; $nRuim = 0
    Write-Host ""
    Write-Rule "Windows"
    Write-Gut ("{0} {1}" -f $OK, [Environment]::OSVersion.VersionString) Green; Write-Host ""; $nOk++
    $elevado = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($elevado) { Write-Gut ("{0} elevated session" -f $OK) Green; $nOk++ }
    else { Write-Gut "! not elevated - installing WSL or Docker from here would fail" DarkYellow; $nAviso++ }
    Write-Host ""

    Write-Rule "WSL2"
    if (Get-Tool wsl) {
        $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $st = ""
        try { $st = (& (Resolve-ToolPath wsl) --status 2>&1 | Out-String) -replace "`0", "" } catch { $st = "" }
        $distros = ""
        try { $distros = (& (Resolve-ToolPath wsl) -l -q 2>&1 | Out-String) -replace "`0", "" } catch { $distros = "" }
        $ErrorActionPreference = $prev
        if (-not $st.Trim() -or $st -match "is not installed") {
            Write-Gut ("{0} the WSL feature is not installed" -f $BAD) Red; $nRuim++
        } elseif (-not $distros.Trim()) {
            Write-Gut ("{0} WSL is present but there is NO DISTRO" -f $BAD) Red; $nRuim++
        } else {
            Write-Gut ("{0} distro(s): {1}" -f $OK, ($distros.Trim() -replace "\s+", ", ")) Green; $nOk++
            if ((Invoke-WslProbe @()) -eq "ok") { Write-Gut ("{0} the distro runs" -f $OK) Green; $nOk++ }
            else { Write-Gut ("{0} the distro does not answer in time" -f $BAD) Red; $nRuim++ }
        }
    } else {
        Write-Gut ("{0} wsl.exe not found" -f $BAD) Red; $nRuim++
    }
    Write-Host ""

    Write-Rule "Docker Desktop and Ollama"
    if (Get-Tool docker) {
        Write-Gut ("{0} the docker CLI is on PATH" -f $OK) Green; $nOk++
        if (Test-DockerDaemon) { Write-Gut ("{0} the daemon answers" -f $OK) Green; $nOk++ }
        else { Write-Gut ("{0} the daemon does not answer - open Docker Desktop" -f $BAD) Red; $nRuim++ }
        if (Test-DockerInWsl) { Write-Gut ("{0} WSL integration is on" -f $OK) Green; $nOk++ }
        else { Write-Gut "! Docker is not reachable inside WSL - Settings > Resources > WSL Integration" DarkYellow; $nAviso++ }
    } else {
        Write-Gut ("{0} the docker CLI is not on PATH" -f $BAD) Red; $nRuim++
    }
    if (Get-Tool ollama) {
        if (Test-OllamaReady) { Write-Gut ("{0} the Ollama service answers" -f $OK) Green; $nOk++ }
        else { Write-Gut "! Ollama is installed but the service does not answer" DarkYellow; $nAviso++ }
    } else {
        Write-Gut "! Ollama is not installed (optional, only for a 100% local model)" DarkYellow; $nAviso++
    }
    Write-Host ""

    Write-Rule "Install manifest (Windows side)"
    if (Test-Path $AfManifest) {
        Write-Gut ("{0} {1}" -f $OK, $AfManifest) Green; Write-Host ""; $nOk++
        foreach ($linha in (Get-Content $AfManifest -ErrorAction SilentlyContinue)) {
            $p = $linha -split "`t", 2
            if ($p.Count -eq 2 -and $p[0] -ne "schema" -and $p[0] -notlike "#*") {
                Write-Host ("    " + $script:Gut + ("{0,-10} {1}" -f $p[0], $p[1])) -ForegroundColor DarkGray
            }
        }
    } else {
        Write-Gut "! no Windows manifest - nothing here was installed by AtlasFile" DarkYellow; Write-Host ""; $nAviso++
    }

    # O lado Linux responde por si: mesmo diagnostico, mesmo vocabulario.
    Write-Host ""
    Write-Rule "Inside WSL"
    $cmdDoc = "$AF_CURL $AF_SH_URL | bash -s -- --doctor --delegated"
    if ($script:AfDir) { $cmdDoc += " --dir $script:AfDir" }
    $saidaDoc = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdDoc))
    if ($saidaDoc.Trim()) {
        foreach ($linha in ($saidaDoc -split "`r?`n")) {
            if ($linha -match '^ATLASFILE_(FACT|UNINSTALL):') { continue }
            Write-Host $linha
        }
    } else {
        Write-Gut ("{0} could not run the diagnosis inside WSL" -f $BAD) Red; Write-Host ""; $nRuim++
    }

    Write-Host ""
    Write-Rule "Diagnosis (Windows side)"
    Write-Gut ("{0} {1} ok" -f $OK, $nOk) Green
    Write-Host ("   ! {0} to watch" -f $nAviso) -ForegroundColor DarkYellow -NoNewline
    Write-Host ("   {0} {1} broken" -f $BAD, $nRuim) -ForegroundColor Red
    Write-Host ""
    return ($nRuim -eq 0)
}

# A identidade da instalacao (usuario do WSL e diretorio) tem de ser recuperada
# ANTES de qualquer bloco que fale com o outro lado - os tres rodam antes da
# fase 1, que e onde ela seria descoberta.
Restore-AfInstallIdentity

if ($Doctor) {
    if (Test-AfDoctor) { Stop-Installer 0; return }
    Stop-Installer 1; return
}

# --- -DryRun: o que uma instalacao faria, dos dois lados ---------------------
# Nao instala NADA, nem do lado Windows: um dry run que instalasse o WSL para
# depois dizer "nada foi instalado" seria uma mentira cara.
# `-and -not $Uninstall`: com as duas flags juntas quem responde e o bloco do
# uninstall, que imprime o plano de REMOCAO. Sem esta guarda o -DryRun capturava
# a combinacao e devolvia o plano de INSTALACAO - o oposto do que foi pedido.
if ($DryRun -and -not $Uninstall) {
    Write-Host ""
    Write-Rule "Install plan (Windows side)"
    foreach ($item in @(
        @{ Nome = "WSL2";           Tem = [bool](Get-Tool wsl) },
        @{ Nome = "Docker Desktop"; Tem = [bool](Get-Tool docker) },
        @{ Nome = "Ollama";         Tem = [bool](Get-Tool ollama) }
    )) {
        if ($item.Tem) { Write-Gut ("{0} {1} is already here" -f $OK, $item.Nome) Green }
        else { Write-Gut ("{0} {1} WOULD BE INSTALLED" -f $DOT, $item.Nome) DarkYellow }
        Write-Host ""
    }
    Write-Host ""
    Write-Rule "Install plan (inside WSL)"
    $cmdSeco = "$AF_CURL $AF_SH_URL | bash -s -- --dry-run --delegated"
    if ($script:AfDir) { $cmdSeco += " --dir $script:AfDir" }
    $saidaSeca = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdSeco))
    foreach ($linha in ($saidaSeca -split "`r?`n")) {
        if ($linha -match '^ATLASFILE_(FACT|UNINSTALL):') { continue }
        Write-Host $linha
    }
    Write-Info "-DryRun: nothing was installed."
    Stop-Installer 0; return
}

if ($Uninstall) {
    # ORQUESTRACAO. Esta maquina tem DOIS escopos - a distro e o Windows - com
    # dois manifestos, e ate aqui so um deles imprimia plano: o usuario
    # confirmava uma lista que falava da distro, e o lado Windows agia depois,
    # sem plano e sem confirmacao. Numa maquina real isso produziu "Docker was
    # already on this machine before AtlasFile - preserved" segundos antes de o
    # Docker Desktop ser apagado, e um Ollama que nao aparecia em secao nenhuma
    # mas era removido assim mesmo.
    #
    # O contrato de um bootstrapper (a forma do bootstrap.ps1 do Claude Code) e:
    # preparar, delegar NAO-INTERATIVAMENTE e propagar o codigo de saida. E o que
    # este bloco passa a fazer: pede os FATOS ao install.sh, imprime UM plano
    # cobrindo os dois lados, faz UMA pergunta e so entao age.
    $extraHost = Get-AfHostExtra
    $flagsComuns = "--uninstall --delegated"
    if ($RemoveDeps) { $flagsComuns += " --remove-deps" }
    if ($Force)      { $flagsComuns += " --force" }
    if ($extraHost)  { $flagsComuns += " --host-extra $extraHost" }
    if ($script:AfDir) { $flagsComuns += " --dir $script:AfDir" }

    # --- 1. FATOS: nao pergunta, nao age ------------------------------------
    Start-Step "reading the removal plan from inside WSL"
    $cmdPlano = "$AF_CURL $AF_SH_URL | bash -s -- $flagsComuns --plan-only"
    $plano = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdPlano))
    if ($script:NativeExitCode -ne 0 -or $plano -notmatch "ATLASFILE_UNINSTALL: plan-only") {
        Write-Fail "could not read the removal plan from WSL (exit $($script:NativeExitCode))"
        Show-LogTail
        Write-Host "    Nothing was removed."
        Stop-Installer 1; return
    }
    Write-Ok "removal plan read"

    # --- 2. UM plano, cobrindo os dois lados --------------------------------
    Write-Host ""
    foreach ($linha in ($plano -split "`r?`n")) {
        # As linhas de maquina existem para ESTE script, nao para o usuario.
        if ($linha -match '^ATLASFILE_(FACT|UNINSTALL):') { continue }
        Write-Host $linha
    }
    $volume = ""
    if ($plano -match 'ATLASFILE_FACT: volume=(\S+)') { $volume = $Matches[1] }
    $temAcoes = ($plano -match 'ATLASFILE_FACT: actions=1')
    if (-not $temAcoes) {
        Write-Info "nothing to remove."
        Stop-Installer 0; return
    }
    # -Uninstall -DryRun: o plano ja esta na tela, e ele cobre os dois lados.
    # Parar aqui e o "mostre, nao faca" do uninstall.
    if ($DryRun) {
        Write-Info "-DryRun: nothing was touched."
        Stop-Installer 0; return
    }

    # --- 3. A decisao sobre os dados, uma vez -------------------------------
    $decisaoDados = ""
    if ($PurgeData)      { $decisaoDados = "--purge-data" }
    elseif ($KeepData)   { $decisaoDados = "--keep-data" }
    elseif ($volume) {
        if ($Yes) {
            Write-Fail "the volume $volume holds the search index - decide explicitly: -PurgeData or -KeepData"
            Stop-Installer 1; return
        }
        Write-Host ""
        Write-Host "  ? The volume $volume holds the search index." -ForegroundColor Yellow
        Write-Host "    Your documents and the _ATLASFILE journal live on disk and are NOT affected;"
        Write-Host "    the index is rebuilt by Reconcile after a reinstall."
        if (Confirm-Plan "Erase the volume?") {
            $decisaoDados = "--purge-data"
            Write-Info "the search index WILL be erased"
        } else {
            $decisaoDados = "--keep-data"
            Write-Info "the search index will be kept"
        }
    }

    # --- 4. UMA confirmacao ---------------------------------------------------
    Write-Host ""
    if (-not (Confirm-Plan "Execute the plan above?")) {
        Write-Info "uninstall cancelled - nothing was touched."
        # 1602 e o codigo que o mundo Windows ja usa para "o usuario cancelou".
        Stop-Installer 1602; return
    }

    # --- 5. Execucao do lado WSL, nao-interativa ------------------------------
    Write-Host ""
    $cmdExec = "$AF_CURL $AF_SH_URL | bash -s -- $flagsComuns --yes $decisaoDados"
    $saidaExec = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdExec))
    foreach ($linha in ($saidaExec -split "`r?`n")) {
        if ($linha -match '^ATLASFILE_(FACT|UNINSTALL):') { continue }
        Write-Host $linha
    }
    # AS DUAS PROVAS. Nao ha documentacao oficial de que o wsl.exe propague o
    # codigo de saida do comando Linux, e um codigo engolido JAMAIS pode ser
    # lido como "o usuario confirmou" - foi assim que um "nao" virou um Docker
    # Desktop apagado. Faltando qualquer uma das provas, o lado Windows nao e
    # tocado.
    if ($script:NativeExitCode -ne 0 -or $saidaExec -notmatch "ATLASFILE_UNINSTALL: confirmed") {
        Write-Fail "the WSL side did not confirm the removal (exit $($script:NativeExitCode))"
        Write-Host "    Nothing was removed on the Windows side."
        Show-LogTail
        Stop-Installer 1; return
    }

    # --- 6. Lado Windows: so o que o plano confirmado mostrou -----------------
    $reinicioPendente = $false
    if (-not $RemoveDeps) {
        Write-Info "Windows-side dependencies preserved - pass -RemoveDeps to revert the ones AtlasFile installed"
    } else {
        foreach ($item in @(
            @{ Key = "docker"; Id = "Docker.DockerDesktop"; Label = "Docker Desktop"; Path = (Join-Path $env:ProgramFiles "Docker\Docker") },
            @{ Key = "ollama"; Id = "Ollama.Ollama";        Label = "Ollama";         Path = "" }
        )) {
            if ((Get-AfState $item.Key) -ne "created") {
                Write-Info "$($item.Label) was already on this machine before AtlasFile - preserved"
                continue
            }
            # Perguntar ANTES de prometer, como faz o desinstalador do
            # mac-env-setup (`brew list --cask X` antes de planejar a remocao).
            # Sem isso o Ollama falhou com "exit -1978335107" e a unica saida
            # oferecida era "remove it from Settings > Apps", sem dizer por que.
            $null = Invoke-NativeCapture winget @("list", "-e", "--id", $item.Id, "--source", "winget")
            if ($script:NativeExitCode -ne 0) {
                Write-Warn "$($item.Label) is not registered with winget under $($item.Id) - remove it from Settings > Apps"
                continue
            }
            # --source winget tambem AQUI: a documentacao do comando uninstall
            # diz, com todas as letras, que sem isso o winget pode esbarrar no
            # contrato da Microsoft Store, porque consulta as duas fontes. E o
            # mesmo "Failed when searching source: msstore" que ja tinha
            # derrubado a instalacao numa maquina real.
            Invoke-Step "removing $($item.Label)" winget @("uninstall", "-e", "--id", $item.Id,
                "--source", "winget", "--silent", "--disable-interactivity")
            if ($script:NativeExitCode -ne 0) {
                Write-Warn "could not remove $($item.Label) (exit $($script:NativeExitCode)) - remove it from Settings > Apps"
                Show-LogTail 8
            } elseif ($item.Path -and (Test-Path $item.Path)) {
                # Medido no Windows real: o desinstalador do Docker agenda
                # arquivos em uso para exclusao no proximo boot e a pasta
                # sobrevive. Isso e 3010 - sucesso com reinicio pendente -, nao
                # uma falha, e nao dizer isso deixaria o usuario achando que a
                # remocao nao funcionou.
                $reinicioPendente = $true
            }
        }
        Remove-Item $AfManifest -ErrorAction SilentlyContinue
    }

    # --- 7. UM veredito, agora que os dois lados terminaram -------------------
    Write-Host ""
    Write-Ok "AtlasFile removed. What already existed on this machine was preserved."
    if ($reinicioPendente) {
        Write-Info "some files were scheduled for deletion on the next restart"
        Stop-Installer 3010; return
    }
    Stop-Installer 0; return
}

# 1. WSL2 - offer to install when missing
# Measured on a clean Windows 11 (build 26200): wsl.exe SHIPS WITH WINDOWS even
# when the feature is absent, so `Get-Command wsl` always succeeds and proves
# nothing. In that state `wsl --status` writes "The Windows Subsystem for Linux
# is not installed" to STDERR and still exits 0 - so neither $LASTEXITCODE nor a
# `2>$null` redirect can be trusted either, and with ErrorActionPreference=Stop
# the native stderr became a terminating NativeCommandError that killed the
# installer with a raw stack trace. The message content is the only real signal.
Write-Phase 1 "Checking Windows prerequisites"

$wslReady = $false
$wslOut = ""
$wslMotivo = ""
if (Get-Tool wsl) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    # `wsl` e nao `wsl.exe`: com a extensao explicita a resolucao pula qualquer
    # substituto na frente do PATH, o que torna este caminho intestavel - a
    # bancada com stubs nunca conseguia exercita-lo.
    try { $wslOut = (& (Resolve-ToolPath wsl) --status 2>&1 | Out-String) } catch { $wslOut = "" }
    $ErrorActionPreference = $prevEap
    # wsl.exe emits UTF-16: without stripping the NULs the text arrives as
    # "i`0s`0 `0n`0o`0t`0..." and every -match below silently fails.
    $wslOut = $wslOut -replace "`0", ""
    # O --status responder NAO prova que o WSL funciona. Relatado numa maquina
    # Windows 11 real: o instalador disse "WSL2 available", nao ofereceu instalar
    # o WSL, e logo depois o Docker Desktop acusou "WSL not installed" - porque
    # havia feature ligada e NENHUMA DISTRO. Prova de verdade e executar.
    if ($wslOut.Trim() -and
        $wslOut -notmatch "is not installed" -and
        $wslOut -notmatch "no installed distributions") {
        $ErrorActionPreference = "Continue"
        # Provar que o WSL EXECUTA exige iniciar a distro, o que na primeira vez
        # leva dezenas de segundos. Sem este aviso o usuario fica olhando um
        # cursor piscando sem saber se travou (relatado numa maquina real).
        $distros = ""
        try { $distros = (& (Resolve-ToolPath wsl) -l -q 2>&1 | Out-String) -replace "`0", "" } catch { $distros = "" }
        if ($distros.Trim()) {
            # PRIMEIRO o remedio canonico da Microsoft, depois a verificacao. Um
            # kernel do WSL desatualizado e a causa comum de `wsl -e` ficar
            # pendurado mesmo com virtualizacao habilitada, e `wsl --update` e
            # idempotente e rapido quando ja esta em dia. Tentar o obvio antes de
            # diagnosticar evita gastar o tempo do usuario com sondagem.
            Invoke-Step "updating the WSL kernel" wsl @("--update")
            Start-Step "checking that WSL2 actually runs"
            $prova = Invoke-WslProbe @()
            if ($prova -eq "ok") { $wslReady = $true }
            elseif ($prova -eq "lento") {
                # NAO declarar pronto: uma distro listada que nao responde e o
                # sintoma classico de virtualizacao indisponivel - o WSL2 fica
                # esperando para sempre a VM que nunca sobe. Relatado numa
                # maquina real, onde o usuario teve que interromper com Ctrl+C e
                # o Docker Desktop, na mesma maquina, acusava
                # "Virtualization support not detected".
                $wslMotivo = "the distro is installed but did not answer in time, even after wsl --update"
            }
            else {
                # Distro recem-instalada com --no-launch existe mas nunca foi
                # inicializada: o usuario padrao ainda nao existe e qualquer
                # execucao normal cairia no assistente de criacao de conta, que
                # travaria uma instalacao desatendida. Como root ela ja responde.
                $prova = Invoke-WslProbe @("-u", "root")
                if ($prova -ne "falhou") {
                    $wslReady = $true
                    $script:WslUser = @("-u", "root")
                    Write-Info "the WSL distro is not initialized yet - using root for this install"
                } else {
                    $wslMotivo = "the distro exists but does not run"
                }
            }
        } else {
            $wslMotivo = "WSL is present but NO DISTRO is installed"
        }
        $ErrorActionPreference = $prevEap
    }
}
if (-not $wslReady) {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    # O manifesto ja registra que ESTE instalador rodou `wsl --install` aqui.
    # Sem consultar isso, a segunda execucao repetia o mesmo comando e a mesma
    # frase otimista, e o usuario entrava em loop: instalar, reiniciar,
    # instalar, reiniciar. Medido num Windows 11 real (build 26200), onde o
    # wsl.exe habilitava o VirtualMachinePlatform de novo a cada volta e nunca
    # chegava a instalar distro nenhuma.
    $jaTentou = (Get-AfState "wsl") -eq "created"
    if ($isAdmin -and (Confirm-Step "WSL2 is not usable - install it now? (a Windows restart may be required)")) {
        # Dizer O QUE vai baixar ANTES de baixar: o usuario viu "Baixando:
        # Ubuntu 31,3%" sem saber por que um Ubuntu aparecia na instalacao dele.
        Write-Host ""
        Write-Host "  Installing WSL2 and Ubuntu (~500 MB, one time)." -ForegroundColor Cyan
        Write-Host "  AtlasFile runs in Linux containers: Ubuntu is where its installer"
        Write-Host "  and its stack actually run, and Docker Desktop needs WSL2 too."
        Write-Host ""
        if ($jaTentou) {
            # Repetir o comando que JA nao resolveu seria pedir mais um reinicio
            # para nada. Estas duas features sao o que o proprio `wsl --install`
            # liga por baixo: faze-lo explicitamente completa um estado que
            # ficou pela metade, e e idempotente quando ja esta ligado.
            Write-Warn "wsl --install already ran here and WSL is still unusable - enabling the Windows features explicitly"
            # /English: o dism fala o idioma do Windows, e o log precisa ser
            # legivel para quem for diagnosticar - inclusive eu, quando o usuario
            # colar o rabo do arquivo. Documentado como opcao global do DISM.
            Invoke-Step "enabling VirtualMachinePlatform" dism @(
                "/online", "/enable-feature", "/featurename:VirtualMachinePlatform", "/all", "/norestart", "/English")
            Invoke-Step "enabling Windows Subsystem for Linux" dism @(
                "/online", "/enable-feature", "/featurename:Microsoft-Windows-Subsystem-Linux", "/all", "/norestart", "/English")
        }
        # --no-launch: sem isso o Windows abre o assistente de criacao de
        # usuario da distro, que trava uma instalacao desatendida.
        Invoke-Step "installing WSL2 and Ubuntu (~500 MB)" wsl @("--install", "--no-launch")
        if ($script:NativeExitCode -ne 0) {
            # Mandar reiniciar DEPOIS de uma falha e o que fechava o loop: o
            # usuario reiniciava so para reencontrar exatamente a mesma tela.
            Write-Fail "wsl --install failed (exit code $($script:NativeExitCode)) - nothing to gain from restarting."
            Show-LogTail
            Write-Host "    Run it by hand to read the real error:"
            Write-Host "      wsl --install" -ForegroundColor Yellow
            Write-Host "    Windows logs servicing failures in %WINDIR%\Logs\DISM\dism.log"
            Stop-Installer 1; return
        }
        Set-AfState "wsl" "created"
        # A distro tambem e artefato nosso (~500 MB) e ate aqui nao era
        # registrada em lugar nenhum: o plano falava do RECURSO WSL e ficava
        # calado sobre o Ubuntu que este instalador baixou.
        $prevDistro = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try {
            $nomeDistro = ((& (Resolve-ToolPath wsl) -l -q 2>&1 | Out-String) -replace "`0", "").Trim() -split "`r?`n" |
                Where-Object { $_ } | Select-Object -First 1
            if ($nomeDistro) { Set-AfState "wsl_distro" $nomeDistro.Trim() }
        } catch { Write-Verbose "distro name unavailable: $($_.Exception.Message)" }
        $ErrorActionPreference = $prevDistro
        # Reiniciar nem sempre e necessario. Quando as features JA estavam
        # ligadas e faltava so a distro - que e o estado da SEGUNDA volta - o
        # `wsl --install` termina o servico ali mesmo. Mandar reiniciar nesse
        # caso custa mais uma volta identica a anterior, que e precisamente o
        # que o usuario le como loop. Entao: perguntar a maquina em vez de supor.
        Invoke-Step "updating the WSL kernel" wsl @("--update")
        Start-Step "checking whether WSL already works"
        if ((Invoke-WslProbe @("-u", "root")) -eq "ok") {
            $wslReady = $true
            # Distro recem-instalada com --no-launch nao tem usuario padrao: so
            # o root responde ate alguem completar o assistente.
            $script:WslUser = @("-u", "root")
            Write-Ok "WSL2 installed and running - no restart needed"
        } else {
            Write-Ok "WSL install started - restart Windows and run this installer again."
            if ($jaTentou) {
                Write-Info "if this same screen returns after the restart, the Windows features are not sticking: check %WINDIR%\Logs\DISM\dism.log"
            }
            Stop-Installer 0; return
        }
    }
}
if (-not $wslReady) {
    Write-Fail "WSL2 is not usable on this machine."
    if ($wslMotivo) { Write-Host "    ($wslMotivo)" -ForegroundColor DarkGray }
    if ($wslMotivo -match "did not answer") {
        # Sem cravar causa: a virtualizacao pode estar LIGADA e o WSL ainda assim
        # nao subir. Lista o que verificar, na ordem de probabilidade.
        Write-Host "    WSL did not answer. Check, in this order:"
        Write-Host "      wsl --update      (already tried by this installer)" -ForegroundColor Yellow
        Write-Host "      wsl --shutdown    then run this installer again" -ForegroundColor Yellow
        Write-Host "      wsl -l -v         does the distro show as Stopped/Running?" -ForegroundColor Yellow
        Write-Host "      Get-CimInstance Win32_Processor | Select VirtualizationFirmwareEnabled" -ForegroundColor Yellow
        Write-Host "      Get-WinEvent -LogName System -MaxEvents 200 | Where ProviderName -like '*Hyper-V*'" -ForegroundColor Yellow
    } else {
        Write-Host "    Install it with (PowerShell as Administrator):"
        Write-Host "      wsl --install" -ForegroundColor Yellow
        Write-Host "    Restart Windows and run this installer again."
    }
    if (-not $isAdmin) { Write-Host "    (this session is not elevated, so the installer cannot do it for you)" -ForegroundColor DarkGray }
    Stop-Installer 1; return
}
Set-AfState "wsl" "preexisting"
# A identidade da instalacao e gravada AQUI, assim que se sabe qual usuario
# consegue rodar dentro da distro - e nao no fim, porque uma instalacao que
# falhe depois disto ainda precisa poder ser desinstalada.
Set-AfState "wsl_user" $(if ($script:WslUser.Count -gt 0) { "root" } else { "default" })
Write-Ok "WSL2 available"

Write-Phase 2 "Docker Desktop"

$docker = Get-Tool docker
if (-not $docker) {
    $winget = Get-Tool winget
    if ($winget -and (Confirm-Step "Docker Desktop not found - install it now via winget?")) {
        # --source winget: both Docker Desktop and Ollama live in the community
        # source. Without it winget also queries msstore, which fails on region,
        # on a signed-out account or on unaccepted terms - exactly the
        # "Failed when searching source: msstore" seen on a real Windows 11.
        Invoke-Step "downloading and installing Docker Desktop (~600 MB)" winget @(
            "install", "-e", "--id", "Docker.DockerDesktop",
            "--source", "winget", "--accept-package-agreements", "--accept-source-agreements",
            "--disable-interactivity")
        if ($script:NativeExitCode -ne 0) {
            Write-Fail "winget could not install Docker Desktop - install manually: https://docs.docker.com/desktop/install/windows-install/"
            Show-LogTail
            Stop-Installer 1; return
        }
        Set-AfState "docker" "created"
        Write-Ok "Docker Desktop installed"
        # Without this the CLI stays invisible to the running session and every
        # later `docker ...` fails as an unknown command.
        Update-SessionPath
        $docker = Get-Tool docker
        if (-not $docker) {
            Write-Info "the docker CLI is not on PATH yet - it appears after the first launch"
        }
    } else {
        Write-Fail "Docker Desktop not found: https://docs.docker.com/desktop/install/windows-install/"
        Write-Host "    (or re-run with -InstallDeps to let this installer handle it)"
        Stop-Installer 1; return
    }
}
if ($docker -and (Get-AfState "docker") -eq "") { Set-AfState "docker" "preexisting" }
if (-not (Test-DockerDaemon)) {
    $dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) { Start-Process $dockerExe }
    # The first launch is what creates the CLI shim, so refresh again while waiting.
    if (-not $env:ATLASFILE_DOCKER_WAIT) { Start-Sleep -Seconds 5 }
    # Timeout injetavel so para teste, mesmo padrao de TTY_DEV/DOCKER_APP_PATH no
    # install.sh: sem isso a bancada esperaria 5 minutos reais por cenario.
    $daemonWait = 300
    if ($env:ATLASFILE_DOCKER_WAIT) { $daemonWait = [int]$env:ATLASFILE_DOCKER_WAIT }
    # O PATH e atualizado A CADA sondagem: o shim do CLI so nasce no primeiro
    # launch, entao consultar uma vez antes da espera nao basta.
    if (-not (Wait-Spinner -Label "starting Docker Desktop - accept the terms in the window that opens" `
            -Test { Update-SessionPath; Test-DockerDaemon } -TimeoutSeconds $daemonWait)) {
        # Two causes are common and the old message only named one, sending
        # people to a dialog that was not the problem. Measured on a Parallels
        # VM: Docker Desktop showed "Virtualization support not detected" while
        # Win32_ComputerSystem.HypervisorPresent still reported True, so there
        # is no reliable signal to tell them apart - name both instead.
        Write-Fail "the Docker daemon did not come up. Two usual causes:"
        Write-Host "    1. Docker Desktop's first-launch dialog was not completed (accept the terms)."
        Write-Host "    2. Virtualization is not available: enable it in the firmware/BIOS, or if this"
        Write-Host "       is a virtual machine, turn on nested virtualization in the hypervisor."
        Write-Host "    Fix it and re-run this installer - it is idempotent."
        Stop-Installer 1; return
    }
}
Write-Ok "Docker Desktop running"

# O Docker Desktop so injeta o CLI dentro da distro DEPOIS que o motor sobe, e
# isso leva alguns segundos. Verificar uma unica vez, no instante seguinte,
# reprova uma maquina que ficaria pronta logo em seguida - medido num Windows 11
# real, onde o daemon do lado Windows respondeu em 52s e esta verificacao,
# feita imediatamente apos, falhou. O lado Windows ja tinha 300s de paciencia;
# este lado tinha ZERO, e a assimetria era o bug.
$esperaWsl = 120
if ($env:ATLASFILE_DOCKER_WAIT) { $esperaWsl = [int]$env:ATLASFILE_DOCKER_WAIT }
$wslDockerOk = Wait-Spinner -Label "waiting for Docker's WSL integration" `
    -Test { Test-DockerInWsl } -TimeoutSeconds $esperaWsl
if (-not $wslDockerOk) {
    Write-Fail "Docker is not reachable inside WSL."
    Write-Host "    In Docker Desktop -> Settings -> Resources -> WSL Integration, enable your distro."
    Stop-Installer 1; return
}
Write-Ok "Docker and WSL are talking to each other"

# A fase 3 era o Ollama, e ela saiu: puxar um modelo sao varios GB e tirava
# qualquer previsibilidade da duracao da instalacao. Habilitar um modelo local
# passa a ser um passo POSTERIOR, ensinado no painel final. De quebra, o defeito
# de o Ollama viver em dois sistemas operacionais ao mesmo tempo deixa de existir
# por construcao. O UNINSTALL continua sabendo reverter um Ollama instalado por
# versoes anteriores - o manifesto daquelas instalacoes segue valendo.

Write-Phase 3 "Installing AtlasFile inside WSL"
Write-Info "the Linux installer takes over from here - first run builds images (~15 min)"
Write-Host ""
# --delegated: o banner ja foi desenhado por este script segundos atras. Dois
# banners seguidos leem como dois produtos - e eles nem eram o mesmo desenho.
#
# --no-ollama NAO existe mais e nao pode ser passado: o Ollama saiu dos dois
# instaladores, e uma flag desconhecida faz o install.sh sair com "Unknown flag".
# O defeito que ela existia para conter (a pergunta reaparecendo dentro da
# distro) deixou de existir por construcao.
# Gravado ANTES de delegar: uma instalacao que morra no meio ainda precisa deixar
# para tras onde ela estava sendo feita, senao o uninstall nao sabe onde olhar.
Set-AfState "install_dir" $(if ($Dir) { $Dir } else { "~/AtlasFile" })
$shFlags = "--no-open --delegated"
if ($Yes) { $shFlags += " --yes" }
if ($InstallDeps) { $shFlags += " --install-deps" }
if ($EnableAuth) { $shFlags += " --enable-auth" }
if ($Dir) { $shFlags += " --dir $Dir" }
$argsSh = @($script:WslUser) + @("-e", "bash", "-c", "$AF_CURL $AF_SH_URL | bash -s -- $shFlags")
Invoke-Native wsl $argsSh
if ($script:NativeExitCode -ne 0) {
    Write-Fail "Install failed inside WSL (see the messages above)."
    Stop-Installer 1; return
}

# Abrir o navegador e cortesia, nao resultado: numa sessao nao interativa o
# Start-Process falha com "The operation attempted is not supported" e cuspia
# erro DEPOIS de a instalacao ter dado certo (medido em bancada).
try { Start-Process "http://localhost:5173" -ErrorAction Stop }
catch { Write-Info "open http://localhost:5173 in your browser" }

# O install.sh JA imprimiu o painel com Interface/API/Dashboards, a senha do
# OpenSearch e a chave de API. Repetir metade disso aqui era o mesmo defeito do
# veredito duplicado do uninstall: duas conclusoes para um trabalho so. Este
# painel diz apenas o que e do lado Windows.
$dirWsl = if ($script:AfDir) { $script:AfDir } else { "~/AtlasFile" }
Write-Panel @(
    "logs   wsl -e bash -c 'cd $dirWsl && docker compose logs -f'",
    "stop   wsl -e bash -c 'cd $dirWsl && docker compose down'"
)

# Placar: o que aconteceu, em numeros.
Clear-AfBar
$dur = [int]((Get-Date) - $script:RunStart).TotalSeconds
$durTexto = if ($dur -ge 60) { "{0}m{1:d2}s" -f [int]($dur / 60), ($dur % 60) } else { "${dur}s" }
Write-Rule "AtlasFile is up"
Write-Gut ("{0} {1} steps" -f $OK, $script:StepsDone) Green
if ($script:StepsFailed -gt 0) { Write-Host ("   {0} {1} failed" -f $BAD, $script:StepsFailed) -ForegroundColor Red -NoNewline }
Write-Host ("   in {0}" -f $durTexto) -ForegroundColor DarkGray

# Espelho em arquivo, ao lado do manifesto: diagnosticar uma instalacao de ontem
# sem isso e adivinhacao.
try {
    $relatorio = Join-Path $AfStateDir "last-run.log"
    $linhas = @("install.ps1 - " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"),
                "dir: $dirWsl - duration: $durTexto", "")
    foreach ($s in $script:RunSteps) {
        $p = $s -split '\|'
        $linhas += ("  {0,-52} {1}s  rc={2}" -f $p[0], $p[1], $p[2])
    }
    $linhas += @("", "tool output of this run: $script:AfLog")
    if (-not (Test-Path $AfStateDir)) { New-Item -ItemType Directory -Path $AfStateDir -Force | Out-Null }
    $linhas | Set-Content -Path $relatorio -Encoding UTF8
    Write-Info "run report: $relatorio"
} catch {
    Write-Verbose "run report not written: $($_.Exception.Message)"
}
# A saida das ferramentas nao apareceu na tela por design; dizer ONDE ela esta e
# o que separa "limpo" de "escondido".
if (Test-Path $script:AfLog) { Write-Info "tool output for this run: $script:AfLog" }
Write-Host ""
