"""The regulatory gate on synthesis planning (`openchem.chem.synthesis_gate`, types in `openchem.domain.synthesis_gate`): what it refuses, that it fails closed, that a user's file cannot switch it off, and that route nodes are flagged rather than refused. Uses the SHIPPED rulesets, never the user's data directory."""

from __future__ import annotations

import json
from datetime import date

import pytest

from openchem.chem import synthesis_gate as gate
from openchem.chem.regulatory import loader
from openchem.chem.regulatory.engine import RegulatoryEngine
from openchem.chem.regulatory.types import ScreeningReport
from openchem.domain.synthesis_gate import (
    GATE_RULESET_ID,
    AlertFinding,
    GateDecision,
    GateMatch,
    GateOutcome,
    NodeScreening,
)

TODAY = date(2026, 10, 20)

ETHANOL = "CCO"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
SARIN = "CC(C)OP(C)(=O)F"
VX = "CCOP(C)(=O)SCCN(C(C)C)C(C)C"


@pytest.fixture(autouse=True)
def _fresh_engines():
    """No test leaves a cached gate or shared engine behind for the next one."""
    from openchem.chem.regulatory import calculator

    gate.reset_gate_engine()
    calculator.reset_engine()
    yield
    gate.reset_gate_engine()
    calculator.reset_engine()


@pytest.fixture(scope="module")
def shipped():
    rulesets, problems = loader.load_all(include_user=False)
    assert problems == []
    return rulesets


@pytest.fixture
def real_gate(shipped):
    return gate.gate_from_rulesets(shipped, [])


def _decision(smiles, real_gate):
    return gate.check_target(smiles, gate=real_gate, today=TODAY)


# --- the decision type ------------------------------------------------------------------------------------------------------


def _match(**kw):
    return GateMatch(**{"ruleset_id": GATE_RULESET_ID, "rule_id": "cwc-1-a-1", "display_name": "Alkylphosphonofluoridates (Schedule 1, A.1)", "section": "Schedule 1, A.1", "confidence": "exact", **kw})


def _allowed(**kw):
    return GateDecision(**{"outcome": GateOutcome.ALLOWED, "ruleset_version": "2", "ruleset_sha256": "abc", "screened_on": "2026-10-20", **kw})


def test_only_an_allowed_decision_permits_planning():
    assert _allowed().permits_planning
    assert not GateDecision(outcome=GateOutcome.REFUSED, matches=(_match(),), reason="matches").permits_planning
    assert not GateDecision(outcome=GateOutcome.UNSCREENED, reason="could not tell").permits_planning


def test_a_refusal_names_what_it_matched_and_says_why():
    with pytest.raises(ValueError, match="entry it matched"):
        GateDecision(outcome=GateOutcome.REFUSED, reason="matches")
    with pytest.raises(ValueError, match="reason"):
        GateDecision(outcome=GateOutcome.REFUSED, matches=(_match(),), reason="  ")


def test_an_unscreened_decision_says_why_and_never_carries_matches():
    with pytest.raises(ValueError, match="why"):
        GateDecision(outcome=GateOutcome.UNSCREENED)
    with pytest.raises(ValueError, match="no matches"):
        GateDecision(outcome=GateOutcome.UNSCREENED, reason="x", matches=(_match(),))


def test_an_allowed_decision_names_the_rules_it_consulted_and_has_no_reason_or_matches():
    for missing in ("ruleset_version", "ruleset_sha256", "screened_on"):
        with pytest.raises(ValueError, match="names the ruleset"):
            _allowed(**{missing: ""})
    with pytest.raises(ValueError, match="no reason"):
        _allowed(reason="fine")
    with pytest.raises(ValueError, match="no matches"):
        _allowed(matches=(_match(),))


def test_a_match_needs_names():
    for field in ("ruleset_id", "rule_id", "display_name"):
        with pytest.raises(ValueError):
            _match(**{field: " "})


