from __future__ import annotations

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import NMRSpectrumResult, SpectrumResult
from openchem.events.base import EventBus
from openchem.events.events import NmrReferenceCalibrated, SpectrumComputed
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel


class _RecordingQuantumChemistryService(QuantumChemistryService):
    """Stands in for the real service -- captures request_calculation's
    kwargs instead of actually spawning a QProcess, so tests can inspect
    exactly what the panel built without needing a real ORCA backend."""

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, Settings(event_bus), providers={})
        self.requests: list[dict] = []
        self.reference_requests: list[tuple[str, str]] = []

    def request_calculation(self, **kwargs) -> None:  # noqa: D102 - test double
        self.requests.append(kwargs)

    def request_reference_calibration(self, method_basis: str, provider_id: str = "orca") -> None:
        self.reference_requests.append((method_basis, provider_id))


def _make_panel():
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    return panel, engine, service


def test_run_refuses_a_molecule_with_no_conformer(qapp):
    """Regression test: confirmed live against a real ORCA install that
    running straight off molecule.molblock (from SMILES import or the 2D
    editor) sends a structure with hydrogens stripped down to implicit
    H-count and no 3D positions at all -- for water, this silently computed
    a bare oxygen atom's energy instead of failing loudly. The panel must
    require a real conformer (which RDKitConformerProvider always builds
    with explicit, positioned hydrogens) before running anything.
    """
    panel, engine, service = _make_panel()
    molecule = MoleculeModel(display_name="Water")
    engine.set_structure_from_smiles(molecule, "O")  # molblock only, no conformer

    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_run_clicked()

    assert service.requests == []
    assert "conformer" in panel._status_label.text().lower()


def test_run_proceeds_once_a_conformer_exists(qapp):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    panel, engine, service = _make_panel()
    molecule = MoleculeModel(display_name="Water")
    engine.set_structure_from_smiles(molecule, "O")

    mol_3d = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=42)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))

    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_run_clicked()

    assert len(service.requests) == 1
    used_mol = service.requests[0]["mol"]
    assert used_mol.GetNumAtoms() == 3  # O + 2 H, not stripped down to just O


def test_nmr_calc_type_is_offered():
    panel, _engine, _service = _make_panel()
    assert "NMR (raw shielding)" in [
        panel._calc_type_combo.itemText(i) for i in range(panel._calc_type_combo.count())
    ]


def test_spectrum_computed_populates_the_table(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    panel._pending_molecule_uuid = "mol-1"

    bus.publish(
        SpectrumComputed(
            spectrum=SpectrumResult(
                spectrum_type="nmr_raw_shielding",
                name="NMR Isotropic Shielding",
                units="ppm (isotropic shielding)",
                method="orca",
                molecule_uuid="mol-1",
                values={0: 365.694, 1: 33.679, 2: 33.679},
                elements={0: "O", 1: "H", 2: "H"},
            )
        )
    )

    assert panel._spectrum_table.rowCount() == 3
    assert panel._spectrum_table.item(0, 1).text() == "O"
    assert panel._spectrum_table.item(0, 2).text() == "365.694"


def test_spectrum_computed_for_a_different_molecule_is_ignored(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    panel._pending_molecule_uuid = "mol-1"

    bus.publish(
        SpectrumComputed(
            spectrum=SpectrumResult(
                spectrum_type="nmr_raw_shielding",
                name="NMR",
                units="ppm",
                method="orca",
                molecule_uuid="some-other-molecule",
                values={0: 1.0},
                elements={0: "O"},
            )
        )
    )

    assert panel._spectrum_table.rowCount() == 0


def test_calibrate_button_calls_request_reference_calibration_with_method_basis(qapp):
    panel, _engine, service = _make_panel()
    panel._method_combo.setCurrentText("B3LYP def2-SVP")

    panel._on_calibrate_clicked()

    assert service.reference_requests == [("B3LYP def2-SVP", "orca")]
    assert not panel._calibrate_button.isEnabled()


def test_calibrate_button_with_empty_method_basis_does_not_call_service(qapp):
    panel, _engine, service = _make_panel()
    panel._method_combo.setCurrentText("")

    panel._on_calibrate_clicked()

    assert service.reference_requests == []


def test_reference_calibrated_success_updates_status_and_reenables_button(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    panel._calibrate_button.setEnabled(False)

    bus.publish(
        NmrReferenceCalibrated(method_basis="B3LYP def2-SVP", provider_id="orca", values={"H": 30.0, "C": 190.0})
    )

    assert panel._calibrate_button.isEnabled()
    assert "B3LYP def2-SVP" in panel._status_label.text()


def test_reference_calibrated_failure_shows_the_error(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)

    bus.publish(
        NmrReferenceCalibrated(method_basis="B3LYP def2-SVP", provider_id="orca", values={}, error="No executable")
    )

    assert panel._calibrate_button.isEnabled()
    assert "No executable" in panel._status_label.text()


def test_note_label_shows_calibrated_text_for_a_calibrated_spectrum(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    panel._pending_molecule_uuid = "mol-1"

    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_calibrated",
                name="Chemical Shift",
                units="ppm",
                method="orca",
                molecule_uuid="mol-1",
                values={0: 90.0},
                elements={0: "C"},
            )
        )
    )

    assert "Calibrated to TMS" in panel._spectrum_note_label.text()


def test_spectrum_computed_populates_correlation_tabs(qapp):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)

    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=7)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("B3LYP def2-SVP")
    panel._on_run_clicked()  # sets panel._pending_mol/_pending_molecule_uuid

    values = {idx: 100.0 + idx for idx in range(mol_3d.GetNumAtoms())}
    elements = {idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())}
    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_raw_shielding",
                name="raw",
                units="ppm",
                method="orca",
                molecule_uuid=molecule.uuid,
                values=values,
                elements=elements,
            )
        )
    )

    # Ethanol has exactly 5 real C-H bonds (3 on CH3, 2 on CH2) -- the OH
    # hydrogen has no carbon neighbor and must be excluded.
    assert panel._correlation_tables["hsqc"].rowCount() == 5
    assert len(panel._correlation_plots["hsqc"]._peaks) == 5
    assert panel._correlation_tables["cosy"].rowCount() > 0


def test_the_1d_signal_tab_exists_before_any_result_arrives(qapp):
    """The tab is created up front so tab order never shifts under the user;
    only the widget inside it (which owns a QWebEngineView) is deferred."""
    panel, _engine, _service = _make_panel()
    assert panel._correlation_tabs.tabText(0) == "1D Signals"
    assert panel._nmr_view is None


def test_spectrum_computed_populates_the_1d_signal_view(qapp):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    panel, engine, _service = _make_panel()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=7)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("B3LYP def2-SVP")
    panel._on_run_clicked()

    elements = {idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())}
    panel._on_spectrum_computed(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_calibrated",
                name="Chemical Shift",
                units="ppm",
                method="orca",
                molecule_uuid=molecule.uuid,
                values={idx: 1.0 + idx for idx in range(mol_3d.GetNumAtoms())},
                elements=elements,
            )
        )
    )

    # Ethanol's protons: CH3 (3H), CH2 (2H), OH (1H).
    assert panel._nmr_view is not None
    assert sorted(s.integration for s in panel._nmr_view.signals()) == [1, 2, 3]
