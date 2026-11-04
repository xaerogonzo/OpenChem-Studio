"""Crystal-ligand `--score_only` for engine gate G5 (shared by probe and test runner)."""

from __future__ import annotations

import math
import pathlib
import tempfile

import prep_box_survey as survey
from _config import smina_executable, vina_executable
from _smina import SminaEngine
from engine_core import G5_ARMS, crystal_score_favorable
from engine_pilot import ARM_NAME
from openchem.chem.binding_site import box_from_ligand
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.receptor_library import find
from openchem.chem.vina_engine import ExecutableVinaEngine
from openchem.services.receptor_library_service import fetch_structure

PH = 7.4

SMINA_SCORING = {
    "smina-default": "vina",
    "smina-vinardo": "vinardo",
    "smina-dkoes_fast": "dkoes_fast",
    "smina-ad4": "ad4_scoring",
}


def build_crystal_ligand_mol(
    smiles: str,
    crystal: list[tuple[str, tuple[float, float, float]]],
):
    """RDKit ligand with heavy atoms on the boxed crystal copy (same pH path as docking)."""
    import numpy as np
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Geometry import Point3D
    from scipy.optimize import linear_sum_assignment

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("SMILES did not parse")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        raise ValueError("would not embed")
    conf = mol.GetConformer()
    heavy = [(a.GetSymbol(), a.GetIdx()) for a in mol.GetAtoms() if a.GetAtomicNum() > 1]
    crystal_h = [(element, pos) for element, pos in crystal if element != "H"]
    if len(heavy) != len(crystal_h):
        raise ValueError(f"heavy atom count {len(heavy)} != crystal {len(crystal_h)}")

    for element in {symbol for symbol, _ in heavy}:
        mol_ids = [idx for symbol, idx in heavy if symbol == element]
        positions = [pos for el, pos in crystal_h if el == element]
        if len(mol_ids) != len(positions):
            raise ValueError(f"{element}: {len(mol_ids)} vs {len(positions)}")
        coords = np.array([conf.GetAtomPosition(i) for i in mol_ids], dtype=float)
        target = np.array(positions, dtype=float)
        cost = ((coords[:, None, :] - target[None, :, :]) ** 2).sum(axis=2)
        rows, cols = linear_sum_assignment(cost)
        for row, col in zip(rows, cols, strict=True):
            x, y, z = target[col]
            conf.SetAtomPosition(mol_ids[row], Point3D(float(x), float(y), float(z)))
    return mol


def score_arm(
    arm: str,
    receptor_pdbqt: pathlib.Path,
    ligand_pdbqt: pathlib.Path,
    box,
    vina_engine: ExecutableVinaEngine,
    smina_engine: SminaEngine,
) -> tuple[float | None, str | None]:
    try:
        if arm == "vina":
            return vina_engine.score_pose(receptor_pdbqt, ligand_pdbqt, box, "vina"), None
        return smina_engine.score_pose(
            receptor_pdbqt, ligand_pdbqt, box, SMINA_SCORING[arm]
        ), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"[:200]


def suggest_min_fraction(favorable_count: int, total: int) -> float:
    """Allow one pilot receptor to fail while passing G5 on the rest."""
    if total == 0:
        return 1.0
    return max(0.0, (favorable_count - 1) / total)


def measure_g5_crystal_scores(
    receptors: list[str],
    *,
    arms: tuple[str, ...] = G5_ARMS,
) -> tuple[list[dict], dict[str, float]]:
    """Score the crystal pose on each receptor and arm; return rows and favourable fractions."""
    from openbabel import pybel

    provider = VinaDockingProvider(executable_path_resolver=vina_executable)
    vina_engine = ExecutableVinaEngine(vina_executable())
    smina_engine = SminaEngine(smina_executable())

    rows: list[dict] = []
    total = len(receptors)

    for pdb_id in receptors:
        entry = find(pdb_id)
        text, fmt = fetch_structure(pdb_id)
        site = box_from_ligand(text, fmt, entry.ligand_code)
        prep = survey.prep_options(ARM_NAME, entry.ligand_code)
        smiles = survey.component_smiles(entry.ligand_code)
        if not smiles:
            for arm in arms:
                rows.append({"pdb": pdb_id, "arm": arm, "error": "no SMILES from RCSB"})
            continue
        crystal = survey.crystal_atoms(text, fmt, entry.ligand_code, site.ligand_positions)
        try:
            ligand_mol = build_crystal_ligand_mol(smiles, crystal)
        except ValueError as exc:
            for arm in arms:
                rows.append({"pdb": pdb_id, "arm": arm, "error": str(exc)[:200]})
            continue

        with tempfile.TemporaryDirectory() as scratch_name:
            scratch = pathlib.Path(scratch_name)
            receptor_pdbqt = scratch / "receptor.pdbqt"
            ligand_pdbqt = scratch / "ligand.pdbqt"
            provider._convert_receptor_to_pdbqt(pybel, text, fmt, receptor_pdbqt, prep, PH)
            provider._convert_ligand_to_pdbqt(pybel, ligand_mol, ligand_pdbqt, PH)
            provider._require_receptor_in_box(receptor_pdbqt, site.box)

            for arm in arms:
                score, err = score_arm(
                    arm, receptor_pdbqt, ligand_pdbqt, site.box, vina_engine, smina_engine
                )
                rows.append(
                    {
                        "pdb": pdb_id,
                        "ligand": entry.ligand_code,
                        "arm": arm,
                        "score": score,
                        "favorable": crystal_score_favorable(score),
                        "error": err,
                    }
                )

    fractions: dict[str, float] = {}
    for arm in arms:
        mine = [r for r in rows if r["arm"] == arm]
        fav = sum(1 for r in mine if r.get("favorable"))
        fractions[arm] = fav / total if total else math.nan
    return rows, fractions
