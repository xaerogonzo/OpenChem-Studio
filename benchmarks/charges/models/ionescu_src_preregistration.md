# Ionescu 2013 E-model EEM in src — pre-registration

**Committed before any src code, and before the guard-feasibility measurement in §6.**
Round 4, Track A. The benchmark reproduction this ships from is TRIAGE check 2.8
(`benchmarks/charges/models/TRIAGE.md` §3.8).

## 1. The claim, and only this claim

> These are the charges that Ionescu et al.'s EEM model `<scheme>` assigns to this
> structure.

Never "the partial charges of this molecule". Three things travel with every result
and are stated wherever the model is named:

1. **12 of 24.** The paper publishes 24 parameterisations — three population
   analyses (MPA, NPA, iterative Hirshfeld "HiI") × two bases × two environments ×
   **two atom typings, E and EX**. This application ships **11 E models** (§5).
   **EX is excluded deliberately, not missing**: its atom types carry bond
   multiplicity (`H1, C1, C2, N1, N2, O1, O2, S1, Ca0`, measured on Table S1), and
   the source's EX charges sit on PDB fragments with no bond orders, so an EX
   implementation could never be checked against its source.
2. **Implementation applicability ≠ validated domain.** The E typing is by element
   alone (Table S1's E atom types are exactly `H C N O S Ca`), so the *code* can
   evaluate any conformer whose elements are parameterised. **Scientific validation
   is the protein-fragment population of TRIAGE 3.8 only.**
3. **Non-convexity is a property of the published model** (§4). It is stated, not
   hidden and not "fixed".

## 2. The system, frozen from the paper (ionescu2013.pdf p 2, rendered at 260 dpi)

Read from the rendered page, not the text layer, because equations are where a text
layer lies.

- **Eq 3:** X̄ = Aᵢ + Bᵢqᵢ + k Σⱼ≠ᵢ qⱼ/rᵢⱼ, with **Aᵢ = Xᵢ⁰ + ΔXᵢ** and
  **Bᵢ = 2(ηᵢ⁰ + Δηᵢ)** — the factor of 2 is already inside B.
- **Eq 4:** Σqᵢ = Q — **the net-charge constraint is its own equation**, so an
  unknown X̄ is never read as an unconstrained total.
- **Eq 5, the system solved:** unknowns **(q₁ … q_N, X̄)** — *"the partial atomic
  charges qᵢ and the molecular electronegativity X̄ can be calculated, provided that
  the rest of the terms (Q, rᵢⱼ, k, Aᵢ, Bᵢ) are known"*. An (N+1)×(N+1) system:
  Bᵢ on the diagonal, **k/rᵢⱼ off the diagonal, one k per model**, −1 in the last
  column, a row of 1s and a 0 in the last row; right-hand side (−A₁ … −A_N, Q).
- **k** is *"an adjusting factor first introduced by Yang and Shen"*. The paper
  states no unit for it. **The registered finding is the reading, not a unit:** rᵢⱼ
  in ångström reproduces 36/36 model × dataset rows; in bohr, 0/36.

### Three typesetting errors in the source, and what is implemented instead

Recorded, never silently corrected:

| where | printed | correct | evidence |
|---|---|---|---|
| eq 2, left side | `X₁ = …` | `Xᵢ = …` | every right-hand term is indexed i; eq 3 restates it |
| eq 5, row 2, column 1 | `k/r₂,₃` | `k/r₂,₁` | as printed the matrix is not symmetric |
| eq 5, right-hand side, row N | `A_N` | `−A_N` | rows 1 and 2 are `−A₁`, `−A₂` |

**Implemented against eqs 3 and 4, which are unambiguous.** The benchmark implements
the corrected form and reproduces 36/36; a literal eq 5 would be wrong for the last
atom and could not. A mutation implementing the printed right-hand side must turn a
test red.

## 3. The parameter table, as measured (not as assumed)

`tests/fixtures/charges/ionescu2013/table_s1.csv`: 180 rows, 24 models, columns
`model, atom_type, kappa, A, B`.

- 12 E models × 6 atom types = 72 E rows; exactly one distinct k per model.
- E-model ranges: **A 2.415 – 2.502, B −0.106 – +0.095, k 0.006 – 0.009**. These are
  not eV-scale EEM parameters; they are in "the paper's units", which nobody here
  has established. **Every conclusion below is chosen to be unit-independent.**

**Revision-6 plan error, corrected here before any code:** the plan required a
schema test that "the hardness term B is positive, a requirement for a well-posed
system". **That assertion fails on the source.** **17 of the 72 E-model B values are
non-positive, and all 12 E models have at least one:**

| model | non-positive B |
|---|---|
| E-HiI/6-31G\*\*/PCM, …/gas, E-HiI/6-31G\*/gas | O |
| E-HiI/6-31G\*/PCM | **N, O** |
| E-MPA/6-31G\*\*/PCM, …/gas | S, Ca |
| E-MPA/6-31G\*/PCM | Ca |
| E-MPA/6-31G\*/gas, E-NPA/6-31G\*\*/gas, E-NPA/6-31G\*/gas | S |
| E-NPA/6-31G\*\*/PCM, E-NPA/6-31G\*/PCM | O, S |

A negative diagonal does not by itself make the system ill-posed, and the source
reproduces with these values. The schema test records the sign table as data; it
does not assert a sign.

## 4. Exploratory findings, disclosed as such

**These measurements were made on 2026-09-16 before this document existed, while
checking the parameter table. They motivated §5 and §6. They are exploratory, not a
registered test**, and are recorded so nothing below is read as having been
predicted.

Probe: `benchmarks/charges/models/ionescu_stability.py convexity`, all 12 E models, `R_angstrom`, on

- **IN-DOMAIN** — the SI's training set, insulin and ubiquitin: 43 structures, the
  population that reproduces;
- **EXTRAPOLATION** — `benchmarks/naming/corpus.json`, filtered only to neutral
  molecules of ≥ 3 heavy atoms within the six elements: 94 structures, ETKDGv3
  seed 20260916, MMFF94-optimised.

Quantities, all unit-independent: the sign of the smallest eigenvalue of
H = diag(B) + k/rᵢⱼ on {Σq = 0} (< 0 is a saddle), the full system's condition
number, and max |q|. The eigenvalue routine was checked against the closed form
(B₁+B₂)/2 − k/r on three two-atom cases, and on known definite matrices, first.

**Finding 1 — the published solutions are saddle points, and extrapolation is not
the cause.** In-domain **487 / 516** model × structure solutions are saddles (94%);
extrapolation **380 / 1128** (34%).

**Finding 2 — the mechanism, verified exactly.** A solution is a saddle **if and
only if** the structure contains an element whose B is negative in that model:
**1644 / 1644 agree, 0 disagree.** Proteins almost always contain O, N or S, which is
why the in-domain rate is higher.

**Finding 3 — blow-ups, all from one model.** 8 of 1128 extrapolation solves exceed
the in-domain maximum |q| of 2.051 over all 12 models. **All 8 are E-HiI/6-31G\*/PCM,
the only model with both N and O negative,** on nitrogen-rich molecules: nitrobenzene
**74.2 e**, 1,2,3-triazole **34.8 e**, 1H-1,2,3-triazole 5.1, 2H-tetrazole 4.2,
4H-1,2,4-triazole 2.7, 1H-tetrazole 2.5, sulfamethoxazole 2.5, diazomethane 2.5.

**Finding 4 — the full-system condition number does NOT discriminate.** In-domain
solutions that reproduce have median condition numbers **1.5 – 4.7 × 10⁴**;
nitrobenzene's blow-up is **3.5 × 10⁴**. A threshold on it would refuse the validated
population or miss the blow-ups.

> **How these scripts reached the repository, so nothing here is taken on trust.** §4, §6 and §7
> were first run from a scratch directory. `ionescu_stability.py` was then assembled from **exactly
> that source** — the function bodies extracted programmatically, only imports and paths changed —
> and all three commands re-run. **Every recorded figure reproduced exactly**: 487/516 and 380/1128
> saddles; NOT-SEPARABLE at 0.018; the 6.87 × 10⁻¹¹ solve check, 53 kept, H1 REFUTED, 40 refused,
> NOT-VIABLE. Each run exited 0.

## 5. Decisions taken on those findings (Alex, 2026-09-16)

1. **Ship, with non-convexity stated as a source property.** EEM is defined by
   electronegativity equalization (eqs 1, 5), which the source computes and which
   is reproduced exactly; the paper never claims an energy minimum. Refusing saddles
   would refuse 94% of the validated population. **The scope sentence says the
   charges are the unique stationary point of the model's equations and, for any
   structure containing an element with negative B in that model, not an energy
   minimum.**
2. **Exclude E-HiI/6-31G\*/PCM. Eleven E models ship.** It is the only model that
   produced a physically absurd charge, on common chemotypes. Recorded as excluded
   with Finding 3, in the same way as the EX family.
3. **No guard is chosen from these numbers.** A guard is measured first (§6).

## 6. Guard feasibility — REGISTERED BEFORE IT RUNS

**The question, and only this one:** does a discriminator computed from the *system*,
before trusting a solve, separate blow-ups from sound solves **on the data already in
hand**? It is a feasibility check, deliberately small, and it decides whether a larger
calibration study is worth doing — not what the threshold is.

### Why a different condition number

Finding 4's number came from the full (N+1)×(N+1) system, which mixes the ±1
constraint row and column (order 1) with B and k/r (order 10⁻²). That mixing can
inflate the number with system size whatever the physics. A charge blows up because
the constrained problem is nearly singular, and the quantity that measures that is
the spectrum of the **reduced Hessian** R = ZᵀHZ, with Z an orthonormal basis of
{Σq = 0}.

### Discriminators, fixed now

- **Primary: κ_R = max|λ(R)| / min|λ(R)|**, the reduced condition number.
  Unit-independent.
- Secondary, reported only: min|λ(R)| (unit-dependent, so compared within a model
  only).

### Populations and labels, fixed now

- **Negatives that must never be refused:** every IN-DOMAIN structure × every one of
  the **11 shipped** models.
- **Positives:** extrapolation solves whose max |q| exceeds **2.051**, the in-domain
  maximum over all 12 models. The excluded model is **included here**, because it is
  the only source of positives; without it there is nothing to separate.
- **Everything else:** extrapolation solves at or below 2.051, reported as a
  distribution, not labelled.

### The criterion, fixed now

**SEPARABLE** if there exists a κ_R threshold at or above which **every positive**
falls and at or below which **every in-domain negative** falls, i.e.
`min(κ_R over positives) > max(κ_R over in-domain negatives)`.

**NOT-SEPARABLE** otherwise. The margin between those two values is reported either
way.

### What each outcome means, fixed now

- **NOT-SEPARABLE** → κ_R cannot be the guard; no larger study of κ_R is run; the
  decision returns to Alex with the numbers.
- **SEPARABLE** → **not a shipped guard yet.** 8 positives from one model do not
  validate a threshold (a threshold fitted to a handful of cases is not validated).
  It means a calibration study is worth designing, with an independent validation
  population. The regulatory corpus supplies one: 67 eligible molecules, 53 of them
  absent from the naming corpus.

Nothing in this section changes the model, the parameters or the 36/36 reproduction.

## 6-R. Guard feasibility — RESULT (2026-09-16, run after commit 97dc03c)

Run exactly as §6 registered: `benchmarks/charges/models/ionescu_stability.py guard`.

| | count | κ_R |
|---|---|---|
| negatives: in-domain × 11 shipped models | 473 | **max 474.1** (E-HiI/6-31G\*\*/gas, a training-set fragment) |
| positives: extrapolation, max \|q\| > 2.051, all 12 models | 8 | **min 8.6** (1H-tetrazole), max 230.7 (nitrobenzene) |
| unlabelled extrapolation | 1120 | 1002 of them ≥ the smallest positive's κ_R |

**VERDICT: NOT-SEPARABLE.** min κ_R over positives / max κ_R over negatives = **0.018**.
Not marginal: the worst blow-up, nitrobenzene at 74 e, is *better* conditioned than
hundreds of validated protein fragments.

**The registered hypothesis is refuted.** §6 proposed that Finding 4's full-system
number was inflated by constraint mixing and that the reduced Hessian would isolate
the physics. It does not; it fails by a factor of ~55 in the wrong direction.

**One pattern, recorded as a HYPOTHESIS and not measured.** The secondary quantity
min|λ(R)| is smallest for the two extreme blow-ups (1.1–1.3 × 10⁻⁴) but the six mild
positives (1.1–2.3 × 10⁻³) sit *above* the in-domain negatives (6.1–7.7 × 10⁻⁴) — the
proteins have near-zero eigenvalues too, and do not blow up. That is consistent with a
blow-up needing a near-zero eigenvalue **and** a right-hand side aligned with its
eigenvector, which no property of H alone can see. Consistent with the data is not
the same as established; it is not relied on below.

**As §6 registered for this outcome:** κ_R cannot be the guard, no larger study of κ_R
is run, and the decision returns to Alex with these numbers.

**One fact that bears on that decision:** all 8 positives are the **excluded** model.
On this corpus the **11 shipped models produced no solve beyond the in-domain maximum**.

## 7. Alignment guard — REGISTERED BEFORE IT RUNS

Decided by Alex on §6-R: study a guard built on the hypothesis that a blow-up needs a
near-zero eigenvalue **and** a right-hand side aligned with its eigenvector.

### 7.1 An equivalence that shapes the study (derivation, not a measurement)

On {Σq = Q} write q = q₀ + Zy, with q₀ = (Q/N)·1 and Z an orthonormal basis of the
constraint's null space. Stationarity gives R y = g, with R = ZᵀHZ and
g = −Zᵀ(A + Hq₀). With R = VΛVᵀ:

    ‖q − q₀‖² = ‖y‖² = Σₖ cₖ²,   cₖ = (vₖᵀ g) / λₖ

**So the exact alignment decomposition sums to the solved charge deviation.** A raw
alignment "predictor" costs a solve and carries no information beyond |q|. Two
consequences are registered here:

- **Raw max|q| is not an admissible baseline.** Positives are *defined* by
  max|q| > 2.051, which is the in-domain maximum, so |q| separates them by
  construction. No result below is framed as "as good as |q|".
- The study therefore tests **the mechanism** and **a scale-free guard**, and the
  guard is judged on a population it was **not** calibrated on.

### 7.2 Question 1 — is the mechanism real?

Per solve, the **dominant-mode share** s = maxₖ cₖ² / Σₖ cₖ², and the |λ|-rank of
the dominant mode (1 = the smallest |λ|).

**H1, registered:** in every positive, the dominant mode is among the three
smallest-|λ| modes **and** s ≥ 0.5; in the in-domain negatives, the mode with the
smallest |λ| carries **less than 0.5** of ‖y‖² in a majority of solves.

**Outcome:** H1 SUPPORTED if both halves hold, REFUTED if the positive half fails,
PARTIAL if only the positive half holds. Reported with the full distributions.

### 7.3 Question 2 — a scale-free guard

**α = ‖y‖ · median|λ(R)| / ‖g‖** — the solution's size relative to what a typical mode
would give it. It is dimensionless, so it does not depend on the unknown units.

- **Calibration population:** the §4 extrapolation set (naming corpus, 94 molecules)
  plus the in-domain negatives.
- **Validation population, independent:** `benchmarks/regulatory/corpus.json`,
  filtered by the §4 rule (neutral, ≥ 3 heavy atoms, the six elements), **excluding
  every molecule also present in the naming corpus** by canonical SMILES. ETKDGv3,
  seed 20260916, MMFF94. Registered size: 53.
- **Labels in both:** positive when max|q| > 2.051; all 12 models, the excluded one
  included, since it is the only source of positives.
- **Threshold:** τ_α = the smallest α over calibration positives. Chosen on
  calibration only, then frozen.

**Criterion, GUARD-VIABLE only if all three hold:**
1. on calibration: τ_α > max α over in-domain negatives (× 11 shipped models);
2. on validation: every positive has α ≥ τ_α;
3. on validation: no solve under the **11 shipped models** with max|q| ≤ 2.051 has
   α ≥ τ_α — the guard must not refuse sound solves on unseen molecules.

**If the validation set yields no positives,** criterion 2 is **UNTESTED**, not
passed, and the verdict can be at most **GUARD-NOT-CONTRADICTED** — which does not
license shipping a threshold.

### 7.4 What each outcome licenses

- **GUARD-VIABLE** → α with τ_α is proposed to Alex as the shipped refusal, with both
  populations' numbers.
- **GUARD-NOT-CONTRADICTED** → not shipped as validated; returns to Alex.
- **Anything else** → α is not the guard, and the decision returns to Alex.

## 7-R. Alignment guard — RESULT (2026-09-16, run after commit 25c5d84)

Run as §7 registered: `benchmarks/charges/models/ionescu_stability.py alignment`, `PY_EXIT=0`.

**Built-in check:** the §7.1 reduced solve reproduces the benchmark's full solve to
**6.9 × 10⁻¹¹ e**, so the decomposition below is of the actual charges.

**Validation population: 53 kept, as registered** — 14 dropped as present in the
naming corpus, 0 as charged, 0 at embedding. (The registered 53 was counted before the
neutral filter was applied; applying it removed nothing.)

### Question 1 — the mechanism: H1 REFUTED

| calibration positive | max \|q\| | dominant mode, \|λ\|-rank | share of ‖y‖² |
|---|---|---|---|
| nitrobenzene | 74.16 | 1 | 0.999 |
| 1,2,3-triazole | 34.78 | 1 | 1.000 |
| 1H-1,2,3-triazole | 5.05 | 1 | 0.993 |
| 2H-tetrazole | 4.20 | 1 | 0.988 |
| 4H-1,2,4-triazole | 2.74 | 1 | 0.980 |
| 1H-tetrazole | 2.48 | 1 | 0.962 |
| **sulfamethoxazole** | 2.48 | **6** | **0.726** |
| diazomethane | 2.46 | 1 | 0.964 |

- **Positive half FAILS:** sulfamethoxazole's dominant mode is rank 6, outside the
  registered rank ≤ 3.
- Negative half holds: the smallest-|λ| mode carries < 0.5 of ‖y‖² in **473 / 473**
  in-domain solves — **median 0.000, max 0.001**.

**Verdict: REFUTED, as the registered rule defines it.** Recorded without softening:
seven of eight blow-ups are driven almost entirely by the single smallest mode, and in
every protein that mode carries essentially nothing, so the data are *largely*
consistent with the hypothesis. A registered gate that one case fails is failed.

### Question 2 — the scale-free guard α: NOT-VIABLE

- τ_α = **2.126** (smallest over the 8 calibration positives); max α over in-domain
  negatives = **1.948**.
- Criterion 1, τ_α > max in-domain negative: **PASS**.
- Criterion 2, every validation positive ≥ τ_α: **PASS** — 6 positives, α 2.21 – 11.6.
- Criterion 3, no sound shipped-model validation solve refused: **FAIL — 40 refused**,
  among them **cyclohexane at max |q| 0.158**, ethylamine 0.601 and 2-butanone 0.752,
  all under E-HiI/6-31G\*\*/PCM.

**Verdict: NOT-VIABLE.** α catches every blow-up and refuses ordinary molecules with
modest charges.

### A finding outside both questions, and it bears on §5

§6-R recorded that the 11 shipped models produced no solve above 2.051 **on the naming
corpus**. **On the independent regulatory corpus they do:**

| molecule | shipped model | max \|q\| |
|---|---|---|
| sulfuric acid | E-NPA/6-31G\*/PCM | **4.28** |
| sulfuric acid | E-NPA/6-31G\*\*/PCM | **4.18** |
| sulfuric acid | E-HiI/6-31G\*\*/gas | 2.84 |
| carbon dioxide | E-HiI/6-31G\*\*/PCM | 2.15 |

(And nitroethane reaches 7.79 under the excluded model.) **Excluding
E-HiI/6-31G\*/PCM did not make the shipped set free of blow-ups;** that conclusion was
a property of one corpus.

**As §7.4 registered:** α is not the guard, and the decision returns to Alex.

## 8. HF/6-31G* reference check — REGISTERED BEFORE IT RUNS

Decided by Alex on §7-R: ship with a refusal on the solved charges, and **check against a
reference before setting its bound**. Also decided: document all of this so it can be worked
on further (§9).

### 8.1 Why a reference, and what it can and cannot settle

The only measured bound so far is **2.051, the in-domain maximum |q|** — taken from protein
fragments, which contain **no hypervalent sulfur**. In quantum-chemical population analyses a
high-oxidation-state sulfur can genuinely carry a large positive charge, so a protein-anchored
bound might refuse real chemistry. **No reference value is quoted here from memory**; that is
what the run is for.

**Ionescu's protocol, from the paper:** HF single points on crystal-derived geometries; MPA in
Gaussian 09, NPA with NBO 3.1, iterative Hirshfeld (HiI) with HiPart. The PCM solvent is not
stated.

**What the installed tools can reproduce, established before registering:**

| scheme | reference available | like-for-like? |
|---|---|---|
| Mulliken ↔ E-MPA models | ORCA 6.1.1 | **yes**, one recorded difference: ORCA uses spherical 5d functions, Gaussian 09's 6-31G\* default is Cartesian 6d, and Mulliken charges depend on the basis |
| standard Hirshfeld ↔ E-HiI models | ORCA 6.1.1 | **no** — non-iterative Hirshfeld, characteristically smaller charges; an indicator only |
| NPA ↔ E-NPA models | **none: NBO is not installed** | — |

So **the shipped blow-ups of §7-R — sulfuric acid under two NPA models (4.28, 4.18) and under
HiI (2.84), and CO₂ under HiI (2.15) — cannot be adjudicated by a reference here.** This check
tests the hypervalent-sulfur concern for the Mulliken scheme only.

### 8.2 The run

- **Molecules:** sulfuric acid and carbon dioxide (the §7-R shipped-model positives) and
  nitrobenzene (the excluded model's 74 e blow-up, a known-absurd anchor). **Three molecules;
  nothing here is a population estimate.**
- **Geometry: identical to the §4 probe** — RDKit AddHs, ETKDGv3 seed 20260916, MMFF94 — so the
  method is the only thing that differs from the model charges.
- **Level:** ORCA 6.1.1, RHF/6-31G\*, gas phase, single point. Mulliken and Hirshfeld charges.
- **Compared with:** E-MPA/6-31G\*/gas (Mulliken, like-for-like) and E-HiI/6-31G\*/gas
  (Hirshfeld, indicator only), on the same atoms.

### 8.3 The question, and what each answer licenses

**Does RHF/6-31G\* Mulliken put |q| > 2.051 on any atom of the three molecules?**

- **YES** → a bound anchored at the protein maximum refuses real chemistry, at least in the
  Mulliken scheme. **2.051 cannot be the shipped bound**, and the decision returns to Alex with
  the reference values.
- **NO** → 2.051 is **not contradicted** by this reference. It is proposed to Alex as the bound,
  with the NPA and HiI cases recorded as **unadjudicated**, not passed.

Reported either way: every atom's reference and model charge, and |Δq| between them.

## 8-R. HF/6-31G* reference check — RESULT (2026-09-16, run after commit 11652ce)

Run as §8 registered: `benchmarks/charges/models/ionescu_reference.py`, `PY_EXIT=0`. Every SCF
converged; every Mulliken and Hirshfeld sum is zero to ±1.2 × 10⁻⁵, which confirms the parse.

### The registered question: NO

RHF/6-31G\* Mulliken's largest |q| over the three molecules is **+1.855, on sulfur in sulfuric
acid** — below 2.051. **2.051 is not contradicted by this reference.** As registered, the NPA and
HiI cases stay **unadjudicated**.

**The hypervalent-sulfur concern was right in direction and not in crossing:** sulfur does carry a
large positive Mulliken charge, and the margin to the protein anchor is thin, 1.855 against 2.051.

### What the per-atom table shows beyond the registered question

This is reported, not registered, and it does not change §8.3's answer.

| molecule, atom | reference | model | \|Δq\| | comparison |
|---|---|---|---|---|
| sulfuric acid, **S** | Mulliken **+1.855** | E-MPA/6-31G\*/gas **+0.096** | **1.759** | like-for-like |
| nitrobenzene, **N** | Mulliken **+0.524** | E-MPA/6-31G\*/gas **−0.464** | 0.988 — **sign** | like-for-like |
| carbon dioxide, C | Mulliken +1.018 | E-MPA/6-31G\*/gas +0.985 | 0.033 | like-for-like |
| sulfuric acid, **every atom** | Hirshfeld S +0.714, O −0.218/−0.356, H +0.217 | E-HiI/6-31G\*/gas S **−0.666**, O **+0.642/+1.451**, H **−1.761** | up to 1.98 — **every sign inverted** | indicator only |

**A second failure mode, which a magnitude refusal cannot see.** The models can be badly wrong at
ordinary magnitudes: the like-for-like MPA model under-charges hypervalent sulfur by 1.76 e and
gives the nitro nitrogen the wrong sign, and the HiI model inverts every sign on sulfuric acid.
**Their largest charges are 0.717, 0.478 and 1.761 — none would trip a 2.051 refusal.**

On the HiI row, recorded with its limit: standard and iterative Hirshfeld are different schemes and
this comparison adjudicates nothing. **A scheme difference changes magnitudes; it does not invert
every sign in a molecule**, and acidic hydrogens at −1.76 e are chemically untenable on any scheme.

**Consequence for §5:** a charge-magnitude refusal protects against runaway solves only. **Off the
protein domain, the domain caveat is the protection that matters**, and the scope sentence has to
say so in words — that these models can be wrong in sign and by more than 1.5 e on molecules unlike
proteins, without any refusal firing.

## 9. Silent-error survey — REGISTERED BEFORE IT RUNS

Decided by Alex on §8-R: before deciding ship or hold, measure whether the silent errors §8-R found
— wrong sign, or more than 1.5 e off, with no refusal firing — are **common or confined to extremes
like sulfuric acid**. §8-R rested on one sulfur molecule and one nitro compound.

### 9.1 Only the like-for-like comparison

RHF Mulliken ↔ E-MPA gas models, the one pairing §8.1 established as like-for-like (bar spherical
5d against Gaussian 09's Cartesian 6d; §8-R's CO₂ agreed to 0.033 e, which suggests but does not
prove that difference is small). **Both shipped MPA gas models:** E-MPA/6-31G\*/gas against
RHF/6-31G\*, and E-MPA/6-31G\*\*/gas against RHF/6-31G\*\*. PCM models are excluded: the paper names
no solvent, so no PCM reference is like-for-like.

### 9.2 The population, with no size cap

The §4 extrapolation set — the naming corpus filtered to neutral molecules of ≥ 3 heavy atoms within
the six elements — at its §4 geometries. **All 94, uncapped**, because any size cap is a selection.
Measured before registering: the largest has 50 atoms, and §8's timings (CO₂ 1.3 s, nitrobenzene
19 s) make that affordable. **Stratified, and every rate reported per stratum:**

| stratum | rule | molecules |
|---|---|---|
| S | contains sulfur | **11** — small; no stratum rate is read as a population estimate |
| N | contains nitrogen, no sulfur | 44 |
| **CHO — the control** | neither | 39 |

**The control exists so a rate can be read:** if plain C/H/O molecules show the same errors, the
problem is not about sulfur or nitrogen.

A molecule whose SCF does not converge, or which is open-shell, is **excluded and listed**, never
silently dropped.

### 9.3 Definitions, fixed now

Declared conventions, chosen before the run, not fitted to it:

- **sign error** (atom): reference and model charges of opposite sign, with **|q_ref| ≥ 0.10 e** —
  so sign noise on a near-neutral atom does not count;
- **magnitude error** (atom): **|q_ref − q_model| ≥ 0.50 e**, half an electron;
- **silent error** (molecule, per model): at least one atom with a sign or magnitude error, **and**
  the model's max |q| ≤ 2.051 — the refusal would not fire;
- **stratum rate:** the fraction of the stratum's molecules with a silent error.

**Primary classification, per stratum and model:** **CONFINED** at ≤ 10%, **COMMON** at ≥ 50%,
**INTERMEDIATE** between.

**Sensitivity, reported and not primary:** the same rates at sign ≥ 0.05 / magnitude ≥ 1.0 e, and
the full per-molecule distribution of max |Δq|, so the thresholds can be re-read by anyone.

### 9.4 What it licenses

**Nothing on its own.** It is the evidence for Alex's ship-or-hold decision, which returns to Alex
with the per-stratum rates, the control's rate beside them, and every molecule listed.

## 9-R. Silent-error survey — RESULT (2026-09-16, run after commit e489910)

Run as §9 registered: `ionescu_survey.py run 6-31G*`, `run 6-31G**`, `summarize`. Every run
`PY_EXIT=0`; **94 / 94 assessed at each basis, none excluded** (no open-shell molecule, every SCF
converged). Per-molecule reference and model charges are committed beside the script as
`ionescu_survey_6-31Gs.json` and `ionescu_survey_6-31Gss.json`.

### Primary classification, per §9.3

| stratum | E-MPA/6-31G\*/gas | E-MPA/6-31G\*\*/gas | class |
|---|---|---|---|
| **S** (11) | 7 / 11 = **63.6%** | 7 / 11 = **63.6%** | **COMMON** |
| N (44) | 7 / 44 = 15.9% | 8 / 44 = 18.2% | INTERMEDIATE |
| **CHO control** (39) | 2 / 39 = 5.1% | 3 / 39 = 7.7% | **CONFINED** |

Sensitivity (sign ≥ 0.05, magnitude ≥ 1.0 e): S 45.5% at both bases; N 15.9%; CHO 5.1% / 12.8%.
max |Δq| over all 94: median 0.167 / 0.141, 90th percentile 0.545 / 0.780, max 1.682 / 1.747.

**The control makes the rates readable: the errors are about sulfur and nitrogen, not a general
failure of the model.** Every control-stratum silent error is a sign flip on an atom just above the
0.10 e threshold, with max |Δq| 0.15 – 0.22.

### The sulfur split, measured after the registered analysis

Not part of §9's registered questions; checked because a pattern read off a list is not a finding.
S–O bonds counted from each molecule's SMILES; **identical at both bases.**

| sulfur class | molecules | silent | max \|Δq\| |
|---|---|---|---|
| **S bonded to O** — sulfamethoxazole, sulfanilamide, benzenesulfonamide, dimethyl sulfone (2 O); omeprazole, DMSO (1 O) | 6 | **6 / 6** | **0.84 – 1.75** |
| no S–O bond — thiophene, thiophenol, dimethyl disulfide, carbon disulfide | 4 | 0 / 4 | 0.12 – 0.31 |
| thiourea — C=S, no oxygen | 1 | 1 | **0.531 / 0.505** — at the 0.50 threshold |

**Every sulfur bonded to oxygen is a silent error, and every sulfur without one is within 0.31 e
except thiourea, which sits on the threshold.** One case outside the survey agrees: sulfuric acid
(§8-R), an S–O molecule the survey never saw, under-charged at sulfur by 1.76 e.

**Nitrogen's silent errors are also chemically grouped**, reported and not yet checked the way
sulfur was: pyridine N-oxide, 4-methylpyridine N-oxide, isonicotinic acid N-oxide; nitrobenzene;
1H- and 2H-tetrazole, 1H-1,2,3-triazole; diazomethane.

**Not tested at all:** calcium. The survey population contains none.

### What it licenses, as §9.4 registered

Nothing on its own. It returns to Alex with these rates, the control beside them, and every
molecule listed.

## 10. Decisions on §9-R, and a record for rework

### 10.1 What ships "for now" (Alex, 2026-09-16)

1. **Two models only: E-MPA/6-31G\*/gas and E-MPA/6-31G\*\*/gas** — the only two whose off-domain
   behaviour was measured (§9). The other nine reproduce in-domain (TRIAGE 3.8) with off-domain
   behaviour **unmeasured**: deferred, not discarded.
2. **Two refusals, both returning a reason and never a number:**
   - **any sulfur bonded to oxygen** — 6 / 6 silent errors in §9-R, and sulfuric acid out-of-sample
     in §8-R;
   - **any solve with max |q| > 2.051** — the in-domain maximum, not contradicted by §8's reference.
3. **The nitrogen classes are documented, not refused** — N-oxides, nitro, tetrazoles and
   triazoles, diazo — because that grouping has not been checked the way sulfur's was.
4. **Calcium ships untested off-domain**, and says so.

Alex's words on it: *"let's go with 1 for now, but write this all down, maybe for later rework,
this is getting pretty patchwork in my opinion."* The rest of this section is that record.

### 10.2 Why it is patchwork: one root cause, four patches

**The root cause.** The published E parameters contain **negative effective hardnesses** — 17 of
the 72 B values, on N, O, S and Ca — so the EEM energy is **non-convex for any structure containing
one of those elements** (§4 Finding 2, 1644 / 1644 exactly). A non-convex quadratic under a linear
constraint still has a unique stationary point, but it can be nearly singular. The parameters were
also fitted only to protein fragments. Together those produce three symptoms:

- **runaway solves** — nitrobenzene 74 e (§4), sulfuric acid 4.28 e under a shipped-at-the-time
  model (§7-R);
- **saddle points** — 94% of the model's own validation set (§4);
- **silent errors off-domain** — oxidised sulfur wrong by up to 1.75 e, with sign flips, at ordinary
  magnitudes (§8-R, §9-R).

**The four patches, each aimed at one symptom:**

| patch | symptom it treats | where it came from |
|---|---|---|
| exclude E-HiI/6-31G\*/PCM | runaways | §4 Finding 3 |
| refuse max \|q\| > 2.051 | runaways in the models that remain | §7-R, §8-R |
| refuse S bonded to O | silent errors | §9-R |
| ship only the two MPA gas models | unmeasured off-domain behaviour | §9.1 |

**Three system-level guards were tried first and each failed a registered test** — the full
condition number (§4 Finding 4), the reduced condition number κ_R (§6-R, margin 0.018) and the
scale-free α (§7-R, 40 false refusals). The surviving patches are the ones that did not.

### 10.3 The question a rework has to answer first

**One artifact is being asked to meet two goals that pull apart:**

- **(G1) reproduce Ionescu 2013 faithfully** — which it does: 36 / 36 in-domain;
- **(G2) give good 3D charges on drug-like molecules** — which the published model does not do
  off-domain.

Every patch is a compromise between those two. **Decide which one this feature is for, and most
of the patchwork follows or falls away:**

- **If G1:** the patches are the honest cost of a flawed published model, and the rework tidies
  them — options A and B below.
- **If G2:** faithful reproduction stops being the constraint, Ionescu provenance can be dropped,
  and the problem is fixed at the source — options C and D.

### 10.4 Options, recorded, not chosen

**A — one applicability-domain mechanism instead of hand rules (G1).** Replace the S–O rule, the
nitrogen-class list and the model exclusion with one measure of distance from the protein-fragment
training population (for example fingerprint similarity), derived and validated once. One mechanism
refuses anything outside the validated domain, instead of a rule per failure found.

**B — complete the reference coverage (G1).** Obtain NBO (for NPA) and an iterative Hirshfeld
implementation (HiPart, which the paper used, or an equivalent), so the nine unmeasured models can
be surveyed the way §9 surveyed two. Until then, model choice among the eleven is not evidence-based.

**C — a convex refit, which is a new model (G2).** Refit EEM parameters with the effective hardness
constrained positive — or the reduced Hessian positive-definite — so runaways and saddles cannot
occur by construction. It needs a reference charge set spanning the target chemistry (oxidised
sulfur, N-oxides, drug-like molecules) and its own pre-registered validation. **It would be an
OpenChem-fitted model, not Ionescu 2013**, and has to say so.

**D — ask whether an EEM-class model can represent oxidised sulfur at all (G2).** Equalisation with
fixed per-element parameters may be structurally unable to capture hypervalent sulfur; a split-charge
or bond-aware form might. Round 3 is a caution here, not a recommendation: Mathieu's SQE was
INCONCLUSIVE and Nistor's PARTIAL.

### 10.5 Everything needed to pick this up again

- **Instruments, all committed and reproducible:** `ionescu_stability.py` (§4, §6, §7),
  `ionescu_reference.py` (§8), `ionescu_survey.py` with its two result JSONs (§9).
- **The benchmark it all rests on:** `ionescu_eem_check.py` and TRIAGE 3.8.
- **Populations:** `benchmarks/naming/corpus.json` (calibration and survey), the regulatory corpus
  (independent validation), the Ionescu SI in Sci Downloads (in-domain).
- **Open questions, each named where it was found:** the nitrogen grouping (§9-R); whether H1's
  alignment mechanism holds once sulfamethoxazole is explained (§7-R); calcium off-domain (§9-R);
  the nine unmeasured models (§9.1); the NPA and HiI blow-ups no installed tool can adjudicate (§8.1).
