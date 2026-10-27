# External tool candidates

An inventory, dated 2026-10-27, of open-source tools that could join the pattern Vina, ORCA, Psi4 and AiZynthFinder already follow: located by the user, tested, measured, and labelled with their limits. It is a **provisional triage**, not a vetting. Nothing here is built, installed or scheduled, and no tool below is chosen.

Facts marked "page" were read from the tool's upstream project page on 2026-10-27; a page that did not state something is recorded as unknown. Licences and Windows status must be re-checked against the exact release before any tool is promoted.

## What already exists

Searched the code graph (`src/`, `docs/`, `tests/`, `tools/`, TOML manifests): xtb, CREST, smina, gnina, Meeko, RXNMapper, Mordred, PySCF and Gypsum-DL have no code or manifest reference. Not searched: about 850 tracked json/csv/txt/out files the index does not cover, the user's runtime environment, bundled binaries.

- `ARCHITECTURE.md` already says the docking seam sets up cleanly for smina, gnina and QuickVina: anticipated, not built.
- The Syntheseus paper (`maziarz2025syntheseus`) is a reference-only source in `sources.toml`; the software is not integrated.
- Dimorphite-DL is already in use.
- The seams a new tool would use: `QuantumEngineProvider` (`src/openchem/plugins/interfaces.py`, ORCA and Psi4 sit behind it), the External Tools catalog (`ManagedExecutable`), the AiZynthFinder runner (own-Python child process, gate, parser, benchmark protocol), and Vina's docking panel.

## Needs and candidates

| Need | Today | Candidate |
|---|---|---|
| Cheap approximate quantum chemistry (opt, frequencies) | ORCA, Psi4 | xtb |
| Conformer ensemble quality | RDKit ETKDG (known not to give minima) | CREST |
| Reaction atom mapping | validator reports mapping absent or partial when the planner omits it; how often is not measured | RXNMapper |
| Second retrosynthesis search | AiZynthFinder only (protocol 3: 13 of 51) | Syntheseus plus a chosen model |
| Docking pose trust and prep | Vina | PoseBusters-style check, Meeko, gnina |

## Source-checked facts

| Tool | Class | Found | Unknown or flagged |
|---|---|---|---|
| xtb | executable, engine | v6.7.1 latest (page). Windows zip is named `6.7.1pre`; notes say it omitted C-API tests (xtb, CPCM-X) and uses an older dftd4 | licence not on the page (upstream README is said to give LGPL-3.0-or-later: confirm); Windows smoke test; fit to the provider contract per operation |
| CREST | executable, ensemble search | LGPL-3.0-or-later in the README, GPL-3.0 file also in the repo. Prebuilt static builds are Linux, plus conda-forge; no Windows binary mentioned; no tagged releases, only a rolling "latest". tblite integrated, xtb still needed for QCG | Windows route; licence of the actual build. Not an engine: belongs behind a conformer workflow |
| Syntheseus | Python framework | MIT (framework). Wrappers for several reaction models, each an optional install; sample environment pins torch 2.2.2 | which model, its weights licence, its stock; an adapter into `RouteSet` is still needed |
| RXNMapper | Python library and model | MIT. Returns mapped SMILES and a confidence; invalid input returns empty | torch/model burden and weights licence not stated. A mapping is inferred, never a proof of conservation |
| smina | executable | page found is a private fork; upstream is on SourceForge. Apache-2.0 and GPL-2.0 files; Linux builds | provenance, licence scope, Windows |
| gnina | executable, CNN weights | v1.3.3 latest; 1.3.2 notes require cuDNN 9 and a separate CUDA 12.8 build for new cards | Windows, licence, weights terms, whether GPU is optional |
| Meeko, PySCF, OPERA, Mordred, PaDEL, Gypsum-DL, ASKCOS, ReactionT5, Chemformer | various | not fetched. PySCF's own docs are reported to say native Windows is unsupported | verify only if promoted |

None would be bundled in a first pass: each is user-installed and located. Whether GPL-3.0-or-later permits bundling any of them is an open question outside this document.

## Verdicts and the gate that promotes each

