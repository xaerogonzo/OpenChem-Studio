# Geometry and Marvin's Geometrical Descriptors: the definitions checklist

**What this is.** Stage 4 of the calculator-organisation plan proposed merging the
geometry calculators "Marvin-style". The plan's first deliverable is this table, written
BEFORE any code: for each quantity Marvin's plugin documents, what Marvin says it is,
what OpenChem already reports, and whether a number from one could be compared with a
number from the other. Nothing was built to produce it; the OpenChem column was read from
the source on 2026-10-10.

**Marvin's side is one page.** ChemAxon's *Geometrical Descriptors Plugin* manual
(`https://docs.chemaxon.com/lts-iodine/geometrical-descriptors-plugin.html`, read
2026-10-10; the `latest/` and `display/docs/` addresses of the same page return a 404).
It lists ten descriptors and five options and **gives no formulas, no defaults, no
version, and no references**. Everything in the "Marvin says" column is a paraphrase of
one sentence. That limits what this document can claim, and it is why no row below is
marked "numerically comparable".

"Marvin-style" is therefore inspiration for WHICH quantities and options to offer. It is
not a claim that a number here equals Marvin's.

## The ten descriptors

| # | Marvin quantity | Marvin says (unit) | OpenChem today | Comparison with Marvin | Gap |
|---|---|---|---|---|---|
| 1 | Dreiding energy | "energy of the 3D structure (conformation)" using the Dreiding force field (kcal/mol or kJ/mol) | **Reported** in `Geometry`: `chem/dreiding/`, implemented from Mayo, Olafson & Goddard 1990 (`mayo1990` in `docs/sources.toml`); reproduces all eight rotational barriers of the paper's Table XI to 0.008 kcal/mol (`docs/DREIDING_ASSESSMENT.md`). No charges and no hydrogen-bond term, as in the paper's own results. kcal/mol only | **Qualitative only.** Marvin does not say how it treats charges or H bonds, so two Dreiding energies of one conformer may legitimately differ | energy unit option (kJ/mol) |
| 2 | MMFF94 energy | energy of the conformation using MMFF94 | **Reported** in `Geometry`, RDKit's MMFF94 on the CURRENT geometry, kcal/mol; `None` where RDKit has no parameters | **Qualitative only**: same force field name, different implementation and (if Marvin optimises first) different geometry | energy unit; "optimise before" option (row O2) |
| 3 | Steric hindrance | "of an atom", "calculated from the covalent radii values and geometrical distances"; no unit | **Not reported under this name.** `Ligand Steric Bulk` computes the exact cone angle and %Vbur for a ligand donor atom (`chem/steric.py`): different quantities, defined for a metal-bound donor, not for any atom | **Not comparable.** Marvin gives no formula, so a per-atom "steric hindrance" cannot be written to match it, and inventing one under that name would be a number nobody can check | none to close. See "Decisions" |
| 4 | Minimal projection area | minimum projection area of the conformer, "based on the van der Waals radius" (A^2) | **Reported, approximated**: measured on the three principal planes, not minimised over all orientations, so a shape whose true minimum is off-axis reads slightly high (`chem/projection_geometry.py`, stated on the fact) | **Not comparable until the minimum is a minimum.** Today's figure is "smallest of three" | true minimisation over orientations (`projection_geometry` calls it Phase 7b, never built) |
| 5 | Maximal projection area | same, maximum | same approximation, reads slightly LOW for the maximum | as above | as above |
| 6 | Minimal projection radius | "radius for the minimal projection area" (A) | **Reported** as the shadow radius of a principal axis | **Not comparable.** "Radius" is not defined on Marvin's page (circumscribed circle? equivalent-area circle?). Ours is stated on the fact; Marvin's is unknown | none until its meaning is known |
| 7 | Maximal projection radius | same, maximum | same | same | same |
| 8 | Max distance perpendicular to the min projection | "maximal extension of the conformer perpendicular to the minimal projection area" (A) | Partly: the half-span of atom centres along each principal axis is held (`axis_half_spans`) but not reported as a distance, and it is atom-centre to atom-centre, not surface to surface | **Not comparable** (centre-to-centre vs unknown) | report it, with the surface (centre +/- vdW radius) definition stated; needs row 4 first |
| 9 | Max distance perpendicular to the max projection | same | same | same | same |
| 10 | van der Waals volume | volume of the conformer (A^3) | **Reported** in `Molecular Surface Area (3D)` and in the shape descriptors: analytic double-cubic-lattice volume at probe 0, cross-checked against RDKit's grid routine, validated on a sphere (4/3 pi r^3) | **Numerically checkable against a closed form, not against Marvin**: Marvin names no radii table. A different radii table moves it by percent, not by rounding | none; it lives in a different calculator from the energies |

