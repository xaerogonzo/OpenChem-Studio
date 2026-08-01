"""Scores a naming engine against the corpus, by chemistry not by text.

WHY NOT EXACT STRING MATCH. A molecule has many correct IUPAC names.
Scoring on string equality against PubChem punishes an engine for
choosing a different valid one -- in the first run of this benchmark it
marked `4-[amino(dioxo)-lambda6-sulfanyl]aniline` wrong for sulfanilamide,
which is a perfectly good name. So the primary metric is the ROUND TRIP:
parse the predicted name back with OPSIN and compare structures. That is
the only check that answers "does this name denote this molecule".

The outcome classes below exist because "80% correct" hides which 20%.
An engine that silently drops stereochemistry needs a different response
(refuse, or warn) than one that hallucinates a functional group.

Usage:
    python score.py predictions.json [--label "model name"]

`predictions.json` maps a label to a list of predicted names, in the same
order as corpus.json.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rdkit import Chem

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from openchem.chem import naming_providers as n  # noqa: E402

# Outcome classes, best to worst. `EQUIVALENT` is a SUCCESS -- a valid
# alternative name -- and is only separated from `EXACT` so that
# disagreement with PubChem stays visible rather than being scored as
# failure.
EXACT = "exact"                      # round-trips AND matches PubChem verbatim
EQUIVALENT = "equivalent"            # round-trips; different valid wording
STEREO_LOST = "stereo_lost"          # right skeleton, stereochemistry dropped
WRONG_STRUCTURE = "wrong_structure"  # parses, but to a different molecule
UNPARSABLE = "unparsable"            # OPSIN cannot read it at all
NO_PREDICTION = "no_prediction"      # the engine returned nothing

SUCCESS = {EXACT, EQUIVALENT}
ORDER = [EXACT, EQUIVALENT, STEREO_LOST, WRONG_STRUCTURE, UNPARSABLE, NO_PREDICTION]


def _flat(smiles: str) -> str:
    """Canonical SMILES with all stereochemistry stripped.

    Used to tell "wrong molecule" apart from "right molecule, lost its
    stereocentres" -- the distinction that decides whether an engine can
    be trusted with a chiral drug.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    Chem.RemoveStereochemistry(mol)
    return Chem.MolToSmiles(mol)


def classify(row: dict, predicted: str | None) -> str:
    if not predicted or predicted.startswith("<ERROR"):
        return NO_PREDICTION
    try:
        parsed = n.opsin_structure_for_name(predicted)
    except n.NamingError:
        return UNPARSABLE
    got = Chem.MolFromSmiles(parsed.smiles)
    if got is None:
        return UNPARSABLE

    want = Chem.MolFromSmiles(row["smiles"])
    if Chem.MolToSmiles(got) == Chem.MolToSmiles(want):
        truth = row.get("pubchem_name")
        if truth and predicted.strip().lower() == truth.strip().lower():
            return EXACT
        return EQUIVALENT
    if _flat(parsed.smiles) == _flat(row["smiles"]):
        return STEREO_LOST
    return WRONG_STRUCTURE


def report(label: str, rows: list[dict], predictions: list[str]) -> dict:
    outcomes = [classify(r, p) for r, p in zip(rows, predictions)]
    counts = Counter(outcomes)
    total = len(rows)
    ok = sum(counts[c] for c in SUCCESS)

    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
    print(f"  CORRECT (round-trips to the right structure): {ok}/{total}  ({ok / total * 100:.0f}%)")
    for cls in ORDER:
        if counts[cls]:
            print(f"     {cls:16} {counts[cls]:3}")

    print("\n  by category:")
    per_cat: dict[str, list[str]] = defaultdict(list)
    for r, o in zip(rows, outcomes):
        per_cat[r["category"]].append(o)
    for cat in sorted(per_cat, key=lambda c: sum(o in SUCCESS for o in per_cat[c]) / len(per_cat[c])):
        got = sum(o in SUCCESS for o in per_cat[cat])
        bar = "#" * round(got / len(per_cat[cat]) * 20)
        print(f"     {cat:22} {got:2}/{len(per_cat[cat]):<2} {bar}")

    stereo_rows = [(r, o) for r, o in zip(rows, outcomes) if r["has_stereo"]]
    if stereo_rows:
        got = sum(o in SUCCESS for _, o in stereo_rows)
        lost = sum(o == STEREO_LOST for _, o in stereo_rows)
        print(f"\n  stereochemistry: {got}/{len(stereo_rows)} correct, "
              f"{lost} silently flattened")

    worst = [(r, o, p) for r, o, p in zip(rows, outcomes, predictions) if o not in SUCCESS]
    if worst:
        print(f"\n  failures ({len(worst)}):")
        for r, o, p in worst[:40]:
            print(f"     {o:16} {r['label'][:26]:28} {str(p)[:44]}")
        if len(worst) > 40:
            print(f"     ... and {len(worst) - 40} more")
    return {"label": label, "total": total, "correct": ok, "counts": dict(counts),
            "outcomes": outcomes}


def main() -> None:
    corpus = json.loads((Path(__file__).with_name("corpus.json")).read_text(encoding="utf-8"))
    preds = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    summary = [report(label, corpus, data["predictions"] if isinstance(data, dict) else data)
               for label, data in preds.items()]
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
