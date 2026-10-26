"""Validation rows and the leakage rule, for the thermophysical / density / enthalpy survey.

A method is only validated on data it was not fitted on, and "was it fitted on this molecule" is a question
about CHEMICAL IDENTITY, not about how a SMILES string happens to be written. This module holds the two
small pieces the survey needs before any method is compared, and nothing about any method itself:

* `ValidationRow` -- one measured value with everything that makes it comparable: identity, property, value,
  units, source, record id, partition, and the **reference temperature and phase**.
* `exclude_leaked` -- drop the rows whose molecule is in the population a model was fitted on FOR THAT
  PROPERTY.

**THE RULES, EACH THE ANSWER TO A WAY THIS GOES WRONG**

* *Leakage is property- and model-specific.* A molecule can be in a model's boiling-point fit and not its
  heat-capacity fit; excluding it from every property, or from every model, throws away honest validation
  data. A population is therefore keyed by `(model, property)`, and a caller asking about a pair that has no
  recorded population gets an ERROR, not "no leakage": an unenumerated fit population is unknown, and unknown
  must never read as clean (the general Cp population in Burkhardt 2026 is exactly that -- see
  `docs/research/literature.toml`).
* *Identity is the first block of the InChIKey*, which is the connectivity and ignores stereo, isotopes and
  charge layers, so `C1=CC=CC=C1` and `c1ccccc1` are one molecule and two enantiomers are one entry. That is a
  deliberate choice with a cost: it also merges genuinely different stereoisomers, which errs toward excluding
  too much rather than leaking. Salts, hydrates and mixtures are keyed by their whole formula unit as given;
  splitting them into components is a decision for the caller, made before the row is built.
* *A row with no reference temperature or phase does not enter the common evaluation set.* A density measured
  at 200 K and one at 298 K are not the same quantity, and a gas-phase and a solid-phase enthalpy of formation
  differ by the sublimation enthalpy. `admit_to_common_set` says why a row cannot enter rather than guessing.
* *Development, selection and holdout are three distinct partitions.* Data used to choose a method is never
  the data that claims the method works.
* *A thermal event is not a property.* What the source observed (melting, boiling, sublimation,
  decomposition ...) and what a method is asked to predict (a melting point, a NORMAL boiling point) are
  separate fields, and `admit_to_target` says for every pair whether the row may be scored. A boiling point
  at reduced pressure is not a normal boiling point, and a sublimation temperature is not either.
* *Numeric rows stay numeric.* "There was no clean normal-boiling event" is a `NoEventRecord`, which has no
  `value` and cannot be passed to an admission function, so a placeholder temperature can never exist.
* *Unknown leakage is a STATUS, not an exception.* `exclude_leaked` still raises for an unrecorded
  population; `assess_leakage` carries the same fact as `"unknown"` so a report can say so, and
  `may_claim_independent_holdout` is False for it however good the numbers look.
* *The split key is deliberately conservative and is not an identity claim.* `split_group_key` is the first
  InChIKey block, so stereoisomers, isotopologues and charge variants of one skeleton always land in one
  partition. That removes some near-duplicates from independent evaluation; it does not prove two grouped
  records are the same chemical entity or the same physical form.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from rdkit import Chem

#: The partitions a row can belong to. **THREE, NEVER TWO**: what is used to develop a method, what is used to
#: choose between methods, and what is held out to state the result are different uses of data.
PARTITIONS = frozenset({"development", "selection", "holdout"})

#: The phases a reference state can name.
PHASES = frozenset({"gas", "liquid", "solid", "crystal"})

#: What a reported thermal event actually was. **A predicted melting point must never be scored against
#: a reported DECOMPOSITION temperature just because both are printed in the same units** -- an energetic
#: material's "204 C" can be either, and the two are different physical quantities (found while building
#: the RDX/HMX/TNT/PETN comparison: Agrawal 2010 Table 3.6 reports melting point, ignition temperature and
#: exotherm temperature as three SEPARATE columns for exactly this reason).
#:
#: The vocabulary is COMPLETE: every event a source can report for these properties has a value, and
#: `ADMISSION_POLICY` below has a decision for every (target, event) pair, so adding an event here without
#: deciding what it may be scored against fails a test. `"unknown"` is for an event that could not be
#: classified; it is admitted to NO score.
TRANSITION_TYPES = frozenset({
    "melting", "boiling", "sublimation", "decomposition", "melting_with_decomposition", "not_observed",
    "unknown",
})

#: What a method can be asked to predict and be scored on. Kept apart from `TRANSITION_TYPES`, which is what
#: the source SAW: a decomposition temperature is evidence about a substance, not a boiling point.
TARGET_PROPERTIES = frozenset({"melting_point", "normal_boiling_point", "decomposition_temperature"})

#: The event that is a clean observation of each target. Every other (target, event) pair is refused, and
#: the refusal says which event it was.
_CLEAN_EVENT = {
    "melting_point": "melting",
    "normal_boiling_point": "boiling",
    "decomposition_temperature": "decomposition",
}

#: Every (target, event) pair and whether it may be scored. Written out as a full product rather than left
#: implicit, so the table can be read and so a new event or target must be decided here
#: (`tests/test_validation_rows.py` compares its keys with the full product).
ADMISSION_POLICY = {
    (target, event): event == _CLEAN_EVENT[target]
    for target in sorted(TARGET_PROPERTIES)
    for event in sorted(TRANSITION_TYPES)
}

#: Normal pressure, 1 atm.
NORMAL_PRESSURE_PA = 101_325.0

#: How far a stated reference pressure may sit from normal pressure and still be called a normal boiling
#: point: +-1.5 kPa, about +-11 mmHg. A value measured at a nearby pressure is not mathematically a normal
#: boiling point; this is a DEFINED reference-compatibility rule, frozen in `benchmarks/mp_bp/
#: PREREGISTRATION.md`, and nothing wider is admitted without a preregistered conversion.
NORMAL_PRESSURE_TOLERANCE_PA = 1_500.0

#: How a row's pressure is known. `"stated"`: the source gives a numeric pressure
#: (`reference_pressure_pa`). `"table_convention_normal"`: the source prints none for this entry but states in
#: its own header that the column is at normal pressure. A row with neither is not a normal boiling point.
PRESSURE_BASES = frozenset({"stated", "table_convention_normal"})

#: Where each partition's share of the grouping-key hash space goes: percentages, summing to 100.
PARTITION_SHARES = (("development", 60), ("selection", 20), ("holdout", 20))

#: The ways leakage can stand for one (model, property). **`"unknown"` is not a kind of "clean".**
#: `"known_population_no_overlap"`: the fit population is recorded and no row is in it.
#: `"known_population_overlap_removed"`: it is recorded, some rows were in it and were removed.
#: `"no_overlap_by_evidence"`: no population list exists but evidence that none overlaps is recorded.
#: `"unknown"`: none of those.
LEAKAGE_STATUSES = frozenset({
    "known_population_no_overlap", "known_population_overlap_removed", "no_overlap_by_evidence", "unknown",
})

#: The events that can leave a target WITHOUT a numeric label. A `NoEventRecord` states which one it was.
NO_LABEL_EVENTS = frozenset({
    "not_observed", "decomposition", "sublimation", "melting_with_decomposition", "unknown",
})

#: How directly a row's value traces to a measurement. **A handbook table is not the experimental
#: source** -- it is a secondary citation of one, and the row should say which. `"primary"` for a value
#: read from the original measurement (or as close as this project has gotten); `"secondary"` for one
#: read from a compilation/handbook that itself cites something else (record that upstream citation in
#: `primary_reference` when it has been traced, even if not held -- as RDX's Agrawal-to-Yinon-and-Zitrin
#: chain was).
VALUE_SOURCES = frozenset({"primary", "secondary"})


class UnknownFitPopulation(KeyError):
    """No fit population is recorded for a (model, property) pair, so leakage there is UNKNOWN."""


@dataclass(frozen=True)
class ValidationRow:
    """One measured value, with what is needed to compare it with another."""

    row_id: str
    smiles: str
    property: str
    value: float
    units: str
    source_id: str
    record_id: str
    partition: str
    #: Kelvin, or None when the source does not say. **None keeps the row out of the common set.**
    temperature_k: float | None = None
    #: One of `PHASES`, or None when the source does not say.
    phase: str | None = None
    #: One of `TRANSITION_TYPES`, or None when the property isn't a thermal transition at all (leave
    #: unset for a non-thermal property; required whenever `property` is a melting/boiling/decomposition
    #: point, enforced below).
    transition_type: str | None = None
    #: One of `VALUE_SOURCES`, or None when not yet classified.
    value_source: str | None = None
    #: The furthest-back citation this value has been traced to, even when that source is not itself
    #: held (e.g. "Yinon & Zitrin 1981, p. 136" -- not held, but the chain is recorded rather than
    #: dropped). Free text; empty when the row's own `source_id` already names the primary source.
    primary_reference: str = field(default="")
    #: The handbook/compilation actually read to obtain `value`, when different from `primary_reference`
    #: (e.g. "Agrawal 2010, Table 3.6, p. 189"). Free text.
    secondary_reference: str = field(default="")
    #: Free text for anything the source says that the fields above cannot (a normalisation, a polymorph).
    note: str = field(default="")
    #: The reference pressure in pascals, normalised, or None. Not the ambient pressure of any calculation.
    reference_pressure_pa: float | None = None
    #: One of `PRESSURE_BASES`, or None when the pressure is not known.
    pressure_basis: str | None = None
    #: The pressure exactly as the source printed it (e.g. "760 mm"), for auditing the normalisation.
    reported_pressure: str = field(default="")
    #: The value and unit exactly as the source printed them, kept beside the normalised `value`/`units`.
    reported_value: str = field(default="")
    reported_unit: str = field(default="")
    #: A reported RANGE. Both or neither. When present the row is scored against the interval
    #: (`absolute_error`), never its midpoint, and `value` must lie inside it.
    range_low: float | None = None
    range_high: float | None = None
    #: How `value` was derived from what the source printed (e.g. "C to K"). Empty when it was not.
    normalisation_method: str = field(default="")
    #: Edition, table, page and entry of the source record, so the value can be checked and a conflict traced.
    locator: str = field(default="")
    #: The physical form the source describes when it says (polymorph, hydrate, salt); empty when it does not.
    physical_form: str = field(default="")

    def __post_init__(self) -> None:
        if self.partition not in PARTITIONS:
            raise ValueError(f"{self.row_id}: partition {self.partition!r} is not one of {sorted(PARTITIONS)}")
        if self.phase is not None and self.phase not in PHASES:
            raise ValueError(f"{self.row_id}: phase {self.phase!r} is not one of {sorted(PHASES)}")
        if self.transition_type is not None and self.transition_type not in TRANSITION_TYPES:
            raise ValueError(
                f"{self.row_id}: transition_type {self.transition_type!r} is not one of "
                f"{sorted(TRANSITION_TYPES)}"
            )
        if self.value_source is not None and self.value_source not in VALUE_SOURCES:
            raise ValueError(f"{self.row_id}: value_source {self.value_source!r} is not one of {sorted(VALUE_SOURCES)}")
        if self.pressure_basis is not None and self.pressure_basis not in PRESSURE_BASES:
            raise ValueError(
                f"{self.row_id}: pressure_basis {self.pressure_basis!r} is not one of {sorted(PRESSURE_BASES)}"
            )
        if self.reference_pressure_pa is not None and not self.reference_pressure_pa > 0:
            raise ValueError(f"{self.row_id}: reference_pressure_pa must be positive, got {self.reference_pressure_pa!r}")
        if self.pressure_basis == "stated" and self.reference_pressure_pa is None:
            raise ValueError(f"{self.row_id}: pressure_basis 'stated' needs a reference_pressure_pa")
        if (self.range_low is None) != (self.range_high is None):
            raise ValueError(f"{self.row_id}: a range needs both range_low and range_high, or neither")
        if self.range_low is not None:
            if not self.range_low <= self.range_high:
                raise ValueError(f"{self.row_id}: range_low {self.range_low} is above range_high {self.range_high}")
            if not self.range_low <= self.value <= self.range_high:
                raise ValueError(f"{self.row_id}: value {self.value} lies outside its own range")


@dataclass(frozen=True)
class NoEventRecord:
    """That a target has NO numeric label for this entity, and why.

    **Deliberately not a `ValidationRow` and with no `value`**: a compound that decomposes before it boils is
    evidence about the substance, not a boiling point, and a placeholder temperature (zero, a limit, the
    decomposition onset) would be scored as if it were one. Counting these records, not scoring them, is what
    keeps "this entity had no clean event" from being either a number or an unexplained deletion.
    """

    record_id: str
    smiles: str
    #: One of `TARGET_PROPERTIES`: the property that has no numeric label.
    target_property: str
    #: One of `NO_LABEL_EVENTS`: what the source reported instead.
    observed_event: str
    source_id: str
    #: Edition, table, page and entry.
    locator: str
    #: One sentence, in words: why this entity has no numeric label for the target.
    reason: str

    def __post_init__(self) -> None:
        if self.target_property not in TARGET_PROPERTIES:
            raise ValueError(
                f"{self.record_id}: target_property {self.target_property!r} is not one of {sorted(TARGET_PROPERTIES)}"
            )
        if self.observed_event not in NO_LABEL_EVENTS:
            raise ValueError(
                f"{self.record_id}: observed_event {self.observed_event!r} is not one of {sorted(NO_LABEL_EVENTS)}"
            )
        if not self.reason.strip():
            raise ValueError(f"{self.record_id}: a no-event record must say why")


def identity_block(smiles: str) -> str:
    """The normalised identity of a molecule: the first block of its InChIKey.

    Raises `ValueError` for a string RDKit cannot read, rather than returning a placeholder that two unreadable
    strings would share and so appear to be the same molecule.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"cannot read {smiles!r} as a structure")
    key = Chem.MolToInchiKey(mol)
    if not key:
        raise ValueError(f"no InChIKey could be made for {smiles!r}")
    return key.split("-", 1)[0]


