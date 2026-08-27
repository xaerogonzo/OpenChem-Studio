"""A CIF may name its space group and list no operations.

`chem/cif.py` used to answer that with the identity, so the asymmetric
unit was never expanded and every derived quantity was computed about a
structure that had not been built. Measured on halite from a symbol-only
file:

    BEFORE (identity only)   2 atoms/cell   Na1 Cl1   0.5409 g/cm3
    AFTER  (expanded)        8 atoms/cell   Na4 Cl4   2.1637 g/cm3
    halite, measured                                  ~2.17

A factor of four, and **0.54 is a perfectly plausible density** -- which
is what made this silent. The same expansion feeds composition, volume per
formula unit, every coordination shell and the lattice energy.

**ALL SIX SHIPPED COD FIXTURES CARRY A SYMOP LOOP**, so the corpus is
degenerate with respect to exactly this bug and a mutation deleting the
fallback passed. The fixtures here are hand-built for that reason, and
`test_the_fixture_really_has_no_symop_loop` asserts the setup so it cannot
go vacuous the day somebody "tidies" the CIF text.
"""

from __future__ import annotations

import pytest

from openchem.chem.cif import read_cif
from openchem.chem.crystal_analysis import density
from openchem.chem.crystal_report import build_crystal_report
from openchem.chem.space_groups import (
    SpaceGroupSetting,
    Unresolved,
    describe,
    normalise,
    resolve,
)
from openchem.domain.crystal import Lattice

# Halite: Fm-3m, a = 5.64 A, Z = 4. A symbol and NO `_symmetry_equiv_pos_as_xyz`.
HALITE_NO_LOOP = """data_halite
_cell_length_a 5.64
_cell_length_b 5.64
_cell_length_c 5.64
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'F m -3 m'
_cell_formula_units_Z 4
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 Na 0.0 0.0 0.0
Cl1 Cl 0.5 0.5 0.5
"""

HEXAGONAL = Lattice(5.0, 5.0, 17.0, 90.0, 90.0, 120.0)
RHOMBOHEDRAL = Lattice(6.0, 6.0, 6.0, 60.0, 60.0, 60.0)
CUBIC = Lattice(5.64, 5.64, 5.64, 90.0, 90.0, 90.0)


def test_the_fixture_really_has_no_symop_loop():
    """Assert the setup, or every test below could pass vacuously."""
    assert "_symmetry_equiv_pos_as_xyz" not in HALITE_NO_LOOP
    assert "_space_group_symop_operation_xyz" not in HALITE_NO_LOOP
    assert "_symmetry_space_group_name_H-M" in HALITE_NO_LOOP


def test_a_symbol_with_no_loop_now_expands_the_cell():
    """The whole branch, end to end."""
    crystal = read_cif(HALITE_NO_LOOP)
    assert crystal.symmetry_source == "space_group"
    assert len(crystal.operations) == 192
    assert len(crystal.expand()) == 8
    assert crystal.composition() == {"Na": 4.0, "Cl": 4.0}


def test_the_expansion_is_right_because_the_density_says_so():
    """An INDEPENDENT physical check, not a restatement of the count.

    Density is mass over cell volume, so it comes out at halite's measured
    ~2.17 only if the expansion produced the right number of atoms. The
    unexpanded cell gives 0.5409 -- a factor of four out, and a number that
    looks entirely ordinary.
    """
    assert density(read_cif(HALITE_NO_LOOP)) == pytest.approx(2.17, abs=0.02)


def test_a_listed_loop_still_wins_over_the_symbol():
    """The file is authoritative when it speaks. A derived answer is the
    fallback, never an override -- a deposit whose operations disagree with
    its own symbol is describing what it deposited."""
    with_loop = HALITE_NO_LOOP + """
loop_
_symmetry_equiv_pos_as_xyz
x,y,z
-x,-y,-z
"""
    crystal = read_cif(with_loop)
    assert crystal.symmetry_source == "loop"
    assert len(crystal.operations) == 2


# ---------------------------------------------------------------------------
# The rhombohedral seven, resolved by the CELL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol, hexagonal_ops, rhombohedral_ops",
    [("R -3 c", 36, 12), ("R 3", 9, 3), ("R 32", 18, 6), ("R -3", 18, 6)],
)
def test_the_cell_chooses_between_hexagonal_and_rhombohedral_axes(
    symbol, hexagonal_ops, rhombohedral_ops
):
    """Seven groups differ in OPERATION COUNT between their two settings.

    A factor of three in how many atoms the cell holds, and a bare symbol
    does not say which. The cell does, and it is a derivation rather than a
    guess: the `:H` blocks carry the (2/3,1/3,1/3) centring translations
    and the `:R` blocks are primitive.
    """
    from_hex = resolve(symbol, HEXAGONAL)
    from_rho = resolve(symbol, RHOMBOHEDRAL)
    assert isinstance(from_hex, SpaceGroupSetting)
    assert isinstance(from_rho, SpaceGroupSetting)
    assert len(from_hex.operations) == hexagonal_ops
    assert len(from_rho.operations) == rhombohedral_ops
    # Same space group, two axis systems -- not two different groups.
    assert from_hex.it == from_rho.it


