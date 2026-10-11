# Explainers: surface area and steric bulk

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by `tools/build_calculator_reference.py`; the format
is documented in `tools/calculator_explainers.py`. Every claim is **published** (a registered source says it),
**shipped** (read from the code) or **measured here** (a run on 2026-10-11, one RDKit-embedded, MMFF94-relaxed
conformer per molecule, seed 7, unless it says otherwise).

**The radii, and what changed.** The three calculators here and Geometry use **Bondi's own list**
[source:bondi1964], extended for sixteen main-group elements he gave none for by the radii of Mantina and co-workers
[source:mantina2009]: hydrogen 1.20, carbon 1.70, nitrogen 1.55, oxygen 1.52, fluorine 1.47, phosphorus and sulfur 1.80, chlorine
1.75, bromine 1.85, iodine 1.98; RDKit's table is used only for an element neither covers (the transition metals).
**Until 2026-10-11 the surface, volume and projection calculators used RDKit's table and this application called it Bondi's;
it is not.** RDKit says only that its radii were taken from the Blue Obelisk Data Repository, which cites nothing; the values
equal Batsanov's recommended crystallographic radii for all 65 elements his table lists [source:batsanov2001]. They match
Bondi's for hydrogen, carbon and sulfur but give nitrogen 1.60, oxygen 1.55, fluorine 1.50, phosphorus 1.95 and chlorine
1.80 where Bondi recommends 1.55, 1.52, 1.47, 1.80 and 1.75. The steric calculator moved first (method steric-v2) because
percent buried volume is defined with Bondi's radii; the surface calculators moved after (surface-v3, geometry-v3), and a
result saved by an earlier method is kept beside the new one and labelled, never replayed as it. The full investigation is
`docs/VDW_RADII_ASSESSMENT.md`. The measured size of the move, over 17 drug-like molecules: accessible area -0.4% on average
(worst -1.9%), van der Waals volume -1.4% (worst -4.5%). Against Bondi's own published volumes for 46 molecules, his list
errs 1.84% on average and RDKit's 2.12%, all of the difference in halides (1.95% against 3.14%) [source:zhao2003]; hydrogen
1.10, which the CRC Handbook takes from Rowland and Taylor, would err 7.7% and is not used. Alvarez's neutron-diffraction
analysis independently finds 1.20 for hydrogen [source:alvarez2013]. The literature offers conventions, not one true radius:
Gavezzotti's set (hydrogen 1.17, oxygen 1.40) gives volumes within 10% of Bondi's [source:gavezzotti1983].

## atom_sasa

### What it does
Gives each atom's **solvent-accessible surface area**: how much of its surface a solvent molecule of a chosen size could actually touch, in square angstroms. It shows which atoms are exposed and which are buried, and colours the structure by it. The probe is a water molecule's size (radius 1.4 angstrom) unless you change it.

### How it works
Each atom is a sphere of its van der Waals radius, and the accessible surface is traced by the **centre** of a probe sphere rolling over them, so each atom's accessible sphere has the radius of the atom plus the probe. The surface of that enlarged sphere is covered with test points, and the share of points that lie inside no other atom's enlarged sphere, times the sphere's area, is the atom's accessible area. This is the point-counting method of Shrake and Rupley, who used 92 nearly equally spaced test points per sphere and a solvent radius of 1.4 angstrom for proteins; it follows the idea of Lee and Richards, who described the molecule as solvated van der Waals spheres [source:shrake1973].

Shipped: the same idea with a different point set, **2000 points per atom on a Fibonacci spiral**, which is the same every call so that a repeat run agrees exactly. Measured against a 200,000-point reference at a 1.4 angstrom probe, it is within about 0.3% (worst error over four molecules: 0.9% at 300 points, 0.4% at 960, 0.3% at 2000, 0.13% at 5000), and a lone atom is exact at any count. The radii are Bondi's (above), and not the radii of the 1973 paper, which used Pauling's [source:shrake1973]. The choice of table moves an area by under 1% on average over a drug-like set, whereas the hydrogen radius alone, 1.20 here and 1.10 in the CRC Handbook, would move it 3 to 7%. It needs a 3D conformer, and the probe can be set from 0 to 5 angstrom (at 0 it is the van der Waals surface itself).

### What the result means
One area per atom for **this conformer**, in square angstroms; the areas of all atoms add up to the molecule's accessible surface. An atom's exposure depends on every other atom, so it changes with the conformer, with the probe size and with whether hydrogens are present. Measured on ethanol at the 1.4 angstrom probe: oxygen 35.49, the methyl carbon 7.73 and the CH2 carbon 3.50, because the hydrogens bonded to a carbon shield it, and each hydrogen 22.85 to 27.61, summing to 197.71 for the molecule. A large value means an atom is reachable, not that it is polar or reactive.

