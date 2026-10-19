# Psi4 as a second quantum-chemistry engine: design

**Status: proposal, 2026-10-19; stage 0 (the spike) was run the same day and its result is in "Stage 0 result" below; stage 1 (the provider, the External Tools tab, the Engine box) was built the same day and is described in "Stage 1 result" below; the ORCA agreement check (stage 2) is preregistered in `benchmarks/psi4_agreement/PLAN.md` (2026-10-19) was run 2026-10-19 with the verdict NOT EVALUABLE (see "Stage 2 result").** Decided by Alex 2026-10-19: spike only first, **locate-only** (no download button), no calculation types beyond `sp` and `opt` in version 1.
Statements marked *read* come from Psi4's documentation or a package index; the rest of the note is superseded where "Stage 0 result" measured it.

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
* **On disk, installed: 1.87 GB** (measured by the spike on a clean prefix: `Library` 1.24 GB, of which `Library/bin` is 641 MB mostly MKL; `Lib` 584 MB, of which Psi4 391 MB). **Not under a gigabyte**, so a tab that describes Psi4 says about 2 GB on disk.
For comparison, the pKa sidecar and the Java runtime are the other things the app fetches; the spike should put their sizes beside this one in the same units.

## Stage 0 result (2026-10-19, this machine, Windows 11, conda 26.1.1; prefix `D:\_scratch\psi4-spike`)

**Go for locate-only.** Native Windows works with no WSL and no admin rights; a user installs Psi4 and points the app at the folder, as for ORCA. Measured:

