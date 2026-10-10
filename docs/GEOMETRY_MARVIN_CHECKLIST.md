# Geometry and Marvin's Geometrical Descriptors: the definitions checklist

**What this is.** Stage 4 of the calculator-organisation plan proposed merging the
geometry calculators "Marvin-style". The plan's first deliverable is this table, written
BEFORE any code: for each quantity Marvin's plugin documents, what Marvin says it is,
what OpenChem already reports, and whether a number from one could be compared with a
number from the other. Nothing was built to produce it; the OpenChem column was read from
the source on 2026-10-10.

**Marvin's side is two pages.** ChemAxon's *Geometrical Descriptors Plugin* manual
(`https://docs.chemaxon.com/latest/calculators_geometrical-descriptors-plugin.html`, read
2026-10-10; the older `lts-iodine` copy says the same word for word) lists ten descriptors
and five options. The command-line page (`.../latest/calculators_cxcalc-calculator-functions.html`)
adds the options each function takes. **Neither gives formulas, defaults (apart from
precision 2 and solvent radius 1.4), a version, or references.** Everything in the "Marvin says" column is a paraphrase of
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

## What the cxcalc page adds (read 2026-10-10)

The plugin page shows a window; the command-line page shows what each function can be
told. Compared with the ten-and-five above, it adds:

| Finding | Detail | Consequence |
|---|---|---|
| **A radius scale factor** on the four projection area and radius functions | `-s/--scalefactor`, with no default, range or meaning on the page (a search snippet called it a "radius scale factor"; the page itself says nothing). The GUI page does not show it | If offered, it must be OpenChem's own, stated definition: a multiplier on the van der Waals radii the projection uses. Not "Marvin's" |
| **`-o/--optimization` belongs to conformer generation, not to the MMFF94 option** | `dreidingenergy`, `hindrance`, `volume` and the projection functions take `-o` and `-l` (the lowest-energy-conformer switch); `mmff94energy` takes `-l` and `--mmff94optimization` and **no `-o`** | **Inference, not stated:** the "Optimization limit" (row O5) is the convergence of the conformer search behind `-l`, not of the MMFF94 or projection "optimise first" options. The accepted values are truncated on the page; examples use 0, 2 and 3, so four levels numbered 0-3 is the likely meaning, with no mapping to "Very loose..." given |
| **The perpendicular functions are called `minimalprojectionsize` / `maximalprojectionsize`** | "the size of the molecule perpendicular to the minimal (maximal) projection area surface" | Same quantity as rows 8 and 9. "Size", not "distance"; still no statement of centre-to-centre versus surface-to-surface |
| **`volume` takes `-o` and `-l`** | the van der Waals volume is computed on a conformer generated by the same options | Marvin's volume depends on which conformer it generated; ours is of the conformer given |
| **A van der Waals surface area function** (`vdwsa`), with `-H` pH and `-i` increments | not in the ten descriptors | **OpenChem already computes it** (`ShapeDescriptors.surface_area`, analytic, validated on a sphere) **but no calculator reports it.** A free addition |
| **Surface calculators take a pH** | `asa`, `molecularsurfacearea` and `vdwsa`: "if a pH is set, the major microspecies at that pH is used"; otherwise the input as given | OpenChem's `Molecular Surface Area (3D)` has no pH option. A real gap, but in the surface calculator, not Geometry |
| **ASA takes a solvent radius** (`-r`, default 1.4) | the only radius documented anywhere | OpenChem's accessible surface uses RDKit's own probe and offers no option. A small gap, surface calculator |
| **Per-atom increments** (`-i`) on the surface functions | per-atom contributions to the area | Covered: `Accessible Surface Area (per atom)` |
| **`stericeffectindex`** is a separate function from `hindrance` | "Steric effect index", `-s/--single` | OpenChem's note stays right: the topological steric effect index has no single published definition here |
| `-l`'s likely default is `if2D` | listed first, and the GUI page lists "if molecule is in 2D" first | **Not stated** as a default on either page. Do not assert it |

Still unsettled by both pages: Marvin's radii, the force-field implementations, the
meaning of "radius" in rows 6 and 7, what the four optimisation limits are numerically,
and the units (the command-line page states only the energy units).

## What the existing calculators already cover, and what retiring would lose

The plan proposed retiring `Geometry`, `Ligand Steric Bulk` and `Molecular Surface Area (3D)` in
favour of one. Read against the table, the three are not duplicates of Marvin's list:

| Calculator | Marvin rows it covers | Behaviour with no Marvin counterpart |
|---|---|---|
| `Geometry` | 1, 2, part of 4-7 | UFF energy, mean/min/max radius from the centroid, the axes drawn on the 3D view |
| `Molecular Surface Area (3D)` | 10 | solvent-accessible area and the ASA+/ASA-/ASA_H/ASA_P splits (not on the Geometrical Descriptors page; where Marvin documents them was not checked); the per-atom area dataset is a separate calculator |
| `Ligand Steric Bulk` | none (row 3 is a different quantity) | exact cone angle and %Vbur for ligands, validated against Tolman's ordering (r = 0.98) |

## Decisions this checklist supports

Agreed 2026-10-10 (Alex): **the smaller scope**, not the merge. Retire nothing.

1. **Retire nothing.** No row shows a replacement that covers an old calculator, and the
   project rule is that a retirement needs exactly that. `Geometry` is extended; the other
   two stay and are cross-linked from it.
2. **Row 3 (steric hindrance) is not built.** Without a published formula any per-atom
   figure under Marvin's name would be unverifiable. `Ligand Steric Bulk` already answers
   the question people mean by it for ligands.
3. **Rows 4-9, the one piece of real scientific work**: true minimisation of the projection
   over orientations, with the radius and perpendicular size defined in OpenChem's own
   words on each fact, checked against a sphere, a two-sphere dumbbell and a rod.
4. **O1-O5**: energy unit as a stored-value conversion; the two "optimise first" options on a
   copy; "lowest of N candidates" for the conformer option; and the optimisation limit
   read as the conformer search's convergence (the inference above), in OpenChem's own
   gradient and iteration terms.
5. **Added by the second page, small:** report the van der Waals surface area the shape code
   already computes; a radius scale factor on the projection, defined as a multiplier on
   the vdW radii.
6. **Added by the second page, outside Geometry (offered, not agreed):** a pH and a solvent
   radius on `Molecular Surface Area (3D)`.
7. **Comparison class for every Marvin row stays "qualitative" or "not comparable"** until
   somebody with the plugin supplies its output for a given structure with its conformer.

## Unknowns these pages cannot settle

- Which Marvin version the page documents (none stated).
- Marvin's radii table for the projection and volume rows.
- What "radius" means in rows 6 and 7, and whether row 8 and 9 are centre-to-centre.
- The force-field implementation behind rows 1 and 2, and what "Strict" means in O5.
