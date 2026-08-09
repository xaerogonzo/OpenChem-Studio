"""Reading the depositor's biological-assembly annotation.

Validated where it counts against RCSB's own API rather than against my
reading of the spec: the parser's `oligomeric_details` matches
`data.rcsb.org`'s for all 49 curated receptors, and the mmCIF and PDB
paths agree on operator applications for all 48 that exist in both
formats. Those runs need the network; the cases below are the specific
constructs that broke on the way there, pinned as fixtures.
"""

from __future__ import annotations

import pytest

from openchem.chem.structure_assembly import (
    AssemblyAnnotation,
    BiologicalAssembly,
    _count_operators,
    parse_assembly,
)


def test_a_looped_assembly_is_read():
    text = """\
#
loop_
_pdbx_struct_assembly.id
_pdbx_struct_assembly.oligomeric_details
_pdbx_struct_assembly.oligomeric_count
1 dimeric 2
2 monomeric 1
#
loop_
_pdbx_struct_assembly_gen.assembly_id
_pdbx_struct_assembly_gen.oper_expression
_pdbx_struct_assembly_gen.asym_id_list
1 1 A,C,D
2 1 A
#
"""
    annotation = parse_assembly(text, "mmcif")

    assert annotation.primary.assembly_id == "1"
    assert annotation.primary.chain_ids == ("A", "C", "D")
    assert annotation.primary.oligomeric_details == "dimeric"


def test_a_single_row_assembly_with_a_multiline_chain_list_is_read():
    """4PE5's shape, and the one that produced NO assembly at all while
    RCSB reported a tetramer.

    The value is a `;`-delimited text field on the lines after a bare tag,
    which is indistinguishable from a loop header unless you use `loop_`
    to tell them apart. It is the same CIF construct `chem/binarycif.py`
    has to WRITE correctly; here it has to be read.
    """
    text = """\
#
_pdbx_struct_assembly.id                   1
_pdbx_struct_assembly.oligomeric_details   tetrameric
#
_pdbx_struct_assembly_gen.assembly_id       1
_pdbx_struct_assembly_gen.oper_expression   1
_pdbx_struct_assembly_gen.asym_id_list
;A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z,AA,BA,CA,DA
;
#
"""
    annotation = parse_assembly(text, "mmcif")

    assert annotation.primary is not None
    assert annotation.primary.oligomeric_details == "tetrameric"
    assert annotation.primary.chain_ids[:3] == ("A", "B", "C")
    assert "DA" in annotation.primary.chain_ids
    assert len(annotation.primary.chain_ids) == 30


def test_operator_applications_accumulate_across_gen_rows():
    """4EA3's shape. Its assembly 1 applies the identity to one chain
    group and a translation to another, written as two rows. Taking the
    maximum per row reported 1 while the PDB file's REMARK 350 reported 2
    for the same deposit; they have to agree."""
    text = """\
#
loop_
_pdbx_struct_assembly_gen.assembly_id
_pdbx_struct_assembly_gen.oper_expression
_pdbx_struct_assembly_gen.asym_id_list
1 1 A,C,D,E,H
1 2 B,F,G,I
2 1 A,C,D,E,H
#
"""
    annotation = parse_assembly(text, "mmcif")

    assert annotation.primary.operator_applications == 2
    assert annotation.primary.needs_generated_copies
    assert set(annotation.primary.chain_ids) == {"A", "B", "C", "D", "E", "F", "G", "H", "I"}


def test_operator_ranges_are_expanded_not_counted_as_one():
    """`1-60` is an icosahedral capsid, not a single transformation."""
    assert _count_operators("1") == 1
    assert _count_operators("1,2,3") == 3
    assert _count_operators("1-60") == 60
    assert _count_operators("(1-60)(61-88)") == 60 * 28
    assert _count_operators("") == 1
    assert _count_operators("?") == 1


def test_remark_350_is_read_from_pdb():
    text = """\
REMARK 350 BIOMOLECULE: 1
REMARK 350 APPLY THE FOLLOWING TO CHAINS: A, B
REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000
REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000
REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
"""
    annotation = parse_assembly(text, "pdb")

    assert annotation.primary.chain_ids == ("A", "B")
    assert annotation.primary.operator_applications == 1
    assert not annotation.primary.needs_generated_copies


def test_a_pdb_assembly_needing_a_generated_partner_is_flagged():
    """4DKL's shape: one chain in the file, a dimer once the second
    operator is applied."""
    text = """\
REMARK 350 BIOMOLECULE: 1
REMARK 350 APPLY THE FOLLOWING TO CHAINS: A
REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000
REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000
REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000
REMARK 350   BIOMT1   2 -1.000000  0.000000  0.000000       14.85678
REMARK 350   BIOMT2   2  0.000000 -1.000000  0.000000        0.00000
REMARK 350   BIOMT3   2  0.000000  0.000000  1.000000      -63.64189
"""
    annotation = parse_assembly(text, "pdb")

    assert annotation.primary.operator_applications == 2
    assert annotation.primary.needs_generated_copies


