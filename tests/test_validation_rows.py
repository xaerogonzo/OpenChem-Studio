"""The leakage rule and the row schema, on synthetic rows.

Nothing here is chemistry data: the molecules are ordinary ones chosen so that each test isolates one rule.
What is guarded is that leakage is judged on chemical identity, per model and per property, that an unknown
population is an error rather than "clean", and that a row without a reference state stays out of the common set.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def vr():
    spec = importlib.util.spec_from_file_location("validation_rows", ROOT / "tools" / "validation_rows.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # a dataclass looks its module up here
    spec.loader.exec_module(module)
    return module


def _row(vr, row_id, smiles, prop="tb", **kw):
    base = dict(value=1.0, units="K", source_id="synthetic", record_id=row_id, partition="holdout",
                temperature_k=298.15, phase="solid")
    base.update(kw)
    return vr.ValidationRow(row_id=row_id, smiles=smiles, property=prop, **base)


def test_two_spellings_of_one_molecule_have_one_identity(vr):
    assert vr.identity_block("C1=CC=CC=C1") == vr.identity_block("c1ccccc1")


def test_a_different_molecule_has_a_different_identity(vr):
    assert vr.identity_block("c1ccccc1") != vr.identity_block("Cc1ccccc1")


def test_two_enantiomers_share_an_identity_and_that_errs_toward_excluding(vr):
    """The first InChIKey block ignores stereo. That merges genuinely different stereoisomers, which can only
    over-exclude, never leak."""
    assert vr.identity_block("C[C@H](N)C(=O)O") == vr.identity_block("C[C@@H](N)C(=O)O")


def test_an_unreadable_string_raises_rather_than_sharing_a_placeholder(vr):
    with pytest.raises(ValueError, match="cannot read"):
        vr.identity_block("not a molecule")


def test_a_row_in_the_fit_population_is_excluded_however_it_is_spelled(vr):
    populations = {("m", "tb"): vr.population_blocks(["c1ccccc1"])}
    rows = [_row(vr, "benzene-kekule", "C1=CC=CC=C1"), _row(vr, "toluene", "Cc1ccccc1")]

    kept, excluded = vr.exclude_leaked(rows, "m", populations)

    assert [r.row_id for r in excluded] == ["benzene-kekule"]
    assert [r.row_id for r in kept] == ["toluene"]


def test_leakage_is_per_property(vr):
    """Benzene is in the model's Tb fit but not its Tc fit, so it is honest Tc validation data."""
    populations = {
        ("m", "tb"): vr.population_blocks(["c1ccccc1"]),
        ("m", "tc"): vr.population_blocks(["Cc1ccccc1"]),
    }
    rows = [_row(vr, "b-tb", "c1ccccc1", prop="tb"), _row(vr, "b-tc", "c1ccccc1", prop="tc")]

    kept, excluded = vr.exclude_leaked(rows, "m", populations)

    assert [r.row_id for r in excluded] == ["b-tb"] and [r.row_id for r in kept] == ["b-tc"]


def test_leakage_is_per_model(vr):
    populations = {("a", "tb"): vr.population_blocks(["c1ccccc1"]), ("b", "tb"): vr.population_blocks(["CCO"])}
    rows = [_row(vr, "benzene", "c1ccccc1")]
    assert vr.exclude_leaked(rows, "a", populations)[1] and not vr.exclude_leaked(rows, "b", populations)[1]


def test_an_unrecorded_population_is_an_error_not_no_leakage(vr):
    """The general Cp population in Burkhardt 2026 cannot be enumerated from its SI: unknown must not read as clean."""
    with pytest.raises(vr.UnknownFitPopulation, match="unknown"):
        vr.exclude_leaked([_row(vr, "r", "CCO", prop="cp")], "m", {("m", "tb"): frozenset()})


@pytest.mark.parametrize(
    ("kw", "phrase"),
    [({"temperature_k": None}, "reference temperature"), ({"phase": None}, "reference phase")],
)
def test_a_row_without_a_reference_state_stays_out_of_the_common_set(vr, kw, phrase):
    assert phrase in vr.admit_to_common_set(_row(vr, "r", "CCO", **kw))


def test_a_complete_row_may_enter(vr):
    assert vr.admit_to_common_set(_row(vr, "r", "CCO")) is None


def test_a_partition_and_a_phase_outside_the_vocabulary_are_refused(vr):
    with pytest.raises(ValueError, match="partition"):
        _row(vr, "r", "CCO", partition="test")
    with pytest.raises(ValueError, match="phase"):
        _row(vr, "r", "CCO", phase="plasma")


def test_there_are_three_partitions_never_two(vr):
    """Development, selection and holdout are different uses of data."""
    assert vr.PARTITIONS == {"development", "selection", "holdout"}
