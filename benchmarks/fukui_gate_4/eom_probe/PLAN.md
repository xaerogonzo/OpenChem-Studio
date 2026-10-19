# The EOM-IP-CCSD probe (after gate 4's outcome; exploratory, decides nothing)

Written 2026-10-19, **before any job of the two molecules of its rule was run**, and committed before the first one. Gate 4's outcome (PARTIAL, `../PREREGISTRATION.md` section 11) is final and this does not touch it. It is the check that
sections 11.7 and 11.8 left open: the larger basis did not remove the sigma-state bias, and the second functional moved the sigma-pi gaps by 0.04 to 0.35 eV, nearer the printed ranges in five molecules and farther in one. Neither result says which functional is right.

## The question

**Which of the two functionals puts the sigma-pi gap nearer a correlated calculation that uses no functional?** The reference is IP-EOM-CCSD: the ionization energies of a closed-shell molecule as the poles of a coupled-cluster
Green's-function-like equation, whose roots are the vertical cation states at the molecule's own geometry, with orbital relaxation and correlation in the method. That is the same quantity a delta-SCF hole calculation at a fixed geometry
estimates, so **the vertical-against-adiabatic difference that blurs the printed photoelectron ranges (section 11.4) does not enter**.

## What is run

* **Method:** canonical IP-EOM-CCSD on an RHF reference (ORCA 6.1.1, `! IP-EOM-CCSD`, `%mdci DoEOM true`, `FollowCIS true` so that the roots are the Koopmans-like ones, 8 roots, ORCA's default frozen core), at the **geometries of gate 4** (B3LYP/6-31G\*, not re-optimized), oriented with the plane as xy.
  Run on a water molecule first to check the syntax (IPs 11.80, 14.11 and 18.46 eV at cc-pVDZ, converged); that check is not a record.
* **Molecules:** **pyrimidine and pyrazine**, the two where the functionals differ most (S = +0.28 and +0.35 eV, `../functional_probe/PLAN.md`), and **pyridine** as the validation of the whole pipeline (its EOM-IP-CCSDT ladder is `trofimov2017` Table V: 1a2 pi +0.15, 2b1 pi +0.85, 5b2 sigma +3.17 eV above the 7a1 sigma state).
* **Bases:** **cc-pVDZ, aug-cc-pVDZ and cc-pVTZ**, in that order. aug-cc-pVTZ (about 640 functions for pyrimidine) is not attempted: a canonical CCSD of that size does not fit this machine's 32 GB. The ladder is there because sigma holes are the basis-sensitive ones in correlated calculations
  (`shojaei2010` Table 1: 0.56 and 0.61 eV from 6-31G to cc-pVDZ++ against 0.11 and 0.18 for pi), so the EOM gap is only a reference when it has stopped moving.
* **Kind of a root:** the kind of its dominant occupied orbital (the largest single-excitation amplitude), read from ORCA's own `LOEWDIN REDUCED ORBITAL POPULATIONS PER MO`: the share of the orbital on functions odd in z (pz, dxz, dyz, f0, f-2, f+2) is 1 for a pi orbital and 0 for a sigma one; at least 0.75 is pi, at most 0.25 sigma (gate 4's limits), anything between is reported as mixed and makes the record incomplete. Checked on water in the xy plane at cc-pVTZ: all 58 orbitals came out at 0.0 or 1.0 (`eom_parse.py`).
* **The DFT gaps compared with it are the ones at def2-TZVP**, the triple-zeta basis, so that the comparison is between triple-zeta calculations (the shifts between 6-31G\* and def2-TZVP are 0.03 and 0.05 eV for B3LYP, `../basis_probe/PLAN.md`): B3LYP/def2-TZVP is the larger-basis probe's own record, and **wB97X-D3/def2-TZVP is run for the three molecules before the comparison is read**
  (`../basis_probe/run_probe.py --method wB97X-D3 --basis def2-TZVP --tag wb97xd3_def2tzvp --out ../functional_probe/artifacts`, the same exhaustive search as every earlier DFT record). The 6-31G\* gaps are printed beside them and decide nothing.
