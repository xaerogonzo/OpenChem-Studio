"""The crystal-density candidates D1 (Tarver 1979), D4 (Keshavarz 2009) and Candidate D (`benchmarks/energetics_props/epb_density_candidates.py`,
`PREREGISTRATION.md` 10.1, 15.7 and section 17).

No label of the COD corpus is compared with a prediction here. The three papers' tables are NOT in the repository (a bulk transcription, kept in
the maintainer's private notes); what is tested is the committed method parameters, the entity-key manifest (recomputed against the COD split
manifest), Candidate D's fixed specification on synthetic data, and, when `OPENCHEM_DENSITY_CANDIDATES_DIR` names the private folder, the
arithmetic checks on the full transcriptions (otherwise those are NOT_RUN, which is said in a test name rather than skipped silently).
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("rdkit")
from rdkit import Chem  # noqa: E402
from rdkit.Chem import Descriptors  # noqa: E402

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


dcand = _load("epb_density_candidates", DIR / "epb_density_candidates.py")
corpus = _load("epb_cod_corpus", DIR / "epb_cod_corpus.py")
MANIFEST = dcand.load_manifest()
COD = json.loads((DIR / "cod_split_manifest.json").read_text(encoding="utf-8"))

NO2 = "[N+](=O)[O-]"


def _key(smiles: str) -> list[str]:
    sp = corpus._sp()
    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    return [sp.entity_key(f) for f in Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False) if f.GetNumHeavyAtoms() >= 4]


def _counts(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    mh = Chem.AddHs(mol)
    return {s: sum(1 for a in mh.GetAtoms() if a.GetSymbol() == s) for s in "CHNO"}, Descriptors.MolWt(mh)


# ------------------------------------------------------------------------------------------------ the published parameters
def test_tarver_tables_have_the_papers_group_counts():
    assert len(dcand.TARVER_TABLE_II) == 26          # "the 26 group configurations" of the aliphatic compounds
    assert len(dcand.TARVER_TABLE_IV) == 47          # "the 47 group configurations" of the nitrogen and cyclic compounds
    assert len(dcand.TARVER_AROMATIC) == 5
    assert all(v > 0 for v in dcand.tarver_volume_table().values())


@pytest.mark.parametrize(
    "mol_wt, groups, printed",
    [
        (222.12, "3cb", 1.780),                                                   # RDX, Table V
        (227.13, "2[Ca-H] + 3[Ca-NO2] + [Ca-CH3]", 1.636),                        # TNT, Table I
        (316.14, "4p + x", 1.7649),                                               # PETN, Table III
        (227.09, "2w + z", 1.5902),                                               # nitroglycerin, Table III
        (296.16, "4[C-H2,(N-NO2)2]c=8", 1.850),                                   # HMX: the eight-membered ring group
    ],
)
def test_tarver_density_reproduces_printed_rows(mol_wt, groups, printed):
    assert dcand.tarver_density(mol_wt, dcand.parse_tarver_groups(groups)) == pytest.approx(printed, abs=0.0006)


def test_group_expression_parser_handles_nesting_and_brackets():
    assert dcand.parse_tarver_groups("2(a + c + h + i)") == {"a": 2, "c": 2, "h": 2, "i": 2}
    assert dcand.parse_tarver_groups("2(w + 2z)") == {"w": 2, "z": 4}
    assert dcand.parse_tarver_groups("3[Ca-NO2] + 2[Ca-H] + θ + [Ca-N(C,NO2)]") == {"[Ca-NO2]": 3, "[Ca-H]": 2, "θ": 1, "[Ca-N(C,NO2)]": 1}


def test_unknown_group_is_refused_not_guessed():
    with pytest.raises(KeyError):
        dcand.tarver_volume({"zz": 1})


def test_keshavarz_nitro_correlation_reproduces_printed_densities():
    # RDX: ED = EI = 0 (Table 1 prints 1.847); nitromethane: ED = 1.7 (1.132)
    c, mw = _counts(f"[O-][N+](=O)N1CN({NO2})CN(C1){NO2}")
    assert dcand.keshavarz_nitro_density(c["C"], c["H"], c["N"], mw, 0.0, 0.0) == pytest.approx(1.847, abs=0.001)
    c, mw = _counts(f"C{NO2}")
    assert dcand.keshavarz_nitro_density(c["C"], c["H"], c["N"], mw, 1.7, 0.0) == pytest.approx(1.132, abs=0.001)
    assert dcand.explains_nitro(c["C"], c["H"], c["N"], mw, 1.132)
    assert not dcand.explains_nitro(c["C"], c["H"], c["N"], mw, 1.00)


def test_keshavarz_arene_correlation_uses_the_cng_constant_that_reproduces_its_tables():
    # TNT, CPG = CNG = 0: 1.647 printed; trimethyltrinitrobenzene, CNG = 1: 1.467 printed (-0.751 would give 0.79)
    c, mw = _counts(f"Cc1c({NO2})cc({NO2})cc1{NO2}")
    assert dcand.keshavarz_arene_density(c["C"], c["H"], c["N"], c["O"], mw, 0.0, 0.0) == pytest.approx(1.647, abs=0.004)       # the printed coefficients carry 3-4 digits
    c, mw = _counts(f"Cc1c({NO2})c(C)c({NO2})c(C)c1{NO2}")
    assert dcand.keshavarz_arene_density(c["C"], c["H"], c["N"], c["O"], mw, 0.0, 1.0) == pytest.approx(1.467, abs=0.004)
    wrong = dcand.keshavarz_arene_density(c["C"], c["H"], c["N"], c["O"], mw, 0.0, 0.0) + dcand.KESHAVARZ_ARENE_CNG_AS_PRINTED
    assert abs(wrong - 1.467) > 0.5                                   # the printed coefficient cannot be the one used
    # TATB, CPG = 2: 1.906 printed
    c, mw = _counts(f"Nc1c({NO2})c(N)c({NO2})c(N)c1{NO2}")
    assert dcand.keshavarz_arene_density(c["C"], c["H"], c["N"], c["O"], mw, 2.0, 0.0) == pytest.approx(1.906, abs=0.004)


def test_the_committed_parameter_tables_are_pinned():
    """Every Tarver designation and every Keshavarz coefficient was checked against the printed rows (the private checks); this pins them
    so an edit is a decision. A change to the tables or coefficients must change this hash in the same commit, with the reason."""
    import hashlib

    blob = json.dumps({"aromatic": dcand.TARVER_AROMATIC, "II": dcand.TARVER_TABLE_II, "IV": dcand.TARVER_TABLE_IV,
                       "nitro": dcand.KESHAVARZ_NITRO, "arene": dcand.KESHAVARZ_ARENE}, sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(blob.encode("utf-8")).hexdigest() == "2736b181a12f1e14e2c508d09a657abec96669657c358dc848be8ea35670b34b"


def test_keshavarz_nitro_ei_coefficient_reproduces_a_printed_row():
    # 2-nitroethanol: an OH on a nitro compound gives EI = 0.4 (rule (4)); Table 1 prints 1.314
    c, mw = _counts(f"OCC{NO2}")
    assert dcand.keshavarz_nitro_density(c["C"], c["H"], c["N"], mw, 0.0, 0.4) == pytest.approx(1.314, abs=0.002)


# ------------------------------------------------------------------------------------------------ the private-transcription checks
def _rows(**over):
    base = dict(table="V", row=1, mw=222.12, measd=1.806, groups="3cb", calc_vol=124.80, calc_den=1.780, pct_err=1.44)
    base.update(over)
    return base


def test_verify_tarver_rows_accepts_a_consistent_row():
    assert dcand.verify_tarver_rows([_rows()]) == []


@pytest.mark.parametrize(
    "mutation",
    [dict(calc_vol=130.0), dict(calc_den=1.70), dict(pct_err=3.0), dict(groups="3zz")],
    ids=["volume", "density", "error", "unknown_group"],
)
def test_verify_tarver_rows_catches_each_kind_of_inconsistency(mutation):
    assert dcand.verify_tarver_rows([_rows(**mutation)])


def test_private_checks_reproduce_the_recorded_printed_inconsistencies():
    directory = dcand.private_dir()
    if directory is None or not (directory / "tarver1979_full.json").exists():
        pytest.skip("NOT_RUN: OPENCHEM_DENSITY_CANDIDATES_DIR is not set (the transcriptions are private)")
    result = dcand.run_private_checks(directory)
    assert result["tarver_problems"] == MANIFEST["checks"]["tarver_expected_problems"]
    assert result["keshavarz_nitro_unexplained"] == MANIFEST["checks"]["keshavarz_nitro_unexplained"]
    assert result["keshavarz_arene_unexplained"] == MANIFEST["checks"]["keshavarz_arene_unexplained"]
    for src in MANIFEST["sources"].values():
        import hashlib
        assert hashlib.sha256((directory / src["private_file"]).read_bytes()).hexdigest() == src["private_file_sha256"]


# ------------------------------------------------------------------------------------------------ the manifest
def test_manifest_carries_keys_and_counts_only():
    text = json.dumps(MANIFEST)
    for forbidden in ('"name"', '"smiles"', '"measd"', '"measured"', '"calc_den"', '"calc_new"'):
        assert forbidden not in text
    assert MANIFEST["builder"] == dcand.BUILDER_VERSION


def test_manifest_counts_are_consistent():
    cands = MANIFEST["candidates"]
    assert set(cands) == {"D1_tarver1979", "D4a_keshavarz2009_nitro", "D4b_keshavarz2009_arene"}
    for name, c in cands.items():
        assert c["rows"] == c["rows_resolved"] + c["rows_ambiguous_position"] + c["rows_unresolved"], name
        assert c["rows_unresolved"] == len(c["unresolved_rows"]), name
        assert c["fit_keys"] == sorted(set(c["fit_keys"])) and c["check_keys"] == sorted(set(c["check_keys"])), name
        assert not set(c["fit_keys"]) & set(c["check_keys"]), name
        assert c["n_keys_total"] == len(c["fit_keys"]) + len(c["check_keys"]), name
    assert cands["D1_tarver1979"]["rows"] == 188                       # the paper's own count
    assert (cands["D4a_keshavarz2009_nitro"]["rows"], cands["D4b_keshavarz2009_arene"]["rows"]) == (113, 59)
    assert sum(s["rows"] for k, s in MANIFEST["sources"].items() if k != "tarver1979") == 113 + 59
    assert sum(MANIFEST["sources"]["tarver1979"]["tables"].values()) == 188


def test_manifest_cod_overlap_is_recomputed_from_the_split_manifest():
    union: set[str] = set()
    for name, c in MANIFEST["candidates"].items():
        keys = set(c["fit_keys"]) | set(c["check_keys"])
        union |= keys
        found = {k: COD[k] for k in keys if k in COD}
        for part in ("development", "selection", "holdout"):
            assert c["cod_overlap_of_all_keys"][part] == sum(1 for v in found.values() if v == part), (name, part)
        assert c["cod_overlap_of_all_keys"]["in_cod_manifest"] == len(found)
    assert MANIFEST["seen_keys_union_count"] == len(union)
    assert MANIFEST["cod_overlap_of_union"]["in_cod_manifest"] == sum(1 for k in union if k in COD)


def test_manifest_forced_overlap_matches_the_previously_examined_set():
    forced = corpus.previously_examined_keys()
    union = set()
    for c in MANIFEST["candidates"].values():
        union |= set(c["fit_keys"]) | set(c["check_keys"])
    assert MANIFEST["cod_overlap_of_union"]["forced_previously_examined"] == sum(1 for k in union if k in forced)


def test_manifest_keys_are_the_keys_of_known_compounds():
    c = MANIFEST["candidates"]
    tnt = f"Cc1c({NO2})cc({NO2})cc1{NO2}"
    rdx = f"[O-][N+](=O)N1CN({NO2})CN(C1){NO2}"
    hmx = f"[O-][N+](=O)N1CN({NO2})CN({NO2})CN({NO2})C1"
    tatb = f"Nc1c({NO2})c(N)c({NO2})c(N)c1{NO2}"
    for smiles, where in ((tnt, "D1_tarver1979"), (tnt, "D4b_keshavarz2009_arene"), (rdx, "D1_tarver1979"), (rdx, "D4a_keshavarz2009_nitro"),
                          (hmx, "D1_tarver1979"), (tatb, "D4b_keshavarz2009_arene"), (tatb, "D1_tarver1979")):
        key = _key(smiles)[0]
        assert key in c[where]["fit_keys"] or key in c[where]["check_keys"], (smiles, where)
    # a compound none of the three papers prints
    assert _key("c1ccc2ccccc2c1")[0] not in {k for v in c.values() for k in v["fit_keys"] + v["check_keys"]}


def test_manifest_sources_match_the_registered_pdfs():
    lit = tomllib.loads((ROOT / "docs" / "research" / "literature.toml").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in lit["source"]}
    for key, src in MANIFEST["sources"].items():
        assert by_id[src["literature_id"]]["sha256"] == src["pdf_sha256"], key


def test_manifest_records_each_finding_once_and_names_the_unresolved_rows():
    ids = [f["id"] for f in MANIFEST["findings"]]
    assert len(ids) == len(set(ids))
    assert len(MANIFEST["checks"]["tarver_expected_problems"]) == 11
    assert MANIFEST["candidates"]["D4b_keshavarz2009_arene"]["rows_unresolved"] == 5
    assert "unresolved" in MANIFEST["leakage_status"]["D4b_keshavarz2009_arene"]


# ------------------------------------------------------------------------------------------------ Candidate D
def test_candidate_d_is_the_preregistered_size():
    assert len(dcand.CANDIDATE_D_GROUPS) <= 10                           # "at most ten functional-group counts" (10.1)
    assert tuple(dcand.CANDIDATE_D_GROUPS) == ("c_nitro", "n_nitro", "nitrate_ester", "azide", "n_oxide", "furazan", "amino_ortho_nitro",
                                                "hydroxyl", "polyazole", "aromatic_ring")
    assert dcand.candidate_d_parameter_count() == 18
    assert dcand.CANDIDATE_D_RIDGE_GRID == (0.01, 0.1, 1.0, 10.0, 100.0)
    assert dcand.CANDIDATE_D_MIN_ROWS_PER_PARAMETER * dcand.candidate_d_parameter_count() == 180


@pytest.mark.parametrize(
    "smiles, expected",
    [
        (f"C{NO2}", {"c_nitro": 1, "n_nitro": 0, "nitrate_ester": 0}),
        (f"CN(C){NO2}", {"c_nitro": 0, "n_nitro": 1}),
        ("C(CO[N+](=O)[O-])(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-]", {"nitrate_ester": 4, "c_nitro": 0}),
        ("CN=[N+]=[N-]", {"azide": 1}),
        (f"Nc1c({NO2})c(N)c({NO2})c(N)c1{NO2}", {"c_nitro": 3, "amino_ortho_nitro": 6, "aromatic_ring": 1}),
        (f"[O-][N+](=O)c1nonc1{NO2}", {"furazan": 1, "n_oxide": 0}),
        ("[O-][n+]1onc2c1c1no[n+]([O-])c1c1no[n+]([O-])c21", {"n_oxide": 3, "furazan": 3}),
        (f"Oc1c({NO2})cc({NO2})cc1{NO2}", {"hydroxyl": 1, "c_nitro": 3}),
        ("CC=NO", {"hydroxyl": 0}),          # an oxime OH is not a C-OH
        ("CC(=O)O", {"hydroxyl": 1}),
        ("c1nc[nH]n1", {"polyazole": 1}),
        ("c1nnn[nH]1", {"polyazole": 1}),
        ("c1c[nH]cn1", {"polyazole": 0}),
        ("C1CCCCC1", {"aromatic_ring": 0}),
    ],
)
def test_candidate_d_group_counts(smiles, expected):
    counts = dcand.candidate_d_counts(Chem.MolFromSmiles(smiles))
    for name, n in expected.items():
        assert counts[name] == n, (smiles, name, counts)


def test_candidate_d_refuses_an_element_outside_the_list():
    assert dcand.candidate_d_counts(Chem.MolFromSmiles("C[Si](C)(C)C")) is None
    assert dcand.candidate_d_counts(Chem.MolFromSmiles("CP(C)C")) is None


def _synthetic_rows(n=240, seed=3):
    import random

    rng = random.Random(seed)
    smiles = ["CC", f"C{NO2}", f"CN(C){NO2}", "CCO[N+](=O)[O-]", "CN=[N+]=[N-]", "c1ccccc1", f"Oc1ccc({NO2})cc1", "c1nc[nH]n1", f"[O-][N+](=O)c1nonc1{NO2}",
              f"Nc1ccc({NO2})cc1{NO2}", "OCC(O)CO", "CC(C)(C)C", "NCCN", f"Cc1c({NO2})cc({NO2})cc1{NO2}", "c1ccc(Cl)cc1", "CSC"]
    truth = {"C": 11.0, "H": 6.5, "N": 5.0, "O": 7.0, "F": 9.0, "Cl": 19.0, "Br": 25.0, "S": 17.0,
             "c_nitro": 3.0, "n_nitro": 2.0, "nitrate_ester": 4.0, "azide": 1.0, "n_oxide": 2.0, "furazan": -3.0, "amino_ortho_nitro": -2.0,
             "hydroxyl": -2.5, "polyazole": -1.5, "aromatic_ring": 1.0}
    rows = []
    for i in range(n):
        smi = smiles[i % len(smiles)]
        mol = Chem.MolFromSmiles(smi)
        counts = dcand.candidate_d_counts(mol)
        volume = sum(truth[k] * v for k, v in counts.items()) * (1.0 + rng.gauss(0, 0.0))
        mw = Descriptors.MolWt(Chem.AddHs(mol))
        rows.append((counts, mw, mw / volume))
    return rows, truth


def test_candidate_d_fit_recovers_a_known_volume_model_without_ridge_bias():
    rows, truth = _synthetic_rows()
    coef = dcand.fit_candidate_d(rows, ridge=1e-9)
    counts, mw, rho = rows[0]
    assert dcand.predict_candidate_d(coef, counts, mw) == pytest.approx(rho, rel=1e-6)
    # every row is predicted back; the fit of the volumes is exact for this noiseless set
    assert max(abs(dcand.predict_candidate_d(coef, c, m) - r) / r for c, m, r in rows) < 1e-5


def test_candidate_d_ridge_shrinks_group_coefficients_only():
    rows, _ = _synthetic_rows()
    free = dcand.fit_candidate_d(rows, ridge=1e-9)
    shrunk = dcand.fit_candidate_d(rows, ridge=1e6)
    assert all(abs(shrunk[g]) < abs(free[g]) + 1e-9 for g in dcand.CANDIDATE_D_GROUPS if g in free and free[g])
    assert abs(shrunk["C"]) > 0.5 * abs(free["C"])                     # the element volumes are not shrunk toward zero


def test_candidate_d_refuses_a_group_absent_from_development():
    rows, _ = _synthetic_rows()
    rows = [(c, m, r) for c, m, r in rows if not c["azide"]]              # no development row carries an azide
    coef = dcand.fit_candidate_d(rows, ridge=0.1)
    assert "azide" not in coef
    azide = Chem.MolFromSmiles("CN=[N+]=[N-]")
    assert dcand.predict_candidate_d(coef, dcand.candidate_d_counts(azide), Descriptors.MolWt(Chem.AddHs(azide))) is None
    silicon = Chem.MolFromSmiles("C[Si](C)(C)C")
    assert dcand.predict_candidate_d(coef, dcand.candidate_d_counts(silicon), 88.0) is None


def test_candidate_d_refuses_a_non_positive_volume():
    assert dcand.predict_candidate_d({"C": -1.0, "H": 0.0}, {"C": 2, "H": 6}, 30.0) is None
