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


# --- mmCIF alternate locations -------------------------------------------

# A minimal but real-shaped atom_site loop. The tag order is the one RCSB
# actually writes, with label_alt_id fifth -- but the filter reads the
# position from the header rather than assuming it, and
# `test_the_altloc_column_is_read_from_the_header` moves it to prove that.
MMCIF_WITH_ALTLOCS = """data_TEST
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
ATOM   1 N N   . MET A 1.000 2.000 3.000
ATOM   2 C CA  A MET A 4.000 5.000 6.000
ATOM   3 C CA  B MET A 4.500 5.500 6.500
HETATM 4 O O1  A LIG B 7.000 8.000 9.000
HETATM 5 O O1  B LIG B 7.500 8.500 9.500
HETATM 6 C C1  ? LIG B 1.000 1.000 1.000
#
"""


def _coordinate_rows(text: str) -> list[str]:
    return [
        line for line in text.splitlines()
        if line.startswith(("ATOM", "HETATM"))
    ]


def test_only_the_first_alternate_location_survives_in_mmcif():
    """The bug this fixes. An mmCIF receptor reached Vina with its atoms
    doubled wherever a side chain was modelled in two states, which
    double-counts the steric term and is reported by nothing."""
    from openchem.chem.pose_analysis import filter_mmcif_altlocs

    kept = _coordinate_rows(filter_mmcif_altlocs(MMCIF_WITH_ALTLOCS))

    assert len(kept) == 4, kept
    assert not any(" B MET " in row or " B LIG " in row for row in kept)
    assert any(" A MET " in row for row in kept), "conformation A is the one kept"


def test_unset_and_unknown_altlocs_are_kept():
    """`.` and `?` mean 'no alternate location', not 'alternate B'. An
    atom with either must never be dropped -- that is most of the file."""
    from openchem.chem.pose_analysis import filter_mmcif_altlocs

    kept = _coordinate_rows(filter_mmcif_altlocs(MMCIF_WITH_ALTLOCS))

    assert any(row.startswith("ATOM   1") for row in kept), "'.' kept"
    assert any(row.startswith("HETATM 6") for row in kept), "'?' kept"


def test_the_altloc_column_is_read_from_the_header_not_assumed():
    """Tag order is a convention, not a rule. A file that declares
    label_alt_id somewhere else must still be filtered correctly, and a
    hardcoded index would silently test the wrong field."""
    from openchem.chem.pose_analysis import filter_mmcif_altlocs

    reordered = """data_TEST
loop_
_atom_site.group_PDB
_atom_site.label_alt_id
_atom_site.id
_atom_site.label_comp_id
ATOM . 1 MET
ATOM A 2 MET
ATOM B 3 MET
#
"""
    kept = _coordinate_rows(filter_mmcif_altlocs(reordered))

    assert len(kept) == 2
    assert not any(row.startswith("ATOM B") for row in kept)


def test_a_quoted_value_containing_a_space_does_not_shift_the_columns():
    """Why the tokenizer is not a plain split. mmCIF permits quoted values,
    and one containing whitespace moves every later field along by one --
    putting the altloc check on the wrong column and dropping atoms at
    random. Nucleic-acid atom names are written `"O5'"` for the same
    quoting reason."""
    from openchem.chem.pose_analysis import filter_mmcif_altlocs

    quoted = """data_TEST
loop_
_atom_site.group_PDB
_atom_site.label_comp_id
_atom_site.label_alt_id
_atom_site.id
ATOM 'MY RESIDUE' . 1
ATOM 'MY RESIDUE' A 2
ATOM 'MY RESIDUE' B 3
#
"""
    kept = _coordinate_rows(filter_mmcif_altlocs(quoted))

    assert len(kept) == 2, f"a naive split would mis-index and keep {len(kept)}"
    assert not any(row.endswith(" 3") for row in kept)


def test_a_loop_without_alternate_locations_is_untouched():
    from openchem.chem.pose_analysis import filter_mmcif_altlocs

    plain = """data_TEST
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.label_comp_id
ATOM 1 MET
ATOM 2 GLY
#
"""
    assert filter_mmcif_altlocs(plain) == plain


def test_other_categories_pass_through_unchanged():
    """Only the atom_site loop is filtered. A citation or author loop with
    a value that happens to look like an altloc must survive intact."""
    from openchem.chem.pose_analysis import filter_mmcif_altlocs

    result = filter_mmcif_altlocs(MMCIF_WITH_ALTLOCS)

    assert result.startswith("data_TEST")
    assert "_atom_site.label_alt_id" in result, "the header itself is preserved"


