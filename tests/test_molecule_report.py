"""`MoleculeReport` -- everything known about a whole molecule.

The load-bearing property is that it NEVER COMPUTES. Its value is reach,
not new information: it gathers what four panels already hold. A report
that started a calculation would be a calculator launcher wearing a
report's name, and nobody would leave it open.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.molecule_report import build_molecule_report
from openchem.domain.report import FactCategory

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def mol(smiles: str = ASPIRIN, hydrogens: bool = False, embed: bool = False):
    m = Chem.MolFromSmiles(smiles)
    if hydrogens or embed:
        m = Chem.AddHs(m)
    if embed:
        AllChem.EmbedMolecule(m, randomSeed=0xF00D)
    return m


def labelled(report, label: str):
    for fact in report.facts:
        if fact.label == label:
            return fact
    return None


# --- identity -----------------------------------------------------------


def test_the_identifiers_are_the_real_ones():
    """Asserted against known values rather than "is a non-empty string" --
    a formula routine returning "C1H1" would pass the latter."""
    report = build_molecule_report(mol(), context={"display_name": "aspirin"})

    assert report.formula == "C9H8O4"
    assert labelled(report, "Molecular weight").value == pytest.approx(180.16, abs=0.01)
    assert labelled(report, "InChIKey").value == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    assert labelled(report, "Name").value == "aspirin"


def test_the_smiles_is_written_without_explicit_hydrogens():
    """A report is usually built on an H-added molecule -- anything that
    has been through 3D embedding is -- and `[H]OC(=O)c1c([H])...` is the
    truthful SMILES of that object while being useless as the identifier
    somebody wants to copy."""
    report = build_molecule_report(mol(embed=True))
    smiles = labelled(report, "SMILES").value
    assert "[H]" not in smiles
    assert Chem.CanonSmiles(smiles) == Chem.CanonSmiles(ASPIRIN)


def test_a_molecule_with_no_name_omits_the_name_rather_than_inventing_one():
    report = build_molecule_report(mol())
    assert labelled(report, "Name") is None
    assert report.display_name == ""


# --- composition --------------------------------------------------------


def test_the_counts_are_right():
    report = build_molecule_report(mol())
    assert labelled(report, "Heavy atoms").value == 13
    assert labelled(report, "Rings").value == 1
    assert labelled(report, "Aromatic rings").value == 1
    assert labelled(report, "Formal charge").value == 0


def test_the_rotatable_bond_count_names_its_stricter_definition():
    """It will not equal the number of bonds a per-bond view flags, and
    saying so is cheaper than someone discovering the discrepancy."""
    fact = labelled(build_molecule_report(mol()), "Rotatable bonds")
    assert fact.value == 2
    assert any("strict definition" in limitation for limitation in fact.limitations)


def test_disconnected_species_are_called_out():
    """A great deal of chemistry silently assumes one connected molecule,
    and a salt or a drawn pair is the commonest reason a result looks
    wrong."""
    report = build_molecule_report(mol("c1ccccc1.O"))
    fact = labelled(report, "Separate species")
    assert fact is not None
    assert fact.value == 2

    assert labelled(build_molecule_report(mol()), "Separate species") is None


def test_a_charged_molecule_reports_its_charge_with_a_sign():
    report = build_molecule_report(mol("CC(=O)[O-]"))
    assert labelled(report, "Formal charge").display_value == "-1"


# --- geometry: the same trap the bond report has -------------------------


def test_a_2d_only_molecule_says_its_coordinates_are_not_measurements():
    m = mol()
    AllChem.Compute2DCoords(m)
    report = build_molecule_report(m)

    coordinates = labelled(report, "Coordinates")
    assert coordinates.value is False
    assert "2D" in coordinates.display_value
    assert any("not measurements" in limitation for limitation in coordinates.limitations)


def test_a_3d_molecule_says_so():
    report = build_molecule_report(mol(embed=True))
    assert labelled(report, "Coordinates").value is True


def test_no_conformer_is_reported_as_an_actionable_absence():
    """"none" plus what to do about it, rather than a bare 0 that reads as
    a failure."""
    report = build_molecule_report(mol())
    fact = labelled(report, "3D conformers")
    assert fact.value == 0
    assert "generate conformers" in fact.display_value


# --- context: what the session already knew -----------------------------


def test_descriptors_that_have_run_appear_and_route_to_their_category():
    from openchem.domain.descriptor import DescriptorValue

    descriptors = [
        DescriptorValue(descriptor_id="mol_wt", name="Molecular Weight", units="g/mol",
                        category="physicochemical", provider="rdkit",
                        molecule_uuid="m", value=180.16),
        DescriptorValue(descriptor_id="homo", name="E(HOMO)", units="eV",
                        category="quantum_chemistry", provider="orca",
                        molecule_uuid="m", value=-6.5),
    ]
    report = build_molecule_report(mol(), context={"descriptors": descriptors})

    assert labelled(report, "Molecular Weight").category is FactCategory.STRUCTURE
    assert labelled(report, "E(HOMO)").category is FactCategory.QUANTUM
    assert labelled(report, "E(HOMO)").units == "eV"


def test_a_descriptor_with_no_value_is_skipped_not_shown_as_blank():
    from openchem.domain.descriptor import DescriptorValue

    pending = DescriptorValue(descriptor_id="pending", name="Pending", units="",
                              category="physicochemical", provider="rdkit",
                              molecule_uuid="m", value=None)
    report = build_molecule_report(mol(), context={"descriptors": [pending]})
    assert labelled(report, "Pending") is None


def test_an_alert_that_matched_nothing_is_still_reported():
    """"PAINS: none matched" and "PAINS was never run" are different
    statements, and the difference is the whole reason it was run."""
    from openchem.domain.scientific_result import AlertResult

    clean = AlertResult(alert_id="pains", name="PAINS", molecule_uuid="m", matched=[])
    report = build_molecule_report(mol(), context={"alerts": [clean]})

    fact = labelled(report, "PAINS")
    assert fact is not None
    assert fact.display_value == "none matched"


def test_structure_check_is_summarised_and_links_to_the_panel():
    from openchem.domain.structure_issue import Basis, Category, Severity, StructureIssue

    issues = [
        StructureIssue(checker_id="bond_length", category=Category.LAYOUT,
                       severity=Severity.WARNING, basis=Basis.HEURISTIC,
                       message="long bond"),
        StructureIssue(checker_id="valence", category=Category.VALIDITY,
                       severity=Severity.ERROR, basis=Basis.DETERMINISTIC,
                       message="bad valence"),
    ]
    report = build_molecule_report(mol(), context={"issues": issues})

    fact = labelled(report, "Structure check")
    assert fact is not None
    # A summary, not a copy -- the panel owns the detail.
    assert "1" in fact.display_value
    assert fact.link.target == "structure_check"


def test_lewis_character_is_counts_rather_than_a_site_list():
    """The per-atom detail belongs on the atom report; what belongs here is
    the shape of the question somebody asks before choosing a partner."""
    fact = labelled(build_molecule_report(mol()), "Lewis sites")
    assert fact is not None
    assert "donor" in fact.display_value
    assert fact.category is FactCategory.ELECTRONIC


# --- the load-bearing guarantee -----------------------------------------


def test_building_a_report_starts_no_calculation(monkeypatch):
    """The guarantee the whole design rests on. An empty context gives a
    SHORT report, never a slow one."""
    import openchem.services.descriptor_service as descriptor_service

    called: list[str] = []
    if hasattr(descriptor_service.DescriptorService, "run_calculator"):
        monkeypatch.setattr(
            descriptor_service.DescriptorService,
            "run_calculator",
            lambda self, *a, **k: called.append("run"),
        )
    report = build_molecule_report(mol(embed=True), context={})
    assert report, "a report with no context is still worth having"
    assert called == []


def test_a_failing_provider_costs_only_its_own_facts():
    class Broken:
        provider_id = "broken"

        def collect_molecule_facts(self, mol, context):
            raise RuntimeError("boom")

    report = build_molecule_report(mol(), providers=[Broken()])
    assert report.formula == "C9H8O4"


def test_a_provider_can_add_molecule_facts():
    from openchem.domain.report import Fact
    from openchem.domain.structure_issue import Basis

    class Extra:
        provider_id = "extra"

        def collect_molecule_facts(self, mol, context):
            return [
                Fact(category=FactCategory.REGULATORY, label="Plugin verdict",
                     value="ok", display_value="ok", source="extra",
                     basis=Basis.HEURISTIC)
            ]

    report = build_molecule_report(mol(), providers=[Extra()])
    assert labelled(report, "Plugin verdict") is not None


def test_the_report_indexes_its_own_atoms_and_bonds():
    """A molecule report is the natural entry point to the per-atom and
    per-bond ones, so a consumer should not have to re-parse a structure to
    know how many there are.

    Asserted on an ACYCLIC molecule, where the two counts differ. Aspirin
    has 13 atoms and 13 bonds -- one ring makes them equal -- so swapping
    the two fields was invisible to this test until it moved.
    """
    report = build_molecule_report(mol("CCCCC"))
    assert report.atom_count == 5
    assert report.bond_count == 4
