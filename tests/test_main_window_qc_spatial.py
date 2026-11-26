"""MainWindow QC spatial_view does not use the ordinary property-panel path."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.qc_dipole import AU_TO_DEBYE, VECTOR_ORIGIN_COM
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus, new_run_id
from openchem.ui.history_entries import QC_PREFIX


_WINDOWS: list = []


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


def _build_window(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = _track(MainWindow(services, settings, session))
    return window, services


def _molblock(seed: int) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(mol)


def _dipole():
    return DescriptorValue(
        descriptor_id="orca.dipole_moment",
        name="Dipole",
        units="Debye",
        category="quantum_chemistry",
        provider="orca",
        molecule_uuid="m1",
        value=AU_TO_DEBYE,
        timestamp=1.0,
        cache_state=CacheState.COMPLETED,
        provenance=Provenance(
            created_by="core",
            method="orca",
            parameters={
                "origin_independent": True,
                "vector": [AU_TO_DEBYE, 0.0, 0.0],
                "vector_origin": VECTOR_ORIGIN_COM,
                "vector_frame": "job_cartesian",
            },
            timestamp=1.0,
        ),
    )


def test_ordinary_spatial_link_still_uses_the_property_panel(qapp, tmp_path, monkeypatch):
    window, _services = _build_window(tmp_path)
    seen = []
    monkeypatch.setattr(
        window._property_panel,
        "open_spatial_view",
        lambda report_id, annotation_index=0: seen.append((report_id, annotation_index)) or True,
    )
    assert window._link_to_spatial_view({"report_id": "dipole_moment"}) is True
    assert seen == [("dipole_moment", 0)]


def test_qc_spatial_link_does_not_call_the_property_panel(qapp, tmp_path, monkeypatch):
    window, services = _build_window(tmp_path)
    submitted, other = _molblock(1), _molblock(9)
    molecule = MoleculeModel(display_name="ethanol", conformers=[ConformerModel(molblock=other)])
    services.chemistry_engine.set_structure_from_smiles(molecule, "CCO")
    window.add_molecule(molecule)
    run = QuantumChemistryRun(
        run_id=new_run_id(),
        molecule_uuid=molecule.uuid,
        calc_type="sp",
        method_basis="B3LYP def2-SVP",
        charge=0,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="fp",
        input_molblock=submitted,
        provider="orca",
        status=RunStatus.COMPLETED,
        completed_at=1.0,
        results={"descriptors": [_dipole()]},
        output_status={},
    )
    services.result_store_service.record_quantum_chemistry_run(run)
    panel_calls = []
    monkeypatch.setattr(
        window._property_panel,
        "open_spatial_view",
        lambda *args, **kwargs: panel_calls.append(True) or True,
    )
    opened = []

    class FakeDialog:
        def __init__(self, report, molblock, parent=None, *, caveat=None):
            opened.append((report, molblock, caveat))

        def setAttribute(self, *args, **kwargs):
            return None

        def show(self):
            return None

        def raise_(self):
            return None

    monkeypatch.setattr("openchem.ui.dialogs.spatial_result_dialog.SpatialResultDialog", FakeDialog)
    assert window._link_to_spatial_view({"report_id": f"{QC_PREFIX}{run.run_id}"}) is True
    assert panel_calls == []
    assert opened[0][1] == submitted
    assert "Quantum run" in opened[0][2]


def test_qc_spatial_link_refuses_a_missing_run(qapp, tmp_path, monkeypatch):
    window, _services = _build_window(tmp_path)
    panel_calls = []
    monkeypatch.setattr(
        window._property_panel,
        "open_spatial_view",
        lambda *args, **kwargs: panel_calls.append(True) or True,
    )
    assert window._link_to_spatial_view({"report_id": "qc:missing"}) is False
    assert panel_calls == []
