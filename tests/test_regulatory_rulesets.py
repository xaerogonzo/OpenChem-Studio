"""The shipped rulesets, and the build that produces them.

These tests are about DATA INTEGRITY rather than logic: that every shipped
rule carries the text it claims to implement, that the build's quote gate
cannot be bypassed, and that the CWC rules actually discriminate the cases
the treaty distinguishes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem.regulatory.engine import RegulatoryEngine
from openchem.chem.regulatory.loader import SHIPPED_ROOT, load_all, load_ruleset
from openchem.chem.regulatory.predicates import SUPPORTED_OPS
from openchem.chem.regulatory.types import RuleConfidence

REPO = Path(__file__).resolve().parent.parent
SOURCES = REPO / "src" / "openchem" / "chem" / "data" / "regulatory" / "sources"

SARIN = "CC(C)OP(C)(=O)F"
SOMAN = "CC(C)(C)C(C)OP(C)(=O)F"
TABUN = "CCOP(=O)(C#N)N(C)C"
SULFUR_MUSTARD = "ClCCSCCCl"
#: Diisopropyl fluorophosphate: same phosphoryl, fluorine and alkoxy, no
#: P-C bond, NOT Schedule 1.
DFP = "CC(C)OP(=O)(F)OC(C)C"


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


@pytest.fixture(scope="module")
def engine() -> RegulatoryEngine:
    rulesets, problems = load_all(include_user=False)
    assert not problems, problems
    return RegulatoryEngine(rulesets)


# --- The shipped data is well-formed ------------------------------------


def test_every_shipped_ruleset_loads():
    rulesets, problems = load_all(include_user=False)
    assert not problems
    assert rulesets


def test_every_shipped_rule_carries_the_text_it_implements():
    """THE GATE, checked on the shipped artefact rather than only in the
    build. A rule without the regulation's own words has not been verified
    against anything, and could not be audited by someone else later."""
    rulesets, _ = load_all(include_user=False)
    for ruleset in rulesets:
        for rule in ruleset.rules:
            if rule.interpretation.confidence is RuleConfidence.REQUIRES_REVIEW:
                continue
            assert rule.legal.quote, f"{rule.rule_id} claims verified status with no quote"
            assert rule.legal.citation_url, f"{rule.rule_id} has no citation URL"


def test_every_shipped_rule_uses_supported_predicates():
    """An unknown op at screening time means a regulation that silently
    matches nothing, which looks exactly like a structure being
    unregulated."""

    def walk(expression):
        if isinstance(expression, str) or not expression:
            return
        assert expression["op"] in SUPPORTED_OPS, expression["op"]
        for child in expression.get("of", []) or []:
            walk(child)

    rulesets, _ = load_all(include_user=False)
    for ruleset in rulesets:
        for rule in ruleset.rules:
            walk(rule.interpretation.expression)


def test_generated_files_are_marked_do_not_edit():
    for path in SHIPPED_ROOT.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "DO NOT EDIT" in data.get("_comment", "")


def test_every_ruleset_records_how_to_regenerate_it():
    """RDKit's version is in there for a concrete reason: aromaticity
    perception and SMARTS semantics change between releases, so the same
    rule against the same structure can change answer. Without it a
    ruleset can be re-run but not reproduced."""
    rulesets, _ = load_all(include_user=False)
    for ruleset in rulesets:
        provenance = ruleset.provenance
        assert provenance.generator
        assert provenance.source_document_sha256
        assert provenance.ruleset_sha256
        assert provenance.rdkit_version


def test_approximate_rules_say_why_they_are_approximate():
    rulesets, _ = load_all(include_user=False)
    for ruleset in rulesets:
        for rule in ruleset.rules:
            if rule.interpretation.confidence is RuleConfidence.APPROXIMATE:
                assert rule.interpretation.limitations, rule.rule_id


# --- The CWC rules discriminate what the treaty discriminates -----------


def test_scheduled_agents_match(engine):
    for smiles in (SARIN, SOMAN, TABUN, SULFUR_MUSTARD):
        assert engine.screen(_mol(smiles)).matched, smiles


def test_the_p_c_bond_distinction_is_honoured(engine):
    """DFP is a phosphoFLUORIDATE, not a phosphoNOfluoridate. Same
    phosphoryl, same fluorine, same alkoxy -- and not Schedule 1. A rule
    that flagged every organophosphate would pass a positives-only suite
    and be useless in a screen."""
    report = engine.screen(_mol(DFP))
    assert not report.matched
    assert report.near_misses
    failed = [o.label for o in report.near_misses[0].outcomes if not o.passed]
    assert any("P-alkyl" in label for label in failed)


def test_the_treaty_s_alkyl_restriction_is_honoured(engine):
    """Entries 1 and 3 restrict the P-alkyl group to methyl, ethyl,
    n-propyl or isopropyl. A P-butyl homologue has the scheduled
    connectivity and is outside the entry."""
    assert not engine.screen(_mol("CCCCP(=O)(F)OC(C)C")).matched


def test_the_carbon_limit_is_honoured(engine):
    """"equal to or less than C10, including cycloalkyl" -- a clause no
    SMARTS expresses, which is why rules are a predicate language.

    The assertion is scoped to SCHEDULE 1, which is what the clause belongs
    to. It read "matches nothing at all" while Schedule 1 was the only
    ruleset, and that stopped being the same statement the moment Schedule
    2 shipped: the C12 chain hangs off the oxygen, so the phosphorus still
    carries one methyl and no other carbon, and entry B.4 catches it.
    Outside Schedule 1 and inside Schedule 2 is the right answer.
    """
    findings = engine.screen(_mol("CCCCCCCCCCCCOP(C)(=O)F")).findings
    assert not [f for f in findings if f.rule.rule_id.startswith("cwc-1-")]
    assert [f.rule.rule_id for f in findings] == ["cwc-2-b-4"]


@pytest.mark.parametrize(
    "smiles",
    [
        "CC(=O)Oc1ccccc1C(=O)O",   # aspirin
        "CCO",                      # ethanol
        "COP(=O)(OC)OC",            # trimethyl phosphate
        "CC(C)OP(=O)(OC(C)C)OC(C)C",  # triisopropyl phosphate
        "c1ccccc1",                 # benzene
    ],
)
def test_ordinary_chemicals_do_not_match(smiles, engine):
    """The negative controls. Without these a rule matching every
    phosphorus compound would look perfect."""
    assert not engine.screen(_mol(smiles)).matched


def test_an_over_broad_rule_says_so_on_the_finding(engine):
    """Chlorambucil is a licensed cytotoxic MEDICINE that shares the
    nitrogen mustard motif. It matches, and it must arrive carrying the
    limitation that says the rule is broader than the treaty's
    enumeration -- a bare match here would read as an accusation."""
    report = engine.screen(_mol("OC(=O)CCCc1ccc(cc1)N(CCCl)CCCl"))
    assert report.matched

    finding = report.findings[0]
    assert finding.rule.interpretation.confidence is RuleConfidence.APPROXIMATE
    assert finding.rule.interpretation.limitations


# --- The build ----------------------------------------------------------


def test_the_build_check_passes_on_the_shipped_sources():
    """`--check` validates without writing, so this cannot mutate the
    working tree."""
    result = subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_regulatory_rulesets.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_quote_gate_cannot_be_bypassed(tmp_path):
    """A source claiming 'exact' with no quote must be forced down to
    requires_review. "I am confident about the chemistry" and "I have read
    the statute" are different claims."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import build_one

    source = {
        "ruleset_id": "test", "display_name": "test",
        "domain": "chemical_weapons", "jurisdiction": "international",
        "version": "1",
        "rules": [{
            "rule_id": "no-quote", "display_name": "no quote",
            "confidence": "exact",
            "legal": {"authority": "x", "instrument": "y", "section": "z", "quote": ""},
            "expression": {"op": "contains", "smarts": "[Br]"},
        }],
    }
    path = tmp_path / "test.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    ruleset, notes = build_one(path)
    assert ruleset["rules"][0]["interpretation"]["confidence"] == "requires_review"
    assert ruleset["coverage"]["requires_review"] == ["no-quote"]
    assert any("forced to" in note for note in notes)


