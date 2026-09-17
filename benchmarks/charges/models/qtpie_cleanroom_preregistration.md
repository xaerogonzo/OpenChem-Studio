# QTPIE clean-room check against Chen's own printed test charges

**Pre-registration, committed before any charge is computed.** Decided by Alex, 2026-09-17: pre-register
a clean-room QTPIE check instead of transcribing Chen's printed Fortran. The thesis carries arXiv's
non-exclusive distribution licence, so its code is not copied into this repository, in whole or in
part. Results are appended below the line at the end and never edited into the sections above it.

## 0. The claim, and what "clean room" means here

**Claim kind: IMPLEMENTATION REPRODUCTION on two molecules.** Does an independent implementation of
QTPIE's Gaussian atom-space form, written from the thesis's equations, give the per-atom charges that
Chen's own test program prints?

**Clean room, defined:**
- **The code is written here, in numpy, from the equations and facts listed in sections 1 and 2.**
- **Chen's appendix was read for facts only:** parameter values, unit constants, the Gaussian
  exponents, which basis the test assigns, the printed expected charges, and the algebraic form of two
  integrals given in comments. No statement, routine structure or control flow is copied.
- **What this cannot say:** that his program is correct, or that QTPIE is accurate. It can only say
  whether the published description and his printed numbers are consistent.

## 1. Sources, as read

`chen2009thesis` (arXiv:1004.0186, `chen2009thesis.pdf`, 245 pp):
- **Energy and effective electronegativity:**
  - eq 2.8, charge-transfer form;
  - eq 3.19–3.21, atom-space form with the constraint Σq = 0;
  - eqs 3.24 and 3.25, choosing k_ij = N / Σ_j′ S_ij′, so that v_i = Σ_j (χ_i − χ_j) S_ij / Σ_j′ S_ij′.
- **The linear system (eq 3.21):** [[J, 1], [1ᵀ, 0]] (q, μ) = (−v, 0).
- **QEq(-H) is the same system with v = χ:** no hydrogen correction, as §2.3 states.
- **Gaussian Coulomb integral:** eq 2.14 prints J_G = erf(√α R)/R for two equal exponents. The appendix
  comment for the general case gives erf(√(αβ/(α+β)) R)/R, which at α = β is erf(√(α/2) R)/R. **They
  differ by a factor of two in the exponent convention** (TRIAGE 3.10), so both are registered readings.
- **Normalised s-Gaussian overlap (appendix comment, and Lalli & Giusti eq A1):**
  S = (4αβ/(α+β)²)^¾ exp(−αβ/(α+β) R²), with S_ii = 1.
- **Units and constants, from the appendix module of conversion factors:** atomic units throughout.
  1 eV = 3.67493245e-2 hartree; 1 Å = 1/0.529177249 bohr. The xyz loader converts Å to bohr.
- **Parameters (eV, as printed; χ then J):** H 4.528 / 13.890, O 8.741 / 13.364, Na 2.843 / 4.592,
  Cl 8.564 / 9.892. These equal Rappé–Goddard Table I (TRIAGE: H's J prints 13.890 against Table I's
  13.8904).
- **Gaussian exponents:** the test's loader assigns the fitted exponent from the appendix array, by
  element, in the same element order as the parameter list. Two printings exist, so both are readings:

  | element | appendix array (E_app) | Table 2.2 (E_tab) |
  |---|---|---|
  | H | 0.534337523756312 | 0.5434 |
  | O | 0.223967308625516 | 0.2240 |
  | Na | 0.095892938712585 | 0.0959 |
  | Cl | 0.113714050615107 | 0.1137 |

- **The oracle, printed in the appendix test program.** Charges in e; its own tolerance is 1e-6.

  | molecule | model | atom | printed charge |
  |---|---|---|---|
  | NaCl | QEq(-H) | Na (atom 1) | +1.3895802392931755 |
  | NaCl | QTPIE | Na (atom 1) | +0.72522900679059155 |
  | H₂O | QEq(-H) | O (atom 1) | −0.98965172663781498 |
  | H₂O | QEq(-H) | H (atom 2) | +0.49438117990925540 |
  | H₂O | QTPIE | O (atom 1) | −0.81213640965 |
  | H₂O | QTPIE | H (atom 2) | +0.40556679590604666 |

- **What is missing:** the two xyz files (`nacl.xyz`, `h2o.xyz`) are not printed, so the geometries are
  unknown. The water charges show the molecule is **not** symmetric: H(3) = −O − H(2) = +0.49527 under
  QEq(-H), against H(2) = +0.49438.

## 2. The model, frozen

For a molecule of N atoms, in atomic units:
- **J matrix:** J_ii = J_i. For i ≠ j, J_ij = K(α_i, α_j, R_ij), under one of two kernel readings:
  - **K_code:** erf(√(α_i α_j / (α_i + α_j)) R) / R;
  - **K_print:** erf(√(2 α_i α_j / (α_i + α_j)) R) / R. This is eq 2.14's convention, generalised
    here to unequal exponents; the generalisation is ours.