### When to use it, when not
Use it to see which atoms of a conformer are exposed, to compare how buried an atom is between conformers, or to see how the picture changes with probe size. Do not compare areas computed with different probes or radii, and do not read exposure as hydrophobicity or as a binding contribution. For the whole-molecule total and its polar and hydrophobic splits use Molecular Surface Area (3D).

### Search for
solvent accessible surface area, SASA, Shrake-Rupley, probe radius

### Sources
- [source:shrake1973] -- the point-counting method, the solvated-sphere picture and the 1.4 angstrom solvent radius
- [source:bondi1964] -- Bondi's radii, which the surface is computed with
- [source:mantina2009] -- the radii for the main-group elements Bondi gave none for
- [source:batsanov2001] -- the table RDKit's radii turned out to equal, which the application used before method surface-v3
- [source:zhao2003] -- Bondi's published volumes for 46 molecules, against which the radii tables were checked
- [source:alvarez2013] -- hydrogen 1.20 from neutron-diffraction contacts
- [source:gavezzotti1983] -- another radii convention, within 10% of Bondi's volumes

## surface_analysis

### What it does
Gives the **whole-molecule surface areas** of a 3D conformer, in square angstroms, with the splits chemists ask for: the solvent-accessible surface area (ASA), the part of it on positively and on negatively charged atoms (ASA+ and ASA-), the part on hydrophobic and on polar atoms (ASA_H and ASA_P), and the van der Waals surface area and volume. It can be taken for the molecule as it is or for the form that predominates at a pH.

### How it works
The accessible surface is computed per atom exactly as in Accessible Surface Area (per atom), so the whole-molecule figures are sums of the same numbers; that is why the four splits cost nothing extra. The splits are rules over those per-atom values. **ASA+ and ASA-** add the atoms whose Gasteiger partial charge is above or below zero, with the charges taken from the same PEOE method as in Partial Charge (pH-dependent) and computed on a copy of the conformer [source:gasteiger1980]. **ASA_P** adds nitrogen, oxygen and fluorine atoms and the hydrogens bonded to them, the atoms that take part in hydrogen bonds, and **ASA_H is everything else**, so a sulfur or a chlorine counts as hydrophobic. The **van der Waals surface** is the surface of the fused atom spheres with no probe, and the **van der Waals volume** is the volume inside them, computed from the same surface points as the areas (a third of the sum, over the exposed points, of the position times the outward normal) and checked against an independent count of grid points; measured on six molecules the volume is within 0.25% of a 0.03 angstrom grid, a lone sphere is exact, and a molecule the two methods disagree about by more than 3% is reported. At a probe of 0 the accessible area equals the van der Waals surface. The radii are Bondi's (above).

Shipped: the probe radius and the pH option. With the pH option, the structure is the stored conformer with **only protons moved**: every heavy atom keeps its coordinates and only a hydrogen the new state adds is placed, and a structure for which that cannot be done is refused with the reason, never a surface of a different molecule.

### What the result means
Measured on one conformer at the 1.4 angstrom probe. Ethanol: ASA 197.71, of which ASA+ 154.50 and ASA- 43.22; ASA_H 139.38 and ASA_P 58.34; van der Waals surface 81.45 and volume 54.14. Benzene: ASA 244.28, ASA_P 0.00 (no polar atoms), van der Waals surface 109.53 and volume 83.69. The two pairs each add to the total. Because ASA+ and ASA- follow the sign of a partial charge, they inherit that model's limits: a different charge model could move an atom across zero and change them. They are areas for one conformer, not averages.

### When to use it, when not
Use it to compare conformers or molecules by exposed surface, to see how much of it is polar, or to size a molecule with a probe. Do not treat ASA_H as a measure of lipophilicity, do not compare areas taken with different probes or radii, and do not compare the charge-sign split between molecules whose charges come from different models. It needs a 3D conformer; the 2D Polar Surface Area calculator needs none.

### Search for
molecular surface area, ASA, van der Waals surface, polar surface

### Sources
- [source:shrake1973] -- the point-counting method the accessible area is computed by
- [source:bondi1964] -- Bondi's radii and van der Waals volume, which the surface and volume are computed with
- [source:mantina2009] -- the radii for the main-group elements Bondi gave none for
- [source:gasteiger1980] -- the PEOE charges whose sign splits ASA+ from ASA-
- [source:batsanov2001] -- the table RDKit's radii turned out to equal, which the application used before method surface-v3

## steric_analysis

### What it does
Measures how much room a ligand takes up around a metal, by two established measures: the **exact cone angle** and the **percent buried volume**. It needs a donor atom (the atom that bonds to the metal), which it finds itself: a carbene carbon (a neutral, two-connected carbon with no hydrogen) first, otherwise the first phosphorus, nitrogen, arsenic or sulfur atom, in that order of preference. A ligand with several possible donors is therefore measured through only one of them. The ligand is a free molecule, with no metal drawn: the metal is placed where it would sit.

