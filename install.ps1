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
# Parameters (when saved and run as a file; under `iex` the prompts cover it).
# This list is a summary — `-Help` is the complete one:
#   -Dir PATH      where AtlasFile lives inside WSL (default: ~/AtlasFile)
#   -ProjectsRoot PATH
#                  where YOUR DOCUMENTS live (default: your Windows Documents)
#   -Branch NAME   branch to clone (default: main)
#   -Yes           non-interactive (accept defaults; does NOT install deps)
#   -InstallDeps   authorize installing missing prerequisites without prompting
#   -EnableAuth    enable API authentication (forwarded to install.sh)
#   -Verbose       show every tool's output instead of hiding it in the log
#   -Uninstall     print a removal plan and, once confirmed, revert what this
#                  installer created (delegates the Linux side to install.sh
#                  inside WSL and reverts the Windows side from the manifest)
#   -PurgeData     uninstall: also erase the OpenSearch volume (the index)
#   -KeepData      uninstall: keep the OpenSearch volume
#   -RemoveDeps    uninstall: also remove Windows-side deps this script installed
#   -Force         uninstall: remove the clone inside WSL even with local changes
#   -Doctor        read-only report of BOTH sides; installs nothing
#   -DryRun        show, do not do (with -Uninstall: the removal plan)
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
    [string]$Dir = "",
    [string]$ProjectsRoot = "",
    [string]$Branch = "",
    # Depreciadas: aceitas e IGNORADAS. O site publica -WithOllama ha meses e
    # PowerShell recusa parametro desconhecido com erro terminante - quem colar
    # o comando do site nao veria nem o banner.
    [switch]$WithOllama,
    [string]$OllamaModel = ""
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
  -ProjectsRoot PATH
                  Where YOUR DOCUMENTS live (default: your Windows Documents
                  folder, so they show up in Explorer). Give it a Windows path
                  or a WSL one; forwarded to install.sh as --projects-root
  -Branch NAME    Branch to clone (default: main). Forwarded as --branch
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

Deprecated (accepted and ignored, so a published command line never breaks):
  -WithOllama     Ollama is no longer installed here - pulling a model is several
  -OllamaModel    GB and made the install take an unpredictable amount of time.
                  The final panel shows how to enable a local model afterwards

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

Environment: ATLASFILE_SH_URL (override the install.sh URL, for testing a branch)
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
    # A barra viva ocupa a ultima linha. Sem apaga-la a pergunta sai GRUDADA
    # nela - medido no Windows 11 real:
    #   "[bar] fase 2/3  ? Docker Desktop not found - install it now? [y/N]"
    # O install.sh chama bar_clear antes de toda mensagem; aqui faltava nas
    # perguntas, que sao justamente onde a tela precisa estar limpa.
    Clear-AfBar
    if ($InstallDeps) { return $true }
    if ($Yes) { return $false }  # conservative: -Yes alone never installs system deps
    if (-not [Environment]::UserInteractive) { return $false }
    # Com a calha, como o ask() do install.sh. Sem ela a pergunta era a unica
    # linha do trilho que nao pendurava nele.
    Write-Host $script:Gut -ForegroundColor DarkGray -NoNewline
    $answer = Read-Host "? $Question [y/N]"
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
# Sobrescrevivel por ambiente, espelhando o ATLASFILE_REPO_URL do install.sh.
# Sem isto NAO DA para testar uma branch de ponta a ponta no Windows: o .ps1 da
# branch buscaria o .sh do main, e o teste validaria a combinacao errada.
$AF_SH_URL = if ($env:ATLASFILE_SH_URL) { $env:ATLASFILE_SH_URL }
             else { "https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh" }
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
# Texto de arquivo, decidindo a codificacao pelos BYTES.
#
# Get-Content -Raw no Windows PowerShell 5.1 decodifica com a code page ANSI: os
# bytes UTF-8 que o WSL devolve viravam mojibake, e a tela inteira do uninstall
# saiu com lixo no lugar da calha. Ler como UTF-8 sempre tambem nao serve,
# porque a saida do PROPRIO wsl.exe (--status, -l) e UTF-16LE - dai a decisao
# pelos bytes, e nao por um palpite fixo.
function Get-AfText([string]$Arquivo) {
    if (-not (Test-Path $Arquivo)) { return "" }
    try { $bytes = [IO.File]::ReadAllBytes($Arquivo) } catch { return "" }
    if ($bytes.Length -eq 0) { return "" }
    $utf16 = $false
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) { $utf16 = $true }
    else {
        # ASCII em UTF-16LE poe um NUL em toda posicao impar. Um quarto ja basta
        # para distinguir de UTF-8, que praticamente nunca tem NUL.
        $limite = [Math]::Min(512, $bytes.Length)
        $nulos = 0
        for ($i = 1; $i -lt $limite; $i += 2) { if ($bytes[$i] -eq 0) { $nulos++ } }
        if ($limite -gt 8 -and $nulos -gt ($limite / 4)) { $utf16 = $true }
    }
    if ($utf16) { return [Text.Encoding]::Unicode.GetString($bytes) }
    return (New-Object Text.UTF8Encoding $false).GetString($bytes)
}

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
    # Cada arquivo entra so se tiver conteudo. Concatenar "$vazio`n" duas vezes
    # deixava o texto terminando em varias quebras, e quem ecoa linha a linha
    # transformava isso em linhas em branco na tela do usuario.
    foreach ($f in @($fOut, $fErr)) {
        if (Test-Path $f) {
            $parte = (Get-AfText $f)
            if ($parte.Trim()) { $texto += ($parte.TrimEnd() + "`n") }
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
    Clear-AfBar
    if ($Yes) { return $true }
    if (-not [Environment]::UserInteractive) { return $false }
    Write-Host $script:Gut -ForegroundColor DarkGray -NoNewline
    $resposta = Read-Host "? $Pergunta [y/N]"
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
        $texto = Get-AfText $saida
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
    try { & $caminho info *> $null; $respondeu = ($LASTEXITCODE -eq 0) } catch { $respondeu = $false }
    $ErrorActionPreference = $prev
    return $respondeu
}

# Pronto = o servico responde; ter o binario nao prova nada. O `ollama list`
# conversa com o daemon em 127.0.0.1:11434, que e exatamente quem recusava a
# conexao logo apos a instalacao.
function Test-OllamaReady {
    $caminho = Resolve-ToolPath ollama
    if (-not $caminho) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $caminho list *> $null; $respondeu = ($LASTEXITCODE -eq 0) } catch { $respondeu = $false }
    $ErrorActionPreference = $prev
    return $respondeu
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

# A integracao com o WSL e o que faz o `docker` existir DENTRO da distro, e ela
# nem sempre vem ligada depois de uma instalacao nova: num Windows 11 real o
# instalador parou exatamente aqui, pedindo um clique em
# Settings > Resources > WSL Integration.
#
# Docker Desktop guarda isso em %APPDATA%\Docker. O nome do arquivo mudou na
# versao 4.35 (settings.json -> settings-store.json), entao os dois sao
# tentados, nessa ordem. E formato INTERNO, sem contrato publico: se o arquivo
# nao existir, nao for JSON valido ou nao tiver a chave, isto NAO falha - cai na
# espera e na mensagem manual que ja existiam. Nunca derrubar a instalacao por
# causa de um palpite sobre esquema alheio.
#
# O diretorio e sobrescrivivel so para teste, mesma costura de DOCKER_APP_PATH.
# As preferencias do Docker Desktop que ESTA instalacao precisa. Duas, e as duas
# tem motivo:
#
#   enableIntegrationWithDefaultWslDistro  - e o que faz o `docker` existir
#     DENTRO da distro. Nem sempre vem ligada apos uma instalacao nova: num
#     Windows 11 real o instalador parou pedindo um clique em
#     Settings > Resources > WSL Integration.
#
#   displayedOnboarding - tira o questionario de boas-vindas do caminho. Chave
#     DOCUMENTADA pela Docker. A tela de LOGIN continua aparecendo, e de
#     proposito: nao ha chave documentada para ela, e inventar uma sobre esquema
#     alheio e o tipo de palpite que este projeto nao da. Ela tambem nao bloqueia
#     nada - o instalador espera o daemon, nao o usuario.
#
# Docker Desktop guarda isso em %APPDATA%\Docker. O nome do arquivo mudou na
# versao 4.35 (settings.json -> settings-store.json), entao os dois sao
# tentados, nessa ordem. E formato INTERNO: se o arquivo nao for JSON valido,
# isto NAO derruba a instalacao - cai na espera e na mensagem manual que ja
# existiam.
#
# Devolve $true quando MUDOU alguma coisa, que e quando vale reiniciar o Docker.
#
# O diretorio e sobrescrivivel so para teste, mesma costura de DOCKER_APP_PATH.
function Set-AfDockerSetting {
    $base = $env:ATLASFILE_DOCKER_SETTINGS_DIR
    if (-not $base) { $base = Join-Path $env:APPDATA "Docker" }
    $desejadas = @{ "enableIntegrationWithDefaultWslDistro" = $true
                    "displayedOnboarding"                   = $true }

    $alvo = ""
    foreach ($nome in @("settings-store.json", "settings.json")) {
        $arq = Join-Path $base $nome
        if (Test-Path $arq) { $alvo = $arq; break }
    }

    # Nenhum dos dois existe. Foi o que aconteceu num Windows 11 real: numa
    # instalacao RECEM-FEITA o Docker ainda nao escreveu suas preferencias, a
    # funcao desistia calada e o instalador parou pedindo um clique no menu.
    # Criar o arquivo aqui e seguro justamente porque nao ha preferencia
    # nenhuma para perder.
    if (-not $alvo) {
        if (-not (Test-Path $base)) {
            try { New-Item -ItemType Directory -Path $base -Force | Out-Null }
            catch { Write-Verbose "cannot create $base : $($_.Exception.Message)"; return $false }
        }
        $alvo = Join-Path $base "settings-store.json"
        try { "{}" | Set-Content $alvo -Encoding UTF8 -ErrorAction Stop }
        catch { Write-Verbose "cannot create $alvo : $($_.Exception.Message)"; return $false }
    }

    try { $cfg = Get-Content $alvo -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop }
    catch { Write-Verbose "cannot read $alvo : $($_.Exception.Message)"; return $false }
    if ($null -eq $cfg) { $cfg = New-Object PSObject }

    $mudou = $false
    foreach ($chave in $desejadas.Keys) {
        if ($cfg.PSObject.Properties[$chave] -and $cfg.$chave -eq $desejadas[$chave]) { continue }
        if ($cfg.PSObject.Properties[$chave]) { $cfg.$chave = $desejadas[$chave] }
        else { $cfg | Add-Member -NotePropertyName $chave -NotePropertyValue $desejadas[$chave] -Force }
        $mudou = $true
    }
    if (-not $mudou) { return $false }

    try { $cfg | ConvertTo-Json -Depth 32 | Set-Content $alvo -Encoding UTF8 -ErrorAction Stop }
    catch { Write-Verbose "cannot write $alvo : $($_.Exception.Message)"; return $false }
    return $true
}

# A mudanca so vale depois que o Docker Desktop reinicia - e o mesmo que o
# botao "Apply & Restart" da tela de Settings faz.
function Restart-AfDockerDesktop {
    Get-Process "Docker Desktop" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $exe) { Start-Process $exe }
}

