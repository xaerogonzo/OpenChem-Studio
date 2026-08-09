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
