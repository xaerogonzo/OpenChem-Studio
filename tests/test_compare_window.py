"""Setting two charge methods side by side, from the Calculator Inspector.

The domain rules are in `test_compare.py`. This is the wiring: the Properties panel keeps a pool
of the per-atom results a molecule has produced (the store keeps one per calculator, so a second
method REPLACED the first), the Inspector offers only comparisons that would not be refused, and
the window shows the table the domain built.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QMessageBox, QTableWidget

import openchem.ui.panels.property_panel as property_panel_module
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import Provenance
from openchem.domain.compare import ComparedResult, compare
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, PerAtomDataComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog
from openchem.ui.dialogs.compare_results_dialog import CompareResultsDialog
from openchem.ui.panels.property_panel import PropertyPanel
from tests.conftest import dispose
from tests.test_property_panel import _FakeDescriptorService


def _dataset(molecule, method, values, units="e", **extra) -> PerAtomDataset:
    return PerAtomDataset(
        timestamp=0.0, property_id="geometry_partial_charge", name=f"Partial Charge ({method})",
        units=units, method=method, molecule_uuid=molecule.uuid, values=values,
        provenance=Provenance(created_by="core", method=method, parameters={}), **extra,
    )


def _arrive(bus, dataset, fingerprint="f1", calculation_input="drawing") -> None:
    bus.publish(PerAtomDataComputed(dataset=dataset, input_fingerprint=fingerprint, calculation_input=calculation_input))


@pytest.fixture
def rig(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeDescriptorService(), engine)
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")  # three heavy atoms: C, C, O
    panel.set_project(ProjectModel(molecules=[molecule]))
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    yield panel, bus, molecule
    dispose(panel)


EEM = {0: -0.10, 1: 0.05, 2: -0.55}
QEQ = {0: -0.20, 1: 0.10, 2: -0.70}


# --- the pool ---------------------------------------------------------------------------------


def test_two_methods_are_both_held_which_the_store_alone_could_not(rig):
    panel, bus, molecule = rig
    eem, qeq = _dataset(molecule, "eem", EEM), _dataset(molecule, "qeq", QEQ)
    _arrive(bus, eem)
    _arrive(bus, qeq)

    anchor, others = panel.comparable_with(eem)

    assert anchor.dataset is eem
    assert [c.dataset for c in others] == [qeq]


def test_the_same_method_recomputed_replaces_its_own_slot_not_a_second_one(rig):
    panel, bus, molecule = rig
    first = _dataset(molecule, "eem", EEM)
    again = _dataset(molecule, "eem", {0: -0.11, 1: 0.05, 2: -0.55})
    _arrive(bus, first)
    _arrive(bus, again)
    assert len(panel._compare_pool) == 1


def test_a_result_computed_for_an_earlier_drawing_is_not_offered(rig):
    panel, bus, molecule = rig
    eem, qeq = _dataset(molecule, "eem", EEM), _dataset(molecule, "qeq", QEQ)
    _arrive(bus, eem, fingerprint="before-the-edit")
    _arrive(bus, qeq, fingerprint="after-the-edit")
    assert panel.comparable_with(qeq)[1] == []


def test_a_result_in_other_units_is_not_offered(rig):
    panel, bus, molecule = rig
    charge, energy = _dataset(molecule, "eem", EEM), _dataset(molecule, "other", QEQ, units="kcal/mol")
    _arrive(bus, charge)
    _arrive(bus, energy)
    assert panel.comparable_with(charge)[1] == []


def test_selecting_another_molecule_drops_the_pool(rig):
    panel, bus, molecule = rig
    _arrive(bus, _dataset(molecule, "eem", EEM))
    bus.publish(MoleculeSelected(molecule_uuid="somebody-else"))
    assert panel._compare_pool == {}


def test_a_different_ph_is_a_different_result_of_one_method(rig):
    panel, bus, molecule = rig
    five = replace(_dataset(molecule, "mmff94", EEM), provenance=Provenance(
        created_by="core", method="mmff94", parameters={"pH": 5.0}))
    nine = replace(_dataset(molecule, "mmff94", QEQ), provenance=Provenance(
        created_by="core", method="mmff94", parameters={"pH": 9.0}))
    _arrive(bus, five)
    _arrive(bus, nine)
    assert len(panel._compare_pool) == 2


# --- opening a comparison -----------------------------------------------------------------------


def test_opening_a_comparison_shows_the_table_with_element_symbols(rig):
    panel, bus, molecule = rig
    eem, qeq = _dataset(molecule, "eem", EEM), _dataset(molecule, "qeq", QEQ)
    _arrive(bus, eem)
    _arrive(bus, qeq)
    anchor, others = panel.comparable_with(eem)

    panel._open_comparison([anchor, *others])

    window = panel._last_comparison()
    assert isinstance(window, CompareResultsDialog)
    table = window.findChild(QTableWidget, "compareTable")
    assert table.rowCount() == 3
    assert [table.item(r, 1).text() for r in range(3)] == ["C", "C", "O"]
    window.close()


def test_a_refused_comparison_says_why_and_opens_nothing(rig, monkeypatch):
    panel, bus, molecule = rig
    told: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: told.append(text))
    eem = _dataset(molecule, "eem", EEM)
    edited = ComparedResult(_dataset(molecule, "qeq", QEQ), "another-drawing", "drawing")

    panel._open_comparison([ComparedResult(eem, "f1", "drawing"), edited])

    assert len(told) == 1 and "edited" in told[0]
    assert panel._last_comparison is None


def test_symbols_are_dropped_rather_than_put_on_the_wrong_atoms(rig):
    """Indices that do not fit the structure (here: a value for atom 9 of a 3-atom molecule)."""
    panel, _bus, molecule = rig
    dataset = _dataset(molecule, "eem", {0: 0.0, 9: 1.0})
    assert panel._symbols_for(molecule, ComparedResult(dataset, "f1", "drawing")) == {}


# --- the window ---------------------------------------------------------------------------------


def _window(qapp, values_b=QEQ):
    molecule = MoleculeModel(display_name="m")
    a = ComparedResult(_dataset(molecule, "eem", EEM))
    b = ComparedResult(_dataset(molecule, "qeq", values_b))
    comparison = compare([a, b])
    return CompareResultsDialog(comparison, {0: "C", 1: "C", 2: "O"}, "Ethanol"), comparison


def test_the_summary_names_the_atom_the_methods_disagree_about_most(qapp):
    window, _comparison = _window(qapp)
    summary = window.findChild(type(window._summary), "compareSummary").text()
    assert "atom 3 (O)" in summary, summary  # 0.15 of spread against 0.10 and 0.05
    assert "e" in summary
    window.close()


def test_the_columns_are_the_atom_the_results_the_spread_and_each_difference(qapp):
    window, _comparison = _window(qapp)
    # A long heading is split over two lines at its first parenthesis, and whole in its tooltip.
    headers = [window._table.horizontalHeaderItem(c) for c in range(window._table.columnCount())]
    assert [h.toolTip() for h in headers[:2]] == ["#", "Element"]
    assert headers[2].text() == "Partial Charge\n(eem)" and headers[2].toolTip() == "Partial Charge (eem)"
    assert headers[3].toolTip() == "Partial Charge (qeq)"
    assert headers[4].text() == "Spread"
    assert headers[5].text().startswith("Δ Partial Charge")
    assert "minus Partial Charge (eem)" in headers[5].toolTip(), "a difference says what it is a difference OF"
    window.close()


def test_sorting_by_spread_is_numeric_and_puts_the_worst_atom_first(qapp):
    """Text order would put "0.1500" before "0.0500" only by luck of the digits; a sign would break it."""
    window, _comparison = _window(qapp)
    window._table.sortItems(4, Qt.SortOrder.DescendingOrder)
    assert window._table.item(0, 1).text() == "O", "atom 3 has the largest spread"
    window.close()


def test_copy_puts_the_table_on_the_clipboard(qapp):
    from PySide6.QtGui import QGuiApplication

    window, comparison = _window(qapp)
    window._copy_button.click()
    assert QGuiApplication.clipboard().text() == comparison.as_text({0: "C", 1: "C", 2: "O"})
    window.close()


# --- the inspector's button ---------------------------------------------------------------------


def _inspector(qapp, result, molecule, candidates):
    engine = ChemistryEngine()
    chosen: list = []
    dialog = CalculatorInspectorDialog(
        engine, molecule, result, None,
        compare_candidates=lambda _r: candidates, on_compare=lambda picked: chosen.append(list(picked)),
    )
    return dialog, chosen


def _molecule():
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    return molecule


def test_the_inspector_offers_compare_for_a_per_atom_result(qapp):
    molecule = _molecule()
    result = _dataset(molecule, "eem", EEM)
    dialog, _chosen = _inspector(qapp, result, molecule, (ComparedResult(result), []))
    assert dialog.findChild(type(dialog._compare_button), "compareWith") is not None
    dispose(dialog)


def test_the_menu_lists_each_comparable_result_and_all_of_them(qapp):
    molecule = _molecule()
    result = _dataset(molecule, "eem", EEM)
    other_a = ComparedResult(_dataset(molecule, "qeq", QEQ))
    other_b = ComparedResult(_dataset(molecule, "gasteiger", {0: 0.0, 1: 0.0, 2: 0.0}))
    anchor = ComparedResult(result)
    dialog, chosen = _inspector(qapp, result, molecule, (anchor, [other_a, other_b]))

    dialog._rebuild_compare_menu()
    texts = [a.text() for a in dialog._compare_menu.actions()]
    assert texts == ["With Partial Charge (qeq)", "With Partial Charge (gasteiger)", "With all 2"]

    dialog._compare_menu.actions()[2].trigger()
    assert chosen == [[anchor, other_a, other_b]]
    dispose(dialog)


def test_an_empty_menu_says_what_to_do_instead_of_being_empty(qapp):
    molecule = _molecule()
    result = _dataset(molecule, "eem", EEM)
    dialog, _chosen = _inspector(qapp, result, molecule, (ComparedResult(result), []))
    dialog._rebuild_compare_menu()
    [only] = dialog._compare_menu.actions()
    assert "run another method" in only.text() and not only.isEnabled()
    dispose(dialog)


def test_a_result_that_is_not_per_atom_has_no_compare_button(qapp):
    from openchem.domain.scientific_result import AlertResult

    molecule = _molecule()
    alert = AlertResult(timestamp=0.0, alert_id="pains", name="PAINS", molecule_uuid=molecule.uuid, matched=[])
    dialog, _chosen = _inspector(qapp, alert, molecule, (ComparedResult(alert), []))
    assert not hasattr(dialog, "_compare_button")
    dispose(dialog)


def test_the_panel_hands_its_own_candidates_and_opener_to_the_inspector(rig, monkeypatch):
    panel, _bus, molecule = rig
    seen: dict = {}

    class _Inspector:
        def __init__(self, engine, molecule, result, conformer_molblock, parent=None, **kwargs):
            seen.update(kwargs)

        def setWindowTitle(self, _t): pass
        def setAttribute(self, *_a): pass
        def show(self): pass
        def isVisible(self): return True
        def raise_(self): pass
        def activateWindow(self): pass
        def pos(self):
            from PySide6.QtCore import QPoint
            return QPoint(0, 0)
        def move(self, *_a): pass
        def width(self): return 100
        def height(self): return 100

    monkeypatch.setattr(property_panel_module, "CalculatorInspectorDialog", _Inspector)
    panel._open_inspector(_dataset(molecule, "eem", EEM))

    assert seen["compare_candidates"] == panel.comparable_with
    assert seen["on_compare"] == panel._open_comparison
