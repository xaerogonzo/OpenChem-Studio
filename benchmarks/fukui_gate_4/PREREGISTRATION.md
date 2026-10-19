# The fourth Fukui gate: preregistration

> **FROZEN, 2026-10-18, by the commit that wrote this banner.** From that commit on sections 0 to 10 are fixed, together with the calculation it tests (`src/openchem/chem/` and what it calls: unchanged from the third gate's, the
> code of PR #380 at commit `c5f2066f`, which this commit leaves untouched under `src/openchem/chem/`), the species, the references, the rules and the judge (`app/fukui_gate_4.py`, `tests/test_fukui_gate_4.py`; every rule of the judge was broken once, in a copy, and a test caught it: the mutation check of 2026-10-18) and the runner (`run_gate.py`). Section 11 is where the outcome is written, after the run and after nothing else.
> **When it was frozen no ORCA job of a decided molecule had been run at this calculation** except where section 2 says so; the four calibration molecules had been, and their numbers were seen (sections 2 and 3). It follows the answers
> Alex gave: a pass changes wording only and the calculator stays experimental; the machine's cores may be used.

This is the fourth preregistered check of the calculator **Fukui functions (Hirshfeld)** (`orca.fukui`). The first three ended in **FAIL by 0.0014 on one quantity**, **FAIL, 33 of 47 numbers within 0.02**
and **FAIL on one run of 114** (`benchmarks/fukui_gate/`, `fukui_gate_2/`, `fukui_v3/`); each is final and none is touched here. This one asks the question none of them could.

## 0. Why a fourth gate, and what it is built on

Fukui v3 reads f- from the **lowest** cation state it finds, because the one N-1 job of the earlier versions reached whichever state ORCA's SCF fell into. The third gate showed the reading is reproducible,
complete and not a regression, and said what it could not say: **no reference with identified cation states was used, so nothing decided whether the lowest state the search reads f- from is the state the
experiments call lowest.** For thiophene the second gate's probes found that the published f- belongs to a state 0.449 eV above the lowest, and the explainer says so; that was an inference from our own calculation.

Alex asked (2026-10-18) for more preregistered checks against the literature, and supplied the papers (they are in his library; `docs/sources.toml` records each one used here).
**The literature has what was missing**: photoelectron bands whose orbitals are assigned (which orbital the hole is in), and ab initio ionization energies for each. For a planar molecule the kind of a hole is
exactly readable from ORCA's own output (section 3), so a state the search finds can be named a sigma or a pi hole and compared with the literature's lowest state.

NIST's WebBook was looked at first and does not do this: it lists one first ionization energy per source and no band, state or orbital label.

## 1. The claim, and what a pass does not say

> On ORCA 6.1.1, at `B3LYP/6-31G*` and on the geometry ORCA optimized at that level (planar, oriented with its plane as xy), for **seven molecules never run through any probe or gate** (section 4):
> **C1.** the lowest state of an exhaustive search (a hole in every orbital from the HOMO-1 to the HOMO-7) is a **sigma** hole for the three diazines (pyridazine, pyrimidine, pyrazine) and a **pi** hole for imidazole,
> pyrazole and oxazole, as the lowest state of the sources is;
> **C2.** for the three diazines the **second** distinct state is a pi hole;
> **C3.** the **gap** from the lowest state to the lowest state of the other kind is within **0.25 eV** of the range the sources print for it;
> **S.** for selenophene, the two highest pi orbitals being near-degenerate: the two lowest states are within the gap the sources print (plus 0.25 eV), both pi, one **a2** (no spin on the heteroatom) and one **b1**
> (much), and the application's own run says another state of the cation lies close (its note has that sentence);
> **C5.** the search the **application** runs (the default job and holes in the HOMO-1, -2 and -3) finds the lowest state the exhaustive search does, to 0.01 eV.

A pass does **not** say that:

* f- is right for any of them: no f- is compared with anything here, only which cation state f- would be read from;
* the second, third or fourth bands are right, other than the second of a diazine (C2): the full ladders are reported in section 10 and decide nothing;
* **a B3LYP energy difference orders states less than about 0.25 eV apart correctly**: the gap tolerance says so;
* anything about a molecule that is not planar (the reading of a state's kind needs the molecular plane), an element heavier than krypton, a charged species, or any other level of theory;
* oxazole's energies are first-hand (they are Palmer et al.'s, quoted in a 1982 paper) or that pyrazole's rest on more than one old table (section 4);
* the calculator's support level: **it stays experimental, hidden and not validated whatever the outcome** (section 8).

## 2. What has been run or seen before the freeze, disclosed

* **The third gate's results for four of the five calibration molecules** (pyridine, thiophene, pyrrole, furan) were seen: for each, which states the search found within 0.5 eV (pyridine two, 0.12 eV apart; thiophene two, 0.45 eV apart;
  pyrrole and furan one), and f- of the lowest. That is why they are calibration and decide nothing.
