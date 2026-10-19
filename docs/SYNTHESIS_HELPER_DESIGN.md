# Synthesis helper: design and spike record (2026-10-19)

Status: **Stage 0 (the spike) in progress; no application code; Stage 1 is not authorized until this note records a GO.** The last item of Phase 4 of the suite roadmap. The approved plan is rev 3 (kept with the session's plan file); this note is its durable record and takes the results as the spike runs.

## What it is, and what it is never claimed to be

Given a target molecule, an **optional external planner** proposes multi-step routes; OpenChem adds its own annotations to every molecule in a route. Standing rules: claims are measured, not asserted; "measured, not shipped" is an accepted outcome; **"no route found within the configured search limits" is a valid answer**; **a returned route is a hypothesis**, never a validated or feasible synthesis. A policy probability is the planner's number and not a measured chance a reaction works; a route score ranks, it does not predict feasibility; "in stock" is a match to a catalogue snapshot, not availability or legality to sell.

## Decisions (Alex, 2026-10-19)

1. **First planner to spike: AiZynthFinder.** Not committed to shipping it: if licence, Windows install or quality fails, the spike records NO-GO and names the next candidate (Syntheseus, or a small in-house RDKit/rdchiral template planner).
2. **Locate-only install**: the app never fetches anything (as Psi4). A download button is a later stage with pinned URLs and checksums, if ever.
3. **Regulated targets: routes are shown with an alert, with one exception.** No planning starts for a target matched to a **CWC Schedule 1** entry (the shipped `cwc-schedule-1` ruleset); the refusal names the reason. DEA listings, CWC Schedules 2 and 3 and everything else are alert-only.

## What was verified against the source

* **AiZynthFinder 4.4.1** (`pyproject.toml`, master, fetched 2026-10-19): Python `>=3.10,<3.13`; `numpy <2.0.0`; `onnxruntime ^1.23.0` required; TensorFlow only in the optional `tf` extra; console scripts `aizynthcli`, `aizynthapp`, `download_public_data`, `smiles2stock`, `cat_aizynth_output`. **The user's planner environment is therefore a separate Python from OpenChem's.**
* **No random-seed setting** appears in the README; the search settings include `max_transforms`, `iteration_limit`, `time_limit` (default 120 s) and `return_first`. The noise-floor design (an `iteration_limit` budget, repeated identical runs) follows.
* **In this repository:** `chem/isotopes.py` `same_structure` exists (merged); `RegulatoryEngine.screen(mol, jurisdictions, include_near_misses, as_of)` returns a `ScreeningReport` whose findings carry `ruleset_id` and `rule_id`, and the Schedule 1 ruleset id is `cwc-schedule-1`.
* **Gaps in the first plan, found by reading the code, and how the plan closes them:**
  * **The shared regulatory engine includes user rulesets** (`calculator._shared_engine()` calls `load_all()` with `include_user=True`, and `add_ruleset` honours `supersedes`), so a user file could supersede `cwc-schedule-1`. **The gate builds its own engine from `load_all(include_user=False)`** and, if `cwc-schedule-1` is missing, has load problems or screening raises, reports `unscreened` and plans nothing. The ruleset's own `known_limitations` (ricin and saxitoxin not encoded; size limits over-report and never under-report; "corresponding alkylated salts" not matched) travel with every refusal: the gate is a list match, not a guarantee.
  * **The reaction-prediction plugin cannot reach a service** (top-level `plugins/reaction_prediction/`, narrow `PluginContext` namespaces only). Stage 1 adds a narrow `context.synthesis` handle, modelled on `PluginCalculations`.
  * **Nothing draws a reaction**, and `ui/` may not import RDKit. Stage 1 adds a `chem/` reaction-SVG function.
  * The bridge's service-run class (`PREVIEW_ONLY` exists in `domain/calculation_bridge.py`) is checked again when the assistant tool is built.

## Stage 0 results

### 0a. Licences (read from each project's own files and records, 2026-10-19; reported separately)

| What | Where | Terms as stated | Size |
|---|---|---|---|
| **Planner code** | `github.com/MolecularAI/aizynthfinder`, `LICENSE` on master (4.4.1) | MIT: the file's only identifying line is "Copyright 2020 Samuel Genheden and Esben Bjerrum" and the text is the standard MIT grant and disclaimer; it carries no "MIT License" heading, so the name is read from the text. The README adds "licensed under the MIT license ... free and provided as-is". | |
| **Policy and filter models (ONNX)** | Zenodo record 7797465, "USPTO-based ONNX models" (Saigiridharan, 2023-04-04, DOI 10.5281/zenodo.7797465) | **CC-BY-4.0**, open access. The record says only "the USPTO models converted as ONNX"; **it does not say what they were trained on beyond "USPTO"**. | `uspto_model.onnx` 91.5 MB, `uspto_filter_model.onnx` 16.8 MB, `uspto_ringbreaker_model.onnx` 15.0 MB |
| **Templates** | Zenodo record 7341155, "PaRoutes 2.0 and USPTO-based models" (Genheden, 2022-11-22, DOI 10.5281/zenodo.7341155) | **CC-BY-4.0**, open access | `uspto_unique_templates.csv.gz` 3.3 MB, `uspto_ringbreaker_unique_templates.csv.gz` 0.37 MB |
| **Stock** | Figshare article 12334577 ("AiZynthFinder: a fast, robust and flexible open-source software for retrosynthetic planning", Genheden, Chadimova, Engkvist, 2020-06-11), file `zinc_stock_17_04_20.hdf5` | The **record's licence field is MIT**; its description says the file is a "stock file made from the ZINC database on 17 April 2020". **ZINC's own terms for that content were not read**, and "in stock" means a match against a 2020 snapshot. | 663.2 MB |
| **Training data** | USPTO reaction extraction, as the models' own records name it ("USPTO") | **Not read**: neither record states the data's licence or provenance beyond the name | |
| **Benchmark/route data** | Zenodo 7341155 (PaRoutes 2.0: `ref_routes_n1.json` 64 MB, `ref_routes_n5.json` 82 MB, `targets_n1.txt`, `targets_n5.txt`, `stock_n1.txt`, `stock_n5.txt`, reaction hashes) | **CC-BY-4.0** as the record states; the PaRoutes paper itself has not been read | targets and stocks under 0.5 MB each; routes 64 and 82 MB |

What the table says and does not: a code licence says nothing about the data, and each data record states its own licence field but **none says what the USPTO extraction it derives from permits**. Locate-only means OpenChem redistributes none of it, but the user's install (below) pulls it all, and the note a user sees must say that. `download_public_data` fetches the six files above from Zenodo (models, templates) and Figshare (stock); **the default install is about 790 MB of data plus an environment with onnxruntime**, to be measured exactly under 0b.

### 0b to 0e: not started

Next, in order: read the AiZynthFinder paper (J. Cheminform. 2020, 12, 70, DOI 10.1186/s13321-020-00472-1) and the PaRoutes paper for the planner's own published accuracy and the route-set definitions; **ask Alex before any install or download** (hundreds of MB, a new Python environment); then 0b (Windows install, sizes, cold start, cancel, path cases), 0c (raw fixtures from 3 to 5 small targets), 0d (route validator and its tests), 0e (the preregistration, with thresholds approved by Alex after the papers' numbers are read), then the runner, tested and committed and not run until Alex says so.

## Stage 1 (only on a GO)

As the approved plan: route domain, internal provider seam, the runner and parser, `SynthesisPlanningService`, the regulatory gate in the shared service path, per-node annotations, the locate-only External Tools tab, the UI with `context.synthesis` and the reaction-SVG function, the confirm-gated assistant tool, docs and registries. Each slice its own PR; the external process isolated throughout (the pKa runner pattern); nothing merged without Alex's go.
