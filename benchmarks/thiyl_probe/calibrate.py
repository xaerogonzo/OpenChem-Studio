"""Calibration of the trigger for numerical frequencies, on bonds whose results are ALREADY SPENT (2026-10-26; not a benchmark record).

`probe.py` found that the thiyl radicals' imaginary modes are spurious (the analytic M06-2X Hessian is ill-conditioned) and that a radical which PASSES can still carry a
quiet analytic error (methoxy: one mode 208 cm-1 off, enthalpy +0.27 kcal/mol). The protocol therefore needs a rule for WHEN to compute numerical frequencies, and a rule
chosen from six radicals would be a threshold fitted to the cases that suggested it. This script gathers the evidence for the rule from the OTHER radicals the two bond
dissociation benchmarks already computed (the first run's and the held-out arm's accepted radicals): nothing here is a held-out result and none of it can change a verdict.

    stability  OUT_DIR              UKS stability analysis at the recorded final geometry of every accepted radical (about a minute each)
    select     OUT_DIR              which radicals then get a numerical-frequency job, by a rule fixed in `select_for_numfreq` before the jobs run
    numfreq    OUT_DIR              analytic and numerical frequencies for the selected ones (the analytic job reruns on the SAME geometry: nothing is compared across geometries)
    collect    OUT_DIR              read the finished jobs (starts nothing) and list any radical a job of which did not finish
    report     OUT_DIR              the table: smallest stability eigenvalue against the analytic-to-numerical enthalpy shift and the largest mode difference
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probe  # noqa: E402  (write_input, summarise, rb.ORCA)

REPO = probe.REPO
SOURCES = {
    "first": REPO / "benchmarks" / "bde" / "artifacts" / "primary" / "runs.jsonl",
    "heldout": REPO / "benchmarks" / "restart_v2" / "artifacts" / "heldout" / "runs.jsonl",
    "stress": REPO / "benchmarks" / "restart_v2" / "artifacts" / "stress" / "runs.jsonl",
}
HARTREE_TO_KCAL = 627.5094740631
#: A radical whose smallest stability eigenvalue is below this gets a numerical-frequency job in the calibration. Chosen to include every radical seen so far with a margin
#: (methylthiyl 0.0005, ethanethiyl 0.0015, methoxy 0.0049, the next one up 0.036): it selects what to MEASURE, it is not the protocol's rule.
FLAG_BELOW = 0.05
#: Radicals of at most this many atoms get a numerical job whatever their eigenvalue (cheap, and a control group of ordinary radicals).
SMALL_ATOMS = 6
#: NO RADICAL LARGER THAN THIS GETS A NUMERICAL JOB IN THE CALIBRATION, decided after the stability phase had ranked the radicals and BEFORE any numerical job ran: a numerical Hessian is 6N gradients
#: (about 25 minutes for the 8-atom ethanethiyl radical, hours at 14 atoms), so the eleven-to-fifteen-atom radicals (the propoxyls, tert-butoxyl, phenoxyl, benzoyloxyl and the hydroperoxyl of
#: tert-butyl) are NOT measured here, and whatever the calibration says is about radicals of this size or smaller.
MAX_ATOMS = 9
#: How many of the remaining (larger, high-eigenvalue) radicals are sampled as a control, by this seed.
SAMPLE_OF_REST = 6
SEED = 20261026


def accepted_radicals() -> list[dict]:
    """One record per (source, bond): the accepted radical structure of lowest enthalpy, which is the one the bond's DH298 uses."""
    chosen = []
    for source, path in SOURCES.items():
        recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        by_bond: dict[str, list[dict]] = {}
        for r in recs:
            if r.get("role") == "radical" and r.get("symbols") and r.get("enthalpy") is not None and r.get("lowest_frequency") is not None and r["lowest_frequency"] > -20:
                by_bond.setdefault(r.get("bond"), []).append(r)
        for bond, rs in by_bond.items():
            best = min(rs, key=lambda r: r["enthalpy"])
            chosen.append({"source": source, "bond": bond, "structure": best["structure"], "atoms": len(best["symbols"]),
                           "symbols": best["symbols"], "coordinates": best["coordinates"], "recorded_enthalpy": best["enthalpy"],
                           "recorded_lowest_frequency": best["lowest_frequency"]})
    return chosen


def slug(item: dict) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", f'{item["source"]}__{item["bond"]}').strip("_")[:90]


def run_job(item: dict, out: Path, kind: str, read_only: bool = False) -> dict | None:
    route, extra = probe.VARIANTS[{"stability": "sp_stability", "analytic": "freq_analytic", "numerical": "freq_numerical"}[kind]]
    workdir = out / kind / slug(item)
    workdir.mkdir(parents=True, exist_ok=True)
    geometry = list(zip(item["symbols"], (tuple(c) for c in item["coordinates"])))
    probe.write_input(workdir / "job.inp", route, extra, geometry)
    started = time.time()
    finished = workdir / "job.out"
    if finished.exists() and "ORCA TERMINATED NORMALLY" in finished.read_text(encoding="utf-8", errors="replace"):
        text = finished.read_text(encoding="utf-8", errors="replace")  # resumable: a job that already ended normally is read, never rerun
    elif read_only:
        return None
    else:
        done = subprocess.run([probe.rb.ORCA, "job.inp"], cwd=workdir, capture_output=True, text=True, timeout=12 * 3600)
        text = done.stdout
        finished.write_text(text, encoding="utf-8", errors="replace")
    summary = probe.summarise(text)
    enthalpy = re.findall(r"Total enthalpy\s*\.*\s*(-?\d+\.\d+)", text)
    block = text.split("The eigenvalues of the stability matrix:")[1].split("The stability")[0] if "The eigenvalues of the stability matrix:" in text else ""
    return {
        "key": slug(item), "kind": kind, "seconds": round(time.time() - started, 1), "terminated_normally": summary["terminated_normally"],
        "energy": summary["energy"], "frequencies": [f for f in summary["frequencies"] if abs(f) > 0.01], "enthalpy": float(enthalpy[-1]) if enthalpy else None,
        "stability_eigenvalues": [float(x) for x in re.findall(r"=\s*(-?\d+\.\d+) Eh", block)],
        "stable": "wavefunction is stable" in text,
    }


