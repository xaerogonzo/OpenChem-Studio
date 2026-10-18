# Fukui v3: the search for other states of the cation

Written 2026-10-18, before the third check of the calculator is preregistered (`PREREGISTRATION.md`), while the calculation was being built. It records what was measured before the code,
what the code does and why each number in it is what it is, what was considered and not done, and what is not known. The measurements it cites are in `benchmarks/fukui_gate_2/PREREGISTRATION.md` 11.4 and its artifacts.

## 1. The problem, as measured

f- is an atom's Hirshfeld charge in the cation minus its charge in the neutral, at the neutral's geometry. A cation can have several states a few tenths of an eV apart, one for each orbital the electron may
have left, and the application's N-1 job reaches **one** of them: it starts from the neutral's orbitals, empties the HOMO, and the SCF relaxes into whichever state is nearest.

After the second gate failed (`benchmarks/fukui_gate_2/PREREGISTRATION.md` section 11):

* for **anilinium, benzaldehyde and thiophene** the published f- matches, to 0.0011 to 0.0021, a cation state **0.094, 0.145 and 0.449 eV above** the lowest state this calculation finds (probe 1, 44 jobs, 11 molecules);
* **the state the application's own input reaches for benzaldehyde is not a function of the structure**: 14 runs of one molecule at one level gave one state in 6 and another, 0.145 eV higher and up to 0.05 away in f-, in 8; what decided it was a
  rotation of one geometry (1 of 4), a displacement of 0.001 A (0 of 4 reached the higher state) or the embedding the geometry was optimized from (2 of 5). Probe 4 (`landing_check.py`).

So the number the calculator printed for such a molecule was a draw. The search of v3 does not make it match the published numbers (it reads the LOWEST state, and for these three molecules the lowest is the one that does not); it makes it **a function of the structure**, and says
when another state is close.

## 2. What was measured before the code was written (exploratory, nothing here is a gate)

A compound ORCA input can hold the neutral, the ordinary cation job and further cation jobs that **start from the neutral's orbitals with the hole forced into the HOMO-k**, and the application's service can run it unchanged:

