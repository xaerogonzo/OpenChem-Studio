"""DREIDING, checked against the numbers the paper computed with it.

**This is the unusual thing about validating DREIDING: the paper prints
its OWN calculated values**, so reproducing them tests the implementation
with no ambiguity left over. Against experiment, a disagreement could be
a bad implementation or a bad force field; against Table XI it can only be
the implementation.

The gate is ethane. Its 2.896 kcal/mol barrier exercises nearly the whole
force field at once -- bond radii, the angle term, the torsion barrier AND
its renormalisation, and the van der Waals term with its combination
rules -- so a single number failing is a real signal and a single number
passing is a lot of evidence.

Mayo, Olafson & Goddard, J. Phys. Chem. 1990, 94, 8897-8909.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.chem.dreiding import UntypedAtomError, assign_types, atom_type, dreiding_energy
from openchem.chem.dreiding.energy import torsion_for
from openchem.chem.dreiding.parameters import (
    TORSION_TABLE_OMISSIONS,
    TORSION_BY_CENTRAL_ATOM,
    VALENCE,
    VAN_DER_WAALS,
    element_of,
)

#: Table XI, the DREIDING column. Experiment is in the paper beside it and
#: is deliberately NOT what is asserted -- see the module docstring.
ETHANE_BARRIER = 2.896


def _ethane(dihedral_deg: float, cc: float, ch: float, angle_deg: float) -> Chem.Mol:
    """Ethane built analytically at a given geometry.

    Built rather than embedded because the point is to place it at
    DREIDING's OWN ideal geometry and see the valence terms vanish, which
    an embedder's approximate coordinates could not show.
    """
    angle = math.radians(angle_deg)
    rw = Chem.RWMol()
    for _ in range(2):
        rw.AddAtom(Chem.Atom(6))
    for _ in range(6):
        rw.AddAtom(Chem.Atom(1))
    rw.AddBond(0, 1, Chem.BondType.SINGLE)
    for h in (2, 3, 4):
        rw.AddBond(0, h, Chem.BondType.SINGLE)
    for h in (5, 6, 7):
        rw.AddBond(1, h, Chem.BondType.SINGLE)
    mol = rw.GetMol()
    Chem.SanitizeMol(mol)

    conformer = Chem.Conformer(8)
    conformer.SetAtomPosition(0, Point3D(0, 0, 0))
    conformer.SetAtomPosition(1, Point3D(0, 0, cc))
    # NEGATIVE z: each methyl's hydrogens point AWAY from the other carbon.
    # Using the supplement here instead put the two methyls inside one
    # another, for a van der Waals energy of 713860 kcal/mol.
    z, radial = ch * math.cos(angle), ch * math.sin(angle)
    for n, index in enumerate((2, 3, 4)):
        a = 2 * math.pi * n / 3
        conformer.SetAtomPosition(index, Point3D(radial * math.cos(a), radial * math.sin(a), z))
    for n, index in enumerate((5, 6, 7)):
        a = 2 * math.pi * n / 3 + math.radians(dihedral_deg)
        conformer.SetAtomPosition(
            index, Point3D(radial * math.cos(a), radial * math.sin(a), cc - z)
        )
    mol.AddConformer(conformer)
    return mol


def _relaxed(dihedral_deg: float) -> tuple[list[float], float]:
    """Ethane relaxed at a fixed dihedral, over its three free parameters.

    D3d (staggered) and D3h (eclipsed) symmetry means C-C, C-H and the
    H-C-C angle describe each stationary point EXACTLY, so this is a full
    relaxation rather than a restricted one -- which is what makes it
    comparable to the paper's optimised barrier.
    """
    point = [1.530, 1.090, 109.471]
    spans = [(1.40, 1.70), (1.00, 1.20), (105.0, 115.0)]

    def energy(values: list[float]) -> float:
        return dreiding_energy(_ethane(dihedral_deg, *values)).total

    for _ in range(6):
        for axis, (low, high) in enumerate(spans):
            for _step in range(40):
                a, b = low + (high - low) / 3, high - (high - low) / 3
                left, right = list(point), list(point)
                left[axis], right[axis] = a, b
                if energy(left) < energy(right):
                    high = b
                else:
                    low = a
            point[axis] = (low + high) / 2
            spans[axis] = (point[axis] - 0.05, point[axis] + 0.05)
    return point, energy(point)


# --- the gate ----------------------------------------------------------------


def test_ethane_reproduces_the_papers_own_rotational_barrier():
    """**The gate.** DREIDING's published value for ethane is 2.896
    kcal/mol and this must reproduce it, not merely land near it.

    A barrier between OPTIMISED structures, which is what the paper
    reports. Held rigid at the ideal geometry it comes out at 3.170 --
    the eclipsed form relaxes further than the staggered one, and that
    0.27 is the difference between "close" and "the same force field".
    """
    _staggered_geometry, staggered = _relaxed(60.0)
    _eclipsed_geometry, eclipsed = _relaxed(0.0)

    assert eclipsed - staggered == pytest.approx(ETHANE_BARRIER, abs=0.005)


def test_relaxation_lengthens_the_bond_and_opens_the_angle():
    """The barrier is right for the right reason: the eclipsed form pays
    for its torsion by pushing the methyls apart, which is exactly the
    relaxation that brings 3.170 down to 2.896."""
    staggered, _ = _relaxed(60.0)
    eclipsed, _ = _relaxed(0.0)

    assert eclipsed[0] > staggered[0] > 1.530  # C-C past the ideal length
    assert eclipsed[2] > staggered[2] > 109.471  # H-C-C opened


def test_the_ideal_geometry_costs_nothing_in_bonds_or_angles():
    """DREIDING's equilibrium bond length is ADDITIVE -- R0(I) + R0(J) -
    0.01 -- so ethane built at 1.530 A with 109.471 degree angles must
    have exactly zero bond and angle energy.

    This is what a mistyped radius in Table I would break, and nothing
    else here would notice.

    The angle tolerance is 1e-6 rather than 1e-9 because the coordinates
    go through an RDKit conformer, which does not round-trip a double
    exactly; the residual measured 1.8e-8. It is round-trip noise, not a
    parameter that nearly matches -- a wrong angle in Table I is out by
    degrees and shows up as whole kcal/mol.
    """
    breakdown = dreiding_energy(_ethane(60.0, 1.530, 1.090, 109.471))

    assert breakdown.bond == pytest.approx(0.0, abs=1e-9)
    assert breakdown.angle == pytest.approx(0.0, abs=1e-6)


# --- the torsion renormalisation, which is the biggest single trap ------------


def test_the_torsion_barrier_is_shared_among_the_nine_dihedrals():
    """The paper: "for a substituted ethane V_JK = 2.0 kcal/mol and the
    program uses a barrier of V_IJKL = 2/9 for each of the nine
    possibilities of I and L".

    Without that division ethane's torsion barrier is 18, not 2. Asserted
    on the rigid geometry so only the torsion term can be responsible.
    """
    eclipsed = dreiding_energy(_ethane(0.0, 1.530, 1.090, 109.471))
    staggered = dreiding_energy(_ethane(60.0, 1.530, 1.090, 109.471))

    assert staggered.torsion == pytest.approx(0.0, abs=1e-9)
    assert eclipsed.torsion == pytest.approx(2.0, abs=1e-9)


def test_the_van_der_waals_term_supplies_the_rest_of_the_barrier():
    """2.0 of the barrier is torsion and the balance is 1-4 hydrogens
    pressing together. **DREIDING does not scale 1-4 pairs**, unlike
    AMBER and friends, and halving them here would lose most of that."""
    eclipsed = dreiding_energy(_ethane(0.0, 1.530, 1.090, 109.471))
    staggered = dreiding_energy(_ethane(60.0, 1.530, 1.090, 109.471))

    assert eclipsed.van_der_waals - staggered.van_der_waals > 0.5


# --- atom typing -------------------------------------------------------------


@pytest.mark.parametrize(
    ("smiles", "index", "expected"),
    [
        ("CC", 0, "C_3"),
        ("C=C", 0, "C_2"),
        ("C#C", 0, "C_1"),
        ("c1ccccc1", 0, "C_R"),
        ("CCO", 2, "O_3"),
        ("CC=O", 2, "O_2"),
        ("CC#N", 2, "N_1"),
        ("CCN", 2, "N_3"),
        ("CF", 1, "F_"),
        ("CCl", 1, "Cl"),
        ("CS", 1, "S_3"),
    ],
)
def test_hybridisation_is_read_from_the_bonding(smiles, index, expected):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert atom_type(mol.GetAtomWithIdx(index)) == expected


def test_an_amide_nitrogen_is_resonant_not_sp3():
    """Its lone pair conjugates into the carbonyl, so DREIDING calls it
    N_R. RDKit marks it aliphatic, which is why this is decided here
    rather than read off `GetIsAromatic`."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)NC"))
    nitrogen = next(a for a in mol.GetAtoms() if a.GetSymbol() == "N")

    assert atom_type(nitrogen) == "N_R"


