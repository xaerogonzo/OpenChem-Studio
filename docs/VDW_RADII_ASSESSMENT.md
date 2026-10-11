# Van der Waals radii: what this application uses, where it comes from, and what the choice changes

Investigated 2026-10-11, after reading Bondi's 1964 paper for the explainers and finding that the numbers the code calls
"Bondi radii" are not in it. Every claim below is one of three kinds and says which: **read** (from a paper or a source
file), **measured** (a run, with the method stated) or **reported** (seen only through a search summary, not read
directly). The decision it asks for is at the end.

## Update (Alex, 2026-10-12): the surface calculators moved to Bondi's list too

After the evidence below (Bondi's own volumes reproduced best by his list, and a provenance gain for one table behind every
calculator), Alex chose the version bump: **the accessible surface, van der Waals volume, projections and Geometry now use
Bondi's own radii** (`chem/vdw_radii.py`), as Ligand Steric Bulk already did. Methods `surface-v3` and `geometry-v3`; results
saved by `surface-v2` and `geometry-v2` are kept beside the new ones, labelled "previous method", never replayed as the new.
Hydrogen stays 1.20. Two consequences worth recording:

- **The volume routine had to change.** RDKit's `DoubleCubicLatticeVolume` and `ComputeMolVolume` take no radii, so the volume
  is now `sasa.enclosed_volume` (the divergence theorem over the same surface points the areas use) with `sasa.grid_volume`
  as the independent check. Measured on six molecules against a 0.03 angstrom grid, the new volume is within 0.25% and
  RDKit's routine within 1.2%; a lone sphere is exact. The old "lone atom is the known exception to the cross-check" is gone.
- **The size of the move, over 17 drug-like molecules** (v3 against v2): accessible area -0.4% on average (worst -1.9%), van der
  Waals volume -1.4% (worst -4.5%), smallest shadow -0.8% (worst -2.8%), largest shadow -0.7% (worst -2.4%). All of it comes
  from the elements the two tables disagree about; hydrocarbons are unchanged.

What stays open is Question 2, the docking table's metals, which is a logic fix more than a radius.

## The decision (Alex, 2026-10-11): what it was before the update above

- **B for the steric calculator.** Ligand Steric Bulk now uses Bondi's own radii (`chem/vdw_radii.py`, method `steric-v2`),
  extended where Bondi gave none by Mantina et al.'s sixteen. Older saved results are kept and labelled
  (`legacy-rdkit-radii-v1`), never replayed as the new method.
- **A for everything else (superseded 2026-10-12, see above).** The surface, volume, projection and Geometry calculators kept
  RDKit's table, **called what it is** in the code, the Geometry result's limitation line and the stored provenance
  (`radii: "rdkit_rvdw"`). No number changed. They have since moved to Bondi's list.
- **C (hydrogen 1.10) is not taken for the surface calculators**, after reading Rowland and Taylor and Mantina et al.: see
  "What the three papers add".
- The docking module's table keeps hydrogen 1.10, which is the right value for the thing it does (contacts), and is now
  documented as such.

## The short version

- The surface, volume, projection and steric calculators take their radii from `rdkit.Chem.GetPeriodicTable().GetRvdw`,
  and the code, the docstrings, one user-facing result line and two stored provenance fields call that table "Bondi".
- It is **not** Bondi's list. RDKit's header says only that its radii were "taken from BODR v10.1" (the Blue Obelisk Data
  Repository), BODR cites no source, and the values equal the **recommended crystallographic radii of Batsanov (2001) for
  all 65 elements** his Table 9 lists, exactly. That is an identification by agreement, and a test now pins it.
- Bondi's own recommended values (read from the 1964 pages) differ from RDKit's for nitrogen, oxygen, fluorine,
  phosphorus, chlorine, bromine and iodine.
- On accessible and van der Waals areas the table choice matters little (a mean of 0.4% on 17 molecules), but the
  **hydrogen** radius matters a lot (1.10 against 1.20 moves areas 3 to 7%). On **percent buried volume** the table
  matters a lot: RDKit's larger phosphorus radius puts small phosphines 2 to 3.6 points high, and Bondi's own list is
  closer to the published values.
- The application has **two** radius tables. The docking module keeps its own, which really is Bondi's (with the CRC
  Handbook's hydrogen).

## What the application says, and where

