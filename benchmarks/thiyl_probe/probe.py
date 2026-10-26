"""Exploratory probe, 2026-10-25 (NOT a benchmark record): why does the methanethiyl radical keep an imaginary mode of about -1300 cm-1?

The bond-dissociation benchmark lost methanethiol's S-H to it, and the displaced restart (benchmarks/restart_diagnosis/) made it WORSE and left the energy where it was. A -1300 cm-1
mode at an ordinary-looking geometry (C-S 1.787 A, three C-H near 1.09 A) is not a soft geometric direction. The hypothesis tested here is that it comes from the ANALYTIC Hessian:
CH3S has a near-degenerate ground state (the two components of a 2E state, split to 2A' and 2A'' once the symmetry is lower), and the coupled-perturbed SCF step divides by orbital-
energy gaps that are nearly zero. Each variant below changes one thing from the benchmark's own setting, at the benchmark's own final geometry, so a difference is attributable.

Run: `uv run --no-sync python benchmarks/thiyl_probe/probe.py OUT_DIR [--structure ID] [variant ...]`. It reads the committed `runs.jsonl` of the benchmarks, writes each ORCA output and a summary.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "benchmarks" / "bde"))
import run_bde as rb  # noqa: E402  (the benchmark's own ORCA path and header)

BASE = "! M062X def2-TZVPD TightSCF DefGrid3"
#: Every committed record file a thiyl radical's geometry can come from (the first benchmark's, and the stress set's).
RUN_FILES = (
    REPO / "benchmarks" / "bde" / "artifacts" / "primary" / "runs.jsonl",
    REPO / "benchmarks" / "restart_v2" / "artifacts" / "stress" / "runs.jsonl",
)
DEFAULT_STRUCTURE = "radical|methanethiol S-H|0"

#: name -> (route line, extra input blocks). One change from the benchmark's `BASE ... Freq` per entry.
VARIANTS: dict[str, tuple[str, str]] = {
    "freq_analytic": (f"{BASE} Freq", ""),                    # the benchmark's own setting: must reproduce about -1328
    "freq_numerical": (f"{BASE} NumFreq", ""),                # finite differences of gradients: no coupled-perturbed SCF
    "sp_stability": (f"{BASE}", "%scf StabPerform true end"),   # is the UKS solution a true minimum in orbital space?
    "sp_guess_hcore": (f"{BASE} HCore", ""),                 # other starting orbitals: do they reach another SCF solution?
    "sp_guess_hueckel": (f"{BASE} Hueckel", ""),
    "sp_guess_patom": (f"{BASE} PAtom", ""),
    "sp_default": (f"{BASE}", ""),
    "freq_b3lyp": ("! B3LYP def2-TZVPD TightSCF DefGrid3 Freq", ""),   # is it the functional? (not a stationary point for B3LYP: only the SPURIOUS size matters)
}


def final_geometry(structure: str) -> list[tuple[str, tuple[float, float, float]]]:
    """The LAST committed record of `structure`: the geometry the benchmark's own run ended on."""
    for path in RUN_FILES:
        recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        found = [r for r in recs if r["structure"] == structure and r.get("symbols") and r.get("coordinates")]
        if found:
            return list(zip(found[-1]["symbols"], (tuple(c) for c in found[-1]["coordinates"])))
    raise SystemExit(f"no record of {structure!r}")


def write_input(path: Path, route: str, extra: str, geometry) -> None:
    lines = [route, "%pal nprocs 4 end", "%maxcore 3000"] + ([extra] if extra else []) + ["* xyz 0 2"]
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in geometry]
    lines += ["*", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def summarise(text: str) -> dict:
    energies = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
    s2 = re.findall(r"Expectation value of <S\*\*2>\s*:\s*(\d+\.\d+)", text)
    block = text.split("VIBRATIONAL FREQUENCIES")[-1].split("NORMAL MODES")[0] if "VIBRATIONAL FREQUENCIES" in text else ""
    freqs = [float(f) for f in re.findall(r"^\s*\d+:\s+(-?\d+\.\d+) cm\*\*-1", block, re.M)]
    stability = ""
    if "tability" in text:
        at = text.index("tability")
        stability = "\n".join(text[max(0, at - 200): at + 1800].splitlines()[:40])
    return {
        "energy": float(energies[-1]) if energies else None,
        "s2": float(s2[-1]) if s2 else None,
        "frequencies": freqs,
        "lowest_frequency": min(freqs) if freqs else None,
        "scf_iterations": len(re.findall(r"^\s*\d+\s+-?\d+\.\d+\s+-?\d+\.\d+", text, re.M)),
        "terminated_normally": "ORCA TERMINATED NORMALLY" in text,
        "stability_excerpt": stability,
    }


def run(name: str, out: Path, geometry) -> dict:
    route, extra = VARIANTS[name]
    workdir = out / name
    workdir.mkdir(parents=True, exist_ok=True)
    write_input(workdir / "job.inp", route, extra, geometry)
    started = time.time()
    done = subprocess.run([rb.ORCA, "job.inp"], cwd=workdir, capture_output=True, text=True, timeout=6 * 3600)
    (workdir / "job.out").write_text(done.stdout, encoding="utf-8", errors="replace")
    return {"variant": name, "route": route, "extra": extra, "seconds": round(time.time() - started, 1), **summarise(done.stdout)}


def main() -> None:
    args = sys.argv[1:]
    out = Path(args.pop(0))
    structure = DEFAULT_STRUCTURE
    if "--structure" in args:
        at = args.index("--structure")
        structure = args[at + 1]
        del args[at: at + 2]
    out.mkdir(parents=True, exist_ok=True)
    names = args or list(VARIANTS)
    geometry = final_geometry(structure)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda n: run(n, out, geometry), names))
    (out / "summary.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    for r in results:
        print(f'{r["variant"]:18s} E={r["energy"]}  <S2>={r["s2"]}  lowest={r["lowest_frequency"]}  {r["seconds"]}s  normal={r["terminated_normally"]}')


if __name__ == "__main__":
    main()
