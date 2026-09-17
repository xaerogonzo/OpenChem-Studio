# Schindler 2021 SQE: source reproduction, then a held-out drug-like benchmark

**Pre-registration, committed before any charge is computed.** The follow-up to TRIAGE §5.2 G2-1.
Decided by Alex, 2026-09-17: pre-register a drug-like study starting with Schindler, and install
ChargeFW2 as a second implementation.

Nothing here ships. Shipping would be a separate `src` pre-registration and Alex's decision. Results
are appended below the line at the end and never edited into the sections above it. A registered
rule that turns out wrong is amended openly, with its commit, and a failed gate stays failed.

## 0. The claims, kept apart

| part | claim kind | question |
|---|---|---|
| A | instrument | Do our SQE and EEM equal the frozen equations and the authors' own implementation? |
| B | **G1, source reproduction** | Do the published CCD_gen SQE parameters, on the deposited structures, give the paper's own printed metrics? |
| C | **G2, held-out benchmark** | On drug-like molecules those parameters never saw, how good are the charges, against a named oracle chosen here? |

**Out of scope, stated:** charges on conformers OpenChem generates. Every number here uses the
*deposited* geometries, because the reference charges belong to them. The application path is a
different question, for a later registration.

## 1. Sources and artifacts, pinned

- **Paper:** `schindler2021`, with `schindler2021_correction`. Sci Downloads holds `schindler2021.pdf`,
  `schindler2021_correction.pdf` and the supplements in `schindler2021_si/` (SHA-256):
  - S1 methods `d96318a3493fbb0f54ad3e95bdd0d3b63725640acc0b2d023a0b7a5aad04f37b`
  - S2 split `d4f207bd46319fd47d581e0e2de00c78d018b182431ab23f16df95654e7ff1a2`
  - S3 SDF `eb9b4d8bed0b740414a7f74bf0bd96de354c5bd052206d07274beaadc0d81cd3`
  - S4 QM charges `fa3fac1e345677c7d7a9772058bae606a8cfbf43bb661618d20c36b778ecb232`
  - S5 `66ce05957ec810589332d600a1b572c6df06ab7996db0b92dcc82f70346a6bcb`
  - S6 metrics `65bb8afc454af12ce417aeb59410e88b4db80005b46dc7b7902befcb483570ac`
  - S7 parameters `5262e40954ac49629db68a4943086d802ea66ac0deb1b7b352665c2be929750b`
- **Populations (counted from S2 and S3; no charges computed):**
  - **CCD_gen:** 4,443 molecules; 3,554 training and 889 test.
  - **DTP_small:** 1,956 molecules; 1,564 training and 392 test.
  - **288 CCD_gen molecules carry an `M  CHG` line.**
  - **CCD_gen bonds:** orders 1, 2 and 3 only (Kekulé).
- **Parameters:** `parameters/SQE_CCD_gen_parameters.json` from S7 (`7d86d0cfd155b68accdb530d102e97711de1a5efec96c20b63fb00a20a088be7`): 15 atom types (HBO) with χ, η and width; 66 bond types with κ.
- **Reference charges:** B3LYP/6-311G NPA, from Gaussian 09, for CCD_gen and DTP_small (paper, "Reference charges").
- **The paper's metrics, read before registering (p 3 and S6):**
  - **Definitions:** R² is the squared Pearson coefficient and RMSD the root mean square deviation. Both are computed **per molecule and averaged over the set**. RMSDat is **the largest per-atom-type RMSD**.
  - **Oracle rows:** S6 Table 2 (CCD_gen), SQE, **seed 5**. Training: R² 0.9953, RMSD 0.0282, RMSDat 0.0414. Test: R² 0.9952, RMSD 0.0279, RMSDat 0.0481.
  - **Why seed 5:** its training row is identical to main-text Table 3's SQE CCD_gen row, the published set.
  - **Not an oracle:** main-text Table 2's "optGM" row (0.9950 / 0.0292 / 0.0406) belongs to the optimiser comparison, a different run.