def test_a_quoted_rule_keeps_its_claimed_confidence(tmp_path):
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import build_one

    source = {
        "ruleset_id": "test", "display_name": "test",
        "domain": "chemical_weapons", "jurisdiction": "international",
        "version": "1",
        "rules": [{
            "rule_id": "quoted", "display_name": "quoted",
            "confidence": "exact",
            "legal": {"authority": "x", "instrument": "y", "section": "z",
                      "quote": "the actual words of the regulation"},
            "expression": {"op": "contains", "smarts": "[Br]"},
        }],
    }
    path = tmp_path / "test.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    ruleset, _ = build_one(path)
    assert ruleset["rules"][0]["interpretation"]["confidence"] == "exact"


def test_an_unknown_op_fails_the_build(tmp_path):
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import BuildError, build_one

    source = {
        "ruleset_id": "test", "display_name": "test",
        "domain": "chemical_weapons", "jurisdiction": "international",
        "version": "1",
        "rules": [{
            "rule_id": "bad", "display_name": "bad",
            "legal": {"quote": "words"},
            "expression": {"op": "not_a_real_op"},
        }],
    }
    path = tmp_path / "test.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(BuildError, match="unknown predicate op"):
        build_one(path)


# --- Schedule 3: the first shipped ruleset matched by identity ----------


