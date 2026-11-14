"""An idealised 3D STARTING geometry for hypervalent molecules, from VSEPR shape and measured bond data.

WHY THIS EXISTS. Distance geometry plus a force field knows nothing of lone pairs. Measured with the
repository's RDKit (2025.09.6, Phase 0 of the hypervalent plan): XeF2 came out bent at 112 degrees, XeF4,
SF4 and SF6 with angles as small as 42 degrees, IF3 trigonal planar, and ClF3, BrF3 and ClF5 cannot be
embedded at all (RDKit allows chlorine and bromine one bond). So for the molecules in `REFERENCES` the
coordinates are built here instead, and for everything else the caller is told it is NOT covered.

WHAT IT IS NOT. It is a starting geometry, never an optimised one: the angles and lengths are the
published gas-phase (or, where stated, crystal) values for ONE molecule each, placed on the VSEPR
template for its shape. It has no energy, it is not a force-field minimum and it is not a quantum
minimum; ORCA is what refines it. Nothing here estimates a bond length from radii: a molecule with no
entry in `REFERENCES` gets a stated refusal, not a guess.

THE SHAPE COMES FROM THE GRAPH. For one centre with `n` terminal ligands (singly bonded, or doubly bonded oxygen where a measured geometry is recorded) and no formal
charge, the lone pairs are `(outer electrons - n) / 2`, and `(n, lone pairs)` names the shape (ClF3:
7 electrons, 3 bonds, 2 lone pairs, T-shaped). Lone pairs are never atoms and never occupy a ligand slot.

THREE OUTCOMES, kept apart because they need different handling (`VseprOutcome.kind`):

* `BUILT`        a supported molecule; `geometry` holds the coordinates.
* `UNSUPPORTED`  a hypervalent centre of the kind this module is about (one centre, terminal single
                 bonds, neutral, a valence the hypervalent table lists) but with no reference entry, or an
                 electron count the templates do not cover. The caller must NOT fall back to embedding:
                 that is the path known to give a wrong shape. `reason` says which.
* `NOT_APPLICABLE` anything else (a carbon, sulfate with its double bonds, a ring, a charged ion, a
                 normal valence): the ordinary conformer path is correct for it and is left alone.

The reference values are literature figures recorded with their source. The first seven rows (ClF3, BrF3, XeF2,
XeF4, SF4, SF6, PF5) were read from NIST's CCCBDB experimental-geometry table (2026-11-13) [source:nist_cccbdb_geometries], a compilation whose
original papers are not held; the last four (BrF5, IF5, ClF5, IF7) were read from the papers themselves, held in
the maintainer's library, and say what each paper does and does not determine. The angles are as measured: ClF3
87.45 degrees (so its trans pair is 174.9), BrF3 86.21, SF4 173.07 and 101.55. The held copy of Kuchitsu 1998 is
only an index of citations, so SF6's value could not be read off the held book. Lengths are `re`, `r0`, `ra` or
`rg` as the source gives them: they differ by a few thousandths of an Angstrom, far below what a starting
geometry needs, and ORCA refines them. ClF5 is the one row whose two lengths are an ASSUMPTION (see its method).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

#: Outer-shell electrons of the centres covered (group number), for the lone-pair count.
_OUTER_ELECTRONS = {"P": 5, "As": 5, "Sb": 5, "S": 6, "Se": 6, "Te": 6, "Cl": 7, "Br": 7, "I": 7, "Xe": 8}


class Kind(str, Enum):
    BUILT = "built"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class Reference:
    """Measured geometry of ONE molecule, in the roles of its template (`axial`/`equatorial`)."""

    centre: str
    ligand: str
    n_ligands: int
    #: Bond length of the axial / equatorial class, Angstrom. Equal when the shape has one class.
    axial: float
    equatorial: float
    #: Named angles, degrees; the template says which it reads (see `_PLACERS`). Absent means the ideal.
    angles: dict[str, float] = field(default_factory=dict)
    source: str = ""
    #: What the numbers were measured by ("gas-phase microwave", ...), so none is read as more than it is.
    method: str = ""
    #: True when the figures were compared with a published table (see the module docstring).
    checked: bool = False
    #: The formal charge on the centre (an anion's, ClF4- and XeF5-); 0 for a neutral molecule.
    charge: int = 0
    #: For a molecule with more than one kind of ligand, or a double bond to oxygen: one `(token, length)` per slot in
    #: the template's slot order (axial slots, then equatorial). A token is the ligand's element, followed by "=" for a
    #: double bond ("F", "O="). Empty for the ordinary case, where `axial` and `equatorial` give every length.
    slots: tuple[tuple[str, float], ...] = ()
    #: Names a placer other than the template's default (see `_LAYOUTS`), for a distorted shape whose angles the
    #: default does not read (ClF3O's Cs bipyramid, SOF4's C2v one, SF5Cl's C4v octahedron).
    layout: str = ""

    @property
    def key(self) -> tuple[str, str, int, int]:
        return (self.centre, self.ligand, self.n_ligands, self.charge)


# Axial and equatorial are the two classes of a T-shape, seesaw or trigonal bipyramid; a one-class shape
# (linear, square planar, octahedral) has `axial == equatorial`.
#: The measured geometries, one row per molecule (see `Reference`); `REFERENCES` is the lookup built from them.
_ENTRIES = (
    # Every row was read from NIST's CCCBDB experimental-geometry table on 2026-11-13 (the original paper in
    # each case is the "source"). CCCBDB's "axial" and "on axis" wording is not consistent across molecules,
    # so the classes here are the VSEPR ones: `axial` is the longer, trans pair (the T's bar, the seesaw's
    # near-linear pair, the bipyramid's apexes).
    Reference(
        "Cl",
        "F",
        3,
        1.697,
        1.597,
        {"ax-eq": 87.45},
        "Muller 2001, PCCP 3, 1570",
        "microwave, re structure",
        True,
    ),
    Reference(
        "Br",
        "F",
        3,
        1.810,
        1.721,
        {"ax-eq": 86.21},
        "Magnuson 1957, J Chem Phys 27, 223",
        "microwave",
        True,
    ),
    Reference(
        "Xe",
        "F",
        2,
        1.974,
        1.974,
        {},
        "Burger and Ma 1993, J Mol Spec 157, 536",
        "re",
        True,
    ),
    Reference(
        "Xe",
        "F",
        4,
        1.935,
        1.935,
        {},
        "Burger, Ma, Breidung and Thiel 1996, J Chem Phys 104, 4945",
        "r0",
        True,
    ),
    Reference(
        "S",
        "F",
        4,
        1.646,
        1.545,
        {"ax-ax": 173.07, "eq-eq": 101.55},
        "Tolles and Gwinn 1962, J Chem Phys 36, 1119",
        "microwave",
        True,
    ),
    Reference(
        "S",
        "F",
        6,
        1.561,
        1.561,
        {},
        "Kuchitsu 1998, Structure of Free Polyatomic Molecules",
        "gas phase",
        True,
    ),
    Reference(
        "P",
        "F",
        5,
        1.577,
        1.534,
        {},
        "Gurvich, Veyts and Alcock 1989 (compilation, as listed by NIST CCCBDB)",
        "compiled",
        True,
    ),
    # The four rows below were read from the PAPERS (held copies, 2026-11-13), not from a compilation. For the
    # square pyramids `axial` is the apical bond and `equatorial` the basal ones; `ax-eq` is F(apical)-X-F(basal).
    Reference(
        "Br",
        "F",
        5,
        1.689,
        1.774,
        {"ax-eq": 84.8},
        "Robiette, Bradley and Brier 1971, J Chem Soc D (23), 1567 [source:robiette1971]",
        "gas electron diffraction with microwave rotational constants (apical 0.008, basal 0.003, angle 0.1 esd)",
        True,
    ),
    Reference(
        "I",
        "F",
        5,
        1.844,
        1.869,
        {"ax-eq": 81.9},
        "Robiette, Bradley and Brier 1971, J Chem Soc D (23), 1567 [source:robiette1971]",
        "gas electron diffraction with microwave rotational constants (apical 0.025, basal 0.005, angle 0.1 esd; "
        "the apical-basal difference is poorly determined)",
        True,
    ),
    Reference(
        "Cl",
        "F",
        5,
        1.65,
        1.65,
        {"ax-eq": 86.5},
        "Bodenseh, Huttner and Nowicki 1976, Z Naturforsch 31a, 1638 [source:bodenseh1976]",
        "microwave, two rotational constants: only the angle (86.5, esd 1.0) is determined; the paper states that a "
        "complete structure is not possible and that both lengths are about 1.65 A, so one value is used for both",
        True,
    ),
    Reference(
        "I",
        "F",
        7,
        1.786,
        1.858,
        {},
        "Adams, Thompson and Bartell 1970, J Chem Phys 53, 4040 [source:adams1970]",
        "gas electron diffraction, D5h average (axial 0.007, equatorial 0.004 esd); the molecule is puckered by "
        "7.5 degrees and axially bent by 4.5 degrees on average, which the ideal pentagonal bipyramid here omits",
        True,
    ),
    # Read from the papers (held copies, 2026-11-13). rg distances are as the source gives them.
    Reference(
        "As",
        "F",
        5,
        1.711,
        1.656,
        {},
        "Clippard and Bartell 1970, Inorg Chem 9, 805 [source:clippard1970]",
        "gas electron diffraction, rg (axial 0.005, equatorial 0.004 esd); trigonal bipyramid with the ideal 90 and 120 degrees",
        True,
    ),
    Reference(
        "Se",
        "F",
        4,
        1.7713,
        1.6821,
        {"ax-ax": 169.20, "eq-eq": 100.55},
        "Bowater, Brown and Burden 1968, J Mol Spec 28, 454 [source:bowater1968]",
        "microwave (two isotopologues); equatorial F-Se-F 100.55, axial F-Se-F 169.20",
        True,
    ),
    Reference(
        "P",
        "Cl",
        5,
        2.124,
        2.020,
        {},
        "Adams and Bartell 1971, J Mol Struct 8, 23 [source:adams1971]",
        "gas electron diffraction, rg (axial 0.009, equatorial 0.007 esd; mean 2.061 0.002); equals the CCCBDB compilation entry",
        True,
    ),
    Reference(
        "Se",
        "F",
        6,
        1.685,
        1.685,
        {},
        "Bartell and Jin 1984, J Mol Struct 118, 289 [source:bartell1984]",
        "gas electron diffraction, rg(3a) 1.685 (0.002); regular octahedron",
        True,
    ),
    Reference(
        "Te",
        "Cl",
        4,
        2.430,
        2.298,
        {"ax-ax": 175.9, "eq-eq": 103.0},
        "Kovacs, Martinsen and Konings 1997, J Chem Soc Dalton Trans, 1037 [source:kovacs1997]",
        "gas electron diffraction, ra (0.006 esd), D term not included: axial 243.0, equatorial 229.8 pm; Cl-Te-Cl axial 175.9 (0.6), equatorial 103.0 (0.7); seesaw",
        True,
    ),
    # Molecules with two kinds of ligand or a double bond to oxygen. Read from the papers (held copies, 2026-11-13);
    # each says what its figures are. The `slots` give a (ligand, length) per position in template order.
    Reference(
        "Cl",
        "FFFO=",
        4,
        1.713,
        1.603,
        {"fax-feq": 87.9, "fax-o": 94.7, "feq-o": 108.9},
        "Oberhammer and Christe 1982, Inorg Chem 21, 273 [source:oberhammer1982]",
        "gas electron diffraction, r-alpha (esd 0.003 to 0.004 A, angles 0.9 to 2.0 degrees); distorted trigonal bipyramid, "
        "Cs, lone pair equatorial",
        True,
        0,
        (("F", 1.713), ("F", 1.713), ("F", 1.603), ("O=", 1.405)),
        "cs_bipyramid",
    ),
    Reference(
        "Xe",
        "FFFFO=",
        5,
        1.7053,
        1.9040,
        {"ax-eq": 91.66},
        "Jacob, Thompson and Bartell 1971, J Mol Struct 8, 383 [source:jacob1971]",
        "microwave rotational constants refined with electron diffraction, rz basis (spectroscopic column; the diffraction "
        "columns give Xe=O 1.708 to 1.711, Xe-F 1.901 to 1.902 A, O-Xe-F 91.6 to 91.9); C4v square pyramid, O apical",
        True,
        0,
        (("O=", 1.7053),) + (("F", 1.9040),) * 4,
    ),
    Reference(
        "Xe",
        "FFO=O=",
        4,
        1.899,
        1.714,
        {"ax-ax": 174.7, "eq-eq": 105.7, "ax-eq": 91.6},
        "Peterson, Holloway, Coyle and Williams 1973, J Chem Phys 58, 456 [source:peterson1973]",
        "neutron diffraction of the CRYSTAL at room temperature (not corrected for thermal motion; the corrected lengths "
        "are 1.92 and 1.74 A); the molecules are joined into layers by weak Xe...O contacts, which are omitted here",
        True,
        0,
        (("F", 1.899), ("F", 1.899), ("O=", 1.714), ("O=", 1.714)),
    ),
    Reference(
        "S",
        "FFFFO=",
        5,
        1.596,
        1.539,
        {"eq-eq": 112.8, "ax-o": 97.7},
        "Hedberg and Hedberg 1982, J Phys Chem 86, 598 [source:hedberg1982]",
        "gas electron diffraction with microwave data, ra at room temperature (esd 0.003 A); C2v trigonal bipyramid with the "
        "oxygen and two fluorines equatorial. Published F(ax)-S-F(eq) 85.7 follows from the two angles used",
        True,
        0,
        (("F", 1.596), ("F", 1.596), ("O=", 1.409), ("F", 1.539), ("F", 1.539)),
        "c2v_bipyramid",
    ),
    Reference(
        "S",
        "ClFFFFF",
        6,
        2.0301,
        1.576,
        {"ax-eq": 88.0 + 22.0 / 60.0},
        "Kewley, Murty and Sugden 1960, Trans Faraday Soc 56, 1732 [source:kewley1960]",
        "microwave (four isotopologues); C4v, all five S-F lengths taken equal (1.576 +- 0.010 A), Cl-S-F 88 degrees 22 minutes",
        True,
        0,
        (("Cl", 2.0301), ("F", 1.576)) + (("F", 1.576),) * 4,
        "c4v_octahedron",
    ),
    # Two more CRYSTAL structures, from the papers (2026-11-14). In each the molecule or ion is bridged to its neighbours by longer contacts, which are omitted.
    Reference(
        "I",
        "F",
        3,
        1.983,
        1.872,
        {"ax-eq": 80.2},
        "Hoyer and Seppelt 2000, Angew Chem Int Ed 39, 1448 [source:hoyer2000]",
        "single-crystal X-ray, -135 C: I-F 198.3 (0.3) twice and 187.2 (0.4) pm, F-I-F 160.3 (0.2) and 80.2 (0.1) degrees; a planar T, but "
        "the solid is polymeric through I...F bridges of 276.9 pm, which are omitted (IF3 decomposes above -28 C and has no gas-phase structure)",
        True,
    ),
    Reference(
        "Cl",
        "F",
        4,
        1.617,
        1.530,
        {"ax-ax": 173.92, "eq-eq": 103.08, "ax-eq": 88.1},
        "Christe, Zhang, Sheehy and Bau 2001, J Am Chem Soc 123, 6338 [source:christe2001]",
        "single-crystal X-ray of ClF4+SbF6-: Cl-F 1.617 (0.002) axial, 1.527 and 1.532 (0.002) equatorial (mean 1.530), F-Cl-F 173.92 axial, "
        "103.08 equatorial, 88.1 axial-equatorial; two longer Cl...F contacts of 2.41 and 2.43 A to anions are omitted, and they compress the equatorial angle "
        "(the free cation calculates near 109.7)",
        True,
        1,
    ),
    # Four more anions, all CRYSTAL structures (2026-11-14). Zhang and Seppelt 1997 used the 1,1,3,3,5,5-hexamethylpiperidinium cation because its contacts with the
    # anion are weak; the ions are close to ideal.
    Reference(
        "I",
        "F",
        4,
        2.007,
        2.007,
        {},
        "Zhang and Seppelt 1997, Z Anorg Allg Chem 623, 491 [source:zhang1997]",
        "single-crystal X-ray of (pip+)2 IF4- H2F3-, two independent square planar ions: I-F 200.6 (0.3), 201.8 (0.3), 200.3 (0.4) and 200.0 (0.4) pm, mean 200.7; angles 90 and 180 within 0.3",
        True,
        -1,
    ),
    Reference(
        "I",
        "F",
        2,
        2.0785,
        2.0785,
        {},
        "Zhang and Seppelt 1997, Z Anorg Allg Chem 623, 491 [source:zhang1997]",
        "single-crystal X-ray of pip+ IF2-: I-F 207.5 (0.3) and 208.2 (0.3) pm (mean 207.85, equal within 3 esd), F-I-F 177.8 (0.1) degrees in the crystal, placed linear here",
        True,
        -1,
    ),
    Reference(
        "Br",
        "F",
        4,
        1.89,
        1.89,
        {},
        "Edwards and Jones 1969, J Chem Soc A, 1936 [source:edwards1969]",
        "neutron powder diffraction of the K salt: Br-F 1.89 (0.02) A, F-Br-F 90.9 and 89.1 (2.0), square planar; Zhang and Seppelt 1997 quote 189 pm from a Rb salt single crystal. "
        "Siegel's 1956 tetrahedral model (1.81 A) was shown wrong",
        True,
        -1,
    ),
    Reference(
        "As",
        "F",
        4,
        1.870,
        1.7255,
        {"ax-ax": 165.7, "eq-eq": 97.5},
        "Zhang and Seppelt 1997, Z Anorg Allg Chem 623, 491 [source:zhang1997]",
        "single-crystal X-ray of pip+ AsF4-: As-F axial 187.8 (0.2) and 186.2 (0.3) (mean 187.0), equatorial 172.4 (0.2) and 172.7 (0.3) (mean 172.55) pm; F-As-F 165.7 (0.1) axial, 97.5 (0.1) equatorial; "
        "the axial-equatorial angles (84.5 to 86.1) follow from those two; a seesaw with several F...H and weak As...F contacts omitted",
        True,
        -1,
    ),
    # Two more trigonal bipyramids (2026-11-14), from gas-phase electron diffraction: antimony pentachloride and PCl2F3 (chlorines equatorial).
    Reference(
        "Sb",
        "Cl",
        5,
        2.338,
        2.277,
        {},
        "Ivashkevich, Ishchenko, Spiridonov et al. 1982, J Struct Chem 23, 295 [source:ivashkevich1982]",
        "gas electron diffraction, re (esd 0.007 axial, 0.005 equatorial), nozzle about 25 C, D3h with a Berry pseudorotation barrier of 1.8 (0.6) kcal/mol; the crystal "
        "(Ohlberg 1959) gives 2.34 and 2.29 A, and the liquid is a different model",
        True,
    ),
    Reference(
        "P",
        "ClClFFF",
        5,
        1.593,
        1.546,
        {},
        "French, Hedberg, Shreeve and Gupta 1985, Inorg Chem 24, 2774 [source:french1985]",
        "gas electron diffraction, rg (P-F axial 1.593 (0.004), P-F equatorial 1.546 (0.009), P-Cl 2.004 (0.002) A, nozzle 22 to 24 C): the chlorines are equatorial, "
        "F(ax)-P-F(eq) 89.3 (0.3) and Cl-P-Cl 122.0 (0.5) degrees are placed at the ideal 90 and 120; the molecule exchanges its fluorines by a Berry motion",
        True,
        0,
        (("F", 1.593), ("F", 1.593), ("F", 1.546), ("Cl", 2.004), ("Cl", 2.004)),
    ),
    # XeF6 is NOT one measured geometry. This row is a MODEL (Bartell and Gavin's Model C, C3v, the one that fits the radial distribution as well as the others) of a molecule
    # that is a fluxional average over such distorted octahedra; it is a starting geometry, labelled so.
    Reference(
        "Xe",
        "F",
        6,
        1.912,
        1.862,
        {"l-l": 100.6, "s-s": 91.0},
        "Bartell and Gavin 1968, J Chem Phys 48, 2466 [source:bartell1968]",
        "MODEL, not a rigid measured structure: gas electron diffraction Model C (C3v), Analysis I (rg): three long Xe-F 1.912 and three short 1.862 A (mean 1.887 (0.005), difference "
        "0.050 (0.03)), the long triple 100.6 and the short triple 91.0 degrees apart; the authors call these parameters rough guides, the molecule is a distribution of distorted "
        "octahedra with bond lengths spread over about 0.08 A and fluorine displacements of 5 to 10 degrees, and the lone pair sits on the side of the long bonds",
        True,
        0,
        (),
        "",
    ),
    # Trigonal pyramids (2026-11-14): the template `_trigonal_pyramid` with the two molecules whose crystals are the only structures measured.
    Reference(
        "Xe",
        "O=O=O=",
        3,
        1.76,
        1.76,
        {"l-l": 103.0},
        "Templeton, Zalkin, Forrester and Williamson 1963, J Am Chem Soc 85, 817 [source:templeton1963]",
        "single-crystal X-ray: Xe-O 1.74, 1.76 and 1.77 (0.03) A and O-Xe-O 108, 100 and 101 (2) degrees, whose deviations from threefold symmetry the authors "
        "call of doubtful significance; the thermal-motion-corrected means 1.76 A and 103 degrees are used",
        True,
    ),
    Reference(
        "Br",
        "FO=O=",
        3,
        1.8015,
        1.6035,
        {"l-l": 103.8},
        "Seppelt 2019, Angew Chem Int Ed 58, 18928 [source:seppelt2019]; angle from Hwang, Kuschel and Seppelt 1997, Z Anorg Allg Chem 623, 379 [source:hwang1997]",
        "lengths from the single-crystal X-ray of the adduct 3 BrO2F.4 acetone, where the bond lengths are not disturbed by disorder: Br=O 1.587 to 1.620 (0.002) and Br-F 1.781 to "
        "1.822 (0.002) A, each placed at the middle of its printed range; they reproduce the 167.4 (0.6) pm mean Br-(O,F) distance of the disordered pure crystal (Hwang 1997). "
        "The angle is that crystal's mean 103.8 (0.3) degrees (the all-equal C3v model), because the adduct paper gives no angle: O-Br-O and O-Br-F are not separately measured",
        True,
        0,
        (("F", 1.8015), ("O=", 1.6035), ("O=", 1.6035)),
    ),
    # The two anions are CRYSTAL structures: the ion is in an ionic lattice, where a Cl-F or Xe-F distance moves by a few
    # hundredths of an Angstrom with the counter-ion (ClF4- spans 1.73 to 1.87 A between salts).
    Reference(
        "Cl",
        "F",
        4,
        1.7982,
        1.7982,
        {},
        "Scheibe, Ivlev, Karttunen and Kraus 2020, Eur J Inorg Chem, 1319 [source:scheibe2020]",
        "single-crystal X-ray, K[ClF4] (F-Cl-F 89.79 and 90.21); the anion is square planar, D4h",
        True,
        -1,
    ),
    Reference(
        "Xe",
        "F",
        5,
        2.012,
        2.012,
        {},
        "Christe et al. 1991, J Am Chem Soc 113, 3351 [source:christe1991]",
        "single-crystal X-ray, [N(CH3)4][XeF5], mean of five distances 1.979 to 2.034 (esd 0.002); mean F-Xe-F 72.0 (0.4); "
        "planar, D5h",
        True,
        -1,
    ),
)
# `key` is derived from the entry, so the table cannot disagree with the lookup.
#: `(centre, ligand, number of ligands)` -> its measured geometry. A molecule not here is refused, never estimated.
REFERENCES: dict[tuple[str, str, int, int], Reference] = {r.key: r for r in _ENTRIES}


@dataclass(frozen=True)
class VseprGeometry:
    """The built coordinates and how they were made."""

    #: One (x, y, z) per atom, in the molecule's own atom order, Angstrom. The centre is at the origin.
    coordinates: tuple[tuple[float, float, float], ...]
    centre_index: int
    ligand_indices: tuple[int, ...]
    #: `"AX3E2"` style: bonds and lone pairs on the centre.
    classification: str
    shape: str
    #: Which ligands were placed in which class: indices in slot order.
    axial_indices: tuple[int, ...]
    equatorial_indices: tuple[int, ...]
    reference: Reference
    diagnostics: dict[str, float] = field(default_factory=dict)
    #: The distance each ligand was placed at, by atom index (what `validate` checks against).
    ligand_lengths: dict[int, float] = field(default_factory=dict)
    #: Always the same statement, so no consumer can mistake this for an optimised structure.
    provenance: str = "idealised VSEPR template with published bond lengths and angles; not optimised, no energy"


@dataclass(frozen=True)
class VseprOutcome:
    kind: Kind
    reason: str = ""
    geometry: VseprGeometry | None = None


#: A fixed rotation applied to every built geometry. The templates sit on the axes (a linear molecule along z, a
#: planar one in a coordinate plane), and the 3D viewer looks down z: ClF3 then drew as a line and XeF2 as a dot,
#: found in the real window. Tilting about x then y changes no length or angle and makes no template edge-on.
_VIEW_TILT = (
    np.array([[math.cos(math.radians(35)), 0.0, math.sin(math.radians(35))], [0.0, 1.0, 0.0],
              [-math.sin(math.radians(35)), 0.0, math.cos(math.radians(35))]])
    @ np.array([[1.0, 0.0, 0.0], [0.0, math.cos(math.radians(25)), -math.sin(math.radians(25))],
                [0.0, math.sin(math.radians(25)), math.cos(math.radians(25))]])
)


# --- the templates ---------------------------------------------------------------------------------------
#
# Each placer returns (axial vectors, equatorial vectors) as unit vectors for the given reference. The
# centre is the origin; the lone pairs are simply absent. Slot order is the order ligands are assigned.


def _t_shape(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # Equatorial ligand on +x; the axial pair tilts TOWARD it by (90 - ax-eq) because the two lone pairs
    # in the equatorial plane push it that way, so ax-eq < 90 (ClF3 87.5).
    a = math.radians(ref.angles.get("ax-eq", 90.0))
    return (
        [
            np.array([math.cos(a), 0.0, math.sin(a)]),
            np.array([math.cos(a), 0.0, -math.sin(a)]),
        ],
        [np.array([1.0, 0.0, 0.0])],
    )


def _linear(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    return [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])], []


def _square_planar(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    v = [np.array(p, float) for p in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))]
    return v, []


def _seesaw(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # Lone pair on -x in the equatorial plane. The axial pair is bent toward +x (away from it), so that
    # ax-ax = 180 - 2t; the two equatorial ligands subtend eq-eq about +x.
    ax = math.radians(ref.angles.get("ax-ax", 180.0))
    eq = math.radians(ref.angles.get("eq-eq", 120.0))
    t = (math.pi - ax) / 2
    if "ax-eq" in ref.angles:
        # A reference that states the axial-equatorial angle says which way the axial pair bends: toward the lone pair
        # (an ax-eq above 90, as in XeO2F2, where the oxo ligands push the fluorines back) or away from it (below 90).
        if (math.cos(math.radians(ref.angles["ax-eq"])) < 0) != (math.sin(t) * math.cos(eq / 2) < 0):
            t = -t
    return (
        [
            np.array([math.sin(t), 0.0, math.cos(t)]),
            np.array([math.sin(t), 0.0, -math.cos(t)]),
        ],
        [
            np.array([math.cos(eq / 2), math.sin(eq / 2), 0.0]),
            np.array([math.cos(eq / 2), -math.sin(eq / 2), 0.0]),
        ],
    )


def _trigonal_bipyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    eq = [
        np.array([math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0])
        for a in (0, 120, 240)
    ]
    return [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])], eq


def _octahedron(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    v = [
        np.array(p, float)
        for p in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    ]
    return v, []


def _square_pyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # Apical ligand on +z; the four basal ligands at `ax-eq` from it, 90 degrees apart about z. The lone pair sits
    # opposite the apex and pushes the basal bonds TOWARD it, so ax-eq < 90 (BrF5 84.8, IF5 81.9, ClF5 86.5).
    t = math.radians(ref.angles.get("ax-eq", 90.0))
    basal = [
        np.array([math.sin(t) * math.cos(math.radians(p)), math.sin(t) * math.sin(math.radians(p)), math.cos(t)])
        for p in (0, 90, 180, 270)
    ]
    return [np.array([0.0, 0.0, 1.0])], basal


def _pentagonal_bipyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # The IDEAL D5h shape (72 and 90 degrees); the measured puckering and axial bend are averages, not a structure.
    equatorial = [
        np.array([math.cos(math.radians(p)), math.sin(math.radians(p)), 0.0]) for p in (0, 72, 144, 216, 288)
    ]
    return [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])], equatorial


def _pentagonal_planar(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # AX5E2: five ligands in one plane at 72 degrees (the two lone pairs are the two poles), as in XeF5-.
    ring = [np.array([math.cos(math.radians(p)), math.sin(math.radians(p)), 0.0]) for p in (0, 72, 144, 216, 288)]
    return [], ring


def _cs_bipyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # ClF3O: two axial ligands mirror each other across the equatorial plane; two ligands (F and O) lie in that plane
    # `feq-o` apart, and the lone pair is the third equatorial position. Each axial vector (a, b, +-c) is solved from
    # its angle to the in-plane F (`fax-feq`) and to the in-plane O (`fax-o`), so all three published angles hold.
    gamma = math.radians(ref.angles["feq-o"]) / 2
    cos_f, cos_o = math.cos(math.radians(ref.angles["fax-feq"])), math.cos(math.radians(ref.angles["fax-o"]))
    a = (cos_f + cos_o) / (2 * math.cos(gamma))
    b = (cos_f - cos_o) / (2 * math.sin(gamma))
    c = math.sqrt(1.0 - a * a - b * b)
    in_plane_f = np.array([math.cos(gamma), math.sin(gamma), 0.0])
    in_plane_o = np.array([math.cos(gamma), -math.sin(gamma), 0.0])
    return [np.array([a, b, c]), np.array([a, b, -c])], [in_plane_f, in_plane_o]


def _c2v_bipyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # SOF4: the oxygen and two fluorines are equatorial (the oxygen on +x, the fluorines `eq-eq` apart about -x), and
    # the axial pair sits `ax-o` from the oxygen in the plane that holds the oxygen and the axis.
    half = math.radians(ref.angles["eq-eq"]) / 2
    cos_ax_o = math.cos(math.radians(ref.angles["ax-o"]))
    axial = [np.array([cos_ax_o, 0.0, s * math.sqrt(1.0 - cos_ax_o**2)]) for s in (1.0, -1.0)]
    equatorial = [
        np.array([1.0, 0.0, 0.0]),
        np.array([-math.cos(half), math.sin(half), 0.0]),
        np.array([-math.cos(half), -math.sin(half), 0.0]),
    ]
    return axial, equatorial


def _c4v_octahedron(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # SF5Cl: the unique ligand (Cl) on +z, its trans ligand on -z, four basal ligands `ax-eq` from the unique one.
    t = math.radians(ref.angles["ax-eq"])
    basal = [
        np.array([math.sin(t) * math.cos(math.radians(p)), math.sin(t) * math.sin(math.radians(p)), math.cos(t)])
        for p in (0, 90, 180, 270)
    ]
    return [np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])], basal


def _trigonal_pyramid(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # AX3E: three ligands on a cone about the axis, 120 degrees apart about it, the lone pair on the other end of the axis. `l-l` is the angle between any two
    # ligands: for ligands at angle b from the axis, cos(l-l) = (3 cos^2 b - 1) / 2, so cos^2 b = (2 cos(l-l) + 1) / 3 (XeO3 103 degrees, BrO2F 103.8).
    cos_ll = math.cos(math.radians(ref.angles.get("l-l", 109.5)))
    cos_b = math.sqrt(max((2.0 * cos_ll + 1.0) / 3.0, 0.0))
    sin_b = math.sqrt(1.0 - cos_b * cos_b)
    ring = [
        np.array([sin_b * math.cos(math.radians(p)), sin_b * math.sin(math.radians(p)), -cos_b]) for p in (0, 120, 240)
    ]
    return [], ring


def _c3v_octahedron(ref: Reference) -> tuple[list[np.ndarray], list[np.ndarray]]:
    # AX6E, a C3v distorted octahedron (XeF6, Bartell and Gavin's Model C): a triple of LONG bonds around the lone pair's side with mutual angle `l-l` (above 90), and a
    # triple of short bonds on the far side with mutual angle `s-s`, staggered by 60 degrees about the axis. For a triple with mutual angle t each bond makes
    # an angle a with the axis where cos^2 a = (2 cos t + 1) / 3. The returned groups are the long triple (`axial`) and the short triple (`equatorial`).
    def cone(mutual: float) -> float:
        return math.sqrt(max((2.0 * math.cos(math.radians(mutual)) + 1.0) / 3.0, 0.0))

    cos_l, cos_s = cone(ref.angles["l-l"]), cone(ref.angles["s-s"])
    sin_l, sin_s = math.sqrt(1.0 - cos_l**2), math.sqrt(1.0 - cos_s**2)
    long_triple = [
        np.array([sin_l * math.cos(math.radians(p)), sin_l * math.sin(math.radians(p)), cos_l]) for p in (0, 120, 240)
    ]
    short_triple = [
        np.array([sin_s * math.cos(math.radians(p)), sin_s * math.sin(math.radians(p)), -cos_s]) for p in (60, 180, 300)
    ]
    return long_triple, short_triple


#: Layout name -> placer, for the references that name one.
_LAYOUTS = {"cs_bipyramid": _cs_bipyramid, "c2v_bipyramid": _c2v_bipyramid, "c4v_octahedron": _c4v_octahedron}


#: (bonds, lone pairs) -> (classification, shape, placer). XeF6 (a distorted mean structure, not one shape) and
#: every shape with more than seven bonds are not here.
_TEMPLATES = {
    (5, 2): ("AX5E2", "pentagonal planar", _pentagonal_planar),
    (2, 3): ("AX2E3", "linear", _linear),
    (3, 1): ("AX3E", "trigonal pyramidal", _trigonal_pyramid),
    (6, 1): ("AX6E", "C3v distorted octahedron", _c3v_octahedron),
    (3, 2): ("AX3E2", "T-shaped", _t_shape),
    (4, 2): ("AX4E2", "square planar", _square_planar),
    (4, 1): ("AX4E", "seesaw", _seesaw),
    (5, 0): ("AX5", "trigonal bipyramidal", _trigonal_bipyramid),
    (5, 1): ("AX5E", "square pyramidal", _square_pyramid),
    (6, 0): ("AX6", "octahedral", _octahedron),
    (7, 0): ("AX7", "pentagonal bipyramidal", _pentagonal_bipyramid),
}


# --- applicability ------------------------------------------------------------------------------------


def _hypervalent_centre(mol: Any) -> tuple[int, list[int]] | None:
    """The one centre and its ligands, when `mol` has the shape this module is about; else None.

    One connected fragment; every other atom terminal, neutral and singly bonded to the centre (or doubly bonded, for
    an oxygen: an oxo ligand, accepted here only so a lookup can find a measured geometry for it); a formal
    charge only on the centre (an anion such as ClF4- or XeF5-; the charge is drawn on the atom whose
    electrons it changes); the centre's element in the hypervalent table with an EFFECTIVE valence (its
    bonds, less a positive or plus a negative charge, as `checkers.valence` counts it) that is permitted
    and is not the preferred one. Anything else belongs to the ordinary conformer path.
    """
    from openchem.chem.checkers.valence import hypervalent_rules

    n_atoms = mol.GetNumAtoms()
    if n_atoms < 3 or len(_fragments(mol)) != 1:
        return None
    centre = max(mol.GetAtoms(), key=lambda a: a.GetDegree())
    if centre.GetDegree() != n_atoms - 1:
        return None
    ligands = [a.GetIdx() for a in mol.GetAtoms() if a.GetIdx() != centre.GetIdx()]
    for index in ligands:
        atom = mol.GetAtomWithIdx(index)
        bond = mol.GetBondBetweenAtoms(index, centre.GetIdx())
        order = bond.GetBondTypeAsDouble() if bond is not None else 0.0
        if atom.GetDegree() != 1 or atom.GetFormalCharge() or order not in (1.0, 2.0):
            return None
        if order == 2.0 and atom.GetSymbol() != "O":
            return None
    rule = hypervalent_rules().get(centre.GetSymbol())
    effective = _bonding_electrons(centre) - centre.GetFormalCharge()
    if (
        not rule
        or effective not in rule["permitted_valences"]
        or effective == rule["preferred_valence"]
    ):
        return None
    return centre.GetIdx(), ligands


def _bonding_electrons(centre: Any) -> int:
    """The centre's valence as its bonds count it: a double bond counts two."""
    return int(round(sum(b.GetBondTypeAsDouble() for b in centre.GetBonds())))


