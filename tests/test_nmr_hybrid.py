"""Per-atom merging of database and computed shift predictions.

These use synthetic spectra deliberately: the selection logic is
arithmetic over two numbers per atom, and making it depend on a real
ORCA run would mean it could only be tested where ORCA is installed. The
real run is still the gate for the FEATURE (see the phase plan) -- it is
just not what proves the merge picks the right candidate.
"""

from __future__ import annotations

import pytest

from openchem.chem.nmr_hybrid import (
    LOOKUP_EXPECTED_ERROR,
    Candidate,
    check_calibration,
    computed_candidates,
    fuse,
    lookup_candidates,
    trusted_values,
)
from openchem.chem.nmr_scaling import fit_scaling
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import NMRSpectrumResult


def _lookup(values: dict[int, float], qualities: dict[int, str]) -> NMRSpectrumResult:
    """A database result shaped exactly as `predict_spectrum` builds one."""
    return NMRSpectrumResult(
        spectrum_type="nmr_13c",
        name="C NMR (database)",
        units="ppm",
        method="hose_lookup",
        molecule_uuid="m",
        values=values,
        elements=dict.fromkeys(values, "C"),
        cache_state=CacheState.COMPLETED,
        provenance=Provenance(
            created_by="core",
            method="hose_lookup",
            parameters={
                "per_atom": {
                    str(index): {"quality": quality, "matches": 5, "spheres": 4}
                    for index, quality in qualities.items()
                }
            },
        ),
    )


class _Factors:
    """Stands in for ScalingFactors -- only the fields the hybrid reads."""

    def __init__(self, residual_rms):
        self.residual_rms = residual_rms
        self.slope = -1.05
        self.r_squared = 0.998
        self.sample_count = 7


def test_the_lookups_good_atoms_beat_a_calculation_of_average_accuracy():
    result = _lookup({0: 128.0}, {0: "good"})
    merged = fuse(
        {0: [lookup_candidates(result)[0], *computed_candidates({0: 130.0}, _Factors(1.5)).values()]},
        {0: "C"},
        "m",
    )

    assert merged.values == {0: 128.0}
    assert merged.provenance.parameters["per_atom"]["0"]["source"] == "trusted lookup"


def test_the_calculation_beats_the_lookups_rough_atoms():
    """The whole point of the phase: 9.93 ppm is worse than a good
    calibration, and an atom nobody has measured is where the user
    actually needs an answer."""
    result = _lookup({0: 40.0}, {0: "rough"})
    merged = fuse(
        {0: [lookup_candidates(result)[0], *computed_candidates({0: 46.0}, _Factors(1.5)).values()]},
        {0: "C"},
        "m",
    )

    assert merged.values == {0: 46.0}
    detail = merged.provenance.parameters["per_atom"]["0"]
    assert detail["source"] == "ORCA (scaled)"
    assert detail["expected_error"] == 1.5
    assert detail["disagreement_ppm"] == 6.0


def test_an_uncalibrated_calculation_never_wins():
    """`residual_rms` is None when there is no calibration to measure it
    from. Unknown must lose to measured, even to the worst measured
    band -- otherwise a user with no calibration silently gets the
    ab initio number everywhere."""
    result = _lookup({0: 40.0}, {0: "rough"})
    merged = fuse(
        {0: [lookup_candidates(result)[0], *computed_candidates({0: 46.0}, _Factors(None)).values()]},
        {0: "C"},
        "m",
    )

    assert merged.values == {0: 40.0}
    assert merged.provenance.parameters["per_atom"]["0"]["source"] == "trusted lookup"


def test_an_atom_only_one_method_answered_for_is_still_reported():
    merged = fuse({7: [Candidate(value=12.0, method="ORCA (scaled)")]}, {7: "C"}, "m")

    assert merged.values == {7: 12.0}
    assert "only ORCA (scaled) had a value" in (
        merged.provenance.parameters["per_atom"]["7"]["selection_reason"]
    )


