"""Builds the halogen arm's references (`benchmarks/restart_v3/PREREGISTRATION.md`) from the SAME saved ATcT 1.228 table, with the first arm's own arithmetic and formula checks.

    python extract_atct_halogen.py "<path to 'ATcT Thermochemical Values ver. 1.228.htm'>"      writes candidates_halogen.json beside this file

THE BONDS WERE CHOSEN FROM THE TABLE'S NAMES AND FORMULAS ALONE, before any of its enthalpies was read or any bond computed: every neutral gas-phase closed-shell parent of at most ten heavy atoms of
H, C, N, O, F, Cl and Br that has a carbon and a halogen and whose radical (the parent minus one hydrogen at one site) is also a gas-phase species of the table. That is six bonds, and the rule
leaves out what the table does not hold, which is most of what one might have wanted: it has no fluoromethyl, difluoromethyl, bromomethyl or tribromomethyl radical, and no chloroethyl, halo-
vinyl or halophenyl radical. The first arm's rule (`extract_atct.py`) did not cover a halogen, so none of these six overlaps it or the first run.

Phosphorus has no usable species in the table and silicon offers three bonds (silane is the first run's; disilane and silanol complete the list), none of them an X-H bond of the calculator's
elements, so neither is pursued. Sulfur is NOT an arm: the table holds no ordinary thiyl radical (no CH3S, no CH3CH2S), only SH from hydrogen sulfide (the first run's) and inorganic HSO/HOS.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import extract_atct as ea

HERE = Path(__file__).resolve().parent

#: (parent's ATcT name, parent SMILES, index of the heavy atom that loses the hydrogen, radical's ATcT name). One line per bond; both names are the table's own.
HALOGEN_PAIRS = [
    ("Chloromethane", "CCl", 0, "Chloromethyl"),
    ("Dichloromethane", "ClCCl", 1, "Dichloromethyl"),
    ("Chloroform", "ClC(Cl)Cl", 1, "Trichloromethyl"),
    ("Fluoroform", "FC(F)F", 1, "Trifluoromethyl"),
    ("Formyl fluoride", "O=CF", 1, "Fluoroformyl"),
    ("Formyl chloride", "O=CCl", 1, "Chloroformyl"),
]


def neutral_gas_row(rows: list[dict], name: str) -> dict:
    """`extract_atct.gas_row` asks for ONE gas-phase row of a name, and the table gives "Formyl fluoride" to the neutral molecule AND to the anion [FCO]-: the neutral one is meant."""
    found = [r for r in rows if r["name"] == name and r["formula"].rstrip().endswith("(g)") and r["units"] == "kJ/mol" and not r["formula"].strip().startswith("[")]
    if len(found) != 1:
        raise SystemExit(f"{name!r}: {len(found)} neutral gas-phase rows")
    return found[0]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = ea.parse_atct(Path(sys.argv[1]))
    ea.gas_row = neutral_gas_row
    ea.PAIRS = HALOGEN_PAIRS
    ea.EXCLUDED = {}
    candidates = ea.build(rows)
    source = "ATcT version 1.228, enthalpies of formation at 298.15 K (kJ/mol), saved 2026-10-22"
    (HERE / "candidates_halogen.json").write_text(json.dumps({"source": source, "bonds": candidates}, indent=1), encoding="utf-8")
    print(f"{len(candidates)} halogen bonds; largest uncertainty {max(c['uncertainty_kcal'] for c in candidates):.2f} kcal/mol")
    for c in candidates:
        print(f'  {c["name"]:50s} DH298 = {c["dh298_kcal"]:7.2f} +- {c["uncertainty_kcal"]:.2f} kcal/mol')


if __name__ == "__main__":
    main()
