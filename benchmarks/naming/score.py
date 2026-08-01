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
GATE_DISAGREE = "gate_disagreement"  # SMILES and InChIKey gates disagree
STEREO_LOST = "stereo_lost"          # right skeleton, stereochemistry dropped
WRONG_STRUCTURE = "wrong_structure"  # parses, but to a different molecule
UNPARSABLE = "unparsable"            # OPSIN cannot read it at all
NO_PREDICTION = "no_prediction"      # the engine returned nothing

SUCCESS = {EXACT, EQUIVALENT}
ORDER = [EXACT, EQUIVALENT, GATE_DISAGREE, STEREO_LOST, WRONG_STRUCTURE,
         UNPARSABLE, NO_PREDICTION]


def _key(smiles: str) -> str | None:
    """Full InChIKey, or None when one cannot be generated.

    A SECOND, INDEPENDENT round-trip gate. Canonical SMILES equality is a
    single algorithm's opinion; InChI derives its identity differently, so
    agreement between the two is much stronger evidence than either alone.

    Compare the FULL key, never the 14-character skeleton block. The two
    are not interchangeable for this corpus: guanidinium and neutral
    guanidine share the skeleton block `ZRALSGWEFCBTJO` and differ only in
    the final protonation character (`-O` vs `-N`). Comparing skeletons
    would silently pass exactly the charge defects this benchmark exists
    to catch.

    InChI is not strictly stronger than SMILES -- it normalises some
    tautomer and charge information away -- which is why a disagreement
    between the gates is surfaced for review rather than scored as a
    failure.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        key = Chem.MolToInchiKey(mol)
    except Exception:
        return None
    return key or None


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
    smiles_agrees = Chem.MolToSmiles(got) == Chem.MolToSmiles(want)

    # Second gate. Only adjudicates when both keys exist; when either is
    # unavailable the SMILES verdict stands alone rather than the molecule
    # being penalised for InChI's coverage limits.
    got_key, want_key = _key(parsed.smiles), _key(row["smiles"])
    if got_key is not None and want_key is not None:
        if (got_key == want_key) != smiles_agrees:
            return GATE_DISAGREE

    if smiles_agrees:
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


def _previous_outcomes(label: str) -> list[str] | None:
    """Outcomes from the last recorded run, for the run-to-run delta.

    Matched by label, falling back to the sole entry when labels differ --
    a scratch run is usually labelled differently from the recorded
    baseline, and refusing to compare would make the delta useless in
    exactly the case it is wanted.
    """
    path = Path(__file__).with_name("results.json")
    if not path.exists():
        return None
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(prev, list) or not prev:
        return None
    by_label = {e.get("label"): e for e in prev if isinstance(e, dict)}
    entry = by_label.get(label) or (prev[0] if len(prev) == 1 else None)
    if not isinstance(entry, dict):
        return None
    outcomes = entry.get("outcomes")
    return outcomes if isinstance(outcomes, list) else None


def delta(rows: list[dict], outcomes: list[str], previous: list[str] | None) -> list[tuple]:
    """Per-molecule change since the previous run.

    This is the number that matters when working through a defect list:
    the headline score can sit still while one molecule is fixed and
    another is broken, and only a per-molecule diff makes that visible.
    """
    if not previous or len(previous) != len(outcomes):
        return []
    changed = []
    for row, was, now in zip(rows, previous, outcomes):
        if was == now:
            continue
        direction = (
            "FIXED" if now in SUCCESS and was not in SUCCESS
            else "REGRESSED" if was in SUCCESS and now not in SUCCESS
            else "changed"
        )
        changed.append((direction, row["label"], was, now))
    # Regressions first -- they are the ones that need acting on.
    order = {"REGRESSED": 0, "changed": 1, "FIXED": 2}
    return sorted(changed, key=lambda c: (order[c[0]], c[1]))


_HTML_STYLE = """
:root { color-scheme: light dark; }
body { font: 14px/1.5 ui-sans-serif, system-ui, sans-serif; margin: 2rem auto;
       max-width: 60rem; padding: 0 1rem; }
h1 { font-size: 1.4rem; margin-bottom: .2rem; }
.sub { opacity: .7; margin-top: 0; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid
         color-mix(in srgb, currentColor 15%, transparent); vertical-align: top; }
th { font-weight: 600; position: sticky; top: 0;
     background: Canvas; }
