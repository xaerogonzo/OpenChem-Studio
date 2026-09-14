# Rappé–Goddard QEq and Bultinck EEM: pre-registration (2026-09-14)

Written after the sources were transcribed and **before any production solve,
reference integral or oracle has run**. The commit that adds this file
contains no solver code, and git order is the evidence. Anything changed
later is an amendment: it is dated, gets its own section at the end, and
says whether any number had been seen.

The plan behind this is `docs/ROADMAP.md`, "EEM and QEq", DECIDED 2026-09-14.

## 1. Sources and fixtures

| Fixture (`tests/fixtures/charges/`) | Source | SHA-256 (LF line endings) |
|---|---|---|
| `rappe1991_table1.csv` | Rappé & Goddard, J. Phys. Chem. 1991, 95, 3358, Table I | `6b4df78c4edda789dfda2ea3e9a44c011b2534eaa61afde711eb9365b8487057` |
| `rappe1991_table2.csv` | same, Table II | `ae5157ef432612d4e377efa624b76d9ecbe7e5af02ac05c1f994ec144dfcc6d4` |
| `rappe1991_table3.csv` | same, Table III | `eed451b2ddf561d3228d92c777f10e7ac6d519a65fd6394393b6b6ac29a79030` |
| `rappe1991_table4.csv` | same, Table IV (QEq and QEqHF columns) | `6b8e80bd1520d01071041ee12851e1e2e9ad29ec75580a4a856ad95bd6c949f3` |
| `bultinck2002a_table1.csv` | Bultinck et al., J. Phys. Chem. A 2002, 106, 7887, Table 1 | `746f6c66cd334d32b84ec0e6f7cca3822b6d083e65b3fd78f37079f9c9ebb9aa` |
| `geometries.csv` | Huber & Herzberg 1979, X-state r_e | `eaa1b880092da5ce33a7c77c85aa18d991c1a6d5ae88dd3d2afc028886f655a0` |

