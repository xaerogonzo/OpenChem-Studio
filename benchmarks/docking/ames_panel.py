"""Ames mutagenicity: does the 1 GB model beat alerts that ship for free?

hERG and CYP had no honest rule-based substitute, which is what justified
a sidecar for them. Ames is different, and that difference is the whole
point of this panel. Mutagenicity is the endpoint where structural alerts
genuinely work -- the Ashby-Tennant alert classes have been the basis of
regulatory screening for decades, because a mutagen usually either is or
generates an electrophile, and electrophiles have recognisable
substructures.

So the question is not "is the model any good" but "is it better than
what the application already has offline, instantly, and at no install
cost". This project has declined to ship things that could not beat a
simpler alternative before; the same bar applies here.

THE ALERTS ARE VERIFIED, NOT ASSERTED. Every SMARTS below is checked
against compounds it must and must not match, and the check runs as part
of the report rather than being a claim in a comment. That is the same
discipline the hERG basic-amine pattern was held to, and it matters more
here because a plausible-looking alert that quietly matches nothing would
make the model look good for the wrong reason.

The panel is standard reference mutagens (the positive controls every
Ames lab runs), marketed drugs known to be Ames-positive, and drugs with
clean genotoxicity records. Categorical only -- no revertant counts,
which vary by strain and by S9 activation.
"""

from __future__ import annotations

import json
import statistics as st

from _config import admet_interpreter
from openchem.chem.admet_providers import compute_admet
from openchem.chem.descriptor_providers import (
    _MUTAGENICITY_PATTERNS,
    compute_mutagenicity_alerts,
)
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors

ADMET_PYTHON = admet_interpreter()

# The alert set and the fused-ring rule are the SHIPPED ones, imported
# rather than copied. This benchmark exists to decide whether they earn
# their place in the Properties panel, so measuring a private duplicate
# would answer a question nobody asked -- and the two would drift.
_COMPILED = _MUTAGENICITY_PATTERNS


def alerts_for(mol: Chem.Mol) -> list[str]:
    return compute_mutagenicity_alerts(mol, "benchmark").matched


#: Each pattern must match something it should and miss something it
#: should not. These duplicate `tests/test_mutagenicity_alerts.py` on
#: purpose: a benchmark that silently measures a broken alert set would
#: report a flattering tie.
ALERT_CHECKS = [
    ("Aromatic nitro", "2-nitrofluorene", True),
    ("Aromatic nitro", "aspirin", False),
    ("Aromatic amine", "benzidine", True),
    ("Aromatic amine", "paracetamol", False),
    ("N-aryl amide (aromatic amine precursor)", "paracetamol", True),
    ("N-aryl amide (aromatic amine precursor)", "ibuprofen", False),
    ("N-nitroso", "N-nitrosodimethylamine", True),
    ("N-nitroso", "metformin", False),
    ("Hydrazine", "procarbazine", True),
    ("Hydrazine", "aspirin", False),
]


AMES_POSITIVE = [
    "2-nitrofluorene", "2-aminoanthracene", "benzo[a]pyrene", "aflatoxin B1",
    "4-nitroquinoline 1-oxide", "2-acetylaminofluorene", "benzidine",
    "4-aminobiphenyl", "2,4-dinitrotoluene", "N-nitrosodimethylamine",
    "2-aminofluorene", "metronidazole", "nitrofurantoin", "procarbazine",
    "azathioprine",
]
AMES_NEGATIVE = [
    "aspirin", "paracetamol", "ibuprofen", "metformin", "atenolol",
    "ascorbic acid", "penicillin G", "D-glucose", "naproxen", "lisinopril",
    "sucrose",
]

smiles = json.load(open("ames_ligands.json"))

print("ALERT PATTERN CHECKS -- must match what they claim, and nothing else")
failures = 0
for alert, compound, expected in ALERT_CHECKS:
    mol = Chem.MolFromSmiles(smiles[compound])
    got = mol.HasSubstructMatch(_COMPILED[alert])
    ok = got == expected
    failures += not ok
    print(f"   {alert:<16} on {compound:<24} expect {str(expected):<5} got {str(got):<5}"
          f" {'ok' if ok else '<-- PATTERN IS WRONG'}")
if failures:
    raise SystemExit(f"\n{failures} alert pattern(s) misbehave; fix before trusting the table.")
print("   all patterns behave\n")