def test_a_schedule_3_precursor_reports_as_a_precursor(engine):
    """The first shipped rules to exercise `_apply_identity` at all. Every
    Schedule 3 Part B entry is a listed PRECURSOR matched by InChIKey, which
    is exactly the combination that used to report as an identity match."""
    findings = engine.screen(_mol("O=S(Cl)Cl")).findings  # thionyl chloride
    assert [f.rule.rule_id for f in findings] == ["cwc-3-b-14"]
    assert findings[0].match_type.value == "precursor"
    assert findings[0].rule.legitimate_uses, "a precursor without its uses reads as an accusation"


def test_a_schedule_3_toxic_chemical_reports_as_an_identity(engine):
    """Part A is not a precursor list, and the two parts must not blur."""
    findings = engine.screen(_mol("C(=O)(Cl)Cl")).findings  # phosgene
    assert [f.rule.rule_id for f in findings] == ["cwc-3-a-1"]
    assert findings[0].match_type.value == "identity"


def test_the_listed_sulfur_monochloride_is_Cl2S2_not_ClS(engine):
    """THE ENTRY A NAME LOOKUP GETS WRONG. OPSIN returns ClS for
    'Sulphur monochloride' and PubChem returns HClS; the entry lists Cl2S2.
    Both halves are asserted, because the shipped key being right is only
    meaningful if the wrong structure also fails to match."""
    assert [f.rule.rule_id for f in engine.screen(_mol("ClSSCl")).findings] == ["cwc-3-b-12"]
    assert not engine.screen(_mol("[S]Cl")).matched


def test_a_salt_of_a_schedule_3_chemical_matches_and_that_is_declared(engine):
    """A DELIBERATE OVER-REACH, asserted so it stays deliberate. Schedule 3
    entries carry no 'and corresponding salts' wording -- unlike several
    Schedule 1 and 2 entries -- but the engine strips counter-ions before
    comparing, so a salt matches. Broader than the statute, and the ruleset
    says so in as many words rather than applying it silently."""
    assert engine.screen(_mol("OCCN(CCO)CCO.Cl")).matched

    ruleset = next(r for r in load_all(include_user=False)[0]
                   if r.ruleset_id == "cwc-schedule-3")
    assert any("salts" in note for note in ruleset.known_limitations)


