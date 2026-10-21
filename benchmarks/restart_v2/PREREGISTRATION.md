# Displaced restart for structures that keep an imaginary mode (protocol v2): preregistration

**Status: DRAFT, written 2026-10-21, not frozen and not run. DEFERRED by Alex on 2026-10-21: the held-out arms are still wanted but are to be done later; the PA and BDE calculators are built meanwhile from the v1 results, with the v1 errors stated (section 10).** See section 10 for the to-do and the plan to revise this draft into before it is frozen. It becomes frozen only when (1) Alex has approved the open choices in section 9, and (2) the runner and its tests are committed after this file and before the first job (`benchmarks/restart_v2/run_restart.py`, not yet written). Until then this file may change. Once frozen it changes only by an amendment section that says what and why. Where this text and the code disagree, the disagreement is fixed before the run, never after.

## 1. What this is, and what it is not

The two ORCA benchmarks (`benchmarks/proton_affinity/PREREGISTRATION.md`, `benchmarks/bde/PREREGISTRATION.md`) were run on 2026-10-20/21: proton affinity **PASS** for PA and GB with water missing, bond dissociation **PARTIAL** (|MSE| 1.53 against 1.5, three deciding bonds missing). **Their verdicts stand and nothing here revises them.** Both lost cells because a structure kept a vibrational frequency below -20 cm-1 after the one `Calc_Hess` re-run (the v1 rule), and so was dropped.

This is a **new protocol (v2)** for those structures, and a test of it on **data it was not designed on**. It is the same pattern as the tautomer work (v1 failed, v2 was preregistered and run).

## 2. What was seen first (disclosure, the most important section)

The v2 rule was designed **after** the v1 verdicts, and an **exploratory run of exactly this rule on exactly the four structures v1 dropped has already been done and seen** (`benchmarks/restart_diagnosis/`, committed): H3O+ repaired in both directions; the ethanol radical and toluene repaired in one direction each; the CH3S radical not repaired (worse). The bond enthalpies those give were also computed (ethanol O-H 102.79, toluene benzylic C-H 90.38, methanethiol S-H 83.96 kcal/mol), and it was seen that adding the first two to the v1 deciding set would move its mean error from -1.53 to about -1.46, just inside the 1.5 limit.

Consequences, fixed now:
* **The v2 run on those four structures is a reproduction, not a test.** Its outcome is known (ORCA is deterministic for a given input). It carries **no weight** in any v2 verdict.
* **A v1 verdict is never re-judged with the v2 cells added.** Doing so would be tuning the protocol until the number crossed the line, which is the one thing the thresholds exist to prevent.
* The **only** evidence this file allows for v2 is the **held-out arm** (section 5): species and bonds chosen by rule before their values are read, computed under the frozen v2 protocol, judged by the unchanged judges.

## 3. The v2 rule (everything here is fixed)

v2 is v1 (every keyword, header, structure-generation step and selection rule of the two preregistrations, unchanged) plus **one additional stage that applies only to a structure still not accepted after v1's own `Calc_Hess` re-run**, i.e. its lowest frequency is still below -20 cm-1 (or it otherwise fails v1's acceptance). For such a structure, from the **geometry of that re-run**:

