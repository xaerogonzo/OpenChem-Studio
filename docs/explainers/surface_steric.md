# Explainers: surface area and steric bulk

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by `tools/build_calculator_reference.py`; the format
is documented in `tools/calculator_explainers.py`. Every claim is **published** (a registered source says it),
**shipped** (read from the code) or **measured here** (a run on 2026-10-11, one RDKit-embedded, MMFF94-relaxed
conformer per molecule, seed 7, unless it says otherwise).

**A finding about the radii, recorded where it applies.** Wherever this application says "Bondi radii" it means
RDKit's van der Waals table, and that table is **not** Bondi's recommended list. RDKit says only that its radii were
taken from the Blue Obelisk Data Repository, which cites nothing; the values equal Batsanov's recommended
crystallographic radii for all 65 elements his table lists [source:batsanov2001]. They match Bondi's for hydrogen
(1.20), carbon (1.70) and sulfur (1.80) but give nitrogen 1.60, oxygen 1.55, fluorine 1.50 and phosphorus 1.95 where
Bondi's paper recommends 1.55, 1.52, 1.47 and 1.80 [source:bondi1964]. The full investigation, with what the choice
changes, is `docs/VDW_RADII_ASSESSMENT.md`. The explainers below say "RDKit's table" and leave the application's own
labels untouched.

## atom_sasa

### What it does
Gives each atom's **solvent-accessible surface area**: how much of its surface a solvent molecule of a chosen size could actually touch, in square angstroms. It shows which atoms are exposed and which are buried, and colours the structure by it. The probe is a water molecule's size (radius 1.4 angstrom) unless you change it.

### How it works
Each atom is a sphere of its van der Waals radius, and the accessible surface is traced by the **centre** of a probe sphere rolling over them, so each atom's accessible sphere has the radius of the atom plus the probe. The surface of that enlarged sphere is covered with test points, and the share of points that lie inside no other atom's enlarged sphere, times the sphere's area, is the atom's accessible area. This is the point-counting method of Shrake and Rupley, who used 92 nearly equally spaced test points per sphere and a solvent radius of 1.4 angstrom for proteins; it follows the idea of Lee and Richards, who described the molecule as solvated van der Waals spheres [source:shrake1973].

Shipped: the same idea with a different point set, **2000 points per atom on a Fibonacci spiral**, which is the same every call so that a repeat run agrees exactly. Measured against a 200,000-point reference at a 1.4 angstrom probe, it is within about 0.3% (worst error over four molecules: 0.9% at 300 points, 0.4% at 960, 0.3% at 2000, 0.13% at 5000), and a lone atom is exact at any count. The radii are RDKit's table, which is Batsanov's recommended crystallographic set and not Bondi's list (nitrogen 1.60 against 1.55, oxygen 1.55 against 1.52, fluorine 1.50 against 1.47, phosphorus 1.95 against 1.80; the effect on an area averages under 1% on a drug-like set, whereas the hydrogen radius alone, 1.20 here and 1.10 in the CRC Handbook, moves it 3 to 7%) [source:bondi1964] [source:batsanov2001], and not the radii of the 1973 paper, which used Pauling's [source:shrake1973]. It needs a 3D conformer, and the probe can be set from 0 to 5 angstrom (at 0 it is the van der Waals surface itself).

### What the result means
One area per atom for **this conformer**, in square angstroms; the areas of all atoms add up to the molecule's accessible surface. An atom's exposure depends on every other atom, so it changes with the conformer, with the probe size and with whether hydrogens are present. Measured on ethanol at the 1.4 angstrom probe: oxygen 35.49, the methyl carbon 7.73 and the CH2 carbon 3.50, because the hydrogens bonded to a carbon shield it, and each hydrogen 22.85 to 27.61, summing to 197.71 for the molecule. A large value means an atom is reachable, not that it is polar or reactive.

### When to use it, when not
Use it to see which atoms of a conformer are exposed, to compare how buried an atom is between conformers, or to see how the picture changes with probe size. Do not compare areas computed with different probes or radii, and do not read exposure as hydrophobicity or as a binding contribution. For the whole-molecule total and its polar and hydrophobic splits use Molecular Surface Area (3D).

### Search for
solvent accessible surface area, SASA, Shrake-Rupley, probe radius

