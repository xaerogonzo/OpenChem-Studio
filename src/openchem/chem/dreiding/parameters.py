"""The DREIDING parameter tables, transcribed from the primary source.

Mayo, Olafson & Goddard, *DREIDING: A Generic Force Field for Molecular
Simulations*, J. Phys. Chem. 1990, 94, 8897-8909.

**EVERY VALUE HERE WAS READ OFF THE RENDERED PAGE, NOT THE PDF'S TEXT
LAYER.** That is not fussiness. The text layer corrupts exactly the field
that must be exact -- the atom-type labels this whole table is keyed on:

    C_3  extracts as  "C.3"        B_3  extracts as  "B?3"
    C_R  extracts as  "C.R"        kcal/mol  as  "keal/mol"

The numbers survive extraction; the labels do not. A silently mistyped
label binds a radius to the wrong hybridisation and produces energies
wrong by a plausible-looking amount, which is this project's worst
failure mode and one it has already paid for once.

## What is DREIDING, exactly

The paper offers several options and names the defaults. Taking the wrong
column produces a different force field that still runs:

    bonds       harmonic (4), NOT Morse -- Morse is DREIDING/M
    angles      harmonic cosine (10a), which the text says is preferred
                over the harmonic-theta form (11)
    torsion     single-term (13)
    inversion   spectroscopic (24)
    vdW         **Lennard-Jones 12-6** -- "We consider the LJ as the
                default and use DREIDING/X6 to denote cases where the
                exponential-6 form is used"
    charges     not included by default

The combination rules are the trap. The paper presents a geometric mean
for R0 (36b) at length, then says plainly: *"for DREIDING we use (36a)
with (36c) as defaults"* -- geometric for the well depth, **ARITHMETIC**
for the radius. The geometric form belongs to X6.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Subtracted from the sum of bond radii, in Angstrom. Equation 6:
#: R0_IJ = R0_I + R0_J - delta.
BOND_RADIUS_CORRECTION = 0.01

#: Equation 7 and Table III. The single-bond force constant, in
#: (kcal/mol)/A^2. A multiple bond of order n uses n times this (9a).
SINGLE_BOND_FORCE_CONSTANT = 700.0

#: Equation 8 and Table III, in kcal/mol. Morse depth for a single bond;
#: order n uses n times this (9b). Only used by DREIDING/M.
SINGLE_BOND_MORSE_DEPTH = 70.0

#: Equation 12 and Table III, in (kcal/mol)/rad^2, "independent of I, J
#: and K" -- one number for every angle in chemistry, which is what
#: "generic" means here.
ANGLE_FORCE_CONSTANT = 100.0

#: Table III, in (kcal/mol)/rad^2, with the equilibrium angle in degrees.
#: X_3 centres get no inversion term at all.
INVERSION_FORCE_CONSTANT = 40.0
INVERSION_PLANAR_ANGLE = 0.0  # X_2, X_R
INVERSION_C31_ANGLE = 54.74  # the implicit-hydrogen united atom


@dataclass(frozen=True)
class ValenceParameters:
    """Table I: one bond radius and one equilibrium angle per atom type."""

    bond_radius: float
    bond_angle: float


#: **TABLE I: Geometric Valence Parameters for DREIDING.**
#: Bond radius in Angstrom, equilibrium bond angle in degrees. Read from
#: the rendered page 8898.
#:
#: The angle of a one-bond type (H_, F_, Cl, Br, I_) is listed as 180 and
#: is never used -- an angle term needs a central atom with two bonds.
VALENCE: dict[str, ValenceParameters] = {
    "H_": ValenceParameters(0.330, 180.0),
    "H___HB": ValenceParameters(0.330, 180.0),
    "H__b": ValenceParameters(0.510, 90.0),
    "B_3": ValenceParameters(0.880, 109.471),
    "B_2": ValenceParameters(0.790, 120.0),
    "C_3": ValenceParameters(0.770, 109.471),
    "C_R": ValenceParameters(0.700, 120.0),
    "C_2": ValenceParameters(0.670, 120.0),
    "C_1": ValenceParameters(0.602, 180.0),
    "N_3": ValenceParameters(0.702, 106.7),
    "N_R": ValenceParameters(0.650, 120.0),
    "N_2": ValenceParameters(0.615, 120.0),
    "N_1": ValenceParameters(0.556, 180.0),
    "O_3": ValenceParameters(0.660, 104.51),
    "O_R": ValenceParameters(0.660, 120.0),
    "O_2": ValenceParameters(0.560, 120.0),
    "O_1": ValenceParameters(0.528, 180.0),
    "F_": ValenceParameters(0.611, 180.0),
    "Al3": ValenceParameters(1.047, 109.471),
    "Si3": ValenceParameters(0.937, 109.471),
    "P_3": ValenceParameters(0.890, 93.3),
    "S_3": ValenceParameters(1.040, 92.1),
    "Cl": ValenceParameters(0.997, 180.0),
    "Ga3": ValenceParameters(1.210, 109.471),
    "Ge3": ValenceParameters(1.210, 109.471),
    "As3": ValenceParameters(1.210, 92.1),
    "Se3": ValenceParameters(1.210, 90.6),
    "Br": ValenceParameters(1.167, 180.0),
    "In3": ValenceParameters(1.390, 109.471),
    "Sn3": ValenceParameters(1.373, 109.471),
    "Sb3": ValenceParameters(1.432, 91.6),
    "Te3": ValenceParameters(1.280, 90.3),
    "I_": ValenceParameters(1.360, 180.0),
    "Na": ValenceParameters(1.860, 90.0),
    "Ca": ValenceParameters(1.940, 90.0),
    "Fe": ValenceParameters(1.285, 90.0),
    "Zn": ValenceParameters(1.330, 109.471),
}


@dataclass(frozen=True)
class VanDerWaalsParameters:
    """Table II: the LJ 12-6 well, plus the X6 scaling parameter."""

    radius: float
    well_depth: float
    #: Zeta, used only by the exponential-6 form. Kept so DREIDING/X6
    #: needs no second transcription of this table.
    scale: float


#: **TABLE II: The van der Waals Parameters for DREIDING.**
#: R0 in Angstrom, D0 in kcal/mol, zeta dimensionless. Rendered page 8899.
#:
#: **Keyed by ELEMENT, not by hybridisation** -- one entry for all of
#: C_3/C_R/C_2/C_1 -- which is a real asymmetry against Table I and is
#: the paper's own design: "we define the van der Waals parameters only
#: for homonuclear cases".
#:
#: The `C_3x`/`C_R1` entries are united atoms carrying implicit
#: hydrogens; they are listed for completeness and are not produced by
#: the typer, which works on explicit structures.
VAN_DER_WAALS: dict[str, VanDerWaalsParameters] = {
    "H": VanDerWaalsParameters(3.195, 0.0152, 12.382),
    "H__b": VanDerWaalsParameters(3.195, 0.0152, 12.382),
    "H___HB": VanDerWaalsParameters(3.195, 0.0001, 12.0),
    "B": VanDerWaalsParameters(4.02, 0.095, 14.23),
    "C": VanDerWaalsParameters(3.8983, 0.0951, 14.034),
    "N": VanDerWaalsParameters(3.6621, 0.0774, 13.843),
    "O": VanDerWaalsParameters(3.4046, 0.0957, 13.483),
    "F": VanDerWaalsParameters(3.4720, 0.0725, 14.444),
    "Al": VanDerWaalsParameters(4.39, 0.31, 12.0),
    "Si": VanDerWaalsParameters(4.27, 0.31, 12.0),
    "P": VanDerWaalsParameters(4.1500, 0.3200, 12.0),
    "S": VanDerWaalsParameters(4.0300, 0.3440, 12.0),
    "Cl": VanDerWaalsParameters(3.9503, 0.2833, 13.861),
    "Ga": VanDerWaalsParameters(4.39, 0.40, 12.0),
    "Ge": VanDerWaalsParameters(4.27, 0.40, 12.0),
    "As": VanDerWaalsParameters(4.15, 0.41, 12.0),
    "Se": VanDerWaalsParameters(4.03, 0.43, 12.0),
    "Br": VanDerWaalsParameters(3.95, 0.37, 12.0),
    "In": VanDerWaalsParameters(4.59, 0.55, 12.0),
    "Sn": VanDerWaalsParameters(4.47, 0.55, 12.0),
    "Sb": VanDerWaalsParameters(4.35, 0.55, 12.0),
    "Te": VanDerWaalsParameters(4.23, 0.57, 12.0),
    "I": VanDerWaalsParameters(4.15, 0.51, 12.0),
    "Na": VanDerWaalsParameters(3.144, 0.5, 12.0),
    "Ca": VanDerWaalsParameters(3.472, 0.05, 12.0),
    "Fe": VanDerWaalsParameters(4.54, 0.055, 12.0),
    "Zn": VanDerWaalsParameters(4.54, 0.055, 12.0),
    # Implicit-hydrogen united atoms.
    "C_R1": VanDerWaalsParameters(4.23, 0.1356, 14.034),
    "C_34": VanDerWaalsParameters(4.2370, 0.3016, 12.0),
    "C_33": VanDerWaalsParameters(4.1524, 0.2500, 12.0),
    "C_32": VanDerWaalsParameters(4.0677, 0.1984, 12.0),
    "C_31": VanDerWaalsParameters(3.9830, 0.1467, 12.0),
}


@dataclass(frozen=True)
class TorsionParameters:
    """A torsion about one central bond: barrier, periodicity, phase.

    `barrier` is the TOTAL over every dihedral sharing the central bond
    -- see `dreiding.torsion_energy`, which divides by that count. Getting
    this wrong is a factor of nine on ethane.
    """

    barrier: float
    periodicity: int
    phase: float


#: **TABLE IV: DREIDING Torsion Parameters for Equivalent Central Atoms.**
#: Rendered page 8900. Keyed by the hybridisation of the two central
#: atoms when both are the same type; the mixed cases are rules, in
#: `dreiding.torsion_for`, from equations 14-23.
#:
#: A barrier of zero means "no torsion term": X_1 centres, monovalent
#: atoms and metals, per equation 20.
TORSION_BY_CENTRAL_ATOM: dict[str, TorsionParameters] = {
    "H_": TorsionParameters(0.0, 0, 0.0),
    # Table IV lists only `H_`, but the other two hydrogen types are
    # equally monovalent and equation 20 covers them: a terminal atom
    # cannot define a dihedral. Present so the table can be iterated
    # against Table I without a hole.
    "H___HB": TorsionParameters(0.0, 0, 0.0),
    "H__b": TorsionParameters(0.0, 0, 0.0),
    "B_3": TorsionParameters(2.0, 3, 180.0),
    "C_3": TorsionParameters(2.0, 3, 180.0),
    "C_R": TorsionParameters(25.0, 2, 180.0),
    "C_2": TorsionParameters(45.0, 2, 180.0),
    "C_1": TorsionParameters(0.0, 0, 0.0),
    "N_3": TorsionParameters(2.0, 3, 180.0),
    "N_R": TorsionParameters(25.0, 2, 180.0),
    "N_2": TorsionParameters(45.0, 2, 180.0),
    "N_1": TorsionParameters(0.0, 0, 0.0),
    # The oxygen column is the exception: n = 2 about 90 degrees, from the
    # p-pi lone pair, which is why HOOH and HSSH sit near 90 rather than
    # anti. Equation 21.
    "O_3": TorsionParameters(2.0, 2, 90.0),
    "O_R": TorsionParameters(25.0, 2, 180.0),
    "O_2": TorsionParameters(45.0, 2, 180.0),
    "O_1": TorsionParameters(0.0, 0, 0.0),
    "F_": TorsionParameters(0.0, 0, 0.0),
    "Al3": TorsionParameters(2.0, 3, 180.0),
    "Si3": TorsionParameters(2.0, 3, 180.0),
    "P_3": TorsionParameters(2.0, 3, 180.0),
    "S_3": TorsionParameters(2.0, 2, 90.0),
    "Cl": TorsionParameters(0.0, 0, 0.0),
    "Ga3": TorsionParameters(2.0, 3, 180.0),
    "Ge3": TorsionParameters(2.0, 3, 180.0),
    "As3": TorsionParameters(2.0, 3, 180.0),
    "Se3": TorsionParameters(2.0, 2, 90.0),
    "Br": TorsionParameters(0.0, 0, 0.0),
    "In3": TorsionParameters(2.0, 3, 180.0),
    "Sn3": TorsionParameters(2.0, 3, 180.0),
    "Sb3": TorsionParameters(2.0, 3, 180.0),
    "Te3": TorsionParameters(2.0, 2, 90.0),
    "I_": TorsionParameters(0.0, 0, 0.0),
    "Na": TorsionParameters(0.0, 0, 0.0),
    "Ca": TorsionParameters(0.0, 0, 0.0),
    "Fe": TorsionParameters(0.0, 0, 0.0),
    "Zn": TorsionParameters(0.0, 0, 0.0),
}

#: Types belonging to the oxygen column (group 16), whose torsions follow
#: equations 21 and 22 rather than the general rules. Named here rather
#: than tested by element so the rule reads as the paper states it.
OXYGEN_COLUMN = frozenset({"O_3", "S_3", "Se3", "Te3"})

#: Hybridisation families, used by the torsion rules.
SP3_TYPES = frozenset(
    t for t in VALENCE if t.endswith("3") or t in {"H_", "F_", "Cl", "Br", "I_"}
)
#: `_R` is DREIDING's resonant suffix. `B_2` does NOT belong here despite
#: being trigonal -- `_2` means sp2 and `_R` means resonant, and boron's
#: empty p orbital is not a filled pi system.
RESONANT_TYPES = frozenset({"C_R", "N_R", "O_R"})
SP2_TYPES = frozenset({"C_2", "N_2", "O_2", "B_2"})
SP1_TYPES = frozenset({"C_1", "N_1", "O_1"})

#: Types in Table I with no row in Table IV. Recorded rather than filled
#: in: inventing a barrier for trigonal boron would be a value with no
#: source, and the general rules of equations 14-23 cover it by
#: hybridisation anyway. `test_every_valence_type_has_a_torsion_entry`
#: allows exactly these, so a NEW gap still fails.
TORSION_TABLE_OMISSIONS = frozenset({"B_2"})


def element_of(atom_type: str) -> str:
    """The van der Waals key for a DREIDING atom type.

    Table II is keyed by ELEMENT while Table I is keyed by type, so this
    is where the two are reconciled. `H___HB` and `H__b` keep their own
    entries because they really are different vdW species -- a
    hydrogen-bonding hydrogen has a well depth of 0.0001 against 0.0152.
    """
    if atom_type in VAN_DER_WAALS:
        return atom_type
    # `C_3` -> `C`, `Al3` -> `Al`, `Cl` -> `Cl`.
    head = atom_type.split("_")[0]
    return head.rstrip("0123456789") or head
