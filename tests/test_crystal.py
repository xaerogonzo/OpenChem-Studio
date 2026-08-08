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


# --- real COD depositions, which is what tests the READER ------------------
#
# The three structures above were keyed in from their papers, so they check
# the arithmetic and not the parsing. These two are files as deposited,
# public domain from the Crystallography Open Database, and they carry the
# things a hand-written CIF never does: multi-line `;` fields, quoted
# values with commas in them, extra _atom_site_ columns, anisotropic and
# geometry loops, tags with slashes in, and negative fractional
# coordinates.
#
#   1504676  Kendall, McDonald, Ferguson & Tykwinski, Org. Lett. 2008,
#            10, 2163 (doi 10.1021/ol800583r) -- a perfluorophenyl-capped
#            polyyne, triclinic P-1
#   7717378  a uranium complex, triclinic P-1, 120 sites
#
# **Each file states its own volume and X-ray density**, computed by the
# depositor's software from the depositor's structure. Reproducing those
# exercises the entire chain at once -- parse, expand, wrap, deduplicate,
# compose, volume, density -- against a number this project did not
# produce.

COD = Path("tests/fixtures/cif")


def _cod(code: str):
    return read_cif((COD / f"{code}.cif").read_text(encoding="utf-8", errors="replace"))


def _stated(code: str, tag: str) -> float:
    import re

    text = (COD / f"{code}.cif").read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"{tag}\s+([\d.]+)", text)
    assert match, f"{tag} not present in {code}"
    return float(match.group(1))


@pytest.mark.parametrize("code", ["1504676", "7717378"])
def test_a_real_deposition_parses_at_all(code):
    crystal = _cod(code)

    assert crystal.space_group == "P -1"
    assert crystal.space_group_number == 2
    assert crystal.sites
    assert len(crystal.operations) == 2


@pytest.mark.parametrize("code", ["1504676", "7717378"])
def test_the_computed_volume_matches_the_one_the_file_states(code):
    """Both cells are TRICLINIC -- all three angles off 90 -- which is the
    shape the orthogonal shortcut cannot fake."""
    crystal = _cod(code)

    assert not crystal.lattice.is_orthogonal
    assert crystal.lattice.volume == pytest.approx(_stated(code, "_cell_volume"), abs=0.05)


@pytest.mark.parametrize("code", ["1504676", "7717378"])
def test_the_computed_density_matches_the_depositors_own(code):
    """**The strongest check in this file.** `_exptl_crystal_density_diffrn`
    was computed by somebody else's software from the same structure, so
    matching it exercises parsing, expansion, wrapping, deduplication,
    composition and volume together against an independent number."""
    crystal = _cod(code)

    assert density(crystal) == pytest.approx(
        _stated(code, "_exptl_crystal_density_diffrn"), abs=0.001
    )


def test_the_polyyne_expands_to_twice_its_asymmetric_unit():
    """P-1 has two operations and no site here sits on the inversion
    centre, so every site doubles -- and the composition must come out at
    Z x the published moiety, C20H5F5."""
    crystal = _cod("1504676")

    assert len(crystal.expand()) == 2 * len(crystal.sites)
    assert crystal.composition() == {"C": 40.0, "H": 10.0, "F": 10.0}
    assert crystal.formula_units_z == 2


def test_an_element_outside_the_organic_set_is_read():
    """The uranium file. An element regex that assumed one or two letters
    of organic chemistry would quietly drop it."""
    assert "U" in _cod("7717378").composition()


def test_negative_fractional_coordinates_wrap_into_the_cell():
    """A deposition writes coordinates in whatever range the refinement
    produced; this file has y = -0.0870 among others. Every one has to
    come back inside the cell."""
    for atom in _cod("1504676").expand():
        for value in atom.position:
            assert 0.0 <= value < 1.0


def test_a_multi_line_text_field_does_not_derail_the_reader():
    """`_publ_section_title` and `_cod_depositor_comments` are `;`-delimited
    blocks running over several lines, one of them containing a bare
    `loop_`-looking indent. Getting this wrong swallows the atom loop."""
    crystal = _cod("1504676")

    assert len(crystal.sites) == 30


