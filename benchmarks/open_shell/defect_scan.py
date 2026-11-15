"""Open-shell defect scan (docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md), the companion of benchmarks/hypervalent/defect_scan.py.

Runs every registry calculator over a panel of species with unpaired electrons and prints, per species, which calculators
returned a number, refused, raised or returned a non-finite value, and (--matrix) the outcome of each calculator.
Like its companion it reports only what can be called wrong WITHOUT a reference; a number that merely looks odd needs an
oracle (benchmarks/open_shell/oracles.py).

    uv run --no-sync python benchmarks/open_shell/defect_scan.py [--matrix]
"""
import math
import os
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, ROOT)
sys.path.insert(0, str(Path(ROOT) / "tools"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["OPENCHEM_PKA_WORKER"] = "0"
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
import calculator_census as cc

cc._isolated_environment()
from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")
from openchem.bootstrap import build_service_container
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers
from openchem.domain.calculator import CalculationRefusal, RegistryExecution

container = build_service_container()
registry = container.descriptor_service._calculator_registry
defs = [d for c in registry.categories() for d in registry.by_category(c) if isinstance(d.execution, RegistryExecution)]

PANEL = {
    "O2_triplet": "[O][O]", "O2_drawn_O=O": "O=O", "methyl": "[CH3]", "hydroxyl": "[OH]", "NO": "[N]=O", "O_atom": "[O]",
    "superoxide": "[O][O-]", "CH2_carbene": "[CH2]", "NH_nitrene": "[NH]", "TEMPO": "CC1(C)CCCC(C)(C)N1[O]",
    "benzyl": "[CH2]c1ccccc1", "tBu_radical": "C[C](C)C",
    "closed_control": "CCO",
}


def nonfinite(obj, depth=0):
    if depth > 3:
        return False
    if isinstance(obj, float):
        return not math.isfinite(obj)
    if isinstance(obj, dict):
        return any(nonfinite(v, depth + 1) for v in obj.values())
    return False


matrix = {}
for name, smiles in PANEL.items():
    mol = Chem.MolFromSmiles(smiles)
    try:
        mol3d = search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions(max_embeddings=10, embedding_batch_size=5)).pool[0][0]
        conf = mol3d.GetConformer()
        note3d = "3D ok; first heavy-heavy bond %s" % (
            "%.3f A" % Chem.rdMolTransforms.GetBondLength(conf, *[(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol3d.GetBonds() if b.GetBeginAtom().GetAtomicNum() > 1 and b.GetEndAtom().GetAtomicNum() > 1][0])
            if any(b.GetBeginAtom().GetAtomicNum() > 1 and b.GetEndAtom().GetAtomicNum() > 1 for b in mol3d.GetBonds()) else "n/a")
    except Exception as e:  # noqa: BLE001
        mol3d, note3d = None, "3D FAILED: " + str(e)[:70]
    print(f"{name:14} {note3d}")
    counts = {"ok": 0, "refused": 0, "error": 0}
    flags = []
    for d in defs:
        params = {p.name: p.default for p in d.parameters}
        use = mol3d if mol3d is not None else mol
        try:
            result = registry.compute(d.calculator_id, use, "u", params)
        except CalculationRefusal as r:
            counts["refused"] += 1
            matrix.setdefault(d.calculator_id, {})[name] = "refused"
            continue
        except Exception as e:  # noqa: BLE001
            counts["error"] += 1
            flags.append(f"{d.calculator_id}:EXC {type(e).__name__}")
            matrix.setdefault(d.calculator_id, {})[name] = "EXC"
            continue
        p = getattr(getattr(result, "provenance", None), "parameters", {}) or {}
        if p.get("refusal"):
            counts["refused"] += 1
            matrix.setdefault(d.calculator_id, {})[name] = "refused"
            continue
        counts["ok"] += 1
        matrix.setdefault(d.calculator_id, {})[name] = "ok"
        if nonfinite(getattr(result, "values", None)):
            flags.append(f"{d.calculator_id}:NaN/inf")
            matrix[d.calculator_id][name] = "NaN"
    print(f"   ok={counts['ok']:2} refused={counts['refused']:2} error={counts['error']:2}  flags: {'; '.join(flags) or '-'}")

if "--matrix" in sys.argv:
    cols = list(PANEL)
    print()
    print("calculator".ljust(34), " ".join(c[:7].ljust(7) for c in cols))
    for cid in sorted(matrix):
        print(cid.ljust(34), " ".join(matrix[cid].get(c, "-")[:7].ljust(7) for c in cols))
