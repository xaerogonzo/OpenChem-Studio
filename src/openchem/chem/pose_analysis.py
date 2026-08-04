from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from rdkit import Chem

# Heavy-atom-to-heavy-atom distance heuristic for a "polar contact" --
# deliberately NOT a true donor-H...acceptor angle check: the receptor has
# no experimental hydrogen positions (they'd have to be added
# geometrically, same as receptor prep already does for docking itself),
# so an angle computed from placed-not-observed hydrogens would look more
# precise than it actually is. This is the same simplification common
# quick-analysis tools (e.g. PyMOL's default polar contacts) use -- a
# heavy-atom distance cutoff, no angle, symmetric on both sides (doesn't
# try to distinguish donor from acceptor).
HBOND_DISTANCE_CUTOFF = 3.5  # Angstrom
CLASH_TOLERANCE = 0.4  # Angstrom subtracted from summed van der Waals radii

# The remaining interaction cutoffs, in Angstrom. They live HERE rather
# than in `interaction_analysis` because that module already imports from
# this one -- the dependency runs one way and putting them the other way
# round is an import cycle. The physics is identical whether the two atoms
# are in one molecule or two, so both callers share these values.
SALT_BRIDGE_CUTOFF = 4.0  # charged-group centre separation
PI_STACKING_CUTOFF = 5.5  # aromatic ring centroid separation
CATION_PI_CUTOFF = 6.0  # cation to aromatic centroid
HYDROPHOBIC_CUTOFF = 4.5  # apolar carbon to apolar carbon
METAL_COORDINATION_CUTOFF = 2.8  # metal ion to coordinating N/O/S

_METALS = {"ZN", "MG", "CA", "FE", "MN", "CU", "NA", "K", "CO", "NI"}
_POLAR_ELEMENTS = {"N", "O", "F"}

# Bondi van der Waals radii (Angstrom) for elements likely to appear in a
# docking receptor/ligand -- anything else falls back to
# _DEFAULT_VDW_RADIUS.
_VDW_RADII = {
    "H": 1.10, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80,
    "F": 1.47, "CL": 1.75, "BR": 1.85, "I": 1.98, "ZN": 1.39, "MG": 1.73,
    "CA": 2.31, "FE": 1.56, "NA": 2.27, "K": 2.75,
}
_DEFAULT_VDW_RADIUS = 1.70

Position = tuple[float, float, float]


@dataclass(slots=True)
class ReceptorAtom:
    element: str
    position: Position
    residue_name: str
    residue_number: int
    #: The PDB atom name (CA, CZ, NH1, OD2 ...), stripped. Needed for
    #: anything beyond a distance: a PHE ring centroid is CG/CD1/CD2/
    #: CE1/CE2/CZ, and averaging every carbon in the residue instead pulls
    #: the centre off the ring by including CA and CB. Empty when the
    #: source had no atom names, in which case the detectors that need
    #: them simply find nothing rather than guessing.
    atom_name: str = ""


def receptor_atoms_from_structure(structure_text: str, source_format: str) -> list[ReceptorAtom]:
    """Plain (position, element, residue) data for the receptor, via Open
    Babel -- already this codebase's receptor parser
    (chem/docking_providers.py), format-agnostic across PDB/mmCIF, unlike
    RDKit's own `MolFromPDBBlock` (PDB only -- the installed RDKit version
    has no mmCIF block reader, confirmed directly). Parse once per docking
    job and reuse across every pose, not once per pose.
    """
    from openbabel import pybel

    table = Chem.GetPeriodicTable()
    mol = pybel.readstring(source_format, structure_text)
    atoms = []
    for atom in mol.atoms:
        if atom.atomicnum == 0:
            continue
        residue = atom.residue
        # Open Babel keeps the PDB atom name on the residue, not the atom
        # -- confirmed live: `residue.OBResidue.GetAtomID(atom.OBAtom)`
        # returns " CD1" (padded, hence the strip).
        atom_name = ""
        if residue is not None:
            ob_residue = getattr(residue, "OBResidue", None)
            if ob_residue is not None:
                try:
                    atom_name = ob_residue.GetAtomID(atom.OBAtom).strip()
                except Exception:  # noqa: BLE001 - a nameless atom is still a usable atom
                    atom_name = ""
        atoms.append(
            ReceptorAtom(
                element=table.GetElementSymbol(atom.atomicnum).upper(),
                position=atom.coords,
                residue_name=residue.name.strip() if residue else "",
                residue_number=_residue_number(residue),
                atom_name=atom_name,
            )
        )
    return atoms



