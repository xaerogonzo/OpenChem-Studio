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
| [SOURCES.md](SOURCES.md) | Every paper, dataset, legal text and bundled library this project rests on, with what uses it and how far it has been checked |

The rest of this directory is **assessments, audits and operational notes**.
They ship with the application because `build.ps1` copies the whole directory,
so they are listed here rather than left for somebody to find:

| | |
|---|---|
| [LIVE_VERIFICATION.md](LIVE_VERIFICATION.md) | How a running application is verified here, and which technique owns which failure — written to be portable to a project that adopts none of this code |
| [DREIDING_ASSESSMENT.md](DREIDING_ASSESSMENT.md) | The DREIDING force field: what the paper specifies, what was implemented, and the eight rotational barriers it reproduces |
| [SOLVENT_SOLUBILITY_ASSESSMENT.md](SOLVENT_SOLUBILITY_ASSESSMENT.md) | Solubility outside water. Twice a record of why the feature could not be built, and both verdicts kept beside the shipped one because the way they were wrong is the durable part |
| [DOCKING_RANKING_BENCHMARK.md](DOCKING_RANKING_BENCHMARK.md) | **A dated record of one measurement, not a live claim** — whether docking scores rank ligands within a single assay |
| [NAVIGATION_AUDIT.md](NAVIGATION_AUDIT.md) | **Dated 2026-08-10.** Every door into the application, written after two reported regressions turned out to be navigation problems wearing a bug's clothes |
| [SELF_HOSTED_RUNNER.md](SELF_HOSTED_RUNNER.md) | The benchmarks that cannot run on a hosted runner, what the self-hosted one needs, and the security position stated plainly |

**Two of those are dated records and say so in their own first lines.** A
measurement is not a claim about today, and re-reading one as though it were is
how this project's own documentation has gone stale before.

`SOURCES.md` is **generated** from [`sources.toml`](sources.toml) by
[`../tools/build_sources_doc.py`](../tools/build_sources_doc.py). Edit the
TOML and re-run the tool; `tests/test_sources_are_current.py` fails if the
two drift apart, in either direction.

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
