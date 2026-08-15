"""Screening structures against rulesets.

The behaviours pinned here are mostly about what the engine REFUSES to
say: it never concludes, it reports which rulesets it consulted, it keeps
unchecked domains visible, and it will not claim a jurisdiction is silent
when no ruleset from that jurisdiction was loaded.
"""

from __future__ import annotations

from datetime import date

import pytest
from rdkit import Chem

from openchem.chem.regulatory.engine import (
    EffectiveDateError,
    RegulatoryEngine,
    parse_effective_date,
    resolve_effective_date,
    rule_applies_at,
)
from openchem.chem.regulatory.types import (
    Domain,
    Jurisdiction,
    LegalSource,
    MachineInterpretation,
    MatchType,
    Rule,
    RuleConfidence,
    Ruleset,
    RulesetCoverage,
)

SARIN = "CC(C)OP(C)(=O)F"
#: A phosphoFLUORIDATE, not a phosphoNOfluoridate -- no P-C bond, so NOT
#: Schedule 1. The near-miss the whole explainer exists for.
DFP = "CC(C)OP(=O)(F)OC(C)C"

#: Authored as a FEATURE CHECKLIST rather than one monolithic SMARTS, so a
#: near miss can say which feature is absent.
SCHEDULE_1_A_1 = {
    "op": "all",
    "of": [
        {"op": "contains", "smarts": "P=O", "label": "phosphoryl (P=O)"},
        {"op": "contains", "smarts": "PF", "label": "P-F bond"},
        {"op": "contains", "smarts": "PO[CX4]", "label": "O-alkyl ester"},
        {"op": "contains", "smarts": "P[CX4]", "label": "P-C bond"},
        {"op": "element_count", "element": "C", "max": 10,
         "label": "total carbons <= 10"},
    ],
}


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


def _rule(expression=None, inchikeys=(), jurisdiction=Jurisdiction.INTERNATIONAL,
          domain=Domain.CHEMICAL_WEAPONS, match_type=MatchType.STRUCTURAL_FAMILY,
          rule_id="r1", effective_date="") -> Rule:
    return Rule(
        rule_id=rule_id,
        display_name=f"rule {rule_id}",
        domain=domain,
        jurisdiction=jurisdiction,
        match_type=match_type,
        legal=LegalSource(
            authority="test", instrument="test", section="1",
            effective_date=effective_date,
        ),
        interpretation=MachineInterpretation(
            expression=expression or "",
            inchikeys=tuple(inchikeys),
            confidence=RuleConfidence.EXACT,
        ),
    )


def _ruleset(*rules: Rule, ruleset_id="rs", jurisdiction=Jurisdiction.INTERNATIONAL,
             domain=Domain.CHEMICAL_WEAPONS, version="1", supersedes="",
             effective_date="") -> Ruleset:
    return Ruleset(
        ruleset_id=ruleset_id,
        display_name=f"ruleset {ruleset_id}",
        domain=domain,
        jurisdiction=jurisdiction,
        version=version,
        supersedes=supersedes,
        effective_date=effective_date,
        rules=tuple(rules),
        coverage=RulesetCoverage(total_entries=len(rules), resolved=len(rules)),
    )


# --- Matching -----------------------------------------------------------


def test_a_scheduled_structure_is_reported_with_its_atoms():
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    report = engine.screen(_mol(SARIN))

    assert report.matched
    assert report.findings[0].match_type is MatchType.STRUCTURAL_FAMILY
    # Atoms are carried so a view can colour them through the same per-atom
    # path the annotation calculators use.
    assert report.findings[0].atoms


def test_the_explanation_lists_every_condition():
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    lines = engine.screen(_mol(SARIN)).findings[0].explanation
    assert len(lines) == 5
    assert all(line.startswith("+") for line in lines)


