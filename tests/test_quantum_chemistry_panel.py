from __future__ import annotations

import re

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.chem.orca_engine import NMR_METHOD_BASIS
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import NMRSpectrumResult, SpectrumResult
from openchem.events.base import EventBus
from openchem.events.events import NmrReferenceCalibrated, SpectrumComputed
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel

import conftest


class _RecordingQuantumChemistryService(QuantumChemistryService):
    """Stands in for the real service -- captures request_calculation's
    kwargs instead of actually spawning a QProcess, so tests can inspect
    exactly what the panel built without needing a real ORCA backend."""

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, Settings(event_bus), providers={})
        self.requests: list[dict] = []
        self.boltzmann_requests: list[dict] = []
        self.reference_requests: list[tuple[str, str]] = []
        self.tautomer_distribution_requests: list[dict] = []

    def request_calculation(self, **kwargs) -> None:  # noqa: D102 - test double
        self.requests.append(kwargs)

    def request_boltzmann_nmr(self, **kwargs) -> None:  # noqa: D102 - test double
        self.boltzmann_requests.append(kwargs)

    def request_reference_calibration(self, method_basis: str, provider_id: str = "orca") -> None:
        self.reference_requests.append((method_basis, provider_id))

    def request_tautomer_distribution(self, **kwargs) -> None:  # noqa: D102 - test double
        self.tautomer_distribution_requests.append(kwargs)


def _make_panel():
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    return panel, engine, service


def _dispose_panel(panel) -> None:
    """Destroy one panel deterministically.

    PER WIDGET, never `sendPostedEvents(None, DeferredDelete)`: the global
    form drains every pending deferred delete in the process, including
    ones other test files left queued.
    """

    conftest.dispose(panel)



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


# --- Tautomer Distribution button --------------------------------------


def _cyclohexanone_molecule(engine) -> MoleculeModel:
    molecule = MoleculeModel(display_name="Cyclohexanone")
    engine.set_structure_from_smiles(molecule, "O=C1CCCCC1")
    return molecule


def test_tautomer_distribution_requires_a_structure():
    panel, _engine, service = _make_panel()
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_tautomer_distribution_clicked()

    assert service.tautomer_distribution_requests == []
    assert "select a molecule" in panel._status_label.text().lower()


def test_tautomer_distribution_proceeds_without_an_existing_conformer():
    """Unlike the main Run button, this needs no pre-generated conformer --
    each candidate gets its own fresh 3D embedding from the 2D structure."""
    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    assert not molecule.conformers

    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_tautomer_distribution_clicked()

    assert len(service.tautomer_distribution_requests) == 1
    request = service.tautomer_distribution_requests[0]
    assert request["molecule_uuid"] == molecule.uuid
    assert len(request["candidates"]) >= 2  # cyclohexanone: at least keto + enol


def test_tautomer_distribution_requires_a_method_basis():
    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("")

    panel._on_tautomer_distribution_clicked()

    assert service.tautomer_distribution_requests == []
    assert "method/basis" in panel._status_label.text().lower()


def test_tautomer_distribution_disables_run_and_tautomer_buttons_while_pending():
    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_tautomer_distribution_clicked()

    assert panel._run_button.isEnabled() is False
    assert panel._tautomer_distribution_button.isEnabled() is False
    assert panel._cancel_button.isEnabled() is True


def test_tautomer_distribution_above_threshold_asks_for_confirmation(monkeypatch):
    import openchem.ui.panels.quantum_chemistry_panel as panel_module

    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    # Force the confirmation path with only a couple of real candidates --
    # patched on the panel module, where the name was bound by its own
    # `from ... import CONFIRMATION_THRESHOLD`, not where it originates.
    monkeypatch.setattr(panel_module, "CONFIRMATION_THRESHOLD", 1)
    asked = []
    monkeypatch.setattr(
        panel_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: asked.append(a) or panel_module.QMessageBox.StandardButton.No),
    )

    panel._on_tautomer_distribution_clicked()

    assert asked  # the confirmation dialog was shown
    assert service.tautomer_distribution_requests == []  # "No" was respected


def test_the_confirmation_names_the_jobs_and_the_tautomers(monkeypatch):
    import openchem.ui.panels.quantum_chemistry_panel as panel_module

    panel, engine, service = _make_panel()
    project = ProjectModel(name="Test")
    project.molecules.append(_cyclohexanone_molecule(engine))
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")
    monkeypatch.setattr(panel_module, "CONFIRMATION_THRESHOLD", 1)
    asked = []
    monkeypatch.setattr(
        panel_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: asked.append(a[2]) or panel_module.QMessageBox.StandardButton.No),
    )

    panel._on_tautomer_distribution_clicked()

    # The JOB count depends on the conformer search; the tautomer and stereoisomer
    # counts, and the named model, are what the user is told alongside it.
    assert re.search(
        r"This will run \d+ real ORCA geometry optimizations for 2 tautomer\(s\) and 2 stereoisomer\(s\)",
        asked[0],
    )
    assert "conformer search mmff_topk" in asked[0]
    assert "exceed the stereoisomer cap" not in asked[0]


def test_the_confirmation_warns_before_a_truncated_tautomer_is_run(monkeypatch):
    """Cost is below the threshold, so only truncation can trigger the prompt:
    the user must hear the result will be incomplete BEFORE paying for it."""
    import openchem.ui.panels.quantum_chemistry_panel as panel_module
    from openchem.chem import tautomer_distribution as td

    panel, engine, service = _make_panel()
    project = ProjectModel(name="Test")
    project.molecules.append(_cyclohexanone_molecule(engine))
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")
    real = td.generate_tautomer_candidates
    monkeypatch.setattr(
        panel_module,
        "generate_tautomer_candidates",
        lambda mol, policy=None: real(
            engine.mol_from_smiles("CC(O)C(C)O"), stereo_cap=1, policy=td.MODEL_POLICY_SINGLE
        ),
    )
    asked = []
    monkeypatch.setattr(
        panel_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: asked.append(a[2]) or panel_module.QMessageBox.StandardButton.No),
    )

    panel._on_tautomer_distribution_clicked()

    assert asked and "1 tautomer(s) exceed the stereoisomer cap" in asked[0]
    assert "incomplete" in asked[0] and "no population percentages" in asked[0]
    assert service.tautomer_distribution_requests == []


def test_tautomer_distribution_ready_ignores_a_different_molecule(qapp):
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import StructureSetResult
    from openchem.events.events import TautomerDistributionResultReady

    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")
    panel._on_tautomer_distribution_clicked()

    unrelated_result = StructureSetResult(
        set_id="tautomer_distribution", name="x", method="orca", molecule_uuid="some-other-molecule",
        provenance=Provenance(created_by="core", method="orca", parameters={}),
    )
    panel._on_tautomer_distribution_ready(
        TautomerDistributionResultReady(molecule_uuid="some-other-molecule", run_id="r1", result=unrelated_result)
    )

    assert panel._results_label.text() == ""


def test_tautomer_distribution_ready_updates_the_summary_label(qapp):
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import StructureEntry, StructureSetResult
    from openchem.events.events import TautomerDistributionResultReady

    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")
    panel._on_tautomer_distribution_clicked()

    result = StructureSetResult(
        set_id="tautomer_distribution",
        name="Tautomer distribution (1)",
        method="orca",
        molecule_uuid=molecule.uuid,
        entries=[StructureEntry(molblock="", label="a", energy=0.0, metadata={"status": "succeeded"})],
        provenance=Provenance(
            created_by="core",
            method="orca",
            parameters={
                "candidate_count_succeeded": 1,
                "candidate_count_failed": 0,
                "validation_branch": "unvalidated",
            },
        ),
    )
    panel._on_tautomer_distribution_ready(
        TautomerDistributionResultReady(molecule_uuid=molecule.uuid, run_id="r1", result=result)
    )

    assert "1/1" in panel._results_label.text()
    assert "not yet validated" in panel._results_label.text().lower()
    panel._tautomer_distribution_dialog.close()


def test_tautomer_distribution_clicked_captures_the_submitting_fingerprint():
    """Phase J: the submitting molecule's own DRAWING fingerprint is
    captured at submission time and handed to the service -- the identity
    a later-recorded `StoredResult` needs, taken BEFORE any candidate
    embedding/ORCA work starts so a mid-run edit cannot retroactively
    change what the eventual result claims to describe."""
    from openchem.chem.calculation_input import input_fingerprint
    from openchem.domain.calculator import DRAWING

    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_tautomer_distribution_clicked()

    assert len(service.tautomer_distribution_requests) == 1
    request = service.tautomer_distribution_requests[0]
    assert request["calculation_input"] == DRAWING
    assert request["input_fingerprint"] == input_fingerprint(engine, molecule, DRAWING)


