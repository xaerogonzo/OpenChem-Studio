"""BBB Score descriptors and stereo descriptors.

The BBB tests pin the three inputs that were checked against ChemAxon's
own worked sildenafil example, since those are what justify shipping the
descriptors at all -- and one test pins the ABSENCE of the composite
score, so restoring it stays a conscious decision rather than an
accident (same shape as the steric-effect-index guard in
test_phase26_calculators.py).
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.bbb_stereo import (
    bbb_descriptors,
    compute_bbb_descriptors,
    compute_stereo_descriptors,
    mwhbn,
    stereo_descriptors,
)
from openchem.domain.common import CacheState

# ChemAxon's own BBB Score documentation example.
SILDENAFIL = "CCCc1nn(C)c2c1nc([nH]c2=O)-c1cc(ccc1OCC)S(=O)(=O)N1CCN(C)CC1"


def test_bbb_inputs_reproduce_chemaxons_sildenafil_example():
    """Their page reports aromatic rings 3, heavy atoms 33, MWHBN 0.37.

    TPSA is deliberately NOT asserted against their 109.13: RDKit gives
    113.42, a real ~4% disagreement between two TPSA implementations. The
    gap is recorded in the module docstring rather than papered over with
    a loose tolerance that would hide a future regression.
    """
    mol = Chem.MolFromSmiles(SILDENAFIL)
    values = bbb_descriptors(mol)

    assert values["aromatic_rings"] == 3
    assert values["heavy_atoms"] == 33
    assert values["mwhbn"] == pytest.approx(0.37, abs=0.005)


def test_mwhbn_is_hydrogen_bond_count_over_root_molecular_weight():
    """The definition ChemAxon's docs never state, recovered from the
    worked example above. Ethanol: 1 donor + 1 acceptor over sqrt(46.07).
    """
    assert mwhbn(Chem.MolFromSmiles("CCO")) == pytest.approx(2 / 46.07**0.5, abs=1e-4)


def test_mwhbn_survives_a_molecule_with_no_weight():
    """An empty mol has MW 0, and dividing by its square root would raise
    rather than return anything useful."""
    assert mwhbn(Chem.MolFromSmiles("")) == 0.0


def test_bbb_composite_score_is_deliberately_not_computed():
    """Five unpublished weight functions against one worked total cannot
    be validated -- a reconstruction hitting 3.05 would prove nothing,
    since five free curves can be tuned to any single number."""
    result = compute_bbb_descriptors(Chem.MolFromSmiles(SILDENAFIL), "mol-1")
    joined = "\n".join(result.matched)

    assert "3.05" not in joined
    assert "NOT computed" in joined
    # The bands ARE published, so they are still reported.
    assert "4-6" in joined


def test_bbb_reports_pka_as_unavailable_without_a_configured_predictor():
    result = compute_bbb_descriptors(Chem.MolFromSmiles("CCO"), "mol-1", interpreter_path="")

    assert result.cache_state == CacheState.COMPLETED
    assert any("pKa (most basic): unavailable" in line for line in result.matched)
    # The other four still computed -- a missing pKa environment must not
    # take the whole result down with it.
    assert any("Heavy atoms: 3" in line for line in result.matched)


def test_bbb_honours_the_decimal_places_option():
    result = compute_bbb_descriptors(
        Chem.MolFromSmiles(SILDENAFIL), "mol-1", {"decimal_places": 4}
    )

    assert any("MWHBN: 0.3672" in line for line in result.matched)


# --- Stereo descriptors --------------------------------------------------


@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O", "R"),
        ("CC(C)Cc1ccc(cc1)[C@H](C)C(=O)O", "S"),
    ],
)
def test_stereo_descriptors_label_a_defined_centre(smiles, expected):
    """Both ibuprofen enantiomers, so the test proves the labeller really
    discriminates rather than always emitting the same letter."""
    elements = stereo_descriptors(Chem.MolFromSmiles(smiles))

    assert len(elements) == 1
    _index, kind, label = elements[0]
    assert kind == "tetrahedral"
    assert label == expected


def test_stereo_descriptors_flag_an_undefined_centre():
    """Same molecule drawn flat: the centre is real and perceivable, but
    the structure does not say which way it points. Reporting it as
    undefined is the useful answer; omitting it would hide a genuine gap
    in the drawn structure."""
    result = compute_stereo_descriptors(
        Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O"), "mol-1"
    )
    joined = "\n".join(result.matched)

    assert "undefined" in joined
    assert "1 stereo element(s), 1 undefined." in joined


def test_stereo_descriptors_label_double_bond_geometry():
    elements = stereo_descriptors(Chem.MolFromSmiles(r"C/C=C/C"))  # trans-2-butene

    assert len(elements) == 1
    _index, kind, label = elements[0]
    assert kind == "double bond"
    assert label == "E"


def test_stereo_descriptors_flag_an_undefined_double_bond():
    """The bond half of the same gap: 2-butene drawn without geometry has
    a real E/Z choice the structure does not make."""
    elements = stereo_descriptors(Chem.MolFromSmiles("CC=CC"))

    assert elements == [(1, "double bond", "undefined")]


def test_stereo_descriptors_say_so_when_there_is_nothing_to_report():
    result = compute_stereo_descriptors(Chem.MolFromSmiles("CCO"), "mol-1")

    assert result.matched == ["No stereo elements in this structure."]
    assert result.cache_state == CacheState.COMPLETED
