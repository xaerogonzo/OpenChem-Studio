"""The regulatory gate on synthesis planning (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 2): one decision about the target before any process starts, and alerts on the molecules of a route that was planned. The decision types are `domain/synthesis_gate.py`.

THE GATE HAS ITS OWN ENGINE, BUILT FROM THE SHIPPED RULESETS ONLY. The shared engine of `regulatory/calculator.py` loads the user's rulesets too (`load_all()` defaults to `include_user=True`). MEASURED, as it is built today it builds `RegulatoryEngine(rulesets)` from a list, so a user file with the id `cwc-schedule-1` sits beside the shipped ruleset (both screen) and `supersedes` is not applied; `RegulatoryEngine.add_ruleset`, which that path does not call, WOULD retire a ruleset on `supersedes` or replace one on a repeated id. A refusal that a user can switch off by dropping in a file is not a gate, and nothing guarantees the shared engine keeps being built the way it is, so the gate does not depend on it. The gate engine is `load_all(include_user=False)`, holds ONLY `cwc-schedule-1`, and is never the shared one. The shared engine is used for alerts, where a user's own rulesets are welcome.

IT FAILS CLOSED. Anything that stops the gate from being able to tell is `UNSCREENED` and nothing starts: the ruleset missing, named in the loader's problems, shadowed by something else or empty; a structure that cannot be read; a screen that raises. There is no path from an exception to `ALLOWED`.

ONLY A MATCH ON THE TARGET REFUSES. A match on an intermediate or a starting material of a planned route is an alert on that node (`screen_nodes`), including a match against Schedule 1 itself: the route is shown, the node is flagged.

A MIXTURE IS SCREENED AS ITS PARTS AS WELL AS AS A WHOLE (a structure written as `A.B`): the engine strips counter-ions, and a family rule can fail on a mixture's total size, so a Schedule 1 substance written beside a solvent would otherwise be missed. A match on any part refuses.

A FINDING DOES NOT CARRY ITS RULESET'S ID (`regulatory.types.Finding` holds the rule only), so the ruleset of a finding is read from the consulted rulesets by rule id. In the gate engine there is one ruleset, so it is unambiguous.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from rdkit import Chem, rdBase

from openchem.chem.regulatory.engine import RegulatoryEngine
from openchem.chem.regulatory.loader import load_all
from openchem.chem.regulatory.types import Finding, Ruleset
from openchem.domain.synthesis_gate import (
    GATE_RULESET_ID,
    AlertFinding,
    GateDecision,
    GateMatch,
    GateOutcome,
    NodeScreening,
)

logger = logging.getLogger("openchem.chemistry")

#: What the reachability guard accepts for a module nothing in the application imports YET. The gate is built first and on its own (Stage 1 slice 2); the synthesis planning service (slice 4) is its first importer, and the guard then fails this declaration, which is the reminder to delete it.
REACHED_BY = (
    "tooling: imported only by tests/test_synthesis_gate.py until the synthesis planning service (Stage 1 slice 4 of docs/SYNTHESIS_HELPER_DESIGN.md) imports it; the feature is not yet reachable from the window"
)

#: The file the gate's ruleset is read from; a loader problem naming it means the ruleset did not load.
GATE_RULESET_FILE = "cwc_schedule_1.json"


@dataclass(frozen=True)
class GateEngine:
    """The gate's engine and ruleset, or why there is none. Exactly one of (`engine` and `ruleset`) and `problem` is set."""

    engine: RegulatoryEngine | None = None
    ruleset: Ruleset | None = None
    problem: str = ""


