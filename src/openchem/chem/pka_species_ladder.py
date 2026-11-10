"""Sequential protonation species from persisted pKa site records.

Species 0 is fully protonated; species `j` applies the `j`th dissociation
in the shared pKa order. The UI never adds or removes protons: this either
returns a complete ordered list of molblocks or a typed refusal. One failed
step suppresses the whole ladder.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem

from openchem.chem.ionisable_sites import ACID, BASE, UNKNOWN
from openchem.chem.logd import classify_ionizable_centres
from openchem.chem.ph_curves import microspecies_fractions, species_charges
from openchem.chem.pka_sites import (
    MAX_PICTURE_SITES,
    MIN_PICTURE_PERCENT,
    PkaSiteRecord,
)

LADDER_NOTE = (
    "The distribution treats predicted per-site pKa values as sequential "
    "dissociation steps. This is an approximate macroscopic model. Interacting "
    "sites, especially sites with similar pKa values, can produce more complex "
    "real microspecies distributions. The structures shown here are the "
    "corresponding sequential protonation ladder, not an independent enumeration "
    "of every microscopic state."
)


@dataclass(frozen=True)
class LadderRefusal:
    """Why pictures cannot be built. Labels, the chart and the table stay."""

    reason: str
    message: str


@dataclass(frozen=True)
class SpeciesLadder:
    """One molblock per sequential species, indexed as Species `j`."""

    molblocks: tuple[str, ...]
    hidden: frozenset[int]
    kinds_match_curve: bool
    charge_labels_match: bool
    net_charges: tuple[int, ...]


def _heavy_signature(mol: Chem.Mol) -> tuple[str, ...]:
    return tuple(atom.GetSymbol() for atom in mol.GetAtoms() if atom.GetAtomicNum() != 1)


def _apply_state(mol: Chem.Mol, index: int | None, state: tuple[int, int] | None) -> None:
    if index is None or state is None:
        raise ValueError("unmapped")
    if index < 0 or index >= mol.GetNumAtoms():
        raise ValueError("invalid_index")
    atom = mol.GetAtomWithIdx(index)
    if atom.GetAtomicNum() == 1:
        raise ValueError("hydrogen_site")
    hydrogens, charge = state
    atom.SetNumExplicitHs(int(hydrogens))
    atom.SetFormalCharge(int(charge))
    atom.SetNoImplicit(True)


def _sanitize(mol: Chem.Mol) -> Chem.Mol:
    copy = Chem.Mol(mol)
    try:
        Chem.SanitizeMol(copy)
    except Exception as exc:
        raise ValueError("sanitize") from exc
    return copy


def _molblock(mol: Chem.Mol) -> str:
    block = Chem.MolToMolBlock(mol)
    if not block.strip():
        raise ValueError("molblock")
    return block


def _hidden_species(records: tuple[PkaSiteRecord, ...], ph_values: list[float] | None) -> frozenset[int]:
    if not ph_values:
        return frozenset()
    pkas = [record.pka for record in records]
    hidden: set[int] = set()
    for index in range(len(records) + 1):
        peak = max((100.0 * microspecies_fractions(ph, pkas)[index] for ph in ph_values), default=0.0)
        if peak < MIN_PICTURE_PERCENT:
            hidden.add(index)
    return frozenset(hidden)


def build_species_ladder(
    parent: Chem.Mol,
    records: tuple[PkaSiteRecord, ...] | list[PkaSiteRecord],
    *,
    ph_values: list[float] | None = None,
) -> SpeciesLadder | LadderRefusal:
    """Complete ordered molblocks, or a refusal that names why pictures are omitted."""
    ordered = tuple(records)
    if not ordered:
        return LadderRefusal("no_sites", "There are no predicted sites to build a protonation ladder from.")
    if len(ordered) > MAX_PICTURE_SITES:
        return LadderRefusal(
            "too_many_sites",
            f"Pictures are omitted above {MAX_PICTURE_SITES} ionisable sites; the chart and table stay.",
        )
    if any(atom.GetAtomicNum() == 1 for atom in parent.GetAtoms()):
        return LadderRefusal(
            "explicit_hydrogens",
            "The drawing already has explicit hydrogen atoms, so proton counts cannot be applied without duplicating them.",
        )

    indices = [record.atom_index for record in ordered]
    if any(index is None for index in indices):
        return LadderRefusal("unmapped", "A predicted site could not be mapped onto an atom of this drawing.")
    if any(record.kind == UNKNOWN for record in ordered):
        return LadderRefusal("unknown_direction", "A predicted site has no acid/base direction, so no protonation ladder is drawn.")
    if any(record.protonated_site is None or record.deprotonated_site is None for record in ordered):
        return LadderRefusal("missing_state", "A predicted site is missing its protonated or deprotonated atom state.")
    if len(set(indices)) != len(indices):
        return LadderRefusal(
            "same_atom",
            "Two predictions map to the same drawing atom, so a sequential ladder would be ambiguous.",
        )

    n_acids, n_bases = classify_ionizable_centres(parent)
    kind_acids = sum(1 for record in ordered if record.kind == ACID)
    kind_bases = sum(1 for record in ordered if record.kind == BASE)
    kinds_match_curve = kind_acids == n_acids and kind_bases == n_bases

    parent_heavy = _heavy_signature(parent)
    try:
        current = Chem.Mol(parent)
        for record in ordered:
            _apply_state(current, record.atom_index, record.protonated_site)
        current = _sanitize(current)
        if _heavy_signature(current) != parent_heavy:
            return LadderRefusal("identity", "Applying the protonated sites changed which heavy atoms are present.")
        blocks = [_molblock(current)]
        charges = [int(Chem.GetFormalCharge(current))]
        for record in ordered:
            current = Chem.Mol(current)
            _apply_state(current, record.atom_index, record.deprotonated_site)
            current = _sanitize(current)
            if _heavy_signature(current) != parent_heavy:
                return LadderRefusal("identity", "A dissociation step changed which heavy atoms are present.")
            blocks.append(_molblock(current))
            charges.append(int(Chem.GetFormalCharge(current)))
    except ValueError as exc:
        reason = str(exc) or "build"
        return LadderRefusal(reason, "The sequential structures could not be built from the stored site records.")

    if len(blocks) != len(ordered) + 1:
        return LadderRefusal("count", "The ladder did not produce one structure per sequential species.")

    expected = species_charges(n_acids, n_bases)
    permanent = int(Chem.GetFormalCharge(parent))
    # species_charges is the ionisable-centre offset only. A permanent charge
    # on the parent has to be added before those labels are molecular net charge.
    charge_labels_match = False
    if len(expected) == len(charges):
        charge_labels_match = all(
            charges[index] == expected[index] + permanent for index in range(len(charges))
        )

    return SpeciesLadder(
        molblocks=tuple(blocks),
        hidden=_hidden_species(ordered, ph_values),
        kinds_match_curve=kinds_match_curve,
        charge_labels_match=charge_labels_match,
        net_charges=tuple(charges),
    )
