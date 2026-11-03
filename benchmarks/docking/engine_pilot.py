"""A SMALL redock of catalogued receptors through other docking engines, as a measurement.

    set OPENCHEM_SMINA=D:\\_scratch\\dockeng\\smina-env\\Library\\bin\\smina.exe
    uv run --no-sync python benchmarks/docking/engine_pilot.py --list
    uv run --no-sync python benchmarks/docking/engine_pilot.py --arms vina smina-default
    uv run --no-sync python benchmarks/docking/engine_pilot.py --report

Written for `docs/DOCKING_ENGINE_CANDIDATES.md`. It is NOT the deciding test and decides
nothing (the draft of that test is `PREREGISTRATION_ENGINE.md`); it asks whether a second
engine runs here at all and what its numbers look like on a handful of receptors.

It changes ONE thing against `prep_box_survey.py`, the survey whose "app" arm is the
baseline: the engine. `run_one` is the survey's own, so the receptor preparation, the
box, the ligand embedding, the seed (20261029), exhaustiveness (25) and nine poses are the
same code. Each arm is the SHIPPED `VinaDockingProvider` with an engine injected.

**Why smina's scoring function is set on the engine and not through the provider.** The
provider refuses any function outside ("vina", "vinardo") before the engine is asked
(`SUPPORTED_SCORING_FUNCTIONS`); that is the seam the smina spike recorded as
`interface_change_required`. Nothing in `src/` is touched, so the arm fixes the function
inside a sibling engine class and the provider is told "vina" to get past its check. The
stored arm name, not the provider's setting, says what ran.

The pilot receptors are chosen by a RULE from the recorded survey rows, not by hand: every
measurable receptor whose top pose was not correct (the headroom), plus every seventh
top-correct receptor in catalogue order (to see losses).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import prep_box_core as core  # noqa: E402
import prep_box_survey as survey  # noqa: E402
from _config import smina_executable, vina_executable  # noqa: E402
from _smina import SminaEngine  # noqa: E402
from openchem.chem.docking_providers import VinaDockingProvider  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
RECORDED = HERE / "artifacts_prep_box" / "results.jsonl"
ARM_NAME = "app"  # the survey's own preparation arm: waters stripped, cofactors kept, pH 7.4

#: arm label -> smina's --scoring value (None = smina's default, which is Vina's function)
SMINA_ARMS = {
    "smina-default": None,
    "smina-vinardo": "vinardo",
    "smina-dkoes_fast": "dkoes_fast",
    "smina-ad4": "ad4_scoring",
}
ARMS = ("vina", *SMINA_ARMS)
EVERY_NTH_CORRECT = 7


class FixedFunctionSmina(SminaEngine):
    """smina with the scoring function fixed by the arm, whatever the provider asks for."""

    def __init__(self, executable_path: str, function: str | None) -> None:
        super().__init__(executable_path)
        self._function = function

    def dock_argv(self, *args, **kwargs):  # noqa: ANN002, ANN003
        argv = super().dock_argv(*args, **kwargs)
        if self._function:
            argv += ["--scoring", self._function]
        return argv


def recorded_rows() -> list[dict]:
    return [json.loads(x) for x in RECORDED.read_text().splitlines() if x.strip()]


def pilot_receptors() -> list[str]:
    rows = [r for r in recorded_rows() if r["arm"] == ARM_NAME]
    measurable = [r for r in rows if not r["outcome"].startswith("setup")]
    headroom = [r["pdb"] for r in measurable if r["outcome"] != core.TOP1_CORRECT]
    correct = [r["pdb"] for r in measurable if r["outcome"] == core.TOP1_CORRECT]
    return headroom + correct[::EVERY_NTH_CORRECT]


def make_provider(arm: str) -> VinaDockingProvider:
    if arm == "vina":
        return VinaDockingProvider(executable_path_resolver=lambda: vina_executable())
    return VinaDockingProvider(engine=FixedFunctionSmina(smina_executable(), SMINA_ARMS[arm]))


def top_rmsd(row: dict) -> float | None:
    poses = row.get("poses") or []
    return poses[0]["rmsd"] if poses else None


def best_rmsd(row: dict) -> float | None:
    values = [p["rmsd"] for p in row.get("poses") or [] if p["rmsd"] is not None]
    return min(values) if values else None


def report(out: pathlib.Path) -> None:
    rows = [json.loads(x) for x in (out / "results.jsonl").read_text().splitlines() if x.strip()]
    recorded = {r["pdb"]: r for r in recorded_rows() if r["arm"] == ARM_NAME}
    print(f"{'arm':<18}{'n':>3}{'top1':>6}{'best9':>7}   (2.0 A, assignment RMSD, lower bound)")
    for arm in ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        if not mine:
            continue
        top = sum(1 for r in mine if (top_rmsd(r) or 99) <= core.SUCCESS_RMSD)
        best = sum(1 for r in mine if (best_rmsd(r) or 99) <= core.SUCCESS_RMSD)
        print(f"{arm:<18}{len(mine):>3}{top:>6}{best:>7}")
    base = {r["pdb"]: r for r in rows if r["arm"] == "vina"}
    if base:
        same = [p for p, r in base.items() if p in recorded and top_rmsd(r) == top_rmsd(recorded[p])]
        print(f"\nvina rerun reproduces the recorded survey top-pose RMSD on {len(same)} of {len(base)}")
    for arm in ARMS[1:]:
        gained = lost = 0
        for r in (x for x in rows if x["arm"] == arm):
            b = base.get(r["pdb"])
            if b is None:
                continue
            was = (top_rmsd(b) or 99) <= core.SUCCESS_RMSD
            now = (top_rmsd(r) or 99) <= core.SUCCESS_RMSD
            gained += (not was) and now
            lost += was and (not now)
        print(f"{arm:<18} vs vina: gained {gained}, lost {lost}")
    print("\nper receptor (top-1 RMSD / best of nine):")
    for pdb in sorted({r["pdb"] for r in rows}):
        cells = []
        for arm in ARMS:
            r = next((x for x in rows if x["pdb"] == pdb and x["arm"] == arm), None)
            cells.append("   -    " if r is None else f"{top_rmsd(r)}/{best_rmsd(r)}")
        print(f"  {pdb:<5} " + "  ".join(f"{c:>10}" for c in cells))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--targets", nargs="+", default=None)
    parser.add_argument("--exhaustiveness", type=int, default=25)
    parser.add_argument("--out", default="bench-out/engine_pilot")
    parser.add_argument("--list", action="store_true", help="print the pilot receptors and stop")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    receptors = [t.upper() for t in args.targets] if args.targets else pilot_receptors()
    if args.list:
        print(len(receptors), " ".join(receptors))
        return
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    results.touch()
    if args.report:
        report(out)
        return
    done = {(r["pdb"], r["arm"]) for r in (json.loads(x) for x in results.read_text().splitlines() if x.strip())}
    for arm in args.arms:
        provider = make_provider(arm)
        for pdb_id in receptors:
            if (pdb_id, arm) in done:
                continue
            row = survey.run_one(provider, pdb_id, ARM_NAME, survey.SEEDS[0], args.exhaustiveness)
            row["arm"] = arm  # the survey's "arm" is its preparation arm; here it names the engine
            row["preparation"] = ARM_NAME
            with results.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            print(f"{pdb_id:<5} {arm:<18} {row['outcome']:<36} {row.get('seconds', '')}s", flush=True)
    report(out)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
