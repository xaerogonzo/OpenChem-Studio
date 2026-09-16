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

Probe: `scratchpad/ionescu_convexity_probe.py`, all 12 E models, `R_angstrom`, on

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

Run exactly as §6 registered: `scratchpad/guard_feasibility.py`.

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
