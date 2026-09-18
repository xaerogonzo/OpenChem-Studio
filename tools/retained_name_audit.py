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

`UNKNOWN` is treated as usable by the engine, deliberately. Refusing 274
entries on no evidence is the mirror image of the original defect -- the
answer to "asserted without evidence" is not "denied without evidence". This
report exists so that backlog stays visible instead of looking like a decision.

    python tools/retained_name_audit.py
    python tools/retained_name_audit.py --reachable   # engine consulted
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


def _reachable() -> dict[str, list[str]]:
    """Retained-entry name -> corpus labels whose name it currently wins.

    Imports the engine, so it is behind a flag: the rest of this report is a
    statement about the DATA and should not depend on the code.
    """
    from openchem.vendor.iupac_namer import engine as eng
    from openchem.vendor.iupac_namer import name_smiles
    from openchem.vendor.iupac_namer.types import OutputForm, RetainedPlan

    rows: list[dict] = []
    for filename in ("corpus.json", "heldout.json"):
        path = BENCH / filename
        if path.exists():
            rows.extend(json.loads(path.read_text(encoding="utf-8")))

    original = eng._search_plans
    hits: dict[str, list[str]] = {}
    for row in rows:
        captured: list[str] = []

        def spy(perception, mol, output_form, free_valence, query, strategy, session):
            ranked = original(
                perception, mol, output_form, free_valence, query, strategy, session
            )
            if output_form == OutputForm.STANDALONE and not captured and ranked:
                winner = ranked[-1][2]
                captured.append(
                    winner.match.name if isinstance(winner, RetainedPlan) else ""
                )
            return ranked

        eng._search_plans = spy
        try:
            name_smiles(row["smiles"])
        except Exception:  # noqa: BLE001
            pass
        finally:
            eng._search_plans = original
        if captured and captured[0]:
            hits.setdefault(captured[0], []).append(row["label"])
    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the retained-name registry.")
    parser.add_argument(
        "--reachable",
        action="store_true",
        help="also report which entries a benchmark name depends on (imports the engine)",
    )
    args = parser.parse_args()

    entries = registry()
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

    if not args.reachable:
        print()
        print("  (pass --reachable to see which entries the corpora depend on)")
        return

    hits = _reachable()
    print()
    print(f"{len(hits)} registry entries are reached by a benchmark name")
    unaudited = {
        name: labels
        for name, labels in hits.items()
        if name in {e.get("name") for e in entries.values()}
        and not next(
            (e for e in entries.values() if e.get("name") == name), {}
        ).get("pin_status")
    }
    print(f"{len(unaudited)} of those have NO audited status:")
    for name, labels in sorted(unaudited.items()):
        print(f"    {name:26s} {', '.join(labels[:4])}")


if __name__ == "__main__":
    main()
