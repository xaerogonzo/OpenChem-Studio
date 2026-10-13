"""The Lewis pairing window in the REAL main window: the menu entry, the hand-off to the Quantum Chemistry panel,
the live refresh, and Keep (`docs/RECIPES_DESIGN.md` section 8).

A real `MainWindow`, a real project with borane and carbon monoxide (real RDKit structures, real conformers) and
stored runs carrying the fingerprints the resolver gives today, so 'current' is not asserted but produced. Nothing
starts ORCA.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QAction
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.calculator import GEOMETRY
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
from openchem.events.events import MoleculeSelected, QuantumChemistryRunCompleted
from tests.conftest import dispose
from tests.lewis_helpers import BH3, CO, METHOD, descriptor


@pytest.fixture
def window(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    if built._lewis_pairing is not None:
        dispose(built._lewis_pairing)
    built.close()


def _molecule(engine, smiles: str, name: str) -> MoleculeModel:
    model = MoleculeModel(display_name=name)
    engine.set_structure_from_smiles(model, smiles)
    mol = Chem.AddHs(engine.mol_from_model(model))
    assert AllChem.EmbedMolecule(mol, randomSeed=11) == 0
    model.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol), energy=0.0))
    return model


def _run(window, model: MoleculeModel, run_id: str, calc: str, values: dict, **kw) -> QuantumChemistryRun:
    """A stored run at the molecule's geometry as it is NOW, the way the service records one."""
    store = window._services.result_store_service
    run = QuantumChemistryRun(
        run_id=run_id, molecule_uuid=model.uuid, calc_type=calc, method_basis=METHOD, charge=0, multiplicity=1,
        calculation_input=GEOMETRY, input_fingerprint=store.fingerprints_for(model)[GEOMETRY],
        input_molblock=model.conformers[0].molblock, started_at=1.0, completed_at=2.0, status=RunStatus.COMPLETED, **kw,
    )
    run.results["descriptors"] = [descriptor(model.uuid, k, v) for k, v in values.items()]
    return run


def _store(window, run) -> None:
    window._services.result_store_service.record_quantum_chemistry_run(run)


@pytest.fixture
def pair(window):
    """Borane and carbon monoxide in the open project; carbon monoxide has no delta-SCF run yet."""
    engine = window._services.chemistry_engine
    project = ProjectModel(name="pairing")
    borane, mono = _molecule(engine, "B", "BH3"), _molecule(engine, "[C-]#[O+]", "CO")
    project.molecules.extend([borane, mono])
    window._set_project(project)
    for model, tag, numbers in ((borane, "bh3", BH3), (mono, "co", CO)):
        _store(window, _run(window, model, f"{tag}-sp", "sp", {
            "orca.homo_energy": numbers["homo"], "orca.lumo_energy": numbers["lumo"]}))
    _store(window, _run(window, borane, "bh3-dscf", "delta_scf", {"orca.dscf_hardness": BH3["hardness"]}))
    return project, borane, mono


_KEEP_ALIVE: list = []


def _tools_menu(window):
    [tools] = [a for a in window.menuBar().actions() if a.text().replace("&", "") == "Tools"]
    # PySide deletes the menu when the wrapper of the menu-bar action that owns it is collected.
    _KEEP_ALIVE.append(tools)
    return tools.menu()


def _tools_action(window, text: str) -> QAction:
    # The menu is held by the caller's frame: a temporary wrapper that dies takes the actions' wrappers with it.
    menu = _tools_menu(window)
    [action] = [a for a in menu.actions() if a.text() == text]
    action._menu_alive = menu
    return action


# --- the menu ------------------------------------------------------------------------------------------------------


def test_tools_has_the_pairing_entry_beside_the_goal_wizard(window):
    texts = [a.text() for a in _tools_menu(window).actions()]
    assert "Lewis Acid-Base Pairing..." in texts
    assert abs(texts.index("Lewis Acid-Base Pairing...") - texts.index("Run Calculators by Goal...")) == 1


