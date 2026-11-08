"""Build `src/openchem/chem/data/eem_second_models.json` from the committed fixtures of the two further EEM models.

    uv run --no-sync python tools/build_eem_second_models.py          # write
    uv run --no-sync python tools/build_eem_second_models.py --check  # fail if the shipped file differs

`benchmarks/charges/models/eem_second_models_preregistration.md` section 0 fixes WHICH parameters ship: Model J is the B3LYP/6-31G* Merz-Kollman
column of Jiroušková 2009's Table 2 (the HF column stays in the fixture), Model N is NEEMP 2016's `CCD_gen_DE_RMSD_B3LYP_6311G_NPA.par`. Every number
is the fixture's printed string parsed, never rounded or recomputed, and the fixtures' SHA-256 travel in the file, so a silent edit of either is a
different hash.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
J_FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "jirouskova2009" / "table2.csv"
N_FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "neemp2016" / "CCD_gen_DE_RMSD_B3LYP_6311G_NPA.par"
OUTPUT = ROOT / "src" / "openchem" / "chem" / "data" / "eem_second_models.json"

J_ID = "jirouskova2009_b3lyp_mk"
N_ID = "neemp2016_ccd_gen_npa"
#: The B3LYP column's kappa, printed in the head of Table 2.
J_KAPPA = 0.302


def _model_j() -> dict:
    raw = J_FIXTURE.read_bytes()
    lines = [line for line in raw.decode("utf-8").splitlines() if not line.startswith("#")]
    types: dict[str, list[float]] = {}
    for row in csv.DictReader(lines):
        key = f"{row['element']}{int(row['bond_order'])}"
        if key in types:
            sys.exit(f"{key} appears twice in {J_FIXTURE.name}")
        types[key] = [float(row["b3lyp_A"]), float(row["b3lyp_B"])]
    return {
        "label": "Jiroušková 2009, B3LYP/6-31G* Merz-Kollman",
        "scheme": "B3LYP/6-31G* Merz-Kollman",
        "source_key": "jirouskova2009",
        "kappa": J_KAPPA,
        "types": types,
        "fixture": "tests/fixtures/charges/jirouskova2009/table2.csv",
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _model_n() -> dict:
    raw = N_FIXTURE.read_bytes()
    block = ET.fromstring(raw).find("Parameters")
    if block is None or block.get("AtomType") != "ElemBond":
        sys.exit("the NEEMP file is not an ElemBond parameter set")
    types: dict[str, list[float]] = {}
    for element in block.findall("Element"):
        symbol = (element.get("Name") or "").strip()
        for bond in element.findall("Bond"):
            key = f"{symbol}{int(bond.get('Type'))}"
            if key in types:
                sys.exit(f"{key} appears twice in {N_FIXTURE.name}")
            types[key] = [float(bond.get("A")), float(bond.get("B"))]
    return {
        "label": "NEEMP 2016, Ccd2016 B3LYP/6-311G NPA",
        "scheme": "B3LYP/6-311G NPA",
        "source_key": "neemp2016",
        "kappa": float(block.get("Kappa")),
        "types": types,
        "fixture": "tests/fixtures/charges/neemp2016/CCD_gen_DE_RMSD_B3LYP_6311G_NPA.par",
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
    }


def build() -> dict:
    return {
        "_source_key": "jirouskova2009",
        "_supplementary_source_keys": ["neemp2016"],
        "_note": (
            "Two EEM parameter sets that are NOT extensions of each other or of Bultinck's: each has its own kappa and charge scheme "
            "(benchmarks/charges/models/eem_second_models_preregistration.md). An atom's type is its element plus the highest bond order of any "
            "bond to it in a Kekule structure. A and B are in the papers' units (Pauling units, per the first paper), r_ij is in angstrom (the "
            "reading of NEEMP's solver and of Ionescu's equations; checked against reference charges in check C5)."
        ),
        "_built_by": "tools/build_eem_second_models.py",
        "models": {J_ID: _model_j(), N_ID: _model_n()},
    }


def render(payload: dict) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    text = render(build())
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            sys.exit(f"{OUTPUT} is out of date; run tools/build_eem_second_models.py")
        print("eem_second_models.json is current")
    else:
        OUTPUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUTPUT}")
