"""WP4 of docs/HYPERVALENT_COVERAGE_DESIGN.md: what the additive polarizability says about over-coordinated centres.

Decided from the CRC Handbook table (97th ed.), not from one molecule: of its entries the model can predict, three have a centre with five
or more neighbours (SF6 -21%, SeF6 -23%, PF5 -8%). The first two are far outside the stated error (about 2% on solvents, about 8% on the CRC set), so a
result for such a centre carries a warning with those figures; the percentages are held to the model's own output here. Ordinary sulfones,
sulfates and phosphates (mean absolute error about 8%, the stated figure) get nothing new.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.electronic_properties import (
    OVER_COORDINATED_MEASURED,
    OVER_COORDINATED_WARNING,
    UNMEASURED_HYPERVALENT_WARNING,
    compute_polarizability,
    molecular_polarizability,
)


def _lines(smiles: str) -> str:
    return " ".join(compute_polarizability(Chem.MolFromSmiles(smiles), "u").matched)


def test_the_quoted_percentages_are_the_models_own_errors():
    errors = {}
    for name, (smiles, experimental) in OVER_COORDINATED_MEASURED.items():
        predicted = molecular_polarizability(Chem.MolFromSmiles(smiles))
        errors[name] = round(100 * (experimental - predicted) / experimental)
    assert errors == {"SF6": 21, "SeF6": 23, "PF5": 8}, "the model or the table moved: update the warning and the design note"
    assert "21%, 23% and 8% low" in OVER_COORDINATED_WARNING


@pytest.mark.parametrize("smiles", [v[0] for v in OVER_COORDINATED_MEASURED.values()] + ["CS(F)(F)(F)(F)F", "FS(F)(F)(F)(F)c1ccccc1"])
def test_an_over_coordinated_centre_carries_the_measured_warning(smiles):
    assert OVER_COORDINATED_WARNING.strip() in _lines(smiles)


@pytest.mark.parametrize("smiles", ["F[Xe]F", "FI(F)(F)(F)F", "CC(=O)OI(OC(C)=O)c1ccccc1"])
def test_a_hypervalent_centre_with_no_measurement_is_called_unvalidated(smiles):
    result = compute_polarizability(Chem.MolFromSmiles(smiles), "u")
    text = " ".join(result.matched)
    if result.error:  # an element outside the table is a refusal, which is its own statement
        assert "No additive polarizability parameter" in result.error
    else:
        assert UNMEASURED_HYPERVALENT_WARNING.strip() in text


@pytest.mark.parametrize(
    "smiles",
    ["CS(C)(=O)=O", "COS(=O)(=O)OC", "COP(=O)(OC)OC", "O=S1(=O)CCCC1", "CS(C)=O", "[O-]Cl(=O)(=O)=O", "CCO", "c1ccccc1", "CCl", "Ic1ccccc1", "C[N+](C)(C)C"],
)
def test_ordinary_molecules_get_no_new_warning(smiles):
    text = _lines(smiles)
    assert "five or more neighbours" not in text and "hypervalent centre" not in text