code { font-family: ui-monospace, monospace; font-size: .85em; word-break: break-word; }
.wrap { overflow-x: auto; }
.tag { display: inline-block; padding: .05rem .45rem; border-radius: .5rem;
       font-size: .78em; font-weight: 600; white-space: nowrap; }
.ok       { background: #16803033; color: #14532d; }
.bad      { background: #b9192233; color: #7f1d1d; }
.warn     { background: #b4530933; color: #7c2d12; }
.fixed    { background: #16803055; color: #14532d; }
.regressed{ background: #b9192255; color: #7f1d1d; }
@media (prefers-color-scheme: dark) {
  .ok { color: #86efac; } .bad { color: #fca5a5; } .warn { color: #fdba74; }
  .fixed { color: #86efac; } .regressed { color: #fca5a5; }
}
"""


def _tag(outcome: str) -> str:
    cls = "ok" if outcome in SUCCESS else (
        "warn" if outcome in (STEREO_LOST, GATE_DISAGREE) else "bad")
    return f'<span class="tag {cls}">{outcome}</span>'


def write_html(path: Path, label: str, rows: list[dict], outcomes: list[str],
               predictions: list[str], previous: list[str] | None) -> None:
    """Per-molecule pass/fail/changed/regressed table.

    Chasing 124 molecules one defect at a time is much easier when
    "yesterday benzyl cation FAILED, today PASSED" is visible at a glance
    instead of being reconstructed from two console logs.
    """
    from html import escape

    ok = sum(o in SUCCESS for o in outcomes)
    prev_map = dict(zip(range(len(outcomes)), previous)) if previous and \
        len(previous) == len(outcomes) else {}

    body = [
        f"<h1>{escape(label)}</h1>",
        f'<p class="sub">{ok}/{len(rows)} correct '
        f"({ok / len(rows) * 100:.0f}%) &middot; scored by OPSIN round trip, "
        "gated on canonical SMILES and full InChIKey</p>",
    ]

    changes = delta(rows, outcomes, previous)
    if changes:
        body.append("<h2>Changed since last run</h2><div class='wrap'><table>")
        body.append("<tr><th>&nbsp;</th><th>molecule</th><th>was</th><th>now</th></tr>")
        for direction, mol_label, was, now in changes:
            cls = direction.lower() if direction in ("FIXED", "REGRESSED") else "warn"
            body.append(
                f'<tr><td><span class="tag {cls}">{direction}</span></td>'
                f"<td>{escape(mol_label)}</td><td>{was}</td><td>{now}</td></tr>"
            )
        body.append("</table></div>")

    body.append("<h2>All molecules</h2><div class='wrap'><table>")
    body.append("<tr><th>outcome</th><th>molecule</th><th>predicted name</th>"
                "<th>change</th></tr>")
    for i, (row, outcome, pred) in enumerate(zip(rows, outcomes, predictions)):
        was = prev_map.get(i)
        change = "" if was in (None, outcome) else f"<code>{was} &rarr;</code>"
        body.append(
            f"<tr><td>{_tag(outcome)}</td><td>{escape(row['label'])}</td>"
            f"<td><code>{escape(str(pred))}</code></td><td>{change}</td></tr>"
        )
    body.append("</table></div>")

    path.write_text(
        "<!doctype html><meta charset='utf-8'>"
        f"<title>naming benchmark &mdash; {escape(label)}</title>"
        f"<style>{_HTML_STYLE}</style>" + "".join(body),
        encoding="utf-8",
    )


def main() -> None:
    corpus = json.loads((Path(__file__).with_name("corpus.json")).read_text(encoding="utf-8"))
    preds = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    summary = []
    for label, data in preds.items():
        predictions = data["predictions"] if isinstance(data, dict) else data
        previous = _previous_outcomes(label)
        entry = report(label, corpus, predictions)
        summary.append(entry)

        changes = delta(corpus, entry["outcomes"], previous)
        if changes:
            print(f"\n  changed since last run ({len(changes)}):")
            for direction, mol_label, was, now in changes:
                print(f"     {direction:10} {mol_label[:30]:32} {was} -> {now}")
        elif previous:
            print("\n  changed since last run: nothing")

        html = Path(__file__).with_name(
            "report.html" if len(preds) == 1 else f"report-{label}.html")
        write_html(html, label, corpus, entry["outcomes"], predictions, previous)
        print(f"  -> {html}")

    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
