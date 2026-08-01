"""Moving the application's data directory somewhere else.

Changing `openchem.paths` alone would only change where NEW data goes,
stranding whatever is already installed -- and for this app that is the
whole point of the exercise, since the sidecar environments are the
gigabytes someone is trying to reclaim.

THE ORDER MATTERS. Contents are moved first, the pointer is written last.
An interrupted move then leaves the pointer still aimed at the old
location, where the data actually is, rather than at a half-filled new
one. The reverse order would produce an application that cannot find its
own installs.

STORED ABSOLUTE PATHS ARE REWRITTEN. The pkasolver and STOUT interpreter
paths live in Settings as absolute paths into the data directory; moving
the files without updating them would leave both sidecars configured but
broken -- exactly the failure mode a stale `.codecov.yml` path already
caused once.

Verified that a moved virtual environment still runs: `pyvenv.cfg` records
`home` as the BASE interpreter, which does not move, and site-packages is
found relative to the executable. Tested directly by creating a venv,
installing into it, moving the directory and re-running it.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openchem import paths as app_paths
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.chem.stout_providers import STOUT_PYTHON_SETTING

logger = logging.getLogger("openchem.services")

# Settings keys holding an absolute path INTO the data directory, which
# therefore have to follow it.
#
# IMPORTED, not written as literals. The first version of this guessed the
# key names ("pkasolver/python_interpreter") and got both wrong -- so the
# move would have relocated the files and left the settings pointing at
# the old location, breaking exactly what this exists to protect. The
# accompanying test guessed identically and passed. Importing the real
# constants makes the two impossible to disagree.
_PATH_SETTINGS = (
    PKASOLVER_PYTHON_SETTING,
    STOUT_PYTHON_SETTING,
    "docking/vina_executable_path",
)



def _force_writable(func, path, exc):
    r"""rmtree error handler that clears the read-only bit and retries.

    Git marks everything under `.git/objects` READ-ONLY, and the
    pkasolver install is a git clone. On Windows a read-only file cannot
    be deleted, so removing that tree fails with

        PermissionError: [WinError 5] Access is denied:
        ...pkasolver\.git\objects\pack\pack-8245c60d....idx

    Hit for real while moving 3.7 GB: the copy had already succeeded and
    the source delete died half way, leaving a damaged original. POSIX
    does not care -- deletion there depends on the DIRECTORY's permissions
    -- which is why this only shows up on Windows.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def remove_tree(path: Path) -> None:
    """`shutil.rmtree` that coexists with read-only files."""
    shutil.rmtree(path, onexc=_force_writable)


def move_tree(source: Path, destination: Path) -> None:
    """Move one item, whatever is in the way.

    A rename is tried FIRST: within a volume it is instantaneous and
    moves nothing, where copy-then-delete would shuffle gigabytes. It
    fails across volumes, which is when the copy path is actually needed.
    """
    try:
        os.replace(source, destination)
        return
    except OSError:
        pass
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
        remove_tree(source)
    else:
        shutil.copy2(source, destination)
        source.unlink()


#: Used when someone picks a folder that already has things in it -- the
#: data goes in a subfolder rather than mixing with what is there.
#:
#: The "_Data" suffix is deliberate and is Alex's own convention: the
#: source tree is "OpenChem Studio", so a data folder called
#: "OpenChemStudio" beside it reads as a second copy of the project.
#: Naming it distinctly means the two can never be confused at a glance,
#: which matters most when someone is looking at a backup listing months
#: later.
DEFAULT_FOLDER_NAME = "OpenChemStudio_Data"


@dataclass(frozen=True)
class MoveProgress:
    step: int
    total: int
    message: str


ProgressCallback = Callable[[MoveProgress], None]


class StorageError(RuntimeError):
    """The move cannot proceed or did not finish, with a reason to show."""


@dataclass(frozen=True)
class StorageUsage:
    """What is in the data directory, largest first."""

    root: Path
    entries: list[tuple[str, int]]
    total_bytes: int

    def describe(self) -> str:
        if not self.entries:
            return f"{self.root}\n\nNothing stored yet."
        lines = [f"{self.root}", "", f"Total: {_human(self.total_bytes)}"]
        lines.extend(f"    {name}  {_human(size)}" for name, size in self.entries)
        return "\n".join(lines)


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def _directory_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            # A file that vanished mid-walk costs its own size, not the
            # whole report.
            continue
    return total


