"""The preregistered validation of the tautomer-distribution model: its criteria, and the comparison.

**WHAT THIS DECIDES.** `chem.tautomer_distribution` can show a population
percentage only for a model that has passed a validation gate; until now every
result shipped `unvalidated`. This module holds the two halves of that gate that
need no quantum chemistry: the CRITERIA, frozen as data
(`data/tautomer_validation.json`) before any number was computed, and the
COMPARISON of computed energies against them, as pure functions. The ORCA half
is `tools/tautomer_validation.py`, which drives the application's own path.

**THE CRITERIA ARE A CLOSED SCHEMA.** An unknown key is refused, not ignored, so
a commit that is meant to contain no result cannot carry one under another name.
`assert_no_computed` says the same thing a second way, by name.

**TAUTOMER LEVEL, NOT STEREO LEVEL.** A reference value belongs to a
constitutional tautomer. The application's energy for it is its lowest
successful stereoisomer (`TautomerState`), and a reference tautomer is matched by
the canonical NON-isomeric SMILES of its structure, never by display or atom
order. An unmatched reference tautomer is an error, never a nearest match.

**RENAMED REFERENCES.** Rotamers and E/Z isomers are not tautomers: a source's
`2a`/`2b` hydroxyl rotamers are ONE application tautomer. Its reference value
is the LOWEST of its variants (`representative_rule`), recorded beside the
variants, because the application can land on either and the lower is the
better statement of the tautomer.

**REBASELINED TO THE REFERENCE'S OWN ZERO.** The application's global minimum
may be a tautomer the reference never lists, so both vectors are rebaselined to
their own lowest REFERENCE-LISTED tautomer before an error is taken, never to
`relative_energy_kcal_mol`.
"""

from __future__ import annotations

#: Entered by the validation runner and the suite only, until the gate wiring
#: (the later commit of this phase) reads a validation record from the service.
REACHED_BY = (
    "tooling: consumed by tools/tautomer_validation.py and tests/test_tautomer_validation.py, "
    "never by the running application until the validation gate is wired in"
)

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from rdkit import Chem

from openchem.chem.tautomer_distribution import (
    HARTREE_TO_KCAL_PER_MOL,
    CandidateStatus,
    TautomerDistributionOutcome,
    TautomerState,
)

#: The frozen criteria and reference values.
SPEC_PATH = Path(__file__).parent / "data" / "tautomer_validation.json"

#: Largest disagreement between a reference value and the energy difference of
#: the source's own printed absolute energies. Values are printed to two
#: decimals, so half a unit in the last place plus rounding of the inputs.
DERIVED_VALUE_TOLERANCE_KCAL = 0.006

#: A system whose reference the gate decides on, alone and without compensation.
ROLE_REQUIRED = "required"
#: A system that is run and reported but never decides the gate.
ROLE_OPTIONAL = "optional"
#: A reference tautomer's value is the LOWEST of its source variants (rotamers, E/Z forms).
REPRESENTATIVE_RULE_LOWEST = "lowest_reference_variant"
#: The source printed the relative energy; there are no absolute energies to check it against.
DERIVATION_REPORTED = "reported_relative"
#: The value was computed from the source's own printed absolute energies, which are kept.
DERIVATION_ABSOLUTES = "derived_from_absolutes"


class ValidationSpecError(ValueError):
    """The criteria file is malformed, inconsistent or inadmissible."""


class MappingError(ValueError):
    """A reference tautomer matched no tautomer the application enumerated."""


class ExecutionStatus(str, Enum):
    """Whether the experiment ran to completion -- a different question from
    whether the model passed it."""

    COMPLETE = "complete"
    #: ORCA failed on a candidate, a reference tautomer was not enumerated or was
    #: only partly searched: nothing can be concluded either way.
    INCOMPLETE = "incomplete"


