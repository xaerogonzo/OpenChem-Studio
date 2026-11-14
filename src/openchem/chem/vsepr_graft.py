"""A hypervalent centre with organic groups on it: the core from the measured table, the groups grown on its ligands.

WHY THIS EXISTS. `vsepr_geometry.build_vsepr_geometry` places one centre with bare ligands (SF6, ClF3). Most hypervalent chemistry that is drawn has organic groups on
the centre: triphenyldifluorophosphorane, a methyl or a hydrogen on phosphorus, an iodine(III) reagent, an aryl-SF5. Distance geometry knows nothing of the five
bonds, so for these RDKit's embedding (measured 2026-11-13) gives the centre a wrong shape; and the organic groups cannot simply be left off.

THE METHOD, in four steps that each use something already trusted:

1. The centre's neighbours are its ligands. Each is a token (its element, "=" for a double bond): a methyl is "C", a hydrogen "H", an acetate oxygen "O". The table
   (`vsepr_geometry.REFERENCES`, keyed by those tokens) places the centre and ALL its ligands, exactly as for a bare core: the same placers, the same lengths, the same
   evidence tier. A hydrogen on the centre is a ligand and is placed there.
2. Every ligand that carries more atoms (everything bonded to it, away from the centre) is a SUBSTITUENT. It is cut out as its own small molecule with a hydrogen where the
   centre was (phenyl becomes benzene, an acetate oxygen becomes acetic acid), embedded and optimised by the ordinary route, where RDKit is reliable.
3. Each substituent is put back: its ligand atom on the core's position, its hydrogen cap along the bond to the centre, and turned about that bond to the angle with the
   fewest clashes with what is already placed. Different seeds and angle choices give different conformers; none has an energy.
4. Nothing is relaxed afterwards (a force field has no terms for the five-bond centre), so the core is exactly the table's.

WHAT IT REFUSES, by saying nothing (the caller falls back to the ordinary path, as before this module existed): a molecule with no row in the table for its core; one that
RDKit cannot read (a centre such as Cl with three bonds and organic groups); a ring that closes through the centre or two hypervalent centres. It never estimates a length.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

from openchem.chem.vsepr_geometry import (
    Kind,
    VseprGeometry,
    VseprOutcome,
    _bonding_electrons,
    _diagnostics,
    evidence_phrase,
    place_core,
    validate,
)

#: Conformers returned for one molecule: seeds 0 to this minus one. Each has no energy; the pipeline's own pruning keeps the distinct ones.
MAX_CONFORMERS = 8
#: Angles tried for a substituent about its bond to the centre, degrees apart.
TORSION_STEP = 15
#: The smallest distance between two atoms that are not bonded and not on the same ligand that a placement may keep, Angstrom.
MIN_NONBONDED_DISTANCE = 1.0


def _is_hypervalent_centre(atom: Any, rules: dict[str, Any]) -> bool:
    rule = rules.get(atom.GetSymbol())
    if not rule:
        return False
    effective = _bonding_electrons(atom) - atom.GetFormalCharge()
    return effective in rule["permitted_valences"] and effective != rule["preferred_valence"]


def _unreadable(mol: Any) -> bool:
    """True when RDKit cannot add hydrogens to (and so cannot sanitise) `mol`."""
    from rdkit import Chem

    try:
        Chem.AddHs(Chem.Mol(mol))
        probe = Chem.Mol(mol)
        return Chem.SanitizeMol(probe, catchErrors=True) != Chem.SanitizeFlags.SANITIZE_NONE
    except Exception:  # noqa: BLE001 - an exception is as unreadable as a failed flag
        return True


def graft_outcome(mol: Any) -> VseprOutcome:
    """The grown geometry of a hypervalent centre with organic groups, or `NOT_APPLICABLE` when this module does not take it."""
    from rdkit import Chem

    from openchem.chem.checkers.valence import hypervalent_rules

    rules = hypervalent_rules()
    # Cheap exits first: only molecules with a hypervalent-table centre at all, and not an oxo-only ordinary case, are looked at.
    if not any(rules.get(a.GetSymbol()) for a in mol.GetAtoms()):
        return VseprOutcome(Kind.NOT_APPLICABLE, "no atom of a hypervalent-table element")
    if _unreadable(mol):
        return VseprOutcome(Kind.NOT_APPLICABLE, "RDKit cannot read the structure, so its organic groups are not grown here")
    mol_h = Chem.AddHs(Chem.Mol(mol))
    centres = [a.GetIdx() for a in mol_h.GetAtoms() if _is_hypervalent_centre(a, rules)]
    if len(centres) != 1:
        return VseprOutcome(Kind.NOT_APPLICABLE, "not exactly one hypervalent centre")
    centre_index = centres[0]
    ligands = [n.GetIdx() for n in mol_h.GetAtomWithIdx(centre_index).GetNeighbors()]
    core = place_core(mol_h, centre_index, ligands)
    if isinstance(core, VseprOutcome):
        # No row for this core (or an ordinary oxo case): the ordinary path keeps it, as before.
        return VseprOutcome(Kind.NOT_APPLICABLE, f"no measured core: {core.reason}")

    core = dataclasses.replace(core, reference=graft_evidence(mol_h, ligands, core.reference))
    grafts = _substituents(mol_h, centre_index, ligands)
    if isinstance(grafts, str):
        return VseprOutcome(Kind.NOT_APPLICABLE, grafts)

    conformers: list[tuple[tuple[float, float, float], ...]] = []
    # Without a substituent there is nothing to vary: one conformer (the core with its hydrogens).
    for seed in range(MAX_CONFORMERS if grafts else 1):
        placed = _assemble(mol_h, core, grafts, seed)
        if placed is None:
            if seed == 0:
                return VseprOutcome(Kind.NOT_APPLICABLE, "the organic groups could not be placed without clashes")
            continue
        conformers.append(placed)
    geometry = VseprGeometry(
        coordinates=conformers[0],
        centre_index=centre_index,
        ligand_indices=tuple(ligands),
        classification=core.classification,
        shape=core.shape,
        axial_indices=core.axial_indices,
        equatorial_indices=core.equatorial_indices,
        reference=core.reference,
        ligand_lengths=core.ligand_lengths,
        provenance=(
            f"idealised VSEPR core with {evidence_phrase(core.reference)} and organic groups grown on its ligands; not optimised, no energy"
        ),
    )
    problems = validate(geometry)
    if problems:
        return VseprOutcome(Kind.NOT_APPLICABLE, "the grown geometry failed its own checks: " + "; ".join(problems))
    return VseprOutcome(
        Kind.BUILT,
        geometry=VseprGeometry(**{**geometry.__dict__, "diagnostics": _diagnostics(geometry)}),
        molecule=mol_h,
        alternatives=tuple(conformers[1:]),
    )


def graft_evidence(mol_h: Any, ligands: list[int], reference: Any) -> Any:
    """`reference`, or the same row downgraded to an ESTIMATE when its measurement does not cover this molecule's carbon ligands.

    Triphenyldifluorophosphorane was measured, not every trialkyl- or triarylphosphorane: a row with a `scope` ("aromatic" or "methyl") is a measurement only for carbon ligands of
    that kind, and a molecule whose carbon ligands are another kind gets the same lengths as a transfer, said as such.
    """
    if not reference.scope or reference.evidence != "measured":
        return reference
    scopes = {part.strip() for part in reference.scope.split(",")}

    def covered(atom: Any) -> bool:
        if atom.GetSymbol() == "C":
            if "aromatic" in scopes:
                return bool(atom.GetIsAromatic())
            if "methyl" in scopes:
                return not atom.GetIsAromatic() and sum(1 for n in atom.GetNeighbors() if n.GetSymbol() == "H") == 3 and atom.GetDegree() == 4
        if atom.GetSymbol() == "O" and "acyloxy" in scopes:
            # an oxygen on a carbon that carries a double-bonded oxygen: a carboxylate
            return any(
                n.GetSymbol() == "C" and any(b.GetBondTypeAsDouble() == 2.0 and b.GetOtherAtom(n).GetSymbol() == "O" for b in n.GetBonds())
                for n in atom.GetNeighbors()
            )
        return True

    if all(covered(mol_h.GetAtomWithIdx(i)) for i in ligands):
        return reference
    return dataclasses.replace(
        reference,
        evidence="estimated",
        method="ESTIMATED by transfer to other ligands than the measured kind: " + reference.method,
    )


def _substituents(mol_h: Any, centre_index: int, ligands: list[int]) -> dict[int, set[int]] | str:
    """For each ligand with atoms beyond it, the set of those atoms (hydrogens included); or a sentence when the molecule is not buildable this way."""
    grafts: dict[int, set[int]] = {}
    seen_global: set[int] = set()
    for ligand in ligands:
        if mol_h.GetAtomWithIdx(ligand).GetDegree() == 1:
            continue
        reach = {ligand}
        frontier = [ligand]
        while frontier:
            current = frontier.pop()
            for neighbour in mol_h.GetAtomWithIdx(current).GetNeighbors():
                index = neighbour.GetIdx()
                if index == centre_index or index in reach:
                    continue
                if index in ligands:
                    return "a ring closes through the hypervalent centre"
                reach.add(index)
                frontier.append(index)
        if reach & seen_global:
            return "two ligands share atoms beyond the centre"
        seen_global |= reach
        grafts[ligand] = reach
    return grafts


def _fragment(mol_h: Any, ligand: int, members: set[int], seed: int) -> tuple[Any, dict[int, int], int] | None:
    """The substituent as a stand-alone molecule with a hydrogen cap in the centre's place, embedded; with the map from its atoms to the drawing's and the cap's index."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    rw = Chem.RWMol(mol_h)
    for atom in rw.GetAtoms():
        atom.SetIntProp("_orig", atom.GetIdx())
    for index in sorted((i for i in range(rw.GetNumAtoms()) if i not in members), reverse=True):
        rw.RemoveAtom(index)
    new_ligand = next(a.GetIdx() for a in rw.GetAtoms() if a.GetIntProp("_orig") == ligand)
    cap = rw.AddAtom(Chem.Atom(1))
    rw.AddBond(new_ligand, cap, Chem.BondType.SINGLE)
    fragment = rw.GetMol()
    try:
        Chem.SanitizeMol(fragment)
    except Exception:  # noqa: BLE001 - a substituent RDKit cannot read is a reason to leave the molecule alone
        return None
    if AllChem.EmbedMolecule(fragment, randomSeed=seed + 1, useRandomCoords=True) != 0:
        return None
    try:
        if AllChem.MMFFHasAllMoleculeParams(fragment):
            AllChem.MMFFOptimizeMolecule(fragment, maxIters=500)
        elif AllChem.UFFHasAllMoleculeParams(fragment):
            AllChem.UFFOptimizeMolecule(fragment, maxIters=500)
    except Exception:  # noqa: BLE001 - an unoptimised embedding is still a usable fragment
        pass
    mapping = {a.GetIdx(): a.GetIntProp("_orig") for a in fragment.GetAtoms() if a.HasProp("_orig")}
    return fragment, mapping, cap


