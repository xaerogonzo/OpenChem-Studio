# Hypervalent structures that RDKit accepts: design

**Status: design. WP6 (geometry coverage) is done, see its section; the other packages are not.** Follows PRs #597 and #598, which made the application hold, draw in 3D and compute on the
structures RDKit refuses (ClF3, BrF3, ClF5). This is about the other half: hypervalent structures RDKit **accepts**, which have
always taken the ordinary path (SF6, PF5, XeF4, XeF2, SF4, IF5, PCl5, Ar-SF5, iodine(III) reagents).

## 1. What was measured

`benchmarks/hypervalent/defect_scan.py` runs every registry calculator and the always-on providers over three groups and reports
only what is wrong **without an external reference**: a non-finite number, an exception, a stereocentre on a molecule that cannot
have one. Run 2026-11-13, RDKit 2025.09.6.

| Molecule | Group | Calculator defects | Always-on defects |
|---|---|---|---|
| SF6 | star | `topology_analysis`: chiral centre count 1 | none |
| PF5, PCl5, IF5 | star | `topology_analysis` chiral 1; `gasteiger_charge_at_ph` NaN | per-atom Gasteiger NaN |
| XeF4, XeF2 | star | `gasteiger_charge_at_ph` NaN | per-atom Gasteiger NaN |
| SF4 | star | none | none |
| Ph-SF5 | embedded | `topology_analysis` chiral 1 | none |
| PIDA (iodine(III)) | embedded | `gasteiger_charge_at_ph` NaN | per-atom Gasteiger NaN |
| CH3-PF4 | embedded | chiral 1; Gasteiger NaN | per-atom Gasteiger NaN |
| sulfate, DMSO, perchlorate, trimethyl phosphate, ethanol, benzene | control | **none** | **none** |

Three facts follow.

1. **The defects are specific, not class-wide.** Two calculators and one always-on dataset account for every flag. Nothing else
   produced a non-finite number or an exception on any of the 16 molecules.
2. **The Gasteiger NaN is on the ordinary path today and Properties shows it.** It follows the centre's element and coordination
   (P with five bonds, Xe, I(III)), not whether the structure is an inorganic "star": PIDA is an ordinary reagent and has it.
   S(VI) happens to be parameterised, so SF6, SF4 and Ph-SF5 do not.
3. **The chiral-centre count follows five- and six-coordinate centres** (SF6, PF5, Ph-SF5, CH3-PF4), again regardless of group.

Separately, measured on held ClF3 and SF6 in #598 and **not** detectable without a reference: the Dreiding energy of ClF3 (216
kcal/mol, typed as a one-bond halogen with three bonds) and the additive polarizability of SF6 (5.15 against about 6.5 A^3
experimental, 21% low).

## 2. Why not refuse by class

The obvious design, "refuse every calculator except the verified five on any hypervalent structure", is wrong for three reasons.

* **RDKit's acceptance is arbitrary, so a rule hung on it is.** It accepts IF5 and not ClF5, iodine at three bonds and bromine
  not, S(VI) and not Cl(III). The held / not-held line of #597 is a statement about RDKit's valence table, not about chemistry.
* **The same atoms are everyday chemistry.** Sulfonyl, phosphoryl and perchlorate centres, Ar-SF5 (a real medicinal-chemistry
  group) and the iodine(III) reagents are all drawn and computed on today. A class refusal removes results that were fine, and the
  scan shows all six controls clean.
* **The defects are not about the class.** They are a missing parameter (Gasteiger for P, Xe, I(III)), a perception that does not
  expect five or six neighbours (topology), a typer that ignores coordination (Dreiding). Each has a precise fix at its source.

So: **fix defects where they arise, add one generic guard that would have caught the NaN, and keep the verified-list mechanism of
#598 only for structures RDKit refuses.**

## 3. Work packages

Each has an acceptance test written first against the measurement above, and a control that must not move.

