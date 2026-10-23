# A displaced restart for structures that keep an imaginary mode (protocol v2), a restart stress set and a held-out bond-dissociation arm: preregistration

**Status: FROZEN 2026-10-22 (section 12 records how), before any job of either arm.** The runner and its tests are committed with this file. It changes only by an amendment section that says what and why. Where this text and the code disagree, the disagreement is fixed before the run, never after. (It was a draft earlier the same day; the text below is unchanged except for the marks "(proposed)", which Alex approved with "Approved. Write the runner and tests." and section 12.)

**Decided by Alex on 2026-10-22:** the held-out bonds come from the Active Thermochemical Tables; the list in section 5 and its three exclusions in section 9 are accepted, **with the exclusions kept documented so they can be lifted**; there is no proton-affinity held-out arm; the bias test of section 7 is wanted. What this file proposes and he has not yet approved is marked **(proposed)**.

## 1. What this is, and what it is not

The two ORCA benchmarks (`benchmarks/proton_affinity/PREREGISTRATION.md`, `benchmarks/bde/PREREGISTRATION.md`) were run on 2026-10-20/21: proton affinity **PASS** for PA and GB with water missing, bond dissociation **PARTIAL** (mean error -1.53 against a limit of 1.5, three deciding bonds missing). **Their verdicts stand and nothing here revises them.** Both lost cells because a structure kept a vibrational frequency below -20 cm-1 after the one `Calc_Hess` re-run (the v1 rule) and was dropped.

This is a **new protocol (v2)**: one extra stage for such structures (section 3), tested in two arms on data it was not designed on:
* **Arm A, a restart stress set** (section 4): what the restart does to the kinds of structure that failed, counted and not judged.
* **Arm B, a held-out bond-dissociation set** (section 5): whether the whole protocol, restart included, keeps its accuracy and its bias on 27 bonds the first run did not contain, judged by the unchanged rule (section 6), plus a preregistered test of whether the first run's bias is stable (section 7).

Why no proton-affinity arm: it passed with room to spare, and the only thing v2 changes for it is tiny ions like H3O+, which Arm A covers.

## 2. What was seen first (disclosure)

