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
from openchem.chem.nmr_reference import average_reference_shielding, tms_molecule
from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.domain.common import CacheState
from openchem.events.base import EventBus
from openchem.events.events import (
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

# TMS is neutral, closed-shell -- fixed, not user-configurable (only
# method_basis varies per reference calibration request).
_TMS_CHARGE = 0
_TMS_MULTIPLICITY = 1


def _reference_job_key(method_basis: str) -> str:
    return f"__nmr_reference__::{method_basis}"


@dataclass
class _ActiveJob:
    key: str
    mol: Chem.Mol
    provider: QuantumEngineProvider
    calc_type: str
    scratch_dir: Path
    process: QProcess
    kind: str = "calculation"  # "calculation" | "reference"
    molecule_uuid: str | None = None  # only set for kind == "calculation"
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

        # A space-free scratch directory is a hard requirement: ORCA's own
        # documentation warns against running from a path containing
        # spaces, and this project's own working directory (a checkout
        # under "D:\...\OpenChem Studio\") does contain one — never derive
        # the scratch dir from the project/source path.
        cache_root = Path(platformdirs.user_cache_dir(_APP_NAME, appauthor=False))
        cache_root.mkdir(parents=True, exist_ok=True)
        scratch_dir = Path(tempfile.mkdtemp(prefix="orca_job_", dir=str(cache_root)))

        job_kind_for_manager = _JOB_KIND if kind == "calculation" else _REFERENCE_JOB_KIND
        try:
            input_text = provider.build_input(mol, charge, multiplicity, method_basis, calc_type)
        except Exception as exc:  # noqa: BLE001 - bad input params, report don't crash
            self._cleanup_scratch(scratch_dir)
            self._publish_state(key, CacheState.FAILED, f"Failed to build input: {exc}")
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
            if job.kind == "reference":
                self._event_bus.publish(
                    NmrReferenceCalibrated(
                        method_basis=job.method_basis, provider_id=job.provider.provider_id, values={}, error=message
                    )
                )
            else:
                self._publish_state(key, CacheState.FAILED, message)
        finally:
            self._cleanup_scratch(job.scratch_dir)
            job_kind_for_manager = _JOB_KIND if job.kind == "calculation" else _REFERENCE_JOB_KIND
            self._job_manager.finish(job_kind_for_manager, key)

    def _on_finished(self, key: str) -> None:
        job = self._active_jobs.pop(key, None)
        if job is None:
            return
        try:
            if job.cancelled:
                if job.kind == "reference":
                    self._event_bus.publish(
                        NmrReferenceCalibrated(
                            method_basis=job.method_basis,
                            provider_id=job.provider.provider_id,
                            values={},
                            error="Cancelled by user",
                        )
                    )
                else:
                    self._publish_state(key, CacheState.FAILED, "Cancelled by user")
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
            else:
                self._finish_calculation_job(job, output_text)
        finally:
            # Guaranteed regardless of which branch above returns --
            # success, cancellation, or a parse failure all reach here.
            self._cleanup_scratch(job.scratch_dir)
            job_kind_for_manager = _JOB_KIND if job.kind == "calculation" else _REFERENCE_JOB_KIND
            self._job_manager.finish(job_kind_for_manager, key)

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

    def _maybe_calibrate(self, spectrum, method_basis: str):
        # Local import avoids a hard dependency on nmr_reference for every
        # QuantumChemistryService caller/test that never touches NMR at
        # all -- mirrors how orca_engine is already imported at module
        # scope but nmr_reference's TMS/embedding machinery is only
        # needed on this one path.
        from openchem.chem.nmr_reference import chemical_shift_from_reference

        orca_version = (spectrum.provenance.parameters.get("orca_version", "unknown") if spectrum.provenance else "unknown")
        reference: dict[str, float] = {}
        for element in ("H", "C"):
            cached = self._settings.get(f"orca/nmr_reference/{method_basis}/{orca_version}/{element}", None)
            if cached is not None:
                reference[element] = float(cached)
        if not reference:
            return spectrum  # no cached reference yet -- raw shielding, unchanged
        calibrated = chemical_shift_from_reference(spectrum, reference)
        return calibrated if calibrated is not None else spectrum

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
