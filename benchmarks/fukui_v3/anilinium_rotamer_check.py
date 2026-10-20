"""WRITTEN AFTER THE OUTCOME (PREREGISTRATION.md 11), decides nothing: is anilinium's one run beyond the limit a different cation STATE or a different GEOMETRY?

Arm R's anilinium `embedding101` run differed from the reference by 0.0133 (limit 0.01), every other run of anilinium by at most 0.0054. The two geometries are two rotamers of the NH3+ group (H-N-C-C torsions 60, 180, -61 against -150, -31, 89), 1.4 meV apart in energy.
This runs both geometries with the search OFF (the v2 input, one cation job) as well as ON, so that a difference that appears with one cation job on each, and the same size, is the geometry's and not the search's.

    python anilinium_rotamer_check.py [--cores 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_gate as rg  # noqa: E402

from openchem.app import fukui_gate_3 as gate  # noqa: E402
from openchem.chem.orca_engine import OrcaQuantumEngineProvider  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cores", type=int, default=8)
    args = parser.parse_args()
    out = HERE / "artifacts"
    geometries = json.loads((out / "geometries.json").read_text())
    species = next(s for s in gate.PANEL if s.name == "anilinium")
    classes = rg.symmetry_classes(species.smiles)
    ctx = rg.Context(Path(rg.tempfile.mkdtemp(prefix="anilinium_rotamer_")), args.cores, 2)
    mol = rg.embed(species.smiles, 7)
    jobs = [(geometry, search) for geometry in ("reference", "embedding101") for search in (False, True)]

    def run(item):
        geometry, search = item
        ctx.provider = OrcaQuantumEngineProvider(cation_search=lambda: search)
        # one provider per call would race: build the input here and run it directly
        provider = OrcaQuantumEngineProvider(cation_search=lambda: search)
        coordinates = rg.with_coordinates(mol, np.array(geometries[f"anilinium_{geometry}"]))
        text = provider.build_input(coordinates, species.charge, 1, species.method_basis, "fukui")
        output, _code, seconds = rg.orca(ctx, f"anilinium_{geometry}_{'on' if search else 'off'}", text)
        result = provider._condensed_fukui(output, coordinates)
        return geometry, search, list(result.f_minus), result.cation_note, seconds

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, jobs))
    by = {(g, s): f for g, s, f, _n, _t in results}
    for search in (False, True):
        difference = gate.class_sorted_difference(by[("reference", search)], by[("embedding101", search)], classes)
        print(f"search {'ON ' if search else 'OFF'}: reference vs embedding101 differ by {difference:.4f}")
    for geometry, search, _f, note, seconds in results:
        print(f"  {geometry:13s} search {'ON ' if search else 'OFF'} {seconds:.0f} s  {note[:140]}")


if __name__ == "__main__":
    main()
