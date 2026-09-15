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
- **QEq stopped at the pre-registered stop rule, twice** (O4 hydrogen, O9
  bounds). The decisions that followed are A6, A8 and A9, below.
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
- ~~The bound procedure (O9).~~ **Studied under A9**, below: on a 174-molecule
  corpus the paper's procedure is the constrained optimum everywhere, and the
  one bound activation is a non-convex runaway that A8 refuses.
- ~~Speed.~~ **Solved under A8**, below.

## Amendment A9: the bound procedure on a real corpus (2026-09-14)

Pre-registered in A9 before any output: `tests/qeq_bounded_qp.py` (the QP),
`build_o9_corpus.py` (the frozen corpus) and `o9_study.py`, whose per-molecule
table is `o9_study.csv`. The corpus is the naming benchmark restricted to
Table I elements: 174 molecules, 22 categories, including 11 polycharged
species. Adopted reading, experimental hydrogen set.

**The QP is checked before it judges anything, in A9's order.**
1. With no bound active it equals the unconstrained solve.
2. It equals the brute-force KKT optimum on all 200 synthetic systems
   (3.6e-15 e) and on the one real bound-active matrix.
3. It equals the paper's procedure wherever that procedure is optimal (172 of
   the 200 synthetic systems).

Disabling its release step turns the tests red.

**On the corpus:**

| | molecules |
|---|---|
| converged | 173 of 174 (methanediylium, CH₂²⁺, does not) |
| a bound touched at any pass | 1 |
| a bound active in the final solution | 1: propane-1,3-diide, two H held at −1 |
| paper's procedure not KKT-optimal | **0** |
| largest paper − optimum difference | 1.1e-16 e (floating point) |
| QEq matrix not convex on Σq = Q | 1: the same propane-1,3-diide (tangent eigenvalue −0.24; median over the rest +1.37) |

**What it means.**
- The paper's never-release fixing, which misses the optimum in 28 of 200
  synthetic systems built to bind, is the true constrained minimum on every
  converged molecule of this corpus.
- **The one bound activation happened exactly where the QEq energy has no
  minimum without the bounds.** Propane-1,3-diide's matrix is not convex on the
  charge-conserving plane, so its charges run away until the bounds stop them.
- Brute force over all 3⁹ assignments finds a single KKT point: the global
  constrained minimum. The paper, the QP and brute force agree on it.
- That answer puts the dianion's charge on two hydrogens (−1 each), with the
  carbanion carbons near −0.16. It is the bounds' answer, not chemistry's.
  A8's refusal is what keeps it from a user.
- **So the data do not argue for replacing the paper's procedure.** Where
  bounds bind in practice, they bind because the model has left its valid
  domain, and a better optimiser would return a more exact version of an
  unphysical answer. The refusal stays.
- **Scope of the conclusion:** one corpus of 174 small molecules, 11 of them
  polycharged. A larger or more ionic set could find a convex bound-active
  case, where the paper's procedure and the optimum might differ. The QP and
  the study script are in place for that.

## Amendment A10: repeating the paper's hydrogen fit (2026-09-14/15)

**The question.** Rappé & Goddard fitted hydrogen's χ and J to five molecules:
- HF, H₂O, NH₃ and CH₄ at weight 1, except CH₄ at 5;
- LiH at weight 0.2 (section IV and ref 20);
- once to the experimental charges, giving (4.5280, 13.8904), and once to HF
  charges, giving (4.7174, 13.4725).

Refitting under a candidate reading tests whether that reading can reproduce
the published fit. The readings tested:
- **V0:** the shipped model;
- **H-a6 to H-a10:** k plain iterations from zero;
- **H-b:** eq 23's gradient;
- **H-c:** ζ° fixed in the pair integrals;
- **H-d:** H-c with cheq's ±0.95 clamp.

All were pre-registered in A10, with three corrections disclosed before any
output. The LiH HF target is Cioslowski's PRL 1989 APT value, −0.6819.

**The run.** `hydrogen_refit.py`, one JSON per job in `hydrogen_refit_jobs/`,
summaries in `hydrogen_refit*.csv`.
- **Jobs: 18 expected / 18 complete / 0 failed / 0 not run.**
- **Symmetry check passed everywhere.** The spread at every reported point is
  ≤ 1.1e-16 e. The largest spread seen anywhere in V0's control is 6.1e-10:
  the noise that crashed the first run, and harmless.