| Where | What it says |
|---|---|
| `chem/surface_analysis.py` (docstrings, `atomic_radii`) | "RDKit's own Bondi table, the same one the van der Waals volume, surface and projections use, so there is one definition of how big an atom is across the application" |
| `chem/projection_geometry.py` | "RDKit's own Bondi radii, asked rather than duplicated" |
| `chem/steric.py` | "%Vbur ... the SambVca convention, R = 3.5 A, Bondi radii scaled by 1.17, hydrogens omitted" |
| `chem/geometry_analysis.py` | a **user-facing** limitation on the shadow facts: "Bondi van der Waals radii." |
| `chem/surface_analysis.py` | stored in every result's provenance: `"radii": "bondi"` |
| `chem/pose_analysis.py` | its own `_VDW_RADII`, also called Bondi, **and the only one that is** (hydrogen 1.10) |

## The provenance chain

1. **RDKit's current table.** `Code/GraphMol/atomic_data.cpp` lists the Rvdw column as "rVdw (taken from BODR v10.1)". It
   never names Bondi, and says "Ds ... Og: we use 2.0 for all of them" because BODR has none. *Read.*
2. **How it got there.** rdkit/rdkit#2154, "Use van der Waals radii from blue obelisk", merged 2019-05-29 for the 2019.09
   release. Its first commit says the radii were updated "to follow the Blue Obelisk Data Repository" from "Ubuntu package
   bodr version 10-1 ... /usr/share/bodr/elements.xml", and changed the default for missing elements from 1.7 to 2.0. The
   maintainers measured "no significant impact on conformation quality in either direction" on the Platinum and ETKDG v2
   sets, and noted the radii are used in conformer generation. No paper, DOI or table is cited anywhere in the thread.
   *Read.*
3. **BODR's own file.** The `elements.xml` in the Blue Obelisk repository lists the radii as `bo:radiusVDW` in angstrom
   with no source attribute, and the Debian package's README names no source for any element data. *Read.*
4. **What the numbers are.** Compared element by element with Batsanov, *Inorganic Materials* 2001, 37, 871, Table 9
   (upper figures, "recommended crystallographic" radii), RDKit's `GetRvdw` is **equal for all 65 of 65** elements,
   including the unusual ones (boron 1.8, silicon 2.1, phosphorus 1.95, selenium 1.9). *Measured, from a publicly
   hosted copy; `tests/test_vdw_radii_provenance.py` and `tests/fixtures/vdw/batsanov2001_table9.csv` keep it checked.*
5. **Before 2019 it was a different table again.** RDKit's 2018.09 data had H 1.2, B 2.08, C 1.95, N 1.85, O 1.70, F 1.73,
   Si 2.1, P 2.08, S 2.0, Cl 1.97, Se 1.9, Br 2.1, I 2.15. So "Bondi" was never RDKit's table in any release, and this
   quantity has already moved once under a dependency upgrade (carbon by 0.25 angstrom). *Read.*
6. **Other tables in the neighbourhood.** Open Babel's data file header is reported (search summary; the raw file could
   not be fetched) to name Mantina et al. 2009 as its van der Waals source and to give hydrogen 1.10, which would make it
   a third table, not RDKit's. ChemAxon publishes no radius table for Marvin: a staff reply on their forum describes
   "spheres at the atomic centres" without saying which radii. *Reported.* So **comparability with Marvin cannot be
   claimed on the radii, whichever table is used.**

## The sets side by side (angstrom)

| | Bondi 1964 (paper) | CRC Handbook 97th | Batsanov 2001 = RDKit now | RDKit before 2019 | docking module |
|---|---|---|---|---|---|
| H | 1.20 | 1.10 | not tabulated (RDKit 1.20) | 1.2 | 1.10 |
| C | 1.70 | 1.70 | 1.7 | 1.95 | 1.70 |
| N | 1.55 | 1.55 | 1.6 | 1.85 | 1.55 |
| O | 1.52 | 1.52 | 1.55 | 1.70 | 1.52 |
| F | 1.47 | 1.47 | 1.5 | 1.73 | 1.47 |
| Si | 2.10 | 2.10 | 2.1 | 2.1 | none |
| P | 1.80 | 1.80 | 1.95 | 2.08 | 1.80 |
| S | 1.80 | 1.80 | 1.8 | 2.0 | 1.80 |
| Cl | 1.75 | 1.75 | 1.8 | 1.97 | 1.75 |
| Br | 1.85 | 1.85 | 1.9 | 2.1 | 1.85 |
| I | 1.98 | 1.98 | 2.1 | 2.15 | 1.98 |

