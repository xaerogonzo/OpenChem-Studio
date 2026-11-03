"""Stage 1b of the COD census for Phase B crystal density: counts from the HEADER index only.

Reads the SQLite index `cod_index.py` wrote and counts, with no structure perception, how many Crystallography Open
Database entries could ever be crystal-density labels under `benchmarks/energetics_props/PREREGISTRATION.md` section 3.2:
organic by section 5's element rule, a diffraction density, a stated temperature in 273-303 K, no stated non-ambient
pressure, and (as information, not a rule) the fit quality. It scores nothing and chooses nothing.

**What these counts are and are not.**
* They are ENTRIES, not compounds: COD holds repeat determinations of one compound, salts, solvates and co-crystals. The
  distinct-formula figure is a FLOOR on distinct compounds (isomers share a formula), not an estimate of them.
* "Composition screen" is not a structure test and not a definition of an energetic material: it is the cheapest cut that
  shows the order of magnitude. Which entries are nitro, azide, azole etc. needs the structure (stage 2).
* The population of the preregistration is *known energetic compounds with a measured value in the held literature*; COD
  entries that merely look nitrogen-rich are a DIFFERENT population and would be reported as a separate stratum.

    python -I cod_census_headers.py --index ".../index/cod_index.sqlite" --sha256 ".../cod-cifs-mysql.txz.sha256" --out cod_census_headers.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

#: Section 5: "organic" = carbon and no element outside this set.
ALLOWED = frozenset({"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I"})
WINDOW_K = (273.0, 303.0)
R_CUTS = (0.05, 0.07)


def composition(formula: str | None) -> dict[str, float] | None:
    """`C6 H3 N3 O7` -> element counts, or None for an empty or unreadable formula."""
    if not formula:
        return None
    out: dict[str, float] = {}
    for element, n in re.findall(r"([A-Z][a-z]?)([0-9.]*)", formula):
        try:
            out[element] = out.get(element, 0.0) + (float(n) if n else 1.0)
        except ValueError:
            return None
    return out


def _r(row) -> float | None:
    """The fit quality used for the information cut: the R factor for observed data, else the all-data one."""
    return row["r_gt"] if row["r_gt"] is not None else row["r_all"]


def funnel(rows: list[dict]) -> dict:
    """The same cuts, in order, for any set of rows; each count is of ENTRIES, with a distinct-formula floor."""
    def step(subset):
        return {"entries": len(subset), "distinct_formulas": len({r["formula"] for r in subset})}

    with_density = [r for r in rows if r["density_diffrn"]]
    stated = [r for r in with_density if r["temperature_k"] is not None]
    window = [r for r in stated if WINDOW_K[0] <= r["temperature_k"] <= WINDOW_K[1]]
    ambient = [r for r in window if not r["pressure_raw"]]
    out = {"all": step(rows), "with_diffraction_density": step(with_density), "temperature_stated": step(stated),
           "in_273_303_K": step(window), "and_no_stated_pressure": step(ambient)}
    for cut in R_CUTS:
        kept = [r for r in ambient if _r(r) is not None and _r(r) <= cut]
        out[f"and_R_at_most_{cut}"] = step(kept)
    return out


def census(index: Path) -> dict:
    db = sqlite3.connect(index)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute(
        "select code, formula, temperature_k, density_diffrn, r_gt, r_all, pressure_raw, year from cod")]
    comps = [(r, composition(r["formula"])) for r in rows]
    organic = [r for r, c in comps if c and "C" in c and set(c) <= ALLOWED]
    with_n = [r for r, c in comps if c and "C" in c and set(c) <= ALLOWED and "N" in c]
    with_no = [r for r, c in comps if c and "C" in c and set(c) <= ALLOWED and "N" in c and "O" in c]
    screen = [r for r, c in comps if c and "C" in c and set(c) <= ALLOWED and c.get("N", 0) >= 3
              and c.get("N", 0) + c.get("O", 0) >= c["C"]]
    years = sorted(r["year"] for r in rows if r["year"])
    meta = dict(db.execute("select key, value from meta").fetchall())
    return {
        "archive": meta.get("archive"), "entries_indexed": len(rows), "entries_with_a_formula": sum(1 for _, c in comps if c),
        "latest_journal_year": years[-1] if years else None,
        "window_k": list(WINDOW_K), "r_cuts_for_information": list(R_CUTS),
        "populations": {
            "organic (section 5 element rule)": funnel(organic),
            "organic with nitrogen": funnel(with_n),
            "organic with nitrogen and oxygen": funnel(with_no),
            "composition screen: N >= 3 and N + O >= C (not a structure test)": funnel(screen),
        },
        "caveats": [
            "entries, not compounds: repeat determinations, salts, solvates and co-crystals are all counted",
            "the composition screen is a cut on the formula, not a definition of an energetic material",
            "COD overlaps the Cambridge Structural Database, so CSD-trained density methods stay unevaluable on COD labels",
            "no disorder, form or quality review has been applied; R factors are shown for information, not as a rule",
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--sha256", type=Path, default=None, help="the file holding the archive's SHA-256")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    result = census(args.index)
    if args.sha256 and args.sha256.exists():
        result["archive_sha256"] = args.sha256.read_text(encoding="utf-8").strip().splitlines()[-1].strip()
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
