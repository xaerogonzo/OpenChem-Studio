from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from rdkit import Chem
from rdkit.Chem import AllChem, TorsionFingerprints, rdMolAlign, rdMolTransforms

from openchem.plugins.interfaces import ConformerBatch, ConformerProvider

logger = logging.getLogger("openchem.chemistry")

#: RMSD (Å) below which two embeddings are geometrically close enough to
#: be MERGE CANDIDATES. Computed over the skeleton `comparison_skeleton`
#: returns. Closeness here permits a merge; `DEFAULT_ENERGY_WINDOW` below
#: can still veto it.
#:
#: 0.5 Å is RDKit's conventional `pruneRmsThresh` value, and it was
#: checked here rather than adopted on authority. Over 40 embeddings of
#: butane every pair came out either below 0.5 Å or at 0.66 Å -- two
#: clean clusters, anti and gauche, with nothing in between.
#:
#: THAT BIMODALITY IS A PROPERTY OF BUTANE, NOT OF MOLECULES, and
#: calibrating on it is why this shipped too coarse for anything larger.
#: Ethylmorphine's 276 pairwise RMSDs are a CONTINUUM with no gap for a
#: threshold to sit in, which is why its count moved between 2 and 3
#: across runs. Measured, against the number of distinct converged MMFF
#: energies as a reference lower bound (never a ground truth -- see
#: `benchmarks/conformers/`):
#:
#:     molecule          ref >=   0.25   0.35   0.50   1.00
#:     ethanol                2      3      3      2      1
#:     butane                 2      3      3      2      1
#:     cyclohexane            2      3      2      1 <-   1   twist-boat LOST
#:     pentane                4      5      5      4      1
#:     ethylene glycol        6      8      7      3      2
#:     ethylmorphine         12      8      6      4      1
#:
#: No threshold fixes that table: 0.35 saves cyclohexane and breaks
#: ethanol and butane. The energy veto is what does, and the row it has
#: to justify is cyclohexane's.
#:
#: Cost is negligible (≤1.6 ms for 10 conformers of ibuprofen), so the
#: N-squared comparison is not worth optimising at these counts.
DEFAULT_RMS_THRESHOLD = 0.5

