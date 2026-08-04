"""Where this application keeps its bulk data, and how to move it.

By default that is the per-user data directory the operating system
nominates -- on Windows, `%LOCALAPPDATA%\\OpenChemStudio`. That default is
correct and it is also, for this application, frequently the wrong place:
the sidecar environments are large (a pkasolver install is ~2.3 GB and a
ADMET one ~1 GB), AppData usually lives on the system SSD, and none of
it is data the OS needs to manage. Someone with a second drive should be
able to say so.

So the root is CONFIGURABLE, and this module is the single place that
answers "where does it go".

WHY IT LIVES AT THE PACKAGE ROOT rather than in `services/` or `app/`.
Its callers span every layer -- `chem/nmr_database.py` wants the shift
index, `services/*_setup.py` want the sidecar roots, `plugins/manager.py`
wants the plugin directory. A module in `services/` could not be imported
by `chem/` without inverting the dependency direction, and one in `app/`
could not be imported by either. This has no openchem imports at all, so
anything may use it.

WHY A POINTER FILE rather than the Settings store. Settings is itself
data, and asking the data directory where the data directory is does not
terminate. A few bytes naming the real location stay in the OS config
directory -- which is small, and is what a config directory is for --
while everything of any size goes wherever the pointer says.

`OPENCHEM_DATA_ROOT` overrides both, for a portable install or a test.
"""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs

APP_NAME = "OpenChemStudio"

#: Overrides everything else. Intended for portable installs and tests,
#: which must never touch a developer's real data directory.
DATA_ROOT_ENV_VAR = "OPENCHEM_DATA_ROOT"

_POINTER_FILENAME = "data_root.txt"


def default_data_root() -> Path:
    """The OS-nominated location, used when nothing else is configured."""
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def pointer_file() -> Path:
    """The small file naming the real data root.

    Deliberately in the CONFIG directory, not the data directory: it has
    to be findable before the data root is known.
    """
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)) / _POINTER_FILENAME


def configured_data_root() -> Path | None:
    """The user's choice, or None if they have not made one."""
    override = os.environ.get(DATA_ROOT_ENV_VAR)
    if override and override.strip():
        return Path(override.strip())
    pointer = pointer_file()
    try:
        recorded = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(recorded) if recorded else None


def data_root() -> Path:
    """Where bulk data goes. Never creates it -- callers that write do."""
    return configured_data_root() or default_data_root()


def set_data_root(path: Path | None) -> None:
    """Record a new location, or `None` to go back to the default.

    Writing the pointer does NOT move anything; see
    `services/storage_service.py`, which moves and then records, in that
    order, so an interrupted move never leaves the pointer aimed at a
    directory that has nothing in it.
    """
    pointer = pointer_file()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    if path is None:
        pointer.unlink(missing_ok=True)
        return
    pointer.write_text(str(Path(path).resolve()), encoding="utf-8")


def cache_root() -> Path:
    """Scratch space -- ORCA job directories and similar.

    Follows the data root when one is configured, because a user who
    moved their data off the system drive meant the scratch too: an ORCA
    optimisation writes gigabytes of temporary files.
    """
    configured = configured_data_root()
    if configured is not None:
        return configured / "cache"
    return Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False))


#: Used when the cache root contains a space. Deliberately at the drive
#: root rather than tucked under the data root -- anything under a parent
#: whose name has a space inherits the problem.
_SPACE_FREE_CACHE_DIRNAME = "OpenChemStudio-scratch"


def space_free_cache_root() -> Path:
    """`cache_root()`, or somewhere without spaces if that has one.

    ORCA CANNOT READ AN INPUT PATH CONTAINING A SPACE. It does not fail
    cleanly either: it starts, prints its banner, and then reports

        Error: Cannot open input file D:\\Random

    having truncated `D:\\Random Programs\\...` at the space. Confirmed
    against a real ORCA 6.1.1 by running the same job from a spaced and an
    unspaced directory -- the second returned an energy, the first did not.

    `quantum_chemistry_service` already knew this and avoided deriving the
    scratch directory from the source tree, which lives under
    "OpenChem Studio". What it could not foresee is that `cache_root()`
    follows the CONFIGURABLE data root, so a user who points their data at
    `D:\\Random Programs\\...` silently reintroduces exactly the thing the
    original comment was guarding against. This makes the requirement hold
    for real instead of by assumption.

    Stays on the SAME DRIVE as the configured cache, because the reason
    that root is configurable is that a geometry optimisation writes
    gigabytes and someone moved it off the system disk on purpose. Falling
    back to a temp directory would quietly undo that.

    Note the 8.3 short-name trick does NOT work as a substitute: on the
    machine this was found on, `GetShortPathName` returned the spaced path
    unchanged because 8.3 generation is disabled on that volume. It looks
    like a fix and does nothing.
    """
    cache = cache_root()
    if " " not in str(cache):
        return cache
    anchor = Path(cache.anchor)
    candidate = anchor / _SPACE_FREE_CACHE_DIRNAME
    # A UNC share can itself contain a space (`\\\\host\\My Share\\`), and
    # then there is nowhere space-free on that volume to retreat to. Return
    # the spaced path rather than a wrong one: the caller reports ORCA's own
    # failure, which is at least truthful, instead of writing somewhere the
    # user never chose.
    if " " in str(candidate):
        return cache
    return candidate


def subdirectory(name: str) -> Path:
    """A named directory under the data root, e.g. `subdirectory("jre")`."""
    return data_root() / name
