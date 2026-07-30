from __future__ import annotations

import math

from rdkit import Chem

from openchem.chem.logd import (
    classify_ionizable_centres,
    logd_from_microspecies,
    logd_from_pkas,
    logd_henderson_hasselbalch,
)

_IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
_PROPRANOLOL = "CC(C)NCC(O)COc1cccc2ccccc12"


def test_at_ph_equal_to_pka_logd_is_logp_minus_log10_of_2():
    """Half ionized at pH == pKa, so exactly half the compound partitions:
    logD = logP - log10(1 + 1). This is the one point the formula can be
    checked against arithmetic rather than a reference value."""
    value = logd_henderson_hasselbalch(logp=3.0, ph=5.0, pkas=[5.0], is_acid=[True])
    assert value == 3.0 - math.log10(2.0)


def test_far_below_its_pka_an_acid_is_neutral_so_logd_equals_logp():
    value = logd_henderson_hasselbalch(logp=3.0, ph=1.0, pkas=[9.0], is_acid=[True])
    assert abs(value - 3.0) < 1e-6


def test_an_acid_becomes_more_hydrophilic_as_ph_rises():
    values = [logd_henderson_hasselbalch(3.0, ph, [4.8], [True]) for ph in (2.0, 4.8, 7.4, 10.0)]
    assert values == sorted(values, reverse=True)
    assert values[-1] < values[0] - 3  # a real drop, not a rounding wobble


def test_a_base_becomes_more_lipophilic_as_ph_rises():
    values = [logd_henderson_hasselbalch(3.0, ph, [9.5], [False]) for ph in (2.0, 7.4, 9.5, 12.0)]
    assert values == sorted(values)


def test_extreme_ionization_does_not_overflow():
    """A centre ionized far past its pKa produces a 10**huge term -- must
    saturate rather than raise OverflowError."""
    value = logd_henderson_hasselbalch(3.0, 14.0, [-20.0], [True])
    assert math.isfinite(value)


def test_classify_ionizable_centres_finds_a_carboxylic_acid():
    assert classify_ionizable_centres(Chem.MolFromSmiles(_IBUPROFEN)) == (1, 0)


def test_classify_ionizable_centres_finds_a_basic_amine():
    acids, bases = classify_ionizable_centres(Chem.MolFromSmiles(_PROPRANOLOL))
    assert (acids, bases) == (0, 1)


def test_classify_ignores_amides_and_aromatic_nitrogen():
    """Same exclusions the Phase 20 hERG basic-amine pattern was verified
    against -- an amide N and a pyridine N are not basic centres."""
    assert classify_ionizable_centres(Chem.MolFromSmiles("CC(=O)N"))[1] == 0
    assert classify_ionizable_centres(Chem.MolFromSmiles("c1ccncc1"))[1] == 0


def test_benzene_has_no_ionizable_centre_so_logd_is_none():
    """None means "logD is just logP here" -- the caller should say that
    rather than present an identical number as a separate calculation."""
    assert logd_from_pkas(Chem.MolFromSmiles("c1ccccc1"), 7.4, []) is None


def test_ibuprofen_logd_falls_between_ph_2_and_ph_7_4():
    mol = Chem.MolFromSmiles(_IBUPROFEN)
    acidic = logd_from_pkas(mol, 2.0, [4.82])
    physiological = logd_from_pkas(mol, 7.4, [4.82])

    assert acidic > physiological
    # Ibuprofen is a carboxylic acid: essentially neutral at pH 2 and
    # substantially ionized at 7.4, a >2 log-unit swing.
    assert acidic - physiological > 2.0


def test_microspecies_fallback_is_ph_dependent_without_any_pka_model():
    """The no-pkasolver path must still respond to pH -- that is the whole
    point of shipping it rather than falling back to plain LogP."""
    mol = Chem.MolFromSmiles(_IBUPROFEN)

    assert logd_from_microspecies(mol, 2.0) != logd_from_microspecies(mol, 7.4)
