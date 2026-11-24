"""Whether two history records may be compared. Adjacency is not compatibility.

See `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md` §9.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from openchem.chem.submitted_structure import submitted_structure_identity
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.property_execution import PropertyExecution
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun
from openchem.domain.report import FactCategory, ReportResult
from openchem.domain.result_store import StoredResult

#: Output keys that are molecule-wide scalars (cross-molecule compare is allowed).
_QUANTUM_SCALAR_KEYS = frozenset({"descriptors", "energy", "scf_energy"})

#: Mixed pair with no allowlist row (or a row that does not extract exactly).
MIXED_UNAPPROVED = (
    "No approved shared quantity is defined for this ordinary run and Quantum job."
)

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


#: Pair-level Quantum input mismatch (drawing, geometry, or ensemble).
QUANTUM_INPUT_MISMATCH = (
    "These runs used different kinds of calculation input, so they cannot be compared."
)

#: Compatible Quantum pair with no family row (not a parser failure).
QUANTUM_FAMILY_EMPTY = (
    "These runs passed the Quantum compatibility checks, but they have no shared "
    "family quantity to compare."
)


def quantum_runs_comparable(left: QuantumChemistryRun, right: QuantumChemistryRun) -> str:
    """Empty if the pair may be compared; otherwise a refusal to show."""
    if left.calc_type != right.calc_type:
        return f"{left.calc_type} and {right.calc_type} are different calculation types."
    if left.calculation_input != right.calculation_input:
        return QUANTUM_INPUT_MISMATCH
    if left.molecule_uuid != right.molecule_uuid:
        if not _quantum_scalar_only(left) or not _quantum_scalar_only(right):
            return "Spectra and per-atom Quantum outputs cannot be aligned across different molecules."
        return ""
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
class MixedQuantity:
    """One ordinary-vs-Quantum scalar that Compare is allowed to tabulate.

    `ordinary_value_ids` are `DescriptorValue.descriptor_id` or `Fact.help_id`,
    never a display label. `ordinary_producers` restricts provenance; it is
    not enough on its own.
    """

    quantity_id: str
    label: str
    units: str
    ordinary_producers: frozenset[str]
    ordinary_result_ids: frozenset[str]
    ordinary_value_ids: frozenset[str]
    quantum_descriptor_ids: frozenset[str]
    quantum_calc_types: frozenset[str]
    allow_cross_molecule: bool = False
    #: Exact matches on `ReportResult.provenance.parameters` (or a
    #: `DescriptorValue`'s, for ordinary descriptors). Booleans use `is`.
    ordinary_parameters: tuple[tuple[str, Any], ...] = ()
    #: Exact matches on the QC descriptor's `provenance.parameters`.
    quantum_parameters: tuple[tuple[str, Any], ...] = ()
    #: When set, `QuantumChemistryRun.charge` must equal this (stale-run guard).
    required_run_charge: int | None = None


#: Ordinary Gasteiger magnitude vs this-run QC Debye. Not EEM/QEq, not ions,
#: not a display-name match. Hückel HOMO/LUMO (beta vs eV) and Miller
#: polarizability stay unlisted.
MIXED_QUANTITIES: tuple[MixedQuantity, ...] = (
    MixedQuantity(
        quantity_id="dipole",
        label="Dipole",
        units="Debye",
        ordinary_producers=frozenset({"dipole_moment"}),
        ordinary_result_ids=frozenset({"dipole_moment"}),
        ordinary_value_ids=frozenset({"dipole.magnitude"}),
        quantum_descriptor_ids=frozenset(
            {"orca.dipole_moment", "psi4.dipole_moment", "xtb.dipole_moment"}
        ),
        quantum_calc_types=frozenset({"sp", "opt", "opt_freq"}),
        allow_cross_molecule=True,
        ordinary_parameters=(("charge_model", "gasteiger"), ("origin_independent", True)),
        quantum_parameters=(("origin_independent", True),),
        required_run_charge=0,
    ),
)


@dataclass(frozen=True)
class MixedHistoryMatch:
    """Validated mixed comparison: one finite number each side, same units."""

    quantity: MixedQuantity
    ordinary_value: float
    quantum_value: float
    units: str


def match_mixed_history(
    execution: PropertyExecution, run: QuantumChemistryRun
) -> MixedHistoryMatch | str:
    """Match one allowlisted quantity, or a refusal.

    Does not consult `named_values_from_execution` / `named_values_from_quantum_run`.
    """
    if execution.calculation_input != run.calculation_input:
        return "A drawing result and a 3D result are not the same input, so they cannot be compared."
    for quantity in MIXED_QUANTITIES:
        matched = _try_mixed_quantity(execution, run, quantity)
        if isinstance(matched, MixedHistoryMatch):
            if (
                execution.molecule_uuid != run.molecule_uuid
                and not quantity.allow_cross_molecule
            ):
                return "Those runs belong to different molecules."
            return matched
        if matched is not None:
            return matched
    return MIXED_UNAPPROVED


def mixed_history_comparable(execution: PropertyExecution, run: QuantumChemistryRun) -> str:
    """Empty if `match_mixed_history` succeeds; otherwise the refusal."""
    outcome = match_mixed_history(execution, run)
    return "" if isinstance(outcome, MixedHistoryMatch) else outcome


def named_row_from_mixed_match(
    match: MixedHistoryMatch, *, ordinary_on_left: bool
) -> NamedCompareRow:
    """One table row. Delta is right minus left, in the user's selected order."""
    if ordinary_on_left:
        left_value, right_value = match.ordinary_value, match.quantum_value
    else:
        left_value, right_value = match.quantum_value, match.ordinary_value
    return NamedCompareRow(
        label=match.quantity.label,
        left=_display(left_value),
        right=_display(right_value),
        delta=right_value - left_value,
    )


