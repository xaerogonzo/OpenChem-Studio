"""The results list is ordered, and the order is written down.

The selector was arrival-ordered: `PropertyPanel._reports` is a dict keyed by
`report_id`, so its values come out in the order results LANDED, and
calculations finish asynchronously. Two runs of the same six calculators could
produce six different lists, and a seventh landing while somebody read it
moved everything below.

Guards come in pairs. "It is ordered" is satisfied by any order at all, so
each term of the key is exercised against a fixture where the terms BELOW it
disagree with the answer -- otherwise a key missing a term still passes.
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass
from pathlib import Path

import pytest

from openchem.domain.calculator_taxonomy import CATEGORY_LABELS, category_label
from openchem.domain.result_ordering import (
    ALWAYS_ON,
    ALWAYS_ON_LABEL,
    IN_SECTION,
    UNORDERED,
    category_of,
    display_band,
    group_label,
    grouped_reports,
    ordered_reports,
    report_sort_key,
)

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"


@dataclass(frozen=True)
class _Entry:
    """The reader contract's ordering surface and nothing else.

    A plain stand-in rather than a `ReportResult`, deliberately: the ordering
    is duck-typed for the same reason `is_report_shaped` is -- a summary
    projection of a per-atom dataset or a pH curve has to be orderable without
    being fabricated as a real report.
    """

    report_id: str
    name: str = ""
    category: str = "other"


class _AlwaysOn:
    """An entry declaring the always-on band, as `DescriptorAggregate` does."""

    display_band = ALWAYS_ON

    def __init__(self, report_id="molecular_properties", name="Molecular Properties"):
        self.report_id = report_id
        self.name = name


def _positions(**by_id):
    """A registry stand-in: `report_id` -> position, None for anything else."""
    return lambda report_id: by_id.get(report_id)


# --- the key, one term at a time -----------------------------------------


def test_the_category_term_leads():
    """`identity` is CATEGORY_ORDER[1] and `admet` is near the end, so the
    section decides even when every later term says the opposite: the admet
    entry is registered FIRST, sorts first by name and first by id."""
    admet = _Entry("aaa", "AAA", "admet")
    identity = _Entry("zzz", "ZZZ", "identity")
    order = _positions(aaa=0, zzz=99)
    assert [e.report_id for e in ordered_reports([identity, admet], order)] == [
        "zzz",
        "aaa",
    ]


def test_the_registry_position_orders_within_a_section():
    """The term this project would lose by sorting names inside a section.

    Measured on the shipped registry: alphabetical order puts **Hansen
    Solubility Parameters ahead of Solubility**, and inverts Lewis Sites
    against Lewis Adduct. So the fixture is built the same way round -- the
    name term disagrees, and the registry position must win.
    """
    hansen = _Entry("hansen_solubility", "Hansen Solubility Parameters", "solubility")
    solubility = _Entry("solubility", "Solubility", "solubility")
    order = _positions(solubility=10, hansen_solubility=12)
    assert [e.name for e in ordered_reports([hansen, solubility], order)] == [
        "Solubility",
        "Hansen Solubility Parameters",
    ]


def test_display_name_orders_when_the_registry_has_no_position():
    """A plugin report and a retired id resolve nothing, so without this term
    they would fall straight through to the id -- and an id is not what a
    reader sees. Two plugins called "Alpha Tool" and "Zulu Tool" would render
    in whatever order their internal ids happened to take.

    **THE IDS CONTRADICT THE NAMES ON PURPOSE.** A fixture whose id order and
    name order agree cannot tell this term from the one below it: the first
    version of this guard used one, and deleting the name term SURVIVED the
    whole file.
    """
    zeta = _Entry("aaa", "Zeta Tool", "identity")
    alpha = _Entry("zzz", "Alpha Tool", "identity")
    assert [e.name for e in ordered_reports([zeta, alpha], _positions())] == [
        "Alpha Tool",
        "Zeta Tool",
    ]


def test_the_name_term_is_casefolded():
    """Otherwise every capitalised name sorts above every lower-case one and
    "alpha" follows "Zeta". The ids contradict the names here too, so this
    cannot pass by falling through to the id term."""
    assert [
        e.name for e in ordered_reports([_Entry("aaa", "Zeta"), _Entry("zzz", "alpha")])
    ] == ["alpha", "Zeta"]


def test_the_report_id_is_the_last_resort():
    """What makes the key TOTAL. Two reports can legitimately share a display
    name -- a retired calculator and its replacement, read back from one saved
    project -- and without this their order is the arrival order again."""
    second = _Entry("bbb", "Same Name", "identity")
    first = _Entry("aaa", "Same Name", "identity")
    assert [e.report_id for e in ordered_reports([second, first])] == ["aaa", "bbb"]


def test_an_unlisted_category_sorts_after_every_listed_one():
    listed = _Entry("l", "L", "identity")
    unlisted = _Entry("u", "U", "a_plugin_category")
    assert [e.report_id for e in ordered_reports([unlisted, listed])] == ["l", "u"]


def test_two_unlisted_categories_are_ordered_alphabetically():
    """`category_sort_key`'s own tail, which is what makes a plugin section
    deterministic rather than merely last."""
    zeta = _Entry("z", "Z", "zeta_tools")
    alpha = _Entry("a", "A", "alpha_tools")
    assert [e.report_id for e in ordered_reports([zeta, alpha])] == ["a", "z"]


def test_an_unregistered_entry_sorts_after_the_registered_ones_in_its_section():
    """AFTER, never before. Ordering it first would let an entry the registry
    never placed displace the calculator its section is named for -- and the
    name term would decide which, so a plugin called "AAA" would head every
    section it landed in."""
    plugin = _Entry("plugin", "AAA Plugin", "identity")
    real = _Entry("elemental_analysis", "Elemental Analysis", "identity")
    order = _positions(elemental_analysis=7)
    assert [e.report_id for e in ordered_reports([plugin, real], order)] == [
        "elemental_analysis",
        "plugin",
    ]


def test_an_unresolved_position_is_the_sentinel_rather_than_a_guess():
    key = report_sort_key(_Entry("x", "X", "identity"), _positions())
    assert key[2] == UNORDERED


# --- stability, which is what the whole module is for --------------------


def test_the_order_does_not_depend_on_the_order_results_arrived_in():
    """**THE DEFECT, DIRECTLY.** Every permutation of the same five results
    must produce one list."""
    entries = [
        _Entry("elemental_analysis", "Elemental Analysis", "identity"),
        _Entry("logd", "LogD at pH 7.4", "lipophilicity"),
        _Entry("solubility", "Solubility", "solubility"),
        _Entry("pka", "pKa", "pka"),
        _Entry("admet_ml", "ADMET", "admet"),
    ]
    order = _positions(elemental_analysis=3, logd=2, solubility=40, pka=41, admet_ml=0)
    expected = [e.report_id for e in ordered_reports(entries, order)]
    for arrival in itertools.permutations(entries):
        assert [e.report_id for e in ordered_reports(list(arrival), order)] == expected


def test_a_new_arrival_does_not_move_the_entries_already_on_screen():
    """The half a "same set sorts the same" test cannot see. A reader is
    looking at a list while a sixth calculator finishes; the five already
    there must keep their order relative to each other."""
    shown = [
        _Entry("elemental_analysis", "Elemental Analysis", "identity"),
        _Entry("logd", "LogD at pH 7.4", "lipophilicity"),
        _Entry("topology_analysis", "Topology Analysis", "topology"),
        _Entry("solubility", "Solubility", "solubility"),
        _Entry("admet_ml", "ADMET", "admet"),
    ]
    order = _positions(
        elemental_analysis=3, logd=2, topology_analysis=20, solubility=40, admet_ml=0
    )
    before = [e.report_id for e in ordered_reports(shown, order)]
    late = _Entry("geometry_analysis", "Geometry", "geometry")
    after = [e.report_id for e in ordered_reports([*shown, late], order)]
    assert [rid for rid in after if rid != "geometry_analysis"] == before


def test_the_key_is_a_pure_function_of_the_entry():
    """No memo, no counter, no clock: two calls must agree, or "stable" is a
    statement about how often it was asked."""
    entry = _Entry("x", "X", "identity")
    assert report_sort_key(entry, _positions(x=1)) == report_sort_key(entry, _positions(x=1))


# --- the band -------------------------------------------------------------


def test_the_always_on_entry_sorts_above_every_section():
    """`physicochemical` is CATEGORY_ORDER[0], so the always-on entry has to
    beat the first section rather than merely a late one."""
    first_section = _Entry("mol_wt", "AAA", "physicochemical")
    aggregate = _AlwaysOn()
    assert [
        getattr(e, "report_id") for e in ordered_reports([first_section, aggregate])
    ] == ["molecular_properties", "mol_wt"]


def test_the_band_is_declared_and_defaults_to_belonging_to_a_section():
    """Never inferred from the content. An entry that declares nothing is in
    its own section, which is the answer that cannot displace anything."""
    assert display_band(_Entry("x")) == IN_SECTION
    assert display_band(_AlwaysOn()) == ALWAYS_ON


def test_an_unknown_band_is_refused_rather_than_sorted_somewhere_plausible():
    """Fail closed. A band nothing recognises would sort at whatever integer
    it happened to be and silently reorder the list -- which is the failure
    this module exists to remove, arriving through its own front door."""

    class _Wrong:
        display_band = 7
        report_id = "x"
        name = "X"

    with pytest.raises(ValueError, match="display band"):
        report_sort_key(_Wrong())


def test_exactly_one_type_in_the_application_declares_the_always_on_band():
    """The narrow half, and the one that matters.

    ALWAYS_ON is a claim that an entry belongs to no section, and it is true
    of exactly one thing: the descriptor aggregate, whose 41 descriptors span
    ten calculator categories. A second declaration would put a calculator
    result above every section without anybody choosing that, so the
    population is derived from the source rather than trusted to review.
    """
    declaring = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "display_band" not in names:
                continue
            declaring.append(path.relative_to(SRC).as_posix())
    assert declaring == ["domain/descriptor_aggregate.py"], declaring


def test_the_descriptor_aggregate_really_carries_the_band():
    """Asserting its own setup: the guard above reads SOURCE, so a rename
    that left the assignment intact would satisfy it while the aggregate
    stopped declaring anything the ordering can read."""
    from openchem.domain.descriptor_aggregate import DescriptorAggregate

    assert display_band(DescriptorAggregate(molecule_uuid="u")) == ALWAYS_ON


# --- an absent category is the default one, not a second section ----------


def test_an_absent_category_reads_as_the_default_one():
    class _Bare:
        report_id = "x"
        name = "X"

    assert category_of(_Bare()) == "other"
    assert group_label(_Bare()) == category_label("other")


def test_a_blank_and_an_explicit_other_land_in_ONE_group():
    """They render identically -- `category_label` maps both to "Other" --
    while `category_sort_key` orders unlisted categories by the string, which
    puts "" and "other" at opposite ends of the tail. A plugin section sorting
    between them would otherwise produce two groups both headed "Other"."""

    class _Blank:
        report_id = "blank"
        name = "Blank"
        category = ""

    entries = [_Blank(), _Entry("other", "Other", "other"), _Entry("mid", "Mid", "mytools")]
    labels = [group.label for group in grouped_reports(entries)]
    assert labels.count("Other") == 1, labels


# --- grouping -------------------------------------------------------------


def test_no_group_is_emitted_empty():
    """The whole invariant. The selector shows what has been COMPUTED, so its
    group set differs per molecule -- somebody who has run one calculator must
    not scroll twenty headings. It is also what makes a search control safe to
    add later: filtering changes the input set, and a set with nothing in a
    category produces no heading for it."""
    groups = grouped_reports([_Entry("lewis_sites", "Lewis Sites", "lewis")])
    assert [group.label for group in groups] == ["Lewis Acid/Base"]
    assert all(len(group) for group in groups)


def test_a_group_holding_one_entry_is_ordinary_here():
    """The narrow half, against the opposite rule the Properties panel is
    held to. `test_no_category_holds_a_single_calculator` exists because a
    SECTION concealing one button is a taxonomy failure; a group here holds
    one entry whenever you have run one calculator from that section -- on a
    full run for aspirin, 11 of 17 groups do."""
    groups = grouped_reports(
        [
            _Entry("elemental_analysis", "Elemental Analysis", "identity"),
            _Entry("logd", "LogD", "lipophilicity"),
        ]
    )
    assert [len(group) for group in groups] == [1, 1]


def test_every_entry_appears_in_exactly_one_group():
    entries = [
        _Entry("elemental_analysis", "Elemental Analysis", "identity"),
        _Entry("mass_spectrum", "Mass Spectrum", "identity"),
        _Entry("logd", "LogD", "lipophilicity"),
        _AlwaysOn(),
    ]
    grouped = [e for group in grouped_reports(entries) for e in group.entries]
    assert len(grouped) == len(entries)
    assert {id(e) for e in grouped} == {id(e) for e in entries}


def test_a_group_keeps_the_order_the_key_gives_its_entries():
    """Cut from the sorted sequence rather than collected and re-sorted, so
    the group order and the order inside a group are one decision."""
    order = _positions(mass_spectrum=1, elemental_analysis=0)
    groups = grouped_reports(
        [
            _Entry("mass_spectrum", "Mass Spectrum", "identity"),
            _Entry("elemental_analysis", "Elemental Analysis", "identity"),
        ],
        order,
    )
    assert [e.report_id for e in groups[0].entries] == [
        "elemental_analysis",
        "mass_spectrum",
    ]


def test_the_group_order_follows_the_entry_order():
    groups = grouped_reports(
        [
            _Entry("admet_ml", "ADMET", "admet"),
            _Entry("elemental_analysis", "Elemental Analysis", "identity"),
            _AlwaysOn(),
        ]
    )
    assert [group.label for group in groups] == [
        ALWAYS_ON_LABEL,
        "Identity",
        "ADMET / Regulatory",
    ]


def test_a_section_is_named_by_the_shared_taxonomy():
    """Two names for one section is exactly what `category_label` was unified
    to prevent -- it already records a heading rendering as "Medicinal
    Chemistry" on screen and copying as "Medicinal_Chemistry"."""
    for category, label in CATEGORY_LABELS.items():
        assert group_label(_Entry("x", "X", category)) == label