def _tautomer_distribution_run(molecule_uuid: str, result) -> "object":
    from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus

    run = QuantumChemistryRun(
        run_id="run-1",
        molecule_uuid=molecule_uuid,
        calc_type="tautomer_distribution",
        method_basis="HF STO-3G",
        charge=0,
        multiplicity=1,
        calculation_input="",
        input_fingerprint="",
        input_molblock="",
        status=RunStatus.COMPLETED,
    )
    run.results["tautomer_distribution"] = result
    run.output_status["tautomer_distribution"] = OutputStatus.AVAILABLE
    return run


def _fake_tautomer_distribution_result(molecule_uuid: str):
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import StructureEntry, StructureSetResult

    return StructureSetResult(
        set_id="orca.tautomer_distribution",
        name="Tautomer distribution (1)",
        method="orca",
        molecule_uuid=molecule_uuid,
        entries=[StructureEntry(molblock="", label="a", energy=0.0, metadata={"status": "succeeded"})],
        provenance=Provenance(
            created_by="core",
            method="orca",
            parameters={
                "candidate_count_succeeded": 1,
                "candidate_count_failed": 0,
                "validation_branch": "unvalidated",
            },
        ),
    )


def test_run_label_names_tautomer_distribution_runs(qapp):
    """`_run_label` special-cases `calc_type == "tautomer_distribution"`
    rather than falling back to the raw calc_type string, since that
    calc_type is deliberately excluded from `CALC_TYPE_LABELS`."""
    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    run = _tautomer_distribution_run(molecule.uuid, _fake_tautomer_distribution_result(molecule.uuid))

    label = panel._run_label(run)

    assert label.startswith("Tautomer Distribution ·")
    assert "tautomer_distribution" not in label  # never the raw calc_type string


def test_render_run_enables_the_view_button_without_opening_a_dialog(qapp):
    """The real fix for 'reselecting a past tautomer-distribution run shows
    nothing': `_render_run` now populates the summary and enables 'View
    Tautomer Distribution...' -- but NEVER auto-opens the dialog, since
    `_render_run` also fires on a plain molecule reselection."""
    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    result = _fake_tautomer_distribution_result(molecule.uuid)
    run = _tautomer_distribution_run(molecule.uuid, result)

    opened = []
    panel._open_tautomer_distribution_dialog = lambda r: opened.append(r)
    panel._render_run(run)

    assert opened == []  # no dialog, even though a result is present
    assert panel._view_tautomer_distribution_button.isEnabled() is True
    assert "1/1" in panel._results_label.text()


def test_render_run_without_a_tautomer_distribution_disables_the_view_button(qapp):
    from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus

    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    # First enable it from a real tautomer-distribution run...
    panel._render_run(_tautomer_distribution_run(molecule.uuid, _fake_tautomer_distribution_result(molecule.uuid)))
    assert panel._view_tautomer_distribution_button.isEnabled() is True

    # ...then render an unrelated (e.g. plain NMR) run and confirm it turns off.
    other_run = QuantumChemistryRun(
        run_id="run-2", molecule_uuid=molecule.uuid, calc_type="nmr", method_basis="HF STO-3G",
        charge=0, multiplicity=1, calculation_input="", input_fingerprint="", input_molblock="",
        status=RunStatus.COMPLETED,
    )
    panel._render_run(other_run)

    assert panel._view_tautomer_distribution_button.isEnabled() is False


def test_clear_run_display_disables_the_view_button(qapp):
    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    panel._render_run(_tautomer_distribution_run(molecule.uuid, _fake_tautomer_distribution_result(molecule.uuid)))
    assert panel._view_tautomer_distribution_button.isEnabled() is True

    panel._clear_run_display()

    assert panel._view_tautomer_distribution_button.isEnabled() is False


def test_view_tautomer_distribution_button_opens_the_exact_selected_runs_result(qapp):
    """The explicit, discoverable reopen path: clicking the button opens
    the CURRENTLY SELECTED run's own result, not a copy and not whatever
    happens to be the molecule's latest."""
    panel, engine, service = _make_panel()
    molecule = _cyclohexanone_molecule(engine)
    result = _fake_tautomer_distribution_result(molecule.uuid)
    run = _tautomer_distribution_run(molecule.uuid, result)
    panel._render_run(run)

    opened = []
    panel._open_tautomer_distribution_dialog = lambda r: opened.append(r)
    panel._on_view_tautomer_distribution_clicked()

    assert opened == [result]  # the exact same object, not a copy


def _panel_with_a_store(qapp, molecule_count: int = 1):
    from openchem.services.result_store_service import ResultStoreService

    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    store_service = ResultStoreService(bus, engine, settings)
    panel = QuantumChemistryPanel(
        _RecordingQuantumChemistryService(bus), engine, settings, bus, result_store_service=store_service
    )
    project = ProjectModel(name="Test")
    molecules = [_cyclohexanone_molecule(engine) for _ in range(molecule_count)]
    project.molecules.extend(molecules)
    store_service.set_project(project)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    return panel, bus, molecules


def test_a_run_finishing_in_this_session_appears_in_the_runs_combo_at_once(qapp):
    """FOUND BY DRIVING THE REAL APP: the combo was only repopulated by a
    molecule selection, a project load or a delete, so a run that finished
    while its molecule stayed selected never showed in "Runs" and "View
    Tautomer Distribution..." stayed disabled until the user switched
    molecules and back."""
    from openchem.events.events import QuantumChemistryRunCompleted

    panel, bus, (molecule,) = _panel_with_a_store(qapp)
    assert panel._runs_combo.count() == 0
    assert panel._view_tautomer_distribution_button.isEnabled() is False

    run = _tautomer_distribution_run(molecule.uuid, _fake_tautomer_distribution_result(molecule.uuid))
    bus.publish(QuantumChemistryRunCompleted(run=run))
    qapp.processEvents()

    assert panel._runs_combo.count() == 1
    assert panel._runs_combo.currentText().startswith("Tautomer Distribution ·")
    assert panel._view_tautomer_distribution_button.isEnabled() is True


def test_a_run_finishing_for_another_molecule_leaves_this_runs_combo_alone(qapp):
    from openchem.events.events import QuantumChemistryRunCompleted

    panel, bus, (_molecule, other) = _panel_with_a_store(qapp, molecule_count=2)

    bus.publish(QuantumChemistryRunCompleted(
        run=_tautomer_distribution_run(other.uuid, _fake_tautomer_distribution_result(other.uuid))
    ))
    qapp.processEvents()

    assert panel._runs_combo.count() == 0
    assert panel._view_tautomer_distribution_button.isEnabled() is False


def test_view_tautomer_distribution_button_is_a_noop_with_no_active_run(qapp):
    panel, engine, service = _make_panel()
    opened = []
    panel._open_tautomer_distribution_dialog = lambda r: opened.append(r)

    panel._on_view_tautomer_distribution_clicked()  # no _render_run call first

    assert opened == []


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


def test_the_more_menu_carries_the_three_setup_buttons(qapp):
    """Collapsed behind `_more_button` rather than removed -- `Configure
    ORCA...` / `Calibrate Reference...` / `Calibrate Scaling...` must still
    be real, clickable `QPushButton`s reachable from the panel, since every
    other test above (and every help tooltip) targets them directly."""
    panel, _engine, _service = _make_panel()

    menu_widgets = {
        action.defaultWidget() for action in panel._more_menu.actions() if action.defaultWidget()
    }

    assert panel._configure_button in menu_widgets
    assert panel._calibrate_button in menu_widgets
    assert panel._scaling_button in menu_widgets
    assert panel._more_button.menu() is panel._more_menu


def test_the_tab_help_button_opens_the_active_tabs_topic(qapp):
    """One affordance, following whichever tab is active -- not one help
    button per tab. Injecting `open_help` (the same optional-callback
    contract `CalculatorVisibilityPage` uses) keeps this test from needing
    a real `HelpDialog`/`QApplication` help window."""
    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.events.base import EventBus as _EventBus

    bus = _EventBus()
    engine = _Engine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    opened: list[str] = []
    panel = QuantumChemistryPanel(service, engine, settings, bus, open_help=opened.append)

    panel._correlation_tabs.setCurrentWidget(panel._ir_view_tab)
    panel._on_tab_help_clicked()
    assert opened == ["ir-spectra"]

    panel._correlation_tabs.setCurrentWidget(panel._nmr_view_tab)
    panel._on_tab_help_clicked()
    assert opened == ["ir-spectra", "nmr-referencing"]


def test_every_tab_has_a_help_topic_assigned(qapp):
    """No tab should fall through to a bare "quantum-chemistry" by
    accident -- the correlation/Hybrid/Surfaces tabs each have a more
    specific topic, and this catches a future tab added without one
    (it would silently answer with the general topic, which this test
    would not have caught without naming every existing tab)."""
    panel, _engine, _service = _make_panel()
    expected = {
        panel._nmr_view_tab: "nmr-referencing",
        panel._ir_view_tab: "ir-spectra",
        panel._surfaces_tab: "surfaces",
    }
    for tab, topic in expected.items():
        index = panel._correlation_tabs.indexOf(tab)
        assert panel._tab_help_topics[index] == topic
    for correlation_type in ("hsqc", "hmbc", "cosy"):
        table = panel._correlation_tables[correlation_type]
        tab = table.parentWidget()
        index = panel._correlation_tabs.indexOf(tab)
        assert panel._tab_help_topics[index] == "2d-correlation"
    hybrid_index = panel._correlation_tabs.indexOf(panel._hybrid_table.parentWidget())
    assert panel._tab_help_topics[hybrid_index] == "hybrid-shifts"
    log_index = panel._correlation_tabs.indexOf(panel._output_log)
    assert panel._tab_help_topics[log_index] == "quantum-chemistry"