def other_history_entries(
    executions: list[PropertyExecution],
    runs: list[QuantumChemistryRun],
    selected: PropertyExecution | QuantumChemistryRun,
) -> list[PropertyExecution | QuantumChemistryRun]:
    """Every retained history record except `selected`."""
    others: list[PropertyExecution | QuantumChemistryRun] = []
    selected_execution = getattr(selected, "execution_id", None)
    selected_run = getattr(selected, "run_id", None)
    for execution in executions:
        if execution.execution_id != selected_execution:
            others.append(execution)
    for run in runs:
        if run.run_id != selected_run:
            others.append(run)
    return others


def history_compare_choice_map(
    pool: list[PropertyExecution | QuantumChemistryRun],
) -> dict[str, PropertyExecution | QuantumChemistryRun]:
    """Stable label -> record. Duplicate short labels get the full id appended."""
    choices: dict[str, PropertyExecution | QuantumChemistryRun] = {}
    for item in pool:
        label = history_compare_label(item)
        if label in choices:
            full_id = getattr(item, "execution_id", None) or getattr(item, "run_id", "")
            label = f"{label} · {full_id}"
        choices[label] = item
    return choices


def history_compare_label(item: PropertyExecution | QuantumChemistryRun) -> str:
    """Picker and column text: kind is explicit."""
    if isinstance(item, QuantumChemistryRun):
        return (
            f"Quantum · {item.calc_type} · {item.provider} · {item.method_basis} · "
            f"{item.run_id[:8]}"
        )
    return (
        f"Property · {item.producer} · {item.method_model} · {item.execution_id[:8]}"
    )


def _try_mixed_quantity(
    execution: PropertyExecution,
    run: QuantumChemistryRun,
    quantity: MixedQuantity,
) -> MixedHistoryMatch | str | None:
    """Match, a specific refusal, or None to try the next allowlist row."""
    if quantity.ordinary_producers and execution.producer not in quantity.ordinary_producers:
        return None
    if run.calc_type not in quantity.quantum_calc_types:
        return None
    if quantity.required_run_charge is not None and run.charge != quantity.required_run_charge:
        return MIXED_UNAPPROVED
    ordinary = _extract_ordinary(execution, quantity)
    if ordinary == "skip":
        return None
    if isinstance(ordinary, str):
        return ordinary
    quantum = _extract_quantum(run, quantity)
    if quantum == "skip":
        return None
    if isinstance(quantum, str):
        return quantum
    ordinary_value, ordinary_units = ordinary
    quantum_value, quantum_units = quantum
    if ordinary_units != quantity.units or quantum_units != quantity.units:
        return MIXED_UNAPPROVED
    return MixedHistoryMatch(
        quantity=quantity,
        ordinary_value=ordinary_value,
        quantum_value=quantum_value,
        units=quantity.units,
    )


