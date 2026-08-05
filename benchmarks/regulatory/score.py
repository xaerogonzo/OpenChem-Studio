"""Score regulatory rules, not runs.

    python benchmarks/regulatory/score.py

EVERY RULE REPORTS TP / FP / TN / FN rather than "matched", because a rule
with perfect recall and terrible precision passes any positives-only suite
and is worse than useless in a screen: it trains its user to ignore the
column. Precision is the number that catches an over-broad pattern, and an
over-broad pattern is the failure mode a structural rule falls into by
default.

The corpora, and why there are four:

  positives    structures the rule SHOULD match
  negatives    ordinary chemicals that must match nothing
  edge_cases   near misses that must NOT match, plus KNOWN false positives
               recorded as such so the benchmark measures the rules as
               written rather than as hoped
  historical   structures whose status CHANGED -- the only way to test
               effective-date resolution

The edge cases carry the weight. Diisopropyl fluorophosphate has sarin's
phosphoryl, fluorine and alkoxy and is not Schedule 1; a rule that cannot
tell them apart would score perfectly on the positives.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from rdkit import Chem, RDLogger

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from openchem.chem.regulatory.engine import RegulatoryEngine  # noqa: E402
from openchem.chem.regulatory.loader import load_all  # noqa: E402

RDLogger.DisableLog("rdApp.*")
HERE = Path(__file__).resolve().parent


def main() -> int:
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    rulesets, problems = load_all(include_user=False)
    if problems:
        print("Could not load:", problems)
        return 1
    engine = RegulatoryEngine(rulesets)

    all_rules = [rule.rule_id for ruleset in rulesets for rule in ruleset.rules]
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    )
    surprises: list[str] = []
    total = 0

    for corpus_name in ("positives", "negatives", "edge_cases", "historical"):
        entries = [e for e in corpus.get(corpus_name, []) if "smiles" in e]
        if not entries:
            continue
        print(f"\n{corpus_name}  ({len(entries)})")
        for entry in entries:
            mol = Chem.MolFromSmiles(entry["smiles"])
            if mol is None:
                print(f"  !! {entry['name']}: SMILES did not parse")
                continue
            total += 1
            expected = set(entry.get("expect", []))
            matched = {
                finding.rule.rule_id
                for finding in engine.screen(mol, include_near_misses=False).findings
            }

            for rule_id in all_rules:
                want = rule_id in expected
                got = rule_id in matched
                key = "tp" if (want and got) else "fp" if got else "fn" if want else "tn"
                counts[rule_id][key] += 1

            if matched != expected:
                surprises.append(
                    f"  {corpus_name}/{entry['name']}: expected "
                    f"{sorted(expected) or 'nothing'}, got {sorted(matched) or 'nothing'}"
                )
                flag = "MISMATCH"
            else:
                flag = "ok"
            print(f"  {flag:9s} {entry['name']}")

    print(f"\n{'rule':22s} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4}  "
          f"{'precision':>9} {'recall':>7}")
    worst_precision = 1.0
    for rule_id in all_rules:
        c = counts[rule_id]
        precision = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 1.0
        recall = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 1.0
        worst_precision = min(worst_precision, precision)
        print(
            f"{rule_id:22s} {c['tp']:4d} {c['fp']:4d} {c['fn']:4d} {c['tn']:4d}  "
            f"{precision:9.2f} {recall:7.2f}"
        )

    if surprises:
        print(f"\nmismatches ({len(surprises)}):")
        for line in surprises:
            print(line)

    print(f"\n{total} structures, {len(all_rules)} rules")
    print(f"worst per-rule precision: {worst_precision:.2f}")
    # Reported, not enforced. A known over-broad rule is a documented state
    # here -- `cwc-1-a-6` matches licensed nitrogen-mustard medicines and
    # says so in its limitations -- and a gate that failed the build for it
    # would push someone to delete the honest edge case rather than fix the
    # rule.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
