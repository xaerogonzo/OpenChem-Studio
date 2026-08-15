"""Screening a structure against loaded rulesets.

WHAT THIS RETURNS IS A REPORT, NOT A VERDICT. `ScreeningReport` carries
what matched, what nearly matched, where jurisdictions disagree, which
rulesets ran and how complete they are. It never concludes. The reason is
in `types.py`: the dangerous failure of a screening tool is silence read as
reassurance, and the only defence is to state the scope of what was checked
in the same breath as the result.

SALTS AND ISOMERS ARE A STATED POLICY, NOT AN ACCIDENT. DEA language is
"including its salts, isomers, and salts of isomers", and the EU precursor
regulations use similar wording, so an identity rule cannot be a plain
InChIKey comparison:

  * Salts are stripped before comparison, so ephedrine hydrochloride
    matches a rule written for ephedrine. Without this, every rule would
    need a hand-written entry per counter-ion.
  * Isomers are matched on the InChIKey's FIRST BLOCK, which encodes
    connectivity while the second encodes stereochemistry and isotopes.
    That is how "and its isomers" is expressed structurally.
  * A stereo-insensitive hit is REPORTED SEPARATELY from an exact one, via
    the outcome list, because they are different claims. Enantiomers can
    differ enormously in effect, and a tool that silently equated them
    would be wrong in the direction that matters.

Getting this wrong in either direction is a real error: too strict misses a
hydrochloride, too loose flags an unrelated stereoisomer as the scheduled
substance.

DATES ARE A FILTER ON WHICH RULES RUN, NOT A CLAIM ABOUT HISTORY.
`screen(as_of=...)` withholds rules taking effect after that calendar date,
inclusively at the start, with no time of day and no timezone -- so the same
question gets the same answer either side of a date line. Three properties
hold it together, and each has a way of going quietly wrong:

  * An UNDATED rule is not date-filtered, which is narrower than "applies at
    every date" and deliberately so. 47 of the 91 shipped rules are undated,
    so the opposite default would empty a majority of the file while looking
    exactly like a substance that is not listed.
  * A withheld rule produces no NEAR MISS either, which is why the skip is
    in `screen()`'s loop rather than in `_apply`. A near miss names a rule
    and says which of its features you have; reporting one for a rule that
    did not yet exist would disclose future law while claiming to describe
    the past.
  * A rule's own date beats its ruleset's. The CWC is the case: a 1997
    ruleset carrying four rules dated 2020.

What this CANNOT say is when a rule stopped applying -- nothing records
repeal or expiry -- so a dated screen answers when a rule STARTED and would
report one since removed as though it still applied.
"""

from __future__ import annotations

import logging
from datetime import date

from rdkit import Chem
from rdkit.Chem.SaltRemover import SaltRemover

from openchem.chem.regulatory.predicates import PredicateError, evaluate
from openchem.chem.regulatory.types import (
    Domain,
    Finding,
    Jurisdiction,
    JurisdictionConflict,
    MalformedDate,
    NearMiss,
    PredicateOutcome,
    Rule,
    Ruleset,
    ScreeningReport,
)

logger = logging.getLogger("openchem.chemistry")

#: How many failed conditions a rule may have and still be reported as a
#: near miss. Two, because one failure is the interesting case ("you are a
#: single feature away from a scheduled family") and beyond two the report
#: fills with structures that merely share a functional group.
NEAR_MISS_MAX_DISTANCE = 2

#: The number of leading InChIKey characters that encode CONNECTIVITY. The
#: remainder encodes stereochemistry, isotopes and charge, which is exactly
#: the split "and its isomers" needs.
_SKELETON_BLOCK = 14


class EffectiveDateError(ValueError):
    """A stored effective date that is neither absent nor a valid ISO date."""

    def __init__(self, value: str) -> None:
        super().__init__(f"{value!r} is not an ISO date (YYYY-MM-DD)")
        self.value = value