Bondi's column is read from the paper's own pages and agrees with Poater et al.'s Table 1 and with Batsanov's Table 1 row
for him. The CRC Handbook, which Bondi's radii are "the most widely used values" in, adopts his values for the main group
**except hydrogen**, for which it takes Rowland and Taylor's 1.10; it fills the elements Bondi did not cover from Mantina
et al. (2009). (Bondi's own hydrogen is 1.20 for aliphatic and 1.00 for aromatic environments, in his Tables XII and XIII;
his recommended list uses 1.20.) Boron and selenium are omitted from the CRC column because the table text did not
parse cleanly for them.

## What the choice changes (measured)

**Areas.** 17 molecules (aspirin, caffeine, ibuprofen, paracetamol, morphine, fluoxetine, chloroquine, sildenafil,
glyphosate, bromobenzene, iodobenzene, DMSO, urea, glycine, ethanol, benzene, trimethyl phosphate), one RDKit-embedded,
MMFF94-relaxed conformer each (seed 7), the application's own Shrake-Rupley routine at 2000 points. Difference from the
RDKit table:

| | accessible area (1.4 A probe) | van der Waals area (probe 0) |
|---|---|---|
| Bondi's list, hydrogen 1.20 | mean -0.4% (range -1.9% to 0.0%) | mean -0.5% (range -2.6% to +1.0%) |
| CRC set, hydrogen 1.10 | mean -3.2% (range -4.1% to -2.4%) | mean -5.2% (range -7.4% to -3.6%) |

The largest effect among the heavy-atom differences is iodobenzene (-1.9% and -2.6%); benzene, with only carbon and
hydrogen, does not move. **The hydrogen radius, not the nitrogen or oxygen one, is the lever.**

**Steric bulk.** The six phosphines PH3, PMe3, PEt3, PPh3, PCy3 and PtBu3, ten conformers each. The **exact cone angle is
identical** under both tables (86.39, 117.20, 146.25, 163.80, 169.55, 193.65), because the atoms that set the cone are
hydrogen and carbon, which agree. **Percent buried volume is not**: RDKit's table gives 21.26, 24.41, 28.43, 30.82, 34.90,
39.68 and Bondi's own list gives 17.65, 22.38, 26.75, 29.29, 33.59, 38.70. The cause is phosphorus: 1.95 x 1.17 = 2.28
angstrom against 1.80 x 1.17 = 2.11, and for PH3 (hydrogens are omitted) phosphorus is the whole answer.

Against Clavier and Nolan's Table 1 (published, from crystal structures, M-P 2.28 angstrom: PMe3 22.2, PEt3 27.8, PPh3
29.6, PCy3 31.8; P(t-Bu)3 is left out because its printed 2.28 value, 26.7 against 42.4 at 2.00, looks anomalous and was
not checked): the application with **RDKit's table** has a mean absolute error of **1.8 points**, with **Bondi's list**
**0.8 points**. The published values come from crystal geometries and these from free MMFF ligands, so the comparison is
indicative, but the direction is what the convention predicts: SambVca uses Bondi's radii.

## What follows

- **Areas and volumes** are within about 2% of Bondi's list either way, so nothing already reported is badly wrong, but
  the label is false for seven elements and the shadows' user-facing line says so wrongly.
- **Percent buried volume** departs from the convention the code states, by an amount larger than the published scatter
  among small phosphines.
- **Reproducibility.** A result's provenance says `radii: "bondi"`, which is untrue, and the real table has changed once
  under an upgrade with nothing in the stored result to show it.
- **Consistency.** "One definition of how big an atom is across the application" is not true while the docking module
  keeps its own table.

## What the three papers add (read 2026-10-11), and why C is not taken for areas and volumes

**Bondi (1964) says what his radii are for.** They "have been selected for the calculation of volumes" and "may not always be
suitable for the calculation of contact distances in crystals" (the second quoted by Rowland and Taylor). That is
exactly the use here, and exactly not the use of the 1.10 hydrogen. His own Table I (read from the page image) gives
hydrogen 1.20 and the nonmetal radii in the table above; his recommended list leaves boron, aluminium, germanium and
antimony blank.