def _token(mol: Any, centre_index: int, ligand_index: int) -> str:
    """A ligand's element, with "=" for a double bond to the centre ("F", "O=")."""
    bond = mol.GetBondBetweenAtoms(centre_index, ligand_index)
    return mol.GetAtomWithIdx(ligand_index).GetSymbol() + ("=" if bond.GetBondTypeAsDouble() == 2.0 else "")


def _ligand_key(tokens: list[str]) -> str:
    """The `Reference.ligand` string for a set of ligand tokens: the bare element for identical single-bonded ligands."""
    if len(set(tokens)) == 1 and not tokens[0].endswith("="):
        return tokens[0]
    return "".join(sorted(tokens))


def _fragments(mol: Any) -> list[Any]:
    from rdkit import Chem

    return list(Chem.GetMolFrags(mol))


def build_vsepr_geometry(mol: Any) -> VseprOutcome:
    """Coordinates for `mol` if it is a supported hypervalent molecule; see the module docstring for the outcomes.

    `mol` is the Mol of `ChemistryEngine.hypervalent_mol_from_molblock` (or any Mol; it is only read: atoms,
    bonds, charges). The input is never modified.
    """
    found = _hypervalent_centre(mol)
    if found is None:
        return VseprOutcome(
            Kind.NOT_APPLICABLE,
            "not a single hypervalent centre with terminal single bonds",
        )
    centre_index, ligand_indices = found
    centre = mol.GetAtomWithIdx(centre_index)
    symbol, n = centre.GetSymbol(), len(ligand_indices)
    outer = _OUTER_ELECTRONS.get(symbol)
    if outer is None:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            f"no electron count is recorded for the centre element {symbol}",
        )
    charge = centre.GetFormalCharge()
    # The centre's own electrons are its outer shell less the charge it carries (an anion has one more).
    tokens = {i: _token(mol, centre_index, i) for i in ligand_indices}
    has_oxo = any(t.endswith("=") for t in tokens.values())
    left_over = outer - charge - _bonding_electrons(centre)
    lone_pairs, remainder = divmod(left_over, 2)
    ligand = _ligand_key(list(tokens.values()))
    reference = REFERENCES.get((symbol, ligand, n, charge))
    if has_oxo and reference is None:
        # An oxo ligand with no recorded geometry is the ordinary case (a sulfate, a perchlorate, a phosphate): it was
        # never this module's, and stays on the conformer path it was always on.
        return VseprOutcome(Kind.NOT_APPLICABLE, "a double-bonded ligand with no recorded geometry")
    if remainder or lone_pairs < 0 or (n, lone_pairs) not in _TEMPLATES:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            f"{symbol} with {n} ligands and {left_over} left-over electrons has no template here",
        )
    classification, shape, placer = _TEMPLATES[(n, lone_pairs)]
    if reference is None:
        sign = "" if charge == 0 else f" with charge {charge:+d}"
        kinds = sorted(set(tokens.values()))
        if len(kinds) > 1:
            return VseprOutcome(
                Kind.UNSUPPORTED,
                f"mixed ligands ({'/'.join(kinds)}) have no measured geometry for {symbol}{sign}",
            )
        return VseprOutcome(
            Kind.UNSUPPORTED,
            f"no measured geometry is recorded for {symbol}{ligand}{n}{sign}",
        )
    if reference.layout:
        placer = _LAYOUTS[reference.layout]

    axial_vectors, equatorial_vectors = (
        [_VIEW_TILT @ v for v in group] for group in placer(reference)
    )
    vectors = axial_vectors + equatorial_vectors
    if reference.slots:
        lengths = [length for _, length in reference.slots]
        wanted = [token for token, _ in reference.slots]
    else:
        lengths = [reference.axial] * len(axial_vectors) + [reference.equatorial] * len(equatorial_vectors)
        wanted = []
    assert len(vectors) == n, (classification, len(vectors), n)
    # With several kinds of ligand, each slot takes the first unused ligand of its kind (atom order, so deterministic).
    if wanted:
        pool = list(ligand_indices)
        order: list[int] = []
        for token in wanted:
            pick = next((i for i in pool if tokens[i] == token), None)
            if pick is None:
                return VseprOutcome(Kind.UNSUPPORTED, "the ligands do not match the recorded geometry's ligands")
            pool.remove(pick)
            order.append(pick)
    else:
        order = list(ligand_indices)
    coordinates: list[tuple[float, float, float]] = [
        (0.0, 0.0, 0.0)
    ] * mol.GetNumAtoms()
    placed: dict[int, float] = {}
    for index, vector, length in zip(order, vectors, lengths):
        point = vector / np.linalg.norm(vector) * length
        coordinates[index] = (float(point[0]), float(point[1]), float(point[2]))
        placed[index] = length
    geometry = VseprGeometry(
        coordinates=tuple(coordinates),
        centre_index=centre_index,
        ligand_indices=tuple(ligand_indices),
        classification=classification,
        shape=shape,
        axial_indices=tuple(order[: len(axial_vectors)]),
        equatorial_indices=tuple(order[len(axial_vectors) :]),
        reference=reference,
        ligand_lengths=placed,
    )
    problems = validate(geometry)
    if problems:
        return VseprOutcome(
            Kind.UNSUPPORTED,
            "the built geometry failed its own checks: " + "; ".join(problems),
        )
    return VseprOutcome(
        Kind.BUILT,
        geometry=VseprGeometry(
            **{**geometry.__dict__, "diagnostics": _diagnostics(geometry)}
        ),
    )


