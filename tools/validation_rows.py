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
"""

from __future__ import annotations

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
TRANSITION_TYPES = frozenset({"melting", "decomposition", "melting_with_decomposition", "not_observed"})

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


def admit_to_melting_point_set(row: ValidationRow) -> str | None:
    """None when `row` may be scored as a melting point, else the reason it may not.

    A row typed `"decomposition"` is a different physical quantity and must never enter a Tm accuracy
    table just because it is in the same units; `"melting_with_decomposition"` and `"not_observed"` are
    also excluded -- the first because the reported number is entangled with decomposition (the value
    exists, but scoring a predictor against it overstates what was actually measured), the second because
    there is no melting value to score against at all. Only `"melting"` is a clean comparison.
    """
    if row.transition_type is None:
        return "no transition_type recorded: cannot tell a melting point from a decomposition temperature"
    if row.transition_type != "melting":
        return f"transition_type is {row.transition_type!r}, not a clean 'melting' value"
    return None


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
