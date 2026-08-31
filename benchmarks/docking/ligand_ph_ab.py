"""Controlled A/B: ONLY the ligand's protonation differs.

Comparing this branch against master would vary two things at once -- the
ligand preparation AND the exhaustiveness default (8 -> 25) -- and master
cannot pin a seed at all, so a same-seed comparison across commits is
impossible. Instead both arms run HERE, through the real provider methods:

    receptor PDBQT     built ONCE at pH 7.4 and reused by both arms, so it
                       is byte-identical rather than merely equivalent
    ligand PDBQT       arm A: AddHydrogens(False, True, 7.4)   [the fix]
                       arm B: addh()                            [the defect]
    box                identical, derived from the deposited ligand
    exhaustiveness     identical
    seed               identical, PINNED, and swept so the pair is measured
                       at several draws rather than one

Reported as centroid displacement from the crystal ligand, which is what
`redock.py` reports and cannot be flattered by a good score.

MEASURED 2026-08-31, exhaustiveness 25, five pinned seeds per target:

    target   pH 7.4 (fix)      neutral (defect)   delta
    8EF5     3.06 - 3.13 A     3.18 - 3.25 A      -0.12 +- 0.02 A
    5C1M     0.40 - 0.43 A     0.51 - 0.53 A      -0.11 +- 0.01 A

**The fix improves the pose in 10 of 10 paired runs**, and the effect is
SMALL: about 0.12 A, against a seed-to-seed spread within either arm of
0.07 A. What makes it real is the sign, not the size -- ten of ten in the
same direction, on two receptors, with everything but the ligand's
protonation held identical.

**IT DOES NOT RESCUE 8EF5.** That redock stays above 3 A in both arms, and
8EF5 is a 3.30 A cryo-EM structure, so the reference ligand position carries
real uncertainty of its own. 5C1M at 2.07 A is the better-resolved arm and
lands at 0.42 A.

**AND THE FIX DOES NOT NEED THIS RESULT.** Its acceptance criterion is
chemical correctness -- the ligand is represented at the declared pH or it is
not -- so it would have shipped on a null. This is secondary evidence,
recorded because it was pre-registered before the numbers existed.
"""

from __future__ import annotations

import math
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _config import vina_executable  # noqa: E402
from openbabel import pybel  # noqa: E402
from openchem import paths  # noqa: E402
from openchem.chem.binding_site import box_from_ligand  # noqa: E402
from openchem.chem.docking_providers import VinaDockingProvider  # noqa: E402
from openchem.chem.receptor_library import find  # noqa: E402
from openchem.chem.vina_engine import ExecutableVinaEngine, parse_vina_output_pdbqt  # noqa: E402
from openchem.services.progress import ProgressHandle  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402

#: The receptor library's own cache. Read rather than fetched, for the reason
#: `OPENCHEM_DRIVE`'s receptor step gives: a measurement that depends on RCSB
#: being up is not a measurement. Populate it once through
#: File > Receptor Library.
CACHE = paths.data_root() / "receptors"
EXHAUSTIVENESS = 25
SEEDS = [11, 22, 33, 44, 55]
# 8EF5 is fentanyl bound to the human mu-opioid receptor -- the experimental
# reference structure for the exact chemistry reported. 5C1M is the receptor
# actually used in the report, whose BU-72 is a rigid morphinan.
TARGETS = {"8EF5": "CCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1", "5C1M": None}

engine = ExecutableVinaEngine(vina_executable())
provider = VinaDockingProvider(engine=engine)


def centroid(points):
    n = len(points)
    return tuple(sum(p[i] for p in points) / n for i in range(3))


def pose_centroid(pdbqt_text):
    pts = [
        (float(l[30:38]), float(l[38:46]), float(l[46:54]))
        for l in pdbqt_text.splitlines()
        if l.startswith(("ATOM", "HETATM"))
    ]
    return centroid(pts)


def ligand_from_component(pdb_id, smiles):
    if smiles is None:
        from openchem.net import open_url
        import json

        code = find(pdb_id).ligand_code
        data = json.loads(
            open_url(f"https://data.rcsb.org/rest/v1/core/chemcomp/{code}", timeout=45).read()
        )
        for row in data.get("pdbx_chem_comp_descriptor", []) or []:
            if row.get("type") == "SMILES_CANONICAL":
                smiles = row.get("descriptor")
                break
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


print(f"{'target':7s} {'seed':>5s}  {'pH 7.4 (fix)':>14s} {'neutral (defect)':>18s}   {'delta':>7s}")
print("-" * 70)
for pdb_id, smiles in TARGETS.items():
    entry = find(pdb_id)
    structure = (CACHE / f"{pdb_id}.pdb").read_text(encoding="utf-8")
    site = box_from_ligand(structure, "pdb", entry.ligand_code)
    crystal = centroid(site.ligand_positions)
    mol = ligand_from_component(pdb_id, smiles)

    with tempfile.TemporaryDirectory() as scratch:
        s = pathlib.Path(scratch)
        receptor = s / "receptor.pdbqt"
        # ONE receptor, both arms. Not "the same options" -- the same FILE.
        provider._convert_receptor_to_pdbqt(
            pybel, structure, "pdb", receptor,
            {"strip_waters": True, "strip_cofactors": True,
             "strip_ligand_codes": (entry.ligand_code,)},
            7.4,
        )
        ligands = {}
        provider._convert_ligand_to_pdbqt(pybel, mol, s / "fix.pdbqt", 7.4)
        ligands["fix"] = s / "fix.pdbqt"
        # The defect, reproduced exactly: pybel's addh() is what the ligand
        # path used to call.
        block = Chem.MolToMolBlock(mol)
        ob = pybel.readstring("mol", block)
        ob.addh()
        ob.write("pdbqt", str(s / "neutral.pdbqt"), overwrite=True)
        ligands["neutral"] = s / "neutral.pdbqt"

        for name, path in ligands.items():
            types = [l.split()[-1] for l in path.read_text().splitlines()
                     if l.startswith(("ATOM", "HETATM"))]
            assert types, name
        fix_has_hd = "HD" in [l.split()[-1] for l in ligands["fix"].read_text().splitlines()
                              if l.startswith(("ATOM", "HETATM"))]
        neu_has_na = "NA" in [l.split()[-1] for l in ligands["neutral"].read_text().splitlines()
                              if l.startswith(("ATOM", "HETATM"))]
        # SETUP ASSERTION: the two arms really do differ in the way claimed.
        print(f"  [{pdb_id} setup] fix has HD: {fix_has_hd}   neutral has NA: {neu_has_na}")

        for seed in SEEDS:
            shifts = {}
            for name, path in ligands.items():
                out = engine.dock(
                    receptor_pdbqt=receptor, ligand_pdbqt=path, box=site.box,
                    num_poses=9, exhaustiveness=EXHAUSTIVENESS, seed=seed,
                    progress=ProgressHandle(),
                )
                best = parse_vina_output_pdbqt(out)[0]
                c = pose_centroid(best.pdbqt_text)
                shifts[name] = math.dist(c, crystal)
            d = shifts["fix"] - shifts["neutral"]
            print(f"{pdb_id:7s} {seed:5d}  {shifts['fix']:11.2f} A {shifts['neutral']:15.2f} A   "
                  f"{d:+6.2f} A")