- **Second implementation:** ChargeFW2 3.0.0 at commit `19e73b248cc3983853892d3b42ca0e967a09954a`.
  - Built in WSL (Ubuntu 24.04) with conda-forge GCC, Eigen 3.4, gemmi 0.7.4 and Boost; `-DCHARGEFW2_PORTABLE=ON`.
  - Its CCD_gen JSON (`ca68bc7e2bff6753a23f831c588947c219021ccd31082c696eb0ea6e80eb1134`) equals S7 to 4 decimals, all 15 atom and 66 bond rows (TRIAGE §5.1).
  - **Which parameter file it runs is decided below (A.4), not assumed.**

## 2. The model, frozen

From the paper's equations (p 2) and the authors' implementation (`src/methods/sqe.cpp` at the pinned commit):

- **Split charges and the system.** q = Tᵀ q_sp, with (T H Tᵀ + diag κ) q_sp = T c.
- **T,** the bond-atom incidence matrix: +1 on a bond's first atom, −1 on its second, bonds in SDF order.
- **H, the hardness matrix.** H_ii = η_i; H_ij = erf(r_ij / d0_ij) / r_ij, with d0_ij = √(2 w_i² + 2 w_j²) and r in Å.
  The sign of w does not matter.
- **κ** is looked up by (type_i, type_j, bond order), unordered in the atom pair.
- **Types:** element plus the atom's highest bond order over its bonds, read from the SDF bond block
  (`structures/molecule.cpp`). A missing atom or bond type means **refused**. ChargeFW2's
  `--permissive-types` is never used.
