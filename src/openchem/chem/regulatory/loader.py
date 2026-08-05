"""Reading generated rulesets, and the user's own, off disk.

TWO SOURCES THAT ARE NEVER MERGED. Shipped rulesets are built from primary
regulation text by `tools/build_regulatory_rulesets.py` and reviewed;
user rulesets come from the data directory and may be anything -- a company
policy, a university teaching-lab restriction, a waste rule, or a newer
regulatory revision someone did not want to wait for. Both are useful and
they are different kinds of claim, so `Ruleset.user_supplied` marks the
second and every report keeps them apart. Collapsing them would destroy the
one property that makes the output trustworthy.

A ruleset that will not parse is SKIPPED WITH A WARNING rather than raising.
One malformed file in a user's directory must not take down screening for
every other ruleset -- but it must not vanish silently either, which is why
`load_all` reports what it could not read.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openchem import paths as app_paths
from openchem.chem.regulatory.types import (
    Domain,
    Jurisdiction,
    LegalSource,
    MachineInterpretation,
    MatchType,
    Rule,
    RuleConfidence,
    Ruleset,
    RulesetCoverage,
    RulesetProvenance,
)

logger = logging.getLogger("openchem.chemistry")

#: Where the built-in rulesets live, beside this package.
SHIPPED_ROOT = Path(__file__).resolve().parent.parent / "data" / "regulatory" / "generated"


def user_root() -> Path:
    """Where a user drops their own rulesets.

    Under the app's data directory rather than beside the installed code,
    so a reinstall does not delete an organisation's policies and a user
    without write access to the install can still add one.
    """
    return app_paths.subdirectory("regulatory_rulesets")


def load_all(include_user: bool = True) -> tuple[list[Ruleset], list[str]]:
    """Every readable ruleset, plus a note for each one that was not.

    Returns `(rulesets, problems)`. The problems are surfaced rather than
    logged and forgotten: a ruleset the user believes is loaded but is not
    is the same silence-as-reassurance failure this whole module is shaped
    against.
    """
    rulesets: list[Ruleset] = []
    problems: list[str] = []

    for path in sorted(SHIPPED_ROOT.glob("*.json")) if SHIPPED_ROOT.is_dir() else []:
        _load_into(path, rulesets, problems, user_supplied=False)

    if include_user:
        root = user_root()
        for path in sorted(root.glob("*.json")) if root.is_dir() else []:
            _load_into(path, rulesets, problems, user_supplied=True)

    return rulesets, problems


def _load_into(
    path: Path, rulesets: list[Ruleset], problems: list[str], user_supplied: bool
) -> None:
    try:
        rulesets.append(load_ruleset(path, user_supplied=user_supplied))
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the rest
        problems.append(f"{path.name}: {type(exc).__name__}: {exc}")
        logger.warning("Could not load ruleset %s: %s", path.name, exc)


def load_ruleset(path: Path, user_supplied: bool = False) -> Ruleset:
    """One ruleset from its JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ruleset_from_dict(data, user_supplied=user_supplied)


def ruleset_from_dict(data: dict, user_supplied: bool = False) -> Ruleset:
    rules = tuple(_rule_from_dict(entry) for entry in data.get("rules", []))
    coverage_raw = data.get("coverage", {})
    provenance_raw = data.get("provenance", {})
    return Ruleset(
        ruleset_id=data["ruleset_id"],
        display_name=data.get("display_name", data["ruleset_id"]),
        domain=Domain(data["domain"]),
        jurisdiction=Jurisdiction(data["jurisdiction"]),
        version=str(data.get("version", "1")),
        effective_date=data.get("effective_date", ""),
        supersedes=data.get("supersedes", ""),
        source_citation=data.get("source_citation", ""),
        rules=rules,
        coverage=RulesetCoverage(
            total_entries=int(coverage_raw.get("total_entries", len(rules))),
            resolved=int(coverage_raw.get("resolved", len(rules))),
            unresolved=tuple(coverage_raw.get("unresolved", [])),
            requires_review=tuple(coverage_raw.get("requires_review", [])),
            manual_entries=int(coverage_raw.get("manual_entries", 0)),
        ),
        provenance=RulesetProvenance(
            generator=provenance_raw.get("generator", ""),
            generator_version=str(provenance_raw.get("generator_version", "")),
            generated_at=provenance_raw.get("generated_at", ""),
            source_document_sha256=provenance_raw.get("source_document_sha256", ""),
            ruleset_sha256=provenance_raw.get("ruleset_sha256", ""),
            opsin_version=provenance_raw.get("opsin_version", ""),
            rdkit_version=provenance_raw.get("rdkit_version", ""),
        ),
        known_limitations=tuple(data.get("known_limitations", [])),
        user_supplied=user_supplied,
    )


def _rule_from_dict(entry: dict) -> Rule:
    legal_raw = entry.get("legal", {})
    interpretation_raw = entry.get("interpretation", {})
    return Rule(
        rule_id=entry["rule_id"],
        display_name=entry.get("display_name", entry["rule_id"]),
        domain=Domain(entry["domain"]),
        jurisdiction=Jurisdiction(entry["jurisdiction"]),
        match_type=MatchType(entry.get("match_type", "structural_family")),
        description=entry.get("description", ""),
        legitimate_uses=tuple(entry.get("legitimate_uses", [])),
        synonyms=tuple(entry.get("synonyms", [])),
        legal=LegalSource(
            authority=legal_raw.get("authority", ""),
            instrument=legal_raw.get("instrument", ""),
            section=legal_raw.get("section", ""),
            quote=legal_raw.get("quote", ""),
            citation_url=legal_raw.get("citation_url", ""),
            effective_date=legal_raw.get("effective_date", ""),
            cited_identifiers=dict(legal_raw.get("cited_identifiers", {})),
        ),
        interpretation=MachineInterpretation(
            expression=interpretation_raw.get("expression", ""),
            inchikeys=tuple(interpretation_raw.get("inchikeys", [])),
            assumptions=tuple(interpretation_raw.get("assumptions", [])),
            limitations=tuple(interpretation_raw.get("limitations", [])),
            confidence=RuleConfidence(
                interpretation_raw.get("confidence", "requires_review")
            ),
            interpreter_version=int(interpretation_raw.get("interpreter_version", 1)),
        ),
    )