#: kcal/mol. Two structures inside `DEFAULT_RMS_THRESHOLD` are merged
#: UNLESS their energies differ by more than this.
#:
#: READ THIS BEFORE SIMPLIFYING THE CONDITION AWAY. It is a merge veto,
#: not evidence of conformational identity. Passing both criteria PERMITS
#: merging; it does not prove equivalence. A ΔE below the window does not
#: establish that two structures are the same conformer, and a ΔE above
#: it does not establish that they are different. Energy is not an
#: identity coordinate and is never used to CLAIM two structures are
#: different conformers -- only to decline to merge them on insufficient
#: evidence, which is the same direction the `except` in
#: `distinct_conformers` already errs in.
#:
#: WHY THE EVIDENCE IS INSUFFICIENT WITHOUT IT. BOTH available geometric
#: measures are blind to what these molecules do, and it is not that
#: nothing moves. For ethylmorphine's worst vetoed pair:
#:
#:     skeleton RMSD (heavy + polar H, what we compare)   0.437  < 0.5
#:     TFD                                                0.037  < 0.2
#:     largest RING torsion change                      104.3 deg
#:     energy difference                          15.79 kcal/mol
#:     all-atom RMSD including carbon-bound H             0.930
#:     nitrogen pyramidalisation      337.9 vs 338.1 deg -- no inversion
#:     stereochemistry re-perceived from 3D    identical in 24 of 24
#:
#: A ring torsion swings over 100 degrees and NEITHER metric registers
#: it. Across 108 vetoed pairs, 100 have a torsion moving more than 60
#: degrees while every one of them sits under both cut-offs (RMSD 0.207
#: to 0.496, TFD 0.008 to 0.072). They miss it for different reasons:
#: RMSD because a fused polycyclic cage constrains how far heavy atoms
#: can move when a ring puckers (the displacement lands on the
#: hydrogens -- the ten largest are all hydrogens, nine carbon-bound, up
#: to 2.71 Å), and TFD because one torsion out of the ~30 it averages
#: over is diluted to nothing.
#:
#: An earlier version of this comment said the torsions barely moved.
#: That was an artefact of the diagnostic: `CalculateTorsionLists`
#: returns (non-ring, ring) and `_torsion_deviation` was reading only the
#: first, so on a molecule whose flexibility is ring pucker it measured
#: the ethyl ether and reported 1.6 degrees. Cyclohexane made it obvious
#: -- ZERO non-ring torsions, so a chair/twist-boat pair scored 0.0
#: degrees against a TFD of 0.407.
#:
#: SO "EVERY PURELY GEOMETRIC CRITERION FAILED" WAS CONCLUDED WITH A
#: BROKEN INSTRUMENT, AND HAS NOW BEEN RE-MEASURED WITH A WORKING ONE.
#: The conclusion survives, and it fails in the OPPOSITE direction from
#: the one that motivated this module. A torsion veto -- merge candidates
#: kept apart when their largest dihedral moved more than the window --
#: swept over the corpus at 30 embeddings x 3 seeds, through the real
#: `_merge_scan` rather than a re-implementation of it:
#:
#:     arm                butane  cyclohexane  pentane  ethylmorphine
#:     (reference)             2            2        4           >=12
#:     energy (shipped)        2            2        4          8..13
#:     torsion > 30 deg        3            3      5-6           6..9
#:     torsion > 60 deg        3          2-3      5-6           6..9
#:     torsion > 90 deg        3          2-3      5-6           6..8
#:     energy + torsion > 60   3          2-3      5-6         10..14
#:
#: Torsion alone OVER-counts the simple molecules while still
#: under-counting ethylmorphine, and combining it with the energy veto
#: inherits the over-counting. A 60-degree torsion change is real and
#: unimportant for butane's methyl or pentane's mirror images, which is
#: precisely what a magnitude threshold cannot tell apart. The
#: diagnostics stay diagnostic.
#:
#: Measured over the validation set, this is the only arm that passes:
#:
#:     criterion                ethanol  butane  cyclohexane  ethylmorphine
#:     (reference lower bound)        2       2            2            >=12
#:     skeleton @ 0.50                2       2            1               4
#:     skeleton @ 0.35                3       3            2               6
#:     all-atom @ 0.50                1       3            3               9
#:     all-atom @ 1.00                1       3            1               2
#:     skeleton 0.50 + 1 kcal veto    2       2            2              13
#:
#: "Best-performing heuristic on this validation set" -- not "the method
#: that finds the correct conformer count", since the reference is itself
#: a computational lower bound.
DEFAULT_ENERGY_WINDOW = 1.0

#: Below this RMSD (Å) two structures are the SAME SHAPE, and the energy
#: veto does not apply to them. Geometry alone still decides identity at
#: the bottom of the scale; energy only speaks in the ambiguous band
#: between here and `DEFAULT_RMS_THRESHOLD`.
#:
#: WITHOUT IT THE VETO OVER-COUNTS RIGID MOLECULES, which is the original
#: bug in reverse. 2H-azirine is a three-membered ring with no
#: conformational freedom at all, and about 2% of embeddings converge to
#: a DISTORTED minimum 10.7 kcal/mol up -- same connectivity, same
#: torsions, but the C=N stretched to 1.339 Å from 1.246. Conformers
#: differ by torsion and ring pucker; a bond length is a force-field
#: artefact, and no energy gap should promote one to a conformer.
#:
#: Squeezed between two measured bounds rather than chosen, over 6 runs
#: of 30 embeddings each -- the RMSD of pairs the veto keeps apart:
#:
#:     2H-azirine (the artefact)          0.0807   <- must NOT be vetoed
#:     ethylmorphine, 503 pairs   0.2065 .. 0.4998 <- must stay vetoed
#:     cyclohexane                        0.3747
#:     ethylene glycol            0.4466 .. 0.4963
#:     pentane                            0.4961
#:
#: 0.15 sits in [0.081, 0.207) with a factor of 2.5 and nothing in
#: between. `test_the_same_shape_floor_stays_between_its_measured_bounds`
#: recomputes both ends, so widening this fails naming what it would
#: break.
#:
#: An energy CEILING was measured as the alternative and does not work:
#: the azirine artefact needs a cut at 10 kcal/mol or below, while
#: ethylmorphine's genuine conformers span 17.9 kcal/mol, so every
#: ceiling either keeps the artefact or discards real minima.
#:
#:     ceiling      none    20    15    10     5
#:     azirine (1)     2     2     2     1     1
#:     cyclohexane     2     2     2     2     1
#:     ethylmorphine  13    12    10     8     4
_IDENTICAL_SHAPE_RMSD = 0.15

