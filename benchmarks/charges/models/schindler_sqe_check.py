"""Schindler 2021 SQE and Geidl 2015 EEM, against their deposited data and the authors' ChargeFW2.

    uv run --no-sync python benchmarks/charges/models/schindler_sqe_check.py a4
    uv run --no-sync python benchmarks/charges/models/schindler_sqe_check.py b
    uv run --no-sync python benchmarks/charges/models/schindler_sqe_check.py c

Everything is frozen by `schindler_sqe_preregistration.md`; this file implements it and decides
nothing. The equations are transcribed from the paper (p 2) and from ChargeFW2's `src/methods/sqe.cpp`
and `src/methods/eem.cpp` at commit 19e73b248cc3983853892d3b42ca0e967a09954a. The one question they
disagree on, the sign of the right-hand side, is a READING, run both ways (section 2).

The source structures are read with a small V2000 parser of our own, not RDKit: sanitising would
re-perceive aromatic bonds and change the bond orders the atom types are made of.
"""

from __future__ import annotations

import io
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field

import numpy as np
from scipy.special import erf

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
SI = pathlib.Path(os.environ.get("OPENCHEM_SCI_DOWNLOADS", r"D:\Xaero Stuff\Documents\Sci Downloads")) / "schindler2021_si"
SQE_PARAMETERS = ROOT / "tests" / "fixtures" / "charges" / "schindler2021" / "SQE_CCD_gen_parameters.json"
GEIDL_NPA = ROOT / "tests" / "fixtures" / "charges" / "geidl2015" / "B3LYP_6-311G_NPA.par"
CHARGEFW2_COMMIT = "19e73b248cc3983853892d3b42ca0e967a09954a"
READINGS = ("R_plus", "R_minus")
AGREE = 1e-6


# --- source data ---------------------------------------------------------------------------------------


@dataclass
class Molecule:
    name: str
    elements: list[str]
    coords: np.ndarray
    bonds: list[tuple[int, int, int]]  # (i, j, order), 0-based, in file order
    formal: list[int] = field(default_factory=list)

    @property
    def total_charge(self) -> int:
        return sum(self.formal)


def parse_sdf(text: str) -> list[Molecule]:
    """V2000 records: title, counts line, atom block, bond block, `M  CHG`. Fails closed on anything else."""
    molecules = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].strip() and i == len(lines) - 1:
            break
        name = lines[i].strip()
        counts = lines[i + 3]
        if "V2000" not in counts:
            raise ValueError(f"{name}: not a V2000 record (line {i + 4})")
        n_atoms, n_bonds = int(counts[0:3]), int(counts[3:6])
        elements, coords, formal = [], [], []
        charge_codes = {1: 3, 2: 2, 3: 1, 5: -1, 6: -2, 7: -3}
        for line in lines[i + 4:i + 4 + n_atoms]:
            coords.append((float(line[0:10]), float(line[10:20]), float(line[20:30])))
            elements.append(line[31:34].strip())
            code = int(line[36:39]) if line[36:39].strip() else 0
            formal.append(charge_codes.get(code, 0))
        bonds = []
        for line in lines[i + 4 + n_atoms:i + 4 + n_atoms + n_bonds]:
            bonds.append((int(line[0:3]) - 1, int(line[3:6]) - 1, int(line[6:9])))
        j = i + 4 + n_atoms + n_bonds
        chg_seen = False
        while lines[j].strip() != "$$$$":
            if lines[j].startswith("M  CHG"):
                if not chg_seen:  # an M  CHG block supersedes the atom-block charge codes
                    formal = [0] * n_atoms
                    chg_seen = True
                fields = lines[j].split()[3:]
                for k in range(0, len(fields), 2):
                    formal[int(fields[k]) - 1] = int(fields[k + 1])
            j += 1
        molecules.append(Molecule(name, elements, np.array(coords, dtype=float), bonds, formal))
        i = j + 1
    return molecules


def parse_chg(text: str) -> dict[str, tuple[list[str], np.ndarray]]:
    """ChargeFW2's charge format: name, atom count, then `index element charge` per atom."""
    out: dict[str, tuple[list[str], np.ndarray]] = {}
    lines = [l for l in text.splitlines()]
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        name, n = lines[i].strip(), int(lines[i + 1])
        rows = [lines[i + 2 + k].split() for k in range(n)]
        if name in out:
            raise ValueError(f"{name} appears twice in the charge file")
        out[name] = ([r[1] for r in rows], np.array([float(r[2]) for r in rows]))
        i += 2 + n
    return out


