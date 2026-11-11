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

#: Uncharged molecular acid or base in Mode A (B or HA), not a drawn ion.
KIND_MOLECULAR_NEUTRAL = "molecular_neutral"
#: A supplied ion. Mixed with a molecular neutral this is a missing proton source, not a salt.
KIND_ION = "ion"
#: Alkali hydroxide. Neutralization is refused; it is not a salt-assembly path.
KIND_METAL_HYDROXIDE = "metal_hydroxide"


@dataclass(frozen=True)
class ModeASpecies:
    identity: str
    charge: int
    kind: str
    element_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ModeAComposition:
    cation_count: int
    anion_count: int
    charge_valid: bool


@dataclass(frozen=True)
class ModeARefusal:
    code: str
    reason: str


def compose_mode_a(
    base: ModeASpecies,
    acid: ModeASpecies,
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal:
    if base.kind == KIND_METAL_HYDROXIDE or acid.kind == KIND_METAL_HYDROXIDE:
        return ModeARefusal(
            code="hydroxide_neutralization",
            reason=(
                "Metal-hydroxide neutralization is not two-neutral proton "
                "transfer; v1 does not form water and a spectator cation."
            ),
        )
    kinds = {base.kind, acid.kind}
    if KIND_MOLECULAR_NEUTRAL in kinds and KIND_ION in kinds:
        return ModeARefusal(
            code="missing_proton_source",
            reason=(
                "A molecular neutral plus a supplied ion does not provide "
                "the protons for the product ions."
            ),
        )
    if base.kind != KIND_MOLECULAR_NEUTRAL or acid.kind != KIND_MOLECULAR_NEUTRAL:
        return ModeARefusal(
            code="unsupported_parents",
            reason="Mode A workflow 1 needs two molecular neutrals.",
        )
    if base.charge != 0 or acid.charge != 0:
        return ModeARefusal(
            code="unsupported_parents",
            reason="Mode A workflow 1 parents must be uncharged.",
        )
    balanced = balance_two(
        ChargedSpecies(cation.identity, cation.charge),
        ChargedSpecies(anion.identity, anion.charge),
    )
    if isinstance(balanced, BalanceRefusal):
        return ModeARefusal(code=balanced.code, reason=balanced.reason)
    left = [
        (dict(base.element_counts), balanced.cation_count),
        (dict(acid.element_counts), balanced.anion_count),
    ]
    right = [
        (dict(cation.element_counts), balanced.cation_count),
        (dict(anion.element_counts), balanced.anion_count),
    ]
    if not formula_unit_conserved(left, right):
        return ModeARefusal(
            code="conservation_failed",
            reason=(
                "Element counts of the parents at the balanced multiplicities "
                "do not match the product ions."
            ),
        )
    return ModeAComposition(
        cation_count=balanced.cation_count,
        anion_count=balanced.anion_count,
        charge_valid=True,
    )


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
