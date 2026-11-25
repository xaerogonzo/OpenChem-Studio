"""Expand a short L-amino-acid sequence into one connected atomistic peptide.

Measured 2026-11-22 on RDKit 2025.09.6: ``Chem.MolFromSequence`` yields a
neutral N-to-C peptide (AEG: 19 heavy atoms, one component, two amides,
free termini). ``MolFromFASTA`` matched it on the same inputs and is not
a second path. Arg and His canonical SMILES differ from the Template
Library catalog by tautomer drawing; InChIKeys match. This module is that
one builder.

The drawing is a **neutral structural representation**, not the
predominant solution-phase protonation state: free N-terminus, free
C-terminal COOH, Asp/Glu side-chain COOH, Cys as free thiol, unprotonated
basic side chains, no zwitterion conversion, no disulfides, no caps.

Histidine is RDKit's ``c1c[nH]cn1`` tautomer; the catalog uses the
equivalent ``N1C=NC=C1`` drawing. Arginine is RDKit's ``N=C(N)N`` form;
the catalog uses ``NC(N)=N``. Identity is InChIKey.

The Template Library's ``amino_acids.json`` also holds D-residues,
selenocysteine, and other noncanonicals. Those are **not** accepted here.
The map below is the closed 20 standard proteinogenic residues (glycine
included).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import rdDepictor

#: Production builder. Do not add a condensation fallback beside it.
BUILDER = "MolFromSequence"

#: Pin of the measurement that chose ``BUILDER``.
MEASURED_RDKIT = "2025.09.6"

#: Closed 20 standard proteinogenic one-letter codes (glycine included).
STANDARD_ONE_LETTER = "ACDEFGHIKLMNPQRSTVWY"

#: One-letter -> Template Library shipped entry id (L, not the extras).
CATALOG_ENTRY_IDS: dict[str, str] = {
    "A": "amino_acids.l_alanine",
    "C": "amino_acids.l_cysteine",
    "D": "amino_acids.l_aspartic_acid",
    "E": "amino_acids.l_glutamic_acid",
    "F": "amino_acids.l_phenylalanine",
    "G": "amino_acids.glycine",
    "H": "amino_acids.l_histidine",
    "I": "amino_acids.l_isoleucine",
    "K": "amino_acids.l_lysine",
    "L": "amino_acids.l_leucine",
    "M": "amino_acids.l_methionine",
    "N": "amino_acids.l_asparagine",
    "P": "amino_acids.l_proline",
    "Q": "amino_acids.l_glutamine",
    "R": "amino_acids.l_arginine",
    "S": "amino_acids.l_serine",
    "T": "amino_acids.l_threonine",
    "V": "amino_acids.l_valine",
    "W": "amino_acids.l_tryptophan",
    "Y": "amino_acids.l_tyrosine",
}

#: Three-letter names (lowercase) to the one-letter map above.
_THREE_LETTER: dict[str, str] = {
    "ala": "A",
    "cys": "C",
    "asp": "D",
    "glu": "E",
    "phe": "F",
    "gly": "G",
    "his": "H",
    "ile": "I",
    "lys": "K",
    "leu": "L",
    "met": "M",
    "asn": "N",
    "pro": "P",
    "gln": "Q",
    "arg": "R",
    "ser": "S",
    "thr": "T",
    "val": "V",
    "trp": "W",
    "tyr": "Y",
}

#: One-letter codes that are not a single residue (B/J/X/Z).
_AMBIGUOUS = frozenset("BJXZ")
#: Peptide-bond SMARTS used to count amides after the builder runs.
_AMIDE = Chem.MolFromSmarts("[CX3](=O)[NX3]")


class PeptideSequenceError(ValueError):
    """Named refusal. The message is what a person is shown. No partial peptide."""


@dataclass(frozen=True)
class PeptideBuild:
    """One connected peptide ready to insert through ``insert_template_molblock``."""

    molblock: str
    one_letter: str
    codes: tuple[str, ...]


def parse_sequence(text: str) -> tuple[str, ...]:
    """Return one-letter codes, N to C. Raise ``PeptideSequenceError`` otherwise."""
    raw = text.strip()
    if not raw:
        raise PeptideSequenceError("Enter a peptide sequence.")
    if any(ch.isspace() for ch in raw):
        raise PeptideSequenceError("A sequence cannot contain spaces.")
    if "*" in raw:
        raise PeptideSequenceError("Stop or wildcard '*' is not a residue.")
    if any(ch.isdigit() for ch in raw):
        raise PeptideSequenceError("Numbers and sequence annotations are not supported.")
    if any(ch in raw for ch in ",;/.|"):
        raise PeptideSequenceError("Multiple chains are not supported.")
    if any(ch in raw for ch in "${}"):
        raise PeptideSequenceError("HELM and other sequence annotations are not supported.")
    if "-" in raw:
        return _parse_three_letter(raw)
    return _parse_one_letter(raw)


def molblock_from_sequence(text: str) -> PeptideBuild:
    """Parse, build, layout. Invalid input never returns a molblock."""
    codes = parse_sequence(text)
    one_letter = "".join(codes)
    mol = Chem.MolFromSequence(one_letter)
    if mol is None:
        raise PeptideSequenceError("The sequence could not be built as a peptide.")
    _refuse_if_not_a_linear_peptide(mol, codes)
    return PeptideBuild(
        molblock=_molblock_2d(mol),
        one_letter=one_letter,
        codes=codes,
    )


def _parse_one_letter(raw: str) -> tuple[str, ...]:
    if raw != raw.upper() or not raw.isalpha():
        raise PeptideSequenceError(
            "One-letter sequences must be uppercase (AEG), not mixed or lowercase."
        )
    if len(raw) < 2:
        raise PeptideSequenceError(
            "A single residue is already in the Template Library; enter at least two."
        )
    codes: list[str] = []
    for ch in raw:
        if ch in _AMBIGUOUS:
            raise PeptideSequenceError(f"{ch} is not a standard amino-acid code (it is ambiguous).")
        if ch == "U":
            raise PeptideSequenceError("Selenocysteine (U) is not in this sequence builder.")
        if ch == "O":
            raise PeptideSequenceError("Pyrrolysine (O) is not in this sequence builder.")
        if ch not in STANDARD_ONE_LETTER:
            raise PeptideSequenceError(f"{ch} is not a standard amino-acid code.")
        codes.append(ch)
    return tuple(codes)


def _parse_three_letter(raw: str) -> tuple[str, ...]:
    parts = raw.split("-")
    if any(part == "" for part in parts):
        raise PeptideSequenceError("Use hyphenated three-letter names (Ala-Glu-Gly).")
    if len(parts) < 2:
        raise PeptideSequenceError(
            "A single residue is already in the Template Library; enter at least two."
        )
    if parts[0].casefold() == "d" and len(parts) >= 2:
        raise PeptideSequenceError("D-amino acids are not supported.")
    codes: list[str] = []
    for part in parts:
        key = part.casefold()
        if key == "d":
            raise PeptideSequenceError("D-amino acids are not supported.")
        letter = _THREE_LETTER.get(key)
        if letter is None:
            raise PeptideSequenceError(f"Unknown residue {part!r}.")
        codes.append(letter)
    return tuple(codes)


def _refuse_if_not_a_linear_peptide(mol: Chem.Mol, codes: tuple[str, ...]) -> None:
    if any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
        raise PeptideSequenceError("The peptide contained a dummy atom and was not inserted.")
    if len(Chem.GetMolFrags(mol)) != 1:
        raise PeptideSequenceError("The peptide was not one connected molecule.")
    amides = mol.GetSubstructMatches(_AMIDE)
    if len(amides) != len(codes) - 1:
        raise PeptideSequenceError("The peptide did not have one amide per residue join.")


def _molblock_2d(mol: Chem.Mol) -> str:
    if mol.GetNumConformers() == 0:
        rdDepictor.Compute2DCoords(mol)
    Chem.WedgeMolBonds(mol, mol.GetConformer())
    return Chem.MolToMolBlock(mol)
