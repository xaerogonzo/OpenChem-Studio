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

EVERY LINE IS ASCII. These reach `AlertResult.matched`, which goes to Qt,
to logs and to console streams, and a Windows cp1252 stream raises on an
em-dash or a tick. `test_naming_result_lines_stay_ascii` exists because
that was hit three times in one session.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem

from openchem.chem.regulatory.engine import RegulatoryEngine
from openchem.chem.regulatory.loader import load_all
from openchem.chem.regulatory.types import Jurisdiction, MatchType, ScreeningReport
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import AlertResult
from openchem.domain.structure_issue import Severity

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
) -> AlertResult:
    """Which regulatory frameworks have something to say about this structure.

    NOT a compliance check, and the result never says one way or the other.
    See `regulatory/types.py` for why that distinction is architectural.
    """
    options = parameters or {}
    chosen = JURISDICTION_CHOICES.get(options.get("jurisdiction", "All jurisdictions"), "")
    jurisdictions = {Jurisdiction(chosen)} if chosen else None
    include_near_misses = bool(options.get("include_near_misses", True))

    engine, problems = _shared_engine()
    report = engine.screen(
        mol, jurisdictions=jurisdictions, include_near_misses=include_near_misses
    )

    lines = _finding_lines(report)
    if include_near_misses:
        lines.extend(_near_miss_lines(report))
    if not report.findings:
        # The one case where a blank cell would be actively misleading.
        lines.insert(0, report.summary())

    return AlertResult(
        alert_id="regulatory_screen",
        name="Regulatory Screen",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="regulatory",
        # The one producer whose severity depends on its own content. A
        # finding is something to act on; "no matches in the 3 rulesets
        # consulted" is a coverage statement and must not be painted as
        # though the molecule were flagged -- which is exactly how it
        # read before severity existed.
        severity=Severity.WARNING if report.findings else Severity.INFO,
        cache_state=CacheState.COMPLETED,
        provenance=Provenance(
            created_by="core",
            method="regulatory-intelligence",
            parameters={
                "jurisdiction": options.get("jurisdiction", "All jurisdictions"),
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
