"""Kapustinskii lattice energies for simple binary salts.

    U = (1.202e5 * v * |z+ z-| / (r+ + r-)) * (1 - 34.5 / (r+ + r-))

with radii in pm and U in kJ/mol, where `v` is the number of ions in the
formula unit. Kapustinskii (1956) fitted this so that a lattice energy
could be had from radii alone, without knowing the structure -- the
Madelung constant and the Born exponent are absorbed into the two
constants.

**It is defined on SIX-COORDINATE radii regardless of the real
coordination.** That is a property of the fit, not an approximation this
module chose: the ratio of Madelung constant to ion count is nearly the
same across the common structure types, which is exactly why the equation
works without being told the structure. `data/ionic_radii.json` therefore
holds VI radii only.

## What it refuses

**Every ion must be monatomic and in the table.** A polyatomic ion has a
thermochemical radius rather than a Shannon one -- those are a different
measurement from a different source, and quietly substituting anything
else would produce a plausible number for ammonium nitrate that means
nothing.

**The structure must be a genuine binary salt**: two distinct ionic
species, charges balancing, nothing covalent. Perception decides that,
not this module -- `chem/substance.py` already classifies, and duplicating
its judgement here would give the app two answers to the same question.

## What it is worth

Kapustinskii runs about 5% below Born-Haber values for the alkali
halides, and the error is systematic rather than random. It is a
structure-free ESTIMATE, and the fact it produces says so. Reporting it
as though it were a measured lattice enthalpy would be the failure this
project keeps refusing.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Kapustinskii's two fitted constants, for radii in **pm** and U in
#: kJ/mol. The 34.5 pm is the repulsion term; it is not a rounding of the
#: 0.345 A that appears in angstrom-based statements of the same equation.
_PREFACTOR_KJ_PM = 1.202e5
_REPULSION_PM = 34.5

_DATA = Path(__file__).with_name("data") / "ionic_radii.json"


@lru_cache(maxsize=1)
def shannon_radii() -> dict[str, float]:
    """Six-coordinate effective ionic radii, in angstrom, by "Na+1" key."""
    return dict(json.loads(_DATA.read_text(encoding="utf-8"))["radii"])


def _key(symbol: str, charge: int) -> str:
    return f"{symbol}{charge:+d}"


@dataclass(frozen=True)
class LatticeEnergy:
    """An estimate, or a refusal carrying its reason."""

    #: kJ/mol, positive by convention (the energy to separate the lattice).
    value: float | None = None
    cation: str = ""
    anion: str = ""
    cation_radius: float = 0.0
    anion_radius: float = 0.0
    ion_count: int = 0
    reason: str = ""

    @property
    def refused(self) -> bool:
        return self.value is None


def _refuse(reason: str) -> LatticeEnergy:
    return LatticeEnergy(reason=reason)


def kapustinskii(
    cation: str, cation_charge: int, anion: str, anion_charge: int
) -> LatticeEnergy:
    """The estimate for one binary salt, from its two ions.

    Takes ions rather than a molecule so it can be tested directly against
    published values without a structure in the way.
    """
    if cation_charge <= 0 or anion_charge >= 0:
        return _refuse(
            "A lattice needs a positive and a negative ion; "
            f"{cation} was given as {cation_charge:+d} and {anion} as {anion_charge:+d}."
        )

    radii = shannon_radii()
    missing = [
        _key(symbol, charge)
        for symbol, charge in ((cation, cation_charge), (anion, anion_charge))
        if _key(symbol, charge) not in radii
    ]
    if missing:
        return _refuse(
            f"No six-coordinate Shannon radius is tabulated here for {', '.join(missing)}. "
            "The shipped table covers the common monatomic ions; a polyatomic ion has a "
            "thermochemical radius instead, which is a different measurement."
        )

    # The formula unit: charges must balance, and the ion count is what
    # balancing them takes. CaCl2 is one Ca2+ and two Cl-, so v = 3.
    common = _gcd(cation_charge, -anion_charge)
    cations = -anion_charge // common
    anions = cation_charge // common
    ion_count = cations + anions

    plus = radii[_key(cation, cation_charge)] * 100.0  # angstrom -> pm
    minus = radii[_key(anion, anion_charge)] * 100.0
    separation = plus + minus

    value = (
        _PREFACTOR_KJ_PM
        * ion_count
        * abs(cation_charge * anion_charge)
        / separation
        * (1.0 - _REPULSION_PM / separation)
    )
    return LatticeEnergy(
        value=value,
        cation=_key(cation, cation_charge),
        anion=_key(anion, anion_charge),
        cation_radius=plus / 100.0,
        anion_radius=minus / 100.0,
        ion_count=ion_count,
    )


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a) or 1


# ---------------------------------------------------------------------------
# The volume route, for salts with complex ions
# ---------------------------------------------------------------------------

#: Coefficients of `U = 2I (alpha / V^(1/3) + beta)`, V in nm^3, U in
#: kJ/mol. Jenkins, Roobottom, Passmore & Glasser, *Inorg. Chem.* 1999,
#: 38, 3609-3620, Table 2/3 and the text beneath them.
#:
#: **Fitted per stoichiometry, not globally, on the paper's own advice.**
#: It also gives a single generalised pair (138.7, 27.6, R = 0.91) and
#: then says outright that "more reliable estimates ... result if data for
#: MX, MX2, and M2X salts are treated independently". The per-type fits
#: have R = 0.94, 0.83 and 0.95.
#:
#: Keyed by (cation charge, anion charge). MX2 and M2X both have
#: 2I = 6 and DIFFERENT coefficients, which is exactly why the key cannot
#: be the ionic strength.
_VOLUME_COEFFICIENTS: dict[tuple[int, int], tuple[float, float]] = {
    (1, -1): (117.3, 51.9),
    (2, -1): (133.5, 60.9),
    (1, -2): (165.3, -29.8),
}


@dataclass(frozen=True)
class VolumeLatticeEnergy:
    """A lattice energy from a formula-unit VOLUME, or a refusal."""

    value: float | None = None
    volume_nm3: float = 0.0
    ionic_strength_term: float = 0.0
    reason: str = ""

    @property
    def refused(self) -> bool:
        return self.value is None


def ionic_strength_term(ions: Sequence[tuple[int, int]]) -> float:
    """`2I = sum(n_k * z_k^2)` over the formula unit.

    **This is what generalises Kapustinskii beyond two ion types**, and
    it is not an approximation: for any neutral binary salt it equals
    `nu * |z+ z-|` exactly, which is the term Kapustinskii introduced.
    Verified over 1:1, 1:2, 2:1, 2:3 and complex-ion cases rather than
    taken from the paper -- Glasser, *Inorg. Chem.* 1995, 34, 4935-4936,
    which notes the quantity is twice the ionic strength and that the
    identity "seems not to have previously been noted".

    `ions` is [(count, charge), ...] over one formula unit.
    """
    return float(sum(count * charge * charge for count, charge in ions))


def volume_based_lattice_energy(
    volume_nm3: float, ions: Sequence[tuple[int, int]]
) -> VolumeLatticeEnergy:
    """Lattice potential energy from the formula-unit volume.

    **The reason this exists: it needs no radii at all.** Kapustinskii
    refuses every polyatomic ion because a thermochemical radius is a
    different measurement from a different source, and the shipped table
    has none. A volume does not care whether an ion is one atom or nine,
    and for an imported crystal the app already measures it -- so a
    nitrate or a hexachloromolybdate is answerable where a radius-based
    route is not.

    Validated on the 26 salts of Jenkins 1999 Tables 2 and 3, taking the
    EXPERIMENTAL column (CRC Handbook, their ref 40) as the target and
    the crystallographic V^(1/3) (Donnay, their ref 41) as the input, so
    neither side of the comparison is the paper's own estimate:

        26 salts   mean |deviation| 3.3%   worst 7.7%  (Ca(NO3)2)

    against Kapustinskii's 7.3% worst over 36 monatomic salts -- the same
    accuracy class, on the harder problem. Fourteen of the 26 carry a
    complex ion and twelve of those land within 4.5%.
    """
    if volume_nm3 <= 0:
        return VolumeLatticeEnergy(reason="a formula unit has no volume to work from.")
    cations = sorted({charge for _, charge in ions if charge > 0})
    anions = sorted({charge for _, charge in ions if charge < 0})
    if len(cations) != 1 or len(anions) != 1:
        return VolumeLatticeEnergy(
            reason=(
                "this equation was fitted to salts with one cation charge and one "
                "anion charge; a mixed-valence structure needs the full "
                "volume-based treatment, not this correlation."
            )
        )
    key = (cations[0], anions[0])
    coefficients = _VOLUME_COEFFICIENTS.get(key)
    if coefficients is None:
        return VolumeLatticeEnergy(
            reason=(
                f"no fitted coefficients for a {key[0]}:{abs(key[1])} charge "
                "combination; the published fits cover MX, MX2 and M2X."
            )
        )
    alpha, beta = coefficients
    two_i = ionic_strength_term(ions)
    return VolumeLatticeEnergy(
        value=two_i * (alpha / volume_nm3 ** (1 / 3) + beta),
        volume_nm3=volume_nm3,
        ionic_strength_term=two_i,
    )
