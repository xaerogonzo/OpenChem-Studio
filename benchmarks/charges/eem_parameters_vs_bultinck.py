"""Does Open Babel's `eem.txt` hold the parameters it is labelled with?

    uv run --no-sync python benchmarks/charges/eem_parameters_vs_bultinck.py

`eem.cpp` registers the file as "Bultinck B3LYP/6-31G*/MPA". Bultinck et al.,
J. Phys. Chem. A 2002, 106, 7895 (part II), Table 2, prints chi* and eta* in
eV for H, C, N, O and F from Mulliken charges at B3LYP/6-31G*, with every
chi* shifted so that hydrogen's is 1.00. Only H, C, N, O and F are compared,
because Table 2 prints nothing else.

The file stores A = chi* and B = 2 eta* in Hartree: its matrix is the
paper's eq 1 with kappa = 0.529176 turning 1/R in angstrom into bohr. So
eta* = B x 27.211386 / 2, and chi* is compared as its difference from H,
because a common shift does not change the charges (the paper says so).

A value agrees if it rounds to the printed two decimals (|diff| <= 0.005 eV),
as fixed in `preregistration.md` before this ran.

Measured 2026-09-14:

    H  agrees  N  agrees  F  agrees
    C  differs: eta* 8.971 against 9.00, chi*-chi*_H 4.253 against 4.26
    O  differs: eta* 14.811 against 14.34, chi*-chi*_H 14.261 against 13.72

Part I (J. Phys. Chem. A 2002, 106, 7887) is not held, and C and O may come
from there. That is unchecked, not settled.
"""

import pathlib

import openbabel

#: CODATA 2018 Hartree energy in eV.
HARTREE_EV = 27.211386

#: Bultinck 2002 part II, Table 2, Mulliken column, read from the page rendered
#: at 300 dpi. (chi*, eta*) in eV, chi* shifted so that H is 1.00.
TABLE_2_MULLIKEN = {
    "H": (1.00, 17.95),
    "C": (5.26, 9.00),
    "N": (8.80, 9.39),
    "O": (14.72, 14.34),
    "F": (15.00, 19.77),
}

#: What "agrees" means: the file's value rounds to the printed two decimals.
PRINTED_ROUNDING_EV = 0.005


def main() -> None:
    path = pathlib.Path(openbabel.__file__).parent / "bin" / "data" / "eem.txt"
    rows = {}
    for line in path.read_text().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "*":
            rows.setdefault(parts[0], (float(parts[2]), float(parts[3])))
    hydrogen_a = rows["H"][0]
    print(f"{'':3} {'chi*-chi*_H file':>17} {'Table 2':>8} {'eta* file':>10} {'Table 2':>8}  verdict")
    for element, (chi, eta) in TABLE_2_MULLIKEN.items():
        a, b = rows[element]
        file_chi = (a - hydrogen_a) * HARTREE_EV
        file_eta = b * HARTREE_EV / 2
        agrees = (
            abs(file_chi - (chi - TABLE_2_MULLIKEN["H"][0])) <= PRINTED_ROUNDING_EV
            and abs(file_eta - eta) <= PRINTED_ROUNDING_EV
        )
        print(
            f"{element:3} {file_chi:17.3f} {chi - 1.00:8.2f} {file_eta:10.3f} {eta:8.2f}  "
            f"{'agrees' if agrees else 'DIFFERS'}"
        )
    uncovered = sorted(set(rows) - set(TABLE_2_MULLIKEN) - {"*"})
    shared = sorted(element for element in rows if rows[element] == rows["C"])
    print(f"rows with no value in Table 2: {uncovered}")
    print(f"rows identical to carbon's: {shared}")
    print(f"the (*, *) row, used for ANY element not listed: {rows.get('*')} (hydrogen's is {rows['H']})")


if __name__ == "__main__":
    main()
