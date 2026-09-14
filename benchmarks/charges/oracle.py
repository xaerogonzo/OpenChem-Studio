"""Open Babel's EEM and QEq against independent solves of the same equations.

    uv run --no-sync python benchmarks/charges/oracle.py [eem,qeq,eem2015bm,...]

The tolerances were fixed in `preregistration.md` before this ran. Both sides
read ONE serialized molblock: Open Babel in a child process
(`openbabel_child.py`, with the data directory set after import), and the
solves below from the same text. So a difference can only come from
implementation, never from geometry, hydrogens or perception.

- **EEM**, Bultinck 2002 II eq 1, which is the matrix `eem.cpp` builds.
  Diagonal B (= 2 eta*, Hartree); off-diagonal kappa/R, R in angstrom; last
  column -1 and last row +1; right-hand side -A and the total formal charge.
  The parameter row is `eem.cpp`'s: the FIRST row in file order that matches
  (element, highest bond order), (element, *) or (*, *).
- **QEq**, Rappe & Goddard 1991 eqs 12-13 in the energy `qeq.cpp` documents,
  E = q.chi + 1/2 q.J.q with sum(q) = Q. Setting its gradient equal to the
  multiplier gives sum_j J_ij q_j - lambda = -chi_i. Both of `qeq.cpp`'s
  documented departures from the paper are applied here too: Gaussian Coulomb
  integrals erf(pR)/R, and hydrogen's charge-independent J and radius.

Measured 2026-09-14 on 13 molecules (neutral, cationic, anionic, zwitterionic;
H C N O F S Cl Br):

    EEM   worst max|OB - solve| = 2.9e-15 e     passes the 1e-4 e tolerance
    QEq   worst max|OB - solve| = 8.0 e         fails
          neutral molecules: max|OB + solve| <= 4e-6 e, so Open Babel's
          charges are the NEGATIVE of the solve. `qeq.cpp` fills its
          right-hand side with +chi where the stationarity condition needs
          -chi. On a charged molecule they are neither.
"""

import json
import math
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
import openbabel
from rdkit import Chem
from rdkit.Chem import AllChem

HERE = pathlib.Path(__file__).parent
TABLE = Chem.GetPeriodicTable()
#: `qeq.h`'s own conversion factors, so the solve cannot differ by a constant.
EV_TO_HARTREE = 3.67493245e-2
ANGSTROM_TO_BOHR = 1.0 / 0.529177249

#: Neutral, charged and zwitterionic; every element the Bultinck set is
#: supposed to cover plus S, Cl and Br, which `eem.txt` covers without a source.
MOLECULES = {
    "methanol": "CO",
    "acetic acid": "CC(=O)O",
    "benzene": "c1ccccc1",
    "pyridine": "c1ccncc1",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "glycine zwitterion": "[NH3+]CC(=O)[O-]",
    "ammonium": "[NH4+]",
    "acetate": "CC(=O)[O-]",
    "fluorobenzene": "Fc1ccccc1",
    "thioanisole": "CSc1ccccc1",
    "chlorobenzene": "Clc1ccccc1",
    "bromobenzene": "Brc1ccccc1",
    "formamide": "NC=O",
}


def read_molblock(text: str) -> list[dict]:
    """Element, coordinates, formal charge and highest bond order, per atom."""
    lines = text.splitlines()
    atom_count, bond_count = int(lines[3][0:3]), int(lines[3][3:6])
    atoms = []
    for line in lines[4:4 + atom_count]:
        atoms.append({
            "z": TABLE.GetAtomicNumber(line[31:34].strip()),
            "xyz": (float(line[0:10]), float(line[10:20]), float(line[20:30])),
            "fc": 0,
            "hbo": 0,
        })
    for line in lines[4 + atom_count:4 + atom_count + bond_count]:
        first, second, order = int(line[0:3]) - 1, int(line[3:6]) - 1, int(line[6:9])
        for index in (first, second):
            atoms[index]["hbo"] = max(atoms[index]["hbo"], order)
    for line in lines[4 + atom_count + bond_count:]:
        if line.startswith("M  CHG"):
            fields = line.split()[3:]
            for index, charge in zip(fields[0::2], fields[1::2]):
                atoms[int(index) - 1]["fc"] = int(charge)
    return atoms


def eem_parameters(path: pathlib.Path) -> tuple[float, list[tuple[int, int, float, float]]]:
    lines = [line.split() for line in path.read_text().splitlines() if line.split()]
    kappa = float(lines[0][1])
    rows = [
        (-1 if symbol == "*" else TABLE.GetAtomicNumber(symbol), -1 if order == "*" else int(order), float(a), float(b))
        for symbol, order, a, b in (line[:4] for line in lines[1:])
    ]
    return kappa, rows


