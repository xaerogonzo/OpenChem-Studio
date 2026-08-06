"""Conceptual-DFT descriptors, and the one place Koopmans gets it wrong.

The inputs in `MEASURED` are REAL, from ORCA 6.1.1 B3LYP/def2-SVP runs on
this machine -- geometries optimized by ORCA, then vertical cation and
anion single points at the optimized neutral geometry. They are pinned
here so the arithmetic and the orderings can be tested without ORCA
installed, which CI does not have.

The load-bearing test in this file is
`test_koopmans_inverts_ammonia_against_phosphine`. It asserts a KNOWN
FAILURE on purpose, the way `test_qt_object_disposal.py` asserts the
PySide6 leak it works around: if a future method or basis stops inverting
that pair, this test fails and the caveat attached to every Koopmans
number can come off.
"""

from __future__ import annotations

import pytest

from openchem.chem.conceptual_dft import (
    ConceptualDFT,
    DescriptorMethod,
    descriptors,
    from_delta_scf,
    from_frontier_energies,
)

#: name -> (E_HOMO eV, E_LUMO eV, E_neutral Eh, E_cation Eh, E_anion Eh)
#: Measured 2026-08-06, ORCA 6.1.1, B3LYP/def2-SVP, ions vertical at the
#: optimized neutral geometry.
MEASURED = {
    "water": (-7.8408, 1.2983, -76.321269385381, -75.869836483374, -76.180683957684),
    "hydrogen_sulfide": (-6.804, 0.9947, -399.214088725337, -398.83907460465, -399.079655368087),
    "ammonia": (-6.8199, 1.4957, -56.473094522647, -56.081151196579, -56.335415183071),
    "phosphine": (-7.4347, 1.1114, -342.986931746376, -342.602149992389, -342.855807424701),
}


def koopmans(name: str) -> ConceptualDFT:
    homo, lumo, *_ = MEASURED[name]
    return from_frontier_energies(homo, lumo)


def delta_scf(name: str) -> ConceptualDFT:
    _homo, _lumo, neutral, cation, anion = MEASURED[name]
    return from_delta_scf(neutral, cation, anion)


# --- the arithmetic ---------------------------------------------------------


def test_the_standard_relations_hold():
    """Hand-checked from I = 10, A = 2:

        chi = 6, mu = -6, eta = 4, S = 0.25, omega = 36/8 = 4.5
    """
    r = descriptors(10.0, 2.0, DescriptorMethod.KOOPMANS)
    assert r.electronegativity == pytest.approx(6.0)
    assert r.chemical_potential == pytest.approx(-6.0)
    assert r.hardness == pytest.approx(4.0)
    assert r.softness == pytest.approx(0.25)
    assert r.electrophilicity == pytest.approx(4.5)


def test_softness_is_the_reciprocal_of_hardness_not_half_of_it():
    """The convention matters downstream: Yang and Parr's local softness
    `s = S * f` is defined against `S = 1/eta`. Some literature uses
    `1/(2 eta)`, so a value quoted from elsewhere may differ by exactly two
    and not be wrong."""
    r = descriptors(10.0, 2.0, DescriptorMethod.KOOPMANS)
    assert r.softness == pytest.approx(1.0 / r.hardness)


def test_chemical_potential_is_minus_electronegativity():
    r = descriptors(9.0, -1.0, DescriptorMethod.KOOPMANS)
    assert r.chemical_potential == pytest.approx(-r.electronegativity)


def test_koopmans_reads_the_signs_off_the_orbital_energies():
    """I = -E(HOMO) and A = -E(LUMO). Water's HOMO sits at -7.8408 eV, so
    its ionization potential is +7.8408 eV; its LUMO is BOUND-looking at
    +1.2983 eV, giving a NEGATIVE electron affinity, which is correct for
    water and is the root of the trouble below."""
    r = koopmans("water")
    assert r.ionization_potential == pytest.approx(7.8408)
    assert r.electron_affinity == pytest.approx(-1.2983)
    assert r.method is DescriptorMethod.KOOPMANS


def test_delta_scf_converts_hartree_to_electron_volts():
    """I = E(cation) - E(neutral). For water that is
    (-75.869836 - -76.321269) Eh = 0.451433 Eh = 12.284 eV."""
    r = delta_scf("water")
    assert r.ionization_potential == pytest.approx(12.284, abs=0.01)
    assert r.method is DescriptorMethod.DELTA_SCF


# --- the orderings, which are the actual scientific claim -------------------


