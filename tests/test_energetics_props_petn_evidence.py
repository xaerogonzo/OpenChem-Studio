"""The PETN / nitrate-ester evidence hunt for Phase B (`benchmarks/energetics_props/PETN_EVIDENCE.md`).

Held: the rows are well formed (a closed `value_kind`, a source and a locator on every row), every row quotes its value as a
short cell and no row reproduces a table, the committed markdown quotes the same COD counts as the JSON the scripts wrote, the pass that looked for nitrate esters
outside the census window finds the PETN topology and ignores the neopentyl look-alikes, and the draft R1 rule of
preregistration 12.1 is matched by a hydrocarbon (which is why that file says the owner's approval does all the work).
The archive and the books are not here; the logic is.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "benchmarks" / "energetics_props"
VALUE_KINDS = {"measured", "derived_from_measured", "computed", "unlabelled", ""}


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ps = _load("cod_nitrate_ester_pass", DIR / "inventory_scripts" / "cod_nitrate_ester_pass.py")
rp = _load("cod_nitrate_ester_report", DIR / "inventory_scripts" / "cod_nitrate_ester_report.py")
EVIDENCE = json.loads((DIR / "PETN_EVIDENCE.json").read_text(encoding="utf-8"))
COD = json.loads((DIR / "cod_nitrate_extra.json").read_text(encoding="utf-8"))
MD = (DIR / "PETN_EVIDENCE.md").read_text(encoding="utf-8")


def test_every_row_has_a_source_a_locator_and_a_closed_value_kind():
    ids = [r["id"] for r in EVIDENCE["rows"]]
    assert len(ids) == len(set(ids))
    for r in EVIDENCE["rows"]:
        assert r["value_kind"] in VALUE_KINDS, r["id"]
        assert r["source"].strip() and r["locator"].strip(), r["id"]
        assert r["group"].startswith(("A_", "B_", "C_", "D_", "E_", "F_")), r["id"]


def test_every_row_quotes_a_value_but_none_reproduces_a_table():
    """The owner relaxed preregistration section 7 for this file (single measured values, short runs and spreads are quoted
    as facts with their locators); what stays out is a table or running text, so a row's value is a short cell."""
    for r in EVIDENCE["rows"]:
        assert "public" not in r and "value_withheld" not in r, r["id"]
        if r["group"] != "E_not_found":
            assert r["value"] and r["value"].strip(), r["id"]
        assert len(r["value"]) <= 700, f"{r['id']} is longer than a cell of numbers"
        assert len(r["note"]) <= 700, r["id"]


def test_the_supplied_papers_were_read_and_say_so():
    read = [r for r in EVIDENCE["rows"] if r["group"] == "F_papers_read"]
    assert len(read) >= 12
    assert sum("read" in r["source"].lower() for r in read) >= 10


def test_the_markdown_quotes_the_cod_counts_the_json_holds():
    s = COD["summary"]
    marker = (f"<!-- cod_nitrate_extra: total={s['nitrate_ester_entries_total']} outside_window={s['nitrate_ester_entries_outside_window']}"
              f" single={s['nitrate_ester_single_component_total']} formulas={s['nitrate_ester_distinct_formulas']}"
              f" four_arm={s['four_arm_entries']} -->")
    assert marker in MD


def test_the_cod_rows_add_up_to_the_summary():
    rows = COD["rows"]
    s = COD["summary"]
    ester = [r for r in rows if r["nitrate_ester"]]
    assert len(ester) == s["nitrate_ester_entries_total"]
    assert sum(1 for r in ester if r["where"] == "outside_census_window") == s["nitrate_ester_entries_outside_window"]
    assert sum(1 for r in rows if r["four_arm"]) == s["four_arm_entries"]
    assert s["extra_classification_errors"] == 0


@pytest.mark.parametrize(
    ("smiles", "arm"),
    [
        ("C(CO[N+](=O)[O-])(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-]", "O"),  # PETN
        ("C(CO)(CO)(CO)CO", "O"),                                                 # pentaerythritol
        ("C(CBr)(CBr)(CBr)CBr", "Br"),                                            # the tetrabromide
        ("CC(C)(C)C", None),                                                      # neopentane: methyl arms, not CH2-X
        ("C(CO[N+](=O)[O-])(CO[N+](=O)[O-])(CO[N+](=O)[O-])CCl", None),           # three nitrate arms and one chloride: not identical
    ],
)
def test_the_four_arm_detector(smiles, arm):
    assert ps.four_arm_element(Chem.MolFromSmiles(smiles)) == arm


def test_the_wanted_set_is_the_census_complement(tmp_path):
    index, done = tmp_path / "i.sqlite", tmp_path / "d.sqlite"
    db = sqlite3.connect(index)
    db.execute("create table cod (code text, formula text)")
    db.executemany("insert into cod values (?,?)", [
        ("1", "C5 H8 N4 O12"),   # a nitrate ester candidate the census skipped
        ("2", "C5 H12 O4"),      # a C5 pentaerythrityl core, no nitrogen
        ("3", "C6 H6"),          # neither
        ("4", "C5 H8 N4 O12"),   # skipped by the census because it was already classified
        ("5", "C2 H4 N2 O6 Pb"), # a metal: outside the organic set
    ])
    db.commit()
    dd = sqlite3.connect(done)
    dd.execute("create table structure (code text)")
    dd.execute("insert into structure values ('4')")
    dd.commit()
    assert ps.wanted(index, done) == {"1": "ester", "2": "core"}


def test_density_from_a_cell_and_a_missing_cell():
    cif = "_cell_length_a 10.0\n_cell_length_b 10.0\n_cell_length_c 10.0\n_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
    # one carbon atom (12.011 u) in 1000 A^3: 12.011 / (6.02214076e23 * 1e-21) g/cm3
    assert rp.density_from_cell(cif, "C1", 1.0) == pytest.approx(0.019945, rel=1e-3)
    assert rp.density_from_cell(cif, "C1", None) is None
    assert rp.density_from_cell("_cell_length_a 10.0\n", "C1", 1.0) is None
    assert rp.density_from_cell(cif, "Xx1", 1.0) is None


def test_the_draft_r1_rule_is_matched_by_a_hydrocarbon():
    """PREREGISTRATION.md 12.1 says R1 needs the owner's approval of the compound. This is why it must: the rule's structure
    pattern alone is satisfied by 3,3-diethylpentane as well as by PETN and pentaerythritol."""
    text = (DIR / "PREREGISTRATION.md").read_text(encoding="utf-8")
    smarts = re.search(r"`(\[CX4;H0\]\(\[CH2\]\[!#1\]\).*?\[CH2\]\[!#1\])`", text).group(1)
    q = Chem.MolFromSmarts(smarts)
    for smiles, expected in [("CCC(CC)(CC)CC", True), ("C(CO)(CO)(CO)CO", True), ("CC(C)(C)C", False)]:
        assert Chem.AddHs(Chem.MolFromSmiles(smiles)).HasSubstructMatch(q) is expected, smiles
