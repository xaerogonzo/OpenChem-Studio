"""Diversity, optimisation strictness, a time limit, and refinement.

Reported as "Generating conformers in our system is still very, very bad.
I think we should make it resemble marvin's conformer generator calculator
much more closely", with ChemAxon's Generate3D page.

**The controls are emulated; algorithmic equivalence is NOT claimed**, and
several tests here exist to keep it that way. ChemAxon's page states no
default values for any of the four -- checked, so ours are not presented
as matching theirs.
"""

from __future__ import annotations

import time

import pytest

from openchem.chem.conformer_providers import (
    DEFAULT_OPTIMISATION_LEVEL,
    DEFAULT_RMS_THRESHOLD,
    OPTIMISATION_LEVELS,
    GenerationOptions,
    RDKitConformerProvider,
    distinct_conformers,
)
from openchem.chem.engine import ChemistryEngine

#: The most flexible molecule in the de-duplication corpus, and the only
#: one whose retained count moves with the optimisation level.
ETHYLMORPHINE = "CN1CC[C@]23[C@@H]4[C@H]1CC5=C2C(=C(C=C5)OCC)O[C@H]3[C@H](C=C4)O"
PENTANE = "CCCCC"


@pytest.fixture(scope="module")
def engine():
    return ChemistryEngine()


# --- diversity ---------------------------------------------------------------


def test_the_diversity_threshold_actually_changes_the_count(engine):
    """It is exposed so it can be changed, so changing it must do
    something. A threshold wired to nothing would be the worst outcome:
    a control that looks like it is working."""
    mol = engine.mol_from_smiles(PENTANE)
    batch = RDKitConformerProvider(random_seed=0xC0FFEE).generate_conformer_batch(
        mol, 30, optimize=True
    )

    loose = len(distinct_conformers(batch.results, rms_threshold=1.5))
    tight = len(distinct_conformers(batch.results, rms_threshold=0.1))

    assert tight > loose, f"tight {tight} was not more than loose {loose}"


def test_the_service_really_uses_the_options_it_was_given(qapp, engine):
    """THROUGH THE SERVICE, not by re-reading the dataclass.

    The first version of this test asserted that
    `GenerationOptions(diversity_rmsd=0.9).diversity_rmsd == 0.9`, which
    is a fact about a dataclass and says nothing about whether the service
    carries it anywhere. Two mutations proved it -- dropping the options
    on the floor, and pruning at the default threshold -- and both passed.

    So this runs a real generation and reads the provenance the service
    wrote, which is the only place the chosen values are observable from
    outside.
    """
    import time as _time

    from openchem.domain.molecule import MoleculeModel
    from openchem.events.base import EventBus
    from openchem.events.events import ConformersReady
    from openchem.services.conformer_service import ConformerService

    bus = EventBus()
    service = ConformerService(bus, engine)
    molecule = MoleculeModel(display_name="Pentane")
    engine.set_structure_from_smiles(molecule, PENTANE)

    ready: list = []
    bus.subscribe(ConformersReady, ready.append)

    service.request_conformers(
        molecule,
        30,
        optimize=True,
        # Enough embeddings that the DEFAULT threshold gives a clearly
        # different answer from the coarse one -- with six, both produce a
        # small number and the assertion below cannot tell them apart. A
        # mutation pruning at the default passed exactly that way.
        num_embeddings=30,
        options=GenerationOptions(
            diversity_rmsd=1.75, optimisation="Strict", enhanced_refinement=True
        ),
    )

    from PySide6.QtCore import QThreadPool

    deadline = _time.time() + 60
    while _time.time() < deadline and not ready:
        QThreadPool.globalInstance().waitForDone(200)
        qapp.processEvents()
    assert ready, "the generation never finished"

    parameters = ready[0].conformers[0].provenance.parameters
    assert parameters["rms_threshold"] == 1.75, parameters
    assert parameters["optimisation_level"] == "Strict", parameters
    assert parameters["refinement_method"] == "enhanced_optimization", parameters
    # And the threshold was USED, not merely recorded. Measured: 30
    # embeddings of pentane give 5 distinct shapes at the shipped 0.5 A
    # and far fewer at 1.75, so this number separates the two.
    assert parameters["conformers_distinct"] <= 3, parameters