- **Geometry symmetry** is exact to 4e-14°.

| variant | column | S at printed pair | LiH residual there | refit (χ, J) | refit − printed | rounding envelope | verdict |
|---|---|---|---|---|---|---|---|
| V0 | experimental | 0.01216 | -0.206 | (4.4845, 14.2602) | (-0.0435, +0.3698) | (±0.0056, ±0.0207) | UNEXPLAINED |
| V0 | hf | 0.03075 | -0.301 | (4.8644, 12.3662) | (+0.1470, -1.1063) | (±0.0045, ±0.0181) | UNEXPLAINED |
| H-a6 | experimental | 0.03048 | 0.367 | (4.6026, 13.6853) | (+0.0746, -0.2051) | (±0.0015, ±0.0058) | UNEXPLAINED |
| H-a6 | hf | 0.01440 | -0.093 | (4.6767, 13.2256) | (-0.0407, -0.2469) | (±0.0021, ±0.0083) | UNEXPLAINED |
| H-a7 | experimental | 0.02426 | 0.320 | (4.5803, 13.8206) | (+0.0523, -0.0698) | (±0.0015, ±0.0058) | UNEXPLAINED |
| H-a7 | hf | 0.03288 | -0.318 | (4.6464, 13.4050) | (-0.0710, -0.0675) | (±0.0045, ±0.0182) | UNEXPLAINED |
| H-a8 | experimental | 0.01492 | 0.237 | (4.5615, 13.9052) | (+0.0335, +0.0148) | (±0.0015, ±0.0058) | UNEXPLAINED |
| H-a8 | hf | 0.01439 | -0.093 | (4.8799, 12.1760) | (+0.1625, -1.2965) | (±0.0021, ±0.0083) | UNEXPLAINED |
| H-a9 | experimental | 0.00371 | 0.005 | (4.5489, 13.9715) | (+0.0209, +0.0811) | (±0.0015, ±0.0058) | UNEXPLAINED |
| H-a9 | hf | 0.03288 | -0.318 | (4.6460, 13.4033) | (-0.0714, -0.0692) | (±0.0045, ±0.0184) | UNEXPLAINED |
| H-a10 | experimental | 0.01445 | -0.232 | (4.5388, 14.0198) | (+0.0108, +0.1294) | (±0.0052, ±0.0187) | UNEXPLAINED |
| H-a10 | hf | 0.01439 | -0.093 | (4.7555, 12.9512) | (+0.0381, -0.5213) | (±0.0021, ±0.0083) | UNEXPLAINED |
| H-b | experimental | +∞ | no Q_H | none: every one of 3,804 evaluations is +∞ | — | — | UNEXPLAINED |
| H-b | hf | +∞ | no Q_H | none: every one of 3,804 evaluations is +∞ | — | — | UNEXPLAINED |
| H-c | experimental | +∞ | no Q_H | none: every one of 3,804 evaluations is +∞ | — | — | UNEXPLAINED |
| H-c | hf | +∞ | no Q_H | none: every one of 3,804 evaluations is +∞ | — | — | UNEXPLAINED |
| H-d | experimental | +∞ | no Q_H | none: every one of 3,804 evaluations is +∞ | — | — | UNEXPLAINED |
| H-d | hf | +∞ | no Q_H | none: every one of 3,804 evaluations is +∞ | — | — | UNEXPLAINED |

**Verdict: every tested reading is UNEXPLAINED.** Under the documented fit
protocol, neither published hydrogen pair is reproduced by the shipped
equations or by any of the eight other readings. This is A10's pre-registered
statement, and it is not softened.

