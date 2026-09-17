"""Section 8 of `ionescu_src_preregistration.md`: an RHF/6-31G* reference for the charge bound.

    uv run --no-sync python benchmarks/charges/models/ionescu_reference.py

Needs ORCA (`OPENCHEM_ORCA`, default `D:\\ORCA\\orca.exe`) and the Ionescu SI in Sci Downloads.

**What it can and cannot settle is registered in section 8.1 and repeated here, because it is the
easiest thing to forget when reading the output:** ORCA's Mulliken is like-for-like with the E-MPA
models (bar spherical 5d against Gaussian 09's Cartesian 6d); its Hirshfeld is the standard,
non-iterative kind, so against the E-HiI models it is an indicator only; and with no NBO installed
there is no NPA reference at all.

**ORCA is invoked with a backslash path from a directory with no spaces.** It derives where its own
helper binaries live from the path it was called with, and aborts at startup on a forward slash or
a space -- both recorded in this project's notes after costing an hour each.
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ionescu_stability", HERE / "ionescu_stability.py")
stab = importlib.util.module_from_spec(_spec)
sys.modules["ionescu_stability"] = stab
_spec.loader.exec_module(stab)

ORCA = pathlib.WindowsPath(os.environ.get("OPENCHEM_ORCA", r"D:\ORCA\orca.exe"))
#: Section 8.2's three molecules, by their corpus names, so the geometry comes from the same
#: generator the probe used rather than a re-embedding that could reorder atoms.
MOLECULES = ("sulfuric acid (DEA List II.9)", "carbon dioxide", "nitrobenzene")
#: The like-for-like comparison, and the indicator-only one (section 8.1).
MULLIKEN_MODEL = "E-MPA/6-31G*/gas"
HIRSHFELD_MODEL = "E-HiI/6-31G*/gas"

_MULLIKEN = re.compile(r"^\s*(\d+)\s+([A-Za-z]{1,2})\s*:\s*(-?\d+\.\d+)\s*$")
_HIRSHFELD = re.compile(r"^\s*(\d+)\s+([A-Za-z]{1,2})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")


def geometries() -> dict:
    found = {name: None for name in MOLECULES}
    for name, elements, coords in stab.extrapolation():
        if name in found:
            found[name] = (elements, coords)
    validation, _ = stab.regulatory_validation()
    for name, elements, coords in validation:
        if name in found and found[name] is None:
            found[name] = (elements, coords)
    missing = [name for name, geometry in found.items() if geometry is None]
    if missing:
        sys.exit(f"not found in the corpora: {missing}")
    return found


def run_orca(slug: str, elements, coords, workdir: pathlib.Path) -> str:
    lines = ["! RHF 6-31G* TightSCF", "%output Print[P_Hirshfeld] 1 end", "* xyz 0 1"]
    lines += [f"  {e:2s} {x:14.8f} {y:14.8f} {z:14.8f}" for e, (x, y, z) in zip(elements, coords)]
    lines.append("*")
    (workdir / f"{slug}.inp").write_text("\n".join(lines) + "\n", encoding="ascii")
    done = subprocess.run([str(ORCA), f"{slug}.inp"], cwd=str(workdir), capture_output=True, text=True)
    output = done.stdout
    (workdir / f"{slug}.out").write_text(output, encoding="utf-8")
    if "ORCA TERMINATED NORMALLY" not in output:
        sys.exit(f"{slug}: ORCA did not terminate normally (exit {done.returncode})")
    if "SCF CONVERGED" not in output:
        sys.exit(f"{slug}: the SCF did not converge; a population from it would mean nothing")
    return output


def charges(output: str, header: str, pattern: re.Pattern, n: int) -> np.ndarray:
    """The charges from one block, by atom index, refusing anything but exactly n rows."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    values = {}
    for line in lines[start + 1:]:
        match = pattern.match(line)
        if match:
            values[int(match.group(1))] = float(match.group(3))
        elif values and ("Sum of atomic charges" in line or line.strip().startswith("TOTAL")):
            break
    if sorted(values) != list(range(n)):
        sys.exit(f"{header}: parsed atoms {sorted(values)}, expected 0..{n - 1}")
    return np.array([values[i] for i in range(n)])


def main() -> None:
    if " " in str(ORCA):
        sys.exit(f"ORCA path contains a space and will abort at startup: {ORCA}")
    table = stab.ion.table_s1()
    geometry = geometries()
    base = pathlib.Path(tempfile.gettempdir())
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="ionescu_ref_", dir=str(base)))
    if " " in str(workdir):
        sys.exit(f"working directory contains a space and ORCA will abort: {workdir}")

    exceeds = []
    for name in MOLECULES:
        elements, coords = geometry[name]
        slug = name.split(" (")[0].replace(" ", "_")
        output = run_orca(slug, elements, coords, workdir)
        n = len(elements)
        mulliken = charges(output, "MULLIKEN ATOMIC CHARGES", _MULLIKEN, n)
        hirshfeld = charges(output, "HIRSHFELD ANALYSIS", _HIRSHFELD, n)
        mpa = stab.ion.eem_charges(elements, coords, 0.0, table[MULLIKEN_MODEL], "R_angstrom")
        hii = stab.ion.eem_charges(elements, coords, 0.0, table[HIRSHFELD_MODEL], "R_angstrom")

        print(f"\n== {name}   (sum Mulliken {mulliken.sum():+.6f}, sum Hirshfeld {hirshfeld.sum():+.6f})")
        print(f"   {'atom':6s} {'Mulliken':>9s} {MULLIKEN_MODEL:>18s} {'|dq|':>7s}   {'Hirshfeld':>9s} {HIRSHFELD_MODEL:>18s} {'|dq|':>7s}")
        for i, element in enumerate(elements):
            print(f"   {i:>2d} {element:3s} {mulliken[i]:+9.4f} {mpa[i]:+18.4f} {abs(mulliken[i] - mpa[i]):7.4f}   "
                  f"{hirshfeld[i]:+9.4f} {hii[i]:+18.4f} {abs(hirshfeld[i] - hii[i]):7.4f}")
        print(f"   max |q|: Mulliken {np.max(np.abs(mulliken)):.4f}   {MULLIKEN_MODEL} {np.max(np.abs(mpa)):.4f}   "
              f"Hirshfeld {np.max(np.abs(hirshfeld)):.4f}   {HIRSHFELD_MODEL} {np.max(np.abs(hii)):.4f}")
        if np.max(np.abs(mulliken)) > stab.POSITIVE_Q:
            exceeds.append((name, float(np.max(np.abs(mulliken)))))

    print(f"\nORCA outputs kept in {workdir}")
    print(f"\nSECTION 8.3: does RHF/6-31G* Mulliken put |q| > {stab.POSITIVE_Q} on any atom?")
    if exceeds:
        print(f"   YES: {exceeds}")
        print(f"   -> {stab.POSITIVE_Q} cannot be the shipped bound; the decision returns to Alex.")
    else:
        print("   NO.")
        print(f"   -> {stab.POSITIVE_Q} is NOT CONTRADICTED by this reference; the NPA and HiI cases stay unadjudicated.")


if __name__ == "__main__":
    main()
