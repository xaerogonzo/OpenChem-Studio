"""Assemble gained/lost from deciding-dock rows. No docking.

`run_engine_test.py report` calls this; `tests/test_engine_judge.py` holds the
population count, completeness, and RESULT.md sentences.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import engine_core as core


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def g4_dropped(gates_dir: Path) -> list[str]:
    summary = json.loads((gates_dir / "g4_summary.json").read_text(encoding="utf-8"))
    gate = summary.get("gate") or {}
    if not gate.get("passed"):
        raise ValueError(f"G4 did not pass: {gate}")
    return [str(p).upper() for p in summary.get("dropped") or []]


def g5_passed(gates_dir: Path) -> bool:
    summary = json.loads((gates_dir / "g5_summary.json").read_text(encoding="utf-8"))
    gates = summary.get("gates") or []
    return bool(gates) and all(g.get("passed") for g in gates)


def expected_keys(deciding: Sequence[str]) -> set[tuple[str, str, int]]:
    return {(pdb, arm, seed) for pdb in deciding for arm in core.G5_ARMS for seed in core.SEEDS}


def recorded_keys(rows: Sequence[dict]) -> set[tuple[str, str, int]]:
    return {(str(r["pdb"]).upper(), str(r["arm"]), int(r["seed"])) for r in rows}


def missing_jobs(rows: Sequence[dict], deciding: Sequence[str]) -> list[tuple[str, str, int]]:
    have = recorded_keys(rows)
    return sorted(expected_keys(deciding) - have)


def records_evaluable(rows: Sequence[dict]) -> str | None:
    """Reason the rows cannot be judged together, or None."""
    commits = {r.get("commit") for r in rows if r.get("commit")}
    if len(commits) > 1:
        return f"records from {len(commits)} commits"
    if any(r.get("dirty") for r in rows):
        return "records from a dirty src/"
    return None


def receptor_arm(pdb: str, arm: str, rows: Sequence[dict]) -> core.ReceptorArm:
    by_seed = {
        int(r["seed"]): r
        for r in rows
        if str(r.get("pdb", "")).upper() == pdb.upper() and r.get("arm") == arm
    }
    seeds = tuple(core.row_top_correct(by_seed[s]) if s in by_seed else None for s in core.SEEDS)
    return core.ReceptorArm(pdb.upper(), arm, seeds)


def pair_outcomes(
    rows: Sequence[dict],
    deciding: Sequence[str],
    before_arm: str,
    after_arm: str,
) -> list[core.PairOutcome]:
    return [
        core.compare_arms(
            receptor_arm(pdb, before_arm, rows),
            receptor_arm(pdb, after_arm, rows),
        )
        for pdb in deciding
    ]


def judge(
    rows: Sequence[dict],
    deciding: Sequence[str],
    *,
    gates: Sequence[core.GateResult] | None = None,
) -> dict:
    """Primary (vs vina) and control (vs smina-default) tallies. Incomplete rows still tally known pairs."""
    missing = missing_jobs(rows, deciding)
    unevaluable = records_evaluable(rows)
    control_pairs = pair_outcomes(rows, deciding, core.REFERENCE_ARM, core.CONTROL_ARM)
    control_tally = core.tally_pairs(control_pairs)
    candidates: dict[str, dict] = {}
    primary: dict[str, str] = {}
    for arm in sorted(core.CANDIDATE_ARMS):
        vs_vina = core.tally_pairs(pair_outcomes(rows, deciding, core.REFERENCE_ARM, arm))
        vs_default = core.tally_pairs(pair_outcomes(rows, deciding, core.CONTROL_ARM, arm))
        v_vina = core.candidate_verdict(vs_vina)
        v_default = core.candidate_verdict(vs_default)
        primary[arm] = v_vina
        candidates[arm] = {
            "vs_vina": {"tally": vs_vina, "verdict": v_vina},
            "vs_default": {"tally": vs_default, "verdict": v_default},
        }
    gate_list = list(gates or [])
    overall = "NOT EVALUABLE" if unevaluable or missing else core.overall_verdict(gate_list, primary)
    return {
        "n_deciding": len(deciding),
        "n_rows": len(rows),
        "n_expected": core.job_count(len(deciding)),
        "missing": missing,
        "unevaluable": unevaluable,
        "control_is_neutral": core.control_is_neutral(control_pairs),
        "control_tally": control_tally,
        "candidates": candidates,
        "primary": primary,
        "overall_verdict": overall,
    }


def _tally_line(t: core.Tally) -> str:
    net = t.gained - t.lost
    p = core.sign_test_one_sided(t.gained, t.lost) if net >= 0 else core.sign_test_one_sided(t.lost, t.gained)
    return (
        f"compared {t.compared}, gained {t.gained}, lost {t.lost}, "
        f"unchanged {t.unchanged}, net {net:+d}, p={p:.4g}"
    )


def render_result(judged: dict, *, dropped: Sequence[str], overlap: Sequence[str]) -> str:
    lines = [
        "# Engine pose-ranking test",
        "",
        "From `PREREGISTRATION_ENGINE.md`, frozen 2026-11-04. Primary comparison is each",
        "candidate against `vina`. `smina-default` is beside it (search-code control).",
        "",
        f"Deciding receptors: {judged['n_deciding']} "
        f"(G4 dropped {', '.join(dropped) or 'none'}; "
        f"training overlap {', '.join(overlap) or 'none'}).",
        f"Rows: {judged['n_rows']} / {judged['n_expected']}.",
        "",
    ]
    if judged["unevaluable"]:
        lines += [f"**NOT EVALUABLE:** {judged['unevaluable']}.", ""]
    if judged["missing"]:
        lines += [
            f"**Incomplete:** {len(judged['missing'])} jobs not recorded. No deciding verdict.",
            "",
        ]
    ct = judged["control_tally"]
    lines += [
        "## Control (`smina-default` vs `vina`)",
        "",
        _tally_line(ct) + ".",
        f"Neutral at two-sided 0.05: **{'yes' if judged['control_is_neutral'] else 'no'}**.",
        "",
        "## Candidates (primary vs `vina`)",
        "",
        "| Arm | vs vina | vs smina-default |",
        "|---|---|---|",
    ]
    for arm in sorted(core.CANDIDATE_ARMS):
        block = judged["candidates"][arm]
        lines.append(
            f"| `{arm}` | {block['vs_vina']['verdict']} ({_tally_line(block['vs_vina']['tally'])}) "
            f"| {block['vs_default']['verdict']} ({_tally_line(block['vs_default']['tally'])}) |"
        )
    lines += [
        "",
        f"Overall (gates plus primary): **{judged['overall_verdict']}**.",
        "",
    ]
    return "\n".join(lines)


def summary_dict(judged: dict) -> dict:
    def pack(t: core.Tally) -> dict:
        return {"compared": t.compared, "gained": t.gained, "lost": t.lost, "unchanged": t.unchanged}

    return {
        "n_deciding": judged["n_deciding"],
        "n_rows": judged["n_rows"],
        "n_expected": judged["n_expected"],
        "n_missing": len(judged["missing"]),
        "unevaluable": judged["unevaluable"],
        "control_is_neutral": judged["control_is_neutral"],
        "control_tally": pack(judged["control_tally"]),
        "primary": judged["primary"],
        "candidates": {
            arm: {
                "vs_vina": {"tally": pack(b["vs_vina"]["tally"]), "verdict": b["vs_vina"]["verdict"]},
                "vs_default": {
                    "tally": pack(b["vs_default"]["tally"]),
                    "verdict": b["vs_default"]["verdict"],
                },
            }
            for arm, b in judged["candidates"].items()
        },
        "overall_verdict": judged["overall_verdict"],
    }