def test_explanation_lines_stay_ascii():
    """These reach `AlertResult.matched`, which goes to Qt, to logs and to
    console streams. A Windows cp1252 stream raises on an em-dash or a
    tick -- `test_naming_result_lines_stay_ascii` exists because that was
    hit three times in one session."""
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    for line in engine.screen(_mol(SARIN)).findings[0].explanation:
        line.encode("cp1252")
    for line in engine.screen(_mol(DFP)).near_misses[0].rule.display_name:
        line.encode("cp1252")


# --- "Why didn't this match?" -------------------------------------------


def test_a_near_miss_names_the_feature_that_is_absent():
    """The most useful thing a screen can tell a legitimate user. DFP has
    the phosphoryl, the fluorine and the alkoxy, and lacks only the P-C
    bond -- which IS the regulatory distinction."""
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    report = engine.screen(_mol(DFP))

    assert not report.matched
    assert len(report.near_misses) == 1
    near = report.near_misses[0]
    assert near.distance == 1
    failed = [o.label for o in near.outcomes if not o.passed]
    assert failed == ["P-C bond"]


def test_an_unrelated_structure_is_not_reported_as_near():
    """THE BUG THIS GUARDS. A numeric bound passes vacuously -- ethanol
    satisfies "10 carbons or fewer" -- so counting failures alone reported
    ethanol as one predicate from a nerve-agent schedule. A near miss now
    requires at least one predicate that actually MATCHED ATOMS."""
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    report = engine.screen(_mol("CCO"))

    assert not report.matched
    assert report.near_misses == ()


def test_near_misses_sort_nearest_first():
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    report = engine.screen(_mol("COP(=O)(OC)OC"))  # trimethyl phosphate
    assert report.near_misses[0].distance == 2


# --- Salts and isomers --------------------------------------------------


def test_a_salt_matches_a_rule_written_for_the_free_base():
    """Regulations reach "and its salts". Without stripping, every rule
    would need a hand-written entry per counter-ion."""
    base = _mol("CNC(C)Cc1ccccc1")
    key = Chem.MolToInchiKey(base)
    engine = RegulatoryEngine([_ruleset(_rule(inchikeys=(key,),
                                              match_type=MatchType.IDENTITY))])

    assert engine.screen(base).matched
    assert engine.screen(_mol("CNC(C)Cc1ccccc1.Cl")).matched


def test_an_isomer_matches_but_is_labelled_as_one():
    """"and its isomers" is real, but enantiomers can differ enormously in
    effect -- so a stereo-insensitive hit is reported as its own kind of
    match rather than silently as an exact identity."""
    listed = Chem.MolToInchiKey(_mol("C[C@H](N)C(=O)O"))
    engine = RegulatoryEngine([_ruleset(_rule(inchikeys=(listed,),
                                              match_type=MatchType.IDENTITY))])

    exact = engine.screen(_mol("C[C@H](N)C(=O)O")).findings[0]
    assert "exact identity" in exact.outcomes[0].label

    other = engine.screen(_mol("C[C@@H](N)C(=O)O")).findings[0]
    assert "different stereochemistry" in other.outcomes[0].label


def test_a_listed_PRECURSOR_is_not_reported_as_an_identity_match():
    """`_apply_identity` used to hardcode `MatchType.IDENTITY`, ignoring
    what the rule declared, while the structural path used `rule.match_type`.

    So a precursor matched by InChIKey reported "identity" on its finding
    line and had its legitimate uses printed a line later by
    `_finding_lines`, which reads the RULE -- one result contradicting
    itself. Invisible until a shipped ruleset carried an identity entry;
    every UN 1988 Table entry is exactly that.

    HOW a structure was matched is in the outcomes. WHAT the regulation
    claims about it is the match type, and only the rule knows that.
    """
    acetic_anhydride = _mol("CC(=O)OC(C)=O")
    key = Chem.MolToInchiKey(acetic_anhydride)
    engine = RegulatoryEngine([_ruleset(_rule(inchikeys=(key,),
                                              match_type=MatchType.PRECURSOR))])

    finding = engine.screen(acetic_anhydride).findings[0]
    assert finding.match_type is MatchType.PRECURSOR
    # The salt-normalised route is still reported -- as evidence, where it
    # belongs, rather than as the claim.
    assert "identity" in finding.outcomes[0].label


