"""Psi4 as a tool the user sets up and an engine the panel can choose (`docs/PSI4_ENGINE_DESIGN.md`, stage 1): the service resolves each engine's own executable, the External Tools
dialog has a locate-only tab, the Test button checks the energy, and the Quantum Chemistry panel shows an Engine box only when there is a choice.

Nothing here needs Psi4: the subprocess calls are replaced. The real program is exercised by `tests/test_psi4_engine.py` (when `OPENCHEM_PSI4_EXE` is set).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryJobStateChanged
from openchem.services import tool_download_service as tools
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.dialogs.external_tool_catalog import psi4
from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel

import conftest

_GOOD_TEST_OUTPUT = (
    "                               Psi4 1.11 release\n"
    "    Total Energy =                        -1.1167830000000000\n"
    "*** Psi4 exiting successfully. Buy a developer a beer!\n"
)


def _a_file(tmp_path, name: str = "psi4.exe") -> str:
    path = tmp_path / name
    path.write_text("not really", encoding="utf-8")
    return str(path)


def _fake_run(stdout: str, returncode: int = 0):
    def run(*_args, **_kwargs):
        return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)

    return run


# --- the service resolves each engine's own executable ----------------------------------------------------------------


def test_each_engine_resolves_its_own_executable_and_orca_keeps_its_setting(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    bus = EventBus()
    settings = Settings(bus)
    service = QuantumChemistryService(bus, settings)
    psi4_provider = service._providers["psi4"]
    orca_provider = service._providers["orca"]

    assert service._resolve_executable_path(psi4_provider) is None and service._resolve_executable_path(orca_provider) is None
    settings.set("psi4/executable_path", _a_file(tmp_path, "psi4.exe"))

    assert service._resolve_executable_path(psi4_provider) == str(tmp_path / "psi4.exe")
    assert service._resolve_executable_path(orca_provider) is None  # setting one engine does not set the other
    assert [p.provider_id for p in service.available_engines()] == ["psi4"]
    settings.set("orca/executable_path", _a_file(tmp_path, "orca.exe"))
    assert [p.provider_id for p in service.available_engines()] == ["orca", "psi4"]
    assert [p.provider_id for p in service.engines()] == ["orca", "psi4"]
    # the public ORCA accessor is unchanged
    assert service.orca_executable() == str(tmp_path / "orca.exe")


def test_a_request_for_psi4_without_it_is_refused_in_psi4s_name(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    bus = EventBus()
    service = QuantumChemistryService(bus, Settings(bus))
    states: list[tuple[CacheState, str]] = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append((e.state, e.message)))

    service.request_calculation(
        mol=Chem.MolFromSmiles("O"), molecule_uuid="m-1", calc_type="sp", charge=0, multiplicity=1, method_basis="B3LYP def2-SVP", provider_id="psi4",
    )

    assert states == [(CacheState.FAILED, "No Psi4 executable configured or found on PATH — set psi4/executable_path in Settings.")]


# --- the tool functions ------------------------------------------------------------------------------------------------


def test_the_status_line_does_not_run_anything(tmp_path):
    assert tools.describe_psi4_status("") == "Not configured"
    assert tools.describe_psi4_status(str(tmp_path / "nowhere.exe")).startswith("Configured, but no file at")
    assert tools.describe_psi4_status(_a_file(tmp_path)).startswith("Configured: psi4.exe in ")


@pytest.mark.parametrize(
    "stdout, returncode, expected",
    [("1.11\n", 0, True), ("1.11.2\n", 0, True), ("Python 3.13.1\n", 0, False), ("1.11\n", 1, False), ("", 0, False), ("psi4 1.11 extra words\n", 0, False)],
)
def test_locate_accepts_only_something_that_answers_like_psi4(monkeypatch, stdout, returncode, expected):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout, returncode))

    assert tools.responds_as_psi4("anything") is expected


def test_locate_rejects_a_program_that_cannot_be_run(monkeypatch):
    def refuse(*_a, **_k):
        raise OSError("not an executable")

    monkeypatch.setattr(subprocess, "run", refuse)

    assert tools.responds_as_psi4("anything") is False
    # and the real interpreter, which prints something else for --version, is not Psi4
    monkeypatch.undo()
    assert tools.responds_as_psi4(sys.executable) is False


def test_the_test_button_checks_the_energy_and_names_the_version(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(_GOOD_TEST_OUTPUT))

    message = tools.verify_psi4(_a_file(tmp_path))

    assert message.startswith("Psi4 1.11 ran a test calculation correctly") and "-1.116783" in message


@pytest.mark.parametrize(
    "stdout, fragment",
    [
        ("Psi4 1.11 release\n!  Method=x is not available  !\n*** Psi4 encountered an error. Buy a developer more coffee!\n", "reported an error"),
        ("Psi4 1.11 release\nno energy here\n", "produced no energy"),
        ("Psi4 1.11 release\n    Total Energy =  -1.2000000000000000\n", "not giving the right answer"),
    ],
)
def test_the_test_button_refuses_an_error_a_missing_energy_and_a_wrong_energy(tmp_path, monkeypatch, stdout, fragment):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout))

    with pytest.raises(tools.ToolVerificationError, match=fragment):
        tools.verify_psi4(_a_file(tmp_path))


def test_the_test_button_refuses_a_path_that_is_not_a_file(tmp_path):
    with pytest.raises(tools.ToolVerificationError, match="No Psi4 executable"):
        tools.verify_psi4(str(tmp_path / "psi4.exe"))


# --- the External Tools tab --------------------------------------------------------------------------------------------


def test_the_psi4_descriptor_is_locate_only():
    descriptor = psi4()

    assert descriptor.key == "psi4" and descriptor.setting_key == "psi4/executable_path"
    # Alex, 2026-10-19: locate-only. No download, and nothing to remove from disk (this app never installed it).
    assert descriptor.obtainable is False and descriptor.removable is False
    assert [label for label, _url in descriptor.vendor_links] == ["Get Psi4...", "Psi4 Documentation..."]
    assert descriptor.locate is not None and descriptor.describe_test is tools.verify_psi4


def test_the_dialog_has_a_psi4_tab_with_locate_and_test_and_no_set_up_button(qapp):
    dialog = ExternalToolsPages(Settings(EventBus()))
    try:
        tab = dialog._tab_for("psi4")
        assert tab.locate_button is not None and tab.test_button is not None
        assert tab.setup_button.isHidden() and tab.remove_button.isHidden()
        assert tab.status_label.text() == "Not configured" or tab.status_label.text().startswith("Configured")
    finally:
        conftest.dispose(dialog)


# --- the panel ---------------------------------------------------------------------------------------------------------


class _RecordingService(QuantumChemistryService):
    def __init__(self, bus: EventBus, settings: Settings) -> None:
        super().__init__(bus, settings)
        self.requests: list[dict] = []

    def request_calculation(self, **kwargs) -> None:
        self.requests.append(kwargs)


def _panel(settings_values: dict[str, str]):
    bus = EventBus()
    settings = Settings(bus)
    for key, value in settings_values.items():
        settings.set(key, value)
    service = _RecordingService(bus, settings)
    engine = ChemistryEngine()
    return QuantumChemistryPanel(service, engine, settings, bus), engine, service


def _calc_items(panel) -> dict[str, bool]:
    model = panel._calc_type_combo.model()
    return {panel._calc_type_combo.itemText(i): model.item(i).isEnabled() for i in range(panel._calc_type_combo.count())}


def test_the_engine_box_is_hidden_when_orca_is_the_only_engine(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    panel, _engine, _service = _panel({"orca/executable_path": _a_file(tmp_path, "orca.exe")})
    try:
        assert panel._engine_combo.count() == 1 and panel._selected_engine_id() == "orca"
        assert not panel._run_form.isRowVisible(panel._engine_combo)
        assert all(_calc_items(panel).values())  # every calculation stays offered
        assert panel._correlation_tabs.tabText(panel._correlation_tabs.indexOf(panel._output_log)) == "ORCA Log"
    finally:
        conftest.dispose(panel)


def test_with_psi4_set_up_the_box_appears_and_choosing_it_greys_out_what_it_does_not_run(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    panel, _engine, _service = _panel({"orca/executable_path": _a_file(tmp_path, "orca.exe"), "psi4/executable_path": _a_file(tmp_path, "psi4.exe")})
    try:
        assert panel._engine_combo.count() == 2 and panel._run_form.isRowVisible(panel._engine_combo)
        assert [panel._engine_combo.itemText(i) for i in range(2)] == ["ORCA", "Psi4"]

        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("psi4"))
        items = _calc_items(panel)

        assert panel._selected_engine_id() == "psi4"
        enabled = {label for label, ok in items.items() if ok}
        assert enabled and any("single point" in label.lower() for label in enabled)
        assert not items["NMR (raw shielding)"]  # ORCA's
        assert not panel._solvent_combo.isEnabled() and not panel._boltzmann_check.isEnabled()
        assert panel._correlation_tabs.tabText(panel._correlation_tabs.indexOf(panel._output_log)) == "Psi4 Log"

        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("orca"))
        assert all(_calc_items(panel).values()) and panel._solvent_combo.isEnabled()
    finally:
        conftest.dispose(panel)


def test_run_sends_the_chosen_engine_with_the_request(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    panel, engine, service = _panel({"orca/executable_path": _a_file(tmp_path, "orca.exe"), "psi4/executable_path": _a_file(tmp_path, "psi4.exe")})
    try:
        molecule = MoleculeModel(display_name="Water")
        engine.set_structure_from_smiles(molecule, "O")
        mol_3d = Chem.AddHs(Chem.MolFromSmiles("O"))
        AllChem.EmbedMolecule(mol_3d, randomSeed=42)
        molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))
        project = ProjectModel(name="Test")
        project.molecules.append(molecule)
        panel.set_project(project)
        panel._molecule_combo.setCurrentIndex(0)
        panel._method_combo.setCurrentText("B3LYP def2-SVP")

        panel._on_run_clicked()
        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("psi4"))
        panel._run_button.setEnabled(True)
        panel._on_run_clicked()

        assert [request["provider_id"] for request in service.requests] == ["orca", "psi4"]
    finally:
        conftest.dispose(panel)


def test_a_panel_over_a_service_with_no_engines_behaves_as_orca_alone(qapp):
    """The tests' recording services are built with `providers={}`: no engine listing at all must read as ORCA, with the form unchanged."""
    from test_quantum_chemistry_panel import _dispose_panel, _make_panel

    panel, _engine, _service = _make_panel()
    try:
        assert panel._selected_engine_id() == "orca"
        assert not panel._run_form.isRowVisible(panel._engine_combo)
        assert all(_calc_items(panel).values())
    finally:
        _dispose_panel(panel)


