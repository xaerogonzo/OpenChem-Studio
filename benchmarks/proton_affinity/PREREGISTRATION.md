# Proton affinity and gas-phase basicity from ORCA: preregistration

Written 2026-10-19, **before any job of the benchmark was run** (what was run, and seen, is listed under "What was seen first"). Design and the reading behind it: `docs/PROTON_AFFINITY_DESIGN.md`. The rule is the code in `judge.py` and the arithmetic is `pa_core.py`, both tested by
`tests/test_proton_affinity_benchmark.py` before any job exists; where this text and that code disagree, the disagreement is fixed before the run, never after. **Status: frozen on commit of this file with its runner** (the runner is written, tested and committed after this file and before the first job; this file changes only by an amendment section that says what and why).

## The question

Does ORCA, run as a stated protocol, give the gas-phase **proton affinity (PA, an enthalpy)** and **gas basicity (GB, a Gibbs energy)** of neutral bases at the accuracy the literature gives that method, against the NIST evaluated values? Measured, not shipped: **if the gate fails, the calculator is not built, and the failure and its reason are the deliverable.**
Two arms are judged separately, each for PA and for GB separately (four verdicts), because the benchmark validates the protocol a calculator would then run, and one protocol cannot vouch for another:
* **Primary arm:** M062X/def2-TZVPD optimization and frequencies, thermochemistry from them.
* **Secondary arm:** the same geometries and thermal corrections with the electronic energy replaced by a DLPNO-CCSD(T)/def2-QZVPPD single point.

## The data (fixed before any calculation)

`nist_values.json`: the proton affinity and gas basicity of **28 neutral bases**, the evaluated values of Hunter and Lias (1998) as the NIST WebBook lists them [source:hunter1998], kJ/mol at 298 K, fetched 2026-10-19. The 28 were **chosen by chemistry before any value was seen** (design note). Errors are computed - reference in **kcal/mol** (1 kcal = 4.184 kJ).
* **The deciding stratum is the 21 bases whose reference PA is above propene's (751.6 kJ/mol)**; the other seven (carbon monoxide, ethene, water, hydrogen sulfide, HCN, formaldehyde, benzene) lie where Hunter and Lias say the scale is not well established and **are reported, never deciding**. A base is in the low stratum by its reference **PA** (methanol, PA 754.3 and GB 724.5, is in the deciding one).
* The reference itself is uncertain by about **8 kJ/mol (1.9 kcal/mol)** for most entries (their Sec. 5.4), which is why no threshold below sits under it.

## The protocol, primary arm (everything here is fixed)

