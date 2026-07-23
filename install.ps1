# AtlasFile — Windows installer (via WSL2)
#
#   irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex
#
# Strategy: AtlasFile runs in Linux containers; on Windows the supported path is
# WSL2 + Docker Desktop (WSL backend). This script checks prerequisites — and
# OFFERS to install what is missing (wsl --install, Docker Desktop via winget,
# optional Ollama) — then delegates to install.sh inside the default WSL distro:
# one real installer, no duplicated logic.
#
# Parameters (when saved and run as a file; under `iex` the prompts cover it):
#   -Yes           non-interactive (accept defaults; does NOT install deps)
#   -InstallDeps   authorize installing missing prerequisites without prompting
#   -WithOllama    also install Ollama on Windows and pull a local model
#   -OllamaModel   model to pull (default: gemma4:12b)
#   -EnableAuth    enable API authentication (forwarded to install.sh)
param(
    [switch]$Yes,
    [switch]$InstallDeps,
    [switch]$WithOllama,
    [switch]$EnableAuth,
    [string]$OllamaModel = "gemma4:12b"
)

$ErrorActionPreference = "Stop"

function Confirm-Step([string]$Question) {
    if ($InstallDeps) { return $true }
    if ($Yes) { return $false }  # conservative: -Yes alone never installs system deps
    if (-not [Environment]::UserInteractive) { return $false }
    $answer = Read-Host "  ? $Question [y/N]"
    return $answer -match '^(y|yes|s)$'
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

# Banner: the orb (with a face) and the wordmark — same character as install.sh
Write-Host ""
Write-Host "        ▄▄▄▄▄        " -ForegroundColor DarkYellow -NoNewline; Write-Host "●" -ForegroundColor Magenta
Write-Host "      ▄███████▄" -ForegroundColor DarkYellow
Write-Host "     ▐██ " -ForegroundColor Yellow -NoNewline; Write-Host "● ●" -ForegroundColor White -NoNewline; Write-Host " ██▌" -ForegroundColor Yellow -NoNewline; Write-Host "   AtlasFile " -ForegroundColor DarkYellow -NoNewline; Write-Host "(Windows/WSL2)" -ForegroundColor DarkGray
Write-Host "      ▀██ " -ForegroundColor DarkYellow -NoNewline; Write-Host "‿" -ForegroundColor White -NoNewline; Write-Host " ██▀" -ForegroundColor DarkYellow -NoNewline; Write-Host "    your documents, alive" -ForegroundColor DarkGray
Write-Host "   ●" -ForegroundColor Yellow -NoNewline; Write-Host "    ▀▀▀▀▀" -ForegroundColor DarkYellow
Write-Host ""

# 1. WSL2 — offer to install when missing
$wsl = Get-Command wsl -ErrorAction SilentlyContinue
if (-not $wsl) {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin -and (Confirm-Step "WSL not found — install it now? (a Windows restart will be required)")) {
        wsl --install
        Write-Host "  ✔ WSL install started — restart Windows and run this installer again." -ForegroundColor Green
        exit 0
    }
    Write-Host "  ✘ WSL not found." -ForegroundColor Red
    Write-Host "    Install it with (PowerShell as Administrator):"
    Write-Host "      wsl --install" -ForegroundColor Yellow
    Write-Host "    Restart Windows and run this installer again."
    exit 1
}
$wslStatus = (wsl --status 2>$null) -join "`n"
if ($LASTEXITCODE -ne 0 -or -not $wslStatus) {
    Write-Host "  ✘ WSL is installed but no distro is set up. Run: wsl --install -d Ubuntu" -ForegroundColor Red
    exit 1
}
Write-Host "  ✔ WSL2 available" -ForegroundColor Green

# 2. Docker Desktop (WSL backend) — offer to install via winget when missing
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget -and (Confirm-Step "Docker Desktop not found — install it now via winget?")) {
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ✘ winget could not install Docker Desktop — install manually: https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor Red
            exit 1
        }
        Write-Host "  ✔ Docker Desktop installed" -ForegroundColor Green
        $docker = Get-Command docker -ErrorAction SilentlyContinue
    } else {
        Write-Host "  ✘ Docker Desktop not found: https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor Red
        Write-Host "    (or re-run with -InstallDeps to let this installer handle it)"
        exit 1
    }
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  · starting Docker Desktop — on first launch, accept the terms in the window that opens" -ForegroundColor DarkGray
    $dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) { Start-Process $dockerExe }
    if (-not (Wait-DockerDaemon 300)) {
        Write-Host "  ✘ the Docker daemon did not come up — finish Docker Desktop's first-launch dialog and re-run this installer." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  ✔ Docker Desktop running (updates itself via the app)" -ForegroundColor Green

wsl -e sh -c "docker info" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✘ Docker is not reachable inside WSL." -ForegroundColor Red
    Write-Host "    In Docker Desktop → Settings → Resources → WSL Integration, enable your distro."
    exit 1
}
Write-Host "  ✔ Docker↔WSL integration active" -ForegroundColor Green

# 3. Ollama (opt-in) — installed on the WINDOWS side; containers reach it via
#    host.docker.internal (Docker Desktop default). Not forwarded to install.sh
#    to avoid a duplicate Ollama inside WSL.
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "  ✔ Ollama already installed (updates itself via the app)" -ForegroundColor Green
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
                Write-Host "  ✔ Ollama installed" -ForegroundColor Green
                $ollama = Get-Command ollama -ErrorAction SilentlyContinue
            }
        }
        if (-not $ollama) {
            Write-Host "  ! could not install Ollama automatically — install manually: https://ollama.com/download/windows" -ForegroundColor DarkYellow
        }
    }
    if ($ollama) {
        $pulled = (ollama list 2>$null | Select-String -SimpleMatch $OllamaModel)
        if ($pulled) {
            Write-Host "  ✔ model $OllamaModel already pulled" -ForegroundColor Green
        } else {
            Write-Host "  · pulling model $OllamaModel — large download (several GB), one-time" -ForegroundColor DarkGray
            ollama pull $OllamaModel
            if ($LASTEXITCODE -ne 0) { Write-Host "  ! could not pull $OllamaModel — run later: ollama pull $OllamaModel" -ForegroundColor DarkYellow }
        }
        Write-Host "  · in the assistant settings, type ollama/$OllamaModel in the model box to use it" -ForegroundColor DarkGray
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
    Write-Host "  ✘ Install failed inside WSL (see the messages above)." -ForegroundColor Red
    exit 1
}

Start-Process "http://localhost:5173"
Write-Host ""
Write-Host "  ✔ AtlasFile is up: http://localhost:5173" -ForegroundColor Green
