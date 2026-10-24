# Proton affinity and gas-phase basicity from ORCA: design

**Status: proposal, 2026-10-19 (Phase 3, item 2 of the suite roadmap). Nothing is built and no calculation has been run.** The decisions that are Alex's are at the end. This note fixes what is being asked, the conventions, the policies that can dominate the answer, the order of work, and the
benchmark data already fetched; the gate's preregistration is written after the decisions, and its numeric thresholds only after the literature that sets them has been read.

## What is computed, and what is never claimed

For a neutral base B and its conjugate acid BH+ (gas phase):

* **Proton affinity, PA(B)** = -DeltaH of B + H+ -> BH+ at 298.15 K and 1 atm: `PA = H(B) + H(H+) - H(BH+)`. An **enthalpy**.
* **Gas-phase basicity, GB(B)** = -DeltaG of the same reaction: `GB = G(B) + G(H+) - G(BH+)`. A **Gibbs energy**, which carries the entropy of the proton and of both species and is the more convention-sensitive number.
* **The proton** has no electrons and no electronic energy, so only its translational terms enter, from the ideal-gas expressions: `H(H+) = (5/2)RT = 1.48 kcal/mol` (6.20 kJ/mol), `S(H+) = 26.02 cal/(mol K)` (108.9 J/(mol K), Sackur-Tetrode for a proton of mass m_p at the standard state), so `G(H+) = H - TS = -6.28 kcal/mol`.
  **Derived independently here** from the Sackur-Tetrode equation with CODATA constants and the proton mass (298.15 K, 101325 Pa): H(H+) = 6.1974 kJ/mol = 1.4812 kcal/mol, S(H+) = 108.836 J/(mol K) = 26.012 cal/(mol K), G(H+) = -6.274 kcal/mol (-26.25 kJ/mol); Moser's 1.48, 26.02 and -6.28 agree to 0.01 cal/(mol K) and 0.006 kcal/mol, which is below anything this check can see.
  These are the values and the standard state (298.15 K, 1 atm) that Moser et al. use against the same NIST data (*J. Phys. Chem. B* 114, 13911 (2010), their eqs 2 and 3 and the text after them), which is the reference implementation to check ours against.
* **PA and GB are separate outputs with separate names and conventions on each**, never one number: an electronic-energy difference between BH+ and B is **never labelled either**. A result states the temperature, the standard state, the proton terms used, the level of theory, the protonation site and the conformers behind it, and says it is a *microscopic* value for that site (see below).

## Where the numbers come from in ORCA

An `Opt Freq` job (already a calculation type, `opt_freq`) prints the electronic energy, the thermal enthalpy and Gibbs corrections from the rigid-rotor / harmonic-oscillator model at 298.15 K and 1 atm, and the total enthalpy and Gibbs free energy; `chem/orca_engine.py` already parses `orca.enthalpy`, `orca.entropy_term` and
`orca.gibbs_free_energy` (Hartree) from it. So PA needs **two optimization-plus-frequency jobs per candidate site (the neutral and the protonated species)** and the proton terms above: no new ORCA capability, a **sequence of jobs and a policy for which ones**.
What the harmonic model gets wrong (low-frequency torsions, methyl rotors: they move GB by tenths of a kcal/mol and PA much less) is a stated limitation, not corrected.

## The policies that can dominate the answer (and are tested, not just chosen)