def test_the_filter_dispatches_on_format():
    """One entry point, so receptor preparation and pose analysis cannot
    disagree about a format -- which is exactly how the PDB-only version
    ended up applied on one path and not the other."""
    from openchem.chem.pose_analysis import filter_altlocs

    assert len(_coordinate_rows(filter_altlocs(MMCIF_WITH_ALTLOCS, "mmcif"))) == 4
    assert len(_coordinate_rows(filter_altlocs(MMCIF_WITH_ALTLOCS, "cif"))) == 4
    # A PDB filter applied to mmCIF text would do nothing useful; the
    # dispatcher must not confuse them.
    assert filter_altlocs(MMCIF_WITH_ALTLOCS, "pdb") == MMCIF_WITH_ALTLOCS
    assert filter_altlocs("anything", "sdf") == "anything"


def test_mmcif_altlocs_are_gone_by_the_time_atoms_are_parsed():
    """End to end through the real parser, which is where it matters."""
    atoms = receptor_atoms_from_structure(MMCIF_WITH_ALTLOCS, "mmcif")

    assert len(atoms) == 4


# --- The box-defining ligand must not be left in the box ----------------


def test_a_named_ligand_code_is_stripped_regardless_of_the_cofactor_flag():
    """MEASURED against real Vina 1.2.7 on real 1HSG, everything identical
    except this option:

        indinavir, 1HSG's OWN co-crystallised ligand   -5.34  ->  -9.75
        benzene                                        -2.97  ->  -4.09
        wall clock                                     65.6s  ->  28.3s

    The receptor library derives every binding-site box from a
    co-crystallised ligand and, before this, left that ligand sitting in
    the pocket the box describes -- so docking searched an occupied site,
    scored the native ligand 4.4 kcal/mol too weak, and ran SLOWER for it.
    """
    from openchem.chem.pose_analysis import is_stripped_residue

    assert is_stripped_residue("MK1", True, False) is False
    assert is_stripped_residue("MK1", True, False, ["MK1"]) is True


def test_naming_a_ligand_does_not_strip_genuine_cofactors():
    """Why this is not just `strip_cofactors=True`. That flag also removes
    haem, catalytic zinc and the rest, which are genuinely part of a site
    and must stay by default. Only the named residue goes."""
    from openchem.chem.pose_analysis import is_stripped_residue

    assert is_stripped_residue("HEM", True, False, ["MK1"]) is False
    assert is_stripped_residue("ZN", True, False, ["MK1"]) is False
    assert is_stripped_residue("ALA", True, False, ["MK1"]) is False


def test_ligand_codes_match_case_and_padding_insensitively():
    """PDB residue names arrive space-padded and in mixed case depending on
    the writer."""
    from openchem.chem.pose_analysis import is_stripped_residue

    assert is_stripped_residue(" mk1 ", True, False, ["MK1"]) is True
    assert is_stripped_residue("MK1", True, False, [" mk1 "]) is True


def test_empty_ligand_codes_change_nothing():
    from openchem.chem.pose_analysis import is_stripped_residue

    assert is_stripped_residue("MK1", True, False, []) is False
    assert is_stripped_residue("MK1", True, False, ["", None]) is False


# --- mmCIF element symbols ------------------------------------------------

#: A PDB-format receptor carrying a zinc, for the control half of the
#: asymmetry: the same element, the reader that was never wrong.
RECEPTOR_PDB_WITH_ZINC = (
    "HEADER    TEST\n"
    "ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N\n"
    "HETATM    2 ZN   ZN  A   2      25.000  25.000  25.000  1.00 20.00          ZN\n"
    "END\n"
)


def _mmcif_with_symbol(symbol: str, comp: str = "LIG") -> str:
    """One atom, in the atom_site tag order RCSB actually writes.

    `type_symbol` is passed in verbatim so a test can put an UPPERCASE
    two-letter element there -- which is what the archive writes, and the
    whole bug.
    """
    return f"""data_TEST
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.pdbx_formal_charge
_atom_site.auth_seq_id
_atom_site.auth_comp_id
_atom_site.auth_asym_id
_atom_site.auth_atom_id
_atom_site.pdbx_PDB_model_num
HETATM 1 {symbol} {symbol} . {comp} A 1 . ? 0.000 0.000 0.000 1.00 20.00 ? 1 {comp} A {symbol} 1
#
"""


