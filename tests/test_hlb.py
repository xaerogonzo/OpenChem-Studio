"""Griffin's HLB: the value, and where it means nothing.

**THE ORACLE IS SCHOTT'S CLOSED FORM, NOT A TABLE OF HLB VALUES**, and
that choice is the most important thing in this file.

The obvious acceptance set was Guo 2006, which tabulates 224 nonionic
surfactants. It is the wrong one: that paper mentions Griffin ZERO times,
and its reference column is manufacturer data -- its own footnotes read
"obtained from the data reported by BASF Corp." and "by ICI Americas
Inc.". Scoring a Griffin implementation against a Davies/ECL paper's
manufacturer column would compare two scales and manufacture a
disagreement that reads as an implementation bug.

Schott Eq. [2] is Griffin's own definition specialised to two named
series, with the constants printed. Checking against it is
Griffin-to-Griffin.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.hlb import (
    EO_UNIT_MASS,
    GriffinHlb,
    HlbRefusal,
    griffin_hlb,
    griffin_hlb_from_chain,
)

#: Schott's own worked constants: the molecular mass of the lipophile.
_OCTYLPHENOL = 206.3
_DODECANOL = 186.3


def _brij(units: int) -> str:
    """C12H25-(OCH2CH2)p-OH, the Brij series Schott gives A = 186.3 for."""
    return "CCCCCCCCCCCC" + "OCC" * units + "O"


def _triton(units: int) -> str:
    """p-t-octylphenol-(OCH2CH2)p-OH, the Triton X series, A = 206.3."""
    return "CC(C)(C)CC(C)(C)c1ccc(cc1)" + "OCC" * units + "O"


@pytest.mark.parametrize("units", [1, 4, 5, 10, 20])
def test_the_ethylene_oxide_units_are_counted_exactly(units):
    """The count is the whole calculation, and it was wrong twice.

    `[O][CH2][CH2]` matches a polyoxyethylene chain from BOTH ends, so
    every internal oxygen counted twice and a C12E4 came out as 9 units.
    A parametrised count is what turns that from "the number looks a bit
    high" into a failure that names the size.
    """
    result = griffin_hlb(Chem.MolFromSmiles(_brij(units)))
    assert result.ethylene_oxide_units == units


@pytest.mark.parametrize(
    "smiles_for, lipophile", [(_brij, _DODECANOL), (_triton, _OCTYLPHENOL)]
)
@pytest.mark.parametrize("units", [4, 5, 10, 20])
def test_griffin_hlb_reproduces_schotts_closed_form(smiles_for, lipophile, units):
    """Schott Eq. [2]: `881 p / (44.05 p + A)`.

    The two routes are independent -- one counts substructures and weighs
    the molecule, the other is the paper's arithmetic on p and A -- so
    agreement is a real check rather than one implementation reading
    itself.

    The tolerance is 0.01 because RDKit weighs the molecule from exact
    atomic masses while Schott's constants are rounded to four figures
    (44.05, 186.3, 206.3). Measured, the gap is about 0.002.
    """
    result = griffin_hlb(Chem.MolFromSmiles(smiles_for(units)))
    assert result.applicable, result.refusal
    expected = griffin_hlb_from_chain(units, lipophile)
    assert result.value == pytest.approx(expected, abs=0.01)


def test_the_closed_form_is_griffins_definition_and_not_a_second_one():
    """`881 = 20 x 44.05`, which is what makes Eq. [2] Eq. [1].

    Asserted so the oracle cannot quietly become an independent
    correlation that happens to agree on the fixtures above.
    """
    assert griffin_hlb_from_chain(1, 0.0) == pytest.approx(20.0)
    assert 20.0 * EO_UNIT_MASS == pytest.approx(881.0)


# --- applicability ----------------------------------------------------------


def test_a_drug_like_molecule_is_refused_rather_than_given_a_number():
    """The failure this predicate exists to prevent.

    Griffin's definition opens "for nonionic surfactants with
    polyoxyethylene as the sole hydrophilic moiety". Returning 4.14 for
    aspirin and relying on documentation to say it is meaningless is the
    shape the `AlertResult` migration spent a phase removing.
    """
    result = griffin_hlb(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    assert not result.applicable
    assert result.value is None
    assert result.refusal is HlbRefusal.NO_POLYOXYETHYLENE


def test_a_plain_fatty_alcohol_is_refused():
    """DODECANOL WAS ACCEPTED BY THE FIRST VERSION, at HLB 4.7.

    Its terminal -OH is an `OX2` bonded to a CH2 bonded to a CH2, so a
    pattern written as "an oxygen then an ethylene" matched a molecule
    with no polyoxyethylene in it at all. It is the lipophile Brij is
    built FROM.
    """
    result = griffin_hlb(Chem.MolFromSmiles("CCCCCCCCCCCCO"))
    assert result.refusal is HlbRefusal.NO_POLYOXYETHYLENE


def test_a_sorbitan_ester_is_refused_even_though_it_carries_polyoxyethylene():
    """THE CASE MOST LIKELY TO BE GOT WRONG, and it is Tween.

    Griffin's EXPERIMENTS produced the published values for Span and
    Tween -- Schott says Davies' group numbers "were calculated
    exclusively from Griffin's experimental HLB values for sorbitan
    esters and polysorbates". But sorbitan is a polyhydric alcohol, so
    polyoxyethylene is not the sole hydrophile and Griffin's FORMULA does
    not apply, whatever his experiments measured.

    A test that fed a Tween to this and compared against 15.0 would be
    testing the wrong thing.
    """
    tween_like = "CCCCCCCCCCCC(=O)OCC(O)C1OCC(OCCOCCO)C1O"
    result = griffin_hlb(Chem.MolFromSmiles(tween_like))
    assert result.ethylene_oxide_units > 0, "setup: this fixture has no POE chain"
    assert result.refusal is HlbRefusal.NOT_SOLE_HYDROPHILE
    assert "polyhydric" in result.detail


def test_an_ionic_surfactant_is_refused():
    result = griffin_hlb(Chem.MolFromSmiles("CCCCCCCCCCCCOCCOCCOS(=O)(=O)[O-].[Na+]"))
    assert result.refusal is HlbRefusal.NOT_SOLE_HYDROPHILE


def test_a_peg_ester_of_a_fatty_acid_is_ACCEPTED(  ):
    """The control, and it is load-bearing.

    Schott names the domain explicitly: "polyoxyethylated alcohols and
    alkylphenols, plus polyethylene glycol esters of fatty acids", which
    together are over 73% of US nonionic surfactant production. A
    predicate that refused the esters would look like a working guard
    while excluding a third of the very population Griffin is for.
    """
    result = griffin_hlb(Chem.MolFromSmiles("CCCCCCCCCCCC(=O)" + "OCC" * 8 + "O"))
    assert result.applicable, result.refusal
    assert 0 < result.value < 20


def test_an_unreadable_structure_is_refused_rather_than_crashing():
    assert griffin_hlb(None).refusal is HlbRefusal.NOT_A_STRUCTURE


def test_the_result_cannot_carry_a_value_and_a_refusal_at_once():
    """`value is None` exactly when `refusal` is set.

    The whole point of the shape is that a consumer cannot read a number
    off a refused answer, so the invariant is asserted rather than left
    to each construction site.
    """
    samples = ["CC(=O)Oc1ccccc1C(=O)O", "CCCCCCCCCCCCO", _brij(6), _triton(3)]
    for smiles in samples:
        result = griffin_hlb(Chem.MolFromSmiles(smiles))
        assert (result.value is None) is (result.refusal is not None), smiles
        assert isinstance(result, GriffinHlb)
