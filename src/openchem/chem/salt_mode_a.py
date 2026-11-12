"""Mode A: two parent molecules and two product ions, no pKa.

Does not invent a microspecies. Metal hydroxide is a refusal, not a path.
"""

from __future__ import annotations

from collections import Counter

from rdkit import Chem

from openchem.chem.salt_components import (
    IdentityRefusal,
    fragment_formal_charge,
    fragment_key,
)
from openchem.domain.salt_stoichiometry import (
    KIND_ION,
    KIND_METAL_HYDROXIDE,
    KIND_MOLECULAR_NEUTRAL,
    ModeAComposition,
    ModeARefusal,
    ModeASpecies,
    compose_mode_a,
    compose_supplied_ions,
)

_ALKALI = frozenset({"Li", "Na", "K", "Rb", "Cs"})


def _counts(mol: Chem.Mol) -> tuple[tuple[str, int], ...]:
    tallies: Counter[str] = Counter()
    for atom in mol.GetAtoms():
        tallies[atom.GetSymbol()] += 1
        tallies["H"] += atom.GetTotalNumHs()
    return tuple(sorted((el, n) for el, n in tallies.items() if n))


def _is_disconnected_metal_hydroxide(mol: Chem.Mol) -> bool:
    """Alkali cation fragment plus hydroxide anion in one disconnected mol."""
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    if len(frags) != 2:
        return False
    alkali, hydroxide = None, None
    for frag in frags:
        symbols = {a.GetSymbol() for a in frag.GetAtoms()}
        charge = fragment_formal_charge(frag)
        if symbols <= _ALKALI and len(symbols) == 1 and charge > 0:
            alkali = frag
        elif symbols <= {"O", "H"} and charge < 0 and frag.GetNumHeavyAtoms() == 1:
            hydroxide = frag
    return alkali is not None and hydroxide is not None


def _kind(mol: Chem.Mol, charge: int) -> str:
    if _is_disconnected_metal_hydroxide(mol):
        return KIND_METAL_HYDROXIDE
    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    metals = [s for s in symbols if s in _ALKALI]
    oxygens = [s for s in symbols if s == "O"]
    others = [s for s in symbols if s not in _ALKALI and s != "O" and s != "H"]
    if metals and oxygens and not others and len(metals) == 1 and len(oxygens) == 1:
        return KIND_METAL_HYDROXIDE
    if charge != 0:
        return KIND_ION
    return KIND_MOLECULAR_NEUTRAL


def species_from_mol(mol: Chem.Mol) -> ModeASpecies | IdentityRefusal:
    key = fragment_key(mol)
    if isinstance(key, IdentityRefusal):
        return key
    charge = fragment_formal_charge(mol)
    return ModeASpecies(key, charge, _kind(mol, charge), _counts(mol))


def compose_from_mols(
    base: Chem.Mol,
    acid: Chem.Mol,
    cation: Chem.Mol,
    anion: Chem.Mol,
) -> ModeAComposition | ModeARefusal | IdentityRefusal:
    parts = [species_from_mol(base), species_from_mol(acid), species_from_mol(cation), species_from_mol(anion)]
    for part in parts:
        if isinstance(part, IdentityRefusal):
            return part
    return compose_mode_a(parts[0], parts[1], parts[2], parts[3])


def compose_from_ion_mols(
    cation: Chem.Mol,
    anion: Chem.Mol,
) -> ModeAComposition | ModeARefusal | IdentityRefusal:
    parts = [species_from_mol(cation), species_from_mol(anion)]
    for part in parts:
        if isinstance(part, IdentityRefusal):
            return part
    return compose_supplied_ions(parts[0], parts[1])
