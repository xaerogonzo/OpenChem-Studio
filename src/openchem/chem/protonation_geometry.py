"""The dominant ionization state at a pH, ON A CONFORMER, with its geometry carried across.

`pka_providers.protonate_at_ph` rebuilds from SMILES, which carries no coordinates, so a 3D
calculator cannot use it: re-embedding would answer a different question from the one asked
("what are the charges on THIS conformer"). This module moves the protons instead.

Measured before it was written (2026-09-15, benchmarks/charges/protonation/preregistration.md):
the provider raises on an H-explicit molecule whose state loses a proton ("Atom 4 is drawn with a
hydrogen the protonated form removes"), and returns an added proton as an implicit H COUNT rather
than an atom with coordinates. Both gaps are closed here, and neither by re-deriving the atom
correspondence: `pka_providers.heavy_correspondence` already settles which atom is which.

**What moves:** only hydrogens this module adds. Every heavy atom and every retained hydrogen keeps
its coordinates bit-for-bit, asserted before and after the placement.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdForceFieldHelpers

from openchem.chem.engine import InvalidStructureError
from openchem.chem.pka_providers import dominant_microspecies

#: Bumped whenever the selection or tie-breaking rules below change, so a stored result says which
#: rules produced it. A guard test hashes the decision table against this.
PROTONATION_SELECTION_POLICY_VERSION = 1

#: Several hydrogens on the changed atom are not equivalent, so which one is removed would be a
#: choice nothing in the source makes.
REFUSE_AMBIGUOUS_H_IDENTITY = "REFUSE_AMBIGUOUS_H_IDENTITY"
#: The selected state differs from the drawing by more than protons at heavy atoms.
REFUSE_NOT_IONISATION_ONLY = "REFUSE_NOT_IONISATION_ONLY"
#: MMFF94 could not type the species, or the placement did not converge.
REFUSE_H_PLACEMENT = "REFUSE_H_PLACEMENT"
#: Dimorphite-DL (or the correspondence behind it) could not answer for this structure.
REFUSE_PROTONATION_FAILED = "REFUSE_PROTONATION_FAILED"

#: MMFF settings, pinned. 94 rather than 94s, so the placement is reproducible across releases.
MMFF_VARIANT = "MMFF94"
#: Iterations allowed for the added hydrogens; RDKit's own default gradient tolerance decides
#: convergence, and a run that does not converge is REFUSE_H_PLACEMENT rather than a placed guess.
MMFF_MAX_ITERATIONS = 2000


@dataclass(frozen=True)
class SiteChange:
    """One proton at one heavy atom. Nothing else is representable, which is the point.

    `delta_h` is +1 for an added proton and -1 for a removed one, and `delta_charge` equals it --
    per site, not merely in total. Glycine at 7.4 is why: its two sites cancel, so a total-only
    record would call a zwitterion "no change".
    """

    heavy_atom: int
    removed_hydrogen: int | None
    delta_h: int
    delta_charge: int


@dataclass(frozen=True)
class ProtonatedConformer:
    """The state at a pH, on the caller's own geometry, or a refusal saying why not."""

    mol: Chem.Mol | None = None
    source_heavy_map: tuple[tuple[int, int], ...] = ()
    site_changes: tuple[SiteChange, ...] = ()
    placed_hydrogens: tuple[int, ...] = ()
    state_id: str = ""
    refusal: str = ""
    message: str = ""
    #: Which hydrogen was removed at a site whose candidates were equivalent, recorded because the
    #: rule picked it rather than the source naming it.
    recorded_choices: tuple[tuple[int, int], ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.site_changes)


def _heavy_copy(mol: Chem.Mol) -> tuple[Chem.Mol, list[int]]:
    """The molecule with its hydrogens folded into counts, plus the source id of each heavy atom.

    Built by hand rather than with `RemoveHs` so the correspondence is a fact of construction:
    heavy atom k of the copy IS source atom `heavy[k]`.
    """
    heavy = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() != 1]
    position = {index: k for k, index in enumerate(heavy)}
    copy = Chem.RWMol()
    for index in heavy:
        source = mol.GetAtomWithIdx(index)
        atom = Chem.Atom(source.GetAtomicNum())
        atom.SetFormalCharge(source.GetFormalCharge())
        atom.SetIsotope(source.GetIsotope())
        atom.SetChiralTag(source.GetChiralTag())
        atom.SetAtomMapNum(source.GetAtomMapNum())
        atom.SetNoImplicit(True)
        atom.SetNumExplicitHs(sum(1 for n in source.GetNeighbors() if n.GetAtomicNum() == 1) + source.GetTotalNumHs())
        copy.AddAtom(atom)
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in position and b in position:
            copy.AddBond(position[a], position[b], bond.GetBondType())
    result = copy.GetMol()
    Chem.SanitizeMol(result)
    return result, heavy


