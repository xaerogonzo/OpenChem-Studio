# Explainers: the partial-charge family

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by
`tools/build_calculator_reference.py`; the format is documented in
`tools/calculator_explainers.py` and guarded by
`tests/test_calculator_explainers.py`. Every claim is one of three kinds and
says which: **published** (a registered source says it), **shipped** (what this
application's code does, read from the code) or **measured here** (a run on
2026-10-11, on one RDKit-embedded, MMFF94-relaxed conformer per molecule, seed 7).

## geometry_partial_charge

### What it does
Puts a partial charge on every atom of a 3D conformer, by one of three published models that share one idea: **electronegativity equalization**. Each atom tends to pull electrons toward itself, and the more negative it becomes the less it wants more. The molecule settles where every atom pulls equally hard, and the charges that achieve that are the answer. Because the pull between charges depends on distance, the result depends on the conformer's geometry, which a drawing-only method cannot do.

### How it works
The three models differ in their parameters and in how the pairwise term is written, but they solve the same kind of problem. Each atom type carries a parameter pair, an effective electronegativity and a hardness (how steeply its pull rises as it gains charge). The electronegativity of atom i in the molecule is its own parameter, plus a term proportional to its own charge, plus the electrostatic potential from every other charge, which falls off with distance. Requiring all atoms to end at the same electronegativity, together with the charges adding up to the molecule's net charge, gives N + 1 linear equations for N charges and the shared electronegativity [source:bultinck2002a]. Solving them is the whole calculation, which is why it is fast: the paper reports 12 neuroleptic structures in under 50 ms [source:bultinck2002a]. This is Sanderson's electronegativity-equalization principle in the formalism of Mortier and co-workers [source:bultinck2002a].

Shipped, for all three: the conformer's own atoms, explicit hydrogens and net formal charge are used as stored, nothing is protonated or moved, and the net charge is spread over the whole molecule rather than left on the atom that was drawn charged. A molecule with hydrogens only implied, or whose hydrogens have no coordinates, is refused, and so is a pair of atoms closer than 0.1 angstrom. Each refusal is the calculator declining to guess; it never substitutes another model's answer. Tick *pH-dependent* to compute on the dominant ionization state at a pH instead of as drawn; only added hydrogens are placed and every other atom keeps its coordinates.

### What the result means
One charge per atom, in units of the elementary charge. Atomic charges are not physical observables: there is no unique definition, and a model's number is only as meaningful as what it was built to reproduce [source:ionescu2013]. Only the **sum** of the charges is constrained, and it equals the net charge exactly (measured here: ethanol, acetate, nitromethane, chloromethane and dimethyl sulfone summed to the net charge to six decimals under every model that accepted them). A correct sum is necessary and proves nothing about how the charge is distributed.

The same atom gets quite different numbers from different models. Measured here, the oxygen of ethanol: EEM -0.58, QEq -0.67, Ionescu 6-31G* -0.82, Ionescu 6-31G** -0.76 (and Gasteiger -0.40, MMFF94 -0.68 from the other charge calculator). None of these is more right in general; compare one model across molecules, not models against each other.

### When to use it, when not
Use it when you want charges that respond to the conformer's shape and need only a few seconds, for instance to colour a structure, to feed the dipole calculator, or to see how a conformational change moves charge. Pick by what each model was built for (see its method below) and by what it refuses. Do not use it as a substitute for a quantum-chemical calculation when the number matters, do not compare values across models, and do not read a number outside the element set of the model you chose as meaningful: a refusal is the model telling you that.

### Search for
electronegativity equalization, EEM charges, QEq charge equilibration, partial atomic charges

### Method: eem_bultinck2002_part1

#### How it works
The EEM of Mortier and co-workers with Bultinck et al.'s 2002 parameters. Their effective electronegativity and hardness for hydrogen, carbon, nitrogen, oxygen and fluorine were calibrated by weighted least squares against Mulliken charges from B3LYP/6-31G* calculations on a training set of 138 small organic molecules (930 hydrogens, 602 carbons, 105 nitrogens, 101 oxygens, 65 fluorines) [source:bultinck2002a]. The method therefore reproduces *those* quantum charges, not an independent truth about the molecule.

Shipped: exactly those five elements and that parameter table. Any other element is refused by name; it is never given a neighbour's parameters.