1. Run `! M062X def2-TZVPD TightSCF DefGrid3 Freq` (the same functional, basis and grid; `%pal nprocs 4`, `%maxcore 3000`; charge and multiplicity as the structure's own, a radical unrestricted) and read the normal mode of the **most negative** frequency from ORCA's `.hess` file.
2. Normalize the mode so that its **largest single Cartesian component (Angstrom) is 1**, and displace the geometry by **+0.15 and by -0.15** along it. (0.15 Angstrom is the only amplitude ever tried; it is not tuned and is not varied.)
3. From each displaced geometry run v1's optimization job, **with `Calc_Hess true`** (`! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`).
4. Each of the two results is an **ordinary structure of the species**: it is accepted by v1's rules (lowest frequency >= -20 cm-1, and for a radical the skeleton test; for an ion the proton-position test) and enters v1's selection (lowest H for PA and BDE, lowest corrected G for GB) alongside the species' other structures. If neither is accepted the species is a missing cell exactly as in v1.
5. **One displaced restart only.** No iteration, no further amplitude, no other mode.

The rule changes nothing for a structure v1 accepted: **its v1 record is used as it is**, and the held-out arm below has no v1 records, so v2 is run in full there (the new stage fires only where v1's retry fails).

**Out of scope, stated so it is not mistaken for a gap:** the CH3S-type failure (the displacement did not help and the energy did not move). v2 does not claim to repair it; a structure like that is a missing cell under v2 and is **counted as one**. It is the subject of a separate possible v3 (a different electronic state or a symmetry-broken start), not designed here.

## 4. The data

* **Reproduction cells (carry no weight):** the four v1-dropped structures (H3O+, the ethanol radical, toluene, the CH3S radical).
* **Held-out proton-affinity bases:** neutral closed-shell bases of at most ten heavy atoms with both a PA and a GB on the NIST WebBook page, **not among v1's 28**, with a reference PA above propene's (751.6 kJ/mol) so that they belong to the deciding stratum. Candidates, chosen by chemistry and **with no value read**: ethylamine, diethylamine, triethylamine, piperidine, morpholine, 2-methylpyridine, 4-methylpyridine, N-methylpyrrolidine, N,N-dimethylformamide, acetamide, diethyl ether, methyl acetate, dimethyl sulfoxide, trimethyl phosphite. **The drop rule, fixed now:** a candidate is dropped, before any calculation, if the NIST page lacks its PA or its GB; nothing is dropped or added after a value has been read for a different reason. The surviving list and the values are fetched after this file is frozen and are committed before the first job.
* **Held-out X-H bonds:** every closed-shell X-H bond of Blanksby and Ellison's Table 1 [source:blanksby2003] that is **not among v1's 33**, is a neutral ordinary doublet radical of at most ten heavy atoms, and has a stated uncertainty (a numeric DH298 and uncertainty, not an inequality). **[To be filled in before freezing: the list by bond name only, prepared from the table's row labels, with no value read.]** The deciding stratum is the bonds with stated uncertainty <= 1.0 as in v1.

## 5. The reading rule (unchanged from v1; the judges are not edited)

`benchmarks/proton_affinity/judge.py` and `benchmarks/bde/judge.py` are used **as they are**, on the **held-out arm alone**, for PA and GB apart (proton affinity) and for the primary arm (BDE):
* **PASS:** MAE <= 2.5 kcal/mol, no error above 5.0, |MSE| <= 1.5.
* **PARTIAL:** not PASS and MAE <= 4.0 (proton affinity) or 3.5 (BDE).
* **FAIL:** otherwise. **NOT EVALUABLE:** more than the v1 number of missing deciding cells (two for PA, three for BDE, **scaled down in proportion to the held-out set's size and rounded down**, computed once the lists are fixed).
The mean error is the quantity v1 narrowly missed, and it is reported on the held-out arm with the **joint** statistic (v1's deciding set and the held-out one together) **as information only**; the joint number decides nothing, because it contains the cells v2 was designed on.

A held-out set of this size cannot show that the restart repairs a given kind of failure (it may trigger only a few times); what it can show is whether **the full protocol, with the restart in it, keeps its accuracy and its bias on molecules it was not designed on**, which is what a calculator needs. The number of times the restart stage fired and how many of those structures it rescued are reported with their counts, no rate claimed from a handful.

## 6. What each verdict does (decided now)

* **PASS:** the calculator is built with the v2 protocol (the restart stage included), with the held-out error stated beside it.
* **PARTIAL or FAIL:** the failing cells are named; whether to build a calculator with a stated larger error is Alex's decision, made with the report. (Alex said on 2026-10-21 that he wants the calculators built; this section keeps the stated error attached to whatever is built.)
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed and the held-out arm is re-run under a new preregistration.
* A result outside the thresholds is never explained away by hand.

## 7. What it cannot say

* **Not a revision of the v1 verdicts**, and not independent evidence about the four cells it was designed on.
* A held-out set of about fifteen bases and a few bonds is small; its confidence interval on MAE and MSE is wide, and a PASS on it is a statement about that set.
* **One functional, one basis, one amplitude**: a different amplitude or a different mode is a different protocol.
* The restart finds **a** minimum near the saddle, not the global one, and the surface along the soft modes involved is flat (the ethanol radical's enthalpy moves by 0.7 kcal/mol between the saddle and the minimum), so a bond that depends on such a mode carries that uncertainty in its enthalpy.
* Nothing about the CH3S-type failure (section 3).

## 8. Records and refusals

Records are `benchmarks/restart_v2/artifacts/<arm>/runs.jsonl`, one line per job, with the same fields as v1 plus the stage (`hessian`, `displaced+`, `displaced-`), the lowest frequency of the Hessian job and the mode's frequency used. **A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`.** Each job has the v1 4-hour limit. The run is one stage at a time and resumes; it is not run while another long ORCA batch is using the machine, and never beside the synthesis benchmark. The runner and its tests (the displacement arithmetic on a synthetic Hessian, the acceptance and selection logic, the missing-cell counts) are written **before** the first job, in the same way as v1's.

## 9. Open choices that need Alex's approval before this is frozen

1. **Whether to run the held-out arms at all**, and their size. Without them v2 has no test (section 2), and the calculators can still be built from v1 with the errors v1 measured (PA 1.55 / 1.53; BDE 1.76 with a -1.5 bias, ethanol, toluene and methanethiol bonds excluded and said so). Cost is unmeasured; by v1's rate a held-out arm of this size is roughly half the corresponding v1 run (PA about 6 h, BDE about 5 h).
2. **The amplitude and selection rule of section 3** (0.15 Angstrom, both directions kept, lowest H). They are a choice, made after seeing the four cells; the held-out arm is what tests them.
3. **The two candidate lists** in section 4 (the proton-affinity names are proposed here; the bond list is still to be written from the table).
4. Whether a separate **v3 for the CH3S-type failure** should be designed before or after this.

## 10. To-do: the deferred held-out work (recorded 2026-10-21)

Alex wants the held-out arms done **at some point** but not now, because the calculators do not need them: both can be built from the v1 results, with the measured errors stated beside each (proton affinity MAE 1.55 / 1.53 kcal/mol for PA / GB; bond dissociation MAE 1.76 with a mean error of -1.53, i.e. about 1.5 kcal/mol low, and the ethanol O-H, toluene benzylic C-H and methanethiol S-H bonds flagged as not computed by the v1 rule). Nothing in this file is frozen or run meanwhile.

**The recommended shape when it is picked up** (this replaces the all-in held-out design of sections 4 and 5, which should be rewritten before freezing; the reasons are in the 2026-10-21 discussion):
1. **A restart stress set, first (about 1 to 2 h of ORCA).** Eight to twelve small species chosen **by rule** because they are likely to trigger the restart: high-symmetry ions, molecules with free methyl rotors, radicals with near-degenerate electronic states. No reference values are needed, so there is nothing to leak. The measure is how many triggered structures end up accepted, as counts with no rate claimed. This tests the thing that was actually changed, which a held-out accuracy set cannot (v1 triggered the restart for 4 of 142 structures, about 3%, so 12 to 15 new molecules would trigger it zero or one time).
2. **A BDE held-out arm of about 12 to 15 bonds (about 5 h)**, from Blanksby and Ellison's Table 1 minus the 33, listed by name only before any value is read. It answers whether the -1.5 bias is stable on new bonds (with a spread of about 1.2 the mean error would be known to roughly +/-0.35: enough to tell -1.5 from 0, not 1.4 from 1.6). **If a bias correction is wanted**, fit the offset on v1's 25 bonds and test it on this arm, rather than judging the uncorrected numbers.
3. **No proton-affinity held-out arm**: PA passed with room to spare, and the only thing v2 changes for it is tiny ions like H3O+, which the stress set covers. It would cost about 6 h and probably confirm v1. Revisit only if the stress set shows the restart changing PA's cells.
4. Drop the "joint statistic" line of section 5 (it adds little), and still never re-judge a v1 verdict with repaired cells added.
5. The CH3S-type failure (v3) is a separate piece, designed before or after this at Alex's choice.
