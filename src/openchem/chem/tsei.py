"""The Cao-Liu topological steric effect index, under that name only.

**"STERIC INDEX" NAMES SEVERAL MUTUALLY INCOMPATIBLE QUANTITIES**, which
is why `topology_analysis` refused to ship one at all: its docstring
records that there was "no identity to check an implementation against,
and no reference value was found", and that shipping a number under a
recognised name that disagrees with every other tool reporting that name
would be worse than shipping nothing.

Half of that has changed and half has not. Cao & Liu ([source:cao2004])
define ONE specific quantity and print reference values for it, so there
is now something to check against. What has not changed is that the bare
name is ambiguous -- Taft's `Es`, Hancock's `Esc`, Charton's `nu` and
this are all "steric parameters" and none of them is the others. So this
is **Cao-Liu TSEI**, everywhere, and never "steric index".

Note the neighbouring trap `topology_analysis` already records: Mordred's
`SZ` is "sum of constitutional descriptor", a completely different
quantity wearing a promising name. That warning stands.

THE DEFINITION
==============

The general quantity is eq 4:

    V_rc = SUM over the substituent's atoms of  R_i^3 / l_i^3

where `R_i` is the ith atom's covalent radius and `l_i` is **the sum of
the bond lengths** from that atom to the reaction centre. TSEI is that
divided by the constant `k_t = R_C^3 / (2 R_C)^3 = 1/8`, which is what
makes it dimensionless. The paper states it as eq 8a/8b in relative form,
and that is the form implemented here because it is the one the paper
PRINTS:

    dTSEI_i = (R_i / R_C)^3 / (l_i / l_CC)^3      l_CC = 2 R_C

**EQ 7 IS A SPECIAL CASE, AND SHIPPING IT AS THE DEFINITION WAS A BUG.**
This module previously computed `SUM 1/L_i^3` -- eq 7 -- which the paper
derives one line after saying "**For any alkyl, it only contains carbon
and hydrogen atoms.** When its hydrogen atoms are ignored, eq 4 also can
be simplified to eq 6". For an all-carbon path every `R_i/R_C` is 1 and
every `l_i` is `L_i x l_CC`, so eq 8a collapses to eq 7 exactly and the
alkyl series in Table 1 reproduces perfectly either way. Off that series
it does not: a first-tier chlorine is **1.4190** by the paper's own
worked example and eq 7 gives 1.000, about 30% low.

THE TRAVERSAL, stated because the equation does not say it
===========================================================

For a reaction centre `centre` and a substituent entered at `first`:

    contributors  every atom reachable from `first` WITHOUT passing back
                  through `centre` -- so a ring fused to the centre is
                  counted whole, which is correct, those atoms do screen
                  it
    path          the breadth-first tree rooted at `centre`, which is the
                  shortest path by construction; where two shortest paths
                  tie, the one found first in RDKit's neighbour order
                  wins, and the tie only ever arises inside a ring where
                  both paths have the same length
    l_i           the sum over that path's bonds of (R_a + R_b), each bond
                  being the two end atoms' covalent radii added
    hydrogens     EXCLUDED by default, which is eq 6's own simplification
                  and the convention of Tables 1, 2 and 4. Table 6 uses
                  the other convention and says so in its footnote c, so
                  `include_hydrogens=True` is offered and named rather
                  than one of the two being silently picked.

THE CROWDED-BRANCH CORRECTION
=============================

The paper does not stop at eq 7 for alkyls either. Reading the SN2
hydrolysis rates it concludes "when three next tier carbon atoms
connected with one carbon atom, the total dTSEI of these three carbon
atoms is 6.5 times of that of one next tier carbon atom", and **every
TSEI value it publishes thereafter uses that**: t-Bu is 1.8125 in Table 2
and 1.8395 in Table 6, never the 1.3750 plain additivity gives. Table 2
tabulates both and prefers the corrected one, R = 1.0000 against 0.9411.

So `crowded_branches=True` is the default: shipping 1.3750 for t-Bu under
this paper's name would disagree with every value the paper prints, which
is the exact "one name, two quantities" failure this module exists to
avoid. The plain form is still reachable, because the paper tabulates it.

The rule is implemented exactly as stated -- a CARBON parent with exactly
THREE carbon children -- and no further. The paper states no rule for a
heteroatom, for four children, or for two, and inventing one would be
this application deriving physics its source declined to state.

WHAT IT IS AND IS NOT
=====================

    a property of a SUBSTITUENT, measured toward a named atom -- not a
    whole-molecule descriptor, and not defined without saying which atom
    the bulk is being felt at
    DIMENSIONLESS -- a relative specific volume divided by `k_t`
    a TOPOLOGICAL estimate of through-space bulk: it reads the graph, so
    it cannot see a conformation, and two rotamers score identically
    LIMITED TO SEVEN ELEMENTS, and it refuses the rest by name -- see
    `chem/data/tsei_radii.json` for why, and note that nitrogen is among
    the absences

THE ACCEPTANCE ORACLE IS THE PRINTED TABLES, NOT THE CORRELATIONS. The
paper reports r = 0.9912 and 0.9845 against biphenyl dihedral angles, and
those are a behavioural check worth having -- but a correlation is a weak
transcription oracle, because a systematically wrong implementation can
still correlate strongly. Table 1 prints exact values for normal alkyls
from n = 1 to 20, converging on 1.2009; Table 6 prints values for the
halogens, the ethers and the branched alkyls. `tests/test_tsei.py` checks
18 of the 19 printed values this module can reach.

**THE NINETEENTH DOES NOT REPRODUCE, AND IT IS RECORDED RATHER THAN
CHASED.** Table 6 gives i-Pr as 1.3752 where the traversal gives 1.2801.
The paper's own text says i-Pr is 1.2500 with hydrogens ignored (and
Table 2 and every i-Pr-bearing row of Table 4 agree), and 1.2500 plus its
seven hydrogens is 1.2801. Making 1.3752 come out needs the two
second-tier carbons scaled by 2.7611, a factor the paper never states and
which Table 4's own two-branch rows (i-Bu 1.1990, s-Bu 1.2870) refute.
1.3752 is within 0.0002 of 1.3750, which is t-Bu's plain-additivity value
in the very table above it. Recorded as an unreproduced printed value;
nothing here is tuned toward it.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from rdkit import Chem

from openchem.chem.calculator_options import atom_basis_of, decimals
from openchem.domain.common import ATOM_BASIS, TOTAL, CacheState, Provenance, decline_total
from openchem.domain.scientific_result import PerAtomDataset

#: DECLARED USER-FACING. See `tests/test_calculator_reachability.py`.
USER_FACING_PROVIDER = (
    "Cao-Liu TSEI, through the 'Cao-Liu TSEI projection (per atom)' calculator"
)

_DATA = Path(__file__).resolve().parent / "data"

#: The exponent in eq 3/4. Named rather than written inline because it is
#: the content of the definition: the screening an atom gives the reaction
#: centre goes as its VOLUME over the cube of its distance, which is why a
#: radius appears at all and why eq 2's surface form was superseded.
_VOLUME_EXPONENT = 3

#: "the total dTSEI of these three carbon atoms is 6.5 times of that of
#: one next tier carbon atom". The paper's own number, from a geometric
#: estimate in its Supporting Information (which is not held here).
_CROWDED_TRIPLE_FACTOR = 6.5


class TseiRadiusError(ValueError):
    """An element with no page-verified covalent radius.

    RAISED RATHER THAN GUESSED AT, for the reason
    `MillerAssignmentError` already gives one module along: substituting a
    radius from a neighbouring table produces a perfectly plausible number
    for a method that was never checked on that element. See
    `chem/data/tsei_radii.json` -- the paper's own radius source is not
    held locally, so the shipped radii are the ones a printed TSEI value
    can be inverted from.
    """


@dataclass(frozen=True)
class SubstituentTsei:
    """One substituent's Cao-Liu TSEI, toward one reaction centre."""

    value: float
    #: How many atoms contributed. Zero means the substituent was a lone
    #: hydrogen with hydrogens excluded, whose TSEI is 0 by eq 6.
    atoms: int
    #: `{atom index: dTSEI}`, the paper's own per-atom increment. Kept
    #: because the paper tabulates it and because it is what makes a
    #: disagreement debuggable rather than merely wrong.
    increments: dict[int, float]