#: `MMFFOptimizeMolecule`'s default is 200 and IS NOT ENOUGH: 1 of 10
#: ethylmorphine embeddings failed to converge there and sat 3.67
#: kcal/mol above its own minimum, corrupting the energy ranking the UI
#: presents as "conformer 1 is the lowest". Measured at 2000, over 30
#: embeddings each of ethanol, cyclohexane, pentane, ibuprofen and
#: ethylmorphine: 150 of 150 converged in a single call.
_OPTIMISATION_MAX_ITERS = 2000

#: Two attempts, the second continuing from the first's coordinates, then
#: the conformer is DISCARDED. Bounded deliberately -- an unbounded retry
#: loop turns a pathological molecule into a hang, and 150/150 says one
#: call is normally enough. A non-converged geometry must not reach the
#: ranking, the veto, de-duplication, or a calculator.
_MAX_OPTIMISATION_ATTEMPTS = 2


#: Hydrogens on these keep their orientation for comparison; see
#: `distinct_conformers`. Carbon is the one deliberately absent.
_POLAR_H_NEIGHBOURS = frozenset({7, 8, 16})  # N, O, S


def comparison_skeleton(mol: Chem.Mol) -> Chem.Mol:
    """`mol` with its carbon-bound hydrogens removed, for RMSD comparison.

    Public because anything checking whether two conformers are the same
    has to use the SAME notion of sameness this module does. A test that
    compared survivors with plain `RemoveHs` reported them as duplicates
    while the pruner had correctly kept them apart on an O-H orientation.
    """
    editable = Chem.RWMol(mol)
    doomed = [
        atom.GetIdx()
        for atom in editable.GetAtoms()
        if atom.GetAtomicNum() == 1
        and atom.GetDegree() == 1
        and atom.GetNeighbors()[0].GetAtomicNum() not in _POLAR_H_NEIGHBOURS
    ]
    # Descending, because removing an atom renumbers every index above it.
    for index in sorted(doomed, reverse=True):
        editable.RemoveAtom(index)
    return editable.GetMol()


def _permits_merge(
    rmsd: float, energy: float | None, other: float | None, energy_window: float
) -> bool:
    """Whether anything objects to merging these two.

    Reads as a VETO, deliberately: `True` means "no evidence against",
    never "these are the same conformer". See `DEFAULT_ENERGY_WINDOW`.

    BELOW `_IDENTICAL_SHAPE_RMSD` THE ENERGY IS NOT CONSULTED. Two
    structures that close are the same shape, and an energy difference
    between them is a bond-length artefact rather than a conformational
    one -- see that constant for the 2H-azirine measurement. Geometry
    alone decides identity at the bottom of the scale.

    MIXED None IS PER PAIR, not per batch. A conformer with no energy
    (`optimize=False`, or a project saved before energies were recorded)
    contributes no evidence, so that pair falls back to RMSD alone while
    every other pair in the same batch keeps the full criterion. Real
    pipelines accumulate partial metadata and an all-or-nothing rule
    would silently change how a whole batch is compared because one
    member lacked a number.
    """
    if rmsd < _IDENTICAL_SHAPE_RMSD:
        return True
    if energy is None or other is None:
        return True
    return abs(energy - other) < energy_window


def _in_comparison_order(
    results: list[tuple[Chem.Mol, float | None]],
) -> list[tuple[Chem.Mol, float | None]]:
    """Ascending by energy, energyless last, arrival order within ties.

    GREEDY LEADER CLUSTERING IS ORDER-DEPENDENT, so the order is part of
    the contract rather than whatever the caller happened to pass. Given
    four structures mutually within the RMSD threshold but spanning 1.2
    kcal/mol, different input orders retain different sets.

    Sorting here rather than trusting the caller is what makes the
    retained set depend on the SET of inputs rather than on the order
    they arrive in. The one exception is deliberate and documented: exact
    energy ties, and batches with no energies at all, fall back to
    arrival order, because there is nothing else to order them by. Exact
    ties between genuinely different geometries do not occur in practice
    (they indicate the same structure embedded twice, where which copy
    survives does not matter).
    """
    return sorted(
        results, key=lambda item: (item[1] is None, item[1] if item[1] is not None else 0.0)
    )


