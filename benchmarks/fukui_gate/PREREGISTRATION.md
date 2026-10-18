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
build on this; this one does not.