* A record is **complete** only if ORCA exited 0, every root converged, 8 roots were read, their dominant orbitals are the HOMO and the orbitals below it without a gap (a gap would mean a lower root was missed), and every root has a kind. An incomplete job is repeated unchanged up to three times.
* A **sizing run** of pyridine (cc-pVDZ: 33 s at 8 cores; the ladder came out sigma 0, pi +0.14, pi +0.84, sigma +3.29 eV, the order of the CCSDT reference) and one at cc-pVTZ (760 s at 8 cores, under 8 GB; pi +0.03, pi +0.75, sigma +3.19 eV: the order of the reference, and the first pi state 0.1 eV lower than at cc-pVDZ, which is the basis sensitivity the ladder is for) were made before this plan to see the cost and that the parser works. Pyridine is the calibration; the two molecules of the rule were not run.

## What is compared, fixed now

For each molecule:
* **G(EOM)** = E(lowest pi root) - E(lowest sigma root), in eV, positive when the sigma root is lower, at each basis, and **G(B3LYP)** and **G(wB97X-D3)** at def2-TZVP defined the same way from the lowest pi and sigma states of the hole search;
* each functional's **error** |G(functional) - G(EOM)| at the decision basis;
* for pyridine, the ladder against EOM-IP-CCSDT.
Reported and in no rule: each root's singles character (a root below 85% is a strongly relaxed or satellite-mixed one, where EOM-IP-CCSD is less reliable), the EOM gap against gate 4's printed ranges, and the first ionization energies.

## The reading rule, fixed now (the first line that holds decides)

* **The decision basis** is the largest basis in the ladder at which all three molecules completed.
* **Validation (pyridine):** at the decision basis the lowest four roots are sigma, pi, pi, sigma, and the three gaps above the lowest are each within **0.25 eV** of EOM-IP-CCSDT's 0.15, 0.85 and 3.17 (gate 4's tolerance, not fitted to the sizing run). If not: **NOT EVALUABLE** (the EOM numbers are not a trusted reference here) and the report says which gap failed.
* **Per molecule (pyrimidine, pyrazine):** the functional with the smaller error at the decision basis is nearer **if its error is smaller by at least 0.05 eV**; otherwise the molecule is a **TIE**.
* **Overall:** **B3LYP NEARER** if no molecule is won by wB97X-D3 and at least one by B3LYP; **wB97X-D3 NEARER** if no molecule is won by B3LYP and at least one by wB97X-D3; **MIXED** if one of each; **NEITHER DISTINGUISHABLE** if both are ties.
* **Convergence:** if the change of G(EOM) from the next smaller basis to the decision basis exceeds **0.10 eV** in either molecule, the outcome is labelled **PROVISIONAL (the basis is not converged)** and says by how much it moved.
* No tolerance, limit or range of gate 4 is changed by anything here, the molecule set is not extended after seeing a result, and **the application's functional (B3LYP) is not changed by this plan whatever it finds**: that would be a decision for Alex with its own preregistration.

## What it cannot say

* EOM-IP-CCSD is a reference of finite accuracy, not the truth: the pyridine check measures it against EOM-IP-CCSDT at the decision basis (0.25 eV allowed), and a gap difference smaller than the sum of the method's error and the 0.05 eV tie width is not resolved by it.
* The geometries are B3LYP's, one reference method, two molecules in the rule. It says nothing about the azoles, where the sigma state is the higher one.
* It compares the SIGMA-PI GAP at a fixed geometry. A functional that is nearer the reference in the gap could still be farther in another quantity a Fukui calculation uses, and nothing here tests that.
* A delta-SCF hole and an EOM root are different calculations of the same vertical quantity; they agree where both are exact and not otherwise, which is what this measures.

## Records

`artifacts/<tag>/runs.jsonl` (one JSON line per attempt, with the commit, the dirty flag, the ORCA version and the input hash, each root's energy, dominant orbital, amplitude, singles character, kind and orbital share) and `<molecule>.eom.txt` (ORCA's results block), `report.txt` and `summary.json` from `report_eom.py`, and the outcome written below, after the run and after nothing else.

## Outcome

