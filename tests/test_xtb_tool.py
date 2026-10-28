"""xtb as a tool the user sets up and an engine the panel can choose (`docs/EXTERNAL_TOOL_CANDIDATES.md`): the service resolves its own executable, the External Tools dialog has a locate-only
tab, the Test button checks the energy through the engine's own input and command, and the Quantum Chemistry panel's method box follows the engine.

Most of this needs no xtb: the subprocess calls are replaced. The real program is exercised by `tests/test_xtb_engine.py` and by the last test here, when `OPENCHEM_XTB_EXE` is set.
"""

from __future__ import annotations

import os
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
from openchem.domain.quantum_methods import METHOD_BASIS_PRESETS
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryJobStateChanged
from openchem.services import tool_download_service as tools
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.dialogs.external_tool_catalog import xtb
from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel

import conftest

FIXTURES = Path(__file__).parent / "fixtures" / "xtb"

#: What the real H2 test job prints, cut to what the parser needs: the banner, the energy summary and the last banner (taken from a real run, not invented).
_GOOD_TEST_OUTPUT = (
    "   * xtb version 6.7.1pre (5071a88) compiled by 'Marcel@Raven' on 2024-07-23\n"
    "          | TOTAL ENERGY               -0.981983694722 Eh   |\n"
    " * finished run on 2026/10/27 at 15:00:00.000\n"
)


def _a_file(tmp_path, name: str = "xtb.exe") -> str:
    path = tmp_path / name
    path.write_text("not really", encoding="utf-8")
    return str(path)


def _fake_run(stdout: str, returncode: int = 0):
    def run(*_args, **_kwargs):
        return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)

    return run


# --- the service resolves xtb's own executable ------------------------------------------------------------------------


def test_xtb_resolves_its_own_executable_and_setting_one_engine_does_not_set_another(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    bus = EventBus()
    settings = Settings(bus)
    service = QuantumChemistryService(bus, settings)

    assert [p.provider_id for p in service.available_engines()] == []
    settings.set("xtb/executable_path", _a_file(tmp_path))

    assert service._resolve_executable_path(service._providers["xtb"]) == str(tmp_path / "xtb.exe")
    assert service._resolve_executable_path(service._providers["orca"]) is None
    assert service._resolve_executable_path(service._providers["psi4"]) is None
    assert [p.provider_id for p in service.available_engines()] == ["xtb"]


def test_a_request_for_xtb_without_it_is_refused_in_xtbs_name(monkeypatch, qapp):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    bus = EventBus()
    service = QuantumChemistryService(bus, Settings(bus))
    states: list[tuple[CacheState, str]] = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append((e.state, e.message)))

    service.request_calculation(
        mol=Chem.MolFromSmiles("O"), molecule_uuid="m-1", calc_type="sp", charge=0, multiplicity=1, method_basis="GFN2-xTB", provider_id="xtb",
    )

    assert states == [(CacheState.FAILED, "No xtb executable configured or found on PATH — set xtb/executable_path in Settings.")]


# --- the tool functions ------------------------------------------------------------------------------------------------


def test_the_status_line_does_not_run_anything(tmp_path):
    assert tools.describe_xtb_status("") == "Not configured"
    assert tools.describe_xtb_status(str(tmp_path / "nowhere.exe")).startswith("Configured, but no file at")
    assert tools.describe_xtb_status(_a_file(tmp_path)).startswith("Configured: xtb.exe in ")


@pytest.mark.parametrize(
    "stdout, returncode, expected",
    [
        ("   * xtb version 6.7.1pre (5071a88) compiled by 'Marcel@Raven' on 2024-07-23\n", 0, True),
        ("   * xtb version 6.7.1 (abc) compiled by 'x'\n", 0, True),
        ("Python 3.13.1\n", 0, False),
        ("   * xtb version 6.7.1pre\n", 1, False),
        ("", 0, False),
    ],
)
def test_locate_accepts_only_something_that_answers_like_xtb(monkeypatch, stdout, returncode, expected):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout, returncode))

    assert tools.responds_as_xtb("anything") is expected


def test_locate_rejects_a_program_that_cannot_be_run(monkeypatch):
    def refuse(*_a, **_k):
        raise OSError("not an executable")

    monkeypatch.setattr(subprocess, "run", refuse)

    assert tools.responds_as_xtb("anything") is False
    monkeypatch.undo()
    assert tools.responds_as_xtb(sys.executable) is False  # the real interpreter prints something else for --version


def test_the_test_button_checks_the_energy_and_names_the_version(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(_GOOD_TEST_OUTPUT))

    message = tools.verify_xtb(_a_file(tmp_path))

    assert message.startswith("xtb 6.7.1pre ran a test calculation correctly") and "-0.981984" in message


def test_the_test_button_runs_the_engines_own_command(tmp_path, monkeypatch):
    seen: list[list[str]] = []

    def run(args, **kwargs):
        seen.append(list(args))
        assert Path(args[1]).name == "job.inp" and kwargs["cwd"] == str(Path(args[1]).parent)
        assert Path(args[1]).read_text(encoding="utf-8").startswith("# openchem-xtb charge=0 uhf=0 job=sp gfn=2")
        return SimpleNamespace(stdout=_GOOD_TEST_OUTPUT, stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    tools.verify_xtb(_a_file(tmp_path))

    assert len(seen) == 1 and seen[0][2:8] == ["--gfn", "2", "--chrg", "0", "--uhf", "0"]


@pytest.mark.parametrize(
    "stdout, fragment",
    [
        ("[ERROR] Program stopped due to fatal error\n-1- Error: coordinates not present, cannot work without coordinates\n", "did not give a result"),
        ("   * xtb version 6.7.1pre\n", "did not give a result"),
        (_GOOD_TEST_OUTPUT.replace("-0.981983694722", "-1.200000000000"), "not giving the right answer"),
    ],
)
def test_the_test_button_refuses_an_error_a_missing_energy_and_a_wrong_energy(tmp_path, monkeypatch, stdout, fragment):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout))

    with pytest.raises(tools.ToolVerificationError, match=fragment):
        tools.verify_xtb(_a_file(tmp_path))