def test_surplus_chains_are_the_ones_the_assembly_omits():
    annotation = AssemblyAnnotation(
        assemblies=(
            BiologicalAssembly(
                assembly_id="1", chain_ids=("A", "C"), operator_applications=1
            ),
        )
    )

    assert annotation.extra_chains(["A", "B", "C", "D"]) == ("B", "D")


def test_no_annotation_claims_nothing_is_surplus():
    """Absence is normal -- computed models and edited files carry no
    annotation. Treating "unlisted" as "surplus" would invite a user to
    delete chains on the strength of a record that was never there."""
    empty = parse_assembly("data_X\n_entry.id X\n", "mmcif")

    assert empty.primary is None
    assert empty.extra_chains(["A", "B"]) == ()


# --- transformations -------------------------------------------------------
#
# The annotation half of this module only ever COUNTED operators. These
# cover reading them, which is what a builder needs.

_NON_COMMUTING_CIF = """\
data_TEST
loop_
_pdbx_struct_oper_list.id
_pdbx_struct_oper_list.matrix[1][1]
_pdbx_struct_oper_list.matrix[1][2]
_pdbx_struct_oper_list.matrix[1][3]
_pdbx_struct_oper_list.vector[1]
_pdbx_struct_oper_list.matrix[2][1]
_pdbx_struct_oper_list.matrix[2][2]
_pdbx_struct_oper_list.matrix[2][3]
_pdbx_struct_oper_list.vector[2]
_pdbx_struct_oper_list.matrix[3][1]
_pdbx_struct_oper_list.matrix[3][2]
_pdbx_struct_oper_list.matrix[3][3]
_pdbx_struct_oper_list.vector[3]
A 0.0 -1.0 0.0 0.0 1.0 0.0 0.0 0.0 0.0 0.0 1.0 0.0
B 1.0 0.0 0.0 0.0 0.0 0.0 -1.0 0.0 0.0 1.0 0.0 0.0
#
"""


def test_operator_expression_composition_order_is_right_to_left():
    """`(A)(B)` applies B FIRST. Asserted against non-commuting rotations.

    mmCIF defines a product expression so that the right-hand group is
    applied first. The count this module already published is
    order-independent, so nothing before now could catch the order being
    wrong -- and composing the other way round produces a perfectly
    plausible assembly in the wrong place.

    A is +90 degrees about z, B is +90 degrees about x, and they do not
    commute. Hand-calculated for the point (1, 2, 3):

        B(p)        = (1, -3, 2)
        A(B(p))     = (3, 1, 2)     <- (A)(B), the correct reading
        A(p)        = (-2, 1, 3)
        B(A(p))     = (-2, -3, 1)   <- the transposed reading

    A test using two rotations about the same axis would pass either way,
    which is the whole reason these were chosen.
    """
    from openchem.chem.structure_assembly import compose, expand_expression, operator_transforms

    transforms = operator_transforms(_NON_COMMUTING_CIF, "mmcif")
    a, b = transforms["A"], transforms["B"]

    assert b.apply(1, 2, 3) == pytest.approx((1, -3, 2))
    assert a.apply(1, 2, 3) == pytest.approx((-2, 1, 3))

    # The expression is written left-to-right...
    assert expand_expression("(A)(B)") == [("A", "B")]
    # ...and composed right-to-left, so B moves the point first.
    outer, inner = transforms["A"], transforms["B"]
    assert compose(outer, inner).apply(1, 2, 3) == pytest.approx((3, 1, 2))
    # The other order is a different, equally plausible-looking answer.
    assert compose(inner, outer).apply(1, 2, 3) == pytest.approx((-2, -3, 1))


def test_a_wrapped_oper_list_row_is_not_silently_dropped():
    """A loop body is a TOKEN STREAM, not one row per line.

    `_loop_rows` required `len(tokens) == len(names)` on a single physical
    line, so a row wrapped across two lines failed the test and vanished.
    1A34 writes all 60 of its operator rows that way: the category came
    back EMPTY for a 60-operator entry, silently, which is the same shape
    as the 4PE5 case this module already records.
    """
    from openchem.chem.structure_assembly import operator_transforms

    wrapped = _NON_COMMUTING_CIF.replace(
        "A 0.0 -1.0 0.0 0.0 1.0 0.0 0.0 0.0 0.0 0.0 1.0 0.0",
        "A 0.0 -1.0 0.0 0.0 1.0 0.0\n0.0 0.0 0.0 0.0 1.0 0.0",
    )
    assert len(operator_transforms(wrapped, "mmcif")) == 2
    assert operator_transforms(wrapped, "mmcif")["A"].apply(1, 2, 3) == pytest.approx((-2, 1, 3))