Run on 2026-10-19 at the commit that holds this plan (`0461d70b`, tree clean; `artifacts/ccpvdz`, `augccpvdz`, `ccpvtz`, and `../functional_probe/artifacts/wb97xd3_def2tzvp`; `report.txt`, `summary.json`). Every job completed at the first attempt except **pyridine at cc-pVTZ, whose first attempt exited with an error (code -3, no roots) when three EOM jobs ran at once** and which was repeated unchanged, alone (the plan allows three attempts); the repeat completed. **READING RULE: B3LYP NEARER.**

The sigma-pi gap G (positive when the sigma root is lower), in eV:

| molecule | EOM cc-pVDZ | EOM aug-cc-pVDZ | **EOM cc-pVTZ** | B3LYP def2-TZVP (error) | wB97X-D3 def2-TZVP (error) | winner |
|---|---|---|---|---|---|---|
| pyrimidine | +0.924 | +0.847 | **+0.800** | +0.877 (0.077) | +0.592 (0.208) | B3LYP |
| pyrazine | +0.652 | +0.563 | **+0.506** | +0.632 (0.126) | +0.272 (0.234) | B3LYP |
| pyridine | +0.140 | +0.075 | **+0.025** | +0.120 | +0.032 | (calibration) |

* **Validation passed.** At cc-pVTZ pyridine's lowest four roots are sigma, pi, pi, sigma, and the three gaps are 0.025, 0.746 and 3.192 eV against EOM-IP-CCSDT's 0.15, 0.85 and 3.17: errors 0.125, 0.104 and 0.022 eV (tolerance 0.25).
* **Convergence, by the rule's own test, passed**: G moves by -0.047 (pyrimidine) and -0.057 eV (pyrazine) from aug-cc-pVDZ to cc-pVTZ, under the 0.10 limit, so the outcome is not labelled provisional.
* **The reference puts both functionals on opposite sides.** B3LYP's gap is 0.08 (pyrimidine) and 0.13 eV (pyrazine) **larger** than the EOM gap, that is, its sigma state is too low relative to pi, the direction of gate 4's bias; wB97X-D3's is 0.21 and 0.23 eV **smaller**, its sigma state too high. Each molecule is won by B3LYP by more than the 0.05 tie width (0.13 and 0.11 eV).
* **The EOM gaps against gate 4's printed ranges**: pyrimidine 0.800 is at the top edge of 0.48 to 0.80, pyrazine 0.506 is 0.044 below 0.55 to 0.80 (reported, in no rule).
* **Every kind and the order of the lowest four roots** are the same as the DFT ladders' in both molecules (sigma, pi, sigma, pi for pyrimidine; sigma, pi, sigma, pi for pyrazine). The lowest four roots have singles character of 90% or more, so none is a strongly relaxed or satellite-mixed one.

**What it says.** Against a calculation that uses no functional, **B3LYP's sigma-pi gap is nearer than wB97X-D3's in both molecules**, and its error is the one gate 4 described (sigma 0.08 to 0.13 eV too low relative to pi), where the range-separated hybrid overshoots by two to three times as much the other way. So the second-functional probe's "nearer the printed ranges" for wB97X-D3 in five molecules was not evidence that it is the better functional for these gaps. The application's functional stays B3LYP, and nothing about gate 4's outcome changes.

**What it does not say, and two things that point in opposite directions, each about as large as the margin.**
* **The reference is still moving with the basis**: G(EOM) fell by 0.077 and 0.047 (pyrimidine) and by 0.089 and 0.057 eV (pyrazine) over the two steps, and pyridine's first pi state kept falling (0.140, 0.075, 0.025). The rule's test (0.10) was met, but if the remaining change at the complete-basis limit were of the size of the last step, it would take G(EOM) down by about another 0.05 to 0.1 eV, which would bring the two functionals' errors to similar sizes in both molecules (and put wB97X-D3 ahead in pyrazine at the upper end of that range). **This is an illustration, not an extrapolation, and not a result**; the plan fixed the cc-pVTZ comparison.
* **EOM-IP-CCSD has its own error**, and pyridine measures it: 0.125 eV on the first pi state against CCSDT, **in the direction of a smaller G**. If that error carried over to the diazines (not tested), their true G would be about 0.1 eV larger than the EOM values, which would favor B3LYP further.
So the verdict is B3LYP nearer by the preregistered rule, with a margin (0.11 to 0.13 eV) that is no larger than either of these two uncertainties.

