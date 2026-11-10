"""Frozen gnina CNN rescore of Vina's nine poses (`PREREGISTRATION_GNINA.md`).

    uv run --no-sync python benchmarks/docking/run_gnina_test.py list
    uv run --no-sync python benchmarks/docking/run_gnina_test.py gates
    uv run --no-sync python benchmarks/docking/run_gnina_test.py dock
    uv run --no-sync python benchmarks/docking/run_gnina_test.py rescore
    uv run --no-sync python benchmarks/docking/run_gnina_test.py report

`list` and `gates` do not CNN-score catalog receptors. `dock` is Vina only (same save
path as the PLEC test). `rescore` is the first catalog CNN and must not run before freeze.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import gnina_core as core  # noqa: E402
import prep_box_core as survey_core  # noqa: E402
from engine_pilot import ARM_NAME, recorded_rows  # noqa: E402

SURVEY_ROWS = pathlib.Path(__file__).resolve().parent / "artifacts_prep_box" / "results.jsonl"
GNINA_WIN = pathlib.Path("D:/_scratch/gnina/gnina.cuda12.8.static")
GNINA_WSL = "/mnt/d/_scratch/gnina/gnina.cuda12.8.static"
CUDA_LIB = "/mnt/d/_scratch/gnina/cuda-env/lib"
WSL_CUDA = "/usr/lib/wsl/lib"


def measurable_receptors() -> list[str]:
    rows = [r for r in recorded_rows() if r["arm"] == ARM_NAME]
    return sorted({r["pdb"] for r in rows if not str(r["outcome"]).startswith("setup")})


def wsl_env() -> str:
    return (
        "export HOME=/home/main "
        f"LD_LIBRARY_PATH={CUDA_LIB}:{WSL_CUDA}"
    )


def wsl(cmd: str, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl", "-d", "Ubuntu", "--", "bash", "-lc", f"{wsl_env()}; {cmd}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def cmd_list(_args: argparse.Namespace) -> None:
    meas = measurable_receptors()
    deciding = list(core.deciding_ids(meas))
    plan = {
        "n_measurable": len(meas),
        "n_overlap": len(core.TRAINING_OVERLAP),
        "n_deciding": len(deciding),
        "overlap": sorted(core.TRAINING_OVERLAP),
        "deciding": deciding,
        "seed": core.SEED,
        "exhaustiveness": core.EXHAUSTIVENESS,
        "cnn_scoring": core.CNN_SCORING,
        "ranking": "CNNscore",
    }
    print(json.dumps(plan, indent=2))
    print(
        f"{plan['n_deciding']} deciding ({plan['n_measurable']} measurable minus "
        f"{plan['n_overlap']} CrossDocked2020 overlap)",
        flush=True,
    )


def cmd_gates(_args: argparse.Namespace) -> None:
    ver = wsl(f"{GNINA_WSL} --version", timeout=120)
    text = (ver.stdout or "") + (ver.stderr or "")
    gpu = wsl("nvidia-smi -L", timeout=60)
    gpu_text = gpu.stdout or ""
    report = {
        "version_text": text.strip(),
        "version_pinned": core.version_is_pinned(text),
        "gpu": gpu_text.strip(),
        "gpu_ok": "4060" in gpu_text,
        "binary_bytes": GNINA_WIN.stat().st_size if GNINA_WIN.is_file() else None,
        "binary_ok": GNINA_WIN.is_file() and GNINA_WIN.stat().st_size == core.GNINA_ASSET_BYTES,
    }
    print(json.dumps(report, indent=2))
    if not report["version_pinned"] or not report["gpu_ok"] or not report["binary_ok"]:
        raise SystemExit("gates failed")


def cmd_dock(args: argparse.Namespace) -> None:
    import run_plec_test as plec_run

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from _config import vina_executable
    from openchem.chem.docking_providers import VinaDockingProvider

    provider = VinaDockingProvider(executable_path_resolver=lambda: vina_executable())
    targets = [t.upper() for t in args.targets] if args.targets else measurable_receptors()
    for pdb_id in targets:
        if (out / pdb_id / "poses.json").exists():
            continue
        print(pdb_id, plec_run.dock_one(provider, pdb_id, out), flush=True)


def _write_sdf(folder: pathlib.Path) -> int:
    from rdkit import Chem

    poses = json.loads((folder / "poses.json").read_text(encoding="utf-8"))
    sdf = folder / "poses.sdf"
    writer = Chem.SDWriter(str(sdf))
    n = 0
    for block in poses["molblocks"]:
        mol = Chem.MolFromMolBlock(block, sanitize=False)
        if mol is None:
            continue
        writer.write(mol)
        n += 1
    writer.close()
    return n


def cmd_rescore(args: argparse.Namespace) -> None:
    out = pathlib.Path(args.out)
    scores: dict = {
        "model": "gnina-default-cnn",
        "cnn_scoring": core.CNN_SCORING,
        "version_needle": core.VERSION_NEEDLE,
    }
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p / "poses.json").exists()):
        rec = folder / "receptor.pdb"
        if not rec.is_file():
            continue
        n = _write_sdf(folder)
        resolved = folder.resolve()
        drive = resolved.drive.rstrip(":").lower()
        wsl_out = "/mnt/" + drive + resolved.as_posix()[len(resolved.drive) :]
        lig = f"{wsl_out}/poses.sdf"
        rec_w = f"{wsl_out}/receptor.pdb"
        log = folder / "gnina.out"
        proc = wsl(
            f"{GNINA_WSL} -r {rec_w} -l {lig} --score_only --cnn_scoring {core.CNN_SCORING} "
            f"--device 0 > {wsl_out}/gnina.out 2>&1",
            timeout=600,
        )
        text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else (proc.stdout or "")
        cnn, aff = core.parse_cnn_scores(text)
        if len(cnn) != n:
            print(folder.name, f"unscored (got {len(cnn)} CNNscore for {n} poses)", flush=True)
            continue
        if core.all_scores_tied(cnn):
            print(folder.name, "unscored (tied CNNscore)", flush=True)
            continue
        scores[folder.name] = {"predicted": cnn, "cnn_affinity": aff, "n": n}
        print(folder.name, "rescored", n, flush=True)
    (out / "cnn_scores.json").write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")


def load(out: pathlib.Path) -> tuple[list[core.Receptor], dict]:
    scores = json.loads((out / "cnn_scores.json").read_text(encoding="utf-8"))
    receptors = []
    for folder in sorted(p for p in out.iterdir() if p.is_dir() and (p / "poses.json").exists()):
        poses = json.loads((folder / "poses.json").read_text(encoding="utf-8"))
        entry = scores.get(folder.name, {})
        predicted = tuple(entry["predicted"]) if "predicted" in entry else None
        receptors.append(core.Receptor(folder.name, tuple(poses["rmsd"]), predicted))
    return receptors, scores


def cmd_report(args: argparse.Namespace) -> None:
    out = pathlib.Path(args.out)
    receptors, scores = load(out)
    outcomes = [core.judge_receptor(r) for r in receptors]
    deciding = [o for o in outcomes if o.pdb not in core.TRAINING_OVERLAP]
    trained = [o for o in outcomes if o.pdb in core.TRAINING_OVERLAP]
    t, t_tr = core.tally(deciding), core.tally(trained)
    deciding_recs = [r for r in receptors if r.pdb not in core.TRAINING_OVERLAP]
    plausible = core.inputs_are_plausible(deciding_recs)
    v = core.verdict(t, plausible)
    print(f"model: {scores.get('model')}  cnn_scoring={scores.get('cnn_scoring')}")
    for label, tl in (("DECIDING (not in CrossDocked2020 index)", t), ("reported apart (overlap)", t_tr)):
        p = core.sign_test_one_sided(tl.gained, tl.lost)
        print(f"\n{label}: {tl.measured} measured, {tl.unscored} not rescored")
        print(
            f"  top pose correct: Vina {tl.before_correct}, after CNNscore {tl.after_correct}"
            f"  (gained {tl.gained}, lost {tl.lost}, one-sided sign p = {p:.4g})"
        )
    print(f"\nCNN sanity (median max CNNscore >= {core.CNN_SANITY_MIN}): {'ok' if plausible else 'FAILED'}")
    print(f"VERDICT (deciding receptors only): {v}")
    (out / "summary.json").write_text(
        json.dumps(
            {
                "deciding": t.__dict__,
                "overlap": t_tr.__dict__,
                "plausible": plausible,
                "verdict": v,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if v == "INCONCLUSIVE" and not plausible:
        raise SystemExit("report: INCONCLUSIVE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("list")
    sub.add_parser("gates")
    dock = sub.add_parser("dock")
    dock.add_argument("--out", default="benchmarks/docking/artifacts_gnina")
    dock.add_argument("--targets", nargs="+", default=None)
    rescore = sub.add_parser("rescore")
    rescore.add_argument("--out", default="benchmarks/docking/artifacts_gnina")
    report = sub.add_parser("report")
    report.add_argument("--out", default="benchmarks/docking/artifacts_gnina")
    args = parser.parse_args()
    {
        "list": cmd_list,
        "gates": cmd_gates,
        "dock": cmd_dock,
        "rescore": cmd_rescore,
        "report": cmd_report,
    }[args.stage](args)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
