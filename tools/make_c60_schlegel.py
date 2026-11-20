"""Generate the curated Schlegel-style 2D molblock of Buckminsterfullerene.

Run: ``uv run --no-sync python tools/make_c60_schlegel.py`` prints the molblock
(``--write`` stores it as the ``molblock`` of ``allotropes.buckminsterfullerene``
and drops that entry's ``smiles``; an entry holds exactly one of the two).

Why it exists: RDKit's Compute2DCoords tangles a fused cage. A Schlegel diagram
draws the cage as a planar graph with one face (here a pentagon) as the outer
boundary and everything else flattened inside it, so no bond crosses another.
The layout is a weighted Tutte embedding of the cage graph with the outer
pentagon pinned (planar by theorem), the weights fitted so inner bonds come out
near one length. A direct perspective projection of the 3D truncated
icosahedron was tried first and measured: it is planar but its bonds span a
ratio of 14 and the weighted embedding is better balanced. Atom identity and
Kekule bond orders come from the shipped SMILES, so the structure is the same
molecule by canonical SMILES and InChIKey.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Geometry import Point3D

DATA = Path(__file__).resolve().parents[1] / "src/openchem/chem/data/structure_templates/allotropes.json"
ENTRY_ID = "allotropes.buckminsterfullerene"
#: Edge length written to the molblock, Å (the editor's usual 2D bond length).
BOND = 1.5


def _pentagon_through(start: int, nbrs: list[np.ndarray]) -> list[int]:
    """A five-cycle through `start` (every C60 atom is on exactly one)."""
    for a in nbrs[start]:
        for b in nbrs[a]:
            if b == start:
                continue
            for c in nbrs[b]:
                if c in (a, start):
                    continue
                for d in nbrs[c]:
                    if d in (a, b, start):
                        continue
                    if start in nbrs[d]:
                        return [start, a, b, c, d]
    raise RuntimeError("no five-cycle found")


def tutte_layout(geom: Chem.Mol, outer: list[int], outer_radius: float) -> np.ndarray:
    """Planar straight-line layout with `outer` pinned to a regular pentagon.

    Positions solve a weighted Tutte embedding (every free atom at the weighted
    mean of its neighbours): with positive weights and a convex outer face the
    drawing is crossing-free by theorem, whatever the weights. The weights are
    then fitted so the bonds come out near one length. (Tried first and
    abandoned, each measured: a free spring/repulsion minimiser and SMACOF
    stress both pulled bonds through each other or collapsed atoms; a
    crossing-gated descent stalled at bond ratios of 7 to 14.)
    """
    from scipy.optimize import minimize

    n = geom.GetNumAtoms()
    bonds = np.array([(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in geom.GetBonds()])
    free = np.setdiff1d(np.arange(n), outer)
    angles = 2 * math.pi * np.arange(5) / 5
    fixed = np.zeros((n, 2))
    fixed[outer] = outer_radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)
    is_outer_edge = np.isin(bonds[:, 0], outer) & np.isin(bonds[:, 1], outer)

    # One weight per class of bond, so the layout keeps the pentagon's 5-fold
    # symmetry and the search has about twenty unknowns instead of ninety. A
    # class is the pair of graph distances of its ends from the outer pentagon
    # and whether the bond lies in a five-ring.
    from rdkit.Chem import GetDistanceMatrix

    dist = GetDistanceMatrix(geom)[:, outer].min(axis=1).astype(int)
    ring_info = geom.GetRingInfo()
    keys = [
        (min(dist[a], dist[b]), max(dist[a], dist[b]), ring_info.IsBondInRingOfSize(geom.GetBondBetweenAtoms(int(a), int(b)).GetIdx(), 5))
        for a, b in bonds
    ]
    classes = {key: i for i, key in enumerate(sorted(set(keys)))}
    bond_class = np.array([classes[key] for key in keys])

    def embed(class_log_w: np.ndarray) -> np.ndarray:
        w = np.zeros((n, n))
        w[bonds[:, 0], bonds[:, 1]] = w[bonds[:, 1], bonds[:, 0]] = np.exp(class_log_w[bond_class])
        lap = np.diag(w.sum(axis=1)) - w
        pos = fixed.copy()
        pos[free] = np.linalg.solve(lap[np.ix_(free, free)], -lap[np.ix_(free, outer)] @ fixed[outer])
        return pos

    def energy(log_w: np.ndarray) -> float:
        pos = embed(log_w)
        d = np.linalg.norm(pos[bonds[:, 0]] - pos[bonds[:, 1]], axis=1)
        gaps = np.linalg.norm(pos[:, None] - pos[None], axis=2) + np.eye(n) * 99
        return float(np.sum((d[~is_outer_edge] - 1.0) ** 2) + 5.0 * np.sum(np.maximum(0.0, 0.85 - gaps) ** 2))

    fit = minimize(energy, np.zeros(len(classes)), method="L-BFGS-B", bounds=[(-6, 6)] * len(classes),
                   options={"maxiter": 1500})
    return embed(fit.x)


def outer_pentagon(geom: Chem.Mol) -> list[int]:
    """Atoms of one pentagon face, in cycle order."""
    nbrs = [np.array([a.GetIdx() for a in atom.GetNeighbors()]) for atom in geom.GetAtoms()]
    return _pentagon_through(0, nbrs)


def build_molblock(outer_radius: float = 5.0) -> str:
    """The curated molblock, Kekule bonds from the shipped SMILES."""
    mol = Chem.MolFromSmiles(_shipped_smiles())
    Chem.Kekulize(mol, clearAromaticFlags=True)
    xy = tutte_layout(mol, outer_pentagon(mol), outer_radius)
    lengths = [np.linalg.norm(xy[b.GetBeginAtomIdx()] - xy[b.GetEndAtomIdx()]) for b in mol.GetBonds()]
    scale = BOND / float(np.median(lengths))
    conf = Chem.Conformer(mol.GetNumAtoms())
    conf.Set3D(False)
    for i, (x, y) in enumerate(xy * scale):
        conf.SetAtomPosition(i, Point3D(float(x), float(y), 0.0))
    mol.RemoveAllConformers()
    mol.AddConformer(conf)
    return Chem.MolToMolBlock(mol, kekulize=True)


def _shipped_smiles() -> str:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    entry = next(e for e in raw["entries"] if e["id"] == ENTRY_ID)
    if "smiles" in entry:
        return entry["smiles"]
    # Already curated: read the identity back from a pinned copy.
    return "c12c3c4c5c1c1c6c7c2c2c8c3c3c9c4c4c%10c5c5c1c1c6c6c%11c7c2c2c7c8c3c3c8c9c4c4c9c%10c5c5c1c1c6c6c%11c2c2c7c3c3c8c4c4c9c5c1c1c6c2c3c41"


def main(argv: list[str]) -> int:
    block = build_molblock()
    if "--write" in argv:
        raw = json.loads(DATA.read_text(encoding="utf-8"))
        entry = next(e for e in raw["entries"] if e["id"] == ENTRY_ID)
        entry.pop("smiles", None)
        entry["molblock"] = block
        entry["description"] = (
            "C60 as a Schlegel diagram: one pentagon in the centre, the cage flattened outward "
            "(curated layout; tools/make_c60_schlegel.py)."
        )
        DATA.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
