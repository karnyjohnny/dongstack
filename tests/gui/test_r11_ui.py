"""Testy GUI r11 (feedback produkcyjny v1.2.1 → v1.3.0).

1. BUG: `total_episodes = 0` (MAL/AniList: „??”, sezon jeszcze nie wyszedł)
   blokował spinboksa odcinka (max=0) → nie dało się wpisać postępu, a edycja
   pokazywała 0 mimo realnego stanu w bazie („w dashboard rośnie, w edycji 0”).
2. FIX: AdvancedPage w QScrollArea — +10 linków nie wypycha okna poza ekran
   (E5500: 1366×768), pasek akcji przypięty na dole.
3. QoL: tytuł alternatywny pod nazwą (karta + nagłówek edycji) i notatka własna.
4. QoL: Ustawienia → Uniwersa (liczba sezonów + bezpieczne usuwanie z Undo).
"""

from __future__ import annotations

import os

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QApplication, QScrollArea, QStyle, QStyleOptionViewItem

from app.controllers.dashboard_controller import DashboardController
from app.domain.models import Donghua, MediaType, SearchItem, Status, Universe
from app.gui.add.add_dialog import AddDialog
from app.gui.add.advanced_page import EPISODE_OPEN_CEILING
from app.gui.dashboard.delegate_backend import DelegateListBackend
from app.gui.dashboard.donghua_row import DonghuaRow
from app.gui.settings_dialog import SettingsDialog

_ALT_RGB = (0x8A, 0x8A, 0x8A)  # QLabel#altLabel / _C_ALT w delegacie


def _item(total=0, alt="Soul Land") -> SearchItem:
    return SearchItem(
        provider="mal",
        ext_id=1,
        mal_id=1,
        title="Douluo Dalu",
        title_alt=alt,
        total_episodes=total,
        year=2018,
        media_type=MediaType.ONA,
    )


def _donghua(**kw) -> Donghua:
    base = dict(
        id=5,
        mal_id=7,
        provider="mal",
        title="Douluo Dalu",
        title_alt="Soul Land",
        total_episodes=0,
        current_episode=0,
        status=Status.WATCHING,
    )
    base.update(kw)
    return Donghua(**base)


def _advanced(qapp, **kw) -> AddDialog:
    dlg = AddDialog()
    dlg.set_universes({})
    dlg.open_advanced(_item(**kw))
    dlg.show()  # isVisible() ma sens tylko na widocznym drzewie widgetów
    qapp.processEvents()
    return dlg


# ------------------------------------------------- BUG: nieznana liczba odcinków
def test_episode_editable_when_total_unknown(qapp):
    dlg = _advanced(qapp, total=0)
    page = dlg.advanced_page
    assert page._total.value() == 0
    assert page._total.specialValueText() == "—"  # spójnie z dashboardem („—”)
    assert page._episode.maximum() == EPISODE_OPEN_CEILING
    page._episode.setValue(12)
    form = page.form()
    assert form["episode"] == 12  # przed fixem: clamp do 0
    assert form["total"] == 0
    dlg.close()


def test_edit_dialog_shows_stored_progress_when_total_unknown(qapp):
    """Dokładny scenariusz z feedbacku: dashboard pokazuje 3, edycja pokazywała 0."""
    dlg = AddDialog()
    dlg.set_universes({})
    dlg.open_advanced_edit(_donghua(total_episodes=0, current_episode=3), [])
    qapp.processEvents()
    page = dlg.advanced_page
    assert page._episode.value() == 3
    assert page.form()["episode"] == 3
    dlg.close()


def test_known_total_still_caps_episode(qapp):
    dlg = _advanced(qapp, total=12)
    page = dlg.advanced_page
    assert page._episode.maximum() == 12
    page._episode.setValue(12)
    page._total.setValue(5)  # user zmniejsza liczbę odcinków → progres przycięty
    assert page._episode.value() == 5
    page._total.setValue(0)  # powrót do „nieznane” = odblokowany sufit
    assert page._episode.maximum() == EPISODE_OPEN_CEILING
    assert page._episode.value() == 5
    assert page.form()["episode"] == 5
    dlg.close()


def test_manual_mode_allows_progress_without_total(qapp):
    dlg = AddDialog()
    dlg.set_universes({})
    dlg.open_manual()
    qapp.processEvents()
    page = dlg.advanced_page
    page._m_title.setText("Xiuluo Wushen 3")
    page._episode.setValue(40)
    form = page.form()
    assert form["manual"] is True
    assert form["episode"] == 40 and form["total"] == 0
    dlg.close()


