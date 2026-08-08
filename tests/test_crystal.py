"""A periodic solid: the cell, its symmetry, and what it expands to.

The spike that preceded this established that the vendored 3Dmol will
render a CIF but will not wrap into the cell, so everything here that
looks like duplicated effort is the half 3Dmol does not do.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from openchem.chem.cif import CifError, element_of, parse_number, read_cif
from openchem.chem.crystal_analysis import (
    CrystalAnalysisError,
    conversion_determinant,
    coordination_shell,
    density,
)
from openchem.domain.crystal import (
    Crystal,
    Lattice,
    Site,
    parse_symmetry_operation,
)

HALITE_CIF = Path("spikes/crystallography/halite.cif")

#: Cells spanning the crystal systems. The triclinic one is synthetic --
#: its job is to make the general formulae differ from the orthogonal
#: shortcut, not to be a real mineral.
CELLS = [
    ("cubic", Lattice(5.6393, 5.6393, 5.6393)),
    ("tetragonal", Lattice(4.594, 4.594, 2.959)),
    ("monoclinic", Lattice(5.68, 15.18, 6.52, 90, 99.3, 90)),
    ("trigonal", Lattice(4.99, 4.99, 17.06, 90, 90, 120)),
    ("triclinic", Lattice(8.1, 9.3, 10.2, 71.2, 88.4, 68.7)),
]


def _halite() -> Crystal:
    return read_cif(HALITE_CIF.read_text(encoding="utf-8"))


# --- the lattice ------------------------------------------------------------


@pytest.mark.parametrize("name,lattice", CELLS, ids=[c[0] for c in CELLS])
def test_the_volume_equals_the_determinant_of_the_conversion_matrix(name, lattice):
    """**Two computations that share no code.** The volume comes from the
    closed-form triclinic expression; the determinant is built from the
    matrix that actually places atoms. If the matrix is wrong the atoms are
    in the wrong places, and this is what notices.

    Run across every crystal system on purpose: for an orthogonal cell the
    triclinic formula reduces to `abc`, so a cubic-only check cannot tell
    the real formula from a bare multiplication.
    """
    crystal = Crystal(lattice=lattice, sites=(Site("X", "C", (0, 0, 0)),))

    assert conversion_determinant(crystal) == pytest.approx(lattice.volume, rel=1e-12)


def test_an_orthogonal_cell_volume_is_just_the_product():
    assert Lattice(2.0, 3.0, 4.0).volume == pytest.approx(24.0)


def test_a_sheared_cell_holds_less_than_the_product_of_its_edges():
    """The triclinic factor is at most 1, so shearing can only lose
    volume. A formula with a sign error tends to break this."""
    lattice = Lattice(8.1, 9.3, 10.2, 71.2, 88.4, 68.7)

    assert 0 < lattice.volume < 8.1 * 9.3 * 10.2


def test_the_cartesian_convention_is_a_along_x_and_b_in_the_xy_plane():
    """Fixed here rather than left implicit: any rotation of this is
    equally valid crystallography and will not match another program."""
    lattice = Lattice(4.0, 5.0, 6.0, 90, 90, 120)

    ax, ay, az = lattice.to_cartesian(1, 0, 0)
    bx, by, bz = lattice.to_cartesian(0, 1, 0)

    assert (ax, ay, az) == pytest.approx((4.0, 0.0, 0.0))
    assert bz == pytest.approx(0.0)
    assert by != pytest.approx(0.0)


def test_distance_uses_the_minimum_image_when_asked():
    """Two ions on opposite faces are neighbours, not a cell apart."""
    lattice = Lattice(10.0, 10.0, 10.0)

    assert lattice.distance((0.05, 0, 0), (0.95, 0, 0)) == pytest.approx(1.0)
    assert lattice.distance((0.05, 0, 0), (0.95, 0, 0), periodic=False) == pytest.approx(9.0)


# --- symmetry ---------------------------------------------------------------


def test_an_operation_parses_into_a_matrix_and_a_shift():
    operation = parse_symmetry_operation("-x, y+1/2, -z+1/2")

    assert operation.rotation == ((-1, 0, 0), (0, 1, 0), (0, 0, -1))
    assert operation.translation == pytest.approx((0.0, 0.5, 0.5))


def test_thirds_are_parsed_as_fractions_not_decimals():
    """**1/3 is the case that matters.** Writing 0.333 loses enough
    precision that a trigonal structure's atoms miss their symmetry
    partners by more than the position tolerance."""
    operation = parse_symmetry_operation("x-y, x, z+2/3")

    assert operation.translation[2] == pytest.approx(2.0 / 3.0, abs=1e-15)


def test_an_operation_that_mixes_axes_is_parsed():
    """Trigonal and hexagonal groups are full of these."""
    operation = parse_symmetry_operation("x-y,x,z")

    assert operation.rotation == ((1, -1, 0), (1, 0, 0), (0, 0, 1))


def test_a_malformed_operation_is_refused():
    with pytest.raises(ValueError, match="three components"):
        parse_symmetry_operation("x,y")


# --- expansion --------------------------------------------------------------


def test_halite_expands_to_four_sodiums_and_four_chlorides():
    crystal = _halite()

    assert len(crystal.expand()) == 8
    assert crystal.composition() == {"Na": 4.0, "Cl": 4.0}


def test_every_expanded_atom_lands_inside_the_cell():
    """**This is the half 3Dmol does not do.** Measured on this exact
    structure, its expansion left 3 of the 4 chlorides at or outside
    [0, a) -- the right set, the wrong representatives, and useless for
    counting cell contents."""
    for atom in _halite().expand():
        for value in atom.position:
            assert 0.0 <= value < 1.0


def test_the_chlorides_land_on_the_canonical_edge_positions():
    """Rock salt's 4b sites. Getting the SET right but the positions
    translated would still pass a count."""
    crystal = _halite()
    chlorides = {
        tuple(round(v, 6) for v in atom.position)
        for atom in crystal.expand()
        if atom.element == "Cl"
    }

    assert chlorides == {(0.5, 0.5, 0.5), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, 0.0, 0.5)}


def test_coincident_images_collapse_rather_than_piling_up():
    """A site on a special position is mapped onto itself by many
    operations. Without deduplication the full Fm-3m list would give 192
    sodiums where there are 4, so the count is only right BECAUSE
    coincident images collapse."""
    lattice = Lattice(5.0, 5.0, 5.0)
    crystal = Crystal(
        lattice=lattice,
        sites=(Site("Na1", "Na", (0.0, 0.0, 0.0)),),
        # Four ways of writing the identity's effect on the origin.
        operations=tuple(
            parse_symmetry_operation(text)
            for text in ("x,y,z", "-x,-y,-z", "-x,y,-z", "x,-y,-z")
        ),
    )

    assert len(crystal.expand()) == 1


def test_a_coordinate_at_the_cell_boundary_folds_to_zero():
    """**A tolerance, not a modulo.** A coordinate that should be exactly
    1.0 arrives as 0.9999999999 or 1.0000000001; plain `% 1.0` puts the
    same atom at opposite ends of the cell depending on rounding."""
    lattice = Lattice(5.0, 5.0, 5.0)
    crystal = Crystal(
        lattice=lattice,
        sites=(Site("A", "C", (0.9999999999, 1.0000000001, 0.0)),),
    )

    (atom,) = crystal.expand()
    assert atom.position == (0.0, 0.0, 0.0)


def test_occupancy_survives_into_the_composition():
    """A half-occupied site contributes half an atom. Rounding it away
    would turn a solid solution into a stoichiometric compound."""
    crystal = Crystal(
        lattice=Lattice(5.0, 5.0, 5.0),
        sites=(Site("Na1", "Na", (0, 0, 0), occupancy=0.5),),
    )

    assert crystal.composition() == {"Na": 0.5}


# --- the CIF reader ---------------------------------------------------------


def test_the_halite_cif_reads_back_what_it_says():
    crystal = _halite()

    assert crystal.name == "Halite"
    assert crystal.space_group_number == 225
    assert crystal.formula_units_z == 4
    assert crystal.lattice.a == pytest.approx(5.6393)
    assert len(crystal.operations) == 4


@pytest.mark.parametrize(
    "text,expected",
    [("5.6393(2)", 5.6393), ("90", 90.0), ("-0.25", -0.25), ("?", None), (".", None)],
)
def test_standard_uncertainty_is_stripped_not_parsed(text, expected):
    """`5.6393(2)` is 5.6393 with an uncertainty of 2 in the last digit.
    The uncertainty is dropped: a half-propagated uncertainty is worse
    than none, the same call this project made about confidence
    percentages."""
    assert parse_number(text) == expected


@pytest.mark.parametrize(
    "symbol,label,expected",
    [("Na+", "", "Na"), ("O2-", "", "O"), ("Fe2+", "", "Fe"), ("", "Na1", "Na"), ("", "O3", "O")],
)
def test_the_element_is_taken_from_the_symbol_or_the_label(symbol, label, expected):
    """Mineral files often carry only `Na1`, `O3`."""
    assert element_of(symbol, label) == expected


def test_both_spellings_of_the_symmetry_loop_are_read():
    """`_symmetry_equiv_pos_as_xyz` is the older tag and
    `_space_group_symop_operation_xyz` the current one. Reading only one
    is a silent way to get an unexpanded structure."""
    modern = """