def test_an_operator_id_is_a_label_not_a_number():
    """1A34 uses `P` and `X0` beside `1`..`60`. Only a RANGE is numeric."""
    from openchem.chem.structure_assembly import expand_expression

    assert expand_expression("X0") == [("X0",)]
    assert expand_expression("P,X0") == [("P",), ("X0",)]
    assert expand_expression("(X0)(1-3)") == [("X0", "1"), ("X0", "2"), ("X0", "3")]


def test_the_enumerator_and_the_shipped_count_agree():
    """`operator_applications` is published behaviour and must not drift.

    The enumerator replaces the counter, so the count has to remain the
    length of what it enumerates -- for every expression shape the corpus
    contains, including the product with a non-numeric id.
    """
    from openchem.chem.structure_assembly import _count_operators, expand_expression

    for expression in ["1", "1,2,3", "1-60", "(1-60)", "(1-5)", "(X0)(1-10,21-25)", "", "?", "."]:
        assert len(expand_expression(expression)) == _count_operators(expression), expression


def test_a_matrix_that_is_not_a_rotation_is_refused_by_name():
    """Scaling and shearing are not rigid-body placements, and the message
    has to say which operator and why -- somebody is looking at a file
    they did not write."""
    from openchem.chem.structure_assembly import AssemblyError, operator_transforms

    scaled = _NON_COMMUTING_CIF.replace(
        "B 1.0 0.0 0.0 0.0 0.0 0.0 -1.0 0.0 0.0 1.0 0.0 0.0",
        "B 2.0 0.0 0.0 0.0 0.0 2.0 0.0 0.0 0.0 0.0 2.0 0.0",
    )
    with pytest.raises(AssemblyError) as raised:
        operator_transforms(scaled, "mmcif")["B"].validate()
    assert "B" in str(raised.value)


def test_a_reflection_is_reported_rather_than_refused():
    """**No deposit in the corpus contains one**, so this branch is
    untested against real data and says so. Detected rather than refused
    because absence in one corpus is not proof the format forbids it, and
    refusing an operator a depositor wrote is the worse mistake."""
    from openchem.chem.structure_assembly import operator_transforms

    reflected = _NON_COMMUTING_CIF.replace(
        "B 1.0 0.0 0.0 0.0 0.0 0.0 -1.0 0.0 0.0 1.0 0.0 0.0",
        "B -1.0 0.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 0.0 1.0 0.0",
    )
    assert operator_transforms(reflected, "mmcif")["B"].validate() == "reflection"


def test_pdb_biomt_needs_all_three_rows():
    """A matrix missing a row is a broken record, not a 2-D rotation."""
    from openchem.chem.structure_assembly import AssemblyError, operator_transforms

    truncated = (
        "REMARK 350   BIOMT1   2 -1.000000  0.000000  0.000000      -70.88200\n"
        "REMARK 350   BIOMT2   2  0.000000  1.000000  0.000000        0.00000\n"
    )
    with pytest.raises(AssemblyError) as raised:
        operator_transforms(truncated, "pdb")
    assert "BIOMT" in str(raised.value)


# --- building ---------------------------------------------------------------
#
# Synthetic deposits throughout: the real corpus lives outside the repo, and
# a test that needs a downloaded file is a test that does not run in CI.

def _pdb(remark: str, atoms: str, extra: str = "") -> str:
    """A minimal deposit: header, REMARK 350, atoms, trailer."""
    return (
        "HEADER    TEST\n"
        "CRYST1   50.000   50.000   50.000  90.00  90.00  90.00 P 1           1\n"
        + remark
        + atoms
        + extra
        + "MASTER        0    0    0    0    0    0    0    0    2    0    0    0\n"
        "END\n"
    )


#: Identity, then a 180-degree rotation about y with a 10 A shift.
_TWO_OPERATORS = (
    "REMARK 350 BIOMOLECULE: 1\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: A\n"
    "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
    "REMARK 350   BIOMT1   2 -1.000000  0.000000  0.000000       10.00000\n"
    "REMARK 350   BIOMT2   2  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   2  0.000000  0.000000 -1.000000        0.00000\n"
)

_IDENTITY_ONLY = (
    "REMARK 350 BIOMOLECULE: 1\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: A\n"
    "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
)

_ATOMS = (
    "ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00 20.00           N\n"
    "ATOM      2  CA  ALA A   1       4.000   5.000   6.000  1.00 20.00           C\n"
    "HETATM    3 ZN    ZN A 101       7.000   8.000   9.000  1.00 20.00          ZN\n"
)


def _coords(line: str) -> tuple[float, float, float]:
    return float(line[30:38]), float(line[38:46]), float(line[46:54])


def _atom_lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if l.startswith(("ATOM  ", "HETATM"))]


