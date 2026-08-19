"""Turning a molecule into a `LewisDiagram`. The only RDKit in the feature.

The chemistry half. `chem/lewis_diagram.py` holds the result and
`chem/lewis_svg.py` draws it; neither imports RDKit, so a chemistry
regression and a rendering regression can never be confused.

**THE SPLIT, and it is the whole idea.** A delocalised bond still has a
localised sigma component; only the excess is delocalised:

    localised pairs on a bond = its MINIMUM order across every
                                resonance structure
    a region's electrons      = sum over its bonds of
                                (kekulised order - minimum) x 2

Benzene comes out as six localised pairs and one six-electron region --
never three doubles and three singles, which would assert a Kekule
structure the molecule does not have. `tests/test_resonance_gate.py` is
where that arithmetic was measured against textbook counts.

**AROMATICITY IS PERCEIVED, NOT READ.** The editor's molblock stores
benzene as alternating SINGLE/DOUBLE, so a non-sanitising parse sees a
perfectly localised molecule and never knows. The parse here sanitises for
exactly that reason.

**BOTH TESTS ARE NEEDED to find a delocalised bond**, and measured:
caffeine, imidazole and pyrrole are aromatic without any bond order
varying, while carboxylate, nitro and guanidinium vary without being
aromatic. Either test alone gets one family wrong.

**EXPLICIT HYDROGENS.** A Lewis structure draws methane as a carbon
sharing four pairs with four hydrogens, so the diagram is built on
`AddHs` with its own layout. That is what makes it a different picture
from the canvas rather than the same one annotated -- and on the
heavy-atom graph methane has no bonds at all.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from openchem.chem.lewis_diagram import (
    Abstention,
    Atom,
    BondPairs,
    Known,
    LewisDiagram,
    Provenance,
    Region,
    Status,
    Unknown,
)

#: Bumped when the analysis changes in a way that would alter a diagram,
#: so a stored or screenshotted one can be told apart from a fresh one.
ANALYSIS_VERSION = "1"

#: How many resonance contributors to enumerate. Measured: no ordinary
#: molecule reaches even 16 (anthracene 4, pentacene 6, porphine 2), so
#: this is headroom. The fail-closed path below still exists, because
#: "no input I tried hit it" is not "no input can".
MAX_RESONANCE_STRUCTURES = 256

#: One bond length in diagram units, matching `chem/lewis_svg.BOND_LENGTH`.
BOND_LENGTH = 60.0

#: Closest non-bonded approach, in bond lengths, below which the diagram
#: is CROWDED. Derived rather than chosen: a lone-pair dot sits 0.33 bond
#: lengths from its atom, so two atoms closer than twice that can have
#: overlapping dots.
#:
#: Measured across a layout set: water 1.73, methane 1.41, acetate 1.41,
#: benzene 1.73, aspirin 1.00, caffeine 1.18 -- and glucose 0.52,
#: cholesterol 0.04. **Atom count does not predict it**; aspirin has 21
#: atoms and lays out cleanly while glucose has 24 and does not.
CROWDED_APPROACH = 0.66

_UNSUPPORTED_OCTET = (
    "an expanded octet, where drawing it that way rather than "
    "charge-separated is contested"
)
_LONE_PAIR_AROMATIC = (
    "a lone pair completes this ring's sextet, which bond orders cannot count"
)
_TRUNCATED = "too many resonance structures to enumerate"


def build(molblock: str | None, structure_revision: int = 0) -> LewisDiagram:
    """A Lewis diagram for a drawing, or one of the three refusals."""
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolDescriptors  # noqa: F401

    if not molblock:
        return _refused("there is no structure to analyse")

    try:
        # **SANITISED.** This is the parse that perceives aromaticity; the
        # `sanitize=False` one used elsewhere would read the stored Kekule
        # orders and call benzene localised.
        parsed = Chem.MolFromMolBlock(molblock, removeHs=False)
    except Exception as exc:  # noqa: BLE001 - an unreadable drawing is normal
        return _refused(f"this structure could not be read ({exc})")
    if parsed is None:
        return _refused("this structure could not be read")

    try:
        mol, layout = _best_layout(parsed)
    except Exception as exc:  # noqa: BLE001
        return _refused(f"this structure could not be laid out ({exc})")

    from openchem.chem.electron_overlay import build as lone_pair_counts

    counts = lone_pair_counts(mol)
    if counts.refused:
        return _refused(counts.reason, molblock, structure_revision)

    orders, structures, truncated = _resonance_orders(mol)
    kekule = _kekule_orders(mol)
    aromatic = {
        _key(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
        for bond in mol.GetBonds()
        if bond.GetIsAromatic()
    }
    varying = {key for key, seen in orders.items() if len(seen) > 1}
    delocalised = aromatic | varying
    expanded = _expanded_octet_atoms(mol)

    # Regions FIRST: a bond inside a region whose electron count could not
    # be determined has to be capped below, and that is only knowable once
    # the regions exist.
    regions = _regions(mol, delocalised, orders, kekule, expanded)
    undeterminable = {
        key
        for region in regions
        if isinstance(region.electrons, Unknown)
        for key in region.bonds
    }

    bond_pairs: list[BondPairs] = []
    abstentions: list[Abstention] = []
    for bond in mol.GetBonds():
        begin, end = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        key = _key(begin, end)
        subject = _bond_name(mol, begin, end)
        if begin in expanded or end in expanded:
            bond_pairs.append(BondPairs(begin, end, Unknown(_UNSUPPORTED_OCTET)))
            abstentions.append(Abstention(subject, _UNSUPPORTED_OCTET))
            continue
        if truncated and key in delocalised:
            # FAIL CLOSED: an enumeration that stopped early cannot
            # establish a minimum, so nothing is asserted about it.
            bond_pairs.append(BondPairs(begin, end, Unknown(_TRUNCATED)))
            abstentions.append(Abstention(subject, _TRUNCATED))
            continue
        seen = orders.get(key)
        pairs = min(seen) if seen else kekule.get(key, 1)
        if key in undeterminable:
            # **PYRROLE WOULD OTHERWISE BE DRAWN AS A KEKULE STRUCTURE.**
            # It has one contributor, so `min` is the bond's own order --
            # 2 for the two rings bonds that happen to be drawn double --
            # and dotting those asserts a localisation the molecule does
            # not have. Every aromatic bond definitely has ONE sigma
            # pair; the rest belongs to a region whose count is not
            # determined, so one is all that is claimed.
            pairs = min(pairs, 1)
        bond_pairs.append(BondPairs(begin, end, Known(int(pairs))))

    atoms = _atoms(mol, counts)
    for atom in atoms:
        if isinstance(atom.lone_pairs, Unknown):
            # A count nobody could determine is an ABSTENTION, not a
            # silent gap -- otherwise a bare metal reports SUPPORTED while
            # its budget cannot be closed.
            abstentions.append(
                Abstention(f"{atom.symbol}{atom.index}", atom.lone_pairs.reason)
            )

    status = Status.SUPPORTED_WITH_ABSTENTIONS if abstentions else Status.SUPPORTED
    return LewisDiagram(
        status=status,
        atoms=tuple(atoms),
        bond_pairs=tuple(bond_pairs),
        regions=tuple(regions),
        abstentions=tuple(abstentions),
        provenance=_provenance(molblock, structure_revision, layout),
    )


@dataclass(frozen=True)
class ChosenLayout:
    """Which engine drew the diagram, and the score that chose it."""

    engine: str
    crowding: float
    crossings: int


def _best_layout(parsed):
    """Lay out with BOTH engines and keep whichever scores better.

    **"USE THE NEWER ENGINE" WOULD HAVE MADE THE REPORTED CASE WORSE.**
    Measured as closest non-bonded approach in bond lengths, CoordGen
    beats `Compute2DCoords` on cholesterol (0.036 -> 0.565, sixteenfold)
    and glucose, and LOSES on morphine (0.303 -> 0.186), caffeine and
    methane. Morphine is essentially the structure this was reported for.

    Both engines are deterministic -- CoordGen re-run three times on
    morphine gives the same layout to six decimal places -- and together
    they cost about 20 ms on the largest molecule in the corpus, so
    running both is cheaper than deciding which to run.

    Ties keep `Compute2DCoords`, the engine that shipped: a chooser that
    flipped on a tie would churn layouts for no measured reason.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdCoordGen

    from openchem.chem.lewis_layout import score

    base = Chem.AddHs(parsed, addCoords=False)
    candidates = []
    for engine, lay_out in (
        ("compute2dcoords", AllChem.Compute2DCoords),
        ("coordgen", rdCoordGen.AddCoords),
    ):
        candidate = Chem.Mol(base)
        lay_out(candidate)
        conformer = candidate.GetConformer()
        positions = {
            index: tuple(conformer.GetAtomPosition(index))[:2]
            for index in range(candidate.GetNumAtoms())
        }
        bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in candidate.GetBonds()]
        candidates.append((score(positions, bonds), engine, candidate))

    best_score, engine, mol = max(candidates, key=lambda item: (item[0], item[1] == "compute2dcoords"))
    return mol, ChosenLayout(engine, best_score.crowding, best_score.crossings)


