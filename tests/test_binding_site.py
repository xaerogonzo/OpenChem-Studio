"""Boxing a bound ligand, checked against geometry with a known answer.

Every fixture here is hand-built with column-exact PDB records so the
expected centre and extent are arithmetic rather than something read off
a real structure. The multi-copy cases are the ones that matter: they are
where this went wrong against real deposits.
"""

from __future__ import annotations

import pytest

from openchem.chem.binding_site import (
    MAXIMUM_SIZE,
    MINIMUM_SIZE,
    BindingSiteError,
    box_from_ligand,
    ligand_codes_in,
)


def _hetatm(serial, name, code, chain, resnum, x, y, z, element, altloc=" "):
    """One column-exact HETATM record. The columns are load-bearing --
    a mis-aligned fixture parses as a different residue entirely, which
    has caught this suite out before."""
    return (
        f"HETATM{serial:>5d} {name:<4}{altloc}{code:>3} {chain}{resnum:>4d}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00 20.00          {element:>2}\n"
    )


def _structure(lines):
    return "HEADER    TEST\n" + "".join(lines) + "END\n"


# A ligand spanning exactly 10 x 4 x 2 A, centred on (5, 2, 1).
SIMPLE = _structure([
    _hetatm(1, "C1", "LIG", "A", 500, 0.0, 0.0, 0.0, "C"),
    _hetatm(2, "C2", "LIG", "A", 500, 10.0, 4.0, 2.0, "C"),
    _hetatm(3, "C3", "LIG", "A", 500, 5.0, 2.0, 1.0, "C"),
    _hetatm(4, "N1", "LIG", "A", 500, 3.0, 1.0, 0.5, "N"),
    _hetatm(5, "O1", "LIG", "A", 500, 7.0, 3.0, 1.5, "O"),
    _hetatm(6, "O2", "LIG", "A", 500, 2.0, 2.0, 1.0, "O"),
    _hetatm(7, "CA", "ALA", "A", 1, 40.0, 40.0, 40.0, "C"),
])


def test_the_box_is_centred_on_the_ligand():
    site = box_from_ligand(SIMPLE, "pdb", "LIG")

    assert site.atom_count == 6
    assert site.box.center == pytest.approx((5.0, 2.0, 1.0))
    assert site.extent == pytest.approx((10.0, 4.0, 2.0))


def test_the_centre_is_the_bounding_box_midpoint_not_the_atom_mean():
    """A ligand with more atoms at one end must still be boxed about its
    geometric middle. Using the mean would pull the centre toward the
    crowded end and push the sparse end against the box wall."""
    lopsided = _structure([
        _hetatm(1, "C1", "LIG", "A", 1, 0.0, 0.0, 0.0, "C"),
        _hetatm(2, "C2", "LIG", "A", 1, 0.5, 0.0, 0.0, "C"),
        _hetatm(3, "C3", "LIG", "A", 1, 1.0, 0.0, 0.0, "C"),
        _hetatm(4, "C4", "LIG", "A", 1, 1.5, 0.0, 0.0, "C"),
        _hetatm(5, "C5", "LIG", "A", 1, 20.0, 0.0, 0.0, "C"),
    ])

    site = box_from_ligand(lopsided, "pdb", "LIG")

    assert site.box.center[0] == pytest.approx(10.0), "midpoint of 0..20"
    # The mean of those five x values is 4.6 -- markedly different.
    assert site.box.center[0] != pytest.approx(4.6)


def test_padding_is_added_to_both_sides():
    site = box_from_ligand(SIMPLE, "pdb", "LIG", padding=10.0)

    # 10 A span + 10 either side = 30, above the 16 A floor so unclamped.
    assert site.box.size[0] == pytest.approx(30.0)


def test_a_small_ligand_still_gets_a_usable_box():
    """GABA is the real case: a few heavy atoms across. Its own extent
    plus padding is too tight for a drug-sized molecule to be placed in,
    so the floor is what makes that catalogue entry work at all."""
    tiny = _structure([
        _hetatm(1, "N1", "ABU", "A", 1, 0.0, 0.0, 0.0, "N"),
        _hetatm(2, "C1", "ABU", "A", 1, 1.0, 0.0, 0.0, "C"),
    ])

    site = box_from_ligand(tiny, "pdb", "ABU")

    assert site.box.size == pytest.approx((MINIMUM_SIZE,) * 3)
    assert site.size_was_clamped


def test_an_unclamped_box_says_so():
    assert not box_from_ligand(SIMPLE, "pdb", "LIG", padding=10.0).size_was_clamped
    assert box_from_ligand(SIMPLE, "pdb", "LIG", padding=1.0).size_was_clamped


def test_a_missing_ligand_code_raises_rather_than_boxing_nothing():
    """The dangerous failure is a box centred at the origin: it docks into
    empty space and returns poses that look like results."""
    with pytest.raises(BindingSiteError, match="ZZZ"):
        box_from_ligand(SIMPLE, "pdb", "ZZZ")


# --- multi-copy handling: where this failed against real structures ---

