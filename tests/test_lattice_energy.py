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
from pathlib import Path

import pytest

from openchem.chem.lattice_energy import (
    ionic_strength_term,
    volume_based_lattice_energy,
)
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


# --- the volume route, for salts a radius cannot describe -------------------
#
# Jenkins, Roobottom, Passmore & Glasser, Inorg. Chem. 1999, 38, 3609-3620.
# Tables 2 and 3: the EXPERIMENTAL lattice potential energy (their ref 40,
# the CRC Handbook) and the crystallographic cube root of the formula-unit
# volume (their ref 41, Donnay). Their own estimate column is deliberately
# NOT used as the target -- that would check arithmetic against the fit
# rather than against experiment.

#: (salt, U_experimental kJ/mol, V^(1/3) nm). MX2 salts, Table 2.
_JENKINS_TABLE_2 = [
    ("BaF2", 2341, 0.3903), ("BaCl2", 2033, 0.4442), ("BaBr2", 1950, 0.4751),
    ("BaI2", 1831, 0.5020), ("CaF2", 2609, 0.3442), ("CaCl2", 2223, 0.4384),
    ("CaBr2", 2132, 0.4614), ("CaI2", 1905, 0.4946), ("MgCl2", 2326, 0.4031),
    ("MgBr2", 2097, 0.4288), ("MgI2", 1944, 0.4674), ("Ca(NO3)2", 2209, 0.4788),
]

#: M2X salts, Table 3. Twelve of these fourteen carry a complex ion.
_JENKINS_TABLE_3 = [
    ("Cs2CoCl4", 1391, 0.6157), ("Cs2CuCl4", 1393, 0.6126), ("Cs2GeF6", 1573, 0.5675),
    ("Cs2MoCl6", 1347, 0.6470), ("Cs2ZnBr4", 1454, 0.6445), ("Cs2ZnCl4", 1429, 0.6157),
    ("K2S", 1979, 0.4637), ("K2MoCl6", 1418, 0.6205), ("K2PtCl4", 1574, 0.5881),
    ("Li2CO3", 2523, 0.3832), ("Na2CO3", 2301, 0.4079), ("Na2S", 2192, 0.4119),
    ("Rb2MoCl6", 1399, 0.6293), ("Rb2S", 1929, 0.4832),
]


def _percent_off(predicted: float, experimental: float) -> float:
    """Named to avoid the file's own `_deviation(salt)`, which takes a
    salt name and uses Kapustinskii. Shadowing it broke 41 tests."""
    return 100.0 * (predicted - experimental) / experimental


def test_twice_the_ionic_strength_equals_kapustinskiis_own_term():
    """**The whole generalisation rests on this identity**, so it is
    checked rather than cited: for any neutral binary salt,
    `sum(n_k z_k^2)` equals `nu * |z+ z-|`, the term Kapustinskii
    introduced. Glasser (Inorg. Chem. 1995, 34, 4935) notes it "seems not
    to have previously been noted"; it is what lets one equation cover
    salts with more than two kinds of ion."""
    cases = {
        "NaCl": [(1, +1), (1, -1)],
        "CaF2": [(1, +2), (2, -1)],
        "MgO": [(1, +2), (1, -2)],
        "Al2O3": [(2, +3), (3, -2)],
        "Na2SO4": [(2, +1), (1, -2)],
    }
    for name, ions in cases.items():
        nu = sum(count for count, _ in ions)
        cation = next(z for _, z in ions if z > 0)
        anion = next(z for _, z in ions if z < 0)
        assert ionic_strength_term(ions) == pytest.approx(nu * abs(cation * anion)), name


def test_the_volume_route_reproduces_experimental_lattice_energies():
    """**The bar Phase 6 was given**: ship only if it reproduces
    Born-Haber values as Kapustinskii did, which was 7.3% worst over 36
    monatomic salts. Measured here over 26 salts, fourteen of them
    carrying a complex ion no radius-based route can describe."""
    deviations = []
    for _salt, experimental, v_cube_root in _JENKINS_TABLE_2:
        result = volume_based_lattice_energy(v_cube_root ** 3, [(1, +2), (2, -1)])
        deviations.append(abs(_percent_off(result.value, experimental)))
    for _salt, experimental, v_cube_root in _JENKINS_TABLE_3:
        result = volume_based_lattice_energy(v_cube_root ** 3, [(2, +1), (1, -2)])
        deviations.append(abs(_percent_off(result.value, experimental)))

    assert len(deviations) == 26
    assert max(deviations) < 8.0, f"worst {max(deviations):.2f}%"
    assert sum(deviations) / len(deviations) < 4.0