def population_blocks(smiles_list) -> frozenset[str]:
    """The identity set of a fit population given as SMILES."""
    return frozenset(identity_block(s) for s in smiles_list)


def admit_to_common_set(row: ValidationRow) -> str | None:
    """None when the row may enter the common evaluation set, else the reason it may not."""
    if row.temperature_k is None:
        return "no reference temperature: it is not comparable with a value measured at another temperature"
    if row.phase is None:
        return "no reference phase: a gas-phase and a condensed-phase value are different quantities"
    return None


def admit_to_target(row: ValidationRow, target: str) -> str | None:
    """None when `row` may be scored against `target`, else the reason it may not.

    The ONE place a (target, event) decision is made; the per-property functions below add only the
    conditions that belong to that property. A `NoEventRecord` has no value to score and is refused with a
    `TypeError` rather than a reason, because passing one here is a programming error, not a data question.
    """
    if isinstance(row, NoEventRecord):
        raise TypeError("a NoEventRecord has no numeric value and cannot be admitted to a scoring set")
    if target not in TARGET_PROPERTIES:
        raise ValueError(f"target {target!r} is not one of {sorted(TARGET_PROPERTIES)}")
    if row.transition_type is None:
        return "no transition_type recorded: cannot tell a melting point from a decomposition temperature"
    if not ADMISSION_POLICY[(target, row.transition_type)]:
        return f"transition_type is {row.transition_type!r}, not a clean {_CLEAN_EVENT[target]!r} value"
    return None