def _site_changes(flat: Chem.Mol, state: Chem.Mol, heavy: list[int]) -> tuple[list[tuple[int, int, int]], str]:
    """Per heavy atom: (source id, delta H, delta charge), or a refusal code.

    `state` is index-aligned with `flat` by `restore_heavy_atom_order`'s contract, so this is a
    comparison and never a search.
    """
    changes = []
    for k, source_index in enumerate(heavy):
        before, after = flat.GetAtomWithIdx(k), state.GetAtomWithIdx(k)
        if before.GetAtomicNum() != after.GetAtomicNum() or before.GetIsotope() != after.GetIsotope():
            return [], REFUSE_NOT_IONISATION_ONLY
        delta_h = after.GetTotalNumHs() - before.GetTotalNumHs()
        delta_charge = after.GetFormalCharge() - before.GetFormalCharge()
        if delta_h == delta_charge == 0:
            continue
        if delta_h != delta_charge:
            # A proton carries its charge with it; anything else is not an ionisation.
            return [], REFUSE_NOT_IONISATION_ONLY
        changes.append((source_index, delta_h, delta_charge))
    return changes, ""


def _equivalent_hydrogens(mol: Chem.Mol, parent: int, candidates: list[int]) -> bool:
    """Whether the candidate hydrogens on `parent` are interchangeable in the SOURCE structure.

    **CANONICAL RANKING IS NOT THE TEST, AND USING IT WOULD HAVE BEEN SILENT.** Measured while
    writing this: `CanonicalRankAtoms(breakTies=False, includeChirality=True)` gives the two
    hydrogens of a CH2 beside a stereocentre the SAME rank, so a rank test calls a prochiral pair
    equivalent and picks one. Labelling one and re-serialising fails the same way, because the
    label creates a stereocentre RDKit then leaves unassigned, and both labellings print alike.

    The question that separates them is prochirality itself: label one candidate and ask whether
    the parent becomes a potential tetrahedral stereocentre. Measured on the cases that matter:

        C[NH3+]        N, 3 H   -> no      equivalent, any may go
        CC             C, 3 H   -> no      equivalent
        C[C@H](N)CO    CH2      -> YES     diastereotopic, refuse
        OCC(N)C(=O)O   CH2      -> YES     refuse

    Enantiotopic pairs on an otherwise symmetric atom (propane's CH2) stay equivalent, which is
    right: removing either gives the same structure.
    """
    for index in candidates:
        copy = Chem.Mol(mol)
        copy.GetAtomWithIdx(index).SetIsotope(2)
        Chem.SanitizeMol(copy)
        found = Chem.FindPotentialStereo(copy)
        if any(element.type == Chem.StereoType.Atom_Tetrahedral and element.centeredOn == parent
               for element in found):
            return False
    return True


def _state_id(state: Chem.Mol, ph: float, changes: tuple[SiteChange, ...]) -> str:
    payload = {
        "smiles": Chem.MolToSmiles(state),
        "ph": round(float(ph), 6),
        "sites": [[c.heavy_atom, c.removed_hydrogen, c.delta_h, c.delta_charge] for c in changes],
        "policy": PROTONATION_SELECTION_POLICY_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _build(mol: Chem.Mol, state: Chem.Mol, heavy: list[int], removals: dict[int, list[int]],
           additions: dict[int, int]) -> tuple[Chem.Mol, dict[int, int]]:
    """The target molecule: every kept atom, in source order, with the state's charges and bonds.

    Coordinates are copied here, not re-embedded, and the caller asserts they are bit-identical.
    """
    removed = {index for indices in removals.values() for index in indices}
    kept = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetIdx() not in removed]
    position = {index: k for k, index in enumerate(kept)}
    state_of = {source: k for k, source in enumerate(heavy)}

    built = Chem.RWMol()
    for index in kept:
        source = mol.GetAtomWithIdx(index)
        atom = Chem.Atom(source.GetAtomicNum())
        atom.SetIsotope(source.GetIsotope())
        atom.SetChiralTag(source.GetChiralTag())
        atom.SetAtomMapNum(source.GetAtomMapNum())
        atom.SetNoImplicit(True)
        if index in state_of:
            made = state.GetAtomWithIdx(state_of[index])
            atom.SetFormalCharge(made.GetFormalCharge())
            atom.SetIsAromatic(made.GetIsAromatic())
            # Only the hydrogens this call adds are implicit for now; AddHs turns them into atoms.
            atom.SetNumExplicitHs(additions.get(index, 0))
        built.AddAtom(atom)

    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in removed or b in removed:
            continue
        if a in state_of and b in state_of:
            made = state.GetBondBetweenAtoms(state_of[a], state_of[b])
            built.AddBond(position[a], position[b], made.GetBondType())
            built.GetBondBetweenAtoms(position[a], position[b]).SetIsAromatic(made.GetIsAromatic())
        else:
            built.AddBond(position[a], position[b], Chem.BondType.SINGLE)

    result = built.GetMol()
    Chem.SanitizeMol(result)
    conformer = Chem.Conformer(result.GetNumAtoms())
    source_conformer = mol.GetConformer()
    for index in kept:
        conformer.SetAtomPosition(position[index], source_conformer.GetAtomPosition(index))
    result.RemoveAllConformers()
    result.AddConformer(conformer, assignId=True)
    return result, position