Also: two molecules, one reference method, B3LYP geometries, the gap only; the azoles, where the sigma state is the higher one, were not run. wB97X-D3's gaps moved with the basis (def2-TZVP against 6-31G*: pyrimidine -0.04, pyrazine -0.07, pyridine -0.01 eV) by about as much as B3LYP's (-0.03, -0.05, 0.00), and the same direction as the EOM gaps' fall.

**Left open.** A larger EOM basis for the diazines is not available on this machine (aug-cc-pVTZ is about 640 functions for pyrimidine); a cc-pVQZ or a basis-set extrapolation of canonical EOM with a smaller frozen-virtual space, or a DLPNO-EOM, would remove the first uncertainty, and EOM-IP-CCSDT on pyrimidine or pyrazine (published for pyridine only) the second.

## After the outcome: a published cross-check, and a correction (2026-10-19)

`ranasinghe2019` (Ranasinghe, Margraf, Perera and Bartlett; its supplement `ranasinghe2019_si/`, Tables S3 and S4) was obtained after the run. It holds **IP-EOM-CCSD/cc-pVTZ for pyrimidine and pyrazine (NIST set, MP2/def2-TZVP geometries) and for pyridine (CGB set), and no CCSDT for any of the three**: IP-EOM-CCSDT/cc-pVTZ was run for 41 molecules, mostly of the CGB set, and neither diazine is in Table S3.

| | theirs, above the lowest (eV) | ours at cc-pVTZ, above the lowest (eV) |
|---|---|---|
| pyrimidine | 0.807, 1.450, 1.648 | 0.800, 1.472, 1.647 |
| pyrazine | 0.476, 1.734, 2.048, 4.021 | 0.506, 1.748, 2.099, 4.101 |
| pyridine, their geometry | 0.260, 0.684, 3.235 | **0.258, 0.683, 3.232** (ORCA at their geometry, `geometry_check.py`) |
| pyridine, gate 4's geometry | | 0.025, 0.746, 3.192 |

(The states are matched by energy order; their irrep labels were not mapped to ours.)
* **Our pipeline reproduces an independent code**: pyridine at their geometry agrees to 0.003 eV on all three gaps, the diazines to 0.01 to 0.08 eV at geometries that differ (MP2/def2-TZVP against B3LYP/6-31G\*), and the gap that decides the rule to 0.007 (pyrimidine) and 0.03 eV (pyrazine).
* **The geometry matters for pyridine and hardly for the diazines**: pyridine's first pi gap is 0.258 eV at their (CCSD(T)/aug-cc-pVTZ) geometry and 0.025 at gate 4's, a shift of 0.23 eV, where the two diazine geometries agree to 0.01 to 0.03 eV in the gap.
* **Correction to the second caveat of the Outcome.** It said EOM-IP-CCSD's own error on pyridine is 0.125 eV in the direction of a smaller gap, which would favor B3LYP. That 0.125 was measured at the B3LYP geometry and mixes the method with the geometry. At a correlated geometry the EOM-IP-CCSD gap is 0.258 against EOM-IP-CCSDT's 0.15 (the geometry of that CCSDT calculation was not checked), a difference of +0.11 in the OTHER direction. **The size of EOM-IP-CCSD's own error is about 0.1 eV; its sign is not established**, and the caveat no longer points toward B3LYP.
* **A counter-observation the rule did not include.** Pyridine was the calibration, outside the rule. At the same geometry and cc-pVTZ-class basis, G(EOM) is 0.025; B3LYP/def2-TZVP gives 0.120 (0.095 above) and **wB97X-D3/def2-TZVP gives 0.032 (0.007 above): wB97X-D3 is the nearer one for pyridine**, B3LYP for the two diazines. B3LYP's gap is larger than the EOM gap by 0.10, 0.08 and 0.13 eV in the three molecules (same direction, its sigma state too low), and wB97X-D3's is 0.01 above in pyridine and 0.21 and 0.23 below in the diazines.
The preregistered outcome (B3LYP NEARER, for the two molecules of the rule) is unchanged; what it supports is narrower than "B3LYP's gap is the nearer one".
