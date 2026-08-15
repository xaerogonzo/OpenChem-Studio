"""The regulatory screen as a registered calculator.

Registering it is what makes it reach the Property panel, the Calculator
Inspector's 2D/3D highlighting and Thread 2's batch table without new UI --
so these tests go THROUGH THE REGISTRY rather than importing the compute
function. A calculator was once shipped bound to a shadowed same-named
function while every direct-import test passed.
"""

from __future__ import annotations

import json

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


def test_a_rulesets_limits_are_scope_and_are_marked_as_scope(registry):
    """ADVANCED, with the coverage notes and ruleset versions: per-ruleset
    scope, identical for every molecule, which is exactly the argument the
    test below makes about not repeating it down 50,000 batch rows.

    This governs the Details dialog, which hides ADVANCED facts by default.
    It does NOT shorten the Property panel, which renders every fact
    whatever its detail -- a first attempt at this test asserted it did."""
    from openchem.domain.report import Detail

    facts = _run(registry, ASPIRIN).facts
    limits = [fact for fact in facts if "does not cover" in fact.label]
    assert limits and all(fact.detail is Detail.ADVANCED for fact in limits)

    coverage = [fact for fact in facts if fact.label == "Coverage"]
    assert coverage and all(fact.detail is Detail.ADVANCED for fact in coverage), (
        "the siblings this is grouped with"
    )


def test_the_answer_comes_before_the_scope(registry):
    """The Property panel renders facts in order and shows all of them, so
    fact ORDER is what keeps a finding from being buried -- not the detail
    flag. Aspirin's screen carries 26 facts and the one that says what
    happened must not be twentieth."""
    facts = _run(registry, ASPIRIN).facts
    assert facts[0].label == "Regulatory Screen"

    findings = _run(registry, SARIN).facts
    assert findings[0].label == "Regulatory Screen"
    assert "Schedule 1" in findings[0].display_value


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


# --- Screening as of a date ---------------------------------------------


def _findings(result) -> list[str]:
    """The finding lines only.

    NOT `result.matched`, which is every line the screen produced -- and a
    ruleset's own `known_limitations` discuss entries by name, so searching
    the whole list for "A.13" finds Schedule 1 explaining its carbon limits
    rather than a finding. The first version of the test below did exactly
    that and failed against correct behaviour.
    """
    return [f.display_value for f in result.facts if f.label == "Regulatory Screen"]


def test_the_screen_can_be_asked_about_a_past_date(registry):
    """The question the whole feature exists for: was this listed when the
    sample was made. Schedule 1's A.13 entered force on 7 June 2020."""
    A13 = "CCN(CC)C(=NP(=O)(C)F)C"
    before = _findings(_run(registry, A13, as_of="2020-06-06"))
    after = _findings(_run(registry, A13, as_of="2020-06-07"))

    assert not any("A.13" in line for line in before), before
    assert any("A.13" in line for line in after), after
    # The day before is not an empty answer: Schedule 2's B.4, dated 1997,
    # matches the same structure. A per-ruleset or global filter would empty
    # this and still satisfy both assertions above.
    assert any("B.4" in line for line in before), before


def test_a_dated_run_says_which_date_even_when_it_matched(registry):
    """`summary()` carries the date too, but only reaches the panel when
    there are NO findings -- so without a fact of its own, a dated screen
    that matched would look exactly like an undated one."""
    facts = _run(registry, SARIN, as_of="2020-06-07").facts
    dated = [f for f in facts if f.label == "Screened as of"]

    assert [f.value for f in dated] == ["2020-06-07"]
    # STANDARD, beside "NOT checked" rather than beside the ruleset versions:
    # a date that changes what matched is not specialist information.
    from openchem.domain.report import Detail

    assert dated[0].detail is Detail.STANDARD
    assert facts[0].label == "Regulatory Screen", "the answer still comes first"


