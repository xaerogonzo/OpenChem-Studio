"""tools/naming_variants.py: the population generator and the atom-order diagnostic.

The operators are the naming rounds' own eligibility tests, so each is pinned on a structure it must change and one it must leave
alone. The frozen guard and the canonicalisation bypass are the two things that can fail silently, and each has a test that fails
if it is removed. Everything but one test runs without a JRE: the namer and the reader are injected.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from rdkit import Chem, RDLogger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_populations as populations  # noqa: E402
import naming_variants as nv  # noqa: E402

RDLogger.DisableLog("rdApp.*")


def canon(smiles: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


def outputs(operator, smiles: str) -> tuple[set[str], list[str]]:
    """(canonical SMILES the operator makes, the skip reasons it gave) for one structure."""
    mol = Chem.MolFromSmiles(smiles)
    made, skipped = set(), []
    for candidate in operator(mol):
        if candidate.mol is None:
            skipped.append(candidate.skip)
        else:
            made.add(Chem.MolToSmiles(candidate.mol))
    return made, skipped


# --- the operators --------------------------------------------------------------------------------------------------------------------

def test_swap_hetero_replaces_a_non_aromatic_ring_atom():
    made, _ = outputs(nv.swap_hetero, "C1CCCCC1")
    assert canon("C1CCOCC1") in made and canon("C1CCNCC1") in made and canon("C1CCSCC1") in made


def test_swap_hetero_leaves_an_aromatic_ring_and_a_chain_alone():
    assert outputs(nv.swap_hetero, "c1ccccc1") == (set(), [])
    assert outputs(nv.swap_hetero, "CCCC") == (set(), [])


def test_swap_hetero_refuses_an_oxygen_on_a_bridgehead_but_allows_a_nitrogen():
    """Round 32's degree rule: O and S need degree 2 or less, N three or less. Norbornane has two bridgeheads of degree 3, so the
    O and S swaps there (four sites) are skipped, and the N swap is not."""
    made, skipped = outputs(nv.swap_hetero, "C1CC2CCC1C2")
    assert skipped.count("degree too high for the element") == 4
    assert canon("C1CC2CCC1N2") in made and canon("C1CC2CCC1O2") in made  # the CH2 bridge (degree 2) takes any of the three
    assert sum("N" in s for s in made) == 3  # the three symmetry-distinct positions: the one-carbon bridge, a bridgehead, a two-carbon bridge



def test_protonate_aromatic_n_makes_the_nh_cation_and_the_n_methyl_cation():
    made, _ = outputs(nv.protonate_aromatic_n, "c1ccncc1")
    assert canon("c1cc[nH+]cc1") in made and canon("C[n+]1ccccc1") in made


def test_protonate_aromatic_n_skips_a_pyrrole_type_nitrogen_and_a_carbocycle():
    _, skipped = outputs(nv.protonate_aromatic_n, "c1cc[nH]c1")
    assert skipped == ["aromatic N already carries a hydrogen"]
    assert outputs(nv.protonate_aromatic_n, "c1ccccc1") == (set(), [])


def test_protonate_sp3_nh_takes_a_secondary_amine_only():
    made, _ = outputs(nv.protonate_sp3_nh, "C1CCNCC1")
    assert made == {canon("C1CC[NH2+]CC1")}
    assert outputs(nv.protonate_sp3_nh, "CN1CCCCC1") == (set(), [])  # tertiary: no hydrogen to count
    assert outputs(nv.protonate_sp3_nh, "c1cc[nH]c1") == (set(), [])  # aromatic


def test_protonate_ring_imine_takes_a_ring_c_equals_n_only():
    made, _ = outputs(nv.protonate_ring_imine, "C1CCN=C1")
    assert canon("C1CC[NH+]=C1") in made and canon("C[N+]1=CCCC1") in made
    assert outputs(nv.protonate_ring_imine, "CC=NC") == (set(), [])  # acyclic
    assert outputs(nv.protonate_ring_imine, "c1ccncc1") == (set(), [])  # aromatic


def test_add_substituent_puts_each_fixed_group_on_every_carbon_with_a_hydrogen():
    made, _ = outputs(nv.add_substituent, "CC")
    assert {canon(s) for s in ("CCC", "CCN", "CCO", "CCCl", "CCc1ccccc1", "CCC(C)=O", "CCNC(C)=O")} <= made
    assert outputs(nv.add_substituent, "ClC(Cl)(Cl)Cl") == (set(), [])  # no carbon with a hydrogen


@pytest.mark.parametrize("name", list(nv.OPERATORS))
def test_an_operator_does_not_change_its_input_and_every_output_parses(name):
    smiles = "C1CC2CC(C1)c1ccccc12"
    mol = Chem.MolFromSmiles(smiles)
    before = Chem.MolToSmiles(mol)
    for candidate in nv.OPERATORS[name](mol):
        if candidate.mol is not None:
            assert Chem.MolFromSmiles(Chem.MolToSmiles(candidate.mol)) is not None
    assert Chem.MolToSmiles(mol) == before


def test_parse_ops_reads_stages_and_alternatives_and_refuses_the_unknown():
    assert nv.parse_ops("add_substituent>protonate_sp3_nh,swap_hetero") == [["add_substituent"], ["protonate_sp3_nh", "swap_hetero"]]
    with pytest.raises(ValueError, match="unknown operator"):
        nv.parse_ops("swap_hetero>explode")
    with pytest.raises(ValueError, match="empty stage"):
        nv.parse_ops("swap_hetero>")


# --- the population: dedup, provenance, order, accounting -----------------------------------------------------------------------------

@pytest.fixture
def no_frozen(monkeypatch):
    monkeypatch.setattr(populations, "frozen_membership", lambda: {})


def test_a_structure_made_twice_is_one_entry_with_both_origins(no_frozen):
    """Two seeds that share a ring make the same oxane: one row, two origins, and the count says so."""
    built = nv.build_population(["C1CCCCC1", "C1CCCCC1"], nv.parse_ops("swap_hetero"))
    entry = built["population"][canon("C1CCOCC1")]
    # six equivalent ring atoms, from each of two seeds: twelve origins of one structure
    assert entry["origin_count"] == 12 and {o["seed"] for o in entry["origins"]} == {"s0", "s1"}
    assert entry["origins"][0]["path"][0]["op"] == "swap_hetero"


def test_row_ids_are_unique_and_stable_and_the_population_is_sorted(no_frozen):
    a = nv.build_population(["C1CCCCC1", "C1CCNCC1"], nv.parse_ops("swap_hetero,add_substituent"))
    b = nv.build_population(["C1CCNCC1", "C1CCCCC1"], nv.parse_ops("swap_hetero,add_substituent"))
    ids = [v["id"] for v in a["population"].values()]
    assert len(ids) == len(set(ids)) > 30
    assert list(a["population"]) == sorted(a["population"])
    assert {c: v["id"] for c, v in a["population"].items()} == {c: v["id"] for c, v in b["population"].items()}


def test_a_chain_keeps_only_the_last_stage_and_records_the_path(no_frozen):
    built = nv.build_population(["C1CCNC1"], nv.parse_ops("add_substituent>protonate_sp3_nh"))
    cation = canon("CC1CC[NH2+]C1")
    assert cation in built["population"]
    assert "C1CCNC1" not in built["population"]  # the seed is not in the population
    assert all("+" in c for c in built["population"])
    path = built["population"][cation]["origins"][0]["path"]
    assert [step["op"] for step in path] == ["add_substituent", "protonate_sp3_nh"]
    assert built["intermediates"][path[1]["on"]] == canon("CC1CCNC1")


def test_yield_counts_every_site_once_and_credits_a_structure_to_its_first_maker(no_frozen):
    built = nv.build_population(["C1CCCCC1"], nv.parse_ops("swap_hetero"))
    y = built["yield"]["swap_hetero"]
    assert y["attempted"] == 18 and y["skipped"] == 0 and y["unique"] == 3 and y["duplicate"] == 15
    assert y["attempted"] == y["skipped"] + y["refused"] + y["duplicate"] + y["unique"]


def test_a_seed_that_does_not_parse_is_reported_not_raised(no_frozen):
    built = nv.build_population(["not a molecule(", "CC"], nv.parse_ops("add_substituent"))
    assert built["invalid_seeds"] == ["not a molecule("] and built["seeds"] == {"s1": "CC"}


# --- the frozen guard -----------------------------------------------------------------------------------------------------------------

def frozen_registry(*smiles: str):
    salt = "test-salt"
    return lambda: {"fake_frozen": (salt, frozenset(populations.membership_hash(canon(s), salt) for s in smiles))}


def test_a_frozen_seed_is_refused_before_anything_is_generated_from_it(monkeypatch):
    monkeypatch.setattr(populations, "frozen_membership", frozen_registry("C1CCCCC1"))
    built = nv.build_population(["C1CCCCC1", "C1CCNCC1"], nv.parse_ops("swap_hetero"))
    assert built["refused"] == {"s0": {"kind": "seed", "population": "fake_frozen"}}
    assert built["seeds"] == {"s1": "C1CCNCC1"}
    assert canon("C1CCOCC1") not in built["population"] or all(o["seed"] == "s1" for o in built["population"][canon("C1CCOCC1")]["origins"])
    assert all(o["seed"] != "s0" for v in built["population"].values() for o in v["origins"])


def test_a_generated_structure_that_is_frozen_is_refused_and_never_reaches_the_namer(monkeypatch):
    monkeypatch.setattr(populations, "frozen_membership", frozen_registry("CCO"))
    built = nv.build_population(["CC"], nv.parse_ops("add_substituent"))
    assert "CCO" not in built["population"]
    assert list(built["refused"].values()) == [{"kind": "generated", "population": "fake_frozen"}]
    assert built["yield"]["add_substituent"]["refused"] == 2  # ethane's two equivalent carbons are two sites; one structure


def test_main_names_nothing_frozen_prints_no_smiles_for_it_and_exits_3(monkeypatch, capsys):
    """The whole command: the rows handed to the scanner exclude the frozen structure, and the refusal line carries an id, not a SMILES."""
    monkeypatch.setattr(populations, "frozen_membership", frozen_registry("CCO"))
    named: list[str] = []

    def fake_scan(rows, *, names_only=False):
        named.extend(row["smiles"] for row in rows)
        return {row["label"]: {"smiles": row["smiles"], "name": "x", "back": None, "cls": "exact"} for row in rows}

    monkeypatch.setattr(nv.census_scan, "scan", fake_scan)
    assert nv.main(["CC", "--ops", "add_substituent", "--names-only"]) == 3
    out = capsys.readouterr().out
    assert "CCO" not in named and "CCC" in named
    assert "FROZEN" in out and "fake_frozen" in out
    assert not any(line.startswith("FROZEN") and "CCO" in line for line in out.splitlines())


def test_the_guard_reads_the_membership_once_per_run_not_once_per_structure(monkeypatch):
    calls = []
    monkeypatch.setattr(populations, "frozen_membership", lambda: calls.append(1) or {})
    nv.build_population(["C1CCCCC1"], nv.parse_ops("swap_hetero,add_substituent"))
    assert calls == [1]


# --- the ordering diagnostic ----------------------------------------------------------------------------------------------------------

def test_spellings_are_random_but_each_is_the_same_structure_and_the_seed_reproduces_them():
    canonical = canon("CCC(C)c1ccc(C(CC)CC)cc1")
    first = nv.spellings(canonical, 12, 5)
    assert nv.spellings(canonical, 12, 5) == first
    assert len(set(first)) > 1  # not twelve copies of one string
    key = Chem.MolToInchiKey(Chem.MolFromSmiles(canonical))
    assert all(Chem.MolToInchiKey(Chem.MolFromSmiles(s)) == key for s in first)
    assert nv.spellings(canonical, 12, 6) != first


def test_a_spelling_is_given_to_the_namer_exactly_as_written():
    """THE BYPASS TEST. A namer whose answer depends on the exact string must be able to disagree with itself. If the diagnostic
    canonicalised on the way in (as `naming_census_scan.name_rows` does), every spelling would arrive as one string, the report
    would find one name, and this test would fail."""
    seen: list[str] = []

    def order_dependent(smiles: str) -> str:
        seen.append(smiles)
        return f"name-of-{smiles[:1]}"

    canonical = canon("CCC(C)c1ccc(C(CC)CC)cc1")
    report = nv.order_report({"x": canonical}, 20, 3, namer=order_dependent)["x"]
    assert report["distinct_names"] > 1
    assert len(set(seen)) > 1 and canonical in seen
    assert report["valid_samples"] == 21  # the canonical spelling and 20 random ones


def test_name_census_scan_name_rows_would_have_hidden_it():
    """Why the diagnostic does not use it: name_rows canonicalises, so two spellings of one structure come back as one SMILES."""
    first, second = nv.spellings(canon("CCC(C)c1ccc(C(CC)CC)cc1"), 2, 1)
    assert first != second
    rows = nv.census_scan.name_rows([{"label": "a", "smiles": first}, {"label": "b", "smiles": second}])
    assert rows["a"]["smiles"] == rows["b"]["smiles"]


def test_a_stable_namer_reports_one_name_and_the_report_says_how_to_reproduce_it():
    report = nv.order_report({"x": canon("CCO")}, 8, 11, namer=lambda s: "ethanol")["x"]
    assert report["distinct_names"] == 1 and report["seed"] == 11 and report["requested"] == 8
    assert report["names"][0]["spellings"][0] == "CCO"


def test_a_spelling_of_another_structure_is_a_serialization_mismatch_not_a_naming_defect(monkeypatch):
    monkeypatch.setattr(nv, "spellings", lambda canonical, count, seed: ["CCN", "OCC"])
    called: list[str] = []
    report = nv.order_report({"x": "CCO"}, 2, 0, namer=lambda s: called.append(s) or "ethanol")["x"]
    assert report["serialization_mismatches"] == ["CCN"]
    assert "CCN" not in called and report["distinct_names"] == 1


def test_every_read_back_is_classified_against_the_canonical_structure_not_the_spelling(monkeypatch):
    """The spelling `OCC` is not the string `CCO`, but both are ethanol. A reader that returns `CCO` is exact for both."""
    monkeypatch.setattr(nv, "spellings", lambda canonical, count, seed: ["OCC"])
    report = nv.order_report({"x": "CCO"}, 1, 0, namer=lambda s: f"n-{s}", reader=lambda names: ["CCO"] * len(names))["x"]
    assert report["distinct_names"] == 2
    assert {entry["cls"] for entry in report["names"]} == {"exact"}
    wrong = nv.order_report({"x": "CCO"}, 1, 0, namer=lambda s: f"n-{s}", reader=lambda names: ["CCN"] * len(names))["x"]
    assert {entry["cls"] for entry in wrong["names"]} == {"mismatch_formula"}


def test_the_order_lines_list_only_unstable_structures_with_an_example_spelling():
    report = nv.order_report({"x": canon("CCC(C)c1ccc(C(CC)CC)cc1")}, 10, 3, namer=lambda s: f"n-{s[:1]}")
    text = "\n".join(nv.order_lines(report))
    assert "1 with more than one name" in text and "e.g." in text
    stable = nv.order_report({"x": "CCO"}, 3, 3, namer=lambda s: "ethanol")
    assert "0 with more than one name" in "\n".join(nv.order_lines(stable)) and "e.g." not in "\n".join(nv.order_lines(stable))


# --- the real engine ------------------------------------------------------------------------------------------------------------------

def test_the_real_engine_runs_through_the_diagnostic_and_every_sample_is_the_same_structure():
    """P-14.5.4 (KNOWN_LIMITATIONS, "Open after the stereo cache fix") is documented as order-dependent for this structure. Whether
    it still is, is MEASURED by the report and is not asserted here: the test pins the report's shape and the identity check, so
    fixing the defect does not break it."""
    canonical = canon("CCCC(C)c1ccc(C(CC)CC)cc1")
    report = nv.order_report({"x": canonical}, 6, 7)["x"]
    assert report["serialization_mismatches"] == []
    assert report["valid_samples"] == 7 and report["distinct_names"] >= 1
    assert all(entry["name"] and not entry["name"].startswith("RAISED") for entry in report["names"])


def test_the_json_record_is_stable_and_complete(monkeypatch, tmp_path, no_frozen):
    out = tmp_path / "v.json"
    monkeypatch.setattr(nv.census_scan, "scan", lambda rows, *, names_only=False: {
        r["label"]: {"smiles": r["smiles"], "name": "x", "back": None, "cls": "exact"} for r in rows})
    assert nv.main(["C1CCNCC1", "--ops", "protonate_sp3_nh", "--names-only", "--json", str(out)]) == 0
    first = out.read_text(encoding="utf-8")
    assert nv.main(["C1CCNCC1", "--ops", "protonate_sp3_nh", "--names-only", "--json", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == first
    payload = json.loads(first)
    assert payload["ops"] == "protonate_sp3_nh" and payload["seeds"] == {"s0": "C1CCNCC1"}
    row = payload["population"][0]
    assert row["smiles"] == canon("C1CC[NH2+]CC1") and row["origins"][0]["path"][0]["op"] == "protonate_sp3_nh"
    assert payload["orderings"] == {"count": 0, "seed": 0, "structures": {}}


def test_no_java_is_refused_unless_names_only(monkeypatch, capsys):
    monkeypatch.setattr(nv.shutil, "which", lambda _name: None)
    assert nv.main(["CC"]) == 2 and "java" in capsys.readouterr().err
