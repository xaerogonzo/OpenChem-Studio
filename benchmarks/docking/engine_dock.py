"""Deciding docks for `PREREGISTRATION_ENGINE.md` (after freeze). Resume-safe jsonl."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import engine_core as core
import prep_box_survey as survey
from engine_g1_survey import G1_EXHAUSTIVENESS
from engine_judge import expected_keys, g4_dropped, g5_passed, recorded_keys
from engine_pilot import ARM_NAME, make_provider


def git_state(root: Path) -> tuple[str, bool]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--", "src/"], cwd=root, text=True
        ).strip()
    )
    return commit, dirty


def load_plan(gates_dir: Path, measurable: list[str]) -> tuple[list[str], list[str]]:
    if not g5_passed(gates_dir):
        raise SystemExit("G5 has not passed; refusing deciding docks")
    dropped = g4_dropped(gates_dir)
    deciding = list(core.deciding_ids(measurable, dropped=dropped, overlap=core.TRAINING_OVERLAP))
    return deciding, dropped


def plan_dict(deciding: list[str], dropped: list[str], n_measurable: int) -> dict:
    n = len(deciding)
    return {
        "n_measurable": n_measurable,
        "n_deciding": n,
        "dropped": dropped,
        "training_overlap": sorted(core.TRAINING_OVERLAP),
        "arms": list(core.G5_ARMS),
        "seeds": list(core.SEEDS),
        "exhaustiveness": G1_EXHAUSTIVENESS,
        "n_jobs": core.job_count(n),
        "receptors": deciding,
    }


def append_row(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def run_missing(
    out_dir: Path,
    deciding: list[str],
    *,
    commit: str,
    dirty: bool,
    arms: tuple[str, ...] | None = None,
) -> int:
    """Dock every missing (pdb, arm, seed). Returns how many jobs were run this call."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = out_dir / "results.jsonl"
    results.touch()
    rows = [
        json.loads(line)
        for line in results.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    done = recorded_keys(rows)
    wanted_arms = arms or core.G5_ARMS
    n_run = 0
    for arm in wanted_arms:
        provider = make_provider(arm)
        for pdb_id in deciding:
            for seed in core.SEEDS:
                if (pdb_id, arm, seed) in done:
                    continue
                row = survey.run_one(provider, pdb_id, ARM_NAME, seed, G1_EXHAUSTIVENESS)
                row["arm"] = arm
                row["preparation"] = ARM_NAME
                row["commit"] = commit
                row["dirty"] = dirty
                append_row(results, row)
                done.add((pdb_id, arm, seed))
                n_run += 1
                print(
                    f"{pdb_id:<5} {arm:<18} seed {seed} {row.get('outcome', ''):<36} "
                    f"{row.get('seconds', '')}s",
                    flush=True,
                )
    leftover = expected_keys(deciding) - done
    print(f"ran {n_run} this call; {len(leftover)} still missing of {core.job_count(len(deciding))}")
    return n_run
