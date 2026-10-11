# Van der Waals radii: what this application uses, where it comes from, and what the choice changes

Investigated 2026-10-11, after reading Bondi's 1964 paper for the explainers and finding that the numbers the code calls
"Bondi radii" are not in it. Every claim below is one of three kinds and says which: **read** (from a paper or a source
file), **measured** (a run, with the method stated) or **reported** (seen only through a search summary, not read
directly). The decision it asks for is at the end.

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

## Options, and a recommendation

- **A. Relabel only.** Say what the table is ("RDKit's table, BODR 10-1, equal to Batsanov 2001 Table 9") in the code
  comments, the Geometry limitation line and the stored provenance. No number changes. This is the minimum, and it does
  not need a decision about values.
- **B. Adopt Bondi's own list** for the surface, volume, projection and steric calculators, as one project-owned table
  with its source recorded, and decide the docking module's hydrogen separately. Areas move by about 0.5% on average,
  buried volumes move toward the published ones, and the label becomes true. It changes stored values, so it needs the
  project's method-version bump and the legacy-result handling that `geometry-v2` and `surface-v2` already use.
- **C. Adopt the CRC set (hydrogen 1.10).** Matches the docking module and the Handbook; lowers areas 3 to 7%. Nothing
  here argues for it except matching the Handbook.

**Recommendation: A in any case, and B for the steric calculator at least**, because its stated convention is Bondi's and
the evidence favours it; B for the surface calculators too if one definition across them is wanted. Do not take C on
the grounds of Marvin parity: that cannot be established. This is Alex's decision, because B changes reported values.

## Not verified

- BODR's real origin. The identification with Batsanov rests on exact equality across 65 elements, not on any statement
  by RDKit or BODR.
- The Open Babel header and the ChemAxon forum reply were seen through search summaries only.
- Mantina et al. 2009 has not been read, and Batsanov was read from a public copy, not a supplied one.
- The published buried volumes come from crystal geometries; the application's from free ligands.

## Reproduce

The comparison script is `benchmarks/vdw_radii/radii_study.py` (run it with `uv run python benchmarks/vdw_radii/radii_study.py`
from the repository root); `tests/test_vdw_radii_provenance.py` holds the table equality and the statements above that
could silently stop being true.