- **Total charge.** q = Tᵀ q_sp sums to zero by construction. So on the 288 charged molecules, SQE's
  Σq = 0 while the reference sums to the formal charge. The paper says so itself ("no way of setting
  the total charge"). **Nothing corrects for it.** It is reported as a stratum (B.3).
- **The right-hand side sign, a registered reading question.** The paper prints **c = +χ**; the code
  writes **b = −χ**. Charges are linear in c, so the two readings give charges of opposite sign.
  - Both readings run: **R_plus** (c = χ) and **R_minus** (c = −χ).
  - The paper's metrics decide which one is the model, as the ångström reading did for Ionescu.
  - Nothing is chosen in advance.

**The Geidl 2015 EEM, for part C,** frozen from `src/methods/eem.cpp`:
- **System:** B_i on the diagonal; κ / r_ij off it (r in Å); b_i = −A_i; one bordered row and column of
  ones; right-hand side Q = Σ formal charges.
- **Parameters:** the B3LYP/6-311G/NPA set (`geidl2015` Additional file 2), κ 0.2509, HBO types.
- **Scope of the reading:** only ChargeFW2's "full" mode, which applies below 20,000 atoms and so
  covers every molecule here.

## 3. Part A: the instrument, before any population run

A committed script, `benchmarks/charges/models/schindler_sqe_check.py`, plus
`tests/test_schindler_sqe_instrument.py`.

1. **Parsing fails closed.** Every SDF record must be matched to its `.chg` record by name, with the
   same atom count and element sequence, and every split ID must resolve to exactly one molecule.
   A mismatch stops the run and names the molecule; nothing is skipped silently.
2. **Synthetic tests, with the equations re-transcribed by hand in the test.**
   - A two-atom molecule solved on paper: q₁ = c-term / (η₁ + η₂ − 2H₁₂ + κ).
   - Σq = 0 for SQE.
   - Invariance under renumbering the atoms (charges follow the atoms).
   - The T orientation cancels.
   - HBO typing on a hand-built molecule with a double and a triple bond.
3. **Registered mutations, each expected red:**
   - width not squared;
   - erf dropped (bare 1/r);
   - κ dropped;
   - the T sign convention changed in only one place;
   - typing by the *lowest* bond order;
   - bond κ looked up in only one atom order;
   - the EEM total charge ignored.
4. **Which parameter file runs, checked here.** ChargeFW2's CCD_gen JSON and S7's JSON must give
   identical types and charges to ≤ 1e-6 e on 20 molecules (seed 20260917). If they do not, S7's
   published file is authoritative, and ChargeFW2 is given S7's values through `--par-file` in its
   schema.

## 4. Part B: G1 source reproduction

1. **B.1 Cross-implementation gate.**
   - **Run:** our SQE under both readings, and ChargeFW2 `--method sqe` with the CCD_gen parameters,
     on all 4,443 molecules.
   - **Report:** per reading, the fraction of molecules where both compute and every atom agrees
     within **1e-6 e**.
   - **The reading matching ChargeFW2** is ChargeFW2's convention, recorded as a fact about the code.
     It does not decide the model; B.2 does.
   - **Molecules only one implementation refuses** are listed by name.
2. **B.2 Source reproduction gate.** Recompute the six S6 seed-5 values under each reading, with the
   paper's definitions: per-molecule R² and RMSD averaged over the split, and RMSDat as the largest
   per-type RMSD over every atom in the split.
   - **REPRODUCED:** all six round to the printed 4 decimals (|Δ| ≤ 5e-5, plus 1e-6 solver noise)
     under exactly one reading.
   - **PARTIAL:** at least one but not all six do.
   - **NOT-REPRODUCED:** none do.
   - **The reading that reproduces is the model.** If both or neither do, the reading is recorded as
     undetermined, and part C runs under ChargeFW2's convention, labelled so.
   - **RMSDat's pooling is a second reading question.** The paper does not say how atoms are pooled
     within a type. The primary rule pools every atom of the type across the split. A per-molecule
     mean within each type is computed as a sensitivity arm and is never used to rescue a miss.
3. **B.3 Strata, reported and not gated.**
   - The 288 charged molecules against the rest.
   - Per atom type.
   - **Conditioning:** the smallest eigenvalue of (T H Tᵀ + diag κ) per molecule, the count of molecules
     where it is ≤ 0 (the system is not positive definite), and the distribution of condition numbers.
     This is TRIAGE §5.1's open item: 9 X–H κ near −33 against a hydrogen hardness of 36.3.

## 5. Part C: G2 held-out benchmark

1. **Oracle, chosen now:** the deposited B3LYP/6-311G NPA charges. Chosen because it is the target
   both candidates were fitted to, which makes the comparison like-for-like. Other targets
   (experimental dipoles, ESP) are **not** part of this registration.
2. **Populations, in order of weight.**
   - **C-primary, cross-dataset:** DTP_small, all 1,956 molecules (a different source database, NCI
     against wwPDB CCD).
     - **Exclusion:** any molecule whose standard InChIKey (RDKit, computed from the deposited SDF)
       equals that of a CCD_gen *training* molecule. Count reported.
   - **C-secondary, in-distribution held out:** the CCD_gen test split (889).
3. **Models.**
   - **Candidates:**
     - Schindler SQE CCD_gen, under the reading B.2 identified;
     - Geidl 2015 EEM B3LYP/6-311G/NPA.
   - **Geidl leakage:** 44 DTP_small NSC ids are in Geidl's 4,475-molecule training list (counted
     from S2 and `geidl2015` Additional file 1). They are **excluded from Geidl's C-primary
     evaluation**; the SQE figure is reported both with and without them.
   - **Geidl on CCD_gen:** overlap with its training set **cannot be measured** from the deposited
     data (the Geidl training set is NSC ids without structures). So its C-secondary figure is
     labelled "overlap unmeasured".
   - **Context only, never gated:**
     - the shipped Bultinck Part I EEM (Mulliken-fitted, so a different target, labelled);
     - RDKit Gasteiger.
4. **Metrics, per model and population, on the covered molecules.**
   - **Coverage:** covered molecules over the population.
   - **The paper's three metrics.**
   - **Pooled per-atom RMSD.**
   - **The silent-error molecule rate,** with Ionescu §9.3's definitions unchanged: a sign error is
     opposite signs with |q_ref| ≥ 0.10 e; a magnitude error is |Δq| ≥ 0.50 e.
   - **Molecules whose matrix is not positive definite,** for SQE the split matrix and for EEM its
     charge block.