- **Overlap:** S as in section 1, with S_ii = 1.
- **Solves:**
  - QEq(-H) solves eq 3.21 with v = χ.
  - QTPIE solves it with v_i = Σ_j (χ_i − χ_j) S_ij / Σ_j S_ij, where both sums include j = i.
- **Total charge:** 0 for both molecules; the loader assigns zero.
- **Cut-offs are not implemented.** The author's program neglects an overlap below 1e-9 and switches
  erf to 1 where erfc < 1e-9. On molecules of 2 and 3 atoms at bonding distances neither ever applies.
  Stated, not modelled.
- **Four arms,** every combination of exponent reading (E_app, E_tab) and kernel reading (K_code,
  K_print). All four run; none is preferred in advance.

## 3. Instrument, before any oracle comparison

`benchmarks/charges/models/qtpie_cleanroom_check.py` and `tests/test_qtpie_cleanroom_instrument.py`.

**Synthetic tests:**
1. **A diatomic in closed form:** q₁ = (v₂ − v₁)/(J₁ + J₂ − 2J₁₂), re-derived by hand in the test.
2. **QTPIE's dissociation limit:** q → 0 as R grows.
3. **QTPIE equals QEq(-H)** when every S_ij = 1.
4. **Σq = 0** for both models.
5. **Overlap:** S_ii = 1, and S is symmetric and at most 1.
6. **K_code and K_print** tend to 1/R at large R.

**Registered mutations, each expected red:**
- overlap exponent not reduced (α + β in place of αβ/(α+β));
- the ¾ power dropped;
- the diagonal of the normalisation sum excluded;
- v without the minus sign;
- K_print and K_code swapped;
- eV conversion applied twice.

## 4. Geometry recovery and prediction

**NaCl, for each arm:**
1. **Scan** R from 1.5 to 4.0 Å in 0.001 Å steps. Bracket every root of q_Na^QEq(R) − 1.3895802392931755,
   then refine each with Brent's method to |ΔR| ≤ 1e-12 Å.
2. **If exactly one root exists,** predict q_Na^QTPIE at that R.
3. **PASS** if the prediction is within **1e-6 e** of +0.72522900679059155.
4. **Zero roots or several:** UNDETERMINED.

**H₂O, for each arm:**
1. **Unknowns:** r₁ = O–H(2), r₂ = O–H(3) and θ = H–O–H, with atom order O, H(2), H(3) as the test's
   indexing implies.
2. **Fit three equations exactly:** q_O^QEq, q_H2^QEq and q_O^QTPIE.
3. **Search:** least squares from a 5 × 5 × 5 grid of starts over r ∈ [0.8, 1.2] Å and θ ∈ [90°, 120°].
   Keep every solution with max |residual| ≤ 1e-10 e.
4. **Distinct solutions:** those differing by more than 1e-6 Å or 1e-4° in any coordinate.
5. **Predict** q_H2^QTPIE for every distinct solution.
6. **PASS** if every solution predicts within **1e-6 e** of +0.40556679590604666.
7. **No solution,** or solutions whose predictions disagree beyond 1e-6: UNDETERMINED.

**Per-arm verdict:**
- **REPRODUCED:** NaCl and H₂O both PASS.
- **PARTIAL:** exactly one passes.
- **NOT-REPRODUCED:** both have a determined geometry and both fail.
- **UNDETERMINED:** anything else.

**The recovered geometries are reported, never gated.** For orientation: NaCl's gas-phase bond is about
2.36 Å, and water's r ≈ 0.96 Å and θ ≈ 104.5°.

## 5. What it licenses

- **If exactly one exponent reading is REPRODUCED and the other is not:** that identifies which printed
  hydrogen exponent the program behind these test values used. Only water contains hydrogen, so only
  the water check can discriminate. It says nothing about which value is Chen's *fit*; TRIAGE 3.10
  showed Table 2.2 does not recompute.
- **If any arm is REPRODUCED:** QTPIE gains an implementation-level charge check that TRIAGE 1 records
  as missing. Its G1 status moves from "no charge oracle" to "reproduced on the author's two test
  molecules". **HOLD stays:** two molecules at unknown geometries are not a population, and nothing
  ships from this.
- **If nothing is REPRODUCED:** the gap is recorded per arm. No third reading is added after the fact
  without an amendment that says why, committed before its numbers.

---

## Results

### Run 1 (2026-09-17, instrument commit c62889e): E_app / K_code REPRODUCED

`qtpie_cleanroom_results.json` (sha256 `b9307e5dd6b888e50682895268413f5915a21bc398853254436a8682544be92e`),
exit 0. Instrument: 11 tests pass; all 6 registered mutations red.

