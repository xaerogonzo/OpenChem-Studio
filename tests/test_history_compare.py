"""Mixed ordinary-vs-Quantum history compare is an allowlist, not a name match."""

from __future__ import annotations

import math

import pytest

from openchem.domain.descriptor import DescriptorValue
from openchem.domain.history_compare import (
    MIXED_UNAPPROVED,
    MixedHistoryMatch,
    MixedQuantity,
    history_compare_choice_map,
    history_compare_label,
    match_mixed_history,
    mixed_history_comparable,
    named_row_from_mixed_match,
    other_history_entries,
    property_executions_comparable,
    quantum_runs_comparable,
)
from openchem.domain.property_execution import ExecutionStatus, PropertyExecution
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus, new_run_id
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.structure_issue import Basis


def _quantity(**overrides) -> MixedQuantity:
    values = dict(
        quantity_id="toy_homo",
        label="HOMO energy",
        units="eV",
        ordinary_producers=frozenset({"toy"}),
        ordinary_result_ids=frozenset({"toy_gap"}),
        ordinary_value_ids=frozenset({"toy.homo"}),
        quantum_descriptor_ids=frozenset({"orca.homo_energy"}),
        quantum_calc_types=frozenset({"sp"}),
        allow_cross_molecule=False,
    )
    values.update(overrides)
    return MixedQuantity(**values)


def _descriptor(descriptor_id="toy.homo", value= -0.3, units="eV", name="E(HOMO)") -> DescriptorValue:
    return DescriptorValue(
        descriptor_id=descriptor_id,
        name=name,
        units=units,
        category="electronic",
        provider="toy",
        molecule_uuid="m1",
        value=value,
    )


def _stored(result, *, result_id="toy_gap", producer="toy", molecule="m1") -> StoredResult:
    return StoredResult(
        identity=ResultIdentity(
            molecule_uuid=molecule,
            result_id=result_id,
            calculation_input="geometry",
            input_fingerprint="fp",
            producer=producer,
        ),
        result=result,
    )


def _execution(
    *,
    producer="toy",
    molecule="m1",
    calculation_input="geometry",
    outputs=None,
    execution_id="exec-1",
) -> PropertyExecution:
    return PropertyExecution(
        execution_id=execution_id,
        molecule_uuid=molecule,
        producer=producer,
        method_model="huckel",
        parameters_key="k",
        calculation_input=calculation_input,
        input_fingerprint="fp",
        status=ExecutionStatus.COMPLETED,
        outputs=list(outputs or [_stored(_descriptor())]),
    )


def _run(
    *,
    molecule="m1",
    calc_type="sp",
    calculation_input="geometry",
    descriptors=None,
    run_id=None,
    extras=None,
) -> QuantumChemistryRun:
    results = {"descriptors": list(descriptors or [_descriptor("orca.homo_energy", -0.4, name="E(HOMO)")])}
    if extras:
        results.update(extras)
    return QuantumChemistryRun(
        run_id=run_id or new_run_id(),
        molecule_uuid=molecule,
        calc_type=calc_type,
        method_basis="B3LYP def2-SVP",
        charge=0,
        multiplicity=1,
        calculation_input=calculation_input,
        input_fingerprint="fp",
        input_molblock="",
        provider="orca",
        status=RunStatus.COMPLETED,
        completed_at=1.0,
        results=results,
        output_status={},
    )


@pytest.fixture
def allow(monkeypatch):
    import openchem.domain.history_compare as module

    quantity = _quantity()
    monkeypatch.setattr(module, "MIXED_QUANTITIES", (quantity,))
    return quantity


def test_empty_allowlist_refuses_every_mixed_pair():
    execution = _execution()
    run = _run()
    assert match_mixed_history(execution, run) == MIXED_UNAPPROVED
    assert mixed_history_comparable(execution, run) == MIXED_UNAPPROVED


def test_identical_display_names_do_not_authorize_comparison():
    execution = _execution()
    run = _run()
    assert "E(HOMO)" in (execution.outputs[0].result.name,)
    assert run.results["descriptors"][0].name == "E(HOMO)"
    assert match_mixed_history(execution, run) == MIXED_UNAPPROVED


