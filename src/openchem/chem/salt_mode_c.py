"""Mode C: candidate states of one two-component pair, then domain enumerate.

pKa is not used to rank or filter. A ladder that cannot be built is a note,
not a substitute list of ions.
"""

from __future__ import annotations

from collections.abc import Sequence

from rdkit import Chem

from openchem.chem.pka_species_ladder import LADDER_NOTE, LadderRefusal, SpeciesLadder
from openchem.chem.salt_components import (
    IdentityRefusal,
    fragment_formal_charge,
    fragment_key,
)
from openchem.domain.salt_stoichiometry import (
    ORIGIN_LADDER,
    ORIGIN_USER,
    ModeCCandidate,
    ModeCResult,
    enumerate_mode_c,
)

REACHED_BY = (
    "window: consumed by chem/salt_compose.py for Tools > Salt Composition"
)


def _candidate(mol: Chem.Mol, origin: str, ladder_index: int | None = None) -> ModeCCandidate | IdentityRefusal:
    key = fragment_key(mol)
    if isinstance(key, IdentityRefusal):
        return key
    charge = fragment_formal_charge(mol)
    if charge == 0:
        return IdentityRefusal(
            code="not_an_ion",
            reason="Mode C candidates must be charged; a net-zero fragment is skipped only from a ladder.",
        )
    return ModeCCandidate(key, charge, origin, ladder_index)


def _from_molblock(block: str) -> Chem.Mol | None:
    mol = Chem.MolFromMolBlock(block, sanitize=False)
    if mol is None:
        return None
    try:
        Chem.SanitizeMol(mol)
    except (ValueError, RuntimeError):
        return None
    return mol


def _ladder_candidates(
    ladder: SpeciesLadder | LadderRefusal | None,
    notes: list[str],
) -> list[ModeCCandidate] | IdentityRefusal:
    if ladder is None:
        return []
    if isinstance(ladder, LadderRefusal):
        notes.append(ladder.message)
        return []
    notes.append(LADDER_NOTE)
    out: list[ModeCCandidate] = []
    for index, block in enumerate(ladder.molblocks):
        mol = _from_molblock(block)
        if mol is None:
            continue
        if fragment_formal_charge(mol) == 0:
            continue
        built = _candidate(mol, ORIGIN_LADDER, index)
        if isinstance(built, IdentityRefusal):
            if built.code == "not_an_ion":
                continue
            return built
        out.append(built)
    return out


def enumerate_pair(
    cation_mols: Sequence[Chem.Mol],
    anion_mols: Sequence[Chem.Mol],
    *,
    cation_ladder: SpeciesLadder | LadderRefusal | None = None,
    anion_ladder: SpeciesLadder | LadderRefusal | None = None,
) -> ModeCResult | IdentityRefusal:
    """User ions first, then ladder species of each side, then ``enumerate_mode_c``."""
    notes: list[str] = []
    cations: list[ModeCCandidate] = []
    anions: list[ModeCCandidate] = []
    for mol in cation_mols:
        built = _candidate(mol, ORIGIN_USER)
        if isinstance(built, IdentityRefusal):
            return built
        cations.append(built)
    for mol in anion_mols:
        built = _candidate(mol, ORIGIN_USER)
        if isinstance(built, IdentityRefusal):
            return built
        anions.append(built)
    extra = _ladder_candidates(cation_ladder, notes)
    if isinstance(extra, IdentityRefusal):
        return extra
    cations.extend(extra)
    extra = _ladder_candidates(anion_ladder, notes)
    if isinstance(extra, IdentityRefusal):
        return extra
    anions.extend(extra)
    return enumerate_mode_c(cations, anions, notes)
