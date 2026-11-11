"""Two-ion charge balance: integers only, no chemistry toolkit.

Contract: docs/SALT_COMPOSITION_DESIGN.md. The solver never sees a molecule.
"""

from openchem.domain.salt_stoichiometry import (
    BalanceRefusal,
    ChargedSpecies,
    TwoIonBalance,
    balance_two,
)


def test_plus_one_and_minus_one_is_one_to_one() -> None:
    result = balance_two(
        ChargedSpecies(identity="cation", charge=1),
        ChargedSpecies(identity="anion", charge=-1),
    )
    assert result == TwoIonBalance(cation_count=1, anion_count=1)
    assert not isinstance(result, BalanceRefusal)
