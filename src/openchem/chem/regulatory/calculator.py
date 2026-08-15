"""The regulatory screen as a registered calculator.

Registering it rather than building a panel is what makes it reach
everything at once: the Property panel renders it, the Calculator Inspector
gives it 2D and 3D atom highlighting through the same per-atom colour path
the annotation calculators use, and Thread 2's batch table screens an entire
project and exports it. None of that needed new UI.

WHERE THE SCOPE STATEMENT LIVES, and it is a real decision rather than
plumbing. The engine's whole discipline is that "no matches" must arrive
with the scope of what was checked -- but that scope is a property of the
RULESETS, identical for every molecule, and repeating it down 50,000 rows
of a batch table is noise that trains people to stop reading. So:

  * `matched` carries the FINDINGS, one line each.
  * With no findings it carries ONE line saying how many rulesets were
    consulted, because a blank cell in a regulatory column is exactly the
    silence-read-as-reassurance this engine exists to prevent.
  * The full coverage notes, ruleset versions and unchecked domains go in
    `Provenance.parameters`, which is this codebase's established home for
    exactly this kind of metadata, and which a view can show ONCE per
    screen instead of once per row.

EVERY LINE IS ASCII. These reach Qt, logs and console streams, and a
Windows cp1252 stream raises on an em-dash or a tick.
`test_naming_result_lines_stay_ascii` exists because that was hit three
times in one session.

**The scope is no longer invisible.** This used to bury the rulesets
consulted, the coverage notes and the unchecked domains in
`Provenance.parameters`, where nothing displayed them -- the panel showed
`1 alert(s): No matches in the 1 ruleset consulted` and stopped. They are
facts now, so the screen reads as the document it always was. The ruleset
versions and coverage notes are marked ADVANCED, so they are there for
somebody who needs them without burying the findings.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem

from openchem.chem.regulatory.engine import (
    EffectiveDateError,
    RegulatoryEngine,
    parse_effective_date,
)
from openchem.chem.regulatory.loader import load_all
from openchem.chem.regulatory.types import Jurisdiction, MatchType, ScreeningReport
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import Detail, Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

#: Jurisdiction filter offered in the UI. "All" first, because a user who
#: has not said where they are should see more rather than less.
JURISDICTION_CHOICES: dict[str, str] = {
    "All jurisdictions": "",
    "International (treaties, UN)": Jurisdiction.INTERNATIONAL.value,
    "United States": Jurisdiction.US.value,
    "European Union": Jurisdiction.EU.value,
    "United Kingdom": Jurisdiction.UK.value,
    "Canada": Jurisdiction.CANADA.value,
    "Australia": Jurisdiction.AUSTRALIA.value,
    "Japan": Jurisdiction.JAPAN.value,
    "China": Jurisdiction.CHINA.value,
    "India": Jurisdiction.INDIA.value,
}

_engine: RegulatoryEngine | None = None
_load_problems: list[str] = []


def _shared_engine() -> tuple[RegulatoryEngine, list[str]]:
    """Rulesets are read once and reused.

    Loading is file I/O and JSON parsing, and a batch run calls this once
    per molecule. Cached at module level the same way the PAINS and BRENK
    catalogs are.
    """
    global _engine, _load_problems
    if _engine is None:
        rulesets, problems = load_all()
        _engine = RegulatoryEngine(rulesets)
        _load_problems = problems
    return _engine, _load_problems


def reset_engine() -> None:
    """Drop the cached engine so newly-added user rulesets are picked up."""
    global _engine, _load_problems
    _engine = None
    _load_problems = []


def compute_regulatory_screen(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
) -> ReportResult:
    """Which regulatory frameworks have something to say about this structure.

    NOT a compliance check, and the result never says one way or the other.
    See `regulatory/types.py` for why that distinction is architectural.
    """
    options = parameters or {}
    chosen = JURISDICTION_CHOICES.get(options.get("jurisdiction", "All jurisdictions"), "")
    jurisdictions = {Jurisdiction(chosen)} if chosen else None
    include_near_misses = bool(options.get("include_near_misses", True))

    requested_date = str(options.get("as_of", "") or "").strip()
    try:
        as_of = parse_effective_date(requested_date)
    except EffectiveDateError:
        return _refuse_an_unreadable_date(molecule_uuid, options, requested_date)

    engine, problems = _shared_engine()
    report = engine.screen(
        mol,
        jurisdictions=jurisdictions,
        include_near_misses=include_near_misses,
        as_of=as_of,
    )

    lines = _finding_lines(report)
    if include_near_misses:
        lines.extend(_near_miss_lines(report))
    if not report.findings:
        # The one case where a blank cell would be actively misleading.
        lines.insert(0, report.summary())

    facts = [_line_fact(line) for line in lines]

    # THE DATE GOES WITH THE ANSWER, NOT WITH THE SCOPE. `summary()` carries
    # it too, but only reaches the panel when there are no findings -- so a
    # dated screen that DID match would otherwise look exactly like an
    # undated one. STANDARD rather than ADVANCED, for the same reason
    # "NOT checked" is: a date that changes what matched is not specialist
    # information, and burying it would defeat the point of asking.
    if as_of is not None:
        facts.append(
            Fact(
                category=FactCategory.REGULATORY,
                label="Screened as of",
                value=as_of.isoformat(),
                display_value=as_of.isoformat(),
                source="Regulatory",
                basis=Basis.DETERMINISTIC,
                limitations=(
                    "Rules taking effect after this date were not evaluated. "
                    "No ruleset here records repeal or expiry, so a rule since "
                    "removed from a schedule is still reported.",
                ),
            )
        )

    # WHAT USED TO BE INVISIBLE. All of this was already computed into
    # `Provenance.parameters` and NONE of it reached the screen: the panel
    # showed "1 alert(s): No matches in the 1 ruleset consulted" and
    # nothing else. A regulatory answer without its scope is the
    # silence-read-as-reassurance this engine exists to prevent, so the
    # scope is now facts of its own.
    for ruleset in report.rulesets_consulted:
        facts.append(
            Fact(
                category=FactCategory.REGULATORY,
                label="Ruleset consulted",
                value=ruleset.ruleset_id,
                display_value=f"{ruleset.ruleset_id} v{ruleset.version}",
                source="Regulatory",
                basis=Basis.DETERMINISTIC,
                detail=Detail.ADVANCED,
            )
        )
    for note in report.coverage_notes():
        facts.append(
            Fact(
                category=FactCategory.REGULATORY,
                label="Coverage",
                value=note,
                display_value=note,
                source="Regulatory",
                basis=Basis.DETERMINISTIC,
                detail=Detail.ADVANCED,
            )
        )
    # A RULESET'S OWN LIMITS, which were loaded and shown NOWHERE -- the
    # same gap the coverage notes above were in before they became facts.
    # These are what a ruleset says it does NOT encode ("the 2019 additions
    # are not encoded", "listing is for verification thresholds and is not
    # a prohibition"), so a rule that fails to match says nothing about them.
    #
    # ADVANCED, beside the coverage notes and ruleset versions, because it
    # is the same KIND of thing: per-ruleset scope, identical for every
    # molecule. `test_coverage_travels_in_provenance_not_in_every_row`
    # makes that argument already.
    #
    # WHAT THAT FLAG DOES AND DOES NOT DO, measured rather than assumed:
    # `FactView` hides ADVANCED facts unless asked for everything, so this
    # keeps them out of the Details dialog's default view. The PROPERTY
    # PANEL renders every fact whatever its detail -- deliberately, see the
    # "EVERY fact, never a slice" comment at its render site -- so these
    # nine lines DO appear there and this flag does not shorten it. An
    # earlier version of this comment claimed the flag cut the panel from
    # 21 rows to 12; it does not, and reading the panel's code is what
    # showed so.
    for ruleset in report.rulesets_consulted:
        for limitation in ruleset.known_limitations:
            facts.append(
                Fact(
                    category=FactCategory.REGULATORY,
                    label=f"{ruleset.display_name} does not cover",
                    value=limitation,
                    display_value=limitation,
                    source="Regulatory",
                    basis=Basis.DETERMINISTIC,
                    detail=Detail.ADVANCED,
                )
            )
    for domain in report.domains_without_rulesets:
        facts.append(
            Fact(
                category=FactCategory.REGULATORY,
                label="NOT checked",
                value=domain.value,
                display_value=domain.value,
                source="Regulatory",
                basis=Basis.DETERMINISTIC,
                limitations=(
                    "No ruleset is loaded for this domain, so this screen "
                    "says nothing about it either way.",
                ),
            )
        )

    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="regulatory_screen",
        name="Regulatory Screen",
        category="admet",
        facts=tuple(facts),
        cache_state=CacheState.COMPLETED,
        limitations=tuple(problems),
        provenance=Provenance(
            created_by="core",
            method="regulatory-intelligence",
            parameters={
                "jurisdiction": options.get("jurisdiction", "All jurisdictions"),
                # THE ISO STRING, NEVER THE `date` OBJECT. Provenance
                # parameters are persisted straight into a saved project,
                # and a value that will not serialise is DROPPED rather
                # than stringified -- so storing the object would silently
                # lose the one field that says which screen this was.
                "as_of": as_of.isoformat() if as_of is not None else "",
                "rules_withheld_by_date": [
                    rule_id for _, rule_id in report.rules_withheld_by_date
                ],
                "rulesets": [
                    f"{r.ruleset_id}@{r.version}" for r in report.rulesets_consulted
                ],
                "coverage": list(report.coverage_notes()),
                "domains_not_checked": [
                    d.value for d in report.domains_without_rulesets
                ],
                "ruleset_load_problems": list(problems),
                "conflicts": [
                    f"matched in {'/'.join(j.value for j in c.matched_in)}, "
                    f"no match in {'/'.join(j.value for j in c.no_match_in)}"
                    for c in report.conflicts
                ],
            },
        ),
    )


def _refuse_an_unreadable_date(
    molecule_uuid: str,
    options: dict[str, Any],
    requested: str,
) -> ReportResult:
    """A date the user typed that cannot be read REFUSES the whole screen.

    NOT a fallback to an undated run with a warning attached, which was the
    first design and is wrong in the way this module is least able to
    afford. Someone who types `2019/13/99` is asking what applied in 2019;
    handing them today's rulesets with a caveat somewhere in the result is
    answering a different question and presenting it as the one they asked.
    They would have to notice the caveat to know they had been given the
    wrong answer, and the whole discipline here is that a reader should not
    have to notice anything to be safe.

    So: no findings, no near misses, no coverage notes -- nothing that
    could be read as a screen having happened. `CacheState.FAILED` with the
    reason in `error` is the shape the panel already renders with a failure
    glyph, and is what geometry-without-a-conformer uses.

    The contrast is deliberate. A malformed date inside a RULESET FILE
    degrades that one rule to undated and is reported, because one bad
    entry must not cost somebody every other rule. A malformed date from
    the USER refuses, because it is the question itself that is broken.
    """
    message = (
        f"'{requested}' is not a date this screen can read. Use YYYY-MM-DD, "
        "or leave the field blank to screen against every loaded rule."
    )
    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="regulatory_screen",
        name="Regulatory Screen",
        category="admet",
        facts=(),
        cache_state=CacheState.FAILED,
        error=message,
        limitations=(
            "No screening was performed, so this result says nothing about "
            "this structure either way.",
        ),
        provenance=Provenance(
            created_by="core",
            method="regulatory-intelligence",
            parameters={
                "jurisdiction": options.get("jurisdiction", "All jurisdictions"),
                # The value AS TYPED, so the record says what was asked for
                # rather than what could be made of it.
                "as_of": requested,
                "as_of_refused": True,
            },
        ),
    )


def _line_fact(line: str) -> Fact:
    """One screen line as a fact, keeping the label it already carried.

    These lines were written to be self-labelling -- `"Near miss: ..."`,
    `"    limitation: ..."` -- so the label is taken from the line rather
    than invented, and `ReportResult.matched` recomposes the original text
    byte-for-byte. That is what lets the existing assertions, the batch
    columns and any downstream export survive the migration unchanged.
    """
    stripped = line.strip()
    for prefix, label in (
        ("Near miss: ", "Near miss"),
        ("also used legitimately for: ", "Legitimate uses"),
        ("limitation: ", "Limitation"),
    ):
        if stripped.startswith(prefix):
            return Fact(
                category=FactCategory.REGULATORY,
                label=label,
                value=stripped[len(prefix):],
                display_value=stripped[len(prefix):],
                source="Regulatory",
                basis=Basis.DETERMINISTIC,
            )
    return Fact(
        category=FactCategory.REGULATORY,
        label="Regulatory Screen",
        value=stripped,
        display_value=stripped,
        source="Regulatory",
        basis=Basis.DETERMINISTIC,
    )


def _finding_lines(report: ScreeningReport) -> list[str]:
    """One line per finding, carrying enough to act on without a drill-down."""
    lines: list[str] = []
    for finding in report.findings:
        rule = finding.rule
        parts = [
            f"{rule.display_name} [{rule.jurisdiction.value}, "
            f"{finding.match_type.value}, {rule.interpretation.confidence.value}]"
        ]
        if rule.legal.section:
            parts.append(f"per {rule.legal.authority} {rule.legal.section}")
        if finding.similarity is not None:
            # Reported as the raw fingerprint similarity it is. NOT a
            # probability that anything applies -- an analogue provision
            # turns on intent and effect, which no structure carries.
            parts.append(
                f"similarity {finding.similarity:.2f} to {finding.similar_to}"
            )
        lines.append(": ".join(parts) if len(parts) == 1 else " - ".join(parts))

        # A precursor without its legitimate uses reads as an accusation:
        # acetic anhydride is a listed precursor AND the reagent for
        # aspirin and cellulose acetate.
        if rule.match_type is MatchType.PRECURSOR and rule.legitimate_uses:
            lines.append(
                f"    also used legitimately for: {', '.join(rule.legitimate_uses)}"
            )
        for limitation in rule.interpretation.limitations:
            lines.append(f"    limitation: {limitation}")
    return lines


def _near_miss_lines(report: ScreeningReport) -> list[str]:
    """The "why didn't this match?" answer, for the nearest rules only.

    Capped at three, because past that the list stops being an explanation
    and becomes a catalogue of everything the structure is not.
    """
    lines: list[str] = []
    for near in report.near_misses[:3]:
        missing = [o.label for o in near.outcomes if not o.passed]
        present = [o.label for o in near.outcomes if o.passed]
        lines.append(
            f"Near miss: {near.rule.display_name} - has {', '.join(present)}; "
            f"lacks {', '.join(missing)}"
        )
    return lines
