"""
iupac_namer/ring_naming/retained_modified.py

Naming round 24 -- a retained polycyclic parent that is MODIFIED by ring unsaturation
and/or one ether bridge: ``4,5-epoxy-7,8-didehydromorphinan`` (morphine's parent).

Background
----------
Blue Book P-101.2 keeps ``morphinan`` as a fundamental parent of the natural products. The
retained-name lookup matches the ring system's skeleton exactly, so it names a saturated
morphinan (levorphanol) and misses every member that has a ring double bond or the 4,5-ether
bridge -- which is morphine, codeine, heroin, hydromorphone, oxycodone, naloxone: the
whole family. Those fell to a von Baeyer pentacycle, a valid name nobody uses.

The book names them on the retained parent (BlueBookV2.pdf p. 66, P-13.8.1.1):

    morphine  4,5α-epoxy-17-methyl-7,8-didehydromorphinan-3,6α-diol

* ``a,b-epoxy`` is a DETACHABLE bridge prefix, cited alphabetically with the substituents
  ("4,5-epoxy-3-methoxy-17-methyl-..."), which is why it travels on
  ``NamedParent.bridge_prefixes`` and is sorted by ``_assemble_substitutive`` rather than baked
  into the parent name (the methylenedioxy bridge bakes it in, and so cannot interleave).
* ``didehydro`` is detachable but NOT alphabetized: it sits immediately before the parent, so it
  IS part of the parent name here.

Scope: only parents named in ``_MODIFIABLE``, whose skeleton is saturated apart from an aromatic
ring. Anything else returns ``[]`` and the caller falls back as before.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rdkit import Chem

from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES
from openchem.vendor.iupac_namer.types import Locant, NamedParent, Numbering

if TYPE_CHECKING:
    from openchem.vendor.iupac_namer.types import CandidateParent, RingSystem

logger = logging.getLogger(__name__)

#: Retained parents whose names accept ``didehydro`` and an ``epoxy`` bridge. A parent is added
#: only when the Blue Book prints such a name for it (morphinan: P-13.8.1.1, p. 66).
_MODIFIABLE = frozenset({"morphinan"})

#: didehydro multiplicity: 2 locants -> didehydro, 4 -> tetradehydro, ...
_DEHYDRO = {2: "didehydro", 4: "tetradehydro", 6: "hexadehydro", 8: "octadehydro"}


def _keys_for(name: str) -> list[tuple[str, dict]]:
    return [(smi, rec) for smi, rec in _RING_CURATED_SMILES.items()
            if rec.get("name") == name and rec.get("atom_locants")]


def _epoxy_oxygens(ring_atoms: frozenset[int], mol) -> list[int]:
    """Neutral, non-aromatic two-coordinate oxygens whose both neighbours are ring-system atoms."""
    found = []
    for idx in sorted(ring_atoms):
        a = mol.GetAtomWithIdx(idx)
        if a.GetAtomicNum() != 8 or a.GetFormalCharge() or a.GetIsAromatic() or a.GetDegree() != 2:
            continue
        if all(n.GetIdx() in ring_atoms for n in a.GetNeighbors()):
            found.append(idx)
    return found


def _base_mol(base_atoms: frozenset[int], mol):
    """The parent skeleton as a fresh molecule, and the ring double bonds that were flattened.

    Aromatic bonds stay aromatic; a non-aromatic double bond becomes single and is RECORDED (it is
    a ``didehydro``); a triple bond or a charge makes the system unsupported (returns None).
    """
    order = sorted(base_atoms)
    where = {a: i for i, a in enumerate(order)}
    rw = Chem.RWMol()
    for a in order:
        src = mol.GetAtomWithIdx(a)
        if src.GetFormalCharge():
            return None
        new = Chem.Atom(src.GetAtomicNum())
        new.SetIsAromatic(src.GetIsAromatic())
        rw.AddAtom(new)
    doubles: list[tuple[int, int]] = []
    for b in mol.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        if i not in where or j not in where:
            continue
        if b.GetIsAromatic():
            rw.AddBond(where[i], where[j], Chem.BondType.AROMATIC)
            rw.GetBondBetweenAtoms(where[i], where[j]).SetIsAromatic(True)
        elif b.GetBondType() == Chem.BondType.SINGLE:
            rw.AddBond(where[i], where[j], Chem.BondType.SINGLE)
        elif b.GetBondType() == Chem.BondType.DOUBLE:
            rw.AddBond(where[i], where[j], Chem.BondType.SINGLE)
            doubles.append((i, j))
        else:
            return None
    base = rw.GetMol()
    if Chem.SanitizeMol(base, catchErrors=True) != Chem.SanitizeFlags.SANITIZE_NONE:
        return None
    return base, order, doubles


def name_retained_modified(
    ring_system: "RingSystem",
    candidate: "CandidateParent",
    mol,
) -> list[NamedParent]:
    """``[epoxy-][didehydro-]<retained parent>``, or ``[]`` when this is not that shape."""
    if ring_system.type not in ("fused", "bridged"):
        return []
    ring_atoms = frozenset(ring_system.atom_indices)

    # No bridge, or exactly one ether bridge.
    options: list[int | None] = [None] + list(_epoxy_oxygens(ring_atoms, mol))
    for oxygen in options:
        base_atoms = ring_atoms - ({oxygen} if oxygen is not None else set())
        built = _base_mol(base_atoms, mol)
        if built is None:
            continue
        base, order, doubles = built
        base_smiles = Chem.MolToSmiles(base)
        for name in sorted(_MODIFIABLE):
            for key_smiles, record in _keys_for(name):
                key = Chem.MolFromSmiles(key_smiles)
                if key is None or Chem.MolToSmiles(key) != base_smiles:
                    continue
                if oxygen is None and not doubles:
                    continue  # the plain retained lookup already names this exactly
                parent = _name_from_match(
                    ring_system, candidate, mol, name, record, key, base, order, doubles, oxygen)
                if parent:
                    return [parent]
    return []


def _name_from_match(ring_system, candidate, mol, name, record, key, base, order, doubles, oxygen):
    atom_locants = record["atom_locants"]
    best = None
    for match in base.GetSubstructMatches(key, uniquify=False, maxMatches=64):
        # match[k] = base index of key atom k; base index i is full-molecule atom order[i]
        to_loc = {order[match[k]]: loc for k, loc in atom_locants.items() if k < len(match)}
        if not all(isinstance(v, int) for v in to_loc.values()):
            continue
        ep = None
        if oxygen is not None:
            nbrs = sorted(to_loc[n.GetIdx()] for n in mol.GetAtomWithIdx(oxygen).GetNeighbors())
            ep = tuple(nbrs)
        dehydro: list[int] = []
        for i, j in doubles:
            dehydro.extend((to_loc[i], to_loc[j]))  # doubles hold FULL-molecule atom indices
        if len(dehydro) != len(set(dehydro)):
            continue  # a cumulated double bond has no didehydro reading
        rank = (ep or (), tuple(sorted(dehydro)))
        if best is None or rank < best[0]:
            best = (rank, to_loc, ep, tuple(sorted(dehydro)))
    if best is None:
        return None
    _rank, to_loc, ep, dehydro = best
    if dehydro and len(dehydro) not in _DEHYDRO:
        return None

    parent_name = name
    if dehydro:
        parent_name = f"{','.join(map(str, dehydro))}-{_DEHYDRO[len(dehydro)]}{name}"

    assignments = tuple(sorted(
        ((a, Locant.numeric(l)) for a, l in to_loc.items()), key=lambda kv: kv[1]._numeric_value or 0))
    numbering = Numbering(_assignments=assignments, locant_set=tuple(l for _, l in assignments))
    bridge = ((("epoxy", tuple(Locant.numeric(l) for l in ep)),) if ep else ())
    return NamedParent(
        candidate=candidate,
        name=parent_name,
        stem=parent_name,
        alkyl_stem=None,
        naming_method="retained_modified",
        indicated_hydrogen=None,
        numbering_options=(numbering,),
        bridge_prefixes=bridge,
    )


__all__ = ["name_retained_modified"]
