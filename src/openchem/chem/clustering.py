"""Grouping a project's molecules by structural similarity.

Butina over Morgan fingerprints, which is the zero-new-dependency default:
both the fingerprint generator and the clustering itself ship inside
RDKit, so this adds no wheel, no model file and no download.

WHY BUTINA AND NOT K-MEANS. Butina takes a similarity THRESHOLD, not a
cluster count. A chemist knows what "Tanimoto 0.65 or better counts as the
same series" means and can defend it; nobody knows in advance that a
project contains seven series. It is also deterministic -- the algorithm
sorts by neighbour count and assigns greedily, with no random
initialisation -- so two runs over one project give the same answer, which
matters for something whose output becomes a column other analyses join
against.

WHAT A CLUSTER HERE IS NOT. It is not a scaffold and not a series in the
medicinal-chemistry sense. Two molecules land together because their
Morgan bits overlap, which tracks substructure and therefore usually
tracks scaffold, but a threshold sweep will happily merge or split a
series depending on where it is set. The threshold is exposed for exactly
that reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.ML.Cluster import Butina

#: Tanimoto similarity at or above which two molecules are neighbours.
#: 0.65 on Morgan radius 2 is the common working default for "same series"
#: in the literature and in RDKit's own cookbook; it is a starting point
#: exposed as a control, not a validated constant.
DEFAULT_SIMILARITY_THRESHOLD = 0.65
DEFAULT_RADIUS = 2
DEFAULT_FINGERPRINT_BITS = 2048


@dataclass(frozen=True)
class ClusterAssignment:
    """Which cluster each molecule landed in, and how the run was set up.

    `cluster_index` is 1-based and ordered largest cluster first, because
    that is how the result gets read -- "cluster 1" should be the main
    series, not whichever molecule happened to sort first. Singletons are
    real clusters, not a leftover bucket: a molecule that resembles nothing
    else in the project is a finding.
    """

    cluster_of: dict[str, int] = field(default_factory=dict)  # molecule uuid -> 1-based index
    cluster_sizes: list[int] = field(default_factory=list)  # by cluster index - 1
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    radius: int = DEFAULT_RADIUS
    skipped: list[str] = field(default_factory=list)  # uuids with no usable structure

    @property
    def cluster_count(self) -> int:
        return len(self.cluster_sizes)

    @property
    def singleton_count(self) -> int:
        return sum(1 for size in self.cluster_sizes if size == 1)

    def describe(self) -> str:
        if not self.cluster_sizes:
            return "Nothing to cluster."
        return (
            f"{self.cluster_count} clusters over {sum(self.cluster_sizes)} molecules "
            f"at Tanimoto ≥ {self.threshold:.2f} (Morgan r={self.radius}); "
            f"largest {max(self.cluster_sizes)}, {self.singleton_count} singletons"
        )


def cluster_molecules(
    mols: dict[str, Chem.Mol],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    radius: int = DEFAULT_RADIUS,
) -> ClusterAssignment:
    """Butina clustering of `uuid -> mol` at a Tanimoto similarity cutoff.

    `threshold` is a SIMILARITY, because that is what a chemist reasons
    about; Butina itself takes a distance, and the conversion happens here
    rather than in every caller. Getting that inversion wrong produces a
    plausible-looking clustering that means the opposite of what was asked
    for, which is the kind of error a UI never surfaces.
    """
    usable = {uuid: mol for uuid, mol in mols.items() if mol is not None and mol.GetNumAtoms() > 0}
    skipped = [uuid for uuid in mols if uuid not in usable]
    if not usable:
        return ClusterAssignment(threshold=threshold, radius=radius, skipped=skipped)

    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=radius, fpSize=DEFAULT_FINGERPRINT_BITS
    )
    uuids = list(usable)
    fingerprints = [generator.GetFingerprint(usable[uuid]) for uuid in uuids]

    # Butina wants the lower triangle of a DISTANCE matrix, flattened, and
    # excluding the diagonal -- row i contributes i entries.
    distances: list[float] = []
    for index in range(1, len(fingerprints)):
        similarities = DataStructs.BulkTanimotoSimilarity(fingerprints[index], fingerprints[:index])
        distances.extend(1.0 - similarity for similarity in similarities)

    clusters = Butina.ClusterData(
        distances, len(fingerprints), 1.0 - threshold, isDistData=True
    )
    ordered = sorted(clusters, key=len, reverse=True)
    cluster_of = {
        uuids[member]: index + 1
        for index, cluster in enumerate(ordered)
        for member in cluster
    }
    return ClusterAssignment(
        cluster_of=cluster_of,
        cluster_sizes=[len(cluster) for cluster in ordered],
        threshold=threshold,
        radius=radius,
        skipped=skipped,
    )
