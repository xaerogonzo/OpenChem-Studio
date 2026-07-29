from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from openchem.app.logging_setup import configure_logging
from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container


def main() -> int:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    configure_logging()

    app = QApplication(sys.argv)
    app.setOrganizationName("OpenChemStudio")
    app.setApplicationName("OpenChemStudio")

    services = build_service_container()
    settings = Settings(services.event_bus)
    session = SessionManager()

    window = MainWindow(services, settings, session)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