data_test
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
loop_
_space_group_symop_operation_xyz
 'x,y,z'
 'x+1/2,y+1/2,z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
 Na1 Na 0.0 0.0 0.0
"""
    assert len(read_cif(modern).operations) == 2


def test_a_quoted_value_with_spaces_survives():
    text = HALITE_CIF.read_text(encoding="utf-8")

    assert read_cif(text).space_group == "F m -3 m"


def test_a_file_with_no_cell_is_refused_by_name():
    with pytest.raises(CifError, match="no usable unit cell"):
        read_cif("data_x\n_chemical_name_mineral 'nothing'\n")


def test_a_file_with_no_atom_sites_is_refused_by_name():
    with pytest.raises(CifError, match="no atom sites"):
        read_cif("data_x\n_cell_length_a 5\n_cell_length_b 5\n_cell_length_c 5\n")


def test_fields_the_reader_does_not_understand_are_recorded_not_dropped():
    """A structure with anisotropic parameters is still worth showing, and
    silently ignoring the fields is how a tool starts implying it
    understood more than it did."""
    text = """
data_test
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
_diffrn_radiation_wavelength 0.71073
_refine_ls_R_factor_all 0.031
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
 Na1 Na 0.0 0.0 0.0
"""
    unhandled = read_cif(text).unhandled

    assert "_diffrn_radiation_wavelength" in unhandled
    assert "_refine_ls_r_factor_all" in unhandled


# --- density and coordination -----------------------------------------------


def test_halite_density_matches_the_measured_value():
    """2.165 g/cm3. This is the check that would catch a wrong cell
    volume, a wrong atom count, or a mishandled occupancy -- all three
    feed it."""
    assert density(_halite()) == pytest.approx(2.165, abs=0.005)


def test_density_falls_with_occupancy():
    full = Crystal(lattice=Lattice(5.0, 5.0, 5.0), sites=(Site("A", "Na", (0, 0, 0)),))
    half = Crystal(
        lattice=Lattice(5.0, 5.0, 5.0),
        sites=(Site("A", "Na", (0, 0, 0), occupancy=0.5),),
    )

    assert density(half) == pytest.approx(density(full) / 2)


@pytest.mark.parametrize("label,partner", [("Na1", "Cl"), ("Cl1", "Na")])
def test_both_halite_sites_are_six_coordinate(label, partner):
    """Octahedral rock salt, and the answer no molecular calculator could
    give: there is no bond in this structure at all."""
    shell = coordination_shell(_halite(), label)

    assert shell.coordination_number == 6
    assert {n.element for n in shell.neighbours} == {partner}
    assert shell.mean_distance == pytest.approx(2.8197, abs=1e-3)


def test_the_shell_reports_how_clear_cut_it_was():
    """41% between the first shell and the second. A structure where that
    gap is small is one where the coordination number is genuinely
    arguable, and the caller deserves to know which they have."""
    shell = coordination_shell(_halite(), "Na1")

    assert shell.gap_fraction > 0.35
    assert shell.is_clear_cut


def test_coordination_is_reported_per_site_not_per_atom():
    """Halite's four chlorides are one crystallographic site with one
    answer; listing them separately would imply four measurements of the
    same thing."""
    crystal = _halite()

    assert {site.label for site in crystal.sites} == {"Na1", "Cl1"}
    assert len({atom.site_label for atom in crystal.expand()}) == 2


def test_an_unknown_site_is_refused_and_the_real_ones_are_named():
    with pytest.raises(CrystalAnalysisError, match="Na1"):
        coordination_shell(_halite(), "Xx9")


def test_an_absurd_search_radius_is_refused_rather_than_attempted():
    with pytest.raises(CrystalAnalysisError, match="shells of neighbouring cells"):
        coordination_shell(_halite(), "Na1", search_radius=60.0)


def test_a_search_radius_of_half_the_cell_edge_is_NOT_refused():
    """The first version refused exactly this, because it applied the
    minimum-image limit to a search that builds explicit images. It
    refused halite outright -- whose Na-Cl distance IS half the cell edge
    -- which is how the mistake was found."""
    shell = coordination_shell(_halite(), "Na1", search_radius=4.0)

    assert shell.coordination_number == 6


# --- the boundary the plan drew ---------------------------------------------


def test_a_crystal_is_not_a_molecule_and_does_not_inherit_from_one():
    """**No inheritance in either direction.** The overlap is "both have
    atoms", and sharing on that basis obliges every molecular calculator
    to decide what it means for an infinite periodic structure."""
    from openchem.domain.molecule import MoleculeModel

    assert not issubclass(Crystal, MoleculeModel)
    assert not issubclass(MoleculeModel, Crystal)
    assert not set(Crystal.__mro__) & set(MoleculeModel.__mro__) - {object}


def test_the_crystal_domain_model_imports_no_chemistry_toolkit():
    """`domain/` is the layer everything else may depend on, so it stays
    free of RDKit -- the crystal model is arithmetic on a lattice and
    needs nothing else."""
    import ast

    tree = ast.parse(Path("src/openchem/domain/crystal.py").read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not any(name.startswith(("rdkit", "openchem.chem", "openchem.ui")) for name in imported)


def test_the_expansion_is_deterministic():
    """Same input, same order out -- a set would make the render flicker
    between runs and a diff between two structures meaningless."""
    first = _halite().expand()
    second = _halite().expand()

    assert [(a.element, a.position) for a in first] == [
        (b.element, b.position) for b in second
    ]


# --- the report, and the refusal that is half of it -------------------------


def _report():
    from openchem.chem.crystal_report import build_crystal_report

    return build_crystal_report(_halite())


def _labels(report) -> dict[str, str]:
    return {fact.label: fact.display_value for fact in report.facts}


def test_the_report_says_what_the_structure_is_and_how_big_its_cell_is():
    labels = _labels(_report())

    assert labels["Structure"] == "Halite"
    assert labels["Space group"] == "F m -3 m (No. 225)"
    assert "5.6393" in labels["Unit cell"]


def test_the_report_gives_the_cell_contents_not_a_molecular_formula():
    """"Cl 4, Na 4" is a statement about a cell. "NaCl" would be a
    statement about a molecule that does not exist here."""
    assert _labels(_report())["Atoms per unit cell"] == "Cl 4, Na 4"


def test_the_report_carries_the_coordination_of_every_site():
    labels = _labels(_report())

    assert labels["Coordination of Na1"].startswith("6 Cl")
    assert labels["Coordination of Cl1"].startswith("6 Na")


def test_the_coordination_fact_says_it_is_a_judgement():
    """The distances are the measurement; where the shell ends is not."""
    fact = next(f for f in _report().facts if f.label == "Coordination of Na1")

    from openchem.domain.structure_issue import Basis as IssueBasis

    assert fact.basis is IssueBasis.HEURISTIC
    assert any("not a measurement" in text for text in fact.limitations)
    assert any("clear-cut" in text for text in fact.evidence)


def test_the_density_is_marked_as_the_ideal_one():
    """A measured density is lower wherever the real material has
    vacancies, porosity or inclusions, and this cannot see any of them."""
    fact = next(f for f in _report().facts if f.label == "Density")

    assert fact.value == pytest.approx(2.165, abs=0.005)
    assert any("X-ray density of an ideal cell" in text for text in fact.limitations)


def test_the_report_states_that_molecular_descriptors_do_not_apply():
    """**The refusal is half the report.** Otherwise a reader wonders why
    the Properties panel looks empty and assumes something is broken."""
    report = _report()

    assert any("not a molecule" in text for text in report.limitations)
    assert any("does not exist in the material" in text for text in report.assumptions)


def test_the_inapplicable_list_is_read_from_the_registry_not_written_out():
    """So a calculator added tomorrow is covered without anybody
    remembering to come back here -- the same direction that caught two
    panels missing a help topic."""
    from openchem.chem.crystal_report import inapplicable_calculators
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    names = inapplicable_calculators()

    assert len(names) > 10
    registered = {d.display_name for d in CALCULATOR_DEFINITIONS}
    assert set(names) <= registered


def test_the_unhandled_cif_fields_are_surfaced_when_there_are_any():
    from openchem.chem.crystal_report import build_crystal_report

    text = """