def test_a_cell_that_is_neither_refuses_rather_than_picking_one():
    """The control. Without it, "always return the H setting" passes."""
    assert resolve("R -3 c", CUBIC) is Unresolved.AMBIGUOUS_SETTING
    assert resolve("R -3 c", None) is Unresolved.AMBIGUOUS_SETTING


def test_an_origin_choice_is_refused_because_no_cell_can_resolve_it():
    """`I 41/a m d` origin 1 vs 2 share a lattice and differ in coordinates.

    Guessing would put every atom in the wrong place while the cell, the
    formula and the density all still looked right -- which is worse than
    refusing, and is why the cell rule is deliberately not extended here.
    """
    for cell in (CUBIC, HEXAGONAL, None):
        assert resolve("I 41/a m d", cell) is Unresolved.AMBIGUOUS_SETTING


# ---------------------------------------------------------------------------
# Lookup discipline
# ---------------------------------------------------------------------------


def test_the_alias_list_is_split_so_the_common_spelling_resolves():
    """The `hm` field is COMMA-SEPARATED: `P 21/c,P 1 21/c 1`.

    Read as one string the table looks like 541 unique symbols with no
    collisions, and `P 21/c` -- the commonest monoclinic group in
    small-molecule crystallography -- misses entirely.
    """
    for spelling in ("P 21/c", "P21/c", "P 1 21/c 1", "p 2 1 / c"):
        setting = resolve(spelling, CUBIC)
        assert isinstance(setting, SpaceGroupSetting), spelling
        assert setting.it == 14
        assert len(setting.operations) == 4


def test_whitespace_and_case_are_the_only_things_normalised():
    assert normalise("P 21/c") == normalise("p21/C")
    # ...and NOT the symbol itself. These are different space groups.
    assert normalise("P 21/c") != normalise("P 21/n")
    assert resolve("P 21/c", CUBIC).hall != resolve("P 21/n", CUBIC).hall


def test_an_unknown_symbol_fails_closed_and_is_never_fuzzy_matched():
    """`difflib` on a symbol is how `P 21/c` quietly becomes `P 21/n`.

    This project already killed exactly that for solvent names, where it
    paired "1,2-dichloroethane" with "dichloromethane" at equal confidence.
    """
    assert resolve("P2(1)/c", CUBIC) is Unresolved.UNKNOWN_SYMBOL
    assert resolve("not a space group", CUBIC) is Unresolved.UNKNOWN_SYMBOL
    assert resolve("", CUBIC) is Unresolved.UNKNOWN_SYMBOL


def test_the_two_refusals_say_different_things():
    """An unknown symbol and an ambiguous one send a reader elsewhere."""
    unknown = describe(Unresolved.UNKNOWN_SYMBOL, "P2(1)/c")
    ambiguous = describe(Unresolved.AMBIGUOUS_SETTING, "I 41/a m d")
    assert unknown != ambiguous
    assert "not one this table knows" in unknown
    assert "more than one setting" in ambiguous
    # The ambiguous one has to tell the reader what would fix it.
    assert "_symmetry_equiv_pos_as_xyz" in ambiguous


# ---------------------------------------------------------------------------
# What the report says when it could not expand
# ---------------------------------------------------------------------------


def test_an_unexpanded_cell_says_so_on_the_face_of_the_report():
    """Silence here is the original defect. Every number below that row is
    about the asymmetric unit rather than the cell, and all of them look
    ordinary."""
    crystal = read_cif(HALITE_NO_LOOP.replace("'F m -3 m'", "'I 41/a m d'"))
    assert crystal.symmetry_source == "unexpanded"

    report = build_crystal_report(crystal)
    row = next(f for f in report.facts if f.label == "Symmetry operations")
    assert "NOT expanded" in row.display_value
    assert row.limitations and "THE CELL WAS NOT EXPANDED" in row.limitations[0]
    # ...and it must carry the reason, not merely the fact.
    assert "more than one setting" in row.limitations[0]


def test_an_expanded_cell_carries_no_such_warning():
    """The control: the warning must not be unconditional."""
    report = build_crystal_report(read_cif(HALITE_NO_LOOP))
    row = next(f for f in report.facts if f.label == "Symmetry operations")
    assert "NOT expanded" not in row.display_value
    assert not row.limitations
    assert "DERIVED from the space-group symbol" in row.evidence[0]


# ---------------------------------------------------------------------------
# The shipped table
# ---------------------------------------------------------------------------


def test_the_table_covers_every_space_group():
    import json
    from pathlib import Path

    import openchem.chem.space_groups as module

    payload = json.loads(Path(module._TABLE).read_text(encoding="utf-8"))
    numbers = {row["it"] for row in payload["groups"]}
    assert numbers == set(range(1, 231))
    assert len(payload["groups"]) == 541  # 230 groups, plus settings/origins


def test_the_operations_go_through_the_shipped_parser():
    """Never a second parser. `domain.crystal` owns that."""
    setting = resolve("F m -3 m", CUBIC)
    operations = setting.symmetry_operations()
    assert len(operations) == 192
    # And they really operate: the identity must be among them.
    assert any(op.is_identity for op in operations)
