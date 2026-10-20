"""Generating conformers can also ORCA-optimize the lowest-energy one: the window's checkbox, what it carries, what runs.

The Generate Conformers window gains "Also ORCA-optimize the lowest-energy conformer" (off by default). These pin the
whole route: the checkbox and what it says, the setting it starts from, the flag riding with the set it belongs to,
the choice of WHICH conformer (the lowest force-field energy of the ones just generated, never position and never an
ORCA geometry kept from before), the panel's own Run being the thing that runs, and what the status bar says when it
cannot.
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QDialog

from openchem.app.settings import CONFORMER_OPTIMIZE_LOWEST, PREFERENCES, Settings
from openchem.chem.calculation_input import geometry_fingerprint
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ORCA_OPTIMIZED, ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersReady, QuantumChemistryRunCompleted
from openchem.services.measurement_service import MeasurementService
from openchem.ui.dialogs.conformer_options_dialog import ConformerOptionsDialog, OrcaGenerationOffer
from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget

import conftest
from tests import test_orca_landing_in_slot as landing
from tests.test_quantum_chemistry_panel import _panel_with_conformers


@pytest.fixture(autouse=True)
def _close_landing_windows():
    yield
    while landing._WINDOWS:
        landing._WINDOWS.pop().close()


AVAILABLE = OrcaGenerationOffer(True, "Runs with the Quantum Chemistry panel's settings: HF STO-3G, charge 0, multiplicity 1.")
UNAVAILABLE = OrcaGenerationOffer(False, "ORCA is not set up. Choose its executable in Settings > External Tools to enable this.")


# --- the checkbox in the Generate Conformers window -----------------------------------------------------------------


def test_a_bare_window_offers_nothing_and_asks_for_nothing(qapp):
    dialog = ConformerOptionsDialog()
    try:
        assert dialog._orca_check is None, "no application behind it: nothing it could name, so nothing offered"
        assert dialog.optimize_lowest() is False
    finally:
        conftest.dispose(dialog)


def test_the_box_is_off_until_ticked_and_names_what_would_run(qapp):
    dialog = ConformerOptionsDialog(orca_offer=AVAILABLE)
    try:
        assert dialog._orca_check.isEnabled() and not dialog._orca_check.isChecked()
        assert dialog._orca_note.text() == AVAILABLE.text
        assert dialog.optimize_lowest() is False

        dialog._orca_check.setChecked(True)

        assert dialog.optimize_lowest() is True
    finally:
        conftest.dispose(dialog)


def test_the_setting_decides_where_the_box_starts(qapp):
    dialog = ConformerOptionsDialog(orca_offer=AVAILABLE, optimize_lowest=True)
    try:
        assert dialog._orca_check.isChecked() and dialog.optimize_lowest() is True
        dialog._orca_check.setChecked(False)
        assert dialog.optimize_lowest() is False, "and this generation can still decide otherwise"
    finally:
        conftest.dispose(dialog)


def test_when_orca_cannot_run_the_box_is_greyed_unticked_and_says_why_even_if_the_setting_is_on(qapp):
    dialog = ConformerOptionsDialog(orca_offer=UNAVAILABLE, optimize_lowest=True)
    try:
        assert not dialog._orca_check.isEnabled()
        assert not dialog._orca_check.isChecked(), "a ticked, greyed box would promise what cannot happen"
        assert "not set up" in dialog._orca_note.text()
        assert dialog.optimize_lowest() is False
        dialog._orca_check.setChecked(True)  # what a script or a stray call could do
        assert dialog.optimize_lowest() is False, "an offer that cannot be taken is never taken"
    finally:
        conftest.dispose(dialog)


def test_the_box_carries_the_help_contract_and_says_what_lowest_means(qapp):
    dialog = ConformerOptionsDialog(orca_offer=AVAILABLE)
    try:
        tip = dialog._orca_check.toolTip()
        assert "lowest force-field energy" in tip
        assert "conformers just generated" in tip
        assert "Jobs panel" in tip
    finally:
        conftest.dispose(dialog)


# --- the setting ----------------------------------------------------------------------------------------------------


def test_the_setting_is_off_by_default_and_is_one_of_the_preferences(qapp):
    settings = Settings(EventBus())
    assert CONFORMER_OPTIMIZE_LOWEST in PREFERENCES
    assert settings.preference(CONFORMER_OPTIMIZE_LOWEST) is False


def test_the_settings_page_has_the_checkbox_and_it_stores_the_choice(qapp):
    from openchem.ui.dialogs.settings_dialog import SettingsDialog

    bus = EventBus()
    settings = Settings(bus)
    dialog = SettingsDialog(settings)
    try:
        box = dialog.findChild(type(dialog._conformer_optimize_lowest), "conformerOptimizeLowest")
        assert box is not None and not box.isChecked()

        box.setChecked(True)

        assert settings.preference(CONFORMER_OPTIMIZE_LOWEST) is True
        assert "ORCA" in box.toolTip() and "Off" in box.toolTip()
    finally:
        conftest.dispose(dialog)


# --- the 3D viewer builds the window with the offer and passes the answer on ----------------------------------------


class _RecordingConformerService:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def request_conformers(self, molecule, keep, **kwargs) -> None:
        self.requests.append({"keep": keep, **kwargs})

    def display_molblocks(self, molecule):
        return [c.molblock for c in molecule.conformers]


def _viewer(settings=None, provider=None):
    from tests.test_molecule_viewer3d_widget import FakeViewerBackend

    service = _RecordingConformerService()
    widget = MoleculeViewer3DWidget(
        service, MeasurementService(ChemistryEngine()), EventBus(), backend=FakeViewerBackend(), settings=settings
    )
    if provider is not None:
        widget.set_orca_offer_provider(provider)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [ConformerModel(molblock="fake molblock", method="rdkit")]
    widget.set_molecule(molecule)
    return widget, service, molecule


def test_the_viewer_asks_the_application_what_the_step_would_do_for_the_molecule_on_screen(qapp):
    asked: list[MoleculeModel] = []

    def provider(molecule):
        asked.append(molecule)
        return AVAILABLE

    widget, _service, molecule = _viewer(provider=provider)
    try:
        dialog = widget.options_dialog()
        assert asked == [molecule]
        assert dialog._orca_check is not None and dialog._orca_note.text() == AVAILABLE.text
        conftest.dispose(dialog)
    finally:
        conftest.dispose(widget)


def test_a_viewer_with_no_application_behind_it_offers_nothing(qapp):
    widget, _service, _molecule = _viewer()
    try:
        dialog = widget.options_dialog()
        assert dialog._orca_check is None
        conftest.dispose(dialog)
    finally:
        conftest.dispose(widget)


@pytest.mark.parametrize("starts_on", [False, True])
def test_the_window_starts_where_the_setting_says(qapp, starts_on):
    settings = Settings(EventBus())
    settings.set_preference(CONFORMER_OPTIMIZE_LOWEST, starts_on)
    widget, _service, _molecule = _viewer(settings=settings, provider=lambda _m: AVAILABLE)
    try:
        dialog = widget.options_dialog()
        assert dialog._orca_check.isChecked() is starts_on
        conftest.dispose(dialog)
    finally:
        conftest.dispose(widget)


@pytest.mark.parametrize("ticked", [False, True])
def test_pressing_ok_passes_the_choice_to_the_conformer_request(qapp, monkeypatch, ticked):
    widget, service, _molecule = _viewer(provider=lambda _m: AVAILABLE)

    def accept(self):
        self._orca_check.setChecked(ticked)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ConformerOptionsDialog, "exec", accept)
    try:
        widget.generate_conformers()

        assert service.requests[-1]["optimize_lowest"] is ticked
    finally:
        conftest.dispose(widget)


def test_cancelling_the_window_requests_nothing(qapp, monkeypatch):
    widget, service, _molecule = _viewer(provider=lambda _m: AVAILABLE)
    monkeypatch.setattr(ConformerOptionsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    try:
        widget.generate_conformers()
        assert service.requests == []
    finally:
        conftest.dispose(widget)


# --- the flag rides with the set it belongs to ----------------------------------------------------------------------


def _generate(qapp, **kwargs) -> ConformersReady:
    from PySide6.QtCore import QThreadPool

    from openchem.services.conformer_service import ConformerService

    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    ready: list[ConformersReady] = []
    bus.subscribe(ConformersReady, ready.append)
    service.request_conformers(model, num_conformers=3, optimize=True, **kwargs)
    QThreadPool.globalInstance().waitForDone(10000)
    for _ in range(50):
        qapp.processEvents()
    assert len(ready) == 1
    return ready[0]


def test_the_set_arrives_carrying_the_request_to_optimize_its_lowest(qapp):
    assert _generate(qapp, optimize_lowest=True).optimize_lowest is True


def test_a_set_nobody_asked_to_optimize_arrives_without_the_flag(qapp):
    assert _generate(qapp).optimize_lowest is False
    assert _generate(qapp, optimize_lowest=False).optimize_lowest is False


# --- the panel: what it would run with, and its Run being the thing that runs ----------------------------------------


def test_the_panel_names_the_method_charge_and_multiplicity_run_would_use(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        panel._method_combo.setCurrentText("HF STO-3G")
        panel._multiplicity_spin.setValue(1)

        ok, text = panel.optimization_offer(molecule)

        assert ok
        assert text == "Runs with the Quantum Chemistry panel's settings: HF STO-3G, charge 0, multiplicity 1."
    finally:
        conftest.dispose(panel)


def test_the_charge_shown_is_the_one_run_will_use_for_a_molecule_the_panel_is_not_on_yet(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        other = MoleculeModel(display_name="Ammonium")
        panel._chemistry_engine.set_structure_from_smiles(other, "[NH4+]")
        panel._charge_spin.setValue(-2)  # the box holds the LAST molecule's charge

        _ok, on_the_current = panel.optimization_offer(molecule)
        _ok, on_another = panel.optimization_offer(other)

        assert "charge -2" in on_the_current, "the panel is on it: the box is what Run uses"
        assert "charge 1" in on_another, "moving to another molecule takes its formal charge, so say that one"
    finally:
        conftest.dispose(panel)


def test_with_no_method_there_is_nothing_to_offer(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        panel._method_combo.setCurrentText("")

        ok, text = panel.optimization_offer(molecule)

        assert not ok and "no method and basis" in text
    finally:
        conftest.dispose(panel)


def test_starting_an_optimization_is_the_panels_own_run_on_that_conformer_in_its_slot(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    try:
        target = molecule.conformers[2]

        reason = panel.start_optimization(molecule.uuid, target.conformer_id)

        assert reason == ""
        assert len(service.requests) == 1
        request = service.requests[0]
        assert request["calc_type"] == "opt"
        assert request["input_fingerprint"] == geometry_fingerprint(target)
        assert request["source_slot"] == 3
        assert request["structure_identity"] == molecule.canonical_smiles
        assert panel._calc_type_combo.currentText() == "Geometry Optimization"
    finally:
        conftest.dispose(panel)


def test_averaging_over_the_conformers_does_not_turn_it_into_an_averaged_run(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    try:
        panel._boltzmann_check.setChecked(True)

        reason = panel.start_optimization(molecule.uuid, molecule.conformers[1].conformer_id)

        assert reason == ""
        assert service.boltzmann_requests == [], "an optimization has one conformer, never an average"
        assert len(service.requests) == 1 and service.requests[0]["input_fingerprint"] == geometry_fingerprint(
            molecule.conformers[1]
        )
    finally:
        conftest.dispose(panel)


def test_a_calculation_already_running_in_the_panel_is_not_interrupted(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    try:
        panel._run_button.setEnabled(False)  # exactly what a running job leaves

        reason = panel.start_optimization(molecule.uuid, molecule.conformers[1].conformer_id)

        assert "still running" in reason
        assert service.requests == []
    finally:
        conftest.dispose(panel)


def test_a_conformer_that_is_gone_starts_nothing_and_says_so(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    try:
        reason = panel.start_optimization(molecule.uuid, "gone")

        assert "no longer there" in reason
        assert service.requests == []
    finally:
        conftest.dispose(panel)


def test_what_a_pressed_run_would_refuse_comes_back_as_the_reason(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    try:
        panel._method_combo.setCurrentText("")

        reason = panel.start_optimization(molecule.uuid, molecule.conformers[0].conformer_id)

        assert "method/basis" in reason
        assert service.requests == []
    finally:
        conftest.dispose(panel)


# --- the window: a set arrives with the flag --------------------------------------------------------------------------


def _stand_in_orca(services):
    """Point the panel's "orca" engine at a stand-in process, so the real Run -> job -> landing path runs.

    It sleeps long enough that the SET is observed installed before the geometry lands in it: a shorter job races
    the assertions about what was installed.
    """
    service = services.quantum_chemistry_service
    service.register_provider(landing._optimizing_stand_in(sleep_seconds=1.5))
    service._settings.set("orca/executable_path", sys.executable)
    requests: list[dict] = []
    original = service.request_calculation

    def capture(**kwargs):
        requests.append(kwargs)
        return original(**{**kwargs, "provider_id": "fake_opt"})

    service.request_calculation = capture
    runs: list = []
    services.event_bus.subscribe(QuantumChemistryRunCompleted, lambda event: runs.append(event.run))
    return requests, runs


def _generated(molecule: MoleculeModel, energies: list[float]) -> list[ConformerModel]:
    """A freshly generated set: distinct real geometries, in the order GIVEN (not sorted: position proves nothing)."""
    blocks = [c.molblock for c in molecule.conformers[:3]]
    return [ConformerModel(molblock=blocks[i % 3], energy=e, method="mmff94") for i, e in enumerate(energies)]


def _arrive(qapp, services, molecule, conformers, *, optimize_lowest: bool) -> None:
    services.event_bus.publish(
        ConformersReady(molecule_uuid=molecule.uuid, conformers=conformers, optimize_lowest=optimize_lowest)
    )
    landing._drain(qapp)


def _status(window) -> str:
    return window.statusBar().currentMessage()


def test_the_lowest_energy_conformer_of_the_set_is_optimized_in_its_slot(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    requests, runs = _stand_in_orca(services)
    fresh = _generated(molecule, [3.0, 1.0, 2.0])  # the lowest is NOT the first

    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    assert molecule.conformers == fresh, "the set is installed first, as it always was"
    assert len(requests) == 1
    assert requests[0]["calc_type"] == "opt"
    assert requests[0]["input_fingerprint"] == geometry_fingerprint(fresh[1])
    assert requests[0]["source_slot"] == 2
    assert "ORCA is optimizing conformer 2 of 3, the lowest in energy" in _status(window)

    landing._wait_for_the_run(qapp, runs)

    assert [c.method for c in molecule.conformers] == ["mmff94", ORCA_OPTIMIZED, "mmff94"]
    assert window._viewer3d._conformer_index == 1, "and the viewer lands on it"


def test_without_the_flag_the_set_is_installed_and_nothing_runs(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    requests, _runs = _stand_in_orca(services)
    fresh = _generated(molecule, [3.0, 1.0, 2.0])

    _arrive(qapp, services, molecule, fresh, optimize_lowest=False)

    assert molecule.conformers == fresh
    assert requests == []
    assert "ORCA" not in _status(window)


def test_an_orca_geometry_kept_from_before_is_never_the_candidate(qapp, tmp_path):
    """The kept geometry has no force-field energy and is what `canonical_conformer` prefers: choosing by that
    would optimize the thing already optimized."""
    window, services, molecule, recorder = landing._window_with(qapp, tmp_path)
    requests, runs = _stand_in_orca(services)
    event, _optimized = landing._orca_result(molecule.conformers[landing.SLOT], molecule)
    landing._land(qapp, services, event)
    kept = molecule.conformers[landing.SLOT]
    assert kept.method == ORCA_OPTIMIZED
    fresh = _generated(molecule, [2.0, 3.0, 1.0])

    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    assert molecule.conformers == [*fresh, kept]
    assert requests[0]["input_fingerprint"] == geometry_fingerprint(fresh[2]), "the lowest of the NEW ones"
    assert requests[0]["source_slot"] == 3
    landing._wait_for_the_run(qapp, runs)
    assert [c.method for c in molecule.conformers] == ["mmff94", "mmff94", ORCA_OPTIMIZED, ORCA_OPTIMIZED]
    assert molecule.conformers[-1] is kept, "the earlier one is untouched"


def test_a_tie_takes_the_first_of_them_rather_than_failing(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    requests, runs = _stand_in_orca(services)
    fresh = _generated(molecule, [1.0, 1.0, 2.0])

    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    assert requests[0]["input_fingerprint"] == geometry_fingerprint(fresh[0])
    landing._wait_for_the_run(qapp, runs)


def test_when_orca_is_not_set_up_the_set_is_installed_and_the_status_says_why(qapp, tmp_path, monkeypatch):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    service = services.quantum_chemistry_service
    service._settings.set("orca/executable_path", "")
    monkeypatch.setattr("openchem.services.quantum_chemistry_service.shutil.which", lambda *_a, **_k: None)
    fresh = _generated(molecule, [3.0, 1.0, 2.0])

    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    assert molecule.conformers == fresh, "the conformers were wanted either way"
    assert "was not ORCA-optimized" in _status(window)
    assert "No ORCA executable" in _status(window)


def test_when_the_panel_is_busy_the_set_is_installed_and_the_status_says_why(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    requests, _runs = _stand_in_orca(services)
    window._quantum_chemistry_panel._run_button.setEnabled(False)
    fresh = _generated(molecule, [3.0, 1.0, 2.0])

    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    assert molecule.conformers == fresh
    assert requests == []
    assert "was not ORCA-optimized: another calculation is still running" in _status(window)


def test_a_set_with_no_energies_has_no_lowest_and_says_so(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    requests, _runs = _stand_in_orca(services)
    fresh = _generated(molecule, [3.0, 1.0, 2.0])
    for conformer in fresh:
        conformer.energy = None

    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    assert molecule.conformers == fresh
    assert requests == []
    assert "no lowest one to ORCA-optimize" in _status(window)


def test_a_set_for_a_molecule_that_is_no_longer_selected_installs_nothing_and_starts_nothing(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    requests, _runs = _stand_in_orca(services)
    before = list(molecule.conformers)
    other = MoleculeModel(display_name="Other")
    window.add_molecule(other)
    landing._drain(qapp)
    fresh = _generated(molecule, [3.0, 1.0, 2.0])

    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    assert molecule.conformers == before
    assert requests == []


def test_undoing_the_generation_after_the_job_started_still_lands_the_geometry_safely(qapp, tmp_path):
    """The set is one undo step and the optimization another: the first can be undone while the job runs."""
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    _requests, runs = _stand_in_orca(services)
    fresh = _generated(molecule, [3.0, 1.0, 2.0])
    _arrive(qapp, services, molecule, fresh, optimize_lowest=True)

    window._undo_stack.undo()
    landing._drain(qapp)
    landing._wait_for_the_run(qapp, runs)

    assert sum(c.method == ORCA_OPTIMIZED for c in molecule.conformers) == 1, "appended, never lost or doubled"


# --- the whole route, through the real window and the real service ---------------------------------------------------


def test_ticking_the_box_in_the_real_generate_window_generates_then_optimizes_the_lowest(qapp, tmp_path, monkeypatch):
    window, services = landing._build_window(qapp, tmp_path)
    molecule = MoleculeModel(display_name="Butanol")
    services.chemistry_engine.set_structure_from_smiles(molecule, "CCCCO")
    window.add_molecule(molecule)
    landing._drain(qapp)
    window._viewer3d.set_molecule(molecule)
    requests, runs = _stand_in_orca(services)
    ready: list[ConformersReady] = []
    services.event_bus.subscribe(ConformersReady, ready.append)
    seen: dict = {}

    def accept(self):
        seen["enabled"] = self._orca_check is not None and self._orca_check.isEnabled()
        seen["note"] = self._orca_note.text()
        self._advanced.setChecked(True)
        self._embeddings_spin.setValue(40)
        self._orca_check.setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ConformerOptionsDialog, "exec", accept)

    window._viewer3d.generate_conformers()
    import time

    deadline = time.time() + 60
    while time.time() < deadline and not runs:
        qapp.processEvents()
        time.sleep(0.02)
    assert runs, "the optimization never finished"
    landing._drain(qapp)

    assert seen["enabled"], "the window offered the step, with ORCA set up"
    assert "Runs with the Quantum Chemistry panel's settings" in seen["note"]
    assert len(ready) == 1 and ready[0].optimize_lowest is True
    generated = ready[0].conformers
    lowest = min(range(len(generated)), key=lambda i: generated[i].energy)
    assert len(requests) == 1
    assert requests[0]["input_fingerprint"] == geometry_fingerprint(generated[lowest])
    assert requests[0]["source_slot"] == lowest + 1
    methods = [c.method for c in molecule.conformers]
    assert methods.count(ORCA_OPTIMIZED) == 1
    assert methods.index(ORCA_OPTIMIZED) == lowest, "it replaced the lowest where it stood"


def test_the_application_window_describes_the_step_from_the_orca_install_and_the_panel(qapp, tmp_path, monkeypatch):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    service = services.quantum_chemistry_service
    service._settings.set("orca/executable_path", "")
    monkeypatch.setattr("openchem.services.quantum_chemistry_service.shutil.which", lambda *_a, **_k: None)

    without = window._orca_generation_offer(molecule)

    assert not without.available and "not set up" in without.text

    service._settings.set("orca/executable_path", sys.executable)
    window._quantum_chemistry_panel._method_combo.setCurrentText("HF STO-3G")
    with_orca = window._orca_generation_offer(molecule)

    assert with_orca.available and "HF STO-3G" in with_orca.text
    assert not window._orca_generation_offer(None).available