# Os documentos do usuario, em caminho que a DISTRO entende.
#
# Sem isto o install.sh usava o default dele ($HOME/Documents/AtlasFileProjects)
# e, como a distro nao inicializada nos faz rodar como root, os documentos
# nasciam em /root/Documents/AtlasFileProjects - dentro da distro. Fora de
# qualquer pasta normal do Explorer, e some junto se alguem fizer
# `wsl --unregister`, que o nosso --uninstall nao controla.
#
# GetFolderPath e nao "$env:USERPROFILE\Documents": num Windows em portugues a
# pasta chama Documentos, e com OneDrive ela e redirecionada. So a API sabe.
#
# wslpath faz a conversao (C:\Users\x -> /mnt/c/Users/x). Se ele falhar, a
# traducao manual cobre o caso comum; se as duas falharem, devolve vazio e o
# instalador segue com o default do install.sh, sem quebrar por causa disto.
# Caminho do Windows -> caminho que a DISTRO entende. wslpath e a ferramenta
# canonica; se ela falhar, a traducao manual cobre o caso comum (C:\x -> /mnt/c/x)
# e, se as duas falharem, devolve vazio para o chamador seguir com o default.
function ConvertTo-AfWslPath([string]$Caminho) {
    if (-not $Caminho) { return "" }
    if ($Caminho.StartsWith("/")) { return $Caminho }   # ja e caminho da distro

    # Conversao LEXICA primeiro: C:\x\y -> /mnt/c/x/y. E a regra do automount do
    # WSL, e o resultado nao depende de estado nenhum da maquina.
    #
    # O wslpath era a primeira escolha e, numa REINSTALACAO real, devolveu
    #   /mnt/wsl/docker-desktop-bind-mounts/Ubuntu/60c0eb2a1c49...
    # para a pasta de documentos - um ponto de montagem que o Docker Desktop
    # tinha criado, e nao a pasta. Onde ficam os documentos de alguem nao pode
    # depender do que estava montado no instante da instalacao.
    if ($Caminho -match '^([A-Za-z]):\\(.*)$') {
        return ("/mnt/" + $Matches[1].ToLower() + "/" + ($Matches[2] -replace '\\', '/'))
    }

    # Sobra o que nao e caminho de unidade (UNC, por exemplo). Ai o wslpath e a
    # unica saida, e o chamador confere o resultado.
    try {
        $argsPath = @($script:WslUser) + @("-e", "wslpath", "-a", $Caminho)
        $convertido = ((& (Resolve-ToolPath wsl) @argsPath 2>$null) | Out-String).Trim()
        if ($convertido -and $convertido.StartsWith("/")) { return $convertido }
    } catch { Write-Verbose "wslpath failed: $($_.Exception.Message)" }
    return ""
}

# Um caminho da DISTRO virando argumento seguro para `bash -c`.
#
# Os dois requisitos brigam entre si e por isso a funcao existe:
#   - ESPACO so sobrevive DENTRO de aspas. Sem elas, "C:\Users\Joao Silva" chega
#     ao install.sh partido em varios argumentos e ele instala no lugar errado.
#   - TIL so expande FORA de aspas simples. E o manifesto guarda literalmente
#     "~/AtlasFile" (Set-AfState "install_dir"), entao um --dir '~/AtlasFile'
#     faria o install.sh procurar uma pasta chamada "~" - a desinstalacao nao
#     acharia instalacao nenhuma.
#
# Aspas DUPLAS atendem os dois: elas seguram o espaco e ainda expandem $HOME.
# Entao o til vira $HOME aqui, antes de sair. O crase escapa o $ para o
# PowerShell nao interpolar o $HOME DELE, que e o do Windows.
#
# O que o bash ainda expandiria dentro de aspas duplas ($ ` " \) e escapado
# antes, senao um caminho com $ viraria outra coisa no meio do caminho.
function ConvertTo-AfShArg([string]$Caminho) {
    # Caminho SIMPLES viaja NU, que e exatamente como a v0.56.0 ja o mandava e
    # como foi validado em maquina real: o bash expande o `~` sozinho e nao ha
    # espaco para proteger. Citar tudo por precaucao teria dois precos — o til
    # deixaria de expandir e a linha ganharia escapes (`\"`) que so poluem.
    if ($Caminho -match '^[A-Za-z0-9_./~-]+$') { return $Caminho }

    # Sobrou o que PRECISA de aspas (espaco, sobretudo). Aspas DUPLAS e nao
    # simples porque elas seguram o espaco E deixam o $HOME expandir: com aspas
    # simples o til morreria, e o manifesto grava literalmente "~/AtlasFile" —
    # o install.sh iria procurar uma pasta chamada "~".
    $v = $Caminho -replace '([\\"$`])', '\$1'
    if ($v -eq '~') { $v = "`$HOME" }
    elseif ($v.StartsWith('~/')) { $v = "`$HOME" + $v.Substring(1) }
    return '"' + $v + '"'
}

function Get-AfProjectsRoot {
    $doc = ""
    try { $doc = [Environment]::GetFolderPath('MyDocuments') } catch { $doc = "" }
    if (-not $doc) { $doc = Join-Path $env:USERPROFILE "Documents" }
    if (-not $doc) { return "" }
    $alvo = Join-Path $doc "AtlasFileProjects"
    $convertido = ConvertTo-AfWslPath $alvo

    # CONFERE antes de entregar. Uma traducao que perde o nome da pasta nao e
    # uma traducao daquela pasta - foi assim que os documentos do usuario foram
    # parar num ponto de montagem do Docker. Se nao bater, devolve vazio e o
    # install.sh usa o padrao dele, que e conhecido e explicavel.
    if (-not $convertido.EndsWith("/AtlasFileProjects")) {
        Write-Verbose "unexpected translation for '$alvo': '$convertido' - falling back to the Linux default"
        return ""
    }
    return $convertido
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
# Cometa: cabeca BRANCA e tres celulas de cauda, os mesmos do install.sh
# (AF_COMET_HEAD_HEX / AF_COL_C1..C3 / AF_COMET_TAIL). A cabeca era "ffd0c4" e a
# cauda tinha quatro celulas - dois pixels diferentes no mesmo desenho.
$AF_COMET_HEAD_HEX = "ffffff"
$AF_COMET_TAIL_HEX = @("ff8a6b", "ff5a36", "b23f26")
$AF_COMET_TAIL = 3
# Quantizacao do degrade do orbe: o install.sh monta uma LUT de 32 passos e
# indexa nela, e sao esses degraus que dao a textura da esfera. Interpolar
# continuo aqui daria um degrade liso ao lado de um bandado.
$AF_LUT_N = 32
$AF_IGNITE = 5
$AF_ORBIT_FRAMES = 12
# 10, o MESMO do install.sh (AF_ORBIT_START). Com 2 as duas luas trocavam de
# lugar em relacao ao bash - as posicoes eram as mesmas, mas a laranja aparecia
# onde a roxa devia estar. Medido: (10 + AF_LAST - AF_IGNITE) % 16 = 14, que e
# exatamente o indice de repouso abaixo.
$AF_ORBIT_START = 10
$AF_ORBIT_REST = 14
$AF_DELAY_MS = 45

# Hex da rampa -> escape de 24 bits. A mesma conversao estava escrita a mao no
# Write-AfGrid e no Show-AfBar; com a regua seria a terceira copia.
function Get-AfEsc([string]$Hex) {
    $r = [Convert]::ToInt32($Hex.Substring(0, 2), 16)
    $g = [Convert]::ToInt32($Hex.Substring(2, 2), 16)
    $b = [Convert]::ToInt32($Hex.Substring(4, 2), 16)
    return ([char]27 + "[38;2;$r;$g;${b}m")
}

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
                if ($cor) { $linha += (Get-AfEsc $cor) } else { $linha += "$esc[0m" }
                $corAtual = $cor
            }
            $linha += $Grid.G[$r, $c]
        }
        # ESC[K apaga ate o fim da linha. Sem isto a lua que sai pela direita
        # deixa RASTRO: as colunas que ela ocupava nao sao repintadas, porque a
        # linha e cortada na ultima coluna com conteudo. Medido no Windows 11
        # real. O install.sh nao tem o problema porque emite todas as colunas,
        # inclusive as vazias.
        Write-Host ($linha + "$esc[0m" + "$esc[K")
    }
}