def load_dataset(name: str) -> list[tuple[Molecule, np.ndarray]]:
    """Every deposited molecule with its reference charges, matched by name, atom count and element."""
    sdf = zipfile.ZipFile(SI / "schindler2021_S3.zip").read(f"{name}.sdf").decode("utf-8")
    chg = zipfile.ZipFile(SI / "schindler2021_S4.zip").read(f"{name}.chg").decode("utf-8")
    molecules, charges = parse_sdf(sdf), parse_chg(chg)
    if len(molecules) != len(charges):
        raise ValueError(f"{name}: {len(molecules)} structures but {len(charges)} charge records")
    paired = []
    for molecule in molecules:
        if molecule.name not in charges:
            raise ValueError(f"{name}: {molecule.name} has no charge record")
        elements, q = charges[molecule.name]
        if [e.upper() for e in elements] != [e.upper() for e in molecule.elements]:
            raise ValueError(f"{name}: {molecule.name} element sequence differs between SDF and charges")
        paired.append((molecule, q))
    return paired


def load_split() -> dict[str, list[str]]:
    text = (SI / "schindler2021_S2.txt").read_text(encoding="utf-8")
    parts = re.split(r"\*\*\* (.+?) \*\*\*", text)
    return {parts[k].strip(): [x.strip() for x in parts[k + 1].replace("\n", " ").split(",") if x.strip()]
            for k in range(1, len(parts), 2)}


# --- typing and parameters ---------------------------------------------------------------------------


def hbo_types(molecule: Molecule) -> list[str]:
    """Element plus the highest bond order over the atom's bonds (ChargeFW2 `structures/molecule.cpp`).

    An atom with no bonds gets order 0, which no published type has, so it is refused.
    """
    highest = [0] * len(molecule.elements)
    for i, j, order in molecule.bonds:
        highest[i] = max(highest[i], order)
        highest[j] = max(highest[j], order)
    return [f"{e.upper()}/{h}" for e, h in zip(molecule.elements, highest)]


