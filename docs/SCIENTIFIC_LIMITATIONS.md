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

**A score from a misplaced box looks exactly like a score from a good
one.** This is the failure mode most likely to produce a confidently wrong
answer, because nothing about the output indicates anything went wrong.
Measured on a real run: four tryptamines docked against 5-HT2A (6WGT) with
the search box left at the origin, **55.1 Å from where LSD actually
binds**. The box still clipped 139 receptor atoms, so it was not empty and
was not refused; all four returned nine poses with affinities of −5.5 to
−4.3 kcal/mol, and all four landed within 0.35 kcal/mol of each other —
because a non-specific patch of protein surface mostly measures ligand
size. The panel now places the box on the annotated site and reports the
distance before each run, but the general point stands: **check where the
box is before believing a score**, and treat a set of near-identical scores
across different ligands as a symptom rather than a result.

**The receptor is rigid.** No induced fit, no side-chain flexibility. A
ligand that would fit a real, breathing protein can be rejected by a frozen
one.

**Poses are not affinities**, and a redocking benchmark cannot show
otherwise. The measured 0.16–0.71 Å centroid displacements (plus one
2.5 Å outlier that is reported rather than hidden) say the search finds
the right *pocket* for ligands that came out of that pocket. They say
nothing about a novel ligand's real affinity.

