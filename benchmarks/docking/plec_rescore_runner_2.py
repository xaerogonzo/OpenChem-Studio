"""Second PLECscore sidecar: score properly built inputs. Run by the ODDT environment's own Python.

    <oddt-python> -I plec_rescore_runner_2.py <dir> [<plecscore_descs_p5_l1.csv.gz>]

Per receptor it reads `<dir>/<PDB>/receptor_full.pdb`, `poses_proper.json` and `crystal.mol` (all
written by `run_plec_test_2.py inputs`) and writes `plec_scores_2.json`: the predicted pKd of each
pose and of the crystal ligand, and, for a receptor that is in the model's own training set,
the share of its stored training fingerprint that these inputs reproduce.

It imports nothing from openchem. Of the first test's runner it reuses only the relaxed readers.

**Why the first test's numbers cannot stand (`PREREGISTRATION_PLEC2.md`).** ODDT 0.7 hashes an
atom environment with `hash(tuple) & 0xffffffff` and calls that "platform independent". CPython
changed the tuple hash in 3.8, and the model's coefficients are indexed by bits made under the
old one, so on a current Python the same atoms land in different bits and the linear model reads
noise. `install_python37_hash` puts the old function back; it is checked against the value
CPython 3.7 gives for `(1, 2, 3)`, and against the stored training fingerprints.
"""

from __future__ import annotations

import ast
import csv
import gzip
import json
import pathlib
import sys
import warnings
from collections import Counter

warnings.filterwarnings("ignore")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

#: Catalogued receptors that are entries of PLECscore's training set. Restated, not imported:
#: this file must run in an environment that has no openchem and no `plec_core`.
TRAINED_ON = ("1HSG", "3EML", "3HS4", "4DJH", "4EA3", "4M48", "4N6H", "5C1M")

_MASK = (1 << 64) - 1
_MODULUS = (1 << 61) - 1


def _int_hash(n: int) -> int:
    h = n % _MODULUS if n >= 0 else -((-n) % _MODULUS)
    return -2 if h == -1 else h


def python37_hash(value) -> int:
    """CPython 3.7's `hash()` for the tuples of ints ODDT hashes (64-bit builds)."""
    if isinstance(value, tuple):
        x, mult, n = 0x345678, 1000003, len(value)
        for item in value:
            n -= 1
            x = ((x ^ (python37_hash(item) & _MASK)) * mult) & _MASK
            mult = (mult + 82520 + n + n) & _MASK
        x = (x + 97531) & _MASK
        return x - (1 << 64) if x >= (1 << 63) else x
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return _int_hash(value)
    return hash(value)


def python37_hash32(value) -> int:
    return python37_hash(value) & 0xFFFFFFFF


def install_python37_hash() -> None:
    import oddt.fingerprints as fingerprints

    fingerprints.hash32 = python37_hash32


def mol_from_block(block: str):
    """A prepared ligand as ODDT's RDKit molecule; its valences were already made consistent."""
    import oddt
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(block, sanitize=False, removeHs=False)
    mol.UpdatePropertyCache(strict=False)
    Chem.SanitizeMol(mol, Chem.SANITIZE_ALL ^ Chem.SANITIZE_PROPERTIES, catchErrors=True)
    return oddt.toolkits.rdk.Molecule(mol)


def stored_fingerprint(descs: pathlib.Path, pdb: str):
    """The training fingerprint ODDT stored for one complex, or None when it is not there."""
    csv.field_size_limit(10**9)
    with gzip.open(descs, "rt") as handle:
        for row in csv.DictReader(handle):
            if row["pdbid"] == pdb.lower():
                return Counter(ast.literal_eval(row["sparse"])), float(row["act"])
    return None


def fidelity(crystal, protein, stored: Counter) -> float:
    """Share of the stored training bits that the same complex rebuilt here also produces."""
    from oddt.fingerprints import PLEC
    from oddt.scoring.functions.PLECscore import MAX_HASH_VALUE

    ours = Counter(PLEC(crystal, protein, depth_ligand=1, depth_protein=5, size=MAX_HASH_VALUE,
                        count_bits=True, sparse=True).tolist())
    return sum((stored & ours).values()) / sum(stored.values())


def main(root: pathlib.Path, descs: pathlib.Path | None) -> None:
    import oddt
    from oddt.scoring.functions import PLECscore

    import plec_rescore_runner as first

    first.shim_scipy()
    install_python37_hash()
    scorer = PLECscore.load(version="linear")
    scores: dict = {"oddt": oddt.__version__, "model": "PLECscore linear P5 L1 pdbbind2016",
                    "hash": "cpython-3.7 tuple hash"}
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and (p / "poses_proper.json").exists()):
        entry: dict = {}
        try:
            protein = first.protein_from_pdb(folder / "receptor_full.pdb")
            scorer.set_protein(protein)
            poses = json.loads((folder / "poses_proper.json").read_text(encoding="utf-8"))
            if any(block is None for block in poses["molblocks"]):
                raise ValueError("a pose could not be built on its template")
            entry["predicted"] = [float(v) for v in scorer.predict(
                [mol_from_block(block) for block in poses["molblocks"]])]
            crystal = mol_from_block((folder / "crystal.mol").read_text(encoding="utf-8"))
            entry["crystal"] = float(scorer.predict([crystal])[0])
            if folder.name in TRAINED_ON and descs is not None:
                stored = stored_fingerprint(descs, folder.name)
                if stored is not None:
                    entry["fidelity"] = fidelity(crystal, protein, stored[0])
                    entry["measured_pkd"] = stored[1]
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed: the report counts it
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        scores[folder.name] = entry
        print(folder.name, entry.get("error", "ok"), flush=True)
    (root / "plec_scores_2.json").write_text(json.dumps(scores, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None)
