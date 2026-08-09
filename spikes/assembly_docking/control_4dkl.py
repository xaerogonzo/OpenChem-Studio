"""Task 7's control: does building 4DKL's assembly move a pose that
should not move?

Its orthosteric pocket sits INSIDE the monomer, so the second copy the
assembly adds is distant from the site. The same box, against a receptor
that now carries that second monomer, must give the same binding mode.

THE SEED IS PINNED, and that is the whole reason this measures anything.
`VinaDockingProvider` passes `seed=None`, so the shipped app runs Vina
with a random seed and two runs of the SAME receptor already differ. An
unpinned A/B would be measuring the search wandering. The engine's dock
is wrapped here to force a seed; nothing else in the path is bypassed --
receptor preparation, pdbqt conversion and pose parsing are the real
ones.

The unpinned spread is measured too, as the control's own control: a
receptor-vs-receptor difference only means something against how much the
same receptor moves on its own.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign

from openchem.chem import vina_engine
from openchem.chem.binding_site import box_from_ligand
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.structure_assembly import build_assembly
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

#: Morphine. The textbook mu-opioid ligand, and non-covalent -- 4DKL's own
#: beta-FNA is covalently bound to Lys233, which is a poor thing to dock.
MORPHINE = "CN1CC[C@]23[C@@H]4[C@H]1CC5=C2C(=C(C=C5)O)O[C@H]3[C@H](C=C4)O"


def _pinned(seed: int | None):
    """Force a seed through the real provider, changing nothing else."""
    original = vina_engine.ExecutableVinaEngine.dock

    def docked(self, **kwargs):
        # The provider calls this by KEYWORD, so the wrapper has to accept
        # them that way -- a positional signature raised "unexpected
        # keyword argument 'seed'" and cost a run.
        kwargs["seed"] = seed
        return original(self, **kwargs)

    vina_engine.ExecutableVinaEngine.dock = docked
    return original


def _ligand() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(MORPHINE))
    AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _best(poses) -> tuple[Chem.Mol, float]:
    top = min(poses, key=lambda p: p.binding_affinity_kcal_mol)
    return Chem.MolFromMolBlock(top.pose_molblock, removeHs=False), top.binding_affinity_kcal_mol


def _rmsd(a: Chem.Mol, b: Chem.Mol) -> float:
    """Symmetry-aware, and NOT re-aligned.

    `GetBestRMS` would superimpose the two poses first, which answers
    "same conformer" when the question here is "same PLACE". A pose that
    moved to the other monomer would superimpose perfectly onto itself.
    """
    return rdMolAlign.CalcRMS(a, b)


def main() -> int:
    deposited = structure("4DKL")
    site = box_from_ligand(deposited, "pdb", "BF0")
    result = build_assembly(deposited, "pdb")
    assert result.ok, result.failure_reason
    built = result.output_text

    n_dep = sum(1 for l in deposited.splitlines() if l.startswith(("ATOM  ", "HETATM")))
    n_built = sum(1 for l in built.splitlines() if l.startswith(("ATOM  ", "HETATM")))
    print(f"receptor: deposited {n_dep:,} atoms -> built {n_built:,} atoms")
    print(f"box (from the DEPOSITED structure, reused for both): "
          f"centre {tuple(round(v, 2) for v in site.box.center)} "
          f"size {tuple(round(v, 2) for v in site.box.size)}")

    ligand = _ligand()
    provider = VinaDockingProvider(executable_path_resolver=lambda: VINA)
    # NOT `{"ph": None}`: the provider does `float(options.get("ph", default))`,
    # so an explicit None reaches float() and raises where an absent key
    # would have taken the default.
    options = {"strip_waters": True}

    def dock(text: str) -> tuple[Chem.Mol, float]:
        poses = provider.dock(text, "pdb", ligand, site.box, 5,
                              ProgressHandle(), options)
        return _best(poses)

    print("\nPINNED SEED -- receptor is the only thing that differs")
    print(f"{'seed':>5} {'deposited':>11} {'built':>11} {'dRMSD':>8} {'dScore':>8}")
    for seed in (1, 2, 3):
        original = _pinned(seed)
        try:
            a, score_a = dock(deposited)
            b, score_b = dock(built)
        finally:
            vina_engine.ExecutableVinaEngine.dock = original
        print(f"{seed:>5} {score_a:>11.3f} {score_b:>11.3f} "
              f"{_rmsd(a, b):>8.3f} {abs(score_a - score_b):>8.3f}")

    print("\nUNPINNED, SAME RECEPTOR -- how much the search wanders on its own")
    reference, score_ref = dock(deposited)
    for run in range(2):
        other, score_other = dock(deposited)
        print(f"  run {run + 1}: RMSD {_rmsd(reference, other):>6.3f}  "
              f"dScore {abs(score_ref - score_other):>6.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