def test_matching_producer_alone_does_not_authorize(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(ordinary_result_ids=frozenset({"other_id"})),),
    )
    assert match_mixed_history(_execution(), _run()) == MIXED_UNAPPROVED


def test_patched_allowlist_returns_the_match(allow):
    execution = _execution()
    run = _run()
    outcome = match_mixed_history(execution, run)
    assert isinstance(outcome, MixedHistoryMatch)
    assert outcome.quantity is allow
    assert outcome.ordinary_value == pytest.approx(-0.3)
    assert outcome.quantum_value == pytest.approx(-0.4)
    assert outcome.units == "eV"
    assert outcome.quantity.label == "HOMO energy"
    assert mixed_history_comparable(execution, run) == ""


def test_exact_value_selectors_are_required(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(ordinary_value_ids=frozenset({"not.this"})),),
    )
    assert match_mixed_history(_execution(), _run()) == MIXED_UNAPPROVED


def test_ambiguous_ordinary_match_refuses(allow):
    extra = _stored(_descriptor(value=-0.1), result_id="toy_gap")
    execution = _execution(outputs=[_stored(_descriptor()), extra])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


def test_missing_or_non_numeric_refuses(allow):
    execution = _execution(outputs=[_stored(_descriptor(value="n/a"))])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_refuses(allow, value):
    execution = _execution(outputs=[_stored(_descriptor(value=value))])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


def test_units_must_match_the_declared_quantity(allow):
    execution = _execution(outputs=[_stored(_descriptor(units="beta"))])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


def test_unsupported_quantum_calc_type_refuses(allow):
    assert match_mixed_history(_execution(), _run(calc_type="opt")) == MIXED_UNAPPROVED


def test_drawing_versus_geometry_refuses_even_with_a_patched_entry(allow):
    execution = _execution(calculation_input="drawing")
    run = _run(calculation_input="geometry")
    message = match_mixed_history(execution, run)
    assert "drawing" in message.lower() or "3D" in message or "input" in message.lower()
    assert not isinstance(message, MixedHistoryMatch)


def test_cross_molecule_refuses_unless_the_entry_permits(allow, monkeypatch):
    import openchem.domain.history_compare as module

    execution = _execution(molecule="m1")
    run = _run(molecule="m2")
    assert match_mixed_history(execution, run) == "Those runs belong to different molecules."
    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(allow_cross_molecule=True),),
    )
    outcome = match_mixed_history(execution, run)
    assert isinstance(outcome, MixedHistoryMatch)


def test_report_fact_matches_help_id_not_label(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(ordinary_value_ids=frozenset({"fact.homo"})),),
    )
    fact = Fact(
        category=FactCategory.ELECTRONIC,
        label="E(HOMO)",
        value=-0.25,
        display_value="-0.25",
        source="toy",
        basis=Basis.DETERMINISTIC,
        units="eV",
        help_id="fact.homo",
    )
    report = ReportResult(
        report_id="toy_gap",
        name="Toy gap",
        molecule_uuid="m1",
        facts=(fact,),
    )
    execution = _execution(outputs=[_stored(report)])
    outcome = match_mixed_history(execution, _run())
    assert isinstance(outcome, MixedHistoryMatch)
    assert outcome.ordinary_value == pytest.approx(-0.25)


def test_named_row_reverses_delta_with_orientation(allow):
    match = match_mixed_history(_execution(), _run())
    assert isinstance(match, MixedHistoryMatch)
    ordinary_left = named_row_from_mixed_match(match, ordinary_on_left=True)
    quantum_left = named_row_from_mixed_match(match, ordinary_on_left=False)
    assert ordinary_left.delta == pytest.approx(-0.1)
    assert quantum_left.delta == pytest.approx(0.1)
    assert ordinary_left.label == "HOMO energy"


