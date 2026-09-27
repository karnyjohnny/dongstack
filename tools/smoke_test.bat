@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM  DongStack smoke test (M7) - wersja BAT dla Windows 7 bez
REM  PowerShell (modowe buildy W7 czesto go nie maja / gryza sie
REM  z UTF-8; ten plik jest czystym ASCII).
REM  Uzycie:  smoke_test.bat  [sciezka\DongStack.exe]
REM  Bez argumentu: tylko sekcja srodowiskowa (venv).
REM ============================================================

echo.
echo == OS ==
ver
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (echo Bitness  : 64-bit) else (echo Bitness  : 32-bit)
echo CPU      : %PROCESSOR_IDENTIFIER%

echo.
echo == Critical updates (OPTIONAL on modded Win7 - E5500 runs without) ==
for %%K in (KB2533623 KB2999226 KB4474419) do (
  wmic qfe list brief 2>nul | find /i "%%K" >nul
  if errorlevel 1 (echo   %%K: MISSING ^(optional^) ) else (echo   %%K: INSTALLED)
)

echo.
echo == Python / PyQt5 (venv) ==
python --version
python -c "import sys; print('exe:', sys.executable)"
python -c "import pip; print('pip:', pip.__version__)"
python -c "from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR; print('Qt:', QT_VERSION_STR, '| PyQt:', PYQT_VERSION_STR)"

echo.
echo == SQLite ==
python -c "import sqlite3; print('sqlite3:', sqlite3.sqlite_version)"

set "EXE=%~1"
if "%EXE%"=="" (
  echo.
  echo == Frozen exe: SKIP ^(podaj sciezke jako argument 1^) ==
  goto :end
)

echo.
echo == Frozen exe: %EXE% ==
if not exist "%EXE%" (
  echo FILE NOT FOUND: %EXE%
  goto :end
)
set "T0=%time%"
"%EXE%" --selftest
set "RC=%errorlevel%"
set "T1=%time%"
echo Exit code : %RC%
echo Start     : %T0%
echo End       : %T1%
if "%RC%"=="0" (echo SELFTEST OK) else (echo SELFTEST FAILED)
set "REPORT=%~dp1selftest-report.json"
rem R16: cmd.exe w batchu czeka na proces potomny, ale na wolnym HDD / przy
rem antywirusie dodajemy pasek bezpieczenstwa (max ~30 s) na plik raportu.
set /a WAITED=0
:wait_report
if exist "%REPORT%" goto have_report
if %WAITED% GEQ 30 goto have_report
ping -n 2 127.0.0.1 >nul
set /a WAITED=%WAITED%+1
goto wait_report
:have_report
if exist "%REPORT%" (
  echo.
  echo == Selftest report M7 ^(JSON^) ==
  type "%REPORT%"
) else (
  echo Report file not found: %REPORT%
)

:end
echo.
echo Smoke test zakonczony.
endlocal