* **Protonation site.** A base with several basic atoms has several BH+: aniline (N or a ring carbon), pyrimidine (two nitrogens), formamide (O or N), carbon monoxide (C or O), and the pi bases (benzene, ethene) that protonate on carbon. The candidate sites are **enumerated by atom type** (a lone-pair heteroatom N, O, S, P; a carbon of a pi system; the carbon of CO) and **every candidate is optimized**; the reported PA is for the **lowest-enthalpy (GB: lowest-Gibbs) converged site**, and the site that won is reported beside it and compared with the site the literature assigns. A candidate whose optimization collapses to another site is recorded as that site, never counted twice.
* **Conformers.** Each species (the neutral and each BH+) is searched (RDKit ETKDG plus MMFF, a fixed number, deduplicated) and the **lowest few are optimized and frequency-checked**; the lowest free-energy conformer is used, and only conformers that change PA or GB by more than 0.1 kcal/mol matter (Moser's rule, which they apply by Boltzmann averaging within the tautomer). A frequency job with an imaginary mode is **not** a result: it is re-run from the displaced geometry or refused.
* **Symmetry numbers and chirality** come from ORCA's own thermochemistry (it prints the symmetry number it used); a molecule it cannot assign one for is refused, not guessed.
* **Level of theory** is one stated model chemistry, optimization and frequencies at one level; **a result is only as good as the method**, and the gate below measures which.

## Order of work (each step behind the one before)

1. **A preregistered benchmark with no application code**: a script runs the protocol on a fixed set of bases (below) through the existing ORCA path and compares with the NIST values. **Measured, not shipped:** if the gate fails the calculation is not built, and the failure and its reason are the deliverable.
2. **Only then** the calculation in the application: a service-level sequence like the tautomer distribution's (one molecule slot for the whole run, cancel reaches all of it, a per-species failure recorded and the run continuing where the answer survives it), results as typed `PA` and `GB` outputs with their site table, an execution policy of **needs approval** (it is many ORCA jobs), stage **experimental** and **not validated** until the gate says otherwise, a help topic, an explainer, and a source-registry entry.
3. The reactivity-map recipe stays after Fukui and is not part of this.

## The benchmark data (fetched 2026-10-19, before any calculation)

`benchmarks/proton_affinity/nist_values.json`: the **proton affinity and gas basicity of 28 neutral bases** from the NIST Chemistry WebBook (NIST Standard Reference Database 69, gas-phase ion energetics), each the evaluated value of Hunter and Lias, *J. Phys. Chem. Ref. Data* 27, 413 (1998), in kJ/mol at 298 K.
**Chosen by chemistry before any value was seen**, to cover the families a user will ask about with one clear dominant site where possible and the hard cases on purpose: amines and N-heteroaromatics (ammonia, methyl-, dimethyl- and trimethylamine, pyrrolidine, pyridine, imidazole, pyrimidine, aniline), nitriles (acetonitrile, HCN), oxygen bases (water, methanol, dimethyl ether, tetrahydrofuran,
formaldehyde, acetaldehyde, acetone, formamide, acetic acid), sulfur and phosphorus bases (H2S, methanethiol, dimethyl sulfide, phosphine, trimethylphosphine), pi bases (benzene, ethene) and carbon monoxide (protonated on carbon). All have at most ten heavy atoms. All 28 returned a PA and a GB. Range 594.0 (CO) to 958.8 kJ/mol (trimethylphosphine).
**What the data cannot do:** the evaluated values carry their own uncertainty (Moser's table lists the NIST error estimates as 0.5 to 5 kcal/mol for their set), which sets how small an error can be called an error; the gate states that rather than treating them as exact.

## What the literature says about accuracy (read so far)

Moser et al. 2010 (their Table 1, errors calculated minus NIST in kcal/mol for CBS-QB3, G3B3, G3MP2B3, PBE0, B1B95, B3LYP and a B3LYP-only scheme) treat protonated amines and imidazoles as acids, so their rows for ammonium, methyl- and ethylammonium, imidazolium, pyridinium and pyrrolidinium **are the proton affinities (and GPB) of ammonia, methyl- and ethylamine, imidazole, pyridine and pyrrolidine**.
On those rows every model is within about 3 kcal/mol of NIST (ammonium within 1.2, methylammonium within 1.1, imidazolium within 1.9, pyridinium up to 3.0 and pyrrolidinium up to 2.9, the largest being a DFT value), and the text says the multilevel methods do better than the DFT ones, that PBE0 and B1B95 generally overestimate and B3LYP underestimates, and that basis sets without diffuse functions overestimate
the anions' values (their case) while those with them underestimate slightly. (I did not take their summary-statistics rows: the PDF text layer scrambles which row is which.) The paper also lists the NIST error estimates (0.5 to 5 kcal/mol) beside each experimental value, which bounds how small an error is distinguishable.
## Read 2026-10-19 (Alex supplied them): what Hunter-Lias and the DLPNO papers say that changes the design

**Hunter and Lias 1998** (the evaluation behind every NIST WebBook value here; 244 pages, Sections 2, 5 and 6 and Table A read):
* **Most values carry an uncertainty of about 8 kJ/mol (1.9 kcal/mol)**: the evaluators assign that to every molecule without its own root-sum-of-squares uncertainty (their Sec. 5.4). Table A lists the 25 bases whose proton affinities were determined absolutely or by their Sec. 5 procedure (trimethylamine, pyridine, dimethylamine, methylamine, ammonia, acetone, dimethyl ether and others), and **ammonia is the primary anchor of the whole scale**.
  **Consequence for the gate: an error below roughly 2 kcal/mol is not distinguishable from the reference's own uncertainty, so no threshold may be tighter than that and call the difference an error.**
* **"The scale of gas basicities is not yet well established in the low basicity region, below the basicities of compounds such as water and hydrogen sulfide"** (their Sec. 5.5); for that part of the scale, **below propene (PA 751.6 kJ/mol)**, "many of the suggested values are broad averages of rather disparate contributing values". In this benchmark set seven bases lie below propene: carbon monoxide (594.0), ethene (680.5), water (691.0), hydrogen sulfide (705.0), HCN (712.9), formaldehyde (712.9) and benzene (750.4).
  **So the gate reports its metrics for all 28 and separately for the 21 above propene and the 7 below, and the rule is fixed on the 21 (the region where the reference is established); the 7 are reported and cannot fail the gate on their own.** That choice is made here, before any calculation.
* **Several protonation sites are tabulated as separate entries** (carbon monoxide at C and at O, Registry Number suffixed `:a` and `:b`): the site policy above has a literature counterpart, and the benchmark compares with the entry of the site the calculation reports. Our NIST fetch for CO returned the C-site value (594.0, "at C").
* **The evaluated protonation entropy is tabulated** (Sp, in J/(mol K), for example 6.4 for ammonia, 8.7 for acetone, 16.5 for dimethyl ether): for the entropy of protonation of a molecule against an analogue the evaluators' own estimates can be compared with the computed T*(S(BH+) - S(B) - S(H+)) as a reported diagnostic of GB, not in a rule.
* Temperature: PA and GB are 298 K values; **relative values from van't Hoff analyses at other temperatures are applied unchanged** (heat capacity terms cancel within the uncertainty), so there is no temperature correction to emulate.

**Goerigk et al. 2017 (GMTKN55) and its SI**, the benchmark of ~200 functionals, read for the **PA26** set (26 adiabatic proton affinities, from H2 at 106.2 to guanine at 236.0 kcal/mol; references W2-F12 or W1-F12 for 12 small molecules and CCSD(T)/CBS(def2-TZVPP/QZVPP)//PBEh-3c for 14 larger ones (ethanol, acetic acid, glycine, phenol, cysteine, nucleobases and others); **zero-point-exclusive electronic values** at def2-QZVP):
the SI's per-functional tables (mean deviation MD, mean absolute deviation MAD, RMSD, in kcal/mol, calculated minus reference) give for PA26 **M06-2X (D3(0)): MD -0.33, MAD 1.23, RMSD 1.52** (M06-2X without dispersion: MD -0.35, MAD 1.24), **B3LYP: MD +2.16, MAD 2.28, RMSD 3.12** (B3LYP-D3(BJ): MAD 2.87), **PBE0: MAD 2.56** (PBE0-D3(BJ): MAD 2.88), PBE 1.97, BLYP 2.44, MN15 1.64, and the double hybrids best, B2PLYP 1.14, DSD-BLYP 0.95 and DSD-PBEP86 0.98.
(**Read by word coordinates and one page checked against its image** (M06-2X-D3(0), Table S89): the PDF's plain text layer interleaves neighbouring rows, and the first reading of these tables took the MD of the row above (DIPCS10's -0.69) for M06-2X's and the sign of B3LYP's MD backwards; both were corrected here, and the MADs were not affected. The omega-B97X rows were not re-read and are not used.)
**These are errors against high-level THEORY for the electronic proton affinity, not against experiment and not including thermal terms**, so they bound the method's own error from below.

**Zhao and Truhlar 2008 (the M06 suite), Table 4, PA8** (eight small-molecule proton affinities **against experiment**, zero-point-exclusive, 6-311+G(2df,2p) at MP2 geometries; mean signed and unsigned error, kcal/mol; read from the page image, because the text layer scrambles this table and a first reading of it, now corrected, gave several rows the values of their neighbours): **M06-2X MSE -0.19, MUE 1.75**; **B3LYP MSE 0.18, MUE 1.02**; PBE MSE 0.04, MUE 1.35; BMK -0.49 and 1.07; B98 1.44 and 1.44; M05-2X -0.25 and 1.23; HF 2.75 and 3.19; the average over the density functionals is MUE 1.83.
**Curtiss, Redfern and Raghavachari 2005 (G3/05), Table IV, "Proton affinities" (10 molecules, against experiment, kcal/mol MAD):** G3 1.14, G3X 1.04, **B3LYP 1.39**, B98 1.07, B97-2 2.25, B1B95 1.32, O3LYP 1.76, VSXC 1.96, TPSS 1.94 (DFT single points 6-311+G(3df,2p) at MP2/6-31G* geometries with scaled HF zero-point energies).
**Safi and Fares 2018** (the book chapter, in *Conceptual Density Functional Theory and Its Application in the Chemical Domain*) is a B3LYP and BP86 study of polyfunctional heterocycles (hydantoin, rhodanine, benzamide and derivatives); its relevant statements are a literature summary (B3LYP proton affinities "comparable up to 1-2 kcal/mol" with measured values) and **PA and GB are site-specific: each chemically different binding site has its own value**, the same site policy as above. It benchmarks no neutral-base set of ours. **Nacsa and Czako 2022** is a CCSDT(Q)-level determination for **cysteine alone** (85 neutral conformers; PA 214.96 and GB 208.21 kcal/mol for N-protonation at the 298.15 K best estimate); it is a reference for one amino acid and shows what "more than the lowest conformer" costs, not a benchmark set.

**What this gives the gate's thresholds** (proposed here, **to be frozen only on Alex's approval**): for M06-2X the published error is **1.2 kcal/mol against theory (PA26) and 1.75 against experiment (PA8)**; the reference's own uncertainty is **about 1.9 kcal/mol**; B3LYP's published errors are 1.0 against experiment (PA8), 1.4 (G3/05) and 2.3 against theory (PA26). **The thresholds proposed and approved (2026-10-19) were built on a first reading of these tables that had B3LYP's and PBE's PA8 errors wrong (2.16 and 1.98, in place of 1.02 and 1.35); the corrected numbers lie inside the approved bands, so the thresholds stand, but the correction is recorded because the approval was given on the wrong numbers.** A benchmark of the protocol (geometries and frequencies at one level, the 298 K thermal terms) against NIST should therefore be expected to land near **2 kcal/mol**, and a threshold must not sit below the reference's own noise.
**Proposed rule for each of PA and GB, on the 21 bases above propene (the 7 below are reported and cannot decide):** **PASS** if the mean absolute error is at most **2.5 kcal/mol (10.5 kJ/mol)**, no single error exceeds **5 kcal/mol (21 kJ/mol)** and the mean signed error is within **1.5 kcal/mol**; **PARTIAL** if the mean absolute error is at most **4 kcal/mol (16.7 kJ/mol)**; **FAIL** otherwise; **NOT EVALUABLE** if more than two of the 21 are missing. **The DLPNO-CCSD(T) arm** (single points on the same geometries and frequencies) is judged by the same rule with a mean absolute error of at most **2.0 kcal/mol (8.4 kJ/mol)** for PASS, because its own error (0.5) is below the reference's noise and a better method should show it. These numbers rest on the sources above and **no calculation**; the 2024 benchmark, if it arrives, can move them only before the preregistration is frozen.

**Riplinger and Neese 2013 (DLPNO-CCSD) and Riplinger, Sandhoefer, Hansen and Neese 2013 (natural triples)**, read for the secondary arm:
* The **default thresholds** are TCutPNO = 3.33e-7, TCutPairs = 1e-4 and TCutMKN = 1e-3, and for the triples TCutTNO = 1e-7; with them about 99.8% of the correlation energy is recovered (99.95% for CCSD with the MP2 correction), and **the method reproduces canonical results to about 0.5 kcal/mol for a challenging test set of medium-sized organic molecules**, "better than chemical accuracy" (1 kcal/mol) for reaction energies (their mean absolute deviations for the test reactions are 0.3 to 0.5 kcal/mol, with a maximum above 1).
* The error **is extensive**: it grows with system size, and the triples correction can reach 4 kcal/mol, which is why the triples are not optional for a number that is to be a few tenths of a kcal/mol.
  **Consequence:** a proton affinity is a small-molecule reaction energy between a neutral and an ion of the same size, the case these papers' tests resemble; the secondary arm uses ORCA's `TightPNO` (tighter than the default) unless a cost measurement says otherwise, and its single points use a basis fixed in the preregistration. DLPNO's own error (about 0.5 kcal/mol) is **below** the reference's uncertainty (about 1.9 kcal/mol), so the arm can be judged against the same reference.

**Not obtained:** the 2024 benchmark of PA and GB values (*Proton affinity Revisited: Benchmarking computational approaches for accurate predictions*, Mathew, Puchta and Thomas; **Alex could not get it, 2026-10-19; it is on the wanted list** with alternatives), which reportedly found B3LYP, BP86, PBEPBE and M062X very good with a slight advantage for M062X.
The **numeric thresholds of the gate are fixed from these sources and that paper**, after they are read and before any calculation.

## Decisions (Alex, 2026-10-19)

1. **PA and GB as two separate outputs**, each its own gate result, so GB can fail without taking PA with it.
2. **The level of theory: the benchmark's primary arm is M062X/def2-TZVPD** (optimization and frequencies at one level), and **a secondary arm, preregistered with its own gate, is a DLPNO-CCSD(T) single point on those same geometries** (the geometries and frequencies already exist, so the arm costs only the single points). Why both: the benchmark validates **the protocol the calculator will then run**, not a method in the abstract. A calculator that offers a two-level "high accuracy" mode needs that mode benchmarked, and
   one benchmarked at one level cannot vouch for another. So the cheap protocol is the calculator's default if it passes, and the two-level mode is offered only if its own arm passes. Which basis and PNO settings the DLPNO arm uses, and every numeric threshold, are fixed in the preregistration **after the 2024 benchmark paper (and a source for DLPNO-CCSD(T)'s own accuracy on proton affinities) have been read.**
