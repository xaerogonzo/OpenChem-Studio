"""Keeping a panel's molecule dropdown in step with the project and the selection.

Two separate bugs live here, and both were invisible rather than loud --
the panel went on working, just on the wrong molecule.

**Repopulating loses the selection.** `QComboBox.clear()` resets the
current index to 0. Every panel's combo is rebuilt on any project mutation
(MainWindow calls `set_project` again from `_refresh_molecule_combos`), so
merely ADDING a molecule silently moved the Quantum Chemistry and Docking
panels back to the first one. Confirmed live: with two molecules, drawing
in the second and pressing Run built the job from the first.

**A panel that ignores the selection operates on something else.** The 2D
editor, the 3D viewer and the Property panel all follow `MoleculeSelected`.
The Quantum Chemistry and Docking panels did not, so the molecule on screen
and the molecule in the dropdown were free to differ -- and when a project
holds two molecules both called "New molecule" (the old default name, since
fixed), nothing about the dropdown looked wrong. The reported symptom was
ORCA refusing to run with "generate conformers first" while the 3D viewer
was showing ten of them, which reads as a broken ORCA integration and is
not one.

Restoring by **uuid rather than index** is the point: a rename or a delete
changes the labels and the ordering, so an index is not the same molecule
after a rebuild.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import QComboBox


def repopulate(combo: QComboBox, entries: Iterable[tuple[str, str]]) -> None:
    """Refill `combo` with (label, uuid) pairs, keeping the current pick.

    Signals are blocked across the rebuild so a repopulate does not look
    like a user changing the selection -- panels react to
    `currentIndexChanged` by resetting charge, clearing results and so on,
    and firing that for a rename of some unrelated molecule would be its
    own bug.
    """
    previous = combo.currentData()
    combo.blockSignals(True)
    try:
        combo.clear()
        for label, uuid in entries:
            combo.addItem(label, uuid)
        if previous is not None:
            restored = combo.findData(previous)
            if restored >= 0:
                combo.setCurrentIndex(restored)
    finally:
        # In a finally block because leaving a combo permanently mute is a
        # far worse failure than the exception that caused it: the panel
        # would keep rendering correctly and quietly stop reacting.
        combo.blockSignals(False)


def select(combo: QComboBox, uuid: str | None) -> bool:
    """Point `combo` at `uuid`. True if it was there to select.

    Unlike `repopulate` this does NOT block signals -- following the
    selection is a real change of subject for the panel, and the handlers
    hanging off `currentIndexChanged` (re-reading formal charge, clearing
    the previous molecule's results) are exactly what should run.

    A missing uuid leaves the combo alone rather than clearing it. The
    molecule may simply not belong in this dropdown -- selecting a
    macromolecule should not blank the ligand list.
    """
    if uuid is None:
        return False
    index = combo.findData(uuid)
    if index < 0:
        return False
    if index != combo.currentIndex():
        combo.setCurrentIndex(index)
    return True