def gate_from_rulesets(rulesets: list[Ruleset], problems: list[str]) -> GateEngine:
    """Build the gate from what `load_all(include_user=False)` returned. Pure, so each way it can fail closed is testable."""
    named = [p for p in problems if GATE_RULESET_FILE in p]
    if named:
        return GateEngine(problem=f"the Schedule 1 ruleset did not load: {'; '.join(named)}")
    found = [r for r in rulesets if r.ruleset_id == GATE_RULESET_ID]
    if not found:
        return GateEngine(problem=f"the Schedule 1 ruleset ({GATE_RULESET_ID}) is not among the shipped rulesets" + (f" ({len(problems)} could not be read)" if problems else ""))
    if len(found) > 1:
        return GateEngine(problem=f"{len(found)} rulesets claim the id {GATE_RULESET_ID}")
    ruleset = found[0]
    if ruleset.user_supplied:
        return GateEngine(problem="the Schedule 1 ruleset is a user-supplied file, not the shipped one")
    if ruleset.supersedes:
        return GateEngine(problem=f"the Schedule 1 ruleset claims to supersede {ruleset.supersedes!r}")
    if not ruleset.rules:
        return GateEngine(problem="the Schedule 1 ruleset has no rules")
    return GateEngine(engine=RegulatoryEngine([ruleset]), ruleset=ruleset)


#: The cached gate (or the cached reason there is none); `reset_gate_engine` clears it.
_GATE: GateEngine | None = None


def gate_engine() -> GateEngine:
    """The cached gate. A load that fails is cached as a failure and is retried only after `reset_gate_engine`, so a missing file is not re-read on every request but is not remembered past a deliberate reset either."""
    global _GATE
    if _GATE is None:
        try:
            rulesets, problems = load_all(include_user=False)
            _GATE = gate_from_rulesets(rulesets, problems)
        except Exception as exc:  # noqa: BLE001 - fail closed: whatever went wrong, the gate cannot tell
            logger.warning("Could not build the synthesis gate: %s", exc)
            _GATE = GateEngine(problem=f"the shipped rulesets could not be read ({type(exc).__name__}: {exc})")
    return _GATE


def reset_gate_engine() -> None:
    global _GATE
    _GATE = None


# --- reading a structure -------------------------------------------------------------------------------------------------------


def _parse(smiles: str) -> tuple[Chem.Mol | None, str]:
    """The molecule, with atom maps cleared, or why there is none."""
    if not isinstance(smiles, str) or not smiles.strip():
        return None, "there is no structure to read"
    with rdBase.BlockLogs():  # an unreadable target is an answer here, not a message on stderr
        mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        return None, "the structure could not be read"
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)  # defensive: today's engine ignores maps (a mutation check found no test can tell), but a planner writes mapped SMILES and nothing should depend on that
    return mol, ""


def _parts(mol: Chem.Mol) -> list[Chem.Mol]:
    """The molecule and, if it is a mixture, each of its components."""
    parts = [mol]
    fragments = Chem.GetMolFrags(mol, asMols=True)
    if len(fragments) > 1:
        parts.extend(fragments)
    return parts


# --- the gate ----------------------------------------------------------------------------------------------------------------------


def check_target(smiles: str, *, gate: GateEngine | None = None, today: date | None = None) -> GateDecision:
    """Whether planning may start for this target. The one call every surface goes through; `permits_planning` is true only for `ALLOWED`."""
    stamp = (today or date.today()).isoformat()
    gate = gate if gate is not None else gate_engine()
    if gate.engine is None or gate.ruleset is None:
        return GateDecision(outcome=GateOutcome.UNSCREENED, reason=f"the target could not be screened against CWC Schedule 1: {gate.problem or 'the gate is not available'}.", screened_on=stamp)
    ruleset = gate.ruleset
    identity = {"ruleset_version": ruleset.version, "ruleset_sha256": ruleset.provenance.ruleset_sha256 or "not recorded", "screened_on": stamp, "limitations": tuple(ruleset.known_limitations)}
    mol, problem = _parse(smiles)
    if mol is None:
        return GateDecision(outcome=GateOutcome.UNSCREENED, reason=f"the target could not be screened against CWC Schedule 1: {problem}.", **identity)
    try:
        findings: dict[str, Finding] = {}
        for part in _parts(mol):
            for finding in gate.engine.screen(part, include_near_misses=False).findings:
                findings.setdefault(finding.rule.rule_id, finding)
    except Exception as exc:  # noqa: BLE001 - fail closed: a screen that raised is a screen that did not tell
        logger.warning("The synthesis gate's screen raised: %s", exc)
        return GateDecision(outcome=GateOutcome.UNSCREENED, reason=f"the target could not be screened against CWC Schedule 1: the screen failed ({type(exc).__name__}).", **identity)
    if not findings:
        return GateDecision(outcome=GateOutcome.ALLOWED, **identity)
    matches = tuple(
        GateMatch(
            ruleset_id=ruleset.ruleset_id,
            rule_id=f.rule.rule_id,
            display_name=f.rule.display_name,
            section=f.rule.legal.section,
            confidence=f.rule.interpretation.confidence.value,
            match_type=f.match_type.value,
        )
        for f in findings.values()
    )
    names = "; ".join(m.display_name + (f" ({m.section})" if m.section and m.section not in m.display_name else "") for m in matches)
    return GateDecision(outcome=GateOutcome.REFUSED, matches=matches, reason=f"this structure matches CWC Schedule 1: {names}. OpenChem does not plan syntheses for substances on that list.", **identity)