def distinct_conformers(
    results: list[tuple[Chem.Mol, float | None]],
    rms_threshold: float = DEFAULT_RMS_THRESHOLD,
    energy_window: float = DEFAULT_ENERGY_WINDOW,
) -> list[tuple[Chem.Mol, float | None]]:
    """Drop embeddings that are the same shape as one already kept.

    WHY THIS IS NOT OPTIONAL. Embedding is random, so asking for ten
    conformers of a molecule that HAS one produced ten copies of it, and
    the UI dutifully reported "Conformer 1/10" with every one identical.
    That is not a cosmetic issue: it invites Boltzmann-weighting a
    population that is really one state ten times over, and it makes a
    rigid molecule look conformationally rich.

    Measured before the fix, 10 requested with MMFF optimisation:
    aziridine 1 distinct, 2H-azirine 1, butane 2.

    TWO CRITERIA, AND THEY ARE NOT SYMMETRIC. Geometric closeness makes
    two structures merge CANDIDATES; energy agreement then permits the
    merge or vetoes it. `DEFAULT_ENERGY_WINDOW` carries the contract and
    the measurements, and `test_conformer_dedup.py` asserts both halves
    -- including the inverse case, which is what stops the energy
    criterion quietly becoming a second identity criterion.

    HEAVY ATOMS PLUS POLAR HYDROGENS, and symmetry-aware via `GetBestRMS`.

    Hydrogens on N, O and S are KEPT because their orientation is a real
    conformational degree of freedom -- it sets hydrogen bonding, and it
    changes the energy of the QM jobs these conformers are generated for.
    Dropping them all was tried first and is measurably worse: ethanol's
    heavy atoms are C-C-O, three points and therefore rigid by
    construction, so heavy-atom-only RMSD reports ONE conformer for a
    molecule whose O-H rotamers are exactly what a conformer search is
    for (ethanol 1 -> 2, ethylene glycol 2 -> 3, ibuprofen 7 -> 9, with
    the rigid cases unaffected).

    HYDROGENS ON CARBON ARE STRIPPED, AND THE ORIGINAL REASON FOR IT WAS
    WRONG. It was "a rotated methyl is not a different conformer but does
    move three atoms". `GetBestRMS` is symmetry-aware and the three
    methyl hydrogens are symmetry-equivalent, so it already matches them
    optimally: measured on a pure 120-degree methyl rotation of ethanol,
    all-atom `GetBestRMS` returns 0.0095 Å. Stripping was never needed
    for that.

    It is kept because all-atom RMSD was then measured as a replacement
    and is worse overall -- it collapses ethanol to 1 and inflates butane
    to 3 (see the table on `DEFAULT_ENERGY_WINDOW`). The cost of keeping
    it is that this comparison is blind to ring pucker, which is exactly
    what the energy veto compensates for.

    Symmetry-awareness matters separately: the two ends of butane are
    interchangeable, and a naive atom-order RMSD calls the same shape
    different simply for having been numbered the other way round.

    `GetBestRMS` does not reflect, so mirror-image conformers of an
    achiral molecule are counted separately -- which is why pentane reads
    5 against a textbook 4. Understood behaviour, asserted in the
    benchmark rather than tolerated as noise.
    """
    kept, _candidates = _merge_scan(results, rms_threshold, energy_window, with_torsions=False)
    return kept


@dataclass(frozen=True)
class MergeCandidate:
    """One pair that got close enough geometrically to be merged, and what
    the other measures said about it.

    Recorded because the RMSD/energy disagreement this module exists to
    handle is not visible from the counts. Two situations that produce
    the same "kept apart" outcome are scientifically very different:

        RMSD low, TFD low,  dE huge     both geometries blind (ethylmorphine)
        RMSD low, TFD high, dE small    torsions moved, energy did not

    `max_dihedral_change` and `largest_torsion` name which torsion moved
    most, so the second case can be recognised rather than guessed at.

    **DIAGNOSTIC, AND THAT IS A MEASURED DECISION RATHER THAN AN
    OVERSIGHT.** Nothing here feeds the merge rule, which invites the
    question of why it is computed at all. It was evaluated as a
    criterion once the measure was fixed, and it loses to the energy
    veto on every molecule that separates them -- the table on
    `DEFAULT_ENERGY_WINDOW` has the numbers. It earns its place by
    telling two identical-looking outcomes apart after the fact, not by
    deciding anything.
    """

    rmsd: float
    energy_difference: float | None
    merged: bool
    tfd: float | None = None
    max_dihedral_change: float | None = None
    largest_torsion: tuple[int, int, int, int] | None = None