def test_pool_includes_both_kinds_and_excludes_the_selection():
    execution = _execution(execution_id="keep")
    other = _execution(execution_id="other")
    run = _run()
    pool = other_history_entries([execution, other], [run], execution)
    ids = {
        getattr(item, "execution_id", None) or getattr(item, "run_id", None)
        for item in pool
    }
    assert "keep" not in ids
    assert "other" in ids
    assert run.run_id in ids


def test_quantum_descriptor_id_not_display_name(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(quantum_descriptor_ids=frozenset({"orca.homo_energy"})),),
    )
    run = _run(descriptors=[_descriptor("other.homo", -0.4, name="E(HOMO)")])
    assert match_mixed_history(_execution(), run) == MIXED_UNAPPROVED


def test_choice_map_prefixes_kind_and_keeps_records():
    execution = _execution()
    run = _run()
    choices = history_compare_choice_map([execution, run])
    assert any(label.startswith("Property ·") for label in choices)
    assert any(label.startswith("Quantum ·") for label in choices)
    assert history_compare_label(execution).startswith("Property ·")
    assert history_compare_label(run).startswith("Quantum ·")
    assert list(choices.values()) == [execution, run]


def test_same_kind_helpers_are_unchanged():
    left = _execution(execution_id="a")
    right = _execution(
        execution_id="b",
        producer="other",
        outputs=[_stored(_descriptor(), result_id="other_id", producer="other")],
    )
    assert "different quantities" in property_executions_comparable(left, right)
    from dataclasses import replace

    orca = _run()
    other = replace(orca, provider="psi4", run_id=new_run_id())
    assert "different programs" in quantum_runs_comparable(orca, other)


def _result_store(*records):
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel
    from openchem.domain.project import ProjectModel
    from openchem.events.base import EventBus
    from openchem.services.result_store_service import ResultStoreService

    project = ProjectModel(name="p")
    project.molecules.extend(
        [
            MoleculeModel(uuid="m1", display_name="water"),
            MoleculeModel(uuid="m2", display_name="ethanol"),
        ]
    )
    service = ResultStoreService(EventBus(), ChemistryEngine())
    service.set_project(project)
    for record in records:
        if isinstance(record, PropertyExecution):
            service.property_executions.record(record)
        else:
            service.qc_runs.record(record)
    return service, project


class _CompareHost:
    def __init__(self, packed):
        from types import SimpleNamespace

        from openchem.app.main_window import MainWindow

        service, project = packed
        self._services = SimpleNamespace(result_store_service=service)
        self._session = SimpleNamespace(project=project)
        self.named = []
        self.atoms = []
        self._on_history_compare_requested = MainWindow._on_history_compare_requested.__get__(self)
        self._show_quantum_history_compare = MainWindow._show_quantum_history_compare.__get__(self)
        self._show_ordinary_history_compare = MainWindow._show_ordinary_history_compare.__get__(self)
        self._history_compare_column_label = MainWindow._history_compare_column_label.__get__(self)

    def _history_molecule_name(self, molecule_uuid: str) -> str:
        from openchem.app.main_window import MainWindow

        return MainWindow._history_molecule_name(self, molecule_uuid)

    def _show_named_history_compare(self, rows, left, right) -> None:
        self.named.append((rows, left, right))

    def _show_atom_history_compare(self, outcome, symbols, molecule_uuid) -> None:
        self.atoms.append((outcome, symbols, molecule_uuid))


def test_compare_request_refuses_mixed_without_opening_the_table(qapp, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QInputDialog, QMessageBox

    execution = _execution()
    run = _run()
    host = _CompareHost(_result_store(execution, run))
    messages = []

    def choose(_parent, _title, _label, items, *_args, **_kwargs):
        return next(item for item in items if item.startswith("Quantum ·")), True

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_a, **_k: messages.append(_a[2])))
    host._on_history_compare_requested(
        SimpleNamespace(history_kind="execution", history_id=execution.execution_id)
    )
    assert host.named == []
    assert messages == [MIXED_UNAPPROVED]


