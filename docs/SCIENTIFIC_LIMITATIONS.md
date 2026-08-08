# Scientific limitations

What each prediction can and cannot tell you.

This page exists because a chemistry application that reports a number to two
decimal places invites more trust than the number has earned. Nothing here is
a disclaimer in the legal sense — each entry is a specific, known property of
a specific method, and most of them are already documented in the module that
implements it. This is the consolidated version.

The general rule: **a value with a confidence label is more useful than a
value without one**, and the app labels predictions `empirical` or
`ab_initio` wherever it has a basis to state which.

---

<!-- help:limits-nmr -->
## NMR shift prediction

Three predictors, three different failure modes.

**The HOSE-code lookup is empirical and environment-matched.** It answers
"what shift do atoms in environments like this one usually have", not "what
shift does this atom have". It is excellent where the environment is well
represented (measured 1.12 ppm MAE) and poor where it is not (10.00 ppm).
That is why every atom carries its band, and why the band is not cosmetic —
it is the number the hybrid selects on.

It is also **solvent-blind**. The underlying measurements were made in
various solvents and are pooled.

**The ORCA path is ab initio but conformer-dependent.** A shift is computed
for the geometry you give it. For a flexible molecule, one MMFF conformer is
a poor model of what a real sample is doing. This was tested directly on
quinine: Boltzmann averaging over conformers moved MAE only 4.30 → 4.27 ppm,
so conformer choice is *not* a general fix — but for individual atoms around
a flexible hinge it matters a great deal.

Computed shieldings are also systematically stretched relative to experiment
by an amount depending on functional, basis, geometry and solvent, which is
why calibration against reference compounds exists rather than a simple TMS
subtraction.

**The hybrid selects; it does not average.** For each atom it picks the
source with the lower expected error and records which one won and by how
much the two disagreed. It cannot make a good prediction out of two bad
ones, and a large `disagreement_ppm` is a flag to go and look, not a
resolved conflict.

**Multiplicities are first-order.** The n+1 rule over adjacent
non-equivalent protons. Real spectra show second-order patterns the rule
cannot produce, and where coupling is to more than one distinct group the
app reports `m` rather than inventing a letter.

**Diastereotopic protons are split structurally, not numerically.** The app
can determine that two geminal protons are inequivalent; it cannot supply
the two different shifts, because the predictor behind it does not
distinguish them. Both signals appear at the same shift. The inequivalence
is a fact; the two numbers would be an invention.

---

## Naming

**The deterministic engine is exact where it succeeds and silent where it
does not.** Every generated name is parsed back with OPSIN before display,
so a name that reaches you round-tripped. That is a strong check, and it is
not a completeness guarantee: structures the engine cannot name produce no
name rather than a wrong one.

**Tautomers are the known ambiguity.** Canonical SMILES does not normalise
tautomers; InChI does. A name can be correct while its round-trip lands on a
different tautomer of the same compound — metformin is the worked example.
The benchmark classes these separately and counts them as successes only
when both a canonical-tautomer match and an InChIKey match agree.

**PubChem lookups are exact but only for known compounds**, and require
network. They are never silently blended with a generated name: every name
carries its source and whether it is `exact`, `derived` or `parsed`.

---

<!-- help:limits-docking -->
## Docking

**Vina's score is not a binding free energy.** It is an empirical scoring
function tuned to rank poses. Treat the numbers as an ordering, not as
ΔG. Comparing scores between different receptors is especially unsafe.

**The receptor is rigid.** No induced fit, no side-chain flexibility. A
ligand that would fit a real, breathing protein can be rejected by a frozen
one.

**Poses are not affinities**, and a redocking benchmark cannot show
otherwise. The measured 0.18–0.73 Å centroid displacements say the search
finds the right *pocket* for ligands that came out of that pocket. They say
nothing about a novel ligand's real affinity.

