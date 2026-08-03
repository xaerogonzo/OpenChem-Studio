"""Pair two indexes atom by atom and bootstrap the difference.

An overall MAE moving from 2.91 to 2.85 ppm is the kind of change that
needs a confidence interval rather than an eyebrow. The comparison is
PAIRED -- the same held-out atom scored by both indexes -- and the
bootstrap resamples MOLECULES, not atoms, because atoms of one molecule
share a structure and an assignment and resampling them independently
would understate the interval.

    python benchmarks/nmr/compare_indexes.py before.sqlite after.sqlite

Both indexes are read through the SHIPPING `lookup`. The atom set comes
from one pass of `iter_assigned_spectra`, so the two columns cannot
silently be scored on different atoms -- which is the way a comparison
like this usually goes wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from rdkit import RDLogger

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.hose_codes import hose_codes  # noqa: E402
from openchem.chem.nmr_database import connect, iter_assigned_spectra, lookup  # noqa: E402

RDLogger.DisableLog("rdApp.*")

SPHERES = 6
WORK = Path("D:/Random Programs/OpenChemStudio_Data/nmr_train_work")


def collect(sdf: Path, before: Path, after: Path):
    left = connect(before)
    right = connect(after)
    rows: dict[str, list[tuple[int, float, float]]] = {"C": [], "H": []}
    try:
        for record, mol, element, assignments in iter_assigned_spectra(sdf):
            for atom_index, shift in assignments:
                try:
                    codes = hose_codes(mol, atom_index, SPHERES)
                except Exception:  # noqa: BLE001
                    continue
                one = lookup(left, codes, element, SPHERES)
                two = lookup(right, codes, element, SPHERES)
                # Only atoms BOTH can answer: an atom one index covers and
                # the other does not is a coverage difference, and averaging
                # it into an accuracy comparison would confuse the two.
                if one is None or two is None:
                    continue
                rows[element].append(
                    (record, abs(one.shift - shift), abs(two.shift - shift))
                )
    finally:
        left.close()
        right.close()
    return rows


def bootstrap(records: np.ndarray, delta: np.ndarray, draws: int = 4000):
    groups = np.unique(records)
    index_of = {record: position for position, record in enumerate(groups)}
    owner = np.asarray([index_of[record] for record in records])
    by_group = [delta[owner == position] for position in range(len(groups))]

    rng = np.random.default_rng(0)
    means = np.empty(draws)
    for draw in range(draws):
        pick = rng.integers(0, len(by_group), len(by_group))
        means[draw] = np.concatenate([by_group[j] for j in pick]).mean()
    return len(groups), np.percentile(means, [2.5, 97.5])


def main(before: Path, after: Path) -> None:
    rows = collect(WORK / "heldout.sd", before, after)
    for element in ("C", "H"):
        if not rows[element]:
            continue
        records = np.asarray([r for r, _, _ in rows[element]])
        old = np.asarray([a for _, a, _ in rows[element]])
        new = np.asarray([b for _, _, b in rows[element]])
        delta = new - old  # negative => the new index is better
        molecules, (low, high) = bootstrap(records, delta)
        verdict = (
            "new better" if high < 0 else "old better" if low > 0 else "not distinguishable"
        )
        print(
            f"{element}: n={len(delta):,} over {molecules:,} molecules   "
            f"before {old.mean():.3f}  after {new.mean():.3f}   "
            f"delta {delta.mean():+.4f}  95% CI [{low:+.4f}, {high:+.4f}]   {verdict}"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
