"""A panel of molecules WITH conformers whose coordinates are frozen in a file, for the tests that hold a geometry calculator to a recording (`tests/test_dipole_typed.py`, `tests/test_surface_typed.py`).

**WHY THE COORDINATES ARE STORED AND NOT EMBEDDED.** A recording of what a calculator says is only a recording of the calculator if its input is the same on every machine. An embedding is seeded, but the force field that relaxes it
is floating-point arithmetic, and the Linux runner is not this machine: a last digit of a coordinate can move a rounded line. The molblocks in `fixtures/conformer_panel.json` were written once, from an embedding
seeded 7 and relaxed with MMFF94 where it has parameters, and are read back with their hydrogens as they are.
"""

from __future__ import annotations

import json
from pathlib import Path

from rdkit import Chem

FIXTURE = Path(__file__).parent / "fixtures" / "conformer_panel.json"

#: Chosen for what each exercises: molecules a dipole is small, middling and large for; a symmetric one (benzene, whose dipole is nothing and whose arrow is not drawn); two a charge model other than Gasteiger declines
#: (DMSO, chloroform); a zwitterion (net charge nothing, a large dipole); three charged species (an anion, a cation of high symmetry, an anion whose dipole depends on the origin); a salt of several fragments; and a molecule
#: whose dipole is nothing in one conformer and large in another (1,2-dichloroethane, here in its anti conformer).
SMILES: dict[str, str] = {
    "water": "O",
    "methane": "C",
    "methanol": "CO",
    "ethanol": "CCO",
    "acetone": "CC(C)=O",
    "dimethyl sulfoxide": "CS(C)=O",
    "chloroform": "ClC(Cl)Cl",
    "benzene": "c1ccccc1",
    "phenol": "Oc1ccccc1",
    "nitromethane": "C[N+](=O)[O-]",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "glycine": "NCC(=O)O",
    "glycine zwitterion": "[NH3+]CC(=O)[O-]",
    "acetate": "CC(=O)[O-]",
    "ammonium": "[NH4+]",
    "sodium acetate": "CC(=O)[O-].[Na+]",
    "1,2-dichloroethane": "ClCCCl",
}

#: The seed the embedding that wrote the file used.
SEED = 7


def write(path: Path = FIXTURE) -> dict[str, str]:
    """(Re)write the file from `SMILES`. Run once, by hand: a rewrite changes every recording that reads it."""
    from rdkit.Chem import AllChem

    blocks: dict[str, str] = {}
    for name, smiles in SMILES.items():
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        if AllChem.EmbedMolecule(mol, randomSeed=SEED) != 0:
            raise RuntimeError(f"{name} could not be embedded")
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=5000)
        except Exception:  # noqa: BLE001 -- no MMFF94 parameters for it: the embedded geometry stands
            pass
        blocks[name] = Chem.MolToMolBlock(mol)
    path.write_text(json.dumps(blocks, indent=1, ensure_ascii=False), encoding="utf-8")
    return blocks


def panel() -> dict[str, Chem.Mol]:
    """Every molecule of the panel with its conformer and its hydrogens, as the app hands a geometry calculator."""
    blocks = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {name: Chem.MolFromMolBlock(block, removeHs=False) for name, block in blocks.items()}