def test_the_refusal_text_carries_the_reason_the_basis_the_approximation_note_and_the_lists_limits_and_is_empty_when_allowed():
    refused = GateDecision(outcome=GateOutcome.REFUSED, matches=(_match(confidence="approximate"),), reason="this structure matches CWC Schedule 1: X.", ruleset_version="2", ruleset_sha256="abc", screened_on="2026-10-20", limitations=("Ricin is not encoded.", "Size limits may over-report."))
    text = refused.refusal_text()
    assert "this structure matches CWC Schedule 1: X." in text and f"{GATE_RULESET_ID}, version 2, screened 2026-10-20" in text and "not a legal determination" in text
    assert "may be a false positive" in text and "Ricin is not encoded. Size limits may over-report." in text
    exact = GateDecision(outcome=GateOutcome.REFUSED, matches=(_match(confidence="exact"),), reason="r.", ruleset_version="2", ruleset_sha256="a", screened_on="2026-10-20")
    assert "false positive" not in exact.refusal_text()
    assert _allowed().refusal_text() == ""


def test_the_unscreened_text_has_no_basis_sentence_when_no_ruleset_was_ever_read():
    text = GateDecision(outcome=GateOutcome.UNSCREENED, reason="the target could not be screened: nothing loaded.", screened_on="2026-10-20").refusal_text()
    assert text == "the target could not be screened: nothing loaded."


def test_a_node_screening_is_either_screened_with_a_date_or_unscreened_with_a_reason():
    ok = NodeScreening(smiles="CCO", screened=True, screened_on="2026-10-20")
    assert not ok.has_alert
    with pytest.raises(ValueError, match="date"):
        NodeScreening(smiles="CCO", screened=True)
    with pytest.raises(ValueError, match="failure reason"):
        NodeScreening(smiles="CCO", screened=True, screened_on="d", reason="x")
    with pytest.raises(ValueError, match="says why"):
        NodeScreening(smiles="CCO", screened=False)
    with pytest.raises(ValueError, match="carries no findings"):
        NodeScreening(smiles="CCO", screened=False, reason="x", rulesets_consulted=("a",))
    with pytest.raises(ValueError):
        NodeScreening(smiles=" ", screened=False, reason="x")


# --- what the gate refuses and allows, on the shipped rulesets ----------------------------------------------------------------


@pytest.mark.parametrize(
    "smiles,rule",
    [
        (SARIN, "cwc-1-a-1"),
        ("C[P@](=O)(F)OC(C)C", "cwc-1-a-1"),  # one enantiomer
        ("[CH3:1][P:2](=[O:3])([F:4])[O:5]C(C)C", "cwc-1-a-1"),  # atom-mapped, as a planner may write it
        (VX, "cwc-1-a-3"),
        ("ClCCSCCCl", "cwc-1-a-4"),  # sulfur mustard
        ("ClC=C[As](Cl)Cl", "cwc-1-a-5"),  # lewisite
        ("ClCCN(CCCl)CCCl", "cwc-1-a-6"),  # nitrogen mustard HN3
        ("CC(C)OP(C)(=O)Cl", "cwc-1-b-11"),  # chlorosarin: a precursor listed by identity, not by family
        ("[CH3:1][P:2](=[O:3])(Cl)[O:5]C(C)C", "cwc-1-b-11"),  # ... atom-mapped
        ("CC(C)(C)C(C)OP(C)(=O)Cl", "cwc-1-b-12"),  # chlorosoman
        (VX + ".Cl", "cwc-1-a-3"),  # a hydrochloride
        ("CCO." + SARIN, "cwc-1-a-1"),  # beside a solvent
    ],
)
def test_a_schedule_1_target_is_refused_whatever_way_it_is_written(smiles, rule, real_gate):
    decision = _decision(smiles, real_gate)

    assert decision.outcome is GateOutcome.REFUSED and not decision.permits_planning
    assert rule in [m.rule_id for m in decision.matches] and all(m.ruleset_id == GATE_RULESET_ID for m in decision.matches)
    assert "does not plan syntheses" in decision.reason


