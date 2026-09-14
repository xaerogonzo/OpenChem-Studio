"""Freeze amendment A9's O9 corpus as 3D structures, once, before any solve.

    uv run --no-sync python benchmarks/charges/rappe_goddard/build_o9_corpus.py

Reads benchmarks/naming/corpus.json, keeps the molecules whose elements are all
in Rappé–Goddard Table I, and writes tests/fixtures/charges/o9_corpus_conformers.csv:
hydrogens added, ETKDGv3 randomSeed 20260914, MMFF94 200 iterations. Skipped
molecules are written as comment lines with the reason. The study never
regenerates this file; the coordinates are its input.
"""

from __future__ import annotations

import json
import pathlib
import sys

from rdkit import Chem, rdBase
from rdkit.Chem import AllChem

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem.charge_equilibration import QEQ_TABLE_I  # noqa: E402

SEED = 20260914
OUT = ROOT / "tests" / "fixtures" / "charges" / "o9_corpus_conformers.csv"


def main() -> None:
    corpus = json.loads((ROOT / "benchmarks" / "naming" / "corpus.json").read_text(encoding="utf-8"))
    header = [
        "# Amendment A9's O9 corpus: benchmarks/naming/corpus.json restricted to Rappé–Goddard Table I elements,",
        f"# built once on 2026-09-14 by build_o9_corpus.py: RDKit {rdBase.rdkitVersion} AddHs, ETKDGv3 randomSeed={SEED}, MMFF94 200 iterations.",
        "# Coordinates in angstrom; atom order as RDKit numbered the hydrogen-added molecule. Nothing regenerates this file.",
    ]
    rows = ["molecule,category,smiles,net_charge,index,element,x,y,z"]
    kept = 0
    for entry in corpus:
        label, smiles = entry["label"], entry["smiles"]
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            header.append(f"# skipped {label}: RDKit could not parse {smiles}")
            continue
        elements = {atom.GetSymbol() for atom in mol.GetAtoms()} | {"H"}
        missing = sorted(elements - set(QEQ_TABLE_I))
        if missing:
            header.append(f"# skipped {label}: elements outside Table I ({', '.join(missing)})")
            continue
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = SEED
        if AllChem.EmbedMolecule(mol, params) != 0:
            header.append(f"# skipped {label}: ETKDGv3 embedding failed")
            continue
        if not AllChem.MMFFHasAllMoleculeParams(mol):
            header.append(f"# skipped {label}: MMFF94 has no parameters for it")
            continue
        AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        net = Chem.GetFormalCharge(mol)
        positions = mol.GetConformer().GetPositions()
        for atom in mol.GetAtoms():
            x, y, z = positions[atom.GetIdx()]
            rows.append(f"{label},{entry['category']},{smiles},{net},{atom.GetIdx()},{atom.GetSymbol()},{x:.6f},{y:.6f},{z:.6f}")
        kept += 1
    header.append(f"# {kept} molecules kept of {len(corpus)}")
    OUT.write_text("\n".join(header + rows) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({kept} of {len(corpus)} molecules)")


if __name__ == "__main__":
    main()
