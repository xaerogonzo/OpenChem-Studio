"""Runs the three arms of protocol v3 (`PREREGISTRATION.md` of this folder) and writes their reports. NOTHING IN THIS FILE HAS BEEN RUN AGAINST A FROZEN PREREGISTRATION: the arms are not computed until the preregistration is frozen.

    python run_restart_v3.py structures --arm halogen|sh|bromine     build every starting structure (RDKit; no ORCA): artifacts/<arm>/structures.json
    python run_restart_v3.py run --arm ... [--workers 3] [--cores 4]  the ORCA jobs (resumes: a structure whose chain is closed is never repeated)
    python run_restart_v3.py status --arm ...                          how many structures, how many closed
    python run_restart_v3.py report --arm ...                          report.txt and verdict.json

    halogen  Arm C   (6 C-H bonds next to F or Cl, ATcT 1.228)           deciding
    sh       Arm D   (3 thiol S-H bonds, acidity route; methanethiol beside, outside the verdict)   deciding for S-H only
    bromine  Arm C-Br (4 bromine C-H bonds, kinetics values)               REPORTED ONLY, no verdict

THE CHAIN OF ONE STRUCTURE is v2's (`benchmarks/restart_v2/run_restart.py`, loaded by path and reused unchanged): the preregistered optimization and frequencies; if a frequency is below -20 cm-1, the same job again from its final geometry with `Calc_Hess`.
Then, if it is STILL imaginary and the skeleton is intact: a RADICAL gets ONE numerical frequency job at that geometry (`restart_v3_core.py`; v2's displaced restart is not applied to it), a closed-shell structure gets v2's displaced restart. A closing record
(`"final": true`) ends every chain. A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/` or benchmark folder. ORCA is `D:\\ORCA\\orca.exe`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rr = _load("restart_v2_runner_for_v3", REPO / "benchmarks" / "restart_v2" / "run_restart.py")
v3 = _load("restart_v3_core", HERE / "restart_v3_core.py")
bde, pa, judge, v2core = rr.bde, rr.pa, rr.judge, rr.core

ARMS = {"halogen": v3.halogen_bonds, "sh": v3.sh_bonds, "bromine": v3.bromine_bonds, "thiophenol": v3.thiophenol_bonds}
#: Folders whose uncommitted change makes a record unreproducible (artifacts excluded).
WATCHED = ["src", "benchmarks/restart_v3", "benchmarks/thiyl_probe", "benchmarks/restart_v2", "benchmarks/bde", "benchmarks/bde_heldout", "benchmarks/proton_affinity"]


def build_structures(bonds: list[dict]) -> list[dict]:
    """Each distinct parent's kept conformers once, one radical start per bond and kept parent conformer, and the hydrogen atom: the held-out arm's builder over this arm's bonds."""
    structures: list[dict] = []
    conformers: dict[str, list] = {}
    for bond in bonds:
        smiles = bond["smiles"]
        mol = bde.parent_molecule(smiles)
        symbols = [a.GetSymbol() for a in mol.GetAtoms()]
        if smiles not in conformers:
            conformers[smiles] = pa.conformers_of(mol)
            for k, xyz in enumerate(conformers[smiles]):
                structures.append({"id": f"parent|{smiles}|{k}", "role": "parent", "smiles": smiles, "charge": 0, "mult": 1, "symbols": symbols, "coordinates": xyz.tolist()})
        neighbors = [n.GetIdx() for n in mol.GetAtomWithIdx(bond["atom"]).GetNeighbors()]
        for k, xyz in enumerate(conformers[smiles]):
            radical_symbols, radical_xyz = bde.core.radical_start(symbols, xyz, bond["atom"], neighbors)
            structures.append({"id": f"radical|{bond['name']}|{k}", "role": "radical", "bond": bond["name"], "smiles": smiles, "atom": bond["atom"], "excluded": bond["excluded"], "element": bond["element"],
                               "charge": 0, "mult": 2, "symbols": radical_symbols, "coordinates": radical_xyz.tolist()})
    structures.append({"id": bde.ATOM_ID, "role": "atom", "charge": 0, "mult": 2, "symbols": ["H"], "coordinates": [[0.0, 0.0, 0.0]]})
    return structures