### Sources
- [source:shrake1973] -- the point-counting method, the solvated-sphere picture and the 1.4 angstrom solvent radius
- [source:bondi1964] -- Bondi's radii, against which RDKit's table was compared
- [source:batsanov2001] -- the table RDKit's radii turned out to equal

## surface_analysis

### What it does
Gives the **whole-molecule surface areas** of a 3D conformer, in square angstroms, with the splits chemists ask for: the solvent-accessible surface area (ASA), the part of it on positively and on negatively charged atoms (ASA+ and ASA-), the part on hydrophobic and on polar atoms (ASA_H and ASA_P), and the van der Waals surface area and volume. It can be taken for the molecule as it is or for the form that predominates at a pH.

### How it works
The accessible surface is computed per atom exactly as in Accessible Surface Area (per atom), so the whole-molecule figures are sums of the same numbers; that is why the four splits cost nothing extra. The splits are rules over those per-atom values. **ASA+ and ASA-** add the atoms whose Gasteiger partial charge is above or below zero, with the charges taken from the same PEOE method as in Partial Charge (pH-dependent) and computed on a copy of the conformer [source:gasteiger1980]. **ASA_P** adds nitrogen, oxygen and fluorine atoms and the hydrogens bonded to them, the atoms that take part in hydrogen bonds, and **ASA_H is everything else**, so a sulfur or a chlorine counts as hydrophobic. The **van der Waals surface** is the surface of the fused atom spheres with no probe, and the **van der Waals volume** is the volume inside them, computed analytically and checked against a grid routine; at a probe of 0 the accessible area equals the van der Waals surface. The radii are RDKit's table, which is Batsanov's recommended crystallographic set and not Bondi's list (nitrogen 1.60 against 1.55, oxygen 1.55 against 1.52, fluorine 1.50 against 1.47, phosphorus 1.95 against 1.80; the effect on an area averages under 1% on a drug-like set, whereas the hydrogen radius alone, 1.20 here and 1.10 in the CRC Handbook, moves it 3 to 7%) [source:bondi1964] [source:batsanov2001].

Shipped: the probe radius and the pH option. With the pH option, the structure is the stored conformer with **only protons moved**: every heavy atom keeps its coordinates and only a hydrogen the new state adds is placed, and a structure for which that cannot be done is refused with the reason, never a surface of a different molecule.

### What the result means
Measured on one conformer at the 1.4 angstrom probe. Ethanol: ASA 197.71, of which ASA+ 154.50 and ASA- 43.22; ASA_H 139.38 and ASA_P 58.34; van der Waals surface 81.45 and volume 54.14. Benzene: ASA 244.28, ASA_P 0.00 (no polar atoms), van der Waals surface 109.53 and volume 83.69. The two pairs each add to the total. Because ASA+ and ASA- follow the sign of a partial charge, they inherit that model's limits: a different charge model could move an atom across zero and change them. They are areas for one conformer, not averages.

### When to use it, when not
Use it to compare conformers or molecules by exposed surface, to see how much of it is polar, or to size a molecule with a probe. Do not treat ASA_H as a measure of lipophilicity, do not compare areas taken with different probes or radii, and do not compare the charge-sign split between molecules whose charges come from different models. It needs a 3D conformer; the 2D Polar Surface Area calculator needs none.

### Search for
molecular surface area, ASA, van der Waals surface, polar surface

### Sources
- [source:shrake1973] -- the point-counting method the accessible area is computed by
- [source:bondi1964] -- Bondi's radii and van der Waals volume, against which RDKit's table was compared
- [source:gasteiger1980] -- the PEOE charges whose sign splits ASA+ from ASA-
- [source:batsanov2001] -- the table RDKit's radii turned out to equal

## steric_analysis

### What it does
Measures how much room a ligand takes up around a metal, by two established measures: the **exact cone angle** and the **percent buried volume**. It needs a donor atom (the atom that bonds to the metal), which it finds itself: a carbene carbon (a neutral, two-connected carbon with no hydrogen) first, otherwise the first phosphorus, nitrogen, arsenic or sulfur atom, in that order of preference. A ligand with several possible donors is therefore measured through only one of them. The ligand is a free molecule, with no metal drawn: the metal is placed where it would sit.

