"""One ordinary calculator invocation, kept as history — not a cache slot.

**A SEPARATE, DURABLE COLLECTION -- NOT A SLOT IN `SessionResultStore`.**
That store is a bounded revision cache: its dictionary key omits
`parameters_key`, and `to_dict(current_fingerprints)` drops results that no
longer match the molecule. Widening that key would change replay, trim and
automatic bundles for every calculator. This module is Option B of
`docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`: an execution id, method/model
and parameter identity, retained unconditionally like
`QuantumChemistryRunStore`.

**AN EXECUTION IS THE UNIT, NOT A RESULT ID.** One Run click may file a
summary and a per-atom table; both sit on the same `execution_id`. A second
click with the same method mints a new id.

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

import enum
import logging
import time
import uuid as uuid_module
from dataclasses import dataclass, field
from typing import Any

from openchem.domain import result_codec
from openchem.domain.result_store import ResultIdentity, StoredResult

logger = logging.getLogger("openchem.property_execution")

#: Independent of `result_store.ENVELOPE_VERSION` and the QC run envelope.
ENVELOPE_VERSION = 1


def new_execution_id() -> str:
    return uuid_module.uuid4().hex


class ExecutionStatus(enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def persisted_states(cls) -> frozenset["ExecutionStatus"]:
        return frozenset({cls.COMPLETED, cls.FAILED, cls.CANCELLED})


def _identity_to_dict(identity: ResultIdentity) -> dict[str, Any]:
    payload = {
        "molecule_uuid": identity.molecule_uuid,
        "result_id": identity.result_id,
        "calculation_input": identity.calculation_input,
        "input_fingerprint": identity.input_fingerprint,
        "producer": identity.producer,
        "parameters_key": identity.parameters_key,
        "method_version": identity.method_version,
    }
    return payload


def _identity_from_dict(data: dict[str, Any]) -> ResultIdentity:
    return ResultIdentity(
        molecule_uuid=str(data["molecule_uuid"]),
        result_id=str(data["result_id"]),
        calculation_input=str(data["calculation_input"]),
        input_fingerprint=str(data["input_fingerprint"]),
        producer=str(data.get("producer", "")),
        parameters_key=str(data.get("parameters_key", "")),
        method_version=str(data.get("method_version", "")),
    )


def _stored_to_dict(stored: StoredResult) -> dict[str, Any]:
    return {
        "identity": _identity_to_dict(stored.identity),
        "application_version": stored.application_version,
        "result": result_codec.encode(stored.result),
    }


def _stored_from_dict(data: dict[str, Any]) -> StoredResult:
    return StoredResult(
        identity=_identity_from_dict(data["identity"]),
        result=result_codec.decode(data["result"]),
        application_version=str(data.get("application_version", "")),
        restored=True,
    )


@dataclass
class PropertyExecution:
    """One calculator invocation and every output it produced."""

    execution_id: str
    molecule_uuid: str
    producer: str
    #: User-selected chemical method/model (EEM, QEq, …), not algorithm revision.
    method_model: str
    parameters_key: str
    calculation_input: str
    input_fingerprint: str
    method_version: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    error: str = ""
    outputs: list[StoredResult] = field(default_factory=list)

    def is_terminal(self) -> bool:
        return self.status in ExecutionStatus.persisted_states()

    def matches_current(self, fingerprints: dict[str, str]) -> bool:
        return fingerprints.get(self.calculation_input) == self.input_fingerprint

    def to_dict(self) -> dict[str, Any]:
        encoded_outputs = []
        for stored in self.outputs:
            try:
                encoded_outputs.append(_stored_to_dict(stored))
            except result_codec.CodecError as exc:
                logger.warning("Not saving an output of execution %s: %s", self.execution_id, exc)
        return {
            "execution_id": self.execution_id,
            "molecule_uuid": self.molecule_uuid,
            "producer": self.producer,
            "method_model": self.method_model,
            "parameters_key": self.parameters_key,
            "calculation_input": self.calculation_input,
            "input_fingerprint": self.input_fingerprint,
            "method_version": self.method_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "error": self.error,
            "outputs": encoded_outputs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PropertyExecution | None":
        try:
            status = ExecutionStatus(data["status"])
            if status not in ExecutionStatus.persisted_states():
                logger.warning("Dropping a property execution with status %r", data.get("status"))
                return None
            outputs: list[StoredResult] = []
            for raw in data.get("outputs") or []:
                try:
                    outputs.append(_stored_from_dict(raw))
                except (KeyError, TypeError, ValueError, result_codec.CodecError) as exc:
                    logger.warning("Unreadable property-execution output: %s", exc)
            return cls(
                execution_id=str(data["execution_id"]),
                molecule_uuid=str(data["molecule_uuid"]),
                producer=str(data["producer"]),
                method_model=str(data.get("method_model", "")),
                parameters_key=str(data.get("parameters_key", "")),
                calculation_input=str(data["calculation_input"]),
                input_fingerprint=str(data["input_fingerprint"]),
                method_version=str(data.get("method_version", "")),
                started_at=float(data.get("started_at", 0.0)),
                completed_at=data.get("completed_at"),
                status=status,
                error=str(data.get("error", "")),
                outputs=outputs,
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Unreadable saved property execution: %s", exc)
            return None


@dataclass
class PropertyExecutionStore:
    """Every terminal ordinary calculator execution in one project, by molecule.

    Unconditional persistence: unlike `SessionResultStore.to_dict()`, nothing
    is dropped because the molecule's current fingerprint moved.
    """

    project_uuid: str
    _executions: dict[str, dict[str, PropertyExecution]] = field(default_factory=dict)

    def record(self, execution: PropertyExecution) -> None:
        if not execution.is_terminal():
            logger.warning(
                "Refusing to store non-terminal execution %s (status=%s)",
                execution.execution_id,
                execution.status,
            )
            return
        self._executions.setdefault(execution.molecule_uuid, {})[execution.execution_id] = execution

    def get(self, execution_id: str) -> PropertyExecution | None:
        for by_id in self._executions.values():
            if execution_id in by_id:
                return by_id[execution_id]
        return None

    def executions_for(self, molecule_uuid: str) -> list[PropertyExecution]:
        """Newest first."""
        return sorted(
            self._executions.get(molecule_uuid, {}).values(),
            key=lambda e: e.started_at,
            reverse=True,
        )

    def all_executions(self) -> list[PropertyExecution]:
        found: list[PropertyExecution] = []
        for by_id in self._executions.values():
            found.extend(by_id.values())
        return found

    def delete(self, execution_id: str) -> bool:
        for by_id in self._executions.values():
            if execution_id in by_id:
                del by_id[execution_id]
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_version": ENVELOPE_VERSION,
            "project_uuid": self.project_uuid,
            "executions": [
                execution.to_dict()
                for by_id in self._executions.values()
                for execution in by_id.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, project_uuid: str) -> "PropertyExecutionStore":
        store = cls(project_uuid)
        if not data:
            return store
        if data.get("envelope_version", 0) > ENVELOPE_VERSION:
            logger.warning(
                "Saved property executions use envelope v%s; ignoring them",
                data.get("envelope_version"),
            )
            return store
        if data.get("project_uuid") not in (None, project_uuid):
            logger.warning(
                "Saved property executions belong to project %s, not %s",
                data.get("project_uuid"),
                project_uuid,
            )
            return store
        for raw in data.get("executions") or []:
            execution = PropertyExecution.from_dict(raw)
            if execution is not None:
                store.record(execution)
        return store


def method_model_of(stored: StoredResult) -> str:
    """The chemical method/model on a stored result, if one is named."""
    result = stored.result
    provenance = getattr(result, "provenance", None)
    parameters = getattr(provenance, "parameters", None) if provenance is not None else None
    if isinstance(parameters, dict):
        for key in ("method", "model", "charge_model"):
            value = parameters.get(key)
            if value:
                return str(value)
    method = getattr(result, "method", None)
    if method:
        return str(method)
    if stored.identity.parameters_key:
        return stored.identity.parameters_key
    return stored.identity.method_version or "default"


def execution_from_stored(stored: StoredResult, *, status: ExecutionStatus | None = None) -> PropertyExecution:
    """A new historical execution whose only output is `stored`. Always a new id."""
    identity = stored.identity
    failed = getattr(getattr(stored.result, "cache_state", None), "value", "") == "failed"
    if status is None:
        status = ExecutionStatus.FAILED if failed else ExecutionStatus.COMPLETED
    now = time.time()
    return PropertyExecution(
        execution_id=new_execution_id(),
        molecule_uuid=identity.molecule_uuid,
        producer=identity.producer or identity.result_id,
        method_model=method_model_of(stored),
        parameters_key=identity.parameters_key,
        calculation_input=identity.calculation_input,
        input_fingerprint=identity.input_fingerprint,
        method_version=identity.method_version,
        started_at=now,
        completed_at=now,
        status=status,
        error=str(getattr(stored.result, "error", "") or ""),
        outputs=[stored],
    )
