# The third Fukui gate: preregistration

> **FROZEN, 2026-10-18, by the commit that wrote this banner.** From that commit on sections 0 to 10 are fixed, together with the calculation it tests (`chem/fukui_plan.py`, `chem/fukui_states.py`, `chem/fukui.py`, `chem/orca_engine.py` and what they
> call: the code of commit `cfb91cfd`, which this commit leaves unchanged under `src/openchem/chem/`), the panel, the rules and the judge (`app/fukui_gate_3.py`, `tests/test_fukui_gate_3.py`) and the runner (`run_gate.py`). Section 11 is where the outcome is written, below a rule, in later commits.
> **When it was frozen no ORCA job of a gate species had been run at this calculation** except where section 2 says so; the two noise floors had been, on molecules in neither gate, and their numbers were seen (section 2). It follows the answers Alex gave: the search is on by default with a switch;
> a pass changes wording only and the calculator stays experimental; the machine's cores may be used (the decisions are recorded at the end).

This is the third preregistered check of the calculator **Fukui functions (Hirshfeld)** (`orca.fukui`). The first (`benchmarks/fukui_gate/PREREGISTRATION.md`) ended in **FAIL by 0.0014 on one quantity** and the second
(`benchmarks/fukui_gate_2/PREREGISTRATION.md`) in **FAIL, 33 of 47 numbers within 0.02**; both are final and neither is touched here. This gate asks a different question: not whether the numbers match a publication but whether
the calculation's **f- is a function of the structure** once it searches for the cation's states (`DESIGN.md`).

## 0. Why a third gate, and what it is built on

The second gate's section 11.4 found, after its outcome and with the published numbers in view, that the state of the cation the application's N-1 job reaches is **not a function of the structure** for benzaldehyde (6 of 14 runs one state, 8 the other,
0.13 apart in f- at the oxygen, depending on a rotation, a 0.001 A displacement or the embedding), and that for three molecules the published numbers belong to a state above the lowest. Its 11.6 left open "a calculation that converges the N-1 state from
several holes, reads the lowest and says when another lies within a stated window ... gated on its own reproducibility and against a reference whose states are identified, and not on this source for these three molecules, whose numbers it would not reproduce".
**That calculation is Fukui v3** (`DESIGN.md`; `chem/fukui_states.py`, `chem/fukui_plan.py`, `chem/orca_engine.py`). It runs three more cation jobs, each starting from the neutral's orbitals with the electron taken from the HOMO-1, HOMO-2 or HOMO-3, reads f- from the
lowest state any N-1 job reached (the mean of the states within 0.01 eV of it if they differ, a degenerate level) and reports the states within 0.5 eV.

**A reference whose states are identified does not exist for this question**, so the gate does not claim accuracy: it tests the three things the search is for and that can be tested without one (section 1).

## 1. The claim, and what a pass does not say

> On ORCA 6.1.1, at `B3LYP/6-31G*` and on the geometry ORCA optimized at that level, for **12 species** (section 3):
> **R.** f- of the application's calculation is **reproducible**: for each species, every perturbed run (four rigid rotations of the reference geometry, four copies with every coordinate displaced by Gaussian noise of 0.001 A, and for six species three
> optimizations from other RDKit embeddings) gives f- within **0.01** of the reference run's at every atom, atom class by atom class;
> **C.** the search is **complete** on the reference geometry: it finds the lowest state, and every state within 0.5 eV of it, that an exhaustive search (holes down to the HOMO-7) finds;
> **N.** it does **not regress**: for the **eight** species of the second gate that calculation reproduced in every number (27 of its 47), this calculation reproduces every number within the second gate's tolerance of 0.02 and every decided site statement.

A pass does **not** say that:

* f- matches a publication: for benzaldehyde, anilinium and thiophene the published values belong to a cation state **above** the lowest, and the search reads the lowest; the 14 numbers the second gate missed are not retested;
* the lowest state is the state a condensed Fukui function ought to describe (nothing here decides it), or that states 0.1 eV apart are correctly ordered by a B3LYP energy difference;
* **a competing state is reported whenever one exists**: the pilot (`DESIGN.md` section 2) found the benzaldehyde note in the reference and three of four rotations and in none of four displaced geometries, where every start relaxed into the lowest state. R tests f-; how often the note appears is
  reported (section 10), not decided;
