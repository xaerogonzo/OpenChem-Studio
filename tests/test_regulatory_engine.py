"""Screening structures against rulesets.

The behaviours pinned here are mostly about what the engine REFUSES to
say: it never concludes, it reports which rulesets it consulted, it keeps
unchecked domains visible, and it will not claim a jurisdiction is silent
when no ruleset from that jurisdiction was loaded.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.regulatory.engine import RegulatoryEngine
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
          rule_id="r1") -> Rule:
    return Rule(
        rule_id=rule_id,
        display_name=f"rule {rule_id}",
        domain=domain,
        jurisdiction=jurisdiction,
        match_type=match_type,
        legal=LegalSource(authority="test", instrument="test", section="1"),
        interpretation=MachineInterpretation(
            expression=expression or "",
            inchikeys=tuple(inchikeys),
            confidence=RuleConfidence.EXACT,
        ),
    )


def _ruleset(*rules: Rule, ruleset_id="rs", jurisdiction=Jurisdiction.INTERNATIONAL,
             domain=Domain.CHEMICAL_WEAPONS, version="1", supersedes="") -> Ruleset:
    return Ruleset(
        ruleset_id=ruleset_id,
        display_name=f"ruleset {ruleset_id}",
        domain=domain,
        jurisdiction=jurisdiction,
        version=version,
        supersedes=supersedes,
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
