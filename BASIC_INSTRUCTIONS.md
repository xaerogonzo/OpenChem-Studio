# OpenChem Studio — Basic Instructions

> **This is a tooling file, not documentation.** It is TokenSave Manager's
> project baseline, and the `@` line below is a template include pointing at
> an absolute path on the maintainer's machine — which is why it stays in
> the repository root while the real documentation lives in [`docs/`](docs/).
> If you are looking for user or developer documentation, start at
> [`README.md`](README.md) or [`docs/`](docs/).

@project-baseline.md

---

## Project Overview

**Name:** OpenChem Studio
**Stack:** Python 3.11+, PySide6 (+ PySide6-Addons/QWebEngine), RDKit, Open Babel (optional extra), uv for dependency management, pytest for testing
**Entry point:** `uv run python -m openchem.main` (also installed as the `openchem` console script)
**Purpose:** Open-source, plugin-based chemistry workstation — a modern, extensible replacement for proprietary molecular editors like MarvinSketch.

---

## Project Structure

- `src/openchem/` — application source, `src`-layout package (see docs/ARCHITECTURE.md for the full layered package map: `domain/`, `chem/`, `services/`, `commands/`, `plugins/`, `app/`, `ui/`, `events/`, `resources/ketcher/`, `vendor/` — third-party code owned in-tree)
- `tests/` — pytest suite (chemistry engine, services, commands, layering rule). `tests/vendor/` holds the vendored nomenclature engine's own ~3,200 tests and is excluded from the default run
- `benchmarks/naming/` — the naming regression benchmark, 181 molecules scored by OPSIN round-trip; the arbiter for any change to naming
- `pyproject.toml` / `uv.lock` — uv-managed dependencies
- `build.ps1` / `build.bat` — **PyInstaller** packaging, driven by `packaging/openchem.spec`; freezes the app into a one-directory `dist/OpenChemStudio/`. PyInstaller over Nuitka deliberately — see docs/ARCHITECTURE.md's packaging section for why, and for the four bundled items that fail *silently* when missing
- `packaging/openchem.spec` — the real build definition, with a comment per bundled item
- `.tokensave/`, `.codegraph/` — code-graph indexes, already initialized against this repo

---

## Documentation Files

| File | Location | Purpose |
|---|---|---|
| README.md | `/README.md` | Project intro, dev setup |
| docs/ARCHITECTURE.md | `/docs/ARCHITECTURE.md` | Layered architecture, package map, design decisions, known TODOs |
| docs/ROADMAP.md | `/docs/ROADMAP.md` | Phased development plan, plus resolved investigations (naming) and documented extension points |
| CALCULATOR_MATURITY.md | `/docs/CALCULATOR_MATURITY.md` | Calculator stages and default visibility, what a declaration obliges, and how a calculator is classified or promoted |
| CLAUDE.md | `/CLAUDE.md` | How to run the tests here, and the traps that cost real time |
| VENDORING.md | `/src/openchem/vendor/VENDORING.md` | What is vendored, from where, at which commit, and what was changed |
| LICENSE | `/LICENSE` | GPL-3.0-or-later (required for optional Open Babel bindings use) |

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture. In short:

```
UI -> Commands (QUndoStack) -> Services (async, typed events) -> Domain models (UUID-identified) -> Chem engine (sole RDKit/Open Babel import site)
```

UI code must never import `rdkit` or `openbabel` directly — this is enforced
by `tests/test_layering.py`.

---

## Key Files