# ------------------------------------------------------------------- QoL: alt + nota
def test_alt_title_in_advanced_header(qapp):
    dlg = _advanced(qapp, alt="Soul Land / 斗罗大陆")
    page = dlg.advanced_page
    assert page._alt_title.text() == "Soul Land / 斗罗大陆"
    assert page._alt_title.isVisible() is True
    dlg.close()


def test_alt_title_hidden_when_absent(qapp):
    dlg = _advanced(qapp, alt=None)
    assert dlg.advanced_page._alt_title.isVisible() is False
    dlg.close()


def test_manual_edit_uses_editable_alt_field_instead_of_label(qapp):
    dlg = AddDialog()
    dlg.set_universes({})
    dlg.open_advanced_edit(_donghua(provider="manual", mal_id=None, title_alt="Alt"), [])
    qapp.processEvents()
    page = dlg.advanced_page
    assert page.manual_mode() is True
    assert page._m_title_alt.text() == "Alt"
    assert page._alt_title.isVisible() is False  # bez duplikatu
    dlg.close()


def test_note_roundtrip(qapp):
    dlg = AddDialog()
    dlg.set_universes({})
    dlg.open_advanced_edit(_donghua(note="na CDA numeracja = 52 + odc. sezonu"), [])
    qapp.processEvents()
    page = dlg.advanced_page
    assert page.note_text() == "na CDA numeracja = 52 + odc. sezonu"
    page._note.setPlainText("  S2 startuje od 28  ")
    assert page.form()["note"] == "S2 startuje od 28"  # trim, bez zmiany reszty
    dlg.close()


def test_note_empty_is_none(qapp):
    dlg = _advanced(qapp)
    dlg.advanced_page._note.setPlainText("   \n ")
    assert dlg.advanced_page.form()["note"] is None
    dlg.close()


def test_note_field_sits_above_streaming_links(qapp):
    dlg = _advanced(qapp)
    page = dlg.advanced_page
    inner = page._scroll.widget()
    order = [inner.layout().itemAt(i) for i in range(inner.layout().count())]
    widgets = [it.widget() for it in order if it.widget() is not None]
    assert page._note in widgets and page.links in widgets
    assert widgets.index(page._note) < widgets.index(page.links)
    dlg.close()


# ----------------------------------------------------------------- FIX: przewijanie
def test_form_scrolls_and_dialog_stays_on_small_screen(qapp):
    dlg = _advanced(qapp)
    page = dlg.advanced_page
    assert isinstance(page._scroll, QScrollArea)
    for i in range(12):  # scenariusz z feedbacku: „+10 linków i okno ucieka”
        page.links.add_row(tag="CDA", url="https://cda.pl/video/x%d" % i)
    dlg.show()
    qapp.processEvents()
    assert len(page.links.get_links()) == 12
    # okno NIE rośnie z liczbą linków (E5500: 768 px wysokości ekranu)
    assert dlg.minimumSizeHint().height() < 700
    assert dlg.height() <= 700
    # treść jest wyższa niż okno ⇒ to scroll przejmuje nadmiar
    assert page._scroll.widget().sizeHint().height() > page._scroll.height()
    # pasek akcji poza scrollem: Zapisz zawsze widoczny
    assert page._save.parent() is page
    assert page._save.isVisible() is True
    dlg.close()


def test_paste_in_note_field_does_not_add_link(qapp):
    dlg = _advanced(qapp)
    dlg.show()
    qapp.processEvents()
    qapp.clipboard().setText("https://cda.pl/video/abc123")
    page = dlg.advanced_page
    page._note.setFocus()
    qapp.processEvents()
    assert QApplication.focusWidget() is page._note
    dlg._on_paste_url()  # Ctrl+V w notatce = zwykłe wklejenie, nie nowy wiersz linku
    assert page.links.get_links() == []
    page._universe.setFocus()  # kontrola: focus poza polem tekstowym → link wchodzi
    qapp.processEvents()
    dlg._on_paste_url()
    assert len(page.links.get_links()) == 1
    dlg.close()


# ------------------------------------------------------------------- QoL: karta
def test_row_shows_alt_title_and_note_tooltip(qapp):
    row = DonghuaRow()
    row.resize(600, 96)
    row.show()
    qapp.processEvents()
    row.set_donghua(_donghua(title_alt="Soul Land II", note="na CDA 52+x", current_episode=3))
    qapp.processEvents()
    assert row._alt.isVisible() is True
    assert row._full_alt == "Soul Land II"  # r13: pełny tekst niezależnie od elide
    assert row._alt.text().startswith("Soul Land")
    assert row.toolTip() == "Notatka: na CDA 52+x"
    assert row._episode.text() == "3/—"  # nieznany total → „—” (jak dotąd)
    # bez alta: wiersz zwinięty (brak pustej linii)
    row.set_donghua(_donghua(title_alt=None, note=None))
    qapp.processEvents()
    assert row._alt.isVisible() is False
    assert row.toolTip() == ""
    assert row.height() == 96  # stała wysokość karty (gate G3 / uniformItemSizes)
    row.hide()


