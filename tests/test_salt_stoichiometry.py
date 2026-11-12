"""Two-ion charge balance: integers only, no chemistry toolkit.

Contract: docs/SALT_COMPOSITION_DESIGN.md. The solver never sees a molecule.
"""

from pathlib import Path

import pytest

from openchem.domain.salt_stoichiometry import (
    KIND_ION,
    KIND_METAL_HYDROXIDE,
    KIND_MOLECULAR_NEUTRAL,
    MODE_C_LIMIT,
    ORIGIN_LADDER,
    ORIGIN_USER,
    BalanceRefusal,
    ChargedSpecies,
    IonizationRefusal,
    ModeAComposition,
    ModeARefusal,
    ModeASpecies,
    ModeCCandidate,
    TwoIonBalance,
    balance_two,
    choose_ionization,
    compose_mode_a,
    compose_supplied_ions,
    enumerate_mode_c,
    formula_unit_conserved,
)


def _species(identity: str, charge: int, kind: str, counts: dict[str, int]) -> ModeASpecies:
    return ModeASpecies(
        identity=identity,
        charge=charge,
        kind=kind,
        element_counts=tuple(sorted(counts.items())),
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


def test_naoh_plus_acetic_is_refused_as_hydroxide_neutralization() -> None:
    result = compose_mode_a(
        _species("NaOH", 0, KIND_METAL_HYDROXIDE, {"H": 1, "Na": 1, "O": 1}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("Na+", 1, KIND_ION, {"Na": 1}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "hydroxide_neutralization"


def test_ethylamine_and_acetic_acid_is_one_to_one() -> None:
    result = compose_mode_a(
        _species("EtNH2", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("EtNH3+", 1, KIND_ION, {"C": 2, "H": 8, "N": 1}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert result == ModeAComposition(
        cation_count=1, anion_count=1, charge_valid=True
    )


def test_ethylenediamine_and_two_acetic_acids_is_one_to_two() -> None:
    result = compose_mode_a(
        _species("en", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 8, "N": 2}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("enH2+2", 2, KIND_ION, {"C": 2, "H": 10, "N": 2}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert isinstance(result, ModeAComposition)
    assert result.cation_count == 1 and result.anion_count == 2
    assert result.charge_valid is True


def test_broken_hydrogen_count_is_not_a_composition() -> None:
    result = compose_mode_a(
        _species("EtNH2", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("wrong", 1, KIND_ION, {"C": 2, "H": 9, "N": 1}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "conservation_failed"


def test_sodium_and_acetate_as_given_ions_balance_one_to_one() -> None:
    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
    acetate = ModeASpecies("CC(=O)[O-]", -1, KIND_ION, (("C", 2), ("H", 3), ("O", 2)))
    result = compose_supplied_ions(sodium, acetate)
    assert isinstance(result, ModeAComposition)
    assert result.cation_count == 1
    assert result.anion_count == 1
    assert result.charge_valid is True


def test_a_neutral_passed_to_supplied_ions_is_refused() -> None:
    acetic = ModeASpecies("CC(=O)O", 0, KIND_MOLECULAR_NEUTRAL, (("C", 2), ("H", 4), ("O", 2)))
    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
    refused = compose_supplied_ions(sodium, acetic)
    assert isinstance(refused, ModeARefusal)
    assert refused.code == "missing_proton_source"


def test_neutral_base_plus_sulfate_without_a_proton_source_is_refused() -> None:
    result = compose_mode_a(
        _species("B", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
        _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
        _species("BH+", 1, KIND_ION, {"C": 2, "H": 8, "N": 1}),
        _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "missing_proton_source"


def test_one_structure_at_the_requested_state_is_accepted() -> None:
    assert choose_ionization(["CC(=O)[O-]"]) == "CC(=O)[O-]"


def test_a_net_charge_with_no_structure_is_refused() -> None:
    refused = choose_ionization([])
    assert refused.code == "net_charge_only"


def test_two_structures_at_the_same_charge_are_not_auto_picked() -> None:
    refused = choose_ionization(["CC(=O)[O-]", "[O-]C=O"])
    assert refused.code == "ambiguous_microspecies"
    assert isinstance(refused, IonizationRefusal)


def test_one_user_cation_and_anion_is_the_one_to_one_salt() -> None:
    result = enumerate_mode_c(
        (ModeCCandidate("[Na+]", 1, ORIGIN_USER),),
        (ModeCCandidate("CC(=O)[O-]", -1, ORIGIN_USER),),
    )
    assert result.generated == 1
    assert result.returned == 1
    assert result.omitted == 0
    hit = result.hits[0]
    assert hit.cation_count == 1
    assert hit.anion_count == 1
    assert hit.charge_valid is True


def test_the_same_mode_c_inputs_yield_the_same_order_and_counts() -> None:
    cations = tuple(ModeCCandidate(f"c{i}", 1, ORIGIN_USER) for i in range(3))
    anions = tuple(ModeCCandidate(f"a{i}", -1, ORIGIN_USER) for i in range(2))
    first = enumerate_mode_c(cations, anions)
    second = enumerate_mode_c(cations, anions)
    assert first.hits == second.hits
    assert (first.generated, first.returned, first.omitted) == (
        second.generated,
        second.returned,
        second.omitted,
    )


def test_mode_c_keeps_fifty_and_says_how_many_it_left_out() -> None:
    cations = tuple(ModeCCandidate(f"c{i:02d}", 1, ORIGIN_USER) for i in range(8))
    anions = tuple(ModeCCandidate(f"a{i:02d}", -1, ORIGIN_USER) for i in range(7))
    result = enumerate_mode_c(cations, anions)
    assert result.generated == 56
    assert result.returned == MODE_C_LIMIT
    assert result.omitted == 6
    assert len(result.hits) == MODE_C_LIMIT


def test_identical_species_and_ratio_are_kept_once() -> None:
    result = enumerate_mode_c(
        (ModeCCandidate("[Na+]", 1, ORIGIN_USER), ModeCCandidate("[Na+]", 1, ORIGIN_LADDER, 0)),
        (ModeCCandidate("[Cl-]", -1, ORIGIN_USER),),
    )
    assert result.generated == 1
    assert result.returned == 1


def test_same_sign_pairs_are_not_compositions() -> None:
    result = enumerate_mode_c(
        (ModeCCandidate("[Na+]", 1, ORIGIN_USER),),
        (ModeCCandidate("[K+]", 1, ORIGIN_USER),),
    )
    assert result.generated == 0
    assert result.returned == 0
    assert result.omitted == 0
    assert result.hits == ()


def test_user_states_come_before_ladder_states() -> None:
    result = enumerate_mode_c(
        (
            ModeCCandidate("zz-ladder", 1, ORIGIN_LADDER, 0),
            ModeCCandidate("aa-user", 1, ORIGIN_USER),
        ),
        (ModeCCandidate("[Cl-]", -1, ORIGIN_USER),),
    )
    assert [hit.cation_identity for hit in result.hits] == ["aa-user", "zz-ladder"]


def test_the_domain_module_does_not_import_lattice_energy() -> None:
    text = Path("src/openchem/domain/salt_stoichiometry.py").read_text(
        encoding="utf-8"
    )
    assert "lattice_energy" not in text
    assert "rdkit" not in text.lower()