3. **Benchmark first**, no application code until the gate has run.

**Still open:** the 2024 paper could not be obtained, so the thresholds are fixed from Moser et al. (DFT and multilevel errors against NIST), from the references' own stated uncertainty (about 1.9 kcal/mol) and from the DLPNO papers, unless an alternative DFT benchmark arrives; the preregistration states exactly what each number rests on.

## Result: the primary arm was run on 2026-10-20 and PASSED, for PA and for GB

Run on commit `6ec0fd29f72945b1f708d67dfe95050fb20656bc` (master after #392), clean `src/`, one commit for every record, ORCA 6.1.1, `run --workers 3 --cores 4`, nothing else heavy on the machine. **Wall time 11 h 49 min** (started 08:23, last record written 20:12:09, 42,526 s, on 2026-10-20; the jobs' own seconds sum to 34.9 h, which over three workers is 11.6 h, so the wall time is the work and not a pause). 77 jobs for the 74 structures (three were re-runs with `Calc_Hess`), 73 structures accepted. Longest job: aniline's C-protonated ion, 2.5 h (limit 4 h). The records are `benchmarks/proton_affinity/artifacts/primary/runs.jsonl`; the report and verdict are beside them (committed with `git add -f`; the ORCA outputs themselves were not kept).

The judge's output (preregistered rule, unchanged), kcal/mol, on the 21 deciding bases (reference PA above propene's):

