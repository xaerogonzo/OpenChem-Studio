"""Reading the depositor's biological-assembly annotation.

Validated where it counts against RCSB's own API rather than against my
reading of the spec: the parser's `oligomeric_details` matches
`data.rcsb.org`'s for all 49 curated receptors, and the mmCIF and PDB
paths agree on operator applications for all 48 that exist in both
formats. Those runs need the network; the cases below are the specific
constructs that broke on the way there, pinned as fixtures.
"""

from __future__ import annotations

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