def _extract_ordinary(
    execution: PropertyExecution, quantity: MixedQuantity
) -> tuple[float, str] | str:
    found: list[tuple[float, str]] = []
    any_result = False
    for stored in execution.outputs:
        if stored.identity.result_id not in quantity.ordinary_result_ids:
            continue
        any_result = True
        if not _report_parameters_match(stored.result, quantity.ordinary_parameters):
            continue
        found.extend(_ordinary_values_from_result(stored.result, quantity))
    if not any_result:
        return "skip"
    if len(found) != 1:
        return MIXED_UNAPPROVED
    return found[0]


def _ordinary_values_from_result(result: Any, quantity: MixedQuantity) -> list[tuple[float, str]]:
    found: list[tuple[float, str]] = []
    if isinstance(result, DescriptorValue):
        if result.descriptor_id in quantity.ordinary_value_ids:
            number = _finite_number(result.value)
            if number is None:
                return []
            return [(number, result.units)]
        return []
    if isinstance(result, ReportResult):
        for fact in result.facts:
            if fact.category is FactCategory.IDENTITY:
                continue
            if fact.help_id not in quantity.ordinary_value_ids:
                continue
            number = _finite_number(fact.value)
            if number is None:
                continue
            found.append((number, fact.units))
        return found
    return []


def _extract_quantum(
    run: QuantumChemistryRun, quantity: MixedQuantity
) -> tuple[float, str] | str:
    descriptors = run.results.get("descriptors") or []
    if not isinstance(descriptors, list):
        return "skip"
    found: list[tuple[float, str]] = []
    any_id = False
    for item in descriptors:
        if not isinstance(item, DescriptorValue):
            continue
        if item.descriptor_id not in quantity.quantum_descriptor_ids:
            continue
        if item.provider != run.provider:
            continue
        any_id = True
        if not _descriptor_parameters_match(item, quantity.quantum_parameters):
            continue
        number = _finite_number(item.value)
        if number is None:
            continue
        found.append((number, item.units))
    if not any_id:
        return "skip"
    if len(found) != 1:
        return MIXED_UNAPPROVED
    return found[0]


def _finite_number(value: Any) -> float | None:
    number = _as_number(value)
    if number is None or not math.isfinite(number):
        return None
    return number


@dataclass(frozen=True)
class QuantumFamilyQuantity:
    """One Quantum-vs-Quantum scalar that Compare is allowed to tabulate.

    Matching uses `{run.provider}.{suffix}` and `DescriptorValue.provider`,
    never a display name. Eligibility flags are independent: matching model
    is method/basis; matching geometry is `input_fingerprint`; matching
    structure is canonical identity of each run's `input_molblock`. None of
    these is a property of the quantity id string.
    """

    quantity_id: str
    label: str
    units: str
    descriptor_suffixes: frozenset[str]
    calc_types: frozenset[str]
    requires_matching_model: bool
    requires_matching_geometry: bool = False
    requires_matching_structure: bool = False
    #: Exact matches on the descriptor's `provenance.parameters`. Booleans use `is`.
    required_descriptor_parameters: tuple[tuple[str, Any], ...] = ()
    #: When set, `QuantumChemistryRun.charge` must equal this.
    required_run_charge: int | None = None


#: Named Quantum-vs-Quantum scalars. Display names are not a quantity.
#: Entropy term and zero-point energy are engine-specific suffixes.
#: Enthalpy and Gibbs are opt_freq only.
QUANTUM_FAMILY_QUANTITIES: tuple[QuantumFamilyQuantity, ...] = (
    QuantumFamilyQuantity(
        "scf_energy",
        "SCF energy",
        "Hartree",
        frozenset({"scf_energy"}),
        frozenset({"sp", "opt", "opt_freq"}),
        True,
        requires_matching_geometry=False,
        requires_matching_structure=True,
    ),
    QuantumFamilyQuantity(
        "homo_energy",
        "HOMO energy",
        "eV",
        frozenset({"homo_energy"}),
        frozenset({"sp", "opt", "opt_freq"}),
        False,
    ),
    QuantumFamilyQuantity(
        "lumo_energy",
        "LUMO energy",
        "eV",
        frozenset({"lumo_energy"}),
        frozenset({"sp", "opt", "opt_freq"}),
        False,
    ),
    QuantumFamilyQuantity(
        "enthalpy",
        "Enthalpy",
        "Hartree",
        frozenset({"enthalpy"}),
        frozenset({"opt_freq"}),
        True,
        requires_matching_geometry=True,
    ),
    QuantumFamilyQuantity(
        "gibbs_free_energy",
        "Gibbs free energy",
        "Hartree",
        frozenset({"gibbs_free_energy"}),
        frozenset({"opt_freq"}),
        True,
        requires_matching_geometry=True,
    ),
    QuantumFamilyQuantity(
        "dipole_moment",
        "Dipole",
        "Debye",
        frozenset({"dipole_moment"}),
        frozenset({"sp", "opt", "opt_freq"}),
        True,
        requires_matching_geometry=False,
        requires_matching_structure=True,
        required_descriptor_parameters=(("origin_independent", True),),
        required_run_charge=0,
    ),
    QuantumFamilyQuantity(
        "entropy_term",
        "Entropy term",
        "Hartree",
        frozenset({"entropy_term"}),
        frozenset({"opt_freq"}),
        True,
        requires_matching_geometry=True,
    ),
    QuantumFamilyQuantity(
        "zero_point_energy",
        "Zero-point energy",
        "Hartree",
        frozenset({"zero_point_energy"}),
        frozenset({"opt_freq"}),
        True,
        requires_matching_geometry=True,
    ),
)


