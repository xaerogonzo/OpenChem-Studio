"""The polarizability calculator's three methods, through the registry.

The module `chem/polarizability_miller.py` is checked against Miller's own
Table I in `tests/test_polarizability_miller.py`. This file is about the
other half: that the METHOD a user picks is the method that runs, and that
the method which ran is the method recorded.

**THE DANGEROUS FAILURE IS SILENT.** The combo says "Miller ahp", the
number is Jensen's, and every ordinary UI test stays green because a
plausible polarizability came back. So the two obligations are asserted
separately -- `test_the_three_methods_give_three_different_answers` proves
the NUMERICAL path changed, `test_the_method_that_ran_is_the_method_recorded`
proves the METADATA path did. A result that computed Miller while
recording Jensen passes either one alone.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.electronic_properties import (
    POLARIZABILITY_METHODS,
    compute_polarizability,
)
from openchem.domain.common import CacheState


def _value(smiles: str, method: str | None = None) -> float:
    parameters = {} if method is None else {"method": method}
    result = compute_polarizability(Chem.MolFromSmiles(smiles), "uuid", parameters)
    assert result.cache_state is not CacheState.FAILED, result.error
    line = result.matched[0]
    assert line.startswith("Molecular polarizability:"), line
    return float(line.split(":")[1].strip().split()[0])


def test_the_three_methods_give_three_different_answers():
    """CBr4, because it is where they genuinely separate.

    Measured across the three: benzene puts ahc and ahp 0.2% apart, which
    a two-decimal display rounds into agreement -- so a fixture chosen for
    familiarity would let "both Miller methods reach one implementation"
    pass. CBr4 puts them 16% apart. Same lesson as the assembly corpus
    that could not see a transposed matrix: a fixture is not big or small,
    it is degenerate or not with respect to a specific mutation.
    """
    jensen = _value("BrC(Br)(Br)Br", "Jensen (additive)")
    ahc = _value("BrC(Br)(Br)Br", "Miller ahc")
    ahp = _value("BrC(Br)(Br)Br", "Miller ahp")

    assert len({round(jensen, 2), round(ahc, 2), round(ahp, 2)}) == 3, (
        f"two methods gave the same displayed number: jensen={jensen:.2f} "
        f"ahc={ahc:.2f} ahp={ahp:.2f}"
    )
    # The setup assertion: the ahc/ahp gap is large here, so a collapse
    # into one implementation cannot hide inside display rounding.
    assert abs(ahc - ahp) / ahp > 0.10


def test_the_method_that_ran_is_the_method_recorded():
    """Provenance, separately from the number.

    There is no parameter-keyed result cache today -- checked -- so this is
    not a live bug; it is the constraint that has to hold before one can be
    added. A cache keyed on `(molecule, calculator_id)` alone would return
    the Jensen result under every method's label.
    """
    for label, expected in POLARIZABILITY_METHODS.items():
        result = compute_polarizability(
            Chem.MolFromSmiles("c1ccccc1"), "uuid", {"method": label}
        )
        assert result.provenance.method == expected, label
        assert result.provenance.parameters["method"] == expected, label


def test_the_default_is_jensen_and_naming_nothing_is_the_same_as_naming_it():
    """The pre-existing behaviour is the default, so adding the parameter
    cannot silently change what an existing project recomputes to."""
    assert _value("c1ccccc1") == pytest.approx(_value("c1ccccc1", "Jensen (additive)"))
    assert compute_polarizability(
        Chem.MolFromSmiles("c1ccccc1"), "uuid", {}
    ).provenance.method == "jensen"


def test_an_unknown_method_label_falls_back_and_says_which_ran():
    """A project saved by a future version must not be unopenable, and the
    recorded method is what stops the fallback being silent."""
    result = compute_polarizability(
        Chem.MolFromSmiles("c1ccccc1"), "uuid", {"method": "Miller ahq"}
    )
    assert result.cache_state is not CacheState.FAILED
    assert result.provenance.method == "jensen"


def test_millers_refusal_reaches_the_user_as_a_failed_result():
    """Table I covers H, C, N, O, S, P and four halogens. Boron has no row,
    and inventing one would give a plausible number for a molecule the
    method was never fitted to -- so the calculator must FAIL rather than
    fall back to Jensen, which would answer a question nobody asked."""
    result = compute_polarizability(
        Chem.MolFromSmiles("B(O)(O)O"), "uuid", {"method": "Miller ahc"}
    )
    assert result.cache_state is CacheState.FAILED
    assert "Miller" in (result.error or "")
    assert result.provenance.method == "miller_ahc"


def test_the_reported_basis_names_the_method_that_ran():
    """A number with no method beside it is the ambiguity this parameter
    creates; the basis line is what closes it."""
    for label, expected in POLARIZABILITY_METHODS.items():
        result = compute_polarizability(
            Chem.MolFromSmiles("c1ccccc1"), "uuid", {"method": label}
        )
        basis = " ".join(result.matched)
        needle = "Jensen" if expected == "jensen" else expected.split("_")[1]
        assert needle in basis, f"{label}: {basis!r} does not name the method"


def test_the_hybrid_assignment_is_reported_for_millers_methods():
    """Miller's answer depends on which row of Table I each atom got, and
    `CBR` versus `CTR` is this project's recorded +36% trap. Printing the
    assignment is what makes a disagreement traceable to a row rather than
    merely observed."""
    result = compute_polarizability(
        Chem.MolFromSmiles("c1ccc2ccccc2c1"), "uuid", {"method": "Miller ahc"}
    )
    assignment = next(line for line in result.matched if line.startswith("Hybrid assignment"))
    assert "CTR x8" in assignment and "CBR x2" in assignment, assignment

    jensen = compute_polarizability(
        Chem.MolFromSmiles("c1ccc2ccccc2c1"), "uuid", {"method": "Jensen (additive)"}
    )
    assert not any(line.startswith("Hybrid assignment") for line in jensen.matched), (
        "Jensen's scheme has no hybrid rows, so claiming an assignment would be a lie"
    )