### How it works
**Exact cone angle.** Tolman defined the cone angle as the apex angle of a cone centred 2.28 angstrom from the phosphorus atom that just touches the van der Waals radii of the outermost atoms of a space-filling model, with the substituents folded back to give the smallest cone [source:tolman1977]. That needs a physical model, a fixed bond length and a judgement about how substituents fold. Bilbrey and co-workers made it a well-posed geometry problem: the exact cone angle is the apex angle of the **most acute right circular cone, with its apex at the metal, that contains the entire ligand** [source:bilbrey2013]. Shipped: that, solved numerically, with the cone's axis solved for and not assumed to lie along the metal-donor bond; the donor's distance from the metal is an option, default 2.28 angstrom [source:tolman1977]. Measured: PEt3's tightest cone is 146 degrees, against 171 along the bond.

**Percent buried volume.** The share of the volume of a sphere around the metal that the ligand occupies. Poater, Cavallo and co-workers defined it for N-heterocyclic carbene ligands [source:poater2009], and Clavier and Nolan applied it to phosphines as well as carbenes [source:clavier2010]. Shipped with the conventions both papers give for SambVca: a sphere of radius 3.5 angstrom, atomic radii scaled by 1.17, and hydrogen atoms omitted [source:poater2009] [source:clavier2010]; the volume is counted on a grid. The radii are **Bondi's own list scaled by 1.17**, as the papers scale it [source:bondi1964], with hydrogen at his 1.20 (hydrogens are omitted from the volume anyway) and, for main-group elements he gave no value for, the radii Mantina and co-workers derived to be compatible with his scale [source:mantina2009]; an element in neither list falls back to RDKit's table. This matters here as it does not for the surface areas: RDKit's phosphorus radius is 1.95 against Bondi's 1.80, so with RDKit's table the ligand's own phosphorus sphere was larger than SambVca's and small phosphines read 2 to 3.6 points too high. Measured on the same conformers, PH3 is 17.7 percent with Bondi's list (21.3 with RDKit's) and PMe3 22.4 (24.4); against Clavier and Nolan's published values for PMe3, PEt3, PPh3 and PCy3 at 2.28 angstrom (22.2, 27.8, 29.6, 31.8) [source:clavier2010] the mean absolute error is 0.8 points, against 1.8 before. The exact cone angle is unchanged, because hydrogen and carbon, which agree between the tables, set it. Hydrogen is deliberately not the 1.10 that the CRC Handbook and the docking module's contact table use: Rowland and Taylor recommend that value as a compromise for contact distances in crystals, while finding that hydrogen-hydrogen contacts support about 1.19 [source:rowland1996]. The reasoning is in `docs/VDW_RADII_ASSESSMENT.md`.

**The geometry.** The ligand is taken from a set of conformers embedded and minimised with MMFF94 (default 20), and the result is reported across them.

### What the result means
A cone angle in degrees (it can exceed 180 for a very bulky ligand) and a buried volume in percent, for the **free ligand**. Published exact cone angles and buried volumes are computed on the ligand **bound** to a metal, in DFT or crystal geometries, where the substituents splay differently, so these values are not directly comparable with those tables: PPh3's exact cone angle is 163.8 degrees here, and Bilbrey's value is about 170, 25 degrees above Tolman's 145 [source:bilbrey2013]. What survives is the **ranking**. Measured here (10 conformers), for the six phosphines of Tolman's appendix [source:tolman1977], the exact cone angle in degrees against Tolman's published value: PH3 86.4 (87), PMe3 117.2 (118), PEt3 146.3 (132), PPh3 163.8 (145), PCy3 169.6 (170), P(t-Bu)3 193.7 (182). The order is identical and the correlation with Tolman's values is r = 0.977; the buried volumes for the same series, 17.7, 22.4, 26.8, 29.3, 33.6 and 38.7 percent, rise in the same order, in line with the strong cone-angle and buried-volume relationship Clavier and Nolan report for phosphines (R2 = 0.96, for the set they studied) [source:clavier2010].

### When to use it, when not
Use it to rank ligands by bulk, to see how a substituent change moves a ligand along that scale, or to estimate bulk for a ligand nobody has tabulated. Do not compare a number with a published table computed on bound geometries as if it were the same quantity, and do not read it as the bulk in a particular complex, where the ligand folds and the metal's own environment matters. It declines a structure with no donor atom it recognises.

### Search for
cone angle, percent buried volume, ligand steric bulk, Tolman

### Sources
- [source:tolman1977] -- the cone angle's definition, the 2.28 angstrom distance and the published series
- [source:bilbrey2013] -- the exact cone angle and its comparison with Tolman's
- [source:poater2009] -- the buried volume and its SambVca conventions
- [source:clavier2010] -- the buried volume for phosphines and the cone-angle relationship
- [source:bondi1964] -- Bondi's recommended radii, which the buried-volume papers scale and this calculator uses
- [source:mantina2009] -- the radii for the main-group elements Bondi gave none for, compatible with his scale
- [source:rowland1996] -- the hydrogen 1.1 compromise for contact distances, and why it is not used here