**Receptor preparation changes results, and it is not automatic.** Which
chains you keep, whether symmetry-generated copies are present, which
alternate locations are selected, and whether untyped atoms were dropped all
change what Vina actually sees. This was the source of a whole class of bug
here — the receptor handed to Vina and the receptor read back by the
interaction analysis have to be the *same* receptor — so the app now derives
both from shared predicates and shows you the structure's contents before
docking. Look at that dialog; the defaults are not always what you want.

**No solvent, no explicit waters, no metals modelled as such.**

---

<!-- help:limits-force-fields -->
## Force field energies

**A force field energy has no absolute meaning.** It is the strain of one
geometry measured against that force field's own idea of an unstrained one,
so the only valid comparison is the *same* force field on conformers of the
*same* molecule. The Geometry panel reports three — MMFF94, UFF and
Dreiding — and they are on **three different scales**. Comparing across them,
or across two different molecules, is meaningless in all three cases. Each
number carries that warning in its own tooltip.

**Dreiding is implemented here rather than imported**, because no Python
chemistry library has it: neither RDKit nor OpenBabel. It follows the
original paper (Mayo, Olafson & Goddard 1990) and reproduces **all eight of
the rotational barriers that paper computes with Dreiding**, worst deviation
0.008 kcal/mol. That is a stronger check than agreement with experiment
would be: those are the force field's own published values, so reproducing
them tests this implementation rather than the model.

**It omits charges and the explicit hydrogen-bond term.** That is the
configuration the paper reports its own results in, and it is what makes
those barriers reproducible — but it means a polar molecule's Dreiding
energy is missing an electrostatic contribution. Treat it as a
conformational strain number, not an interaction energy.

Dreiding covers 37 atom types and **refuses outside them** rather than
guessing a radius. A molecule containing an element it does not cover simply
gets no Dreiding row.

---

<!-- help:limits-esp -->
## Electrostatic potential surfaces

**Computed from point charges.** Each atom is a single charge at the nuclear
position. That representation has no lone-pair directionality and no sigma
holes, so the two features a chemist most often *wants* an ESP map for —
where a lone pair points, and the positive cap on a halogen — are exactly
what it cannot show.

It is a good picture of gross charge distribution and a bad picture of
directional non-covalent interaction. For the latter you need a real
wavefunction.

**The app has one, and shows both side by side.** The Quantum Chemistry
panel's Surfaces tab plots the ab initio potential with `orca_plot` from
the wavefunction a completed ORCA job leaves behind, beside the
point-charge map, each labelled with its method. They are shown together
rather than one replacing the other because they fail differently — on
bromobenzene the ab initio potential changes sign around the halogen and
the point-charge one cannot, since a single charge on a single atom has
no angular dependence at all. Everything above still applies to the
left-hand pane.

The charges are recomputed on the 3D conformer being displayed rather than
reused from a flat structure, and an incomplete charge map is refused rather
than defaulted to zero — a missing charge silently treated as zero gives a
neutral molecule a net charge it does not have.

---

## Molecular dynamics

**Vacuum molecular dynamics, and nothing more.** No thermostat, no barostat,
no constraints, no periodic boundaries, no implicit or explicit solvent.
Velocity-Verlet over MMFF94 or UFF gradients.

This is useful for looking at conformational motion and for animation. It is
not a simulation you should draw thermodynamic conclusions from.

The dynamics integrator uses **MMFF94 or UFF**, not Dreiding.

Dreiding *is* available for single-point energies — see below — but it is
not wired into the integrator, so a trajectory is on one of the other two.

---

<!-- help:limits-admet -->
## ADMET

**Predictions with real uncertainty, not measurements.** Every ADMET
calculator is labelled `empirical`, and the reported performance figures are
the model's own published test-set numbers, not something measured here.

**The size confound is real and was measured.** For hERG, the model's
apparent separation correlated with molecular size at **r = +0.98**. A
size-matched panel built specifically to break that still showed r = +0.82
against size. Treat a "high risk" flag on a large lipophilic molecule as
largely a restatement that the molecule is large and lipophilic.

This is why the **rule-based hERG risk-factor checklist ships alongside the
model and is labelled "not a prediction"**. It lists structural correlates —
high lipophilicity, a basic amine, aromatic rings — which is what the
evidence actually supports.