def test_an_identity_rule_still_reports_identity():
    """The CONTROL. Without it a fix that answered PRECURSOR unconditionally,
    or read some unrelated field, would satisfy the test above."""
    ephedrine = _mol("CNC(C)C(O)c1ccccc1")
    engine = RegulatoryEngine([_ruleset(_rule(inchikeys=(Chem.MolToInchiKey(ephedrine),),
                                              match_type=MatchType.IDENTITY))])

    assert engine.screen(ephedrine).findings[0].match_type is MatchType.IDENTITY


def test_an_isomer_of_a_precursor_is_still_a_precursor():
    """The second identity branch had the same hardcoded type, and a fix
    applied to only one of them looks exactly like a fix. This file already
    records that shape twice."""
    listed = Chem.MolToInchiKey(_mol("C[C@H](N)C(=O)O"))
    engine = RegulatoryEngine([_ruleset(_rule(inchikeys=(listed,),
                                              match_type=MatchType.PRECURSOR))])

    finding = engine.screen(_mol("C[C@@H](N)C(=O)O")).findings[0]
    assert "different stereochemistry" in finding.outcomes[0].label
    assert finding.match_type is MatchType.PRECURSOR


def test_an_unrelated_structure_does_not_match_an_identity_rule():
    listed = Chem.MolToInchiKey(_mol("CCO"))
    engine = RegulatoryEngine([_ruleset(_rule(inchikeys=(listed,),
                                              match_type=MatchType.IDENTITY))])
    assert not engine.screen(_mol("c1ccccc1")).matched


# --- What the report refuses to say -------------------------------------


def test_a_report_with_no_findings_states_what_was_consulted():
    """The dangerous failure of a screening tool is silence read as
    reassurance. "No matches" alone is not a usable answer."""
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    report = engine.screen(_mol("CCO"))

    assert "consulted" in report.summary()
    assert report.coverage_notes()


def test_an_empty_engine_says_nothing_was_checked():
    report = RegulatoryEngine().screen(_mol("CCO"))
    assert "nothing was checked" in report.summary()


def test_unchecked_domains_are_listed():
    """A user seeing no food-additive findings should learn that no
    food-additive ruleset was loaded, not infer that none applied."""
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    report = engine.screen(_mol("CCO"))

    assert Domain.FOOD in report.domains_without_rulesets
    assert Domain.CHEMICAL_WEAPONS not in report.domains_without_rulesets
    assert any("Not checked" in note for note in report.coverage_notes())


def test_no_report_ever_claims_compliance():
    """The vocabulary is matched rules, rulesets consulted, coverage. Never
    "compliant", never "not controlled"."""
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    for smiles in (SARIN, DFP, "CCO"):
        text = " ".join(
            [engine.screen(_mol(smiles)).summary(), *engine.screen(_mol(smiles)).coverage_notes()]
        ).lower()
        assert "compliant" not in text
        assert "not controlled" not in text
        assert "legal" not in text


# --- Jurisdictions ------------------------------------------------------


def test_disagreement_between_jurisdictions_is_reported_not_resolved():
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, jurisdiction=Jurisdiction.EU, rule_id="eu"),
                 ruleset_id="eu", jurisdiction=Jurisdiction.EU),
        _ruleset(_rule("[Br]", jurisdiction=Jurisdiction.US, rule_id="us"),
                 ruleset_id="us", jurisdiction=Jurisdiction.US),
    ])
    report = engine.screen(_mol(SARIN))

    assert report.conflicts
    assert Jurisdiction.EU in report.conflicts[0].matched_in
    assert Jurisdiction.US in report.conflicts[0].no_match_in


