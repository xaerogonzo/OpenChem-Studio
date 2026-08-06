"""The content-addressed store must actually be read, not only written.

`result_cache.store()` was called for every retained wavefunction and
`result_cache.lookup()` was called from nowhere -- so finished ORCA work
was archived and then recomputed anyway. Found during a documentation
sweep, when the guide claimed a cache that did not exist.

These tests pin the two halves that make reuse safe rather than merely
possible: a hit requires the SAME structure, and the orbital indices come
from the same entry as the wavefunction they index into.
"""

from __future__ import annotations

import json

import pytest
from rdkit import Chem

from openchem import paths as app_paths
from openchem.services import result_cache
from openchem.services.qm_surface_service import QmSurfaceService
from openchem.events.base import EventBus


def _molblock(smiles: str) -> str:
    return Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))


def _fingerprint(smiles: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromMolBlock(_molblock(smiles), removeHs=False))


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point the wavefunction and cache roots at tmp_path.

    Both, because `result_cache.cache_root()` is derived from
    `wavefunction_root()`. Redirecting one and not the other would write
    into the real data directory, which is the same class of mistake the
    settings-isolation fixture exists for.
    """
    root = tmp_path / "wavefunctions"
    root.mkdir()
    monkeypatch.setattr(app_paths, "wavefunction_root", lambda: root)
    return root


def _store_wavefunction(smiles: str, *, homo: int, lumo: int, method: str, tmp_path):
    source = tmp_path / "job.gbw"
    source.write_bytes(b"not a real gbw, but a real file")
    return result_cache.store(
        "orca_wavefunction",
        files={"job.gbw": source},
        metadata={"homo": homo, "lumo": lumo},
        structure=_fingerprint(smiles),
        method_basis=method,
        calc_type="sp",
    )


def test_a_wavefunction_stored_under_one_molecule_serves_another(
    qapp, isolated_cache, tmp_path
):
    """The reuse this exists for: the same structure, a different molecule.

    Re-importing a compound, opening another project that contains it, or
    deleting and re-adding it all produce a new uuid with no retained
    wavefunction -- and used to cost a fresh ORCA run for a calculation
    already on disk.
    """
    _store_wavefunction("c1ccccc1", homo=20, lumo=21, method="B3LYP def2-SVP", tmp_path=tmp_path)
    service = QmSurfaceService(EventBus(), None)

    found = service.wavefunction_for("a-uuid-that-never-ran-anything", _molblock("c1ccccc1"))

    assert found is not None
    assert found.is_file()


def test_a_different_structure_is_still_a_miss(qapp, isolated_cache, tmp_path):
    """The guard that makes the reuse safe.

    If this ever passes, the stale-wavefunction bug is back: benzene's
    orbitals would plot against toluene, which is exactly what the
    per-molecule structure check was added to stop.
    """
    _store_wavefunction("c1ccccc1", homo=20, lumo=21, method="B3LYP def2-SVP", tmp_path=tmp_path)
    service = QmSurfaceService(EventBus(), None)

    assert service.wavefunction_for("any-uuid", _molblock("Cc1ccccc1")) is None


def test_no_structure_to_match_on_is_a_miss(qapp, isolated_cache, tmp_path):
    """With no molblock there is nothing to be sure about, and guessing is
    what the uuid path was doing wrong."""
    _store_wavefunction("c1ccccc1", homo=20, lumo=21, method="B3LYP def2-SVP", tmp_path=tmp_path)
    service = QmSurfaceService(EventBus(), None)

    assert service.wavefunction_for("a-uuid-with-nothing-retained", "") is None


def test_orbital_indices_come_from_the_entry_that_supplied_the_wavefunction(
    qapp, isolated_cache, tmp_path
):
    """An orbital index only means anything against its own wavefunction.

    HOMO is orbital 4 for water and 37 for bromobenzene, so reading the
    index from one job while plotting another's `.gbw` renders a real
    orbital that nobody asked for -- and labels it confidently.
    """
    _store_wavefunction("c1ccccc1", homo=20, lumo=21, method="B3LYP def2-SVP", tmp_path=tmp_path)
    service = QmSurfaceService(EventBus(), None)

    assert service.frontier_orbitals("some-other-uuid", _molblock("c1ccccc1")) == (20, 21)


def test_the_per_molecule_copy_still_wins_when_it_is_valid(qapp, isolated_cache, tmp_path):
    """The store is a fallback, not a replacement.

    The uuid copy is the one this molecule's own job produced, so it stays
    the first choice; the store only fills the gap when that misses.
    """
    directory = isolated_cache / "mol-1"
    directory.mkdir()
    (directory / "job.gbw").write_bytes(b"the molecule's own wavefunction")
    (directory / "orbitals.json").write_text(
        json.dumps({"homo": 7, "lumo": 8, "structure": _fingerprint("c1ccccc1")}),
        encoding="utf-8",
    )
    _store_wavefunction("c1ccccc1", homo=20, lumo=21, method="other", tmp_path=tmp_path)
    service = QmSurfaceService(EventBus(), None)

    assert service.wavefunction_for("mol-1", _molblock("c1ccccc1")) == directory / "job.gbw"
    assert service.frontier_orbitals("mol-1", _molblock("c1ccccc1")) == (7, 8)


def test_a_stale_per_molecule_copy_does_not_shadow_a_good_stored_one(
    qapp, isolated_cache, tmp_path
):
    """Edit the structure and the uuid copy goes stale. The store may still
    hold a wavefunction for what the molecule is NOW, and that is a hit."""
    directory = isolated_cache / "mol-1"
    directory.mkdir()
    (directory / "job.gbw").write_bytes(b"benzene, from before the edit")
    (directory / "orbitals.json").write_text(
        json.dumps({"homo": 7, "lumo": 8, "structure": _fingerprint("c1ccccc1")}),
        encoding="utf-8",
    )
    _store_wavefunction("Cc1ccccc1", homo=24, lumo=25, method="B3LYP def2-SVP", tmp_path=tmp_path)
    service = QmSurfaceService(EventBus(), None)

    found = service.wavefunction_for("mol-1", _molblock("Cc1ccccc1"))
    assert found is not None
    assert found != directory / "job.gbw"
    assert service.frontier_orbitals("mol-1", _molblock("Cc1ccccc1")) == (24, 25)


def test_find_is_a_partial_key_search_and_lookup_is_not(qapp, isolated_cache, tmp_path):
    """`lookup` needs every input that went into the key; `find` does not.

    Both exist because the caller that stores knows the method and the
    calculation type, and the caller that later wants a surface knows only
    the structure.
    """
    _store_wavefunction("CCO", homo=12, lumo=13, method="B3LYP def2-SVP", tmp_path=tmp_path)
    fingerprint = _fingerprint("CCO")

    assert result_cache.find("orca_wavefunction", structure=fingerprint) is not None
    assert result_cache.lookup("orca_wavefunction", structure=fingerprint) is None
    assert (
        result_cache.lookup(
            "orca_wavefunction",
            structure=fingerprint,
            method_basis="B3LYP def2-SVP",
            calc_type="sp",
        )
        is not None
    )