def test_an_invalid_date_does_not_fall_back_to_an_undated_screen(registry):
    """THE REFUSAL, and the failure mode it is written against.

    Someone typing `2019/13/99` is asking what applied in 2019. Running the
    current rulesets and attaching a warning answers a different question and
    presents it as the one they asked -- they would have to notice the
    caveat to know they had been given the wrong answer, and the discipline
    here is that a reader should not have to notice anything to be safe.

    So: FAILED, and nothing that could be read as a screen having happened.
    Mutate `parse_effective_date` to return None on a bad string and this is
    the only test in the suite that fails.
    """
    result = _run(registry, SARIN, as_of="2019/13/99")

    assert result.cache_state is CacheState.FAILED
    assert result.facts == (), [f.label for f in result.facts]
    assert not result.matched, "no findings may survive a refused date"
    assert "2019/13/99" in (result.error or "")
    assert any("No screening was performed" in text for text in result.limitations)


def test_a_refused_date_is_recorded_as_typed(registry):
    """The record has to say what was ASKED, not what could be made of it --
    otherwise a stored refusal cannot be told from a blank run."""
    parameters = _run(registry, SARIN, as_of="2019/13/99").provenance.parameters
    assert parameters["as_of"] == "2019/13/99"
    assert parameters["as_of_refused"] is True


def test_the_screened_date_is_persisted_as_a_string_not_a_date_object(registry):
    """Provenance parameters go straight into a saved project, and a value
    that will not serialise is DROPPED rather than stringified -- so a `date`
    object here would silently lose the one field saying which screen this
    was."""
    parameters = _run(registry, SARIN, as_of="2020-06-07").provenance.parameters

    assert parameters["as_of"] == "2020-06-07"
    assert json.loads(json.dumps(parameters))["as_of"] == "2020-06-07"


def test_a_dated_run_records_what_it_withheld(registry):
    """A screen that quietly drops rules and still reports "no matches in the
    4 rulesets consulted" is the silence-read-as-reassurance this engine
    exists against."""
    parameters = _run(registry, ASPIRIN, as_of="2020-06-06").provenance.parameters
    assert set(parameters["rules_withheld_by_date"]) == {
        "cwc-1-a-13", "cwc-1-a-14", "cwc-1-a-15", "cwc-1-a-16",
    }
    assert _run(registry, ASPIRIN).provenance.parameters["rules_withheld_by_date"] == []


def test_an_undated_run_is_unchanged(registry):
    """THE COMPATIBILITY INVARIANT FOR THE WHOLE FEATURE, compared across
    everything a caller can see rather than on the findings alone.

    A blank field and no field at all must be the same run, and neither may
    mention a date. If this ever diverges, every existing project, batch
    column and export changed meaning without anybody asking for it.
    """
    definition = next(
        d
        for category in registry.categories()
        for d in registry.by_category(category)
        if d.calculator_id == "regulatory_screen"
    )
    defaults = {p.name: p.default for p in definition.parameters}
    assert defaults["as_of"] == "", "blank is the default"

    without = dict(defaults)
    without.pop("as_of")
    mol = Chem.MolFromSmiles(SARIN)

    blank = registry.compute("regulatory_screen", mol, "mol-1", defaults)
    absent = registry.compute("regulatory_screen", mol, "mol-1", without)

    assert blank.matched == absent.matched
    assert blank.limitations == absent.limitations
    assert blank.cache_state is absent.cache_state
    assert [(f.label, f.value, f.detail) for f in blank.facts] == [
        (f.label, f.value, f.detail) for f in absent.facts
    ]
    assert blank.provenance.parameters == absent.provenance.parameters

    text = " ".join(blank.matched) + " ".join(f.label for f in blank.facts)
    assert "as of" not in text.lower(), text


def test_the_jurisdiction_filter_narrows_the_screen(registry):
    assert _run(registry, SARIN, jurisdiction="All jurisdictions").matched
    filtered = _run(registry, SARIN, jurisdiction="United States")
    # No US ruleset ships yet, so this must report that nothing was checked
    # rather than that nothing applies.
    assert "nothing was checked" in filtered.matched[0] or "consulted" in filtered.matched[0]
