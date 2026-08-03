from __future__ import annotations

import dataclasses
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs
from PySide6.QtCore import QObject, QProcess
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.chem.boltzmann import boltzmann_average_spectrum
from openchem.chem.nmr_reference import (
    SPECTRUM_TYPE_BY_ELEMENT,
    average_reference_shielding,
    tms_molecule,
)
from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem import paths as app_paths
from openchem.domain.common import CacheState, Provenance
from openchem.events.base import EventBus
from openchem.events.events import (
    NmrScalingCalibrated,
    NmrReferenceCalibrated,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    SpectrumComputed,
)
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.job_manager import JobManager

logger = logging.getLogger("openchem.chemistry")

# Same appname/appauthor PluginManager/reaction_prediction already use for
# their own "OpenChemStudio" app-data locations.
_APP_NAME = "OpenChemStudio"
_JOB_KIND = "quantum_chemistry"
_REFERENCE_JOB_KIND = "quantum_chemistry_reference"
_SCALING_JOB_KIND = "quantum_chemistry_scaling"

# TMS is neutral, closed-shell -- fixed, not user-configurable (only
# method_basis varies per reference calibration request).
_TMS_CHARGE = 0
_TMS_MULTIPLICITY = 1


def _reference_job_key(method_basis: str) -> str:
    return f"__nmr_reference__::{method_basis}"


def _scaling_job_key(method_basis: str) -> str:
    return f"__nmr_scaling__::{method_basis}"


def _job_manager_kind(kind: str) -> str:
    """Only a reference calibration gets its own JobManager kind. A
    conformer job in a Boltzmann run is part of the molecule's single
    logical job, so it shares `_JOB_KIND` with an ordinary calculation --
    which is what keeps Cancel and the one-job-per-molecule guard working
    across the whole sequence."""
    if kind == "reference":
        return _REFERENCE_JOB_KIND
    if kind == "scaling":
        return _SCALING_JOB_KIND
    return _JOB_KIND


@dataclass
class _BoltzmannRun:
    """One logical NMR job spanning N sequential ORCA runs, one per
    conformer, averaged at the end (`chem/boltzmann.py`).

    Sequential rather than parallel on purpose: ORCA is already
    multi-threaded internally and will happily saturate the machine, so
    running conformers concurrently mostly makes each one slower while
    multiplying the scratch-disk footprint. It also keeps the existing
    one-job-per-molecule invariant intact -- from JobManager's point of
    view this is still a single job for the molecule, which is what makes
    Cancel keep working unchanged.
    """

    molecule_uuid: str
    remaining_mols: list[Chem.Mol]
    calc_type: str
    charge: int
    multiplicity: int
    method_basis: str
    provider: QuantumEngineProvider
    executable_path: str
    total: int
    spectra: list = field(default_factory=list)
    energies: list[float] = field(default_factory=list)


@dataclass
class _ScalingRun:
    """One logical calibration spanning N sequential ORCA runs, one per
    reference compound, regressed at the end (`chem/nmr_scaling.py`).

    Sequential for the same reasons as `_BoltzmannRun`, and holding ONE
    JobManager slot for the whole sequence so Cancel reaches the run as a
    single thing rather than only the compound currently in flight.

    A compound that fails to run is recorded in `failed` and skipped
    rather than aborting: the fit needs four points, not eleven, so one
    bad reference should cost a data point and not the calibration. The
    R^2 guard is what catches a set degraded too far.
    """

    method_basis: str
    remaining: list  # list[ReferenceCompound]
    provider: QuantumEngineProvider
    executable_path: str
    total: int
    # compound name -> element -> shieldings for that element's nuclei
    shieldings: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    # Recorded from the first standard that reports one. The cache key
    # includes it so a calibration never survives an ORCA upgrade that
    # could have changed the shieldings it was fitted to.
    orca_version: str = "unknown"


@dataclass
class _ActiveJob:
    key: str
    mol: Chem.Mol
    provider: QuantumEngineProvider
    calc_type: str
    scratch_dir: Path
    process: QProcess
    kind: str = "calculation"  # "calculation" | "reference" | "conformer" | "scaling"
    molecule_uuid: str | None = None  # only set for kind == "calculation"/"conformer"
    # Only set for kind == "scaling": which calibration standard this run
    # is, so its shieldings can be filed against the right literature
    # shift when the whole sequence finishes.
    compound_name: str = ""
    method_basis: str = ""  # set for both kinds -- the exact free-text
    # method_basis string the job ran with, needed to look up/write the
    # right TMS reference cache entry either way.
    stdout_chunks: list[str] = field(default_factory=list)
    cancelled: bool = False


