# Explainers: interactions within a molecule, and molecular dynamics

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by `tools/build_calculator_reference.py`; the format
is documented in `tools/calculator_explainers.py`. Every claim is **published** (a registered source says it),
**shipped** (read from the code) or **measured here** (a run on 2026-10-11 on RDKit-embedded, MMFF94-relaxed
conformers, seed 7 unless it says otherwise).

3D Alignment is the third calculator of this group and has no explainer yet.

## interaction_analysis

### What it does
Looks through one 3D conformer for pairs of atoms or rings that are close enough to be **non-covalent contacts** inside the molecule itself, and lists each with the atoms involved and the distance in angstroms. It looks for seven kinds: hydrogen bonds, salt bridges, π-π stacking, cation-π contacts, hydrophobic contacts, metal coordination and steric clashes. It needs a 3D conformer; with none, it says so.

### How it works
Every pair of heavy atoms is tested against a distance rule, with a minimum number of bonds between them so that atoms joined by one or two bonds are not reported as "contacts" of each other. Shipped, with the cutoffs in angstroms:

- **Hydrogen bond:** both atoms are nitrogen, oxygen or fluorine, at most 3.5 apart and at least 3 bonds apart. The rule uses the two heavy atoms only: no hydrogen position, no angle, and no distinction between donor and acceptor.
- **Salt bridge:** one atom with a formal positive charge and one with a formal negative charge, at most 4.0 apart and at least 4 bonds apart.
- **π-π stacking:** two aromatic rings that share no atom, with their centres (centroids) at most 5.5 apart.
- **Cation-π:** an atom with a formal positive charge that is not in the ring, at most 6.0 from an aromatic ring's centroid.
- **Hydrophobic contact:** two carbons, neither aromatic and neither bonded to a nitrogen, oxygen or fluorine, at most 4.5 apart and at least 4 bonds apart. There is no lower limit.
- **Metal coordination:** a metal (zinc, magnesium, calcium, iron, manganese, copper, sodium, potassium, cobalt or nickel) and a nitrogen, oxygen or fluorine, at most 2.8 apart and at least 3 bonds apart.
- **Steric clash:** two heavy atoms at least 4 bonds apart that are closer than the sum of their van der Waals radii less 0.4. A pair already reported as a hydrogen bond is never also reported as a clash, since that closeness is the hydrogen bond.

This is the kind of rule-based, purely geometric detection that protein-ligand interaction tools use, whose published description says its thresholds are taken from the literature and in places made deliberately permissive to tolerate imperfect structures [source:plip2015]. The cutoffs here are conventional values: none is fitted or validated in this application, and no source is recorded for any individual number.

### What the result means
A list of **candidate contacts in this one conformer**, one line each, such as `Hydrogen bond: atoms 0-9 (2.56 Å)`; the atom numbers are the structure's own, counted from 0. It is a geometric screen, not an energy, a score or a statement about strength: a short distance means two atoms are near each other, not that they attract. An empty answer means nothing met a rule in this conformer, not that no contact is possible: 1,2-diphenylethane and 4-phenylbutyl-trimethylammonium report nothing in their relaxed, extended shape, while phenethyl-trimethylammonium reports a cation-π contact of 4.36 angstroms.

Measured, to show the kinds working: salicylic acid's textbook six-membered intramolecular hydrogen bond (O...O 2.56), ethylene glycol's (2.79) and glycine's N...O contact (2.65 as the neutral form, 2.47 as the zwitterion).

**Known limits, each measured on 2026-10-11, and the reason to read the list with care:**
- **Two acceptors count as a hydrogen bond.** 1,2-dimethoxyethane has two ether oxygens and no hydrogen on either; it reports a hydrogen bond between them at 3.01 angstroms.
- **A nitro group's nitrogen counts as a cation.** Its formal charge is a way of drawing a neutral group, but the rule sees a positive atom: nitrobenzene reports a cation-π contact of 2.86 angstroms between the nitro nitrogen and its own ring, as does every nitro-substituted ring tried, and 2-nitrobenzoate also reports a salt bridge of 2.74 between the nitro nitrogen and the carboxylate oxygen. Any group drawn with charges on a neutral whole is read the same way.
- **Two directly bonded aromatic rings count as stacked.** Biphenyl reports π-π stacking at 4.31 angstroms between its two rings; stacking needs one ring folded over the other, and here they are simply joined.
- **Metal coordination looks at nitrogen, oxygen and fluorine only.** A thiolate sulfur on zinc is not counted, whereas its amine nitrogen is.
- **A salt written as separate fragments has no meaningful geometry.** Sodium acetate is embedded with its two pieces on top of each other (a sodium-carbon distance of 0.64), so the calculator reports a salt bridge, two metal coordinations and four clashes that describe the embedding and not the compound.
- **A "hydrophobic contact" can be crowding.** With no lower limit, the 3.00 angstrom contact between the methyl groups of 1,8-dimethylnaphthalene and the nine contacts between the tert-butyl groups of cis-1,3-di-tert-butylcyclohexane (3.56 to 4.49) are reported, though these groups are pushed together and not attracted.