def test_calibrate_button_calls_request_reference_calibration_with_method_basis(qapp):
    panel, _engine, service = _make_panel()
    panel._method_combo.setCurrentText("B3LYP def2-SVP")

    panel._on_calibrate_clicked()

    assert service.reference_requests == [("B3LYP def2-SVP", "orca")]
    assert not panel._calibrate_button.isEnabled()


def test_selecting_a_solvent_appends_a_cpcm_keyword_to_the_header(qapp):
    panel, _engine, service = _make_panel()
    panel._method_combo.setCurrentText("B3LYP pcSseg-1")
    panel._solvent_combo.setCurrentText("Chloroform")

    panel._on_calibrate_clicked()

    assert service.reference_requests == [("B3LYP pcSseg-1 CPCM(Chloroform)", "orca")]


def test_gas_phase_leaves_the_header_untouched(qapp):
    panel, _engine, service = _make_panel()
    panel._method_combo.setCurrentText("B3LYP pcSseg-1")

    panel._on_calibrate_clicked()

    # The default entry carries "" as its data, so existing gas-phase jobs --
    # and every TMS reference already cached against a bare method string --
    # keep producing the exact same header they always did.
    assert service.reference_requests == [("B3LYP pcSseg-1", "orca")]


def test_run_and_calibrate_build_the_same_solvated_header(qapp):
    """The TMS reference cache is keyed on this string, so a mismatch here
    would mean a solvated run never finds the reference calibrated for it."""
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
    panel._method_combo.setCurrentText("B3LYP pcSseg-1")
    panel._solvent_combo.setCurrentText("DMSO")

    panel._on_calibrate_clicked()
    panel._on_run_clicked()

    assert service.reference_requests[0][0] == service.requests[0]["method_basis"]


def test_switching_to_nmr_preselects_an_nmr_appropriate_basis(qapp):
    panel, _engine, _service = _make_panel()
    panel._method_combo.setCurrentText("B3LYP def2-SVP")

    panel._calc_type_combo.setCurrentText("NMR (raw shielding)")

    assert panel._method_combo.currentText() == NMR_METHOD_BASIS


def test_switching_to_nmr_leaves_a_hand_typed_method_alone(qapp):
    panel, _engine, _service = _make_panel()
    panel._method_combo.setCurrentText("PBE0 D3BJ pcSseg-2")

    panel._calc_type_combo.setCurrentText("NMR (raw shielding)")

    assert panel._method_combo.currentText() == "PBE0 D3BJ pcSseg-2"


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

    # Bidirectional selection, through (atom_a, atom_b) rather than row
    # position or coordinates: the table drives the plot...
    table = panel._correlation_tables["hsqc"]
    plot = panel._correlation_plots["hsqc"]
    table.selectRow(2)
    atom_a = int(table.item(2, 0).text())
    atom_b = int(table.item(2, 1).text())
    assert plot._highlighted_pair == (atom_a, atom_b)

    # ...and a peak click drives the table back, landing on the SAME row
    # regardless of which one was selected a moment ago. Emitted for real
    # (not called directly) because the handler reads `correlation_type`
    # off `self.sender()`, which only resolves during a real signal
    # dispatch.
    other_row = 0 if atom_a != int(table.item(0, 0).text()) else 1
    plot.peak_selected.emit(
        int(table.item(other_row, 0).text()), int(table.item(other_row, 1).text())
    )
    assert {index.row() for index in table.selectedIndexes()} == {other_row}


# --- Sortable correlation/hybrid tables (Phase E) --------------------------


def test_sorting_the_correlation_table_orders_atom_columns_numerically(qapp):
    from PySide6.QtCore import Qt

    bus = EventBus()
    engine = ChemistryEngine()
    panel, molecule, mol_3d = _ethanol_panel(
        bus, engine, Settings(bus), _RecordingQuantumChemistryService(bus)
    )
    values = {idx: 100.0 + idx for idx in range(mol_3d.GetNumAtoms())}
    elements = {idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())}
    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_raw_shielding", name="raw", units="ppm", method="orca",
                molecule_uuid=molecule.uuid, values=values, elements=elements,
            )
        )
    )
    table = panel._correlation_tables["hsqc"]

    table.sortItems(0, Qt.SortOrder.DescendingOrder)

    shown = [int(table.item(row, 0).text()) for row in range(table.rowCount())]
    assert shown == sorted(shown, reverse=True)

    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    shown = [int(table.item(row, 0).text()) for row in range(table.rowCount())]
    assert shown == sorted(shown)


def test_selection_survives_a_correlation_table_sort_through_the_atom_pair(qapp):
    """The claim this phase relies on rather than re-derives:
    `_on_correlation_row_selected`/`_on_correlation_peak_selected` already
    resolve through `(atom_a, atom_b)` text, never row position -- live-
    checked here AFTER a sort, not assumed from reading the source."""
    from PySide6.QtCore import Qt

    bus = EventBus()
    engine = ChemistryEngine()
    panel, molecule, mol_3d = _ethanol_panel(
        bus, engine, Settings(bus), _RecordingQuantumChemistryService(bus)
    )
    values = {idx: 100.0 + idx for idx in range(mol_3d.GetNumAtoms())}
    elements = {idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())}
    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_raw_shielding", name="raw", units="ppm", method="orca",
                molecule_uuid=molecule.uuid, values=values, elements=elements,
            )
        )
    )
    table = panel._correlation_tables["hsqc"]
    plot = panel._correlation_plots["hsqc"]

    table.sortItems(0, Qt.SortOrder.DescendingOrder)
    table.selectRow(2)
    atom_a = int(table.item(2, 0).text())
    atom_b = int(table.item(2, 1).text())

    assert plot._highlighted_pair == (atom_a, atom_b)

    other_row = 0 if atom_a != int(table.item(0, 0).text()) else 1
    plot.peak_selected.emit(
        int(table.item(other_row, 0).text()), int(table.item(other_row, 1).text())
    )
    assert {index.row() for index in table.selectedIndexes()} == {other_row}


def test_sorting_the_correlation_tables_j_column_groups_missing_values(qapp):
    """A mixed column (real Hz floats alongside the "no coupling reported"
    em dash) must sort deterministically, not raise."""
    from PySide6.QtCore import Qt

    from openchem.domain.scientific_result import CrossPeak

    panel, _engine, _service = _make_panel()
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_calibrated", name="n", units="ppm", method="orca",
        molecule_uuid="uuid", values={0: 1.0, 1: 2.0, 2: 3.0, 3: 4.0},
    )
    cross_peaks = [
        CrossPeak(atom_a=0, atom_b=1, coupling_hz=7.0),
        CrossPeak(atom_a=2, atom_b=3, coupling_hz=None),
        CrossPeak(atom_a=1, atom_b=2, coupling_hz=14.0),
    ]
    panel._populate_correlation_tab("hsqc", cross_peaks, spectrum, "x", "y")
    table = panel._correlation_tables["hsqc"]

    table.sortItems(4, Qt.SortOrder.AscendingOrder)

    order = [table.item(row, 4).text() for row in range(table.rowCount())]
    assert order == ["—", "7.00", "14.00"]


def test_a_rerun_resets_the_correlation_tables_sort_order(qapp):
    from PySide6.QtCore import Qt

    bus = EventBus()
    engine = ChemistryEngine()
    panel, molecule, mol_3d = _ethanol_panel(
        bus, engine, Settings(bus), _RecordingQuantumChemistryService(bus)
    )
    values = {idx: 100.0 + idx for idx in range(mol_3d.GetNumAtoms())}
    elements = {idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())}

    def _run():
        bus.publish(
            SpectrumComputed(
                spectrum=NMRSpectrumResult(
                    spectrum_type="nmr_raw_shielding", name="raw", units="ppm", method="orca",
                    molecule_uuid=molecule.uuid, values=values, elements=elements,
                )
            )
        )

    _run()
    table = panel._correlation_tables["hsqc"]
    natural = [int(table.item(row, 0).text()) for row in range(table.rowCount())]

    table.sortItems(0, Qt.SortOrder.DescendingOrder)
    descending = [int(table.item(row, 0).text()) for row in range(table.rowCount())]
    assert descending == sorted(descending, reverse=True)

    panel._on_run_clicked()  # re-arms _pending_molecule_uuid for a second run
    _run()

    shown = [int(table.item(row, 0).text()) for row in range(table.rowCount())]
    assert shown == natural