# --- the ORCA-only controls say so while Psi4 is chosen -----------------------------------------------------------------------


def _two_engine_panel(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    return _panel({"orca/executable_path": _a_file(tmp_path, "orca.exe"), "psi4/executable_path": _a_file(tmp_path, "psi4.exe")})


def _orca_only(panel):
    return [widget for widget, _key in panel._orca_only_controls()]


def test_choosing_psi4_disables_what_would_start_an_orca_job_and_names_the_reason(tmp_path, monkeypatch, qapp):
    """The tautomer, proton-affinity and calibration buttons always run ORCA. With Psi4 in the Engine box and its log tab, they must not be offered."""
    panel, _engine, _service = _two_engine_panel(tmp_path, monkeypatch)
    try:
        before = {widget: widget.toolTip() for widget in _orca_only(panel)}
        assert len(before) == 7 and all(widget.isEnabled() for widget in _orca_only(panel) if widget is not panel._tautomer_nmr_button)

        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("psi4"))

        for widget in _orca_only(panel):
            assert not widget.isEnabled()
            assert "ORCA only" in widget.toolTip() and "Psi4" in widget.toolTip()
        assert panel._configure_button.text() == "Configure Psi4..." and "Psi4" in panel._configure_button.toolTip()

        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("orca"))
        for widget in _orca_only(panel):
            assert widget.toolTip() == before[widget], "ORCA's help contract comes back word for word"
        assert panel._tautomer_distribution_button.isEnabled() and panel._proton_affinity_button.isEnabled()
        assert panel._calibrate_button.isEnabled() and panel._scaling_button.isEnabled()
        assert panel._tautomer_full_check.isEnabled() and panel._tautomer_nmr_conformers_check.isEnabled()
        assert panel._configure_button.text() == "Configure ORCA..."
    finally:
        conftest.dispose(panel)


