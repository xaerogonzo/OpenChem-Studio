"""Frozen CNNaffinity ranking power vs Vina (`PREREGISTRATION_CNN_AFFINITY.md`).

    uv run --no-sync python benchmarks/docking/run_cnn_affinity_test.py list
    uv run --no-sync python benchmarks/docking/run_cnn_affinity_test.py gates

`list` and `gates` start no catalog CNNaffinity. `rescore` is the first
catalog score and must not run before this freeze.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cnn_affinity_core as core  # noqa: E402


def cmd_list(_args: argparse.Namespace) -> None:
    deciding = core.deciding_pdbs()
    overlap = core.overlap_pdbs()
    plan = {
        "n_ranking_series": core.n_series(sorted(core.RANKING_PDBS)),
        "n_deciding_series": core.n_series(deciding),
        "n_overlap_series": core.n_series(overlap),
        "deciding_pdbs": list(deciding),
        "overlap_pdbs": list(overlap),
        "score_only": core.SCORE_ONLY,
        "cnn_scoring": core.CNN_SCORING,
        "cnn_ensemble": list(core.CNN_ENSEMBLE),
        "cnn_higher_is_better": core.CNN_AFFINITY_HIGHER_IS_BETTER,
        "crossdocked_sha256": core.CROSSDOCKED_SET_IDS_SHA256,
    }
    print(json.dumps(plan, indent=2))
    print(
        f"{plan['n_deciding_series']} deciding series on {len(deciding)} PDBs; "
        f"{plan['n_overlap_series']} overlap series reported apart",
        flush=True,
    )


def cmd_gates(_args: argparse.Namespace) -> None:
    import run_gnina_test as pose_run

    ver = pose_run.wsl(f"{pose_run.GNINA_WSL} --version", timeout=120)
    help_p = pose_run.wsl(f"{pose_run.GNINA_WSL} --help", timeout=180)
    gpu = pose_run.wsl("nvidia-smi -L", timeout=60)
    version_text = (ver.stdout or "") + (ver.stderr or "")
    help_text = (help_p.stdout or "") + (help_p.stderr or "")
    gpu_text = gpu.stdout or ""
    report = {
        "version_pinned": pose_core_version(version_text),
        "ensemble_named": core.help_names_default_ensemble(help_text),
        "gpu_ok": "4060" in gpu_text,
        "binary_ok": pose_run.GNINA_WIN.is_file()
        and pose_run.GNINA_WIN.stat().st_size == core.GNINA_ASSET_BYTES,
        "score_only": core.SCORE_ONLY,
        "sign_predeclared": core.cnn_sign_is_predeclared(True),
    }
    print(json.dumps(report, indent=2))
    if not all(
        [
            report["version_pinned"],
            report["ensemble_named"],
            report["gpu_ok"],
            report["binary_ok"],
            report["score_only"] is True,
            report["sign_predeclared"],
        ]
    ):
        raise SystemExit("gates failed")


def pose_core_version(text: str) -> bool:
    return core.VERSION_NEEDLE in text and core.COMMIT_NEEDLE in text


def cmd_rescore(_args: argparse.Namespace) -> None:
    raise SystemExit("rescore is the first catalog CNNaffinity; do not run it before freeze")


def cmd_report(_args: argparse.Namespace) -> None:
    raise SystemExit("report needs a rescore; not in the freeze commit")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("list")
    sub.add_parser("gates")
    sub.add_parser("rescore")
    sub.add_parser("report")
    args = parser.parse_args()
    {
        "list": cmd_list,
        "gates": cmd_gates,
        "rescore": cmd_rescore,
        "report": cmd_report,
    }[args.stage](args)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
