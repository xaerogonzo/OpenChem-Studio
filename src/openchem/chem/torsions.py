"""The torsion table: every rotatable bond of a conformer, with the dihedral angle about it.

`Rotatable Bonds` in Properties is a COUNT. This lists which bonds make it up and the angle at each
in the conformer on screen, so "flexible" can be read bond by bond. It is geometry, not a model: the
angle is a definition, and the only decisions are WHICH bonds and WHICH four atoms.

**WHICH BONDS: EXACTLY THE ONES THE COUNT COUNTS.** The count is RDKit's `CalcNumRotatableBonds` at
its default (strict) setting, which exposes no list of bonds, so the same definition is written out
below as a SMARTS pattern and `tests/test_torsions.py` holds it to the count over a corpus of
structures. A table that listed seven bonds beside a count of six would put two definitions of
"rotatable" on one screen, so the test is what keeps them one.

The pattern is matched on the HEAVY-ATOM graph. The count is taken on the drawing (implicit
hydrogens); a conformer carries explicit ones, which change every atom's degree and so decide a
terminal methyl differently (D1 on the drawing, D4 on the conformer). Hydrogens are removed from a
copy before matching and the matches mapped back, so the table agrees with the count whichever of the
two it is handed.

**WHICH FOUR ATOMS.** About a bond B-C the angle needs one neighbour of each end. Where there is a
choice the heaviest neighbour is taken, the lowest index among equals: a torsion through a hydrogen is
the least informative one and the least stable to report, and a rule that depends on atom order alone
would change when the drawing is renumbered. The four atoms are named on the result so nothing is left
to be guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import rdMolTransforms

from openchem.chem.calculator_options import decimals
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

#: The conditions on one END of a rotatable bond: not part of a triple bond, not terminal, and not a
#: trihalomethyl or tert-butyl carbon (a group that spins but whose spin changes nothing).
_END = (
    "!$(*#*)&!D1&!$(C(F)(F)F)&!$(C(Cl)(Cl)Cl)&!$(C(Br)(Br)Br)&!$(C([CH3])([CH3])[CH3])"
)
#: RDKit's strict rotatable-bond definition (the one `Lipinski.NumRotatableBonds` counts), as a SMARTS
#: pattern: a single, non-ring bond between two atoms that satisfy `_END`, and that are not the
#: amide-like C(=X)-N/O/S linkage RDKit treats as rigid. Held to RDKit's own count by
#: `tests/test_torsions.py`.
_ROTATABLE = Chem.MolFromSmarts(
    f"[{_END}&!$([CD3](=[N,O,S])-!@[#7,O,S!D1])&!$([#7,O,S!D1]-!@[CD3]=[N,O,S])"
    f"&!$([CD3](=[N+])-!@[#7!D1])&!$([#7!D1]-!@[CD3]=[N+])]-,:;!@[{_END}]"
)

#: The atom property that carries a conformer atom's own index through the hydrogen removal.
_INDEX = "_oc_torsion_index"


@dataclass(frozen=True)
class Torsion:
    """The dihedral about one rotatable bond."""

    #: The four atoms, in the conformer's own numbering: a bonded to b, b to c, c to d.
    atoms: tuple[int, int, int, int]
    #: The angle in degrees, in (-180, 180]; 180 is anti and 0 is syn.
    angle: float

    @property
    def bond(self) -> tuple[int, int]:
        return self.atoms[1], self.atoms[2]


def rotatable_bonds(mol: Chem.Mol) -> list[tuple[int, int]]:
    """The rotatable bonds of `mol`, as pairs of its own atom indices, lowest first.

    The same bonds `Lipinski.NumRotatableBonds` counts, found on the heavy-atom graph (see the
    module docstring).
    """
    marked = Chem.Mol(mol)
    for atom in marked.GetAtoms():
        atom.SetIntProp(_INDEX, atom.GetIdx())
    heavy = Chem.RemoveHs(marked, sanitize=False)
    heavy.UpdatePropertyCache(strict=False)
    Chem.FastFindRings(heavy)  # `!@` in the pattern reads ring membership, which sanitize=False left unset
    bonds = []
    for first, second in heavy.GetSubstructMatches(_ROTATABLE, uniquify=True):
        pair = (heavy.GetAtomWithIdx(first).GetIntProp(_INDEX), heavy.GetAtomWithIdx(second).GetIntProp(_INDEX))
        bonds.append((min(pair), max(pair)))
    return sorted(set(bonds))


def _outer_neighbour(mol: Chem.Mol, atom: int, other: int) -> int:
    """The neighbour of `atom` (not `other`) a torsion is measured through: heaviest, then lowest index.

    Every end of a rotatable bond has one: the pattern excludes terminal atoms, and a conformer's
    explicit hydrogens only add neighbours.
    """
    candidates = [n for n in mol.GetAtomWithIdx(atom).GetNeighbors() if n.GetIdx() != other]
    return min(candidates, key=lambda n: (-n.GetAtomicNum(), n.GetIdx())).GetIdx()


def torsions(mol: Chem.Mol) -> list[Torsion]:
    """One `Torsion` per rotatable bond of the conformer `mol` carries, in bond order.

    Raises ValueError when `mol` has no 3D conformer: an angle from flat 2D coordinates would be 0 or
    180 and mean nothing.
    """
    if mol.GetNumConformers() == 0 or not mol.GetConformer().Is3D():
        raise ValueError("A torsion needs a 3D conformer.")
    conformer = mol.GetConformer()
    found = []
    for b, c in rotatable_bonds(mol):
        a, d = _outer_neighbour(mol, b, c), _outer_neighbour(mol, c, b)
        angle = float(rdMolTransforms.GetDihedralDeg(conformer, a, b, c, d))
        # (-180, 180]: RDKit returns -180 for an exactly anti arrangement on some platforms.
        found.append(Torsion(atoms=(a, b, c, d), angle=180.0 if angle == -180.0 else angle))
    return found


def _atom_name(mol: Chem.Mol, index: int) -> str:
    """`C12`: the symbol and the drawing's own number, as the Atom Inspector and the pKa sites name atoms."""
    from openchem.chem.components import drawing_label

    return drawing_label(mol.GetAtomWithIdx(index))