@pytest.mark.parametrize("smiles", [ETHANOL, ASPIRIN, "OCCSCCO", "COP(C)(=O)OC", "CC(=O)Nc1ccc(O)cc1"])  # the third and fourth are in Schedule 2 / 3 territory, which does not refuse
def test_other_molecules_are_allowed_with_the_identity_of_what_decided_it(smiles, real_gate):
    decision = _decision(smiles, real_gate)

    assert decision.outcome is GateOutcome.ALLOWED and decision.permits_planning and decision.matches == ()
    assert decision.ruleset_version == "2" and len(decision.ruleset_sha256) > 10 and decision.screened_on == "2026-10-20"
    assert len(decision.limitations) == 5 and any("ricin" in s.lower() for s in decision.limitations)


def test_the_date_is_todays_unless_given():
    decision = gate.check_target(ETHANOL, gate=gate.gate_from_rulesets(loader.load_all(include_user=False)[0], []))
    assert decision.screened_on == date.today().isoformat()


def test_a_matched_target_carries_the_entry_the_confidence_and_the_lists_limits(real_gate):
    decision = _decision(SARIN, real_gate)
    match = decision.matches[0]
    assert match.display_name.startswith("Alkylphosphonofluoridates") and match.section == "Schedule 1, A.1" and match.confidence == "exact" and match.match_type == "structural_family"
    assert "Schedule 1, A.1" in decision.reason and decision.reason.count("A.1") == 1  # the section is not repeated when the name already holds it
    assert "Known limits of that list" in decision.refusal_text()


def test_a_rule_that_requires_review_also_says_it_may_be_a_false_positive():
    unsure = GateDecision(outcome=GateOutcome.REFUSED, matches=(_match(confidence="requires_review"),), reason="r.", ruleset_version="2", ruleset_sha256="a", screened_on="2026-10-20")
    assert "false positive" in unsure.refusal_text()


def test_an_approximate_rule_says_it_may_be_a_false_positive(real_gate):
    decision = _decision("ClCCSCCCl", real_gate)
    assert decision.matches[0].confidence == "approximate" and "false positive" in decision.refusal_text()


def test_every_part_of_a_mixture_is_screened_not_only_the_whole(shipped):
    """A family rule can fail on a mixture's total size, so a part must be tried on its own. The engine here is blind to anything bigger than eight heavy atoms."""
    real = RegulatoryEngine([r for r in shipped if r.ruleset_id == GATE_RULESET_ID])

    class SmallOnly:
        def screen(self, mol, **kw):
            return real.screen(mol, **kw) if mol.GetNumAtoms() <= 8 else ScreeningReport()

    blind = gate.GateEngine(engine=SmallOnly(), ruleset=real.rulesets[0])

    assert gate.check_target(SARIN, gate=blind, today=TODAY).outcome is GateOutcome.REFUSED
    assert gate.check_target("CCO." + SARIN, gate=blind, today=TODAY).outcome is GateOutcome.REFUSED  # eleven heavy atoms as a whole; the part is eight
    assert gate.check_target("CCO.CCCO", gate=blind, today=TODAY).outcome is GateOutcome.ALLOWED


def test_two_copies_of_one_substance_are_one_match(real_gate):
    decision = _decision(SARIN + "." + SARIN, real_gate)
    assert [m.rule_id for m in decision.matches] == ["cwc-1-a-1"]


def test_all_fourteen_schedule_1_rules_are_in_the_gate(real_gate):
    assert real_gate.ruleset.ruleset_id == GATE_RULESET_ID and len(real_gate.ruleset.rules) == 14
    assert [r.ruleset_id for r in real_gate.engine.rulesets] == [GATE_RULESET_ID]  # and nothing else


