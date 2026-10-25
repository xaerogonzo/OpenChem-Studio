# OpenChem Studio documentation

*Two terms used in the design and validation documents.* **The reference editor** is a
commercial structure editor whose public documentation and published output were read to
decide which quantities, options and worked examples to compare against. **The vendor** is
its maker. Neither is named in this repository on purpose; where a number was checked
against one of them, the document says what was checked and where it was read.

| | |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | Install and run — from the release zip or from source, plus the optional external tools |
| [USER_GUIDE.md](USER_GUIDE.md) | Working guide to the panels, calculators, docking, spectroscopy and naming |
| [VALIDATION.md](VALIDATION.md) | Benchmark results, with the method and sample size behind each number |
| [SCIENTIFIC_LIMITATIONS.md](SCIENTIFIC_LIMITATIONS.md) | What each prediction can and cannot tell you |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Internal design, layering, and the decisions worth remembering |
| [ROADMAP.md](ROADMAP.md) | What is built, what is left, and why each remaining item is blocked |
| [PLUGIN_SDK.md](PLUGIN_SDK.md) | Writing a plugin |
| [WHATS_NEW.md](WHATS_NEW.md) | A dated tour of the assistant's calculator bridge, recipes and derived scores: what each is for, where it is in the application, and what it does not do |
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

**Design records, references and maintainers' notes.** These were in the directory and not in this index:

| | |
|---|---|
| [DERIVED_SCORES_DESIGN.md](DERIVED_SCORES_DESIGN.md) | Design record for derived scores, slice by slice: why a score is a projection and not a result, the approved outputs, what was measured, and the geometry decisions |
| [RECIPES_DESIGN.md](RECIPES_DESIGN.md) | Design record for recipes (typed dependencies between calculators) and the Lewis pairing, with the preregistered gate |
| [AI_CALCULATION_BRIDGE.md](AI_CALCULATION_BRIDGE.md) | Design record for the assistant's calculator bridge: the execution policy, the handle, the frozen turn and the approval flow |
| [TAUTOMER_NMR_DESIGN.md](TAUTOMER_NMR_DESIGN.md) | Design for tautomer peaks on the NMR spectrum |
| [CALCULATOR_REFERENCE.md](CALCULATOR_REFERENCE.md) | The generated reference for every calculator: options, limits and the evidence behind each (built from the registry; do not edit) |
| [CALCULATOR_MATURITY.md](CALCULATOR_MATURITY.md) | Maintainer's document: calculator stages, default visibility, and how a calculator is classified or promoted |
| [CALCULATOR_GAP_REPORT.md](CALCULATOR_GAP_REPORT.md) | Which calculators a user of a reference-editor-like workstation might look for that OpenChem does not have, and an order to build them in |
| [GEOMETRY_DEFINITIONS_CHECKLIST.md](GEOMETRY_DEFINITIONS_CHECKLIST.md) | The reference editor's Geometrical Descriptors, definition by definition, written before the geometry calculators were merged |
| [PANEL_FEATURE_INVENTORY.md](PANEL_FEATURE_INVENTORY.md) | The inventory behind "no feature may be lost" for the Batch, Docking, Quantum Chemistry and 3D Alignment panels |
| [LESSONS.md](LESSONS.md) | The lessons moved out of `CLAUDE.md` so they are not loaded on every message |
| [LITERATURE_LOG.md](LITERATURE_LOG.md) | Every paper opened for a question and what came of it, so a later search is not repeated |
| [KETCHER_SPIKE.md](KETCHER_SPIKE.md) | Research note (2026-09-24): what was measured about driving the embedded Ketcher page |
| [PERFORMANCE_CENSUS.md](PERFORMANCE_CENSUS.md) | **Dated 2026-10-07**: a survey of the running application's performance and memory (nothing was fixed) |
| [VDW_RADII_ASSESSMENT.md](VDW_RADII_ASSESSMENT.md) | Van der Waals radii: what the application uses, where it comes from, and what the choice changes (investigated 2026-10-11) |
| [BRANCH_CLEANUP.md](BRANCH_CLEANUP.md) | **Dated 2026-09-12**: the record of every feature branch deleted that day |

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