5. **G2 verdict, per candidate, on C-primary only.**
   - **G2-CANDIDATE only if all four hold:**
     1. coverage ≥ 90 %;
     2. the per-molecule average RMSD ≤ **0.05 e**;
     3. the silent-error molecule rate ≤ **10 %**;
     4. the matrix is not positive definite on ≤ **1 %** of covered molecules.
   - **Otherwise NOT-G2-CANDIDATE,** naming every failed criterion.
   - **How the thresholds were chosen:** set now as priors, and not fitted.
     - 0.05 e is under twice the paper's own in-distribution test RMSD (0.0279).
     - 10 % is the CONFINED boundary already used for Ionescu.
6. **What it licenses:** a G2-CANDIDATE verdict makes a model eligible for a `src` pre-registration,
   which remains Alex's decision. A comparison between the two candidates is **descriptive**; no
   "better model" is declared from one population.

## 6. Order of work, and how it is committed

1. **Instrument:** implemented, synthetic tests and mutations; committed.
2. **A.4:** which parameter file runs.
3. **B:** B.1 and B.2 run, with the results appended below.
4. **C:** runs only after B is committed; its results are appended below.

**Every run** records its exit code, the tool versions, and a hash of each result file.

---

## Results

### A. Instrument (2026-09-17, commit 43e3c87)

- 11 tests pass, including every deposited CCD_gen and DTP_small molecule pairing with its charges and
  the split resolving exactly.
- **All 7 registered mutations are red.**

**Four plumbing fixes before A.4 produced any number.** None changes a registered rule; each is recorded
so the run is reproducible.
1. **ChargeFW2's command line prints charges to 5 decimals** (`formats/txt.cpp`, `{:.5f}`), which
   cannot test a 1e-6 gate. The runs use its own Python bindings (`chargefw2.calculate_charges`), which
   return the solver's doubles.
2. **The bindings' `Molecules` defaults to `permissive_types=True`.** It is passed as `False`, as
   section 2 requires.
3. **A parameter file is named without `.json`,** and `CHARGEFW2_INSTALL_DIR` must be set, as in its
   Dockerfile.
4. **Its parser requires `metadata.notes`,** so the converted S7 file carries one.

### A.4. Which parameter file runs: S7's values (2026-09-17)

`schindler_sqe_results/a4.json` (sha256 `6656553e8e749473989319a4e7d1f0e07e2ec2ac265ec2f81ab1cfaf33f229bb`).
- **20 molecules, seed 20260917,** all computed by both files. ChargeFW2's own 4-decimal CCD_gen file and
  S7's full-precision values differ by up to **2.65e-4 e**, against the 1e-6 gate.
- **As registered, S7 is authoritative:** part B runs ChargeFW2 with S7's values through `--par-file`.
- **As expected:** ChargeFW2 rounds κ values near −33 to 4 decimals.

### B. Source reproduction (2026-09-17): PARTIAL, reading undetermined

`schindler_sqe_results/b.json` (sha256 `7046c7c5460f0166e31d9113f8762305df99bfc3287a296816abf80b082980b0`). Exit 0; 4,443 molecules; none refused by either
implementation.

**B.1, cross-implementation.**
- **R_minus** (c = −χ) agrees with ChargeFW2 on **4,443 of 4,443** molecules, worst difference
  **4.0e-15 e**.
- **R_plus** agrees on 0, worst difference 4.89 e.
- So ChargeFW2's convention is −χ, as its source says.

**B.2, the registered verdicts.**

| reading | train R² | train RMSD | train RMSDat | test R² | test RMSD | test RMSDat | matching | verdict |
|---|---|---|---|---|---|---|---|---|
| printed (S6, seed 5) | 0.9953 | 0.0282 | 0.0414 | 0.9952 | 0.0279 | 0.0481 | | |
| R_minus | 0.99381 | 0.02726 | **0.04140** | 0.99393 | 0.02702 | **0.04811** | 2 / 6 | **PARTIAL** |
| R_plus | 0.99381 | 0.79807 | 4.56076 | 0.99393 | 0.78829 | 4.58096 | 0 / 6 | NOT-REPRODUCED |