* **Before this file was written, on 2026-10-18, the four were run once more at the exhaustive search with their spin read** (section 3), to check the reading and to fix its limits. The same four were then compared
  with the literature *with those results in view*: pyridine with [source:trofimov2017] (read before), thiophene, pyrrole and furan with [source:trofimov2008] (read before). **The gap tolerance (0.25 eV) was set after that
  comparison**, from the largest of its errors (section 3), so it is informed by seen data and is tested on the seven unseen molecules.
* **No ORCA job of a decided molecule had been run at this calculation**, with one exception: **selenophene's neutral single point** (B3LYP/6-31G*, an unoptimised RDKit geometry, `FINAL SINGLE POINT ENERGY` -2555.776359 Eh),
  to see that ORCA has a 6-31G* basis for selenium. No cation job, no charge and no spin of it was looked at. RDKit embeddings of the seven were made (for the SMILES of section 4), nothing more.
* **Every reference number in section 4 was read before any decided molecule was run**, from the papers in Alex's library, off the page images where the text layer was unusable. The ranges are the rule of section 4
  applied to what those tables print; none was chosen after a result.
* **Oxazole and pyrazole were added after the other five**, when two further tables ([source:kobayashi1982], [source:cradock1973]) were read, also before any run.
* **The machine's cores are used**, four per ORCA job, as in the earlier gates.

## 3. The reading of a state's kind, and its calibration

ORCA prints, for an open-shell job, the Loewdin spin population of every function of every atom (`LOEWDIN REDUCED ORBITAL CHARGES AND SPIN POPULATIONS`, in its default output). A pi orbital has a nodal plane in the
molecular plane, so the electron a pi hole leaves unpaired is in `pz` (and the d functions with a z) when the plane is xy, and a sigma hole's is in `s`, `px` and `py`. **The out-of-plane fraction of a state is the sum,
over all atoms, of its `pz`, `dxz` and `dyz` spin populations**, divided by the total spin (`out_of_plane_fraction`). The limits are fixed from symmetry and not from any decided molecule:

| fraction | kind |
|---|---|
| at least **0.75** | a **pi** hole |
| at most **0.25** | a **sigma** hole |
| between | not classified: a claim that needs the kind cannot be decided (NOT EVALUABLE, section 7) |

In a five-membered ring with a heteroatom, a pi hole in the **a2** orbital has a node through the heteroatom and leaves **at most 0.10** of the spin on it; one in the **b1** orbital leaves **at least 0.20**
([source:schafer1973]: the b1 orbital is about 80 % on the sulphur of thiophene). Between the two limits the state is not classified.

**Calibration, measured on 2026-10-18 before the freeze** (`artifacts/calibration/`; the runner of this gate, run with `--calibration`; B3LYP/6-31G*, the third gate's optimised geometries rotated to the xy plane;
`states_probe.py` gave the same numbers). Every pi state read 1.000 and every sigma state 0.000 (to three places):

