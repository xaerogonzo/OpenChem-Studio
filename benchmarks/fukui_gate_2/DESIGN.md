# Fukui v2: design record

Written 2026-10-18, **before the second gate (`PREREGISTRATION.md`) was frozen and before any gate species was run.** Alex asked for the gate to test the robust-anion version of the calculation, so this
is the calculation that was built first, what each change rests on, and what was tried and not adopted. Everything measured here was measured on **stand-in species that are not in the gate's tables**
(`PREREGISTRATION.md` section 2 lists them); no number of a species of `deproft2002`'s Tables 4 to 6 was looked at.

## 1. What changed, and where

| # | Change | Why (measured) | Code |
|---|---|---|---|
| 1 | **A species with a negative charge gets f- alone**: two states (N, N-1), not three. | The N+1 state of an anion is a dianion, bound by no basis set in the gas phase. In the first gate's reported arm the dianion states were refused for an integration shortfall (0.010 to 0.073 electrons at 6-311+G**) and had more than one SCF solution (f+ differing by up to 0.31). f- needs only the N and N-1 states, both bound; section 2.2. | `chem/fukui_plan.py` (`plan_fukui`), `chem/fukui.py` (`condensed_fukui(..., anion=None)`), `chem/orca_engine.py` |
| 2 | **`%method IntAcc 6.0` in every job.** | Hirshfeld charges are integrals on ORCA's grid. A finer grid took seven diffuse anions from 0.010-0.073 electrons short to within 0.005 (first gate 11.5, 11.6) and changed nothing where nothing was wrong: 0.0000 on 14 jobs at 6-31G**, at most 0.00001 on three drug-sized molecules (2.4), at most 0.0004 on seven bound anions (2.2). It costs 8% to 28% (2.4). | `orca_engine._FUKUI_GRID` |
| 3 | **`%scf HFTyp RHF` or `UHF` in every job.** | Found while building the fixtures: ORCA switches the first doublet to UHF/UKS and keeps the setting for the later jobs of a compound input, so a closed-shell job written after a doublet ran unrestricted (2.1). Without it the extra starts of an anion are not the restricted closed-shell state the N state means. | `orca_engine._build_fukui_input` |
| 4 | **At a basis set with diffuse functions, each anionic state is also started from HCore and from Hueckel, written after every default job; the lowest solution is read unless the default start is within 0.01 eV of it.** | At 6-311+G** ORCA's default start (the previous job's orbitals) reached a solution 0.6 to 1.0 eV above one another start found in 3 of 6 cases, with f+ differing by up to 0.31; HCore or Hueckel found the lowest in all 6 (2.3). At 6-31G** and for bound anions at 6-31+G* every start ended within 0.004 eV of the default (2.2, 2.3). | `chem/fukui_plan.py` (`plan_fukui`, `choose_solutions`, `has_diffuse_functions`), `orca_engine._fukui_job_results` |
| 5 | **Each job is read from its own stretch of output** (from its echo of charge and multiplicity to the next job's). | A failed job is then a stretch with no energy and no table, named; counting every energy in the file could only say the total was wrong. It is also what lets an extra start be told from a state, and an <S**2> be attributed to its own job. | `orca_engine._fukui_job_results` |

The input of a run is one ORCA compound input (`$new_job`), as before; the service needed no change. The jobs a run holds are **written in the order the answer needs them**: ORCA ends the whole compound input at
the first job that does not converge (2.1), so every default job comes first and an extra start that fails costs only itself.

## 2. The measurements

All with ORCA 6.1.1 on this machine, through `OrcaQuantumEngineProvider.build_input` or standalone with the same keywords; scripts are in the session scratchpad and the real-ORCA fixtures in
`tests/fixtures/orca/` regenerate with `benchmarks/fukui_gate_2/make_fixtures.py`.

### 2.1 What ORCA does inside a compound input

* **An explicit guess keyword in a later job replaces the default "read the previous job's orbitals".** CN-, `B3LYP 6-31+G*`, five jobs: the `INITIAL GUESS:` line reads `MODEL POTENTIAL` (job 1), `MOREAD`
  (a later job with no keyword), `HCORE` (`! HCore`), `MINIMAL BASIS EHT` (`! Hueckel`) and `POLARIZED ATOMIC DENSITIES` (`! PAtom`). The neutral radical's energy from the four starts: -92.666645, -92.666637, -92.666652 and
  -92.666662 Eh (0.7 meV apart). ORCA warns that `MOInp` is ignored when a guess is given; it is harmless.
* **A job that does not converge ends the whole run.** The same input with the third job given `%scf MaxIter 2`: exit code 115, no `ORCA TERMINATED NORMALLY`, the first two jobs complete (energies
  -92.811331 and -92.666645 Eh), the third echoed and not finished, the fourth never run. The service reads the output whatever the exit code, so what the finished jobs printed is usable.
* **HFTyp is inherited.** Methoxide, `B3LYP 6-31+G*`, four jobs (anion, neutral radical, anion from HCore, anion from Hueckel): the output prints `HFTyp .... RHF`, `UHF`, **`UHF`, `UHF`**, and an <S**2> of 0.000 for the
  two closed-shell extras. With `HFTyp RHF` written in them they run restricted and give -115.040725409317 and -115.040701711269 Eh, **identical to every printed digit to the standalone restricted runs** of the same
  anion at the same grid (2.2), where the inherited-UHF jobs differed by 3.3 and 2.1 meV.

### 2.2 Seven bound anions at `B3LYP/6-31+G*` (the route of SCN- and NO2-)

Stand-ins: azide, cyanate, formate, acetate, the acetone enolate, p-cresolate, methoxide; RDKit ETKDG (seed 7) then MMFF, one geometry each; two jobs (the anion, its neutral radical) on ORCA's default grid and on `IntAcc 6.0`,
and the anion again standalone from HCore, Hueckel and PAtom on each grid.

| anion | anion charge sum, deviation from -1 (default / fine grid) | largest change of f- from default to fine grid | largest energy of any start from the default start's (eV) |
|---|---|---|---|
| azide | 0.00039 / 0.00005 | 0.0002 | 0.0018 |
| cyanate | 0.00022 / 0.00003 | 0.0001 | 0.0034 |
| formate | 0.00007 / 0.00002 | 0.0004 | 0.0013 |
| acetate | 0.00007 / 0.00002 | 0.0002 | 0.0040 |
| acetone enolate | 0.00008 / 0.00009 | 0.0001 | 0.0016 |
| p-cresolate | 0.00003 / 0.00002 | 0.0001 | 0.0028 |
| methoxide | 0.00001 / 0.00012 | 0.0001 | 0.0029 |

A bound anion has no integration shortfall (the worst is 0.0004 of an electron against the 0.01 the calculation tolerates), the grid moves f- by at most 0.0004, and **every start ends in the same solution: none is lower
than another by more than 0.004 eV.** The margin of `START_MARGIN_EV` (0.01 eV) is above that. So for the anions of the second gate, changes 2 and 4 are expected to be no-ops, and change 1 is what
makes the gate possible.

### 2.3 Which start finds the lowest solution of an unbound anion

From the first gate's follow-up probes (`benchmarks/fukui_gate/artifacts/anion_guess_probe_diffuse.json`, `_gated.json`; standalone anions at ORCA-optimized geometries; energies against the default start):

* **At 6-311+G** (six cases)**: acetone/HF: only HCore lower (-1.013 eV). CN-/HF: Hueckel, HCore and the stability analysis lower (-0.681 eV), PAtom equal to the default. CN-/B3LYP: all four other starts lower (-0.615 eV).
  Acetone/B3LYP, CNO-/B3LYP, H2CO/B3LYP: all within 0.001 eV except Hueckel on H2CO (+0.39, a higher solution). **{default, HCore, Hueckel} found the lowest solution in all six**; PAtom added nothing; the stability analysis
  found the lower CN- solutions, missed acetone/HF, and stopped with an error for some diatomics.
* **At the 6-31G** levels the first gate decided on (14 cases, five starts each)**: no start was lower than the default by more than 0.004 eV. HCore landed on a HIGHER solution in four (+7.26 eV for CO/HF, +3.48 H2CO/HF,
  +1.34 NCO-/HF, +1.04 NCO-/B3LYP), which `choose_solutions` never reads: it takes the lowest, and keeps the default unless something is lower by more than 0.01 eV.

So a start can land on a higher or a lower solution and the default start can be on either; reading the variational (lowest) one among three starts is deterministic and does not depend on which was tried first. It is **not**
claimed to be the physically right solution of an unbound state (below), only a defined one.

### 2.4 What the finer grid costs and changes at `B3LYP/6-31G*`

The application's own three-job input on molecules that are in neither gate, four cores, default grid against `IntAcc 6.0`:

| molecule (atoms) | default grid | `IntAcc 6.0` | ratio | largest change of f+ / f- |
|---|---|---|---|---|
| aspirin (21) | 63.5 s | 81.0 s | 1.28 | 0.00000 / 0.00001 |
| caffeine (24) | 73.4 s | 82.6 s | 1.13 | 0.00000 / 0.00000 |
| ibuprofen (33) | 94.4 s | 101.9 s | 1.08 | 0.00000 / 0.00000 |

Charge sums were within 0.0001 of the charge for every state, both grids. On the small anions of 2.2 the two-job plan took 5% to 33% longer.

### 2.5 In the real window

`benchmarks/visual/fukui_v2_anion.json` (methoxide, `B3LYP 6-31+G*`: ORCA optimization, then Fukui; four jobs, 18 s): one per-atom dataset (`orca.fukui_minus`, largest on the oxygen, 0.522), the panel says
"f+, f0 and the dual descriptor were not computed" and gives the reason, the Atom Inspector holds `orca.fukui_minus` fresh, **VERDICT PASS** (0 unexpected application errors).
`benchmarks/visual/fukui_v2_diffuse_neutral.json` (acetone, `HF 6-311+G**`, optimized in the application first): four datasets; the panel reports the anion 1.69 eV above the neutral and "The anion state has more than
one SCF solution. ORCA's default start reached one 1.01 eV above the lowest of the 3 starts that finished, and the lowest, from the HCore start, was used. The two differ by up to 0.212 electrons in one atom's Hirshfeld
charge..."; **VERDICT PASS**. These are the same numbers the real-ORCA fixtures hold (`tests/test_orca_fukui_v2.py`).

## 3. Decisions, and what was not done

* **An anion is f- only by its charge, automatically.** Alternatives: an explicit "f- only" choice in the panel (more surface, a new field through the service, the run record and the provider interface, for a
  distinction the charge already makes); or keeping f+ for anions with the unbound caveat, as the first release did (it computes a number from a state no basis set binds, which is what the gate-1 follow-up measured to be
  refused or irreproducible at a diffuse basis). **This is a behaviour change for anion inputs, and is for Alex to confirm (`PREREGISTRATION.md`, C1).**
* **Extra starts only at a basis set with diffuse functions, recognised by name** (`has_diffuse_functions`: Pople `+`/`++`, Dunning `aug-`/`d-aug-`/`heavy-aug-`/`jun-`/`jul-`/`may-`/`apr-`/`maug-`, `ma-def2`, `def2-...D`).
  A name it does not recognise gets one start: the cost is the extra starts a run would have had, and the "not validated" caveat about f+ is the same. The alternative, deciding after the first run whether the anion
  is unbound, needs a second ORCA call and a service that chains runs, which the compound input exists to avoid.
* **HCore and Hueckel, not PAtom or the stability analysis** (2.3). **A margin of 0.01 eV**, because two starts that reach the same solution differ by the SCF's own convergence (at most 0.004 eV in everything measured) and a
  choice made on that would be a choice made on noise.
* **Anionic states only** (a total charge below zero): the N+1 state of a neutral or a cation, and the N state of an anion (and, for a dianion, its N-1 state). The measured fragility is the unbound anion's.
* **The N-1 state of an anion is a neutral radical** and is named so in every sentence (`state_name`); the spin sentence says "The neutral radical is spin-contaminated", not "The cation".
* **`IntAcc 6.0`, not ORCA's `DefGrid3`**: only the first was measured.

## 4. What v2 does not claim

* **Diffuse-level f+ is still not validated, and not made well defined.** The lowest of three starts is one solution of a state that has several: in the probes the stability analysis found another 0.017 eV below the lowest
  start for formaldehyde at B3LYP/6-311+G**, with f+ differing by 0.026, and a published diffuse-level f+ matched the lower solution for acetone/HF and the higher for CN-/HF. v2 reads a defined one and says when the starts
  disagreed.
* **The lowest SCF energy is not a claim about which solution is physical** for a state the basis set only describes.
* The first gate's carbon monoxide miss is not explained by any of this (it is a neutral at 6-31G**; the cation's spin contamination remains a candidate).
* Unrestricted ions without annihilation, as before: the <S**2> warnings stand.

