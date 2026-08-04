"""Structured logging for every subsystem -- never print().

WHY THERE IS A FILE HANDLER. There wasn't one, and the cost of that
turned up concretely: an ADMET sidecar install failed somewhere between
"environment built" and "path saved", and once the message box was
dismissed there was no record of it anywhere on the machine. The in-app
Console panel showed it live and then it was gone with the process. A
failure you cannot read after the fact is a failure you cannot diagnose,
and that one had to be reconstructed from file timestamps and registry
archaeology instead.

So the same records now also land on disk, rotating so they cannot grow
without bound.

THE FILE FORMAT DELIBERATELY DIFFERS FROM THE CONSOLE'S. The console
shows `%H:%M:%S`, which is right for a live view and useless in a file
that spans days -- during the very session that motivated this, midnight
passed and "00:32:10" became ambiguous about which day it meant. The file
gets a full date, the logger name, and the thread, because "which thread
was that on" was one of the questions being asked.

Logging must never be the reason the application fails to start, so a
data directory that is read-only, full, or on a disconnected drive
degrades to console-only rather than raising.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

LOGGER_NAMES = [
    "openchem.ui",
    "openchem.chemistry",
    "openchem.plugin",
    "openchem.project",
    "openchem.import",
    "openchem.export",
    "openchem.performance",
    # Sidecar installs and downloads report here. It was missing from this
    # list, which was survivable only because these loggers inherit the
    # root level anyway -- but it is the one that carries setup outcomes,
    # exactly what the file handler exists to preserve.
    "openchem.services",
]

#: Name of the current log within the data directory's `logs` folder.
LOG_FILENAME = "openchem.log"

#: 2 MB per file, five kept. Large enough to hold a long session with a
#: chatty install in it, small enough to open in an editor and to attach
#: to a bug report.
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 5


def log_directory() -> Path:
    """Where logs live. Imported lazily inside the function because
    `paths` resolves the data root, and a bad `OPENCHEM_DATA_ROOT` must
    not break importing this module."""
    from openchem.paths import subdirectory

    return subdirectory("logs")


def log_file_path() -> Path:
    return log_directory() / LOG_FILENAME


def configure_logging(level: int = logging.INFO) -> None:
    """Console plus a rotating file, for every subsystem.

    Call once at startup. `ui/panels/console_panel.py` attaches its own
    handler to the root logger separately to surface records in-app --
    all three destinations see the same records.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for name in LOGGER_NAMES:
        logging.getLogger(name).setLevel(level)

    _attach_file_handler(level)


def _attach_file_handler(level: int) -> None:
    logger = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers):
        return  # configure_logging called twice; one file handler is enough

    try:
        directory = log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            directory / LOG_FILENAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:
        # A read-only or missing data directory costs the log, not the
        # application. Said on the console so it is not silent.
        logging.getLogger("openchem.ui").warning(
            "Could not open a log file (%s) -- logging to the console only", exc
        )
        return

    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    _write_session_header()


def _write_session_header() -> None:
    """A banner per run, so a log with several sessions in it can be cut
    at the right place -- and so the reader knows which build produced
    the lines that follow without having to guess from behaviour."""
    from openchem.paths import data_root

    logger = logging.getLogger("openchem.ui")
    logger.info("=" * 62)
    logger.info(
        "OpenChem Studio session started %s",
        datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
    )
    logger.info("Python %s on %s", sys.version.split()[0], sys.platform)
    logger.info("Data root: %s", data_root())
    logger.info("Log file:  %s", log_file_path())
