# Explainers: the thermochemistry calculators

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by
`tools/build_calculator_reference.py`; the format is documented in
`tools/calculator_explainers.py` and guarded by
`tests/test_calculator_explainers.py`. Every claim is one of three kinds and
says which: **published** (a registered source says it), **shipped** (what this
application's code does, read from the code) or **measured here** (the
preregistered benchmark in `benchmarks/proton_affinity/`, run on 2026-10-20 with
ORCA 6.1.1 on commit 6ec0fd29; its record is `docs/PROTON_AFFINITY_DESIGN.md`).

## orca.proton_affinity

### What it does
Says how strongly a neutral molecule holds a proton in the gas phase. Two numbers, in kJ/mol, as NIST tabulates them: the **proton affinity** (PA), the enthalpy released when the molecule takes up a proton at 298.15 K and 1 atm, and the **gas-phase basicity** (GB), the Gibbs energy of the same step, which also carries the entropy of the proton and of both species. A molecule with several places a proton can go (an amine and a ring nitrogen, an oxygen and a nitrogen, a carbon of a pi system) has a value for each place; the result gives the best one, says which atom it is, and lists every site's own value, because a proton affinity belongs to a site.

### How it works
Shipped: the molecule and its conjugate acid at every candidate site are each optimized and given a frequency calculation with ORCA at M062X/def2-TZVPD (`! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`). The candidate sites are every nitrogen, oxygen, sulfur or phosphorus atom without a positive charge and every carbon of a C=C, C#C or aromatic bond (plus the carbon of carbon monoxide), sites that are equivalent by the molecule's symmetry counted once. Each species is embedded fresh from the 2D structure with ETKDG (seed 7, 30 conformers), relaxed with MMFF94, deduplicated by an all-atom RMSD of 0.5 angstrom, and the lowest three within 5 kcal/mol are optimized. A structure with any vibrational frequency below -20 cm-1 is re-run once from its final geometry with the Hessian calculated at the start, and dropped if it still has one; a conjugate acid in which the proton ends on anything but one atom of the base is dropped too. The proton has no electrons, so its enthalpy and Gibbs energy are the translational ones for an ideal gas, 1.4812 and -6.274 kcal/mol at 298.15 K and 1 atm, which is the standard state and the values used in the literature this was compared with [source:moser2010]. **ORCA's symmetry number is replaced by the true one**, counted from the molecule's proper rotations, because ORCA gave a C3v hydronium ion the number 1 (measured here: 0.65 kcal/mol in the Gibbs energy); this changes GB and never PA. Then PA is the enthalpy of the lowest base structure plus the proton's, minus the enthalpy of the lowest conjugate acid over every site, and GB the same with Gibbs energies, each chosen on its own. Nothing is averaged over conformers: the lowest structure stands alone.

The functional was chosen from the literature, not by trial: M06-2X was reported to have a mean unsigned error of 1.75 kcal/mol on eight small-molecule proton affinities against experiment, [source:zhao2008] and 1.2 against high-level theory on a larger set of 26 [source:goerigk2017]. The reference values are the evaluated proton affinities and gas basicities of Hunter and Lias, the numbers behind NIST's tables [source:hunter1998].

### What the result means
**It was measured, once, and each result states the measurement.** On the 21 of the 28 benchmark bases whose evaluated proton affinity is above propene's (the range where the evaluation is well established), the mean absolute error against NIST was **1.55 kcal/mol (6.5 kJ/mol) for PA and 1.53 for GB**, the largest error 2.94 and 2.99, and the **mean signed error -1.19 and -1.27: the calculation binds the proton about 1.2 kcal/mol too weakly on average**, a bias and not scatter. Both passed the rule fixed before the run (mean absolute error at most 2.5, no error above 5.0, mean signed error within 1.5). The evaluated values themselves are uncertain by about 8 kJ/mol (1.9 kcal/mol) for most entries [source:hunter1998], so an error of that size is not shown to be the calculation's. The seven weaker bases (carbon monoxide, ethene, water, hydrogen sulfide, hydrogen cyanide, formaldehyde, benzene) were computed and reported but decided nothing.

**A number can be missing.** A structure that keeps an imaginary vibration after its one re-run is dropped, and a base or acid with no accepted structure has no value: the benchmark lost water this way, because the hydronium ion optimized to a planar saddle point. The result then says which structures were dropped and why, and the missing quantity is an error and never a zero. PA and GB can be missing separately.

### When to use it, when not
Use it for a neutral base of at most ten heavy atoms of H, C, N, O, P and S, to compare two bases or two sites of one base, with the error above in mind. It is **refused** for a charged or radical species, a mixture, anything with another element (halogens, metals, silicon) and anything larger than ten heavy atoms, because the benchmark measured none of these and a number with no measured error is not offered. It is not a solution-phase basicity and not a pKa. It runs many ORCA jobs (one per structure: a base with three conformers and three sites is about a dozen), which takes minutes to hours, so it asks for approval before it starts and holds the molecule until it finishes or is cancelled.

### Search for
proton affinity, gas-phase basicity, protonation site, conjugate acid

### Sources
- [source:hunter1998] -- the evaluated proton affinities and gas basicities the calculation was measured against, and their stated uncertainty
- [source:moser2010] -- the standard state and the proton's enthalpy and Gibbs energy
- [source:zhao2008] -- the published error of M06-2X on eight proton affinities against experiment
- [source:goerigk2017] -- the published error of M06-2X on the PA26 set of proton affinities against high-level theory