def _torsion_deviation(first: Chem.Mol, second: Chem.Mol) -> tuple[float | None, float | None, tuple[int, int, int, int] | None]:
    """TFD, largest single dihedral change (degrees), and which torsion.

    Returns `(None, None, None)` rather than raising when RDKit declines
    the molecule -- a diagnostic that fails must not take down a
    generation run that is otherwise fine.
    """
    try:
        combined = Chem.Mol(first)
        combined.RemoveAllConformers()
        combined.AddConformer(Chem.Conformer(first.GetConformer()), assignId=True)
        combined.AddConformer(Chem.Conformer(second.GetConformer()), assignId=True)
        tfd = TorsionFingerprints.GetTFDBetweenConformers(combined, [0], [1])[0]
        # BOTH LISTS. `CalculateTorsionLists` returns (non-ring, ring) and
        # taking only the first makes this blind to ring pucker -- which
        # is the one degree of freedom the molecules that motivated this
        # module actually have. Measured: cyclohexane has ZERO non-ring
        # torsions and one ring group, so the non-ring-only version
        # reported "max dihedral 0.0 deg" for a chair/twist-boat pair
        # while TFD read 0.407. Ethylmorphine is 2 non-ring against 5
        # ring groups, so it was reporting on the ethyl ether alone.
        # Both entries have the same ([(a,b,c,d), ...], value) shape.
        nonring, rings = TorsionFingerprints.CalculateTorsionLists(first)
        torsions = list(nonring) + list(rings)
    except Exception:  # noqa: BLE001 - diagnostics are never load-bearing
        return None, None, None
    worst = 0.0
    worst_atoms: tuple[int, int, int, int] | None = None
    for atom_groups, _method in torsions:
        for atoms in atom_groups:
            try:
                a = rdMolTransforms.GetDihedralDeg(first.GetConformer(), *atoms)
                b = rdMolTransforms.GetDihedralDeg(second.GetConformer(), *atoms)
            except Exception:  # noqa: BLE001
                continue
            # Periodic: 350 deg and 10 deg are 20 apart, not 340.
            delta = abs((a - b + 180.0) % 360.0 - 180.0)
            if delta > worst:
                worst, worst_atoms = delta, tuple(atoms)
    return tfd, worst, worst_atoms


def merge_candidates(
    results: list[tuple[Chem.Mol, float | None]],
    rms_threshold: float = DEFAULT_RMS_THRESHOLD,
    energy_window: float = DEFAULT_ENERGY_WINDOW,
    with_torsions: bool = True,
) -> list[MergeCandidate]:
    """Diagnostics for pairs `distinct_conformers` considered merging.

    SCOPED TO MERGE CANDIDATES, not every pair, or this turns generation
    into a pairwise-analysis monster: at 100 embeddings the full matrix
    is ~5000 torsion analyses against a few hundred here. The pairs where
    RMSD passed are exactly the population the veto acts on, and the only
    ones whose diagnosis says anything.

    `with_torsions=False` skips the expensive half; the benchmark wants
    the torsions, a routine generation run does not always.
    """
    _kept, candidates = _merge_scan(results, rms_threshold, energy_window, with_torsions)
    return candidates