| molecule | state (eV above the lowest) | kind, heteroatom spin | the literature's | error |
|---|---|---|---|---|
| pyridine | 0.000 | sigma (spin on N 0.762) | 7a1, sigma lone pair, lowest at EOM-IP-CCSDT ([source:trofimov2017]) | |
| | 0.123 | pi (N -0.069) | 1a2, +0.15 | -0.03 |
| | 0.803 | pi (N 0.388) | 2b1, +0.85 | -0.05 |
| | 2.973 | sigma | 5b2, +3.17 | -0.20 |
| thiophene | 0.000 / 0.449 | pi, S -0.071 (a2) / pi, S +0.580 (b1) | 1a2 lowest; the gap 0.3 (ADC(3)) and 0.5 (experiment) ([source:trofimov2008]) | -0.05 against the experiment |
| pyrrole | 0.000 / 0.836 | pi, N -0.056 (a2) / pi, N +0.399 (b1) | the gap 0.7 and 1.0 | -0.16 |
| furan | 0.000 / 1.370 | pi, O -0.033 (a2) / pi, O +0.322 (b1) | the gap 1.5 and 1.4 | -0.03 |

The calibration records carry `dirty: true`: `src/` then held the new, uncommitted judge module, and nothing under `src/openchem/chem/` differed from the commit. The application's own run found the lowest state of the exhaustive search in all four (0.0007, 0.0000, 0.0000, 0.0000 eV from it). **The ladder of pyridine's four lowest states follows the highest-level calculation's**
in kind and order, and its three gaps to within 0.20 eV. That the lowest state of pyridine is sigma agrees with EOM-IP-CCSDT and not with delta-SCF at the Hartree-Fock level or ADC(3), which put the pi state first; this
method puts it lowest by 0.12 eV, and [source:trofimov2017] itself finds the order method-dependent, so pyridine is not decided.

**The gap tolerance, `GAP_TOLERANCE_EV` = 0.25 eV**, is a little above the largest of the four errors against the experimental or highest-level gap (0.16 eV, pyrrole; the pyridine sigma state's 0.20 is a higher state and a
different quantity), and of the order of the spread between two printed values of one gap (0.1 to 0.25 eV, section 4). It is fixed here and not changed after the run.

## 4. The molecules and what the sources print

**Seven decided molecules**, all planar, optimised by ORCA (`B3LYP 6-31G*`, from an RDKit ETKDG + MMFF embedding with seed 7; if that optimisation does not converge, seeds 8 and then 9). **Four calibration molecules**
(section 3). The reference of each decided molecule is the **range of the gap from its lowest state to the lowest state of the other kind** (for the diazines the second state; for selenophene the gap between its two pi states, whichever
is lower) over every correlated calculation and every experiment the sources print, at the largest basis each printed, **never a Koopmans value and never a CAS-SCF value without dynamic correlation**. Each value is
printed in `app/fukui_gate_4.py` and `tests/test_fukui_gate_4.py` checks that the gap printed beside each pair of energies is their difference and that the range is the smallest and largest of them.

