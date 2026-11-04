"""G3: one receptor, each arm and seed, two docks, pose files byte-identical."""

from __future__ import annotations

import pathlib
import tempfile

import engine_core as core
import prep_box_survey as survey
from _config import smina_executable, vina_executable
from engine_g1_survey import G1_EXHAUSTIVENESS
from engine_g2_score_only import NUM_POSES, _embed_ligand
from engine_g5_crystal import PH
from engine_pilot import ARM_NAME, FixedFunctionSmina, SMINA_ARMS
from openchem.chem.binding_site import box_from_ligand
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.vina_engine import ExecutableVinaEngine
from openchem.services.progress import ProgressHandle
from openchem.services.receptor_library_service import fetch_structure

#: Small ligand already in the G2 five; one receptor for every arm × seed pair.
G3_RECEPTOR = "7E2Y"


def arm_engine(arm: str):
    if arm == "vina":
        return ExecutableVinaEngine(vina_executable())
    return FixedFunctionSmina(smina_executable(), SMINA_ARMS[arm])


def dock_once(engine, receptor_pdbqt, ligand_pdbqt, box, seed: int) -> str:
    return engine.dock(
        receptor_pdbqt,
        ligand_pdbqt,
        box,
        NUM_POSES,
        G1_EXHAUSTIVENESS,
        seed,
        ProgressHandle(),
        scoring_function="vina",
    )


def measure_g3_repro(
    pdb_id: str = G3_RECEPTOR,
    arms: tuple[str, ...] = core.G5_ARMS,
    seeds: tuple[int, ...] = core.SEEDS,
) -> tuple[list[dict], list[str]]:
    """Two docks per arm and seed; failures are human-readable arm/seed labels."""
    from openbabel import pybel

    entry, mol = _embed_ligand(pdb_id)
    text, fmt = fetch_structure(pdb_id)
    site = box_from_ligand(text, fmt, entry.ligand_code)
    prep = survey.prep_options(ARM_NAME, entry.ligand_code)
    provider = VinaDockingProvider(executable_path_resolver=vina_executable)

    rows: list[dict] = []
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as scratch_name:
        scratch = pathlib.Path(scratch_name)
        receptor_pdbqt = scratch / "receptor.pdbqt"
        ligand_pdbqt = scratch / "ligand.pdbqt"
        provider._convert_receptor_to_pdbqt(pybel, text, fmt, receptor_pdbqt, prep, PH)
        provider._convert_ligand_to_pdbqt(pybel, mol, ligand_pdbqt, PH)
        provider._require_receptor_in_box(receptor_pdbqt, site.box)

        for arm in arms:
            engine = arm_engine(arm)
            for seed in seeds:
                row: dict = {
                    "pdb": pdb_id,
                    "arm": arm,
                    "seed": seed,
                    "byte_identical": False,
                    "error": None,
                    "bytes": None,
                }
                try:
                    first = dock_once(engine, receptor_pdbqt, ligand_pdbqt, site.box, seed)
                    second = dock_once(engine, receptor_pdbqt, ligand_pdbqt, site.box, seed)
                except Exception as exc:  # noqa: BLE001
                    row["error"] = f"{type(exc).__name__}: {exc}"[:200]
                    failures.append(f"{arm} seed {seed}: {row['error']}")
                    rows.append(row)
                    continue
                identical = first == second
                row["byte_identical"] = identical
                row["bytes"] = len(first)
                if not identical:
                    failures.append(f"{arm} seed {seed}: pose files differ ({len(first)} vs {len(second)} bytes)")
                rows.append(row)
    return rows, failures


def run_g3_gate(pdb_id: str = G3_RECEPTOR):
    rows, failures = measure_g3_repro(pdb_id)
    return core.gate_g3_reproducible(failures), rows