* The v2 rule was designed **after** the v1 verdicts, and an exploratory run of exactly this rule on the four structures v1 dropped has been done and seen (`benchmarks/restart_diagnosis/`): H3O+ repaired in both directions, the ethanol radical and toluene in one each, the CH3S radical not. **The v2 run on those four is a reproduction, not a test, and carries no weight.** A v1 verdict is never re-judged with repaired cells added (adding two of them would have moved the first run's mean error from -1.53 to about -1.46, a rescue the thresholds exist to prevent).
* **The held-out references were computed, from the table, before any calculation of those bonds** (`benchmarks/bde_heldout/candidates.json`, from `extract_atct.py`): the bonds were chosen by a rule and the references are the table's numbers combined as the definition says. No ORCA calculation of any of them exists.
* **The arithmetic was checked on bonds we already hold** (`benchmarks/bde_heldout/crosscheck_v1.json`): over the 22 first-run bonds both sources cover, ATcT minus Blanksby and Ellison is **-0.11 kcal/mol on average**, within 0.2 for every reference the first run held to 0.1 or better, and beyond three combined standard uncertainties for **one** bond, propene's allylic C-H (87.50 against 88.8). The two sources are therefore not interchangeable at the level of 1 kcal/mol for loosely held bonds, which is why the held-out arm is judged on its own and the joint number is information only.
* **A post-hoc diagnostic on the first run, not a re-judging:** over the 17 deciding bonds ATcT can also give, the first run's mean error is -1.48 against Blanksby and Ellison and **-1.27 against ATcT**. The bias is therefore not an artefact of that reference; it moves by 0.2.
* Two of the excluded bonds' experimental values were read in Luo's handbook (section 9). Nothing else of the held-out data was read.

## 3. The v2 rule (everything here is fixed)

v2 is v1 (every keyword, header, structure-generation step and selection rule of the two preregistrations, unchanged) plus **one additional stage that applies only to a structure still not accepted after v1's own `Calc_Hess` re-run because its lowest frequency is still below -20 cm-1 and its skeleton is intact** (a radical or ion that rearranged, or lost its proton, is a failed structure, not a saddle point near a minimum: a displacement along its mode would not make it the species, so it is not restarted). For such a structure, from the **geometry of that re-run**:

1. Run `! M062X def2-TZVPD TightSCF DefGrid3 Freq` (same functional, basis and grid; `%pal nprocs 4`, `%maxcore 3000`; charge and multiplicity as the structure's own, a radical unrestricted) and read the normal mode of the **most negative** frequency from ORCA's `.hess` file.
2. Normalize the mode so that its **largest single Cartesian component (Angstrom) is 1**, and displace the geometry by **+0.15 and by -0.15** along it. (0.15 Angstrom is the only amplitude ever tried; it is not tuned and is not varied.)
3. From each displaced geometry run v1's optimization job **with `Calc_Hess true`** (`! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`).
4. Each of the two results is an **ordinary structure of the species**: accepted by v1's rules (lowest frequency >= -20 cm-1, and for a radical the skeleton test) and entering v1's selection (lowest H) alongside the species' other structures. If neither is accepted the species is a missing cell exactly as in v1.
5. **One displaced restart only.** No iteration, no further amplitude, no other mode.

A structure v1 accepted keeps its v1 record. **Out of scope, stated so it is not mistaken for a gap:** the CH3S-type failure (the displacement did not help and the energy did not move): a structure like that is a missing cell under v2 and is **counted as one**. It is the subject of a separate possible v3.

## 4. Arm A: the restart stress set (descriptive; no verdict)

**The species, by rule** (a structure of the kind the four v1 failures show, one class each; the four v1 failures themselves are run as controls and carry no weight):
* **Tiny lone-pair bases' conjugate acids,** built as the proton-affinity runner builds them (the failure class of H3O+): H3S+, PH4+, protonated methanol, protonated dimethyl ether.
* **Parents with a freely turning methyl on a heteroatom or ring** (the failure class of toluene): p-xylene, ethylbenzene, anisole.
* **Radicals made by deleting the hydrogen of an S-H or O-H** as the bond-dissociation runner makes them (the failure classes of the CH3S and ethoxy radicals): ethanethiyl (from ethanethiol), 1-propoxyl, 2-propoxyl, tert-butoxyl.
That is 11 new species and 4 controls. **What is measured:** for every structure, whether v1's own two stages accepted it; for those they did not, whether the restart accepted one of the two displaced results, and the enthalpy of the accepted structure against the structure it replaced. **What is reported, as counts and never as a rate claimed from a handful:** structures run, structures v1 alone accepted, structures that triggered the restart, structures it rescued.
**What it decides (proposed):** the restart enters the calculators' protocol only if **at least two** structures triggered it and **at least half** of the triggered structures were accepted after it. Otherwise it is reported and not adopted, and the calculators keep v1's rule with its missing cells.

## 5. Arm B: the held-out bonds

**The source.** The Active Thermochemical Tables, version 1.228 [source:atct1228]: enthalpies of formation at 298.15 K, kJ/mol, with uncertainties, derived from a thermochemical network [source:ruscic2004]. A bond enthalpy is `DH298 = dfH(R.) + dfH(H.) - dfH(RH)`, its uncertainty the root sum of squares of the three. Blanksby and Ellison's Table 1 [source:blanksby2003] contains no in-scope X-H bond that the first run did not already use (the only closed-shell parents left are HNO, HONO and nitric acid, which the first run excluded), which is why the arm cannot come from it.
**The rule, fixed before the values were computed:** a closed-shell parent of the table's gas-phase species with at most ten heavy atoms of H, C, N, O, P and S, whose radical is also in the table and is the parent minus one hydrogen at one named site, not a bond of the first run, with a combined uncertainty of at most 1.0 kcal/mol. **30 bonds met it** (largest uncertainty 0.47). Each pair is checked by formula and structure in `extract_atct.py`; the file is `benchmarks/bde_heldout/candidates.json`.
**The 27 deciding bonds** (3 are excluded, section 9): 19 C-H (propane's terminal; ethanol's alpha and beta; propene's 2-position vinyl; propyne's propargylic and acetylenic; n-butane's terminal; 1,3-butadiene; ethylamine's alpha and beta; methylamine; acetonitrile; dimethyl ether; dimethyl sulfide; methyl hydroperoxide; propionaldehyde's and acrolein's formyl; methanimine's; ethanimine's), **6 N-H** (methylamine, ethylamine, hydrazine, hydroxylamine, methanimine, ethanimine) and **2 O-H** (hydroxylamine, formaldoxime). No P-H bond: the table has no phosphorus species with a radical partner.
**The protocol:** v2, on each bond's parent and radical as in the first run (parent from its SMILES with explicit hydrogens, the lowest three conformers within 5 kcal/mol, the radical's starts the parent's conformers with the lowest-numbered hydrogen on the named atom deleted, `H(H.)` from the same hydrogen-atom job); selection of the lowest H of each, independently; `DH298 = H(R.) + H(H.) - H(RH)`.

## 6. The reading rule (unchanged from the first run; `benchmarks/bde/judge.py` is not edited)

On the 27 deciding bonds: mean absolute error, mean signed error, largest absolute error.
* **PASS:** MAE <= 2.5 kcal/mol, no error above 5.0, |MSE| <= 1.5. **PARTIAL:** not PASS and MAE <= 3.5. **FAIL:** otherwise. **NOT EVALUABLE:** more than three of the 27 have no computed value.
* **Reported in the same statistics and deciding nothing:** each class (C-H, N-H, O-H) and the three excluded bonds (section 9). The joint statistic with the first run's 22 computed bonds is information only, because the first set's cells include the ones v2 was designed on and its reference differs (section 2).
* The standard error of every mean (SD / sqrt(n)) is reported beside it, so a verdict at a threshold is read with its uncertainty: **at this size the standard error of the mean error is about 0.25 kcal/mol, so a result within 0.3 of a limit cannot tell the two sides apart** and the report says so.

## 7. The bias test (preregistered; the numbers are proposed)

The first run's mean error over its 22 computed deciding bonds is **-1.53 kcal/mol** (the calculation reads low). Fixed now: the offset `b = -1.53`.
* **Reproduced:** the held-out mean error's interval (mean +/- 2 standard errors) **contains -1.53**. **Not reproduced:** it excludes it.
* **A correction is supported** (and only then offered to users as a stated offset, never silently applied) if the bias is reproduced **and** the corrected errors `e + 1.53` have a lower mean absolute error than the uncorrected ones on the held-out set.
* It is judged per class as information (is the offset the same for C-H, N-H and O-H?), but the decision rests on the whole set. The N-H bonds are the class to watch: the proton-affinity benchmark was biased more for its nitrogen and phosphorus bases (-1.77 kcal/mol over 11) than for the others (-0.56 over 10), a split no one preregistered.

## 8. What each verdict does (decided now)

* **PASS or PARTIAL on Arm B:** the BDE calculator's stated error is the held-out result beside the first run's, with the bias test's outcome, and the restart (if Arm A adopted it) is in the protocol. Alex has said the calculators are wanted whatever the verdict; the verdict decides what error is stated.
* **FAIL:** the held-out error is stated, nothing about a correction is claimed, and the cause is looked for in the per-class table.
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed and the arm is re-run under a new preregistration.
* A result outside the thresholds is never explained away by hand.

## 9. Documented exclusions (this is v2's scope, and it can change)

Three bonds were excluded from the deciding set by a rule fixed before any calculation: **a bond whose radical is a linear or heteroallene-type pi radical is not an "ordinary doublet radical", which the first run's scope required.** They are **still computed and reported, deciding nothing,** so that what it takes to lift the exclusion is measured and not guessed. Each is recorded with its reason, the evidence read, and what would lift it in `candidates.json` (`exclusion`):
* **Isocyanic acid, N-H (radical NCO).** Luo's handbook (Table 7.1.1) lists five experimental H-NCO values from 109.6 to 111.5 kcal/mol, so the reference is not tight; ATcT's value is in that range.
* **Hydrazoic acid, N-H (radical N3).** Luo lists five values from 88.7 to 93.7 kcal/mol, about five kcal/mol of spread, the loosest reference of the three.
* **Ketene, C-H (radical HCCO).** A bent-linear radical with a low-lying excited state, and a cumulene parent; Luo's ketene entries were not read.
**What would lift the exclusions, in order of cost:** (1) read Luo's entries for the three and the literature on the electronic states of NCO, N3 and HCCO; (2) a multireference or CCSD(T) energy of the three radicals at the ORCA geometry, to say whether a single-reference unrestricted treatment is adequate for them; (3) a **v2 scope** that adds "linear pi radicals" as its own class with its own preregistered check, so that these three (and any more the tables hold) are judged as a class and not as outliers; (4) any published M06-2X error for these radicals.

## 10. What it cannot say

* **Not a revision of the first run's verdicts,** and not independent evidence about the four cells the restart was designed on.
* A held-out set of 27 bonds has a standard error of the mean error of about 0.25 kcal/mol; a PASS or a bias test on it is a statement about these bonds, **small acyclic organics of at most four heavy atoms** (the largest parent is n-butane, acrolein or 1,3-butadiene), not about larger or cyclic molecules, solution, or phosphorus.
* **One functional, one basis, one amplitude.** The restart finds *a* minimum near the saddle, not the global one, and the surface along the soft modes involved is flat (the ethanol radical's enthalpy moves by 0.7 kcal/mol between the saddle and the minimum), so a bond that depends on such a mode carries that uncertainty.
* The reference is ATcT, a derived thermochemical network and not a direct measurement of each bond; its uncertainties are the table's.
* Nothing about the CH3S-type failure (section 3), which is a possible v3.

## 11. Records, and what is still open

Records are `benchmarks/restart_v2/artifacts/<arm>/runs.jsonl`, one line per job, the fields of the first run's plus the stage (`hessian`, `displaced+`, `displaced-`) and the frequency of the mode used. **A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`.** Each job has the 4-hour limit. One stage at a time, resumable, never beside another long ORCA batch or the synthesis benchmark. Commands (from the repository root, on the commit this is frozen on, no edit to `src/` between the first job and the report): `python benchmarks/restart_v2/run_restart.py structures --arm stress|heldout`, then `run --arm ... --workers 3 --cores 4`, `status`, `report`. The stress arm builds 18 structures of 15 species and the held-out arm 68 (29 parents, 38 radicals, the hydrogen atom) of 30 bonds.

**Before this is frozen:**
1. **Alex's approval of the proposed numbers:** section 4's adoption rule (two triggers, half rescued), section 7's reproduction interval (mean +/- 2 standard errors) and its correction criterion, and the stress set's eleven species.
2. **A second reference column from the literature already held**, for the deciding bonds Luo's handbook covers, read by page and reported beside ATcT (reported only): Luo [source:luo2007] for the N-H and other bonds, and Ruscic's sequential-bond paper [source:ruscic2015] for the methane, ethane and methanol bonds. This was not done for the draft.
3. **The runner and its tests: written** (`run_restart.py`, `restart_core.py`, `tests/test_restart_v2_runner.py`: the Hessian reader on a real ORCA file, the displacement, the chain of jobs against a stand-in for ORCA, resumption, both reports and the two rules; three mutations of the code each fail a test). **Smoke-tested on real ORCA 6.1.1 on one control structure** (the H3O+ start, 4 min 38 s, a scratch folder, not a record): the first two jobs reproduced the planar saddle (-601.55 and -601.56 cm-1, as the first run found for water), the Hessian job read the mode (-601.56), and both displaced optimizations gave the same real minimum (H = -76.66319626 Eh, 0.30 kcal/mol below the saddle's enthalpy), accepted by the first run's rules. Still to do before freezing: a read of the runner against this text by someone other than its author.
4. The proton-affinity arm stays out; the DLPNO secondary arms of both benchmarks stay unwritten.

## 12. The freeze, and what was settled on the way (2026-10-22)

Alex said "start the run" with section 11's list open. What was done, in order, and what was not:

1. **Approval of the numbers (item 1):** given earlier in the day ("Approved. Write the runner and tests."), covering section 4's rule, section 7's interval and criterion, and the stress set's species.
2. **Independent read of the runner against this text (item 3's last line):** done by a reviewer who had not written either and was given the files, not the author's conclusions. Findings that changed the code before any job, each with a test: (a) a job that could not even start ORCA (a wrong path, a locked folder) closed the structure's chain as a permanent missing cell; such a chain now stays open and the next `run` does it again, while a calculation that ran and failed, or timed out, still closes as a missing cell as in the first run; (b) the held-out report printed a verdict with chains still open; it now reports NOT EVALUABLE, as the stress report did; (c) the modes of the Hessian file were assumed to share the frame and atom order of the geometry displaced; the runner now refuses a file whose `$atoms` differ from the given geometry by more than one common translation. **Measured, real ORCA 6.1.1, a water in an arbitrary pose:** ORCA writes the geometry shifted by one common translation (the centre of mass moved) and not rotated, which is what the check allows. The modes are Cartesian displacements, not mass-weighted: in the H3O+ umbrella mode the oxygen moves 0.19 for a hydrogen at 1, 3/16 as momentum conservation gives; (d) a Hessian job that finds no frequency below -20 cm-1 ends the restart (there is no direction to displace along) instead of displacing along the smallest mode, which would have been a rotation; the stage is recorded with its reason and the structure is a missing one.
3. **Clarified, not changed:** controls (the four first-run failures) carry no weight in the adoption rule, section 4; adoption counts structures, not species, as section 4 says; a non-control structure whose chain is not closed makes the stress verdict NOT EVALUABLE. The dirty-tree refusal now covers `src/`, `benchmarks/restart_v2`, `benchmarks/bde`, `benchmarks/bde_heldout` and `benchmarks/proton_affinity` (excluding this arm's `artifacts/`), which is wider than section 11 says and so stricter.
4. **Not done before the freeze (item 2, the second reference column):** Luo's handbook and the sequential-bond paper were not read for page-level values. **That column is reported only and decides nothing**, so the verdict cannot depend on it; it will be added to the report after the run, by page, and labelled as made after the result.
5. **Run order:** the stress arm first, then the held-out arm, one at a time, never beside another heavy job. The stress arm's result does not change the held-out arm's protocol: both arms use the same restart, and the adoption rule is about whether the calculators adopt it.
