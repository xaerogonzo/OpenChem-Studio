"""The COD header census for Phase B crystal density (`benchmarks/energetics_props/inventory_scripts/`).

The archive and its index are not in the repository; what is held is the logic that turns an index into counts (the
preregistered temperature window, the element rule, the pressure rule, the distinct-formula floor) and that the committed
counts file is consistent with itself and says what it is not.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "benchmarks" / "energetics_props"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


index = _load("cod_index", DIR / "inventory_scripts" / "cod_index.py")
census = _load("cod_census_headers", DIR / "inventory_scripts" / "cod_census_headers.py")


def test_numbers_drop_their_uncertainty_and_unknowns_are_none():
    assert index.number("293(2)") == 293.0
    assert index.number("1.5") == 1.5
    assert index.number("?") is None and index.number(".") is None and index.number("") is None and index.number(None) is None
    assert index.number("'0.043'") == 0.043


def test_the_header_parser_takes_the_diffraction_temperature_before_the_cell_measurement_one():
    text = "data_1000001\n_cell_measurement_temperature 100\n_diffrn_ambient_temperature 293(2)\n_chemical_formula_sum 'C6 H3 N3 O7'\n"
    f = index.parse(text)
    assert f["code"] == "1000001" and f["formula"] == "C6 H3 N3 O7"
    assert f["temperature_raw"] == "293(2)" and f["temperature_tag"] == "_diffrn_ambient_temperature"
    only_cell = index.parse("data_1\n_cell_measurement_temperature 150\n")
    assert only_cell["temperature_tag"] == "_cell_measurement_temperature"
    assert "formula" not in index.parse("data_2\n_chemical_formula_sum ?\n")


def test_composition_reads_a_formula_or_refuses():
    assert census.composition("C6 H3 N3 O7") == {"C": 6, "H": 3, "N": 3, "O": 7}
    assert census.composition("C12 H10 N2.5") == {"C": 12, "H": 10, "N": 2.5}
    assert census.composition(None) is None and census.composition("") is None


def _rows():
    def row(formula, t, d=1.6, r=0.04, pressure=None, code="x"):
        return {"code": code, "formula": formula, "temperature_k": t, "density_diffrn": d, "r_gt": r, "r_all": None,
                "pressure_raw": pressure, "year": 2000}
    return [
        row("C6 H3 N3 O7", 293.0, code="a"),
        row("C6 H3 N3 O7", 293.0, code="b"),            # a repeat determination: an entry, not a new compound
        row("C3 H6 N6 O6", 273.0, code="c"),            # on the lower edge of the window
        row("C3 H6 N6 O6", 303.0, code="d"),            # on the upper edge
        row("C3 H6 N6 O6", 272.9, code="e"),            # just outside
        row("C3 H6 N6 O6", 303.1, code="f"),
        row("C2 H4 N4 O2", 293.0, pressure="1000000", code="g"),   # a stated pressure
        row("C2 H4 N4 O2", None, code="h"),             # no temperature
        row("C2 H4 N4 O2", 293.0, d=None, code="i"),    # no density
        row("C2 H4 N4 O2", 293.0, r=0.09, code="j"),    # poor fit: kept, only the information cut drops it
    ]


def test_the_funnel_applies_the_preregistered_window_inclusively_and_each_cut_in_order():
    f = census.funnel(_rows())
    assert f["all"]["entries"] == 10
    assert f["with_diffraction_density"]["entries"] == 9
    assert f["temperature_stated"]["entries"] == 8
    assert f["in_273_303_K"]["entries"] == 5 + 0 + 1 and f["in_273_303_K"]["entries"] == 6   # a, b, c, d, g, j
    assert f["and_no_stated_pressure"]["entries"] == 5                                        # g dropped
    assert f["and_R_at_most_0.05"]["entries"] == 4                                            # j dropped by the information cut only
    assert f["and_R_at_most_0.07"]["entries"] == 4
    assert f["and_R_at_most_0.05"]["distinct_formulas"] == 2                                  # a, b share a formula


def test_the_element_rule_is_section_5s_not_phase_as():
    with_metal = census.composition("C4 H4 N4 O4 Cu1")
    assert set(with_metal) - census.ALLOWED == {"Cu"}
    carbon_only_bonds = census.composition("C2 H4 N4 O2")      # carbons bonded only to heteroatoms stay organic here
    assert set(carbon_only_bonds) <= census.ALLOWED and "C" in carbon_only_bonds


def test_census_counts_from_a_real_sqlite_index(tmp_path):
    path = tmp_path / "i.sqlite"
    db = sqlite3.connect(path)
    db.executescript(index.SCHEMA)
    for i, r in enumerate(_rows()):
        db.execute("INSERT INTO cod (code, formula, temperature_k, density_diffrn, r_gt, pressure_raw, year) VALUES (?,?,?,?,?,?,?)",
                   (str(i), r["formula"], r["temperature_k"], r["density_diffrn"], r["r_gt"], r["pressure_raw"], 2000))
    db.execute("INSERT INTO cod (code, formula) VALUES ('m', 'Fe2 O3')")           # not organic
    db.execute("INSERT INTO meta VALUES ('archive', 'x.txz')")
    db.commit()
    db.close()
    out = census.census(path)
    assert out["entries_indexed"] == 11
    assert out["populations"]["organic (section 5 element rule)"]["all"]["entries"] == 10
    assert "composition screen" in " ".join(out["populations"])


def test_the_committed_counts_are_consistent_and_say_what_they_are_not():
    c = json.loads((DIR / "cod_census_headers.json").read_text(encoding="utf-8"))
    assert len(c["archive_sha256"]) == 64 and c["archive"].endswith(".txz")
    assert c["window_k"] == [273.0, 303.0]
    order = ["all", "with_diffraction_density", "temperature_stated", "in_273_303_K", "and_no_stated_pressure"]
    for name, funnel in c["populations"].items():
        entries = [funnel[k]["entries"] for k in ("all", "with_diffraction_density", "temperature_stated")]
        assert entries == sorted(entries, reverse=True), name                         # each cut can only remove entries
        assert funnel["in_273_303_K"]["entries"] <= funnel["temperature_stated"]["entries"]
        assert funnel["and_no_stated_pressure"]["entries"] <= funnel["in_273_303_K"]["entries"]
        assert funnel["and_R_at_most_0.05"]["entries"] <= funnel["and_R_at_most_0.07"]["entries"] <= funnel["and_no_stated_pressure"]["entries"]
        for k in order:
            assert funnel[k]["distinct_formulas"] <= funnel[k]["entries"]
    assert any("not compounds" in s for s in c["caveats"]) and any("CSD" in s or "Cambridge" in s for s in c["caveats"])
    screen = next(v for k, v in c["populations"].items() if k.startswith("composition screen"))
    assert screen["all"]["entries"] < c["populations"]["organic with nitrogen and oxygen"]["all"]["entries"]


@pytest.mark.parametrize("bad", ["window", "pressure"])
def test_the_funnel_is_sensitive_to_its_rules(bad, monkeypatch):
    rows = _rows()
    if bad == "window":
        monkeypatch.setattr(census, "WINDOW_K", (274.0, 302.0))
        assert census.funnel(rows)["in_273_303_K"]["entries"] != 6
    else:
        f = census.funnel([dict(r, pressure_raw="1000000") for r in rows])
        assert f["and_no_stated_pressure"]["entries"] == 0
