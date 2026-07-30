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


def test_cancel_invokes_the_registered_callback():
    manager = JobManager()
    calls = []
    manager.try_start("conformer", "mol-1", cancel_callback=lambda: calls.append(1))

    result = manager.cancel("conformer", "mol-1")

    assert result is True
    assert calls == [1]


def test_cancel_returns_false_when_job_not_active():
    manager = JobManager()
    assert manager.cancel("conformer", "does-not-exist") is False


def test_cancel_returns_false_when_no_callback_registered():
    manager = JobManager()
    manager.try_start("conformer", "mol-1")  # no cancel_callback given

    assert manager.cancel("conformer", "mol-1") is False


def test_active_jobs_lists_every_registered_job():
    manager = JobManager()
    manager.try_start("conformer", "mol-1")
    manager.try_start("docking", "lig-1:rec-1")

    handles = manager.active_jobs()

    assert {(h.kind, h.key) for h in handles} == {("conformer", "mol-1"), ("docking", "lig-1:rec-1")}


def test_active_jobs_excludes_finished_jobs():
    manager = JobManager()
    manager.try_start("conformer", "mol-1")
    manager.finish("conformer", "mol-1")

    assert manager.active_jobs() == []


def test_update_message_is_reflected_in_active_jobs():
    manager = JobManager()
    manager.try_start("conformer", "mol-1")

    manager.update_message("conformer", "mol-1", "3/9 conformers")

    handle = next(h for h in manager.active_jobs() if h.key == "mol-1")
    assert handle.message == "3/9 conformers"


def test_update_message_for_inactive_job_is_a_no_op():
    manager = JobManager()
    manager.update_message("conformer", "does-not-exist", "hello")  # must not raise