def test_an_assembly_with_no_generated_copies_is_a_no_op():
    """Distinct from the identity test below, and the COMMON path: most
    deposits already hold their biological unit, and asking for it must
    not put them through a rebuild they do not need."""
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(_pdb(_IDENTITY_ONLY, _ATOMS), "pdb")
    assert result.ok
    assert result.generated_copies == 0
    assert result.changed_the_structure is False


def test_the_identity_copy_keeps_its_coordinates_exactly():
    """A transform pipeline can apply the identity and still perturb, via
    formatting or rounding. The deposited coordinate columns must come
    back unchanged, not merely close."""
    from openchem.chem.structure_assembly import build_assembly

    source = _pdb(_TWO_OPERATORS, _ATOMS)
    built = build_assembly(source, "pdb").output_text
    for before, after in zip(_atom_lines(source), _atom_lines(built)):
        assert before[30:54] == after[30:54]


def test_a_generated_copy_lands_where_the_operator_says():
    """Hand-calculated from the fixture: (x, y, z) -> (-x + 10, y, -z)."""
    from openchem.chem.structure_assembly import build_assembly

    produced = _atom_lines(build_assembly(_pdb(_TWO_OPERATORS, _ATOMS), "pdb").output_text)
    assert len(produced) == 6
    assert _coords(produced[3]) == pytest.approx((9.0, 2.0, -3.0))
    assert _coords(produced[5]) == pytest.approx((3.0, 8.0, -9.0))


def test_a_hetatm_travels_with_its_chain():
    """Otherwise the protein assembly is correct and the cofactor is still
    sitting at asymmetric-unit coordinates."""
    from openchem.chem.structure_assembly import build_assembly

    built = build_assembly(_pdb(_TWO_OPERATORS, _ATOMS), "pdb").output_text
    hetatms = [l for l in built.splitlines() if l.startswith("HETATM")]
    assert len(hetatms) == 2, "the zinc was not copied with its chain"
    assert [hetatms[0][21], hetatms[1][21]] == ["A", "B"]


def test_the_deposited_chain_name_survives_the_build():
    """A saved docking box and an excluded chain both address chains BY
    NAME, so the copy sitting where the deposit put it keeps its name and
    only the extra copies get invented ones."""
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(_pdb(_TWO_OPERATORS, _ATOMS), "pdb")
    assert [i.generated_chain_id for i in result.instances] == ["A", "B"]
    assert result.instances[0].is_original
    assert not result.instances[1].is_original


def test_records_that_cannot_survive_a_rebuild_are_dropped():
    """ANISOU would describe the wrong orientation once rotated, MASTER's
    counts go stale, and REMARK 350 would tell the next reader to build
    the thing again."""
    from openchem.chem.structure_assembly import build_assembly, parse_assembly

    anisou = "ANISOU    1  N   ALA A   1     2406   1892   1614      0      0      0       N\n"
    built = build_assembly(_pdb(_TWO_OPERATORS, _ATOMS, anisou), "pdb").output_text
    assert "ANISOU" not in built
    assert "MASTER" not in built
    # Re-entrancy: the output must not re-announce an assembly it already is.
    assert parse_assembly(built, "pdb").assemblies == ()


def test_conect_is_rewritten_to_the_new_serials():
    """Open Babel perceives HETATM bonds from CONECT, so losing it would
    silently change the cofactors and ligands in the receptor. 53 of 56
    corpus deposits carry one."""
    from openchem.chem.structure_assembly import build_assembly

    built = build_assembly(_pdb(_TWO_OPERATORS, _ATOMS, "CONECT    1    2\n"), "pdb").output_text
    records = [l.split() for l in built.splitlines() if l.startswith("CONECT")]
    # 1-3 are the first copy, 4 is its TER -- a TER record consumes a
    # serial number in PDB -- so the second copy starts at 5.
    assert records == [["CONECT", "1", "2"], ["CONECT", "5", "6"]]


def test_every_refusal_names_what_is_wrong_and_returns_nothing():
    """A partial assembly is never returned, and "invalid assembly" is not
    a message anybody can act on."""
    from openchem.chem.structure_assembly import build_assembly

    cases = {
        "no annotation": (_pdb("", _ATOMS), "1", "no biological assembly annotation"),
        "unknown id": (_pdb(_TWO_OPERATORS, _ATOMS), "7", "declares no assembly"),
        "absent chain": (
            _pdb(_TWO_OPERATORS.replace("CHAINS: A", "CHAINS: Z"), _ATOMS),
            "1",
            "does not contain",
        ),
    }
    for label, (text, assembly_id, fragment) in cases.items():
        result = build_assembly(text, "pdb", assembly_id)
        assert not result.ok, label
        assert result.output_text == "", f"{label} returned partial text"
        assert fragment in result.failure_reason, f"{label}: {result.failure_reason}"


def test_an_assembly_too_large_to_dock_is_refused_with_its_size():
    """1A34 really is 60 operators over 3,474 atoms, so the guard is not
    hypothetical -- and the message has to carry the number."""
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(_pdb(_TWO_OPERATORS, _ATOMS), "pdb", atom_limit=4)
    assert not result.ok
    assert result.output_text == ""
    assert "6 atoms" in result.failure_reason


