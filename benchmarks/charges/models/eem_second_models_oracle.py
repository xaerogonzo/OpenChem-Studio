"""An independent solve of the two further EEM models, for check C2 of `eem_second_models_preregistration.md`.

INDEPENDENT MEANS THREE THINGS HERE, each a place the shipped `chem/typed_eem.py` could be wrong without this noticing if it shared it:

1. **The parameters** are read straight from the committed fixtures (`table2.csv`, the `.par` file), never from the shipped JSON that `tools/build_eem_second_models.py`
   makes, so a builder bug cannot hide.
2. **The atom types** are taken from an RDKit molecule's own bonds (the highest `GetBondTypeAsDouble` of any bond to the atom, after kekulisation), not from the
   shipped `highest_bond_orders`.
3. **The solve** is a different algebra: eliminate the equalised electronegativity chi and solve the N x N system M q = chi*1 - A for two right-hand sides, then fix chi
   from sum(q) = Q. The shipped code solves the bordered (N+1) x (N+1) system in one step.

What it deliberately SHARES with the shipped code is the equation itself (J's eq 3 with NEEMP's matrix) and the unit of the distance (angstrom): both come from the same
sources, and the unit is what check C5 tests against reference charges.
"""

from __future__ import annotations

import csv
import pathlib
import xml.etree.ElementTree as ET

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

ROOT = pathlib.Path(__file__).resolve().parents[3]
J_FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "jirouskova2009" / "table2.csv"
N_FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "neemp2016" / "CCD_gen_DE_RMSD_B3LYP_6311G_NPA.par"

J = "jirouskova2009_b3lyp_mk"
N = "neemp2016_ccd_gen_npa"
OUT_OF_SCOPE = {J: {"Zn1"}, N: set()}


def parameters_from_fixtures() -> dict[str, tuple[float, dict[str, tuple[float, float]]]]:
    lines = [ln for ln in J_FIXTURE.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    j_types = {f"{r['element']}{int(r['bond_order'])}": (float(r["b3lyp_A"]), float(r["b3lyp_B"])) for r in csv.DictReader(lines)}
    block = ET.parse(N_FIXTURE).getroot().find("Parameters")
    n_types = {}
    for element in block.findall("Element"):
        for bond in element.findall("Bond"):
            n_types[f"{element.get('Name').strip()}{int(bond.get('Type'))}"] = (float(bond.get("A")), float(bond.get("B")))
    return {J: (0.302, j_types), N: (float(block.get("Kappa")), n_types)}


def kekule_types(mol: Chem.Mol) -> list[str]:
    """Element + the highest bond order of any bond to the atom, from the molecule's OWN Kekule bonds."""
    work = Chem.Mol(mol)
    Chem.Kekulize(work, clearAromaticFlags=True)
    out = []
    for atom in work.GetAtoms():
        orders = [int(round(b.GetBondTypeAsDouble())) for b in atom.GetBonds()]
        out.append(f"{atom.GetSymbol()}{max(orders) if orders else 0}")
    return out


def oracle_charges(mol: Chem.Mol, model: str, types: list[str] | None = None) -> tuple[list[str], np.ndarray | None]:
    """(types, charges) for a molecule WITH a conformer, or (types, None) when the model lacks a type. `types` may be given for a particular Kekule form."""
    kappa, table = parameters_from_fixtures()[model]
    types = types if types is not None else kekule_types(mol)
    if any(t not in table or t in OUT_OF_SCOPE[model] for t in types):
        return types, None
    xyz = mol.GetConformer().GetPositions()
    n = len(types)
    a = np.array([table[t][0] for t in types])
    m = np.zeros((n, n))
    for i in range(n):
        m[i, i] = table[types[i]][1]
        for j in range(n):
            if i != j:
                m[i, j] = kappa / float(np.sqrt(((xyz[i] - xyz[j]) ** 2).sum()))
    charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
    ones = np.ones(n)
    x_a = np.linalg.solve(m, a)  # M^-1 A
    x_1 = np.linalg.solve(m, ones)  # M^-1 1
    chi = (charge + ones @ x_a) / (ones @ x_1)  # from sum(q) = Q with q = chi M^-1 1 - M^-1 A
    return types, chi * x_1 - x_a


def embedded(smiles: str, seed: int = 20261030) -> Chem.Mol | None:
    """The molecule with hydrogens and one MMFF-optimised conformer, or None when it cannot be embedded."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=seed) != 0:
        return None
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
    except Exception:  # noqa: BLE001 - an element MMFF has no type for keeps its embedded coordinates
        pass
    return mol
