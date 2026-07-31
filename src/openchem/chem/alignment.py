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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, rdFMCS, rdMolAlign, rdMolDescriptors

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

DEFAULT_ACCURACY = "Normal"


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


def _ensure_conformer(mol: Chem.Mol, seed: int = 0xF00D) -> Chem.Mol:
    prepared = Chem.AddHs(Chem.Mol(mol))
    if prepared.GetNumConformers() == 0 or not prepared.GetConformer().Is3D():
        if AllChem.EmbedMolecule(prepared, randomSeed=seed) != 0:
            raise AlignmentError("Could not generate a 3D conformer for this structure.")
        AllChem.MMFFOptimizeMolecule(prepared)
    return prepared


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
    """Atom pairs from the 2D maximum common substructure."""
    result = rdFMCS.FindMCS([probe, reference], timeout=timeout)
    if result.canceled and not result.smartsString:
        raise AlignmentError("The maximum-common-substructure search timed out.")
    if not result.smartsString or result.numAtoms == 0:
        raise AlignmentError(
            "These molecules share no common substructure, so there is nothing to align on. "
            "Try the extended-atom-types method instead."
        )
    pattern = Chem.MolFromSmarts(result.smartsString)
    probe_match = probe.GetSubstructMatch(pattern)
    reference_match = reference.GetSubstructMatch(pattern)
    if not probe_match or not reference_match:
        raise AlignmentError("The common substructure could not be located in both molecules.")

    # O3A rejects a constraint map containing hydrogens outright
    # ("Constrained atoms must be heavy atoms"). The MCS runs against
    # H-added molecules, so any hydrogen the pattern happened to match has
    # to be dropped rather than passed through.
    pairs = [
        (probe_index, reference_index)
        for probe_index, reference_index in zip(probe_match, reference_match)
        if probe.GetAtomWithIdx(probe_index).GetAtomicNum() > 1
        and reference.GetAtomWithIdx(reference_index).GetAtomicNum() > 1
    ]
    if not pairs:
        raise AlignmentError(
            "The common substructure contains no heavy atoms to constrain the alignment with."
        )
    return pairs


def align(
    probe: Chem.Mol,
    reference: Chem.Mol,
    method: str = "atom_types",
    accuracy: str = DEFAULT_ACCURACY,
    seed: int = 0xF00D,
) -> AlignmentResult:
    """Align `probe` onto `reference`, keeping the best of several starting
    conformers.

    Trying multiple conformers is the point of ChemAxon's "initial
    conformation count": a flexible molecule's alignment quality depends
    heavily on which starting geometry it began from, so the best score
    across a diverse set is a far better answer than one arbitrary pose.
    """
    conformer_count, mcs_timeout = ACCURACY_LEVELS.get(accuracy, ACCURACY_LEVELS[DEFAULT_ACCURACY])
    reference_3d = _ensure_conformer(reference, seed=seed)

    probe_with_h = Chem.AddHs(Chem.Mol(probe))
    conformer_ids = AllChem.EmbedMultipleConfs(
        probe_with_h, numConfs=conformer_count, randomSeed=seed
    )
    if not conformer_ids:
        raise AlignmentError("Could not generate any 3D conformer for the molecule being aligned.")
    AllChem.MMFFOptimizeMoleculeConfs(probe_with_h)

    constraint_map = None
    if method == "mcs":
        # MCS pairing first, then O3A refines the rest around it.
        constraint_map = _mcs_atom_map(probe_with_h, reference_3d, mcs_timeout)

    best: tuple[float, float, int, str, Chem.Mol] | None = None
    for conformer_id in conformer_ids:
        single = Chem.Mol(probe_with_h, confId=int(conformer_id))
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
    return AlignmentResult(
        aligned_molblock=Chem.MolToMolBlock(aligned),
        reference_molblock=Chem.MolToMolBlock(reference_3d),
        score=score,
        rmsd=rmsd,
        matched_atoms=matched,
        method=method,
        typing=typing,
        conformers_tried=len(conformer_ids),
    )


def align_ensemble(
    probes: list[tuple[str, Chem.Mol]],
    reference: Chem.Mol,
    reference_label: str = "Reference",
    method: str = "atom_types",
    accuracy: str = DEFAULT_ACCURACY,
    seed: int = 0xF00D,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[EnsembleEntry]:
    """Align every molecule in `probes` onto the same `reference`.

    Returns the reference FIRST, then one entry per probe in the order
    given. Pairwise `align()` is called once per probe rather than
    anything cleverer: O3A is inherently pairwise, and aligning each
    molecule onto the same fixed reference is what puts them all in one
    coordinate frame -- which is the whole point of an ensemble overlay.

    A per-molecule failure is recorded on its own entry, not raised. Ten
    molecules where one cannot be embedded should return nine alignments
    and one explanation, not nothing.
    """
    reference_3d = _ensure_conformer(reference, seed=seed)
    entries = [EnsembleEntry(label=reference_label, molblock=Chem.MolToMolBlock(reference_3d))]

    for index, (label, probe) in enumerate(probes):
        if on_progress is not None:
            on_progress(index, len(probes), label)
        try:
            result = align(probe, reference, method=method, accuracy=accuracy, seed=seed)
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
