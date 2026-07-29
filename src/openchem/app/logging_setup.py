from __future__ import annotations

import logging

LOGGER_NAMES = [
    "openchem.ui",
    "openchem.chemistry",
    "openchem.plugin",
    "openchem.project",
    "openchem.import",
    "openchem.export",
    "openchem.performance",
]


def configure_logging(level: int = logging.INFO) -> None:
    """Structured logging for every subsystem — never print().

    Call once at startup. `ui/panels/console_panel.py` attaches its own
    handler to the root logger separately to surface records in-app.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for name in LOGGER_NAMES:
        logging.getLogger(name).setLevel(level)
