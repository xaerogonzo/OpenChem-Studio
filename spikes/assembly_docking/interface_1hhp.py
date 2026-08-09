"""The other half of task 7: a site that IS at the interface.

4DKL is the control -- its pocket is inside the monomer, so building must
NOT move the pose. This is the case where building must move it.

HIV-1 protease is the textbook example: the enzyme is an obligate
homodimer and its active site sits ON the 2-fold axis, with one catalytic
aspartate contributed by each chain. 1HHP deposits ONE chain (758 atoms)
and annotates a dimer, so the file as deposited is half an active site.
Measured here: the two Asp25 CG atoms of the built dimer are 5.36 A
apart, at (43.52, 44.33, -2.62) and (44.33, 43.52, 2.62) -- a clean
2-fold, which is itself a check on the build.

The box is the SAME for both arms and is centred on that dyad, because
that is where the site is. Docking the deposited monomer against it is
not a strawman: it is exactly what the app did before this work, for any
structure whose biological unit the depositor did not put in the file.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign

from openchem.chem import vina_engine
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.structure_assembly import build_assembly
from openchem.domain.docking import DockingBox
from openchem.services.progress import ProgressHandle

#: Overridable, because a Vina path is a property of the machine. The
#: default is the install these numbers were measured against.
VINA = os.environ.get("OPENCHEM_VINA", r"D:\Xaero Stuff\Downloads\vina_1.2.7_win.exe")

#: The RCSB gate's cache, so the two share their downloads.
CACHE = Path(__file__).resolve().parents[2] / "benchmarks" / "assembly" / "cache"


def structure(pdb_id: str) -> str:
    """The deposit, fetched into the gate's cache if it is not there."""
    path = CACHE / f"{pdb_id}.pdb"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(
            f"https://files.rcsb.org/download/{pdb_id}.pdb", timeout=120
        ) as response:
            path.write_bytes(response.read())
    return path.read_text(errors="ignore")

#: Nelfinavir, an approved HIV-1 protease inhibitor. 40 heavy atoms and 9
#: rotatable bonds -- a real drug rather than a probe fragment, because a
#: small rigid ligand could sit happily in half a pocket and hide the
#: effect being measured.
NELFINAVIR = (
    "CC1=C(C=CC=C1O)C(=O)N[C@@H](CSC2=CC=CC=C2)[C@H](O)CN3C[C@H]4CCCC[C@H]4C[C@H]3"
    "C(=O)NC(C)(C)C"
)


def _pinned(seed: int):
    original = vina_engine.ExecutableVinaEngine.dock

    def docked(self, **kwargs):
        kwargs["seed"] = seed
        return original(self, **kwargs)

    vina_engine.ExecutableVinaEngine.dock = docked
    return original


def _catalytic_dyad_centre(text: str) -> tuple[float, float, float]:
    points = [
        (float(l[30:38]), float(l[38:46]), float(l[46:54]))
        for l in text.splitlines()
        if l.startswith("ATOM  ")
        and l[17:20] == "ASP"
        and l[22:26].strip() == "25"
        and l[12:16].strip() == "CG"
    ]
    assert len(points) == 2, f"expected two Asp25 CG atoms, found {len(points)}"
    return tuple(sum(p[i] for p in points) / 2 for i in range(3))


def main() -> int:
    deposited = structure("1HHP")
    result = build_assembly(deposited, "pdb")
    assert result.ok, result.failure_reason
    built = result.output_text

    centre = _catalytic_dyad_centre(built)
    # 24 A: the protease pocket plus the flaps that close over it. Large
    # enough that the monomer arm is not being refused a site it has --
    # it simply does not have the other half.
    box = DockingBox(center=centre, size=(24.0, 24.0, 24.0))

    n = lambda t: sum(1 for l in t.splitlines() if l.startswith(("ATOM  ", "HETATM")))
    print(f"1HHP: deposited {n(deposited):,} atoms (one chain) -> built {n(built):,} (dimer)")
    print(f"box centred on the catalytic dyad: "
          f"{tuple(round(v, 2) for v in centre)} size 24 A cube")

    ligand = Chem.AddHs(Chem.MolFromSmiles(NELFINAVIR))
    AllChem.EmbedMolecule(ligand, randomSeed=0xC0FFEE)
    AllChem.MMFFOptimizeMolecule(ligand)

    provider = VinaDockingProvider(executable_path_resolver=lambda: VINA)
    options = {"strip_waters": True}

    def dock(text: str):
        poses = provider.dock(text, "pdb", ligand, box, 5, ProgressHandle(), options)
        top = min(poses, key=lambda p: p.binding_affinity_kcal_mol)
        return (
            Chem.MolFromMolBlock(top.pose_molblock, removeHs=False),
            top.binding_affinity_kcal_mol,
        )

    print(f"\n{'seed':>5} {'monomer':>10} {'dimer':>10} {'gain':>8} {'dRMSD':>8}")
    for seed in (1, 2, 3):
        original = _pinned(seed)
        try:
            mono, score_mono = dock(deposited)
            dimer, score_dimer = dock(built)
        finally:
            vina_engine.ExecutableVinaEngine.dock = original
        print(f"{seed:>5} {score_mono:>10.3f} {score_dimer:>10.3f} "
              f"{score_mono - score_dimer:>8.3f} {rdMolAlign.CalcRMS(mono, dimer):>8.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