**WP1. No non-finite number is ever published.** A guard where results leave the calculators (`DescriptorService`, for registry
results, always-on descriptors and per-atom datasets): any NaN or infinity becomes a refusal `ELEMENT_OUTSIDE_PARAMETER_SET` (an
existing LIMIT) naming the element and, where known, the atoms. Fixes `gasteiger_charge_at_ph`, the always-on Gasteiger dataset and
anything similar not yet found. *Accept:* PF5, XeF4, XeF2, IF5, PCl5, PIDA, CH3-PF4 no longer publish NaN; the six controls'
results are byte-identical; a mutation test (guard removed) fails. *Open:* whether the dataset should drop only the bad atoms or
refuse whole. Recommendation: refuse whole, because a charge set with holes does not sum to the formal charge.

**WP2. Stereocentre perception for 5- and 6-coordinate centres.** `topology_analysis.stereo_counts` counts a stereocentre only
where RDKit's stereo model applies (three or four neighbours, the cases the codebase already treats as tetrahedral or pyramidal),
and says "not assessed" for a higher coordination rather than 1. *Accept:* SF6, PF5, Ph-SF5, CH3-PF4, PCl5, IF5 count 0; CHFClBr
1; a sulfoxide and a sulfoximine unchanged. Check the sibling code paths (`stereo_descriptors`, per-atom `stereocenters`) for the
same count; the always-on `num_stereocenters` was already 0 on SF6.

**WP3. Dreiding typing must respect coordination.** `chem/dreiding` refuses (`UntypedAtomError`, which the report already turns
into a stated reason) an atom whose coordination exceeds its type's (a halogen with more than one bond, a noble gas, a type with a
fixed geometry that the neighbour count contradicts). *Accept:* the Dreiding fact on ClF3 and on Cl, Br, I and Xe centres says it
cannot type them; the facts that already carry numbers for ordinary molecules are unchanged (`tests/test_dreiding*`).

**WP4. Polarizability: decide from the data, not from one molecule.** The CRC Handbook table that `benchmarks/polarizability/`
already parses (`crc_parse.py`, `crc_resolve.py`) contains hypervalent molecules (SF6 and others). Compute the model's error on
every entry with a hypervalent centre. If the error is a clear outlier against the stated 2.1 and 9 per cent, add a caveat (or a
limit) for those centres with the measured figure; if it is not, do nothing. *Accept:* the decision is a table in this document,
and a test holds whatever is shipped to it.

**WP5. Extend the held-structure verified list.** The unverified calculators are each checked against an oracle exactly as in
#598. The likely candidates are few (the Lewis-sites report, formula-driven facts). A calculator is added only with its oracle test.

**WP6. Geometry coverage. DONE 2026-11-13** (BrF5, IF5, ClF5 and IF7 added from the papers, held in the maintainer's library and
recorded in `docs/sources.toml` and `docs/LITERATURE_LOG.md`; the table below is what was found before reading them). BrF5 (square pyramid; NIST CCCBDB: apical 1.689, basal 1.774 A, apical-basal 84.8, basal-basal 89.53
degrees, Gurvich compilation) and IF7 (pentagonal bipyramid; Adams, Thompson and Bartell 1970: axial 1.786, equatorial 1.858 A)
need two templates. IF5 (Robiette, Bradley and Brier 1971) and ClF5 (Bodenseh, Huttner and Nowicki 1976) need the original papers:
CCCBDB has no IF5 geometry, and its ClF5 entry lists D3h and one length, which cannot be a square pyramid. XeF6 is a distorted
mean structure (Bartell and Gavin 1968: lengths spread over about 0.08 A around 1.890) and stays excluded. Oxyfluorides (XeOF4,
SOF4) and ions need a source search first; the CCCBDB lookup by CAS number did not serve them.

What the papers showed, and what shipped. Robiette 1971 gives BrF5 (apical 1.689, basal 1.774 A, 84.8 degrees) and IF5 (1.844, 1.869 A,
81.9 degrees; the difference is poorly determined). Adams 1970 gives IF7 (axial 1.786, equatorial 1.858 A, ideal D5h placed; the 7.5 degree puckering
is an average and is not). **Bodenseh 1976 does not determine ClF5's lengths**: only the angle (86.5 +/- 1.0 degrees), with both lengths about 1.65 A
and "a complete structure determination is not possible", so the shipped row uses 1.65 for both and says so; NIST's single 1.650 A is the same
assumption. A real ORCA B3LYP/def2-SVP optimisation from that start gives apical 1.664, basal 1.709 A, 85.6 degrees. ORCA also keeps BrF5 (84.9 to
85.0 degrees against 84.8), IF5 and IF7 in shape. Still unsupported: IF3 (no structure found), XeF6 (not one geometry), the oxyfluorides and ions.