def test_a_built_copy_is_not_mistaken_for_a_crystal_copy():
    """The hazard this whole approach rests on, checked from both ends.

    Receptor preparation DELETES the unit-cell copies Open Babel invents
    for structures whose space group it cannot recognise -- 6WGT's
    8,100-atom deposit once reached Vina as 73,707 atoms. If a built
    assembly's copies looked the same, building one would silently
    produce a receptor with the extra chains stripped straight back out.

    They do not look the same, and the reason is structural rather than
    lucky: `is_symmetry_generated` keys on the copies carrying NO residue
    record, and copies built here are emitted as ordinary ATOM/HETATM
    lines that carry one. Both directions are asserted, because checking
    only that our atoms survive would still pass if the predicate itself
    stopped identifying anything.

    ENVIRONMENT NOTE, measured while writing this: Open Babel here reports
    `Unable to open data file 'space-groups.txt'` and so does not expand
    at all -- 6WGT reads back at its deposited 8,100 atoms. The expansion
    the predicate exists for cannot be reproduced in this environment,
    which is why the "still catches an invented copy" half is asserted
    against the predicate's contract rather than against a live expander.
    """
    from openbabel import pybel

    from openchem.chem.pose_analysis import is_symmetry_generated, receptor_atoms_from_structure
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(_pdb(_TWO_OPERATORS, _ATOMS), "pdb")
    assert result.ok

    molecule = pybel.readstring("pdb", result.output_text)
    assert len(molecule.atoms) == 6
    assert not any(is_symmetry_generated(atom.residue) for atom in molecule.atoms), (
        "a built copy was identified as an invented crystal copy, so preparing "
        "this receptor would delete the assembly it was asked to build"
    )

    # The other end: an atom with no residue record IS one, which is what
    # keeps the assertion above from passing vacuously.
    assert is_symmetry_generated(None)

    # And the whole built assembly survives the real receptor path.
    assert len(receptor_atoms_from_structure(result.output_text, "pdb")) == 6


# --- generation rows, and the id scoping under them -------------------------

#: 4EA3's real shape, with its real numbers: two chain groups inside
#: BIOMOLECULE 1, and a SECOND biomolecule that reuses operator id 2 for a
#: different translation.
_TWO_BIOMOLECULES = (
    "REMARK 350 BIOMOLECULE: 1\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: A\n"
    "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: B\n"
    "REMARK 350   BIOMT1   2  1.000000  0.000000  0.000000       14.85678\n"
    "REMARK 350   BIOMT2   2  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   2  0.000000  0.000000  1.000000      -63.64189\n"
    "REMARK 350 BIOMOLECULE: 2\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: A\n"
    "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: B\n"
    "REMARK 350   BIOMT1   2  1.000000  0.000000  0.000000      -27.24922\n"
    "REMARK 350   BIOMT2   2  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   2  0.000000  0.000000  1.000000      -63.64189\n"
)

_TWO_CHAINS = (
    "ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00 20.00           N\n"
    "ATOM      2  N   ALA B   1       0.000   0.000   0.000  1.00 20.00           N\n"
)


def test_pdb_operator_ids_are_scoped_to_their_biomolecule():
    """**Reading them globally silently builds the wrong structure.**

    Every `BIOMOLECULE:` block restarts its operator numbering, so the
    same id means different things in different blocks. 4EA3, in the
    bundled catalogue, is the live case -- its operator 2 translates by
    +14.85678 in assembly 1 and by -27.24922 in assembly 2. A global map
    keeps whichever came last, which placed assembly 1's second chain
    42 A from where the depositor put it: a plausible dimer, in the wrong
    place, with nothing at all to say so.
    """
    from openchem.chem.structure_assembly import operator_transforms

    assert operator_transforms(_TWO_BIOMOLECULES, "pdb", "1")["2"].vector[0] == pytest.approx(14.85678)
    assert operator_transforms(_TWO_BIOMOLECULES, "pdb", "2")["2"].vector[0] == pytest.approx(-27.24922)


def test_building_uses_the_operators_of_the_assembly_asked_for():
    """The same check one level up, on the coordinates that come out."""
    from openchem.chem.structure_assembly import build_assembly

    text = _pdb(_TWO_BIOMOLECULES, _TWO_CHAINS)
    first = _atom_lines(build_assembly(text, "pdb", "1").output_text)
    second = _atom_lines(build_assembly(text, "pdb", "2").output_text)

    # Compared at the FORMAT's precision, not the transform's: PDB writes
    # three decimals, so 14.85678 is serialised as 14.857. Asserting the
    # unrounded value here would be asserting something the file cannot
    # express -- the transform's own accuracy is a separate measurement,
    # made before serialisation.
    assert _coords(first[1])[0] == pytest.approx(14.85678, abs=5e-4)
    assert _coords(second[1])[0] == pytest.approx(-27.24922, abs=5e-4)


