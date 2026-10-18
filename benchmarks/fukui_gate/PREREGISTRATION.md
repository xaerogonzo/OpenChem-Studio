# The Fukui gate: preregistration

**Frozen 2026-10-18, in the commit that adds this file, `src/openchem/app/fukui_gate.py`, `tests/test_fukui_gate.py`, the drive steps that use
it and the three scripts. Before any ORCA job of a gate species at a gate level, and before the noise floor below has been measured.**
Everything in sections 1 to 10 is fixed. Section 11 is where the outcome is written, below a rule, and nothing above the rule is edited
afterwards. An amendment is allowed only before the number it concerns exists, and it is a new commit that says what it changes and why
(the held-out discipline this project already follows).

The calculator is the Quantum Chemistry panel's **Fukui functions (Hirshfeld)** calculation (`orca.fukui`, `chem/fukui.py`,
`chem/orca_engine.py`). The preceding choices were made by Alex in chat on 2026-10-18, before this file: Hirshfeld charges only; an
open-shell species is refused and an unbound anion is computed with a caveat; four per-atom outputs (f+, f-, f0 and the dual descriptor); the
gate rests on published tables and on documented sites; the tolerance is 0.02; the verdict is decided on the `6-31G**` levels and the rest is
reported; a FAIL means the calculator is not shipped. The consequence of PARTIAL (section 8) was confirmed by Alex in chat on 2026-10-18 after the sources were read, with the remark that he dislikes
retiring or not shipping something unless it truly cannot be done; section 8 keeps that.

## 1. The claim, and what a pass does not say

> On ORCA 6.1.1, the Fukui calculation, run through the application on the geometry ORCA optimized at the same level, at `B3LYP/6-31G**` and
> `HF/6-31G**`, reproduces **54 published Hirshfeld condensed values** (f+ and f- of CO, CO2, formaldehyde, CN-, NCO- and CNO-) each within
> **T = 0.02**, and puts its largest value on the documented atom in **13 documented site statements** (seven sites, at each level where the published margin allows).

A pass says the calculator's wiring and arithmetic reproduce what two programs and three papers published, on this machine, at those two
levels. It does **not** say that:

* the largest condensed Fukui value is where a reaction goes. A 2019 benchmark found the Fukui function the weaker descriptor and weakest
  for nucleophiles (`wang2019`); this gate tests reproduction and not prediction;
* f+ is reliable at a basis set with diffuse functions, which the decided levels do not have (the diffuse columns are reported, section 10);
* any other level, molecule, solvent or ORCA version reproduces;
* the dual descriptor or f0 is validated by a publication. They are checked to be exactly f+ - f- and (f+ + f-)/2 in every run
  (section 7), and nothing more is claimed for them.

## 2. What has been run or seen before this commit, disclosed

* Exploration on formaldehyde, propene and pyridine at B3LYP/def2-SVP and def2-SVPD (`exploration.md`), which chose the charge scheme. Its
  formaldehyde numbers were seen **before the published tables were read**. Formaldehyde is a gate species at the `6-31G**` levels, where no
  ORCA job has been run, and in the reported arm at the default level, where its numbers are the ones already seen.
* A water HF/STO-3G run behind a test fixture, and a plumbing check of three gate species (CN-, NCO-, acetone) at HF/STO-3G, which is **not** a
  gate level. For the plumbing check only the molecule's charge, its atom order, the method, the ORCA version, the geometry flag and the sum
  rule were looked at; no f value was.
* The published tables were read and transcribed, and the rules of section 3 were run over the typed numbers. No ORCA job at `6-31G**` or
  `6-311+G**` of any gate species has been run.

## 3. The published numbers, and the rules that decide which may be targets

Typed into `app/fukui_gate.py` and pinned by `tests/test_fukui_gate.py`, so neither can move alone.

* **`olah2002`**, Tables 1 to 3: stockholder (Hirshfeld) charges, f+ and f- for each atom at B3LYP and HF with `6-311+G**` and `6-31G**`, four
  decimals; Gaussian 98, geometries optimized at each level, the ions as single-annihilated UHF.
* **`bultinck2007`**, Table I: formaldehyde, plain Hirshfeld, `RHF/6-31G**` geometry and `UHF/6-31G**` ions: f- C 0.226, H 0.146, O 0.482; f+ C
  0.402, H 0.146, O 0.306.
* **`thanikaivelan2002`**, Table 5: formaldehyde, Hirshfeld, DMol3 BLYP/dnd (reported, section 10).

**Rule A, the sum rule.** A column of f over *all* the atoms of a molecule sums to 1. For CO, CO2, CN-, NCO- and CNO- every atom is tabulated, so
each of the 40 columns (two attacks, four models) is summed. A column more than 0.001 from 1 is a misprint and is **dropped whole**. Exactly three
are: CO2 f- at `B3LYP/6-31G**` (sums to 1.0119), CNO- f+ at `B3LYP/6-31G**` (1.0241) and NCO- f- at `HF/6-31G**` (0.9960).

