"""The second reference column of the held-out arm (`PREREGISTRATION.md` sections 11 item 2 and 14): Luo's handbook [source:luo2007] for the held-out bonds it covers, and Ruscic's sequential-bond paper [source:ruscic2015] against the ATcT 1.228 values the first run's bonds were checked with.

    python second_column.py        prints the comparison and writes second_column.json beside this file

REPORTED ONLY, AND MADE AFTER THE RESULT: the held-out verdict (PASS) and the bias test (-1.53 did not reproduce) were decided by `run_restart.py report` on the ATcT column before any number here was read. Nothing in this file can change them.

HOW THE LUO VALUES WERE READ: each held-out bond's parent was looked up in the handbook's own tables (C-H: 3.1, 3.2, 3.6.x; N-H: 7.1.1; O-H: 6.1.1), the pages rendered and read by eye, because the handbook marks its recommended datum in BOLDFACE and a text extraction loses that. A bond is `used` only when the handbook gives ONE number for it at the gas-phase standard state: a bold recommended datum, or a single entry. A bond with no bold datum among several values, a range from an electrochemical (solution) measurement, a 0 K value and a bond the handbook does not list are reported and not used. The page numbers are the PDF page (the handbook's own printed page is 29 less in chapters 3 and 4, 29 less in chapter 7). Values are kcal/mol with the handbook's own uncertainty where it gives one.

HOW THE RUSCIC VALUES WERE READ: Tables 1-3 of the paper are images, rendered and read; the 298.15 K column in kJ/mol, divided by 4.184.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
KJ_PER_KCAL = 4.184

#: bond name as the held-out report prints it -> what Luo's handbook holds for it.
#: `value` None = not used; `why` says what the handbook shows. `pdf_page` is the PDF page of the handbook.
LUO = {
    "propane C-H (n-Propyl)": {"value": 100.9, "unc": 0.5, "pdf_page": 49, "table": "3.1", "kind": "recommended (boldface)"},
    "ethanol C-H (2-Hydroxyethyl)": {"value": None, "pdf_page": 99, "table": "3.6.1.1", "why": "three values (101.3, 98 +/- 2, 100.8 +/- 2) and none in boldface"},
    "ethanol C-H (1-Hydroxyethyl)": {"value": 95.9, "unc": 1.0, "pdf_page": 99, "table": "3.6.1.1", "kind": "recommended (boldface)"},
    "propene C-H (1-Methylethenyl)": {"value": None, "pdf_page": 55, "table": "3.2", "why": "not listed: the handbook has the terminal vinylic C-H (111.1) and the allylic one, not the central one"},
    "propyne C-H (Propargyl)": {"value": 88.9, "unc": 1.0, "pdf_page": 53, "table": "3.2", "kind": "recommended (boldface)"},
    "propyne C-H (1-Propynyl)": {"value": None, "pdf_page": 53, "table": "3.2", "why": "not listed (only the methyl C-H of propyne)"},
    "methylamine N-H (Methylamidogen)": {"value": 101.6, "unc": 2.0, "pdf_page": 399, "table": "7.1.1", "kind": "recommended (boldface)"},
    "methylamine C-H (Aminomethyl)": {"value": 93.9, "unc": 2.0, "pdf_page": 131, "table": "3.6.2.1", "kind": "recommended (boldface)"},
    "hydrazine N-H (Hydrazino)": {"value": None, "pdf_page": 400, "table": "7.1.1", "why": "the recommended datum is 80.8 +/- 0.3 AT 0 K, not 298 K"},
    "methyl hydroperoxide C-H (Hydroperoxymethyl)": {"value": 98.4, "unc": None, "pdf_page": 129, "table": "3.6.1.5", "kind": "single entry (derived, 2004JAN/ROS)"},
    "n-butane C-H (n-Butyl)": {"value": 100.7, "unc": None, "pdf_page": 49, "table": "3.1", "kind": "recommended (boldface)"},
    "1,3-butadiene C-H (1,3-Butadienyl)": {"value": 114.4, "unc": None, "pdf_page": 55, "table": "3.2", "kind": "single entry (derived, 2004JAN/ROS), assigned to the terminal CH2 by its radical enthalpy of formation (87.1 kcal/mol, against 86.5 from ATcT)"},
    "ethylamine N-H (Ethylamidogen)": {"value": None, "pdf_page": None, "table": "7.1.1", "why": "not listed"},
    "ethylamine C-H (1-Aminoethyl)": {"value": 90.1, "unc": 2.0, "pdf_page": 131, "table": "3.6.2.1", "kind": "recommended (boldface)"},
    "ethylamine C-H (2-Aminoethyl)": {"value": None, "pdf_page": 131, "table": "3.6.2.1", "why": "not listed (only the CH2 next to the nitrogen)"},
    "acetonitrile C-H (Cyanomethyl)": {"value": 97.0, "unc": 1.0, "pdf_page": 135, "table": "3.6.2.2", "kind": "recommended (boldface)"},
    "methoxymethane C-H (Methoxymethyl)": {"value": 96.1, "unc": None, "pdf_page": 102, "table": "3.6.1.2", "kind": "recommended (boldface)"},
    "propionaldehyde C-H (1-Oxopropyl)": {"value": 91.7, "unc": None, "pdf_page": 114, "table": "3.6.1.3", "kind": "single entry (GPA, 1977CUM/KEB)"},
    "dimethyl sulfide C-H ((Methylthio)methyl)": {"value": 93.7, "unc": 1.4, "pdf_page": 155, "table": "3.6.4", "kind": "recommended (boldface)"},
    "hydroxylamine O-H (Aminooxy)": {"value": None, "pdf_page": 290, "table": "6.1.1", "why": "a range, 75-77, from an electrochemical (solution) measurement"},
    "hydroxylamine N-H (Hydroxyamidogen)": {"value": None, "pdf_page": 402, "table": "7.1.1", "why": "a range, 81-82, from an electrochemical (solution) measurement"},
    "acrolein C-H (Acryloyl)": {"value": None, "pdf_page": None, "table": "3.6.1", "why": "not listed"},
    "methanimine N-H (Methyleneamidogen)": {"value": 87.0, "unc": 6.0, "pdf_page": 399, "table": "7.1.1", "kind": "recommended (boldface)"},
    "methanimine C-H (Iminomethyl)": {"value": None, "pdf_page": None, "table": "3.6.2", "why": "not listed (only the N-H)"},
    "ethanimine N-H (Ethylideneamidogen)": {"value": None, "pdf_page": None, "table": "7.1.1", "why": "not listed"},
    "ethanimine C-H (1-Iminoethyl)": {"value": None, "pdf_page": None, "table": "3.6.2", "why": "not listed"},
    "formaldoxime O-H (Formaldiminoxy)": {"value": None, "pdf_page": None, "table": "6.1.2", "why": "not listed"},
    # the three excluded bonds, reported only
    "isocyanic acid N-H (Cyanooxidanyl)": {"value": 110.1, "unc": 0.5, "pdf_page": 399, "table": "7.1.1", "kind": "recommended (boldface)"},
    "hydrazoic acid N-H (Azido radical)": {"value": None, "pdf_page": 399, "table": "7.1.1", "why": "five values (92, <=93, 92.7, <=88.7, 93.7) and none in boldface"},
    "ketene C-H (Ketenyl)": {"value": 105.9, "unc": 2.1, "pdf_page": 114, "table": "3.6.1.3", "kind": "recommended (boldface)"},
}

#: Ruscic 2015 (ATcT version 1.122), Tables 1-3, 298.15 K, kJ/mol: the first run's bonds, against the ATcT 1.228 values the first run's crosscheck holds (`bde_heldout/crosscheck_v1.json`).
RUSCIC_KJ = {
    "methane C-H": ("Table 1, CH3-H", 438.892),
    "ethane C-H": ("Table 2, CH3CH2-H", 421.77),
    "ethene C-H": ("Table 2, CH2=CH-H", 462.46),
    "ethyne C-H": ("Table 2, HC=C-H", 557.709),
    "methanol C-H": ("Table 3, HOCH2-H", 402.14),
    "methanol O-H": ("Table 3, CH3O-H", 440.24),
}


def held_out_rows() -> list[dict]:
    """The held-out report's table: bond, computed, ATcT reference, whether excluded."""
    text = (HERE / "artifacts" / "heldout" / "report.txt").read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        m = re.match(r"^(.+?)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+([+-]\d+\.\d+)(\s+\(excluded\))?\s*$", line)
        if m:
            rows.append({"name": m.group(1).strip(), "calc": float(m.group(2)), "atct": float(m.group(3)), "excluded": bool(m.group(5))})
    return rows