def test_several_chain_groups_in_one_assembly_are_unioned():
    """4DAJ writes five groups, each naming different chains with their
    own operators. Applying every operator to every chain would be a
    different structure, and assuming one group per assembly is a very
    plausible parser mistake."""
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(_pdb(_TWO_BIOMOLECULES, _TWO_CHAINS), "pdb", "1")
    assert result.ok
    assert [(i.source_chain, i.operator_id) for i in result.instances] == [("A", "1"), ("B", "2")]


def test_a_repeated_chain_and_operator_is_placed_once():
    """Overlapping groups must not double the atoms. The same
    `(assembly, source chain, operator)` is ONE copy however many rows
    happen to name it."""
    from openchem.chem.structure_assembly import build_assembly

    overlapping = (
        "REMARK 350 BIOMOLECULE: 1\n"
        "REMARK 350 APPLY THE FOLLOWING TO CHAINS: A, B\n"
        "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
        "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
        "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
        "REMARK 350 APPLY THE FOLLOWING TO CHAINS: B\n"
        "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
        "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
        "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
    )
    result = build_assembly(_pdb(overlapping, _TWO_CHAINS), "pdb")

    assert result.ok
    assert len(result.instances) == 2, [i.source_chain for i in result.instances]
    assert len(_atom_lines(result.output_text)) == 2


def test_alternate_locations_survive_the_build_untouched():
    """The builder PRESERVES altlocs and does not choose between them.

    Selection belongs to `pose_analysis.filter_altlocs`, which sits
    immediately upstream of the receptor path; a builder that also picked
    would mean two things deciding the same question. Both conformations
    have to come through, keeping their identifiers and occupancies, and
    both have to be transformed.
    """
    from openchem.chem.structure_assembly import build_assembly

    altloc = (
        "ATOM      1  N  AALA A   1       1.000   2.000   3.000  0.60 20.00           N\n"
        "ATOM      2  N  BALA A   1       1.500   2.500   3.500  0.40 20.00           N\n"
    )
    produced = _atom_lines(build_assembly(_pdb(_TWO_OPERATORS, altloc), "pdb").output_text)

    assert len(produced) == 4
    assert [line[16] for line in produced] == ["A", "B", "A", "B"]
    assert [line[54:60] for line in produced] == ["  0.60", "  0.40", "  0.60", "  0.40"]
    # ...and the generated pair moved, both of them: (x, y, z) -> (-x + 10, y, -z).
    assert _coords(produced[2]) == pytest.approx((9.0, 2.0, -3.0))
    assert _coords(produced[3]) == pytest.approx((8.5, 2.5, -3.5))


# --- building from mmCIF ----------------------------------------------------
#
# The format PDB refuses into. Everything below exists because a
# single-character chain id and a five-column atom serial cannot express
# the assemblies most worth building.

_OPER_COLUMNS = (
    "id type name symmetry_operation "
    "matrix[1][1] matrix[1][2] matrix[1][3] vector[1] "
    "matrix[2][1] matrix[2][2] matrix[2][3] vector[2] "
    "matrix[3][1] matrix[3][2] matrix[3][3] vector[3]"
).split()

#: Identity, then a 2-fold about z with a translation -- a matrix whose
#: transpose is a DIFFERENT rotation, so these tests can catch what an
#: axis-aligned one cannot.
_OPERATORS = (
    "1 'identity operation' 1_555 x,y,z "
    "1.0000000000 0.0000000000 0.0000000000 0.0000000000 "
    "0.0000000000 1.0000000000 0.0000000000 0.0000000000 "
    "0.0000000000 0.0000000000 1.0000000000 0.0000000000",
    "2 'crystal symmetry operation' 2_555 -y,x,z "
    "0.0000000000 -1.0000000000 0.0000000000 10.0000000000 "
    "1.0000000000 0.0000000000 0.0000000000 0.0000000000 "
    "0.0000000000 0.0000000000 1.0000000000 0.0000000000",
)

_ATOM_COLUMNS = (
    "group_PDB id type_symbol label_atom_id label_alt_id label_comp_id "
    "label_asym_id label_entity_id label_seq_id pdbx_PDB_ins_code "
    "Cartn_x Cartn_y Cartn_z occupancy B_iso_or_equiv "
    "auth_seq_id auth_comp_id auth_asym_id auth_atom_id pdbx_PDB_model_num"
).split()


