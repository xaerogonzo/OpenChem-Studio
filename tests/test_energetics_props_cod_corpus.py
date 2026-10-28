"""The COD crystal-density corpus builder (`benchmarks/energetics_props/epb_cod_corpus.py`, `PREREGISTRATION.md` section 15).

The archive is not here. What is held: one CIF read to the right record (a whole molecule, its groups, family and entity key, bond orders perceived
from coordinates, and every refusal), each of the seven dispositions, the label rules, the partition rule with the previously examined compounds forced
into development, and the aggregates. The CIFs are SYNTHETIC: a molecule of known structure placed in a large P1 cell, so every expected answer is known.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors

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


corpus = _load("epb_cod_corpus", DIR / "epb_cod_corpus.py")
sp = _load("cod_structure_pass", DIR / "inventory_scripts" / "cod_structure_pass.py")
vr = _load("validation_rows", ROOT / "tools" / "validation_rows.py")

TNT = "Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]"
RDX = "C1N([N+](=O)[O-])CN([N+](=O)[O-])CN1[N+](=O)[O-]"
PETN = "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]"
ETHYL_ACETATE = "CCOC(C)=O"
WATER = "O"


def _hill(mol) -> str:
    plain = rdMolDescriptors.CalcMolFormula(mol)
    return " ".join(f"{el}{n}" for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", plain))


def make_cif(smiles, *, code="9999999", moiety="same", extra=(), temperature=293, density=1.65, r="0.04", space_group="P 1", z=1,
             hydrogens=True, volume="64000.0", pressure=None):
    """A synthetic CIF: the molecule (and any `extra` molecules, ten angstroms apart) in a 40 A cube, P1."""
    mols = [Chem.AddHs(Chem.MolFromSmiles(s)) for s in (smiles, *extra)]
    atoms = []
    for i, m in enumerate(mols):
        AllChem.EmbedMolecule(m, randomSeed=7)
        conf = m.GetConformer()
        for a in m.GetAtoms():
            if a.GetAtomicNum() == 1 and not hydrogens:
                continue
            p = conf.GetAtomPosition(a.GetIdx())
            atoms.append((a.GetSymbol(), (p.x + 10 + 12 * i) / 40.0, (p.y + 20) / 40.0, (p.z + 20) / 40.0))
    total = Chem.CombineMols(mols[0], mols[1]) if len(mols) == 2 else mols[0]
    formula = _hill(total)
    lines = [f"data_{code}", "_cell_length_a 40.0", "_cell_length_b 40.0", "_cell_length_c 40.0", "_cell_angle_alpha 90", "_cell_angle_beta 90",
             "_cell_angle_gamma 90", f"_cell_volume {volume}", f"_symmetry_space_group_name_H-M '{space_group}'", f"_cell_formula_units_Z {z}",
             f"_chemical_formula_sum '{formula}'"]
    if moiety == "same":
        lines.append(f"_chemical_formula_moiety '{_hill(mols[0])}'" if not extra else f"_chemical_formula_moiety '{_hill(mols[0])}, {_hill(mols[1])}'")
    elif moiety:
        lines.append(f"_chemical_formula_moiety '{moiety}'")
    if temperature is not None:
        lines.append(f"_diffrn_ambient_temperature {temperature}")
    if pressure:
        lines.append(f"_diffrn_ambient_pressure {pressure}")
    lines += [f"_exptl_crystal_density_diffrn {density}"]
    if r is not None:
        lines.append(f"_refine_ls_R_factor_gt {r}")
    lines += ["loop_", "_symmetry_equiv_pos_as_xyz", "'x, y, z'", "loop_", "_atom_site_label", "_atom_site_type_symbol", "_atom_site_fract_x",
              "_atom_site_fract_y", "_atom_site_fract_z"]
    for n, (sym, x, y, zz) in enumerate(atoms):
        lines.append(f"{sym}{n + 1} {sym} {x:.5f} {y:.5f} {zz:.5f}")
    return "\n".join(lines) + "\n"


def _key_of(smiles):
    return sp.entity_key(Chem.MolFromSmiles(smiles, sanitize=False))


def _block(smiles):
    return Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)).split("-")[0]


# ------------------------------------------------------------------------------------------------ one CIF -> one record
@pytest.mark.parametrize(
    ("smiles", "family", "section5"),
    [(TNT, "c_nitro", "nitroaromatic"), (RDX, "nitramine", "nitramine"), (PETN, "nitrate_ester", "nitrate_ester")],
)
def test_a_whole_explosophore_molecule_is_read_classified_keyed_and_perceived(smiles, family, section5):
    rec = corpus.process_entry("9999999", make_cif(smiles))
    assert rec["whole_molecule"] and rec["components"] == "single"
    assert rec["family"] == family and rec["key"] == _key_of(smiles)
    assert rec["perception"] == "perceived"
    assert _block(rec["smiles"]) == _block(smiles)                          # the SAME molecule, with its bond orders recovered
    assert rec["section5_family"] == section5
    assert corpus.disposition(rec) == "accepted"
    assert (rec["cell_volume"], rec["space_group"], rec["z"], rec["density"], rec["temperature_k"]) == (64000.0, "P 1", 1.0, 1.65, 293.0)


def test_a_solvate_is_not_a_single_component_and_gets_no_key():
    rec = corpus.process_entry("9999998", make_cif(TNT, extra=(WATER,)))
    assert rec["components"] == "multi" and rec["key"] is None
    assert corpus.disposition(rec) == "not_single_component"


def test_with_no_moiety_formula_a_whole_molecule_with_exactly_the_header_formula_is_single_by_geometry_and_otherwise_unknown():
    alone = corpus.process_entry("9999997", make_cif(TNT, moiety=None))
    assert alone["components"] == "single_by_geometry" and alone["whole_molecule"] and corpus.disposition(alone) == "accepted"
    solvate = corpus.process_entry("9999996", make_cif(TNT, moiety=None, extra=(WATER,)))
    assert solvate["components"] == "unknown" and corpus.disposition(solvate) == "not_single_component"
    # without a moiety line the exact formula is the only evidence of "whole", so unplaced hydrogens leave it unproven
    bare = corpus.process_entry("9999993", make_cif(TNT, moiety=None, hydrogens=False))
    assert not bare["whole_molecule"] and corpus.disposition(bare) == "not_single_component"


def test_hydrogens_that_were_never_placed_do_not_change_the_key_and_refuse_perception():
    full = corpus.process_entry("9999995", make_cif(TNT))
    bare = corpus.process_entry("9999994", make_cif(TNT, hydrogens=False))
    assert bare["whole_molecule"] and bare["key"] == full["key"]            # the heavy-atom graph is the same
    assert bare["perception"] == "hydrogens_missing" and bare["smiles"] is None
    assert corpus.disposition(bare) == "accepted"                           # the label does not need bond orders


def test_a_compound_without_one_of_the_four_groups_is_outside_the_primary_population():
    rec = corpus.process_entry("9999993", make_cif(ETHYL_ACETATE))
    assert rec["family"] == "other_organic" and corpus.disposition(rec) == "no_explosophore_group"
    imidazole = corpus.process_entry("9999992", make_cif("c1cnc[nH]1"))
    assert imidazole["family"] == "n_rich_heterocycle" and corpus.disposition(imidazole) == "no_explosophore_group"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, "accepted"),
        ({"temperature": 100}, "temperature_outside_window"),
        ({"temperature": 272.9}, "temperature_outside_window"),
        ({"temperature": 273}, "accepted"),
        ({"temperature": 303}, "accepted"),
        ({"temperature": 303.1}, "temperature_outside_window"),
        ({"r": None}, "r_factor_missing"),
        ({"r": "0.071"}, "r_factor_above_cut"),
        ({"r": "0.07"}, "accepted"),
    ],
)
def test_each_disposition_follows_from_the_entry_in_the_stated_order(kwargs, expected):
    assert corpus.disposition(corpus.process_entry("9999991", make_cif(TNT, **kwargs))) == expected


def test_an_unreadable_entry_is_its_own_disposition():
    assert corpus.disposition({"code": "1", "error": "read: boom"}) == "unreadable_entry"


def test_every_disposition_the_rules_can_give_is_in_the_documented_list():
    assert len(set(corpus.DISPOSITIONS)) == len(corpus.DISPOSITIONS) == 8
    for name in ("unreadable_entry", "accepted", "not_single_component", "no_whole_molecule", "no_explosophore_group",
                 "temperature_outside_window", "r_factor_missing", "r_factor_above_cut"):
        assert name in corpus.DISPOSITIONS


def test_a_cell_block_is_read_and_an_uncertainty_is_dropped():
    cell = corpus.cell_fields("_cell_volume 1234.5(3)\n_cell_length_a 10.1(2)\n_cell_angle_beta 95.5\n_cell_length_b ?\n")
    assert cell["cell_volume"] == 1234.5 and cell["a"] == 10.1 and cell["beta"] == 95.5 and cell["b"] is None and cell["c"] is None


# ------------------------------------------------------------------------------------------------ labels, forms, partitions
def _det(density, sg="P 21/c", z=4, code="x"):
    return {"density": density, "space_group": sg, "z": z, "code": code}


def test_the_label_is_the_median_of_one_form_and_a_wide_spread_is_unresolved():
    ok = corpus.resolve_entity([_det(1.80), _det(1.81), _det(1.83)])
    assert ok["status"] == "resolved" and ok["value"] == 1.81 and ok["agreeing"] and ok["n_determinations"] == 3
    edge = corpus.resolve_entity([_det(1.80), _det(1.83)])
    assert edge["status"] == "resolved" and edge["value"] == pytest.approx(1.815)            # a spread of exactly 0.03 is allowed
    assert corpus.resolve_entity([_det(1.80), _det(1.8301)])["status"] == "unresolved_spread"
    single = corpus.resolve_entity([_det(1.77)])
    assert single["status"] == "resolved" and not single["agreeing"]                          # one determination: resolved, not agreeing


def test_different_space_groups_or_z_are_different_forms_and_are_never_combined():
    assert corpus.resolve_entity([_det(1.80, "P 21/c", 4), _det(1.80, "P -1", 2)])["status"] == "unresolved_forms"
    assert corpus.resolve_entity([_det(1.80, "P 21/c", 4), _det(1.80, "P 21/c", 8)])["status"] == "unresolved_forms"


def test_the_previously_examined_compounds_are_found_and_forced_into_development():
    forced = corpus.previously_examined_keys()
    assert len(forced) >= 40
    for smiles in (TNT, RDX, PETN, "C1N([N+](=O)[O-])CN([N+](=O)[O-])CN([N+](=O)[O-])CN1[N+](=O)[O-]"):      # TNT, RDX, PETN, HMX
        assert _key_of(smiles) in forced, smiles
    assert corpus.assign_partition(_key_of(TNT), forced) == ("development", "previously_examined")
    other = "somekey"
    assert corpus.assign_partition(other, forced) == (vr.partition_for(other), "hash")


def test_a_forced_compound_stays_in_development_whatever_its_hash():
    forced = {k: "x" for k in ("a" * 5 + str(i) for i in range(200))}
    assert all(corpus.assign_partition(k, forced)[0] == "development" for k in forced)
    assert {vr.partition_for(k) for k in forced} == {"development", "selection", "holdout"}      # so the rule changed some of them


# ------------------------------------------------------------------------------------------------ the build, on synthetic records
def _rec(code, key, density, *, family="c_nitro", t=293.0, r=0.04, sg="P 1", z=1, volume=1000.0, components="single", whole=True, smiles=None):
    return {"code": code, "key": key, "density": density, "family": family, "temperature_k": t, "r_gt": r, "r_all": None, "space_group": sg,
            "z": float(z), "cell_volume": volume, "components": components, "whole_molecule": whole, "formula": "C H N O", "perception": "perceived" if smiles else "not_attempted",
            "smiles": smiles, "section5_family": "nitroaromatic" if smiles else None}


def test_the_build_counts_every_entry_once_and_writes_a_manifest_of_resolved_entities_only():
    tnt_key = _key_of(TNT)
    records = [
        _rec("1", "k_resolved", 1.70, smiles="CC"), _rec("2", "k_resolved", 1.71),                      # two agreeing determinations
        _rec("3", "k_spread", 1.60), _rec("4", "k_spread", 1.70),                                        # unresolved: spread
        _rec("5", "k_forms", 1.60, sg="P 1"), _rec("6", "k_forms", 1.60, sg="P -1"),                    # unresolved: forms
        _rec("7", tnt_key, 1.65),                                                                         # previously examined
        _rec("8", "k_cold", 1.80, t=100.0), _rec("9", "k_bad_r", 1.80, r=0.09), _rec("10", "k_salt", 1.8, components="multi"),
        _rec("11", None, 1.8, whole=False), _rec("12", "k_plain", 1.2, family="other_organic"),
        {"code": "13", "error": "read: boom"},
    ]
    built = corpus.build(records, corpus.previously_examined_keys())
    s = built["summary"]
    assert sum(s["dispositions"].values()) == len(records) == s["records"]                        # exactly one disposition each
    assert s["dispositions"] == {"unreadable_entry": 1, "accepted": 7, "not_single_component": 1, "no_whole_molecule": 1,
                                 "no_explosophore_group": 1, "temperature_outside_window": 1, "r_factor_missing": 0, "r_factor_above_cut": 1}
    assert s["entities_by_label_status"] == {"resolved": 2, "unresolved_spread": 1, "unresolved_forms": 1}
    assert set(built["manifest"]) == {"k_resolved", tnt_key}                                      # resolved entities only
    assert built["manifest"][tnt_key] == "development" and s["forced_entities"] == 1
    assert s["resolved_entities_with_agreeing_determinations"] == 1
    assert s["manifest_entities"] == len(built["manifest"])
    assert s["manifest_checksum"] == vr.manifest_checksum(built["manifest"])
    assert built["entities"]["k_resolved"]["section5_family"] == "nitroaromatic" and built["entities"]["k_resolved"]["structure_perceived"]


def test_the_manifest_partition_of_a_key_does_not_depend_on_the_other_entries():
    a = corpus.build([_rec("1", "k_one", 1.7)], {})["manifest"]
    b = corpus.build([_rec("1", "k_one", 1.7), _rec("2", "k_two", 1.8), _rec("3", "k_three", 1.9)], {})["manifest"]
    assert a["k_one"] == b["k_one"] == vr.partition_for("k_one")


def test_pairs_are_one_entity_one_form_one_low_and_one_room_temperature_determination_with_a_plausible_volume():
    records = [
        _rec("lo", "k", 1.80, t=100.0, volume=1000.0), _rec("rt", "k", 1.75, t=293.0, volume=1030.0),            # ratio 1.03: kept
        _rec("lo2", "kb", 1.80, t=100.0, volume=1000.0), _rec("rt2", "kb", 1.60, t=293.0, volume=1200.0),        # ratio 1.20: a different form
        _rec("lo3", "kc", 1.80, t=100.0, volume=None), _rec("rt3", "kc", 1.75, t=293.0, volume=1030.0),          # no cell volume
        _rec("lo4", "kd", 1.80, t=100.0, volume=1000.0),                                                          # no room-temperature partner
        _rec("lo5", "ke", 1.80, t=100.0, volume=1000.0, sg="P 1"), _rec("rt5", "ke", 1.75, t=293.0, volume=1030.0, sg="P -1"),   # forms differ
        _rec("lo6", "kf", 1.80, t=100.0, volume=1000.0, r=0.09), _rec("rt6", "kf", 1.75, t=293.0, volume=1030.0),   # poor fit
        _rec("lo7", "kg", 1.80, t=100.0, volume=1000.0, family="other_organic"), _rec("rt7", "kg", 1.75, t=293.0, volume=1030.0, family="other_organic"),
        _rec("lo8", "kh", 1.80, t=100.0, volume=1000.0), _rec("rt8", "kh", 1.75, t=293.0, volume=1030.0, family="other_organic"),   # one side only: not flagged
    ]
    pairs = corpus.pairs_for_study(records)
    # a pair is not limited to the four explosophore groups: thermal expansion of the lattice does not depend on the group (owner, 2026-10-27)
    assert [(p["low_code"], p["rt_code"], p["explosophore"]) for p in pairs["rows"]] == [("lo", "rt", True), ("lo7", "rt7", False), ("lo8", "rt8", False)]
    assert pairs["rows"][0]["volume_ratio"] == pytest.approx(1.03)
    assert (pairs["matched_before_volume_cut"], pairs["dropped_no_cell_volume"], pairs["dropped_volume_ratio_outside"], pairs["pairs"]) == (5, 1, 1, 3)
    assert pairs["explosophore_pairs"] == 1


def test_the_report_is_generated_from_the_summary_and_says_what_it_is_not():
    built = corpus.build([_rec("1", "k", 1.7), _rec("2", "k2", 1.8, t=100.0)], {})
    text = corpus.render_report(built["summary"])
    assert built["summary"]["manifest_checksum"] in text and "No method has been scored" in text and "CC0" in text
    for name in corpus.DISPOSITIONS:
        assert name in text


# ---- the committed outputs of the full build (corpus kept outside the repository) ------------------------------------------------------------

def _committed():
    import json
    return {n: json.loads((DIR / f).read_text(encoding="utf-8")) for n, f in
            (("manifest", "cod_split_manifest.json"), ("summary", "cod_corpus_summary.json"), ("pairs", "cod_correction_pairs.json"))}


def test_the_committed_summary_adds_up():
    c = _committed()
    s, manifest = c["summary"], c["manifest"]
    assert sum(s["dispositions"].values()) == s["records"] == sum(s["components"].values())
    assert sum(s["entities_by_label_status"].values()) == s["entities_with_an_accepted_determination"]
    assert s["entities_by_label_status"]["resolved"] == s["manifest_entities"] == len(manifest)
    assert sum(s["resolved_entities_by_partition"].values()) == len(manifest)
    assert sum(s["resolved_entities_by_connectivity_family"].values()) == len(manifest)
    assert sum(s["resolved_entities_by_section5_family"].values()) == len(manifest)
    assert s["dispositions"]["accepted"] == sum(s["perception_of_accepted_determinations"].values())
    assert s["extract_errors"] == s["dispositions"]["unreadable_entry"]


def test_the_committed_manifest_matches_its_checksum_and_follows_the_partition_rule_except_for_the_forced_compounds():
    c = _committed()
    manifest, s = c["manifest"], c["summary"]
    assert vr.manifest_checksum(manifest) == s["manifest_checksum"]
    assert set(manifest.values()) <= {"development", "selection", "holdout"}
    moved = [k for k, part in manifest.items() if part != vr.partition_for(k)]
    assert all(manifest[k] == "development" for k in moved)
    assert len(moved) <= s["forced_entities"]


def test_the_sealed_set_is_large_enough_for_the_gate_before_any_label_is_checked():
    # 15.5: at least 60 paired verified holdout entities; the holdout partition is an upper bound on them
    assert _committed()["summary"]["resolved_entities_by_partition"]["holdout"] >= 60


def test_the_committed_report_is_what_the_builder_renders_from_the_committed_summary():
    text = (DIR / "COD_CORPUS_REPORT.md").read_text(encoding="utf-8")
    assert text == corpus.render_report(_committed()["summary"])


def test_the_committed_pairs_obey_the_study_rules():
    c = _committed()
    pairs, s = c["pairs"], c["summary"]["pairs"]
    assert len(pairs) == s["pairs"] and len({(p["key"], p["space_group"], p["z"]) for p in pairs}) == len(pairs)
    for p in pairs:
        assert corpus.LOW_T_K[0] <= p["t_low"] <= corpus.LOW_T_K[1] and corpus.WINDOW_K[0] <= p["t_rt"] <= corpus.WINDOW_K[1]
        assert corpus.PAIR_VOLUME_RATIO[0] <= p["volume_ratio"] <= corpus.PAIR_VOLUME_RATIO[1]
        assert p["low_code"] != p["rt_code"]