**Program and inputs.** ORCA 6.1.1. Every optimization and frequency job: `! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`, `%pal nprocs 4 end`, `%maxcore 3000`, charge and multiplicity 0/1 for a base and +1/1 for its conjugate acid. (A smoke run on water and H3O+ showed these keywords work and that ORCA's thermochemistry is at 298.15 K and 1.00 atm, with a **quasi-RRHO treatment of the vibrational entropy, Grimme's, reference frequency 100 cm-1, as ORCA 6.1.1's default**; that default is kept and is part of what is validated.)
**Structures.** Each species (the base and each candidate conjugate acid) is embedded with RDKit ETKDG (seed 7, 30 conformers), relaxed with MMFF94, **deduplicated by all-atom RMSD 0.5 Angstrom**, and the **lowest three within 5 kcal/mol (MMFF) are optimized** (fewer if fewer exist).
**Protonation sites, enumerated by rule and every one optimized.** A candidate is (a) every N, O, S or P atom with a lone pair and no positive charge, and (b) every carbon of a C=C, C#C or aromatic bond, plus the carbon of carbon monoxide; **sites equivalent by the base's graph symmetry are one site**. The conjugate acid of a candidate is the base with one more hydrogen on that atom (charge +1), embedded as above.
An optimization in which the added hydrogen ends bonded to a different heavy atom is **recorded as the site it ended on** (the heavy atom whose hydrogen count rose relative to the base, found from the optimized distances, covalent radii + 0.4 Angstrom) and merged with that site's other structures; a structure that loses the proton (the base plus a free H+ in the output) is a failed candidate.
**Frequencies.** A structure with any vibrational frequency **below -20 cm-1** (the allowance for numerical noise in soft modes; no literature number) is not accepted; it is **re-run once from its final geometry with `%geom Calc_Hess true end`** and dropped if it still has one. A base or acid with no accepted structure is a missing cell.
**Thermochemistry, per accepted structure:** the electronic energy, the total enthalpy H and the Gibbs free energy G of ORCA's output (298.15 K, 1 atm). **The symmetry number is overridden**: `pa_core.rotational_symmetry_number` (proper rotations found from the graph automorphisms and checked against the geometry, tolerance 0.05 Angstrom) replaces ORCA's, and G is corrected by `RT ln(sigma_true/sigma_ORCA)` (`symmetry_correction_eh`), because ORCA gave a C3v H3O+ the symmetry number 1 in the smoke run (0.65 kcal/mol in G, none in H). The number ORCA used, the number used here and the correction are recorded for every structure.
**Selection.** For **PA**: the base's structure of lowest H, and the lowest-H structure over all sites and conformers of the conjugate acid; for **GB**: lowest G (corrected) likewise, chosen independently of PA's choice. `PA = H(B) + H(H+) - H(BH+)` and `GB = G(B) + G(H+) - G(BH+)` with the proton's terms of `pa_core.proton_terms` (298.15 K, 101325 Pa): H(H+) = 1.4812, S(H+) = 26.012 cal/(mol K), G(H+) = -6.274 kcal/mol, derived from Sackur-Tetrode and agreeing with Moser, Range and York's printed values [source:moser2010]. No Boltzmann averaging over conformers (the lowest only; a stated limitation).

## The protocol, secondary arm

DLPNO-CCSD(T) single points, `! DLPNO-CCSD(T) def2-QZVPPD AutoAux TightPNO TightSCF`, frozen core as ORCA defaults it, on **every accepted structure within 4 kcal/mol in H (for GB, in G) of its species' lowest at the primary level, and for each conjugate acid every site within 4 kcal/mol of the lowest site**. `H = E(DLPNO) + (H(primary) - E(primary))`, likewise G, so the thermal corrections are the DFT ones; then selection and the formulas as above. The method's settings are its tight preset (TCutPNO 1e-7, TCutPairs 1e-5, tighter than the 3.33e-7 and 1e-4 defaults of its papers [source:riplinger2013dlpno] [source:riplinger2013triples]); a smoke run of water showed the keywords are accepted.

## The reading rule, fixed now (the code is `judge.py`)

For each arm and for each of PA and GB, on the **21 deciding bases**: mean absolute error (MAE), mean signed error (MSE), largest absolute error.
* **PASS**: MAE <= **2.5 kcal/mol (primary arm)** or **2.0 (secondary arm)**, **no error above 5.0**, and |MSE| <= **1.5**.
* **PARTIAL**: not PASS and MAE <= **4.0**.
* **FAIL**: otherwise.
* **NOT EVALUABLE**: more than **two** of the 21 have no computed value for that quantity and arm.
PA and GB are judged apart: **GB may fail without PA, and a missing PA does not take GB with it.** The seven low-basicity bases and all 28 together are **reported** in the same statistics and decide nothing. The thresholds rest on the published errors of these methods against theory and experiment and on the reference's own uncertainty (design note; Moser, GMTKN55's PA26 set, the M06 suite's PA8 and G3/05 [source:moser2010] [source:goerigk2017] [source:zhao2008] [source:curtiss2005]) and were approved by Alex on 2026-10-19; the 2024 benchmark paper could not be obtained.

## What each verdict does (decided now)

* **PASS:** the calculator is built (a service-level sequence like the tautomer distribution's, experimental and needing approval at first) **with the protocol of the arm that passed**: the primary protocol is the default; the secondary arm is offered only as an optional high-accuracy mode **and only if its own arm passed**. Each of PA and GB is offered only if its own verdict passed, with the error found stated beside it.
* **PARTIAL:** the failing cells are named; nothing is built; whether a calculation with a stated larger error is wanted is Alex's decision, made with the report.
* **FAIL:** nothing is built; the report and the reason are the deliverable.
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed (a missing-cell pattern usually names a protocol defect) and the benchmark re-run under a new preregistration.
* A result outside the thresholds is never explained away by hand: the diagnostics below say what they can, and the verdict stands.

## Reported, and in no rule

* Per base: the site the calculation chose against the site chemistry expects (ammonia, the amines, pyridine, imidazole N3, pyrimidine N, water, ethers, carbonyl oxygens, sulfur and phosphorus at the heteroatom, benzene and ethene at carbon, carbon monoxide at C; aniline and formamide reported without a prior), the number of structures per species, the errors in both arms, and the time per job.
* **Symmetry:** how often ORCA's symmetry number differed from the one used here and the size of the GB shift it caused.
* **GB - PA against the evaluators' protonation entropy** (Hunter and Lias tabulate Sp for many bases) where the NIST page carries one, a diagnostic for GB's entropy terms.
* The effect of lowest-structure against Boltzmann averaging within each species where more than one structure was accepted (a limitation measured, not corrected).

## What was seen first (disclosure)

A **keyword smoke run on water and H3O+** (M062X/def2-TZVPD Opt Freq in the scratch folder, not a record) and **one DLPNO single point of water** (a keyword check at an unoptimized geometry) were run before this file was written. Their numbers were seen: water H = -76.40397512 and H3O+ H = -76.66319385 Eh give PA(water) = 686.8 kJ/mol against the evaluated 691.0 (error -1.0 kcal/mol), and GB = 658.5 kJ/mol with ORCA's symmetry number
for H3O+ and 655.8 with the corrected one, against 660.0. **Water is in the low-basicity stratum and cannot decide**, and the benchmark recomputes it through the full protocol; but the number was seen, which is why this section exists. Nothing in the protocol or the thresholds was changed after seeing it, except that the symmetry-number override was added **because** of the H3O+ result, which is a correction of a defect and not a tuning of an outcome.

## What it cannot say

* **Twenty-eight neutral bases of at most ten heavy atoms**: nothing about larger or charged bases, bases with several conformationally coupled sites, radicals, metals, or anything in solution. A calculator validated here is validated for that kind of molecule.
* **The reference is an evaluation with about 1.9 kcal/mol uncertainty** (more, below propene): an error of that size is not shown to be the calculation's.
* **One DFT functional and one DLPNO setting**: a different functional or basis is a different protocol and needs its own run.
* **Harmonic-oscillator thermochemistry with ORCA's quasi-RRHO entropy**: anharmonic and hindered-rotor effects are not treated, and GB depends on them more than PA does.
* **The lowest structure, not a Boltzmann average**, and a **rule-based site list**: a site no rule enumerates is not tried.

## Records and refusals

Records are `artifacts/<stage>/<arm>.jsonl`, one line per job: the species, structure, the input's sha256, the ORCA version, the commit and whether `src/` was dirty, the seconds, the energies, H, G, the symmetry numbers, the lowest frequency, and any error. **A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`.** Each job has a 4-hour limit; a job that does not finish is a missing structure, never a pass. The run is one stage at a time (structures, primary jobs, secondary jobs, report) and resumes; it is not run while another long ORCA batch is using the machine's cores.