class QuantumChemistryService(QObject):
    """Runs a `QuantumEngineProvider`'s calculation via `QProcess`, run
    **on the GUI thread** — a deliberate asymmetry from every other async
    service in this codebase (`ConformerService`, `DescriptorService`,
    `DockingService`), which all use `QRunnable`/`QThreadPool`. `QProcess`
    is only safely usable from the thread that constructs it: its signals
    (`readyReadStandardOutput`, `finished`) are ordinary Qt signals
    delivered via that thread's event loop. ORCA jobs can run for many
    minutes and need real, immediate cancellation (Cancel -> a live
    `QProcess.kill()`, not "the next time a worker thread checks in") plus
    live-streamed stdout, both of which fit QProcess/GUI-thread naturally.
    Constructing/starting the `QProcess` from a `QRunnable` worker thread
    instead would not give clean cancellation from a GUI button click.

    Only one active job per molecule at a time (keyed by `molecule_uuid`)
    — starting a second job for the same molecule while one is running
    isn't a supported use case in V1. A reference-shielding calibration
    job (Phase 22, `request_reference_calibration`) is keyed separately
    (`_reference_job_key`, `_REFERENCE_JOB_KIND` in `JobManager`) so it can
    never collide with a real molecule's job even if one happens to be
    running at the same time.
    """

    def __init__(
        self,
        event_bus: EventBus,
        settings: Settings,
        providers: dict[str, QuantumEngineProvider] | None = None,
        job_manager: JobManager | None = None,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._settings = settings
        default_provider = OrcaQuantumEngineProvider()
        self._providers: dict[str, QuantumEngineProvider] = (
            providers if providers is not None else {default_provider.provider_id: default_provider}
        )
        self._active_jobs: dict[str, _ActiveJob] = {}
        # Keyed by molecule_uuid, same as _active_jobs: a Boltzmann run owns
        # the molecule's job slot for its whole sequence of conformers.
        self._boltzmann_runs: dict[str, _BoltzmannRun] = {}
        # Keyed by scaling-job key, one entry per in-flight calibration.
        self._scaling_runs: dict[str, _ScalingRun] = {}
        self._job_manager = job_manager if job_manager is not None else JobManager()

    def register_provider(self, provider: QuantumEngineProvider) -> None:
        self._providers[provider.provider_id] = provider

    def unregister_provider(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def request_calculation(
        self,
        mol: Chem.Mol,
        molecule_uuid: str,
        calc_type: str,
        charge: int,
        multiplicity: int,
        method_basis: str,
        provider_id: str = "orca",
    ) -> None:
        provider = self._providers.get(provider_id)
        if provider is None:
            self._publish_state(molecule_uuid, CacheState.FAILED, f"Unknown quantum engine: {provider_id}")
            return
        executable_path = self._resolve_executable_path()
        if executable_path is None:
            self._publish_state(
                molecule_uuid,
                CacheState.FAILED,
                "No ORCA executable configured or found on PATH — set orca/executable_path in Settings.",
            )
            return
        # Guards the real bug this used to have: request_calculation had no
        # check at all before `self._active_jobs[molecule_uuid] = job`
        # below, so a second call while one was running silently overwrote
        # the dict entry -- orphaning the first QProcess (cancel() could
        # never reach it again) while the first job's own finished/
        # errorOccurred handler later popped the SECOND job's entry out
        # from under it.
        # Registers this service's own existing cancel() as the callback --
        # QuantumChemistryService already has real, immediate QProcess.kill()
        # cancellation; this just makes it reachable through JobManager too,
        # so a Jobs panel can cancel it the same way it cancels any other
        # job type, not only from this panel's own Cancel button.
        if not self._job_manager.try_start(
            _JOB_KIND, molecule_uuid, cancel_callback=lambda: self.cancel(molecule_uuid)
        ):
            self._publish_state(
                molecule_uuid,
                CacheState.FAILED,
                "A calculation is already running for this molecule — cancel it first.",
            )
            return

        self._launch_job(
            key=molecule_uuid,
            mol=mol,
            charge=charge,
            multiplicity=multiplicity,
            method_basis=method_basis,
            calc_type=calc_type,
            provider=provider,
            executable_path=executable_path,
            kind="calculation",
            molecule_uuid=molecule_uuid,
        )

    def request_boltzmann_nmr(
        self,
        mols: list[Chem.Mol],
        molecule_uuid: str,
        calc_type: str,
        charge: int,
        multiplicity: int,
        method_basis: str,
        provider_id: str = "orca",
    ) -> None:
        """Runs `calc_type` on every conformer in `mols`, one after another,
        and publishes a single Boltzmann-averaged spectrum.

        This is what makes a predicted shift comparable to a measured one
        for a flexible molecule: the experiment sees a population-weighted
        average over conformers, not the lowest-energy geometry alone.

        Costs N times a single run, so the panel offers it as an opt-in
        rather than doing it silently. One conformer degrades to exactly
        `request_calculation` -- no special case needed downstream, since
        averaging one spectrum returns it unchanged.
        """
        if not mols:
            self._publish_state(molecule_uuid, CacheState.FAILED, "No conformers to average over.")
            return
        provider = self._providers.get(provider_id)
        if provider is None:
            self._publish_state(molecule_uuid, CacheState.FAILED, f"Unknown quantum engine: {provider_id}")
            return
        executable_path = self._resolve_executable_path()
        if executable_path is None:
            self._publish_state(
                molecule_uuid,
                CacheState.FAILED,
                "No ORCA executable configured or found on PATH — set orca/executable_path in Settings.",
            )
            return
        # Takes the molecule's single job slot for the WHOLE sequence, not
        # per conformer -- so Cancel (from this panel or the Jobs panel)
        # reaches the run as one thing, and a second request while it is
        # going is refused the same way it would be for a single job.
        if not self._job_manager.try_start(
            _JOB_KIND, molecule_uuid, cancel_callback=lambda: self.cancel(molecule_uuid)
        ):
            self._publish_state(
                molecule_uuid,
                CacheState.FAILED,
                "A calculation is already running for this molecule — cancel it first.",
            )
            return

        run = _BoltzmannRun(
            molecule_uuid=molecule_uuid,
            remaining_mols=list(mols),
            calc_type=calc_type,
            charge=charge,
            multiplicity=multiplicity,
            method_basis=method_basis,
            provider=provider,
            executable_path=executable_path,
            total=len(mols),
        )
        self._boltzmann_runs[molecule_uuid] = run
        self._launch_next_conformer(run)

    def _launch_next_conformer(self, run: _BoltzmannRun) -> None:
        mol = run.remaining_mols.pop(0)
        self._publish_state(
            run.molecule_uuid,
            CacheState.RUNNING,
            f"Conformer {run.total - len(run.remaining_mols)}/{run.total}",
        )
        self._launch_job(
            key=run.molecule_uuid,
            mol=mol,
            charge=run.charge,
            multiplicity=run.multiplicity,
            method_basis=run.method_basis,
            calc_type=run.calc_type,
            provider=run.provider,
            executable_path=run.executable_path,
            kind="conformer",
            molecule_uuid=run.molecule_uuid,
        )

    def request_reference_calibration(self, method_basis: str, provider_id: str = "orca") -> None:
        """Runs a real ORCA `! NMR` job on TMS (the standard 1H/13C
        reference compound, `chem/nmr_reference.py::tms_molecule()`) at
        `method_basis`, and caches the resulting per-element shielding in
        `Settings` for `chemical_shift_from_reference` to use on every
        subsequent real-molecule NMR result at the same (method_basis,
        ORCA version) -- run once, reused, not recomputed per molecule.
        """
        provider = self._providers.get(provider_id)
        if provider is None:
            self._event_bus.publish(
                NmrReferenceCalibrated(
                    method_basis=method_basis,
                    provider_id=provider_id,
                    values={},
                    error=f"Unknown quantum engine: {provider_id}",
                )
            )
            return
        executable_path = self._resolve_executable_path()
        if executable_path is None:
            self._event_bus.publish(
                NmrReferenceCalibrated(
                    method_basis=method_basis,
                    provider_id=provider_id,
                    values={},
                    error="No ORCA executable configured or found on PATH — set orca/executable_path in Settings.",
                )
            )
            return

        key = _reference_job_key(method_basis)
        if not self._job_manager.try_start(
            _REFERENCE_JOB_KIND, key, cancel_callback=lambda: self._cancel_by_key(key)
        ):
            self._event_bus.publish(
                NmrReferenceCalibrated(
                    method_basis=method_basis,
                    provider_id=provider_id,
                    values={},
                    error=f"A reference calibration for {method_basis!r} is already running.",
                )
            )
            return

        self._launch_job(
            key=key,
            mol=tms_molecule(),
            charge=_TMS_CHARGE,
            multiplicity=_TMS_MULTIPLICITY,
            method_basis=method_basis,
            calc_type="nmr",
            provider=provider,
            executable_path=executable_path,
            kind="reference",
        )

    def request_scaling_calibration(self, method_basis: str, provider_id: str = "orca") -> None:
        """Runs `! NMR` on each calibration standard in
        `chem/nmr_scaling.REFERENCE_COMPOUNDS` at `method_basis`, then
        fits `delta = slope * sigma + intercept` per element and caches
        the result for every subsequent NMR job at the same (method_basis,
        ORCA version).

        Costs N runs where the TMS reference costs one, which is why it is
        a separate opt-in rather than folded into that button. What it buys
        is real: measured against ORCA 6.1.1 at B3LYP/def2-SVP, carbon goes
        from ~11.3 ppm mean error to 1.5, and protons from 0.67 to 0.21.
        """
        from openchem.chem.nmr_scaling import REFERENCE_COMPOUNDS

        provider = self._providers.get(provider_id)
        if provider is None:
            self._fail_scaling(method_basis, provider_id, f"Unknown quantum engine: {provider_id}")
            return
        executable_path = self._resolve_executable_path()
        if executable_path is None:
            self._fail_scaling(
                method_basis,
                provider_id,
                "No ORCA executable configured or found on PATH — set orca/executable_path in Settings.",
            )
            return

        key = _scaling_job_key(method_basis)
        if not self._job_manager.try_start(
            _SCALING_JOB_KIND, key, cancel_callback=lambda: self._cancel_by_key(key)
        ):
            self._fail_scaling(
                method_basis, provider_id, f"A scaling calibration for {method_basis!r} is already running."
            )
            return

        run = _ScalingRun(
            method_basis=method_basis,
            remaining=list(REFERENCE_COMPOUNDS),
            provider=provider,
            executable_path=executable_path,
            total=len(REFERENCE_COMPOUNDS),
        )
        self._scaling_runs[key] = run
        self._launch_next_reference_compound(key, run)

    def _fail_scaling(self, method_basis: str, provider_id: str, message: str) -> None:
        self._event_bus.publish(
            NmrScalingCalibrated(
                method_basis=method_basis, provider_id=provider_id, factors={}, error=message
            )
        )

    def _launch_next_reference_compound(self, key: str, run: _ScalingRun) -> None:
        """Starts the next standard, skipping any that cannot be built.

        Embedding failures are handled HERE rather than inside the job
        loop because they happen before any process starts -- a compound
        RDKit cannot embed should cost one data point, not stall the
        sequence waiting for a process that was never launched.
        """
        from openchem.chem.nmr_scaling import reference_molecule

        while run.remaining:
            compound = run.remaining.pop(0)
            try:
                mol = reference_molecule(compound)
            except Exception as exc:  # noqa: BLE001 - skip this standard, keep the run
                logger.warning("Skipping NMR calibration standard %s: %s", compound.name, exc)
                run.failed.append(compound.name)
                continue
            self._publish_state(
                key,
                CacheState.RUNNING,
                f"{compound.name} ({run.total - len(run.remaining)}/{run.total})",
            )
            self._launch_job(
                key=key,
                mol=mol,
                charge=_TMS_CHARGE,
                multiplicity=_TMS_MULTIPLICITY,
                method_basis=run.method_basis,
                calc_type="nmr",
                provider=run.provider,
                executable_path=run.executable_path,
                kind="scaling",
                compound_name=compound.name,
            )
            return
        # Nothing left to launch -- every remaining standard failed to
        # build, so finish with whatever was already collected.
        self._complete_scaling_run(key, run)

    def _launch_job(
        self,
        *,
        key: str,
        mol: Chem.Mol,
        charge: int,
        multiplicity: int,
        method_basis: str,
        calc_type: str,
        provider: QuantumEngineProvider,
        executable_path: str,
        kind: str,
        molecule_uuid: str | None = None,
        compound_name: str = "",
    ) -> None:
        """Shared QProcess launch mechanics for both `request_calculation`
        (a real molecule) and `request_reference_calibration` (TMS) --
        build scratch dir, write input, wire signals, start the process.
        The caller has already resolved the provider/executable and
        registered the job with `JobManager`; this only handles the
        actually-running-ORCA part, which is identical either way.
        `executable_path` is threaded through explicitly (not re-resolved
        here) so it's guaranteed to be the exact path the caller already
        validated, not a second, potentially-different lookup.
        """
        self._publish_state(key, CacheState.QUEUED)

        # A space-free scratch directory is a hard requirement: ORCA
        # truncates its input path at the first space and aborts. This used
        # to derive straight from `cache_root()` on the reasoning that the
        # source tree ("D:\...\OpenChem Studio\") was the only spaced path
        # in play — but `cache_root()` follows the CONFIGURABLE data root,
        # so pointing that at, say, "D:\Random Programs\..." put the space
        # right back and every ORCA job failed. `space_free_cache_root()`
        # enforces the requirement instead of assuming it, and stays on the
        # same drive so the gigabytes still land where the user put them.
        cache_root = app_paths.space_free_cache_root()
        cache_root.mkdir(parents=True, exist_ok=True)
        scratch_dir = Path(tempfile.mkdtemp(prefix="orca_job_", dir=str(cache_root)))

        job_kind_for_manager = _job_manager_kind(kind)
        try:
            input_text = provider.build_input(mol, charge, multiplicity, method_basis, calc_type)
        except Exception as exc:  # noqa: BLE001 - bad input params, report don't crash
            self._cleanup_scratch(scratch_dir)
            self._publish_state(key, CacheState.FAILED, f"Failed to build input: {exc}")
            # Abandons the whole Boltzmann sequence if one conformer can't
            # even produce an input file -- the remaining ones would fail
            # identically (same params, same provider), and a partial
            # average would be silently wrong rather than obviously absent.
            self._boltzmann_runs.pop(key, None)
            self._scaling_runs.pop(key, None)
            self._job_manager.finish(job_kind_for_manager, key)
            return

        input_path = scratch_dir / "job.inp"
        input_path.write_text(input_text, encoding="utf-8")

        process = QProcess(self)
        args = provider.command_args(executable_path, input_path)
        job = _ActiveJob(
            key=key,
            mol=mol,
            provider=provider,
            calc_type=calc_type,
            scratch_dir=scratch_dir,
            process=process,
            kind=kind,
            molecule_uuid=molecule_uuid,
            method_basis=method_basis,
            compound_name=compound_name,
        )
        self._active_jobs[key] = job

        process.setWorkingDirectory(str(scratch_dir))
        process.readyReadStandardOutput.connect(lambda: self._on_stdout(key))
        process.finished.connect(lambda code, status: self._on_finished(key))
        process.errorOccurred.connect(lambda error: self._on_process_error(key, error))

        process.setProgram(args[0])
        process.setArguments([str(a) for a in args[1:]])
        process.start()
        self._publish_state(key, CacheState.RUNNING, "Starting")

    def cancel(self, molecule_uuid: str) -> None:
        self._cancel_by_key(molecule_uuid)

    def _cancel_by_key(self, key: str) -> None:
        job = self._active_jobs.get(key)
        if job is None:
            return
        job.cancelled = True
        job.process.kill()

    def _on_stdout(self, key: str) -> None:
        job = self._active_jobs.get(key)
        if job is None:
            return
        chunk = bytes(job.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        job.stdout_chunks.append(chunk)
        last_line = next((line for line in reversed(chunk.splitlines()) if line.strip()), "")
        self._publish_state(key, CacheState.RUNNING, last_line)

    def _on_process_error(self, key: str, error: QProcess.ProcessError) -> None:
        # Covers the process failing to even start (e.g. a bad executable
        # path) -- `finished` never fires in that case, so cleanup must
        # happen here instead. Confirmed directly: `errorOccurred` ALSO
        # fires (with ProcessError.Crashed) when an already-running process
        # is killed via cancel(), racing `_on_finished` for the same job --
        # since dict.pop() makes whichever handler runs first "win," this
        # must check `job.cancelled` too, or a real cancellation gets
        # reported as a generic crash instead of "Cancelled by user."
        job = self._active_jobs.pop(key, None)
        if job is None:
            return
        try:
            message = "Cancelled by user" if job.cancelled else f"Process error: {error}"
            self._report_job_failure(job, message)
        finally:
            # A process-level error ends the whole run, not just this
            # conformer -- there is no partial average worth publishing.
            self._boltzmann_runs.pop(key, None)
            self._scaling_runs.pop(key, None)
            self._cleanup_scratch(job.scratch_dir)
            self._job_manager.finish(_job_manager_kind(job.kind), key)

    def _report_job_failure(self, job: _ActiveJob, message: str) -> None:
        """Announce a terminal failure on the channel this job's requester
        is actually listening to.

        Shared by `_on_process_error` and `_on_finished` because those two
        RACE each other when a running process is killed -- whichever pops
        the job first wins. That race was already handled for reference
        jobs and was missed for scaling ones when they were added, so the
        Cancel button silently produced no event at all. One reporter
        means the next job kind cannot repeat it.
        """
        if job.kind == "reference":
            self._event_bus.publish(
                NmrReferenceCalibrated(
                    method_basis=job.method_basis,
                    provider_id=job.provider.provider_id,
                    values={},
                    error=message,
                )
            )
        elif job.kind == "scaling":
            self._event_bus.publish(
                NmrScalingCalibrated(
                    method_basis=job.method_basis,
                    provider_id=job.provider.provider_id,
                    factors={},
                    error=message,
                )
            )
        else:
            self._publish_state(job.key, CacheState.FAILED, message)

    def _on_finished(self, key: str) -> None:
        job = self._active_jobs.pop(key, None)
        if job is None:
            return
        # Set only when this conformer's success handler started the NEXT
        # one in the sequence. The molecule's JobManager slot must then stay
        # held (the logical job is still running) -- releasing it here would
        # let a second request start alongside the rest of the run and would
        # make Cancel unreachable for the remaining conformers.
        chaining = False
        try:
            if job.cancelled:
                self._boltzmann_runs.pop(key, None)
                self._scaling_runs.pop(key, None)
                self._report_job_failure(job, "Cancelled by user")
                return
            # `finished` can fire before Qt has delivered the LAST
            # `readyReadStandardOutput` signal for data ORCA wrote right as
            # it exited -- confirmed live: a short single-point job's
            # output always arrived in time, but a longer geometry
            # optimization's final "FINAL SINGLE POINT ENERGY"/"OPTIMIZATION
            # RUN DONE" block was sporadically missing from `stdout_chunks`,
            # even though the identical input ran to completion when
            # invoked directly. Draining here guarantees nothing buffered
            # is lost regardless of exactly when that last signal lands.
            if job.process.bytesAvailable():
                job.stdout_chunks.append(
                    bytes(job.process.readAllStandardOutput()).decode("utf-8", errors="replace")
                )
            output_text = "".join(job.stdout_chunks)
            if job.kind == "reference":
                self._finish_reference_job(job, output_text)
            elif job.kind == "conformer":
                chaining = self._finish_conformer_job(job, output_text)
            elif job.kind == "scaling":
                chaining = self._finish_scaling_job(job, output_text)
            else:
                self._finish_calculation_job(job, output_text)
        finally:
            # Guaranteed regardless of which branch above returns --
            # success, cancellation, or a parse failure all reach here.
            # The scratch dir is this conformer's own, so it is cleaned up
            # even mid-sequence; only the job slot is held open.
            self._cleanup_scratch(job.scratch_dir)
            if not chaining:
                self._job_manager.finish(_job_manager_kind(job.kind), key)

    def _finish_calculation_job(self, job: _ActiveJob, output_text: str) -> None:
        molecule_uuid = job.molecule_uuid
        try:
            descriptors, conformer = job.provider.parse_output(output_text, job.mol, molecule_uuid, job.calc_type)
        except Exception as exc:  # noqa: BLE001 - report failure, never crash
            logger.exception("Failed to parse ORCA output for molecule %s", molecule_uuid)
            self._publish_state(molecule_uuid, CacheState.FAILED, str(exc))
            return
        self._event_bus.publish(
            QuantumChemistryResultReady(molecule_uuid=molecule_uuid, descriptors=descriptors, conformer=conformer)
        )
        try:
            spectrum = job.provider.parse_spectrum_output(output_text, job.mol, molecule_uuid, job.calc_type)
        except Exception:  # noqa: BLE001 - a spectrum is an enhancement, must not fail an otherwise-successful job
            logger.exception("Failed to parse spectrum output for molecule %s", molecule_uuid)
        else:
            if spectrum is not None:
                try:
                    couplings = job.provider.parse_spin_spin_coupling(output_text, job.calc_type)
                except Exception:  # noqa: BLE001 - couplings are an enhancement, must not drop the spectrum above
                    logger.exception("Failed to parse spin-spin coupling for molecule %s", molecule_uuid)
                else:
                    if couplings is not None:
                        spectrum = dataclasses.replace(spectrum, couplings=couplings)
                self._event_bus.publish(SpectrumComputed(spectrum=self._maybe_calibrate(spectrum, job.method_basis)))
        self._publish_state(molecule_uuid, CacheState.COMPLETED)

    def _finish_conformer_job(self, job: _ActiveJob, output_text: str) -> bool:
        """Collects one conformer's spectrum + SCF energy, then either
        starts the next conformer or publishes the Boltzmann average.

        Returns True when it started another job, which tells `_on_finished`
        to keep holding the molecule's JobManager slot.
        """
        molecule_uuid = job.molecule_uuid
        run = self._boltzmann_runs.get(molecule_uuid)
        if run is None:  # cancelled or already torn down
            return False
        try:
            descriptors, _conformer = job.provider.parse_output(
                output_text, job.mol, molecule_uuid, job.calc_type
            )
            spectrum = job.provider.parse_spectrum_output(output_text, job.mol, molecule_uuid, job.calc_type)
        except Exception as exc:  # noqa: BLE001 - report failure, never crash
            logger.exception("Failed to parse ORCA output for molecule %s", molecule_uuid)
            self._boltzmann_runs.pop(molecule_uuid, None)
            self._publish_state(molecule_uuid, CacheState.FAILED, str(exc))
            return False
        if spectrum is None:
            self._boltzmann_runs.pop(molecule_uuid, None)
            self._publish_state(
                molecule_uuid, CacheState.FAILED, "ORCA produced no shielding data for this conformer."
            )
            return False

        # The energy that weights this conformer comes from the SAME run
        # that produced its shieldings -- same geometry, same level of
        # theory. Using the RDKit MMFF energy the conformer was embedded
        # with would mix a force-field population with DFT shifts.
        # `<provider_id>.scf_energy` is the convention every QuantumEngine
        # Provider follows for its converged total energy (orca_engine.py's
        # `orca.scf_energy`), so this stays provider-agnostic rather than
        # hardcoding ORCA's id into the service.
        energy_id = f"{job.provider.provider_id}.scf_energy"
        energy = next((d.value for d in descriptors if d.descriptor_id == energy_id), None)
        if energy is None:
            self._boltzmann_runs.pop(molecule_uuid, None)
            self._publish_state(
                molecule_uuid,
                CacheState.FAILED,
                "No SCF energy in ORCA output — cannot weight this conformer.",
            )
            return False

        try:
            couplings = job.provider.parse_spin_spin_coupling(output_text, job.calc_type)
        except Exception:  # noqa: BLE001 - couplings are an enhancement, must not drop the spectrum
            logger.exception("Failed to parse spin-spin coupling for molecule %s", molecule_uuid)
        else:
            if couplings is not None:
                spectrum = dataclasses.replace(spectrum, couplings=couplings)

        run.spectra.append(spectrum)
        run.energies.append(float(energy))

        if run.remaining_mols:
            self._launch_next_conformer(run)
            return True

        self._boltzmann_runs.pop(molecule_uuid, None)
        averaged = boltzmann_average_spectrum(run.spectra, run.energies)
        # Only the averaged spectrum is published, not one event per
        # conformer: the per-conformer shifts are an intermediate, and
        # emitting them would leave the NMR view flickering through
        # geometries that are not what the experiment measures.
        self._event_bus.publish(
            SpectrumComputed(spectrum=self._maybe_calibrate(averaged, run.method_basis))
        )
        self._publish_state(
            molecule_uuid, CacheState.COMPLETED, f"Averaged over {run.total} conformer(s)"
        )
        return False

    def _finish_scaling_job(self, job: _ActiveJob, output_text: str) -> bool:
        """Files one standard's shieldings, then starts the next or fits.

        Returns True when it started another job, which tells
        `_on_finished` to keep holding the calibration's JobManager slot.
        """
        run = self._scaling_runs.get(job.key)
        if run is None:  # cancelled or already torn down
            return False
        try:
            spectrum = job.provider.parse_spectrum_output(
                output_text, job.mol, "__nmr_scaling__", job.calc_type
            )
        except Exception:  # noqa: BLE001 - one bad standard costs a point, not the run
            logger.exception("Failed to parse calibration output for %s", job.compound_name)
            spectrum = None

        if spectrum is None or not spectrum.values:
            run.failed.append(job.compound_name)
        else:
            per_element: dict[str, list[float]] = {}
            for atom_index, shielding in spectrum.values.items():
                element = spectrum.elements.get(atom_index)
                if element is not None:
                    per_element.setdefault(element, []).append(shielding)
            run.shieldings[job.compound_name] = per_element
            # Recorded from the first standard that reports one, so the
            # cache key matches what `_maybe_calibrate` will look up.
            if spectrum.provenance is not None:
                run.orca_version = spectrum.provenance.parameters.get("orca_version", run.orca_version)

        if run.remaining:
            self._launch_next_reference_compound(job.key, run)
            return True
        self._complete_scaling_run(job.key, run)
        return False

    def _complete_scaling_run(self, key: str, run: _ScalingRun) -> None:
        """Fits one line per element and caches whatever passed.

        Elements are fitted INDEPENDENTLY and a refused fit drops only
        that element: carbon and hydrogen genuinely do not succeed or fail
        together (measured -- at HF/STO-3G carbon fits at R^2 0.979 while
        hydrogen comes out at 0.859), so an all-or-nothing calibration
        would throw away a good carbon line because of a bad proton one.
        """
        from openchem.chem.nmr_scaling import CalibrationError, fit_scaling, reference_points

        self._scaling_runs.pop(key, None)
        factors = {}
        reasons = []
        for element in ("H", "C"):
            points = reference_points(
                {name: values.get(element, []) for name, values in run.shieldings.items()}, element
            )
            try:
                factors[element] = fit_scaling(points)
            except CalibrationError as exc:
                reasons.append(f"{element}: {exc}")

        if not factors:
            message = " ".join(reasons) or "No reference calculation produced usable shieldings."
            self._fail_scaling(run.method_basis, run.provider.provider_id, message)
            self._publish_state(key, CacheState.FAILED, message)
            return

        for element, fitted in factors.items():
            prefix = f"orca/nmr_scaling/{run.method_basis}/{run.orca_version}/{element}"
            self._settings.set(f"{prefix}/slope", fitted.slope)
            self._settings.set(f"{prefix}/intercept", fitted.intercept)
            self._settings.set(f"{prefix}/r_squared", fitted.r_squared)
            self._settings.set(f"{prefix}/sample_count", fitted.sample_count)

        self._event_bus.publish(
            NmrScalingCalibrated(
                method_basis=run.method_basis,
                provider_id=run.provider.provider_id,
                factors=factors,
                # A partial success still reports what went wrong, so a
                # missing element is explained rather than just absent.
                error="; ".join(reasons) or None,
            )
        )
        self._publish_state(
            key,
            CacheState.COMPLETED,
            f"Calibrated {', '.join(sorted(factors))} from {len(run.shieldings)} standard(s)",
        )

    def _cached_scaling_factors(self, method_basis: str, orca_version: str) -> dict:
        from openchem.domain.nmr import ScalingFactors

        factors = {}
        for element in ("H", "C"):
            prefix = f"orca/nmr_scaling/{method_basis}/{orca_version}/{element}"
            slope = self._settings.get(f"{prefix}/slope", None)
            intercept = self._settings.get(f"{prefix}/intercept", None)
            if slope is None or intercept is None:
                continue
            factors[element] = ScalingFactors(
                slope=float(slope),
                intercept=float(intercept),
                r_squared=float(self._settings.get(f"{prefix}/r_squared", 0.0) or 0.0),
                sample_count=int(self._settings.get(f"{prefix}/sample_count", 0) or 0),
            )
        return factors

    def _maybe_calibrate(self, spectrum, method_basis: str):
        # Local import avoids a hard dependency on nmr_reference for every
        # QuantumChemistryService caller/test that never touches NMR at
        # all -- mirrors how orca_engine is already imported at module
        # scope but nmr_reference's TMS/embedding machinery is only
        # needed on this one path.
        from openchem.chem.nmr_reference import chemical_shift_from_reference

        orca_version = (spectrum.provenance.parameters.get("orca_version", "unknown") if spectrum.provenance else "unknown")

        # Empirical scaling WINS over plain TMS subtraction where both are
        # cached, because subtraction is the special case of scaling with
        # the slope forced to -1 -- and that forced slope is most of the
        # residual error (measured at B3LYP/def2-SVP: carbon 1.5 ppm
        # scaled against ~11.3 subtracted). Falls back rather than
        # requiring both, so an existing TMS-only setup keeps working
        # exactly as before.
        scaling = self._cached_scaling_factors(method_basis, orca_version)
        if scaling:
            return self._apply_scaling(spectrum, scaling)

        reference: dict[str, float] = {}
        for element in ("H", "C"):
            cached = self._settings.get(f"orca/nmr_reference/{method_basis}/{orca_version}/{element}", None)
            if cached is not None:
                reference[element] = float(cached)
        if not reference:
            return spectrum  # no cached reference yet -- raw shielding, unchanged
        calibrated = chemical_shift_from_reference(spectrum, reference)
        return calibrated if calibrated is not None else spectrum

    def _apply_scaling(self, spectrum, factors: dict):
        """Rebuild the spectrum in real ppm, one `spectrum_type` per
        nucleus.

        Mirrors `chemical_shift_from_reference`'s output shape rather than
        inventing a second one -- the NMR view and the signal grouping
        both key off `spectrum_type`, so a scaled result has to be
        indistinguishable in shape from a TMS-referenced one. Returns the
        spectrum unchanged if scaling would leave it empty (every atom's
        element uncalibrated), since an empty spectrum reads as a failed
        calculation.
        """
        from openchem.chem.nmr_scaling import scale_spectrum

        scaled_values = scale_spectrum(spectrum.values, spectrum.elements, factors)
        if not scaled_values:
            return spectrum

        elements_present = {spectrum.elements.get(index) for index in scaled_values}
        spectrum_type = (
            SPECTRUM_TYPE_BY_ELEMENT.get(next(iter(elements_present)), spectrum.spectrum_type)
            if len(elements_present) == 1
            else "nmr_shifts"
        )
        parameters = dict(spectrum.provenance.parameters) if spectrum.provenance else {}
        parameters["referencing"] = "empirical_linear_scaling"
        for element, fitted in factors.items():
            parameters[f"scaling_{element}"] = {
                "slope": fitted.slope,
                "intercept": fitted.intercept,
                "r_squared": fitted.r_squared,
                "sample_count": fitted.sample_count,
            }
        # Provenance is CREATED when absent rather than left None: how a
        # value was referenced is the difference between 128 ppm and a raw
        # shielding of 57, and a result that does not say which is a
        # result nobody can check.
        provenance = (
            dataclasses.replace(spectrum.provenance, parameters=parameters)
            if spectrum.provenance is not None
            else Provenance(created_by="core", method="empirical_linear_scaling", parameters=parameters)
        )
        return dataclasses.replace(
            spectrum,
            values=scaled_values,
            units="ppm",
            spectrum_type=spectrum_type,
            provenance=provenance,
        )

    def _finish_reference_job(self, job: _ActiveJob, output_text: str) -> None:
        method_basis = job.method_basis
        try:
            spectrum = job.provider.parse_spectrum_output(output_text, job.mol, "__tms_reference__", job.calc_type)
        except Exception as exc:  # noqa: BLE001 - report failure, never crash
            logger.exception("Failed to parse ORCA reference output for %s", method_basis)
            self._event_bus.publish(
                NmrReferenceCalibrated(
                    method_basis=method_basis, provider_id=job.provider.provider_id, values={}, error=str(exc)
                )
            )
            self._publish_state(job.key, CacheState.FAILED, str(exc))
            return
        if spectrum is None:
            message = "ORCA produced no shielding data for the reference calculation."
            self._event_bus.publish(
                NmrReferenceCalibrated(
                    method_basis=method_basis, provider_id=job.provider.provider_id, values={}, error=message
                )
            )
            self._publish_state(job.key, CacheState.FAILED, message)
            return

        averaged = average_reference_shielding(spectrum)
        orca_version = spectrum.provenance.parameters.get("orca_version", "unknown") if spectrum.provenance else "unknown"
        for element, value in averaged.items():
            self._settings.set(f"orca/nmr_reference/{method_basis}/{orca_version}/{element}", value)
        self._event_bus.publish(
            NmrReferenceCalibrated(method_basis=method_basis, provider_id=job.provider.provider_id, values=averaged)
        )
        self._publish_state(job.key, CacheState.COMPLETED)

    def _cleanup_scratch(self, scratch_dir: Path) -> None:
        try:
            shutil.rmtree(scratch_dir, ignore_errors=True)
        except OSError:
            logger.warning("Failed to clean up ORCA scratch directory %s", scratch_dir)

    def _publish_state(self, molecule_uuid: str, state: CacheState, message: str = "") -> None:
        if message:
            self._job_manager.update_message(_JOB_KIND, molecule_uuid, message)
        self._event_bus.publish(
            QuantumChemistryJobStateChanged(molecule_uuid=molecule_uuid, state=state, message=message)
        )

    def _resolve_executable_path(self) -> str | None:
        configured = self._settings.get("orca/executable_path", "")
        if configured and Path(configured).is_file():
            return configured
        return shutil.which("orca") or shutil.which("orca.exe")