def _merge_scan(
    results: list[tuple[Chem.Mol, float | None]],
    rms_threshold: float,
    energy_window: float,
    with_torsions: bool,
) -> tuple[list[tuple[Chem.Mol, float | None]], list[MergeCandidate]]:
    """One pass: what is kept, and what every merge candidate looked like.

    **THE DECISION AND THE DIAGNOSTIC HAVE TO COME OUT OF THE SAME LOOP.**
    `distinct_conformers` and `merge_candidates` were two copies of this
    walk -- same ordering, same skeleton, same `GetBestRMS`, same
    threshold, same `_permits_merge` -- one returning the survivors and
    one returning the reasons. Nothing tied them together, so the day the
    merge rule changed in one, the other would have gone on describing an
    algorithm that no longer ran, and a diagnostic that describes the
    wrong algorithm is worse than none: `DEFAULT_ENERGY_WINDOW`'s own
    comment records a conclusion that had already been reached and
    written down from a torsion number that was measuring the wrong
    thing.

    Returning both is what makes the single loop possible; each caller
    drops the half it does not want.
    """
    kept: list[tuple[Chem.Mol, float | None]] = []
    kept_heavy: list[Chem.Mol] = []
    candidates: list[MergeCandidate] = []
    for mol, energy in _in_comparison_order(results):
        try:
            heavy = comparison_skeleton(mol)
        except Exception:  # noqa: BLE001 - a shape we cannot compare is one we keep
            kept.append((mol, energy))
            continue
        duplicate = False
        for (kept_mol, kept_energy), other in zip(kept, kept_heavy):
            try:
                rmsd = rdMolAlign.GetBestRMS(heavy, other)
            except (RuntimeError, ValueError):
                # GetBestRMS raises when it cannot match the two graphs.
                # Keeping the conformer is the safe direction: showing one
                # too many is a far smaller error than silently discarding
                # a real minimum.
                continue
            if rmsd >= rms_threshold:
                continue
            merged = _permits_merge(rmsd, energy, kept_energy, energy_window)
            # The CANDIDATE is always recorded; only the torsion analysis
            # is optional. Recording it only when torsions were asked for
            # would make `with_torsions=False` return an empty list rather
            # than a cheaper one, which is a different function.
            tfd, worst, atoms = (
                _torsion_deviation(mol, kept_mol) if with_torsions else (None, None, None)
            )
            candidates.append(
                MergeCandidate(
                    rmsd=rmsd,
                    energy_difference=(
                        None if energy is None or kept_energy is None else abs(energy - kept_energy)
                    ),
                    merged=merged,
                    tfd=tfd,
                    max_dihedral_change=worst,
                    largest_torsion=atoms,
                )
            )
            if merged:
                duplicate = True
                break
        if not duplicate:
            kept.append((mol, energy))
            kept_heavy.append(heavy)
    return kept, candidates


# RDKitConformerProvider implements the same ConformerProvider ABC a future
# plugin would (openchem.plugins.interfaces.ConformerProvider) — ConformerService
# can't tell a built-in method from a plugin-supplied one.


