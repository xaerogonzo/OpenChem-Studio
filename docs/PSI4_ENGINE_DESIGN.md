# Psi4 as a second quantum-chemistry engine: design

**Status: proposal, 2026-10-19. Nothing is built, and nothing in it has been run on this machine.** Every statement about Psi4 below is marked as *read* (from its documentation or a package index, not yet tried) or *to measure* (the spike
in stage 0 decides it). The decisions that are Alex's are listed at the end.

## Why

OpenChem Studio runs its quantum-chemistry jobs through ORCA, which a user must obtain from FACCTS with an account, and whose licence does not permit the app to fetch it (`ui/dialogs/external_tool_catalog.py`, `orca()`: "No Set Up button, deliberately"). A user without ORCA has no ab initio engine at all. Psi4 is open source
(LGPL-3.0, *read*), so the app could offer to fetch it with the same "what, from where, how big, then an explicit yes" confirmation as the Java runtime and the pKa sidecar. That is the reason; it is not that Psi4 is better. Nothing measured here says it is, and the Fukui and EOM work in `benchmarks/fukui_gate_4/` neither needs nor tests it
(Psi4 has no IP-EOM-CCSDT, and no native IP-EOM at all that we found).

## The central decision: an engine provider, not a JSON sidecar

A sidecar (`chem/pka_worker.py`) pays off when a request is short and the child is expensive to start (pKa: 3 to 5 seconds of model load against a fraction of a second of prediction). A quantum-chemistry job is minutes, so a per-job process costs nothing that matters, and **the app already has the seam for exactly this**:
`plugins/interfaces.py` `QuantumEngineProvider` (`build_input`, `command_args`, `parse_output`, with the service owning the `QProcess`), `QuantumChemistryService.register_provider` / `providers` keyed by `provider_id`, and `context.quantum_chemistry.register(provider)` for plugins. A `Psi4QuantumEngineProvider` is a second implementation of
that interface plus a tab in the External Tools dialog. It reuses job records, the Jobs panel, cancellation, provenance (`RUN_PROVIDER` already stamps the engine on every result) and the run ledger. No actor thread, no protocol, no persistent child.

## What a Psi4 engine would do (version 1)

* **Calculation types:** `sp` and `opt` at the methods the Method/Basis presets already name (HF and the DFT functionals), energies reported in Hartree as `psi4.scf_energy` (the convention `chem/boltzmann.py` looks up by `<provider_id>.scf_energy`).
  Everything that is ORCA-specific today (the compound-input Fukui run, delta-SCF, LED, NMR shielding parsing, the hole starts) **stays ORCA-only and the panel says so**: an engine declares which calculation types it supports (a small addition to the interface, defaulting to "all" for ORCA so nothing existing moves), and a calculation type an engine does not support is not offered for it, rather than offered and refused.
* **Input:** Psi4's own input (`molecule`, `set basis`, `energy('method')` / `optimize(...)`, `memory`, threads), built from the same `Chem.Mol`, charge and multiplicity. A closed shell is RHF/RKS and an open shell UHF/UKS, stated in the input and not left to a default, for the reason `docs/gotchas` and the Fukui work recorded for ORCA (a default can silently change the state).
* **Geometry out:** an optimized geometry returns as a `ConformerModel` with its method recorded, exactly as the ORCA path does (`ReplaceConformerCommand` and the landing rule from the ORCA-conformer work apply unchanged).
* **Not in version 1:** any EOM or ADC method, SAPT, properties (dipole is a candidate for version 2), frequencies, and any calculator that exists today only through ORCA. A Psi4 result is a result of Psi4 at that method and basis, never relabelled as the ORCA calculator's.

## Obtaining it (the tab)

A `ManagedExecutable` descriptor beside `orca()` and `vina()`, with `key="psi4"`, a setting `psi4/executable_path`, `Locate`, `Test (runs a 2-atom calculation)` and, because the licence allows it, **`obtainable=True`**: a Set Up button that downloads, extracts without installing, and changes no system setting, as the Java tab does. The confirmation names the source, the size and the
destination and waits for a yes (the app's download policy). **The source and the size are to measure** (the project's install page lists a standalone command-line installer and a conda route for native 64-bit Windows, *read*); the descriptor does not ship until a source whose URL and checksum we can pin has been found, because an unpinned download is a different product on each fetch.
A user who already has Psi4 (a conda environment, WSL is not an option for the app) points `Locate` at it, and `Locate` **runs** each candidate before accepting it, as the ORCA tab does, since a binary called `psi4` is not necessarily this one.

## Windows specifics, each to be settled by the spike and not assumed

