"""The regulatory screen as a registered calculator.

Registering it is what makes it reach the Property panel, the Calculator
Inspector's 2D/3D highlighting and Thread 2's batch table without new UI --
so these tests go THROUGH THE REGISTRY rather than importing the compute
function. A calculator was once shipped bound to a shadowed same-named
function while every direct-import test passed.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.regulatory.calculator import reset_engine
from openchem.domain.common import CacheState

SARIN = "CC(C)OP(C)(=O)F"
DFP = "CC(C)OP(=O)(F)OC(C)C"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


@pytest.fixture(scope="module")
def registry():
    reset_engine()
    return build_service_container().calculator_registry


def _run(registry, smiles: str, **overrides):
    definition = next(
        d
        for category in registry.categories()
        for d in registry.by_category(category)
        if d.calculator_id == "regulatory_screen"
    )
    parameters = {p.name: p.default for p in definition.parameters}
    parameters.update(overrides)
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return registry.compute("regulatory_screen", mol, "mol-1", parameters)


def test_it_runs_through_the_registry(registry):
    result = _run(registry, SARIN)
    assert result.cache_state is CacheState.COMPLETED
    assert result.report_id == "regulatory_screen"


def test_a_scheduled_structure_is_reported_with_its_framework(registry):
    lines = _run(registry, SARIN).matched
    joined = " ".join(lines)
    assert "Schedule 1" in joined
    assert "international" in joined
    assert "structural_family" in joined


def test_every_line_is_ascii(registry):
    """These reach `AlertResult.matched`, which goes to Qt, logs and console
    streams. A Windows cp1252 stream raises on a tick or an em-dash --
    `test_naming_result_lines_stay_ascii` exists because that was hit three
    times in one session."""
    for smiles in (SARIN, DFP, ASPIRIN):
        for line in _run(registry, smiles).matched:
            line.encode("cp1252")


def test_a_structure_with_no_findings_still_says_what_was_checked(registry):
    """THE HONESTY REQUIREMENT. A blank cell in a regulatory column is
    exactly the silence-read-as-reassurance the engine exists to prevent,
    so the no-findings case carries one line naming how many rulesets ran."""
    lines = _run(registry, ASPIRIN).matched
    assert lines
    assert "consulted" in lines[0]


def test_no_output_ever_claims_compliance(registry):
    for smiles in (SARIN, DFP, ASPIRIN):
        text = " ".join(_run(registry, smiles).matched).lower()
        assert "compliant" not in text
        assert "not controlled" not in text


def test_the_near_miss_explains_which_feature_is_absent(registry):
    """DFP has sarin's phosphoryl, fluorine and alkoxy and lacks the P-C
    bond. "No match" alone leaves a user unable to see where the boundary
    runs."""
    lines = _run(registry, DFP).matched
    near = [line for line in lines if line.startswith("Near miss")]
    assert near
    assert any("lacks" in line and "P-alkyl" in line for line in near)


def test_near_misses_can_be_turned_off(registry):
    lines = _run(registry, DFP, include_near_misses=False).matched
    assert not [line for line in lines if line.startswith("Near miss")]


def test_an_approximate_rule_carries_its_limitation_into_the_result(registry):
    """Chlorambucil is a licensed medicine that the nitrogen-mustard pattern
    matches. The finding must arrive with the caveat -- a bare match here
    would read as an accusation."""
    result = _run(registry, "OC(=O)CCCc1ccc(cc1)N(CCCl)CCCl")

    # A fact with its own label now, rather than an indented line of prose
    # in a string list -- so a reader can see it is a caveat rather than
    # a second finding, and an export keeps them apart.
    caveats = [fact for fact in result.facts if fact.label == "Limitation"]
    assert caveats, [fact.label for fact in result.facts]


def test_a_rulesets_own_limits_reach_the_screen(registry):
    """`known_limitations` was loaded off disk, stored on the Ruleset, and
    displayed NOWHERE -- the same gap the coverage notes were in before they
    became facts. It is where a ruleset says what it does not encode ("the
    2019 additions are not encoded", "listing is not a prohibition"), so a
    rule failing to match says nothing about those. Silence there is the
    silence-read-as-reassurance this whole engine is written against."""
    facts = _run(registry, ASPIRIN).facts
    limits = [fact for fact in facts if "does not cover" in fact.label]

    assert limits, [fact.label for fact in facts]
    assert any("2019" in fact.value for fact in limits), "Schedule 1 says so"
    assert any("not a prohibition" in fact.value.lower() for fact in limits), "Schedule 3 says so"


def test_a_rulesets_limits_are_not_buried_as_specialist_detail(registry):
    """Same reasoning as "NOT checked", which is deliberately STANDARD: a
    gap in coverage is not specialist information. Ruleset versions and
    coverage percentages are ADVANCED because they are bookkeeping; what a
    ruleset cannot tell you is not."""
    from openchem.domain.report import Detail

    limits = [fact for fact in _run(registry, ASPIRIN).facts if "does not cover" in fact.label]
    assert limits and all(fact.detail is Detail.STANDARD for fact in limits)


# --- Provenance ---------------------------------------------------------


def test_coverage_travels_in_provenance_not_in_every_row(registry):
    """Scope is a property of the RULESETS, identical for every molecule.
    Repeating it down 50,000 batch rows is noise that trains people to stop
    reading, so it lives where a view can show it once."""
    parameters = _run(registry, ASPIRIN).provenance.parameters
    assert parameters["rulesets"]
    assert parameters["coverage"]
    assert "domains_not_checked" in parameters


def test_unchecked_domains_are_named_in_provenance(registry):
    """A user seeing no food-additive findings should learn that no
    food-additive ruleset was loaded."""
    parameters = _run(registry, ASPIRIN).provenance.parameters
    assert "food" in parameters["domains_not_checked"]


def test_the_jurisdiction_filter_narrows_the_screen(registry):
    assert _run(registry, SARIN, jurisdiction="All jurisdictions").matched
    filtered = _run(registry, SARIN, jurisdiction="United States")
    # No US ruleset ships yet, so this must report that nothing was checked
    # rather than that nothing applies.
    assert "nothing was checked" in filtered.matched[0] or "consulted" in filtered.matched[0]