def _residue_number(residue) -> int:
    """The residue number the STRUCTURE FILE gives, not Open Babel's index.

    `residue.idx` is an internal 0-based counter, so a PDB's LYS 128 came
    back as 1. That was wrong everywhere it surfaced, and worst where it
    is invisible: `ui/visualization.py` builds labels like "TYR652" from
    this, and `resources/molstar/*.html` matches them against Mol*'s
    `auth_seq_id` -- the file's own numbering. Feeding an index into an
    auth_seq_id comparison meant the binding-site colouring highlighted
    whatever residue happened to sit at that index, or nothing at all.

    `GetNum()` is the file's number. Confirmed live: a PDB with residues
    57 and 128 reports idx 0/1 and GetNum 57/128.
    """
    if residue is None:
        return 0
    ob_residue = getattr(residue, "OBResidue", None)
    if ob_residue is not None:
        try:
            return int(ob_residue.GetNum())
        except Exception:  # noqa: BLE001 - fall back rather than fail a whole job
            pass
    return int(getattr(residue, "idx", 0))


def _ligand_heavy_atoms(pose_molblock: str) -> list[tuple[str, Position]]:
    mol = Chem.MolFromMolBlock(pose_molblock, sanitize=False, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return []
    conformer = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol().upper()
        if symbol == "H":
            continue
        pos = conformer.GetAtomPosition(atom.GetIdx())
        atoms.append((symbol, (pos.x, pos.y, pos.z)))
    return atoms


def _vdw_radius(element: str) -> float:
    return _VDW_RADII.get(element, _DEFAULT_VDW_RADIUS)



# --- Receptor feature perception ----------------------------------------
#
# Everything below identifies groups by RESIDUE AND ATOM NAME rather than
# by bond perception. That is deliberate and not a shortcut: the receptor
# arrives as coordinates from a PDB/mmCIF file with no reliable bond
# orders, and standard residues have standard atom names, which is exactly
# what the PDB naming convention is for. Anything non-standard -- a ligand
# in the receptor file, a modified residue -- simply contributes no
# features rather than being guessed at.
#
# Cutoffs are IMPORTED from `interaction_analysis`, not restated. The
# physics does not change between two atoms in one molecule and two atoms
# in different ones, and a second copy is how the two would drift apart.

#: Aromatic side-chain rings, by the atoms whose centroid IS the ring.
#: Tryptophan has two fused rings; the six-membered one is used, which is
#: the convention for pi-stacking geometry.
_AROMATIC_RINGS: dict[str, tuple[str, ...]] = {
    "PHE": ("CG", "CD1", "CD2", "CE1", "CE2", "CZ"),
    "TYR": ("CG", "CD1", "CD2", "CE1", "CE2", "CZ"),
    "TRP": ("CD2", "CE2", "CE3", "CZ2", "CZ3", "CH2"),
    "HIS": ("CG", "ND1", "CD2", "CE1", "NE2"),
}

#: Charged side-chain groups. HIS is included as a cation because it is
#: protonated at physiological pH often enough to matter, but it is the
#: least certain of these -- its pKa sits right at 6, so whether a given
#: histidine is charged depends on its environment, which coordinates
#: cannot tell us.
_CATION_GROUPS: dict[str, tuple[str, ...]] = {
    "ARG": ("NE", "NH1", "NH2"),
    "LYS": ("NZ",),
    "HIS": ("ND1", "NE2"),
}
_ANION_GROUPS: dict[str, tuple[str, ...]] = {
    "ASP": ("OD1", "OD2"),
    "GLU": ("OE1", "OE2"),
}

#: Side-chain carbons bonded to N or O, which are therefore NOT apolar
#: even though they are carbon. Listing the exceptions is shorter and
#: more legible than listing every apolar carbon, and the backbone
#: carbonyl carbon "C" is excluded for every residue.
_POLAR_CARBONS: dict[str, frozenset[str]] = {
    "ARG": frozenset({"CZ"}),
    "ASN": frozenset({"CG"}),
    "ASP": frozenset({"CG"}),
    "GLN": frozenset({"CD"}),
    "GLU": frozenset({"CD"}),
    "HIS": frozenset({"CG", "CD2", "CE1"}),
    "LYS": frozenset({"CE"}),
    "SER": frozenset({"CB"}),
    "THR": frozenset({"CB"}),
    "TRP": frozenset({"CD1", "CE2"}),
    "TYR": frozenset({"CZ"}),
}


@dataclass(frozen=True)
class _Group:
    """A named point on the receptor -- a ring centroid or a charge site."""

    residue: str
    position: Position


def _residues(receptor_atoms: list[ReceptorAtom]) -> dict[tuple[str, int], list[ReceptorAtom]]:
    grouped: dict[tuple[str, int], list[ReceptorAtom]] = {}
    for atom in receptor_atoms:
        grouped.setdefault((atom.residue_name, atom.residue_number), []).append(atom)
    return grouped


def _centroid(positions: list[Position]) -> Position:
    count = len(positions)
    return (
        sum(p[0] for p in positions) / count,
        sum(p[1] for p in positions) / count,
        sum(p[2] for p in positions) / count,
    )


def receptor_features(receptor_atoms: list[ReceptorAtom]) -> dict[str, list[_Group]]:
    """Aromatic ring centroids, charge sites and metals on the receptor.

    Computed ONCE per docking job and reused across poses, like the atom
    list itself -- a receptor does not move between poses, and re-deriving
    this per pose was the mistake `receptor_atoms_from_structure` already
    warns about.

    A ring only counts when EVERY one of its atoms is present. A partially
    resolved side chain would otherwise produce a centroid computed from
    three atoms and reported as if it were the ring.
    """
    rings: list[_Group] = []
    cations: list[_Group] = []
    anions: list[_Group] = []
    metals: list[_Group] = []

    for (name, number), atoms in _residues(receptor_atoms).items():
        label = f"{name}{number}"
        by_name = {atom.atom_name: atom for atom in atoms if atom.atom_name}

        wanted = _AROMATIC_RINGS.get(name)
        if wanted and all(atom_name in by_name for atom_name in wanted):
            rings.append(_Group(label, _centroid([by_name[a].position for a in wanted])))

        for table, sink in ((_CATION_GROUPS, cations), (_ANION_GROUPS, anions)):
            wanted = table.get(name)
            if wanted:
                present = [by_name[a].position for a in wanted if a in by_name]
                if present:
                    sink.append(_Group(label, _centroid(present)))

        for atom in atoms:
            if atom.element in _METALS:
                metals.append(_Group(label, atom.position))

    return {"rings": rings, "cations": cations, "anions": anions, "metals": metals}


def _is_apolar_receptor_carbon(atom: ReceptorAtom) -> bool:
    if atom.element != "C" or not atom.atom_name:
        return False
    if atom.atom_name == "C":  # the backbone carbonyl carbon
        return False
    return atom.atom_name not in _POLAR_CARBONS.get(atom.residue_name, frozenset())



def _ligand_features(pose_molblock: str) -> dict[str, Any]:
    """Apolar carbons, aromatic ring centroids and charge sites on the pose.

    The pose is parsed WITHOUT sanitization first, because a docked pose
    is geometry rather than a curated structure and a strict parse would
    reject perfectly usable output. Sanitization is then attempted purely
    to get ring and aromaticity perception; when it fails, the ring-based
    interactions simply find nothing rather than the whole analysis
    failing -- distances and clashes still work on any parse.
    """
    mol = Chem.MolFromMolBlock(pose_molblock, sanitize=False, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return {"apolar": [], "rings": [], "cations": [], "anions": [], "polar": []}
    conformer = mol.GetConformer()
    position = lambda index: tuple(conformer.GetAtomPosition(index))  # noqa: E731

    aromatic_ok = True
    try:
        Chem.SanitizeMol(mol)
    except Exception:  # noqa: BLE001 - geometry is still usable without perception
        aromatic_ok = False

    apolar, cations, anions, polar = [], [], [], []
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol().upper()
        if symbol == "H":
            continue
        index = atom.GetIdx()
        if symbol == "C":
            neighbours = {n.GetSymbol().upper() for n in atom.GetNeighbors()}
            if not (neighbours & _POLAR_ELEMENTS):
                apolar.append(position(index))
        if symbol in _POLAR_ELEMENTS or symbol == "S":
            polar.append((symbol, position(index)))
        charge = atom.GetFormalCharge()
        if charge > 0:
            cations.append(position(index))
        elif charge < 0:
            anions.append(position(index))

    rings = []
    if aromatic_ok:
        for ring in mol.GetRingInfo().AtomRings():
            if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
                rings.append(_centroid([position(i) for i in ring]))
    return {"apolar": apolar, "rings": rings, "cations": cations, "anions": anions, "polar": polar}


def analyze_pose(pose_molblock: str, receptor_atoms: list[ReceptorAtom]) -> dict[str, Any]:
    """Returns `{"hbonds": [...], "clashes": [...]}` for one docked pose
    against an already-parsed receptor atom list (see
    `receptor_atoms_from_structure`). Each entry is a plain dict (not a
    dataclass) since this lands directly in `DockingPoseModel.metadata`,
    an open `dict[str, Any]` meant for JSON-serializable data.
    """
    hbonds: list[dict[str, Any]] = []
    clashes: list[dict[str, Any]] = []

    for ligand_element, ligand_position in _ligand_heavy_atoms(pose_molblock):
        ligand_radius = _vdw_radius(ligand_element)
        ligand_is_polar = ligand_element in _POLAR_ELEMENTS
        for receptor_atom in receptor_atoms:
            distance = math.dist(ligand_position, receptor_atom.position)
            contact = {
                "ligand_element": ligand_element,
                "receptor_element": receptor_atom.element,
                "receptor_residue": f"{receptor_atom.residue_name}{receptor_atom.residue_number}",
                "distance": round(distance, 2),
            }
            if (
                ligand_is_polar
                and receptor_atom.element in _POLAR_ELEMENTS
                and distance <= HBOND_DISTANCE_CUTOFF
            ):
                hbonds.append(contact)
            receptor_radius = _vdw_radius(receptor_atom.element)
            if distance < (ligand_radius + receptor_radius - CLASH_TOLERANCE):
                clashes.append(contact)

    found: dict[str, Any] = {"hbonds": hbonds, "clashes": clashes}
    found.update(_contact_interactions(pose_molblock, receptor_atoms))
    return found


def _contact_interactions(
    pose_molblock: str, receptor_atoms: list[ReceptorAtom]
) -> dict[str, list[dict[str, Any]]]:
    """The interaction types beyond hydrogen bonds and clashes.

    Split out rather than folded into `analyze_pose`'s loop because these
    work on GROUPS -- ring centroids, charged-group centres -- not on
    atom pairs, so they cannot share that loop's structure without
    contorting it.

    Every entry keeps the same `receptor_residue` key the existing two
    use, so `build_interaction_layers` can colour any of them without
    knowing which type it is holding.
    """
    ligand = _ligand_features(pose_molblock)
    receptor = receptor_features(receptor_atoms)

    def pairs(a_points, b_groups, cutoff, describe):
        out = []
        for a in a_points:
            for group in b_groups:
                distance = math.dist(a, group.position)
                if distance <= cutoff:
                    out.append({
                        "receptor_residue": group.residue,
                        "distance": round(distance, 2),
                        **describe,
                    })
        return out

    hydrophobic = []
    for point in ligand["apolar"]:
        for atom in receptor_atoms:
            if not _is_apolar_receptor_carbon(atom):
                continue
            distance = math.dist(point, atom.position)
            if distance <= HYDROPHOBIC_CUTOFF:
                hydrophobic.append({
                    "receptor_residue": f"{atom.residue_name}{atom.residue_number}",
                    "distance": round(distance, 2),
                    "ligand_element": "C",
                    "receptor_element": "C",
                })

    # A salt bridge needs OPPOSITE charges, so each ligand sign pairs with
    # the receptor's other sign -- pairing like with like would report
    # electrostatic repulsion as a favourable contact.
    salt_bridges = (
        pairs(ligand["cations"], receptor["anions"], SALT_BRIDGE_CUTOFF, {"charge": "ligand +"})
        + pairs(ligand["anions"], receptor["cations"], SALT_BRIDGE_CUTOFF, {"charge": "ligand -"})
    )
    metal_coordination = []
    for element, point in ligand["polar"]:
        metal_coordination += pairs(
            [point], receptor["metals"], METAL_COORDINATION_CUTOFF, {"ligand_element": element}
        )

    return {
        "hydrophobic": hydrophobic,
        "salt_bridges": salt_bridges,
        "pi_stacking": pairs(
            ligand["rings"], receptor["rings"], PI_STACKING_CUTOFF, {"geometry": "centroid"}
        ),
        # Both directions: a ligand cation over a receptor aromatic ring,
        # and a receptor cation (ARG/LYS/HIS) over a ligand ring. Reporting
        # only one would miss half of a symmetric interaction.
        "cation_pi": (
            pairs(ligand["cations"], receptor["rings"], CATION_PI_CUTOFF, {"cation": "ligand"})
            + pairs(ligand["rings"], receptor["cations"], CATION_PI_CUTOFF, {"cation": "receptor"})
        ),
        "metal_coordination": metal_coordination,
    }
