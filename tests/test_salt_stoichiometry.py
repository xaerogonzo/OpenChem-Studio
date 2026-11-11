"""Two-ion charge balance: integers only, no chemistry toolkit.

Contract: docs/SALT_COMPOSITION_DESIGN.md. The solver never sees a molecule.
"""

from pathlib import Path

import pytest

from openchem.domain.salt_stoichiometry import (
    BalanceRefusal,
    ChargedSpecies,
    TwoIonBalance,
    balance_two,
    formula_unit_conserved,
)


def test_plus_one_and_minus_one_is_one_to_one() -> None:
    result = balance_two(
        ChargedSpecies(identity="cation", charge=1),
        ChargedSpecies(identity="anion", charge=-1),
    )
    assert result == TwoIonBalance(cation_count=1, anion_count=1)
    assert not isinstance(result, BalanceRefusal)


@pytest.mark.parametrize(
    ("z_plus", "z_minus", "n_c", "n_a"),
    [
        (1, -2, 2, 1),
        (2, -1, 1, 2),
        (2, -2, 1, 1),
        (3, -2, 2, 3),
        (4, -2, 1, 2),
        (6, -9, 3, 2),
    ],
)
def test_the_reduced_ratio_follows_the_gcd(
    z_plus: int, z_minus: int, n_c: int, n_a: int
) -> None:
    result = balance_two(
        ChargedSpecies("c", z_plus),
        ChargedSpecies("a", z_minus),
    )
    assert result == TwoIonBalance(cation_count=n_c, anion_count=n_a)
    assert n_c * z_plus + n_a * z_minus == 0


def test_identity_is_ignored_by_the_counts() -> None:
    a = balance_two(ChargedSpecies("NH4+", 1), ChargedSpecies("Cl-", -1))
    b = balance_two(ChargedSpecies("Na+", 1), ChargedSpecies("acetate", -1))
    assert a == b == TwoIonBalance(cation_count=1, anion_count=1)


def test_a_zero_charge_is_refused() -> None:
    result = balance_two(ChargedSpecies("c", 0), ChargedSpecies("a", -1))
    assert isinstance(result, BalanceRefusal)
    assert result.code == "not_opposite_signs"


def test_same_sign_charges_are_refused() -> None:
    result = balance_two(ChargedSpecies("c", 1), ChargedSpecies("a", 1))
    assert isinstance(result, BalanceRefusal)
    assert result.code == "not_opposite_signs"


def test_roles_swapped_are_refused() -> None:
    """The cation argument must actually be positive."""
    result = balance_two(ChargedSpecies("c", -1), ChargedSpecies("a", 1))
    assert isinstance(result, BalanceRefusal)


def test_successful_counts_are_positive() -> None:
    result = balance_two(ChargedSpecies("c", 3), ChargedSpecies("a", -2))
    assert isinstance(result, TwoIonBalance)
    assert result.cation_count > 0 and result.anion_count > 0


def test_one_base_and_two_acids_match_the_dication_formula_unit() -> None:
    # B + 2 HA → BH2^2+ + 2 A−  (ethylenediamine + 2 acetic, as counts)
    base = {"C": 2, "H": 8, "N": 2}
    acid = {"C": 2, "H": 4, "O": 2}
    cation = {"C": 2, "H": 10, "N": 2}
    anion = {"C": 2, "H": 3, "O": 2}
    assert formula_unit_conserved(
        [(base, 1), (acid, 2)],
        [(cation, 1), (anion, 2)],
    )


def test_a_one_to_one_check_of_the_base_against_the_dication_is_the_wrong_test() -> None:
    base = {"C": 2, "H": 8, "N": 2}
    cation = {"C": 2, "H": 10, "N": 2}
    assert not formula_unit_conserved([(base, 1)], [(cation, 1)])


def test_the_domain_module_does_not_import_lattice_energy() -> None:
    text = Path("src/openchem/domain/salt_stoichiometry.py").read_text(
        encoding="utf-8"
    )
    assert "lattice_energy" not in text
    assert "rdkit" not in text.lower()
