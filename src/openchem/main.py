from __future__ import annotations

import os
import sys

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QApplication

from openchem.app.debug_drive import start_if_requested
from openchem.app.logging_setup import configure_logging
from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.app.window_trace import install_if_requested
from openchem.bootstrap import build_service_container
from openchem.paths import subdirectory
from openchem.services.recovery_service import RecoveryService


def main() -> int:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    configure_logging()

    app = QApplication(sys.argv)
    app.setOrganizationName("OpenChemStudio")
    app.setApplicationName("OpenChemStudio")

    services = build_service_container()
    # Before the window exists, so the trace sees every window it shows.
    app._window_tracer = install_if_requested(app, services.event_bus)
    settings = Settings(services.event_bus)
    session = SessionManager()

    window = MainWindow(services, settings, session)
    window.show()
    # Off unless OPENCHEM_DRIVE names a script. Held for the process's
    # life because a QTimer whose owner is collected stops firing, which
    # would strand a script half-way and look like the app hanging.
    window._debug_driver = start_if_requested(window)
    # Recovery copies are for a PERSON's session. A scripted run neither
    # writes them nor is asked about them: a modal question would stall it,
    # and its throwaway work must not be offered back to Alex next launch.
    # Gated on the variable, not on the driver: a script that fails to load
    # returns no driver and is still not a person's session.
    if not os.environ.get("OPENCHEM_DRIVE"):
        window.enable_recovery(
            RecoveryService(services.project_service, subdirectory("recovery"))
        )
        QTimer.singleShot(0, window.offer_recovery)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
