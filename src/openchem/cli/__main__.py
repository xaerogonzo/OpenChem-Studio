"""``python -m openchem.cli`` -- the same entry as the ``openchem-cli`` script."""

from __future__ import annotations

REACHED_BY = (
    "console_script: entered by the `openchem-cli` script in pyproject.toml "
    "([project.scripts] -> openchem.cli.commands:main) or `python -m openchem.cli`, "
    "never by an import from openchem.main"
)

from openchem.cli.commands import main

if __name__ == "__main__":
    raise SystemExit(main())
