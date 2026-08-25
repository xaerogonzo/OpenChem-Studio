"""3D alignment of one molecule onto another.

Two methods, matching ChemAxon's plugin:

EXTENDED ATOM TYPES -- Open3DAlign (O3A), which pairs atoms by MMFF atom
type and maximises the overlap of like-typed atoms. MMFF types encode
atomic number, hybridization and aromaticity, so an aromatic nitrogen does
not pair with a tertiary amine. That is the same discrimination ChemAxon
describes for its extended atom types.

    MMFF cannot type every element -- confirmed that selenium and platinum
    both fail. Crippen-based O3A is used as the fallback there rather than
    refusing the alignment, since Crippen contributions are defined for a
    wider element set. Which one ran is reported, because the scores are
    on different scales and are not comparable between the two.

COMMON SCAFFOLD -- the 2D maximum common substructure fixes the atom
pairing, then O3A refines everything else around it via its constraint
map. That two-stage shape is ChemAxon's own description ("after MCS
pairing is established, extended atom type alignment applies to remaining
atoms"), not an invention here.

THE SCORE IS NOT AN RMSD, and the two are reported separately. O3A's score
is an overlap quality where HIGHER is better and the scale depends on
molecular size; RMSD is a distance in angstroms where LOWER is better.
Conflating them would invert the meaning of a result.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, Lipinski, rdFMCS, rdMolAlign, rdMolDescriptors
from rdkit.Geometry import Point3D

from openchem.chem.calculator_options import decimals
from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import StructureEntry, StructureSetResult

# Labels are ChemAxon's; the values are what the code branches on.
ALIGNMENT_METHODS: dict[str, str] = {
    "Extended atom types": "atom_types",
    "Common scaffold (MCS)": "mcs",
}

# ChemAxon's three accuracy levels, expressed as what they actually change
# here: how many starting conformers are tried, and how long the MCS search
# may run. More conformers means a better chance of finding the pose that
# really overlays, at linear cost.
ACCURACY_LEVELS: dict[str, tuple[int, int]] = {
    # label: (conformers, mcs timeout seconds)
    "Fast": (1, 5),
    "Normal": (5, 15),
    "Accurate": (20, 60),
}

logger = logging.getLogger("openchem.chemistry")

DEFAULT_ACCURACY = "Normal"

# ChemAxon's rigid/flexible switch. It is NOT a third method: it composes
# with both of the two above, because it governs how the probe's STARTING
# GEOMETRY is prepared rather than how atoms are paired.
#
# **The contract, stated rather than left to the implementation:**
#
# FLEXIBLE  the MCS atoms are positional CONSTRAINTS, not merely an atom
#           correspondence -- the probe is embedded onto the reference's
#           coordinates for those atoms, and everything outside the MCS MAY
#           CHANGE CONFORMATION during preparation.
# RIGID     the supplied geometry is preserved: no re-embedding and no
#           torsion moves. With nothing supplied there is nothing to
#           preserve, so it embeds -- and `geometry_source` says which
#           happened rather than leaving the caller to guess.
#
# Flexible uses an MCS to build its constraints even when the ALIGNMENT
# method is extended atom types, because the MCS is the only atom
# correspondence that exists before an alignment has been computed. Where
# no common substructure exists there is nothing to constrain against and
# it degrades to an ordinary embed, again recorded on `geometry_source`.
FLEXIBILITY_MODES: dict[str, str] = {
    "Flexible": "flexible",
    "Rigid": "rigid",
}

DEFAULT_FLEXIBILITY = "flexible"

#: Where the probe's coordinates came from. Reported for the same reason
#: `typing` is: alignments begun from different geometries are not
#: comparable, and a score that does not say which it was invites exactly
#: that comparison. The UI renders these through `GEOMETRY_SOURCE_LABELS`
#: rather than paraphrasing, so a new member cannot ship unlabelled.
PROJECT_CONFORMERS = "project_conformers"
EMBEDDED = "embedded"
CONSTRAINED_EMBED = "constrained_embed"

GEOMETRY_SOURCE_LABELS: dict[str, str] = {
    PROJECT_CONFORMERS: "project conformer",
    EMBEDDED: "generated conformer",
    CONSTRAINED_EMBED: "constrained to the reference",
}


class AlignmentError(ValueError):
    """Alignment could not be performed, for a reason worth showing."""


@dataclass(frozen=True)
class AlignmentResult:
    aligned_molblock: str
    reference_molblock: str
    score: float
    rmsd: float
    matched_atoms: int
    method: str
    typing: str  # "MMFF" or "Crippen" -- scores are not comparable across these
    conformers_tried: int
    #: One of PROJECT_CONFORMERS / EMBEDDED / CONSTRAINED_EMBED.
    geometry_source: str = EMBEDDED
    flexibility: str = DEFAULT_FLEXIBILITY
    #: TWO COUNTS, NAMED FOR WHAT THEY COUNT. `matched_atoms` is O3A's own
    #: match count, and for an MCS-method result a reader takes "14 paired
    #: atoms" to mean the MCS -- which on the reported MPMI/4-HO-MPMI pair
    #: was 33. One field with a method-dependent meaning is how that
    #: ambiguity returns under a new label.
    mcs_atom_count: int = 0
    #: RMSD split by the MCS's own correspondence, partitioned by
    #: flexibility. THE REPORTED RMSD CANNOT SEE THE DEFECT THIS EXISTS
    #: FOR: measured on that pair, the panel said 0.116 while the core sat
    #: at 0.083 and the flexible part at 0.931.
    core_rmsd: float | None = None
    flexible_rmsd: float | None = None

    @property
    def o3a_match_count(self) -> int:
        """`matched_atoms` under the name that says what it counts."""
        return self.matched_atoms


def _first_3d(conformers: Sequence[str] | None) -> Chem.Mol | None:
    """The first stored conformer that is really 3D, or None.

    A 2D molblock parses into a conformer with flat z, so
    `GetNumConformers() > 0` is true and useless as a check -- the same
    trap `DescriptorService.request_descriptors` already records for the
    descriptor path.
    """
    for molblock in conformers or ():
        if not molblock:
            continue
        mol = Chem.MolFromMolBlock(molblock, removeHs=False)
        if mol is None or mol.GetNumConformers() == 0:
            continue
        if mol.GetConformer().Is3D():
            return mol
    return None


def _ensure_conformer(
    mol: Chem.Mol,
    seed: int = 0xF00D,
    conformers: Sequence[str] | None = None,
) -> tuple[Chem.Mol, str]:
    """A molecule with 3D coordinates, and where they came from.

    **`addCoords=True` IS LOAD-BEARING AND WAS MISSING.** Without it,
    `AddHs` on a molecule that already carries a 3D conformer adds every
    hydrogen AT THE ORIGIN -- and the `Is3D()` check below then passes,
    because a conformer does exist and is three-dimensional. It returns
    silently, with every hydrogen collapsed onto one point, which is
    exactly the input O3A's MMFF typing is least able to survive.

    It was unreachable while the only caller handed in a 2D drawing.
    Accepting stored conformers is what makes it reachable, so the two
    changes belong together.
    """
    stored = _first_3d(conformers)
    if stored is not None:
        return Chem.AddHs(stored, addCoords=True), PROJECT_CONFORMERS

    prepared = Chem.AddHs(Chem.Mol(mol), addCoords=True)
    if prepared.GetNumConformers() == 0 or not prepared.GetConformer().Is3D():
        if AllChem.EmbedMolecule(prepared, randomSeed=seed) != 0:
            raise AlignmentError("Could not generate a 3D conformer for this structure.")
        AllChem.MMFFOptimizeMolecule(prepared)
        return prepared, EMBEDDED
    return prepared, PROJECT_CONFORMERS


def _o3a(probe: Chem.Mol, reference: Chem.Mol, constraint_map=None):
    """O3A by MMFF typing, falling back to Crippen when MMFF has no
    parameters. Returns (alignment, typing_name)."""
    probe_properties = AllChem.MMFFGetMoleculeProperties(probe)
    reference_properties = AllChem.MMFFGetMoleculeProperties(reference)
    if probe_properties is not None and reference_properties is not None:
        kwargs = {"constraintMap": constraint_map} if constraint_map else {}
        return (
            rdMolAlign.GetO3A(probe, reference, probe_properties, reference_properties, **kwargs),
            "MMFF",
        )
    # Crippen contributions cover elements MMFF does not -- confirmed that
    # MMFF refuses Se and Pt outright.
    probe_contribs = rdMolDescriptors._CalcCrippenContribs(probe)
    reference_contribs = rdMolDescriptors._CalcCrippenContribs(reference)
    kwargs = {"constraintMap": constraint_map} if constraint_map else {}
    return (
        rdMolAlign.GetCrippenO3A(probe, reference, probe_contribs, reference_contribs, **kwargs),
        "Crippen",
    )


def _mcs_atom_map(probe: Chem.Mol, reference: Chem.Mol, timeout: int) -> list[tuple[int, int]]:
    """Atom pairs from the 2D maximum common substructure.

    ONE implementation of "pair these two by MCS", shared with
    `mcs_partition` below -- this wrapper only adds the refusals worth
    showing a user. Two MCS implementations would be two chances to
    disagree about which atoms correspond, and the whole partition rests
    on that correspondence being the same one the alignment used.

    O3A rejects a constraint map containing hydrogens outright
    ("Constrained atoms must be heavy atoms"), which is why `mcs_partition`
    drops them.
    """
    partition = mcs_partition(probe, reference, timeout)
    if partition.atom_count == 0:
        raise AlignmentError(
            "These molecules share no common substructure, so there is nothing to align on. "
            "Try the extended-atom-types method instead."
        )
    if not partition.pairs:
        raise AlignmentError(
            "The common substructure contains no heavy atoms to constrain the alignment with."
        )
    return list(partition.pairs)


@dataclass(frozen=True)
class MCSPartition:
    """The MCS correspondence, split into a rigid core and a flexible rest.

    **THE PARTITION IS COMPUTED ONCE, ON THE SHARED SUBGRAPH.** Classifying
    each molecule independently is how "14 core atoms here, 17 there"
    happens: two ring perceptions on two molecules can disagree, and then a
    pair is core on one side and flexible on the other, which makes the two
    RMSDs below incomparable rather than merely noisy.

    **AND THE CORRESPONDENCE IS THE MCS'S OWN.** The obvious metric --
    "RMSD over the atoms NOT in the MCS" -- cannot be computed at all:
    those atoms have no correspondence by construction, since the
    substituent that differs exists in one molecule and not the other.
    Inventing one (a second MCS, nearest neighbour, matching indices) turns
    the oracle into an arbitrary geometric metric. The atoms worth
    measuring are inside the correspondence; what separates them is
    FLEXIBILITY, not MCS membership.
    """

    pairs: tuple[tuple[int, int], ...]
    core: tuple[tuple[int, int], ...]
    flexible: tuple[tuple[int, int], ...]
    atom_count: int

    @property
    def degenerate(self) -> bool:
        """True when everything landed in one bucket.

        A guard measuring a flexible RMSD over an empty set proves nothing,
        so a fixture asserts this is False before believing any number
        derived from it.
        """
        return not self.core or not self.flexible


def _ring_systems(pattern: Chem.Mol) -> list[set[int]]:
    """Fused ring systems -- rings sharing an atom are one system."""
    systems: list[set[int]] = []
    for ring in pattern.GetRingInfo().AtomRings():
        merged = set(ring)
        for existing in [s for s in systems if s & merged]:
            merged |= existing
            systems.remove(existing)
        systems.append(merged)
    return systems


def mcs_partition(
    probe: Chem.Mol, reference: Chem.Mol, timeout: int = 15
) -> MCSPartition:
    """Pair the two by MCS, then split the pairs by flexibility.

        1  pairs     the MCS correspondence, heavy atoms only
        2  scaffold  the largest fused ring system OF THE PATTERN
        3  cuttable  bonds in the pattern matching RDKit's own
                     RotatableBondSmarts -- the definition
                     CalcNumRotatableBonds uses, so it is not ours to drift
        4  core      pattern atoms reachable from the scaffold without
                     crossing a cuttable bond; flexible is the rest
        5  classify  a PAIR takes the bucket of its pattern atom, so both
                     molecules are classified by one decision
    """
    result = rdFMCS.FindMCS([probe, reference], timeout=timeout)
    if not result.smartsString or result.numAtoms == 0:
        return MCSPartition((), (), (), 0)
    pattern = Chem.MolFromSmarts(result.smartsString)
    if pattern is None:
        return MCSPartition((), (), (), 0)
    # A SMARTS mol carries no ring perception, so GetRingInfo() would report
    # nothing and every atom would land in `flexible`.
    Chem.GetSSSR(pattern)
    pattern.UpdatePropertyCache(strict=False)

    probe_match = probe.GetSubstructMatch(pattern)
    reference_match = reference.GetSubstructMatch(pattern)
    if not probe_match or not reference_match:
        return MCSPartition((), (), (), result.numAtoms)

    systems = _ring_systems(pattern)
    scaffold = max(systems, key=len) if systems else set()
    cuttable = set()
    for a, b in pattern.GetSubstructMatches(Lipinski.RotatableBondSmarts):
        bond = pattern.GetBondBetweenAtoms(a, b)
        if bond is not None:
            cuttable.add(bond.GetIdx())

    core_atoms = set(scaffold)
    stack = list(scaffold)
    while stack:
        index = stack.pop()
        for bond in pattern.GetAtomWithIdx(index).GetBonds():
            if bond.GetIdx() in cuttable:
                continue
            other = bond.GetOtherAtomIdx(index)
            if other not in core_atoms:
                core_atoms.add(other)
                stack.append(other)

    pairs, core, flexible = [], [], []
    for pattern_index in range(pattern.GetNumAtoms()):
        probe_index = probe_match[pattern_index]
        reference_index = reference_match[pattern_index]
        # Heavy atoms only: O3A refuses hydrogens in a constraint map, and a
        # hydrogen's position says more about the embedder than about
        # whether the two structures superimpose.
        if probe.GetAtomWithIdx(probe_index).GetAtomicNum() <= 1:
            continue
        if reference.GetAtomWithIdx(reference_index).GetAtomicNum() <= 1:
            continue
        pair = (probe_index, reference_index)
        pairs.append(pair)
        (core if pattern_index in core_atoms else flexible).append(pair)
    return MCSPartition(tuple(pairs), tuple(core), tuple(flexible), result.numAtoms)


def paired_rmsd(
    probe: Chem.Mol, reference: Chem.Mol, pairs: Sequence[tuple[int, int]]
) -> float | None:
    """RMSD over a given correspondence, in whatever frame the two are in."""
    if not pairs:
        return None
    probe_conformer = probe.GetConformer()
    reference_conformer = reference.GetConformer()
    total = 0.0
    for probe_index, reference_index in pairs:
        a = probe_conformer.GetAtomPosition(probe_index)
        b = reference_conformer.GetAtomPosition(reference_index)
        total += (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2
    return math.sqrt(total / len(pairs))


def _xyz(position) -> tuple[float, float, float]:
    return (position.x, position.y, position.z)


#: How far a constrained atom may sit from its reference position, in
#: angstroms, during the restrained minimisation. Loose enough that MMFF can
#: relieve a clash the embedder left, tight enough that the guard's "the
#: constraint held" arm means something.
CONSTRAINT_TOLERANCE = 0.05


def _constrained_conformer(
    probe: Chem.Mol,
    reference: Chem.Mol,
    pairs: Sequence[tuple[int, int]],
    seed: int = 0xF00D,
) -> Chem.Mol:
    """Embed `probe` with its MCS atoms pinned to the reference's positions.

    This is what "flexible" means. O3A is a RIGID superposition: it finds
    the best transform for a pairing and cannot rotate a bond. So a probe
    embedded in isolation keeps whatever rotamer the embedder chose, the
    rigid core lands perfectly, and a flexible substituent lands wherever it
    happened to be -- which is the reported defect. Measured on
    MPMI/4-HO-MPMI: flexible RMSD 0.931 A that way against 0.036 A with the
    constraints, a 26x difference, while the score and the reported RMSD
    looked equally healthy in both.
    """
    prepared = Chem.AddHs(Chem.Mol(probe), addCoords=True)
    reference_conformer = reference.GetConformer()
    coordinates = {
        probe_index: Point3D(*_xyz(reference_conformer.GetAtomPosition(reference_index)))
        for probe_index, reference_index in pairs
    }
    embedded = AllChem.EmbedMolecule(
        prepared, coordMap=coordinates, randomSeed=seed, useRandomCoords=True
    )
    if embedded != 0:
        raise AlignmentError(
            "Could not build a conformer constrained to the reference. "
            "Try the Rigid setting."
        )

    properties = AllChem.MMFFGetMoleculeProperties(prepared)
    if properties is not None:
        field = AllChem.MMFFGetMoleculeForceField(prepared, properties)
        for probe_index, reference_index in pairs:
            position = _xyz(reference_conformer.GetAtomPosition(reference_index))
            anchor = field.AddExtraPoint(*position, fixed=True) - 1
            field.AddDistanceConstraint(
                anchor, probe_index, 0, CONSTRAINT_TOLERANCE, 100.0
            )
        # REQUIRED after AddExtraPoint. Without it the minimiser raises a
        # "size mismatch" pre-condition violation, because the force field
        # still believes it holds as many points as the molecule has atoms.
        field.Initialize()
        field.Minimize(maxIts=800)
    return prepared


def _rigid_candidates(
    probe: Chem.Mol,
    conformers: Sequence[str] | None,
    count: int,
    seed: int,
) -> tuple[list[Chem.Mol], str]:
    """The supplied geometry if there is one, otherwise fresh embeds."""
    stored = []
    for molblock in conformers or ():
        if not molblock:
            continue
        mol = Chem.MolFromMolBlock(molblock, removeHs=False)
        if mol is None or mol.GetNumConformers() == 0:
            continue
        if mol.GetConformer().Is3D():
            stored.append(Chem.AddHs(mol, addCoords=True))
        if len(stored) >= count:
            break
    if stored:
        # RIGID MEANS RIGID: handed to O3A exactly as stored, with no
        # re-embedding and no minimisation, so no torsion moves.
        return stored, PROJECT_CONFORMERS

    prepared = Chem.AddHs(Chem.Mol(probe), addCoords=True)
    conformer_ids = AllChem.EmbedMultipleConfs(prepared, numConfs=count, randomSeed=seed)
    if not conformer_ids:
        raise AlignmentError("Could not generate any 3D conformer for the molecule being aligned.")
    AllChem.MMFFOptimizeMoleculeConfs(prepared)
    return [Chem.Mol(prepared, confId=int(i)) for i in conformer_ids], EMBEDDED


def _probe_candidates(
    probe: Chem.Mol,
    reference_3d: Chem.Mol,
    flexibility: str,
    partition: MCSPartition,
    conformers: Sequence[str] | None,
    count: int,
    seed: int,
) -> tuple[list[Chem.Mol], str]:
    """Starting geometries for the probe, and where they came from.

    **A FLEXIBLE REQUEST THAT CANNOT BE HONOURED DEGRADES RATHER THAN
    FAILING, AND SAYS SO.** Pinning the probe's shared atoms onto the
    reference's coordinates is not always geometrically possible, and that
    is chemistry rather than a bug: measured on ibuprofen against naproxen,
    the MCS spans BOTH rings of naproxen's naphthalene, so no conformer of
    ibuprofen's single benzene can put its six shared ring atoms there.
    Distance geometry correctly refuses -- it fails at 14 constraints, at
    the 6 ring ones, and at every subset that carries the real shape.

    Forcing it would mean inventing a geometry. So the fallback is the
    ordinary embed, and `geometry_source` comes back EMBEDDED rather than
    CONSTRAINED_EMBED -- which the panel shows, so "flexible did not take
    on this pair" is visible rather than silent.
    """
    if flexibility == "flexible" and partition.pairs:
        try:
            return (
                [_constrained_conformer(probe, reference_3d, partition.pairs, seed)],
                CONSTRAINED_EMBED,
            )
        except AlignmentError:
            logger.info(
                "Constrained embedding was not geometrically possible; "
                "falling back to an unconstrained conformer."
            )
    return _rigid_candidates(probe, conformers, count, seed)


def align(
    probe: Chem.Mol,
    reference: Chem.Mol,
    method: str = "atom_types",
    accuracy: str = DEFAULT_ACCURACY,
    seed: int = 0xF00D,
    flexibility: str = DEFAULT_FLEXIBILITY,
    conformers: Sequence[str] | None = None,
    reference_conformers: Sequence[str] | None = None,
) -> AlignmentResult:
    """Align `probe` onto `reference`, keeping the best of several starts.

    Trying multiple conformers is the point of ChemAxon's "initial
    conformation count": a flexible molecule's alignment quality depends
    heavily on which starting geometry it began from, so the best score
    across a diverse set beats one arbitrary pose.

    **BUT MORE STARTING POSES DO NOT FIX A FLEXIBLE SUBSTITUENT**, and that
    was the reported defect. O3A is a rigid superposition; if none of the
    embedded rotamers happens to put the tail where the reference has it,
    no amount of them will. `flexibility="flexible"` is the answer -- see
    `_constrained_conformer` and `FLEXIBILITY_MODES`.

    `conformers` / `reference_conformers` are molblocks the project already
    holds. They used to be ignored entirely: the service handed over
    `model.molblock`, the 2D drawing, and every stored conformer was
    discarded. On the reported pair the reference had SEVENTEEN.
    """
    conformer_count, mcs_timeout = ACCURACY_LEVELS.get(accuracy, ACCURACY_LEVELS[DEFAULT_ACCURACY])
    reference_3d, _reference_source = _ensure_conformer(
        reference, seed=seed, conformers=reference_conformers
    )

    # Computed once and used for three things: the O3A constraint map when
    # the method is MCS, the positional constraints when the mode is
    # flexible, and the core/flexible RMSD split that is reported. One
    # correspondence, so all three describe the same pairing.
    partition = mcs_partition(Chem.AddHs(Chem.Mol(probe)), reference_3d, mcs_timeout)

    constraint_map = None
    if method == "mcs":
        # Raises the refusals worth showing when there is no shared core.
        constraint_map = _mcs_atom_map(Chem.AddHs(Chem.Mol(probe)), reference_3d, mcs_timeout)

    candidates, geometry_source = _probe_candidates(
        probe, reference_3d, flexibility, partition, conformers, conformer_count, seed
    )

    best: tuple[float, float, int, str, Chem.Mol] | None = None
    for single in candidates:
        try:
            alignment, typing = _o3a(single, reference_3d, constraint_map)
            rmsd = float(alignment.Align())
            score = float(alignment.Score())
            matched = len(alignment.Matches())
        except (RuntimeError, ValueError) as exc:
            raise AlignmentError(f"Alignment failed: {exc}") from exc
        # HIGHER score is better -- it is an overlap quality, not a distance.
        if best is None or score > best[0]:
            best = (score, rmsd, matched, typing, single)

    score, rmsd, matched, typing, aligned = best
    # Recomputed against the ALIGNED coordinates. The partition above was
    # built on an unaligned copy, so its indices are right and its
    # distances are not.
    measured = mcs_partition(aligned, reference_3d, mcs_timeout)
    return AlignmentResult(
        aligned_molblock=Chem.MolToMolBlock(aligned),
        reference_molblock=Chem.MolToMolBlock(reference_3d),
        score=score,
        rmsd=rmsd,
        matched_atoms=matched,
        method=method,
        typing=typing,
        conformers_tried=len(candidates),
        geometry_source=geometry_source,
        flexibility=flexibility,
        mcs_atom_count=measured.atom_count,
        core_rmsd=paired_rmsd(aligned, reference_3d, measured.core),
        flexible_rmsd=paired_rmsd(aligned, reference_3d, measured.flexible),
    )


def align_ensemble(
    probes: Sequence[tuple],
    reference: Chem.Mol,
    reference_label: str = "Reference",
    method: str = "atom_types",
    accuracy: str = DEFAULT_ACCURACY,
    seed: int = 0xF00D,
    on_progress: Callable[[int, int, str], None] | None = None,
    flexibility: str = DEFAULT_FLEXIBILITY,
    reference_conformers: Sequence[str] | None = None,
) -> list[EnsembleEntry]:
    """Align every molecule in `probes` onto the same `reference`.

    Returns the reference FIRST, then one entry per probe in the order
    given. Pairwise `align()` is called once per probe rather than anything
    cleverer: O3A is inherently pairwise, and aligning each molecule onto
    the same fixed reference is what puts them all in one coordinate frame
    -- which is the whole point of an ensemble overlay.

    A per-molecule failure is recorded on its own entry, not raised. Ten
    molecules where one cannot be embedded should return nine alignments
    and one explanation, not nothing.

    **A PROBE IS `(label, mol)` OR `(label, mol, conformers)`.** The third
    element is the molblocks the project already holds for that molecule.
    Accepting both shapes rather than changing the tuple keeps every
    existing caller working, and the stored conformers were being thrown
    away entirely before this -- `mol_from_model` hands over
    `model.molblock`, the 2D drawing, and never `model.conformers`.
    """
    reference_3d, _source = _ensure_conformer(
        reference, seed=seed, conformers=reference_conformers
    )
    entries = [EnsembleEntry(label=reference_label, molblock=Chem.MolToMolBlock(reference_3d))]

    for index, entry in enumerate(probes):
        label, probe = entry[0], entry[1]
        conformers = entry[2] if len(entry) > 2 else None
        if on_progress is not None:
            on_progress(index, len(probes), label)
        try:
            result = align(
                probe,
                reference,
                method=method,
                accuracy=accuracy,
                seed=seed,
                flexibility=flexibility,
                conformers=conformers,
                reference_conformers=reference_conformers,
            )
        except (AlignmentError, ValueError, RuntimeError) as exc:
            entries.append(EnsembleEntry(label=label, molblock="", error=str(exc)))
            continue
        entries.append(
            EnsembleEntry(
                label=label,
                molblock=result.aligned_molblock,
                score=result.score,
                rmsd=result.rmsd,
                matched_atoms=result.matched_atoms,
                typing=result.typing,
                geometry_source=result.geometry_source,
                mcs_atom_count=result.mcs_atom_count,
                core_rmsd=result.core_rmsd,
                flexible_rmsd=result.flexible_rmsd,
            )
        )
    return entries


def _failed(molecule_uuid: str, message: str) -> StructureSetResult:
    return StructureSetResult(
        set_id="alignment_3d",
        name="3D Alignment",
        method="rdkit_o3a",
        molecule_uuid=molecule_uuid,
        entries=[],
        cache_state=CacheState.FAILED,
        error=message,
        provenance=Provenance(created_by="core", method="rdkit_o3a"),
    )


def compute_3d_alignment(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> StructureSetResult:
    """The "alignment" category's calculator.

    The reference is given as SMILES rather than picked from the project:
    `CalculatorRegistry.compute` receives one molecule and no project
    handle, the same constraint that keeps docking in its own panel. A
    text reference keeps the feature usable inside the existing framework;
    aligning a whole project ensemble would need a panel of its own.
    """
    parameters = parameters or {}
    reference_smiles = (parameters.get("reference_smiles") or "").strip()
    if not reference_smiles:
        return _failed(
            molecule_uuid,
            "Enter a reference structure as SMILES -- this molecule will be aligned onto it.",
        )
    reference = Chem.MolFromSmiles(reference_smiles)
    if reference is None:
        return _failed(molecule_uuid, f"Could not parse the reference SMILES: {reference_smiles!r}")

    method = ALIGNMENT_METHODS.get(parameters.get("method", ""), "atom_types")
    accuracy = parameters.get("accuracy", DEFAULT_ACCURACY)
    try:
        result = align(mol, reference, method=method, accuracy=accuracy)
    except AlignmentError as exc:
        return _failed(molecule_uuid, str(exc))

    places = decimals(parameters)
    method_label = next(
        (label for label, value in ALIGNMENT_METHODS.items() if value == result.method), result.method
    )
    return StructureSetResult(
        set_id="alignment_3d",
        name=(
            f"3D Alignment ({method_label}) - score {result.score:.{places}f}, "
            f"RMSD {result.rmsd:.{places}f} A"
        ),
        method="rdkit_o3a",
        molecule_uuid=molecule_uuid,
        entries=[
            StructureEntry(
                molblock=result.reference_molblock,
                label=f"Reference: {reference_smiles}",
                metadata={"role": "reference"},
            ),
            StructureEntry(
                molblock=result.aligned_molblock,
                label=(
                    f"Aligned - score {result.score:.{places}f} (higher is better), "
                    f"RMSD {result.rmsd:.{places}f} A over {result.matched_atoms} paired atoms"
                ),
                score=result.score,
                metadata={
                    "role": "aligned",
                    "rmsd": result.rmsd,
                    "matched_atoms": result.matched_atoms,
                    "typing": result.typing,
                },
            ),
        ],
        provenance=Provenance(
            created_by="core",
            method="rdkit_o3a",
            parameters={
                "alignment_method": result.method,
                "accuracy": accuracy,
                "conformers_tried": result.conformers_tried,
                # Reported because MMFF and Crippen scores are on different
                # scales -- comparing one against the other is meaningless.
                "typing": result.typing,
                "score": result.score,
                "rmsd": result.rmsd,
                "decimal_places": places,
            },
        ),
    )


# --- conformers of ONE molecule, aligned for display -------------------------
#
# A DIFFERENT PROBLEM FROM EVERYTHING ABOVE, and kept here so there is one
# place to look for "how does this project align things" rather than a
# fourth. O3A and MCS exist because two different molecules have no given
# atom correspondence. Conformers of one molecule have the identity
# correspondence for free, so none of that machinery applies.


def align_conformers_for_display(molblocks: Sequence[str]) -> list[str]:
    """Superimpose conformers of one molecule onto the first of them.

    **THIS IS PRESENTATION, NOT CHEMISTRY.** `EmbedMolecule` puts every
    conformer in its own arbitrary frame -- a gauge choice carrying no
    information -- so stepping from one to the next in the viewer changes
    the orientation as much as the shape, and comparing them by eye is
    impossible. Reported exactly that way: "It is extremely difficult to
    compare different conformers... I arranged the first conformer in 1
    row, then in the second conformer I moved it a certain way, then moved
    back to the first conformer, and it was once again in a different way."

    **The result is never stored.** `ConformerModel.molblock` keeps the
    coordinates the generator produced; this is recomputed for display. A
    rigid rotation changes no chemistry, but "recompute a view" and
    "overwrite the scientific result" are different things and only one of
    them is reversible. The alternative -- a transform field on the model --
    was rejected because every consumer would then have to remember to
    apply it, and the one that forgets shows exactly the unaligned view
    this exists to fix.

    **The identity atom map, deliberately, NOT `GetBestRMS`.** Conformers of
    one molecule already share an atom ordering, so the identity
    correspondence is well defined and deterministic. `GetBestRMS` searches
    symmetry-equivalent permutations for the lowest RMSD, and on a molecule
    with a symmetric core it can pick a permutation that flips the whole
    structure between one conformer and the next -- replacing the visual
    jump being fixed here with a different one.

    **Fitted on heavy atoms, applied to every atom.** A rotating methyl's
    hydrogens would otherwise drag the fit and rotate the whole molecule to
    chase three atoms that are not what anybody is comparing.

    Returns the input unchanged if there is nothing to align, or if the
    molblocks disagree about how many atoms the molecule has -- which means
    they are not conformers of one molecule and no correspondence exists.
    """
    if len(molblocks) < 2:
        return list(molblocks)

    mols = []
    for molblock in molblocks:
        mol = Chem.MolFromMolBlock(molblock, removeHs=False)
        if mol is None or mol.GetNumConformers() == 0:
            return list(molblocks)
        mols.append(mol)

    counts = {mol.GetNumAtoms() for mol in mols}
    if len(counts) != 1:
        return list(molblocks)

    reference = mols[0]
    heavy = [
        atom.GetIdx() for atom in reference.GetAtoms() if atom.GetAtomicNum() > 1
    ]
    # Degenerate fits are the failure mode a fixed correspondence does not
    # by itself rule out. Three points define a plane and fewer define
    # nothing, so below that the rotation is not determined and the honest
    # answer is to leave the coordinates alone.
    if len(heavy) < 3:
        return list(molblocks)
    atom_map = [(index, index) for index in heavy]

    aligned = [molblocks[0]]
    for mol in mols[1:]:
        rdMolAlign.AlignMol(mol, reference, atomMap=atom_map)
        aligned.append(Chem.MolToMolBlock(mol))
    return aligned