def test_long_alt_title_elides_from_real_width_not_stale(qapp, require_real_fonts):
    """Regresja r13 (CI windows-2022): stary `_set_alt` elide'ował TEKST PRZED
    show() — szerokością ukrytej etykiety (domyślne 100 px), a nie realną
    kolumną (~350 px). Z szerszymi metrykami (Windows offscreen bez fontów =
    fallback „box” ~1 em/znak) alt zostawał trwale obcięty ('Soul Lan…'), bo
    resizeEvent przy niezmienionej geometrii nie zachodzi. Po fixie: pełny
    tekst → show() → synchroniczny layout → elide z realnej szerokości."""
    long_alt = "Soul Land II: Legend of the Divine Realm Saga"  # ~225 px w 10 px
    row = DonghuaRow()
    row.resize(600, 96)
    row.show()
    qapp.processEvents()
    row.set_donghua(_donghua(title_alt=long_alt))
    qapp.processEvents()
    assert row._full_alt == long_alt
    assert row.width() == 600  # diagnostyka: offscreen nie może zwinąć wiersza
    assert row._alt.width() > 200  # realna kolumna, nie stale 100 px
    # mieści się → bez elide (mutacja: stara kolejność cięłaby przy 100 px)
    assert row._alt.text() == long_alt
    row.hide()


def _paint_card(qapp, d: Donghua) -> QImage:
    backend = DelegateListBackend()
    backend.set_items([d])
    qapp.processEvents()
    img = QImage(600, 96, QImage.Format_ARGB32)
    img.fill(QColor("#123456"))
    painter = QPainter(img)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 600, 96)
    opt.widget = backend.widget()
    opt.state = QStyle.State_Enabled
    backend._delegate.paint(painter, opt, backend.model.index(0, 0))
    painter.end()
    return img


def _ink(img: QImage, rect: QRect) -> tuple:
    """(liczba_pikseli, średnia_jasność) neutralnego tekstu w prostokącie.

    Neutralne = r==g==b: tytuł (#E6E1E5) odpada, zostają alt (#8A8A8A) i meta
    (#A0A0A0) — czyli dokładnie te dwie linie, które test rozróżnia.
    """
    values = []
    for y in range(max(0, rect.top()), min(img.height(), rect.bottom() + 1)):
        for x in range(max(0, rect.left()), min(img.width(), rect.right() + 1)):
            c = img.pixelColor(x, y)
            if c.red() == c.green() == c.blue() and 90 <= c.red() <= 200:
                values.append(c.red())
    if not values:
        return (0, None)
    return (len(values), sum(values) / float(len(values)))


def test_card_text_rects_reserve_alt_line():
    from app.gui.dashboard.delegate_backend import card_text_rects

    rect = QRect(0, 3, 600, 90)
    with_alt = card_text_rects(rect, 81, 400, True)
    without = card_text_rects(rect, 81, 400, False)
    assert with_alt["alt"] is not None and without["alt"] is None
    assert with_alt["meta"].top() == with_alt["alt"].bottom() + 1
    # z altem meta zjeżdża w dół — inaczej linie nachodziłyby na siebie
    assert with_alt["meta"].top() > without["meta"].top()
    assert with_alt["bar"] == without["bar"]  # pasek postępu zawsze przy dole karty
    assert with_alt["bar"].bottom() <= rect.bottom()


def test_delegate_paints_alt_line_and_pushes_meta_down(qapp, require_real_fonts):
    from app.gui.dashboard.delegate_backend import card_text_rects

    rects = card_text_rects(QRect(0, 3, 600, 90), 81, 480, True)
    img_with = _paint_card(qapp, _donghua(title_alt="Soul Land II"))
    img_without = _paint_card(qapp, _donghua(title_alt=None))

    alt_band, meta_band = rects["alt"], rects["meta"]
    n_alt, mean_alt = _ink(img_with, alt_band)
    n_meta, mean_meta = _ink(img_with, meta_band)
    assert n_alt > 20 and n_meta > 20, "karta z altem musi mieć obie linie"
    assert mean_alt < mean_meta, "alt-tytuł jest ciemniejszy (mniej ważny) niż meta"

    # bez alta: dolny pas pusty (meta wskoczyła na miejsce alta), a w „pasie alta”
    # siedzi dokładnie meta — dowód, że nie malujemy pustej linii
    assert _ink(img_without, meta_band)[0] == 0
    n_up, mean_up = _ink(img_without, alt_band)
    assert n_up > 20
    assert abs(mean_up - mean_meta) < 2.0