# --- it fails closed -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "this is not smiles", "C(C", None, 42])
def test_a_target_that_cannot_be_read_is_unscreened_never_allowed(bad, real_gate, capfd):
    decision = gate.check_target(bad, gate=real_gate, today=TODAY)

    assert decision.outcome is GateOutcome.UNSCREENED and not decision.permits_planning and "could not be screened" in decision.reason
    assert capfd.readouterr().err == ""  # RDKit's parse message is an answer here, not noise on stderr


def test_an_unreadable_target_still_names_the_ruleset_that_could_not_be_applied(real_gate):
    decision = _decision("not smiles", real_gate)
    assert decision.ruleset_version == "2" and decision.limitations


def _shipped_ruleset(shipped):
    return next(r for r in shipped if r.ruleset_id == GATE_RULESET_ID)


def test_each_way_the_ruleset_can_be_missing_or_wrong_leaves_the_gate_unavailable(shipped):
    import dataclasses

    base = _shipped_ruleset(shipped)
    others = [r for r in shipped if r.ruleset_id != GATE_RULESET_ID]
    cases = {
        "absent": (others, [], "not among the shipped"),
        "absent with problems": (others, ["something_else.json: ValueError: x"], "1 could not be read"),
        "named in the problems": (shipped, ["cwc_schedule_1.json: JSONDecodeError: bad"], "did not load"),
        "duplicated": ([*shipped, base], [], "2 rulesets claim"),
        "user supplied": ([*others, dataclasses.replace(base, user_supplied=True)], [], "user-supplied"),
        "claims to supersede": ([*others, dataclasses.replace(base, supersedes="cwc-schedule-2")], [], "supersede"),
        "no rules": ([*others, dataclasses.replace(base, rules=())], [], "no rules"),
    }
    for name, (rulesets, problems, expected) in cases.items():
        built = gate.gate_from_rulesets(list(rulesets), list(problems))
        assert built.engine is None and built.ruleset is None and expected in built.problem, name


@pytest.mark.parametrize("smiles", [ETHANOL, SARIN])
def test_a_gate_that_is_unavailable_stops_every_target_including_a_harmless_one(smiles, shipped):
    broken = gate.gate_from_rulesets([r for r in shipped if r.ruleset_id != GATE_RULESET_ID], [])

    decision = gate.check_target(smiles, gate=broken, today=TODAY)

    assert decision.outcome is GateOutcome.UNSCREENED and not decision.permits_planning
    assert "could not be screened against CWC Schedule 1" in decision.reason and "not among the shipped rulesets" in decision.reason


def test_a_screen_that_raises_is_unscreened(shipped):
    class Exploding:
        def screen(self, *a, **kw):
            raise RuntimeError("boom")

    built = gate.GateEngine(engine=Exploding(), ruleset=_shipped_ruleset(shipped))

    decision = gate.check_target(ETHANOL, gate=built, today=TODAY)

    assert decision.outcome is GateOutcome.UNSCREENED and "the screen failed (RuntimeError)" in decision.reason


def test_a_loader_that_raises_leaves_the_cached_gate_unavailable_until_it_is_reset(monkeypatch):
    calls = []

    def exploding(include_user=True):
        calls.append(include_user)
        raise OSError("disk gone")

    monkeypatch.setattr(gate, "load_all", exploding)
    first = gate.check_target(ETHANOL, today=TODAY)
    again = gate.check_target(SARIN, today=TODAY)

    assert first.outcome is GateOutcome.UNSCREENED and again.outcome is GateOutcome.UNSCREENED and "OSError" in first.reason
    assert calls == [False]  # read once, as a failure, and not again for every request
    monkeypatch.undo()
    gate.reset_gate_engine()
    assert gate.check_target(ETHANOL, today=TODAY).outcome is GateOutcome.ALLOWED


def test_the_real_gate_is_built_from_shipped_rulesets_only(monkeypatch):
    seen = []
    real = loader.load_all
    monkeypatch.setattr(gate, "load_all", lambda include_user=True: (seen.append(include_user), real(include_user=include_user))[1])

    assert gate.gate_engine().engine is not None
    assert seen == [False]


# --- a user's file cannot switch it off -------------------------------------------------------------------------------------------


