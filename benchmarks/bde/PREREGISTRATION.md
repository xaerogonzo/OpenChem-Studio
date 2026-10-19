# Bond dissociation enthalpy of X-H bonds from ORCA: preregistration

Written 2026-10-19, **before any job of the benchmark was run** (nothing of it has been run; what was read is listed under "What was seen first"). Design and the reading behind it: `docs/BDE_DESIGN.md`. The rule is the code in `judge.py` and the arithmetic is `bde_core.py`, both tested by `tests/test_bde_benchmark.py` before any job exists; where this text and that code disagree, the disagreement is fixed before the run, never after. **Status: frozen on commit of this file with its runner** (the runner is written, tested and committed after this file and before the first job; this file changes only by an amendment section that says what and why).

## The question

Does ORCA, run as a stated protocol, give the 298 K bond dissociation enthalpy (DH298, the enthalpy of RH -> R. + H.) of X-H bonds of small molecules at the accuracy the literature gives that method, against the experimental values Blanksby and Ellison tabulate [source:blanksby2003]? Measured, not shipped: **if the gate fails, the calculator is not built, and the failure and its reason are the deliverable.**
Two arms are judged separately, because one protocol cannot vouch for another:
* **Primary arm:** M062X/def2-TZVPD optimization and frequencies, thermochemistry from them.
* **Secondary arm:** the same geometries and thermal corrections with the electronic energy replaced by a DLPNO-CCSD(T)/def2-QZVPPD single point; **run only if the primary arm passes** (stage order, not a rule change).

## The data (fixed before any calculation)

`reference_values.json`: **33 X-H bonds** of Blanksby and Ellison's Table 1, each as a SMILES of the closed-shell parent and the index (as written in that SMILES) of the heavy atom that loses the hydrogen, with the experimental DH298 and the uncertainty they state (kcal/mol), read 2026-10-19 from the page image. Errors are computed - reference.
* **The deciding stratum is the 25 bonds whose stated uncertainty is at most 1.0 kcal/mol**; the other 8 (acetaldehyde's methyl C-H, phenol, the two hydroperoxides, the three acids, methanethiol's C-H) are **reported, never deciding**, because a reference that loose cannot tell a good calculation from a bad one. The stratum is set by the reference's uncertainty alone.
* **What is in and out of scope** (fixed): closed-shell neutral parents, ordinary doublet radicals, X-H bonds; no biradicals, no charged species, no radical parents, no X-Y bonds (their own later preregistration). Formic acid's C-H (`>= 96`, an inequality) is left out.

## The protocol, primary arm (everything here is fixed)

