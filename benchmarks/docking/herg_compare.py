"""Docking vs the ADMET model, on the same ten compounds.

The docking run separated blockers from non-blockers by 3.5 kcal/mol,
which looked convincing until size was checked: Pearson r between heavy
atom count and Vina score was -0.91, and ligand efficiency reversed the
ranking entirely. So the question here is not "do the two methods agree"
but something sharper -- does the ML model separate these compounds for a
reason that is NOT molecular size?

Same test: correlate each method's output against heavy-atom count. A
predictor that tracks size as tightly as Vina does is measuring the same
confound under a different name.
"""

from __future__ import annotations

import json
import statistics as st
import time

from openchem.chem.admet_providers import compute_admet
from rdkit import Chem

ADMET_PYTHON = r"D:/Random Programs/OpenChemStudio_Data/admet_env/.venv/Scripts/python.exe"

# Vina best-pose affinities and Tyr652 subunit counts from the 8ZYO run.
DOCKED = {
    "astemizole":  (-12.2, 4), "terfenadine": (-10.5, 4),
    "dofetilide":   (-9.9, 4), "verapamil":    (-9.3, 4),
    "amiodarone":   (-9.1, 4), "cisapride":    (-9.0, 4),
    "sotalol":      (-7.8, 3), "aspirin":      (-7.1, 3),
    "paracetamol":  (-6.3, 2), "metformin":    (-5.3, 0),
}
# Clinical class. Verapamil is deliberately NOT counted in either group:
# it genuinely blocks hERG in vitro yet carries low torsadogenic risk
# clinically, so scoring it either way would rig the comparison.
BLOCKERS = {"astemizole", "terfenadine", "cisapride", "dofetilide",
            "amiodarone", "sotalol"}
NON_BLOCKERS = {"metformin", "paracetamol", "aspirin"}

smiles = json.load(open("herg_ligands.json"))

print(f"{'compound':<13} {'heavy':>5} {'Vina':>7} {'LE':>6} {'ML hERG':>8}  class")
print("-" * 60)
rows = []
started = time.time()
for name in DOCKED:
    mol = Chem.MolFromSmiles(smiles[name])
    result = compute_admet(mol, ADMET_PYTHON)
    probability = float(result["hERG"]) if result and "hERG" in result else float("nan")
    affinity, tyr = DOCKED[name]
    heavy = mol.GetNumHeavyAtoms()
    label = ("blocker" if name in BLOCKERS
             else "non-blocker" if name in NON_BLOCKERS else "(excluded)")
    rows.append((name, heavy, affinity, -affinity / heavy, probability, label))
    print(f"{name:<13} {heavy:>5} {affinity:>7.1f} {-affinity/heavy:>6.3f} "
          f"{probability:>8.3f}  {label}")
print(f"\n({time.time() - started:.0f}s for {len(rows)} predictions)")


def correlate(xs, ys):
    mx, my = st.fmean(xs), st.fmean(ys)
    denominator = st.pstdev(xs) * st.pstdev(ys)
    if not denominator:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / denominator


blockers = [r for r in rows if r[5] == "blocker"]
non = [r for r in rows if r[5] == "non-blocker"]

print(f"\n{'':<16}{'blockers':>12}{'non-blockers':>14}   separation")
for label, index, better_is in (("Vina affinity", 2, "lower"),
                                ("ligand eff.", 3, "lower"),
                                ("ML hERG prob", 4, "higher")):
    b, n = st.fmean(r[index] for r in blockers), st.fmean(r[index] for r in non)
    gap = (n - b) if better_is == "lower" else (b - n)
    print(f"{label:<16}{b:>12.3f}{n:>14.3f}   {gap:+.3f} in the right direction"
          if gap > 0 else
          f"{label:<16}{b:>12.3f}{n:>14.3f}   {gap:+.3f} WRONG DIRECTION")

heavy = [r[1] for r in rows]
print(f"\nCorrelation with molecular size (heavy atoms), all {len(rows)} compounds:")
print(f"  r(size, Vina affinity)  {correlate(heavy, [r[2] for r in rows]):+.2f}"
      "   <- larger molecules score better, regardless of pharmacology")
print(f"  r(size, ML hERG prob)   {correlate(heavy, [r[4] for r in rows]):+.2f}")

# Does either method rank every blocker above every non-blocker? That is
# the only claim worth making from ten compounds -- a separated mean can
# hide complete overlap.
worst_blocker = max(blockers, key=lambda r: r[2])
best_non = min(non, key=lambda r: r[2])
print(f"\nVina overlap: worst blocker {worst_blocker[0]} {worst_blocker[2]:.1f} vs "
      f"best non-blocker {best_non[0]} {best_non[2]:.1f}"
      f" -> {'CLEAN' if worst_blocker[2] < best_non[2] else 'OVERLAPPING'}")
low_blocker = min(blockers, key=lambda r: r[4])
high_non = max(non, key=lambda r: r[4])
print(f"ML overlap:   lowest blocker {low_blocker[0]} {low_blocker[4]:.3f} vs "
      f"highest non-blocker {high_non[0]} {high_non[4]:.3f}"
      f" -> {'CLEAN' if low_blocker[4] > high_non[4] else 'OVERLAPPING'}")