#### What the result means
Charges that approximate what a B3LYP/6-31G* Mulliken analysis would give for molecules like the training set. Mulliken charges themselves depend heavily on the level of theory and basis set: the Gasteiger-Marsili paper's own example is the hydrogen of methane, whose population-analysis charge differs by a factor of about 15 and even in sign across levels of theory [source:gasteiger1980]. Measured here against experimental dipole moments (15 molecules of Gasteiger and Saller's Table I [source:gasteiger1985], on OpenChem conformers), dipoles from these charges have a mean absolute error of 1.79 D over the 14 molecules EEM covers, and overestimate polar molecules.

#### Sources
- [source:bultinck2002a] -- the equations, the parameter table, the training set and its size
- [source:gasteiger1980] -- Mulliken charges' dependence on method and basis set
- [source:gasteiger1985] -- the experimental dipole moments the application's benchmark used

### Method: qeq_rg1991_lambda_half_h_experimental

#### How it works
Rappé and Goddard's charge equilibration. Instead of fitting parameters to quantum charges it takes experimental atomic data (ionization potentials, electron affinities and atomic radii), builds an atomic chemical potential from them, and requires all chemical potentials to be equal [source:rappe1991]. Its distinguishing feature is that the electrostatic interaction between atoms is **shielded**: each atom is a Slater orbital with a finite size, so two nearby charges do not interact as point charges. Mortier's EEM, by comparison, uses the unshielded Coulomb potential and fits to Mulliken charges from small STO-3G calculations [source:rappe1991]. Hydrogen is a special case: the paper redefines its electronegativity and lets its orbital size and hardness depend on its own charge, so hydrogen's charge is found iteratively [source:rappe1991].

Shipped: the 16 elements of the paper's Table I; the lambda = 1/2 reading of the shielding (equation 17') and the experimental hydrogen parameter set, one of several readings the paper leaves open, fixed in advance in `benchmarks/charges/rappe_goddard/preregistration.md` (amendment A8). Each charge is bounded by the valence-electron range the paper writes out for Li, C and O (from -(8 - v) to +v for v valence electrons) and that this application derives by the same rule for the other elements. The calculator refuses when the hydrogen iteration does not settle, and when the final solution needs an atom held at a charge bound.

#### What the result means
Charges that equalize chemical potential for this geometry, from atomic data rather than a fit to a quantum calculation. They are not validated against any quantum method here beyond the recorded benchmark scope. Measured here against experimental dipole moments (the same 15 molecules), dipoles from these charges have a mean absolute error of 1.69 D and overestimate polar molecules. A single conformer of dimethyl sulfone gave a slightly negative sulfur (-0.10) where Gasteiger and MMFF94 give a positive one: no refusal fired, and a number that is returned is not thereby shown to be reasonable.

#### Sources
- [source:rappe1991] -- the method, the parameters, the shielding, the hydrogen treatment, and the comparison with Mortier's EEM
- [source:gasteiger1985] -- the experimental dipole moments the application's benchmark used

### Method: eem_ionescu2013_e_mpa_631gs_gas, eem_ionescu2013_e_mpa_631gss_gas

#### How it works
Ionescu et al.'s 2013 models are EEM models fitted for proteins. They use large protein fragments as the reference structures and fit the parameters to Mulliken charges at the Hartree-Fock level, with 6-31G* or 6-31G** and in the gas phase for the two shipped here; the paper parametrized and validated 24 such models over three population analyses, two basis sets and two environments [source:ionescu2013]. The equation is not Bultinck's: it carries an adjusting factor k on the Coulomb term [source:ionescu2013], and this application reads the distance there in angstrom, the reading that reproduces the paper's own results (36 of 36 model-by-dataset rows; bohr reproduced none; see `benchmarks/charges/models/ionescu_src_preregistration.md`). In the shipped parameter table some elements have a negative effective hardness (checked in that pre-registration, not stated in the paper), so for a molecule that contains one of them the charges returned are the model's unique stationary point and not an energy minimum; the result says so.

Shipped: 2 of the paper's 24 models, the Mulliken gas-phase ones, for H, C, N, O, S and Ca. Anything the model has no parameters for is refused. A sulfur bonded to oxygen is refused as well, because every sulfonamide, sulfone and sulfoxide measured came out wrong by 0.84 to 1.75 e, several with the wrong sign, at magnitudes no charge bound catches. Any charge beyond 2.051 e (the largest on the protein fragments the model was validated on) is refused as a runaway solve.