def test_a_quoted_value_containing_a_comma_stays_one_token():
    """`'Kendall, Jamie'` is one author, not two. A naive whitespace split
    would not care, but a comma-aware one would break here."""
    from openchem.chem.cif import _tokenise

    assert _tokenise("'Kendall, Jamie' 'McDonald, Robert'") == [
        "Kendall, Jamie",
        "McDonald, Robert",
    ]


@pytest.mark.parametrize("code", ["1504676", "7717378"])
def test_the_fields_the_reader_ignores_are_counted_not_silently_dropped(code):
    """A real deposition is mostly metadata -- 116 and 172 fields here.
    Recording them is what stops the app implying it understood the
    anisotropic displacement parameters it did not read."""
    crystal = _cod(code)

    assert len(crystal.unhandled) > 50
    assert any(tag.startswith("_atom_site_aniso") for tag in crystal.unhandled)


# --- disorder and partial occupancy, in real files --------------------------
#
# The gap the docs named after the first two depositions: both of those
# were fully ordered, so occupancy was covered by synthetic cases only.
# These four are not, and between them they carry every awkward thing the
# reader had been claiming to survive. See tests/fixtures/cif/SOURCES.md
# for provenance and licences -- 1569411 is IUCr-sourced and its use is
# conditional on citing Bravetti et al., IUCrJ 10 (2023) 448.

DISORDERED = ["1511792", "1569411", "1004002", "1502211"]


@pytest.mark.parametrize("code", DISORDERED)
def test_a_disordered_deposition_still_reproduces_its_stated_density(code):
    """**The whole chain, against somebody else's number.** Partial
    occupancies feed straight into the mass, so a file with a 0.42-occupied
    water cannot match unless the occupancy was read, expanded and weighted
    correctly."""
    crystal = _cod(code)

    # Half of the last printed digit. These files give the volume to one
    # decimal -- 1650.9(11), where the (11) is an uncertainty of 1.1 -- so
    # a tighter tolerance would be testing the printout, not the cell.
    assert crystal.lattice.volume == pytest.approx(_stated(code, "_cell_volume"), abs=0.05)
    assert density(crystal) == pytest.approx(
        _stated(code, "_exptl_crystal_density_diffrn"), abs=0.001
    )


@pytest.mark.parametrize("code", DISORDERED)
def test_partial_occupancies_are_read_rather_than_rounded_to_one(code):
    crystal = _cod(code)
    occupancies = {site.occupancy for site in crystal.sites}

    assert any(occupancy < 1.0 for occupancy in occupancies)


def test_a_partly_occupied_water_gives_a_fractional_composition():
    """Leucopterin's O1W refines to 0.4212(76). Rounding that to 1 would
    turn a variable hydrate into a stoichiometric monohydrate, and rounding
    it to 0 would lose the water entirely."""
    composition = _cod("1569411").composition()

    assert composition["O"] != int(composition["O"])
    assert composition["O"] == pytest.approx(12.842, abs=0.01)


def test_the_partly_occupied_water_sits_on_a_special_position():
    """**Deduplication earning its keep on a real structure.** O1W is at
    (1/2, y, 1/4), on the twofold axis of P2/c, so the four operations
    generate only two distinct images. Twenty sites and four operations
    would give 80 atoms if images piled up; the answer is 78."""
    crystal = _cod("1569411")

    assert len(crystal.sites) == 20
    assert len(crystal.operations) == 4
    assert len(crystal.expand()) == 78

    waters = [atom for atom in crystal.expand() if atom.site_label == "O1W"]
    assert len(waters) == 2


def test_matching_the_density_pins_which_of_the_files_own_numbers_is_computed():
    """The file states BOTH `_chemical_formula_sum 'C6 H5.34 N5 O3.17'`
    (giving 12.68 O per cell at Z=4) and a density of 1.888. They are not
    quite consistent: 12.68 O would give 1.882.

    The reading here gives 12.842 O and 1.8878, so it agrees with the
    DENSITY. That is the right one to agree with -- the formula is rounded
    for display, and the file's own remark calls the water content "very
    uncertain". A fixture that only checked the formula string would have
    called this a failure.
    """
    crystal = _cod("1569411")
    from_formula = 4 * 3.17

    assert crystal.composition()["O"] > from_formula
    assert density(crystal) == pytest.approx(1.888, abs=0.001)


