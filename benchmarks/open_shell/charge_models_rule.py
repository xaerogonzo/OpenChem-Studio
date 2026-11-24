"""PREREGISTRATION: partial-charge models on radicals (OS4, the item left over in docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md, section 3.4).

Written and committed BEFORE any ORCA number for this question was seen. The runner is `charge_models.py`; this module is the pure part, so a test can hold the rule.

QUESTION. The EEM, QEq and Gasteiger charges have no spin term. Does a radical's charge from each model degrade, relative to the same model on the closed-shell parent, by more than 0.05 e on any
heavy atom, against an independent computational reference? (The reference is ORCA's own atomic-charge partition; it is NOT an oracle for atomic charges, which are not observables.)

MODELS, and how each is reached (none is substituted for another):
  gasteiger                      RDKit `ComputeGasteigerCharges`, RAW values (the application's `_gasteiger` turns a NaN into 0.0, which would read as a perfect charge)
  eem_bultinck2002_part1         `charge_evaluation.evaluate_charges`
  qeq_rg1991_lambda_half_h_experimental   `charge_evaluation.evaluate_charges`
  eem_ionescu2013_e_mpa_631gs_gas, eem_ionescu2013_e_mpa_631gss_gas   `geometry_charges.compute_geometry_charges`
  NEEMP 2016 and Jiroušková 2009: already refuse an unpaired electron (`REFUSE_UNPAIRED_ELECTRON`); not measured, regression-tested, and NOT counted as a pass.

METRIC. For a pair (radical R, parent P), a reference scheme s and every mapped heavy atom i of R (its partner j in P):
    e_R,i = |q_model(R, i) - q_ref(R, i)|     e_P,j = |q_model(P, j) - q_ref(P, j)|     Delta_i = e_R,i - e_P,j
    E(model) = max over all pairs and mapped atoms of Delta_i.
Hydrogens are printed, never part of E (their correspondence between a radical and its parent is ambiguous). A negative Delta means the model did better on the radical than on its parent; it says nothing
about the absolute accuracy of the radical's charges, so a model that is wrong on both can pass this test, and a pass is worded accordingly.

VERDICT. E <= 0.05 e is PASS (the boundary is inclusive); E > 0.05 e is FAIL; a missing, non-finite, refused, unmatched or unvalidated number anywhere in a model's rows is INCONCLUSIVE, never a pass.

REFERENCE. Primary: ORCA Hirshfeld (B3LYP/def2-SVP, `IntAcc 6.0`, UKS for a radical and RKS for its parent, the application's own geometry). Loewdin is a sensitivity row reported beside it and cannot change
the verdict; CHELPG is not used. The species without a defensible closed-shell parent (O2, NO, an O atom, superoxide, NH, triplet CH2) are DESCRIPTIVE rows outside E.

PASS WORDING. "no radical-specific degradation beyond 0.05 e on this panel". Never "validated on radicals".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: The excess error, in electrons, above which a model FAILS. Inclusive at the boundary: exactly 0.05 passes.
THRESHOLD_E = 0.05
#: The scheme that decides; the other is a sensitivity row only.
PRIMARY_SCHEME = "hirshfeld"
SENSITIVITY_SCHEME = "loewdin"

PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"

#: The models measured, by their stable codes (those of `charge_evaluation` and `geometry_charges`).
MEASURED_MODELS = (
    "gasteiger",
    "eem_bultinck2002_part1",
    "qeq_rg1991_lambda_half_h_experimental",
    "eem_ionescu2013_e_mpa_631gs_gas",
    "eem_ionescu2013_e_mpa_631gss_gas",
)


@dataclass(frozen=True)
class Pair:
    """A radical, its closed-shell parent and which heavy atom of the parent each heavy atom of the radical is compared with."""

    name: str
    radical: str
    parent: str
    #: The radical's multiplicity (the parent is a singlet).
    multiplicity: int
    #: (radical heavy-atom index, parent heavy-atom index) in the order each SMILES is written, which is the order RDKit numbers the heavy atoms.
    atom_map: tuple[tuple[int, int], ...]


#: The fixed pairs. Maps are identity where the heavy skeleton is the same; every radical centre is mapped to the atom that carries the hydrogen it lost or the lone pair it shares.
PAIRS = (
    Pair("methyl", "[CH3]", "C", 2, ((0, 0),)),
    Pair("hydroxyl", "[OH]", "O", 2, ((0, 0),)),
    Pair("amino", "[NH2]", "N", 2, ((0, 0),)),
    Pair("ethyl", "C[CH2]", "CC", 2, ((0, 0), (1, 1))),
    Pair("methoxy", "C[O]", "CO", 2, ((0, 0), (1, 1))),
    Pair("hydroperoxyl", "O[O]", "OO", 2, ((0, 0), (1, 1))),
    Pair("tert-butyl", "C[C](C)C", "CC(C)C", 2, ((0, 0), (1, 1), (2, 2), (3, 3))),
    Pair("benzyl", "[CH2]c1ccccc1", "Cc1ccccc1", 2, tuple((i, i) for i in range(7))),
    Pair("TEMPO", "CC1(C)CCCC(C)(C)N1[O]", "CC1(C)CCCC(C)(C)N1O", 2, tuple((i, i) for i in range(11))),
)


@dataclass(frozen=True)
class Descriptive:
    """A species with no defensible closed-shell parent: measured and printed, outside E."""

    name: str
    smiles: str
    charge: int
    multiplicity: int


DESCRIPTIVE = (
    Descriptive("O2 (triplet, [O][O])", "[O][O]", 0, 3),
    Descriptive("O2 (drawn O=O, triplet)", "O=O", 0, 3),
    Descriptive("NO", "[N]=O", 0, 2),
    Descriptive("O atom (triplet)", "[O]", 0, 3),
    Descriptive("superoxide", "[O][O-]", -1, 2),
    Descriptive("NH (triplet)", "[NH]", 0, 3),
    Descriptive("CH2 (triplet)", "[CH2]", 0, 3),
)


def validate_map(pair: Pair, radical_heavy: int, parent_heavy: int) -> None:
    """Refuse a pair whose map is missing, out of range or ambiguous (one parent atom compared with two radical atoms, or a radical atom with two partners)."""
    sources = [r for r, _ in pair.atom_map]
    targets = [p for _, p in pair.atom_map]
    if not pair.atom_map:
        raise ValueError(f"{pair.name}: no atom map")
    if len(set(sources)) != len(sources):
        raise ValueError(f"{pair.name}: a radical atom has two partners")
    if len(set(targets)) != len(targets):
        raise ValueError(f"{pair.name}: a parent atom is compared with two radical atoms")
    if any(not 0 <= r < radical_heavy for r in sources) or any(not 0 <= p < parent_heavy for p in targets):
        raise ValueError(f"{pair.name}: an index lies outside the heavy atoms ({radical_heavy} radical, {parent_heavy} parent)")
    if set(sources) != set(range(radical_heavy)):
        raise ValueError(f"{pair.name}: every heavy atom of the radical must be mapped")


@dataclass(frozen=True)
class AtomRow:
    """One mapped heavy atom: the two absolute errors and their difference. Any of the four inputs may be None (missing)."""

    radical_atom: int
    parent_atom: int
    error_radical: float | None
    error_parent: float | None

    @property
    def excess(self) -> float | None:
        if self.error_radical is None or self.error_parent is None:
            return None
        return self.error_radical - self.error_parent


def _error(model: float | None, reference: float | None) -> float | None:
    if model is None or reference is None or not math.isfinite(model) or not math.isfinite(reference):
        return None
    return abs(model - reference)


def atom_rows(pair: Pair, model_radical, reference_radical, model_parent, reference_parent) -> list[AtomRow]:
    """The rows of one pair; each charge argument is a mapping from heavy-atom index to charge (a missing key or a None is missing data)."""
    return [
        AtomRow(r, p, _error(model_radical.get(r), reference_radical.get(r)), _error(model_parent.get(p), reference_parent.get(p)))
        for r, p in pair.atom_map
    ]


def verdict(rows: list[AtomRow]) -> tuple[str, float | None]:
    """(PASS | FAIL | INCONCLUSIVE, E). INCONCLUSIVE when there are no rows or any row lacks a number; otherwise E = the largest excess, compared inclusively with `THRESHOLD_E`."""
    if not rows or any(row.excess is None for row in rows):
        return INCONCLUSIVE, None
    worst = max(row.excess for row in rows)  # type: ignore[type-var]
    # Rounded to 1e-9 so that a difference which is 0.05 on paper (0.75 - 0.70 is 0.050000000000000044 in binary) is on the boundary and passes, as the rule says.
    return (PASS if round(worst, 9) <= THRESHOLD_E else FAIL), worst
