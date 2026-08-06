"""Plotting a QM surface from a finished job's retained wavefunction.

WHY THIS IS A SERVICE AND NOT A CALCULATOR. Everything else that produces
a `ScalarField` does so from the molecule alone -- the point-charge ESP
needs only coordinates and charges, so the Calculator Inspector computes
it inline. A QM surface needs the `.gbw` a previous ORCA run left behind,
so it is only available for molecules that have HAD a calculation, and it
shells out to `orca_plot`. That is a service's job, not a calculator's.

RUN OFF THE GUI THREAD, because `orca_plot` is a subprocess that takes
seconds -- measured at roughly 1 s for water at 20 points and several for
a 60-point grid on a 12-atom molecule. Fast enough to feel interactive,
far too slow to block a repaint.

`QThreadPool` + `QRunnable` rather than the `QProcess` machinery
`QuantumChemistryService` uses for ORCA itself, and deliberately: that
machinery exists for jobs measured in minutes that need progress,
cancellation and a single-flight guard per molecule. Plotting a surface
needs none of those, and `orca_plot` is driven through stdin, which
`QProcess` makes harder rather than easier.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool

from openchem import paths as app_paths
from openchem.chem.cube import CubeFormatError, read_cube
from openchem.chem.orca_surfaces import (
    SURFACE_KINDS,
    OrcaPlotError,
    SurfaceKind,
    run_orca_plot,
)
from openchem.chem.scalar_field import ScalarField
from openchem.events.base import EventBus
from openchem.events.events import QmSurfaceComputed
from openchem.services import result_cache

logger = logging.getLogger("openchem.chemistry")


class _SurfaceTask(QRunnable):
    """One `orca_plot` invocation, off the GUI thread.

    Publishes through the EventBus, which is safe from a worker because
    `publish` is a Qt signal emit queued onto the bus's own thread -- the
    same contract `_DescriptorComputeTask` relies on.
    """

    def __init__(
        self,
        *,
        molecule_uuid: str,
        gbw_path,
        kind: SurfaceKind,
        orca_plot_executable: str,
        orbital_index: int | None,
        resolution: int,
        event_bus: EventBus,
    ) -> None:
        super().__init__()
        self._molecule_uuid = molecule_uuid
        self._gbw_path = gbw_path
        self._kind = kind
        self._executable = orca_plot_executable
        self._orbital_index = orbital_index
        self._resolution = resolution
        self._event_bus = event_bus

    def run(self) -> None:  # noqa: D102 - QRunnable override
        try:
            cube_path = run_orca_plot(
                self._executable,
                self._gbw_path,
                self._kind,
                orbital_index=self._orbital_index,
                resolution=self._resolution,
            )
            cube = read_cube(cube_path, name=self._kind.label, units=self._kind.units)
        except (OrcaPlotError, CubeFormatError, OSError) as exc:
            logger.warning(
                "QM surface %s failed for molecule %s: %s",
                self._kind.id,
                self._molecule_uuid,
                exc,
            )
            self._event_bus.publish(
                QmSurfaceComputed(
                    molecule_uuid=self._molecule_uuid,
                    surface_id=self._kind.id,
                    field=None,
                    error=str(exc),
                )
            )
            return
        self._event_bus.publish(
            QmSurfaceComputed(
                molecule_uuid=self._molecule_uuid,
                surface_id=self._kind.id,
                field=cube.field,
                error="",
            )
        )


def _fingerprint_of_molblock(molblock: str) -> str:
    """The constitution a molblock describes, in the same form
    `quantum_chemistry_service` records when it retains a wavefunction.

    Both sides must produce the identical string for the comparison to mean
    anything, which is why both are canonical SMILES from RDKit rather than
    one being a hash of the file.
    """
    from rdkit import Chem

    try:
        mol = Chem.MolFromMolBlock(molblock, removeHs=False)
        return Chem.MolToSmiles(mol) if mol is not None else ""
    except Exception:  # noqa: BLE001 - unverifiable, not fatal
        return ""


class QmSurfaceService(QObject):
    """Turns a retained `.gbw` into a `ScalarField` the viewer can colour by."""

    def __init__(
        self,
        event_bus: EventBus,
        settings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._settings = settings
        self._pool = QThreadPool.globalInstance()

    def is_available(self, molecule_uuid: str, molblock: str = "") -> bool:
        """Whether a surface could be plotted for this molecule right now.

        Both halves matter and they fail for different reasons: no
        `orca_plot` means ORCA is not configured, while no wavefunction
        means this particular molecule has never had a calculation. A UI
        that offers the control in either case is offering something that
        cannot work.

        Pass `molblock` and a wavefunction retained for a DIFFERENT
        structure counts as absent -- see `wavefunction_for`.
        """
        return (
            bool(self._orca_plot_path())
            and self.wavefunction_for(molecule_uuid, molblock) is not None
        )

    def wavefunction_for(self, molecule_uuid: str, molblock: str = ""):
        """The retained `.gbw`, or None -- including when it is STALE.

        A wavefunction is retained per molecule uuid, and a uuid survives a
        structure edit. `EditStructureCommand` clears a molecule's
        conformers when its structure changes because they described the
        old structure; nothing gave the wavefunction the same treatment, so
        drawing benzene, running ORCA, editing to toluene and asking for
        the HOMO plotted benzene's orbitals against toluene in silence.

        Given the current structure, this compares it against the one
        recorded when the wavefunction was retained and returns None on a
        mismatch -- a miss, and therefore a recalculation, rather than a
        confident wrong picture. A wavefunction retained before structures
        were recorded is unverifiable and is also refused: one wasted
        recalculation against a silently wrong surface is not a close call.
        """
        candidate = app_paths.wavefunction_root() / molecule_uuid / "job.gbw"
        if candidate.is_file():
            if not molblock:
                return candidate
            recorded = self._recorded_structure(molecule_uuid)
            if recorded and recorded == _fingerprint_of_molblock(molblock):
                return candidate
        # The per-molecule copy missed. Every job also stores its
        # wavefunction content-addressed by structure, so a calculation run
        # on this SAME structure from a different molecule -- an
        # accidentally re-imported duplicate, the same compound in another
        # project, a molecule that was deleted and brought back -- can serve
        # it here instead of costing another ORCA run.
        #
        # Only ever on an exact structure match, so this cannot reintroduce
        # the stale-wavefunction bug the check above exists for: a miss on
        # structure stays a miss.
        return self._wavefunction_from_store(molblock)

    def _wavefunction_from_store(self, molblock: str):
        if not molblock:
            # With no structure to match on there is nothing to be sure
            # about, and guessing here is exactly what the uuid path was
            # doing wrong.
            return None
        entry = result_cache.find(
            "orca_wavefunction", structure=_fingerprint_of_molblock(molblock)
        )
        return entry.file("job.gbw") if entry is not None else None

    def _recorded_structure(self, molecule_uuid: str) -> str:
        path = app_paths.wavefunction_root() / molecule_uuid / "orbitals.json"
        if not path.is_file():
            return ""
        try:
            return str(json.loads(path.read_text(encoding="utf-8")).get("structure", ""))
        except (OSError, ValueError):
            return ""

    def frontier_orbitals(
        self, molecule_uuid: str, molblock: str = ""
    ) -> tuple[int | None, int | None]:
        """(HOMO, LUMO) indices for the wavefunction that will actually be plotted.

        Read from disk rather than remembered in memory, so a surface can
        still be plotted in a later session from a wavefunction that is
        still there -- which is the whole reason it is retained.

        THESE MUST COME FROM THE SAME PLACE THE `.gbw` DOES. An orbital
        index only means anything against the wavefunction it was recorded
        with -- HOMO is orbital 20 for one molecule and orbital 34 for
        another -- so serving a stored wavefunction while reading the index
        from a different job would plot the wrong orbital and label it
        confidently. `molblock` is threaded through for exactly that
        reason: it selects the same entry `wavefunction_for` selects.
        """
        path = app_paths.wavefunction_root() / molecule_uuid / "orbitals.json"
        recorded = self._recorded_structure(molecule_uuid)
        fingerprint = _fingerprint_of_molblock(molblock) if molblock else ""
        uuid_copy_is_usable = path.is_file() and (not fingerprint or recorded == fingerprint)
        if uuid_copy_is_usable:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None, None
            return data.get("homo"), data.get("lumo")

        if not fingerprint:
            return None, None
        entry = result_cache.find("orca_wavefunction", structure=fingerprint)
        if entry is None:
            return None, None
        return entry.metadata.get("homo"), entry.metadata.get("lumo")

    def request_surface(
        self,
        molecule_uuid: str,
        surface_id: str,
        *,
        orbital: str = "",
        orbital_index: int | None = None,
        resolution: int = 60,
        molblock: str = "",
    ) -> bool:
        """Queue one surface. Returns False when it cannot be attempted.

        `molblock` selects the wavefunction the same way `is_available`
        does, and passing it matters for two separate reasons. It lets a
        wavefunction stored for this exact structure under a different
        molecule be used, so the button `is_available` enabled does not
        then fail. And it applies the stale-structure check HERE too --
        without it this method would happily plot a wavefunction for a
        structure the molecule no longer has, which is the check
        `is_available` performs and this one skipped.

        `orbital` names a frontier orbital ("homo"/"lumo") and is resolved
        against the indices retained from the job -- which is the only way
        a caller can ask for one, since the index depends on the basis
        set. `orbital_index` overrides it for a caller that already knows
        the number.

        A synchronous False rather than a failure event for the "not set
        up" cases, because they are not results: the caller should not
        have offered the action, and a greyed-out control beats an error
        afterwards.
        """
        kind = SURFACE_KINDS.get(surface_id)
        if kind is None:
            raise ValueError(f"unknown surface kind {surface_id!r}")
        executable = self._orca_plot_path()
        gbw = self.wavefunction_for(molecule_uuid, molblock)
        if not executable or gbw is None:
            return False

        if kind.needs_orbital and orbital_index is None:
            homo, lumo = self.frontier_orbitals(molecule_uuid, molblock)
            orbital_index = {"homo": homo, "lumo": lumo}.get(orbital.lower())
            if orbital_index is None:
                # Refused rather than defaulted to orbital 0, which is a
                # real orbital (a core 1s) and would render a perfectly
                # good picture of something nobody asked for.
                return False

        self._pool.start(
            _SurfaceTask(
                molecule_uuid=molecule_uuid,
                gbw_path=gbw,
                kind=kind,
                orca_plot_executable=executable,
                orbital_index=orbital_index,
                resolution=resolution,
                event_bus=self._event_bus,
            )
        )
        return True

    def _orca_plot_path(self) -> str:
        """`orca_plot` beside the configured `orca` executable.

        Derived rather than separately configured: they ship in the same
        directory and always have, and a second path setting is a second
        thing to get out of step with the first.
        """
        configured = self._settings.get("orca/executable_path", "")
        if not configured:
            return ""
        from pathlib import Path

        candidate = Path(configured).with_name(
            "orca_plot.exe" if Path(configured).suffix.lower() == ".exe" else "orca_plot"
        )
        return str(candidate) if candidate.is_file() else ""


__all__ = ["QmSurfaceService", "ScalarField"]