def test_the_entry_no_resolver_could_reach_is_visible_not_missing():
    """Schedule 3 entry B.11 is not encoded, because PubChem's record for
    its CAS is a cation and OPSIN returns an anion where the entry lists a
    neutral substance. The failure mode to avoid is it quietly vanishing:
    coverage must still count 17 entries and name the one not resolved."""
    ruleset = next(r for r in load_all(include_user=False)[0]
                   if r.ruleset_id == "cwc-schedule-3")

    assert ruleset.coverage.total_entries == 17
    assert ruleset.coverage.resolved == 16
    assert any("cwc-3-b-11" in item for item in ruleset.coverage.unresolved)
    assert any("diethyl phosphite" in note.lower() for note in ruleset.known_limitations)


# --- Schedule 2: generic families, and the exemptions inside them -------


def test_a_schedule_2_family_honours_its_alkyl_restriction(engine):
    """Five entries say "(Me, Et, n-Pr or i-Pr)" and mean it. A pattern that
    accepted any alkyl would match a great deal of ordinary chemistry."""
    assert [f.rule.rule_id for f in
            engine.screen(_mol("CC(C)N(C(C)C)CCO")).findings] == ["cwc-2-b-11"]
    assert not engine.screen(_mol("CCCCN(CCCC)CCO")).matched, "N,N-dibutyl is outside"


@pytest.mark.parametrize(
    "name,smiles",
    [("fonofos, exempted from B.4", "CCOP(=S)(CC)Sc1ccccc1"),
     ("N,N-dimethylaminoethanol, exempted from B.11", "CN(C)CCO"),
     ("N,N-diethylaminoethanol, exempted from B.11", "CCN(CC)CCO"),
     ("a protonated salt of an exempt chemical", "CN(C)CCO.Cl")],
)
def test_an_exempted_chemical_does_not_match(engine, name, smiles):
    """The treaty exempts these BY NAME, and each one's family pattern hits
    it -- so without the exemption every one is a false positive on a
    chemical in ordinary commerce."""
    assert not engine.screen(_mol(smiles)).matched, name


def test_the_exemption_does_not_excuse_a_larger_molecule_that_contains_it(engine):
    """An exemption names a CHEMICAL. A bare substructure exemption would
    also excuse anything containing it, which is why each is a skeleton
    plus an exact carbon count."""
    findings = engine.screen(_mol("CCOP(=S)(CC)Sc1ccc(CCCC)cc1")).findings
    assert [f.rule.rule_id for f in findings] == ["cwc-2-b-4"]


def test_entry_B4_requires_ONE_alkyl_and_no_further_carbon(engine):
    """"...to which is bonded one methyl, ethyl or propyl group BUT NOT
    FURTHER CARBON ATOMS". Without that clause the entry would reach a
    large part of organophosphorus chemistry.

    Added after a mutation deleting the clause survived the whole file: the
    case was in the pattern's prototype and never carried into a shipped
    guard, which is how a clause ends up load-bearing and untested.
    """
    assert engine.screen(_mol("CP(=O)(Cl)Cl")).matched, "one methyl, nothing else"
    assert not engine.screen(_mol("CP(=O)(C)OC")).matched, "two methyls on the phosphorus"
    assert not engine.screen(_mol("c1ccccc1P(c1ccccc1)c1ccccc1")).matched


def test_entry_B4_constrains_ONE_phosphorus_not_the_molecule(engine):
    """WHY B.4 IS A SINGLE RECURSIVE SMARTS rather than the feature
    checklist this project prefers elsewhere.

    Every clause constrains the same phosphorus. Written as a checklist --
    "contains a P-alkyl" AND "no phosphorus carries two carbons" -- this
    molecule would be REJECTED, because its second phosphorus carries two
    methyls, even though its first satisfies the entry exactly.
    """
    assert engine.screen(_mol("CP(=O)(Cl)OP(=O)(C)C")).matched


