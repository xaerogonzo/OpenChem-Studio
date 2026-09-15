"""Amendment A11, experiment A: Cioslowski's LiH APT charge with Cartesian d functions, in Psi4.

    C:/Users/pmpd/miniconda3/envs/psi4-a11/python.exe benchmarks/charges/rappe_goddard/cioslowski_apt_psi4.py

Runs in the throwaway `psi4-a11` conda environment (Psi4 1.11, conda-forge),
not the project's, and writes tests/fixtures/charges/cioslowski_lih_psi4.csv.
The analysis is `cioslowski_apt.analyse`, the same code experiment B uses.
"""

from __future__ import annotations

import csv
import io
import math
import pathlib

import psi4

HERE = pathlib.Path(__file__).resolve().parent
FIXTURE = HERE.parent.parent.parent / "tests" / "fixtures" / "charges" / "cioslowski_lih_psi4.csv"
STEPS = (0.00025, 0.0005, 0.001, 0.002, 0.004)
BASIS = "6-31++G(d,p)"
OPTIONS = {"basis": "6-31++G**", "puream": False, "reference": "rhf", "scf_type": "pk",
           "e_convergence": 1e-10, "d_convergence": 1e-10, "g_convergence": "gau_tight"}


def molecule(li, r):
    return psi4.geometry(f"""
0 1
Li {li[0]:.10f} {li[1]:.10f} {li[2]:.10f}
H 0.0 0.0 {r:.10f}
units angstrom
symmetry c1
no_reorient
no_com
""")


def main() -> None:
    psi4.set_memory("2 GB")
    # Psi4 writes a ~270 KB log (and timer.dat into the cwd); keep them out of the repository.
    work = pathlib.Path(r"D:\oc-psi4-a11")
    work.mkdir(exist_ok=True)
    psi4.core.set_output_file(str(work / "cioslowski_apt_psi4.log"), False)
    psi4.set_options(OPTIONS)
    mol = molecule((0.0, 0.0, 0.0), 1.6)
    psi4.optimize("scf", molecule=mol)
    xyz = mol.geometry().np * psi4.constants.bohr2angstroms
    r = float(math.dist(xyz[0], xyz[1]))
    rows = [[BASIS, "6d", "optimised", "", "", True, "", "", "", "", f"{r:.8f}"]]
    for h in STEPS:
        for axis in range(3):
            for sign in (+1, -1):
                li = [0.0, 0.0, 0.0]
                li[axis] = sign * h
                energy, wfn = psi4.energy("scf", molecule=molecule(li, r), return_wfn=True)
                dipole = [float(x) for x in wfn.variable("SCF DIPOLE")]
                rows.append([BASIS, "6d", "displaced", h, "xyz"[axis] + ("+" if sign > 0 else "-"), True,
                             f"{energy:.10f}", *[f"{d:.9f}" for d in dipole], f"{r:.8f}"])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["basis", "d_functions", "kind", "h_angstrom", "displacement", "scf_converged", "energy_hartree",
                     "dipole_x_au", "dipole_y_au", "dipole_z_au", "r_LiH_angstrom"])
    writer.writerows(rows)
    # scf_converged is True by construction: Psi4 raises SCFConvergenceError rather than returning.
    FIXTURE.write_text(f"# Amendment A11, experiment A: Psi4 {psi4.__version__} RHF, CARTESIAN d (puream false), run by cioslowski_apt_psi4.py.\n"
                       "# Li at the origin (displaced by +-h), H on +z at the optimised bond length; dipoles are Psi4's SCF DIPOLE in a.u.\n"
                       + buffer.getvalue(), encoding="utf-8", newline="\n")
    print(f"r = {r:.6f} A; wrote {FIXTURE}")


if __name__ == "__main__":
    main()
