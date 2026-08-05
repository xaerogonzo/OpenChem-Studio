"""The persistent result cache, and the staleness bug that motivated it.

`CacheState` has always been a lifecycle enum, never storage, so a forty
minute geometry optimisation was recomputed on demand and its scratch
directory deleted. The first thing to survive that -- the retained
wavefunction -- was keyed by `molecule_uuid`, and a uuid is stable across
structure edits. That is the bug pinned at the bottom of this file.
"""

from __future__ import annotations

import json

import pytest

from openchem.services import result_cache


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Never touch the real cache. Sibling of `isolated_settings`."""
    monkeypatch.setattr(result_cache, "cache_root", lambda: tmp_path / "results")
    yield


def _file(tmp_path, name: str, text: str = "data"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- The key is the whole design ----------------------------------------


def test_the_same_inputs_give_the_same_key_across_calls():
    """Stable across PROCESSES, which rules out `hash()` -- randomised per
    process by PYTHONHASHSEED -- and anything depending on dict order."""
    a = result_cache.key_for("orca", structure="CCO", method_basis="B3LYP def2-SVP")
    b = result_cache.key_for("orca", method_basis="B3LYP def2-SVP", structure="CCO")
    assert a == b


def test_a_different_structure_gives_a_different_key():
    """THE POINT. A cache whose key omits an input is not a cache, it is a
    way of serving stale data with extra steps."""
    benzene = result_cache.key_for("orca", structure="c1ccccc1", method_basis="B3LYP")
    toluene = result_cache.key_for("orca", structure="Cc1ccccc1", method_basis="B3LYP")
    assert benzene != toluene


def test_a_different_method_gives_a_different_key():
    svp = result_cache.key_for("orca", structure="O", method_basis="B3LYP def2-SVP")
    tzvp = result_cache.key_for("orca", structure="O", method_basis="B3LYP def2-TZVP")
    assert svp != tzvp


def test_numbers_and_their_strings_do_not_collide():
    """`1` and `"1"` are different inputs, and a key that flattened both to
    text would let a caller's type change silently reuse a result."""
    assert result_cache.key_for("k", n=1) != result_cache.key_for("k", n="1")


def test_none_is_distinct_from_the_empty_string():
    """"no basis specified" and "a basis called ''" are different inputs
    even though both are falsy."""
    assert result_cache.key_for("k", basis=None) != result_cache.key_for("k", basis="")


# --- Storing and finding ------------------------------------------------


def test_a_stored_result_is_found_by_the_same_inputs(tmp_path):
    result_cache.store(
        "orca_wavefunction",
        files={"job.gbw": _file(tmp_path, "src.gbw", "orbitals")},
        metadata={"homo": 4},
        structure="O",
        method_basis="B3LYP def2-SVP",
    )
    entry = result_cache.lookup(
        "orca_wavefunction", structure="O", method_basis="B3LYP def2-SVP"
    )
    assert entry is not None
    assert entry.file("job.gbw").read_text(encoding="utf-8") == "orbitals"
    assert entry.metadata["homo"] == 4


def test_a_different_structure_misses(tmp_path):
    result_cache.store(
        "orca_wavefunction",
        files={"job.gbw": _file(tmp_path, "a.gbw")},
        structure="c1ccccc1",
        method_basis="B3LYP",
    )
    assert (
        result_cache.lookup(
            "orca_wavefunction", structure="Cc1ccccc1", method_basis="B3LYP"
        )
        is None
    )


def test_the_inputs_are_readable_on_the_entry(tmp_path):
    """What makes an entry a RECORD rather than an opaque blob: someone
    looking months later can see the method without reversing a hash."""
    result_cache.store(
        "orca_wavefunction",
        files={"job.gbw": _file(tmp_path, "a.gbw")},
        structure="O",
        method_basis="B3LYP def2-SVP",
    )
    entry = result_cache.lookup(
        "orca_wavefunction", structure="O", method_basis="B3LYP def2-SVP"
    )
    assert entry.inputs["method_basis"] == "B3LYP def2-SVP"
    assert entry.inputs["structure"] == "O"


def test_a_missing_entry_is_none_not_an_error():
    assert result_cache.lookup("orca_wavefunction", structure="nothing") is None


def test_an_entry_with_no_manifest_is_a_miss(tmp_path):
    """The manifest is written LAST, so a run interrupted mid-copy leaves a
    directory that is IGNORED rather than one half-present and trusted."""
    key = result_cache.key_for("orca_wavefunction", structure="O")
    directory = result_cache.cache_root() / key
    directory.mkdir(parents=True)
    (directory / "job.gbw").write_text("orphan", encoding="utf-8")
    assert result_cache.entry_for(key) is None


def test_a_corrupt_manifest_is_a_miss_not_a_crash(tmp_path):
    key = result_cache.key_for("orca_wavefunction", structure="O")
    directory = result_cache.cache_root() / key
    directory.mkdir(parents=True)
    (directory / "entry.json").write_text("{not json", encoding="utf-8")
    assert result_cache.entry_for(key) is None


