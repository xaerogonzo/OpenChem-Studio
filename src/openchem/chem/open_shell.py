"""What a structure says about unpaired electrons, and the spin choices that follow from it.

**WHY THIS EXISTS (docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).** RDKit accepts a radical, a carbene and
triplet O2 drawn as [O][O], so the ordinary path runs for them and nothing downstream knows the molecule is open-shell.
Measured: no calculator returned NaN or raised on twelve open-shell species; the defects are numbers computed as if
the molecule were closed-shell (Joback groups for ethyl radical included a vinyl CH2; Hueckel dropped benzyl's
radical carbon) and a quantum run whose multiplicity stays at 1 (real ORCA B3LYP/def2-SVP: O2 at multiplicity 1 is
0.0632 Eh, 39.7 kcal/mol, above the triplet, and runs without a message).

**WHAT IS AND IS NOT KNOWN FROM A STRUCTURE.** The number of unpaired electrons is read from the radical-electron
count RDKit keeps (`M  RAD` in a molfile). The multiplicity is NOT stored on the molecule: RDKit reads a molfile's
singlet (`M  RAD 1`) and triplet (`M  RAD 3`) both as two radical electrons and writes the triplet back, so a
singlet carbene cannot be told from a triplet one (measured). `default_multiplicity` is therefore the high-spin
rule, unpaired electrons plus one, which is right for methyl, hydroxyl, NO, triplet O2 and triplet CH2 and is a
DEFAULT the person can change, never a fact about the molecule. Pure RDKit, no Qt, no state.
"""

from __future__ import annotations

from rdkit import Chem

#: Why a group-contribution method refuses a radical; one wording for Joback and Hansen.
OPEN_SHELL_GROUP_NOTE = (
    "{method}'s groups are defined for closed-shell molecules and match on hydrogen and connection counts, "
    "not on a missing valence, so an unpaired electron is read as if the group were complete."
)


def unpaired_electrons(mol: Chem.Mol) -> int:
    """The radical electrons the structure carries (RDKit's count: a carbene has two, a radical one)."""
    return sum(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms())


def has_unpaired_electrons(mol: Chem.Mol) -> bool:
    return unpaired_electrons(mol) > 0


def electron_count(mol: Chem.Mol, charge: int) -> int:
    """All electrons of the species: nuclear charges plus hydrogens the molecule holds implicitly, less the net charge."""
    return sum(atom.GetAtomicNum() + atom.GetTotalNumHs() for atom in mol.GetAtoms()) - charge


def default_multiplicity(mol: Chem.Mol) -> int:
    """High-spin multiplicity of the drawn radicals, 2S+1 with one electron per spin: 1 for a closed-shell drawing."""
    return unpaired_electrons(mol) + 1


def multiplicity_problem(mol: Chem.Mol, charge: int, multiplicity: int) -> str:
    """Why this charge and multiplicity cannot belong to the molecule's electrons, or "" when they can.

    The check ORCA makes itself (exit 55, 'multiplicity (1) is odd and number of electrons (9) is odd -> impossible',
    measured on a methyl radical and on NO) and xtb does not (`xtb_engine.check_electrons`), made here so a person is
    told before a job is queued.
    """
    electrons = electron_count(mol, charge)
    unpaired = multiplicity - 1
    if unpaired < 0:
        return f"A multiplicity of {multiplicity} is not possible."
    if electrons < unpaired or (electrons - unpaired) % 2:
        return (
            f"{electrons} electrons cannot have multiplicity {multiplicity} (charge {charge:+d}): "
            f"{'an even' if electrons % 2 == 0 else 'an odd'} number of electrons needs "
            f"{'an odd' if electrons % 2 == 0 else 'an even'} multiplicity."
        )
    return ""


def spin_note(mol: Chem.Mol, multiplicity: int) -> str:
    """A caution when the multiplicity chosen does not match the radicals drawn, or "" when it does.

    Said, not refused: a person may want the open-shell singlet or a low-spin state. What is measured is that the
    mismatch is silent: O2 and CH2 at multiplicity 1 ran and finished, 39.7 and 41.9 kcal/mol above the triplet.
    """
    unpaired = unpaired_electrons(mol)
    if unpaired == 0 or multiplicity == unpaired + 1:
        return ""
    if multiplicity == 1:
        return (
            f"The drawing has {unpaired} unpaired electron{'s' if unpaired != 1 else ''}, and multiplicity 1 runs a closed-shell "
            f"calculation. That is a different state from the one drawn (multiplicity {unpaired + 1}) and is not its ground state "
            "for a radical, triplet O2 or triplet CH2."
        )
    return (
        f"The drawing has {unpaired} unpaired electron{'s' if unpaired != 1 else ''}, which is multiplicity {unpaired + 1}; "
        f"this run uses multiplicity {multiplicity}."
    )
