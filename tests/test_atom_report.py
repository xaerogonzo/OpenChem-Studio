"""Everything known about one atom, gathered in one place.

**Assertions here are by CONTENT, never by position.** "the Electronic
group contains a Lewis role" survives a new fact being added anywhere;
"fact #17 is the Lewis role" breaks the first time anything is inserted,
and the whole point of this module is that sources get added to it.

Chalcone (PhCH=CH-C(=O)-Ph) is the fixture because it exercises several
sources at once on different atoms: a lone-pair donor, two pi* acceptors,
oxidation states of three different signs, rings, and hybridisation worth
looking at.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.atom_report import build_atom_report
from openchem.domain.atom_report import (
    CATEGORY_ORDER,
    DEFAULT_EXPANDED,
    AtomFact,
    AtomReport,
    FactCategory,
    FactLink,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import PerAtomDataset, SpectrumResult
from openchem.domain.structure_issue import Basis, Severity, StructureIssue

CHALCONE = "c1ccc(cc1)C=CC(=O)c1ccccc1"
CARBONYL_O, CARBONYL_C, BETA_C = 9, 8, 6

_PROVENANCE = Provenance(created_by="core", method="test")


def mol_for(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


def report_for(smiles: str, index: int, **kwargs) -> AtomReport:
    return build_atom_report(mol_for(smiles), index, **kwargs)


def labels(report: AtomReport, category: FactCategory) -> set[str]:
    return {fact.label for fact in report.by_category().get(category, ())}


def fact_named(report: AtomReport, label: str) -> AtomFact:
    found = [fact for fact in report.facts if fact.label == label]
    assert found, f"no fact named {label!r}; have {sorted(f.label for f in report.facts)}"
    return found[0]


def per_atom(property_id: str, name: str, values: dict[int, float], units: str = "") -> PerAtomDataset:
    return PerAtomDataset(
        property_id=property_id, name=name, units=units, method="test",
        molecule_uuid="m1", values=values,
        cache_state=CacheState.COMPLETED, provenance=_PROVENANCE,
    )


# --- what each source contributes ------------------------------------------


def test_intrinsic_facts_are_always_present():
    """No calculator has run and no plugin is loaded; RDKit alone still
    answers the questions somebody asks first."""
    report = report_for(CHALCONE, CARBONYL_O)
    assert {"Element", "Atom index"} <= labels(report, FactCategory.IDENTITY)
    assert {"Hybridisation", "Aromatic"} <= labels(report, FactCategory.STRUCTURE)
    assert "Formal charge" in labels(report, FactCategory.ELECTRONIC)


def test_the_element_reference_is_reused_rather_than_re_derived():
    """`element_reference.facts_for` was built for the periodic table and
    answers this too -- a second copy of the same data is a second thing
    to get wrong."""
    report = report_for(CHALCONE, CARBONYL_O)
    element = labels(report, FactCategory.ELEMENT)
    assert {"Name", "Atomic number", "Electronegativity"} <= element
    assert fact_named(report, "Name").display_value == "Oxygen"


def test_lewis_role_arrives_with_the_rule_that_found_it():
    report = report_for(CHALCONE, CARBONYL_O)
    role = fact_named(report, "Lewis role")
    assert role.display_value == "donor"
    assert role.evidence, "a role with no evidence cannot answer 'why'"
    assert "lone pair" in role.evidence[0]
    assert fact_named(report, "Lone pairs").value == 2


def test_a_heuristic_source_says_so_on_the_fact():
    """The carbonyl carbon is an acceptor by motif, not by arithmetic, and
    the fact carries that rather than the report averaging it away."""
    report = report_for(CHALCONE, CARBONYL_C)
    assert fact_named(report, "Lewis role").basis is Basis.HEURISTIC
    assert fact_named(report, "Lone pairs").basis is Basis.DETERMINISTIC


@pytest.mark.parametrize(
    ("label", "index", "expected"),
    [("carbonyl oxygen", CARBONYL_O, "-2"), ("carbonyl carbon", CARBONYL_C, "+2"), ("beta carbon", BETA_C, "-1")],
)
def test_oxidation_states_come_through_with_their_sign(label, index, expected):
    assert fact_named(report_for(CHALCONE, index), "Oxidation state").display_value == expected, label


def test_ring_membership_reports_the_ring_size():
    assert fact_named(report_for("c1ccccc1", 0), "In ring").display_value == "6-membered"


def test_an_atom_in_no_ring_has_no_ring_fact():
    """Absent, not "none" -- a report that states every negative is a wall."""
    assert "In ring" not in {fact.label for fact in report_for("CCO", 0).facts}


# --- results that arrive by event ------------------------------------------


def test_computed_per_atom_data_joins_the_report():
    context = {"per_atom": {"gasteiger_charge": per_atom(
        "gasteiger_charge", "Partial Charge (Gasteiger)", {CARBONYL_C: 0.2034}, "e")}}
    charge = fact_named(report_for(CHALCONE, CARBONYL_C, context=context), "Partial Charge (Gasteiger)")
    assert charge.value == pytest.approx(0.2034)
    assert charge.display_value == "0.2034 e"


def test_each_atom_gets_its_own_value_and_only_its_own():
    """The dataset holds every atom's value; this atom gets exactly one.

    Asserting only ABSENCE for the wrong atom is not enough, and a
    surviving mutation proved it: drop the membership guard and the
    collector raises `KeyError`, which `build_atom_report` swallows by
    design -- so the fact is missing either way and the test cannot tell
    correct filtering from a crashed collector. Checking that each atom
    gets its OWN distinct number is what separates them.
    """
    charges = {CARBONYL_O: -0.2712, CARBONYL_C: 0.2034}
    context = {"per_atom": {"gasteiger_charge": per_atom(
        "gasteiger_charge", "Partial Charge (Gasteiger)", charges, "e")}}

    for index, expected in charges.items():
        report = report_for(CHALCONE, index, context=context)
        assert fact_named(report, "Partial Charge (Gasteiger)").value == pytest.approx(expected)

    # An atom the dataset says nothing about gets no fact, and does not
    # inherit a neighbour's number.
    silent = report_for(CHALCONE, BETA_C, context=context)
    assert "Partial Charge (Gasteiger)" not in {fact.label for fact in silent.facts}


def test_one_dataset_missing_an_atom_does_not_cost_the_others():
    """The case that actually pins the membership guard.

    Two datasets, and this atom appears in only ONE of them. Skipping the
    absent dataset must leave the present one intact. Without the guard
    the collector raises `KeyError` on the dataset that does not mention
    the atom, and `build_atom_report` swallows it -- taking the OTHER
    dataset's perfectly good fact down with it.

    Absence-only assertions cannot see this: a crash and a correct skip
    look identical from the missing atom's side.
    """
    context = {"per_atom": {
        "atom_sasa": per_atom("atom_sasa", "Atom SASA", {BETA_C: 12.5}, "A^2"),
        "gasteiger_charge": per_atom("gasteiger_charge", "Partial Charge", {CARBONYL_O: -0.27}, "e"),
    }}
    report = report_for(CHALCONE, BETA_C, context=context)
    present = {fact.label for fact in report.facts}
    assert "Atom SASA" in present, "the dataset that DOES mention this atom must survive"
    assert "Partial Charge" not in present


def test_a_spectrum_becomes_a_spectroscopy_fact():
    context = {"spectra": {"nmr_13c": SpectrumResult(
        spectrum_type="nmr_13c", name="13C Shift", units="ppm", method="orca",
        molecule_uuid="m1", values={CARBONYL_C: 190.4}, elements={CARBONYL_C: "C"},
        cache_state=CacheState.COMPLETED, provenance=_PROVENANCE)}}
    report = report_for(CHALCONE, CARBONYL_C, context=context)
    assert "13C Shift" in labels(report, FactCategory.SPECTROSCOPY)


def test_a_structure_issue_naming_this_atom_shows_up():
    context = {"issues": (StructureIssue(
        checker_id="geometry", category="geometry", severity=Severity.WARNING,
        basis=Basis.HEURISTIC, message="Bond crossing near this atom",
        atom_indices=(CARBONYL_C,), bond_indices=()),)}
    report = report_for(CHALCONE, CARBONYL_C, context=context)
    assert any("Bond crossing" in fact.display_value for fact in report.facts)
    # ...and not on an atom it does not name.
    other = report_for(CHALCONE, CARBONYL_O, context=context)
    assert not any("Bond crossing" in fact.display_value for fact in other.facts)


# --- the design decisions --------------------------------------------------


def test_facts_group_by_category_not_by_producing_module():
    """Four Lewis facts must sit under ONE Electronic heading beside the
    formal charge and oxidation state. Grouping by source would give four
    consecutive "Lewis" headings, which is an implementation detail
    leaking onto the screen."""
    report = report_for(CHALCONE, CARBONYL_C)
    electronic = labels(report, FactCategory.ELECTRONIC)
    assert {"Lewis role", "Lone pairs", "Accepts via"} <= electronic
    assert {"Formal charge", "Oxidation state"} <= electronic
    assert len(report.facts_from("LewisAnalysis")) >= 3


def test_structured_values_survive_for_consumers():
    """`value` is `Any` and `display_value` is the rendering. A plugin or
    the AI assistant wants the ring sizes, not the string "6-membered"."""
    ring = fact_named(report_for("c1ccccc1", 0), "In ring")
    assert ring.value == [6]
    assert ring.display_value == "6-membered"

    role = fact_named(report_for(CHALCONE, CARBONYL_O), "Lewis role")
    assert role.value.value == "donor"  # the enum, not its name
    assert isinstance(role.display_value, str)


def test_facts_carry_links_to_the_tool_that_owns_them():
    """The inspector is a hub, not a replacement -- and the PARAMETERS are
    what make a link useful rather than decorative."""
    report = report_for(CHALCONE, CARBONYL_O)
    element = fact_named(report, "Name")
    assert element.link.target == "periodic_table"
    assert element.link.params == {"symbol": "O"}


def test_a_per_atom_link_names_its_calculator_and_atom():
    context = {"per_atom": {"atom_sasa": per_atom("atom_sasa", "Atom SASA", {BETA_C: 12.5}, "A^2")}}
    link = fact_named(report_for(CHALCONE, BETA_C, context=context), "Atom SASA").link
    assert link.params == {"calculator_id": "atom_sasa", "atom": BETA_C}


def test_a_sparse_atom_reads_cleanly():
    """Methane's carbon knows almost nothing. It must not become a wall of
    "unavailable" -- absent is the honest rendering of not computed."""
    report = report_for("C", 0)
    assert report.facts
    assert not any("unavailable" in fact.display_value.lower() for fact in report.facts)
    assert FactCategory.SPECTROSCOPY not in report.by_category()


def test_an_empty_category_is_omitted_rather_than_shown_empty():
    grouped = report_for("C", 0).by_category()
    assert all(facts for facts in grouped.values())
    assert list(grouped) == [c for c in CATEGORY_ORDER if c in grouped]


def test_a_failing_collector_costs_only_its_own_facts(monkeypatch):
    """One badly-behaved source -- or one plugin -- must not take the
    report down with it."""
    import openchem.chem.atom_report as module

    def explode(mol, index, context):
        raise RuntimeError("this source is broken")

    monkeypatch.setattr(module, "_COLLECTORS", (module.collect_intrinsic, explode, module.collect_element))
    report = build_atom_report(mol_for(CHALCONE), CARBONYL_O)
    assert "Element" in labels(report, FactCategory.IDENTITY)
    assert "Name" in labels(report, FactCategory.ELEMENT)


def test_the_report_records_the_structure_version_it_was_built_for():
    """This is what makes a cached report safe to reuse, and it is the
    checker's existing counter rather than a second mechanism."""
    report = report_for(CHALCONE, CARBONYL_O, molecule_uuid="m1", structure_version=12)
    assert report.structure_version == 12
    assert report.molecule_uuid == "m1"


