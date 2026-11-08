"""Amendment 5 of `eem_second_models_preregistration.md`: Model J against Merz-Kollman charges computed here from ORCA's electrostatic potential.

    uv run --no-sync python benchmarks/charges/models/eem_model_j_mk.py

For each molecule of `eem_model_j_panel.PANEL`: B3LYP/6-31G* single point on the same MMFF conformer, the potential from `orca_vpot` on four shells of points around the molecule, and a
least-squares fit of point charges with the net charge as the one constraint. The pure parts (`shell_points`, `fit_charges`) are tested by `tests/test_eem_model_j_mk.py`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import time

import numpy as np
from rdkit import Chem, RDLogger

HERE = pathlib.Path(__file__).resolve().parent
ORCA_DIR = pathlib.Path(r"D:\ORCA")
BOHR = 0.529177210903
SCALES = (1.4, 1.6, 1.8, 2.0)
POINTS_PER_A2 = 5.0
VDW = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "S": 1.80, "Cl": 1.75, "Br": 1.85}
WATER_OXYGEN_RANGE = (-0.9, -0.7)
MAX_MEAN_DIFF_TO_CHELPG = 0.10


def sphere(count: int) -> np.ndarray:
    """`count` roughly even points on the unit sphere (Fibonacci lattice)."""
    k = np.arange(count) + 0.5
    phi = np.arccos(1 - 2 * k / count)
    theta = np.pi * (1 + 5**0.5) * k
    return np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)


def shell_points(elements, coords, scales=SCALES, density=POINTS_PER_A2) -> np.ndarray:
    """Points (angstrom) on the shells around the atoms: on each atom's sphere of radius scale*vdW, kept only if outside the same-scale sphere of every atom."""
    coords = np.asarray(coords, dtype=float)
    radii = np.array([VDW[e] for e in elements])
    out = []
    for scale in scales:
        scaled = radii * scale
        for i, (centre, r) in enumerate(zip(coords, scaled, strict=True)):
            count = max(int(round(density * 4 * np.pi * r * r)), 12)
            points = centre + r * sphere(count)
            distance = np.linalg.norm(points[:, None, :] - coords[None, :, :], axis=-1)
            keep = np.all(distance >= scaled[None, :] - 1e-9, axis=1)
            out.append(points[keep])
    return np.concatenate(out)


def fit_charges(coords, points, potential, net_charge: float) -> np.ndarray:
    """Charges q (e) minimising sum (V_k - sum_i q_i / r_ik)^2 subject to sum q = net_charge. Coordinates in bohr, potential in atomic units."""
    coords = np.asarray(coords, dtype=float)
    r = np.linalg.norm(points[:, None, :] - coords[None, :, :], axis=-1)
    a = 1.0 / r
    n = coords.shape[0]
    kkt = np.zeros((n + 1, n + 1))
    kkt[:n, :n] = a.T @ a
    kkt[:n, n] = 1.0
    kkt[n, :n] = 1.0
    rhs = np.concatenate([a.T @ potential, [net_charge]])
    return np.linalg.solve(kkt, rhs)[:n]


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_job(c5, folder: pathlib.Path, name: str, mol: Chem.Mol, points_angstrom: np.ndarray) -> np.ndarray:
    folder.mkdir(parents=True, exist_ok=True)
    net = Chem.GetFormalCharge(mol)
    lines = ["! B3LYP 6-31G* TightSCF", "%pal nprocs 2 end", f"* xyz {net} 1"]
    for atom, (x, y, z) in zip(mol.GetAtoms(), mol.GetConformer().GetPositions(), strict=True):
        lines.append(f"{atom.GetSymbol():2s} {x:14.8f} {y:14.8f} {z:14.8f}")
    lines.append("*")
    (folder / "job.inp").write_text("\n".join(lines) + "\n", encoding="utf-8")
    flags = 0x4000 | 0x08000000
    with open(folder / "job.out", "w", encoding="utf-8") as out:
        subprocess.run([str(ORCA_DIR / "orca.exe"), "job.inp"], cwd=folder, stdout=out, stderr=subprocess.STDOUT, creationflags=flags if os.name == "nt" else 0, timeout=900, check=False)
    if "ORCA TERMINATED NORMALLY" not in (folder / "job.out").read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError(f"ORCA did not finish {name}")
    bohr_points = points_angstrom / BOHR
    (folder / "pts.txt").write_text(f"{len(bohr_points)}\n" + "\n".join(f"{x:.10f} {y:.10f} {z:.10f}" for x, y, z in bohr_points) + "\n", encoding="utf-8")
    subprocess.run([str(ORCA_DIR / "orca_vpot.exe"), "job.gbw", "job.scfp", "pts.txt", "pot.txt"], cwd=folder, capture_output=True, creationflags=flags if os.name == "nt" else 0, timeout=900, check=True)
    rows = [line.split() for line in (folder / "pot.txt").read_text(encoding="utf-8").splitlines()[1:] if line.strip()]
    return np.array([float(r[3]) for r in rows])