| | MAE | MSE | largest | missing | verdict |
|---|---|---|---|---|---|
| PA, 21 deciding | 1.55 | -1.19 | 2.94 | 0 | **PASS** (needs MAE <= 2.5, max <= 5.0, \|MSE\| <= 1.5) |
| GB, 21 deciding | 1.53 | -1.27 | 2.99 | 0 | **PASS** |
| PA, 7 low (reported only) | 1.80 | -1.75 | 4.34 | 1 | decides nothing |
| GB, 7 low (reported only) | 1.83 | -1.69 | 4.37 | 1 | decides nothing |

The error is **systematic, not scatter**: the mean signed error is negative (the calculation underbinds the proton by about 1.2 to 1.3 kcal/mol on average), and |MSE| = 1.19 for PA is closer to its 1.5 limit than the MAE is to 2.5. Every deciding PA error lies within 2.94. The calculated site is the chemically expected one for every base (amines, pyridine and pyrimidine at N, imidazole at N, ethers and carbonyls at O, H2S/CH3SH/Me2S at S, phosphines at P, benzene and ethene at C, CO at C). Among the largest PA errors are acetic acid (-12.3 kJ/mol), ammonia (-9.1), dimethyl ether (-8.6) and formamide (+8.5); the reference itself is uncertain by about 8 kJ/mol, so most of these are not shown to be the calculation's.