- `src/openchem/main.py` / `bootstrap.py` — composition root, DI wiring
- `src/openchem/chem/engine.py` — the only RDKit touchpoint for molecule conversion/canonicalization
- `src/openchem/services/descriptor_service.py` — async descriptor computation (Queued/Running/Completed/Failed)
- `src/openchem/ui/widgets/ketcher_editor_backend.py` — the embedded 2D editor, behind the `EditorBackend` interface
- `src/openchem/chem/naming_providers.py` — structure <-> name; the only entry point to the vendored nomenclature engine
- `src/openchem/net.py` — every outbound HTTP request, so each one identifies the app (a missing User-Agent is a 403 on some hosts)
- `src/openchem/chem/pka_worker.py` -- the persistent pkasolver sidecar: one owner thread over a request queue, `pka_runner.py --serve` as the child; the cache in `pka_providers._PAYLOADS` sits in front of it and `use_cache=False` bypasses it; `OPENCHEM_PKA_WORKER=0` turns it off (the suite does)
- `src/openchem/chem/periodic_charges.py` — EQeq charges for a crystal; the only calculation here about a periodic solid, reached through `crystal_report.py` rather than the calculator registry (a `CalculationRequest` cannot name a crystal)
- `src/openchem/domain/refusal_kinds.py` — why a calculator declined (limit / needs input / needs setup); a refusal with no kind is a fault
- `src/openchem/domain/calculator_support.py` — a calculator's stage (maturity of this implementation) and default visibility, with the reason; `LEGACY_UNCLASSIFIED` only shrinks (see `docs/CALCULATOR_MATURITY.md`)
- `src/openchem/domain/execution_policy.py` / `builtin_execution_policies.py` -- whether a model may start a calculator or a person approves a preview first; measured in `benchmarks/calculator_cost/`, attached to each definition by `bootstrap`; the design the assistant bridge follows is `docs/AI_CALCULATION_BRIDGE.md`
- `src/openchem/app/calculation_host.py` / `plugins/calculation_access.py` -- the window's side of the assistant's calculator bridge and the handle a plugin gets as `context.calculations` (no way to approve a run); pure parts in `domain/calculation_bridge.py` (cards, validation), `turn_snapshot.py` (what a turn may read) and `run_lifecycle.py` (the run ledger); driven in the real window by `benchmarks/visual/ai_bridge_run.json`
- `src/openchem/domain/result_envelope.py` -- what a stored result looks like to a model: every number with its method, settings, structure, units, status, freshness and caveats; `plugins/ai_assistant/bridge.py` / `calculation_tools.py` are the five tools built on it (`list_goals` reads `domain/calculator_goals.py` as knowledge; nothing calls `PropertyPanel.run_goal`, which skips the execution policy) (and the only place a tool is handed the calculation handle, never the approvals one); driven in the real window by `benchmarks/visual/ai_assistant_tools.json`
- `src/openchem/domain/calculator_search.py` -- the one rule for which calculators match a phrase (the launcher's Find box and the assistant)
- `src/openchem/domain/recipe.py` / `recipe_run.py` -- a recipe (an ordered plan whose steps read each other's typed outputs; closed value types, closed transform table, `validate_recipe`) and one evaluation of it (`RecipeRun`, its own store and `recipe_runs` project block, eight binding states, staleness derived at read by `assess`); the design is `docs/RECIPES_DESIGN.md`, `ResultStoreService.record_recipe_run` is the one write path. The first shipped recipe is the Lewis pairing: `domain/lewis_pairing.py` (the plan), `recipe_catalogue.py` (what ships), `lewis_binder.py` (stored runs -> evidence or a reasoned gap), `chem/lewis_pairing_eval.py` and `chem/recipe_host.py` (evaluation, and "does this run still describe the drawing"), `services/recipe_service.py` (the host side; evaluates without recording); the window is `ui/dialogs/lewis_pairing_dialog.py` (Tools menu; view model `domain/recipe_preview.py`; driven by `benchmarks/visual/lewis_pairing.json`); the real-ORCA gate on BH3/BF3 with CO was preregistered and PASSED at 0.01 eV on 2026-10-13, and is final (`benchmarks/lewis_gate/PREREGISTRATION.md`; arithmetic `app/lewis_gate.py`, scripts `benchmarks/visual/lewis_gate_*.json`); a kept answer is read in Results as a `RecipeAnswer` (`domain/recipe_answer.py`, built by `RecipeService.answers_for`, stale from `assess`, never stored as a result)
- `src/openchem/domain/score_formula.py` / `score_units.py` -- the formula language of a user-defined derived score: a hand-written parser (nothing here evaluates Python; `tests/test_score_formula_guard.py` reads the syntax trees), nine functions, strict opaque units with no conversions, and an evaluator that refuses rather than return a non-finite or invented number; slice 1 of `docs/DERIVED_SCORES_DESIGN.md`, reached by `tools/check_score_formula.py` until slice 3 wires it into the application; `domain/score_outputs.py` is slice 2, the table of approved outputs a formula may name (typed numbers of the drawing, each with the unit it must carry and an endpoint tag; two inputs of one endpoint are refused), swept by `tools/sweep_score_outputs.py` and held to the registry by `tests/test_score_outputs.py`
- `tools/perf_census.py` / `benchmarks/perf/scenarios.py` / `src/openchem/app/drive_probes.py` — the resource census: external sampler, scenario builders, in-app probes; findings in `docs/PERFORMANCE_CENSUS.md` (start with its "Unresolved" and "where they were wrong" sections before trusting a number)
- `src/openchem/cli/` — the headless command line (`openchem-cli`): any registered calculator on a SMILES, one JSON envelope on stdout, no Qt; `tests/test_cli.py` runs the real service task beside it and compares
- `tools/naming_variants.py` — a naming population from seed molecules (the operators are rounds 32-35's generator rules, ported), and the atom-order diagnostic: it names random spellings AS WRITTEN (not through `naming_census_scan.name_rows`, which canonicalises) and reports any structure with more than one name; `tools/naming_census_scan.py` now labels each wrong-molecule row with what the read-back changed (`delta`)
- `tools/naming_ion_populations.py` -- how naming rounds 46 to 52 found their defects once the census was saturated: change ONE site of every census molecule into an ion (`anion` deprotonates, `cation` protonates, `quaternary` N-methylates), name it, read it back through OPSIN, and class each (`ok`, `refused`, `no_anion_word`, `charge_changed`, `wrong` ...); `tests/test_naming_ion_populations.py` pins which ions it builds and how it judges a name
- `docs/explainers/` / `tools/calculator_explainers.py` -- hand-written prose on what each calculator DOES, merged into the generated `CALCULATOR_REFERENCE.md` by `tools/build_calculator_reference.py`; `tests/test_calculator_explainers.py` owns it (the `EXPLAINER_DEBT` ratchet only shrinks, citations are `[source:key]`, no URLs)
- `tools/survey_descriptor_inputs.py` / `DescriptorProvider.geometric_descriptor_ids` — which always-on results depend on coordinates and which only on how the hydrogens are written (three structures per molecule: the drawing and two embeddings). A conformer request computes ONLY the provider's geometric descriptors (the ten shape ones); every other descriptor, alert catalogue and per-atom dataset is computed on the drawing, in `DescriptorService`, in the Project table (`batch_service`), and in a saved file (`ResultStoreService.set_project` drops an earlier build's GEOMETRY copies); guarded by `tests/test_descriptor_input.py`, driven by `benchmarks/visual/descriptors_survive_a_conformer.json`. A DRAWING request on a molecule that holds a conformer carries the geometry run with it and the two split the provider's ids (the drawing run records the shape ids and does not show them: two writers of one reader id lost 37 runs in 40); a replay that did not bring them back is topped up by `request_missing_geometric_descriptors`; driven by `benchmarks/visual/descriptors_restored_with_a_conformer.json`
- `tools/calculator_census.py` — every calculator over a fixed panel through the app's own path; `tests/test_calculator_census.py` fails on a fault, an error logged, an unclassified refusal code, or a moved cell

---

## Project-Specific Rules

- New descriptor sources (including future plugins) implement `DescriptorProvider` from `openchem.plugins.interfaces` / `openchem.chem.descriptor_providers` — never bolt caching onto `MoleculeModel` directly.
- Never store a raw RDKit `Mol` in a `.ocsproj` project file — persist molblock + canonical SMILES/InChI/InChIKey + metadata, and reconstruct via `ChemistryEngine`.
- Structure-modifying user actions go through a `QUndoCommand` in `openchem.commands` so undo/redo stays correct — don't mutate `MoleculeModel`/`ProjectModel` directly from UI code.