* degenerate levels of more than two components (methane's cation was run once and did not look like one) or any species outside the 12 and the eight;
* any other level, an anion's f+, a molecule with an element heavier than krypton (the search is not written for it), or the calculator's support level: **it stays experimental whatever the outcome** (section 8).

## 2. What has been run or seen before the freeze, disclosed

* The first and second gates and the second gate's probes (`benchmarks/fukui_gate_2/artifacts/cation_states_probe.json`, `route_check.json`, `core_check.json`, `landing_check.json`): **eleven molecules were run with holes in the HOMO to the HOMO-3 and their states were seen**
  (HCN, benzaldehyde, pyrrole, furan, thiophene, anilinium, SCN-, phenol, aniline, N2O, styrene), and benzaldehyde's landing under 14 perturbations. All eight of the panel's first eight are among them; **their states, gaps and published distances are known**, including the three whose
  published values match a higher state (0.094, 0.145, 0.449 eV) and HCN's sigma state (0.392 eV). The window of 0.5 eV was chosen after they were seen (`chem/fukui_states.py`), which is why it contains them.
* **The mechanics of the search were run before the code was written** (`proto_holes.py`): HCN, benzaldehyde (an RDKit geometry), benzene (RDKit and then ORCA-optimized geometries) and methane, B3LYP/6-31G*; the real-ORCA fixtures of the tests (`tests/fixtures/orca/*_cation_search*`) are
  HCN, HCN with a hole job that cannot converge, benzaldehyde, benzene and water. **Benzene and methane are therefore seen and are only in the reported arm; HCN and benzaldehyde at their ORCA geometries are seen at v3.**
* **The pilot** (`pilot_v3.py`, `artifacts/pilot_benzaldehyde_search_on.log` and `_off.log`): benzaldehyde, the reference and four rotations and four displacements, with the search on (worst difference of f- from the reference 0.0021, the note in 4 of 9 runs) and off (5 of 8 differed by 0.127 to 0.130).
  **Benzaldehyde's reproducibility at v3 is therefore seen**, with these seeds' geometries; the gate's seeds are different (section 4).
* ORCA's DeltaSCF with a held hole (`exp_mom.py`) was tried once on benzaldehyde and not adopted (`DESIGN.md`).
* **The two noise floors of section 6 were measured before the freeze, on molecules in neither gate** (acetaldehyde and ethylene), at commit `cfb91cfd` (`dirty: false`; `artifacts/floors.json`, `floor_records.jsonl`, `floor_geometries.json`, committed with this banner): **acetaldehyde 0.0 for the same input twice and
  0.000131 for the whole chain twice; ethylene 0.0 and 0.000004; F = 0.000131**, against the limit 0.005. **No ORCA job of any other species of the panel of section 3 (pyridine, toluene, naphthalene, acetophenone, phenol, aniline, anilinium at their ORCA geometries with this calculation, and so on) has been run at v3.**
  Pyridine was a floor molecule of the second gate (a comparison between two of its own runs, never with a published number); toluene, naphthalene and acetophenone were in no run of any kind. The wide registry sweep of the calculation's code (146 test files that touch the calculator registry) passed at `cfb91cfd`: 4545 passed, 2 skipped.

## 3. The panel

All at **`B3LYP 6-31G*`**, gas phase, ORCA 6.1.1 (`D:\ORCA\orca.exe`), closed shell, from an RDKit ETKDG (seed 7) + MMFF embedding optimized by ORCA at that level, which is the **reference geometry**. The first eight are the second gate's, the last four held out.

| Group | Species (SMILES; charge) | R perturbations |
|---|---|---|
| close | benzaldehyde `O=Cc1ccccc1`, anilinium `[NH3+]c1ccccc1` (+1), thiophene `c1ccsc1`, hydrogen cyanide `C#N` | 4 rotations, 4 displacements, 3 embeddings |
| clean | phenol `Oc1ccccc1`, aniline `Nc1ccccc1`, pyrrole `c1cc[nH]c1`, furan `c1ccoc1` | 4 rotations, 4 displacements |
| held out | pyridine `c1ccncc1`, naphthalene `c1ccc2ccccc2c1` | 4 rotations, 4 displacements |
| held out | toluene `Cc1ccccc1`, acetophenone `CC(=O)c1ccccc1` | 4 rotations, 4 displacements, 3 embeddings |

(6 species at 12 runs and 6 at 9: **126 runs** of R.) The held-out four were chosen as pi systems with a lone pair or a methyl group before any was run. **N** runs the eight of the second gate named in `app/fukui_gate_3.py` (`N_SPECIES`): phenol, aniline, fluorobenzene, styrene,
nitrobenzene, acrolein, N2O and nitrite (`B3LYP 6-31+G*`, an anion), each once at its second-gate level on its ORCA optimization. **Reported only:** benzene (a degenerate pair) and methane (seen, section 2).

## 4. Procedure

`benchmarks/fukui_v3/run_gate.py`, through the application's own input builder (`OrcaQuantumEngineProvider.build_input`, the search on) and parse (`_condensed_fukui`, the function `parse_per_atom_output` calls), at 4 cores a job, six jobs at once.
**R.** The reference run on the reference geometry; four **rotations** (a rigid rotation by a random orthogonal matrix of the reference geometry), four **displacements** (every coordinate plus Gaussian noise of sigma 0.001 A) from one rng stream per species,
`numpy.random.default_rng(20261019 + k)` with `k` the species' place in the list `PANEL + FLOOR_SPECIES + REPORTED_SPECIES` (rotations first); and for the six species marked, **three embeddings** (RDKit seeds 101, 102, 103, each ORCA-optimized, then run).
**C.** One run per species on the reference geometry whose input has the hole starts of the HOMO-1 to the HOMO-7 (`EXHAUSTIVE_OFFSETS`; a hole that reaches the core is dropped), read with the same function; its states and those of R's reference run are compared (section 7).
**N.** The second gate's own species, geometries (ORCA optimizations of seed-7 embeddings) and published numbers (`app/fukui_gate_2.py`, `decided_entries`, `decidable_site_statements`), compared with the second gate's `compare`; acrolein's optimized O=C-C=C dihedral must be within 30 degrees of 180.
**Atom classes.** R compares f- atom class by atom class with each class's values sorted (`Chem.CanonicalRankAtoms(breakTies=False)` of the molecule with explicit hydrogens), so that an optimization from another embedding that puts a substituent on the other side of a ring is the same run.

## 5. What is recorded

Into `benchmarks/fukui_v3/artifacts/`: `floors.json` and `floor_records.jsonl`; `runs.jsonl` (one line per attempt of each job: species, variant, the arm, the commit and whether `src/` differed from it, the ORCA version and exit code, the sha256 of the input, seconds, f-, f+, f0 and
the dual descriptor, every state the search found within the window with its absolute energy and charges, how many states it found in all, the competing gaps, whether the level was degenerate, whether the search was incomplete, the note, and how far above the lowest state the default job's state was);
`geometries.json` (every optimized geometry); `verdict.json` (the outcome, every reason, every R row, every C row, every N row and site row). Nothing is chosen afterwards.

## 6. The noise floors, and the tolerances

**R: 0.01.** Fixed here by hand. It lies between **0.0004**, the largest amount by which two jobs that reached one state differed in an atom's charge (44 jobs, eleven molecules), and **0.085**, the smallest by which two different states did, and above **0.0021**, how far a 0.001 A displacement moved
benzaldehyde's f- inside one state in the pilot: a tenth of the smaller of the two states' differences. **C:** states match when their absolute energies are within **0.01 eV** and every atom's charge within **0.005**; the lowest state may not be missed by more than 0.01 eV; the window is **0.5 eV**.
**N:** the second gate's **T = 0.02**.
**The floors F** are measured on **two molecules in neither gate and not in the panel, acetaldehyde `CC=O` and ethylene `C=C`**, each as the largest difference of any atom's f-, f+, f0 or dual descriptor (atom class by atom class) between the **same input twice** and the **whole chain twice** (a second molecule embedded with seed 11, optimized and run
independently). **The gate can use its tolerances only if F <= 0.005** (the second gate's limit); otherwise it is NOT EVALUABLE.

## 7. The verdicts

Decided by a pure, tested judge (`app/fukui_gate_3.py`, `tests/test_fukui_gate_3.py`). Every reason is collected; none hides another.

**NOT EVALUABLE** (nothing is claimed) when any of: no floor, or a floor above 0.005; an ORCA other than 6.1.1; runs made from more than one commit, or from a `src/` that differed from its commit; a panel species with no reference run, or a run of R that was never attempted, or no exhaustive record; acrolein's dihedral
outside the limit or missing. **A job that did not finish is repeated unchanged up to three attempts and a job that completed is never repeated** (as in the earlier gates); a run that still has no result is recorded as not computed and is a **failure of R**, not a reason to call the gate not evaluable.
**R** holds when no perturbed run's f- differs from its species' reference by more than 0.01 and every run was computed. **C** holds when, for every species, the exhaustive search's lowest state is within 0.01 eV of the application search's and every state of the exhaustive search within 0.5 eV of its lowest is matched by one of the application search's.
**N** holds when all 27 numbers are within 0.02 and every decided site statement is reproduced.
**PASS:** R, C and N. **PARTIAL:** R holds for every species and C or N does not. **FAIL:** R does not hold: any run beyond the limit or not computed. The measured numbers are printed beside every row; **T and the limits are not changed after an outcome**.

## 8. After each outcome

* **PASS:** the documentation says, for the species tested and as far as they resemble them, that f- of this calculation was reproducible under the perturbations of section 4 to 0.01, that the search found the states an exhaustive one did, and that it did not lose a number the second gate's calculation reproduced; it keeps
  section 1's list of what it does not say, and **the calculator stays EXPERIMENTAL, hidden, with the second gate's "Not validated" sentence and one clause more saying the third check passed**. Promotion would need a new preregistration against a reference with identified states.
* **PARTIAL:** the same for the arms that held, and the arm that did not is named in the documentation with its numbers; the calculator stays experimental.
* **FAIL:** the search ships (it is a switch, and the pilot's benzaldehyde improved from a spread of 0.13 to 0.002) with the failure stated: which species and run, by how much; **a failure is a reason to find the cause, not to retire the work**, and the cause, the design or the limit is the subject of a new preregistration.
* **NOT EVALUABLE:** not a result; repeated after its cause is fixed, with the same limits.

## 9. What may be repeated, and what may not

A job that did not finish may be repeated unchanged up to three attempts, each a line in `runs.jsonl`; a job that completed is never repeated; NOT EVALUABLE may be repeated after its cause is fixed; **PASS, PARTIAL and FAIL are final**, and nothing about the limits, the panel, the perturbations, the seeds or the rules changes after a decided outcome.

## 10. The reported arm: written beside the outcome, and never decides

* **Recall of the note:** for each species whose reference run reported a competing state, in how many of its perturbed runs the note appeared (the pilot: benzaldehyde 4 of 9).
* **Benzene and methane** (seen): the degenerate-level average and its f- by atom; methane's states.
* **How much the search changed:** for each run, how far the state the default job reached lay above the lowest (the amount v2's f- would have been wrong by), and in how many runs it was not the lowest.
* **Cost:** seconds per run, with and without the hole jobs (the same input's first three jobs are v2's).
* **The second gate's 15 species** are not rerun here; N uses eight.

## 11. Outcome

(Written below a rule, in later commits, after the run.)

---

## Decisions (kept as a record)

Alex, 2026-10-18: "Yeah, let's do the 3 cation-state search, why not?" **Asked of Alex before the freeze, and answered:** the search is **on by default, with the switch** in Settings > Quantum chemistry ("On by default, with the switch"); a PASS is **wording only, and the calculator stays experimental**
("We can go with Wording only, stays experimental (Recommended), but I definitely want to get more preregistration, papers, ect if we can. So record that, or we could even do that now, not sure."); the gate may use most of the machine's cores for a few hours ("Yes, start when frozen"). Left at the recommended default, not asked:
the window is **0.5 eV**, the panel is the 12 and the eight, and the limits are section 6's.

**Recorded, not part of this gate: Alex wants more preregistered checks against the literature, "papers, etc."** The gate's own limit is that no reference with identified cation states was used. What such a reference could be, and where it might be found, is the work that follows: published condensed Fukui tables
that name the state or the orbital the electron was taken from; photoelectron spectra whose bands are assigned to cation states (vertical ionization energies by band, to test the ORDER of states); and high-level state energies (EOM-IP-CCSD or CASSCF/NEVPT2) for the molecules where B3LYP puts two states within 0.5 eV. Each would need its own preregistration and its own tolerances.
