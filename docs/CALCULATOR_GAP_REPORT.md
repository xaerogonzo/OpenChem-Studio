# Calculator gap report

**What this is.** Stage 5 of the calculator-organisation plan: which calculators OpenChem Studio does
not have that a user of a Marvin-like workstation would reasonably look for, with what already
covers part of each, what a correct version would need, and an order to build them in. **It is
research only.** No registry entry, calculator, source or maturity classification was added or
changed to write it.

Written 2026-10-10. Every "OpenChem has / lacks" statement was checked against the generated
`docs/CALCULATOR_REFERENCE.md` (80 entries) and, where the reference was not enough, the source
named in the row. Statements about ChemAxon come only from pages and search results read that
day, and say so.

## How far Marvin parity already goes

ChemAxon's plugin catalogue could not be read as one list: its overview page redirects to a 404
and its introduction page names no plugin. What search results and individual pages confirmed
exists in Marvin, and has an OpenChem counterpart:

| Marvin plugin (confirmed to exist) | OpenChem |
|---|---|
| pKa, major microspecies, microspecies distribution | `pKa`, `Major Microspecies`, `Microspecies Distribution` |
| isoelectric point | `Isoelectric Point` |
| logP, logD | `LogP Contribution`, `LogD (pH-dependent)` |
| topological analysis | `Topology Analysis`, `Ring Systems`, `Stereocentres` |
| geometrical descriptors | `Geometry`, `Molecular Surface Area (3D)` (options and method versions, 2026-10-10) |
| polarizability, dipole moment, charge | `Polarizability (molecular)`, `Dipole Moment`, `Partial Charge (3D)`, `Partial Charge (pH-dependent)` |
| conformer, tautomer generation, stereoisomer generation, stereo analysis | the conformer search, `Tautomers`, `Stereoisomers`, `Stereo Descriptors` |
| solubility, HLB, NMR, hERG, BBB score, CNS MPO | `Solubility`, `HLB (Griffin)`, `NMR Shifts (experimental)`, `ADMET (hERG, CYP, Ames, ADME)`, `BBB Score Descriptors`, `CNS MPO Score` |

Not confirmed either way, so not claimed: a plugin list beyond these, and whether any Marvin
calculator outside it is missing here. The candidates below therefore come from what the
application's own output leaves out, not from a Marvin checklist.

**Already present, and so NOT gaps** (each was a candidate before it was checked): Rule of Three
(an always-on descriptor), the Pfizer 3/75 and GSK 4/400 rules, Lipinski, Veber, Ghose, Egan, QED,
synthetic accessibility, NP-likeness, PAINS and Brenk (alert catalogs), per-ring aromaticity
(HOMA and Bird), and per-ionisable-centre pKa (`pKa` returns one line per centre, with its atom).

## The candidates

Effort is relative and says what it is made of. "Reference needed" names what must be read and
checked BEFORE any code, following the project's rule that a formula or threshold is verified
against a primary source; **no citation below was fetched**, and authors and years are as recalled,
to be confirmed when a candidate is approved.

### 1. Torsion table (rotatable bonds with their dihedral angles)

**BUILT 2026-10-10** as `Torsion Table` (see CHANGELOG). The bonds are held to the count by a test over 85 structures in two forms. What follows is the analysis it was built from.

- **Gap:** `Rotatable Bonds` is a count. Nothing lists WHICH bonds, or the dihedral at each in the
  conformer on screen.
- **Existing coverage:** an interactive measurement (`services/measurement_service.py`) gives ONE
  dihedral between four atoms a person picks; `geometry_analysis.dihedral_angle` is a function no
  calculator calls. No calculator lists the torsions. The conformer pool is stored per molecule.
- **Reference needed:** none for the angle (a definition). One decision: which bonds count as
  rotatable. The count uses RDKit's `Lipinski.NumRotatableBonds`, so the table must list exactly
  those bonds or the two will disagree on the same screen.
- **Effort:** small. Existing helper, existing report types; the work is choosing four atoms per
  bond deterministically and handling terminal groups.
- **Depends on:** a conformer. **Risk:** low; the number is geometry, not a model.

