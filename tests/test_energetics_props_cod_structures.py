"""The COD structure pass for Phase B (`inventory_scripts/cod_structure_pass.py`, `cod_census_structures.py`).

Held: the family groups are found from CONNECTIVITY alone (the same answer whatever bond orders Open Babel guessed, which
were measured unusable), the first family wins in section 5's order, the component class is read from the CIF's moiety
formula, and the counts join and aggregate as stated. The archive is not here; the logic is.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from rdkit import Chem

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


sp = _load("cod_structure_pass", DIR / "inventory_scripts" / "cod_structure_pass.py")
agg = _load("cod_census_structures", DIR / "inventory_scripts" / "cod_census_structures.py")
index = _load("cod_index", DIR / "inventory_scripts" / "cod_index.py")


def family(smiles: str) -> str:
    return sp.families_from_graph(Chem.MolFromSmiles(smiles, sanitize=False))["family"]


def family_of(graph) -> str:
    return sp.families_from_graph(graph)["family"]


@pytest.mark.parametrize(
    ("smiles", "expected"),
    [
        ("Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]", "c_nitro"),              # TNT, charge-separated nitro
        ("Cc1c(N(=O)=O)cc(N(=O)=O)cc1N(=O)=O", "c_nitro"),                              # the same, the way Open Babel writes it
        ("C1N(N(=O)=O)CN(N(=O)=O)CN1N(=O)=O", "nitramine"),                             # RDX
        ("C1N([N+](=O)[O-])CN([N+](=O)[O-])CN1[N+](=O)[O-]", "nitramine"),
        ("C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]", "nitrate_ester"),   # PETN
        ("CC(N=[N+]=[N-])C", "azide"),
        ("c1nnn[nH]1", "n_rich_heterocycle"),                                           # tetrazole
        ("c1cnc[nH]1", "n_rich_heterocycle"),                                           # imidazole
        ("c1ccncc1", "other_organic"),                                                  # one ring nitrogen is not enough
        ("Clc1ccccc1", "halogenated"),
        ("CCO", "other_organic"),
        ("CN(c1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-])[N+](=O)[O-]", "nitramine"),     # tetryl: N-nitro AND C-nitro
        ("O=[N+]([O-])OCCCl", "nitrate_ester"),                                         # nitrate ester before halogenated
        ("O=[N+]([O-])c1ccc(Cl)cc1", "c_nitro"),                                        # C-nitro before halogenated
    ],
)
def test_the_family_is_read_from_connectivity_in_sections_5_order(smiles, expected):
    assert family(smiles) == expected


def test_the_same_connectivity_gives_the_same_groups_whatever_the_bond_orders():
    a = sp.families_from_graph(Chem.MolFromSmiles("O=N(=O)c1ccccc1", sanitize=False))
    b = sp.families_from_graph(Chem.MolFromSmiles("[O-][N+](=O)c1ccccc1", sanitize=False))
    c = sp.families_from_graph(Chem.MolFromSmiles("[O]N([O])c1ccccc1", sanitize=False))   # radicals: same graph
    assert a == b == c


def test_a_graph_with_no_hydrogens_is_not_given_any():
    """The bug the first full pass had: RDKit filled in an implicit H on a singly-bonded nitro oxygen, so [OX1] never matched."""
    rw = Chem.RWMol()
    c, n, o1, o2 = (rw.AddAtom(Chem.Atom(z)) for z in (6, 7, 8, 8))
    for a, b in ((c, n), (n, o1), (n, o2)):
        rw.AddBond(a, b, Chem.BondType.SINGLE)
    assert sp.families_from_graph(rw.GetMol())["family"] == "c_nitro"


def test_an_open_babel_molecule_becomes_one_graph_per_fragment():
    from openbabel import pybel

    graphs = sp.graph_from_obmol(pybel.readstring("smi", "[NH4+].[O-][N+](=O)[O-]").OBMol)
    assert len(graphs) == 2
    assert sorted(family_of(g) for g in graphs) == ["other_organic", "other_organic"]       # no carbon, so no C-nitro
    tnt = sp.graph_from_obmol(pybel.readstring("smi", "Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]").OBMol)
    assert len(tnt) == 1 and family_of(tnt[0]) == "c_nitro"


@pytest.mark.parametrize(
    ("moiety", "kind", "n"),
    [
        ("C6 H3 N3 O7", "single", 1),
        ("'C6 H12 O6, H2 O'", "multi", 2),
        ("C9 H13 N5 O3, 2(H2 O)", "multi", 2),
        ("C4 H12 N2 2+, 2(Cl -)", "ionic", 2),
        ("'C12 H17 N2 O+, Cl-'", "ionic", 2),
        ("?", "unknown", None),
        (None, "unknown", None),
        ("", "unknown", None),
    ],
)
def test_components_come_from_the_moiety_formula_and_no_moiety_is_never_single(moiety, kind, n):
    assert sp.components(moiety) == (kind, n)


def test_the_candidate_set_applies_the_preregistered_cuts(tmp_path):
    path = tmp_path / "i.sqlite"
    db = sqlite3.connect(path)
    db.executescript(index.SCHEMA)
    rows = [
        ("ok", "C6 H3 N3 O7", 293.0, 1.7, None),
        ("no_nitrogen", "C6 H6 O", 293.0, 1.2, None),
        ("metal", "C4 H4 N4 O4 Cu", 293.0, 1.9, None),
        ("cold", "C6 H3 N3 O7", 100.0, 1.7, None),
        ("pressure", "C6 H3 N3 O7", 293.0, 1.7, "1000000"),
        ("no_density", "C6 H3 N3 O7", 293.0, None, None),
        ("edge_low", "C2 H4 N4 O2", 273.0, 1.6, None),
        ("edge_high", "C2 H4 N4 O2", 303.0, 1.6, None),
        ("just_out", "C2 H4 N4 O2", 303.5, 1.6, None),
        ("just_below", "C2 H4 N4 O2", 272.5, 1.6, None),
    ]
    for code, f, t, d, p in rows:
        db.execute("INSERT INTO cod (code, formula, temperature_k, density_diffrn, pressure_raw) VALUES (?,?,?,?,?)", (code, f, t, d, p))
    db.commit()
    db.close()
    assert sp.candidates(path) == {"ok", "edge_low", "edge_high"}


def _joined(tmp_path):
    ipath, spath = tmp_path / "i.sqlite", tmp_path / "s.sqlite"
    db = sqlite3.connect(ipath)
    db.executescript(index.SCHEMA)
    sdb = sqlite3.connect(spath)
    sdb.executescript(sp.SCHEMA)
    spec = [
        # code, formula, r_gt, components, family
        ("a", "C7 H5 N3 O6", 0.04, "single", "c_nitro"),
        ("b", "C7 H5 N3 O6", 0.04, "single", "c_nitro"),                # repeat determination: an entry, not a new formula
        ("c", "C3 H6 N6 O6", 0.09, "single_by_geometry", "nitramine"),
        ("d", "C3 H6 N6 O6", 0.04, "multi", "nitramine"),               # a solvate: counted under all candidates only
        ("e", "C6 H6 N2", 0.04, "single", "other_organic"),
        ("f", "C2 H2 N4", 0.04, "unknown", "n_rich_heterocycle"),       # unknown is never single
    ]
    for code, formula, r, comp, fam in spec:
        db.execute("INSERT INTO cod (code, formula, r_gt) VALUES (?,?,?)", (code, formula, r))
        sdb.execute("INSERT INTO structure (code, components, family, groups) VALUES (?,?,?,?)", (code, comp, fam, fam))
    db.commit()
    sdb.commit()
    db.close()
    sdb.close()
    return ipath, spath


def test_the_aggregation_counts_entries_with_a_formula_floor_and_never_counts_unknown_as_single(tmp_path):
    out = agg.census(*_joined(tmp_path))
    allc, single = out["families"]["all_candidates"], out["families"]["single_component"]
    assert allc["c_nitro"]["entries"] == 2 and allc["c_nitro"]["distinct_formulas"] == 1
    assert allc["nitramine"]["entries"] == 2 and single["nitramine"]["entries"] == 1
    label = agg.EXPLOSOPHORE_LABEL
    assert allc[label]["entries"] == 4                                 # a, b, c, d: an N-rich ring (f) is not an explosophore group
    assert single[label]["entries"] == 3                               # a, b, c: d is a solvate
    assert allc["n_rich_heterocycle"]["entries"] == 1 and "n_rich_heterocycle" not in single   # f is unknown, never single
    assert single["other_organic"]["entries"] == 1
    assert allc["nitramine"]["entries_with_R_at_most_0.07"] == 1       # c's 0.09 fit is dropped by the information cut only
    assert out["by_components"]["unknown"] == 1


def test_the_committed_counts_are_consistent_and_say_what_they_are_not():
    c = json.loads((DIR / "cod_census_structures.json").read_text(encoding="utf-8"))
    fam = c["families"]
    for scope in fam.values():
        for name, cell in scope.items():
            assert cell["distinct_formulas"] <= cell["entries"], name
            assert cell["entries_with_R_at_most_0.07"] <= cell["entries"], name
    for name, cell in fam["single_component"].items():
        assert cell["entries"] <= fam["all_candidates"][name]["entries"], name
    assert sum(c["by_components"].values()) == c["candidates_classified"]
    assert c["errors"] <= c["candidates_classified"]
    text = " ".join(c["caveats"])
    assert "not an energetic material" in text and "COD overlaps the CSD" in text and "Open Babel" in text


# ------------------------------------------------------------------------------------- the entity key (PREREGISTRATION 15.3)
def _key(smiles: str) -> str:
    return sp.entity_key(Chem.MolFromSmiles(smiles, sanitize=False))


def test_the_entity_key_is_the_same_for_every_way_of_writing_one_molecules_bonds():
    pentavalent = _key("Cc1c(N(=O)=O)cc(N(=O)=O)cc1N(=O)=O")
    separated = _key("Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]")
    kekule = _key("CC1=C(N(=O)=O)C=C(N(=O)=O)C=C1N(=O)=O")
    assert pentavalent == separated == kekule


def test_the_entity_key_tells_different_molecules_apart():
    assert _key("Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]") != _key("C1N(N(=O)=O)CN(N(=O)=O)CN1N(=O)=O")   # TNT, RDX
    assert _key("c1ccc2ccccc2c1") != _key("c1ccc2cccc2c1")                                                          # ring size matters
    assert _key("CCO") != _key("COC")                                                                               # connectivity matters


def test_stereoisomers_and_tautomers_share_a_key_and_an_open_babel_graph_carries_no_stereo():
    from openbabel import pybel

    r = sp.graph_from_obmol(pybel.readstring("smi", "C[C@H](N)C(=O)O").OBMol)[0]
    s = sp.graph_from_obmol(pybel.readstring("smi", "C[C@@H](N)C(=O)O").OBMol)[0]
    assert sp.entity_key(r) == sp.entity_key(s)                                                     # a COD graph has no chirality tags
    assert _key("CC(=O)C") == _key("CC(O)=C")                                                       # keto and enol: one heavy-atom graph


def test_the_key_does_not_depend_on_how_the_atoms_are_numbered():
    a = _key("Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]")
    b = _key("[O-][N+](=O)c1cc([N+](=O)[O-])c(C)c([N+](=O)[O-])c1")
    assert a == b