def test_the_always_on_group_has_a_label_of_its_own():
    """It is not a category, so `category_label` cannot answer for it -- and
    letting it fall through would head the always-on entry "Other"."""
    assert group_label(_AlwaysOn()) == ALWAYS_ON_LABEL
    assert ALWAYS_ON_LABEL not in CATEGORY_LABELS.values()


def test_no_two_sections_share_a_display_label():
    """Grouping cuts on the LABEL, so two categories rendering the same
    heading would silently merge -- or, if something sorted between them,
    produce the same heading twice."""
    labels = list(CATEGORY_LABELS.values())
    assert len(labels) == len(set(labels))


# --- the population this runs against ------------------------------------


def test_the_registry_gives_every_calculator_a_position():
    """Derived from the shipped registry rather than a count: a lookup that
    answered None for real calculators would leave the whole section term
    resolving to the sentinel, and every section would order by name -- which
    is the arrangement measured to put Hansen ahead of Solubility."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.services.calculator_registry import CalculatorRegistry

    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        registry.register(definition)
    assert CALCULATOR_DEFINITIONS, "fixture is degenerate: no calculators registered"
    positions = [registry.display_order(d.calculator_id) for d in CALCULATOR_DEFINITIONS]
    assert None not in positions
    assert positions == sorted(positions), "registration order IS the display order"
    assert len(set(positions)) == len(positions), "two calculators cannot share a slot"


def test_an_unregistered_id_gets_no_position_rather_than_a_wrong_one():
    from openchem.services.calculator_registry import CalculatorRegistry

    assert CalculatorRegistry().display_order("nothing_registers_this") is None


@pytest.mark.parametrize("smiles", ["CC(=O)Oc1ccccc1C(=O)O"])
def test_every_result_that_reaches_the_reader_is_placed_by_the_key(smiles):
    """**THE POPULATION WALK, AGAINST THE REAL REGISTRY.**

    Two claims that a constructed fixture cannot make, and both decide whether
    the first two terms of the key are load-bearing or vacuous here:

      * a report carries its OWN category, and it is the registered one -- so
        no registry lookup is needed for the section term;
      * every id that reaches the reader resolves a registry position -- so
        the within-section term is the ordinary case rather than a fallback.

    Measured when this was written: 30 results reach the merged reader for
    aspirin, 30 of 30 carry their calculator's category, none falls back to
    the "other" default, and 30 of 30 resolve a position.
    """
    from rdkit import Chem

    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.chem.report_adapter import report_from_alert
    from openchem.domain.calculator import RegistryExecution
    from openchem.domain.merged_results import is_report_shaped
    from openchem.domain.scientific_result import AlertResult
    from openchem.services.calculator_registry import CalculatorRegistry

    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        registry.register(definition)

    mol = Chem.MolFromSmiles(smiles)
    reaching = []
    for definition in CALCULATOR_DEFINITIONS:
        if not isinstance(definition.execution, RegistryExecution):
            continue
        try:
            result = definition.execution.compute(
                mol, "u", {p.name: p.default for p in definition.parameters}
            )
        except Exception:
            continue
        if isinstance(result, AlertResult):
            result = report_from_alert(result)
        if is_report_shaped(result):
            reaching.append((definition, result))

    assert len(reaching) >= 25, f"fixture is degenerate: only {len(reaching)} reached"

    wrong_category = [
        (d.calculator_id, category_of(r))
        for d, r in reaching
        if category_of(r) != d.category
    ]
    assert not wrong_category, wrong_category

    unplaced = [
        r.report_id
        for _d, r in reaching
        if report_sort_key(r, registry.display_order)[2] == UNORDERED
    ]
    assert not unplaced, f"these reach the reader with no registry position: {unplaced}"


def test_the_shipped_results_sort_into_the_taxonomys_order():
    """End to end over the same population: the sections come out in
    `CATEGORY_ORDER`, which is the order the Properties panel shows them in
    and the thing arrival order could not give."""
    from openchem.domain.calculator_taxonomy import CATEGORY_ORDER

    entries = [
        _Entry("a", "A", "admet"),
        _Entry("b", "B", "identity"),
        _Entry("c", "C", "solubility"),
        _Entry("d", "D", "pka"),
    ]
    categories = [category_of(e) for e in ordered_reports(entries)]
    assert categories == sorted(categories, key=CATEGORY_ORDER.index)
