# The second Fukui gate: preregistration

> **DRAFT, 2026-10-18. NOTHING IS FROZEN, and no ORCA job of a gate species has been run.** The freeze will be the commit that adds the typed tables,
> the judge, its tests and the scripts, after Alex has confirmed the decisions listed at the end ("Decisions needed before the freeze"). Until then this
> file may change freely; from the freeze on, sections 0 to 10 are fixed and section 11 is where the outcome is written, below a rule, in later commits.

This is the second preregistered check of the calculator **Fukui functions (Hirshfeld)** (`orca.fukui`, `chem/fukui.py`, `chem/orca_engine.py`). The first,
`benchmarks/fukui_gate/PREREGISTRATION.md`, ended in **FAIL by 0.0014 on one quantity** (CO's f- at `HF/6-31G**`), which is final and is not touched here; the calculator
ships as experimental and not validated. This gate asks a different question of different published numbers.

## 0. Why a second gate, and what it is built on

Measurements made after the first outcome (`benchmarks/fukui_gate/PREREGISTRATION.md` 11.5 and 11.6) say where a published-table check can and cannot work:

* **At the `6-31G**` levels the numbers do not depend on the integration grid, on the SCF starting guess or on the starting embedding** (a finer grid changed no value on 14 jobs;
  no start found an anion solution lower than the default; three embeddings agreed to 0.0004). That is the regime a published table can test.
* **With diffuse functions f+ is not a reproducible number** (the unbound anion has more than one SCF solution, and two molecules gave two different anions from three embeddings),
  and the published diffuse-level f+ values themselves match one solution in one case and another in the next. **No diffuse-level f+ is a target here.**
* **The first gate's data cannot be used again.** Its B3LYP arm reproduced all 23 numbers within 0.0066, but those numbers are known; a gate built on them would be circular.
  What is needed is published values for **molecules the first gate never used**, which `deproft2002` supplies.

This gate tests the calculation **as it stands at the freeze commit, which is pull request 374's** (or master's, once that has merged), unchanged. The changes that are being considered for a later version of it (a finer grid by
default, the lowest of several anion starts) are numerically no-ops at these levels for neutral molecules (11.6.2 and 11.6.4), and are not part of what is tested.

## 1. The claim, and what a pass does not say

> On ORCA 6.1.1, the Fukui calculation, run through the application on the geometry ORCA optimized at the same level, at **`B3LYP/6-31G*`**, reproduces **42 published Hirshfeld condensed values**
> of **13 molecules** (f- of HCN, N2O, anilinium, phenol, aniline, fluorobenzene, benzaldehyde, styrene, nitrobenzene, pyrrole, furan and thiophene; f+ of acrolein), each within **T = 0.02**, and puts its
> largest value on the published site in **10 site statements**.

A pass says the calculator's wiring and arithmetic reproduce what a second group published, for molecules the first gate did not touch, on this machine at one level. It does **not** say that:

* the largest condensed Fukui value is where a reaction goes (`wang2019` found the Fukui function the weaker descriptor); the experimental selectivities in the source are reported beside our values and decide nothing;
* any other level reproduces: **not HF** (the first gate's miss, with its unrestricted cations), **not a basis set with diffuse functions**, **not `def2-SVP`, which is the application's default preset**
  (it is run in the reported arm, section 10, and is therefore seen); any other functional, solvent or ORCA version;
* an anion is reproduced (section 3 keeps every anion out of the decision and says why);
* the result is independent of the first gate's source: both are Gaussian 98 calculations (section 4);
* f0 or the dual descriptor is validated by a publication.

## 2. What has been run or seen before the freeze, disclosed

* The first gate and its post-gate measurements (`benchmarks/fukui_gate/`), at `6-31G**`, `6-311+G**` and `def2-SVP`, on CO, CO2, formaldehyde, acetone, CN-, NCO-, CNO- (and formaldehyde, propene and
  pyridine in the exploration at `def2-SVP` and `def2-SVPD`). **Only CO and formaldehyde are also in `deproft2002`**, and they are kept out of the decision for that reason (section 3).
* **No ORCA job of any other species in this document has been run, at any level.** One throwaway check was made that ORCA 6.1.1 accepts the keywords `B3LYP 6-31G*` and `B3LYP 6-31+G*`: a single point of
  water and of hydroxide, no Fukui job, no f value read.
* `deproft2002` was read and its Tables 4 to 6 were transcribed from the page images (the text layer scrambles them); every complete column was summed (section 3), and ten rows and acrolein's three values were
  compared with the second printing in `sablon2007` (Table III and Fig. 1). The published numbers of CO and formaldehyde were compared with the first gate's published numbers (published against published, no ORCA):
  they differ by at most 0.0023.
* The noise floor of section 6 has not been measured.

## 3. The published numbers, and the rules that decide which may be targets

**Source: `deproft2002`** (De Proft, Van Alsenoy, Peeters, Langenaeker, Geerlings, *J. Comput. Chem.* 23, 1198, doi 10.1002/jcc.10067), Tables 4, 5 and 6. Gaussian 98, geometries fully optimized and densities obtained at
**`B3LYP/6-31G*`** (`B3LYP/6-31+G*` for the anions), Hirshfeld populations with the Yang-Mortier finite differences `f+_k = q_k(N+1) - q_k(N)` and `f-_k = q_k(N) - q_k(N-1)` in terms of populations, three decimals, values in e, hydrogens
averaged over the hydrogens of a heavy atom. The paper does not say whether the ions use the neutral geometry (the first gate's source did not either; the application's calculation is vertical).

**Table 4, f-** (formula order of the paper): HCN H 0.109, C 0.389, N 0.502; N2O (terminal N, central N, O) 0.399, 0.173, 0.428; CO C 0.687, O 0.314; H2CO O 0.433, C 0.229, H 0.169; SCN- S 0.606, C 0.115, N 0.279;
NO2- N 0.310, O 0.345 (each O); CH2CHO- C 0.324, C 0.131, O 0.273 (hydrogens not listed).
**Table 5, f-, ring carbons** (ortho, meta, para; two values where the two ortho or the two meta carbons differ; heterocycles by position 2 and 3):
anilinium o 0.067, m 0.095, p 0.175; phenolate o 0.102, m 0.057, p 0.136; phenol o 0.091 and 0.081, m 0.073 and 0.064, p 0.144; aniline o 0.080, m 0.061, p 0.131; fluorobenzene o 0.087, m 0.078, p 0.158;
benzaldehyde o 0.033 and 0.044, m 0.045 and 0.044, p 0.072; styrene o 0.065 and 0.059, m 0.054 and 0.059, p 0.115; nitrobenzene o 0.118, m 0.126, p 0.048; pyrrole 2 0.194, 3 0.068; furan 2 0.272, 3 0.107; thiophene 2 0.059, 3 0.138.
**Table 6, f+:** H2CO O 0.308, C 0.397, H 0.147; acrolein C-beta 0.211, C-alpha 0.116, carbonyl C 0.171; maleic anhydride carbonyl C 0.097, CH 0.145; maleimide carbonyl C 0.096, CH 0.137.

**Rule A, the sum rule.** A column of f over *all* the atoms of a molecule sums to 1, and each printed value carries up to 0.0005 of rounding. A complete column more than **0.002** from 1 is a misprint and is dropped whole. The complete columns are
HCN (1.000), N2O (1.000), CO (1.001), H2CO f- (1.000), H2CO f+ (0.999), SCN- (1.000) and NO2- (1.000); none is dropped. The enolate's hydrogens are not listed, so its column cannot be summed.

**Rule B, a second printing.** A column that omits atoms cannot be summed. A number from such a column is a target only where **a second printing agrees with it exactly**. `sablon2007` (Sablon, De Proft, Ayers, Geerlings, *J. Chem. Phys.* 126, 224108) reprints the finite-difference Hirshfeld values of `deproft2002`
(its Table III for ten of the eleven rings, which omits phenolate; its Fig. 1 for acrolein's three carbons), and every reprinted number agrees with the original. **This guards against a misprint and against my transcription. It is the same group's own data, so it does not guard against a
difference of method, and it is weaker than the first gate's second source (a different program).**

**The decided numbers: 42.** HCN 3 and N2O 3 (complete columns, Rule A); anilinium 3, phenol 5, aniline 3, fluorobenzene 3, benzaldehyde 5, styrene 5, nitrobenzene 3, pyrrole 2, furan 2, thiophene 2 (33, Rule B); acrolein f+ 3 (Rule B).

**Kept out of the decision, and run in the reported arm (section 10):**

* **Every anion** (SCN-, NO2-, the enolate, phenolate). The calculator computes the N+1 state of every species, which for an anion is a dianion, and at the source's `6-31+G*` that dianion is unbound with diffuse functions on it, the case
  that was refused in the first gate's reported arm. The source published only f- for them. **Gating them needs a calculation that does not run the N+1 state, which does not exist; that is a later change and a later preregistration.**
* **CO and formaldehyde:** the first gate's numbers for them are known, and the source's differ from the first gate's published values by at most 0.0023, so the outcome would carry no information.
* **Maleic anhydride and maleimide f+** and **phenolate f-:** partial columns with no second printing.

**Rule C, site statements.** A statement "the largest value is on X" is **decided only if the published margin (the expected site over the next listed one) is at least twice the tolerance** (0.04, with the first gate's float slack of 1e-9).
A statement about a whole molecule (HCN) needs a complete column. **A statement about a table that lists only some atoms is restricted to the atoms it lists, and says so:** for the rings it is about the largest of the ring-carbon values listed (ortho, meta, para, or positions 2 and 3), not about the
ipso carbon, the substituent or the hydrogens, and for acrolein it is about the three carbons. (A statement about a whole molecule from a partial column would also need the expected value to exceed all the weight the column leaves unlisted; none is decided here, and the enolate's, in the reported arm, would be.)
**Decided (10):** HCN f- on N; the largest ring site is para in anilinium, phenol, aniline, fluorobenzene and styrene; position 2 in pyrrole and furan; position 3 in thiophene; acrolein f+ on C-beta among its carbons (margin 0.040, exactly twice T).
**Listed and not decided (three):** N2O f- on O (margin 0.029), benzaldehyde's largest ring site (para, margin 0.027) and nitrobenzene's (meta, margin 0.008). The published values for thiophene put the largest value on position 3 where experiment says 2; the statement
reproduces **the published ordering** and is not a claim about experiment.

## 4. Procedure

The application's own path throughout, driven by `OPENCHEM_DRIVE` (no mouse), on this machine's ORCA (`D:\ORCA\orca.exe`, 6.1.1), gas phase; `benchmarks/fukui_gate_2/make_scripts.py` will write the scripts. For each of the **13 decided species** at **`B3LYP 6-31G*`**:

1. Add it from its SMILES: HCN `C#N`, N2O `[N-]=[N+]=O`, anilinium `[NH3+]c1ccccc1`, phenol `Oc1ccccc1`, aniline `Nc1ccccc1`, fluorobenzene `Fc1ccccc1`, benzaldehyde `O=Cc1ccccc1`, styrene `C=Cc1ccccc1`, nitrobenzene `[O-][N+](=O)c1ccccc1`, pyrrole `c1cc[nH]c1`,
   furan `c1ccoc1`, thiophene `c1ccsc1`, acrolein `C=CC=O`; embed 3 conformers. The panel takes the net charge from the drawn structure (+1 for anilinium).
2. One ORCA **Geometry Optimization** at the method; the optimized conformer is then the canonical one (the script asserts `canonical_method: orca_opt`, `canonical_mapped: true`).
3. One **Fukui functions (Hirshfeld)** run at the same method on that geometry. No job starts while another runs.
4. `fukui_gate_record` writes the stored run.

**Atom labels** are typed per species in the atom order the application embeds (heavy atoms in SMILES order, then hydrogens) and pinned by a test that embeds each SMILES: ring carbons are labelled ipso, ortho, meta or para by graph distance from the carbon that carries the substituent; in the five-membered rings position 2 is the carbon bonded to the heteroatom and 3 the other; acrolein's carbons are beta
(the CH2), alpha and carbonyl; N2O's nitrogens are terminal and central. **A published pair** (two ortho values for phenol, benzaldehyde and styrene) **is matched to the two atoms of that label as an unordered pair**: both lists sorted, each element within T. A single published value for a label with two
equivalent atoms is judged by the worse atom, as the first gate judged CO2's oxygens.

**Input validity, not a result:** acrolein has two planar minima; the published one is s-trans. The script asserts that the optimized O=C-C=C dihedral is within 30 degrees of 180; if it is not, **acrolein is NOT EVALUABLE** (section 7) and is rerun from an s-trans start, because the input was not the published
molecule.

**Differences from the published calculations, disclosed and not corrected:** a different program (Gaussian 98 for the source, ORCA here); ORCA's B3LYP uses VWN-5 for the local part of its correlation, and Gaussian's B3LYP uses another form (the first gate's note, not checked here against Gaussian's documentation);
the source's d functions are those of Gaussian's 6-31G*, and whether ORCA's `6-31G*` uses the same Cartesian or spherical d functions was **not checked**; the ions are UKS without annihilation (the source's method for them is not stated beyond "the same level"); ORCA's Hirshfeld promolecule is ORCA's own and the source's was
its authors' own numerical integration; the geometries are ORCA's optimized ones, where the source optimized with Gaussian.

## 5. What is recorded

Into `benchmarks/fukui_gate_2/artifacts/`: `floor_records.json` and `floor.json`; `records.json` (one line per attempt of each job); `verdict.json` (the outcome, every reason, every compared row with its published value, measured value and signed difference, every site row); `reported_records.json`
and `reported.json`. Nothing is chosen afterwards.

## 6. The noise floor, and the tolerance

**T = 0.02**, fixed here by hand and not by the floor (decision A1). Its evidence: the first gate's `B3LYP/6-31G**` arm reproduced all 23 numbers within 0.0066 (a fact about the calculator and the published values already seen, used only to set the scale); two groups'
published values of CO and formaldehyde at neighbouring levels differ by at most 0.0023; and 0.02 is under half of every decided site margin (Rule C). The share of rows within **0.01** is also written, and decides nothing.

**The floor F** is measured on **pyridine at `B3LYP/6-31G*`, a molecule that is in neither gate** (a rigid ring with a heteroatom, so no rotor or hydrogen-numbering ambiguity), as the largest difference of any atom's f+, f-, f0 or dual descriptor between the **same input twice** (one input fingerprint, two run ids) and the **whole chain twice**
(a second pyridine embedded, optimized and run independently). **The gate can use T only if F <= 0.005**; otherwise it is NOT EVALUABLE. `fukui_gate_begin` ends the run before one job unless the floor is usable. The floor is measured and committed before the gate runs.

## 7. The verdicts

Decided by a pure, tested judge. Every reason is collected; none hides another. "Within T" means `|measured - published| <= 0.02` with a float slack of 1e-9.

**NOT EVALUABLE** (nothing is claimed either way) when any of: T is not 0.02; no floor, or F > 0.005; an ORCA other than 6.1.1 or none recorded; a species has no run, or fewer than three attempts failed and none completed; a run's charge or multiplicity is not its species' (+1 for anilinium, 0 for the rest, multiplicity 1);
a run did not complete; a run did not run on the ORCA-optimized geometry; a run's atoms are not its species'; a run's f+ or f- does not sum to 1 within 0.001; a run's dual descriptor is not f+ - f- or its f0 not their mean (to 1e-9); one job has two completed attempts; or acrolein fails the input-validity check of section 4.

**PASS:** every one of the 42 numbers within T, every one of the 10 statements reproduced, no species left uncomputed.
**PARTIAL:** every **neutral** species (all but anilinium) reproduced, numbers and statements, and the **cation** (anilinium) not: a number outside T, a statement missed, or the species not computed.
**FAIL:** any neutral-species number outside T, any neutral statement missed, or a neutral species ORCA could not compute in three attempts. The published values stay the published values, the measured ones are printed beside them with the signed differences, **the word "reproduces" is not used**, and T is not widened.

## 8. After each outcome (decision A4)

* **PASS:** the calculator's stage becomes **LIMITED** and its default visibility **SHOWN**, with the scope stated as: closed-shell molecules, at **`B3LYP 6-31G*` or `B3LYP 6-31G**`** (the two exact method strings; they differ by the hydrogen p functions, and the first gate's `B3LYP/6-31G**` arm, whose verdict was set by its HF arm,
  reproduced all of its 23 numbers within 0.0066; that supports the second string and decides nothing). Charged species are covered only as far as the ones tested (anilinium here; CN-, NCO- and CNO- in the first gate's B3LYP arm), which the explainer lists; no anion is claimed beyond those. In that scope a result's closing sentence says it was validated against published values and names the record; **at every other method or basis it keeps today's "Not validated" sentence**, and HF and diffuse-function levels keep their
  spin and SCF-solution caveats. `docs/explainers/reactivity.md` and the user guide say what was validated and keep section 1's list of what it was not.
* **PARTIAL:** the same, for **neutral** species only; a cation's result keeps the "Not validated" sentence and says the cation was not reproduced.
* **FAIL:** the calculator stays **EXPERIMENTAL** and hidden; the record states which numbers failed and by how much. **A failure is a reason to find the cause, not to retire the work**: a difference between programs the published scatter did not bound, a conformer, a basis-set definition (the d-function question of section 4) or a defect in the code is investigated first
  and is the subject of a new preregistration.
* **NOT EVALUABLE:** not a result. See section 9.

## 9. What may be repeated, and what may not

Identical to the first gate: a job that did not finish may be repeated unchanged up to **three attempts**, each a line in `records.json`, and a species whose states do not complete in three attempts is NOT COMPUTED and counts as a failure to reproduce; a job that completed is **never** repeated; NOT EVALUABLE may be repeated after its
cause is fixed, with the same T; **PASS, PARTIAL and FAIL are final**, and nothing about T, the level, the molecules, the published numbers or the rules changes after a decided outcome.

## 10. The reported arm: run, written beside the outcome, and never decides

Every row is marked `decided: false`; the verdict never reads them. **One attempt each, and a refusal or a failure is recorded as what it is.**

* **Cross-source consistency:** CO f-, formaldehyde f- and f+ at `B3LYP/6-31G*`, against `deproft2002` (seen, section 3).
* **The anions at `B3LYP/6-31+G*`:** SCN- `[S-]C#N`, NO2- `[O-]N=O`, the enolate `C=C[O-]` and phenolate `[O-]c1ccccc1`: what the shipped calculation does with them (it runs a dianion), their f- where it completes, against the source.
* **The partial columns:** maleic anhydride `O=C1C=CC(=O)O1` and maleimide `O=C1C=CC(=O)N1` f+, phenolate f-.
* **The three statements not decided** (N2O, benzaldehyde, nitrobenzene) and the **experimental selectivity column** of Table 5: whether the largest ring value of our f- is on the class the experiment prefers.
* **The default preset:** the 13 decided species at **`B3LYP/def2-SVP`**, against the same published numbers (a different basis from the source's, so a measure of basis dependence and not a test; **running it makes those numbers seen, so `def2-SVP` cannot be added to the validated scope by this gate**).
* **Rows within 0.01** of the decided numbers.

## 11. Outcome

*(Empty. The noise floor, the gate's outcome and the reported arm are appended below this rule, each with its commit, and nothing above it changes after the freeze.)*

---

## Decisions needed before the freeze (to be deleted when they are made)

* **A1. The tolerance.** `T = 0.02`, as in the first gate (recommended: continuity, and a stricter 0.01 would sit close to the 0.0066 the first gate's own B3LYP arm reached), with the share within 0.01 reported; or `T = 0.01`.
* **A2. What decides.** The 42 numbers and 10 statements of section 3, with **every anion kept out** because the calculation runs a dianion (recommended), or hold the gate until the calculation can skip the N+1 state and gate the anions too.
* **A3. How strict.** Any neutral miss is a FAIL, as in the first gate (recommended; the first gate's B3LYP arm passed all of its numbers), or a graded rule such as "up to two misses, none off by more than 0.04, is PARTIAL".
* **A4. What a pass promotes.** LIMITED and SHOWN, scoped to `B3LYP 6-31G*` and `B3LYP 6-31G**` (recommended), or LIMITED and still HIDDEN, or the single method string of this gate only.
* **A5. What is tested.** The calculation as it is in pull request 374 (recommended: the changes considered after it are no-ops at these levels), or wait until a finer grid and a lowest-of-several-starts anion are in and test those.
* **A6. Acrolein's input check.** NOT EVALUABLE and rerun from an s-trans start if the dihedral is not within 30 degrees of 180 (recommended), or drop acrolein.
