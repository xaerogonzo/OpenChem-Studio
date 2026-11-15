"""Assigning DREIDING atom types to an RDKit molecule.

DREIDING's type is `<element><hybridisation>` -- `C_3`, `C_R`, `N_2` --
and everything else in the force field keys off it, so this runs first and
a mistake here is a wrong energy rather than an error.

The paper's own description (page 8898): the first two characters are the
element, right-padded with `_`; the third is the hybridisation, `1`/`2`/`3`
for linear/trigonal/tetrahedral and `R` for a resonant (aromatic or
otherwise conjugated) centre.

**A resonant centre is not the same as an RDKit aromatic atom**, and that
is the one judgement call here. The paper puts amide nitrogen in `N_R`
because its lone pair conjugates, while RDKit marks it aliphatic. Handled
explicitly in `_is_resonant`, with the reason at the site.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.dreiding.parameters import VALENCE


class UntypedAtomError(ValueError):
    """No DREIDING type exists for an atom.

    Raised rather than substituted. DREIDING covers 37 types and stops;
    guessing a radius for a transition metal outside the table would give
    a number with no source, which is the failure this whole module is
    written to avoid.
    """


#: Elements whose type carries no hybridisation suffix -- monovalent
#: halogens and the metals in Table I.
_UNHYBRIDISED = {
    "F": "F_",
    "Cl": "Cl",
    "Br": "Br",
    "I": "I_",
    "Na": "Na",
    "Ca": "Ca",
    "Fe": "Fe",
    "Zn": "Zn",
}

#: Elements written with a two-character stem plus a bare `3`, rather than
#: the `X_3` form. Straight from Table I, where `Al3` and `Si3` sit beside
#: `P_3` and `S_3`.
_BARE_DIGIT_STEMS = {"Al", "Si", "Ga", "Ge", "As", "Se", "In", "Sn", "Sb", "Te"}


#: The most neighbours (hydrogens included) a type's own geometry allows, from its hybridisation digit: `X_3` is
#: tetrahedral (four), `X_2` and `X_R` trigonal (three), `X_1` linear (two), and a one-bond type one. A centre with more is
#: not that type, and typing it anyway gave a number that means nothing: SF6 as `S_3` came out at 708 kcal/mol, PF5 as `P_3`
#: at 163, a perchlorate chlorine as a monovalent halogen at 404 (measured 2026-11-13).
_MAX_NEIGHBOURS = {"3": 4, "2": 3, "R": 3, "1": 2}
#: The metals in Table I, which the neighbour limit does not bind: their coordination is whatever the complex has.
_METALS = {"Na", "Ca", "Fe", "Zn"}


def _coordination_limit(candidate: str) -> int | None:
    """The neighbour limit of a DREIDING type, or None where it is not bounded."""
    symbol = candidate.rstrip("_0123R") or candidate
    if candidate in {"H_", "F_", "Cl", "Br", "I_"}:
        return 1
    if symbol in _METALS or candidate[:2].rstrip("_") in _METALS:
        return None
    return _MAX_NEIGHBOURS.get(candidate[-1])


def _is_resonant(atom: Chem.Atom) -> bool:
    """Whether this centre is `X_R` rather than `X_2`.

    RDKit aromaticity is the main signal, plus the case the paper names
    that RDKit does not mark: **an sp2 nitrogen or oxygen whose lone pair
    conjugates into an adjacent pi system.** The paper's footnote 8 is
    explicit for the aromatic case -- an -NH2 or -OH on a ring carbon is
    described as `N_R`/`O_R` so that the C_R-N_R torsion picks up the
    5 kcal/mol barrier of equation 18 rather than the 2.0 of a plain
    single bond.
    """
    if atom.GetIsAromatic():
        return True
    if atom.GetSymbol() not in ("N", "O"):
        return False
    # A lone pair next to a multiple bond or an aromatic ring: amide N,
    # ester/phenol O. Excludes an sp2 atom that is itself doubly bonded,
    # which is a plain X_2.
    if any(bond.GetBondType() != Chem.BondType.SINGLE for bond in atom.GetBonds()):
        return False
    for neighbour in atom.GetNeighbors():
        if neighbour.GetIsAromatic():
            return True
        for bond in neighbour.GetBonds():
            if bond.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE):
                return True
    return False


def _hybridisation_digit(atom: Chem.Atom) -> str:
    """`1`, `2` or `3` from the bonding, not from RDKit's own enum.

    Counted from bond orders rather than read off `GetHybridization()`
    because RDKit reports SP3 for an amide nitrogen and SP2 for others
    inconsistently across sanitisation states, while "does it carry a
    triple bond or two doubles" is unambiguous.
    """
    orders = [bond.GetBondTypeAsDouble() for bond in atom.GetBonds()]
    if any(order >= 3 for order in orders) or orders.count(2.0) == 2:
        return "1"
    if any(order == 2.0 for order in orders):
        return "2"
    return "3"


def atom_type(atom: Chem.Atom) -> str:
    """The DREIDING type for one atom, e.g. `C_3`.

    Hydrogen is always `H_`. The bridging `H__b` and hydrogen-bonding
    `H___HB` types are deliberately NOT assigned automatically: the first
    belongs to boranes and the second is a modelling choice about which
    hydrogens participate in the explicit H-bond term, and inferring
    either from connectivity alone would be a guess.
    """
    symbol = atom.GetSymbol()
    if symbol == "H":
        return _checked(atom, "H_")
    if symbol in _UNHYBRIDISED:
        return _checked(atom, _UNHYBRIDISED[symbol])

    if _is_resonant(atom):
        suffix = "R"
    else:
        suffix = _hybridisation_digit(atom)

    if symbol in _BARE_DIGIT_STEMS:
        candidate = f"{symbol}3"  # Table I lists only the sp3 form for these
    elif len(symbol) == 1:
        candidate = f"{symbol}_{suffix}"
    else:
        candidate = f"{symbol}{suffix}"

    if candidate not in VALENCE:
        raise UntypedAtomError(
            f"DREIDING has no parameters for {symbol} as {candidate!r}. The "
            "force field covers 37 atom types (Table I of Mayo, Olafson & "
            "Goddard 1990) and this structure needs one outside them."
        )
    return _checked(atom, candidate)


def _sp3_limit(atom: Chem.Atom) -> int:
    """Neighbours an sp3 main-group atom has from its own electrons: its valence electrons less its charge, `v`, gives
    `v` bonds up to four and `8 - v` beyond (neutral C 4, N 3, O 2, P 3, S 2, B 3; N+ 4, S+ 3, B- 4). SF4's sulfur has four
    neighbours and a lone pair, which is not an sp3 sulfur, however tetrahedral the formula looks."""
    outer = Chem.GetPeriodicTable().GetNOuterElecs(atom.GetAtomicNum()) - atom.GetFormalCharge()
    return outer if outer <= 4 else 8 - outer


def _checked(atom: Chem.Atom, candidate: str) -> str:
    """`candidate`, unless the atom has more neighbours than that type's geometry has."""
    limit = _coordination_limit(candidate)
    if limit is not None and candidate.endswith("3") and candidate not in {"H_", "F_", "Cl", "Br", "I_"}:
        limit = min(limit, max(_sp3_limit(atom), 0))
    neighbours = atom.GetTotalDegree()
    if limit is not None and neighbours > limit:
        raise UntypedAtomError(
            f"{atom.GetSymbol()} has {neighbours} neighbours, more than DREIDING's {candidate.strip('_')!r} type allows "
            f"({limit}). The force field has no type for a hypervalent or over-coordinated centre, and the number it "
            "would give is not an energy."
        )
    return candidate


def assign_types(mol: Chem.Mol) -> list[str]:
    """DREIDING types for every atom, in atom-index order.

    Requires EXPLICIT hydrogens. DREIDING's united-atom types (`C_33` and
    friends, Table II) carry their own van der Waals parameters and are a
    different model; silently treating an implicit-hydrogen structure as
    the explicit one would drop most of the atoms in an alkane.
    """
    if any(atom.GetTotalNumHs() for atom in mol.GetAtoms()):
        raise UntypedAtomError(
            "DREIDING needs explicit hydrogens -- call Chem.AddHs first. "
            "The implicit-hydrogen united atoms are a different "
            "parameterisation, not this one with the hydrogens dropped."
        )
    return [atom_type(atom) for atom in mol.GetAtoms()]
