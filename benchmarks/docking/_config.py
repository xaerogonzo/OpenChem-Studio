"""Where the benchmarks find the external tools they measure.

Every script here used to carry a hardcoded absolute path to Vina or to
the ADMET sidecar. That works on exactly one machine, and worse, it lets a
benchmark drift away from the install it claims to characterise -- the
app could be configured to use one interpreter while the numbers were
measured against another.

So the tools are read from the SAME Settings the application uses. A
benchmark then measures what the app actually runs, and anyone who has
set the tools up through the UI can reproduce the tables without editing
source.
"""

from __future__ import annotations

from openchem.chem.admet_providers import ADMET_PYTHON_SETTING

#: The docking panel's own key, kept here rather than imported because
#: `chem/docking_providers.py` does not define one -- the setting is bound
#: in `bootstrap` from the UI side.
VINA_SETTING = "docking/vina_executable_path"


def _setting(key: str) -> str:
    from PySide6.QtCore import QSettings

    return str(QSettings("OpenChemStudio", "OpenChemStudio").value(key, "") or "")


def vina_executable() -> str:
    path = _setting(VINA_SETTING)
    if not path:
        raise SystemExit(
            "No Vina executable is configured.\n"
            "Set one via the Docking panel's 'Configure Vina...', then re-run."
        )
    return path


def admet_interpreter() -> str:
    path = _setting(ADMET_PYTHON_SETTING)
    if not path:
        raise SystemExit(
            "No ADMET environment is configured.\n"
            "Set one up via Tools > External Tools > ADMET (hERG/CYP), then re-run."
        )
    return path
