"""Phase 27: structure generators and Markush enumeration."""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.markush import (
    AtomListPosition,
    MarkushError,
    MarkushStructure,
    RGroupDefinition,
    compute_markush_enumeration,
    describe_library_size,
    enumerate_markush,
    library_size,
    parse_substituent_spec,
)
from openchem.chem.structure_generators import (
    RESONANCE_FLAG_SETS,
    enumerate_resonance_forms,
    enumerate_stereoisomers,
    enumerate_tautomers,
)
from openchem.domain.common import CacheState

BENZENE_CORE = "[*:1]c1ccc([*:2])cc1"


def _markush(**overrides) -> MarkushStructure:
    defaults = dict(
        core_smiles=BENZENE_CORE,
        r_groups=[
            RGroupDefinition(1, ["[*:99]Cl", "[*:99]F", "[*:99]Br"]),
            RGroupDefinition(2, ["[*:99]O", "[*:99]N", "[*:99]OC", "[*:99]C"]),
        ],
    )
    defaults.update(overrides)
    return MarkushStructure(**defaults)


# --- Structure generators ----------------------------------------------


def test_two_stereocentres_give_four_stereoisomers():
    result = enumerate_stereoisomers(Chem.MolFromSmiles("CC(F)C(Cl)C"), "mol-1")
    assert len(result.entries) == 4


def test_cyclohexanone_has_a_keto_and_an_enol_tautomer():
    result = enumerate_tautomers(Chem.MolFromSmiles("O=C1CCCCC1"), "mol-1")
    smiles = {entry.metadata["smiles"] for entry in result.entries}

    assert "O=C1CCCCC1" in smiles
    assert "OC1=CCCCC1" in smiles


def test_exactly_one_tautomer_is_flagged_canonical():
    result = enumerate_tautomers(Chem.MolFromSmiles("O=C1CCCCC1"), "mol-1")
    assert sum(1 for entry in result.entries if entry.metadata["canonical"]) == 1


def test_resonance_flag_set_changes_how_many_forms_are_found():
    """The load-bearing finding: RDKit's DEFAULT flags return ZERO forms for
    diazomethane -- Marvin's own documentation example. The wider flag set
    finds more than the narrow one, which is why this is a user choice
    rather than a hardcoded constant."""
    narrow = enumerate_resonance_forms(
        Chem.MolFromSmiles("[CH2-][N+]#N"), "mol-1", flag_set="Major contributors"
    )
    wide = enumerate_resonance_forms(
        Chem.MolFromSmiles("[CH2-][N+]#N"),
        "mol-1",
        flag_set="All forms (charge-separated, incomplete octets)",
    )

    assert len(narrow.entries) >= 2, "the default RDKit flags would give 0 here"
    assert len(wide.entries) > len(narrow.entries)


def test_both_resonance_flag_sets_are_offered():
    assert set(RESONANCE_FLAG_SETS) == {
        "Major contributors",
        "All forms (charge-separated, incomplete octets)",
    }


def test_resonance_forms_are_not_deduplicated_by_canonical_smiles():
    """Acetate's two contributors both serialize to `CC(=O)[O-]`. They are
    genuinely different molecules; only canonical SMILES hides it. Any
    dedupe on that string would silently delete half the result."""
    result = enumerate_resonance_forms(Chem.MolFromSmiles("CC(=O)[O-]"), "mol-1")
    assert len(result.entries) == 2


def test_generated_entries_carry_depictable_molblocks():
    result = enumerate_stereoisomers(Chem.MolFromSmiles("CC(F)C(Cl)C"), "mol-1")
    for entry in result.entries:
        assert Chem.MolFromMolBlock(entry.molblock) is not None


# --- Markush: library size ---------------------------------------------


def test_library_size_is_the_product_of_the_option_counts():
    assert library_size(_markush()) == 12  # 3 x 4


