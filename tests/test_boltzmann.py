from __future__ import annotations

import math

import pytest

from openchem.chem.boltzmann import (
    STANDARD_TEMPERATURE_K,
    boltzmann_average_spectrum,
    boltzmann_weights,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import NMRSpectrumResult

# 1 kcal/mol in Hartree -- the natural unit to think about conformer gaps in.
KCAL_PER_MOL = 1.0 / 627.5094740631


def _spectrum(values, *, couplings=None, provenance=None) -> NMRSpectrumResult:
    return NMRSpectrumResult(
        spectrum_type="nmr_raw_shielding",
        name="NMR Isotropic Shielding",
        units="ppm (isotropic shielding)",
        method="orca",
        molecule_uuid="mol-1",
        values=values,
        elements={index: "H" for index in values},
        couplings=couplings,
        provenance=provenance,
        cache_state=CacheState.COMPLETED,
    )


def test_degenerate_energies_split_evenly():
    assert boltzmann_weights([-100.0, -100.0, -100.0]) == pytest.approx([1 / 3, 1 / 3, 1 / 3])


def test_weights_sum_to_one():
    weights = boltzmann_weights([-100.0, -99.998, -99.995])
    assert sum(weights) == pytest.approx(1.0)


def test_lower_energy_conformer_gets_more_population():
    lower, higher = boltzmann_weights([-100.002, -100.0])
    assert lower > higher


def test_one_kcal_gap_matches_the_textbook_population_ratio():
    """RT at 298.15 K is 0.593 kcal/mol, so a 1 kcal/mol gap should leave
    the higher conformer at exp(-1/0.593) ~= 18.5% of the lower one's
    population. Pins the unit conversion, which is the one place this could
    be silently wrong by orders of magnitude and still look plausible."""
    lower, higher = boltzmann_weights([-100.0, -100.0 + KCAL_PER_MOL])

    assert higher / lower == pytest.approx(math.exp(-1.0 / 0.5925), rel=1e-3)


def test_a_three_kcal_gap_is_effectively_unpopulated():
    lower, higher = boltzmann_weights([-100.0, -100.0 + 3 * KCAL_PER_MOL])
    assert higher < 0.01
    assert lower > 0.99


def test_higher_temperature_flattens_the_distribution():
    cold = boltzmann_weights([-100.0, -100.0 + KCAL_PER_MOL], temperature_k=200.0)
    hot = boltzmann_weights([-100.0, -100.0 + KCAL_PER_MOL], temperature_k=500.0)
    assert hot[1] > cold[1]


def test_empty_energies_give_no_weights():
    assert boltzmann_weights([]) == []


def test_averaging_a_single_spectrum_returns_it_unchanged():
    """Makes the one-conformer case need no special handling at the call
    site -- request_boltzmann_nmr with one conformer is just a normal run."""
    only = _spectrum({0: 30.0})

    assert boltzmann_average_spectrum([only], [-100.0]) is only


def test_equal_energies_give_the_arithmetic_mean():
    averaged = boltzmann_average_spectrum(
        [_spectrum({0: 30.0, 1: 10.0}), _spectrum({0: 20.0, 1: 14.0})], [-100.0, -100.0]
    )

    assert averaged.values == pytest.approx({0: 25.0, 1: 12.0})


def test_the_dominant_conformer_pulls_the_average_toward_itself():
    averaged = boltzmann_average_spectrum(
        [_spectrum({0: 30.0}), _spectrum({0: 10.0})], [-100.0, -100.0 + 3 * KCAL_PER_MOL]
    )

    # Nearly all population sits on the -100.0 conformer at a 3 kcal/mol gap.
    assert averaged.values[0] == pytest.approx(30.0, abs=0.2)


def test_atoms_missing_from_one_conformer_are_dropped_not_partially_averaged():
    """Averaging an atom over a subset of conformers would weight it
    differently from its neighbours -- silently, and only for that atom."""
    averaged = boltzmann_average_spectrum(
        [_spectrum({0: 30.0, 1: 10.0}), _spectrum({0: 20.0})], [-100.0, -100.0]
    )

    assert set(averaged.values) == {0}
    assert set(averaged.elements) == {0}


def test_couplings_are_averaged_alongside_shifts():
    averaged = boltzmann_average_spectrum(
        [
            _spectrum({0: 30.0, 1: 10.0}, couplings={(0, 1): 8.0}),
            _spectrum({0: 30.0, 1: 10.0}, couplings={(0, 1): 4.0}),
        ],
        [-100.0, -100.0],
    )

    assert averaged.couplings == pytest.approx({(0, 1): 6.0})


def test_couplings_stay_none_when_any_conformer_lacks_them():
    averaged = boltzmann_average_spectrum(
        [
            _spectrum({0: 30.0}, couplings={(0, 1): 8.0}),
            _spectrum({0: 30.0}, couplings=None),
        ],
        [-100.0, -100.0],
    )

    assert averaged.couplings is None


def test_weights_are_recorded_in_provenance():
    """A 0.99/0.01 average is really just the lowest-energy conformer, and a
    reader should be able to see that rather than infer it."""
    averaged = boltzmann_average_spectrum(
        [
            _spectrum({0: 30.0}, provenance=Provenance(created_by="core", method="orca", parameters={})),
            _spectrum({0: 10.0}, provenance=Provenance(created_by="core", method="orca", parameters={})),
        ],
        [-100.0, -100.0 + 3 * KCAL_PER_MOL],
    )

    parameters = averaged.provenance.parameters
    assert parameters["boltzmann_conformers"] == 2
    assert parameters["boltzmann_temperature_k"] == STANDARD_TEMPERATURE_K
    assert sum(parameters["boltzmann_weights"]) == pytest.approx(1.0, abs=1e-3)


def test_mismatched_spectrum_and_energy_counts_raise():
    with pytest.raises(ValueError, match="every conformer needs exactly one of each"):
        boltzmann_average_spectrum([_spectrum({0: 30.0}), _spectrum({0: 10.0})], [-100.0])


def test_averaging_nothing_raises():
    with pytest.raises(ValueError, match="empty list"):
        boltzmann_average_spectrum([], [])
