"""The Atom Inspector and the 2D editor point at the same atom.

`AtomInspectorPanel.atom_selected` was emitted and **connected to nothing**.
Its own comment said "so viewers can highlight it" and no viewer ever heard
it, so picking a row named an atom you then had to find by eye -- on a
structure of any size, that is the panel telling you about an atom it will
not show you.

**THE INDEX TRANSLATION IS NOT HERE.** Ketcher's pool ids and the molfile's
positions diverge the moment anything is deleted, and that lives in
`main.jsx`'s `poolIdAt`, asserted against the real bundle in
`tests/test_ketcher_editor_backend.py`. What lives here is the other half of
the problem, which is entirely Python's: the two directions form a LOOP.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication


@pytest.fixture
def window(qapp, tmp_path):
    """A real MainWindow, because the loop being guarded against is between
    two widgets and closes through this layer -- neither half of it is
    visible from either widget on its own."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


def _ethanol_in(window):
    molecule = window._current_molecule()
    window._services.chemistry_engine.set_structure_from_smiles(molecule, "CCO")
    window._atom_inspector_panel.set_project(window._session.project)
    window._atom_inspector_panel._molecule_uuid = molecule.uuid
    window._atom_inspector_panel._rebuild_atom_table()
    QCoreApplication.processEvents()
    return molecule


def _recording_canvas(window) -> list[list[int]]:
    """Record what reaches the BACKEND, not what reaches the widget.

    **ONE LAYER LOWER THAN THE OBVIOUS PLACE, AND A MUTATION PASS IS WHY.**
    Patching `window._editor.select_atoms` replaces the very method that
    carries the call from the widget to its backend, so emptying that
    method out changed nothing and every test here still passed -- the
    recorder had stood in for the thing under test. Measured: arm K6
    survived a full run.

    The real page is exercised in `tests/test_ketcher_editor_backend.py`;
    what is asserted here is which calls happen and which do not, and a
    QWebEngine round trip would make that a timing question.
    """
    sent: list[list[int]] = []
    window._editor._backend.select_atoms = lambda indices: sent.append(list(indices))
    return sent


def _pick_row_for(window, atom_index: int) -> None:
    """Select the TABLE ROW, not the panel method behind it.

    `AtomInspectorPanel.select_atom` is the INBOUND door -- the 3D viewer's
    click lands there -- and the path under test starts one step later, at
    `_on_row_selected` reading the table's own selection. Driving the method
    would exercise the same emit and say nothing about the row being what
    emits it.
    """
    from PySide6.QtCore import Qt

    table = window._atom_inspector_panel._atom_table
    for row in range(table.rowCount()):
        cell = table.item(row, 0)
        if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == atom_index:
            table.selectRow(row)
            QCoreApplication.processEvents()
            return
    raise AssertionError(
        f"no inspector row holds atom {atom_index} ({table.rowCount()} rows)"
    )


def test_picking_an_inspector_row_shows_that_atom_on_the_canvas(window):
    """The wire that did not exist."""
    _ethanol_in(window)
    sent = _recording_canvas(window)

    _pick_row_for(window, 2)

    assert sent == [[2]], f"the canvas was told {sent}"


def test_the_editors_own_click_is_not_sent_straight_back(window):
    """**THE LOOP, AND THE ORDER OF TWO LINES IS THE WHOLE GUARD.**

    `select_atom` selects the table row, and Qt delivers
    `itemSelectionChanged` SYNCHRONOUSLY -- so the editor reporting a click
    comes straight back out of the panel as `atom_selected` before
    `_on_editor_atom_selected` has returned. Recording what the editor
    reported *after* that call means the echo arrives while the comparison
    still reads `None`, and gets pushed to the canvas as a fresh pick.

    Measured in the running app before this was fixed: erasing an atom
    (which selects it before pressing Delete, as a user does) left an
    unrelated carbon selected on the canvas -- and a Ketcher selection is
    ACTIONABLE, so the next Delete would have acted on it.

    A re-entrancy flag cannot close this. The trip is synchronous here and
    asynchronous through the web channel in the real application, so the
    flag is either still set or long since cleared depending on which, and
    only comparing the indices works for both.
    """
    _ethanol_in(window)
    sent = _recording_canvas(window)

    window._on_editor_atom_selected(2)

    assert sent == [], (
        f"the editor's own selection was sent back to it: {sent}. "
        "`_selected_atom_index` must be assigned BEFORE `select_atom`."
    )


def test_the_guard_does_not_swallow_a_genuinely_new_pick(window):
    """The other half, and the reason this is a comparison rather than a
    mute: after the editor reports one atom, picking a DIFFERENT row must
    still reach the canvas. A guard that suppressed everything after an
    editor click would pass the test above and break the feature."""
    _ethanol_in(window)
    window._on_editor_atom_selected(2)
    sent = _recording_canvas(window)

    _pick_row_for(window, 0)

    assert sent == [[0]], f"a genuinely new pick was swallowed: {sent}"


def test_the_round_trip_settles_instead_of_ringing(window):
    """Feed the echo back the way the page really does.

    `Editor.selection()` dispatches `selectionChange` unconditionally --
    read from Ketcher's own TypeScript source -- so every selection sent
    from here returns as `atomSelected`. Replaying that by hand is the only
    way to assert termination without a web view, and termination is the
    property that matters: a wrong mapping in either direction would leave
    the two panels handing an index back and forth forever.
    """
    _ethanol_in(window)
    sent = _recording_canvas(window)

    _pick_row_for(window, 1)
    assert sent == [[1]]

    # The page echoes what it was just told.
    for _ in range(5):
        window._on_editor_atom_selected(1)

    assert sent == [[1]], f"the echo kept going round: {sent}"


def test_the_signal_the_panel_offers_is_the_one_the_window_connects(window):
    """The narrow half, because everything above would also pass if the
    panel emitted on a schedule of its own: what is connected is
    `atom_selected`, and it carries a MOLFILE POSITION -- the index space
    `main.jsx` translates into before anything crosses the bridge, and the
    one `poolIdAt` translates back out of."""
    _ethanol_in(window)
    seen: list[int] = []
    window._atom_inspector_panel.atom_selected.connect(seen.append)

    _pick_row_for(window, 2)

    assert seen == [2]
