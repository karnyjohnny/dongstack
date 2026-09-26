# packaging/ — konfiguracja freezera (PyInstaller)

> Katalog nazywa się `packaging/` (a nie `build/`), ponieważ nazwa `build`
> jest wyłączona z persistence snapshotów środowiska deweloperskiego.

| Plik | Rola |
|---|---|
| `dongstack.spec` | Definicja buildu: entrypoint `app/main.py`, zasoby QSS/ikony (`datas`), excludes modułów Qt, czystka translacji/pluginów, UPX **off**, `console=False`, ikona + VERSIONINFO. Wariant onefile przez env `DHT_ONEFILE=1`. |
| `version_info.txt` | Metadane VERSIONINFO wstrzykiwane do exe (wersja w sync z `app/__init__.py`). |
| `python-win7.json` | **Pin zaufania supply-chain**: commit + SHA256 installerów Python-Win7 3.13.5 (x64/x86). CI (`release.yml`) odmawia buildu przy niezgodności sum. Regeneracja: `python tools/hash_python_win7.py`. |

## Szybkie komendy

```bat
:: onedir (rekomendowany na docelowy sprzęt)
python -m PyInstaller packaging\dongstack.spec --noconfirm

:: onefile (portable)
set DHT_ONEFILE=1
python -m PyInstaller packaging\dongstack.spec --noconfirm --distpath dist-onefile
```

Artefakty: `dist\DongStack\DongStack.exe` (onedir) / `dist-onefile\DongStack.exe` (onefile).

> Katalogi `dist*/`, `work/` są w `.gitignore` — do repo commitujemy wyłącznie pliki z tabeli powyżej.
> Pełny opis: `docs/SPECYFIKACJA-TECHNICZNA.md` §8–§9.
