"""The virtual screening dialog.

Its table shipped with one column configured and three left at Qt's
default width, which clipped the longest header at both ends. Found by
driving the dialog and magnifying the shot, with every test in the suite
green -- the dialogs had no coverage at all until this file.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.ui.dialogs.inventory import DialogContext, iter_dialog_fixtures


@pytest.fixture
def dialog(qapp):
    """Built through `ui/dialogs/inventory.py`, not by hand.

    That module is the one place that knows how each dialog is
    constructed, shared with the `OPENCHEM_DRIVE` harness. Reaching past
    it here would be the second implementation it exists to prevent --
    and this fixture is also the proof that a guard CAN use it, which is
    what the drive step alone would not establish.
    """
    services = build_service_container()
    molecule = MoleculeModel(display_name="Aspirin")
    services.chemistry_engine.set_structure_from_smiles(molecule, "CC(=O)Oc1ccccc1C(=O)O")
    context = DialogContext(
        services=services,
        molecule=molecule,
        project=ProjectModel(name="screening", molecules=[molecule]),
    )
    fixture = next(f for f in iter_dialog_fixtures() if f.name == "VirtualScreeningDialog")
    built = fixture.build(context)
    yield built
    built.setParent(None)
    built.deleteLater()
    QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)


def test_no_results_header_is_narrower_than_its_own_text(dialog):
    """Every column header fits the words in it.

    ASSERTED IN THE HEADER'S OWN FONT, so this is a claim about the
    layout and not about the platform: `offscreen`'s default font is far
    wider than a user's, and a pinned pixel width here would fail against
    a dialog that is measurably clean in the app.

    The defect this catches rendered "Best score (kcal/mol)" as
    "est score (kcal/mo" -- clipped at BOTH ends, which is the tell that
    a section is narrower than its content rather than merely elided.
    """
    dialog.resize(900, 600)
    dialog.grab()  # a widget that was never shown lays nothing out

    header = dialog._results.horizontalHeader()
    metrics = header.fontMetrics()

    too_narrow = []
    for column in range(dialog._results.columnCount()):
        item = dialog._results.horizontalHeaderItem(column)
        text = item.text() if item is not None else ""
        needed = metrics.horizontalAdvance(text)
        if header.sectionSize(column) < needed:
            too_narrow.append((text, header.sectionSize(column), needed))

    assert not too_narrow, (
        "column header(s) narrower than their own text, so the words are "
        f"clipped: {too_narrow}"
    )


def test_the_ligand_column_is_the_one_that_absorbs_the_slack(dialog):
    """The other half, and the one that fails if every column is fixed.

    Sizing all four to their contents would satisfy the guard above while
    leaving a ragged table with dead space on the right. Ligand holds the
    variable-length value and is the column that should grow, which is
    what makes the arrangement a decision rather than an accident.
    """
    dialog.resize(1200, 600)
    dialog.grab()

    header = dialog._results.horizontalHeader()
    sizes = [header.sectionSize(c) for c in range(dialog._results.columnCount())]

    assert sizes[1] == max(sizes), (
        f"Ligand is not the widest column ({sizes}); the slack has gone "
        "somewhere it cannot be read"
    )
    assert sizes[1] > sum(sizes[c] for c in (0, 2, 3)) / 3, (
        f"Ligand did not absorb the extra width on a 1200 px dialog: {sizes}"
    )
