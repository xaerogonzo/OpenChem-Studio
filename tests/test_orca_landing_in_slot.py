"""Where a finished ORCA optimisation lands, and when it must not.

THE REAL `MainWindow`, because the two claims here live in its handler and nowhere a helper test reaches:
the geometry goes in the slot of the conformer it was optimised from (and the viewer shows it), and a job that
finishes after its molecule's structure was edited installs NOTHING and publishes nothing as current.

**The stale cases are asserted against a recording of every event on the bus**, not against the handler's
view of the world. The check must not depend on whether `ConformersInvalidated` fired: that event is only
published when there are conformers to clear, so a molecule that held none (the generation undone, then the
structure edited) never raises it. Case (a) below is exactly that route.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import canonical_conformer, geometry_fingerprint
from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.isotopes import set_isotope
from openchem.commands.molecule_commands import EditStructureCommand
from openchem.domain.common import CacheState
from openchem.domain.conformer import (
    OPTIMIZED_FROM_ID,
    OPTIMIZED_FROM_SLOT,
    ORCA_OPTIMIZED,
    ConformerModel,
)
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.events.events import (
    ConformersChanged,
    ConformersInvalidated,
    DescriptorComputed,
    QuantumChemistryResultReady,
)

_WINDOWS: list = []

HEXANOL = "CCCCCCO"
SLOT = 6  # "7 of 20"


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def _build_window(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    window = MainWindow(services, settings, SessionManager())
    _WINDOWS.append(window)
    return window, services


class _Recorder:
    """Every event the landing could be judged by, recorded as it happens."""

    def __init__(self, bus) -> None:
        self.changed: list[ConformersChanged] = []
        self.invalidated: list[ConformersInvalidated] = []
        self.descriptors: list[DescriptorComputed] = []
        bus.subscribe(ConformersChanged, self.changed.append)
        bus.subscribe(ConformersInvalidated, self.invalidated.append)
        bus.subscribe(DescriptorComputed, self.descriptors.append)

    def qc_numbers(self) -> list[DescriptorComputed]:
        return [d for d in self.descriptors if d.descriptor.descriptor_id == "orca.scf_energy"]


def _molecule(services, smiles: str = HEXANOL, count: int = 20) -> MoleculeModel:
    """A molecule with `count` conformers: three real embeddings cycled, each its own object with its own id,
    so a replacement in one slot can be told from the others."""
    molecule = MoleculeModel(display_name="Test")
    services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
    generated = RDKitConformerProvider(random_seed=0xC0FFEE).generate_conformers(
        services.chemistry_engine.mol_from_model(molecule), num_conformers=3, optimize=True
    )
    blocks = [(services.chemistry_engine.mol_to_molblock(mol), energy) for mol, energy in generated]
    molecule.conformers = [
        ConformerModel(molblock=blocks[i % len(blocks)][0], energy=float(i), method="mmff94") for i in range(count)
    ]
    return molecule


def _map_source(services, source: ConformerModel) -> None:
    atoms = services.chemistry_engine.mol_from_molblock(source.molblock).GetNumAtoms()
    source.drawing_atom_ids = list(range(atoms))
    source.drawing_fingerprint = "drawing-at-creation"


def _orca_result(source: ConformerModel, molecule: MoleculeModel, identity: str | None = None, **overrides):
    """What the service publishes for an optimisation of `source`: no energy, no map, the engine's provenance."""
    optimized = ConformerModel(molblock=source.molblock, energy=None, method=ORCA_OPTIMIZED)
    descriptor = DescriptorValue(
        descriptor_id="orca.scf_energy", name="SCF energy", units="Eh", category="quantum_chemistry",
        provider="orca", molecule_uuid=molecule.uuid, value=-1.0, cache_state=CacheState.COMPLETED,
    )
    fields = dict(
        molecule_uuid=molecule.uuid,
        descriptors=[descriptor],
        conformer=optimized,
        input_fingerprint=geometry_fingerprint(source),
        structure_identity=molecule.canonical_smiles if identity is None else identity,
        # One-based, as the panel stamps it when Run is pressed.
        source_slot=molecule.conformers.index(source) + 1 if source in molecule.conformers else 0,
    )
    fields.update(overrides)
    return QuantumChemistryResultReady(**fields), optimized


