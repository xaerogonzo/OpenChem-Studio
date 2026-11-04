"""G2: Vina 1.2.7 and smina-default `--score_only` on the same nine Vina poses."""

from __future__ import annotations

import pathlib
import re
import tempfile

import engine_core as core
import prep_box_survey as survey
from _config import smina_executable, vina_executable
from _smina import SminaEngine
from engine_g1_survey import G1_EXHAUSTIVENESS, G1_SEED
from engine_g5_crystal import PH
from engine_pilot import ARM_NAME, pilot_receptors
from openchem.chem.binding_site import box_from_ligand
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.receptor_library import find
from openchem.chem.vina_engine import ExecutableVinaEngine
from openchem.services.progress import ProgressHandle
from openchem.services.receptor_library_service import fetch_structure
from rdkit import Chem
from rdkit.Chem import AllChem

NUM_POSES = survey.NUM_POSES
_MODEL_RE = re.compile(r"^MODEL\s+\d+\s*\n(.*?)^ENDMDL", re.MULTILINE | re.DOTALL)


def g2_receptors() -> tuple[str, ...]:
    """The five receptors named by the preregistration: first five of the 17-receptor pilot."""
    names = tuple(pilot_receptors()[: core.G2_RECEPTOR_COUNT])
    if len(names) != core.G2_RECEPTOR_COUNT:
        raise RuntimeError(f"pilot list has {len(names)} receptors, need {core.G2_RECEPTOR_COUNT}")
    return names


def vina_pose_blocks(pdbqt: str) -> list[str]:
    """Each MODEL body as a bare PDBQT (the form `score_pose` writes as `-l`)."""
    blocks = [match.group(1).strip() + "\n" for match in _MODEL_RE.finditer(pdbqt)]
    return blocks or [pdbqt]


def _embed_ligand(pdb_id: str):
    entry = find(pdb_id)
    smiles = survey.component_smiles(entry.ligand_code)
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        raise ValueError("no usable SMILES from RCSB")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        raise ValueError("would not embed")
    AllChem.MMFFOptimizeMolecule(mol)
    return entry, mol


def measure_g2_score_only(receptors: tuple[str, ...] | None = None) -> tuple[list[dict], list[float]]:
    """Dock Vina once per receptor, then `--score_only` each pose with Vina and smina-default."""
    from openbabel import pybel

    names = receptors if receptors is not None else g2_receptors()
    provider = VinaDockingProvider(executable_path_resolver=vina_executable)
    vina_engine = ExecutableVinaEngine(vina_executable())
    smina_engine = SminaEngine(smina_executable())
    rows: list[dict] = []
    diffs: list[float] = []

    for pdb_id in names:
        try:
            entry, mol = _embed_ligand(pdb_id)
            text, fmt = fetch_structure(pdb_id)
            site = box_from_ligand(text, fmt, entry.ligand_code)
            prep = survey.prep_options(ARM_NAME, entry.ligand_code)
        except Exception as exc:  # noqa: BLE001
            rows.append({"pdb": pdb_id, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue

        with tempfile.TemporaryDirectory() as scratch_name:
            scratch = pathlib.Path(scratch_name)
            receptor_pdbqt = scratch / "receptor.pdbqt"
            ligand_pdbqt = scratch / "ligand.pdbqt"
            try:
                provider._convert_receptor_to_pdbqt(pybel, text, fmt, receptor_pdbqt, prep, PH)
                provider._convert_ligand_to_pdbqt(pybel, mol, ligand_pdbqt, PH)
                provider._require_receptor_in_box(receptor_pdbqt, site.box)
                docked = vina_engine.dock(
                    receptor_pdbqt,
                    ligand_pdbqt,
                    site.box,
                    NUM_POSES,
                    G1_EXHAUSTIVENESS,
                    G1_SEED,
                    ProgressHandle(),
                    scoring_function="vina",
                )
                poses = vina_pose_blocks(docked)
            except Exception as exc:  # noqa: BLE001
                rows.append({"pdb": pdb_id, "ligand": entry.ligand_code, "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue

            for index, block in enumerate(poses):
                pose_path = scratch / f"pose_{index}.pdbqt"
                pose_path.write_text(block, encoding="utf-8")
                row: dict = {
                    "pdb": pdb_id,
                    "ligand": entry.ligand_code,
                    "pose": index,
                    "vina": None,
                    "smina_default": None,
                    "diff": None,
                    "error": None,
                }
                try:
                    vina_score = vina_engine.score_pose(receptor_pdbqt, pose_path, site.box, "vina")
                    smina_score = smina_engine.score_pose(receptor_pdbqt, pose_path, site.box, "vina")
                except Exception as exc:  # noqa: BLE001
                    row["error"] = f"{type(exc).__name__}: {exc}"[:200]
                    rows.append(row)
                    continue
                diff = smina_score - vina_score
                row["vina"] = vina_score
                row["smina_default"] = smina_score
                row["diff"] = diff
                diffs.append(diff)
                rows.append(row)
    return rows, diffs


def run_g2_gate(receptors: tuple[str, ...] | None = None):
    """Compare Vina vs smina-default on the fixed pose set; returns gate, rows, diffs."""
    names = receptors if receptors is not None else g2_receptors()
    rows, diffs = measure_g2_score_only(names)
    errors = [r for r in rows if r.get("error")]
    if errors or not diffs:
        detail = f"{len(errors)} scoring errors" if errors else "no comparisons"
        return core.GateResult("G2", False, detail), rows, diffs
    return core.gate_g2_same_function(diffs), rows, diffs
