"""Bondi's own radii, the extension, and the steric calculator's use of them.

Every expected number here was read from a paper, and the test says which: Bondi 1964 Table I (page image, checked
against Mantina et al.'s Table 9 and Poater et al.'s Table 1) and Table XIV, Mantina et al.'s abstract. The
investigation is `docs/VDW_RADII_ASSESSMENT.md`.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem import vdw_radii
from openchem.chem.steric import BONDI_SCALE, compute_steric_analysis
from openchem.chem.vdw_radii import BONDI_1964, MANTINA_2009, bondi_radius, radius_source
from openchem.domain.calculator import GEOMETRY
from openchem.domain.result_store import CURRENT_METHOD_VERSIONS, LEGACY_METHOD_VERSIONS, STERIC_METHOD

_TABLE = Chem.GetPeriodicTable()


def _number(symbol: str) -> int:
    return _TABLE.GetAtomicNumber(symbol)


# --- the table is the paper's -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("symbol, value", [
    ("H", 1.20), ("He", 1.40), ("C", 1.70), ("N", 1.55), ("O", 1.52), ("F", 1.47), ("Ne", 1.54),
    ("Si", 2.10), ("P", 1.80), ("S", 1.80), ("Cl", 1.75), ("Ar", 1.88),
    ("As", 1.85), ("Se", 1.90), ("Br", 1.85), ("Kr", 2.02), ("Te", 2.06), ("I", 1.98), ("Xe", 2.16),
])
def test_bondis_table_one_values_are_the_papers(symbol, value):
    """Bondi 1964, Table I, read from the page image. Bromine is 1.85 there (Mantina's Table 9 prints 1.83, the
    paper does not) and iodine 1.98 (the running text says 1.97, the table and every later source 1.98)."""
    assert BONDI_1964[symbol] == value
    assert bondi_radius(_number(symbol)) == value


@pytest.mark.parametrize("symbol, value", [
    ("Li", 1.82), ("Na", 2.27), ("Mg", 1.73), ("K", 2.75), ("Ga", 1.87), ("In", 1.93), ("Sn", 2.17), ("Tl", 1.96), ("Pb", 2.02),
])
def test_bondis_main_group_metals_are_table_fourteen(symbol, value):
    """Table XIV, from critical volumes (Mantina's Table 9 prints lithium as 1.81; the paper says 1.82)."""
    assert BONDI_1964[symbol] == value


def test_the_scaled_values_equal_poater_tables_one():
    """Poater et al. 2009, Table 1, 'Bondi*1.17': H 1.40, C(sp2) 1.99, N(sp2) 1.81, O 1.78, F 1.72, P 2.11."""
    scaled = {symbol: round(BONDI_1964[symbol] * BONDI_SCALE, 2) for symbol in ("H", "C", "N", "O", "F", "P")}

    assert scaled == {"H": 1.40, "C": 1.99, "N": 1.81, "O": 1.78, "F": 1.72, "P": 2.11}


def test_mantinas_sixteen_are_the_abstracts():
    """Mantina et al. 2009, abstract: 'the newly determined radii (in A) are ...'."""
    assert MANTINA_2009 == {
        "Be": 1.53, "B": 1.92, "Al": 1.84, "Ca": 2.31, "Ge": 2.11, "Rb": 3.03, "Sr": 2.49, "Sb": 2.06,
        "Cs": 3.43, "Ba": 2.68, "Bi": 2.07, "Po": 1.97, "At": 2.02, "Rn": 2.20, "Fr": 3.48, "Ra": 2.83,
    }


def test_the_two_tables_do_not_overlap():
    """An element in both would make which one wins a matter of dictionary order."""
    assert not set(BONDI_1964) & set(MANTINA_2009)


def test_hydrogen_is_bondis_not_the_crc_handbooks():
    """1.20 and not 1.10, on purpose (the module docstring says why): it is the volume convention, and the value
    the buried-volume papers and the exact cone angle use."""
    assert bondi_radius(1) == 1.20


# --- source and fallback ------------------------------------------------------------------------------------------------


def test_each_radius_says_which_table_it_came_from():
    assert radius_source(_number("P")) == vdw_radii.SOURCE_BONDI
    assert radius_source(_number("B")) == vdw_radii.SOURCE_MANTINA
    assert radius_source(_number("Fe")) == vdw_radii.SOURCE_RDKIT


def test_an_element_neither_source_covers_falls_back_to_rdkit_and_says_so():
    assert bondi_radius(_number("Fe")) == pytest.approx(_TABLE.GetRvdw("Fe"))


def test_phosphorus_is_not_rdkits():
    """The reason this module exists: RDKit's phosphorus is 1.95."""
    assert bondi_radius(15) == 1.80 != _TABLE.GetRvdw("P")


# --- the steric calculator uses it ---------------------------------------------------------------------------------------


def test_the_steric_buried_volume_of_phosphine_is_computed_with_bondis_phosphorus():
    """PH3 omits its hydrogens, so phosphorus is the whole answer: 17.65% with Bondi's 1.80 x 1.17, against 21.26%
    with RDKit's 1.95 (measured, benchmarks/vdw_radii/radii_study.py)."""
    result = compute_steric_analysis(Chem.MolFromSmiles("P"), "m", {"conformers": 3})
    facts = {fact.label: fact.display_value for fact in result.facts}

    assert float(facts["Percent buried volume"]) == pytest.approx(17.65, abs=0.3)


def test_the_exact_cone_angle_is_unchanged_by_the_table():
    """Hydrogen and carbon set the cone, and they agree between the tables: PMe3 stays at 117.2 degrees."""
    result = compute_steric_analysis(Chem.MolFromSmiles("CP(C)C"), "m", {"conformers": 5})
    facts = {fact.label: fact.display_value for fact in result.facts}

    assert float(facts["Exact cone angle"]) == pytest.approx(117.2, abs=0.5)


def test_a_steric_result_records_its_method_and_its_radii():
    result = compute_steric_analysis(Chem.MolFromSmiles("CP(C)C"), "m", {"conformers": 3})

    assert result.provenance.parameters["method"] == STERIC_METHOD == "steric-v2"
    assert result.provenance.parameters["radii"] == vdw_radii.RADII_LABEL


def test_the_method_version_is_part_of_the_stored_identity():
    from openchem.services.result_identity import make_identity

    result = compute_steric_analysis(Chem.MolFromSmiles("CP(C)C"), "m", {"conformers": 3})
    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY, input_fingerprint="fp", producer="core"
    )

    assert identity.method_version == STERIC_METHOD == CURRENT_METHOD_VERSIONS["steric_analysis"]