**Rowland and Taylor (1996) find Bondi's radii "highly consistent" with the contacts in 28,403 organic crystal structures, with
one exception: hydrogen.** Hydrogen contact distances were computed with hydrogens moved to neutron C-H, N-H and O-H lengths
(1.083, 1.009, 0.983 angstrom). Bondi's 1.2 is "probably too high by about 0.1 A". But they also find, and say, that
**H...H contacts in neutron structures support about 1.19, "almost identical to Bondi's value"**, because Bondi's hydrogen
rested largely on H...H contacts (Kitaigorodskii's adamantane work). Only the H...O and H...N contacts, shortened by
electrostatic attraction, call for less. Their 1.1 is "a weighted average over several different types of H...X
distribution", offered as "a better compromise" for transferability across contact types. For the other elements they
"see no reason to move away from Bondi's data" (for O, F, S, Cl, Br and I the difference is 0.04 angstrom or less),
with carbon (0.05) and nitrogen (0.06) the largest.

**Mantina et al. (2009) adopt 1.10 for their standard set and say why, and what it costs.** "Bondi's value of 1.2 A describes
well the size of H in H...H contacts, but for interactions with other elements, the smaller value is more appropriate.
Bondi had drawn similar conclusions, but he favored using the higher value as a standard. We accept the Rowland-Taylor
recommendation for H." They extend Bondi's scale to the sixteen main-group elements he left out, correlating his radii
with repulsive-wall distances from relativistic coupled-cluster calculations. Their Table 9 prints two Bondi values that
the paper does not (bromine 1.83 against 1.85, lithium 1.81 against 1.82).

**What follows for hydrogen.** The two values answer different questions. 1.10 is a contact-distance compromise across
H...X pairs. 1.20 is what hydrogen is against another hydrogen, and for the surface of an organic molecule, which is
mostly hydrogen facing hydrogen, that is the contact that sets the area. Bondi's purpose (volumes), the surface
calculators' purpose (areas and volumes) and the buried-volume papers' convention (Bondi's scale) all point to 1.20; a
contact test, which is what the docking module does, points to 1.10. So **the two tables are not an inconsistency to
remove but a difference of purpose to document**, and the geometry the application builds has X-H lengths within 0.01
angstrom of the neutron-normalised ones Rowland and Taylor used (measured on seven molecules: C-H 1.093, N-H 1.014, O-H
0.978 against their 1.083, 1.009, 0.983), which suits a contact table.

**What follows for the other elements.** RDKit's values (Batsanov's crystallographic set) differ from Bondi's by 0.03 to
0.05 angstrom for nitrogen, oxygen, fluorine, chlorine and bromine, which Rowland and Taylor's own scatter covers, and by
0.15 for phosphorus and 0.12 for iodine, where Bondi's own evidence is thin (he had "only very few" phosphorus contacts and
set 1.80 from them and from the ionisation potential). For areas the effect is small and measured above; for the
buried volume it is not, which is why that calculator, and only that one, follows Bondi.

## Options, and what was decided

- **A. Relabel only** (done for the surface, volume, projection and Geometry calculators): the code comments, the Geometry
  limitation line and the stored provenance say "RDKit's table" and no number moves.
- **B. Adopt Bondi's own list** (done for the steric calculator): one project-owned table with its sources, method version
  `steric-v2`, older results kept and labelled. Buried volumes move toward the published ones (mean error 0.8 points
  against 1.8); the exact cone angle does not move.
- **C. The CRC set, hydrogen 1.10** (not taken for areas): it would lower every area and volume 3 to 7% to buy a contact
  compromise the area calculators do not need, and Bondi's, Rowland and Taylor's and Mantina et al.'s own words all put
  1.20 on the volume side.

## The three open questions, researched further (2026-10-11)

**1. Should the surface calculators follow Bondi's list too?** Bondi's own Tables XV and XVI give a volume increment for
each functional group, which makes a published oracle for the one question the application can check against him: does
a radius table reproduce his volumes? Seventeen molecules with no hydrogen bond and no crowding correction (alkanes,
five halides, an ether, a nitrile, a ketone, a nitro compound, a sulfide, an amine) were measured with each table on one
MMFF94 geometry each (`radii_study.py`, `group_volumes`):

| table | mean signed | mean absolute | worst |
|---|---|---|---|
| Bondi 1964 | -0.3% | 1.3% | 2.9% |
| RDKit (Batsanov) | +1.1% | 2.0% | 5.2% (nitromethane; iodoethane and chloromethane +4.6%) |
| CRC, hydrogen 1.10 | -7.5% | 7.5% | 10.5% (every hydrocarbon about -10%) |

Two things follow, and one does not. **Hydrogen 1.10 is settled for volumes**: it misses Bondi's own methane by 10%, so
C stays refused for the surface and volume calculators. **RDKit's table is within a few percent of Bondi's convention
for hydrocarbons (identical there) and overshoots for halides and nitro compounds**, which Bondi's list does not. What
this does **not** show is that Bondi's list is the better description of a real molecule: the oracle is Bondi's own
arithmetic, so it measures agreement with his convention, not with nature. The decision to move the surface
calculators is therefore a question of which convention to follow, and the evidence is that Bondi's is the one the
volume and area literature (and the buried-volume papers) use. It still needs a method-version bump and the legacy
slot, and it is left for Alex.