# --- checks ---------------------------------------------------------------------------------------------


def _diagnostics(geometry: VseprGeometry) -> dict[str, float]:
    points = np.array(geometry.coordinates)
    ligands = [points[i] for i in geometry.ligand_indices]
    angles = [
        math.degrees(
            math.acos(
                np.clip(
                    np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)), -1.0, 1.0
                )
            )
        )
        for i, a in enumerate(ligands)
        for b in ligands[i + 1 :]
    ]
    gaps = [
        np.linalg.norm(a - b) for i, a in enumerate(ligands) for b in ligands[i + 1 :]
    ]
    return {
        "smallest_angle": min(angles),
        "largest_angle": max(angles),
        "closest_ligands": float(min(gaps)),
    }


def validate(geometry: VseprGeometry) -> list[str]:
    """What is wrong with `geometry`, as sentences; empty when it is sound.

    Finite coordinates, the centre at the origin, each centre-ligand distance equal to its reference
    class, ligands not on top of each other, and not all in one point: the checks an angle assertion
    alone would miss.
    """
    problems: list[str] = []
    points = np.array(geometry.coordinates, dtype=float)
    if not np.all(np.isfinite(points)):
        return ["a coordinate is not finite"]
    if np.linalg.norm(points[geometry.centre_index]) > 1e-9:
        problems.append("the centre is not at the origin")
    expected = dict(geometry.ligand_lengths)
    for index, length in expected.items():
        actual = float(np.linalg.norm(points[index]))
        if abs(actual - length) > 1e-6:
            problems.append(
                f"atom {index} is {actual:.4f} A from the centre, not {length:.4f}"
            )
    ligands = [points[i] for i in geometry.ligand_indices]
    for i, a in enumerate(ligands):
        for b in ligands[i + 1 :]:
            if np.linalg.norm(a - b) < 1.5:
                problems.append("two ligands are closer than 1.5 A")
    return problems
