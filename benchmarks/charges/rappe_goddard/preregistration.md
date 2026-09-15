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
| `harmony1979_structures.csv` | Harmony et al. 1979, every printed parameter of 15 molecules (added by amendment A4) | `da2928073adde371187a3f420cc9593e1a44ee0ebaee9cf2fd798c7cb5285229` |
| `kuchitsu1998_ethane.csv` | Kuchitsu (ed.) 1998, ethane only (added by amendment A5) | `4a29c922313513dd20bec0a8f3557566fa3a7aad316c11060005fe48aadb6218` |
| `bakowies1996_table8_parameters.csv` | Bakowies & Thiel 1996, Table VIII, Rappé–Goddard rows (added by amendment A7) | `8c409a309fed28fbea367163fde1e0615df5aee0de0cb99f68a7f6eabeb9e54d` |
| `bakowies1996_table10_charges.csv` | same, Table X, Rappé–Goddard column (added by amendment A7) | `d50985432501bbb2a951d181935ea6ff8010b1821c27cf627db8727d6b340750` |
| `ramachandran1996_tables.csv` | Ramachandran et al. 1996, Tables 2 and 3, every column (added by amendment A7) | `90d8f7e57ba5b67e5644244b25a1bf4c253e6fc4ededa6d8b45eb66a29e0b08a` |
| `almenningen1963_disiloxane.csv` | Almenningen et al. 1963, Table 1 final results, plus labelled reconstruction (added by amendment A7) | `028b430065320a0de85ceef08d07f2b921a3005744b292b5e8bc3a95c3fdef48` |
| `qeq_perf_conformers.csv` | Aspirin, fentanyl, n-hexadecane and atorvastatin, frozen RDKit/MMFF94 coordinates for the A8 time gate (added by amendment A8) | `6592aefb3aee17f9665604746238fc795b56ca01d180388642cddc7eb68edfae` |
| `o9_corpus_conformers.csv` | The naming corpus restricted to Table I elements, 174 molecules, frozen RDKit/MMFF94 coordinates (added by amendment A9) | `d4641f3b7ee7a2d014d5b5c0f427b0de8bc21567470a86d0cbc11dd7e47491f1` |

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

### A4 (2026-09-14, after Harmony 1979 arrived and BEFORE any polyatomic solve)

