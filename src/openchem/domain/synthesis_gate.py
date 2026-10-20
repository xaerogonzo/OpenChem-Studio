"""What the regulatory gate on synthesis planning decides, and what it says about the molecules of a route (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 2). Pure types; the screening itself is `chem/synthesis_gate.py`.

TWO DIFFERENT THINGS, KEPT APART ON PURPOSE:

* **The gate** is one decision about the TARGET, made before any process starts: `ALLOWED`, `REFUSED` (the target matches an entry of CWC Schedule 1) or `UNSCREENED` (the gate could not tell, so nothing starts). It is the only place a plan is refused, and it fails closed: a ruleset that is missing, broken or shadowed, a structure that cannot be read, or a screen that raises is `UNSCREENED`, never `ALLOWED`.
* **Alerts** are what the wider rulesets (DEA, the CWC's other schedules, a user's own) say about each molecule of a route that WAS planned: the target, its intermediates and its starting materials. An alert never refuses anything and never removes a route; it is a note on a node.

EVERY SENTENCE HERE IS A LIST MATCH, NOT A LEGAL DETERMINATION. The gate matches structures against the rules of a ruleset; the ruleset's own `known_limitations` (saxitoxin and ricin are not encoded, a carbon-count limit may over-report and will not under-report, alkylated salts are not matched) travel with every decision as data so no surface can leave them out. A refusal is not an accusation and an `ALLOWED` is not a clearance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: What the reachability guard accepts for a module nothing in the application imports YET. The gate is built first and on its own (Stage 1 slice 2); the synthesis planning service (slice 4) is its first importer, and the guard then fails this declaration, which is the reminder to delete it.
REACHED_BY = (
    "tooling: imported only by tests/test_synthesis_gate.py until the synthesis planning service (Stage 1 slice 4 of docs/SYNTHESIS_HELPER_DESIGN.md) imports it; the feature is not yet reachable from the window"
)

#: The only ruleset whose match refuses a plan.
GATE_RULESET_ID = "cwc-schedule-1"


class GateOutcome(StrEnum):
    """The gate's answer. Planning starts only on `ALLOWED`."""

    ALLOWED = "allowed"
    REFUSED = "refused"
    UNSCREENED = "unscreened"


@dataclass(frozen=True, kw_only=True)
class GateMatch:
    """One rule of the gate's ruleset that the target matched."""

    ruleset_id: str
    rule_id: str
    display_name: str
    #: Where in the instrument the entry is (for example "Schedule 1, A.1"); empty if the rule does not say.
    section: str = ""
    #: How sure the ruleset is that its machine reading matches its source text: "verified", "exact", "approximate" or "requires_review". A match on an approximate rule may be a false positive.
    confidence: str = ""
    match_type: str = ""

    def __post_init__(self) -> None:
        for name in ("ruleset_id", "rule_id", "display_name"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be blank")


@dataclass(frozen=True, kw_only=True)
class GateDecision:
    """The gate's decision about one target, with the identity of what decided it.

    `ruleset_version`, `ruleset_sha256` and `screened_on` say which rules were consulted and when. They are blank only for
    an `UNSCREENED` decision that could not load a ruleset at all.
    """

    outcome: GateOutcome
    matches: tuple[GateMatch, ...] = ()
    #: Why, in words the user is shown. Empty for `ALLOWED`.
    reason: str = ""
    ruleset_version: str = ""
    ruleset_sha256: str = ""
    screened_on: str = ""
    #: The gate ruleset's own known limitations, verbatim. Shown with every refusal.
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome is GateOutcome.REFUSED:
            if not self.matches:
                raise ValueError("a refusal names the entry it matched")
            if not self.reason.strip():
                raise ValueError("a refusal needs a reason")
        elif self.matches:
            raise ValueError(f"an '{self.outcome}' decision carries no matches")
        if self.outcome is GateOutcome.UNSCREENED and not self.reason.strip():
            raise ValueError("an unscreened decision says why it could not tell")
        if self.outcome is GateOutcome.ALLOWED:
            if self.reason:
                raise ValueError("an allowed decision has no reason")
            if not (self.ruleset_version and self.ruleset_sha256 and self.screened_on):
                raise ValueError("an allowed decision names the ruleset version, its checksum and the date it was screened")

    @property
    def permits_planning(self) -> bool:
        """The one question a caller asks. True only for `ALLOWED`: a refusal and an inability to tell both stop the plan."""
        return self.outcome is GateOutcome.ALLOWED

    def refusal_text(self) -> str:
        """What is shown to a person when planning did not start: the reason, what the decision rests on, and the list's known limits."""
        if self.permits_planning:
            return ""
        parts = [self.reason.strip()]
        if self.ruleset_version:
            parts.append(f"This is a match against the structural rules of the shipped ruleset {GATE_RULESET_ID}, version {self.ruleset_version}, screened {self.screened_on}; it is not a legal determination.")
        if any(match.confidence in ("approximate", "requires_review") for match in self.matches):
            parts.append("The rule that matched is marked approximate, so this may be a false positive; no planning was started either way.")
        if self.limitations:
            parts.append("Known limits of that list: " + " ".join(self.limitations))
        return " ".join(parts)


@dataclass(frozen=True, kw_only=True)
class AlertFinding:
    """One rule a molecule of a route matched, in a ruleset the gate does not use to refuse."""

    ruleset_id: str
    rule_id: str
    display_name: str
    domain: str
    jurisdiction: str
    section: str = ""
    confidence: str = ""
    match_type: str = ""
    #: True for a ruleset the user supplied rather than one shipped with the application.
    user_supplied: bool = False


@dataclass(frozen=True, kw_only=True)
class NodeScreening:
    """What the wider rulesets say about one molecule of a route: `findings` (empty means nothing matched among `rulesets_consulted`, NOT that nothing applies) or, if it could not be screened, why.

    `screened` False means the screen did not run for this molecule (it could not be read, or the screen raised); then `findings` is empty and `reason` says why, and no surface may read the empty findings as "nothing matched".
    """

    smiles: str
    screened: bool
    findings: tuple[AlertFinding, ...] = ()
    rulesets_consulted: tuple[str, ...] = ()
    screened_on: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.smiles.strip():
            raise ValueError("smiles cannot be blank")
        if self.screened:
            if self.reason:
                raise ValueError("a screened molecule has no failure reason")
            if not self.screened_on:
                raise ValueError("a screened molecule records the date it was screened")
        else:
            if self.findings or self.rulesets_consulted:
                raise ValueError("a molecule that was not screened carries no findings or rulesets")
            if not self.reason.strip():
                raise ValueError("a molecule that was not screened says why")

    @property
    def has_alert(self) -> bool:
        return bool(self.findings)
