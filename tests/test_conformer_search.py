"""The batched, seeded conformer search.

**WHAT THIS REPLACED, AND WHY.** Generation made exactly N embeddings once,
with no seed -- ETKDG's own "draw from the global RNG". Reported from the
running app: the same molecule gave 6 distinct conformers, then 9, then 8,
then 7. `benchmarks/conformers/funnel.py` on that molecule, 5 seeds x 100
embeddings, says why:

    distinct PRE-optimisation        3 - 4      per seed
    distinct, shipped criterion      6 - 9      per seed
    union across 5 seeds            10
    coverage                         0.80

So the de-duplication was never the bottleneck -- one hundred embeddings
contain only three or four distinct shapes to begin with -- and a single run
finds four fifths of the discovered set, a different four fifths each time.

Sampling until nothing new turns up answers both halves, and a pinned seed
makes the answer repeat. Measured with the search: 9 distinct from either of
two seeds, stopping on a plateau at 200 embeddings.

**AND "PLATEAU" IS NOT "CONVERGED".** Nothing here enumerates a
conformational space. A plateau says no unmatched candidate turned up in
the last few batches, which is a statement about the sampling.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign, rdMolTransforms

from openchem.chem.conformer_providers import (
    DEFAULT_RMS_THRESHOLD,
    STOP_BUDGET,
    STOP_PLATEAU,
    STOP_TIME,
    GenerationOptions,
    RDKitConformerProvider,
    SearchArchive,
    comparison_skeleton,
    distinct_conformers,
    search_conformers,
    select_for_return,
)
from openchem.plugins.interfaces import ConformerBatch, ConformerProvider

ETHANOL = "CCO"
#: The molecule the defect was reported on: a fused pentacyclic cage.
CAGE = "C[C@H]1CC[C@H]2[C@H]3Cc4ccc(O)c5c4[C@@]2(CCN3C)[C@H]1O5"


@pytest.fixture(scope="module")
def engine():
    from openchem.bootstrap import build_service_container

    return build_service_container().chemistry_engine


def _mol(engine, smiles: str):
    from openchem.domain.molecule import MoleculeModel

    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, smiles)
    return engine.mol_from_molblock(molecule.molblock)


def _origins(pool) -> list[str]:
    from openchem.chem.conformer_providers import ORIGIN_PROPERTY

    return [m.GetProp(ORIGIN_PROPERTY) for m, _energy in pool if m.HasProp(ORIGIN_PROPERTY)]


# --- the three quantities, kept apart -----------------------------------------
#
# `unmatched_candidate_found` controls stopping. `representative_change` and
# `survivor_count_delta` are diagnostics. Conflating the first with the third
# is the obvious implementation and it is wrong under this merge rule.


def _three_geometries():
    """A, B and C with the relations the counter-example needs.

    Built by rotating ONE torsion of hexane, so the RMSDs are real rather
    than asserted: measured at 50 degrees of separation,

        RMSD(A, B) = 0.623   >= 0.50, so A and B never merge
        RMSD(C, A) = 0.323   <  0.50
        RMSD(C, B) = 0.319   <  0.50

    C sits between two structures that are too far apart to merge with each
    other, which is exactly the shape that makes a survivor count lie.
    """
    base = Chem.AddHs(Chem.MolFromSmiles("CCCCCC"))
    AllChem.EmbedMolecule(base, AllChem.ETKDGv3(), )
    AllChem.MMFFOptimizeMolecule(base)
    start = rdMolTransforms.GetDihedralDeg(base.GetConformer(), 0, 1, 2, 3)

    def at(offset):
        m = Chem.Mol(base)
        rdMolTransforms.SetDihedralDeg(m.GetConformer(), 0, 1, 2, 3, start + offset)
        return m

    return at(0), at(100), at(50)


def test_the_counter_example_really_has_the_relations_it_claims():
    """Asserted before it is used, because the whole point below is that the
    numbers -- not the story -- produce the surprising outcome."""
    a, b, c = _three_geometries()
    rms = lambda x, y: rdMolAlign.GetBestRMS(comparison_skeleton(x), comparison_skeleton(y))

    assert rms(a, b) >= DEFAULT_RMS_THRESHOLD
    assert rms(c, a) < DEFAULT_RMS_THRESHOLD
    assert rms(c, b) < DEFAULT_RMS_THRESHOLD


def test_a_batch_that_finds_nothing_new_can_LOWER_the_distinct_count():
    """**WHY YIELD IS NOT THE SURVIVOR DELTA.**

    Leaders are chosen in ascending energy order, so a lower-energy arrival
    is re-ordered AHEAD of the existing ones and can absorb more than one of
    them. C merges with both A and B, which were too far apart to merge with
    each other:

        pool {A 3.0, B 3.4}                          2 distinct
        add   C 2.5, which merges with each of them  1 distinct

    A stopping rule keyed on "did the count go up" reads this batch as
    nothing happening, and one keyed on "did it change" reads it as
    something happening. Only "did anything fail to match" is right, and
    here the right answer is that C matched -- so this batch was quiet.
    """
    a, b, c = _three_geometries()
    pool = [(a, 3.0), (b, 3.4)]
    assert len(distinct_conformers(pool)) == 2

    archive = SearchArchive()
    assert archive.add_batch(pool) == 2, "the setup did not start with two representatives"
    unmatched = archive.add_batch([(c, 2.5)])

    assert unmatched == 0, "C merged with what was already there, so nothing was found"
    assert len(distinct_conformers(pool + [(c, 2.5)])) == 1, (
        "the survivor count did not fall, so this is no longer the case that "
        "separates the three quantities"
    )


def test_a_batch_with_a_genuinely_new_shape_resets_the_plateau():
    """The complement, and the pair is what pins the semantics -- either one
    alone is satisfied by a constant."""
    a, b, _c = _three_geometries()
    archive = SearchArchive()
    archive.add_batch([(a, 3.0)])

    assert archive.add_batch([(b, 3.4)]) == 1


def test_the_later_lower_energy_duplicate_becomes_the_representative():
    """Batch 1 finds a shape at 3.6; batch 2 finds it again at 3.0. What is
    kept must be the lower-energy one, identical to what a single pooled
    batch would have kept -- "first batch wins" must not become a selection
    rule the day sampling was split up.

    **THE ENERGIES ARE INSIDE THE VETO WINDOW, AND THEY HAVE TO BE.** The
    first version of this used 5.0 and 2.0, and the pair did not merge at
    all: `DEFAULT_ENERGY_WINDOW` is 1.0 kcal/mol, so three apart is
    evidence AGAINST sameness however close the geometries are. Correct
    behaviour, and a reminder that "the same shape" here is two criteria
    rather than one -- an example that ignores the second is not an example
    of a duplicate.
    """
    a, _b, c = _three_geometries()
    pooled = distinct_conformers([(a, 3.6), (c, 3.0)])

    assert len(pooled) == 1
    assert pooled[0][1] == 3.0


# --- batching is control flow, not sampling -----------------------------------


class _CountingProvider(ConformerProvider):
    """Records the `attempt_offset` each batch was given, and nothing else.

    A FAKE, deliberately: what is under test is that the search offsets the
    global embedding index, and asserting that through real chemistry would
    be asserting it through whatever the embedder happened to produce.
    """

    provider_id = "counting"

    def __init__(self) -> None:
        self.offsets: list[int] = []
        self.sizes: list[int] = []

    def generate_conformers(self, mol, num_conformers, optimize, on_progress=None):
        return []

    def generate_conformer_batch(
        self, mol, num_conformers, optimize, on_progress=None, options=None
    ):
        self.offsets.append(0 if options is None else options.attempt_offset)
        self.sizes.append(num_conformers)
        return ConformerBatch(
            results=[], attempted=num_conformers, embedded=0, converged=0
        )


def test_each_batch_is_told_where_the_last_one_stopped():
    """**THE GLOBAL EMBEDDING INDEX.** `_embed_one` seeds from `seed +
    attempt`, so if `attempt` were the position WITHIN a batch every batch
    would redraw the same seeds and the search would sample the same
    embeddings over and over."""
    provider = _CountingProvider()
    options = GenerationOptions(
        embedding_batch_size=10, max_embeddings=40, plateau_batches_required=99
    )

    search_conformers(provider, None, False, options)

    assert provider.offsets == [0, 10, 20, 30]
    assert provider.sizes == [10, 10, 10, 10]


def test_the_last_batch_is_trimmed_to_the_ceiling():
    """A budget of 25 in batches of 10 is 10 + 10 + 5, never 30. The ceiling
    is the promise; the batch size is the step."""
    provider = _CountingProvider()
    options = GenerationOptions(
        embedding_batch_size=10, max_embeddings=25, plateau_batches_required=99
    )

    search_conformers(provider, None, False, options)

    assert provider.sizes == [10, 10, 5]


@pytest.mark.parametrize("batch_size", [10, 25, 50])
def test_the_batch_size_does_not_change_what_is_SAMPLED(engine, batch_size):
    """Same seed and same budget draw the same embeddings at any batch size.

    **ASSERTED ON THE SEED SEQUENCE ITSELF**, through the origin each
    embedding carries, rather than inferred from resulting coordinates: a
    failure then names itself instead of arriving as two geometries that
    differ for no stated reason.
    """
    mol = _mol(engine, ETHANOL)
    options = GenerationOptions(
        embedding_batch_size=batch_size, max_embeddings=50, plateau_batches_required=99
    )

    outcome = search_conformers(RDKitConformerProvider(random_seed=4242), mol, False, options)

    assert outcome.attempted == 50
    assert _origins(outcome.pool) == [f"seed=4242 embedding={i}" for i in range(50)]


def test_the_result_is_one_pass_over_the_whole_pool(engine):
    """**THE CENTRAL INVARIANT.** With plateau stopping disabled and a fixed
    budget, what a batched search returns must be identical to what a single
    batch of the same size returns -- batching changes the control flow and
    nothing about the selection.
    """
    mol = _mol(engine, ETHANOL)

    def run(batch_size):
        options = GenerationOptions(
            embedding_batch_size=batch_size, max_embeddings=40, plateau_batches_required=99
        )
        outcome = search_conformers(
            RDKitConformerProvider(random_seed=99), mol, True, options
        )
        kept = select_for_return(distinct_conformers(outcome.pool), 20)
        return [round(energy, 6) for _mol, energy in kept]

    assert run(8) == run(40)


# --- why a search stops -------------------------------------------------------


def test_a_quiet_batch_alone_does_not_stop_the_search():
    """**ONE EMPTY BATCH IS NOT EVIDENCE OF SATURATION**, and that matters
    most here: the whole diagnosis is that ETKDG samples a small subset of
    this space, so a batch can miss a region and the next one find it."""
    provider = _CountingProvider()  # never returns anything, so every batch is quiet
    options = GenerationOptions(
        embedding_batch_size=10, max_embeddings=100, plateau_batches_required=3
    )

    outcome = search_conformers(provider, None, False, options)

    assert outcome.batches == 3
    assert outcome.stop_reason == STOP_PLATEAU
    assert outcome.batches_without_new_candidates == 3


def test_the_ceiling_binds_when_the_search_never_plateaus():
    """`while not plateau` has to terminate for a caller who passed no time
    limit, which is why `max_embeddings` is required rather than optional."""
    provider = _CountingProvider()
    options = GenerationOptions(
        embedding_batch_size=10, max_embeddings=30, plateau_batches_required=99
    )

    outcome = search_conformers(provider, None, False, options)

    assert outcome.attempted == 30
    assert outcome.stop_reason == STOP_BUDGET


def test_the_time_limit_spans_the_SEARCH_not_each_batch(engine):
    """It used to bound one call. With several, passing it through unchanged
    would give every batch the whole limit -- so a 2 s limit on a search of
    eight batches would run for sixteen."""
    import time

    mol = _mol(engine, CAGE)
    options = GenerationOptions(
        embedding_batch_size=5,
        max_embeddings=5000,
        plateau_batches_required=99,
        time_limit_seconds=2.0,
    )

    started = time.monotonic()
    outcome = search_conformers(RDKitConformerProvider(random_seed=1), mol, True, options)
    elapsed = time.monotonic() - started

    assert outcome.stop_reason == STOP_TIME
    assert elapsed < 20.0, f"a 2 s limit ran for {elapsed:.1f} s"


def test_the_number_to_KEEP_is_not_a_stopping_condition(engine):
    """`select_for_return` is deliberately a separate stage. A search that
    stopped once it had enough survivors would find a smaller pool and hand
    back a worse-chosen slice of it -- the cap picks the lowest-energy
    members, which is only the lowest-energy members OF WHAT WAS FOUND."""
    mol = _mol(engine, ETHANOL)
    options = GenerationOptions(embedding_batch_size=10, max_embeddings=60)

    outcome = search_conformers(RDKitConformerProvider(random_seed=7), mol, True, options)

    assert len(distinct_conformers(outcome.pool)) >= 2
    assert len(select_for_return(distinct_conformers(outcome.pool), 1)) == 1
    assert outcome.attempted > 10, "the search stopped as soon as it had one"


# --- seeds --------------------------------------------------------------------


def test_the_same_seed_gives_the_same_search(engine):
    mol = _mol(engine, ETHANOL)
    options = GenerationOptions(embedding_batch_size=10, max_embeddings=50)

    def run():
        outcome = search_conformers(
            RDKitConformerProvider(random_seed=2024), mol, True, options
        )
        return outcome.attempted, [round(e, 6) for _m, e in distinct_conformers(outcome.pool)]

    assert run() == run()


def test_different_seeds_are_PERMITTED_to_differ(engine):
    """**NOT REQUIRED TO DIFFER, AND NOT REQUIRED TO MATCH.** A first draft
    asserted that pooling seeds beats any single run, which no algorithm can
    guarantee -- for a rigid molecule independent seeds may legitimately
    find the same set, which is close to what the funnel shows at coverage
    0.80.

    So what is asserted is that the seed REACHES the embedder, on a fake
    whose candidate set depends on it, and the real benchmark measures seed
    diversity rather than pretending it is an invariant.
    """
    mol = _mol(engine, ETHANOL)
    options = GenerationOptions(
        embedding_batch_size=10, max_embeddings=20, plateau_batches_required=99
    )

    first = search_conformers(RDKitConformerProvider(random_seed=1), mol, False, options)
    second = search_conformers(RDKitConformerProvider(random_seed=500), mol, False, options)

    assert _origins(first.pool)[0] == "seed=1 embedding=0"
    assert _origins(second.pool)[0] == "seed=500 embedding=0"


def test_an_unseeded_provider_is_still_allowed(engine):
    """The benchmark and any plugin may pass None, which is ETKDG's own
    default. What changed is that the APPLICATION no longer does."""
    mol = _mol(engine, ETHANOL)
    options = GenerationOptions(embedding_batch_size=5, max_embeddings=10)

    outcome = search_conformers(RDKitConformerProvider(), mol, False, options)

    assert outcome.attempted == 10
    assert _origins(outcome.pool)[0].startswith("seed=none")


# --- the survivors ------------------------------------------------------------


class _ScriptedProvider(ConformerProvider):
    """Hands back a prepared batch each call, and records what it was given.

    Real chemistry cannot be aimed precisely enough for the cases below: they
    turn on a batch having a specific relation to what the pool already holds,
    which is a property of the numbers rather than of any molecule.
    """

    provider_id = "scripted"

    def __init__(self, batches):
        self._batches = list(batches)
        self.limits: list[float | None] = []
        self.calls = 0

    def generate_conformers(self, mol, num_conformers, optimize, on_progress=None):
        return []

    def generate_conformer_batch(
        self, mol, num_conformers, optimize, on_progress=None, options=None
    ):
        self.limits.append(None if options is None else options.time_limit_seconds)
        results = self._batches[self.calls] if self.calls < len(self._batches) else []
        self.calls += 1
        return ConformerBatch(
            results=list(results),
            attempted=num_conformers,
            embedded=len(results),
            converged=len(results),
        )


def _four_geometries():
    """A, B, C as above, plus D -- far enough from all three to match none.

    Measured at 250 degrees from A: 0.676 to A, 0.564 to B, 0.738 to C,
    every one above the 0.50 threshold.
    """
    base = Chem.AddHs(Chem.MolFromSmiles("CCCCCC"))
    AllChem.EmbedMolecule(base, AllChem.ETKDGv3())
    AllChem.MMFFOptimizeMolecule(base)
    start = rdMolTransforms.GetDihedralDeg(base.GetConformer(), 0, 1, 2, 3)

    def at(offset):
        m = Chem.Mol(base)
        rdMolTransforms.SetDihedralDeg(m.GetConformer(), 0, 1, 2, 3, start + offset)
        return m

    return at(0), at(100), at(50), at(250)


def test_the_search_keeps_going_on_a_batch_the_SURVIVOR_COUNT_calls_quiet():
    """**THE CASE THE TWO RULES ANSWER DIFFERENTLY**, and the reason the
    archive exists at all.

    Batch 2 holds C, which merges with both A and B, AND D, which merges
    with none of them. So it contains a genuinely new shape -- and the
    distinct count does not move, because C absorbs two representatives
    while D adds one:

        pool {A 3.0, B 3.4}                 2 distinct
        add  {C 2.5, D 3.2}                 2 distinct   delta 0

    A rule keyed on the count reads that as saturation and stops. The
    search must not: something was found.
    """
    a, b, c, d = _four_geometries()
    assert len(distinct_conformers([(a, 3.0), (b, 3.4)])) == 2
    assert len(distinct_conformers([(a, 3.0), (b, 3.4), (c, 2.5), (d, 3.2)])) == 2, (
        "the setup no longer has a zero delta, so it no longer separates the rules"
    )

    provider = _ScriptedProvider([[(a, 3.0), (b, 3.4)], [(c, 2.5), (d, 3.2)], []])
    options = GenerationOptions(
        embedding_batch_size=2, max_embeddings=100, plateau_batches_required=1
    )

    outcome = search_conformers(provider, None, True, options)

    assert outcome.batches == 3, (
        f"stopped after {outcome.batches} batches -- batch 2 found a new shape "
        f"and only the survivor count says otherwise"
    )


def test_each_batch_gets_the_time_that_is_LEFT(qapp=None):
    """**THE DEADLINE SPANS THE SEARCH.** Passing the limit through unchanged
    gives every batch the whole of it, so an eight-batch search under a 2 s
    limit runs for sixteen.

    Asserted on what the provider was HANDED, not on a wall clock: a timing
    bound loose enough to be stable is loose enough to pass with the defect
    in place, which is how this survived its first mutation arm.
    """
    provider = _ScriptedProvider([[], [], []])
    options = GenerationOptions(
        embedding_batch_size=1,
        max_embeddings=3,
        plateau_batches_required=99,
        time_limit_seconds=5.0,
    )

    search_conformers(provider, None, False, options)

    assert provider.limits[0] is not None
    assert provider.limits[0] <= 5.0
    # **STRICTLY smaller each time, not merely non-increasing.** The first
    # version allowed equality and the mutation arm walked straight through
    # it: handing every batch the same 5.0 IS a non-increasing sequence.
    # What the fix produces is the time that is LEFT, which cannot repeat --
    # `time.monotonic()` has advanced by the time the next batch starts.
    assert all(
        later < earlier
        for earlier, later in zip(provider.limits, provider.limits[1:])
    ), f"the limit handed down did not shrink: {provider.limits}"