Harmony et al., J. Phys. Chem. Ref. Data 1979, 8, 619
(https://doi.org/10.1063/1.555605; the PDF prints no DOI, so it was
confirmed against Crossref's record for that volume and page) was added as `harmony1979_structures.csv`. Every printed column was
transcribed, from 200 dpi renders.

**Coverage.**
- All five Table III molecules except the diatomics already run.
- Every Table IV compound except **ethane**, which is not in the compilation.
  Its C₂H₆ formulas run from C₂H₅P to C₂H₆BN, so it came from Landolt–Börnstein
  (the paper's reference 16), which is not held. C₂H₆ stays skipped.

**Which column, fixed now.** Harmony often prints several structure types for
one parameter. For each parameter, take the first one printed in the order
**equilibrium, substitution, average, effective**, from nearest to the
equilibrium structure to furthest. The paper says only "experimental
geometries".
- One diagnostic is reported and is not a gate: the reverse order,
  effective first.
- The types used per molecule are recorded in the output.

**Construction, fixed now.** Net charge 0 for every molecule; planar where
Harmony's drawing or symmetry says so.

| molecule | rule |
|---|---|
| H₂O, NH₃, PH₃ | C2v / C3v from the bond and the H–X–H angle |
| CH₄, SiH₄ | Td from the bond |
| H₂CO | planar C2v; H–C–O = (360° − HCH)/2 |
| CO₂, C₂H₂ | linear |
| H₂C=C=O | planar C2v, C=C=O linear, H–C–C = (360° − HCH)/2 |
| CH₃CN | linear C–C≡N, C3v methyl with H–C–C = HCC |
| C₂H₄ | planar D2h, H–C–C = (360° − HCH)/2 |
| C₆H₆ | regular D6h hexagon, C–H radial |
| HOC(O)H | planar. O1 is the carbonyl (Harmony's drawing). HCO is read as H–C–O1, so H–C–O2 = 360° − OCO − HCO = 111.3°. O2–H at COH, with **H syn to O1** (dihedral O1–C–O2–H = 0°) as drawn. |
| H₂NC(O)H | planar. N–C–O = NCO, N–C–H = NCH. H1 at H1–N–C = 118.5° **on O's side** (dihedral H1–N–C–O = 0°) as drawn; H2 at 360° − 121.6° − 118.5° = 119.9° on the other side. |
| H₃COH | C–O and C–O–H in a plane. The methyl is C3v (C–H, H–C–H) about an axis tilted φ from the C–O line **away from the OH group**, in that plane. It is **staggered**: one methyl H anti to the hydroxyl H across C–O, as drawn. |

**Table IV's duplicate and positional labels.** These are inferences, stated
because the table prints none of them:
- **HOC(O)H:** the first O (printed before C) is O1, the carbonyl; the second
  (printed directly above H(O)) is O2.
- **H₃CCN:** the first C (printed after N) is the nitrile carbon; the second is
  the methyl carbon.
- **H₂C=C=O:** the first C (after O) is the carbonyl carbon; the second is CH₂.
- **H₃COH:** Ht is the methyl H anti to the hydroxyl H; Hg is each of the two
  gauche H, and both must match.
- **H₂NC(O)H:** Hc is H1 (cis to O); Ht is H2.
- **Where one label covers equivalent atoms** (the H of CH₄, C₂H₄, C₆H₆, SiH₄,
  PH₃, CH₃CN, H₂CO, H₂C=C=O), every such atom must match.

**Tolerances unchanged:** O4 ±0.002 e for polyatomics, O5 ±0.01 e.

**What these can change.** Nothing about shipping: QEq already stopped on
HF, LiH and O9. These rows complete the record Alex decides from. They are
run under P, with the one-at-a-time alternates in `oracle.py`, as section 3
requires.

### A5 (2026-09-14, after the 1998 volume arrived and BEFORE ethane is solved)

**The source.** Ethane is the one Table IV compound Harmony 1979 lacks.
Rappé & Goddard's other source, Landolt–Börnstein II/7 (1976), is not held.
Held instead is Kuchitsu (ed.), *Structure of Free Polyatomic Molecules: Basic
Data* (1998), https://doi.org/10.1007/978-3-642-45748-7. It is a digest of
II/7, II/15 and II/23, and its ethane entry is tagged II/7(3,274).

**Which determination, fixed now.** The entry prints three:
- Iijima's electron diffraction, 1973;
- Hirota et al.'s microwave, 1981;
- Harmony's microwave/IR, 1990.

Only Iijima 1973 predates II/7, so only it can be what the authors used. Within
it, the r_z structure is used (A4's "average" type): C–C 1.5323 Å, C–H
1.1017 Å, H–C–H 107.30°, staggered D3d. The r_g values are thermal averages,
not a structure. **That II/7 printed exactly these numbers is an inference;
II/7 has not been seen.**

**Label.** Table IV prints ethane's H only. Every H must match (A4), at
±0.01 e, under P, with the alternates reported in `oracle.py`.

**Not used:** *Vogt & Vogt, Structure Data of Free Polyatomic Molecules*
(2019), https://doi.org/10.1007/978-3-030-29430-4. Its introduction scopes it to
structures published 2009–2017, so nothing in it could be a geometry Rappé &
Goddard used in 1991.

### A6 (2026-09-14, AFTER every oracle had run -- a post-hoc choice, disclosed as such)

**The decision.** Alex adopted R4 (eq 17′, λ = ½ for every element) as the
reading the solver uses. `charge_equilibration.ADOPTED` is R4, and it is the
default. P stays in the code as `PREREGISTERED`, unchanged, so the
pre-registered result can still be reproduced.

**Why it is post-hoc, and why it was made anyway.** Section 3 forbids
promoting a reading because it fits, and R4 was chosen after the tables had
been compared: P misses 39 of 76 polyatomic cells, and R4 misses 10. Three
things made the choice defensible, and none of them is the fit alone:
- the paper's text describes it: "Rounding off to λ = 1/2 … and hence (17)
  becomes (17′)";
- Table II prints a λ = ½ column, and R4 reproduces it to 0.0005 e, as P does
  Table II's other column;
- the improvement is consistent across 15 molecules, not concentrated in one.

**What changed.**
- The stop record in `tests/test_charge_equilibration.py` now lists R4's
  misses, not P's: 6 Table III cells (HF QEqHF; LiH, both columns; the QEqHF
  column of H₂O, NH₃ and CH₄) and 7 of 74 Table IV cells (methanol's H(O), C
  and Ht in QEqHF; formamide's C in QEq and N in QEqHF; SiH₄ in both). P
  missed 43 of the same test cells.
- O3 holds each Table II column to its own reading explicitly.
- A mutation that sets `ADOPTED = PREREGISTERED` turns 56 tests red.

**What did not change.** Tolerances, fixtures and geometries. QEq still does
not ship: LiH never converges, SiH₄ is wrong in sign, the HF-fitted hydrogen
column misses more than the experimental one, the bound procedure misses the
KKT optimum (O9), and a drug-sized molecule takes minutes.

**Ethane's geometry, measured (A5 follow-up).** Solved under R4 at every
structure the 1998 digest prints (Iijima 1973 r_z and r_g, Hirota 1981 r_z,
Harmony 1990 r_m; H–C–H from C–C–H where only that is printed), Q_H is 0.150
to 0.155 with the experimental set (printed 0.16) and 0.130 to 0.135 with the
HF set (printed 0.13). All four pass ±0.01 e, and they span 0.005 e. Which
determination Landolt–Börnstein II/7 printed cannot change ethane's result,
so II/7 is not needed.

**Checked and not useful.** Rappé, Casewit, Colwell, Goddard & Skiff 1992
(UFF, https://doi.org/10.1021/ja00051a040) prints no electronegativity,
hardness or QEq radius. It cites the same unpublished GMP paper ("submitted")
for them, so it cannot explain SiH₄.

### A7 (2026-09-14, before any output of the studies it defines)

A6 does not retroactively change the original pre-registration; it records a
post-hoc, literature-supported change of reading. **A7 changes no reading, no
tolerance and no line of `charge_equilibration.py`.** It pre-registers
diagnostics for three open problems (LiH, SiH₄, the transcriptions). The bound
procedure (O9) and speed are deferred to separate plans. Nothing here fits a
parameter: Si and H χ, J, ζ and λ are never changed to reach SiH₄'s +0.13 or
LiH's −0.767, and mixing is never added to the solver.

Background measured before A7, not under it: `oracle.py`'s LiH scan (199
points on [−0.99, 0], centred difference h = 1e-5) found one root under
ADOPTED, Q_H = −0.9731 with map slope −14.24 (experimental set), and −0.9819
with −14.36 (HF set).

**The map F.** For hydrogen charges q_H (one per hydrogen), F(q_H) is one
outer iteration of `qeq_charges`, in its order:
1. `ce.qeq_hardness_matrix(elements, coords, q_H, hydrogen, ce.ADOPTED)`, which
   sets ζ_H = ζ° + Q (eq 20) in every hydrogen-involving `coulomb_pair`
   (`zeta_h_in_pairs`) and hardness_diag_H = J°(1 + Q/ζ°) (eq 21);
2. `ce.solve_bounded(C, χ, 0, lower, upper)` with eq 5's bounds from
   `ce.charge_bounds`;
3. the solved charges at the hydrogen indices.

A test holds that iterating F from q_H = 0 reproduces `qeq_charges` on HF and
H₂O to 1e-12 e.

**Three questions, kept apart.** Q-A: does Q\* = F(Q\*) exist? Q-B: is the
printed charge one? Q-C: does a given iteration converge to Q\*?

**Root-finding (LiH, scalar), frozen.**
- g(Q) = F(Q) − Q on a uniform grid over [−1, +1], 2001 points. The whole
  grid is written to `lih_g_scan.csv`, both hydrogen sets.
- A root bracket is a sign change, or an exact zero, between neighbouring
  points. It is refined by bisection to a bracket ≤ 1e-10. It is accepted as
  a root only if |g| ≤ 1e-8 evaluated directly at the midpoint.
- A tangency candidate is a local minimum of |g| on the grid below 1e-3
  without a sign change on either side. It is refined by golden-section
  search on |g| within ±0.002 and reported with its minimum, whatever it is.

**Slope, frozen.** Centred differences (F(Q\*+h) − F(Q\*−h))/2h at
h ∈ {1e-3, 1e-4, 1e-5, 1e-6}; the reported slope is h = 1e-5; if the four
spread by more than 0.05 the slope is reported as unstable. Inner solves are
direct linear solves.

**Bound state at Q\*.** Report the active set `solve_bounded` chose and each
atom's distance to both bounds. If an active set differs anywhere in
[Q\* − 1e-3, Q\* + 1e-3], the slope is reported only as one-sided differences,
labelled active-set-adjacent.

**Predictions.** Q-A: exactly one root, −0.973 ± 0.002 (experimental) and
−0.982 ± 0.002 (HF), no bound active, no tangency candidate. Slope −14.24 ±
0.1 and −14.36 ± 0.1. Q-B: |g(−0.767)| ≥ 0.05 (experimental) and |g(−0.679)| ≥
0.05 (HF).

**Mixing study (Q-C), diagnostic only.**
- Q_{k+1} = (1 − α)Q_k + αF(Q_k) from Q₀ = 0, α ∈ {1.0, 0.75, 0.5, 0.25, 0.1,
  0.05}, at most 500 iterations.
- Converged requires BOTH |Q_{k+1} − Q_k| ≤ 1e-8 AND |F(Q_k) − Q_k| ≤ 1e-8.
- Iteration counts are reported in bins: ≤ 50, ≤ 100, ≤ 250, ≤ 500, not
  converged. `_trace_class` labels are descriptive and decide nothing.
- Predicted by local stability, s_mix = 1 − α(1 − s), converging only when
  |s_mix| < 1 (α < 2/(1 − s) ≈ 0.131): α ≥ 0.25 does not converge; α = 0.1 and
  0.05 converge to Q\*.
- The same α that converges is never offered as the answer to Q-B.

**Mixing invariant.** Mixing moves the path, not the fixed point. HF, H₂O, NH₃
and CH₄ (Harmony geometries, both sets), iterated with α = 1 and α = 0.5 from
q_H = 0 under the criteria above, each independently: the two must agree to
1e-7 e. Agreement with the stored ADOPTED charges is a separate regression.

**Ramachandran et al. 1996 water.** Their Table 8 gives QEq H = 0.353 at an
O–H of 0.9572 Å and H–O–H of 104.52°, which they state (section VIII.c). Under
ADOPTED, experimental set, both hydrogens must be 0.353 ± 0.001. It is the
first QEq charge in this benchmark whose geometry its authors state.

**SiH₄ geometry sensitivity.** Si–H ∈ {1.45, 1.48, 1.51} Å and a D2d
distortion of the tetrahedron: hydrogens at (±a, 0, c) and (0, ±a, −c) with
the H–Si–H angle within each pair θ = 109.47° + δ, δ ∈ {−5, −2.5, 0, +2.5, +5}°.
Report min and max Q_H under ADOPTED, both sets. The question is binary: does
any reach +0.13 (experimental) or +0.11 (HF)?

**Ramachandran Tables 2 and 3, source audit.** From a 300 dpi render of
p. 5899: every QEq value, multiplicities (O 1, Si 2, H 6 for O(SiH₃)₂; Si 1,
O 4, H 4 for Si(OH)₄), and the totals. If Table 3's QEq column sums far from
zero, the record says "internally inconsistent with charge conservation", not
"misprinted". Table 2's H1/H2 multiplicities are inferred from its sum; which
hydrogens are H1 is a further inference and is labelled so.

**Disiloxane (only if Almenningen et al. 1963 is obtained).**
`almenningen1963_disiloxane.csv` carries a `provenance` column: `source` for
every printed parameter, `reconstructed` for C2v symmetry, local C3v silyls
and the conformation. Under ADOPTED, experimental set: the sign test first
(every H negative, Si positive). The magnitudes second, only once H1/H2 is
mapped: H and Si within ±0.02 e, O within ±0.03 e. The sweep is Si–O–Si 140° to
180° in 10° steps and Si–O ±0.02 Å; report any sign change. Ramachandran
cites no parameter source that can be followed (its "earlier work" is ref 6,
a catalysis paper), so Si being 1991 Table I's in their program is an
inference.

**Bakowies & Thiel 1996 reprints.** Table VIII (χ, J for H, C, N, O) and Table X
(the Rappé–Goddard column: QEqHF, "exp. geometries") are transcribed from 300
dpi renders into two fixtures, compared with `rappe1991_table1.csv` and
`rappe1991_table4.csv` in two tests. Only cells whose molecule, atom and column
all correspond are compared. A mismatch is re-read against the 1991 render
and is never corrected toward the reprint.

**Both λ readings as regressions.** A test reproduces the polyatomic cell miss
counts, 39 of 76 under PREREGISTERED and 10 of 76 under ADOPTED, and the exact
miss sets, through the same `qeq_charges` path.

**Outcomes, stated in advance.** LiH: the printed charge is a fixed point; it
is not and Q\* lies elsewhere; a pre-registered alternate reading produces it;
unexplained. SiH₄: reproduced; contradicted by the later Rappé-group program
(recorded as a strongly supported inconsistency, not as a misprint);
geometry-sensitive; a parameter-source discrepancy remains; unresolved.

**A7 addendum (2026-09-14, after Almenningen 1963 arrived and BEFORE any
disiloxane solve).** The paper settles the geometry and not the conformation:
its authors call C2v "with one hydrogen on each -SiH3 group nearest the
2-fold axis" the most obvious interpretation, "not ... a firm conclusion".
That conformation (dihedral H-Si-O-Si = 0 for the in-plane hydrogen) is the
reference, labelled reconstructed. Because it is not firm, one sweep is added
to A7's, before any solve and disclosed as an addition: torsion of both silyls
by 0, 30 and 60 deg (60 puts the other hydrogens in-plane pointing away). It
reports signs only, like the Si-O-Si and Si-O sweeps. The H1/H2 magnitude
comparison maps H1 to the two in-plane hydrogens of the reference
conformation, an inference from Table 2's multiplicities.

### A8 (2026-09-14, a revised SHIPPING scope; before any optimisation or any number it governs)

**The original gate failed and stays failed.** Section 8 made O4 and O5 the
condition for shipping QEq. They are not met, and their strict xfails stay in
the suite unchanged. A8 does not reinterpret them. It records a decision by
Alex to ship under a narrower, stated validation scope, and why.

**Why the scope was revised, not the bar lowered.**
- O4/O5 were a strict source-reproduction gate. Later, independent evidence
  showed that one printed row (SiH₄) conflicts with the authors' own later
  program (Ramachandran et al. 1996, A7).
- λ = ½ reproduces that later program (disiloxane O and Si, conformation-
  independent, 0.002 e). LiH's printed charge is not a solution of the
  equations (A7).
- What ships is therefore a narrower claim. The cases the record cannot
  support are refused or not offered.

**The shipped method.** `qeq_rg1991_lambda_half_h_experimental`: readings
`ce.ADOPTED`, hydrogen set `experimental`, the solver as it is. **Not
offered:** the HF-fitted hydrogen set (it misses more cells and inverts the
paper's ordering of the two sets) and PREREGISTERED. Both stay in code for this
benchmark.

**The validated subset (the scope's evidence), all under the shipped method:**
- Table II: all 20 halides, ≤ 0.0005 e.
- Table III: HF within 0.001 e; H₂O, NH₃ and CH₄ within 0.002 e.
- Table IV QEq column: HF and ClH, and 33 of 35 polyatomic cells, within 0.01 e.
  The misses are formamide C (+0.011) and SiH₄.
- Ramachandran 1996: water (0.3532 against 0.353, at their stated geometry);
  disiloxane O and Si (0.002 e); all four disiloxane charges within 0.002 e in
  the anti C2v conformation (post hoc, A7).

**Scope sentence, verbatim for the documentation.** "This calculator implements
the Rappé–Goddard 1991 QEq formulation using the λ = ½ interpretation (eq 17′)
and the experimental hydrogen parameter set. It reproduces the validated
benchmark subset recorded in amendment A8. The published LiH value is not a
self-consistent solution of the implemented equations, and such cases are
refused. The published 1991 SiH₄ value is inconsistent with the later
Rappé-group implementation and is treated as a source discrepancy, not as an
oracle. Results whose final solution requires an active charge bound are
refused pending the O9 study."

**Two categories, never merged.**
- **Computationally refused:** `REFUSE_NOT_CONVERGED` (LiH among others) and
  `REFUSE_BOUND_ACTIVE` (the final solution has a non-empty active set). This is
  a deliberate validity boundary: QEq is incomplete over the bound-active
  domain until O9.
- **Source discrepancy:** silicon. A result is returned, with a note that it
  does not reproduce the 1991 SiH₄ row and that Ramachandran 1996 supports its
  sign.

**Result contract.** `QEqResult.clamped` is, and has been, the active set of the
converged final iteration. It is renamed `final_active_atoms` (with `clamped`
kept as an alias). A new `ever_clamped` is true if any pass of any outer
iteration fixed an atom. The refusal is decided on `final_active_atoms` alone:
an iterate clamped mid-loop whose final solve is bound-free is a valid result.
Refusal provenance keeps the diagnostics: iterations, final metrics, trace
class and `ever_clamped` for non-convergence; index, element, bound and final
charge per active atom for a bound.

**Provenance separates what was computed from how it was validated.** The
calculation block carries the method code, `parameter_set =
rappe_1991_table_I`, `hydrogen_parameter_set = experimental`,
`zeta_parameterization = rappe_1991_eq17_prime_lambda_half` with `lambda = 0.5`,
`zeta_h_in_pairs`, `hydrogen_self_term = eq21`, `integral_model =
ns_slater_exact`, a0, eV per hartree, iterations, final metrics,
`bound_passes_max`, `ever_clamped` and `solver_to_source`. A separate
validation block carries A8 and the scope sentence; it is not part of any
result's identity. EEM stays the default method, and its default
`parameters_key` stays `c8a6d189021bbd3d35d4621f5b102f37`.

**Speed: a pure optimisation, with acceptance fixed now.** No screening,
cutoff, truncation, reduced pair list or loosened tolerance. A change that moves
a charge beyond these limits is a new model and does not ship under A8. The
authorities, in order:
1. **The mpmath table** (`slater_reference.csv`), the independent accuracy
   reference: fast integrals ≤ 1e-9 Ha on all 1076 points (O1 as it is).
2. **The charge oracles**, the scientific end-to-end reference: every charge
   vector for Tables II–IV, Ramachandran water and disiloxane, and the A7 LiH
   quantities unchanged to ≤ 1e-9 e, compared as full vectors; both λ miss
   sets identical.
3. **The scalar `coulomb_pair_integral`**, the regression-compatibility
   reference. Stage 1 (vectorisation with the same nodes and branches) must
   match it pair by pair to ≤ 1e-11 Ha on the O1 grid and every pair of the
   timing molecules at the ζ_H values their iterations visit. A Stage 2 closed
   form, used only if Stage 1 misses the time gate, need only meet (1) and (2),
   and its cancellation switch is frozen in a note before it is written.

Only terms whose inputs do not depend on the hydrogen iteration may be reused
across it (distances, shells, heavy-atom ζ, χ and diagonal, heavy–heavy pairs).
Every hydrogen-involving integral is recomputed each iteration.

**Time gate (this machine, not a CI gate).** Only `ce.qeq_charges` is timed:
integrals, linear solves and hydrogen iteration. Import, parsing, conformer
generation, UI and provenance are excluded. Input: a frozen fixture of aspirin,
fentanyl, n-hexadecane and atorvastatin (SMILES, atom order, elements, exact
coordinates, experimental set). Median of 3: atorvastatin ≤ 5 s and aspirin ≤
0.5 s; fentanyl and hexadecane reported with atom counts, hydrogen fraction and
iteration counts. Hardware, OS, Python and numpy versions are recorded.

**O9 is not touched here.** Its study is a separate branch and amendment (A9).

**A8 Stage 2 note (2026-09-14, after Stage 1 missed the time gate and BEFORE any
Stage 2 code).** Stage 1 kept every node and branch and agreed with the scalar
routine to 1e-14 Ha, but still evaluates about 2 million quadrature nodes per
hydrogen iteration on atorvastatin, and measured 10-22 s (the CPU was shared
with another heavy process). By A8, Stage 2 follows. Fixed now:

*The closed form.* With a = 2ζ_a, b = 2ζ_b, p = 2n_b − 1, m = 2n_a + 1 and
W_a(r) = r − m/(2a) + e^(−ar) Π(r), where Π(r) = Σ_k π_k r^k,
π_k = a^(k−1) [−[1≤k≤m]/(k−1)! + [2≤k≤m]/(4n_a (k−2)!) + [k≤m] m/(2 k!)]
(so that W_a(0) = 0):
J(R) = b^(2n_b+1) / (2R (2n_b)!) × { L + e^(−aR) A − e^(−aR) B − e^(−bR) C },
- L = 2(p+1)!/b^(p+2) P(p+2, bR) + 2R p!/b^(p+1) Q(p+1, bR), by the
  existing gamma functions;
- A = Σ_k π_k Σ_{i≤k} C(k,i) R^(k−i) (p+i)!/(a+b)^(p+i+1) (all positive
  powers);
- C = Σ_k π_k Σ_{i≤p} C(p,i) R^(p−i) (i+k)!/(a+b)^(i+k+1);
- B = Σ_k π_k R^(p+k+1) p! k!/(p+k+1)! M(p+1; p+k+2; z), z = −(b − a)R,
  with M Kummer's confluent hypergeometric function.

*The one cancellation switch, dimensionless:* the sign of z. For z ≥ 0, M is
summed directly (all terms positive); for z < 0 through Kummer's transformation
M(α; β; z) = e^z M(β−α; β; −z) (all terms positive). At z = 0 both give 1
exactly. Continuity is tested at z = 0 and z = ±1e-12, ±1e-6 (relative change
≤ 1e-12). The exponential prefactor (e^(−aR) or e^(−bR)) is applied to each
series' first term, so no intermediate overflows where the result is finite.
A series stops once its index exceeds |z| + β and every new term is below
1e-17 of its running sum; a pair that has not stopped by 4000 terms is sent to
the fallback, and counted.

*The one small-argument fallback:* where min(a, b)·R < 2 (and for R = 0), the
1/R prefactor makes the closed form cancel, so those pairs use the Stage 1
batched quadrature, which is exact to the same standard. QEq refuses R below
0.1 Å, but diffuse hydrogens (small ζ_H) can still reach the fallback. A
counter records how often each branch runs, and a test asserts that both are
exercised.

*Acceptance is unchanged from A8:* ≤ 1e-9 Ha against the mpmath table on all
1076 points (whichever branch each takes), charge vectors unchanged to ≤ 1e-9
e, both λ miss sets identical, and the time gate. The closed form is never
validated only against the quadrature.
### A9 (2026-09-14, the O9 bound study; before any output it defines)

**The question.** How often does a charge bound activate on realistic
molecules, and where it does, how far is the paper's never-release fixing
(eq 13) from the true constrained minimum? This is research: nothing here
changes the solver or any calculator, and any later decision to ship a
departure from the paper is Alex's.

**The derivation, so the QP is QEq's and not merely a problem with the same
unconstrained answer.** At fixed hydrogen parameters, the paper's electrostatic
energy (its eq 6 at those parameters) is
E(q) = Σ_i χ_i q_i + ½ qᵀ C q (eV), with C_ii = J_i (hydrogen:
hardness_diag_H at the fixed Q_H) and C_ij = the Slater Coulomb integral
(eq 16). Its Hessian is C. Minimising E subject to Σ q = Q gives the linear
KKT system C q − μ 1 = −χ, 1ᵀq = Q, which is exactly the system `solve_bounded`
builds (eqs 10–13). Adding eq 5's bounds l ≤ q ≤ u gives the convex QP (when C is
positive definite on {1ᵀd = 0}, which is checked and reported per matrix), whose
KKT conditions are: stationarity C q − μ 1 − λ_l + λ_u = −χ, with λ_l, λ_u ≥ 0,
complementarity, and feasibility. The QP optimum is the reference; the paper's
procedure is compared with it.

**Hydrogen is frozen for every O9 solve.** ζ_H and hardness_diag_H are fixed at
given hydrogen charges, so the question contains no nonlinear loop. For a
corpus molecule they are fixed at the hydrogen charges of its converged
production solve (ADOPTED, experimental set); for a molecule that does not
converge, the study reports that and uses no fixed point.

**The QP solver** (`tests/qeq_bounded_qp.py`, used by the benchmark script): a
primal active-set method that can release atoms. Checked in this order, and
reported in this order:
1. with no bound active at the optimum it equals the unconstrained KKT solve,
   to ≤ 1e-10 e, on ordinary QEq matrices (Table II halides, water, methanol);
2. it equals the brute-force KKT optimum on O9's 200 synthetic systems, and on
   every real corpus matrix whose bounds activate, to ≤ 1e-10 e;
3. it equals the paper's procedure wherever the paper's procedure already
   satisfies the KKT conditions.

**The corpus, frozen before any solve.** The naming benchmark's
`benchmarks/naming/corpus.json` (181 molecules), keeping those whose elements
are all in Table I. Each is hydrogen-added by RDKit, embedded by ETKDGv3 with
randomSeed 20260914, optimised by MMFF94 (200 iterations), and written to
`tests/fixtures/charges/o9_corpus_conformers.csv` with its SMILES, net formal
charge, elements and coordinates. A molecule RDKit cannot embed or MMFF94 cannot
type is recorded as skipped with the reason. The corpus is an evaluation set:
nothing is tuned on it.

**Recorded per molecule:** convergence of the production solve; whether any
bound was active in its final solve (`final_active_atoms`) or at any pass
(`ever_clamped`); at the frozen hydrogen parameters, whether the paper's
procedure is KKT-optimal; and where it is not, max |q_paper − q_opt|, RMS
difference, the atoms whose active status differs, and E(q_paper) − E(q_opt).
Aggregates: activation frequency, and disagreement frequency and size, by
element and by the corpus's charge categories.

**No outcome here ships anything.** If no molecule activates a bound, the
refusal introduced by A8 stays as a cheap safety boundary. If some do, these
data inform the decision.

**A9 correction (2026-09-14, before any study output).** The first corpus file
wrote its rows with an unquoted f-string, so the fourteen molecule names that
contain a comma ("1,4-…", "(S,R)-…") split across columns, and the first
study run stopped while reading the file, with no molecule solved. The
builder now uses `csv.writer`. Regenerated with the same seed, it holds the
same 174 molecules and coordinates, correctly quoted, and the hash above is
updated.

### A10 (2026-09-14, the hydrogen refit; before any output it defines)

**The question.** Can the published hydrogen parameter pairs be reproduced by
repeating the paper's own fit? Section IV fits χ°_H and J°_H to "the charges on
H in the molecules LiH, CH₄, NH₃, H₂O, and HF", and ref 20 states the weights:
"In this fit we weighted CH₄ as 5, LiH as 0.2, and the others as 1." Table III
prints both target columns and both results: the exptl column, fitted to
(4.5280, 13.8904), and the HF column, fitted to (4.7174, 13.4725). This is
evidence only. Nothing here changes the solver, a calculator, a default, an
identity or a shipped claim, and any later proposal is a separate amendment
with a complete new gate.

**Sources read for it (2026-09-14).**
- **Cioslowski, Phys. Rev. Lett. 1989, 62, 1469** (Table III footnote e). Its
  Table I prints LiH Q_H = −0.6819 (APT, RHF/6-31++G\*\*, optimised geometry).
  That is Table III's HF value −0.682, identified. It prints no bond length, so
  there is no geometry variant to test.
- **Cioslowski, J. Am. Chem. Soc. 1989, 111, 8333** was requested first by
  mistake and is not the cited paper.
- **Ongari et al. 2019** confirms the five-molecule fit and the iteration
  "starting from the initial guess of null partial charge".
- **caltechmsc/cheq v0.5.1** (MIT) is an implementation reference only, the
  source of H-c and H-d below.

**Targets and observations.**
- One observation per molecule: its Table III row (`rappe1991_table3.csv`).
- Every hydrogen in these symmetric molecules carries the same charge. The
  instrument asserts equality to 1e-10 e and uses that value, so multiplicity
  never enters.
- Geometries are O4's: Huber r_e for HF and LiH, and A4's builders for H₂O, NH₃
  and CH₄.

**Objective.** S(χ, J) = Σᵢ wᵢ (Qᵢ(χ, J) − Tᵢ)², summed over the five
molecules.
- T is the exptl column for the experimental-set fit and the HF column for the
  HF-set fit.
- w = 5 (CH₄), 0.2 (LiH), 1 (HF, H₂O, NH₃). These are the weights themselves,
  never their squares or square roots.

**Variants.** The list is complete, and each differs from V0 in one rule.

1. **V0, the shipped A8 model** (ADOPTED):
   - ζ from eq 17′ with λ = ½;
   - ζ_H = ζ° + Q (eq 20) in every hydrogen-involving pair, both H–heavy and
     H–H;
   - hydrogen's diagonal D = J°(1 + Q/ζ°) (eq 21), with ζ° = 1.0698;
   - eq 5's bounds and eq 13's fixing, through `ce.solve_bounded`.

   Q_H is the self-consistent charge: the unique root of g(Q) = F(Q·1)_H − Q on
   [−1, +1]. F is one outer build and solve at all hydrogens set to Q. Mixing
   does not move a fixed point (A7), so this is the converged answer wherever
   plain iteration converges, and LiH's where it does not.
2. **H-a6, H-a7, H-a8, H-a9, H-a10**, five separate variants. V0's equations,
   with Q_H = F^k(0), where F^k is k plain outer iterations from all hydrogens
   at zero.
   - k is fixed per variant, and the same for all five molecules and both
     columns. The optimiser never chooses it.
   - Every molecule's trace Q₀…Q_k is written at the printed pairs.
   - A pass shows only that a k-iteration reading reproduces the fit, not that
     the 1991 program stopped at k.
3. **H-b.** V0 with D = J°(1 + 1.5 Q/ζ°), the diagonal whose fixed point
   satisfies eq 23's gradient. From E_H(Q) = χ°Q + ½J°Q²(1 + Q/ζ°), dE_H/dQ =
   χ° + J°Q + (3/2)J°Q²/ζ° (section 3, R2). Built as ADOPTED with
   `hydrogen_self_term="eq23_gradient"`. Q_H is defined as in V0.
4. **H-c.** V0 with ζ_H = ζ° = 1.0698 in every hydrogen-involving pair, both
   H–heavy and H–H. D is still eq 21 and moves with Q. Built as ADOPTED with
   `zeta_h_in_pairs=False`. Q_H is defined as in V0.
5. **H-d.** H-c with D = J°(1 + clamp(Q, −0.95, +0.95)/ζ°).
   - The clamp is applied only to the Q entering D, as cheq's
     `run_single_solve` applies it.
   - Pair ζ is already fixed.
   - The solved charges are never clamped.

   Q_H is defined as in V0.

χ°_H and J°_H enter nothing but hydrogen's χ entry and diagonal. The instrument
sets those two directly and takes everything else from the shipped build. A
test holds its matrices equal to `ce.qeq_hardness_matrix` at both printed pairs
under V0, H-b and H-c.

**Root finding (V0, H-b, H-c, H-d).**
1. g is evaluated on A7's grid of 2001 points over [−1, +1]. Pair integrals on
   that grid do not depend on χ or J, so they are computed once per molecule.
2. **Exactly one sign change** is required. Zero or several (or an exact zero on
   a grid point beside a sign change) make S = +∞ at that (χ, J). The count of
   such evaluations is reported.
3. The bracket is refined by two exact batched evaluations of 9 equally spaced
   points each.
4. A cubic through the four points nearest the sign change gives the root.
5. The root is accepted only if exact |g| ≤ 1e-11 there; otherwise S = +∞ and
   the failure is counted.

Integrals that are identical by symmetry (same shells, same exponents, distance
equal to 1e-12 Å) are computed once.

**Optimiser, fixed.**
- **Box:** χ ∈ [4.0, 5.5] eV, J ∈ [12.0, 15.0] eV. Outside the box S = +∞, so
  the point is rejected, never clipped or reflected.
- **Global structure:** S on a 61 × 61 grid over the box. Local minima (a finite
  S no larger than any of its eight neighbours) are reported as grid basins.
- **Local search:** Nelder–Mead in the script, since scipy is not in the
  environment:
  - reflection 1, expansion 2, contraction ½, shrink ½;
  - initial simplex x₀, x₀ + (0.05, 0), x₀ + (0, 0.05);
  - stop when every vertex is within 1e-6 eV of the best (max-norm) and every
    S within 1e-10 of the best, or after 4000 iterations;
  - a test holds it to the minima of a quadratic and of Rosenbrock's function
    within 1e-6;
  - it starts from the 25 points of the 5 × 5 grid over the box (the corners
    included) and from the printed pair.
- **Basins:** every endpoint is recorded, and endpoints within 1e-3 eV
  (max-norm) share a basin. The best fit is the lowest-S endpoint. When another
  basin lies within ΔS < 1e-8 of it, all such basins are reported and none is
  selected.
- **No-optimiser check:** S on a 41 × 41 grid spanning ±0.05 eV around the best
  fit. Its minimum must lie within one grid step (0.0025 eV) of the best fit.

**Rounding recovery control, per variant and column, before that variant's
real refit.**
1. Draw 200 samples, seeded with numpy `default_rng(20260915)`.
2. For each, add U(−5e-5, +5e-5) eV to each printed parameter (four-decimal
   printing) and compute every molecule's Q_H there.
3. Add U(−0.0005, +0.0005) e to each charge (three-decimal printing).
4. Refit by Nelder–Mead from the printed pair.
5. The envelope is the 95th percentile of |χ_fit − χ_printed| and of
   |J_fit − J_printed|. Draws with no finite S are counted and excluded.

The fixed ±0.01 eV is reported beside it, as a reference and not a gate.

**Reported per variant and column,** at the printed pair first:
- **at the printed pair:** each molecule's Q_H and residual against the target;
  S; max |residual|; the LiH residual; RMS and max over the four non-LiH
  molecules; and centred ∂S/∂χ, ∂S/∂J (h = 1e-4 eV, diagnostic);
- **at the refit:** the pair, S, ΔS = S(printed) − S(refit), the same residual
  set, the basins, the fine-grid check, and the local elongation. A quadratic is
  fitted to the fine grid, and the square root of its Hessian's eigenvalue
  ratio is reported;
- **the program-output check:** each molecule's Q_H at the printed pair against
  the paper's own QEq (or QEqHF) column, with O4's tolerance of ±0.001 e for
  diatomics and ±0.002 e for polyatomics;
- **ordering:** per molecule, whether sign(Q_exp-set − Q_HF-set) at the two
  printed pairs matches sign(QEq − QEqHF) in Table III. It is reported as a
  count of inverted molecules.

**Classification, per variant, with no combined score.**
- **FIT-REPRODUCED** needs, for both columns: the refit within the rounding
  envelope of the printed pair (both parameters), **and** every program-output
  check within tolerance. Each condition must hold on its own.
- **PARTIAL:** one column meets both conditions.
- **UNEXPLAINED:** neither does.
- PROGRAM-CONFIRMED is not reachable here; it would need a source stating how
  the 1991 program worked.

**Stop rule.** No variant is added after any output exists. If every variant is
UNEXPLAINED, the record says that the published pairs are not reproduced, under
the documented fit protocol, by the shipped equations or by any reading tested
here.

**Test pins.** Verdicts, basin counts, S to 1e-9 relative, and refit pairs to
1e-4 eV. Optimiser digits beyond those are not pinned.

**A10 corrections (2026-09-14, before any objective value, refit, control draw
or grid existed; disclosed with what had been seen).**

1. **The root rule was wrong for this map.** "Exactly one sign change" assumed
   g is continuous. It is not: the bounded solve switches active set, so g
   jumps. The rule now reads:
   - every sign change is refined as above, and kept only if exact
     |g| ≤ 1e-11 at the refined point (a jump never passes);
   - an exact zero on a grid point is kept on the same test;
   - a kept root whose bounded solve has an active bound is **pinned**, and is
     not a charge, because A8 refuses such answers;
   - Q_H is the unique **bound-free** root, and zero or several make S = +∞;
   - bound-free and pinned counts per molecule are reported at the printed
     pairs.

   **How it was found.** An instrument probe of the sign changes and the
   active set beside each, with no S computed, at (4.528, 15.0),
   (4.528, 13.8904), (4.7174, 13.4725) and (5.0, 12.5), for V0 and H-c. What
   it showed:
   - **V0 at both printed pairs:** one sign change per molecule, bound-free,
     where production and A7 already put the charges.
   - **V0 LiH at (4.528, 15.0):** three bound-free sign changes (near −0.970,
     −0.473 and −0.258).
   - **H-c at both printed pairs:** a bound-free sign change near +0.440,
     +0.325, +0.218 and +0.130 (experimental pair) and near +0.444, +0.324,
     +0.212 and +0.113 (HF pair) for HF, H₂O, NH₃ and CH₄. Beside them, jumps
     with bounds active, and further bound-free sign changes at negative Q for
     H₂O, NH₃ and CH₄. For LiH, only a sign change with Li and H at their
     bounds.

   That is the extent of what was seen. A test now holds the corrected rule on
   H-c's HF (three sign changes, one bound-free root, one pinned root) and on
   V0's LiH at (4.528, 15.0) (three bound-free roots, so no charge).
2. **H-c and H-d's fixed hydrogen exponent is the shipped one.** With
   `zeta_h_in_pairs=False` the shipped build keeps eq 17′'s ζ_H = 1.069751
   (λ = ½, R = 0.371 Å). A10 wrote "ζ° = 1.0698", the rounded constant that
   eq 20 and eq 21 use. The instrument uses the shipped 1.069751, since it is
   also cheq's λ = 0.5 radius rule; the difference is 5e-5 bohr⁻¹. The
   diagonal still divides by ζ° = 1.0698, as the shipped build does.

**A10 correction 3 (2026-09-14, after a crashed run that wrote no output;
before any rerun).**

**What happened.** The first full run crashed inside the rounding control. One
CH₄ evaluation in an ill-conditioned region gave a hydrogen charge spread of
2.05e-10 e, against the instrument's `assert spread <= 1e-10`. Because the jobs
were collected with an all-or-nothing `pool.map`, that one assertion discarded
all 18 jobs. **No objective value, refit, control envelope, basin or verdict
was ever written or seen**; the traceback is the only output.

**What changes, and why the change is not tuned to anything.** A numerical QA
threshold must not become a wall inside the function being optimised.
1. **Symmetry groups.** In all five fit molecules, every hydrogen is equivalent
   under the point group as built: HF and LiH have one H; H₂O (C2v) two; NH₃
   (C3v) three; CH₄ (Td) four. The group is read from the builder's own atom
   mapping (Table IV printed order 1 for the polyatomics) and asserted, when the
   molecule is constructed, to be every hydrogen. That is a setup check, not
   one the optimiser can reach.
2. **Q_H is the mean over the group.** The spread (max − min) is recorded for
   every evaluation, into a log₁₀ histogram with 0.1-decade bins, per phase:
   printed pair, control, grid and Nelder–Mead. **The spread never makes S
   infinite and never raises.**
3. **Geometry symmetry is measured separately.** For each built molecule, the
   spread of heavy-atom–H distances and of H–X–H angles is reported, so
   asymmetry in the fixture is not blamed on the solver.
4. **The check at reported points.** Spread is measured at the solved charge,
   at the printed pair and at the refit pair. It must be ≤ 10 × the 99th
   percentile of spreads in that column's control phase (the upper edge of the
   histogram bin holding the 99th percentile, which is conservative), floored
   at 1e-10 e. The control histogram is reported first. A violation marks the
   column SYMMETRY-CHECK-FAILED, and that variant gets no verdict.
5. **Each job writes its own self-contained file**
   (`hydrogen_refit_jobs/<variant>_<column>.json`): settings, fixture and
   preregistration SHA-256s, git commit, symmetry statistics, the result, or the
   traceback.
6. **Job states are COMPLETE, FAILED or NOT_RUN,** and the summary is sorted by
   (variant, column).
   - A variant gets a verdict only when both of its columns are COMPLETE and
     neither failed the symmetry check.
   - No overall conclusion is written unless all 18 jobs are COMPLETE.