def test_library_size_is_computed_without_enumerating():
    """The whole point of the feature -- Marvin's documentation example
    reports 38,102,400 members, which can only be answered by arithmetic.
    A space far too large to walk must still return instantly."""
    huge = MarkushStructure(
        core_smiles=BENZENE_CORE,
        r_groups=[
            RGroupDefinition(1, [f"[*:99]C{'C' * n}" for n in range(30)]),
            RGroupDefinition(2, [f"[*:99]N{'C' * n}" for n in range(30)]),
        ],
    )
    assert library_size(huge) == 900


def test_selected_part_sizing_counts_only_the_chosen_labels():
    assert library_size(_markush(), only_labels={1}) == 3
    assert library_size(_markush(), only_labels={2}) == 4


def test_describe_library_size_reports_an_exact_count_when_readable():
    assert "12" in describe_library_size(_markush())


# --- Markush: enumeration modes ----------------------------------------


def test_sequential_enumeration_respects_the_generation_maximum():
    result = enumerate_markush(_markush(), "mol-1", mode="sequential", max_structures=5)

    assert len(result.entries) == 5
    assert result.total_available == 12
    assert result.truncated


def test_sequential_enumeration_is_deterministic():
    first = [e.label for e in enumerate_markush(_markush(), "m", max_structures=6).entries]
    second = [e.label for e in enumerate_markush(_markush(), "m", max_structures=6).entries]
    assert first == second


def test_random_enumeration_is_reproducible_for_a_given_seed():
    a = [e.label for e in enumerate_markush(_markush(), "m", mode="random", max_structures=4, seed=7).entries]
    b = [e.label for e in enumerate_markush(_markush(), "m", mode="random", max_structures=4, seed=7).entries]
    assert a == b


def test_random_enumeration_differs_between_seeds():
    a = [e.label for e in enumerate_markush(_markush(), "m", mode="random", max_structures=4, seed=7).entries]
    b = [e.label for e in enumerate_markush(_markush(), "m", mode="random", max_structures=4, seed=9).entries]
    assert a != b


def test_random_enumeration_terminates_when_asked_for_more_than_exists():
    """A 12-member library asked for 500 samples must stop, not spin."""
    result = enumerate_markush(_markush(), "m", mode="random", max_structures=500, seed=1)
    assert len(result.entries) <= 12


def test_random_enumeration_returns_distinct_members():
    result = enumerate_markush(_markush(), "m", mode="random", max_structures=8, seed=3)
    assert len({e.label for e in result.entries}) == len(result.entries)


def test_selected_part_enumeration_leaves_other_labels_generic():
    """Marvin's documented behaviour: enumerating only part of a Markush
    structure yields MORE SPECIFIC MARKUSH STRUCTURES, not fully specified
    molecules -- the untouched attachment point survives in the output."""
    result = enumerate_markush(_markush(), "m", only_labels={1}, max_structures=10)

    assert len(result.entries) == 3  # R1's three options only
    assert all("*" in entry.label for entry in result.entries), "R2 should remain an attachment point"


# --- Markush: valence filter -------------------------------------------


def _quaternary_swap() -> MarkushStructure:
    """A quaternary carbon swapped to N/O/F -- three of the four options
    are impossible valences."""
    return MarkushStructure(
        core_smiles="CC(C)(C)C", atom_lists=[AtomListPosition(1, ["C", "N", "O", "F"])]
    )


def test_valence_filter_removes_impossible_structures():
    filtered = enumerate_markush(_quaternary_swap(), "m", valence_filter=True, max_structures=100)

    assert len(filtered.entries) == 1
    assert filtered.provenance.parameters["rejected_by_valence"] == 3


def test_turning_the_valence_filter_off_genuinely_returns_more():
    """Regression test for an inert checkbox: the first implementation
    skipped bad-valence members in BOTH branches, so the setting changed
    nothing. Sanitizing without SANITIZE_PROPERTIES keeps them usable."""
    on = enumerate_markush(_quaternary_swap(), "m", valence_filter=True, max_structures=100)
    off = enumerate_markush(_quaternary_swap(), "m", valence_filter=False, max_structures=100)

    assert len(off.entries) > len(on.entries)
    assert len(off.entries) == 4


