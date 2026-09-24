"""Log records must survive the process that produced them.

There was no file handler until an ADMET sidecar install failed between
"environment built" and "path saved", and the only record of it went away
with the in-app Console panel. Reconstructing what had happened took file
timestamps and registry inspection, and still did not fully answer it.

These tests pin the two things that make a log worth having: it is
actually written, and it can never be the reason the application fails to
start.
"""

from __future__ import annotations

import logging
import logging.handlers

import pytest

from openchem.app import logging_setup


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """Point the data root at a temp directory and strip any file handler
    the real application left on the root logger, so these tests neither
    read nor write the developer's own logs."""
    monkeypatch.setenv("OPENCHEM_DATA_ROOT", str(tmp_path))
    root = logging.getLogger()
    original = list(root.handlers)
    for handler in original:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            root.removeHandler(handler)
    yield tmp_path
    for handler in list(root.handlers):
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.close()
            root.removeHandler(handler)
    for handler in original:
        if handler not in root.handlers:
            root.addHandler(handler)


def _file_handlers():
    return [
        h for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]


def test_records_reach_a_file_on_disk(isolated_root):
    logging_setup.configure_logging()

    logging.getLogger("openchem.services").error("ADMET setup failed: something specific")
    for handler in _file_handlers():
        handler.flush()

    written = logging_setup.log_file_path().read_text(encoding="utf-8")
    assert "ADMET setup failed: something specific" in written


def test_the_services_logger_is_captured(isolated_root):
    """`openchem.services` carries sidecar install outcomes and was absent
    from LOGGER_NAMES -- survivable only by inheriting the root level, but
    it is precisely what this file exists to preserve."""
    assert "openchem.services" in logging_setup.LOGGER_NAMES


def test_the_file_entries_carry_a_date(isolated_root):
    """The console format is %H:%M:%S, which is fine live and ambiguous in
    a file spanning days -- midnight passed during the session that
    prompted this, making '00:32:10' undatable."""
    logging_setup.configure_logging()

    logging.getLogger("openchem.ui").info("a marker line")
    for handler in _file_handlers():
        handler.flush()

    written = logging_setup.log_file_path().read_text(encoding="utf-8")
    marker = next(line for line in written.splitlines() if "a marker line" in line)
    # YYYY-MM-DD at the start, and the thread, which was one of the
    # questions actually being asked during that investigation.
    assert marker[:4].isdigit() and marker[4] == "-", marker
    assert "[" in marker and "]" in marker, "thread name is recorded"


def test_a_session_header_identifies_the_run(isolated_root):
    logging_setup.configure_logging()
    for handler in _file_handlers():
        handler.flush()

    written = logging_setup.log_file_path().read_text(encoding="utf-8")
    assert "session started" in written
    assert "Data root:" in written, "so a log names the install it came from"


def test_configure_logging_twice_does_not_duplicate_the_file_handler(isolated_root):
    logging_setup.configure_logging()
    logging_setup.configure_logging()

    assert len(_file_handlers()) == 1


def test_an_unwritable_log_directory_does_not_stop_startup(isolated_root, monkeypatch):
    """The whole point of degrading rather than raising: a data root on a
    disconnected drive must cost the log, not the application."""
    def explode(*_args, **_kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(logging_setup.Path, "mkdir", explode)

    logging_setup.configure_logging()  # must not raise

    assert _file_handlers() == []
    # Console logging still works, which is what "degrades" has to mean.
    logging.getLogger("openchem.ui").info("still logging")


def test_rotation_is_bounded(isolated_root):
    """A log that grows without limit is its own bug."""
    logging_setup.configure_logging()

    handler = _file_handlers()[0]
    assert handler.maxBytes > 0
    assert handler.backupCount > 0


def test_a_scripted_run_writes_its_own_file_and_leaves_the_sessions_alone(isolated_root, monkeypatch):
    """Two processes rotating one file fails on Windows (WinError 32), and a
    byte range in a shared file is not the run's output. A driven run therefore
    gets `drive-<pid>.log`, and `openchem.log` -- the person's own session --
    is neither opened nor created."""
    import os

    monkeypatch.setenv("OPENCHEM_DRIVE", "some-script.json")
    logging_setup.configure_logging()
    logging.getLogger("openchem.services").error("a driven record")
    for handler in _file_handlers():
        handler.flush()

    path = logging_setup.log_file_path()
    assert path.name == f"drive-{os.getpid()}.log"
    assert "a driven record" in path.read_text(encoding="utf-8")
    assert not (isolated_root / "logs" / logging_setup.LOG_FILENAME).exists()


def test_an_ordinary_run_still_writes_openchem_log(isolated_root, monkeypatch):
    monkeypatch.delenv("OPENCHEM_DRIVE", raising=False)
    assert logging_setup.log_file_path().name == logging_setup.LOG_FILENAME


def test_old_driven_run_logs_are_pruned_and_the_sessions_log_is_never_touched(isolated_root, monkeypatch):
    import os

    logs = isolated_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    session = logs / logging_setup.LOG_FILENAME
    session.write_text("the person's own session", encoding="utf-8")
    for n in range(25):
        old = logs / f"drive-{100000 + n}.log"
        old.write_text("old run", encoding="utf-8")
        os.utime(old, (1_000_000 + n, 1_000_000 + n))  # a strictly increasing age
    (logs / "drive-100000.log.1").write_text("its rotation", encoding="utf-8")

    monkeypatch.setenv("OPENCHEM_DRIVE", "some-script.json")
    logging_setup.configure_logging()

    left = sorted(p.name for p in logs.glob("drive-*.log"))
    assert len(left) == logging_setup._DRIVE_LOGS_KEPT + 1  # the kept ones plus this run's own
    assert "drive-100000.log" not in left  # the oldest went
    assert not (logs / "drive-100000.log.1").exists()  # and took its rotation with it
    assert f"drive-{100000 + 24}.log" in left  # the newest survived
    assert session.read_text(encoding="utf-8") == "the person's own session"