def test_a_job_finishing_while_psi4_is_chosen_cannot_switch_an_orca_button_back_on(tmp_path, monkeypatch, qapp):
    """`_on_job_state_changed` and the calibration handlers enable these buttons when work ends. The choice of engine wins; what they wanted is kept for ORCA."""
    panel, _engine, _service = _two_engine_panel(tmp_path, monkeypatch)
    try:
        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("psi4"))

        panel._set_orca_only_enabled(panel._tautomer_distribution_button, True)
        panel._set_orca_only_enabled(panel._calibrate_button, True)
        panel._set_orca_only_enabled(panel._proton_affinity_button, False)  # busy: it wanted to be off

        assert not panel._tautomer_distribution_button.isEnabled() and not panel._calibrate_button.isEnabled()
        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("orca"))
        assert panel._tautomer_distribution_button.isEnabled() and panel._calibrate_button.isEnabled()
        assert not panel._proton_affinity_button.isEnabled(), "a button that was busy stays off when ORCA is chosen again"
    finally:
        conftest.dispose(panel)


def test_configure_opens_the_tab_of_the_engine_chosen(tmp_path, monkeypatch, qapp):
    from openchem.ui.panels import quantum_chemistry_panel as panel_module

    opened = []

    class _Dialog:
        def __init__(self, _settings, _parent=None, **kwargs):
            opened.append(kwargs)

        def exec(self):
            return 0

    monkeypatch.setattr(panel_module, "SettingsDialog", _Dialog)
    panel, _engine, _service = _two_engine_panel(tmp_path, monkeypatch)
    try:
        panel._on_configure_clicked()
        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("psi4"))
        panel._on_configure_clicked()

        assert [kwargs["tool"] for kwargs in opened] == ["orca", "psi4"]
    finally:
        conftest.dispose(panel)


