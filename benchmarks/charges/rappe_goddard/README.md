# Rappé–Goddard QEq and Bultinck EEM, implemented here: what the oracles said

Phase A of "EEM and QEq" (ROADMAP, DECIDED 2026-09-14). The implementation
is `src/openchem/chem/charge_equilibration.py`. Every tolerance and reading
was fixed in `preregistration.md` before the solver existed, and its
amendments say which ones came after a number had been seen.

```bash
uv run --no-sync python -m pytest tests/test_charge_equilibration.py -q
uv run --no-sync python benchmarks/charges/rappe_goddard/oracle.py
```

## Verdict

- **EEM passes its gate.** It ships with Bultinck part I Table 1's parameters
  (Phase B).
- **QEq stopped at the pre-registered stop rule, twice.** The next decision is
  Alex's.
- **Harmony et al. 1979 arrived, and the polyatomic rows point at one reading.**
  - **Under the pre-registered primary P** (Table I's printed ζ), 39 of 76
    Table III/IV cells miss.
  - **Under R4** (eq 17′, λ = ½ for every element), 10 miss. Table III's
    experimental column for H₂O, NH₃ and CH₄ lands within 0.002 e, as HF's did.
  - The paper's text supports R4: "Rounding off to λ = 1/2 … and hence (17)
    becomes (17′)".
- **R4 is ADOPTED (amendment A6, 2026-09-14), after the tables were seen.**
  It is the solver's default; P stays in the code as `PREREGISTERED`, and
  every P number below stays on file.
- **QEq SHIPPED under amendment A8's revised scope (2026-09-14).** The
  original O4/O5 gate failed and its strict xfails stay. What ships is
  λ = ½ with the experimental hydrogen set; non-convergence and a final
  active bound are refused, and silicon is a documented source
  discrepancy. The scope sentence is in A8 and in SCIENTIFIC_LIMITATIONS.

| # | Oracle | Result |
|---|---|---|
| O1 | Slater integrals against momentum space, over 1076 grid points | worst 1e-9 eV or better, passes |
| O1 | against the 30-digit mpmath table (1076 rows; its two coordinate systems agree to 1.8e-22 Ha) | **worst 5.2e-14 Ha**, at the near-zero point R = 1e-6 bohr; passes |
| O2 | eq 17 regenerates Table I's ζ | 14 elements within ±0.0001; **N misses by 2.5e-5**, within the rounding of its printed radius (amendment A3); **O misses by 0.0030**, four times its rounding, recorded before any solve |
| O3 | Table II, 20 alkali halides, both λ columns | **passes: worst 0.0005 e** in each column, and eq 18 agrees with the general solver to 1e-8 e |
| O4 | Table III hydrogen charges (±0.001 e diatomic, ±0.002 e polyatomic) | **STOP**: under P, HF, H₂O, NH₃ and CH₄ miss and LiH never converges; under the adopted R4, the QEq column passes except LiH, and the QEqHF column misses HF, H₂O, NH₃ and CH₄ |
| O5 | Table IV at ±0.01 e: diatomics at Huber r_e, polyatomics at Harmony 1979 geometries (A4), ethane at Iijima 1973 from the 1998 Kuchitsu digest (A5) | **P misses 34 of 70 cells; R4, adopted, misses 7** (below) |
| O6 | Open Babel's EEM, given Table 1 | same arithmetic to 1e-6 e (compatibility only) |
| O7 | EEM eq 3's diatomic closed form | passes; the η-for-2η build fails, as it must |
| O8 | EEM matrix, entry by entry | passes |
| O9 | bound fixing against brute-force KKT | **STOP**: misses the optimum in 28 of 200 synthetic systems |

**What O3 establishes:** the Slater integrals, the linear system and its sign,
and Table I's heavy-atom ζ reproduce the paper wherever hydrogen is absent,
across n = 3 to 6 and both of the paper's λ values. The QEq failures below are
therefore about hydrogen and the bounds, not the core.

## QEq stop 1: hydrogen (O4)

Q_H by reading, with the difference from the printed value
(`oracle.py`, 2026-09-14):

| row | set | printed | P | R1 | R2 | R3 | R4 |
|---|---|---|---|---|---|---|---|
| III HF | QEq | 0.462 | 0.4568 (−0.0052) | 0.4363 | 0.4006 | 0.4568 | **0.4623 (+0.0003)** |
| III HF | QEqHF | 0.457 | 0.4613 (+0.0043) | 0.4397 | 0.4039 | 0.4613 | 0.4671 (+0.0101) |
| III LiH | both | −0.767 / −0.679 | no convergence (oscillating) | none (monotone) | none (stalled) | none (oscillating) | none (oscillating) |
| IV HF | QEq / QEqHF | 0.46 / 0.46 | 0.4568 / 0.4613 | | | | |
| IV ClH | QEq / QEqHF | 0.32 / 0.31 | 0.3138 / 0.3126 | | | | |

- **HF:** no reading passes both columns.
  - R4 (λ = ½ for every element) lands on the QEq column but misses QEqHF by
    0.010.
  - Under every reading, the HF-fitted hydrogen set gives a *larger* Q_H than
    the experimental set. The paper's own table has it smaller for all five
    molecules.
  - A pass by R4 in one column is not a validation (section 3).
- **LiH:** the paper says 6–10 iterations sufficed for every case; here no
  reading converges in 50.
  - Tabulating the iteration map shows why. Near the printed −0.767, hydrogen's
    diffuse ζ_H(Q) ≈ 0.30 and eq 21's J_HH ≈ 3.9 eV make the 2×2 system's
    J_Li + J_HH − 2J_LiH only 0.28 eV under P. The solve then swings to the
    charge bounds.
  - For −0.767 to be self-consistent, that quantity would have to be about
    1.98 eV (from eq 18's form, with χ_H − χ_Li = 1.522 eV).
  - No pre-registered reading comes near it, and nothing was tuned towards it.
- **Measured since (amendment A7, below): the iteration is not the cause.**
  Under the adopted reading LiH has exactly one self-consistent charge,
  −0.9737, and the printed −0.767 is not one. Damped iteration converges, but
  to −0.9737.

## The polyatomics, at Harmony 1979's geometries (A4) and ethane's (A5)

Run 2026-09-14 by `oracle.py`. Geometries: per parameter, the first printed of
equilibrium, substitution, average, effective; conformations as Harmony draws
them. Ethane, which Harmony lacks: Iijima 1973's r_z structure, the only one
in the 1998 digest that predates Landolt–Börnstein II/7. Cells outside
tolerance, of 76 (6 in Table III, 70 in Table IV):

| reading | P | R1 | R2 | R3 | **R4** | P, effective-first geometry |
|---|---|---|---|---|---|---|
| cells missed | 39 | 59 | 64 | 44 | **10** | 40 |

- **The geometry choice is not the cause.** Reversing the structure-type order
  moves P from 39 to 40 misses.
- **R4 with the experimental hydrogen set reproduces every Table III and IV
  cell except two:**
  - formamide's C, +0.011 against a tolerance of 0.01;
  - SiH₄.
- **The QEqHF column misses more under R4.** Of R4's 10 misses, 7 are
  QEqHF cells:
  - H₂O +0.008 and CH₄ +0.005 in Table III (tolerance 0.002);
  - methanol H(O) +0.016, C −0.014 and Ht +0.014;
  - formamide N −0.013;
  - SiH₄.

  HF's QEqHF was already +0.010. Something about the HF-fitted hydrogen set is
  not what the paper says.
- **SiH₄ fails under every reading by about 0.18 e.**
  - Every reading gives H about −0.04 e (Si's χ, 4.168, is below hydrogen's
    4.528); the table prints +0.13.
  - It is the only hydride whose heavy atom is less electronegative than H in
    Table I.
  - **Measured since (A7):** no Si–H length or tetrahedral distortion in the
    sweep changes the sign. Ramachandran et al. 1996, from Rappé's group,
    print QEq silyl hydrogens of −0.021 and −0.040 in O(SiH₃)₂. That strongly
    supports the 1991 +0.13 being inconsistent with the group's later program.
    It is not proof of a misprint, because which silicon parameters that
    program used is an inference.
- **LiH still converges under no reading, R4 included.**

## Amendment A7: the open problems, diagnosed (2026-09-14)

Everything below was pre-registered in A7 before it ran
(`hydrogen_fixed_point.py`, `lih_g_scan.csv`, and the A7 tests). Nothing in it
changes the solver.

**LiH, as three separate questions.** F is one complete outer iteration of the
solver; a test holds that iterating F reproduces `qeq_charges` step for step.

| | experimental set | HF set | A7's prediction |
|---|---|---|---|
| Q-A: roots of F(Q) − Q on [−1, +1] (2001 points, bisected) | one, **−0.973740**, no tangency | one, **−0.982743** | one root, −0.973 / −0.982 ± 0.002: **held** |
| bound state at Q\* | none active; Li is 0.026 from its +1 bound, one active set within ±1e-3 | none; 0.017 | bound-free: **held** |
| slope of F at Q\* (h = 1e-3 … 1e-6, spread 0.001) | **−14.06** | **−14.12** | −14.24 / −14.36 ± 0.1: **FAILED** (the earlier estimate was taken at a coarser root). The instability, \|s\| > 1, holds |
| Q-B: g(printed) | g(−0.767) = −0.233 | g(−0.679) = −0.321 | ≥ 0.05, not a fixed point: **held** |

Q-C, damped iteration Q ← (1 − α)Q + αF(Q) from 0. Convergence requires both
the step and the residual ≤ 1e-8, within 500 iterations. Stability predicts
convergence only for α < 2/(1 − s) ≈ 0.133.

| α | experimental | HF |
|---|---|---|
| 1.0, 0.75, 0.5, 0.25 | not converged | not converged |
| 0.1 | converged in 133, to −0.973740 | converged in 89, to −0.982743 |
| 0.05 | converged in 234, to −0.973740 | converged in 148, to −0.982743 |

All twelve verdicts match the prediction.

- **Mixing moves the path, not the fixed point.** HF, H₂O, NH₃ and CH₄, both
  sets, agree at α = 1 and α = 0.5 to 7.5e-9 e.
- **Conclusion:**
  - a self-consistent LiH charge exists;
  - the printed charge is not one under the adopted reading;
  - plain iteration cannot reach the fixed point, and damping reaches it but
    never the printed value.
- **Still unexplained:** why the paper prints −0.767. Damping is not the
  answer, and it is not added to the solver.

**Water at an author-stated geometry.** Ramachandran et al. 1996 state
0.9572 Å and 104.52° for their QEq water (H 0.353). QEq here gives 0.3532:
**held**. It is the first oracle whose geometry the authors state, rather than
one inferred from a compilation.

**SiH₄.**
- Si–H 1.45–1.51 Å with a D2d distortion of ±5° gives Q_H −0.046 to −0.045
  (experimental) and −0.077 to −0.074 (HF). Geometry cannot reach +0.13:
  **held**.
- Ramachandran's O(SiH₃)₂ QEq hydrogens are negative, and its silicon
  positive.
- **Its Table 3 QEq column** (Si(OH)₄) repeats Table 2's numbers and sums to
  −2.208 e, while all six reference columns sum to zero within 0.001. It is
  internally inconsistent with charge conservation.
- **Its Table 2** conserves charge in all four columns only with 2 × H1 and
  4 × H2.
- **Its citations do not point where its text says.** "Follow the earlier
  work" cites ref 6, a catalysis paper. Aluminium's parameters are cited to the
  1991 paper, whose Table I has no aluminium.
- **Disiloxane at Almenningen et al. 1963's structure**
  (https://doi.org/10.3891/acta.chem.scand.17-2455; Si–H 1.486, Si–O 1.634 Å,
  Si–O–Si 144.1°, O–Si–H 109.9°). Adopted reading, experimental hydrogen set.
  - **Pre-registered.**
    - **Signs: held.** Every H is negative and Si positive, at the reference
      structure, across Si–O–Si 140–180°, Si–O ±0.02 Å and silyl torsion
      0/30/60°.
    - **Magnitudes at the authors' non-firm conformation** (in-plane H nearest
      the 2-fold axis): O −0.6362 (printed −0.636), Si +0.4218 (+0.420) and
      H2 −0.0283 (−0.040) **held**. **H1 FAILED**: −0.0472 against −0.021,
      tolerance ±0.02.
  - **Post hoc, found after H1 failed.** Almenningen's data do not fix the
    conformation. In the other C2v conformation (in-plane H anti, torsion 60°)
    **all four printed values reproduce within 0.002 e**: O −0.6361,
    Si +0.4219, H1 −0.0228, H2 −0.0406.
  - **Post hoc, and not used to choose anything.** O and Si move by under
    0.001 e with torsion, so they compare readings with no conformation choice
    involved. The adopted λ = ½ gives −0.636 / +0.422. The pre-registered
    reading gives −0.624 / +0.388, and no torsion from 0 to 60° or Si–O–Si
    from 140 to 150° brings it within 0.03 e. This is independent support for
    A6 from data that played no part in it.
  - **So:** Rappé's group's 1996 program reproduces, to 0.002 e, as this
    solver with 1991 Table I silicon and λ = ½. That same program would give
    silane hydrogen about −0.045, where the 1991 Table IV prints +0.13. The
    SiH₄ row is inconsistent with the authors' own program under every check
    available. It is still not called a misprint, because the 1991 program
    itself is not available.

**Transcriptions.** Bakowies & Thiel 1996 reprint Table I's H/C/N/O χ and J and
23 comparable Table IV QEqHF cells. All agree with our fixtures, including
formic acid's carbonyl O and acetonitrile's nitrile C, the two label
inferences A4 made.

**Both λ readings are regressions now:** 39 of 76 polyatomic cells
(PREREGISTERED) and 10 of 76 (ADOPTED), cell for cell.

**Papers checked for these problems and not used:**
- **Oda & Hirono 2003:** empirical two-centre terms, no timings. It is not
  evidence about this implementation's speed.
- **Zhang & Fournier 2009:** its "mixing" is an alloy mixing index, not
  charge mixing.
- **Thompson et al. 2002:** charge-model benchmarking, no QEq.
- **Wells et al. 2015:** later variants; misquotes the 1991 hydrogen values.
- **Wilmer et al. 2012:** EQeq, non-iterative.
- **Rappé et al. 1992 (UFF):** prints no QEq parameters.
- **A claim that QuantumATK's QEq uses mixing = 0.5** could not be verified,
  and nothing relies on it.

**Deferred, deliberately:**
- **The bound procedure (O9).** Still deferred; the shipped calculator refuses
  its domain (A8).
- ~~Speed.~~ **Solved under A8**, below.

## QEq stop 2: the bounds (O9)

- **The paper's procedure never releases a fixed atom.** It is: solve; fix
  every atom outside its range at the boundary; solve the rest (eq 13).
- **It misses the constrained optimum in 28 of 200 synthetic systems**:
  symmetric positive-definite matrices, seed 20260914, built so that a bound
  binds.
- **In 26 of the 28, a fixed atom has a gradient pointing back inside**, and a
  feasible charge set with lower energy exists. The worst case is 2.0 e.
- In several of them the paper's literal one pass is the whole procedure, so
  this is not about repeating it.
- **These matrices are not molecules.** Whether a real molecule reaches such a
  case has not been measured.
- The pre-registration does not allow swapping in a proper active-set method
  silently, so this is recorded and goes to Alex.

## Cost

### Before A8 (performance gate B3, 2026-09-14, one Windows machine)

| molecule | atoms with H | EEM, median of 5 | QEq, one run |
|---|---|---|---|
| aspirin | 21 | 0.36 ms | 13.5 s (23 iterations) |
| n-hexadecane | 50 | 1.2 ms | 58 s (18) |
| fentanyl | 53 | 2.0 ms | 77 s (21) |
| atorvastatin | 76 | 4.5 ms | 202 s (26) |

EEM passed the 1 s gate by three orders of magnitude; QEq failed it by two.
Every hydrogen iteration re-evaluated every hydrogen-involving integral, one
pair at a time, by quadrature.

### After A8 (the time gate, `perf.py`, median of 3)

Environment: Windows 11 10.0.26200, Intel64 Family 6 Model 183, Python 3.13.7,
numpy 2.5.1, RDKit 2025.09.6, with another heavy process sharing the CPU.
Structures are frozen in `tests/fixtures/charges/qeq_perf_conformers.csv`, so
their iteration counts differ from B3's.

| molecule | atoms | H % | iterations | Stage 1 (batched quadrature) | Stage 2 (closed form) | gate |
|---|---|---|---|---|---|---|
| aspirin | 21 | 38 | 26 | 0.49–0.75 s | **0.117 s** | ≤ 0.5 s: held |
| fentanyl | 53 | 53 | 17 | 2.8–12 s | **0.114 s** | |
| n-hexadecane | 50 | 68 | 17 | 3.4–12 s | **0.112 s** | |
| atorvastatin | 76 | 46 | 26 | 10–22 s | **0.399 s** | ≤ 5 s: held |

- **Stage 1** kept every node and branch of the scalar routine, and agreed with
  it to 9.8e-15 Ha on the O1 grid and 5.8e-16 Ha on 4000 arguments logged from
  real iterations. Still about 2 million quadrature nodes per iteration, so it
  missed the gate. A mutation using a quarter of the panels was not caught: the
  panel rule is far more conservative than accuracy needs, so node identity is
  not observable by value. That was recorded, not exploited.
- **Stage 2**, the closed form frozen in the A8 note before it was written:
  - within 5.3e-14 Ha of mpmath on all 1076 points;
  - charges on the four structures unchanged from the pre-A8 scalar solver to
    6.5e-14 e, with identical iteration counts;
  - no real molecule reached the quadrature fallback or the series cap.
- **The timings are acceptance measurements on one machine, not a CI test.**
  The numerical gates are in the suite.

## The decisions this needs

0. ~~Adopt R4 (λ = ½, eq 17′) as the reading.~~ **DECIDED 2026-09-14: adopted**
   (amendment A6). With the experimental hydrogen set it reproduces 33 of
   Table IV's 35 polyatomic cells (it misses formamide's C by 0.001 past
   tolerance, and SiH₄) and all of Table III's polyatomics. With the
   HF-fitted set it misses 5 of 35. The record says it was chosen after the
   tables were seen.
1. **The hydrogen treatment.**
   - Ship QEq only for molecules without hydrogen? That is almost nothing
     useful.
   - Or look for Rappé & Goddard's own later clarification? Their references
     9 and 24, "Generalized Mulliken–Pauling Electronegativities", were
     "submitted" and may never have appeared.
   - Or accept a documented reading that does not reproduce Table III?
2. **The bound algorithm.** Keep the paper's never-release fixing, or
   replace it with a true constrained minimum, labelled as a departure from
   the paper.
3. ~~Ethane's source.~~ **Not needed (measured 2026-09-14, A6).** Under R4,
   every structure the 1998 digest prints gives Q_H within ±0.01 e of both
   columns, and the four span 0.005 e, so what Landolt–Börnstein II/7 printed
   cannot change the row.

## Sources looked at for SiH₄, and not useful

- **Rappé et al. 1992, UFF** (https://doi.org/10.1021/ja00051a040): Table I
  holds bond, angle and van der Waals data only. The GMP electronegativities
  are cited to Rappé & Goddard, "submitted", the same unpublished paper as
  the 1991 references 9 and 24.
- The GMP papers themselves have no Crossref record.
