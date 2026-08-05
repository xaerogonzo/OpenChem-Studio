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

## Where this is enforced

Most of these limits are also written into the module that implements the
method, next to the code they constrain. Where a limitation was discovered
by measurement rather than assumed, the measurement is recorded with it —
see [VALIDATION.md](VALIDATION.md) for the numbers.