1. **xtb.** Strongest candidate: a distinct capability and a real Windows build. Gate: smoke test of single point, optimization and frequencies; a capability map against `QuantumEngineProvider` (charge, multiplicity, element coverage, failure parsing); then a preregistered comparison with ORCA and Psi4 before any claim that it improves their inputs.
2. **RXNMapper.** Narrow and testable. Gate: measure how often route validation reports mapping absent or partial on the real fixtures. Keep the planner's reaction and the inferred map separate, labelled model-generated, and keep "not assessable".
3. **CREST.** A separate ensemble project. Gate: a working xtb environment and a Windows route, then a frozen flexible-molecule comparison (minima found, diversity, failure rate, runtime) with the current generator. Nothing is replaced before that.
4. **Syntheseus.** A framework, not a planner. Gate: choose a model and check its licence, then an equal-budget comparison with AiZynthFinder on protocol 3's routes.
5. **Defer or skip.** PySCF (Windows), ASKCOS (heavy), OPERA, forward-reaction models, Mordred and PaDEL (redundancy not yet measured), Gypsum-DL, Orthonym (no verifiable source; the project owns its naming engine), vague "NMR processors", molecular-dynamics stacks. ASE and a second semiempirical backend are worth assessing only if xtb fails a stated requirement.

## Docking

Two separate problems with different prior evidence. Read `ROADMAP.md` "Ranking affinities" and `benchmarks/docking/` first.

**Affinity.** Vina's number is not meant as an affinity. Already done: replicate ranges shipped ("these overlap, do not rank them"); rescoring ranking power is a measured null on 77 series over 12 targets; free-energy methods were refused on cost; a smina spike ended at findings with nothing shipped. Even the best published scoring functions reach about 0.6 correlation. So the answer is to say less, not to add another number: audit what the Docking panel states about the score and present it as a pose score or a within-series rank, never an absolute binding strength. This is not a case for shipping smina.

**Pose trust** is the open gap. Rescoring with Vinardo left docking power unchanged (6 of 8 within 3 Å, ceiling 8 of 8); gnina's published gain is docking power, not ranking.

| Candidate | Role | Note |
|---|---|---|
| PoseBusters-style check | physical plausibility of a pose (clashes, geometry) | open Python, no new engine; verify at source |
| Meeko or existing prep | ligand and receptor preparation | measure prep and box failures first; earlier lessons found pH, chain and box mismatches |
| gnina | CNN pose scoring | Windows, licence and weights unknown; needs its own preregistered docking-power benchmark |
| smina | Vina fork | already spiked; no new reason beyond gnina's |
| interaction fingerprints | does the pose make the known contacts | Interaction Analysis already exists; reuse |

Suggested order: a plausibility flag together with the wording audit; then measure prep and box failure rates on the catalogued receptors, adopting Meeko only for failures it demonstrably fixes; then gnina feasibility followed by a docking-power benchmark in the existing harness.

## xtb: the spike and the first provider (2026-10-27)

The Windows zip (`6.7.1pre`, 37,550,920 bytes) matched its published sha256. Run on ethanol with GFN2: a single point (-11.3819 Eh), an optimization (-11.3943 Eh, gradient 3.6e-4) and an optimization with frequencies (27 values, 0 imaginary) each took well under a second; implicit solvation, a radical and an Au-H molecule ran. The licence was not on the release page and the zip carries only a licence for one bundled library: still to confirm.

`chem/xtb_engine.py` is a provider for `sp`, `opt` and `opt_freq` at GFN2-xTB or GFN1-xTB, tested against real outputs (`tests/test_xtb_engine.py`). It is registered with the service (an engine only when its executable is configured), has a locate-only External Tools tab whose Test runs H2 through the provider's own input and command, and the panel's method box offers `GFN2-xTB` and `GFN1-xTB` when it is chosen. Its numbers have not been compared with ORCA or Psi4. Four things the spike found that decided its shape:

- `command_args` is not handed the charge, spin or job, so the input file carries them in a header comment and the command is built by reading it back.
- The service writes `job.inp`, and xtb chooses its geometry reader by file name (a `.inp` name is refused) but reads a Turbomole `$coord` block by content, so that is the format, in Bohr; the final structure comes back in Bohr too.
- xtb accepted a methyl radical at `--uhf 0` and exited 0 with a different energy, so the provider refuses an impossible electron count itself.
- `normal termination of xtb` is on stderr, which the service does not read; a run is judged from stdout (`[ERROR]`, `finished run on`). IR intensities are only in a file in the working folder, so the modes carry none.

xtb's stdout is UTF-8 (its frequency heading contains `cm⁻¹`), so anything that reads it as text on Windows must say `encoding="utf-8"`: the default code page raised a decode error in the first draft of the Test button.

Next: the preregistered comparison with ORCA and Psi4 before any claim that it improves their inputs.

## Not done

No licence matrix beyond the table above, no version or commit pinning, no maintenance cadence, no installs. Those are the first step of each promoted tool's spike. The design document for a chosen tool would follow `PSI4_ENGINE_DESIGN.md` and carry a preregistered gate.
