# The second Fukui gate: preregistration

> **FROZEN, 2026-10-18, by the commit that wrote this banner.** From that commit on sections 0 to 10 are fixed, together with the calculation it tests (`chem/fukui_plan.py`, `chem/fukui.py`,
> `chem/orca_engine.py` and what they call), the typed tables, rules and judge (`app/fukui_gate_2.py`, `tests/test_fukui_gate_2.py`) and the drive steps and scripts (`fukui2_*` in `app/debug_drive.py`,
> `benchmarks/fukui_gate_2/make_scripts.py`, `benchmarks/visual/fukui2_gate_*.json`). Section 11 is where the outcome is written, below a rule, in later commits. **When it was frozen no ORCA job of
> a gate species had been run**; a rehearsal and the two noise floors had, on molecules in neither gate, and their numbers were seen (section 2).
> It follows the answers Alex gave: T = 0.02; the anions are decided, through a mode that does not run the N+1 state; the calculation tested is the robust-anion version of it ("Fukui v2", `DESIGN.md`),
> which therefore had to be built first; a pass promotes the calculator to LIMITED and SHOWN (the decisions are recorded at the end).

This is the second preregistered check of the calculator **Fukui functions (Hirshfeld)** (`orca.fukui`, `chem/fukui.py`, `chem/fukui_plan.py`, `chem/orca_engine.py`). The first,
`benchmarks/fukui_gate/PREREGISTRATION.md`, ended in **FAIL by 0.0014 on one quantity** (CO's f- at `HF/6-31G**`), which is final and is not touched here; the calculator
ships as experimental and not validated. This gate asks a different question of different published numbers.

## 0. Why a second gate, and what it is built on

Measurements made after the first outcome (`benchmarks/fukui_gate/PREREGISTRATION.md` 11.5 and 11.6) say where a published-table check can and cannot work:

* **At the `6-31G**` levels the numbers do not depend on the integration grid, on the SCF starting guess or on the starting embedding** (a finer grid changed no value on 14 jobs;
  no start found an anion solution lower than the default; three embeddings agreed to 0.0004). That is the regime a published table can test.
* **With diffuse functions f+ is not a reproducible number** (the unbound anion has more than one SCF solution, and two molecules gave two different anions from three embeddings),
  and the published diffuse-level f+ values themselves match one solution in one case and another in the next. **No diffuse-level f+ is a target here.** f- is a different matter:
  at 6-311+G** it agreed with the published values in all 17 rows, and the N and N-1 states of an anion are both bound.
* **The first gate's data cannot be used again.** Its B3LYP arm reproduced all 23 numbers within 0.0066, but those numbers are known; a gate built on them would be circular.
  What is needed is published values for **molecules the first gate never used**, which `deproft2002` supplies.

**The calculation that is tested is Fukui v2**, the calculation as it stands at the freeze commit (`benchmarks/fukui_gate_2/DESIGN.md` records what it is, and the measurements each change rests on).
It differs from the one the first gate tested in five ways: (1) **a species with a negative charge is given f- alone**, from two states, because its N+1 state is a dianion that no basis set binds
(this is what makes it possible to test an anion at all: the first gate's reported arm showed that dianion refused or irreproducible at a diffuse basis); (2) **every job uses ORCA's `IntAcc 6.0` grid**;
(3) **every job states `HFTyp RHF` or `UHF`**, because ORCA keeps the unrestricted setting of the first doublet for a later closed-shell job of the same input; (4) **at a basis set with diffuse functions
(`6-31+G*` is one) each anionic state is also started from the HCore and the Hueckel guess, written after the default jobs, and the lowest solution is read** unless the default start is within 0.01 eV of it;
(5) **each job is read from its own stretch of output**. For the neutral species and the cation at `6-31G*` (changes 2 and 4 do nothing there that was measured: a finer grid moved the f+ and f- of aspirin, caffeine and
ibuprofen by at most 0.00001 at `B3LYP/6-31G*`, and no diffuse function means no extra start) the numbers are those the first calculation gave; changes 1 and 4 are about the anions. **v2 was developed on stand-in species, none of which is in this gate's tables**
(section 2).

## 1. The claim, and what a pass does not say

> On ORCA 6.1.1, the Fukui calculation of the application at the freeze commit, run on the geometry ORCA optimized at the same level, reproduces **47 published Hirshfeld condensed values of 15
> molecules**, each within **T = 0.02**, and puts its largest value on the published site in **11 statements**:
> at **`B3LYP/6-31G*`**, the f- of HCN, N2O, anilinium (a cation), phenol, aniline, fluorobenzene, benzaldehyde, styrene, nitrobenzene, pyrrole, furan and thiophene and the f+ of acrolein
> (42 values, 10 statements); and at **`B3LYP/6-31+G*`**, the f- of the anions SCN- and NO2- (5 values, 1 statement).

A pass says the calculator's wiring and arithmetic reproduce what a second group published, for molecules the first gate did not touch, on this machine at these levels. It does **not** say that:

* the largest condensed Fukui value is where a reaction goes (`wang2019` found the Fukui function the weaker descriptor); the experimental selectivities in the source are reported beside our values and decide nothing;
* any other level reproduces: **not HF** (the first gate's miss, with its unrestricted cations), **not a basis set with diffuse functions for a neutral molecule or a cation**, **not `def2-SVP`, which is the application's default preset**
  (it is run in the reported arm, section 10, and is therefore seen); any other functional, solvent or ORCA version;
* an anion is reproduced beyond the two tested, or at any other basis set, or that an anion's f+ means anything: **v2 does not compute it** (a dianion), and no f+ of an anion is claimed;
* the result is independent of the first gate's source: both are Gaussian 98 calculations (section 4);
* f0 or the dual descriptor is validated by a publication.

## 2. What has been run or seen before the freeze, disclosed

* The first gate and its post-gate measurements (`benchmarks/fukui_gate/`), at `6-31G**`, `6-311+G**` and `def2-SVP`, on CO, CO2, formaldehyde, acetone, CN-, NCO-, CNO- (and formaldehyde, propene and
  pyridine in the exploration at `def2-SVP` and `def2-SVPD`). **Only CO and formaldehyde are also in `deproft2002`**, and they are kept out of the decision for that reason (section 3).
* **The development of v2 (`DESIGN.md`) ran real ORCA on stand-in species, none of them in `deproft2002`'s Tables 4 to 6, and their numbers were seen:** the anions azide, cyanate, formate, acetate, the acetone enolate,
  p-cresolate and methoxide at `B3LYP/6-31+G*` (grid and start sweeps, f- of each at both grids, and a real-window run of methoxide), acetone at `HF/6-311+G**` (a real-window run, for the lowest-of-starts
  choice), and aspirin, caffeine and ibuprofen at `B3LYP/6-31G*` (the cost of the grid). **p-cresolate is a substituted phenolate; phenolate itself is in Table 5 and is in the reported arm only.**
* **A rehearsal of the whole path was run in the real window on two molecules that are in neither gate, and its numbers were seen:** pyridinium (a cation, `B3LYP/6-31G*`: ORCA optimization, then all
  three states and four datasets) and azide (a linear anion, `B3LYP/6-31+G*`: the same, with f- alone and the sentence saying why). No unexpected application error; the drive's one failed assertion was a wrong
  atom count typed into the rehearsal script.
* **The two noise floors of section 6 were measured before the freeze** (pyridine, formate; neither is in a gate), with the freeze's code, by `benchmarks/visual/fukui2_gate_floor.json`: pyridine F = 0.000000 (the same input twice and the whole chain twice both identical to every stored digit, three jobs a run) and formate F = 0.000000 (likewise, four jobs a run), against the limit 0.005; the gate uses the larger and is NOT EVALUABLE above the limit (`artifacts/floor.json` and
  `floor_records.json`, committed before this banner). **No ORCA job of any other species in this document has been run, at any level.** One throwaway check was made that ORCA 6.1.1 accepts the keywords
  `B3LYP 6-31G*` and `B3LYP 6-31+G*`: a single point of water and of hydroxide, no Fukui job, no f value read.
* `deproft2002` was read and its Tables 4 to 6 were transcribed from the page images (the text layer scrambles them), twice, the second time against the page images again on 2026-10-18; every complete column
  was summed (section 3), and the ten rings and acrolein's three values were compared with the second printing in `sablon2007` (its Table III and Fig. 1, read from the page images). The published numbers of CO and formaldehyde
  were compared with the first gate's published numbers (published against published, no ORCA): they differ by at most 0.0023.

## 3. The published numbers, and the rules that decide which may be targets

**Source: `deproft2002`** (De Proft, Van Alsenoy, Peeters, Langenaeker, Geerlings, *J. Comput. Chem.* 23, 1198, doi 10.1002/jcc.10067), Tables 4, 5 and 6. Gaussian 98, geometries fully optimized and densities obtained at
**`B3LYP/6-31G*`** (`B3LYP/6-31+G*` for the anions), Hirshfeld populations with the Yang-Mortier finite differences `f+_k = q_k(N+1) - q_k(N)` and `f-_k = q_k(N) - q_k(N-1)` in terms of populations, three decimals, values in e, hydrogens
averaged over the hydrogens of a heavy atom. The paper does not say whether the ions use the neutral geometry (the first gate's source did not either; the application's calculation is vertical). For an anion `N` is the anion
and `N-1` the neutral radical.

**Table 4, f-** (formula order of the paper): HCN H 0.109, C 0.389, N 0.502; N2O (terminal N, central N, O) 0.399, 0.173, 0.428; CO C 0.687, O 0.314; H2CO O 0.433, C 0.229, H 0.169; SCN- S 0.606, C 0.115, N 0.279;
NO2- N 0.310, O 0.345 (each O); the enolate (printed `CH2CO-`, called the enolate ion in the text; taken to be the enolate of acetaldehyde) C 0.324, C 0.131, O 0.273 (hydrogens not listed).
**Table 5, f-, ring carbons** (ortho, meta, para; two values where the two ortho or the two meta carbons differ; heterocycles by position 2 and 3):
anilinium o 0.067, m 0.095, p 0.175; phenolate o 0.102, m 0.057, p 0.136; phenol o 0.091 and 0.081, m 0.073 and 0.064, p 0.144; aniline o 0.080, m 0.061, p 0.131; fluorobenzene o 0.087, m 0.078, p 0.158;
benzaldehyde o 0.033 and 0.044, m 0.045 and 0.044, p 0.072; styrene o 0.065 and 0.059, m 0.054 and 0.059, p 0.115; nitrobenzene o 0.118, m 0.126, p 0.048; pyrrole 2 0.194, 3 0.068; furan 2 0.272, 3 0.107; thiophene 2 0.059, 3 0.138.
**Table 6, f+:** H2CO O 0.308, C 0.397, H 0.147; acrolein C-beta 0.211, C-alpha 0.116, carbonyl C 0.171; maleic anhydride carbonyl C 0.097, CH 0.145; maleimide carbonyl C 0.096, CH 0.137.

**Rule A, the sum rule.** A column of f over *all* the atoms of a molecule sums to 1, and each printed value carries up to 0.0005 of rounding. A complete column more than **0.002** from 1 is a misprint and is dropped whole. The complete columns are
HCN (1.000), N2O (1.000), CO (1.001), H2CO f- (1.000), H2CO f+ (0.999), SCN- (1.000) and NO2- (1.000); none is dropped. The enolate's hydrogens are not listed, so its column cannot be summed.

**Rule B, a second printing.** A column that omits atoms cannot be summed. A number from such a column is a target only where **a second printing agrees with it exactly**. `sablon2007` (Sablon, De Proft, Ayers, Geerlings, *J. Chem. Phys.* 126, 224108) reprints the finite-difference Hirshfeld values of `deproft2002`
(its Table III for ten of the eleven rings, which omits phenolate; its Fig. 1 for acrolein's three carbons), and every reprinted number agrees with the original. **This guards against a misprint and against my transcription. It is the same group's own data, so it does not guard against a
difference of method, and it is weaker than the first gate's second source (a different program).**

**The decided numbers: 47.** HCN 3, N2O 3, SCN- 3 and NO2- 2 (complete columns, Rule A); anilinium 3, phenol 5, aniline 3, fluorobenzene 3, benzaldehyde 5, styrene 5, nitrobenzene 3, pyrrole 2, furan 2, thiophene 2 (33, Rule B); acrolein f+ 3 (Rule B).

**Kept out of the decision, and run in the reported arm (section 10):**

* **CO and formaldehyde:** the first gate's numbers for them are known, and the source's differ from the first gate's published values by at most 0.0023, so the outcome would carry no information.
* **Maleic anhydride and maleimide f+, phenolate f- and the enolate's f-:** partial columns with no second printing.
* **Every f+ of an anion:** the source published none, and v2 does not compute one.

**Rule C, site statements.** A statement "the largest value is on X" is **decided only if the published margin (the expected site over the next listed one) is at least twice the tolerance** (0.04, with the first gate's float slack of 1e-9).
A statement about a whole molecule (HCN, SCN-) needs a complete column. **A statement about a table that lists only some atoms is restricted to the atoms it lists, and says so:** for the rings it is about the largest of the ring-carbon values listed (ortho, meta, para, or positions 2 and 3), not about the
ipso carbon, the substituent or the hydrogens, and for acrolein it is about the three carbons. (A statement about a whole molecule from a partial column would also need the expected value to exceed all the weight the column leaves unlisted; none is decided here, and the enolate's, in the reported arm, would be.)
**Decided (11):** HCN f- on N; SCN- f- on S (margin 0.327); the largest ring site is para in anilinium, phenol, aniline, fluorobenzene and styrene; position 2 in pyrrole and furan; position 3 in thiophene; acrolein f+ on C-beta among its carbons (margin 0.040, exactly twice T).
**Listed and not decided (four):** N2O f- on O (margin 0.029), NO2- f- on O (0.035), benzaldehyde's largest ring site (para, margin 0.027) and nitrobenzene's (meta, margin 0.008). The published values for thiophene put the largest value on position 3 where experiment says 2; the statement
reproduces **the published ordering** and is not a claim about experiment.

## 4. Procedure

The application's own path throughout, driven by `OPENCHEM_DRIVE` (no mouse), on this machine's ORCA (`D:\ORCA\orca.exe`, 6.1.1), gas phase; `benchmarks/fukui_gate_2/make_scripts.py` will write the scripts. For each of the **15 decided species**:

1. Add it from its SMILES: HCN `C#N`, N2O `[N-]=[N+]=O`, anilinium `[NH3+]c1ccccc1`, phenol `Oc1ccccc1`, aniline `Nc1ccccc1`, fluorobenzene `Fc1ccccc1`, benzaldehyde `O=Cc1ccccc1`, styrene `C=Cc1ccccc1`, nitrobenzene `[O-][N+](=O)c1ccccc1`, pyrrole `c1cc[nH]c1`,
   furan `c1ccoc1`, thiophene `c1ccsc1`, acrolein `C=CC=O`, SCN- `[S-]C#N`, NO2- `[O-]N=O`; embed 3 conformers. The panel takes the net charge from the drawn structure (+1 for anilinium, -1 for the anions).
2. One ORCA **Geometry Optimization** at the species' method: **`B3LYP 6-31G*`**, or **`B3LYP 6-31+G*`** for the two anions; the optimized conformer is then the canonical one (the script asserts `canonical_method: orca_opt`, `canonical_mapped: true`).
3. One **Fukui functions (Hirshfeld)** run at the same method on that geometry. No job starts while another runs. **What v2 runs:** for each neutral species and the cation, three jobs (N, N-1, N+1), each at `IntAcc 6.0` and with its `HFTyp`; for each anion, four jobs (the anion, its neutral radical, then
   the anion again from HCore and from Hueckel). The stored run carries which it did (`functions`, `grid`, `reference_charge`, `starts_run`), and section 7 refuses a run that did not do it.
4. `fukui_gate_record` writes the stored run.

**Atom labels** are typed per species in the atom order the application embeds (heavy atoms in SMILES order, then hydrogens) and pinned by a test that embeds each SMILES: ring carbons are labelled ipso, ortho, meta or para by graph distance from the carbon that carries the substituent; in the five-membered rings position 2 is the carbon bonded to the heteroatom and 3 the other; acrolein's carbons are beta
(the CH2), alpha and carbonyl; N2O's nitrogens are terminal and central. **A published pair** (two ortho values for phenol, benzaldehyde and styrene) **is matched to the two atoms of that label as an unordered pair**: both lists sorted, each element within T. A single published value for a label with two
equivalent atoms (the two oxygens of NO2-, the two ortho carbons of aniline) is judged by the worse atom, as the first gate judged CO2's oxygens.

**Input validity, not a result:** acrolein has two planar minima; the published one is s-trans. The script asserts that the optimized O=C-C=C dihedral is within 30 degrees of 180; if it is not, **acrolein is NOT EVALUABLE** (section 7) and is rerun from an s-trans start, because the input was not the published
molecule.

**Differences from the published calculations, disclosed and not corrected:** a different program (Gaussian 98 for the source, ORCA here); ORCA's B3LYP uses VWN-5 for the local part of its correlation, and Gaussian's B3LYP uses another form (the first gate's note, not checked here against Gaussian's documentation);
the source's d functions are those of Gaussian's 6-31G*, and whether ORCA's `6-31G*` uses the same Cartesian or spherical d functions was **not checked**; the ions are UKS without annihilation (the source's method for them is not stated beyond "the same level"); ORCA's Hirshfeld promolecule is ORCA's own and the source's was
its authors' own numerical integration; the geometries are ORCA's optimized ones, where the source optimized with Gaussian; **ORCA's integration grid here is `IntAcc 6.0` and the source's is Gaussian's default**; and **for the anions the extra SCF starts of section 0 are used, which the source did not report using**.

## 5. What is recorded

Into `benchmarks/fukui_gate_2/artifacts/`: `floor_records.json` and `floor.json`; `records.json` (one line per attempt of each job, with the run's provenance: method and basis, charge, multiplicity, `functions`, `grid`, `reference_charge`, the number of starts run and failed and how far below the default one the chosen start was, the ORCA version, the input
fingerprint and whether it is the optimized conformer's, the commit and whether `src/` differed from it, and for acrolein the dihedral); `verdict.json` (the outcome, every reason, every compared row with its published value, measured value and signed difference, every site row); `reported_records.json`
and `reported.json`. Nothing is chosen afterwards.

## 6. The noise floors, and the tolerance

**T = 0.02**, fixed here by hand and not by the floor (decision A1). Its evidence: the first gate's `B3LYP/6-31G**` arm reproduced all 23 numbers within 0.0066 (a fact about the calculator and the published values already seen, used only to set the scale); two groups'
published values of CO and formaldehyde at neighbouring levels differ by at most 0.0023; and 0.02 is under half of every decided site margin (Rule C). The share of rows within **0.01** is also written, and decides nothing.

**The floors F** are measured on **two molecules that are in neither gate**: **pyridine at `B3LYP/6-31G*`** (a rigid ring with a heteroatom: the route of the neutral species and the cation) and **formate at `B3LYP/6-31+G*`** (an anion, with extra starts: the route of SCN- and NO2-), each as the largest difference of any atom's f-, f+, f0 or dual descriptor
(for formate f- alone) between the **same input twice** (one input fingerprint, two run ids) and the **whole chain twice** (a second molecule embedded, optimized and run independently).
**The gate can use T only if both are <= 0.005**; otherwise it is NOT EVALUABLE. `fukui_gate_begin` ends the run before one job unless both floors are usable. The floors are measured and committed before the gate runs. (Formate was a stand-in in the development of v2 and its numbers were seen; that does not matter
for a floor, which is a difference between two runs and not a comparison with a published value.)

## 7. The verdicts

Decided by a pure, tested judge (`app/fukui_gate_2.py`). Every reason is collected; none hides another. "Within T" means `|measured - published| <= 0.02` with a float slack of 1e-9.

**NOT EVALUABLE** (nothing is claimed either way) when any of: T is not 0.02; no floor, or a floor above 0.005; an ORCA other than 6.1.1 or none recorded; the runs were made by more than one version of `src/` or by a `src/` that differed from its commit;
a species has no run, or fewer than three attempts failed and none completed; a run's charge or multiplicity is not its species' (+1 for anilinium, -1 for the anions, 0 for the rest, multiplicity 1); a run's method is not its species'; a run's grid is not `IntAcc 6.0`; a run's `functions` is not `f-` for an anion and `f+ f- f0 dual` for every other species,
or its `reference_charge` is not its species' charge, or an anion's run holds an f+, f0 or dual descriptor; a run did not complete; a run did not run on the ORCA-optimized geometry; a run's atoms are not its species'; a run's f+ (where it has one) or f- does not sum to 1 within 0.001; a run's dual descriptor is not f+ - f- or its f0 not their mean (to 1e-9);
one job has two completed attempts; or acrolein fails the input-validity check of section 4. **A start that did not converge, or a lower start that replaced the default one, is recorded and is not a reason: both are the calculation doing what it is specified to do.**

**PASS:** every one of the 47 numbers within T, every one of the 11 statements reproduced, no species left uncomputed.
**PARTIAL:** every **neutral** species (all but anilinium, SCN- and NO2-) reproduced, numbers and statements, and **a charged species** not: a number outside T, a statement missed, or the species not computed.
**FAIL:** any neutral-species number outside T, any neutral statement missed, or a neutral species ORCA could not compute in three attempts. The published values stay the published values, the measured ones are printed beside them with the signed differences, **the word "reproduces" is not used**, and T is not widened.

## 8. After each outcome

* **PASS:** the calculator's stage becomes **LIMITED** and its default visibility **SHOWN**, with the scope stated as: closed-shell neutral molecules and cations at **`B3LYP 6-31G*` or `B3LYP 6-31G**`** (f+ and f-; the two exact method strings: they differ by the hydrogen p functions, and the second is included on the strength of the first
  gate's `B3LYP/6-31G**` arm, which reproduced all 23 of its numbers within 0.0066 but belonged to a gate that failed on its HF arm; that supports it and decides nothing), and **f- of anions at `B3LYP 6-31+G*`** (an anion has no f+). Charged species are covered only as far as the ones tested (anilinium; SCN- and NO2-),
  which the explainer lists. In that scope a result's closing sentence says it was validated against published values and names the record; **at every other method or basis it keeps the "Not validated" sentence**, and HF and diffuse-function levels keep their spin and SCF-solution caveats.
  `docs/explainers/reactivity.md` and the user guide say what was validated and keep section 1's list of what it was not.
* **PARTIAL:** the same, for **neutral** species only; a charged species' result keeps the "Not validated" sentence and says which were not reproduced.
* **FAIL:** the calculator stays **EXPERIMENTAL** and hidden; the record states which numbers failed and by how much. **A failure is a reason to find the cause, not to retire the work**: a difference between programs the published scatter did not bound, a conformer, a basis-set definition (the d-function question of section 4) or a defect in the code is investigated first
  and is the subject of a new preregistration.
* **NOT EVALUABLE:** not a result. See section 9.

## 9. What may be repeated, and what may not

Identical to the first gate: a job that did not finish may be repeated unchanged up to **three attempts**, each a line in `records.json`, and a species whose states do not complete in three attempts is NOT COMPUTED and counts as a failure to reproduce; a job that completed is **never** repeated; NOT EVALUABLE may be repeated after its
cause is fixed, with the same T; **PASS, PARTIAL and FAIL are final**, and nothing about T, the level, the molecules, the published numbers or the rules changes after a decided outcome.

## 10. The reported arm: run, written beside the outcome, and never decides

Every row is marked `decided: false`; the verdict never reads them. **One attempt each, and a refusal or a failure is recorded as what it is.**

* **Cross-source consistency:** CO f-, formaldehyde f- and f+ at `B3LYP/6-31G*`, against `deproft2002` (seen, section 3).
* **The partial columns:** the enolate `C=C[O-]` and phenolate `[O-]c1ccccc1` f- at `B3LYP/6-31+G*` (anions, f- alone), maleic anhydride `O=C1C=CC(=O)O1` and maleimide `O=C1C=CC(=O)N1` f+ at `B3LYP/6-31G*`.
* **The statements not decided** (N2O, NO2-, benzaldehyde, nitrobenzene) and the **experimental selectivity column** of Table 5: our largest ring value beside the class the experiment prefers, as written, with no verdict.
* **The default preset:** the 13 neutral and cation species at **`B3LYP/def2-SVP`**, against the same published numbers (a different basis from the source's, so a measure of basis dependence and not a test; **running it makes those numbers seen, so `def2-SVP` cannot be added to the validated scope by this gate**).
* **Rows within 0.01** of the decided numbers.

## 11. Outcome

*(Empty. The noise floors, the gate's outcome and the reported arm are appended below this rule, each with its commit, and nothing above it changes after the freeze.)*

---

### 11.1 The noise floors, measured 2026-10-18 09:27 to 09:33, before the freeze (committed in `95cf12a2`)

`benchmarks/visual/fukui2_gate_floor.json`, real ORCA 6.1.1, at commit `fa8850aa`; `VERDICT PASS` of the drive (8 assertions, 0 app errors, 0 driver failures; `artifacts/floor.drive_report.json`). Two molecules that are in neither gate: pyridine at
`B3LYP/6-31G*` and formate at `B3LYP/6-31+G*`. For each, the same input twice and the whole chain twice (a second molecule embedded, optimized and run independently): the largest difference of any atom's f-, f+, f0 or dual descriptor
(formate: f- alone) is **0.0 on both routes of both molecules**. **F = 0.0** against the limit of 0.005, so the gate could use T = 0.02, and `fukui2_begin` checked the artifact before the gate started a job.

The drive report's whole-tree `dirty: true` is not the code: the six floor records say `src/` did not differ from its commit, and between that commit and the freeze only this document and the floor artifacts changed
(`git diff --stat fa8850aa 40bf48c7` lists those four files). Small rigid molecules are an easy case for a repeat to agree on, and a floor of exactly zero says ORCA and the application are deterministic here, not that the published values will be reproduced.

### 11.2 The outcome: FAIL, 2026-10-18 09:35 to 09:55 (the one attempt, at the freeze commit `40bf48c7`; committed in `4177a038`)

`benchmarks/visual/fukui2_gate_run.json`, real ORCA 6.1.1, gas phase, **T = 0.02** (section 6; the floor of 11.1 was 0.0). `VERDICT PASS` of the drive (18 assertions, 0 app errors, 0 driver failures; `artifacts/run.drive_report.json`);
**the gate's own verdict, by `app/fukui_gate_2.judge`: FAIL** (`artifacts/verdict.json`).

`artifacts/records.json` holds 15 lines, one per species, every one attempt 1 and completed, **every one on the ORCA-optimized geometry** (`canonical_method: orca_opt`), at ORCA 6.1.1 and `IntAcc 6.0`, at commit `40bf48c7` with `src/` unmodified, 15 distinct stored runs.
The neutral species and anilinium ran three jobs and the two anions four; **no extra start was lower than the default in any of the 15 runs** (`start_gain_ev` 0.0), which is the calculation doing what it is specified to do. Acrolein's optimized O=C-C=C dihedral is 179.96 degrees (s-trans), so the
input-validity check of section 4 held. No condition of section 7's NOT EVALUABLE list applied.

**33 of the 47 numbers are within T (31 within 0.01, 23 within 0.002) and 9 of the 11 site statements are reproduced.** Because F = 0.0, each difference below is a difference from the published value and not run-to-run noise. The 14 numbers outside T belong to seven molecules:

| Molecule (charge) | Atom or site | Published (`deproft2002`) | Measured | Signed difference |
|---|---|---|---|---|
| HCN (0) | C | 0.389 | 0.4361 | +0.0471 |
| HCN (0) | N | 0.502 | 0.4494 | -0.0526 |
| SCN- (-1) | S | 0.606 | 0.6303 | +0.0243 |
| anilinium (+1) | ortho | 0.067 | 0.1441 | +0.0771 |
| anilinium (+1) | meta | 0.095 | 0.1313 | +0.0363 |
| anilinium (+1) | para | 0.175 | 0.0544 | -0.1206 |
| benzaldehyde (0) | ortho (a published pair, the worse atom) | 0.044 | 0.0837 | +0.0397 |
| benzaldehyde (0) | meta (a published pair, the worse atom) | 0.045 | 0.0968 | +0.0518 |
| benzaldehyde (0) | para | 0.072 | 0.0924 | +0.0204 |
| pyrrole (0) | position 3 | 0.068 | 0.1198 | +0.0518 |
| furan (0) | position 2 | 0.272 | 0.1966 | -0.0754 |
| furan (0) | position 3 | 0.107 | 0.1292 | +0.0222 |
| thiophene (0) | position 2 | 0.059 | 0.1762 | +0.1172 |
| thiophene (0) | position 3 | 0.138 | 0.1076 | -0.0304 |

**The two site statements that were not reproduced:** anilinium (published: the largest ring value is para; measured: ortho, 0.1441 against para 0.0544) and thiophene (published: position 3; measured: position 2). The other nine were: HCN's f- on N, SCN-'s on S, the largest ring site
para in phenol, aniline, fluorobenzene and styrene, position 2 in pyrrole and furan, and acrolein's f+ on C-beta.

**Eight of the 15 species have every number within T, and within 0.0067:** phenol (largest difference 0.0016), aniline (0.0009), fluorobenzene (0.0012), styrene (0.0019), nitrobenzene (0.0017), acrolein (0.0024), NO2- (0.0053) and N2O (0.0067). SCN- has two of its three numbers within T (C and N).

By section 7 the **neutral** species with a number outside T (HCN, benzaldehyde, pyrrole, furan, thiophene) make the outcome **FAIL**; the two charged misses (anilinium, SCN-) alone would have made it PARTIAL. T is not widened, the word "reproduces" is not used of the gate as a whole,
and the gate is not re-run: a decided outcome is final (section 9).

### 11.3 The reported arm, 2026-10-18 09:56 to 10:22: decides nothing

`benchmarks/visual/fukui2_gate_reported.json`, real ORCA 6.1.1, at commit `7e1e140a` (the outcome commit as it stood when the arm ran; its message was amended afterwards into `4177a038`, which has the same tree, `ea61f252`), `VERDICT PASS` of the drive (22 assertions, 0 app errors, 0 driver failures;
`artifacts/reported.drive_report.json`). 19 jobs, every one attempt 1 and completed (`artifacts/reported_records.json`), written as 60 rows, each marked `decided: false`, of which **48 are within 0.02** (`artifacts/reported.json`).

| Group | Level | Rows | Within 0.02 | Largest difference |
|---|---|---|---|---|
| CO f- (cross-source consistency) | `B3LYP/6-31G*` | 2 | 2 | 0.0033 |
| formaldehyde f- and f+ | `B3LYP/6-31G*` | 6 | 6 | 0.0033 |
| enolate f- (a partial column) | `B3LYP/6-31+G*` | 3 | 3 | 0.0063 |
| phenolate f- (a partial column) | `B3LYP/6-31+G*` | 3 | 3 | 0.0026 |
| maleic anhydride f+ (a partial column) | `B3LYP/6-31G*` | 2 | 2 | 0.0003 |
| maleimide f+ (a partial column) | `B3LYP/6-31G*` | 2 | 2 | 0.0005 |
| the 13 neutral and cation species' decided numbers, at the application's default preset | `B3LYP/def2-SVP` | 42 | 30 | 0.1211 (anilinium, para) |

* **At the source's own levels all 18 rows are within 0.0063**, including the four partial-column species the rules kept out of the decision and the two molecules the first gate shares with this source.
* **The default preset reproduces the 6-31G* numbers, misses included.** Over the 42 numbers, the median difference between the `6-31G*` value and the `def2-SVP` one is 0.0006 and the largest 0.0047 (HCN, N). The 12 rows outside 0.02 at `def2-SVP` belong to the same six molecules as at `6-31G*` (HCN, anilinium, benzaldehyde, pyrrole,
  furan, thiophene; the anions SCN- and NO2- were not run there); benzaldehyde's para is the one number that changes side (0.0204 at `6-31G*`, within at `def2-SVP`). **The misses are not a matter of the basis set.** Running this arm made those `def2-SVP` numbers seen, so `def2-SVP` cannot be added to a validated scope by this gate (section 10).
* **The four statements the rules left out** (`artifacts/reported_sites.json`; **written afterwards**: the drive step `fukui2_report` was given the reported arm's records only, and `reported_site_rows` looks each statement up under the species' gate level, so `reported.json` has an empty `site_rows`; `reported_sites.py` makes the one
  call it should have made, with the same function and the gate's own records, and runs nothing). N2O f-: published O, measured O. NO2- f-: published O, measured O. Benzaldehyde: published largest ring site para, **measured meta** (the experimental order printed beside it in Table 5 is m > o >> p). Nitrobenzene: published meta,
  measured meta (experiment m >> o > p). These decide nothing, and the experimental column is not a target: the 2019 benchmark found the Fukui function the weaker descriptor of where a reaction goes [source:wang2019].

### 11.4 After the outcome: two probes of one candidate cause, neither of them the gate and neither able to change it

Written after 11.2 existed, **with the published numbers in view**. They are a search and not a preregistered test: each looks for the cation state a published number belongs to, among a handful of candidates, so what they find is a candidate cause and not an established one.
Files: `cation_states_probe.py` and `route_check.py`, standalone ORCA 6.1.1 in fresh directories (the second writes through the application's own input builder), results in `artifacts/cation_states_probe.json` and `artifacts/route_check.json`.

**The candidate, as it stood when the probe was written.** The molecules that missed were thought to have cations whose lowest states lie close together (benzaldehyde, the five-membered rings, anilinium, HCN), while eight others reproduce to 0.0067. The application's N-1 job starts from the neutral's converged
orbitals and removes the electron of the HOMO, so it reaches one state, whichever its SCF falls into; the source's program may have reached another. The probe tests that, and finds it fits three of the molecules and not the rest.

**Probe 1, `cation_states_probe.py`.** The seven molecules and four that did not miss (phenol, aniline, styrene, N2O), `B3LYP/6-31G*` (`6-31+G*` for SCN-), each geometry ORCA-optimized from an RDKit ETKDG (seed 7) + MMFF embedding, **so not the gate's geometry**; the N state restricted, the N-1 state unrestricted,
`IntAcc 6.0`, Hirshfeld printed. The N-1 state is converged four times, with its hole put in the HOMO, HOMO-1, HOMO-2 and HOMO-3 of the N state by rotating the beta orbitals of the guess (`%scf Rotate {HOMO-k, HOMO, 90, 1, 1} end`; checked first on water, where the 3a1 hole came out 2.2 eV above the 1b1 one).
A start can relax into another state, so the four are not four distinct states; for each the probe records the state it ended in (energy above the lowest found, `<S^2>`, Hirshfeld f-) and the largest distance of that f- from the published numbers.

| Molecule | Lowest state found: largest distance to the published numbers | A state that matches the published numbers |
|---|---|---|
| anilinium | 0.1206 | **+0.094 eV above the lowest, distance 0.0013** |
| benzaldehyde | 0.0518 (two starts reach it) | **+0.145 eV above the lowest, distance 0.0011** (a third state, +0.127 eV, is 0.0696 away) |
| thiophene | 0.1172 | **+0.449 eV above the lowest, distance 0.0021** |
| HCN | 0.0526 (the pi-hole state; two starts, a degenerate pair) | none: the sigma-hole state (+0.392 eV) is 0.0382 away; the published C 0.389 and N 0.502 lie between the two states' values (C 0.436 and 0.351, N 0.449 and 0.531) at mixing fractions that differ (0.55 and 0.65), and the published H 0.109 lies below both (0.1145, 0.1183) |
| pyrrole | 0.0518 | none: the next state (+0.837 eV) is 0.1123 away |
| furan | 0.0754 | none: the next state (+1.370 eV) is 0.1762 away |
| SCN- (S) | 0.0243 (all four starts reach one state) | none to find |
| phenol, aniline, styrene, N2O (did not miss) | 0.0016, 0.0009, 0.0019, 0.0067 | the lowest state is the one that matches; phenol, styrene and N2O have no distinct competing state (every start ended in the lowest), and aniline's (+1.213 eV) is 0.0799 away |

**For anilinium, benzaldehyde and thiophene the published numbers match, to between 0.0011 and 0.0021 (a tenth of T), the f- of a cation state that lies 0.094, 0.145 and 0.449 eV above the lowest state this calculation finds.** In those three the neutral's HOMO and the next orbital lie 0.11, 0.24 (HOMO-1; HOMO-2 at 0.32) and 0.42 eV apart, and
where the competing state was found as a distinct state its energy above the lowest tracks the neutral's orbital-energy gap (orbital gap and ΔSCF gap, in eV: anilinium 0.109 and 0.094, thiophene 0.419 and 0.449, pyrrole 0.835 and 0.837, furan 1.332 and 1.370, aniline 1.151 and 1.213; the differences are 0.002 to 0.062).
**The gap does not tell a missing molecule from one that matched**: pyrrole's 0.835 eV is above phenol's 0.815 eV and pyrrole is the one that missed.

**Probe 2, `route_check.py`.** Probe 1's plain-aufbau start (hole 0) for benzaldehyde landed 0.145 eV above the lowest state, where the gate's run, made by the application, had landed on the lowest. Two things differed: the geometry, and the form of the input (a separate `MORead` job, against
the application's compound input whose second job reads the first job's orbitals by default). This writes **the application's own three-job input** (`OrcaQuantumEngineProvider._build_fukui_input`, the builder the service calls) on probe 1's geometries of the three molecules and runs it once:

| Molecule | N-1 state the application's input reached, on probe 1's geometry | Largest distance to the published numbers |
|---|---|---|
| benzaldehyde | **+0.145 eV above the lowest** | **0.0011** |
| anilinium | the lowest | 0.1206 |
| thiophene | the lowest | 0.1172 |

**So the application's own route reaches the state that matches the published benzaldehyde numbers on one geometry and the lowest state on another**: two ORCA-optimized geometries of one molecule at one level (the gate's and probe 1's), the same code, N-1 states 0.145 eV apart. The gate's geometry is not stored, so how the two
differ was not measured, and nothing here says which is nearer the true minimum. For anilinium and thiophene the application's route lands on the lowest state on this geometry as it did on the gate's, so those two misses do not depend on the geometry.

### 11.5 What this says, and what it does not

* **The outcome stands.** FAIL, with T = 0.02, one attempt, no re-run, and the word "reproduces" not used of the gate. Nothing in 11.3 or 11.4 changes a number of 11.2.
* **The misses are not a fault of wiring or arithmetic that any measurement here shows.** Eight species reproduce in every number to 0.0067; all 18 own-level rows of the reported arm are within 0.0063; the same numbers come out at two basis sets (median difference 0.0006); the floor is 0.0.
* **For three of the six molecules that missed in a neutral or a cation (anilinium, benzaldehyde, thiophene), the published numbers belong to a cation state above the lowest one this calculation finds.** That is a candidate cause found after the outcome by choosing among a few states with the published numbers in view; it is strong (three
  matches to 0.0021 or better against a tolerance of 0.02) and it is not a preregistered result.
* **What it implies about the calculator, measured:** for a molecule whose cation has close-lying states, the application's f- is the f- of whichever state ORCA's SCF reaches from the neutral's orbitals. It does not look for a lower state or say that another one is close (it does that for the starts of an anion, not for the N-1 state), and for
  benzaldehyde the state it reached depended on which geometry it was given.
* **HCN, pyrrole, furan and the sulfur of SCN- are not explained.** Nothing measured here accounts for them, and the cation-state candidate does not: neither alternative state lies near their published numbers.
* **It does not say the published values are wrong or ours are.** Which state a condensed Fukui function ought to describe is not decided by anything measured here, and the order of states 0.1 eV apart in a B3LYP ΔSCF is itself uncertain. It does not say that taking the lowest of several holes would reproduce
  the published numbers: for these three molecules the lowest state is the one that does **not**. And it does not say that a small orbital gap marks a molecule that will miss (the pyrrole and phenol numbers above).

### 11.6 The consequence, and what was left open

Section 8 for a FAIL: **the calculator stays EXPERIMENTAL and hidden.** Its standing sentence and its support reason were rewritten to say it failed two preregistered checks, with the numbers (33 of 47 within 0.02, the other 14 in seven named molecules, three of them matched by a higher cation state, and the first check's miss by 0.0014),
and `docs/explainers/reactivity.md`, the user guide and the changelog were brought into line with this section.

**A failure is a reason to find the cause, not to retire the work (section 8).** The cause is found for three of the six neutral and cation molecules and not for HCN, pyrrole, furan or the sulfur of SCN-. Anything further needs a new preregistration with data not seen here. Two shapes it could take, neither started, both Alex's call:
(a) a calculation that converges the N-1 state from several holes, reads the lowest and says when another lies within a stated window; it would be gated on its own reproducibility (the same molecule at two geometries) and against a reference whose states are identified, and not on this source for these three molecules, whose numbers
it would not reproduce; (b) a caveat only, which says when the neutral's HOMO and next orbital are within a stated gap and claims nothing else, gated on whether it fires on the molecules that miss and stays quiet on those that match. Alex's earlier answer that an anion's f+ might come back as an option later (C1) is untouched: it
could not change what this gate tested.

---

## Decisions (kept as a record)

Decided by Alex on 2026-10-18: **A1** T = 0.02. **A2** the anions are decided, through an f- only mode (so the calculation had to be changed first). **A4** a pass promotes to LIMITED and SHOWN, scoped to `B3LYP 6-31G*` and `B3LYP 6-31G**`. **A5** the calculation tested is the
robust-anion one (finer grid by default, the lowest of several anion starts, flagged when they differ). Left at the recommended default, not asked: **A3** any neutral miss is a FAIL, as in the first gate; **A6** acrolein is NOT EVALUABLE and rerun from an s-trans start if its dihedral is not within 30 degrees of 180.

**Asked of Alex on 2026-10-18, and answered:**

* **C1. An anion no longer gets f+, f0 or the dual descriptor.** The first release computed them from a dianion; v2 does not (`chem/fukui_plan.py`). The three anions of the first gate (CN-, NCO-, CNO-) had f+ compared there, and that record stands; the calculator no longer produces those numbers.
  *Alex leans to yes and would not object to an optional f+ for anions later.* The gate tests the default, which is f- only, so an optional switch, if one is ever added, cannot change what this gate tests.
* **C2. A third method string in the promoted scope:** `B3LYP 6-31+G*`, for the f- of anions only (a pass at the two anions SCN- and NO2- is its whole evidence). *Alex: yes, include it.*
* **C3. A charged species that does not reproduce gives PARTIAL, not FAIL** (the first gate's rule for its anions), so that a miss on one of the three charged species does not withhold the promotion of the neutral molecules. *Alex: PARTIAL.*
* **C4. When to freeze.** *Alex: freeze and run once a rehearsal on molecules that are not in the gate (a cation, a linear anion, and the two noise floors) comes back clean; stop and say so if it finds anything that would change this document.*