def _rotation_aligning(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The rotation matrix taking unit vector `a` onto unit vector `b`."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        if c > 0:
            return np.eye(3)
        axis = np.cross(a, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, np.array([0.0, 1.0, 0.0]))
        return _rotation_about(axis, math.pi)
    k = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + k + k @ k * (1.0 / (1.0 + c))


def _rotation_about(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    k = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]])
    return np.eye(3) + math.sin(angle) * k + (1.0 - math.cos(angle)) * (k @ k)


def _clash(points: np.ndarray, others: np.ndarray, radii: np.ndarray, other_radii: np.ndarray) -> float:
    """A smooth penalty for atoms closer than 0.75 of their van der Waals sum (0 when none is)."""
    if len(others) == 0:
        return 0.0
    d = np.linalg.norm(points[:, None, :] - others[None, :, :], axis=2)
    limit = 0.75 * (radii[:, None] + other_radii[None, :])
    return float(np.sum(np.clip(limit - d, 0.0, None) ** 2))


def _assemble(mol_h: Any, core: Any, grafts: dict[int, set[int]], seed: int) -> tuple[tuple[float, float, float], ...] | None:
    """All atoms' coordinates for conformer number `seed`, or None when a substituent cannot be placed without a clash."""
    from rdkit import Chem

    table = Chem.GetPeriodicTable()
    n = mol_h.GetNumAtoms()
    positions: dict[int, np.ndarray] = {i: np.array(p, dtype=float) for i, p in core.coordinates.items()}
    centre = np.array(core.coordinates[core.centre_index], dtype=float)
    rng = np.random.default_rng(20261114 + seed)
    # Larger substituents first: they have the fewest places to go.
    for ligand in sorted(grafts, key=lambda lig: -len(grafts[lig])):
        built = _fragment(mol_h, ligand, grafts[ligand], seed)
        if built is None:
            return None
        fragment, mapping, cap = built
        conf = fragment.GetConformer()
        local = {i: np.array(conf.GetAtomPosition(i), dtype=float) for i in range(fragment.GetNumAtoms())}
        ligand_local = next(i for i, orig in mapping.items() if orig == ligand)
        anchor = positions[ligand]
        to_centre = centre - anchor
        base = _rotation_aligning(local[cap] - local[ligand_local], to_centre)
        axis = to_centre
        movers = [i for i in local if i != cap and i != ligand_local]
        radii = np.array([table.GetRvdw(fragment.GetAtomWithIdx(i).GetAtomicNum()) for i in movers])
        placed_indices = [i for i in positions if i != ligand]
        others = np.array([positions[i] for i in placed_indices]) if placed_indices else np.zeros((0, 3))
        other_radii = np.array([table.GetRvdw(mol_h.GetAtomWithIdx(i).GetAtomicNum()) for i in placed_indices])
        candidates: list[tuple[float, float, np.ndarray]] = []
        for angle in range(0, 360, TORSION_STEP):
            turn = _rotation_about(axis, math.radians(angle))
            points = np.array([anchor + turn @ (base @ (local[i] - local[ligand_local])) for i in movers])
            candidates.append((_clash(points, others, radii, other_radii), float(angle), points))
        candidates.sort(key=lambda item: item[0])
        best = candidates[0][0]
        # Conformer 0 takes the least clashing angle; later ones draw among the angles about as good, so the set differs.
        pool = [c for c in candidates if c[0] <= best + 0.5] if seed else candidates[:1]
        penalty, _angle, points = pool[int(rng.integers(len(pool)))]
        if penalty > 25.0:
            return None
        for i, point in zip(movers, points):
            positions[mapping[i]] = point
    if len(positions) != n:
        return None
    coordinates = np.array([positions[i] for i in range(n)])
    # A last check no angle choice can repair: atoms that are not bonded and have been put on top of each other.
    topological = Chem.GetDistanceMatrix(mol_h)
    d = np.linalg.norm(coordinates[:, None, :] - coordinates[None, :, :], axis=2)
    close = (d < MIN_NONBONDED_DISTANCE) & (topological > 2) & (np.eye(n) == 0)
    if np.any(close):
        return None
    return tuple((float(x), float(y), float(z)) for x, y, z in coordinates)
