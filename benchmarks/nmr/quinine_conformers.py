"""Does conformational averaging explain quinine's bad calculation?

THE QUESTION. Phase 32's scale-agreement gate refused quinine because the
calculation sat +3.00 ppm from trusted lookup values, with a worst atom at
9.40 ppm -- well outside the ~5.5 ppm maximum deviation DELTA50 reports for
a properly run B3LYP calculation. The three worst atoms (C-2, C-8, C-9) all
sit around the flexible carbinol/quinuclidine hinge, which is exactly where
a SINGLE conformer is a poor model of a solution average.

So: is the calculation bad because the method is crude, or because it was
handed one arbitrary geometry of a floppy molecule? Those have different
fixes, and only one of them is a problem with the hybrid's gate.

REPORTED PER ATOM, not just in aggregate. If averaging helps, it should
help *on the hinge carbons specifically*. A global improvement with the
hinge unchanged would mean something else is going on, and an aggregate
number cannot tell those apart.

THE ANSWER: NO. Nine conformers, B3LYP/def2-SVP, scored against
Moreland's assigned table.

    MAE over all 20 carbons     single 4.30  ->  Boltzmann 4.27 ppm
    the three hinge carbons     single 6.77  ->  Boltzmann 7.13 ppm
    the other seventeen         single 3.86  ->  Boltzmann 3.76 ppm

Conformational averaging does not rescue this calculation, and the
per-atom view is what shows why the aggregate would have misled: the
hinge carbons the hypothesis named got slightly WORSE, so the mechanism
proposed for quinine's poor agreement is not supported. Whatever limits
the calculation here, it is not the choice of geometry.

Two details worth keeping. First, the DFT populations are lopsided --
one conformer carries 98.7% -- so this is closer to "a different single
conformer" than to a real average, and the comparison is weaker than the
conformer count suggests. Second, that dominant conformer is NOT the one
MMFF ranked first, so the original quinine run used a geometry DFT says
is essentially unpopulated; correcting that moved the MAE by 0.03 ppm.

The one real change is C-5', which went from 12.52 ppm out to 1.66 --
and that was precisely the atom responsible for the worst regret in the
Phase 33 comparison. So conformer choice can fix an individual bad atom
while leaving the spectrum as a whole where it was.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from literature_shifts import QUININE  # noqa: E402
from run_shieldings import ORCA, RAW, slug  # noqa: E402

from openchem.chem.boltzmann import boltzmann_average_spectrum, boltzmann_weights  # noqa: E402
from openchem.chem.orca_engine import OrcaQuantumEngineProvider  # noqa: E402

_SCF_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
METHOD = "B3LYP def2-SVP"
provider = OrcaQuantumEngineProvider()


def conformers(count: int) -> Chem.Mol:
    """`count` MMFF-optimised conformers on one molecule object.

    Kept on a single Mol so every conformer shares the atom ordering the
    literature mapping is keyed to -- separate Mols would each need
    re-validating.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles(QUININE.smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xF00D
    params.useRandomCoords = True
    params.pruneRmsThresh = 0.5
    AllChem.EmbedMultipleConfs(mol, numConfs=count, params=params)
    AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=5000)
    return mol


def run_conformer(mol: Chem.Mol, conf_id: int) -> tuple[dict[int, float], float] | None:
    """Shieldings and SCF energy for one conformer, cached like any other."""
    path = RAW / slug(METHOD) / f"quinine_conf{conf_id:02d}.out"
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        # Build the input from THIS conformer's coordinates. `build_input`
        # reads `mol.GetConformer()` with no id, so the chosen geometry has
        # to be the only one on the molecule it is handed.
        holder = Chem.Mol(mol)
        holder.RemoveAllConformers()
        holder.AddConformer(mol.GetConformer(conf_id), assignId=True)
        text_in = provider.build_input(holder, 0, 1, METHOD, "nmr")
        with tempfile.TemporaryDirectory(prefix=f"quinconf{conf_id}_") as scratch:
            inp = Path(scratch) / "job.inp"
            inp.write_text(text_in, encoding="utf-8")
            done = subprocess.run(
                [str(ORCA), str(inp)], capture_output=True, text=True, cwd=scratch, timeout=28800
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(done.stdout, encoding="utf-8")
        text = done.stdout

    energy = _SCF_RE.search(text)
    result = provider.parse_spectrum_output(text, mol, "q", "nmr")
    if energy is None or result is None or not result.values:
        return None
    return result, float(energy.group(1))


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    mol = conformers(count)
    ids = [c.GetId() for c in mol.GetConformers()]
    print(f"{len(ids)} conformers generated", flush=True)

    spectra, energies = [], []
    for conf_id in ids:
        got = run_conformer(mol, conf_id)
        if got is None:
            print(f"  conf {conf_id}: FAILED", flush=True)
            continue
        result, energy = got
        spectra.append(result)
        energies.append(energy)
        print(f"  conf {conf_id}: E = {energy:.6f} Ha", flush=True)

    weights = boltzmann_weights(energies)
    averaged = boltzmann_average_spectrum(spectra, energies)
    out = {
        "energies_hartree": energies,
        "weights": [round(w, 5) for w in weights],
        "single": {str(i): round(v, 4) for i, v in spectra[0].values.items()},
        "averaged": {str(i): round(v, 4) for i, v in averaged.values.items()},
        "elements": {str(i): e for i, e in averaged.elements.items()},
    }
    path = HERE / "shieldings" / "quinine_conformers.json"
    path.write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(f"\nweights: {['%.3f' % w for w in weights]}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
