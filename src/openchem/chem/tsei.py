"""The Cao-Liu topological steric effect index, under that name only.

**"STERIC INDEX" NAMES SEVERAL MUTUALLY INCOMPATIBLE QUANTITIES**, which
is why `topology_analysis` refused to ship one at all: its docstring
records that there was "no identity to check an implementation against,
and no reference value was found", and that shipping a number under a
recognised name that disagrees with every other tool reporting that name
would be worse than shipping nothing.

Half of that has changed and half has not. Cao & Liu
([source:cao2004]) define ONE specific quantity and print reference
values for it, so there is now something to check against. What has not
changed is that the bare name is ambiguous -- Taft's `Es`, Hancock's
`Esc`, Charton's `nu` and this are all "steric parameters" and none of
them is the others. So this is **Cao-Liu TSEI**, everywhere, and never
"steric index".

Note the neighbouring trap `topology_analysis` already records: Mordred's
`SZ` is "sum of constitutional descriptor", a completely different
quantity wearing a promising name. That warning stands.

THE DEFINITION, from the paper's eq 7:

    TSEI = SUM over the substituent's atoms of  1 / L_i^3

where `L_i` is the topological distance -- the number of consecutive
bonds -- from the i-th atom of the substituent to the REACTION CENTRE,
and hydrogens are ignored. The paper's own words: "the relative order of
the steric effect of the alkyl substituent can be quantified by the right
term of SUM(1/L_i^3), which is called the Topological Steric Effect
Index".

WHAT IT IS AND IS NOT:

    a property of a SUBSTITUENT, measured toward a named atom -- not a
    whole-molecule descriptor, and not defined without saying which atom
    the bulk is being felt at
    DIMENSIONLESS -- it is a relative specific volume divided by a
    constant `k_t`, which cancels
    HEAVY ATOMS ONLY, by the paper's own simplification
    a TOPOLOGICAL estimate of through-space bulk: it reads the graph, so
    it cannot see a conformation, and two rotamers score identically

THE ACCEPTANCE ORACLE IS TABLE 1, NOT THE CORRELATIONS. The paper reports
r = 0.9912 and 0.9845 against biphenyl dihedral angles, and those are a
behavioural check worth having -- but a correlation is a weak
transcription oracle, because a systematically wrong implementation can
still correlate strongly. Table 1 prints exact values for normal alkyls
from n = 1 to 20, converging on 1.2009, and reproducing a converging
series to four decimals is a far harder thing to do by accident.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem

#: The exponent in eq 7. Named rather than written inline because it is
#: the whole content of the definition: the screening a substituent atom
#: gives the reaction centre falls off as the cube of its topological
#: distance.
_DISTANCE_EXPONENT = 3


@dataclass(frozen=True)
class SubstituentTsei:
    """One substituent's Cao-Liu TSEI, toward one reaction centre."""

    value: float
    #: How many heavy atoms contributed. Zero means the substituent was
    #: a lone hydrogen, whose TSEI is 0 by the paper's simplification.
    atoms: int
    #: `{atom index: 1 / L^3}`, the paper's own per-atom increment. Kept
    #: because the paper tabulates it (its `delta-TSEI`) and because it is
    #: what makes a disagreement debuggable rather than merely wrong.
    increments: dict[int, float]


def substituent_atoms(mol: Chem.Mol, centre: int, first: int) -> list[int]:
    """The heavy atoms of the substituent attached at `first`.

    Everything reachable from `first` WITHOUT passing back through the
    reaction centre -- so for a ring fused to the centre this returns the
    whole ring, which is correct: those atoms do screen it.
    """
    seen = {centre}
    stack = [first]
    found: list[int] = []
    while stack:
        index = stack.pop()
        if index in seen:
            continue
        seen.add(index)
        atom = mol.GetAtomWithIdx(index)
        if atom.GetAtomicNum() == 1:
            continue
        found.append(index)
        stack.extend(n.GetIdx() for n in atom.GetNeighbors())
    return sorted(found)


def substituent_tsei(mol: Chem.Mol, centre: int, first: int) -> SubstituentTsei:
    """Cao-Liu TSEI of the substituent at `first`, felt at `centre`.

    `centre` is the reaction centre the bulk is measured toward. It is a
    REQUIRED argument and not defaulted, because TSEI without one is not
    a defined quantity -- the paper's `L_i` is a distance to something.
    """
    distances = Chem.GetDistanceMatrix(mol)
    increments = {
        index: 1.0 / float(distances[centre][index]) ** _DISTANCE_EXPONENT
        for index in substituent_atoms(mol, centre, first)
    }
    return SubstituentTsei(sum(increments.values()), len(increments), increments)


def normal_alkyl_tsei(carbons: int) -> float:
    """TSEI of a straight -(CH2)n-1CH3 chain, as a pure function.

    The paper's Table 1 in closed form: the i-th carbon sits at
    topological distance i, so the sum is `1 + 1/8 + 1/27 + ...`.

    **THE ACCEPTANCE ORACLE, and deliberately arithmetic rather than a
    structure walk** -- checking `substituent_tsei` against a table this
    function generated would be one implementation reading itself. What
    makes it a real check is that the paper PRINTS these values, so
    `tests/test_tsei.py` compares both against numbers typed from the
    page.
    """
    return sum(1.0 / float(i) ** _DISTANCE_EXPONENT for i in range(1, carbons + 1))
