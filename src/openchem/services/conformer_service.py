from __future__ import annotations

import logging
import time

import rdkit
from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.conformer_providers import (
    DEFAULT_ENERGY_WINDOW,
    DEFAULT_RMS_THRESHOLD,
    RDKitConformerProvider,
    distinct_conformers,
)
from openchem.chem.alignment import align_conformers_for_display
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersReady
from openchem.plugins.interfaces import ConformerProvider
from openchem.services.job_manager import JobManager
from openchem.services.progress import ProgressHandle

_JOB_KIND = "conformer"

logger = logging.getLogger("openchem.chemistry")


class _ConformerGenerationTask(QRunnable):
    """Runs one provider's `generate_conformers()` off the GUI thread.

    Publishes RUNNING progress via ConformerJobStateChanged and, on success,
    the results as data via ConformersReady — it never mutates MoleculeModel
    itself. Applying the results to the model is a command's job (see
    commands/conformer_commands.py), the same separation DescriptorService
    keeps for descriptor values.
    """

    def __init__(
        self,
        provider: ConformerProvider,
        engine: ChemistryEngine,
        model: MoleculeModel,
        num_conformers: int,
        optimize: bool,
        event_bus: EventBus,
        job_manager: JobManager,
        progress: ProgressHandle,
        num_embeddings: int | None = None,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._engine = engine
        self._model = model
        # Two different numbers, and conflating them is what made the UI
        # ask for "10 conformers" and hand 10 to the EMBEDDER. Even at a
        # perfect threshold, 10 embeddings of ethylmorphine found at most
        # 6 distinct geometries against a reference lower bound of 12.
        self._num_conformers = num_conformers
        self._num_embeddings = num_embeddings if num_embeddings is not None else num_conformers
        self._optimize = optimize
        self._event_bus = event_bus
        self._job_manager = job_manager
        # Constructed by ConformerService BEFORE this task is scheduled
        # (see request_conformers), same reasoning as DockingService's
        # equivalent: its cancel() must be registered with JobManager
        # ahead of scheduling, not from inside run() on the worker thread.
        self._progress = progress

    def run(self) -> None:
        self._event_bus.publish(
            ConformerJobStateChanged(molecule_uuid=self._model.uuid, state=CacheState.RUNNING)
        )
        try:
            mol = self._engine.mol_from_model(self._model)
            batch = self._provider.generate_conformer_batch(
                mol, self._num_embeddings, self._optimize, on_progress=self._on_progress
            )
            results = batch.results
        except Exception as exc:  # noqa: BLE001 - report failure, never crash the pool
            logger.exception("Conformer generation failed for molecule %s", self._model.uuid)
            self._event_bus.publish(
                ConformerJobStateChanged(
                    molecule_uuid=self._model.uuid, state=CacheState.FAILED, message=str(exc)
                )
            )
            self._job_manager.finish(_JOB_KIND, self._model.uuid)
            return

        if self._progress.is_cancelled():
            # generate_conformers() returns whatever partial results it had
            # accumulated when on_progress told it to stop (best-effort,
            # checked between conformers) -- discarded here rather than
            # reported as a successful (if short) batch, matching
            # Docking/QuantumChemistry's convention that a cancelled job
            # reports FAILED("Cancelled by user"), not a partial COMPLETED.
            self._event_bus.publish(
                ConformerJobStateChanged(
                    molecule_uuid=self._model.uuid, state=CacheState.FAILED, message="Cancelled by user"
                )
            )
            self._job_manager.finish(_JOB_KIND, self._model.uuid)
            return

        # Embedding is random, so N requests for a molecule with fewer than
        # N shapes returns copies. Applied here rather than in the provider
        # so a plugin-supplied provider gets it too, and reported here
        # because this is where every count is known.
        converged = len(results)
        results = distinct_conformers(results)
        distinct = len(results)
        # Sorted ascending by energy, so truncating to the requested count
        # keeps the lowest-energy members rather than an arbitrary slice.
        results = results[: self._num_conformers]
        if distinct < converged:
            logger.info(
                "Kept %d distinct conformer(s) of %d converged for molecule %s",
                distinct,
                converged,
                self._model.uuid,
            )

        method = (
            f"{self._provider.provider_id}+MMFF94/UFF" if self._optimize else self._provider.provider_id
        )
        now = time.time()
        provenance = Provenance(
            created_by="core",
            method=self._provider.provider_id,
            parameters={
                "num_conformers": self._num_conformers,
                "num_embeddings": self._num_embeddings,
                "optimize": self._optimize,
                # EVERY count, because "3 conformers" means something
                # different when 3 were asked for than when 25 were and 22
                # were the same shape -- the latter says the molecule is
                # rigid, which is a result about the molecule. And an
                # embedding failure is not a convergence failure: one
                # "13 disappeared" figure has two different answers, so
                # both are recorded even though the UI shows neither.
                "conformers_attempted": batch.attempted,
                "conformers_embedded": batch.embedded,
                "conformers_converged": batch.converged,
                "embedding_failures": batch.embedding_failures,
                "convergence_failures": batch.convergence_failures,
                "conformers_distinct": distinct,
                "rms_threshold": DEFAULT_RMS_THRESHOLD,
                # A merge VETO, never a claim that two structures with
                # different energies are different conformers. See
                # DEFAULT_ENERGY_WINDOW.
                "energy_window": DEFAULT_ENERGY_WINDOW if self._optimize else None,
                "force_field": "MMFF94/UFF" if self._optimize else None,
                # An RDKit upgrade can move every number above; without
                # this there is nothing to say whether the toolkit or the
                # algorithm changed.
                "rdkit_version": rdkit.__version__,
            },
            timestamp=now,
        )
        conformers = [
            ConformerModel(
                molblock=self._engine.mol_to_molblock(conf_mol),
                energy=energy,
                method=method,
                timestamp=now,
                provenance=provenance,
            )
            for conf_mol, energy in results
        ]
        self._event_bus.publish(ConformersReady(molecule_uuid=self._model.uuid, conformers=conformers))
        # Say so when fewer came back than were asked for, rather than
        # leaving the user to notice "Conformer 1/1" after requesting ten
        # and conclude something failed. Fewer is the correct answer for a
        # rigid molecule, and it reads as a bug unless it is stated.
        #
        # NEVER phrased as "different conformers because their energies
        # differ" -- the energy term declines to merge on insufficient
        # evidence, it does not classify. See DEFAULT_ENERGY_WINDOW.
        message = self._completion_message(batch, distinct, len(conformers))
        self._event_bus.publish(
            ConformerJobStateChanged(
                molecule_uuid=self._model.uuid, state=CacheState.COMPLETED, message=message
            )
        )
        self._job_manager.finish(_JOB_KIND, self._model.uuid)

    def _completion_message(self, batch, distinct: int, returned: int) -> str:
        """What the status line says. Three numbers, not one.

        "100 -> 23" cannot distinguish 77 duplicates from 77 failures, and
        those call for completely different responses from the user --
        nothing, versus a structure that will not embed.
        """
        parts = [f"{returned} conformer(s)"]
        if distinct > returned:
            parts.append(f"{distinct} distinct found, showing the {returned} lowest in energy")
        elif distinct < batch.converged:
            parts.append(
                f"from {batch.converged} converged - the rest were the same shape "
                f"(within {DEFAULT_RMS_THRESHOLD} A and {DEFAULT_ENERGY_WINDOW} kcal/mol)"
            )
        failures = []
        if batch.embedding_failures:
            failures.append(f"{batch.embedding_failures} failed to embed")
        if batch.convergence_failures:
            failures.append(f"{batch.convergence_failures} failed to converge")
        if failures:
            parts.append("; ".join(failures))
        return " - ".join(parts)

    def _on_progress(self, done: int, total: int) -> bool | None:
        message = f"{done}/{total} conformers"
        self._job_manager.update_message(_JOB_KIND, self._model.uuid, message)
        self._event_bus.publish(
            ConformerJobStateChanged(
                molecule_uuid=self._model.uuid,
                state=CacheState.RUNNING,
                message=message,
            )
        )
        return not self._progress.is_cancelled()


class ConformerService:
    """Schedules conformer generation (+ optional geometry optimization) on a
    QThreadPool, moving each request through Queued -> Running ->
    Completed|Failed, same contract as DescriptorService.

    Supports multiple registered providers (keyed by `provider_id`) for
    plugin extensibility, even though only the built-in "rdkit" one is
    exposed through the UI today — the "Generate Conformers" dialog picking
    a provider is a fast-follow, not part of this phase.
    """

    def __init__(
        self,
        event_bus: EventBus,
        engine: ChemistryEngine,
        providers: dict[str, ConformerProvider] | None = None,
        job_manager: JobManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._engine = engine
        default_provider = RDKitConformerProvider()
        self._providers: dict[str, ConformerProvider] = (
            providers if providers is not None else {default_provider.provider_id: default_provider}
        )
        self._pool = QThreadPool.globalInstance()
        self._job_manager = job_manager if job_manager is not None else JobManager()
        #: (molecule uuid, conformer molblocks) -> display-aligned copies.
        self._display_cache: dict[tuple, list[str]] = {}

    def register_provider(self, provider: ConformerProvider) -> None:
        self._providers[provider.provider_id] = provider

    def unregister_provider(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def request_conformers(
        self,
        model: MoleculeModel,
        num_conformers: int,
        optimize: bool,
        provider_id: str = "rdkit",
        num_embeddings: int | None = None,
    ) -> None:
        """`num_conformers` is how many distinct conformers to KEEP;
        `num_embeddings` is how many random embeddings to try in order to
        find them.

        They are separate because a random search finds fewer distinct
        shapes than it takes samples -- 10 embeddings of a drug-like
        molecule found at most 6 distinct geometries against a reference
        lower bound of 12. `None` means "try exactly as many as asked
        for", which is what this method did when it had one number, so an
        existing caller keeps its behaviour.
        """
        provider = self._providers.get(provider_id)
        if provider is None:
            self._event_bus.publish(
                ConformerJobStateChanged(
                    molecule_uuid=model.uuid,
                    state=CacheState.FAILED,
                    message=f"Unknown conformer provider: {provider_id}",
                )
            )
            return
        # Constructed here (main thread, before scheduling) so its
        # cancel() can be registered with JobManager up front -- same
        # reasoning as DockingService's equivalent.
        progress = ProgressHandle()
        if not self._job_manager.try_start(_JOB_KIND, model.uuid, cancel_callback=progress.cancel):
            self._event_bus.publish(
                ConformerJobStateChanged(
                    molecule_uuid=model.uuid,
                    state=CacheState.FAILED,
                    message="A conformer generation job is already running for this molecule.",
                )
            )
            return
        self._event_bus.publish(
            ConformerJobStateChanged(molecule_uuid=model.uuid, state=CacheState.QUEUED)
        )
        self._pool.start(
            _ConformerGenerationTask(
                provider,
                self._engine,
                model,
                num_conformers,
                optimize,
                self._event_bus,
                self._job_manager,
                progress,
                num_embeddings=num_embeddings,
            )
        )

    def display_molblocks(self, model: MoleculeModel) -> list[str]:
        """This molecule's conformers, superimposed for viewing.

        **The viewer cannot do this itself.** `tests/test_layering.py`
        forbids a `ui/` module importing RDKit, and a rigid superposition is
        chemistry-layer work; this is the seam the widget already has to
        reach it through.

        **Recomputed, never stored.** `ConformerModel.molblock` keeps the
        coordinates the generator produced. See
        `chem/alignment.py::align_conformers_for_display` for why the
        alternative -- a transform carried on the model -- was rejected.

        Cached against the identity of the conformer set rather than
        recomputed per frame, because the viewer asks on every navigation
        and a superposition of a large set is not free. The key is the list
        of molblocks itself, so a regenerated set misses and an unchanged
        one hits.
        """
        molblocks = [conformer.molblock for conformer in model.conformers if conformer.molblock]
        if not molblocks:
            return []
        key = (model.uuid, tuple(molblocks))
        cached = self._display_cache.get(key)
        if cached is None:
            cached = align_conformers_for_display(molblocks)
            # One entry: the viewer looks at one molecule at a time, and an
            # unbounded cache of molblock lists is a real amount of memory.
            self._display_cache = {key: cached}
        return cached
