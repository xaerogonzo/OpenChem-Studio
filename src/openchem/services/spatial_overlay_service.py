"""Recomputing shape-valued results for the conformer actually on screen.

**WHY RECOMPUTE RATHER THAN TRANSFORM.** The 3D viewer does not show a
stored conformer; it shows a display-ALIGNED copy, rigidly rotated onto
the lowest-energy one so that stepping between conformers compares shapes
rather than orientations. An annotation computed in the stored frame,
drawn there, would sit plausibly and wrongly.

The obvious fix is to expose the transform `align_conformers_for_display`
computes and discards, and rotate the annotation by it. Measured over
four real conformers of ethylmorphine, recomputing the producer on the
DISPLAYED molblock instead gives an annotation already in the displayed
frame, in 5.2 ms for all four -- so the transform-composition bug class,
whose oracle this project has already recorded as backwards once, never
arises. There is no matrix here to get the wrong way round.

It is also the more correct answer. Each conformer genuinely has its own
dipole (4.43, 5.53, 5.53, 5.19 D across those four), so the overlay shows
what the molecule on screen actually does, which is a different and more
useful question than the one the Properties panel answers.

**WHAT MAY BE RECOMPUTED IS DECLARED, NEVER INFERRED.** A result names
its calculator through `report_id`, which resolves through the registry;
its parameters come from what the routing layer recorded when it ran. If
either cannot be resolved, that annotation is SKIPPED with a reason --
never approximated from current defaults, and never backfilled with the
stored annotation, which is the wrong-frame behaviour this module exists
to prevent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.calculation_input import INPUT_PREFIX
from openchem.domain.calculator import RegistryExecution
from openchem.domain.report import ReportResult, SpatialAnnotation, valid_spatial_annotation
from openchem.events.base import EventBus
from openchem.events.events import SpatialAnnotationsReady
from openchem.services.calculator_registry import CalculatorRegistry

logger = logging.getLogger("openchem.services")

#: The single view is cell 0, so one vocabulary covers both modes and no
#: caller has to special-case "not a gallery".
SINGLE_VIEW_CELL = 0


@dataclass(frozen=True)
class _Recomputable:
    """One calculator that can be re-run for a displayed conformer.

    Deliberately plain data: this crosses into a worker thread, so it
    carries the calculator's ID and the parameters it ran with, never a
    result object, a model, or anything Qt owns.
    """

    calculator_id: str
    parameters: dict


@dataclass
class _CellState:
    """What one viewer cell has asked for and what is under way.

    `token` is the cell's own monotonic counter, so cells never
    invalidate each other -- updating cell 2 must leave a valid result
    for cell 1 alone.
    """

    token: int = 0
    running: int | None = None
    pending: tuple | None = None
    #: Every token this cell has issued that must be rejected on arrival.
    #: Cheaper and clearer than comparing against `token` alone, because
    #: "the overlay was switched off" invalidates without issuing a new
    #: request.
    accepted: int | None = None


def resolvable_annotations(
    reports: list[ReportResult], registry: CalculatorRegistry
) -> tuple[list[_Recomputable], list[str]]:
    """`(what can be recomputed, why the rest cannot)`.

    ORIGIN IS DECLARED. A result names its calculator through `report_id`
    and the registry resolves it; nothing here infers a calculator from a
    display name, an annotation type or the shape of a provenance dict.
    `tests/test_spatial_origin_resolution.py` holds that contract over
    the whole registry, so a future calculator that breaks it fails
    loudly rather than silently losing its overlay.

    PARAMETERS COME FROM THE RECORD, NEVER FROM TODAY'S DEFAULTS. A
    result computed at a non-default setting must be replayed at that
    setting or it is a different calculation wearing the same label --
    which is why `_with_geometry_provenance` records them at all.

    Order follows the caller's list, which follows registry order, so a
    payload is reproducible rather than however a dict happened to
    iterate.
    """
    recomputable: list[_Recomputable] = []
    skipped: list[str] = []
    for report in reports:
        if not getattr(report, "spatial", ()):
            continue
        definition = registry.get(report.report_id)
        if definition is None:
            skipped.append(f"{report.report_id}: not in the calculator registry")
            continue
        if not isinstance(definition.execution, RegistryExecution):
            skipped.append(f"{report.report_id}: service-executed, not re-runnable here")
            continue
        parameters = (report.provenance.parameters or {}).get(f"{INPUT_PREFIX}parameters")
        if parameters is None:
            # Recorded since the overlay work; a result from an older
            # project has none, and guessing would silently replay a
            # different calculation.
            skipped.append(f"{report.report_id}: no recorded parameters to replay")
            continue
        recomputable.append(
            _Recomputable(calculator_id=report.report_id, parameters=dict(parameters))
        )
    return recomputable, skipped


class _OverlayTask(QRunnable):
    """Recomputes every resolvable spatial result for ONE displayed
    conformer, as ONE payload.

    **ATOMIC BY DESIGN.** Independent per-calculator jobs would let a
    slow cone land on top of a fast dipole, showing a half-updated
    overlay whose parts describe the same molecule at different moments.
    One job per cell gives `(cell, token) -> exactly one payload`.

    **A FAILURE IS PARTIAL, NOT FATAL.** One calculator raising must not
    make a perfectly good dipole disappear, so the successes are returned
    with a diagnostic for the failure. What never happens is a fallback
    to the stored annotation: a missing arrow is a smaller error than an
    arrow drawn for a geometry nobody is looking at.

    **THREAD BOUNDARY.** Everything this holds is immutable and
    serialised -- molblock text, calculator ids, parameter dicts. It
    reconstructs its own private RDKit molecule and touches no widget, no
    model and no QObject; the result goes back through the event bus,
    which delivers on the GUI thread.
    """

    def __init__(
        self,
        registry: CalculatorRegistry,
        event_bus: EventBus,
        molecule_uuid: str,
        structure_key: str,
        conformer_index: int,
        cell_index: int,
        token: int,
        molblock: str,
        recomputable: list[_Recomputable],
        skipped: list[str],
    ) -> None:
        super().__init__()
        self._registry = registry
        self._event_bus = event_bus
        self._molecule_uuid = molecule_uuid
        self._structure_key = structure_key
        self._conformer_index = conformer_index
        self._cell_index = cell_index
        self._token = token
        self._molblock = molblock
        self._recomputable = recomputable
        self._skipped = list(skipped)

    def run(self) -> None:
        annotations: list[SpatialAnnotation] = []
        diagnostics = list(self._skipped)
        try:
            from rdkit import Chem

            mol = Chem.MolFromMolBlock(self._molblock, removeHs=False)
            if mol is None:
                diagnostics.append("the displayed conformer could not be parsed")
            else:
                for item in self._recomputable:
                    annotations.extend(self._one(mol, item, diagnostics))
        except Exception as exc:  # noqa: BLE001 - a bad recompute must not kill the pool
            logger.exception("Spatial overlay recompute failed")
            diagnostics.append(f"overlay recompute failed: {exc}")
        # ALWAYS published, including empty: the widget uses this to stop
        # waiting, and a cell that silently never hears back is the
        # failure mode the `finally` in `_CalculationTask` exists for.
        self._event_bus.publish(
            SpatialAnnotationsReady(
                molecule_uuid=self._molecule_uuid,
                structure_key=self._structure_key,
                conformer_index=self._conformer_index,
                cell_index=self._cell_index,
                token=self._token,
                annotations=tuple(annotations),
                diagnostics=tuple(diagnostics),
            )
        )

    def _one(self, mol, item: _Recomputable, diagnostics: list[str]) -> list[SpatialAnnotation]:
        try:
            result = self._registry.compute(
                item.calculator_id, mol, self._molecule_uuid, item.parameters
            )
        except Exception as exc:  # noqa: BLE001 - one calculator must not sink the payload
            logger.info("Overlay recompute of %s failed: %s", item.calculator_id, exc)
            diagnostics.append(f"{item.calculator_id}: {exc}")
            return []
        annotations = [
            annotation
            for annotation in getattr(result, "spatial", ())
            if valid_spatial_annotation(annotation)
        ]
        if not annotations:
            diagnostics.append(
                f"{item.calculator_id}: produced no drawable geometry for this conformer"
            )
        return annotations


class SpatialOverlayService:
    """Keeps each viewer cell's spatial annotations current, off the GUI
    thread, without ever showing one conformer's geometry on another.

    **LATEST WINS, BOUNDED AT TWO.** Per cell there is at most one job
    running and one request pending; a newer request replaces the pending
    one rather than joining a queue, so scrubbing through conformers can
    never build a backlog however fast it is done.

    **CANCELLATION IS DISCARD, AND THAT IS STATED RATHER THAN DRESSED
    UP.** The producers are plain functions with no progress handle to
    check, so a superseded job cannot be interrupted -- it runs to
    completion and its result is dropped on arrival by token. This is the
    same snapshot-and-recheck the 3D viewer already uses for its
    asynchronous camera read.
    """

    def __init__(
        self,
        event_bus: EventBus,
        registry: CalculatorRegistry,
        pool: QThreadPool | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._registry = registry
        self._pool = pool or QThreadPool.globalInstance()
        self._cells: dict[int, _CellState] = {}
        #: Counters a test reads to check the collapse actually collapses
        #: rather than merely appearing to.
        self.jobs_started = 0
        self.requests_superseded = 0

    def _cell(self, cell_index: int) -> _CellState:
        return self._cells.setdefault(cell_index, _CellState())

    def request(
        self,
        cell_index: int,
        molecule_uuid: str,
        structure_key: str,
        conformer_index: int,
        molblock: str,
        reports: list[ReportResult],
    ) -> int:
        """Ask for `cell_index`'s annotations. Returns the accepted token.

        The token is what makes a late answer safe to ignore, so it is
        returned rather than kept private: the caller records it and
        compares on arrival.
        """
        cell = self._cell(cell_index)
        cell.token += 1
        cell.accepted = cell.token
        recomputable, skipped = resolvable_annotations(reports, self._registry)
        payload = (
            molecule_uuid,
            structure_key,
            conformer_index,
            cell.token,
            molblock,
            recomputable,
            skipped,
        )
        if cell.running is not None:
            # Replace whatever was waiting; only the newest matters, and
            # this is what bounds the backlog at one.
            if cell.pending is not None:
                self.requests_superseded += 1
            cell.pending = payload
            return cell.token
        self._start(cell_index, payload)
        return cell.token

    def invalidate(self, cell_index: int) -> None:
        """Stop accepting results for this cell.

        For the overlay being switched off, or the molecule changing:
        a running job finishes and its answer is dropped, and any pending
        request is forgotten. A result from a previous molecule may never
        reach the current one's viewer.
        """
        cell = self._cell(cell_index)
        cell.accepted = None
        cell.pending = None

    def invalidate_all(self) -> None:
        for cell_index in list(self._cells):
            self.invalidate(cell_index)

    def accepts(self, cell_index: int, token: int) -> bool:
        """Whether a result carrying `token` is still wanted."""
        return self._cell(cell_index).accepted == token

    def _start(self, cell_index: int, payload: tuple) -> None:
        molecule_uuid, structure_key, conformer_index, token, molblock, recomputable, skipped = payload
        cell = self._cell(cell_index)
        cell.running = token
        self.jobs_started += 1
        self._pool.start(
            _OverlayTask(
                registry=self._registry,
                event_bus=self._event_bus,
                molecule_uuid=molecule_uuid,
                structure_key=structure_key,
                conformer_index=conformer_index,
                cell_index=cell_index,
                token=token,
                molblock=molblock,
                recomputable=recomputable,
                skipped=skipped,
            )
        )

    def finished(self, cell_index: int, token: int) -> None:
        """Called when a job's result arrives, whatever its fate.

        Starting the pending request HERE rather than when it was made is
        the collapse: everything asked for while a job was running has
        already been reduced to the most recent one.
        """
        cell = self._cell(cell_index)
        if cell.running != token:
            return
        cell.running = None
        if cell.pending is not None:
            payload, cell.pending = cell.pending, None
            self._start(cell_index, payload)
