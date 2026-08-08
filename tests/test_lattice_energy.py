"""Kapustinskii, against experiment and against first principles.

This shipped only because it cleared a gate written before it was built:
reproduce reference Born-Haber values for simple binary salts, or join
the measured-and-not-shipped list beside TSEI, HLB and Miller
polarizability. It cleared it, and the deviation it clears it BY is
asserted here rather than described loosely -- a systematic 5% is a
usable estimate, a random 5% would not be.
"""

from __future__ import annotations

import math
import statistics

import pytest

from openchem.chem.lattice_energy import kapustinskii, shannon_radii

#: Experimental lattice energies, kJ/mol, from Kaya, Robles-Navarro,
#: Mejia, Gomez & Cardenas, *J. Phys. Chem. A* **2022**, 126, 4507-4516,
#: Table 3, column "Exp U".
#:
#: Only the salts whose ions are in the shipped radii table are here. The
#: paper's transition-metal and beryllium rows are omitted because no
#: radius was transcribed for them -- not because they disagree.
EXPERIMENTAL: dict[str, int] = {
    "LiF": 1036, "LiCl": 853, "LiBr": 807, "LiI": 757,
    "NaF": 923, "NaCl": 787, "NaBr": 747, "NaI": 704,
    "KF": 821, "KCl": 715, "KBr": 682, "KI": 649,
    "RbF": 785, "RbCl": 689, "RbBr": 660, "RbI": 630,
    "CsF": 740, "CsCl": 659, "CsBr": 631, "CsI": 604,
    "MgO": 3791, "CaO": 3401, "SrO": 3223, "BaO": 3054,
    "CaS": 2966, "SrS": 2779, "BaS": 2643,
    "MgF2": 2978, "MgCl2": 2540, "MgBr2": 2451, "MgI2": 2340,
    "CaF2": 2651, "CaCl2": 2363, "CaI2": 2087,
    "BaF2": 2373, "BaCl2": 2069,
}

_CATIONS = {"Li": 1, "Na": 1, "K": 1, "Rb": 1, "Cs": 1, "Mg": 2, "Ca": 2, "Sr": 2, "Ba": 2}
_ANIONS = {"F": -1, "Cl": -1, "Br": -1, "I": -1, "O": -2, "S": -2}


def _split(salt: str) -> tuple[str, str]:
    for cation in sorted(_CATIONS, key=len, reverse=True):
        if salt.startswith(cation):
            rest = salt[len(cation) :].rstrip("0123456789")
            if rest in _ANIONS:
                return cation, rest
    raise AssertionError(f"could not split {salt}")


def _estimate(salt: str) -> float:
    cation, anion = _split(salt)
    result = kapustinskii(cation, _CATIONS[cation], anion, _ANIONS[anion])
    assert not result.refused, result.reason
    return result.value


def _deviation(salt: str) -> float:
    return 100.0 * (_estimate(salt) - EXPERIMENTAL[salt]) / EXPERIMENTAL[salt]


# --- the gate ---------------------------------------------------------------


@pytest.mark.parametrize("salt", sorted(EXPERIMENTAL))
def test_every_salt_lands_within_ten_percent_of_experiment(salt):
    assert abs(_deviation(salt)) < 10.0


def test_the_whole_set_is_close_and_the_worst_case_is_pinned():
    """Pinned so that a change which improves the average while wrecking
    one salt cannot pass. Measured: 36 salts, worst 7.3%."""
    deviations = [abs(_deviation(salt)) for salt in EXPERIMENTAL]

    assert len(deviations) == 36
    assert max(deviations) < 7.5
    assert statistics.mean(deviations) < 5.0


def test_the_error_is_systematic_rather_than_random():
    """**This is what makes a 5% estimate usable.** A reader who knows the
    answer is consistently a few percent low can correct for it; a reader
    facing a random 5% cannot. Every 1:1 alkali halide comes out LOW."""
    halides = [
        salt
        for salt in EXPERIMENTAL
        if _CATIONS[_split(salt)[0]] == 1 and _ANIONS[_split(salt)[1]] == -1
    ]

    assert len(halides) == 20
    assert all(_deviation(salt) < 0 for salt in halides)
    assert all(-8.0 < _deviation(salt) < -3.0 for salt in halides)