# --- optimisation strictness -------------------------------------------------


def test_every_level_is_a_real_and_distinct_setting():
    """Four labels that mapped to the same numbers would be a menu that
    does nothing. Both halves: strictly increasing effort, and a tolerance
    that actually tightens."""
    levels = [OPTIMISATION_LEVELS[name] for name in OPTIMISATION_LEVELS]
    iterations = [iters for iters, _tol, _attempts in levels]
    tolerances = [tol for _iters, tol, _attempts in levels]

    assert iterations == sorted(iterations), iterations
    assert tolerances == sorted(tolerances, reverse=True), tolerances
    assert len(set(tolerances)) == len(tolerances), "two levels share a tolerance"


def test_normal_is_the_default_and_reproduces_what_shipped():
    """Somebody who never opens the menu must get the behaviour the
    150-of-150 convergence measurement was taken against."""
    from openchem.chem.conformer_providers import (
        _MAX_OPTIMISATION_ATTEMPTS,
        _OPTIMISATION_MAX_ITERS,
    )

    iterations, _tolerance, attempts = OPTIMISATION_LEVELS[DEFAULT_OPTIMISATION_LEVEL]

    assert GenerationOptions().optimisation == DEFAULT_OPTIMISATION_LEVEL
    assert iterations == _OPTIMISATION_MAX_ITERS
    assert attempts == _MAX_OPTIMISATION_ATTEMPTS


def test_a_non_converged_geometry_is_discarded_at_every_level(engine):
    """**THE STRICTNESS DECIDES HOW HARD TO TRY, NOT WHAT COUNTS.**

    The plan for this work suggested the level should decide whether to
    keep a non-converged geometry. It must not: CLAUDE.md records, with
    the measurement behind it, that such a structure corrupts the energy
    ranking, the 1 kcal/mol veto, the de-duplication and any geometry
    calculator -- and "did not converge" and "is a conformer" is an
    incoherent pair to hold at once.
    """
    from tests.test_conformer_providers import _never_converging

    mol = engine.mol_from_smiles("CCO")
    for level in OPTIMISATION_LEVELS:
        with _never_converging():
            batch = RDKitConformerProvider(random_seed=0).generate_conformer_batch(
                mol, 3, optimize=True, options=GenerationOptions(optimisation=level)
            )
        assert batch.results == [], f"{level} kept a geometry that never converged"
        assert batch.convergence_failures == 3


# --- the time limit ----------------------------------------------------------


def test_the_time_limit_stops_starting_new_embeddings(engine):
    """A big request with a small limit must come back early.

    Asserted on the ATTEMPT count rather than the wall clock, because a
    clock assertion on a loaded machine is a flake generator -- and the
    attempt count is the thing the limit actually governs.
    """
    mol = engine.mol_from_smiles(ETHYLMORPHINE)

    batch = RDKitConformerProvider(random_seed=0xC0FFEE).generate_conformer_batch(
        mol, 200, optimize=True, options=GenerationOptions(time_limit_seconds=0.5)
    )

    assert batch.attempted < 200, "the limit did not stop anything"
    assert batch.results, "the limit stopped everything, leaving nothing"


def test_no_time_limit_means_every_embedding_is_attempted(engine):
    """The other direction, so a limit that always fires cannot pass."""
    mol = engine.mol_from_smiles("CCO")

    batch = RDKitConformerProvider(random_seed=0).generate_conformer_batch(
        mol, 8, optimize=True, options=GenerationOptions(time_limit_seconds=None)
    )

    assert batch.attempted == 8