# --- the numerical stage -----------------------------------------------------------------------------------------------------------


def numerical_input(structure: dict, cores: int) -> str:
    """The numerical job: the first run's functional, basis and grid with `NumFreq` and no `Opt`, at the geometry the structure carries, its own charge and multiplicity."""
    lines = [v3.NUMERICAL_HEADER, f"%pal nprocs {cores} end", "%maxcore 3000", f"* xyz {structure['charge']} {structure['mult']}"]
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in zip(structure["symbols"], structure["coordinates"])]
    lines += ["*", ""]
    return "\n".join(lines)


def numerical_stage(structure: dict, retry: dict, cores: int, run, commit: str, dirty: bool, append) -> None:
    """The v3 stage for a radical the first run's two stages left imaginary: ONE numerical frequency job at the re-run's geometry. Its own id (`<id>#numerical`), so the first run's 'latest record of a structure' never mistakes it for the structure's analytic result;
    the record is a completed species whose enthalpy REPLACES the analytic one (the analytic enthalpy and frequency are kept in it). A radical over the atom cap gets no job and a record saying why; a job that fails is a missing structure."""
    record = {"structure": f"{structure['id']}#numerical", "role": structure["role"], "stage": "numerical", "commit": commit, "dirty": dirty, "completed": False, "parent_structure": structure["id"]}
    for key in rr.CARRIED:
        if key in structure:
            record[key] = structure[key]
    if not v3.within_cap(len(retry["symbols"])):
        record.update(capped=True, label=v3.OVER_CAP)
        append(record)
        return
    at = dict(structure, symbols=retry["symbols"], coordinates=retry["coordinates"])
    began = time.time()
    try:
        text, _ = run(numerical_input(at, cores))
        parsed = v3.parse_numerical(text)
        record.update(parsed, skeleton_kept=rr.skeleton_ok(structure, parsed), **v3.numerical_fields(retry, parsed))
        record["completed"] = True
    except subprocess.TimeoutExpired:
        record["error"] = f"timeout after {bde.JOB_TIMEOUT_SECONDS} s"
    except OSError as error:
        record["error"], record["infrastructure"] = f"{type(error).__name__}: {error}"[:300], True
    except Exception as error:  # noqa: BLE001 - a failed job is a missing structure, recorded with its reason
        record["error"] = f"{type(error).__name__}: {error}"[:300]
    record["seconds"] = round(time.time() - began, 1)
    append(record)


def process(structure: dict, cores: int, run, commit: str, dirty: bool, append) -> bool:
    """The whole chain of one structure, then its closing record. A job that could not even be started (`infrastructure`) leaves the chain OPEN and returns False: the structure is done again by the next run."""
    broken: list[bool] = []

    def keep(record: dict) -> None:
        broken.append(bool(record.get("infrastructure")))
        append(record)

    first = rr.attempt(structure, cores, False, "opt", run, commit, dirty)
    keep(first)
    if first["completed"] and structure["role"] != "atom" and first["lowest_frequency"] < v3.IMAGINARY_CM:
        again = dict(structure, symbols=first["symbols"], coordinates=first["coordinates"])
        second = rr.attempt(again, cores, True, "retry", run, commit, dirty)
        keep(second)
        if v3.needs_numerical(second):
            numerical_stage(structure, second, cores, run, commit, dirty, keep)
        elif structure["role"] != "radical" and v2core.needs_restart(second):
            rr.restart(structure, second, cores, run, commit, dirty, keep)
    if any(broken):
        return False
    append({"structure": structure["id"], "role": structure["role"], "stage": "closed", "completed": False, "final": True, "commit": commit, "dirty": dirty})
    return True


def git_state() -> tuple[str, bool]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO, check=False).stdout.strip()
    spec = ["status", "--porcelain", "--", *WATCHED, ":(exclude)benchmarks/restart_v3/artifacts", ":(exclude)benchmarks/restart_v2/artifacts", ":(exclude)benchmarks/restart_v3/RESULT*.md"]
    return commit, bool(subprocess.run(["git", *spec], capture_output=True, text=True, cwd=REPO, check=False).stdout.strip())


