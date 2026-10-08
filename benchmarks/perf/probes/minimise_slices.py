"""Does slicing `ForceField.Minimize` fix the GIL stall, and what does it cost?

`ForceField.Minimize` holds the GIL for the whole call (see rdkit_gil.py), so a worker
minimising a conformer freezes every other Python thread for that long. Slicing the call
into `maxIts=N` pieces releases the GIL between pieces. The minimiser is restarted at each
slice boundary (BFGS forgets its curvature estimate), so two things have to be measured, not
assumed: how long the OTHER thread is starved, and whether the answer changes.

    PYTHONPATH=. uv run --no-sync python benchmarks/perf/probes/minimise_slices.py
"""

from __future__ import annotations

import threading
import time

from rdkit import Chem
from rdkit.Chem import AllChem

from benchmarks.perf.scenarios import HEAVY_SMILES

PANEL = {
    "ethanol": "CCO",
    "cyclohexane": "C1CCCCC1",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "ethylmorphine": "CCOC1=CC=C2C[C@H]3N(C)CC[C@@]45[C@@H](OC1=C24)[C@@H](O)C=C[C@@H]35",
    "erythromycin": HEAVY_SMILES,
}
MAX_ITERS, FORCE_TOL, ATTEMPTS = 2000, 1e-4, 2


def minimise(ff, slice_iters: int | None) -> bool:
    """The shipped contract: up to ATTEMPTS attempts of MAX_ITERS iterations; True on convergence."""
    for _ in range(ATTEMPTS):
        if slice_iters is None:
            if ff.Minimize(maxIts=MAX_ITERS, forceTol=FORCE_TOL) == 0:
                return True
            continue
        spent = 0
        while spent < MAX_ITERS:
            step = min(slice_iters, MAX_ITERS - spent)
            if ff.Minimize(maxIts=step, forceTol=FORCE_TOL) == 0:
                return True
            spent += step
            time.sleep(0)  # let the waiting thread have the GIL now rather than at the next switch
    return False


def run(mol: Chem.Mol, slice_iters: int | None):
    work = Chem.Mol(mol)
    out: dict = {"energies": [], "converged": 0}

    def job() -> None:
        t0 = time.perf_counter()
        if slice_iters == "batch":
            # RDKit's own multi-conformer optimiser: releases the GIL, default forceTol 1e-4
            # (= the "Normal" level), no per-conformer force tolerance to vary.
            todo = list(range(work.GetNumConformers()))
            for _ in range(ATTEMPTS):
                results = AllChem.MMFFOptimizeMoleculeConfs(work, numThreads=1, maxIters=MAX_ITERS)
                if all(flag == 0 for flag, _ in results):
                    break
            out["converged"] = sum(flag == 0 for flag, _ in results)
            props = AllChem.MMFFGetMoleculeProperties(work)
            out["energies"] = [
                AllChem.MMFFGetMoleculeForceField(work, props, confId=c).CalcEnergy() for c in todo
            ]
            out["seconds"] = time.perf_counter() - t0
            return
        props = AllChem.MMFFGetMoleculeProperties(work)
        for cid in range(work.GetNumConformers()):
            ff = AllChem.MMFFGetMoleculeForceField(work, props, confId=cid)
            out["converged"] += bool(minimise(ff, slice_iters))
            out["energies"].append(ff.CalcEnergy())
        out["seconds"] = time.perf_counter() - t0

    gaps: list[float] = []
    thread = threading.Thread(target=job)
    thread.start()
    last = time.perf_counter()
    while thread.is_alive():
        time.sleep(0.005)
        now = time.perf_counter()
        gaps.append((now - last) * 1000.0)
        last = now
    thread.join()
    gaps = sorted(gaps) or [0.0]  # a job shorter than one tick has no gaps to report
    out.update(ticks=len(gaps), p50=gaps[len(gaps) // 2], p99=gaps[int(0.99 * len(gaps))], max=gaps[-1],
               over100=sum(g > 100 for g in gaps), over30=sum(g > 30 for g in gaps))
    return out


def main() -> None:
    slices = [None, 100, "batch"]
    print(f"{'molecule':14s} {'slice':>6s} {'secs':>6s} {'conv':>5s} {'max gap ms':>10s} {'p99':>6s} "
          f"{'>30ms':>6s} {'>100ms':>6s} {'max |dE| kcal':>14s}")
    for name, smiles in PANEL.items():
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        AllChem.EmbedMultipleConfs(mol, 10, randomSeed=7)
        reference = None
        for size in slices:
            r = run(mol, size)
            if reference is None:
                reference = r["energies"]
            delta = max(abs(a - b) for a, b in zip(r["energies"], reference))
            label = "whole" if size is None else str(size)
            print(f"{name:14s} {label:>6s} {r['seconds']:6.2f} {r['converged']:>2d}/10 {r['max']:10.1f} "
                  f"{r['p99']:6.1f} {r['over30']:6d} {r['over100']:6d} {delta:14.4f}")


if __name__ == "__main__":
    main()
