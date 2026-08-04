"""Does the CYP prediction know WHICH enzyme, or only that a molecule is drug-like?

The hERG panel established the question worth asking: a model can look
excellent while tracking nothing but size and lipophilicity. CYP allows a
sharper version of that test than hERG did, because there are five
isoform predictions per molecule instead of one endpoint.

THE HEADLINE TEST NEEDS NO GROUND TRUTH AT ALL. If the five isoform
predictions rise and fall together across compounds, the model has
learnt "this molecule interacts with CYPs" rather than which one -- and
that is measurable purely from its own outputs, with no reliance on
anyone's classification. Isoform selectivity is the entire clinical point
of a CYP prediction: "inhibits CYP2D6" and "inhibits CYP3A4" imply
different interacting drugs and different advice.

The second test does use clinical knowledge, but only in its most robust
form: for a drug whose SELECTIVE inhibition is textbook -- ketoconazole
for 3A4, quinidine for 2D6, fluvoxamine for 1A2 -- is the model's highest
isoform score the right one? No IC50 values are quoted, because those
vary by assay and are not what is being asked.

INHIBITOR AND SUBSTRATE ARE KEPT APART. The model reports both (Veith =
inhibition, CarbonMangels = substrate) and they are different questions:
an inhibitor blocks the enzyme and causes interactions, a substrate is
cleared by it. Quinidine is the case that punishes conflating them -- a
potent 2D6 INHIBITOR that is itself a 3A4 SUBSTRATE.
"""

from __future__ import annotations

import json
import statistics as st

from _config import admet_interpreter
from openchem.chem.admet_providers import compute_admet
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors

ADMET_PYTHON = admet_interpreter()

INHIBITION = ["CYP1A2_Veith", "CYP2C19_Veith", "CYP2C9_Veith",
              "CYP2D6_Veith", "CYP3A4_Veith"]
SUBSTRATE = ["CYP2C9_Substrate_CarbonMangels", "CYP2D6_Substrate_CarbonMangels",
             "CYP3A4_Substrate_CarbonMangels"]
SHORT = {name: name.split("_")[0].replace("CYP", "") for name in INHIBITION}

#: Drugs whose SELECTIVE inhibition of one isoform is standard clinical
#: knowledge -- the isoform each is used as a probe inhibitor for. Only
#: unambiguous cases are listed; anything with a mixed profile is left out
#: rather than assigned a primary isoform by preference.
SELECTIVE = {
    "ketoconazole": "3A4",
    "itraconazole": "3A4",
    "clarithromycin": "3A4",
    "ritonavir": "3A4",
    "quinidine": "2D6",
    "paroxetine": "2D6",
    "fluoxetine": "2D6",
    "bupropion": "2D6",
    "fluvoxamine": "1A2",
    "ciprofloxacin": "1A2",
    "ticlopidine": "2C19",
}

#: Cleared largely renally or by non-CYP routes, with no meaningful
#: inhibition of any isoform -- the negative controls.
CLEAN = ["metformin", "atenolol", "gabapentin", "lisinopril", "ranitidine"]

#: Classic probe SUBSTRATES, used only against the substrate endpoints.
SUBSTRATES = {"midazolam": "3A4", "dextromethorphan": "2D6", "warfarin": "2C9"}

smiles = json.load(open("cyp_ligands.json"))
wanted = list(SELECTIVE) + CLEAN + list(SUBSTRATES) + ["fluconazole", "omeprazole", "caffeine"]

rows = []
for name in wanted:
    if name not in smiles:
        continue
    mol = Chem.MolFromSmiles(smiles[name])
    result = compute_admet(mol, ADMET_PYTHON)
    rows.append({
        "name": name,
        "heavy": mol.GetNumHeavyAtoms(),
        "logp": Crippen.MolLogP(mol),
        "mw": Descriptors.MolWt(mol),
        "inhib": {SHORT[k]: float(result[k]) for k in INHIBITION},
        "sub": {k.split("_")[0].replace("CYP", ""): float(result[k]) for k in SUBSTRATE},
    })

order = [SHORT[k] for k in INHIBITION]