Every value was checked by eye against its page rendered at 300 dpi
(Huber & Herzberg's rotated tables at 130 dpi). No fixture value comes from a
text layer or a modern database.

**Found while transcribing, before any solver existed:**

- **Oxygen's printed ζ does not follow from its printed radius.**
  - Eq 17 with λ = 0.4913 regenerates the printed ζ to ±0.0001 for 14 of the
    16 elements.
  - Hydrogen needs λ = ½ (eq 17′).
  - O prints ζ 0.9745 beside R 0.669 Å. From that radius, λ = 0.4913 gives
    0.9715 and λ = ½ gives 0.9887. The printed ζ implies R = 0.667 Å.
- **The paper contradicts Table IV twice in its own text**: H₂CO Q_C "0.21" in
  the text against 0.19 in the table, and H₂O Q_H "0.36" against 0.35. The
  tables are the oracle.
- **Table III's footnote a says its numbers are "from eq 23 for χ_H(Q)"**, the
  gradient of eq 23. Section IV's text instead describes solving eq 10 with
  eq 21 and iterating. These differ; see reading R2.
- **One Table IV row has no compound name** (H 0.19 / 0.18, between PH₃ and
  ClH). It is not assigned and no oracle uses it.
- **Harmony et al. 1979 (J. Phys. Chem. Ref. Data 8, 619), the paper's
  polyatomic geometry source, is not held.** The file received as
  `krause1979.pdf` is Krause & Oliver, JPCRD 8, 329, on X-ray line widths.

## 2. Constants

- a₀ = 0.52917 Å, as the paper states under eq 17, for Å → bohr.
- 1 hartree = 27.211386 eV.
- So the large-R limit is 27.211386 × 0.52917 = 14.39945 eV·Å, against the
  paper's rounded 14.4 in eq 14. **No constant is tuned.**

## 3. QEq: the system, and the readings the paper leaves open

**The system.** Equations 7–9 are equivalent to eqs 10–12, which eliminate μ by
subtracting row 1. With Σ_j C_ij Q_j − μ = −χ_i and Σ_i Q_i = Q_tot:
- C_ii = J_i (Table I). For H it is the self term of the chosen reading R2.
- C_ij (i ≠ j) = the Coulomb integral between the normalised ns Slater
  densities ρ(r) = (2ζ)^(2n+1) r^(2n−2) e^(−2ζr) / (4π (2n)!) (eq 15), in
  hartree at R in bohr, then × 27.211386 to eV.
- **−χ on the right**, the sign `qeq.cpp` gets wrong (#99).

**Code names.** `hardness_diag_H(Q)` is hydrogen's diagonal self term.
`coulomb_pair(i, j)` is any two-centre integral, H–H included. The paper's J
appears only in comments.

**Four readings are fixed now.** P is the primary combination. Each alternate
is run **one at a time**, with everything else held at P. The 16-way factorial
is not searched.

| | Question the paper leaves open | P (primary) | Alternate | Why P |
|---|---|---|---|---|
| R1 | Does ζ_H(Q) (eq 20) enter the off-diagonal integrals? | **Yes**: every `coulomb_pair` involving H uses ζ° + Q_H, each H its own | No: `coulomb_pair` keeps ζ° = 1.0698 | Eq 17's paragraph: "The diatomic Coulomb integral J_AB involving these Slater functions is evaluated exactly for ζ_A and ζ_B", and eq 20 makes ζ_H charge-dependent |
| R2 | Hydrogen's self term | **Eq 21 in the linear system**: `hardness_diag_H` = J°_H (1 + Q_prev/ζ°), with ζ° = 1.0698, iterated | **Eq 23's gradient** (Table III footnote a): the stationarity of χ°Q + ½J°Q²(1 + Q/1.0698) is χ° + J°Q + (3/2)J°Q²/1.0698. It is iterated as a diagonal J°(1 + 1.5 Q_prev/1.0698), whose fixed point satisfies that gradient exactly | Section IV's paragraph on how the equations are *solved*: "In solving (10) using (21), we use (20) with an estimated Q_H and iterate" |
| R3 | O's ζ | **Printed ζ = 0.9745** | ζ from printed R by eq 17: 0.9715 | ζ is the quantity eq 15 uses; the radius only produced it |
| R4 | λ for Tables III and IV | **Table I's ζ as printed** (heavy atoms λ = 0.4913, H λ = ½) | eq 17′ for every element (λ = ½ from R; O from R too) | Section V says the calculations used "the electronegativities, idempotentials, and atomic radii in Table I"; Table II separates the λ columns explicitly |

Hydrogen sets: QEq (χ° 4.5280, J° 13.8904) and QEqHF (χ° 4.7174, J° 13.4725).
Eq 21 and eq 23 use ζ° = 1.0698 for both sets.

**A pass by an alternate while P fails is a question for Alex, not a
validation, and P is never replaced because an alternate fits.**

## 4. QEq: bounds, the hydrogen loop, convergence

**Bounds.** Eq 5 prints −7 < Q_Li < +1, −4 < Q_C < +4, −2 < Q_O < +6, "etc.", and
eq 5′ gives −1 < Q_H < +1.
- For other elements the rule is **derived** as −(8 − v) ≤ Q ≤ v, with v the
  valence electron count: Li, Na, K, Rb, Cs 1; C, Si 4; N, P 5; O, S 6;
  F, Cl, Br, I 7.
- A test checks the derivation reproduces the three printed ranges.
- An atom is fixed **at** the boundary it crossed, as the paper says.

**Order of operations** (the paper does not say how the two loops combine):
- **Outer loop, hydrogen self-consistency.** Iteration k builds ζ_H and
  `hardness_diag_H` from Q⁽ᵏ⁻¹⁾, starting from Q⁽⁰⁾ = 0 (the paper's initial
  guess).
- **Inner, a complete active-set solve** with those parameters fixed:
  1. Solve with no atom fixed.
  2. Every free atom outside its bound is fixed at that bound.
  3. The fixed atoms' Σ_B J_AB Q_B moves to the right-hand side, and their
     charge leaves the total (eq 13).
  4. Re-solve the reduced system.
  5. Repeat until no free atom is outside its bound.
  - Atoms are never released.
  - **The active set is rebuilt from nothing in every outer iteration.**
- A hydrogen fixed at a bound feeds its bound value into the next update.
- **Convergence requires all four**, within 50 outer iterations:
  - max|ΔQ_H| ≤ 1e-8 e;
  - max|Δζ_H| ≤ 1e-8 bohr⁻¹;
  - max|Δ`hardness_diag_H`| ≤ 1e-8 eV;
  - the same active set in the last two outer iterations.
  - A molecule with no hydrogen converges in one outer iteration by definition.
- **Otherwise the result is `NOT_CONVERGED`**, with no charges and a trace
  class: `oscillating` if ΔQ_H changes sign in 3 of the last 4 iterations,
  `stalled` if max|ΔQ_H| fell by less than 10 % over the last 5, `monotone`
  otherwise.
- **The paper describes one fixing pass**, so any inner loop needing a second
  sets `bound_extension_used`. The algorithm is recorded as
  `rappe_eq13_repeated_active_set`.
- **The trace keeps a row per (outer iteration, inner pass)**: the active set,
  the fixed atoms with their bounds, and the three H deltas.

## 5. The Slater Coulomb integral

**Production (numpy, `coulomb_pair_integral`).** Position space, spherical
shells.
- a = 2ζ.
- Enclosed charge: Qₑ(r) = P(2n+1, ar), with P the regularised lower
  incomplete gamma function.
- Potential: V(r) = Qₑ(r)/r + (a/2n)·Γᵤ(2n, ar), with Γᵤ the regularised upper
  incomplete gamma function.
- W(r) = ∫₀ʳ V(t) t dt, in closed form as finite sums of the same functions.
- Shell average: ⟨V_a⟩(s, R) = [W(R+s) − W(|R−s|)] / (2sR).
- **Near-zero branch.** When min(s,R)/max(s,R) < 1e-3:
  - ⟨V_a⟩ = V_a(R) − (2π/3) s² ρ_a(R) if s is the small one, or
    V_a(s) − (2π/3) R² ρ_a(s) if R is. This is the mean-value expansion with
    ∇²V = −4πρ.
  - ⟨V_a⟩ = V_a(s) exactly at R = 0.
  - A counter records every use of the branch.
- **Incomplete gamma functions** use the series form wherever x < m + 1, so
  that 1 − e^(−x)Σ… never cancels.
- **The s integral** ∫₀^∞ 4πs² ρ_b(s) ⟨V_a⟩(s,R) ds is split at s = R:
  - [0, R]: composite Gauss–Legendre, 32 points per panel, panel width
    ≤ 1/a_b;
  - [R, ∞): 64-point Gauss–Laguerre in t = a_b(s − R).
- **Internal convergence check, not an oracle.** Doubling both orders over the
  O1 grid must change no value by more than 1e-12 Ha.
  - If it fails, the orders are raised, and that is recorded as an amendment
    **before** any comparison with the oracles below.

**Oracle 1 (test code; no production import).** Momentum space.
- F(k) = ∫ρ(r) e^(−ik·r) d³r = a^(2n+1) sin(2nθ) / (2n k (a² + k²)ⁿ), with
  θ = atan(k/a).
  - Derivation: ∫₀^∞ r^m e^(−ar) sin(kr) dr = m! sin((m+1)θ) / (a²+k²)^((m+1)/2),
    with m = 2n − 1 and the normalisation 4πN² = a^(2n+1)/(2n)!.
  - F(0) = 1.
- J(R) = (2π)⁻³ ∫ F_a F_b (4π/k²) e^(ik·R) d³k = (2/π) ∫₀^∞ F_a F_b sin(kR)/(kR) dk.
  - Setting F = 1 gives 1/R, which checks the normalisation.
- **Checks:**
  - F(0) = 1 to 1e-14 for every density on the grid;
  - F against direct radial quadrature at k = 0.1, 1, 3, 10 and 30 (to 1e-12);
  - the 1/R check at three values of R.
- **Quadrature:** composite Gauss–Legendre, 32 points per panel. Panel width is
  min(π/R, min(a_a, a_b)/4), summed until the envelope |F_a F_b|/(kR) at a
  panel's end is below 1e-15. The alternating remainder bound is reported
  with each value.

**Oracle 2 (frozen table, `slater_reference.csv`).** Generated once by
`integrals_mpmath.py`:
- Python 3.13.7, mpmath (version recorded in the file header), `mp.dps = 30`,
  run in a throwaway venv.
- R ≥ 0.05 bohr: J = ∫ρ_b V_a d³r in prolate-spheroidal coordinates
  (ξ, η), with V_a from mpmath's own `gammainc`.
- R < 0.05 bohr: the same integral in spherical coordinates about A, 2D in
  (r, μ), split at r = R.
- R = 0: the one-centre radial integral.
- **Both 2D methods also run at R = 0.05 and 0.2 bohr**, and must agree to
  1e-14 Ha before the table is written.
- The header records the Python and mpmath versions, dps, the script's
  SHA-256, and the date.
- **Tests never regenerate the table.**

**Roothaan closed form, 1s–1s with equal ζ:**
J = 1/R − e^(−2ζR) (1/R + 11ζ/8 + 3ζ²R/4 + ζ³R²/6). Its R → 0 limit is 5ζ/8.

**The O1 grid:**
- **n pairs:** all 21 unordered (n_a ≤ n_b), n = 1–6.
- **ζ per n pair:**
  - (i) ζ_a = ζ_b = 1.0;
  - (ii) ζ_a = 0.4174, ζ_b = 1.0726;
  - (iii) ζ_a = 1.0726, ζ_b = 0.4174.
- **Hydrogen cases (n_a = 1):** ζ_a ∈ {0.0698, 0.5698, 1.0698, 1.5698, 2.0698}
  (ζ_H at Q = −1, −0.5, 0, +0.5, +1), against n_b = 2 with ζ_b 0.8563 and
  0.9745, and against n_b = 1 with ζ_b 1.0698 and with ζ_b = ζ_a.
- **R in Å:** 0.2, 0.2961, 0.4385, 0.6492, 0.9613, 1.4234, 2.1076, 3.1207,
  4.6207, 6.8418, 10.1305, 15.0.
- **Near-zero R in bohr:** 0, 1e-6, 1e-4, 5e-4, 9.99e-4, 1.001e-3, 2e-3, 1e-2.
  These run for the n pairs (1,1), (1,2), (2,2), (3,5) and (6,6), with ζ
  combinations (i) and (ii).
  - The near-zero branch counter must be non-zero for the R < 1e-3 values, and
    not every node may hit the branch at R ≥ 1e-3.

## 6. EEM (Bultinck 2002 part I)

**The system.** Eq 3 (p. 7888), read from the rendered page:
- diagonal **2η\***;
- off-diagonal 1/R_αβ;
- last column −1, last row the charge constraint;
- right-hand side −χ\* and the total charge.

**Published vs. solver values:**
- The fixture stores the published η\*.
- The solver's diagonal coefficient is 2η\*, per eq 2 and eq 3.

**Units.** Eq 2 carries no conversion constant, so it is dimensionally
consistent in atomic units only. The paper converts "8.5 eV (0.3124 au)"
(p. 7889).
- χ\* and η\* ÷ 27.211386 give hartree; R is in bohr.
- Working in eV with 14.39945/R_Å gives identical charges up to rounding of
  the constants, so this is not an open reading.
- **The recorded convention is `bultinck2002_eq3_atomic_units`**, with κ = 1
  (hartree·bohr).

**Elements.** Only H, C, N, O and F are parameterised; anything else is
refused.

**O7 closed form (diatomic), from eq 3:**
q₁ = [χ₂ − χ₁ + (2η₂ − 1/R) Q] / (2η₁ + 2η₂ − 2/R).
- A variant built with η in place of 2η must **fail** the same assertion.
- Fixtures for O7 and O8 must have a condition number below 1e3, recorded.

## 7. Oracles and tolerances

| # | Kind | Oracle | Tolerance |
|---|---|---|---|
| O1 | math | Production against oracle 1 and oracle 2 over the §5 grid; Roothaan; J(a,b) = J(b,a); J·R → 1 at 15 Å and beyond | ≤ 1e-9 Ha, and the same bound in eV |
| O2 | transcription | Eq 17 regenerates Table I's ζ | ±0.0001 au for 15 elements; **O is the recorded exception** (§1) and is not a failure of O2 |
| O3 | literature | Table II: the general solver at Huber r_e against the printed Q_QEq (Table I ζ) and against Q_λ=0.5 (eq 17′ ζ from R), for all 20 molecules. **Separately**, eq 18 evaluated from the fixture with oracle 1's integral against the general solver | printed ±0.001 e; eq 18 vs solver ≤ 1e-8 e (amended from the plan's 1e-9 before any run: an O1-sized integral difference moves Q by up to ~1e-8 e through eq 18's denominator) |
| O4 | literature | Table III, QEq and QEqHF columns. HF and LiH now; H₂O, NH₃, CH₄ when Harmony is held | ±0.001 e diatomic, ±0.002 e polyatomic |
| O5 | literature | Table IV, QEq and QEqHF columns. HF and ClH now; every other printed atom when Harmony is held. Duplicate labels (§ fixture header) are assigned by an inference stated in the test | ±0.01 e |
| O6 | compatibility only | `eem_charges` against Open Babel's EEM, fed a temporary `eem.txt` of Table 1 converted to hartree with the diagonal as 2η\*. **Establishes nothing about Bultinck** | ≤ 1e-6 e |
| O7 | literature / convention | §6 closed form against `eem_charges`; the η-for-2η variant fails | ≤ 1e-12 e |
| O8 | math | A hand-built 3-atom EEM matrix: shape (4×4), diagonal, off-diagonal, RHS signs, and the constraint row and multiplier column in place (a transposed build must fail), then the charges | ≤ 1e-12 |
| O9 | math | 200 synthetic bounded systems (numpy seed 20260914, N = 3–6, symmetric positive-definite C, χ scaled so that at least one bound binds; **the construction is in the test**): (i) the §4 active-set solve against brute-force KKT enumeration of every free/lower/upper assignment; (ii) solve-once-then-clip-and-renormalise differs from the optimum in at least one case | (i) all 200 agree ≤ 1e-10 e; (ii) some case differs > 1e-3 e |
| B | benchmark | With Gaussian integrals and constant H substituted, the solve core against −(Open Babel QEq) on neutral molecules | ≤ 1e-5 e, reported, not a gate |

**Invariants** (not literature):
- **Shift invariance:** adding a constant to every χ leaves every charge
  unchanged, for EEM and for QEq while no bound is active.
- **Conservation:** Σq = Q_tot to 1e-10. This is necessary but not sufficient.
- **Net charge:** neutral, +1 and −1 all run, and changing only Q_tot changes
  the charges.
- **Permutation:** permuting atoms and coordinates together gives
  q′[P(i)] = q[i] to 1e-12, for both solvers.
- **R1 isolation:** at identical hydrogen charges, the P and R1-alternate
  matrices are bit-identical except off-diagonal entries involving an H, and
  identical everywhere when every Q_H = 0.
- **Hydrogen sets:** on HF, QEq and QEqHF both converge and their charges
  differ by more than 1e-6 e. The observed difference is printed as a datum.
- **No extension in validation:** no O3–O5 molecule sets
  `bound_extension_used`, and whether any bound activates is printed.

## 8. Stop rule and gate

- **O1, O2 (beyond the recorded O), O3, O8 or O9 fails:** stop and investigate.
  λ and the parameters are never tuned.
- **O9(i) disagrees on any case:** the §4 algorithm is not an optimum finder
  for that case. Stop and bring it to Alex; the algorithm is not swapped
  silently.
- **O4 or O5 fails on P:** report P and the four one-at-a-time alternates side
  by side, and bring it to Alex.
- **QEq does not ship until O4 and O5 have run on the Harmony polyatomics.**
  Phase A still finishes on the diatomics.
- **EEM ships on O7 and O8** with the transcription verified. O6 is reported
  beside them.

## Amendments

### A1 (2026-09-14, before any production code or reference value existed)

- **EEM's Bohr radius.** Section 6 says "R is in bohr" without naming a₀, and
  section 2's 0.52917 Å is Rappé & Goddard's own value, stated in their paper.
  Bultinck part I states none.
  - EEM therefore uses CODATA 2018, a₀ = 0.529177210903 Å.
  - O6's Open Babel κ = 0.529176 differs from it by 2e-6 relative, which is
    far inside O6's 1e-6 e on these molecules.
  - QEq keeps 0.52917.

### A2 (2026-09-14, before any oracle had produced a number)

- **`rappe1991_table4.csv`'s hash was taken over the file's CRLF bytes**,
  against this document's own "LF line endings" rule. It is replaced by the
  LF hash.
- The content is unchanged: the committed blob normalised to LF hashes to the
  new value.
- Found by the fixture-hash test, the first test to run. Nothing had been
  solved against a literature table.

### A3 (2026-09-14, AFTER the oracles had run -- disclosed as such)

- **O2's ±0.0001 au failed for N**, by 2.5e-5: eq 17 gives 0.90903 against the
  printed 0.9089.
- **The tolerance was an arithmetic error in this document.** R is printed to
  0.001 Å, so the printed ζ can differ from eq 17 applied to the printed R by
  up to ζ·0.0005/R + 0.00005. That is 6.9e-4 for N.
- **The pre-registered check is kept and marked as an expected failure for N.**
  A second check applies the rounding bound. It passes for 15 elements, and
  oxygen's 0.0030 is more than three times its bound, so oxygen's exception
  stands and is not rounding.
- No charge depends on this: the solver uses the printed ζ.

