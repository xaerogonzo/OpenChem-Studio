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
    "window: consumed by chem/salt_compose.py for Tools > Salt Composition"
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


def compose_supplied_ions(
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal:
    if cation.kind != KIND_ION or anion.kind != KIND_ION:
        return ModeARefusal(
            code="missing_proton_source",
            reason=(
                "A molecular neutral plus a supplied ion does not provide "
                "the protons for a transfer; supply both ions as given."
            ),
        )
    balanced = balance_two(
        ChargedSpecies(cation.identity, cation.charge),
        ChargedSpecies(anion.identity, anion.charge),
    )
    if isinstance(balanced, BalanceRefusal):
        return ModeARefusal(code=balanced.code, reason=balanced.reason)
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


@dataclass(frozen=True)
class IonizationRefusal:
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


#: Pick among fully specified ionic structures. An empty list is a net-charge
#: request with no structure; several distinct graphs at one charge are not ranked.
def choose_ionization(candidates: Sequence[str]) -> str | IonizationRefusal:
    unique = list(dict.fromkeys(candidates))
    if not unique:
        return IonizationRefusal(
            code="net_charge_only",
            reason="A net charge is not an ionization state; name a structure.",
        )
    if len(unique) > 1:
        return IonizationRefusal(
            code="ambiguous_microspecies",
            reason="Several structures share this charge; v1 does not pick one.",
        )
    return unique[0]


#: Fully specified structures the caller named.
ORIGIN_USER = "user"
#: Sequential ladder species, in the ladder's own index order.
ORIGIN_LADDER = "ladder"

#: Unique compositions Mode C returns. Generated may be larger; omitted is the rest.
MODE_C_LIMIT = 50


@dataclass(frozen=True)
class ModeCCandidate:
    identity: str
    charge: int
    origin: str
    ladder_index: int | None = None


@dataclass(frozen=True)
class ModeCHit:
    cation_identity: str
    anion_identity: str
    cation_count: int
    anion_count: int
    charge_valid: bool


@dataclass(frozen=True)
class ModeCResult:
    hits: tuple[ModeCHit, ...]
    generated: int
    returned: int
    omitted: int
    notes: tuple[str, ...]


def _mode_c_order(candidate: ModeCCandidate) -> tuple[int, int, str]:
    if candidate.origin == ORIGIN_USER:
        rank = 0
    elif candidate.origin == ORIGIN_LADDER:
        rank = 1
    else:
        rank = 2
    index = candidate.ladder_index if candidate.ladder_index is not None else 0
    return (rank, index, candidate.identity)


def enumerate_mode_c(
    cations: Sequence[ModeCCandidate],
    anions: Sequence[ModeCCandidate],
    notes: Sequence[str] = (),
) -> ModeCResult:
    """Cartesian product of one cation list and one anion list, then ``balance_two``.

    Deduplicates identical species+ratio, keeps the first occurrence, and
    truncates to ``MODE_C_LIMIT``. pKa is not consulted.
    """
    ordered_cations = sorted(cations, key=_mode_c_order)
    ordered_anions = sorted(anions, key=_mode_c_order)
    unique: list[ModeCHit] = []
    seen: set[tuple[str, str, int, int]] = set()
    for cation in ordered_cations:
        for anion in ordered_anions:
            balanced = balance_two(
                ChargedSpecies(cation.identity, cation.charge),
                ChargedSpecies(anion.identity, anion.charge),
            )
            if isinstance(balanced, BalanceRefusal):
                continue
            key = (
                cation.identity,
                anion.identity,
                balanced.cation_count,
                balanced.anion_count,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                ModeCHit(
                    cation_identity=cation.identity,
                    anion_identity=anion.identity,
                    cation_count=balanced.cation_count,
                    anion_count=balanced.anion_count,
                    charge_valid=True,
                )
            )
    generated = len(unique)
    hits = tuple(unique[:MODE_C_LIMIT])
    return ModeCResult(
        hits=hits,
        generated=generated,
        returned=len(hits),
        omitted=generated - len(hits),
        notes=tuple(notes),
    )
