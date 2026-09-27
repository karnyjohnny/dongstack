Fonty WYŁĄCZNIE do testów GUI (patrz ../gui/conftest.py).

Dlaczego: runner CI (windows-2022, QT_QPA_PLATFORM=offscreen) nie ma bazy fontów
systemowych dla Qt — wtyczka offscreen na Windows NIE enumeruje fontów systemowych,
a PyQt5 od 5.15 nie dołącza własnych (logi CI: "QFontDatabase: Cannot find font
directory .../PyQt5/Qt5/lib/fonts"). Qt spada wtedy na fallback "box": puste glify
+ rozdęte metryki (~1 em na znak), co zerowało testy pikselowe/ink i elide
('Soul Lan…' zamiast 'Soul Land II'). DejaVu rasteryzowany przez FreeType daje
identyczne piksele na każdej platformie → testy deterministyczne.

Aplikacja NIE bundle'uje tych fontów (spec §6.4: systemowy Segoe UI).
Licencja: Bitstream Vera (LICENSE-DejaVu.txt).
