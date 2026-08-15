"""Turn hand-written regulation sources into shippable rulesets.

    python tools/build_regulatory_rulesets.py [--check]

`sources/` is written and reviewed by people; `generated/` is written by
this script and must not be edited. The split exists so an accidental edit
to a machine-owned file is detectable rather than invisible, and every
generated file carries a DO NOT EDIT header plus its own SHA-256.

WHAT THIS ENFORCES, and the first one is the point of the whole script:

1. CONFIDENCE IS CAPPED BY THE VERBATIM QUOTE. A rule whose
   `legal.quote` is empty is forced to `requires_review`, whatever the
   source file claims. "I am confident about the chemistry" and "I have
   read the statute" are different claims, and only the second can be
   checked by someone else later. Filling in the quote is how a rule
   graduates -- there is no other route, deliberately.

2. NAMES ARE RESOLVED, NOT TRANSCRIBED. Where a source gives a chemical
   name, OPSIN turns it into a structure. Measured on regulation-style
   names: 7 of 7 systematic names resolved, 1 of 4 trivial ones. A name
   that will not resolve is recorded as UNRESOLVED and counted against
   coverage -- it never silently vanishes, and nobody types a structure
   from memory.

3. EVERY PREDICATE IS VALIDATED against `SUPPORTED_OPS` before shipping.
   A typo'd op at screening time means a regulation that silently matches
   nothing, which is the worst outcome this system has.

4. REVIEW DEBT FAILS THE BUILD past a threshold, so it cannot quietly
   become the shipped product.

Provenance is recorded so a ruleset can be REGENERATED years later rather
than merely dated: hashes of the source document and the output, plus the
generator, OPSIN and RDKit versions. RDKit's version matters concretely --
aromaticity perception and SMARTS semantics change between releases, so the
same rule against the same structure can change answer under a different
one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from openchem.chem.regulatory.predicates import SUPPORTED_OPS  # noqa: E402

GENERATOR = "build_regulatory_rulesets.py"
GENERATOR_VERSION = "1"

SOURCES = REPO / "src" / "openchem" / "chem" / "data" / "regulatory" / "sources"
GENERATED = REPO / "src" / "openchem" / "chem" / "data" / "regulatory" / "generated"

#: Above this share of rules needing review, the build fails. Not zero:
#: a ruleset under active transcription is a legitimate state, and a build
#: that refused it would push people to fake the quotes. High enough to
#: allow honest work in progress, low enough that a finished ruleset cannot
#: sit mostly unreviewed.
MAX_REVIEW_FRACTION = 0.75

#: Match types a rule may declare when it matches by InChIKey. Each NAMES A
#: SUBSTANCE, which is what a key can establish. `structural_family` and
#: `analogue` are absent deliberately: a family is a specification rather
#: than a list, and an analogue finding must carry a similarity, which
#: nothing produces yet.
IDENTIFYING_MATCH_TYPES = frozenset({"identity", "precursor", "metabolite"})

_DO_NOT_EDIT = (
    "GENERATED FILE -- DO NOT EDIT. Written by "
    f"{GENERATOR}; edit the matching file under sources/ and rebuild."
)


class BuildError(RuntimeError):
    """A source file that cannot be turned into a shippable ruleset."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj) -> str:
    """The one serialization every hash and comparison goes through.

    Sorted keys and no whitespace, so key order, indentation and line
    endings cannot produce a false difference. The file on disk is written
    with `indent=1` for review, which is why verifying it means reparsing
    and re-canonicalising rather than comparing bytes.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


#: Provenance that legitimately differs between two builds of the same
#: source, and so must come out before a rebuild is compared against the
#: committed artefact. `ruleset_sha256` is here because it is computed
#: over a document containing `generated_at`; it is verified separately
#: and on its own terms by `verify_stored_hash`.
NONDETERMINISTIC_PROVENANCE = frozenset({"generated_at", "ruleset_sha256"})


def _versions() -> dict[str, str]:
    import rdkit

    opsin = ""
    try:
        import py2opsin

        opsin = getattr(py2opsin, "__version__", "") or "present"
    except Exception:  # noqa: BLE001 - recorded as unknown, not fatal
        opsin = "unavailable"
    return {"rdkit_version": rdkit.__version__, "opsin_version": opsin}


def _validate_expression(expression, rule_id: str) -> None:
    """Reject an unknown op at BUILD time.

    Left to screening time the symptom is a regulation that matches
    nothing, which looks exactly like a structure being unregulated.
    """
    if isinstance(expression, str):
        return
    if not isinstance(expression, dict):
        raise BuildError(f"{rule_id}: expression must be a dict or SMARTS string")
    op = str(expression.get("op", "")).lower()
    if op not in SUPPORTED_OPS:
        raise BuildError(f"{rule_id}: unknown predicate op {op!r}")
    for child in expression.get("of", []) or []:
        _validate_expression(child, rule_id)


def _resolve_name(name: str) -> tuple[str, str]:
    """(inchikey, note) for a chemical name, via OPSIN.

    Returns an empty key rather than raising: an unresolved name is a
    coverage fact to be reported, not a build failure. Guessing the
    structure would be the one thing this script exists to prevent.
    """
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    from openchem.chem import naming_providers

    try:
        result = naming_providers.opsin_structure_for_name(name)
    except Exception as exc:  # noqa: BLE001
        return "", f"OPSIN could not parse: {type(exc).__name__}"
    smiles = getattr(result, "smiles", "") or ""
    if not smiles:
        return "", "OPSIN returned no structure"
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "", "OPSIN structure did not parse"
    return Chem.MolToInchiKey(mol) or "", ""


def build_one(source_path: Path) -> tuple[dict, list[str]]:
    """Build one ruleset. Returns (ruleset dict, human-readable notes)."""
    raw = source_path.read_text(encoding="utf-8")
    source = json.loads(raw)
    notes: list[str] = []

    rules_out = []
    unresolved: list[str] = []
    requires_review: list[str] = []
    manual_entries = 0

    for entry in source.get("rules", []):
        rule_id = entry.get("rule_id") or "<unnamed>"
        legal = dict(entry.get("legal", {}))
        quote = str(legal.get("quote", "")).strip()

        claimed = str(entry.get("confidence", "requires_review")).lower()
        # THE GATE. No verbatim text means the primary source was never
        # checked against this pattern, whatever the source file claims.
        if not quote:
            confidence = "requires_review"
            if claimed != "requires_review":
                notes.append(
                    f"  {rule_id}: claimed '{claimed}', forced to "
                    f"'requires_review' -- legal.quote is empty"
                )
        else:
            confidence = claimed
        if confidence == "requires_review":
            requires_review.append(rule_id)

        interpretation: dict = {
            "assumptions": entry.get("assumptions", []),
            "limitations": entry.get("limitations", []),
            "confidence": confidence,
            "interpreter_version": int(entry.get("interpreter_version", 1)),
        }

        expression = entry.get("expression")
        if expression:
            _validate_expression(expression, rule_id)
            interpretation["expression"] = expression

        # Identity entries: resolve names rather than carrying structures.
        keys: list[str] = []
        for name in entry.get("names", []) or []:
            key, why = _resolve_name(name)
            if key:
                keys.append(key)
            else:
                unresolved.append(f"{rule_id}: {name} ({why})")
        for key in entry.get("inchikeys", []) or []:
            # A hand-supplied key is a manual entry and is counted as one,
            # so the coverage report distinguishes derived from asserted.
            keys.append(key)
            manual_entries += 1
        if keys:
            interpretation["inchikeys"] = sorted(set(keys))

        if not expression and not keys:
            notes.append(f"  {rule_id}: no expression and no resolved identity -- skipped")
            unresolved.append(f"{rule_id}: nothing to match on")
            continue

        # A rule matched by InChIKey NAMES A SUBSTANCE, and the finding
        # carries whichever claim the rule declared. `structural_family`
        # is the loader's default for a rule that declares nothing, so
        # without this an identity rule that forgot to say so would report
        # every hit as a structural family -- a plausible-looking answer
        # about a family the regulation never defined.
        declared = str(entry.get("match_type", "")).strip().lower()
        if keys and declared not in IDENTIFYING_MATCH_TYPES:
            raise BuildError(
                f"{rule_id}: matches by identity (inchikeys/names) but declares "
                f"match_type {declared or '<none>'!r}. A listed substance must "
                f"declare one of {sorted(IDENTIFYING_MATCH_TYPES)} -- a family "
                f"cannot be expressed as a list of keys."
            )

        rules_out.append(
            {
                "rule_id": rule_id,
                "display_name": entry.get("display_name", rule_id),
                "domain": source["domain"],
                "jurisdiction": source["jurisdiction"],
                "match_type": entry.get("match_type", "structural_family"),
                "description": entry.get("description", ""),
                "legitimate_uses": entry.get("legitimate_uses", []),
                "synonyms": entry.get("synonyms", []),
                "legal": {
                    "authority": legal.get("authority", ""),
                    "instrument": legal.get("instrument", ""),
                    "section": legal.get("section", ""),
                    "quote": quote,
                    "citation_url": legal.get("citation_url", source.get("citation_url", "")),
                    "effective_date": legal.get(
                        "effective_date", source.get("effective_date", "")
                    ),
                    "cited_identifiers": legal.get("cited_identifiers", {}),
                },
                "interpretation": interpretation,
            }
        )

    total = len(source.get("rules", []))
    ruleset = {
        "_comment": _DO_NOT_EDIT,
        "ruleset_id": source["ruleset_id"],
        "display_name": source["display_name"],
        "domain": source["domain"],
        "jurisdiction": source["jurisdiction"],
        "version": source.get("version", "1"),
        "effective_date": source.get("effective_date", ""),
        "supersedes": source.get("supersedes", ""),
        "source_citation": source.get("source_citation", ""),
        "known_limitations": source.get("known_limitations", []),
        "rules": rules_out,
        "coverage": {
            "total_entries": total,
            "resolved": len(rules_out),
            "unresolved": unresolved,
            "requires_review": requires_review,
            "manual_entries": manual_entries,
        },
        "provenance": {
            "generator": GENERATOR,
            "generator_version": GENERATOR_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_document_sha256": _sha256(raw),
            **_versions(),
        },
    }
    # The output's own hash is computed over the ruleset WITHOUT it, so it
    # is reproducible: hashing a document that contains its own hash is not.
    ruleset["provenance"]["ruleset_sha256"] = _sha256(_canonical(ruleset))
    return ruleset, notes


def _without_nondeterministic(ruleset: dict) -> dict:
    """A copy comparable across builds of the same source."""
    trimmed = json.loads(_canonical(ruleset))
    provenance = trimmed.get("provenance")
    if isinstance(provenance, dict):
        for field in NONDETERMINISTIC_PROVENANCE:
            provenance.pop(field, None)
    return trimmed


def _first_difference(built, committed, path: str = "") -> str:
    """Where two rulesets first disagree, as a readable path.

    Naming the place matters more than it looks: a check that only says
    "these differ" teaches people to regenerate blindly, which is the
    habit that lets a hand edit through in the first place.
    """
    if type(built) is not type(committed):
        return f"{path or '<root>'}: {type(committed).__name__} -> {type(built).__name__}"
    if isinstance(built, dict):
        # Substance before bookkeeping. Editing a source ALWAYS moves
        # `source_document_sha256`, so walking in plain sorted order would
        # report that every time and never the rule that actually changed
        # -- a true first difference, and the least useful one available.
        def _priority(key: str) -> tuple[int, str]:
            return ({"rules": 0, "coverage": 1, "provenance": 3}.get(key, 2), key)

        for key in sorted(set(built) | set(committed), key=_priority):
            where = f"{path}.{key}" if path else key
            if key not in committed:
                return f"{where}: absent from the committed file"
            if key not in built:
                return f"{where}: in the committed file, not in the rebuild"
            found = _first_difference(built[key], committed[key], where)
            if found:
                return found
        return ""
    if isinstance(built, list):
        if len(built) != len(committed):
            return f"{path or '<root>'}: {len(committed)} entries -> {len(built)}"
        for index, (one, other) in enumerate(zip(built, committed)):
            # A rule is far easier to find by id than by position.
            label = one.get("rule_id") if isinstance(one, dict) else None
            where = f"{path}[{label or index}]"
            found = _first_difference(one, other, where)
            if found:
                return found
        return ""
    if built != committed:
        return f"{path or '<root>'}: {committed!r} -> {built!r}"
    return ""


def verify_stored_hash(committed: dict) -> str:
    """Does the committed file still hash to what it says it does?

    Catches a HAND EDIT. `_comment` promises the file is generated and
    nothing enforced that promise, so anyone could edit a shipped rule --
    a SMARTS pattern, a confidence, a quote -- and every test would pass
    against a ruleset no source produces.

    Returns "" when the file is intact, otherwise the reason.
    """
    provenance = committed.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("ruleset_sha256"):
        return "no ruleset_sha256 recorded, so the file cannot be verified"
    stated = provenance["ruleset_sha256"]
    stripped = json.loads(_canonical(committed))
    del stripped["provenance"]["ruleset_sha256"]
    actual = _sha256(_canonical(stripped))
    if actual != stated:
        return (
            f"content does not match its own recorded hash "
            f"(records {stated[:12]}..., hashes to {actual[:12]}...) -- "
            f"the file has been edited by hand"
        )
    return ""


def verify_matches_source(built: dict, committed: dict) -> str:
    """Is the committed file what this source currently builds?

    Catches a STALE artefact: a source edited without rebuilding ships the
    previous ruleset, and the hash check above cannot see it because the
    old file is perfectly self-consistent.

    Returns "" when they agree, otherwise where they first differ.
    """
    return _first_difference(
        _without_nondeterministic(built), _without_nondeterministic(committed)
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate and report without writing, for CI.",
    )
    args = parser.parse_args(argv)

    sources = sorted(SOURCES.glob("*.json"))
    if not sources:
        print(f"No sources under {SOURCES}")
        return 1

    GENERATED.mkdir(parents=True, exist_ok=True)
    failed = False

    for source_path in sources:
        try:
            ruleset, notes = build_one(source_path)
        except BuildError as exc:
            print(f"FAIL {source_path.name}: {exc}")
            failed = True
            continue

        coverage = ruleset["coverage"]
        total = coverage["total_entries"] or 1
        review_fraction = len(coverage["requires_review"]) / total

        print(f"\n{ruleset['ruleset_id']}  ({source_path.name})")
        print(f"  rules            {coverage['resolved']} of {total}")
        print(f"  requires review  {len(coverage['requires_review'])} "
              f"({review_fraction:.0%})")
        print(f"  unresolved       {len(coverage['unresolved'])}")
        print(f"  manual entries   {coverage['manual_entries']}")
        for note in notes:
            print(note)
        for item in coverage["unresolved"][:10]:
            print(f"  UNRESOLVED {item}")

        if review_fraction > MAX_REVIEW_FRACTION:
            print(
                f"  FAIL: {review_fraction:.0%} of rules need review, over the "
                f"{MAX_REVIEW_FRACTION:.0%} threshold. Review debt must not "
                f"become the shipped product -- add the verbatim quotes."
            )
            failed = True

        if args.check:
            # WITHOUT THIS, `--check` VALIDATED THE SOURCE AND NEVER LOOKED
            # AT WHAT SHIPS. A generated file that had been hand-edited, or
            # left behind by a source that moved on, passed CI untouched --
            # so the DO-NOT-EDIT header and the recorded hash were promises
            # with nothing enforcing either one.
            out = GENERATED / source_path.name
            if not out.is_file():
                print(f"  FAIL: {out.relative_to(REPO)} does not exist. Run without --check.")
                failed = True
            else:
                committed = json.loads(out.read_text(encoding="utf-8"))
                edited = verify_stored_hash(committed)
                if edited:
                    print(f"  FAIL: {out.relative_to(REPO)} {edited}")
                    failed = True
                stale = verify_matches_source(ruleset, committed)
                if stale:
                    print(
                        f"  FAIL: {out.relative_to(REPO)} is not what "
                        f"{source_path.name} builds -- first difference at {stale}. "
                        f"Rebuild it."
                    )
                    failed = True
                if not edited and not stale:
                    print("  artefact        matches its source, hash intact")

        if not args.check:
            out = GENERATED / source_path.name
            out.write_text(json.dumps(ruleset, indent=1) + "\n", encoding="utf-8")
            print(f"  -> {out.relative_to(REPO)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
