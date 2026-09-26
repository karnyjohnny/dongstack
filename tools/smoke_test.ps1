<#
.SYNOPSIS
  DongStack — smoke test platformy (kamienie milowe M0/M7, specyfikacja §14).
  Kompatybilny z PowerShell 2.0 (Windows 7 SP1).

.DESCRIPTION
  1) raport OS/bitowość + obecność krytycznych aktualizacji (KB2533623, KB2999226/UCRT),
  2) weryfikacja Pythona i PyQt5 w bieżącym środowisku (venv),
  3) opcjonalnie: uruchomienie zbudowanego exe z --selftest, pomiar czasu i RSS.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\smoke_test.ps1
  powershell -ExecutionPolicy Bypass -File tools\smoke_test.ps1 -ExePath "dist\DongStack\DongStack.exe"
#>
param(
    [string]$ExePath = "",
    [string]$Python = "python"
)

$ErrorActionPreference = "Continue"

function Write-Section($t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }

Write-Section "OS"
$os = Get-WmiObject Win32_OperatingSystem
$cs = Get-WmiObject Win32_ComputerSystem
Write-Host ("System   : {0} (build {1})" -f $os.Caption, $os.BuildNumber)
Write-Host ("Bitness  : {0}-bit" -f $os.OSArchitecture)
Write-Host ("RAM      : {0:N0} MB" -f ($cs.TotalPhysicalMemory / 1MB))
Write-Host ("CPU      : {0}" -f (Get-WmiObject Win32_Processor | Select-Object -First 1).Name)

Write-Section "Krytyczne aktualizacje (Track A: Python-Win7 3.13)"
$kbs = @("KB2533623", "KB2999226", "KB4474419")
foreach ($kb in $kbs) {
    $found = Get-WmiObject Win32_QuickFixEngineering | Where-Object { $_.HotFixID -eq $kb }
    if ($found) { Write-Host ("  {0}: ZAINSTALOWANA" -f $kb) -ForegroundColor Green }
    else        { Write-Host ("  {0}: BRAK (może być wymagana)" -f $kb) -ForegroundColor Yellow }
}

Write-Section "Python / PyQt5"
& $Python --version
& $Python -c "import sys; print('exe:', sys.executable)"
& $Python -c "import pip; print('pip:', pip.__version__)" 2>$null
& $Python -c "from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR; print('Qt:', QT_VERSION_STR, '| PyQt:', PYQT_VERSION_STR)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyQt5 NIEDOSTEPNE - pip install -r requirements.txt" -ForegroundColor Red
}

Write-Section "SQLite"
& $Python -c "import sqlite3; print('sqlite3:', sqlite3.sqlite_version)"

if ($ExePath -ne "") {
    Write-Section "Frozen exe: $ExePath"
    if (-not (Test-Path $ExePath)) { Write-Host "BRAK PLIKU!" -ForegroundColor Red; exit 1 }
    $env:QT_QPA_PLATFORM = "windows"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $ExePath -ArgumentList "--selftest" -PassThru -NoNewWindow
    $proc.WaitForExit(120000) | Out-Null
    $sw.Stop()
    Write-Host ("Exit code : {0}" -f $proc.ExitCode)
    Write-Host ("Czas      : {0:N1} s" -f $sw.Elapsed.TotalSeconds)
    if ($proc.ExitCode -ne 0) { Write-Host "SELFTEST FAILED" -ForegroundColor Red; exit $proc.ExitCode }
    Write-Host "SELFTEST OK" -ForegroundColor Green
    $report = Join-Path (Split-Path $ExePath) "selftest-report.json"
    if (Test-Path $report) {
        Write-Host ""
        Write-Host "== Selftest report M7 (JSON) ==" -ForegroundColor Cyan
        Get-Content $report -Raw | Write-Host
    }
}

Write-Host ""
Write-Host "Smoke test zakonczony." -ForegroundColor Green
