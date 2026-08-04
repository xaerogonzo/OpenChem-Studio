"""Chain/residue classification, and the symmetry-expansion bug it found.

The summariser is small; the interesting part is what building it
surfaced. Running it over the 49 curated receptors crashed on two of
them, and the crash turned out to be Open Babel silently returning
symmetry copies of the whole protein -- 6WGT's 8,100-atom deposit reached
Vina as a 73,707-atom receptor. Those tests live here because this is
where the evidence was gathered.
"""

from __future__ import annotations

import textwrap

from openchem.chem.pose_analysis import is_symmetry_generated, receptor_atoms_from_structure
from openchem.chem.structure_summary import MIN_POLYMER_RESIDUES, summarize_structure


def _pdb(rows: str) -> str:
    return textwrap.dedent(rows).strip() + "\nEND\n"


def _atom(serial, name, res, chain, resnum, x, y, z, element, record="ATOM"):
    return (
        f"{record:<6}{serial:>5} {name:^4} {res:>3} {chain}{resnum:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00          {element:>2}"
    )


def _two_chain_structure() -> str:
    """Chain A: a 3-residue peptide. Chain B: a 2-residue one plus a
    ligand and a water, so the classifier has to separate components that
    share a file rather than assuming one kind per chain."""
    rows = [
        _atom(1, "CA", "GLY", "A", 1, 0.0, 0.0, 0.0, "C"),
        _atom(2, "CA", "ALA", "A", 2, 1.5, 0.0, 0.0, "C"),
        _atom(3, "CA", "SER", "A", 3, 3.0, 0.0, 0.0, "C"),
        _atom(4, "CA", "VAL", "B", 1, 0.0, 5.0, 0.0, "C"),
        _atom(5, "CA", "LEU", "B", 2, 1.5, 5.0, 0.0, "C"),
        _atom(6, "C1", "STE", "B", 90, 8.0, 8.0, 0.0, "C", record="HETATM"),
        _atom(7, "O", "HOH", "B", 91, 9.0, 9.0, 0.0, "O", record="HETATM"),
    ]
    return _pdb("\n".join(rows))


def test_chains_are_separated_and_sized():
    summary = summarize_structure(_two_chain_structure(), "pdb")

    chains = {c.chain_id: c for c in summary.chains}
    assert set(chains) == {"A", "B"}
    assert chains["A"].polymer_residue_count == 3
    assert chains["B"].polymer_residue_count == 2


def test_a_chain_reports_every_component_it_holds():
    """PDB files routinely put a protein, its ligands and its waters on
    one chain id. Reporting only the dominant one would hide the ligand
    the user is looking for."""
    summary = summarize_structure(_two_chain_structure(), "pdb")

    chain_b = next(c for c in summary.chains if c.chain_id == "B")
    assert chain_b.kind == "polymer"
    assert chain_b.ligand_codes == ("STE",)
    assert chain_b.water_count == 1


def test_the_sequence_is_one_letter_and_in_residue_order():
    """Ordered by residue number, not by the order atoms happen to appear
    -- the atom stream gives no such guarantee, and an out-of-order
    sequence is useless for identifying a chain."""
    summary = summarize_structure(_two_chain_structure(), "pdb")

    assert next(c for c in summary.chains if c.chain_id == "A").sequence == "GAS"


def test_a_lone_amino_acid_is_a_ligand_not_a_one_residue_protein():
    """Glycine and glutamate are neurotransmitters, and several receptors
    in the bundled catalogue are solved with one bound."""
    rows = [
        _atom(1, "CA", "GLY", "A", 1, 0.0, 0.0, 0.0, "C"),
        _atom(2, "CA", "ALA", "A", 2, 1.5, 0.0, 0.0, "C"),
        _atom(3, "CA", "GLU", "L", 1, 20.0, 0.0, 0.0, "C", record="HETATM"),
    ]
    summary = summarize_structure(_pdb("\n".join(rows)), "pdb")

    ligand_chain = next(c for c in summary.chains if c.chain_id == "L")
    assert ligand_chain.polymer_residue_count < MIN_POLYMER_RESIDUES
    assert ligand_chain.kind == "ligand"


def test_polymer_chains_sort_before_ligands_and_largest_first():
    """The question being answered is "which of these is my target", and
    the target is rarely the smallest thing in the file."""
    summary = summarize_structure(_two_chain_structure(), "pdb")

    assert [c.chain_id for c in summary.chains] == ["A", "B"]
    assert summary.polymer_chains[0].polymer_residue_count >= (
        summary.polymer_chains[-1].polymer_residue_count
    )


def test_a_single_chain_structure_is_not_called_a_complex():
    rows = [
        _atom(1, "CA", "GLY", "A", 1, 0.0, 0.0, 0.0, "C"),
        _atom(2, "CA", "ALA", "A", 2, 1.5, 0.0, 0.0, "C"),
        _atom(3, "C1", "STE", "A", 90, 8.0, 8.0, 0.0, "C", record="HETATM"),
    ]
    summary = summarize_structure(_pdb("\n".join(rows)), "pdb")

    assert not summary.looks_like_a_complex()


def test_two_polymer_chains_are_flagged_as_a_complex():
    """The signal that sent a user to look: measured across the bundled
    catalogue, 32 of 49 curated receptors trip this. 3SN6, labelled
    "beta2-adrenergic receptor", is five polymer chains of which the
    receptor is one -- the rest are a Gs heterotrimer and a nanobody."""
    summary = summarize_structure(_two_chain_structure(), "pdb")

    assert summary.looks_like_a_complex()
    assert len(summary.polymer_chains) == 2


def test_waters_are_reported_rather_than_stripped():
    """The summary describes the FILE, including the parts preparation
    would later delete. One that quietly agreed with the preparation could
    not tell you what you were about to lose."""
    summary = summarize_structure(_two_chain_structure(), "pdb")

    assert sum(c.water_count for c in summary.chains) == 1
    assert "HOH" not in summary.ligand_codes()


def test_ligand_codes_are_collected_across_chains():
    summary = summarize_structure(_two_chain_structure(), "pdb")

    assert summary.ligand_codes() == ("STE",)


# --- the symmetry-expansion bug -------------------------------------------


def test_a_null_residue_wrapper_is_treated_as_symmetry_generated():
    """The exact shape of the bug, which no obvious guard catches.

    Open Babel expands the unit cell when it cannot recognise a space
    group, and the generated copies carry no residue record. pybel wraps
    that null pointer in a perfectly TRUTHY `Residue` object, so
    `residue is not None` passes and `residue.name` then raises
    `AttributeError: 'NoneType' object has no attribute 'GetName'` --
    which is how this was found, by crashing on 2 of 49 real receptors.
    """

    class _NullWrapper:
        """Truthy, exactly like pybel's Residue around a null pointer."""

        OBResidue = None

    assert is_symmetry_generated(_NullWrapper())
    assert is_symmetry_generated(None)

    class _RealResidue:
        OBResidue = object()

    assert not is_symmetry_generated(_RealResidue())


def test_an_ordinary_structure_loses_no_atoms_to_the_symmetry_filter():
    """The filter must be precise, not blanket. Measured on real
    structures: 5C1M, 1ERE and 8ZYO all have zero symmetry-generated
    atoms -- and 8ZYO triggers Open Babel's space-group warning anyway,
    so the warning alone would have been the wrong signal to filter on."""
    structure = _two_chain_structure()

    atoms = receptor_atoms_from_structure(
        structure, "pdb", {"strip_waters": False, "strip_cofactors": False}
    )

    assert len(atoms) == 7
