"""Score the HOSE lookup on the held-out split, through the shipping code.

This is the arbiter for "did a change to the index or the codes make
prediction better". It calls `iter_assigned_spectra` and `lookup`
directly, so what it measures is what the application does -- a
re-implementation that merely resembled them would be measuring itself.

    python benchmarks/nmr/score_lookup.py split_index.sqlite

The protocol is the one recorded in `chem/nmr_database.py`: every
twentieth record is held out, the index is built from the rest, and those
molecules are predicted against their own measured shifts. Results are
reported per quality band, because a headline average that mixes the band
the lookup is confident about with the band it is not hides both the
thing worth keeping and the thing worth fixing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from rdkit import RDLogger

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.hose_codes import hose_codes  # noqa: E402
from openchem.chem.nmr_database import (  # noqa: E402
    connect,
    iter_assigned_spectra,
    lookup,
    stale_format,
)

RDLogger.DisableLog("rdApp.*")

SPHERES = 6
BANDS = ("good", "medium", "rough")
WORK = Path("D:/Random Programs/OpenChemStudio_Data/nmr_train_work")


def score(sdf: Path, index: Path) -> None:
    if stale_format(index):
        print(f"NOTE: {index.name} is a format-1 index -- scoring it as-is.")

    errors: dict[str, dict[str, list[float]]] = {
        element: {band: [] for band in BANDS} for element in ("C", "H")
    }
    totals = {"C": 0, "H": 0}
    missed = {"C": 0, "H": 0}

    connection = connect(index)
    try:
        for _record, mol, element, assignments in iter_assigned_spectra(sdf):
            for atom_index, shift in assignments:
                try:
                    codes = hose_codes(mol, atom_index, SPHERES)
                except Exception:  # noqa: BLE001
                    continue
                totals[element] += 1
                prediction = lookup(connection, codes, element, SPHERES)
                if prediction is None:
                    missed[element] += 1
                    continue
                errors[element][prediction.quality].append(abs(prediction.shift - shift))
    finally:
        connection.close()

    for element in ("C", "H"):
        if not totals[element]:
            continue
        pooled: list[np.ndarray] = []
        print(f"\n--- {element}: {totals[element]:,} held-out atoms")
        print(f"    {'band':8} {'n':>7}  {'MAE':>7} {'median':>7}")
        for band in BANDS:
            values = np.asarray(errors[element][band], dtype=float)
            pooled.append(values)
            if values.size:
                print(
                    f"    {band:8} {values.size:>7,}  {values.mean():>7.2f}"
                    f" {np.median(values):>7.2f}"
                )
        every = np.concatenate([v for v in pooled if v.size])
        print(
            f"    {'ALL':8} {every.size:>7,}  {every.mean():>7.2f} {np.median(every):>7.2f}"
            f"    coverage {100 * every.size / totals[element]:.1f}%"
            f"  ({missed[element]:,} with no match)"
        )


if __name__ == "__main__":
    index = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK / "split_index.sqlite"
    score(WORK / "heldout.sd", index if index.is_absolute() else WORK / index)