def parse_effective_date(value: str) -> date | None:
    """The one date grammar, shared by the build and by screening.

    THREE STATES, AND THEY MUST NOT COLLAPSE INTO TWO. Absence is a VALUE
    (`None`, meaning the source records no date); malformation is an
    EXCEPTION. That split is what lets one function serve both callers
    without either reimplementing it: `tools/build_regulatory_rulesets.py`
    lets the exception become a `BuildError` so shipped data cannot carry
    one, while `screen()` catches it, records it and treats the rule as
    undated so one bad entry in somebody's own file does not take down the
    whole screen.

    A `date`, never a `datetime`. These are calendar dates, so there is no
    time of day and no timezone conversion -- otherwise the same question
    would get different answers either side of a date line.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise EffectiveDateError(text) from exc


def resolve_effective_date(rule: Rule, ruleset: Ruleset) -> date | None:
    """When `rule` took effect: its own date, else its ruleset's, else None.

    A RULE'S OWN DATE BEATS ITS RULESET'S, and the CWC is the case that
    makes this concrete: the Schedule 1 ruleset is dated 1997-04-29 and
    carries four rules dated 2020-06-07. Falling back the other way, or not
    at all, would report the 2019 additions as having existed since the
    treaty entered force.

    THE FALLBACK LOOKS REDUNDANT AGAINST SHIPPED DATA AND IS NOT.
    `build_regulatory_rulesets.py` already writes the ruleset's date onto
    every rule that does not declare one, so for a shipped ruleset both
    halves agree and deleting this one would change nothing measurable.
    `loader.py` does no such thing, so a USER ruleset that dates itself and
    not its rules is the only place this branch is reachable -- which is
    why its guard has to be a synthetic fixture and says so.

    Raises `EffectiveDateError` if the date it settles on cannot be read.
    """
    own = parse_effective_date(rule.legal.effective_date)
    if own is not None:
        return own
    return parse_effective_date(ruleset.effective_date)


def _applies_at(effective: date | None, as_of: date | None) -> bool:
    """The whole comparison, in one place so there is one of it.

    Inclusive at the start: a rule applies ON the day it takes effect.
    An undated rule is NOT DATE-FILTERED -- which is a narrower statement
    than "applies at every date", and the narrower one is the true one.
    The opposite default would be a screen that silently matches nothing,
    which looks exactly like a substance that is not listed.
    """
    return as_of is None or effective is None or effective <= as_of


def rule_applies_at(rule: Rule, ruleset: Ruleset, as_of: date | None) -> bool:
    """Whether `rule` should be evaluated for a screen dated `as_of`.

    Named for what the engine KNOWS, which is an inclusive start date and
    nothing else. Not `is_in_force`: no ruleset records repeal or expiry,
    so a rule struck from a schedule still reports here, and a name
    implying otherwise would have to be walked back the day end dates
    exist.

    A date this cannot read is treated as absent, matching the tolerance
    `screen()` applies; `screen()` additionally REPORTS it, which a bare
    predicate has nowhere to put.
    """
    try:
        effective = resolve_effective_date(rule, ruleset)
    except EffectiveDateError:
        effective = None
    return _applies_at(effective, as_of)


class RegulatoryEngine:
    """Holds rulesets and screens structures against them.

    Domains are registered even when they have no rulesets, so the report
    can distinguish "checked, nothing matched" from "never checked". An
    absent domain is invisible and reads as the former.
    """

    def __init__(self, rulesets: list[Ruleset] | None = None) -> None:
        self._rulesets: list[Ruleset] = list(rulesets or [])
        self._salt_remover = SaltRemover()

    # -- registry --------------------------------------------------------

    def add_ruleset(self, ruleset: Ruleset) -> None:
        """Add a ruleset, newest effective date winning for the same id.

        `supersedes` is honoured so dropping in a revision retires the one
        it replaces without deleting a file -- which keeps the superseded
        version available as the record of what was true before.
        """
        superseded = {r.supersedes for r in [*self._rulesets, ruleset] if r.supersedes}
        self._rulesets = [
            existing
            for existing in self._rulesets
            if existing.ruleset_id != ruleset.ruleset_id
            and existing.ruleset_id not in superseded
        ]
        if ruleset.ruleset_id not in superseded:
            self._rulesets.append(ruleset)

    @property
    def rulesets(self) -> tuple[Ruleset, ...]:
        return tuple(self._rulesets)

    def domains_with_rulesets(self) -> set[Domain]:
        return {ruleset.domain for ruleset in self._rulesets}

    def empty_domains(self) -> tuple[Domain, ...]:
        """Registered domains with nothing loaded.

        Reported so an unchecked domain reads as unchecked. This is the
        single most likely way for this tool to mislead: a user seeing no
        food-additive findings should learn that no food-additive ruleset
        was loaded, not infer that none applied.
        """
        loaded = self.domains_with_rulesets()
        return tuple(domain for domain in Domain if domain not in loaded)

    # -- screening -------------------------------------------------------

    def screen(
        self,
        mol: Chem.Mol,
        jurisdictions: set[Jurisdiction] | None = None,
        include_near_misses: bool = True,
        as_of: date | None = None,
    ) -> ScreeningReport:
        """Screen `mol` against every loaded ruleset.

        `jurisdictions` filters to the places that apply to the person
        asking; the default is everything, because a user who has not said
        where they are should see more rather than less.

        `as_of` answers "was this listed when the sample was made" by
        withholding rules that take effect after that date. Three things
        about it are deliberate:

        * **The default is None, not today.** Every shipped rule is dated
          in the past, so `date.today()` would give identical answers on
          all shipped data and diverge only on a rule dated in the future
          -- a difference no corpus here could see. None means no date
          filtering at all, and an undated screen is byte-identical to
          what this returned before the parameter existed.
        * **A withheld rule produces no NEAR MISS either**, which is why
          the skip is here rather than inside `_apply`. A near miss naming
          a rule that did not yet exist would leak future law while
          claiming to report the past -- and near misses are the part of
          this screen a legitimate user gets the most from.
        * **What was withheld is reported, not merely omitted.** A screen
          that quietly drops half its rules and still says "no matches in
          the 4 rulesets consulted" is the silence-read-as-reassurance
          this whole module is written against.
        """
        if mol is None:
            return ScreeningReport(
                rulesets_consulted=tuple(self._rulesets), as_of=as_of
            )

        normalised = self._normalise(mol)
        findings: list[Finding] = []
        near_misses: list[NearMiss] = []
        withheld: list[tuple[str, str]] = []
        malformed: list[MalformedDate] = []

        for ruleset in self._rulesets:
            if jurisdictions and ruleset.jurisdiction not in jurisdictions:
                continue
            for rule in ruleset.rules:
                try:
                    effective = resolve_effective_date(rule, ruleset)
                except EffectiveDateError as exc:
                    # Tolerated and RECORDED, the same way an unevaluable
                    # predicate is. Shipped rulesets cannot reach here (the
                    # build refuses a bad date), so this is a user's own
                    # file, where one broken entry must not cost them every
                    # other rule -- but must not pass as timeless either.
                    logger.warning(
                        "Rule %s has an unreadable effective date %r; "
                        "screening it as undated",
                        rule.rule_id,
                        exc.value,
                    )
                    malformed.append(
                        MalformedDate(ruleset.ruleset_id, rule.rule_id, exc.value)
                    )
                    effective = None
                if not _applies_at(effective, as_of):
                    withheld.append((ruleset.ruleset_id, rule.rule_id))
                    continue

                finding, near_miss = self._apply(rule, mol, normalised)
                if finding is not None:
                    findings.append(finding)
                elif near_miss is not None and include_near_misses:
                    near_misses.append(near_miss)

        consulted = tuple(
            ruleset
            for ruleset in self._rulesets
            if not jurisdictions or ruleset.jurisdiction in jurisdictions
        )
        return ScreeningReport(
            findings=tuple(findings),
            near_misses=tuple(sorted(near_misses, key=lambda n: n.distance)),
            conflicts=self._conflicts(findings, consulted),
            rulesets_consulted=consulted,
            domains_without_rulesets=self.empty_domains(),
            as_of=as_of,
            rules_withheld_by_date=tuple(withheld),
            malformed_effective_dates=tuple(malformed),
        )

    # -- one rule --------------------------------------------------------

    def _apply(
        self, rule: Rule, mol: Chem.Mol, normalised: Chem.Mol
    ) -> tuple[Finding | None, NearMiss | None]:
        interpretation = rule.interpretation
        if interpretation.inchikeys:
            return (self._apply_identity(rule, mol, normalised), None)
        if not interpretation.expression:
            return (None, None)
        try:
            passed, outcomes = evaluate(interpretation.expression, mol)
        except PredicateError:
            # A malformed rule is a build-time fault, and the build
            # validates against SUPPORTED_OPS. Reaching here at screening
            # time means a user ruleset -- log it and skip, rather than
            # failing a screen over one bad entry in someone's own file.
            logger.warning("Skipping unevaluable rule %s", rule.rule_id)
            return (None, None)

        atoms = frozenset(i for outcome in outcomes for i in outcome.atoms)
        if passed:
            return (
                Finding(
                    rule=rule,
                    match_type=rule.match_type,
                    atoms=atoms,
                    outcomes=tuple(outcomes),
                ),
                None,
            )

        failed = sum(1 for outcome in outcomes if not outcome.passed)
        if 0 < failed <= NEAR_MISS_MAX_DISTANCE and _structurally_near(outcomes):
            return (None, NearMiss(rule=rule, distance=failed, outcomes=tuple(outcomes)))
        return (None, None)

    def _apply_identity(
        self, rule: Rule, mol: Chem.Mol, normalised: Chem.Mol
    ) -> Finding | None:
        """Identity, with the salts-and-isomers policy applied.

        THE FINDING CARRIES THE RULE'S DECLARED MATCH TYPE, not a hardcoded
        `IDENTITY`. Those are two different statements and this method used
        to collapse them: HOW the structure was matched (by salt-normalised
        key, which is what the outcomes below say) is not WHAT the
        regulation claims about it. A listed precursor is matched by
        identity and is still a precursor -- and with `IDENTITY` forced
        here, such a rule reported "identity" on its finding line while
        `_finding_lines` printed its legitimate uses from the rule a line
        later, contradicting itself.

        Invisible until a shipped ruleset carried an `inchikeys` entry,
        because the structural path a few lines up always used
        `rule.match_type` correctly.
        """
        listed = set(rule.interpretation.inchikeys)
        key = _inchikey(normalised)
        if not key:
            return None

        outcome: PredicateOutcome | None = None
        if key in listed:
            outcome = PredicateOutcome(
                label="exact identity (salt-normalised)", passed=True
            )
        else:
            # "and its isomers": same connectivity, different stereochemistry.
            # Reported as its own outcome rather than silently as an exact
            # hit, because enantiomers can differ enormously in effect.
            skeleton = key[:_SKELETON_BLOCK]
            if any(candidate[:_SKELETON_BLOCK] == skeleton for candidate in listed):
                outcome = PredicateOutcome(
                    label="same connectivity, different stereochemistry",
                    passed=True,
                    detail=(
                        "matched under the regulation's 'and its isomers' "
                        "wording, not as an exact identity"
                    ),
                )
        if outcome is None:
            return None

        return Finding(
            rule=rule,
            match_type=rule.match_type,
            atoms=frozenset(range(mol.GetNumAtoms())),
            outcomes=(outcome,),
        )

    # -- helpers ---------------------------------------------------------

    def _normalise(self, mol: Chem.Mol) -> Chem.Mol:
        """Strip counter-ions so a salt matches a rule written for the base.

        Best-effort: a structure the salt remover cannot handle is compared
        as drawn rather than dropped, since a missed strip costs a match
        and an exception costs the whole screen.
        """
        try:
            stripped = self._salt_remover.StripMol(mol, dontRemoveEverything=True)
            return stripped if stripped is not None and stripped.GetNumAtoms() else mol
        except Exception:  # noqa: BLE001 - screening must not fail on a salt
            return mol

    def _conflicts(
        self, findings: list[Finding], consulted: tuple[Ruleset, ...]
    ) -> tuple[JurisdictionConflict, ...]:
        """Where one jurisdiction matched and another did not.

        Reported, never resolved. Which one governs depends on where
        someone is and what they are doing, and picking for them would be a
        legal determination this software is in no position to make.

        Only jurisdictions that were actually CONSULTED can appear on
        either side -- "no match in Japan" is meaningless when no Japanese
        ruleset was loaded, and would be the same silence-as-reassurance
        error this whole module is shaped against.
        """
        consulted_jurisdictions = {ruleset.jurisdiction for ruleset in consulted}
        matched = {finding.rule.jurisdiction for finding in findings}
        if not matched:
            return ()
        silent = consulted_jurisdictions - matched
        if not silent:
            return ()
        return (
            JurisdictionConflict(
                structure_note=(
                    "matched in some consulted jurisdictions and not others"
                ),
                matched_in=tuple(sorted(matched, key=lambda j: j.value)),
                no_match_in=tuple(sorted(silent, key=lambda j: j.value)),
            ),
        )


def _structurally_near(outcomes: list[PredicateOutcome]) -> bool:
    """Whether a partial match reflects shared STRUCTURE.

    A numeric bound can pass vacuously -- ethanol satisfies "10 carbons or
    fewer" -- so counting failures alone reported ethanol as one predicate
    away from a nerve-agent schedule. Nonsense, and the kind of nonsense
    that trains a user to ignore the near-miss column entirely.

    Only predicates that MATCHED ATOMS count as evidence of nearness:
    `contains` reports the atoms it hit, while `element_count` and `mw`
    report none. So at least one real substructure must have been found.

    THIS IS ALSO WHY RULES ARE AUTHORED AS FEATURE CHECKLISTS rather than
    one monolithic SMARTS. Decomposed into "P=O", "P-F", "P-O-alkyl" and
    "P-C", diisopropyl fluorophosphate matches the first three and fails
    only the P-C bond -- which is the true and useful statement. Written as
    a single pattern it is simply "no match", and the reader learns
    nothing about where the boundary runs.
    """
    return any(outcome.passed and outcome.atoms for outcome in outcomes)


def _inchikey(mol: Chem.Mol) -> str:
    try:
        return Chem.MolToInchiKey(mol) or ""
    except Exception:  # noqa: BLE001
        return ""
