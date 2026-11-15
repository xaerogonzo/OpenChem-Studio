"""Objective defect scan for hypervalent structures that RDKit ACCEPTS (docs/HYPERVALENT_COVERAGE_DESIGN.md).

Runs every registry calculator, and the always-on providers, over three groups: STARS (one hypervalent centre, all
terminal ligands), EMBEDDED centres in an ordinary organic (Ph-SF5, PIDA, CH3PF4) and ordinary CONTROLS (sulfate,
DMSO, perchlorate, phosphate, ethanol, benzene). It reports only what can be called wrong WITHOUT an external
reference: a non-finite number, an exception, or a stereocentre on a molecule that cannot have one. It says nothing
about a number that merely looks odd; that needs an oracle (see tests/test_hypervalent_calculators.py).

    uv run --no-sync python benchmarks/hypervalent/defect_scan.py

Needs a JRE on PATH for the naming calculators (the managed one: see services/java_setup.py).
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
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.bootstrap import build_service_container
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers
from openchem.domain.calculator import CalculationRefusal, RegistryExecution

container = build_service_container()
registry = container.descriptor_service._calculator_registry
defs = [d for c in registry.categories() for d in registry.by_category(c) if isinstance(d.execution, RegistryExecution)]

PANEL = {
    # stars
    "SF6": "FS(F)(F)(F)(F)F", "PF5": "FP(F)(F)(F)F", "XeF4": "F[Xe](F)(F)F", "XeF2": "F[Xe]F", "SF4": "FS(F)(F)F",
    "IF5": "FI(F)(F)(F)F", "PCl5": "ClP(Cl)(Cl)(Cl)Cl",
    # embedded centres
    "PhSF5": "FS(F)(F)(F)(F)c1ccccc1", "PIDA": "CC(=O)OI(OC(C)=O)c1ccccc1", "CH3PF4": "CP(F)(F)(F)F",
    # ordinary controls
    "sulfate": "[O-]S(=O)(=O)[O-]", "DMSO": "CS(C)=O", "perchlorate": "[O-]Cl(=O)(=O)=O", "TMP": "COP(=O)(OC)OC",
    "ethanol": "CCO", "benzene": "c1ccccc1",
}


def nonfinite(obj, depth=0):
    if depth > 3:
        return False
    if isinstance(obj, float):
        return not math.isfinite(obj)
    if isinstance(obj, dict):
        return any(nonfinite(v, depth + 1) for v in obj.values())
    return False


def chiral_in(result):
    report = getattr(result, "report", result)
    for fact in getattr(report, "facts", []) or []:
        label = str(getattr(fact, "label", ""))
        if "hiral" in label or "tereocent" in label or "symmetric atom" in label.lower():
            value = str(getattr(fact, "display_value", ""))
            if value.strip() not in ("0", "", "None", "none"):
                return f"{label}={value}"
    return None


for name, smiles in PANEL.items():
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print(f"{name:12} not parsed by RDKit")
        continue
    try:
        mol3d = search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions(max_embeddings=10, embedding_batch_size=5)).pool[0][0]
    except Exception as e:  # noqa: BLE001
        mol3d = None
        print(f"{name:12} 3D unavailable: {str(e)[:60]}")
    counts = {"ok": 0, "refused": 0, "error": 0}
    flags = []
    for d in defs:
        params = {p.name: p.default for p in d.parameters}
        use = mol3d if (mol3d is not None) else mol
        try:
            result = registry.compute(d.calculator_id, use, "u", params)
        except CalculationRefusal:
            counts["refused"] += 1
            continue
        except Exception as e:  # noqa: BLE001
            counts["error"] += 1
            flags.append(f"{d.calculator_id}:EXC {type(e).__name__}")
            continue
        p = getattr(getattr(result, "provenance", None), "parameters", {}) or {}
        if p.get("refusal"):
            counts["refused"] += 1
            continue
        counts["ok"] += 1
        if nonfinite(getattr(result, "values", None)):
            flags.append(f"{d.calculator_id}:NaN/inf")
        report = getattr(result, "report", result)
        for fact in getattr(report, "facts", []) or []:
            if "nan" in str(getattr(fact, "display_value", "")).lower():
                flags.append(f"{d.calculator_id}:fact NaN")
                break
        c = chiral_in(result)
        if c:
            flags.append(f"{d.calculator_id}:{c}")
    print(f"{name:12} ok={counts['ok']:2} refused={counts['refused']:2} error={counts['error']:2}  flags: {'; '.join(flags) or '-'}")


# --- the always-on providers (their per-atom Gasteiger dataset is what Properties shows) ---
from openchem.chem.descriptor_providers import RDKitDescriptorProvider

print()
provider = RDKitDescriptorProvider()
for name, smiles in PANEL.items():
    mol = Chem.MolFromSmiles(smiles)
    bad = [v.descriptor_id for v in provider.compute(mol, "u") if isinstance(v.value, float) and not math.isfinite(v.value)]
    for dataset in provider.compute_per_atom(mol, "u"):
        values = list(getattr(dataset, "values", {}).values())
        if any(isinstance(x, float) and not math.isfinite(x) for x in values):
            bad.append(f"per-atom:{dataset.property_id}")
    print(f"{name:12} always-on non-finite: {bad or '-'}")