def test_a_jurisdiction_that_was_never_consulted_is_not_called_silent():
    """"No match in Japan" is meaningless when no Japanese ruleset was
    loaded, and would be the same silence-as-reassurance error."""
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, jurisdiction=Jurisdiction.EU),
                 ruleset_id="eu", jurisdiction=Jurisdiction.EU),
    ])
    report = engine.screen(_mol(SARIN))
    assert report.conflicts == ()


def test_screening_can_be_filtered_to_relevant_jurisdictions():
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, jurisdiction=Jurisdiction.EU),
                 ruleset_id="eu", jurisdiction=Jurisdiction.EU),
    ])
    assert not engine.screen(_mol(SARIN), jurisdictions={Jurisdiction.US}).matched
    assert engine.screen(_mol(SARIN), jurisdictions={Jurisdiction.EU}).matched


# --- Ruleset lifecycle --------------------------------------------------


def test_a_revision_supersedes_the_version_it_replaces():
    engine = RegulatoryEngine()
    engine.add_ruleset(_ruleset(_rule("[Br]"), ruleset_id="old", version="1"))
    engine.add_ruleset(
        _ruleset(_rule("[Cl]"), ruleset_id="new", version="2", supersedes="old")
    )
    assert [r.ruleset_id for r in engine.rulesets] == ["new"]


def test_a_malformed_user_rule_is_skipped_rather_than_failing_the_screen():
    """A build validates shipped rulesets against SUPPORTED_OPS, so this
    can only be a user file -- and one bad entry in someone's own ruleset
    must not take down the whole screen."""
    engine = RegulatoryEngine([
        _ruleset(_rule({"op": "no_such_op"}, rule_id="bad"),
                 _rule(SCHEDULE_1_A_1, rule_id="good"))
    ])
    assert engine.screen(_mol(SARIN)).matched


def test_screening_none_returns_an_empty_report_rather_than_raising():
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    assert not engine.screen(None).matched


# --- Screening as of a date ---------------------------------------------
#
# ON FIXTURES RATHER THAN THE SHIPPED RULESETS, and three of these could not
# be written any other way. The build writes a ruleset's date onto every rule
# that does not declare one, so shipped data cannot show the runtime fallback
# working or failing; and every shipped rule is dated in the past, so nothing
# there can tell `as_of=None` apart from `as_of=today`. The shipped-data
# half lives in `test_regulatory_rulesets.py`, where it belongs.


def test_an_absent_date_is_a_value_and_a_malformed_one_is_an_error():
    """THE THREE STATES, which must not collapse into two.

    Absence is a VALUE and malformation is an EXCEPTION, which is what lets
    the build and the engine share one parser while doing opposite things
    with a bad date: the build refuses it, the engine records it and carries
    on. A parser returning None for both would make those indistinguishable
    and silently let a broken date ship as a timeless one.
    """
    assert parse_effective_date("") is None
    assert parse_effective_date("   ") is None
    assert parse_effective_date("2020-06-07") == date(2020, 6, 7)

    for bad in ("2019/13/99", "7 June 2020", "2020-13-01", "soon"):
        with pytest.raises(EffectiveDateError):
            parse_effective_date(bad)


def test_a_rule_dated_after_the_screen_is_withheld():
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, effective_date="2020-06-07"))
    ])
    assert not engine.screen(_mol(SARIN), as_of=date(2020, 6, 6)).matched


def test_a_rule_applies_on_the_day_it_takes_effect():
    """INCLUSIVE AT THE START. The comparison is `<=`, and `<` would be
    wrong by exactly one day on every rule in the file -- a difference
    nothing else in this suite would notice."""
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, effective_date="2020-06-07"))
    ])
    assert engine.screen(_mol(SARIN), as_of=date(2020, 6, 7)).matched