def test_sorting_the_hybrid_table_orders_the_shift_column_numerically(qapp, monkeypatch):
    """The same `SortableItem` mechanism as the other two tables, proven
    non-lexicographic with values that would misorder as strings: 9 vs 18."""
    from PySide6.QtCore import Qt

    from openchem.chem import nmr_database
    from openchem.domain.common import CacheState, Provenance

    bus = EventBus()
    engine = ChemistryEngine()
    panel, molecule, mol_3d = _ethanol_panel(
        bus, engine, Settings(bus), _RecordingQuantumChemistryService(bus)
    )

    def fake_predict(mol, molecule_uuid, element="C", **kwargs):
        if element != "C":
            return NMRSpectrumResult(
                spectrum_type="nmr_1h", name="H (database)", units="ppm", method="hose_lookup",
                molecule_uuid=molecule_uuid, cache_state=CacheState.FAILED, error="nothing indexed",
            )
        return NMRSpectrumResult(
            spectrum_type="nmr_13c", name="C (database)", units="ppm", method="hose_lookup",
            molecule_uuid=molecule_uuid, values={0: 9.0, 1: 58.0}, elements={0: "C", 1: "C"},
            cache_state=CacheState.COMPLETED,
            provenance=Provenance(
                created_by="core", method="hose_lookup",
                parameters={"per_atom": {
                    "0": {"quality": "good", "matches": 40, "spheres": 4},
                    "1": {"quality": "good", "matches": 40, "spheres": 4},
                }},
            ),
        )

    monkeypatch.setattr(nmr_database, "predict_spectrum", fake_predict)

    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_13c", name="scaled", units="ppm", method="orca",
                molecule_uuid=molecule.uuid, values={0: 9.3, 1: 58.4}, elements={0: "C", 1: "C"},
                provenance=Provenance(
                    created_by="core", method="orca",
                    parameters={
                        "referencing": "empirical_linear_scaling",
                        "scaling_C": {
                            "slope": -1.0, "intercept": 0.0, "r_squared": 0.999,
                            "sample_count": 7, "residual_rms": 0.2,
                        },
                    },
                ),
            )
        )
    )

    table = panel._hybrid_table
    assert table.rowCount() == 2

    table.sortItems(2, Qt.SortOrder.AscendingOrder)
    shown = [float(table.item(row, 2).text()) for row in range(table.rowCount())]
    assert shown == sorted(shown)

    table.sortItems(2, Qt.SortOrder.DescendingOrder)
    shown = [float(table.item(row, 2).text()) for row in range(table.rowCount())]
    assert shown == sorted(shown, reverse=True)


def test_a_stored_run_repaints_the_panel_with_no_job_submitted_this_session(qapp):
    """The actual persistence bug this was all for: `_pending_molecule_uuid`
    is `None` right after a project loads or a molecule is (re)selected --
    no job was ever submitted THIS session -- so a naive replay through the
    live `_on_spectrum_computed`/`_on_result_ready` handlers (gated on
    `_pending_molecule_uuid`) would be silently ignored. `_refresh_active_run`
    must reach the panel a different way."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.quantum_chemistry_run import (
        OutputStatus,
        QuantumChemistryRun,
        RunStatus,
    )
    from openchem.services.result_store_service import ResultStoreService

    bus = EventBus()
    engine = _Engine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    store_service = ResultStoreService(bus, engine, settings)

    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=7)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    store_service.set_project(project)

    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="Chemical Shift",
        units="ppm",
        method="orca",
        molecule_uuid=molecule.uuid,
        values={idx: 100.0 + idx for idx in range(mol_3d.GetNumAtoms())},
        elements={idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())},
    )
    run = QuantumChemistryRun(
        run_id="run-1",
        molecule_uuid=molecule.uuid,
        calc_type="nmr",
        method_basis="B3LYP def2-SVP",
        charge=0,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="fp",
        input_molblock=Chem.MolToMolBlock(mol_3d),
        status=RunStatus.COMPLETED,
    )
    run.results["spectrum"] = spectrum
    run.output_status["spectrum"] = OutputStatus.AVAILABLE
    run.results["descriptors"] = [
        DescriptorValue(
            descriptor_id="orca.scf_energy",
            name="SCF Energy",
            units="Hartree",
            category="quantum_chemistry",
            provider="orca",
            molecule_uuid=molecule.uuid,
            value=-154.9,
        )
    ]
    store_service.record_quantum_chemistry_run(run)

    # Fresh panel: no job has ever been submitted through it.
    panel = QuantumChemistryPanel(
        service, engine, settings, bus, result_store_service=store_service
    )
    assert panel._pending_molecule_uuid is None

    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)

    assert panel._active_run is run
    assert "SCF Energy" in panel._results_label.text()
    assert panel._spectrum_table.rowCount() == mol_3d.GetNumAtoms()
    assert panel._correlation_tables["hsqc"].rowCount() > 0


def _two_nmr_runs(qapp):
    """Shared setup for the Phase 2 history-control tests: a panel wired to
    a real `ResultStoreService`, with two completed NMR runs on one
    molecule at different (fingerprint, method) so `compare()` accepts
    them. Returns (panel, store_service, molecule, run_older, run_newer)."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.domain.quantum_chemistry_run import (
        OutputStatus,
        QuantumChemistryRun,
        RunStatus,
    )
    from openchem.services.result_store_service import ResultStoreService

    bus = EventBus()
    engine = _Engine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    store_service = ResultStoreService(bus, engine, settings)

    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=7)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    store_service.set_project(project)

    def _spectrum(offset: float) -> NMRSpectrumResult:
        return NMRSpectrumResult(
            spectrum_type="nmr_calibrated",
            name="Chemical Shift",
            units="ppm",
            method="orca",
            molecule_uuid=molecule.uuid,
            values={idx: offset + idx for idx in range(mol_3d.GetNumAtoms())},
            elements={idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())},
        )

    def _run(run_id: str, method_basis: str, started_at: float, offset: float) -> QuantumChemistryRun:
        run = QuantumChemistryRun(
            run_id=run_id,
            molecule_uuid=molecule.uuid,
            calc_type="nmr",
            method_basis=method_basis,
            charge=0,
            multiplicity=1,
            calculation_input="geometry",
            # SAME fingerprint on purpose -- both runs are on the same
            # structure, which is what makes compare() accept them.
            input_fingerprint="fp-shared",
            input_molblock=Chem.MolToMolBlock(mol_3d),
            status=RunStatus.COMPLETED,
            started_at=started_at,
        )
        run.results["spectrum"] = _spectrum(offset)
        run.output_status["spectrum"] = OutputStatus.AVAILABLE
        return run

    run_older = _run("run-older", "B3LYP def2-SVP", 1.0, offset=10.0)
    run_newer = _run("run-newer", "PBE0 def2-SVP", 2.0, offset=20.0)
    store_service.record_quantum_chemistry_run(run_older)
    store_service.record_quantum_chemistry_run(run_newer)

    panel = QuantumChemistryPanel(service, engine, settings, bus, result_store_service=store_service)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    return panel, store_service, molecule, run_older, run_newer


def test_the_runs_combo_lists_every_run_newest_first(qapp):
    panel, _store, _molecule, run_older, run_newer = _two_nmr_runs(qapp)

    assert panel._runs_combo.count() == 2
    assert panel._runs_combo.itemData(0) == run_newer.run_id
    assert panel._runs_combo.itemData(1) == run_older.run_id
    assert panel._active_run is run_newer


def test_selecting_an_older_run_in_the_combo_repaints_the_panel(qapp):
    panel, _store, _molecule, run_older, _run_newer = _two_nmr_runs(qapp)

    panel._runs_combo.setCurrentIndex(1)

    assert panel._active_run is run_older
    assert panel._spectrum_table.item(0, 2).text() == f"{10.0:.3f}"


def test_tab_titles_carry_a_status_glyph_for_the_active_run(qapp):
    """The fixture run sets only `output_status["spectrum"]`, the way a
    hand-built test run does but a real one from the service never would
    (it always sets every key it touches) -- so spectrum-derived tabs get
    the available mark, and IR, which this run's `output_status` says
    nothing about, gets none at all rather than a guessed one. Surfaces
    always resolves, even to "not produced", because its sentinel reads
    `run.surface_cache_key` directly rather than a possibly-absent key."""
    panel, _store, _molecule, _run_older, run_newer = _two_nmr_runs(qapp)

    index_1d = panel._correlation_tabs.indexOf(panel._nmr_view_tab)
    index_ir = panel._correlation_tabs.indexOf(panel._ir_view_tab)
    index_surfaces = panel._correlation_tabs.indexOf(panel._surfaces_tab)

    assert panel._correlation_tabs.tabText(index_1d) == "1D Signals ✓"
    assert panel._correlation_tabs.tabText(index_ir) == "IR"
    assert panel._correlation_tabs.tabText(index_surfaces) == "Surfaces –"