def test_both_methods_get_the_water_hydrogen_sulfide_pair_right():
    """Oxygen hard, sulfur soft -- the pair every HSAB discussion opens
    with. Both methods reproduce it, which is why the ammonia/phosphine
    failure below was a surprise rather than an expected weakness."""
    for method in (koopmans, delta_scf):
        assert method("water").hardness > method("hydrogen_sulfide").hardness


def test_delta_scf_gets_the_ammonia_phosphine_pair_right():
    """Nitrogen hard, phosphorus soft. This is the ordering behind most of
    the hard/soft donor reasoning in coordination chemistry."""
    assert delta_scf("ammonia").hardness > delta_scf("phosphine").hardness


def test_koopmans_inverts_ammonia_against_phosphine():
    """A KNOWN FAILURE, asserted on purpose so it cannot be forgotten.

    Koopmans/B3LYP makes phosphine the harder of the two. Every molecule
    here has a negative electron affinity, so its "LUMO" is an unbound
    state whose energy belongs to the basis set rather than the molecule;
    Koopmans reads that number straight out, and it does not preserve the
    ordering.

    If a future method stops inverting this pair, this test fails and the
    caveat attached to every Koopmans number can come off.
    """
    assert koopmans("ammonia").hardness < koopmans("phosphine").hardness


def test_delta_scf_ionization_potentials_are_the_believable_ones():
    """Not a comparison against a literature table -- Pearson's tabulated
    values are paywalled (doi:10.1021/ic00277a030) and nothing here quotes
    them as fact. This pins the measured GAP between the two methods,
    which is large and one-directional: delta-SCF puts every ionization
    potential 3-4.5 eV above Koopmans, in the direction of experiment.
    """
    for name in MEASURED:
        gap = delta_scf(name).ionization_potential - koopmans(name).ionization_potential
        assert 3.0 < gap < 4.5, name


# --- what travels with the numbers -----------------------------------------


def test_every_koopmans_result_carries_the_inversion_warning():
    caveat = " ".join(koopmans("water").caveats)
    assert "ammonia" in caveat and "phosphine" in caveat


def test_delta_scf_admits_the_electron_affinity_is_still_weak():
    """Reproducing both pairs is not the same as being right about A. Every
    anion here is unbound in a basis with no diffuse functions."""
    caveat = " ".join(delta_scf("water").caveats)
    assert "diffuse" in caveat


def test_the_method_is_recorded_rather_than_left_to_be_inferred():
    assert koopmans("water").method is DescriptorMethod.KOOPMANS
    assert delta_scf("water").method is DescriptorMethod.DELTA_SCF


# --- refusals ---------------------------------------------------------------


def test_a_non_positive_hardness_is_refused_rather_than_divided_by():
    """A LUMO below the HOMO means the job did not converge to the state
    intended. `S = 1/eta` would divide by zero or return a confident
    negative, so there is no number at all."""
    r = from_frontier_energies(1.0, -5.0)
    assert r.refused
    assert not r
    assert r.softness == 0.0
    assert "non-positive" in r.reason


def test_missing_frontier_energies_are_refused():
    r = from_frontier_energies(None, None)
    assert r.refused
    assert "no orbital energy table" in r.reason


@pytest.mark.parametrize(
    ("label", "neutral", "cation", "anion", "named"),
    [
        ("no neutral", None, -1.0, -1.0, "neutral"),
        ("no cation", -1.0, None, -1.0, "cation"),
        ("no anion", -1.0, -1.0, None, "anion"),
    ],
)
def test_delta_scf_names_which_of_the_three_jobs_is_missing(
    label, neutral, cation, anion, named
):
    """Three separate runs, so "it failed" is not a useful message -- which
    one failed is what tells you what to re-run."""
    r = from_delta_scf(neutral, cation, anion)
    assert r.refused
    assert named in r.reason, label


# ---------------------------------------------------------------------------
# Against the primary source.
#
# Pearson, "Absolute electronegativity and hardness: application to
# inorganic chemistry", Inorg. Chem. 1988, 27, 734
# (doi:10.1021/ic00277a030), Table II "Experimental Parameters for
# Molecules (eV)". Read from the paper, not quoted from memory -- an
# earlier version of this file said these were paywalled and pinned only
# orderings.
# ---------------------------------------------------------------------------

#: molecule -> (I, A, chi, eta) in eV, verbatim from Pearson's Table II.
PEARSON_EXPERIMENTAL = {
    "water": (12.6, -6.4, 3.1, 9.5),
    "hydrogen_sulfide": (10.5, -2.1, 4.2, 6.2),
    "ammonia": (10.7, -5.6, 2.6, 8.2),
    "phosphine": (10.0, -1.9, 4.1, 6.0),
}


