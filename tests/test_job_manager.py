from __future__ import annotations

from openchem.services.job_manager import JobManager


def test_try_start_succeeds_when_not_active():
    manager = JobManager()
    assert manager.try_start("conformer", "mol-1") is True
    assert manager.is_active("conformer", "mol-1") is True


def test_try_start_rejects_duplicate_key():
    manager = JobManager()
    manager.try_start("conformer", "mol-1")
    assert manager.try_start("conformer", "mol-1") is False


def test_different_kind_or_key_does_not_collide():
    manager = JobManager()
    manager.try_start("conformer", "mol-1")
    assert manager.try_start("docking", "mol-1") is True
    assert manager.try_start("conformer", "mol-2") is True


def test_finish_releases_the_guard():
    manager = JobManager()
    manager.try_start("conformer", "mol-1")
    manager.finish("conformer", "mol-1")
    assert manager.is_active("conformer", "mol-1") is False
    assert manager.try_start("conformer", "mol-1") is True


def test_finish_is_idempotent():
    manager = JobManager()
    manager.finish("conformer", "does-not-exist")  # must not raise
    manager.try_start("conformer", "mol-1")
    manager.finish("conformer", "mol-1")
    manager.finish("conformer", "mol-1")  # second finish, still must not raise
