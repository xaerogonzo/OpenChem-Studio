"""Build `src/openchem/chem/data/eem_ionescu2013.json` from the committed Table S1 fixture.

    uv run --no-sync python tools/build_ionescu_parameters.py          # write
    uv run --no-sync python tools/build_ionescu_parameters.py --check  # fail if the shipped file differs

**Only the models that ship.** `benchmarks/charges/models/ionescu_src_preregistration.md` §10 ships
exactly two of Ionescu et al.'s 24 parameterisations, E-MPA/6-31G*/gas and E-MPA/6-31G**/gas: the two
whose behaviour off the protein-fragment domain was measured (§9). The full table stays in the test
fixture, where the benchmark reproduction and the rework record (§10.5) read it.

Values are parsed from the fixture's printed strings and never rounded or recomputed, so the shipped
number is the printed number.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "ionescu2013" / "table_s1.csv"
OUTPUT = ROOT / "src" / "openchem" / "chem" / "data" / "eem_ionescu2013.json"
#: The paper's own scheme names for the shipped models, in the order they are offered.
SHIPPED = ("E-MPA/6-31G*/gas", "E-MPA/6-31G**/gas")


def build() -> dict:
    raw = FIXTURE.read_bytes()
    rows = [row for row in csv.reader(line for line in raw.decode("utf-8").splitlines() if not line.startswith("#"))]
    header, data = rows[0], rows[1:]
    if header != ["model", "atom_type", "kappa", "A", "B"]:
        sys.exit(f"unexpected fixture header {header}")
    models: dict[str, dict] = {}
    for model, atom_type, kappa, a, b in data:
        if model not in SHIPPED:
            continue
        entry = models.setdefault(model, {"kappa": float(kappa), "types": {}})
        if float(kappa) != entry["kappa"]:
            sys.exit(f"{model}: more than one kappa in the fixture")
        if atom_type in entry["types"]:
            sys.exit(f"{model}: {atom_type} appears twice in the fixture")
        entry["types"][atom_type] = [float(a), float(b)]
    missing = [m for m in SHIPPED if m not in models]
    if missing:
        sys.exit(f"shipped models absent from the fixture: {missing}")
    return {
        "_source_key": "ionescu2013",
        "_note": (
            "Ionescu et al. 2013 Table S1, the two E-typing Mulliken gas-phase models this application "
            "ships (preregistration section 10). A and B are the paper's A_i and B_i = 2(eta0 + delta "
            "eta), in the paper's units, which nobody here has established; r_ij is in angstrom, the "
            "reading that reproduces 36/36. B is NEGATIVE for some elements, which is the published "
            "model and makes its energy non-convex for any structure containing one (section 4)."
        ),
        "_built_by": "tools/build_ionescu_parameters.py",
        "_fixture": "tests/fixtures/charges/ionescu2013/table_s1.csv",
        "_fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "models": {model: models[model] for model in SHIPPED},
    }


def main() -> None:
    text = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            sys.exit(f"{OUTPUT} is stale or hand-edited; re-run without --check")
        print(f"{OUTPUT.name} is current")
        return
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
