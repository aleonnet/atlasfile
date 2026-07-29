@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ===========================================================================
REM  AtlasFile - reset the Windows side back to a machine that never had WSL.
REM
REM  Run this, reboot, and the end-to-end installer test starts from zero.
REM
REM  DESTRUCTIVE: every WSL distro is unregistered, which deletes its whole
REM  filesystem with no recycle bin. Only run this on a test machine.
REM
REM  Pure ASCII on purpose: a .bat with accented characters renders as garbage
REM  under a different console codepage, and the console here is not ours.
REM ===========================================================================

title AtlasFile - reset WSL

REM --- must run elevated: wsl --unregister and dism both require it ---------
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [X] This script must run as Administrator.
    echo.
    echo       Right-click it and pick "Run as administrator",
    echo       or open an elevated PowerShell and run it from there.
    echo.
    pause
    exit /b 1
)

REM --- WSL_UTF8: without it `wsl --list` emits UTF-16LE and every `for /f`
REM     below reads garbage. Supported since WSL 0.64; harmless if ignored. ---
set WSL_UTF8=1

echo.
echo ===========================================================================
echo   AtlasFile - reset the Windows side to "never had WSL"
echo ===========================================================================
echo.
echo   This will:
echo     1. shut down WSL
echo     2. UNREGISTER every distro (deletes their files permanently)
echo     3. uninstall the WSL app, when this Windows supports it
echo     4. disable the Microsoft-Windows-Subsystem-Linux and
echo        VirtualMachinePlatform Windows features
echo     5. delete %%LOCALAPPDATA%%\AtlasFile (the installer manifest and log)
echo     6. optionally uninstall Docker Desktop
echo.
echo   Your Windows documents are NOT touched.
echo.

echo ---------------------------------------------------------------------------
echo   What is on this machine right now:
echo ---------------------------------------------------------------------------
echo.

REM NAO usar `wsl --list` para inspecionar. Medido no Windows 11 real do teste
REM (2026-07-29): com a feature ligada e ZERO distro, `wsl --list` DISPARA
REM "Pressione qualquer tecla para instalar Subsistema do Windows para Linux" -
REM um script que promete apenas relatar ficava esperando 60s por um prompt do
REM sistema. As duas fontes abaixo sao read-only de verdade:
REM   - dism  : diz se a feature esta ligada, sem tocar no wsl.exe
REM   - registro: lista as distros registradas, que e onde o WSL as guarda
set "WSL_FEATURE=0"
dism.exe /online /get-featureinfo /featurename:Microsoft-Windows-Subsystem-Linux /English 2>nul | findstr /i /c:"State : Enabled" >nul
if not errorlevel 1 set "WSL_FEATURE=1"
set "VMP_FEATURE=0"
dism.exe /online /get-featureinfo /featurename:VirtualMachinePlatform /English 2>nul | findstr /i /c:"State : Enabled" >nul
if not errorlevel 1 set "VMP_FEATURE=1"

if "!WSL_FEATURE!"=="1" (echo   Windows feature "Subsystem for Linux" : ENABLED) else (echo   Windows feature "Subsystem for Linux" : disabled)
if "!VMP_FEATURE!"=="1" (echo   Windows feature "VirtualMachinePlatform": ENABLED) else (echo   Windows feature "VirtualMachinePlatform": disabled)
echo.

set "TEM_DISTRO=0"
echo   Registered distributions:
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss" /s /v DistributionName 2^>nul ^| findstr /i "REG_SZ"') do (
    if not "%%B"=="" (
        set "TEM_DISTRO=1"
        echo     - %%B
    )
)
if "!TEM_DISTRO!"=="0" echo     (none)
echo.
if exist "%LOCALAPPDATA%\AtlasFile" (
    echo   AtlasFile installer state: FOUND at %LOCALAPPDATA%\AtlasFile
) else (
    echo   AtlasFile installer state: none
)
echo.

REM --- typed confirmation: a single keystroke is too easy to hit by mistake --
echo ---------------------------------------------------------------------------
set "CONFIRM="
set /p "CONFIRM=Type RESET (all caps) to proceed, anything else to abort: "
if not "!CONFIRM!"=="RESET" (
    echo.
    echo   Aborted. Nothing was changed.
    echo.
    pause
    exit /b 0
)
echo.

REM --- 1. stop everything ---------------------------------------------------
REM Guarda pela feature: com ela DESLIGADA, qualquer wsl.exe cai no prompt de
REM instalacao do sistema. Nada a parar nesse estado, de todo modo.
echo [1/6] Shutting down WSL...
if "!WSL_FEATURE!"=="1" (
    wsl --shutdown 2>nul
    echo       done.
) else (
    echo       feature already off - nothing to shut down.
)

