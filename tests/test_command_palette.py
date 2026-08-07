"""Type what you want instead of remembering where it lives.

The ranking gets its own tests because it is the only part of a palette
that can be subtly WRONG rather than broken -- a palette that opens and
lists things but puts the obvious answer fourth is worse than none.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from openchem.ui.dialogs.command_palette import Command, CommandPalette, rank, score


def _dispose(widget) -> None:
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def _command(label: str, source: str = "Panel") -> Command:
    return Command(label=label, source=source, run=lambda: None)


# --- ranking, with no Qt at all ---------------------------------------------


def test_an_exact_match_beats_everything():
    assert score("batch", "Batch") > score("batch", "Batch Analysis")


def test_a_prefix_beats_a_word_start_which_beats_a_subsequence():
    """The order people expect, and the reason subsequence is last: it
    matches almost everything, so it must never outrank a real prefix."""
    prefix = score("str", "Structure Check")
    word = score("check", "Structure Check")
    subsequence = score("sck", "Structure Check")

    assert prefix > word > subsequence > 0


def test_a_shorter_match_wins_within_a_tier():
    """"prop" should find Properties before "Property Something Longer" --
    the shorter name is more likely to be the thing meant."""
    assert score("prop", "Properties") > score("prop", "Properties Extended View")


def test_initials_find_a_two_word_panel():
    """The move that makes a palette worth using: "qc" -> Quantum
    Chemistry, without typing either word."""
    assert score("qc", "Quantum Chemistry") > 0


def test_a_query_that_matches_nothing_scores_zero():
    assert score("zzz", "Properties") == 0


def test_an_empty_query_lists_everything():
    commands = [_command("Properties"), _command("Batch")]
    assert len(rank("", commands)) == 2


def test_ties_keep_the_caller_s_order():
    """Panels before calculators before menu items, so typing "geometry"
    lands on the panel rather than on a menu entry of the same name.
    Python's stable sort is what makes that free."""
    commands = [_command("Geometry", "Panel"), _command("Geometry", "Calculator")]
    assert [c.source for c in rank("geometry", commands)] == ["Panel", "Calculator"]


# --- the dialog -------------------------------------------------------------


@pytest.fixture
def palette(qapp):
    ran: list[str] = []
    commands = [
        Command(label="Properties", source="Panel", run=lambda: ran.append("Properties")),
        Command(label="Quantum Chemistry", source="Panel", run=lambda: ran.append("QC")),
        Command(label="Elemental Analysis", source="Calculator", run=lambda: ran.append("EA")),
        Command(label="New Molecule", source="File", run=lambda: ran.append("New")),
    ]
    dialog = CommandPalette(commands)
    yield dialog, ran
    _dispose(dialog)


def test_it_lists_everything_before_you_type(palette):
    dialog, _ran = palette
    assert len(dialog.visible_labels()) == 4


def test_typing_narrows_the_list(palette):
    dialog, _ran = palette
    dialog._search.setText("quantum")
    assert dialog.visible_labels() == ["Quantum Chemistry    (Panel)"]


def test_the_source_is_shown_because_a_name_alone_is_ambiguous(palette):
    """"Geometry" is a panel, a calculator and a menu item. Without the
    source the list is three identical rows."""
    dialog, _ran = palette
    assert all("(" in label for label in dialog.visible_labels())


def test_enter_runs_the_highlighted_command(palette):
    """The only reason to use a palette rather than the menus: you type,
    you press Enter, your hands never leave the keyboard."""
    dialog, ran = palette
    dialog._search.setText("elemental")

    dialog._run_current()

    assert ran == ["EA"]
    assert dialog.chosen().label == "Elemental Analysis"


def test_the_arrow_keys_move_the_selection_without_leaving_the_box(palette):
    """Otherwise choosing the second result means tabbing out of the
    search field, which defeats the point."""
    from PySide6.QtGui import QKeyEvent

    dialog, ran = palette
    assert dialog._list.currentRow() == 0

    dialog.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))

    assert dialog._list.currentRow() == 1
    dialog._run_current()
    assert ran == ["QC"]


def test_it_closes_before_running_so_a_dialog_does_not_open_behind_it(qapp):
    opened_while_visible: list[bool] = []
    dialog: CommandPalette | None = None

    def _open_something() -> None:
        opened_while_visible.append(dialog.isVisible())

    dialog = CommandPalette([Command(label="Thing", source="Panel", run=_open_something)])
    dialog._run_current()

    assert opened_while_visible == [False]
    _dispose(dialog)


# --- the three indexes ------------------------------------------------------


def test_the_window_offers_panels_calculators_and_menu_items(qapp, tmp_path):
    """**No fourth registry.** A palette that needed each feature to
    register itself would be another list to keep in step, and the one
    that falls out of step is always the one nobody updates."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    window = MainWindow(services, settings, SessionManager())

    commands = window._collect_commands()
    sources = {c.source for c in commands}
    labels = {c.label for c in commands}

    assert "Panel" in sources and "Calculator" in sources
    assert "File" in sources, sorted(sources)
    assert "Properties" in labels
    assert "New Molecule" in labels
    window.close()


def test_every_panel_the_rail_knows_is_in_the_palette(qapp, tmp_path):
    """Walks what the window BUILDS, so a panel added later is covered
    without anybody remembering to add it here."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    window = MainWindow(services, settings, SessionManager())

    panels = {c.label for c in window._collect_commands() if c.source == "Panel"}
    for dock in window._right_docks:
        assert dock.windowTitle() in panels, dock.windowTitle()
    window.close()


def test_a_disabled_menu_action_is_not_offered(qapp, tmp_path):
    """Offering something that cannot run is worse than not offering it.

    Uses an action this test adds and holds, rather than one taken out of
    `_menu_actions()`. Those wrappers are transient -- the C++ QAction can
    be gone by the time the returned list is unpacked -- which is exactly
    why `_menu_actions` captures each label while it walks instead of
    handing back a wrapper for the caller to read later.
    """
    from PySide6.QtGui import QAction

    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    window = MainWindow(services, settings, SessionManager())

    # `top_actions` is held deliberately. A wrapper reached only through a
    # TEMPORARY list is invalidated when that list is released, so
    # `next(a.menu() for a in bar.actions() ...)` hands back a QMenu that
    # raises `Internal C++ object already deleted` on the next line. The
    # C++ menu is fine; the wrapper is not.
    top_actions = window.menuBar().actions()
    view_menu = next(
        action.menu()
        for action in top_actions
        if action.menu() is not None and "View" in action.text()
    )
    probe = QAction("Palette Probe", window)
    view_menu.addAction(probe)

    assert "Palette Probe" in {entry[0] for entry in window._menu_actions()}

    probe.setEnabled(False)

    assert "Palette Probe" not in {entry[0] for entry in window._menu_actions()}
    window.close()


def test_a_panel_is_offered_once_not_twice(qapp, tmp_path):
    """Every dock's `toggleViewAction` sits in the View menu under the
    panel's own name, so without this every panel appeared twice. The
    panel command wins because it SHOWS the panel; the toggle can hide
    it, which from a palette is a surprising thing to have asked for."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    window = MainWindow(services, settings, SessionManager())

    labels = [c.label for c in window._collect_commands()]

    assert labels.count("Properties") == 1, [label for label in labels if label == "Properties"]
    assert labels.count("Batch") == 1
    # Console is a dock with a toggle and NO rail entry, so its View item
    # is the only way to reach it and must survive the de-duplication.
    assert "Console" in labels
    window.close()
