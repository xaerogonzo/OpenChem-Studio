# Explainers: the thermochemistry calculators

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by
`tools/build_calculator_reference.py`; the format is documented in
`tools/calculator_explainers.py` and guarded by
`tests/test_calculator_explainers.py`. Every claim is one of three kinds and
says which: **published** (a registered source says it), **shipped** (what this
application's code does, read from the code) or **measured here** (the
preregistered benchmark in `benchmarks/proton_affinity/`, run on 2026-10-20 with
ORCA 6.1.1 on commit 6ec0fd29; its record is `docs/PROTON_AFFINITY_DESIGN.md`; for the bond dissociation enthalpy, the benchmarks in
`benchmarks/bde/` and `benchmarks/restart_v2/`, whose record is `docs/BDE_DESIGN.md`).

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
Use it for a neutral base of at most ten heavy atoms of H, C, N, O, P and S, to compare two bases or two sites of one base, with the error above in mind. Outside that (a larger base, a halogen, silicon or a metal) it still computes, but asks first and labels the result an estimate to which the measured error does not apply. It is **refused** only for what the protocol cannot compute: a charged or radical species (every job is a neutral base and a +1 ion), a mixture, a base with no protonation site, or an element the basis set lacks. It is not a solution-phase basicity and not a pKa. It runs many ORCA jobs (one per structure: a base with three conformers and three sites is about a dozen), which takes minutes to hours, so it asks for approval before it starts and holds the molecule until it finishes or is cancelled.

### Search for
proton affinity, gas-phase basicity, protonation site, conjugate acid

### Sources
- [source:hunter1998] -- the evaluated proton affinities and gas basicities the calculation was measured against, and their stated uncertainty
- [source:moser2010] -- the standard state and the proton's enthalpy and Gibbs energy
- [source:zhao2008] -- the published error of M06-2X on eight proton affinities against experiment
- [source:goerigk2017] -- the published error of M06-2X on the PA26 set of proton affinities against high-level theory

## orca.bond_dissociation_enthalpy

### What it does
Says how much enthalpy it takes to break an X-H bond of a neutral molecule homolytically in the gas phase, leaving a radical and a hydrogen atom: the **bond dissociation enthalpy at 298.15 K**, DH298, in kJ/mol (and kcal/mol in the bond table), for the C-H, N-H, O-H or S-H bonds you choose. The headline is the weakest bond computed, the one a radical most easily takes; every chosen bond is listed with its own value, or with the reason it has none. It is never an electronic-energy difference and never D0. [source:blanksby2003]

### How it works
Shipped: `DH298(R-H) = H(R.) + H(H.) - H(RH)`, each H a total enthalpy at 298.15 K and 1 atm. The molecule and, for each chosen bond, the doublet radical it leaves are optimized and given a frequency calculation with ORCA at M062X/def2-TZVPD (`! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`, the radical unrestricted); the hydrogen atom is one single point of the same method, plus (5/2) kT for its translation. The molecule is embedded with ETKDG (seed 7, 30 conformers), relaxed with MMFF94, deduplicated, and its lowest three distinct conformers within 5 kcal/mol are optimized; **a radical's starting structures are those conformers with one hydrogen of the atom deleted**, so the optimizer begins from the molecule's own shape. The lowest-enthalpy structure of each species is used, with no averaging over conformers. A structure that keeps a vibration below -20 cm-1 is re-run once with an initial Hessian and dropped if it still has one, and a radical whose optimized bonds are not the molecule's minus that one hydrogen (it rearranged) is dropped as not being the radical of the bond. Equivalent atoms are one bond: methane has one C-H bond class, toluene four.

The functional was chosen from the literature: with this kind of protocol (M06-2X, a triple-zeta basis, enthalpies at 298 K after a conformer search) the mean absolute error against 368 experimental bond enthalpies was reported to be about 2.1 kcal/mol, the same as DLPNO-CCSD(T) [source:stjohn2020], and the functional is known to do worse on species with multireference character [source:mardirossian2017].

### What the result means
**It was measured twice, and each result states the measurement.** Measured here: the preregistered benchmark (`benchmarks/bde/`, 2026-10-21) computed 22 of its 25 deciding bonds against Blanksby and Ellison's experimental values [source:blanksby2003] and was PARTIAL, failing only its limit on the mean signed error (1.53 against 1.5 kcal/mol); a second, held-out set of 27 bonds chosen by rule from the Active Thermochemical Tables [source:atct1228] then PASSED (`benchmarks/restart_v2/`, 2026-10-23). Over the 49: **mean absolute error 1.48 kcal/mol (6.2 kJ/mol), mean signed error -1.38**: the calculation runs LOW, and only one of the 49 (HCN's C-H) is above its reference. By class: C-H 1.28 (32 bonds), N-H 1.02 (7), O-H 1.68 (4), and **an O-H next to another oxygen or a nitrogen (a peroxide, a hydroxylamine, an oxime) 3.30, all low, up to 4.57** (4 bonds; that class was separated after the results were seen). The bias is not subtracted: the preregistered test of whether the first run's offset reproduced on the held-out bonds said it did not (-1.25, interval -1.50 to -1.01), so a correction was not supported. Read a value as about 1.4 kcal/mol (6 kJ/mol) too low, and compare two bonds computed this way more confidently than one bond with experiment.

**A number can be missing.** A radical that keeps an imaginary vibration after its one re-run has no value, and the result names it and the frequency: the benchmark lost methanethiol's S-H this way (the CH3S radical optimized to a saddle point at -1306 cm-1), and a second protocol that displaces the structure along that vibration did not repair thiyl radicals and was not adopted. If the hydrogen atom's own job fails, no bond has a value and the run stops there.

### When to use it, when not
Use it for the X-H bonds of a neutral closed-shell molecule of at most nine heavy atoms of H, C, N, O and S, to rank the bonds of one molecule or compare similar bonds of two, with the error above in mind. Outside that (a larger molecule, another element, a bond of an unmeasured kind such as P-H) it still computes, but asks first and labels the result an estimate to which the measured error does not apply. It is **refused** only for what the protocol cannot compute: a charged or radical species, a mixture, a molecule with no X-H bond, or an element the basis set lacks. It does not compute C-C, C-O or other bonds between heavy atoms, and an S-H bond may have no value. Each chosen bond costs one radical optimization per conformer of the molecule; a run computes at most six bonds.

### Search for
bond dissociation enthalpy, BDE, homolytic cleavage, X-H bond

### Sources
- [source:blanksby2003] -- the experimental bond enthalpies the first benchmark was measured against, and the definition of DH298
- [source:atct1228] -- the Active Thermochemical Tables enthalpies of formation the held-out bonds were built from
- [source:stjohn2020] -- the published error of M06-2X with this kind of protocol on a large experimental set
- [source:mardirossian2017] -- the published behaviour of M06-2X on bond energies with and without multireference character
