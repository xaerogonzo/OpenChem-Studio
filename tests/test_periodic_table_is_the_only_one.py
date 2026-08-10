"""There is ONE periodic table, and it can draw.

Ketcher ships its own on the editor toolbar; the application has a much
richer one under Tools. Two tables that look alike and know different
things read as one table that has lost half its features depending which
button you pressed -- reported, in those words, as "the periodic table no
longer shows all the atom drawing, it's reverted to vanilla". Neither
table was broken; there were simply two of them.

The editor's button is intercepted in `tools/ketcher-host/src/main.jsx`
and answered with this dialog, which gained "Insert into drawing" in the
same move. Taking a button over without taking its job over is just
breaking the button.

**The interception itself lives in the bundle and cannot be asserted
here.** `test_ketcher_bundle_is_current.py` already covers the half that
is checkable offline -- that `bridgeObject.periodicTableRequested()` in
the JSX has a matching `_Bridge` slot and appears in the committed dist.
The other half was verified in the running app, which is the only place
it can be: clicking the real button opened this dialog while Ketcher's
own stayed shut (`dialogs: 0, modals: 0`), and Insert armed the canvas
(`AtomTool2`).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.ui.dialogs.periodic_table_dialog import PeriodicTableDialog


@pytest.fixture
def dialog(qapp):
    built = PeriodicTableDialog()
    yield built
    built.setParent(None)
    built.deleteLater()
    QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)


def test_insert_asks_for_the_selected_element(dialog):
    dialog.select("Na")
    seen: list[str] = []
    dialog.insert_requested.connect(seen.append)

    dialog._insert_button.click()

    assert seen == ["Na"]


def test_insert_follows_the_selection_rather_than_the_first_click(dialog):
    """A stale symbol would draw the wrong element, which is the quiet
    kind of wrong -- the canvas gets an atom, just not the one asked
    for. Two selections, so a handler pinned to the first fails."""
    seen: list[str] = []
    dialog.insert_requested.connect(seen.append)

    dialog.select("Na")
    dialog._insert_button.click()
    dialog.select("Fe")
    dialog._insert_button.click()

    assert seen == ["Na", "Fe"]


def test_the_dialog_stays_open_after_inserting(dialog):
    """Placing three heteroatoms should not mean reopening the table
    between each. It is non-modal for the same reason."""
    dialog.show()
    dialog.select("O")

    dialog._insert_button.click()

    assert not dialog.isHidden()


def test_the_query_atom_gap_is_named_on_the_dialog(dialog):
    """Ketcher's table can draw list/not-list query atoms and this one
    cannot -- measured, `atomList` appears 149 times in the vendored
    bundle. Consolidating onto this table drops that capability from the
    button, so the dialog SAYS so.

    A gap that is merely absent looks identical to one nobody noticed;
    this is the same reason `catches_composition_order: false` is written
    into the assembly gate rather than left out of it.
    """
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert "query atom" in text.lower()


def test_the_dialog_no_longer_points_at_a_second_table(dialog):
    """It used to say "use the periodic table in the 2D editor's
    toolbar", which is now this same dialog. A sentence sending somebody
    back to where they came from is worse than none."""
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in dialog.findChildren(QLabel)).lower()

    assert "periodic table in the 2d editor" not in text
