from __future__ import annotations

from rdkit import Chem

from openchem.chem.pose_analysis import ReceptorAtom, analyze_pose, receptor_atoms_from_structure

RECEPTOR_PDB = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
END
"""


def _make_ligand_molblock(atoms: list[tuple[str, tuple[float, float, float]]]) -> str:
    """A minimal molblock with only atom positions -- pose_analysis reads
    element + 3D position only, never bonding, so no bonds are needed."""
    mol = Chem.RWMol()
    for symbol, _pos in atoms:
        mol.AddAtom(Chem.Atom(symbol))
    conformer = Chem.Conformer(mol.GetNumAtoms())
    for i, (_symbol, pos) in enumerate(atoms):
        conformer.SetAtomPosition(i, pos)
    mol.AddConformer(conformer)
    return Chem.MolToMolBlock(mol.GetMol(), kekulize=False)


def test_receptor_atoms_from_structure_parses_real_pdb():
    atoms = receptor_atoms_from_structure(RECEPTOR_PDB, "pdb")

    assert len(atoms) == 4
    elements = {atom.element for atom in atoms}
    assert elements == {"N", "C", "O"}
    oxygen = next(atom for atom in atoms if atom.element == "O")
    assert oxygen.position == (13.598, 13.601, 2.128)
    assert oxygen.residue_name == "ALA"


def test_analyze_pose_detects_hbond_within_cutoff():
    # Receptor oxygen at the origin; ligand nitrogen 3.0 A away -- well
    # within the 3.5 A polar-contact cutoff.
    receptor_atoms = [ReceptorAtom(element="O", position=(0.0, 0.0, 0.0), residue_name="ALA", residue_number=1)]
    molblock = _make_ligand_molblock([("N", (3.0, 0.0, 0.0))])

    result = analyze_pose(molblock, receptor_atoms)

    assert len(result["hbonds"]) == 1
    hbond = result["hbonds"][0]
    assert hbond["ligand_element"] == "N"
    assert hbond["receptor_element"] == "O"
    assert hbond["distance"] == 3.0
    assert result["clashes"] == []


def test_analyze_pose_does_not_flag_hbond_beyond_cutoff():
    receptor_atoms = [ReceptorAtom(element="O", position=(0.0, 0.0, 0.0), residue_name="ALA", residue_number=1)]
    molblock = _make_ligand_molblock([("N", (5.0, 0.0, 0.0))])  # beyond 3.5 A

    result = analyze_pose(molblock, receptor_atoms)

    assert result["hbonds"] == []


def test_analyze_pose_ignores_nonpolar_atoms_for_hbonds():
    # Two carbons close enough to be a polar contact distance-wise, but
    # neither is N/O/F -- must not be flagged as an hbond.
    receptor_atoms = [ReceptorAtom(element="C", position=(0.0, 0.0, 0.0), residue_name="ALA", residue_number=1)]
    molblock = _make_ligand_molblock([("C", (3.0, 0.0, 0.0))])

    result = analyze_pose(molblock, receptor_atoms)

    assert result["hbonds"] == []


def test_analyze_pose_detects_steric_clash():
    # Two carbons (vdW radius 1.70 each) 1.0 A apart -- well inside
    # 1.70 + 1.70 - 0.4 = 3.0 A, a clear clash.
    receptor_atoms = [ReceptorAtom(element="C", position=(0.0, 0.0, 0.0), residue_name="ALA", residue_number=1)]
    molblock = _make_ligand_molblock([("C", (1.0, 0.0, 0.0))])

    result = analyze_pose(molblock, receptor_atoms)

    assert len(result["clashes"]) == 1
    assert result["clashes"][0]["distance"] == 1.0


def test_analyze_pose_clean_pose_has_no_hbonds_or_clashes():
    receptor_atoms = [ReceptorAtom(element="C", position=(0.0, 0.0, 0.0), residue_name="ALA", residue_number=1)]
    molblock = _make_ligand_molblock([("C", (10.0, 0.0, 0.0))])  # far away, no contact at all

    result = analyze_pose(molblock, receptor_atoms)

    assert result == {"hbonds": [], "clashes": []}
