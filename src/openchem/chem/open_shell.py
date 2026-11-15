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

import re

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


#: Neutral molecules whose ground state is a triplet although the usual drawing has no unpaired electrons (keyed by canonical SMILES of the
#: closed-shell drawing). Each was MEASURED here, not only recalled: real ORCA 6.1.1, B3LYP/def2-SVP, triplet minus singlet energy at the
#: optimised geometry: O2 -39.7, SO -29.7, S2 -23.7 kcal/mol (`benchmarks/open_shell/orca_spin_states.py`). N2 (+147.5) is the control that
#: must not be here. The ground states are textbook X 3Sigma-; a literature citation per row is still to be attached (OS2 in the design).
TRIPLET_GROUND_STATES = frozenset({"O=O", "S=S", "O=S"})


# --- the spin a molfile states (RDKit cannot keep it) -------------------------------------------------------------------------------------------

#: Unpaired electrons an atom's `M  RAD` code stands for: 1 singlet (a carbene's paired electrons), 2 doublet, 3 triplet.
_RAD_UNPAIRED = {1: 0, 2: 1, 3: 2}
#: One `M  RAD` line: the count, then (atom, code) pairs, atoms 1-based; at most eight pairs to a line.
_RAD_LINE = re.compile(r"^M  RAD\s+(\d+)((?:\s+\d+\s+\d+)+)\s*$")


def rad_codes(molblock: str) -> dict[int, int]:
    """The molfile's own `M  RAD` codes, atom index (0-based) -> code. Empty when it has none."""
    codes: dict[int, int] = {}
    for line in molblock.splitlines():
        match = _RAD_LINE.match(line)
        if match:
            numbers = [int(n) for n in match.group(2).split()]
            codes.update({numbers[i] - 1: numbers[i + 1] for i in range(0, len(numbers) - 1, 2)})
    return codes


def spin_from_molblock(molblock: str | None) -> int | None:
    """The multiplicity a molfile's radical codes state (one electron per spin: singlet 0, doublet 1, triplet 2 unpaired each), or None when it has none.

    RDKit reads singlet (1) and triplet (3) as two radical electrons alike and writes the triplet back, so this reads the TEXT. The structure
    `ChemistryEngine.set_structure_from_molblock` stores keeps the singlet code (`molblock_keeping_spin`), so the drawing's multiplicity survives
    undo, redo and the project file with no field of its own.
    """
    codes = rad_codes(molblock or "")
    if not codes:
        return None
    return 1 + sum(_RAD_UNPAIRED.get(code, 0) for code in codes.values())


def molblock_keeping_spin(written: str, original: str) -> str:
    """`written` (RDKit's molfile for a structure) with the singlet codes `original` carried put back, since RDKit rewrites a singlet as a triplet."""
    singlets = {index for index, code in rad_codes(original).items() if code == 1}
    if not singlets:
        return written
    codes = rad_codes(written)
    patched = {index: (1 if index in singlets and code == 3 else code) for index, code in codes.items()}
    if patched == codes:
        return written
    out, done = [], False
    for line in written.splitlines(keepends=True):
        if _RAD_LINE.match(line.rstrip("\r\n")):
            if not done:
                items = sorted(patched.items())
                for start in range(0, len(items), 8):
                    chunk = items[start:start + 8]
                    out.append(f"M  RAD{len(chunk):3d}" + "".join(f" {index + 1:3d} {code:3d}" for index, code in chunk) + "\n")
                done = True
            continue
        out.append(line)
    return "".join(out)


def default_multiplicity(mol: Chem.Mol) -> int:
    """The multiplicity a job starts from: high-spin for drawn radicals (2S+1, one electron per spin), 3 for a listed triplet drawn closed-shell, else 1."""
    unpaired = unpaired_electrons(mol)
    if unpaired:
        return unpaired + 1
    # No RemoveHs: it sanitises, and a held hypervalent Mol (ClF3) is not sanitisable. Only a two-atom molecule can be in the table.
    if mol.GetNumAtoms() == 2 and Chem.GetFormalCharge(mol) == 0:
        try:
            if Chem.MolToSmiles(mol) in TRIPLET_GROUND_STATES:
                return 3
        except Exception:  # noqa: BLE001 - an unreadable structure has no table entry
            return 1
    return 1


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


def spin_note(mol: Chem.Mol, multiplicity: int, drawn_multiplicity: int | None = None) -> str:
    """A caution when the multiplicity chosen does not match the radicals drawn, or "" when it does.

    Said, not refused: a person may want the open-shell singlet or a low-spin state. What is measured is that the
    mismatch is silent: O2 and CH2 at multiplicity 1 ran and finished, 39.7 and 41.9 kcal/mol above the triplet.
    """
    unpaired = unpaired_electrons(mol)
    if drawn_multiplicity is not None:
        # The drawing's own statement (`spin_from_molblock`) wins over RDKit's count, which cannot tell a singlet carbene from a triplet one.
        unpaired = drawn_multiplicity - 1
        if unpaired == 0 and multiplicity == 1:
            return ""
    if unpaired == 0:
        if default_multiplicity(mol) == 3 and multiplicity == 1:
            return "This molecule's ground state is a triplet (multiplicity 3); multiplicity 1 runs a higher-energy closed-shell state."
        return ""
    if multiplicity == unpaired + 1:
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