#: Every two-letter element the PDB archive routinely writes uppercase,
#: with the atomic number it must come back as. Not a sample -- the
#: reader's lookup is case-sensitive, so this is the whole class, and the
#: eight the bug was first reported for were only the ones somebody
#: happened to name.
TWO_LETTER_SYMBOLS = [
    ("ZN", "ZN"), ("FE", "FE"), ("MG", "MG"), ("MN", "MN"),
    ("CU", "CU"), ("CL", "CL"), ("BR", "BR"), ("SE", "SE"),
    ("CA", "CA"), ("NA", "NA"), ("NI", "NI"), ("CO", "CO"),
]


@pytest.mark.parametrize("symbol,expected", TWO_LETTER_SYMBOLS)
def test_an_uppercase_two_letter_element_keeps_its_identity(symbol, expected):
    """THE BUG. Open Babel's mmCIF reader matches `type_symbol` case
    sensitively while the archive writes `CL`, so every two-letter element
    arrived as atomic number 0 -- element unknown -- and was then removed
    by the `atomicnum == 0` skip. A zinc metalloprotease imported as
    mmCIF silently lost its catalytic zinc; measured over the bundled
    catalogue in mmCIF form, 30 atoms across 16 of the 49 receptors.

    Read through `receptor_atoms_from_structure`, not through the string
    transform, because the claim is about what the READER produces.
    """
    from openchem.chem.pose_analysis import receptor_atoms_from_structure

    atoms = receptor_atoms_from_structure(_mmcif_with_symbol(symbol), "mmcif")

    assert len(atoms) == 1, f"{symbol} was dropped entirely, not merely mistyped"
    assert atoms[0].element == expected


@pytest.mark.parametrize("symbol", ["C", "N", "O", "S", "P", "F", "W", "I"])
def test_a_one_letter_element_is_left_exactly_as_written(symbol):
    """One-letter symbols were never broken -- case cannot differ -- so
    normalising must not touch them. `W` and `I` are here deliberately:
    both are real one-letter elements, and a rule keyed on token length
    rather than on the symbol table would mangle them."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    text = _mmcif_with_symbol(symbol)

    assert normalise_mmcif_element_symbols(text) == text


def test_an_already_correct_symbol_is_not_rewritten():
    """A file written `Cl` is already right, and rewriting it would be
    churn a byte comparison downstream would notice."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    text = _mmcif_with_symbol("Cl")

    assert normalise_mmcif_element_symbols(text) == text


def test_nothing_but_the_element_column_changes():
    """The load-bearing constraint. `CL` appears three MORE times in the
    same row here -- as the atom name, the residue name and the auth atom
    name -- exactly as it does in a real deposit, so a normaliser that
    rewrote any other field would corrupt the structure while still
    reporting the right element."""
    from openchem.chem.pose_analysis import _cif_tokens, normalise_mmcif_element_symbols

    text = _mmcif_with_symbol("CL", comp="CL")
    result = normalise_mmcif_element_symbols(text)

    assert len(result) == len(text), "case never changes length; alignment must survive"
    before = _cif_tokens(text.splitlines()[-2])
    after = _cif_tokens(result.splitlines()[-2])
    assert before[2] == "CL", "the fixture really did start uppercase"
    assert after[2] == "Cl", "the type_symbol is normalised"
    assert before[:2] == after[:2] and before[3:] == after[3:], (
        f"only the element column may change, got {before} -> {after}"
    )
    # label_atom_id, label_comp_id, auth_comp_id, auth_atom_id.
    assert after.count("CL") == 4, "atom, residue and auth names all untouched"


def test_an_element_in_the_last_column_is_normalised_too():
    """The case that caught a real bug in the tokeniser. Splitting on
    space and tab alone folds the line terminator into the row's FINAL
    token, so `type_symbol` declared last read as `"NA\\n"` and matched no
    element -- while every fixture with a column after it passed. RCSB
    puts `pdbx_PDB_model_num` last, so the shape that fails is exactly the
    one a hand-written or trimmed file has."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    last = """data_TEST
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
HETATM 1 NA
#
"""
    assert "HETATM 1 Na" in normalise_mmcif_element_symbols(last)


def test_a_windows_line_ending_does_not_hide_the_last_column():
    """`structure_io` decodes bytes itself rather than going through
    universal newlines, so a CRLF deposit reaches the tokeniser with its
    `\\r` intact -- which folds into the last token the same way."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    crlf = (
        "data_TEST\r\nloop_\r\n_atom_site.group_PDB\r\n_atom_site.id\r\n"
        "_atom_site.type_symbol\r\nHETATM 1 ZN\r\n#\r\n"
    )
    result = normalise_mmcif_element_symbols(crlf)

    assert "HETATM 1 Zn\r\n" in result, repr(result)


