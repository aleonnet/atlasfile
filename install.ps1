# AtlasFile - Windows installer (via WSL2)
#
#   irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex
#
# Strategy: AtlasFile runs in Linux containers; on Windows the supported path is
# WSL2 + Docker Desktop (WSL backend). This script checks prerequisites - and
# OFFERS to install what is missing (wsl --install, Docker Desktop via winget,
# optional Ollama) - then delegates to install.sh inside the default WSL distro:
# one real installer, no duplicated logic.
#
# Parameters (when saved and run as a file; under `iex` the prompts cover it):
#   -Yes           non-interactive (accept defaults; does NOT install deps)
#   -InstallDeps   authorize installing missing prerequisites without prompting
#   -WithOllama    also install Ollama on Windows and pull a local model
#   -OllamaModel   model to pull (default: gemma4:12b)
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
    [switch]$WithOllama,
    [switch]$EnableAuth,
    [switch]$Uninstall,
    [switch]$PurgeData,
    [switch]$KeepData,
    [switch]$RemoveDeps,
    [switch]$Help,
    [string]$OllamaModel = "gemma4:12b"
)

$ErrorActionPreference = "Stop"

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
  & ([scriptblock]::Create((irm .../install.ps1))) -EnableAuth -WithOllama

AtlasFile runs in Linux containers, so on Windows the supported path is
WSL2 + Docker Desktop. This script prepares the Windows side and then runs the
real installer inside WSL.

Install options:
  -Yes            Non-interactive. On its own it NEVER installs system
                  dependencies - see -InstallDeps
  -InstallDeps    Authorize installing WSL2 / Docker Desktop / Ollama
  -WithOllama     Also install Ollama on Windows and pull a local model
  -OllamaModel    Model to pull with -WithOllama (default: gemma4:12b)
  -EnableAuth     Enable API authentication (forwarded to install.sh)

Uninstall options:
  -Uninstall      Print a removal plan and, once confirmed, revert what this
                  installer created. What already existed is preserved
  -PurgeData      Uninstall: also erase the OpenSearch volume (the index)
  -KeepData       Uninstall: keep the OpenSearch volume
  -RemoveDeps     Uninstall: also remove the Windows-side dependencies that the
                  manifest records as installed by AtlasFile

Other:
  -Help           This help

Manifest: %LOCALAPPDATA%\AtlasFile\host-prereqs
"@
}

if ($Help) { Show-Usage; exit 0 }

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
        # bookkeeping must never break an install
    }
}

function Wait-DockerDaemon([int]$TimeoutSeconds) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSeconds) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

# -- Banner: the orb, its two moons and the comet it fires (no face) ---------
# Same art, palette and moon rest positions as install.sh. Truecolor is used
# only when the host announces it (Windows Terminal sets WT_SESSION and
# supports VT); otherwise this falls back to the classic console colors, and
# with NO_COLOR nothing is emitted at all. The animation itself lives in
# install.sh: this banner is printed once, and seconds later the WSL side
# prints the animated one - two moving banners in a row would be noise.
$AfTrueColor = ($null -ne $env:WT_SESSION -or $env:COLORTERM -in @("truecolor", "24bit")) -and -not $env:NO_COLOR
$AfPlain = [bool]$env:NO_COLOR

function Write-AfLine([string]$Text, [string]$Hex, [string]$Fallback, [switch]$NoNewline) {
    if ($AfPlain) { Write-Host $Text -NoNewline:$NoNewline; return }
    if ($AfTrueColor) {
        $r = [Convert]::ToInt32($Hex.Substring(0, 2), 16)
        $g = [Convert]::ToInt32($Hex.Substring(2, 2), 16)
        $b = [Convert]::ToInt32($Hex.Substring(4, 2), 16)
        Write-Host "$([char]27)[38;2;$r;$g;$b`m$Text$([char]27)[0m" -NoNewline:$NoNewline
    } else {
        Write-Host $Text -ForegroundColor $Fallback -NoNewline:$NoNewline
    }
}