def test_the_merge_summary_counts_each_source():
    result = _lookup({0: 128.0, 1: 40.0}, {0: "good", 1: "rough"})
    lookups = lookup_candidates(result)
    computed = computed_candidates({0: 130.0, 1: 46.0}, _Factors(1.5))
    merged = fuse(
        {index: [lookups[index], computed[index]] for index in (0, 1)},
        {0: "C", 1: "C"},
        "m",
    )

    assert merged.provenance.parameters["sources"] == {"trusted lookup": 1, "ORCA (scaled)": 1}
    # (1.17 + 1.5) / 2
    assert merged.provenance.parameters["expected_average_error"] == pytest.approx(1.335)


def test_a_calculation_on_a_different_scale_is_refused_not_spliced():
    """The failure this gate exists for. A systematic offset means the
    two sets of numbers are not the same quantity, and merging them
    produces a step a chemist would read as real."""
    trusted = {0: 128.0, 1: 20.0, 2: 60.0, 3: 100.0}
    computed = {index: value + 9.0 for index, value in trusted.items()}
    check = check_calibration(trusted, computed, "C")

    assert check is not None
    assert not check.passed
    assert check.mean_offset == pytest.approx(9.0)
    assert check.max_deviation == pytest.approx(9.0)

    merged = fuse({}, {}, "m", calibration=check)
    assert merged.cache_state is CacheState.FAILED
    assert "+9.00 ppm" in merged.error
    assert merged.values == {}


def test_a_well_calibrated_calculation_passes_and_reports_its_worst_atom():
    """One badly placed atom hides inside a good RMS -- which is why the
    maximum is reported next to it rather than instead of it."""
    trusted = {0: 128.0, 1: 20.0, 2: 60.0, 3: 100.0}
    computed = {0: 128.3, 1: 19.8, 2: 60.1, 3: 103.4}
    check = check_calibration(trusted, computed, "C")

    assert check.passed
    assert check.max_deviation == pytest.approx(3.4)
    assert check.rms > abs(check.mean_offset)


def test_calibration_is_measured_only_against_the_lookups_good_atoms():
    result = _lookup({0: 128.0, 1: 40.0, 2: 60.0}, {0: "good", 1: "rough", 2: "medium"})

    assert trusted_values(result) == {0: 128.0}


def test_nothing_shared_means_no_calibration_rather_than_a_pass():
    """Returning a passing check here would claim the calculation had
    been verified when nothing was compared."""
    assert check_calibration({0: 128.0}, {5: 130.0}, "C") is None


def test_the_calibration_fit_reports_its_residual_in_ppm():
    """The number the ORCA candidate's expected error comes from. A fit
    through points that do not sit exactly on a line has a residual, and
    R^2 alone cannot express it in ppm."""
    points = [(200.0, 0.0), (150.0, 50.0), (100.0, 101.0), (50.0, 149.0)]
    factors = fit_scaling(points)

    assert factors.residual_rms == pytest.approx(0.6708, abs=1e-3)
    assert factors.r_squared > 0.999


def test_a_perfectly_linear_calibration_has_no_residual():
    factors = fit_scaling([(200.0, 0.0), (150.0, 50.0), (100.0, 100.0), (50.0, 150.0)])

    assert factors.residual_rms == pytest.approx(0.0, abs=1e-9)


def test_the_lookups_expected_errors_are_the_recorded_held_out_numbers():
    """A guard, not a tautology: these three came from a held-out run of
    24,046 carbons recorded in `nmr_database.py`. Changing them changes
    which method wins atoms, so it should not be possible to do quietly.
    """
    assert LOOKUP_EXPECTED_ERROR == {"good": 1.17, "medium": 3.38, "rough": 9.93}