* the first job of a compound input writes `<name>.gbw` and the later ones `<name>_job2.gbw`, `<name>_job3.gbw` ...; the service always names its input `job.inp`, so `%moinp "job.gbw"` is the neutral's orbitals in every run;
* `%scf Rotate {HOMO-k, HOMO, 90, 1, 1} end` (the beta orbitals, the probe's own procedure) inside such a job gave states that converged in every case tried, and the output's `INITIAL GUESS:` line says MOREAD for it exactly as for an ordinary
  later job: **the guess line cannot tell a hole start from a default one**, but ORCA echoes the whole input at the top of its output, and that echo names every job's `Rotate` (read back by `OrcaQuantumEngineProvider._echoed_holes`);
* HCN (3 atoms, 5 jobs): 11 s at 4 cores. Benzaldehyde (14 atoms, 5 jobs, 8 cores): 83 s. **The cost of the search, measured afterwards (the pilot and the gate, 4 cores, six jobs at once): about 2.5 times a Fukui run of v2's three jobs** (benzaldehyde 100 to 144 s without it, a median of 273 s with it; anilinium at 8 cores 28 to 34 s against 66 to 83 s), because the three hole jobs are unrestricted cations like the existing one and the number of unrestricted jobs goes from two to five; an earlier figure in this file, about 50 s for v2's three jobs at 8 cores, was not measured and was wrong.

Four molecules (ORCA's own B3LYP/6-31G* optimized geometries, or RDKit's for the first two runs), recorded as the fixtures of `tests/test_orca_fukui_v3.py`:

| Molecule | What the cation jobs found | f- of the state the default job reached vs the lowest |
|---|---|---|
| HCN | a pi state (the default job and the HOMO-1 hole; the HOMO is a degenerate pair with identical charges) and a sigma state 0.391 eV above it (the HOMO-2 and HOMO-3 holes) | 0.085 apart at C |
| benzaldehyde | the default job reached the state 0.145 eV above the lowest; the HOMO-1 hole a state 0.127 eV above; the HOMO-2 and HOMO-3 holes the lowest | 0.128 apart at O (0.34 against 0.21) |
| benzene | the HOMO is an e1g pair: the default job and the HOMO-1 hole reach two states 0.002 eV apart whose Hirshfeld charges differ by up to 0.104 in one atom; the HOMO-2 and HOMO-3 holes an e2g pair 2.6 eV up | one determinant gives a lopsided f- (0.164 at one carbon, 0.152 at another); the mean of the two is uniform to 0.001 |
| water | the HOMO-1 hole 2.2 eV above and the HOMO-2 hole 6.4 eV above the default state | nothing within 0.5 eV |

Methane was also run (RDKit geometry): the default job, the HOMO-2 and the HOMO-3 holes reached one state and the HOMO-1 hole one 0.105 eV above it, which is not the third component of a degenerate level and shows
that a single-determinant description of a triply degenerate cation is not what these jobs give. **Degenerate cations of more than two components are not claimed.**

### The pilot (exploratory, 2026-10-18; `pilot_v3.py`, `artifacts/pilot_benzaldehyde_search_*.log`)

The question of the second gate's probe 4, asked of the code as built: benzaldehyde (ORCA B3LYP/6-31G* geometry from the seed-7 embedding), the application's own input through real ORCA at 4 cores, on that geometry (the reference), on 4
rigid rotations and on 4 copies with every coordinate displaced by Gaussian noise of 0.001 A (the same rng stream for both columns), each read with the application's own parse. The control is the same nine runs with the search off, which is v2's input.

| Run | f- against the reference, search OFF (v2) | search ON | states the search found / the competing state it reported |
|---|---|---|---|
| rotation 0 | 0.0002 | 0.0004 | 2 / 0.147 eV |
| rotation 1 | **0.1282** | 0.0001 | 1 / none |
| rotation 2 | 0.0000 | 0.0002 | 3 / 0.127 eV |
| rotation 3 | 0.0002 | 0.0001 | 2 / 0.145 eV |
| displacement 0 to 3 | **0.1301, 0.1268, 0.1286, 0.1276** | 0.0020, 0.0019, 0.0016, 0.0021 | 1 / none, in all four |
| the reference | | | 3 / 0.127 eV |

**Without the search 5 of 8 perturbed runs gave the other state's f- (0.13 at the oxygen); with it the worst difference was 0.0021**, which is what a 0.001 A displacement moves f- by within one state. **The search makes f- a function of the structure for this molecule.**
It does **not** make the report of the competing state reproducible: it was reported in the reference and in all three rotations that kept the molecule planar enough, and in none of the four displaced geometries, where every start relaxed into the lowest state. A displaced
geometry has no symmetry for the two states to keep apart, and an excited state that is not a stationary point of the SCF cannot be reached by starting near it. **So the absence of a note is not evidence that no other state exists**, and the gate measures how often the note appears (the reported arm).

**ORCA's own DeltaSCF** (`! DeltaSCF` with `%scf IonizeBeta <orbital> end`, which holds the hole by the maximum overlap method) was tried on the reference geometry as a way to make the report reproducible: the HOMO-hole state came out at the 0.145 eV state and the HOMO-1 hole at the 0.127 eV one, and **the HOMO-2 hole did not converge, which
ends a compound run**. The lowest state, which the relaxed starts reach from the HOMO-2 and HOMO-3 holes, is therefore not the state with the hole held in any of the three, so holding the hole would have lost it. Not adopted (`exp_mom.py`).

## 3. The calculation

**The jobs** (`chem/fukui_plan.py`). For a closed-shell species with valence orbitals below its HOMO, three more N-1 jobs: the cation from the neutral's orbitals with the hole in the HOMO-1, the HOMO-2 and the HOMO-3. The HOMO's number is
read off the electron count (`searchable_holes`), which is exact only where no electron is taken out of the problem, so **a molecule with an element heavier than krypton gets no search** (its basis set may use a core potential), and a hole that would reach the core is dropped.
The order is load-bearing: ORCA ends a compound input at the first job that does not converge, so **the jobs the answer needs come first and each optional one after everything it is optional for**: for a neutral species or a cation the holes follow its N+1 state (f+ is half the answer);
for an anion, whose dianion is optional and is the one job that is only the basis set's state, the holes come **before** the dianion.

**The reading** (`chem/fukui_states.py`, `read_cation`), over every finished N-1 job. Two jobs reached the **same state** when their energies differ by no more than `LEVEL_MARGIN_EV` = 0.01 eV and no atom's charge by more than `CHARGE_TOLERANCE` = 0.005.
f- is read from the **lowest** state. States within 0.01 eV of the lowest that are nevertheless different (a **degenerate level**) are **averaged**, so that the result does not depend on which component the SCF found. Every other state within `WINDOW_EV` = 0.5 eV is **reported as competing**,
with how far its f- is from the one read and at which atom; states beyond the window are counted. The default start's job is the one whose charges are read when it reached the lowest state, so a run in which the search found nothing new gives exactly what v2 gave.

**Where each number comes from.**

* *0.01 eV and 0.005.* In probe 1 (11 molecules, 44 jobs, every one converged) starts that reached one state agreed to **0.0004** in every atom's charge and **0.004 eV** in energy, and the closest two different states were **0.018 eV** apart and **0.085 or more** apart in a charge (benzaldehyde's two,
  0.22). Both margins sit in those gaps, the energy one with a factor of 2.5 on each side and the charge one with more than a factor of 10.
