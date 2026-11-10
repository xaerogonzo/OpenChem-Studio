"""Amendment 3 of `eem_second_models_preregistration.md`: Model J against CHELPG on a panel of 36 molecules, with the shipped default EEM as the yardstick.

    uv run --no-sync python benchmarks/charges/models/eem_model_j_panel.py

Reuses the ORCA machinery of `eem_second_models_c5_c7.py` (MMFF conformer, B3LYP/6-31G*, CHELPG, 2 cores, below-normal priority, scratch removed). The unpause rule is
judged by `judge_unpause`, which is pure and tested; the committed result is `eem_second_models_results/model_j_panel.json`.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import statistics
import sys
import time

from rdkit import Chem, RDLogger

HERE = pathlib.Path(__file__).resolve().parent
MAX_MEAN_E = 0.15
MAX_RATIO_TO_YARDSTICK = 1.25
MAX_ATOM_E = 0.5

PANEL = {
    "propane": "CCC", "isobutane": "CC(C)C", "ethylene": "C=C", "acetylene": "C#C", "cyclohexane": "C1CCCCC1", "benzene": "c1ccccc1", "toluene": "Cc1ccccc1",
    "phenol": "Oc1ccccc1", "aniline": "Nc1ccccc1", "pyridine": "c1ccncc1", "imidazole": "c1c[nH]cn1", "pyrrole": "c1cc[nH]c1", "furan": "c1ccoc1", "thiophene": "c1ccsc1",
    "acetone": "CC(C)=O", "acetaldehyde": "CC=O", "acetonitrile": "CC#N", "urea": "NC(N)=O", "dimethylamine": "CNC", "trimethylamine": "CN(C)C",
    "2-propanol": "CC(O)C", "tetrahydrofuran": "C1CCOC1", "ethyl acetate": "CCOC(C)=O", "methyl formate": "COC=O", "N-methylacetamide": "CNC(C)=O",
    "nitromethane": "C[N+](=O)[O-]", "dichloromethane": "ClCCl", "bromomethane": "CBr", "chlorobenzene": "Clc1ccccc1", "fluorobenzene": "Fc1ccccc1",
    "ethanethiol": "CCS", "benzaldehyde": "O=Cc1ccccc1", "benzoic acid": "OC(=O)c1ccccc1", "acetophenone": "CC(=O)c1ccccc1",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1", "aspirin": "CC(=O)Oc1ccccc1C(=O)O", "metronidazole": "Cc1ncc([N+](=O)[O-])n1CCO",
}


def judge_unpause(mean_j: float, mean_j_common: float, mean_yardstick: float, worst_atom: float) -> dict:
    """The registered rule of section 13: all three conditions must hold."""
    a = mean_j <= MAX_MEAN_E
    b = mean_j_common <= MAX_RATIO_TO_YARDSTICK * mean_yardstick
    c = worst_atom <= MAX_ATOM_E
    return {"mean_ok": a, "ratio_ok": b, "worst_atom_ok": c, "unpause": a and b and c}


def _load_c5():
    spec = importlib.util.spec_from_file_location("c5_under_reuse", HERE / "eem_second_models_c5_c7.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    c5 = _load_c5()
    c5.lower_priority()
    RDLogger.DisableLog("rdApp.*")
    from openchem.chem import geometry_charges as gc

    c5.SCRATCH = pathlib.Path(r"D:\_scratch\openchem-eem-jpanel")
    c5.SCRATCH.mkdir(parents=True, exist_ok=True)
    started = time.time()
    rows = {}
    for name, smiles in PANEL.items():
        mol = c5.embedded(smiles)
        ref = c5.run_orca(name, mol)["chelpg"]
        heavy = [i for i, a in enumerate(mol.GetAtoms()) if a.GetSymbol() != "H"]
        j = c5.model_charges(mol, c5.J)
        dataset = gc.compute_geometry_charges(mol, "panel", {"method": gc.EEM_BULTINCK2002_PART1})
        bult = [dataset.values.get(i) for i in range(mol.GetNumAtoms())] if dataset.values else None
        rows[name] = {
            "smiles": smiles, "heavy": heavy, "chelpg": ref, "J": j, "bultinck": bult,
            "bultinck_status": getattr(dataset, "status", None) if not dataset.values else "ok",
        }
        print(f"{name}: done ({time.time() - started:.0f} s)", flush=True)

    def errors(key, subset):
        out = []
        for n in subset:
            r = rows[n]
            out.extend(abs(r[key][i] - r["chelpg"][i]) for i in r["heavy"] if r[key][i] is not None)
        return out

    accepted_j = [n for n, r in rows.items() if r["J"] is not None]
    common = [n for n in accepted_j if rows[n]["bultinck"] is not None and all(rows[n]["bultinck"][i] is not None for i in rows[n]["heavy"])]
    ej, ey = errors("J", accepted_j), errors("bultinck", common)
    ej_common = errors("J", common)
    worst = max(ej) if ej else float("nan")
    result = {
        "seed": c5.SEED, "level": "B3LYP/6-31G*", "reference": "CHELPG",
        "molecules": len(PANEL), "J_accepts": len(accepted_j), "J_refused": [n for n in PANEL if n not in accepted_j],
        "common_with_yardstick": len(common),
        "mean_abs_J": statistics.fmean(ej), "worst_atom_J": worst,
        "mean_abs_J_on_common": statistics.fmean(ej_common) if ej_common else None,
        "mean_abs_yardstick_on_common": statistics.fmean(ey) if ey else None,
        "judge": judge_unpause(statistics.fmean(ej), statistics.fmean(ej_common), statistics.fmean(ey), worst) if ey else None,
        "rows": rows, "seconds": time.time() - started,
    }
    out = HERE / "eem_second_models_results" / "model_j_panel.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(c5.SCRATCH, ignore_errors=True)
    print({k: v for k, v in result.items() if k != "rows"}, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