def test_mixed_compare_opens_one_named_row_in_both_orientations(qapp, allow, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QInputDialog

    execution = _execution()
    run = _run()
    host = _CompareHost(_result_store(execution, run))

    def choose_quantum(_parent, _title, _label, items, *_args, **_kwargs):
        return next(item for item in items if item.startswith("Quantum ·")), True

    def choose_property(_parent, _title, _label, items, *_args, **_kwargs):
        return next(item for item in items if item.startswith("Property ·")), True

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose_quantum))
    host._on_history_compare_requested(
        SimpleNamespace(history_kind="execution", history_id=execution.execution_id)
    )
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose_property))
    host._on_history_compare_requested(
        SimpleNamespace(history_kind="quantum", history_id=run.run_id)
    )
    assert len(host.named) == 2
    first_rows, first_left, first_right = host.named[0]
    second_rows, second_left, second_right = host.named[1]
    assert first_rows[0].delta == pytest.approx(-0.1)
    assert second_rows[0].delta == pytest.approx(0.1)
    assert isinstance(first_left, PropertyExecution)
    assert isinstance(first_right, QuantumChemistryRun)
    assert isinstance(second_left, QuantumChemistryRun)
    assert isinstance(second_right, PropertyExecution)


def test_ordinary_compare_still_opens_named_table(qapp):
    left = _execution(execution_id="exec-a")
    right = _execution(execution_id="exec-b", outputs=[_stored(_descriptor(value=-0.5))])
    host = _CompareHost(_result_store(left, right))
    host._show_ordinary_history_compare(left, right)
    assert host.atoms == []
    assert len(host.named) == 1
    assert host.named[0][0][0].delta == pytest.approx(-0.2)


def test_quantum_named_compare_still_opens_named_table(qapp):
    left = _run()
    right = _run(descriptors=[_descriptor("orca.homo_energy", -0.5, name="E(HOMO)")])
    host = _CompareHost(_result_store(left, right))
    host._show_quantum_history_compare(left, right)
    assert host.atoms == []
    assert len(host.named) == 1


def test_quantum_nmr_opens_the_per_atom_dialog(qapp):
    from openchem.domain.scientific_result import NMRSpectrumResult

    spectrum_a = NMRSpectrumResult(
        spectrum_type="nmr_13c",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="m1",
        values={0: 120.0},
        elements={0: "C"},
    )
    spectrum_b = NMRSpectrumResult(
        spectrum_type="nmr_13c",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="m1",
        values={0: 118.0},
        elements={0: "C"},
    )
    from dataclasses import replace

    left = _run(calc_type="nmr", extras={"spectrum": spectrum_a})
    right = replace(
        _run(calc_type="nmr", extras={"spectrum": spectrum_b}),
        method_basis="PBE0 def2-SVP",
    )
    host = _CompareHost(_result_store(left, right))
    host._show_quantum_history_compare(left, right)
    assert host.named == []
    assert len(host.atoms) == 1
    assert host.atoms[0][2] == "m1"


def test_cross_molecule_column_labels_name_both_molecules(qapp, monkeypatch):
    from openchem.app.main_window import MainWindow

    execution = _execution(molecule="m1")
    run = _run(molecule="m2")
    host = _CompareHost(_result_store(execution, run))
    left = MainWindow._history_compare_column_label(host, execution, run)
    right = MainWindow._history_compare_column_label(host, run, execution)
    assert "water" in left
    assert "ethanol" in right
    assert "Property ·" in left
    assert "Quantum ·" in right


def test_named_dialog_shows_the_mixed_row(qapp, allow):
    from openchem.ui.dialogs.compare_results_dialog import NamedValueCompareDialog

    match = match_mixed_history(_execution(), _run())
    row = named_row_from_mixed_match(match, ordinary_on_left=True)
    dialog = NamedValueCompareDialog(
        [row],
        "Property · toy · huckel · exec-1",
        "Quantum · sp · orca · B3LYP def2-SVP · abcd1234",
        "water vs ethanol",
    )
    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "HOMO energy"
    assert "Property ·" in dialog._table.horizontalHeaderItem(1).text()
    assert "Quantum ·" in dialog._table.horizontalHeaderItem(2).text()
    assert "water vs ethanol" in dialog.windowTitle()
