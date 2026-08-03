# OpenChem Studio

An open-source, plugin-based chemistry workstation — a modern, extensible
replacement for proprietary molecular editors like MarvinSketch. Built on
PySide6, RDKit, and Open Babel, with a layered architecture designed to
support future plugins (descriptor providers, importers/exporters, panels)
without restructuring the core.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the internal design,
[ROADMAP.md](ROADMAP.md) for the phased development plan, and
[PLUGIN_SDK.md](PLUGIN_SDK.md) for writing your own plugins.

## Naming molecules

Structure-to-name works offline and without a model. Known compounds resolve
against PubChem; anything else — including structures nothing has ever
registered — is named by a vendored deterministic IUPAC engine, and every
generated name is verified by parsing it back with OPSIN before it is shown.
Names carry their source and whether they are `exact`, `derived` or `parsed`;
they are never merged into a single unattributed answer.

Accuracy is measured, not asserted: `benchmarks/naming/` scores 181 molecules
by structural round-trip rather than string equality. Current: **180/181**,
stereochemistry 11/11. Run it before believing any claim that a different
engine is better.

## Development setup

```bash
uv sync --all-extras
uv run python -m openchem.main
```

Run the test suite:

```bash
uv run --no-sync python -u -m pytest -q > /tmp/suite.log 2>&1; tail -5 /tmp/suite.log
```

Invoke pytest as a module and redirect to a file. `uv run pytest -q ... | tail`
has hung twice for ~40 minutes at almost no CPU; see [CLAUDE.md](CLAUDE.md).
The vendored nomenclature engine's own ~3,200 tests are excluded from that run
— `uv run --no-sync python -m pytest tests/vendor -q`, with Java on PATH.

## Building a standalone application

Produces `dist\OpenChemStudio\`, which runs on a Windows machine with no
Python and no development environment:

```powershell
uv sync --extra ai --extra network --extra openbabel --group build
.\build.ps1
```

It is ~650 MB, almost all of it PySide6 — QtWebEngine alone is a full
Chromium, and the app hosts three web views (Ketcher, Mol*, 3Dmol). Ship the
whole directory; the `.exe` alone does nothing.

pkasolver, STOUT, the Temurin JRE, ORCA and Vina are **not** bundled. They
stay user-installed into the configurable data directory via Tools > External
Tools, exactly as in a source checkout. See
[ARCHITECTURE.md](ARCHITECTURE.md) for what the build has to get right and
why each part of it is there.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE). This license is required because
the project optionally links against Open Babel's Python bindings (GPL).
RDKit (BSD) and PySide6 (LGPL) are both GPL-compatible.