# --- alerts on the molecules of a route -------------------------------------------------------------------------------------------


def screen_nodes(smiles: list[str] | tuple[str, ...], *, engine: RegulatoryEngine | None = None, today: date | None = None) -> tuple[NodeScreening, ...]:
    """What the wider rulesets (the shared engine: shipped plus the user's own) say about each distinct molecule, in the order first given.

    A match is an alert on the node and never a refusal. A molecule that could not be read, or whose screen raised, is `screened` False with the reason, never an empty list of findings. A blank molecule raises `ValueError`.
    """
    stamp = (today or date.today()).isoformat()
    if any(not isinstance(s, str) or not s.strip() for s in smiles):
        # A route node always has a structure; a blank one is a caller's bug, and skipping it would read as 'screened, nothing found'.
        raise ValueError("a molecule to screen cannot be blank")
    unique = list(dict.fromkeys(smiles))
    try:
        if engine is None:
            from openchem.chem.regulatory.calculator import _shared_engine

            engine, _ = _shared_engine()
    except Exception as exc:  # noqa: BLE001
        return tuple(NodeScreening(smiles=s, screened=False, reason=f"the rulesets could not be loaded ({type(exc).__name__})") for s in unique)
    results: list[NodeScreening] = []
    for s in unique:
        mol, problem = _parse(s)
        if mol is None:
            results.append(NodeScreening(smiles=s, screened=False, reason=problem))
            continue
        try:
            found: dict[str, tuple[Finding, Ruleset]] = {}
            consulted: tuple[str, ...] = ()
            for part in _parts(mol):
                report = engine.screen(part, include_near_misses=False)
                by_rule = {rule.rule_id: ruleset for ruleset in report.rulesets_consulted for rule in ruleset.rules}
                consulted = tuple(r.ruleset_id for r in report.rulesets_consulted)
                for finding in report.findings:
                    found.setdefault(finding.rule.rule_id, (finding, by_rule[finding.rule.rule_id]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("A route node's regulatory screen raised: %s", exc)
            results.append(NodeScreening(smiles=s, screened=False, reason=f"the screen failed ({type(exc).__name__})"))
            continue
        findings = tuple(
            AlertFinding(
                ruleset_id=ruleset.ruleset_id,
                rule_id=f.rule.rule_id,
                display_name=f.rule.display_name,
                domain=ruleset.domain.value,
                jurisdiction=f.rule.jurisdiction.value,
                section=f.rule.legal.section,
                confidence=f.rule.interpretation.confidence.value,
                match_type=f.match_type.value,
                user_supplied=ruleset.user_supplied,
            )
            for f, ruleset in found.values()
        )
        results.append(NodeScreening(smiles=s, screened=True, findings=findings, rulesets_consulted=consulted, screened_on=stamp))
    return tuple(results)
