"""Second PLECscore pose-ranking test: the same poses, inputs built the way the model was trained.

    uv run --no-sync python benchmarks/docking/run_plec_test_2.py inputs  --out bench-out/plec
    uv run --no-sync python benchmarks/docking/run_plec_test_2.py rescore --out bench-out/plec \
        --oddt-python D:/_scratch/oddt-venv/Scripts/python.exe --descs plecscore_descs_p5_l1.csv.gz
    uv run --no-sync python benchmarks/docking/run_plec_test_2.py report  --out bench-out/plec

`--out` is the folder the FIRST test's `run_plec_test.py dock` filled (each receptor's
`poses.json`); the docking is not repeated, so both tests rank the very same nine poses. Frozen
by `PREREGISTRATION_PLEC2.md`; the counting rules are `plec_core.py`.

`inputs` rebuilds what the first test fed PLECscore wrongly (see the preregistration):
  * each pose: heavy-atom coordinates from Vina, bond orders, charges and EVERY hydrogen from the
    ligand's chemical-component SMILES (neutral, as the model's training ligands mostly were),
    never from the PDBQT Vina wrote, which keeps no bond orders, no charges and no non-polar H;
  * the crystal ligand, built the same way from its coordinates (the control);
  * the receptor: the object Open Babel prepared (waters and the box-defining residue stripped,
    hydrogens added at pH 7.4) written out BEFORE it is turned into a PDBQT.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import plec_core as core  # noqa: E402
import prep_box_core as survey_core  # noqa: E402
import prep_box_survey as survey  # noqa: E402
from _config import vina_executable  # noqa: E402
from openchem.chem.binding_site import box_from_ligand  # noqa: E402
from openchem.chem.docking_providers import VinaDockingProvider  # noqa: E402
from openchem.chem.receptor_library import RECEPTOR_LIBRARY, find  # noqa: E402
from openchem.services.receptor_library_service import fetch_structure  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem, rdDetermineBonds  # noqa: E402

ARM = "app"
RUNNER = pathlib.Path(__file__).resolve().parent / "plec_rescore_runner_2.py"
SURVEY_ROWS = pathlib.Path(__file__).resolve().parent / "artifacts_prep_box" / "results.jsonl"


def on_template(template_heavy, heavy_pose):
    """The pose's heavy atoms with the template's bond orders, charges and every hydrogen.

    Open Babel's PDBQT keeps neither bond orders nor non-polar hydrogens, and ODDT's atom
    description reads the hydrogen count, the charge and the aromatic flag of every atom, so a
    ligand rebuilt from the PDBQT is a different molecule to the model. Radicals and implicit
    flags that the template match leaves behind are cleared before the hydrogens are added.
    """
    mol = AllChem.AssignBondOrdersFromTemplate(template_heavy, heavy_pose)
    for atom in mol.GetAtoms():
        atom.SetNoImplicit(False)
        atom.SetNumRadicalElectrons(0)
        atom.SetNumExplicitHs(0)
    mol.UpdatePropertyCache(strict=False)
    Chem.SanitizeMol(mol)
    return Chem.AddHs(mol, addCoords=True)


def heavy_pose(block: str):
    mol = Chem.MolFromMolBlock(block, sanitize=False, removeHs=False)
    mol = Chem.RemoveHs(mol, sanitize=False)
    mol.UpdatePropertyCache(strict=False)
    Chem.SanitizeMol(mol, Chem.SANITIZE_ALL ^ Chem.SANITIZE_PROPERTIES, catchErrors=True)
    return mol


def crystal_mol(structure: str, fmt: str, code: str, positions, template_heavy):
    atoms = survey.crystal_atoms(structure, fmt, code, positions)
    rw = Chem.RWMol()
    conf = Chem.Conformer(len(atoms))
    for i, (element, xyz) in enumerate(atoms):
        rw.AddAtom(Chem.Atom(element))
        conf.SetAtomPosition(i, xyz)
    mol = rw.GetMol()
    mol.AddConformer(conf)
    rdDetermineBonds.DetermineConnectivity(mol)
    return on_template(template_heavy, mol)


def prepared_receptor_pdb(provider, structure: str, fmt: str, options: dict, scratch: pathlib.Path) -> str:
    """The receptor as Open Babel prepared it for docking, hydrogens included, as a PDB.

    `_convert_receptor_to_pdbqt` does the whole preparation and then writes the PDBQT; a thin
    wrapper around `pybel` keeps the molecule it read so it can be written as a PDB instead, and
    the preparation stays one piece of code rather than a copy of it.
    """
    from openbabel import pybel

    kept = []

    class Capture:
        def __getattr__(self, name):
            real = getattr(pybel, name)
            if name != "readstring":
                return real

            def readstring(*args, **kwargs):
                molecule = real(*args, **kwargs)
                kept.append(molecule)
                return molecule

            return readstring

    provider._convert_receptor_to_pdbqt(Capture(), structure, fmt, scratch / "unused.pdbqt", options, 7.4)
    return kept[0].write("pdb")


def build_one(provider, pdb_id: str, out: pathlib.Path) -> str:
    folder = out / pdb_id
    source = folder / "poses.json"
    if not source.exists():
        return "no poses (docking never ran)"
    entry = find(pdb_id)
    structure, fmt = fetch_structure(pdb_id)
    site = box_from_ligand(structure, fmt, entry.ligand_code)
    smiles = survey.component_smiles(entry.ligand_code)
    template = Chem.MolFromSmiles(smiles) if smiles else None
    if template is None:
        return "no ligand template"
    template_heavy = Chem.RemoveHs(template)
    poses = json.loads(source.read_text(encoding="utf-8"))
    blocks = []
    for block in poses["molblocks"]:
        try:
            blocks.append(Chem.MolToMolBlock(on_template(template_heavy, heavy_pose(block))))
        except Exception:  # noqa: BLE001 - kept as None: the sidecar marks the receptor unscored
            blocks.append(None)
    crystal = crystal_mol(structure, fmt, entry.ligand_code, site.ligand_positions, template_heavy)
    options = survey.prep_options(ARM, entry.ligand_code)
    (folder / "receptor_full.pdb").write_text(
        prepared_receptor_pdb(provider, structure, fmt, options, folder), encoding="utf-8")
    (folder / "crystal.mol").write_text(Chem.MolToMolBlock(crystal), encoding="utf-8")
    (folder / "poses_proper.json").write_text(json.dumps(
        {"pdb": pdb_id, "vina": poses["vina"], "rmsd": poses["rmsd"], "molblocks": blocks}), encoding="utf-8")
    (folder / "unused.pdbqt").unlink(missing_ok=True)
    return f"{sum(b is not None for b in blocks)} of {len(blocks)} poses built"


def stage_inputs(args) -> None:
    out = pathlib.Path(args.out)
    provider = VinaDockingProvider(executable_path_resolver=lambda: vina_executable())
    targets = [t.upper() for t in args.targets] if args.targets else [e.pdb_id for e in RECEPTOR_LIBRARY]
    for pdb_id in targets:
        if (out / pdb_id / "poses_proper.json").exists():
            continue  # resumable
        try:
            print(pdb_id, build_one(provider, pdb_id, out), flush=True)
        except Exception as exc:  # noqa: BLE001 - one receptor must not end the run
            print(pdb_id, f"inputs failed: {type(exc).__name__}: {exc}"[:160], flush=True)


def stage_rescore(args) -> None:
    command = [args.oddt_python, "-I", str(RUNNER), str(pathlib.Path(args.out))]
    if args.descs:
        command.append(args.descs)
    subprocess.run(command, check=True)


def load(out: pathlib.Path):
    scores = json.loads((out / "plec_scores_2.json").read_text(encoding="utf-8"))
    receptors = []
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p / "poses.json").exists()):
        poses = json.loads((folder / "poses.json").read_text(encoding="utf-8"))
        entry = scores.get(folder.name, {})
        predicted = tuple(entry["predicted"]) if "predicted" in entry else None
        receptors.append(core.Receptor(folder.name, tuple(poses["rmsd"]), predicted))
    return receptors, scores


def survey_agreement(outcomes) -> list[str]:
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
    print(f"model: {scores.get('model')}  oddt {scores.get('oddt')}  hash: {scores.get('hash')}")
    for label, tl in (("DECIDING (not in the training set)", t), ("reported apart (in the training set)", t_trained)):
        p = core.sign_test_one_sided(tl.gained, tl.lost)
        print(f"\n{label}: {tl.measured} measured, {tl.unscored} not rescored")
        print(f"  top pose correct: Vina {tl.before_correct}, after PLEC {tl.after_correct}"
              f"  (gained {tl.gained}, lost {tl.lost}, one-sided sign p = {p:.4f})")
    shares = {pdb: e["fidelity"] for pdb, e in scores.items() if isinstance(e, dict) and "fidelity" in e}
    crystal = [e["crystal"] for e in scores.values() if isinstance(e, dict) and "crystal" in e]
    print("\nfidelity (share of the stored training fingerprint reproduced):",
          {k: f"{v:.0%}" for k, v in sorted(shares.items())})
    reproduces = core.inputs_reproduce_training(list(shares.values()))
    print(f"  median {core.median(list(shares.values()))}, gate >= {core.FIDELITY_MIN_MEDIAN} on at least "
          f"{core.FIDELITY_MIN_MEASURED} receptors: {'ok' if reproduces else 'FAILED'}")
    print(f"crystal-ligand control: median predicted pKd {core.median(crystal)} over {len(crystal)} receptors")
    deciding_receptors = [r for r in receptors if r.pdb not in core.TRAINED_ON]
    plausible = core.inputs_are_plausible(deciding_receptors)
    print(f"input sanity (median best predicted pKd >= {core.SANITY_MIN_MEDIAN_PKD}): "
          f"{'ok' if plausible else 'FAILED'}")
    final = core.verdict(t, plausible and reproduces)
    print(f"VERDICT (deciding receptors only): {final}")
    moved = [(o.pdb, o.before, o.after) for o in outcomes if o.before != o.after and o.after is not None]
    print("receptors whose top-1 call changed:", moved or "none")
    print("receptors not rescored:", [r.pdb for r in receptors if r.predicted is None] or "none")
    print("survey-agreement mismatches (Vina order, this run vs the survey):",
          survey_agreement(outcomes) or "none")
    (out / "results_2.json").write_text(json.dumps({
        "deciding": t.__dict__, "trained": t_trained.__dict__, "plausible": plausible,
        "fidelity": shares, "reproduces_training": reproduces, "crystal_median": core.median(crystal),
        "verdict": final, "sign_p": core.sign_test_one_sided(t.gained, t.lost),
    }, indent=1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in ("inputs", "rescore", "report"):
        p = sub.add_parser(name)
        p.add_argument("--out", default="bench-out/plec")
        if name == "inputs":
            p.add_argument("--targets", nargs="+", default=None)
        if name == "rescore":
            p.add_argument("--oddt-python", required=True)
            p.add_argument("--descs", default=None)
    args = parser.parse_args()
    {"inputs": stage_inputs, "rescore": stage_rescore, "report": stage_report}[args.stage](args)


if __name__ == "__main__":
    main()
