"""TRIAGE.md check 2.1: extract Nistor et al. 2006's supplement, once.

    <a venv with pymupdf>/python benchmarks/charges/models/nistor_extract.py

pymupdf is deliberately not a project dependency (see LESSONS, "`Read` cannot
open a PDF here"), so this runs from a throwaway venv; the functions the tests
import need nothing but the standard library.

Reads `nistor2006_si.pdf.pdf` (the archived UWO Müser group pages) and
`nistor2006.pdf` from Alex's Sci Downloads folder, and writes:

- tests/fixtures/charge_models/nistor2006_si_molecules.csv  every atom row
- tests/fixtures/charge_models/nistor2006_si_sigma.csv      each page's Sigma row
- tests/fixtures/charge_models/nistor2006_table4.csv        the paper's Table IV

The checks themselves live in `tests/test_charge_models_triage.py`, which reads
only the fixtures, so CI never needs the PDFs.
"""

from __future__ import annotations

import csv
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCI = pathlib.Path(r"D:\Xaero Stuff\Documents\Sci Downloads")
OUT = ROOT / "tests" / "fixtures" / "charge_models"

#: The index page's names, in its own numbering (1-21 Si-O-H, 22-30 Si-C-O-H,
#: 31-41 C-O-H), copied as printed -- including the site's unbalanced
#: parentheses, which `formula_counts` reads by a stated rule.
INDEX = {
    1: "Si3H8", 2: "H3SiOSiH3", 3: "(HO)3SiOSiH3", 4: "(H3Si)3SiH", 5: "[(HO)2SiO]3", 6: "SiH4", 7: "Si2H6",
    8: "Si6H12", 9: "(H3SiO)2SiH2", 10: "Si4O4H8", 11: "(OSiH2)3", 12: "Si5O5H10", 13: "(HO)3SiSiH3",
    14: "((HO)3SiO)2Si(OH)2", 15: "Si4O3(OH)8", 16: "Si2(OH)6", 17: "Si3(OH)8", 18: "[(HO)2SiO]4",
    19: "[(HO)3SiO](HO)2SiSi(OH)3", 20: "Si4O2(OH)8", 21: "Si4O(OH)8", 22: "(CH3)3-SiH", 23: "(CH3)3Si)2O",
    24: "(CH3)3Si)2", 25: "(CH3)2SiHC2H5", 26: "(CH3)3SiC2H5", 27: "(CH3)2Si(CH2)2Si(CH3)2", 28: "SiH(CH2)3",
    29: "(CH3)2Si)6", 30: "(CH3)2Si)5", 31: "C5H12", 32: "C3H8", 33: "HO-CH2-OH", 34: "CH3OH", 35: "CH4",
    36: "CH3CH(CH3)2", 37: "CH(OH)3", 38: "C(OH)2(CH3)2", 39: "CH3-C(OH)3", 40: "C(OH)4", 41: "C(CH3)3(OH)",
}


def index_number(code: str) -> int:
    """M0nn -> nn; M20k -> 21 + k; M1kk -> 30 + kk (family sizes 21, 9, 11)."""
    family, number = int(code[1]), int(code[2:])
    return {0: number, 2: 21 + number, 1: 30 + number}[family]


