# Homolytic bond dissociation enthalpy from ORCA: design (2026-10-19)

Status: **design and proposed thresholds only; nothing is run and nothing is frozen.** The third reactivity calculator of Phase 3 (after Fukui and proton affinity), behind a preregistered gate; "measured, not shipped" is an accepted outcome. This note records what was decided with Alex, what the one reference source says, and the thresholds proposed for approval. The preregistration is written after the thresholds are approved, as it was for proton affinity.

## What is computed, and what is never claimed

* **The bond dissociation enthalpy at 298.15 K, DH298(R-H) = H(R.) + H(H.) - H(RH)**, each H a total enthalpy at 298.15 K and 1 atm, the same quantity as Blanksby and Ellison's `DH298`. Not D0, not De, not a Gibbs energy, and never an electronic-energy difference. [source:blanksby2003]
* **X-H bonds only** (Alex, 2026-10-19). C-C, C-Hal, C-O and C-N bonds are a later class with its own preregistration, so one failure cannot sink the other.
* **Closed-shell neutral parent, doublet radical, unrestricted Kohn-Sham.** Radicals of the benchmark's own bonds only; no biradicals, no charged species, no open-shell parents (so CH3, CH2, OH, NO, HONO are out).
* The hydrogen atom is computed, not tabulated: `H(H.) = E(H atom, same method and basis) + (5/2) RT` (translation only, `1.4812` kcal/mol, the same term `benchmarks/proton_affinity/pa_core.py` derives for the proton).

## The reference (Table 1 of Blanksby and Ellison 2003, read from the page image)

Experimental `DH298` with the stated uncertainty, in `benchmarks/bde/reference_values.json`: **33 bonds**. The **25 whose stated uncertainty is at most 1.0 kcal/mol decide** (methane through silane, the alkane C-H classes, ethene, ethyne, benzene, propene allylic, toluene benzylic, the alcohol O-H and C-H, the thiol S-H, H2S, NH3, H2O, the two peroxide O-H, formaldehyde, acetaldehyde formyl, HCN, SiH4); the **8 with an uncertainty above 1.0** (acetaldehyde's methyl C-H, phenol, the two hydroperoxides, the three acids, methanethiol's C-H) are **reported, never deciding**, because a reference this loose cannot tell a good calculation from a bad one. The stratum is set by the reference's own uncertainty, not by what the calculation gives. Formic acid's `>=96` is an inequality and is left out.

## Protocol, primary arm (same as proton affinity)

M062X/def2-TZVPD, `TightSCF TightOpt DefGrid3 Opt Freq`, ORCA 6.1.1, radicals as `* xyz 0 2` (UKS), the parent as 0/1. Each species: ETKDG seed 7 (30 conformers), MMFF94, dedupe by all-atom RMSD 0.5 Angstrom, the lowest three within 5 kcal/mol optimized; **a radical's starts are the parent's kept conformers with the hydrogen deleted**, so the radical is not embedded as a closed-shell guess. The lowest-H structure of each species, independently; no Boltzmann average. A frequency below -20 cm-1 is not accepted (one retry with an initial Hessian). The hydrogen atom: one UKS single point of the same method.
**Reported for every radical, deciding nothing:** the `<S**2>` (0.75 is a clean doublet) and the largest unpaired-spin leakage onto an atom far from the site, as a flag for a contaminated result.
No symmetry-number issue: the quantity is an enthalpy.
The secondary arm (DLPNO-CCSD(T)/def2-QZVPPD single points on the same geometries with the DFT thermal corrections) is the same one as for proton affinity and is only run if the primary arm passes.

## What the literature says about accuracy (read so far, and what it does not cover)

* **The reference's own uncertainty** for the deciding bonds is 0.008 to 1.0 kcal/mol, the median about 0.4. No threshold below sits under it.
* **Zhao and Truhlar 2008 (the M06 suite), their Table 5, the ABDE4 database** (four alkyl bond energies, R-CH3 and R-OCH3 with R = methyl and isopropyl, **De, electronic, not an enthalpy**, 6-311+G(3df,2p) single points on B3LYP/6-31G(d) geometries; read from the page image): **M06-2X MSE +0.27, MUE 0.74 kcal/mol**; M05-2X -0.18 and 0.61; BMK -1.37 and 1.67; M06 -1.90 and 1.90; **B3LYP -8.62 and 8.62**, PBE -3.98. [source:zhao2008] These are C-C and C-O bonds, a harder class for a density functional than X-H, and a different quantity (De), so it is evidence about the functional, not a transferable error bar.
* **Not found, and said so:** the GMTKN55 SI in the library (`goerigk2017_si.pdf`) carries two bond-energy sets, ALKBDE10 (M06-2X MAD 4.79, group 1 and 2 diatomics) and YBDE18 (M06-2X 2.40), neither of which is an organic R-H bond, and **no published M06-2X error for R-H bonds of the kind in this set has been read.** The proposed thresholds therefore rest on the one close database (ABDE4), on the reference's uncertainty, and on the PA benchmark's own convention of leaving room for a different basis, UKS radicals and ORCA's thermochemistry; that is weaker footing than proton affinity had, and the preregistration will say so.

## Proposed thresholds (for approval; the same shape as proton affinity's rule)

On the **25 deciding bonds**, error = calculated - experimental in kcal/mol:

* **PASS:** MAE <= **2.0**, no error above **4.0**, |MSE| <= **1.5**.
* **PARTIAL:** not PASS and MAE <= **3.0**.
* **FAIL:** otherwise.
* **NOT EVALUABLE:** more than **three** of the 25 have no computed value.
* The 8 loose-reference bonds, and all 33 together, are reported in the same statistics and decide nothing.

Why these numbers: M06-2X's one close published MUE is 0.74 and the median reference uncertainty about 0.4, so 2.0 is about 2.7 times that MUE and leaves room for def2-TZVPD against a quadruple-zeta-class basis, UKS radicals and ORCA's thermal corrections; the maximum of 4.0 stops one wild bond hiding in a good mean; the 1.5 mean-signed limit catches a systematic bias that a mean absolute error can hide. If the primary arm passes, the secondary arm's PASS limit is tighter, as for proton affinity, and is fixed in the preregistration.

## What a verdict does

PASS: the calculator is built (a service-level sequence, experimental, needing approval at first), offered only for the X-H classes the benchmark covers and with its error stated. PARTIAL: the failing bonds are named and Alex decides. FAIL: nothing is built; the report is the deliverable. NOT EVALUABLE: nothing is claimed; the cause is fixed and the benchmark re-run under a new preregistration.

## Order of work

1. This note, and Alex's approval of the thresholds.
2. `PREREGISTRATION.md`, `bde_core.py` (the arithmetic) and `judge.py`, tested on synthetic data before any job.
3. The runner (the proton-affinity runner's structure, radical starts from the parent), tested on real output, committed, **not run** until Alex says so.
4. The overnight run, then the report.
5. Only then, on a PASS, the calculator in the application.
