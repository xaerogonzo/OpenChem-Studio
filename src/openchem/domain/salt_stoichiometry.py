"""Smallest charge-neutral integers for exactly two ions.

No chemistry toolkit. No lattice-energy import. Identity is opaque: the solver uses
charges only. Drawn multiplicities are a later layer's problem.

    n_C = |z-| / gcd(|z+|, |z-|)
    n_A = |z+| / gcd(|z+|, |z-|)
"""

from __future__ import annotations

#: Slice 1 has no window import; tests are the only consumers until a later
#: slice wires Mode B. Remove this when something reachable from
#: ``openchem.main`` imports the module.
REACHED_BY = (
    "tooling: consumed by tests/test_salt_stoichiometry.py and "
    "tests/test_salt_components.py; Mode B is not on the window yet"
)

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import gcd


@dataclass(frozen=True)
class ChargedSpecies:
    """One ion, as the stoichiometry layer is allowed to see it."""

    identity: str
    charge: int


@dataclass(frozen=True)
class TwoIonBalance:
    cation_count: int
    anion_count: int


@dataclass(frozen=True)
class BalanceRefusal:
    code: str
    reason: str


def balance_two(
    cation: ChargedSpecies, anion: ChargedSpecies
) -> TwoIonBalance | BalanceRefusal:
    if cation.charge <= 0 or anion.charge >= 0:
        return BalanceRefusal(
            code="not_opposite_signs",
            reason=(
                "A binary salt needs one positive charge and one negative "
                f"charge; got {cation.charge:+d} and {anion.charge:+d}."
            ),
        )
    common = gcd(cation.charge, -anion.charge)
    return TwoIonBalance(
        cation_count=(-anion.charge) // common,
        anion_count=cation.charge // common,
    )


def formula_unit_conserved(
    left: Sequence[tuple[Mapping[str, int], int]],
    right: Sequence[tuple[Mapping[str, int], int]],
) -> bool:
    def _total(parts: Sequence[tuple[Mapping[str, int], int]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for counts, n in parts:
            if n <= 0:
                return {"__invalid__": 1}
            for element, count in counts.items():
                out[element] = out.get(element, 0) + n * count
        return out

    return _total(left) == _total(right)