### When to use it, when not
Use it to see which atoms of a conformer are close enough to interact, to compare how conformers differ in their internal contacts, or to find where a hydrogen bond could close a ring. Do not read the count as strength or stability, do not treat it as a donor-and-acceptor analysis, and check any line that involves a nitro group, a drawn zwitterion or a metal against the structure before relying on it. For contacts between a ligand and a receptor, which this does not do, use the docking pose analysis.

### Search for
intramolecular hydrogen bond, salt bridge, pi stacking, non-covalent interactions

### Sources
- [source:plip2015] -- the rule-based, literature-threshold character of geometric interaction detection

## molecular_dynamics

### What it does
Lets the atoms of one conformer **move under the forces of a force field** for a short time, and records the motion as a trajectory you can play back, with the total energy at every recorded frame. It is a vacuum simulation of one isolated molecule, run at constant total energy. It needs a 3D conformer.

### How it works
At each step the force on every atom is the negative gradient of the molecule's MMFF94 energy, the Merck Molecular Force Field [source:halgren1996_mmff1], as implemented in RDKit [source:tosco2014]; where MMFF94 has no parameters for the molecule it uses the UFF force field instead, and where neither does it declines with that reason, never integrating zero forces. The positions and velocities are advanced by the **velocity Verlet** scheme: a half-step of the velocities, a full step of the positions, new forces, and a second half-step of the velocities.

Shipped: the starting velocities are drawn at random from the Maxwell-Boltzmann distribution for the temperature you give, and the total linear momentum is removed so the molecule does not drift across the view; its rotation is not removed. The conformer is used as it stands, without minimising it first. There is **no thermostat, no barostat, no constraints, no periodic boundaries and no solvent**, so the temperature is where the velocities start and is not held. A random seed of 0 means an unseeded run; any other value repeats exactly (measured: two runs with seed 5 gave identical final coordinates, a run with seed 6 did not). The limits are 10 to 100000 steps of 0.1 to 2.0 femtoseconds, 1 to 2000 K, and a frame every 1 to 1000 steps (defaults 1000 steps of 0.5 fs at 300 K, a frame every 10). If the numbers blow up, the run stops at the first non-finite value and **fails with a message, keeping no trajectory**; at 5 fs, outside the allowed range, ibuprofen failed at 35 fs. MMFF94 and UFF energies are not Dreiding's, so they are not comparable with another program's Dreiding energies.

### What the result means
A trajectory of the structure at each frame, the time of each frame in femtoseconds, and the total (potential plus kinetic) energy of each in kcal/mol. It describes how this molecule would vibrate and flex **alone, in vacuum, near the conformer it started from**, within the accuracy of the force field. It is not an ensemble, a free energy or a prediction in solution.

Measured, on MMFF94-minimised starts, 1000 steps of 0.5 fs (0.5 ps): the **total energy is conserved**, drifting by +0.013 kcal/mol for ethanol, +0.073 for ibuprofen and +0.034 for caffeine, with a range of at most 0.10; the same ibuprofen run drifts 0.23 kcal/mol at 1 fs and 1.20 at 2 fs, so the default step is the careful one. **The temperature you ask for is not the temperature you get.** The velocities drawn for 300 K gave an initial kinetic temperature of 255, 275 and 263 K for those three molecules (a small molecule's draw is noisy), and over the second half of a run started from a minimised conformer the average fell to 155, 139 and 135 K, about half. That is what an isolated system started at a minimum does when its energy is shared between motion and strain, and a conformer that was not relaxed first (raw embedding) kept 240 to 300 K, because it began with strain to release.

It also does **not search conformations**. Over the default 0.5 ps, the heavy atoms of ibuprofen stayed within 0.27 angstrom of the start and the isobutyl-aryl torsion between 90 and 120 degrees; over the 50 ps maximum at 300 K, within 1.0 angstrom and 76 to 148 degrees, still the starting conformer; only at 1000 K did that torsion sweep through the full circle (heavy atoms up to 1.8 angstrom away). A run takes a fraction of a second for the default and about 7 seconds for 100000 steps of a 33-atom molecule.

### When to use it, when not
Use it to watch a structure vibrate and flex, to see whether a geometry holds together, or to teach how a force field moves atoms. Do not use it to sample conformations (generate conformers for that), to estimate thermodynamic quantities, to describe behaviour in water or at a surface, or to read an energy off against another program's. Compare energies only within one run, and do not read the starting temperature as the temperature of the simulation.

### Search for
molecular dynamics, velocity Verlet, NVE ensemble, MMFF94 trajectory

### Sources
- [source:halgren1996_mmff1] -- MMFF94, the force field the forces come from
- [source:tosco2014] -- the implementation of MMFF94 in RDKit that this application uses
