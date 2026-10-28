# OpenChem Studio — Basic Instructions

> **This is a tooling file, not documentation.** The `@` line below includes
> `project-baseline.md`, TokenSave Manager's committed baseline copy, which is
> why this file stays in the repository root while the real documentation lives
> in [`docs/`](docs/). If you are looking for user or developer documentation,
> start at [`README.md`](README.md) or [`docs/`](docs/).

@project-baseline.md

---

## Project Overview

**Name:** OpenChem Studio
**Stack:** Python 3.11+, PySide6 (+ PySide6-Addons/QWebEngine), RDKit, Open Babel (optional extra), uv for dependency management, pytest for testing
**Entry point:** `uv run python -m openchem.main` (also installed as the `openchem` console script)
**Purpose:** Open-source, plugin-based chemistry workstation — a modern, extensible alternative to proprietary molecular editors.

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
| CODE_SIGNING_POLICY.md | `/docs/CODE_SIGNING_POLICY.md` | The code signing policy (for SignPath Foundation's terms), who approves a release, and the privacy statement listing every service the program contacts |
| RELEASING.md | `/docs/RELEASING.md` | How to cut a release with the GitHub Actions workflow, what to check by hand before publishing, and how to verify a download |
| RELEASE_CONTENTS.md | `/docs/RELEASE_CONTENTS.md` | What a release zip holds and what stays in the repository, checked by `tests/test_release_contents.py` |
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
- `src/openchem/domain/synthesis_route.py` -- the synthesis helper's route type (Stage 1 slice 1 of `docs/SYNTHESIS_HELPER_DESIGN.md`; no planner or UI yet): `Route` (steps in forward order, a tree with one root, checked at construction), `RouteStep`/`RouteMolecule` (a field the planner did not supply is `None`, shown as "not provided" by `shown`), `ValidationReport` (separate outcomes; conservation only where the mapping is complete), `RouteSet` with a closed `RouteStatus` and `SearchTermination` and `STANDARD_LIMITATIONS` that cannot be omitted, and `read_termination` (the planner has no stop-reason field, so it is read from limits and counters and is `unknown` otherwise); tested by `tests/test_synthesis_route.py` against the real planner fixtures in `benchmarks/synthesis/fixtures/`
- `src/openchem/chem/synthesis_gate.py` -- the regulatory gate on synthesis planning (Stage 1 slice 2 of `docs/SYNTHESIS_HELPER_DESIGN.md`; types in `domain/synthesis_gate.py`): `check_target` returns a `GateDecision` (`allowed`, `refused` on a `cwc-schedule-1` match, or `unscreened`, which stops planning exactly as a refusal does) from its OWN engine built from `load_all(include_user=False)`, failing closed on every way the ruleset or the structure can go wrong; `screen_nodes` flags the molecules of a planned route with the wider rulesets as alerts, never refusals; `permits_planning` is true only for `allowed`; tested by `tests/test_synthesis_gate.py`
- `src/openchem/chem/aizynth_planner.py` / `aizynth_runner.py` -- the AiZynthFinder runner and parser (Stage 1 slice 3 of `docs/SYNTHESIS_HELPER_DESIGN.md`): the planner is NEVER imported, it is the user's own Python environment run as a child process (`run_planner`: argument array, `-I`, one JSON request on stdin, one JSON document on stdout, bounded output and wall clock, a cancel or overrun kills the child, nothing retries); `aizynth_runner.py` is handed to that interpreter as a PATH, imports nothing from openchem and checks every named asset before the library loads; `BENCHMARK_FINDING` is the measured result (protocol 3's 13 of 51 with its interval and the patent figure beside it, each held to `benchmarks/synthesis/RESULT_3.md` and `RESULT_2.md` by a test) that every plan it makes carries in its limitations; `parse_document` turns the response into a `RouteSet`, keeping only routes with a reaction whose starting materials are all flagged in stock and saying how many it left out; every failure is a typed result, `failed` or `unavailable` naming the asset; tested by `tests/test_synthesis_planner.py` (four tests drive the real planner where it is installed); it asks for every solved route (`all_routes` on) and keeps the first `ROUTES_SHOWN` (10) in the order of `chem/route_ranking.py` (the PaRoutes route score, then the planner's own score, then its order: protocol 2's M2, held to `benchmarks/synthesis/route_rank.py` by `tests/test_synthesis_route_ranking.py`), saying how many it did not keep
- `src/openchem/chem/route_validation.py` -- the route validator (Stage 1 slice 6 of `docs/SYNTHESIS_HELPER_DESIGN.md`, moved from the spike): `validate_route(route)` returns the domain `ValidationReport` (molecules parse; each step's reaction parses AND its sides are the molecules the step connects; mapping complete/partial/absent; conservation only where the mapping is complete, else not assessable; stock; what the planner left out), nothing repaired or invented, never raises; `parse_document` attaches it to every route it keeps; `tests/test_synthesis_route_validation.py` runs it on the real fixtures and holds it equal to the spike's `benchmarks/synthesis/route_validator.py`, which the frozen quality benchmark still runs. The other half of slice 6 is `chem/synthesis_gate.annotate_route_set` (every distinct molecule of a plan screened through `screen_nodes` into `RouteSet.node_screenings`, applied by the planning service; an alert never removes a route, a screen that cannot run marks the molecules unscreened), tested by `tests/test_synthesis_annotations.py`
- `benchmarks/synthesis/PREREGISTRATION_3.md` / `RESULT_3.md` / `run_quality_3.py` / `judge_3.py` / `artifacts_protocol3/` -- protocol 3 of the planner quality benchmark (option 3c, run 2026-10-24, reading LOWER): 51 routes from journal papers after the model's training data (190 papers read; lead rule, 4-reaction cap, reader agents + a second reading + `validate_refs.py`), searched on three stocks with protocol 2's settings; M2 at 10 = 13 of 51 = 0.255, 8 of 36 against 14.0 expected from protocol 2's depth rates (p = 0.007); `judge_3.py` is the pure part (lenient match, same-materials count, reaction-level recall, Wilson interval, the reading), held by `tests/test_synthesis_protocol3.py`; the references carry no DOIs (the DOI guard sweeps `.json`), the stem-to-DOI tables are kept in the maintainer's library; `BENCHMARK_FINDING` quotes it first, with protocol 2's 41.7% beside it as the patent-target figure
- `benchmarks/synthesis/run_addendum_3.py` / `RESULT_3_ADDENDUM.md` / `artifacts_protocol3_addendum/` -- the post-freeze addendum to protocol 3 (2026-10-25): two papers that arrived after the freeze (Kral's article, Singh's SI), read with the same rules, one search each on the primary stock, 0 of 2 recovered, reported BESIDE the frozen result and never in it (a third, Ma's, was excluded: its lead needs about 8 reactions); `run_addendum_3.py` only calls `run_quality_3.py` and `judge_3.py`, the stock is the frozen primary plus these routes' leaves, and no reading is made; held apart from the frozen 51 by `tests/test_synthesis_protocol3_addendum.py`
- `src/openchem/services/synthesis_planning_service.py` -- the synthesis helper's one planning path (Stage 1 slice 4 of `docs/SYNTHESIS_HELPER_DESIGN.md`): `request_plan(molecule, requested_by=...)` runs the regulatory gate FIRST (a refusal or an `unscreened` starts no process and registers no job), captures the target and the `PlannerSetup` before the worker starts, allows one slot per molecule and one search at a time (a pool of its own), and `cancel`/`shutdown` (wired to the application quitting) kill the planner child; `set_project(project, plans)` and `plan_store(project)` are the project file's two ends (a plan read from a FILE is input from outside: the gate is asked again, each route is validated again, the sentences are this build's; see `domain/synthesis_route_codec.py` and `domain/synthesis_plan_store.py`, the `synthesis_plans` block, only routes found or none found); `result_for(molecule)` returns the stored `RouteSet` bound to the structure it was made for (`BoundResult.is_current`, never for another molecule); events `SynthesisJobStateChanged` / `SynthesisRouteReady`; the setting provider is a stub that answers "not set up" until the External Tools slice; tested by `tests/test_synthesis_planning_service.py`
- `src/openchem/services/synthesis_planner_setup.py` -- the planner's setting and the External Tools tab's checks (Stage 1 slice 7 of `docs/SYNTHESIS_HELPER_DESIGN.md`): `describe_status` reads two paths and starts nothing; `verify` (the Test button) names the first thing wrong in order and then runs a real trivial search; `SetupProvider(settings)` is the planning service's `setup_provider`, reading the configuration once per file as it stands through the planner's OWN Python (`chem.aizynth_planner.inspect_environment`, the runner's `aizynth-inspect-request-1`), choosing `uspto`, `zinc` and no filter unless `aizynthfinder/expansion|stock|filter` say otherwise; the tab is `external_tool_catalog.aizynthfinder()` (a `ManagedExecutable` with an `ExtraPath` for the configuration file); tested by `tests/test_synthesis_planner_setup.py`
- `plugins/synthesis_planner/` / `src/openchem/plugins/synthesis_access.py` / `src/openchem/app/synthesis_host.py` / `src/openchem/chem/reaction_depiction.py` -- the Synthesis panel (Stage 1 slice 8 of `docs/SYNTHESIS_HELPER_DESIGN.md`): a bundled plugin whose `panel.py` shows the selected molecule, three lists filled from the planner's configuration on a worker (`SetupProvider.options()`), Plan and Cancel, the routes, a route's steps, each step drawn by `chem/reaction_depiction.py` (from the plain molecules, never the mapped reaction) and the standing limitations, with `route_text.py` holding the words as pure functions; it reaches the planner only through `context.synthesis` (reads, drawing) and `context.synthesis_requests` (start, cancel, choose; for a panel's buttons, never a tool) over one `SynthesisHost`, and every start is `SynthesisPlanningService.request_plan`, where the gate runs first; tested by `tests/test_synthesis_panel.py`, `test_synthesis_host.py`, `test_synthesis_options.py`, `test_synthesis_route_text.py` and `test_reaction_depiction.py`, driven by `benchmarks/visual/synthesis_panel.json`
- `plugins/ai_assistant/synthesis_tools.py` -- the assistant's two synthesis tools (Stage 1 slice 9 of `docs/SYNTHESIS_HELPER_DESIGN.md`): `plan_synthesis` (no arguments; starts NOTHING, leaves a card whose Approve is the only path to `request_plan`, where the gate speaks first) and `read_synthesis_plan` (the plan as it was when Send was pressed; summary or one route in full; a gate refusal, a failure's message and an alert's listing name are never sent, only the status, the rule id and the standing limitations); `SynthesisBridge` is built from `context.synthesis` (reads) and never `context.synthesis_requests`; the panel's `_SynthesisCard`, `_on_synthesis_approve` and `_on_synthesis_ready` hold the decision and tell the model the outcome with the next message; tested by `tests/test_ai_assistant_synthesis.py`, driven by `benchmarks/visual/synthesis_assistant.json`
- `src/openchem/chem/psi4_engine.py` -- Psi4 as a second `QuantumEngineProvider` (single points and optimizations, locate-only External Tools tab `psi4/executable_path`, the Engine box on the Quantum Chemistry panel when more than one engine is set up): the functional is mapped by NAME through `PSI4_METHODS` because Psi4's `b3lyp` is not ORCA's `B3LYP` (37 mEh; `b3lyp5` is), a failed run is the text "Psi4 encountered an error" and not the exit code, and a Psi4 geometry is `psi4_opt` in `QUANTUM_OPTIMIZED_METHODS`; design, the Windows spike and its size in `docs/PSI4_ENGINE_DESIGN.md`
- `src/openchem/chem/xtb_engine.py` -- xtb (GFN2/GFN1-xTB) as a third `QuantumEngineProvider` (`sp`, `opt`, `opt_freq`; registered with `QuantumChemistryService` and used only when `xtb/executable_path` is set or xtb is on PATH, a locate-only External Tools tab `xtb()` whose Test runs H2 through the provider's own input and command (`tool_download_service.verify_xtb`), and the panel's method box swaps to the engine's `method_basis_presets` (`GFN2-xTB`, `GFN1-xTB`; xtb has no basis) when it is chosen; driven in the real window on real xtb by `benchmarks/visual/xtb_engine.json` (PASS 2026-10-27; its path is `D:/_scratch/xtb-6.7.1/bin/xtb.exe`); no accuracy comparison with ORCA/Psi4 yet; the spike and its findings are in `docs/EXTERNAL_TOOL_CANDIDATES.md`): `command_args` is not handed the charge, spin or job, so `build_input` writes them in a header comment on the first line and `command_args` reads the file back; the geometry is a Turbomole `$coord` block in Bohr because the service names the file `job.inp` and xtb picks its reader by NAME (a `.inp` file is refused) but sniffs a `$coord` block by content, and xtb then prints the final structure in Bohr too; xtb ran an impossible electron count (a methyl radical at `--uhf 0`) with exit 0, so `check_electrons` refuses it first; `normal termination of xtb` is on STDERR, which the service does not read, so a run is judged from stdout (`[ERROR]`, `finished run on`); a linear molecule's frequency block has no `projected` in its heading; IR intensities exist only in the `vibspectrum` file, so modes carry none; geometry label `xtb_opt` in `QUANTUM_OPTIMIZED_METHODS`; tested by `tests/test_xtb_engine.py` against real outputs in `tests/fixtures/xtb/` (regenerated through the provider's own input and command, and a live test runs when `OPENCHEM_XTB_EXE` names an xtb)
- `benchmarks/xtb_comparison/PREREGISTRATION.md` / `run_comparison.py` / `judge.py` -- xtb against ORCA and Psi4, FROZEN 2026-10-27 and RUN the same day (C1 PARTIAL, C2 TIER C, C3 PARTIAL; section 14 has the outcome and the artifacts are committed): three separate claims, each with its own verdict and no overall one (C1 xtb structures against ORCA B3LYP/def2-SVP, C2 isomer and conformer energy differences against B3LYP-D3BJ/def2-TZVP single points, tiers A/B/C, C3 whether starting an ORCA optimization from an xtb structure saves cycles and reaches the same minimum), 25 molecules in sets S, M and F, floors measured first, thresholds fixed in `judge.py` and held by `tests/test_xtb_comparison_judge.py` (mutation-checked) and `tests/test_xtb_comparison_runner.py`; stages `floor`, `geometry`, `conformers`, `reference`, `preopt`, `gfn1`, then `report` (`python benchmarks/xtb_comparison/run_comparison.py list` runs nothing); the set-F conformer rule was changed at the freeze after counting what it kept, and section 13 says so; the outcome moved the xtb tab's note to the measured wording
- `src/openchem/help.py` / `tools/build_help_bundle.py` -- the in-app help's content provider: a checkout reads `docs/*.md`, a frozen build reads ONLY `openchem/_help_bundle.py` (generated by `build.ps1`, gitignored, in the exe's archive; digest over canonical bytes, `content_source()` says which), and `reading_copy` is the read-only temp copy the Open file button opens; tested by `tests/test_help_bundle.py`
- `src/openchem/install_check.py` / `app/install_monitor.py` / `tools/verify_install_tree.py` -- the install self-check: `build_manifest` (called by `packaging/openchem.spec` on its own `datas`, written to the gitignored `_integrity.py`) records sha256 and size of every first-party data file; `check_installed` compares them against `sys._MEIPASS` at startup on one worker thread, closed verdicts `not_applicable | checking | verified | modified | check_failed` (an unreadable file or malformed manifest is never `verified`; extra files are ignored); it reports and never repairs, and detects accidental change only; `current()` feeds About; tested by `tests/test_install_check.py`
- `tools/frozen_smoke.py` / `tools/make_release_zip.py` / `src/openchem/app/drive_release.py` -- the release pipeline's gates: `frozen_smoke.run_smoke` launches the BUILT exe on `benchmarks/visual/frozen_smoke.json` in a fresh folder and `judge` passes only an exit 0 with a fresh report, verdict PASS, every `REQUIRED_ASSERTIONS` step present and ok, `dropped == 0` and the whole script run; the `help_report` / `install_report` driver steps (`drive_release.py`, pure) read the RUNNING modules (help source `bundle`, install check `verified`) and fail closed on an unknown key; `make_release_zip.build_release` writes a `.partial` zip under a versioned top folder, validates the inventory, smoke-tests the EXTRACTED copy, then promotes zip and `SHA256SUMS.txt` together; `build.ps1` refuses a dirty tree (`-AllowDirty`) and `-Release` refuses one outright; tested by `tests/test_frozen_smoke.py` and `tests/test_release_zip.py`
- `packaging/openchem.iss` / `tools/make_installer.py` / `tools/drive_installer.py` -- the Windows installer: Inno Setup script (per-user or all-users chosen at install, upgrade deletes the old `_internal` but never `plugins\`, uninstall form with two UNTICKED removal boxes and `/REMOVESETTINGS=1` `/REMOVEDATA=1` for silent use, removal confined to the application's own `OpenChemStudio*` folder, a moved data folder only reported; unsigned); `make_installer.compile_installer` compiles into scratch and promotes only a finished file, then adds its line to `SHA256SUMS.txt`; `--test-build` (`/DTestBuild`) is the sandbox variant (own AppId, `OpenChemStudio-TEST` data folder and registry key) and never a release; `drive_installer.py` drives the REAL compiled installer silently (install, smoke test of the installed app, upgrade, uninstall, and with `--removal` each removal option) and refuses to run when the installer's AppId is already registered; the uninstaller's first process exits at once, so results are read after its `/LOG` closes; tested by `tests/test_installer_tooling.py`
- `.github/workflows/release.yml` / `tools/release_info.py` -- the release workflow: a `v<version>` tag builds with `build.ps1 -Release -Installer` on a clean Windows runner, attests provenance, and creates a DRAFT release (never publishes); pull requests touching the release path and `workflow_dispatch` run it as a dry run; `release_info.py` (stdlib only) checks the tag against `pyproject.toml` and extracts the version's CHANGELOG section as the notes; actions pinned to commit SHAs, `permissions: {}` by default with `contents: write` only on the draft job, scripts take values through `env:`; how to cut one is `docs/RELEASING.md`; tested by `tests/test_release_workflow.py`
- `packaging/win_version_info.py` / `docs/CODE_SIGNING_POLICY.md` -- what a SIGNED file must say and promise: `win_version_info.render(version)` writes the exe's Windows version resource (product name, company, file and product version from `pyproject.toml`) as a PyInstaller version file the spec passes to `EXE(version=...)` (loaded by path: `packaging/` is not a package), `build.ps1` reads the built exe back, the installer script states the same product fields; the policy page holds the signing policy (honest that nothing is signed yet), the roles and the privacy statement with a table of every host the program contacts, and `tests/test_code_signing_policy.py` fails when code names a host the page does not
- `src/openchem/ui/widgets/dock_title_bar.py` / `dock_layout_menu.py` / `dock_panel_actions.py` / `src/openchem/app/dock_expansion.py` -- the title bar on EVERY dock (stable objectNames, deliberate title elision) with a layout menu (Move to a side, Expand panel / Restore size, Show alongside, Lock open / Unlock, Float panel / Dock panel back, Return to default side) built from a plain `DockMenuState`, refilled on each opening, handled by ONE bound `MainWindow._on_dock_menu_triggered` reading each action's `(kind, dock, argument)`, and a panel's own buttons as data (`PanelButton` / `PanelMenuButton`, registered by `MainWindow._register_panel_buttons`: Results' Report menu, Structure Check's Check again, Jobs' Cancel all, which reports a REQUEST); Expand is a resize with one snapshot of every docked dock, re-applied after a window resize and resolved before any other layout change and before close (the measurements, including why one dock's restore strands the explorer, are `docs/DOCK_LAYOUT_DESIGN.md`); the layout button is TEXT because the standard icon is the window's own (the Qt logo on Windows); tested by `tests/test_dock_layout_menu.py`, `test_dock_panel_buttons.py` and `test_dock_title_bar.py`, driven by `benchmarks/visual/dock_layout_menu.json`
- `src/openchem/app/appearance_service.py` / `ui/theme.py` / `ui/widgets/web_appearance.py` / `domain/appearance.py` -- Light / Dark / Follow the system (`APPEARANCE`, stored 0/1/2; Settings > Appearance and View > Theme are one setting): the service applies it (`unsetColorScheme()` is System, never a one-time read of Windows), waits for the PALETTE to settle (Qt's scheme signal can come first) and publishes one `AppearanceChanged(effective)`; a colour that means something goes through `theme.style(widget, light_stylesheet)` (resolved per look and rewritten on change; `tests/test_theme.py` fails on a direct `setStyleSheet`), a painted one through `theme.ink` / `faint` / `panel_fill` / `paper`, and the web pages are TOLD the look (`PageLook`, one latest value, no queue; the 2D editor's four toolbars go dark and its drawing area is never filtered, measured pixel-identical); the offscreen platform IGNORES a forced scheme, so the palette tests skip there; the design and its measurements, including the rejected whole-page inversion, are `docs/APPEARANCE_DESIGN.md`; driven by `benchmarks/visual/appearance.json`
- `src/openchem/app/menu_layout.py` -- where every command sits in the menu bar, as ONE table (`MENU_SPECS`): the builders in `MainWindow._build_*_menu` still create and document each action, then `_arrange_menus` re-orders each menu (first block in the order given, submenus A-Z, loose entries A-Z, last block), logging a name the table uses that no menu holds; `walk` gives every command with its menu path and is what the Keyboard page's groups, `ShortcutRegistry.set_menu_order` and the drive `menu` step's `"in"` read. **`removeAction` makes the wrapper it is given own the action, so `_keep_alive` re-parents; and `_add_top_menu` makes the window own its menus (`menuBar().addMenu(title)` returns a wrapper the builders dropped, which let a menu and its actions be destroyed).** A commit-time snapshot (`tests/fixtures/menu_commands.json`) holds every command id and default shortcut to what they were, since a stored shortcut is keyed by id; tested by `tests/test_menu_layout.py` and `tests/test_keyboard_groups.py` (the page's collapsible sections), driven by `benchmarks/visual/menus_grouped.json`
- `src/openchem/net.py` — every outbound HTTP request, so each one identifies the app (a missing User-Agent is a 403 on some hosts)
- `src/openchem/chem/pka_worker.py` -- the persistent pkasolver sidecar: one owner thread over a request queue, `pka_runner.py --serve` as the child; the cache in `pka_providers._PAYLOADS` sits in front of it and `use_cache=False` bypasses it; `OPENCHEM_PKA_WORKER=0` turns it off (the suite does)
- `src/openchem/chem/proton_affinity.py` -- the chemistry of the proton affinity / gas basicity calculation, ported from `benchmarks/proton_affinity/` (PASS 2026-10-20) and held to its records by `tests/test_proton_affinity_calculation.py`: scope check (`check_scope`, `OutOfScope`), structures and ORCA input, output parsing, the symmetry-number override, `resolve` (PA and GB with the site table from the job records); no engine and no Qt; `Sequence` is the pure state machine of one run's jobs (order, the one `Calc_Hess` retry, failures) and `descriptors` builds the typed `orca.proton_affinity` / `orca.gas_basicity` outputs with their site table and the benchmark's measured error. `QuantumChemistryService.request_proton_affinity` runs it (one molecule slot, cancel, `tests/test_proton_affinity_service.py`); it is registered as `orca.proton_affinity` in `bootstrap.py` (LIMITED and shown since 2026-10-23, after the driven run on real ORCA recorded in `docs/PROTON_AFFINITY_DESIGN.md`; needs approval) and offered by the Quantum Chemistry panel's `Proton affinity...` button (`tests/test_proton_affinity_panel.py`)
- `src/openchem/chem/bond_dissociation.py` -- the chemistry of the X-H bond dissociation enthalpy calculation (stages 1 and 2 of three: the chemistry, and `QuantumChemistryService.request_bond_dissociation` running it under the molecule's job slot with one result and one run, `tests/test_bond_dissociation_service.py`; and stage 3, `orca.bond_dissociation_enthalpy` registered in `bootstrap.py` (LIMITED and shown since 2026-10-25, after two more driven runs on master; needs approval) and the Quantum Chemistry panel's `Bond dissociation...` button with its bond-choice dialog (`_BondChoiceDialog`; `tests/test_bond_dissociation_panel.py`), driven on real ORCA by `benchmarks/visual/bond_dissociation_run.json` through the drive steps `bond_dissociation_run` / `bond_dissociation_report`), ported from `benchmarks/bde/` (PARTIAL, 2026-10-21) and held to its records and to the held-out arm's (PASS, 2026-10-23) by `tests/test_bond_dissociation_calculation.py`: scope (`check_scope`, H, C, N, O, S, at most nine heavy atoms), `bond_classes` (one heavy atom per symmetry class; an O-H next to O or N is flagged), structures (the parent's conformers, a radical's starts are the parent's with one hydrogen deleted, the hydrogen atom), the ORCA input, the radical-skeleton check, `select` (lowest enthalpy of each species, `DH298 = H(R.) + H(H.) - H(RH)`), `BENCHMARK` (the stated error: 49 bonds, mean absolute 1.48 kcal/mol, mean signed -1.38, i.e. the calculation runs LOW, and 3.3 for O-H next to O or N) recomputed from the committed records by a test, the pure `Sequence` (hydrogen atom first, the one `Calc_Hess` retry) and `descriptors` (`orca.bond_dissociation_enthalpy`, the weakest computed bond in kJ/mol with every bond's value or reason in its provenance)
- `benchmarks/restart_v2/run_restart.py` / `restart_core.py` / `benchmarks/bde_heldout/` -- the displaced-restart protocol (v2) and its two arms, DRAFT and NOT RUN (`benchmarks/restart_v2/PREREGISTRATION.md`): `restart_core.py` is pure (the ORCA `.hess` reader, the +/-0.15 Angstrom displacement along the most imaginary mode, `needs_restart`, the stress set's adoption rule, the preregistered bias test), `run_restart.py` runs the chain of one structure (the first run's two stages, then Hessian and two displaced optimizations) for the stress set and the held-out bonds and reports both (the first run's judge, unchanged); the held-out references are ATcT 1.228 combined by `bde_heldout/extract_atct.py` (30 bonds chosen by rule, 3 excluded and documented); tested by `tests/test_restart_v2_runner.py` and `tests/test_bde_heldout_data.py`
- `benchmarks/restart_v3/` (`PREREGISTRATION.md`, `references.json`, `LITERATURE_LOG.md`) / `benchmarks/thiyl_probe/` -- restart protocol v3, FROZEN 2026-10-28 (decisions D1-D7; `freeze.json` hashes the runner, the shared code, the references and the text, `freeze.py` is how an Amendment is made, `tests/test_restart_v3_freeze.py` guards it) and Arm C RUN 2026-10-28, PASS (6 bonds, MAE 0.94, MSE -0.94, max 1.86; `RESULT_C.md`; the numerical stage never fired there), Arms D, D-Ph and C-Br not yet run: a numerical-frequency step for radicals (R1 only; the stability trigger R2 was measured and dropped), Arm C (six F/Cl C-H bonds, ATcT, deciding), **Arm D (S-H of ethanethiol, the two propanethiols and tert-butanethiol from the gas-phase acidity cycle, deciding for S-H only; the propanethiol D298 is DERIVED with a thermal step COMPUTED in `thermal_step.py` and held to Ervin's published ethanethiol step, and all three share an anchor with the first run's methanethiol bond)** Arm D-Ph (thiophenol S-H, REPORTED ONLY against every determination, none a reference, decision D6) and Arm C-Br (four bromine C-H bonds, REPORTED ONLY: the R + HBr kinetics are disputed and a coupled-cluster calculation sits below them); `references.json` holds the printed inputs and `tests/test_restart_v3_references.py` recomputes every derived number; `LITERATURE_LOG.md` is the record of what was fetched and read (PDFs in Sci Downloads, text extracts outside Git, a reusable literature-search prompt); **the runner** is `run_restart_v3.py` / `restart_v3_core.py` (v2's chain loaded by path and reused; a radical still below -20 cm-1 after the re-run gets ONE `NumFreq` job at the re-run's geometry, no displaced restart, enthalpy kept and labelled "frequencies not verified" if the numerical mode is still below -20, any size, labelled as outside the benchmark above 12 atoms; Arms `halogen`/`sh`/`bromine`/`thiophenol`; run order and commands in the preregistration's section 11), tested by `tests/test_restart_v3_runner.py` with excerpts of real ORCA output in `tests/fixtures/orca/`
- `src/openchem/chem/periodic_charges.py` — EQeq charges for a crystal; the only calculation here about a periodic solid, reached through `crystal_report.py` rather than the calculator registry (a `CalculationRequest` cannot name a crystal)
- `src/openchem/domain/refusal_kinds.py` — why a calculator declined (limit / needs input / needs setup); a refusal with no kind is a fault
- `src/openchem/domain/calculator_support.py` — a calculator's stage (maturity of this implementation) and default visibility, with the reason; `LEGACY_UNCLASSIFIED` only shrinks (see `docs/CALCULATOR_MATURITY.md`)
- `src/openchem/domain/support_marker.py` / `ui/widgets/stage_marker.py` — the small star beside a calculator (full = STABLE, half = LIMITED, empty = EXPERIMENTAL) on Properties rows and in the Results reader; an unclassified calculator gets none, and the rows of a section that has a star keep the room for one; `tests/test_support_marker.py`, driven by `benchmarks/visual/stage_markers.json`
- `src/openchem/domain/execution_policy.py` / `builtin_execution_policies.py` -- whether a model may start a calculator or a person approves a preview first; measured in `benchmarks/calculator_cost/`, attached to each definition by `bootstrap`; the design the assistant bridge follows is `docs/AI_CALCULATION_BRIDGE.md`
- `src/openchem/app/calculation_host.py` / `plugins/calculation_access.py` -- the window's side of the assistant's calculator bridge and the handle a plugin gets as `context.calculations` (no way to approve a run); pure parts in `domain/calculation_bridge.py` (cards, validation), `turn_snapshot.py` (what a turn may read) and `run_lifecycle.py` (the run ledger); driven in the real window by `benchmarks/visual/ai_bridge_run.json`
- `src/openchem/domain/result_envelope.py` -- what a stored result looks like to a model: every number with its method, settings, structure, units, status, freshness and caveats; `plugins/ai_assistant/bridge.py` / `calculation_tools.py` are the eight tools built on it (`read_scores` reads the user's derived scores, which are not stored results, and `propose_score` / `list_score_outputs` let it PROPOSE a new one that only a person can save (`domain/score_proposal.py`, `CalculationHost.propose_score`, approved on `PluginCalculationApprovals.approve_score`, driven by `benchmarks/visual/ai_score_proposals.json`); `list_goals` reads `domain/calculator_goals.py` as knowledge; nothing calls `PropertyPanel.run_goal`, which skips the execution policy) (and the only place a tool is handed the calculation handle, never the approvals one); driven in the real window by `benchmarks/visual/ai_assistant_tools.json`
- `src/openchem/domain/calculator_search.py` -- the one rule for which calculators match a phrase (the launcher's Find box and the assistant)
- `src/openchem/domain/recipe.py` / `recipe_run.py` -- a recipe (an ordered plan whose steps read each other's typed outputs; closed value types, closed transform table, `validate_recipe`) and one evaluation of it (`RecipeRun`, its own store and `recipe_runs` project block, eight binding states, staleness derived at read by `assess`); the design is `docs/RECIPES_DESIGN.md`, `ResultStoreService.record_recipe_run` is the one write path. The first shipped recipe is the Lewis pairing: `domain/lewis_pairing.py` (the plan), `recipe_catalogue.py` (what ships), `lewis_binder.py` (stored runs -> evidence or a reasoned gap), `chem/lewis_pairing_eval.py` and `chem/recipe_host.py` (evaluation, and "does this run still describe the drawing"), `services/recipe_service.py` (the host side; evaluates without recording); the window is `ui/dialogs/lewis_pairing_dialog.py` (Tools menu; view model `domain/recipe_preview.py`; driven by `benchmarks/visual/lewis_pairing.json`); the real-ORCA gate on BH3/BF3 with CO was preregistered and PASSED at 0.01 eV on 2026-10-13, and is final (`benchmarks/lewis_gate/PREREGISTRATION.md`; arithmetic `app/lewis_gate.py`, scripts `benchmarks/visual/lewis_gate_*.json`); a kept answer is read in Results as a `RecipeAnswer` (`domain/recipe_answer.py`, built by `RecipeService.answers_for`, stale from `assess`, never stored as a result)
- `src/openchem/chem/fukui.py` / `app/fukui_gate.py` -- the condensed Fukui functions (f+, f-, f0 and the dual descriptor, from the Hirshfeld charges of a closed-shell molecule's neutral, cation and anion at one geometry): `chem/fukui.py` is pure arithmetic that refuses a state whose charges do not sum to its charge, `chem/orca_engine.py` writes the compound input (calc type `fukui`) and reads each job from its own stretch of output (`parse_hirshfeld_tables`, `_fukui_job_results`, `parse_per_atom_output`, a hook `QuantumEngineProvider` gained with a default of nothing), `services/quantum_chemistry_service.py` publishes the four datasets (f- alone for an anion) as `PerAtomDataComputed` and files them like descriptors; **Fukui v2** (`benchmarks/fukui_gate_2/DESIGN.md`) is `chem/fukui_plan.py` (pure: which jobs a run has and which finished one it reads: an anion's N+1 state is a dianion, written LAST so that its failure costs f+ and not f- (the second gate decided f- alone for an anion; the dianion came back after it, with a Settings switch, `FUKUI_ANION_F_PLUS`, that leaves it out again), extra HCore and Hueckel starts of an anionic state at a basis with diffuse functions, the lowest solution read unless the default is within 0.01 eV), `IntAcc 6.0` and `HFTyp RHF|UHF` in every job, and three real-ORCA fixtures in `tests/fixtures/orca/` that `benchmarks/fukui_gate_2/make_fixtures.py` regenerates; the first gate, which FAILED by 0.0014 and is final, is `benchmarks/fukui_gate/PREREGISTRATION.md` with its arithmetic in `app/fukui_gate.py` and its scripts generated by `benchmarks/fukui_gate/make_scripts.py`; the second, on De Proft et al.'s tables (15 species, 47 numbers, 11 site statements; the calculation tested is v2) also FAILED (33 of 47 numbers within 0.02, 9 of 11 sites; final; the calculator stays experimental) and is `benchmarks/fukui_gate_2/PREREGISTRATION.md` with its typed tables, rules and judge in `app/fukui_gate_2.py`, the drive steps `fukui2_*` and scripts generated by `benchmarks/fukui_gate_2/make_scripts.py`, and what was measured after it (the published numbers of three molecules match a cation state above the lowest one; the application's own input reaches that state for benzaldehyde in 6 of 14 runs and the lowest in 8, depending on a rotation, a 0.001 A displacement or the embedding) is its 11.4 with `cation_states_probe.py`, `route_check.py`, `core_check.py`, `landing_check.py` and `reported_sites.py` beside it; the prose is `docs/explainers/reactivity.md`; what was measured after the gate (the integration grid, spin, the anion's SCF solution, reproducibility across embeddings) is `PREREGISTRATION.md` 11.5 and 11.6 with the scripts `grid_probe.py`, `grid_sweep.py`, `rohf_cation_sweep.py`, `anion_guess_probe.py` and `seed_sweep.py` beside it; **Fukui v3** (`benchmarks/fukui_v3/DESIGN.md`) is the search for other states of the cation, because one N-1 job reached whichever state ORCA's SCF fell into and for benzaldehyde that was not a function of the structure: three more cation jobs per run that start from the neutral's orbitals with the hole in the HOMO-1, -2 and -3 (`chem/fukui_plan.py` `searchable_holes`, `FukuiJob.hole`; written after the N+1 state of a neutral species or cation and before the dianion of an anion; read back out of ORCA's echo of the input by `OrcaQuantumEngineProvider._echoed_holes`, since the guess line says MOREAD), read by `chem/fukui_states.py` (`read_cation`: the lowest state, a degenerate level averaged, the states within 0.5 eV reported as competing), switched off by `FUKUI_CATION_SEARCH` in Settings, with real-ORCA fixtures `tests/fixtures/orca/*_fukui_cation_search*`; its third gate (reproducibility of f- under rotation, displacement and re-embedding over 12 species, completeness against an exhaustive hole search, no regression on 8 second-gate species) is `benchmarks/fukui_v3/PREREGISTRATION.md` with its typed panel and judge in `app/fukui_gate_3.py` and its runner `benchmarks/fukui_v3/run_gate.py`; **Fukui gate 4** (`benchmarks/fukui_gate_4/PREREGISTRATION.md`, PARTIAL, final) is the first check against a reference whose cation states are identified: `app/fukui_gate_4.py` reads a state's kind (sigma or pi hole) from ORCA's Loewdin spin populations of a planar molecule oriented with its plane as xy, holds the typed references from eleven registered papers (the diazines, imidazole, pyrazole, oxazole, selenophene) and judges them; its runner is `benchmarks/fukui_gate_4/run_gate.py`, its calibration on four seen molecules is `artifacts/calibration/`, and the two limits it found (a sigma state about a tenth of an eV too low relative to the pi states, and no second state of one symmetry) are in its 11.4
- `src/openchem/domain/score_formula.py` / `score_units.py` -- the formula language of a user-defined derived score: a hand-written parser (nothing here evaluates Python; `tests/test_score_formula_guard.py` reads the syntax trees), nine functions, strict opaque units with no conversions, and an evaluator that refuses rather than return a non-finite or invented number; slice 1 of `docs/DERIVED_SCORES_DESIGN.md` (`tools/check_score_formula.py` tries a formula from the command line); `domain/score_outputs.py` is slice 2, the table of approved outputs a formula may name (typed numbers, each read from one input: the drawing, or for the ten shape descriptors, eight of Geometry Analysis's sizes, HOMA's two extremes, the dipole's magnitude and five surface numbers the conformer every calculation uses (HOMA's only when ORCA optimised it; the dipole and the surface numbers only at the settings `ApprovedOutput.run_with` names); each with the unit it must carry and an endpoint tag; two inputs of one endpoint are refused), swept by `tools/sweep_score_outputs.py` and held to the registry by `tests/test_score_outputs.py`; `domain/score_constants.py` is a named number with a declared unit, the strict alternative to a bare number in a formula; `domain/score_editor.py` and `ui/dialogs/score_dialog.py` are slice 3d, the Derived Scores window (Tools menu; a `Draft` of strings checked by the same `check_score_definition` the service and loader use, a preview from `ScoreService.preview`, driven by `benchmarks/visual/score_dialog.json`); slice 3a makes it a feature: `domain/score_definition.py` (a definition and its label and field rules), `score_definition_store.py` (a project's definitions and the `derived_scores` block, which carries through anything this build cannot read), `score_value.py` (reading the inputs from the molecule's CURRENT results and evaluating, or refusing naming the input; a geometry number that is not the stored conformer's, or is of a whole structure of several fragments, is declined by `not_applicable_reason`), `services/score_service.py` (make, edit, remove, `values_for`; never starts a calculation) and the `ScoreDefinitionsChanged` event; a score is NOT a registry calculator; slice 3b reads it in Results as a `ScoreAnswer` (`domain/score_answer.py`, a projection built by `ScoreService.answers_for`, never stored; its category is `FactCategory.DERIVED`), driven by `benchmarks/visual/score_results.json`; slice 3c puts a score in the project table: `domain/score_table.py` reads the table's own cells (`read_cell_output`, a calculator that declined through its placeholder column) and returns a COPY of the table with the score columns first (`table_with_scores`), which `ProjectTableView` draws, exports and hands to the analytics and rebuilds when a definition changes, driven by `benchmarks/visual/score_table.json` (the older Batch panel's own table is given the same lookup, driven by `benchmarks/visual/score_batch_table.json`); slice 4a lets the assistant READ a score (never write one): `domain/score_reading.py` evaluates the definitions frozen into the turn (`TurnContext.scores`, captured by `CalculationHost.begin_turn`) against its frozen results, `result_envelope.scores_view_envelope` serialises them (owner and note never sent) and `plugins/ai_assistant/calculation_tools.py`'s `read_scores` is the sixth tool, driven by `benchmarks/visual/ai_scores.json`; slice 4c is the second `on_missing` policy: `ScoreDefinition.defaults` (format 2; a definition with none is byte-for-byte format 1) gives an input that was NEVER CALCULATED a declared number (`score_value.InputState.DEFAULT`, `ScoreValue.defaulted`; never for a refused, failed, stale or wrong-unit input, never a score from defaults alone), and every surface that shows a number that used one says so (a `*` and a companion column in the project table, `computed_with_defaults` for the assistant), driven by `benchmarks/visual/score_defaults.json`; `domain/score_run_inputs.py` says which always-on properties and calculators a run must include for the scores to have a column (the Properties Presets menu's "Tick what my scores read", driven by `benchmarks/visual/score_tick_inputs.json`)
- `tools/perf_census.py` / `benchmarks/perf/scenarios.py` / `src/openchem/app/drive_probes.py` — the resource census: external sampler, scenario builders, in-app probes; findings in `docs/PERFORMANCE_CENSUS.md` (start with its "Unresolved" and "where they were wrong" sections before trusting a number)
- `src/openchem/cli/` — the headless command line (`openchem-cli`): any registered calculator on a SMILES, one JSON envelope on stdout, no Qt; `tests/test_cli.py` runs the real service task beside it and compares
- `tools/naming_variants.py` — a naming population from seed molecules (the operators are rounds 32-35's generator rules, ported), and the atom-order diagnostic: it names random spellings AS WRITTEN (not through `naming_census_scan.name_rows`, which canonicalises) and reports any structure with more than one name; `tools/naming_census_scan.py` now labels each wrong-molecule row with what the read-back changed (`delta`)
- `tools/naming_ion_populations.py` -- how naming rounds 46 to 90 found their defects once the census was saturated: change ONE site of every census molecule into an ion (`anion` deprotonates, `cation` protonates, `quaternary` N-methylates; since round 55 `zwitterion`, `dianion`, `dication`, `betaine` and `quat_dication` change two sites at once), name it, read it back through OPSIN, and class each (`ok`, `refused`, `no_anion_word`, `charge_changed`, `wrong` ...); `tests/test_naming_ion_populations.py` pins which ions it builds and how it judges a name
- `docs/explainers/` / `tools/calculator_explainers.py` -- hand-written prose on what each calculator DOES, merged into the generated `CALCULATOR_REFERENCE.md` by `tools/build_calculator_reference.py`; `tests/test_calculator_explainers.py` owns it (the `EXPLAINER_DEBT` ratchet only shrinks, citations are `[source:key]`, no URLs)
- `tools/survey_descriptor_inputs.py` / `DescriptorProvider.geometric_descriptor_ids` — which always-on results depend on coordinates and which only on how the hydrogens are written (three structures per molecule: the drawing and two embeddings). A conformer request computes ONLY the provider's geometric descriptors (the ten shape ones); every other descriptor, alert catalogue and per-atom dataset is computed on the drawing, in `DescriptorService`, in the Project table (`batch_service`), and in a saved file (`ResultStoreService.set_project` drops an earlier build's GEOMETRY copies); guarded by `tests/test_descriptor_input.py`, driven by `benchmarks/visual/descriptors_survive_a_conformer.json`. A DRAWING request on a molecule that holds a conformer carries the geometry run with it and the two split the provider's ids (the drawing run records the shape ids and does not show them: two writers of one reader id lost 37 runs in 40); a replay that did not bring them back is topped up by `request_missing_geometric_descriptors`; a GEOMETRY dispatch also claims the ids from drawing runs already running (`_GeometryClaims`: the check and the emit are one step under a lock); driven by `benchmarks/visual/descriptors_restored_with_a_conformer.json`
- `benchmarks/mp_bp/` -- the melting / normal-boiling-point benchmark (preregistration FROZEN 2026-10-25, Amendment 1 in its section 13; no method scored yet): `mpbp_lange.py` / `mpbp_crc.py` read the handbooks' tables by column position (needs `pymupdf`, run via `uvx --with pymupdf`; Lange's minus signs are symbol-font glyphs classified by rendered ink), `mpbp_cells.py` is the closed grammar of a mp/bp cell (anything outside it is refused with a reason), `mpbp_identity.py` checks name -> structure against the printed formula and weight, `mpbp_build.py extract|build|report` writes the corpus OUTSIDE Git (copyrighted tables) and a committed split manifest, aggregate summary and generated `CORPUS_REPORT.md`; tested by `tests/test_mp_bp_corpus.py` (a built corpus is NOT_RUN without `OPENCHEM_MP_BP_CORPUS`); `mpbp_models.py` / `mpbp_score.py` are Phase 3 (Joback, Marrero-Gani, Candidate C, development-only baseline; `features` -> `select` writes `freeze.json` -> `score` development/selection any time -> `holdout` only with `--confirm-holdout-once`, on byte-identical frozen files, once, behind a lock), `mpbp_result.py` renders `RESULT.md` from `results/` (the holdout was scored ONCE, 2026-10-25, no method passed; the lock is `results/holdout_scored.lock`), tested by `tests/test_mp_bp_scoring.py`; `mpbp_family.py` is the leave-one-family-out generalisation report (`FAMILY_REPORT.md`, `results_family/`; a different claim, no verdict, Amendment 3), tested by `tests/test_mp_bp_family.py`; both books contain printed errors, found by comparing them
- `benchmarks/energetics_props/` -- Phase B (energetic materials) of the validation program, DRAFT preregistration, MERGED but NOT FROZEN (the owner's decisions of 2026-10-26 are its section 15: crystal density's primary population is COD entries carrying a nitrate ester, nitramine, C-nitro or azide group, entity key `cod_structure_pass.entity_key`, room temperature only plus a gated correction study; the held-literature compounds are a side stratum; the COD archive and indexes live on E:, outside the repo; nothing built or scored): `PREREGISTRATION.md` (crystal density, condensed-phase enthalpy of formation, melting point; decomposition is evidence only; `value_kind` so a calculated value is never a reference; leakage status per candidate; label-error detection fixed before scoring; compounds the earlier survey examined forced out of the holdout; minimum n derived (60 paired verified holdout entities, so about 300 verified); Kamlet-Jacobs stays `NEEDS_INPUT`; the PETN reversal rule; owner decisions D1-D14 at the end), `INVENTORY.md` (generated from `inventory.json` by `inventory_report.py`, which refuses a count without a locator; counts of what the held books print, with locators, hand-check rates and the printed errors found; the ceilings in its section 7 are below 300 for qualified crystal density and for measured enthalpy; the LMU dissertations are NOT in the library), `epb_families.py` (structure-only families, fixed before any score; "organic" is NOT Phase A's rule, which would drop NTO and nitroguanidine), `inventory_scripts/` (the procedures behind the counts, not run in CI), `PETN_EVIDENCE.md` / `.json` (the evidence inventory for PETN, the nitrate esters and the nitramine stratum: one row per observation with its locator, `value_kind` and `lineage_root`, built by a generator kept outside the repo; **it carries no DOIs**, which live in the maintainer's notes, because `tests/test_sources_are_current.py` fails any DOI not registered in `docs/sources.toml`); tested by `tests/test_energetics_props_families.py`, `tests/test_energetics_props_inventory.py` and `tests/test_energetics_props_petn_evidence.py`; `epb_cod_corpus.py` (`extract|build|report`) reads the whole COD archive as a stream into a corpus kept on E: outside the repository (one disposition per entry, entity key = heavy-atom element graph, label rules of 15.4, bond orders perceived from coordinates with nitro groups set aside, previously examined compounds forced into development) and commits only `cod_split_manifest.json`, `cod_corpus_summary.json`, `cod_correction_pairs.json` and the generated `COD_CORPUS_REPORT.md` (counts, nothing scored; 2,797 resolved entities, holdout 519, 49 correction pairs), tested by `tests/test_energetics_props_cod_corpus.py`; `epb_density_correction.py` is the low-temperature density correction study of 15.8 (code and tests only, no real pair scored: two closed-form expansion forms fitted on development pairs, chosen on selection, one locked holdout run with an entity-resampling bootstrap against 0.015 / 0.02 g/cm3; its `MIN_HELD_OUT_ENTITIES` of 35 was confirmed by the owner 2026-10-27 and is in the preregistration's section 16 (Amendment 2), and its pairs are every organic nitrogen-containing crystal, widened from the four groups by the owner 2026-10-27: 369 pairs, 82 held-out entities, the 49 explosophore pairs flagged and reported beside the whole, never the gate), tested by `tests/test_energetics_props_density_correction.py`; `epb_density_candidates.py` / `density_candidates_manifest.json` are crystal-density candidates D1 (Tarver 1979) and D4 (Keshavarz 2009, two papers) and Candidate D (the preregistration's section 17: the printed tables, about 360 rows, are transcribed and checked three ways but kept in the maintainer's private notes; the committed manifest holds entity keys, counts, hashes and the printed inconsistencies by id, 6 of 256 keys are in the COD corpus, 5 of them held out; the module holds the published parameters pinned by a hash, with Keshavarz's CNG coefficient as the tables need it (-0.0751, printed -0.751), and Candidate D's fixed ten-group specification, fit and refusals; `OPENCHEM_DENSITY_CANDIDATES_DIR` runs the private checks, otherwise they are skipped by name), tested by `tests/test_energetics_props_density_candidates.py`. Do not edit `tools/validation_rows.py`: Phase A's `freeze.json` hashes it
- `tools/changelog.py` / `changelog.d/` -- changelog fragments: one uniquely named file per PR instead of a section of `CHANGELOG.md` (no shared insertion point, so no merge conflict); `new`/`check`/`preview` and a `build` that folds them into `[Unreleased]` at release time; `check --no-pending` gates the release tag; `tests/test_changelog_fragments.py`
- `benchmarks/thermophysical/marrero2001_groups.py` -- the general first-order fragmenter for Marrero-Gani (2001): SMILES -> counts of all 182 Table 6 groups, by group id (the paper prints `aC-NCO` twice), as the best full disjoint cover under the golden rule with aC-R groups first; "aromatic" is the paper's six-ring meaning, a molecule it cannot tile or ranks equally two ways is refused (`GroupingRefusal`, with the atoms); `estimate_first_order` gives Tm/Tb etc. at the first level; tested by `tests/test_marrero2001_groups.py` against every group's sample compound and Appendix B
- `tools/calculator_census.py` — every calculator over a fixed panel through the app's own path; `tests/test_calculator_census.py` fails on a fault, an error logged, an unclassified refusal code, or a moved cell

---

## Project-Specific Rules

- **Changelog entries are fragments, not edits to `CHANGELOG.md`.** This overrides the generic
  "`CHANGELOG.md` only / entry" rows in `project-baseline.md`. Run
  `uv run --no-sync python tools/changelog.py new <slug>`, fill in the file it prints, and
  `check` it; see `changelog.d/README.md`. Editing `CHANGELOG.md` directly brings back the
  merge conflict this removes. The release PR runs `build`.
- New descriptor sources (including future plugins) implement `DescriptorProvider` from `openchem.plugins.interfaces` / `openchem.chem.descriptor_providers` — never bolt caching onto `MoleculeModel` directly.
- Never store a raw RDKit `Mol` in a `.ocsproj` project file — persist molblock + canonical SMILES/InChI/InChIKey + metadata, and reconstruct via `ChemistryEngine`.
- Structure-modifying user actions go through a `QUndoCommand` in `openchem.commands` so undo/redo stays correct — don't mutate `MoleculeModel`/`ProjectModel` directly from UI code.

# OpenChem Studio — notes for Claude

## Working in a git worktree — do this before anything else

A fresh worktree needs two things set up, and **both fail silently rather
than loudly**, which is why they are the first thing in this file.

```bash
uv sync --extra ai --extra network --extra openbabel
"D:/Claude Co worker/Token Save/tokensave.exe" init
```

**The venv.** A worktree has no `.venv`. `uv run` will happily create an
empty one and then report `No module named pytest`, which reads like a
broken checkout rather than a missing sync.

**The tokensave index — the dangerous one.** The MCP server is registered
globally as `tokensave.exe serve` with no `--root`, and finds its project
by searching *upward* for a `.tokensave/` directory. A worktree created
under `.claude/worktrees/` sits inside the main repo folder and has none
of its own, so the search walks up and serves **the main checkout's
code** — a different branch, without the files you just wrote. Measured
2026-08-04: `tokensave_search` for a class written minutes earlier
returned `[]`.

Every call does carry a `worktree_mismatch` warning. **That warning is not
cosmetic; it means the answers are about different code.** Never work past it.

`init` costs about 2 seconds (343 files, ~8000 nodes) and leaves
`git status` clean. Three things that cost real time when they were not
known:

- **`init` refuses to rebuild an existing index.** It prints a "use
  `tokensave sync`" hint and exits 0, so a stale index looks like a
  successful re-index. Use `sync --force` to actually rebuild.
- **Initialising mid-session does NOT rebind the MCP tools.** The server
  resolved its root when it started, so `tokensave_*` calls keep hitting
  the old index. Until the session restarts, query through the CLI
  instead: `tokensave.exe tool health --path src/openchem`,
  `tokensave.exe tool search SomeClass`.
- **`tokensave branch` does not solve this.** It tracks branches within
  one checkout and syncs from that checkout's files, so it cannot see
  another directory's working tree.

The binary is not on PATH; call it by full path.

## Driving the app for a live check -- do NOT use the mouse

Several findings in this file could only be made in the running
application, so live checks are routine here. **They used to make the
machine unusable**, because every one drove the real input queue with
`SetCursorPos` + `mouse_event` + `SendKeys`: the cursor jumps, the app
must hold focus for every step, and Alex cannot work for the length of a
run. It was also fragile in a way that reads as an app bug -- a console
window stealing focus mid-sequence sent a paste into the wrong window and
the run looked like "the app ignored the import".

**Script the app from inside instead.** `OPENCHEM_DRIVE` names a JSON
file of steps (`src/openchem/app/debug_drive.py` documents the shape),
which run on a `QTimer` inside the process:

```bash
OPENCHEM_DRIVE=/path/to/script.json uv run --no-sync python -m openchem.main
```

    {"do": "import",     "path": "..."}      no file dialog
    {"do": "select",     "molecule": -1}
    {"do": "receptor",   "pdb_id": "6WGT"}   from the CACHE, never the network
    {"do": "receptor",   "pdb_id": "1HSG", "plain": true}
    {"do": "dock_receptor", "index": -1}     CHANGES the panel's receptor
    {"do": "dock_run"}                       the REAL button, real Vina
    {"do": "dock_panel", "tag": "after"}     box, its source, the status line
    {"do": "panel",      "id": "Properties"}
    {"do": "expand",     "section": "admet"}
    {"do": "calculator", "id": "admet_ml", "parameters": {...}}
    {"do": "calculator", "id": "...", "reveal": false}  no Calculator
                                          Inspector window -- see below
    {"do": "expect_inspectors", "count": 2, "titles": ["(qeq"]}  how many
                                          inspectors are OPEN side by side
    {"do": "atom_action", "atom": 2, "submenu": "Change", "text": "N",
     "expect": {"smiles_equals": "CCN", "undo_delta": 1}}  press an ENTRY of the
                                          atom menu the app builds, assert the
                                          structure and the undo stack
    {"do": "ketcher_hover", "bond": 0, "press": "2", "expect": {"bond_type": 1}}
                                          set Ketcher's HOVER through its own editor API
                                          (no pointer), press a key inside the editor,
                                          assert the page; "click": true sends a mouse-down
                                          and up instead; see docs/KETCHER_SPIKE.md. A
                                          script that changes a setting through the REAL
                                          Settings dialog writes the real store: put it
                                          back at the end (bond_click_cycle.json does)
    {"do": "atom_editor", "atom": 2, "set": {"charge": "1"}, "apply": true,
     "expect": {"dialog": true, "smiles_contains": "+", "undo_delta": 1}}  the atom
                                          menu's Edit... on the REAL page, asserted
                                          from the page; `ketcher_eval` runs one
                                          JS expression there and logs its string
    {"do": "shortcut", "command": "search_facts", "sequence": "Ctrl+Alt+F9",
     "press": true}                       rebind through the REAL Settings > Keyboard
                                          page, assert the ACTION and the page's
                                          status, and press the real new/old keys
    {"do": "compare_results", "property": "geometry_partial_charge",
     "expect": {"columns": 2, "atoms": 9}}     the inspector's REAL "Compare
                                          with..." menu, then the window
    {"do": "service_row", "calculator": "orca.nmr", "expect": {"panel": "Quantum_Chemistry"}}
                                          PRESS a row that opens another panel;
                                          `reveal_row` scrolls one into a shot
    {"do": "project_run", "calculators": ["topology_analysis"], "scope": "all",
     "descriptors": true}                 tick calculators, pick a scope (this/all/chosen)
                                          and press the REAL "Run selected"
    {"do": "project_run", "calculators": ["polar_surface_area"], "scope": "chosen", "chosen": [1, 2],
     "descriptor_ids": ["mol_wt"], "alert_ids": ["pains"]}   a SUBSET of the always-on properties
                                          and alert catalogs (the picker's answer, by id)
    {"do": "results_details", "molecule": 3, "expect": {"computed": ["polar_surface_area"],
     "rows": 2, "wait_ms": 5000}}         press Details in the project table for one molecule; the
                                          dialog is shown, not exec'd, and what it computed is read
    {"do": "expect_project_table", "rows": 2, "columns_contain": ["Atom count"],
     "showing": true}                     what the Results dock's PROJECT TABLE holds,
                                          read off the workspace the dock is built from
    {"do": "expand", "section": "workflow:alignment"}   open a Properties WORKFLOW section
    {"do": "workflow_move", "workflow": "docking", "to": "properties"}  move a workflow
                                          between its own tab and Properties by pressing the
                                          REAL button; `align_report` and `dock_panel` take
                                          `expect` (`home`, `rows`/`poses_at_least`,
                                          `viewer_built`, `settings_expanded`, `groups_expanded`)
                                          and read where the widget is off its containers
    {"do": "goal_wizard", "goal": "identity", "scope": "this", "press": "run_recommended",
     "expect": {"ran_all": ["elemental_analysis"], "status_contains": "Running"}}
                                          the goal wizard's REAL buttons ("customise" then
                                          "run", with "tick"/"untick"); `shot` takes
                                          "widget": "goal_wizard"
    {"do": "workflow_group", "workflow": "docking", "group": "search", "expanded": false}
                                          open or close a collapsible group INSIDE a workflow
                                          (alignment: settings; docking: box, prep, search)
    {"do": "properties_height_report", "workflow": "alignment"}  each level from the workflow up to
                                          the window: height against the minimum it asks for,
                                          STARVED when shorter; `properties_width_report` says why
                                          the list scrolls sideways; `properties_grab` saves the
                                          whole list at full height. A script that moves a
                                          workflow writes the real settings: end it in its tab
    {"do": "properties_scroll", "to": "workflow:alignment"}  scroll the Properties list
                                          ("end", "top", a pixel offset) so a tall section's
                                          picture is in the shot
    {"do": "chip", "calculator": "detonation", "expect": {"status": "needs_input"}}
                                          PRESS a status chip and assert where
                                          the press went; `tool_setup` is the
                                          window half of a "Needs setup" press
    {"do": "expect_coverage", "chips": {"griffin_hlb": "Can run"}, "rows": {"orca.proton_affinity": "✓"},
     "silent": [...], "tooltips": {...}}  what the Properties rows SAY about the drawn structure before any run
                                          (`domain/structure_coverage.py`), read off the chips and service-row
                                          labels; Settings > Recalculation switches it off
    {"do": "inspector_report", "tag": "after-edit"}  the Atom Inspector's
                                          pinned line, HELD results and state
    {"do": "inspect", "id": "geometry_partial_charge", "parameters": {"ph_dependent": true}}
    {"do": "inspect_report", "tag": "ph", "filter": "N", "select_row": 0}  the
                                          structure the panes draw, labels, table
    {"do": "result_report", "calculator": "geometry_partial_charge",
     "expect_refusal": "REFUSE_NOT_CONVERGED"}  WHICH refusal Properties
                                          holds; "Not applicable" names none
    {"do": "units", "key": "mg_per_ml"}   the reader's Units COMBO, and what
                                          the chart and unit rows then say
    {"do": "reader_layout_report", "tag": "beside"}  whole fact ROWS on
                                          screen, through every clipping parent,
                                          and every CHROME row (reader_chrome)
    {"do": "fact_rows_report", "tag": "docked"}  each value row's height
                                          against its TEXT's, never the row's
                                          own answer, which is floored
    {"do": "dock_resize", "panel": "Results", "width": 380}
    {"do": "chart_cursor", "x": 7.4}       a REAL click on the line chart,
                                          and the kept reading beside the fact
    {"do": "shot",       "path": "..."}
    {"do": "lewis",      "details": true}     the Full Lewis window
    {"do": "shot",       "path": "...", "widget": "lewis"}
    {"do": "dialog",     "name": "HelpDialog"}   built by ui/dialogs/inventory
    {"do": "dialog",     "name": "PeriodicTableDialog", "tab": "Isotopes"}
    {"do": "dialog",     "name": "HelpDialog", "topic": "calc-dipole-moment"}  the Help window on a
                                          topic, or "search": "SD-POE" typed into its own box
    {"do": "dialog",     "name": "SettingsDialog", "section": "results"}
    {"do": "control",    "name": "railHidesPanels", "value": false}  a NAMED
                                          control of the open dialog, for real
    {"do": "close_dialog"}                before a key that needs MainWindow active
    {"do": "shot",       "path": "...", "widget": "dialog"}
    {"do": "overlay",    "on": true, "gallery": true, "step": 1}
    {"do": "cip",        "on": true}          R/S and E/Z, through the menu
    {"do": "erase",      "element": "N"}      a REAL canvas edit
    {"do": "menu",       "text": "Rotate 3D"}  THIS app's menu bar
    {"do": "menu",       "text": "Undo", "prefix": true}  "Undo <command>"
    {"do": "menu",       "text": "Derived Scores...", "in": "Tools > Calculators"}  an entry by its MENU PATH
                                          (the menus are grouped; the CIP toggle is in two); `dialog` takes
                                          `"real": true` for SettingsDialog, built with the window's own
                                          shortcut registry so a shot shows the real Keyboard groups, and
                                          `control` types into a QLineEdit (the page's `shortcutSearch`)
    {"do": "picture",    "index": 0, "path": "..."}  the reader's
                                          chart, through the REAL export
    {"do": "rotate_report", "tag": "entered"}  the tick, the button AND
                                              whether the PAGE is still in it
    {"do": "key", "key": "F7", "focus": "canvas"}  a REAL key, at the
    {"do": "key", "key": "Escape", "focus": "explorer"}   focus widget
    {"do": "key", "key": "Comma", "modifiers": "ctrl", "close_modal_after_ms": 1500}
                                          a shortcut that opens a MODAL: the
                                          log names it, and the ACTIVE window
    {"do": "geometry_report", "tag": "flat"}   z spread AND the conformers
    {"do": "adopt"}                            the REAL "Use in 2D Editor"
    {"do": "select_atom", "atom": 4}       the inspector ROW, and
    {"do": "selection_report"}             BOTH id spaces off the page
    {"do": "report",     "tag": "after"}      conformers, undo depth, SMILES
    {"do": "conformer_report", "tag": "x", "expect": {"canonical_method": "orca_opt",
     "canonical_mapped": true, "conformers": 3}}   each stored conformer (method, energy, whether it
                                          has the way back to the drawing's atoms, its GEOMETRY fingerprint,
                                          the same string `qc_run` logs) and which one a calculation gets;
                                          it also reads the 3D VIEWER and the status bar: `viewer_index`,
                                          `viewer_on_canonical`, `viewer_label_contains`/`_excludes`,
                                          `orca_conformers`, `origin_slot`, `status_contains` -- "the geometry
                                          is stored" and "the viewer shows it" are different claims;
                                          also `badge_contains`/`badge_empty` (the Properties header),
                                          `explorer_contains`/`explorer_excludes` (the Project Explorer row)
                                          and `methods` (every conformer's method in slot order)
    {"do": "orca_optimize_button", "via": "button", "conformer": 1, "expect": {"chosen_slot": 2,
     "calc_type": "Geometry Optimization", "job_started": false}}    put the viewer on a slot and press the REAL
                                          "ORCA optimize" button (or `"via": "menu"`, Tools > ORCA Geometry
                                          Optimization...), then assert what the Quantum Chemistry panel was SET UP
                                          to do and that NOTHING started; Run is a separate `qc_run` step
    {"do": "jobs_report", "tag": "running"}   rows AND whether it is POLLING
    {"do": "jobs_cancel", "row": 0}           the real button in a real row
    {"do": "synthesis_panel", "tag": "x", "press": "plan", "route": 1, "step": 0, "scroll": "end",
     "expect": {"routes_at_least": 1, "picture": true, "status_contains": "routes found"}}
                                          the Synthesis panel's REAL buttons and lists, and what it SHOWS (status, routes,
                                          whether a step's picture is drawn, the limitations; `details_scroll` reaches the last
                                          lines of the step's text, its consistency checks and alerts); press and report in
                                          SEPARATE steps, since Plan waits for the configuration to be read off the GUI thread
    {"do": "synthesis_setup", "python": "...", "config": "..."}  the planner's settings for THIS run ("" = not set up);
                                          writes the real registry, so `quit` or `{"restore": true}` puts them back
    {"do": "synthesis_fixture_plan", "fixture": "aspirin_it100", "screen": true}  give the SELECTED molecule a plan a real planner once made (the real parser and annotator,
                                          stored as a finished search stores one), so a script can save, reopen and read a plan without the planner; pair with `save_project`,
                                          `menu` "New Project" and `open_project`
    {"do": "ai_card", "card": "synthesis", "action": "approve"}   the Approve (or "cancel") of a card for a synthesis SEARCH the assistant asked for; `ai_expect` takes
                                          `synthesis_requests` (cards waiting) and `notes_contain` / `notes_exclude` (what is held to tell the model with its next message)
    {"do": "conformers_finish", "expect": {"enabled": true, "readout_contains": ["found"]}}
                                          the REAL Finish now in the 3D viewer, asserted
                                          before it is pressed; "press": false only looks
    {"do": "conformers_provenance", "expect": {"stop_reason": "finished_early"}}  how the
                                          stored run ended; `conformers` takes "with_settings":
                                          true for what Settings > Conformers adds, and
                                          "optimize_lowest": true to tick the Generate window's ORCA box
                                          (its real checkbox; `expect_offer` asserts what the window offered)
    {"do": "screen_run",  "receptor": 0}      the REAL Run button, and the
                                              PREP DICT the service got
    {"do": "qc_run", "calc_type": "NMR (raw shielding)", "method": "HF def2-SVP"}
                                              REAL ORCA, and the IDENTITY
                                              the service was handed; add
                                              `"conformer": 1` (zero-based slot) to
                                              point the Conformer box first, or
                                              `"automatic"` to put it back: the pick
                                              PERSISTS between runs
    {"do": "inspector_report", "expect_spectrum": "stale"}  ASSERTS the held
                                              spectrum carries that identity
    {"do": "tautomer_run", "method": "HF STO-3G"}  the REAL "Tautomers..." button,
                                              REAL ORCA, and the identity handed on
    {"do": "tautomer_report", "expect": {"in_results": true, "runs_label": "Tautomer",
     "view_enabled": true}, "view": true}     where the result is REACHABLE from, read
                                              off the widgets (Results list, Runs combo,
                                              the View button, no auto-popped dialog)
    {"do": "proton_affinity_run", "expect_refusal": "Cl"}   the REAL "Proton affinity..." button (answer its cost question with
                                              OPENCHEM_DRIVE_MODAL=yes), or a refusal asserted before anything is queued;
                                              follow a run with `qc_wait`; `proton_affinity_report` reads the STORED
                                              outputs (`pa_kj`/`gb_kj` windows or `null` for no value), the stored run
                                              and the panel's text; benchmarks/visual/proton_affinity_run.json
    {"do": "bond_dissociation_run", "bonds": [0, 1]}  the REAL "Bond dissociation..." button and its REAL bond-choice dialog
                                              (ticked and pressed through its own widgets from a timer, since it is modal;
                                              `"cancel": true`, or `expect_refusal` before the dialog opens); follow a run with
                                              `qc_wait`; `bond_dissociation_report` reads the STORED output (`dh_kj`, each bond's
                                              kJ/mol by label prefix or `null`, `reason_contains`), the stored run and the panel's
                                              text; benchmarks/visual/bond_dissociation_run.json
    {"do": "tautomer_nmr_run", "method": "HF STO-3G"}  the REAL "Tautomer NMR..." button on the
                                              newest distribution run (answer its cost question with
                                              OPENCHEM_DRIVE_MODAL=yes); `tautomer_nmr_report` reads
                                              the traces DRAWN, the stored result and the combo
    {"do": "save_project", "path": "..."}     the REAL save, results included; "results": false
                                          writes the file an older build wrote (conformers, no results)
    {"do": "dock_move", "panel": "Results", "area": "top"}   as a drop
    {"do": "dock_move", "panel": "Results", "beside": "Properties"}
    {"do": "dock_tabify", "panel": "Results", "onto": "Properties"}
    {"do": "dock_float", "panel": "Properties", "on": true}
    {"do": "reset_layout"}                    View > Reset Panel Layout
    {"do": "dock_report", "tag": "after"}     areas, rects, OVERLAPS, placed
    {"do": "log_report", "tag": "after"}      what the APPLICATION logged
    {"do": "dock_menu", "panel": "Results", "press": "move_bottom", "expect": {"present": ["move_left", "expand"], "disabled": ["move_bottom"],
     "text": {"lock": "Unlock"}}}           open a panel's title-bar layout menu through its REAL aboutToShow and press one entry (its objectName
                                          without `dockMenu_`: move_left, expand, restore, float, dock_back, lock, return, alongside_<Panel>);
                                          `dock_state` asserts where a dock is afterwards, once the layout has settled (area, hidden, floating,
                                          user_placed, expanded, min_width / max_width, no_overlaps); `dock_button` presses or asserts a panel's own
                                          title-bar button (`"item"` for one entry of its menu); benchmarks/visual/dock_layout_menu.json
    {"do": "expect_clean", "allow": ["..."]}  FAILS the run on an unexcused ERROR
    {"do": "expect_results", "expect": {"solubility": "ready",
                             "fragment_counts": {"facts_contain": ["nitro (2)"]}}}
                                          what Properties HOLDS, asserted
    {"do": "descriptors_report", "tag": "x", "values": {"sa_score": 1.58}, "equals_drawing": true,
     "alerts_equal_drawing": true}        the always-on descriptors the READER holds, against the same
                                          computed on the DRAWING (a conformer must leave every one the
                                          provider does not declare geometric alone); the geometric ones
                                          are reported and need `geometric_values`
    {"do": "pka_worker_report", "tag": "x"}  the pKa sidecar: state, pid, spawns, requests,
                                          its own startup/prediction times (never creates one)
    {"do": "ai_bridge_run", "calculator": "polar_surface_area", "parameters": {"pH": 7}}
                                          the assistant's calculator bridge in the REAL window: freeze a
                                          turn, prepare the request and, if it is automatic, call `run`
                                          from a worker thread as the tool loop would (give it `after_ms`)
    {"do": "ai_bridge_decide", "approve": true}   a person's Approve or Cancel on the pending preview
    {"do": "ai_bridge_expect", "expect": {"state": "completed", "has_number": true, "reads": [...],
     "not_run": [...], "problems": ["not_a_choice"], "route": "auto"}}  asserts what the last run did
    {"do": "ai_send", "text": "...", "script": [{"tool": "run_calculator", "input": {...}}, {"text": "..."}]}
                                          the assistant PANEL with a SCRIPTED provider: its real Send, the
                                          tool loop on its worker thread, the real host (give it `after_ms`)
    {"do": "ai_card", "action": "approve"}   press a REAL button on the preview card showing
                                          ("approve" | "cancel" | "open" | "dismiss"; add "card": "score" for a score
                                          the assistant PROPOSED, whose Approve is the only way it is saved)
    {"do": "ai_expect", "expect": {"ledger_contains": [...], "pending": 1, "service_previews": 1,
     "tool_results_contain": [...], "tool_results_exclude": [...], "tools_offered": [...], "notes": 1, "panel_visible": "Quantum_Chemistry",
     "score_proposals": 1, "scores_stored": 0, "scores_owner": [...], "sent_contains": [...]}}
                                          what the panel shows and what the model was told, asserted
    {"do": "lewis_pairing", "first": 0, "second": 1, "method": "B3LYP def2-SVP", "role": "acid",
     "press": "job:dscf_second", "expect": {"status": "partial", "jobs_to_do": 1, "panel_calc_type": "delta_scf"}}
                                          the Lewis pairing window (Tools menu) and its REAL controls: the form's
                                          combos, "choose" a run by id, "press" Keep or a job row's button (which
                                          asks for the Quantum Chemistry panel and starts nothing); `expect` reads the
                                          screen, the project's recipe runs and where the press went
    {"do": "recipe_results", "focus": true, "expect": {"entries": 1, "stale": 0, "title_contains": ["BH3 + CO"],
     "summary_contains": ["was edited"], "stored_as_results": 0}}
                                          what the Results READER holds of the recipe answers kept in the project, for the
                                          selected molecule: how many, how many stale, the line above the facts, and that none
                                          is also a stored result; `shot` takes "widget": "results_reader"
    {"do": "score_define", "label": "Polar window", "formula": "ramp(psa, 140, 60)", "inputs": [["psa", "descriptor:tpsa"]],
     "result_unit": "1", "constants": [], "defaults": [["logp", 3.5]], "expect": {"made": true}}      define a user-defined score through `ScoreService` (the call the
                                          definition dialog will make); a refusal is asserted with `"made": false, "problem": "unit",
                                          "message_contains": [...]` and must leave the project's scores as they were
    {"do": "score_results", "focus": true, "which": "Polar window", "expect": {"entries": 1, "has_value": true,
     "value_between": [0.95, 0.96], "evidence_contains": ["Formula:"], "reason_contains": [], "stored_as_results": 0, "defaulted": ["logp"]}}
                                          what the Results READER holds of the scores, for the selected molecule: the number or the
                                          reason there is none, the label, the evidence, and that none is also a stored result
    {"do": "score_dialog", "new": true, "fill": {"label": "Polar window", "inputs": [["psa", "descriptor:tpsa"], ["ob", "calculator:oxygen_balance:Oxygen balance (CO basis)", "-50"]], "formula": "ramp(psa, 140, 60)",
     "constants": [{"name": "hi", "value": "140", "unit": "\u00c5^2"}], "result_unit": "1"}, "press": "save", "confirm": "yes",
     "expect": {"ok": true, "marked": [], "preview_contains": ["For Aspirin: 0.955"], "stored": 1, "project_unsaved": true,
     "results_listed": ["Polar window"], "asked": ["Unsaved changes"]}}
                                          the Derived Scores window (Tools menu) driven through its REAL controls: `new`, `choose` a list entry,
                                          `fill` (presses Remove/Add and types into the edits, so it checks after every keystroke), `press`
                                          save/revert/delete/new (a disabled button is logged, not pressed), `confirm` answers its two questions;
                                          `expect` reads the window (message, `where`, fields outlined as `marked`, `pointer_column` of the caret, preview, buttons, list) and the project
                                          (definitions stored, unsaved, listed in Results); `shot` takes "widget": "scores"
    {"do": "table_scores", "export_csv": "C:/tmp/table.csv", "expect": {"columns": ["Polar window (user-defined, unvalidated)"], "note": "",
     "grid": {"Aspirin": {"Polar window": "0.955"}}, "tooltips": {"Aspirin": {"Polar window": ["Inputs: psa = 63.6"]}},
     "column_tooltips": {"Polar window": ["Formula:"]}, "csv_header_contains": ["Polar window"], "csv_cells": {"Aspirin": {"Polar window": 0.955}},
     "csv_text": {"Aspirin": {"inputs given a default": "ob"}}}}
                                          the user-defined SCORES in the Results dock's project table, read off the grid a person looks at (the exact score
                                          headers in order, the note under the status, what a cell SHOWS, tooltips) and off the file the REAL "Export CSV"
                                          button writes (the file dialog answered); pair it with `project_run` and `expect_project_table`; `shot` takes
                                          "widget": "project_table"; `"panel": "batch"` reads the Batch panel's OWN table (after `batch_fill`) and
                                          `shot` then takes "widget": "batch_table"
    {"do": "tick_score_inputs", "tag": "x", "expect": {"menu_label": "Tick what my scores read (2)", "calculators": ["oxygen_balance"], "descriptor_choice": null,
     "descriptors_box": true, "run_enabled": true, "status_contains": ["Ticked 1 calculator(s)"]}}
                                          the Presets menu's REAL "Tick what my scores read" entry in Properties (a menu with no such entry fails), asserted off the
                                          ticks, the always-on choice and the status line; `project_run` then takes `"keep_ticks": true` to run with the ticks as they are
    {"do": "qc_setup", "method": "HF STO-3G"}   set the Quantum Chemistry panel's method (and "calc_type") and press NOTHING:
                                          for a run something else starts, such as the Generate window's ORCA box
    {"do": "qc_wait", "timeout_ms": 600000}   hold the script until the Quantum Chemistry service has no job running (give up = an
                                          ERROR); use it after `qc_run` instead of guessing an `after_ms` for a job of unknown length
    {"do": "qc_panel_report", "tag": "fukui", "expect": {"calc_type": "Fukui functions (Hirshfeld)", "run_calc_type": "fukui",
     "run_status": "completed", "per_atom_outputs": 4, "results_contains": ["Largest f+"], "status_contains": []}}
                                          what the Quantum Chemistry panel SHOWS after a job (its Calculation entry, the results line, the
                                          status line) and what the newest stored run holds, asserted; `shot` saves the panel
    {"do": "fukui_gate_begin"}  {"do": "fukui_gate_record", "species": "CO", "level": "HF/6-31G**", "attempt": 1}
    {"do": "fukui_gate_floor"}  {"do": "fukui_gate_judge"}  {"do": "fukui_gate_report"}
                                          the Fukui GATE (benchmarks/fukui_gate/PREREGISTRATION.md; the scripts are generated by
                                          `benchmarks/fukui_gate/make_scripts.py`): `begin` ends the run before any job unless the noise
                                          floor is measured and usable; `record` appends what the newest STORED Fukui run says (its datasets,
                                          charge, method, ORCA version, and whether it ran on the ORCA-optimized geometry) as one attempt;
                                          `floor` is the largest difference between two runs that should agree; `judge` is `app/fukui_gate.judge`
                                          and writes the outcome beside the drive's own verdict (a FAIL of the gate is a result, not a broken
                                          script); `report` writes the reported arm, which never decides
    {"do": "fukui2_begin"}  {"do": "fukui2_record", "species": "phenol", "level": "B3LYP/6-31G*", "attempt": 1}
    {"do": "fukui2_floor"}  {"do": "fukui2_judge"}  {"do": "fukui2_report"}
                                          the SECOND Fukui gate (benchmarks/fukui_gate_2/PREREGISTRATION.md, arithmetic `app/fukui_gate_2.py`, scripts
                                          from `benchmarks/fukui_gate_2/make_scripts.py`): the first gate's steps widened for what v2 needs -- an
                                          anion's run holds ONE dataset, every record carries the provenance the judge checks (grid, functions, reference
                                          charge, starts, the commit and whether `src/` differs from it, acrolein's dihedral), and `floor` measures two
                                          floors (pyridine and formate) and uses the larger
    {"do": "lewis_gate_begin"}  {"do": "lewis_gate_floor", "a": -2, "b": -1}  {"do": "lewis_gate_pair", "bh3": -3, "bf3": -2, "co": -1}
                                          the Lewis pairing GATE (benchmarks/lewis_gate/PREREGISTRATION.md): `begin` ends the run before any
                                          job unless tolerance.json holds the tolerance the preregistered rule gives the recorded floor;
                                          `floor` measures the noise floor from two repeats of CO; `pair` judges BH3/CO and BF3/CO against
                                          the documented numbers. The gate was PASSED on 2026-10-13 (PREREGISTRATION.md section 9) and a decided outcome is final: do not re-run it to see whether the number moves
    {"do": "stage_report", "tag": "x", "expect": {"rows": {"torsion_table": "full", "oxygen_balance": null},
     "reader_header": "half", "reader_rows": 0}}   the support-stage STARS on screen: each Properties row's
                                          fill (full/half/empty, or none), its tooltip carrying the reason, the star beside
                                          "Showing" and how many reader rows carry one; read off the widgets
    {"do": "color_scheme", "scheme": "dark"}   Qt's light/dark override for THIS process ("unknown" hands it back);
                                          for a widget that borrows the palette
    {"do": "appearance", "choice": "dark", "via": "menu"}  choose the colour scheme through a REAL control ("menu" is
                                          View > Theme, "settings" the open Settings dialog's combo); read the result in a LATER step,
                                          the look settles a few milliseconds after the write. It writes the real stored choice: end a
                                          script on {"choice": "system"}
    {"do": "appearance_report", "tag": "x", "expect": {"effective": "dark", "choice": "dark", "editor_style": true,
     "viewer3d": "dark"}}                 the palette, the service's settled look, the stored integer, the checked menu entry, the open
                                          combo and each page's own state, asserted; the page reads are asynchronous (give it `after_ms`)
    {"do": "reader_filter", "text": "Donors"}  type into the docked reader's fact filter (it expands what it matches)
    {"do": "wait"} {"do": "quit"}

**A DRIVEN RUN ENDS IN A VERDICT, AND EXITS NON-ZERO WHEN IT FAILED.**
`src/openchem/app/drive_ledger.py` keeps every WARNING-and-above record the application
logs, de-duplicated by (logger, exception, innermost frame, message with its
numbers collapsed), and `quit` prints `VERDICT PASS|FAIL`, writes
`<script>.report.json` (`OPENCHEM_DRIVE_REPORT` moves it) and sets the exit
status: a driver failure (`no molecule selected`, `EXPECT ... FAILED`, a step
that raised), a failed `expect_*`, or an application ERROR nothing in `allow`
excuses all fail it. `{"do": "quit", "tolerate_errors": true}` opts out for a
script that provokes an error on purpose. **`expect_clean` IS NEVER A PASS ON ITS
OWN** -- an empty ledger is what a molecule that never ran the breaking code
also produces -- so pair it with `expect_results`. A scripted run writes its
own `drive-<pid>.log`, since two processes cannot share one rotating file on
Windows. The report records the run's identity (commit, script and lockfile
hashes, Qt/RDKit/Ketcher versions).

**`OPENCHEM_TRACE_WINDOWS=1` LOGS EVERY TOP-LEVEL WINDOW THAT SHOWS**, with
its class, its parent chain and a timestamp for every result event. It is
how the 1801 flashing windows were named; see the lesson. Pair it with
any drive script.

**`jobs_report` CARRIES A FLAG NO SCREENSHOT CAN**, which is why it exists
beside a `shot` rather than instead of one: both of the Jobs panel's
recorded defects live in `QTimer.isActive()` and neither is visible. A
panel that leaked itself polled for the life of the process; a visibility
gate that never restarts the timer leaves a frozen list that looks exactly
like an idle one. Switching to another right-hand panel IS the hide --
twelve docks, one visible at a time -- so no synthetic `hide()` is needed.

**`jobs_cancel` presses the BUTTON, not the handler behind it**, and here
that is load-bearing rather than stylistic: `_on_cancel_clicked` reads
which job it means off `sender()`, so calling it directly passes
`sender() is None` and proves nothing about the wiring, which is the thing
that changed.

**`select_atom` AND `selection_report` READ BOTH ID SPACES AT ONCE**, which
is why they exist beside a `shot` rather than instead of one. A selection is
a few highlighted pixels, and the failure they guard against is a
plausible-looking one: Ketcher's pool ids and the molfile's positions
diverge as soon as anything is deleted, so the two agree on a freshly
loaded structure and disagree on an edited one. `selection_report` prints
the pool order beside what is selected -- measured on `CCNCCO` with the
nitrogen erased, `poolOrder [0,1,3,4,5]` against positions `0..4`, and
asking for the oxygen at position 4 correctly reaches pool id 5 where
reading the position as an id would have selected a carbon.

`select_atom` drives the inspector's TABLE ROW, not the `select_atom()`
method behind it, for the reason `jobs_cancel` presses the real button: the
panel's own method is the INBOUND door the 3D viewer's click lands on, and
the path under test starts one step later.

**A MODAL DIALOG OPENED INSIDE A BUS HANDLER STARVES EVERY LATER
SUBSCRIBER**, and in a driven run it read as the Atom Inspector never
receiving the result. The calculator reveal used to `exec()` the Calculator
Inspector inside `EventBus._dispatch`; measured 2026-09-13, Properties held
`gasteiger_charge_at_ph` 67 s before the Atom Inspector did (at quit). Fixed
by `PropertyPanel._reveal_after_dispatch`. `inspector_report`'s `held=` is
what separates "not shown" from "never arrived"; `"reveal": false` keeps an
unattended run free of an open inspector window. (The inspector is modeless
now -- `_open_inspector` shows it, one window per result -- so a reveal no
longer blocks anything; the deferral stays because building the Chromium view
inside a dispatch is not free.)

**`erase` is the only step that drives the route `set_molecule` never
covers** -- the user drawing on the canvas -- so it is what any
calculated-annotation staleness has to be checked with. It goes through
Ketcher's own Delete hotkey, synthesised on the page. **A canvas edit
recomputes after the recalculation pause** (Settings > Recalculation, 800 ms
by default), so a script that reads results after an `erase` must wait the
pause AND the computation -- `after_ms` of a few seconds -- and results read
STALE in between, which is the point. Pair it with
`report`, whose `undo=` is how "did this display toggle quietly become an
edit" is answered: measured across a run, `baseline undo=2 -> labels-on
undo=2 -> after-edit undo=3 -> labels-off undo=3`.

**`receptor` DOES NOT SELECT WHAT IT ADDS EITHER, and that cost a run
that read as a bug in the code under test.** `molecule_combo.repopulate`
restores the previous pick by uuid, deliberately, so adding a second
receptor leaves the panel looking at the first. A script that adds one and
then dumps the box is still describing the OLD receptor -- which, when the
thing being checked is "does a derived box survive a receptor change",
reports the exact failure it was written to detect. `dock_receptor` is the
step that changes it; measured either side, the box goes
`(6.710, 2.210, 54.620) source=derived` -> `(0,0,0) source=none` -> back
again, and the Derive button stays ENABLED on the receptor with no
annotation because that structure still has ligands to box.

**`receptor` READS THE CACHE AND NEVER THE NETWORK.** A diagnostic run
that depends on RCSB being up is not a diagnostic. Populate the cache once
through File > Receptor Library; `_do_receptor` logs and skips if the id
is not there.

**`smiles` does NOT select what it adds**, and `conformers` and
`calculator` both act on the PANEL's selection -- so without a `select`
step they operate on whatever was already showing (the starter molecule,
which has no molblock) and the run fails with `has no molblock` as though
the structure were broken. `import` has the same shape, which is why the
example above pairs them.

`overlay` takes `gallery` and applies it AFTER the overlay, deliberately:
that is the gallery's FIRST render with requests already in flight, which
is the ordering the page's replay exists for and the one a script ticking
the gallery first would never reach. It logs what the PAGE drew per cell
(`drawnGridShapes`) and `gridBuilds`, not what Python believes it sent --
the distinction that whole feature turned on. Both are asynchronous, so
give the step an `after_ms` long enough for them to reach the log; a
probe issued in the same handler reads zeroes, correctly.

`after_ms` on any step is how long to wait before the next, which is how
an asynchronous calculator is waited on. Measured on the ADMET case: the
whole import-to-screenshot run is **55 seconds unattended**, with the
window sitting behind whatever Alex is working in. Nine molecules through
the Lewis dialog is about 25 seconds.

**A step that opens a MODAL dialog must not call `exec()`.** It spins its
own event loop inside the handler, so the next step is never scheduled
and an unattended run stalls on a window with nobody to close it -- the
same trap `quit()` set, one row down. `lewis` uses `show()`, which is the
only thing it does differently from a real click.

This is the real `MainWindow` with its real docks, fonts and DPI, which is
what the **six** "the harness said the opposite of the app" entries in
this file demand -- the count reached six at the starved-section entry,
which numbers itself. Only the INPUT is skipped.

**AND DRIVING IS NO LONGER ENOUGH ON ITS OWN: MAGNIFY THE SHOT.** The
width-clip work added three cases of an ADJACENT shape, counted
separately because they are not harness-versus-app disagreements -- the
whole panel suite was green, the in-app dump agreed with the code, and
the screen showed the defect at once: a value painted on top of its
caption, captions latched at `...`, captions collapsed to zero width.
`OPENCHEM_DRIVE` takes a `shot` step; cropping it 3x took seconds and
caught all three.

When a click really is needed, `spikes/gui_drive/drive.ps1` posts it to
the window handle rather than through the machine:

- `Save-AppShot` uses `PrintWindow(PW_RENDERFULLCONTENT)` -- captures the
  window while it is BEHIND other windows, and crops to the app instead
  of photographing the whole desktop. Verified with the app deliberately
  put behind Notepad++.
- `Invoke-AppClick -FromCapture` posts `WM_LBUTTONDOWN`/`UP` with
  coordinates read straight off that capture. Verified: it switched the
  right-hand panel while the app stayed in the background and the cursor
  never moved.
- `Assert-AppWindow` replaces the old "is the app in front" guard and is
  strictly better -- that one was a race, this asks whether the handle
  belongs to the expected pid, which cannot be.

Four things that cost a run each:

- **`quit()` closes all windows in Qt 6**, so a scripted run ended on a
  modal "Unsaved changes" box with nobody to answer it -- and removing
  the explicit `window.close()` changed nothing, because `quit()` was
  doing it. `exit(0)` leaves the loop without closing anything.
- **Skipping `closeEvent` is a feature.** It saves window geometry and
  dock state, so a diagnostic run would otherwise overwrite the layout
  Alex has arranged, every time.
- **Do not `Set-StrictMode` in a dot-sourced module.** It applies to the
  caller's session; here it broke the harness's own exit-code handling
  and read as a failure of a capture that had just succeeded.
- **A step that opens a window must not ACTIVATE it.** `MainWindow.show_scores()`
  raises and focuses the Derived Scores window, which is right for a person and
  wrong for a script on a timer: the keys a person types in another window next
  land in its Name field. Measured 2026-10-15: 2 of 15 driven saves ended with one
  stray letter in the label and a form that was "unsaved" (the cause of the one
  unexplained `score_dialog.json` failure); 0 of 15 once the driven open used
  `show_scores(activate=False)`. A new drive step that shows a window with text
  fields takes the same care, and the app still takes the foreground when a run
  starts, so type nothing into it in the first seconds.

## The regulatory rulesets -- work on them by rule id

`src/openchem/chem/regulatory/` screens a drawn structure against published
regulations and reports which one lists a matching substance and what
obligations may follow. It is a **detector**: the data holds recognition
patterns, each regulation's verbatim wording with a citation URL, and a
`legitimate_uses` field whose whole job is to stop the screen over-flagging
ordinary laboratory reagents. There is no synthesis, route, procedure or
yield information anywhere in it. The five rulesets under
`src/openchem/chem/data/regulatory/sources/` are hand-reviewed; everything
under `generated/` is machine-owned and must never be hand-edited.

**Reading these files is fine. Repeating their contents into a conversation
is what stops a session** -- a safety classifier fires on the vocabulary, and
it has stopped mid-sentence explanations of rules more than once. So:

- Refer to a rule by its `rule_id` (`cwc-1-a-1`, `dea-i-4`, `osha-z1-...`).
  Never by substance name, and never by quoting its expression or its
  `legal.quote`.
- Do not paste ruleset JSON into a message, a commit message, a PR body or a
  plan file. Point at `file:line` instead.
- To check the data is sound, run the four `tests/test_regulatory_*.py` files
  and the build's `--check`. Neither needs a JSON opened -- but **`--check`
  is not quiet**: measured 2026-10-20, a bare run prints 382 lines and most
  of them carry substance display names (OPSIN's parse warnings on stderr,
  and one `UNRESOLVED`/`skipped` line per unresolved entry on stdout). Run it
  filtered, which leaves the ruleset ids, the counts and the verdict:

  ```bash
  uv run --no-sync python tools/build_regulatory_rulesets.py --check \
      2>/dev/null | grep -vE 'UNRESOLVED|skipped'
  ```

  The verdict to look for is `matches its source, hash intact` on all five,
  and exit 0. Both halves matter: a hand-edited file still agrees with its
  source-document hash, and a stale file still hashes correctly to its own
  older content. pytest is quiet on its own (`186 passed`, no names).
- Open a data file only when a rule is genuinely being added or corrected,
  and then say what changed by id, not by content.

The graph is told to stop volunteering the contents, in
`.tokensave/queryignore` -- the data only, never the Python or the tests.
**`.tokensave/` is gitignored**, so a clone, a fresh worktree or another
machine has no such file until it is recreated there with these three lines:

```
src/openchem/chem/data/regulatory/generated/
src/openchem/chem/data/regulatory/sources/*.json
src/openchem/chem/data/regulatory/sources/*.xml
```

**The guard was measured, and `init` alone hides the data by accident.**
A/B'd on 2026-10-20 with a literal search for `ruleset_sha256`, re-indexing
in each state: 0 hits with the file, 5 without it, 0 with it restored. But
`tokensave init` does not index artifact-extension files at all, so straight
after an `init` the data looks safe whether or not the guard exists -- the
first `sync -f` is what indexes it, and only then does the guard do the work.
Do not read a fresh worktree's 0 as the guard working.

**The main checkout needs its own copy, and now has one.** The MCP server
resolves its root upward and serves `D:\Random Projects\OpenChem Studio`,
whose index did return these files' contents on an ordinary search until the
file was put there and the graph rebuilt on 2026-10-20 (the same probe went
from 5 data-file hits to 0, with the Python, the tests and the README still
indexed). `.tokensave/` being gitignored, no branch can carry this, so a new
machine or a re-created index needs it again:

```bash
cp .tokensave/queryignore "D:/Random Projects/OpenChem Studio/.tokensave/queryignore"
"D:/Claude Co worker/Token Save/tokensave.exe" sync -f "D:/Random Projects/OpenChem Studio"
```

Note the shape: `--project <path>` selects the project for `tokensave tool`
subcommands, but `sync` takes the path **positionally** and rejects
`--project`.

Permissions were deliberately left alone: a `deny` rule would also block
legitimate rule maintenance.

## Lessons (moved out of this file)

These were appended here after individual investigations. They live
in [`docs/LESSONS.md`](docs/LESSONS.md) and are **not** loaded on every
message — this index is. **If a title below names what you are
about to touch, read that section before you start.** Headings there
are verbatim, so grep the file for the line.

- THE SAME ENTHALPY IN FIVE BOOKS WAS ONE 1949 MEASUREMENT, AND THE NEWEST BOOK HELD THE OLDEST DATA
- A GUARD THAT SWEEPS EVERY TRACKED FILE LIVES IN A TEST FILE YOU DID NOT TOUCH
- ORCA COMPOUND INPUT: A LATER JOB'S GUESS KEYWORD BEATS MOREAD, A FAILED JOB ENDS THE RUN, AND HFTyp IS INHERITED
- RDKIT CONFORMER POOLS: SEED 0 GIVES ONE GEOMETRY N TIMES, A SYMMETRY-BLIND RMSD PRUNE KEEPS ROTAMERS, AND RAW ETKDG IS NOT A MINIMUM
- A BARE `import judge` RETURNED ANOTHER BENCHMARK'S FILE, AND ONLY A PROCESS THAT RAN BOTH SAW IT
- A CLASSIFIER STOPPED THE EXPLANATION, NOT THE FILES, AND THE FEATURE WAS BUILT THROUGH THE SAME ALERTS
- A MEASUREMENT MADE WITH THE LIBRARY DESCRIBED A STRUCTURE THE APPLICATION NEVER COMPUTES, AND A DECISION WAS TAKEN ON IT
- A MOLECULE THAT ARRIVED WITH A CONFORMER SHOWED ITS SHAPE DESCRIPTORS AS FAILED, AND THE OBVIOUS FIX LOST ITS OWN RACE 37 TIMES IN 40
- A CONFORMER RE-RAN THE WHOLE ALWAYS-ON SET ON ITS HYDROGENS, AND THE READER, THE PROJECT TABLE AND THE SAVED FILE ALL TOOK ITS ANSWER
- A SHARD THAT FIT ON A FAST RUNNER DID NOT FIT ON A SLOW ONE, AND THE FIRST TEN PERCENT OF THE TESTS SAID SO
- A PLUGIN PANEL OPENED AS A BARE RECTANGLE ON WINDOWS, AND NOTHING THE SUITE RUNS ON COULD SHOW IT
- TWO CLOSE COPPER CONTACTS LOOKED LIKE A COUNTEREXAMPLE UNTIL THE LIGANDS' FIT AND THE PAPERS' OWN WORDS WERE READ
- THE ACCESSIBLE SURFACE WAS COMPUTED WITH A RADIUS OF ZERO FOR EVERY ATOM, AND EVERY TEST COMPARED ONE MOLECULE WITH ANOTHER
- A WORKFLOW IN A SCROLLED LIST WAS GIVEN HALF THE HEIGHT IT ASKED FOR, AND EVERY WIDGET REPORTED A SENSIBLE SIZE
- THE NOTE COUNTED FIVE EXAMPLES AND THE BOOK PRINTS FIFTEEN, AND THE RULE'S FIRST WRONG NAME WAS A TREE IT HAD NEVER BEEN OFFERED
- A RE-PIN CANNOT BUY HEADROOM THE SUM DOES NOT HAVE, AND THE WEIGHTS MODELLED THE SMALLER HALF OF A SHARD'S COST
- A GROUP'S BONDING NUMBER AND A PREFIX'S NUCLIDE WERE IN NO TABLE, AND THE APP'S READ-BACK HID BOTH
- A STABLE NAME IS NOT THE NAME THE RULE CHOSE, AND THE STABILITY PROBE WROTE A DIFFERENT MOLECULE
- SIXTEEN CORRECT NAMES OF ONE MOLECULE, AND THE DEFECT WAS THE CHOICE BETWEEN THEM
- A TARGET LABELLED "NOT CHECKED AGAINST THE BLUE BOOK" WAS THE BOOK'S NON-PIN NAME
- TWO FAILED ROUTES WERE WRITTEN UP AS "IMPOSSIBLE", AND THE FEATURE THE NOTE ASSUMED WAS NOT THERE EITHER
- A TYPO PARSED AS "NO SHORTCUT", TWO ACTIONS ON ONE KEY RUN NEITHER, AND A GATE'S THREE CRASHES IN A ROW WERE LUCK
- THE FIRST FIX CHECKED THE DISPATCH, THE PAGE HAD NO DIALOG, AND THE SECOND FIX ARMED A TOOL AND CHANGED NOTHING
- THE STORE KEPT ONE RESULT PER CALCULATOR, WHICH WAS THE REAL REASON COMPARING METHODS WAS HARD
- A DEBOUNCE TURNED "CLOSE ENOUGH" INTO A WRONG ANSWER, AND THE PROFILE FOUND TWO COSTS NOBODY HAD NAMED
- A CRASH WAS LOGGED FIVE TIMES AND NOTHING FAILED, BECAUSE NO RUN ASKED WHAT THE APP SAID
- A REFUSAL WAS CORRECT AT THE SERVICE AND "FAILED" ON SCREEN, BECAUSE THE PANEL FILES A SUMMARY
- THE ORACLE READ EVERY MISSPELLING, AND SIX DEFECTS WERE IN NO CORPUS ROW
- A ZERO-OWNER HOLE BETWEEN TWO GUARDS, AND AN INVARIANT THAT COULD NOT SEE THE WRONG MOLECULE
- NO CALCULATOR HAD BEEN ASKED WHICH COMPONENT OF A SALT IT DESCRIBED
- A CATEGORY ID PRINTED AS A VALUE IN TWO VIEWS, AND A LABEL OVER THE WRONG COLOUR
- THE ORACLE'S IMPLEMENTATION WAS NOT ITS PAPER, AND IT STILL FOUND TEN THINGS
- A RECURSIVE SMARTS ON AN ATOM IS SATISFIED BY ITS NEIGHBOUR IN THE PATTERN, THREE TIMES IN ONE BRANCH
- A FALLBACK NOBODY TAKES CANNOT BE TESTED THROUGH THE PIPELINE, AND THE SOURCE SCAN HID THAT
- A RING TABLE AND A DRAWING BOTH GAVE MIRROR-IMAGE NUMBERS, CONFIDENTLY, AND NOTHING RAISED
- A TEST FILE THAT CONSUMES NAMES SAT RED FOR SIX STAGES, BECAUSE EACH STAGE RAN ONLY THE NAMING TESTS
- A CONFORMANCE CHECKER WAS WRONG TWICE, IN OPPOSITE DIRECTIONS, BEFORE IT AGREED WITH THE BOOK
- A SHARED TEMP FILE MADE CORRECT NAMES LOOK UNPARSEABLE, AND IT WAS THE FLAKE ALL SESSION
- A TABLE NAMED `retained_pins` WAS A PARSER'S VOCABULARY, AND A CITATION IS NOT EVIDENCE
- THREE ENTRIES NAMED THE WRONG MOLECULE, AND ONLY A DUPLICATE REVEALED THEM
- A RULE FOR "THE PREVIOUS METHOD" MEANT ONE PREVIOUS METHOD, AND V3 MADE TWO
- A HELD-OUT SET FOUND A WRONG MOLECULE ON ITS FIRST RUN, BECAUSE A CORPUS CANNOT TEST WHAT IT WAS BUILT FROM
- FOUR DEFECTS THAT LOOKED LIKE ONE WERE IN FOUR LAYERS, AND THE REFACTOR THAT WOULD HAVE FIXED THEM FIXED NONE
- ADDING A TEST FILE RE-BALANCES THE SHARDS, SO MASTER'S GREEN HISTORY IS NOT YOUR SHARD'S
- A NAME THAT PARSES BACK IS NOT A NAME THAT IS RIGHT, AND FOUR DEFECTS SAT BEHIND THAT
- TWO PRODUCERS, ONE RESULT ID, AND A PANEL THAT ANSWERED ONCE
- DRAWN IS NOT ON SCREEN, AND THE PAGE'S OWN REPORT SAID DRAWN
- THE MICROSPECIES WAS COMPUTED AND DISCARDED, AND A REGISTERED FIELD WAS NEVER WRITTEN
- A GREEN PYTEST SUMMARY AND A NON-ZERO EXIT: THE SAME WINDOWS CRASH, WEARING THE ONE SHAPE NO DIAGNOSTIC CATCHES
- A TRUNCATED LATTICE SUM IS NOT INVARIANT TO MOVING ONE ATOM, AND THE CIF CANNOT CARRY WHAT THE SOURCE USED
- A QA ASSERT INSIDE AN OPTIMISER DISCARDED 18 JOBS, AND A SIGN CHANGE WAS NOT A ROOT
- A GATE THAT FAILED STAYS FAILED, AND QEQ SHIPPED UNDER A NARROWER CLAIM
- A PRINTED CHARGE THAT IS NOT A SOLUTION, AND A SECOND PAPER'S TABLE THAT DOES NOT SUM
- A TABLE CAN CHECK ITS OWN TRANSCRIPTION, AND QEQ'S HYDROGEN NEVER CAME BACK
- A ROW KEPT THE HEIGHT ITS TEXT NEEDS AT 100 PX, BECAUSE QLABEL FLOORS ITS OWN ANSWER
- A CALLER'S ATOM MAPS REACHED THE LIBRARY, AND THE ORACLE HAD TO AVOID THE RULE IT TESTED
- A FOOTNOTE ON THE NEXT COLUMN IS NOT A FLAG ON THIS ONE
- A SETTING EXPOSES WHAT ITS DEFAULT HID, AND ENTER PRESSED A BUTTON NOBODY CHOSE
- THE SMILES ROUND TRIP DROPPED THE INDEX SPACE, AND ATOM MAPS WERE THE WRONG REPAIR
- OPEN BABEL'S QEQ HAS THE WRONG SIGN, AND THE FIRST DIAGNOSIS NAMED TWO WRONG CAUSES
- A PARTIAL RESTORE IS NOT A CACHE HIT, AND THREE DEFECTS ONLY RUNNING FOUND
- A RE-RENDER OPENED 1801 WINDOWS, AND ONLY A TRACE COULD NAME THEM
- A MATCHING COUNT IS NOT A REPRODUCTION, AND A PAPER'S SILENCE IS NOT A TERM
- A THIRD OF THE SUITE WAS IN NO TEST, AND THE TABLE JUSTIFYING IT WAS WRONG IN EVERY CELL
- THE DRIVEN CHECK CAN ASSERT NOW, AND THREE EYE-ONLY DEFECTS BECAME TESTS
- A RATCHET IS NOT A MIGRATION, AND CALLING THIS ONE A MIGRATION WAS WRONG
- THE HELP CONTRACT: a tooltip is a RENDERING, not the thing itself
- BATCH WAS A SECOND IMPLEMENTATION OF WHAT PROPERTIES ALREADY DID
- THE VIEWER AND THE DOCKING WERE SHOWING DIFFERENT CHAINS
- THE ALIGNMENT COULD NOT MOVE A TORSION, AND THE RMSD COULD NOT SAY SO
- POPPING A VIEW OUT: the widget MOVES, and that was measured first
- A HORIZONTAL ROW'S MINIMUM IS THE SUM, and it set the whole window's
- A PANEL THAT LEAKS ITSELF AND THEN POLLS FOREVER
- OPEN BABEL HAS NO DATA FILES ON WINDOWS -- THE PLATFORM THIS SHIPS ON
- THE LINUX JOB COULD NOT NAME ITS OWN VICTIM, AND THE DATA WAS ALREADY THERE
- THE LINUX SUITE CRASHES ON 4 OF 6 COMMITS, AND THE INSTRUMENT NEEDED FIXING TWICE
- TEN CENSUS-NAMED CRASHES, TWO FILES, AND THE COUNTER-EXAMPLE CAME ON A BYTE-IDENTICAL TREE
- A RED SUITE SILENTLY DISABLES EVERY GATE BEHIND IT
- A WINDOWS RUNNER HANDS A BASH SCRIPT TO POWERSHELL
- A FORMULATION IS NOT A MOLECULE, AND THE COMPONENTS ARE EACH REFUSED
- A POWDER PATTERN'S POSITIONS SHIP AND ITS INTENSITIES ARE REFUSED
- A DECISION WAS REVERSED ON PRODUCT GROUNDS, AND THE RECORD SAYS SO
- GELL-MANN--NISHIJIMA IS THE CHECKSUM ON A HAND-ENTERED TABLE
- THE PDG SUPPLIES ITS OWN COUNTEREXAMPLE, WHICH IS THE WHOLE DESIGN
- A NEUTRAL LIGHT MESON IS A SUPERPOSITION, AND THE SOURCE PRINTS IT
- THE PDG WAS FETCHED, READ AS A PDF, AND CROSS-CHECKED
- THE DIALOG OPENED ON A DELTA++ AND EVERY TEST PASSED
- A DRIVE STEP THAT DRIVES THE CONTROLS, NOT THE FUNCTION BEHIND THEM
- FILE DIALOGS REMEMBER WHERE YOU WERE, AND `QFileDialog` IS PATCHABLE
- THE RECEPTOR WAS PREPARED AT pH 7.4 AND THE LIGAND AT NEUTRAL
- THE ANCHOR RESIDUE IS NUMBERED DIFFERENTLY IN THE TWO STRUCTURES
- THE BOX WAS NOT THE PROBLEM, AND THE FIRST MEASUREMENT SAID IT WAS
- THE STORED RESULT WAS A PLAUSIBLE-LOOKING LIE
- CASF-2016 SPLITS THE ANSWER, AND IT IS THE ANSWER TO THE REPORT
- EXHAUSTIVENESS 25, AND THE NUMBER WAS REVISED ON READING THE SOURCE
- `flow_row` IS NOT A FREE SUBSTITUTION FOR A TWO-CHILD `QHBoxLayout`
- A REVIEW'S CITATION DID NOT RESOLVE TWICE, AND I CALLED IT FABRICATED
- `Read` CANNOT OPEN A PDF HERE, AND THE THROWAWAY VENV IS THE ANSWER
- A SCORE IS ONE DRAW, AND THE PANEL PRINTED IT TO TWO DECIMAL PLACES
- MASTER CRASHES IN THE SAME TWO TESTS, AND THAT IS THE ATTRIBUTION
- A SECOND SCORE ON A POSE, AND THREE WAYS TO SHIP A WRONG NUMBER
- A P-VALUE LOOKED AT REPEATEDLY IS NOT A P-VALUE, AND MINE CROSSED 0.05 AND CAME BACK
- REPRODUCIBLE SEARCH PLUS NO CORRELATION IS THE STRONGEST NULL AVAILABLE
- WIDENING A CORPUS AFTER A MARGINAL RESULT IS CORRECT, AND MUST BE PRE-COMMITTED
- A SCREEN COULD NOT BE PINNED EVEN IN PRINCIPLE, WHILE A SINGLE DOCK COULD
- A REFUSAL THAT NAMED ITS OWN UNBLOCKING CONDITION, UNCHECKED FOR TEN DAYS
- THE RANKING CORPUS WIDENED OFF THE GPCRs, AND THE ENDPOINT EXCLUDED TWO CLASSES
- A CHART IS DECLARED, AND THE MERGE KEEPS WHAT EACH PRODUCER DECLARED
- THE ION IS A COMPOSITION, AND POTASSIUM IS WHY
- SIX DEFECTS THE DRIVEN APP FOUND WITH 1006 TESTS GREEN
- A GUARD RED FOR A REAL REASON: a category holding one calculator
- THE ISOTOPE FOLD WAS EXPONENTIAL IN THE ATOM COUNT
- "EXACT" WAS THE ARITHMETIC AND THE CONTRACT SAID FINE STRUCTURE
- A UNIT IN BOTH FIELDS AND A UNIT IN NEITHER, AND THEY PARTITIONED PERFECTLY
- THE POWDER PATTERN REACHED THE CHART CHANNEL, AND TWO COMMENTS WERE LYING
- A SECOND CHART KIND, AND ONE RENDERER FOR CURVES
- A DEPICTION, FROM THE LAYER TYPE THAT ALREADY EXISTED
- THREE GUARDS I WROTE MATCHED THE PROSE EXPLAINING THEIR OWN RULE
- A HELP-CONTRACT FIXTURE THAT COULD NOT BE BUILT WAS SKIPPING 5 CONTROLS
- A `"choice"` PARAMETER STORED THE ENGLISH ON THE SCREEN, IN THE CACHE KEY
- A HEADER OVERFLOWS; A CELL ELIDES. AND THE ORACLE SEES NEITHER
- `batch_service` READS AN EMPTY SCOPE AS "EVERYTHING GIVEN"
- TESTING A HELPER IS NOT TESTING THE WIRING -- TWICE MORE, BOTH MINE
- A COMMITTED DRIVE SCRIPT DID NOT CONSTRUCT ITS OWN STATE
- A BLANK LINE IN A REPORT IS A ROW WITH NO VALUE
- MEASURE THE POPULATION BEFORE DESIGNING FOR IT
- A LIMIT IS A NUMBER PLUS WHAT IT IS A LIMIT ON, AND FOUR WAYS THAT GOES WRONG
- THE RESULTS LIST FOLLOWED WHICHEVER CALCULATION FINISHED FIRST
- A READER'S POSITION HAD NEVER HAD TO SURVIVE ANYTHING
- THE READER CONTRACT WAS FOUR NAMES AND THE READER READ NINE
- HALF THE APPLICATION'S OUTPUT COULD NOT REACH THE READER
- A SUMMARY WITH NO WAY BACK TO THE RESULT IS A DEAD END
- TWO SEARCHES, AND ONE BOX OVER BOTH CANNOT SAY WHAT IT MATCHED
- A SHAPE-VALUED RESULT WAS A DIFFERENT-SHAPED, MODAL WINDOW
- A READER THAT FOLLOWS THE SELECTION CANNOT BE A DIALOG
- RESULTS IS A PANEL NOW, AND ONE PANEL AT A TIME IS WHY THE POP-OUT IS LOAD-BEARING
- ONE READER, AND "DETAILS..." REACHES IT WHEREVER IT IS
- THE LAUNCHER HAS TO SAY WHETHER THERE IS ANYTHING TO READ
- EMPTYING THE LAUNCHER IS HOW YOU FIND OUT WHAT ONLY THE LAUNCHER SAID
- THE 41 DESCRIPTORS LEAVE, AND EVERY CLAIM THEY CARRIED ALONE GOES RED
- A CONTRACT FOLLOWS THE VALUE, NOT THE WIDGET
- A MERGE HAS EXACTLY ONE POSSIBLE TARGET, AND THE DATA MODEL SAYS WHICH
- A REFERENCE OVER 68 CALCULATORS IS 68 PLACES TO FORGET
- THE POOL-ID TRAP IN REVERSE, AND THE LOOP IT CLOSES
- THE REASON EXISTED, IN A BATCH CELL, AND THE READER NEVER READ IT
- A MODE WITH ONE WAY IN, AND TWO WRONG WAYS TO GIVE IT A SECOND
- A PICTURE THAT COULD BE READ AND NOT TAKEN AWAY
- A MODE WHOSE EXIT DELETED THE ONLY WAY OUT OF IT
- THE TIDY ACTION THAT CHANGED THE COMPOUND
- THE CONFORMER COUNT MOVED BECAUSE NOBODY HAD PINNED THE DRAW
- A FEATURE THAT EXISTED, UNDER A NAME NOBODY WOULD LOOK FOR
- THE COST OF AN OPSIN CALL IS THE JVM, NOT THE PARSE
- Running the tests
- RESONANCE: four things measured before the Lewis diagram was built
- The naming benchmark
- Ketcher CAN report atom AND bond selection, with one trap
- SHAPE-VALUED RESULTS DRAW THEMSELVES, and what that took to make honest
- The bond and molecule reports, and what generalising cost
- A new panel needs a help topic, and nothing was checking
- A DOC GUARD THAT CHECKS CITATIONS CANNOT CHECK CLAIMS
- A blocklist of category NAMES rots; a declared capability does not
- The presentation layer, and four things measured while fixing it
- A UI MUST NOT INFER SCIENTIFIC MEANING FROM A DATASET'S SHAPE
- SOLUBILITY: an uncapped model, a 1000x review, and two defects only the screen showed
- SOURCES: a provenance registry, and two traps in building one
- A PANEL THAT DREW TWO THIRDS OF AN ANSWER AND SAID NOTHING
- THE CRC OVERTURNED THE REASON IT WAS OPENED
- A BETTER LAYOUT ENGINE THAT IS WORSE ON THE REPORTED MOLECULE
- THE MUTATION STEP EARNED ITS KEEP SEVEN TIMES IN ONE BRANCH
- AND TWO DEFECTS ONLY THE MAGNIFIED SHOT FOUND
- NUCLIDES: what the isotope and decay work cost
- FIVE THINGS TO KEEP DISTINCT IN A SCIENTIFIC CALCULATION
- SHIPPED IS NOT REACHABLE, AND THE GUARD FOR IT HAD THREE BLIND SPOTS
- "25 COLLAPSIBLE CATEGORIES" WAS 20, AND MEASURING IT FOUND A 21st
- SHIPPED IS NOT REACHABLE, AND FOUR MODULES PROVED IT
- `variants[0]` WAS NOT A RANKING, AND THE ORDER CAME FROM THE HASH SEED
- A CORRECT NUMBER THAT READS AS A WRONG ONE
- A WORKFLOW REPLAYED PERFECTLY LOCALLY AND COULD NEVER HAVE RUN: GITHUB WITHHOLDS SECRETS FROM DEPENDABOT
- A REFUSAL IS NOT A FAULT, AND THE STYLE'S OWN COMMENT SAID SO
- GASTEIGER'S OWN TABLE 3 IS AN ORACLE, AND IT AGREES
- A ROUND TRIP can pass without exercising what it is named for
- A docking A/B needs a pinned seed AND its own noise floor
- A whole CORPUS can be degenerate, and then size proves nothing
- Open Babel reads mmCIF elements CASE-SENSITIVELY, and the archive is uppercase
- A threshold fitted to a BIMODAL molecule is not validated
- Two empirical fits can CROSS, so one test point proves nothing
- Normalise the DRAWING, do not fork the vendor
- A threshold with two measured bounds is not a taste question
- A library DEFAULT can be a different quantity, not a tuning knob
- Bound the grid, not the resolution
- A derivative can be self-consistent, symmetric, and wrong
- A conformer search result is part of the question, not the setup
- Koopmans hardness is wrong for the pair people actually use it on
- ORCA ABORTS AT STARTUP IF ITS OWN PATH USES FORWARD SLASHES
- A KILLED PROCESS STILL OWNS ITS WORKING DIRECTORY, and cleanup was silent about it
- A gbw remembers where it was born, and orca_plot goes there
- ORCA's LED summary block does not mean what it looks like it means
- An engine and its own data table have to be run against each other
- The two orbital measures disagree on the motivating case
- Alex has the paywalled papers. Ask before hedging around one.

## Books and papers: use the facts

Measured values, short runs of values from one cell, spreads, units, temperatures and forms are
**facts**: read every held book, handbook and paper for them (`D:\Xaero Stuff\Documents\Sci Downloads`,
`tools/library_index.py`) and **quote them with source and page** in the committed docs and JSON. Do not
withhold them, and do not write "counted only", "not read" or "not held" without having looked. What stays
out of git is a whole table or page reproduced, running prose, figures, and a **bulk extracted corpus**
(hundreds of rows, such as Phase A's handbook corpus, which is built beside the library and was used in
full). A value in a committed file carries `value_kind`, temperature, form, page and lineage, and a row's
value is a short cell, not a table. Older wording in the Phase A preregistration (frozen) and in the
energetic-materials draft's section 7 ("books are not committed", "no per-compound values from a
copyrighted table") describes where a bulk corpus lives; it is not a reason to skip a source or to omit a
fact. Owner's instruction, 2026-10-26.

## Verification standard

This project's convention, established across many sessions: **claims are
measured, not asserted.** Before shipping a formula, a threshold, a parser
regex or a model, verify it against a primary source or a real run and record
what was checked. Several things were deliberately NOT shipped because they
could not be validated (Miller polarizability, HLB, TSEI) — that is a normal
outcome here, not a failure.

Comments explain **why**, especially where something is non-obvious or was got
wrong once. A comment restating the code is noise.