def test_a_user_ruleset_with_the_same_id_sits_beside_the_shipped_one_in_the_shared_engine_and_is_not_in_the_gate(tmp_path, monkeypatch):
    from openchem.chem.regulatory import calculator

    shadow = {"ruleset_id": GATE_RULESET_ID, "display_name": "My lab policy", "domain": "chemical_weapons", "jurisdiction": "international", "version": "9", "effective_date": "2030-01-01", "rules": []}
    (tmp_path / "shadow.json").write_text(json.dumps(shadow), encoding="utf-8")
    monkeypatch.setattr(loader, "user_root", lambda: tmp_path)

    # Measured: the shared engine is built from a list, so the user's file does NOT replace the shipped ruleset, it joins it under the same id.
    calculator.reset_engine()
    shared, _ = calculator._shared_engine()
    schedule_1 = [r for r in shared.rulesets if r.ruleset_id == GATE_RULESET_ID]
    assert sorted(r.user_supplied for r in schedule_1) == [False, True]

    # The gate does not read the data directory at all: one ruleset, the shipped one.
    gate.reset_gate_engine()
    built = gate.gate_engine()
    assert [r.user_supplied for r in built.engine.rulesets] == [False]
    decision = gate.check_target(SARIN, today=TODAY)
    assert decision.outcome is GateOutcome.REFUSED and decision.ruleset_version == "2"


def test_the_path_that_would_retire_or_replace_a_ruleset_cannot_reach_the_gate(tmp_path, monkeypatch, shipped):
    """`add_ruleset` honours `supersedes` and a repeated id. The shared engine does not call it today; this is what would happen to a shared engine built that way, and the gate is immune to it."""
    retire = loader.ruleset_from_dict({"ruleset_id": "my-policy", "display_name": "x", "domain": "chemical_weapons", "jurisdiction": "international", "supersedes": GATE_RULESET_ID, "rules": []}, user_supplied=True)
    replace = loader.ruleset_from_dict({"ruleset_id": GATE_RULESET_ID, "display_name": "x", "domain": "chemical_weapons", "jurisdiction": "international", "rules": []}, user_supplied=True)
    for user in (retire, replace):
        engine = RegulatoryEngine()
        for ruleset in shipped:
            engine.add_ruleset(ruleset)
        engine.add_ruleset(user)
        assert not any(r.ruleset_id == GATE_RULESET_ID and not r.user_supplied for r in engine.rulesets)  # the shipped Schedule 1 is gone from an engine built this way

    (tmp_path / "retire.json").write_text(json.dumps({"ruleset_id": "my-policy", "display_name": "x", "domain": "chemical_weapons", "jurisdiction": "international", "supersedes": GATE_RULESET_ID, "rules": []}), encoding="utf-8")
    monkeypatch.setattr(loader, "user_root", lambda: tmp_path)
    gate.reset_gate_engine()
    assert gate.check_target(VX, today=TODAY).outcome is GateOutcome.REFUSED


# --- alerts on the molecules of a route ---------------------------------------------------------------------------------------------


@pytest.fixture
def shipped_engine(shipped):
    return RegulatoryEngine(shipped)


def test_a_schedule_1_molecule_in_a_route_is_an_alert_on_that_node_and_not_a_refusal(shipped_engine):
    screenings = gate.screen_nodes([ETHANOL, SARIN], engine=shipped_engine, today=TODAY)

    by = {s.smiles: s for s in screenings}
    assert by[SARIN].screened and by[SARIN].has_alert
    assert GATE_RULESET_ID in {f.ruleset_id for f in by[SARIN].findings}
    assert GATE_RULESET_ID in by[SARIN].rulesets_consulted and by[SARIN].screened_on == "2026-10-20"


