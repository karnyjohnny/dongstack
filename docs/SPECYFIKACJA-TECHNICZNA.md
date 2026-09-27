# DONGSTACK (d. donghua-tracker)
# Specyfikacja techniczna i architektura systemu — v1.1

> **Status:** ZATWIERDZONA do implementacji — decyzje D1–D8 rozstrzygnięte przez Właściciela Produktu 2026-09-26 (§15)
> **Data:** 2026-09-26 (v1.0-DRAFT → v1.1)
> **Autor:** Główny Architekt Oprogramowania / Inżynier DevOps
> **Dokument wejściowy:** `donghua-tracker-super-specyfikacja-pyqt5.md` (Biblia GUI — 68 sekcji, zasady niepodlegające dyskusji)
> **Zakres:** architektura, dobór i weryfikacja stosu technologicznego pod Windows 7 / Core 2 Duo / 2 GB RAM, warstwa danych, integracja MAL API, freezing PyInstaller, CI/CD GitHub Actions, plan implementacji.
>
>**Changelog v1.3.0 (2026-09-27) — r11: postęp przy nieznanym totalu, notatka, alt-tytuły, zarządzanie uniwersami, przewijalny formularz; r12: czytelne segmenty statusu:**
> 0. **M7 zamknięty dowodem z urządzenia docelowego:** selftest v1.2.1 na E5500 — `increment_p95_ms = 0.622` (G2 ≤50 ✔), `gui_rebuild300_ms = 2.0` (G3 ≤150 ✔; przed DelegateListBackend: 1688.7), `db_init 219 ms`, `insert300 912 ms`, `update200 31 ms`, `threads = 1`. CI (freeze-smoke + release) zielone po wprowadzeniu R16.
> 1. **BUG „nie da się wpisać obejrzanych odcinków, gdy baza nie zna ich liczby”** — root-cause: `AdvancedPage` robił `_episode.setMaximum(max(0, total))`, więc przy `total_episodes = 0` (MAL/AniList `??`, sezon jeszcze niewyemitowany) sufit wynosił **0**: spinboksa nie dało się ruszyć, a `setValue(current_episode)` przy wczytaniu edycji był clampowany do zera → „w dashboard `+/−` rośnie, a w edycji dalej 0 (string)”, dopóki użytkownik ręcznie nie zamienił `—` na liczbę. Fix: semantyka **`0 = nieznane`** (nowa zasada R18) — sufit techniczny `EPISODE_OPEN_CEILING = 9999`, `_total.valueChanged` przelicza sufit i przycina wartość **tylko** gdy `total > 0`; kolejność ładowania: najpierw `setValue(total)` (ustawia sufit), potem `setValue(episode)`. `specialValueText` skrócone do `—` (spójnie z kartą dashboardu). Kontroler i repozytorium clampowały poprawnie już wcześniej (`if total > 0`) — defekt był wyłącznie w warstwie widgetów.
> 2. **FIX „modal dodawania/edycji ucieka poza ekran”** (1366×768 + ~10 linków; z notatką byłoby gorzej): pola, notatka i sekcja linków trafiły do `QScrollArea` (`widgetResizable`, `NoFrame`, przezroczyste tło, `ScrollBarAlwaysOff` w poziomie), a **nagłówek (tytuł + alt) i pasek akcji (Usuń/Wstecz/Zapisz) zostały przypięte poza scrollem**. Root-cause: `minimumSizeHint` dialogu rósł z każdym wierszem linków (minimum layoutu propaguje się do okna) — po fixie minimum = 349 px przy 12 linkach, treść 783 px jest przewijana. Przy okazji: `QPlainTextEdit` **nie jest** podklasą `QTextEdit`, więc guard skrótu „Ctrl+V = doklej link” nie łapał pola notatki (wklejenie URL-a tworzyło wiersz linku) — dodany do `isinstance`.
> 3. **QoL notatka własna** (`donghua.note`): pole tekstowe 64 px **nad linkami streamingowymi** (opcjonalne; trim; puste → `NULL`) — np. „na CDA numeracja = 52 + odcinek tego sezonu”, „S2 = 28+”. **Bez nowej migracji:** kolumna `note` istnieje od schematu v1, a `insert/update_full` ją obsługują — brakowało wyłącznie UI (zero ryzyka dla danych użytkownika). Notatka wraca też jako tooltip karty na dashboardzie.
> 4. **QoL tytuł alternatywny pod nazwą serii:** karta dashboardu (`QLabel#altLabel`, 10 px, ElideRight, linia **zwinięta** gdy alta brak — karta trzyma 96 px) + identyczny układ w `CardDelegate`. Geometria linii karty wyextractowana do funkcji czystej `card_text_rects(rect, text_left, text_right, has_alt) -> {title, alt, meta, bar}` — współdzielona przez paint i testy (bez analizy pikseli). Nagłówek AdvancedPage pokazuje alt z providera/bazy; w trybie ręcznym zostaje edytowalne pole „Tytuł alt.” (bez duplikatu).
> 5. **QoL zarządzanie uniwersami** (⚙ Ustawienia → „Uniwersa (przypisane sezony, usuwanie)…”, nowy `SettingsDialog` z `QTabWidget`: „MAL API” / „Uniwersa”): lista uniwersów **z liczbą przypisanych sezonów** + „Usuń wybrane”. Kasowanie jest „kaskadowe” w sensie **czyszczenia przynależności**: `DELETE FROM universes` + FK `ON DELETE SET NULL` (`PRAGMA foreign_keys=ON`) ⇒ sezony zostają w bibliotece, tracą tylko `universe_id`. Ścieżka wg Biblii §9: widok odłącza **optymistycznie**, `DELETE` idzie kolejką DbWorker (R2), `universeDeleted/universeDeleteFailed` z `request_id` (R5), nack przywraca rejestr i przynależności. **Undo** odtwarza uniwersum (`createUniverse` z tą samą nazwą/anchorem) i podpina te same `donghua_id` z zachowaniem `universe_order`; przycisk „Cofnij” siedzi w **stopce dialogu**, bo SnackBar jest przykryty oknem modalnym. Liczniki odświeżają się na żywo (`universesChanged` → `set_universes`), bo Undo nadaje uniwersum **nowe id**. Menu ⚙ zachowuje „Client ID MyAnimeList…” (teraz otwiera zakładkę MAL API); first-run `ClientIdDialog` bez zmian.
> 6. Nowe zasady **R17** (przewijalny formularz + przypięty pasek akcji) i **R18** (`0 = wartość nieznana` w polach liczbowych) — §3.2.
> 7. Regresje: `tests/unit/test_r11_universes.py` (roundtrip notatki w repo, `ON DELETE SET NULL` na żywym SQL, liczniki, delete/ack/nack/Undo, tryb bez workera), `tests/gui/test_r11_ui.py` (sufit odcinka, edycja z `total=0`, clamp przy znanym totalu, tryb ręczny, alt/notatka, scroll + 12 linków, Ctrl+V w notatce, karta i delegate — geometria + differential pixel test, `SettingsDialog`, e2e z DbWorker i SQLite), `tests/gui/test_r11_note_plumbing.py` (formularz → model → SQL), rozszerzone `test_main_wiring` (kontrakt `deleteUniverse/universeDeleted/universeDeleteFailed` + wiring ustawień) i `StubWorker`. **Weryfikacja mutacyjna: 8/8 mutacji złapanych** (m.in. przywrócony stary sufit spinboksa, brak scrolla, brak `delete` w workerze, note=None). Razem **354 testy** (`pytest tests/unit tests/gui`, offscreen), `ruff check`/`format` czyste, `--selftest` `ok:true` (rebuild300 0.9 ms).
> 8. **FIX r12 (przed wydaniem): segmenty statusu w dodawaniu/edycji nieczytelne po zaznaczeniu/wciśnięciu** — objaw z feedbacku: „wciśnięty przycisk, nieważne w którym statusie, robi się ciemnoniebieski/fioletowy i kompletnie nieczytelny”. Root-cause dwuwarstwowy: **(a)** `viewport().setStyleSheet("background:transparent;")` przy `QScrollArea` (wprowadzone w r11) — w Qt stylesheet **bez selektora** działa jak `* { background: transparent }` na widget **i wszystkich potomków**, a conflict resolution daje pierwszeństwo stylesheetowi bliższemu widgetowi **niezależnie od specyficzności** app-QSS → każde pole formularza w scrollu straciło tło, a `QPushButton#statusSegment` został bez `background` → `QStyleSheetStyle` oddał rysowanie przycisku **natywnemu motywowi Windows** (aero: ciemnoniebieski/fioletowy fill checked/pressed, wspólny dla wszystkich statusów). Fix: stylesheet viewportu usunięty (`setAutoFillBackground(False)` — viewport i tak sam z siebie nie maluje tła). **(b)** Redesign QSS wg wytycznej Właściciela: zaznaczony = **ramka 2px w pełnym kolorze statusu + pogrubiony napis tym samym kolorem** na ciemnym tle `#2A2A2A` (padding 7/11 kompensuje grubszą ramkę — geometria nie skacze; równe szerokości segmentów przez `addWidget(btn, 1)`), wciśnięty = ramka + tekst **o stopień jaśniejsze** i tło `#303030`; dodane **jawne reguły `:pressed`/`:checked:pressed`** dla każdego statusu (definitywnie odcinają natywny aero-fallback), usunięte pełne fille z tekstem `#14181C` oraz fioletowy akcent `#B39DDB` z generycznego fallbacka `:checked`. Drabinka kolorów na status: ramka stonowana → hover → pełny kolor (zaznaczony) → jasny (wciśnięty). Regresja: `tests/gui/test_r12_status_segment.py` (pikselowe: ramka/tekst/tło dla 4 statusów × checked/pressed/niezaznaczony, dowód braku wycieku stylesheetu na viewport, kontrakt statyczny jawnych `:pressed` i zakazu `#B39DDB`/`#14181C` w regułach segmentu) — **weryfikacja mutacyjna 4/4** (wyciek viewportu, stary fill, brak `:pressed`, fiolet). Razem **362 testy**, `ruff` czysty, `--selftest` `ok:true`.
>
>**Changelog v1.2.1 (2026-09-27) — CI: selftest frozen exe (poprawka harnessa, nie aplikacji):**
> 1. **ci.yml `freeze-smoke`: „Brak selftest-report.json obok exe” + pusty `selftest exit code:`** — root-cause: PowerShell **nie czeka** na zakończenie procesu uruchomionego przez `& exe`, gdy exe jest aplikacją *windowed* (GUI subsystem, `console=False`); `$LASTEXITCODE` zostaje pusty, a `Test-Path` raportu wykonuje się, zanim proces zdąży go zapisać. Dowód z logu: dwie linie stdout exe (`selftest-report: …` + JSON z `ok:true`) pojawiły się w logu **po** błędzie kroku, a krok `upload` znalazł plik bez problemu — aplikacja była zdrowa, wyścig był w skrypcie.
> 2. **release.yml `build`: `ConvertFrom-Json … Unexpected character … : s`** — root-cause: `& $exe --selftest | Tee-Object $out` pisał **do tego samego pliku**, który aplikacja zapisywała przez `DONGSTACK_SELFTEST_OUT=$out`; pierwszy znak „s” to linia `selftest-report: …` ze stdout (Tee przechwycił stdout i zanieczyścił raport).
> 3. **Fix (oba workflowy):** `Start-Process -FilePath $exe -ArgumentList "--selftest" -NoNewWindow -Wait -PassThru` → `$p.ExitCode` (deterministyczne czekanie + prawdziwy kod wyjścia), raport czytany **wyłącznie z pliku** wskazanego przez `DONGSTACK_SELFTEST_OUT` (bez Tee, bez parsowania stdout windowed exe). Gate M9 bez zmian: `code -eq 0` **i** `report.ok -eq $true`. W ci.yml ścieżka raportu ustawiana jawnie w `env:` kroku; przy braku pliku krok dumpuje listę katalogu (diagnostyka).
> 4. **Zasada R16 (nowa, §3.2):** frozen exe z `console=False` w skryptach CI/smoke uruchamiamy wyłącznie przez mechanizm **czekający** (`Start-Process -Wait` / pipeline z przechwyconym wyjściem do *innego* pliku niż raport); nigdy `& exe` bez pipeline i nigdy ten sam plik jako cel Tee i `DONGSTACK_SELFTEST_OUT`.
> 5. Regresja: `tests/unit/test_workflows_selftest.py` (statyczna analiza YAML: obecność `Start-Process … -Wait … -PassThru`, zakaz `& … --selftest`, zakaz `Tee-Object` na ścieżce raportu, spójność `DONGSTACK_SELFTEST_OUT` z czytanym plikiem) + `test_selftest_report_env_path_relative` (kontrakt raportu: env względny, poprawny JSON, `ok:true`). Razem 314 testów (`pytest tests/unit tests/gui`, offscreen).
>
>**Changelog v1.2.0 (2026-09-27) — M9: płaskie uniwersa + wpis ręczny + fix CI:**
> 1. **CI freeze-smoke: „Process completed with exit code 1” mimo `ok:true`** — root-cause: frozen **windowed** exe (console=False) po wydrukowaniu raportu potrafił złapać wyjątek w teardown interpretera; windowed excepthook PyInstallera kieruje traceback do NIEWIDZIALNEGO messageboxa (brak stderr), a bootloader zwraca 1. Fix: `selftest()` po flushu raportu robi `os._exit(code)` (frozen) — teardown już nie uczestniczy; każdy wyjątek w ciele łapany i zapisywany do raportu jako `error`. Gate w ci.yml i release.yml czyta teraz **raport JSON (`ok`) + kod wyjścia** (raport = źródło prawdy). Wyjaśnienie obserwacji użytkownika: CI uruchamiało się na każdy push (run #16–#20), ale każdy run ginął na tym samym kroku.
> 2. **Uniwersa bez zwijanych nagłówków (§6.7 M9):** root-cause rozjazdu layoutu (luki/nakładanie z załączników r7) = `uniformItemSizes(True)` + mix wysokości itemów (nagłówek 34 px / karta 96 px). Redesign wg propozycji Właściciela: sort „Uniwersa” = płaska lista kart (bloki uniwersów obok siebie, watch order w bloku), przynależność pokazuje **dwupoziomowe podświetlenie hover** (kursor = mocny tint + pełny pasek akcentu; reszta uniwersum = słaby tint + ćwierć-pasek). Usunięto: `DisplayHeader`, `universe_header.py`, `toggle_universe`, `_collapsed`, obsługa nagłówków w obu backendach.
> 3. **Ręczne dodawanie donghua (PPM na FABie):** seria bez strony na MAL/AniList (np. „Xiuluo Wushen 3” w produkcji) trafia do biblioteki przez formularz ręczny: tytuł*, tytuł alt, rok, typ, status segmentowy, odcinki, uniwersum, linki + **URL okładki z podglądem** (podgląd ściąga NetworkWorker kolejka LOW — R1/R3, debounce 600 ms, wspólny LRU pixmap). Zapis: `mal_id=NULL` + `provider='manual'` + `cover_key=URL` — schemat bez migracji (UNIQUE(mal_id) toleruje NULL-e). Edycja pozycji ręcznej pokazuje te same pola; Esc zamyka dialog (brak „wstecz” do wyszukiwarki). Walidacja: pusty tytuł = zapis wstrzymany + czerwona ramka.
> 4. Testy: `test_universe_flat_m9` (płaskość/kolejność/brak collapse API), `test_universe_hover_m9` (poziomy hoveru widget+row, PPM FAB), `test_manual_add_m9` (formularz/walidacja/kontroler/roundtrip repo/edycja manual), delegate hover zamiast toggle nagłówka; `test_grouping_m5` usunięty. Razem 291 testów.
>
>**Changelog v1.1.0 (2026-09-27) — DelegateListBackend (gate G3):**
> 1. **Pomiary M7 z E5500 (selftest-report.json):** `increment_p95_ms = 0.773` (G2 ≤50 ms ✔, ~60× zapasu), `gui_rebuild300_ms = 1688.7` (G3 ≤150 ms ✘) → zgodnie z §7.4 wjeżdża **DelegateListBackend**: QListView + QAbstractListModel + QStyledItemDelegate (Biblia §43) — malowane wyłącznie widoczne wiersze; `+/−` jako hit-testy w `editorEvent`; nagłówki uniwersów i skeletony w tym samym delegate; tooltipy i menu „przesuń w uniwersum” zachowane. W sandboxie: fill300 174→4.8 ms, rebuild300 494→0.9 ms.
> 2. **Auto-swap:** `DONGSTACK_LIST_BACKEND = auto|widgets|delegate`; `auto` = delegate powyżej 100 widocznych wpisów, widgets poniżej (Biblia: QListWidget jako baza dla małych bibliotek). Kontrakt sygnałów ListBackend wspólny — kontroler i koordynator okładek nie widzą różnicy.
> 3. Sygnały wiersza/nagłówka przeniesione na poziom backendu; koordynator okładek przez `backend.set_cover(url, pixmap)`; model delegate czyta współdzielony LRU pixmap przy paint.
> 4. **Fix uniwersów w dialogu:** `universesChanged` emitowane również przy `on_universes_loaded`, a dialog dostaje świeży rejestr przy każdym otwarciu (combobox „Uniwersum” pusty mimo istniejących uniwersów — raport Windows).
> 5. Testy delegate: klik `+/−` przez viewport (w tym disabled przy 0/12), toggle nagłówka, set_cover, rebuild<100 ms, auto-swap dashboardu, regresja comboboxa. Razem 281 testów.
>
>**Changelog v1.0.1 (2026-09-27):**
> 1. **Crash przy pisaniu „litera po literze”** (RuntimeError: wrapped C/C++ object of type QLabel has been deleted): `SearchPage._cover_rows` trzymał referencje do wierszy usuniętych przez przebudowę listy, a spóźniona okładka dotykała martwego QLabel. Fix: `_clear_list()` czyści mapy wierszy, `apply_cover` odporny (porzuca martwe referencje); regresja testowa „late cover after rebuild”.
> 2. **selftest-report.json ginął w frozen exe**: ścieżka raportu preferowała `DONGSTACK_HOME`, który selftest nadpisuje tmp-em; teraz frozen → katalog exe (bat/ps1 go znajdują), dev → DONGSTACK_HOME/cwd.
> 3. **Sanitaryzacja sekretów (§12):** placeholder w `ClientIdDialog` wymieniony z produkcyjnego Client ID na neutralny przykład; audit repo usunął wyciekłe credentials z testów (zamienione na ewidentnie fałszywe `TESTCLIENTID…/TESTSECRET…`); zero wystąpień prawdziwych wartości w repo.
> 4. MAL HTTP 400 przy niektórych krótkich/frazowych zapytaniach jest obsługiwane: failover AniList serwuje wyniki (widoczne w logu jako WARNING + zamówienia okładek z s4.anilist.co) — zachowanie zgodne z §5.0.
>
> **Changelog v1.0.0 (2026-09-26) — WYDANIE:**
> 1. **M7 zamknięty dowodem z żelaza:** onedir i onefile z release działają na Dell Latitude E5500 (Core 2 Duo T7250, W7 SP1 x64 mod) „od razu”, `--selftest` exit 0; KB2533623/KB2999226/KB4474419 nieobecne i niepotrzebne (runbook: opcjonalne). `tools/smoke_test.bat` (ASCII, dla W7 bez PowerShell — wariant użytkownika przygarnięty i sformalizowany) wypisuje JSON pomiarów jako protokół M7.
> 2. **M8:** wersja aplikacji `1.0.0` (app/__init__ ⇄ version_info), README/runbook aktualne.
> 3. First-run Client ID (§5.5) z live-attach MAL — domknięte w v1.2.0, zweryfikowane w binarce.
>
> **Changelog pre-1.0 (numer draftu „v1.2.0”, przed wydaniem — 2026-09-26):**
> 1. **§5.5 zaimplementowane (first-run Client ID):** `ClientIdDialog` (instrukcja 3 kroków, pole Client ID, „Zapisz i używaj MAL” / „Pomiń (AniList)”) pokazuje się RAZ przy pierwszym starcie bez ID i bez zapisanego „pomiń” (`DONGSTACK_SKIP_CLIENT_ID`), oraz zawsze z menu ⚙ → „Client ID MyAnimeList…”. Zapis = **live-attach** providera MAL bez restartu (`MetadataService.attach_provider`: providers+breaker+preferred w locie) + snack potwierdzający. Client ID nie jest sekretem (§12) — pole jawne, trafia do `config.json`.
> 2. Przy okazji: ruff po odzyskanym `app/data` (lint wcześniej pomijał katalog przez .gitignore) — UP004/E501 wyczyszczone.
> 3. Razem 280 testów.
>
> **Changelog v1.1.19 (2026-09-26):**
> 1. **ROOT-CAUSE „No module named 'app.data'” w CI i w frozen exe:** wzorzec `data/` w `.gitignore` (miał chronić katalog danych użytkownika w roocie repo) jest NIEKOTWICZONY, więc matchował także `app/data/` — git po cichu pomijał cały pakiet przy `git add -A` (lokalnie pliki istniały → testy sandboxa zielone; repo GitHub i buildy z niego = brak modułu). Fix: kotwice `/data/ /logs/ /backups/ /covers/`; `app/data/*` wraca do repo (6 plików); weryfikacja `git check-ignore` + diff ls-files workspace↔GitHub (nic więcej nie brakowało).
> 2. Lekcja procesowa: po każdej zmianie `.gitignore` robimy `git ls-files | grep <pakiet>` jako sanity check; gate'y CI (pytest collection + freeze-smoke) łapią tę klasę błędu od razu.
>
> **Changelog v1.1.18 (2026-09-26):**
> 1. **CI 1603 przy `InstallAllUsers=1`:** runner `windows-2022` ma oficjalnego CPythona 3.13 per-machine (ten sam UpgradeCode MSI) → instalacja Python-Win7 per-machine kończy się fatalem 1603. Powrót do `InstallAllUsers=0` (per-user) + krok **Locate**: kandydaci `%LOCALAPPDATA%\Programs\Python\Python313[-32]` i `Program Files…`, wybór po raporcie `--version == Python 3.13.5`, następnie `GITHUB_PATH` + VERIFY. Determinizm bez konfliktu MSI.
>
> **Changelog v1.1.17 (2026-09-26):**
> 1. **Root-cause walki z CI (20 commitów użytkownika):** instalator Python-Win7 z `InstallAllUsers=0 PrependPath=1` zapisuje PATH w rejestrze, którego procesy trwającego joba NIE dziedziczą — kolejne kroki release.yml korzystały z systemowego interpretera runnera (stąd walka o pythonpath, ręczne łaty haszy w locku dla cp39/cp310 wheeli i w końcu binarka z oficjalnym CPython = „failed to load Python DLL” na czystym Win7). Fix: `InstallAllUsers=1` (deterministyczne `C:\Program Files\Python313` / `(x86)` dla win32) + jawne `Add-Content $env:GITHUB_PATH` + krok VERIFY (sys.executable musi matchować `Python313` i wersję 3.13.5, inaczej twardy fail).
> 2. Lock kanoniczny dla py3.13 (2 hasze na koła binarne amd64+win32, 1 dla `py3-none-any`); ręczne łaty haszy z GitHuba nadpisuje force-push.
> 3. Przywrócone testy usunięte na GitHubie (HEAD `acc02ce`); `freeze-smoke` w ci.yml zostaje jako gate brakujących modułów w frozen binary.
>
> **Changelog v1.1.16 (2026-09-26):**
> 1. **Bug: „nie można stworzyć uniwersum”** — `DbWorker.createUniverse` wołał `repo.create(...)` na `DonghuaRepository`, podczas gdy `create()` siedzi w `UniverseRepository` (`self._universes`); AttributeError zabijał cały łańcuch sugestii (create→attach). Fix + regresja testowa create/attach/load.
> 2. **Bug: „edycja milczy, dopóki nie otworzę raz AddDialogu”** — `controller.editRequestedFull` było podłączane WENĄTRZ `_open_add_dialog`, więc subscriber istniał dopiero po pierwszym kliknięciu `+`. Refaktoryzacja: `_ensure_dialog()` (leniwe tworzenie + komplet wiringu) oraz podłączenie `editRequestedFull → _open_edit` na poziomie `run_gui`; regresja testowa pilnuje wcięcia/poziomu tego connectu w źródle.
> 3. Razem 275 testów.
>
> **Changelog v1.1.15 (2026-09-26):**
> 1. **ROOT-CAUSE „pustego dashboardu po restarcie” (wyścig inicjalizacji):** `db_thread.start()` odpalał `loadLibrary` milisekundy po utworzeniu wątku — EMISJA `libraryLoaded` następowała zanim `DashboardController` istniał i subskrybował sygnał, więc zdarzenie ginęło bez odbiorcy; GUI zostawało na skeletonach mimo pełnej bazy (log: „wczytana: N pozycji”). Fix: starty obu wątków dopiero po kompletnym okablowaniu kontrolerów/koordynatora; regresja testowa pilnuje kolejności w źródle `run_gui`.
> 2. Dedupe zapisu `cover_cache`: ten sam url zapisywany dokładnie raz na sesję (podwójne linie „cover_cache: zapis” w logu użytkownika).
> 3. Razem 273 testy.
>
> **Changelog v1.1.14 (2026-09-26):**
> 1. **Pamiętany kontekst widoku (QoL, ból „pusty dashboard po restarcie”):** ostatni filtr statusów i sort zapisują się w `config.json` (`DONGSTACK_LAST_FILTER/SORT`); start odtwarza widok, w którym użytkownik skończył pracę (sidebar i tytuł sekcji zsynchronizowane). Pierwszy start nadal „W trakcie” (Biblia §68.2).
> 2. **Quick-add duplikatu nie udaje dodawania:** pozycja żyjąca już w bibliotece → snack „„X” już jest w bibliotece (status). Kliknij kartę, aby edytować.” bez zapisu do bazy (koniec z „dodałem 10 razy xian ni”); snack po realnym dodaniu podaje faktyczny status zapisu, nie sztywne „Planowane”.
> 3. **Logi okładek wyciszone do DEBUG** (prośba użytkownika): w INFO/WARNING/ERROR zostają tylko błędy i ostrzeżenia; pełna ścieżka dostępna przez `--verbose` lub `DONGSTACK_LOG_LEVEL=DEBUG`.
> 4. Regresje: duplikat quick-add, restore filtra/sortu z configu, synchronizacja sidebara. Razem 271 testów.
>
> **Changelog v1.1.13 (2026-09-26):**
> 1. **ROOT-CAUSE braku okładek (log użytkownika: „zamawiam N” i cisza):** pierwsze wyszukiwanie wołało `cancel(0)` (anulowanie „poprzedniego” rid, którego nie było), a taski okładek/backfillu miały `rid=0` → pętla workera wyrzucała je jako anulowane PRZED jakimkolwiek HTTP (stąd zero logów i pusty `cover_cache`). Fix: taski okładek/backfillu mają `rid=None` (niepodległe anulowaniu), a `_fire_search` anuluje wyłącznie realne poprzednie rid (`prev > 0`). Regresje: `cancel(0)` nie zabija covera; pierwsze szukanie nie anuluje zera.
> 2. „Dashboard pusty po restarcie” = domyślny filtr „W trakcie” przy pozycjach w Planowanych/Obejrzanych (log potwierdzał wczytanie); nota empty-state z v1.1.12 tłumaczy to w UI.
> 3. Razem 274 testy unit+GUI + 5 live.
>
> **Changelog v1.1.12 (2026-09-26):**
> 1. **Bug produkcyjny UNIQUE(mal_id):** soft-delete zostawiał wiersz z unikalnym `mal_id`, więc ponowne dodanie usuniętej serii crashowało insert. `DonghuaRepository.insert` teraz **wskrzesza** miękko usunięty wiersz (UPDATE z `deleted_at=NULL` i świeżymi metadanymi), a żywy duplikat zwraca istniejące id bez nadpisania (badge „✓ Już w bibliotece” pozostaje prawdą).
> 2. **QoL pustego widoku:** startowy filtr „W trakcie” z pustą listą podpowiada teraz „Masz N pozycji w innych statusach — zerknij na sidebar” (MainWindow.set_counts), żeby restart nie wyglądał jak utrata danych.
> 3. **Diagnostyka okładek (prośba użytkownika):** logi INFO/DEBUG na całej ścieżce — zamówienie par (koordynator), task w kolejce workera, start cover, źródło/zapis do `cover_cache`; po następnej sesji na Windows jeden rzut oka w log powie, gdzie łańcuch się urywa.
> 4. Regresje: revive po usunięciu, duplikat żywy bez wyjątku, coversRequested przy starcie, nota empty-state. Razem 272 testy.
>
> **Changelog v1.1.11 (2026-09-26):**
> 1. **Runda 4 feedbacku z Windows:** (a) sekcja linków: „Dodaj link” przyklejony NA GÓRZE, wiersze od góry do dołu, luz na dole strony (AdvancedPage bez stretcha); (b) **Ctrl+V** w oknie dodawania/edycji z URL-em w schowku = nowy wiersz linku z auto-TAG-iem (focus w polu edycji = zwykłe wklejenie; tekst nie-URL ignorowany); (c) **PPM na karcie = wyłącznie menu kontekstowe** (LPM otwiera edycję — wcześniej oba naraz); (d) **kasowanie pozycji**: czerwony przycisk z koszem w edycji → soft-delete + SnackBar „Usunięto … [Cofnij]” (Undo zamiast Confirm, Biblia §9), kosz widoczny tylko w trybie edycji.
> 2. **Okładki — aspect 225/318 i fallback CDN:** karty 57×80 / wyniki 44×62 / decode 120×170; zadanie cover niesie `mal_id`, a przy niedostępności CDN MAL worker ciągnie okładkę z **CDN AniList** (`covers_for_mal` po `idMal`, key cache = oryginalny URL); logi INFO/WARNING z źródłem okładki; **backfill** starych pozycji bez `cover_key` (details → URL → cover). Live-testy na prawdziwym API: pipeline MAL CDN ✔ i symulowana blokada CDN MAL → fallback AniList ✔.
> 3. Razem 268 testów unit+GUI + 5 live.
>
> **Changelog v1.1.10 (2026-09-26):**
> 1. **Fixy rundy 3 z Windows:** (a) `QDesktopServices` importowany z `PyQt5.QtGui` (nieistniejący moduł `QtDesktopServices` crashował „Otwórz folder danych”); (b) **freeze + „duch” zaznaczenia** przy zmianie filtra: `unpolish/polish` na property-selectorach QSS wymienione na scoped inline stylesheet + jawne `update()` w `NavItemWidget.set_active` (repolish całego arkusza na Win7/GMA = wielosekundowy zwis i brak repaintu); (c) **AddDialog „nie otwierał się”** po kliknięciu FAB: na Windows potrafił wystartować ZA MainWindow → flaga `Qt.Tool | WindowCloseButtonHint` (zawsze nad rodzicem).
> 2. Regresje: `_open_data_dir` bez ImportError, dialog z flagą Tool, sidebar `is_active` + inline QSS. Razem 264 testy.
>
> **Changelog v1.1.9 (2026-09-26):**
> 1. **Druga runda feedbacku z Windows:** (a) EDYCJA: `editSaveRequested` nie było podłączone w main — Zapisz w trybie edycji tylko cofał do wyszukiwarki; teraz edytuje realnie (`saveFull`) i zamyka dialog, tytuł okna „Edytuj: <tytuł>"; (b) AddDialog po ponownym otwarciu czyści pole szukania; Enter = natychmiastowe szukanie (`force_search`); (c) segmenty statusów w AdvancedPage kolorowane jak kropki statusów (property `status` + QSS,checked/=pełny kolor, niechecked/=jaśniejszy wariant); (d) linki streamingowe: **[TAG][URL]** zamiast comboboxa platform — TAG auto-wycinany z domeny URL na żywo, edytowalny ręcznie; schemat SQLite **v2** (migracja v1→v2 z zachowaniem danych i backupem); (e) edytowalna liczba odcinków (MAL `??`/emisja w toku; 0 = nieznane); (f) przycisk **Ustawień** obok sortowania: „Otwórz folder danych" przez `QDesktopServices` (uniwersalne dla każdego %LOCALAPPDATA%).
> 2. **Okładki — diagnostyka i backfill:** pipeline okładek zweryfikowany end-to-end w sandboxie (HTTP+dekodowanie+Pixmap na wierszu = OK), więc brak okładek u użytkownika jest środowiskowy: dodane logi WARNING (HTTP/decode) w pliku logu do diagnozy; **backfill starych pozycji**: wiersz z `mal_id` bez `cover_key` zgłasza (raz) `backfillRequested` → worker ciągnie `details` → `cover_key` zapisywany do DB i okładka dochodzi bez ponownego dodawania.
> 3. Razem 262 testy zielone (nowe: migracja v1→v2, edit-flow e2e, reset dialogu, force_search, TAG auto/manual, Ustawienia, property statusów, backfill ×3).
>
> **Changelog v1.1.8 (2026-09-26):**
> 1. **Fixy po testach na Windows (raport Właściciela):** (a) `AttributeError: AddController.snackbar_timeout_ms` — crash snackbara przy pierwszym dodaniu (убijał cały feedback dodawania); (b) okładki w wynikach wyszukiwania: wspólny LRU pixmap (`SharedPixmaps`) + `CoverCoordinator.request_urls` + `SearchPage.set_cover_requester/apply_cover` — wiersze MAL wyników zamawiają okładki kolejką LOW i podstawiają je bez ponownego dekodowania; (c) `SearchPage.mark_in_library` po Quick/Advanced Add (badge „✓ Już w bibliotece” bez ponownego szukania); (d) wyjaśnienie „zero reakcji”: Quick Add świadomie ląduje w Planowanych (Biblia §24) — po fixie snackbara SnackBar+badge sidebara dają natychmiastowy feedback.
> 2. Regresje produkcyjne w `tests/gui/test_m6_production_regressions.py` (5 testów): _show_snack z AddControllerem, quick-add end-to-end z Undo, advanced-add widoczny na ekranie startowym, okładki wyników (request→LRU→apply), mark_in_library. Razem 249 testów.
>
> **Changelog v1.1.7 (2026-09-26):**
> 1. **Poprawka po pierwszym CI (push użytkownika):** (a) `quality` — kod sformatowany `ruff format` + domknięcie lintu (B904/E501/SIM102/E731/F841…); `UP031` (%-format) dodane do ignore jako celowy styl; (b) `freeze-smoke` — frozen selftest spadał z `ModuleNotFoundError: No module named 'app.data'`: PyInstaller nie domknął leniwych importów wewnątrz funkcji entrypointu → `hiddenimports = ["sqlite3"] + collect_submodules("app")` w `packaging/dongstack.spec` + regresja w `test_spec_logic.py` (asercja obecności app.data/app.gui/app.workers w hiddenimports).
> 2. Stan po poprawkach: ruff check+format clean, 242 testy zielone.
>
> **Changelog v1.1.6 (2026-09-26):**
> 1. **M6 dostarczony (część sandboxowa):** testy logiki `packaging/dongstack.spec` bez freezera (stub Analysis/PYZ/EXE/COLLECT: entrypoint, datas, excludes, filtr `_keep` translacji/pluginów, gałęzie onedir/onefile, twarde reguły upx=False/console=False), testy pinów supply-chain (`python-win7.json`, pokrycie `requirements.lock.txt` hashami obu architektur Windows, sync `version_info.txt` ⇄ `app.__version__`, referencje w workflow), nowy job **`freeze-smoke`** w `ci.yml` (windows-2022: PyInstaller 6.11.1 onedir + frozen `--selftest` offscreen — gate uszkodzeń .spec na każdym PR), `packaging/RELEASE_RUNBOOK.md` (tag → release → weryfikacja E5500 → rollback; udokumentowane ograniczenie: Linux ze statycznym CPython nie freeze'uje).
> 2. Razem 242 testy unit+GUI zielone.
>
> **Changelog v1.1.5 (2026-09-26):**
> 1. **M5 dostarczony:** okładki async (NetworkWorker LOW → QImage skalowane w workerze → QPixmap w GUI (R3) → LRU 64 → zapis plik+indeks przez DbWorker.saveCover (R2); dysk-first w kolejnych sesjach), AdvancedPage (segmentowe statusy, QSpinBox z capem, StreamingLinksWidget, wybór uniwersum „istniejące/nowe/brak”, tryb edycji istniejącej pozycji z rollbackiem), grupowanie uniwersów na dashboardzie (§6.7: UniverseHeaderRow z badge i collapse, watch_order z relacji + override'y „przesuń ↑/↓” w menu kontekstowym), screenshot `docs/screenshots/universes.png`.
> 2. Razem 231 testów unit+GUI zielonych; selftest M4-api bez regressji (p95 `+1` = 0.30 ms).
>
> **Changelog v1.1.4 (2026-09-26):**
> 1. **M4 dostarczony:** `MalClient` (X-MAL-CLIENT-ID, limit≤100, taksonomia błędów z 403-HTML i Retry-After), `AnilistClient` (GraphQL, errors[] przy HTTP 200), `MetadataService` (cache-first 6 h/7 dni, failover, breakery, stale-if-error), `NetworkWorker` (kolejka priorytetowa HIGH=search/LOW=related, token buckety per provider, retry+backoff, cancel po request_id), `AddController` (debounce 450 ms, stany IDLE/SEARCHING/RESULTS/NO_RESULTS/ERROR, Quick Add = Planowane+0, duplikaty bez blokady), `AddDialog`+`SearchPage` (non-modal, skeleton statyczny, retry bez utraty zapytania).
> 2. **Uniwersa cd. (§5.6):** po Quick Add leniwe `related_anime` (LOW) → `UniverseSuggester` → SnackBar „Połączyć … z uniwersum …? [Połącz]” → create/attach przez DbWorker; sugestie nie dotykają ścieżki Quick Add.
> 3. Testy live opt-in przeciw produkcyjnemu MAL: 3/3 OK (search schema, graf related 37176, 400 na limit=1500). Razem 146 testów unit+GUI zielonych.
>
> **Changelog v1.1.3 (2026-09-26):**
> 1. **M3 dostarczony:** `DbWorker` (QThread, koalescencja zapisów 250 ms, ack/nack, flush+checkpoint przy zamknięciu) + `DashboardController` (optymistyczny `+1/−1`, auto-complete z Undo, rollback po błędzie zapisu, filtry/sort/lokalne szukanie w pamięci, request_id kontra stale-ack).
> 2. **Korekta projektowa §4.6:** koalescencja realizowana przez `QTimer.singleShot` tworzony w wątku wywołania + strażnika wątku właściciela połączenia (`_owner_ident`), zamiast timera-QTimer będącego członkiem obiektu — pomiary M3 wykazały pułapki afiliacji timera między wątkami (flush potrafił wykonać się w złym wątku → cross-thread SQLite). Reguła R2 nienaruszona.
> 3. Wyniki selftestu M3 (sandbox offscreen): p95 handlera `+1` = **0.25 ms** (gate G2 ≤ 8 ms), fill 300 = 179 ms, rebuild 300 = 499 ms (obserwacja pod gate G3/M7), wątki = 1.
>
> **Changelog v1.1.2 (2026-09-26):**
> 1. **M1 dostarczony:** rdzeń danych (migracje+backup+recovery, repozytoria, cache, cover store), `watch_order`, warstwa odporności sieci (TokenBucket/backoff/breaker), 113 testów jednostkowych zielonych.
> 2. **M2 dostarczony:** GUI statyczne zgodne z Biblią (MainWindow, sidebar z badge'ami, karty DonghuaRow, skeleton, SnackBar+Undo, FAB overlay, 5 warstw QSS flat dark), selftest z fazą GUI, screenshot `docs/screenshots/dashboard.png`, branding generowany kodem (w tym ciemny wariant `+` dla FAB).
> 3. Katalog `build/` → **`packaging/`** (nazwa `build` jest wyłączona z persistence środowiska deweloperskiego; na GitHubie bez znaczenia). Ścieżki w CI/README/narzędziach zaktualizowane.
> 4. Pomiar M2 (sandbox Linux offscreen, NIE E5500): fill 300 wierszy 435 ms, rebuild 635 ms, update 200 wierszy 5.7 ms → decyzja gate G3 (DelegateListBackend) pozostaje otwarta do pomiaru na E5500 w M7; gorąca ścieżka `+1` nie dotyka przebudowy listy (§6.2).
>
> **Changelog v1.1 (2026-09-26):**
> 1. Decyzje D1–D8 zatwierdzone (§15) — m.in. x64 jako arch. bazowa, onedir ZIP rekomendowany / onefile portable, brak OAuth2 w v1 (tracker w 100% lokalny), MIT, `--require-hashes` w release.yml.
> 2. **Nazwa produktu (D7): `DongStack`** — repo `github.com/karnyjohnny/dongstack`, exe `DongStack.exe`, dane w `%LOCALAPPDATA%\DongStack\`. Nazwa zweryfikowana: wolna na GitHub (0 trafień) i PyPI (404). Logo i ikony generowane programowo w Pythonie (`tools/generate_branding.py`, Pillow — dev-only).
> 3. **Nowy wymóg produktowy: UNIWERSA** — łączenie serii w łańcuchy prequel/sequel i wyświetlanie na dashboardzie w kolejności oglądania (S1 → S2 → … → filmy → specjały). Projekt: §4.9 (model + algorytm watch-order), §5.1/§5.6 (MAL `related_anime` — zweryfikowany live), §6.7 (grupowanie na dashboardzie). Schemat SQLite v1 rozszerzony PRZED pierwszym wydaniem (bez migracji danych).
> 4. Potwierdzenie D4: maszyna docelowa działa na buildzie **Python-Win7 (Alex313031) 3.13.5** + pip 25.1.1 + PyQt5 5.15.11 — Track A zweryfikowany u Właściciela (import Qt działa); M0 redukuje się do testu freeze/launch.
> 5. Licencja: źródła MIT; uwaga o GPL v3 PyQt5 w binariach (§12.3).
>
> **Konwencja nazewnicza dokumentu:** historyczne wystąpienia starej nazwy roboczej (`DonghuaTracker` / `donghua-tracker`) w przykładach odpowiadają `DongStack` / `dongstack` w implementacji; kluczowe miejsca zostały zaktualizowane wprost.

---

## SPIS TREŚCI

- §0. Streszczenie weryfikacyjne (co zostało sprawdzone namacalnie)
- §1. Cele produktu i budżety nadrzędne
- §2. Platforma docelowa i macierz kompatybilności (Track A / Track B)
- §3. Architektura systemu i struktura plików
- §4. Warstwa danych: SQLite, repozytorium, cache
- §5. Integracja z API zewnętrznymi (MAL / AniList), rate limiting, backoff
- §6. Podsystem GUI — przełożenie Biblii GUI na wymagania techniczne
- §7. Budżety wydajnościowe i pomiar
- §8. Freezing: PyInstaller (plik .spec)
- §9. CI/CD: GitHub Actions
- §10. Strategia testów
- §11. Struktura README.md
- §12. Bezpieczeństwo i sekrety
- §13. Rejestr ryzyk
- §14. Plan implementacji (kamienie milowe M0–M8)
- §15. Decyzje — rozstrzygnięte (D1–D8 + nowe wymagania v1.1)
- §16. Standardy kodowania (baseline składniowy Python 3.8)
- §17. Źródła i dziennik testów live
- Załącznik A: Odrzucone alternatywy technologiczne

---

# §0. STRESZCZENIE WERYFIKACYJNE

Niniejsza specyfikacja **nie opiera się na założeniach**. Poniższe fakty zostały zweryfikowane praktycznie w dniu 2026-09-26 (testy live API, zapytania do PyPI JSON API, dokumentacja oficjalna):

| # | Fakt | Metoda weryfikacji | Wynik |
|---|------|--------------------|-------|
| F1 | Oficjalny CPython 3.13.x **nie działa na Windows 7** ("Python 3.13 cannot be used on Windows 7 or earlier"); ostatnia oficjalna wersja na Win7 to 3.8.10 | python.org/downloads/windows, endoflife.date/python | POTWIERDZONE |
| F2 | Istnieje **nieoficjalny build Python 3.13.5 dla Windows 7 SP1** (projekt Alex313031/Python-Win7), w wariantach amd64 i win32, z pełnym instalatorem | GitHub API (listing katalogu `3.13.5`) | POTWIERDZONE — pliki `python-3.13.5-amd64-full.exe` (81 884 004 B) i `python-3.13.5-full.exe` x86 (77 753 711 B); oba pobrane, SHA256 obliczone (patrz §9.3) |
| F3 | **PyQt5 5.15.11** publikuje koła `cp38-abi3` dla `win32` i `win_amd64` → działa na Python 3.8 **i** 3.13 (limited API) | PyPI JSON API | POTWIERDZONE |
| F4 | **PyQt5-Qt5 (runtime Qt) na Windows istnieje TYLKO w wersji 5.15.2** — nowsze wydania (5.15.11+, 5.15.19) nie mają kół Windows (Qt 5.15.3+ LTS był komercyjny). `pip install PyQt5==5.15.11` na Windows i tak rozwiąże się do Qt 5.15.2 | PyPI JSON API (enumeracja wszystkich wydań) | POTWIERDZONE — to NASZA KORZYŚĆ: Qt 5.15 oficjalnie wspiera Windows 7 x86/x64 |
| F5 | **Qt 5.15 wspiera Windows 7** (x86 i x86_64, MSVC 2019) | dokumentacja "Supported Platforms — Qt 5.15" | POTWIERDZONE |
| F6 | **PyQt5-sip 12.19.0** ma koła `cp313-win32/win_amd64` (Track A); **12.15.0** ma koła `cp38` (Track B) | PyPI JSON API | POTWIERDZONE |
| F7 | **PyInstaller**: README oficjalne — "should work on Windows 7 or newer, but we only officially support Windows 8+"; od changelogu v6.11 bootloader jest kompilowany z jawnym "Windows 7 feature level" dla nagłówków Windows | github.com/pyinstaller, pyinstaller.org CHANGES v6.11.0 | POTWIERDZONE → pin `pyinstaller==6.11.1` |
| F8 | PyInstaller jako **narzędzie budujące** wymaga Windows 8+ (host CI: `windows-2022` — OK) | pyinstaller.org/en/stable/requirements.html | POTWIERDZONE |
| F9 | **MAL API v2 działa z nagłówkiem `X-MAL-CLIENT-ID`** dla endpointów publicznych (bez OAuth2, bez Client Secret!). Wykonano realne zapytania produkcyjne (Client ID z zadania): `GET /v2/anime?q=…` → HTTP 200; `GET /v2/anime/{id}?fields=…` → HTTP 200; `GET /v2/anime/ranking?ranking_type=airing` → HTTP 200 | test live z sandboxa, 2026-09-26 | POTWIERDZONE — schematy odpowiedzi zarejestrowane w §5.1 i Załączniku B |
| F10 | Walidacja parametrów MAL: `limit=1500` → HTTP 400 `{"message":"limit","error":"bad_request"}`; `limit=500` → HTTP 200 (brak błędu, ale wynik przycięty). Bezpieczny zakres produkcyjny: `limit ≤ 100` | test live | POTWIERDZONE |
| F11 | **Jikan (nieoficjalne API MAL): publiczna instancja zostanie wyłączona 1 października 2026** (ogłoszenie na Discordzie, issue jikan-rest#610). Dodatkowo Jikan nigdy nie wspierał operacji uwierzytelnionych | github.com/jikan-me/jikan-rest/issues/610 | POTWIERDZONE → Jikan wykluczony z architektury |
| F12 | **AniList GraphQL działa bez uwierzytelnienia**: `POST https://graphql.anilist.co` → HTTP 200 (test live). Limit: API w stanie zdegradowanym — **30 req/min** (docelowo 90 req/min), odpowiedź 429 zawiera `Retry-After`, `X-RateLimit-Limit/Remaining/Reset`, dodatkowo burst-limiter | test live + docs.anilist.co/guide/rate-limiting | POTWIERDZONE |
| F13 | MAL **nie publikuje** oficjalnych limitów zapytań; zgłoszenia 429 (Too Many Requests) z produkcyjnego API są udokumentowane na forum MAL; przy agresywnym throttlingu MAL potrafi też odpowiedzieć 403 z generyczną stroną HTML | forum MAL: topicid=1547561, topicid=1991772 | POTWIERDZONE → projektujemy konserwatywnie: ≤ 1 req/s + backoff wykładniczy (§5.4) |
| F14 | Wszystkie piny bibliotek z §2.4 istnieją na PyPI, mają koła `py3-none-any` lub binaria Windows (brak kompilacji na maszynie docelowej), a ich `requires_python` pokrywa oba tracki | PyPI JSON API | POTWIERDZONE |
| F15 | **MAL `related_anime` działa i wystarcza do budowy uniwersów**: dla `id=37176` zwrócono `prequel → 36491 (S1)`, `sequel → 38436 (S3)`, `side_story → 36561, 39178`, `prequel → 51038 (Yuanqi)` | test live 2026-09-26 (`fields=id,title,related_anime,…` → HTTP 200); nagranie: `tests/fixtures/mal_related_37176.json` | POTWIERDZONE — fundament §4.9 |
| F16 | Nazwa **DongStack** jest wolna: GitHub repo search `total_count=0`, PyPI `dongstack` → 404 | GitHub Search API + PyPI, 2026-09-26 | POTWIERDZONE (D7) |

**Konsekwencja F1+F2 (najważniejsza decyzja całej specyfikacji):** zadeklarowane środowisko "Python 3.13.5 na Windows 7" jest osiągalne wyłącznie przez nieoficjalny build Python-Win7 (albo przez zmodyfikowany system typu "Windows JG 2021" z rozszerzonym jądrem — co wyjaśnia, dlaczego Python 3.13.5 już działa na maszynie Zamawiającego). Architektura przyjmuje to jako **Track A (główny)** i definiuje **Track B (awaryjny: oficjalny Python 3.8.10)** jako w pełni odtwarzalną ścieżkę zapasową, która NIE wymaga zmian w kodzie (patrz §16 — baseline składniowy 3.8).

---

# §1. CELE PRODUKTU I BUDŻETY NADRZĘDNE

## 1.1. Produkt

Osobisty, lokalny tracker donghua (chińskich animacji) na pulpit Windows. Ekran główny odpowiada wyłącznie na dwa pytania: *co aktualnie oglądam?* i *na którym jestem odcinku?*. Najczęstsza czynność (zmiana odcinka) = **jedno kliknięcie**, zero dialogów, zero czekania.

## 1.2. Nadrzędne rygory (źródło: zadanie + Biblia GUI §68)

1. **Zero operacji sieciowych i ciężkiego I/O w wątku GUI.** Zamrożenie okna ≥ 100 ms jest błędem krytycznym (defect, nie "known issue").
2. **Budżet pamięci:** aplikacja + interpreter ≤ 250 MB prywatnego zestawu roboczego przy 300 pozycjach w bibliotece (maszyna ma 2 GB RAM współdzielone z OS).
3. **Płaski dark mode bez efektów GPU/CPU-żernych**: zakaz `QGraphicsBlurEffect`, `QGraphicsDropShadowEffect`, gradientów animowanych, równoległych animacji wielu kart.
4. **Undo zamiast Confirm**, optymistyczny update, skeleton zamiast pustego ekranu, progressive disclosure (Quick Add vs Advanced).
5. **Jeden plik `.exe`** jako artefakt dystrybucyjny (onefile) **oraz** wariant onedir (rekomendowany na E5500 — uzasadnienie w §8.1), budowane w CI z tagów, z sumami SHA256.
6. **Reprodukowalność:** wszystkie zależności przypięte co do patcha; build CI deterministyczny (ten sam commit → ten sam zestaw artefaktów; binarnie bajt-w-bajt nie jest wymagany, wersje — tak).
7. **Sekrety nigdy w kodzie, logach, README ani testach** (§12).
8. **Baza lokalna SQLite**, GUI nie wykonuje SQL; przepływ UI → Controller/Service → Repository → SQLite.
9. **Odporność sieciowa:** lokalna kolejka zapytań, token bucket, exponential backoff z jitterem, respektowanie `Retry-After`, cache lokalny, graceful degradation (serwowanie danych przestarzałych przy braku sieci), awaryjny provider AniList.

## 1.3. Kryterium sukcesu ("definicja demonicznej szybkości")

Na Dell Latitude E5500 (Core 2 Duo T7250, 2 GB DDR2, GMA 4500MHD, HDD 5400 rpm, Windows 7 SP1):

| Interakcja | Budżet |
|---|---|
| klik `+` → widoczna zmiana licznika | **≤ 50 ms** (cel: < 16 ms, tj. 1 klatka) |
| start zimny (onedir) → okno interaktywne | ≤ 3,5 s |
| start gorący → okno interaktywne | ≤ 2,5 s |
| przełączenie filtra statusu (300 pozycji) | ≤ 150 ms |
| keystroke lokalnego wyszukiwania → przefiltrowana lista | ≤ 20 ms |
| wynik wyszukiwania MAL z cache → wyrenderowana lista | ≤ 50 ms |
| CPU w spoczynku (bez animacji) | ≤ 1% (praktycznie 0) |

Pomiar: wbudowany `--selftest` (§7.3) + stoper/profilowanie w M0 i M7.

---

# §2. PLATFORMA DOCELOWA I MACIERZ KOMPATYBILNOŚCI

## 2.1. Profil sprzętowo-systemowy

| Element | Wartość | Konsekwencja architektoniczna |
|---|---|---|
| CPU | Intel Core 2 Duo T7250, 2×2.0 GHz, Merom, SSE3, 64-bit | Maks. **3 wątki aplikacji** (GUI + Network + DB); brak wątków per-żądanie; brak `QThreadPool` o dużym `maxThreadCount`; brak paralelizmu spekulacyjnego |
| RAM | 2 GB DDR2 (2×1024 MB) | Twardy budżet 250 MB (§1.2.2); dekodowanie okładek ze skalowaniem (`QImageReader.setScaledSize`); bounded LRU dla piksmAP; zakaz trzymania surowych odpowiedzi JSON po sparsowaniu |
| GPU | Intel GMA 4500MHD | **Tylko Qt Widgets + raster paint engine.** Zakaz Qt Quick/QML (scenegraf OpenGL), zakaz efektów `QGraphicsEffect` na listach, zakaz animowanych gradientów. ANGLE/D3D nie jest używane |
| Dysk | HDD 5400 rpm (typowo dla E5500) | `PRAGMA synchronous=NORMAL` + WAL; koalescencja zapisów (§4.5); **onedir zamiast onefile jako rekomendacja** (onefile rozpakowuje ~150 MB do %TEMP% przy każdym starcie); leniwe ładowanie okładek z dysku |
| OS | Windows 7 SP1 ("JG 2021"), **x64 — potwierdzone (D1)**; artefakt win32 pozostaje w CI (działa też na x64) | Patrz F1/F2: Track A (Python-Win7 3.13.5 — **potwierdzony na maszynie Właściciela, D4**) / Track B (oficjalny 3.8.10); font systemowy **Segoe UI** (obecny w Win7); ścieżki przez `%LOCALAPPDATA%`; brak API Win8+ w kodzie aplikacji |
| Sieć | Wolne WiFi typicalnie | timeouty 5/10 s; cache-first; skeleton states; retry z backoffem |

## 2.2. Dwutorowość runtime'u (Track A / Track B)

### Track A — GŁÓWNY: Python 3.13.5 (build Python-Win7)

- Interpreter: **nieoficjalny build `Alex313031/Python-Win7`, wersja 3.13.5**, instalator pełny (amd64 lub win32 zależnie od bitowości systemu docelowego), przypięty w CI przez **commit SHA + SHA256 pliku** (§9.3).
- Uzasadnienie: Zamawiający deklaruje Python 3.13.5 działający na maszynie docelowej; projekt Alex313031/Python-Win7 to utrzymywane, patchowane buildy CPython działające na Windows 7 SP1 i Server 2008 R2 (a także na nowszych Windows — co pozwala budować i testować w CI na `windows-2022`).
- Ryzyko: build nieoficjalny → mitygacja: pin commita + checksum + test dymny M0 na fizycznym E5500 ZANIM powstanie jakikolwiek kod produkcyjny.
- **Status D4 (2026-09-26): POTWIERDZONY przez Właściciela** — na maszynie docelowej działa venv z Python 3.13.5 (build Python-Win7/Alex313031), pip 25.1.1, PyQt5 5.15.11 (import Qt OK). M0 redukuje się do: freeze hello-world PyInstallerem 6.11.1 → launch obu wariantów exe na Win7.
- Skład kodu: baseline składniowy **3.8** (§16), więc kod działa identycznie na obu trackach.

### Track B — AWARYJNY: oficjalny Python 3.8.10 (ostatni wspierający Win7)

- Aktywowany automatycznie, gdyby M0 na Track A zakończył się niepowodzeniem (np. Qt 5.15.2/MSVC2019 runtime nie wstanie na konkretnej instalacji JG 2021).
- Różnice: `PyQt5-sip==12.15.0` (koła cp38), `pyinstaller==5.13.2` (ostatnia linia 5.x, `requires_python <3.13,>=3.7`, bootloader sprawdzony na Win7), pozostałe piny BEZ ZMIAN (dobrano je tak, by `requires_python` obejmowało 3.8 — tabela §2.3).
- Koszt przełączenia: wyłącznie pliki `requirements*.txt` + wersja instalatora Pythona w workflow (parametr matrix). **Zero zmian w kodzie.**

> Decyzja: requirements używają markerów środowiskowych `python_version`, dzięki czemu jeden plik obsługuje oba tracki (listing w §2.4).

## 2.3. Macierz weryfikacji zależności (rygor zadania: runtime / Win7 / architektura / TLS / pamięć / wheel)

| Biblioteka | Pin | Python (requires) | Win7 | Arch (koła) | TLS/HTTPS | Pamięć/rozmiar | Uzasadnienie |
|---|---|---|---|---|---|---|---|
| **PyQt5** | 5.15.11 | ≥3.8 (wheel `cp38-abi3` → 3.8…3.14) | ✔ przez Qt 5.15.2 | win32 + win_amd64 | n/d | ~6 MB wheel | GUI. Limited API (abi3) = jedno koło dla wszystkich Pythonów 3.x |
| **PyQt5-Qt5** | 5.15.2 | brak wymagań (py3-none) | ✔ (Qt 5.15 oficjalnie wspiera Win7 x86/x64, F5) | win32 + win_amd64 (F4: jedyna wersja z Windows!) | n/d | ~45 MB wheel; ~120 MB po rozpakowaniu (w tym nieużywane moduły — Patrz excludes §8.2) | Runtime Qt. Wersja wymuszona przez dostępność kół Windows — i dokładnie ta, która wspiera Win7 |
| **PyQt5-sip** | 12.19.0 (py≥3.10) / 12.15.0 (py<3.10) | patrz pin | ✔ | cp313-win32/amd64; cp38-win32/amd64 | n/d | <1 MB | Binding sip; piny zweryfikowane na PyPI (F6) |
| **requests** | 2.32.3 | ≥3.8 | ✔ (czysty Python; TLS robi OpenSSL wbudowany w CPython, nie schannel) | py3-none-any | TLS 1.2/1.3 przez `ssl` CPython (OpenSSL 3.x w buildach 3.13; 1.1.1 w 3.8) — Win7 SP1 obsługuje TLS 1.2 na winsock | ~1 MB | Klient HTTP (sync, wywoływany WYŁĄCZNIE z NetworkWorker). Wybrany zamiast httpx — patrz Załącznik A |
| **urllib3** | 2.2.3 | ≥3.8 | ✔ | py3-none-any | j.w. | ~1 MB | Zależność requests; pin konserwatywny (2.2.x = ostatnia gałąź z `>=3.8`) |
| **certifi** | 2026.7.22 | ≥3.7 | ✔ | py3-none-any | wiązka CA — podstawa weryfikacji certyfikatów MAL/AniList | ~0.6 MB | Pin = zamrożony stan CA na dzień specyfikacji; aktualizacja świadoma, nie automatyczna |
| **charset-normalizer** | 3.4.3 | ≥3.7 | ✔ | py3-none-any (+opcjonalne akceleratory C — fallback czysto-Pythonowy zawsze działa) | n/d | ~0.5 MB | Dekodowanie odpowiedzi requests |
| **idna** | 3.11 | ≥3.8 | ✔ | py3-none-any | n/d | ~0.3 MB | Domeny IDN (requests) |
| **sqlite3** | stdlib CPython (SQLite ≥3.45 w 3.13; ≥3.31 w 3.8) | wbudowany | ✔ (sqlite3.dll w bundlu CPython) | wbudowany | n/d | 0 | Baza lokalna — ZERO dodatkowej zależności (odrzucono SQLAlchemy — Załącznik A). WAL, `VACUUM INTO` (≥3.27) dostępne na obu trackach |
| **pyinstaller** | 6.11.1 (Track A) / 5.13.2 (Track B) | ≥3.8,<3.14 / ≥3.7,<3.13 | bootloader od 6.11 kompilowany z "Windows 7 feature level" (F7); oficjalnie wspierany Win8+ → ryzyko udokumentowane i testowane w M0 | win32 + win_amd64 | n/d | dev-only, nie wchodzi do runtime | Freezer. Pin 6.11.1 = pierwsza linia z jawnym targetem Win7 w bootloaderze + pełne wsparcie Python 3.13 (od 6.10) |
| **pyinstaller-hooks-contrib** | 2025.5 | ≥3.8 | ✔ | py3-none-any | n/d | dev-only | Hooke PyQt5 dla PyInstaller |
| **pytest** | 8.3.5 | ≥3.8 (działa na 3.13) | ✔ | py3-none-any | n/d | dev-only | Testy |
| **pytest-qt** | 4.4.0 | ≥3.8 | ✔ (offscreen w CI) | py3-none-any | n/d | dev-only | Testy GUI |
| **responses** | 0.25.7 | ≥3.8 | ✔ | py3-none-any | n/d | dev-only | Mockowanie MAL/AniList w testach (nagrywane fixtures — zero sekretów) |
| **ruff** | 0.9.10 | ≥3.7 | ✔ | wheel binarny win_amd64 (CI) | n/d | dev-only | Lint + format |

**Kryteria odrzucenia zależności (checklista zadania):** brak koła Windows dla docelowego Pythona; `requires_python` wykluczający Track B bez markera; natywne rozszerzenia wymagające kompilacji na Win7; użycie API Win8+; footprint RAM/dysk nieuzasadniony funkcją.

**Zależności ŚWIADOMIE NIE wprowadzone:** httpx/httpcore/h11/anyio (Załącznik A), python-dotenv (własny parser `.env` ~25 linii — mniej zależności w freeze), SQLAlchemy/peewee (stdlib sqlite3), PySide6/Qt6 (brak Win7), pillow (dekodowanie przez QImageReader z Qt), psutil (pomiary przez WinAPI/ctypes w `--selftest`), aiohttp (asyncio na 2 rdzeniach bez korzyści).

## 2.4. Pliki wymagań (produkcyjne, przypięte)

`requirements.txt` (runtime — instalowany też w CI do buildu):

```text
# DongStack — runtime dependencies (PINNED — nie bumpować bez decyzji architekta)
# Track A: Python 3.13.5 (build Python-Win7) | Track B: Python 3.8.10 (oficjalny)
# Wszystkie piny zweryfikowane na PyPI 2026-09-26 pod kątem: requires_python, kół Windows, Win7.

PyQt5==5.15.11
PyQt5-Qt5==5.15.2
PyQt5-sip==12.19.0 ; python_version >= "3.10"
PyQt5-sip==12.15.0 ; python_version < "3.10"

requests==2.32.3
urllib3==2.2.3
certifi==2026.7.22
charset-normalizer==3.4.3
idna==3.11
```

`requirements-dev.txt` (testy/build — NIGDY nie instalowany w runtime użytkownika):

```text
-r requirements.txt

# Freezer (wersja zależna od tracka — patrz §2.2)
pyinstaller==6.11.1 ; python_version >= "3.10"
pyinstaller==5.13.2 ; python_version < "3.10"
pyinstaller-hooks-contrib==2025.5

# Testy
pytest==8.3.5
pytest-qt==4.4.0
responses==0.25.7

# Lint/format
ruff==0.9.10
```

Zasady:
- `pip install --require-hashes` jest włączony dla release.yml (decyzja D8) — hash-e wszystkich kół generowane skryptem `tools/freeze_hashes.py` do `requirements.lock.txt`.
- Zakaz `pip install -U czegokolwiek` na maszynie produkcyjnej; aktualizacje wyłącznie przez zmianę pina + pełny przegląd macierzy §2.3 + zielone CI.
- Na maszynie docelowej (Win7) `pip 25.1.1` z deklaracji Zamawiającego jest OK; Track-A build Python-Win7 zawiera pip (instalator "full").

---

# §3. ARCHITEKTURA SYSTEMU I STRUKTURA PLIKÓW

## 3.1. Warstwy (przepływ nadrzędny)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ WĄTEK GUI (jedyny wątek dotykający QWidget/QPixmap)                    │
│                                                                        │
│  MainWindow ─ SidebarWidget ─ DashboardWidget ─ AddDialog ─ SnackBar   │
│        │              │              │              │                 │
│        └──────────────┴──────┬───────┴──────────────┘                 │
│                              ▼                                         │
│              Controllers (DashboardController, AddController)          │
│              • optymistyczny update stanu UI (<16 ms)                  │
│              • request_id dla odpowiedzi asynchronicznych              │
│              • komendy Undo (stos, 1 poziom na snackbar)               │
│                              │                                         │
└──────────────────────────────┼─────────────────────────────────────────┘
              sygnały (Qt.QueuedConnection — automatyczne między wątkami)
        ┌──────────────────────┴──────────────────────┐
        ▼                                             ▼
┌───────────────────────────────┐   ┌───────────────────────────────────┐
│ WĄTEK DB (DbWorker, QThread)  │   │ WĄTEK SIECI (NetworkWorker,       │
│ — JEDYNE miejsce z sqlite3    │   │ QThread) — JEDYNE miejsce z       │
│                               │   │ requests                          │
│ • Repository (parametryzowany │   │ • kolejka FIFO z priorytetami     │
│   SQL, transakcje)            │   │   (search/details > covers)       │
│ • migracje, backup VACUUM INTO│   │ • TokenBucket (≤1 req/s MAL,      │
│ • ApiCache (TTL) + CoverStore │   │   ≤0.4 req/s AniList)             │
│ • koalescencja zapisów 250 ms │   │ • retry/backoff + Retry-After     │
│                               │   │ • MetadataService: cache-first,   │
│                               │   │   failover MAL→AniList            │
└───────────────────────────────┘   └───────────────────────────────────┘
```

Zasady wynikające z Biblii GUI i rygoru sprzętowego:

- **Dokładnie 3 wątki procesu**: GUI, DbWorker, NetworkWorker. Żadnego `QThreadPool` per-żądanie, żadnego tworzenia/niszczenia `QThread` w cyklu życia wyszukiwania (Biblia §18). Na 2-rdzeniowym CPU współbieżność >3 wątków obliczeniowych to czysta strata na przełączaniu kontekstu.
- Komunikacja wyłącznie **sygnałowo-slotowa przez granice wątków** (kolejkowana). Zakaz współdzielonych mutowalnych struktur bez synchronizacji; obiekty domenowe przekazywane przez sygnały są niemutowalne (dataclasses `frozen=True`).
- `QPixmap` tworzymy WYŁĄCZNIE w wątku GUI. Worker sieciowy zwraca `QImage` (bezpieczna między wątkami), GUI konwertuje i cache'uje w bounded LRU.
- Lokalna lista biblioteki trzymana jest **w pamięci kontrolera** (załadowana raz asynchronicznie przy starcie). Filtrowanie/sortowanie/wyszukiwanie lokalne operuje na liście w pamięci w wątku GUI (Biblia §13: bez QThread do lokalnego filtrowania) — 300–1000 lekkich dataclass to <1 MB i mikrosekundy.
- SQLite jest w całości za plecami `Repository`; GUI i kontrolery nie widzą SQL ani `sqlite3` (Biblia §53, rygor 12 zadania).

## 3.2. Reguły twarde (Hard Rules) — podstawa code review

| # | Reguła | Egzekwowanie |
|---|--------|--------------|
| R1 | W wątku GUI zakaz: `requests.*`, `sqlite3.*`, `open()` plików cache/DB, `time.sleep` | ruff (custom flake8-print rozszerzone) + review + testy GUI z detektorem (monkeypatch `sqlite3.connect` rzucający w wątku GUI) |
| R2 | Połączenie `sqlite3` istnieje tylko w DbWorker (utworzone w jego wątku → `check_same_thread` domyślne, bez flag) | test jednostkowy |
| R3 | Worker zwraca `QImage`, nigdy `QPixmap` | review + test |
| R4 | Zakaz `QThread.terminate()`; anulowanie = `request_id` + flaga kooperacyjna | review |
| R5 | Każda odpowiedź asynchroniczna niesie `request_id`; kontroler odrzuca odpowiedzi nieaktualne | test jednostkowy (wyścig dwóch wyszukiwań) |
| R6 | Wątki pracownicze są singletonami sesyjnymi (start przy bootstrapie, `quit()+wait()` przy zamknięciu) | review |
| R7 | Maksymalnie 3 wątki procesu | test `--selftest` zlicza wątki |
| R8 | Zakaz `QEventLoop`/`processEvents` jako "czekania" w GUI | review |
| R9 | Animacje: tylko 150–200 ms, maks. jedna równocześnie na widok, skeleton DOMYŚLNIE STATYCZNY (Biblia §21, rygor 18 zadania); globalny przełącznik `animations=off` w ustawieniach | review + pomiar CPU w M7 |
| R10 | Zapisy epizodów koalescencjonowane (okno 250 ms per id) | test |
| R11 | Żaden handler sygnału GUI nie przekracza 8 ms (połowa budżetu klatki) — pomiary `QElapsedTimer` w trybie dev | test wydajnościowy |
| R12 | `sys.excepthook` loguje i wyświetla SnackBar "Wystąpił nieoczekiwany błąd" — aplikacja nie umiera cicho | test |
| R13 | Zakaz stringowego składania SQL; wyłącznie parametry `?` | ruff + review + test (audyt repo) |
| R14 | Sekrety: zakaz logowania `MAL_CLIENT_SECRET`, zakaz `repr()` configa bez maskowania | test jednostkowy (przechwycenie logów) |
| R15 | Baseline składni: Python 3.8 (§16). Żadnego `match`, `list[str]`, `X | None` w anotacjach ewaluowanych | ruff (`target-version = "py38"`) — twarde, automatyczne |
| R16 | Frozen exe (`console=False`) w skryptach CI/smoke uruchamiamy wyłącznie mechanizmem **czekającym** (`Start-Process -Wait -PassThru` → `$p.ExitCode`); raport selftest czytamy z pliku `DONGSTACK_SELFTEST_OUT`, nigdy z `Tee-Object` na tę samą ścieżkę ani z parsowania stdout | test statyczny `tests/unit/test_workflows_selftest.py` |
| R17 | Formularz modalny o zmiennej liczbie wierszy (linki streamingowe, notatka) musi siedzieć w `QScrollArea`, a pasek akcji i nagłówek **poza** nim (przypięte); `minimumSizeHint` okna nie może rosnąć z liczbą wierszy — docelowy ekran 1366×768 | test GUI (`tests/gui/test_r11_ui.py`: 12 linków → min < 700 px, treść wyższa niż viewport) |
| R18 | `0` w polach liczbowych z bazy/API (`total_episodes`, `start_year`) znaczy **„nieznane”**, nigdy „limit zero”: spinboksy mają `specialValueText` i odblokowany sufit, a clampowanie wartości tylko dla `> 0` (dotyka widgetów, kontrolera i repo) | testy GUI + unit (`test_r11_ui.py`, `test_r11_note_plumbing.py`) |

## 3.3. Kontrakt sygnałów (rozszerzenie Biblii §46)

```text
# GUI → Controlers (wątek GUI)
DonghuaRow.episodeIncrementRequested(int donghua_id)
DonghuaRow.episodeDecrementRequested(int donghua_id)
DonghuaRow.editRequested(int donghua_id)
DonghuaRow.detailsRequested(int donghua_id)
SidebarWidget.statusFilterChanged(str status)          # all|watching|completed|planned|dropped
DashboardWidget.localSearchChanged(str text)
DashboardWidget.sortChanged(str mode)                  # updated|alpha|added|progress
DashboardWidget.addClicked()

# Controlers → Workers (kolejkowane między wątkami)
DashboardController → DbWorker:  saveEpisodeRequested(int id, int episode, int request_id)
DashboardController → DbWorker:  saveStatusRequested(int id, str status, int request_id)
AddController → NetworkWorker:   searchRequested(str query, int request_id)
AddController → NetworkWorker:   detailsRequested(str provider, int ext_id, int request_id)
CoverLoader → NetworkWorker:     coverRequested(str url, int priority)

# Workers → GUI (kolejkowane)
DbWorker.libraryLoaded(list)                             # start aplikacji
DbWorker.saveSucceeded(int id, int request_id)
DbWorker.saveFailed(int id, int request_id, str message) # → rollback optymistyczny + SnackBar
NetworkWorker.searchFinished(int request_id, list items)
NetworkWorker.searchFailed(int request_id, object api_error)
NetworkWorker.detailsFinished(int request_id, object details)
NetworkWorker.coverFetched(str url, QImage image)        # QImage, NIE QPixmap (R3)
NetworkWorker.coverFailed(str url)

# Model/Controller → GUI
DashboardController.donghuaAdded(object donghua)
DashboardController.donghuaUpdated(object donghua)
DashboardController.donghuaRemoved(int id)
DashboardController.episodeChanged(int id, int current, int total)
DashboardController.statusChanged(int id, str status)
DashboardController.countsChanged(dict)                  # badge'e sidebara

# Uniwersa (§4.9, §5.6, §6.7)
UniverseService.relationsFetched(int mal_id, list relations)   # wynik related_anime (cache 7 dni)
DashboardController.universeSuggested(int new_donghua_id, list candidate_universes)
                                                       # → SnackBar "Połączyć z «X»? [Połącz] [Nie teraz]"
DashboardController.universeChanged(int universe_id)   # przegrupowanie widoku listy
DashboardController.universeOrderOverride(int donghua_id, object position)  # ręczna korekta kolejności
```

## 3.4. Struktura katalogów i plików (docelowe repozytorium GitHub)

```text
dongstack/                               # repo: github.com/karnyjohnny/dongstack (D7)
├── .github/
│   └── workflows/
│       ├── ci.yml                     # push/PR: ruff + pytest (offscreen) na CPython 3.13
│       └── release.yml                # tag v*: build matrix (win32/amd64 × onedir/onefile)
│                                      #   na Python-Win7 3.13.5 + GitHub Release + SHA256SUMS
├── app/                               # CAŁY kod produkcyjny (importowalny pakiet)
│   ├── __init__.py                    # __version__ = "1.0.0" (single source of truth)
│   ├── main.py                        # entrypoint: bootstrap, excepthook, single-instance,
│   │                                  #   --selftest, kod wyjścia
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # ConfigService: env > .env (dev) > %LOCALAPPDATA%\config.json
│   │   │                              #   > first-run prompt; MAL_CLIENT_ID; maskowanie sekretów (R14)
│   │   ├── paths.py                   # resource_path() (sys._MEIPASS-aware), app_data_dir(), logs_dir()
│   │   ├── logging_setup.py           # RotatingFileHandler 3×1 MB + filtr maskujący sekrety
│   │   ├── dotenv_lite.py             # minimalny parser .env (~25 linii, bez zależności)
│   │   └── errors.py                  # ApiError(kind, message, provider, retryable) — taksonomia §5.4
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py                  # frozen dataclasses: Donghua, StreamingLink, SearchItem,
│   │   │                              #   AnimeDetails, Universe; enumy Status/MediaType/SortMode/Platform
│   │   └── undo.py                    # UndoCommand (Increment/Decrement/Add/Remove/StatusChange)
│   │                                  #   + UndoStack (1 aktywna komenda per SnackBar)
│   ├── data/
│   │   ├── __init__.py
│   │   ├── connection.py              # factory sqlite3 + PRAGMA (WAL, synchronous=NORMAL,
│   │   │                              #   foreign_keys=ON, busy_timeout, cache_size)
│   │   ├── migrations.py              # user_version + sekwencyjne migracje + backup VACUUM INTO
│   │   ├── repository.py              # DonghuaRepository/LinksRepository — JEDYNE miejsce z SQL (R13)
│   │   ├── api_cache.py               # ApiCacheRepo (TTL, stale-if-error, vacuum cache)
│   │   ├── cover_store.py             # okładki na dysku + indeks w SQLite; ścieżki względne
│   │   └── settings_store.py          # ustawienia aplikacji (JSON w AppData; bez QSettings — spójność)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── provider.py                # MetadataProvider (ABC): search()/details()/name
│   │   ├── mal_client.py              # MalClient: requests.Session, endpointy §5.1, parser,
│   │   │                              #   klasyfikacja błędów; User-Agent aplikacji
│   │   ├── anilist_client.py          # AnilistClient: GraphQL §5.2 (fallback; idMal → normalizacja)
│   │   ├── rate_limiter.py            # TokenBucket(rate, capacity) — thread-safe, blocking acquire
│   │   ├── retry.py                   # RetryPolicy + exponential backoff z jitterem + Retry-After
│   │   ├── circuit_breaker.py         # 3 niepowodzenia → open 60 s → half-open (per provider)
│   │   └── metadata_service.py        # fasada: cache-first → provider → failover; normalizacja modeli
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── db_worker.py               # DbWorker(QObject) + wątek; kolejka komend; koalescencja (R10);
│   │   │                              #   migracje i backup przy starcie
│   │   └── network_worker.py          # NetworkWorker(QObject) + wątek; kolejka priorytetowa;
│   │                                  #   request_id (R5); TokenBucket; MetadataService
│   ├── controllers/
│   │   ├── __init__.py
│   │   ├── dashboard_controller.py    # stan biblioteki w pamięci, filtry/sort/search lokalny,
│   │   │                              #   optymistyczny update + rollback, auto-complete, Undo,
│   │   │                              #   grupowanie uniwersów (§6.7)
│   │   └── add_controller.py          # debounce 450 ms, deduplikacja wyników, quick/advanced add
│   ├── services/
│   │   ├── __init__.py
│   │   ├── watch_order.py             # kolejność oglądania uniwersum: topo-sort relacji MAL
│   │   │                              #   + heurystyka tytułów (EN/CN) + override ręczny (§4.9.2)
│   │   └── universe_service.py        # related_anime → detekcja powiązań → sugestie (§5.6)
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py             # QMainWindow: sidebar+content (Biblia §1), shortcuty (§47)
│   │   ├── sidebar.py                 # SidebarWidget + NavItemWidget (badge'e liczników)
│   │   ├── theme.py                   # ładowanie QSS przez resource_path(), paleta (Biblia §29)
│   │   ├── snackbar.py                # SnackBar(QFrame) overlay + QTimer + opcjonalna anim. 150 ms
│   │   ├── dashboard/
│   │   │   ├── __init__.py
│   │   │   ├── dashboard_widget.py    # topBar + QListWidget#donghuaList + FAB addButton (overlay)
│   │   │   ├── donghua_row.py         # karta DonghuaRow (Biblia §4–§6): cover/info/actions
│   │   │   ├── list_backend.py        # ListBackend (ABC): WidgetListBackend (v1) | DelegateListBackend
│   │   │   │                          #   (próg 300 pozycji — Biblia §43, gate wydajnościowy §7.4)
│   │   │   ├── skeleton.py            # SkeletonRow — STATYCZNY (R9)
│   │   │                              #   (M9: universe_header.py usunięty — płaska lista §6.7)
│   │   └── add/
│   │       ├── __init__.py
│   │       ├── add_dialog.py          # QDialog + QStackedWidget (Biblia §15), non-modal
│   │       ├── search_page.py         # QLineEdit + debounce + stany IDLE/SEARCHING/RESULTS/
│   │       │                          #   NO_RESULTS/ERROR (Biblia §20) + skeleton 4–5 wierszy
│   │       ├── mal_result_row.py      # wiersz wyniku: cover/title/meta/QuickAdd/Advanced,
│   │       │                          #   badge "✓ Już w bibliotece" (nie blokuje dodania — Biblia §23)
│   │       ├── advanced_page.py       # QFormLayout: QButtonGroup statusów, QSpinBox odcinek (Biblia §26–27)
│   │       └── streaming_links.py     # dynamiczne wiersze: QComboBox platformy + URL + remove
│   └── resources/                     # assety pakowane do .exe (§8.2 datas)
│       ├── styles/
│       │   ├── base.qss               # globalne QWidget/QMainWindow/QLineEdit/QScrollBar…
│       │   ├── sidebar.qss
│       │   ├── cards.qss              # donghuaCard, plus/minus, progressBar
│       │   ├── dialogs.qss            # AddDialog, wyniki MAL, advanced, comboBoxy
│       │   └── snackbar.qss
│       └── icons/                     # PNG generowane programowo (§6.4.3, tools/generate_branding.py)
│           ├── add_16..32.png remove_*.png more_*.png search_*.png sort_*.png
│           ├── link_*.png undo_*.png  # uniwersa + akcja Cofnij
│           ├── status_watching_*.png status_completed_*.png status_planned_*.png status_dropped_*.png
│           ├── cover_placeholder_*.png
│           └── app.ico logo_256.png   # ikona exe/okna (wielorozmiarowa) + logo README
├── tests/
│   ├── unit/                          # bez Qt: rate_limiter, retry, cache, repository (sqlite :memory:),
│   │   │                              #   migrations, config/masking, undo, dotenv_lite
│   ├── gui/                           # pytest-qt + QT_QPA_PLATFORM=offscreen: sygnały DonghuaRow,
│   │   │                              #   optymistyczny update/rollback, request_id race, R1-detektor
│   ├── fixtures/                      # NAGRANE odpowiedzi API (zrealizowane live 2026-09-26):
│   │   │                              #   mal_search.json, mal_details.json, mal_ranking.json,
│   │   │                              #   anilist_page.json, mal_429.txt, mal_400_limit.json
│   └── live/                          # opt-in (RUN_LIVE_API_TESTS=1 + MAL_CLIENT_ID z env):
│                                      #   smoke MAL/AniList; NIGDY domyślnie w CI; zero sekretów w kodzie
├── packaging/
│   ├── dongstack.spec           # plik PyInstaller (§8.2)
│   ├── version_info.txt               # VERSIONINFO (metadane exe: wersja, firma, opis)
│   ├── python-win7.json               # pin: commit SHA + nazwy plików + SHA256 (§9.3)
│   └── README.md                      # jak ręcznie zbudować exe na Win7 i w CI
├── tools/
│   ├── hash_python_win7.py            # regeneruje packaging/python-win7.json (checksumy installerów)
│   ├── generate_branding.py           # logo/ikony/app.ico rysowane w Pillow (dev-only — D7)
│   ├── freeze_hashes.py               # generuje requirements.txt z --require-hashes (opcjonalnie)
│   └── smoke_test.ps1                 # skrypt testu dymnego M0/M7 na maszynie docelowej
├── docs/
│   ├── SPECYFIKACJA-TECHNICZNA.md     # ← ten dokument
│   └── ADR/                           # lekkie rekordy decyzji (0001-dwutorowosc-runtime.md, …)
├── .env.example                       # SZABLON bez prawdziwych wartości (§12)
├── .gitignore                         # m.in. .env, dist/, build artifacts, *.sqlite, logs/
├── README.md                          # struktura §11
├── requirements.txt                   # §2.4
├── requirements-dev.txt               # §2.4
├── pyproject.toml                     # WYŁĄCZNIE konfiguracja ruff/pytest (bez metadanych dystrybucji)
└── LICENSE                            # MIT (D6 zatwierdzone; uwaga GPLv3 binariów §12.3)
```

Liczby: ~45 plików źródłowych Python, 5 QSS, ~15 ikon. Cel: **zero** plików powyżej ~400 linii; moduły jednorodnych odpowiedzialności (SRP) — ułatwia testy jednostkowe bez Qt.

Kluczowe konwencje nazewnicze:
- pakiet aplikacji `app/` (krótki import w spec/exe: `from app.gui...`),
- dane użytkownika: `%LOCALAPPDATA%\DongStack\{donghua.sqlite, covers\, logs\, config.json, donghua.lock}`,
- artefakty: `DongStack.exe` (onefile) / `DongStack\DongStack.exe` (onedir).

---

# §4. WARSTWA DANYCH: SQLITE, REPOZYTORIUM, CACHE

## 4.1. Lokalizacja i pliki

```text
%LOCALAPPDATA%\DongStack\
├── dongstack.sqlite          # baza główna (WAL → obok powstają -wal i -shm)
├── backups\                  # kopie VACUUM INTO (3 ostatnie)
│   └── dongstack-20260926-1830.sqlite
├── covers\                   # cache okładek (JPEG, zdekodowane do docelowego rozmiaru)
│   └── 37\37347_180x220.jpg  # podkatalogi = pierwsze 2 znaki klucza (limit plików/katalog)
├── logs\dongstack.log        # RotatingFileHandler 3×1 MB
├── config.json               # ustawienia (w tym MAL_CLIENT_ID — patrz §12)
└── dongstack.lock            # QLockFile (single instance)
```

`%LOCALAPPDATA%` (a nie Roaming): okładki i cache to dane odtwarzalne, nie chcemy ich w profilach wędrownych. Win7: `C:\Users\<user>\AppData\Local\DongStack`. Nadpisanie lokalizacji: zmienna środowiskowa `DONGSTACK_HOME` (tryb portable/testy).

## 4.2. Połączenie i PRAGMA (ustawiane raz, w wątku DbWorker)

```python
conn = sqlite3.connect(db_path, timeout=5.0)        # utworzone W wątku workera (R2)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode = WAL")            # zapis nie blokuje odczytu; crash-safe
conn.execute("PRAGMA synchronous = NORMAL")          # optymalne dla WAL i HDD 5400 rpm
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA busy_timeout = 3000")
conn.execute("PRAGMA cache_size = -4000")            # 4 MB cache stron — kompromis dla 2 GB RAM
conn.execute("PRAGMA temp_store = FILE")             # nie marnujemy RAM na temp-tablice
conn.execute("PRAGMA mmap_size = 0")                 # przewidywalność na Win7
```

Uzasadnienie `synchronous=NORMAL` + WAL: w WAL przy `NORMAL` trwałość pozostaje wystarczająca (utrata co najwyżej ostatnich transakcji przy zaniku zasilania, bez uszkodzenia bazy), a każdy commit `+1` nie czeka na fsync — na HDD to różnica ~20 ms vs ~0 ms, przy zachowaniu reguły "GUI nigdy nie czeka" (commit i tak jest w workerze).

## 4.3. Schemat v1 (DDL — wykonywany przez migrations.py)

```sql
PRAGMA user_version = 1;

CREATE TABLE IF NOT EXISTS universes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                  -- np. "Doupo Cangqiong / 斗破苍穹"
    mal_anchor_id   INTEGER,                        -- MAL id dowolnego członka (kotwica related_anime)
    created_at      TEXT NOT NULL                   -- ISO-8601 UTC z Pythona
);

CREATE TABLE IF NOT EXISTS donghua (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mal_id          INTEGER UNIQUE,                 -- kanoniczny klucz zewnętrzny (może NULL dla ręcznych)
    anilist_id      INTEGER,                        -- pomocniczo (failover provider)
    provider        TEXT NOT NULL DEFAULT 'mal',    -- 'mal' | 'anilist' | 'manual'
    title           TEXT NOT NULL,
    title_alt       TEXT,                           -- romaji/english — drugorzędne
    total_episodes  INTEGER NOT NULL DEFAULT 0,     -- 0 = nieznane/w trakcie emisji
    current_episode INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('watching','completed','planned','dropped')),
    score           INTEGER CHECK (score IS NULL OR score BETWEEN 1 AND 10),
    media_type      TEXT,                           -- tv|ona|ova|movie|special
    start_year      INTEGER,
    cover_key       TEXT,                           -- klucz w cover_cache (NULL = placeholder)
    universe_id     INTEGER REFERENCES universes(id) ON DELETE SET NULL,  -- §4.9
    universe_order  INTEGER,                        -- ręczna pozycja w uniwersum (NULL = auto)
    note            TEXT,
    added_at        TEXT NOT NULL,                  -- ISO-8601 UTC, ustawiane w Pythonie
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT                            -- soft-delete na potrzeby Undo (purge po 24 h)
);

CREATE TABLE IF NOT EXISTS streaming_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    donghua_id  INTEGER NOT NULL REFERENCES donghua(id) ON DELETE CASCADE,
    platform    TEXT NOT NULL CHECK (platform IN ('iqiyi','bilibili','youtube','crunchyroll','other')),
    url         TEXT NOT NULL,
    label       TEXT,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS api_cache (
    cache_key   TEXT PRIMARY KEY,                   -- "mal:search:<norm_query>:<limit>" | "mal:anime:<id>" | "anilist:..."
    provider    TEXT NOT NULL,
    payload     TEXT NOT NULL,                      -- JSON dokładnie jak z API (re-parse w serwisie)
    fetched_at  INTEGER NOT NULL,                   -- unix epoch (s)
    ttl_s       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cover_cache (
    cache_key   TEXT PRIMARY KEY,                   -- sha1(url) + rozmiar docelowy
    url         TEXT NOT NULL,
    path        TEXT NOT NULL,                      -- względem katalogu covers\
    fetched_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
```

Indeksy (dokładnie tam, gdzie mają sens — rygor 12 zadania):

```sql
CREATE INDEX IF NOT EXISTS idx_donghua_status_updated ON donghua(status, updated_at DESC);
    -- główny widok "W trakcie" + sortowanie domyślne "Ostatnio aktualizowane" → covering index
CREATE INDEX IF NOT EXISTS idx_donghua_title ON donghua(title COLLATE NOCASE);
    -- lokalne wyszukiwanie (fallback; primary: lista w pamięci)
CREATE INDEX IF NOT EXISTS idx_donghua_alive ON donghua(deleted_at);
    -- zapytanie startowe: WHERE deleted_at IS NULL
CREATE INDEX IF NOT EXISTS idx_donghua_universe ON donghua(universe_id, universe_order);
    -- grupowanie uniwersów (§4.9/§6.7)
CREATE UNIQUE INDEX IF NOT EXISTS idx_universes_name ON universes(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_links_donghua ON streaming_links(donghua_id);
CREATE INDEX IF NOT EXISTS idx_cache_fetched ON api_cache(provider, fetched_at);
    -- okresowe vacuum cache
```

Brak indeksów na `api_cache.cache_key`/`cover_cache.cache_key` — to PRIMARY KEY (rowid-less nie jest potrzebne; tabele małe).

## 4.4. Migracje i backup

- Wersjonowanie: `PRAGMA user_version`. Sekwencja migracji w `migrations.py`: `MIGRATIONS = {1: [...DDL...], 2: [...]}`; każda w jawnej transakcji; po sukcesie `user_version = N`.
- **Backup przed pierwszą migracją w danej wersji aplikacji**: `VACUUM INTO 'backups/donghua-<timestamp>.sqlite'` (SQLite ≥3.27 — dostępne na obu trackach), retencja: 3 najnowsze, reszta kasowana.
- Migracja w dół: nie wspierana (kopia zapasowa wystarczy).
- Uszkodzona baza (SQLITE_CORRUPT / brak otwarcia): przy starcie aplikacja proponuje `donghua.sqlite.corrupt-<ts>` + odtworzenie z najnowszego backupu + komunikat SnackBar. Zero utraty całego UX.

## 4.5. Repository — jedyna warstwa SQL

```python
class DonghuaRepository(object):
    """Wszystkie zapytania parametryzowane (R13). Wywoływana WYŁĄCZNIE z DbWorker."""

    def load_alive(self) -> List[Donghua]: ...
        # SELECT ... WHERE deleted_at IS NULL ORDER BY updated_at DESC
    def insert(self, d: Donghua) -> int: ...
    def update_progress(self, donghua_id: int, episode: int, status: str, now_iso: str) -> None: ...
        # UPDATE donghua SET current_episode=?, status=?, updated_at=? WHERE id=?
    def update_full(self, d: Donghua) -> None: ...
    def soft_delete(self, donghua_id: int, now_iso: str) -> None: ...
    def purge_deleted(self, older_than_iso: str) -> int: ...
    def replace_links(self, donghua_id: int, links: List[StreamingLink]) -> None: ...
        # DELETE + INSERT w JEDNEJ transakcji (with conn:)
```

Transakcje: wyłącznie `with conn:` (auto-commit/rollback). Operacje wielowierszowe (add + links) w jednej transakcji. Brak zagnieżdżonych transakcji.

## 4.6. DbWorker — kolejka, koalescencja, ack

```python
class DbWorker(QObject):
    libraryLoaded   = pyqtSignal(list)
    saveSucceeded   = pyqtSignal(int, int)            # donghua_id, request_id
    saveFailed      = pyqtSignal(int, int, str)

    # sloty wywoływane sygnałami z GUI (Qt.QueuedConnection automatycznie)
    @pyqtSlot(int, int, int)
    def saveEpisode(self, donghua_id, episode, request_id): ...
    @pyqtSlot(object)
    def addDonghua(self, command): ...
```

- **Koalescencja (R10):** kliknięcia `+` szybsze niż 250 ms dla tego samego `id` są scalane — worker trzyma `pending: Dict[int, SaveRequest]`; pierwszy pending w oknie planuje flush przez `QTimer.singleShot(250 ms, …)` utworzony w wątku wywołania (worker), a flush weryfikuje wątek właściciela połączenia (`_owner_ident`) — korekta v1.1.3 po pomiarach M3 (member-QTimer miał pułapki afiliacji międzywątkowej). Operacje nieprogresowe (add/remove/restore)wykonują się natychmiast. Efekt: 10 szybkich klików = 1 fsync, nie 10.
- **Ack/nack:** `saveFailed` → kontroler cofa stan optymistyczny + SnackBar "Nie udało się zapisać zmiany." (Biblia §9 — bez QMessageBox).
- Start: `migrate()` → `backup_if_needed()` → `load_alive()` → `libraryLoaded`. GUI pokazuje w tym czasie skeletony dashboardu (nie pusty ekran).
- Zamknięcie: `flush()` → `PRAGMA wal_checkpoint(TRUNCATE)` → `close()`.

## 4.7. Cache API (ApiCache) — polityka

| Dane | Klucz | TTL | Zachowanie po wygaśnięciu | Zachowanie przy błędzie sieci |
|---|---|---|---|---|
| Wynik wyszukiwania MAL | `mal:search:<query_norm>:<limit>` | 6 h | refetch | **serwuj stale** + znacznik "dane nieaktualne?" (graceful degradation) |
| Szczegóły anime | `mal:anime:<id>` | 7 dni | refetch | serwuj stale |
| Wynik AniList | `anilist:search:<query_norm>` | 6 h | refetch | serwuj stale |
| Okładki | dysk `covers\` + `cover_cache` | 30 dni (weryfikacja obecności pliku) | re-download w tle | placeholder |

- `query_norm`: lowercase, trim, spacje → `_`, max 64 znaki — klucz deterministyczny.
- Odczyt cache odbywa się w DbWorker (R1/R2) i jest asynchroniczny z perspektywy GUI: `searchRequested` → NetworkWorker pyta DbWorker o cache sygnałem, ALBO (prościej, decyzja implementacyjna) NetworkWorker ma **własne połączenie read-only do tabel cache** (SQLite WAL pozwala na wielodostęp; odczyt nie blokuje zapisu). Decyzja: **wariant prostszy** — NetworkWorker czyta cache bezpośrednio (połączenie `mode=ro`), zapis cache idzie przez DbWorker. Rygor 12 zadania ("nie twórz nadmiarowego systemu wielowątkowości") spełniony: nadal dokładnie 3 wątki.
- Payload trzymany jako surowy JSON z API (re-parse przy odczycie): odporność na zmiany parsera, brak migracji cache przy zmianie modeli.
- Vacuum cache: przy starcie raz na dobę `DELETE FROM api_cache WHERE fetched_at + ttl_s < now - 7d`.
- Bounded RAM: cache NIGDY nie jest ładowany hurtem do pamięci; pojedyncze wpisy (kilka–kilkadziesiąt KB).

## 4.8. CoverStore

- Zapis: worker sieciowy pobiera JPEG/PNG → dekoduje `QImageReader` z `setScaledSize(QSize(180, 220))` (= 2× docelowe 72×88 karty dla ostrości, ale 16× mniej pikseli niż pełny cover 400×600) → zapisuje znormalizowany JPEG (quality 82) do `covers\`.
- GUI dostaje `QImage` z dysku/sieci i tworzy `QPixmap` w wątku GUI; LRU `collections.OrderedDict` o limicie **64 pixmapy** (~1,6 MB) + `QPixmapCache.setCacheLimit(8192)` (KB).
- Brak okładki → `coverPlaceholder` z inicjałem tytułu (Biblia §5.2).
- Kolejkowanie: priorytet dla wierszy widocznych w viewporcie; reszta lazy przy scrollu (sygnał `rowsAboutToBeVisible`).

## 4.9. Uniwersa (franczyzy) — model, kolejność oglądania, repozytorium

**Wymaganie (D7/rozszerzenie zakresu, 2026-09-26):** pozycje w bibliotece dają się łączyć w **uniwersa** (łańcuchy prequel/sequel + side stories), a dashboard wyświetla członków uniwersum w **kolejności oglądania**: sezon 1 → sezon 2 → … → ostatni sezon → filmy → OVA/specjale. Rozwiązuje realny problem Właściciela: "mam donghua s2, s5, s1, s7 — nie są w kolejności".

### 4.9.1. Źródła prawdy o kolejności (w prioritetcie)

1. **Graf relacji MAL `related_anime`** (zweryfikowany live — F15): dla `id=37176` ("Doupo Cangqiong 2nd Season") zwraca `prequel → 36491 (S1)`, `sequel → 38436 (S3)`, `side_story → 36561/39178 (Specjale)`. Relacje `sequel`/`prequel` tworzą **twarde krawędzie** DAG (A prequel B ⇒ A przed B); `side_story`/`parent_story`/`alternative_version` — **krawędzie miękkie** (porządkują, ale nie mogą tworzyć cykli twardych).
2. **Ręczny override**: `donghua.universe_order` (drag/menu "Przesuń w górę/w dół") — wartości nie-NULL są kotwicami, reszta układana między nimi.
3. **Heurystyka tytułu** (fallback i tie-breaker): parser sezonu — wzorce EN (`2nd Season`, `Season 2`, `Part 3`, `II`/`III` rzymskie) oraz CN (`第二季`, `第3季`, `第三部`), z konwersją liczebników chińskich (一二三…十, 二十一 itd.).
4. **Metadane**: `media_type` (rank: tv/ona=0 → movie=1 → ova/special=2 → music=3), następnie `start_year`, następnie tytuł alfabetycznie.

### 4.9.2. Algorytm `watch_order` (app/services/watch_order.py — czysta funkcja, testowalna bez Qt)

```text
order_universe(members, relations, overrides) -> List[Donghua]:
  1. krawędzie twarde z relations (tylko między members; prequel/sequel, znormalizowane do A→B)
  2. sort topologiczny (Kahn) z tie-breakerem: (universe_order IS NULL, media_rank, season_hint, start_year, title)
  3. wykryty cykl twardy → usunięcie najsłabszej krawędzi (wg start_year) + log WARN (nigdy crash)
  4. krawędzie miękkie (side_story…) → wstawienie elementu PO sąsiedzie, którego dotyczą, o ile nie łamie topo
  5. override'y ręczne: stabilne przypięcie pozycji (elementy z universe_order wychodzą pierwsze w swojej kolejności, auto-reszta dopełnia luki)
  6. wynik: lista memberów w kolejności oglądania; członkowie bez mal_id (ręczne) lądują wg (media_rank, start_year, title)
```

Złożoność O(V+E) — dla uniwersum ≤ 50 pozycji to mikrosekundy; liczone w kontrolerze (wątek GUI) na liście w pamięci, zero SQL.

### 4.9.3. UniverseRepository + cykl życia

- `create(name, mal_anchor_id) -> int`, `rename`, `delete(id)` (FK `ON DELETE SET NULL` — członkowie wracają do "bez uniwersum", NIE są usuwani), `list_all()`, `members(universe_id)`.
- **Auto-sugestia przy dodaniu (§5.6):** po Quick/Advanced Add pozycji z `mal_id`, UniverseService (w NetworkWorker, priorytet LOW) pobiera `related_anime` (cache 7 dni w `api_cache`) → jeżeli którykolwiek `node.id` jest już w bibliotece i należy do uniwersum (lub tworzy parę) → sygnał `universeSuggested` → SnackBar: `Połączyć „X” z uniwersum „Doupo Cangqiong”? [Połącz] [Nie teraz]` (Undo zamiast Confirm — Biblia). Sugestia nigdy nie blokuje i nie opóźnia dodania.
- **Ręczne zarządzanie:** AdvancedPage ma pole "Uniwersum" (QComboBox: istniejące + "Utwórz nowe…" + "Brak"); menu kontekstowe wiersza: "Połącz z uniwersum…", "Przesuń w górę/w dół" (override).
- **Usuwanie (r11, ⚙ Ustawienia → Uniwersa):** lista z liczbą przypisanych sezonów (liczoną z pamięci kontrolera — bez SQL w GUI, R2) + „Usuń wybrane”. `delete(id)` + FK `ON DELETE SET NULL` ⇒ sezony zostają w bibliotece bez uniwersum; stan widoku odłączany optymistycznie, `universeDeleted/universeDeleteFailed` z `request_id` (R5), nack = przywrócenie rejestru i przynależności. **Undo** = `create(name, anchor)` + ponowne `attach` tych samych `donghua_id` z zachowaniem `universe_order` (nowe id uniwersum — lista w oknie odświeża się przez `universesChanged`).
- Nazwa uniwersum: domyślnie tytuł najwcześniejszego członka (po watch_order) bez sufiksu sezonu, edytowalna.

---

# §5. INTEGRACJA Z API ZEWNĘTRZNYMI

## 5.0. Architektura providerów

```text
MetadataService (używana przez NetworkWorker)
    ├── cache-first (ApiCache §4.7)
    ├── provider główny:  MalClient      (api.myanimelist.net/v2)
    ├── provider awaryjny: AnilistClient (graphql.anilist.co)
    └── normalizacja → SearchItem / AnimeDetails (modele domenowe)
```

Interfejs:

```python
class MetadataProvider(object):          # ABC
    name = ""                            # "mal" | "anilist"
    def search(self, query: str, limit: int) -> Tuple[List[SearchItem], Paging]: ...
    def details(self, ext_id: int) -> AnimeDetails: ...

class SearchItem(object):                # frozen dataclass — wspólny mianownik
    provider: str
    ext_id: int
    mal_id: Optional[int]                # AniList zwraca idMal → zawsze normalizujemy do mal_id, gdy znany
    title: str
    title_alt: Optional[str]
    cover_url: Optional[str]
    total_episodes: int                  # 0 = nieznane
    year: Optional[int]
    media_type: str                      # znormalizowane: tv|ona|ova|movie|special|music|unknown
    mean_score: Optional[float]
```

**Kanon klucza zewnętrznego: `mal_id`.** Pozycje dodane przez fallback AniList zapisują `anilist_id` oraz `mal_id` (z pola `idMal`), dzięki czemu duplikaty są wykrywalne niezależnie od providera (§6.2.4), a przyszła synchronizacja z kontem MAL pozostaje możliwa.

Failover (automatyczny):
- MAL → błąd retryable wyczerpał próby LUB circuit breaker OPEN → próba AniList (ta sama fraza).
- AniList jest też ręcznym przełącznikiem w ustawieniach (provider preferowany) — na wypadek długotrwałej niedostępności MAL.
- Wynik zawsze oznaczony `provider`, UI pokazuje źródło danych w szczegółach (poziom 3 — Biblia §64).

## 5.1. Provider MAL (zweryfikowany live 2026-09-26 — F9/F10)

**Baza:** `https://api.myanimelist.net/v2`
**Uwierzytelnianie danych publicznych:** nagłówek `X-MAL-CLIENT-ID: <MAL_CLIENT_ID>` — **Client Secret NIE jest potrzebny** w tej aplikacji (v1 nie dotyka endpointów użytkownika). Potwierdzone live: HTTP 200 dla wyszukiwania, szczegółów i rankingu.

Endpointy używane w v1:

| Cel | Żądanie | Uwagi zweryfikowane |
|---|---|---|
| Wyszukiwanie | `GET /anime?q={query}&limit=20&offset=0&fields=id,title,alternative_titles,main_picture,num_episodes,mean,media_type,start_date,status&nsfw=false` | `limit=1500` → 400 `{"message":"limit","error":"bad_request"}`; `limit=500` → 200 ale niestandardowo — **produkcyjnie limit ≤ 100, UI: 20/stronę**; odpowiedź: `{"data":[{"node":{...}}], "paging":{"next": "..."}}` — paginacja przez `offset` z URL w `paging.next` |
| Szczegóły | `GET /anime/{id}?fields=id,title,alternative_titles,synopsis,mean,rank,genres,media_type,status,num_episodes,start_date,main_picture,pictures` | HTTP 200 live; pola opcjonalne mogą być nieobecne → parser defensywny (`.get`) |
| (v2, opcjonalnie) Ranking | `GET /anime/ranking?ranking_type=airing&limit=20` | HTTP 200 live — feature "co teraz leci" na przyszłość |
| **Powiązania (uniwersa)** | `GET /anime/{id}?fields=id,title,related_anime` | HTTP 200 live 2026-09-26 (F15): `related_anime: [{node:{id,title}, relation_type: sequel\|prequel\|side_story\|…, relation_type_formatted}]` — podstawa auto-detekcji uniwersów (§4.9) |

Maksymalny zestaw pól dla wyszukiwania jest celowo wąski (9 pól) — mniejszy payload = mniej JSON-a do sparsowania na Core 2 Duo i mniej pamięci.

**Przyszłość (poza v1):** synchronizacja z kontem użytkownika MAL (`/users/@me/animelist`) wymaga OAuth2 Authorization Code + PKCE (`https://myanimelist.net/v1/oauth2/authorize` / `/token`). PKCE = klient publiczny, **bez Client Secret**. Moduł opcjonalny v2+ — w v1 wykluczony decyzją D3 ("lokalny tracking").

**Taksonomia błędów MAL → `ApiError(kind)`:**

| HTTP | kind | retryable | Akcja klienta |
|---|---|---|---|
| 200 | — | — | parse (defensywnie: brak pól = None/0) |
| 400 | `bad_request` | NIE | błąd programistyczny/parametrów → log + SnackBar "Nie udało się wyszukać." |
| 401 | `auth` | NIE | brak/zły Client ID → SnackBar + odesłanie do ustawień (first-run flow §5.5) |
| 403 (HTML!) | `throttled_ban` | TAK (długi cooldown) | specyfika MAL (F13): cooldown 5 min + natychmiastowy failover AniList |
| 404 | `not_found` | NIE | pozycja usunięta z MAL → oznacz metadane jako "niedostępne" |
| 429 | `rate_limited` | TAK | `Retry-After` jeśli obecny, else backoff (§5.4) |
| 5xx | `server` | TAK | backoff |
| timeout/ConnectionError | `network` | TAK | backoff; po 3 porażkach circuit breaker |

## 5.2. Provider AniList (zweryfikowany live — F12)

**Endpoint:** `POST https://graphql.anilist.co`, `Content-Type: application/json`, **bez uwierzytelnienia**.

Zapytanie wyszukiwania (szablon produkcyjny):

```graphql
query ($q: String, $page: Int) {
  Page(page: $page, perPage: 20) {
    pageInfo { total currentPage hasNextPage }
    media(search: $q, type: ANIME, sort: SEARCH_MATCH) {
      id idMal
      title { romaji english native }
      episodes status seasonYear format countryOfOrigin averageScore
      coverImage { medium large }
    }
  }
}
```

Uwagi praktyczne (wynik testów live):
- `search:` AniList jest bardziej "exact-phrase" niż MAL — przy pustym wyniku ponawiamy z frazą skróconą (pierwsze 3 słowa) LUB `sort: POPULARITY_DESC` bez `countryOfOrigin`; filtrowanie donghua (`countryOfOrigin: CN`) jest opcjonalnym zawężeniem w UI ("tylko chińskie"), NIE domyślnym twardym filtrem (wiele donghua ma w bazach mieszane metadane).
- Błędy GraphQL przychodzą jako HTTP 200 z `errors[]` **oraz** jako 429 z `{"data":null,"errors":[{"message":"Too Many Requests.","status":429}]}` — parser MUSI sprawdzać `errors` zawsze.
- Rate limit: **30 req/min (stan zdegradowany API; docelowo 90)** → nasz TokenBucket: **0.4 req/s** (24/min — margines 20%), respektowanie `Retry-After` i `X-RateLimit-Reset`.
- Mapowanie pól: `episodes→total_episodes`, `seasonYear→year`, `format` (TV/TV_SHORT/MOVIE/ONA/OVA/SPECIAL/MUSIC) → `media_type`, `averageScore` (0–100) → `mean_score` (/10), `coverImage.medium→cover_url`, `idMal→mal_id`.

**Jikan: WYKLUCZONY** (F11 — wyłączenie instancji publicznej 01.10.2026; brak auth; niestabilność 504). Wzmianka w README w sekcji "Dlaczego oficjalne API".

## 5.3. Client Secret i Client ID — traktowanie (rygor 14 zadania)

- W kodzie występują WYŁĄCZNIE nazwy `MAL_CLIENT_ID` / `MAL_CLIENT_SECRET` (stałe konfiguracyjne), nigdy wartości.
- `.env` (gitignored) / `.env.example` (szablon z placeholderami) — wzór w §12.2.
- **Aplikacja w v1 w ogóle NIE potrzebuje `MAL_CLIENT_SECRET`** (F9: endpointy publiczne na sam `X-MAL-CLIENT-ID`). Pole istnieje w konfiguracji wyłącznie z myślą o przyszłym OAuth2 i jest zawsze puste w `.env.example`.
- Frozen exe: Client ID podawany w pierwszym uruchomieniu (dialog ustawień) → `config.json` w AppData; albo zmienna środowiskowa; albo `.env` obok exe (tryb dev/portable). Brak secretów w bundle — nic tajnego nie wycieknie z binarki.
- ⚠️ **Uwaga bezpieczeństwa (pilne):** w treści zadania pojawił się Client Secret wyglądający na prawdziwy (`7a51…`). Zgodnie z zasadą "nigdy nie commituj prawdziwego Client Secret" — **zalecam natychmiastową rotację tej pary w panelu https://myanimelist.net/apiconfig** i traktowanie jej jako skompromitowanej (wyciek do czatu/dokumentów). Nowa wartość trafia WYŁĄCZNIE do lokalnego `.env` (użytkownika) — repozytorium i binarka jej nie potrzebują.

## 5.4. Rate limiting, kolejka, backoff — mechanika obronna

Wszystko wewnątrz NetworkWorker (wątek sieciowy), więc GUI nie widzi żadnych opóźnień:

```text
request → Priority Queue (search/details=HIGH, covers=LOW)
        → TokenBucket.acquire()          # MAL: rate=1.0/s, capacity=2 (burst 2)
                                           # AniList: rate=0.4/s, capacity=1
        → HTTP (timeout=(5,10))
        → 2xx: parse → emit
        → 429/5xx/network: RetryPolicy
              delay(n) = min(base * factor^n, max_delay) * (1 ± jitter)
              base=1.0s factor=2.0 max_delay=60s jitter=0.2 attempts=4
              jeśli Retry-After obecny: delay = max(delay, Retry-After)
              403-HTML (F13): cooldown 300s + circuit breaker OPEN dla MAL
        → attempts wyczerpane: circuit_breaker.record_failure(); failover AniList; emit searchFailed
```

- **TokenBucket** (thread-safe, `threading.Lock`, `time.monotonic`): gwarantuje, że aplikacja NIGDY nie wyśle >1 req/s do MAL niezależnie od liczby kliknięć użytkownika — lokalny throttling jest pierwszą linią obrony przed 429 (rygor zadania).
- **Circuit breaker** per provider: próg 3 kolejnych `network/server/rate_limited` → OPEN 60 s (dla `throttled_ban` → 300 s); potem HALF_OPEN (1 próbne żądanie); sukces → CLOSED. Gdy MAL jest OPEN, wyszukiwania idą bezpośrednio do AniList bez próby MAL (szybszy UX w awarii).
- **Anulowanie:** flaga kooperacyjna `cancelled: Set[int]` (request_id) — worker porzuca emitowanie wyniku dla anulowanego request_id (nadal musi dokończyć HTTP dla higieny backoffa, ale wynik ląduje w koszu). Żadnego `QThread.terminate()` (R4).
- **Budżet żądań sesji wyszukiwania:** 1 debounce = maksymalnie 1 żądanie MAL (+ ewentualne retry). Typowa sesja "wpisuję tytuł" = 1–2 żądania, nie 10 (debounce 450 ms + cache 6 h).
- Nagłówek `User-Agent: DongStack/<version> (+<repo_url>)` — identyfikowalność i kultura wobec API.

## 5.5. Pierwsze uruchomienie (brak Client ID)

```text
start → config bez MAL_CLIENT_ID → AddDialog otwiera się w stanie:
   "Aplikacja potrzebuje darmowego Client ID MyAnimeList (jednorazowo).
    1. Zaloguj się na myanimelist.net → Account Settings → API → Create ID
    2. Wklej Client ID poniżej.        [____________]  [Zapisz]
    — lub pomiń i użyj źródła awaryjnego (AniList, bez rejestracji)."
```

To jedyny "formularz" w całej aplikacji poza AdvancedPage — i pojawia się raz. Sekcja w README z instrukcją krok po kroku (§11). AniList działa bez ID → aplikacja jest użyteczna od pierwszej minuty nawet bez konta MAL.

## 5.6. Auto-detekcja uniwersów (related_anime) — polityka żądań

Nowe żądania sieciowe wprowadzone przez funkcję uniwersów MUSZĄ przestrzegać budżetu ≤1 req/s i nie mogą opóźniać Quick Add:

1. `related_anime` pobierane **leniwie i asynchronicznie** (priorytet LOW w kolejce NetworkWorker) — dopiero PO zapisie dodanej pozycji i PO zamknięciu snackbara dodania.
2. Cache `api_cache` klucz `mal:related:<id>`, TTL **7 dni** (relacje franczyz zmieniają się rzadko). Trafienie w cache = zero żądań.
3. Jedno pobranie = maks. 1 żądanie MAL na dodaną pozycję (bez pełnego crawla franczyzy). Sugestia łączenia pojawia się tylko, gdy `node.id` z odpowiedzi istnieje już w bibliotece (porównanie z setem `mal_id` w pamięci kontrolera — O(1)).
4. Przy seryjnym dodawaniu 5 pozycji z tej samej franczyzy: pierwsza odpowiedź `related` zasila cache i kolejne sugestie przychodzą bez dodatkowych żądań (te same id w grafie).
5.Fallback AniList: `Media.relations { edges { relationType node { id idMal } } }` (analogiczny graf) — używany, gdy pozycja nie ma `mal_id` (dodana przez provider awaryjny bez `idMal`).

---

# §6. PODSYSTEM GUI — PRZEŁOŻENIE BIBLII GUI NA WYMAGANIA TECHNICZNE

Biblia GUI (dokument wejściowy, §1–§68) pozostaje **nadrzędnym prawem produktu** — niniejsza sekcja nie powtarza jej, a jedynie (a) doprecyzowuje decyzje wydajnościowe na E5500 i (b) mapuje na moduły z §3.4.

## 6.1. Hierarchia okien (zgodnie z Biblią §67)

- `MainWindow(QMainWindow)` → `centralWidget` → `QHBoxLayout` → `SidebarWidget(fixedWidth=210)` + `DashboardWidget(stretch=1)`.
- `DashboardWidget`: topBar (`QLabel` tytuł sekcji, stretch, `QLineEdit#localSearch`, `QToolButton#sortButton`) → separator → `QListWidget#donghuaList` → FAB `addButton` jako **overlay** (dziecko widgetu contentu, pozycjonowany w `resizeEvent`, `raise_()`) — nigdy wewnątrz scrollowanej listy (Biblia §14).
- `AddDialog(QDialog)`: non-modal (`show()`, nie `exec_()`), `QStackedWidget` [SearchPage | AdvancedPage], focus na `malSearch` przy otwarciu (Biblia §15–16).
- `SnackBar(QFrame)`: overlay contentu, `QTimer.singleShot(6000)` auto-hide, akcja "Cofnij" (Biblia §10).

## 6.2. Krytyczna ścieżka "+1" (najważniejsza czynność produktu)

```text
klik [+]  (wątek GUI, t=0)
  ├─ t≈0–2 ms:  DonghuaRow emituje episodeIncrementRequested(id)
  ├─ t≈2–8 ms:  DashboardController: walidacja (current<total gdy total>0),
  │             mutacja obiektu w pamięci, przeliczenie statusu (auto-complete §10 Biblii),
  │             row.updateValues() — TYLKO setText/setValue na istniejących widgetach
  │             (bez re-layoutu całej listy, bez tworzenia widgetów!)
  ├─ t≈8 ms:    sygnał saveEpisodeRequested(id, ep, request_id) → kolejka DbWorker (async)
  ├─ t≈10 ms:   countsChanged → aktualizacja 1 badge'a sidebara (setText)
  └─ t≈12 ms:   (jeśli auto-complete) SnackBar "Oznaczono … jako ukończone [Cofnij]"
DB (t≈10–300 ms, równolegle, niewidoczne): koalescencja 250 ms → UPDATE → saveSucceeded
błąd DB: saveFailed → rollback wartości wiersza + SnackBar "Nie udało się zapisać zmiany."
```

Wymagania techniczne ścieżki:
- **Brak przebudowy wiersza**: `DonghuaRow.updateValues(donghua)` aktualizuje wyłącznie `QLabel.setText`, `QProgressBar.setValue`, ewentualnie kropkę statusu. Zakaz `clear()+addItem()` na liście przy zmianie epizodu.
- Sortowanie "Ostatnio aktualizowane" po `+1`: wiersz POWINIEN przeskoczyć na górę — ale nie natychmiast (to dezorientuje i kosztuje). Przesunięcie następuje przy najbliższej naturalnej przebudowie listy (zmiana filtra/scroll-rebuild) — decyzja UX zgodna z Biblią (responsiveness > porządek). Opcja `reorder_on_update=true` w ustawieniach dla chętnych.
- `−` przy `current=0`: przycisk wyłączony (`setEnabled(False)` + QSS `:disabled`) — zero komunikatów.
- Undo dla `+1`: SnackBar "[Cofnij]" przez 6 s (komenda `Increment` na UndoStack, 1 poziom).

## 6.3. Wydajność listy głównej — ListBackend i próg skalowania

- v1: `WidgetListBackend` = `QListWidget` + `setItemWidget(DonghuaRow)` (Biblia §3.1) z OBOWIĄZKOWO:
  - `setUniformItemSizes(True)`, `setResizeMode(QListView.Adjust)`, stała wysokość wiersza 96 px (`setSizeHint`),
  - `setSpacing(6)`, `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)`,
  - aktualizacja przy zmianie filtra: **reuse istniejących wierszy** (pula `Dict[int, DonghuaRow]` + `takeItem`/`insertItem` różnicowo), pełny rebuild tylko gdy pula nie wystarcza; usunięte wiersze: `list.takeItem(i)` + `row.deleteLater()` (poprawne zwalnianie — rygor pamięciowy zadania),
  - maks. ~8 widgetów na wiersz (QLabel×4, QPushButton×2, QProgressBar, QFrame) — zgodnie z Biblią §3.
- **Gate wydajnościowy (§7.4):** przy `len(library) > 300` kontroler loguje ostrzeżenie, a `--selftest` mierzy czas rebuildu; jeśli na E5500 rebuild > 150 ms → aktywacja `DelegateListBackend` (`QListView + QAbstractListModel + QStyledItemDelegate`, `+/-` jako hit-test w `editorEvent` — Biblia §43). Interfejs `ListBackend` (ABC: `set_items`, `update_item`, `remove_item`) izoluje zamianę bez dotykania kontrolera.
- Okładki w wierszach: wyłącznie z bounded LRU (§4.8); brak okładki → placeholder (zero opóźnienia renderu).

## 6.4. Renderowanie i styl (rygor GMA 4500MHD)

### 6.4.1. Zakazy renderowania (egzekwowane w review + teście statycznym QSS)

| Zakaz | Powód |
|---|---|
| `QGraphicsBlurEffect`, `QGraphicsDropShadowEffect` (gdziekolwiek) | efekty = pełne przejście przez raster + cache tekstur; Biblia §32 wprost |
| animowane gradienty, `qlineargradient` w stanach hover/pressed | przeliczanie paint na każdy event; flat design |
| `border-image` z rozciąganiem na dużych powierzchniach | kosztowne skalowanie bitmap; używamy `background-color` |
| więcej niż 1 `QPropertyAnimation` jednocześnie | budżet R9 |
| `Qt.WA_TranslucentBackground` na oknie głównym | wymusza compositing (DWM off na Win7 classic / GMA) |
| frameless + custom shadow | j.w. |

Warstwowość dark mode realizujemy WYŁĄCZNIE kolorami powierzchni (Biblia §29/§32): `#121212 → #181818 → #1E1E1E → #242424 → #2A2A2A`, border `#303030/#444444`, tekst `#E6E1E5/#A0A0A0/#707070`, akcent `#B39DDB` (+hover `#C5B3E8`, +pressed `#9580BF`). Kolory statusów: kropka 8×8 px / pasek 3 px, nigdy całe tło karty.

### 6.4.2. QSS — organizacja

- 5 plików QSS (§3.4) ładowanych i sklejanych RAZ przy starcie (`theme.py`), `app.setStyleSheet(joined)` — zero ponownych parse'ów w runtime.
- QSS ogranicza selektory do `#objectName` i typów (zakaz uniwersalnych `*`, głębokich descendant-selectorów — koszt matchowania przy każdym polish).
- Paleta dodatkowo przez `QApplication.setPalette` (spójność widgetów natywnych: tooltipy, scrollbary).
- Font: `Segoe UI 13px` bazowo (Biblia §30/§40); brak fontów własnych w bundle.

### 6.4.3. Ikony — decyzja: PNG generowane programowo (D7)

Biblia §6.2 sugeruje SVG; **decyzja architektoniczna: ikony i logo generuje skrypt `tools/generate_branding.py` (Pillow, dev-only — rysunek wektorowych prymitywów kodem, render 4× supersampling + downscale LANCZOS), a do bundle wchodą wyłącznie PNG 16/20/24/32 px + `app.ico`**. Powody: (1) `QIcon` z SVG wymaga modułu QtSvg + pluginu qsvgicon → +8 MB w exe i koszt dekodowania wektorowego na GMA przy każdym renderze; (2) PNG w docelowym rozmiarze = blit bitmapy, najszybsza możliwa ścieżka; (3) `QIcon` z zestawem rozmiarów wybiera najbliższy — ostrość zachowana; (4) zgodne z decyzją Właściciela D7 ("grafiki możesz wygenerować w pythonie"). Nazewnictwo plików: `<nazwa>_<rozmiar>.png` (np. `add_24.png`); wyniki generatora są commitowane (build nie wymaga Pillow).

## 6.5. AddDialog / wyszukiwanie MAL — stany i skeleton

- Maszyna stanów (Biblia §20): `IDLE → SEARCHING → RESULTS|NO_RESULTS|ERROR`; `ERROR` zachowuje wpisany tekst + przycisk "Spróbuj ponownie" (ponawia OSTATNIE zapytanie, nie wymaga przeredagowania).
- Debounce: `QTimer(singleShot, 450 ms)`, restart na `textChanged` (Biblia §17). Minimum 2 znaki do wyzwolenia.
- Skeleton: **4 statyczne `SkeletonRow`** (`QFrame#skeletonBlock` o ton jaśniejsze od powierzchni — Biblia §38). Animacja pulsowania: zaimplementowana, ale **domyślnie WYŁĄCZONA** flagą `animations` (auto-off gdy `--selftest` zmierzy CPU>5% przy pulsowaniu; rygor 18 zadania: "na tym sprzęcie skeleton może być statyczny").
- `request_id`: każdy `searchRequested` niesie monotoniczny int; `searchFinished(rid, items)` jest ignorowane gdy `rid != current` (R5, Biblia §19).
- Wyniki: `MalResultRow` z QuickAdd (`+`) i Advanced (`⋮`); duplikaty: badge "✓ Już w bibliotece" + przygaszone tło, dodawanie NIEZABLOKOWANE (Biblia §23); deduplikacja po `mal_id` wobec biblioteki w pamięci (O(1) `set`).
- Quick Add: status `planned`, episode 0, zapis async, SnackBar "[Cofnij] [Edytuj]", **dialog zostaje otwarty** do seryjnego dodawania (Biblia §24).
- Advanced Page (stan r11): **nagłówek** (tytuł + `QLabel#altLabel` z tytułem alternatywnym, ukryty gdy brak) → `QScrollArea` z `QFormLayout` (segmentowy status: `QButtonGroup` exclusive, 4×`QPushButton` checkable; `QSpinBox` odcinka; `QSpinBox` liczby odcinków z `specialValueText = „—”`; wybór uniwersum), polem **notatki** (`QPlainTextEdit` 64 px, nad linkami) i `StreamingLinksWidget` ([TAG] [URL], auto-TAG z domeny, Ctrl+V dokleja wiersz **poza** polami tekstowymi) → **przypięty pasek akcji** (Usuń / Wstecz / Zapisz). Scroll jest wymagany przez R17 (dialog nie może rosnąć ponad ekran), a sufit spinboksa odcinka wynika z R18 (`total = 0` → `EPISODE_OPEN_CEILING = 9999`, clamp wyłącznie dla `total > 0`).

## 6.6. Dostępność klawiaturowa i shortcuty (Biblia §47)

`Ctrl+F` lokalne szukaj, `Ctrl+N` AddDialog, `Esc` zamyka popup/dialog, `Enter` aktywuje focused button / Quick Add na zaznaczonym wyniku MAL, `↑/↓` nawigacja wyników, `Tab` przez `+`/`−` wierszy (`setFocusPolicy(Qt.TabFocus)`), tooltippy akcji (Biblia §48). Focus widoczny przez border accent (Biblia §35).

## 6.7. Uniwersa na dashboardzie (M9: płaska lista + hover-highlight)

> **Redesign v1.2.0 (feedback produkcyjny r7):** zwijane nagłówki grup USUNIĘTE.
> Root-cause buga layoutu: `QListWidget.setUniformItemSizes(True)` + dwa rozmiary
> itemów (nagłówek 34 px / karta 96 px) = niezdefiniowane zachowanie layoutu Qt
> (luki między grupami przy częściowym rozwinięciu, nakładanie się kart przy
> rozwinięciu środkowej grupy). Klasa błędu zlikwidowana u źródła: lista ZAWSZE
> ma jeden rozmiar wiersza.

- **Sort „Uniwersa (kolejność oglądania)”** (`SortMode.WATCH_ORDER`): płaska lista
  kart; bloki uniwersów stoją obok siebie (kolejność bloków: max updated_at desc,
  kolejność członków: `watch_order` §4.9.2 + override'y „przesuń ↑/↓” w menu
  kontekstowym karty), pozycje bez uniwersum na końcu w bieżącym sorcie.
- **Dwupoziomowe podświetlenie uniwersum (hover):** karta pod kursorem = poziom 2
  (tint rgba(179,157,219,26) + pełny pasek akcentu 3 px przy lewej krawędzi),
  pozostałe karty tego samego uniwersum = poziom 1 (tint rgba(179,157,219,14)
  + pasek ćwierć-kryty). Psychologia: kursor = „tu jestem”, uniwersum = „to rodzina”
  — bez klikania, bez zwijania, bez utraty kontekstu listy. Implementacja:
  `DonghuaRow.enterEvent/leaveEvent → hoverStateChanged → backend.set_universe_hover()`
  (widget backend: repaint tylko kart o zmienionym poziomie; delegate backend:
  `viewport().update()` — malowane są wyłącznie widoczne wiersze, budżet G3).
- Brak stanu collapsed w kontrolerze (`toggle_universe`/`_collapsed` USUNIĘTE);
  `DisplayHeader` i `universe_header.py` usunięte z kodu i z obu backendów.
- Filtry statusów i lokalne szukanie działają ortogonalnie (bloki liczą się
  z widocznych pozycji); badge'e sidebara bez zmian (liczą pozycje, nie uniwersa).
- Wydajność: hover-highlight = repaint ≤ liczby członków uniwersum (widget) lub
  viewportu (delegate); przebudowa listy przy zmianie filtra/sortu = 1× set_items
  (budżet §7.4 G3 bez zmian).

---

# §7. BUDŻETY WYDAJNOŚCIOWE I POMIAR

## 7.1. Budżet pamięci (E5500, 2 GB)

| Komponent | Cel |
|---|---|
| Python 3.13 + Qt5 DLL (załadowane) | ~90–120 MB (private bytes) |
| Biblioteka 300 pozycji (modele w pamięci) | < 2 MB |
| Wiersze listy (widoczne + pula ~40 widgetów) | ~15–25 MB |
| Pixmapy okładek (LRU 64 × 180×220×4 B) | ~10 MB (+QPixmapCache 8 MB) |
| **RAZEM cel** | **≤ 250 MB private bytes** (twardy gate w M7) |

Techniki: `deleteLater()` dla usuwanych wierszy; brak trzymania surowych dict-ów JSON po konwersji na dataclasses; `del` referencji do QImage po konwersji; cover-y dekodowane ze skalowaniem (§4.8); logi rotowane 3×1 MB; zero `gc.collect()` na ścieżce interakcji (koszt na C2D; Python sam zarządza generacyjnie).

## 7.2. Budżet startu

| Faza | Budżet | Technika |
|---|---|---|
| process start → QApplication (onedir) | ≤ 0,8 s | importy leniwe: `main.py` importuje Qt + bootstrap; moduły `api/`, `gui/add/` importowane przy PIERWSZYM użyciu (AddDialog) — mniejszy koszt zimnego importu |
| → okno widoczne ze skeletonem dashboardu | ≤ 1,5 s | okno pokazujemy PRZED `libraryLoaded` (async DB) |
| → lista wypełniona (300 pozycji, bez okładek) | ≤ 2,5 s | wsadowe `addItem` z `setUpdatesEnabled(False)` na czas wypełniania |
| → okładki widocznych wierszy | ≤ 4 s | lazy, priorytet viewport |
| onefile: + ekstrakcja ~150 MB do %TEMP% | +5–20 s na HDD | **dlatego onedir jest REKOMENDOWANY na E5500 (§8.1)** |

## 7.3. `--selftest` (wbudowany benchmark; używany w CI i na maszynie docelowej)

```text
DongStack.exe --selftest
→ tryb offscreen (QT_QPA_PLATFORM=offscreen), tworzy MainWindow,
  ładuje 300 syntetycznych pozycji, wykonuje:
  - 200× episodeIncrement (pomiar p95 czasu handlera GUI)
  - 30× rebuild filtra
  - pomiar RSS (GetProcessMemoryInfo przez ctypes — bez psutil)
  - zliczenie wątków procesu
→ stdout: JSON {"gui_p95_ms":..., "rebuild_ms":..., "rss_mb":..., "threads":3}
→ exit code 0/1 wg progów (CI: progi luźne; M7 na E5500: progi §1.3)
```

## 7.4. Gate'y (warunki przejścia dalej)

| Gate | Warunek | Akcja przy oblaniu |
|---|---|---|
| G1 (M0) | exe Track-A startuje na fizycznym E5500 | przełącz na Track B (§2.2) |
| G2 (M3) | p95 handlera `+1` ≤ 8 ms (offscreen CI) / ≤ 50 ms (E5500) | profilowanie; uproszczenie updateValues |
| G3 (M6) | rebuild 300 wierszy ≤ 150 ms na E5500 | implementacja `DelegateListBackend` (Biblia §43) |
| G4 (M7) | RSS ≤ 250 MB przy 300 pozycjach | audyt pixmap/LRU; zmniejszenie puli |
| G5 (M7) | idle CPU ≤ 1% | wyłączenie pozostałych animacji |

---

# §8. FREEZING: PYINSTALLER

## 8.1. Decyzja: onedir (rekomendowany) + onefile (portable) — OBA artefakty z CI

| Kryterium | onedir (`DongStack\…`) | onefile (`DongStack.exe`) |
|---|---|---|
| Start na E5500 (HDD 5400 rpm) | **1–3 s** | +5–20 s (rozpakowanie ~150 MB do %TEMP% przy KAŻDYM starcie) + zużycie dysku |
| RAM przy starcie | niższy | wyższy chwilowo (I/O cache ekstrakcji) |
| Antywirus/SmartScreen | mniej fałszywych alarmów | klasyczny problem heurystyk AV na Win7 |
| Dystrybucja | ZIP (~60–80 MB) | jeden plik (wygoda) |
| Aktualizacja | podmiana katalogu | podmiana pliku |

**Rekomendacja architekta:** na maszynie docelowej (E5500) jako codzienny użytek **onedir z ZIP-a** (rozpakuj raz → shortcut na pulpicie); **onefile** jako artefakt "wrzuć i uruchom" dla wygody/USB. CI produkuje oba (matrix `package: [onedir, onefile]`), README prezentuje oba z jasnym oznaczeniem rekomendacji. Wymaganie zadania ("samodzielny plik wykonywalny .exe") jest spełnione przez wariant onefile; uczciwość inżynierska wymaga pokazać jego koszt startu na tym sprzęcie.

## 8.2. Plik `packaging/dongstack.spec` (kompletny projekt)

```python
# -*- mode: python ; coding: utf-8 -*-
# DongStack — PyInstaller spec
# Budowanie:  python -m PyInstaller packaging/dongstack.spec --noconfirm
# Wariant onefile:  set DHT_ONEFILE=1   (Windows) / DHT_ONEFILE=1 (shell)
# Zmienne dostarczone przez PyInstaller: SPECPATH, DISTPATH, workpath
import os
import sys

SPECPATH_DIR = os.path.abspath(SPECPATH)                 # ...\build
ROOT = os.path.abspath(os.path.join(SPECPATH_DIR, ".."))  # katalog repo

APP_NAME   = "DongStack"
ENTRY      = os.path.join(ROOT, "app", "main.py")
ICON       = os.path.join(ROOT, "app", "resources", "icons", "app.ico")
VERSION_RC = os.path.join(SPECPATH_DIR, "version_info.txt")
ONEFILE    = os.environ.get("DHT_ONEFILE", "0") == "1"

# --- Zasoby (QSS, ikony PNG) pakowane do wnętrza binarium -------------------
# Docelowy układ w bundle:  <_MEIPASS>/app/resources/{styles,icons}
# (identyczny z układem repo -> resource_path() działa bez rozgałęzień)
datas = [
    (os.path.join(ROOT, "app", "resources", "styles"), os.path.join("app", "resources", "styles")),
    (os.path.join(ROOT, "app", "resources", "icons"),  os.path.join("app", "resources", "icons")),
]

# --- Moduły WYKLUCZONE (rozmiar + RAM + brak potrzeby na Win7) --------------
excludes = [
    # Python dev/runtime noise
    "tkinter", "_tkinter", "pydoc_data", "doctest", "pdb",
    "pytest", "pip", "setuptools", "wheel", "ruff", "responses",
    # Nieużywane moduły PyQt5 (Python-level; DLL-e nie zostaną wciągnięte)
    "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebChannel",
    "PyQt5.QtWebSockets", "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuickWidgets",
    "PyQt5.Qt3DCore", "PyQt5.Qt3DRender", "PyQt5.QtBluetooth", "PyQt5.QtNfc",
    "PyQt5.QtPositioning", "PyQt5.QtLocation", "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets", "PyQt5.QtSerialPort", "PyQt5.QtSerialBus",
    "PyQt5.QtSql", "PyQt5.QtCharts", "PyQt5.QtDataVisualization",
    "PyQt5.QtNetwork",            # HTTP robimy przez requests (mniej DLL w bundle)
    "PyQt5.QtSvg",                # ikony jako PNG (§6.4.3)
    "PyQt5.QtTest", "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.QtPrintSupport",
    "PyQt5.QtOpenGL", "PyQt5.QtXml", "PyQt5.QtXmlPatterns",
]

# --- Analiza ----------------------------------------------------------------
a = Analysis(
    [ENTRY],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=["sqlite3"],          # importowany dynamicznie w workerze — jawnie
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# --- Czystka assetów Qt (translacje poza en/pl, zbędne pluginy) -------------
# PyQt5-Qt5 5.15.2 (Windows) zawiera pełny zestaw qt_*.qm i pluginów;
# hook PyInstallera domyślnie bierze tylko potrzebne, ale dobijamy resztę:
_KEEP_PLUGINS = ("platforms", "styles", "imageformats")
_KEEP_IMGFMT  = ("qjpeg", "qico", "qgif")          # qsvg usunięty (§6.4.3)
def _keep(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    if "/translations/" in p or p.endswith(".qm"):
        return ("qt_en" in p) or ("qt_pl" in p)
    if "/plugins/" in p:
        parts = p.split("/")
        try:
            i = parts.index("plugins")
        except ValueError:
            return True
        fam = parts[i + 1] if i + 1 < len(parts) else ""
        if fam not in _KEEP_PLUGINS:
            return False
        if fam == "imageformats":
            return any(k in p for k in _KEEP_IMGFMT)
    return True

a.datas = [d for d in a.datas if _keep(d[0])]
a.binaries = [b for b in a.binaries if _keep(b[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    *([] if not ONEFILE else [a.binaries, a.datas, a.zipfiles]),
    exclude_binaries=(not ONEFILE),
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # BEZWZGLĘDNIE: UPX uszkadza DLL-e Qt + flagi AV na Win7
    console=False,              # windowed bootloader (brak czarnego okna cmd)
    disable_windowed_traceback=False,
    icon=ICON,
    version=VERSION_RC,
)

if not ONEFILE:
    coll = COLLECT(
        exe, a.binaries, a.datas,
        strip=False, upx=False, name=APP_NAME,
    )
```

`packaging/version_info.txt` (szkielet):

```python
VSVersionInfo(
  ffi=FixedFileInfo(filevers=(1,0,0,0), prodvers=(1,0,0,0), ...),
  kids=[StringFileInfo([StringTable('040904b0', [
      StringStruct('FileDescription', 'DongStack — osobisty tracker donghua'),
      StringStruct('ProductName', 'DongStack'),
      StringStruct('ProductVersion', '1.0.0'),
      StringStruct('LegalCopyright', 'Copyright (C) 2026 <autor> — MIT License'),
  ]))], VarFileInfo([VarStruct('Translation', [1033, 1200])])
)
```

## 8.3. Rozdzielanie zasobów w runtime (`app/core/paths.py`)

```python
import os, sys

def resource_path(*rel: str) -> str:
    """Działa identycznie w dev i w frozen exe (onedir oraz onefile)."""
    base = getattr(sys, "_MEIPASS", None)          # frozen: katalog rozpakowania/_internal
    if base is not None:
        return os.path.join(base, "app", "resources", *rel)
    here = os.path.dirname(os.path.abspath(__file__))   # dev: app/core/paths.py
    return os.path.join(os.path.dirname(here), "resources", *rel)

def app_data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "DongStack")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d
```

Zasada: `datas` w .spec odwzorowują strukturę `app/resources/…` 1:1, więc `resource_path("styles", "base.qss")` i `resource_path("icons", "add.png")` działają bez warunków na frozen/dev (jedyny branch = `_MEIPASS`). `sys._MEIPASS` istnieje także w onedir (PyInstaller 6: wskazuje `_internal/`).

## 8.4. Ręczny build na laptopie E5500 (Win7) — runbook

```bat
:: 1) Instalacja Python-Win7 3.13.5 (amd64 lub x86 wg bitowości systemu)
python-3.13.5-amd64-full.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
:: 2) Repo + zależności
git clone https://github.com/karnyjohnny/dongstack.git
cd dongstack
python -m venv .venv && .venv\Scripts\activate
python -m pip install -r requirements.txt -r requirements-dev.txt
:: 3) Build (onedir rekomendowany)
python -m PyInstaller packaging\dongstack.spec --noconfirm
dist\DongStack\DongStack.exe
:: 4) Wariant onefile
set DHT_ONEFILE=1 && python -m PyInstaller packaging\dongstack.spec --noconfirm --distpath dist-onefile
```

Uwaga: build lokalny na E5500 (2 GB RAM) jest wolny (~10–20 min) — normalne; CI robi to w ~5 min.

---

# §9. CI/CD: GITHUB ACTIONS

## 9.1. Przegląd potoku

```text
push/PR → ci.yml:      ruff (lint+format check) → pytest (unit+gui offscreen, CPython 3.13 official)
tag v*  → release.yml: build matrix [win32, amd64] × [onedir, onefile] NA Python-Win7 3.13.5
                       (pinned commit + SHA256) → smoke --selftest offscreen → artefakty
                       → job release: ZIP-y + exe + SHA256SUMS.txt → GitHub Release
```

Dlaczego build na Python-Win7 w CI (a nie na oficjalnym 3.13 z `actions/setup-python`)? Bo oficjalny python313.dll **nie uruchomi się na czystym Win7** (F1). Artefakt musi być zbudowany interpreterem z patchami Win7, by spełnić wymagania platformy docelowej — a buildy Python-Win7 działają też na nowszym Windows (w tym na runnerze `windows-2022`).

## 9.2. `packaging/python-win7.json` (pin zaufania — sprawdzane sumy)

```json
{
  "repo": "Alex313031/Python-Win7",
  "commit": "2aba455bcf205d0f12fc55aa59adc352196d46c2",
  "version": "3.13.5",
  "files": {
    "amd64": {
      "name": "python-3.13.5-amd64-full.exe",
      "size": 81884004,
      "sha256": "9670a588c086621763329aabd2cfcfdb9f6f5f04ff515cbd309e64edd0be92b3"
    },
    "win32": {
      "name": "python-3.13.5-full.exe",
      "size": 77753711,
      "sha256": "29e3fd56c2904f182a5a390da2f1f7727f6f41f660a042ad955b958eeddf2158"
    }
  },
  "verified_on": "2026-09-26",
  "regenerate": "python tools/hash_python_win7.py"
}
```

(Sumy obliczone praktycznie przez pobranie plików z przypiętego commita — nie są przepisane z README.)

## 9.3. `.github/workflows/release.yml` (kompletny projekt)

```yaml
name: release
on:
  push:
    tags: ["v*"]
  workflow_dispatch:

permissions:
  contents: write          # tworzenie GitHub Release

env:
  PY_REQ: "3.13.5"

jobs:
  build:
    runs-on: windows-2022
    strategy:
      fail-fast: false
      matrix:
        arch: [amd64, win32]
        package: [onedir, onefile]
    steps:
      - uses: actions/checkout@v4

      - name: Read pinned Python-Win7 manifest
        id: pin
        shell: pwsh
        run: |
          $m = Get-Content packaging/python-win7.json -Raw | ConvertFrom-Json
          $f = $m.files.'${{ matrix.arch }}'
          "COMMIT=$($m.commit)"       | Out-File -Append $env:GITHUB_OUTPUT
          "FILENAME=$($f.name)"       | Out-File -Append $env:GITHUB_OUTPUT
          "SHA256=$($f.sha256)"       | Out-File -Append $env:GITHUB_OUTPUT

      - name: Download & VERIFY Python-Win7 installer (supply-chain pin)
        shell: pwsh
        run: |
          $url = "https://raw.githubusercontent.com/Alex313031/Python-Win7/${{ steps.pin.outputs.COMMIT }}/3.13.5/${{ steps.pin.outputs.FILENAME }}"
          Invoke-WebRequest -Uri $url -OutFile py-setup.exe
          $h = (Get-FileHash py-setup.exe -Algorithm SHA256).Hash.ToLower()
          if ($h -ne "${{ steps.pin.outputs.SHA256 }}".ToLower()) {
            Write-Error "SHA256 mismatch! expected=${{ steps.pin.outputs.SHA256 }} got=$h"; exit 1
          }

      - name: Install Python (silent)
        shell: cmd
        run: |
          py-setup.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=0
          python --version
          python -c "import sys; print(sys.executable)"

      - name: Install pinned dependencies
        run: python -m pip install --disable-pip-version-check -r requirements.txt -r requirements-dev.txt

      - name: Verify frozen-target stack
        run: |
          python -c "import PyQt5.QtCore as c; print('Qt', c.QT_VERSION_STR, 'PyQt', c.PYQT_VERSION_STR)"
          python -m PyInstaller --version

      - name: Build (${{ matrix.package }} / ${{ matrix.arch }})
        shell: cmd
        run: |
          set DHT_ONEFILE=${{ matrix.package == 'onefile' && 1 || 0 }}
          python -m PyInstaller packaging\dongstack.spec --noconfirm ^
            --distpath dist\${{ matrix.arch }}-${{ matrix.package }} ^
            --workpath work\${{ matrix.arch }}-${{ matrix.package }}

      - name: Smoke test (offscreen --selftest)
        shell: pwsh
        run: |
          $env:QT_QPA_PLATFORM = "offscreen"
          $exe = if ("${{ matrix.package }}" -eq "onefile") {
            "dist\${{ matrix.arch }}-onefile\DongStack.exe"
          } else {
            "dist\${{ matrix.arch }}-onedir\DongStack\DongStack.exe"
          }
          & $exe --selftest | Tee-Object selftest-${{ matrix.arch }}-${{ matrix.package }}.json
          if ($LASTEXITCODE -ne 0) { exit 1 }

      - name: Package artifacts
        shell: pwsh
        run: |
          if ("${{ matrix.package }}" -eq "onedir") {
            Compress-Archive "dist\${{ matrix.arch }}-onedir\DongStack" `
              "DongStack-${{ env.PY_REQ }}-win-${{ matrix.arch }}-onedir.zip"
          } else {
            Copy-Item "dist\${{ matrix.arch }}-onefile\DongStack.exe" `
              "DongStack-${{ env.PY_REQ }}-win-${{ matrix.arch }}-portable.exe"
          }
          Get-FileHash DongStack-* | ForEach-Object {
            "{0}  {1}" -f $_.Hash.ToLower(), (Split-Path $_.Path -Leaf)
          } | Out-File -Append SHA256SUMS-${{ matrix.arch }}-${{ matrix.package }}.txt

      - uses: actions/upload-artifact@v4
        with:
          name: dist-${{ matrix.arch }}-${{ matrix.package }}
          path: |
            DongStack-*
            SHA256SUMS-*.txt
            selftest-*.json

  release:
    needs: build
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with: { path: artifacts, merge-multiple: true }
      - name: Merge checksums
        run: cat artifacts/SHA256SUMS-*.txt | sort -u > artifacts/SHA256SUMS.txt
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            artifacts/DongStack-*.zip
            artifacts/DongStack-*-portable.exe
            artifacts/SHA256SUMS.txt
          generate_release_notes: true
```

## 9.4. `.github/workflows/ci.yml` (lint + testy na każdym push/PR)

```yaml
name: ci
on:
  push: { branches: [main] }
  pull_request:
jobs:
  quality:
    runs-on: windows-2022        # Windows, bo testy GUI z PyQt5 (offscreen)
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13", cache: "pip" }   # CI-test na oficjalnym CPython (szybko);
                                                          # zgodność z Win7-buildem pilnuje smoke w release.yml
      - run: python -m pip install -r requirements.txt -r requirements-dev.txt
      - run: python -m ruff check .
      - run: python -m ruff format --check .
      - name: pytest (GUI offscreen)
        env: { QT_QPA_PLATFORM: "offscreen" }
        run: python -m pytest tests/unit tests/gui -q --maxfail=3
      # tests/live NIGDY domyślnie (opt-in RUN_LIVE_API_TESTS + sekret repo)
```

## 9.5. Zasady CI/CD

- **Reprodukowalność:** wszystko przypięte (pip co do patcha, PyInstaller, actions co do major-tag z rekomendacją pin-SHA dla `softprops/action-gh-release`; Python-Win7: commit+SHA256). `workflow_dispatch` pozwala odtworzyć build historycznego taga.
- **Live-testy API w CI:** wyłącznie ręcznie (`workflow_dispatch` + input `run_live=true`) i z `MAL_CLIENT_ID` z **GitHub Secrets** (nigdy w pliku workflow). Client Secret w CI jest zbędny (§5.3).
- **Cache pip** po hashu `requirements*.txt`.
- Rozmiar artefaktów: onedir ZIP ~60–80 MB (po czystce pluginów/translacji §8.2); poniżej limitów GH Releases.
- Tag `v1.0.0` → pełna macierz 4 artefaktów (2 arch × 2 package).

---

# §10. STRATEGIA TESTÓW

## 10.1. Piramida

| Poziom | Zakres | Narzędzia | Uruchamianie |
|---|---|---|---|
| Unit (70%) | rate_limiter (symulacja czasu), retry/backoff (Retry-After, jitter bounds), circuit_breaker, api_cache (TTL/stale), repository (sqlite `:memory:`), migrations (v0→v1, backup), config+masking (R14), dotenv_lite, undo commands, normalizacja modeli MAL/AniList | pytest, `responses` (nagrane fixtures) | każdy push (ci.yml) |
| GUI (20%) | sygnały `DonghuaRow` (klik + → `episodeIncrementRequested`), optymistyczny update + rollback po `saveFailed`, race `request_id` (stara odpowiedź NIE nadpisuje — R5), koalescencja zapisów (R10), filtr/sort, detektor R1 (sqlite3/requests w wątku GUI = fail), `deleteLater` przy usuwaniu wierszy | pytest-qt, `QT_QPA_PLATFORM=offscreen` | każdy push |
| Integracja live (opt-in) | smoke 3 zapytań MAL + 1 AniList, asercje schematu (`data[].node.id`, `paging.next`), próg 429 nieosiągalny w teście (nie floodujemy!) | pytest + znacznik `@pytest.mark.live`, `RUN_LIVE_API_TESTS=1`, `MAL_CLIENT_ID` z env | ręcznie / workflow_dispatch |
| Wydajnościowe | `--selftest` (p95 `+1`, rebuild, RSS, liczba wątków) | exe zbudowany w CI; na E5500 w M7 | tag + M7 |
| Manual QA (macierz) | E5500/Win7: instalacja, pierwszy start, first-run Client ID, 20× `+1`, seryjne Quick Add (5 tytułów), undo wszystkich operacji, offline start (stale cache), kill -9 przy zapisie (spójność WAL), migracja z v1.0 | checklist w `docs/` | przed każdym release |

## 10.2. Fixtures = nagrane odpowiedzi (zero sekretów w testach)

`tests/fixtures/*.json` zawierają **zdenormalizowane nagrania realnych odpowiedzi** (uzyskane live 2026-09-26, Załącznik B): `mal_search.json`, `mal_details.json`, `mal_ranking.json`, `anilist_page.json`, `mal_400_limit.json`, `mal_429.txt` (z `Retry-After`). Testy `responses`-owe odtwarzają je — CI nie potrzebuje sieci ani Client ID. Nagłówki autoryzacyjne w nagraniach są usunięte/zamaskowane.

## 10.3. Jakość statyczna

`ruff` (pyproject.toml): `target-version = "py38"` (twardy baseline §16), reguły: E,F,W,I,UP (z `--ignore UP006,UP007,UP035` — wymuszają składnię 3.9+/3.10+, której ZAKAZUJEMY), B (bugbear), SIM wybiórczo, + własny zakaz: grep-lint `verify=False`, `QThread.terminate`, `exec_` z `QMessageBox` w kontrolerach (custom test statyczny `tests/unit/test_architecture.py` parsujący AST repo pod kątem R1/R4/R13).

---

# §11. STRUKTURA README.md

```text
┌──────────────────────────────────────────────────────────────┐
│ [hero: screenshot dashboardu dark-mode + logo]                │
│  # 🀄 DongStack                                               │
│  Osobisty tracker donghua na Windows — +1 jednym kliknięciem, │
│  serie łączone w UNIWERSA i układane w kolejności oglądania   │
│  (S1 → S2 → … → filmy → specjały). Działa na Windows 7 SP1.   │
│  [badge: Release] [CI] [Windows 7+] [Python 3.13] [License]   │
├──────────────────────────────────────────────────────────────┤
│  ## ✨ Dlaczego                                              │
│   • +/− zawsze widoczne, zmiana odcinka = 1 klik (<50 ms)    │
│   • Undo zamiast potwierdzeń • działa offline (cache)        │
│   • zbudowany pod Core 2 Duo / 2 GB RAM — flat dark UI       │
│  ## 📸 Zrzuty (dashboard, AddDialog, snackbar Undo)           │
│  ## ⬇️ Instalacja (Windows)                                   │
│   1. Pobierz z Releases: …-onedir.zip (REKOMENDOWANY na stary │
│      sprzęt) lub …-portable.exe (jednoplikowy)               │
│   2. Rozpakuj → DongStack.exe (SHA256SUMS do weryfikacji)│
│   3. Pierwsze uruchomienie: podaj darmowy MAL Client ID       │
│      (instrukcja 3 kroków + link) albo pomiń → tryb AniList   │
│   Wymagania: Windows 7 SP1+ (x86/x64), ~200 MB dysk           │
│  ## 🚀 Uruchomienie ze źródeł (krok po kroku)                │
│   Windows 7: instalator Python-Win7 3.13.5 (link+checksum) →  │
│   git clone → venv → pip install -r requirements.txt →        │
│   python -m app.main ;  Windows 10/11: setup-python 3.13      │
│  ## 👩‍💻 Dla deweloperów                                       │
│   • struktura projektu (drzewko §3.4)                         │
│   • testy: pytest (QT_QPA_PLATFORM=offscreen)                 │
│   • lint: ruff                                                │
│   • BUDOWA EXE: pip install -r requirements-dev.txt →         │
│     pyinstaller packaging\dongstack.spec (onedir) /         │
│     DHT_ONEFILE=1 (portable); artefakty w dist\               │
│   • CI/CD: tag v* → release.yml (matrix, sumy SHA256)         │
│   • live-testy API: RUN_LIVE_API_TESTS=1 + MAL_CLIENT_ID      │
│  ## ⚙️ Konfiguracja (.env / config.json; tabela zmiennych)     │
│  ## 🏗️ Architektura (link do docs/SPECYFIKACJA-TECHNICZNA.md) │
│  ## 🐛 Rozwiązywanie problemów                               │
│   Win7: wymagane SP1 + KB2533623/KB2999226 (UCRT); SmartScreen│
│   /AV przy onefile; wolny start onefile na HDD → użyj onedir  │
│  ## 📜 Licencja (MIT)                                         │
│  ## 🙏 Podziękowania/atrybucja                                │
│   "Dane: MyAnimeList.net (oficjalne API v2)"                  │
│   "This product uses the AniList API but is not endorsed or   │
│    certified by AniList."                                     │
└──────────────────────────────────────────────────────────────┘
```

Zasady README: bez emoji-śmieci w nadmiarze, bez sekretów (Client ID użytkownika NIGDY — tylko instrukcja wyrobienia własnego), screenshoty jako PNG WebP-friendly ≤300 KB, sekcja instalacji czytelna dla nietechnicznego użytkownika (krok, ekran, gotowe), sekcja dev z dokładnymi komendami kopiuj-wklej.

---

# §12. BEZPIECZEŃSTWO I SEKRETY

## 12.1. Polityka (rygor 14 zadania)

1. Prawdziwy `MAL_CLIENT_SECRET` **nigdy** nie trafia do: kodu, repo, README, logów, testów, artefaktów CI, binarki.
2. `MAL_CLIENT_ID` jest traktowany jak identyfikator publiczny aplikacji (trafia do nagłówka każdego żądania), ale i tak nie commitujemy cudzego/prawdziwego ID — użytkownik podaje własne w first-run (§5.5) lub w `.env` lokalnie.
3. Logi: filtr maskujący (`SecretsFilter`) zamienia każdą wartość skonfigurowaną jako sekret na `***` przed zapisem; `ConfigService.__repr__` maskuje pola `*_SECRET*`; test jednostkowy R14 przechwytuje strumień logów i asertuje brak sekretu.
4. TLS: `verify=True` zawsze (certifi pin), zakaz `verify=False` egzekwowany lintem; brak proxy-config w v1.
5. Dane osobowe: baza lokalna zawiera wyłącznie dane katalogowe anime + postęp użytkownika; brak telemetrii, brak analityki, zero połączeń poza MAL/AniList/CDN okładek.
6. **Rotacja:** para Client ID/Secret ujawniona w treści zadania (`c13fe…`/`7a51…`) jest uważana za SKOMPROMITOWANĄ → zalecenie natychmiastowej regeneracji w panelu MAL (§5.3). Do testów live w trakcie prac użyto wyłącznie Client ID (secret nie był potrzebny — F9); w dokumentacji wartości są maskowane.

## 12.2. Pliki konfiguracyjne

`.env.example` (commitowany szablon — placeholders):

```dotenv
# Skopiuj do .env i uzupełnij WŁASNYMI wartościami. .env jest w .gitignore!
# Jak zdobyć Client ID: myanimelist.net → Account Settings → API → Create ID
MAL_CLIENT_ID=twoj_client_id_tutaj
# Client Secret NIE jest potrzebny do funkcji aplikacji (publiczne endpointy MAL).
# Pole istnieje wyłącznie na przyszłość (OAuth2). NIGDY go nie commituj.
MAL_CLIENT_SECRET=
# Opcjonalne: wymuś providera awaryjnego (gdy brak Client ID lub awaria MAL)
DHT_PREFERRED_PROVIDER=mal
```

`.gitignore` (fragment kluczowy):

```gitignore
.env
*.sqlite
*.sqlite-wal
*.sqlite-shm
dist/
dist-onefile/
work/
build/*/            # artefakty, NIE build/*.spec|version_info|python-win7.json
logs/
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
```

## 12.3. Licencja (D6)

- **Kod źródłowy repo: MIT** (`LICENSE`, Copyright (c) 2026 KarnyJohnny) — zgodnie z wolą Właściciela ("chcę się tym dzielić").
- **Uwaga prawna dot. binariów:** PyQt5 jest licencjonowany **GPL v3** (lub komercyjnie przez Riverbank). Zlinkowanie MIT-kodu z PyQt5/Qt w jednym exe sprawia, że **dystrybuowana binarka podlega GPL v3** — jest to w pełni legalne i spójne z niekomercyjnym, otwartym charakterem projektu (MIT jest GPL-kompatybilny: kod MIT może wejść w dzieło GPL). W README i w oknie "O aplikacji" znajdzie się notka: *"DongStack (MIT) używa PyQt5/Qt (GPL v3) — dystrybuowane binaria podlegają GPLv3."*
- Alternatywa LGPL (PySide6/Qt6) została wykluczona przez brak wsparcia Windows 7 (Załącznik A) — PyQt5 jest jedyną realną opcją na tej platformie, co Właściciel potwierdził (D6).
- Dane z MAL/AniList: w README sekcja atrybucji (§11) zgodna z wymogami obu API.

---

# §13. REJESTR RYZYK

| # | Ryzyko | Prawd. | Wpływ | Mitygacja |
|---|---|---|---|---|
| RR1 | Build Python-Win7 3.13.5 nie uruchomi się na konkretnej instalacji "JG 2021" (brakujące KB, specyfika moda) | **niskie** (D4: interpreter + import PyQt5 już działają u Właściciela) | krytyczny | M0 = test freeze/launch; Track B (3.8.10) bez zmian w kodzie (§16); skrypt smoke_test.ps1 z listą KB (KB2533623, KB2999226/UCRT, KB3140245 niepotrzebny — OpenSSL CPython) |
| RR2 | Bootloader PyInstaller 6.x odmówi startu na Win7 (oficjalnie Win8+) | niskie (F7: Win7 feature level) | krytyczny | M0 buduje minimalne exe "Hello Qt"; fallback: `pyinstaller==5.13.2` + Track B |
| RR3 | Qt 5.15.2 (MSVC2019 runtime) wymaga VC++ redist nieobecnego na Win7 | niskie (wheel bundluje CRT; Win7 SP1 wspiera MSVC2019 runtime) | wysoki | M0 weryfikuje `msvcp140.dll`/`vcruntime140.dll` w dist; jeśli brak → dołączamy z redist (legalne) do bundle |
| RR4 | MAL zaostrzy throttling / zmieni API beta | śr | średni | cache-first, stale-if-error, AniList failover, taksonomia błędów z 403-HTML (F13), warstwa provider izoluje zmiany |
| RR5 | Jikan wyłączenie (01.10.2026) kusi do obejścia | — | — | wykluczony architektonicznie (F11) |
| RR6 | Lista >300 pozycji → koszt `setItemWidget` | śr | średni | ListBackend + gate G3 → DelegateListBackend (Biblia §43) |
| RR7 | RSS przekroczy 250 MB (pixmapy) | niskie | średni | bounded LRU, dekodowanie skalowane, gate G4 |
| RR8 | AV/SmartScreen oflaguje onefile | wysokie | niski | onedir jako rekomendowany (D2), SHA256SUMS, podpis kodu (opcja płatna — poza v1) |
| RR9 | Zmiany w repo Python-Win7 (master się przesuwa) | niskie | wysoki | pin commit SHA + SHA256 w `python-win7.json` (CI nie ufa HEAD) |
| RR10 | Utrata danych przy migracji schematu | niskie | wysoki | VACUUM INTO przed migracją, retencja 3 backupów, ścieżka corrupt-recovery (§4.4) |

---

# §14. PLAN IMPLEMENTACJI (M0–M8)

| Kamień | Zawartość | Kryteria akceptacji | Szacunek |
|---|---|---|---|
| **M0 — Walidacja platformy** (BEZ kodu produktowego) | Na fizycznym E5500: instalacja Python-Win7 3.13.5; `pip install` pinów §2.4; minimalne okno Qt (QLabel); freeze `pyinstaller==6.11.1` hello-world (onedir+onefile); uruchomienie obu exe; pomiar startu/RSS; smoke_test.ps1 + lista KB | Gate G1: oba exe startują i renderują okno; raport pomiarów w docs/ | 0,5–1 dni |
| **M1 — Szkielet + rdzeń danych** | Struktura §3.4; core (config/paths/logging/dotenv_lite); domain models (+Universe); connection+migrations+repository (+UniverseRepository)+api_cache; **services/watch_order (§4.9)**; api: rate_limiter/retry/circuit_breaker; testy unit (sqlite :memory:) | 100% operacji CRUD w testach; migracja v0→v1 + backup działa; watch_order: testy topo-sort/heurystyka EN+CN/override/cykle; ruff czysty | 2–3 dni |
| **M2 — GUI statyczne** | MainWindow/Sidebar/DashboardWidget/DonghuaRow/SkeletonRow/theme QSS/SnackBar (bez logiki); ikony PNG (export_icons.py) | Zrzuty zgodne z Biblią (§1–§6, §29–§40); selftest buduje 300 wierszy; zero efektów (§6.4.1) | 2–3 dni |
| **M3 — Sterowanie + DB w tle** | DbWorker (koalescencja, ack/nack), DashboardController: load async, filtr/sort/search lokalny, optymistyczny `+1/−1`, auto-complete, Undo, rollback po błędzie | Gate G2; testy GUI: race request_id, rollback, deleteLater; Biblia §8–§10 spełniona | 2–3 dni |
| **M4 — Warstwa API** | rate_limiter/retry/circuit_breaker/mal_client/anilist_client/metadata_service + NetworkWorker; AddDialog (search page, stany, debounce, skeleton, quick add, duplikaty); **related_anime + UniverseService → auto-sugestie uniwersów (§5.6)** | testy na fixtures (nagrania live, w tym mal_related_37176.json); live-smoke opt-in przechodzi na produkcji MAL; 429 symulowany → backoff wg specyfikacji; sugestia uniwersum nie opóźnia Quick Add | 3–4 dni |
| **M5 — Okładki + Advanced + Uniwersa UI** | CoverStore, kolejka priorytetowa, placeholder; AdvancedPage (statusy, spinbox, streaming links, **pole Universum**); failover AniList e2e; **grupowanie uniwersów na dashboardzie (§6.7): UniverseHeaderRow, collapse, watch-order w widoku, override'y ręczne** | okładki nie blokują renderu (test GUI); dodanie z linkami zapisuje transakcyjnie; franczyza Doupo (S1,S2,S3+specjały) wyświetla się w kolejności oglądania; budżet G3 trzymany z nagłówkami grup | 2–3 dni |
| **M6 — Freezing + CI/CD** | spec §8.2, version_info, workflows §9, python-win7.json, artefakty + SHA256SUMS, release z taga | zielony release.yml: 4 artefakty; onedir ZIP startuje na Win10 runnera i (manualnie) na E5500 | 1–2 dni |
| **M7 — Tuning na E5500** | pomiary selftest na fizycznej maszynie; gate'y G3/G4/G5; ewentualny DelegateListBackend; profilowanie startu (lazy importy); QA macierz §10.1 | wszystkie budżety §1.3/§7 spełnione na docelowym sprzęcie; raport w docs/ | 2–3 dni |
| **M8 — Dokumentacja + v1.0** | README §11, ADR-y, tag v1.0.0, release | README przechodzi test "świeży użytkownik instaluje bez pytania" | 1 dzień |

Kolejność M0 przed wszystkim jest **twarda** — cała reszta planu zakłada wynik G1 (Track A lub B).

---

# §15. DECYZJE — ROZSTRZYGNIĘTE (zatwierdzone przez Właściciela 2026-09-26)

| # | Pytanie | Decyzja Właściciela | Implementacja w specyfikacji/kodzie |
|---|---|---|---|
| D1 | Bitowość Windows 7 na E5500? | **x64 jako standard bazowy**; 32-bit "i tak będzie działać" dla innych użytkowników | Artefakt główny: `amd64`; matrix CI buduje też `win32` (zero dodatkowego kosztu, większy zasięg) |
| D2 | Artefakt główny: onedir vs onefile? | **"onedir ZIP jako rekomendowany, onefile jako portable — idealne wyjście"** | §8.1 bez zmian; release.yml produkuje oba; README prezentuje ZIP jako rekomendowany |
| D3 | Synchronizacja z kontem MAL (OAuth2) w v1? | **NIE — "to ma być lokalny tracking"** | v1 = 100% lokalna baza; endpointy `@me` poza zakresem; architektura providerów zostawia miejsce na moduł `sync/` w v2 |
| D4 | Jaki Python działa na maszynie docelowej? | **Potwierdzone: Python-Win7 (Alex313031) 3.13.5**, pip 25.1.1, PyQt5 5.15.11 — dowód: output konsoli Właściciela; baseline składniowy §16 zaakceptowany | Track A uprawomocniony; M0 zredukowany do testu freeze/launch (RR1 obniżone do "niskie") |
| D5 | Rotacja ujawnionego Client Secret | **"po zakończeniu pracy dostęp zostanie zamknięty i stworzony nowy"** | Do dnia rotacji sekrety traktowane jako skompromitowane: w testach live używany wyłącznie Client ID, secret nieużywany (F9); po rotacji nowa wartość wyłącznie w lokalnym `.env` / GH Secrets |
| D6 | Licencja | **MIT** ("chcę się tym dzielić"); świadomość GPLv3 PyQt5 ("nie mamy innej opcji") | `LICENSE` MIT + §12.3 (notka o GPLv3 binariów w README i About) |
| D7 | Nazwa programu/repo + branding | **Delegowane na architekta**; grafikę "możesz wygenerować w pythonie"; GitHub: `karnyjohnny` | Nazwa: **DongStack** (wolna — F16); repo `github.com/karnyjohnny/dongstack`; exe `DongStack.exe`; ikony/logo generowane skryptem `tools/generate_branding.py` (Pillow, dev-only) |
| D8 | `pip --require-hashes`? | **"tak dla release.yml, nie dla dev"** | `tools/freeze_hashes.py` → `requirements.lock.txt` (hash-e kół win_amd64+win32 dla cp313); release.yml instaluje runtime z locka; dev/CI-test bez hashowania |

### Nowe wymagania produktowe dodane przy zatwierdzeniu (v1.1)

- **UNIWERSA**: łączenie serii w prequel/sequel i wyświetlanie na dashboardzie od 1. sezonu do ostatniego, potem filmy i specjały (§4.9, §5.6, §6.7). Motywacja Właściciela: obecny program gubi kolejność sezonów ("mam s2, s5, s1, s7 — a każdy lubi porządek").
- API służy **wyłącznie szybkiemu dodawaniu serii bez ręcznego wypełniania pól** (quick add z wyniku wyszukiwania) + pobieraniu okładek do cache — potwierdzone jako zgodne z projektem §5–§6.
- Preferencja providera: **MAL** (lepiej zorganizowane donghua), AniList jako plan awaryjny — zgodne z §5.0.

---

# §16. STANDARDY KODOWANIA

1. **Baseline składniowy: Python 3.8** — mimo runtime 3.13.5. Powód: utrzymuje Track B (§2.2) przy zerowym koszcie oraz spełnia rygor zadania dot. funkcji języka. ZAKAZ: `match/case`, `list[str]`/`dict[str,int]`/`X | None` w anotacjach, `tomllib`, `zoneinfo` (używamy UTC + strftime), operatora `:=` używamy oszczędnie (dozwolony — 3.8). NAKAZ: `typing.List/Dict/Optional/Tuple`, `from __future__ import annotations` (3.7+) w każdym module dla spójności. Ruff `target-version = "py38"` egzekwuje automatycznie (reguły UP006/UP007/UP035 wyłączone).
2. **Dozwolone z nowości (działają w 3.8):** dataclasses (frozen dla modeli domenowych), `typing.Protocol`, f-strings, `contextlib`, `enum` (w tym `(str, Enum)`), `functools.lru_cache` (z `maxsize` — pamięć!), `time.monotonic`.
3. Styl: ruff format (odpowiednik black, line-length 100), docstringi w modułach publicznych, komentarze PO POLSKU dozwolone tam, gdzie wyjaśniają "dlaczego" (kod i identyfikatory — angielski).
4. Typowanie: anotacje wszystkich funkcji publicznych; `mypy` jako opcjonalny gate (nie blokujący w v1 — decyzja po M3).
5. Zakaz mutowania obiektów domenowych po emisji sygnałem (frozen dataclass + `dataclasses.replace`).
6. Importy Qt: tylko potrzebne symbole (`from PyQt5.QtCore import ...`) — mniejszy ślad w Analysis.
7. Każdy moduł ≤ ~400 linii; każdy plik GUI ma odpowiadający plik testu.
8. Commit convention: Conventional Commits (`feat:`, `fix:`, `perf:`, `build:`) → changelog release'ów generowany przez `generate_release_notes`.

---

# §17. ŹRÓDŁA I DZIENNIK TESTÓW LIVE

## 17.1. Źródła zewnętrzne (dostęp 2026-09-26)

1. Python Releases for Windows — python.org/downloads/windows (F1: "Python 3.13 cannot be used on Windows 7 or earlier")
2. endoflife.date/python — "Python 3.8 was the last version to support Windows 7"
3. Alex313031/Python-Win7 (GitHub) — nieoficjalne buildy CPython dla Win7 SP1 / Server 2008 R2 (F2)
4. Qt 5.15 Supported Platforms — qthub.com/static/doc/qt5/qtdoc/supported-platforms.html (F5: Windows 7 x86/x64)
5. PyInstaller (GitHub README) — "should work on Windows 7 or newer, but we only officially support Windows 8+" (F7)
6. PyInstaller CHANGES v6.11.0 — bootloader "request Windows 7 feature level for Windows headers" (F7)
7. PyInstaller Requirements (stable docs) — build host: Windows 8+ (F8)
8. MyAnimeList API (beta) v2 — myanimelist.net/apiconfig/references/api/v2 (X-MAL-CLIENT-ID)
9. Forum MAL: "429 (Too Many Requests) from API" (topicid=1547561); "Throttling" (topicid=1991772) (F13)
10. jikan-rest issue #610 — "Jikan public API will be discontinued on October 1, 2026" (F11)
11. docs.anilist.co/guide/rate-limiting — 30 req/min (degraded; docelowo 90), 429+Retry-After+X-RateLimit-* (F12)
12. PyPI JSON API — weryfikacja kół/pinów: PyQt5, PyQt5-Qt5, PyQt5-sip, PyInstaller, requests, urllib3, certifi, charset-normalizer, idna, pytest, pytest-qt, responses, ruff, pyinstaller-hooks-contrib (F3, F4, F6, F14)

## 17.2. Dziennik testów live API (2026-09-26, sandbox)

```text
[1] GET https://api.myanimelist.net/v2/anime?q=ling long&limit=2&fields=…
    header: X-MAL-CLIENT-ID: c13fe…e8e1 (zamaskowany)      → HTTP 200, 0.45 s, 861 B
[2] GET https://api.myanimelist.net/v2/anime/37347?fields=… → HTTP 200, 0.25 s, 2366 B
[3] GET https://api.myanimelist.net/v2/anime?q=doupo cangqiong&limit=3 → HTTP 200, 0.31 s
[4] GET …/anime?q=斗争苍穹(native)&limit=2&fields=…          → HTTP 200 (schemat §5.1: data[].node + paging.next)
[5] GET …/anime/ranking?ranking_type=airing&limit=1          → HTTP 200, 384 B
[6] GET …/anime?q=naruto&limit=500                           → HTTP 200, 34 nodes (przycięcie — patrz F10)
[7] GET …/anime?q=naruto&limit=1500                          → HTTP 400 {"message":"limit","error":"bad_request"}
[8] POST https://graphql.anilist.co (search "Battle Through the Heavens", CN) → HTTP 200
[9] POST https://graphql.anilist.co (search "Doupo Cangqiong") → HTTP 200, media: [] (uwaga §5.2: exact-phrase)
--- sesja 2 (2026-09-26, po zatwierdzeniu D1–D8) ---
[10] GET …/anime/37176?fields=id,title,related_anime,media_type,start_date → HTTP 200:
     prequel→36491 (S1), sequel→38436 (S3), side_story→36561, side_story→39178, prequel→51038 (Yuanqi)
     = dowód F15; nagranie: tests/fixtures/mal_related_37176.json
[11] GET …/anime?q=fanren xiu xian&limit=3 → HTTP 200 (sezony/arki jednej franczyzy rozrzucone po id — potwierdzenie potrzeby watch_order)
[12] FIXTURES: nagrane mal_search.json, mal_related_37176.json, mal_400_limit.json (HTTP 400), anilist_page.json (HTTP 200) → tests/fixtures/
[13] Kontrola kolizji nazwy "dongstack": GitHub Search total_count=0, PyPI 404 → nazwa wolna (F16)
Użycie łącznie: 15 żądań API w dwóch sesjach, odstępy ≥1.2 s (zgodne z projektowanym limitem 1 req/s). Client Secret nie był użyty w żadnym żądaniu.
```

## 17.3. Checksumy zweryfikowanych installerów Python-Win7

Patrz `packaging/python-win7.json` (§9.2) — obliczone z pobranych plików, commit `2aba455bcf205d0f12fc55aa59adc352196d46c2`.

---

# ZAŁĄCZNIK A — ODRZUCONE ALTERNATYWY (decision log)

| Alternatywa | Werdykt | Powód |
|---|---|---|
| Qt6/PySide6 | ODRZUCONE | Qt 6 wymaga Windows 10+ — koniec dyskusji na Win7 |
| Qt Quick/QML (nawet w Qt5) | ODRZUCONE | scenegraf OpenGL/GPU — GMA 4500MHD; Widgets+raster to jedyna stabilna droga |
| Flet/Flutter-webview | ODRZUCONE | dokument wejściowy już migrował z Flet; webview = RAM+CPU poza budżetem |
| httpx | ODRZUCONE | httpx+httpcore+h11+anyio+sniffio = 5 dodatkowych zależności dla funkcji (async/HTTP2), których architektura (1 wątek sieciowy, serializacja) nie używa; requests wystarcza i jest lżejszy w freeze |
| Jikan API | ODRZUCONE | wyłączenie publiczne 01.10.2026 (F11); brak auth; niestabilność |
| SQLAlchemy / peewee | ODRZUCONE | +5–10 MB w exe, warstwa niepotrzebna dla 5 tabel; stdlib sqlite3 + cienki Repository spełnia rygor 12 |
| asyncio + aiohttp | ODRZUCONE | pętla zdarzeń w workerze QThread = złożoność bez zysku przy ≤1 req/s; kolejka + token bucket rozwiązuje throttling prościej |
| python-dotenv | ODRZUCONE | parser .env to ~25 linii bez zależności (dotenv_lite) |
| PyInstaller onefile jako JEDYNY artefakt | ODRZUCONE (częściowo) | ekstrakcja ~150 MB na HDD przy każdym starcie zabija "demoniczną szybkość" na E5500; onefile pozostaje wariantem portable |
| Nuitka | ODRZUCONE w v1 | ciekawa alternatywa (C-compilation), ale: dłuższy build w CI, mniej dojrzałe hooki PyQt5, wymóg MSVC na Win7-buildzie; zostaje jako eksperyment po v1 |
| UPX | ODRZUCONE | uszkodzenia DLL Qt, fałszywe alarmy AV, koszt dekompresji CPU na C2D |

# ZAŁĄCZNIK B — ZAREJESTROWANE SCHEMATY ODPOWIEDZI (fragmenty live)

```jsonc
// MAL GET /v2/anime?q=…&limit=2&fields=id,title,num_episodes,mean,main_picture,media_type,start_date,status
{
  "data": [
    { "node": {
        "id": 37176,
        "title": "Doupo Cangqiong 2nd Season",
        "main_picture": {
          "medium": "https://cdn.myanimelist.net/images/anime/1283/90230.jpg",
          "large":  "https://cdn.myanimelist.net/images/anime/1283/90230l.jpg"
        },
        "num_episodes": 12,
        "mean": 7.65,
        "media_type": "ona",
        "start_date": "2018-03-03",
        "status": "finished_airing"
    }}
  ],
  "paging": { "next": "https://api.myanimelist.net/v2/anime?offset=2&q=…&limit=2&fields=…" }
}

// MAL błąd walidacji (limit=1500):  {"message":"limit","error":"bad_request"}   (HTTP 400)

// AniList POST graphql.anilist.co → {"data":{"Page":{"media":[ … ]}}}
// (uwaga: search bywa exact-phrase — pusty wynik ≠ błąd; patrz §5.2)
```

Te nagrania (w pełnej wersji) trafiają do `tests/fixtures/` jako podstawa testów offline (§10.2).

---

*KONIEC DOKUMENTU — v1.1, ZATWIERDZONA do implementacji (§15). Następny krok: M0/M1 → kod modułów.*
