"""Checks C5 and C7 of `eem_second_models_preregistration.md`: the two that need ORCA.

    uv run --no-sync python benchmarks/charges/models/eem_second_models_c5_c7.py

The panels are the ones registered in section 10 of the plan BEFORE anything ran: C5's 12 small molecules and C7's 10 sulfur and 4 phosphorus molecules. Every molecule is
the MMFF conformer the EEM models are given (single points, no optimisation), run at B3LYP/6-31G* with ORCA's CHELPG, Loewdin and Mulliken charges, on 2 cores at
below-normal priority, one job at a time, in a space-free scratch folder that is removed afterwards. Only the charges are kept (`eem_second_models_results/c5_c7.json`).

**C5, the unit of the distance.** Model J's EEM charges with r in angstrom and with r in bohr against ORCA's CHELPG charges (the nearest here to J's Merz-Kollman reference); the
mean absolute error over heavy atoms of each; the unit with the smaller error by a factor of at least 1.5 is the unit, otherwise the unit stays angstrom and the result is "not
discriminated". Model N (fitted to NPA, which ORCA cannot give here) is reported the same way for information and is NOT judged.

**C7, oxidised sulfur and phosphorus in Model N.** For the S2 and P2 atoms of the panel: |q_N - q_CHELPG|; if it exceeds 0.5 e on 3 or more molecules of a type, the plan's rule says that
type is refused. CHELPG is not Model N's NPA scheme, so the result is reported with that confound and the decision is Alex's, not the script's.
"""

from __future__ import annotations

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
from rdkit.Chem import AllChem

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESULTS = pathlib.Path(__file__).resolve().parent / "eem_second_models_results"
SCRATCH = pathlib.Path(r"D:\_scratch\openchem-eem-c5")
ORCA = pathlib.Path(r"D:\ORCA\orca.exe")
SEED = 20261030
BOHR_ANGSTROM = 0.529177210903
UNIT_FACTOR = 1.5
REFUSAL_THRESHOLD_E = 0.5
REFUSAL_MOLECULES = 3

from openchem.chem import resonance_forms as rf  # noqa: E402
from openchem.chem import typed_eem as te  # noqa: E402

J, N = te.JIROUSKOVA2009_B3LYP_MK, te.NEEMP2016_CCD_GEN_NPA

C5_PANEL = {
    "water": "O", "methanol": "CO", "ethanol": "CCO", "acetic acid": "CC(=O)O", "acetamide": "CC(N)=O", "dimethyl ether": "COC",
    "methylamine": "CN", "fluoromethane": "CF", "chloromethane": "CCl", "methanethiol": "CS", "dimethyl sulfide": "CSC", "formamide": "NC=O",
}
C7_SULFUR = {
    "dimethyl sulfone": "CS(C)(=O)=O", "dimethyl sulfoxide": "CS(C)=O", "methanesulfonamide": "CS(N)(=O)=O", "benzenesulfonamide": "NS(=O)(=O)c1ccccc1",
    "methanesulfonic acid": "CS(=O)(=O)O", "methyl methanesulfonate": "CS(=O)(=O)OC", "sulfolane": "O=S1(=O)CCCC1", "thiourea": "NC(N)=S",
    "thioacetamide": "CC(N)=S", "dimethyl sulfate": "COS(=O)(=O)OC",
}
C7_PHOSPHORUS = {
    "trimethyl phosphate": "COP(=O)(OC)OC", "dimethyl methylphosphonate": "COP(C)(=O)OC", "phosphoric acid": "OP(=O)(O)O", "trimethylphosphine oxide": "CP(C)(C)=O",
}


# --- the judging rules: pure --------------------------------------------------------------------------------------------------------------


def mean_abs_error(model: list[float], reference: list[float]) -> float:
    return statistics.fmean(abs(a - b) for a, b in zip(model, reference, strict=True))


