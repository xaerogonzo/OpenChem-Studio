from __future__ import annotations

import contextlib

import pytest

from rdkit.Chem import AllChem

from openchem.chem.conformer_providers import (
    _MAX_OPTIMISATION_ATTEMPTS,
    _OPTIMISATION_MAX_ITERS,
    RDKitConformerProvider,
)
from openchem.chem.engine import ChemistryEngine


def test_generates_requested_number_of_distinct_conformers():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCCCO")  # a flexible chain, several distinct conformers expected
    provider = RDKitConformerProvider()

    results = provider.generate_conformers(mol, num_conformers=5, optimize=False)

    assert len(results) == 5
    molblocks = {engine.mol_to_molblock(conf_mol) for conf_mol, _ in results}
    assert len(molblocks) > 1  # coordinates actually differ between conformers


def test_energy_present_only_when_optimizing():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    unoptimized = provider.generate_conformers(mol, num_conformers=2, optimize=False)
    assert all(energy is None for _, energy in unoptimized)

    optimized = provider.generate_conformers(mol, num_conformers=2, optimize=True)
    assert all(energy is not None for _, energy in optimized)


def test_on_progress_called_once_per_conformer():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    calls: list[tuple[int, int]] = []
    provider.generate_conformers(mol, num_conformers=3, optimize=False, on_progress=lambda d, t: calls.append((d, t)))

    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_on_progress_returning_false_stops_early():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    calls: list[tuple[int, int]] = []

    def on_progress(done: int, total: int) -> bool:
        calls.append((done, total))
        return done < 2  # stop right after the 2nd conformer

    results = provider.generate_conformers(mol, num_conformers=5, optimize=False, on_progress=on_progress)

    assert calls == [(1, 5), (2, 5)]
    assert len(results) == 2


def test_conformers_are_sorted_ascending_by_energy():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCCCCCO")  # flexible chain, several distinct energies expected
    provider = RDKitConformerProvider()

    results = provider.generate_conformers(mol, num_conformers=8, optimize=True)

    energies = [energy for _, energy in results]
    assert energies == sorted(energies)


def test_on_progress_returning_none_keeps_going():
    """The common case -- most callers' on_progress has no return
    statement at all (implicitly None) -- must not be mistaken for a
    cancellation request."""
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    def on_progress(done: int, total: int) -> None:
        pass  # no return statement -- implicitly None

    results = provider.generate_conformers(mol, num_conformers=3, optimize=False, on_progress=on_progress)

    assert len(results) == 3


# --------------------------------------------------------------------------
# Convergence. RDKit's MMFFOptimizeMolecule default is maxIters=200 and the
# shipped code discarded its return code entirely: 1 of 10 ethylmorphine
# embeddings sat 3.67 kcal/mol above its own minimum while being presented
# as "conformer 1 is the lowest in energy".
# --------------------------------------------------------------------------


@contextlib.contextmanager
def _never_converging(calls: list | None = None):
    """A force field whose `Minimize` -- and the batch API the default level uses -- never
    reports convergence.

    Wraps the REAL force field so energies stay real and only the
    convergence answer is forced -- a stub returning a fake energy would
    also disable the ranking these tests do not mean to touch.
    """
    original = AllChem.MMFFGetMoleculeForceField

    def wrapped(*args, **kwargs):
        field = original(*args, **kwargs)

        class _Stubborn:
            def Minimize(self, **minimise_kwargs):  # noqa: N802 - RDKit's name
                if calls is not None:
                    calls.append(minimise_kwargs)
                return 1

            def CalcEnergy(self):  # noqa: N802 - RDKit's name
                return field.CalcEnergy()

        return _Stubborn()

    original_confs = AllChem.MMFFOptimizeMoleculeConfs

    def wrapped_confs(mol, numThreads=1, maxIters=200, **kwargs):  # noqa: N803 - RDKit's names
        """The "Normal" level goes through the batch API (it releases the GIL); force the
        same answer there, recording the call in the shape the force-field path records."""
        if calls is not None:
            calls.append({"maxIts": maxIters})
        real = original_confs(mol, numThreads=numThreads, maxIters=maxIters, **kwargs)
        return [(1, energy) for _flag, energy in real]

    AllChem.MMFFGetMoleculeForceField = wrapped
    AllChem.MMFFOptimizeMoleculeConfs = wrapped_confs
    try:
        yield
    finally:
        AllChem.MMFFGetMoleculeForceField = original
        AllChem.MMFFOptimizeMoleculeConfs = original_confs