def _mmcif(
    atoms: tuple[str, ...],
    asym_id_list: str = "A",
    oper_expression: str = "1,2",
    extra: str = "",
) -> str:
    """A minimal but REAL-SHAPED mmCIF: looped categories, `#` separators.

    Written out rather than trimmed from a deposit because every column
    here is one the builder reads or must carry through untouched, and a
    fixture nobody can read line by line hides which is which.
    """
    lines = ["data_TEST", "#", "loop_"]
    lines += [
        "_pdbx_struct_assembly.id",
        "_pdbx_struct_assembly.details",
        "_pdbx_struct_assembly.oligomeric_details",
        "_pdbx_struct_assembly.oligomeric_count",
        "1 author_defined_assembly dimeric 2",
        "#",
        "loop_",
        "_pdbx_struct_assembly_gen.assembly_id",
        "_pdbx_struct_assembly_gen.oper_expression",
        "_pdbx_struct_assembly_gen.asym_id_list",
        f"1 {oper_expression} {asym_id_list}",
        "#",
        "loop_",
    ]
    lines += [f"_pdbx_struct_oper_list.{name}" for name in _OPER_COLUMNS]
    lines += list(_OPERATORS)
    lines += ["#"]
    if extra:
        lines += extra.splitlines() + ["#"]
    lines += ["loop_"]
    lines += [f"_atom_site.{name}" for name in _ATOM_COLUMNS]
    lines += list(atoms)
    lines += ["#", ""]
    return "\n".join(lines)


def _atom(
    serial: int,
    chain: str,
    x: float,
    y: float,
    z: float,
    atom_name: str = "N",
    auth_chain: str | None = None,
) -> str:
    auth = auth_chain if auth_chain is not None else chain
    return (
        f"ATOM {serial} N {atom_name} . ALA {chain} 1 1 ? "
        f"{x:.3f} {y:.3f} {z:.3f} 1.00 20.00 1 ALA {auth} {atom_name} 1"
    )


def _cif_atoms(text: str) -> list[list[str]]:
    from openchem.chem.structure_assembly import _loop_rows

    return _loop_rows(text, "_atom_site.")[1]


def _cif_column(text: str, name: str) -> list[str]:
    from openchem.chem.structure_assembly import _loop_rows

    names, rows = _loop_rows(text, "_atom_site.")
    position = names.index(name)
    return [row[position] for row in rows]


def test_an_mmcif_assembly_applies_the_operator_to_the_named_chains():
    """The 2-fold above sends (x, y, z) to (-y + 10, x, z)."""
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(_mmcif((_atom(1, "A", 1.0, 2.0, 3.0),)), "mmcif")

    assert result.ok, result.failure_reason
    xs = _cif_column(result.output_text, "Cartn_x")
    ys = _cif_column(result.output_text, "Cartn_y")
    assert [float(v) for v in xs] == [1.0, 8.0]
    assert [float(v) for v in ys] == [2.0, 1.0]


def test_a_generated_mmcif_chain_is_named_after_its_operator():
    """RCSB's own convention, and it was MEASURED rather than guessed.

    2OMF's single chain under operators 1, 2 and 3 is `A`, `A-2`, `A-3` in
    RCSB's generated file, so the suffix is the operator id and not a copy
    ordinal. Both id spaces are suffixed together, because several
    label_asym_ids can share one auth_asym_id (4DKL has 20 to 1) and only
    an operator-derived suffix stays consistent across that.
    """
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(_mmcif((_atom(1, "A", 1.0, 2.0, 3.0),)), "mmcif")

    assert [i.generated_chain_id for i in result.instances] == ["A", "A-2"]
    assert _cif_column(result.output_text, "label_asym_id") == ["A", "A-2"]
    assert _cif_column(result.output_text, "auth_asym_id") == ["A", "A-2"]


def test_mmcif_has_no_chain_name_limit_where_pdb_refuses():
    """**THE WHOLE REASON THIS PATH EXISTS.**

    PDB gives the chain field one column, so 62 names is all there is and
    a 63rd copy cannot be written at all. mmCIF has no such limit, and the
    assemblies that need a 63rd copy -- capsids, spindles, filaments --
    are exactly the ones where the deposited file is least like the
    biological unit.
    """
    from openchem.chem.structure_assembly import build_assembly

    chains = [chr(ord("A") + i) for i in range(26)] + [
        f"A{chr(ord('A') + i)}" for i in range(26)
    ] + [f"B{chr(ord('A') + i)}" for i in range(11)]
    assert len(chains) == 63
    atoms = tuple(_atom(n + 1, chain, 1.0, 2.0, 3.0) for n, chain in enumerate(chains))

    result = build_assembly(
        _mmcif(atoms, asym_id_list=",".join(chains), oper_expression="1,2"), "mmcif"
    )

    assert result.ok, result.failure_reason
    assert len(result.instances) == 126
    assert len(_cif_atoms(result.output_text)) == 126