def test_a_plain_amine_nitrogen_is_sp3():
    """The counterpart, so the rule above cannot be "every nitrogen"."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCN"))
    nitrogen = next(a for a in mol.GetAtoms() if a.GetSymbol() == "N")

    assert atom_type(nitrogen) == "N_3"


def test_implicit_hydrogens_are_refused_rather_than_ignored():
    """The united-atom types are a different parameterisation, not this
    one with the hydrogens dropped -- so treating an implicit structure
    as explicit would silently drop most of an alkane."""
    with pytest.raises(UntypedAtomError, match="explicit hydrogens"):
        assign_types(Chem.MolFromSmiles("CC"))


def test_an_element_outside_the_table_is_refused():
    """DREIDING covers 37 types and stops. Guessing a radius for a metal
    outside Table I would produce a number with no source."""
    mol = Chem.AddHs(Chem.MolFromSmiles("[Pt]"))

    with pytest.raises(UntypedAtomError, match="37 atom types"):
        assign_types(mol)


# --- the torsion rules, which are ten cases and easy to mis-order ------------


def _bond_between(mol: Chem.Mol, i: int, j: int) -> Chem.Bond:
    return mol.GetBondBetweenAtoms(i, j)


@pytest.mark.parametrize(
    ("name", "smiles", "i", "j", "type_i", "type_j", "expected"),
    [
        ("ethane", "CC", 0, 1, "C_3", "C_3", (2.0, 3, 180.0)),
        ("hydrogen peroxide", "OO", 0, 1, "O_3", "O_3", (2.0, 2, 90.0)),
        ("butadiene middle", "C=CC=C", 1, 2, "C_2", "C_2", (5.0, 2, 180.0)),
        ("ethene", "C=C", 0, 1, "C_2", "C_2", (45.0, 2, 180.0)),
        ("propene single", "C=CC", 1, 2, "C_2", "C_3", (1.0, 6, 0.0)),
        ("benzene", "c1ccccc1", 0, 1, "C_R", "C_R", (25.0, 2, 180.0)),
    ],
)
def test_the_symmetric_cases_route_through_their_own_rule(
    name, smiles, i, j, type_i, type_j, expected
):
    """**These are here because they all silently took the wrong path.**

    The rules were written against `{type_j, type_k}`, a SET, which
    collapses to one element whenever both central atoms are the same
    type -- so every "are both of these sp3" test answered 1, no rule
    matched, and everything fell through to the Table IV fallback.

    Ethane still came out at 2.0 by luck, which is why the barrier gate
    passed while hydrogen peroxide was returning a 3-fold 180-degree
    torsion instead of its 2-fold 90-degree one. A test that only checks
    the symmetric case you happen to care about cannot see this.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    parameters = torsion_for(type_i, type_j, mol.GetBondBetweenAtoms(i, j), mol)

    assert (parameters.barrier, parameters.periodicity, parameters.phase) == expected