Write-Host ""
Write-AfLine ("        " + ($BLK_LO * 5) + "   ") "ff8a6b" DarkYellow -NoNewline; Write-AfLine $MOON_FAR "c97bff" Magenta
Write-AfLine ("      " + $BLK_LO + ($BLK_FU * 7) + $BLK_LO) "ff5a36" DarkYellow -NoNewline
Write-AfLine "         AtlasFile" "ff5a36" Yellow
Write-AfLine ("     " + $BLK_RT + ($BLK_FU * 9) + $BLK_LF) "ff8a6b" Yellow -NoNewline
Write-AfLine "        Your documents have gravity." "8a8a8a" DarkGray
Write-AfLine ("      " + $BLK_UP + ($BLK_FU * 7) + $BLK_UP) "ff5a36" DarkYellow -NoNewline
Write-AfLine "        (Windows / WSL2)" "8a8a8a" DarkGray
Write-AfLine "    " "592013" DarkYellow -NoNewline
Write-AfLine $MOON_NEAR "ff5a36" Yellow -NoNewline; Write-AfLine ("   " + ($BLK_UP * 5)) "592013" DarkYellow
Write-Host ""

if ($Uninstall) {
    # The Linux side owns the plan, the confirmation and the whole stack: it is
    # the same code path a native install uses, so there is no second
    # implementation to drift. Only the Windows-side packages are handled here.
    Write-Host "  Running the uninstaller inside WSL..." -ForegroundColor Cyan
    $unFlags = "--uninstall"
    if ($Yes) { $unFlags += " --yes" }
    if ($PurgeData) { $unFlags += " --purge-data" }
    if ($KeepData) { $unFlags += " --keep-data" }
    if ($RemoveDeps) { $unFlags += " --remove-deps" }
    wsl -e bash -c "curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- $unFlags"

    Write-Host ""
    if (-not $RemoveDeps) {
        Write-Host "  $DOT Windows-side dependencies preserved - pass -RemoveDeps to revert the ones AtlasFile installed" -ForegroundColor DarkGray
    } else {
        foreach ($item in @(
            @{ Key = "docker"; Id = "Docker.DockerDesktop"; Label = "Docker Desktop" },
            @{ Key = "ollama"; Id = "Ollama.Ollama";        Label = "Ollama" }
        )) {
            if ((Get-AfState $item.Key) -eq "created") {
                Write-Host "  $DOT removing $($item.Label) (installed by AtlasFile)" -ForegroundColor DarkGray
                winget uninstall -e --id $item.Id --silent
                if ($LASTEXITCODE -ne 0) { Write-Host "  ! could not remove $($item.Label) - remove it from Settings > Apps" -ForegroundColor DarkYellow }
            } else {
                Write-Host "  $DOT $($item.Label) was already on this machine before AtlasFile - preserved" -ForegroundColor DarkGray
            }
        }
        # WSL itself is never removed: it is a Windows feature other tools use.
        Write-Host "  $DOT WSL is never removed automatically (other tools may depend on it)" -ForegroundColor DarkGray
        Remove-Item $AfManifest -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Host "  $OK Done. What already existed on this machine was preserved." -ForegroundColor Green
    exit 0
}

# 1. WSL2 - offer to install when missing
# Measured on a clean Windows 11 (build 26200): wsl.exe SHIPS WITH WINDOWS even
# when the feature is absent, so `Get-Command wsl` always succeeds and proves
# nothing. In that state `wsl --status` writes "The Windows Subsystem for Linux
# is not installed" to STDERR and still exits 0 - so neither $LASTEXITCODE nor a
# `2>$null` redirect can be trusted either, and with ErrorActionPreference=Stop
# the native stderr became a terminating NativeCommandError that killed the
# installer with a raw stack trace. The message content is the only real signal.
$wslReady = $false
$wslOut = ""
if (Get-Command wsl -ErrorAction SilentlyContinue) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $wslOut = (& wsl.exe --status 2>&1 | Out-String) } catch { $wslOut = "" }
    $ErrorActionPreference = $prevEap
    # wsl.exe emits UTF-16: without stripping the NULs the text arrives as
    # "i`0s`0 `0n`0o`0t`0..." and every -match below silently fails.
    $wslOut = $wslOut -replace "`0", ""
    if ($wslOut.Trim() -and
        $wslOut -notmatch "is not installed" -and
        $wslOut -notmatch "no installed distributions") { $wslReady = $true }
}
if (-not $wslReady) {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin -and (Confirm-Step "WSL2 is not available - install it now? (a Windows restart will be required)")) {
        wsl --install
        Set-AfState "wsl" "created"
        Write-Host "  $OK WSL install started - restart Windows and run this installer again." -ForegroundColor Green
        exit 0
    }
    Write-Host "  $BAD WSL2 is not available on this machine." -ForegroundColor Red
    Write-Host "    Install it with (PowerShell as Administrator):"
    Write-Host "      wsl --install" -ForegroundColor Yellow
    Write-Host "    Restart Windows and run this installer again."
    if (-not $isAdmin) { Write-Host "    (this session is not elevated, so the installer cannot do it for you)" -ForegroundColor DarkGray }
    exit 1
}
Set-AfState "wsl" "preexisting"
Write-Host "  $OK WSL2 available" -ForegroundColor Green

