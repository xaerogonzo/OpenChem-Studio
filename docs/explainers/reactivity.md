# Explainers: the reactivity calculators

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by
`tools/build_calculator_reference.py`; the format is documented in
`tools/calculator_explainers.py` and guarded by
`tests/test_calculator_explainers.py`. Every claim is one of three kinds and
says which: **published** (a registered source says it), **shipped** (what this
application's code does, read from the code) or **measured here** (a run on
2026-10-18 with ORCA 6.1.1 at B3LYP, on formaldehyde, propene and pyridine, each
at the geometry ORCA optimized at def2-SVP from an RDKit embedding; these runs
are exploration, not the preregistered gate in `benchmarks/fukui_gate/`).

## orca.fukui

### What it does
Says, atom by atom, where a molecule's electrons come from and go to when one is taken away or added, and so which atoms an attacking electrophile, nucleophile or radical is likely to meet. Four numbers per atom: **f+** (an electron added, the nucleophilic-attack function), **f-** (an electron removed, the electrophilic-attack function), **f0** (their mean, the radical-attack function) and the **dual descriptor** f+ - f-. It runs ORCA once, as three single points in one job (the neutral molecule, its cation and its anion), and compares an atom's charge in each.

### How it works
A condensed Fukui function is a finite difference of atomic populations between two states of the molecule at one geometry: f+ is an atom's population in the N+1-electron state minus its population in the N-electron state, f- is its population in the N-electron state minus the N-1 state, and f0 is half the N+1 minus the N-1 [source:olah2002] [source:thanikaivelan2002]. Written with atomic charges, which are the nuclear charge minus the population, each sign flips: this application's f+ is q(N) - q(N+1). All three are populations of the same atom in different states, so each of f+ and f- sums to 1 over the atoms.

Shipped: three single points in one ORCA input, in the order neutral, cation, anion, **all at the geometry as supplied** (the ions are not relaxed, so the numbers are vertical; optimize first if the drawn geometry is not good enough). The method and basis are the panel's. The species must be a closed shell (multiplicity 1): the cation and anion of an open-shell molecule each have more than one spin state, and nothing in the structure says which was meant, so it is refused. A charged closed-shell species is allowed; its ions are doublets. Each job echoes its own charge and multiplicity, and the parser accepts the three tables only in that order and only for the molecule's own atoms; a state whose atomic charges do not sum to its charge is refused, because that is the signature of one state's table read as another's.

**The charge scheme is Hirshfeld's, and only Hirshfeld's.** In it the electron density at every point is divided among the atoms in proportion to the densities of the free neutral atoms there. Those weights come from neutral atoms whatever the electron count of the molecule, so the population difference is exactly the response of the atom's share of the density, not a mixture of two different partitions [source:bultinck2007]. Where the weights themselves move with the electron count (Hirshfeld-I, Bader) the two forms differ, and that paper reports about 20% of the Hirshfeld-I population-difference values negative against about 2% for the other form [source:bultinck2007]. Measured here, ORCA prints five schemes for the same job and changing only the basis from def2-SVP to def2-SVPD moved the largest per-atom f+ by 0.011 to 0.023 for Hirshfeld, 0.067 to 0.107 for Loewdin, 0.106 to 0.222 for Mulliken, 0.051 to 0.210 for MBIS and 0.042 to 0.279 for CHELPG; Mulliken put 0.23 on each hydrogen of formaldehyde and about as much on the oxygen as on the carbon, where Hirshfeld puts 0.38 to 0.40 on the carbon; MBIS and CHELPG gave the carbon a negative f-. That Hirshfeld partitioning gives non-negative values where other schemes do not was reported before [source:roy1999].

### What the result means
One dimensionless number per atom for each function. They are descriptors of a particular partition of a particular calculation, not observables: the paper that compares the definitions concludes that different procedures give different values and that the choices an atom-condensed value needs in practice (which partition, which definition) are somewhat arbitrary [source:bultinck2007]. Compare atoms within one molecule at one method; do not compare numbers across schemes or levels of theory.

**f+ is the less trustworthy half.** A neutral closed-shell molecule has a negative electron affinity in a basis set without diffuse functions (all six cases measured here, from -1.06 to -3.02 eV), so its anion is a state the basis set only describes. The result says so, with the energy by which the anion lies above the neutral, whenever it is the case. Hirshfeld's f+ moved by at most 0.023 per atom when diffuse functions were added to the three molecules measured here, and its f- by at most 0.009, so the unbound anion is reported and not refused. The authors of the largest published table of Hirshfeld values say the same of f- against f+: generally steadier across basis sets and levels of theory [source:olah2002].

A negative value is the partition compensating, not an atom that loses density on gaining an electron; it is reported as it came out and flagged. No Hirshfeld f+ or f- was negative in any of the six runs measured here (three molecules, two basis sets).

### When to use it, when not
Use it to rank the atoms of one molecule as sites for a nucleophile, an electrophile or a radical, and to see how a substituent moves that ranking at one method. Check f+ with a basis set that has diffuse functions before leaning on it. A 2019 benchmark found the Fukui function the weaker descriptor, and weakest for nucleophiles. On seven molecules with experimentally established reaction sites, the Hirshfeld charge itself gave the site in all seven, while the Fukui function from none of 15 charge schemes did; with Hirshfeld charges it matched the established site for three of the four electrophilic attacks and one of the three nucleophilic ones (read from its Tables 1 and 2). Over 43 systems with experimental scales the Hirshfeld charge correlated with electrophilicity at R = 0.995 and with nucleophilicity at 0.988, the Fukui function at 0.905 and 0.344 [source:wang2019]. That study used M06-2X/6-311+G(d) with an implicit dichloromethane solvent, so it measures the descriptors and not this application's default level; it is the reason f+ and f- here are offered as a ranking of atoms within one molecule, not as a predictor of where a reaction goes.

Do not treat the largest value as a prediction of where a reaction goes: the authors of the largest published table of Hirshfeld values report that the atom with the largest value matched the experimentally known site in every case they tested, while noting that their own anion results were not predicted satisfactorily [source:olah2002], and the same scheme failed to pick the carbonyl carbon of acetaldehyde and acetone in another study [source:thanikaivelan2002]. Do not average it over conformers (it is computed for one geometry, and the conformer-averaging option is refused for it). An open-shell species is refused.

### Search for
Fukui function, dual descriptor, reactive site, Hirshfeld charges

### Sources
- [source:olah2002] -- the finite-difference definitions in populations, the four-decimal Hirshfeld tables used as reference, and the stability of f- against f+
- [source:thanikaivelan2002] -- the same definitions, the Hirshfeld formaldehyde table, and the acetaldehyde and acetone failure
- [source:bultinck2007] -- why the Hirshfeld population difference is the fragment response, and the negative-value rates of Hirshfeld-I
- [source:roy1999] -- non-negative values from Hirshfeld partitioning
- [source:wang2019] -- the benchmark of the Fukui function against the Hirshfeld charge, and its weakness for nucleophiles
