"""Does the ADMET model know hERG, or does it know molecular size?

On the first ten compounds it separated blockers from non-blockers almost
perfectly -- and correlated with heavy-atom count at r = +0.98. Both facts
can be true at once, because that panel put every blocker among the large
drugs and every non-blocker among the small ones. A model that had learnt
nothing but "big lipophilic molecules block hERG" would score exactly the
same on it.

So this panel is built to break that confound: large compounds with no
hERG liability, and small-to-mid ones with real liability.

THE PAIR THAT SETTLES IT is terfenadine and fexofenadine. Fexofenadine is
terfenadine's own carboxylic-acid metabolite -- slightly LARGER, same
scaffold -- and it exists as a marketed drug precisely because
terfenadine's hERG block caused fatal arrhythmias and got it withdrawn.
Any predictor keying on size or scaffold must score them alike. Only one
keying on the pharmacology can separate them.
"""

from __future__ import annotations

import json
import statistics as st

from openchem.chem.admet_providers import compute_admet
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors

ADMET_PYTHON = r"D:/Random Programs/OpenChemStudio_Data/admet_env/.venv/Scripts/python.exe"

# Clinical classification: withdrawn or carrying a QT/TdP label, versus
# no recognised hERG liability. Compounds whose status is genuinely
# mixed are EXCLUDED rather than forced into a bucket -- verapamil blocks
# hERG in vitro yet carries low torsadogenic risk, and diphenhydramine
# blocks only weakly, so scoring either way would rig the result.
BLOCKERS = {
    "astemizole", "terfenadine", "cisapride", "dofetilide", "amiodarone",
    "sotalol", "haloperidol", "thioridazine", "pimozide", "domperidone",
    "ondansetron",
}
NON_BLOCKERS = {
    "metformin", "paracetamol", "aspirin", "fexofenadine", "cetirizine",
    "atorvastatin", "naproxen", "ranitidine",
}
EXCLUDED = {"verapamil", "diphenhydramine", "loratadine"}

smiles = json.load(open("herg_ligands.json"))

rows = []
for name, smi in smiles.items():
    if name in EXCLUDED:
        continue
    label = "blocker" if name in BLOCKERS else "non-blocker" if name in NON_BLOCKERS else None
    if label is None:
        continue
    mol = Chem.MolFromSmiles(smi)
    result = compute_admet(mol, ADMET_PYTHON)
    rows.append({
        "name": name,
        "heavy": mol.GetNumHeavyAtoms(),
        "logp": Crippen.MolLogP(mol),
        "mw": Descriptors.MolWt(mol),
        "prob": float(result["hERG"]),
        "label": label,
    })

rows.sort(key=lambda r: -r["prob"])
print(f"{'compound':<16} {'heavy':>5} {'MW':>7} {'logP':>6} {'ML hERG':>8}  class")
print("-" * 60)
for r in rows:
    flag = ""
    if r["label"] == "blocker" and r["prob"] < 0.5:
        flag = "  <-- MISSED"
    if r["label"] == "non-blocker" and r["prob"] >= 0.5:
        flag = "  <-- FALSE ALARM"
    print(f"{r['name']:<16} {r['heavy']:>5} {r['mw']:>7.1f} {r['logp']:>6.2f} "
          f"{r['prob']:>8.3f}  {r['label']}{flag}")


def correlate(xs, ys):
    mx, my = st.fmean(xs), st.fmean(ys)
    d = st.pstdev(xs) * st.pstdev(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / d if d else float("nan")


blockers = [r for r in rows if r["label"] == "blocker"]
non = [r for r in rows if r["label"] == "non-blocker"]
print(f"\nn = {len(rows)}  ({len(blockers)} blockers, {len(non)} non-blockers)")
print(f"mean size   blockers {st.fmean(r['heavy'] for r in blockers):.0f} heavy atoms"
      f"   non-blockers {st.fmean(r['heavy'] for r in non):.0f}")
print(f"mean hERG   blockers {st.fmean(r['prob'] for r in blockers):.3f}"
      f"   non-blockers {st.fmean(r['prob'] for r in non):.3f}")

print("\nCorrelation of the prediction with things that are NOT hERG:")
for field, title in (("heavy", "heavy atoms"), ("mw", "molecular weight"), ("logp", "logP")):
    print(f"  r(prob, {title:<17}) {correlate([r[field] for r in rows], [r['prob'] for r in rows]):+.2f}")

correct = sum(
    (r["label"] == "blocker") == (r["prob"] >= 0.5) for r in rows
)
print(f"\naccuracy at a 0.5 threshold: {correct}/{len(rows)}")

print("\nThe decisive pair -- same scaffold, same size, opposite clinical outcome:")
for name in ("terfenadine", "fexofenadine"):
    r = next(x for x in rows if x["name"] == name)
    print(f"  {name:<14} {r['heavy']:>3} heavy, MW {r['mw']:6.1f}, logP {r['logp']:5.2f}"
          f"  ->  {r['prob']:.3f}  ({r['label']})")