def test_the_tolerance_widens_with_the_calculations_own_stated_error():
    """Two imperfect methods disagree even when both work. A fixed limit
    cannot express that; adding the two errors in quadrature can, and it
    is why the same 2 ppm offset is evidence of a scale problem from a
    tight calibration and not from a loose one."""
    trusted = {0: 100.0, 1: 50.0, 2: 20.0}
    computed = {index: value + 2.0 for index, value in trusted.items()}

    assert not check_calibration(trusted, computed, "C").passed
    # sqrt(1.17^2 + 2.34^2) = 2.62, the real B3LYP/def2-SVP residual.
    assert check_calibration(trusted, computed, "C", 2.34).passed


def test_the_floor_stops_a_tight_calibration_producing_an_absurd_limit():
    trusted = {0: 100.0, 1: 50.0}
    computed = {0: 101.4, 1: 51.4}

    assert check_calibration(trusted, computed, "C", 0.0).passed


def test_only_carbon_is_merged():
    """The lookup's per-band MAE was measured on 24,046 carbons. There is
    no equivalent number for protons, and 1.17 ppm would span most of a
    1H spectrum -- so protons are not selected on at all rather than
    selected on a fabricated figure."""
    from openchem.chem.nmr_hybrid import MERGEABLE_ELEMENTS

    assert MERGEABLE_ELEMENTS == ("C",)


def test_caffeine_the_real_measured_case():
    """The values here are from a real ORCA 6.1.1 run at B3LYP/def2-SVP
    against literature 13C shifts, recorded in this module's docstring.
    Kept as a fixture rather than a live run so the demonstrated
    behaviour is locked in on machines with no ORCA.

    Caffeine's N7-methyl is the point: `rough`, and the lookup misses it
    by 29 ppm. Everything else is `good` and must be left alone.
    """
    literature = {0: 33.6, 2: 141.5, 4: 148.7, 5: 107.6, 6: 155.4, 9: 27.9, 10: 151.7, 13: 29.7}
    looked_up = {0: 62.58, 2: 144.15, 4: 148.97, 5: 107.73, 6: 155.11, 9: 28.58, 10: 150.24, 13: 29.50}
    orca = {0: 36.11, 2: 139.16, 4: 147.71, 5: 108.28, 6: 154.84, 9: 29.95, 10: 152.77, 13: 31.28}
    qualities = {index: ("rough" if index == 0 else "good") for index in literature}
    residual_rms = 2.339

    lookup = _lookup(looked_up, qualities)
    check = check_calibration(trusted_values(lookup), orca, "C", residual_rms)
    assert check.passed, check.reason

    lookups = lookup_candidates(lookup)
    computed = computed_candidates(orca, _Factors(residual_rms))
    merged = fuse(
        {i: [lookups[i], computed[i]] for i in literature},
        dict.fromkeys(literature, "C"),
        "caffeine",
        "C",
        check,
    )

    sources = merged.provenance.parameters["per_atom"]
    assert sources["0"]["source"] == "ORCA (scaled)"
    assert all(sources[str(i)]["source"] == "trusted lookup" for i in literature if i != 0)

    def mae(values):
        return sum(abs(values[i] - lit) for i, lit in literature.items()) / len(literature)

    # The claim this phase rests on: better than BOTH inputs, not just one.
    assert mae(merged.values) == pytest.approx(1.02, abs=0.01)
    assert mae(merged.values) < mae(looked_up)  # 4.33
    assert mae(merged.values) < mae(orca)  # 1.47


def test_the_measured_aspirin_case_is_refused():
    """The other half of the real run: on the same install, aspirin's
    calculation sat +4.10 ppm from trusted values, and scaled ORCA really
    was worse there than the lookup (3.75 vs 1.58 ppm MAE). The gate has
    to catch that, or the hybrid degrades spectra it should leave alone.
    """
    trusted = {
        0: 20.76, 1: 169.68, 4: 150.99, 5: 122.36, 6: 130.58,
        7: 120.89, 8: 131.79, 9: 123.01, 10: 168.77,
    }
    computed = {
        0: 25.16, 1: 176.30, 4: 156.67, 5: 127.17, 6: 135.65,
        7: 128.20, 8: 137.68, 9: 123.86, 10: 165.03,
    }

    check = check_calibration(trusted, computed, "C", 2.339)

    assert not check.passed
    assert check.compared == 9
    assert check.mean_offset == pytest.approx(4.10, abs=0.01)
    assert fuse({}, {}, "aspirin", "C", check).cache_state is CacheState.FAILED