def test_a_withheld_rule_produces_no_near_miss_either():
    """THE LEAK THIS IS REALLY ABOUT, and the reason the skip sits in the
    screening loop rather than inside `_apply`.

    A near miss names a rule and says which of its features you have. Report
    one for a rule that did not yet exist and the screen has disclosed
    future law while claiming to describe the past -- worse than a missing
    finding, because near misses are the part a legitimate user gets the
    most from.
    """
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, effective_date="2020-06-07"))
    ])
    report = engine.screen(_mol(DFP), as_of=date(2020, 6, 6))

    assert not report.matched
    assert report.near_misses == ()


def test_the_same_rule_produces_its_near_miss_once_it_applies():
    """THE CONTROL. Without it, an engine that had simply stopped reporting
    near misses altogether would satisfy the test above -- and this file
    already records how much is lost by weakening near-miss reporting to
    silence something."""
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, effective_date="2020-06-07"))
    ])
    report = engine.screen(_mol(DFP), as_of=date(2020, 6, 7))

    assert [o.label for o in report.near_misses[0].outcomes if not o.passed] == [
        "P-C bond"
    ]


def test_an_undated_rule_is_not_filtered_by_as_of():
    """The entry's own named decision, and the one that could have gone the
    other way. 47 of the 91 shipped rules are undated -- the whole DEA list
    -- so "no date means never applicable" would empty half the screen while
    looking exactly like a substance that is not listed.

    Note the claim: NOT date-filtered. That is narrower than "applicable at
    every date", which is a statement about history no undated ruleset can
    support, and the wording is load-bearing rather than fussy.
    """
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])
    for as_of in (date(1900, 1, 1), date(2020, 6, 7), date(2999, 1, 1)):
        assert engine.screen(_mol(SARIN), as_of=as_of).matched, as_of


def test_a_rule_takes_its_own_date_over_its_ruleset_s():
    """The CWC case exactly: a 1997 ruleset carrying 2020 rules. Falling back
    the other way would report the 2019 additions as having existed since the
    treaty entered force."""
    engine = RegulatoryEngine([
        _ruleset(
            _rule(SCHEDULE_1_A_1, effective_date="2020-06-07"),
            effective_date="1997-04-29",
        )
    ])
    assert not engine.screen(_mol(SARIN), as_of=date(1997, 4, 29)).matched
    assert engine.screen(_mol(SARIN), as_of=date(2020, 6, 7)).matched


def test_a_rule_with_no_date_takes_its_ruleset_s():
    """THE ONLY GUARD ON THE RUNTIME FALLBACK, and it cannot be written
    against shipped data.

    `build_regulatory_rulesets.py` already writes a ruleset's date onto every
    rule that does not declare one, so for a shipped ruleset the fallback and
    the baked-in value agree and deleting the fallback changes nothing
    measurable. `loader.py` does no such thing -- so a USER ruleset that
    dates itself and not its rules is the only place this branch is
    reachable, and a synthetic fixture is the only way to reach it.

    Measured: the mutation that deletes the fallback is caught here and
    nowhere else in the suite.
    """
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1), effective_date="2020-06-07")
    ])
    assert not engine.screen(_mol(SARIN), as_of=date(2020, 6, 6)).matched
    assert engine.screen(_mol(SARIN), as_of=date(2020, 6, 7)).matched


def test_a_rule_dated_in_the_future_still_matches_an_undated_screen():
    """THE ONLY THING THAT CATCHES `as_of` DEFAULTING TO TODAY.

    Every shipped rule is dated in the past, so `date.today()` as the default
    would give identical answers on all shipped data and on all four corpora.
    It diverges only here. `None` means no date filtering at all, which is
    what keeps an undated screen byte-identical to the behaviour that existed
    before this parameter did.
    """
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, effective_date="2999-01-01"))
    ])
    assert engine.screen(_mol(SARIN)).matched
    assert engine.screen(_mol(SARIN), as_of=None).matched


