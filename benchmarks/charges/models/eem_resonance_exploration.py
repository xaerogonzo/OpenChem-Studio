"""EXPLORATORY measurement behind `eem_resonance_typing_design.md` (2026-10-30). Run BEFORE the design's checks were registered, and disclosed as such.

    uv run --no-sync python benchmarks/charges/models/eem_resonance_exploration.py

For every molecule of the test panel whose atom types depend on how a nitro group or carboxylate is drawn, under Model N (NEEMP 2016, Ccd2016 NPA): the charge difference
between the two oxygens of one group (a) as drawn, taking the worst over the resonance forms, and (b) with each atom's A and B averaged over the lowest-charge resonance
forms (after Gilson, Gilson and Potter 2003), and the largest change that averaging makes to any atom NOT in a group. A "group" is two variable atoms of one element
bonded to the same single neighbour. The conformers are not symmetric, so an averaged pair can still differ by what the geometry gives it; that residual is reported,
not removed.
"""

from __future__ import annotations

import pathlib
import statistics
import sys

import numpy as np
from rdkit import Chem

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
import test_eem_second_models as panel  # noqa: E402  (the panel and the independent oracle's embedder live there)

te = panel.te
MODEL = te.NEEMP2016_CCD_GEN_NPA


def solve(parameters: list[tuple[float, float]], coords: np.ndarray, kappa: float, charge: float) -> np.ndarray:
    """The Schur-complement solve of the oracle: eliminate chi, solve M q = chi*1 - A."""
    a = np.array([p[0] for p in parameters])
    b = np.array([p[1] for p in parameters])
    n = len(a)
    dist = np.linalg.norm(coords[:, None] - coords[None], axis=-1)
    m = np.zeros((n, n))
    for i in range(n):
        m[i, i] = b[i]
        for j in range(n):
            if i != j:
                m[i, j] = kappa / dist[i, j]
    ones = np.ones(n)
    xa, x1 = np.linalg.solve(m, a), np.linalg.solve(m, ones)
    return ((charge + ones @ xa) / (ones @ x1)) * x1 - xa


def main() -> None:
    entry = te.parameters()[MODEL]
    rows = []
    mixed = 0
    for smiles in panel.PANEL:
        mol = panel.oracle.embedded(smiles)
        if mol is None:
            continue
        elements = [a.GetSymbol() for a in mol.GetAtoms()]
        forms = [Chem.Mol(f) for f in Chem.ResonanceMolSupplier(mol)] or [mol]
        bond_lists = [[(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(round(b.GetBondTypeAsDouble()))) for b in f.GetBonds()] for f in forms]
        sums = [sum(abs(a.GetFormalCharge()) for a in f.GetAtoms()) for f in forms]
        mixed += len(set(sums)) > 1
        kept = [bl for bl, s in zip(bond_lists, sums, strict=True) if s == min(sums)]
        type_sets = [te.atom_types(elements, bl) for bl in kept]
        if len(set(type_sets)) == 1 or any(t not in entry["types"] for ts in type_sets for t in ts):
            continue
        coords, charge, kappa = mol.GetConformer().GetPositions(), sum(a.GetFormalCharge() for a in mol.GetAtoms()), entry["kappa"]
        drawn = [solve([entry["types"][t] for t in ts], coords, kappa, charge) for ts in set(type_sets)]
        averaged = solve([tuple(np.mean([entry["types"][ts[i]] for ts in type_sets], axis=0)) for i in range(len(elements))], coords, kappa, charge)
        variable = [i for i in range(len(elements)) if len({ts[i] for ts in type_sets}) > 1]

        def neighbours(i: int) -> set[int]:
            return {n.GetIdx() for n in mol.GetAtomWithIdx(i).GetNeighbors()}

        pairs = [(i, j) for k, i in enumerate(variable) for j in variable[k + 1 :] if elements[i] == elements[j] and len(neighbours(i)) == 1 and neighbours(i) == neighbours(j)]
        if not pairs:
            continue
        others = [i for i in range(len(elements)) if i not in variable]
        rows.append(
            (
                smiles[:36],
                len(forms),
                len(kept),
                len(pairs),
                max(abs(q[i] - q[j]) for q in drawn for i, j in pairs),
                max(abs(averaged[i] - averaged[j]) for i, j in pairs),
                max(abs(averaged[i] - drawn[0][i]) for i in others) if others else 0.0,
            )
        )
    print(f"molecules with a nitro or carboxylate pair whose types vary: {len(rows)}; molecules whose enumeration mixes formal-charge sums: {mixed}")
    print(f"{'molecule':38s}{'forms':>6s}{'kept':>6s}{'pairs':>6s}{'drawn gap':>11s}{'averaged':>10s}{'elsewhere':>11s}")
    for r in rows:
        print(f"{r[0]:38s}{r[1]:6d}{r[2]:6d}{r[3]:6d}{r[4]:10.3f} e{r[5]:9.4f} e{r[6]:10.3f} e")
    print(f"drawn gap: median {statistics.median(r[4] for r in rows):.3f} e, max {max(r[4] for r in rows):.3f} e; averaged: median {statistics.median(r[5] for r in rows):.4f} e, max {max(r[5] for r in rows):.4f} e")


if __name__ == "__main__":
    main()