## The five options

| # | Marvin option | Marvin says | OpenChem today | Gap |
|---|---|---|---|---|
| O1 | Energy unit | kcal/mol or kJ/mol | kcal/mol, fixed | add; **convert the stored energy**, never recompute |
| O2 | Set MMFF94 optimalization | "optimizes the structure before the MMFF94 energy calculation" | none: the energy is of the geometry as given | add; must work on a COPY, never moving the active molecule |
| O3 | Set projection optimalization | "optimizes the structure before the projection area and projection radius calculations" | none | add, same rule |
| O4 | Calculate for lowest energy conformer | If molecule is in 2D / Never / Always: "generates the lowest energy conformer" for 2D input, 3D input as given, or for both | none here. Conformer generation is a separate, explicit step with its own stop rule and settings (`docs/SCIENTIFIC_LIMITATIONS.md`, "The generation controls emulate Marvin's, not its algorithms") | add as "lowest of N", stated honestly: never "the global minimum" |
| O5 | Optimization limit | Very loose / Normal / Strict / Very strict; "lower gradient limit" for stricter | none; the Conformers settings have their own convergence | name the actual gradient and iteration limits in OpenChem's own terms; Marvin's four levels carry no numbers |
| - | Decimal places | number of decimals | `decimal_places`, presentation only | none |

## What the existing calculators already cover, and what retiring would lose

The plan proposed retiring `Geometry`, `Ligand Steric Bulk` and `Molecular Surface Area (3D)` in
favour of one. Read against the table, the three are not duplicates of Marvin's list:

| Calculator | Marvin rows it covers | Behaviour with no Marvin counterpart |
|---|---|---|
| `Geometry` | 1, 2, part of 4-7 | UFF energy, mean/min/max radius from the centroid, the axes drawn on the 3D view |
| `Molecular Surface Area (3D)` | 10 | solvent-accessible area and the ASA+/ASA-/ASA_H/ASA_P splits (not on the Geometrical Descriptors page; where Marvin documents them was not checked); the per-atom area dataset is a separate calculator |
| `Ligand Steric Bulk` | none (row 3 is a different quantity) | exact cone angle and %Vbur for ligands, validated against Tolman's ordering (r = 0.98) |

## Decisions this checklist supports (proposals, for Alex to react to)

1. **Retire nothing.** No row shows a replacement that covers an old calculator's behaviour,
   and the project rule is that a retirement needs exactly that. `Geometry` is extended;
   the other two stay and are cross-linked from it.
2. **Row 3 (steric hindrance) is not built.** Without a published formula any per-atom
   figure under Marvin's name would be unverifiable. `Ligand Steric Bulk` already answers
   the question people mean by it for ligands.
3. **Rows 4-9 are the one piece of real scientific work**: true minimisation of the
   projection over orientations, with the radius and perpendicular extension defined in
   OpenChem's own words on each fact. It has analytic checks (a sphere, a two-sphere
   dumbbell, a rod) that Marvin's numbers cannot provide.
4. **O1-O5 are cheap and are what "Marvin-style" most visibly means.** Energy unit as a
   stored-value conversion; the two "optimise first" options on a copy with the optimiser's
   own limits stated; "lowest of N candidates" for the conformer option.
5. **Comparison class for every Marvin row stays "qualitative" or "not comparable"** until
   somebody with the plugin supplies its output for a given structure with its conformer.

## Unknowns this page cannot settle

- Which Marvin version the page documents (none stated).
- Marvin's radii table for the projection and volume rows.
- What "radius" means in rows 6 and 7, and whether row 8 and 9 are centre-to-centre.
- The force-field implementation behind rows 1 and 2, and what "Strict" means in O5.
