"""RDKit to `LewisDiagram`: the chemistry, and what it declines to say.

The oracle below is HAND-AUTHORED from the electron budget, worked before
the builder was run. That direction matters: an expectation derived from
the implementation cannot catch a classifier bug, and this project has
already had an oracle written carelessly -- nitrate and carbonate went
into the plan as 4 delocalised electrons when both are 2.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.lewis_builder import ANALYSIS_VERSION, CROWDED_APPROACH, build, crowding
from openchem.chem.lewis_diagram import Known, Status, Unknown


def molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


#: valence electrons, localised PAIRS, delocalised ELECTRONS, lone PAIRS.
#: Each worked by hand: total = sum of group valence - total formal charge.
ORACLE = {
    "water": ("O", 8, 2, 0, 2),
    "ammonia": ("N", 8, 3, 0, 1),
    "methane": ("C", 8, 4, 0, 0),
    "ethene": ("C=C", 12, 6, 0, 0),
    "ethyne": ("C#C", 10, 5, 0, 0),
    "carbon dioxide": ("O=C=O", 16, 4, 0, 4),
    "ammonium": ("[NH4+]", 8, 4, 0, 0),
    "hydroxide": ("[OH-]", 8, 1, 0, 3),
    "acetate": ("CC(=O)[O-]", 24, 6, 2, 5),
    "nitromethane": ("C[N+](=O)[O-]", 24, 6, 2, 5),
    "benzene": ("c1ccccc1", 30, 12, 6, 0),
    "naphthalene": ("c1ccc2ccccc2c1", 48, 19, 10, 0),
}


@pytest.mark.parametrize("case", list(ORACLE), ids=list(ORACLE))
def test_the_budget_matches_the_hand_authored_oracle(case):
    smiles, valence, pairs, delocalised, lone_pairs = ORACLE[case]

    diagram = build(molblock(smiles))
    accounting = diagram.accounting

    assert diagram.status is Status.SUPPORTED, diagram.abstentions
    assert accounting.valence_electrons == Known(valence), accounting.describe()
    assert accounting.localised_bonding_electrons == Known(2 * pairs), accounting.describe()
    assert accounting.delocalised_electrons == Known(delocalised), accounting.describe()
    assert accounting.lone_pair_electrons == Known(2 * lone_pairs), accounting.describe()
    assert accounting.balances, accounting.describe()


# --- no Kekule structure, ever ------------------------------------------------


@pytest.mark.parametrize(
    "case,smiles",
    [
        ("benzene", "c1ccccc1"),
        ("pyridine", "c1ccncc1"),
        ("naphthalene", "c1ccc2ccccc2c1"),
        ("pyrrole", "c1cc[nH]c1"),
        ("furan", "c1ccoc1"),
        ("imidazole", "c1cnc[nH]1"),
    ],
)
def test_an_aromatic_ring_bond_carries_exactly_ONE_localised_pair(case, smiles):
    """**PYRROLE IS THE ONE THAT NEARLY GOT THIS WRONG.**

    It has a single resonance contributor, so the minimum order of a bond
    IS its own order -- 2 for the two drawn double -- and dotting those
    asserts exactly the Kekule structure this feature exists not to
    assert. Benzene was fine and pyrrole was not, from the same code.

    Every aromatic bond definitely has one sigma pair; anything beyond
    that belongs to the region, whose count may itself be undetermined.
    """
    diagram = build(molblock(smiles))
    ring_atoms = {index for region in diagram.regions for index in region.atom_indices}
    assert ring_atoms, f"{case}: no delocalised region was found at all"

    ring_bonds = [
        bond
        for bond in diagram.bond_pairs
        if bond.begin in ring_atoms and bond.end in ring_atoms
    ]
    assert ring_bonds, case
    assert all(bond.pairs == Known(1) for bond in ring_bonds), [
        (b.begin, b.end, b.pairs) for b in ring_bonds
    ]


def test_aromaticity_is_PERCEIVED_not_read_off_the_stored_molblock():
    """The editor stores benzene as alternating SINGLE/DOUBLE.

    A parse that does not sanitise -- which is the one
    `chem/electron_overlay.for_molblock` uses -- sees a perfectly
    localised molecule and would dot it as three doubles and three
    singles. The stored orders are asserted here first, so the test
    cannot pass by the molblock happening to be aromatic.
    """
    stored = molblock("c1ccccc1")
    raw = Chem.MolFromMolBlock(stored, sanitize=False)
    assert {str(b.GetBondType()) for b in raw.GetBonds()} == {"SINGLE", "DOUBLE"}

    diagram = build(stored)

    assert diagram.regions and diagram.regions[0].electrons == Known(6)
    assert all(b.pairs == Known(1) for b in diagram.bond_pairs if b.begin < 6 and b.end < 6)


def test_finding_a_delocalised_bond_needs_BOTH_tests():
    """Measured: pyrrole is aromatic with no bond order varying, and
    carboxylate varies without being aromatic. Either test alone gets one
    of these two families wrong, so both fixtures are asserted together
    -- a single one of them would pass against half the classifier."""
    pyrrole = build(molblock("c1cc[nH]c1"))
    carboxylate = build(molblock("CC(=O)[O-]"))

    assert pyrrole.regions, "aromaticity alone must still find pyrrole's ring"
    assert carboxylate.regions, "resonance alone must still find the carboxylate"
    assert carboxylate.regions[0].electrons == Known(2)
    assert isinstance(pyrrole.regions[0].electrons, Unknown)


def test_a_ring_whose_count_is_undetermined_says_so_rather_than_zero():
    """The region is real; the number is not. Those are different
    statements, and "0 electrons delocalised" would be the wrong one."""
    diagram = build(molblock("c1cc[nH]c1"))

    (region,) = diagram.regions
    assert region.is_ring
    assert isinstance(region.electrons, Unknown)
    assert "lone pair" in region.electrons.reason
    assert not diagram.accounting.balances, "an undetermined budget must not read as balanced"


def test_a_delocalised_region_knows_whether_it_is_a_RING():
    """A ring gets the conventional inscribed circle and an open system an
    arc, so the renderer needs to be told which."""
    assert build(molblock("c1ccccc1")).regions[0].is_ring
    assert not build(molblock("CC(=O)[O-]")).regions[0].is_ring


# --- what it declines ---------------------------------------------------------


def test_an_unpaired_electron_refuses_the_whole_molecule():
    diagram = build(molblock("[CH2]"))

    assert diagram.status is Status.CHEMISTRY_REFUSED
    assert "unpaired" in diagram.reason.lower()
    assert not diagram.drawable


def test_an_expanded_octet_abstains_bond_by_bond_and_names_them():
    """Sulfate presents as cleanly localised, and whether to draw it with
    an expanded octet or charge-separated is contested. Abstained with
    that reason rather than answered."""
    diagram = build(molblock("[O-]S(=O)(=O)[O-]"))

    assert diagram.status is Status.SUPPORTED_WITH_ABSTENTIONS
    assert diagram.abstentions
    assert any("octet" in a.reason for a in diagram.abstentions)
    assert all(a.subject for a in diagram.abstentions), "an abstention must name its subject"
    sulfur_bonds = [b for b in diagram.bond_pairs if isinstance(b.pairs, Unknown)]
    assert len(sulfur_bonds) == 4


def test_an_atom_whose_lone_pairs_are_unknown_is_an_ABSTENTION():
    """A bare metal reported SUPPORTED while its budget could not be
    closed -- which is the status claiming more than the analysis did."""
    diagram = build(molblock("[Fe+3]"))

    assert diagram.status is Status.SUPPORTED_WITH_ABSTENTIONS
    assert diagram.abstentions
    assert not diagram.accounting.balances


def test_an_unreadable_structure_is_refused_rather_than_returned_empty():
    for bad in (None, "", "this is not a molblock"):
        diagram = build(bad)
        assert diagram.status is Status.CHEMISTRY_REFUSED, bad
        assert diagram.reason


# --- what must not change the chemistry --------------------------------------


def test_atom_ORDER_does_not_change_what_each_atom_is_given():
    """RDKit renumbers on ordinary operations, and the diagram is keyed by
    index. Compared by ELEMENT and count, which a renumbering cannot
    satisfy by accident."""
    from rdkit.Chem import rdmolops

    plain = Chem.MolFromSmiles("CC(=O)[O-]")
    reordered = rdmolops.RenumberAtoms(plain, [3, 1, 0, 2])

    first = build(Chem.MolToMolBlock(_with_coords(plain)))
    second = build(Chem.MolToMolBlock(_with_coords(reordered)))

    def signature(diagram):
        return sorted(
            (atom.symbol, atom.formal_charge, str(atom.lone_pairs)) for atom in diagram.atoms
        )

    assert signature(first) == signature(second)
    assert first.accounting.describe() == second.accounting.describe()


def test_a_DIFFERENT_CONFORMER_gives_a_chemically_identical_diagram():
    """**No energy, force field or 3D geometry may inform a Lewis
    representation.** The layout may differ; the chemistry may not. A
    cross-check that the recent 3D work cannot bleed in here.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMultipleConfs(mol, numConfs=2, randomSeed=0xC0FFEE)
    assert mol.GetNumConformers() == 2

    diagrams = [
        build(Chem.MolToMolBlock(mol, confId=conf.GetId())) for conf in mol.GetConformers()
    ]

    assert diagrams[0].accounting.describe() == diagrams[1].accounting.describe()
    assert [str(b.pairs) for b in diagrams[0].bond_pairs] == [
        str(b.pairs) for b in diagrams[1].bond_pairs
    ]