def test_tab_status_glyphs_clear_when_the_run_display_is_cleared(qapp):
    panel, _store, _molecule, run_older, _run_newer = _two_nmr_runs(qapp)
    index_1d = panel._correlation_tabs.indexOf(panel._nmr_view_tab)
    assert panel._correlation_tabs.tabText(index_1d) == "1D Signals ✓"

    panel._clear_run_display()

    assert panel._correlation_tabs.tabText(index_1d) == "1D Signals"


def test_deleting_the_active_run_leaves_the_other_one_selectable(qapp):
    panel, store, molecule, run_older, run_newer = _two_nmr_runs(qapp)
    assert panel._active_run is run_newer

    from PySide6.QtWidgets import QMessageBox

    orig_question = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        panel._on_delete_run_clicked()
    finally:
        QMessageBox.question = orig_question

    assert store.qc_runs.get(run_newer.run_id) is None
    assert store.qc_runs.get(run_older.run_id) is run_older
    assert panel._runs_combo.count() == 1
    assert panel._active_run is run_older


def test_deleting_a_run_does_not_touch_the_wavefunction_cache(qapp, tmp_path, monkeypatch):
    """The store-level guarantee (tests/test_quantum_chemistry_run.py) is
    that delete() only removes the project record; this confirms the panel's
    Delete button doesn't add its own cache-purging on top of that."""
    from openchem import paths as app_paths

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setattr(app_paths, "cache_root", lambda: cache_root)
    marker = cache_root / "some_cache_entry"
    marker.mkdir()

    panel, store, _molecule, _run_older, run_newer = _two_nmr_runs(qapp)

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    panel._on_delete_run_clicked()

    assert marker.exists()


def test_compare_runs_opens_a_dialog_for_two_compatible_runs(qapp, monkeypatch):
    panel, _store, molecule, run_older, run_newer = _two_nmr_runs(qapp)

    import openchem.ui.panels.quantum_chemistry_panel as panel_module

    opened = {}

    class _FakeDialog:
        def __init__(self, outcome, symbols, molecule_name, parent=None):
            opened["outcome"] = outcome
            opened["symbols"] = symbols
            opened["molecule_name"] = molecule_name

        def setAttribute(self, *_a, **_k):
            pass

        def show(self):
            opened["shown"] = True

    monkeypatch.setattr(panel_module, "CompareResultsDialog", _FakeDialog)
    monkeypatch.setattr(
        panel_module.QInputDialog, "getItem", staticmethod(lambda *a, **k: (a[3][0], True))
    )
    # A real QMessageBox.information() would block forever waiting for a
    # click nobody sends -- if compare() unexpectedly refuses (this test's
    # own hang, once, on a real bug: both runs' PerAtomDataset used
    # method="orca" regardless of method_basis, so compare() saw "the same
    # result twice"), fail loudly instead of hanging.
    def _unexpected_refusal(_parent, _title, text):
        raise AssertionError(f"compare() refused unexpectedly: {text}")

    monkeypatch.setattr(panel_module.QMessageBox, "information", _unexpected_refusal)

    panel._on_compare_runs_clicked()

    assert opened.get("shown") is True
    assert opened["molecule_name"] == molecule.display_name
    assert len(opened["outcome"].columns) == 2


def test_compare_runs_refuses_when_structures_differ(qapp, monkeypatch):
    """compare() itself refuses on a fingerprint mismatch -- this proves
    the panel surfaces that refusal rather than silently comparing the
    wrong atoms or crashing."""
    panel, store, molecule, run_older, run_newer = _two_nmr_runs(qapp)
    from dataclasses import replace

    edited = replace(run_older, input_fingerprint="fp-different")
    store.qc_runs.delete(run_older.run_id)
    store.qc_runs.record(edited)
    panel._refresh_active_run()
    panel._runs_combo.setCurrentIndex(0)  # newest (run_newer) active

    import openchem.ui.panels.quantum_chemistry_panel as panel_module

    told = []
    monkeypatch.setattr(
        panel_module.QMessageBox, "information", lambda parent, title, text: told.append(text)
    )
    monkeypatch.setattr(
        panel_module.QInputDialog, "getItem", staticmethod(lambda *a, **k: (a[3][0], True))
    )

    panel._on_compare_runs_clicked()

    assert told and "edited" in told[0].lower()


def test_compare_runs_refuses_two_runs_at_the_same_method(qapp, monkeypatch):
    """Two executions of the IDENTICAL calculation (same method/basis) are
    two separate history entries (run_id), but comparing their NMR shifts
    is a table of zeros -- compare() should refuse it as the same result
    twice, and the panel must build the PerAtomDataset so that refusal can
    actually fire (method=method_basis, not method=provider, which would
    make EVERY pair of ORCA runs look identical to compare())."""
    panel, store, molecule, run_older, run_newer = _two_nmr_runs(qapp)
    from dataclasses import replace

    same_method = replace(run_older, method_basis=run_newer.method_basis)
    store.qc_runs.delete(run_older.run_id)
    store.qc_runs.record(same_method)
    panel._refresh_active_run()
    panel._runs_combo.setCurrentIndex(0)

    import openchem.ui.panels.quantum_chemistry_panel as panel_module

    told = []
    monkeypatch.setattr(
        panel_module.QMessageBox, "information", lambda parent, title, text: told.append(text)
    )
    monkeypatch.setattr(
        panel_module.QInputDialog, "getItem", staticmethod(lambda *a, **k: (a[3][0], True))
    )

    panel._on_compare_runs_clicked()

    assert told and "twice" in told[0].lower()