**Disclosures (what the run did that the notes did not predict):**
* **Water has no computed value.** Its H3O+ optimized at M062X/def2-TZVPD from the runner's RDKit start to a planar, D3h-like geometry with a vibration at -601.6 cm-1; the `Calc_Hess` re-run kept it (-601.6), so by the preregistered rule it was dropped and water's PA and GB are missing cells. Water is in the low stratum, so the verdict is unaffected (one of seven missing; the judge allows two of the 21 deciding). The smoke run recorded in the preregistration got a real C3v H3O+ from a different start, so this is a start-geometry effect of the protocol, not of the method. **It was not repaired**: a retry from a symmetry-broken start would be a protocol change; if a calculator is built, water and other tiny ions are a case to handle in its design.
* Two other structures (pyrrolidine's N-protonated ion at -50.6 cm-1, acetic acid's carbonyl-protonated ion at -68.9 cm-1) failed the -20 cm-1 rule once and passed after the `Calc_Hess` re-run, as designed.
* The structure count is 74 as the notes say, but its split is 29 bases and 45 conjugate-acid starts rather than the 28 and 46 written above: tetrahydrofuran has two distinct base conformers within the window, and its ion therefore has two starts too (the note's breakdown miscounted; the total, and the 28 bases, stand).
* **Symmetry numbers:** ORCA's differed from the one used here in 25 of 73 accepted structures (ORCA reports 1 for most C2v/C3v molecules). The GB shifts range from +0.41 to +1.47 kcal/mol (ammonium +1.47, benzene +1.06); the PA is not affected by the override, GB is (by up to those amounts per species, in the direction the species' role sets). The override was a preregistered part of the protocol.
* The preregistration also lists three reported-only diagnostics that `run_pa.py report` does not produce (GB - PA against the evaluators' protonation entropy, lowest-structure against Boltzmann averaging, time per job by base). They were not computed after the fact by hand; the per-job seconds and the full records are in the committed jsonl.
* The peak load was not measured; the configuration requested 12 cores (3 workers x 4) and `%maxcore 3000` per core, so up to about 9 GB.

**What this does under the preregistration:** the primary arm passed for each of PA and GB, so the calculator may be built with the primary protocol as its default, each of PA and GB offered with the error found stated beside it (MAE 1.5, systematic -1.2 kcal/mol, on bases of at most ten heavy atoms). The secondary DLPNO-CCSD(T) arm is a **later stage and was not written or run**; it needs Alex's go. Nothing was built.

## Exploratory rerun of water's H3O+ (2026-10-21; not a benchmark record)

Re-optimizing H3O+ from a geometry displaced 0.15 Angstrom along its -601.6 cm-1 mode gave a real minimum in either direction (lowest mode 0.0), H = -76.66319626 Eh, which matches the preregistration's smoke-run value (-76.66319385); so water's missing cell was a starting-geometry effect, as the disclosure above said. This does not change the verdict (water is a reported-only base); see `benchmarks/restart_diagnosis/` and the draft `benchmarks/restart_v2/PREREGISTRATION.md`.

## To run the primary-arm ORCA benchmark (as recorded 2026-10-19, before the result above)

The runner is written, tested on real water and H3O+ output and committed (`benchmarks/proton_affinity/run_pa.py`, `tests/test_proton_affinity_runner.py`); (as written before the run; it has since been run, see above). It builds 74 structures (28 bases and 46 conjugate-acid starts over every rule-enumerated site; `structures` prints the count) of M062X/def2-TZVPD `Opt Freq`, each a few minutes to some tens of minutes at 4 cores (the duration of the whole run is **unmeasured**; the water smoke job took minutes).

From the repository root, on the commit the preregistration froze (no edit to `src/` between the first job and the report, or the report is refused), with nothing else using the cores:

```bash
uv run --no-sync python benchmarks/proton_affinity/run_pa.py structures
uv run --no-sync python benchmarks/proton_affinity/run_pa.py run --workers 3 --cores 4     # resumable: run it again after an interruption
uv run --no-sync python benchmarks/proton_affinity/run_pa.py status
uv run --no-sync python benchmarks/proton_affinity/run_pa.py report                        # report.txt, verdict.json
```

Rules that go with it: one stage at a time; never edit a threshold or a rule after the report is seen (an amendment section, disclosed); **the secondary DLPNO arm is a later stage, written and run only if the primary arm passes** (stage order, not a rule change); a failed or partial verdict is the deliverable, as the preregistration says. Machine capacity: `--workers 3 --cores 4` assumes 12 free cores and about 9 GB of RAM (`%maxcore 3000`).

## Driven through the application on real ORCA, and promoted to LIMITED (2026-10-23)

`benchmarks/visual/proton_affinity_run.json` drives the real window: the real **Proton affinity...** button, real ORCA 6.1.1, and the values read back from the STORED result, the stored run and the panel's text. It was run twice, both **VERDICT PASS, 5 of 5 assertions, no application error**:

| | 2026-10-22, commit `b41c2e93` (#429) | 2026-10-23, commit `fb65056a` (master, clean tree) | benchmark |
|---|---|---|---|
| chloromethane | refused before anything was queued | refused before anything was queued | out of scope |
| ammonia PA / GB (kJ/mol) | 844.5166 / 810.1305 | 844.5166 / 810.1305 | 844.5166 / 810.1305 |
| methylamine PA / GB | 890.8002 / 856.3339 | 890.8002 / 856.3339 | 890.8003 / 856.3341 |
| water | no value, the planar H3O+ named | no value, the planar H3O+ named | no value |

The first of these runs found a defect no unit test had reached (the Runs history raising on a stored run with no value), fixed in #429. The second was made on the commit the promotion was made from, after the service gained the bond-dissociation sequence beside this one.

**What the promotion is.** `orca.proton_affinity` was EXPERIMENTAL and hidden for one stated reason: the benchmark passed, but this implementation had not been driven through the application on real ORCA. With that recorded it is **LIMITED and shown by default** (`docs/CALCULATOR_MATURITY.md`: a promotion is one change carrying the metadata, the evidence and the changelog entry). It is LIMITED and not STABLE because the scope is narrow (neutral closed-shell bases of at most ten heavy atoms of H, C, N, O, P and S) and one preregistered benchmark is not the independent, held-out, stratified result STABLE asks for. Its execution policy is unchanged: a model may not start it without a person's approval.