def test_a_conformer_that_never_converges_is_discarded():
    """Not kept-and-marked. A geometry that did not reach a minimum is not
    a candidate for ranking, for the energy veto, for de-duplication, or
    for a geometry calculator -- and "not converged" and "is a conformer"
    is an incoherent state to hold."""
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider(random_seed=0)

    # Patched at the FORCE FIELD, not at `MMFFOptimizeMolecule`: the
    # optimisation goes through `ForceField.Minimize` now, because that is
    # the only entry point taking a force tolerance -- and a gradient
    # criterion is what an optimisation LEVEL has to vary.
    with _never_converging():
        batch = provider.generate_conformer_batch(mol, num_conformers=4, optimize=True)

    assert batch.results == []
    assert batch.attempted == 4
    assert batch.embedded == 4
    assert batch.converged == 0
    assert batch.convergence_failures == 4
    # The two failure modes are counted separately on purpose: one
    # "4 disappeared" figure has two different answers.
    assert batch.embedding_failures == 0


def test_optimisation_is_retried_a_bounded_number_of_times():
    """Exactly `_MAX_OPTIMISATION_ATTEMPTS`, then give up.

    Bounded deliberately -- an unbounded retry loop turns a pathological
    molecule into a hang. Measured over 30 embeddings each of ethanol,
    cyclohexane, pentane, ibuprofen and ethylmorphine, 150 of 150
    converged on the FIRST call at maxIters=2000, so the retry is a
    safety net rather than the normal path.
    """
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    calls: list[dict] = []

    with _never_converging(calls):
        RDKitConformerProvider(random_seed=0).generate_conformer_batch(
            mol, num_conformers=1, optimize=True
        )

    assert len(calls) == _MAX_OPTIMISATION_ATTEMPTS
    # The library default of 200 is what shipped and was not enough.
    assert all(call["maxIts"] == _OPTIMISATION_MAX_ITERS for call in calls)
    assert _OPTIMISATION_MAX_ITERS > 200


def test_a_seed_makes_a_run_reproducible_without_making_it_uniform():
    """Both halves matter.

    Seeded, two runs must agree -- otherwise the benchmark cannot tell
    seed-to-seed variation from noise in its own harness. But the
    embeddings WITHIN a run must still differ from each other, or a
    seeded run returns N copies of one conformer, which is the exact bug
    de-duplication exists to report.
    """
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCCCO")

    first = RDKitConformerProvider(random_seed=7).generate_conformers(mol, 5, optimize=False)
    second = RDKitConformerProvider(random_seed=7).generate_conformers(mol, 5, optimize=False)
    blocks_first = [engine.mol_to_molblock(m) for m, _ in first]
    blocks_second = [engine.mol_to_molblock(m) for m, _ in second]
    assert blocks_first == blocks_second

    assert len(set(blocks_first)) > 1, "a seeded run collapsed to one repeated conformer"


def test_an_unseeded_provider_is_still_random():
    """The app passes no seed, and must not become deterministic by
    accident -- a conformer search that returns the same answer every
    time is not a search."""
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCCCO")
    first = RDKitConformerProvider().generate_conformers(mol, 5, optimize=False)
    second = RDKitConformerProvider().generate_conformers(mol, 5, optimize=False)
    assert [engine.mol_to_molblock(m) for m, _ in first] != [
        engine.mol_to_molblock(m) for m, _ in second
    ]


def test_a_provider_written_against_the_original_interface_still_works():
    """`generate_conformer_batch` is NOT abstract, so a plugin that only
    implements `generate_conformers` keeps working -- it just reports the
    counts it can honestly derive and nothing it cannot know."""
    from rdkit import Chem

    from openchem.plugins.interfaces import ConformerProvider

    class _OldStyleProvider(ConformerProvider):
        provider_id = "old-style"

        def generate_conformers(self, mol, num_conformers, optimize, on_progress=None):
            return [(Chem.Mol(mol), None)] * 2

    batch = _OldStyleProvider().generate_conformer_batch(
        ChemistryEngine().mol_from_smiles("CCO"), 5, optimize=False
    )
    assert len(batch.results) == 2
    assert batch.attempted == 5
    assert batch.embedded == 2
    # Zero rather than a guess: this provider does not distinguish them.
    assert batch.embedding_failures == 0
    assert batch.convergence_failures == 0


