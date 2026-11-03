"""Run: python saddle_follow.py OUT_DIR  (ORCA is the ORCA constant below; about 20 minutes). Its numbers are summarised by the committed artifacts/saddle_follow/summary.json.

Follow the -233 cm-1 mode of the B3LYP 2-propanethiyl saddle point (conformer 1) down, at the SAME level as benchmarks/restart_v3/thermal_step.py. B3LYP only: the benchmark's own protocol (M06-2X) is NOT run on any Arm D bond here, so the held-out arm is not looked at."""
import importlib.util, json, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m

core = load("rc", REPO / "benchmarks/restart_v2/restart_core.py")
ts = load("ts", REPO / "benchmarks/restart_v3/thermal_step.py")
ORCA = r"D:\ORCA\orca.exe"

recs = [json.loads(l) for l in (REPO / "benchmarks/restart_v3/artifacts/thermal_step/records.jsonl").read_text().splitlines()]
rad = {r["conformer"]: r for r in recs if r["name"] == "2-propanethiol" and r["role"] == "radical"}

def inp(route, symbols, xyz):
    rows = [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in zip(symbols, xyz)]
    return "\n".join([route, "%pal nprocs 4 end", "%maxcore 3000", "* xyz 0 2", *rows, "*", ""])

def run(tag, text, want_hess=False):
    d = Path(tempfile.mkdtemp(prefix="saddle_"))
    try:
        (d / "job.inp").write_text(text)
        out = subprocess.run([ORCA, "job.inp"], cwd=d, capture_output=True, text=True, timeout=4 * 3600).stdout
        (OUT / f"{tag}.out").write_text(out, encoding="utf-8", errors="replace")
        hess = (d / "job.hess").read_text() if want_hess and (d / "job.hess").exists() else None
        return out, hess
    finally:
        shutil.rmtree(d, ignore_errors=True)

sad = rad[1]
out, hess = run("freq_at_saddle", inp("! B3LYP def2-TZVPD TightSCF Freq", sad["symbols"], sad["coordinates"]), True)
f, vec = core.lowest_mode(hess)
print("mode at the saddle geometry:", f, flush=True)
plus, minus = core.displaced(sad["coordinates"], vec)

def follow(sign, xyz):
    out, _ = run(f"opt_{sign}", inp("! B3LYP def2-TZVPD TightSCF Opt Freq", sad["symbols"], xyz.tolist()))
    p = ts.thermal_from_output(out)
    return sign, p

with ThreadPoolExecutor(2) as pool:
    results = list(pool.map(lambda a: follow(*a), [("plus", plus), ("minus", minus)]))
summary = {"saddle": {"enthalpy": sad["enthalpy"], "lowest_frequency": sad["lowest_frequency"]},
           "conformer0_radical": {"enthalpy": rad[0]["enthalpy"], "lowest_frequency": rad[0]["lowest_frequency"], "h_thermal_kj": rad[0]["h_thermal_kj"]},
           "followed": {s: {"enthalpy": p["enthalpy"], "lowest_frequency": p["lowest_frequency"], "h_thermal_kj": p["h_thermal_kj"], "symbols": p["symbols"], "coordinates": p["coordinates"]} for s, p in results}}
(OUT / "summary.json").write_text(json.dumps(summary, indent=1))
for s, p in results:
    print(s, "enthalpy", p["enthalpy"], "lowest", p["lowest_frequency"], "Hth", round(p["h_thermal_kj"], 2), flush=True)
print("saddle enthalpy", sad["enthalpy"], "conf0", rad[0]["enthalpy"])
