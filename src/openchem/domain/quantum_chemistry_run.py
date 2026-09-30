"""One executed ORCA calculation, with the outputs it produced.

**A SEPARATE, DURABLE COLLECTION -- NOT A SLOT IN `SessionResultStore`.**
That store is, by its own docstring, "enough to undo back through a handful
of edits without recomputing; not a history": `_MoleculeRecord.results` is
keyed by `(result_id, calculation_input, input_fingerprint, method_version)`
with no room for the calculation's parameters (method/basis/charge/...), and
`to_dict()` deliberately drops any result whose fingerprint no longer
matches the molecule's CURRENT structure on save -- correct for a bounded
revision cache, wrong for a QC run, which must survive exactly "run NMR,
edit the molecule, run IR, save" intact. Widening that store's key instead
would touch `fresh_results()`, `_trim()` and `bundle_state()` for every
other calculator that already depends on their current one-result-per-slot
behaviour, to solve a problem specific to this one caller. This module is
the alternative: its own identity, its own retention (unconditional -- no
current-fingerprint pruning), and its own store, reusing `result_codec` for
the individual results it holds but nothing else from `result_store.py`.

**A RUN IS THE UNIT, NOT A RESULT.** One ORCA job produces a bundle --
a spectrum, maybe a vibrational spectrum, several descriptors, maybe an
optimized conformer -- and a user asked for that bundle with one Run click,
not for four independently-timestamped results that happen to agree. Every
output a run produced is addressed by an exact key on `QuantumChemistryRun`
itself (`results[key]`), never by a bare `result_id` string two different
runs could both use -- the failure mode `["nmr_1h", "orca.scf_energy"]`
would have, once more than one run exists.

**TMS reference and empirical-scaling calibration are not runs here.**
`request_reference_calibration`/`request_scaling_calibration`
(`services/quantum_chemistry_service.py`) always run on a fixed reference
compound (`chem/nmr_reference.tms_molecule()`), never the selected molecule,
and cache their result into `Settings` -- an application-level calibration
cache, not a record of something the user calculated about their molecule.
Only `_finish_calculation_job`/`_finish_conformer_job` mint a
`QuantumChemistryRun`.
"""

from __future__ import annotations

import enum
import logging
import time
import uuid as uuid_module
from dataclasses import dataclass, field
from typing import Any

from openchem.domain import result_codec

logger = logging.getLogger("openchem.quantum_chemistry_run")

#: The on-disk block's own layout version, independent of
#: `result_store.ENVELOPE_VERSION` -- this is a different collection with a
#: different retention policy, not a variant of that one.
ENVELOPE_VERSION = 1


class RunStatus(enum.Enum):
    """The calculation's own lifecycle, not any one output's.

    A coupling-parser failure (an ENHANCEMENT the service deliberately lets
    fail without dropping the base spectrum -- see
    `NMRSpectrumResult.coupling_error`) makes a run COMPLETED_WITH_WARNINGS,
    never FAILED: the job the user asked for came back with a usable
    result, just not every part of it. FAILED is reserved for a run whose
    core output (the thing the calc_type promises) never parsed at all.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"

    #: Persisted states only -- a project file never records RUNNING. This
    #: application has no way to reconnect to a process that was mid-flight
    #: when it last closed, so a serialized RUNNING entry would be a record
    #: of nothing anyone could act on; the run is simply not written for a
    #: still-in-flight job (see `QuantumChemistryRunStore.record`'s
    #: docstring).
    @classmethod
    def persisted_states(cls) -> frozenset["RunStatus"]:
        return frozenset({cls.COMPLETED, cls.COMPLETED_WITH_WARNINGS, cls.FAILED, cls.CANCELLED})


class OutputStatus(enum.Enum):
    """Why a given output is or is not there for THIS run -- the axis a
    run's own `RunStatus` cannot carry on its own. "NMR spectrum available,
    spin-spin coupling failed, IR not produced by this run" needs both."""

    AVAILABLE = "available"
    #: This calc_type never produces this output (IR after an NMR-only run).
    NOT_PRODUCED = "not_produced"
    #: This calc_type could produce it, but this molecule/method cannot
    #: (IR from a single-point calculation, which has no vibrational modes).
    INAPPLICABLE = "inapplicable"
    #: Requested and attempted, but the ORCA output did not parse.
    FAILED = "failed"