**BBB permeation and oral bioavailability are labelled approximations**
inspired by published heuristics, not reproductions of the Clark regression
or the Abbott bioavailability score. Both of those are more nuanced in their
primary sources than a threshold check.

---

<!-- help:limits-pka -->
## pKa and logD

**No solvent model.** Aqueous, room temperature, implicitly. There is no
temperature or ionic-strength parameter because the underlying model exposes
none.

**Reaction-centre indices do not map onto our atom numbering.** This was
confirmed directly: ibuprofen reports a centre on a carbon while the acidic
proton is on a carboxyl oxygen. So pKa values are reported as a **list**
rather than painted onto atoms — keying a 2D or 3D highlight off those
indices would have confidently coloured the wrong atoms.

**logD has two modes and says which one it used.** With a configured pKa
sidecar it is real Henderson–Hasselbalch. Without one it is the Crippen logP
of the dominant microspecies at that pH — a genuinely pH-dependent number,
but not the same quantity, and labelled as such rather than presented as
equivalent.

---

<!-- help:limits-structure -->
## Structure handling

**The biological assembly is read from the deposit, not inferred.** Where a
file records one, the app can build it. Where it does not, what you get is
the asymmetric unit — which for many entries is not the biologically
meaningful molecule.

**Symmetry-generated copies are detected and can be dropped**, because Open
Babel will expand a unit cell on some space groups whether or not you wanted
that, and a duplicated receptor silently doubles your binding site.

**No missing-residue repair.** This was spiked with PDBFixer and rejected:
the rebuilt geometry is not trustworthy near a binding site, which is
exactly where docking would rely on it. A gap in a chain stays a gap, and
the contents dialog shows you it is there.

---

<!-- help:limits-conformers -->
## Conformer generation

**These are MMFF94 (or UFF) geometries, not QM ones.** They are good enough
to start a calculation from and to compare shapes with; they are not the
answer to "what is this molecule's geometry". An ORCA optimisation started
from one will move it, sometimes a lot.

**"Distinct" is a 0.5 Å RMSD judgement, not a physical fact.** Two
embeddings are treated as the same conformer when their heavy atoms and
polar hydrogens fall within that threshold, compared symmetry-aware. The
number was checked rather than chosen: across 40 embeddings of butane every
pair came out either below 0.5 Å or at 0.66 Å — two clean clusters, anti
and gauche, with nothing between them — so 0.5 separates them with margin
while 1.0 merges them and loses a real conformer.

The threshold cuts both ways. It is coarse enough to hide conformers that
differ by less than it, and any two shapes closer than 0.5 Å will be
reported as one.

**Carbon-bound hydrogens are ignored in that comparison and polar ones are
not.** A rotated methyl is not a different conformer; an O–H orientation
is, because it changes hydrogen bonding and the energy of anything computed
afterwards. Heavy-atom-only comparison was tried first and was measurably
worse: ethanol's heavy atoms are C–C–O, three points and therefore rigid by
construction, so it reported one conformer for a molecule whose O–H
rotamers are exactly what a conformer search is for.

**The search is random, not exhaustive.** ETKDG embeds from random starting
points, so the set you get is a sample. A molecule can have a conformer the
search did not find, and asking for more embeddings is the only lever —
there is no guarantee attached to any count.

**Energies rank; they do not quantify populations.** Conformers are sorted
by force-field energy so conformer 1 is the lowest found, but MMFF energies
are not free energies and the differences between them do not convert into
a Boltzmann population you should trust for anything quantitative.

---

<!-- help:limits-led -->
## Interaction energy decomposition (LED)

**Only the total energy is an observable; the decomposition is, to some
extent, arbitrary.** That is ORCA's own wording, and it is carried on every
result rather than paraphrased here. There is no unique way to divide an
interaction into "electrostatics" and "charge transfer" — the split depends
on the scheme. Compare terms *between* similar systems, where the scheme is
held constant; do not read a single term in isolation as a measured
quantity.

