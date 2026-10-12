"""What does each calculator cost, and which of them does a parameter change that?

Writes `results.json` beside this file. Takes about ten minutes, most of it the slow cases the
execution policy exists to catch (alignment, molecular dynamics, generated conformers).

    uv run --no-sync python benchmarks/calculator_cost/measure.py

Run through `openchem.cli.calculation` -- the Qt-free twin of the task the application runs -- so
no window is needed and what is timed is the registry path every route shares. The pkasolver and
ADMET sidecars are NOT configured here (that is what a command line sees), so those calculators
report `needs_setup` in the first section and their cost is cited from the roadmap instead.

Three sections, because each answers a different question:

* `defaults`: every registry calculator, default settings, three molecules.
* `with_inputs`: the four that only REFUSED at their defaults, re-run with real inputs. A refusal
  is fast; timing it says nothing about the calculator.
* `scaling`: the calculators whose cost depends on a parameter, at the values a model could pick.

The molecules are fixed and the conformer is seeded, so a rerun measures the same work.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

from openchem.chem.engine import ChemistryEngine
from openchem.cli import calculation as c
from openchem.domain.calculator import RegistryExecution

HERE = Path(__file__).resolve().parent

MOLECULES = {
    "ethanol": "CCO",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    # 41 heavy atoms: the largest the policy's measurements stand for (AUTO_MAX_HEAVY_ATOMS).
    "atorvastatin": "CC(C)c1c(C(=O)Nc2ccccc2)c(-c2ccccc2)c(-c2ccc(F)cc2)n1CCC(O)CC(O)CC(=O)O",
}
IBUPROFEN_AMIDE = "CC(C)Cc1ccc(cc1)C(C)C(=O)NC1CCN(CC1)c1ccc(F)cc1"
POLYOL = "OCC(O)C(O)C(O)C(O)C(O)C(O)C(O)C(O)C(O)C(O)C(O)C(O)C(O)CO"  # 14 stereocentres
POLYKETO = "O=C(CC(=O)CC(=O)CC(=O)CC(=O)CC(=O)CC(=O)CC(=O)CC(=O)C)O"
TNT = "Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]"

engine = ChemistryEngine()
registry = c.build_registry()
_models: dict[str, object] = {}


def model_for(smiles: str):
    if smiles not in _models:
        _models[smiles] = c.build_model(engine, smiles, conformer=True, seed=1)[0]
    return _models[smiles]


def timed(calculator_id: str, smiles: str, **overrides) -> dict:
    definition = registry.get(calculator_id)
    parameters = {p.name: p.default for p in definition.parameters}
    parameters.update(overrides)
    model = model_for(smiles)
    started = time.perf_counter()
    outcome = c.run_calculator(registry, engine, model, calculator_id, parameters)
    return {
        "calculator": calculator_id, "molecule": smiles, "overrides": overrides,
        "seconds": round(time.perf_counter() - started, 3), "status": outcome.status,
    }


def log(row: dict) -> dict:
    print(f"{row['calculator']:22s} {str(row['overrides']):62s} {row['seconds']:8.2f}s {row['status']}", flush=True)
    return row


results: dict = {
    "machine": {"platform": platform.platform(), "processor": platform.processor(), "python": sys.version.split()[0]},
    "defaults": [], "with_inputs": [], "scaling": [],
}

for definition in registry._definitions.values():
    if not isinstance(definition.execution, RegistryExecution) or c.runnable_reason(definition):
        continue
    for name, smiles in MOLECULES.items():
        row = log(timed(definition.calculator_id, smiles))
        row["molecule_name"] = name
        results["defaults"].append(row)

for row in [
    timed("lewis_adduct", "B", partner_smiles="[C-]#[O+]"),
    timed("lewis_adduct", MOLECULES["atorvastatin"], partner_smiles="N"),
    timed("detonation", TNT, loading_density_g_cm3=1.64, enthalpy_of_formation_kcal_mol=-16.0),
    timed("alignment_3d", MOLECULES["aspirin"], reference_smiles=MOLECULES["atorvastatin"]),
    timed("alignment_3d", MOLECULES["atorvastatin"], reference_smiles=MOLECULES["aspirin"]),
    timed("alignment_3d", MOLECULES["atorvastatin"], reference_smiles=IBUPROFEN_AMIDE),
    timed("alignment_3d", MOLECULES["atorvastatin"], reference_smiles=IBUPROFEN_AMIDE, accuracy="Accurate"),
    timed("alignment_3d", MOLECULES["atorvastatin"], reference_smiles=IBUPROFEN_AMIDE, method="Common scaffold (MCS)"),
    timed("alignment_3d", MOLECULES["atorvastatin"], reference_smiles=IBUPROFEN_AMIDE, method="Common scaffold (MCS)", accuracy="Accurate"),
    # Griffin's HLB is defined for surfactants and refuses the three panel molecules, so it is
    # timed on pentaethylene glycol monododecyl ether (C12E5) instead.
    timed("griffin_hlb", "CCCCCCCCCCCCOCCOCCOCCOCCOCCO"),
    timed("markush_enumeration", "c1ccccc1[*:1]", substituents="R1: Cl, F, Br, C, CC, O, N", max_structures=1000),
]:
    results["with_inputs"].append(log(row))

BIG = MOLECULES["atorvastatin"]
for calculator_id, smiles, name, values in [
    ("hbond_vs_ph", BIG, "ph_step", [0.5, 0.1, 0.05, 0.02, 0.01]),
    ("molecular_dynamics", BIG, "steps", [1000, 5000, 20000, 100000]),
    ("geometry_analysis", BIG, "conformer_count", [20, 200]),
    ("stereoisomers", POLYOL, "max_structures", [200, 2000, 10000]),
    ("tautomers", POLYKETO, "max_structures", [200, 2000, 10000]),
    ("resonance_forms", POLYKETO, "max_structures", [200, 2000, 10000]),
    ("steric_analysis", BIG, "conformers", [20, 200]),
]:
    for value in values:
        overrides = {name: value}
        if calculator_id == "hbond_vs_ph":
            overrides.update(ph_min=-2.0, ph_max=16.0)
        results["scaling"].append(log(timed(calculator_id, smiles, **overrides)))

# `conformer_policy` is a choice, so it is its own measurement: the same count under each policy.
for policy in ("never", "if_2d", "always"):
    for count in (20, 200):
        results["scaling"].append(log(timed("geometry_analysis", BIG, conformer_policy=policy, conformer_count=count)))

(HERE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
print("wrote", HERE / "results.json")
