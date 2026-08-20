"""Cao-Liu TSEI, checked against the values the paper prints.

**TWO ORACLES, AND THE EXACT ONE CARRIES THE WEIGHT.** The paper reports
correlations of 0.9912 and 0.9845 against biphenyl dihedral angles, and
those are a fine behavioural check -- but a correlation is a weak
transcription oracle, because plenty of systematically wrong
implementations still correlate strongly. Table 1 prints exact TSEI for
normal alkyls from n = 1 to 20, converging on 1.2009, and reproducing a
converging series to four decimals is much harder to do by accident.

The table below is TYPED FROM THE PAGE. Generating it from either code
path would make this file one implementation reading itself.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.tsei import normal_alkyl_tsei, substituent_atoms, substituent_tsei

#: Cao & Liu, Table 1, "TSEI and delta-TSEI Values of Normal Alkyl".
#: Typed from the paper.
_TABLE_1 = {
    1: 1.0000, 2: 1.1250, 3: 1.1620, 4: 1.1777, 5: 1.1857,
    6: 1.1903, 7: 1.1932, 8: 1.1952, 9: 1.1965, 10: 1.1975,
    11: 1.1983, 12: 1.1989, 13: 1.1993, 14: 1.1997, 15: 1.2000,
    16: 1.2002, 17: 1.2004, 18: 1.2006, 19: 1.2007, 20: 1.2009,
}


def _chain(carbons: int) -> Chem.Mol:
    """A reaction centre (atom 0) with a straight chain hung off atom 1."""
    return Chem.MolFromSmiles("C" + "C" * carbons)


@pytest.mark.parametrize("carbons,expected", sorted(_TABLE_1.items()))
def test_the_closed_form_reproduces_table_1(carbons, expected):
    assert normal_alkyl_tsei(carbons) == pytest.approx(expected, abs=5e-5)


@pytest.mark.parametrize("carbons,expected", sorted(_TABLE_1.items()))
def test_walking_a_real_structure_reproduces_table_1(carbons, expected):
    """The route a caller actually takes, against the same printed values.

    Independent of `normal_alkyl_tsei`: this counts bonds through an
    RDKit distance matrix, that one sums a series. Both are checked
    against the page rather than against each other.
    """
    result = substituent_tsei(_chain(carbons), 0, 1)
    assert result.value == pytest.approx(expected, abs=5e-5)
    assert result.atoms == carbons


def test_the_series_converges_where_the_paper_says_it_does():
    """1.2009 at n = 20, and still 1.2009 far beyond it.

    The convergence is the shape that makes this table a good oracle: an
    implementation with the wrong exponent reproduces neither the early
    values nor the limit.
    """
    assert normal_alkyl_tsei(20) == pytest.approx(1.2009, abs=5e-5)
    assert normal_alkyl_tsei(200) == pytest.approx(1.2021, abs=5e-4)
    assert normal_alkyl_tsei(20) < normal_alkyl_tsei(200) < 1.21


def test_a_second_tier_atom_contributes_the_increment_the_paper_states():
    """"their corresponding steric effect increments delta-TSEI caused by
    second tier carbon atoms should be 0.1250, 0.2500, and 0.3750".

    So isopropyl is 1 + 2 x 0.1250 and tert-butyl is 1 + 3 x 0.1250 --
    a branch check the normal-alkyl series cannot make, since every atom
    there sits at a different distance.
    """
    isopropyl = substituent_tsei(Chem.MolFromSmiles("CC(C)C"), 0, 1)
    tert_butyl = substituent_tsei(Chem.MolFromSmiles("CC(C)(C)C"), 0, 1)

    assert isopropyl.value == pytest.approx(1.0 + 0.2500, abs=5e-5)
    assert tert_butyl.value == pytest.approx(1.0 + 0.3750, abs=5e-5)


def test_hydrogens_are_ignored_as_the_paper_simplifies():
    """"if the hydrogen atoms are ignored" -- eq 6 onward.

    Asserted through an EXPLICIT-hydrogen molecule, because that is the
    form where getting it wrong changes the answer, and a SMILES-only
    test could never tell.
    """
    implicit = substituent_tsei(_chain(3), 0, 1)
    explicit = substituent_tsei(Chem.AddHs(_chain(3)), 0, 1)
    assert explicit.value == pytest.approx(implicit.value, abs=1e-12)
    assert explicit.atoms == implicit.atoms == 3


def test_the_substituent_stops_at_the_reaction_centre():
    """A walk that crossed the centre would swallow the rest of the
    molecule and score the whole thing as one substituent."""
    # centre = atom 0; two separate methyls hang off it.
    mol = Chem.MolFromSmiles("C(C)C")
    first = substituent_atoms(mol, 0, 1)
    assert first == [1], f"the walk leaked past the reaction centre: {first}"


def test_a_ring_fused_to_the_centre_is_counted_whole():
    """Not an edge case being tolerated -- those atoms really do screen it.

    Cyclohexyl on a centre: six ring carbons, at distances 1, 2, 2, 3, 3, 4.
    """
    result = substituent_tsei(Chem.MolFromSmiles("C1CCCCC1C"), 6, 0)
    assert result.atoms == 6
    expected = 1 + 2 * (1 / 8) + 2 * (1 / 27) + 1 / 64
    assert result.value == pytest.approx(expected, abs=5e-5)


def test_the_index_is_reported_per_atom_as_the_paper_tabulates_it():
    """`delta-TSEI` is the paper's own column, and it is what makes a
    disagreement debuggable rather than merely wrong."""
    result = substituent_tsei(_chain(3), 0, 1)
    assert sorted(round(v, 6) for v in result.increments.values()) == sorted(
        round(1 / d**3, 6) for d in (1, 2, 3)
    )
    assert sum(result.increments.values()) == pytest.approx(result.value)
