"""Perceiving what a structure represents, not just what it contains.

The cases here are the ones that decide whether this is perception or a
pile of booleans: a salt it should be confident about, a salt-shaped thing
it must REFUSE, a mixture that is neither, and a sandwich complex that an
ionic rule reached first would confidently mislabel.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem

from openchem.chem.substance import (
    GEOMETRY_MATCH_TOLERANCE_DEGREES,
    IRREGULAR,
    _REFERENCE_GEOMETRIES,
    _angle_multiset,
    _rmsd_degrees,
    SubstanceKind,
    classify_coordination_geometry,
    perceive,
)

SODIUM_CHLORIDE = "[Na+].[Cl-]"
CALCIUM_CHLORIDE = "[Ca+2].[Cl-].[Cl-]"
FERROCENE = "[Fe+2].[cH-]1cccc1.[cH-]1cccc1"
METHYLFERROCENE = "[Fe+2].[cH-]1cccc1.Cc1ccc[cH-]1"
FOUR_IONS = "[Na+].[Cl-].[K+].[Br-]"
NEUTRAL_MIXTURE = "CCO.c1ccccc1"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def _perceive(smiles: str):
    return perceive(Chem.MolFromSmiles(smiles))


# --- the confident cases ----------------------------------------------------


def test_sodium_chloride_is_a_one_to_one_ionic_salt():
    """What the app could not say before. Its numbers were all correct --
    formula ClNa, mass 58.443 -- and "Bond count: 0" is true of table salt
    and useless about it."""
    substance = _perceive(SODIUM_CHLORIDE)

    assert substance.kind is SubstanceKind.IONIC_SALT
    assert substance.formula_unit == "Na+ · Cl-"
    assert substance.total_charge == 0
    assert "stoichiometry 1:1" in " ".join(substance.evidence)


def test_calcium_chloride_counts_its_two_chlorides():
    """Identical components collapse to a count: CaCl2 is one Ca2+ and two
    Cl-, not three unrelated fragments."""
    substance = _perceive(CALCIUM_CHLORIDE)

    assert substance.kind is SubstanceKind.IONIC_SALT
    assert substance.formula_unit == "Ca2+ · 2 × Cl-"


def test_a_salt_carries_its_evidence():
    """Not a bare verdict. The evidence is what lets a reader disagree."""
    evidence = " | ".join(_perceive(SODIUM_CHLORIDE).evidence)

    assert "charged components" in evidence
    assert "cation Na+" in evidence
    assert "anion Cl-" in evidence


def test_an_ordinary_molecule_is_not_called_a_salt():
    substance = _perceive(ASPIRIN)

    assert substance.kind is SubstanceKind.MOLECULE
    assert substance.associations == ()
    assert substance.coordination is None


# --- the refusal, which is the point ----------------------------------------


def test_four_ions_are_refused_rather_than_guessed():
    """**NaCl + KBr, or NaBr + KCl, or a mixture of four ions.** Nothing in
    the graph decides, so the answer is that it cannot be decided.

    This is what stops the classifier decaying into
    `if charged_components: return "ionic salt"`.
    """
    substance = _perceive(FOUR_IONS)

    assert substance.kind is SubstanceKind.AMBIGUOUS_IONIC
    assert not substance.is_single_substance


def test_the_refusal_keeps_its_reason():
    """"Unknown" would be useless. The reason names what the structure
    fails to encode, which is the actionable half."""
    substance = _perceive(FOUR_IONS)

    assert "does not encode which ions" in substance.reason
    assert "2 distinct cations, 2 distinct anions" in " ".join(substance.evidence)


def test_ambiguous_and_mixture_stay_distinguishable():
    """Different statements: one says the components cannot be paired, the
    other that nothing suggests they are one substance at all. A
    disconnected graph is not one substance merely because its charges
    happen to cancel."""
    ambiguous = _perceive(FOUR_IONS)
    mixture = _perceive(NEUTRAL_MIXTURE)

    assert ambiguous.kind is SubstanceKind.AMBIGUOUS_IONIC
    assert mixture.kind is SubstanceKind.MIXTURE
    assert ambiguous.kind is not mixture.kind


def test_a_neutral_mixture_says_why_it_is_not_one_substance():
    substance = _perceive(NEUTRAL_MIXTURE)

    assert "Nothing in the structure says these are one substance" in substance.reason


# --- organometallic, which an ionic rule would get wrong --------------------


def test_ferrocene_is_organometallic_not_a_salt():
    """**Order matters.** Ferrocene's ionic form is three charged
    fragments whose charges cancel, so an ionic rule reached first would
    confidently call it a 1:2 salt."""
    substance = _perceive(FERROCENE)

    assert substance.kind is SubstanceKind.ORGANOMETALLIC
    assert substance.coordination is not None
    assert substance.coordination.metal_symbol == "Fe"
    assert substance.coordination.oxidation_state == 2


def test_ferrocene_reports_two_named_counts_not_one_coordination_number():
    """**"Coordination number 10" invites the wrong convention** -- it is
    the ten Cp carbons, not ten ligands. Both numbers are named, and
    neither is merged into a single ambiguous figure."""
    coordination = _perceive(FERROCENE).coordination

    assert coordination.ligand_count == 2
    assert coordination.donor_atom_count == 10
    assert [ligand.label for ligand in coordination.ligands] == ["eta5-Cp", "eta5-Cp"]


def test_a_substituted_metallocene_is_still_perceived():
    """The pinned table covers 27 exact structures and returns None for
    anything substituted; the general classifier underneath is what keeps
    methylferrocene from falling through to "ionic salt"."""
    substance = _perceive(METHYLFERROCENE)

    assert substance.kind is SubstanceKind.ORGANOMETALLIC
    labels = [ligand.label for ligand in substance.coordination.ligands]
    assert "eta5-methylCp" in labels


def test_perception_does_not_depend_on_the_namer_having_a_name():
    """**Classification is not naming.** Ferrocene is pinned and carries a
    name; methylferrocene is not and carries none -- and both are
    classified. A card that collapsed to "unknown" because one source came
    up empty would be worth much less."""
    pinned = _perceive(FERROCENE)
    unpinned = _perceive(METHYLFERROCENE)

    assert pinned.perceived_name == "ferrocene"
    assert unpinned.perceived_name == ""
    assert unpinned.kind is pinned.kind


# --- the four relationships, kept apart -------------------------------------


def test_an_ionic_association_is_not_a_bond():
    """`[Na+].[Cl-]` has no RDKit bond and must not grow one. The
    relationship is between COMPONENTS, and is qualitative."""
    substance = _perceive(SODIUM_CHLORIDE)
    molecule = Chem.MolFromSmiles(SODIUM_CHLORIDE)

    assert molecule.GetNumBonds() == 0
    assert len(substance.associations) == 1
    assert substance.associations[0].kind == "ionic"
    assert "opposite formal charges" in substance.associations[0].evidence


def test_an_association_carries_no_distance():
    """It must never acquire one. A distance between two ions needs a 3D
    structure and is a CONTACT measurement even then -- calling it a bond
    length would be wrong. This is what keeps the model coherent when
    crystals arrive, where the same pair has many distances."""
    association = _perceive(SODIUM_CHLORIDE).associations[0]

    assert not hasattr(association, "distance")
    assert not hasattr(association, "length")


def test_geometry_is_absent_without_a_conformer():
    """**Six things attached does not make something octahedral.** That is
    a claim about angles, and a flat drawing has none."""
    for smiles in (FERROCENE, "[Fe](Cl)(Cl)Cl"):
        substance = _perceive(smiles)
        if substance.coordination is not None:
            assert substance.coordination.geometry is None, smiles


# --- adjacent cases, which is where the category errors were ----------------


def test_a_lone_ion_is_an_ion_not_a_coordination_compound():
    """Found by walking the adjacent case rather than by a test failing:
    `[Na+]` came back as a coordination compound with zero ligands, which
    is a category error rather than a rounding one."""
    substance = _perceive("[Na+]")

    assert substance.kind is SubstanceKind.ION
    assert substance.coordination is None


def test_a_polyatomic_anion_is_an_ion():
    substance = _perceive("[O-]S(=O)(=O)[O-]")

    assert substance.kind is SubstanceKind.ION
    assert substance.total_charge == -2


def test_an_empty_structure_does_not_raise():
    assert perceive(Chem.MolFromSmiles("")).components == ()


# --- the cp1252 rule this project has been bitten by three times ------------


@pytest.mark.parametrize(
    "smiles", [SODIUM_CHLORIDE, CALCIUM_CHLORIDE, FERROCENE, FOUR_IONS, NEUTRAL_MIXTURE]
)
def test_every_reported_string_survives_a_windows_console(smiles):
    """These reach `Fact` values, exports and logs. A cp1252 stream raises
    on a typographic minus or an eta, and this project has hit that three
    times in one session. The pretty forms exist separately, for a UI that
    is not writing to a stream."""
    substance = _perceive(smiles)

    for text in (
        substance.formula_unit,
        substance.reason,
        *substance.evidence,
        *(a.describe() for a in substance.associations),
    ):
        text.encode("cp1252")
    if substance.coordination is not None:
        for ligand in substance.coordination.ligands:
            ligand.label.encode("cp1252")


# --- coordination geometry, measured from real angles -----------------------
#
# Every constant in the classifier was derived rather than chosen, and the
# tests below assert the derivations, not only the outcomes -- a tolerance
# is defensible only while the two bounds that produced it still hold.


def _reference(name: str) -> list[tuple[float, float, float]]:
    return [tuple(float(c) for c in v) for v in _REFERENCE_GEOMETRIES[name]]


def _tris_chelate_octahedron(bite_degrees: float) -> list[tuple[float, float, float]]:
    """Three mutually-cis donor pairs squeezed from 90 deg to `bite`.

    This is what a real tris(bidentate) complex looks like: en and bipy
    both bite at about 78 deg, and tris(ethylenediamine)cobalt(III) is
    octahedral by any account, so the tolerance has to accept it.
    """
    half = bite_degrees / 2
    axes = ((0, 1), (0, 2), (1, 2))
    centres = (45.0, 135.0, 225.0)
    donors = []
    for (i, j), centre in zip(axes, centres):
        for theta in (centre + half, centre - half):
            radians = math.radians(theta)
            vector = [0.0, 0.0, 0.0]
            vector[i] = math.cos(radians)
            vector[j] = math.sin(radians)
            donors.append(tuple(vector))
    return donors


def _complex_molblock(metal: str, donor: str, positions) -> str:
    """A metal with `positions` donors around the origin.

    The header says 3D deliberately: RDKit takes `Is3D()` from it and only
    overrides to 3D when some z is non-zero, so a genuinely PLANAR complex
    -- square planar is flat by definition -- would otherwise be
    indistinguishable from a 2D drawing. Confirmed live in all four
    combinations of header and z-coordinate.
    """
    atoms = [(0.0, 0.0, 0.0, metal)] + [(x, y, z, donor) for x, y, z in positions]
    lines = [
        "geometry fixture", "  OpenChem          3D", "",
        f"{len(atoms):3d}{len(positions):3d}  0  0  0  0            999 V2000",
    ]
    for x, y, z, element in atoms:
        lines.append(f"{x:10.4f}{y:10.4f}{z:10.4f} {element:<3} 0  0")
    for index in range(2, len(atoms) + 1):
        lines.append(f"  1{index:3d}  1  0")
    lines.append("M  END")
    return "\n".join(lines)


def test_every_reference_polyhedron_is_recognised_from_its_own_coordinates():
    """The floor of the whole feature. Built from explicit coordinates
    rather than from an embedding, so the expected answer is known rather
    than whatever the conformer generator happened to produce."""
    for name in _REFERENCE_GEOMETRIES:
        geometry = classify_coordination_geometry((0.0, 0.0, 0.0), _reference(name))
        assert geometry.name == name
        assert geometry.rmsd_degrees == pytest.approx(0.0, abs=1e-9)


def test_five_ninety_degree_angles_do_not_make_it_octahedral():
    """**The donor count must never decide on its own.** A pentagonal
    pyramid has six donors and five angles within 5 deg of 90, which is
    exactly the coincidence a "six donors and some right angles" rule
    would fall for. Measured: 27.5 deg RMSD from octahedral."""
    donors = [(0.0, 0.0, 1.0)] + [
        (math.cos(math.radians(72 * k)), math.sin(math.radians(72 * k)), 0.0)
        for k in range(5)
    ]
    angles = _angle_multiset(donors)
    assert sum(1 for angle in angles if abs(angle - 90) < 5) == 5  # the trap itself

    geometry = classify_coordination_geometry((0.0, 0.0, 0.0), donors)

    assert geometry.name == IRREGULAR
    assert geometry.closest_reference == "octahedral"
    assert geometry.rmsd_degrees > 25


def test_a_tris_chelate_octahedron_is_still_octahedral():
    """The LOWER bound on the tolerance. A 78 deg bite scores 7.58, so any
    tolerance below that would refuse the textbook octahedral complexes."""
    geometry = classify_coordination_geometry(
        (0.0, 0.0, 0.0), _tris_chelate_octahedron(78.0)
    )
    assert geometry.name == "octahedral"
    assert 7.0 < geometry.rmsd_degrees < 8.0


def test_a_squashed_octahedron_is_irregular_and_names_what_it_is_near():
    """Small-bite chelates such as acetate and nitrate reach about 60 deg.
    That is a genuinely distorted polyhedron, and a bare "octahedral"
    would round the distortion away -- so it is irregular WITH the
    deviation, which is a measurement rather than a shrug."""
    geometry = classify_coordination_geometry(
        (0.0, 0.0, 0.0), _tris_chelate_octahedron(60.0)
    )
    assert geometry.name == IRREGULAR
    assert geometry.closest_reference == "octahedral"
    assert "irregular" in geometry.summary
    assert "octahedral" in geometry.summary


def test_the_two_five_donor_geometries_are_told_apart():
    """Trigonal bipyramidal and square pyramidal are the closest pair of
    references anywhere, and the pair a five-donor complex is actually
    asked about."""
    for name in ("trigonal bipyramidal", "square pyramidal"):
        geometry = classify_coordination_geometry((0.0, 0.0, 0.0), _reference(name))
        assert geometry.name == name


def test_the_tolerance_stays_below_half_the_closest_reference_separation():
    """**Guards the constant, not the code.** Two references closer
    together than twice the tolerance could both match, and which one won
    would come down to dict order. Measured: trigonal bipyramidal and
    square pyramidal are 23.24 deg apart, the closest pair. Widening the
    tolerance past half of that fails here, naming the pair."""
    separation, pair = min(
        (
            _rmsd_degrees(_angle_multiset(a_vectors), _angle_multiset(b_vectors)),
            f"{a} vs {b}",
        )
        for a, a_vectors in _REFERENCE_GEOMETRIES.items()
        for b, b_vectors in _REFERENCE_GEOMETRIES.items()
        if a < b and len(a_vectors) == len(b_vectors)
    )

    assert GEOMETRY_MATCH_TOLERANCE_DEGREES < separation / 2, (
        f"{pair} are only {separation:.2f} deg apart, so a tolerance of "
        f"{GEOMETRY_MATCH_TOLERANCE_DEGREES} could match both"
    )


def test_two_donors_modelled_on_one_position_are_not_two_donors():
    """Measured on COD 1511792, the disordered lithium solvate: two
    modelled nitrogen positions of one ligand subtend 14 deg. Without the
    guard that scores as a five-coordinate complex and earns a polyhedron
    name it should not have."""
    donors = [
        (1.0, 0.0, 0.0),
        (math.cos(math.radians(14)), math.sin(math.radians(14)), 0.0),  # the same N
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]

    geometry = classify_coordination_geometry((0.0, 0.0, 0.0), donors)

    assert geometry.name is None
    assert "14" in geometry.note
    assert geometry.angles  # the measurement is still reported


def test_no_reference_polyhedron_is_invented_for_seven_donors():
    """COD 7717378's uranium centre has seven donors. There is no
    reference at that count, and saying so is a different statement from
    "irregular", which would imply a comparison that never happened."""
    donors = [
        (math.cos(math.radians(72 * k)), math.sin(math.radians(72 * k)), 0.0)
        for k in range(5)
    ] + [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]

    geometry = classify_coordination_geometry((0.0, 0.0, 0.0), donors)

    assert geometry.name is None
    assert geometry.closest_reference is None
    assert "7 donor atoms" in geometry.note


def test_a_3d_complex_reports_its_geometry_all_the_way_through_perceive():
    """End to end, not only the classifier: a real conformer has to reach
    `Coordination.geometry`."""
    mol = Chem.MolFromMolBlock(
        _complex_molblock(
            "Zn", "Cl",
            [(x * 2.3, y * 2.3, z * 2.3) for x, y, z in _reference("tetrahedral")],
        ),
        sanitize=False,
    )

    substance = perceive(mol)

    assert substance.coordination is not None
    assert substance.coordination.geometry is not None
    assert substance.coordination.geometry.name == "tetrahedral"


def test_a_flat_drawing_gets_no_geometry_even_with_four_donors():
    """The 2D path is unchanged. `GetNumConformers() > 0` is true for
    every drawn structure -- a molblock from the 2D editor always parses
    into one flat conformer -- so the check has to be `Is3D()`, and a
    drawing gets no geometry at all rather than a confident square
    planar."""
    flat = _complex_molblock(
        "Pt", "Cl", [(2.3, 0, 0), (-2.3, 0, 0), (0, 2.3, 0), (0, -2.3, 0)]
    )
    mol = Chem.MolFromMolBlock(flat.replace("          3D", "          2D"), sanitize=False)
    assert not mol.GetConformer().Is3D()

    substance = perceive(mol)

    assert substance.coordination is not None
    assert substance.coordination.geometry is None


def test_the_geometry_summary_survives_a_windows_console():
    """Same rule as the labels above: this reaches a `Fact`'s
    display_value, exports and logs."""
    classify_coordination_geometry(
        (0.0, 0.0, 0.0), _reference("octahedral")
    ).summary.encode("cp1252")
    classify_coordination_geometry(
        (0.0, 0.0, 0.0), _tris_chelate_octahedron(60.0)
    ).summary.encode("cp1252")
