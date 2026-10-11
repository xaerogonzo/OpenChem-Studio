# Explainers: shape and surface (first part)

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by `tools/build_calculator_reference.py`; the format
is documented in `tools/calculator_explainers.py`. Every claim is **published** (a registered source says it),
**shipped** (read from the code) or **measured here** (a run on 2026-10-11, one RDKit-embedded, MMFF94-relaxed
conformer per molecule, seed 7).

The surface and steric calculators of this group are in `surface_steric.md`; the radii they and Geometry share, and what
changed in method v3, are described at the top of that file.

## polar_surface_area

### What it does
Estimates how much of a molecule's surface belongs to its polar atoms, the nitrogens and oxygens, in square angstroms, from the 2D drawing alone. It is reported twice: for the structure as drawn, and for the form that predominates at a chosen pH, because an acid that has lost a proton or an amine that has gained one has different polar atoms.

### How it works
This is **topological polar surface area (TPSA)**. Rather than build a 3D structure and measure a surface, it adds up a fixed contribution for each polar fragment, where a fragment is an atom together with its bonding pattern: a neutral hydroxyl contributes 20.23, an ether oxygen 9.23, a primary amine nitrogen 26.02 [source:ertl2000]. The contributions were found by least-squares fitting to the polar surface measured on a single 3D conformer, taken from the van der Waals surface of the oxygens, nitrogens, sulfurs and phosphorus atoms with their attached hydrogens, for 34,810 drug-like molecules from the World Drug Index [source:ertl2000]. The fit has a correlation of 0.99 with the 3D value (standard deviation 7.83 square angstroms, average absolute error 5.62) [source:ertl2000].