def run_stage(arm: str, out: Path, cores: int, workers: int, run=rr.run_orca) -> None:
    structures = json.loads((out / arm / "structures.json").read_text(encoding="utf-8"))
    path = out / arm / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    commit, dirty = git_state()
    todo = rr.pending(structures, pa.records_of(path))
    print(f"{len(structures) - len(todo)} closed, {len(todo)} to run", flush=True)

    def append(record: dict) -> None:
        # the tree is asked again for EVERY record: an edit made during a run of hours marks the records written after it, not just those written at the start
        record["commit"], record["dirty"] = git_state()
        with rr.LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def work(structure: dict) -> None:
        closed = process(structure, cores, run, commit, dirty, append)
        print(f"{structure['id']} {'closed' if closed else 'LEFT OPEN: ORCA could not be started'}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, todo))


# --- the reports -------------------------------------------------------------------------------------------------------------------


def _selected(done: list[dict], bond: dict, labels: dict) -> dict:
    """WHICH structures the bond's value was taken from (the lowest-enthalpy accepted parent and radical, the first run's rule) and how each was obtained: the report flags and prints from this, never from the other conformers."""
    out = {}
    for role, key, match in (("parent", "smiles", bond["smiles"]), ("radical", "bond", bond["name"])):
        pool = [r for r in done if r["role"] == role and r.get(key) == match]
        if not pool:
            out[role] = None
            continue
        r = min(pool, key=lambda x: x["enthalpy"])
        entry = {"structure": r["structure"], "lowest_frequency": v3.lowest_vibration(r.get("frequencies") or []) if r.get("frequencies") else r["lowest_frequency"], "method": "numerical" if r.get("numerical") else "analytic"}
        if r.get("numerical"):
            entry.update(verified=r["verified"], shift_kcal=labels[r["parent_structure"]]["shift_kcal"])
        out[role] = entry
    return out


def _numerical_outcomes(records: list[dict], bond: dict) -> list[dict]:
    """The numerical jobs of a bond's radicals that gave NO result (failed, timed out, or over the atom cap), with the reason, so a bond decided by the other conformers says so."""
    out = []
    for r in records:
        if r.get("stage") == "numerical" and not r.get("completed") and str(r.get("structure", "")).startswith(f"radical|{bond['name']}|"):
            out.append({"structure": r["structure"], "reason": r.get("label") or r.get("error") or "no result"})
    return out


def judge_rows(records: list[dict], bonds: list[dict]) -> list[dict]:
    """The first run's judge over this protocol's accepted records (a numerical record is accepted at any frequency), one row per bond with its reference, computed value, the structures the value came from and how, and the numerical jobs that gave no result."""
    done = v3.accepted(records)
    labels = v3.numerical_labels(records)
    rows = []
    for bond in bonds:
        picked = bde.select(done, bond)
        row = {"name": bond["name"], "dh_ref": bond["dh298"], "uncertainty": bond["uncertainty"], "dh_kcal": picked["value_eh"] * bde.core.HARTREE_TO_KCAL if picked else None, "s2": picked["s2"] if picked else None,
               "element": bond["element"], "excluded": bond["excluded"]}
        row["selected"] = _selected(done, bond, labels) if picked else None
        row["numerical_no_result"] = _numerical_outcomes(records, bond)
        rows.append(row)
    return rows


#: The folders whose change since the records were made makes a report unreproducible (the same list `git_state` watches; artifacts are data, not code).
_DRIFT_SPEC = [*WATCHED, ":(exclude)benchmarks/restart_v3/artifacts", ":(exclude)benchmarks/restart_v2/artifacts", ":(exclude)benchmarks/restart_v3/RESULT*.md"]


def drift_problem(records: list[dict]) -> str | None:
    """Whether anything the records depend on changed between the commit they were made at and HEAD: the runner, the references, the shared code. A report built from references edited after the run is not a report of that run. An empty or unknown commit is a problem."""
    commits = {r.get("commit") for r in records}
    if not commits:
        return None
    if "" in commits or None in commits:
        return "a record carries no commit"
    for commit in commits:
        done = subprocess.run(["git", "diff", "--name-only", commit, "HEAD", "--", *_DRIFT_SPEC], capture_output=True, text=True, cwd=REPO, check=False)
        if done.returncode != 0:
            return f"commit {commit[:8]} cannot be compared with HEAD"
        if done.stdout.strip():
            return f"files changed since the records' commit {commit[:8]}: {', '.join(done.stdout.split()[:5])}"
    return None


def problem_of(records: list[dict], structures: list[dict] | None) -> str | None:
    problem = bde.provenance_problem(records) or drift_problem(records)
    if structures is not None and (open_chains := rr.pending(structures, records)) and not problem:
        problem = f"{len(open_chains)} structure chain(s) are not closed"
    return problem


def _flags(row: dict) -> str:
    """What to know about THE STRUCTURES THE VALUE CAME FROM: their lowest frequencies, whether the radical's came from the numerical job and what it moved, and the numerical jobs that gave no result."""
    notes = []
    sel = row.get("selected")
    if sel:
        parent, radical = sel["parent"], sel["radical"]
        notes.append(f"lowest frequency parent {parent['lowest_frequency']:.0f}, radical {radical['lowest_frequency']:.0f} cm-1")
        if radical["method"] == "numerical":
            notes.append(f"radical from the NUMERICAL job, {radical['shift_kcal']:+.2f} kcal/mol vs analytic" + ("" if radical["verified"] else "; FREQUENCIES NOT VERIFIED"))
        else:
            notes.append("radical analytic")
    for n in row.get("numerical_no_result", []):
        notes.append(f"numerical job gave no result for {n['structure']}: {n['reason']}")
    return ("  [" + "; ".join(notes) + "]") if notes else ""


def _fmt(s) -> str:
    if s.count == 0:
        return f"n=0 missing={s.missing}"
    return f"n={s.count:2d} missing={s.missing} MAE={s.mae:.2f} MSE={s.mse:+.2f} max={s.max_abs:.2f}"


def deciding_report(arm: str, records: list[dict], bonds: list[dict], structures: list[dict] | None) -> tuple[str, dict]:
    """Arms C and D: the first run's limits on the deciding bonds, the standard error, the limits the result is too close to call, and every bond with its flags. Arm D prints methanethiol beside, outside the verdict."""
    problem = problem_of(records, structures)
    rows = judge_rows(records, bonds)
    deciding = [r for r in rows if not r["excluded"]]
    beside = [r for r in rows if r["excluded"]]
    stats = judge.stats(deciding)
    verdict = judge.NOT_EVALUABLE if problem else v3.arm_verdict(stats)
    errors = [r["dh_kcal"] - r["dh_ref"] for r in deciding if r["dh_kcal"] is not None]
    se = v3.standard_error(errors)
    band = 0.7 if arm == "sh" else 0.5
    title = {"halogen": "ARM C (six C-H bonds next to F and Cl; ATcT 1.228)", "sh": "ARM D (three thiol S-H bonds; gas-phase acidity references that share an anchor, n = 3 with correlated errors)"}[arm]
    lines = [title + (f"; REFUSED: {problem}" if problem else ""), f"deciding {_fmt(stats)}", f"VERDICT {verdict}",
             "standard error of the mean error: " + (f"{se:.2f} kcal/mol" if se is not None else "n/a")]
    close = v3.near_limits(stats, band)
    lines.append(f"within {band} kcal/mol of a limit, so the two sides cannot be told apart: " + ("; ".join(close) if close else "none"))
    sensitivity = None
    if arm == "sh":
        shifts = v3.anchor_shifts_kcal()
        sensitivity = {name: v3.reference_sensitivity(deciding, shift) for name, shift in shifts.items()}
        lines.append("SENSITIVITY TO THE SHARED METHANETHIOL ANCHOR (not a correction; the verdict above is read on Ervin's references as they stand): every reference raised by the most the anchor could move it:")
        for name, label in (("combined", "the anchor averaged with Wilson, Ashfold and Dixon 1994"), ("wilson_alone", "that measurement alone")):
            s = sensitivity[name]
            st = s["stats"]
            body = "n/a" if not st["count"] else f"MAE {st['mae']:.2f}, MSE {st['mse']:+.2f}, max {st['max_abs']:.2f}"
            lines.append(f"    +{s['shift']:.2f} kcal/mol ({label}): {body} -> {s['verdict']}")
    if stats.missing == 1:
        lines.append(f"ONE of the {len(deciding)} deciding bonds has no computed value: the verdict rests on the other {stats.count}.")
    if arm == "sh":
        lines.append("Reference status: ethanethiol's is PUBLISHED (Ervin 2015); 1-propanethiol's and 2-propanethiol's are DERIVED here from published acidities and electron affinities with a thermal step COMPUTED in thermal_step.py, not published numbers.")
        lines.append("Methanethiol's S-H (the first run's lost bond; Nicovich 1992) is printed beside the three bonds and does not enter the mean.")
    unverified = [r["name"] for r in rows if r.get("selected") and r["selected"]["radical"]["method"] == "numerical" and not r["selected"]["radical"]["verified"]]
    if unverified:
        lines.append(f"{len(unverified)} bond(s) took their radical value from a numerical job that kept a mode below -20 cm-1 (enthalpy used and labelled): {', '.join(unverified)}")
    no_result = [(r["name"], n["reason"]) for r in rows for n in r["numerical_no_result"]]
    if no_result:
        lines.append(f"{len(no_result)} numerical job(s) gave no result (failed, timed out, or over the {v3.MAX_NUMERICAL_ATOMS}-atom cap): " + "; ".join(f"{a}: {b}" for a, b in no_result))
    lines += ["", f"{'bond':44s} {'calc':>8s} {'ref':>8s} {'error':>7s}"]
    for r in deciding + beside:
        calc = "-" if r["dh_kcal"] is None else f"{r['dh_kcal']:.2f}"
        error = "missing" if r["dh_kcal"] is None else f"{r['dh_kcal'] - r['dh_ref']:+.2f}"
        lines.append(f"{r['name'][:44]:44s} {calc:>8s} {r['dh_ref']:8.2f} {error:>7s}{'  (beside, outside the verdict)' if r['excluded'] else ''}{_flags(r)}")
    return "\n".join(lines), {"arm": arm, "verdict": verdict, "problem": problem, "deciding": stats.__dict__, "standard_error": se, "within_band_of": close, "anchor_sensitivity": sensitivity, "rows": rows}


def bromine_report(records: list[dict], bonds: list[dict], structures: list[dict] | None) -> tuple[str, dict]:
    """Arm C-Br: no verdict. Each bond's computed value against the kinetics value, the other determinations and the calculated values, and a claim only for a gross failure."""
    problem = problem_of(records, structures)
    rows = judge_rows(records, bonds)
    lines = ["ARM C-Br (four bromine C-H bonds; REPORTED ONLY, deciding nothing)" + (f"; REFUSED: {problem}" if problem else ""),
             "A claim is made only when the error exceeds 5.0 kcal/mol against the kinetics value AND every calculated value (bromoethane, which has none: more than 5.0 outside the whole range of the other determinations); anything else is numbers.", ""]
    readings = []
    for row, bond in zip(rows, bonds):
        reading = v3.bromine_reading(row["dh_kcal"], bond)
        if problem:
            # a refused report makes no claim about anything
            reading = dict(reading, gross=False, claim="no claim: the report is refused")
        readings.append(dict(reading, name=bond["name"]))
        if row["dh_kcal"] is None:
            lines.append(f"{bond['name']:26s} no computed value{_flags(row)}")
            continue
        low, high = min(bond["others"]), max(bond["others"])
        calc = ", ".join(f"{c:.2f}" for c in bond["calculated"]) or "none"
        vs_range = reading["vs_others_high_low"]
        vs_calc = ", ".join(f"{e:+.2f}" for e in reading["vs_calculated"]) or "n/a"
        lines.append(f"{bond['name']:26s} computed {row['dh_kcal']:.2f}; kinetics {bond['dh298']:.2f} (error {reading['vs_kinetics']:+.2f}); other determinations {low:.2f} to {high:.2f} "
                     f"(error {vs_range[1]:+.2f} to {vs_range[0]:+.2f}); calculated {calc} (error {vs_calc}); {reading['claim']}{_flags(row)}")
    return "\n".join(lines), {"arm": "bromine", "verdict": None, "problem": problem, "readings": readings, "rows": rows}


def thiophenol_report(records: list[dict], bonds: list[dict], structures: list[dict] | None) -> tuple[str, dict]:
    """Arm D-Ph: no verdict. The computed value against every determination, the span they cover, Devine's upper limit, and a claim only for a gross failure."""
    problem = problem_of(records, structures)
    rows = judge_rows(records, bonds)
    lines = ["ARM D-Ph (thiophenol S-H; REPORTED ONLY, deciding nothing)" + (f"; REFUSED: {problem}" if problem else ""),
             "No determination is a reference (they span about 5 kcal/mol and the newest is an upper limit). A claim is made only when the computed value is more than 5.0 kcal/mol outside the whole span of the determinations; anything else is numbers.", ""]
    readings = []
    for row, bond in zip(rows, bonds):
        reading = span_reading_for(row, bond, problem)
        readings.append(dict(reading, name=bond["name"]))
        if row["dh_kcal"] is None:
            lines.append(f"{bond['name']} no computed value{_flags(row)}")
            continue
        lines.append(f"{bond['name']}: computed {row['dh_kcal']:.2f} kcal/mol at 298 K; span of the determinations {reading['span'][0]:.2f} to {reading['span'][1]:.2f}; {reading['claim']}{_flags(row)}")
        lines += [f"    {label:46s} {value:7.2f}  error {reading['errors'][label]:+.2f}" for label, value in bond["points"].items()]
        lines.append(f"    {'Devine 2008, UPPER LIMIT (0 K value plus the step)':46s} {bond['upper_limit']:7.2f}  computed minus limit {reading['above_upper_limit']:+.2f}")
    return "\n".join(lines), {"arm": "thiophenol", "verdict": None, "problem": problem, "readings": readings, "rows": rows}


def span_reading_for(row: dict, bond: dict, problem: str | None) -> dict:
    reading = v3.span_reading(row["dh_kcal"], bond)
    return dict(reading, gross=False, claim="no claim: the report is refused") if problem and row["dh_kcal"] is not None else reading


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["structures", "run", "report", "status"])
    parser.add_argument("--arm", choices=sorted(ARMS), required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", default=str(HERE / "artifacts"))
    args = parser.parse_args()
    out = Path(args.out)
    (out / args.arm).mkdir(parents=True, exist_ok=True)
    structures_path, runs_path = out / args.arm / "structures.json", out / args.arm / "runs.jsonl"
    bonds = ARMS[args.arm]()
    if args.command == "structures":
        structures = build_structures(bonds)
        structures_path.write_text(json.dumps(structures), encoding="utf-8")
        roles = [s["role"] for s in structures]
        print(f"{len(structures)} structures ({', '.join(f'{roles.count(r)} {r}' for r in sorted(set(roles)))})")
    elif args.command == "run":
        run_stage(args.arm, out, args.cores, args.workers)
    elif args.command == "status":
        structures = json.loads(structures_path.read_text(encoding="utf-8"))
        print(f"{len(structures)} structures, {len(structures) - len(rr.pending(structures, pa.records_of(runs_path)))} closed")
    else:
        structures = json.loads(structures_path.read_text(encoding="utf-8"))
        records = pa.records_of(runs_path)
        report = {"bromine": bromine_report, "thiophenol": thiophenol_report}.get(args.arm)
        text, verdict = report(records, bonds, structures) if report else deciding_report(args.arm, records, bonds, structures)
        print(text)
        (out / args.arm / "report.txt").write_text(text, encoding="utf-8")
        (out / args.arm / "verdict.json").write_text(json.dumps(verdict, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
