from __future__ import annotations

import pytest
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

    # Every interaction type, not just the original two -- asserting the
    # exact key set would have to be edited each time one is added, which
    # is churn that proves nothing.
    assert all(entries == [] for entries in result.values()), result


# --- Interaction depth beyond hydrogen bonds and clashes -----------------


def _pdb(rows) -> str:
    """Column-exact PDB. The atom name must land in columns 13-16 and the
    residue name in 18-20, or Open Babel silently reads "LYS" as "YS1" --
    which cost a debugging round when these tests were written."""
    lines = [
        f"ATOM  {index:5d}  {name:<3s} {residue:>3s} A{number:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2s}"
        for index, (name, residue, number, x, y, z, element) in enumerate(rows, 1)
    ]
    return "\n".join(lines) + "\nEND\n"


_PHE_RING = [
    ("CG", -1.4, 0.0), ("CD1", -0.7, 1.2), ("CD2", -0.7, -1.2),
    ("CE1", 0.7, 1.2), ("CE2", 0.7, -1.2), ("CZ", 1.4, 0.0),
]


def _benzoate_at_origin() -> str:
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1C(=O)[O-]"))
    AllChem.EmbedMolecule(mol, randomSeed=3)
    AllChem.MMFFOptimizeMolecule(mol)
    conformer = mol.GetConformer()
    centre = [
        sum(conformer.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())) / mol.GetNumAtoms(),
        sum(conformer.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())) / mol.GetNumAtoms(),
        sum(conformer.GetAtomPosition(i).z for i in range(mol.GetNumAtoms())) / mol.GetNumAtoms(),
    ]
    for i in range(mol.GetNumAtoms()):
        p = conformer.GetAtomPosition(i)
        conformer.SetAtomPosition(i, (p.x - centre[0], p.y - centre[1], p.z - centre[2]))
    return Chem.MolToMolBlock(mol)


def test_the_residue_number_is_the_files_own_not_open_babels_index():
    """A real bug, found while adding the detectors below. `residue.idx`
    is an internal 0-based counter, so a PDB's LYS 128 was reported as
    LYS1 -- and `ui/visualization.py` turns that label into a Mol*
    selection matched against `auth_seq_id`, the file's numbering. The
    binding-site colouring was highlighting the wrong residues."""
    atoms = receptor_atoms_from_structure(
        _pdb([("N", "PHE", 57, 0.0, 0.0, 0.0, "N"), ("NZ", "LYS", 128, 5.0, 0.0, 0.0, "N")]), "pdb"
    )

    assert [f"{a.residue_name}{a.residue_number}" for a in atoms] == ["PHE57", "LYS128"]


def test_atom_names_are_carried_through_because_geometry_needs_them():
    atoms = receptor_atoms_from_structure(
        _pdb([("CD1", "PHE", 57, 0.0, 0.0, 0.0, "C")]), "pdb"
    )

    assert atoms[0].atom_name == "CD1"


def test_a_ring_centroid_uses_the_ring_atoms_not_the_whole_residue():
    """CA and CB are in the residue but not the ring. Including them drags
    the centroid off the ring plane and every ring-based distance with
    it -- here to 13.5 instead of the true 14.4."""
    from openchem.chem.pose_analysis import receptor_features

    rows = [("CA", "PHE", 1, 11.0, 10.0, 10.0, "C"), ("CB", "PHE", 1, 12.0, 10.0, 10.0, "C")]
    rows += [(name, "PHE", 1, 14.4 + x, 10.0 + y, 10.0, "C") for name, x, y in _PHE_RING]

    rings = receptor_features(receptor_atoms_from_structure(_pdb(rows), "pdb"))["rings"]

    assert len(rings) == 1
    assert rings[0].position[0] == pytest.approx(14.4, abs=0.01)


def test_a_partly_resolved_ring_is_skipped_rather_than_averaged():
    """Three atoms of a phenylalanine ring give a centroid that is not the
    ring's. Reporting it would be worse than reporting nothing."""
    from openchem.chem.pose_analysis import receptor_features

    rows = [(name, "PHE", 1, x, y, 0.0, "C") for name, x, y in _PHE_RING[:3]]

    assert receptor_features(receptor_atoms_from_structure(_pdb(rows), "pdb"))["rings"] == []


def test_pi_stacking_and_cation_pi_and_salt_bridges_are_all_found():
    """One constructed pose: benzoate at the origin, a PHE ring stacked
    4 A above it, a lysine NZ beside the carboxylate."""
    rows = [(name, "PHE", 1, x, y, 4.0, "C") for name, x, y in _PHE_RING]
    rows += [("NZ", "LYS", 2, 3.2, 0.0, 0.0, "N")]
    receptor = receptor_atoms_from_structure(_pdb(rows), "pdb")

    found = analyze_pose(_benzoate_at_origin(), receptor)

    assert len(found["pi_stacking"]) == 1
    assert found["pi_stacking"][0]["receptor_residue"] == "PHE1"
    assert found["pi_stacking"][0]["distance"] == pytest.approx(4.0, abs=0.5)
    assert found["salt_bridges"], "the carboxylate and NZ are 3.2 A apart"
    assert found["cation_pi"], "NZ sits over the ligand ring"
    assert found["hydrophobic"], "ring carbons face each other"


def test_a_salt_bridge_needs_opposite_charges():
    """An anionic ligand near an anionic residue is repulsion, not a
    bridge. Pairing like with like would report it as a favourable
    contact."""
    rows = [("OD1", "ASP", 1, 3.0, 0.0, 0.0, "O"), ("OD2", "ASP", 1, 3.0, 1.0, 0.0, "O")]
    receptor = receptor_atoms_from_structure(_pdb(rows), "pdb")

    assert analyze_pose(_benzoate_at_origin(), receptor)["salt_bridges"] == []


def test_metal_coordination_is_found_only_within_bonding_range():
    from openchem.chem.pose_analysis import METAL_COORDINATION_CUTOFF

    close = _pdb([("ZN", "ZN", 1, 2.0, 0.0, 0.0, "ZN")])
    far = _pdb([("ZN", "ZN", 1, 8.0, 0.0, 0.0, "ZN")])
    pose = _benzoate_at_origin()

    assert METAL_COORDINATION_CUTOFF < 3.0
    assert analyze_pose(pose, receptor_atoms_from_structure(close, "pdb"))["metal_coordination"]
    assert analyze_pose(pose, receptor_atoms_from_structure(far, "pdb"))["metal_coordination"] == []


def test_a_distant_receptor_yields_every_interaction_type_empty():
    """The negative control. Everything must come back empty rather than
    a detector firing on nothing."""
    receptor = receptor_atoms_from_structure(
        _pdb([(name, "PHE", 1, x + 50.0, y, 0.0, "C") for name, x, y in _PHE_RING]), "pdb"
    )

    found = analyze_pose(_benzoate_at_origin(), receptor)

    assert all(entries == [] for entries in found.values()), found


def test_the_cutoffs_have_one_owner_across_both_analysers():
    """Intramolecular and intermolecular detection share these values --
    the physics does not change between one molecule and two -- and a
    second copy is how they would drift apart."""
    from openchem.chem import interaction_analysis, pose_analysis

    for name in ("SALT_BRIDGE_CUTOFF", "PI_STACKING_CUTOFF", "CATION_PI_CUTOFF",
                 "HYDROPHOBIC_CUTOFF"):
        assert getattr(pose_analysis, name) is getattr(interaction_analysis, name)