### 2. Hydrogen-bond site table

**BUILT 2026-10-10** as `Hydrogen-Bond Sites`, classified LIMITED. What follows is the analysis it was built from; its acceptor definition needed one change from RDKit's module-level pattern (see the CHANGELOG).

- **Gap:** `H-Bond Donors/Acceptors vs pH` is a count curve and `Interaction Analysis` finds
  intramolecular contacts in a conformer. Nothing says WHICH atoms are donors or acceptors, nor
  which change with pH.
- **Existing coverage:** the counts, and Dimorphite-DL's dominant form at each pH.
- **Reference needed:** the definition of a donor and an acceptor. The counts are RDKit's
  `Lipinski.NumHDonors` and `NumHAcceptors`, so the table should be built from the same definition
  (or the difference stated); Marvin's own per-atom values were not read.
- **Effort:** medium. Per-atom, pH-dependent, and the atoms must be mapped back to the drawing
  through the microspecies (`protonation_geometry` already does that for 3D).
- **Depends on:** nothing new. **Risk:** medium: two definitions in use already would become three
  unless the table is built from the same one as the count.

### 3. Ionisable-site summary

**BUILT 2026-10-10** as `Ionisable Sites`, classified LIMITED. What follows is the analysis it was built from; building it found the pKa line's zero-based atom label, now fixed.

- **Gap:** presentation, not computation. `pKa` returns one line per centre; there is no table of
  centre, acid or base, pKa, and the fraction ionised at a chosen pH.
- **Existing coverage:** the pKa values and their atom indices, `Microspecies Distribution`.
- **Reference needed:** none beyond what `pKa` already cites.
- **Effort:** small. **Depends on:** pkasolver (the same "needs setup" refusal as `pKa`).
- **Risk:** low, provided it reads the same payload `pKa` does and never recomputes.

### 4. Conformer-ensemble (Boltzmann-averaged) properties

- **Gap:** every calculator runs on ONE conformer (the lowest MMFF94 one retained). No property is
  averaged over the stored conformers, so a dipole, surface area or radius for a flexible molecule
  is the lowest conformer's, which is a claim the result does not make.
- **Existing coverage:** the `ENSEMBLE` calculation input already exists
  (`chem/calculation_input.py`) and is used by the Quantum Chemistry panel; `chem/boltzmann.py` has the weights; conformers carry energies. **No registry
  calculator uses `ENSEMBLE`.** The ROADMAP records Boltzmann-averaged SCF energy as shipped for
  QC runs only.
- **Reference needed:** which weights (MMFF94 energies are not free energies, and the existing
  conformer search stops on a sampling plateau, not on a converged ensemble); the standard-state
  and temperature to state. The project's own finding that a conformer search result is "part of
  the question, not the setup" applies directly.
- **Effort:** medium to large, because the design question comes first: which calculators may be
  averaged (a per-atom charge can; an IUPAC name cannot), and how a result says "averaged over N
  conformers at T K with these energies".
- **Risk:** high if done carelessly: an average over a plateau-stopped, force-field-ranked set looks
  authoritative and is neither. The result must carry the count, the energy spread and the
  weights' basis.

### 5. Ring planarity and puckering

- **Gap:** `PBF` is one plane-of-best-fit distance for the whole molecule. Aromaticity is per ring
  but is a different question. Nothing reports how flat or puckered each ring is.
- **Existing coverage:** ring perception (`Ring Systems`), per-ring HOMA and Bird.
- **Reference needed:** the Cremer-Pople puckering coordinates (Cremer and Pople, 1975, as
  recalled) are a closed-form definition with a known value for an ideal chair that gives an
  analytic test. **"Ring strain" as an energy is deliberately not proposed**: it is not a property
  of a structure alone but of a reference scheme (group increments or homodesmotic reactions), so a
  number would be only as good as that scheme and nothing here supplies one.
- **Effort:** medium. New mathematics, but it has exact checks.
- **Depends on:** a conformer. **Risk:** low for puckering, high for strain, hence the split.

### 6. Consensus aqueous solubility

