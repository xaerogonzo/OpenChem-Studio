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