def eem_solve(atoms, kappa, rows):
    n = len(atoms)
    matrix, rhs = np.zeros((n + 1, n + 1)), np.zeros(n + 1)
    for i, atom in enumerate(atoms):
        row = next(
            (r for r in rows if (r[0] == atom["z"] and r[1] in (atom["hbo"], -1)) or (r[0] == -1 and r[1] == -1)),
            None,
        )
        if row is None:
            return None
        matrix[i, i], rhs[i] = row[3], -row[2]
    for i in range(n):
        for j in range(i + 1, n):
            matrix[i, j] = matrix[j, i] = kappa / math.dist(atoms[i]["xyz"], atoms[j]["xyz"])
    matrix[:n, n], matrix[n, :n] = -1.0, 1.0
    rhs[n] = sum(atom["fc"] for atom in atoms)
    return np.linalg.solve(matrix, rhs)[:n]


def qeq_parameters(path: pathlib.Path) -> list[tuple[float, float, float]]:
    params = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if line.startswith("#") or len(parts) < 4:
            continue
        radius = float(parts[3]) * ANGSTROM_TO_BOHR
        params.append((float(parts[1]) * EV_TO_HARTREE, float(parts[2]) * EV_TO_HARTREE, 1.0 / radius**2))
    return params


def qeq_solve(atoms, params):
    n = len(atoms)
    chi = np.array([params[atom["z"] - 1][0] for atom in atoms])
    exponent = [params[atom["z"] - 1][2] for atom in atoms]
    matrix, rhs = np.zeros((n + 1, n + 1)), np.zeros(n + 1)
    for i in range(n):
        matrix[i, i] = params[atoms[i]["z"] - 1][1]
        for j in range(i + 1, n):
            r = math.dist(atoms[i]["xyz"], atoms[j]["xyz"]) * ANGSTROM_TO_BOHR
            p = math.sqrt(exponent[i] * exponent[j] / (exponent[i] + exponent[j]))
            matrix[i, j] = matrix[j, i] = math.erf(p * r) / r
    matrix[:n, n], matrix[n, :n] = -1.0, 1.0
    rhs[:n], rhs[n] = -chi, sum(atom["fc"] for atom in atoms)
    return np.linalg.solve(matrix, rhs)[:n]


def open_babel(method: str, mol_path: pathlib.Path) -> dict:
    run = subprocess.run(
        [sys.executable, str(HERE / "openbabel_child.py"), "python_after_import_win", method, str(mol_path)],
        capture_output=True, text=True, timeout=120,
    )
    line = next((line for line in run.stdout.splitlines() if line.startswith("RESULT ")), None)
    if line is None:
        raise RuntimeError(f"Open Babel child failed with {run.returncode}: {run.stderr[-500:]}")
    return json.loads(line[7:])


def main() -> None:
    methods = sys.argv[1].split(",") if len(sys.argv) > 1 else ["eem", "qeq"]
    data = pathlib.Path(openbabel.__file__).parent / "bin" / "data"
    worst: dict[str, tuple[float, str]] = {}
    with tempfile.TemporaryDirectory() as scratch:
        mol_path = pathlib.Path(scratch) / "input.mol"
        for name, smiles in MOLECULES.items():
            molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
            AllChem.EmbedMolecule(molecule, randomSeed=11)
            block = Chem.MolToMolBlock(molecule)
            mol_path.write_text(block)
            atoms = read_molblock(block)
            for method in methods:
                result = open_babel(method, mol_path)
                seen = result["atoms"]
                same_input = len(seen) == len(atoms) and all(
                    a["z"] == b["z"] and a["hbo"] == b["hbo"] and a["fc"] == b["fc"]
                    and max(abs(u - v) for u, v in zip(a["xyz"], b["xyz"])) < 1e-9
                    for a, b in zip(atoms, seen)
                )
                if method.startswith("eem"):
                    solve = eem_solve(atoms, *eem_parameters(data / f"{method}.txt"))
                else:
                    solve = qeq_solve(atoms, qeq_parameters(data / "qeq.txt"))
                if solve is None:
                    print(f"{name:20} {method:9} no parameter row matches every atom")
                    continue
                charges = np.array([atom["q"] for atom in seen])
                difference = float(np.max(np.abs(charges - solve)))
                negated = float(np.max(np.abs(charges + solve)))
                if difference > worst.get(method, (-1.0, ""))[0]:
                    worst[method] = (difference, name)
                print(
                    f"{name:20} {method:9} computed={result['ok']} same_input={same_input} "
                    f"max|OB-solve|={difference:.1e} max|OB+solve|={negated:.1e} "
                    f"sum(OB)={charges.sum():+.4f}"
                )
    for method, (difference, name) in worst.items():
        print(f"== {method}: worst max|OB-solve| = {difference:.1e} e ({name})")


if __name__ == "__main__":
    main()
