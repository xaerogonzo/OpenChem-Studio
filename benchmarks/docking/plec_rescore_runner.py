"""Score saved Vina poses with ODDT's PLECscore. Run by the ODDT environment's own Python.

    <oddt-python> -I plec_rescore_runner.py <poses-dir>

This file imports NOTHING from openchem, on purpose: ODDT 0.7 needs an environment of its own
(it does not install in a plain `pip install` and wants six present at build time), so it is
a sidecar run as a child process, the way `aizynth_runner.py` is. Per receptor it reads
`<dir>/<PDB>/receptor.pdb` and `poses.json` and writes `plec_scores.json` beside them.

The model is ODDT's shipped PLECscore `linear` (depths P5 L1, trained on PDBbind v2016). It
is loaded, never retrained. The score is a predicted pKd: higher is better.
"""

from __future__ import annotations

import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")


def ligand_from_block(block: str):
    """A pose as ODDT's RDKit molecule, WITHOUT RDKit's valence check.

    Vina's pose arrives through a PDBQT that carries no formal charges, so a protonated amine
    is written as a four-bond nitrogen with no charge and RDKit refuses to sanitize it (found
    on the first smoke test, 4IAR). Everything except the property check still runs; the
    protonation state is whatever Vina wrote, stated as a limit in the preregistration.
    """
    import oddt
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(block, sanitize=False, removeHs=False)
    mol.UpdatePropertyCache(strict=False)
    Chem.SanitizeMol(mol, Chem.SANITIZE_ALL ^ Chem.SANITIZE_PROPERTIES, catchErrors=True)
    return oddt.toolkits.rdk.Molecule(mol)


def shim_scipy() -> None:
    """ODDT 0.7 (2019) hands scipy a lazy `map` where current scipy wants a list.

    One of three places the released ODDT meets a modern library (the others: `numpy.in1d`,
    so the sidecar environment pins numpy below 2.3, and the `six` build dependency). The
    shim changes the container only, not a number.
    """
    import oddt.scoring.descriptors as descriptors

    original = descriptors.sparse_vstack
    descriptors.sparse_vstack = lambda blocks, *a, **k: original(list(blocks), *a, **k)


def main(root: pathlib.Path) -> None:
    import oddt
    from oddt.scoring.functions import PLECscore

    shim_scipy()
    scorer = PLECscore.load(version="linear")
    scores: dict = {"oddt": oddt.__version__, "model": "PLECscore linear P5 L1 pdbbind2016"}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        poses = json.loads((folder / "poses.json").read_text(encoding="utf-8"))
        try:
            protein = next(oddt.toolkit.readfile("pdb", str(folder / "receptor.pdb")))
            protein.protein = True
            scorer.set_protein(protein)
            ligands = [ligand_from_block(block) for block in poses["molblocks"]]
            predicted = [float(v) for v in scorer.predict(ligands)]
            scores[folder.name] = {"predicted": predicted}
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed: the report counts it
            scores[folder.name] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
        print(folder.name, scores[folder.name].get("error", "ok"), flush=True)
    (root / "plec_scores.json").write_text(json.dumps(scores, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