# ------------------------------------------------------------- QoL: Ustawienia
def test_settings_dialog_universes_tab(qapp):
    dlg = SettingsDialog(
        client_id="cid",
        universes=[(Universe(id=7, name="Douluo Dalu"), 2), (Universe(id=8, name="Solo"), 0)],
        tab=1,
    )
    dlg.show()
    qapp.processEvents()
    assert dlg._tabs.currentIndex() == 1
    assert dlg._tree.topLevelItemCount() == 2
    assert dlg._tree.topLevelItem(0).text(0) == "Douluo Dalu"
    assert dlg._tree.topLevelItem(0).text(1) == "2"  # liczba sezonów w uniwersum
    assert dlg._delete_universe.isEnabled() is False

    deleted, undone = [], []
    dlg.deleteUniverseRequested.connect(deleted.append)
    dlg.undoRequested.connect(lambda: undone.append(True))

    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    assert dlg._delete_universe.isEnabled() is True
    dlg._on_delete_universe()
    assert deleted == [7]
    assert dlg._tree.topLevelItemCount() == 1  # widok reaguje od razu (Biblia §9)
    assert dlg._undo.isVisible() is True
    assert "Douluo Dalu" in dlg._status.text()

    dlg._on_undo()
    assert undone == [True]
    assert dlg._undo.isVisible() is False
    dlg.close()


def test_settings_dialog_universes_empty_state(qapp):
    dlg = SettingsDialog(universes=[(Universe(id=9, name="Jedyne"), 1)], tab=1)
    dlg.show()
    qapp.processEvents()
    assert dlg._empty_universes.isVisible() is False
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    dlg._on_delete_universe()
    assert dlg._empty_universes.isVisible() is True
    dlg.close()


def test_settings_dialog_refresh_updates_counts(qapp):
    dlg = SettingsDialog(universes=[(Universe(id=7, name="Douluo Dalu"), 2)], tab=1)
    dlg.set_universes([(Universe(id=42, name="Douluo Dalu"), 2)])  # Undo = nowe id
    qapp.processEvents()
    assert dlg._tree.topLevelItemCount() == 1
    assert dlg._tree.topLevelItem(0).data(0, Qt.UserRole) == 42
    dlg.close()


def test_settings_dialog_client_id_tab(qapp):
    dlg = SettingsDialog(client_id="", tab=0)
    got = []
    dlg.clientIdChanged.connect(got.append)
    dlg._cid.setText("  2342aaac3213esac  ")
    dlg._on_save_client_id()
    assert got == ["2342aaac3213esac"]
    dlg._cid.setText("   ")
    dlg._on_save_client_id()
    assert got == ["2342aaac3213esac"]  # puste pole = brak zapisu
    dlg.close()


# --------------------------------------------------- integracja z DbWorker + SQLite
def test_universe_delete_end_to_end(qapp, tmp_home):
    from app.data import migrations
    from app.data.connection import open_connection
    from app.data.repository import DonghuaRepository, UniverseRepository
    from app.workers.db_worker import DbWorker

    db_path = os.path.join(tmp_home, "e2e.sqlite")
    worker = DbWorker(db_path, os.path.join(tmp_home, "backups"))
    controller = DashboardController(worker=worker)
    try:
        conn = open_connection(db_path)
        migrations.ensure_schema(conn)
        repo, unis = DonghuaRepository(conn), UniverseRepository(conn)
        uid = unis.create("Douluo Dalu", 123)
        for i in range(2):
            repo.insert(
                _donghua(
                    id=0,
                    mal_id=100 + i,
                    title="S%d" % i,
                    universe_id=uid,
                    universe_order=(i + 1) * 10,
                )
            )
        conn.close()

        worker.loadLibrary()
        qapp.processEvents()
        assert controller.universe_counts() == {uid: 2}

        controller.request_delete_universe(uid)
        qapp.processEvents()

        conn = open_connection(db_path)
        repo, unis = DonghuaRepository(conn), UniverseRepository(conn)
        assert unis.list_all() == []
        assert [d.universe_id for d in repo.load_alive()] == [None, None]  # sezony żyją
        conn.close()

        controller.undo_last()  # odtworzenie uniwersum + ponowne przypięcie sezonów
        qapp.processEvents()

        conn = open_connection(db_path)
        repo, unis = DonghuaRepository(conn), UniverseRepository(conn)
        remaining = unis.list_all()
        assert [u.name for u in remaining] == ["Douluo Dalu"]
        new_uid = remaining[0].id
        assert sorted(d.universe_id for d in repo.load_alive()) == [new_uid, new_uid]
        conn.close()
        assert controller.universe_counts() == {new_uid: 2}
    finally:
        worker.shutdown()