def admit_to_melting_point_set(row: ValidationRow) -> str | None:
    """None when `row` may be scored as a melting point, else the reason it may not.

    A row typed `"decomposition"` is a different physical quantity and must never enter a Tm accuracy
    table just because it is in the same units; `"melting_with_decomposition"` and `"not_observed"` are
    also excluded -- the first because the reported number is entangled with decomposition (the value
    exists, but scoring a predictor against it overstates what was actually measured), the second because
    there is no melting value to score against at all. Only `"melting"` is a clean comparison.
    """
    return admit_to_target(row, "melting_point")


def admit_to_normal_boiling_point_set(row: ValidationRow) -> str | None:
    """None when `row` may be scored as a NORMAL boiling point, else the reason it may not.

    Two conditions, both required: the observed event is a clean boiling, and the reference pressure is
    normal. A pressure within `NORMAL_PRESSURE_TOLERANCE_PA` of one atmosphere passes; a printed pressure
    outside it is refused (a reduced-pressure value is not converted here); and a row with no pressure passes
    ONLY when its source states that the column is at normal pressure (`pressure_basis ==
    "table_convention_normal"`), never by assumption.
    """
    refusal = admit_to_target(row, "normal_boiling_point")
    if refusal is not None:
        return refusal
    if row.reference_pressure_pa is not None:
        gap = abs(row.reference_pressure_pa - NORMAL_PRESSURE_PA)
        if gap > NORMAL_PRESSURE_TOLERANCE_PA:
            return (
                f"reference pressure {row.reference_pressure_pa:g} Pa is {gap:g} Pa from normal pressure, "
                f"outside the +-{NORMAL_PRESSURE_TOLERANCE_PA:g} Pa this score allows"
            )
        return None
    if row.pressure_basis == "table_convention_normal":
        return None
    return (
        "no reference pressure, and the source is not recorded as stating that its column is at normal "
        "pressure: a boiling point without a pressure is not a normal boiling point"
    )


