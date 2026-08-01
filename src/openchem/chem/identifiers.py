"""The identifiers that name a structure when nothing else can.

Most structures have no verified IUPAC name -- the naming benchmark
(benchmarks/naming) put PubChem's coverage at 118/124 for well-known
chemistry, and at zero for anything genuinely new. A SMILES, an InChI or
an InChIKey is then the only unambiguous way to refer to a molecule at
all, which is why copying one has to be one click rather than an export
dialog.

InChIKey specifically is the one to paste into a search engine: it is
fixed-length, has no characters that break in a URL or a spreadsheet
cell, and is what most databases index on.
"""

from __future__ import annotations

import logging

from rdkit import Chem

logger = logging.getLogger("openchem.chemistry")

#: Menu label -> what it produces. Keys are what callers pass to
#: `identifier_for_molblock`.
KINDS = ("smiles", "inchi", "inchikey")


def identifier_for_molblock(molblock: str, kind: str) -> str:
    """One identifier for `molblock`, or "" if it cannot be produced.

    Returns empty rather than raising: every caller is a menu action, and
    a structure that will not parse is a normal thing to right-click, not
    an error worth interrupting someone over.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown identifier kind {kind!r}; expected one of {KINDS}")
    if not molblock or not molblock.strip():
        return ""
    mol = Chem.MolFromMolBlock(molblock)
    if mol is None:
        logger.debug("No identifier: the structure could not be parsed")
        return ""
    return identifier_for_mol(mol, kind)


def identifier_for_mol(mol: Chem.Mol, kind: str) -> str:
    if kind == "smiles":
        # Canonical and isomeric: stereochemistry is part of the identity
        # of the compound, and dropping it would silently equate
        # enantiomers.
        return Chem.MolToSmiles(mol)
    # InChI generation writes to RDKit's C++ error log for things like an
    # unusual valence. That is not a failure -- the InChI is still
    # produced -- so the log is left alone and only an empty result is
    # treated as one.
    if kind == "inchi":
        return Chem.MolToInchi(mol) or ""
    return Chem.MolToInchiKey(mol) or ""