def test_the_element_column_is_read_from_the_header_not_assumed():
    """Tag order is a convention, not a rule. A hardcoded index would
    normalise some other field, and every value it then failed to
    recognise would pass through -- so the damage stays invisible on any
    file whose columns happen to sit where RCSB puts them."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    reordered = """data_TEST
loop_
_atom_site.group_PDB
_atom_site.label_comp_id
_atom_site.id
_atom_site.type_symbol
HETATM NA 1 NA
#
"""
    result = normalise_mmcif_element_symbols(reordered)

    assert "HETATM NA 1 Na" in result, result


def test_a_quoted_element_row_does_not_shift_the_columns():
    """Same reason the altloc filter tokenises rather than splitting: a
    quoted value containing whitespace moves every later field along by
    one, and the element check would then land on the wrong column."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    quoted = """data_TEST
loop_
_atom_site.group_PDB
_atom_site.label_comp_id
_atom_site.type_symbol
_atom_site.id
HETATM 'MY RESIDUE' ZN 1
#
"""
    result = normalise_mmcif_element_symbols(quoted)

    assert "'MY RESIDUE' Zn 1" in result, f"a naive split would mis-index: {result}"


@pytest.mark.parametrize("value", ["?", ".", "XX", "Unl", "D"])
def test_an_unrecognised_element_value_is_left_alone(value):
    """Only a value that IS an element once normalised is rewritten. `?`
    and `.` are mmCIF's own placeholders, `D` is deuterium (which the
    element table does not carry), `XX` is nothing at all -- guessing at
    any of them would invent an element the file never claimed."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    text = _mmcif_with_symbol(value)

    assert normalise_mmcif_element_symbols(text) == text


def test_another_categorys_type_symbol_column_is_not_rewritten():
    """`_atom_site` is not the only mmCIF category with a `type_symbol`.
    `_chem_comp_atom.type_symbol` is the chemical component dictionary's,
    and a real deposit can carry it -- so the tag lookup must be an EXACT
    match and not a suffix one. Open Babel types atoms from coordinates
    alone, so the coordinate loop is the only thing worth touching."""
    from openchem.chem.pose_analysis import normalise_mmcif_element_symbols

    other = """data_TEST
loop_
_chem_comp_atom.comp_id
_chem_comp_atom.atom_id
_chem_comp_atom.type_symbol
CL CL CL
ZN ZN ZN
#
"""
    assert normalise_mmcif_element_symbols(other) == other


def test_pdb_text_is_returned_unchanged():
    """The PDB reader already matches case-insensitively -- measured on
    the same twelve symbols -- so normalising it would be a rewrite with
    no defect behind it.

    HONEST LIMIT: this test cannot fail today, and mutation testing said
    so -- deleting the format check leaves it green. The mmCIF walker is
    inert on PDB text (it needs a bare `loop_` line followed by
    `_atom_site.type_symbol`, which no PDB file has), so the dispatch is
    a guard against cost and against a future third format, not against a
    reachable corruption. Kept as the statement of intent, deliberately
    not propped up with a fixture no real file resembles."""
    from openchem.chem.pose_analysis import normalise_element_symbols

    assert normalise_element_symbols(RECEPTOR_PDB_WITH_ZINC, "pdb") == RECEPTOR_PDB_WITH_ZINC


def test_open_babel_really_does_lose_an_uppercase_symbol_without_the_fix():
    """Asserts the DEFECT, on purpose, so the workaround has an expiry.

    `normalise_mmcif_element_symbols` only earns its place while Open
    Babel's mmCIF reader is case-sensitive. If a future version stops
    losing `CL`, this fails, the normalisation and its two call sites can
    go, and nobody has to rediscover why they were there. The PDB half is
    the control: same element, a reader that was never wrong.
    """
    from openbabel import pybel

    mmcif = pybel.readstring("mmcif", _mmcif_with_symbol("CL"))
    assert [a.atomicnum for a in mmcif.atoms] == [0], (
        "Open Babel now reads uppercase mmCIF elements -- delete the workaround"
    )

    pdb = pybel.readstring("pdb", RECEPTOR_PDB_WITH_ZINC)
    assert 30 in [a.atomicnum for a in pdb.atoms], "PDB was never affected"
