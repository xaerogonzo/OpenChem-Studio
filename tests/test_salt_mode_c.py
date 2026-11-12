"""Mode C: one two-component pair, candidate states, no pKa ranking."""

from rdkit import Chem

from openchem.chem.pka_species_ladder import LADDER_NOTE, LadderRefusal, SpeciesLadder
from openchem.chem.salt_mode_c import enumerate_pair
from openchem.domain.salt_stoichiometry import ModeCResult


def test_pyridinium_and_acetate_make_one_composition() -> None:
    result = enumerate_pair(
        (Chem.MolFromSmiles("c1cc[nH+]cc1"),),
        (Chem.MolFromSmiles("CC(=O)[O-]"),),
    )
    assert isinstance(result, ModeCResult)
    assert result.generated == 1
    assert result.returned == 1
    assert result.omitted == 0
    assert result.hits[0].cation_count == 1
    assert result.hits[0].anion_count == 1


def test_the_same_molecules_yield_the_same_mode_c_list() -> None:
    args = (
        (Chem.MolFromSmiles("c1cc[nH+]cc1"),),
        (Chem.MolFromSmiles("CC(=O)[O-]"),),
    )
    first = enumerate_pair(*args)
    second = enumerate_pair(*args)
    assert first.hits == second.hits
    assert (first.generated, first.returned, first.omitted) == (
        second.generated,
        second.returned,
        second.omitted,
    )


def test_a_usable_ladder_carries_its_standing_note() -> None:
    pyridinium = Chem.MolFromSmiles("c1cc[nH+]cc1")
    ladder = SpeciesLadder(
        molblocks=(Chem.MolToMolBlock(pyridinium),),
        hidden=frozenset(),
        kinds_match_curve=True,
        charge_labels_match=True,
        net_charges=(1,),
    )
    result = enumerate_pair(
        (pyridinium,),
        (Chem.MolFromSmiles("CC(=O)[O-]"),),
        cation_ladder=ladder,
    )
    assert isinstance(result, ModeCResult)
    assert LADDER_NOTE in result.notes
    assert result.generated == 1


def test_a_ladder_refusal_is_a_note_and_user_ions_still_compose() -> None:
    result = enumerate_pair(
        (Chem.MolFromSmiles("c1cc[nH+]cc1"),),
        (Chem.MolFromSmiles("CC(=O)[O-]"),),
        cation_ladder=LadderRefusal("explicit_hydrogens", "no pictures"),
    )
    assert isinstance(result, ModeCResult)
    assert "no pictures" in result.notes
    assert result.generated == 1
    assert LADDER_NOTE not in result.notes