def test_a_stored_runs_output_conformer_is_resolved_by_id_not_list_position(qapp):
    """Two conformers exist (e.g. from two different runs' optimizations);
    selecting the OLDER run must show ITS geometry, not whichever conformer
    a later run most recently added."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
    from openchem.services.result_store_service import ResultStoreService

    bus = EventBus()
    engine = _Engine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    store_service = ResultStoreService(bus, engine, settings)

    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=7)
    old_conformer = ConformerModel(molblock="OLD GEOMETRY", method="orca_opt")
    new_conformer = ConformerModel(molblock="NEW GEOMETRY", method="orca_opt")
    molecule.conformers.extend([old_conformer, new_conformer])
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    store_service.set_project(project)

    old_run = QuantumChemistryRun(
        run_id="run-old",
        molecule_uuid=molecule.uuid,
        calc_type="opt",
        method_basis="B3LYP def2-SVP",
        charge=0,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="fp-a",
        input_molblock=Chem.MolToMolBlock(mol_3d),
        output_conformer_id=old_conformer.conformer_id,
        status=RunStatus.COMPLETED,
        started_at=1.0,
    )
    new_run = QuantumChemistryRun(
        run_id="run-new",
        molecule_uuid=molecule.uuid,
        calc_type="opt",
        method_basis="B3LYP def2-SVP",
        charge=0,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="fp-b",
        input_molblock=Chem.MolToMolBlock(mol_3d),
        output_conformer_id=new_conformer.conformer_id,
        status=RunStatus.COMPLETED,
        started_at=2.0,
    )
    store_service.record_quantum_chemistry_run(old_run)
    store_service.record_quantum_chemistry_run(new_run)

    panel = QuantumChemistryPanel(
        service, engine, settings, bus, result_store_service=store_service
    )
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)

    # Newest run is shown by default.
    assert panel._active_run is new_run
    assert panel._optimized_conformer_molblock == "NEW GEOMETRY"

    panel._render_run(old_run)
    assert panel._optimized_conformer_molblock == "OLD GEOMETRY"


def test_running_ir_after_nmr_clears_the_stale_correlation_tables(qapp):
    """Flagged from real screenshots as a possible regression: NMR
    populates HSQC/HMBC/COSY, then a separate IR run on the same molecule
    must not leave the OLD NMR-run rows sitting in those tables under the
    new run's heading. `_on_run_clicked` already calls
    `_reset_empty_states()` with a comment saying exactly this must not
    happen -- this proves whether it still holds."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from openchem.domain.scientific_result import VibrationalSpectrumResult

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

    # Run 1: NMR -- populates HSQC/HMBC/COSY.
    panel._calc_type_combo.setCurrentText("NMR (raw shielding)")
    panel._on_run_clicked()
    values = {idx: 100.0 + idx for idx in range(mol_3d.GetNumAtoms())}
    elements = {idx: atom.GetSymbol() for idx, atom in enumerate(mol_3d.GetAtoms())}
    panel._on_spectrum_computed(
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
    assert panel._correlation_tables["hsqc"].rowCount() > 0
    assert panel._correlation_tables["cosy"].rowCount() > 0

    # Run 2: IR -- a separate calculation, no NMR data at all.
    panel._calc_type_combo.setCurrentText("Optimization + Frequency")
    panel._on_run_clicked()
    panel._on_spectrum_computed(
        SpectrumComputed(
            spectrum=VibrationalSpectrumResult(
                spectrum_type="ir",
                name="IR",
                units="cm-1",
                method="orca",
                molecule_uuid=molecule.uuid,
                modes=(),
            )
        )
    )

    assert panel._correlation_tables["hsqc"].rowCount() == 0, (
        "HSQC still shows the previous NMR run's rows after a separate IR run"
    )
    assert panel._correlation_tables["cosy"].rowCount() == 0, (
        "COSY still shows the previous NMR run's rows after a separate IR run"
    )
    assert not panel._correlation_plots["hsqc"]._peaks, (
        "the HSQC plot still holds the previous NMR run's peaks after a separate IR run"
    )
    assert not panel._correlation_plots["cosy"]._peaks


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


def test_a_stored_nmr_run_fills_the_1d_signal_view_from_its_3d_structure(qapp):
    """A run chosen from the Runs combo has no 2D drawing, only the structure ORCA was given. The 1D tab used
    to stay on its "No NMR signals" placeholder for it (a table under an empty tab), which also hid anything
    drawn onto that view, such as tautomer peaks."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus

    panel, engine, _service = _make_panel()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=7)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    run = QuantumChemistryRun(
        run_id="stored", molecule_uuid=molecule.uuid, calc_type="nmr", method_basis="HF STO-3G", charge=0,
        multiplicity=1, calculation_input="geometry", input_fingerprint="f",
        input_molblock=Chem.MolToMolBlock(mol_3d), status=RunStatus.COMPLETED,
    )
    run.results["spectrum"] = NMRSpectrumResult(
        spectrum_type="nmr_calibrated", name="Chemical Shift", units="ppm", method="orca",
        molecule_uuid=molecule.uuid, values={i: 1.0 + i for i in range(mol_3d.GetNumAtoms())},
        elements={i: a.GetSymbol() for i, a in enumerate(mol_3d.GetAtoms())},
    )
    panel._render_run(run)
    assert panel._nmr_view is not None
    assert sorted(s.integration for s in panel._nmr_view.signals()) == [1, 2, 3]


def _panel_with_conformers(count: int):
    """A molecule carrying `count` real embedded conformers, since the
    Boltzmann path only engages when there is more than one to average."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    panel, engine, service = _make_panel()
    molecule = MoleculeModel(display_name="Butane")
    engine.set_structure_from_smiles(molecule, "CCCC")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCCC"))
    AllChem.EmbedMultipleConfs(mol_3d, numConfs=count, randomSeed=42)
    for conf_id in range(count):
        molecule.conformers.append(
            ConformerModel(molblock=Chem.MolToMolBlock(mol_3d, confId=conf_id), method="rdkit_etkdg")
        )
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("B3LYP pcSseg-1")
    return panel, service, molecule


def test_boltzmann_is_off_by_default(qapp):
    panel, _engine, _service = _make_panel()
    assert not panel._boltzmann_check.isChecked()


def test_unchecked_boltzmann_runs_the_single_lowest_energy_conformer(qapp):
    panel, service, _molecule = _panel_with_conformers(3)

    panel._on_run_clicked()

    assert len(service.requests) == 1
    assert service.boltzmann_requests == []


def test_checked_boltzmann_sends_every_conformer(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    panel._boltzmann_check.setChecked(True)

    panel._on_run_clicked()

    assert service.requests == []
    assert len(service.boltzmann_requests) == 1
    assert len(service.boltzmann_requests[0]["mols"]) == len(molecule.conformers) == 3


def test_checked_boltzmann_with_one_conformer_takes_the_ordinary_path(qapp):
    """Nothing to average over -- routing it through the sequencing code
    would only add a layer for no benefit."""
    panel, service, _molecule = _panel_with_conformers(1)
    panel._boltzmann_check.setChecked(True)

    panel._on_run_clicked()

    assert len(service.requests) == 1
    assert service.boltzmann_requests == []


# --- the identity a run is submitted with ------------------------------------


def test_a_single_run_is_submitted_with_its_conformers_identity(qapp):
    from openchem.chem.calculation_input import input_fingerprint
    from openchem.domain.calculator import GEOMETRY

    panel, service, molecule = _panel_with_conformers(3)

    panel._on_run_clicked()

    request = service.requests[0]
    assert request["calculation_input"] == GEOMETRY
    assert request["input_fingerprint"] == input_fingerprint(ChemistryEngine(), molecule, GEOMETRY)


def test_a_boltzmann_run_is_submitted_with_the_identity_of_exactly_its_set(qapp):
    from openchem.chem.calculation_input import input_fingerprint
    from openchem.domain.calculator import ENSEMBLE

    panel, service, molecule = _panel_with_conformers(3)
    panel._boltzmann_check.setChecked(True)

    panel._on_run_clicked()

    request = service.boltzmann_requests[0]
    assert request["calculation_input"] == ENSEMBLE
    assert request["input_fingerprint"] == input_fingerprint(ChemistryEngine(), molecule, ENSEMBLE)
    assert len(request["mols"]) == 3


def test_a_conformer_without_3d_coordinates_is_refused_not_run_on_the_drawing(qapp):
    """The resolver falls back to the DRAWING for a flat conformer, and the
    drawing has no hydrogens: ORCA would compute a plausible-looking answer
    for a different molecule. Refused on the resolver's stated `used`."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    panel, engine, service = _make_panel()
    molecule = MoleculeModel(display_name="Water")
    engine.set_structure_from_smiles(molecule, "O")
    flat = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.Compute2DCoords(flat)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(flat), method="flat"))
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_run_clicked()

    assert service.requests == [] and service.boltzmann_requests == []
    assert "3d" in panel._status_label.text().lower()
    assert panel._run_button.isEnabled(), "a refusal must leave the panel ready to run"


def test_a_boltzmann_set_with_a_flat_member_is_refused_before_the_panel_commits(qapp):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    panel, service, molecule = _panel_with_conformers(2)
    flat = Chem.AddHs(Chem.MolFromSmiles("CCCC"))
    AllChem.Compute2DCoords(flat)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(flat), method="flat"))
    panel._boltzmann_check.setChecked(True)

    panel._on_run_clicked()

    assert service.requests == [] and service.boltzmann_requests == []
    assert "conformer 3" in panel._status_label.text().lower()
    assert panel._run_button.isEnabled()


def test_what_a_run_publishes_comes_from_its_submission_not_the_panel_later(qapp, tmp_path, monkeypatch):
    """THE SUBMISSION SNAPSHOT IS THE ONLY SOURCE. Against the REAL service
    with a slow job: while it runs, the panel's charge, multiplicity and
    method change and the molecule gains a conformer. The published spectrum
    must still name what was submitted -- both its identity and its run
    record -- because a result described from the panel at finish would
    describe a calculation nobody ran."""
    import sys
    import time
    from pathlib import Path

    from rdkit import Chem

    from openchem import paths as app_paths
    from openchem.chem.calculation_input import input_fingerprint
    from openchem.domain.calculator import ENSEMBLE
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.events.events import QuantumChemistryJobStateChanged
    from openchem.plugins.interfaces import QuantumEngineProvider

    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(tmp_path / "data-root"))

    class _SlowNmr(QuantumEngineProvider):
        # Registered under the id the panel submits with, so the panel's own
        # call reaches it unmodified.
        provider_id = "orca"

        def build_input(self, mol, charge, multiplicity, method_basis, calc_type):
            return "fake"

        def command_args(self, executable_path, input_path: Path):
            return [executable_path, "-c", "import time; time.sleep(0.6)"]

        def parse_output(self, output_text, mol, molecule_uuid, calc_type):
            energy = DescriptorValue(
                descriptor_id="orca.scf_energy", name="E", units="Hartree",
                category="quantum_chemistry", provider="orca", molecule_uuid=molecule_uuid,
                value=-1.0, cache_state=CacheState.COMPLETED,
            )
            return [energy], None

        def parse_spectrum_output(self, output_text, mol, molecule_uuid, calc_type):
            from openchem.domain.common import Provenance

            # With provenance, as the real ORCA parser always gives it: the
            # Boltzmann average records its conformer count only onto one.
            return NMRSpectrumResult(
                spectrum_type="nmr_raw_shielding", name="NMR", units="ppm", method="orca",
                molecule_uuid=molecule_uuid, values={0: 30.0}, elements={0: "C"},
                provenance=Provenance(created_by="core", method="orca", parameters={"orca_version": "fake"}),
            )

    from rdkit.Chem import AllChem

    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    real = QuantumChemistryService(bus, settings, providers={"orca": _SlowNmr()})
    panel = QuantumChemistryPanel(real, engine, settings, bus)
    molecule = MoleculeModel(display_name="Butane")
    engine.set_structure_from_smiles(molecule, "CCCC")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCCC"))
    AllChem.EmbedMultipleConfs(mol_3d, numConfs=2, randomSeed=42)
    for conf_id in range(2):
        molecule.conformers.append(
            ConformerModel(molblock=Chem.MolToMolBlock(mol_3d, confId=conf_id), method="rdkit_etkdg")
        )
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("B3LYP pcSseg-1")
    submitted = input_fingerprint(ChemistryEngine(), molecule, ENSEMBLE)
    events: list[SpectrumComputed] = []
    bus.subscribe(SpectrumComputed, events.append)
    states: list = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    panel._boltzmann_check.setChecked(True)
    panel._charge_spin.setValue(0)
    panel._multiplicity_spin.setValue(1)
    panel._on_run_clicked()

    # Everything the panel or model could say about the run, changed mid-run.
    panel._charge_spin.setValue(3)
    panel._multiplicity_spin.setValue(4)
    panel._method_combo.setCurrentText("HF STO-3G")
    molecule.conformers.append(ConformerModel(molblock=molecule.conformers[0].molblock, method="added"))

    deadline = time.time() + 30
    while not (states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED)) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)

    assert states and states[-1] == CacheState.COMPLETED, states
    assert [(e.input_fingerprint, e.calculation_input) for e in events] == [(submitted, ENSEMBLE)]
    assert input_fingerprint(ChemistryEngine(), molecule, ENSEMBLE) != submitted, "setup: the set changed"
    parameters = events[0].spectrum.provenance.parameters if events[0].spectrum.provenance else {}
    assert (parameters.get("run_charge"), parameters.get("run_multiplicity")) == (0, 1)
    assert parameters.get("run_method_basis") == "B3LYP pcSseg-1"
    assert parameters.get("boltzmann_conformers") == 2


def _ethanol_panel(bus, engine, settings, service):
    """A panel with a real ethanol conformer, run-clicked so the panel holds
    the mol its hybrid merge needs."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    panel = QuantumChemistryPanel(service, engine, settings, bus)
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=7)
    molecule.conformers.append(
        ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg")
    )
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("B3LYP def2-SVP")
    panel._on_run_clicked()
    return panel, molecule, mol_3d


def test_the_hybrid_tab_refuses_an_unscaled_spectrum(qapp):
    """TMS referencing removes an offset but not the scale error, so
    merging those values into measured ones would put part of the spectrum
    on a different scale -- a step that reads as chemistry."""
    from openchem.domain.common import Provenance

    bus = EventBus()
    engine = ChemistryEngine()
    panel, molecule, mol_3d = _ethanol_panel(
        bus, engine, Settings(bus), _RecordingQuantumChemistryService(bus)
    )

    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_13c",
                name="TMS referenced",
                units="ppm",
                method="orca",
                molecule_uuid=molecule.uuid,
                values={0: 15.0, 1: 58.0},
                elements={0: "C", 1: "C"},
                provenance=Provenance(created_by="core", method="orca", parameters={"referencing": "tms"}),
            )
        )
    )

    assert panel._hybrid_table.rowCount() == 0
    assert "empirically scaled" in panel._hybrid_summary_label.text()


