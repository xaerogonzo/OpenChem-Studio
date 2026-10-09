"""Copying one thing out of the Calculator Inspector, not the whole result.

The headline sentences are highlightable and the per-atom table copies a cell
or a row. `QMenu.exec` is modal and cannot be patched, so the menu is built
and an action triggered without ever being shown.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import Provenance, declare_total
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.ui.dialogs.calculator_inspector_dialog import (
    CalculatorInspectorDialog,
    _CalculatorResultView,
)

import conftest


def _dialog() -> CalculatorInspectorDialog:
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = PerAtomDataset(
        property_id="test_calc",
        name="Test Calculator at pH 7.4",
        units="e",
        method="rdkit",
        molecule_uuid="mol-1",
        values={0: -0.2, 1: 0.3, 2: 0.15},
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={"total": declare_total(0.25, "Net charge")},
        ),
    )
    return CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)


def _view(dialog) -> _CalculatorResultView:
    return dialog.findChildren(_CalculatorResultView)[0]


def _clipboard() -> str:
    return QGuiApplication.clipboard().text()


def _choose(view, row: int, action_text: str) -> None:
    QGuiApplication.clipboard().clear()
    index = view._table_proxy.index(row, 2)
    menu, choose = view.table_menu(index)
    choose(next(a for a in menu.actions() if a.text() == action_text))


def test_headline_sentences_can_be_highlighted(qapp):
    dialog = _dialog()
    sentences = {
        label.text(): label
        for label in dialog.findChildren(QLabel)
        if label.text() in ("Test Calculator at pH 7.4", "Net charge: 0.25")
    }
    assert len(sentences) == 2, [l.text() for l in dialog.findChildren(QLabel)]
    for label in sentences.values():
        assert label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    conftest.dispose(dialog)


def test_copy_cell_and_copy_row_take_the_cell_under_the_pointer(qapp):
    dialog = _dialog()
    view = _view(dialog)
    # Make the CURRENT row differ from the clicked one: the menu must follow
    # the pointer, not the last selection.
    view._table.selectRow(0)
    for row in range(3):
        index = view._table_proxy.index(row, 2)
        expected_cell = view.table_cell_text(index)
        expected_row = view.table_row_text(index)
        _choose(view, row, "Copy cell")
        assert _clipboard() == expected_cell
        _choose(view, row, "Copy row")
        assert _clipboard() == expected_row
    assert view.table_row_text(view._table_proxy.index(1, 2)) == "2\tC\t0.30"
    conftest.dispose(dialog)


def test_ctrl_c_copies_the_current_row_in_copy_all_format(qapp):
    dialog = _dialog()
    view = _view(dialog)
    view._table.selectRow(2)
    view._table.setCurrentIndex(view._table_proxy.index(2, 0))
    QGuiApplication.clipboard().clear()
    view._copy_current_row()
    assert _clipboard() == view.table_row_text(view._table_proxy.index(2, 0))
    assert _clipboard() in view.table_text()
    conftest.dispose(dialog)