def test_the_dipositive_salts_are_far_more_accurate_than_the_alkali_halides():
    """Not an accident, and worth stating because it means the caveat is
    not uniform. The omitted dispersion term is roughly the same absolute
    size either way, so against a much larger Coulomb term it barely
    shows: the 2:2 oxides and sulfides land inside 2%."""
    two_two = ["MgO", "CaO", "SrO", "BaO", "CaS", "SrS", "BaS"]

    assert all(abs(_deviation(salt)) < 2.0 for salt in two_two)
    assert max(abs(_deviation(s)) for s in two_two) < min(
        abs(_deviation(s)) for s in ("LiF", "NaCl", "KBr", "CsI")
    )


# --- the implementation, checked without any table at all -------------------


def test_the_madelung_constant_can_be_computed_from_scratch():
    """Evjen summation, weighting ions on the cube's surface by the
    fraction of it they occupy so each shell is neutral -- the raw sum is
    only conditionally convergent and does not settle.

    This exists so the Born-Lande cross-check below rests on a number this
    suite derived rather than one it was told.
    """
    def madelung(n: int) -> float:
        total = 0.0
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                for k in range(-n, n + 1):
                    if i == j == k == 0:
                        continue
                    weight = 1.0
                    for component in (i, j, k):
                        if abs(component) == n:
                            weight *= 0.5
                    total += weight * (-1) ** (i + j + k) / math.sqrt(i * i + j * j + k * k)
        return -total

    assert madelung(8) == pytest.approx(1.74756, abs=2e-5)


def test_kapustinskii_agrees_with_born_lande_from_first_principles():
    """A second, independent route to the same number, using only physical
    constants and the accepted rock-salt Madelung constant. It catches the
    errors an experimental comparison would hide behind a fitted constant:
    a wrong prefactor, an angstrom/picometre slip, a miscounted ion.
    """
    avogadro = 6.02214076e23
    charge = 1.602176634e-19
    permittivity = 8.8541878128e-12
    madelung = 1.74756
    born_exponent = 8  # Pauling: Na+ (Ne core) 7 and Cl- (Ar core) 9, averaged

    radii = shannon_radii()
    separation = (radii["Na+1"] + radii["Cl-1"]) * 1e-10
    born_lande = (
        avogadro
        * madelung
        * charge**2
        / (4 * math.pi * permittivity * separation)
        * (1 - 1 / born_exponent)
        / 1000
    )

    assert _estimate("NaCl") == pytest.approx(born_lande, rel=0.02)


# --- the radii themselves ---------------------------------------------------


def test_the_effective_radii_are_used_not_the_crystal_radii():
    """**Cs+ is CR 1.81 / IR 1.67 and Cl- is CR 1.67 / IR 1.81** -- the
    same two numbers, swapped. A spot-check landing on either alone would
    look right with the columns transposed, so both are asserted."""
    radii = shannon_radii()

    assert radii["Cs+1"] == 1.67
    assert radii["Cl-1"] == 1.81


@pytest.mark.parametrize(
    "ion,radius",
    [("Li+1", 0.76), ("Na+1", 1.02), ("K+1", 1.38), ("F-1", 1.33), ("O-2", 1.40)],
)
def test_radii_match_shannon_table_1(ion, radius):
    """Read from a rendered image of Table 1 -- the PDF's text layer is
    OCR and mangles the ion labels -- and cross-checked against an
    independent transcription. All 15 agreed."""
    assert shannon_radii()[ion] == radius


# --- refusals ---------------------------------------------------------------


def test_an_ion_with_no_tabulated_radius_is_refused_with_its_reason():
    result = kapustinskii("Fe", 2, "Cl", -1)

    assert result.refused
    assert "Fe+2" in result.reason
    assert "thermochemical radius" in result.reason


def test_two_cations_are_refused():
    assert kapustinskii("Na", 1, "K", 1).refused


def test_the_formula_unit_counts_its_ions():
    """CaCl2 is one Ca2+ and two Cl-, so v = 3. Getting this wrong scales
    the answer by 3/2 and still produces a plausible number."""
    assert kapustinskii("Na", 1, "Cl", -1).ion_count == 2
    assert kapustinskii("Ca", 2, "Cl", -1).ion_count == 3
    assert kapustinskii("Mg", 2, "O", -2).ion_count == 2
