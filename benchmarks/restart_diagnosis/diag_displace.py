"""Exploratory diagnosis, 2026-10-21 (NOT a benchmark record; see docs/BDE_DESIGN.md "Exploratory rerun"): for each of the four structures the preregistered rule dropped, take the
final geometry, get the Hessian, displace along the most imaginary mode in both directions and re-optimise."""
import json, re, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "bde"))
import run_bde as rb  # noqa: E402

OUT = Path(sys.argv[1])
CASES = {
    "water_H3O+": (REPO / "benchmarks/proton_affinity/artifacts/primary/runs.jsonl", "water|ion|lone_pair0|0", 1, 1),
    "ethanol_radical": (REPO / "benchmarks/bde/artifacts/primary/runs.jsonl", "radical|ethanol O-H|0", 0, 2),
    "CH3S_radical": (REPO / "benchmarks/bde/artifacts/primary/runs.jsonl", "radical|methanethiol S-H|0", 0, 2),
    "toluene": (REPO / "benchmarks/bde/artifacts/primary/runs.jsonl", "parent|Cc1ccccc1|0", 0, 1),
}
BOHR = 0.529177210903


def final_record(path, sid):
    recs = [json.loads(l) for l in open(path) if l.strip()]
    return [r for r in recs if r["structure"] == sid][-1]


def run_orca(tag, header, rec_geom, charge, mult, extra=""):
    d = Path(tempfile.mkdtemp(prefix="diag_"))
    lines = [header, "%pal nprocs 4 end", "%maxcore 3000"] + ([extra] if extra else []) + [f"* xyz {charge} {mult}"]
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in rec_geom]
    lines += ["*", ""]
    (d / "job.inp").write_text("\n".join(lines))
    t = time.time()
    p = subprocess.run([rb.ORCA, "job.inp"], cwd=d, capture_output=True, text=True, timeout=4 * 3600)
    return d, p.stdout, time.time() - t


def read_modes(hess_text):
    sec = hess_text.split("$normal_modes")[1].split("$")[0].split("\n#")[0].strip().splitlines()
    n = int(sec[0].split()[0])
    M = np.zeros((n, n))
    i = 1
    while i < len(sec):
        cols = [int(c) for c in sec[i].split()]
        for r in range(n):
            vals = sec[i + 1 + r].split()
            M[r, cols] = [float(v) for v in vals[1:]]
        i += n + 1
    f = hess_text.split("$vibrational_frequencies")[1].split("$")[0].strip().splitlines()
    freqs = np.array([float(l.split()[1]) for l in f[1:1 + int(f[0])]])
    return M, freqs


def case(name):
    path, sid, charge, mult = CASES[name]
    rec = final_record(path, sid)
    geom = list(zip(rec["symbols"], rec["coordinates"]))
    out = {"case": name, "start_lowest_freq": rec["lowest_frequency"]}
    d, text, secs = run_orca(name + "_freq", "! M062X def2-TZVPD TightSCF DefGrid3 Freq", geom, charge, mult)
    hess = (d / "job.hess").read_text()
    M, freqs = read_modes(hess)
    k = int(np.argmin(freqs))
    out.update(hess_lowest=float(freqs[k]), hess_lowest_five=[float(x) for x in np.sort(freqs)[:8]], freq_seconds=round(secs))
    shutil.rmtree(d, ignore_errors=True)
    vec = M[:, k].reshape(-1, 3)
    vec = vec / np.abs(vec).max()  # largest atom component = 1
    xyz = np.array([g[1] for g in geom])
    results = []
    for sign in (+1, -1):
        for amp in (0.15,):
            new = list(zip([g[0] for g in geom], (xyz + sign * amp * vec).tolist()))
            d2, t2, s2 = run_orca(name + f"_opt{sign:+d}", rb.HEADER, new, charge, mult, "%geom\n  Calc_Hess true\nend")
            try:
                parsed = rb.parse_species(t2)
                results.append({"sign": sign, "amp": amp, "energy": parsed["energy"], "enthalpy": parsed["enthalpy"], "lowest_frequency": parsed["lowest_frequency"], "seconds": round(s2)})
            except Exception as e:
                results.append({"sign": sign, "amp": amp, "error": str(e)[:200], "seconds": round(s2)})
            shutil.rmtree(d2, ignore_errors=True)
    out["displaced"] = results
    out["start_enthalpy"] = rec["enthalpy"]
    (OUT / f"{name}.json").write_text(json.dumps(out, indent=1))
    print(name, json.dumps(out), flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(case, ["toluene", "ethanol_radical", "CH3S_radical", "water_H3O+"]))
