"""SMARTS substructure search with highlightable matches.

Not one of Marvin's plugins -- added because it is genuinely useful and
because this codebase already contains a lot of validated SMARTS that
becomes browsable through it: the PAINS and BRENK catalogs, the curated
functional-group set, and the hERG basic-amine pattern whose 9 test cases
were checked live in Phase 20.

Matches are returned as a `PerAtomDataset` rather than a plain list of
indices, so highlighting comes free through the visualization layers that
already exist -- a matched atom gets 1.0, everything else 0.0, which the
existing colour scale renders as a two-tone highlight over both the 2D
depiction and the 3D view.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem

from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import PerAtomDataset

# A starting library so the calculator is useful before anyone has typed a
# SMARTS of their own. Every pattern here is either trivially checkable or
# already validated elsewhere in this codebase.
COMMON_PATTERNS: dict[str, str] = {
    "Carboxylic acid": "[CX3](=O)[OX2H1]",
    "Ester": "[CX3](=O)[OX2H0][#6]",
    "Amide": "[NX3][CX3](=[OX1])",
    "Primary amine": "[NX3;H2;!$(NC=[O,S]);!$(N=*);!$(Nc)]",
    "Basic amine (hERG risk pattern)": "[NX3;H2,H1,H0;!$(NC=[O,S]);!$(N=*);!$(NS(=O)=O);!$(Nc);!a]",
    "Alcohol": "[OX2H][CX4]",
    "Phenol": "[OX2H]c",
    "Ether": "[OD2]([#6])[#6]",
    "Ketone": "[#6][CX3](=O)[#6]",
    "Aldehyde": "[CX3H1](=O)[#6]",
    "Nitrile": "[NX1]#[CX2]",
    "Nitro": "[$([NX3](=O)=O),$([NX3+](=O)[O-])]",
    "Sulfonamide": "[SX4](=[OX1])(=[OX1])([NX3])",
    "Halogen": "[F,Cl,Br,I]",
    "Aromatic ring": "a1aaaaa1",
    "Benzene ring": "c1ccccc1",
}


class InvalidSmartsError(ValueError):
    """Raised when a SMARTS pattern cannot be parsed -- reported to the
    user rather than silently matching nothing, which would be
    indistinguishable from a valid pattern with no hits."""


def find_matches(mol: Chem.Mol, smarts: str) -> list[tuple[int, ...]]:
    """Every distinct match of `smarts`, as tuples of atom indices."""
    pattern = Chem.MolFromSmarts(smarts)
    if pattern is None:
        raise InvalidSmartsError(f"Not a valid SMARTS pattern: {smarts!r}")
    return [tuple(match) for match in mol.GetSubstructMatches(pattern)]


def matched_atoms(mol: Chem.Mol, smarts: str) -> set[int]:
    return {index for match in find_matches(mol, smarts) for index in match}


def compute_substructure_search(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """The "substructure" category's calculator.

    Takes either a raw `smarts` string or a `pattern` name from
    `COMMON_PATTERNS`; an explicit `smarts` wins so a user's own pattern is
    never silently overridden by a leftover dropdown selection.
    """
    parameters = parameters or {}
    smarts = (parameters.get("smarts") or "").strip()
    if not smarts:
        smarts = COMMON_PATTERNS.get(parameters.get("pattern", ""), "")
    if not smarts:
        return PerAtomDataset(
            property_id="substructure_match",
            name="Substructure Search",
            units="",
            method="rdkit",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error="Enter a SMARTS pattern, or pick one from the list.",
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    try:
        matches = find_matches(mol, smarts)
    except InvalidSmartsError as exc:
        return PerAtomDataset(
            property_id="substructure_match",
            name="Substructure Search",
            units="",
            method="rdkit",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    hit_atoms = {index for match in matches for index in match}
    # Every atom gets a value, not just the hits -- a dataset containing
    # only the matches would make the colour scale's domain collapse to a
    # single value and render every matched atom mid-scale grey.
    values = {atom.GetIdx(): (1.0 if atom.GetIdx() in hit_atoms else 0.0) for atom in mol.GetAtoms()}
    return PerAtomDataset(
        property_id="substructure_match",
        name=f"Substructure: {smarts} ({len(matches)} match{'es' if len(matches) != 1 else ''})",
        units="",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={"smarts": smarts, "match_count": len(matches)},
        ),
    )
