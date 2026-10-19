"""Runs the larger-basis probe (`PLAN.md`): gate 4's exhaustive search at another basis, on gate 4's own geometries.

    python run_probe.py --basis "6-31+G*" --tag 631pG      [--workers 7] [--cores 4] [--species NAME]
    python run_probe.py --basis "def2-TZVP" --tag def2tzvp
    python run_probe.py --method "wB97X-D3" --basis "6-31G*" --tag wb97xd3 --out ../functional_probe/artifacts   (the functional probe: another functional, the basis of gate 4)

Everything but the basis is gate 4's: the B3LYP/6-31G* optimised geometries (read from `../artifacts/`, not re-optimised), oriented with the plane as xy, the application's compound input with holes in the HOMO-1 to the
HOMO-7, and the reading of every N-1 state's kind from the Loewdin spin populations (`openchem.app.fukui_gate_4`). **One difference, and why**: the N+1 job is removed from the input. At a basis the neutral's
anion is not always a converging state, ORCA ends a compound input at the first job that does not converge, and the N+1 state comes BEFORE the hole jobs; the probe needs only the cation states, so it never runs it.
Records go to `artifacts/<tag>/runs.jsonl`, one line per attempt, with the commit, the dirty flag, the ORCA version and the input hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # benchmarks/fukui_gate_4, for run_gate

import run_gate as rg  # noqa: E402

from openchem.app import fukui_gate_4 as gate  # noqa: E402
from openchem.chem.fukui_plan import searchable_holes  # noqa: E402
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, _TOTAL_CHARGE_RE, OrcaOutputError, add_parallel_block  # noqa: E402

#: The molecules of PLAN.md: six decided molecules of gate 4 with a sigma state in the comparison, and the calibration pyridine.
SPECIES = ("pyrimidine", "pyrazine", "pyridazine", "imidazole", "pyrazole", "oxazole", "pyridine")
GATE_ARTIFACTS = HERE.parent / "artifacts"


class Species:
    """A gate species with another basis (the gate's own `GateSpecies.method_basis` is fixed at 6-31G*)."""

    def __init__(self, base: gate.GateSpecies, method_basis: str) -> None:
        self.name, self.smiles, self.charge, self.hetero, self.method_basis = base.name, base.smiles, base.charge, base.hetero, method_basis


def without_the_anion(text: str) -> str:
    """The compound input without its N+1 job (the block whose coordinates carry charge -1): the probe needs the cation states only."""
    blocks = re.split(r"\n\n\$new_job\n", text)
    kept = [block for block in blocks if "* xyz -1 2" not in block]
    if len(kept) != len(blocks) - 1:
        raise RuntimeError(f"expected to remove exactly one N+1 job, removed {len(blocks) - len(kept)}")
    return "\n\n$new_job\n".join(kept)


def probe_run(ctx: rg.Context, species: Species, mol) -> dict:
    """The exhaustive search at this basis; a record per attempt, a completed one never repeated."""
    done = ctx.completed(species.name, "E")
    if done is not None:
        return done
    attempt = ctx.attempts(species.name, "E") + 1
    atomic_numbers = [a.GetAtomicNum() for a in mol.GetAtoms()]
    search = searchable_holes(atomic_numbers, species.charge, offsets=gate.EXHAUSTIVE_OFFSETS)
    header = f"! {species.method_basis} {_CALC_TYPE_KEYWORDS['fukui']}".strip()
    text = ctx.provider._build_fukui_input(header, rg.lines_of(mol), species.charge, 1, diffuse=False, holes=search.offsets, homo=search.homo)
    text = without_the_anion(text)
    out, code, seconds = rg.orca(ctx, f"{species.name}_E_{attempt}", text)
    record = rg.base_record(ctx, "E", species, attempt, text, out, code, seconds)
    record["basis"] = species.method_basis
    symbols = [a.GetSymbol().upper() for a in mol.GetAtoms()]
    z = np.array([mol.GetConformer().GetAtomPosition(i).z for i in range(mol.GetNumAtoms())])
    record["planarity"] = float(np.abs(z - z.mean()).max())
    record["planned_holes"] = list(search.offsets)
    try:
        results = ctx.provider._fukui_job_results(out, symbols)
    except OrcaOutputError as error:
        record.update({"completed": False, "error": str(error)})
        ctx.append(record)
        return record
    starts = [m.start() for m in _TOTAL_CHARGE_RE.finditer(out)]
    segments = [out[a:b] for a, b in zip(starts, [*starts[1:], len(out)])]
    expected_jobs = 2 + len(search.offsets)  # the neutral, the default cation, the cation holes (no N+1)
    jobs = []
    for index, result in enumerate(results):
        if result.state != "N-1" or result.energy_hartree is None:
            continue
        spins = gate.parse_lowdin_spin(segments[index], len(symbols))
        if spins is None:
            continue
        jobs.append({
            "position": index + 1, "start": str(result.start), "energy_hartree": result.energy_hartree, "s_squared": result.s_squared,
            "out_of_plane": gate.out_of_plane_fraction(spins), "atom_spin": [sum(atom.values()) for atom in spins],
        })
    finished = sum(1 for r in results if r.energy_hartree is not None)
    completed = code == 0 and finished == expected_jobs and len(jobs) == 1 + len(search.offsets)
    record.update({"completed": completed, "jobs": jobs, "symbols": symbols, "jobs_finished": finished, "jobs_expected": expected_jobs})
    if not completed:
        record["error"] = f"{finished} of {expected_jobs} jobs finished, exit {code}"
    ctx.append(record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--basis", required=True, help='the basis set keyword ORCA reads, e.g. "6-31+G*" or "def2-TZVP"')
    parser.add_argument("--tag", required=True, help="the folder under artifacts/ the records go to")
    parser.add_argument("--method", default="B3LYP", help="the functional ORCA reads (default B3LYP, the one every earlier run used)")
    parser.add_argument("--out", help="the folder the tag folder goes in (default: artifacts/ beside this file)")
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--species")
    args = parser.parse_args()

    out = (Path(args.out).resolve() if args.out else HERE / "artifacts") / args.tag
    ctx = rg.Context(out, args.cores, args.workers)
    geometries = json.loads((GATE_ARTIFACTS / "geometries.json").read_text())
    geometries.update({k: v for k, v in json.loads((GATE_ARTIFACTS / "calibration" / "geometries.json").read_text()).items() if k == "pyridine_reference"})
    by_name = {s.name: s for s in (*gate.GATE_SPECIES, *gate.CALIBRATION)}
    chosen = [by_name[name] for name in SPECIES if args.species in (None, name)]
    for base in chosen:
        key = f"{base.name}_reference"
        if ctx.geometry(key) is None:
            ctx.store_geometry(key, geometries[key])

    def work(base: gate.GateSpecies) -> None:
        species = Species(base, f"{args.method} {args.basis}")
        mol = rg.with_coordinates(rg.embed(base.smiles, rg.SEED), rg.oriented(ctx.geometry(f"{base.name}_reference")))
        record = rg.with_attempts(probe_run, ctx, species, mol)
        print(f"{args.tag} {base.name:11s} completed={record['completed']} {record['seconds']} s", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(work, chosen))


if __name__ == "__main__":
    main()
