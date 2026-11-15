"""Which of RDKit's perceived stereo elements this application counts as stereocentres.

WHY THIS EXISTS (WP2 of docs/HYPERVALENT_COVERAGE_DESIGN.md). `Chem.FindPotentialStereo` reports one tetrahedral
element for an atom with five or six neighbours whose substituents it cannot tell apart, so SF6, PF5, PCl5, IF5, Ar-SF5
and CH3-PF4 were counted as having a chiral centre ("Chiral center count: 1", "1 stereo element(s), 1 undefined").
That is not a stereocentre in the sense the report states: the model is tetrahedral or pyramidal, three or four
neighbours, and RDKit applies it to a centre it does not describe. Measured 2026-11-13: the always-on stereocentre count
and the stereocentre calculators already said 0; topology analysis and the stereo descriptors said 1.

THE RULE. An atom is assessed only with at most `MAX_STEREO_COORDINATION` neighbours (hydrogens counted). A higher
coordination is NOT counted and is NOT called achiral either: it is reported as not assessed, because a five- or six-
coordinate centre can be stereogenic (a chiral octahedral complex), and this model says nothing about it.
"""

from __future__ import annotations

from rdkit import Chem

#: The most neighbours (explicit and implicit hydrogens included) a tetrahedral or pyramidal stereocentre has here.
MAX_STEREO_COORDINATION = 4


def is_assessed(mol: Chem.Mol, atom_index: int) -> bool:
    """True when the atom's coordination is one the tetrahedral/pyramidal stereo model describes."""
    return mol.GetAtomWithIdx(atom_index).GetTotalDegree() <= MAX_STEREO_COORDINATION


def perceived_elements(mol: Chem.Mol) -> list:
    """`FindPotentialStereo`'s elements, without the atom centres this model does not describe."""
    return [
        element
        for element in Chem.FindPotentialStereo(mol)
        if not str(element.type).startswith("Atom_") or is_assessed(mol, int(element.centeredOn))
    ]


def unassessed_centres(mol: Chem.Mol) -> list[int]:
    """Atoms RDKit perceives as stereo elements that are left out for their coordination, in order."""
    return [
        int(element.centeredOn)
        for element in Chem.FindPotentialStereo(mol)
        if str(element.type).startswith("Atom_") and not is_assessed(mol, int(element.centeredOn))
    ]
