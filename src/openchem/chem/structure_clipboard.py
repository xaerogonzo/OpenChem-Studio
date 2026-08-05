"""Reading a structure out of whatever happens to be on the clipboard.

Pasting a structure is one action from the user's point of view, but what
lands on the clipboard depends entirely on where they copied it from: a
SMILES from a paper or a database page, a molfile from another editor, an
InChI from a supplementary table. Making them pick the format from a menu
first would be asking the user to do the one part of this a computer can
do reliably.

FORMAT IS DETECTED BY PARSING, NOT BY GUESSING FROM THE TEXT. An earlier
sketch of this sniffed for "M  END" and for an "InChI=" prefix, which is
fine until it is not: plenty of valid molfiles in the wild are truncated
before `M  END`, and the only way to know a string is a usable SMILES is
to hand it to the SMILES parser. So each candidate reader is simply tried,
most specific first, and the first one that yields a real molecule wins.

Order matters and is not arbitrary. InChI is checked before SMILES
because an InChI string starts with `InChI=1S/C2H6O/...` -- and RDKit's
SMILES parser, given that, does not necessarily refuse it outright.
Molfile is checked before either because a molfile's first line is a
title line that can contain anything at all, including something that
parses as a SMILES.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import AllChem

logger = logging.getLogger("openchem.chemistry")

#: Anything longer than this is not a structure someone pasted, and
#: handing it to three parsers in turn is a way to freeze the UI. A large
#: SDF or a stray copied document hits this; a real single structure does
#: not come close.
MAX_CLIPBOARD_CHARS = 100_000


@dataclass(frozen=True)
class ParsedStructure:
    """A structure recovered from clipboard text, and what it turned out to be."""

    molblock: str
    #: For the status bar. The user pasted something without saying what
    #: it was, so telling them what was recognised is how they find out
    #: the paste did what they meant -- particularly for the InChI case,
    #: where stereochemistry can be silently absent from the string.
    source_format: str


def parse_structure_text(text: str) -> ParsedStructure | None:
    """Recover a structure from clipboard text, or None if it isn't one.

    Returns None rather than raising: every caller is a menu action, and
    "the clipboard had no structure on it" is an ordinary thing for a
    paste to discover, not an error worth a traceback.
    """
    if not text or not text.strip():
        return None
    if len(text) > MAX_CLIPBOARD_CHARS:
        logger.debug("Clipboard text too long to be a single structure (%d chars)", len(text))
        return None

    for reader, name in (
        (_from_molblock, "molfile"),
        (_from_inchi, "InChI"),
        (_from_smiles, "SMILES"),
    ):
        mol = reader(text)
        if mol is None:
            continue
        molblock = _with_2d_coordinates(mol)
        if molblock:
            return ParsedStructure(molblock=molblock, source_format=name)
    return None


def _from_molblock(text: str) -> Chem.Mol | None:
    # A molfile's counts line is the 4th, so anything shorter cannot be
    # one. Checked because MolFromMolBlock on a one-line SMILES writes a
    # parse error to RDKit's C++ log, which is noise in every paste.
    if len(text.splitlines()) < 4:
        return None
    return Chem.MolFromMolBlock(text)


def _from_inchi(text: str) -> Chem.Mol | None:
    stripped = text.strip()
    if not stripped.startswith("InChI="):
        return None
    return Chem.MolFromInchi(stripped)


def _from_smiles(text: str) -> Chem.Mol | None:
    # SMILES have no whitespace; taking the first token means a copied
    # "CCO ethanol" line (SMILES plus a name, the usual .smi format)
    # still pastes, while a paragraph of prose does not become a
    # single-atom molecule from its first character.
    stripped = text.strip()
    if not stripped or "\n" in stripped:
        return None
    return Chem.MolFromSmiles(stripped.split()[0])


def _has_usable_coordinates(mol: Chem.Mol) -> bool:
    """Whether this structure is actually laid out, not merely conformer-bearing.

    "Has a conformer" is the obvious test and it is not quite enough: a
    molfile can carry a full block of zero coordinates, which parses into
    a perfectly valid conformer and draws as a heap of atoms stacked on
    the origin. Some SDF exports do this for structures that were never
    laid out.

    Not a problem this application creates for itself, which is worth
    recording because the opposite was assumed first: `MolToMolBlock`
    computes 2D coordinates when the molecule has none, so
    `set_structure_from_smiles` already produces a laid-out molblock
    (verified -- aspirin 13/13 atoms non-zero). The misreading came from
    checking only the first atom line, which reads `0.0000 0.0000 0.0000`
    in a correct layout too, because something has to be at the origin.
    """
    if not mol.GetNumConformers():
        return False
    conformer = mol.GetConformer()
    return any(
        pos.x or pos.y or pos.z
        for pos in (conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms()))
    )


def _with_2d_coordinates(mol: Chem.Mol) -> str:
    """A molblock the 2D editor can draw.

    Real coordinates are left alone -- a molfile from a database or
    another editor was laid out deliberately, and recomputing would throw
    that away for no gain.
    """
    try:
        if not _has_usable_coordinates(mol):
            AllChem.Compute2DCoords(mol)
        return Chem.MolToMolBlock(mol)
    except Exception:  # noqa: BLE001 - a structure we cannot write is one we cannot paste
        logger.debug("Parsed a structure from the clipboard but could not write a molblock")
        return ""