# --- it must never compute -------------------------------------------------


def test_building_a_report_starts_no_calculation():
    """The load-bearing guarantee. An inspector that launches ORCA when
    you click an atom is a calculator launcher, and people stop trusting
    it. Asserted with a spy rather than described in prose.
    """
    calls: list[tuple] = []

    class Spy:
        def run_calculator(self, *args, **kwargs):
            calls.append(args)

        def request_descriptors(self, *args, **kwargs):
            calls.append(args)

    spy = Spy()
    context = {"per_atom": {}, "spectra": {}, "issues": (), "descriptor_service": spy}
    report = build_atom_report(mol_for(CHALCONE), CARBONYL_C, context=context)

    assert report.facts, "the report should still be built"
    assert calls == [], "building a report must not dispatch any calculation"


# --- search and display ordering -------------------------------------------


def test_search_matches_labels_values_and_evidence():
    report = report_for(CHALCONE, CARBONYL_O)
    assert any(f.label == "Lewis role" for f in report.find("lewis"))
    assert any(f.label == "Name" for f in report.find("oxygen"))
    # "lone pair available" is evidence, not a label or a value.
    assert report.find("lone pair available")


def test_an_empty_search_returns_everything():
    report = report_for(CHALCONE, CARBONYL_O)
    assert report.find("   ") == report.facts


def test_identity_and_electronic_open_expanded():
    """Progressive disclosure from the start. A hundred-odd facts rendered
    flat is a wall, and this is much cheaper to design in than retrofit."""
    assert DEFAULT_EXPANDED == frozenset({FactCategory.IDENTITY, FactCategory.ELECTRONIC})
    assert all(category in CATEGORY_ORDER for category in DEFAULT_EXPANDED)


def test_limitations_come_from_the_sources_without_a_generic_restatement():
    """Every fact already shows its own basis, so a blanket "some of these
    are heuristic" line only competes with the specific warnings a source
    actually wrote."""
    report = report_for(CHALCONE, CARBONYL_C)
    assert report.limitations
    assert not any(
        text.startswith("Some facts here were found by structural motif")
        for text in report.limitations
    )
    assert len(set(report.limitations)) == len(report.limitations), "no duplicates"