@lru_cache(maxsize=1)
def _payload() -> dict:
    return json.loads((_DATA / "tsei_radii.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _radii() -> dict[str, float]:
    return {symbol: row["radius"] for symbol, row in _payload()["radii"].items()}


def covalent_radius(symbol: str) -> float:
    """The radius this method uses, or `TseiRadiusError`.

    Deliberately NOT `Chem.GetPeriodicTable().GetRcovalent` -- that is the
    Cordero 2008 set (carbon 0.760, chlorine 1.02) and it puts the paper's
    own chlorine example at 1.5052 against a printed 1.4190.
    """
    radius = _radii().get(symbol)
    if radius is None:
        raise TseiRadiusError(
            f"no page-verified covalent radius for {symbol}. Cao-Liu TSEI ships "
            f"radii for {', '.join(sorted(_radii()))} only, each recovered from a "
            "TSEI value the paper prints; extending it needs Lange's Handbook of "
            "Chemistry 15th ed. p 4.35, which this project does not hold."
        )
    return radius


def reference_values() -> list[dict]:
    """Every TSEI value the paper prints, for the acceptance test."""
    return list(_payload()["reference_values"])


def _carbon_radius() -> float:
    return covalent_radius("C")


def substituent_atoms(
    mol: Chem.Mol, centre: int, first: int, include_hydrogens: bool = False
) -> list[int]:
    """The atoms of the substituent attached at `first`.

    Everything reachable from `first` WITHOUT passing back through the
    reaction centre -- so for a ring fused to the centre this returns the
    whole ring, which is correct: those atoms do screen it.
    """
    return sorted(_walk(mol, centre, first, include_hydrogens)[0])


def _walk(
    mol: Chem.Mol, centre: int, first: int, include_hydrogens: bool
) -> tuple[list[int], dict[int, int]]:
    """`(contributing atoms, parent map)` from a breadth-first walk.

    BREADTH-FIRST IS LOAD-BEARING, not a style choice: the parent map it
    builds is the shortest-path tree, which is what `l_i` is defined over.
    A depth-first walk builds a spanning tree whose paths can be arbitrarily
    long inside a ring, and every increment computed from it would be too
    small while still looking like a TSEI.
    """
    parent: dict[int, int] = {first: centre}
    order: list[int] = [first]
    seen = {centre, first}
    queue = deque([first])
    while queue:
        index = queue.popleft()
        for neighbour in mol.GetAtomWithIdx(index).GetNeighbors():
            other = neighbour.GetIdx()
            if other in seen:
                continue
            seen.add(other)
            parent[other] = index
            order.append(other)
            queue.append(other)

    if not include_hydrogens:
        order = [i for i in order if mol.GetAtomWithIdx(i).GetAtomicNum() != 1]
    return order, parent


def substituent_tsei(
    mol: Chem.Mol,
    centre: int,
    first: int,
    include_hydrogens: bool = False,
    crowded_branches: bool = True,
) -> SubstituentTsei:
    """Cao-Liu TSEI of the substituent at `first`, felt at `centre`.

    `centre` is the reaction centre the bulk is measured toward. It is a
    REQUIRED argument and not defaulted, because TSEI without one is not a
    defined quantity -- the paper's `l_i` is a distance to something.

    Raises `TseiRadiusError` if any contributing atom has no page-verified
    radius. Refusing the whole substituent rather than skipping the atom is
    deliberate: a partial sum silently understates the screening, and this
    project has the `atomic_polarizabilities` precedent for exactly that.
    """
    order, parent = _walk(mol, centre, first, include_hydrogens)
    radius_c = _carbon_radius()
    bond_cc = 2.0 * radius_c

    def radius(index: int) -> float:
        return covalent_radius(mol.GetAtomWithIdx(index).GetSymbol())

    def path_length(index: int) -> float:
        total = 0.0
        while index != centre:
            up = parent[index]
            total += radius(index) + radius(up)
            index = up
        return total

    increments: dict[int, float] = {}
    for index in order:
        relative_radius = radius(index) / radius_c
        relative_length = path_length(index) / bond_cc
        increments[index] = (
            relative_radius**_VOLUME_EXPONENT / relative_length**_VOLUME_EXPONENT
        )

    if crowded_branches:
        _apply_crowded_branches(mol, centre, order, parent, increments)

    return SubstituentTsei(sum(increments.values()), len(increments), increments)


def _apply_crowded_branches(
    mol: Chem.Mol,
    centre: int,
    order: list[int],
    parent: dict[int, int],
    increments: dict[int, float],
) -> None:
    """"three next tier carbon atoms connected with one carbon atom".

    Their total becomes 6.5x one of them instead of 3x, which is what
    takes t-Bu from 1.3750 to the 1.8125 the paper publishes.

    THE CENTRE IS NOT A BRANCHING PARENT. Its other neighbours are other
    SUBSTITUENTS, and the paper's rule is about crowding within one --
    three separate substituents crowding a reaction centre is a different
    physical claim that this paper does not make.
    """
    for atom_parent in {parent[i] for i in order}:
        if atom_parent == centre:
            continue
        if mol.GetAtomWithIdx(atom_parent).GetAtomicNum() != 6:
            continue
        carbons = [
            i
            for i in order
            if parent.get(i) == atom_parent and mol.GetAtomWithIdx(i).GetAtomicNum() == 6
        ]
        if len(carbons) != 3:
            continue
        # The three sit at the same tier by construction, so they carry the
        # same increment and "6.5 times one of them" is unambiguous.
        share = _CROWDED_TRIPLE_FACTOR * increments[carbons[0]] / 3.0
        for index in carbons:
            increments[index] = share


def normal_alkyl_tsei(carbons: int) -> float:
    """TSEI of a straight -(CH2)n-1CH3 chain, as a pure function.

    The paper's Table 1 in closed form: on an all-carbon path every
    `R_i/R_C` is 1 and every `l_i` is `L_i x l_CC`, so eq 8a collapses to
    eq 7's `SUM 1/L_i^3` and the i-th carbon sits at topological distance
    i, giving `1 + 1/8 + 1/27 + ...`.

    **THE ACCEPTANCE ORACLE, and deliberately arithmetic rather than a
    structure walk** -- checking `substituent_tsei` against a table this
    function generated would be one implementation reading itself. What
    makes it a real check is that the paper PRINTS these values, so
    `tests/test_tsei.py` compares both against numbers typed from the
    page. A straight chain never has three carbons on one carbon, so the
    crowded-branch correction cannot reach this series.
    """
    return sum(1.0 / float(i) ** _VOLUME_EXPONENT for i in range(1, carbons + 1))


# ---------------------------------------------------------------------------
# The per-atom projection, and what it is NOT
# ---------------------------------------------------------------------------


def tsei_projection(
    mol: Chem.Mol, include_hydrogens: bool = False, crowded_branches: bool = True
) -> dict[int, float]:
    """Every heavy atom in turn as the reaction centre.

    **THIS IS OPENCHEM'S GENERALISATION, NOT THE PAPER'S QUANTITY.** Cao &
    Liu define TSEI for a SUBSTITUENT measured toward a named reaction
    centre; running that expression for every atom is a projection of it,
    and it is named as one everywhere it surfaces. The arithmetic at each
    atom is exactly the paper's -- each branch off the centre is treated
    as its own substituent and summed, which is also what keeps the
    crowded-branch correction scoped the way the paper scopes it.

    Raises `TseiRadiusError` if any atom has no page-verified radius.
    """
    values: dict[int, float] = {}
    for atom in mol.GetAtoms():
        if not include_hydrogens and atom.GetAtomicNum() == 1:
            continue
        centre = atom.GetIdx()
        total = 0.0
        for neighbour in atom.GetNeighbors():
            if not include_hydrogens and neighbour.GetAtomicNum() == 1:
                continue
            total += substituent_tsei(
                mol,
                centre,
                neighbour.GetIdx(),
                include_hydrogens=include_hydrogens,
                crowded_branches=crowded_branches,
            ).value
        values[centre] = total
    return values


def compute_tsei_projection(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """The Cao-Liu TSEI projection, for the Calculator Inspector's 2D/3D view.

    A crowded atom scores high because everything else in the molecule is
    close to it in the graph; a terminal one scores low. That is a reading
    of hindrance the app had no way to show.
    """
    parameters = parameters or {}
    places = decimals(parameters)
    include_hydrogens = bool(parameters.get("include_hydrogens", False))
    crowded = bool(parameters.get("crowded_branches", True))

    provenance = Provenance(
        created_by="core",
        method="cao_liu_tsei",
        parameters={
            "decimal_places": places,
            ATOM_BASIS: atom_basis_of(mol),
            "include_hydrogens": include_hydrogens,
            "crowded_branches": crowded,
            # DECLINED. Every atom's value counts every other atom, so a
            # sum over atoms double-counts each pair and lands on a number
            # with no referent -- the same shape as the summed
            # eccentricities `topology_analysis` already refuses.
            TOTAL: decline_total(
                "A TSEI is the screening ONE reaction centre feels. Every atom's "
                "value already counts every other atom, so adding them together "
                "counts each pair twice and is not a molecular quantity."
            ),
        },
    )

    try:
        values = tsei_projection(mol, include_hydrogens, crowded)
    except TseiRadiusError as error:
        return PerAtomDataset(
            property_id="tsei_projection",
            name="Cao-Liu TSEI projection",
            units="dimensionless",
            method="cao_liu_tsei",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=str(error),
            provenance=provenance,
        )

    return PerAtomDataset(
        property_id="tsei_projection",
        name="Cao-Liu TSEI projection",
        units="dimensionless",
        method="cao_liu_tsei",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=provenance,
    )
