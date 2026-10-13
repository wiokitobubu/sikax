<#
    Fabrique la distribution Windows de Sikax.

        powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

    Options :
        -SansTests       ne lance pas la suite de tests avant de fabriquer
        -Installateur    fabrique aussi l'installateur (Inno Setup doit être installé)
        -Python <exe>    interpréteur à utiliser (par défaut : « py -3 », sinon « python »)

    Résultat : dist\Sikax\Sikax.exe et ses dossiers runtime\, locales\, resources\,
    puis dist\Sikax-<version>-windows.zip.
#>
param(
    [switch]$SansTests,
    [switch]$Installateur,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
Set-Location $racine

function Executer($programme, $arguments) {
    & $programme @arguments
    if ($LASTEXITCODE -ne 0) { throw "Échec : $programme $($arguments -join ' ')" }
}

# 1. Environnement de fabrication isolé : la distribution ne contient que ce qui est demandé.
$venv = Join-Path $racine ".venv-build"
if (-not (Test-Path $venv)) {
    Write-Host "== Création de l'environnement de fabrication" -ForegroundColor Cyan
    if ($Python) { Executer $Python @("-m", "venv", $venv) }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { Executer "py" @("-3", "-m", "venv", $venv) }
    else { Executer "python" @("-m", "venv", $venv) }
}
$py = Join-Path $venv "Scripts\python.exe"
Write-Host "== Installation des dépendances" -ForegroundColor Cyan
Executer $py @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
Executer $py @("-m", "pip", "install", "--quiet", "-r", "requirements-dev.txt")

# 2. Tests : on ne distribue pas un programme qui échoue à ses propres vérifications.
if (-not $SansTests) {
    Write-Host "== Tests" -ForegroundColor Cyan
    $env:QT_QPA_PLATFORM = "offscreen"
    Executer $py @("-m", "pytest", "-q")
    Remove-Item Env:QT_QPA_PLATFORM
}

# 3. Fabrication du dossier d'application.
Write-Host "== PyInstaller" -ForegroundColor Cyan
Executer $py @("-m", "PyInstaller", "packaging\sikax.spec", "--noconfirm", "--clean", "--distpath", "dist", "--workpath", "build")

# 4. Contrôle de la distribution : l'exécutable se vérifie lui-même, sans fenêtre.
Write-Host "== Contrôle de dist\Sikax\Sikax.exe" -ForegroundColor Cyan
$exe = Join-Path $racine "dist\Sikax\Sikax.exe"
$controle = Start-Process -FilePath $exe -ArgumentList "--autotest" -Wait -PassThru -WindowStyle Hidden
if ($controle.ExitCode -ne 0) { throw "La distribution ne passe pas son auto-contrôle (code $($controle.ExitCode))." }
foreach ($dossier in @("locales", "resources\icons", "resources\themes", "resources\exemples")) {
    if (-not (Test-Path (Join-Path $racine "dist\Sikax\$dossier"))) { throw "Dossier manquant dans la distribution : $dossier" }
}

# 5. Archive prête à diffuser.
$version = (& $py -c "import sikax; print(sikax.__version__)").Trim()
$archive = Join-Path $racine "dist\Sikax-$version-windows.zip"
if (Test-Path $archive) { Remove-Item $archive }
Compress-Archive -Path (Join-Path $racine "dist\Sikax") -DestinationPath $archive
Write-Host "== Distribution prête" -ForegroundColor Green
Write-Host "   Dossier : dist\Sikax"
Write-Host "   Archive : dist\Sikax-$version-windows.zip"

# 6. Installateur (facultatif).
if ($Installateur) {
    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $candidat = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (Test-Path $candidat) { $iscc = $candidat }
    }
    if (-not $iscc) { throw "Inno Setup (ISCC.exe) est introuvable : installez-le depuis https://jrsoftware.org/isinfo.php" }
    Write-Host "== Installateur" -ForegroundColor Cyan
    Executer $iscc @("/DVersion=$version", "packaging\sikax.iss")
    Write-Host "   Installateur : dist\Sikax-$version-setup.exe"
}