#### What the result means
Charges that reproduce Hartree-Fock Mulliken charges on proteins. The paper reports, tested on insulin and ubiquitin, an average correlation of 0.961, RMSD of 0.097 e and average absolute error of 0.072 e across its 24 models [source:ionescu2013]. On a molecule that is unlike a protein this is an extrapolation, and every result is labelled as one: it can be wrong in sign without any refusal. Measured here, nitromethane's nitrogen came out negative (-0.42 and -0.49 e) under these two models where EEM, QEq, Gasteiger and MMFF94 all give a positive one.

#### Sources
- [source:ionescu2013] -- the models, their reference charges, their validation numbers and the negative-hardness behaviour

## gasteiger_charge_at_ph

### What it does
Estimates a partial charge on each atom from the 2D drawing alone, with no conformer, after first choosing the form of the molecule that predominates at a given pH. A carboxylic acid is computed as the carboxylate at pH 7.4, and an amine as the ammonium, so the charges describe the species that is actually there. Two models are offered, and they are different models, so they give different numbers for the same atom.

### How it works
First the dominant protonation state at the chosen pH is chosen with Dimorphite-DL [source:dimorphite_dl]. It gives ionization states only: it does not move protons between atoms to make a different tautomer, and an amide nitrogen reported as protonated is corrected, because its lone pair is delocalised into the carbonyl. Then the charge model runs on that structure. The result is stored under the method you chose, so a Gasteiger result is never served as an MMFF94 one. The choice of *Increment of Hs* folds each added hydrogen's charge onto its heavy atom; that is an aggregation this application performs, not a property of either model.

### When to use it, when not
Use it for a quick, conformer-free picture of where charge sits on the form of the molecule present at a pH, for example before docking or when comparing how ionization moves charge. Use the 3D calculator when geometry matters. Neither model here sees the 3D shape, and neither is a substitute for a quantum calculation.

### Search for
Gasteiger charges, PEOE, MMFF94 charges, protonation state

### Sources
- [source:dimorphite_dl] -- the tool the application calls to choose the dominant protonation state (cited for provenance only; its algorithm is not described here)

### Method: gasteiger

#### How it works
Gasteiger and Marsili's partial equalization of orbital electronegativity (PEOE). Each atom's orbital electronegativity is a quadratic function of its charge, a + b q + c q squared, with coefficients from ionization potentials and electron affinities [source:gasteiger1980]. Complete equalization is chemically wrong (every atom of one kind would get the same charge, so all four hydrogens of acetic acid would match), so charge is moved only **partly**: along each bond, from the less to the more electronegative atom, in proportion to the difference, with the amount damped by one half at the first iteration, one quarter at the second and so on. Total charge is preserved at every step, and in the paper the transfer falls below 0.001 e by the fourth or fifth iteration [source:gasteiger1980]. It uses only which atoms are bonded; geometry plays no part.

Shipped: RDKit's implementation of this iteration, at RDKit's default of 12 rounds (the paper stops at 6), on the protonated drawing. It is a sigma-charge method: it has no pi component, so a sigma/pi/total selector is deliberately not offered.