def _window_with(qapp, tmp_path, **molecule_kwargs):
    window, services = _build_window(qapp, tmp_path)
    molecule = _molecule(services, **molecule_kwargs)
    _map_source(services, molecule.conformers[SLOT])
    window.add_molecule(molecule)
    _drain(qapp)
    recorder = _Recorder(services.event_bus)
    return window, services, molecule, recorder


def _land(qapp, services, event) -> None:
    services.event_bus.publish(event)
    _drain(qapp)


# --- it lands in its slot ---------------------------------------------------------------------------------------


def test_the_result_replaces_its_source_in_slot_seven_of_twenty(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    before = list(molecule.conformers)
    source = before[SLOT]
    event, optimized = _orca_result(source, molecule)

    _land(qapp, services, event)

    assert len(molecule.conformers) == 20, "replaced, not appended"
    landed = molecule.conformers[SLOT]
    assert landed.conformer_id == optimized.conformer_id, "the run history names this id as its output"
    assert [c for i, c in enumerate(molecule.conformers) if i != SLOT] == [c for i, c in enumerate(before) if i != SLOT]
    assert landed.drawing_atom_ids == source.drawing_atom_ids and landed.drawing_fingerprint == "drawing-at-creation"
    assert landed.provenance.parameters[OPTIMIZED_FROM_ID] == source.conformer_id
    assert landed.provenance.parameters[OPTIMIZED_FROM_SLOT] == SLOT + 1
    assert canonical_conformer(molecule) is landed, "every later calculation uses it"
    assert [e.show_conformer_id for e in recorder.changed][-1] == landed.conformer_id
    assert len(recorder.qc_numbers()) == 1, "the numbers are published as current"


def test_undo_and_redo_keep_the_slot(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    event, optimized = _orca_result(source, molecule)
    _land(qapp, services, event)

    window._undo_stack.undo()
    _drain(qapp)
    assert molecule.conformers[SLOT] is source, "the very object that was there"
    assert len(molecule.conformers) == 20
    assert canonical_conformer(molecule).method != ORCA_OPTIMIZED, "the force-field rule applies again"

    window._undo_stack.redo()
    _drain(qapp)
    assert molecule.conformers[SLOT].conformer_id == optimized.conformer_id
    assert len(molecule.conformers) == 20


def test_the_viewer_in_the_window_lands_on_the_replaced_slot_and_says_orca(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    viewer = window._viewer3d
    viewer.set_molecule(molecule)
    _drain(qapp)
    assert viewer._conformer_index == 0
    event, _optimized = _orca_result(molecule.conformers[SLOT], molecule)

    _land(qapp, services, event)

    assert viewer._conformer_index == SLOT
    assert viewer._status_label.text().startswith(f"Conformer {SLOT + 1}/20 - ORCA optimized")


def test_when_the_conformers_were_regenerated_meanwhile_the_geometry_is_appended_and_shown(qapp, tmp_path):
    """The structure is unchanged, so the geometry is still the user's: added, and shown, not dropped."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    event, optimized = _orca_result(source, molecule)
    molecule.conformers = [ConformerModel(molblock=c.molblock, energy=c.energy, method="mmff94") for c in molecule.conformers]

    _land(qapp, services, event)

    assert len(molecule.conformers) == 21
    assert molecule.conformers[-1].conformer_id == optimized.conformer_id
    assert recorder.changed[-1].show_conformer_id == optimized.conformer_id
    assert len(recorder.qc_numbers()) == 1


def test_a_result_with_no_single_source_is_appended_and_shown(qapp, tmp_path):
    """A Boltzmann run's lowest conformer has no fingerprint to find a slot by."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    event, optimized = _orca_result(molecule.conformers[SLOT], molecule, input_fingerprint="")

    _land(qapp, services, event)

    assert len(molecule.conformers) == 21
    assert molecule.conformers[-1].conformer_id == optimized.conformer_id
    assert molecule.conformers[-1].drawing_atom_ids is None, "'not recorded' is never guessed"
    assert recorder.changed[-1].show_conformer_id == optimized.conformer_id


def test_a_result_without_a_conformer_publishes_its_numbers_and_touches_no_conformer(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    before = list(molecule.conformers)
    event, _optimized = _orca_result(molecule.conformers[SLOT], molecule, conformer=None)

    _land(qapp, services, event)

    assert molecule.conformers == before
    assert len(recorder.qc_numbers()) == 1


# --- it must NOT land on a structure it was not run on ---------------------------------------------------------


def _edit(window, services, molecule, new_smiles: str) -> None:
    """A real structure edit, through the real command, on the window's undo stack."""
    scratch = MoleculeModel()
    services.chemistry_engine.set_structure_from_smiles(scratch, new_smiles)
    window._undo_stack.push(EditStructureCommand(services.chemistry_engine, molecule, scratch.molblock, services.event_bus))
    _drain(QApplication.instance())


def _assert_withheld(window, molecule, recorder, conformers_before) -> None:
    assert molecule.conformers == conformers_before, "no conformer added, replaced or removed by the landing"
    assert recorder.qc_numbers() == [], "the numbers are NOT shown as current for the edited molecule"
    assert "edited while the ORCA job ran" in window.statusBar().currentMessage()


def test_a_molecule_with_no_conformers_and_no_invalidation_event_is_still_protected(qapp, tmp_path):
    """**THE CASE A SUBSCRIPTION TO `ConformersInvalidated` WOULD MISS.** Submit (conformers exist), undo the
    generation, edit the structure. There is nothing to clear, so the editor publishes no invalidation at all,
    and the job lands on a molecule it was not run on."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    event, _optimized = _orca_result(source, molecule)  # identity captured at submission: hexanol
    molecule.conformers = []  # what undoing the generation leaves

    _edit(window, services, molecule, "CCCCCCCO")

    assert molecule.canonical_smiles != event.structure_identity
    assert recorder.invalidated == [], "the premise: no ConformersInvalidated was ever published"
    _land(qapp, services, event)

    _assert_withheld(window, molecule, recorder, [])


def test_a_constitution_edit_with_conformers_present_is_withheld_too(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    event, _optimized = _orca_result(molecule.conformers[SLOT], molecule)

    _edit(window, services, molecule, "CCCCCCCO")

    assert len(recorder.invalidated) == 1, "the control: here the event DOES fire, and the answer is the same"
    assert molecule.conformers == []
    _land(qapp, services, event)
    _assert_withheld(window, molecule, recorder, [])


def test_a_stereochemistry_only_edit_is_withheld(qapp, tmp_path):
    window, services = _build_window(qapp, tmp_path)
    molecule = _molecule(services, smiles="C[C@H](F)Cl", count=3)
    window.add_molecule(molecule)
    _drain(qapp)
    recorder = _Recorder(services.event_bus)
    event, _optimized = _orca_result(molecule.conformers[1], molecule)

    _edit(window, services, molecule, "C[C@@H](F)Cl")

    _land(qapp, services, event)
    _assert_withheld(window, molecule, recorder, [])


def test_an_isotope_only_edit_still_lands(qapp, tmp_path):
    """The editor keeps the conformers through a mass label, so the geometry still fits."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    event, optimized = _orca_result(source, molecule)

    window._undo_stack.push(
        EditStructureCommand(services.chemistry_engine, molecule, set_isotope(molecule.molblock, 0, 13), services.event_bus)
    )
    _drain(qapp)
    assert "13" in molecule.canonical_smiles and len(molecule.conformers) == 20
    _land(qapp, services, event)

    assert molecule.conformers[SLOT].conformer_id == optimized.conformer_id
    assert len(recorder.qc_numbers()) == 1


def test_an_edit_that_leaves_the_structure_alone_still_lands(qapp, tmp_path):
    """Layout, Clean Up and dragging an atom change coordinates and not canonical SMILES."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    event, optimized = _orca_result(source, molecule)

    _edit(window, services, molecule, HEXANOL)  # a fresh drawing of the same molecule
    assert len(molecule.conformers) == 20, "the editor kept them"
    _land(qapp, services, event)

    assert molecule.conformers[SLOT].conformer_id == optimized.conformer_id
    assert recorder.invalidated == []


@pytest.mark.parametrize("identity", ["", "not a smiles"])
def test_an_identity_that_cannot_be_matched_is_withheld(qapp, tmp_path, identity):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    before = list(molecule.conformers)
    event, _optimized = _orca_result(molecule.conformers[SLOT], molecule, identity=identity)

    _land(qapp, services, event)

    _assert_withheld(window, molecule, recorder, before)


def test_a_boltzmann_style_result_for_an_edited_molecule_installs_nothing(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    event, _optimized = _orca_result(molecule.conformers[SLOT], molecule, input_fingerprint="")

    _edit(window, services, molecule, "CCCCCCCO")

    _land(qapp, services, event)
    _assert_withheld(window, molecule, recorder, [])


def test_a_boltzmann_style_result_for_an_unedited_molecule_installs_normally(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    event, optimized = _orca_result(molecule.conformers[SLOT], molecule, input_fingerprint="")

    _land(qapp, services, event)

    assert molecule.conformers[-1].conformer_id == optimized.conformer_id
    assert len(recorder.qc_numbers()) == 1


# --- regenerating -----------------------------------------------------------------------------------------------


def _regenerate(qapp, services, molecule, count: int = 3) -> list[ConformerModel]:
    from openchem.events.events import ConformersReady

    fresh = [ConformerModel(molblock=molecule.conformers[0].molblock, energy=float(i), method="mmff94") for i in range(count)]
    services.event_bus.publish(ConformersReady(molecule_uuid=molecule.uuid, conformers=fresh))
    _drain(qapp)
    return fresh


def test_generating_again_keeps_the_orca_conformer_by_default(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    event, optimized = _orca_result(molecule.conformers[SLOT], molecule)
    _land(qapp, services, event)
    orca = molecule.conformers[SLOT]

    fresh = _regenerate(qapp, services, molecule)

    assert molecule.conformers == [*fresh, orca], "the new ones, then the kept optimized geometry"
    assert molecule.conformers[-1] is orca, "the same object: its provenance and origin intact"
    window._undo_stack.undo()
    _drain(qapp)
    assert len(molecule.conformers) == 20 and molecule.conformers[SLOT] is orca, "undo restores the exact previous list"


def test_generating_again_replaces_everything_when_the_choice_is_off(qapp, tmp_path):
    from openchem.app.settings import CONFORMER_KEEP_OPTIMIZED

    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    window._settings.set(CONFORMER_KEEP_OPTIMIZED.key, False)
    event, _optimized = _orca_result(molecule.conformers[SLOT], molecule)
    _land(qapp, services, event)

    fresh = _regenerate(qapp, services, molecule)

    assert molecule.conformers == fresh
    assert not any(c.method == ORCA_OPTIMIZED for c in molecule.conformers)


def test_a_structure_edit_still_clears_the_kept_orca_conformer(qapp, tmp_path):
    """Keeping is about regeneration, never about an edit: the geometry no longer fits the molecule."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    event, _optimized = _orca_result(molecule.conformers[SLOT], molecule)
    _land(qapp, services, event)
    _regenerate(qapp, services, molecule)

    _edit(window, services, molecule, "CCCCCCCO")

    assert molecule.conformers == []


# --- the origin slot is where the source stood when Run was pressed ---------------------------------------------


def test_the_origin_slot_is_where_the_source_was_when_run_was_pressed_not_where_it_ended_up(qapp, tmp_path):
    """Run is pressed on an ORCA conformer in slot 7; a regeneration that keeps ORCA conformers moves it behind
    the new ones while the job runs. The result replaces it where it NOW is, and says it was optimized from
    number 7."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    first_event, _first = _orca_result(molecule.conformers[SLOT], molecule)
    _land(qapp, services, first_event)
    source = molecule.conformers[SLOT]
    assert source.method == ORCA_OPTIMIZED
    second_event, second = _orca_result(source, molecule)
    assert second_event.source_slot == SLOT + 1, "the panel stamps it when Run is pressed"
    _regenerate(qapp, services, molecule)
    moved_to = molecule.conformers.index(source)
    assert moved_to != SLOT, "the premise: the regeneration moved the source"

    _land(qapp, services, second_event)

    landed = molecule.conformers[moved_to]
    assert landed.conformer_id == second.conformer_id
    assert landed.provenance.parameters[OPTIMIZED_FROM_SLOT] == SLOT + 1, "what the calculation started from"
    assert landed.provenance.parameters[OPTIMIZED_FROM_ID] == source.conformer_id
    assert recorder.changed[-1].show_conformer_id == landed.conformer_id, "the viewer lands on where it is now"


def test_a_result_that_names_no_run_slot_records_the_source_and_no_slot(qapp, tmp_path):
    window, services, molecule, _recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    event, optimized = _orca_result(source, molecule, source_slot=0)

    _land(qapp, services, event)

    landed = molecule.conformers[SLOT]
    assert landed.conformer_id == optimized.conformer_id
    assert landed.provenance.parameters[OPTIMIZED_FROM_ID] == source.conformer_id
    assert OPTIMIZED_FROM_SLOT not in landed.provenance.parameters


# --- a REAL job through the real service, edited while it runs ----------------------------------------------------
#
# The tests above publish the landing event themselves. These start the job through the service the window owns
# (a real QProcess on a stand-in engine), change the molecule while it runs, and read what the window, the
# property panel's feed and the run history hold once it has finished.


def _optimizing_stand_in(sleep_seconds: float):
    """A provider that really spawns a process and returns an optimized conformer, as the ORCA engine does."""
    from rdkit import Chem

    from tests.test_quantum_chemistry_service import FakeQuantumEngineProvider

    class Provider(FakeQuantumEngineProvider):
        provider_id = "fake_opt"

        def parse_output(self, output_text, mol, molecule_uuid, calc_type):
            descriptors, _ = super().parse_output(output_text, mol, molecule_uuid, calc_type)
            return descriptors, ConformerModel(molblock=Chem.MolToMolBlock(mol), method=ORCA_OPTIMIZED)

    return Provider(sleep_seconds=sleep_seconds)


def _start_a_job(services, molecule, source, *, structure_identity: str):
    """Press Run, as the panel does: identity and slot taken NOW, the job sleeping long enough to edit under it."""
    import sys

    from openchem.domain.calculator import GEOMETRY
    from openchem.events.events import QuantumChemistryRunCompleted

    service = services.quantum_chemistry_service
    service.register_provider(_optimizing_stand_in(sleep_seconds=1.5))
    service._settings.set("orca/executable_path", sys.executable)
    runs: list = []
    services.event_bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    service.request_calculation(
        mol=services.chemistry_engine.mol_from_molblock(source.molblock),
        molecule_uuid=molecule.uuid,
        calc_type="opt",
        charge=0,
        multiplicity=1,
        method_basis="HF STO-3G",
        provider_id="fake_opt",
        input_fingerprint=geometry_fingerprint(source),
        calculation_input=GEOMETRY,
        structure_identity=structure_identity,
        source_slot=molecule.conformers.index(source) + 1,
    )
    return runs


def _wait_for_the_run(qapp, runs, timeout_seconds: float = 20.0):
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not runs:
        qapp.processEvents()
        time.sleep(0.02)
    assert runs, "the stand-in job never finished"
    _drain(qapp)
    return runs[-1]


def _assert_the_job_was_withheld_but_remembered(window, services, molecule, recorder, run, conformers_before):
    from openchem.domain.quantum_chemistry_run import RunStatus

    assert molecule.conformers == conformers_before, "no conformer added, replaced or removed by the landing"
    assert [d for d in recorder.descriptors if d.descriptor.descriptor_id == "fake.scf_energy"] == [], (
        "the live numbers are not published for a molecule they were not computed on"
    )
    assert "edited while the ORCA job ran" in window.statusBar().currentMessage()
    assert run.status is RunStatus.COMPLETED
    kept = services.result_store_service.qc_runs.get(run.run_id)
    assert kept is not None, "the finished run is still in the project's history"
    assert list(kept.results["descriptors"]), "and it still holds what it computed"


def test_a_real_job_edited_under_with_no_conformers_left_is_withheld_and_its_run_is_kept(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    runs = _start_a_job(services, molecule, source, structure_identity=molecule.canonical_smiles)
    molecule.conformers = []  # the generation undone: nothing for the edit to clear

    _edit(window, services, molecule, "CCCCCCCO")
    run = _wait_for_the_run(qapp, runs)

    assert recorder.invalidated == [], "the premise: no ConformersInvalidated was ever published"
    _assert_the_job_was_withheld_but_remembered(window, services, molecule, recorder, run, [])


def test_a_real_job_edited_under_with_conformers_present_is_withheld_and_its_run_is_kept(qapp, tmp_path):
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    runs = _start_a_job(services, molecule, source, structure_identity=molecule.canonical_smiles)

    _edit(window, services, molecule, "CCCCCCCO")
    run = _wait_for_the_run(qapp, runs)

    assert len(recorder.invalidated) == 1
    _assert_the_job_was_withheld_but_remembered(window, services, molecule, recorder, run, [])


def test_a_real_job_unedited_lands_in_its_slot_through_the_same_path(qapp, tmp_path):
    """The control: the identical job with nothing done to the molecule installs, so the two tests above are
    about the edit and not about the stand-in."""
    window, services, molecule, recorder = _window_with(qapp, tmp_path)
    source = molecule.conformers[SLOT]
    runs = _start_a_job(services, molecule, source, structure_identity=molecule.canonical_smiles)

    run = _wait_for_the_run(qapp, runs)

    assert len(molecule.conformers) == 20
    assert molecule.conformers[SLOT].method == ORCA_OPTIMIZED
    assert molecule.conformers[SLOT].provenance.parameters[OPTIMIZED_FROM_SLOT] == SLOT + 1
    assert len([d for d in recorder.descriptors if d.descriptor.descriptor_id == "fake.scf_energy"]) == 1
    assert services.result_store_service.qc_runs.get(run.run_id) is not None


def test_using_a_conformer_in_the_2d_editor_while_orca_runs_withholds_the_result(qapp, tmp_path):
    """**"Use in 2D Editor" can give the drawing stereochemistry it did not have**, which changes its canonical
    SMILES without being an edit: the conformers are kept, the structure is now MORE SPECIFIC. A job started on
    the unspecified structure must not claim the now-specified molecule as its own: the geometry and the live
    numbers are withheld, the status bar says why, and the finished run stays in the history."""
    window, services = _build_window(qapp, tmp_path)
    molecule = _molecule(services, smiles="CC(F)Cl", count=3)  # one stereocentre, left unspecified
    window.add_molecule(molecule)
    _drain(qapp)
    recorder = _Recorder(services.event_bus)
    assert "@" not in molecule.canonical_smiles, "the premise: the drawing has no stereochemistry"
    unspecified = molecule.canonical_smiles
    source = molecule.conformers[1]
    before = list(molecule.conformers)
    runs = _start_a_job(services, molecule, source, structure_identity=unspecified)

    window._adopt_conformer(molecule.conformers[0].molblock)
    _drain(qapp)
    assert "@" in molecule.canonical_smiles, "the premise: adopting the conformer specified the stereocentre"
    assert molecule.conformers == before, "adopting keeps the conformers, which is why no invalidation was published"
    run = _wait_for_the_run(qapp, runs)

    assert recorder.invalidated == []
    _assert_the_job_was_withheld_but_remembered(window, services, molecule, recorder, run, before)