def test_with_orca_alone_nothing_about_these_controls_changes(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    panel, _engine, _service = _panel({"orca/executable_path": _a_file(tmp_path, "orca.exe")})
    try:
        assert panel._configure_button.text() == "Configure ORCA..."
        assert all("ORCA only" not in widget.toolTip() for widget in _orca_only(panel))
        assert panel._tautomer_distribution_button.isEnabled() and panel._calibrate_button.isEnabled()
    finally:
        conftest.dispose(panel)


# --- a Psi4 geometry is labelled as Psi4's wherever a conformer is named ------------------------------------------------


def _psi4_conformer(level: str = "B3LYP def2-SVP", molblock: str = "psi4") -> ConformerModel:
    from openchem.domain.common import RUN_METHOD_BASIS, Provenance
    from openchem.domain.conformer import PSI4_OPTIMIZED

    provenance = Provenance(created_by="core", method="psi4", parameters={RUN_METHOD_BASIS: level})
    return ConformerModel(molblock=molblock, method=PSI4_OPTIMIZED, provenance=provenance)


def test_the_project_list_badge_names_the_engine_and_a_rename_strips_it(qapp):
    from PySide6.QtGui import QUndoStack

    from openchem.ui.panels.project_explorer_panel import ProjectExplorerPanel

    forcefield = [ConformerModel(molblock="ff", energy=0.0, method="mmff94")]
    orca_geometry = ConformerModel(molblock="o", method="orca_opt")
    molecules = [
        MoleculeModel(display_name="Plain", conformers=list(forcefield)),
        MoleculeModel(display_name="FromPsi4", conformers=[*forcefield, _psi4_conformer()]),
        MoleculeModel(display_name="FromOrca", conformers=[*forcefield, orca_geometry]),
        MoleculeModel(display_name="FromBoth", conformers=[*forcefield, orca_geometry, _psi4_conformer()]),
    ]
    panel = ProjectExplorerPanel(EventBus(), QUndoStack())
    panel.set_project(ProjectModel(name="P", molecules=molecules))
    try:
        assert [panel._list.item(i).text() for i in range(4)] == [
            "Plain", "FromPsi4  [Psi4-optimized]", "FromOrca  [ORCA-optimized]", "FromBoth  [quantum-optimized]",
        ]
    finally:
        conftest.dispose(panel)


def test_the_viewer_says_psi4_for_a_psi4_geometry_in_the_label_the_cell_and_the_tooltip(qapp):
    from tests.test_molecule_viewer3d_widget import _gallery_widget

    widget, _backend, molecule = _gallery_widget(None, count=3)
    try:
        molecule.conformers[1] = _psi4_conformer()

        assert widget._cell_label(1) == "2 - Psi4"
        assert "Optimized with Psi4 at B3LYP def2-SVP" in widget._conformer_tooltip(molecule.conformers[1])
    finally:
        conftest.dispose(widget)