def test_an_entry_from_an_older_cache_version_is_ignored(tmp_path):
    """Bumping the version must retire entries rather than migrate data
    that is regenerable by definition."""
    key = result_cache.key_for("orca_wavefunction", structure="O")
    directory = result_cache.cache_root() / key
    directory.mkdir(parents=True)
    (directory / "entry.json").write_text(
        json.dumps({"version": result_cache.CACHE_VERSION - 1, "kind": "x"}),
        encoding="utf-8",
    )
    assert result_cache.entry_for(key) is None


def test_storing_twice_replaces_rather_than_merges(tmp_path):
    """A partially-overwritten entry mixes files from two runs, and for a
    wavefunction that means a `.gbw` and a `.densities` describing
    different calculations."""
    result_cache.store(
        "k", files={"a.txt": _file(tmp_path, "a", "first"), "gone.txt": _file(tmp_path, "g")},
        structure="O",
    )
    result_cache.store(
        "k", files={"a.txt": _file(tmp_path, "a2", "second")}, structure="O"
    )
    entry = result_cache.lookup("k", structure="O")
    assert entry.file("a.txt").read_text(encoding="utf-8") == "second"
    assert entry.file("gone.txt") is None


# --- Housekeeping -------------------------------------------------------


def test_entries_can_be_listed_and_cleared(tmp_path):
    result_cache.store("k", files={"a.txt": _file(tmp_path, "a")}, structure="O")
    result_cache.store("k", files={"a.txt": _file(tmp_path, "b")}, structure="CCO")
    assert len(result_cache.entries("k")) == 2
    assert result_cache.total_size_bytes() > 0

    freed = result_cache.clear("k")
    assert freed > 0
    assert result_cache.entries("k") == []


def test_clearing_one_kind_leaves_another(tmp_path):
    result_cache.store("keep", files={"a.txt": _file(tmp_path, "a")}, structure="O")
    result_cache.store("drop", files={"a.txt": _file(tmp_path, "b")}, structure="O")
    result_cache.clear("drop")
    assert len(result_cache.entries("keep")) == 1


# --- The bug this was built for -----------------------------------------


def test_a_wavefunction_is_refused_when_the_structure_has_changed(tmp_path, monkeypatch):
    """THE STALENESS BUG, pinned.

    A wavefunction is retained under `molecule_uuid`, and a uuid SURVIVES A
    STRUCTURE EDIT -- `EditStructureCommand` clears a molecule's conformers
    when its structure changes (Phase 9.1: they described the old
    structure) and nothing gave the wavefunction the same treatment. So
    drawing benzene, running ORCA, editing to toluene and asking for the
    HOMO plotted benzene's orbitals against toluene, silently, because the
    only check was that a file existed under that uuid.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem import paths as app_paths
    from openchem.services import qm_surface_service as module

    retained = tmp_path / "wavefunctions"
    monkeypatch.setattr(app_paths, "wavefunction_root", lambda: retained)
    monkeypatch.setattr(module.app_paths, "wavefunction_root", lambda: retained)

    def molblock(smiles: str) -> str:
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        AllChem.EmbedMolecule(mol, randomSeed=7)
        return Chem.MolToMolBlock(mol)

    benzene, toluene = molblock("c1ccccc1"), molblock("Cc1ccccc1")

    directory = retained / "mol-1"
    directory.mkdir(parents=True)
    (directory / "job.gbw").write_text("benzene orbitals", encoding="utf-8")
    (directory / "orbitals.json").write_text(
        json.dumps({"homo": 20, "lumo": 21, "structure": Chem.MolToSmiles(
            Chem.MolFromMolBlock(benzene, removeHs=False))}),
        encoding="utf-8",
    )

    service = module.QmSurfaceService.__new__(module.QmSurfaceService)

    # The structure it was computed for: a hit.
    assert service.wavefunction_for("mol-1", benzene) is not None
    # A DIFFERENT structure under the same uuid: a miss, not a wrong answer.
    assert service.wavefunction_for("mol-1", toluene) is None


def test_an_unverifiable_wavefunction_is_refused(tmp_path, monkeypatch):
    """Retained before structures were recorded. Unverifiable is not
    known-good: one wasted recalculation against a silently wrong surface
    is not a close call."""
    from openchem import paths as app_paths
    from openchem.services import qm_surface_service as module

    retained = tmp_path / "wavefunctions"
    monkeypatch.setattr(app_paths, "wavefunction_root", lambda: retained)
    monkeypatch.setattr(module.app_paths, "wavefunction_root", lambda: retained)

    directory = retained / "mol-1"
    directory.mkdir(parents=True)
    (directory / "job.gbw").write_text("orbitals", encoding="utf-8")
    (directory / "orbitals.json").write_text(
        json.dumps({"homo": 1, "lumo": 2}), encoding="utf-8"
    )

    service = module.QmSurfaceService.__new__(module.QmSurfaceService)
    assert service.wavefunction_for("mol-1") is not None      # no structure asked
    assert service.wavefunction_for("mol-1", "some molblock") is None