# Two copies of the same ligand, 60 A apart, both numbered 600 and told
# apart ONLY by chain. This is 1ERE's arrangement (six estradiols, all
# residue 600, chains A-F), and it is why residue number alone is not
# enough to separate copies.
TWO_CHAINS = _structure([
    _hetatm(1, "C1", "EST", "A", 600, 0.0, 0.0, 0.0, "C"),
    _hetatm(2, "C2", "EST", "A", 600, 4.0, 0.0, 0.0, "C"),
    _hetatm(3, "C3", "EST", "A", 600, 2.0, 3.0, 0.0, "C"),
    _hetatm(4, "C1", "EST", "B", 600, 60.0, 0.0, 0.0, "C"),
    _hetatm(5, "C2", "EST", "B", 600, 64.0, 0.0, 0.0, "C"),
    _hetatm(6, "C3", "EST", "B", 600, 62.0, 3.0, 0.0, "C"),
])


def test_copies_in_different_chains_are_not_merged():
    """The 1ERE bug. Six estradiols sharing residue number 600 were merged
    into a single 120-atom 'ligand' spanning the whole structure, giving a
    40 A box centred in solvent between the copies -- pointed at nothing,
    and still returning scored poses."""
    site = box_from_ligand(TWO_CHAINS, "pdb", "EST")

    assert site.atom_count == 3, "one copy, not both"
    assert site.extent[0] == pytest.approx(4.0), "one copy spans 4 A, not 64"
    # The centre must be ON a copy, not in the gap between them.
    assert site.box.center[0] == pytest.approx(2.0) or site.box.center[0] == pytest.approx(62.0)
    assert site.box.center[0] != pytest.approx(32.0), "the empty midpoint"


def test_the_larger_copy_wins_when_one_is_partly_resolved():
    """A partly-modelled copy defines the site worse than a complete one."""
    uneven = _structure([
        _hetatm(1, "C1", "LIG", "A", 1, 0.0, 0.0, 0.0, "C"),
        _hetatm(2, "C2", "LIG", "A", 1, 1.0, 0.0, 0.0, "C"),
        _hetatm(3, "C1", "LIG", "B", 1, 50.0, 0.0, 0.0, "C"),
        _hetatm(4, "C2", "LIG", "B", 1, 51.0, 0.0, 0.0, "C"),
        _hetatm(5, "C3", "LIG", "B", 1, 52.0, 0.0, 0.0, "C"),
        _hetatm(6, "C4", "LIG", "B", 1, 53.0, 0.0, 0.0, "C"),
    ])

    site = box_from_ligand(uneven, "pdb", "LIG")

    assert site.atom_count == 4
    assert site.box.center[0] == pytest.approx(51.5), "the four-atom copy in chain B"


def test_the_same_structure_always_gives_the_same_box():
    """Determinism matters: a box that varies run to run makes a docking
    result irreproducible for reasons nothing records."""
    boxes = {tuple(box_from_ligand(TWO_CHAINS, "pdb", "EST").box.center) for _ in range(5)}

    assert len(boxes) == 1


def test_alternate_locations_are_not_counted_twice():
    """8ZYO's astemizole is one 34-atom molecule refined in two
    conformations; read unfiltered it is 34 atoms at A plus 34 at B, and
    both the atom count and the box grow to cover the pair."""
    with_altlocs = _structure([
        _hetatm(1, "C1", "XB7", "D", 1101, 0.0, 0.0, 0.0, "C", altloc="A"),
        _hetatm(2, "C1", "XB7", "D", 1101, 0.4, 0.2, 0.0, "C", altloc="B"),
        _hetatm(3, "C2", "XB7", "D", 1101, 5.0, 0.0, 0.0, "C", altloc="A"),
        _hetatm(4, "C2", "XB7", "D", 1101, 5.3, 0.1, 0.0, "C", altloc="B"),
    ])

    site = box_from_ligand(with_altlocs, "pdb", "XB7")

    assert site.atom_count == 2, "conformation A only"


def test_a_box_never_exceeds_the_ceiling():
    huge = _structure([
        _hetatm(1, "C1", "LIG", "A", 1, 0.0, 0.0, 0.0, "C"),
        _hetatm(2, "C2", "LIG", "A", 1, 200.0, 200.0, 200.0, "C"),
    ])

    site = box_from_ligand(huge, "pdb", "LIG")

    assert site.box.size == pytest.approx((MAXIMUM_SIZE,) * 3)
    assert site.size_was_clamped


# --- listing what a structure actually contains ---


def test_ligand_codes_exclude_protein_and_water():
    """"What is bound here" must not answer with the amino acids. The
    first version did, because it only filtered water, and a list starting
    ILE, LEU, PHE is useless for picking a site."""
    mixed = _structure([
        _hetatm(1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0, "C"),
        _hetatm(2, "CB", "ILE", "A", 2, 1.0, 0.0, 0.0, "C"),
        _hetatm(3, "O", "HOH", "A", 900, 2.0, 0.0, 0.0, "O"),
        _hetatm(4, "O", "HOH", "A", 901, 3.0, 0.0, 0.0, "O"),
        _hetatm(5, "O", "HOH", "A", 902, 4.0, 0.0, 0.0, "O"),
        _hetatm(6, "C1", "LIG", "A", 600, 5.0, 0.0, 0.0, "C"),
        _hetatm(7, "C2", "LIG", "A", 600, 6.0, 0.0, 0.0, "C"),
        _hetatm(8, "S", "SO4", "A", 700, 7.0, 0.0, 0.0, "S"),
    ])

    codes = ligand_codes_in(mixed, "pdb")

    assert "ALA" not in codes and "ILE" not in codes
    assert "HOH" not in codes, "three waters would otherwise outrank the ligand"
    assert codes[0] == "LIG", "largest non-protein component first"
    assert "SO4" in codes, "buffer components are still listed, just ranked lower"
