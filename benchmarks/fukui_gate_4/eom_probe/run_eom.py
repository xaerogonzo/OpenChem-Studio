"""Runs the EOM-IP-CCSD probe (`PLAN.md`): the lowest ionization roots of a gate-4 molecule at its gate-4 geometry, each classified sigma or pi from its dominant orbital.

    python run_eom.py --basis cc-pVDZ --tag ccpvdz [--species NAME ...] [--workers 3] [--cores 8] [--roots 8] [--maxcore 3000]

The geometry is the B3LYP/6-31G* optimum of gate 4 (read from `../artifacts/`, never re-optimised), oriented with the plane as xy (`run_gate.oriented`), so an orbital odd in z is a pi orbital.
Records go to `artifacts/<tag>/runs.jsonl`, one line per attempt (commit, dirty flag, ORCA version, input hash), and the results block of each output beside it as `<species>.eom.txt`.
A record is `completed` only if ORCA exited 0, every root converged, `--roots` roots were read, and their dominant orbitals are the HOMO and the orbitals below it WITHOUT A GAP (a gap would mean a lower root was missed).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # benchmarks/fukui_gate_4, for run_gate

import eom_parse  # noqa: E402
import run_gate as rg  # noqa: E402

from openchem.app import fukui_gate_4 as gate  # noqa: E402

#: The molecules of PLAN.md: the two of the rule, and pyridine (the calibration against EOM-IP-CCSDT).
SPECIES = ("pyrimidine", "pyrazine", "pyridine")
GATE_ARTIFACTS = HERE.parent / "artifacts"


class Species:
    """A gate species at another method and basis (the gate's own `method_basis` is B3LYP 6-31G*)."""

    def __init__(self, base: gate.GateSpecies, method_basis: str) -> None:
        self.name, self.smiles, self.charge, self.hetero, self.method_basis = base.name, base.smiles, base.charge, base.hetero, method_basis


def eom_input(basis: str, roots: int, maxcore: int, lines: list[str]) -> str:
    return "\n".join([
        f"! IP-EOM-CCSD {basis} TightSCF", f"%maxcore {maxcore}", "%mdci", "  DoEOM true", f"  NRoots {roots}", "  FollowCIS true", "end",
        "%output", "  Print[P_ReducedOrbPopMO_L] 1", "end", "* xyz 0 1", *lines, "*", ""])


def homo_of(out: str) -> int | None:
    """The 0-based number of the HOMO: ORCA's electron count over two, minus one."""
    match = re.search(r"Number of Electrons\s+NEL\s+\.\.\.\.\s+(\d+)", out)
    return int(match.group(1)) // 2 - 1 if match else None


def probe_run(ctx: rg.Context, species: Species, mol, roots: int, maxcore: int) -> dict:
    done = ctx.completed(species.name, "EOM")
    if done is not None:
        return done
    attempt = ctx.attempts(species.name, "EOM") + 1
    text = eom_input(species.method_basis, roots, maxcore, rg.lines_of(mol))
    out, code, seconds = rg.orca(ctx, f"{species.name}_EOM_{attempt}", text)
    record = rg.base_record(ctx, "EOM", species, attempt, text, out, code, seconds)
    homo = homo_of(out)
    classified = eom_parse.classified_roots(out)
    parity = eom_parse.parse_orbital_parity(out)
    orbitals = sorted((r["orbital"] for r in classified), reverse=True)
    contiguous = homo is not None and orbitals == list(range(homo, homo - len(orbitals), -1))
    converged = "CONVERGENCE OF RESIDUAL NORM REACHED" in out
    record.update({
        "roots_asked": roots, "homo": homo, "converged": converged, "contiguous_from_homo": contiguous, "roots": classified,
        "occupied_parity": {str(k): round(v, 4) for k, v in parity.items() if homo is not None and k <= homo},
        "completed": code == 0 and converged and len(classified) == roots and contiguous and all(r["kind"] in ("sigma", "pi") for r in classified),
    })
    if not record["completed"]:
        record["error"] = f"exit {code}, converged {converged}, {len(classified)} of {roots} roots, contiguous from the HOMO {contiguous}, kinds {[r['kind'] for r in classified]}"
    block = out[out.rfind("EOM-CCSD RESULTS"):] if "EOM-CCSD RESULTS" in out else out[-2000:]
    (ctx.out / f"{species.name}.eom.txt").write_text(block, encoding="utf-8")
    ctx.append(record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--basis", required=True, help='the basis ORCA reads, e.g. "cc-pVDZ" or "aug-cc-pVDZ"')
    parser.add_argument("--tag", required=True, help="the folder under artifacts/ the records go to")
    parser.add_argument("--species", nargs="*", help="a subset of the molecules (default: all three)")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--roots", type=int, default=8)
    parser.add_argument("--maxcore", type=int, default=3000, help="MB per core")
    args = parser.parse_args()

    ctx = rg.Context(HERE / "artifacts" / args.tag, args.cores, args.workers)
    geometries = json.loads((GATE_ARTIFACTS / "geometries.json").read_text())
    geometries.update({k: v for k, v in json.loads((GATE_ARTIFACTS / "calibration" / "geometries.json").read_text()).items() if k == "pyridine_reference"})
    by_name = {s.name: s for s in (*gate.GATE_SPECIES, *gate.CALIBRATION)}
    chosen = [by_name[name] for name in SPECIES if not args.species or name in args.species]
    for base in chosen:
        key = f"{base.name}_reference"
        if ctx.geometry(key) is None:
            ctx.store_geometry(key, geometries[key])

    def work(base: gate.GateSpecies) -> None:
        species = Species(base, args.basis)
        mol = rg.with_coordinates(rg.embed(base.smiles, rg.SEED), rg.oriented(ctx.geometry(f"{base.name}_reference")))
        record = probe_run(ctx, species, mol, args.roots, args.maxcore)
        print(f"{args.tag} {base.name:11s} completed={record['completed']} {record['seconds']} s {record.get('error', '')}", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(work, chosen))


if __name__ == "__main__":
    main()
