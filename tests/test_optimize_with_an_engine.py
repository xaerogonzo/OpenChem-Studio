"""Optimizing a conformer with a chosen engine: the service's list of choices, the panel selecting the engine, and the viewer's menu."""

from __future__ import annotations

from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.optimize_choice import OptimizeChoice
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel

import conftest


def _file(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_text("not really", encoding="utf-8")
    return str(path)


def _panel(tmp_path, monkeypatch, *, with_xtb: bool):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", _file(tmp_path, "orca.exe"))
    if with_xtb:
        settings.set("xtb/executable_path", _file(tmp_path, "xtb.exe"))
    service = QuantumChemistryService(bus, settings)
    engine = ChemistryEngine()
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    molecule = MoleculeModel(display_name="Water")
    engine.set_structure_from_smiles(molecule, "O")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=42)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    return panel, service, molecule


# -- the service ---------------------------------------------------------------------------------------------------


def test_the_service_lists_every_engine_that_can_optimize_with_whether_it_is_set_up(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", _file(tmp_path, "orca.exe"))
    settings.set("xtb/executable_path", _file(tmp_path, "xtb.exe"))
    choices = {c.provider_id: c for c in QuantumChemistryService(bus, settings).optimization_choices()}
    assert choices["orca"].available and choices["xtb"].available and choices["orca"].reason == ""
    assert not choices["psi4"].available and "not set up" in choices["psi4"].reason and "Settings" in choices["psi4"].reason


# -- the panel -----------------------------------------------------------------------------------------------------


def test_prepare_optimization_selects_the_engine_asked_for(tmp_path, monkeypatch, qapp):
    panel, _service, molecule = _panel(tmp_path, monkeypatch, with_xtb=True)
    try:
        conformer_id = molecule.conformers[0].conformer_id
        assert panel.prepare_optimization(molecule.uuid, conformer_id, "xtb")
        assert panel._selected_engine_id() == "xtb" and "with xtb" in panel._status_label.text()
        # The ORCA door puts the panel back on ORCA: it used to leave it on xtb, so "ORCA optimize" ran xtb.
        assert panel.prepare_optimization(molecule.uuid, conformer_id)
        assert panel._selected_engine_id() == "orca" and "with ORCA" in panel._status_label.text()
    finally:
        conftest.dispose(panel)


def test_an_engine_that_is_not_set_up_is_refused_with_the_reason_and_nothing_changes(tmp_path, monkeypatch, qapp):
    panel, _service, molecule = _panel(tmp_path, monkeypatch, with_xtb=False)
    try:
        before = panel._status_label.text()
        assert not panel.prepare_optimization(molecule.uuid, molecule.conformers[0].conformer_id, "xtb")
        assert "xtb is not set up" in panel.optimization_refusal and "Settings" in panel.optimization_refusal
        assert panel._selected_engine_id() == "orca" and panel._status_label.text() == before
    finally:
        conftest.dispose(panel)


def test_a_vanished_conformer_is_refused_with_its_own_reason(tmp_path, monkeypatch, qapp):
    panel, _service, molecule = _panel(tmp_path, monkeypatch, with_xtb=True)
    try:
        assert not panel.prepare_optimization(molecule.uuid, "gone", "xtb")
        assert "no longer there" in panel.optimization_refusal
        assert panel.prepare_optimization(molecule.uuid, molecule.conformers[0].conformer_id, "xtb")
        assert panel.optimization_refusal == ""
    finally:
        conftest.dispose(panel)


# -- the viewer's menu ---------------------------------------------------------------------------------------------


def test_the_viewers_engine_menu_lists_the_other_engines_and_greys_one_that_is_not_set_up(qapp):
    from tests.test_molecule_viewer3d_widget import _gallery_widget

    widget, _backend, _molecule = _gallery_widget(None, count=4)
    try:
        widget.set_engine_choices(lambda: [
            OptimizeChoice("orca", "ORCA", True),
            OptimizeChoice("xtb", "xtb", True),
            OptimizeChoice("psi4", "Psi4", False, "Psi4 is not set up. Choose it in Settings > External Tools."),
        ])
        asked: list[tuple[str, str, str]] = []
        widget.optimize_requested.connect(lambda *args: asked.append(args))
        widget._fill_engine_menu()
        actions = widget._engine_menu.actions()
        assert [a.text() for a in actions] == ["Optimize with xtb", "Optimize with Psi4 (not set up)"]  # ORCA has its own button
        assert actions[0].isEnabled() and not actions[1].isEnabled() and "Settings" in actions[1].toolTip()
        actions[0].trigger()
        assert len(asked) == 1 and asked[0][2] == "xtb" and asked[0][0] == widget._molecule.uuid
    finally:
        conftest.dispose(widget)
