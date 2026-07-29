# OpenChem Studio

An open-source, plugin-based chemistry workstation — a modern, extensible
replacement for proprietary molecular editors like MarvinSketch. Built on
PySide6, RDKit, and Open Babel, with a layered architecture designed to
support future plugins (descriptor providers, importers/exporters, panels)
without restructuring the core.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the internal design and
[ROADMAP.md](ROADMAP.md) for the phased development plan.

## Development setup

```bash
uv sync --all-extras
uv run python -m openchem.main
```

Run the test suite:

```bash
uv run pytest
```

## License

GPL-3.0-or-later — see [LICENSE](LICENSE). This license is required because
the project optionally links against Open Babel's Python bindings (GPL).
RDKit (BSD) and PySide6 (LGPL) are both GPL-compatible.