def test_a_schedule_1_agent_also_matches_B4_and_the_rule_says_why(engine):
    """B.4 opens "except for those listed in Schedule 1" and nothing here
    can exclude another ruleset's members. Pinned so the overlap stays a
    recorded decision: it over-reports and never under-reports, and the
    limitation travels with the finding rather than living only in a doc."""
    findings = engine.screen(_mol(SARIN)).findings
    assert [f.rule.rule_id for f in findings] == ["cwc-1-a-1", "cwc-2-b-4"]

    b4 = next(f.rule for f in findings if f.rule.rule_id == "cwc-2-b-4")
    assert any("Schedule 1" in text for text in b4.interpretation.limitations)


def test_an_identity_rule_is_confidence_verified_not_exact():
    """The vocabulary distinguishes them and flattening it loses the one
    thing an auditor most needs. `exact` means the regulation gave a
    structural specification and the pattern transcribes it; `verified`
    means a named substance whose identity was checked against the primary
    text. Every keyed rule here is the second."""
    for ruleset in load_all(include_user=False)[0]:
        for rule in ruleset.rules:
            if rule.interpretation.inchikeys:
                assert rule.interpretation.confidence is RuleConfidence.VERIFIED, rule.rule_id


def test_every_shipped_rule_is_exercised_by_the_benchmark_corpus():
    """A rule with no positive case scores precision 1.00 in the benchmark
    while testing nothing -- the same vacuous pass its own README warns
    about for a rule that matches every organophosphate. Sixteen of the
    twenty-two shipped rules were in that state when Schedule 3 landed."""
    corpus = json.loads(
        (REPO / "benchmarks" / "regulatory" / "corpus.json").read_text(encoding="utf-8")
    )
    exercised = {
        rule_id
        for case in corpus["positives"]
        for rule_id in case.get("expect", [])
    }
    shipped = {
        rule.rule_id for ruleset in load_all(include_user=False)[0] for rule in ruleset.rules
    }
    assert not (shipped - exercised), "shipped rules with no positive case"


def test_an_identity_rule_must_declare_what_it_claims(tmp_path):
    """`loader` defaults an undeclared `match_type` to `structural_family`,
    and the engine now reports whatever the rule declared. So a rule matched
    by InChYKey that forgot to declare itself would report every hit as a
    structural family -- a plausible answer about a family the regulation
    never defined. Caught at build time, where it is one message."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import BuildError, build_one

    source = {
        "ruleset_id": "test", "display_name": "test",
        "domain": "chemical_weapons", "jurisdiction": "international",
        "version": "1",
        "rules": [{
            "rule_id": "listed", "display_name": "a listed substance",
            "match_type": "structural_family",
            "legal": {"quote": "words"},
            "inchikeys": ["WQZGKKKJIJFFOK-GASJEMHNSA-N"],
        }],
    }
    path = tmp_path / "test.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(BuildError, match="cannot be expressed as a list of keys"):
        build_one(path)


@pytest.mark.parametrize("match_type", ["identity", "precursor", "metabolite"])
def test_a_substance_naming_match_type_is_accepted(tmp_path, match_type):
    """The CONTROL for the guard above: it must ACCEPT the types that name a
    substance, or the cheapest way to satisfy it is to reject every identity
    rule."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import build_one

    source = {
        "ruleset_id": "test", "display_name": "test",
        "domain": "drug_precursors", "jurisdiction": "international",
        "version": "1",
        "rules": [{
            "rule_id": "listed", "display_name": "a listed substance",
            "match_type": match_type,
            "legal": {"quote": "words"},
            "inchikeys": ["WQZGKKKJIJFFOK-GASJEMHNSA-N"],
        }],
    }
    path = tmp_path / "test.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    ruleset, _ = build_one(path)
    assert ruleset["rules"][0]["match_type"] == match_type


