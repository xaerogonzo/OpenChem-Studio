"""Setting what the assistant says against what the application knows (`docs/AI_CALCULATION_BRIDGE.md`, section 28).

**WHY THIS EXISTS.** A live run of a local 14B model (section 27) never started a job without an Approve, which is the design, but twice told the person "a preview is on your screen" when it
had called nothing, and once answered "already computed and stored, 18.01528 g/mol" without reading anything. The person looking at the screen sees there is no card; the sentence they were
told is wrong, and nothing in the application checked it. The application knows both facts without trusting the model: whether an approval card is showing, and what the model was actually shown.

Two claims are checked, both against the application's own state, and nothing else:

- **A waiting approval that is not there.** The reply says a preview, card or approval is waiting, and no approval card is showing.
- **A number the model was never shown.** The reply states a decimal number that appears in nothing the model was given: the molecule summary, the person's messages (and the application's notes
  with them) and the tool results of this reply. Rounding is honest and allowed (a reply's 18.015 for a shown 18.01528); more precision than anything shown is not. The model's OWN earlier replies
  are not evidence, or a number once invented would pass the next time it was repeated.

**What it does not do.** It does not judge whether a number is right (18.01528 is the right weight of water; it still came from nowhere the application showed), whether the model's reading of a result is
sound, or any claim it has no state for (that a job is running, finished, or what a result means). A sentence that does not match a pattern here is not thereby true. Pure: no Qt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Present-tense claims that an approval is pending. Conditional wording ("ORCA starts only if you approve it") is deliberately not matched: it says what WOULD happen, not what is showing. Each of
#: these is a sentence the live runs produced.
_WAITING_CLAIMS = (
    re.compile(r"\b(?:awaiting|waiting\s+for)\b[^.\n]{0,40}\bapproval\b", re.IGNORECASE),
    re.compile(r"\bpreview\b[^.\n]{0,40}\b(?:on|in)\b[^.\n]{0,15}\bscreen\b", re.IGNORECASE),
    re.compile(r"\b(?:approve|review)\b[^.\n]{0,25}\b(?:the|this|that|your)\s+(?:preview|card)\b", re.IGNORECASE),
)

#: A decimal number: digits, a point, digits, not part of a longer token (a version "2.5.1", an identifier). A sentence's own full stop after it is not part of the number, so "is 18.01528." is read. A leading sign is not part of it.
_DECIMAL = re.compile(r"(?<![\w.])\d+\.\d+(?!\w|\.\d)")

@dataclass(frozen=True)
class Finding:
    """One claim the application's own state does not support."""

    kind: str
    #: What the person is told, under the reply.
    message: str
    #: What the model is told with the person's next message, so it can correct itself.
    note: str


#: A word that turns a sentence about a waiting preview into a denial of one. A live reply said "There is no current preview waiting for your approval": the same words, the opposite claim.
_NEGATION = re.compile(r"\b(?:no|not|nothing|none|never|without)\b|n't\b", re.IGNORECASE)
_SENTENCE_START = re.compile(r"[.!?\n]")


def claims_a_waiting_approval(reply: str) -> bool:
    """Whether `reply` says, in the present tense, that a preview or card is waiting for the person. A sentence that denies it ("no preview is waiting") is not a claim."""
    for pattern in _WAITING_CLAIMS:
        for match in pattern.finditer(reply):
            before = reply[: match.start()]
            starts = list(_SENTENCE_START.finditer(before))
            sentence_before = before[starts[-1].end():] if starts else before
            if not _NEGATION.search(sentence_before):
                return True
    return False


def _decimals(text: str) -> list[str]:
    return _DECIMAL.findall(text)


def _places(number: str) -> int:
    return len(number.split(".")[1])


def _supported(number: str, shown: list[str]) -> bool:
    """Whether `number` is something a shown number rounds to: equal, or equal at the (no greater) number of places `number` has."""
    places = _places(number)
    value = float(number)
    for candidate in shown:
        if _places(candidate) < places:
            continue  # more precision than what was shown cannot have been read from it
        if round(float(candidate), places) == value:
            return True
    return False


def unshown_numbers(reply: str, shown_text: str) -> list[str]:
    """The decimal numbers in `reply` that nothing in `shown_text` supports, in order, each once."""
    shown = _decimals(shown_text)
    out: list[str] = []
    for number in _decimals(reply):
        if number not in out and not _supported(number, shown):
            out.append(number)
    return out


def check_reply(reply: str, *, approvals_waiting: int, shown_text: str, tools_offered: bool) -> list[Finding]:
    """What in `reply` the application's own state does not support.

    `approvals_waiting` is the number of approval cards showing (a job, a proposed score, a synthesis search), `shown_text` everything the model was shown that is not its own words, and
    `tools_offered` whether it had tools: without any, a number can only come from the molecule summary or from memory, and the rule that a value must come from a tool result is not one it could keep.
    """
    findings: list[Finding] = []
    if approvals_waiting == 0 and claims_a_waiting_approval(reply):
        findings.append(Finding(
            "waiting_approval",
            "Application check: the reply says something is waiting for your approval, but no approval card is showing. Nothing was requested and nothing will start.",
            "Your last reply said a preview was waiting for the person's approval, but no approval card exists: nothing was requested. Say so plainly; call run_calculator if they still want it.",
        ))
    if tools_offered:
        numbers = unshown_numbers(reply, shown_text)
        if numbers:
            listed = ", ".join(numbers)
            findings.append(Finding(
                "unshown_number",
                f"Application check: {listed} appear{'s' if len(numbers) == 1 else ''} nowhere in what the application showed the model (the molecule summary, your messages, calculator results). "
                "Treat it as the model's own, not a result from this application.",
                f"Your last reply stated {listed}, which no tool result or message contained. State a value only if a tool result contains it, and say where a number came from.",
            ))
    return findings