| question | result |
|---|---|
| install | `conda create -p <prefix> -c conda-forge psi4 python=3.12`: 2 min 30 s here, 222 MB fetched, **1.87 GB installed** |
| executable | `<prefix>\Scripts\psi4.exe` (also `psi4.bat`). **The app's existing finder (`find_program`) returns it unchanged** from the environment folder, from `Scripts` and from a parent folder, so no new locating code is needed |
| version | `psi4 --version` prints `1.11`, exit 0, 0.2 s of start-up |
| a job | `psi4 -n 4 input.dat output.dat`: water B3LYP/def2-SVP 2.3 s; water optimization 3.4 s |
| output | **both work**: the output file, and `-o stdout` (one `Final Energy` line captured from stdout), so `parse_output` can keep being handed captured stdout |
| a path with a space | works (`D:\_scratch\with space\`), unlike ORCA; forward-slash `PSI_SCRATCH` also works |
| failure | a bad input exits **1** and the output ends "Psi4 encountered an error" (with the failing statement boxed in `!` lines above it); a good run ends "Psi4 exiting successfully". **Corrected 2026-10-19: an earlier version of this row said a failed run still prints the success banner, which was a misreading of two outputs read together.** The service reads no exit code, so the parser keys on the error marker |
| cancel | killing the `psi4.exe` launcher (what `QProcess.kill` does) **also ended its python child** (benzene optimization, 2.5 GB resident at the time): no worker left behind, as measured for the pKa sidecar |
| memory | `memory 4 GB` in the input is honoured (the job held 2.5 GB); threads are `-n` on the command line, not an input block |
| optimized geometry | printed as "Final optimized geometry and variables" with element symbols and Angstrom coordinates, the shape the existing conformer landing needs |

**The trap, found by comparing with ORCA on the same molecule, geometry and basis (water, def2-SVP):** Psi4's `b3lyp` gives -76.35814 Eh (exact `scf_type pk`) and ORCA's `B3LYP` -76.32109 Eh, **37 mEh (23 kcal/mol) apart, because the two programs' B3LYP use different VWN forms**. Matched by name they are not the same functional: Psi4's `b3lyp5` gives -76.32099 against ORCA's `B3LYP` (0.10 mEh), and Psi4's `b3lyp` -76.35814 against ORCA's `B3LYP/G` -76.35824 (0.10 mEh). Psi4's default density fitting is a further difference (the default `scf_type` is `df`; -76.35815 against pk's -76.35814 here).
**So an engine provider must map a functional's NAME to the engine's own keyword by a table checked against ORCA, never pass the label through**, and a result carries the exact keyword and `scf_type` it ran with. This is the first entry of the agreement check's expected findings, and is why stage 2 compares energies rather than assuming them.

**Not measured:** whether a console window flashes when `QProcess` starts it (needs the application; check in stage 1), Windows Defender or SmartScreen behaviour on a first run, and a path with non-ASCII characters. The standalone installer route (the install page's other option) was not tried; conda was, because it was the one with a size we could read first.
The spike environment (1.87 GB) is left at `D:\_scratch\psi4-spike` for stage 1; remove it with `conda env remove -p D:\_scratch\psi4-spike` and delete `D:\_scratch
un1`, `orca_w`, `with space`, `pscr`.

## Stage 1 result (2026-10-19)

Built: `chem/psi4_engine.py` (`Psi4QuantumEngineProvider`: `sp` and `opt`, the functional table `PSI4_METHODS`, `puream true`, density fitting recorded in the provenance, the final geometry as a `psi4_opt` conformer), the interface's `display_name` / `supported_calc_types` / `supports()` /
`executable_setting()` / `executable_names()` (defaults keep every existing provider on ORCA's executable), the service's per-engine executable resolution (`available_engines()`; ORCA's refusal text is unchanged), the locate-only tab (`catalog.psi4()`, `verify_psi4`, `responds_as_psi4`), and the panel's
Engine box (shown only with more than one engine; greys out unsupported calculations and ORCA's solvent and conformer-average controls). Tests: `tests/test_psi4_engine.py` (20, parsed from real outputs, one running a real Psi4 when `OPENCHEM_PSI4_EXE` is set) and `tests/test_psi4_tool.py`;
11 mutations of the new code were all caught.

**What the comparison with ORCA found while building the table** (water, B3LYP/def2-SVP unless stated, exact integrals, energies in Eh; the difference is Psi4 minus ORCA):
HF 0.0000 mEh; PBE0 +0.10; M062X +0.09; B3LYP (Psi4 `b3lyp5`) +0.10 at def2-SVP, +0.14 at def2-TZVP, +0.14 and +0.16 at pcSseg-1 and pcSseg-2; **6-31G(d) -1.84 with Psi4's default cartesian d functions and +0.08 with `puream true`**. The 0.1 mEh is the two programs' default integration grids. This is a spot check of the table on one molecule, **not the preregistered agreement check of stage 2**, which compares more molecules and geometries.

**Corrected in this stage:** the spike's table said a failed Psi4 run still prints "Psi4 exiting successfully". It does not: a failed run exits 1 and ends "Psi4 encountered an error" (re-measured on a bad functional and a bad basis); the earlier row was a misreading of two outputs read together. The parser keys on the error marker, which is right either way.

**Left for later:** a Settings control for Psi4's memory (a job is given 2 GB in its input) and threads (it uses the ORCA cores setting), the stage-2 agreement check, calculation types beyond `sp` and `opt`, and text on the panel that still says ORCA (most tooltips and the Configure button) which is true of the panel's ORCA features and not wrong for Psi4 but is not Psi4-aware.

## Deferred 2026-10-19: where it stands and what is left (Alex: not a priority, somewhat redundant beside ORCA; do it in its own session)

**Built and pushed (branch `claude/fukui-gate-4`, PR #381, commits `67ddd11f` stage 1, `3869a514` and `052dfd35` and `334780dc` stage 2 plan, judge and runner):** the provider, the locate-only tab, the Engine box, `psi4_opt` conformers and labels, the real-window drive `benchmarks/visual/psi4_engine.json`, and the stage-2 preregistration with its judge (`benchmarks/psi4_agreement/`).
**Nothing in it is merged**, and #381 carries a lot besides Psi4 (the Fukui gate 4 work and its probes, the EOM cross-check): when it is merged is Alex's call. If Psi4 should wait for a later merge, the Psi4 commits are the four above and are separable from the Fukui ones.

**To do, in order:**
1. **Run the stage-2 agreement check** (`benchmarks/psi4_agreement/PLAN.md`, frozen after its one amendment). Needs the Psi4 environment (`conda create -p D:\_scratch\psi4-spike -c conda-forge psi4 python=3.12`, 1.87 GB, 2.5 minutes; the runner reads `OPENCHEM_PSI4_EXE`, default `D:\_scratch\psi4-spike\Scripts\psi4.exe`) and ORCA at `D:\ORCA\orca.exe`. Commands, run from the folder, ORCA and Psi4 one after the other so they do not fight over cores
   (`--workers 3 --cores 4`; expect a few hours; every stage resumes): `run_agreement.py floor --engine orca`, `floor --engine psi4`, `floor-report`, `grid --engine orca`, `grid --engine psi4`, `optimize --engine orca`, `optimize --engine psi4`, `attribute`, `report`. **Commit the tree first and do not edit `src/` while it runs** (the report refuses a dirty `src/` or two commits). Then write the outcome into the plan's last section,
   in `docs/PSI4_ENGINE_DESIGN.md` and the CHANGELOG, and act on the verdict as the plan says (a FAIL removes the functional from `PSI4_METHODS`).
2. **Settings for Psi4's memory and threads** (a job is given a fixed 2 GB in its input; threads reuse the ORCA cores setting).
3. **Panel text that still says ORCA** (most tooltips, "Configure ORCA...", "Full ORCA conformers"): true for ORCA's features, not Psi4-aware.
4. **Calculation types beyond `sp` and `opt`** (frequencies, dipole) only after 1, each behind its own decision; none are planned.
5. **A pinned download** only if Alex reverses "locate-only" (a pinned source URL and checksum, the size in the confirmation: about 330 MB download, 1.87 GB installed).

**Traps already paid for (do not re-learn):** Psi4's `b3lyp` is not ORCA's `B3LYP` (37 mEh; `b3lyp5` is); Pople bases are cartesian in Psi4 (`puream true` always); a failed Psi4 run exits 1 and ends "Psi4 encountered an error" and does NOT print the success banner (an earlier note here said it did: wrong, corrected); an empty registry key is left by the drive's `tool_path` step and is harmless; the 1.87 GB spike environment at `D:\_scratch\psi4-spike` and the folders `run1`, `orca_w`, `with space`, `pscr`, `fx` beside it are scratch and can be deleted.

## Stage 2 result (2026-10-19): NOT EVALUABLE

Run exactly as `benchmarks/psi4_agreement/PLAN.md` froze it (commit `7bc3d20c`, clean `src/`, about 70 minutes with 3 workers x 4 cores). **Verdict NOT EVALUABLE:** the HF floor, Psi4 `scf_type pk` against its default density fitting at 6-31G(d) (0.37 to 0.45 mEh on pyridine, DMSO, benzene and acetic acid), gives T_HF = 0.90 mEh, above the plan's 0.5 mEh ceiling. The DFT floor was small (0.065 mEh, T_DFT 0.13 mEh). So **no agreement is claimed and no failure either**, and `PSI4_METHODS` is unchanged.
For the record only (not judged): the median Psi4 minus ORCA is +0.09 to +0.49 mEh in every one of the 15 combinations (M062X the largest), always positive, with no trace of the 37 mEh or 1.8 mEh errors found earlier; the largest single difference is 0.75 mEh. Density fitting does not explain the offset (the `pk` reruns moved cells by tens of microhartree). One Psi4 `gau_tight` pyridine optimization did not converge in 50 iterations.
**Next, if wanted:** a new plan that settles the Psi4 default for Pople bases (density fitting against `pk`) and the HF floor's variants before any run. Not started. The stage-2 item in "Deferred" above is done; items 2 to 5 remain deferred.

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

## Decisions (Alex, 2026-10-19)

1. **The first deliverable is the spike:** done (above).
2. **Locate-only for now**, no download button; the confirmation-and-pinned-source work in stage 3 is deferred indefinitely.
3. **No calculation types beyond `sp` and `opt`** in version 1.
