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
**Not yet read:** the 2024 benchmark of PA and GB values (*Proton affinity Revisited: Benchmarking computational approaches for accurate predictions*, a ScienceDirect article found by search and **not obtained**: Alex has the paywalled papers), which reportedly found B3LYP, BP86, PBEPBE and M062X very good with a slight advantage for M062X.
The **numeric thresholds of the gate are fixed from these sources and that paper**, after they are read and before any calculation.

## Decisions (Alex, 2026-10-19)

1. **PA and GB as two separate outputs**, each its own gate result, so GB can fail without taking PA with it.
2. **The level of theory: the benchmark's primary arm is M062X/def2-TZVPD** (optimization and frequencies at one level), and **a secondary arm, preregistered with its own gate, is a DLPNO-CCSD(T) single point on those same geometries** (the geometries and frequencies already exist, so the arm costs only the single points). Why both: the benchmark validates **the protocol the calculator will then run**, not a method in the abstract. A calculator that offers a two-level "high accuracy" mode needs that mode benchmarked, and
   one benchmarked at one level cannot vouch for another. So the cheap protocol is the calculator's default if it passes, and the two-level mode is offered only if its own arm passes. Which basis and PNO settings the DLPNO arm uses, and every numeric threshold, are fixed in the preregistration **after the 2024 benchmark paper (and a source for DLPNO-CCSD(T)'s own accuracy on proton affinities) have been read.**
3. **Benchmark first**, no application code until the gate has run.

**Needed from Alex:** the 2024 paper (*Proton affinity Revisited: Benchmarking computational approaches for accurate predictions*, ScienceDirect, article S2210271X24000161) so the thresholds can be fixed from it; with its DOI so the filename can be proposed (`feedback`: propose distinct filenames).