def compute_torsion_table(mol: Chem.Mol, molecule_uuid: str, parameters: dict | None = None) -> ReportResult:
    """The "geometry" category's torsion table: a fact per rotatable bond, and the count they add up to."""
    places = decimals(parameters)
    provenance = Provenance(created_by="core", method="rdkit")
    try:
        found = torsions(mol)
    except ValueError as exc:
        return ReportResult(
            molecule_uuid=molecule_uuid,
            report_id="torsion_table",
            name="Torsion Table",
            category="geometry",
            cache_state=CacheState.FAILED,
            error=f"{exc} Generate one with Structure \u25b8 Generate Conformers... first.",
            provenance=provenance,
        )
    how = (
        "The dihedral about this bond in the conformer on screen, through the heaviest neighbour of "
        "each end (lowest atom number among equals); 180 is anti, 0 is syn, and the sign gives the "
        "handedness. A conformer is one point on the energy surface, not a scan: another conformer "
        "of the same molecule has other angles.",
    )
    facts = [
        Fact(
            category=FactCategory.GEOMETRY,
            label="Rotatable bonds",
            value=float(len(found)),
            display_value=str(len(found)),
            source="Torsion Table",
            basis=Basis.DETERMINISTIC,
            limitations=(
                "The bonds the Rotatable Bonds count in Properties counts (RDKit's strict definition): "
                "single, non-ring, between non-terminal atoms, with trihalomethyl, tert-butyl and "
                "amide-like linkages excluded.",
            ),
        )
    ]
    for torsion in found:
        a, b, c, d = torsion.atoms
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label=f"Torsion {_atom_name(mol, a)}-{_atom_name(mol, b)}-{_atom_name(mol, c)}-{_atom_name(mol, d)}",
                value=torsion.angle,
                display_value=f"{torsion.angle:.{places}f}",
                source="Torsion Table",
                basis=Basis.DETERMINISTIC,
                units="deg",
                limitations=how,
            )
        )
    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="torsion_table",
        name="Torsion Table",
        category="geometry",
        facts=tuple(facts),
        provenance=provenance,
    )