class RDKitConformerProvider(ConformerProvider):
    """Embeds conformers one at a time (rather than RDKit's batch
    EmbedMultipleConfs) specifically so each iteration can report progress
    and honor cancellation via `on_progress`'s return value: returning
    `False` stops the loop before the next conformer starts (RDKit's own
    embed/optimize calls aren't preemptible mid-call, so this is
    best-effort, checked between conformers, not instant). A `None` return
    (the common case -- most callers' `on_progress` has no return
    statement) means "keep going," so this is fully backward compatible
    with callers that don't care about cancellation at all.
    """

    provider_id = "rdkit"

    def __init__(self, random_seed: int | None = None) -> None:
        """`random_seed` makes a run REPRODUCIBLE, and is None in the app.

        ETKDG's own default is -1, meaning "draw from the global RNG", so
        two runs of the same molecule legitimately return different
        conformers -- which is correct for a random search and useless
        for a benchmark. Given a seed, embedding `i` uses `seed + i`, so
        the attempts within one run still differ from each other while
        the run as a whole repeats exactly.

        The benchmark needs this to report seed-to-seed stability at all:
        without it, "13, 15, 14, 16" cannot be told from noise in the
        measurement harness.
        """
        self._random_seed = random_seed

    def generate_conformers(
        self,
        mol: Chem.Mol,
        num_conformers: int,
        optimize: bool,
        on_progress: Callable[[int, int], bool | None] | None = None,
    ) -> list[tuple[Chem.Mol, float | None]]:
        return self.generate_conformer_batch(mol, num_conformers, optimize, on_progress).results

    def generate_conformer_batch(
        self,
        mol: Chem.Mol,
        num_conformers: int,
        optimize: bool,
        on_progress: Callable[[int, int], bool | None] | None = None,
    ) -> ConformerBatch:
        results: list[tuple[Chem.Mol, float | None]] = []
        attempted = embedding_failures = convergence_failures = 0
        for i in range(num_conformers):
            attempted += 1
            conf_mol = self._embed_one(mol, attempt=i)
            if conf_mol is None:
                embedding_failures += 1
            elif optimize:
                energy, converged = self._optimize_one(conf_mol)
                if converged:
                    results.append((conf_mol, energy))
                else:
                    # Discarded, not kept-and-marked. A geometry that did
                    # not reach a minimum is not a candidate for ranking,
                    # for the energy veto, for de-duplication, or for a
                    # geometry calculator -- and "not converged" and
                    # "is a conformer" is an incoherent state to hold.
                    convergence_failures += 1
                    logger.info("Discarded a conformer that did not converge in %d attempts", _MAX_OPTIMISATION_ATTEMPTS)
            else:
                results.append((conf_mol, None))
            if on_progress is not None:
                should_continue = on_progress(i + 1, num_conformers)
                if should_continue is False:
                    break
        # Ascending by energy so conformer 1/N is the lowest-energy (most
        # relevant) one -- matches Marvin/standard conformer-tool convention.
        # Duplicate embeddings are NOT pruned here. `ConformerService` does
        # it, so that a plugin-supplied provider gets the same treatment
        # without having to remember to, and so the counts before and after
        # are both available where the user-facing message is built.
        # `distinct_conformers` re-sorts into the same order for itself
        # rather than trusting this, since the ordering is part of its
        # contract (see `_in_comparison_order`).
        results.sort(key=lambda item: item[1] if item[1] is not None else float("inf"))
        return ConformerBatch(
            results=results,
            attempted=attempted,
            embedded=attempted - embedding_failures,
            converged=len(results),
            embedding_failures=embedding_failures,
            convergence_failures=convergence_failures,
        )

    def _embed_one(self, mol: Chem.Mol, attempt: int = 0) -> Chem.Mol | None:
        conf_mol = Chem.AddHs(Chem.Mol(mol))
        params = AllChem.ETKDGv3()
        if self._random_seed is not None:
            # Per attempt, so the embeddings within a run still differ
            # while the run repeats. Seeding them all identically would
            # return N copies of one conformer.
            params.randomSeed = self._random_seed + attempt
        conf_id = AllChem.EmbedMolecule(conf_mol, params)
        if conf_id < 0:
            # Retry once with random coordinates — some strained/unusual
            # structures fail ETKDG's distance-geometry pass otherwise.
            params.useRandomCoords = True
            conf_id = AllChem.EmbedMolecule(conf_mol, params)
        if conf_id < 0:
            logger.warning("Failed to embed a conformer for molecule")
            return None
        return conf_mol

    def _optimize_one(self, conf_mol: Chem.Mol) -> tuple[float | None, bool]:
        """`(energy, converged)`. See `_OPTIMISATION_MAX_ITERS` for why the
        library default was not enough, and why the caller discards rather
        than keeps a `False`."""
        mmff_props = AllChem.MMFFGetMoleculeProperties(conf_mol)
        if mmff_props is not None:
            converged = self._minimise(
                lambda: AllChem.MMFFOptimizeMolecule(
                    conf_mol, confId=0, maxIters=_OPTIMISATION_MAX_ITERS
                )
            )
            force_field = AllChem.MMFFGetMoleculeForceField(conf_mol, mmff_props, confId=0)
        else:
            # MMFF94 has no parameters for some elements/charges — UFF covers
            # a much broader range of the periodic table as a fallback.
            converged = self._minimise(
                lambda: AllChem.UFFOptimizeMolecule(
                    conf_mol, confId=0, maxIters=_OPTIMISATION_MAX_ITERS
                )
            )
            force_field = AllChem.UFFGetMoleculeForceField(conf_mol, confId=0)
        energy = force_field.CalcEnergy() if force_field is not None else None
        return energy, converged

    @staticmethod
    def _minimise(step: Callable[[], int]) -> bool:
        """Run `step` until it reports convergence (0), at most
        `_MAX_OPTIMISATION_ATTEMPTS` times. Each call continues from the
        previous one's coordinates, since RDKit minimises in place."""
        for _attempt in range(_MAX_OPTIMISATION_ATTEMPTS):
            if step() == 0:
                return True
        return False
