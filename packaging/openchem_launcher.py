"""Frozen-build entry point.

PyInstaller freezes a *script*, not a console-script entry point, so
`[project.scripts] openchem = "openchem.main:main"` cannot be handed to it
directly. This is that entry point expressed as a script. Keep the delegation
to `openchem.main` a one-liner so there is never a second definition of "how
the app starts" to drift out of sync -- everything else in this file exists
to repair the frozen *environment* before the application sees it.
"""

from __future__ import annotations

import io
import os
import sys


def _ensure_std_streams() -> None:
    """Give `sys.stdout`/`sys.stderr` real file objects.

    In a windowed PyInstaller build (`console=False`) there is no console, and
    PyInstaller sets both of these to `None`. Any library that so much as
    reads `sys.stdout.encoding` then dies on `AttributeError: 'NoneType'`.

    FOUND THE HARD WAY, and it is worth recording how well it hides. Naming a
    molecule failed in the frozen build with

        TypeError: can only concatenate str (not "AttributeError") to str

    which names neither stdout nor the real fault. py2opsin decodes OPSIN's
    output with `sys.stdout.encoding` (py2opsin.py:156), and its own
    `except Exception as e: warnings.warn("..." + e)` handler is itself buggy
    -- concatenating an exception to a str -- so the AttributeError never
    surfaces and a TypeError from the error handler is all anyone sees.

    Fixed here rather than in `openchem/` because nothing is wrong with the
    application: it is the frozen environment that is missing streams every
    normal Python process has. Fixing it at the entry point also covers the
    whole class of bug, not just this one library.
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            # Buffered binary sink wrapped in text, so the object has the full
            # TextIOWrapper API -- `.encoding`, `.buffer`, `.fileno()` -- that
            # a real stream has. A bare object with a `write` method is not
            # enough; the failure above was a read of `.encoding`, not a write.
            stream = io.TextIOWrapper(
                open(os.devnull, "wb"), encoding="utf-8", errors="replace"
            )
            setattr(sys, name, stream)


def main() -> int:
    _ensure_std_streams()
    from openchem.main import main as app_main

    return app_main()


if __name__ == "__main__":
    sys.exit(main())