* *0.5 eV.* **Not measured**; the size of difference a B3LYP energy difference between cation states cannot be trusted to order, taken as 0.5 eV. It includes the three molecules above (0.094, 0.145, 0.449) and HCN's sigma state (0.392) and excludes the next closest in probe 1 (pyrrole 0.837,
  aniline 1.21, furan 1.37). **The three were seen before the window was chosen**, and the gate says so.
* *Three holes.* The probe's own count; on its eleven molecules a hole in the HOMO-3 always ended in a state the default, HOMO-1 or HOMO-2 start had already found. A choice from eleven small molecules, not a derived number, and **a molecule with more orbitals close to its HOMO is said to have been
  searched only so far**: when the occupied orbital below the deepest hole lies within 0.6 eV (the window plus 0.1 eV, the largest amount by which a state gap differed from the orbital gap in probe 1 was 0.062) of the HOMO, the result says a state with the hole there may exist and was not looked for.

**What a result says** (`chem/fukui.py`): nothing when the search ran to the end and found no other state within the window; one sentence for a degenerate level that was averaged; one for the states that compete; one for a search that did not run to the end (a hole job ORCA could not
converge, or that never began because ORCA ended the run earlier); one when the search stopped short of orbitals close to the HOMO; and, for a run with no hole start at all (the setting is off, or the molecule has no search), a sentence saying so and what that cost benzaldehyde.
The provenance carries `cation_search`, `cation_states_found`, `cation_competing_ev`, `cation_degenerate_states` and `cation_note`, and the starts counted include the holes.

**The switch** (Settings > Quantum chemistry, `FUKUI_CATION_SEARCH`, on by default): three more ORCA jobs a run, a few tenths more time.

## 4. What this does not claim

* **Nothing about published values.** For benzaldehyde, anilinium and thiophene the lowest state is not the one the published numbers belong to, and the search reads the lowest. Which state a condensed Fukui function ought to describe is not decided here, and the order of states 0.1 eV apart in a B3LYP
  ΔSCF is itself uncertain; the result reports the states so that the reader can see that.
* **Nothing about HCN, pyrrole, furan or the sulfur of thiocyanate**, which the second gate missed and the cation-state candidate does not explain.
* **Nothing about degenerate levels of more than two components** (methane above), and the degenerate average is a rule of the calculation and not a measured result beyond the two benzene components.
* **Nothing about a cation whose lowest state the holes do not reach**: the search covers the four highest occupied orbitals, and says when more may lie close.

## 5. Considered, and not done

* **A caveat only**, with no search, firing when the neutral's HOMO and HOMO-1 are within a gap: cheaper, and the second gate's 11.6 (b). It would say a state may be close without saying which or how far its f- is, and it would not make f- reproducible. Not chosen; nothing prevents adding it later for a run with the search off.
* **A Boltzmann or other weighted average over the states.** Continuous in the structure, where the margin of the rule above is a step; but it makes f- a thermal ensemble quantity, which is not what is defined, and it would move the printed number a little for every molecule with a state within about 0.1 eV, including every one in
  the published tables. Not chosen.
* **Choosing the holes from the neutral's orbital energies**, so that a molecule with many close orbitals gets more holes and one with few gets fewer. It needs the neutral's output before the input is written: a two-stage run, and a change to the service's one-process-per-request design. The orbital-energy caveat above is what stands in for it.
* **ORCA's stability analysis** (`STABPerform`), which finds a lower solution of the same occupation when the converged one is a saddle point. A hole state is a different local minimum, not a saddle of the ground state, so it would not move between them.
* **Symmetry-constrained or MOM/IMOM calculations**, which need the symmetry or the occupation to be known in advance.

## 6. Decisions

Alex, 2026-10-18: "Yeah, let's do the 3 cation-state search, why not?" (the search of 11.6 (a), asked after the second gate and the anion f+ were opened as pull requests).