def test_the_entry_opens_one_window_and_a_second_press_raises_it_rather_than_opening_another(window, pair):
    action = _tools_action(window, "Lewis Acid-Base Pairing...")
    action.trigger()
    first = window._lewis_pairing
    assert first is not None and not first.isHidden()
    action.trigger()
    assert window._lewis_pairing is first


def test_it_opens_on_the_selected_molecule(window, pair):
    _, borane, mono = pair
    window._services.event_bus.publish(MoleculeSelected(molecule_uuid=mono.uuid))
    snapshot = window.show_lewis_pairing().snapshot()
    assert (snapshot["first"], snapshot["second"]) == (mono.uuid, borane.uuid)


def test_with_no_second_molecule_it_opens_and_says_a_pairing_needs_two(window):
    dialog = window.show_lewis_pairing()
    assert "needs two" in dialog.snapshot()["headline"] or dialog.snapshot()["second"] is not None


# --- evaluating the real project -----------------------------------------------------------------------------------


def test_it_evaluates_the_real_projects_stored_runs(window, pair):
    _, borane, mono = pair
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    dialog.set_parameters(role="acid")
    snapshot = dialog.snapshot()
    assert snapshot["status"] == "partial", "carbon monoxide has no delta-SCF run"
    assert any("Frontier orbital gap: 8.13 eV" in line for line in snapshot["result_lines"])
    [todo] = [j for j in snapshot["jobs"] if j["state"] == "blocked"]
    assert todo["step"] == "dscf_second" and "CO has no delta-SCF run" in todo["note"]


def test_the_orca_requirement_reflects_the_real_configuration(window, pair, monkeypatch):
    _, borane, mono = pair
    service = window._services.quantum_chemistry_service
    monkeypatch.setattr(service, "orca_executable", lambda: None)
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    assert any(not j["ready"] for j in dialog.snapshot()["jobs"] if j["state"] == "blocked")
    monkeypatch.setattr(service, "orca_executable", lambda: "C:/orca/orca.exe")
    dialog.refresh()
    [todo] = [j for j in dialog.snapshot()["jobs"] if j["state"] == "blocked"]
    assert todo["ready"]


def test_a_job_says_the_molecules_own_charge_and_whether_it_has_a_conformer(window):
    """Read from the project as it is: a charged molecule runs at its charge, and a molecule with no conformer
    cannot have a job run on it yet."""
    engine = window._services.chemistry_engine
    project = ProjectModel(name="charged")
    ion = _molecule(engine, "C[N+](C)(C)C", "tetramethylammonium")
    flat = MoleculeModel(display_name="flat")
    engine.set_structure_from_smiles(flat, "O")
    project.molecules.extend([ion, flat])
    window._set_project(project)
    dialog = window.show_lewis_pairing(ion.uuid, flat.uuid)
    by_step = {j["step"]: j for j in dialog.snapshot()["jobs"]}
    assert "charge +1" in by_step["sp_first"]["would_run_with"], "the ion's own charge, not zero"
    assert "charge +0" in by_step["sp_second"]["would_run_with"]
    assert by_step["sp_first"]["missing"] == [] or by_step["sp_first"]["missing"] == ["the ORCA executable"]
    assert "a 3D conformer for flat" in by_step["sp_second"]["missing"], "no conformer means the job cannot run yet"
    assert not by_step["sp_second"]["ready"]


# --- the hand-off to the Quantum Chemistry panel -------------------------------------------------------------------


def test_a_jobs_button_opens_the_quantum_chemistry_panel_on_that_molecule_and_calculation_and_level(window, pair):
    from openchem.ui.panels.quantum_chemistry_panel import CALC_TYPE_LABELS

    _, borane, mono = pair
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    dialog.set_parameters(method_basis="PBE0 def2-TZVP", solvent="Water")
    assert dialog.press_job("dscf_second") is True
    dock = window._dock_by_panel_id("Quantum_Chemistry")
    assert dock is not None and not dock.isHidden()
    panel = window._quantum_chemistry_panel
    assert CALC_TYPE_LABELS[panel._calc_type_combo.currentText()] == "delta_scf"
    assert panel._method_combo.currentText() == "PBE0 def2-TZVP" and panel._solvent_combo.currentData() == "Water"
    assert panel._molecule_combo.currentData() == mono.uuid


