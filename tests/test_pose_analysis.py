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


# --- The receptor the analysis sees must be the receptor that was docked ---

# Column-exact PDB. A protein residue, a water, and a co-crystallised
# ligand -- the three cases receptor preparation treats differently.
# Modelled on 4DKL, where this bug was found: docking naloxone into the
# mu-opioid receptor with stripping on reported 195 clashes and hydrogen
# bonds to BF0601 and HOH718, none of which Vina had been given.
MIXED_RECEPTOR_PDB = """HEADER    TEST
ATOM      1  N   ASP A 147      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  OD1 ASP A 147      11.999  12.040   2.945  1.00 20.00           O
HETATM    3  O   HOH A 718      13.398  12.442   2.508  1.00 20.00           O
HETATM    4  C1  BF0 A 601      13.598  13.601   2.128  1.00 20.00           C
HETATM    5  ZN   ZN A 900      14.100  14.100   2.100  1.00 20.00          ZN
END
"""


def _residues(atoms):
    return {atom.residue_name for atom in atoms}


def test_without_prep_options_the_whole_structure_is_parsed():
    """The default must not silently strip anything -- a receptor handed
    over unprepared is analysed as it stands."""
    atoms = receptor_atoms_from_structure(MIXED_RECEPTOR_PDB, "pdb")

    assert _residues(atoms) == {"ASP", "HOH", "BF0", "ZN"}


def test_stripped_waters_and_cofactors_are_absent_from_the_analysis():
    atoms = receptor_atoms_from_structure(
        MIXED_RECEPTOR_PDB, "pdb", {"strip_waters": True, "strip_cofactors": True}
    )

    assert _residues(atoms) == {"ASP"}, "only standard protein residues survive both strips"


def test_stripping_waters_alone_keeps_the_cofactor():
    """The two options are independent -- a metal or co-crystal ligand a
    user deliberately kept must still be there to interact with."""
    atoms = receptor_atoms_from_structure(
        MIXED_RECEPTOR_PDB, "pdb", {"strip_waters": True, "strip_cofactors": False}
    )

    assert _residues(atoms) == {"ASP", "BF0", "ZN"}


def test_an_interaction_is_not_reported_against_a_stripped_ligand():
    """The actual defect, end to end. A pose sitting on top of the
    co-crystallised ligand's position must report nothing there once that
    ligand has been stripped -- previously it reported a clash and an
    H-bond against an atom the docking never saw."""
    molblock = _make_ligand_molblock([("N", (13.598, 13.601, 2.128))])
    options = {"strip_waters": True, "strip_cofactors": True}

    unprepared = analyze_pose(
        molblock, receptor_atoms_from_structure(MIXED_RECEPTOR_PDB, "pdb")
    )
    prepared = analyze_pose(
        molblock, receptor_atoms_from_structure(MIXED_RECEPTOR_PDB, "pdb", options)
    )

    assert any(c["receptor_residue"] == "BF0601" for c in unprepared["clashes"])
    assert not any(c["receptor_residue"] == "BF0601" for c in prepared["clashes"])
    assert not any(h["receptor_residue"] == "HOH718" for h in prepared["hbonds"])


def test_both_strippers_agree_on_what_counts_as_removable():
    """`docking_providers` deletes residues before docking and
    `pose_analysis` skips them before analysis. They must reach the same
    verdict, so they share the predicate rather than each holding a copy
    of the residue tables."""
    from openchem.chem import docking_providers, pose_analysis

    assert docking_providers.is_stripped_residue is pose_analysis.is_stripped_residue
    assert pose_analysis.is_stripped_residue("HOH", True, False) is True
    assert pose_analysis.is_stripped_residue("HOH", False, True) is False, (
        "a water is a water, not a cofactor -- strip_cofactors must not take it"
    )
    assert pose_analysis.is_stripped_residue("ASP", True, True) is False
    assert pose_analysis.is_stripped_residue("BF0", False, True) is True


# --- multi-chain receptors: every subunit must be seen ---

