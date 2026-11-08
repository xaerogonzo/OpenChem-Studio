"""C1 of `benchmarks/charges/models/eem_second_models_preregistration.md`: the parameters of the two further EEM models equal their sources, exactly.

Model J (Jirouskova 2009, B3LYP/6-31G* Merz-Kollman) has two independent readings of its Table 2: the PDF's text layer (`table2_textlayer.json`, written by
`benchmarks/charges/models/jirouskova_extract.py`) and the page rendered at 300 dpi and typed by hand (`table2.csv`). They must agree on every number. **The
second reading was not blind**: the text-layer numbers had been printed before the page was read, so it is a check on a transcription slip, not on a shared
misreading; the rendered page is what settles a disagreement. Model N (NEEMP 2016, Ccd2016 NPA) is a machine file, so its source IS the file: its hash is held and
its content is read as a parameter table, never retyped.
"""

from __future__ import annotations

import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "charges"
J_CSV = FIXTURES / "jirouskova2009" / "table2.csv"
J_JSON = FIXTURES / "jirouskova2009" / "table2_textlayer.json"
N_PAR = FIXTURES / "neemp2016" / "CCD_gen_DE_RMSD_B3LYP_6311G_NPA.par"
N_PAR_SHA256 = "a0f20738dca189c7b89e4015e40a708b7353697afe1a9d5998ead23fd3b12e47"
N_README = FIXTURES / "neemp2016" / "README.md"

J_TYPES = {("H", 1), ("C", 1), ("C", 2), ("N", 1), ("N", 2), ("O", 1), ("O", 2), ("F", 1), ("Cl", 1), ("Br", 1), ("S", 1), ("Zn", 1)}
N_TYPES = {("H", 1), ("C", 1), ("C", 2), ("C", 3), ("N", 1), ("N", 2), ("N", 3), ("O", 1), ("O", 2), ("F", 1), ("S", 1), ("S", 2), ("Cl", 1), ("Br", 1), ("P", 2)}


def page_reading() -> list[dict]:
    lines = [line for line in J_CSV.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return list(csv.DictReader(lines))


def text_layer() -> dict:
    return json.loads(J_JSON.read_text(encoding="utf-8"))


def neemp_table() -> tuple[float, dict[tuple[str, int], tuple[float, float]]]:
    root = ET.parse(N_PAR).getroot()
    block = root.find("Parameters")
    assert block is not None and block.get("AtomType") == "ElemBond"
    table: dict[tuple[str, int], tuple[float, float]] = {}
    for element in block.findall("Element"):
        symbol = (element.get("Name") or "").strip()
        for bond in element.findall("Bond"):
            key = (symbol, int(bond.get("Type")))
            assert key not in table, f"{key} is listed twice"
            table[key] = (float(bond.get("A")), float(bond.get("B")))
    return float(block.get("Kappa")), table


# --- model J ---------------------------------------------------------------------------------------------------------------------------------


def test_the_two_readings_of_table_2_agree_on_every_number():
    page, layer = page_reading(), text_layer()
    assert len(page) == len(layer["rows"]) == 12
    for typed, machine in zip(page, layer["rows"], strict=True):
        assert (typed["element"], int(typed["bond_order"])) == (machine["element"], machine["bond_order"])
        for column in ("b3lyp", "hf"):
            for key in ("A", "A_pm", "B", "B_pm", "s"):
                assert float(typed[f"{column}_{key}"]) == machine[column][key], (typed["element"], typed["bond_order"], column, key)


def test_the_two_readings_agree_on_kappa_and_on_the_paper_s_own_quality_number():
    layer = text_layer()
    assert (layer["kappa_b3lyp"], layer["kappa_hf"]) == (0.302, 0.227)
    assert layer["ravg_mol"] == [0.941, 0.940]


def test_model_j_has_exactly_the_twelve_atom_types_of_the_papers_table():
    assert {(r["element"], int(r["bond_order"])) for r in page_reading()} == J_TYPES


@pytest.mark.parametrize("column", ["b3lyp", "hf"])
def test_every_hardness_B_is_positive_so_the_stationary_point_is_a_minimum(column):
    # The shipped model is the B3LYP column; HF is held to the same check so a later change of mind starts from a sound table.
    assert all(float(r[f"{column}_B"]) > 0 for r in page_reading())


def test_the_types_that_model_j_lacks_are_absent_not_defaulted():
    types = {(r["element"], int(r["bond_order"])) for r in page_reading()}
    for missing in [("C", 3), ("N", 3), ("S", 2), ("P", 1), ("P", 2), ("B", 1), ("I", 1)]:
        assert missing not in types


# --- model N ---------------------------------------------------------------------------------------------------------------------------------


def test_the_neemp_file_is_the_one_the_plan_registered():
    assert hashlib.sha256(N_PAR.read_bytes()).hexdigest() == N_PAR_SHA256
    assert N_PAR_SHA256 in N_README.read_text(encoding="utf-8")


def test_model_n_is_the_ccd_gen_de_rmsd_npa_set_with_its_kappa():
    kappa, table = neemp_table()
    assert kappa == 0.5125
    assert set(table) == N_TYPES


def test_model_n_has_every_type_that_model_j_refuses_and_still_lacks_boron_and_iodine():
    _, table = neemp_table()
    for gained in [("C", 3), ("N", 3), ("S", 2), ("P", 2)]:
        assert gained in table
    assert not {e for e, _ in table} & {"B", "I", "Zn"}


def test_every_model_n_hardness_is_positive():
    _, table = neemp_table()
    assert all(b > 0 for _, b in table.values())


def test_a_few_numbers_of_the_neemp_file_as_the_plan_read_them():
    _, table = neemp_table()
    assert table[("C", 3)] == (2.6944, 0.6776)
    assert table[("S", 2)] == (2.6471, 0.4512)
    assert table[("Cl", 1)] == (2.7026, 1.1537)
    assert table[("P", 2)] == (2.2933, 0.5759)
