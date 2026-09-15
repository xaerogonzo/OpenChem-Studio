"""Amendment A11: Cioslowski's LiH APT charge, reproduced by the PRL's own definition.

    uv run --no-sync python benchmarks/charges/rappe_goddard/cioslowski_apt.py [--run]

`--run` drives ORCA (D:\\ORCA\\orca.exe, working in D:\\oc-orca-a11, both
space-free as ORCA requires) and writes
tests/fixtures/charges/cioslowski_lih_orca.csv. Without it the script reads
only that fixture. ORCA 6.1.1 has no Cartesian d functions (measured), so
these are experiment B (spherical 5d), a diagnostic that gates nothing. The
4-31G cross-check is not run: ORCA has no built-in 4-31G.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "cioslowski_lih_orca.csv"
#: Experiment A (Cartesian d), written by cioslowski_apt_psi4.py in the psi4-a11 environment.
FIXTURE_A = ROOT / "tests" / "fixtures" / "charges" / "cioslowski_lih_psi4.csv"
ORCA = pathlib.Path(r"D:\ORCA\orca.exe")
WORK = pathlib.Path(r"D:\oc-orca-a11")
BOHR = 0.52917721
STEPS = (0.00025, 0.0005, 0.001, 0.002, 0.004)
#: A11's 4-31G cross-check (against 0.6513) is not run: ORCA 6.1.1 has no built-in
#: 4-31G ("UNRECOGNIZED OR DUPLICATED KEYWORD"), and it gated nothing.
BASES = {"6-31++G(d,p)": "5d"}
PRINTED = {"6-31++G(d,p)": 0.6819}


def _run(name: str, text: str) -> str:
    folder = WORK / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.inp").write_text(text, encoding="ascii")
    # str(Path(...)): ORCA derives its helpers' directory from argv[0] and dies on forward slashes.
    result = subprocess.run([str(ORCA), "job.inp"], cwd=str(folder), capture_output=True, text=True)
    (folder / "job.out").write_text(result.stdout, encoding="utf-8")
    return result.stdout


def _parse(out: str) -> tuple[bool, float, tuple[float, float, float]]:
    converged = "SCF CONVERGED" in out and "ORCA TERMINATED NORMALLY" in out
    energy = float(re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", out)[-1])
    dipole = tuple(float(v) for v in re.findall(r"Total Dipole Moment\s*:\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)", out)[-1])
    return converged, energy, dipole


def _single_point(tag: str, basis: str, li: tuple[float, float, float], r: float) -> list:
    header = f"! RHF {basis} TightSCF\n* xyz 0 1\n"
    text = header + f"Li {li[0]:.8f} {li[1]:.8f} {li[2]:.8f}\nH 0.0 0.0 {r:.8f}\n*\n"
    out = _run(tag, text)
    converged, energy, dipole = _parse(out)
    if not converged:
        out = _run(tag, text.replace("TightSCF", "VeryTightSCF"))
        converged, energy, dipole = _parse(out)
    return [converged, f"{energy:.10f}", *[f"{d:.9f}" for d in dipole]]


def run() -> None:
    rows = []
    for basis, dfuncs in BASES.items():
        safe = re.sub(r"[^A-Za-z0-9]", "", basis)
        out = _run(f"{safe}_opt", f"! RHF {basis} TightSCF TightOpt\n* xyz 0 1\nLi 0 0 0\nH 0 0 1.6\n*\n")
        converged = "SCF CONVERGED" in out and "OPTIMIZATION RUN DONE" in out and "ORCA TERMINATED NORMALLY" in out
        xyz = (WORK / f"{safe}_opt" / "job.xyz").read_text(encoding="utf-8").splitlines()[2:4]
        a, b = (tuple(float(v) for v in line.split()[1:4]) for line in xyz)
        r = math.dist(a, b)
        rows.append([basis, dfuncs, "optimised", "", "", converged, "", "", "", "", f"{r:.8f}"])
        for h in STEPS:
            for axis in range(3):
                for sign in (+1, -1):
                    li = [0.0, 0.0, 0.0]
                    li[axis] = sign * h
                    tag = f"{safe}_h{h}_ax{axis}_{'p' if sign > 0 else 'm'}"
                    rows.append([basis, dfuncs, "displaced", h, "xyz"[axis] + ("+" if sign > 0 else "-"),
                                 *_single_point(tag, basis, tuple(li), r), f"{r:.8f}"])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["basis", "d_functions", "kind", "h_angstrom", "displacement", "scf_converged", "energy_hartree",
                     "dipole_x_au", "dipole_y_au", "dipole_z_au", "r_LiH_angstrom"])
    writer.writerows(rows)
    FIXTURE.write_text("# Amendment A11, experiment B: ORCA 6.1.1 RHF, spherical basis functions, run by cioslowski_apt.py --run.\n"
                       "# Li at the origin (displaced by +-h), H on +z at the optimised bond length; dipoles are ORCA's total dipole in a.u.\n"
                       + buffer.getvalue(), encoding="utf-8", newline="\n")


def rows(fixture: pathlib.Path = FIXTURE) -> list[dict[str, str]]:
    lines = [l for l in fixture.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return list(csv.DictReader(lines))


def apt_charge(dipoles: dict[str, tuple[float, float, float]], h_angstrom: float) -> float:
    """(1/3) sum_p [mu_p(+h) - mu_p(-h)] / (2h): eq 9's trace, with h in bohr."""
    h = h_angstrom / BOHR
    return sum((dipoles["xyz"[p] + "+"][p] - dipoles["xyz"[p] + "-"][p]) / (2 * h) for p in range(3)) / 3.0