def test_the_complex_ion_salts_are_the_point_and_they_work():
    """Kapustinskii refuses every one of these by name -- a nitrate, a
    carbonate and a hexachlorometallate have thermochemical radii, which
    are a different measurement from a different source and are not in
    the shipped table. A volume does not care how many atoms an ion has."""
    for salt, experimental, v_cube_root in _JENKINS_TABLE_3:
        if salt not in ("Li2CO3", "Na2CO3", "K2PtCl4", "Cs2GeF6"):
            continue
        result = volume_based_lattice_energy(v_cube_root ** 3, [(2, +1), (1, -2)])
        assert abs(_percent_off(result.value, experimental)) < 5.0, salt

    # And the radius route still refuses them, which is correct: it has
    # no radius for a carbonate and must not invent one.
    assert kapustinskii("Na", 1, "CO3", -2).refused


def test_MX2_and_M2X_are_not_interchangeable_despite_equal_ionic_strength():
    """Both have `2I = 6`, and they have different fitted coefficients --
    which is why the coefficient table is keyed on the charges rather
    than on the ionic strength.

    **The two fits CROSS**, and that is why this test does not pick a
    single volume. MX2's larger beta offsets M2X's larger alpha, so near
    V^(1/3) = 0.34 they agree to 10 kJ/mol; out where the real M2X salts
    live (0.6 and above) they differ by more than 200. An earlier version
    of this test asserted a large gap at CaF2's volume and failed --
    correctly, because the claim was wrong rather than the code.
    """
    def pair(v_cube_root):
        v = v_cube_root ** 3
        return (volume_based_lattice_energy(v, [(1, +2), (2, -1)]).value,
                volume_based_lattice_energy(v, [(2, +1), (1, -2)]).value)

    assert ionic_strength_term([(1, +2), (2, -1)]) == ionic_strength_term([(2, +1), (1, -2)])

    near_crossing = pair(0.3442)                    # CaF2
    assert abs(near_crossing[0] - near_crossing[1]) < 20

    where_m2x_salts_live = pair(0.6470)             # Cs2MoCl6
    assert abs(where_m2x_salts_live[0] - where_m2x_salts_live[1]) > 200


def test_a_measured_cell_volume_reproduces_a_born_haber_value():
    """**The chain that needs no shipped parameters at all.** The volume
    comes from a CIF this app parsed; the target is the experimental
    value already in this file's Kapustinskii validation set. Neither
    came from the paper the coefficients came from."""
    from openchem.chem.cif import read_cif
    from openchem.chem.crystal_analysis import volume_per_formula_unit

    crystal = read_cif(
        (Path(__file__).resolve().parent.parent
         / "spikes" / "crystallography" / "halite.cif").read_text(encoding="utf-8")
    )
    volume_nm3 = volume_per_formula_unit(crystal) / 1000.0

    result = volume_based_lattice_energy(volume_nm3, [(1, +1), (1, -1)])

    assert abs(_percent_off(result.value, EXPERIMENTAL["NaCl"])) < 5.0


def test_a_mixed_valence_structure_is_refused_rather_than_averaged():
    """Magnetite has Fe(II) and Fe(III). The correlation was fitted to
    one cation charge and one anion charge, and picking a mean would give
    a plausible number the fit says nothing about."""
    result = volume_based_lattice_energy(0.0739, [(1, +2), (2, +3), (4, -2)])

    assert result.refused
    assert "mixed-valence" in result.reason


def test_a_charge_combination_outside_the_published_fits_is_refused():
    """MX, MX2 and M2X are what were fitted. A 3:2 salt is not, and
    extrapolating a two-parameter empirical correlation past its data is
    how a plausible wrong number gets shipped."""
    result = volume_based_lattice_energy(0.05, [(2, +3), (3, -2)])

    assert result.refused
    assert "MX, MX2 and M2X" in result.reason
