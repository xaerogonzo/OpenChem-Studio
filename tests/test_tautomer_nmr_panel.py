"""The Quantum Chemistry panel's tautomer NMR controls (P5, step 4): starting the run and showing the result.

The service is a recording double (what the panel hands it is the contract); the tautomer fixtures are the real
keto and enol structures of the averaging tests, so the stored geometries and populations are real data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

sys.path.insert(0, str(Path(__file__).parent))
from test_quantum_chemistry_panel import (  # noqa: E402
    _cyclohexanone_molecule,
    _dispose_panel,
    _panel_with_a_store,
    _RecordingQuantumChemistryService,
    _tautomer_distribution_run,
)
from test_tautomer_nmr_average import PARENT, _build  # noqa: E402

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryRunCompleted, TautomerNmrResultReady
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel


class _Service(_RecordingQuantumChemistryService):
    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.tautomer_nmr_requests: list[dict] = []

    def request_tautomer_nmr(self, **kwargs) -> None:  # noqa: D102 - test double
        self.tautomer_nmr_requests.append(kwargs)


@pytest.fixture
def setup(qapp):
    """A panel with a result store, a distribution run holding validated populations and stored geometries, and
    that run selected."""
    from openchem.services.result_store_service import ResultStoreService

    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    store = ResultStoreService(bus, engine, settings)
    service = _Service(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus, result_store_service=store)
    from openchem.domain.project import ProjectModel

    project = ProjectModel(name="T")
    molecule = _cyclohexanone_molecule(engine)
    project.molecules.append(molecule)
    store.set_project(project)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    nmr, distribution, _ = _build()
    run = _tautomer_distribution_run(molecule.uuid, distribution)
    run.run_id = PARENT
    bus.publish(QuantumChemistryRunCompleted(run=run))
    qapp.processEvents()
    panel._method_combo.setCurrentText("HF STO-3G")
    yield panel, bus, service, molecule, run, nmr, distribution
    _dispose_panel(panel)


def _nmr_run(molecule, nmr):
    run = QuantumChemistryRun(
        run_id="nmr-run", molecule_uuid=molecule.uuid, calc_type="tautomer_nmr", method_basis=nmr.method_basis,
        charge=0, multiplicity=1, calculation_input="", input_fingerprint="", input_molblock="",
        status=RunStatus.COMPLETED,
    )
    run.results["tautomer_nmr"] = nmr
    run.output_status["tautomer_nmr"] = OutputStatus.AVAILABLE
    return run


def _answer(monkeypatch, button):
    asked = []

    def question(_parent, title, text, *_a, **_k):
        asked.append((title, text))
        return button

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


def test_the_run_button_needs_a_selected_distribution_with_stored_geometries(setup, qapp):
    panel, bus, _service, molecule, run, _nmr, _distribution = setup
    assert panel._tautomer_nmr_button.isEnabled() is True
    assert panel._view_tautomer_nmr_button.isEnabled() is False
    # A distribution computed before geometries were kept has nothing to run NMR from.
    from test_quantum_chemistry_panel import _fake_tautomer_distribution_result

    old = _tautomer_distribution_run(molecule.uuid, _fake_tautomer_distribution_result(molecule.uuid))
    old.run_id = "old"
    panel._render_run(old)
    assert panel._tautomer_nmr_button.isEnabled() is False
    panel._render_run(run)
    assert panel._tautomer_nmr_button.isEnabled() is True


def test_confirming_hands_the_service_the_tautomers_the_method_and_the_parent_run(setup, monkeypatch):
    panel, _bus, service, molecule, run, _nmr, distribution = setup
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    panel._on_tautomer_nmr_clicked()
    (request,) = service.tautomer_nmr_requests
    assert request["molecule_uuid"] == molecule.uuid and request["method_basis"] == "HF STO-3G"
    assert request["parent_run_id"] == PARENT and request["per_conformer"] is False
    assert [t.label for t in request["targets"]] and len(request["targets"]) == 2
    assert all(len(t.jobs) == 1 for t in request["targets"])
    title, text = asked[0]
    assert "2 real ORCA NMR calculation(s) for 2 tautomer(s)" in text and "HF STO-3G" in text
    assert panel._tautomer_nmr_button.isEnabled() is False  # a job is running


def test_declining_runs_nothing(setup, monkeypatch):
    panel, _bus, service, *_ = setup
    _answer(monkeypatch, QMessageBox.StandardButton.No)
    panel._on_tautomer_nmr_clicked()
    assert service.tautomer_nmr_requests == [] and panel._tautomer_nmr_button.isEnabled() is True


def test_the_conformer_option_is_remembered_and_changes_the_request(setup, monkeypatch):
    panel, _bus, service, *_ = setup
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    panel._tautomer_nmr_conformers_check.setChecked(True)
    assert str(panel._settings.get("tautomer/nmr_average_conformers", False)).lower() == "true"
    panel._on_tautomer_nmr_clicked()
    assert service.tautomer_nmr_requests[0]["per_conformer"] is True


def test_a_tautomer_that_cannot_be_run_is_named_in_the_question_and_passed_on(setup, monkeypatch):
    panel, _bus, service, molecule, run, _nmr, distribution = setup
    import dataclasses

    entries = list(distribution.entries)
    metadata = {k: v for k, v in entries[1].metadata.items() if k != "optimized_molblock"}
    entries[1] = dataclasses.replace(entries[1], metadata=metadata)
    run.results["tautomer_distribution"] = dataclasses.replace(distribution, entries=entries)
    panel._render_run(run)
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    panel._on_tautomer_nmr_clicked()
    (request,) = service.tautomer_nmr_requests
    assert len(request["targets"]) == 1 and len(request["skipped"]) == 1
    assert "Left out" in asked[0][1] and "not stored" in asked[0][1]


def test_a_live_result_is_shown_with_the_distribution_the_run_started_from(setup, monkeypatch):
    panel, bus, _service, molecule, run, nmr, distribution = setup
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    panel._on_tautomer_nmr_clicked()
    shown = []
    panel._show_tautomer_nmr = lambda r, d: shown.append((r, d))
    bus.publish(TautomerNmrResultReady(molecule_uuid=molecule.uuid, run_id="nmr-run", result=nmr))
    assert shown == [(nmr, distribution)]
    assert "Tautomer NMR at" in panel._results_label.text() and "2/2" in panel._results_label.text()


def test_a_result_for_another_molecule_is_ignored(setup, monkeypatch):
    panel, bus, _service, _molecule, _run, nmr, _distribution = setup
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    panel._on_tautomer_nmr_clicked()  # a run is pending, so a wrongly accepted result WOULD be shown
    shown = []
    panel._show_tautomer_nmr = lambda r, d: shown.append(r)
    bus.publish(TautomerNmrResultReady(molecule_uuid="someone-else", run_id="x", result=nmr))
    assert shown == []


def test_a_stored_tautomer_nmr_run_is_viewable_and_finds_its_distribution_by_run_id(setup):
    panel, bus, _service, molecule, run, nmr, distribution = setup
    bus.publish(QuantumChemistryRunCompleted(run=_nmr_run(molecule, nmr)))
    assert panel._runs_combo.currentText().startswith("Tautomer NMR ·")
    assert panel._view_tautomer_nmr_button.isEnabled() is True
    shown = []
    panel._show_tautomer_nmr = lambda r, d: shown.append((r, d))
    panel._on_view_tautomer_nmr_clicked()
    assert shown == [(nmr, distribution)]


def test_viewing_says_so_when_the_distribution_is_gone(setup):
    panel, bus, _service, molecule, run, nmr, _distribution = setup
    import dataclasses

    orphan = dataclasses.replace(nmr, parent_run_id="a-run-that-was-deleted")
    bus.publish(QuantumChemistryRunCompleted(run=_nmr_run(molecule, orphan)))
    shown = []
    panel._show_tautomer_nmr = lambda r, d: shown.append(r)
    panel._on_view_tautomer_nmr_clicked()
    assert shown == [] and "no longer in this project" in panel._status_label.text()


def test_with_no_spectrum_of_its_own_the_peaks_open_in_their_own_window(setup, qapp):
    from openchem.ui.widgets.nmr_spectrum_widget import NmrSpectrumWidget

    panel, _bus, _service, molecule, run, nmr, distribution = setup
    panel._show_tautomer_nmr(nmr, distribution)
    window = panel._tautomer_nmr_window
    spectrum = window.findChild(NmrSpectrumWidget)
    assert [t.is_average for t in spectrum.tautomer_traces()] == [False, False, True]
    assert len(spectrum.drawn_tautomer_traces()) == 3
    window.close()


def test_the_window_switches_nucleus_and_the_axis_follows(setup, qapp):
    from PySide6.QtWidgets import QComboBox

    from openchem.ui.widgets.nmr_spectrum_widget import NmrSpectrumWidget

    panel, _bus, _service, _molecule, _run, nmr, distribution = setup
    panel._show_tautomer_nmr(nmr, distribution)
    window = panel._tautomer_nmr_window
    spectrum = window.findChild(NmrSpectrumWidget)
    combo = window.findChild(QComboBox)
    assert [combo.itemData(i) for i in range(combo.count())] == ["H", "C"]
    combo.setCurrentIndex(combo.findData("H"))
    assert spectrum.view_range()[1] < 30  # proton shifts
    combo.setCurrentIndex(combo.findData("C"))
    assert spectrum.view_range()[1] > 90  # carbon shifts
    window.close()