**2. The docking table's `Fe` 1.56.** It entered with the table on 2026-07-30 with no source in the commit or the comment.
It is not Bondi's: Table I has no iron, and Table XIV's metals are Li, Na, Mg, K, Ni, Cu, Zn, Ga, Pd, Ag, Cd, In, Sn, Pt,
Au, Hg, Tl, Pb and U (the application's Zn 1.39, Mg 1.73, Na 2.27 and K 2.75 do match it, and Ca 2.31 is Mantina's).
It is not Mantina's, which treats main-group elements only, and it is not Batsanov's, whose Table 9 gives iron 2.05
(which is also RDKit's). A search of the maintainer's library for a page holding "van der Waals", "1.56" and "iron"
found nothing. The value is therefore untraced and should be read as an undocumented placeholder; **a hypothesis, not
a finding**, is that it is a calculated atomic (not van der Waals) radius, but nothing read here says so. It matters
little, as an expectation not measured here: iron in a protein receptor is typically the metal of a heme or an iron-sulfur cluster, bonded to atoms
that sit at 2.0 angstrom, so the contact test is not about its van der Waals size. Replacing it needs a source for
what the table means by a metal's radius, not a different number.

**3. A Geometry result saved before this change (decided and built, 2026-10-11).** Its stored limitation line said
"Bondi van der Waals radii.", which was never true. The numbers in it are correct and unchanged, so a method-version bump
(which marks a previous method and implies its numbers differ) would say something false in the other direction. Instead a
**reader's note** is applied when the saved result is loaded (`STORED_TEXT_NOTES` in `domain/result_store.py`): that exact
line is shown as "Van der Waals radii from RDKit's table (Batsanov's recommended set, not Bondi's). This result was saved
when they were labelled Bondi's; its numbers are unchanged." The numbers, the provenance and the method version are not
touched, and only an exact match is replaced.

## Five more papers, and what they say (2026-10-11, later)

**The volume check, on 46 molecules from a second transcription of Bondi** [source:zhao2003]. Zhao, Abraham and Zissimos's
Tables 1 and 3 give Bondi's group-contribution volumes for alkanes, alkenes and alkynes, heteroatom compounds, halides, rings
and aromatics, and they agree with the application's own transcription of Bondi's tables to within 0.1 cubic angstrom. Measured with a
0.04 angstrom grid on one MMFF94 geometry each (`radii_study.py`, `zhao_volumes`):

| set | RDKit (Batsanov) mean abs | Bondi 1964 mean abs | CRC, hydrogen 1.10 mean abs |
|---|---|---|---|
| all 46 | 2.12% | 1.84% | 7.71% |
| acyclic hydrocarbons (17) | 1.91% | 1.91% | 9.81% |
| N, O, S, P compounds (11) | 2.04% | 1.86% | 7.26% |
| halides (9) | 3.14% (mean +3.14%) | 1.95% (mean -0.40%) | 5.91% |
| rings (5) | 1.13% | 1.09% | 8.22% |
| aromatics (4) | 2.22% | 2.22% | 3.41% |

**What this settles and what it does not.** Hydrocarbons are identical in the two tables, so nothing moves there. The whole
gain from Bondi's list is in halides and some heteroatoms: about 1 to 3 points of volume, and for a typical drug-like molecule
well under 1%. The largest errors for both tables are structural and are not fixed by any radii table: acetylene (-9.8%
for both) and benzene (+4.0% for both) need Bondi's own special radii for sp and aromatic carbon, which one radius per element
cannot supply. So moving the surface calculators to Bondi's list is a provenance and consistency improvement (one table
behind steric and surface, every value traced to a paper), not an accuracy one for common molecules. Hydrogen 1.10 is
refuted again, at 7.7%.

**Gavezzotti's convention** [source:gavezzotti1983] is a fourth set (H 1.17, C 1.75, N 1.55, O 1.40, F 1.30, Cl 1.77, Br 1.95,
I 2.10) computed by the same random-point counting used here, and he reports volumes within 10% of Bondi's. Zhao et al. note
that programs give ethanol's volume as 76, 41 or 52 cubic angstrom. Together with Alvarez's larger contact-based radii, the
literature offers no single true radius for a surface, only conventions, and Bondi's is the one the volume literature and the
buried-volume papers share.