## 5. Verification

* **Pure tests:** `tests/test_fukui_plan.py` (the plan for every charge, with and without diffuse functions; every basis-name family; the choice among starts, the margin, order independence, failed starts),
  `tests/test_fukui_anions_and_starts.py` (f- alone, the refusals by state, the sentences, the summary lines), `tests/test_fukui.py`, `tests/test_orca_fukui.py` (the input: states, grid, HFTyp, extra starts after the defaults).
* **Real ORCA output, from the application's own input:** `tests/test_orca_fukui_v2.py` on `tests/fixtures/orca/{methoxide_fukui_fminus,acetone_fukui_diffuse_hf,methoxide_fukui_failed_start}.out`, whose `.inp`
  files the builder is asserted to reproduce exactly.
* **The real window, real ORCA:** the two drive scripts of 2.5.
* **Mutation check:** 51 single-line mutations of `chem/fukui_plan.py`, `chem/fukui.py`, `chem/orca_engine.py` and `app/fukui_gate_2.py`, each applied to the committed file with its bytes restored afterwards
  (the margin and its sign, the choice of the lowest start, which states have an N+1 and which get extra starts, the diffuse-basis recogniser, the grid and `HFTyp` strings, the per-job reading, the
  widths of Rules A and B, pair matching, each condition of NOT EVALUABLE and the verdict ladder): **every one is caught by a test.** The first pass left two alive: a condition that was dead code
  (`position == 1 and state != STATE_N`, unreachable because a first job that is not a closed-shell state is refused one line earlier; removed) and the rule that a job's LAST energy line is its energy
  (a test was added).
* **The standing sentence:** every result's closing sentence now says an EARLIER version of the calculation failed its check and this version has not been checked, which is what is true of v2 until
  the second gate decides (`chem/fukui.py` `NOT_VALIDATED_SENTENCE`).
