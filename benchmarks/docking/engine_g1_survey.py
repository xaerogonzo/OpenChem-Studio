"""G1: reproduce the prep-and-box survey's recorded top-pose distances with Vina."""

from __future__ import annotations

from engine_pilot import ARM_NAME, recorded_rows

#: Pinned in `PREREGISTRATION_ENGINE.md` and `prep_box_survey.py`.
G1_SEED = 20261029
G1_EXHAUSTIVENESS = 25


def top_pose_rmsd(row: dict) -> float | None:
    """Assignment RMSD of the top-ranked pose, or None when the run did not produce one."""
    poses = row.get("poses") or []
    if not poses:
        return None
    value = poses[0].get("rmsd")
    return None if value is None else float(value)


def recorded_g1_distances() -> dict[str, float]:
    """Top-pose distances from the committed survey (`artifacts_prep_box`), app arm, G1 seed."""
    out: dict[str, float] = {}
    for row in recorded_rows():
        if row.get("arm") != ARM_NAME or row.get("seed") != G1_SEED:
            continue
        if str(row.get("outcome", "")).startswith("setup"):
            continue
        rmsd = top_pose_rmsd(row)
        if rmsd is not None:
            out[row["pdb"]] = rmsd
    return out


def measure_g1_vina_rerun(receptors: list[str]) -> tuple[list[dict], dict[str, float]]:
    """Redock each receptor with the survey's `run_one` path and return rows plus top-pose RMSDs."""
    import prep_box_survey as survey
    from _config import vina_executable
    from openchem.chem.docking_providers import VinaDockingProvider

    provider = VinaDockingProvider(executable_path_resolver=vina_executable)
    rows: list[dict] = []
    measured: dict[str, float] = {}
    for pdb_id in receptors:
        row = survey.run_one(provider, pdb_id, ARM_NAME, G1_SEED, G1_EXHAUSTIVENESS)
        rows.append(row)
        if str(row.get("outcome", "")).startswith("setup"):
            continue
        rmsd = top_pose_rmsd(row)
        if rmsd is not None:
            measured[pdb_id] = rmsd
    return rows, measured


def run_g1_gate(receptors: list[str] | None = None):
    """Compare a fresh Vina rerun to the recorded survey; returns gate result and detail rows."""
    import engine_core as core

    recorded = recorded_g1_distances()
    if receptors is None:
        pdbs = sorted(recorded)
    else:
        pdbs = sorted(p for p in receptors if p in recorded)
    rows, measured = measure_g1_vina_rerun(pdbs)
    gate = core.gate_g1_reproduces_survey(
        [(p, recorded[p]) for p in pdbs],
        [(p, measured[p]) for p in pdbs if p in measured],
    )
    return gate, rows, recorded, measured