def formula_counts(name: str) -> dict[str, int]:
    """Element counts of an index name. Hyphens are ignored; [ ] act as ( ).
    An unmatched ')' closes a group opened at the start of the name -- the
    site prints "(CH3)3Si)2O" for ((CH3)3Si)2O."""
    text = name.replace("-", "").replace("[", "(").replace("]", ")")
    depth, lowest = 0, 0
    for ch in text:
        depth += 1 if ch == "(" else -1 if ch == ")" else 0
        lowest = min(lowest, depth)
    text = "(" * (-lowest) + text
    tokens = re.findall(r"[A-Z][a-z]?|\d+|\(|\)", text)
    stack: list[dict[str, int]] = [{}]
    k = 0
    while k < len(tokens):
        token = tokens[k]
        if token == "(":
            stack.append({})
        elif token == ")":
            group = stack.pop()
            times = 1
            if k + 1 < len(tokens) and tokens[k + 1].isdigit():
                times = int(tokens[k + 1])
                k += 1
            for element, n in group.items():
                stack[-1][element] = stack[-1].get(element, 0) + n * times
        elif token.isdigit():
            raise ValueError(f"stray count in {name}")
        else:
            times = 1
            if k + 1 < len(tokens) and tokens[k + 1].isdigit():
                times = int(tokens[k + 1])
                k += 1
            stack[-1][token] = stack[-1].get(token, 0) + times
        k += 1
    if len(stack) != 1:
        raise ValueError(f"unbalanced {name}")
    return stack[0]


def rows_by_y(page) -> list[list[str]]:
    rows: dict[float, list] = {}
    for w in page.get_text("words"):
        rows.setdefault(round(w[1], 0), []).append(w)
    return [[w[4] for w in sorted(rows[y], key=lambda w: w[0])] for y in sorted(rows)]


def main() -> None:
    import pymupdf

    si = pymupdf.open(SCI / "nistor2006_si.pdf.pdf")
    atoms, sigmas = [], []
    for page in si:
        lines = rows_by_y(page)
        code = next((l[1] for l in lines if len(l) >= 2 and l[0] == "Molecule:"), None)
        if code is None:
            continue
        code = re.search(r"M\d{3}", code).group(0)
        number = index_number(code)
        for line in lines:
            if len(line) == 10 and line[0].isdigit() and line[1].isdigit():
                atoms.append([number, INDEX[number], code, int(line[0]), int(line[1]), *line[2:]])
            if line and line[0] == "Sigma:":
                sigmas.append([number, INDEX[number], code, *line[1:5]])
    atoms.sort(key=lambda r: (r[0], r[3]))
    sigmas.sort(key=lambda r: r[0])

    paper = " ".join(" ".join(p.get_text().split()) for p in pymupdf.open(SCI / "nistor2006.pdf"))
    start = paper.index("TABLE IV. Atomic charges on the molecule")
    body = paper[start:start + 2500]
    table4 = [[int(m.group(1)), m.group(2), *m.group(3, 4, 5, 6, 7)]
              for m in re.finditer(r"\b(\d{1,2}) (Si|O|C|H) (−?\d\.\d{4}) (−?\d\.\d{4}) (−?\d\.\d{4}) (−?\d\.\d{4}) (−?\d\.\d{4})", body)]
    table4 = [[r[0], r[1], *[v.replace("−", "-") for v in r[2:]]] for r in table4]

    header = ("# Transcribed by benchmarks/charges/models/nistor_extract.py from the archived UWO Muser group pages\n"
              "# (nistor2006_si.pdf.pdf; J. Chem. Phys. 2006, 125, 094108, EPAPS E-JCPSA6-125-520627), read positionally.\n"
              "# Its pages state: \"All information is licenced under the GNU: Reproduction by nonprofit organizations or for academic use.\"\n")
    write(OUT / "nistor2006_si_molecules.csv", header,
          ["index", "name", "code", "atom", "Z", "x", "y", "z", "esp", "i", "ii", "iii", "iv"], atoms)
    write(OUT / "nistor2006_si_sigma.csv", header,
          ["index", "name", "code", "i", "ii", "iii", "iv"], sigmas)
    write(OUT / "nistor2006_table4.csv",
          "# Nistor et al., J. Chem. Phys. 2006, 125, 094108, Table IV (hexamethyldisiloxane), from the text layer.\n",
          ["atom", "element", "ab_initio", "i", "ii", "iii", "iv"], table4)
    print(f"{len(sigmas)} molecules, {len(atoms)} atom rows, Table IV {len(table4)} rows", file=sys.stderr)


def write(path: pathlib.Path, header: str, columns: list[str], rows: list[list]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    path.write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