- **Gap:** `Solubility` reports one model's logS at a time (ESOL or the AqSolDB-trained one, by
  choice). A user comparing two predictions has to run it twice.
- **Existing coverage:** both models, and a benchmark with a recorded error
  (`benchmarks/solubility/`, MAE about 0.74 to 0.9 log units on the two held-out sets, base bias
  -0.4 to -0.6).
- **Reference needed:** evidence that agreement of THESE two models says anything. **The project has
  already recorded that they are not independent**: AqSolDB contains Delaney's ESOL set, which the
  anti-leak rule was written for. A consensus of two models trained on overlapping data
  overstates confidence.
- **Effort:** medium, almost all of it the benchmark that would show whether a spread between the
  models predicts the error. **Risk:** high; a spread that predicts nothing would be worse than
  none. Not recommended before the benchmark shows it does.

### 7. Lead-likeness

- **Gap:** Rule of Three (fragment-likeness) and the drug-likeness filters exist; a lead-likeness
  filter does not.
- **Reference needed:** the thresholds. Teague et al. (1999) and Oprea (2001), as recalled, give
  different ones; which to ship, and whether to ship both labelled separately, is the whole
  decision.
- **Effort:** small once decided; it is one more always-on descriptor.
- **Risk:** low; its limitation is that thresholds are conventions, which the existing filters'
  help text already says.

### 8. More structural-alert catalogs

- **Gap:** five catalogs are offered (PAINS, Brenk, fragment counts, hERG risk factors,
  mutagenicity). RDKit ships others through its filter catalog interface.
- **Reference needed: licences, which were not checked.** RDKit's filter catalog offers NIH, ZINC and
  the ChEMBL-derived BMS, Dundee, Glaxo, Inpharmatica, LINT, MLSMR and SureChEMBL sets (listed from
  the installed RDKit). Their origins and terms must be read before any are offered, because
  redistributing patterns is not the same as calling a library.
- **Effort:** small to medium, and the licence reading is most of it. **Risk:** legal rather than
  scientific.

## Recommended order

1. **Torsion table**: smallest, no model risk, fills a visible hole.
2. **Ionisable-site summary**: small, and only reads what `pKa` already has.
3. **Hydrogen-bond site table**: parity with what a Marvin user expects; settle the definition
   first so it agrees with the count.
4. **Lead-likeness**: small once the thresholds are chosen.
5. **Ring puckering**: medium, with closed-form checks.
6. **Conformer-ensemble properties**: the most useful and the most dangerous. Needs a design
   record before code.
7. **Extra alert catalogs**: after the licences are read.
8. **Consensus logS**: only if a benchmark first shows the models' disagreement predicts error.

## Smaller gaps seen while building the last stages

- **Per-atom surface area takes a probe but not a pH.** A pH changes the atoms, so the per-atom
  result's indices would no longer match the drawing. Left out on purpose; recorded here so it is
  not mistaken for an oversight.
- **ChemAxon's per-atom steric hindrance is not built**, because no formula is published
  (`docs/GEOMETRY_MARVIN_CHECKLIST.md`).
- **Batch inventory B09**: a section heading has no "n / total" readout or partial-tick state
  (`docs/PANEL_FEATURE_INVENTORY.md`).

## Future-feature backlog (not calculators; recorded from the plan, priority order)

1. **Calculator information cards**: what it measures, unit, inputs, applicability, tools needed,
   maturity, caveat, assembled from `calculator_help` and the support metadata, with no second
   source of text.
2. **"Why unavailable?"** from the existing preflight and refusal results, in Properties and in
   the goal wizard.
3. **A plan preview before a multi-molecule run**, reading the same immutable `ExecutionPlan`.
4. Later: portable analysis recipes; re-run only the failed or skipped cells of a project table; a
   run-details view over the existing result records; search synonyms through a defined metadata
   contract.

## What this report did not do

- It did not read ChemAxon's per-plugin pages for hydrogen-bond donor/acceptor, polarizability,
  refractivity or Hückel, so nothing here claims Marvin matches or exceeds OpenChem on them.
- It did not fetch any paper, so no threshold or definition above is verified.
- It did not rank the candidates by user demand, which nothing in the repository measures.