# --- The shipped artefact is what the source builds ---------------------
#
# `--check` used to validate the SOURCE and never look at what ships, so a
# generated file that had been hand-edited, or left behind by a source that
# moved on, passed CI untouched. The DO-NOT-EDIT header and the recorded
# `ruleset_sha256` were both promises with nothing enforcing either.
#
# Two failures, deliberately checked separately: a hand edit leaves a file
# that is perfectly self-consistent with its own source-document hash, and
# a stale artefact hashes correctly to its own (old) content. Neither check
# sees the other's case.


def _built(tmp_path, rule_overrides: dict | None = None):
    """One built ruleset from a minimal, valid source."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import build_one

    rule = {
        "rule_id": "a-rule", "display_name": "a rule",
        "confidence": "exact",
        "legal": {"authority": "x", "instrument": "y", "section": "z",
                  "quote": "the actual words of the regulation"},
        "expression": {"op": "contains", "smarts": "[Br]"},
    }
    rule.update(rule_overrides or {})
    source = {
        "ruleset_id": "test", "display_name": "test",
        "domain": "chemical_weapons", "jurisdiction": "international",
        "version": "1", "rules": [rule],
    }
    path = tmp_path / "test.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    ruleset, _ = build_one(path)
    return ruleset


def test_an_intact_shipped_artefact_verifies():
    """THE CONTROL, and it runs against the real shipped file rather than a
    fixture. Without it a `verify_stored_hash` that always reported a
    problem would satisfy every test below it."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import verify_stored_hash

    for path in sorted(SHIPPED_ROOT.glob("*.json")):
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert verify_stored_hash(committed) == "", path.name


def test_a_hand_edited_artefact_no_longer_matches_its_own_hash(tmp_path):
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import verify_stored_hash

    ruleset = _built(tmp_path)
    assert verify_stored_hash(ruleset) == ""

    # The edit somebody would actually make: widen a pattern in place.
    ruleset["rules"][0]["interpretation"]["expression"]["smarts"] = "[Cl]"
    problem = verify_stored_hash(ruleset)
    assert "edited by hand" in problem


def test_an_artefact_whose_hash_is_missing_is_refused_not_passed(tmp_path):
    """Absence must not read as intactness -- deleting the hash is the
    cheapest way to defeat the check, so it is the one that must fail."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import verify_stored_hash

    ruleset = _built(tmp_path)
    del ruleset["provenance"]["ruleset_sha256"]
    assert "cannot be verified" in verify_stored_hash(ruleset)


def test_a_stale_artefact_is_caught_though_it_hashes_correctly(tmp_path):
    """The case the hash check CANNOT see: the committed file is internally
    consistent, and simply older than its source."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import verify_matches_source, verify_stored_hash

    committed = _built(tmp_path)
    rebuilt = _built(tmp_path, {"display_name": "a rule, reworded"})

    assert verify_stored_hash(committed) == "", "the stale file is self-consistent"
    assert verify_matches_source(rebuilt, committed)


def test_the_reported_difference_names_the_RULE_not_the_source_hash(tmp_path):
    """Editing a source always moves `source_document_sha256`, so a plain
    sorted walk reports that every time and never the rule that changed --
    a true first difference, and the least useful one available."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import verify_matches_source

    committed = _built(tmp_path)
    rebuilt = _built(tmp_path, {"display_name": "a rule, reworded"})

    difference = verify_matches_source(rebuilt, committed)
    assert "rules[a-rule].display_name" in difference
    assert "source_document_sha256" not in difference


def test_a_rebuild_of_one_source_matches_despite_its_timestamp(tmp_path):
    """`generated_at` and the hash over it differ between two builds of the
    same source. Without excluding them the check would fail on every
    correct tree, which is the shape of a control nobody keeps."""
    sys.path.insert(0, str(REPO / "tools"))
    from build_regulatory_rulesets import verify_matches_source

    committed = _built(tmp_path)
    rebuilt = json.loads(json.dumps(committed))
    rebuilt["provenance"]["generated_at"] = "1999-12-31T23:59:59+00:00"
    rebuilt["provenance"]["ruleset_sha256"] = "0" * 64

    assert verify_matches_source(rebuilt, committed) == ""
