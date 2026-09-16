"""TRIAGE.md 2.6a: freeze Mathieu 2007 Table III (p. 8) and identify its atoms.

    uv run --no-sync python benchmarks/charges/models/mathieu_table3.py

Identification uses the DEPOSITED Mulliken charges only -- no model is run --
so this fixture can exist before any SQE number does. A row's printed
molecule name restricts the files searched; an atom qualifies when its element
is the bold glyph's and its deposited charge is within 5e-4 of the printed
3 dp Q^M. The one row whose bold glyph and value disagree is identified by
value and says so.
"""

from __future__ import annotations

import csv
import io
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import mathieu_eem_check as mec  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "charge_models"
OUT = FIXTURES / "mathieu2007_table3.csv"

#: (set, printed molecule, bold glyph, Q^M, Q_i, Dev, deposited file, element searched, note)
TABLE_III = [
    ("EQ", "NNO", "N", "0.615", "0.247", "-0.367", "N2O", "N", ""),
    ("EQ", "F3C-CN", "C", "0.892", "0.540", "-0.352", "F3C-CN", "C", ""),
    ("EQ", "(NO2)2-CF-CF2-(NO2)", "C", "0.788", "0.481", "-0.307", "trifluorotrinitroethane", "C", "same molecule as O2N-CF2-CF-(NO2)2"),
    ("EQ", "F3C-CO-NH2", "C", "0.797", "0.498", "-0.299", "trifluoroacetamide", "C", ""),
    ("EQ", "F3C-CO-OCH3", "C", "0.803", "0.509", "-0.294", "methyltrifluoroacetate", "C", ""),
    ("EQ", "O2N-CF2-CF2-NO2", "C", "0.725", "0.460", "-0.266", "O2N-CF2-CF2-NO2", "C", ""),
    ("EQ", "(NO2)2-CF-CF-(NO2)2", "C", "0.601", "0.338", "-0.263", "difluorotetranitroethane", "C", ""),
    ("EQ", "CO", "O", "-0.180", "-0.442", "-0.262", "CO", "O", ""),
    ("EQ", "FCCF", "F", "-0.029", "-0.269", "-0.240", "FCCF", "F", ""),
    ("EQ", "O2N-CF2-CF-(NO2)2", "C", "0.535", "0.315", "-0.220", "trifluorotrinitroethane", "C", "same molecule as (NO2)2-CF-CF2-(NO2)"),
    ("EQ", "Guanine", "C", "0.259", "0.054", "-0.205", "guanine", "C", "caption: the carbon alpha to the carbonyl"),
    ("EQ", "N2O", "O", "-0.492", "-0.253", "0.238", "N2O", "O", ""),
    ("EQ", "FCCF", "C", "0.029", "0.269", "0.240", "FCCF", "C", ""),
    ("EQ", "CO", "C", "0.180", "0.442", "0.262", "CO", "C", ""),
    ("EQ", "F3C-CN", "C", "-0.421", "-0.144", "0.277", "F3C-CN", "N",
     "no carbon of F3C-CN is within 5e-4 of -0.421; N6 is (-0.4211): identified by value, glyph and number disagree"),
    ("TS", "H3NO+HONO (Ref. 53)", "N", "-0.425", "-0.650", "-0.225", "JPCA2003-107-5798-TS17", "N", ""),
    ("TS", "HCO+OH (Ref. 52)", "H", "0.387", "0.183", "-0.204", "JPCA_2000_104_10526-ts1", "H", ""),
    ("TS", "H3NO+HONO (Ref. 53)", "O", "-0.547", "-0.306", "0.241", "JPCA2003-107-5798-TS17", "O", ""),
    ("TS", "HCO+OH (Ref. 52)", "O", "-0.780", "-0.494", "0.285", "JPCA_2000_104_10526-ts1", "O", ""),
    ("TS", "F+FNH+C4H9N (Ref. 55)", "F", "-0.501", "-0.161", "0.340", "JPCA_2005_109_4829-TS1", "F", ""),
]
SETS = {"EQ": FIXTURES / "mathieu2007_eq.csv", "TS": FIXTURES / "mathieu2007_ts.csv"}
MATCH = 5e-4


def identify() -> list[list[str]]:
    molecules = {s: mec.molecules(path) for s, path in SETS.items()}
    out = []
    for row in TABLE_III:
        set_name, printed, glyph, qm, qi, dev, file, element, note = row
        atoms = molecules[set_name][file]
        hits = [a for a in atoms if a["element"] == element and abs(float(a["mulliken"]) - float(qm)) <= MATCH + 1e-12]
        assert hits, row
        # A row may name a symmetric pair whose deposited values round alike; every atom of it is gated.
        assert len({round(float(a["mulliken"]), 3) for a in hits}) == 1, row
        for a in hits:
            out.append([set_name, printed, glyph, qm, qi, dev, file, a["atom"], element, a["mulliken"], note])
    return out


def main() -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["set", "printed_molecule", "bold_glyph", "qm_printed", "q_printed", "dev_printed",
                     "file", "atom", "element", "qm_deposited", "note"])
    writer.writerows(identify())
    OUT.write_text("# D. Mathieu, J. Chem. Phys. 2007, 127, 224103, Table III (p. 8), rendered at 300 dpi.\n"
                   "# Atoms identified from deposited Mulliken charges only (TRIAGE.md 2.6a); a pair row gates both atoms.\n"
                   + buffer.getvalue(), encoding="utf-8", newline="\n")
    print(OUT, len(identify()), "atoms")


if __name__ == "__main__":
    main()