def test_the_limit_is_an_upper_bound_on_STARTING_not_a_hard_ceiling(engine):
    """Stated as a test because the promise is easy to overstate.

    Neither `EmbedMolecule` nor a minimisation is interruptible, so a run
    can overshoot by one embedding. A test demanding it finish within the
    limit would be asserting a guarantee the library cannot give.
    """
    mol = engine.mol_from_smiles(ETHYLMORPHINE)
    limit = 0.3

    started = time.monotonic()
    RDKitConformerProvider(random_seed=0xC0FFEE).generate_conformer_batch(
        mol, 200, optimize=True, options=GenerationOptions(time_limit_seconds=limit)
    )
    elapsed = time.monotonic() - started

    assert elapsed >= limit * 0.5, "it stopped before the limit was reached"
    # Generous, and deliberately so: the bound is "one more embedding",
    # whose cost depends on the molecule and the machine.
    assert elapsed < limit + 10.0, f"overshot by more than one embedding ({elapsed:.1f}s)"


# --- enhanced refinement, and what it is NOT ---------------------------------


def _non_docstring_strings(path):
    """Every string literal in a file that is not a docstring.

    The distinction is the whole point: a COMMENT or a docstring saying
    "this is not Marvin's hyperfine" is exactly what should be written,
    while a string literal can reach a label, a tooltip, or a stored
    property. Only the second kind is forbidden.
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_marvins_word_never_reaches_a_user_or_a_stored_file():
    """**"hyperfine" may be EXPLAINED but never SHOWN or WRITTEN.**

    ChemAxon's hyperfine is short molecular dynamics followed by strict
    optimisation; this is a second minimisation pass, and a minimiser
    cannot leave the basin it is already in -- which is the whole point of
    the dynamics. So the word belongs in comments saying what this is not,
    and nowhere a label, a tooltip or a provenance value can carry it.
    A stored SDF property outlives every UI that wrote it, and somebody
    reading `hyperfine: true` would reasonably conclude otherwise.

    Comments and docstrings are deliberately exempt. The first version of
    this test forbade the word outright and failed on the very comments
    that exist to prevent the confusion.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "openchem"
    offenders = []
    for path in root.rglob("*.py"):
        if "resources" in path.parts:
            continue
        for text in _non_docstring_strings(path):
            if "hyperfine" in text.lower():
                offenders.append((path.relative_to(root), text[:60]))

    assert not offenders, f"Marvin's term is user-visible in {offenders}"


def test_refinement_is_recorded_as_enhanced_optimization_in_provenance():
    """The name that gets STORED. Asserted on the literals rather than on
    the surrounding code, for the same reason as above."""
    from pathlib import Path

    service = (
        Path(__file__).resolve().parent.parent
        / "src" / "openchem" / "services" / "conformer_service.py"
    )
    literals = _non_docstring_strings(service)

    assert "refinement_method" in literals
    assert "enhanced_optimization" in literals


def test_refinement_does_not_invent_conformers(engine):
    """It is a second minimisation, so it can only ever keep or drop --
    never add. Measured across the corpus: it changes nothing at Normal or
    above, and its one visible effect was recovering what a Loose run had
    lost. A version that returned MORE than it was given would mean
    something other than refinement was happening.
    """
    mol = engine.mol_from_smiles(PENTANE)
    provider = RDKitConformerProvider(random_seed=0xC0FFEE)

    plain = provider.generate_conformer_batch(mol, 12, optimize=True)
    refined = provider.generate_conformer_batch(
        mol, 12, optimize=True, options=GenerationOptions(enhanced_refinement=True)
    )

    assert len(refined.results) <= len(plain.results)


def test_refinement_is_off_by_default():
    """It costs about 25% more time for no measurable gain at the default
    optimisation level. Opt-in."""
    assert GenerationOptions().enhanced_refinement is False


# --- what is NOT claimed -----------------------------------------------------


def test_the_shipped_diversity_default_is_ours_and_is_not_claimed_as_marvins():
    """ChemAxon's Generate3D page states NO default for the diversity
    parameter -- checked, twice, rather than inferred. So 0.5 is
    OpenChem's own value and nothing in the code or the UI may present it
    as matching Marvin's."""
    assert DEFAULT_RMS_THRESHOLD == 0.5
