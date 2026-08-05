"""Run the real ORCA jobs this benchmark scores, and plot their cubes.

Separate from `score.py` because it is the slow half (minutes per
molecule, and it needs ORCA installed) while scoring is seconds and needs
only the cubes. Re-running this is how the benchmark is refreshed against
a new ORCA build; `score.py` is what runs when only the reading code
changed.

Usage:
    python benchmarks/esp/generate.py <work directory> [--orca D:/ORCA]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.chem.orca_surfaces import ELECTRON_DENSITY, ESP, run_orca_plot

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent

#: B3LYP/def2-SVP, the same level the IR benchmark used, so the two
#: benchmarks describe the same method rather than two.
METHOD_BASIS = "B3LYP def2-SVP"

#: Grid points per axis. The comparison is pointwise on a shared grid, so
#: this sets the resolution of every number in `score.py`. 60 keeps a
#: 12-atom molecule's ESP cube around 3 MB.
RESOLUTION = 60

#: The set, and why each is in it.
MOLECULES = {
    # The lone-pair case named in the plan.
    "water": "O",
    # Controls. No lone pair pointing out of the surface and no halogen,
    # so point charges have nothing in particular to get wrong -- these
    # are what make a high correlation elsewhere meaningful rather than
    # automatic.
    "benzene": "c1ccccc1",
    "methane": "C",
    # The sigma-hole series. The hole should DEEPEN F < Cl < Br, which is
    # a textbook periodic trend and therefore a prediction this benchmark
    # can be wrong about -- the point of including all three rather than
    # only the bromo case the plan asked for.
    "fluorobenzene": "c1ccccc1F",
    "chlorobenzene": "c1ccccc1Cl",
    "bromobenzene": "c1ccccc1Br",
}


def _embed(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    parser.add_argument("--orca", type=Path, default=Path("D:/ORCA"))
    parser.add_argument("--resolution", type=int, default=RESOLUTION)
    args = parser.parse_args()

    orca = args.orca / "orca.exe"
    orca_plot = args.orca / "orca_plot.exe"
    for binary in (orca, orca_plot):
        if not binary.is_file():
            print(f"not found: {binary}", file=sys.stderr)
            return 2

    args.work.mkdir(parents=True, exist_ok=True)
    provider = OrcaQuantumEngineProvider()
    manifest = {}

    for name, smiles in MOLECULES.items():
        directory = args.work / name
        directory.mkdir(exist_ok=True)
        mol = _embed(smiles)
        # Written through the app's own input builder, so the geometry
        # ORCA optimises is the one the app would have sent.
        (directory / "job.inp").write_text(
            provider.build_input(mol, 0, 1, METHOD_BASIS, "opt"), encoding="utf-8"
        )
        # The starting molecule is saved with its BONDS, because the
        # scoring side needs a real RDKit molecule to compute Gasteiger
        # charges on and ORCA's output carries only elements and
        # coordinates. Atom order is preserved through `build_input`,
        # which writes atoms in RDKit index order.
        Chem.MolToMolFile(mol, str(directory / "start.mol"))

        started = time.monotonic()
        with (directory / "job.out").open("w", encoding="utf-8") as handle:
            subprocess.run(
                [str(orca), "job.inp"], stdout=handle, stderr=subprocess.STDOUT,
                cwd=str(directory), check=False,
            )
        elapsed = time.monotonic() - started
        output = (directory / "job.out").read_text(encoding="latin-1")
        if "ORCA TERMINATED NORMALLY" not in output:
            print(f"{name}: ORCA did not terminate normally", file=sys.stderr)
            continue

        esp = run_orca_plot(orca_plot, directory / "job.gbw", ESP, resolution=args.resolution)
        density = run_orca_plot(
            orca_plot, directory / "job.gbw", ELECTRON_DENSITY, resolution=args.resolution
        )
        manifest[name] = {
            "smiles": smiles,
            "esp_cube": esp.name,
            "density_cube": density.name,
            "seconds": round(elapsed, 1),
        }
        print(f"{name:16s} {elapsed:6.1f}s  {esp.name}  {density.name}")

    (args.work / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\nwrote {args.work / 'manifest.json'} ({len(manifest)} molecules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