def test_the_hybrid_tab_picks_each_atoms_less_wrong_method(qapp, monkeypatch):
    """The wiring end to end: a well-covered carbon keeps the database
    value, a poorly covered one takes the calculation."""
    from openchem.chem import nmr_database
    from openchem.domain.common import CacheState, Provenance

    bus = EventBus()
    engine = ChemistryEngine()
    panel, molecule, mol_3d = _ethanol_panel(
        bus, engine, Settings(bus), _RecordingQuantumChemistryService(bus)
    )

    def fake_predict(mol, molecule_uuid, element="C", **kwargs):
        if element != "C":
            return NMRSpectrumResult(
                spectrum_type="nmr_1h",
                name="H NMR (database)",
                units="ppm",
                method="hose_lookup",
                molecule_uuid=molecule_uuid,
                cache_state=CacheState.FAILED,
                error="nothing indexed",
            )
        return NMRSpectrumResult(
            spectrum_type="nmr_13c",
            name="C NMR (database)",
            units="ppm",
            method="hose_lookup",
            molecule_uuid=molecule_uuid,
            values={0: 18.3, 1: 52.0},
            elements={0: "C", 1: "C"},
            cache_state=CacheState.COMPLETED,
            provenance=Provenance(
                created_by="core",
                method="hose_lookup",
                parameters={
                    "per_atom": {
                        "0": {"quality": "good", "matches": 40, "spheres": 4},
                        "1": {"quality": "rough", "matches": 1, "spheres": 2},
                    }
                },
            ),
        )

    monkeypatch.setattr(nmr_database, "predict_spectrum", fake_predict)

    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_13c",
                name="scaled",
                units="ppm",
                method="orca",
                molecule_uuid=molecule.uuid,
                values={0: 18.6, 1: 58.4},
                elements={0: "C", 1: "C"},
                provenance=Provenance(
                    created_by="core",
                    method="orca",
                    parameters={
                        "referencing": "empirical_linear_scaling",
                        "scaling_C": {
                            "slope": -1.04,
                            "intercept": 186.2,
                            "r_squared": 0.998,
                            "sample_count": 7,
                            "residual_rms": 1.5,
                        },
                    },
                ),
            )
        )
    )

    rows = {
        panel._hybrid_table.item(row, 0).text(): (
            panel._hybrid_table.item(row, 2).text(),
            panel._hybrid_table.item(row, 3).text(),
        )
        for row in range(panel._hybrid_table.rowCount())
    }
    assert rows == {"0": ("18.300", "trusted lookup"), "1": ("58.400", "ORCA (scaled)")}
    summary = panel._hybrid_summary_label.text()
    assert "1 ORCA (scaled)" in summary and "1 trusted lookup" in summary
    assert "calibration check passed against 1 trusted values" in summary


# --- detached views and the tab machinery ----------------------------------
#
# The correlation plots are built eagerly in `__init__`, so their hosts
# exist without a job having run -- which is what makes these testable
# without an ORCA backend.


def _a_correlation_host(panel):
    """One PopOutHost from a correlation tab, with its tab index."""
    from openchem.ui.widgets.pop_out_host import PopOutHost

    for index in range(panel._correlation_tabs.count()):
        tab = panel._correlation_tabs.widget(index)
        hosts = tab.findChildren(PopOutHost)
        if hosts:
            return index, tab, hosts[0]
    raise AssertionError("no correlation tab carries a PopOutHost")


def test_a_detached_view_survives_switching_to_another_tab(qapp):
    """LOOKING AWAY IS NOT A RESET.

    Switching tab, switching dock, hiding the dock and floating it are
    all `hideEvent` on the tab page. If `PopOutHost` grew a `hideEvent`
    hook -- which is the obvious way to write "put it back when the panel
    goes away" -- the window would snap shut every time the user glanced
    at another tab, which is the opposite of why anyone detaches a view.
    """
    panel, _engine, _service = _make_panel()
    index, _tab, host = _a_correlation_host(panel)

    # THE PANEL IS SHOWN, and that is the whole test.
    #
    # The first version of this did not show it, and a `hideEvent` hook
    # mutation walked straight through: a widget that was never shown
    # receives no hide events at all, so the guard was asserting on code
    # that never ran. Mutation is what found it -- the test read
    # perfectly well and proved nothing.
    panel._correlation_tabs.setVisible(True)
    panel.show()
    panel._correlation_tabs.setCurrentIndex(index)
    qapp.processEvents()
    assert host.isVisible(), "setup: the host must be on screen before it can be hidden"

    host.pop_out()

    other = (index + 1) % panel._correlation_tabs.count()
    panel._correlation_tabs.setCurrentIndex(other)
    qapp.processEvents()

    # SETUP ASSERTION: switching the tab really did hide the host. Without
    # this the claim below is about a hide that never happened.
    assert not host.isVisible(), "setup: switching tabs did not hide the host"

    assert host.is_popped_out(), "switching tabs must not bring a detached view home"

    host.return_home()
    _dispose_panel(panel)


def test_resetting_the_empty_states_brings_a_detached_view_home(qapp):
    """A NEW JOB IS A SEMANTIC RESET, and this is the one thing that
    returns a view.

    Without it, starting a job blanks the tab back to its placeholder
    while a window on another monitor goes on showing the PREVIOUS run's
    result -- a stale picture with nothing anywhere saying so. Hiding the
    host does not close the window its content is sitting in.
    """
    panel, _engine, _service = _make_panel()
    _index, _tab, host = _a_correlation_host(panel)
    content = host.content()
    host.pop_out()
    assert host.is_popped_out()

    panel._reset_empty_states()

    assert not host.is_popped_out()
    assert content.parentWidget() is host
    _dispose_panel(panel)


def test_the_host_is_reusable_after_a_reset(qapp):
    """A one-shot state machine passes a test that only ever goes out
    once, so this goes out, is reset, and goes out again."""
    panel, _engine, _service = _make_panel()
    _index, _tab, host = _a_correlation_host(panel)

    first = host.pop_out()
    panel._reset_empty_states()
    second = host.pop_out()

    assert second is not first
    assert host.is_popped_out()

    host.return_home()
    _dispose_panel(panel)