def load_sqe_parameters(path: pathlib.Path = SQE_PARAMETERS) -> tuple[dict, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    names = data["atom"]["names"]
    if names != ["chi", "eta", "width"]:
        raise ValueError(f"unexpected atom parameter names {names}")
    atoms = {k.upper(): tuple(v) for k, v in data["atom"]["data"].items()}
    bonds = {k.upper(): float(v) for k, v in data["bond"]["data"].items()}
    return atoms, bonds


def bond_kappa(bonds: dict, type_i: str, type_j: str, order: int) -> float | None:
    """Unordered in the atom pair: the published keys happen to be sorted, and nothing here relies on it."""
    for a, b in ((type_i, type_j), (type_j, type_i)):
        key = f"{a}-{b}-{order}"
        if key in bonds:
            return bonds[key]
    return None


def load_geidl(path: pathlib.Path = GEIDL_NPA) -> tuple[float, dict]:
    lines = [l.split() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if lines[0][0] != "kappa":
        raise ValueError("Geidl parameter file does not open with kappa")
    return float(lines[0][1]), {f"{p[0].upper()}/{p[1]}": (float(p[2]), float(p[3])) for p in lines[1:]}


# --- the two models -------------------------------------------------------------------------------------


def distances(coords: np.ndarray) -> np.ndarray:
    return np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)


def sqe_matrix(molecule: Molecule, atoms: dict, bonds: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray] | str:
    """(T, H, split matrix) or the reason the molecule is refused."""
    types = hbo_types(molecule)
    missing = sorted({t for t in types if t not in atoms})
    if missing:
        return f"atom type {', '.join(missing)} not parameterised"
    n, m = len(types), len(molecule.bonds)
    chi = np.array([atoms[t][0] for t in types])
    eta = np.array([atoms[t][1] for t in types])
    width = np.array([atoms[t][2] for t in types])
    r = distances(molecule.coords)
    d0 = np.sqrt(2.0 * width[:, None] ** 2 + 2.0 * width[None, :] ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        H = erf(r / d0) / r
    H[np.diag_indices(n)] = eta
    T = np.zeros((m, n))
    kappa = np.zeros(m)
    for k, (i, j, order) in enumerate(molecule.bonds):
        T[k, i], T[k, j] = 1.0, -1.0
        value = bond_kappa(bonds, types[i], types[j], order)
        if value is None:
            return f"bond type {types[i]}-{types[j]}-{order} not parameterised"
        kappa[k] = value
    return T, chi, T @ H @ T.T + np.diag(kappa)


def sqe_charges(molecule: Molecule, atoms: dict, bonds: dict, reading: str) -> np.ndarray | str:
    built = sqe_matrix(molecule, atoms, bonds)
    if isinstance(built, str):
        return built
    T, chi, split = built
    if T.shape[0] == 0:
        return np.zeros(len(molecule.elements))
    c = chi if reading == "R_plus" else -chi
    return T.T @ np.linalg.solve(split, T @ c)


def eem_charges(molecule: Molecule, kappa: float, parameters: dict) -> np.ndarray | str:
    """ChargeFW2 `eem.cpp`, "full": B on the diagonal, kappa/r off it, -A, bordered by the total charge."""
    types = hbo_types(molecule)
    missing = sorted({t for t in types if t not in parameters})
    if missing:
        return f"atom type {', '.join(missing)} not parameterised"
    n = len(types)
    r = distances(molecule.coords)
    A = np.zeros((n + 1, n + 1))
    with np.errstate(divide="ignore"):
        A[:n, :n] = kappa / r
    A[np.diag_indices(n)] = [parameters[t][1] for t in types]
    A[n, :n] = 1.0
    A[:n, n] = 1.0
    A[n, n] = 0.0
    b = np.zeros(n + 1)
    b[:n] = [-parameters[t][0] for t in types]
    b[n] = molecule.total_charge
    return np.linalg.solve(A, b)[:n]


# --- the paper's metrics ----------------------------------------------------------------------------------


def metrics(pairs: list[tuple[list[str], np.ndarray, np.ndarray]], pooled_rmsdat: bool = True) -> dict:
    """Per-molecule R2 and RMSD averaged over the set; RMSDat the worst per-type RMSD (section 1)."""
    r2s, rmsds, undefined = [], [], 0
    by_type: dict[str, list[float]] = {}
    per_molecule_type: dict[str, list[float]] = {}
    for types, ref, model in pairs:
        diff = model - ref
        rmsds.append(math.sqrt(float(np.mean(diff ** 2))))
        if np.std(ref) == 0 or np.std(model) == 0:
            undefined += 1
        else:
            r2s.append(float(np.corrcoef(ref, model)[0, 1] ** 2))
        seen: dict[str, list[float]] = {}
        for t, d in zip(types, diff):
            by_type.setdefault(t, []).append(float(d))
            seen.setdefault(t, []).append(float(d))
        for t, ds in seen.items():
            per_molecule_type.setdefault(t, []).append(math.sqrt(np.mean(np.square(ds))))
    pooled = {t: math.sqrt(float(np.mean(np.square(v)))) for t, v in by_type.items()}
    averaged = {t: float(np.mean(v)) for t, v in per_molecule_type.items()}
    return {
        "molecules": len(pairs), "r2_undefined": undefined,
        "R2": float(np.mean(r2s)), "RMSD": float(np.mean(rmsds)),
        "RMSDat": max(pooled.values()), "RMSDat_type": max(pooled, key=pooled.get),
        "RMSDat_sensitivity_per_molecule_mean": max(averaged.values()),
    }


# --- ChargeFW2 in WSL --------------------------------------------------------------------------------------


def to_wsl_path(path: pathlib.Path) -> str:
    resolved = str(path.resolve())
    return "/mnt/" + resolved[0].lower() + resolved[2:].replace("\\", "/")


def chargefw2_parameter_file(atoms: dict, bonds: dict, out: pathlib.Path) -> pathlib.Path:
    """S7's full-precision values in ChargeFW2's schema, so the authors' code runs the published numbers."""
    def element(symbol: str) -> str:
        return symbol[0] + symbol[1:].lower()
    atom_rows = [{"key": [element(k.split("/")[0]), "hbo", k.split("/")[1]], "value": list(v)} for k, v in sorted(atoms.items())]
    bond_rows = []
    for key, value in sorted(bonds.items()):
        # keys look like "C/1-H/1-1": the bond order is after the last "-", the two types before it
        pair, order = key.rsplit("-", 1)
        first, second = pair.split("-")
        bond_rows.append({"key": [element(first.split("/")[0]), "hbo", first.split("/")[1],
                                  element(second.split("/")[0]), "hbo", second.split("/")[1], "bo", order],
                          "value": [value]})
    payload = {
        "metadata": {"name": "Schindler 2021 (CCD_gen), S7 full precision", "method": "sqe",
                     "publication": "10.1186/s13321-021-00528-w"},
        "atom": {"names": ["electronegativity", "hardness", "width"], "data": atom_rows},
        "bond": {"names": ["kappa"], "data": bond_rows},
    }
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return out


def run_chargefw2(sdf: pathlib.Path, method: str, par_file: pathlib.Path, out_dir: pathlib.Path) -> dict[str, np.ndarray]:
    out_dir.mkdir(parents=True, exist_ok=True)
    command = (
        f"export MAMBA_ROOT_PREFIX=~/tools/mamba; ~/tools/bin/micromamba run -n chargefw2 ~/tools/chargefw2/bin/chargefw2 "
        f"--mode charges --method {method} --par-file '{to_wsl_path(par_file)}' "
        f"--input-file '{to_wsl_path(sdf)}' --chg-out-dir '{to_wsl_path(out_dir)}'"
    )
    done = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"ChargeFW2 exited {done.returncode}: {done.stderr[-2000:]}")
    (chg,) = list(out_dir.glob("*.chg"))
    return {name: q for name, (_, q) in parse_chg(chg.read_text(encoding="utf-8")).items()}


if __name__ == "__main__":
    sys.exit("run a stage: a4, b or c (see the pre-registration)") if len(sys.argv) < 2 else None
