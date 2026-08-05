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
    SMARTS expresses, which is why rules are a predicate language."""
    assert not engine.screen(_mol("CCCCCCCCCCCCOP(C)(=O)F")).matched


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