# -- the "Normal" level goes through the batch API, which releases the GIL --------------------------

#: Erythromycin A: big enough that ONE minimisation takes ~0.3 s, which is what makes a held GIL
#: visible. Frozen with `benchmarks/perf/scenarios.HEAVY_SMILES`.
_BIG_MOLECULE = (
    "CC[C@@H]1[C@@]([C@@H]([C@H](C(=O)[C@@H](C[C@@]([C@@H]([C@H]([C@@H]([C@H](C(=O)O1)C)"
    "O[C@H]2C[C@@]([C@H]([C@@H](O2)C)O)(C)OC)C)O[C@H]3[C@@H]([C@H](C[C@H](O3)C)N(C)C)O)(C)O)C)C)O)(C)O"
)


def _embedded(smiles: str, seed: int = 7):
    from rdkit import Chem

    provider = RDKitConformerProvider(random_seed=seed)
    return provider, provider._embed_one(Chem.MolFromSmiles(smiles), attempt=0)


def test_normal_level_uses_the_batch_api_and_other_levels_keep_minimize():
    from openchem.chem.conformer_providers import OPTIMISATION_LEVELS

    seen: list[str] = []
    original_confs, original_ff = AllChem.MMFFOptimizeMoleculeConfs, AllChem.MMFFGetMoleculeForceField

    def spy_confs(*args, **kwargs):
        seen.append("batch")
        return original_confs(*args, **kwargs)

    def spy_ff(*args, **kwargs):
        seen.append("force-field")
        return original_ff(*args, **kwargs)

    AllChem.MMFFOptimizeMoleculeConfs, AllChem.MMFFGetMoleculeForceField = spy_confs, spy_ff
    try:
        for name in ("Loose", "Normal", "Strict"):
            provider, conf_mol = _embedded("CCCCO")
            seen.clear()
            provider._optimize_one(conf_mol, OPTIMISATION_LEVELS[name])
            assert seen == (["batch"] if name == "Normal" else ["force-field"]), (name, seen)
    finally:
        AllChem.MMFFOptimizeMoleculeConfs, AllChem.MMFFGetMoleculeForceField = original_confs, original_ff


@pytest.mark.parametrize("smiles", ["CCO", "C1CCCCC1", "CC(C)Cc1ccc(cc1)C(C)C(=O)O", _BIG_MOLECULE])
def test_the_batch_api_reaches_the_same_energy_as_the_force_field_path(smiles):
    """Measured 0.0000 kcal/mol apart over five molecules; asserted at 1e-3 so a different
    force-field default (not a different run) is what would fail it."""
    from rdkit import Chem

    provider, conf_mol = _embedded(smiles)
    reference = Chem.Mol(conf_mol)
    field = AllChem.MMFFGetMoleculeForceField(reference, AllChem.MMFFGetMoleculeProperties(reference), confId=0)
    for _ in range(2):
        if field.Minimize(maxIts=2000, forceTol=1e-4) == 0:
            break
    energy, converged = provider._optimize_one(conf_mol)
    assert converged
    assert energy == pytest.approx(field.CalcEnergy(), abs=1e-3)


def test_minimising_a_big_molecule_does_not_starve_another_python_thread():
    """THE REASON FOR THE BATCH API. `ForceField.Minimize` holds the GIL for the whole call, so a
    worker minimising one erythromycin conformer left a 5 ms ticking thread waiting 270-470 ms
    (docs/PERFORMANCE_CENSUS.md F10). Through the batch API the worst wait measured 17 ms; the
    limit here is 8x that, because a CI machine is not this one and the failure being guarded
    against is ten times larger."""
    import threading
    import time

    provider, conf_mol = _embedded(_BIG_MOLECULE)
    done = threading.Event()
    result: list = []

    def worker() -> None:
        result.append(provider._optimize_one(conf_mol))
        done.set()

    gaps: list[float] = []
    thread = threading.Thread(target=worker)
    thread.start()
    last = time.perf_counter()
    while not done.is_set():
        time.sleep(0.005)
        now = time.perf_counter()
        gaps.append((now - last) * 1000.0)
        last = now
    thread.join()

    assert result and result[0][1], "the conformer should have converged"
    assert len(gaps) > 10, "the minimisation finished too quickly to say anything about the GIL"
    assert max(gaps) < 140.0, f"another thread was starved for {max(gaps):.0f} ms"
