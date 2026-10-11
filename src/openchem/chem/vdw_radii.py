"""Bondi's van der Waals radii, as the paper prints them, for the calculators that say they use them.

`docs/VDW_RADII_ASSESSMENT.md` is the investigation. The short version: the surface, volume and projection
calculators take their radii from RDKit's periodic table, which is NOT Bondi's list (it equals Batsanov 2001's
recommended crystallographic radii), and for most purposes that is fine. **Percent buried volume is the exception.**
It is defined with Bondi's radii [source:bondi1964] scaled by 1.17 (SambVca, Poater et al. [source:poater2009] and Clavier and Nolan [source:clavier2010]), and RDKit's
phosphorus radius (1.95) is far from Bondi's (1.80), which put small phosphines 2 to 3.6 points high. So the steric
calculator, and only it, reads this table.

**WHAT IS IN IT, AND WHERE EACH NUMBER IS FROM.**

* `BONDI_1964`: Bondi's recommended radii for the nonmetals (his Table I, "mean van der Waals radii", the single-bonded
  forms) and for the main-group metals he derives from critical volumes (his Table XIV). Read from the printed pages of
  the 1964 paper and cross-checked against Poater et al.'s Table 1 (H, C, N, O, F, P and their x 1.17 values) and
  Mantina et al.'s Table 9 (every element, bar two noted below).
* `MANTINA_2009`: the radii Mantina et al. [source:mantina2009] determined for the 16 main-group elements Bondi gave none for, "in a way
  designed to be compatible with Bondi's scale" (their abstract).
* Anything else (the transition metals, the lanthanides) falls back to RDKit's table, and `radius_source` says so.
  Bondi's own transition-metal radii are tentative by his own account and Mantina et al. did not take them up, so
  they are not used.

**TWO PLACES THE SECONDARY SOURCES DISAGREE WITH THE PAPER, resolved by reading the paper.** Mantina's Table 9 prints
Bondi's bromine as 1.83 and lithium as 1.81; Bondi's Table I gives bromine 1.85 (also what Batsanov and the CRC
Handbook print) and his Table XIV gives lithium 1.82. This module follows the paper. Bondi's running text also says
"1.75, 1.85 and 1.97" for chlorine, bromine and iodine; his Table I says 1.98 for iodine, which the later sources
use, and so does this.

**HYDROGEN IS 1.20, BONDI'S, AND THAT IS DELIBERATE.** Rowland and Taylor (1996) [source:rowland1996] suggest 1.10 for contacts across many
atom pairs, and the CRC Handbook adopts it; but Bondi chose his radii "for the calculation of volumes", Rowland and Taylor
themselves find that hydrogen-hydrogen contacts in neutron structures support about 1.19, and Mantina et al. say 1.2
"describes well the size of H in H...H contacts". Percent buried volume omits hydrogens anyway, and the exact cone angle
uses 1.20, as it always has.
"""

from __future__ import annotations

from rdkit import Chem

#: Bondi 1964, Table I (the nonmetals he recommends a value for) and Table XIV (the main-group metals, from critical
#: volumes). Angstrom. Boron, aluminium, germanium and antimony are blank in his Table I and are Mantina's below.
BONDI_1964: dict[str, float] = {
    "H": 1.20, "He": 1.40, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "Ne": 1.54,
    "Si": 2.10, "P": 1.80, "S": 1.80, "Cl": 1.75, "Ar": 1.88,
    "As": 1.85, "Se": 1.90, "Br": 1.85, "Kr": 2.02,
    "Te": 2.06, "I": 1.98, "Xe": 2.16,
    "Li": 1.82, "Na": 2.27, "Mg": 1.73, "K": 2.75, "Ga": 1.87, "In": 1.93, "Sn": 2.17, "Tl": 1.96, "Pb": 2.02,
}

#: Mantina et al. 2009, abstract: the radii "for the other 16" main-group elements, compatible with Bondi's scale.
MANTINA_2009: dict[str, float] = {
    "Be": 1.53, "B": 1.92, "Al": 1.84, "Ca": 2.31, "Ge": 2.11, "Rb": 3.03, "Sr": 2.49, "Sb": 2.06,
    "Cs": 3.43, "Ba": 2.68, "Bi": 2.07, "Po": 1.97, "At": 2.02, "Rn": 2.20, "Fr": 3.48, "Ra": 2.83,
}

#: What `radius_source` answers for an element in `BONDI_1964`.
SOURCE_BONDI = "bondi1964"
#: What `radius_source` answers for an element only in `MANTINA_2009`.
SOURCE_MANTINA = "mantina2009"
#: What `radius_source` answers for an element in neither table: RDKit's own radius is the fallback.
SOURCE_RDKIT = "rdkit"

#: What a result computed with this table records as its radii, so a stored value says which table made it.
RADII_LABEL = "bondi1964+mantina2009 (rdkit for other elements)"

#: RDKit's periodic table, the documented fallback for an element neither source covers.
_PERIODIC_TABLE = Chem.GetPeriodicTable()


def _symbol(atomic_number: int) -> str:
    return _PERIODIC_TABLE.GetElementSymbol(int(atomic_number))


def radius_source(atomic_number: int) -> str:
    """Which table the radius of this element comes from."""
    symbol = _symbol(atomic_number)
    if symbol in BONDI_1964:
        return SOURCE_BONDI
    if symbol in MANTINA_2009:
        return SOURCE_MANTINA
    return SOURCE_RDKIT


def bondi_radius(atomic_number: int) -> float:
    """The van der Waals radius of an element on Bondi's scale, in angstrom.

    Bondi's own recommended value where he gives one, Mantina et al.'s where they extend it, and RDKit's table for
    the rest (see the module docstring).
    """
    symbol = _symbol(atomic_number)
    if symbol in BONDI_1964:
        return BONDI_1964[symbol]
    if symbol in MANTINA_2009:
        return MANTINA_2009[symbol]
    return float(_PERIODIC_TABLE.GetRvdw(int(atomic_number)))
