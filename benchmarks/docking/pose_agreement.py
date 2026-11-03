"""Does agreement among Vina's poses say whether pose 1 is the right one?

    uv run --no-sync python benchmarks/docking/pose_agreement.py bench-out/plec

Reads the `poses.json` files the PLECscore test's `dock` stage wrote (`run_plec_test.py dock`):
Vina's order, each pose's molblock and its assignment RMSD to the crystal pose. For every
receptor, k is the number of OTHER poses whose heavy atoms lie within 2 A (assignment RMSD,
`prep_box_core.assignment_rmsd`) of pose 1; pose 1 is right when it is within 2 A of the crystal
pose. One feature, chosen before looking (the only thing a panel could cheaply show: "how many
of the other poses sit where pose 1 sits"), no threshold fitted. Pure analysis, reports and
decides nothing; `RESULT_AGREEMENT.md` holds the reading.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import prep_box_core as core  # noqa: E402
from rdkit import Chem  # noqa: E402

#: Same cutoff as the survey and the PLECscore tests, restated so this analysis stays put.
WITHIN = 2.0


def one_sided_fisher(right_a: int, wrong_a: int, right_b: int, wrong_b: int) -> float:
    """P(group A has at least this many right), pose 1's rightness independent of the group."""
    n_a, n_b, right = right_a + wrong_a, right_b + wrong_b, right_a + right_b
    top = math.comb(n_a + n_b, right)
    return sum(math.comb(n_a, k) * math.comb(n_b, right - k)
               for k in range(right_a, min(n_a, right) + 1)) / top


def heavy_atoms(block: str):
    mol = Chem.MolFromMolBlock(block, sanitize=False)
    conf = mol.GetConformer()
    return [(a.GetSymbol(), tuple(conf.GetAtomPosition(a.GetIdx())))
            for a in mol.GetAtoms() if a.GetSymbol() != "H"]


def agreement(folder: pathlib.Path):
    """(poses, k, pose 1 right) for one receptor, or None without a measured pose 1."""
    data = json.loads((folder / "poses.json").read_text(encoding="utf-8"))
    rmsd = data["rmsd"]
    if len(rmsd) < 2 or rmsd[0] is None:
        return None
    atoms = [heavy_atoms(block) for block in data["molblocks"]]
    near = [core.assignment_rmsd(atoms[0], other) for other in atoms[1:]]
    k = sum(1 for d in near if d is not None and d <= WITHIN)
    return len(atoms), k, rmsd[0] <= WITHIN


def main(root: pathlib.Path) -> None:
    rows = [(f.name, *r) for f in sorted(root.iterdir())
            if f.is_dir() and (f / "poses.json").exists() and (r := agreement(f)) is not None]
    print(f"{len(rows)} receptors with a measured pose 1; {sum(1 for r in rows if r[1] < 9)} returned fewer than nine poses")
    for k in sorted({r[2] for r in rows}):
        sub = [r for r in rows if r[2] == k]
        print(f"  k = {k}: {len(sub):2d} receptors, pose 1 right in {sum(r[3] for r in sub)}")
    for label, test in (("k >= 1", lambda k: k >= 1), ("k >= 2", lambda k: k >= 2), ("k >= 3", lambda k: k >= 3)):
        agree = [r for r in rows if test(r[2])]
        rest = [r for r in rows if not test(r[2])]
        right_a, right_b = sum(r[3] for r in agree), sum(r[3] for r in rest)
        p = one_sided_fisher(right_a, len(agree) - right_a, right_b, len(rest) - right_b)
        print(f"{label}: {right_a}/{len(agree)} right, against {right_b}/{len(rest)} without; one-sided Fisher p = {p:.2f}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
