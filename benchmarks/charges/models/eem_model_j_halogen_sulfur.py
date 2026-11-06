"""Amendment 6 of `eem_second_models_preregistration.md` (section 19): Model J on chlorine, bromine and sulfur, against Merz-Kollman charges computed here.

    uv run --no-sync python benchmarks/charges/models/eem_model_j_halogen_sulfur.py

26 compounds that Model J accepts (plus 3 it refuses, listed so the scope is visible). For each: B3LYP/6-31G* on the same kind of MMFF conformer as sections 13 and 17, CHELPG from that run
(only to check the implementation), and a Merz-Kollman fit from `orca_vpot` exactly as `eem_model_j_mk.py` does it. The judgement counts ONLY chlorine, bromine and sulfur atoms. The pure
`judge` is tested by `tests/test_eem_model_j_halogen_sulfur.py`.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shutil
import statistics
import sys
import time

import numpy as np
from rdkit import Chem, RDLogger

HERE = pathlib.Path(__file__).resolve().parent
SCOPE_ELEMENTS = ("Cl", "Br", "S")
MAX_MEAN_E = 0.15
MAX_RATIO_TO_N = 1.25
MAX_ATOM_E = 0.5
MAX_MEAN_DIFF_TO_CHELPG = 0.10

PANEL = {
    "chloroform": "ClC(Cl)Cl", "carbon tetrachloride": "ClC(Cl)(Cl)Cl", "chloroethane": "CCCl", "1,2-dichloroethane": "ClCCCl", "1,2-dichlorobenzene": "Clc1ccccc1Cl",
    "4-chlorophenol": "Oc1ccc(Cl)cc1", "chloroacetone": "CC(=O)CCl", "acetyl chloride": "CC(Cl)=O", "chloroacetic acid": "OC(=O)CCl", "2-chloropyridine": "Clc1ccccn1",
    "4-chloroacetanilide": "CC(=O)Nc1ccc(Cl)cc1", "vinyl chloride": "C=CCl",
    "bromobenzene": "Brc1ccccc1", "bromoethane": "CCBr", "1,2-dibromoethane": "BrCCBr", "bromoform": "BrC(Br)Br", "bromochloromethane": "BrCCl", "4-bromophenol": "Oc1ccc(Br)cc1",
    "methanethiol": "CS", "dimethyl sulfide": "CSC", "dimethyl disulfide": "CSSC", "thiophenol": "Sc1ccccc1", "thioanisole": "CSc1ccccc1", "2-chlorothiophene": "Clc1cccs1",
    "thiazole": "c1cscn1", "2-chloroethanethiol": "ClCCS",
}
#: Listed, not scored: Model J has no type for a doubly bonded or oxidised sulfur (Model N does).
REFUSED_BY_J_EXPECTED = {"dimethyl sulfoxide": "CS(C)=O", "thiourea": "NC(N)=S", "methanesulfonamide": "CS(N)(=O)=O"}


def judge(mean_j: float, worst_atom_j: float, mean_j_on_n_atoms: float, mean_n_on_same_atoms: float) -> dict:
    """The registered rule of section 19, over chlorine, bromine and sulfur atoms only: all three must hold."""
    a = mean_j <= MAX_MEAN_E
    b = worst_atom_j <= MAX_ATOM_E
    c = mean_j_on_n_atoms <= MAX_RATIO_TO_N * mean_n_on_same_atoms
    return {"mean_ok": a, "worst_atom_ok": b, "ratio_to_n_ok": c, "offer_for_these_elements": a and b and c}


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    mk = _load("model_j_mk_for_halogen", "eem_model_j_mk.py")
    panel = _load("model_j_panel_for_halogen", "eem_model_j_panel.py")
    c5 = panel._load_c5()
    c5.lower_priority()
    RDLogger.DisableLog("rdApp.*")
    c5.SCRATCH = pathlib.Path(r"D:\_scratch\openchem-eem-halogen-chelpg")
    c5.SCRATCH.mkdir(parents=True, exist_ok=True)
    scratch = pathlib.Path(r"D:\_scratch\openchem-eem-halogen-mk")
    started = time.time()
    rows = {}
    for name, smiles in PANEL.items():
        mol = c5.embedded(smiles)
        elements = [a.GetSymbol() for a in mol.GetAtoms()]
        coords = mol.GetConformer().GetPositions()
        chelpg = c5.run_orca(name, mol)["chelpg"]
        points = mk.shell_points(elements, coords)
        potential = mk.run_job(c5, scratch / re.sub(r"[^A-Za-z0-9]+", "_", name), name, mol, points)
        q = mk.fit_charges(coords / mk.BOHR, points / mk.BOHR, potential, 0.0)
        rows[name] = {
            "smiles": smiles, "elements": elements, "mk": [float(x) for x in q], "chelpg": chelpg,
            "J": c5.model_charges(mol, c5.J), "N": c5.model_charges(mol, c5.N), "points": int(len(points)),
        }
        print(f"{name}: done ({time.time() - started:.0f} s)", flush=True)

    refused = {}
    for name, smiles in REFUSED_BY_J_EXPECTED.items():
        mol = c5.embedded(smiles)
        refused[name] = {"smiles": smiles, "J_accepts": c5.model_charges(mol, c5.J) is not None, "N_accepts": c5.model_charges(mol, c5.N) is not None}

    def scope_atoms(model_key, only_accepted_by=()):
        out = []
        for name, r in rows.items():
            if r[model_key] is None or any(r[k] is None for k in only_accepted_by):
                continue
            for i, e in enumerate(r["elements"]):
                if e in SCOPE_ELEMENTS:
                    out.append((e, name, abs(r[model_key][i] - r["mk"][i])))
        return out

    j_atoms, n_atoms = scope_atoms("J"), scope_atoms("N", only_accepted_by=("J",))
    j_on_common = scope_atoms("J", only_accepted_by=("N",))
    diff_chelpg = statistics.fmean(abs(r["mk"][i] - r["chelpg"][i]) for r in rows.values() for i, e in enumerate(r["elements"]) if e != "H")
    sums_ok = all(abs(sum(r["mk"])) < 1e-8 for r in rows.values())
    checks = {"sums_to_net_charge": sums_ok, "mean_abs_diff_to_chelpg": diff_chelpg, "diff_to_chelpg_ok": diff_chelpg <= MAX_MEAN_DIFF_TO_CHELPG}
    checks["implementation_ok"] = checks["sums_to_net_charge"] and checks["diff_to_chelpg_ok"]

    def by_element(atoms):
        return {e: {"atoms": len([a for a in atoms if a[0] == e]), "mean": statistics.fmean(a[2] for a in atoms if a[0] == e), "worst": max(a[2] for a in atoms if a[0] == e)} for e in SCOPE_ELEMENTS if any(a[0] == e for a in atoms)}

    worst = max(j_atoms, key=lambda a: a[2])
    result = {
        "reference": "Merz-Kollman fit, B3LYP/6-31G*, ORCA potential", "molecules": len(rows), "scope_atoms": len(j_atoms), "checks": checks,
        "mean_abs_J": statistics.fmean(a[2] for a in j_atoms), "worst_atom_J": worst[2], "worst_atom_where": [worst[0], worst[1]],
        "mean_abs_J_on_common": statistics.fmean(a[2] for a in j_on_common), "mean_abs_N_on_common": statistics.fmean(a[2] for a in n_atoms),
        "by_element_J": by_element(j_atoms), "by_element_N": by_element(n_atoms), "refused_by_J": refused,
        "judge": judge(statistics.fmean(a[2] for a in j_atoms), worst[2], statistics.fmean(a[2] for a in j_on_common), statistics.fmean(a[2] for a in n_atoms)),
        "rows": rows, "seconds": time.time() - started,
    }
    (HERE / "eem_second_models_results" / "model_j_halogen_sulfur.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(scratch, ignore_errors=True)
    shutil.rmtree(c5.SCRATCH, ignore_errors=True)
    print({k: v for k, v in result.items() if k != "rows"}, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