**Second pass (2026-11-13), from five more papers.** Added AsF5 (Clippard and Bartell 1970: rg axial 1.711, equatorial 1.656 A), SeF4
(Bowater, Brown and Burden 1968: 1.7713 and 1.6821 A, 169.20 and 100.55 degrees), PCl5 (NIST CCCBDB, Gurvich: 2.124 and 2.020 A, primary paper not held)
and, as the first CHARGED cases, ClF4- (Scheibe et al. 2020: K salt 1.7982 A, square planar, a crystal) and XeF5- (Christe et al. 1991: mean
2.012 A, planar regular pentagon, a crystal). Charged centres needed three changes: the builder counts lone pairs from the centre's outer
shell less its formal charge and keys a reference by charge; the acceptance test became "RDKit actually refuses this atom and the table allows it"
(the old comparison with RDKit's valence list never flagged XeF5-, which sits inside xenon's list, so a drawn XeF5- was rejected); and arsenic
and selenium joined `hypervalent_rules.json` because a paper was read for each. A real ORCA optimisation from each start keeps the shape: SeF4 100.0
and 170.2 degrees, both anions D4h and D5h. **XeOF4** (Martins and Wilson 1964: Xe-O 1.70, Xe-F 1.95 A, 91 degrees, preliminary and uncertain to 0.05 A) is
read and recorded and not shipped, because it has two kinds of ligand and a Xe=O bond, which the builder does not handle; so are SF5Cl and SOF4. That
is the next structural step (a per-ligand-class reference and oxo ligands), not a data one.

**Third pass (2026-11-13), from the ChatGPT-suggested batch.** Added SeF6 (Bartell and Jin 1984, rg 1.685 A) and TeCl4 (Kovacs, Martinsen and Konings 1997, ra 243.0 and 229.8 pm, 175.9 and 103.0 degrees; tellurium joins `hypervalent_rules.json`) and moved PCl5 to its primary paper (Adams and Bartell 1971). The five mixed-ligand or oxo cases (ClF3O, XeOF4, XeO2F2, SOF4, SF5Cl) now all have measured values (see `docs/LITERATURE_LOG.md`), and the builder then gained per-slot ligand kinds, oxo ligands (a double bond to oxygen) and three layouts (Cs and C2v bipyramids, C4v octahedron): ClF3O, XeOF4, XeO2F2, SOF4 and SF5Cl are built. An oxo ligand with no recorded geometry (sulfate, perchlorate, XeO3, XeO4) is still left to the ordinary path. IF4- is square planar on spectral evidence but has no lengths; IF3 has only a crystal with bridging contacts.

**WP7. The regulatory screen on a held structure stays refused**, with a test that a held structure never yields "no matches" (it
did in the #598 audit, a silent false negative for a screen). Not a change; a guard on the decision of #598.

## 4. Order and non-goals

WP1 first (it is the visible NaN and the cheapest), then WP2 and WP3 (small, each with its control), WP4 (data work), then WP6
(new templates) and WP5. One PR per package; the scan is re-run and its table updated in each.

**Non-goals:** no refusal of any calculator on an RDKit-accepted structure because it is "hypervalent"; no change to sulfones,
sulfates, phosphates or perchlorates; no estimated bond lengths; no new calculators.

## 5. Questions for the owner

1. Ph-SF5 and iodine(III) reagents are in scope of WP1 and WP2 because they showed the same defects; confirm they should be fixed
   rather than excluded.
2. For WP1, refuse a charge dataset whole or drop the unparameterised atoms (recommended: whole).
3. Do you hold Robiette 1971 and Bodenseh 1976 (WP6)?