### How it works
**Exact cone angle.** Tolman defined the cone angle as the apex angle of a cone centred 2.28 angstrom from the phosphorus atom that just touches the van der Waals radii of the outermost atoms of a space-filling model, with the substituents folded back to give the smallest cone [source:tolman1977]. That needs a physical model, a fixed bond length and a judgement about how substituents fold. Bilbrey and co-workers made it a well-posed geometry problem: the exact cone angle is the apex angle of the **most acute right circular cone, with its apex at the metal, that contains the entire ligand** [source:bilbrey2013]. Shipped: that, solved numerically, with the cone's axis solved for and not assumed to lie along the metal-donor bond; the donor's distance from the metal is an option, default 2.28 angstrom [source:tolman1977]. Measured: PEt3's tightest cone is 146 degrees, against 171 along the bond.

**Percent buried volume.** The share of the volume of a sphere around the metal that the ligand occupies. Poater, Cavallo and co-workers defined it for N-heterocyclic carbene ligands [source:poater2009], and Clavier and Nolan applied it to phosphines as well as carbenes [source:clavier2010]. Shipped with the conventions both papers give for SambVca: a sphere of radius 3.5 angstrom, atomic radii scaled by 1.17, and hydrogen atoms omitted [source:poater2009] [source:clavier2010]; the volume is counted on a grid. The radii here are RDKit's table scaled by 1.17, where the papers scale Bondi's own list (RDKit's differs for nitrogen, oxygen, fluorine and phosphorus [source:bondi1964]), and for the buried volume that matters: RDKit's phosphorus radius is 1.95 against Bondi's 1.80, so the ligand's own phosphorus sphere is larger than SambVca's. Measured with Bondi's list substituted, PH3 falls from 21.3 to 17.7 percent and PMe3 from 24.4 to 22.4; against Clavier and Nolan's published values for PMe3, PEt3, PPh3 and PCy3 at 2.28 angstrom (22.2, 27.8, 29.6, 31.8) [source:clavier2010] the mean absolute error is 1.8 points with RDKit's table and 0.8 with Bondi's. The exact cone angle does not change, because hydrogen and carbon, which agree, set it. Which table to use is an open decision (`docs/VDW_RADII_ASSESSMENT.md`).

**The geometry.** The ligand is taken from a set of conformers embedded and minimised with MMFF94 (default 20), and the result is reported across them.

### What the result means
A cone angle in degrees (it can exceed 180 for a very bulky ligand) and a buried volume in percent, for the **free ligand**. Published exact cone angles and buried volumes are computed on the ligand **bound** to a metal, in DFT or crystal geometries, where the substituents splay differently, so these values are not directly comparable with those tables: PPh3's exact cone angle is 163.8 degrees here, and Bilbrey's value is about 170, 25 degrees above Tolman's 145 [source:bilbrey2013]. What survives is the **ranking**. Measured here (10 conformers), for the six phosphines of Tolman's appendix [source:tolman1977], the exact cone angle in degrees against Tolman's published value: PH3 86.4 (87), PMe3 117.2 (118), PEt3 146.3 (132), PPh3 163.8 (145), PCy3 169.6 (170), P(t-Bu)3 193.7 (182). The order is identical and the correlation with Tolman's values is r = 0.977; the buried volumes for the same series, 21.3, 24.4, 28.4, 30.8, 34.9 and 39.7 percent, rise in the same order, in line with the strong cone-angle and buried-volume relationship Clavier and Nolan report for phosphines (R2 = 0.96, for the set they studied) [source:clavier2010].

### When to use it, when not
Use it to rank ligands by bulk, to see how a substituent change moves a ligand along that scale, or to estimate bulk for a ligand nobody has tabulated. Do not compare a number with a published table computed on bound geometries as if it were the same quantity, and do not read it as the bulk in a particular complex, where the ligand folds and the metal's own environment matters. It declines a structure with no donor atom it recognises.

### Search for
cone angle, percent buried volume, ligand steric bulk, Tolman

### Sources
- [source:tolman1977] -- the cone angle's definition, the 2.28 angstrom distance and the published series
- [source:bilbrey2013] -- the exact cone angle and its comparison with Tolman's
- [source:poater2009] -- the buried volume and its SambVca conventions
- [source:clavier2010] -- the buried volume for phosphines and the cone-angle relationship
- [source:bondi1964] -- Bondi's recommended radii, which the buried-volume papers scale and RDKit's table departs from
- [source:batsanov2001] -- the table RDKit's radii turned out to equal