def test_a_steric_result_saved_before_the_change_is_kept_and_labelled():
    """The project's rule for a change of meaning: the old result sits beside the new one under its own label and is
    never replayed as the current method."""
    from openchem.domain.result_store import SessionResultStore, StoredResult
    from openchem.services.result_identity import make_identity

    result = compute_steric_analysis(Chem.MolFromSmiles("CP(C)C"), "m", {"conformers": 3})
    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY, input_fingerprint="fp", producer="core"
    )
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=result))
    saved = store.to_dict()
    (entry,) = saved["molecules"]["m"]["results"]
    entry.pop("method_version")

    (restored,) = SessionResultStore.from_dict(saved, "project").fresh_results("m", {GEOMETRY: "fp"})

    legacy, label = LEGACY_METHOD_VERSIONS["steric_analysis"]
    assert restored.identity.method_version == legacy == "legacy-rdkit-radii-v1"
    assert restored.result.name == label and label.startswith("Ligand Steric Bulk") and "previous method" in label


# --- an older Geometry result said "Bondi" for RDKit's table: a reader's note, not a new method -----------------------


def _geometry_result():
    from rdkit.Chem import AllChem

    from openchem.chem.geometry_analysis import compute_geometry_analysis

    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    AllChem.MMFFOptimizeMolecule(mol)
    return compute_geometry_analysis(mol, "m", {})


def _as_saved_before_the_relabel(result):
    """The same result with the one line the earlier version wrote, which is what a saved project holds."""
    from dataclasses import replace

    from openchem.domain.result_store import STORED_TEXT_NOTES

    (old,) = STORED_TEXT_NOTES["geometry_analysis"]
    current = "Van der Waals radii from RDKit's table (Batsanov's recommended set, not Bondi's)."
    facts = tuple(replace(f, limitations=tuple(old if t == current else t for t in f.limitations)) for f in result.facts)
    return replace(result, facts=facts)


def _round_trip(result):
    from openchem.domain.result_store import SessionResultStore, StoredResult
    from openchem.services.result_identity import make_identity

    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY, input_fingerprint="fp", producer="core"
    )
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=result))
    (restored,) = SessionResultStore.from_dict(store.to_dict(), "project").fresh_results("m", {GEOMETRY: "fp"})
    return identity, restored


def test_an_older_geometry_result_loads_with_a_note_where_it_said_bondi():
    from openchem.domain.result_store import STORED_TEXT_NOTES

    ((old, note),) = STORED_TEXT_NOTES["geometry_analysis"].items()
    saved = _as_saved_before_the_relabel(_geometry_result())
    assert any(old in f.limitations for f in saved.facts), "the fixture must carry the old line, or this proves nothing"

    _identity, restored = _round_trip(saved)

    shown = [text for fact in restored.result.facts for text in fact.limitations]
    assert note in shown and old not in shown
    assert "not Bondi's" in note and "numbers are unchanged" in note


def test_the_note_changes_the_words_only_not_the_numbers_the_provenance_or_the_method():
    saved = _as_saved_before_the_relabel(_geometry_result())
    identity, restored = _round_trip(saved)

    assert [f.value for f in restored.result.facts] == [f.value for f in saved.facts]
    assert [f.display_value for f in restored.result.facts] == [f.display_value for f in saved.facts]
    assert restored.result.provenance == saved.provenance
    assert restored.identity.method_version == identity.method_version == CURRENT_METHOD_VERSIONS["geometry_analysis"]


def test_a_current_geometry_result_never_says_the_old_line_so_the_note_cannot_shadow_live_text():
    from openchem.domain.result_store import STORED_TEXT_NOTES

    texts = {text for fact in _geometry_result().facts for text in fact.limitations}

    assert not texts & set(STORED_TEXT_NOTES["geometry_analysis"])
    assert any("RDKit's table" in text for text in texts)


def test_only_an_exact_match_is_replaced():
    from dataclasses import replace

    result = _geometry_result()
    other = "Bondi van der Waals radii, scaled."
    unrelated = replace(result, facts=tuple(replace(f, limitations=(*f.limitations, other)) for f in result.facts))

    _identity, restored = _round_trip(unrelated)

    assert all(other in f.limitations for f in restored.result.facts)