REM --- 2. unregister every distro ------------------------------------------
REM A lista vem do REGISTRO, nao de `wsl --list`, pela mesma razao. E o
REM --unregister so e chamado quando ha distro de verdade para remover.
echo [2/6] Unregistering distributions...
if "!TEM_DISTRO!"=="0" (
    echo       none registered.
) else (
    for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss" /s /v DistributionName 2^>nul ^| findstr /i "REG_SZ"') do (
        if not "%%B"=="" (
            echo       - unregistering %%B
            wsl --unregister "%%B" >nul 2>&1
            if errorlevel 1 (
                echo         [!] failed to unregister %%B
            ) else (
                echo         removed.
            )
        )
    )
)

REM --- 3. remove the WSL app itself (Store-delivered builds only) -----------
echo [3/6] Uninstalling the WSL app...
wsl --uninstall >nul 2>&1
if errorlevel 1 (
    echo       not supported on this build - skipping.
    echo       ^(the dism step below is what actually turns WSL off^)
) else (
    echo       done.
)

REM --- 4. disable the Windows features the installer re-enables -------------
REM     These two names are exactly the ones install.ps1 turns back on.
echo [4/6] Disabling Windows features...
echo       - Microsoft-Windows-Subsystem-Linux
dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart /English >nul 2>&1
if errorlevel 1 (echo         [!] dism reported an error) else (echo         disabled.)
echo       - VirtualMachinePlatform
dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart /English >nul 2>&1
if errorlevel 1 (echo         [!] dism reported an error) else (echo         disabled.)

REM --- 5. forget what the installer recorded --------------------------------
echo [5/6] Clearing the AtlasFile installer state...
if exist "%LOCALAPPDATA%\AtlasFile" (
    rmdir /s /q "%LOCALAPPDATA%\AtlasFile" 2>nul
    if exist "%LOCALAPPDATA%\AtlasFile" (
        echo       [!] could not delete %LOCALAPPDATA%\AtlasFile
    ) else (
        echo       removed.
    )
) else (
    echo       nothing to clear.
)

REM --- 6. Docker Desktop is optional: it is slow to reinstall ---------------
echo [6/6] Docker Desktop
REM `if errorlevel 1` NAO serve aqui: o winget sai 0 mesmo quando nao acha o
REM pacote - ele escreve "No installed package found matching input criteria" e
REM considera que o COMANDO funcionou. Medido no Windows 11 real do teste
REM (2026-07-29): o script anunciou "Docker Desktop IS installed" numa maquina
REM sem Docker, tentou remover, e imprimiu "done" sem ter removido nada. A prova
REM de verdade e o id aparecer na SAIDA, mesma licao do `wsl --status`.
winget list -e --id Docker.DockerDesktop 2>nul | findstr /i /c:"Docker.DockerDesktop" >nul
if errorlevel 1 (
    echo       not installed - nothing to do.
) else (
    echo       Docker Desktop IS installed.
    set "RMDOCKER="
    REM Colchetes, nao parenteses: um ")" dentro de um bloco fecha o bloco cedo,
    REM e escapar com ^ dentro de aspas imprimiria o proprio ^ no prompt.
    set /p "RMDOCKER=      Uninstall it too, for a full zero? [y/N]: "
    if /i "!RMDOCKER!"=="y" (
        echo       uninstalling - this takes a while...
        REM Docker's OWN uninstaller, with --quiet. `winget uninstall` does not
        REM accept --override or --custom, so a --silent passed to it never
        REM reaches Docker's installer: measured on a real Windows 11, it popped
        REM a window and sat there waiting for a click on "Close". Calling the
        REM binary directly is the path Docker documents, and it deregisters the
        REM product by itself. Same choice install.ps1 makes.
        set "DOCKERUNINST=%ProgramFiles%\Docker\Docker\Docker Desktop Installer.exe"
        if exist "!DOCKERUNINST!" (
            "!DOCKERUNINST!" uninstall --quiet
            echo       done.
        ) else (
            echo       Docker's own uninstaller not found - falling back to winget.
            winget uninstall -e --id Docker.DockerDesktop --silent
            REM Confere o RESULTADO em vez de anunciar sucesso: era aqui que o
            REM script dizia "done" tendo falhado.
            winget list -e --id Docker.DockerDesktop 2>nul | findstr /i /c:"Docker.DockerDesktop" >nul
            if errorlevel 1 (
                echo       removed.
            ) else (
                echo       [!] STILL INSTALLED - remove it from Settings ^> Apps by hand.
            )
        )
    ) else (
        echo       kept. The installer will detect it and skip installing it.
    )
)

echo.
echo ===========================================================================
echo   RESET COMPLETE - NOW REBOOT WINDOWS
echo ===========================================================================
echo.
echo   The feature changes only take effect after a restart.
echo.
echo   After rebooting, confirm the machine really is clean:
echo.
echo       wsl --list --verbose      (should say none are installed)
echo       wsl --status              (should fail, or say WSL is not installed)
echo.
echo   Then start the end-to-end test - see docs\teste_windows_11_real.md:
echo.
echo       ^& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -EnableAuth -Yes -InstallDeps
echo.
pause
endlocal
