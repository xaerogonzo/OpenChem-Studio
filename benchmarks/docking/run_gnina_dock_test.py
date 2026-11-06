"""Frozen gnina default dock vs Vina (`PREREGISTRATION_GNINA_DOCK.md`).

    uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py list
    uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py gates
    uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py vina_dock
    uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py search
    uv run --no-sync python benchmarks/docking/run_gnina_dock_test.py report

`list` and `gates` start no catalog gnina search. `vina_dock` is Vina only.
`search` is the first catalog gnina dock and must not run before freeze.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import gnina_dock_core as core  # noqa: E402
import prep_box_core as survey_core  # noqa: E402
import prep_box_survey as survey  # noqa: E402
import run_gnina_test as rescore_run  # noqa: E402
import run_plec_test as plec_run  # noqa: E402

OUT_DEFAULT = "benchmarks/docking/artifacts_gnina_dock"


def _wsl_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    return "/mnt/" + drive + resolved.as_posix()[len(resolved.drive) :]


def cmd_list(_args: argparse.Namespace) -> None:
    meas = rescore_run.measurable_receptors()
    deciding = list(core.deciding_ids(meas))
    plan = {
        "n_measurable": len(meas),
        "n_overlap": len(core.TRAINING_OVERLAP),
        "n_deciding": len(deciding),
        "overlap": sorted(core.TRAINING_OVERLAP),
        "deciding": deciding,
        "seed": core.SEED,
        "exhaustiveness": core.EXHAUSTIVENESS,
        "num_modes": core.NUM_MODES,
        "cnn_scoring": core.CNN_SCORING,
        "score_only": core.SCORE_ONLY,
    }
    print(json.dumps(plan, indent=2))
    print(
        f"{plan['n_deciding']} deciding; gnina default dock "
        f"(--cnn_scoring {plan['cnn_scoring']}, no --score_only)",
        flush=True,
    )


def cmd_gates(_args: argparse.Namespace) -> None:
    ver = rescore_run.wsl(f"{rescore_run.GNINA_WSL} --version", timeout=120)
    help_p = rescore_run.wsl(f"{rescore_run.GNINA_WSL} --help", timeout=180)
    gpu = rescore_run.wsl("nvidia-smi -L", timeout=60)
    version_text = (ver.stdout or "") + (ver.stderr or "")
    help_text = (help_p.stdout or "") + (help_p.stderr or "")
    gpu_text = gpu.stdout or ""
    report = {
        "version_pinned": core.version_is_pinned(version_text),
        "help_default_rescore": core.help_default_is_rescore(help_text),
        "gpu_ok": "4060" in gpu_text,
        "binary_ok": rescore_run.GNINA_WIN.is_file()
        and rescore_run.GNINA_WIN.stat().st_size == rescore_run.core.GNINA_ASSET_BYTES,
        "score_only": core.SCORE_ONLY,
    }
    print(json.dumps(report, indent=2))
    if not all(
        [
            report["version_pinned"],
            report["help_default_rescore"],
            report["gpu_ok"],
            report["binary_ok"],
            report["score_only"] is False,
        ]
    ):
        raise SystemExit("gates failed")


def cmd_vina_dock(args: argparse.Namespace) -> None:
    from _config import vina_executable
    from openchem.chem.docking_providers import VinaDockingProvider

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    provider = VinaDockingProvider(executable_path_resolver=lambda: vina_executable())
    targets = [t.upper() for t in args.targets] if args.targets else rescore_run.measurable_receptors()
    for pdb_id in targets:
        if (out / pdb_id / "poses.json").exists():
            continue
        print(pdb_id, plec_run.dock_one(provider, pdb_id, out), flush=True)


def _write_start_ligand(folder: pathlib.Path, pdb_id: str) -> tuple[pathlib.Path, dict]:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.chem.binding_site import box_from_ligand

    entry = plec_run.find(pdb_id)
    text, fmt = plec_run.fetch_structure(pdb_id)
    site = box_from_ligand(text, fmt, entry.ligand_code)
    smiles = survey.component_smiles(entry.ligand_code)
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        raise RuntimeError("no ligand SMILES")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        raise RuntimeError("ligand would not embed")
    AllChem.MMFFOptimizeMolecule(mol)
    lig = folder / "ligand.sdf"
    writer = Chem.SDWriter(str(lig))
    writer.write(mol)
    writer.close()
    box = {"center": list(site.box.center), "size": list(site.box.size)}
    (folder / "box.json").write_text(json.dumps(box) + "\n", encoding="utf-8")
    crystal = survey.crystal_atoms(text, fmt, entry.ligand_code, site.ligand_positions)
    return lig, {"crystal": crystal, "box": box}


def cmd_search(args: argparse.Namespace) -> None:
    from rdkit import Chem

    out = pathlib.Path(args.out)
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p / "poses.json").exists()):
        if (folder / "gnina.json").exists():
            continue
        rec = folder / "receptor.pdb"
        if not rec.is_file():
            continue
        try:
            _write_start_ligand(folder, folder.name)
        except Exception as exc:  # noqa: BLE001
            print(folder.name, f"unscored ({type(exc).__name__}: {exc})", flush=True)
            continue
        box = json.loads((folder / "box.json").read_text(encoding="utf-8"))
        cx, cy, cz = box["center"]
        sx, sy, sz = box["size"]
        wsl_out = _wsl_path(folder)
        cmd = (
            f"{rescore_run.GNINA_WSL} -r {wsl_out}/receptor.pdb -l {wsl_out}/ligand.sdf "
            f"--center_x {cx} --center_y {cy} --center_z {cz} "
            f"--size_x {sx} --size_y {sy} --size_z {sz} "
            f"--exhaustiveness {core.EXHAUSTIVENESS} --num_modes {core.NUM_MODES} "
            f"--seed {core.SEED} --cnn_scoring {core.CNN_SCORING} --device 0 "
            f"-o {wsl_out}/gnina_poses.sdf > {wsl_out}/gnina.out 2>&1"
        )
        if "--score_only" in cmd:
            raise SystemExit("search command must not pass --score_only")
        rescore_run.wsl(cmd, timeout=1800)
        sdf = folder / "gnina_poses.sdf"
        if not sdf.is_file():
            print(folder.name, "unscored (no sdf)", flush=True)
            continue
        entry = plec_run.find(folder.name)
        text, fmt = plec_run.fetch_structure(folder.name)
        from openchem.chem.binding_site import box_from_ligand

        site = box_from_ligand(text, fmt, entry.ligand_code)
        crystal = survey.crystal_atoms(text, fmt, entry.ligand_code, site.ligand_positions)
        suppl = Chem.SDMolSupplier(str(sdf), sanitize=False, removeHs=False)
        rmsds = []
        for mol in suppl:
            if mol is None:
                continue
            conf = mol.GetConformer()
            atoms = [
                (a.GetSymbol(), tuple(conf.GetAtomPosition(a.GetIdx())))
                for a in mol.GetAtoms()
                if a.GetSymbol() != "H"
            ]
            rmsds.append(survey_core.assignment_rmsd(atoms, crystal) if crystal else None)
        (folder / "gnina.json").write_text(
            json.dumps({"pdb": folder.name, "rmsd": rmsds, "n": len(rmsds)}) + "\n",
            encoding="utf-8",
        )
        print(folder.name, "docked", len(rmsds), flush=True)


def load(out: pathlib.Path) -> list[core.DockReceptor]:
    receptors = []
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p / "poses.json").exists()):
        vina = json.loads((folder / "poses.json").read_text(encoding="utf-8"))
        gnina_path = folder / "gnina.json"
        gnina_rmsds = None
        if gnina_path.is_file():
            gnina = json.loads(gnina_path.read_text(encoding="utf-8"))
            if gnina.get("rmsd"):
                gnina_rmsds = tuple(gnina["rmsd"])
        receptors.append(core.DockReceptor(folder.name, tuple(vina["rmsd"]), gnina_rmsds))
    return receptors


def cmd_report(args: argparse.Namespace) -> None:
    out = pathlib.Path(args.out)
    receptors = load(out)
    outcomes = [core.judge_dock(r) for r in receptors]
    deciding = [o for o in outcomes if o.pdb not in core.TRAINING_OVERLAP]
    trained = [o for o in outcomes if o.pdb in core.TRAINING_OVERLAP]
    t, t_tr = core.tally(deciding), core.tally(trained)
    v = core.verdict(t, plausible=True)
    print(f"cnn_scoring={core.CNN_SCORING}  score_only={core.SCORE_ONLY}")
    for label, tl in (("DECIDING (not in CrossDocked2020 index)", t), ("reported apart (overlap)", t_tr)):
        p = core.sign_test_one_sided(tl.gained, tl.lost)
        print(f"\n{label}: {tl.measured} measured, {tl.unscored} not docked by gnina")
        print(
            f"  top pose correct: Vina {tl.before_correct}, after gnina dock {tl.after_correct}"
            f"  (gained {tl.gained}, lost {tl.lost}, one-sided sign p = {p:.4g})"
        )
    print(f"\nVERDICT (deciding receptors only): {v}")
    (out / "summary.json").write_text(
        json.dumps({"deciding": t.__dict__, "overlap": t_tr.__dict__, "verdict": v}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("list")
    sub.add_parser("gates")
    vina = sub.add_parser("vina_dock")
    vina.add_argument("--out", default=OUT_DEFAULT)
    vina.add_argument("--targets", nargs="+", default=None)
    search = sub.add_parser("search")
    search.add_argument("--out", default=OUT_DEFAULT)
    report = sub.add_parser("report")
    report.add_argument("--out", default=OUT_DEFAULT)
    args = parser.parse_args()
    {
        "list": cmd_list,
        "gates": cmd_gates,
        "vina_dock": cmd_vina_dock,
        "search": cmd_search,
        "report": cmd_report,
    }[args.stage](args)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