def test_quinine_the_case_where_the_gate_costs_a_real_gain():
    """Real ORCA 6.1.1 at B3LYP/def2-SVP against Moreland's assigned CDCl3
    table. Recorded as a fixture so the finding cannot quietly regress:
    the gate refuses this merge, and the merge would have been much
    better than the lookup.

    Kept as a FAILING-gate test rather than being 'fixed' by loosening
    the threshold, because the miscalibration is structural (the offset
    is measured on atoms the lookup then wins) and two data points are
    not enough to justify a redesign. See the module docstring.
    """
    lit = {
        0: 55.44, 2: 157.44, 3: 118.30, 4: 130.89, 5: 143.67, 7: 147.01, 8: 121.09,
        9: 148.33, 10: 126.43, 11: 101.40, 12: 71.51, 14: 59.85, 15: 21.44, 16: 27.71,
        17: 27.46, 18: 43.00, 20: 56.86, 21: 39.76, 22: 141.66, 23: 114.08,
    }
    looked_up = {
        0: 55.61, 2: 154.30, 3: 112.06, 4: 121.93, 5: 144.13, 7: 131.85, 8: 107.24,
        9: 135.55, 10: 113.80, 11: 103.44, 12: 71.07, 14: 60.06, 15: 41.42, 16: 43.07,
        17: 40.58, 18: 56.32, 20: 54.82, 21: 56.17, 22: 139.52, 23: 114.84,
    }
    orca = {
        0: 55.77, 2: 157.28, 3: 113.64, 4: 135.56, 5: 141.12, 7: 149.84, 8: 122.88,
        9: 151.84, 10: 127.63, 11: 113.92, 12: 76.13, 14: 68.19, 15: 30.09, 16: 29.56,
        17: 34.77, 18: 46.91, 20: 64.22, 21: 43.86, 22: 146.30, 23: 113.09,
    }
    good = {0, 2, 5, 12, 14, 20, 23}
    medium = {11}
    qualities = {i: ("good" if i in good else "medium" if i in medium else "rough") for i in lit}
    residual_rms = 2.339

    lookup = _lookup(looked_up, qualities)
    check = check_calibration(trusted_values(lookup), orca, "C", residual_rms)

    # The refusal itself, and how narrow it is.
    assert not check.passed
    assert check.compared == len(good)
    assert check.mean_offset == pytest.approx(3.00, abs=0.02)
    # Scatter, not a systematic shift -- the RMS is far larger than the mean.
    assert check.rms > 1.7 * abs(check.mean_offset)
    assert fuse({}, {}, "quinine", "C", check).cache_state is CacheState.FAILED

    lookups = lookup_candidates(lookup)
    computed = computed_candidates(orca, _Factors(residual_rms))
    would_be = fuse(
        {i: [lookups[i], computed[i]] for i in lit},
        dict.fromkeys(lit, "C"),
        "quinine",
        "C",
        None,
    )

    def mae(values, keys):
        return sum(abs(values[i] - lit[i]) for i in keys) / len(keys)

    rough = [i for i in lit if qualities[i] == "rough"]
    assert mae(looked_up, rough) == pytest.approx(12.50, abs=0.05)
    assert mae(would_be.values, rough) == pytest.approx(4.09, abs=0.05)
    assert mae(would_be.values, lit) == pytest.approx(3.44, abs=0.05)
    assert mae(would_be.values, lit) < mae(looked_up, lit)  # 7.96