def test_charges_and_isotopes_survive_the_explicit_hydrogens():
    """`AddHs` must depict the same graph, not a newly inferred molecule."""
    heavy = Chem.MolFromSmiles("[2H]O[NH3+]")
    diagram = build(Chem.MolToMolBlock(_with_coords(heavy)))

    assert any(atom.isotope == 2 for atom in diagram.atoms), [a.label for a in diagram.atoms]
    assert any(atom.formal_charge == 1 for atom in diagram.atoms)


def test_the_lone_pair_counts_agree_with_the_canvas_overlay():
    """One source, so the diagram and the 2D editor can never disagree
    about how many pairs an oxygen has."""
    from openchem.chem.electron_overlay import build as overlay_build

    block = molblock("CC(=O)O")
    diagram = build(block)
    with_hydrogens = Chem.AddHs(Chem.MolFromMolBlock(block, removeHs=False))
    overlay = overlay_build(with_hydrogens)

    for atom in diagram.atoms:
        expected = overlay.counts.get(atom.index)
        if expected is None:
            assert isinstance(atom.lone_pairs, Unknown)
        else:
            assert atom.lone_pairs == Known(expected), atom


# --- provenance and legibility -----------------------------------------------


def test_the_diagram_records_which_molecule_it_is_of():
    """So a snapshot dialog can say what it is showing, and a stale one is
    diagnosable rather than merely wrong."""
    block = molblock("CCO")
    diagram = build(block, structure_revision=7)

    assert diagram.provenance.molblock_sha
    assert diagram.provenance.structure_revision == 7
    assert diagram.provenance.analysis_version == ANALYSIS_VERSION
    assert diagram.provenance.rdkit_version
    assert build(molblock("CCC")).provenance.molblock_sha != diagram.provenance.molblock_sha


def test_crowding_is_a_LEGIBILITY_number_and_not_a_refusal():
    """Glucose lays out crowded and cholesterol far worse, and both have
    perfectly good chemistry. Reporting "analysis unsupported" for a
    layout problem would conflate the two failure kinds the `Status`
    enum exists to separate.

    Atom count does not predict it: aspirin has 21 atoms and lays out
    cleanly, glucose has 24 and does not.
    """
    roomy = build(molblock("CC(=O)Oc1ccccc1C(=O)O"))
    crowded = build(molblock("OCC1OC(O)C(O)C(O)C1O"))

    assert roomy.status is Status.SUPPORTED
    assert crowded.status is Status.SUPPORTED, "crowding is not a chemistry refusal"
    assert crowding(roomy) > CROWDED_APPROACH
    assert crowding(crowded) < CROWDED_APPROACH


def _with_coords(mol):
    copy = Chem.Mol(mol)
    AllChem.Compute2DCoords(copy)
    return copy
