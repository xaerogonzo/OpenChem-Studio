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
    #: Free text for anything the source says that the fields above cannot (a normalisation, a polymorph).
    note: str = field(default="")

    def __post_init__(self) -> None:
        if self.partition not in PARTITIONS:
            raise ValueError(f"{self.row_id}: partition {self.partition!r} is not one of {sorted(PARTITIONS)}")
        if self.phase is not None and self.phase not in PHASES:
            raise ValueError(f"{self.row_id}: phase {self.phase!r} is not one of {sorted(PHASES)}")


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