| arm | NaCl roots (Å) | predicted QTPIE Na (printed +0.72522900679) | H₂O solutions (r₁, r₂, θ) | predicted QTPIE H(2) (printed +0.40556679591) | verdict |
|---|---|---|---|---|---|
| **E_app / K_code** | 2.3610000298 | +0.7252289943, \|Δ\| **1.2e-8** | (0.9699999924, 0.9687329648, 100.35341°) | +0.4055667959, \|Δ\| **7.5e-12** | **REPRODUCED** |
| E_tab / K_code | 2.3609819774 | +0.7252534258, \|Δ\| 2.4e-5 | (0.9592406859, 0.9580341451, 98.27479°) | +0.4055680583, \|Δ\| 1.26e-6 | NOT-REPRODUCED |
| E_app / K_print | 1.7082726 and 2.7258088 (two roots) | — | none in range | — | UNDETERMINED |
| E_tab / K_print | 1.7082604 and 2.7258057 (two roots) | — | none in range | — | UNDETERMINED |

**By the registered rule,** an independent implementation of the thesis's equations reproduces the
author's own printed QTPIE charges on both test molecules. The conditions are the appendix exponent
array (E_app) and the Coulomb kernel erf(√(αβ/(α+β)) R)/R (K_code), not eq 2.14's printed convention.
QTPIE gains the implementation-level charge check TRIAGE 1 recorded as missing. HOLD stays (section 5).

**Reported, not gated: the recovered geometries are round numbers under the reproducing arm only.**
- **E_app / K_code:** NaCl R = 2.3610000 Å, and water's first O–H = 0.9700000 Å. That is to 7 digits,
  as a hand-written xyz file would be.
- **E_tab / K_code:** 2.3609820 and 0.9592407, which are not round.
- This is independent corroboration that the reproducing arm's geometry is the test's actual geometry.

**A limit on section 5's first clause, stated before going further.** E_tab differs from E_app in *all
four* exponents, not only hydrogen's.
- NaCl contains no hydrogen, so its decisive miss (2.4e-5) comes from the Na and Cl rounding.
- Water's miss under E_tab, 1.26e-6, is only just over the tolerance.
- **So run 1 identifies the exponent *set* the program used. It does not cleanly isolate hydrogen's
  exponent.**

### Amendment Q-A1: isolate hydrogen (registered after run 1, before computing it)

- **Arm E_mix:** E_app with hydrogen alone set to Table 2.2's 0.5434, under K_code.
- **Run:** the water recovery and prediction exactly as in section 4. NaCl is unaffected.
- **Rule:**
  - if E_mix water is determined and FAILS while E_app passes, the program's hydrogen exponent was the
    appendix value 0.534337523756312;
  - if E_mix water PASSES, water cannot distinguish the two hydrogen printings at this tolerance, and
    the question stays open;
  - if UNDETERMINED, it is recorded as undetermined.
- **Reported beside the verdict:** |Δ|, and the recovered r₁, because a round r₁ is the same kind of
  corroboration as above.
- **This cannot change run 1's verdict.**

### Q-A1 result (2026-09-17): the program used the appendix hydrogen exponent

`qtpie_cleanroom_results_qa1.json` (sha256 `60e2d5ab89fdc048723e86ff9affba23ace29d9d8c4d7c456f2abe73c70cba84`), exit 0.

| arm | H exponent | water solution (r₁, r₂, θ) | predicted QTPIE H(2) | \|Δ\| | status |
|---|---|---|---|---|---|
| E_app / K_code (run 1) | 0.534337523756312 | (**0.9699999924**, 0.9687329648, 100.35341°) | +0.4055667959 | 7.5e-12 | PASS |
| E_mix / K_code | 0.5434 | (0.9593152853, 0.9581079531, 98.30869°) | +0.4055680450 | 1.249e-6 | **FAIL** |

**By Q-A1's rule, the program that produced the printed test charges used hydrogen exponent
0.534337523756312, the appendix value, not Table 2.2's 0.5434.**

Stated plainly, because the margin looks small:
- **E_mix misses by only 1.25 times the tolerance.**
- **The contrast is larger than that margin suggests:**
  - E_app matches to 7.5e-12, five orders of magnitude inside the tolerance;
  - E_app's geometry is round (r₁ = 0.9700000 Å), and E_mix's is not.
- **What remains open:** which value is Chen's *fit*. TRIAGE 3.10 showed §2.4 cannot recompute
  Table 2.2 at all.
- **What follows for LAMMPS:** its example gfile uses 0.5434, which is not the value the thesis's own
  program ran with.

**Records to update once #123 merges.** TRIAGE §1 (QTPIE) and 3.10, and the unblock-inventory row for
QTPIE: the G1 charge oracle is no longer missing, and HOLD stays for the reasons in section 5. They are
not edited on this branch, to avoid conflicting with #123's changes to the same sections.

**Records updated, 2026-09-17, after #123, #124 and #125 merged:** TRIAGE section 1 (QTPIE), 3.10 (the hydrogen addendum, and a correction to the thesis-read line: the charge oracle was found in the unread test program) and 5.3, plus the unblock-inventory QTPIE row. The row keeps G1 HOLD, with the primary blocker now data: a population-level oracle.