def test_a_malformed_stored_date_is_reported_not_silently_undated():
    """A broken date in somebody's own ruleset is tolerated AND recorded.

    Tolerated, because one bad entry must not cost them every other rule --
    the same policy as an unevaluable predicate. Recorded, because
    "this regulation records no dates" and "this file has a broken date" are
    different states, and folding the second into the first would let a
    malformed ruleset read as deliberately timeless.
    """
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, effective_date="7 June 2020"))
    ])
    report = engine.screen(_mol(SARIN), as_of=date(2019, 1, 1))

    assert report.matched, "tolerated: screened as undated"
    assert [(m.rule_id, m.value) for m in report.malformed_effective_dates] == [
        ("r1", "7 June 2020")
    ]

    note = report.coverage_notes()[0]
    assert "unreadable effective date" in note
    assert "no effective dates recorded" not in note, (
        "a broken date must not read as a ruleset that records none"
    )


def test_the_report_says_which_date_it_screened_as_of():
    """A dated answer that reads identically to an undated one is the same
    silence-read-as-reassurance this module is written against."""
    engine = RegulatoryEngine([_ruleset(_rule(SCHEDULE_1_A_1))])

    assert "as of" not in engine.screen(_mol("CCO")).summary()
    dated = engine.screen(_mol("CCO"), as_of=date(1990, 1, 1)).summary()
    assert "Screened as of 1990-01-01" in dated
    assert "consulted" in dated, "the verdict survives the qualifier"


def test_a_withheld_rule_is_named_rather_than_only_counted():
    """Rule ids, not a count. A count cannot be reconciled against anything,
    and the benchmark needs to know WHICH rules were not in the running so it
    does not score them as correct rejections."""
    engine = RegulatoryEngine([
        _ruleset(
            _rule(SCHEDULE_1_A_1, rule_id="new", effective_date="2020-06-07"),
            _rule("[Br]", rule_id="old", effective_date="1997-04-29"),
        )
    ])
    report = engine.screen(_mol(SARIN), as_of=date(2019, 1, 1))

    assert report.rules_withheld_by_date == (("rs", "new"),)
    assert report.withheld_in("rs") == ("new",)
    assert report.withheld_in("no such ruleset") == ()


def test_an_undated_screen_withholds_nothing_and_says_nothing_about_dates():
    """THE COMPATIBILITY INVARIANT, in the engine. Every one of these fields
    has to stay at its default, or an existing caller sees something new."""
    engine = RegulatoryEngine([
        _ruleset(_rule(SCHEDULE_1_A_1, effective_date="2999-01-01"))
    ])
    report = engine.screen(_mol(SARIN))

    assert report.as_of is None
    assert report.rules_withheld_by_date == ()
    assert report.malformed_effective_dates == ()
    assert "as of" not in " ".join(report.coverage_notes())


def test_the_applies_at_predicate_answers_for_a_rule_and_its_ruleset():
    """The predicate the benchmark and any future caller use, exercised
    directly rather than only through a screen -- it is the thing that
    encodes the policy, and a screen can hide a wrong answer behind a
    structure that would not have matched anyway."""
    ruleset = _ruleset(
        _rule(SCHEDULE_1_A_1, effective_date="2020-06-07"), effective_date="1997-04-29"
    )
    rule = ruleset.rules[0]

    assert resolve_effective_date(rule, ruleset) == date(2020, 6, 7)
    assert rule_applies_at(rule, ruleset, None)
    assert rule_applies_at(rule, ruleset, date(2020, 6, 7))
    assert not rule_applies_at(rule, ruleset, date(2020, 6, 6))


def test_the_predicate_treats_a_date_it_cannot_read_as_absent():
    """Matching what `screen()` does, so the two cannot disagree about a
    rule. The predicate has nowhere to REPORT it, which is exactly why
    `screen()` does the reporting rather than this."""
    ruleset = _ruleset(_rule(SCHEDULE_1_A_1, effective_date="7 June 2020"))
    assert rule_applies_at(ruleset.rules[0], ruleset, date(1900, 1, 1))