**No counterpoise correction.** Each fragment is computed in its own basis,
so basis-set superposition error inflates the binding. Measured on BH₃·CO in
cc-pVDZ: −36.6 kcal/mol against an experimental bond enthalpy near −25. The
error is in a known direction (too negative) but is not corrected for.

**A vertical interaction energy, not a bond dissociation energy.** The
fragments are held at the geometry they have in the complex and never
relaxed, so the number does not include the energy either partner recovers
by relaxing once separated.

**The decomposition is complete only to within a stated residual.** The
terms are reported alongside how far they miss the total — a few hundredths
of a kcal/mol in the reference case, arising from how DLPNO splits the
triples correction. If that residual is large the result says so.

**Not usable on anything drug-sized.** DLPNO-CCSD(T) cost rises steeply —
roughly with the cube of the basis-set size. Measured: 15 seconds for a
water dimer, 21 minutes for a pentane dimer, 44 minutes and 6 GB of scratch
for a benzene dimer. The estimate shown before launching is fitted on six
measured jobs and is a guide to the order of the cost, not a prediction; it
is accurate to about a factor of 1.6, against run-to-run variation on the
same job of about 1.2.

**Aromatic rings cost about three times what their size suggests**, and the
estimate accounts for it. This is not a size effect: a methanol dimer and a
benzene molecule have almost the same number of correlated electrons (28 and
30), and benzene takes twelve times as long. Delocalised π systems defeat
the locality approximations DLPNO depends on. Conjugated and aromatic
partners are therefore the expensive case, which is unfortunate, because
they are also the interesting one for π-stacking.

**The result is only as good as the geometry you give it.** Two fragments
placed on top of each other produce a large, confident and meaningless
number; the app refuses those rather than reporting them, but it cannot
tell a merely poor geometry from a good one.

---

<!-- help:limits-regulatory -->
## Regulatory screening

**This is not legal advice, and it is not a compliance determination.** The
feature reports which of the loaded rulesets matched a structure. That is a
statement about the rulesets, not about the law, and the wording is
deliberate throughout: the result says *"no matches in the N rulesets
consulted"* and never "not controlled" or "compliant".

**Coverage is partial by construction.** What ships is what could be
verified against primary text and lawfully redistributed. Several obvious
sources cannot be shipped in a GPL application at all — CAS Registry
Numbers as a database, DrugBank's non-commercial data, ACGIH TLVs, the IATA
DGR — so their domains are either absent or represented only by a public
equivalent. Registered-but-empty domains appear in the coverage report
rather than being hidden, because an absent domain is invisible and an
empty one is honest.

**A structural family match is a reading of prose.** Regulations contain
language that structure alone cannot carry — *"except…"*, *"other than…"*,
*"when intended for…"*, *"and its salts, isomers, and salts of isomers"*.
Every one of those became an implementation decision. That is why each rule
keeps the verbatim legal quote beside the pattern and carries a separate
confidence, and why `requires_review` exists as an outcome rather than
being resolved silently.

**An `analogue` match is a similarity number, not a probability.** It is
reported as the fingerprint similarity it is, against a named listed
substance. It is not a claim that anything is controlled, and it does not
convert into one.

**Salt and isomer handling is a stated policy.** Matching strips salts and
compares on a normalised parent, with stereo-insensitive hits reported
separately from exact ones. Getting this wrong in either direction is a
real error: too strict misses a hydrochloride salt, too loose flags an
unrelated stereoisomer.

**Metabolites are not predicted.** Some parent compounds are unscheduled
while their metabolites are not. The engine carries the match type so a
curated list could populate it, and predicts nothing.

---

## Substance classification and coordination

`chem/substance.py` says what kind of thing a structure represents. It is
graph perception, and the honest boundaries are these.

**It describes the structure as drawn, and never alters it.** An ionic
association is reported without adding a bond; a dative reading of a
metal-ligand bond is offered as a quick fix rather than applied.

**A geometry is never inferred from a count.** Six things attached to a
metal does not make something octahedral — that is a claim about angles,
and a flat drawing has none. A coordination environment perceived from a
2D structure reports its ligands, their hapticity and both counts, and
says "not determined" for geometry. The same rule the bond report already
applies to 2D bond lengths.