**Metal-donor distances**, from Harding's papers, current table [source:harding2006] (supersedes [source:harding2001] and
[source:harding2002]). Target metal-donor distances in angstrom, small-molecule and protein structures combined, read from the
paper's own Table 4 (a mark of three stars means a standard deviation of about 0.05, two 0.10, one 0.15 to 0.20):

| metal | O water | O carboxylate | O carbonyl | N histidine | S cysteine |
|---|---|---|---|---|---|
| Na | 2.41 | 2.41 | 2.38 | | |
| K | 2.81 | 2.82 | 2.74 | | |
| Mg | 2.07 | 2.07 | 2.26 | | |
| Ca | 2.39 | 2.36 | 2.36 | | |
| Fe | 2.09 | 2.04 | 2.04 | 2.16 | 2.30 |
| Co | 2.09 | 2.05 | 2.08 | 2.14 | 2.25 |
| Zn | 2.09 | 1.99 | 2.07 | 2.03 | 2.31 |

**Nickel** is not in Harding. Zheng et al.'s Table 3, from the Cambridge Structural Database [source:zheng2017], gives Ni-O
(water) 2.08, Ni-N 1.89 and 2.09 and Ni-S 2.18 and 2.46 (two values each where given), and for cobalt Co-N 1.95 and 2.14, which agrees
with Harding's 2.14. A donor is in the primary coordination sphere within the target plus 0.5 angstrom for the transition
metals, Mg and Ca, but **plus 0.75 for sodium and potassium** [source:harding2002], whose interactions are "predominantly
electrostatic" and for which a distance 0.5 angstrom shorter than the target is not acceptable while one 0.5 longer is
possible. Weakly bonded extra N and O donors of Zn and Cu sit at 2.4 to 3.0 and 2.6 to 3.0 angstrom [source:harding2000],
"shorter than a van der Waals contact". Harding 2002's conclusions printed the sodium and potassium distances interchanged;
the corrigendum gives K 2.84 and Na 2.42 [source:harding2013] (the tables were right).

Four things follow for the code. **The 2.8 angstrom coordination cutoff** is a good size for the transition metals (target plus
0.5 is 2.5 to 2.9) but is **too short for potassium** (target 2.81, so the primary sphere runs to about 3.6), and a single
number cannot be right for both. **Sulfur belongs among the donors** (Zn-S 2.31, Fe-S 2.30, Co-S 2.25, Ni-S 2.18), which
`interaction_analysis` excludes. **The docking table has no sourced distance for any metal not in the table above**; nickel
now has one (Zheng), manganese and copper have Harding's. And a **bond to a metal is not a contact**, which is the logic fix
described below; sodium and potassium are the cases where even that threshold is soft.

**More on why no contact-based radius is used for metals.** Chernyshov, Ananyev and Pidko [source:chernyshov2020] find that sums
of tabulated radii, Bondi's included, fall short of the energy-minimum distance by as much as 0.3 to 0.4 angstrom, which is a
statement about contacts and not about volumes (Bondi chose his radii for volumes), and that the concept of a van der Waals
radius should be applied with special care to atoms in confined tetrahedral or octahedral environments, naming most d and f
elements. That is the same caution as Alvarez's, and the reason the metals' radii are not a free parameter to be tuned.

## A third published set, and what it did to the Fe question (2026-10-11)

Alvarez's 2013 radii [source:alvarez2013], deduced from over five million contacts in the Cambridge Structural Database,
are the first set that covers iron, and it puts it at **2.44 angstrom**, with Batsanov's 2.05 and no Bondi value. The
application's 1.56 is therefore supported by none of the three published sets, and it is not close to any of them. The same
table puts the docking table's other metals far above the application's values: Zn 2.39 (the application has 1.39), Mg 2.51
(1.73), Na 2.50 (2.27), Ca 2.62 (2.31). Bondi's metal radii are, by the paper's own account, in several cases a cutoff
distance and not a van der Waals radius, so the two sets are not measuring the same thing. For hydrogen the paper
independently gets 1.20 from neutron-diffraction H...H contacts and says it needs no modification to Rowland and Taylor's
1.10, which agrees with keeping 1.20 for areas and volumes.