print("CYP INHIBITION (Veith endpoints)")
print(f"{'compound':<17}" + "".join(f"{iso:>7}" for iso in order) + "   known selective for")
print("-" * 74)
for row in rows:
    peak = max(row["inhib"], key=row["inhib"].get)
    cells = "".join(
        (f"{row['inhib'][iso]:>6.2f}" + ("*" if iso == peak else " ")) for iso in order
    )
    expected = SELECTIVE.get(row["name"], "" if row["name"] not in CLEAN else "(none - clean)")
    mark = ""
    if expected in order:
        mark = "  <-- HIT" if peak == expected else f"  <-- peak is {peak}"
    print(f"{row['name']:<17}{cells}   {expected}{mark}")
print("  * = the model's highest isoform for that compound")


def correlate(xs, ys):
    mx, my = st.fmean(xs), st.fmean(ys)
    d = st.pstdev(xs) * st.pstdev(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / d if d else float("nan")


print("\n1. ISOFORM SPECIFICITY -- needs no ground truth.")
print("   Correlation between isoform predictions across all compounds.")
print("   Near 1.00 everywhere means one 'CYP-ness' score wearing five labels.")
print("        " + "".join(f"{iso:>7}" for iso in order))
pairwise = []
for a in order:
    cells = ""
    for b in order:
        r = correlate([row["inhib"][a] for row in rows], [row["inhib"][b] for row in rows])
        cells += f"{r:>7.2f}"
        if a < b:
            pairwise.append(r)
    print(f"   {a:<5}" + cells)
print(f"   mean off-diagonal correlation: {st.fmean(pairwise):+.2f}"
      f"   (range {min(pairwise):+.2f} to {max(pairwise):+.2f})")

print("\n2. SELECTIVITY -- is the top isoform the clinically expected one?")
print("   RANKING ONLY. A compound scored 0.05 across the board still has a")
print("   'top' isoform, so this says nothing about whether the model")
print("   detected inhibition at all -- section 2b is that question.")
hits = [(r["name"], max(r["inhib"], key=r["inhib"].get), SELECTIVE[r["name"]],
         max(r["inhib"].values())) for r in rows if r["name"] in SELECTIVE]
correct = sum(1 for _n, peak, want, _m in hits if peak == want)
for name, peak, want, peak_value in hits:
    verdict = "hit" if peak == want else "miss"
    if peak_value < 0.5:
        verdict += "  (but scored inactive)"
    print(f"   {name:<17} expected {want:<5} got {peak:<5} {peak_value:.2f}  {verdict}")
print(f"   {correct}/{len(hits)} ranked correctly "
      f"(chance with 5 isoforms is about {len(hits) / 5:.1f})")

print("\n2b. DETECTION -- known inhibitors the model calls inactive")
missed = [(n, m) for n, _p, _w, m in hits if m < 0.5]
for name, peak_value in missed:
    print(f"   {name:<17} highest isoform only {peak_value:.2f}  <-- FALSE NEGATIVE")
print(f"   {len(missed)}/{len(hits)} known inhibitors scored below 0.5 on every isoform")

print("\n3. INHIBITORS vs CLEAN DRUGS, on each compound's own maximum isoform")
inhibitors = [max(r["inhib"].values()) for r in rows if r["name"] in SELECTIVE]
clean = [max(r["inhib"].values()) for r in rows if r["name"] in CLEAN]
print(f"   known inhibitors  n={len(inhibitors):>2}  mean max {st.fmean(inhibitors):.3f}")
print(f"   clean drugs       n={len(clean):>2}  mean max {st.fmean(clean):.3f}")

print("\n4. THE SAME CONFOUND CHECK THE hERG PANEL FAILED")
flat = [(r, iso) for r in rows for iso in order]
for field, title in (("heavy", "heavy atoms"), ("logp", "logP")):
    r_all = correlate([r[field] for r, _ in flat], [r["inhib"][iso] for r, iso in flat])
    print(f"   r(prediction, {title:<12}) {r_all:+.2f}")

print("\n5. SUBSTRATE endpoints on classic probe substrates -- a different question")
print(f"{'compound':<17}" + "".join(f"{iso:>8}" for iso in ("2C9", "2D6", "3A4"))
      + "   known substrate of")
for row in rows:
    if row["name"] not in SUBSTRATES and row["name"] != "quinidine":
        continue
    cells = "".join(f"{row['sub'].get(iso, float('nan')):>8.2f}" for iso in ("2C9", "2D6", "3A4"))
    note = SUBSTRATES.get(row["name"], "3A4 (while INHIBITING 2D6)")
    print(f"{row['name']:<17}{cells}   {note}")
