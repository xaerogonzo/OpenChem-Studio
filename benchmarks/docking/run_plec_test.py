"""Does re-ranking Vina's nine poses by PLECscore put the correct pose on top more often?

    uv run --no-sync python benchmarks/docking/run_plec_test.py dock    --out bench-out/plec
    uv run --no-sync python benchmarks/docking/run_plec_test.py rescore --out bench-out/plec \
        --oddt-python D:/_scratch/oddt-venv/Scripts/python.exe
    uv run --no-sync python benchmarks/docking/run_plec_test.py report  --out bench-out/plec

Frozen by `PREREGISTRATION_PLEC.md`; the counting rules are `plec_core.py`. Three stages
because the three pieces live in different environments: docking (the application's Vina and
Open Babel), PLECscore (ODDT, its own Python), and the arithmetic (pure).

`dock` repeats the prep-and-box survey's "app" arm exactly (same box, ligand, preparation, pinned
seed, nine poses) and SAVES what that survey did not keep: each pose's molblock and the prepared
receptor as a PDB. The survey's own recorded class for each receptor is compared with the one
this run reproduces, and any disagreement is reported rather than hidden.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import plec_core as core  # noqa: E402
import prep_box_core as survey_core  # noqa: E402
import prep_box_survey as survey  # noqa: E402
from _config import vina_executable  # noqa: E402
from openchem.chem.binding_site import BindingSiteError, box_from_ligand  # noqa: E402
from openchem.chem.docking_providers import (  # noqa: E402
    DEFAULT_EXHAUSTIVENESS,
    VinaDockingProvider,
)
from openchem.chem.pose_analysis import receptor_atoms_from_structure  # noqa: E402
from openchem.chem.receptor_library import RECEPTOR_LIBRARY, find  # noqa: E402
from openchem.services.progress import ProgressHandle  # noqa: E402
from openchem.services.receptor_library_service import fetch_structure  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402

ARM = "app"
SURVEY_ROWS = pathlib.Path(__file__).resolve().parent / "artifacts_prep_box" / "results.jsonl"
RUNNER = pathlib.Path(__file__).resolve().parent / "plec_rescore_runner.py"


def receptor_pdb_text(provider, structure: str, fmt: str, options: dict) -> str:
    """The receptor exactly as the docking run prepared it, written as a PDB with hydrogens."""
    from openbabel import pybel

    with tempfile.TemporaryDirectory() as scratch:
        pdbqt = pathlib.Path(scratch) / "receptor.pdbqt"
        provider._convert_receptor_to_pdbqt(pybel, structure, fmt, pdbqt, options, 7.4)
        molecule = next(pybel.readfile("pdbqt", str(pdbqt)))
        return molecule.write("pdb")


def dock_one(provider, pdb_id: str, out: pathlib.Path) -> str:
    entry = find(pdb_id)
    folder = out / pdb_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        text, fmt = fetch_structure(pdb_id)
        site = box_from_ligand(text, fmt, entry.ligand_code)
    except (BindingSiteError, Exception) as exc:  # noqa: BLE001
        return f"setup failed: {type(exc).__name__}"
    smiles = survey.component_smiles(entry.ligand_code)
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return "setup failed: no ligand SMILES"
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        return "setup failed: ligand would not embed"
    AllChem.MMFFOptimizeMolecule(mol)
    options = survey.prep_options(ARM, entry.ligand_code)
    poses = provider.dock(
        receptor_structure_text=text, receptor_source_format=fmt, ligand_mol=mol, box=site.box,
        num_poses=survey.NUM_POSES, progress=ProgressHandle(), receptor_prep_options=options,
        search_options={"seed": survey.SEEDS[0], "exhaustiveness": DEFAULT_EXHAUSTIVENESS},
    )
    crystal = survey.crystal_atoms(text, fmt, entry.ligand_code, site.ligand_positions)
    rmsds, blocks, vina = [], [], []
    for pose in poses:
        docked = Chem.MolFromMolBlock(pose.pose_molblock, sanitize=False)
        conf = docked.GetConformer()
        atoms = [(a.GetSymbol(), tuple(conf.GetAtomPosition(a.GetIdx())))
                 for a in docked.GetAtoms() if a.GetSymbol() != "H"]
        rmsds.append(survey_core.assignment_rmsd(atoms, crystal) if crystal else None)
        blocks.append(pose.pose_molblock)
        vina.append(pose.binding_affinity_kcal_mol)
    (folder / "receptor.pdb").write_text(receptor_pdb_text(provider, text, fmt, options))
    (folder / "poses.json").write_text(json.dumps(
        {"pdb": pdb_id, "vina": vina, "rmsd": rmsds, "molblocks": blocks}), encoding="utf-8")
    return f"{len(poses)} poses"


def stage_dock(args) -> None:
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    provider = VinaDockingProvider(executable_path_resolver=lambda: vina_executable())
    targets = [t.upper() for t in args.targets] if args.targets else [e.pdb_id for e in RECEPTOR_LIBRARY]
    for pdb_id in targets:
        if (out / pdb_id / "poses.json").exists():
            continue  # resumable: a finished receptor is never repeated
        print(pdb_id, dock_one(provider, pdb_id, out), flush=True)


def stage_rescore(args) -> None:
    subprocess.run([args.oddt_python, "-I", str(RUNNER), str(pathlib.Path(args.out))], check=True)


def load(out: pathlib.Path):
    scores = json.loads((out / "plec_scores.json").read_text(encoding="utf-8"))
    receptors = []
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p / "poses.json").exists()):
        poses = json.loads((folder / "poses.json").read_text(encoding="utf-8"))
        entry = scores.get(folder.name, {})
        predicted = tuple(entry["predicted"]) if "predicted" in entry else None
        receptors.append(core.Receptor(folder.name, tuple(poses["rmsd"]), predicted))
    return receptors, scores


def survey_agreement(outcomes) -> list[str]:
    """Receptors whose Vina-order top-1 call differs from the survey's recorded class."""
    recorded = {}
    for line in SURVEY_ROWS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["arm"] == ARM:
            recorded[row["pdb"]] = row["outcome"] == survey_core.TOP1_CORRECT
    return [o.pdb for o in outcomes
            if o.pdb in recorded and o.before is not None and o.before != recorded[o.pdb]]


