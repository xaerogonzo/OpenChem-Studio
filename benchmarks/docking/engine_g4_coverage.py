"""G4: every arm docks enough of the measurable catalog; failures drop paired."""

from __future__ import annotations

import engine_core as core
import prep_box_survey as survey
from engine_g1_survey import G1_EXHAUSTIVENESS, G1_SEED
from engine_pilot import ARM_NAME, make_provider


def dock_ok(row: dict) -> bool:
    if str(row.get("outcome", "")).startswith("setup"):
        return False
    return bool(row.get("poses"))


def measure_g4_coverage(
    receptors: list[str],
    *,
    arms: tuple[str, ...] = core.G5_ARMS,
) -> tuple[list[dict], dict[str, int], frozenset[str]]:
    """One dock per arm and receptor (G1 seed). Returns rows, successes per arm, paired drops."""
    rows: list[dict] = []
    failed: dict[str, set[str]] = {arm: set() for arm in arms}
    for pdb_id in receptors:
        for arm in arms:
            try:
                row = survey.run_one(
                    make_provider(arm), pdb_id, ARM_NAME, G1_SEED, G1_EXHAUSTIVENESS
                )
            except Exception as exc:  # noqa: BLE001
                row = {
                    "pdb": pdb_id,
                    "arm": arm,
                    "outcome": "setup: dock",
                    "detail": f"{type(exc).__name__}: {exc}"[:200],
                    "poses": [],
                }
            row = {**row, "engine_arm": arm}
            rows.append(row)
            if not dock_ok(row):
                failed[arm].add(pdb_id)
    dropped = frozenset().union(*failed.values()) if failed else frozenset()
    docked_per_arm = {arm: len(receptors) - len(failed[arm]) for arm in arms}
    return rows, docked_per_arm, dropped


def run_g4_gate(receptors: list[str]):
    rows, docked, dropped = measure_g4_coverage(receptors)
    population = len(receptors)
    if len(dropped) > core.G4_MAX_DROPPED:
        gate = core.GateResult(
            "G4",
            False,
            f"paired drop {len(dropped)} > {core.G4_MAX_DROPPED}: {', '.join(sorted(dropped))}",
        )
        return gate, rows, docked, dropped
    gate = core.gate_g4_coverage(docked, population)
    return gate, rows, docked, dropped