def usage(root: Path | None = None) -> StorageUsage:
    root = root or app_paths.data_root()
    if not root.is_dir():
        return StorageUsage(root=root, entries=[], total_bytes=0)
    entries = []
    for child in root.iterdir():
        try:
            entries.append((child.name, _directory_size(child)))
        except OSError:
            continue
    entries.sort(key=lambda pair: pair[1], reverse=True)
    return StorageUsage(root=root, entries=entries, total_bytes=sum(s for _n, s in entries))


def move_data_root(
    destination: Path,
    settings=None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Move everything to `destination` and point the app at it.

    `settings` is optional so this is testable without one, but passing it
    is what keeps the sidecar interpreter paths working afterwards.
    """
    source = app_paths.data_root()
    destination = Path(destination).resolve()

    if destination == source.resolve():
        raise StorageError("That is already the current location.")
    if source.resolve() in destination.parents:
        raise StorageError(
            "The new location cannot be inside the current one -- moving a directory into "
            "itself would recurse."
        )

    current = usage(source)
    if destination.exists() and any(destination.iterdir()):
        raise StorageError(
            f"{destination} is not empty. Choose an empty folder, or a new one -- this moves "
            "files in, and merging into existing content risks overwriting it."
        )

    if current.total_bytes:
        free = shutil.disk_usage(destination.parent if not destination.exists() else destination).free
        # A little headroom: a move across drives is a copy-then-delete,
        # so the destination briefly needs the full amount.
        if free < current.total_bytes * 1.05:
            raise StorageError(
                f"Not enough space: {_human(current.total_bytes)} to move, "
                f"{_human(free)} free at the destination."
            )

    destination.mkdir(parents=True, exist_ok=True)
    children = list(source.iterdir()) if source.is_dir() else []
    total = len(children) + 1

    for index, child in enumerate(children):
        if on_progress:
            on_progress(MoveProgress(index + 1, total, f"Moving {child.name}"))
        try:
            move_tree(child, destination / child.name)
        except OSError as exc:
            raise StorageError(
                f"Failed while moving {child.name}: {exc}. Some items may already have moved; "
                f"they are in {destination}, and the app is still pointed at {source}."
            ) from exc

    # Last, and only now: everything above succeeded, so the pointer can
    # safely name the new location.
    if on_progress:
        on_progress(MoveProgress(total, total, "Recording the new location"))
    app_paths.set_data_root(destination)

    _repoint_pth_files(destination, source)
    if settings is not None:
        _repoint_settings(settings, source, destination)

    # An empty source directory is tidied away; a non-empty one is left
    # alone, because something was in there that this did not put there.
    try:
        if source.is_dir() and not any(source.iterdir()):
            source.rmdir()
    except OSError:
        pass
    return destination


def _repoint_pth_files(root: Path, old_root: Path) -> None:
    """Rewrite .pth files inside moved environments that named the old
    location.

    A .pth file in site-packages puts extra directories on the import
    path, and an absolute one survives a move looking perfectly healthy
    while pointing at nothing. Hit for real: pkasolver's clone was added
    this way, and after moving, the interpreter still started and every
    prediction failed with "ModuleNotFoundError: No module named
    'pkasolver'" -- naming neither the .pth file nor the move.

    New installs write a path derived from `sys.prefix` instead and are
    immune (see `pkasolver_setup.RELOCATABLE_PTH`); this repairs the ones
    already on disk.
    """
    old_text = str(old_root)
    for pth in root.rglob("*.pth"):
        try:
            content = pth.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if old_text not in content:
            continue
        try:
            pth.write_text(content.replace(old_text, str(root)), encoding="utf-8")
            logger.info("Re-pointed %s after data move", pth)
        except OSError:
            logger.warning("Could not re-point %s; it still names the old location", pth)


def _repoint_settings(settings, source: Path, destination: Path) -> None:
    """Rewrite stored absolute paths that pointed into the old root."""
    for key in _PATH_SETTINGS:
        current = settings.get(key, "")
        if not current:
            continue
        try:
            relative = Path(current).resolve().relative_to(source.resolve())
        except (ValueError, OSError):
            continue  # points somewhere else entirely; leave it alone
        settings.set(key, str(destination / relative))
        logger.info("Re-pointed %s after data move", key)


def describe_status() -> str:
    """The location only -- deliberately no size.

    Totalling the data directory means walking every file in it, which
    for two sidecar environments takes seconds. A status line is drawn on
    dialog construction and must be instant; the size arrives separately.
    """
    configured = app_paths.configured_data_root()
    where = "custom location" if configured is not None else "system default"
    return f"{app_paths.data_root()}  ({where})"