# 2. Docker Desktop (WSL backend) - offer to install via winget when missing
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget -and (Confirm-Step "Docker Desktop not found - install it now via winget?")) {
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  $BAD winget could not install Docker Desktop - install manually: https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor Red
            exit 1
        }
        Set-AfState "docker" "created"
        Write-Host "  $OK Docker Desktop installed" -ForegroundColor Green
        $docker = Get-Command docker -ErrorAction SilentlyContinue
    } else {
        Write-Host "  $BAD Docker Desktop not found: https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor Red
        Write-Host "    (or re-run with -InstallDeps to let this installer handle it)"
        exit 1
    }
}
if ($docker -and (Get-AfState "docker") -eq "") { Set-AfState "docker" "preexisting" }
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  $DOT starting Docker Desktop - on first launch, accept the terms in the window that opens" -ForegroundColor DarkGray
    $dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) { Start-Process $dockerExe }
    if (-not (Wait-DockerDaemon 300)) {
        Write-Host "  $BAD the Docker daemon did not come up - finish Docker Desktop's first-launch dialog and re-run this installer." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  $OK Docker Desktop running (updates itself via the app)" -ForegroundColor Green

wsl -e sh -c "docker info" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  $BAD Docker is not reachable inside WSL." -ForegroundColor Red
    Write-Host "    In Docker Desktop -> Settings -> Resources -> WSL Integration, enable your distro."
    exit 1
}
Write-Host "  $OK Docker<->WSL integration active" -ForegroundColor Green

# 3. Ollama (opt-in) - installed on the WINDOWS side; containers reach it via
#    host.docker.internal (Docker Desktop default). Not forwarded to install.sh
#    to avoid a duplicate Ollama inside WSL.
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Set-AfState "ollama" "preexisting"
    Write-Host "  $OK Ollama already installed (updates itself via the app)" -ForegroundColor Green
}
if (-not $WithOllama -and -not $ollama -and -not $Yes -and [Environment]::UserInteractive) {
    if (Confirm-Step "Also install Ollama for a 100% local model ($OllamaModel, several GB)?") { $WithOllama = $true }
}
if ($WithOllama) {
    if (-not $ollama) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -eq 0) {
                Set-AfState "ollama" "created"
                Write-Host "  $OK Ollama installed" -ForegroundColor Green
                $ollama = Get-Command ollama -ErrorAction SilentlyContinue
            }
        }
        if (-not $ollama) {
            Write-Host "  ! could not install Ollama automatically - install manually: https://ollama.com/download/windows" -ForegroundColor DarkYellow
        }
    }
    if ($ollama) {
        $pulled = (ollama list 2>$null | Select-String -SimpleMatch $OllamaModel)
        if ($pulled) {
            Write-Host "  $OK model $OllamaModel already pulled" -ForegroundColor Green
        } else {
            Write-Host "  $DOT pulling model $OllamaModel - large download (several GB), one-time" -ForegroundColor DarkGray
            ollama pull $OllamaModel
            if ($LASTEXITCODE -ne 0) { Write-Host "  ! could not pull $OllamaModel - run later: ollama pull $OllamaModel" -ForegroundColor DarkYellow }
        }
        Write-Host "  $DOT in the assistant settings, type ollama/$OllamaModel in the model box to use it" -ForegroundColor DarkGray
    }
}

# 4. Delegate to the Linux installer inside WSL
Write-Host ""
Write-Host "  Running the installer inside WSL..." -ForegroundColor Cyan
Write-Host ""
$shFlags = "--no-open"
if ($Yes) { $shFlags += " --yes" }
if ($InstallDeps) { $shFlags += " --install-deps" }
if ($EnableAuth) { $shFlags += " --enable-auth" }
wsl -e bash -c "curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- $shFlags"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  $BAD Install failed inside WSL (see the messages above)." -ForegroundColor Red
    exit 1
}

Start-Process "http://localhost:5173"
Write-Host ""
Write-Host "  $OK AtlasFile is up: http://localhost:5173" -ForegroundColor Green
