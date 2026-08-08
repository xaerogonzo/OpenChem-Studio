"""The adapter over the vendored organometallic perception.

The vendored namer recognises a sandwich complex only in its IONIC form
(`[cH-]1cccc1.[cH-]1cccc1.[Fe+2]`). Most people draw ferrocene with
bonds from the iron to both rings, and that returned nothing at all.

The fix normalises the DRAWING rather than editing 5,020 lines of
vendored perception -- see `_as_ionic_sandwich`. These tests pin both
halves: that bonded drawings are now perceived, and that the ionic path
is untouched.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.organometallic_adapter import _as_ionic_sandwich, metallocene

IONIC_FERROCENE = "[cH-]1cccc1.[cH-]1cccc1.[Fe+2]"
BONDED_FERROCENE = "C1=CC=C[CH]1[Fe]C1[CH]=CC=C1"
BONDED_METHYLFERROCENE = "CC1=CC=C[CH]1[Fe]C1[CH]=CC=C1"


def _mol(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


def test_the_ionic_form_is_unchanged_by_any_of_this():
    """Normalisation only ever runs on a molecule the vendor has already
    declined, so the path that worked before cannot regress."""
    found = metallocene(_mol(IONIC_FERROCENE))

    assert found is not None
    assert found.retained_name == "ferrocene"
    assert len(found.rings) == 2


@pytest.mark.parametrize(
    "smiles,metal,name",
    [
        (BONDED_FERROCENE, "Fe", "ferrocene"),
        ("C1=CC=C[CH]1[Ru]C1[CH]=CC=C1", "Ru", "ruthenocene"),
        ("C1=CC=C[CH]1[Co]C1[CH]=CC=C1", "Co", "cobaltocene"),
    ],
)
def test_a_bonded_sandwich_is_perceived_and_keeps_its_retained_name(smiles, metal, name):
    """**The gap this closes.** Every one of these returned None before,
    which is what somebody drawing ferrocene the ordinary way saw."""
    found = metallocene(_mol(smiles))

    assert found is not None
    assert found.metal_symbol == metal
    assert found.retained_name == name
    assert len(found.rings) == 2


def test_every_index_addresses_the_CALLERS_molecule():
    """Normalisation builds a new molecule, and the indices it reports
    must still mean something in the one that was passed in. Removing a
    bond does not renumber atoms -- asserted rather than assumed, because
    an index that quietly means something else is the bug this project
    has already hit in Ketcher's pool ids and in the crystal viewer."""
    mol = _mol(BONDED_FERROCENE)

    found = metallocene(mol)

    assert mol.GetAtomWithIdx(found.metal_index).GetSymbol() == "Fe"
    for ring in found.rings:
        assert len(ring.atom_indices) == 5
        assert {mol.GetAtomWithIdx(i).GetSymbol() for i in ring.atom_indices} == {"C"}


def test_a_substituted_ring_survives_normalisation():
    """**A substituted ring carbon has no hydrogen**, and forcing one on
    every ring atom made this fail to sanitise -- so plain ferrocene
    worked while methylferrocene returned None, which is the confusing
    kind of bug rather than the obvious kind. The general classifier
    handles it and reports the prefix."""
    found = metallocene(_mol(BONDED_METHYLFERROCENE))

    assert found is not None
    assert found.metal_symbol == "Fe"
    assert "methyl" in {ring.substituent_prefix for ring in found.rings}


@pytest.mark.parametrize(
    "smiles,why",
    [
        ("[Fe](Cl)(Cl)Cl", "not a sandwich at all"),
        ("C1=CC=C[CH]1[Mn](C#[O+])(C#[O+])C#[O+]", "half sandwich: one ring, not two"),
        ("c1ccccc1", "no metal"),
    ],
)
def test_things_that_are_not_two_ring_sandwiches_are_refused(smiles, why):
    """Normalising something that is not a sandwich would hand the vendor
    a molecule with bonds removed and charges invented."""
    assert _as_ionic_sandwich(_mol(smiles)) is None, why


def test_pentamethylferrocene_is_a_VENDOR_limit_not_a_normalisation_one():
    """Asserted deliberately, so the two are never confused.

    Normalisation produces a perfectly good ionic form for it, and the
    vendored perception declines that form too -- so the gap is upstream.
    If a future vendor learns this structure, this test fails and the
    caveat can come off.
    """
    bonded = _mol("CC1=C(C)C(C)=C(C)[CH]1[Fe]C1[CH]=CC=C1")

    normalised = _as_ionic_sandwich(bonded)

    assert normalised is not None                      # our half works
    assert Chem.MolToSmiles(normalised).count("[cH-]") + \
           Chem.MolToSmiles(normalised).count("[c-]") >= 1
    # and the vendor declines the ionic form independently of us
    assert metallocene(_mol("[c-]1(C)c(C)c(C)c(C)c1C.[cH-]1cccc1.[Fe+2]")) is None
    assert metallocene(bonded) is None


def test_a_drawing_that_will_not_sanitise_returns_None_rather_than_raising():
    """Fails soft, like everything else in this adapter: a namer that
    cannot classify something must not take a calculator down."""
    assert metallocene(None) is None
