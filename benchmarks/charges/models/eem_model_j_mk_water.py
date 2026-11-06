"""The water check of section 17 (the panel has no water, so the check could not be read from it): Merz-Kollman charges of water by `eem_model_j_mk`, same level and scheme."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys

import numpy as np
from rdkit import Chem, RDLogger

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    spec = importlib.util.spec_from_file_location("model_j_mk_water_reuse", HERE / "eem_model_j_mk.py")
    mk = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mk
    spec.loader.exec_module(mk)
    panel = mk._load("model_j_panel_water_reuse", "eem_model_j_panel.py")
    c5 = panel._load_c5()
    c5.lower_priority()
    RDLogger.DisableLog("rdApp.*")
    mol = c5.embedded("O")
    elements = [a.GetSymbol() for a in mol.GetAtoms()]
    coords = mol.GetConformer().GetPositions()
    points = mk.shell_points(elements, coords)
    scratch = pathlib.Path(r"D:\_scratch\openchem-eem-mk-water")
    potential = mk.run_job(c5, scratch, "water", mol, points)
    q = mk.fit_charges(coords / mk.BOHR, points / mk.BOHR, potential, 0.0)
    low, high = mk.WATER_OXYGEN_RANGE
    result = {"charges": [float(x) for x in q], "oxygen": float(q[0]), "in_registered_range": bool(low <= q[0] <= high), "range": [low, high]}
    (HERE / "eem_second_models_results" / "model_j_mk_water.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(scratch, ignore_errors=True)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