def test_a_built_mmcif_carries_no_instruction_to_build_it_again():
    """Re-entrancy, the same contract `REMARK 350` has on the PDB side.

    Left in place, `_pdbx_struct_assembly_gen` tells the next reader to
    apply the operators to a structure that has already had them applied.
    """
    from openchem.chem.structure_assembly import build_assembly, parse_assembly

    result = build_assembly(_mmcif((_atom(1, "A", 1.0, 2.0, 3.0),)), "mmcif")

    assert parse_assembly(result.output_text, "mmcif").assemblies == ()
    for category in ("_pdbx_struct_assembly", "_pdbx_struct_oper_list", "_atom_site_anisotrop"):
        assert category not in result.output_text


def test_the_anisotropic_tensor_category_is_dropped_not_carried():
    """`_atom_site_anisotrop` is ANISOU under another name: it transforms
    as R.U.Rt, so a copy carrying it unrotated states the WRONG
    orientation rather than a missing one."""
    from openchem.chem.structure_assembly import build_assembly

    anisotrop = (
        "loop_\n"
        "_atom_site_anisotrop.id\n"
        "_atom_site_anisotrop.U[1][1]\n"
        "1 0.1234\n"
    )
    result = build_assembly(
        _mmcif((_atom(1, "A", 1.0, 2.0, 3.0),), extra=anisotrop), "mmcif"
    )

    assert result.ok, result.failure_reason
    assert "_atom_site_anisotrop" not in result.output_text
    assert "0.1234" not in result.output_text


def test_an_atom_name_carrying_a_prime_survives_the_rebuild():
    """CIF QUOTES a value containing a prime, and `_cif_tokens` strips the
    quotes on the way in. Written back bare, `C1'` would change the token
    count of its row and shift every column after it -- which is the same
    trap that made 11 of 5I6X's atoms look like a composition mismatch in
    the RCSB gate's own scorer.
    """
    from openchem.chem.structure_assembly import build_assembly

    text = _mmcif((_atom(1, "A", 1.0, 2.0, 3.0, atom_name='"C1\'"'),))
    result = build_assembly(text, "mmcif")

    assert result.ok, result.failure_reason
    rows = _cif_atoms(result.output_text)
    assert all(len(row) == len(_ATOM_COLUMNS) for row in rows), rows
    assert _cif_column(result.output_text, "label_atom_id") == ["C1'", "C1'"]
    # ...and it is WRITTEN quoted, which the round trip above does not
    # prove. `C1'` is legal bare and survives this module's own tokeniser
    # either way, so the first version of this test passed while the
    # quoting it was named for was never exercised -- caught by mutating
    # `_cif_value` to quote nothing and watching every test still pass.
    assert "\"C1'\"" in result.output_text


def test_a_chain_named_by_the_assembly_but_absent_says_which_id_space():
    """mmCIF assembly records name label_asym_ids and PDB REMARK 350 names
    author ids, and confusing the two is the failure this message exists
    to shorten."""
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(
        _mmcif((_atom(1, "A", 1.0, 2.0, 3.0),), asym_id_list="A,Z"), "mmcif"
    )

    assert not result.ok
    assert "Z" in result.failure_reason
    assert "label_asym_id" in result.failure_reason


def test_several_models_are_refused_rather_than_merged():
    """An NMR ensemble has no single structure to transform, and silently
    transforming all of them would multiply the atom count by the model
    count without saying so."""
    from openchem.chem.structure_assembly import build_assembly

    two_models = (
        _atom(1, "A", 1.0, 2.0, 3.0),
        _atom(1, "A", 1.5, 2.5, 3.5).rsplit(" ", 1)[0] + " 2",
    )
    result = build_assembly(_mmcif(two_models), "mmcif")

    assert not result.ok
    assert "models" in result.failure_reason


def test_the_mmcif_build_keeps_every_other_category_verbatim():
    """The analogue of the PDB path keeping its header records: a built
    assembly is the same deposit with different coordinates, not a
    stripped one."""
    from openchem.chem.structure_assembly import build_assembly

    extra = (
        "loop_\n"
        "_struct_conn.id\n"
        "_struct_conn.ptnr1_label_asym_id\n"
        "disulf1 A\n"
    )
    result = build_assembly(
        _mmcif((_atom(1, "A", 1.0, 2.0, 3.0),), extra=extra), "mmcif"
    )

    assert result.ok, result.failure_reason
    # Kept, deliberately: its references are chain/residue/atom NAMES, so
    # they stay true of the copy that keeps its deposited name and simply
    # say nothing about the generated one -- incomplete, never wrong.
    assert "_struct_conn.id" in result.output_text
    assert "disulf1" in result.output_text


def test_the_atom_limit_refuses_before_anything_is_written():
    """Same guard as the PDB path, and it has to be on this side too --
    mmCIF's lack of field-width limits removes the OTHER two refusals, so
    without this one an icosahedral capsid would build silently."""
    from openchem.chem.structure_assembly import build_assembly

    result = build_assembly(
        _mmcif((_atom(1, "A", 1.0, 2.0, 3.0),)), "mmcif", atom_limit=1
    )

    assert not result.ok
    assert "2 atoms" in result.failure_reason
    assert result.output_text == ""
