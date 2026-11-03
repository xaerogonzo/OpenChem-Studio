"""The nitrate-ester and four-arm entries of the COD, outside the census window, as one JSON (counts and rows).

Reads `cod_index.sqlite` (header fields), `cod_structure.sqlite` (the census pass: 273-303 K, a diffraction density, no
pressure) and `cod_nitrate_extra.sqlite` (`cod_nitrate_ester_pass.py`: the organic entries the census skipped that could
hold a nitrate ester, and the C5 entries that could hold a pentaerythrityl core), and writes the rows of every entry that
carries a nitrate-ester group or four identical one-atom arms on a quaternary carbon.

    uv run --no-sync python cod_nitrate_ester_report.py --index .../cod_index.sqlite --structure .../cod_structure.sqlite \
        --extra .../cod_nitrate_extra.sqlite --out ../cod_nitrate_extra.json

A density the header does not carry is computed from the CIF's own cell (`density_from_cell`: Z x M / (N_A x V), M the sum of
the header formula's atomic masses), and labelled `density_source: "cell"`; it is the diffraction density at the cell's own
temperature, not a measurement of anything else. The temperature is the CIF's, never inferred.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from pathlib import Path

#: Atomic masses of the elements an organic CHNO(+halogen) formula holds (IUPAC standard values, enough for a density).
MASS = {"H": 1.008, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Si": 28.085, "P": 30.974, "S": 32.06,
        "Cl": 35.45, "Br": 79.904, "I": 126.904}
AVOGADRO = 6.02214076e23


def formula_counts(formula: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for el, n in re.findall(r"([A-Z][a-z]?)([0-9.]*)", formula or ""):
        out[el] = out.get(el, 0.0) + (float(n) if n else 1.0)
    return out


def _num(text: str, tag: str) -> float | None:
    m = re.search(rf"^{tag}\s+([-0-9.]+)", text, re.MULTILINE)
    return float(m.group(1)) if m else None


def density_from_cell(cif: str, formula: str, z: float | None) -> float | None:
    """Z x M / (N_A x V) in g/cm3 from a CIF's cell lengths and angles; None when any piece is missing."""
    a, b, c = (_num(cif, f"_cell_length_{x}") for x in "abc")
    al, be, ga = (_num(cif, f"_cell_angle_{x}") for x in ("alpha", "beta", "gamma"))
    if None in (a, b, c, al, be, ga) or not z:
        return None
    ca, cb, cg = (math.cos(math.radians(x)) for x in (al, be, ga))
    v = a * b * c * math.sqrt(max(0.0, 1 - ca * ca - cb * cb - cg * cg + 2 * ca * cb * cg))
    counts = formula_counts(formula)
    if not counts or any(el not in MASS for el in counts):
        return None
    m = sum(MASS[el] * n for el, n in counts.items())
    return z * m / (AVOGADRO * v * 1e-24)


def rows(index: Path, structure: Path, extra: Path) -> tuple[list[dict], dict]:
    db = sqlite3.connect(index)
    db.execute("ATTACH DATABASE ? AS s", (str(structure),))
    db.execute("ATTACH DATABASE ? AS x", (str(extra),))
    out: list[dict] = []
    head = ("select c.code, c.formula, c.temperature_k, c.temperature_raw, c.pressure_raw, c.density_diffrn, c.r_gt, c.r_all, "
            "c.year, c.space_group, c.z")
    for r in db.execute(head + ", s.components, s.groups from cod c join s.structure s on s.code = c.code "
                        "where s.groups like '%nitrate_ester%'"):
        out.append(_row(r, "census_window", None, None, None))
    for r in db.execute(head + ", h.components, h.groups, h.four_arm, k.text from cod c join x.hit h on h.code = c.code "
                        "left join x.cif k on k.code = c.code where h.nitrate_ester = 1 or h.four_arm is not null"):
        cif = r[-1]
        out.append(_row(r[:13], "outside_census_window", r[13], r[14], cif))
    counts = {
        "extra_candidates_classified": db.execute("select count(*) from x.hit").fetchone()[0],
        "extra_classification_errors": db.execute("select count(*) from x.hit where error is not null").fetchone()[0],
    }
    return out, counts


def _row(r, where: str, four_arm, groups_extra, cif) -> dict:
    code, formula, t, t_raw, p_raw, dens, r_gt, r_all, year, sg, z, comp, groups = r[:13]
    d_source = "header" if dens is not None else None
    if dens is None and cif:
        dens = density_from_cell(cif, formula, z)
        d_source = "cell" if dens is not None else None
    return {"code": code, "formula": formula, "temperature_k": t, "temperature_raw": t_raw, "pressure_raw": p_raw,
            "density_g_cm3": None if dens is None else round(dens, 4), "density_source": d_source,
            "r_factor": r_gt if r_gt is not None else r_all, "year": year, "space_group": sg, "z": z, "components": comp,
            "groups": groups, "nitrate_ester": "nitrate_ester" in (groups or ""), "four_arm": four_arm if where != "census_window" else None,
            "where": where}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--structure", type=Path, required=True)
    ap.add_argument("--extra", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    data, counts = rows(a.index, a.structure, a.extra)
    data.sort(key=lambda d: (d["formula"], d["code"]))
    ester = [d for d in data if d["nitrate_ester"]]
    single = [d for d in ester if d["components"] in ("single", "single_by_geometry")]
    summary = {
        **counts,
        "nitrate_ester_entries_census_window": sum(1 for d in ester if d["where"] == "census_window"),
        "nitrate_ester_entries_outside_window": sum(1 for d in ester if d["where"] == "outside_census_window"),
        "nitrate_ester_entries_total": len(ester),
        "nitrate_ester_single_component_total": len(single),
        "nitrate_ester_distinct_formulas": len({d["formula"] for d in ester}),
        "nitrate_ester_single_component_distinct_formulas": len({d["formula"] for d in single}),
        "four_arm_entries": sum(1 for d in data if d["four_arm"]),
    }
    a.out.write_text(json.dumps({"summary": summary, "rows": data}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