def stats(errors: list[float]) -> dict:
    n = len(errors)
    return {"n": n, "mae": sum(abs(e) for e in errors) / n, "mse": sum(errors) / n} if n else {"n": 0}


def build() -> dict:
    rows = held_out_rows()
    assert len(rows) == 30, f"the held-out report holds {len(rows)} bonds, not 30"
    out, used = [], []
    for row in rows:
        luo = LUO[row["name"]]
        entry = dict(row, luo=luo)
        if luo["value"] is not None and not row["excluded"]:
            entry.update(calc_minus_luo=row["calc"] - luo["value"], calc_minus_atct=row["calc"] - row["atct"], luo_minus_atct=luo["value"] - row["atct"])
            used.append(entry)
        out.append(entry)
    result = {
        "bonds": out,
        "used": len(used),
        "calc_vs_luo": stats([e["calc_minus_luo"] for e in used]),
        "calc_vs_atct_same_bonds": stats([e["calc_minus_atct"] for e in used]),
        "luo_vs_atct": stats([e["luo_minus_atct"] for e in used]),
        "listed_not_used": [e["name"] for e in out if not e["excluded"] and e["luo"]["value"] is None and e["luo"].get("pdf_page")],
        "not_listed": [e["name"] for e in out if not e["excluded"] and not e["luo"].get("pdf_page")],
    }
    cross = {c["bond"]: c for c in json.loads((HERE.parent / "bde_heldout" / "crosscheck_v1.json").read_text(encoding="utf-8"))}
    ruscic = []
    for bond, (where, kj) in RUSCIC_KJ.items():
        kcal = kj / KJ_PER_KCAL
        ruscic.append({"bond": bond, "where": where, "ruscic_kcal": kcal, "atct_1228_kcal": cross[bond]["atct_dh298"], "difference": kcal - cross[bond]["atct_dh298"]})
    result["ruscic_vs_atct_1228"] = ruscic
    return result


def main() -> None:
    result = build()
    (HERE / "second_column.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"Luo covers {result['used']} of the 27 deciding bonds with one usable number")
    for key in ("calc_vs_luo", "calc_vs_atct_same_bonds", "luo_vs_atct"):
        s = result[key]
        print(f"  {key:26s} n={s['n']} MAE={s['mae']:.2f} MSE={s['mse']:+.2f}")
    print("listed, not used:", "; ".join(result["listed_not_used"]))
    print("not listed:", "; ".join(result["not_listed"]))
    print("Ruscic 2015 (kcal/mol) against ATcT 1.228:")
    for r in result["ruscic_vs_atct_1228"]:
        print(f"  {r['bond']:14s} {r['ruscic_kcal']:8.3f} {r['atct_1228_kcal']:8.3f} {r['difference']:+.3f}")
    print(f"{'bond':46s} {'calc':>7s} {'ATcT':>7s} {'Luo':>7s}")
    for e in result["bonds"]:
        luo = e["luo"]["value"]
        print(f"{e['name'][:46]:46s} {e['calc']:7.2f} {e['atct']:7.2f} {'-' if luo is None else f'{luo:7.1f}':>7s}{'  (excluded)' if e['excluded'] else ''}")


if __name__ == "__main__":
    main()