def judge_unit(error_angstrom: float, error_bohr: float, factor: float = UNIT_FACTOR) -> dict:
    """The registered rule: the unit with the smaller error by at least `factor` is the unit; otherwise it stays angstrom and is not discriminated."""
    if error_bohr * factor <= error_angstrom:
        return {"unit": "bohr", "discriminated": True, "ratio": error_angstrom / error_bohr}
    if error_angstrom * factor <= error_bohr:
        return {"unit": "angstrom", "discriminated": True, "ratio": error_bohr / error_angstrom}
    ratio = max(error_angstrom, error_bohr) / max(min(error_angstrom, error_bohr), 1e-12)
    return {"unit": "angstrom", "discriminated": False, "ratio": ratio}


def judge_oxidised(differences: list[float], threshold: float = REFUSAL_THRESHOLD_E, needed: int = REFUSAL_MOLECULES) -> dict:
    """The registered rule: refuse the type if |model - reference| exceeds `threshold` on `needed` or more molecules."""
    over = sum(1 for d in differences if abs(d) > threshold)
    return {"molecules": len(differences), "over_threshold": over, "rule_says_refuse": over >= needed}


# --- ORCA --------------------------------------------------------------------------------------------------------------------------------


def lower_priority() -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def embedded(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = SEED
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise RuntimeError(f"cannot embed {smiles}")
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
    except Exception:  # noqa: BLE001
        pass
    return mol


def orca_input(mol: Chem.Mol) -> str:
    lines = ["! B3LYP 6-31G* CHELPG TightSCF", "%pal nprocs 2 end", "* xyz 0 1"]
    for atom, (x, y, z) in zip(mol.GetAtoms(), mol.GetConformer().GetPositions(), strict=True):
        lines.append(f"{atom.GetSymbol():2s} {x:14.8f} {y:14.8f} {z:14.8f}")
    lines.append("*")
    return "\n".join(lines) + "\n"


def parse_block(text: str, header: str, pattern: str) -> list[float]:
    start = text.rindex(header)
    values = []
    for line in text[start:].splitlines()[1:]:
        match = re.match(pattern, line)
        if match:
            values.append(float(match.group(1)))
        elif values and not line.strip().startswith("-"):
            break
    return values


def parse_orca(text: str, atoms: int) -> dict[str, list[float]]:
    found = {
        "chelpg": parse_block(text, "CHELPG Charges", r"\s*\d+\s+[A-Z][a-z]?\s+:\s+(-?\d+\.\d+)"),
        "loewdin": parse_block(text, "LOEWDIN ATOMIC CHARGES", r"\s*\d+\s+[A-Z][a-z]?\s*:\s+(-?\d+\.\d+)"),
        "mulliken": parse_block(text, "MULLIKEN ATOMIC CHARGES", r"\s*\d+\s+[A-Z][a-z]?\s*:\s+(-?\d+\.\d+)"),
    }
    for name, values in found.items():
        if len(values) != atoms:
            raise RuntimeError(f"{name}: expected {atoms} charges, read {len(values)}")
    return found


def run_orca(name: str, mol: Chem.Mol) -> dict[str, list[float]]:
    folder = SCRATCH / re.sub(r"[^A-Za-z0-9]+", "_", name)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.inp").write_text(orca_input(mol), encoding="utf-8")
    flags = 0x4000 | 0x08000000  # BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
    with open(folder / "job.out", "w", encoding="utf-8") as out:
        process = subprocess.Popen([str(ORCA), "job.inp"], cwd=folder, stdout=out, stderr=subprocess.STDOUT, creationflags=flags if os.name == "nt" else 0)
        try:
            process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            process.kill()
            raise
    text = (folder / "job.out").read_text(encoding="utf-8", errors="replace")
    if "ORCA TERMINATED NORMALLY" not in text:
        raise RuntimeError(f"ORCA did not finish {name}")
    return parse_orca(text, mol.GetNumAtoms())


# --- the checks ----------------------------------------------------------------------------------------------------------------------------


def model_charges(mol: Chem.Mol, model: str, bohr: bool = False) -> list[float] | None:
    work = Chem.Mol(mol)
    if bohr:  # r in bohr: the solver divides by the coordinates' own length unit, so hand it bohr
        conformer = work.GetConformer()
        for i, (x, y, z) in enumerate(conformer.GetPositions()):
            conformer.SetAtomPosition(i, (x / BOHR_ANGSTROM, y / BOHR_ANGSTROM, z / BOHR_ANGSTROM))
    result = rf.typed_eem_for_molecule(work, model)
    return [float(q) for q in result.charges] if result.status == "converged" else None


def main() -> None:
    lower_priority()
    RDLogger.DisableLog("rdApp.*")
    if not ORCA.exists():
        sys.exit(f"ORCA not found at {ORCA}")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    started = time.time()
    panel = {**{n: ("c5", s) for n, s in C5_PANEL.items()}, **{n: ("c7_sulfur", s) for n, s in C7_SULFUR.items()}, **{n: ("c7_phosphorus", s) for n, s in C7_PHOSPHORUS.items()}}
    data: dict[str, dict] = {}
    for name, (group, smiles) in panel.items():
        mol = embedded(smiles)
        reference = run_orca(name, mol)
        elements = [a.GetSymbol() for a in mol.GetAtoms()]
        types = list(rf.typed_eem_for_molecule(mol, N).atom_types)
        data[name] = {
            "group": group, "smiles": smiles, "elements": elements, "n_types": types, "reference": reference,
            "J_angstrom": model_charges(mol, J), "J_bohr": model_charges(mol, J, bohr=True), "N_angstrom": model_charges(mol, N), "N_bohr": model_charges(mol, N, bohr=True),
        }
        print(f"{name}: done ({time.time() - started:.0f} s)", flush=True)

    # C5
    heavy = lambda row: [i for i, e in enumerate(row["elements"]) if e != "H"]  # noqa: E731
    c5: dict[str, dict] = {}
    for model in ("J", "N"):
        errors = {"angstrom": [], "bohr": []}
        for row in data.values():
            if row["group"] != "c5" or row[f"{model}_angstrom"] is None:
                continue
            idx = heavy(row)
            for unit in errors:
                errors[unit].extend(abs(row[f"{model}_{unit}"][i] - row["reference"]["chelpg"][i]) for i in idx)
        a, b = statistics.fmean(errors["angstrom"]), statistics.fmean(errors["bohr"])
        c5[model] = {"heavy_atoms": len(errors["angstrom"]), "mean_abs_error_angstrom": a, "mean_abs_error_bohr": b, "verdict": judge_unit(a, b), "judged": model == "J"}
    # C7
    c7: dict[str, dict] = {}
    for group, element, atom_type in (("c7_sulfur", "S", "S2"), ("c7_phosphorus", "P", "P2")):
        rows = []
        for name, row in data.items():
            if row["group"] != group or row["N_angstrom"] is None:
                continue
            for i, (e, t) in enumerate(zip(row["elements"], row["n_types"], strict=True)):
                if e == element:
                    rows.append({"molecule": name, "atom": i, "type": t, "N": row["N_angstrom"][i], **{k: v[i] for k, v in row["reference"].items()}})
        diffs = [r["N"] - r["chelpg"] for r in rows]
        c7[atom_type] = {
            "atoms": rows,
            "vs_chelpg": judge_oxidised(diffs),
            "vs_loewdin": judge_oxidised([r["N"] - r["loewdin"] for r in rows]),
            "mean_N": statistics.fmean(r["N"] for r in rows) if rows else None,
            "mean_chelpg": statistics.fmean(r["chelpg"] for r in rows) if rows else None,
            "mean_loewdin": statistics.fmean(r["loewdin"] for r in rows) if rows else None,
            "mean_mulliken": statistics.fmean(r["mulliken"] for r in rows) if rows else None,
        }
    RESULTS.mkdir(exist_ok=True)
    payload = {"seed": SEED, "level": "B3LYP/6-31G*", "orca": "6.1.1", "seconds": time.time() - started, "c5": c5, "c7": c7, "molecules": data}
    (RESULTS / "c5_c7.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print(f"written {RESULTS / 'c5_c7.json'} in {time.time() - started:.0f} s; scratch removed", flush=True)


if __name__ == "__main__":
    sys.exit(main())
