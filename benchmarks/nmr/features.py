"""Features for the shift model that was tried, measured, and NOT shipped.

THIS IS BENCHMARK CODE, not application code, and it lives here rather
than under `src/` for that reason. The model it builds was trained on
nmrshiftdb2 and scored against the HOSE lookup on the held-out split
`chem/nmr_database.py` records -- and it lost. The full table is in
`README.md` beside this file. Kept so the negative result is reproducible
and so a later attempt starts from the evidence instead of repeating the
work; see docs/ROADMAP.md.

WHAT WAS TRIED. The lookup fails in one specific way: when an environment
has never been seen, widening the sphere depth pools an ever more generic
set of measurements until the answer averages things that are not alike.
That is the `rough` band, and at ~10 ppm it is where the error lives. A
model generalises where a lookup can only widen, so the model predicts
the same quantity from features that survive when the exact environment
does not.

FEATURES:

  * The lookup's (count, mean, spread) at EACH of the six sphere depths,
    NaN where that depth found nothing. This is the load-bearing block --
    a target encoding that carries not just "what did the lookup say" but
    "at what depth did it stop being confident", which is the signal the
    quality rating is built from. HistGradientBoostingRegressor takes NaN
    natively, so "not found" needs no sentinel and no imputation.

  * Ordinary RDKit atom descriptors -- element, hybridisation,
    aromaticity, ring membership and size, degree, charge, Gasteiger
    charge, E-state, Crippen contributions, neighbouring elements out to
    two bonds. These contributed ESSENTIALLY NOTHING: permutation
    importance puts every one of them at or below 0.01 ppm, against 0.21
    for the sphere-1 lookup mean.

  * A hash of each sphere's HOSE code, as a categorical. This one was
    expected to be useless -- 250 buckets over ~200,000 environments
    makes each bucket a random mix -- and the ablation says otherwise:
    removing them takes the carbon model from 3.32 to 3.87 ppm. At sphere
    one the code is coarse enough ("C;C,C,O") that 250 buckets encode it
    almost losslessly, so the column is a real categorical of the
    immediate environment rather than noise. The guess was wrong and the
    measurement is what stands.

TRAINING-TIME LEAKAGE is the caller's job, via `leave_one_out`. A
training atom's own measurement is inside the index mean it is asked to
predict -- with `count` as low as three that is a third of the answer.
Removing it changes what the model learns completely, though not in the
direction expected: WITHOUT the correction the model stops after ~49
iterations having learned to copy the lookup, and scores 2.89 ppm, i.e.
the lookup's own 2.91. WITH it, the model is forced to actually predict,
and does worse (3.32). That the leaky model's optimum is "reproduce the
lookup" is the clearest single piece of evidence that these features hold
nothing the lookup does not already have.
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("benchmarks.nmr")

#: Buckets for the hashed-HOSE categoricals. Below scikit-learn's 255-bin
#: default so they can be declared categorical at all.
_HASH_BUCKETS = 250

_HALOGENS = frozenset({"F", "Cl", "Br", "I"})
_NEIGHBOUR_GROUPS = ("C", "N", "O", "S", "P", "halogen", "other")

_HYBRIDISATIONS = ("SP", "SP2", "SP3", "SP3D", "SP3D2")


# --- Features -------------------------------------------------------------


def _group_of(symbol: str) -> str:
    if symbol in ("C", "N", "O", "S", "P"):
        return symbol
    return "halogen" if symbol in _HALOGENS else "other"


def _hash_bucket(code: str) -> int:
    """A stable bucket for a HOSE code.

    blake2b rather than `hash()`: Python randomises string hashing per
    process, so a model trained in one run would read different buckets in
    the next and quietly lose whatever the feature contributed.
    """
    digest = hashlib.blake2b(code.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % _HASH_BUCKETS


@dataclass(frozen=True)
class MoleculeCache:
    """Per-molecule quantities, computed once rather than per atom.

    Gasteiger charges, E-state indices and Crippen contributions are all
    whole-molecule calculations that return a value for every atom.
    Calling them inside the per-atom loop would repeat the whole
    calculation once per assigned shift -- a dozen or more times over for
    a typical record -- for identical output.
    """

    gasteiger: list[float]
    estate: list[float]
    crippen_logp: list[float]
    crippen_mr: list[float]

    @classmethod
    def build(cls, mol) -> "MoleculeCache":
        from rdkit.Chem import rdMolDescriptors, rdPartialCharges
        from rdkit.Chem.EState import EStateIndices

        count = mol.GetNumAtoms()

        # Each of these is guarded independently: a molecule with an
        # unusual valence can defeat Gasteiger while E-state succeeds, and
        # losing one descriptor is better than losing the atom.
        try:
            rdPartialCharges.ComputeGasteigerCharges(mol)
            gasteiger = [
                _finite(mol.GetAtomWithIdx(i).GetDoubleProp("_GasteigerCharge"))
                for i in range(count)
            ]
        except Exception:  # noqa: BLE001
            gasteiger = [math.nan] * count

        try:
            estate = [_finite(value) for value in EStateIndices(mol)]
        except Exception:  # noqa: BLE001
            estate = [math.nan] * count

        try:
            contributions = rdMolDescriptors._CalcCrippenContribs(mol)
            logp = [_finite(pair[0]) for pair in contributions]
            mr = [_finite(pair[1]) for pair in contributions]
        except Exception:  # noqa: BLE001
            logp = [math.nan] * count
            mr = [math.nan] * count

        return cls(gasteiger=gasteiger, estate=estate, crippen_logp=logp, crippen_mr=mr)


def _finite(value: float) -> float:
    """NaN and infinity are the same thing to the model -- "no value" --
    and infinity is the one that makes numpy warn later."""
    return value if math.isfinite(value) else math.nan


def feature_names(max_spheres: int = 6) -> list[str]:
    names: list[str] = []
    for spheres in range(max_spheres, 0, -1):
        names += [f"lookup{spheres}_mean", f"lookup{spheres}_logcount", f"lookup{spheres}_spread"]
    names += [
        "atomic_num",
        "degree",
        "total_hs",
        "formal_charge",
        "is_aromatic",
        "in_ring",
        "min_ring_size",
        "num_rings",
        "hybridisation",
        "total_valence",
        "gasteiger",
        "estate",
        "crippen_logp",
        "crippen_mr",
        "bonds_single",
        "bonds_double",
        "bonds_triple",
        "bonds_aromatic",
        "any_conjugated",
    ]
    names += [f"nbr1_{group}" for group in _NEIGHBOUR_GROUPS]
    names += ["nbr1_aromatic", "nbr1_in_ring"]
    names += [f"nbr2_{group}" for group in _NEIGHBOUR_GROUPS]
    names += ["heavy_atoms"]
    names += [f"hose{spheres}_hash" for spheres in range(max_spheres, 0, -1)]
    return names


def categorical_feature_indices(max_spheres: int = 6) -> list[int]:
    names = feature_names(max_spheres)
    return [index for index, name in enumerate(names) if name.endswith("_hash")]


def lookup_block(stats: list[tuple[int, float, float] | None]) -> list[float]:
    """The leading, load-bearing part of a feature row.

    Split out because the benchmark needs it twice per atom -- corrected
    and uncorrected -- and the descriptors that follow it are the same
    either way, so rebuilding the whole row would double the work for
    columns that cannot have changed.
    """
    row: list[float] = []
    for entry in stats:
        if entry is None:
            row += [math.nan, math.nan, math.nan]
        else:
            count, mean, spread = entry
            row += [mean, math.log1p(count), spread]
    return row


def feature_row(
    mol,
    atom_index: int,
    stats: list[tuple[int, float, float] | None],
    codes: list[str],
    cache: MoleculeCache,
) -> list[float]:
    """One atom's feature vector.

    `stats` is the lookup's (count, mean, spread) per sphere depth,
    largest first, with None where nothing was found; `codes` is the
    matching list of HOSE codes. They are passed in rather than looked up
    here so that training can apply its leave-one-out correction to the
    same values prediction will see uncorrected.
    """
    row: list[float] = lookup_block(stats)

    atom = mol.GetAtomWithIdx(atom_index)
    ring_info = mol.GetRingInfo()

    bonds = atom.GetBonds()
    single = double = triple = aromatic = 0
    conjugated = 0
    for bond in bonds:
        if bond.GetIsAromatic():
            aromatic += 1
        else:
            name = str(bond.GetBondType())
            if name == "SINGLE":
                single += 1
            elif name == "DOUBLE":
                double += 1
            elif name == "TRIPLE":
                triple += 1
        if bond.GetIsConjugated():
            conjugated = 1

    hybrid = str(atom.GetHybridization())
    row += [
        float(atom.GetAtomicNum()),
        float(atom.GetDegree()),
        float(atom.GetTotalNumHs(includeNeighbors=True)),
        float(atom.GetFormalCharge()),
        float(atom.GetIsAromatic()),
        float(atom.IsInRing()),
        float(ring_info.MinAtomRingSize(atom_index)),
        float(ring_info.NumAtomRings(atom_index)),
        float(_HYBRIDISATIONS.index(hybrid) if hybrid in _HYBRIDISATIONS else -1),
        float(atom.GetTotalValence()),
        cache.gasteiger[atom_index],
        cache.estate[atom_index],
        cache.crippen_logp[atom_index],
        cache.crippen_mr[atom_index],
        float(single),
        float(double),
        float(triple),
        float(aromatic),
        float(conjugated),
    ]

    first = {group: 0 for group in _NEIGHBOUR_GROUPS}
    second = {group: 0 for group in _NEIGHBOUR_GROUPS}
    aromatic_neighbours = ring_neighbours = 0
    for neighbour in atom.GetNeighbors():
        symbol = neighbour.GetSymbol()
        if symbol == "H":
            # Explicit hydrogens are in these files. They are already
            # counted as `total_hs`, and letting them into the neighbour
            # histogram would make the same information disagree with
            # itself depending on how a record was drawn.
            continue
        first[_group_of(symbol)] += 1
        aromatic_neighbours += neighbour.GetIsAromatic()
        ring_neighbours += neighbour.IsInRing()
        for outer in neighbour.GetNeighbors():
            if outer.GetIdx() == atom_index or outer.GetSymbol() == "H":
                continue
            second[_group_of(outer.GetSymbol())] += 1

    row += [float(first[group]) for group in _NEIGHBOUR_GROUPS]
    row += [float(aromatic_neighbours), float(ring_neighbours)]
    row += [float(second[group]) for group in _NEIGHBOUR_GROUPS]
    row += [float(mol.GetNumHeavyAtoms())]
    row += [float(_hash_bucket(code)) for code in codes]
    return row


def leave_one_out(
    stats: list[tuple[int, float, float] | None], shift: float
) -> list[tuple[int, float, float] | None]:
    """`stats` with this atom's own measurement removed.

    Training rows are drawn from the same molecules the index was built
    from, so the mean a training atom is asked to predict CONTAINS that
    atom's answer -- weight 1/count, and count is allowed to be as low as
    three. A model fed the uncorrected mean learns that the lookup is
    nearly always right, which is true of the training set and false
    everywhere else.

    Dropping to fewer than the lookup's own minimum is reported as "not
    found", because that is what the lookup would have done for an atom
    that genuinely was not in the index.

    The spread is left uncorrected. Recomputing it would need the sum of
    squares, which the index does not store, and the residual bias from
    one measurement in three or more is small next to the bias in the mean
    it sits beside.
    """
    from openchem.chem.nmr_database import MIN_MATCHES

    corrected: list[tuple[int, float, float] | None] = []
    for entry in stats:
        if entry is None:
            corrected.append(None)
            continue
        count, mean, spread = entry
        if count - 1 < MIN_MATCHES:
            corrected.append(None)
            continue
        corrected.append((count - 1, (mean * count - shift) / (count - 1), spread))
    return corrected


def sphere_stats(
    connection, codes: list[str], element: str, max_spheres: int
) -> list[tuple[int, float, float] | None]:
    """The index's (count, mean, spread) at every sphere depth.

    Every depth, not just the first one that satisfies the lookup: the
    depth at which the evidence thins out is itself the signal, and a
    single already-chosen row throws that away.
    """
    found: list[tuple[int, float, float] | None] = []
    for offset, code in enumerate(codes):
        row = connection.execute(
            "SELECT count, mean, spread FROM shift_environments "
            "WHERE hose_code = ? AND spheres = ? AND element = ?",
            (code, max_spheres - offset, element),
        ).fetchone()
        found.append((row[0], row[1], row[2]) if row is not None else None)
    return found


def hose_answer(stats, element: str, max_spheres: int):
    """What `nmr_database.lookup` would return, from already-fetched stats.

    The same widening rule -- deepest sphere with enough matches wins --
    expressed over the per-depth statistics the feature extractor already
    has. Calling `lookup` as well would double the queries for an answer
    that must agree by construction; `tests/test_nmr_ml.py` pins that it
    does.
    """
    from openchem.chem.nmr_database import MIN_MATCHES, ShiftPrediction

    for offset, entry in enumerate(stats):
        if entry is None:
            continue
        count, mean, spread = entry
        if count < MIN_MATCHES:
            continue
        return ShiftPrediction(
            shift=mean,
            spread=spread,
            match_count=count,
            spheres=max_spheres - offset,
            element=element,
        )
    return None


#: The order `hose_quality` is encoded in, everywhere. "none" is not a
#: rating the lookup gives itself -- it is the absence of one, kept in the
#: same vocabulary so an uncovered atom is a band rather than a special
#: case that every caller has to remember.
QUALITY_BANDS = ("good", "medium", "rough", "none")


@dataclass(frozen=True)
class TrainingRow:
    """One atom, ready to train on or to score."""

    record: int
    element: str
    features: list[float]
    shift: float
    #: What the plain lookup answered, and how it rated itself -- carried
    #: so the baseline, the model and the hybrid are all scored on exactly
    #: the same atoms rather than on three separately-collected sets.
    hose_shift: float
    hose_quality: int
    #: The same lookup block as `features` begins with, but WITHOUT the
    #: leave-one-out correction. Only the benchmark uses it, to measure
    #: what the correction is worth; training ignores it.
    uncorrected_lookup: list[float]


def training_rows(
    sdf_path: Path,
    connection,
    max_spheres: int = 6,
    correct_leakage: bool = True,
    on_progress=None,
):
    """`TrainingRow` per assigned atom in `sdf_path`.

    Shared by the benchmark and by the in-app trainer ON PURPOSE. These
    features have to be built identically at training time and at
    prediction time, and the cheapest way to guarantee that is for there
    to be one loop rather than two that look alike.

    `correct_leakage` is the leave-one-out switch: true when the rows come
    from molecules the index was built from, false when they do not.
    """
    from openchem.chem.hose_codes import hose_codes
    from openchem.chem.nmr_database import iter_assigned_spectra

    seen = 0
    for record_index, mol, element, assignments in iter_assigned_spectra(sdf_path):
        try:
            cache = MoleculeCache.build(mol)
        except Exception:  # noqa: BLE001 - one bad record costs itself, not the run
            continue
        for atom_index, shift in assignments:
            try:
                codes = hose_codes(mol, atom_index, max_spheres)
            except Exception:  # noqa: BLE001
                continue
            stats = sphere_stats(connection, codes, element, max_spheres)

            # Read BEFORE any correction: this is the baseline the model
            # is being judged against, and it must be what ships.
            answer = hose_answer(stats, element, max_spheres)
            model_stats = leave_one_out(stats, shift) if correct_leakage else stats
            yield TrainingRow(
                record=record_index,
                element=element,
                features=feature_row(mol, atom_index, model_stats, codes, cache),
                shift=shift,
                hose_shift=answer.shift if answer is not None else math.nan,
                hose_quality=QUALITY_BANDS.index(
                    answer.quality if answer is not None else "none"
                ),
                uncorrected_lookup=lookup_block(stats) if correct_leakage else [],
            )
        seen += 1
        if on_progress is not None and seen % 5000 == 0:
            on_progress(seen)