**Two counts, and neither is "the coordination number".** Ferrocene's
ligand coordination is 2 and its donor-atom count is 10. A single figure
of 10 invites the reader to supply the wrong convention, so the two are
reported separately and never merged.

**A disconnected structure with charged components may be refused.**
`[Na+].[Cl-]` is a confident 1:1 salt. `[Na+].[Cl-].[K+].[Br-]` is not
classified at all — it could be NaCl + KBr, or NaBr + KCl, or a mixture of
four ions, and nothing in the graph decides. The refusal carries that
reason, which is the useful half of it.

**"Ambiguous" and "mixture" are different statements.** A disconnected
graph is not one substance merely because its charges happen to cancel.

### Oxidation states of sandwich complexes

A metallocene's metal is now assigned, from the ionic ligand convention:
each eta-5 cyclopentadienide counts as -1 and the metal takes whatever
balances the total charge. Ferrocene gives Fe(+2), ferrocenium Fe(+3),
cobaltocene Co(+2).

**The ring carbons are deliberately left unassigned.** The negative charge
is spread over all five, and a per-atom state there depends on which atom
the charge happened to be typed on — the delocalisation limitation this
file and `chem/oxidation_states.py` already record.

**Only the ionic DRAWING is recognised.** The vendored perception was
measured against five variants with the metal bonded into its rings
(single, alternating and aromatic ring bonds; single and dative metal-carbon
bonds) and classified none of them. A sandwich drawn that way still hits
the metal-carbon refusal, and that refusal now names the drawing that can
be assigned.

Metal carbonyls remain refused. Cr(CO)6 comes out at Cr(+6) where the
answer is 0, and nothing here can see the back-donation that makes it so.

### Bond polarity

Reported as an **electronegativity difference (Δχ)** and a direction, never
as a percentage of ionic character. The Pauling transform
`1 − exp(−(Δχ)²/4)` would turn Δχ = 0.89 into "18.3% ionic", and that is two
decimal places on a quantity nobody measured. The formula is named in the
fact's limitations so a reader knows exactly what is withheld.

Δχ is a difference of **tabulated atomic values**, not a measurement on the
bond. The real charge separation depends on everything else attached.

The wording — "essentially non-polar", "polar covalent", "usually described
as ionic" — is a convention with its thresholds stated (0.4 and 1.7).
Textbooks put the ionic boundary at 1.7 or at 2.0, so a bond near it is
described differently by different sources.

### Lattice energy

A **Kapustinskii estimate from Shannon six-coordinate ionic radii**, and it
ships because it cleared a gate set before it was built.

Validated against 36 experimental Born–Haber values (Kaya, Robles-Navarro,
Mejía, Gómez & Cardenas, *J. Phys. Chem. A* 2022, **126**, 4507, Table 3):

| set | deviation |
| --- | --- |
| 20 alkali halides (1:1) | −4% to −7%, every one LOW |
| 7 oxides and sulfides (2:2) | within 2% |
| all 36 | worst 7.3%, mean −3.7% |

**The error is systematic, not random**, which is what makes a 5% estimate
usable — a reader who knows the answer runs low can correct for it. The
reported fact states which regime the salt is in rather than giving one
averaged caveat.

It runs low because it omits the dispersion and zero-point terms, and it
assumes fully ionic bonding: any covalent character makes it worse in a
direction it cannot report. It knows nothing about the actual crystal
structure — Kapustinskii works without one precisely because the Madelung
constant per ion barely varies between the common structure types.

**It refuses rather than approximating.** A salt of polyatomic ions
(sodium acetate, ammonium nitrate) needs *thermochemical* radii, which are
a different measurement from a different source, so no estimate is given at
all. Ions outside the shipped table are refused by name.

The implementation is also checked against Born–Landé built on a Madelung
constant this suite computes by Evjen lattice summation (1.74757 against
the accepted 1.74756) — two independent routes agreeing to 0.6%, which
catches a wrong prefactor or a unit slip that an experimental comparison
could hide.