#### What the result means
A quick, topology-only estimate of how charge is shared along bonds, reflecting the inductive effect. The paper reports correlations with core-electron binding energies and with acidity constants [source:gasteiger1980], which is what it is for, not for absolute numbers. The same drawing gives the same charges whatever conformer exists. Measured here against experimental dipoles, charges of this kind give a mean absolute error of 0.79 D over 15 molecules (the dipole calculator's benchmark). It treats conjugated pi systems by extension, not as given [source:gasteiger1980].

#### Sources
- [source:gasteiger1980] -- the method, its parameters, the damping, the convergence and what it correlates with
- [source:gasteiger1985] -- the experimental dipole moments the application's benchmark used

### Method: mmff94

#### How it works
The partial charges of the MMFF94 force field. An atom's charge is its formal charge (shared with its bonded neighbours for some negatively charged atom types) plus the sum of **bond charge increments**, one for each bond, each a fixed amount that one atom type gains from the polarity of the bond to another and the other loses [source:halgren1996_mmff2]. They are looked up by the atom types of the bonded pair, so the method needs MMFF94 to assign a type to every atom. They were derived for use inside the force field as part of its nonbonded interaction parameters, fitted to reproduce interaction energies and dipole moments from Hartree-Fock calculations, and Halgren describes the resulting potentials as effective pair potentials that include in an averaged way the increase in polarity that occurs in a high-dielectric medium [source:halgren1996_mmff2]. The application reaches them through RDKit's port of MMFF94 [source:tosco2014].

Shipped: it checks that the charges add up to the formal charge. A structure MMFF94 cannot type is reported as not covered, and so are drawn carbanions, where MMFF94's own output was measured to sum to 0 on a charge of -1.

#### What the result means
Charges built to work inside a force field, not an attempt at the electron population of an isolated molecule. They are often larger in magnitude than the other models here: measured on one conformer, the sulfur of dimethyl sulfone is +1.09 and the carboxylate carbon of acetate +0.91, against +0.14 and +0.04 from Gasteiger. That is consistent with their purpose, and a reason not to compare them with other models' values.

#### Sources
- [source:halgren1996_mmff2] -- the charge formula, the bond charge increments, and what they were fitted to
- [source:tosco2014] -- RDKit's implementation of MMFF94

## dipole_moment

### What it does
Computes the molecule's dipole moment as a vector and a magnitude in debye, from a set of partial charges and this conformer's geometry. The direction is where the molecule is, on balance, more negative than positive, and the magnitude says how strongly. Pick the charge model; Gasteiger (PEOE) is the default, with the 3D EEM or QEq charges of the same conformer as alternatives.

### How it works
The dipole is the charge-weighted sum of the atoms' positions, taken about the molecule's centre of mass and converted from elementary charge times angstrom to debye. Every atom needs a charge, because a missing one would be a net charge the molecule does not have. A charge model that declines the molecule is reported as having declined; the calculator never substitutes another model's charges.

### What the result means
A vector sum of point charges, so it inherits everything the charge model gets wrong. Direction and symmetry are the reliable parts (a symmetric molecule comes out near zero, which is the test that actually validates the arithmetic); the magnitude is only as good as the charges. Measured against experiment on 15 molecules of Gasteiger and Saller's Table I [source:gasteiger1985], on OpenChem conformers: Gasteiger mean absolute error 0.79 D over 15, EEM 1.79 D over the 14 it covers and QEq 1.69 D over 15, with EEM and QEq overestimating polar molecules. For a molecule with a net charge the dipole depends on where the origin is placed; it is computed about the centre of mass and the result says so.

### When to use it, when not
Use it to see which way a molecule is polarised and to compare conformers of one molecule with each other, and use Gasteiger for the lowest error found here. Do not treat the magnitude as a prediction of the measured dipole, and do not compare a charged species' dipole with a neutral one's. It needs a 3D conformer, because a dipole is a property of an arrangement and flat coordinates would give a confident but meaningless number.

### Search for
dipole moment, debye, point charge dipole

### Sources
- [source:gasteiger1980] -- the default (PEOE) charges
- [source:bultinck2002a] -- the EEM charges offered as an alternative
- [source:rappe1991] -- the QEq charges offered as an alternative
- [source:gasteiger1985] -- the experimental dipole moments the benchmark compares against

## orbital_electronegativity

### What it does
Reports how strongly each atom attracts electrons in this molecule, in electronvolts. It is the Gasteiger-Marsili orbital electronegativity: an atom's own electronegativity, adjusted for the charge it currently carries. A more electronegative atom is one that will pull charge toward itself in a bond; this shows which atoms those are.

### How it works
Each atom's orbital electronegativity is a + b q + c q squared evaluated at its charge q [source:gasteiger1980]. Two components can be chosen. **Sigma** uses the converged PEOE charge, read from RDKit's own implementation of the iteration. **Pi** uses Marsili and Gasteiger's sigma-dependent pi-orbital electronegativity (SD-POE): the pi-orbital electronegativity of an atom depends on the sigma charge on it, because the sigma charge changes how strongly the nucleus is screened [source:marsili1980]. The pi values here are the paper's starting values at the converged sigma charge and are not iterated to pi self-consistency; they cover conjugated atoms only.

### What the result means
Absolute values depend on the parameter set and will not match another implementation digit for digit. What is meaningful is the ordering between atoms: oxygen above nitrogen above carbon, and aromatic carbon above aliphatic, which the tests pin. The pi ordering is not the sigma ordering: a sigma-negative atom is screened and comes out lower, which is the effect these parameters exist to carry. Because the pi values are not iterated, they do not reflect pi charge redistribution.

### When to use it, when not
Use it to rank atoms by electron-attracting power, for instance to see which end of a bond will carry the negative charge, or to follow how substitution shifts it. Do not read the absolute number as an electronegativity on the Pauling scale, and do not read the pi column as a charge distribution.

### Search for
orbital electronegativity, Gasteiger-Marsili, PEOE electronegativity

### Sources
- [source:gasteiger1980] -- the quadratic form and its sigma parameters
- [source:marsili1980] -- the pi-orbital electronegativity and its dependence on sigma charge