def run_many(items: list[dict], out: Path, kind: str, workers: int) -> list[dict]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda it: run_job(it, out, kind), items))


def select_for_numfreq(items: list[dict], stability: dict[str, dict]) -> list[dict]:
    """The selection rule, fixed here before any numerical job runs: flagged by eigenvalue, small, or a seeded sample of the rest."""
    items = [it for it in items if it["atoms"] <= MAX_ATOMS]
    flagged = [it for it in items if min(stability[slug(it)]["stability_eigenvalues"] or [9.0]) < FLAG_BELOW]
    small = [it for it in items if it["atoms"] <= SMALL_ATOMS and it not in flagged]
    rest = [it for it in items if it not in flagged and it not in small]
    rest.sort(key=slug)
    sample = random.Random(SEED).sample(rest, min(SAMPLE_OF_REST, len(rest)))
    return flagged + small + sample


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    items = accepted_radicals()
    if phase == "stability":
        results = run_many(items, out, "stability", workers=6)
        (out / "stability.json").write_text(json.dumps({r["key"]: r for r in results}, indent=1), encoding="utf-8")
        (out / "radicals.json").write_text(json.dumps([{k: v for k, v in it.items() if k not in ("coordinates",)} for it in items], indent=1), encoding="utf-8")
        for r in sorted(results, key=lambda r: min(r["stability_eigenvalues"] or [9])):
            print(f'{min(r["stability_eigenvalues"] or [9]):.5f}  stable={r["stable"]}  {r["key"]}  {r["seconds"]}s')
    elif phase == "select":
        stability = load(out / "stability.json")
        picked = select_for_numfreq(items, stability)
        (out / "selected.json").write_text(json.dumps([slug(it) for it in picked], indent=1), encoding="utf-8")
        print(len(picked), "selected of", len(items))
        for it in picked:
            print(f'  {min(stability[slug(it)]["stability_eigenvalues"] or [9]):.5f}  {it["atoms"]:2d} atoms  {slug(it)}')
    elif phase == "numfreq":
        wanted = set(json.loads((out / "selected.json").read_text(encoding="utf-8")))
        picked = [it for it in items if slug(it) in wanted]
        picked.sort(key=lambda it: -it["atoms"])  # the big jobs first, so the last workers are not left holding one
        results = run_many(picked, out, "analytic", workers=6) + run_many(picked, out, "numerical", workers=6)
        (out / "numfreq.json").write_text(json.dumps({f'{r["kind"]}:{r["key"]}': r for r in results}, indent=1), encoding="utf-8")
        print("done", len(results))
    elif phase == "collect":
        # Reads the jobs that finished and starts nothing. `numfreq` writes its file only when EVERY job has returned, so one radical whose ORCA run crashed or
        # hung (methyl hydroperoxide's C-H did both, twice, in the analytic CPSCF step) would lose the other eighty; a radical either job of which is missing is
        # listed in unmeasured.json with that fact and is not in numfreq.json at all.
        wanted = set(json.loads((out / "selected.json").read_text(encoding="utf-8")))
        results, unmeasured = [], []
        for it in (i for i in items if slug(i) in wanted):
            pair = [run_job(it, out, kind, read_only=True) for kind in ("analytic", "numerical")]
            if all(pair):
                results += pair
            else:
                unmeasured.append({"key": slug(it), "atoms": it["atoms"], "analytic_finished": bool(pair[0]), "numerical_finished": bool(pair[1])})
        (out / "numfreq.json").write_text(json.dumps({f'{r["kind"]}:{r["key"]}': r for r in results}, indent=1), encoding="utf-8")
        (out / "unmeasured.json").write_text(json.dumps(unmeasured, indent=1), encoding="utf-8")
        print("collected", len(results) // 2, "radicals; unmeasured:", [u["key"] for u in unmeasured])
    elif phase == "report":
        stability, nf = load(out / "stability.json"), load(out / "numfreq.json") or {}
        rows = []
        for key, s in stability.items():
            a, n = nf.get(f"analytic:{key}"), nf.get(f"numerical:{key}")
            row = {"key": key, "min_eigenvalue": min(s["stability_eigenvalues"] or [9.0]), "stable": s["stable"]}
            if a and n and a["enthalpy"] is not None and n["enthalpy"] is not None:
                fa, fn = sorted(a["frequencies"]), sorted(n["frequencies"])
                row["enthalpy_shift_kcal"] = round((n["enthalpy"] - a["enthalpy"]) * HARTREE_TO_KCAL, 3)
                row["analytic_lowest"], row["numerical_lowest"] = fa[0] if fa else None, fn[0] if fn else None
                row["max_mode_difference"] = round(max(abs(x - y) for x, y in zip(fa, fn)), 1) if len(fa) == len(fn) else None
            rows.append(row)
        rows.sort(key=lambda r: r["min_eigenvalue"])
        (out / "calibration_table.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        for r in rows:
            print(f'{r["min_eigenvalue"]:.5f}  shift={r.get("enthalpy_shift_kcal")}  dmode={r.get("max_mode_difference")}  low(a/n)={r.get("analytic_lowest")}/{r.get("numerical_lowest")}  {r["key"]}')
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
