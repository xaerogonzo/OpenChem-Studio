import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path.cwd() / "benchmarks" / "fukui_v3"))
import run_gate  # noqa: E402
from rdkit import Chem  # noqa: E402

from openchem.app import fukui_gate_3 as gate  # noqa: E402

root = Path.cwd() / "benchmarks/fukui_v3/artifacts"
records = [json.loads(line) for line in (root / "runs.jsonl").read_text().splitlines()]
by = {(r["species"], r["variant"]): r for r in records if r["kind"] == "R" and r["completed"]}
geoms = json.loads((root / "geometries.json").read_text())
species = next(s for s in gate.PANEL if s.name == "anilinium")
classes = run_gate.symmetry_classes(species.smiles)
mol = Chem.AddHs(Chem.MolFromSmiles(species.smiles))
print("atoms:", [(a.GetIdx(), a.GetSymbol(), [n.GetIdx() for n in a.GetNeighbors()]) for a in mol.GetAtoms() if a.GetSymbol() in "NC"][:4])
ref = by[(species.name, "reference")]
for variant in species.variants():
    r = by[(species.name, variant)]
    d = gate.class_sorted_difference(ref["f_minus"], r["f_minus"], classes)
    line = f"{variant:14s} diff {d:.4f}  states {r['states_found']} competing {r['competing_ev']}  lowest E {r['states'][0]['energy_hartree']:.6f}"
    key = f"anilinium_{variant}" if variant.startswith("embedding") or variant == "reference" else None
    if key and key in geoms:
        xyz = np.array(geoms[key])
        # torsion H-N-C(ipso)-C(ortho): atoms: N=0, ipso=1, ortho=2; H on N are the last three hydrogens? find H neighbours of N
        n_idx = 0
        hs = [a.GetIdx() for a in mol.GetAtomWithIdx(n_idx).GetNeighbors() if a.GetSymbol() == "H"]
        ipso = [a.GetIdx() for a in mol.GetAtomWithIdx(n_idx).GetNeighbors() if a.GetSymbol() == "C"][0]
        ortho = [a.GetIdx() for a in mol.GetAtomWithIdx(ipso).GetNeighbors() if a.GetIdx() != n_idx][0]

        def tors(a, b, c, d):
            b0, b1, b2 = xyz[a] - xyz[b], xyz[c] - xyz[b], xyz[d] - xyz[c]
            b1 = b1 / np.linalg.norm(b1)
            v, w = b0 - np.dot(b0, b1) * b1, b2 - np.dot(b2, b1) * b1
            return float(np.degrees(np.arctan2(np.dot(np.cross(b1, v), w), np.dot(v, w))))

        line += "  H-N-C-C torsions " + str([round(tors(h, n_idx, ipso, ortho)) for h in hs])
        line += f"  CN {np.linalg.norm(xyz[n_idx] - xyz[ipso]):.4f}"
    print(line)