def crowding(diagram: LewisDiagram) -> float:
    """Closest non-bonded approach, in bond lengths. Small means crowded.

    **A LEGIBILITY NUMBER, NEVER A CHEMISTRY ONE.** A molecule whose
    diagram is hard to read still has a correct diagram, and reporting
    "analysis unsupported" for a layout problem would be the two failure
    kinds conflated -- which is why `Status` keeps them apart.
    """
    positions = {atom.index: (atom.x, atom.y) for atom in diagram.atoms}
    bonded = {frozenset((b.begin, b.end)) for b in diagram.bond_pairs}
    lengths = [
        math.dist(positions[b.begin], positions[b.end])
        for b in diagram.bond_pairs
        if b.begin in positions and b.end in positions
    ]
    if not lengths or len(positions) < 2:
        return math.inf
    mean_bond = sum(lengths) / len(lengths)
    closest = math.inf
    indices = sorted(positions)
    for i, first in enumerate(indices):
        for second in indices[i + 1 :]:
            if frozenset((first, second)) in bonded:
                continue
            closest = min(closest, math.dist(positions[first], positions[second]))
    return closest / mean_bond if mean_bond else math.inf


def _resonance_orders(mol):
    """Every order each bond takes across the resonance contributors.

    `KEKULE_ALL` alone, and that is measured rather than chosen:
    `ALLOW_CHARGE_SEPARATION` leaves pyrrole and furan unchanged at zero
    and gives AMIDE two delocalised electrons from a contributor a Lewis
    structure has no business drawing.
    """
    from rdkit import Chem

    orders: dict[tuple[int, int], set[int]] = {}
    structures = 0
    try:
        supplier = Chem.ResonanceMolSupplier(
            mol, Chem.KEKULE_ALL, maxStructs=MAX_RESONANCE_STRUCTURES
        )
        for resonance in supplier:
            if resonance is None:
                continue
            structures += 1
            for bond in resonance.GetBonds():
                key = _key(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
                orders.setdefault(key, set()).add(int(bond.GetBondTypeAsDouble()))
    except Exception:  # noqa: BLE001 - treated as "could not enumerate"
        return {}, 0, True
    return orders, structures, structures >= MAX_RESONANCE_STRUCTURES


def _kekule_orders(mol) -> dict[tuple[int, int], int]:
    """Integer orders from a KEKULISED copy.

    Summed over the aromatic form each bond counts 1.5, and naphthalene
    then reports 11 delocalised electrons against a textbook 10.
    """
    from rdkit import Chem

    try:
        kekulised = Chem.Mol(mol)
        Chem.Kekulize(kekulised, clearAromaticFlags=True)
    except Exception:  # noqa: BLE001
        kekulised = mol
    return {
        _key(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()): int(bond.GetBondTypeAsDouble())
        for bond in kekulised.GetBonds()
    }


def _expanded_octet_atoms(mol) -> set[int]:
    """Atoms carrying more than eight electrons.

    **NOT from RDKit's valence list**, which does not work:
    `GetValenceList(16)` is `[2, 4, 6]`, so sulfur(VI) is a perfectly
    normal valence and sulfate goes undetected. Counting the octet needs
    no element list and so cannot rot.
    """
    from openchem.chem.lewis import lone_pairs

    flagged = set()
    for atom in mol.GetAtoms():
        if atom.GetSymbol() in ("H", "He"):
            continue
        pairs = lone_pairs(atom)
        if pairs is None:
            continue
        if 2 * (int(atom.GetTotalValence()) + pairs) > 8:
            flagged.add(atom.GetIdx())
    return flagged


def _regions(mol, delocalised, orders, kekule, expanded) -> list[Region]:
    """Connected groups of delocalised bonds, each with its own count."""
    adjacency: dict[int, set[int]] = {}
    for begin, end in delocalised:
        if begin in expanded or end in expanded:
            continue
        adjacency.setdefault(begin, set()).add(end)
        adjacency.setdefault(end, set()).add(begin)

    seen: set[int] = set()
    regions: list[Region] = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        component = set()
        stack = [start]
        while stack:
            index = stack.pop()
            if index in component:
                continue
            component.add(index)
            stack.extend(adjacency[index] - component)
        seen |= component

        bonds = tuple(
            sorted(key for key in delocalised if key[0] in component and key[1] in component)
        )
        excess = 0
        determinable = False
        for key in bonds:
            seen_orders = orders.get(key)
            if not seen_orders:
                continue
            gap = kekule.get(key, min(seen_orders)) - min(seen_orders)
            excess += gap
            if len(seen_orders) > 1:
                determinable = True

        # **PYRROLE.** A ring flagged by aromaticity alone has no order
        # variation to count, and its sextet is completed by a lone pair
        # the enumeration never moves. The region is real; the number is
        # not determined, and that is not the same as zero.
        electrons = Known(excess * 2) if determinable else Unknown(_LONE_PAIR_AROMATIC)
        ring_info = mol.GetRingInfo()
        is_ring = all(ring_info.NumAtomRings(index) > 0 for index in component)
        regions.append(
            Region(
                atom_indices=tuple(sorted(component)),
                electrons=electrons,
                is_ring=is_ring,
                bonds=bonds,
            )
        )
    return regions


def _atoms(mol, counts) -> list[Atom]:
    """Model atoms, in DIAGRAM coordinates.

    RDKit lays out with y increasing upwards and a bond length near 1.5;
    SVG has y increasing downwards. Both are corrected here so the
    renderer never has to know where its numbers came from.
    """
    from rdkit import Chem

    table = Chem.GetPeriodicTable()
    conformer = mol.GetConformer()
    positions = [tuple(conformer.GetAtomPosition(i))[:2] for i in range(mol.GetNumAtoms())]
    lengths = [
        math.dist(positions[b.GetBeginAtomIdx()], positions[b.GetEndAtomIdx()])
        for b in mol.GetBonds()
    ]
    unit = (sum(lengths) / len(lengths)) if lengths else 1.0
    scale = BOND_LENGTH / unit if unit else BOND_LENGTH

    atoms = []
    for atom in mol.GetAtoms():
        index = atom.GetIdx()
        x, y = positions[index]
        pairs = counts.counts.get(index)
        atoms.append(
            Atom(
                index=index,
                symbol=atom.GetSymbol(),
                x=round(x * scale, 4),
                y=round(-y * scale, 4),
                lone_pairs=Known(pairs)
                if pairs is not None
                else Unknown("this atom's non-bonding electrons cannot be counted"),
                valence_electrons=table.GetNOuterElecs(atom.GetAtomicNum()),
                formal_charge=atom.GetFormalCharge(),
                isotope=atom.GetIsotope(),
            )
        )
    return atoms


def _bond_name(mol, begin: int, end: int) -> str:
    first = mol.GetAtomWithIdx(begin)
    second = mol.GetAtomWithIdx(end)
    return f"{first.GetSymbol()}{begin}-{second.GetSymbol()}{end}"


def _key(begin: int, end: int) -> tuple[int, int]:
    return (begin, end) if begin < end else (end, begin)


def _provenance(
    molblock: str,
    revision: int,
    layout: ChosenLayout | None = None,
) -> Provenance:
    from rdkit import rdBase

    return Provenance(
        molblock_sha=hashlib.sha256(molblock.encode("utf-8")).hexdigest()[:16],
        structure_revision=revision,
        analysis_version=ANALYSIS_VERSION,
        rdkit_version=rdBase.rdkitVersion,
        layout_engine=layout.engine if layout else "",
        layout_crowding=layout.crowding if layout else None,
        layout_crossings=layout.crossings if layout else None,
    )


def _refused(reason: str, molblock: str | None = None, revision: int = 0) -> LewisDiagram:
    return LewisDiagram(
        status=Status.CHEMISTRY_REFUSED,
        reason=reason,
        provenance=_provenance(molblock, revision) if molblock else Provenance(),
    )