**The finding that changes the question: the docking pose analysis counted a coordinated metal as a clash (fixed
2026-10-11).** The radius does not matter as much as how it is used. `analyze_pose` reports a clash for any pair closer
than the sum of the two radii less 0.4 angstrom, and it treated a metal as an ordinary atom. Measured with an imidazole
(MMFF94-optimised) given a metal along the lone pair of its pyridine-type nitrogen: zinc at 2.1 angstrom, iron at 2.0 and
magnesium at 2.1 each gave one clash and one metal coordination, and calcium and sodium at 2.4 gave three clashes and one
coordination. The extra two were the nitrogen's own ring carbons, 3.39 and 3.40 angstrom from the metal, which is not a
contact: it is what the bond's geometry puts there (the M-N-C angle at a coordinated imidazole is 126-131 degrees, Harding
1999 Table 6 [source:harding1999]). A better radius would have made it worse (Alvarez's 2.44 for iron puts the threshold at
3.6 angstrom, and every coordinated donor and its neighbours would clash).

**What was decided**, in `_metal_bonded_pairs` (`chem/pose_analysis.py`), which `analyze_pose` consults before the clash test:

1. **A ligand donor within bonding range of a receptor metal is not a contact.** Donors are N, O, F and S, exactly the set
   the metal-coordination detector already used (so a pair can no longer be both), and the range is from
   `METAL_DONOR_MIN_DISTANCE` = 1.8 to `METAL_COORDINATION_CUTOFF` = 2.8 angstrom. The upper bound was already there; it is
   the loosest bond Harding supports (he accepted Ca...O to 2.80 as a bond, and found weak Zn donors at 2.4-3.0 and Cu at
   2.6-3.0 [source:harding1999] [source:harding2000]), not a typical one, since his means for the donors tested run from
   1.99 to 2.44. The lower bound is new and is there so an overlap does not pass as a bond: the shortest metal-N/O/S distance
   in the survey is 1.81 angstrom (a Cu-phenolate outlier; Mn 1.83 and Fe 1.84 are the shortest regular ones). It is one
   value for every donor, which is loose for sulfur (its own shortest is 2.18, Fe-thiolate); a per-donor floor was not built.
   Harding's primary coordination sphere is the target plus 0.5 angstrom (about 2.5 for Zn-N, 2.9 for Ca-O) [source:harding2006], so the single
   2.8 cutoff also exempted weakly bonded donors outside it for Zn, Fe, Mg and Cu, which Harding 2000 finds "shorter than a van
   der Waals contact". **Superseded 2026-10-12: the window is now per metal and per donor, see below.**
2. **The donor's neighbours are the bond's own geometry, against that metal only.** Every ligand atom within two bonds of a
   coordinating donor is left out of the clash test against the metal the donor binds, and stays in it against every other
   atom. Two bonds is `interaction_analysis.MIN_SEPARATION["clashes"]` (a bond-path separation under four is not a contact)
   with the metal counted as bonded to the donor; it is also where a six-membered chelate ring puts its far atom (the
   central carbon of acetylacetonate on calcium is two bonds from both oxygens and about 3.3 angstrom from the metal). Atoms
   further out keep the ordinary radius test. A second metal pressed against another part of the same ligand still clashes.
3. **A ligand's own metal bound by a receptor N, O, F or S is exempt the same way, and is now reported.** The detector used
   to look only from the ligand's donors to the receptor's metals; exempting this pair without reporting it would have made
   the contact vanish from both lists, so it appears in `metal_coordination` with the metal as `ligand_element` and the
   donor as `receptor_element`. The receptor has no bonds, so only the pair itself is exempt, not a neighbourhood.
4. **The radii are unchanged**, and the table's metal entries now say they are placeholders for a non-bonded contact. They
   were not replaced with Alvarez's: that would move every non-bonded metal contact the application reports, on a radius
   defined as the edge of a contact-distance peak rather than a cutoff, and nothing has measured what it would do. The Fe
   1.56 stays untraced; it simply no longer decides anything about iron's own ligands.

**Measured after** (the same five geometries): 0 clashes and 1 coordination for all of Zn at 2.1, Fe at 2.0, Mg at 2.1, Ca at
2.4 and Na at 2.4. `tests/test_pose_analysis_metals.py` runs these through `analyze_pose`, with Harding's means for Zn, Fe, Mn,
Cu, Ca and Mg, a chelate ring, the boundaries (overlap, just outside the cutoff, a non-bonded atom, a second metal), a sweep
over every metal and donor that no distance is both a coordination and a clash, and the ligand-metal direction. Eleven
mutants of the fix (no skip, depth 0, depth 1, no floor, a cutoff 0.5 too wide, neighbours exempt against every metal, the
ligand direction not exempted or not reported, fluorine or sulfur dropped as a donor, any receptor atom as a donor) are all
killed.