def stage_report(args) -> None:
    out = pathlib.Path(args.out)
    receptors, scores = load(out)
    outcomes = [core.judge_receptor(r) for r in receptors]
    deciding = [o for o in outcomes if o.pdb not in core.TRAINED_ON]
    trained = [o for o in outcomes if o.pdb in core.TRAINED_ON]
    t, t_trained = core.tally(deciding), core.tally(trained)
    print(f"model: {scores.get('model')}  oddt {scores.get('oddt')}")
    for label, tl in (("DECIDING (not in the training set)", t), ("reported apart (in the training set)", t_trained)):
        p = core.sign_test_one_sided(tl.gained, tl.lost)
        print(f"\n{label}: {tl.measured} measured, {tl.unscored} not rescored")
        print(f"  top pose correct: Vina {tl.before_correct}, after PLEC {tl.after_correct}"
              f"  (gained {tl.gained}, lost {tl.lost}, one-sided sign p = {p:.4f})")
    deciding_receptors = [r for r in receptors if r.pdb not in core.TRAINED_ON]
    plausible = core.inputs_are_plausible(deciding_receptors)
    print(f"\ninput sanity (median best predicted pKd >= {core.SANITY_MIN_MEDIAN_PKD}): "
          f"{'ok' if plausible else 'FAILED'}")
    print(f"VERDICT (deciding receptors only): {core.verdict(t, plausible)}")
    moved = [(o.pdb, o.before, o.after) for o in outcomes if o.before != o.after and o.after is not None]
    print("receptors whose top-1 call changed:", moved or "none")
    print("survey-agreement mismatches (Vina order, this run vs the survey):",
          survey_agreement(outcomes) or "none")
    (out / "results.json").write_text(json.dumps({
        "deciding": t.__dict__, "trained": t_trained.__dict__, "plausible": plausible,
        "verdict": core.verdict(t, plausible),
        "sign_p": core.sign_test_one_sided(t.gained, t.lost),
    }, indent=1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in ("dock", "rescore", "report"):
        p = sub.add_parser(name)
        p.add_argument("--out", default="bench-out/plec")
        if name == "dock":
            p.add_argument("--targets", nargs="+", default=None)
        if name == "rescore":
            p.add_argument("--oddt-python", required=True)
    args = parser.parse_args()
    {"dock": stage_dock, "rescore": stage_rescore, "report": stage_report}[args.stage](args)


if __name__ == "__main__":
    main()