**Rule B, corroboration.** A column that omits atoms (formaldehyde and acetone omit their hydrogens) cannot be summed. It is used only where a
second source agrees with every value within 0.01. Formaldehyde's carbon and oxygen agree with Bultinck's (`HF/6-31G**`) and Thanikaivelan's
(`B3LYP/6-31G**` against BLYP/dnd), by at most 0.0041 and 0.0080, so they are used. Acetone has no second source, so it gives **no number**.

**The decided numbers**, at `B3LYP/6-31G**` and `HF/6-31G**` only: **54**, which are Olah's CO 8, CO2 6, formaldehyde 8, CN- 8, NCO- 9 and CNO- 9
(48, after Rule A) and Bultinck's formaldehyde 6.

**Rule C, site statements.** Seven documented sites: CO f- on C (HCO+ is more stable than HOC+), CO2 f- on O, formaldehyde f- on O, formaldehyde f+
on C, acetone f- on O, CN- f- on C (HCN is more stable than HNC), NCO- f- on N (HNCO is more stable than HOCN by about 28.5 kcal/mol), each taken from
`olah2002`'s text and each required to be supported by the paper's own numbers at the level. A statement is **decided at a level only if the
published margin (the expected atom's value over the next tabulated atom's) is at least twice the tolerance**, because a tolerance wider than half
the margin could turn the ordering over. That gives **13** decided (statement, level) pairs and leaves one out, listed and not decided: **NCO- f- at
`HF/6-31G**` (margin 0.0198)**. Acetone's f+ is not a statement at all: Olah's own `B3LYP/6-31G**` numbers put its oxygen (0.2491) above its
carbonyl carbon (0.2388) where the text says the carbon.

## 4. Procedure

The application's own path throughout, driven by `OPENCHEM_DRIVE` (no mouse), on this machine's ORCA (`D:\ORCA\orca.exe`, 6.1.1), gas phase.
`benchmarks/fukui_gate/make_scripts.py` writes the scripts. For each of the seven species at each of the two levels:

1. Add it from its SMILES (CO `[C-]#[O+]`, CO2 `O=C=O`, formaldehyde `C=O`, acetone `CC(C)=O`, CN- `[C-]#N`, NCO- `[N-]=C=O`, CNO- `[C-]#[N+][O-]`)
   and embed 3 conformers. The panel takes the net charge from the drawn structure (checked in the plumbing run: -1 for the anions).
2. One ORCA **Geometry Optimization** at the level's method (`B3LYP 6-31G**` or `HF 6-31G**`). The optimized conformer is then the canonical one, which the
   script asserts (`canonical_method: orca_opt`, `canonical_mapped: true`).
3. One **Fukui functions (Hirshfeld)** run at the same method, on that geometry (the three states are vertical). No job starts while another runs.
4. `fukui_gate_record` writes the stored run: its four per-atom datasets, the elements it ran on, its charge, multiplicity, method, ORCA version, input
   fingerprint, and whether that fingerprint is the ORCA-optimized conformer's.

**Differences from the published calculations, disclosed and not corrected:** a different program (Gaussian 94/98 and DMol3 for the sources, ORCA here); ORCA's
B3LYP uses VWN-5 for the local part of its correlation (read from its output; Gaussian's B3LYP uses a different form, not checked here against Gaussian's own
documentation); the ions are UKS/UHF without the annihilation the source applied; ORCA's Hirshfeld promolecule is ORCA's own; and the geometries are ORCA's
optimized ones at each level, as the source optimized at each.

## 5. What is recorded

Into `benchmarks/fukui_gate/artifacts/`: `floor_records.json` and `floor.json`; `records.json` (one line per attempt of each job: its stored run's values, charge,
multiplicity, method, ORCA version, fingerprints, status and warnings); `verdict.json` (the outcome, every reason, every compared row with its published value,
measured value and signed difference, every site row); `reported_records.json` and `reported.json`. Nothing is chosen afterwards.

## 6. The noise floor, and the tolerance

**T = 0.02**, fixed here by hand and not by the floor. Its evidence is the literature's own scatter: at comparable levels the independent published values of
formaldehyde disagree by at most **0.0080** (`published_scatter`, a test pins it), and 0.02 is two and a half times that. It is also under half of every decided site
margin (section 3, Rule C).

**The floor F** is measured on **water at `B3LYP/6-31G**`, a molecule that is not in the gate**, as the largest difference of any atom's f+, f-, f0 or dual descriptor
between: the **same input twice** (`a1`, `a2`: two runs on one optimized geometry, which must carry one input fingerprint and two different run ids, or the floor is
not recorded) and the **whole chain twice** (`a1` against `b`: a second water embedded, optimized and run independently).

**The rule:** the gate can use T only if **F <= 0.005**; otherwise it is NOT EVALUABLE (an instrument noisier than a quarter of the tolerance cannot test it).
`fukui_gate_begin`, the first step of the gate script, ends the run before one job unless `floor.json` says the floor is usable. The floor is measured and committed
before the gate runs.

## 7. The verdicts

