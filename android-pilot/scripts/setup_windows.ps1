# Android Pilot - installation locale Windows (a lancer depuis le dossier android-pilot)
# Usage : powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
# Idempotent : peut etre relance sans risque.

$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project
Write-Host "== Android Pilot : installation dans $Project ==" -ForegroundColor Cyan

function Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Yellow }

# --- 1. Python >= 3.10 -------------------------------------------------------
Step "Verification Python"
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python absent -> installation via winget" -ForegroundColor Magenta
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
$ver = & py -3 -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]"3.10") { throw "Python $ver trop ancien (>= 3.10 requis)" }
Write-Host "Python $ver OK"

# --- 2. ADB (platform-tools) -------------------------------------------------
Step "Verification ADB"
$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb) {
    Write-Host "adb absent -> installation via winget (Google.PlatformTools)" -ForegroundColor Magenta
    winget install --id Google.PlatformTools -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $adb = Get-Command adb -ErrorAction SilentlyContinue
}
if (-not $adb) { throw "adb introuvable apres installation. Ouvrir un nouveau terminal et relancer le script." }
$AdbPath = $adb.Source
Write-Host "adb : $AdbPath"

# --- 3. venv + dependances ---------------------------------------------------
Step "Environnement virtuel Python"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & py -3 -m venv .venv }
$VenvPy = Join-Path $Project ".venv\Scripts\python.exe"
& $VenvPy -m pip install --quiet --upgrade pip
& $VenvPy -m pip install --quiet -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "pip install a echoue" }

# --- 4. Tests (faux ADB, sans telephone) ------------------------------------
Step "Tests unitaires"
& $VenvPy -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests en echec - ne pas brancher le telephone avant correction" }

# --- 5. Declaration du serveur MCP pour Claude Code (.mcp.json, scope projet) --
Step "Configuration MCP (.mcp.json)"
$mcp = @{
    mcpServers = @{
        "android-pilot" = @{
            command = $VenvPy
            args    = @("-m", "android_pilot.server")
            env     = @{ ANDROID_PILOT_ADB = $AdbPath }
        }
    }
}
$json = $mcp | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText((Join-Path $Project ".mcp.json"), $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ".mcp.json ecrit (Claude Code demandera de l'approuver au demarrage)"

# --- 6. Etat du telephone ----------------------------------------------------
Step "Appareils ADB visibles"
& $AdbPath start-server | Out-Null
& $AdbPath devices -l

Write-Host "`n== Installation terminee ==" -ForegroundColor Green
Write-Host @"
Etapes suivantes :
  1. Brancher le S24 Ultra en USB -> accepter 'Autoriser le debogage USB' (cocher 'Toujours autoriser').
  2. Verifier :  adb devices   -> doit afficher '<serial>  device'
  3. (Optionnel, sans fil) :  adb tcpip 5555   puis   adb connect <IP_TELEPHONE>:5555   et debrancher le cable.
  4. Lancer Claude Code ici :  cd "$Project" ; claude
     puis approuver le serveur MCP 'android-pilot' et demander : "fais un device_info de mon telephone".
"@