**Program and inputs.** ORCA 6.1.1. Every optimization and frequency job: `! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`, `%pal nprocs 4 end`, `%maxcore 3000`; a parent is charge 0 and multiplicity 1, **a radical charge 0 and multiplicity 2 (unrestricted: ORCA uses UKS for a non-singlet)**. ORCA's thermochemistry is at 298.15 K and 1.00 atm with its default quasi-RRHO treatment of the vibrational entropy (an entropy does not enter an enthalpy, but the default is what the run uses and is part of what is validated).
**Structures.** Each parent is built from its SMILES with explicit hydrogens (so heavy-atom indices are the SMILES's), embedded with RDKit ETKDG (seed 7, 30 conformers), relaxed with MMFF94, **deduplicated by all-atom RMSD 0.5 Angstrom**, and the **lowest three within 5 kcal/mol (MMFF) are optimized**. **A radical's starts are the parent's kept conformers with one hydrogen deleted from the named atom** (`bde_core.radical_start`: the lowest-numbered hydrogen on that atom), so a radical is never embedded afresh as if it were a closed-shell molecule and each kept parent conformer gives one radical start.
**The hydrogen atom** is one unrestricted single point at the same method and basis (`! M062X def2-TZVPD TightSCF DefGrid3`, multiplicity 2); `H(H.) = E + (5/2) RT` (`bde_core.hydrogen_atom_enthalpy`, 1.4812 kcal/mol, translation and pV only).
**Frequencies.** A structure with any vibrational frequency **below -20 cm-1** (the allowance for numerical noise in soft modes; no literature number) is not accepted; it is **re-run once from its final geometry with `%geom Calc_Hess true end`** and dropped if it still has one. A parent or radical with no accepted structure is a missing cell.
**Thermochemistry, per accepted structure:** ORCA's total enthalpy H (298.15 K, 1 atm). **No symmetry number enters** (an enthalpy has none).
**Selection and the formula.** The parent's structure of lowest H and the radical's structure of lowest H, **each chosen independently**; `DH298 = H(R.) + H(H.) - H(RH)` (`bde_core.bond_dissociation_enthalpy`). No Boltzmann averaging over conformers (the lowest only; a stated limitation).
**The failure that does not look like one.** ORCA can converge a radical to a different electronic state or a rearranged structure (a hydroperoxyl radical that loses its hydrogen, a ring-opening); **a radical whose optimized structure does not have the parent's heavy-atom connectivity minus the one hydrogen is a failed structure, not a low-energy one** (checked from the optimized distances, covalent radii + 0.4 Angstrom, the same test the proton-affinity runner uses for a proton that moved).

## The protocol, secondary arm

DLPNO-CCSD(T) single points, `! DLPNO-CCSD(T) def2-QZVPPD AutoAux TightPNO TightSCF`, frozen core as ORCA defaults it, on **every accepted structure within 4 kcal/mol in H of its species' lowest at the primary level**; `H = E(DLPNO) + (H(primary) - E(primary))`, so the thermal corrections are the DFT ones; then selection and the formula as above. The hydrogen atom's electronic energy is the same single point; **if ORCA refuses a one-electron system the unrestricted Hartree-Fock energy, which is exact for one electron in the basis, is used and the fact recorded.** The method's tight preset is TCutPNO 1e-7, TCutPairs 1e-5 [source:riplinger2013dlpno] [source:riplinger2013triples]; DLPNO from an unrestricted reference is not validated here for these radicals, which is one of the things the arm tests.

## The reading rule, fixed now (the code is `judge.py`)

For each arm, on the **25 deciding bonds**: mean absolute error (MAE), mean signed error (MSE), largest absolute error.
* **PASS**: MAE <= **2.5 kcal/mol (primary arm)** or **2.0 (secondary arm)**, **no error above 5.0**, and |MSE| <= **1.5**.
* **PARTIAL**: not PASS and MAE <= **3.5**.
* **FAIL**: otherwise.
* **NOT EVALUABLE**: more than **three** of the 25 have no computed value.
The 8 loose-reference bonds and all 33 together are **reported** in the same statistics and decide nothing.
**Where the thresholds come from**, approved by Alex on 2026-10-19 after the three papers below were read: M06-2X's published errors are 1.1 to 1.4 kcal/mol against experiment for aromatic X-H bonds [source:vo2022], **about 2.1 for this protocol (M06-2X/def2-TZVP enthalpies after a conformer search) on 368 experimental bond enthalpies** [source:stjohn2020], 1.83 against theory on 99 non-multireference bond energies and 6.3 on the multireference ones [source:mardirossian2017], and 0.74 on four alkyl bond energies (De) [source:zhao2008]; the reference's stated uncertainty for the deciding bonds is 0.008 to 1.0 with a median about 0.4. **A first proposal (2.0, 4.0, 3.0) was revised to the numbers above before approval**, because 2.0 sat below the 2.1 this protocol scored on a broad set; the revision is disclosed here and was made on the literature, not on any result of this benchmark. The thresholds rest on weaker footing than proton affinity's (no published M06-2X error for small-molecule X-H bonds specifically was found).

## What each verdict does (decided now)

* **PASS:** the calculator is built (a service-level sequence like the tautomer distribution's, experimental and needing approval at first) **with the protocol of the arm that passed**: the primary protocol is the default; the secondary arm is offered only as an optional high-accuracy mode and only if its own arm passed. It is offered **for X-H bonds of the kind in the benchmark** with the error found stated beside it.
* **PARTIAL:** the failing bonds are named; nothing is built; whether a calculation with a stated larger error is wanted is Alex's decision, made with the report.
* **FAIL:** nothing is built; the report and the reason are the deliverable.
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed (a missing-cell pattern usually names a protocol defect) and the benchmark re-run under a new preregistration.
* A result outside the thresholds is never explained away by hand: the diagnostics below say what they can, and the verdict stands.

## Reported, and in no rule

* Per bond: the error in both arms, the number of structures per species, the time per job.
* **Spin contamination:** the `<S**2>` of every radical's lowest structure, flagged above 0.80 (`bde_core.spin_contaminated`), and which bonds those are, as a check on whether the worst errors are the contaminated ones.
* **By class:** the errors of the C-H bonds, the O-H bonds, the other X-H bonds and the peroxides separately (Mardirossian's multireference warning makes the peroxides and HCN the cases to watch).
* The effect of lowest-structure against Boltzmann averaging within each species where more than one structure was accepted (a limitation measured, not corrected).

## What was seen first (disclosure)

**No job of this benchmark, and no ORCA calculation of a bond dissociation, has been run.** What was read before this file: Blanksby and Ellison's Table 1 (the reference), the four literature accuracy sources above, and, from the proton-affinity work, ORCA's frequency-block format and the thermochemistry output of a water and an H3O+ calculation (a different molecule set; nothing in them is a BDE).

## What it cannot say

* **Thirty-three X-H bonds of molecules of at most ten heavy atoms**: nothing about C-C, C-halogen, C-O or C-N bonds (a later preregistration), large or charged molecules, radicals as parents, metals, or anything in solution. A calculator validated here is validated for that kind of bond.
* **The reference is experimental with stated uncertainties of up to 1.0 kcal/mol in the deciding stratum** (median 0.4); an error of about that size is not shown to be the calculation's.
* **One DFT functional and one DLPNO setting**: a different functional or basis is a different protocol and needs its own run.
* **Harmonic-oscillator thermochemistry**: anharmonic and hindered-rotor effects are not treated.
* **The lowest structure, not a Boltzmann average**, and **a single radical start per parent conformer** (the lowest-numbered hydrogen deleted): a radical state reached only from another hydrogen's removal, or a different electronic state, is not tried.

## Records and refusals

Records are `artifacts/<stage>/<arm>.jsonl`, one line per job: the species, structure, the input's sha256, the ORCA version, the commit and whether `src/` was dirty, the seconds, the energy, H, the `<S**2>`, the lowest frequency, and any error. **A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`.** Each job has a 4-hour limit; a job that does not finish is a missing structure, never a pass. The run is one stage at a time (structures, primary jobs, secondary jobs, report) and resumes; it is not run while another long ORCA batch is using the machine's cores.