def new_run_id() -> str:
    return uuid_module.uuid4().hex


@dataclass
class QuantumChemistryRun:
    """One `_finish_calculation_job`/`_finish_conformer_job` completion,
    everything it produced, and everything needed to redisplay it later
    without depending on the molecule's CURRENT state.

    `input_molblock`/`input_conformer_id` are an immutable snapshot of what
    was actually submitted -- not "ask `canonical_conformer(molecule)` again
    later", which can silently answer with a different conformer once more
    have been generated. `output_conformer_id` is which conformer THIS run's
    `AddConformerCommand` added (main_window.py already does this for the
    live/newest run; a stored run just has to remember which one was its),
    never "the molecule's optimized conformer" generically -- a later run's
    optimization must not retroactively change what an older run displays.
    """

    run_id: str
    molecule_uuid: str
    calc_type: str
    method_basis: str
    charge: int
    multiplicity: int
    #: DRAWING / GEOMETRY / ENSEMBLE -- display/provenance only. Never used
    #: to address this run in the store; `run_id` alone does that.
    calculation_input: str
    input_fingerprint: str
    input_molblock: str
    input_conformer_id: str | None = None
    solvent: str = ""
    provider: str = "orca"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status: RunStatus = RunStatus.RUNNING
    #: Human-readable, e.g. "Spin-spin coupling output could not be parsed"
    #: -- what made this COMPLETED_WITH_WARNINGS rather than plain COMPLETED.
    warnings: list[str] = field(default_factory=list)
    output_conformer_id: str | None = None
    #: The exact `services.result_cache` entry this run's wavefunction was
    #: retained under, if any -- so a historical Surfaces view resolves
    #: THIS run's `.gbw`, not "whatever the cache currently holds for this
    #: molecule+method" (a later run at a different method/basis would have
    #: silently replaced that).
    surface_cache_key: str | None = None
    #: Raw ORCA stdout is never persisted here -- an optimization can run to
    #: megabytes of it, and retaining every historical run's would grow a
    #: project file without bound. A historical run's ORCA Log tab reads
    #: this flag and says "not retained" rather than showing an unexplained
    #: blank; only the LIVE run's log (already just a `QPlainTextEdit`
    #: this session) has real content.
    log_retained: bool = False
    #: output key ("spectrum", "vibrational_spectrum", "descriptors") -> the
    #: actual result object(s). A list under "descriptors" since one run
    #: produces several `DescriptorValue`s; every other key holds exactly
    #: one result.
    results: dict[str, Any] = field(default_factory=dict)
    #: output key -> why it is or is not in `results` -- see `OutputStatus`.
    output_status: dict[str, OutputStatus] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.status in RunStatus.persisted_states()

    def to_dict(self) -> dict[str, Any]:
        encoded_results: dict[str, Any] = {}
        for key, value in self.results.items():
            if isinstance(value, list):
                encoded_results[key] = [result_codec.encode(item) for item in value]
            else:
                encoded_results[key] = result_codec.encode(value)
        return {
            "run_id": self.run_id,
            "molecule_uuid": self.molecule_uuid,
            "calc_type": self.calc_type,
            "method_basis": self.method_basis,
            "charge": self.charge,
            "multiplicity": self.multiplicity,
            "calculation_input": self.calculation_input,
            "input_fingerprint": self.input_fingerprint,
            "input_molblock": self.input_molblock,
            "input_conformer_id": self.input_conformer_id,
            "solvent": self.solvent,
            "provider": self.provider,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "warnings": list(self.warnings),
            "output_conformer_id": self.output_conformer_id,
            "surface_cache_key": self.surface_cache_key,
            "log_retained": self.log_retained,
            "results": encoded_results,
            "output_status": {key: status.value for key, status in self.output_status.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuantumChemistryRun | None":
        """`None` on anything unreadable -- one damaged run must not break
        loading every other run in the project, the same contract
        `SessionResultStore._load_entry` already keeps."""
        try:
            status = RunStatus(data["status"])
            if status not in RunStatus.persisted_states():
                logger.warning("Dropping a run saved with a non-terminal status %r", data.get("status"))
                return None
            results: dict[str, Any] = {}
            for key, raw in (data.get("results") or {}).items():
                if isinstance(raw, list):
                    results[key] = [result_codec.decode(item) for item in raw]
                else:
                    results[key] = result_codec.decode(raw)
            output_status = {
                key: OutputStatus(value) for key, value in (data.get("output_status") or {}).items()
            }
            return cls(
                run_id=str(data["run_id"]),
                molecule_uuid=str(data["molecule_uuid"]),
                calc_type=str(data["calc_type"]),
                method_basis=str(data["method_basis"]),
                charge=int(data["charge"]),
                multiplicity=int(data["multiplicity"]),
                calculation_input=str(data["calculation_input"]),
                input_fingerprint=str(data["input_fingerprint"]),
                input_molblock=str(data["input_molblock"]),
                input_conformer_id=data.get("input_conformer_id"),
                solvent=str(data.get("solvent", "")),
                provider=str(data.get("provider", "orca")),
                started_at=float(data.get("started_at", 0.0)),
                completed_at=data.get("completed_at"),
                status=status,
                warnings=[str(w) for w in data.get("warnings", [])],
                output_conformer_id=data.get("output_conformer_id"),
                surface_cache_key=data.get("surface_cache_key"),
                log_retained=bool(data.get("log_retained", False)),
                results=results,
                output_status=output_status,
            )
        except (KeyError, TypeError, ValueError, result_codec.CodecError) as exc:
            logger.warning("Unreadable saved quantum chemistry run: %s", exc)
            return None


@dataclass
class QuantumChemistryRunStore:
    """Every terminal QC run in one project, by molecule.

    **UNCONDITIONAL PERSISTENCE.** Unlike `SessionResultStore.to_dict()`,
    nothing here is dropped because a molecule's current structure no
    longer matches a run's `input_fingerprint` -- that comparison is
    exactly the bug this module exists to not have (see the module
    docstring). Every terminal run this store holds is written on save.
    """

    project_uuid: str
    #: molecule_uuid -> run_id -> run, newest-inserted last within each
    #: molecule (callers sort by `started_at` for display order).
    _runs: dict[str, dict[str, QuantumChemistryRun]] = field(default_factory=dict)

    def record(self, run: QuantumChemistryRun) -> None:
        """Store a run. Only a TERMINAL run is kept -- a project never
        serializes a RUNNING entry (see `RunStatus.persisted_states`'s
        docstring), so a caller records once the job has actually finished,
        not when it starts. `run_id` is minted at submission time regardless
        (so a run that fails to parse still gets a terminal record with that
        same id), it is simply not stored here until it reaches one."""
        if not run.is_terminal():
            logger.warning("Refusing to store non-terminal run %s (status=%s)", run.run_id, run.status)
            return
        self._runs.setdefault(run.molecule_uuid, {})[run.run_id] = run

    def get(self, run_id: str) -> QuantumChemistryRun | None:
        for by_run in self._runs.values():
            if run_id in by_run:
                return by_run[run_id]
        return None

    def runs_for(self, molecule_uuid: str) -> list[QuantumChemistryRun]:
        """Newest first."""
        return sorted(
            self._runs.get(molecule_uuid, {}).values(), key=lambda r: r.started_at, reverse=True
        )

    def delete(self, run_id: str) -> bool:
        for by_run in self._runs.values():
            if run_id in by_run:
                del by_run[run_id]
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_version": ENVELOPE_VERSION,
            "project_uuid": self.project_uuid,
            "runs": [
                run.to_dict()
                for by_run in self._runs.values()
                for run in by_run.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, project_uuid: str) -> "QuantumChemistryRunStore":
        store = cls(project_uuid)
        if not data:
            return store
        if data.get("envelope_version", 0) > ENVELOPE_VERSION:
            logger.warning(
                "Saved quantum chemistry runs use envelope v%s; ignoring them", data.get("envelope_version")
            )
            return store
        if data.get("project_uuid") not in (None, project_uuid):
            logger.warning(
                "Saved quantum chemistry runs belong to project %s, not %s",
                data.get("project_uuid"),
                project_uuid,
            )
            return store
        for raw in data.get("runs") or []:
            run = QuantumChemistryRun.from_dict(raw)
            if run is not None:
                store.record(run)
        return store