def main() -> int:
    panel_mod = _load("model_j_panel_reuse", "eem_model_j_panel.py")
    c5 = panel_mod._load_c5()
    c5.lower_priority()
    RDLogger.DisableLog("rdApp.*")
    prior = json.loads((HERE / "eem_second_models_results" / "model_j_panel.json").read_text(encoding="utf-8"))
    scratch = pathlib.Path(r"D:\_scratch\openchem-eem-mk")
    scratch.mkdir(parents=True, exist_ok=True)
    started = time.time()
    rows = {}
    for name, smiles in panel_mod.PANEL.items():
        mol = c5.embedded(smiles)
        elements = [a.GetSymbol() for a in mol.GetAtoms()]
        coords = mol.GetConformer().GetPositions()
        points = shell_points(elements, coords)
        potential = run_job(c5, scratch / re.sub(r"[^A-Za-z0-9]+", "_", name), name, mol, points)
        q = fit_charges(coords / BOHR, points / BOHR, potential, float(Chem.GetFormalCharge(mol)))
        predicted = (1.0 / np.linalg.norm(points[:, None, :] / BOHR - (coords / BOHR)[None, :, :], axis=-1)) @ q
        rms = float(np.sqrt(np.mean((predicted - potential) ** 2)))
        heavy = [i for i, e in enumerate(elements) if e != "H"]
        old = prior["rows"][name]
        j = c5.model_charges(mol, c5.J)
        bult = old["bultinck"]
        rows[name] = {"smiles": smiles, "heavy": heavy, "mk": [float(x) for x in q], "chelpg": old["chelpg"], "J": j, "bultinck": bult, "points": int(len(points)), "esp_rms_au": rms, "net": float(Chem.GetFormalCharge(mol))}
        print(f"{name}: done ({time.time() - started:.0f} s)", flush=True)

    def errors(key, subset):
        return [abs(rows[n][key][i] - rows[n]["mk"][i]) for n in subset for i in rows[n]["heavy"] if rows[n][key][i] is not None]

    accepted = [n for n, r in rows.items() if r["J"] is not None]
    common = [n for n in accepted if rows[n]["bultinck"] is not None and all(rows[n]["bultinck"][i] is not None for i in rows[n]["heavy"])]
    ej, ejc, ey = errors("J", accepted), errors("J", common), errors("bultinck", common)
    sums_ok = all(abs(sum(r["mk"]) - r["net"]) < 1e-8 for r in rows.values())
    diff_chelpg = statistics.fmean(abs(r["mk"][i] - r["chelpg"][i]) for r in rows.values() for i in r["heavy"])
    water = rows.get("water")
    checks = {
        "sums_to_net_charge": sums_ok,
        "mean_abs_diff_to_chelpg": diff_chelpg, "diff_to_chelpg_ok": diff_chelpg <= MAX_MEAN_DIFF_TO_CHELPG,
        "water_oxygen": water["mk"][0] if water else None,
        "water_oxygen_ok": bool(water) and WATER_OXYGEN_RANGE[0] <= water["mk"][0] <= WATER_OXYGEN_RANGE[1],
        "worst_esp_rms_au": max(r["esp_rms_au"] for r in rows.values()),
    }
    checks["implementation_ok"] = checks["sums_to_net_charge"] and checks["diff_to_chelpg_ok"] and checks["water_oxygen_ok"]
    result = {
        "reference": "Merz-Kollman fit, B3LYP/6-31G*, ORCA potential", "molecules": len(rows), "J_accepts": len(accepted), "common_with_yardstick": len(common),
        "checks": checks, "mean_abs_J": statistics.fmean(ej), "worst_atom_J": max(ej), "mean_abs_J_on_common": statistics.fmean(ejc), "mean_abs_yardstick_on_common": statistics.fmean(ey),
        "judge": panel_mod.judge_unpause(statistics.fmean(ej), statistics.fmean(ejc), statistics.fmean(ey), max(ej)), "rows": rows, "seconds": time.time() - started,
    }
    (HERE / "eem_second_models_results" / "model_j_mk.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(scratch, ignore_errors=True)
    print({k: v for k, v in result.items() if k != "rows"}, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