def test_an_alert_names_its_ruleset_domain_jurisdiction_and_whether_the_user_supplied_it(shipped_engine):
    findings = next(s for s in gate.screen_nodes([SARIN], engine=shipped_engine, today=TODAY)).findings
    a1 = next(f for f in findings if f.rule_id == "cwc-1-a-1")
    assert (a1.ruleset_id, a1.domain, a1.jurisdiction, a1.section, a1.confidence, a1.user_supplied) == (GATE_RULESET_ID, "chemical_weapons", "international", "Schedule 1, A.1", "exact", False)


def test_a_user_ruleset_alert_is_marked_as_the_users(tmp_path, shipped):
    from openchem.chem.regulatory.types import MatchType  # noqa: F401

    mine = {
        "ruleset_id": "lab-policy", "display_name": "Lab policy", "domain": "chemical_weapons", "jurisdiction": "international", "version": "1",
        "rules": [{"rule_id": "lab-1", "display_name": "No ethanol", "domain": "chemical_weapons", "jurisdiction": "international", "match_type": "identity",
                   "interpretation": {"inchikeys": ["LFQSCWFLJHTTHZ-UHFFFAOYSA-N"], "confidence": "verified"}}],
    }
    ruleset = loader.ruleset_from_dict(mine, user_supplied=True)
    engine = RegulatoryEngine([*shipped, ruleset])

    ethanol = next(s for s in gate.screen_nodes([ETHANOL], engine=engine, today=TODAY))

    own = [f for f in ethanol.findings if f.rule_id == "lab-1"]
    assert len(own) == 1 and own[0].user_supplied and own[0].ruleset_id == "lab-policy"


def test_nodes_are_deduplicated_in_the_order_first_given(shipped_engine):
    result = gate.screen_nodes([ETHANOL, SARIN, ETHANOL, ASPIRIN, SARIN], engine=shipped_engine, today=TODAY)
    assert [s.smiles for s in result] == [ETHANOL, SARIN, ASPIRIN]


def test_a_node_that_cannot_be_read_is_not_screened_and_says_why_rather_than_showing_no_alert(shipped_engine, capfd):
    result = gate.screen_nodes(["junk", ETHANOL], engine=shipped_engine, today=TODAY)
    assert (result[0].screened, result[0].findings, result[0].reason) == (False, (), "the structure could not be read") and result[1].screened
    assert capfd.readouterr().err == ""


def test_a_screen_that_raises_marks_the_node_unscreened(shipped):
    class Exploding:
        def screen(self, *a, **kw):
            raise RuntimeError("boom")

    result = gate.screen_nodes([ETHANOL, SARIN], engine=Exploding(), today=TODAY)
    assert [s.screened for s in result] == [False, False] and "RuntimeError" in result[0].reason


def test_a_blank_node_is_a_callers_bug_and_raises(shipped_engine):
    for bad in ("", "  ", None):
        with pytest.raises(ValueError, match="cannot be blank"):
            gate.screen_nodes([ETHANOL, bad], engine=shipped_engine, today=TODAY)


def test_an_engine_that_cannot_be_obtained_leaves_every_node_unscreened(monkeypatch):
    from openchem.chem.regulatory import calculator

    monkeypatch.setattr(calculator, "_shared_engine", lambda: (_ for _ in ()).throw(OSError("no disk")))
    result = gate.screen_nodes([ETHANOL, ASPIRIN], today=TODAY)
    assert [s.screened for s in result] == [False, False] and "could not be loaded" in result[0].reason


def test_a_mixture_node_is_screened_by_its_parts(shipped):
    real = RegulatoryEngine(shipped)

    class SmallOnly:
        def screen(self, mol, **kw):
            return real.screen(mol, **kw) if mol.GetNumAtoms() <= 8 else ScreeningReport(rulesets_consulted=tuple(shipped))

    node = next(s for s in gate.screen_nodes(["CCO." + SARIN], engine=SmallOnly(), today=TODAY))
    assert node.has_alert


def test_the_alert_types_are_plain_data():
    a = AlertFinding(ruleset_id="r", rule_id="x", display_name="n", domain="d", jurisdiction="j")
    assert not a.user_supplied and a.section == ""