- **No reading gives REPRODUCED, so the model reading is undetermined by the registered rule.**
- **Part C runs under ChargeFW2's convention (R_minus),** labelled so.
- **R² cannot separate the readings:** a sign flip leaves r² unchanged.
- **RMSDat reproduces to the printed digit on both splits under R_minus,** with per-type pooling (the
  primary rule).
- **The per-molecule-averaged R² and RMSD miss:** 0.0282 printed against 0.0273, and 0.9953 against
  0.9938.

**B.3, conditioning.**
- The split matrix is positive definite on **4,443 of 4,443** molecules. The smallest eigenvalue over
  the whole set is 0.237.
- Condition numbers: median 1,519, 90th percentile 1,627, maximum 3,172.
- **TRIAGE §5.1's concern is answered:** the κ near −33 does not make any deposited molecule's system
  indefinite.
- The charged/neutral strata were not computed, because the reading is undetermined. They follow in
  part C under R_minus.

### Amendment B-A1: the aggregation the printed RMSD and R² use (registered after B.2, before computing it)

**Why.** RMSDat reproduced exactly with per-type **pooling**, while the per-molecule averages the paper's
text describes did not. The authors' parameterisation code, MACH (`dargen3/MACH`, `modules/comparison.py`,
cited by the paper as ref 31), computes both kinds of statistic:
- **all-atom pooled** RMSD and R² (`all_ats`);
- **per-molecule** RMSD and R², each rounded to 4 decimals and then averaged.

MACH's `SQE.py` is the same model as ChargeFW2's, with −χ.

**What runs:**
- **A1-pooled:** RMSD and R² over every atom of the split pooled together.
- **A1-rounded-mean:** MACH's per-molecule values rounded to 4 decimals before averaging.

**What it can and cannot do:**
- **It cannot change B.2's verdict.** PARTIAL stands whatever this shows.
- **What it can establish:** if A1-pooled matches all four printed RMSD and R² values, then the printed
  values are pooled statistics, and the paper's own sentence ("computed for each molecule and then
  averaged") contradicts its tables. That is a source finding, recorded as such.
- **If neither aggregation matches,** the misses stay unexplained, and nothing further is tried.

### B-A1 result (2026-09-17): the printed RMSD and R² are pooled statistics

`schindler_sqe_results/b_a1.json` (sha256 `ae738d1bd62f9169d006a01d89eac6a01abe5be01655146c4e2d9e29bfea51ae`), exit 0, R_minus.

| split | statistic | printed | A1-pooled | A1-rounded-mean |
|---|---|---|---|---|
| train | RMSD | 0.0282 | **0.02822** | 0.0273 |
| train | R² | 0.9953 | **0.99532** | 0.9938 |
| test | RMSD | 0.0279 | **0.02794** | 0.0270 |
| test | R² | 0.9952 | **0.99523** | 0.9939 |

- **All four match under A1-pooled; none under MACH's rounded per-molecule means.** With B.2's two
  RMSDat values, **every printed S6 seed-5 value reproduces under R_minus** once RMSD and R² are
  pooled over atoms.
- **A source finding, recorded as one:** the paper's sentence "the values of R² and RMSD are computed
  for each molecule and then averaged over the whole set" does not describe the numbers it prints.
- **The registered B.2 verdict is unchanged: PARTIAL.** The amendment said it could not be changed.
- **What this does establish:** the published parameters, our SQE and ChargeFW2 are one model, with
  the right-hand side −χ. **Corrected the same day, before part C:** this sentence first said the paper's printed +χ "is wrong in sign". What is established is narrower: with the published parameter values, only −χ reproduces the paper's own numbers. The paper's metrics are recovered
  exactly with that model.
- **Part C still uses the registered per-molecule averages for its threshold,** and reports pooled
  values beside them.