data_test
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
_refine_ls_R_factor_all 0.031
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
 Na1 Na 0.0 0.0 0.0
"""
    labels = {f.label for f in build_crystal_report(read_cif(text)).facts}

    assert "Fields not interpreted" in labels


def test_every_reported_string_survives_a_windows_console():
    """The cp1252 rule. Angstrom and degree signs are the obvious way to
    write a cell and neither is safe on a Windows stream."""
    report = _report()

    for fact in report.facts:
        fact.label.encode("cp1252")
        str(fact.display_value).encode("cp1252")
        for text in (*fact.evidence, *fact.limitations, fact.units):
            text.encode("cp1252")


# --- real published structures, which is what a cubic test cannot do --------
#
# The three cells below are the only reason the general formulae are known
# to be right. For an orthogonal cell the triclinic volume expression
# reduces to `abc`, so halite alone cannot tell it from a multiplication.


def test_gypsum_reproduces_its_published_monoclinic_cell_volume():
    """**The first real non-orthogonal check.** Cole & Lancucki,
    *Acta Cryst.* (1974) **B30**, 921, refining gypsum in I2/a:

        a 5.670  b 15.201  c 6.533 A, beta 118 deg 36 min, V 494.37 A^3

    beta is printed in degrees and MINUTES, which is worth reading
    carefully -- 118.36 would be a plausible-looking transcription and is
    wrong by 0.24 degrees.
    """
    beta = 118 + 36 / 60.0
    lattice = Lattice(5.670, 15.201, 6.533, 90.0, beta, 90.0)

    assert lattice.volume == pytest.approx(494.37, abs=0.01)


def test_gypsums_density_follows_from_its_cell_and_contents():
    """4 x CaSO4.2H2O per cell, as the paper states. Needs no atomic
    coordinates -- which is the point: density checks the VOLUME and the
    cell contents, and both are wrong together or right together."""
    beta = 118 + 36 / 60.0
    crystal = Crystal(
        lattice=Lattice(5.670, 15.201, 6.533, 90.0, beta, 90.0),
        formula_units_z=4,
        sites=tuple(
            [Site(f"Ca{i}", "Ca", (0, 0, 0)) for i in range(4)]
            + [Site(f"S{i}", "S", (0, 0, 0)) for i in range(4)]
            + [Site(f"O{i}", "O", (0, 0, 0)) for i in range(24)]
            + [Site(f"H{i}", "H", (0, 0, 0)) for i in range(16)]
        ),
    )

    assert density(crystal) == pytest.approx(2.31, abs=0.01)


def test_low_quartz_reproduces_its_trigonal_cell_volume():
    """Baur, *Z. Kristallogr.* (2009), averaging 18 measurements of low
    quartz at 291 K: P3(1)21, a = 4.9130(1), c = 5.4047(1) A.

    The 120 degree gamma is what makes this different from every
    orthogonal case.
    """
    lattice = Lattice(4.9130, 4.9130, 5.4047, 90.0, 90.0, 120.0)
    closed_form = lattice.a**2 * lattice.c * math.sqrt(3) / 2

    assert lattice.volume == pytest.approx(closed_form, rel=1e-12)
    assert lattice.volume == pytest.approx(112.98, abs=0.01)


def test_low_quartz_density_follows_from_its_wyckoff_multiplicities():
    """Z = 3 is not quoted from anywhere -- it FALLS OUT of the Wyckoff
    positions the paper states, Si in 3a and O in 6c, giving Si3O6."""
    crystal = Crystal(
        lattice=Lattice(4.9130, 4.9130, 5.4047, 90.0, 90.0, 120.0),
        formula_units_z=3,
        sites=tuple(
            [Site(f"Si{i}", "Si", (0, 0, 0)) for i in range(3)]
            + [Site(f"O{i}", "O", (0, 0, 0)) for i in range(6)]
        ),
    )

    assert crystal.composition() == {"Si": 3.0, "O": 6.0}
    assert density(crystal) == pytest.approx(2.65, abs=0.01)


def test_a_real_trigonal_cell_is_thinner_than_its_shortest_edge():
    """**Why the neighbour search measures width and not edge length.**
    Low quartz has edges 4.9130, 4.9130, 5.4047 A and a perpendicular
    width of 4.25 A -- so a search bounded by the shortest EDGE would
    reach further than one shell of images actually covers, and find
    nothing wrong while doing it.
    """
    from openchem.chem.crystal_analysis import _shortest_perpendicular_width

    crystal = Crystal(
        lattice=Lattice(4.9130, 4.9130, 5.4047, 90.0, 90.0, 120.0),
        sites=(Site("Si1", "Si", (0.5301, 0, 0)),),
    )

    width = _shortest_perpendicular_width(crystal)
    assert width == pytest.approx(4.255, abs=0.01)
    assert width < min(crystal.lattice.a, crystal.lattice.b, crystal.lattice.c)


def test_the_conversion_matrix_is_right_for_every_published_cell():
    """det(M) == V, on the real cells rather than only synthetic ones."""
    for lattice in (
        Lattice(5.6393, 5.6393, 5.6393),
        Lattice(5.670, 15.201, 6.533, 90.0, 118 + 36 / 60.0, 90.0),
        Lattice(4.9130, 4.9130, 5.4047, 90.0, 90.0, 120.0),
    ):
        crystal = Crystal(lattice=lattice, sites=(Site("X", "Si", (0, 0, 0)),))
        assert conversion_determinant(crystal) == pytest.approx(lattice.volume, rel=1e-12)