Decided by `app/fukui_gate.judge`, which is pure and tested with invented numbers. Every reason is collected; none hides another. "Within T" means
`|measured - published| <= 0.02`, with a float slack of 1e-9; a symmetric pair (CO2's two oxygens) is judged by its worse atom.

**NOT EVALUABLE** (nothing is claimed either way, and it takes precedence over everything else) when any of: the tolerance is not 0.02; no floor, or F > 0.005; an ORCA
other than 6.1.1 or none recorded; a species at a level has no run, or fewer than three attempts have failed and none completed; a run's charge is not its species' or
its multiplicity is not 1; a run did not complete; a run did not run on the ORCA-optimized geometry; a run's atoms are not its species'; a run's own f+ or f- does not sum
to 1 within 0.001 (a defect in the code, not a result about chemistry); a run's dual descriptor is not f+ - f- or its f0 is not their mean (to 1e-9); or one job has two
completed attempts (a second draw, not a repeat).

**PASS** requires every one of the 54 numbers within T, and every one of the 13 sites reproduced, and no species left uncomputed.

**PARTIAL** is every neutral species (CO, CO2, formaldehyde, acetone) reproduced, numbers and sites, and at least one **charged** species (CN-, NCO-, CNO-) not: a number
outside T, a site missed, or the species not computed.

**FAIL** is any neutral-species number outside T, any neutral site missed, or a neutral species ORCA could not compute at a gate level in three attempts. The published values
stay the published values, the measured ones are printed beside them with the signed differences, **the word "reproduces" is not used**, and T is not widened.

## 8. After each outcome

* **PASS:** the calculator ships, charged species included. `docs/explainers/reactivity.md` and the user guide say it reproduced the published Hirshfeld values within 0.02 at
  those two levels, name the commit, and keep section 1's list of what that does not say.
* **PARTIAL:** the calculator ships **for neutral species**. A **charged** species is refused, with a message that says the charged cases did not reproduce the published
  values and where the record is, in the way the dipole refuses a net-charged species. The anions are a later preregistration, if a second independent table of anion values is found.
* **FAIL:** the calculator is **not shipped as validated** ("measured, not shipped"). The pull request carries the gate record and the documentation of what was measured; the
  implementation stays on a pushed branch so it can be found and fixed under a new preregistration. **A failure is a reason to find the cause, not to retire the work:** a
  difference between programs that the published scatter did not bound, or a defect in the code, is investigated first, and either is the subject of a new preregistration;
  nothing is deleted, and the calculator is dropped only if it truly cannot be made to reproduce.
* **NOT EVALUABLE:** not a result. See section 9.

## 9. What may be repeated, and what may not

* **A job that did not finish** (ORCA crashed, a scratch-file fault, the script lost a step) **may be repeated unchanged**, up to **three attempts** in all, and every attempt is a
  line in `records.json`. A species whose three states do not complete in three attempts is **NOT COMPUTED** at that level, and counts as a failure to reproduce (section 7).
* **A job that completed is never repeated** to see whether the number moves; two completed attempts of one job leave the gate unable to decide.
* **NOT EVALUABLE may be repeated after its cause is fixed**, with the same T and the same conditions; a defect found this way is fixed in a commit that says so, and each attempt is listed.
* **PASS, PARTIAL and FAIL are final.** Nothing about T, the levels, the molecules, the published numbers or the rules is changed after a decided outcome.
* The floor is measured once.

## 10. The reported arm: run, written beside the outcome, and never decides

The same machinery writes these into `reported.json`, each row marked `decided: false`; the verdict never reads them.

* **Olah's `6-311+G**` columns** (B3LYP and HF) for the seven species. They are compared with all four published columns' values; a row whose column fails the sum rule is marked `suspect`.
  The paper's own f+ moves by up to 0.1 with that basis, which is why they do not decide.
* **Formaldehyde at the application's default level** (B3LYP/def2-SVP, whose numbers were seen first, section 2) against `thanikaivelan2002`'s Table 5, `bultinck2007`'s Table I and Olah's `B3LYP/6-31G**`.
* Not in this arm and not in this gate: the Franco-Perez (2022) supplementary table (omega-B97X-D, two decimals, a functional ORCA does not have in the same form), `tiznado2005`
  (no Hirshfeld column), and acetaldehyde and acetone in `thanikaivelan2002` (their tables do not sum or are asymmetric). Any of them can be the subject of a later preregistration.

## 11. Outcome

*(Empty at the freezing commit. The noise floor, the gate's outcome and the reported arm are appended below this rule, each with its commit, and nothing above it changes.)*

---

### 11.1 The noise floor, measured 2026-10-18 04:11 to 04:13, commit that adds this section

`benchmarks/visual/fukui_gate_floor.json`, real ORCA 6.1.1, `B3LYP 6-31G**`, gas phase, charge 0, multiplicity 1, `VERDICT PASS` of the drive (5 assertions, 0 app errors, 0 driver
failures). **Water only, a molecule that is not in the gate; no gate species has been run.** Every value is the stored run's.

| Run | Chain | Stored run | Input fingerprint | Job |
|---|---|---|---|---|
| `a1` | first water, embedded, ORCA-optimized | `66f97034` | `251508707de9` | Fukui |
| `a2` | the same water, the same optimized geometry | `86734bf1` | `251508707de9` | Fukui, again |
| `b` | a second water, embedded and ORCA-optimized independently | `27af9158` | `e45f4e2f3abb` | Fukui |

* **Same input twice** (`a1` against `a2`: one input fingerprint, two different run ids, so not a cache hit): the largest difference of any atom's f+, f-, f0 or dual descriptor is **0.0**.
* **The whole chain twice** (`a1` against `b`: a second water embedded, optimized and run independently): the largest difference is **0.0**.
* **F = 0.0.** The three runs agree to every digit the application stores. By the rule of section 6 the gate may use T = 0.02 (F is not above 0.005), and `fukui_gate_begin` checks the artifact
  before the gate script starts a job. `floor_records.json` and `floor.json` are committed with this section.

Disclosed: a molecule of three atoms is the easiest case for a repeat to agree on, and a floor of exactly zero says ORCA and the application are deterministic here, not that the
published values will be reproduced.

### 11.2 The outcome: FAIL, 2026-10-18 04:14 to 04:27, commit that adds this section

`benchmarks/visual/fukui_gate_run.json`, **the one attempt**, real ORCA 6.1.1, gas phase, tolerance **T = 0.02** (fixed in section 6 before this ran; the floor of section 11.1 was 0.0).
`fukui_gate_begin` passed. `VERDICT PASS` of the drive (17 assertions, 0 app errors, 0 driver failures; `artifacts/run.drive_report.json`); **the gate's own verdict, by
`app/fukui_gate.judge`: FAIL.** The record is `artifacts/records.json` (14 lines, one per job, all attempt 1, all completed, all on the ORCA-optimized geometry, all ORCA 6.1.1, 14 distinct
stored runs) and `artifacts/verdict.json`.

**Every rule of section 7 held except one.** Fifty-two of the 54 numbers are within T, all 13 site statements are reproduced (the anions' included), every run's own sum rule and
identities held, and no species was left uncomputed. The two that are not within T are one quantity:

| Quantity | Published (`olah2002`) | Measured | Signed difference | Within T = 0.02 |
|---|---|---|---|---|
| CO, carbon, f-, `HF/6-31G**` | 0.6931 | 0.6717 | **-0.0214** | **no** |
| CO, oxygen, f-, `HF/6-31G**` | 0.3069 | 0.3283 | **+0.0214** | **no** |

CO is a neutral species, so by section 7 the outcome is **FAIL** and not PARTIAL. The two rows are the same difference, because a column of f sums to one. T is not widened, the word "reproduces" is
not used of this gate, and the gate is not re-run: a decided outcome is final (section 9).

For the record, all 54 differences (published against measured, in f units): median 0.0034, mean 0.0045, 50 within 0.01 and 52 within 0.02. The largest after the two above are CN- at
`HF/6-31G**` (+0.0101 on N, -0.0101 on C), CNO- N f- at `HF/6-31G**` (+0.0098) and CNO- N f+ (+0.0068), then CO2 C f+ at `B3LYP/6-31G**` (-0.0066). The largest difference by species and level:

| Species | `B3LYP/6-31G**` | `HF/6-31G**` |
|---|---|---|
| CO | 0.0058 | **0.0214** |
| CO2 | 0.0066 | 0.0060 |
| formaldehyde | 0.0027 | 0.0042 |
| CN- | 0.0043 | 0.0101 |
| NCO- | 0.0054 | 0.0050 |
| CNO- | 0.0062 | 0.0098 |

**What this says, and does not.** At `B3LYP/6-31G**` every one of the 23 decided numbers is within 0.0066 of the published value, and at `HF/6-31G**` 29 of the 31 are within 0.0101 (the other two are CO's f-). The calculator
did not reproduce the published value of one quantity by 0.0014 more than the tolerance allowed. It does not say the calculator is wrong in general, and it does not say it is right: the verdict is
as the rule gave it.

### 11.3 After the outcome: a diagnostic, which is not the gate and cannot change it

`post_gate_diagnostic.py`, standalone ORCA in fresh directories, run after section 11.2 existed, on CO at HF/6-31G**. The question was why one quantity is 0.0214 from the published value.
The sources' ions were **single-annihilated** UHF (`olah2002`); ORCA's UHF is not annihilated.

| | f- on C | f- on O | `<S^2>` of the cation |
|---|---|---|---|
| ORCA, UHF cation (what the application computes) | 0.6717 | 0.3283 | **0.967** (a pure doublet is 0.75) |
| ORCA, ROHF cation (no spin contamination) | 0.7102 | 0.2898 | |
| Published (annihilated UHF) | 0.6931 | 0.3069 | |

The gate's number (0.6717) is the UHF one, to the digit. The unrestricted cation of CO at HF is heavily spin-contaminated, and the published value lies between the contaminated
and the uncontaminated ones, as a partially annihilated density would. That is a measured cause for the one failing number, and it is a **difference of method**, not a defect in the arithmetic.
Whether the other HF cations are contaminated was not measured: CN- at HF has the next largest difference (0.0101), and its cation is the CN radical, a doublet. A new preregistration may
build on this; this one does not. *(Qualified in 11.6.3: "a measured cause" overstated it. Spin contamination is a candidate for this one number and not an established cause.)*

### 11.4 The reported arm, 2026-10-18: measured twice, decides nothing

`benchmarks/visual/fukui_gate_reported.json`, real ORCA 6.1.1, gas phase. Every row is marked `decided: false` and the verdict never reads them (section 10); the tolerance of 0.02 is shown beside the rows so
they can be read, not to judge them. 50 rows (*corrected, 11.6.1: 46 as first written*) from 7 species at two diffuse levels plus formaldehyde at the application's default level (`artifacts/reported.json`, `artifacts/reported_records.json`).

**The arm was run twice, and the two runs agree to every stored digit.** The first run (04:30 to 04:45) ended with the drive's own `VERDICT FAIL`, and not for the numbers: seven of its 14 diffuse-level jobs
were *refused by the application* (below), the refusal is logged as an error, and the script had not declared those errors as expected. The script (`make_scripts.py`, the reported arm only) now declares
`state's charges sum to` as expected, with a comment saying why, and the arm was run again from scratch (04:47 to 05:01): `VERDICT PASS` (18 assertions, 0 unexpected app errors, 0 driver failures;
`artifacts/reported.drive_report.json`). The largest difference between the two runs' measured values is **0.0**, both refuse the same seven jobs for the same sums, and both give the same rows within 0.02 (31 of 46 as first written, 37 of 50 as corrected in 11.6.1).
The first run's drive report is kept as `artifacts/reported.first_run.drive_report.json`. Nothing about the decided gate (sections 7 and 11.2) changes.

**Rows within 0.02, by level and quantity:**

| Level | f+ | f- | Notes |
|---|---|---|---|
| `B3LYP/6-311+G**` (Olah) | 4 of 10 (median difference 0.096, largest 0.327) | 10 of 10 (median 0.004, largest 0.008) | 4 of 7 species ran (*corrected, 11.6.1*) |
| `HF/6-311+G**` (Olah) | 2 of 7 (median 0.197, largest 0.278) | 7 of 7 (median 0.007, largest 0.012) | 3 of 7 species ran (*corrected, 11.6.1*) |
| `B3LYP/def2-SVP`, formaldehyde (Olah B3LYP/6-31G**, Thanikaivelan Table 5, Bultinck Table I) | 8 of 8 (median 0.007, largest 0.012) | 6 of 8 (median 0.005, largest 0.056) | the application's default level |

**Seven of the 14 diffuse-level jobs were refused, all in the anion state**, by the rule that a state's Hirshfeld charges must sum to its charge to 0.01 (`chem/fukui.py`). The refusal is the application doing
what it was built to do: a table that does not sum to the state's charge is not that state's partition. Between the two runs the sums did not move.

| Species | Level | Anion's charge | Charges sum to | Short by |
|---|---|---|---|---|
| CO | `B3LYP/6-311+G**` | -1 | -0.986 | 0.014 |
| CO2 | `B3LYP/6-311+G**` | -1 | -0.927 | 0.073 |
| NCO- | `B3LYP/6-311+G**` | -2 | -1.990 | 0.010 |
| CO | `HF/6-311+G**` | -1 | -0.984 | 0.016 |
| CO2 | `HF/6-311+G**` | -1 | -0.977 | 0.023 |
| NCO- | `HF/6-311+G**` | -2 | -1.983 | 0.017 |
| CNO- | `HF/6-311+G**` | -2 | -1.986 | 0.014 |

H2CO, acetone and CN- ran at both levels, and CNO- at `B3LYP/6-311+G**`. The sums were printed to three decimals, so 0.010 is the shortfall of a sum that was refused, not a threshold.

**What this shows, and what it does not.**

* With diffuse functions, **f+ is the quantity that departs from the published values** (acetone's f+ at `HF/6-311+G**` is 0.245 on carbon against 0.037 published, CN-'s at `B3LYP/6-311+G**` is 0.878 on carbon against 0.636),
  and f- stays near them in every row (*corrected, 11.6.1: first written "except in acetone", which was the comparison error*; all 17 rows are within 0.012). This is the other side of what the exploration measured (`exploration.md`: Hirshfeld's own f+ moved by at most 0.023 per atom between
  def2-SVP and def2-SVPD on three molecules), and it **retires a sentence this work had been carrying, unreleased**: the unbound-anion caveat ended "Adding diffuse functions is the check", and the explainer said to check f+ with a basis set
  that has them. Both are replaced; diffuse functions are not a cure, and with them seven of the 14 jobs, covering four of the seven species, are refused by the rule below.
* The cause of the disagreement was **not diagnosed here** (11.5 and 11.6 test the integration grid, spin, the SCF solution and the starting embedding afterwards). The unbound anion's extra electron sits in the diffuse functions, far from the nuclei, and a Hirshfeld integral on a grid can miss it; the published program, its geometry
  (the application runs the ions at the neutral geometry ORCA optimized at def2-SVP; whether a published table used another is not known here) and the spin treatment of section 11.3 are all candidates. None was tested. A cause can be put to the test by a
  new preregistration; this section only records the measurement.
* The refusal threshold of 0.01 was fixed before any job ran (`chem/fukui.py`, section 7) and is **not changed here**: loosening it after seeing seven refusals would choose the threshold by its result. A rule loosened to 0.02 would admit five of the seven, and the values it admitted would need the same
  scrutiny as the f+ rows above.
* Formaldehyde at the default level reproduces Olah's and Thanikaivelan's published values to 0.012 (all 10 rows) and Bultinck's Table I to 0.056, two rows outside 0.02 (O f- -0.056, H f- +0.027). Bultinck's column is UHF/6-31G**
  and this is B3LYP/def2-SVP, and the same six numbers were reproduced within 0.02 at `HF/6-31G**` in the decided arm; nothing here says which level the paper's table belongs to better.

### 11.5 After 11.4: a probe of one candidate cause, which is not the gate and changes nothing

`grid_probe.py`, standalone ORCA 6.1.1 in fresh directories, **one molecule**: the anion of CO2 (charge -1, doublet) at an idealized linear geometry (C=O 1.16 A), `6-311+G**`, the case the application refused at both
levels. The default-grid sums land within 0.002 of the application's own (-0.9271 against -0.927 at B3LYP, -0.9785 against -0.977 at HF, which used its ORCA-optimized geometry). Section 11.4 said none of the candidate causes
of the refusals had been tested; this tests one, the integration grid, and only on this molecule.

| ORCA setting | B3LYP: charges sum to | short by | HF: charges sum to | short by |
|---|---|---|---|---|
| default | -0.9271 | 0.0729 | -0.9785 | 0.0215 |
| `DefGrid3` | -0.9572 | 0.0428 | -0.9909 | 0.0091 |
| `%method IntAcc 6.0` | -0.9793 | 0.0207 | -0.9973 | 0.0027 |
| `%method AngularGrid 7, IntAcc 6.0` | -0.9811 | 0.0189 | -0.9978 | 0.0022 |

**What it shows.** The shortfall is in large part the integration of the diffuse electron on the grid: it shrinks at every refinement, at both methods. At HF the SCF energy is unchanged by the grid to 1e-9 Eh (there the grid serves the Hirshfeld
integral only), the sum is inside the 0.01 rule at `DefGrid3` and 0.003 short at `IntAcc 6.0`. At B3LYP the finest grid tried is still 0.019 short and the SCF energy moves by 0.0037 Eh (-188.4981 to -188.5019), so a finer grid alone does
not close it there. That makes part of the refusals a limitation of ORCA's default grid for a diffuse unbound electron and not of the Hirshfeld arithmetic or the sum rule.

**What it does not show.** That the f+ values at `6-311+G**` would then match the published ones (not run: the refusal and the f+ disagreement are different quantities, and the f+ rows of 11.4 that were computed did sum correctly);
that the other six refused jobs behave as CO2 does (one molecule); or what the neutral and the cation states' own shortfalls are. The application does **not** use a finer grid. A different numerical setting is a different calculation from
the one that was gated, so whether it should become the default, and at which setting, is for a new preregistration and this probe is not one. Two earlier spellings of the keyword (`Grid7 NoFinalGrid`, and `IntAcc 6` on the simple input
line) were rejected by ORCA as unrecognized input, produced no output, and say nothing.

### 11.6 After 11.5: a correction to 11.4, and four measurements, none of which is the gate

Standalone ORCA 6.1.1 in fresh directories (or saved records re-read), after the outcome, deciding nothing, and changing neither the calculation nor the verdict. Scripts and summaries: `grid_sweep.py`,
`rohf_cation_sweep.py`, `anion_guess_probe.py`, `seed_sweep.py` and their JSON in `artifacts/`. Each species is ORCA-optimized at its own level from an RDKit embedding and then given the application's own
three-job Fukui input, as the gate's blocks do.

#### 11.6.1 A correction to 11.4 (an error of mine, found by reading the per-atom values of the acetone runs)

`MeasuredRun.of_element` matched the element symbol. Acetone has three carbons and the published table two labels for them (the carbonyl carbon, "C", and the two methyl carbons, "Cm"), so the carbonyl row was compared with
whichever of the three carbons was farthest from the published value, usually a methyl carbon, and the "Cm" rows were compared with nothing. Effect on the reported arm: three rows change (acetone C: B3LYP f+ 0.1063 to 0.0293,
B3LYP f- 0.0811 to 0.1152, HF f- 0.0641 to 0.1216, each now within 0.02) and four are added (Cm), so the arm has **50 rows, 37 within 0.02** (first written: 31 of 46). **The decided gate is unaffected**: no acetone number is
decided (section 7), every decided element has one atom or equivalent atoms, and `judge_records` on the committed `records.json` returns a verdict **identical** to the committed `verdict.json` (FAIL, 54 rows, 13 site rows).
Fix: `Species.labels` and `MeasuredRun.labels()`; five new tests, four mutants killed, a test that every published number names atoms its species has (the "Cm" rows had been skipped without a word). The reported artifact was regenerated from the
saved `reported_records.json`; no ORCA job was run again. What 11.4 got wrong is marked where it stands. In short: at the diffuse levels **f- agrees with the published value in all 17 rows (largest difference 0.012)**; f+ does not.

#### 11.6.2 The integration grid, for all seven species (`grid_sweep.py`)

Each species at the four levels of the published table, the three-job input at ORCA's default grid and with `%method IntAcc 6.0` in every job's header. The charge-sum rule is not applied here, so a state the application
would refuse is still read; the comparison with the published numbers is `fukui_gate.compare` with the corrected labels, undecided.

* **At the two 6-31G** levels the gate decided on, the finer grid changes no value**: the largest change of any atom's f+ or f- is 0.0000 on all 14 jobs, and no state is short of its charge. The decided numbers do not depend on the grid.
* **At 6-311+G** the grid is the whole of the refusals.** The anion's charge sum was short by up to 0.0226 at the default grid and by 0.0050 or less on the finer one for all 14 jobs; no neutral or cation state was off by more than 0.0002 at either.
  The finer grid moved a species' largest f by 0.0002 to 0.0248.

  | Level | CO | CO2 | H2CO | acetone | CN- | NCO- | CNO- |
  |---|---|---|---|---|---|---|---|
  | `B3LYP/6-311+G**`, anion short by, default grid | 0.0142 | 0.0197 | 0.0061 | -0.0004 | -0.0009 | 0.0100 | 0.0179 |
  | on the finer grid | 0.0045 | 0.0028 | 0.0019 | 0.0006 | -0.0012 | -0.0009 | 0.0022 |
  | `HF/6-311+G**`, default grid | 0.0164 | 0.0226 | 0.0062 | 0.0003 | -0.0031 | 0.0171 | 0.0141 |
  | on the finer grid | 0.0050 | 0.0028 | 0.0019 | 0.0001 | -0.0045 | 0.0012 | 0.0013 |

  (The application's own sums for the seven refused jobs are in 11.4; CO2 at B3LYP was 0.073 short there and 0.0197 here; the anion of CO2 at `B3LYP/6-311+G**` has two solutions depending on the starting embedding (11.6.5), which is the likely reason and was not tested for that run.)
* **It does not bring f+ to the published values.** At 6-311+G** f+ is within 0.02 for 5 of 17 rows at the default grid and 4 of 17 on the finer one at B3LYP, and 3 of 17 and 3 of 17 at HF; f- is within for 17 and 17 of 17 at B3LYP and
  15 and 15 of 17 at HF (CO's, 0.0205 from the published value). The refusals are the grid. The f+ disagreement is something else.

#### 11.6.3 Spin (`rohf_cation_sweep.py`)

S squared of every cation and anion of the 28 species and levels, read from the sweep's outputs: **every B3LYP ion is at most 0.78** (CO2's cation) and **no anion is above 0.77**. At HF the cations of CO (0.967), CN- (1.121), CO2 (0.934) and NCO- (0.885) are
contaminated and those of H2CO (0.784), acetone (0.773) and CNO- (0.788) are not; at 6-311+G** each is within 0.02 of its 6-31G** value. The cation of CN- is the most contaminated of all and its f- is 0.0101 from the published value; CO's is 0.0214.
With the cation as a restricted open-shell (ROHF) doublet and the anion unchanged, at HF/6-31G** against the decided numbers: CO's f- goes from 0.0214 to **0.0171** from the published value (inside 0.02), CN-'s from 0.0101 to 0.0050,
CO2's from 0.0060 to 0.0066, NCO-'s stays 0.0050, H2CO's 0.0042. **The ROHF cation of CNO- is another electronic state** (f- on oxygen 1.331, a value above 1), so 28 of the 31 decided numbers are within 0.02 where the unrestricted ones give 29.
What stands: spin contamination is **a candidate** for CO's miss, because its ROHF value moves toward the published one and so does CN-'s, and it is **not an established cause**, because CO2 and NCO- are contaminated and indifferent, and ROHF
is not a drop-in replacement (it lands on another state for CNO-). The sentence of 11.3 that called it a measured cause is qualified there.

#### 11.6.4 The anion's SCF solution (`anion_guess_probe.py`)

The same anion, standalone, at the sweep's geometry and with the application's keywords, run from five starts: ORCA's default guess, Hueckel, PAtom, HCore and the UHF stability analysis with restart. Inside the application's compound input ORCA does not use the default
guess for the cation and anion: it reads **the cation's orbitals as the anion's guess** ("INITIAL GUESS: MOREAD" from `job_job2.gbw`), so the anion's solution there depends on the path.

* **At the two 6-31G** levels the default solution is the lowest found in all 14 jobs**: no start found anything lower than the default by more than 0.005 eV (the largest was 0.004 eV), and the starts that reached its energy agree on every heavy atom's f+ to 0.0004.
  (HCore sometimes ends in a state higher by up to 7.3 eV, which is not a solution anyone wants; the stability analysis stopped with an error for CN- at both levels and NCO- at HF.)
* **At 6-311+G** there is more than one solution.** Of the six cases probed, three had a solution **lower** than the default one:

  | Case | default solution: f+ (heavy atoms) | lowest found | f+ at the lowest | published f+ (Olah) |
  |---|---|---|---|---|
  | acetone `HF/6-311+G**` | carbonyl C 0.245, methyl C 0.054, O 0.251 | HCore, **1.013 eV lower** | carbonyl C 0.032, methyl C 0.103, O 0.058 | 0.037, 0.104, 0.055 |
  | CN- `HF/6-311+G**` | C 0.872, N 0.128 | Hueckel, HCore, stability, 0.681 eV lower | C 0.592, N 0.411 | C 0.867, N 0.133 |
  | CN- `B3LYP/6-311+G**` | C 0.878, N 0.122 | all four others, 0.615 eV lower | C 0.573, N 0.431 | C 0.636, N 0.364 |
  | H2CO `B3LYP/6-311+G**` | C 0.438, O 0.220 | stability, 0.017 eV lower | C 0.428, O 0.194 | C 0.428, O 0.339 |
  | acetone `B3LYP/6-311+G**` | carbonyl C 0.030, methyl C 0.106, O 0.057 | none | | 0.047, 0.103, 0.060 |
  | CNO- `B3LYP/6-311+G**` | C 0.632, N 0.156, O 0.194 | none lower (stability job failed) | | 0.520, 0.139, 0.342 |

  f+ differs by up to **0.31** between the solutions of one anion (CN- at B3LYP). **The published values do not pick a solution**: acetone's published f+ at HF is the lower one (within 0.005 on all three atoms) and CN-'s at HF is the higher one (within 0.005).
  A published f+ at a basis set with diffuse functions is the value of whichever solution the published program reached, which is not a single well-defined target.

#### 11.6.5 Reproducibility across starting embeddings (`seed_sweep.py`)

Every species at the four levels, three RDKit embedding seeds (7, 11, 23), each ORCA-optimized and given the three-job input at the default grid: the largest difference between the seeds in any heavy atom's f+ and f-. (Hydrogens are left out: the equivalent
hydrogens of a methyl group are numbered by position, which differs between embeddings, and acetone's all-atom spread of 0.02 to 0.07 is that and not a result. The optimized energies of the three seeds agree to 0.0004 eV everywhere, so they are one minimum.)

* **At the two 6-31G** levels all 14 jobs reproduce to 0.0004 or better** (0.0001 typical), at both methods. The decided numbers are not a property of one embedding, and the grid sweep's own embeddings (11.6.2) reproduce the gate's result the same way: of Olah's 48 decided numbers 46 are within 0.02, and the two that are not are CO's f- at `HF/6-31G**`, 0.0214 from the published value, as in 11.2.
* **At 6-311+G** 12 of 14 reproduce** (largest difference 0.0066, acetone at B3LYP, whose two equivalent methyl carbons exchange). **Two do not**: CO2 and CNO- at `B3LYP/6-311+G**`, where two seeds give one anion and the third another:
  f+ on CO2's carbon 0.591, 0.712, 0.591 (spread 0.121) and on CNO-'s carbon 0.632, 0.846, 0.632 (spread 0.214), where f- agrees to 0.0001. **The application's own run of CNO- (11.4) is the 0.846 one.** f+ at a basis set with diffuse functions is not
  a reproducible number of this calculation.

#### 11.6.6 What this changes, and what it does not

* **Not changed**: the calculation, the 0.01 rule, the tolerance, the verdict of 11.2 (FAIL, by 0.0014 on CO's f-), and the decision to ship as experimental and not validated.
* **Changed, text only**: the refusal of a state that is a few hundredths of an electron short now says it is the numerical integration and what helps (it used to say "the table read is not that state's", which was wrong for all seven refusals); the
  unbound-anion caveat says that with diffuse functions the anion has more than one SCF solution; the explainer, the guide and the changelog say that spin contamination is a candidate and not the cause, and that f+ with diffuse functions is not reproducible.
* **For a new preregistration, not done here**: a finer integration grid by default (it removes the refusals and moves no 6-31G** value); the lowest of several anion starts with a flag when they differ (the gated levels would not change); and a validation against published
  values at a basis set **without** diffuse functions, which needs tables other than Olah's, because Olah's diffuse columns are themselves the value of one arbitrary solution (11.6.4). The gate of this document cannot be re-run, and these would not be it.

### 11.7 What was done about 11.6.6 afterwards (appended 2026-10-18; nothing above this line changes)

The three items 11.6.6 left "for a new preregistration" were built as **Fukui v2**, and the calculation this document gated is no longer the one in the application: a finer integration grid (`IntAcc 6.0`) is now used in every job, an anionic state at a basis set with diffuse functions is started from three guesses and the lowest solution is read, every job states `HFTyp RHF` or `UHF`, and **a species with a negative charge is given f- alone** (its N+1 state is a dianion), so the f+ of CN-, NCO- and CNO- that this gate compared is no longer produced. The statements above that the application "does not use a finer grid" are true of the calculation as it was and are kept as written. What v2 is, what each change rests on and what it costs are in `benchmarks/fukui_gate_2/DESIGN.md`; the validation against tables other than Olah's that 11.6.6 asked for is `benchmarks/fukui_gate_2/PREREGISTRATION.md` (written, not yet frozen or run). The verdict of 11.2 is untouched.