class GateOutcome(str, Enum):
    """What a COMPLETE run decided. `attempted_failed` is a positive record of a
    run that missed the gate, distinct from never having tried."""

    PASSED = "passed"
    #: Every required ordering was right but a quantitative tolerance was missed.
    RANKING_ONLY = "ranking_only"
    ATTEMPTED_FAILED = "attempted_failed"
    NOT_EVALUABLE = "not_evaluable"


# --- the criteria as data ------------------------------------------------------


@dataclass(frozen=True)
class ReferenceVariant:
    label: str
    reference_kcal: float
    locator: str


@dataclass(frozen=True)
class ReferenceTautomer:
    id: str
    name: str
    smiles: str
    reference_kcal: float
    representative_rule: str
    variants: tuple[ReferenceVariant, ...]
    absolute_hartree: float | None = None


@dataclass(frozen=True)
class ReferenceSystem:
    id: str
    role: str
    name: str
    input_smiles: str
    source: Mapping[str, str]
    reference: Mapping[str, Any]
    tautomers: tuple[ReferenceTautomer, ...]
    notes: str

    @property
    def required(self) -> bool:
        return self.role == ROLE_REQUIRED


@dataclass(frozen=True)
class Gates:
    reference_tie_kcal: float
    mae_tolerance_kcal: float
    max_error_tolerance_kcal: float


@dataclass(frozen=True)
class ValidationSpec:
    criteria_version: str
    model_under_test: Mapping[str, Any]
    quantity: Mapping[str, Any]
    gates: Gates
    systems: tuple[ReferenceSystem, ...]
    raw: Mapping[str, Any]

    @property
    def criteria_hash(self) -> str:
        """Everything that decides pass or fail EXCEPT the reference values: the
        declared model, the quantity, the gate rules and the tolerances."""
        raw = self.raw
        return _digest(
            {
                "schema_version": raw["schema_version"],
                "validation_criteria_version": raw["validation_criteria_version"],
                "model_under_test": raw["model_under_test"],
                "quantity": raw["quantity"],
                "gates": raw["gates"],
            }
        )

    @property
    def benchmark_set_hash(self) -> str:
        """WHICH systems and tautomers, and whether each is required, without
        their values: the same set with one number corrected keeps this hash and
        changes `reference_bundle_hash`."""
        return _digest(
            [
                [s.id, s.role, s.input_smiles, [[t.id, t.smiles] for t in s.tautomers]]
                for s in self.systems
            ]
        )

    @property
    def reference_bundle_hash(self) -> str:
        """The exact extracted reference values, sources and variants: correcting
        one transcription error visibly yields a new bundle."""
        return _digest(self.raw["systems"])

    def system(self, system_id: str) -> ReferenceSystem:
        for system in self.systems:
            if system.id == system_id:
                return system
        raise KeyError(system_id)

    @property
    def required_systems(self) -> tuple[ReferenceSystem, ...]:
        return tuple(s for s in self.systems if s.required)


