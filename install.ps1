# AtlasFile — instalador Windows (via WSL2)
#
#   irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex
#
# Estratégia: o AtlasFile roda em containers Linux; no Windows o caminho
# suportado é WSL2 + Docker Desktop (backend WSL). Este script verifica os
# pré-requisitos e delega ao install.sh dentro da distro default do WSL —
# um único instalador de verdade, sem lógica duplicada.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  AtlasFile — gestão documental inteligente (Windows/WSL2)" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────────────────────────────────"
Write-Host ""

# 1. WSL2
$wsl = Get-Command wsl -ErrorAction SilentlyContinue
if (-not $wsl) {
    Write-Host "  ✘ WSL não encontrado." -ForegroundColor Red
    Write-Host "    Instale com (PowerShell como Administrador):"
    Write-Host "      wsl --install" -ForegroundColor Yellow
    Write-Host "    Reinicie o Windows e rode este instalador novamente."
    exit 1
}
$wslStatus = (wsl --status 2>$null) -join "`n"
if ($LASTEXITCODE -ne 0 -or -not $wslStatus) {
    Write-Host "  ✘ WSL instalado mas sem distro configurada. Rode: wsl --install -d Ubuntu" -ForegroundColor Red
    exit 1
}
Write-Host "  ✔ WSL2 disponível" -ForegroundColor Green

# 2. Docker Desktop com backend WSL
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "  ✘ Docker Desktop não encontrado: https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor Red
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✘ Docker Desktop instalado mas não está rodando — abra-o e tente de novo." -ForegroundColor Red
    exit 1
}
Write-Host "  ✔ Docker Desktop rodando" -ForegroundColor Green

wsl -e sh -c "docker info" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✘ O Docker não está acessível dentro do WSL." -ForegroundColor Red
    Write-Host "    Em Docker Desktop → Settings → Resources → WSL Integration, habilite sua distro."
    exit 1
}
Write-Host "  ✔ Integração Docker↔WSL ativa" -ForegroundColor Green

# 3. Delegar ao instalador Linux dentro do WSL
Write-Host ""
Write-Host "  Executando o instalador dentro do WSL..." -ForegroundColor Cyan
Write-Host ""
wsl -e bash -c "curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --no-open"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✘ Instalação falhou dentro do WSL (veja as mensagens acima)." -ForegroundColor Red
    exit 1
}

Start-Process "http://localhost:5173"
Write-Host ""
Write-Host "  ✔ AtlasFile no ar: http://localhost:5173" -ForegroundColor Green
