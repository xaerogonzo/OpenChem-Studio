"""Does stripping explicit hydrogens before coding fix the `rough` band?

34.3% of nmrshiftdb2's records carry explicit hydrogens and the rest do
not. `hose_code` walks every bond, so an explicit H becomes part of the
code -- which means that third of the database speaks a different code
vocabulary from the other two thirds, and neither can match the other. A
molecule the user drew, which has no explicit hydrogens, can only ever
match the 65.7%.

This builds a second index in which every molecule is stripped to heavy
atoms first, and scores the same held-out split against it. Nothing here
touches shipping code; it is a measurement. Result and caveats are in
README.md -- it is a real improvement (2.91 -> 2.85 ppm overall) and a
larger one than the ML model managed, but it obsoletes every built index
and so is left for its own change.

    python benchmarks/nmr/hydrogen_normalisation.py build
    python benchmarks/nmr/hydrogen_normalisation.py score

Atom indices are REMAPPED rather than trusted. RemoveAllHs renumbers, and
the assignments reference the original numbering -- reading the wrong atom
would produce a plausible index that is wrong throughout, which no later
check would distinguish from a bad predictor.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from rdkit import Chem, RDLogger

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import features as nmr_ml  # noqa: E402
from openchem.chem.hose_codes import hose_codes  # noqa: E402
from openchem.chem.nmr_database import (  # noqa: E402
    MIN_MATCHES,
    _Accumulator,
    _element_from_nucleus,
    _parse_assignments,
    connect,
    create_schema,
)

RDLogger.DisableLog("rdApp.*")

SPHERES = 6
WORK = Path("D:/Random Programs/OpenChemStudio_Data/nmr_train_work")
BANDS = nmr_ml.QUALITY_BANDS


def stripped(mol):
    """(heavy-atom molecule, original index -> new index).

    RemoveAllHs keeps the relative order of the atoms it keeps, so an
    atom's new index is simply how many non-hydrogens preceded it.
    """
    mapping = {}
    kept = 0
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 1:
            mapping[atom.GetIdx()] = kept
            kept += 1
    return Chem.RemoveAllHs(mol), mapping


def iter_rows(sdf: Path):
    """`iter_assigned_spectra`, but heavy-atom-only and remapped.

    Assignments whose atom index IS a hydrogen are dropped -- 7,935 of
    them across the training split. That is a caveat on the 1H numbers
    rather than a decision: 1H records index the heavy atom, so these need
    explaining before this becomes a change.
    """
    supplier = Chem.SDMolSupplier(str(sdf), removeHs=False, sanitize=True)
    for record_index, mol in enumerate(supplier):
        if mol is None:
            continue
        atom_count = mol.GetNumAtoms()
        for prop in mol.GetPropNames():
            if not prop.startswith("Spectrum "):
                continue
            parts = prop.split()
            if len(parts) < 2:
                continue
            element = _element_from_nucleus(parts[1])
            if element is None:
                continue
            assignments = _parse_assignments(mol.GetProp(prop), atom_count)
            if not assignments:
                continue
            try:
                heavy, mapping = stripped(mol)
            except Exception:  # noqa: BLE001
                continue
            remapped = [(mapping[i], shift) for i, shift in assignments if i in mapping]
            if remapped:
                yield record_index, heavy, element, remapped


def build(sdf: Path, destination: Path) -> None:
    accumulators: dict[tuple[str, int, str], _Accumulator] = {}
    records: set[int] = set()
    measurements = 0
    started = time.time()

    for record_index, mol, element, assignments in iter_rows(sdf):
        records.add(record_index)
        for atom_index, shift in assignments:
            try:
                codes = hose_codes(mol, atom_index, SPHERES)
            except Exception:  # noqa: BLE001
                continue
            for offset, code in enumerate(codes):
                key = (code, SPHERES - offset, element)
                accumulator = accumulators.get(key)
                if accumulator is None:
                    accumulator = accumulators[key] = _Accumulator()
                accumulator.add(shift)
            measurements += 1

    connection = connect(destination)
    try:
        create_schema(connection)
        connection.execute("DELETE FROM shift_environments")
        connection.executemany(
            "INSERT INTO shift_environments (hose_code, spheres, element, count, mean, spread) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (code, spheres, element, a.count, a.mean, a.spread)
                for (code, spheres, element), a in accumulators.items()
                if a.count >= MIN_MATCHES
            ],
        )
        connection.commit()
        (kept,) = connection.execute("SELECT count(*) FROM shift_environments").fetchone()
    finally:
        connection.close()
    print(
        f"molecules {len(records):,}  measurements {measurements:,}  environments {kept:,}"
        f"  in {time.time() - started:.0f}s"
    )


def score(sdf: Path, index: Path) -> None:
    connection = connect(index)
    errors: dict[str, list[list[float]]] = {"C": [[] for _ in BANDS], "H": [[] for _ in BANDS]}
    totals = {"C": 0, "H": 0}

    for _record, mol, element, assignments in iter_rows(sdf):
        for atom_index, shift in assignments:
            try:
                codes = hose_codes(mol, atom_index, SPHERES)
            except Exception:  # noqa: BLE001
                continue
            totals[element] += 1
            stats = nmr_ml.sphere_stats(connection, codes, element, SPHERES)
            answer = nmr_ml.hose_answer(stats, element, SPHERES)
            band = BANDS.index(answer.quality) if answer is not None else BANDS.index("none")
            errors[element][band].append(
                abs(answer.shift - shift) if answer is not None else float("nan")
            )
    connection.close()

    for element in ("C", "H"):
        every: list[np.ndarray] = []
        print(f"--- {element} (hydrogen-normalised index): {totals[element]:,} atoms")
        for position, band in enumerate(BANDS):
            values = np.asarray(errors[element][position], dtype=float)
            if values.size == 0:
                continue
            clean = values[~np.isnan(values)]
            every.append(clean)
            if clean.size:
                print(
                    f"    {band:7} n={clean.size:6,}  MAE {clean.mean():6.2f}"
                    f"  median {np.median(clean):6.2f}"
                )
            else:
                print(f"    {band:7} n={values.size:6,}  (no prediction)")
        pooled = np.concatenate(every) if every else np.asarray([])
        if pooled.size:
            print(
                f"    {'ALL':7} n={pooled.size:6,}  MAE {pooled.mean():6.2f}"
                f"  median {np.median(pooled):6.2f}"
                f"   coverage {100 * pooled.size / totals[element]:.1f}%"
            )


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "build"
    if action == "build":
        build(WORK / "train.sd", WORK / "hnorm_index.sqlite")
    else:
        score(WORK / "heldout.sd", WORK / "hnorm_index.sqlite")
