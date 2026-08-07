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

The force field is **MMFF94 or UFF, never Dreiding** — Dreiding is not
available here, and its numbers are not comparable, so nothing is relabelled
as it.

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

## Where this is enforced

Most of these limits are also written into the module that implements the
method, next to the code they constrain. Where a limitation was discovered
by measurement rather than assumed, the measurement is recorded with it —
see [VALIDATION.md](VALIDATION.md) for the numbers.