def _place_hydrogens(mol: Chem.Mol, fixed: int) -> str:
    """Minimise ONLY the atoms from `fixed` onward (the ones `AddHs` appended), or a refusal code.

    Every earlier atom is a fixed point of the force field, which is what makes the coordinate gate
    an equality rather than a tolerance.
    """
    properties = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant=MMFF_VARIANT)
    if properties is None:
        return REFUSE_H_PLACEMENT
    field = AllChem.MMFFGetMoleculeForceField(mol, properties)
    if field is None:
        return REFUSE_H_PLACEMENT
    for index in range(fixed):
        field.AddFixedPoint(index)
    field.Initialize()
    if field.Minimize(maxIts=MMFF_MAX_ITERATIONS) != 0:
        return REFUSE_H_PLACEMENT
    return ""


def protonate_conformer(mol: Chem.Mol, ph: float) -> ProtonatedConformer:
    """The dominant state at `ph`, on `mol`'s own coordinates.

    `mol` must carry explicit hydrogens and one conformer -- what a 3D calculator always has.
    """
    if mol.GetNumConformers() == 0:
        return ProtonatedConformer(refusal=REFUSE_PROTONATION_FAILED, message="The structure has no conformer.")
    flat, heavy = _heavy_copy(mol)
    try:
        selected = dominant_microspecies(flat, ph)
    except InvalidStructureError as exc:
        return ProtonatedConformer(refusal=REFUSE_PROTONATION_FAILED, message=str(exc))

    raw_changes, refusal = _site_changes(flat, selected.mol, heavy)
    if refusal:
        return ProtonatedConformer(refusal=refusal, message="The state at this pH differs from the drawing by more than protons.")

    removals: dict[int, list[int]] = {}
    additions: dict[int, int] = {}
    changes: list[SiteChange] = []
    recorded: list[tuple[int, int]] = []
    for source_index, delta_h, delta_charge in raw_changes:
        if delta_h > 0:
            additions[source_index] = delta_h
            changes.append(SiteChange(source_index, None, delta_h, delta_charge))
            continue
        candidates = sorted(n.GetIdx() for n in mol.GetAtomWithIdx(source_index).GetNeighbors() if n.GetAtomicNum() == 1)
        if len(candidates) < -delta_h:
            return ProtonatedConformer(refusal=REFUSE_NOT_IONISATION_ONLY,
                                       message=f"Atom {source_index + 1} loses more hydrogens than it carries.")
        if len(candidates) > 1 and not _equivalent_hydrogens(mol, source_index, candidates):
            return ProtonatedConformer(
                refusal=REFUSE_AMBIGUOUS_H_IDENTITY,
                message=(f"Atom {source_index + 1} carries {len(candidates)} hydrogens that are not equivalent, "
                         "so which one this pH removes is not determined by the structure."))
        chosen = candidates[: -delta_h]
        removals[source_index] = chosen
        for index in chosen:
            changes.append(SiteChange(source_index, index, -1, -1))
            if len(candidates) > 1:
                recorded.append((source_index, index))

    built, position = _build(mol, selected.mol, heavy, removals, additions)
    before = np.array(built.GetConformer().GetPositions(), dtype=float)
    kept_count = built.GetNumAtoms()

    if additions:
        built = Chem.AddHs(built, onlyOnAtoms=[position[i] for i in additions], addCoords=True)
        moved = np.array(built.GetConformer().GetPositions(), dtype=float)[:kept_count]
        if not np.array_equal(moved, before):  # the gate, before any minimisation
            raise AssertionError("AddHs moved an existing atom")
        refusal = _place_hydrogens(built, kept_count)
        if refusal:
            return ProtonatedConformer(refusal=refusal,
                                       message="MMFF94 could not place the added hydrogens on this structure.")
        after = np.array(built.GetConformer().GetPositions(), dtype=float)[:kept_count]
        if not np.array_equal(after, before):
            raise AssertionError("the hydrogen placement moved an atom it was told to hold fixed")

    ordered = tuple(sorted(changes, key=lambda c: (c.heavy_atom, c.removed_hydrogen or -1)))
    return ProtonatedConformer(
        mol=built,
        source_heavy_map=tuple((index, position[index]) for index in heavy if index in position),
        site_changes=ordered,
        placed_hydrogens=tuple(range(kept_count, built.GetNumAtoms())),
        state_id=_state_id(selected.mol, ph, ordered),
        recorded_choices=tuple(recorded),
    )
