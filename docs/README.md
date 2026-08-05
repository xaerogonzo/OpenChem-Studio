# OpenChem Studio documentation

| | |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | Install and run — from the release zip or from source, plus the optional external tools |
| [USER_GUIDE.md](USER_GUIDE.md) | Working guide to the panels, calculators, docking, spectroscopy and naming |
| [VALIDATION.md](VALIDATION.md) | Benchmark results, with the method and sample size behind each number |
| [SCIENTIFIC_LIMITATIONS.md](SCIENTIFIC_LIMITATIONS.md) | What each prediction can and cannot tell you |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Internal design, layering, and the decisions worth remembering |
| [ROADMAP.md](ROADMAP.md) | What is built, what is left, and why each remaining item is blocked |
| [PLUGIN_SDK.md](PLUGIN_SDK.md) | Writing a plugin |

The root [`README.md`](../README.md) is the overview; everything above goes
deeper.

[`../CHANGELOG.md`](../CHANGELOG.md), [`../CONTRIBUTING.md`](../CONTRIBUTING.md),
[`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) and
[`../CITATION.cff`](../CITATION.cff) stay in the repository root, where GitHub
and packaging tools expect to find them.

`build.ps1` copies this whole directory, plus the root `README.md` and
`LICENSE`, into the distributable on every build — so a shipped zip carries
its own documentation rather than pointing at a repository the user may not
have.
