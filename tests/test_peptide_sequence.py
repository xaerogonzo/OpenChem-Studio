"""Pin the peptide sequence expander: grammar, connectivity, stereo, refusals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit import __version__ as rdkit_version

from openchem.chem.peptide_sequence import (
    BUILDER,
    CATALOG_ENTRY_IDS,
    MEASURED_RDKIT,
    STANDARD_ONE_LETTER,
    PeptideSequenceError,
    molblock_from_sequence,
    parse_sequence,
)

CATALOG = Path(__file__).resolve().parents[1] / "src" / "openchem" / "chem" / "data" / "structure_templates" / "amino_acids.json"
_AMIDE = Chem.MolFromSmarts("[CX3](=O)[NX3]")
_PRIMARY_NTERM = Chem.MolFromSmarts("[NX3H2][CX4][CX3](=O)")
_PRO_NTERM = Chem.MolFromSmarts("[NX3H1]1CCC[C@H]1C(=O)")
_INTERNAL_PRO_AMIDE = Chem.MolFromSmarts("[CX3](=O)[NX3H0]1CCC[C@H]1")
_SIDE_COOH = Chem.MolFromSmarts("[CX4][CX3](=O)[OX2H1]")
_THIOL = Chem.MolFromSmarts("[CX4][SH1]")


def _catalog_by_id() -> dict[str, str]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {entry["id"]: entry["smiles"] for entry in data["entries"]}


def _mol(text: str) -> Chem.Mol:
    built = molblock_from_sequence(text)
    mol = Chem.MolFromMolBlock(built.molblock, removeHs=False)
    assert mol is not None
    return mol, built


def _centers(mol: Chem.Mol) -> list[tuple[int, str]]:
    Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
    return Chem.FindMolChiralCenters(mol, includeUnassigned=True)


def test_the_builder_is_molfromsequence_on_the_pinned_rdkit():
    assert BUILDER == "MolFromSequence"
    assert rdkit_version.startswith("2025.09")
    assert MEASURED_RDKIT.startswith("2025.09")


def test_ala_glu_gly_and_aeg_are_the_same_molecule():
    a = molblock_from_sequence("Ala-Glu-Gly")
    b = molblock_from_sequence("AEG")
    ma = Chem.MolFromMolBlock(a.molblock)
    mb = Chem.MolFromMolBlock(b.molblock)
    assert a.one_letter == b.one_letter == "AEG"
    assert Chem.MolToInchiKey(ma) == Chem.MolToInchiKey(mb) == "PAIHPOGPJVUFJY-WDSKDSINSA-N"
    assert Chem.MolToSmiles(ma, isomericSmiles=True) == Chem.MolToSmiles(mb, isomericSmiles=True)


@pytest.mark.parametrize(
    "text",
    ["Ala-Glu-Gly", "ALA-GLU-GLY", "ala-glu-gly", "Ala-glu-GLY"],
)
def test_three_letter_input_is_case_insensitive(text):
    assert parse_sequence(text) == ("A", "E", "G")


def test_one_letter_must_be_uppercase():
    with pytest.raises(PeptideSequenceError, match="uppercase"):
        parse_sequence("aeg")
    with pytest.raises(PeptideSequenceError, match="uppercase"):
        parse_sequence("Aeg")


def test_all_twenty_one_letter_codes_match_the_catalog_by_inchikey():
    catalog = _catalog_by_id()
    for letter in STANDARD_ONE_LETTER:
        entry_id = CATALOG_ENTRY_IDS[letter]
        cat = Chem.MolFromSmiles(catalog[entry_id])
        seq = Chem.MolFromSequence(letter)
        assert cat is not None and seq is not None
        assert Chem.MolToInchiKey(cat) == Chem.MolToInchiKey(seq), letter


def test_aeg_connectivity_and_neutral_termini():
    mol, built = _mol("AEG")
    assert built.codes == ("A", "E", "G")
    assert mol.GetNumHeavyAtoms() == 19
    assert len(Chem.GetMolFrags(mol)) == 1
    assert len(mol.GetSubstructMatches(_AMIDE)) == 2
    assert mol.HasSubstructMatch(_PRIMARY_NTERM)
    acids = mol.GetSubstructMatches(_SIDE_COOH)
    # C-terminal COOH plus Glu side chain
    assert len(acids) == 2
    assert not any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms())


def test_n_terminal_proline_is_a_secondary_amine():
    mol, _ = _mol("PG")
    assert mol.HasSubstructMatch(_PRO_NTERM)
    assert not mol.HasSubstructMatch(_PRIMARY_NTERM)
    assert len(mol.GetSubstructMatches(_AMIDE)) == 1


def test_internal_proline_is_a_tertiary_amide():
    mol, _ = _mol("APG")
    assert mol.HasSubstructMatch(_PRIMARY_NTERM)
    assert mol.HasSubstructMatch(_INTERNAL_PRO_AMIDE)
    assert len(mol.GetSubstructMatches(_AMIDE)) == 2


def test_cysteine_stays_a_free_thiol():
    mol, _ = _mol("AC")
    assert mol.HasSubstructMatch(_THIOL)


def test_two_mer_three_mer_and_ten_mer_are_one_component_with_n_minus_one_amides():
    for text, n in (("AG", 2), ("AEG", 3), ("ACDEFGHIKL", 10)):
        mol, built = _mol(text)
        assert len(built.codes) == n
        assert len(Chem.GetMolFrags(mol)) == 1
        assert len(mol.GetSubstructMatches(_AMIDE)) == n - 1


def test_dag_is_asp_ala_gly_not_d_chemistry():
    assert parse_sequence("DAG") == ("D", "A", "G")
    mol, _ = _mol("DAG")
    assert len(mol.GetSubstructMatches(_AMIDE)) == 2


def test_isoleucine_and_threonine_keep_two_assigned_centres():
    catalog = _catalog_by_id()
    for letter, entry_id in (("I", "amino_acids.l_isoleucine"), ("T", "amino_acids.l_threonine")):
        cat = Chem.MolFromSmiles(catalog[entry_id])
        seq = Chem.MolFromSequence(letter)
        cat_c = [cfg for _i, cfg in _centers(cat) if cfg in ("R", "S")]
        seq_c = [cfg for _i, cfg in _centers(seq) if cfg in ("R", "S")]
        assert len(seq_c) == 2, letter
        assert sorted(cat_c) == sorted(seq_c), letter


def test_l_cysteine_cip_matches_the_catalog():
    catalog = _catalog_by_id()
    cat = Chem.MolFromSmiles(catalog["amino_acids.l_cysteine"])
    seq = Chem.MolFromSequence("C")
    assert [cfg for _i, cfg in _centers(cat)] == [cfg for _i, cfg in _centers(seq)]


def test_alanine_glutamate_proline_match_catalog_inchikeys():
    catalog = _catalog_by_id()
    for letter, entry_id in (
        ("A", "amino_acids.l_alanine"),
        ("E", "amino_acids.l_glutamic_acid"),
        ("P", "amino_acids.l_proline"),
    ):
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(catalog[entry_id])) == Chem.MolToInchiKey(
            Chem.MolFromSequence(letter)
        )


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("", "Enter a peptide sequence"),
        ("A", "at least two"),
        ("Ala", "uppercase"),
        ("ZZ", "ambiguous"),
        ("BAA", "ambiguous"),
        ("UAA", "Selenocysteine"),
        ("OAA", "Pyrrolysine"),
        ("D-Ala-Gly", "D-amino"),
        ("Ala*Gly", "wildcard"),
        ("AA,GG", "Multiple chains"),
        ("AEG1", "Numbers"),
        ("PEPTIDE{R}", "HELM"),
        ("Sec-Gly", "Unknown residue"),
        ("ala glu gly", "spaces"),
        ("aeg", "uppercase"),
    ],
)
def test_refusals_are_named_and_return_no_partial(text, needle):
    with pytest.raises(PeptideSequenceError, match=needle):
        molblock_from_sequence(text)


def test_the_catalog_has_extras_that_are_not_accepted():
    catalog = _catalog_by_id()
    assert "amino_acids.l_selenocysteine" in catalog
    assert "amino_acids.d_alanine" in catalog
    with pytest.raises(PeptideSequenceError):
        parse_sequence("Sec-Gly")
    with pytest.raises(PeptideSequenceError):
        parse_sequence("D-Ala-Gly")