def _tyr_ring(chain, resnum, x, y, z):
    """One complete tyrosine ring, offset to (x, y, z). All six ring atom
    names present, since a partly resolved ring is deliberately skipped."""
    ring = [("CG", 0.0, 0.0, 0.0), ("CD1", 1.4, 0.0, 0.0), ("CD2", 0.7, 1.2, 0.0),
            ("CE1", 2.1, 1.2, 0.0), ("CE2", 1.4, 2.4, 0.0), ("CZ", 2.8, 2.4, 0.0)]
    return "".join(
        f"ATOM  {i + 1:>5d} {name:<4} TYR {chain}{resnum:>4d}    "
        f"{x + dx:>8.3f}{y + dy:>8.3f}{z + dz:>8.3f}  1.00 20.00           C\n"
        for i, (name, dx, dy, dz) in enumerate(ring)
    )


# Four subunits of a homotetramer, each with TYR652 -- identical residue
# name and number, distinguished only by chain. This is hERG's
# arrangement, and 8ZYO is where the bug was found.
TETRAMER_PDB = (
    "HEADER    TEST\n"
    + _tyr_ring("A", 652, 0.0, 0.0, 0.0)
    + _tyr_ring("B", 652, 20.0, 0.0, 0.0)
    + _tyr_ring("C", 652, 40.0, 0.0, 0.0)
    + _tyr_ring("D", 652, 60.0, 0.0, 0.0)
    + "END\n"
)


def test_every_subunit_of_a_multimer_is_detected():
    """Residues were grouped by (name, number) with no chain, so all four
    subunits merged into one -- and because the grouping then indexes
    atoms BY NAME, the last chain read silently overwrote the other
    three. Three quarters of a homotetramer's aromatic rings and charge
    sites did not exist as far as the interaction analysis was concerned.
    Measured on 8ZYO: 34 rings found before, 121 after.
    """
    from openchem.chem.pose_analysis import receptor_features

    atoms = receptor_atoms_from_structure(TETRAMER_PDB, "pdb")
    features = receptor_features(atoms)

    rings = [g for g in features["rings"] if g.residue == "TYR652"]
    assert len(rings) == 4, "one ring centroid per subunit, not one in total"
    assert {g.chain for g in rings} == {"A", "B", "C", "D"}


def test_each_subunits_centroid_is_on_its_own_ring():
    """The failure mode that matters. A merged group does not just lose
    count -- it puts the centroid somewhere no ring is, so pi-stacking is
    measured against a phantom point."""
    from openchem.chem.pose_analysis import receptor_features

    features = receptor_features(receptor_atoms_from_structure(TETRAMER_PDB, "pdb"))
    by_chain = {g.chain: g.position for g in features["rings"] if g.residue == "TYR652"}

    # Rings were placed 20 A apart along x, so each centroid must sit near
    # its own subunit's offset and nowhere near the others.
    for chain, expected_x in (("A", 0.0), ("B", 20.0), ("C", 40.0), ("D", 60.0)):
        assert by_chain[chain][0] == pytest.approx(expected_x + 1.4, abs=0.5)


def test_the_chain_is_reported_alongside_each_contact():
    """`receptor_residue` stays NAME+NUMBER because `ui/visualization.py`
    matches it against Mol*'s auth_seq_id -- so the chain rides alongside
    rather than being folded into the label."""
    # An apolar carbon 3 A above chain A's CG -- inside the 4.5 A
    # hydrophobic cutoff, and CG is apolar in tyrosine (only CZ carries
    # the hydroxyl), so this is a real contact rather than a contrived one.
    molblock = _make_ligand_molblock([("C", (0.0, 0.0, 3.0))])

    found = analyze_pose(molblock, receptor_atoms_from_structure(TETRAMER_PDB, "pdb"))

    contacts = [c for entries in found.values() for c in entries]
    assert contacts, "the ligand is placed on chain A's ring"
    assert all("receptor_chain" in c for c in contacts)
    assert any(c["receptor_chain"] == "A" for c in contacts)
    assert all(c["receptor_residue"] == "TYR652" for c in contacts), (
        "the Mol*-facing label must not gain a chain suffix"
    )