# Um quadro: orbe com brilho especular varrendo, duas luas em oposicao, cometa
# com cauda e o texto revelado pela passagem dele.
function New-AfFrame([int]$N, [int]$Total) {
    $grid = New-AfGrid

    # A ORDEM DE ESCRITA E A PRECEDENCIA, e ela e a mesma do af_row_cells do
    # install.sh: cometa < orbe < texto < luas. E o que faz o cometa parecer
    # SAIR DE TRAS do orbe - a celula de cauda que cai sobre uma coluna do orbe
    # e coberta por ele. Aqui o cometa era desenhado por ULTIMO e passava por
    # cima: no quadro 17 a cauda apagava o `▀` da linha 4, coluna 14, que no
    # bash continua sendo orbe.
    $tri = $N % 20; if ($tri -gt 10) { $tri = 20 - $tri }
    $hlCol = 5 + $tri

    # --- 1. cometa, e a revelacao que a passagem dele dispara ---------------
    # O QUADRO FINAL NAO TEM COMETA (no install.sh, `n < AF_LAST`).
    $primeiroCometa = $AF_IGNITE + $AF_ORBIT_FRAMES
    $revelaAteCol = -1
    if ($N -ge $primeiroCometa -and $N -lt ($primeiroCometa + $AF_COMET.Count)) {
        $j = $N - $primeiroCometa
        $hr = $AF_COMET[$j][0]; $hc = $AF_COMET[$j][1]
        $grid.G[$hr, $hc] = $MOON_NEAR
        $grid.C[$hr, $hc] = $AF_COMET_HEAD_HEX
        # Cauda CONTIGUA atras da cabeca, na direcao do movimento. Amostrar as
        # celulas anteriores do TRAJETO - que era o que se fazia aqui - deixa
        # vaos de 3 a 5 colunas e le como faisca, nao como cometa. O install.sh
        # registra essa forma como medida e REJEITADA; este lado a usava.
        if ($j -gt 0) { $pr = $AF_COMET[$j - 1][0]; $pc = $AF_COMET[$j - 1][1] }
        else          { $pr = $hr;                  $pc = $hc - 1 }
        $dcol = $hc - $pc; $drow = $hr - $pr
        if ($dcol -le 0) { $dcol = 1 }
        for ($t = 1; $t -le $AF_COMET_TAIL; $t++) {
            $tc = $hc - $t
            if ($tc -lt 0) { break }
            # Truncate e nao [int]: o cast do PowerShell arredonda (e arredonda
            # para o par), o bash trunca em direcao ao zero. Com $drow negativo
            # - o cometa SOBE - os dois dao linhas diferentes.
            $tr = $hr - [int][Math]::Truncate(($drow * $t) / $dcol)
            if ($tr -lt 0) { $tr = 0 }
            if ($tr -ge $AF_ROWS) { $tr = $AF_ROWS - 1 }
            $grid.G[$tr, $tc] = $DOT
            $grid.C[$tr, $tc] = $AF_COMET_TAIL_HEX[$t - 1]
        }
        # A revelacao conta CARACTERES, nao colunas: no install.sh sao
        # `hc - AF_WORD_COL` letras. Passando `hc` como ultima coluna permitida
        # aparecia sempre uma letra a mais do que no outro lado.
        $revelaAteCol = $hc - 1
    }
    if ($N -eq $Total - 1) { $revelaAteCol = $AF_COLS }

    # --- 2. orbe, com o brilho especular ------------------------------------
    $arte = @(
        @{ Row = 1; Col = 8;  Glifos = (, $BLK_LO * 5) },
        @{ Row = 2; Col = 6;  Glifos = @($BLK_LO) + (, $BLK_FU * 7) + @($BLK_LO) },
        @{ Row = 3; Col = 5;  Glifos = @($BLK_RT) + (, $BLK_FU * 9) + @($BLK_LF) },
        @{ Row = 4; Col = 6;  Glifos = @($BLK_UP) + (, $BLK_FU * 7) + @($BLK_UP) },
        @{ Row = 5; Col = 8;  Glifos = (, $BLK_UP * 5) }
    )
    # Ignicao: o orbe ocupa as linhas 1..5 e nasce de dentro para fora. O
    # install.sh revela `row < n+2`; aqui era `row <= n+2`, uma linha adiantada
    # em cada um dos cinco quadros de ignicao.
    $revelaAte = if ($N -lt $AF_IGNITE) { $N + 2 } else { $AF_ROWS }
    foreach ($a in $arte) {
        if ($a.Row -ge $revelaAte) { continue }
        for ($i = 0; $i -lt $a.Glifos.Count; $i++) {
            $col = $a.Col + $i
            # A MESMA formula do install.sh: queda de 90 por coluna e 180 por
            # linha a partir do ponto de luz (linha 2, nao 3), piso em 120, e o
            # resultado quantizado nos 32 degraus da LUT. A formula anterior era
            # outra (distancia de Manhattan sobre 11, centrada na linha 3) e
            # sombreava a esfera de um jeito que o outro lado nunca produz.
            $p = 1000 - [Math]::Abs($col - $hlCol) * 90 - [Math]::Abs($a.Row - 2) * 180
            if ($p -lt 120) { $p = 120 }
            $degrau = [int][Math]::Floor($p * ($AF_LUT_N - 1) / 1000)
            $posLut = [Math]::Floor($degrau * 1000 / ($AF_LUT_N - 1)) / 1000.0
            $grid.G[$a.Row, $col] = $a.Glifos[$i]
            $grid.C[$a.Row, $col] = Get-AfRampHex $posLut
        }
    }

    # --- 3. texto revelado pela passagem do cometa --------------------------
    if ($revelaAteCol -ge 0) {
        Set-AfText $grid 2 24 "AtlasFile" "ff5a36" $revelaAteCol
        Set-AfText $grid 3 24 "Your documents have gravity." "8a8a8a" $revelaAteCol
        # Divergencia DELIBERADA, decidida pelo dono do projeto: o lado Windows
        # identifica a plataforma. E a unica linha que o install.sh nao tem, e a
        # guarda de paridade de quadros a perdoa explicitamente (e cobra que ela
        # continue existindo).
        Set-AfText $grid 4 23 "(Windows / WSL2)" "8a8a8a" $revelaAteCol
    }

    # --- 4. luas, por cima de tudo ------------------------------------------
    # A orbita avanca em TODO quadro a partir da ignicao, inclusive durante o
    # voo do cometa - e o que o install.sh faz. Aqui elas congelavam no indice
    # de repouso assim que o cometa saia, e so o quadro FINAL coincidia: por
    # isso a guarda do indice de repouso passava com as luas paradas.
    $idx = $AF_ORBIT_REST
    if ($N -ge $AF_IGNITE) {
        $idx = ($AF_ORBIT_START + ($N - $AF_IGNITE)) % $AF_ORBIT.Count
        # Glifo pela LINHA (a lua do lado de tras e menor e mais escura) e cor
        # POR LUA - a regra do af_row_cells do install.sh.
        $m1 = $AF_ORBIT[$idx]
        $m2 = $AF_ORBIT[($idx + 8) % $AF_ORBIT.Count]
        if ($m1[0] -le 2) { $g1 = $MOON_FAR;  $c1 = "b23f26" } else { $g1 = $MOON_NEAR; $c1 = "ff5a36" }
        if ($m2[0] -le 2) { $g2 = $MOON_FAR;  $c2 = "8d56b2" } else { $g2 = $MOON_NEAR; $c2 = "c97bff" }
        $grid.G[$m1[0], $m1[1]] = $g1; $grid.C[$m1[0], $m1[1]] = $c1
        $grid.G[$m2[0], $m2[1]] = $g2; $grid.C[$m2[0], $m2[1]] = $c2
    }
    return $grid
}