def test_valence_error_structures_are_labelled_as_such():
    """In a grid of depictions an impossible structure looks perfectly
    normal unless it is called out."""
    off = enumerate_markush(_quaternary_swap(), "m", valence_filter=False, max_structures=100)
    bad = [entry for entry in off.entries if not entry.metadata["valence_ok"]]

    assert len(bad) == 3
    assert all("valence error" in entry.label for entry in bad)


def test_valence_labels_stay_ascii():
    """These labels reach logs and console streams; a Windows cp1252 stream
    raises UnicodeEncodeError on a warning glyph (hit while testing)."""
    off = enumerate_markush(_quaternary_swap(), "m", valence_filter=False, max_structures=100)
    for entry in off.entries:
        entry.label.encode("cp1252")


def test_library_size_ignores_the_valence_filter():
    """Matches Marvin, whose docs state the size 'does not consider the
    valence check filter' -- filtering would require generating everything,
    defeating the purpose."""
    assert library_size(_quaternary_swap()) == 4


# --- Atom lists ---------------------------------------------------------


def test_atom_list_substitutes_the_element_at_a_position():
    markush = MarkushStructure(
        core_smiles="C1CCCCC1", atom_lists=[AtomListPosition(0, ["C", "N", "O"])]
    )
    result = enumerate_markush(markush, "m", max_structures=10)
    smiles = {entry.metadata["smiles"] for entry in result.entries}

    assert {"C1CCCCC1", "C1CCNCC1", "C1CCOCC1"} <= smiles


# --- Spec parsing -------------------------------------------------------


def test_substituent_spec_parses_multiple_labels():
    groups = parse_substituent_spec("R1: Cl, F, Br; R2: O, N")

    assert [g.label for g in groups] == [1, 2]
    assert groups[0].substituents == ["[*:99]Cl", "[*:99]F", "[*:99]Br"]


def test_substituent_spec_rejects_malformed_input():
    with pytest.raises(MarkushError):
        parse_substituent_spec("just some text")
    with pytest.raises(MarkushError):
        parse_substituent_spec("RX: Cl")


def test_an_rgroup_with_no_substituents_is_rejected_at_construction():
    with pytest.raises(MarkushError):
        RGroupDefinition(1, [])


# --- The registered calculator -----------------------------------------


def test_calculator_requires_attachment_points_on_the_core():
    result = compute_markush_enumeration(
        Chem.MolFromSmiles("c1ccccc1"), "mol-1", {"substituents": "R1: Cl"}
    )

    assert result.cache_state == CacheState.FAILED
    assert "attachment points" in result.error


def test_calculator_requires_substituents_for_every_label():
    result = compute_markush_enumeration(
        Chem.MolFromSmiles(BENZENE_CORE), "mol-1", {"substituents": "R1: Cl"}
    )

    assert result.cache_state == CacheState.FAILED
    assert "R2" in result.error


def test_calculator_library_size_mode_generates_nothing():
    result = compute_markush_enumeration(
        Chem.MolFromSmiles(BENZENE_CORE),
        "mol-1",
        {"mode": "Markush library size", "substituents": "R1: Cl, F, Br; R2: O, N, OC, C"},
    )

    assert result.entries == []
    assert result.total_available == 12
    assert "12" in result.name


def test_calculator_sequential_mode_generates_structures():
    result = compute_markush_enumeration(
        Chem.MolFromSmiles(BENZENE_CORE),
        "mol-1",
        {
            "mode": "Sequential enumeration",
            "substituents": "R1: Cl, F, Br; R2: O, N, OC, C",
            "max_structures": 5,
        },
    )

    assert len(result.entries) == 5
    assert result.total_available == 12