Shipped: RDKit's implementation of that table, which counts **nitrogen and oxygen only**. The paper also lists "slightly polar" sulfur and phosphorus fragments for those who want them [source:ertl2000]; they are not counted here (measured: thiophenol gives 0.00, where counting sulfur would give 38.80, and trimethyl phosphate 44.76, where counting phosphorus would give 54.57). At a pH, the dominant form is chosen with Dimorphite-DL and the same sum is taken over it, so the value changes only by the polar atoms' changed contributions (measured: acetic acid 37.30 as drawn and 40.13 as the carboxylate, which is the table's 23.06 for the anion oxygen plus 17.07 for the carbonyl; methylamine 26.02 as drawn and 27.64 as the ammonium).

### What the result means
A fast, topological estimate of the polar surface a 3D calculation would give, not a measured surface. It uses no geometry, so every conformer of a molecule has the same value. The paper reports that it correlates with published intestinal absorption, Caco-2 permeability and blood-brain barrier data, with squared correlations from 0.56 to 0.96 across six data sets of 9 to 57 compounds, similar to the 3D value on the same data [source:ertl2000]. Its one reported weakness is large macrocycles with many polar substituents, whose polar groups sit buried in the ring, so the topological value is too large against the 3D one [source:ertl2000].

### When to use it, when not
Use it to screen or rank many structures quickly, or to see how ionization shifts the polar surface. Do not read it as an accessible or measured surface, do not compare it with a value computed with sulfur and phosphorus counted, and treat it as an overestimate for macrocycles whose polar groups face inward. For a surface of a particular conformer use Molecular Surface Area (3D).

### Search for
topological polar surface area, TPSA, Ertl, polar surface area

### Sources
- [source:ertl2000] -- the method, the fragment contributions, how they were fitted, and the validation data

## griffin_hlb

### What it does
Gives Griffin's hydrophile-lipophile balance (HLB) of a nonionic surfactant: a number from 0 to 20 for how water-loving versus oil-loving the molecule is, used to choose an emulsifier. It answers only for the surfactants the definition covers, and says so with a reason for any other structure, instead of returning a number that would mean nothing.

### How it works
Griffin defined HLB for nonionic surfactants **whose only hydrophilic part is polyoxyethylene** as one fifth of the weight percentage of ethylene oxide in the molecule, HLB = E / 5, and fixed its scale by experiment, determining the HLB a surfactant must have to emulsify each of a variety of oils, fats and waxes in water [source:schott1989]. For a polyoxyethylated dodecanol with p ethylene oxide units this becomes 881 p / (44.05 p + 186.3) [source:schott1989].

Shipped: the calculator counts the ethylene oxide units (-O-CH2-CH2-O- repeats) by substructure, takes each as 44.05 mass units, and divides by the whole molecular weight, so HLB = 20 x units x 44.05 / molecular weight. It reproduces the closed form above (measured: dodecanol with 4, 10 and 23 units gives 9.72, 14.05 and 16.89; the closed form gives 9.72, 14.06 and 16.89). It refuses a structure with no polyoxyethylene chain (measured: dodecanol, aspirin), and one that carries another hydrophilic group: a formal charge, an amine, an amide, a carboxylic acid, a sulfur or phosphorus oxyacid, a hydroxylated ring or more than one hydroxyl (measured: sodium laureth sulfate is refused for "a formal charge"). The refusal list is of what is excluded, not of what is allowed, so a hydrophile nobody thought of is not silently accepted.

### What the result means
A classification aid, validated by Griffin's emulsification experiments rather than by a measurement of the molecule. Schott's Table I gives the working ranges: about 3 to 6 for water-in-oil emulsifiers, 8 to 17 for oil-in-water emulsifiers and 15 to 18 for solubilizers, and the scale approaches 20 asymptotically as the chain lengthens [source:schott1989]. **Davies' HLB is a different scale** that shares the name: it was calculated from Griffin's results for sorbitan esters and polysorbates, none of which has polyoxyethylene as the sole hydrophile, and Schott shows it differs substantially from Griffin's over the whole practical range, for surfactants of that kind [source:schott1989]. Davies' scale is therefore not offered, and the two numbers must never be reported under one label. Sorbitan esters (Span, Tween) are outside the formula: Griffin's experiments produced their published values, but sorbitan is a polyhydric alcohol, so his formula does not apply to them.

### When to use it, when not
Use it for polyoxyethylated alcohols, alkylphenols and fatty acid esters of polyethylene glycol, which the paper says make up over 73% of the weight of nonionic surfactants produced in the United States at the time [source:schott1989]. Do not use it for ionic surfactants, for anything with a second hydrophilic group, or for an ordinary drug, and do not read a refusal as a fault: it is the answer.

### Search for
HLB, hydrophile-lipophile balance, Griffin, emulsifier

### Sources
- [source:schott1989] -- Griffin's definition and the HLB = E / 5 form, the closed form for polyoxyethylated dodecanols, the application ranges, and why Davies' scale is not interchangeable

## torsion_table

### What it does
Lists every rotatable bond of the conformer on screen with the twist about it, in degrees, so that "flexible" can be read bond by bond instead of as a single count. Each row names the four atoms the angle was measured through.

### How it works
The angle about a bond B-C is the dihedral angle between the plane through A, B, C and the plane through B, C, D, where A is a neighbour of B and D a neighbour of C. Where an end has a choice of neighbour the heaviest is taken and, among equals, the lowest-numbered one, so the angle is never measured through a hydrogen when something heavier is there, and a renumbered drawing gives the same row.

Which bonds count is the shipped part. They are exactly the ones in Properties' **Rotatable Bonds** count, which is RDKit's strict definition [source:rdkit]: a single bond not in a ring between two atoms that are not terminal and not part of a triple bond, leaving out the spin of a trihalomethyl or tert-butyl group (which changes nothing) and the amide-like C(=X)-N, -O or -S linkage that is treated as rigid. RDKit gives only the count, so the same definition is written out as a pattern and a test holds the two equal over a corpus of structures, so the table and the count cannot disagree. The pattern is matched on the heavy-atom graph, so it gives the same bonds whether it is handed the drawing or a conformer with explicit hydrogens.

### What the result means
One angle per rotatable bond, in the range minus 180 to 180 degrees, where 180 is anti and 0 is syn. It describes **this conformer only**: it is not a scan, not an energy and not a preference, and another conformer of the same molecule has different angles. A bond that is rotatable by definition may still be hindered in practice.

### When to use it, when not
Use it to see where two conformers differ, to read which bonds make a molecule flexible, or to pick the bonds to scan in another calculation. Do not read an angle as the preferred or the lowest-energy one, and do not read the number of rows as a conformational count. It needs a 3D conformer, because an angle from flat 2D coordinates would be 0 or 180 and mean nothing.

### Search for
torsion angle, dihedral angle, rotatable bonds

### Sources
- [source:rdkit] -- the rotatable-bond definition the table reproduces (cited for provenance; the pattern and its agreement with the count are this application's, tested here)

## geometry_analysis

### What it does
Describes the size and shape of the conformer on screen and gives its energy under three force fields. For shape it reports how far the atoms lie from the centre, the smallest and the largest shadow the molecule casts over all viewing directions with the radius of the circle round each, and how far the molecule extends along that viewing direction. For energy it reports MMFF94, UFF and Dreiding, in kcal/mol or kJ/mol.

### How it works
**Extent.** The distances from the centroid (the unweighted mean of the atom positions) to the nearest, the farthest and the average atom.

**Shadows.** The molecule is drawn as a union of spheres, one per atom, of the atom's van der Waals radius times a scale factor (default 1). Its shadow in a viewing direction is the union of the discs they project, and the area of that union is computed exactly, not on a grid. The smallest and largest shadow are found by searching the viewing directions: about a thousand orientations are sampled over the sphere, the area is exact at each, and the best are refined locally (measured: benzene, 990 orientations, smallest shadow 18.75 square angstroms, where measuring on the three principal planes and calling the smaller "minimal" gives 20.07). The radii are Bondi's own list, the most widely used scale of van der Waals radii [source:crc_handbook] [source:bondi1964], extended for the sixteen main-group elements he gave none for by the radii of Mantina and co-workers [source:mantina2009]; they are shared with the surface and steric calculators. Before method geometry-v3 the radii were RDKit's table, which is a different set (Batsanov's) that this application had called Bondi's; the change moved the smallest shadow by -0.8% on average and the largest by -0.7% over 17 drug-like molecules (worst -2.8% and -2.4%), because the two sets differ for nitrogen, oxygen, fluorine, phosphorus and the halogens, and not for hydrogen, carbon or sulfur. A result saved by the earlier method is kept beside the new one and labelled.

**Energies.** Each force field is evaluated at the geometry as it is. **MMFF94** was derived mainly from high-quality computational data, about 500 structures optimized at HF/6-31G*, 475 at MP2/6-31G* and further sets evaluated at higher levels, as a combined organic and protein force field [source:halgren1996_mmff1]; it is reached through RDKit's port [source:tosco2014]. **UFF**, the Universal force field, estimates its parameters from general rules that use only the element, its hybridization and its connectivity, so it covers the full periodic table [source:rappe1992]. **Dreiding** is also a generic force field: it takes bond lengths from atomic radii and uses one force constant each for bonds, angles and inversions and only six torsional barriers, all from simple hybridization rules [source:mayo1990]. Shipped: Dreiding is implemented here from that paper, with neither charges nor an explicit hydrogen-bond term, which is how the paper reports its own results, and it covers 37 atom types and declines outside them; the application's own check reproduces all eight rotational barriers the paper computes with Dreiding to within 0.008 kcal/mol (`docs/DREIDING_ASSESSMENT.md`). Any of the three can be absent for a molecule it has no parameters for, and nothing is substituted.

**Options.** The energies and shadows can be taken on a relaxed **copy** of the geometry, never the one on screen, and a lowest-energy conformer can be taken from several generated ones ("lowest of those tried", never a global minimum). Changing the energy unit converts the same stored number.

### What the result means
Shape numbers are for this conformer; a flexible molecule has many. The three energies are on **different scales and are never comparable with each other**, and each fact says so. Measured here on one conformer, in kcal/mol: ethanol MMFF94 -1.34, UFF 3.05, Dreiding 3.74; benzene 16.23, 10.65, 21.41; hexane -4.65, 5.91, 10.81. They differ even in sign. What is meaningful is to compare **one** of them across conformers of the **same** molecule.

### When to use it, when not
Use it to compare conformers of one molecule, to size a molecule up (how big a shadow it casts, how far it reaches) or to see which of several conformers is the most compact. Do not compare an energy from one force field with another's, or between different molecules, and do not read the lowest energy among a handful of conformers as the global minimum. It needs a 3D conformer unless it is asked to generate one.

### Search for
force field energy, MMFF94 UFF Dreiding, projection area, molecular shape

### Sources
- [source:halgren1996_mmff1] -- what MMFF94 is, what it was derived from and what it is for
- [source:rappe1992] -- what UFF is and how its parameters are generated
- [source:mayo1990] -- what Dreiding is and how its parameters are generated
- [source:tosco2014] -- RDKit's implementation of MMFF94, through which the energy is computed
- [source:crc_handbook] -- Bondi's van der Waals radii as the most widely used scale
- [source:bondi1964] -- Bondi's recommended radii, which the shadow is drawn with
- [source:mantina2009] -- the radii for the main-group elements Bondi gave none for