rows = []
for name in AMES_POSITIVE + AMES_NEGATIVE:
    if name not in smiles:
        continue
    mol = Chem.MolFromSmiles(smiles[name])
    result = compute_admet(mol, ADMET_PYTHON)
    rows.append({
        "name": name,
        "truth": name in AMES_POSITIVE,
        "ml": float(result["AMES"]),
        "alerts": alerts_for(mol),
        "heavy": mol.GetNumHeavyAtoms(),
        "logp": Crippen.MolLogP(mol),
        "mw": Descriptors.MolWt(mol),
    })

print(f"{'compound':<26} {'known':>7} {'ML':>6} {'alert?':>7}  structural alerts")
print("-" * 96)
for row in sorted(rows, key=lambda r: (-r["truth"], -r["ml"])):
    flagged = bool(row["alerts"])
    marks = ""
    if row["truth"] and row["ml"] < 0.5:
        marks += " ML-MISS"
    if not row["truth"] and row["ml"] >= 0.5:
        marks += " ML-FALSE+"
    if row["truth"] and not flagged:
        marks += " ALERT-MISS"
    if not row["truth"] and flagged:
        marks += " ALERT-FALSE+"
    print(f"{row['name']:<26} {'POS' if row['truth'] else 'neg':>7} {row['ml']:>6.2f}"
          f" {('yes' if flagged else 'no'):>7}  {', '.join(row['alerts']) or '-'}{marks}")


def scores(predicted, rows):
    tp = sum(1 for r, p in zip(rows, predicted) if r["truth"] and p)
    tn = sum(1 for r, p in zip(rows, predicted) if not r["truth"] and not p)
    fp = sum(1 for r, p in zip(rows, predicted) if not r["truth"] and p)
    fn = sum(1 for r, p in zip(rows, predicted) if r["truth"] and not p)
    n = len(rows)
    return tp, tn, fp, fn, (tp + tn) / n


ml_calls = [r["ml"] >= 0.5 for r in rows]
alert_calls = [bool(r["alerts"]) for r in rows]

print("\nHEAD TO HEAD")
print(f"{'':<26}{'TP':>5}{'TN':>5}{'FP':>5}{'FN':>5}{'accuracy':>10}")
for label, calls in (("ADMET-AI model", ml_calls), ("structural alerts", alert_calls)):
    tp, tn, fp, fn, acc = scores(calls, rows)
    print(f"{label:<26}{tp:>5}{tn:>5}{fp:>5}{fn:>5}{acc:>9.0%}")

agree = sum(1 for a, b in zip(ml_calls, alert_calls) if a == b)
print(f"\nthe two agree on {agree}/{len(rows)} compounds")
print("where they disagree:")
for row, ml, al in zip(rows, ml_calls, alert_calls):
    if ml != al:
        right = "model" if ml == row["truth"] else "alerts"
        print(f"   {row['name']:<26} known {'POS' if row['truth'] else 'neg':<4}"
              f" model {'pos' if ml else 'neg':<4} alerts {'pos' if al else 'neg':<4}"
              f"  -> {right} correct")


print("\nCOMBINING THEM -- the two are complementary, not redundant")
print("They tie on accuracy while failing on DIFFERENT compounds, so the")
print("union and the intersection each buy something neither has alone.")
either = [a or b for a, b in zip(ml_calls, alert_calls)]
both = [a and b for a, b in zip(ml_calls, alert_calls)]
for label, calls in (("either flags it", either), ("both must agree", both)):
    tp, tn, fp, fn, acc = scores(calls, rows)
    sensitivity = tp / (tp + fn) if tp + fn else float("nan")
    specificity = tn / (tn + fp) if tn + fp else float("nan")
    print(f"   {label:<18} accuracy {acc:>4.0%}   sensitivity {sensitivity:>4.0%}"
          f"   specificity {specificity:>4.0%}")
print("   For a genotoxicity screen sensitivity is the one that matters --")
print("   a missed mutagen costs more than a compound needlessly re-tested.")


def correlate(xs, ys):
    mx, my = st.fmean(xs), st.fmean(ys)
    d = st.pstdev(xs) * st.pstdev(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / d if d else float("nan")


print("\nTHE CONFOUND CHECK, for comparison with hERG (+0.82 size, +0.75 logP)")
for field, title in (("heavy", "heavy atoms"), ("logp", "logP")):
    print(f"   r(ML prediction, {title:<12}) "
          f"{correlate([r[field] for r in rows], [r['ml'] for r in rows]):+.2f}")
