"""Stage 2b of the COD census: counts by family and component class from the structure pass.

Joins `cod_index.sqlite` (header fields) with `cod_structure.sqlite` (what `cod_structure_pass.py` found) for the
candidate set: organic with nitrogen, a diffraction density, a stated temperature in 273-303 K, no stated pressure.
Every count is of ENTRIES with a distinct-formula floor beside it (isomers share a formula, so the floor is not an estimate
of distinct compounds), and each is given for all candidates and for the single-component subset, which is the only one
that could be in a primary cohort (`PREREGISTRATION.md` section 5: neutral, single-component).

    python -I cod_census_structures.py --index .../cod_index.sqlite --structure .../cod_structure.sqlite --out cod_census_structures.json

What this does not say: an entry that carries a group is a compound with that group, not an energetic material; C-nitro is
one count (nitroaromatic and nitroaliphatic need bond orders); the geometry fallback for entries with no moiety formula is
reported apart from the CIF's own moiety; no disorder, form or fit-quality review has been applied.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

FAMILIES = ("nitrate_ester", "nitramine", "c_nitro", "azide", "n_rich_heterocycle", "halogenated", "other_organic")
SINGLE = ("single", "single_by_geometry")
#: The groups that make a compound explosophoric on their own. A ring with two nitrogens is NOT one: imidazole, pyrimidine and
#: piperazine are ordinary heterocycles, so `n_rich_heterocycle` is counted but never folded into this row.
EXPLOSOPHORE_FAMILIES = ("nitrate_ester", "nitramine", "c_nitro", "azide")
EXPLOSOPHORE_LABEL = "ANY explosophore group (nitrate ester, nitramine, C-nitro or azide)"
R_CUT = 0.07


def census(index: Path, structure: Path) -> dict:
    db = sqlite3.connect(index)
    db.execute("ATTACH DATABASE ? AS s", (str(structure),))
    rows = db.execute(
        "select c.code, c.formula, c.r_gt, c.r_all, s.components, s.family, s.groups, s.error "
        "from cod c join s.structure s on s.code = c.code").fetchall()
    out: dict = {"candidates_classified": len(rows), "errors": sum(1 for r in rows if r[7]), "by_components": defaultdict(int)}
    cells: dict = defaultdict(lambda: {"entries": 0, "formulas": set(), "r_at_most": 0, "r_formulas": set()})
    for code, formula, r_gt, r_all, comp, family, groups, error in rows:
        out["by_components"][comp] += 1
        if error:
            continue
        r = r_gt if r_gt is not None else r_all
        for scope in ("all_candidates", "single_component"):
            if scope == "single_component" and comp not in SINGLE:
                continue
            labels = {family}
            if family in EXPLOSOPHORE_FAMILIES:
                labels.add(EXPLOSOPHORE_LABEL)
            for fam in labels:
                cell = cells[(scope, fam)]
                cell["entries"] += 1
                cell["formulas"].add(formula)
                if r is not None and r <= R_CUT:
                    cell["r_at_most"] += 1
                    cell["r_formulas"].add(formula)
    table: dict = {}
    for (scope, fam), c in sorted(cells.items()):
        table.setdefault(scope, {})[fam] = {
            "entries": c["entries"], "distinct_formulas": len(c["formulas"]),
            f"entries_with_R_at_most_{R_CUT}": c["r_at_most"], f"distinct_formulas_with_R_at_most_{R_CUT}": len(c["r_formulas"])}
    out["by_components"] = dict(out["by_components"])
    out["families"] = table
    out["family_order"] = list(FAMILIES)
    out["explosophore_families"] = list(EXPLOSOPHORE_FAMILIES)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--structure", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    result = census(args.index, args.structure)
    result["caveats"] = [
        "entries, not compounds: repeat determinations are counted; the distinct-formula figure is a floor",
        "a group present is not an energetic material; C-nitro is one count (nitroaromatic vs nitroaliphatic needs bond orders)",
        "n_rich_heterocycle (a ring with two or more nitrogens) is dominated by ordinary heterocycles and is NOT counted as explosophoric",
        "connectivity from Open Babel only: its bond orders were measured unusable, so no pattern depends on them",
        ("single_component = the CIF's moiety formula lists one uncharged component (single) or, with no moiety, a whole molecule"
        " with exactly the header formula exists in the cell (single_by_geometry)"),
        "candidates require nitrogen: organic peroxides without nitrogen are not looked for",
        "no disorder, polymorph, hydrate or fit-quality review has been applied; COD overlaps the CSD",
    ]
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