def analyse(fixture: pathlib.Path = FIXTURE) -> dict[str, dict]:
    data = rows(fixture)
    report = {}
    for basis in BASES:
        mine = [r for r in data if r["basis"] == basis]
        r_opt = float(next(r["r_LiH_angstrom"] for r in mine if r["kind"] == "optimised"))
        charges = {}
        for h in STEPS:
            displaced = {r["displacement"]: tuple(float(r[f"dipole_{k}_au"]) for k in "xyz")
                         for r in mine if r["kind"] == "displaced" and math.isclose(float(r["h_angstrom"]), h)}
            charges[h] = apt_charge(displaced, h)
        stable = [h for h, smaller in zip(STEPS[1:], STEPS[:-1]) if abs(charges[h] - charges[smaller]) <= 1e-5]
        chosen = max(stable) if stable else None
        spread = (max(charges[h] for h in stable + [STEPS[0]]) - min(charges[h] for h in stable + [STEPS[0]])) if stable else math.nan
        bound = max(0.0005, 2 * spread) if stable else math.nan
        value = charges[chosen] if chosen else math.nan
        report[basis] = {"r": r_opt, "charges": charges, "stable": stable, "h": chosen, "Q_Li": value,
                         "printed": PRINTED[basis], "bound": bound,
                         "within": bool(stable) and abs(value - PRINTED[basis]) <= bound,
                         "all_converged": all(r["scf_converged"] == "True" for r in mine)}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    if parser.parse_args().run:
        run()
    for label, fixture in (("A (Cartesian d, Psi4; gates H-e)", FIXTURE_A), ("B (spherical d, ORCA; diagnostic)", FIXTURE)):
      if not fixture.exists():
        continue
      print(f"experiment {label}")
      for basis, rep in analyse(fixture).items():
        print(f"{basis}: r = {rep['r']:.5f} A (Huber r_e 1.5957), converged {rep['all_converged']}")
        for h, q in rep["charges"].items():
            print(f"   h {h:<8} Q_Li {q:+.6f}")
        print(f"   stable {rep['stable']}, h used {rep['h']}, Q_Li {rep['Q_Li']:+.5f} vs printed {rep['printed']} "
              f"(bound {rep['bound']:.5f}): {'within' if rep['within'] else 'OUTSIDE'}")


if __name__ == "__main__":
    main()