def test_an_atom_label_containing_an_apostrophe_does_not_swallow_the_line():
    """**The trap this file exists for.** Disorder alternatives are named
    `N2'`, `C6'`, `H6'1`, and the tokeniser treats `'` as an opening quote
    -- so a naive split would consume the rest of the row and every
    coordinate on it."""
    crystal = _cod("1511792")
    labels = {site.label for site in crystal.sites}

    assert "N2'" in labels
    assert "H6'1" in labels
    assert len(crystal.sites) == 61


def test_two_site_disorder_sums_back_to_the_published_formula():
    """LiDFOB's amine disorders over two positions at 0.897 and 0.103.
    They sum to 1, so the cell composition must come out INTEGER despite
    every contributing site being fractional -- C11 H23 B F2 Li N3 O4 at
    Z = 4."""
    composition = _cod("1511792").composition()

    # **Approximately integer, not exactly.** Summing 0.897 and 0.103
    # ninety-two times accumulates to 91.9999999999999, and asserting
    # exact equality would be asserting a property of binary floating
    # point rather than of the structure.
    expected = {"Li": 4, "B": 4, "C": 44, "N": 12, "O": 16, "F": 8, "H": 92}
    assert set(composition) == set(expected)
    for element, count in expected.items():
        assert composition[element] == pytest.approx(count, abs=1e-9)


def test_a_centred_group_expands_every_site_by_all_eight_operations():
    """C222(1): 186 sites, 8 operations, 1488 atoms, and heavily
    disordered solvent -- five distinct partial occupancies. The largest
    structure here, and the one that would notice an expansion that
    silently truncated."""
    crystal = _cod("1502211")

    assert crystal.space_group == "C 2 2 21"
    assert len(crystal.operations) == 8
    assert len(crystal.expand()) == 8 * len(crystal.sites) == 1488
    assert len({site.occupancy for site in crystal.sites}) > 4


def test_the_modern_space_group_tags_are_read():
    """1569411 uses `_space_group_symop_operation_xyz` and
    `_space_group_name_H-M_alt`; the older files use the `_symmetry_`
    spellings. Reading only one family is a silent way to get an
    unexpanded structure."""
    crystal = _cod("1569411")

    assert crystal.space_group == "P 1 2/c 1"
    assert crystal.space_group_number == 13
    assert len(crystal.operations) == 4


@pytest.mark.parametrize("code", ["1004002", "1502211"])
def test_the_larger_depositions_expand_without_help(code):
    """238 and 186 sites. Nothing here is tuned for small structures, and
    a quadratic step in the expansion would show up first at this size."""
    crystal = _cod(code)

    assert len(crystal.expand()) == len(crystal.operations) * len(crystal.sites)


def test_a_name_field_that_is_a_text_block_yields_a_name_not_a_paragraph():
    """**Found by running the app.** Leucopterin's `_chemical_name_common`
    is a `;` block whose first line is the name and whose remainder is a
    400-character remark about the refinement. The block parser had joined
    those lines with spaces, so the whole paragraph arrived as the
    structure's name and filled the report's Structure row.

    The file's own line structure is what separates them -- there is a
    blank line after the name -- so the fix was to stop destroying it.
    """
    crystal = _cod("1569411")

    assert crystal.name == "Leucopterin (variable hydrate)"
    assert "Remark" not in crystal.name


def test_a_multi_line_text_field_keeps_its_line_structure():
    """The general form of the same thing: a `;` block is text, and its
    newlines mean something."""
    from openchem.chem.cif import _blocks

    text = (COD / "1569411.cif").read_text(encoding="utf-8", errors="replace")
    tags, _loops = next(iter(_blocks(text).values()))

    assert "\n" in tags["_chemical_name_common"]
    assert tags["_chemical_name_common"].splitlines()[0] == "Leucopterin (variable hydrate)"


def test_a_name_the_depositor_truncated_is_reported_as_deposited():
    """1004002 states `_chemical_name_common 'Tungsten sulfide cluster
    with'` -- a fragment, in the file itself. Reading it faithfully is
    right; quietly substituting `_chemical_name_systematic` would be the
    reader deciding it knows better than the deposition."""
    assert _cod("1004002").name == "Tungsten sulfide cluster with"
