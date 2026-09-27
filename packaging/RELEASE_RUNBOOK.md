# RELEASE RUNBOOK (M6) — od commita do Release z binarkami

## 0. Ograniczenia środowiskowe (udokumentowane)

- **Sandbox/dev Linux ze statycznym CPython NIE zbuduje binarki** — PyInstaller na
  Linuksie wymaga interpretera linkowanego z `libpython` (shared). Dlatego logikę
  `.spec` pilnują testy jednostkowe (`tests/unit/test_spec_logic.py`, stub
  Analysis/PYZ/EXE/COLLECT), a prawdziwy freeze odbywa się **wyłącznie na Windows**
  (CI `windows-2022` lub lokalnie na maszynie deweloperskiej/docelowej).
- Artefakty produkcyjne powstają na **przypiętym buildzie Python-Win7 3.13.5**
  (`packaging/python-win7.json`: commit + SHA256) — tylko taki interpreter daje exe
  działający na Windows 7 SP1 (specyfikacja §2.2, F1/F2).

## 1. Przygotowanie wydania

1. Zielone `ci.yml` na main (ruff + 230+ testów, w tym `test_spec_logic` i `test_packaging_pins`).
2. Sync wersji: `app/__init__.py:__version__` ⇄ `packaging/version_info.txt`
   (pilnuje test `test_version_info_in_sync_with_package`).
3. Opcjonalnie odśwież piny: `python tools/freeze_hashes.py` (regeneruje
   `requirements.lock.txt` z hashami kół win_amd64+win32) — commit osobno.
4. Tag: `git tag -a v1.0.0 -m "release 1.0.0" && git push origin v1.0.0`.

## 2. Co robi `release.yml` (tag v*)

1. Matrix `arch: [amd64, win32] × package: [onedir, onefile]` na `windows-2022`.
2. Pobiera installer Python-Win7 z **przypiętego commita** i weryfikuje SHA256
   (niezgodność = twardy fail builda, supply-chain pin §9.3).
3. Instaluje runtime z `requirements.lock.txt` przez `--require-hashes` (D8),
   narzędzia builda z `requirements-dev.txt` (bez hashowania).
4. pytest (unit+gui, offscreen) **na docelowym interpreterze** + opcjonalne testy
   live MAL (`workflow_dispatch` + secret `MAL_CLIENT_ID`, D5).
5. `PyInstaller packaging\dongstack.spec` (onedir) / `DHT_ONEFILE=1` (onefile).
6. Smoke: `DongStack.exe --selftest` (offscreen) — JSON z progami (exit≠0 = fail).
   **R16:** exe jest *windowed* (`console=False`), więc PowerShell **nie czeka** na nie przy `& exe`
   (`$LASTEXITCODE` pusty, raport jeszcze nie zapisany). W skryptach używaj
   `Start-Process -FilePath $exe -ArgumentList "--selftest" -NoNewWindow -Wait -PassThru` → `$p.ExitCode`,
   a raport czytaj z pliku `DONGSTACK_SELFTEST_OUT` (nigdy `Tee-Object` na tę samą ścieżkę — stdout exe
   zaczyna się od `selftest-report: …`, więc `ConvertFrom-Json` się wysypie). `cmd.exe` w batchu czeka sam
   (`tools\smoke_test.bat` ma dodatkowo pętlę oczekiwania na plik raportu).
7. Pakowanie: `DongStack-3.13.5-win-<arch>-onedir.zip` / `…-portable.exe`
   + `SHA256SUMS-*.txt`; job `release` skleja sumy i publikuje GitHub Release.

## 3. Weryfikacja na sprzęcie docelowym (E5500, Windows 7 SP1 x64)

```powershell
# po pobraniu artefaktów z Release (PowerShell):
certutil -hashfile DongStack-3.13.5-win-amd64-onedir.zip SHA256   # porównaj z SHA256SUMS.txt
Expand-Archive DongStack-3.13.5-win-amd64-onedir.zip -DestinationPath C:\DongStack
powershell -ExecutionPolicy Bypass -File tools\smoke_test.ps1 -ExePath C:\DongStack\DongStack\DongStack.exe
```

Na Windows 7 bez PowerShell (modowe buildy) użyj wariantu BAT (czysty ASCII):

```bat
cmd
tools\smoke_test.bat "C:\DongStack\DongStack\DongStack.exe"
```

BAT wypisuje na stdout pełny JSON z `--selftest` (protokół pomiarów M7:
`increment_p95_ms`, `gui_fill300_ms`, `gui_rebuild300_ms`, `threads`, `total_ms`).

**Uwaga M7 (dowód z E5500, 2026-09-26):** maszyna docelowa (Core 2 Duo T7250,
W7 SP1 x64 mod) działa bez KB2533623/KB2999226/KB4474419 — build Python-Win7
nie wymaga ich na tej instalacji; lista KB zostaje jako diagnostyka opcjonalna.

`smoke_test.ps1` raportuje: OS/KB (KB2533623, KB2999226/UCRT), Python/PyQt5/SQLite
w venv, a z `-ExePath` uruchamia `--selftest` zamrożonej binarki i mierzy czas + exit code.

Progi akceptacji M6/M7 na E5500 (specyfikacja §1.3, §7):
- start zimny onedir → okno interaktywne ≤ 3,5 s,
- `--selftest`: `increment_p95_ms` ≤ 50 (E5500; CI ma próg 8),
- RSS procesu ≤ 250 MB przy 300 pozycjach (M7),
- rebuild listy 300 (sort „Wszystkie”) ≤ 150 ms, inaczej gate G3 → `DelegateListBackend`.

## 4. Rollback

Każdy Release trzyma komplet 4 artefaktów + sumy; poprzedni tag zostaje na repo —
rollback = wskazanie starszego Release (binarki są samowystarczalne, dane użytkownika
w `%LOCALAPPDATA%\DongStack` są niezależne od wersji exe dzięki migracjom §4.4).
