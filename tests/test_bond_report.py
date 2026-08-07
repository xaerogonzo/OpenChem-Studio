"""`BondReport` -- everything known about one bond.

Assertions are about WHICH facts appear and whether they are true, not
about counts or positions. A report gains sources over time; "the
Structure group contains a ring-membership fact" survives that, and
"fact #4 is the ring fact" breaks the first time anything is inserted.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.bond_report import bond_label, build_bond_report
from openchem.domain.report import FactCategory

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def mol_2d(smiles: str = ASPIRIN):
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return mol


def mol_3d(smiles: str = ASPIRIN):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    return mol


def bond_between(mol, symbol_a: str, symbol_b: str, order=None):
    for bond in mol.GetBonds():
        symbols = {bond.GetBeginAtom().GetSymbol(), bond.GetEndAtom().GetSymbol()}
        if symbols != {symbol_a, symbol_b}:
            continue
        if order is not None and bond.GetBondType() != order:
            continue
        return bond.GetIdx()
    raise AssertionError(f"no {symbol_a}-{symbol_b} bond")


def labelled(report, label: str):
    for fact in report.facts:
        if fact.label == label:
            return fact
    return None


# --- identity -----------------------------------------------------------


def test_a_bond_reports_the_two_atoms_it_joins():
    mol = mol_2d()
    index = bond_between(mol, "C", "O", Chem.BondType.DOUBLE)
    report = build_bond_report(mol, index, molecule_uuid="m")

    bond = mol.GetBondWithIdx(index)
    assert report.begin_atom_index == bond.GetBeginAtomIdx()
    assert report.end_atom_index == bond.GetEndAtomIdx()
    assert labelled(report, "From") is not None
    assert labelled(report, "To") is not None


def test_each_end_links_to_its_own_atom_report():
    """The reason a bond view sits beside an atom view rather than
    duplicating it."""
    mol = mol_2d()
    index = bond_between(mol, "C", "O", Chem.BondType.DOUBLE)
    report = build_bond_report(mol, index)

    ends = [f for f in report.facts if f.label in {"From", "To"}]
    assert len(ends) == 2
    for fact in ends:
        assert fact.link is not None
        assert fact.link.target == "atom_report"
        assert fact.link.params["atom_index"] == fact.value


def test_the_label_shows_the_order_as_a_glyph():
    """"C2=O3" reads as a double bond without a legend."""
    mol = mol_2d()
    double = bond_label(mol, bond_between(mol, "C", "O", Chem.BondType.DOUBLE))
    aromatic = bond_label(mol, bond_between(mol, "C", "C", Chem.BondType.AROMATIC))
    single = bond_label(mol, bond_between(mol, "C", "O", Chem.BondType.SINGLE))
    assert "=" in double
    assert ":" in aromatic
    assert "-" in single


def test_the_label_numbers_atoms_from_one():
    """Every user-facing index in this application is 1-based, and the
    structure checker's own messages already say "atoms 3 and 4" for what
    RDKit calls 2 and 3."""
    mol = Chem.MolFromSmiles("CO")
    # Bond 0 joins RDKit atoms 0 and 1, so the label must read C1-O2.
    assert bond_label(mol, 0) == "C1-O2"


# --- structure ----------------------------------------------------------


def test_an_aromatic_bond_says_so_and_reports_its_ring():
    mol = mol_2d()
    index = bond_between(mol, "C", "C", Chem.BondType.AROMATIC)
    report = build_bond_report(mol, index)

    assert labelled(report, "Aromatic").value is True
    assert labelled(report, "In a ring").value is True
    assert 6 in labelled(report, "Ring size").value


def test_an_acyclic_bond_says_it_is_not_in_a_ring_rather_than_omitting_it():
    """A missing fact reads as "not checked". Ring membership is cheap and
    always knowable, so absence would be the wrong signal."""
    mol = mol_2d()
    index = bond_between(mol, "C", "O", Chem.BondType.DOUBLE)
    report = build_bond_report(mol, index)

    fact = labelled(report, "In a ring")
    assert fact is not None
    assert fact.value is False


def test_a_fused_bond_is_reported_as_shared_between_rings():
    mol = mol_2d("c1ccc2ccccc2c1")  # naphthalene
    shared = next(
        b.GetIdx()
        for b in mol.GetBonds()
        if mol.GetRingInfo().NumBondRings(b.GetIdx()) > 1
    )
    report = build_bond_report(mol, shared)
    assert labelled(report, "Ring fusion") is not None


# --- geometry: the trap -------------------------------------------------


def test_a_3d_conformer_gives_a_bond_length_in_angstrom():
    mol = mol_3d()
    index = bond_between(mol, "C", "O", Chem.BondType.DOUBLE)
    report = build_bond_report(mol, index)

    length = labelled(report, "Length")
    assert length is not None
    assert length.units == "Å"
    # A real C=O is near 1.2 A. This asserts the number is a MEASUREMENT,
    # not merely present.
    assert 1.15 < length.value < 1.35
    assert length.category is FactCategory.GEOMETRY


def test_a_2d_depiction_reports_no_length_at_all():
    """The trap this exists to avoid.

    A 2D layout has coordinates, and they are drawing units -- every bond
    comes out about the same length whatever its order. Measured on
    aspirin: the 2D C=O reads 1.5 "units" against a real 1.264 A. Printing
    that as angstrom would be a fabricated measurement, so a 2D conformer
    produces no length rather than a wrong one.
    """
    mol = mol_2d()
    index = bond_between(mol, "C", "O", Chem.BondType.DOUBLE)
    report = build_bond_report(mol, index)
    assert labelled(report, "Length") is None


def test_a_molecule_with_no_conformer_reports_no_length():
    mol = Chem.MolFromSmiles(ASPIRIN)
    report = build_bond_report(mol, 0)
    assert labelled(report, "Length") is None
    assert report, "the rest of the report should still be there"


# --- flexibility --------------------------------------------------------


def test_the_flexibility_fact_does_not_claim_to_be_rotatability():
    """Deliberately not called "rotatable".

    That word is defined by `CalcNumRotatableBonds`, and this is not it:
    the strict count excludes amide and ester bonds. Two reconstructions
    were tried and both failed -- excluding amides leaves aspirin at 3
    against RDKit's 2, and excluding conjugated bonds drops biphenyl's
    central bond, which RDKit does count. So the fact reports the
    structural property it can stand behind and names the gap.
    """
    mol = mol_2d()
    report = build_bond_report(mol, bond_between(mol, "C", "O", Chem.BondType.SINGLE))

    fact = labelled(report, "Single, acyclic, non-terminal")
    assert fact is not None
    assert not any("rotatable" in f.label.lower() for f in report.facts)
    assert any("strict definition" in limitation for limitation in fact.limitations)


def test_an_aromatic_ring_bond_is_not_flagged_as_free():
    mol = mol_2d()
    report = build_bond_report(mol, bond_between(mol, "C", "C", Chem.BondType.AROMATIC))
    assert labelled(report, "Single, acyclic, non-terminal").value is False


# --- retrosynthesis -----------------------------------------------------


def test_a_brics_bond_is_reported_with_its_environments():
    from rdkit.Chem import BRICS

    mol = mol_2d()
    pair = next(iter(BRICS.FindBRICSBonds(mol)))[0]
    index = mol.GetBondBetweenAtoms(pair[0], pair[1]).GetIdx()
    report = build_bond_report(mol, index)

    fact = labelled(report, "Retrosynthetic disconnection")
    assert fact is not None
    assert "BRICS" in fact.display_value
    # It is a synthesis statement, not a stability one, and says so.
    assert any("how strong" in limitation for limitation in fact.limitations)


def test_a_bond_brics_would_not_cut_carries_no_disconnection_fact():
    mol = mol_2d()
    report = build_bond_report(mol, bond_between(mol, "C", "C", Chem.BondType.AROMATIC))
    assert labelled(report, "Retrosynthetic disconnection") is None


# --- issues and isolation -----------------------------------------------


def test_structure_issues_are_matched_on_bond_indices():
    """`StructureIssue` already carries `bond_indices`, populated by the
    valence and geometry checkers -- nothing had to change for a bond to
    find its own issues."""
    from openchem.domain.structure_issue import Basis, Category, Severity, StructureIssue

    mol = mol_2d()
    # The atom and bond indices are DISJOINT on purpose. With overlapping
    # ones the test cannot tell the two lookups apart: bond 0 is in
    # atom_indices (0, 1) as well, so a collector reading the wrong field
    # still produced the right answer and the mutation survived.
    issue = StructureIssue(
        checker_id="bond_length",
        category=Category.LAYOUT,
        severity=Severity.WARNING,
        basis=Basis.HEURISTIC,
        message="This bond is 2.0x the typical length.",
        atom_indices=(7, 8),
        bond_indices=(0,),
    )
    on_bond = build_bond_report(mol, 0, context={"issues": [issue]})
    other = build_bond_report(mol, 5, context={"issues": [issue]})

    assert any(f.source == "StructureCheck" for f in on_bond.facts)
    assert not any(f.source == "StructureCheck" for f in other.facts)


def test_a_failing_provider_costs_only_its_own_facts():
    class Broken:
        provider_id = "broken"

        def collect_bond_facts(self, mol, bond_index, context):
            raise RuntimeError("boom")

    mol = mol_2d()
    report = build_bond_report(mol, 0, providers=[Broken()])
    assert report, "the built-in facts must survive a broken plugin"


def test_a_provider_can_add_bond_facts():
    from openchem.domain.report import Fact
    from openchem.domain.structure_issue import Basis

    class Extra:
        provider_id = "extra"

        def collect_bond_facts(self, mol, bond_index, context):
            return [
                Fact(
                    category=FactCategory.ELECTRONIC,
                    label="Plugin fact",
                    value=1,
                    display_value="1",
                    source="extra",
                    basis=Basis.HEURISTIC,
                )
            ]

    report = build_bond_report(mol_2d(), 0, providers=[Extra()])
    assert labelled(report, "Plugin fact") is not None


def test_the_report_groups_by_category_not_by_producer():
    """Grouping by producer gives consecutive "RDKit" headings, which is an
    implementation detail on screen."""
    report = build_bond_report(mol_3d(), 1)
    grouped = report.by_category()
    assert FactCategory.IDENTITY in grouped
    # Every category present must be non-empty -- an empty heading says
    # "nothing found" where the truth is "not applicable".
    assert all(facts for facts in grouped.values())