| question | what is known | the spike measures |
|---|---|---|
| does a native install work on a current Windows 11 and Python | the install page lists native Windows since v1.4; forum reports of DLL-load errors are from the 1.4 era (*read*) | install, `psi4 --version`, a 2-atom job, on this machine |
| where the output goes | Psi4's command line is `psi4 input output`; whether stdout capture (what `parse_output` is handed today) works or the output file must be read instead is not known | run both; if a file, `parse_output` is given its text and `command_args` names it |
| space-free path | ORCA aborts on a path with spaces and on forward slashes (`docs/LESSONS.md`) | the same two cases for Psi4 and its scratch directory (`PSI_SCRATCH`) |
| process tree and cancel | `QProcess.kill` ends a launcher's child on Windows for the pKa sidecar (measured) | whether killing Psi4 leaves a worker behind |
| console window | a sidecar needs `CREATE_NO_WINDOW`; QProcess may not | whether a window flashes |
| memory and threads | set in the input (`memory`, `-n`), not by `%pal` | a default from Settings, with the ORCA setting's discipline: a limit safe at its default |
| size on disk and download | see "How large it is" below | the whole environment, installed, on a clean prefix, and stated in the confirmation |

## How large it is (measured 2026-10-19 from a `conda create --dry-run` and this machine's package cache; nothing was installed)

conda-forge publishes a native **win-64** Psi4 1.11 (builds for Python 3.11 to 3.15, uploaded 2026-10-12), so the Windows route exists today without WSL.
* **The Psi4 package itself: 78 MB compressed** (the one measured build, py312: 78.3 MB), **about 480 MB extracted** (an extracted Psi4 1.11 build already sits in this machine's conda cache).
* **A full environment** (Psi4, its own Python 3.12, numpy, scipy, libint, libxc, pydantic and the rest, 74 packages) needs **222 MB of downloads** by the dry run, **plus the MKL math library (about 100 MB compressed), which this machine already had cached and the dry run therefore did not count**: about **320 to 340 MB to download** on a clean machine.
* **On disk, installed: not measured**, and certainly more than the 480 MB of Psi4 alone, because MKL and Python extract larger than they download. The spike measures it on a clean prefix; the confirmation dialog would show that number, not an estimate.
For comparison, the pKa sidecar and the Java runtime are the other things the app fetches; the spike should put their sizes beside this one in the same units.

## How it is validated before it is offered (the project standard: claims are measured)

1. **The parser is written against real output**, saved as fixtures (`tests/fixtures/psi4/`), never against what the manual says it prints; a mutation check on it, as for every parser here.
2. **A preregistered agreement check with ORCA**, written and committed before it is run: the same molecules, geometries, functional and basis, the total energy and the optimized geometry compared between the two engines, with the tolerance **set from a measured floor** (two ORCA runs differing in grid, two Psi4 runs differing in threads) and not guessed. A Psi4 energy that differs from ORCA's by more than that floor for a stated reason (a different default grid, density fitting) is documented, not hidden; and the engine's results carry their own settings in provenance so two engines' numbers are never mixed under one label.
3. **A real run through the real window** (`OPENCHEM_DRIVE`, `qc_run` with the engine named, then `conformer_report`), with the Test button, since this project's earlier engine bugs were all found there and not in mocked tests.

## Stages

* **Stage 0, the spike (no app code):** install Psi4 by the route a user would, answer every row of the table above, run water at HF and one DFT functional, and write down the download source, size and checksum. **Output: a short result section appended here and a go / no-go.** If native Windows does not work cleanly, the answer is no-go for a user-facing engine, and this note says why.
* **Stage 1:** the provider, the `supports(calc_type)` hook, the External Tools tab with Locate and Test, a help topic, the sources-registry entry for Psi4's own citation (read from the paper first; no DOI is quoted here because the DOI guard requires one in the registry).
* **Stage 2:** the preregistered ORCA agreement check; its outcome, whichever way, is recorded.
* **Stage 3 (only after 2):** the download button, then version 2 calculation types, each behind its own decision.

## Risks, named

* A second engine doubles the surface that can disagree with itself. The mitigation is the provenance already carried (engine, method, basis, settings), the rule that nothing is relabelled across engines, and that ORCA stays the default.
* Psi4's bundled Python and its own libraries must not collide with the app's environment: it runs as a separate process from its own prefix, never imported, which the layering test (UI and services never import a chemistry library directly) already enforces for the others.
* A download is a trust decision. A pinned source and checksum, a size shown before the yes, nothing run as an installer, and no system setting changed, or the button does not ship.
* A tool a user obtains "for free" will be assumed to be validated. It is offered as a second engine at stated methods and nothing more, with the same stage and visibility vocabulary as the calculators (`docs/CALCULATOR_MATURITY.md`).

## Decisions that are Alex's

1. **Is the first deliverable just the spike?** Recommended: yes. Everything after it depends on a Windows install that has not been tried, and the spike costs no application code.
2. **Should a successful spike lead to an automatic download, or to Locate only?** Locate-only is the smaller commitment (no pinned download to maintain); the download is what makes it a tool other users can obtain without a guide.
3. **Which calculation types, if any, beyond `sp` and `opt`?** The note proposes none in version 1.