def test_the_test_button_refuses_a_path_that_is_not_a_file(tmp_path):
    with pytest.raises(tools.ToolVerificationError, match="No xtb executable"):
        tools.verify_xtb(str(tmp_path / "xtb.exe"))


@pytest.mark.skipif(not os.environ.get("OPENCHEM_XTB_EXE"), reason="set OPENCHEM_XTB_EXE to a real xtb to run this")
def test_a_real_xtb_passes_its_own_locate_and_test():
    path = os.environ["OPENCHEM_XTB_EXE"]

    assert tools.responds_as_xtb(path)
    message = tools.verify_xtb(path)
    assert message.startswith("xtb ") and "ran a test calculation correctly" in message


# --- the External Tools tab --------------------------------------------------------------------------------------------


def test_the_xtb_descriptor_is_locate_only():
    descriptor = xtb()

    assert descriptor.key == "xtb" and descriptor.setting_key == "xtb/executable_path"
    assert descriptor.obtainable is False and descriptor.removable is False
    assert [label for label, _url in descriptor.vendor_links] == ["Get xtb...", "xtb Project Page..."]
    assert descriptor.locate is not None and descriptor.describe_test is tools.verify_xtb


def test_the_dialog_has_an_xtb_tab_with_locate_and_test_and_no_set_up_button(qapp):
    dialog = ExternalToolsPages(Settings(EventBus()))
    try:
        tab = dialog._tab_for("xtb")
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


def _methods(panel) -> list[str]:
    return [panel._method_combo.itemText(i) for i in range(panel._method_combo.count())]


def _calc_items(panel) -> dict[str, bool]:
    model = panel._calc_type_combo.model()
    return {panel._calc_type_combo.itemText(i): model.item(i).isEnabled() for i in range(panel._calc_type_combo.count())}


def _two_engine_panel(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    return _panel({"orca/executable_path": _a_file(tmp_path, "orca.exe"), "xtb/executable_path": _a_file(tmp_path)})


def test_with_xtb_set_up_the_box_offers_it_and_it_runs_only_what_it_runs(tmp_path, monkeypatch, qapp):
    panel, _engine, _service = _two_engine_panel(tmp_path, monkeypatch)
    try:
        assert [panel._engine_combo.itemText(i) for i in range(panel._engine_combo.count())] == ["ORCA", "xtb"]
        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("xtb"))
        items = _calc_items(panel)

        assert {label for label, ok in items.items() if ok} == {"Single Point", "Geometry Optimization", "Optimization + Frequency"}
        assert not items["NMR (raw shielding)"] and not panel._solvent_combo.isEnabled()
        assert panel._correlation_tabs.tabText(panel._correlation_tabs.indexOf(panel._output_log)) == "xtb Log"
        assert panel._configure_button.text() == "Configure xtb..."
    finally:
        conftest.dispose(panel)


def test_the_method_box_follows_the_engine_and_gives_orcas_choices_back(tmp_path, monkeypatch, qapp):
    panel, _engine, _service = _two_engine_panel(tmp_path, monkeypatch)
    try:
        assert _methods(panel) == list(METHOD_BASIS_PRESETS)
        panel._method_combo.setCurrentText("PBE0 def2-TZVP")

        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("xtb"))
        assert _methods(panel) == ["GFN2-xTB", "GFN1-xTB"]
        assert panel._method_combo.currentText() == "GFN2-xTB", "a DFT method is not one xtb has: the box starts from its first choice, not a run that can only fail"

        panel._method_combo.setCurrentText("GFN1-xTB")
        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("orca"))
        assert _methods(panel) == list(METHOD_BASIS_PRESETS)
        assert panel._method_combo.currentText() == METHOD_BASIS_PRESETS[0], "an xtb method means nothing to ORCA"
    finally:
        conftest.dispose(panel)


def test_a_method_typed_by_hand_survives_a_trip_through_an_engine_that_shares_the_list(tmp_path, monkeypatch, qapp):
    """Psi4 offers ORCA's list, so choosing it must not touch the box: what was typed stays."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    panel, _engine, _service = _panel(
        {"orca/executable_path": _a_file(tmp_path, "orca.exe"), "psi4/executable_path": _a_file(tmp_path, "psi4.exe")}
    )
    try:
        panel._method_combo.setCurrentText("HF 6-31G(d)")
        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("psi4"))
        assert panel._method_combo.currentText() == "HF 6-31G(d)" and _methods(panel) == list(METHOD_BASIS_PRESETS)
    finally:
        conftest.dispose(panel)


def test_run_sends_xtb_with_an_xtb_method_and_the_charge_and_spin(tmp_path, monkeypatch, qapp):
    panel, engine, service = _two_engine_panel(tmp_path, monkeypatch)
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

        panel._engine_combo.setCurrentIndex(panel._engine_combo.findData("xtb"))
        panel._on_run_clicked()

        assert len(service.requests) == 1
        request = service.requests[0]
        assert request["provider_id"] == "xtb" and request["method_basis"] == "GFN2-xTB"
        assert (request["charge"], request["multiplicity"]) == (0, 1)
    finally:
        conftest.dispose(panel)