def absolute_error(row: ValidationRow, predicted: float) -> float:
    """|predicted - the row's reference|, with a reported RANGE scored as an interval.

    Inside the interval the error is 0; outside it is the distance to the NEARER bound. A range is never
    replaced by its midpoint, and `value` is not used when a range is present.
    """
    if row.range_low is not None:
        if row.range_low <= predicted <= row.range_high:
            return 0.0
        return min(abs(predicted - row.range_low), abs(predicted - row.range_high))
    return abs(predicted - row.value)


def exclude_leaked(
    rows: list[ValidationRow],
    model: str,
    populations: dict[tuple[str, str], frozenset[str]],
) -> tuple[list[ValidationRow], list[ValidationRow]]:
    """Split `rows` into (kept, excluded) for `model`: excluded are those whose identity is in the population
    the model was fitted on FOR THAT ROW'S PROPERTY.

    Raises `UnknownFitPopulation` for a (model, property) with no recorded population. Silence there would
    read as "no leakage", which is the one thing an unenumerated population cannot claim.
    """
    kept, excluded = [], []
    for row in rows:
        try:
            fitted = populations[(model, row.property)]
        except KeyError:
            raise UnknownFitPopulation(
                f"no fit population is recorded for model {model!r} and property {row.property!r}, so whether "
                f"{row.row_id} leaks is unknown"
            ) from None
        (excluded if identity_block(row.smiles) in fitted else kept).append(row)
    return kept, excluded


