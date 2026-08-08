"""The one place that knows how the vendored organometallic code works.

`vendor/iupac_namer/perception/organometallic.py` is 5,020 lines of real
perception -- metallocenes, cyclopentadienide rings, carbonyls, nitrosyls
-- written to produce a NAME and then throw the perception away. This
surfaces it, the way `structure_annotation.py` surfaced the same engine's
ring and functional-group analysis.

**A vendored module is not an API.** Everything below reaches into
private, underscore-prefixed functions of a file this project does not
own. That is exactly why it happens HERE and nowhere else: when the
vendored namer changes, one file needs repairing rather than four, and
`substance.py`, `oxidation_states.py` and `bond_report.py` never learn
that the namer exists.

## What it can actually do, measured rather than assumed

    classify_metallocene                27 EXACT structures, by canonical
                                        SMILES. Gives a retained name.
                                        Returns None for methylferrocene.
    _classify_substituted_metallocene   GENERAL. Handled methylferrocene,
                                        returning the metal and both Cp
                                        rings with substituent prefixes.

The narrow one is a pin table; the general one is perception. Both are
used, in that order, because a pinned hit also yields the accepted name
and the general one does not.

Everything here **fails soft**. A namer that cannot classify something
must not take a calculator down with it, so every call is wrapped and a
failure means "nothing perceived" rather than an exception.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("openchem.chem")


@dataclass(frozen=True)
class CpRing:
    """One cyclopentadienyl ring bound to a metal."""

    atom_indices: tuple[int, ...]
    #: "" for an unsubstituted ring, else the namer's own prefix
    #: ("methyl", "pentamethyl"...).
    substituent_prefix: str = ""

    @property
    def label(self) -> str:
        return f"{self.substituent_prefix}Cp" if self.substituent_prefix else "Cp"


@dataclass(frozen=True)
class Metallocene:
    """A sandwich complex, as the vendored perception sees it."""

    metal_symbol: str
    metal_index: int | None
    rings: tuple[CpRing, ...]
    #: The accepted name when this matched a pinned structure, else "".
    #: Absence is not a failure -- methylferrocene is perceived without
    #: being pinned -- so callers must not treat it as identity.
    retained_name: str = ""

    @property
    def is_pinned(self) -> bool:
        return bool(self.retained_name)


#: Elements that form sandwich complexes. Broad rather than exact, for
#: the same reason `_METALS` in `chem/substance.py` is: refusing an
#: unusual metal is worse than considering one.
_SANDWICH_METALS = frozenset(
    "Sc Ti V Cr Mn Fe Co Ni Y Zr Nb Mo Tc Ru Rh Pd Hf Ta W Re Os Ir Pt "
    "Sm Eu Yb U Th Mg Ca Sn Pb".split()
)


def _as_ionic_sandwich(mol):
    """A sigma-bonded sandwich drawing, redrawn in the ionic form.

    **Normalising the DRAWING instead of forking the vendor.** The
    vendored perception recognises only `[cH-]1cccc1.[cH-]1cccc1.[Fe+2]`;
    somebody who draws ferrocene with bonds from the iron to the rings --
    which is how most people draw it -- got nothing. The obvious fix was
    to teach `vendor/.../organometallic.py` about bonded forms, and that
    is precisely what this adapter exists to avoid: a change inside 5,020
    lines of vendored code has to be re-applied every time the vendor
    moves.

    So the molecule is converted to the form the vendor already
    understands, and the vendor is left alone.

    **Atom indices are preserved, and callers depend on it.** Removing a
    bond and changing charges does not renumber atoms, so the ring and
    metal indices this returns address the CALLER's molecule. That is
    asserted in the tests rather than assumed -- an index that silently
    means something else is the bug this project has now hit twice, in
    Ketcher's pool ids and in the crystal viewer.

    Returns None for anything that is not a two-ring sandwich, including
    a structure that will not sanitise afterwards.
    """
    from rdkit import Chem

    metals = [a for a in mol.GetAtoms() if a.GetSymbol() in _SANDWICH_METALS]
    if len(metals) != 1:
        return None
    metal = metals[0]

    rings = mol.GetRingInfo().AtomRings()
    cp_rings: list[tuple[int, ...]] = []
    for neighbour in metal.GetNeighbors():
        for ring in rings:
            if len(ring) != 5 or neighbour.GetIdx() not in ring:
                continue
            if not all(mol.GetAtomWithIdx(i).GetSymbol() == "C" for i in ring):
                continue
            if all(set(ring) != set(known) for known in cp_rings):
                cp_rings.append(ring)
    # Exactly two: one ring is a half-sandwich (different perception) and
    # three is not a structure this vendor classifies either.
    if len(cp_rings) != 2:
        return None

    editable = Chem.RWMol(mol)
    ring_atoms = {index for ring in cp_rings for index in ring}
    for neighbour in list(metal.GetNeighbors()):
        if neighbour.GetIdx() in ring_atoms:
            editable.RemoveBond(metal.GetIdx(), neighbour.GetIdx())

    for ring in cp_rings:
        unsubstituted = []
        for index in ring:
            atom = editable.GetAtomWithIdx(index)
            atom.SetIsAromatic(True)
            atom.SetFormalCharge(0)
            # **Per atom, not one each.** A substituted ring carbon has no
            # hydrogen, and forcing one on it made methylferrocene fail to
            # sanitise -- so a bonded SUBSTITUTED sandwich returned None
            # while the plain ones worked, which is the confusing half of
            # a bug rather than an obvious one.
            substituents = [
                n for n in atom.GetNeighbors()
                if n.GetIdx() not in ring_atoms and n.GetIdx() != metal.GetIdx()
            ]
            atom.SetNumExplicitHs(0 if substituents else 1)
            atom.SetNoImplicit(True)
            if not substituents:
                unsubstituted.append(index)
        # The 6 pi electrons come from somewhere: one ring carbon carries
        # the charge, which is how the vendored form is written. It has to
        # be an unsubstituted one -- a carbon holding both a substituent
        # and the charge is a different species.
        editable.GetAtomWithIdx(unsubstituted[0] if unsubstituted else ring[0]).SetFormalCharge(-1)
        for position in range(5):
            bond = editable.GetBondBetweenAtoms(ring[position], ring[(position + 1) % 5])
            if bond is not None:
                bond.SetBondType(Chem.BondType.AROMATIC)
                bond.SetIsAromatic(True)
    editable.GetAtomWithIdx(metal.GetIdx()).SetFormalCharge(2)

    normalised = editable.GetMol()
    try:
        Chem.SanitizeMol(normalised)
    except Exception:  # noqa: BLE001 - a drawing that will not sanitise is not one of these
        logger.debug("sandwich normalisation did not sanitise", exc_info=True)
        return None
    return normalised


def _module():
    from openchem.vendor.iupac_namer.perception import organometallic

    return organometallic


def metallocene(mol) -> Metallocene | None:
    """Perceive a sandwich complex, or return None.

    Tries the pin table first because a hit there also yields the accepted
    name; falls back to the general classifier, which is what handles
    every substituted ring.

    A SIGMA-BONDED drawing is normalised to the ionic form first. The
    vendored perception knows only the ionic one, so ferrocene drawn the
    way most people draw it -- bonds from the iron to both rings --
    returned None. See `_as_ionic_sandwich` for why that is fixed here
    rather than inside the vendor.
    """
    if mol is None:
        return None
    try:
        module = _module()
    except Exception:  # noqa: BLE001 - a missing vendor must not be fatal
        logger.debug("organometallic perception unavailable", exc_info=True)
        return None

    # The ionic form is tried FIRST and unchanged, so nothing about the
    # existing path can regress: normalisation only ever runs on a
    # molecule the vendor has already declined.
    for candidate in (mol, _as_ionic_sandwich(mol)):
        if candidate is None:
            continue
        found = _perceive_ionic(candidate, module)
        if found is not None:
            return found
    return None


def _perceive_ionic(mol, module) -> Metallocene | None:
    """The vendored perception, on a molecule already in ionic form."""
    try:
        pinned = module.classify_metallocene(mol)
    except Exception:  # noqa: BLE001
        logger.debug("classify_metallocene failed", exc_info=True)
        pinned = None
    if pinned is not None:
        return Metallocene(
            metal_symbol=mol.GetAtomWithIdx(pinned.center_atom_idx).GetSymbol(),
            metal_index=pinned.center_atom_idx,
            rings=tuple(
                CpRing(tuple(sorted(ring))) for ring in pinned.ring_atom_sets
            ),
            retained_name=pinned.retained_name,
        )

    try:
        general = module._classify_substituted_metallocene(mol)
    except Exception:  # noqa: BLE001
        logger.debug("_classify_substituted_metallocene failed", exc_info=True)
        return None
    if not general:
        return None

    symbol, *rings = general
    metal_index = next(
        (a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == symbol), None
    )
    return Metallocene(
        metal_symbol=symbol,
        metal_index=metal_index,
        rings=tuple(
            CpRing(tuple(sorted(ring.atom_idxs)), getattr(ring, "substituent_prefix", ""))
            for ring in rings
        ),
    )


def is_cyclopentadienide(mol, atom_indices) -> bool:
    """Whether these atoms are a Cp- ring, by the namer's own test."""
    try:
        return bool(_module()._is_cyclopentadienide_anion_fragment(mol, tuple(atom_indices)))
    except Exception:  # noqa: BLE001
        logger.debug("cyclopentadienide test failed", exc_info=True)
        return False


def is_carbonyl_ligand(mol, atom_indices) -> bool:
    """Whether these atoms are a CO ligand, by the namer's own test."""
    try:
        return bool(_module()._is_co_fragment(mol, tuple(atom_indices)))
    except Exception:  # noqa: BLE001
        logger.debug("carbonyl test failed", exc_info=True)
        return False
