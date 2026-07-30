from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs
from PySide6.QtCore import QObject, QProcess
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.domain.common import CacheState
from openchem.events.base import EventBus
from openchem.events.events import (
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


@dataclass
class _ActiveJob:
    molecule_uuid: str
    mol: Chem.Mol
    provider: QuantumEngineProvider
    calc_type: str
    scratch_dir: Path
    process: QProcess
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
    isn't a supported use case in V1.
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

        self._publish_state(molecule_uuid, CacheState.QUEUED)

        # A space-free scratch directory is a hard requirement: ORCA's own
        # documentation warns against running from a path containing
        # spaces, and this project's own working directory (a checkout
        # under "D:\...\OpenChem Studio\") does contain one — never derive
        # the scratch dir from the project/source path.
        cache_root = Path(platformdirs.user_cache_dir(_APP_NAME, appauthor=False))
        cache_root.mkdir(parents=True, exist_ok=True)
        scratch_dir = Path(tempfile.mkdtemp(prefix="orca_job_", dir=str(cache_root)))

        try:
            input_text = provider.build_input(mol, charge, multiplicity, method_basis, calc_type)
        except Exception as exc:  # noqa: BLE001 - bad input params, report don't crash
            self._cleanup_scratch(scratch_dir)
            self._publish_state(molecule_uuid, CacheState.FAILED, f"Failed to build input: {exc}")
            self._job_manager.finish(_JOB_KIND, molecule_uuid)
            return

        input_path = scratch_dir / "job.inp"
        input_path.write_text(input_text, encoding="utf-8")

        process = QProcess(self)
        args = provider.command_args(executable_path, input_path)
        job = _ActiveJob(
            molecule_uuid=molecule_uuid,
            mol=mol,
            provider=provider,
            calc_type=calc_type,
            scratch_dir=scratch_dir,
            process=process,
        )
        self._active_jobs[molecule_uuid] = job

        process.setWorkingDirectory(str(scratch_dir))
        process.readyReadStandardOutput.connect(lambda: self._on_stdout(molecule_uuid))
        process.finished.connect(lambda code, status: self._on_finished(molecule_uuid))
        process.errorOccurred.connect(lambda error: self._on_process_error(molecule_uuid, error))

        process.setProgram(args[0])
        process.setArguments([str(a) for a in args[1:]])
        process.start()
        self._publish_state(molecule_uuid, CacheState.RUNNING, "Starting")

    def cancel(self, molecule_uuid: str) -> None:
        job = self._active_jobs.get(molecule_uuid)
        if job is None:
            return
        job.cancelled = True
        job.process.kill()

    def _on_stdout(self, molecule_uuid: str) -> None:
        job = self._active_jobs.get(molecule_uuid)
        if job is None:
            return
        chunk = bytes(job.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        job.stdout_chunks.append(chunk)
        last_line = next((line for line in reversed(chunk.splitlines()) if line.strip()), "")
        self._publish_state(molecule_uuid, CacheState.RUNNING, last_line)

    def _on_process_error(self, molecule_uuid: str, error: QProcess.ProcessError) -> None:
        # Covers the process failing to even start (e.g. a bad executable
        # path) -- `finished` never fires in that case, so cleanup must
        # happen here instead. Confirmed directly: `errorOccurred` ALSO
        # fires (with ProcessError.Crashed) when an already-running process
        # is killed via cancel(), racing `_on_finished` for the same job --
        # since dict.pop() makes whichever handler runs first "win," this
        # must check `job.cancelled` too, or a real cancellation gets
        # reported as a generic crash instead of "Cancelled by user."
        job = self._active_jobs.pop(molecule_uuid, None)
        if job is None:
            return
        try:
            if job.cancelled:
                self._publish_state(molecule_uuid, CacheState.FAILED, "Cancelled by user")
            else:
                self._publish_state(molecule_uuid, CacheState.FAILED, f"Process error: {error}")
        finally:
            self._cleanup_scratch(job.scratch_dir)
            self._job_manager.finish(_JOB_KIND, molecule_uuid)

    def _on_finished(self, molecule_uuid: str) -> None:
        job = self._active_jobs.pop(molecule_uuid, None)
        if job is None:
            return
        try:
            if job.cancelled:
                self._publish_state(molecule_uuid, CacheState.FAILED, "Cancelled by user")
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
            try:
                descriptors, conformer = job.provider.parse_output(
                    output_text, job.mol, molecule_uuid, job.calc_type
                )
            except Exception as exc:  # noqa: BLE001 - report failure, never crash
                logger.exception("Failed to parse ORCA output for molecule %s", molecule_uuid)
                self._publish_state(molecule_uuid, CacheState.FAILED, str(exc))
                return
            self._event_bus.publish(
                QuantumChemistryResultReady(molecule_uuid=molecule_uuid, descriptors=descriptors, conformer=conformer)
            )
            try:
                spectrum = job.provider.parse_spectrum_output(
                    output_text, job.mol, molecule_uuid, job.calc_type
                )
            except Exception:  # noqa: BLE001 - a spectrum is an enhancement, must not fail an otherwise-successful job
                logger.exception("Failed to parse spectrum output for molecule %s", molecule_uuid)
            else:
                if spectrum is not None:
                    self._event_bus.publish(SpectrumComputed(spectrum=spectrum))
            self._publish_state(molecule_uuid, CacheState.COMPLETED)
        finally:
            # Guaranteed regardless of which branch above returns --
            # success, cancellation, or a parse failure all reach here.
            self._cleanup_scratch(job.scratch_dir)
            self._job_manager.finish(_JOB_KIND, molecule_uuid)

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
