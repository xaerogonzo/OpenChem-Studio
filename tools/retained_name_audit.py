"""What the retained-name registry claims, and what it can support.

**A TABLE NAMED `retained_pins` IS A CLAIM ABOUT 292 NAMES.** Measured
2026-09-17, its provenance does not back that claim up:

    opsin          161   harvested from OPSIN's name->structure dictionary
    algorithm.py    72   no rule cited
    opsin_data      22   same provenance problem
    retained         6   unexplained
    bluebook        16   cited
    opsin+bluebook   7   cited
    iupac_p34/64/65/66  4   cited
    manual           2   cited

31 entries cite a rule and 261 carry `rule: "various"`, and source and rule
agree on every row. Being in OPSIN's dictionary establishes that a name can be
READ, which is a different fact from IUPAC preferring it -- the same shape as
the triazole entry recorded in `KNOWN_LIMITATIONS.md`, where a test written
from the table agreed with the table.

**AND A CITATION IS NOT AUTOMATICALLY EVIDENCE.** `caffeine` cites
`P-31.1.3`, which is about indicated hydrogen and says nothing about
retaining `caffeine`; 14 of the 31 cited rows are L-amino acids, which are
genuinely retained (P-103). So the cited rows were checked against what the
citation actually establishes rather than counted.

## What this tool reports, and what it does not do

It reports the audit's coverage: how many entries carry a `pin_status`, how
many of those are reachable by the benchmark corpora, and which entries a
corpus name currently depends on while having no audited status. It changes
nothing.

`UNKNOWN` is treated as usable by the engine, deliberately, EXCEPT where the
name came from OPSIN's parse dictionary. Refusing every unaudited entry on no
evidence is the mirror image of the original defect -- the answer to
"asserted without evidence" is not "denied without evidence". This report
exists so that backlog stays visible instead of looking like a decision.

**THE USABLE BACKLOG IS AUDITED (naming round 5, N9; Alex's decision of
2026-09-19).** Every entry the gate lets through now carries a typed status
with a quoted rule: of the 75 that were usable and untyped, 33 are PIN, 6 are
demoted because the book prints another name as the PIN, and 36 are demoted
because the book never prints the name at all. Three entries were REMOVED:
they bound an amino-acid name to the wrong stereoisomer (D-proline as
"L-proline", L-allothreonine, L-alloisoleucine), which nothing was checking
until the audit found each name under a second SMILES. Two tests in
`tests/test_retained_registry_contract.py` now check the pair -- one parses
every name with OPSIN and compares structures, the other forbids one name
under two structures. What remains unaudited is the 171-entry unreached
backlog whose source is OPSIN's dictionary (the gate refuses those) and the
OPSIN RING vocabulary, which Alex left ungated.

**THE OPSIN GATE (naming round 5, N5).** A name whose record came from OPSIN
-- the 1,824-name vocabulary file, or a registry entry whose `source` says it
was copied from there -- is emitted only when the registry types it with
NORMATIVE_RULE evidence. "fluorouracil" and "tabun" reached the output as
whole-molecule names on nothing but a parser's ability to read them. The rule
itself is `engine.retained_gate_refusal`; `--gate` prints how it partitions
both tables, by calling that function rather than restating it.

    python tools/retained_name_audit.py
    python tools/retained_name_audit.py --gate        # the gate's partitions
    python tools/retained_name_audit.py --reachable   # engine consulted

`--reachable` runs the three TUNING populations (regression, v1, v2). The
fresh held-out population is excluded by design: nothing about it may inform
a gate or an audit decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src/openchem/vendor/data/retained_names_expanded.json"
BENCH = ROOT / "benchmarks" / "naming"

sys.path.insert(0, str(ROOT / "src"))


def registry() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))["retained_pins"]


PIN_STATUSES = {"PIN", "RETAINED_NOT_PIN"}
EVIDENCE_KINDS = {"NORMATIVE_RULE", "ABSENT_FROM_SOURCE", "STRUCTURE_PARSE_ONLY"}
SCOPES = {"full", "ring_only", "limited", "none"}


def validate(entries: dict) -> list[str]:
    """Every impossible combination in the registry, as one message each.

    FAILS CLOSED. The registry's fields are CLAIMS the generator acts on, so
    an entry the audit cannot vouch for must not be able to assert anything:

      * a PIN, or a name allowed to act as a PARENT, needs NORMATIVE evidence
        -- "OPSIN can parse it" establishes that a name can be read, and that
        is exactly the confusion `retained_pins` was built on;
      * ABSENT_FROM_SOURCE can only ever support a demotion;
      * a whole-molecule-only name cannot also be a substitutable parent.

    An entry with no `pin_status` is UNKNOWN and asserts nothing, which is
    allowed: 274 of them are the declared backlog, not an error.
    """
    errors: list[str] = []
    for smiles, e in entries.items():
        name = e.get("name", smiles)
        status = e.get("pin_status")
        kind = e.get("evidence_kind")
        if status is not None and status not in PIN_STATUSES:
            errors.append(f"{name}: unknown pin_status {status!r}")
        if kind is not None and kind not in EVIDENCE_KINDS:
            errors.append(f"{name}: unknown evidence_kind {kind!r}")
        if (status == "PIN" or e.get("may_be_parent")) and kind != "NORMATIVE_RULE":
            errors.append(f"{name}: a PIN or a parent needs NORMATIVE_RULE evidence, has {kind!r}")
        if kind == "NORMATIVE_RULE" and not (e.get("rule_id") and e.get("evidence_source")):
            errors.append(f"{name}: NORMATIVE_RULE without rule_id and evidence_source")
        if kind == "ABSENT_FROM_SOURCE" and status != "RETAINED_NOT_PIN":
            errors.append(f"{name}: ABSENT_FROM_SOURCE can only support a demotion")
        if e.get("may_be_substituted") and not e.get("may_be_parent"):
            errors.append(f"{name}: substitutable but not a parent")
        scope = e.get("substitution_scope")
        if scope is not None and scope not in SCOPES:
            errors.append(f"{name}: unknown substitution_scope {scope!r}")
        if e.get("whole_molecule_only") and (e.get("may_be_parent") or scope not in (None, "none")):
            errors.append(f"{name}: whole-molecule-only yet usable as a substituted parent")
    return errors


def partitions(entries: dict) -> dict[str, Counter]:
    """Machine-derived counts, each of which must sum to the total."""
    return {
        "pin_status": Counter(e.get("pin_status", "UNKNOWN") for e in entries.values()),
        "evidence_kind": Counter(e.get("evidence_kind", "NONE") for e in entries.values()),
        "may_be_parent": Counter(bool(e.get("may_be_parent")) for e in entries.values()),
    }


TUNING_POPULATIONS = (
    ("regression", "corpus.json"),
    ("v1", "heldout.json"),
    ("v2", "heldout2.json"),
)


def gate_partitions() -> dict[str, Counter]:
    """How the OPSIN gate splits the registry and the OPSIN vocabulary file.

    Calls the engine's own `retained_gate_refusal`, so this report cannot
    drift from the rule it describes. Each partition sums to its table.
    """
    from openchem.vendor.iupac_namer.data_loader import (
        OPSIN_VOCABULARY_TABLE,
        get_retained_names_from_opsin,
    )
    from openchem.vendor.iupac_namer.engine import (
        _is_valid_retained_name_for_standalone,
        retained_gate_refusal,
    )
    from openchem.vendor.iupac_namer.strategy import default_strategy

    strategy = default_strategy()
    registry_counts: Counter = Counter()
    for smiles, entry in registry().items():
        record = {"smiles": smiles, **entry, "table": "retained_pins"}
        registry_counts[retained_gate_refusal(record, strategy) or "usable"] += 1
    vocabulary_counts: Counter = Counter()
    for entry in get_retained_names_from_opsin():
        record = {**entry, "table": OPSIN_VOCABULARY_TABLE}
        if not _is_valid_retained_name_for_standalone(record):
            vocabulary_counts["never standalone (a stem or fragment)"] += 1
        else:
            vocabulary_counts[retained_gate_refusal(record, strategy) or "usable"] += 1
    return {"registry": registry_counts, "opsin_vocabulary": vocabulary_counts}


def _reachable() -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    """(winners, refusals) over the tuning populations.

    winners:  retained name -> row labels whose naming it won, at any level
              (a whole molecule, a substituent, an acid stem, ...);
    refusals: (name, refusal code) -> row labels where the gate stopped a
              record that would otherwise have been eligible.

    Imports the engine, so it is behind a flag: the rest of this report is a
    statement about the DATA and should not depend on the code. A name cached
    by an earlier row is not looked up again, so these are lower bounds.
    """
    from openchem.vendor.iupac_namer import engine as eng
    from openchem.vendor.iupac_namer import name_smiles
    from openchem.vendor.iupac_namer.types import RetainedPlan

    winners: dict[str, set[str]] = {}
    refusals: dict[tuple[str, str], set[str]] = {}
    original_search = eng._search_plans
    original_gate = eng.retained_gate_refusal
    for population, filename in TUNING_POPULATIONS:
        path = BENCH / filename
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            label = f"{population}:{row['label']}"

            def search(*args, _label=label):
                ranked = original_search(*args)
                if ranked and isinstance(ranked[-1][2], RetainedPlan):
                    winners.setdefault(ranked[-1][2].match.name, set()).add(_label)
                return ranked

            def gate(match, strategy, _label=label):
                code = original_gate(match, strategy)
                if code is not None and eng._is_valid_retained_name_for_standalone(match):
                    refusals.setdefault((match.get("name", ""), code), set()).add(_label)
                return code

            eng._search_plans = search
            eng.retained_gate_refusal = gate
            try:
                name_smiles(row["smiles"])
            except Exception:  # noqa: BLE001
                pass
            finally:
                eng._search_plans = original_search
                eng.retained_gate_refusal = original_gate
    return winners, refusals


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the retained-name registry.")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="also report how the OPSIN gate partitions both tables (imports the engine)",
    )
    parser.add_argument(
        "--reachable",
        action="store_true",
        help="also report which entries a benchmark name depends on (imports the engine)",
    )
    args = parser.parse_args()

    entries = registry()
    errors = validate(entries)
    for field, counts in partitions(entries).items():
        if sum(counts.values()) != len(entries):
            errors.append(f"partition {field} sums to {sum(counts.values())}, not {len(entries)}")
    statuses = Counter(e.get("pin_status", "UNKNOWN") for e in entries.values())
    sources = Counter(e.get("source", "?") for e in entries.values())
    cited = sum(
        1
        for e in entries.values()
        if str(e.get("rule", "")).strip().lower() not in ("various", "", "none")
    )

    print(f"{len(entries)} entries in the retained-name registry")
    print(f"  {cited} cite a rule, {len(entries) - cited} carry rule='various'")
    print()
    print("  pin_status:")
    for status, count in sorted(statuses.items()):
        print(f"    {status:20s} {count}")
    print()
    print("  source:")
    for source, count in sources.most_common():
        print(f"    {str(source):20s} {count}")

    audited = {
        e.get("name"): e for e in entries.values() if e.get("pin_status")
    }
    if audited:
        print()
        print(f"  audited ({len(audited)}):")
        for name, entry in sorted(audited.items()):
            print(f"    {entry['pin_status']:18s} {name}")

    print()
    for field, counts in partitions(entries).items():
        print(f"  {field}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=str)))
    if errors:
        print()
        print(f"  {len(errors)} VALIDATION ERROR(S):")
        for error in errors:
            print(f"    {error}")
        raise SystemExit(1)

    if args.gate:
        print()
        for table, counts in gate_partitions().items():
            total = sum(counts.values())
            print(f"  gate over {table} ({total}):")
            for outcome, count in sorted(counts.items()):
                print(f"    {outcome:40s} {count}")

    if not args.reachable:
        print()
        print("  (pass --gate for the OPSIN gate, --reachable for what the corpora depend on)")
        return

    winners, refusals = _reachable()
    by_name = {e.get("name"): e for e in entries.values()}
    in_registry = {name: labels for name, labels in winners.items() if name in by_name}
    unaudited = {name: labels for name, labels in in_registry.items()
                 if not by_name[name].get("pin_status")}
    print()
    print(f"{len(winners)} retained names win a tuning-population name "
          f"({len(in_registry)} from the registry, {len(winners) - len(in_registry)} "
          f"from the curated ring and inorganic tables)")
    print(f"  registry entries reached: {len(in_registry)}, audited "
          f"{len(in_registry) - len(unaudited)}, UNKNOWN {len(unaudited)}")
    for name, labels in sorted(in_registry.items()):
        status = by_name[name].get("pin_status", "UNKNOWN")
        print(f"    {status:18s} {name:26s} {', '.join(sorted(labels)[:4])}")
    print()
    print(f"  {len(refusals)} record(s) refused by the gate on a tuning row:")
    for (name, code), labels in sorted(refusals.items()):
        print(f"    {code:26s} {name:26s} {', '.join(sorted(labels)[:4])}")
    if unaudited:
        raise SystemExit(f"{len(unaudited)} reached registry entries have no audited status")


if __name__ == "__main__":
    main()