def _digest(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Keys that would carry a RESULT. A preregistration holds none; the closed schema
#: below is the real defence and this is the same rule by name, so a refusal can
#: say which.
_RESULT_KEY = re.compile(
    r"^(computed|measured|observed|calculated|actual|result|outcome|passed|gate_outcome)"
    r"|(_outcome|_computed|_measured)$",
    re.IGNORECASE,
)


def assert_no_computed(node: Any, where: str = "$") -> None:
    """Raises if any key, at any depth, is named like a result."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if _RESULT_KEY.search(str(key)):
                raise ValidationSpecError(f"{where}.{key}: a preregistration holds no computed or outcome keys")
            assert_no_computed(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            assert_no_computed(value, f"{where}[{index}]")


def _closed(obj: Any, required: set[str], optional: set[str], where: str) -> None:
    if not isinstance(obj, Mapping):
        raise ValidationSpecError(f"{where}: expected an object")
    keys = set(obj)
    if missing := required - keys:
        raise ValidationSpecError(f"{where}: missing {sorted(missing)}")
    if unknown := keys - required - optional:
        raise ValidationSpecError(f"{where}: unknown key(s) {sorted(unknown)} (the schema is closed)")


def _number(value: Any, where: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationSpecError(f"{where}: expected a finite number, got {value!r}")
    if positive and value <= 0:
        raise ValidationSpecError(f"{where}: must be positive, got {value!r}")
    return float(value)


#: The flags that say WHICH physical quantity an energy is; a reference row must carry exactly the
#: values the model declares, or it cannot gate.
_QUANTITY_KEYS = {
    "phase", "energy_kind", "geometry", "vertical", "zpe_included", "thermal_included",
    "solvent", "experimental", "charge", "multiplicity",
}


def canonical_key(structure: str | Chem.Mol) -> str:
    """The canonical NON-isomeric SMILES of a constitution: hydrogens made
    implicit, stereochemistry dropped. This is how a reference tautomer is
    matched to an enumerated one. RDKit's canonical form can change between
    releases, so both sides are always computed here and the stored SMILES is
    only an input, never a key."""
    mol = Chem.MolFromSmiles(structure) if isinstance(structure, str) else Chem.Mol(structure)
    if mol is None:
        raise ValidationSpecError(f"not a structure: {structure!r}")
    mol = Chem.RemoveHs(mol)
    Chem.RemoveStereochemistry(mol)
    return Chem.MolToSmiles(mol, isomericSmiles=False)


def protocol_mismatches(system_protocol: Mapping[str, Any], declared: Mapping[str, Any]) -> list[str]:
    """What differs between what a reference row measured and the quantity the
    model computes. A row measured with a solvent, with zero-point or thermal
    terms, vertically, or as an experimental equilibrium is a different physical
    quantity and may not gate the model, however good the number is."""
    return [
        f"{key}: reference {system_protocol.get(key)!r}, model {declared.get(key)!r}"
        for key in sorted(_QUANTITY_KEYS)
        if system_protocol.get(key) != declared.get(key)
    ]


def parse_spec(raw: Mapping[str, Any]) -> ValidationSpec:
    """Validates `raw` and builds the typed spec; every inconsistency is an
    error naming where."""
    _closed(
        raw,
        {"schema_version", "validation_criteria_version", "preregistration", "model_under_test",
         "quantity", "gates", "tolerance_evidence", "systems", "corroboration_only"},
        {"_source_key", "_supplementary_source_keys"},
        "$",
    )
    assert_no_computed(raw)
    if raw["schema_version"] != 1:
        raise ValidationSpecError(f"unsupported schema_version {raw['schema_version']!r}")
    _closed(raw["preregistration"], {"frozen_before_first_run", "frozen_on", "note"}, set(), "$.preregistration")
    if raw["preregistration"]["frozen_before_first_run"] is not True:
        raise ValidationSpecError("$.preregistration.frozen_before_first_run must be true")
    _closed(
        raw["model_under_test"],
        {"method_basis", "provider", "calc_type", "orca_version", "charge", "multiplicity",
         "embedding_algorithm", "embedding_base_seed", "temperature_k", "dispersion", "convergence",
         "rationale"},
        set(),
        "$.model_under_test",
    )
    _closed(raw["quantity"], set(_QUANTITY_KEYS), set(), "$.quantity")
    _closed(
        raw["gates"],
        {"reference_tie_kcal", "mae_tolerance_kcal", "max_error_tolerance_kcal", "scope", "ranking_rule",
         "quantitative_rule", "tied_pairs_in_quantitative_gate", "pooled_mae"},
        set(),
        "$.gates",
    )
    gates = Gates(
        reference_tie_kcal=_number(raw["gates"]["reference_tie_kcal"], "$.gates.reference_tie_kcal", positive=True),
        mae_tolerance_kcal=_number(raw["gates"]["mae_tolerance_kcal"], "$.gates.mae_tolerance_kcal", positive=True),
        max_error_tolerance_kcal=_number(
            raw["gates"]["max_error_tolerance_kcal"], "$.gates.max_error_tolerance_kcal", positive=True
        ),
    )
    if gates.max_error_tolerance_kcal < gates.mae_tolerance_kcal:
        raise ValidationSpecError("the maximum-error tolerance cannot be tighter than the MAE tolerance")
    if raw["gates"]["tied_pairs_in_quantitative_gate"] != "included":
        raise ValidationSpecError("tied pairs are included in the quantitative gate (decided before the run)")

    systems = tuple(_parse_system(s, raw["quantity"], index) for index, s in enumerate(raw["systems"]))
    ids = [s.id for s in systems]
    if len(set(ids)) != len(ids):
        raise ValidationSpecError(f"duplicate system ids: {ids}")
    if not any(s.required for s in systems):
        raise ValidationSpecError("no system is required: there is nothing to gate on")
    if not isinstance(raw["corroboration_only"], list) or not isinstance(raw["tolerance_evidence"], list):
        raise ValidationSpecError("corroboration_only and tolerance_evidence are lists")
    for index, entry in enumerate(raw["corroboration_only"]):
        _closed(entry, {"key", "file", "doi", "doi_status", "role", "why_not_a_row"}, set(),
                f"$.corroboration_only[{index}]")
    return ValidationSpec(
        criteria_version=raw["validation_criteria_version"],
        model_under_test=raw["model_under_test"],
        quantity=raw["quantity"],
        gates=gates,
        systems=systems,
        raw=raw,
    )


def _parse_system(node: Mapping[str, Any], declared_quantity: Mapping[str, Any], index: int) -> ReferenceSystem:
    where = f"$.systems[{index}]"
    _closed(node, {"id", "role", "name", "input_smiles", "source", "reference", "tautomers", "notes"}, set(), where)
    if node["role"] not in (ROLE_REQUIRED, ROLE_OPTIONAL):
        raise ValidationSpecError(f"{where}.role: {node['role']!r}")
    _closed(node["source"], {"key", "file", "doi", "locator"}, set(), f"{where}.source")
    _closed(node["reference"], {"method", "units", "zero", "derivation", "protocol", "uncertainty"}, set(),
            f"{where}.reference")
    _closed(node["reference"]["uncertainty"], {"value_kcal", "basis"}, set(), f"{where}.reference.uncertainty")
    _closed(node["reference"]["protocol"], set(_QUANTITY_KEYS), set(), f"{where}.reference.protocol")
    if node["reference"]["units"] != "kcal/mol":
        raise ValidationSpecError(f"{where}.reference.units must be kcal/mol")
    if node["reference"]["derivation"] not in (DERIVATION_REPORTED, DERIVATION_ABSOLUTES):
        raise ValidationSpecError(f"{where}.reference.derivation")
    if node["role"] == ROLE_REQUIRED and not (node["source"]["doi"] and node["source"]["locator"]):
        raise ValidationSpecError(f"{where}: a required row needs a verified source (DOI and table)")
    if mismatches := protocol_mismatches(node["reference"]["protocol"], declared_quantity):
        raise ValidationSpecError(f"{where}: the reference is not the quantity the model computes: {mismatches}")
    if Chem.MolFromSmiles(node["input_smiles"]) is None:
        raise ValidationSpecError(f"{where}.input_smiles does not parse")

    tautomers = tuple(_parse_tautomer(t, f"{where}.tautomers[{i}]") for i, t in enumerate(node["tautomers"]))
    if len(tautomers) < 2:
        raise ValidationSpecError(f"{where}: a system needs at least two tautomers")
    if len({t.id for t in tautomers}) != len(tautomers):
        raise ValidationSpecError(f"{where}: duplicate tautomer ids")
    keys = [canonical_key(t.smiles) for t in tautomers]
    if len(set(keys)) != len(keys):
        raise ValidationSpecError(f"{where}: two reference tautomers are the same constitution")
    if min(t.reference_kcal for t in tautomers) != 0.0:
        raise ValidationSpecError(f"{where}: the lowest reference value must be 0.0 (the source's own zero)")
    if node["reference"]["derivation"] == DERIVATION_ABSOLUTES:
        absolutes = [t.absolute_hartree for t in tautomers]
        if any(a is None for a in absolutes):
            raise ValidationSpecError(f"{where}: derived_from_absolutes needs every absolute energy")
        lowest = min(absolutes)  # type: ignore[type-var]
        for t in tautomers:
            derived = (t.absolute_hartree - lowest) * HARTREE_TO_KCAL_PER_MOL  # type: ignore[operator]
            if abs(derived - t.reference_kcal) > DERIVED_VALUE_TOLERANCE_KCAL:
                raise ValidationSpecError(
                    f"{where}: {t.id} reference {t.reference_kcal} does not match its own absolutes ({derived:.3f})"
                )
    elif any(t.absolute_hartree is not None for t in tautomers):
        raise ValidationSpecError(f"{where}: reported_relative rows carry no absolute energies")
    return ReferenceSystem(
        id=node["id"], role=node["role"], name=node["name"], input_smiles=node["input_smiles"],
        source=node["source"], reference=node["reference"], tautomers=tautomers, notes=node["notes"],
    )


def _parse_tautomer(node: Mapping[str, Any], where: str) -> ReferenceTautomer:
    _closed(node, {"id", "name", "smiles", "reference_kcal", "representative_rule", "variants"},
            {"absolute_hartree"}, where)
    if node["representative_rule"] != REPRESENTATIVE_RULE_LOWEST:
        raise ValidationSpecError(f"{where}.representative_rule")
    if Chem.MolFromSmiles(node["smiles"]) is None:
        raise ValidationSpecError(f"{where}.smiles does not parse")
    variants = []
    for i, variant in enumerate(node["variants"]):
        _closed(variant, {"label", "reference_kcal", "locator"}, set(), f"{where}.variants[{i}]")
        variants.append(ReferenceVariant(
            variant["label"], _number(variant["reference_kcal"], f"{where}.variants[{i}]"), variant["locator"]
        ))
    if not variants:
        raise ValidationSpecError(f"{where}: no variants")
    value = _number(node["reference_kcal"], f"{where}.reference_kcal")
    if value != min(v.reference_kcal for v in variants):
        raise ValidationSpecError(f"{where}: the reference value is not its lowest variant")
    absolute = node.get("absolute_hartree")
    return ReferenceTautomer(
        id=node["id"], name=node["name"], smiles=node["smiles"], reference_kcal=value,
        representative_rule=node["representative_rule"], variants=tuple(variants),
        absolute_hartree=None if absolute is None else _number(absolute, f"{where}.absolute_hartree"),
    )


def load_spec(path: Path = SPEC_PATH) -> ValidationSpec:
    return parse_spec(json.loads(path.read_text(encoding="utf-8")))


# --- matching a reference tautomer to what the application enumerated --------------


def map_reference_tautomers(
    system: ReferenceSystem, key_by_tautomer: Mapping[str, str]
) -> dict[str, tuple[str, ...]]:
    """Reference tautomer id -> the application's tautomer keys that ARE that
    constitution. `key_by_tautomer` maps each enumerated tautomer's fingerprint to
    its `canonical_key`. Several enumerated tautomers can share one constitution
    (they differ only in how a bond's stereo was marked), and are then one
    reference tautomer. A reference tautomer nothing matches is an error: no
    nearest match, no silent skip."""
    by_constitution: dict[str, list[str]] = {}
    for fingerprint, key in key_by_tautomer.items():
        by_constitution.setdefault(key, []).append(fingerprint)
    mapping: dict[str, tuple[str, ...]] = {}
    for tautomer in system.tautomers:
        found = by_constitution.get(canonical_key(tautomer.smiles))
        if not found:
            raise MappingError(
                f"{system.id}: reference tautomer {tautomer.id!r} ({tautomer.smiles}) is not among the "
                f"{len(key_by_tautomer)} tautomers enumerated from {system.input_smiles!r}"
            )
        mapping[tautomer.id] = tuple(sorted(found))
    return mapping


def unreferenced_tautomers(system: ReferenceSystem, key_by_tautomer: Mapping[str, str]) -> list[str]:
    """Enumerated tautomers the reference does not list, as their canonical keys.
    Reported, never an error: it can mean the reference set is incomplete, not
    that the application is wrong."""
    listed = {canonical_key(t.smiles) for t in system.tautomers}
    return sorted({key for key in key_by_tautomer.values() if key not in listed})


@dataclass(frozen=True)
class TautomerEnergy:
    """One reference tautomer's energy under the application's own rule."""

    reference_id: str
    absolute_hartree: float | None
    representative_fingerprint: str
    #: Every enumerated tautomer behind it was searched completely.
    complete: bool


def reference_tautomer_energies(
    mapping: Mapping[str, tuple[str, ...]], outcome: TautomerDistributionOutcome
) -> dict[str, TautomerEnergy]:
    """Each reference tautomer's energy: the lowest SUCCESSFUL stereo job over
    every enumerated tautomer that is that constitution, and `complete` only when
    each of those tautomers is `TautomerState.COMPLETE`. A failed job makes it
    incomplete, so the run is not evaluable rather than quietly using a survivor."""
    energies: dict[str, TautomerEnergy] = {}
    for reference_id, tautomer_keys in mapping.items():
        members = [c for c in outcome.candidates if c.tautomer_key in tautomer_keys]
        succeeded = [c for c in members if c.status is CandidateStatus.SUCCEEDED]
        complete = bool(members) and all(
            outcome.tautomer_states.get(key) is TautomerState.COMPLETE for key in tautomer_keys
        )
        if not succeeded:
            energies[reference_id] = TautomerEnergy(reference_id, None, "", False)
            continue
        best = min(succeeded, key=lambda c: (c.absolute_energy_hartree, c.fingerprint))
        energies[reference_id] = TautomerEnergy(reference_id, best.absolute_energy_hartree, best.fingerprint, complete)
    return energies


# --- the comparison -----------------------------------------------------------------


def rebaseline(values: Mapping[str, float]) -> dict[str, float]:
    """Every value relative to the lowest of THESE values."""
    lowest = min(values.values())
    return {key: value - lowest for key, value in values.items()}


def computed_kcal(absolute_hartree: Mapping[str, float]) -> dict[str, float]:
    """Absolute electronic energies (Hartree) of the reference-listed tautomers as
    relative energies in kcal/mol, rebaselined to the lowest COMPUTED one among
    them -- never to the application's global minimum."""
    lowest = min(absolute_hartree.values())
    return {key: (value - lowest) * HARTREE_TO_KCAL_PER_MOL for key, value in absolute_hartree.items()}


@dataclass(frozen=True)
class PairCheck:
    a: str
    b: str
    reference_gap_kcal: float
    computed_gap_kcal: float
    #: The reference does not separate the pair, so no ordering is demanded.
    tied: bool
    ok: bool


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def ranking_checks(
    reference_kcal: Mapping[str, float], computed: Mapping[str, float], tie_kcal: float
) -> list[PairCheck]:
    """Every pair of reference-listed tautomers, tie-aware. A pair the reference
    separates by at least `tie_kcal` must be ordered the same way by the computed
    energies (a computed gap of exactly zero orders nothing, so it fails); a
    closer pair is unordered. The reference is a SET of pairwise constraints and
    is never forced into one total order, so A~B, B~C, A<C is legal."""
    checks = []
    ids = sorted(reference_kcal)
    for index, a in enumerate(ids):
        for b in ids[index + 1:]:
            reference_gap = reference_kcal[a] - reference_kcal[b]
            computed_gap = computed[a] - computed[b]
            tied = abs(reference_gap) < tie_kcal
            ok = tied or _sign(computed_gap) == _sign(reference_gap)
            checks.append(PairCheck(a, b, reference_gap, computed_gap, tied, ok))
    return checks


@dataclass(frozen=True)
class SystemEvaluation:
    system_id: str
    role: str
    pair_checks: tuple[PairCheck, ...]
    #: reference id -> (reference kcal, computed kcal, absolute error)
    errors: Mapping[str, tuple[float, float, float]]
    mae_kcal: float
    max_error_kcal: float
    ranking_ok: bool
    quantitative_ok: bool

    @property
    def passed(self) -> bool:
        return self.ranking_ok and self.quantitative_ok


def evaluate_system(
    system: ReferenceSystem, absolute_hartree: Mapping[str, float], gates: Gates
) -> SystemEvaluation:
    """One error per reference-listed tautomer (NOT all pairs: an n-state system
    would otherwise weigh n(n-1)/2 correlated errors against one for a binary
    pair), both vectors rebaselined to their own lowest."""
    ids = [t.id for t in system.tautomers]
    if set(absolute_hartree) != set(ids):
        raise ValueError(f"{system.id}: computed energies for {sorted(absolute_hartree)}, reference lists {sorted(ids)}")
    reference = rebaseline({t.id: t.reference_kcal for t in system.tautomers})
    computed = computed_kcal(absolute_hartree)
    errors = {i: (reference[i], computed[i], abs(computed[i] - reference[i])) for i in sorted(ids)}
    magnitudes = [e[2] for e in errors.values()]
    mae = sum(magnitudes) / len(magnitudes)
    worst = max(magnitudes)
    checks = tuple(ranking_checks(reference, computed, gates.reference_tie_kcal))
    return SystemEvaluation(
        system_id=system.id,
        role=system.role,
        pair_checks=checks,
        errors=errors,
        mae_kcal=mae,
        max_error_kcal=worst,
        ranking_ok=all(c.ok for c in checks),
        quantitative_ok=mae <= gates.mae_tolerance_kcal and worst <= gates.max_error_tolerance_kcal,
    )


@dataclass(frozen=True)
class GateEvaluation:
    execution: ExecutionStatus
    outcome: GateOutcome
    systems: tuple[SystemEvaluation, ...]
    #: Mean over every error of every REQUIRED system. Reported, never the criterion.
    pooled_mae_kcal: float | None


def evaluate_gate(
    spec: ValidationSpec,
    absolute_hartree_by_system: Mapping[str, Mapping[str, float]],
    execution_complete: bool,
) -> GateEvaluation:
    """The gate. Every REQUIRED system must pass on its own, with no
    compensation between systems, and optional systems are evaluated and reported
    but never decide it. An incomplete execution, or a required system with no
    energies, is `not_evaluable`: the experiment did not happen, which is neither
    a pass nor a failed attempt."""
    evaluations = tuple(
        evaluate_system(system, absolute_hartree_by_system[system.id], spec.gates)
        for system in spec.systems
        if system.id in absolute_hartree_by_system
    )
    have = {e.system_id for e in evaluations}
    covered = all(system.id in have for system in spec.required_systems)
    if not execution_complete or not covered:
        return GateEvaluation(ExecutionStatus.INCOMPLETE, GateOutcome.NOT_EVALUABLE, evaluations, None)
    required = [e for e in evaluations if e.role == ROLE_REQUIRED]
    pooled = [error[2] for e in required for error in e.errors.values()]
    if not all(e.ranking_ok for e in required):
        outcome = GateOutcome.ATTEMPTED_FAILED
    elif not all(e.quantitative_ok for e in required):
        outcome = GateOutcome.RANKING_ONLY
    else:
        outcome = GateOutcome.PASSED
    return GateEvaluation(ExecutionStatus.COMPLETE, outcome, evaluations, sum(pooled) / len(pooled))


def systems_summary(systems: Sequence[ReferenceSystem]) -> list[str]:
    """One line per system, for the runner's listing."""
    return [f"{s.id} [{s.role}] {len(s.tautomers)} tautomers, {s.source['key']}" for s in systems]


@dataclass(frozen=True)
class SystemRun:
    """What the runner measured for one system: the application's own jobs and
    the energies it formed from them. Holds numbers, so it exists only at run
    time and in the artifact, never in the preregistered criteria."""

    system_id: str
    #: Non-empty when a reference tautomer matched nothing (a loud failure).
    mapping_error: str
    energies: Mapping[str, TautomerEnergy]
    #: Enumerated constitutions the reference does not list.
    unreferenced: Sequence[str]
    #: One record per stereo job (fingerprint, stereo index, status, energy, input hash...).
    jobs: Sequence[Mapping[str, Any]]


def build_artifact(
    spec: ValidationSpec,
    runs: Sequence[SystemRun],
    *,
    model_version: str,
    model_policy: str,
    source_commit: str,
    orca_version: str,
    rdkit_version: str,
) -> dict[str, Any]:
    """The machine-readable artifact: every number the gate used, so the outcome
    can be re-audited without rerunning ORCA. `validation_execution_status` (did the
    experiment run to completion) and `validation_gate_outcome` (what it decided)
    are separate fields on purpose."""
    by_id = {run.system_id: run for run in runs}
    usable: dict[str, dict[str, float]] = {}
    systems_out = []
    for system in spec.systems:
        run = by_id.get(system.id)
        entry: dict[str, Any] = {"id": system.id, "role": system.role, "source": dict(system.source)}
        if run is None:
            entry["execution"] = "not_run"
            systems_out.append(entry)
            continue
        complete = (
            not run.mapping_error
            and all(
                run.energies.get(t.id) is not None
                and run.energies[t.id].complete
                and run.energies[t.id].absolute_hartree is not None
                for t in system.tautomers
            )
        )
        entry["execution"] = ExecutionStatus.COMPLETE.value if complete else ExecutionStatus.INCOMPLETE.value
        entry["mapping_error"] = run.mapping_error
        entry["unreferenced_tautomers"] = list(run.unreferenced)
        entry["jobs"] = [dict(job) for job in run.jobs]
        if complete:
            absolute = {t.id: run.energies[t.id].absolute_hartree for t in system.tautomers}
            usable[system.id] = absolute  # type: ignore[assignment]
            evaluation = evaluate_system(system, absolute, spec.gates)
            entry["ranking_ok"] = evaluation.ranking_ok
            entry["quantitative_ok"] = evaluation.quantitative_ok
            entry["mae_kcal"] = evaluation.mae_kcal
            entry["max_error_kcal"] = evaluation.max_error_kcal
            entry["pairs"] = [
                {"a": c.a, "b": c.b, "reference_gap_kcal": c.reference_gap_kcal,
                 "computed_gap_kcal": c.computed_gap_kcal, "tied": c.tied, "ok": c.ok}
                for c in evaluation.pair_checks
            ]
            entry["tautomers"] = [
                {"id": t.id, "reference_kcal": reference, "computed_kcal": calculated, "error_kcal": error,
                 "absolute_hartree": run.energies[t.id].absolute_hartree,
                 "representative_fingerprint": run.energies[t.id].representative_fingerprint,
                 "reference_source": system.source["key"], "reference_locator": system.source["locator"],
                 "reference_units": "kcal/mol", "reference_zero": system.reference["zero"]}
                for t in system.tautomers
                for reference, calculated, error in [evaluation.errors[t.id]]
            ]
        systems_out.append(entry)
    gate = evaluate_gate(
        spec,
        usable,
        execution_complete=all(
            by_id.get(s.id) is not None and s.id in usable for s in spec.required_systems
        ),
    )
    return {
        "artifact_schema": 1,
        "identity": {
            "model_version": model_version,
            "model_policy": model_policy,
            "validation_criteria_version": spec.criteria_version,
            "criteria_hash": spec.criteria_hash,
            "benchmark_set_hash": spec.benchmark_set_hash,
            "reference_bundle_hash": spec.reference_bundle_hash,
            "source_commit": source_commit,
            "orca_version": orca_version,
            "rdkit_version": rdkit_version,
            "method_basis": spec.model_under_test["method_basis"],
        },
        "validation_execution_status": gate.execution.value,
        "validation_gate_outcome": gate.outcome.value,
        "pooled_mae_kcal": gate.pooled_mae_kcal,
        "systems": systems_out,
    }