| molecule | the lowest state(s) | the range | what it is made of |
|---|---|---|---|
| pyrimidine | sigma (n-), then pi, n, pi | **0.48 to 0.80** | ADC(3)/cc-pVDZ++ 0.48 and OVGF/aug-cc-pVTZ 0.60 ([source:shojaei2010] Table 1); PES 0.70 (the same table); He I 0.68 ([source:gleiter1972] Table 2); 0.80 (Asbrink et al. as tabulated in [source:stener2011] Table 1). The order n, pi, n, pi is confirmed by angle-resolved spectra ([source:piancastelli1983]) |
| pyrazine | sigma (n+), then pi, n, pi | **0.55 to 0.80** | He I 0.55 ([source:gleiter1972]; the order confirmed by [source:piancastelli1983]); 0.80 (Fridh et al. as tabulated in [source:stener2011]). Experiment only: no correlated calculation of it is in hand |
| pyridazine | sigma (n-), then pi, pi, n | **1.30 to 1.52** | He I 1.30 ([source:gleiter1972]); experiment 1.34, NEVPT2 1.50 and 1.52 ([source:holland2013] Table 1, cc-pVTZ) |
| imidazole | pi (3a''); the lowest sigma state is 15a' | **1.23 to 1.67** | experiment 1.30, best theoretical estimate 1.28, CC3 1.23, EOM-IP-CCSD 1.24, OVGF 1.45, IP-ADC(3) 1.62, Dyson ADC(3) 1.67 ([source:patanen2021] Table II) |
| pyrazole | pi (3a''), pi (2a''), then sigma (15a') | **1.55** | one old He I table, 9.15 and 10.7 ([source:cradock1973] Table 1) |
| oxazole | pi, sigma (n), pi | **1.36** | 9.83 and 11.19, quoted from Palmer et al. 1977 in [source:kobayashi1982] Table 1 (the original is not held); the order is Palmer's ab initio assignment, supported by a perturbation-theoretic reading and band shape there |
| selenophene | the two highest pi orbitals near-degenerate | **0.0 to 0.1** (a size, whichever is lower) | ADC(3) 8.7 and 8.7: 0.0; OVGF 1a2 8.6 and 2b1 8.7: 0.1; experiment 2b1 9.0 and 1a2 9.1: 0.1 ([source:trofimov2008] Table 2); [source:schafer1973]: "nearly degenerate" |

SMILES (RDKit order is the application's): pyrimidine `c1cncnc1`, pyrazine `c1cnccn1`, pyridazine `c1ccnnc1`, imidazole `c1c[nH]cn1`, pyrazole `c1cc[nH]n1`, oxazole `c1cocn1`, selenophene `c1cc[se]c1`.
**What each is for.** The three diazines are the n/pi pairs where the lowest state is hardest to read and the sources agree it is sigma. Imidazole, pyrazole and oxazole put a pi state lowest with the lone pair above it, the
opposite order, so a search that merely preferred sigma states would fail them. Selenophene is the near-degenerate pair. None of the seven was in any earlier gate.

## 5. Procedure

For each decided molecule, with ORCA 6.1.1 at `B3LYP 6-31G*`, four cores per job:

1. optimise the geometry (seed 7; seeds 8 and 9 only if it does not converge) and **rotate it so that its plane is xy**; the largest distance of an atom from the mean plane is recorded and must be at most **0.05 A**;
2. **the exhaustive search (`E`)**: the application's own compound input with holes in the HOMO-1 to the HOMO-7 (the application's `OrcaQuantumEngineProvider._build_fukui_input`), and for every N-1 job its energy, its
   spin populations and its kind;
3. **the application's own run (`A`)**: `OrcaQuantumEngineProvider.build_input` and `_condensed_fukui` on the same geometry, the cation search on, recording the energy of the state f- is read from and the note.

Jobs within 0.01 eV of each other are one state (the application's own reading rule, chained as it is), read from the lowest of them. A **state's kind is that of its lowest job**; if the jobs of one state do not
agree about their kind the state is not read.

## 6. The claims, exactly

For each decided molecule, the states of `E` lowest first:

* **C5.** The energy of the state `A` read f- from is at most **0.01 eV** above the lowest state of `E`. (Below it does not fail: it is no fault to find a lower state.)
* **C1** (the six molecules with a stated lowest kind: the three diazines, imidazole, pyrazole, oxazole). The lowest state's kind equals the stated one.
* **C2** (the three diazines). The second distinct state is a pi hole.
* **C3.** The lowest state of the **other** kind than the lowest state's lies at a gap, in eV, of at least the range's lower end minus 0.25 and at most its upper end plus 0.25. If no state of the other kind was found among
  the seven holes, C3 fails.
* **S** (selenophene). **S1:** the two lowest states are both pi, one with the spin on Se at most 0.10 (a2) and one at least 0.20 (b1). **S2:** the gap between them is within `0.0 to 0.1` plus or minus 0.25.
  **S3:** the application's own run reports a note that says "Another state of the cation lies" or, for several, "Other states of the cation lie" (`CLOSE_STATE_SENTENCES`; a note that says something else does not count). One state found, or a second that is sigma, fails S1.

## 7. The verdicts

* **NOT EVALUABLE** (nothing is claimed): an ORCA other than 6.1.1; records from more than one commit or from a `src/` that differed from its commit; a decided molecule with no record of `E` or of `A`; a geometry not
  planar to 0.05 A; a state a claim needs that is not classified, absent, or whose jobs disagree about their kind; selenophene's spin on Se between 0.10 and 0.20 for a state.
* **FAIL**: the search reads f- from the wrong **kind** of state (any C1 or C2 or S1 not holding), or a job could not be computed in three attempts.
* **PARTIAL**: every kind is right and a **distance** is not (any C3, S2 or S3), or the application's own search missed the lowest state (C5).
* **PASS**: every claim holds.

## 8. After each outcome

The calculator is **experimental, hidden and not validated whatever the outcome**, and no outcome changes code under `src/openchem/chem/`.

* **PASS**: the explainer (`docs/explainers/reactivity.md`) and the changelog say that for seven further planar molecules, from three families, the lowest state the search reads f- from is the kind of state the literature
  assigns to be lowest and its distance to the other kind is within 0.25 eV of the literature's range, with the limits of section 1. Wording only.
* **PARTIAL**: the same, naming each distance or application search that missed, its size and the molecule.
* **FAIL**: the explainer and the changelog say which molecules' lowest (or second) state the search reads f- from the wrong kind of, as the literature has it, and the Fukui result's note for a molecule of that family is a
  separate decision for Alex, not made here. The failure is not tuned away: no limit, tolerance or rule of this file changes after a decided result.
* **NOT EVALUABLE**: repeat only as section 9 allows.

## 9. What may be repeated, and what may not

* A job ORCA could not complete may be repeated unchanged **up to three attempts**; a job that completed is never repeated (a record with `completed: true` is read back, not run again). A geometry optimisation that does not
  converge is repeated from the next seed (8, then 9), and the seed that gave the geometry is stored beside it.
* A run that is NOT EVALUABLE for an instrument or record reason may be repeated after its cause is fixed, the first records kept in `runs.jsonl`; a species whose geometry is not planar may be re-optimised from the next seed.
* **A decided outcome is final**: the gate is not re-run to see whether the number moves, a tolerance or limit is not changed after seeing a decided result, and a state is not reclassified.
* Anything measured after the outcome is written in section 11 as **after the outcome**, with what was seen.

## 10. The reported arm: written beside the outcome, and never decides

* Every decided molecule's **full ladder**: every state `E` found, its energy above the lowest, its kind and its spin on the heteroatoms, against the further bands the sources print (diazines' third and fourth, pyrazole's
  second, oxazole's third, imidazole's second pi state), and the size of each difference.
* Whether the application's note appears wherever the second state lies within 0.5 eV (the window), and what it says.
* How long each job took (the exhaustive search against the application's own run).
* The four calibration molecules' records, which are in `artifacts/calibration/`.

## 11. Outcome

### 11.1 The run

The runner was started on 2026-10-18 at the frozen commit `43ce522c` (a clean `src/`), seven species at once, four cores each. **It stopped on selenophene**: ORCA prints a two-letter element's line of the spin block with no space
before the shell (`3 Ses`) where a one-letter element has one (`0 C s`), so the parser read the nine-atom block as eight and raised, in the first selenophene job, before any record of it was written. The six other species
had completed. **No decided result had been read** (the log showed `completed=True` and the seconds). To find the cause the first selenophene job's spin block was read: its charge half for selenium and the s-shell spin of every atom. **That is
all that was seen of a decided state before the fix**; it was not used for anything and nothing was changed on account of it.

The fix is commit `c6c3bb3c`: the pattern of `_ATOM_LINE` now allows the missing space, and a test reads the real block that exposed the fault (it fails with the old pattern). Nothing else of the judge, the rules or the runner
changed. The judge refuses records from more than one commit, so **all seven species were run again at `c6c3bb3c`** (section 9: an instrument fault may be repeated after its cause is fixed, the first records kept):
`artifacts/runs_first_attempt.jsonl` holds the first run's six species and `artifacts/runs.jsonl` the second's fourteen records, from one commit, ORCA 6.1.1, a clean `src/`. Every job completed at the first attempt.
(After the outcome, section 11.4 compares the two: the six species' records are identical.)

### 11.2 The outcome: PARTIAL

`artifacts/verdict.json`. **Every claim about the kind of state held; one distance missed.**

| claim | holds | what was found |
|---|---|---|
| **C1**, the lowest state's kind | **6 of 6** | pyrimidine, pyrazine, pyridazine: sigma (out-of-plane fraction 0.000); imidazole, pyrazole, oxazole: pi (1.000) |
| **C2**, the second state of a diazine is pi | **3 of 3** | pyrimidine +0.909 eV, pyrazine +0.683, pyridazine +1.564, all 1.000 out of plane |
| **C3**, the gap to the lowest state of the other kind | **5 of 6** | pyrimidine 0.909 (range 0.48 to 0.80, allowed 0.23 to 1.05); pyrazine 0.683 (0.55 to 0.80); pyridazine 1.564 (1.30 to 1.52, allowed 1.05 to 1.77); imidazole 1.174 (1.23 to 1.67, allowed 0.98 to 1.92); oxazole 1.252 (1.36, allowed 1.11 to 1.61); **pyrazole 1.157 against 1.55, allowed 1.30 to 1.80: MISSED, 0.143 eV below the allowed range** |
| **S**, selenophene | **3 of 3** | S1: two pi states, the spin on Se -0.079 (a2) in the lower and +0.682 (b1) in the upper; S2: 0.182 eV apart (allowed up to 0.35); S3: the application's note reads "Another state of the cation lies 0.18 eV (its f- differs by up to 0.226, at Se (atom 4))" |
| **C5**, the application's own search | **7 of 7** | the lowest state found to within 0.0037 eV of the exhaustive search's in every species (0.0009, 0.0000, 0.0037, 0.0000, 0.0001, 0.0015, 0.0000) |

Under the rules of section 7 a kind failure is FAIL and a missed distance with every kind right is **PARTIAL**. **The outcome is final.**

### 11.3 The reported arm (`artifacts/report.txt`; decides nothing)

**The full ladders**, in eV above the lowest state (kind), against the further bands the sources print, measured the same way:

| molecule | ours | the sources print |
|---|---|---|
| pyrimidine | 0 (sigma), 0.909 (pi), 1.356 (sigma), 1.735 (pi) | n 0, pi 0.68, n 1.50, pi 1.66 ([source:gleiter1972]); Asbrink et al. (vertical): n 0, pi 0.8, pi 1.5, n 1.8; ADC(3): n 0, pi 0.48, pi 1.37, n 1.48 ([source:shojaei2010]). **The sources disagree about the order of the third and fourth bands, 0.1 to 0.2 eV apart** (n then pi: Gleiter and Piancastelli; pi then n: Asbrink and ADC(3)); ours is n then pi, Gleiter's order |
| pyrazine | 0, 0.683 (pi), 1.735 (sigma), 2.173 (pi), then sigma 3.871, pi 4.832, sigma 5.219 | n 0, pi 0.55, n 1.72, pi 2.14 ([source:gleiter1972]): the third and fourth within 0.015 and 0.033 eV |
| pyridazine | 0, 1.564 (pi), 1.962 (pi), 2.001 (sigma) | experiment 0, 1.34, 1.93, 2.03; NEVPT2 0, 1.52, 1.94, 2.09 ([source:holland2013]): the third and fourth within 0.03 and 0.09 eV |
| imidazole | 0 (pi), 1.174 (sigma) | the sigma state 1.28 (best estimate), 1.3 (experiment); a second pi state at 1.49 ([source:patanen2021]) was **not found** |
| pyrazole | 0 (pi), 1.157 (sigma) | the sigma state 1.55 and a second pi state at 0.73 ([source:cradock1973], the order pi, pi, n); **Baker et al. 1970 assign the 10.00 eV band to the lone pair and the 10.73 eV band to the second pi orbital (pi, n, pi): the sigma state at 0.61 and the second pi at 1.34.** A second pi state was **not found** |
| oxazole | 0 (pi), 1.252 (sigma) | the sigma state 1.36; a third band, pi, at 1.97 ([source:kobayashi1982]) was **not found** |
| selenophene | 0 (a2), 0.182 (b1) | the gap 0.0 to 0.1, either order ([source:trofimov2008]) |

**How many jobs reached each state** (of the eight N-1 jobs: the default and the seven holes): pyrimidine 5, 1, 1, 1; pyrazine 1, 1, 2, 1, 1, 1, 1; pyridazine 5, 1, 1, 1; imidazole, pyrazole and oxazole **7 and 1**; selenophene 5 and 3.
**The application's note appeared in selenophene only**, where a second state lies 0.18 eV above (inside its 0.5 eV window); in every other species the second state lies above the window (0.68 to 1.56 eV).
**Time**: the exhaustive search 203 to 383 s per molecule and the application's own run 86 to 107 s (four cores, seven molecules at once).
**The four calibration molecules** are in `artifacts/calibration/` (section 3).

### 11.4 After the outcome (written with the result in view; decides nothing)

* **The first run and the second are the same.** For the six species both runs completed, every N-1 job's energy and out-of-plane fraction is identical (a difference of 0 eV) and every input has the same sha256: the fix changed the parse of a two-letter element and nothing else.
* **Pyrazole's reference is contested in its ORDER, not only in a value, and an earlier version of this bullet was wrong.** The range was one old table's pair (9.15 and 10.7, [source:cradock1973]: the order pi, pi, n, a sigma gap of 1.55). The two Baker, Betteridge, Kemp and Kirby papers of 1970, held in the library
  and read after the outcome, give pyrazole's three lowest bands as 9.5, 10.1 and 10.8 (*Chem. Commun.* 1970, 286) and, vertical, 9.39, 10.00 and 10.73 (*Anal. Chem.* 42, 1064, Table I), **and assign the first and the third to the two pi orbitals (their Table IV, pi3 9.39 and pi2 10.73) and so the middle one,
  10.00, to the nitrogen lone pair: the order pi, n, pi, a sigma gap of 0.61 eV.** (An earlier version of this section said that Baker's papers put the sigma gap at 1.3 to 1.34 eV, within tolerance of the calculation. That read the 10.73 band as the sigma state, which Baker's own Table IV contradicts; it was wrong and is corrected here.)
  The calculation's 1.157 lies between the two assignments' 0.61 and 1.55, and the gate has no way to choose between them: **the miss is a weak, contested reference and not evidence about the calculation**, and under Baker's order the second pi state would be at 1.34 eV, which the search cannot find in any case (next bullet). The first band alone moves between 9.15 and 9.5 eV with the paper. **This does not change the outcome**, which was fixed by the range chosen before the run.
* **A signed pattern in the sigma-pi gaps, small.** Of the five uncontested decided gaps compared with a printed range, four lie outside it, and all four on the side where the sigma state is too low relative to the pi states: the diazines' second state (pi, above a sigma state) lies above the range by 0.109 (pyrimidine)
  and 0.044 eV (pyridazine), and the azoles' sigma state (above a pi state) below it by 0.056 (imidazole) and 0.108 eV (oxazole, whose energies are second-hand); pyrazine's is inside. Pyrazole's is excluded: its reference is contested (previous bullet). Pyridine in the calibration (a point value, 0.123 against 0.15) is the one
  comparison the other way, by 0.03 eV. That is the direction a delta-SCF that relaxes a sigma hole more than the sources' calculations do would give (the sources themselves put the relaxation of a nitrogen lone pair at 2.7 to 2.9 eV against 0.8 to 1.0 eV for a pi hole in pyridine). **It is an observation about the size and direction of the error, four numbers, none more than 0.11 eV from its range, and not a finding with a test behind it.**
* **The search cannot hold two states of the same symmetry.** In the three Cs azoles seven of the eight N-1 jobs relaxed into the lowest pi state: a second pi state (A'' like the first) is not a state a ground-state SCF started from a hole will stay in. Those states were **not found**: imidazole's second pi at 1.49 eV, pyrazole's at 0.61 to 0.73 and oxazole's third band at 1.97 (section 11.3). Where
  the two pi states are of different symmetry (selenophene's a2 and b1, both reached, the pyridine and diazine pairs) they were. The consequence is for the note about competing states: **it cannot report a second state of the lowest state's own symmetry**, so for a Cs molecule with a close pi-pi pair (pyrazole's gap
  of 0.6 to 0.7 eV is just outside the 0.5 eV window) the absence of a note is no evidence that there is none. That limit was not known to the third gate, which found its competing states by the same search. **It is also stated in the literature**: "only the lowest state of each symmetry can be treated within the delta-SCF framework" (Holland et al. 2017, 2- and 3-chloropyridine, [source:holland2017]), and the pyridine paper's own unrestricted hole calculation in C1 symmetry fell into the lowest 2A2 state ([source:trofimov2017]). And **the third gate's own records agree**: its exhaustive search found ONE state for phenol, whose two outer pi states are both A'' (the literature puts the second 0.91 eV above the first), and two for toluene, whose two outer pi states are A' and A'' (0.289 eV apart there, 0.52 in the literature).

### 11.5 What this says, and what it does not

* It says that for seven planar molecules from three families never run before, the search reads f- from **the same kind of state the literature assigns as lowest** in all six where the sources fix it, finds the second diazine state to be the pi hole the sources assign in all three, and for selenophene finds the two near-degenerate pi
  states with the node and the weight on the heteroatom in the right places; that the gap to the other kind is within 0.25 eV of the printed range in six of seven; and that the application's own search finds the lowest state in all of them. Together with the calibration (pyridine's four lowest states in the order and, to 0.2 eV, the gaps of the highest-level calculation), the
  states the search finds are, in kind and order and to within a few tenths of an eV, **the states the experiments assign**.
* It does not say that f- is right, that a B3LYP energy difference orders states less than 0.25 eV apart, anything about a molecule outside these three families, or that the sigma-state bias of section 11.4 is zero.
* The thiophene reading of the second gate (the published f- belongs to the b1 state 0.45 eV above the lowest, and "read the lowest" is the experimentally right ground state) is now supported by an independent reference and not only by our calculation: thiophene's a2 state is lowest and the b1 0.449 eV above matches the 0.3 and 0.5 eV the sources print ([source:trofimov2008]).

### 11.6 The consequence, and what was left open

Section 8 for PARTIAL: wording only, and the calculator stays experimental, hidden and not validated. The explainer and the changelog say what 11.2 found and name pyrazole's distance and the reference it rests on. Nothing under `src/openchem/chem/` changed.

**Left open** (each a decision for Alex, none made here):
* a way to hold a second state of the lowest state's symmetry (a maximum-overlap SCF or an occupation constraint by symmetry), which would let the note see a close pi-pi pair in a Cs molecule; the third gate's completeness arm would need repeating;
* the sigma-state bias of 11.4: a second functional, or the same states at EOM-IP-CCSD, on the molecules of this gate, to see whether it is B3LYP's;
* pyrazole's order, which two sources assign differently (a calculation that holds both pi states, or a correlated one, would settle it);
* proton affinity and bond dissociation energies, each with its own preregistration.

## Decisions (kept as a record)

* **2026-10-18, Alex:** "Yeah, do the pre-registered gate on the new species." The book (Kimura 1981) he could not obtain and would not pay for; the papers in section 4 are the ones he fetched. A wanted-list for the others is in
  his library (`WANTED_LITERATURE.md`, not in the repository because the DOI guard fails a tracked document with an unregistered DOI).
* **2026-10-18:** a pass changes wording only and the calculator stays experimental (his answer to the same question for the third gate, applied here).