def test_the_placeholder_message_is_not_shadowed_by_a_pop_out_host(qapp):
    """`empty_message_for_tab` returns the FIRST `is_empty_state` widget it
    finds anywhere under a tab, via `findChildren`.

    So building `PopOutHost`'s "showing in its own window" placeholder
    with `empty_state()` -- the helper whose name sounds exactly right --
    would put a hidden marked label inside every host, and every wrapped
    tab would start answering for itself with the pop-out's message
    instead of its own. It is a plain `QLabel` for that reason.
    """
    panel, _engine, _service = _make_panel()

    for index in range(panel._correlation_tabs.count()):
        message = panel.empty_message_for_tab(index)
        assert "own window" not in message, (
            f"tab {index} is answering with a pop-out placeholder: {message!r}"
        )

    # ...and the real messages are still there, so this is not passing
    # because every tab went silent.
    messages = [
        panel.empty_message_for_tab(index)
        for index in range(panel._correlation_tabs.count())
    ]
    assert all(text.strip() for text in messages), messages
    _dispose_panel(panel)


def test_wrapping_a_view_does_not_change_the_tabs_content_classification(qapp):
    """The integration invariant for this panel, stated directly.

    `_content_of` walks `tab.children()` -- DIRECT children only -- so a
    host becomes that direct child and `_fill_tab` goes on showing and
    hiding exactly one thing. This works BECAUSE the host is a real
    widget in the tab rather than a transparent wrapper, and it is the
    property that would break first if somebody made it one.
    """
    panel, _engine, _service = _make_panel()
    index, tab, host = _a_correlation_host(panel)

    state, content = panel._content_of(tab)
    assert host in content, "the host must be the tab's own direct child"
    assert state is None or not any(
        host.isAncestorOf(widget) for widget in [state]
    ), "the placeholder must not have ended up inside the host"
    _dispose_panel(panel)


def test_the_tautomer_summary_says_how_a_stereo_search_chose_its_energies():
    """The dialog's own text, not just the Results entry: it is what the user
    reads beside the energies the stereo search produced."""
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import StructureSetResult

    def summary(**parameters):
        base = {"candidate_count_succeeded": 3, "candidate_count_failed": 0}
        base.update(parameters)
        result = StructureSetResult(
            set_id="orca.tautomer_distribution", name="t", method="orca", molecule_uuid="m",
            entries=[], provenance=Provenance(created_by="core", method="orca", parameters=base),
        )
        return QuantumChemistryPanel._tautomer_distribution_summary(result)

    searched = summary(stereo_search=True)
    assert "lowest successful stereoisomer" in searched and "truncated" not in searched
    assert "stereoisomer" not in summary(stereo_search=False)
    truncated = summary(stereo_search=True, stereo_enumeration_truncated=2, stereo_enumeration_cap=8)
    assert "truncated for 2 tautomer(s)" in truncated and "no population percentages" in truncated


def test_show_spectrum_tab_selects_the_named_tab_and_nothing_else():
    panel, _engine, _service = _make_panel()

    assert panel.show_spectrum_tab("ir") is True
    assert panel._correlation_tabs.currentWidget() is panel._ir_view_tab
    assert panel.show_spectrum_tab("nmr") is True
    assert panel._correlation_tabs.currentWidget() is panel._nmr_view_tab
    assert panel.show_spectrum_tab("surfaces") is False
    assert panel._correlation_tabs.currentWidget() is panel._nmr_view_tab


def test_the_report_links_reveal_the_panel_and_select_its_tab():
    """`Open IR` / `Open NMR` with no spectrum named: reveal the Quantum
    Chemistry panel AND land on the matching tab (previously the panel only)."""
    from types import SimpleNamespace

    from openchem.app.main_window import MainWindow

    panel, _engine, _service = _make_panel()
    chosen = []
    fake = SimpleNamespace(_on_panel_chosen=chosen.append, _quantum_chemistry_panel=panel)

    assert MainWindow._link_to_ir_view(fake, {}) is True
    assert chosen == ["Quantum_Chemistry"]
    assert panel._correlation_tabs.currentWidget() is panel._ir_view_tab
    assert MainWindow._link_to_nmr_view(fake, {}) is True
    assert panel._correlation_tabs.currentWidget() is panel._nmr_view_tab


def test_each_correlation_tab_has_a_reset_zoom_that_follows_its_own_plot(qapp):
    """Reset Zoom is enabled only while THAT tab's plot is zoomed. The handler
    reads the plot off `sender()`, so zooming one tab must not enable another's."""
    panel, _engine, _service = _make_panel()
    try:
        hsqc, cosy = panel._correlation_plots["hsqc"], panel._correlation_plots["cosy"]
        hsqc_button = hsqc.property("reset_zoom_button")
        cosy_button = cosy.property("reset_zoom_button")
        assert not hsqc_button.isEnabled() and not cosy_button.isEnabled()

        hsqc._view_x_range = (0.0, 1.0)
        hsqc.view_changed.emit()
        assert hsqc_button.isEnabled() and not cosy_button.isEnabled()

        hsqc_button.click()
        assert not hsqc.is_zoomed() and not hsqc_button.isEnabled()
    finally:
        _dispose_panel(panel)


def test_the_tautomer_dialog_exports_the_result_it_shows_as_csv(qapp, tmp_path, monkeypatch):
    """The grid shows captions; the file has the numbers at full precision."""
    from PySide6.QtWidgets import QFileDialog, QPushButton
    from rdkit import Chem

    from openchem.chem.tautomer_distribution import (
        CandidateResult,
        CandidateStatus,
        build_outcome,
        build_structure_set_result,
    )

    def block(smiles):
        mol = Chem.MolFromSmiles(smiles)
        return Chem.MolToMolBlock(mol)

    outcome = build_outcome([
        CandidateResult("a", block("CCO"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-154.1234567),
        CandidateResult("b", block("CC=O"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-154.1),
    ])
    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-1")
    target = tmp_path / "t.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    panel, _engine, _service = _make_panel()
    try:
        panel._open_tautomer_distribution_dialog(result)
        dialog = panel._tautomer_distribution_dialog
        button = next(b for b in dialog.findChildren(QPushButton) if b.text().startswith("Export table"))

        button.click()

        lines = target.read_text(encoding="utf-8-sig").splitlines()
        assert lines[0].startswith("Structure,Status,Tautomer state")
        assert len(lines) == 3 and "-154.1234567" in lines[1] + lines[2]
        dialog.close()
    finally:
        _dispose_panel(panel)


# --- the conformer-search setting (model revision 4) -----------------------------------


def _run_tautomers(monkeypatch, full: bool):
    from openchem.chem import tautomer_distribution as td

    panel, engine, service = _make_panel()
    project = ProjectModel(name="Test")
    project.molecules.append(_cyclohexanone_molecule(engine))
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")
    panel._tautomer_full_check.setChecked(full)
    panel._on_tautomer_distribution_clicked()
    return panel, service, td


def test_the_full_orca_conformers_box_is_off_by_default_and_runs_the_top_k_model(monkeypatch):
    panel, service, td = _run_tautomers(monkeypatch, full=False)

    assert panel._tautomer_full_check.text() == "Full ORCA conformers"
    request = service.tautomer_distribution_requests[0]
    assert request["policy"] is td.MODEL_POLICY_TOPK
    assert all(c.conformer.search == "mmff_topk" for c in request["candidates"])


def test_ticking_full_orca_conformers_runs_the_other_model_and_remembers_the_choice(monkeypatch):
    panel, service, td = _run_tautomers(monkeypatch, full=True)

    request = service.tautomer_distribution_requests[0]
    assert request["policy"] is td.MODEL_POLICY_FULL
    assert all(c.conformer.search == "full_orca" for c in request["candidates"])
    assert panel._stored_tautomer_full_mode() is True


def test_the_two_settings_name_different_model_versions(monkeypatch):
    from openchem.chem.tautomer_distribution import model_version

    _panel, top_service, td = _run_tautomers(monkeypatch, full=False)
    _panel2, full_service, _td = _run_tautomers(monkeypatch, full=True)
    top = top_service.tautomer_distribution_requests[0]["policy"]
    full = full_service.tautomer_distribution_requests[0]["policy"]

    assert model_version("M062X def2-TZVP", "ETKDGv3", 298.15, top) != model_version(
        "M062X def2-TZVP", "ETKDGv3", 298.15, full
    )


def test_the_summary_names_the_conformer_search_and_says_it_is_not_exhaustive():
    from openchem.chem import tautomer_distribution as td
    from rdkit import Chem

    candidates, _ = td.generate_tautomer_candidates(Chem.MolFromSmiles("CCCCO"))
    outcome = td.build_outcome(
        [
            td.CandidateResult.for_candidate(c, "", td.CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0 - 0.001 * i)
            for i, c in enumerate(candidates)
        ]
    )
    result = td.build_structure_set_result(outcome, "m", "M062X def2-TZVP", run_id="r")

    text = QuantumChemistryPanel._tautomer_distribution_summary(result)

    assert "Conformer search: MMFF top-3 of" in text and "not exhaustive" in text