**Good poses, weak ranking — and they are separate abilities.** This is the
single most useful thing to know about the tool, and it is measured rather
than asserted. CASF-2016 ([source:su2019]) evaluates scoring functions on
four *distinct* abilities and places Vina on opposite sides of two of them:
strong at **docking power** (finding the right pose — success rates "close
to 90%") and among the "not-so-good scoring functions in the scoring/ranking
power tests". A second study reaches the same split from another direction
([source:agboola2026]): across eleven targets, ranking barely degraded
between a site-directed and a whole-protein box (ROC-AUC 0.69 → 0.62) while
correct placement collapsed (96% → 48%), and the two were **uncorrelated**
(Pearson r = −0.03).

So: **trust the pose more than the ordering.** A set of close analogues
scoring within a few tenths of a kcal/mol is the expected behaviour of this
scoring function, not a finding about those molecules — and no amount of
extra search effort changes it, because it is the scoring function rather
than the sampling. Do not present such a spread to anyone as a ranking.

**The ligand is prepared at the declared pH, and that reaches the score.**
The Preparation pH governs the ligand as well as the receptor. It decides
which groups carry a hydrogen and therefore which can *donate* a hydrogen
bond, and a basic amine prepared as neutral reaches Vina typed as an
*acceptor* — the opposite of what it does in a pocket. This is not a
cosmetic distinction: [source:zhuang2022] shows fentanyl's piperidine amine
salt-bridging to the receptor's anchor aspartate, which is precisely the
interaction a neutral preparation cannot make. Ligand protonation, tautomer
and stereoisomer state are all known to move docking results
([source:tenbrink2009]).

One value is used for both because they are in the same solution. It is a
**declared preparation pH**, not a claim that a single number fixes every
protonation state — buried residues and histidine tautomers are beyond what
any one pH determines.

**Vina's search is stochastic, and the seed is now recorded.** Two runs of
the same receptor and ligand still differ — measured at about 0.03 Å of
centroid scatter on the redocking set — so do not read a difference smaller
than that as a difference. What changed is that the seed used is stored with
every result, so a run can be repeated *after the fact* rather than only
when someone thought to pin it in advance. That reproduces a run under the
same Vina version and settings; it is not a guarantee of identical output
across versions or machines, which is why the engine version is stored
beside it.

**Search effort is a documented choice, not an optimum.** The default
exhaustiveness is 25. Vina's own default is 8, and a study of 1/8/25/50/75/100
found 8 "performs well overall" with median pose error changing "little with
values higher than 25" ([source:agarwal2022]) — so 25 is that study's
resources-available recommendation rather than a value this project has
shown to be best for these receptors. Raising it does **not** rescue a
search box the ligand does not fit in: in [source:agboola2026], doubling
exhaustiveness left six of eight gross misplacements unresolved.

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

<!-- help:limits-solubility -->
## Solubility

**The intrinsic value is a model output read as a baseline, and those are
two different things.** ESOL predicts the aqueous solubility of the
compound as supplied. Treating that as the *neutral species'* solubility,
so a pH correction can be laid on top, is an assumption this app makes —
not something ESOL claims. The panel says `model logS0` and *predicted
intrinsic* deliberately, and never simply "intrinsic solubility".

**The rise stops at one of two bounds, and they say different things.**
Uncapped, Henderson–Hasselbalch puts aspirin at 4.7×10¹⁰ mg/mL at pH 14 —
correct arithmetic, meaningless answer. Any value that hit a bound says
which one on the fact itself.

The first is chemistry with a citation: Avdeef's **"sdiff 3–4"
approximation** ([10.1016/j.addr.2007.05.008](https://doi.org/10.1016/j.addr.2007.05.008),
§2.2) — in 0.15 M NaCl, the counter-ion salt begins to precipitate once
solubility exceeds intrinsic by about **four orders of magnitude for a
weak acid and three for a weak base**. It is asymmetric because a sodium
and a chloride salt are not equally soluble. This replaced a symmetric
+2 that had been inferred from a single ChemAxon screenshot and had no
source; on propranolol at gastric pH it moves the prediction from 7 to
70 mg/mL, against a real hydrochloride solubility near 50.

The second is arithmetic declining to be absurd: a **pure-compound
ceiling** of 1000 mg/mL, since a solute cannot outweigh the solution
holding it. It exists because sdiff is stated for *sparingly*-soluble
drugs and is silent about the rest — aspirin's uncapped rise of 3.91
never reaches an acid's 4.0, so the salt rule alone would leave it at
twelve kilograms per litre. Neither bound is this compound's measured
solubility product.

**For a strong base the cap swallows the whole regulatory window — but it
no longer decides anything.** Measured on propranolol (pKa 9.4): the
adjustment wants +8.20 at pH 1.2 and +2.60 at pH 6.8, so every point in
ICH M9's pH 1.2–6.8 window hits the limit and the *displayed* spread
across it is exactly zero. That used to make the screen report
`UNDETERMINED`, which meant an arbitrary constant blanked a whole
compound class.

**The screen is bounded rather than capped now**, and both bounds are
real: solubility is at least the neutral species' alone (ionization only
adds dissolved species), and at most the uncapped Henderson–Hasselbalch
value (which assumes the counter-ion salt never precipitates). So the
dose number is sandwiched, and each side licenses one verdict — a pass
when even the pessimistic bound clears the criterion, a fail when even
the optimistic one misses it. Four of five measured compounds get a
sound answer that way; propranolol remains `UNDETERMINED`, now because
its bounds genuinely straddle 1 rather than because a safeguard fired.

The floor assumes the solid is the free form, which is this model's
scope — salts and mixtures are refused. A compound dosed as a salt can
dissolve below its free-form solubility through the common-ion effect,
and nothing here models that.

**Multi-site ionization was corrected in 2026-08.** Ionizable sites
compose multiplicatively, and the shared Henderson–Hasselbalch factor
summed them — which never reaches the doubly-ionized regime, because
getting there needs both protons off. Monoprotic answers are unchanged to
the last bit; molecules with two or more ionizable centres moved, by up to
several log units, and they moved because they were wrong. This affected
logD, the logD curve, CNS MPO and BBB descriptors as well as solubility.
The reference is Avdeef 2007 Table 1
([10.1016/j.addr.2007.05.008](https://doi.org/10.1016/j.addr.2007.05.008)).

**Ampholytes and salts are refused, not modelled.** Henderson–Hasselbalch
assumes the undissolved species is the one with no site ionized. A
zwitterion's un-ionized form *is* the zwitterion, which is highly soluble,
so the model puts the solubility minimum in the wrong place and would
report a plausible curve for a different compound. A drawn salt or mixture
is already the species the pH correction models forming, so applying it
again answers a question nobody asked.

**The BCS line is a screening estimate and never a classification.** ICH
M9 requires solubility established *experimentally* over pH 1.2–6.8 at
37 ± 1 °C, using the lowest measured value. Everything here is predicted,
at no defined temperature. Dose number addresses only the high-solubility
half of the BCS test; permeability is a separate measurement.

**Solvents other than water are a LOOKUP, and a narrow one.** 92 solvents
and 2193 compounds, both sides measured (Abraham's solvation equation; see
`docs/SOLVENT_SOLUBILITY_ASSESSMENT.md` for the sources). Four limits
follow directly:

- **ESOL under-predicts BASES by more than half a log unit** — measured
  bias −0.59 on the Solubility Challenge (n=27) and −0.42 on the
  independent SC-2 set (n=17). It is **reported, not corrected**: a
  cross-corpus held-out test found the offsets agree and base RMSE improves
  both ways, but the bootstrap CI on the held-out improvement includes zero
  in both directions, so the adjustment is not distinguishable from
  sampling noise. Any base carries that note on the panel. Two further
  independent corpora were extracted to raise the power and could not —
  one is 74% inside ESOL's own training set and yields no bases at all,
  the other is too small to be held out — so this is a limit of the
  available public data rather than a question left unasked.
- **A compound outside those 2193 is refused by name**, with no fallback to
  a predicted descriptor. Coverage is the price of not estimating.
- **The aqueous baseline's error carries through undiminished.** The shift
  is measured; what it moves is an ESOL prediction at RMSE ≈ 1.26 log. A
  non-aqueous answer is not more reliable than the aqueous one it came
  from, and is usually the same accuracy or slightly worse.
- **The non-aqueous benchmark cannot validate the shift, and does not
  claim to.** Abraham's coefficients were fitted to measured solubilities
  — the very endpoint — so that half is structurally leaked. Measured on
  968 de-leaked cases: the composite prediction scores MAE 0.68 against
  ESOL's own 0.61 on the same compounds, which confirms the point above
  (the baseline dominates) without resting on the shift being validated.
  The shift-only arm is reported as an *optimistic bound* and visibly
  flatters itself, improving to 0.21 MAE when leaked rows are kept in.
- **Where two literature sources disagree by more than a factor of ten in
  the answer, it refuses rather than averaging.** Aspirin in toluene is a
  real instance.

**Acetic acid IS available now, and the entry it replaces is worth
knowing about.** It used to be refused here because it appeared only in
the source's *predicted* coefficient set, which its own authors say should
not be taken "as gospel". A *measured* set was later read from a second
paper, so it ships — and the 118 solvents still listed predicted-only are
refused on exactly the original grounds, with the reason named rather
than the solvent silently missing.

**pH, the BCS screen and the pH curve are water-only, deliberately.**
Henderson–Hasselbalch, the pKa values behind it and the ICH window are all
defined on aqueous media, so a non-aqueous solvent gets an intrinsic
solubility and no pH story rather than an authoritative-looking curve that
means nothing.

**Gutmann donor and acceptor numbers are reported BESIDE the prediction and
never fed into it.** Where the chosen solvent is one Gutmann measured, the
report names its donor number and its acceptor number. Those are facts about
the solvent, looked up, not inputs to the solvation model — Abraham's
equation is a fitted five-descriptor model and folding a donicity into it
would be inventing a relationship no source here establishes.

**They are two scales, and "the Gutmann number" is not a well-formed
question.** DN is −ΔH for the solvent's adduct with SbCl₅ in kcal/mol,
measured dilute in 1,2-dichloroethane. AN is dimensionless, a ³¹P shift on a
two-point scale between hexane at 0 and SbCl₅ at 100. A solvent can be high
in both — water is 18.0 and 54.8 — or high in one and near the bottom in the
other, which is HMPA at 38.8 and 10.6.

**Bulk donicity is a THIRD quantity.** Seven solvents were measured "in the
associated liquid" rather than dilute, and water is reported both ways: 18.0
dilute against 33.0 bulk. That gap is wider than the whole range from benzene
to acetonitrile, so the two are never merged.

<!-- help:limits-narrow-applicability -->
## Numbers whose applicability is narrower than their output

Four calculators will produce a number for almost any structure and mean
something for a much smaller set. Each refuses where it can tell, and this
section is for the part it cannot.

### Griffin's HLB

**Defined for nonionic surfactants with polyoxyethylene as the sole
hydrophilic moiety**, which is a structural condition rather than an
editorial caveat — it comes from the opening sentence of Griffin's own
definition. An ionic surfactant, a sorbitan ester or an ordinary drug is
**refused with the reason named**, not given a number.

Sorbitan esters are the case most likely to be got wrong. Griffin's
*experiments* produced the published values for Span and Tween, but his
*formula* does not apply to them: sorbitan is a polyhydric alcohol, so
polyoxyethylene is not the sole hydrophile.

**It will not agree with Marvin**, whose default is a proprietary consensus
method. That is documented rather than chased.

**"HLB" names two incompatible quantities.** Davies' scale shares the name
and differs substantially from Griffin's across the entire range of practical
applications, so the result says which scale it is on. Davies is not offered.

### The Cao–Liu topological steric effect index

**Topological, so it cannot see a conformation.** Two rotamers of one
molecule score identically. It estimates through-space bulk from the graph
alone, which is the whole point of it being instant — and the reason it is
not a substitute for the 3D steric measures in Geometry.

**"Steric index" names several mutually incompatible quantities** — Taft's
*E*s, Hancock's *E*sc, Charton's *ν* and this one — so it is reported as
Cao–Liu TSEI and never as a bare "steric index".

**Covers 28 elements and refuses the rest by name.** Those are the elements
Lange's Handbook tabulates a single-bond covalent radius for; the equation
needs one and there is nothing to substitute that would not be a number from
a different table.

**The equation is geometric and the validation is not.** There is no
per-element fitting, so any of those 28 computes — but Cao and Liu validated
against alkyl, halogen and ether substituents on biphenyls. A result on an
organometallic is an extrapolation the source does not support.

**The per-atom form is OpenChem's projection, not the paper's quantity.**
TSEI is defined for a *substituent measured toward a named reaction centre*;
running that expression at every atom in turn is a generalisation of it, and
the calculator is named "projection" for that reason.

**One published value does not reproduce**, and it is recorded rather than
tuned toward: the source's Table 6 gives isopropyl as 1.3752 where this gives
1.2801, which is what the same paper's text, Table 2 and Table 4 all imply.

### Miller polarizability

**Empirical, fitted to about 240 molecules**, so it says nothing dependable
about a structure unlike those.

**Isotropic — an average, not a tensor.** The companion paper that treats the
tensor is not implemented.

**`ahc` and `ahp` are different quantities, not settings of one.** The first
squares a sum over the whole molecule; the second is plain additivity. They
are offered side by side because the source offers both, and neither is a
default for the other. Jensen's additive scheme is a third answer again:
about 1% on aromatics and halogenated compounds, and roughly 11% high on
saturated hydrocarbons, because an atom-additive scheme has no hybridization
dependence.

**One published atom assignment disagrees.** Nitrobenzene's is `6CTR 1NPI2
2OTE 5H` in the source and differs here on the ipso carbon and on the nitro
oxygens — noted because that row is also among the worst in the source's own
table, at −6.8%.

### The pi component of orbital electronegativity

**It is a STARTING value, not a converged one**, and that is the whole of
the limitation. Marsili & Gasteiger's eq (7) is evaluated at the atom's
converged PEOE **sigma** charge — what the paper itself calls the starting
POE values — because the pi charge is zero at the beginning of a pi-level
computation. The iteration that would redistribute pi charge and feed it
back is not implemented, so nothing in this column reflects it.

**Three reconstructions of that iteration were measured and refused**, and
the numbers are in docs/VALIDATION.md: against the 15-molecule dipole
table of the source's own successor paper, the best scored 0.693 D where
the paper reports 0.164 D, and the printed equations came out at 0.834 D —
**worse than using no pi term at all**. The sources specify the weighting
and not the resonance-structure enumeration, so closing that gap means
tuning an unspecified enumeration until fifteen numbers agree.

**The ordering is the meaningful part, and it is NOT the sigma ordering.**
A sigma-negative atom is screened and comes out LOWER on this scale, which
is the effect these parameters exist to carry rather than a defect —
pyridine's nitrogen sits below its own carbons. Reading a pi value as
though it were a bare electronegativity inverts the conclusion.

**Conjugated atoms only.** An atom with no pi orbital is absent from the
result rather than reported as zero, and a molecule with no conjugated
system is refused with the reason named.

**Absolute values are parameter-set dependent** and will differ from any
other implementation, the same caveat the sigma component already carries.

<!-- help:limits-thermophysical -->
## Thermophysical properties (Joback)

**A group-contribution estimate, not a measurement.** Joback sums increments
over the 41 groups the 1987 paper tabulates. It has **no way to tell
structural isomers apart when they share a group count** — the paper says so
of cis and trans explicitly, so two geometric isomers receive one answer.

**A molecule containing a group Joback does not tabulate is refused by name**,
never given a partial sum. Every heavy atom has to be covered, and a group
the paper prints a dash for contributes nothing to *that property* rather
than contributing zero.

**The enthalpy of formation is the IDEAL-GAS value**, which is what the paper
predicts. It is not the solid. The gap between them is the enthalpy of
sublimation — tens of kJ/mol on exactly the compounds where it matters — and
that gap is why the detonation calculator below refuses rather than chaining
onto this one.

---

## Hansen solubility parameters

**A group-contribution estimate.** Stefanis and Panayiotou report r² = 0.935
for δd over 344 data points, 0.925 for δp over 350, and 0.960 for δhb over
375. **Errors of one to three MPa^0.5 are ordinary**, and δt inherits them
from all three.

**Stated for organic compounds with three or more carbon atoms**, excluding
the characteristic group's own atom. That is the paper's own domain, not a
conservative reading of it.

**Below 3 MPa^0.5 a separate regression applies** — the paper's Eqs. 27 and
28 rather than 25 and 26 — and the result records which produced it. Without
those two equations n-hexane's δp comes out **negative**, which is not a
quantity that exists.

**Second-order corrections deliberately overlap the first-order groups.**
They exist to say "these groups, in this arrangement, behave differently", so
a compound with none is not a degraded answer — it is the method. The result
says which order produced it either way.

---

## Energetic properties

### Oxygen balance

**Two conventions, reported as two named facts.** Ω(CO₂) and Ω(CO) are
different quantities for the same molecule — TNT is −74.0% against −24.7% —
so a figure quoted as a bare "oxygen balance" is ambiguous between them. The
source subscripts them for that reason and so does this.

**CHNO only.** The closed form is stated for CₐH_bN_cO_d. A sulfur or a metal
needs different accounting, so anything else is **refused rather than given a
confident wrong number** by silently ignoring those atoms.

### Detonation (Kamlet–Jacobs)

**It needs a measured solid-phase enthalpy of formation and a measured
loading density, and refuses without either.** Neither is something this
application can obtain, and that refusal is the honest answer rather than a
missing feature.

**The obvious bridge does not exist, and that was measured rather than
assumed.** Joback supplies the ideal-gas ΔHf; Trouton's rule
(ΔH_sub = 188 × T_m) appears to close the gap to the solid. Its own cited
source states a domain three times — few or zero internal rotors, no crystal
symmetry permitting overall rotation, no strong hydrogen bonding — and **0 of
8 classic energetic materials fall inside it**, because the nitro groups
*are* the internal rotors the correlation excludes. The domain predicate
ships anyway, so the next attempt starts from the measurement.

**ρ₀ is the density the charge was actually loaded to**, not a crystal
density and not a predicted one. P goes as ρ₀², so substituting one for the
other is not a small error.

**The −6% correction where G > 0.93 is opt-in and says why.** The paper
introduces it to match RUBY output and states it is "not necessarily
applicable for the prediction of actual detonation parameters".

### Formulations (mixtures of several substances)

**Every limitation above still applies**, because a formulation goes
through the identical equations. What follows is what is additionally true
of a mixture.

**Applying the method to a mixture is the authors' own, not this
project's.** [source:kamlet1968_iii] evaluates the pressure equation
against Table I's "13 explosive compounds and **14 binary mixtures** of
three general types", with those mixtures' parameters "estimated from the
H₂O–CO₂ arbitrary according to Eqs. (13)–(15) of Ref. 1" — the same
arbitrary the single-substance path uses. [source:kamlet1968_iv] is the
matching evaluation for the velocity.

**The composite formula is MOLE-weighted from MASS fractions, and getting
that wrong is silent.** A recipe is stated the way it is mixed, by mass;
CₐH_bN_cO_d is a per-mole quantity. Treating the stated mass fractions as
mole fractions gives a composite wrong by a few percent per element — on
ANFO 94.5/5.5, C0.3195 H4.5857 N1.9468 O2.9201 correctly against
C0.6600 H5.2100 N1.8900 O2.8350 — and **both land inside the arbitrary's
window and both give an ordinary-looking pressure**. No domain check can
separate them, which is why the composite formula is printed on the face
of the report rather than kept as an internal: it is the one number a
reader can check the arithmetic against.

**ρ₀ is the measured bulk density of the charge and is never derived from
the recipe.** A mass-weighted average of the components' crystal densities
is arithmetically reasonable, produces a plausible number, and is wrong: a
packed charge is nowhere near its ingredients' crystal densities, and P
goes as ρ₀². There is no source-backed route from a recipe to this number,
so it is supplied or the estimate is refused.

**Every component's condensed-phase ΔHf is supplied, never estimated** —
for the same reason as the single-substance path, and it bites harder
here, since a formulation needs one per component.

**Stated fractions that do not sum to 1 are refused rather than
normalised.** 94.5 + 5.0 renormalises to a perfectly ordinary-looking
recipe that is not the one anybody typed, and hides the missing
half-percent permanently.

**A mixture can still fall outside the arbitrary**, and then it is refused
like any other structure — the refusal says the *mixture* is outside it, so
a reader does not go hunting for an offending component.

**What is NOT modelled at all.** This is an ideal-detonation estimate for
the composite CHNO composition. It knows nothing about particle size,
intimacy of mixing, charge diameter, confinement, non-ideal or
diameter-dependent behaviour, or any component outside C/H/N/O — a metal
fuel, an inert binder or a plasticiser is refused rather than ignored.
ANFO in particular is strongly non-ideal in practice and its real velocity
depends on things no composition-only method can see.

**It is a property calculation and not a safety assessment**, and — like
the single-substance path — describes what a stated mixture would do, never
how to prepare one.

---

## Geometric aromaticity (HOMA and Bird)

**Both read real bond lengths, so both refuse a 2D drawing.** A depiction's
coordinates are a layout in arbitrary units: every bond in one comes out
about the same length whatever its order, so an index computed from them
would be a number about the drawing.

**Both describe the conformer in front of them.** A different conformer, or a
geometry from a different method, gives a different number. Bird's published
indices come from experimental geometries and a force field's are not those.

**They answer different questions, and the panel labels them so.** HOMA
measures how far each bond sits from one optimal length; Bird converts every
bond to a bond order and measures how **uniform** those orders are. Measured
on a six-carbon ring with all six bonds equal:

    bond length      HOMA      Bird
    1.397 Å         0.979     100.0
    1.467 Å        −0.608     100.0
    1.537 Å        −4.721     100.0

**So a Bird index of 100 means "equal bond orders", not "benzene-like bond
lengths".** Six equal bonds score 100 at any length, because the index is a
coefficient of variation; HOMA collapses across the same range. Neither is
wrong and they are not interchangeable.

**A Bird index is not comparable across ring sizes.** That is the source's
own requirement rather than an editorial caveat — the Kekulé reference
differs, 35 for a five-membered ring against 33.3 for a six-membered one — so
the fact label carries the I₅ or I₆ subscript, in the paper's words, "to
discourage inappropriate comparisons". HOMA sits in the same panel section
and *does* share one scale across ring sizes, which is why the labelling
matters here more than it would alone.

**I₅,₆ is not computed.** It indexes a fused two-ring system; this walks
rings individually, and reporting a per-ring number under that label would be
a different quantity wearing the name.

**Bird's own stated sensitivity is ±2 to 3 index units** from substituent
effects. Nothing here is pinned tighter than the method.

**Neither says whether a ring sustains a ring current or is energetically
stabilised.** Those are different measures of aromaticity, and this pair is
geometric only.

---

## Drug-likeness and complexity scores

**None of these is a probability and none is a verdict.**

**QED** is a desirability *aggregate* over eight properties. It is not a
probability that a molecule is a drug.

**Synthetic accessibility** scores ease of synthesis on a 1–10 scale. It does
not say whether a synthetic route exists, and RDKit's implementation is the
author's own later revision rather than the published one — r² = 0.97 against
the original.

**NP-likeness is a Bayesian comparison against a corpus**, so the corpus is
part of what the number means, and RDKit's model is a 2015 re-fit on public
data rather than the Novartis corpus behind the paper. The one case a reader
must not get wrong: **caffeine scores −1.09**, i.e. synthetic-like, and is a
natural product by any account; morphine scores +2.59.

**A confidence of 0.000 means no fragment of the molecule appeared in the
training corpus at all.** Methane scores exactly 0.00 for that reason, which
is indistinguishable from a confident neutral result unless the confidence is
read — which is why it ships as its own value beside the score.

**BertzCT is an index, and two different molecules can share a value** —
methane and propane both score 0. RDKit's implementation **deliberately
departs from the 1981 paper on aromatic rings**, by its own documentation, so
a printed value from that paper is an oracle only for non-aromatic molecules.

**Fsp3 is the ratio of sp³ carbons to all carbons.** It says nothing about
which carbons they are, and nothing about any atom that is not carbon.

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

**The dominant microspecies comes from Dimorphite-DL, and one of its
answers is corrected rather than inherited.** Dimorphite treats a nitrogen
bonded to an aliphatic carbon as a basic amine with pKa 8.16, and its
amide rule only fires when that nitrogen carries a hydrogen. A *tertiary*
amide therefore matches neither and is protonated at pH 7.4, which is
wrong by about eight pKa units — an amide's conjugate acid sits near −0.5.
Measured over sixteen drug-like molecules with literature charge states,
five were affected and every one was that class: DMF, DEET,
N,N-dimethylacetamide, N-methylpyrrolidone and fentanyl. Acetanilide and
lidocaine are unaffected, because they have an N–H.

This application removes that one protonation and reports the atoms it
touched — it never *adds* one, and anything else Dimorphite does stands.
Where the correction fires, the Calculator Inspector says so. It is worth
knowing that this is us overriding a library on a specific, well-understood
class rather than a general re-derivation of protonation, and that the
correction is structural: it does not consult a pKa predictor, so it
behaves the same whether or not one is configured.

**Charges are computed on that species, not on the structure as drawn.** A
neutral molecule with a basic centre is charged as its cation at pH 7.4, so
the Properties panel's "Total charge" (the drawn structure) and the
inspector's "Net calculated charge" (the species) legitimately differ. The
inspector names the species when they do.

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

**The file format you load a structure from can still change the
answer — slightly.** The same deposit is available from the PDB as
fixed-column `.pdb` and as `.cif`/`.bcif` (mmCIF), and the app reads both
through the same chemistry toolkit. That toolkit does not perceive them
identically.

Most of the gap is closed. Measured across the 48 curated docking targets
the catalogue held at the time (it holds 49 now — the figures below are a
measurement of that moment, not a claim about today's catalogue),
preparing each from both formats and comparing the atom types Vina is
handed: **0 of 48 matched before this was chased, 38 of 48 match now.**
Three causes were found and fixed — two-letter element symbols (Zn, Cl,
Fe, Se, Na) were silently *dropped* from mmCIF because the element lookup
is case-sensitive and the archive writes them uppercase; which copy of a
repeated ligand defined the search box depended on chain labels that mean
different things in the two formats; and no hydrogens at all were added to
an mmCIF receptor.

**What remains, and it is not fixed:** 10 of the 48 still differ in polar
hydrogens and nitrogen typing. No *heavy* atom differs anywhere any more,
so the structures agree — the protonation does not. **Which of the two is
right has not been established**, and the more plausible of the two is not
always the one you would guess. So:

- a docking score from an mmCIF-loaded receptor is not guaranteed
  bit-identical to one from the same entry loaded as PDB;
- if you are comparing runs, keep the source format constant;
- if a result is load-bearing, say which format it came from.

This is the honest state rather than a claim of parity. The app's own
receptor library downloads `.pdb` and falls back to mmCIF only for entries
too large for that format, so the common path is consistent by default.

---

<!-- help:limits-conformers -->
## Conformer generation

**These are MMFF94 (or UFF) geometries, not QM ones.** They are good enough
to start a calculation from and to compare shapes with; they are not the
answer to "what is this molecule's geometry". An ORCA optimisation started
from one will move it, sometimes a lot.

**No count of conformers is a count of the molecule's conformers.** The
search is random and a single run finds a slice of what is discoverable,
measured rather than presumed: on the hardest benchmark case
(ethylmorphine, a fused polycyclic) one run at the default settings finds
about 60% of the set five independent runs find together — and that
pooled set itself grew from 17 to 25 when the embedder's small-ring
torsion sampling was turned on, so "what is discoverable" is a property
of the sampling, not a property the application can exhaust. More
embeddings find more; the "distinct conformers to keep" limit then caps
what is returned, and its default is observed headroom over typical runs,
not a claim of sufficiency. When the cap removes conformers that were
found, the run's Details dialog says so; when it doesn't, the number you
got is still a lower bound of the run, never an inventory of the
molecule.

**"Distinct" is a heuristic judgement, not a physical fact, and this is
the part of conformer generation that is least solved.** Two embeddings
are treated as the same conformer when their heavy atoms and polar
hydrogens fall within 0.5 Å, compared symmetry-aware — *unless* their
force-field energies differ by more than 1 kcal/mol, which keeps them
apart.

**Why the energy term is there.** The geometric comparison has a measured
blind spot. On a fused polycyclic — a morphine derivative was the case
that exposed it — a ring can pucker through more than 100° while the
heavy atoms barely move, because the cage constrains them and the
displacement lands on the hydrogens. Across 138 such pairs, 128 had a
torsion moving more than 60° while every one sat under the 0.5 Å cut-off
(the figures were re-measured after the torsion diagnostic itself was
found symmetry-blind — it once reported a 180° change between two
*identical* structures — and the conclusion survived the corrected
instrument to the digit). The standard torsion fingerprint (TFD) misses
them too, reading 0.008 to 0.072 against a literature cut of 0.2, because
one torsion out of ~30 gets averaged away. Without the energy term the
molecule reported 2 to 4 conformers where at least 12 were found;
cyclohexane lost its twist-boat and was reported as rigid.

**The energy term is a veto, not a definition.** It declines to merge two
structures on insufficient evidence; it never claims that two structures
with different energies *are* different conformers. A difference below
the window does not establish that two shapes are the same conformer, and
one above it does not establish that they are different. Below 0.15 Å the
energy is not consulted at all — structures that close are the same shape,
and an energy gap there is a force-field artefact rather than a
conformational difference. That floor exists because without it about 2%
of 2H-azirine embeddings, a rigid three-membered ring, converged to a
distorted minimum 10.7 kcal/mol up with a stretched C=N and were reported
as a second conformer.

**A conformer can make stereochemistry ASSIGNABLE. That is not the same
as the molecule being stereochemically specified.** Once atoms have real
positions, RDKit's perception will label centres a flat drawing left
open — a bicyclo[2.2.2] cage's bridgeheads are the case that exposed
this. The label is a consequence of the geometry that happened to be
generated, not evidence that the drawn structure specified it, and
interconverting conformations, symmetric environments, pseudoasymmetric
centres and stereogenic axes or planes all sit outside what a single
embedded conformer can settle. The application therefore *reports* when
a geometry has done this rather than treating the perception as
authoritative, and *refuses* outright when a geometry would change or
erase stereochemistry that was already specified.

A consequence worth knowing: a derived IUPAC name may then be less
specific than the structure. The name is shown with a note saying so,
rather than withheld — the nomenclature engine is not wrong, it simply
cannot express what the geometry added.

**The generation controls emulate Marvin's, not its algorithms.** The
diversity threshold, optimisation level, time limit and refinement pass
are modelled on ChemAxon's Generate3D options because those are the knobs
people expect; none of them reproduces ChemAxon's implementation, and
ChemAxon publishes no default values for any of them, so the defaults here
are this application's own. In particular **"enhanced refinement" is not
"hyperfine"** — that runs short molecular dynamics before a strict
optimisation, and repeated minimisation is not an approximation of
trajectory sampling. It is recorded in a conformer's provenance as
`enhanced_optimization`, never as `hyperfine`.

**What the 3D viewer shows is superimposed for display, and that is a
viewing aid rather than a result.** Conformers come out of the embedder in
unrelated coordinate frames, so they are rigidly rotated onto the
lowest-energy one before being drawn — otherwise stepping between them
changes the orientation as much as the shape. The rotation changes no
chemistry (every bond length, angle, torsion and energy is identical), it
is recomputed rather than stored, and the coordinates that get saved,
exported or handed to a calculation are the ones the generator produced.
If you compare an exported conformer against what was on screen, expect
the same molecule in a different frame.

**A conformer brought into the 2D editor is a projection, not a
depiction.** "Use in 2D Editor" keeps the geometry and turns it to face
the camera, so bonds cross and atoms can sit close together — that is what
a 3D shape looks like drawn flat, and it is the point rather than a fault.
Some angles are genuinely unreadable: seen down its bridgehead axis a
bicyclo[2.2.2] cage superimposes its two bridges exactly. The application
says so and leaves the choice of angle to you.

**A CIP label on the canvas is a snapshot, not a live readout.** Ketcher
computes `(R)`/`(S)`/`(E)`/`(Z)` when asked and does not recompute them
when the structure changes — measured: deleting the atom that made a
centre stereogenic left the `(S)` label in place. Run the calculation
again after an edit. Unspecified centres are correctly left unlabelled,
so the failure mode is a stale label rather than an invented one.

**A lone-pair count is the LEWIS ANALYSIS MODEL's answer, and it
inherits that model's assumptions.** It is not measured electron density,
and it is not merely counting from the picture either: `outer electrons −
bonds − formal charge`, halved, guarded by everything `chem/lewis.py`
knows about when that arithmetic does not apply. Right for 21 of 21
textbook main-group cases checked (amine, ammonium, amide, nitro,
nitrile, carbonyl, ether, hydroxyl, alkoxide, water, thioether,
sulfoxide, sulfone, phosphine, phosphine oxide, pyridine, pyrrole, furan,
organofluorine, chloride, borane).

It declines three things. It has **no answer for a metal**, whose valence
is undefined and whose non-bonding electrons are frequently unpaired
rather than paired — reported as "cannot say", never as zero. It refuses
any structure with an **unpaired electron on a main-group atom**, since a
singlet carbene has a donor pair where the triplet has two lone electrons
and a drawing does not distinguish them. And it says nothing about
**where** a pair points, so it cannot rank two donors.

**Drawing those counts as dots on the canvas changes none of that**, and
makes it easier to forget — a picture reads as an observation in a way a
number does not. The dots are a visualisation of the analysis, and where
each one sits is a drawing convention chosen to avoid bonds and labels,
not a statement about orbital direction.

**A delocalised bond is split into what is localised and what is not.**
Where a full Lewis structure is drawn, a bond's *localised* electron pairs
are its minimum order across every resonance structure, and the remainder
is reported as one delocalised system with its own electron count.
Benzene is six localised σ pairs plus six π electrons — never three double
bonds and three single ones, which would assert a Kekulé structure the
molecule does not. Acetate, nitro, nitrate, carbonate and guanidinium each
come out as one delocalised pair over their equivalent bonds, which is why
none of them is drawn with one long bond and one short.

**Three things that method cannot do**, each measured rather than assumed:

- **An aromatic ring whose sextet is completed by a lone pair gets no
  number.** Pyrrole, furan and thiophene have a single Kekulé structure,
  so no bond order varies and the arithmetic finds nothing delocalised —
  when the answer is six, four from the two C=C and two from a heteroatom
  lone pair sitting in the ring. RDKit's resonance enumeration does not
  produce the contributors that move it there. The ring is still reported
  as delocalised; its electron count is reported as **not determined**,
  which is a different statement from zero.
- **An expanded octet is declined.** Sulfate, phosphate, SF₆, sulfite,
  dimethyl sulfoxide and phosphine oxide all present as cleanly localised,
  and whether they are drawn with expanded octets or as charge-separated
  is genuinely contested. This application has no position, so those bonds
  abstain with that reason. (A perchlorate written charge-separated obeys
  the octet exactly and needs no abstention — the contested thing is the
  drawing, not the species.)
- **Amide is treated as its neutral form.** Its charge-separated
  contributor is real chemistry, but a Lewis structure draws the neutral
  one, and the resonance settings that would include it also fail to fix
  the pyrrole case above.

**A region's electron count is a COUNTING statement.** "6 electrons" says
how many electrons the analysis could not assign to any single bond. It
is not a claim about orbital extent, not a Hückel aromaticity verdict,
and not a statement about how the contributing resonance structures are
weighted. The circle drawn around a ring is a convention for "these
electrons belong to the system rather than to one bond" and its radius
means nothing.

**And that is not always the π-electron count.** Measured against Hückel
on every aromatic shape the analysis can reach:

| ring | π electrons | region says |
| --- | --- | --- |
| benzene, aniline, tropylium | 6 | 6 |
| naphthalene | 10 | 10 |
| pyridine | 6 | 6 |
| pyrrole, furan, thiophene, imidazole | 6 | not determined |
| **cyclopentadienide** | **6** | **4** |

Cyclopentadienide's remaining two are drawn as a *lone pair on the
carbanion*, so all six are on the page and the electron budget closes —
they are simply apportioned as "four the analysis could not assign, plus
one pair it could" rather than as a π sextet. **Read the number as what
it is defined to be, not as an aromaticity count.**

The split between that `4` and pyrrole's `not determined` is mechanical
rather than principled: pyrrole has a single resonance contributor so
nothing varies and the model can tell it is blind, while
cyclopentadienide's bond orders do vary and the arithmetic completes on
the part it can see. Telling an **in-plane** lone pair (pyridine, which
correctly reports 6) from one **donated into the ring** is perception
this application does not have, so the gap is stated here rather than
guessed at.

**A truncated enumeration fails closed.** The resonance search stops at
256 contributors, and a bond whose minimum order was not established over
a complete set is never asserted as localised — it abstains, and says so.
An answer withheld is preferred to one derived from a partial search.

**Legibility is not a chemistry limit.** A large molecule whose analysis
is fine gets its diagram plus "may be hard to read at this size", never
"analysis unsupported". The two are separate statuses precisely so that
"I cannot represent this chemistry" and "I know the answer and could not
place a dot clear of a label" cannot be mistaken for each other.

**The diagram is a snapshot.** It shows the structure it was opened for
and does not follow later edits; it carries the molblock hash and the
structure revision so a stale window is diagnosable rather than merely
wrong. It cannot change the molecule.

**Rotating in the 2D editor is a rigid motion, and it is checked rather
than trusted.** Turning the structure changes coordinates and nothing
else — no bond length, no angle, no stereocentre. The app verifies both
halves of that before committing a turn, because each is invisible to the
other: a *reflection* preserves every distance (only the stereochemistry
sees one), and a *shear* preserves every stereocentre and the atom
ordering (only the distances see one). Either is refused with a message
rather than committed.

**The editor's coordinates are not Ångström until they are put back.**
Ketcher normalises bond lengths to its own unit — measured, a C–C at
1.5301 Å is handed back as 1.0702, a uniform ×0.699 — which never
mattered while the canvas only ever held a *layout*. Now that it can hold
a *geometry*, the scale is restored on the way in. Nothing you compute is
affected; this is recorded because a 30% error in every bond length is
invisible to atom order, to R/S labels and to a molecule's formula, and
would have looked entirely plausible.

**None of this makes the count correct in general.** It is the
best-performing heuristic on an eleven-molecule validation set
(`benchmarks/conformers/`), where half the references are textbook counts
and half are computational lower bounds — "at least this many minima were
found", not "this many exist". Every purely geometric criterion tested
failed that set, and there may be no single scalar
conformer-difference metric that works across arbitrary chemistry.

**Carbon-bound hydrogens are ignored in that comparison and polar ones are
not.** An O–H orientation is a real conformational degree of freedom,
because it changes hydrogen bonding and the energy of anything computed
afterwards. Heavy-atom-only comparison was tried first and was measurably
worse: ethanol's heavy atoms are C–C–O, three points and therefore rigid by
construction, so it reported one conformer for a molecule whose O–H
rotamers are exactly what a conformer search is for.

Carbon-bound hydrogens were originally dropped on the grounds that a
rotated methyl is not a different conformer. That reasoning turned out to
be unnecessary — the comparison is symmetry-aware, so it already scores a
pure methyl rotation at 0.0095 Å — but dropping them is kept because
including them measurably reads worse across the set. The cost is the
ring-pucker blindness described above.

**Mirror-image conformers are counted separately.** The comparison does
not reflect, so pentane reports 5 where the textbook says 4 unique
conformers: G+G+ and G−G− are enantiomeric and cannot be superimposed by
a rotation.

**A conformer that would not minimise is discarded, not shown.** Roughly
1 in 10 embeddings of a drug-like molecule failed to converge at the
library's default iteration limit and sat several kcal/mol above its own
minimum while being presented as part of an energy ranking.

**The search is random, not exhaustive.** ETKDG embeds from random starting
points, so the set you get is a sample. A molecule can have a conformer the
search did not find, and asking for more embeddings is the only lever —
there is no guarantee attached to any count.

That is why the dialog asks for two numbers. **Embeddings to try** is how
many random attempts to make; **conformers to keep** is how many distinct
shapes to return from them. They are not the same quantity and the gap
between them is large: measured across five independent seeds of 50
embeddings, the morphine derivative returned 10, 14, 14, 12 and 14 distinct
conformers — so the count varies by 4 between runs of the *same* request,
and 10 embeddings could not find its minima at any threshold.

**A 3D-dependent calculation uses one conformer, and says which.**
Geometry, surface area, SASA, the dipole and the steric parameters are
computed on the lowest-MMFF94-energy conformer *among those this sampling
run retained* — not "the lowest-energy conformer", which would be a claim
about the molecule rather than about one random search under one force
field. Each result records the conformer's id, so a number can be traced
back to the geometry it came from even after the list is re-sorted. A
molecule with no conformers is unchanged: those calculators say they need
one, as they always did.

**And the 3D viewer's shape overlay answers a DIFFERENT question, so its
number can differ from the panel's.** Ticking "Show shapes" recomputes a
shape-valued result — the dipole vector, a ligand cone, the principal
axes — for the conformer *currently displayed*, while the Properties
panel keeps reporting the conformer the calculator originally ran on. A
flexible molecule genuinely has a different dipole in each conformer:
measured on ethylmorphine, 5.53 D on the lowest-energy one and 4.71 D
three conformers along. Neither is wrong and they are not a
disagreement — the overlay labels its value with the conformer it
belongs to precisely so the difference reads as information. While a
conformer's shapes are being computed nothing is drawn, rather than the
previous conformer's geometry being left on screen.

In the gallery every cell is recomputed for its own conformer, so a page
of six shows six values that are all correct and all different. **None of
them is "the" dipole of the molecule**: each belongs to one geometry, and
a real sample is an ensemble. Comparing them tells you how much the
property depends on conformation, which is a different and usually more
useful thing than any single number — but it is not a population average,
for the same reason the energies below rank without quantifying.

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

**A dated screen is a question about the rulesets, not about legal
history.** *Screen as of* answers exactly one thing: *would this rule be
considered applicable under the effective-date metadata encoded in this
ruleset?* It does **not** establish complete historical coverage for that
date, repeal or expiry, jurisdictional validity beyond the ruleset,
amendments not represented in it, or how anything was interpreted or
enforced at the time. It is not a legal-history engine and must not be read
as one.

Two concrete consequences, both visible in the screen's own output:

- **Nothing here records repeal or expiry**, only when a rule started
  applying. A substance since removed from a schedule is still reported at
  any later date, and no ruleset carries the field that would say otherwise.
- **A ruleset with no dates is not constrained by the date at all.** The US
  DEA listed-chemicals ruleset records none — 47 of the 91 shipped rules —
  because 21 CFR 1310.02 has been amended repeatedly and no single date
  describes the list. Those rules are reported whatever date is asked for,
  and the coverage note says so rather than letting it pass as confirmation
  that they applied then. The alternative, treating an absent date as "never
  applicable", would silently empty half the screen.

A date the application cannot read is **refused**: the screen does not run,
and says so. Falling back to a current-rules answer with a warning attached
would answer a different question from the one asked and present it as the
one asked.

**A LISTING IS NOT A PROHIBITION, and most of what ships is ordinary
chemistry.** All three CWC schedules are loaded, and Schedules 2 and 3 are
largely industrial: phosgene, hydrogen cyanide, thionyl chloride,
triethanolamine, thiodiglycol. They are listed so that production above
certain quantities is declared and can be verified. The Convention's
obligations turn on quantity and concentration, which a structure carries
neither of — so this screen can say a chemical is listed and can never say
whether an obligation applies to anybody.

**Three entries are not encoded, and are counted rather than hidden.**
Saxitoxin and ricin, where a structural rule for a protein toxin is
meaningless; and Schedule 3's diethyl phosphite, where PubChem's record for
the CAS the entry prints is a cation and OPSIN returns an anion, so neither
resolver reaches the neutral substance listed. Coverage reports 16 of 17
for that ruleset and names the gap.

**Two rules over-report, by construction, and say so on the finding.**
Schedule 2's entry B.4 opens "except for those listed in Schedule 1" and no
rule can exclude another ruleset's members, so a Schedule 1 organophosphorus
agent matches both. And Schedule 3's entries carry no "and corresponding
salts" wording, unlike several in Schedules 1 and 2, while the engine strips
counter-ions before comparing — so a salt of a Schedule 3 chemical is
reported. Both are declared limitations rather than silent behaviour.

**Where a generic entry gives a size limit, it is usually not applied.**
Clauses like "H or ≤C10, including cycloalkyl" restrict a *substituent*,
and this engine can only count a molecule's total carbons. Applying the
total-carbon reading to entries A.3 and B.10 would exclude VX and QL, which
are those entries' own examples and have eleven carbons each — so those
rules carry no carbon limit at all. Where a limit is applied it may
over-report and will not under-report.

**THE DRUG-PRECURSOR RULESET IS ANCHORED MORE WEAKLY THAN THE CWC ONES,
and it says so.** The CWC Annex prints a CAS number beside every named
chemical, so those identities are traceable to the statute's own
identifier. 21 CFR 1310.02 prints DEA chemical codes instead, the EU
precursor annex prints CN codes, and the UN 1988 Tables print names only —
so no drug-precursor identity here could be anchored that way. Each rests
on two independent structure derivations agreeing, which is evidence and
not the statute's word. Every rule records which route produced it.

**A listed chemical is not a controlled substance.** The DEA list exists
because these chemicals can be diverted, not because possessing them is an
offence. Most are ordinary commerce and several are licensed medicines.

**Allotropes cannot be told apart by structure.** Red and white phosphorus
are separate entries with separate DEA codes and the same element; neither
is encoded.

**"Optical isomers" is matched more broadly than it is written.** The
engine compares stereo-insensitively as a fallback, which reaches
diastereomers as well as enantiomers. The DEA list carries three
diastereomer pairs, so each member matches its partner's entry too — as an
isomer, saying so, and every one of the six is itself listed.

**An exemption is matched as a skeleton plus a carbon count, not as an
identity.** Three entries exempt named chemicals; each exemption covers the
chemical and its salts, and does not excuse a mixture containing it.
Mixtures are outside what this screen considers in any case.

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

### Coordination geometry, when there ARE coordinates

With a real 3D conformer the polyhedron is named from every
donor–metal–donor angle, as the RMS deviation from a reference geometry
with the same donor count. Seven references are known: linear, trigonal
planar, tetrahedral, square planar, trigonal bipyramidal, square
pyramidal, octahedral.

**The match threshold is 10° RMSD, and both of its bounds were
measured.** A tris-chelate octahedron with ethylenediamine or bipyridine
bite angles (78°) scores 7.58, so anything stricter would refuse the
textbook octahedral complexes. Trigonal bipyramidal and square pyramidal
— the closest pair of references anywhere — are only 23.24° apart, so
anything at or above 11.62° could match both and the answer would depend
on the order the references happen to be listed in. 10° is the middle of
a genuinely narrow window.

**"Irregular" is a result, not a failure.** A complex outside tolerance
is reported as irregular together with the nearest reference and the
deviation, so a squashed octahedron reads as a squashed octahedron
rather than being rounded to "octahedral" or shrugged at. A tris-acetate
complex, biting at 60–65°, lands here at 18.9° and 15.8° respectively.

**The count alone never decides, and that is a real trap rather than a
theoretical one.** A pentagonal pyramid has six donors and five angles
within 5° of 90°; a rule keyed on "six donors, some right angles" would
call it octahedral. It scores 27.5° and is reported irregular.

**Nothing is reported for donor counts outside the table.** A
seven-coordinate uranyl centre or a nine-coordinate cluster gets "no
reference polyhedron at this donor count", which is a different
statement from "irregular" — the latter would imply a comparison that
never happened.

**Two donors closer than 30° are treated as one position modelled
twice.** This is disorder, not coordination: the lithium site of COD
1511792 has two modelled nitrogen positions 14° apart, and without the
guard it scores as a five-coordinate complex and earns a polyhedron name
it should not have.

**A perfectly planar complex from the 2D editor is indistinguishable
from a drawing, and is treated as one.** Square planar is flat by
definition, so coordinates alone cannot separate it from a flat sketch;
the check is RDKit's `Conformer.Is3D()`, which follows the molblock's
declared dimensionality. A square-planar complex from a genuine 3D
source is classified normally.

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

**A sigma-bonded drawing now works too.** The vendored perception still
recognises only the ionic form, so a sandwich drawn the ordinary way —
bonds from the metal to both rings — is *converted* to that form before
being handed over. The metal–ring bonds are removed, the rings made
aromatic anions and the metal given the balancing charge; the vendored
code is not modified, because a change inside 5,000 lines of vendored
perception has to be re-applied every time the vendor moves. Ferrocene,
ruthenocene, cobaltocene and methylferrocene are all assigned from a
bonded drawing, and the atom indices reported still address the molecule
you passed in.

**Pentamethylferrocene is still refused, and that is an upstream limit
rather than this one.** The conversion produces a correct ionic form for
it; the vendored perception declines that form as well. A test asserts
both halves so the two are never confused — if the vendor learns the
structure, the test fails and this paragraph comes off.

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

### Lattice energy for salts with complex ions

Kapustinskii refuses every polyatomic ion, because a nitrate or a
carbonate has a *thermochemical* radius — a different measurement from a
different source, absent from the shipped table. A second route answers
those: the volume-based correlation [source:jenkins1999] of Jenkins, Roobottom, Passmore &
Glasser (*Inorg. Chem.* 1999, 38, 3609), `U = 2I(α/V^⅓ + β)`, which
needs only the formula-unit volume and does not care how many atoms an
ion contains.

**Validated on 26 salts, mean deviation 3.3%, worst 7.7%** — against
Kapustinskii's 7.3% worst over 36 monatomic salts, so the same accuracy
class on the harder problem. Fourteen of the 26 carry a complex ion and
twelve of those land within 4.5%. The worst case is Ca(NO₃)₂, the one
markedly non-spherical anion in the set. The targets are CRC Handbook
Born–Haber values and the inputs are crystallographic volumes, so
neither side of that comparison is the source paper's own estimate.
Both were read from Jenkins' own Tables 2 and 3 — the CRC column is that
paper's reference 40 — rather than from the Handbook directly, which is
what [source:crc_handbook] records and why it is `reference_only`.

What it will not do:

- **Mixed valence is refused, not averaged.** Magnetite has Fe(II) and
  Fe(III); the correlation was fitted to one cation charge and one anion
  charge, and a mean would be a number the fit says nothing about.
- **Only MX, MX₂ and M₂X were fitted.** A 3:2 salt is refused rather
  than extrapolated — running a two-parameter empirical correlation past
  its data is how a plausible wrong number ships.
- **An imported crystal gets it only when the file states its ion
  charges.** The equation needs them, and a CIF supplies them only if the
  depositor wrote them into `_atom_site_type_symbol` — halite's own
  carries bare `Na` and `Cl`, and most depositions are the same. A
  structure silent about its charges gets **no lattice-energy line at
  all**: not a zero, not a default, absent. "The file did not say" and
  "the atoms are neutral" are different claims, and guessing between them
  would produce exactly the confident wrong number this file exists to
  prevent.

### Lattice energy

A **Kapustinskii estimate from Shannon six-coordinate ionic radii**, and it
ships because it cleared a gate set before it was built.

Validated against 36 experimental Born–Haber values
([source:kaya2022] — Kaya, Robles-Navarro, Mejía, Gómez & Cardenas,
*J. Phys. Chem. A* 2022, **126**, 4507, Table 3; 35 of the 36 were located
in the paper and all 35 match what ships):

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

## Nuclear data and decay chains

The nuclide table is **NUBASE2020**, shipped as a committed snapshot
([source:nubase2020]). It is a *reference table*, not a model: nothing
here computes a half-life or predicts a decay. What follows is what the
table cannot tell you and where this application has had to choose.

**NUBASE names no daughter STATE, so drawing a chain at all means
choosing one.** Read off the raw rows, the whole of what the decay field
carries is the mode and its branching — `B-=100`, `IT~100;B-=0.0037`.
Which state of Ru-99 a Tc-99m beta decay populates is simply not in the
source. This application draws the daughter's **ground state** and
**marks every edge where it did**: an assumed edge is dashed and the
legend says so. The one exception is an isomeric transition from the
first metastable state, where only the ground state lies below it, so
nothing is being chosen and the line is solid.

That assumption is older than the isomer data — a ground-states-only
table made it invisible rather than absent. Treat a dashed edge as "this
decay happens; which level of the daughter it lands on is not stated".

**One decay in the whole table is refused rather than drawn.** Pd-126p
records `B=72 8` — a beta decay with no sign — and the sign is exactly
what decides whether Z goes up or down. Its own ground state is `B-=100`
and an isomer sits higher in energy, so beta-minus is a near-certain
inference. It is refused for that reason: NUBASE's format header
documents no mode vocabulary to appeal to, and inferring would be this
application supplying physics the source declined to state. The branch is
reported as *underspecified*, which is deliberately **not** one of the
three physical leaf reasons — it describes the data, not the nucleus.

**Spontaneous fission and two cluster expressions have no single
daughter**, so those branches terminate with the reason written on them
rather than being followed.

**A half-life is not always a measurement, and the marks say which.**
`>` and `<` are bounds, `~` is approximate, and *(estimated)* means the
value comes from systematics rather than from experiment. A branching
marked *(unconfirmed)* is a decay nobody has quantified — **not** one
that never happens. Reading an estimated value as a measured one is the
easiest mistake to make here, which is why the marks are in the text and
not only in a colour.

**Four nuclides are marked stable AND carry a decay nobody has ever
observed** — Pb-204, Pb-206, Pb-208 and Hg-204, with `A ?` or `2B- ?`.
That is a genuine contradiction in the source, not a parsing error, and
it is why a uranium-238 chain continues past lead into mercury and why
the status line reports which stable nuclides a chain *reaches* rather
than where it "ends".

**253 and 254 are both correct for the stable count.** Ta-180m is an
isomer marked `stbl`, so a count over every state gives 254 where every
textbook says 253 ground states.

**A molfile records a mass number, not a nuclear state.** Tc-99m and
Tc-99 would write identical bytes, so applying an isomer to a structure
is refused rather than silently writing the ground state. Its half-life
and decay modes are still shown; only the write is refused.

**An element's "longest-lived radioactive isotope" is a property of the
isotope, taken over its states.** Silver's answer is Ag-108 at 439 years
— via Ag-108m, a metastable state. The swatch names the state, because
Ag-108's *ground* state lasts 2.37 minutes and attributing 439 years to
it would be wrong.

**Isobaric analogue states are listed.** Carbon shows four rows suffixed
`i` with no measured half-life. They are real entries in NUBASE and are
shown rather than filtered; deciding a reader may not see a state the
source lists would be this application editing its source.

## Crystal structures

### A crystal has to be MEASURED. You cannot get one from a SMILES.

Stated first because it is the question people actually arrive with —
"how do I turn the SMILES for table salt into a crystallography
structure" — and because the honest answer is no, in a way that is easy
to mistake for a missing feature.

**Going from a molecular graph to a lattice is crystal structure
prediction**, and it is an open research problem, not a menu item this
app is missing. It means searching the space of packing arrangements and
ranking them by lattice energy, where the relevant energy differences
between real polymorphs are often under 1 kJ/mol — smaller than the error
of the methods doing the ranking. Blind tests run by the CCDC have been
the field's benchmark for it precisely because the answer is so often
wrong. Nothing in this application attempts it, and a tool that produced
a lattice from a SMILES without saying which of those assumptions it had
made would be worse than one that declines.

So a crystal enters this app **only as a measured structure**, through
`File ▸ Import Crystal Structure...`, which reads a CIF. Where CIFs come
from:

| source | covers | access |
| --- | --- | --- |
| COD (Crystallography Open Database) | small molecules, minerals | open |
| ICSD | inorganic, including simple salts | subscription |
| CCDC / CSD | organic and metal-organic | subscription |
| RCSB PDB | macromolecules, as mmCIF | open |

Sodium chloride is in COD, which is where the two CIFs in
`tests/fixtures/cif` came from.

**What this app then does with it is read it, not refine it.** Everything
below is about a structure somebody else measured, and none of it
improves on the deposited coordinates.

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

### Clicking a site, and what its geometry does and does not mean

Clicking an atom in the unit cell reports that crystallographic site's
first coordination shell: the neighbours, their distances, and the
coordination polyhedron. The polyhedron uses **the same classifier as the
molecular path**, with the same 10° tolerance and the same references —
one answer computed one way, whether the subject is a metal complex or a
lattice site. Halite's sodium comes out octahedral at 0.0° RMSD, six
chlorides at 2.820 Å.

**The geometry describes whatever the shell rule returned, and the shell
rule is not a bond-finder.** The shell is cut at the largest relative gap
in the sorted distances, which works for the ionic and mineral structures
it was built for and less well wherever hydrogen and heavy atoms mix: the
biggest gap is then usually the one between the hydrogens and everything
else. Measured on COD 1511792, a methyl carbon's shell is its three
hydrogens at 0.986–0.996 Å, with the C–C bond at 1.47 Å beyond a 47.6%
jump. Three hydrogens 109° apart score 11.0° against trigonal planar and
are reported irregular — correct for that set of neighbours, and
misleading only if you cannot see what the set is. **That is why the
neighbour composition is always named** ("3 (3 H)") rather than only
counted.

**A neighbour is a contact, not a bond.** Nothing in a site report
asserts that two atoms are bonded, and several neighbours of any site
normally belong to adjacent unit cells — they are found as explicit
periodic images.

**A crystal click and a molecule click are different index spaces.** They
travel on separate signals and reach separate consumers; a crystal atom
and a molecular atom that share index 7 are not the same object.

### Which calculators a crystal is offered, and why it is none of them

Every calculator declares the structure kinds it applies to, and the
default is molecule-only. Today **none of the 59 registered calculators
declares a crystal**, so the crystal report says so outright rather than
implying some subset applies. That is not a gap being admitted — a
molecular weight, a logP or a rotatable-bond count is a property of a
discrete molecule, and running one on a single arbitrary formula unit
would give an arithmetically correct number about a species that does
not exist in the material.

The declaration replaced a hand-maintained list of category names, which
had drifted badly: 27 of the 49 were silently treated as applicable —
IUPAC Name, Tautomers, Molecular Dynamics and NMR Shifts among them —
while three of the thirteen blocked names matched no live category at
all. A calculator that genuinely applies to a periodic solid can opt in;
one registered without a thought cannot claim one by accident.

**A crystal is saved as its CIF text, not as a parsed structure.**
Reopening a project reparses it, so a project saved today reads better
tomorrow if the CIF reader improves — and nothing the reader currently
ignores is lost by being written out in a reduced form.

### What the CIF reader does not do

Anisotropic displacement parameters, disorder groups, restraints and
refinement statistics are **recorded in `Crystal.unhandled` rather than
dropped**, because a structure with disorder is still worth showing and
silently ignoring the fields is how a tool starts implying it understood
more than it did.

Standard uncertainty is stripped, not parsed: `5.6393(2)` becomes 5.6393.
Propagating it would only be worth doing everywhere, and a half-propagated
uncertainty is worse than none.

**The reader is exercised against six real depositions** from the
Crystallography Open Database, committed as fixtures — see
`tests/fixtures/cif/SOURCES.md` for provenance and licences. Between them
they carry everything the reader claims to survive: multi-line `;` fields,
quoted values containing commas, extra `_atom_site_` columns, anisotropic
and geometry loops, tags with slashes, negative fractional coordinates,
both the old `_symmetry_` and new `_space_group_` tag families, elements
from lithium to uranium, and atom labels containing apostrophes.

**Each file states its own `_cell_volume` and `_exptl_crystal_density_diffrn`,
computed by the depositor's software from the depositor's structure.** All
six are reproduced to the printed precision, which exercises parsing,
symmetry expansion, wrapping, deduplication, composition and cell volume
together against numbers this project did not produce.

Disorder and partial occupancy are covered by four of them:

| COD | disorder |
| --- | --- |
| 1511792 | an amine over two sites at 0.897/0.103, labelled `N2` and `N2'` |
| 1569411 | a water at 0.4212(76) **on a twofold axis**, giving 2 images not 4 |
| 1004002 | two-site disorder at 0.746/0.254, 238 sites |
| 1502211 | five distinct partial occupancies, 1488 atoms after expansion |

Leucopterin (1569411) is worth singling out. It states a rounded formula
(`C6 H5.34 N5 O3.17`, giving 12.68 O per cell) **and** a density of 1.888,
and the two are not quite consistent — 12.68 O would give 1.882. The
reading here gives 12.842 O and 1.8878, agreeing with the density. That is
the right one to agree with: the formula is rounded for display and the
file's own remark calls the water content "very uncertain".

What remains untested: **modulated and incommensurate structures**, which
this model has no vocabulary for at all, and **CIFs whose coordinates are
Cartesian rather than fractional**, which are refused by name.

### The calculated powder pattern gives POSITIONS and no intensities

**File → Import Crystal Structure** now reports where a powder X-ray
diffraction pattern's peaks would fall: an (hkl) list with an interplanar
spacing, a Bragg angle and a multiplicity. It reports **no peak heights
at all**, and that is a refusal rather than an omission.

**The two halves rest on different kinds of evidence, which is why one
ships and the other does not.**

Positions are lattice geometry. `1/d² = [h k l] G* [h k l]ᵀ` and Bragg's
law — nothing fitted, nothing tabulated, and the answer is checkable by
arithmetic you can redo: for a cubic cell the general expression must
reduce to `a/√(h²+k²+l²)`, and it does to six decimal places. Halite's
first lines come out at 27.37°, 31.70°, 45.45° and 53.87° for Cu Kα₁,
which is what a powder-diffraction text prints.

Intensities need `|F(hkl)|²`, and that needs a tabulated atomic
scattering factor per element. The standard parameterisation is
Waasmaier & Kirfel (1995) — five Gaussians, eleven parameters per
species. **The refusal is a measurement, not an estimate of effort.**
Over the four pages of its Table 1 in the copy available here:

| | |
|---|---|
| numeric tokens on the table pages | 2267 |
| visibly corrupted | 673 (29.7%) |

…and 70.3% "clean" is an *upper bound* on correctness, because a token
can be well formed and still wrong. Element labels are corrupted too —
the calcium row extracts as `Cs`, which would silently put caesium's
scattering factors on calcium.

**The deciding point is that only 6 of the 11 parameters can be
checked.** A neutral atom's scattering factor at zero angle is its
electron count, so `Σaᵢ + c = Z` is a per-row oracle over `a₁..a₅` and
`c`. The five `b` values have no such check: a wrong `b` is wrong at
every non-zero angle and exactly right at θ = 0, which is the one place
the checksum looks. A plausible intensity of unknown correctness is
worse than none.

### What the powder pattern is not

- **It is kinematic.** Extinction, multiple scattering and anomalous
  dispersion are not represented.
- **It is an idealised cell.** No preferred orientation, no strain, no
  instrument broadening, no zero-point offset, no sample displacement,
  and **no peak shape at all** — a reflection is a line at an angle, not
  a profile. Comparing it against a measured diffractogram is comparing a
  stick pattern with data that has all of those in it.
- **A systematic absence here is a statement about the space group**, not
  a prediction that an experiment sees nothing. The absences are derived
  from the structure's own symmetry operations rather than from a table
  of extinction conditions, so they are only as good as the space group
  the CIF resolved to — see the space-group section above.
- **The wavelength is the experiment's, not the crystal's.** The pattern
  uses the CIF's own `_diffrn_radiation_wavelength` when the file states
  one, and refuses when it does not. Nothing defaults to a laboratory
  tube: the whole angle axis scales with that number, and inventing it
  would be inventing the result.
- **The reported list is capped and says so.** A large organic cell with
  Mo radiation has tens of thousands of reflection families out to 60°;
  the report lists the twelve lowest-angle ones and states how many it
  did not list. Lowest-angle is the only honest ordering available
  without intensities.

## Where this is enforced

Most of these limits are also written into the module that implements the
method, next to the code they constrain. Where a limitation was discovered
by measurement rather than assumed, the measurement is recorded with it —
see [VALIDATION.md](VALIDATION.md) for the numbers.
