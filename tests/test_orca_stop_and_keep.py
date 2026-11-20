"""Stop and keep geometry: reading the geometry ORCA had reached, and the end of a job stopped that way."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

import conftest
from openchem.app.settings import Settings
from openchem.chem.orca_partial import read_partial_geometry
from openchem.domain.common import CacheState
from openchem.domain.conformer import ORCA_PARTIAL_OPT, QUANTUM_OPTIMIZED_METHODS, conformer_choice_text
from openchem.domain.opt_progress import SLOW_WINDOW, ConvergenceItem, OptProgress, slow_progress_note
from openchem.domain.quantum_chemistry_run import RunStatus
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryJobStateChanged, QuantumChemistryResultReady
from openchem.services.quantum_chemistry_service import QuantumChemistryService, _ActiveJob


def _water() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return mol


def _xyz(rows, comment: str = "") -> str:
    body = "".join(f"{e} {x:.6f} {y:.6f} {z:.6f}\n" for e, x, y, z in rows)
    return f"{len(rows)}\n{comment}\n{body}"


_GOOD = [("O", 0.0, 0.0, 0.1), ("H", 0.0, 0.75, -0.5), ("H", 0.0, -0.75, -0.5)]


# -- reading the geometry ------------------------------------------------------------------------------------------


def test_the_final_xyz_is_read_when_it_is_sound(tmp_path):
    (tmp_path / "job.xyz").write_text(_xyz(_GOOD), encoding="utf-8")
    assert read_partial_geometry(tmp_path, _water()) == [(0.0, 0.0, 0.1), (0.0, 0.75, -0.5), (0.0, -0.75, -0.5)]


def test_a_missing_final_file_falls_back_to_the_last_complete_trajectory_frame(tmp_path):
    later = [("O", 0.0, 0.0, 0.2), ("H", 0.0, 0.8, -0.5), ("H", 0.0, -0.8, -0.5)]
    cut = _xyz(later)[:-12]  # a frame cut off by the kill: dropped, not half-read
    (tmp_path / "job_trj.xyz").write_text(_xyz(_GOOD, "frame 1") + cut, encoding="utf-8")
    assert read_partial_geometry(tmp_path, _water()) == [(a, b, c) for _e, a, b, c in _GOOD]


@pytest.mark.parametrize(
    "rows",
    [
        [("O", 0.0, 0.0, 0.1), ("H", 0.0, 0.75, -0.5)],  # wrong atom count
        [("H", 0.0, 0.0, 0.1), ("O", 0.0, 0.75, -0.5), ("H", 0.0, -0.75, -0.5)],  # elements in another order
        [("O", 0.0, 0.0, float("nan")), ("H", 0.0, 0.75, -0.5), ("H", 0.0, -0.75, -0.5)],  # not finite
    ],
)
def test_an_unsound_geometry_is_refused_and_nothing_else_is_substituted(tmp_path, rows):
    (tmp_path / "job.xyz").write_text(_xyz(rows), encoding="utf-8")
    assert read_partial_geometry(tmp_path, _water()) is None


def test_nothing_to_read_is_none(tmp_path):
    assert read_partial_geometry(tmp_path, _water()) is None


# -- the end of a stopped job --------------------------------------------------------------------------------------


class _Process:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True

    def bytesAvailable(self):  # noqa: N802 - Qt's name
        return 0


def _service_with_job(folder, *, calc_type="opt", provider_id="orca", xyz=None):
    bus = EventBus()
    seen: list = []
    bus.subscribe(QuantumChemistryResultReady, seen.append)
    bus.subscribe(QuantumChemistryJobStateChanged, seen.append)
    service = QuantumChemistryService(bus, Settings(bus), providers={})
    recorded: list = []
    service._record_run = recorded.append  # the ledger is not under test
    scratch = folder / "orca_job"
    scratch.mkdir()
    if xyz is not None:
        (scratch / "job.xyz").write_text(xyz, encoding="utf-8")
    job = _ActiveJob(
        key="m1", mol=_water(), provider=SimpleNamespace(provider_id=provider_id), calc_type=calc_type,
        scratch_dir=scratch, process=_Process(), kind="calculation", molecule_uuid="m1",
        method_basis="B3LYP def2-SVP", run_id="run-1", structure_identity="O",
    )
    service._active_jobs["m1"] = job
    return service, job, seen, recorded


def test_only_a_running_orca_optimization_can_be_stopped_with_its_geometry(tmp_path):
    for index, kwargs in enumerate(({"calc_type": "sp"}, {"provider_id": "xtb"})):
        folder = tmp_path / str(index)
        folder.mkdir()
        service, job, _seen, _rec = _service_with_job(folder, **kwargs)
        assert not service.can_stop_and_keep("m1")
        assert not service.stop_and_keep("m1")
        assert not job.process.killed and not job.cancelled
    folder = tmp_path / "ok"
    folder.mkdir()
    service, job, _seen, _rec = _service_with_job(folder)
    assert service.can_stop_and_keep("m1") and service.stop_and_keep("m1")
    assert job.process.killed and job.cancelled and job.keep_partial
    assert not service.can_stop_and_keep("m1")  # asked once


@pytest.mark.parametrize("order", ["finished_first", "error_first"])
def test_the_geometry_is_kept_whichever_end_of_process_signal_comes_first(tmp_path, order):
    service, job, seen, recorded = _service_with_job(tmp_path, xyz=_xyz(_GOOD))
    job.progress = OptProgress(cycle=106)
    assert service.stop_and_keep("m1")
    scratch = job.scratch_dir
    ends = [lambda: service._on_finished("m1"), lambda: service._on_process_error("m1", None)]
    if order == "error_first":
        ends.reverse()
    for end in ends:
        end()  # the second finds no job and does nothing

    landed = [e for e in seen if isinstance(e, QuantumChemistryResultReady)]
    assert len(landed) == 1 and landed[0].descriptors == [] and landed[0].structure_identity == "O"
    conformer = landed[0].conformer
    assert conformer.method == ORCA_PARTIAL_OPT and conformer.method not in QUANTUM_OPTIMIZED_METHODS
    assert conformer.energy is None
    text = conformer_choice_text([conformer], 0)
    assert "NOT converged" in text and "cycle 106" in text
    states = [e for e in seen if isinstance(e, QuantumChemistryJobStateChanged)]
    assert states and states[-1].state == CacheState.FAILED and "NOT converged" in states[-1].message
    assert len(recorded) == 1 and recorded[0].status == RunStatus.CANCELLED
    assert recorded[0].output_conformer_id == conformer.conformer_id
    assert not scratch.exists()  # the folder is still cleaned up


def test_nothing_is_kept_when_no_sound_geometry_exists(tmp_path):
    service, _job, seen, recorded = _service_with_job(tmp_path, xyz=_xyz(_GOOD[:2]))
    assert service.stop_and_keep("m1")
    service._on_finished("m1")
    assert not [e for e in seen if isinstance(e, QuantumChemistryResultReady)]
    assert recorded[0].status == RunStatus.CANCELLED and "nothing was kept" in recorded[0].warnings[0]


def test_an_ordinary_cancel_still_keeps_nothing(tmp_path):
    service, _job, seen, recorded = _service_with_job(tmp_path, xyz=_xyz(_GOOD))
    service.cancel("m1")
    service._on_finished("m1")
    assert not [e for e in seen if isinstance(e, QuantumChemistryResultReady)]
    assert recorded[0].status == RunStatus.CANCELLED and recorded[0].output_conformer_id is None


# -- the slow-progress note ----------------------------------------------------------------------------------------


def _progress(change: float, resets: int, unmet: bool = True, cycles: int = 40) -> OptProgress:
    history = tuple(-810.0 - 1e-6 * i + (change if i == cycles - 1 else 0.0) for i in range(cycles))
    item = ConvergenceItem("MAX gradient", 3.4e-4, 3e-4, not unmet)
    return OptProgress(cycle=cycles, energy_history=history, criteria=(item,), resets=resets)


def test_the_slow_note_needs_all_the_signs():
    assert "Progress is slow" in slow_progress_note(_progress(0.0, resets=30))
    assert slow_progress_note(_progress(0.0, resets=5)) == ""  # the optimizer is not rebuilding itself
    assert slow_progress_note(_progress(0.0, resets=30, unmet=False)) == ""  # nothing is holding it up
    assert slow_progress_note(_progress(-1e-3, resets=30)) == ""  # the energy is still moving
    assert slow_progress_note(OptProgress(cycle=SLOW_WINDOW, resets=SLOW_WINDOW)) == ""  # too early to say


# -- how the viewer says it ---------------------------------------------------------------------------------------


def test_the_viewer_labels_a_kept_geometry_as_not_converged_and_not_as_energy_n_a(qapp):
    from openchem.domain.common import Provenance
    from openchem.domain.conformer import ConformerModel, PARTIAL_CYCLE
    from tests.test_molecule_viewer3d_widget import _gallery_widget

    widget, _backend, molecule = _gallery_widget(None, count=3)
    try:
        kept = ConformerModel(molblock=molecule.conformers[0].molblock, method=ORCA_PARTIAL_OPT,
                              provenance=Provenance(created_by="core", method="orca", parameters={PARTIAL_CYCLE: 7}))
        label = widget._conformer_label(kept)
        assert "ORCA partial geometry, NOT converged (cycle 7)" in label and "energy n/a" not in label
        assert "NOT converged" in widget._conformer_tooltip(kept)
    finally:
        conftest.dispose(widget)


def test_the_readout_counts_in_the_singular():
    from openchem.domain.opt_progress import detail_text

    assert detail_text(OptProgress(cycle=1, resets=1)) == "ORCA rebuilt its optimizer 1 time in 1 cycle"
    assert detail_text(OptProgress(cycle=2, resets=2)) == "ORCA rebuilt its optimizer 2 times in 2 cycles"