def test_pressing_a_jobs_button_starts_no_job(window, pair):
    _, borane, mono = pair
    started = []
    service = window._services.quantum_chemistry_service
    for name in ("request_calculation", "request_boltzmann_nmr", "request_reference_calibration"):
        if hasattr(service, name):
            setattr(service, name, lambda *a, _n=name, **k: started.append(_n))
    window.show_lewis_pairing(borane.uuid, mono.uuid).press_job("dscf_second")
    assert started == [], "the button opens a panel; Run there is the person's"


# --- following the project -----------------------------------------------------------------------------------------


def test_a_run_finishing_updates_the_open_window(window, pair):
    _, borane, mono = pair
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    dialog.set_parameters(role="acid")
    assert dialog.snapshot()["status"] == "partial"
    finished = _run(window, mono, "co-dscf", "delta_scf", {"orca.dscf_hardness": CO["hardness"]})
    window._services.event_bus.publish(QuantumChemistryRunCompleted(run=finished))
    snapshot = dialog.snapshot()
    assert snapshot["status"] == "completed" and snapshot["headline"].startswith("Complete.")
    assert any("HSAB hardness match: 1.63 eV" in line for line in snapshot["result_lines"])


def test_editing_a_structure_updates_the_open_window(window, pair):
    from openchem.events.events import MoleculeChanged

    _, borane, mono = pair
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    window._services.chemistry_engine.set_structure_from_smiles(mono, "C=O")
    mono.conformers.clear()
    window._services.event_bus.publish(MoleculeChanged(molecule_uuid=mono.uuid))
    states = {b["state"] for b in dialog.snapshot()["jobs"]}
    assert "blocked" in states and "edited" in " ".join(j["note"] for j in dialog.snapshot()["jobs"])


def test_a_hidden_window_is_not_re_evaluated(window, pair):
    _, borane, mono = pair
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    calls = []
    real = dialog._host.evaluate
    dialog._host.evaluate = lambda *a, **k: calls.append(1) or real(*a, **k)
    dialog.hide()
    window._services.event_bus.publish(
        QuantumChemistryRunCompleted(run=_run(window, mono, "co-dscf", "delta_scf", {"orca.dscf_hardness": 8.4}))
    )
    assert calls == []


def test_opening_a_different_project_refreshes_the_open_window(window, pair):
    _, borane, mono = pair
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    other = ProjectModel(name="other")
    lone = _molecule(window._services.chemistry_engine, "O", "water")
    other.molecules.append(lone)
    window._set_project(other)
    snapshot = dialog.snapshot()
    assert snapshot["first"] == lone.uuid and snapshot["second"] is None
    assert "needs two" in snapshot["headline"]


# --- keeping -------------------------------------------------------------------------------------------------------


def test_keep_files_the_answer_with_the_project_and_marks_it_unsaved(window, pair):
    _, borane, mono = pair
    dialog = window.show_lewis_pairing(borane.uuid, mono.uuid)
    dialog.set_parameters(role="acid")
    window._session.mark_clean()
    shown = dialog._run
    assert dialog.press_keep() is True
    store = window._services.result_store_service
    assert store.recipe_runs.get(shown.run_id) is shown
    assert window._session.is_dirty, "an answer that was never saved would otherwise close without a question"
    assert dialog.snapshot()["kept"]


def test_looking_without_keeping_changes_nothing_in_the_project(window, pair):
    _, borane, mono = pair
    window._session.mark_clean()
    window.show_lewis_pairing(borane.uuid, mono.uuid)
    assert window._services.result_store_service.recipe_runs.all_runs() == [] and not window._session.is_dirty
