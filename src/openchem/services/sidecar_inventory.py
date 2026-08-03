"""What this application has installed, and how to remove it.

Every sidecar already had a way in; none had a way out. Removing one
meant deleting a directory by hand and then remembering that its
interpreter path is still recorded in Settings -- which leaves the app
reporting a configured-but-broken tool, the same state a stale path
produced once already.

ONLY WHAT THIS APP INSTALLED IS REMOVABLE, and that rule does real work
here rather than being a platitude. Java and Vina can each be either
managed or the user's own: `java_home()` prefers a system JRE, and the
Vina path can point at a copy someone downloaded themselves. Removing
those would be deleting a user's software because they asked to free
space in an application's data folder. Each component therefore resolves
its own path and reports `is_managed`, and the ones that are not managed
offer nothing to remove.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from openchem import paths as app_paths
from openchem.chem.admet_providers import ADMET_PYTHON_SETTING
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.chem.stout_providers import STOUT_PYTHON_SETTING
from openchem.services import storage_service

logger = logging.getLogger("openchem.services")

VINA_SETTING = "docking/vina_executable_path"


class UninstallError(RuntimeError):
    """Removal failed, with a reason worth showing verbatim."""


@dataclass(frozen=True)
class Component:
    """One removable thing.

    `paths` is a list because a component is not always a single
    directory -- the shift index is a SQLite database plus its `-wal` and
    `-shm` companions, and leaving those behind would strand a few
    megabytes and, worse, let SQLite reconstruct a partial database from
    a stale write-ahead log.
    """

    key: str
    label: str
    description: str
    paths: list[Path]
    settings_keys: tuple[str, ...] = ()
    is_managed: bool = True
    unmanaged_reason: str = ""
    reinstall_hint: str = ""

    @property
    def present(self) -> bool:
        return self.is_managed and any(path.exists() for path in self.paths)

    def size_bytes(self) -> int:
        return sum(_size_of(path) for path in self.paths if path.exists())


def _size_of(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _index_paths() -> list[Path]:
    from openchem.chem.nmr_database import default_database_path

    database = default_database_path()
    # The -wal and -shm companions are part of the database, not debris.
    return [database, Path(f"{database}-wal"), Path(f"{database}-shm")]


def _java_component() -> Component:
    from openchem.services import java_setup

    system = java_setup.system_java_home()
    root = java_setup.default_install_root()
    if system is not None and not root.exists():
        return Component(
            key="java",
            label="Java runtime",
            description="Needed by STOUT and OPSIN.",
            paths=[],
            is_managed=False,
            unmanaged_reason=f"Using the system Java at {system} -- not installed by this app.",
        )
    return Component(
        key="java",
        label="Java runtime (Temurin)",
        description="Portable JRE used by STOUT and OPSIN.",
        paths=[root],
        reinstall_hint="Re-installable from the Java tab in one click.",
    )


def _vina_component(settings=None) -> Component:
    """Vina is removable only if it is the copy this app downloaded.

    A user who pointed the app at their own Vina and then clicked Remove
    would otherwise lose their own executable.
    """
    managed_dir = app_paths.subdirectory("tools") / "vina"
    configured = (settings.get(VINA_SETTING, "") if settings is not None else "") or ""
    if configured:
        try:
            inside = managed_dir.resolve() in Path(configured).resolve().parents
        except OSError:
            inside = False
        if not inside:
            return Component(
                key="vina",
                label="AutoDock Vina",
                description="Docking engine.",
                paths=[],
                is_managed=False,
                unmanaged_reason=f"Configured to {configured}, which this app did not install.",
            )
    return Component(
        key="vina",
        label="AutoDock Vina",
        description="Docking engine downloaded by this app.",
        paths=[managed_dir],
        settings_keys=(VINA_SETTING,),
        reinstall_hint="Re-downloadable from the AutoDock Vina tab.",
    )


def components(settings=None) -> list[Component]:
    """Everything removable, in a fixed order.

    CHEAP -- it stats nothing. Sizing a component means walking its tree,
    and the two sidecar environments contain hundreds of thousands of
    files: sorting this list by size cost 12.7 seconds, on top of 6.2 for
    the usage report, every single time the External Tools dialog was
    constructed. Callers that want sizes ask for them, off the GUI
    thread.

    Built fresh on each call rather than cached: the data root can move
    and a tool can be installed or reconfigured between calls, and a
    stale inventory would offer to delete the wrong path.
    """
    from openchem.services import admet_setup, pkasolver_setup, stout_setup

    items = [
        Component(
            key="admet",
            label="ADMET environment",
            description="hERG, CYP450 and Ames prediction (Python + PyTorch).",
            paths=[admet_setup.default_install_root()],
            settings_keys=(ADMET_PYTHON_SETTING,),
            reinstall_hint="Re-installable from the ADMET tab; the rule-based hERG "
            "risk-factor checklist keeps working without it.",
        ),
        Component(
            key="pkasolver",
            label="pkasolver environment",
            description="Numeric pKa prediction (Python + PyTorch).",
            paths=[pkasolver_setup.default_install_root()],
            settings_keys=(PKASOLVER_PYTHON_SETTING,),
            reinstall_hint="Re-installable from the pkasolver tab; pKa falls back to "
            "ionizable-group detection without it.",
        ),
        Component(
            key="stout",
            label="STOUT environment",
            description="Structure-to-name prediction (Python + TensorFlow).",
            paths=[stout_setup.default_install_root()],
            settings_keys=(STOUT_PYTHON_SETTING,),
            reinstall_hint="Re-installable from the STOUT tab; PubChem still names known "
            "compounds without it.",
        ),
        _java_component(),
        Component(
            key="nmr_index",
            label="NMR shift database",
            description="Experimental shifts indexed from nmrshiftdb2.",
            paths=_index_paths(),
            reinstall_hint="Rebuildable from the NMR Database tab (re-downloads ~152 MB).",
        ),
        _vina_component(settings),
        Component(
            key="cache",
            label="Scratch files",
            description="Temporary ORCA job directories.",
            paths=[app_paths.cache_root()],
            reinstall_hint="Recreated automatically as needed -- always safe to remove.",
        ),
    ]
    return items


def find(key: str, settings=None) -> Component:
    for component in components(settings):
        if component.key == key:
            return component
    raise UninstallError(f"Unknown component: {key!r}")


def uninstall(component: Component, settings=None) -> int:
    """Delete a component and forget where it was. Returns bytes freed.

    Settings are cleared AFTER the files are gone, not before: if the
    delete fails halfway the tool is still there and still configured,
    which is a working state. Clearing first would produce an install
    nothing can find.
    """
    if not component.is_managed:
        raise UninstallError(
            f"{component.label} was not installed by this app -- {component.unmanaged_reason}"
        )
    freed = component.size_bytes()
    for path in component.paths:
        if not path.exists():
            continue
        try:
            if path.is_file():
                path.unlink()
            else:
                # Not plain rmtree: the pkasolver install is a git clone
                # and git marks its pack files read-only, which Windows
                # refuses to delete. Removing pkasolver would have failed
                # for exactly the reason moving it did.
                storage_service.remove_tree(path)
        except OSError as exc:
            raise UninstallError(
                f"Could not remove {path}: {exc}. If a calculation is still running, wait for "
                "it to finish and try again."
            ) from exc

    if settings is not None:
        for key in component.settings_keys:
            settings.set(key, "")
    logger.info("Removed %s, freeing %d bytes", component.key, freed)
    return freed


def measure(settings=None) -> list[tuple[Component, int]]:
    """(component, size) pairs, biggest first. Walks the disk -- call it
    off the GUI thread."""
    measured = [(component, component.size_bytes()) for component in components(settings)]
    measured.sort(key=lambda pair: pair[1], reverse=True)
    return measured


def describe(settings=None) -> str:
    lines = []
    for component in components(settings):
        if not component.is_managed:
            lines.append(f"{component.label}: {component.unmanaged_reason}")
        elif component.present:
            lines.append(f"{component.label}: {_human(component.size_bytes())}")
        else:
            lines.append(f"{component.label}: not installed")
    return "\n".join(lines)


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