**What the numbers say.**
- **V0 is not the 1991 program, and the miss is far outside rounding.**
  - Refitting the experimental column moves J by +0.37 eV against a rounding
    envelope of ±0.021.
  - Refitting the HF column moves χ by +0.147 and J by −1.106.
  - At the printed experimental pair, every V0 cell except LiH is within O4's
    tolerance. LiH is off by −0.207, because V0's only self-consistent LiH
    charge is −0.974 (A7).
  - The refit cannot absorb LiH either: its best residual is still −0.20 at a
    weight of 0.2.
  - **The experimental refit sits on a boundary, not at an interior minimum**
    (measured after the run, on the job file's full-precision pair).
    - Raising J by 1e-3 eV, or lowering χ by 1e-4, gives LiH two more
      bound-free self-consistent charges (near −0.35). A10's uniqueness rule
      then makes S infinite.
    - The optimiser stopped where the rule does, so +0.37 eV is the smallest
      move that still keeps one LiH charge, not the free optimum.
    - The HF-column refit is interior: all four perturbations keep every
      charge unique.
  - The objective surface is a long valley, with elongation 11–13.
  - **A refit that wanders along a valley is expected of charge-only fits.**
    Verstraelen et al. 2011 (`verstraelen2011`) find the least-squares
    objective on atomic charges "in general ill-conditioned" for EEM and SQE
    parameters. That is context for why a refit need not land on one pair; it
    changes none of A10's verdicts.
- **The same pattern holds for truncated iteration.** No k gives a refit
  inside its envelope in either column. H-a9's experimental column is the
  closest (S = 0.0037 at the printed pair) but still moves J by +0.081 against
  ±0.006.
- **H-b, H-c and H-d have no charge to fit.**
  - At the printed pairs, LiH has **no** bound-free self-consistent charge
    under any of them. Under H-c, water, ammonia and methane each have two; under
    H-d, ammonia and methane do.
  - Across the whole box, every evaluation is +∞. All 200 control draws fail
    at generation.
  - As defined, those readings cannot be the 1991 program.
- **Ordering.** At the printed pairs, V0 and H-a6–H-a9 invert the paper's
  QEq − QEqHF sign for 3 of the 5 molecules, and H-a10 for 2. The HF-fitted
  set's inversion (O4) is therefore not a rounding effect.

**Post hoc, and not used for anything.** H-a9 at the printed experimental pair
puts LiH at −0.7632, 0.004 from the printed −0.767. That looks suggestive, but:
- the same nine iterations put LiH at the −1 bound in the HF column;
- the refit leaves its envelope;
- the stop rule forbids adding a variant around it;
- the map oscillates with slope −14 (A7), so some iterate lands near any value
  in its range.

It is recorded here so nobody rediscovers it as a finding.

**What changes.** Nothing shipped changes: QEq stays under A8, with the
experimental set only and LiH refused. The HF-fitted set stays unoffered, and
now has a measured reason beyond O4: no tested reading reproduces its fit.
- **Still unexplained:** what the 1991 program did for hydrogen.
- **What was ruled out:** eight readings.
- **Checked since:** the LiH geometry route, amendment A11 below. Cioslowski's
  geometry is reproduced, and it does not explain the miss.

## Amendment A11: Cioslowski's LiH geometry (2026-09-15)

Pre-registered after A10's output, and disclosed as such. Code:
`cioslowski_apt.py` (analysis, and the ORCA run) and `cioslowski_apt_psi4.py`
(the Psi4 run). Fixtures: `cioslowski_lih_psi4.csv` for A and
`cioslowski_lih_orca.csv` for B.

**Experiment A, the historical reproduction: PASSED.** ORCA 6.1.1 cannot use
Cartesian d functions, so A ran in Psi4 1.11, with Alex's approval, in a
throwaway conda environment.
- **Cross-check first:** Psi4's spherical LiH single point equals ORCA's to
  1e-10 hartree.
- **Geometry:** with Cartesian d, RHF/6-31++G(d,p) optimises LiH to
  **1.632817 Å**.
- **Charge:** the trace charge (eq 9) is **Li +0.681846** at every h from
  0.0005 to 0.004 Å, agreeing to 1e-6. Cioslowski prints +0.6819, a
  difference of 5e-5, inside A11's ±0.0005.
- **The trace matters:** the axial derivative alone would give 0.48.

**Experiment B, spherical d in ORCA (a diagnostic):** 1.63279 Å and +0.68215,
2.5e-4 away. The 4-31G cross-check is not run, because ORCA has no built-in
4-31G.

**H-e, run because A passed:** A10's V0 refit of the HF column, with LiH at
1.632817 Å (A10 used Huber's 1.5957) and every other molecule unchanged. The
output is in `hydrogen_refit_he/`: 1 of 1 jobs complete, symmetry check passed.

| | V0 (LiH at 1.5957 Å) | H-e (LiH at 1.632817 Å) |
|---|---|---|
| LiH Q_H at the printed HF pair | −0.9827 | −0.9826 |
| LiH against the paper's QEqHF (−0.679) | −0.3037 | −0.3036 |
| S at the printed pair | 0.030747 | 0.030730 |
| refit (χ, J) | (4.8644, 12.3662) | (4.8642, 12.3673) |
| refit − printed | (+0.147, −1.106) | (+0.147, −1.105) |
| inside the rounding envelope? | no | no |
| program check at the printed pair | fails | fails |

**What it means.**
- **Cioslowski's −0.682 target is understood exactly:** its definition, level
  of theory and geometry are all reproduced.
- **Its 0.037 Å longer bond changes nothing that matters.** LiH's
  self-consistent charge moves by 1e-4, and the refit moves by ≤ 0.001 eV.
- **So geometry does not explain LiH or the HF-fitted set;** the difference
  lies in the hydrogen treatment, as A10 already showed.
- **Classification:** H-e fits one column, so A10's two-column classification
  gives no verdict ("NO VERDICT" in its CSV). That column meets neither of
  A10's conditions: its refit is outside the envelope, and it fails the
  program check.

## Amendment A12: Table IV geometry sensitivity (2026-09-15)

A diagnostic, pre-registered after A10's output; nothing is adopted.
`table_iv_geometry.py`; outputs `table_iv_geometry.csv` (500 evaluations, all
converged) and `table_iv_geometry_summary.csv`.
- **Grid:** one internal coordinate at a time, ±0.005/±0.010 Å on every bond
  and ±0.5/±1.0° on every angle (plus methanol's H–O–C–H torsion), applied as
  fixed Cartesian operations on each Harmony structure type.
- **Side effects:** coupled angles in planar formamide and around the methyl
  group move with their neighbour, and each one is listed in the CSV.

| cell (adopted reading) | base | printed | nominal | range over grid | closest | class |
|---|---|---|---|---|---|---|
| formamide C, QEq | substitution | 0.39 | 0.4011 | 0.3994 – 0.4027 | 0.0094 away (C–N–H1 −1°) | **geometry-compatible** |
| formamide N, QEqHF | substitution | −0.61 | −0.6233 | −0.6246 – −0.6220 | 0.0120 | geometry-insensitive |
| methanol H(O), QEqHF | substitution | 0.34 | 0.3561 | 0.3535 – 0.3586 | 0.0135 | geometry-insensitive |
| methanol C, QEqHF | substitution | −0.09 | −0.1040 | −0.1080 – −0.1000 | 0.0100 | geometry-insensitive |
| methanol Ht, QEqHF | substitution | 0.16 | 0.1737 | 0.1709 – 0.1766 | 0.0109 | geometry-insensitive |
| methanol H(O), QEqHF | effective | 0.34 | 0.3608 | 0.3583 – 0.3633 | 0.0183 | geometry-insensitive |
| methanol C, QEqHF | effective | −0.09 | −0.1065 | −0.1105 – −0.1025 | 0.0125 | geometry-insensitive |
| methanol Ht, QEqHF | effective | 0.16 | 0.1747 | 0.1718 – 0.1775 | 0.0118 | geometry-insensitive |

**What it means.**
- **Formamide's C was 0.001 past tolerance, and a one-degree angle change
  closes that.** That is all "geometry-compatible" can say. It does not
  explain the miss.
- **The four QEqHF cells cannot reach tolerance within the grid,** and each
  moves by less than 0.01 across it. Their misses are not a geometry effect of
  this size, which is consistent with A10: the HF-fitted set's problem is in
  the hydrogen treatment.
- Methanol C at the substitution structure reaches 0.010011 in its closest
  case, missing tolerance by 1.1e-5.

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
- **These matrices are not molecules.** At the time, whether a real molecule
  reaches such a case had not been measured.
- The pre-registration does not allow swapping in a proper active-set method
  silently, so this was recorded for a decision.
- **Measured since (A9, above):** on 174 real molecules the paper's procedure
  is the constrained optimum on every converged one. The procedure and A8's
  refusal of a final active bound both stay.

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
1. ~~The hydrogen treatment.~~ **DECIDED 2026-09-14 (A8):** ship the
   experimental hydrogen set under a stated scope, refuse LiH-like cases, and
   leave the HF-fitted set unoffered. Rappé & Goddard's "submitted" references
   9 and 24 were looked for and have no record (below). A10–A12 later tested
   why the hydrogen fit does not come back; it is still unexplained.
2. ~~The bound algorithm.~~ **DECIDED 2026-09-14 (A9):** keep the paper's
   never-release fixing. On a real corpus it is the constrained optimum
   everywhere, and the one bound activation is a non-convex case A8 refuses.
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
