"""The ORCA optimization progress reader as wired into the service and the Quantum Chemistry panel."""

from __future__ import annotations

from types import SimpleNamespace

from openchem.domain.common import CacheState
from openchem.domain.opt_progress import ConvergenceItem, OptProgress, detail_text, summary_line
from openchem.events.events import (
    QuantumChemistryJobStateChanged,
    QuantumChemistryOutput,
    QuantumChemistryProgress,
)
from openchem.services.quantum_chemistry_service import QuantumChemistryService

import conftest
from test_quantum_chemistry_panel import _make_panel

_TABLE = (
    "          ----------------------|Geometry convergence|-------------------------\n"
    "          Item                value                   Tolerance       Converged\n"
    "          ---------------------------------------------------------------------\n"
    "          Energy change      -0.0000244545            0.0000010000      NO\n"
    "          MAX gradient        0.0003400000            0.0003000000      NO\n"
    "          RMS step            0.0000175939            0.0006000000      YES\n"
    "          ---------------------------------------------------------------------\n"
    "Max(Bonds)      0.0000\n"
)


def _job(calc_type: str = "opt", provider_id: str = "orca"):
    return SimpleNamespace(calc_type=calc_type, provider=SimpleNamespace(provider_id=provider_id), progress_parser=None, progress=None)


# -- the service's side ------------------------------------------------------------------------------------------


def test_an_orca_optimization_is_read_and_an_unchanged_snapshot_is_not_republished():
    job = _job()
    first = QuantumChemistryService._read_progress(job, "         *                GEOMETRY OPTIMIZATION CYCLE   4            *\n")
    assert first is not None and first.cycle == 4
    assert QuantumChemistryService._read_progress(job, "some line that changes nothing\n") is None


def test_only_an_orca_optimization_is_read():
    for job in (_job("sp"), _job("opt", "xtb"), _job("opt_freq", "psi4")):
        assert QuantumChemistryService._read_progress(job, "GEOMETRY OPTIMIZATION CYCLE   4\n") is None
        assert job.progress_parser is None


def test_the_status_text_carries_the_summary_only_once_there_is_one():
    job = _job()
    assert QuantumChemistryService._with_progress(job, "ORCA opt — 3 min 0 s") == "ORCA opt — 3 min 0 s"
    QuantumChemistryService._read_progress(job, "GEOMETRY OPTIMIZATION CYCLE   4\n")
    assert QuantumChemistryService._with_progress(job, "ORCA opt — 3 min 0 s") == "ORCA opt — 3 min 0 s · cycle 4"


# -- the plain-text reading ---------------------------------------------------------------------------------------


def test_the_summary_and_detail_say_only_what_was_reported():
    assert summary_line(OptProgress()) == ""
    progress = OptProgress(
        cycle=106, max_cycles=123, energy=-810.2419, energy_change=-2e-6,
        criteria=(ConvergenceItem("MAX gradient", 3.4e-4, 3e-4, False), ConvergenceItem("RMS step", 1e-5, 6e-4, True)),
        resets=101,
    )
    assert summary_line(progress) == "cycle 106 of 123 · E -810.24190 Eh · ΔE -2.0e-06 Eh · 1/2 criteria met"
    assert detail_text(progress) == "MAX gradient: 3.4e-04 (needs 3.0e-04)\nORCA rebuilt its optimizer 101 times in 106 cycles"


# -- the panel's side ----------------------------------------------------------------------------------------------


def _pending_panel():
    panel, _engine, _service = _make_panel()
    panel._pending_molecule_uuid = "m1"
    return panel


def test_output_chunks_that_split_a_line_land_as_whole_lines(qapp):
    panel = _pending_panel()
    try:
        for text in ("first line\nsecond ", "half\nthird\n"):
            panel._on_job_output(QuantumChemistryOutput(molecule_uuid="m1", text=text))
        assert panel._output_log.toPlainText() == "first line\nsecond half\nthird\n"
        panel._on_job_output(QuantumChemistryOutput(molecule_uuid="other", text="not mine\n"))
        assert "not mine" not in panel._output_log.toPlainText()
    finally:
        conftest.dispose(panel)


def test_a_running_status_goes_to_the_readout_and_not_into_the_log(qapp):
    panel = _pending_panel()
    try:
        panel._on_job_state_changed(
            QuantumChemistryJobStateChanged(molecule_uuid="m1", state=CacheState.RUNNING, message="ORCA opt — 3 min 0 s")
        )
        assert panel._progress_label.isVisibleTo(panel) and "3 min" in panel._progress_label.text()
        assert panel._output_log.toPlainText() == ""
        panel._on_job_state_changed(
            QuantumChemistryJobStateChanged(molecule_uuid="m1", state=CacheState.FAILED, message="ORCA exited with code 1")
        )
        assert "exited with code 1" in panel._output_log.toPlainText()  # a failure's reason is still in the log
        assert not panel._progress_label.isVisibleTo(panel)
    finally:
        conftest.dispose(panel)


def test_the_readout_names_the_criterion_holding_the_job_up(qapp):
    from openchem.chem.orca_progress import OrcaProgressParser

    panel = _pending_panel()
    try:
        parser = OrcaProgressParser()
        panel._on_job_progress(QuantumChemistryProgress(molecule_uuid="m1", progress=parser.feed(_TABLE + "\n")))
        text = panel._progress_label.text()
        assert "MAX gradient" in text and "Energy change" in text and "RMS step" not in text
    finally:
        conftest.dispose(panel)


def test_the_keep_button_follows_whether_the_service_can_keep_the_geometry(qapp):
    panel, _engine, service = _make_panel()
    panel._pending_molecule_uuid = "m1"
    asked: list[str] = []
    service.can_stop_and_keep = lambda uuid: True
    service.stop_and_keep = lambda uuid: asked.append(uuid) or True
    try:
        assert not panel._keep_button.isEnabled()
        panel._on_job_state_changed(QuantumChemistryJobStateChanged(molecule_uuid="m1", state=CacheState.RUNNING, message="x"))
        assert panel._keep_button.isEnabled()
        panel._keep_button.click()
        assert asked == ["m1"] and not panel._keep_button.isEnabled()  # one request
        panel._on_job_state_changed(QuantumChemistryJobStateChanged(molecule_uuid="m1", state=CacheState.FAILED, message="stopped"))
        assert not panel._keep_button.isEnabled()
        service.can_stop_and_keep = lambda uuid: False  # an engine or calculation that cannot keep one
        panel._on_job_state_changed(QuantumChemistryJobStateChanged(molecule_uuid="m1", state=CacheState.RUNNING, message="x"))
        assert not panel._keep_button.isEnabled()
    finally:
        conftest.dispose(panel)
