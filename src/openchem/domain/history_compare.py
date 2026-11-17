"""Whether two history records may be compared. Adjacency is not compatibility.

See `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md` §9.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openchem.domain.descriptor import DescriptorValue
from openchem.domain.property_execution import PropertyExecution
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun
from openchem.domain.report import FactCategory, ReportResult
from openchem.domain.result_store import StoredResult

#: Output keys that are molecule-wide scalars (cross-molecule compare is allowed).
_QUANTUM_SCALAR_KEYS = frozenset({"descriptors", "energy", "scf_energy"})


def property_executions_comparable(left: PropertyExecution, right: PropertyExecution) -> str:
    """Empty if the pair may be compared; otherwise a refusal to show."""
    if left.producer != right.producer and left.outputs and right.outputs:
        left_ids = {o.identity.result_id for o in left.outputs}
        right_ids = {o.identity.result_id for o in right.outputs}
        if left_ids.isdisjoint(right_ids):
            return "Those results are different quantities, so they cannot be compared."
    if left.calculation_input != right.calculation_input:
        return "A drawing result and a 3D result are not the same input, so they cannot be compared."
    if left.molecule_uuid != right.molecule_uuid:
        if _has_per_atom(left) or _has_per_atom(right):
            return "Per-atom values cannot be lined up across different molecules."
        return ""
    if left.input_fingerprint != right.input_fingerprint:
        if _has_per_atom(left) or _has_per_atom(right):
            return "Those runs used different structures, so per-atom values would point at the wrong atoms."
    return ""


def quantum_runs_comparable(left: QuantumChemistryRun, right: QuantumChemistryRun) -> str:
    """Empty if the pair may be compared; otherwise a refusal to show."""
    if left.calc_type != right.calc_type:
        return f"{left.calc_type} and {right.calc_type} are different calculation types."
    if left.molecule_uuid != right.molecule_uuid:
        if not _quantum_scalar_only(left) or not _quantum_scalar_only(right):
            return "Spectra and per-atom Quantum outputs cannot be aligned across different molecules."
        return ""
    if left.provider != right.provider and left.method_basis.split()[0:1] == right.method_basis.split()[0:1]:
        # Same functional name, different engine: never mix under one comparison without saying so.
        return (
            f"{left.provider} and {right.provider} are different programs; "
            "their numbers are not the same method even when the functional name matches."
        )
    return ""


def _has_per_atom(execution: PropertyExecution) -> bool:
    for stored in execution.outputs:
        result = stored.result
        if getattr(result, "values", None) is not None and getattr(result, "property_id", None):
            return True
        kind = getattr(result, "kind", "")
        if str(kind).lower() in {"per_atom", "peratom"}:
            return True
        if type(result).__name__ == "PerAtomDataset":
            return True
    return False


def _quantum_scalar_only(run: QuantumChemistryRun) -> bool:
    keys = set(run.results) | set(run.output_status)
    if not keys:
        return True
    return keys <= _QUANTUM_SCALAR_KEYS or keys <= {"descriptors"}


@dataclass(frozen=True)
class NamedCompareRow:
    """One quantity lined up across two history records."""

    label: str
    left: str
    right: str
    delta: float | None = None


def named_values_from_execution(execution: PropertyExecution) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for stored in execution.outputs:
        values.update(_named_values_from_stored(stored))
    return values


def named_values_from_quantum_run(run: QuantumChemistryRun) -> dict[str, Any]:
    values: dict[str, Any] = {}
    descriptors = run.results.get("descriptors") or []
    if isinstance(descriptors, list):
        for item in descriptors:
            if isinstance(item, DescriptorValue):
                values[item.name or item.descriptor_id] = item.value
    for key in ("energy", "scf_energy"):
        if key in run.results and key not in values:
            values[key] = run.results[key]
    return values


def named_compare_rows(left: dict[str, Any], right: dict[str, Any]) -> list[NamedCompareRow]:
    """Side-by-side named numbers; delta when both sides are numeric."""
    rows: list[NamedCompareRow] = []
    for label in sorted(set(left) | set(right)):
        left_raw = left.get(label)
        right_raw = right.get(label)
        left_number = _as_number(left_raw)
        right_number = _as_number(right_raw)
        delta = None
        if left_number is not None and right_number is not None:
            delta = right_number - left_number
        rows.append(
            NamedCompareRow(
                label=label,
                left=_display(left_raw) if label in left else "—",
                right=_display(right_raw) if label in right else "—",
                delta=delta,
            )
        )
    return rows


def _named_values_from_stored(stored: StoredResult) -> dict[str, Any]:
    result = stored.result
    if isinstance(result, DescriptorValue):
        return {result.name or result.descriptor_id: result.value}
    if isinstance(result, ReportResult):
        values: dict[str, Any] = {}
        for fact in result.facts:
            if fact.category is FactCategory.IDENTITY:
                continue
            values[fact.label] = fact.value
        return values
    return {}


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _display(value: Any) -> str:
    if value is None:
        return "—"
    number = _as_number(value)
    if number is not None:
        return f"{number:.6g}"
    return str(value)
