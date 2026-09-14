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
  Alex's. QEq could not have shipped yet anyway, because the polyatomic
  oracles need Harmony et al. 1979, which is not held.

| # | Oracle | Result |
|---|---|---|
| O1 | Slater integrals against momentum space, over 1076 grid points | worst 1e-9 eV or better, passes |
| O1 | against the 30-digit mpmath table (1076 rows; its two coordinate systems agree to 1.8e-22 Ha) | **worst 5.2e-14 Ha**, at the near-zero point R = 1e-6 bohr; passes |
| O2 | eq 17 regenerates Table I's ζ | 14 elements within ±0.0001; **N misses by 2.5e-5**, within the rounding of its printed radius (amendment A3); **O misses by 0.0030**, four times its rounding, recorded before any solve |
| O3 | Table II, 20 alkali halides, both λ columns | **passes: worst 0.0005 e** in each column, and eq 18 agrees with the general solver to 1e-8 e |
| O4 | Table III hydrogen charges | **STOP**: HF misses (below); LiH never converges |
| O5 | Table IV, the diatomics HF and ClH | pass at ±0.01 e |
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
- **What it could be, unmeasured:** the paper's hydrogen procedure may differ
  from both readings of section IV and Table III's footnote. Candidates are an
  undamped iteration that differs in some other detail, or ζ_H entering eq 21
  in some other way. The paper gives no more than it gives.

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

## Cost (performance gate B3, 2026-09-14, one Windows machine)

| molecule | atoms with H | EEM, median of 5 | QEq, one run |
|---|---|---|---|
| aspirin | 21 | 0.36 ms | 13.5 s (23 iterations) |
| n-hexadecane | 50 | 1.2 ms | 58 s (18) |
| fentanyl | 53 | 2.0 ms | 77 s (21) |
| atorvastatin | 76 | 4.5 ms | 202 s (26) |

**EEM passes the 1 s gate by three orders of magnitude.**

**QEq would fail it by two**, even if its oracles passed. Every hydrogen
iteration re-evaluates every integral that involves a hydrogen, one pair at
a time, at about 4 ms per integral. The integral cache the plan allows would
not help here, because ζ_H changes on every iteration. Shipping QEq would
first need the pair integrals vectorized across pairs, at the same O1
accuracy.

## The decisions this needs

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
3. **Harmony et al. 1979** (J. Phys. Chem. Ref. Data 8, 619) is still needed
   for any polyatomic oracle. The file received as `krause1979.pdf` is a
   different paper.