@pytest.mark.parametrize("name", list(MEASURED))
def test_delta_scf_ionization_potentials_match_experiment(name):
    """Within 0.5 eV on every one. This is the half of delta-SCF that is
    genuinely good, and the reason it is the recommended path."""
    expected = PEARSON_EXPERIMENTAL[name][0]
    assert delta_scf(name).ionization_potential == pytest.approx(expected, abs=0.5), name


@pytest.mark.parametrize("name", list(MEASURED))
def test_koopmans_ionization_potentials_do_not(name):
    """The near-miss that gives the test above its meaning. Koopmans is
    off by 3-4.5 eV on the same molecules, always too small."""
    expected = PEARSON_EXPERIMENTAL[name][0]
    assert koopmans(name).ionization_potential < expected - 2.0, name


def test_delta_scf_hardness_is_within_about_one_electron_volt():
    errors = [
        abs(delta_scf(name).hardness - PEARSON_EXPERIMENTAL[name][3])
        for name in MEASURED
    ]
    assert sum(errors) / len(errors) < 1.5


def test_koopmans_hardness_is_far_too_small_on_every_molecule():
    """Not a near miss. Koopmans returns 48-71% of the experimental
    hardness -- it halves water's -- and the caveat riding on every
    Koopmans descriptor exists because of this."""
    for name in MEASURED:
        ratio = koopmans(name).hardness / PEARSON_EXPERIMENTAL[name][3]
        assert 0.45 < ratio < 0.75, f"{name}: {ratio:.2f}"


def test_delta_scf_returns_nearly_the_same_electron_affinity_for_everything():
    """The unbound-anion artefact, made visible.

    Experimentally these four affinities span -1.9 to -6.4 eV. Delta-SCF
    returns -3.6 to -3.8 for all of them: without diffuse functions the
    "anion" is a basis-set artefact whose energy barely depends on which
    molecule it is attached to.

    An earlier version of this test asserted the error was one-directional
    and about +2 eV. It is not -- it is too positive for the very-negative
    affinities and too negative for the mild ones, which is precisely what
    a near-constant output looks like.
    """
    affinities = [delta_scf(name).electron_affinity for name in MEASURED]
    assert max(affinities) - min(affinities) < 0.5

    experimental = [PEARSON_EXPERIMENTAL[name][1] for name in MEASURED]
    assert max(experimental) - min(experimental) > 4.0


def test_delta_scf_compresses_the_hardness_scale():
    """The consequence of the affinity above, and the caveat on the
    orderings this module recommends.

    Hard molecules come out too soft and soft ones too hard, so the
    ORDER survives while the SPREAD does not. Ammonia and phosphine are
    2.2 eV apart experimentally and 0.19 eV apart here -- the right
    answer, on a margin thin enough that it should not be leaned on.
    """
    for name in ("water", "ammonia"):
        assert delta_scf(name).hardness < PEARSON_EXPERIMENTAL[name][3]
    for name in ("hydrogen_sulfide", "phosphine"):
        assert delta_scf(name).hardness > PEARSON_EXPERIMENTAL[name][3]

    computed = delta_scf("ammonia").hardness - delta_scf("phosphine").hardness
    experimental = PEARSON_EXPERIMENTAL["ammonia"][3] - PEARSON_EXPERIMENTAL["phosphine"][3]
    assert 0 < computed < 0.5
    assert experimental > 2.0


def test_experimental_hardness_orders_both_textbook_pairs():
    """Sanity on the transcription itself: if these numbers were typed
    wrong, the orderings the rest of this file is about would not hold in
    the reference data either."""
    eta = {name: values[3] for name, values in PEARSON_EXPERIMENTAL.items()}
    assert eta["water"] > eta["hydrogen_sulfide"]
    assert eta["ammonia"] > eta["phosphine"]


def test_pearson_relates_his_own_columns_consistently():
    """chi = (I + A)/2 and eta = (I - A)/2 must hold within rounding for
    every row -- the strongest available check that the four columns were
    read off the page correctly."""
    # 0.15 rather than 0.05: Pearson prints I and A to one decimal and
    # evidently computed chi and eta before rounding, so hydrogen
    # sulfide's row is internally off by 0.10. That is the source's
    # rounding, not a transcription error.
    for name, (i, a, chi, eta) in PEARSON_EXPERIMENTAL.items():
        assert (i + a) / 2 == pytest.approx(chi, abs=0.15), name
        assert (i - a) / 2 == pytest.approx(eta, abs=0.15), name
