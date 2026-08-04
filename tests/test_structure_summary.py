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


# --- excluding chains from docking ----------------------------------------
#
# The rule these enforce is the one this codebase keeps relearning: the
# receptor that gets DOCKED and the receptor that gets ANALYSED must be
# the same receptor. `keep_chains` travels in `receptor_prep_options`,
# which the service hands to both, and both consult `is_excluded_chain`.


def test_no_selection_means_no_restriction():
    """Backward compatibility, and the reason the dialog returns an empty
    list rather than every chain id when all are ticked: an untouched
    dialog must leave docking exactly as it was."""
    from openchem.chem.pose_analysis import is_excluded_chain

    assert not is_excluded_chain("A", [])
    assert not is_excluded_chain("A", None)
    assert not is_excluded_chain("", [])


def test_a_chain_outside_the_selection_is_excluded():
    from openchem.chem.pose_analysis import is_excluded_chain

    assert is_excluded_chain("B", ["A"])
    assert not is_excluded_chain("A", ["A"])
    assert not is_excluded_chain("A", ["A", "B"])


def test_chain_matching_is_exact_and_not_case_folded():
    """mmCIF `label_asym_id` is case-sensitive and multi-character, and
    files do carry both `A` and `a`. Folding case to be forgiving would
    silently merge two different chains -- the same class of error as the
    residue key that once merged a homotetramer's subunits."""
    from openchem.chem.pose_analysis import is_excluded_chain

    assert is_excluded_chain("a", ["A"])
    assert not is_excluded_chain("AA", ["AA"])
    assert is_excluded_chain("AA", ["A"])


def test_excluding_a_chain_drops_exactly_that_chain_from_the_analysis():
    structure = _two_chain_structure()

    everything = receptor_atoms_from_structure(
        structure, "pdb", {"strip_waters": False, "strip_cofactors": False}
    )
    only_a = receptor_atoms_from_structure(
        structure,
        "pdb",
        {"strip_waters": False, "strip_cofactors": False, "keep_chains": ["A"]},
    )

    assert {a.chain for a in everything} == {"A", "B"}
    assert {a.chain for a in only_a} == {"A"}
    assert len(only_a) == sum(1 for a in everything if a.chain == "A")


def test_the_docking_receptor_and_the_analysis_agree_on_the_same_chains():
    """The whole point, asserted directly rather than trusted.

    Measured live on 3SN6 (the beta2AR/Gs complex) as well: unrestricted
    gives 10,274 analysis atoms against a 10,345-atom receptor, and
    keeping only chain D gives 3,433 against 3,456 -- the receptor running
    slightly higher throughout because preparation adds hydrogens. Here
    the same agreement is checked without a network fetch.
    """
    import pathlib
    import tempfile

    from openbabel import pybel

    from openchem.chem.docking_providers import VinaDockingProvider

    structure = _two_chain_structure()
    options = {"strip_waters": True, "keep_chains": ["A"]}

    analysed = receptor_atoms_from_structure(structure, "pdb", options)
    with tempfile.TemporaryDirectory() as scratch:
        out = pathlib.Path(scratch) / "receptor.pdbqt"
        VinaDockingProvider()._convert_receptor_to_pdbqt(
            pybel, structure, "pdb", out, options
        )
        docked = out.read_text()

    assert {a.chain for a in analysed} == {"A"}
    # Chain B's ligand code must not survive into the docked receptor --
    # if it does, the analysis is describing atoms Vina never saw.
    assert "STE" not in docked
    assert "HOH" not in docked
