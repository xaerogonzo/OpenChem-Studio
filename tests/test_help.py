"""The help system's contract with the documentation.

The whole design rests on the shipped markdown BEING the help, so the way
it breaks is a documentation edit that removes or renames an anchor. That
is silent at run time -- an empty help window -- and these tests are what
make it loud instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from PySide6.QtCore import Qt

from openchem import help as help_docs
from openchem.app.main_window import HELP_TOPIC_BY_CENTRE_TAB, HELP_TOPIC_BY_DOCK

import conftest


@pytest.fixture
def help_widgets():
    """Destroys each MainWindow deterministically; see the docstring on the
    equivalent fixture in tests/test_batch_panel.py for why this matters."""
    built = []
    yield built
    for widget in built:
        widget.close()
        conftest.dispose(widget)

ANCHOR = re.compile(r"<!--\s*help:([a-z0-9-]+)\s*-->")


def test_the_documents_are_found():
    assert help_docs.docs_directory().is_dir()


def test_every_help_document_exists():
    directory = help_docs.docs_directory()
    missing = [name for name in help_docs.HELP_DOCUMENTS if not (directory / name).is_file()]
    assert not missing, f"HELP_DOCUMENTS names files that are not there: {missing}"


def test_topics_are_discovered():
    assert len(help_docs.topics()) >= 15


@pytest.mark.parametrize("key", sorted(HELP_TOPIC_BY_DOCK.values()))
def test_every_panel_topic_resolves(key):
    """A panel pointing at a topic that no longer exists is the failure
    mode this whole file exists for -- F1 would open an empty window."""
    assert help_docs.topic_markdown(key).strip()


@pytest.mark.parametrize("key", sorted(set(HELP_TOPIC_BY_CENTRE_TAB.values())))
def test_every_centre_tab_topic_resolves(key):
    assert help_docs.topic_markdown(key).strip()


def test_every_topic_has_content():
    """No anchor may sit above an empty section.

    An anchor left behind after its prose was moved elsewhere still
    resolves, still appears in the sidebar, and shows a heading with
    nothing under it.
    """
    thin = []
    for topic in help_docs.topics():
        body = help_docs.topic_markdown(topic.key)
        # Everything after the heading line.
        prose = "\n".join(body.splitlines()[1:]).strip()
        if len(prose) < 80:
            thin.append((topic.key, len(prose)))
    assert not thin, f"Help topics with almost no text under the heading: {thin}"


def test_topic_titles_come_from_the_headings():
    """The sidebar label and the page heading cannot disagree."""
    for topic in help_docs.topics():
        first_line = help_docs.topic_markdown(topic.key).splitlines()[0]
        assert first_line.lstrip("#").strip() == topic.title


def test_anchors_are_unique_across_documents():
    seen: dict[str, str] = {}
    duplicates = []
    directory = help_docs.docs_directory()
    for name in help_docs.HELP_DOCUMENTS:
        for key in ANCHOR.findall((directory / name).read_text(encoding="utf-8")):
            if key in seen:
                duplicates.append((key, seen[key], name))
            seen[key] = name
    assert not duplicates, f"The same help key is anchored twice: {duplicates}"


def test_a_section_stops_at_the_next_heading_of_its_own_level():
    """`## Quantum chemistry` must not run on into `## Batch mode`."""
    body = help_docs.topic_markdown("quantum-chemistry")
    assert "## Batch mode" not in body


def test_a_section_carries_its_own_subsections():
    """...but it must still include its `###` children, or per-panel help
    would silently drop half of what the panel does."""
    body = help_docs.topic_markdown("quantum-chemistry")
    assert "IR spectra and normal modes" in body


def test_a_subsection_is_readable_on_its_own():
    body = help_docs.topic_markdown("ir-spectra")
    assert body.startswith("### IR spectra")
    assert "## Batch mode" not in body


def test_anchors_never_reach_the_reader():
    """They are markup for the loader, not content."""
    for topic in help_docs.topics():
        assert "<!-- help:" not in help_docs.topic_markdown(topic.key)
    for document in help_docs.HELP_DOCUMENTS:
        assert "<!-- help:" not in help_docs.document_markdown(document)


def test_an_unknown_key_raises_rather_than_returning_nothing():
    """Returning "" would render as a blank page that looks like a topic
    with no text written yet, rather than a wiring mistake."""
    with pytest.raises(help_docs.HelpUnavailable):
        help_docs.topic_markdown("no-such-topic")


def test_the_help_is_bundled_not_shipped_loose():
    """A release carries the help inside the exe's archive, not as files.

    This used to assert the spec shipped `docs/` as `openchem/docs`. That
    copy is what the Help window's Open file button opened, so a save over
    it broke F1. The spec must no longer ship it, and `build.ps1` must
    generate the module that replaces it -- either half missing gives a
    release with no help, which a checkout cannot show.
    """
    root = help_docs.docs_directory().parent
    spec = (root / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    assert 'str(ROOT / "docs")' not in spec
    assert '"openchem/docs"' not in spec
    build = (root / "build.ps1").read_text(encoding="utf-8")
    assert "build_help_bundle.py" in build
    assert "_help_bundle.py" in build


class TestHelpRouting:
    """F1 must land on the panel the user is actually working in.

    Two wrong implementations came before this one, which is why it is
    tested per panel rather than once. Both were plausible and both were
    silently wrong:

      * "the first visible dock" -- several docks are up at once (Project
        Explorer on the left, Console at the bottom, plus the front
        right-hand tab), so this returned whichever was constructed first.
        Measured: "docking" while the Project Explorer was in front.
      * checking the centre tabs only as a last resort -- the right-hand
        panels are still on screen, so F1 while drawing a structure
        answered "Properties".
    """

    @staticmethod
    def _window(qapp, tmp_path, widgets):
        from openchem.app.main_window import MainWindow
        from openchem.app.session import SessionManager
        from openchem.app.settings import Settings
        from openchem.bootstrap import build_service_container

        services = build_service_container()
        settings = Settings(services.event_bus)
        settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
        settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins"))
        window = MainWindow(services, settings, SessionManager())
        widgets.append(window)
        window.show()
        qapp.processEvents()
        return window

    @pytest.mark.parametrize(("dock_name", "expected"), sorted(HELP_TOPIC_BY_DOCK.items()))
    def test_focus_in_a_panel_selects_that_panels_topic(
        self, qapp, tmp_path, help_widgets, dock_name, expected
    ):
        from PySide6.QtWidgets import QDockWidget

        window = self._window(qapp, tmp_path, help_widgets)
        for dock in window.findChildren(QDockWidget):
            if dock.objectName() == dock_name:
                dock.raise_()
                dock.show()
                dock.widget().setFocus()
        qapp.processEvents()
        assert window._help_topic_for_visible_panel() == expected

    def test_every_dock_the_window_builds_has_a_help_topic(
        self, qapp, tmp_path, help_widgets
    ):
        """The guard that goes the OTHER way.

        Both tests above iterate over `HELP_TOPIC_BY_DOCK`, so a panel
        MISSING from the map is invisible to them -- its `?` button opens
        help with nothing selected and no test notices. The Atom Inspector
        and the Interactions panel both shipped that way and were only
        found by reading the map against the docks by hand.
        """
        from PySide6.QtWidgets import QDockWidget

        window = self._window(qapp, tmp_path, help_widgets)
        docks = {
            dock.objectName()
            for dock in window.findChildren(QDockWidget)
            if dock.objectName()
        }
        assert docks, "no docks found -- the traversal, not the map, is wrong"
        missing = sorted(docks - set(HELP_TOPIC_BY_DOCK))
        assert not missing, f"docks with no help topic: {missing}"

    def test_focus_in_the_editor_beats_a_visible_side_panel(self, qapp, tmp_path, help_widgets):
        window = self._window(qapp, tmp_path, help_widgets)
        window._center_tabs.setCurrentIndex(0)
        window._center_tabs.setFocus()
        qapp.processEvents()
        assert window._help_topic_for_visible_panel() == "centre-tabs"


class TestSearch:
    """Search covers the section BODIES, which is the whole point.

    Title-only filtering answers "what is this feature called" -- the
    question of someone who already knows. "Vina" appears in no heading in
    these documents and in four sections of their text.
    """

    def test_finds_a_word_that_appears_in_no_heading(self):
        """Body text is searched, not only headings.

        **THIS ASSERTED `all(not in_title)` AND THAT STOPPED BEING TRUE.**
        `docs/CALCULATOR_REFERENCE.md` gives every calculator a heading, and
        one of them is "Molecular Docking (Vina)" -- so the word now appears
        in a title as well, which is a better help system rather than a
        regression. What the test is for is that the SEVEN body-only matches
        still come back, so the assertion names that rather than the absence
        of any title match.
        """
        hits = help_docs.search("Vina")
        assert len(hits) >= 3
        body_only = [hit for hit in hits if not hit.in_title]
        assert len(body_only) >= 3, [h.topic.key for h in hits]
        assert {"limits-docking", "external-tools"} <= {
            hit.topic.key for hit in body_only
        }

    def test_a_title_match_outranks_a_busier_body_match(self):
        """Someone typing "docking" wants the Docking section, not
        whichever section happens to mention docking most often."""
        hits = help_docs.search("docking")
        assert hits[0].in_title

    def test_body_hits_are_ranked_by_how_often_the_term_appears(self):
        body_hits = [hit for hit in help_docs.search("Vina") if not hit.in_title]
        counts = [hit.occurrences for hit in body_hits]
        assert counts == sorted(counts, reverse=True)

    def test_multi_word_phrases_work(self):
        hits = help_docs.search("binding free energy")
        assert hits
        assert "limits-docking" in {hit.topic.key for hit in hits}

    def test_search_is_case_insensitive(self):
        assert {h.topic.key for h in help_docs.search("VINA")} == {
            h.topic.key for h in help_docs.search("vina")
        }

    def test_every_hit_carries_a_snippet(self):
        for hit in help_docs.search("conformer"):
            assert hit.snippet.strip()
            assert len(hit.snippet) <= 120

    @pytest.mark.parametrize("query", ["", "   ", "qqqqzzzz"])
    def test_no_matches_returns_empty_rather_than_everything(self, query):
        assert help_docs.search(query) == ()

    def test_every_search_row_names_its_document(self, qapp, help_widgets):
        """Two documents have a section called "Docking", and search
        results have no group headers to tell them apart.

        Asserted as "every row carries its document tag" rather than "the
        labels are all distinct". Distinctness passes by accident:
        stripping the tag leaves `Docking` and `Docking  (1)`, which
        differ only by an occurrence count and tell the reader nothing
        about which document they are about. Mutation testing caught that
        -- removing the tag entirely failed no test.
        """
        from openchem.ui.dialogs.help_dialog import HelpDialog
        from openchem.ui.dialogs.help_dialog import _DOCUMENT_TAGS

        dialog = HelpDialog()
        help_widgets.append(dialog)
        dialog._filter.setText("Vina")
        assert dialog._list.count() >= 2
        for row in range(dialog._list.count()):
            item = dialog._list.item(row)
            expected = _DOCUMENT_TAGS[help_docs.topic(item.data(Qt.ItemDataRole.UserRole)).document]
            assert expected in item.text(), f"Row {item.text()!r} does not say which document it is from"

    def test_matches_are_highlighted_in_the_rendered_page(self, qapp, help_widgets):
        """A result opens at the top of a section that may be several
        screens long; finding the word again is most of the work the
        search was asked to do."""
        from openchem.ui.dialogs.help_dialog import HelpDialog

        dialog = HelpDialog()
        help_widgets.append(dialog)
        dialog._filter.setText("Vina")
        assert len(dialog._view.extraSelections()) >= 1

    def test_clearing_the_search_restores_the_table_of_contents(self, qapp, help_widgets):
        from openchem.ui.dialogs.help_dialog import HelpDialog

        dialog = HelpDialog()
        help_widgets.append(dialog)
        browse_rows = dialog._list.count()
        dialog._filter.setText("Vina")
        assert dialog._list.count() < browse_rows
        dialog._filter.setText("")
        assert dialog._list.count() == browse_rows
        assert dialog._view.extraSelections() == []


class TestHelpWindowBehaviour:
    """What a person reading a long document in the help window runs into.

    Each case is a defect reported from using the window, in the order it was reported: clearing a
    search threw the reader back to the top, the window could not be maximised, and "Read the whole
    document" did nothing on the page that already is the whole document.
    """

    @staticmethod
    def _open(qapp, help_widgets, topic_key=""):
        from openchem.ui.dialogs.help_dialog import HelpDialog

        dialog = HelpDialog(topic_key=topic_key)
        help_widgets.append(dialog)
        dialog.resize(900, 500)
        dialog.show()
        qapp.processEvents()
        return dialog

    def test_clearing_the_search_keeps_the_readers_place_and_drops_the_marks(self, qapp, help_widgets):
        dialog = self._open(qapp, help_widgets, "calculator-reference")
        dialog._filter.setText("compar")
        # The search opens its best hit; the reader then picks the long page from the results.
        dialog.show_topic("calculator-reference")
        qapp.processEvents()
        assert dialog._current_key == "calculator-reference"
        assert dialog._view.extraSelections(), "the search should have marked something to clear"
        bar = dialog._view.verticalScrollBar()
        assert bar.maximum() > 300, "the page must be long enough for a scroll position to mean anything"
        bar.setValue(300)
        key_before = dialog._current_key

        reloads = []
        original = dialog._view.setMarkdown
        dialog._view.setMarkdown = lambda text: (reloads.append(1), original(text))[1]
        dialog._filter.setText("")
        qapp.processEvents()

        assert dialog._view.extraSelections() == []
        assert dialog._current_key == key_before
        assert dialog._view.verticalScrollBar().value() == 300
        assert not reloads, "clearing the search must not re-render the page"
        assert dialog._list.currentItem().data(Qt.ItemDataRole.UserRole) == key_before

    def test_clearing_a_search_with_nothing_open_still_works(self, qapp, help_widgets):
        dialog = self._open(qapp, help_widgets)
        dialog._current_key = ""
        dialog._filter.setText("conformer")
        dialog._filter.setText("")

        assert dialog._list.count() > 10

    def test_the_window_can_be_minimised_and_maximised(self, qapp, help_widgets):
        dialog = self._open(qapp, help_widgets)
        flags = dialog.windowFlags()

        assert flags & Qt.WindowType.WindowMaximizeButtonHint
        assert flags & Qt.WindowType.WindowMinimizeButtonHint
        assert dialog.isSizeGripEnabled()

    def test_the_whole_document_button_is_off_where_it_would_redraw_the_same_page(self, qapp, help_widgets):
        dialog = self._open(qapp, help_widgets, "calculator-reference")
        assert help_docs.topic("calculator-reference").level == 1
        assert not dialog._whole_document_button.isEnabled()

        section = next(t for t in help_docs.topics() if t.level > 1)
        dialog.show_topic(section.key)
        assert dialog._whole_document_button.isEnabled()

    def test_open_the_file_hands_the_current_document_to_the_system(self, qapp, help_widgets, monkeypatch):
        from openchem.ui.dialogs import help_dialog

        opened = []
        monkeypatch.setattr(help_dialog.QDesktopServices, "openUrl", lambda url: (opened.append(url), True)[1])
        dialog = self._open(qapp, help_widgets, "calculator-reference")
        dialog._open_file_button.click()

        assert len(opened) == 1
        assert opened[0].isLocalFile()
        opened_path = Path(opened[0].toLocalFile())
        # A COPY: the document the help is read from is never the one opened.
        assert opened_path.name == "CALCULATOR_REFERENCE.md"
        assert opened_path != help_docs.docs_directory() / "CALCULATOR_REFERENCE.md"
        assert opened_path.read_text(encoding="utf-8") == help_docs.document_text("CALCULATOR_REFERENCE.md")
        help_docs._remove_copy_directory()

    def test_open_the_file_says_so_when_the_system_has_no_program_for_it(self, qapp, help_widgets, monkeypatch):
        from openchem.ui.dialogs import help_dialog

        monkeypatch.setattr(help_dialog.QDesktopServices, "openUrl", lambda url: False)
        dialog = self._open(qapp, help_widgets, "calculator-reference")
        dialog._open_file_button.click()

        assert "no program" in dialog._status.text()
        assert "CALCULATOR_REFERENCE.md" in dialog._status.text()
