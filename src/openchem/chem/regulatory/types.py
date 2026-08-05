"""What a regulatory rule IS, and what a match against one means.

THE ENGINE ANSWERS "WHAT FRAMEWORKS APPLY", NOT "IS THIS LEGAL". That is
not a wording preference, it is the whole design. A boolean compliance
answer ages badly, cannot express that two jurisdictions disagree, and
invites the reading nobody should make -- that a silent result means a
substance is unregulated. Everything here reports what was found, from
which framework, under which jurisdiction, as of which revision, and is
explicit about what it did not consult.

THE LAW AND OUR READING OF IT ARE SEPARATE RECORDS, and this is the most
important structural decision in the module. A rule is not
"citation -> SMARTS". Regulations carry language that structure alone
cannot express -- "except...", "other than...", "when intended for...",
"and its salts, isomers, and salts of isomers" -- and every one of those
becomes an implementation decision when it is turned into a pattern. A
rule that stored only the pattern would have silently absorbed a
judgement call as if it were the statute. So `LegalSource` holds the
authority, the instrument, the section and a VERBATIM QUOTE, and
`MachineInterpretation` holds the pattern plus the assumptions made and
the limitations accepted in writing it. Someone auditing this years from
now can then see both, and see where they diverge.

NOTHING HERE SAYS "COMPLIANT", and nothing says "not controlled". The
vocabulary is matched rules, rulesets consulted, coverage, revision date.
A `ScreeningReport` with no findings states which rulesets ran and how
complete they are, because "we checked these four lists, which cover this
much" is a true statement and "this substance is not controlled" is not
one this software can make.

Precedent for all of the above is already in this codebase: the hERG
checklist ships as "a risk-factor checklist, explicitly not a prediction",
and the naming results carry `source` and `kind` rather than an invented
confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Jurisdiction(str, Enum):
    """Whose law. Present from the start so adding one is a ruleset file
    rather than a refactor, and so a finding can be filtered to the places
    that actually apply to the person reading it."""

    US = "us"
    EU = "eu"
    UK = "uk"
    CANADA = "ca"
    AUSTRALIA = "au"
    JAPAN = "jp"
    CHINA = "cn"
    INDIA = "in"
    #: Treaties and UN model regulations, which are not one country's law.
    INTERNATIONAL = "international"
    #: A company, university or teaching-lab policy. Never merged with a
    #: statutory ruleset in reporting -- they are different kinds of claim.
    ORGANISATION = "organisation"


class Domain(str, Enum):
    """Which body of regulation. Registered even when empty: a domain with
    no rulesets loaded says so in the coverage report, where a domain that
    simply does not exist is invisible and reads as "nothing applies"."""

    CONTROLLED_SUBSTANCES = "controlled_substances"
    CHEMICAL_WEAPONS = "chemical_weapons"
    DRUG_PRECURSORS = "drug_precursors"
    EXPORT_CONTROLS = "export_controls"
    HAZARDOUS_CHEMICALS = "hazardous_chemicals"
    OCCUPATIONAL_EXPOSURE = "occupational_exposure"
    ENVIRONMENTAL = "environmental"
    EXPLOSIVES = "explosives"
    TRANSPORT = "transport"
    FOOD = "food"
    COSMETICS = "cosmetics"
    AGRICULTURE = "agriculture"


class MatchType(str, Enum):
    """WHAT KIND OF CLAIM a finding is making. These are not degrees of one
    thing; they are different statements, and collapsing them into
    "matched" would be the single most misleading simplification available.
    """

    #: This exact substance, by salt-normalised identity.
    IDENTITY = "identity"
    #: The regulation defines a family structurally and this is in it.
    #: As strong as identity, because the family IS the specification.
    STRUCTURAL_FAMILY = "structural_family"
    #: Structurally close to a listed substance. NOT a determination that
    #: anything applies -- analogue provisions turn on intent and effect,
    #: which no structure can carry. Always accompanied by a similarity.
    ANALOGUE = "analogue"
    #: A listed input to a controlled synthesis. Carries legitimate uses,
    #: because most precursors are ordinary reagents.
    PRECURSOR = "precursor"
    #: Reserved. Some parents are unscheduled while metabolites are not.
    #: NOTHING IS PREDICTED -- the type exists so a curated list could
    #: populate it, and no code produces one today.
    METABOLITE = "metabolite"


class RuleConfidence(str, Enum):
    """How much the machine interpretation is trusted to reflect the law.

    Four levels because a CWC generic family and a reading of DEA analogue
    prose are not the same kind of artefact, and presenting them
    identically would flatten the one distinction an auditor most needs.
    """

    #: The regulation itself is a structural specification, so the pattern
    #: is a transcription rather than an interpretation.
    EXACT = "exact"
    #: An identity checked against the primary text.
    VERIFIED = "verified"
    #: Our reading of prose that structure cannot fully express.
    APPROXIMATE = "approximate"
    #: Unresolved or disputed. Surfaced in the coverage report and never
    #: silently used; the build fails if these accumulate past a threshold.
    REQUIRES_REVIEW = "requires_review"


@dataclass(frozen=True)
class LegalSource:
    """The regulation, in its own words.

    `quote` is verbatim on purpose. A paraphrase is already an
    interpretation, and the point of this record is to be the thing the
    interpretation can be checked against.
    """

    authority: str          # "OPCW", "US DEA", "European Commission"
    instrument: str         # "Chemical Weapons Convention, Annex on Chemicals"
    section: str            # "Schedule 1, A.1"
    quote: str = ""
    citation_url: str = ""
    effective_date: str = ""  # ISO date; what the LAW says, not our reading
    #: CAS numbers PRINTED IN THE REGULATION travel with the citation.
    #: This is not a CAS database and must never become one -- the registry
    #: is proprietary to ACS and cannot be redistributed. A number quoted
    #: by a statute is part of that statute's text.
    cited_identifiers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MachineInterpretation:
    """Our reading of a `LegalSource`, and what it cost to make it one.

    `assumptions` and `limitations` are the fields that make this record
    worth having. "Salts are matched by stripping counter-ions" is an
    assumption; "the 'when intended for' clause is not evaluated" is a
    limitation. Both are invisible in a SMARTS string and both change what
    a match means.
    """

    #: A predicate expression (see `predicates.py`) or a bare SMARTS.
    expression: dict | str = ""
    #: Salt-normalised InChIKeys, for identity rules.
    inchikeys: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    confidence: RuleConfidence = RuleConfidence.REQUIRES_REVIEW
    #: Bumped when OUR pattern improves without the law changing. Distinct
    #: from `LegalSource.effective_date`, so "the rule changed" and "the
    #: law changed" stay tellable apart.
    interpreter_version: int = 1


@dataclass(frozen=True)
class Rule:
    """One regulated thing: what the law says, and how we look for it."""

    rule_id: str
    display_name: str
    domain: Domain
    jurisdiction: Jurisdiction
    match_type: MatchType
    legal: LegalSource
    interpretation: MachineInterpretation
    description: str = ""
    #: Why a precursor is also an ordinary reagent. REQUIRED in practice
    #: for `MatchType.PRECURSOR`: reporting acetic anhydride as a heroin
    #: precursor without mentioning aspirin and cellulose acetate turns an
    #: intelligence tool into an accusation.
    legitimate_uses: tuple[str, ...] = ()
    #: Display text lives here, apart from the logic above, so a future
    #: translation never touches the chemistry.
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True)
class PredicateOutcome:
    """One condition's result, kept whether it passed or failed.

    Failures are retained deliberately -- they are what lets the engine say
    "nearest rule, failed on one predicate" instead of staying silent, and
    a near-miss is often the most useful thing a screen can report.
    """

    label: str
    passed: bool
    detail: str = ""
    atoms: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Finding:
    """One rule matching one structure, with everything needed to justify it.

    Carries the atoms so a view can colour them through the same per-atom
    path the annotation calculators use, and carries the predicate outcomes
    so "why" is answerable without re-running anything.
    """

    rule: Rule
    match_type: MatchType
    atoms: frozenset[int] = frozenset()
    outcomes: tuple[PredicateOutcome, ...] = ()
    #: Populated for ANALOGUE only, and it is a raw fingerprint similarity
    #: against a named listed substance -- NOT a probability that anything
    #: applies. Manufacturing a calibrated-looking number here would be the
    #: same fabricated precision this project refuses for NMR RMSE and hERG.
    similarity: float | None = None
    similar_to: str = ""

    @property
    def explanation(self) -> tuple[str, ...]:
        """The matched and missing conditions, in reading order.

        ASCII ONLY, and that is a hard constraint rather than a style
        choice. These lines reach `AlertResult.matched`, which goes to Qt,
        to logs and to console streams -- and a Windows cp1252 stream
        raises `UnicodeEncodeError` on an em-dash or a tick.
        `test_naming_result_lines_stay_ascii` exists because that was hit
        three times in one session, and this is the same class of string.
        "+"/"-" carry the checklist reading without the hazard.
        """
        return tuple(
            f"{'+' if outcome.passed else '-'} {outcome.label}"
            + (f" ({outcome.detail})" if outcome.detail else "")
            for outcome in self.outcomes
        )


@dataclass(frozen=True)
class NearMiss:
    """A rule this structure ALMOST matched.

    The answer to "why didn't this match?", which is the question a
    legitimate user asks when trying to understand where a boundary runs.
    `distance` is how many predicates failed, so the nearest rules sort
    first.
    """

    rule: Rule
    distance: int
    outcomes: tuple[PredicateOutcome, ...] = ()


@dataclass(frozen=True)
class RulesetProvenance:
    """Enough to REGENERATE a ruleset, not merely to date it.

    `rdkit_version` is here for a concrete reason rather than for
    ceremony: aromaticity perception and SMARTS matching semantics change
    between RDKit releases, so the same rule against the same structure can
    change answer under a different one. Without it recorded a ruleset can
    be re-run but not reproduced.
    """

    generator: str = ""
    generator_version: str = ""
    generated_at: str = ""
    source_document_sha256: str = ""
    ruleset_sha256: str = ""
    opsin_version: str = ""
    rdkit_version: str = ""


@dataclass(frozen=True)
class RulesetCoverage:
    """How complete a ruleset is, as a number the UI can quote.

    Exists because the dangerous failure of a screening tool is silence
    read as reassurance. A report that says "no matches" while a ruleset
    resolved 180 of 261 entries is telling the user much less than it
    appears to, and the only fix is to say so in the same breath.
    """

    total_entries: int = 0
    resolved: int = 0
    unresolved: tuple[str, ...] = ()
    requires_review: tuple[str, ...] = ()
    manual_entries: int = 0

    @property
    def fraction(self) -> float:
        return self.resolved / self.total_entries if self.total_entries else 0.0

    def describe(self) -> str:
        if not self.total_entries:
            return "no entries loaded"
        return (
            f"{self.resolved} of {self.total_entries} entries resolved "
            f"({self.fraction:.0%})"
        )


@dataclass(frozen=True)
class Ruleset:
    """A body of rules from one instrument, with its own provenance."""

    ruleset_id: str
    display_name: str
    domain: Domain
    jurisdiction: Jurisdiction
    version: str
    effective_date: str = ""
    supersedes: str = ""
    source_citation: str = ""
    rules: tuple[Rule, ...] = ()
    coverage: RulesetCoverage = field(default_factory=RulesetCoverage)
    provenance: RulesetProvenance = field(default_factory=RulesetProvenance)
    known_limitations: tuple[str, ...] = ()
    #: True for anything loaded from the user's data directory. Kept
    #: separate in every report: a company policy and a statute are
    #: different kinds of claim and merging them would destroy the only
    #: thing that makes the output trustworthy.
    user_supplied: bool = False


@dataclass(frozen=True)
class JurisdictionConflict:
    """Two jurisdictions reaching different answers about one structure.

    Reported rather than resolved. Which one governs depends on where
    someone is and what they are doing, and a tool that picked for them
    would be making a legal determination it is in no position to make.
    """

    structure_note: str
    matched_in: tuple[Jurisdiction, ...]
    no_match_in: tuple[Jurisdiction, ...]


@dataclass(frozen=True)
class ScreeningReport:
    """The whole answer: what matched, what nearly did, and what was asked.

    `rulesets_consulted` and `coverage_notes` are not decoration. With no
    findings, they ARE the result -- "these four rulesets ran, at these
    revisions, with this coverage" is a statement this software can support,
    where "this substance is not controlled" is not.
    """

    findings: tuple[Finding, ...] = ()
    near_misses: tuple[NearMiss, ...] = ()
    conflicts: tuple[JurisdictionConflict, ...] = ()
    rulesets_consulted: tuple[Ruleset, ...] = ()
    #: Domains registered with nothing loaded. Listed so an empty domain
    #: reads as "not checked" rather than as "checked and clear".
    domains_without_rulesets: tuple[Domain, ...] = ()

    @property
    def matched(self) -> bool:
        return bool(self.findings)

    def summary(self) -> str:
        """One line, in the permitted vocabulary.

        Never "compliant", never "not controlled" -- see the module
        docstring. This says what was done, not what is true of the world.
        """
        if self.findings:
            domains = sorted({f.rule.domain.value for f in self.findings})
            return (
                f"{len(self.findings)} matched rule"
                f"{'' if len(self.findings) == 1 else 's'} "
                f"across {', '.join(domains)}"
            )
        if not self.rulesets_consulted:
            return "No rulesets were loaded, so nothing was checked."
        return (
            f"No matches in the {len(self.rulesets_consulted)} ruleset"
            f"{'' if len(self.rulesets_consulted) == 1 else 's'} consulted"
        )

    def coverage_notes(self) -> tuple[str, ...]:
        """Per-ruleset coverage, for display beside `summary()`."""
        notes = [
            f"{ruleset.display_name} "
            f"({ruleset.jurisdiction.value}, rev. {ruleset.version}): "
            f"{ruleset.coverage.describe()}"
            + ("  [user-supplied]" if ruleset.user_supplied else "")
            for ruleset in self.rulesets_consulted
        ]
        if self.domains_without_rulesets:
            missing = ", ".join(d.value for d in self.domains_without_rulesets)
            notes.append(f"Not checked (no rulesets loaded): {missing}")
        return tuple(notes)