def test_a_double_bond_between_sp2_centres_gets_the_45_barrier():
    mol = Chem.AddHs(Chem.MolFromSmiles("C=C"))
    parameters = torsion_for("C_2", "C_2", _bond_between(mol, 0, 1), mol)

    assert (parameters.barrier, parameters.periodicity) == (45.0, 2)


def test_an_aromatic_bond_gets_the_25_barrier():
    mol = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1"))
    parameters = torsion_for("C_R", "C_R", _bond_between(mol, 0, 1), mol)

    assert (parameters.barrier, parameters.periodicity) == (25.0, 2)


def test_biphenyls_central_bond_is_the_exocyclic_exception():
    """Equation 19 is written as an exception to equation 18, so the two
    must be tested in that order -- an exocyclic single bond between two
    aromatic centres gets 10, not 5."""
    mol = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1-c1ccccc1"))
    bridge = next(
        b for b in mol.GetBonds()
        if not b.IsInRing()
        and b.GetBeginAtom().GetIsAromatic()
        and b.GetEndAtom().GetIsAromatic()
    )
    parameters = torsion_for("C_R", "C_R", bridge, mol)

    assert parameters.barrier == 10.0


def test_a_bond_to_a_monovalent_atom_has_no_torsion():
    """Equation 20. A terminal atom cannot define a dihedral, so a
    barrier here would be an artefact."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CF"))
    parameters = torsion_for("C_3", "F_", _bond_between(mol, 0, 1), mol)

    assert parameters.barrier == 0.0


def test_the_oxygen_column_prefers_ninety_degrees():
    """Equation 21, and the reason HOOH and HSSH sit near 90 rather than
    anti: the p-pi lone pair, not sterics."""
    assert TORSION_BY_CENTRAL_ATOM["O_3"].phase == 90.0
    assert TORSION_BY_CENTRAL_ATOM["S_3"].phase == 90.0
    assert TORSION_BY_CENTRAL_ATOM["C_3"].phase == 180.0


# --- the tables themselves ---------------------------------------------------


def test_every_valence_type_has_van_der_waals_parameters():
    """Table I is keyed by atom TYPE and Table II by ELEMENT, and
    `element_of` reconciles them. A type whose element is missing would
    raise deep inside an energy evaluation instead of here.

    This is the guard shape that caught the Drago table refusing 14 of
    its own 24 acids: run a data table against the code that consumes it.
    """
    for atom_type_name in VALENCE:
        assert element_of(atom_type_name) in VAN_DER_WAALS, atom_type_name


def test_every_valence_type_has_a_torsion_entry_or_a_recorded_reason():
    """Table IV omits `B_2`, which is a real gap in the paper rather than
    a transcription slip. It is listed in `TORSION_TABLE_OMISSIONS` so
    the gap is explicit and a NEW one still fails here -- inventing a
    barrier for trigonal boron would be a number with no source."""
    missing = {t for t in VALENCE if t not in TORSION_BY_CENTRAL_ATOM}

    assert missing == set(TORSION_TABLE_OMISSIONS), missing


def test_the_table_has_the_thirty_seven_types_the_paper_lists():
    assert len(VALENCE) == 37


@pytest.mark.parametrize(
    ("atom_type_name", "radius", "angle"),
    [
        # Spot checks against the rendered page, chosen for the labels the
        # PDF's text layer corrupts: C_3 vs C_R vs C_2 differ only in the
        # character that does not survive extraction.
        ("C_3", 0.770, 109.471),
        ("C_R", 0.700, 120.0),
        ("C_2", 0.670, 120.0),
        ("C_1", 0.602, 180.0),
        ("N_3", 0.702, 106.7),
        ("O_3", 0.660, 104.51),
        ("H_", 0.330, 180.0),
    ],
)
def test_table_one_spot_checks(atom_type_name, radius, angle):
    entry = VALENCE[atom_type_name]

    assert entry.bond_radius == radius
    assert entry.bond_angle == angle


def test_the_carbon_van_der_waals_well_is_williams_value():
    """Table II, and the one most likely to be mistyped since four carbon
    TYPES share a single ELEMENT entry."""
    carbon = VAN_DER_WAALS["C"]

    assert (carbon.radius, carbon.well_depth) == (3.8983, 0.0951)


# --- the whole thing on a real molecule --------------------------------------


def test_it_runs_on_an_embedded_drug_molecule():
    """Nothing is asserted about the VALUE -- there is no reference for
    aspirin's DREIDING energy. This asserts only that a real structure
    types and evaluates without raising, which is what a new element or a
    new bonding pattern would break."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol)

    breakdown = dreiding_energy(mol)

    assert math.isfinite(breakdown.total)
    assert breakdown.bond >= 0 and breakdown.angle >= 0 and breakdown.torsion >= 0