**Per-metal bond windows (built 2026-10-12), which close the first of the two things this left open.** The donor window was one
pair of numbers (1.8 to 2.8 angstrom) for every metal and donor. It is now `pose_analysis.metal_bond_window(metal, donor)`,
from `METAL_DONOR_TARGETS`: the distance a bond from that metal to that kind of donor is expected to have, by donor element
(N, O, S; fluorine reads oxygen's, an assumption with no source), taken from Harding 2006 Table 4 for Zn, Fe, Co, Mn, Cu,
Mg, Ca, Na and K [source:harding2006] and, for nickel, which Harding does not cover, from Zheng et al.'s CSD means
[source:zheng2017]. The N and S entries for Mg, Ca, Na and K are Harding's own estimates, marked as such in his 2001 and
2002 tables [source:harding2001] [source:harding2002]. The window is **the target plus 0.5 angstrom, and plus 0.75 for
sodium and potassium; its floor is the target less 0.5, never below 1.8** (the shortest distance in his survey). For
sodium and potassium a donor out to the target plus 0.95 (his secondary sphere) is not a bond but is a normal contact of an
ion, so it is left out of the clash test as well.

| pair | old window | new window |
|---|---|---|
| Zn to N | 1.8 to 2.8 | 1.80 to 2.53 |
| Zn to S | 1.8 to 2.8 | 1.81 to 2.81 |
| Fe to N | 1.8 to 2.8 | 1.80 to 2.66 |
| Ca to O | 1.8 to 2.8 | 1.89 to 2.89 |
| Na to O | 1.8 to 2.8 | 1.91 to 3.16 (not a clash to 3.36) |
| K to O | 1.8 to 2.8 | 2.32 to 3.57 (not a clash to 3.77) |

What moved, each measured through `analyze_pose` (`tests/test_pose_analysis_metals.py`): potassium to oxygen at 3.5 angstrom was
a steric clash (the radius rule's threshold is 3.87) and is now a coordination; at 3.7 it is neither, and at 3.8, past
Harding's secondary sphere and inside the radius rule, it is a clash again. Zinc to a histidine nitrogen at 2.7 angstrom was a
coordination and is not (it is Harding's weak-interaction range for zinc, 2.4 to 3.0). Sodium to oxygen at 1.85 angstrom,
above the survey floor but under sodium's own 1.91, is overlap and stays a clash. The same function decides the
`metal_coordination` lines of Interaction Analysis (method `interactions-v3`; a v2 result is kept, labelled), so the two
calculators cannot disagree, and the sweep that no distance is both a coordination and a clash now runs over every window.
**What stays open:** the metal radii themselves are untouched, so a non-bonded contact with a metal is still judged by the
placeholder radii above (Fe 1.56 among them), and a saved docking result keeps the clash list it was analysed with.
(b) **A saved docking result keeps what it was analysed with.** Interaction data
lives in `DockingPoseModel.metadata`, written once by the docking job and saved in the project file; nothing recomputes it
on load. Results saved before this change still list the coordinated metal under clashes. The method-version mechanism in
`domain/result_store.py` is keyed by calculator result id and does not reach docking poses, so no version was bumped and
no note was attached; re-running the dock (or the analysis) replaces them. (c) **The same defect is in `interaction_analysis.find_interactions`, which analyses a ligand with itself, and is not fixed here.**
Measured 2026-10-11 with a zinc 2.0 angstrom from an imidazole nitrogen: a zinc bonded in the molecule is correctly left alone
(its bond-path separation from the nitrogen is under four), but a zinc drawn as a separate fragment (`c1c[nH]cn1.[Zn+2]`)
gives one clash and one metal coordination.

## Not verified

- BODR's real origin. The identification with Batsanov rests on exact equality across 65 elements, not on any statement
  by RDKit or BODR.
- The Open Babel header and the ChemAxon forum reply were seen through search summaries only.
- Bondi's group increments for volume were read from Tables XV and XVI and used for the oracle above; his area increments, his Table XVII corrections and the other nine tables of Batsanov were not used. The oracle's molecules are 17 and share one MMFF94 geometry each.
- Mantina et al. 2009 and Rowland and Taylor 1996 are now read, and Alex's copy of Batsanov matches the public one first read. What was read of each is in its registry row, with what was not.
- The published buried volumes come from crystal geometries; the application's from free ligands.

## Reproduce

The comparison script is `benchmarks/vdw_radii/radii_study.py` (run it with `uv run python benchmarks/vdw_radii/radii_study.py`
from the repository root); `tests/test_vdw_radii_provenance.py` holds the table equality and the statements above that
could silently stop being true.