def split_group_key(smiles: str) -> str:
    """What decides which partition a molecule goes to: the conservative `identity_block`.

    Every observation of a molecule, and every stereoisomer, isotopologue and charge variant of its
    skeleton, shares this key and so always lands in ONE partition. It is a leakage-control choice, not
    a claim that grouped records are the same entity or the same physical form.
    """
    return identity_block(smiles)


def partition_for(key: str) -> str:
    """The partition a grouping key belongs to: a hash of the key, so it does not depend on row order or on
    which rows are present, mapped onto `PARTITION_SHARES`."""
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16) % 100
    edge = 0
    for name, share in PARTITION_SHARES:
        edge += share
        if bucket < edge:
            return name
    raise AssertionError("PARTITION_SHARES must sum to 100")  # pragma: no cover


def partition_manifest(smiles_list) -> dict[str, str]:
    """{grouping key: partition} for every molecule given. Many SMILES can share a key; they share a partition."""
    return {key: partition_for(key) for key in sorted({split_group_key(s) for s in smiles_list})}


def manifest_checksum(manifest: dict[str, str]) -> str:
    """A checksum of a manifest, so a frozen split can be shown to be the split that was used."""
    lines = "\n".join(f"{key}\t{manifest[key]}" for key in sorted(manifest))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LeakageAssessment:
    """Leakage for one (model, property), as a status a report can print.

    `kept` rows are cleared for an independent-holdout claim; `excluded` were in the fit population;
    `exploratory` rows are all there is when the status is `"unknown"`: they may be scored and reported,
    labelled as non-blind, and they clear nothing.
    """

    model: str
    property: str
    status: str
    kept: tuple = ()
    excluded: tuple = ()
    exploratory: tuple = ()
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.status not in LEAKAGE_STATUSES:
            raise ValueError(f"leakage status {self.status!r} is not one of {sorted(LEAKAGE_STATUSES)}")


def assess_leakage(
    rows: list[ValidationRow],
    model: str,
    populations: dict[tuple[str, str], frozenset[str]],
    no_overlap_evidence: dict[tuple[str, str], str] | None = None,
) -> LeakageAssessment:
    """Leakage for `model` over `rows`, which must all be one property. Never raises for an unrecorded
    population: that is the `"unknown"` status, in which NOTHING is cleared."""
    properties = {row.property for row in rows}
    if len(properties) > 1:
        raise ValueError(f"assess_leakage takes one property at a time, got {sorted(properties)}")
    prop = next(iter(properties), "")
    pair = (model, prop)
    if pair in populations:
        kept, excluded = exclude_leaked(rows, model, populations)
        status = "known_population_overlap_removed" if excluded else "known_population_no_overlap"
        return LeakageAssessment(model, prop, status, tuple(kept), tuple(excluded))
    evidence = (no_overlap_evidence or {}).get(pair, "").strip()
    if evidence:
        return LeakageAssessment(model, prop, "no_overlap_by_evidence", tuple(rows), evidence=evidence)
    return LeakageAssessment(model, prop, "unknown", exploratory=tuple(rows))


def may_claim_independent_holdout(assessment: LeakageAssessment) -> bool:
    """Whether results for this (model, property) may be reported as an independent held-out test.
    False for `"unknown"`, however small the errors."""
    return assessment.status != "unknown"
