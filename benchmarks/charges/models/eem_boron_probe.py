"""A feasibility probe for boron in the EEM models (ROADMAP "parameters missing for an element"; `eem_second_models_preregistration.md` section 14).

    uv run --no-sync python benchmarks/charges/models/eem_boron_probe.py

Question: could a single boron type (electronegativity A and hardness B, 2 numbers) added to Model J's table reproduce ORCA's CHELPG charges on boron compounds as well as Model J
reproduces them on its own elements (0.134 e mean absolute, `model_j_panel.json`)? Everything but boron is Model J's, unchanged; boron's two numbers are fitted to the CHELPG charges of
16 compounds; the score is leave-one-molecule-out, so no compound is predicted by a fit that saw it. This is a probe: the numbers it finds ship nowhere (see the section).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import statistics
import sys
import time

import numpy as np
from rdkit import Chem, RDLogger
from scipy.optimize import least_squares

HERE = pathlib.Path(__file__).resolve().parent

PANEL = {
    "borane": "[BH3]", "boron trifluoride": "FB(F)F", "boron trichloride": "ClB(Cl)Cl", "boric acid": "OB(O)O", "trimethyl borate": "COB(OC)OC", "trimethylborane": "CB(C)C",
    "methylboronic acid": "CB(O)O", "phenylboronic acid": "OB(O)c1ccccc1", "boramide": "NB(N)N", "aminoborane": "N=B", "methyldifluoroborane": "CB(F)F",
    "ammonia borane": "[BH3-][NH3+]", "dimethylamine borane": "C[NH2+]C.[BH3-]", "tetrafluoroborate": "F[B-](F)(F)F", "borohydride": "[BH4-]", "borazine": "B1NBNBN1",
}
# dimethylamine borane as one fragment, not two
PANEL["dimethylamine borane"] = "C[NH+](C)[BH3-]"
MODEL = "jirouskova2009_b3lyp_mk"


def _load_c5():
    spec = importlib.util.spec_from_file_location("c5_under_reuse", HERE / "eem_second_models_c5_c7.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def solve(types, coords, net, boron, entry):
    """Model J's EEM with boron's (A, B) given, everything else from the table."""
    from openchem.chem import typed_eem as te

    override = [tuple(boron) if t.startswith("B") else tuple(entry["types"][t]) for t in types]
    matrix, rhs = te.typed_system(types, coords, MODEL, net, override)
    return np.linalg.solve(matrix, rhs)[: len(types)]


def mean_abs(model, reference, idx):
    return statistics.fmean(abs(model[i] - reference[i]) for i in idx)


def main() -> int:
    c5 = _load_c5()
    c5.lower_priority()
    RDLogger.DisableLog("rdApp.*")
    from openchem.chem import typed_eem as te

    entry = te.parameters()[MODEL]
    c5.SCRATCH = pathlib.Path(r"D:\_scratch\openchem-eem-boron")
    c5.SCRATCH.mkdir(parents=True, exist_ok=True)
    started = time.time()
    data = {}
    for name, smiles in PANEL.items():
        mol = c5.embedded(smiles)
        data[name] = {"smiles": smiles, "mol": mol}
    # ORCA needs the net charge in its input; the reused writer assumes neutral, so write it here.
    for name, row in data.items():
        mol = row["mol"]
        net = Chem.GetFormalCharge(mol)
        lines = ["! B3LYP 6-31G* CHELPG TightSCF", "%pal nprocs 2 end", f"* xyz {net} 1"]
        for atom, (x, y, z) in zip(mol.GetAtoms(), mol.GetConformer().GetPositions(), strict=True):
            lines.append(f"{atom.GetSymbol():2s} {x:14.8f} {y:14.8f} {z:14.8f}")
        lines.append("*")
        original = c5.orca_input
        c5.orca_input = lambda _m, text="\n".join(lines) + "\n": text  # noqa: B023
        try:
            row["chelpg"] = c5.run_orca(name, mol)["chelpg"]
        finally:
            c5.orca_input = original
        print(f"{name}: done ({time.time() - started:.0f} s)", flush=True)

    systems = {}
    for name, row in data.items():
        mol = row["mol"]
        kek = Chem.Mol(mol)
        Chem.Kekulize(kek, clearAromaticFlags=True)
        elements = [a.GetSymbol() for a in kek.GetAtoms()]
        bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(round(b.GetBondTypeAsDouble()))) for b in kek.GetBonds()]
        types = te.atom_types(elements, bonds)
        coords = mol.GetConformer().GetPositions()
        net = float(Chem.GetFormalCharge(mol))
        missing = sorted({t for t in types if not t.startswith("B") and t not in entry["types"]})
        systems[name] = {"types": types, "coords": coords, "net": net, "missing": missing, "ref": np.array(row["chelpg"]), "boron": [i for i, t in enumerate(types) if t.startswith("B")]}

    usable = [n for n, s in systems.items() if not s["missing"]]
    refused = {n: s["missing"] for n, s in systems.items() if s["missing"]}

    def residuals(params, names):
        out = []
        for n in names:
            s = systems[n]
            out.extend(solve(s["types"], s["coords"], s["net"], params, entry) - s["ref"])
        return np.array(out)

    start = [2.6, 0.5]
    full = least_squares(residuals, start, args=(usable,))
    loo = {}
    for held in usable:
        train = [n for n in usable if n != held]
        p = least_squares(residuals, start, args=(train,)).x
        s = systems[held]
        q = solve(s["types"], s["coords"], s["net"], p, entry)
        heavy = [i for i, t in enumerate(s["types"]) if not t.startswith("H")]
        loo[held] = {"params": [float(x) for x in p], "boron_error": mean_abs(q, s["ref"], s["boron"]), "heavy_error": mean_abs(q, s["ref"], heavy), "boron_model": [float(q[i]) for i in s["boron"]], "boron_chelpg": [float(s["ref"][i]) for i in s["boron"]]}
    result = {
        "model": MODEL, "reference": "CHELPG B3LYP/6-31G*", "molecules": len(PANEL), "usable": usable, "refused_for_other_types": refused,
        "fit_all": [float(x) for x in full.x], "fit_all_converged": bool(full.success),
        "leave_one_out_mean_heavy_error": statistics.fmean(v["heavy_error"] for v in loo.values()),
        "leave_one_out_mean_boron_error": statistics.fmean(v["boron_error"] for v in loo.values()),
        "leave_one_out_worst_boron_error": max(v["boron_error"] for v in loo.values()),
        "model_j_reference_mean_heavy_error": 0.134, "loo": loo,
        "boron_chelpg_range": [min(min(v["boron_chelpg"]) for v in loo.values()), max(max(v["boron_chelpg"]) for v in loo.values())],
        "parameter_spread_over_loo": {"A": float(np.std([v["params"][0] for v in loo.values()])), "B": float(np.std([v["params"][1] for v in loo.values()]))},
        "seconds": time.time() - started,
    }
    (HERE / "eem_second_models_results" / "boron_probe.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(c5.SCRATCH, ignore_errors=True)
    print({k: v for k, v in result.items() if k != "loo"}, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