# Seam de teste, no mesmo espirito de ATLASFILE_FORCE_ANIM/ATLASFILE_FAKE_MISSING:
# despeja os quadros do banner em TEXTO PURO e sai. E o equivalente exato do
# af_frame_plain do install.sh.
#
# Existe porque a paridade de arte comparava as TABELAS (orbita, cometa, rampa,
# hexes) e nunca o DESENHO que elas produzem. Quatro divergencias viviam
# justamente nos algoritmos que consomem essas tabelas - cauda do cometa, luas
# durante o voo, ignicao e brilho especular - e passavam verdes por ela.
#
# Variavel de ambiente e nao parametro: um parametro entraria no param() e a
# guarda de ajuda cobraria que ele aparecesse no Show-Usage, poluindo a ajuda
# publica com um gancho de bancada.
if ($env:ATLASFILE_DUMP_FRAMES -eq "1") {
    $totalDump = $AF_IGNITE + $AF_ORBIT_FRAMES + $AF_COMET.Count + 1
    for ($nd = 0; $nd -lt $totalDump; $nd++) {
        $gd = (New-AfFrame $nd $totalDump).G
        for ($rd = 0; $rd -lt $AF_ROWS; $rd++) {
            $linhaDump = ""
            for ($cd = 0; $cd -lt $AF_COLS; $cd++) { $linhaDump += $gd[$rd, $cd] }
            [Console]::Out.WriteLine($linhaDump.TrimEnd())
        }
    }
    Stop-Installer 0; return
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


# AF-INICIO-DO-TRILHO: daqui para baixo tudo que vai a tela pendura na calha,
# ate a marca AF-FIM-DO-TRILHO la embaixo. O banner fica ACIMA desta marca de
# proposito: ele emoldura a arte com linhas vazias e e desenhado antes de o
# trilho existir. A bancada varre exatamente esta faixa.
#
# --- UI: mesma gramatica visual do install.sh (fases, passos, painel) -------
# A calha vertical, a regua de fase, a barra viva e o placar sao os MESMOS do
# install.sh, que por sua vez os tomou do mac_env_install.sh. Dois instaladores
# com duas gramaticas visuais foi um dos defeitos deste ciclo, nao uma escolha.
$script:PhaseTotal = 3
$script:StepStart = $null
$BOX_V   = [string][char]0x2502   # |
$BOX_H   = [string][char]0x2500   # -
$BOX_T   = [string][char]0x251C   # |-
# U+2588/U+2591 (Block Elements) no lugar de U+25B0/U+25B1 (Geometric Shapes).
# Medido num Windows 11 real: o console renderiza a calha, as reguas e os
# mas os paralelogramos saem como [?] - a fonte do console nao os tem. Block
# Elements estao no CP437 e em toda fonte de console.
#
# Divergencia DELIBERADA e restrita a este par, decidida pelo dono do projeto:
# no macOS e no Linux o par U+25B0/U+25B1 renderiza e fica melhor, entao
# muda-lo la seria piorar o que funciona. O resto da UI segue identico.
$BAR_ON  = [string][char]0x2588   # bloco cheio
$BAR_OFF = [string][char]0x2591   # bloco vazio
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
    # Sem fase nao ha barra. No uninstall, no doctor e no dry-run ela aparecia
    # como "fase 0/3" - ruido puro. Mesma guarda do bar_show do install.sh.
    if ($script:BarDone -le 0) { return }
    $largura = 24
    $cheio = [int]($script:BarDone * $largura / $script:PhaseTotal)
    $esc = [char]27
    $linha = ""
    for ($i = 0; $i -lt $largura; $i++) {
        if ($i -lt $cheio) {
            $linha += (Get-AfEsc (Get-AfRampHex ([double]$i / [Math]::Max(1, $largura - 1)))) + $BAR_ON
        } else {
            $linha += "$esc[38;5;240m$BAR_OFF"
        }
    }
    # Na CALHA, como o bar_render do install.sh. Dois espacos crus deixavam a
    # barra flutuando ao lado do trilho em vez de pendurada nele - e ela e a
    # linha que fica VIVA na tela, entao o desalinhamento ficava permanente.
    Write-Host $script:Gut -ForegroundColor DarkGray -NoNewline
    Write-Host ($linha + "$esc[0m " + "fase $($script:BarDone)/$($script:PhaseTotal)") -NoNewline
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
    # Uma linha de calha, nunca uma linha VAZIA: linha vazia abre um buraco no
    # trilho. E o padrao do mac_env_install.sh (`echo -e "${GUT}"`) e o mesmo do
    # install.sh - o Write-Host "" que ficava aqui divergia das duas telas.
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
# Largura da regua, identica a do install.sh: o conector ocupa 4 colunas, o
# cabecalho as dele, mais um espaco, e os tracos completam ate a largura. Toda
# regua termina na MESMA coluna, independente do tamanho do texto - que era o
# zelo do mac_env_install.sh que faltava nos dois lados.
$AF_RULE_COLS = 4
function Get-AfRuleWidth {
    $largura = 80
    # Host sem RawUI (sessao redirecionada, ISE, runspace) nao tem largura para
    # dar: a regua cai na largura padrao e a instalacao segue.
    try {
        $w = $Host.UI.RawUI.WindowSize.Width
        if ($w -gt 40) { $largura = [Math]::Max(60, [Math]::Min(92, $w - 1)) }
    } catch { Write-Verbose "console width unavailable: $($_.Exception.Message)" }
    return $largura
}

# O conector E a calha, nao vem depois dela - no install.sh vale o mesmo.
# A regua VARRE a rampa do produto, como o rule_sweep do install.sh - mesmas
# posicoes, mesma segmentacao. Antes eram tres cores fixas de 16 (DarkGray,
# White, DarkYellow) e as duas metades da tela nao pareciam o mesmo produto;
# com a largura ja igualada, isto fecha o handover.
#
# A rampa nao e nova: Get-AfRampHex ja pinta o banner e a barra de fase. O que
# faltava era a regua usar o que ja existia.
#
# UMA string com os escapes embutidos, e nao 90 Write-Host coloridos: e a mesma
# tecnica do Write-AfGrid, e evita piscada numa linha desenhada ~10 vezes por
# execucao.
#
# Oito segmentos nos tracos, como o bash. La a razao e tecnica (o traco e
# multibyte e nao pode ser fatiado por indice); aqui daria para pintar caractere
# a caractere, mas um degrade liso ao lado de um segmentado seria justamente a
# costura que este trabalho remove.
$AF_RULE_SEGS = 8
function Write-Rule([string]$Cabecalho) {
    $largura = Get-AfRuleWidth
    $tracos = $largura - $Cabecalho.Length - $AF_RULE_COLS - 1
    if ($tracos -lt 4) { $tracos = 4 }

    if (-not $AfTrueColor -or $AfPlain) {
        Write-Host ($BOX_T + ($BOX_H * 2) + " ") -ForegroundColor DarkGray -NoNewline
        Write-Host $Cabecalho -ForegroundColor White -NoNewline
        Write-Host (" " + ($BOX_H * $tracos)) -ForegroundColor DarkYellow
        return
    }

    $esc = [char]27
    $vao = [Math]::Max(1, $Cabecalho.Length + $tracos - 1)
    $linha = (Get-AfEsc (Get-AfRampHex 0)) + $BOX_T + ($BOX_H * 2) + " "
    for ($i = 0; $i -lt $Cabecalho.Length; $i++) {
        $linha += (Get-AfEsc (Get-AfRampHex ([double]$i / $vao))) + $Cabecalho[$i]
    }
    $linha += " "
    for ($i = 0; $i -lt $AF_RULE_SEGS; $i++) {
        $ini = [int]($i * $tracos / $AF_RULE_SEGS)
        $fim = [int](($i + 1) * $tracos / $AF_RULE_SEGS)
        $n = $fim - $ini
        if ($n -le 0) { continue }
        $linha += (Get-AfEsc (Get-AfRampHex ([double]($Cabecalho.Length + $ini) / $vao))) + ($BOX_H * $n)
    }
    Write-Host ($linha + "$esc[0m")
}

# O ambiente que a outra metade precisa para desenhar IGUAL a esta.
#
# Nada disso atravessa o wsl.exe sozinho, e sem esses tres o install.sh se
# degrada em silencio: sem COLORTERM ele desiste do degrade (reguas brancas),
# sem TERM ele desiste da cor inteira, e sob captura - que e como a
# desinstalacao roda, para ler o plano e a sentinela - `[ -t 1 ]` e falso e a
# tela sai toda branca. Quem sabe do que o console e capaz e ESTE lado.
#
# Anunciar truecolor sem ter seria mentir para o outro lado, entao vai preso ao
# $AfTrueColor - que e medido, nao presumido.
function Get-AfEnvPrefix {
    $partes = @("COLUMNS=$(Get-AfRuleWidth)")
    if ($AfTrueColor -and -not $AfPlain) {
        $partes += @("TERM=xterm-256color", "COLORTERM=truecolor", "ATLASFILE_FORCE_COLOR=1")
    }
    return ("export " + ($partes -join " ") + "; ")
}

# A divisoria do HANDOVER: onde este instalador entrega ao do Linux.
#
# Tracejada e rotulada de proposito - ela NAO e uma fase, e parecer uma seria
# pior do que nao existir. Continua pendurada na calha, entao o trilho atravessa
# a fronteira inteiro em vez de recomecar do outro lado.
$BOX_DASH = [string][char]0x2504
function Write-Handover([string]$Rotulo) {
    $largura = Get-AfRuleWidth
    $texto = " " + $Rotulo + " "
    $antes = 4
    $depois = $largura - 1 - $antes - $texto.Length
    if ($depois -lt 4) { $depois = 4 }

    if (-not $AfTrueColor -or $AfPlain) {
        Write-Host ($BOX_T + ($BOX_DASH * $antes) + $texto + ($BOX_DASH * $depois)) -ForegroundColor DarkYellow
        return
    }
    $vao = [Math]::Max(1, $antes + $texto.Length + $depois - 1)
    $linha = (Get-AfEsc (Get-AfRampHex 0)) + $BOX_T + ($BOX_DASH * $antes)
    for ($i = 0; $i -lt $texto.Length; $i++) {
        $linha += (Get-AfEsc (Get-AfRampHex ([double]($antes + $i) / $vao))) + $texto[$i]
    }
    for ($i = 0; $i -lt $AF_RULE_SEGS; $i++) {
        $ini = [int]($i * $depois / $AF_RULE_SEGS)
        $fim = [int](($i + 1) * $depois / $AF_RULE_SEGS)
        $n = $fim - $ini
        if ($n -le 0) { continue }
        $linha += (Get-AfEsc (Get-AfRampHex ([double]($antes + $texto.Length + $ini) / $vao))) + ($BOX_DASH * $n)
    }
    Write-Host ($linha + [char]27 + "[0m")
}

# Fecha o TRILHO: linha de calha, o fechamento e a folga antes do que vem fora
# dele. Espelho do rail_end do install.sh. O -Doctor ABRIA o trilho com `+--` e
# nunca o fechava, exatamente como o --doctor do outro lado.
function Close-AfRail {
    Write-Host ($script:Gut) -ForegroundColor DarkGray
    Write-RuleClose
    Write-Host ""
}

# Fecha o bloco, como o fechamento do install.sh e do mac-env.
function Write-RuleClose {
    $largura = Get-AfRuleWidth
    $fecha = [string][char]0x2570 + ($BOX_H * ($largura - 1))
    if (-not $AfTrueColor -or $AfPlain) {
        Write-Host $fecha -ForegroundColor DarkYellow
        return
    }
    # Cor UNICA no fim da rampa, como o rule_close do install.sh: o fechamento
    # e o ponto de chegada da varredura, nao uma varredura nova.
    Write-Host ((Get-AfEsc (Get-AfRampHex 1)) + $fecha + [char]27 + "[0m")
}

# Mensagem FORA da calha: depois que o trilho fecha, o relatorio final nao pode
# continuar pendurado nele.
function Write-Note([string]$Texto, [string]$Cor = "Gray") {
    Write-Host ("  " + $Texto) -ForegroundColor $Cor
}

function Start-Step([string]$Texto) {
    $script:StepStart = Get-Date
    Clear-AfBar
    Write-Gut ("{0} {1}..." -f $DOT, $Texto) DarkGray
}
function Format-Elapsed {
    if (-not $script:StepStart) { return "" }
    $s = [int]((Get-Date) - $script:StepStart).TotalSeconds
    $script:StepStart = $null
    if ($s -ge 60) { return (" ({0}m{1:d2}s)" -f [int]($s / 60), ($s % 60)) }
    return " (${s}s)"
}
# Quebra na largura do trilho, reprefixando a CALHA - espelho do af_wrap do
# install.sh, ate na fonte de largura (Get-AfRuleWidth, a mesma que desenha as
# reguas). Sem isto a continuacao de uma mensagem longa saia sem `|` e o trilho
# ficava furado, que foi o defeito visto numa desinstalacao real no macOS.
function Split-AfWrap([string]$Texto, [int]$Util) {
    $linhas = @(); $linha = ""
    foreach ($palavra in ($Texto -split '\s+')) {
        if ($palavra -eq "") { continue }
        if ($linha -eq "") { $linha = $palavra }
        elseif (($linha.Length + 1 + $palavra.Length) -le $Util) { $linha = "$linha $palavra" }
        else { $linhas += $linha; $linha = $palavra }
    }
    $linhas += $linha
    return ,$linhas
}
function Write-Wrapped([string]$Glifo, [string]$Texto, [string]$Cor) {
    $util = [Math]::Max(20, (Get-AfRuleWidth) - 4)
    $linhas = Split-AfWrap $Texto $util
    for ($i = 0; $i -lt $linhas.Count; $i++) {
        Write-Host $script:Gut -ForegroundColor DarkGray -NoNewline
        if ($i -eq 0) {
            # So o GLIFO recebe a cor. O texto fica na cor padrao, como o ok()
            # do install.sh e o do mac_env_install.sh: a cor significa ESTADO, e
            # pintar a frase inteira faz o verde competir com o conteudo dela.
            # As duas telas divergiam justamente aqui.
            Write-Host $Glifo -ForegroundColor $Cor -NoNewline
            Write-Host (" " + $linhas[$i])
        } else {
            Write-Host ("  " + $linhas[$i])
        }
    }
}
function Write-Ok([string]$Texto)   { Clear-AfBar; Write-Wrapped $OK ("{0}{1}" -f $Texto, (Format-Elapsed)) Green; Show-AfBar }
function Write-Info([string]$Texto) { Clear-AfBar; Write-Wrapped $DOT $Texto DarkGray; Show-AfBar }
function Write-Warn([string]$Texto) { Clear-AfBar; Write-Wrapped "!" $Texto DarkYellow; Show-AfBar }
function Write-Fail([string]$Texto) { Clear-AfBar; Write-Wrapped $BAD $Texto Red }
# A caixa CRESCE com o conteudo. Antes tinha largura fixa de 57 e o comando do
# WSL vazava por fora dela, num Windows 11 real. O install.sh nao vaza porque
# TRUNCA o valor com reticencias, mas truncar um comando o tornaria incopiavel -
# e comando existe para ser copiado. Piso de 57 para casar com a caixa do outro
# instalador quando o conteudo e curto.
function Write-Panel([string[]]$Linhas) {
    $largura = 55
    foreach ($l in $Linhas) { if ($l.Length -gt $largura) { $largura = $l.Length } }
    Write-Host ""
    Write-Host ("  " + [char]0x256D + ([string][char]0x2500) * ($largura + 2) + [char]0x256E) -ForegroundColor DarkYellow
    foreach ($l in $Linhas) {
        Write-Host ("  " + [char]0x2502) -ForegroundColor DarkYellow -NoNewline
        Write-Host ("  " + $l.PadRight($largura)) -NoNewline
        Write-Host ([char]0x2502) -ForegroundColor DarkYellow
    }
    Write-Host ("  " + [char]0x2570 + ([string][char]0x2500) * ($largura + 2) + [char]0x256F) -ForegroundColor DarkYellow
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
# ZERA a cada execucao. O caminho e fixo (o install.sh usa um arquivo por
# execucao, e por isso nunca teve isto), entao sem truncar o "last lines of"
# mostrava a saida de execucoes ANTERIORES. Numa maquina real isso pos, logo
# abaixo de "Nothing was removed", a prova de um winget uninstall bem-sucedido
# de OUTRA execucao. Diagnostico com evidencia de outro dia e pior que nenhum.
try {
    [IO.File]::WriteAllText($script:AfLog,
        "AtlasFile install.ps1 - " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + [Environment]::NewLine,
        (New-Object Text.UTF8Encoding $false))
} catch { Write-Verbose "could not reset the log: $($_.Exception.Message)" }
# Placar e relatorio da execucao, como no install.sh: o log guarda a saida das
# FERRAMENTAS, e o que o instalador fez nao ficava em lugar nenhum.
$script:TrilhoFechadoNoWsl = $false
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

# UTF-8 SEM BOM e explicito. Add-Content sem -Encoding grava com a code page
# ANSI no PowerShell 5.1, e a calha que vem do WSL virava lixo dentro do proprio
# log - o "last lines" saiu com barras quebradas na tela do usuario.
function Add-AfLog([string]$Texto) {
    try {
        [IO.File]::AppendAllText($script:AfLog, $Texto + [Environment]::NewLine,
                                 (New-Object Text.UTF8Encoding $false))
    } catch { Write-Verbose "log write failed: $($_.Exception.Message)" }
}

function Write-LogSection([string]$Titulo, [string[]]$Arquivos) {
    Add-AfLog ("=== " + $Titulo + " ===")
    foreach ($f in $Arquivos) {
        if (Test-Path $f) {
            $texto = Get-AfText $f
            if ($texto) { Add-AfLog $texto }
        }
    }
}

# Ultimas linhas do log quando algo falha: sem isto, esconder a saida de terceiro
# transformaria uma falha em misterio. E o fail_with_log do install.sh.
function Show-LogTail([int]$Linhas = 15) {
    if (-not (Test-Path $script:AfLog)) { return }
    Write-Gut ("  last lines of $script:AfLog") DarkGray
    foreach ($l in (Get-Content $script:AfLog -Tail $Linhas -ErrorAction SilentlyContinue)) {
        Write-Gut ("  | " + $l) DarkGray
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
        Write-Gut ("{0} {1}..." -f $DOT, $Label) DarkGray
        $tv = Get-Date
        Invoke-Native $File $Arguments
        if ($script:NativeExitCode -eq 0) {
            Write-Gut ("{0} {1} ({2})" -f $OK, $Label, (Format-Since $tv)) Green
            } else {
            Write-Gut ("{0} {1} (exit {2})" -f $BAD, $Label, $script:NativeExitCode) Red
            $script:StepsFailed++
        }
        # Linha de CALHA, nao linha vazia: em -Verbose a saida da ferramenta
        # acabou de inundar a tela e o respiro ajuda, mas vazia ele e um buraco
        # no trilho. O Write-Gut acima ja quebrou a linha.
        Write-Gut ""
        return
    }
    $fOut = [IO.Path]::GetTempFileName()
    $fErr = [IO.Path]::GetTempFileName()
    $t0 = Get-Date
    # Na calha, como o ramo sem TTY do run_step do install.sh.
    if (-not $script:AfAnim) { Write-Gut ("{0} {1}..." -f $DOT, $Label) DarkGray }
    try {
        # CONSOLE PROPRIO (escondido) em vez de -NoNewWindow. Redirecionar
        # stdout/stderr so alcanca o FILHO: o desinstalador do Docker Desktop se
        # relanca do TEMP (--remove-self --relaunch-from-temp) e o NETO escreve
        # direto em CONOUT$, que nenhum redirecionamento do pai captura.
        #
        # Isso estava previsto como inferencia no diagnostico deste ciclo e foi
        # MEDIDO agora: o log inteiro do desinstalador do Docker vazou por cima
        # do spinner, com o spinner desenhando \r no meio das linhas dele. Com um
        # console proprio o neto escreve LA, e a nossa tela fica intacta.
        #
        # A saida do filho continua indo para os arquivos, entao o log da
        # execucao nao perde nada.
        $proc = Start-Process -FilePath $caminho -ArgumentList $citados -WindowStyle Hidden -PassThru `
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
    } else {
        Write-Gut ("{0} {1} (exit {2})" -f $BAD, $Label, $script:NativeExitCode) Red
        $script:StepsFailed++
    }
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
    if (-not $script:AfAnim) { Write-Gut ("{0} {1}..." -f $DOT, $Label) DarkGray }
    # $pronto e nao $ok: nomes de variavel do PowerShell NAO diferenciam
    # maiusculas, entao um local chamado $ok sombreia o glifo global $OK e a
    # linha de sucesso saia "True waiting for..." - medido num Windows 11
    # real. Mesma colisao que ja tinha mordido no --doctor.
    $pronto = $false
    while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSeconds) {
        if ($script:AfAnim) {
            # Na calha, igual ao spinner do Invoke-Step. Os dois spinners do
            # arquivo divergiam entre si: um pendurava no trilho, este nao.
            Write-Host ("`r" + $script:Gut) -ForegroundColor DarkGray -NoNewline
            Write-Host ($AF_SPIN[$i % $AF_SPIN.Count]) -ForegroundColor DarkYellow -NoNewline
            Write-Host (" {0} {1}   " -f $Label, (Format-Since $t0)) -ForegroundColor DarkGray -NoNewline
            $i++
        }
        Start-Sleep -Milliseconds 700
        if (& $Test) { $pronto = $true; break }
    }
    if ($script:AfAnim) { Write-Host ("`r" + (" " * 78) + "`r") -NoNewline }
    if ($pronto) { Write-Gut ("{0} {1} ({2})" -f $OK, $Label, (Format-Since $t0)) Green; Show-AfBar }
    return $pronto
}

# -Verbose: a saida das ferramentas volta para a tela. Esconde-la e a regra (e o
# que separa uma tela limpa de uma colcha de retalhos com dism em portugues,
# winget em ingles e tres estilos de barra), mas quando algo da errado ver o que
# a ferramenta diz, na hora, vale mais.
if ($Verbose) { $VerbosePreference = "Continue"; $script:AfVerbose = $true }

if ($WithOllama -or $OllamaModel) {
    Write-Warn "the Ollama flags are no longer used: pulling a model is several GB and made the install take an unpredictable amount of time"
    Write-Info "this run continues normally; the final panel shows how to enable a local model afterwards"
}

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
    # Uma linha de CALHA antes de cada regua, nunca uma linha vazia: e o que o
    # doc_head do install.sh faz (`printf '%s\n' "$GUT"`), e linha vazia dentro
    # do trilho e um buraco nele. Eram cinco aqui, mais a regua do WSL2 que nao
    # tinha separador nenhum.
    Write-Gut ""
    Write-Rule "Windows"
    Write-Gut ("{0} {1}" -f $OK, [Environment]::OSVersion.VersionString) Green; $nOk++
    $elevado = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($elevado) { Write-Gut ("{0} elevated session" -f $OK) Green; $nOk++ }
    else { Write-Gut "! not elevated - installing WSL or Docker from here would fail" DarkYellow; $nAviso++ }

    Write-Gut ""
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
    Write-Gut ""
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
    Write-Gut ""
    Write-Rule "Install manifest (Windows side)"
    if (Test-Path $AfManifest) {
        Write-Gut ("{0} {1}" -f $OK, $AfManifest) Green; $nOk++
        foreach ($linha in (Get-Content $AfManifest -ErrorAction SilentlyContinue)) {
            $p = $linha -split "`t", 2
            if ($p.Count -eq 2 -and $p[0] -ne "schema" -and $p[0] -notlike "#*") {
                # A calha vem PRIMEIRO e o recuo depois. Invertido, o `|` caia na
                # coluna 5 e o trilho ficava torto justo no despejo do manifesto.
                # Largura 16 no campo da chave, a mesma do install.sh.
                Write-Gut ("    " + ("{0,-16} {1}" -f $p[0], $p[1])) DarkGray
            }
        }
    } else {
        Write-Gut "! no Windows manifest - nothing here was installed by AtlasFile" DarkYellow; $nAviso++
    }

    # O lado Linux responde por si: mesmo diagnostico, mesmo vocabulario.
    Write-Gut ""
    Write-Rule "Inside WSL"
    $cmdDoc = "$(Get-AfEnvPrefix)$AF_CURL $AF_SH_URL | bash -s -- --doctor --delegated"
    if ($script:AfDir) { $cmdDoc += " --dir $(ConvertTo-AfShArg $script:AfDir)" }
    $saidaDoc = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdDoc))
    if ($saidaDoc.Trim()) {
        foreach ($linha in (("$saidaDoc").TrimEnd() -split "`r?`n")) {
            if ($linha -match '^ATLASFILE_(FACT|UNINSTALL):') { continue }
            Write-Host $linha
        }
    } else {
        Write-Gut ("{0} could not run the diagnosis inside WSL" -f $BAD) Red; $nRuim++
    }

    Write-Gut ""
    Write-Rule "Diagnosis (Windows side)"
    # UMA linha, como o placar do install.sh (`✔ N ok  ! N to watch  ✘ N broken`).
    # Sem o -NoNewline o Write-Gut quebrava a linha depois do "N ok" e o resto do
    # placar saia numa segunda linha, essa SEM calha.
    Write-Gut ("{0} {1} ok" -f $OK, $nOk) Green -NoNewline
    Write-Host ("   ! {0} to watch" -f $nAviso) -ForegroundColor DarkYellow -NoNewline
    Write-Host ("   {0} {1} broken" -f $BAD, $nRuim) -ForegroundColor Red
    Close-AfRail
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
    Write-Gut ""
    Write-Rule "Install plan (Windows side)"
    # SEM Ollama. A fase 3 que o instalava saiu, e um dry run que promete instalar
    # o que o instalador nao instala mais mente sobre o proprio trabalho - o
    # `--dry-run` do install.sh lista so o que ele de fato instalaria (git, Docker,
    # plugin do compose). O -Doctor continua reportando o Ollama, e ali esta
    # certo: la a pergunta e "o que existe nesta maquina", nao "o que eu faria".
    foreach ($item in @(
        @{ Nome = "WSL2";           Tem = [bool](Get-Tool wsl) },
        @{ Nome = "Docker Desktop"; Tem = [bool](Get-Tool docker) }
    )) {
        if ($item.Tem) { Write-Gut ("{0} {1} is already here" -f $OK, $item.Nome) Green }
        else { Write-Gut ("{0} {1} WOULD BE INSTALLED" -f $DOT, $item.Nome) DarkYellow }
    }
    Write-Gut ""
    Write-Rule "Install plan (inside WSL)"
    $cmdSeco = "$(Get-AfEnvPrefix)$AF_CURL $AF_SH_URL | bash -s -- --dry-run --delegated"
    if ($script:AfDir) { $cmdSeco += " --dir $(ConvertTo-AfShArg $script:AfDir)" }
    $saidaSeca = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdSeco))
    foreach ($linha in (("$saidaSeca").TrimEnd() -split "`r?`n")) {
        if ($linha -match '^ATLASFILE_(FACT|UNINSTALL):') { continue }
        Write-Host $linha
    }
    Write-Info "-DryRun: nothing was installed."
    Close-AfRail
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
    if ($script:AfDir) { $flagsComuns += " --dir $(ConvertTo-AfShArg $script:AfDir)" }

    # --- 1. FATOS: nao pergunta, nao age ------------------------------------
    Start-Step "reading the removal plan from inside WSL"
    $cmdPlano = "$(Get-AfEnvPrefix)$AF_CURL $AF_SH_URL | bash -s -- $flagsComuns --plan-only"
    $plano = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdPlano))
    if ($script:NativeExitCode -eq 0 -and $plano -match "ATLASFILE_UNINSTALL: plan-only") {
        Write-Ok "removal plan read"
    } else {
        # Plano ilegivel: o lado Windows NAO e tocado. Ponto.
        #
        # A tentacao e agir mesmo assim, porque uma instalacao que morreu depois
        # do Docker Desktop e antes de o WSL ficar utilizavel deixa um Docker
        # orfao que o usuario nao tinha. Mas "nao consegui ler o plano" NAO prova
        # que nao ha instalacao do outro lado: o WSL pode estar vivo, com
        # AtlasFile rodando dentro, e so a comunicacao ter falhado — e ai remover
        # o Docker Desktop apaga o runtime de uma instalacao que existe. E a
        # mesma classe do defeito da v0.55.0, em que um "nao" do usuario virava
        # um Docker Desktop apagado.
        #
        # O manifesto tambem nao resolve: `install_dir` so passou a ser gravado
        # na v0.55.0, entao "ausente" significa tanto "nunca delegou" quanto
        # "instalado por uma versao anterior" — que pode ter WSL cheio.
        #
        # Entao o orfao e RELATADO, nunca removido: e a mesma disciplina que este
        # projeto ja aplica ao Ollama no Linux e ao Homebrew, que sao listados
        # com os passos e deixados para a pessoa executar.
        Write-Fail "could not read the removal plan from WSL (exit $($script:NativeExitCode))"
        Show-LogTail
        Write-Wrapped " " "Nothing was removed, on either side." Red
        $orfaos = @("docker", "ollama") | Where-Object { (Get-AfState $_) -eq "created" }
        if ($orfaos) {
            Write-Gut ""
            Write-Wrapped " " ("The Windows manifest records these as installed by AtlasFile. They were " +
                               "NOT removed, because without the WSL side there is no way to prove that " +
                               "nothing still depends on them:") DarkYellow
            foreach ($chaveOrfa in $orfaos) {
                $rotuloOrfao = if ($chaveOrfa -eq "docker") { "Docker Desktop" } else { "Ollama" }
                Write-Gut ("  - $rotuloOrfao") DarkYellow
            }
            Write-Wrapped " " ("Fix WSL and run this again to remove them properly, or uninstall them " +
                               "by hand from Settings > Apps.") DarkYellow
        }
        Close-AfRail
        Stop-Installer 1; return
    }

    # --- 2. UM plano, cobrindo os dois lados --------------------------------
    # Sem linha em branco aqui: o proprio plano ABRE com uma linha de calha, e
    # uma vazia antes dela era um buraco no trilho.
    # `if ($plano)`: vazio, o -split devolve UMA string vazia e o eco imprimiria
    # uma linha em branco - buraco no trilho, no caminho em que o lado WSL nao
    # respondeu e o plano acima ja foi desenhado por este script.
    if ($plano) {
        foreach ($linha in (("$plano").TrimEnd() -split "`r?`n")) {
            # As linhas de maquina existem para ESTE script, nao para o usuario.
            if ($linha -match '^ATLASFILE_(FACT|UNINSTALL):') { continue }
            Write-Host $linha
        }
    }
    $volume = ""
    if ($plano -match 'ATLASFILE_FACT: volume=(\S+)') { $volume = $Matches[1] }
    $temAcoes = ($plano -match 'ATLASFILE_FACT: actions=1')
    # ESTA maquina tem DOIS escopos. Parar so porque o lado WSL nao tem acao
    # deixava o Docker Desktop instalado mesmo com -RemoveDeps e mesmo com o
    # manifesto do Windows registrando que fomos NOS que o instalamos - medido
    # num Windows 11 real, ao rodar a desinstalacao depois de outra bem-sucedida.
    $temAcoesWindows = $false
    if ($RemoveDeps) {
        foreach ($chaveDep in @("docker", "ollama")) {
            if ((Get-AfState $chaveDep) -eq "created") { $temAcoesWindows = $true }
        }
    }
    if (-not $temAcoes -and -not $temAcoesWindows) {
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
        Write-Gut ""
        Write-Gut ("? The volume $volume holds the search index.") Yellow
        Write-Gut ("  Your documents and the _ATLASFILE journal live on disk and are NOT") Yellow
        Write-Gut ("  affected; the index is rebuilt by Reconcile after a reinstall.") Yellow
        if (Confirm-Plan "Erase the volume?") {
            $decisaoDados = "--purge-data"
            Write-Info "the search index WILL be erased"
        } else {
            $decisaoDados = "--keep-data"
            Write-Info "the search index will be kept"
        }
    }

    # --- 4. UMA confirmacao ---------------------------------------------------
    Write-Gut ""
    if (-not (Confirm-Plan "Execute the plan above?")) {
        Write-Info "uninstall cancelled - nothing was touched."
        Close-AfRail
        # 1602 e o codigo que o mundo Windows ja usa para "o usuario cancelou".
        Stop-Installer 1602; return
    }

    # --- 5. Execucao do lado WSL, nao-interativa ------------------------------
    # So se houver o que fazer LA. Sem esta guarda, um plano que so tem itens do
    # Windows mandava o install.sh remover o nada e depois exigia dele a prova
    # "confirmed", que ele nao tem por que dar.
    Write-Gut ""
    if ($temAcoes) {
    $cmdExec = "$(Get-AfEnvPrefix)$AF_CURL $AF_SH_URL | bash -s -- $flagsComuns --yes $decisaoDados"
    $saidaExec = Invoke-NativeCapture wsl (@($script:WslUser) + @("-e", "bash", "-c", $cmdExec))
    foreach ($linha in (("$saidaExec").TrimEnd() -split "`r?`n")) {
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
        Write-Wrapped " " "Nothing was removed on the Windows side." Red
        Show-LogTail
        Close-AfRail
        Stop-Installer 1; return
    }
    } else {
        Write-Info "nothing left to remove inside WSL - only the Windows side"
    }

    # --- 6. Lado Windows: so o que o plano confirmado mostrou -----------------
    $reinicioPendente = $false
    if (-not $RemoveDeps) {
        Write-Info "Windows-side dependencies preserved - pass -RemoveDeps to revert the ones AtlasFile installed"
    } else {
        foreach ($item in @(
            @{ Key = "docker"; Id = "Docker.DockerDesktop"; Label = "Docker Desktop"
               Path = (Join-Path $env:ProgramFiles "Docker\Docker")
               # Desinstalador PROPRIO, com --quiet. `winget uninstall` nao
               # aceita --override nem --custom (medido: nao sao parametros
               # dele), entao o --silent que passamos nao alcanca o instalador
               # do Docker - ele abria janela e ficava esperando um clique em
               # "Close", num Windows 11 real. Chamar o binario da Docker com
               # --quiet e o caminho que a propria Docker documenta, e ele
               # desregistra o produto sozinho. Se o binario nao estiver la, cai
               # no winget, que continua sendo o caminho registrado.
               Direto = (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop Installer.exe")
               DiretoArgs = @("uninstall", "--quiet") },
            @{ Key = "ollama"; Id = "Ollama.Ollama";        Label = "Ollama";         Path = ""
               Direto = ""; DiretoArgs = @() }
        )) {
            if ((Get-AfState $item.Key) -ne "created") {
                # So afirma preservacao do que ESTA aqui. O usuario tinha
                # removido o Ollama por conta propria ANTES de instalar o
                # AtlasFile, e a tela dizia que nos o preservamos - promessa
                # sobre uma coisa que nao existe. Mesma disciplina do plano:
                # consultar o estado real antes de falar dele.
                if (Get-Tool $item.Key) {
                    Write-Info "$($item.Label) was already on this machine before AtlasFile - preserved"
                }
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
            if ($item.Direto -and (Test-Path $item.Direto)) {
                Invoke-Step "removing $($item.Label)" $item.Direto $item.DiretoArgs
            } else {
                Invoke-Step "removing $($item.Label)" winget @("uninstall", "-e", "--id", $item.Id,
                    "--source", "winget", "--silent", "--disable-interactivity")
            }
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
    # FORA do trilho, como o un_report do install.sh: depois que o `+--` fecha, o
    # relatorio nao pode continuar pendurado na calha. E o fechamento e daqui
    # porque, delegado, o install.sh pula o un_report justamente para nao dar o
    # veredito antes de o lado Windows terminar.
    Close-AfRail
    Write-Note "AtlasFile removed. What already existed on this machine was preserved."
    if ($reinicioPendente) {
        Write-Note "some files were scheduled for deletion on the next restart"
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
        # Na calha: sao cinco linhas no MEIO da fase 1, e cruas elas abriam dois
        # buracos e tres linhas soltas no trilho. O texto e um paragrafo, entao
        # quem quebra e o Write-Wrapped - a largura passa a ser a do trilho em
        # vez de uma quebra escrita a mao.
        Write-Gut ""
        Write-Wrapped " " "Installing WSL2 and Ubuntu (~500 MB, one time)." Cyan
        Write-Wrapped " " ("AtlasFile runs in Linux containers: Ubuntu is where its installer " +
                           "and its stack actually run, and Docker Desktop needs WSL2 too.") Gray
        Write-Gut ""
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
            # Na calha. A tela de FALHA era justamente onde as linhas fugiam do
            # trilho, e e a tela que o usuario mais le. Prosa pelo Write-Wrapped
            # (que quebra na largura), COMANDO pelo Write-Gut: comando existe
            # para ser copiado e nao pode ser requebrado.
            Write-Wrapped " " "Run it by hand to read the real error:" Gray
            Write-Gut "  wsl --install" Yellow
            Write-Wrapped " " "Windows logs servicing failures in %WINDIR%\Logs\DISM\dism.log" Gray
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
    if ($wslMotivo) { Write-Wrapped " " "($wslMotivo)" DarkGray }
    if ($wslMotivo -match "did not answer") {
        # Sem cravar causa: a virtualizacao pode estar LIGADA e o WSL ainda assim
        # nao subir. Lista o que verificar, na ordem de probabilidade.
        Write-Wrapped " " "WSL did not answer. Check, in this order:" Gray
        Write-Gut "  wsl --update      (already tried by this installer)" Yellow
        Write-Gut "  wsl --shutdown    then run this installer again" Yellow
        Write-Gut "  wsl -l -v         does the distro show as Stopped/Running?" Yellow
        Write-Gut "  Get-CimInstance Win32_Processor | Select VirtualizationFirmwareEnabled" Yellow
        Write-Gut "  Get-WinEvent -LogName System -MaxEvents 200 | Where ProviderName -like '*Hyper-V*'" Yellow
    } else {
        Write-Wrapped " " "Install it with (PowerShell as Administrator):" Gray
        Write-Gut "  wsl --install" Yellow
        Write-Wrapped " " "Restart Windows and run this installer again." Gray
    }
    if (-not $isAdmin) { Write-Wrapped " " "(this session is not elevated, so the installer cannot do it for you)" DarkGray }
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
        # --silent: sem ele o winget roda o instalador do Docker com INTERFACE, e
        # ele fica esperando um clique em "Close". Medido num Windows 11 real: o
        # Docker FOI instalado e mesmo assim winget devolveu 0x8A150006
        # (ShellExecute install failed), porque o instalador saiu com 0xFFFFFFFA.
        # --disable-interactivity desliga os prompts DO WINGET, nao a UI do
        # instalador - a chamada de REMOCAO ja passava --silent, a de instalacao
        # nao, e a assimetria era o defeito.
        Invoke-Step "downloading and installing Docker Desktop (~600 MB)" winget @(
            "install", "-e", "--id", "Docker.DockerDesktop",
            "--source", "winget", "--accept-package-agreements", "--accept-source-agreements",
            "--silent", "--disable-interactivity",
            # --custom ACRESCENTA aos switches do manifesto (--override os
            # substituiria). Documentado pela Docker:
            #   --accept-license  "aceita o Docker Subscription Service Agreement
            #                      AGORA, em vez de exigir aceite no primeiro uso"
            #   --backend=wsl-2   escolhe o WSL2 como backend, que e o que este
            #                      instalador precisa
            #   --always-run-service  sobe o com.docker.service e o deixa em
            #                      Automatico, para o daemon nao depender de
            #                      alguem abrir a janela
            # Sem isto o --silent calava o INSTALADOR mas a janela de aceite
            # aparecia no primeiro uso, e o usuario tinha de clicar.
            "--custom", "--accept-license --backend=wsl-2 --always-run-service")
        # 3010 e sucesso COM reinicio pendente (convencao MSI), nao falha.
        $codigoInstall = $script:NativeExitCode
        if ($codigoInstall -ne 0 -and $codigoInstall -ne 3010) {
            # Perguntar antes de declarar: a mesma disciplina que a remocao ja
            # segue (winget list antes de prometer). Um codigo feio nao prova
            # que nada foi instalado - na maquina real o Docker estava la.
            $null = Invoke-NativeCapture winget @("list", "-e", "--id", "Docker.DockerDesktop", "--source", "winget")
            if ($script:NativeExitCode -ne 0) {
                Write-Fail "winget could not install Docker Desktop - install manually: https://docs.docker.com/desktop/install/windows-install/"
                Show-LogTail
                Stop-Installer 1; return
            }
            Write-Warn "winget reported exit $codigoInstall but Docker Desktop is installed - continuing"
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
        Write-Wrapped " " "(or re-run with -InstallDeps to let this installer handle it)" Red
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
        Write-Wrapped " " "1. Docker Desktop's first-launch dialog was not completed (accept the terms)." Red
        Write-Wrapped " " "2. Virtualization is not available: enable it in the firmware/BIOS, or if this is a virtual machine, turn on nested virtualization in the hypervisor." Red
        Write-Wrapped " " "Fix it and re-run this installer - it is idempotent." Red
        Stop-Installer 1; return
    }
}
Write-Ok "Docker Desktop running"

# Tentar ANTES de esperar: sem isto a instalacao gastava os 120s do timeout para
# so entao mandar o usuario clicar num menu.
if (-not (Test-DockerInWsl)) {
    if (Set-AfDockerSetting) {
        Write-Info "adjusting Docker Desktop (WSL integration, welcome survey) and restarting it"
        Restart-AfDockerDesktop
    }
}

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
    Write-Wrapped " " "In Docker Desktop -> Settings -> Resources -> WSL Integration, enable your distro." Red
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
# A barra vive pinada na ultima linha, e daqui em diante quem escreve e o outro
# instalador: sem apaga-la, a linha dela fica encalhada no meio da saida dele,
# sem calha. Medido num Windows 11 real.
Clear-AfBar
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
# -Verbose tem de ATRAVESSAR a fronteira. O build de ~15 min roda do outro lado,
# e e la que as falhas acontecem: pedir a saida das ferramentas e receber so a
# do lado Windows deixa mudo exatamente o trecho que se queria ver.
if ($Verbose) { $shFlags += " --verbose" }
if ($Dir) { $shFlags += " --dir $(ConvertTo-AfShArg $Dir)" }
if ($Branch) { $shFlags += " --branch $Branch" }
# "C:\Users\Joao Silva\Documents" vira um caminho com ESPACO, e a linha inteira
# viaja como argumento unico de `bash -c`. Mesma regra de citacao do --dir: uma
# so, senao as duas divergem na primeira alteracao.
$raizProjetos = if ($ProjectsRoot) { ConvertTo-AfWslPath $ProjectsRoot } else { Get-AfProjectsRoot }
if ($raizProjetos) { $shFlags += " --projects-root $(ConvertTo-AfShArg $raizProjetos)" }
# A divisoria do handover, logo antes de entregar: daqui em diante quem escreve
# na tela e o outro instalador, e isso precisa ficar visivel. A calha continua,
# entao o trilho atravessa a fronteira em vez de recomecar do outro lado.
Write-Gut ""
Write-Handover "handover $([char]0x2504) Linux installer"
$argsSh = @($script:WslUser) + @("-e", "bash", "-c", "$(Get-AfEnvPrefix)$AF_CURL $AF_SH_URL | bash -s -- $shFlags")
Invoke-Native wsl $argsSh
if ($script:NativeExitCode -ne 0) {
    Write-Fail "Install failed inside WSL (see the messages above)."
    Stop-Installer 1; return
}
# O install.sh JA fechou o trilho (o `+--` antes do painel dele). Fechar de novo
# aqui punha uma calha solta e um segundo fechamento no fim da tela - foi o que
# o Windows real mostrou entre "run report:" e "AtlasFile is up in".
$script:TrilhoFechadoNoWsl = $true

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

# FECHAR o trilho antes de qualquer coisa do relatorio. A caixa saia com o
# trilho ainda aberto e o `+--` vinha DEPOIS dela, deixando uma calha solta no
# fim da tela - medido num Windows 11 real. O install.sh fecha primeiro e so
# entao imprime o que e do lado de fora.
Clear-AfBar
$dur = [int]((Get-Date) - $script:RunStart).TotalSeconds
$durTexto = if ($dur -ge 60) { "{0}m{1:d2}s" -f [int]($dur / 60), ($dur % 60) } else { "${dur}s" }
# AF-FIM-DO-TRILHO: esta linha e o fechamento. Daqui para baixo o trilho JA
# FECHOU — aqui, ou do lado do install.sh, que fecha o dele antes do painel — e
# o relatorio final sai sem calha, que e o desenho do mac-env.
if ($script:TrilhoFechadoNoWsl) { Write-Host "" } else { Close-AfRail }
Write-Note ("AtlasFile is up in {0}" -f $durTexto)
Write-Panel @(
    "logs   wsl -e bash -c 'cd $dirWsl && docker compose logs -f'",
    "stop   wsl -e bash -c 'cd $dirWsl && docker compose down'"
)
# Sem contador, como no install.sh: a tela acima ja mostra as fases com seus
# tempos, e um numero novo aqui so compete com ela. Falha continua aparecendo,
# porque isso o usuario PRECISA ver.
if ($script:StepsFailed -gt 0) {
    Write-Host ("  {0} {1} failed - see the run report" -f $BAD, $script:StepsFailed) -ForegroundColor Red
}

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
    Write-Note "run report: $relatorio"
} catch {
    Write-Verbose "run report not written: $($_.Exception.Message)"
}
# A saida das ferramentas nao apareceu na tela por design; dizer ONDE ela esta e
# o que separa "limpo" de "escondido".
if (Test-Path $script:AfLog) { Write-Note "tool output for this run: $script:AfLog" }
Write-Host ""
