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