## Crystal structures

A periodic solid is **not a molecule**, and `domain/crystal.py` does not
inherit from the molecule model in either direction. Most molecular
calculators mean nothing for one — a molecular weight, a logP, a
rotatable-bond count — so the crystal report names them as inapplicable
rather than leaving a reader to wonder why the Properties panel is empty.
That list is read from the live calculator registry, so a calculator added
later is covered without anyone remembering to update it.

**What is computed, and how it was checked.** The cell volume uses the
general triclinic expression, which for an orthogonal cell reduces to
`abc` — so a cubic structure cannot tell the real formula from a bare
multiplication. Three published structures spanning three crystal systems
were used instead:

| structure | source | cell volume | density |
| --- | --- | --- | --- |
| Halite, Fm-3m | Walker et al. 2004 | 179.339 vs 179.34 Å³ | 2.1645 vs 2.165 |
| Gypsum, I2/a | Cole & Lancucki 1974 | 494.372 vs 494.37 Å³ | 2.3132 vs 2.31 |
| Low quartz, P3₁21 | Baur 2009 | 112.9785 (3 routes) | 2.6493 vs 2.65 |

Independently, `det(M)` — the determinant of the fractional-to-Cartesian
matrix that actually places atoms — equals the closed-form volume exactly
for every cell shape. The two share no code, so a wrong conversion matrix
cannot hide behind a right volume.

**Density is the X-ray density of an ideal cell.** A measured density is
lower wherever the real material has vacancies, porosity or inclusions,
and nothing here can see any of those. Occupancies below 1 are honoured,
so a partly-vacant site lowers it exactly as it does in the material.

**Coordination number is a judgement, and is reported as one.** There is
no measurement saying where a shell ends; the rule used here is the first
jump in sorted neighbour distances larger than 15%. Halite is unambiguous
— six neighbours at 2.820 Å and the next shell 41% further out — and the
report says whether a given case was that clear-cut or not. **The
distances are the measurement; the count is an interpretation of them.**

**The Cartesian convention is fixed and stated**: a along x, b in the xy
plane. Any rotation of that is equally valid crystallography and will not
match these coordinates.

### What the CIF reader does not do

Anisotropic displacement parameters, disorder groups, restraints and
refinement statistics are **recorded in `Crystal.unhandled` rather than
dropped**, because a structure with disorder is still worth showing and
silently ignoring the fields is how a tool starts implying it understood
more than it did.

Standard uncertainty is stripped, not parsed: `5.6393(2)` becomes 5.6393.
Propagating it would only be worth doing everywhere, and a half-propagated
uncertainty is worse than none.

**The reader is exercised against two real depositions**, public domain
from the Crystallography Open Database and committed as fixtures:
`1504676` (a perfluorophenyl-capped polyyne, Kendall et al., *Org. Lett.*
2008, **10**, 2163) and `7717378` (a uranium complex, 120 sites). Both are
**triclinic** — all three angles off 90 — and both carry what a
hand-written file never does: multi-line `;` fields, quoted values with
commas, extra `_atom_site_` columns, anisotropic and geometry loops, tags
containing slashes, and negative fractional coordinates.

Each file states its own `_cell_volume` and `_exptl_crystal_density_diffrn`,
computed by the depositor's software from the depositor's structure, and
both are reproduced to four significant figures — 768.527 against 768.5
and 1.4703 against 1.470; 1955.152 against 1955.15 and 1.5525 against
1.552. That exercises parsing, expansion, wrapping, deduplication,
composition and volume together against numbers this project did not
produce.

What remains untested: **disorder groups and partially occupied sites in a
real file**. Both fixtures are fully ordered, so the occupancy path is
covered only by synthetic cases.

## Where this is enforced

Most of these limits are also written into the module that implements the
method, next to the code they constrain. Where a limitation was discovered
by measurement rather than assumed, the measurement is recorded with it —
see [VALIDATION.md](VALIDATION.md) for the numbers.