def quantum_family_rows(
    left: QuantumChemistryRun, right: QuantumChemistryRun
) -> list[NamedCompareRow]:
    """Family rows with one finite number each side. Delta is right minus left."""
    rows: list[NamedCompareRow] = []
    for quantity in QUANTUM_FAMILY_QUANTITIES:
        if not _family_eligible(left, right, quantity):
            continue
        left_value = _extract_family_value(left, quantity)
        right_value = _extract_family_value(right, quantity)
        if left_value is None or right_value is None:
            continue
        rows.append(
            NamedCompareRow(
                label=quantity.label,
                left=_display(left_value),
                right=_display(right_value),
                delta=right_value - left_value,
            )
        )
    return rows


def _family_eligible(
    left: QuantumChemistryRun, right: QuantumChemistryRun, quantity: QuantumFamilyQuantity
) -> bool:
    if left.calc_type not in quantity.calc_types or right.calc_type not in quantity.calc_types:
        return False
    if left.molecule_uuid != right.molecule_uuid:
        return False
    if left.charge != right.charge or left.multiplicity != right.multiplicity:
        return False
    if left.solvent != right.solvent:
        return False
    if quantity.requires_matching_model and left.method_basis != right.method_basis:
        return False
    if quantity.requires_matching_geometry and left.input_fingerprint != right.input_fingerprint:
        return False
    if quantity.requires_matching_structure:
        left_identity = submitted_structure_identity(left.input_molblock)
        right_identity = submitted_structure_identity(right.input_molblock)
        if not left_identity or left_identity != right_identity:
            return False
    if quantity.required_run_charge is not None:
        if left.charge != quantity.required_run_charge or right.charge != quantity.required_run_charge:
            return False
    return True


def _extract_family_value(
    run: QuantumChemistryRun, quantity: QuantumFamilyQuantity
) -> float | None:
    descriptors = run.results.get("descriptors") or []
    if not isinstance(descriptors, list):
        return None
    matches: list[DescriptorValue] = []
    for item in descriptors:
        if not isinstance(item, DescriptorValue):
            continue
        if item.provider != run.provider:
            continue
        expected = {f"{run.provider}.{suffix}" for suffix in quantity.descriptor_suffixes}
        if item.descriptor_id not in expected:
            continue
        if not _descriptor_parameters_match(item, quantity.required_descriptor_parameters):
            continue
        matches.append(item)
    if len(matches) != 1:
        return None
    item = matches[0]
    number = _finite_number(item.value)
    if number is None or item.units != quantity.units:
        return None
    return number


def _parameter_equals(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    return actual == expected


def _descriptor_parameters_match(
    item: DescriptorValue, required: tuple[tuple[str, Any], ...]
) -> bool:
    if not required:
        return True
    if item.provenance is None:
        return False
    parameters = item.provenance.parameters or {}
    for key, expected in required:
        if key not in parameters or not _parameter_equals(parameters[key], expected):
            return False
    return True


def _report_parameters_match(result: Any, required: tuple[tuple[str, Any], ...]) -> bool:
    if not required:
        return True
    provenance = getattr(result, "provenance", None)
    if provenance is None:
        return False
    parameters = provenance.parameters or {}
    for key, expected in required:
        if key not in parameters or not _parameter_equals(parameters[key], expected):
            return False
    return True


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
