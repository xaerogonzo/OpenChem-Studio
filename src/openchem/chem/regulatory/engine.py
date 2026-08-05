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
"""

from __future__ import annotations

import logging

from rdkit import Chem
from rdkit.Chem.SaltRemover import SaltRemover

from openchem.chem.regulatory.predicates import PredicateError, evaluate
from openchem.chem.regulatory.types import (
    Domain,
    Finding,
    Jurisdiction,
    JurisdictionConflict,
    MatchType,
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
    ) -> ScreeningReport:
        """Screen `mol` against every loaded ruleset.

        `jurisdictions` filters to the places that apply to the person
        asking; the default is everything, because a user who has not said
        where they are should see more rather than less.
        """
        if mol is None:
            return ScreeningReport(rulesets_consulted=tuple(self._rulesets))

        normalised = self._normalise(mol)
        findings: list[Finding] = []
        near_misses: list[NearMiss] = []

        for ruleset in self._rulesets:
            if jurisdictions and ruleset.jurisdiction not in jurisdictions:
                continue
            for rule in ruleset.rules:
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
        """Identity, with the salts-and-isomers policy applied."""
        listed = set(rule.interpretation.inchikeys)
        key = _inchikey(normalised)
        if not key:
            return None

        if key in listed:
            return Finding(
                rule=rule,
                match_type=MatchType.IDENTITY,
                atoms=frozenset(range(mol.GetNumAtoms())),
                outcomes=(
                    PredicateOutcome(
                        label="exact identity (salt-normalised)", passed=True
                    ),
                ),
            )

        # "and its isomers": same connectivity, different stereochemistry.
        # Reported as its own outcome rather than silently as an exact hit,
        # because enantiomers can differ enormously in effect.
        skeleton = key[:_SKELETON_BLOCK]
        if any(candidate[:_SKELETON_BLOCK] == skeleton for candidate in listed):
            return Finding(
                rule=rule,
                match_type=MatchType.IDENTITY,
                atoms=frozenset(range(mol.GetNumAtoms())),
                outcomes=(
                    PredicateOutcome(
                        label="same connectivity, different stereochemistry",
                        passed=True,
                        detail=(
                            "matched under the regulation's 'and its isomers' "
                            "wording, not as an exact identity"
                        ),
                    ),
                ),
            )
        return None

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
