# Changelog — vendored `iupac_namer`

Changes made since the pinned upstream commit
`c3eac17ffd110c7c5dd37aaad2955e06cf8c9303`. Upstream is abandoned, so this is
the only history there will be; see `VENDORING.md` for provenance and
`KNOWN_LIMITATIONS.md` for what is still wrong.

The engine's correctness criterion is the **OPSIN round trip**: a name is
right when parsing it back yields the structure it came from. Since 2026-08-01
that is checked on two independent gates, canonical SMILES and full InChIKey.

## 2026-08-01 — vendoring

* 302 imports re-homed from `iupac_namer.` to `openchem.vendor.iupac_namer.`
  across 33 modules. Purely mechanical.
* `tests/audit/_audit_helpers.py`, which upstream never committed, was
  reconstructed at `tests/vendor/iupac_namer/audit/`. Three test files import
  it; writing it fixed 7 of upstream's 12 failures, which were failing on the
  missing module rather than on their merits.
* State as received: 2,907 passing, 12 failing, one file that would not
  collect. After the helper: 2,940 passing, 5 failing, 16 skipped.

## 2026-08-01 — the remaining 5 test failures were the tests, not the engine

Investigated all five. None was an engine defect; the engine's output is more
correct in every case, so the expectations were corrected and the comments
that had misled them fixed.

* **Cyclophosphazene lambda numbering (2 tests).** Engine emits
  `1,2,2,4,5,6-hexamethyl-2lambda5-1,3,5,2,4,6-triazatriphosphinine`; the
  tests pinned `4lambda5` with methyls at 1,2,3,4,4,6. Both round-trip, so
  only the lowest-locant rule separates them. The ring name pins N to 1,3,5
  and P to 2,4,6, leaving six numberings; the engine's wins **both** the
  lambda-locant criterion (2 < 4) and P-14.4's lowest-locants-to-prefixes
  (`1,2,2,4,5,6` < `1,2,3,4,4,6`), so it is right however that hierarchy is
  read. The expectation came from an illustrative example in
  `try_hantzsch_widman`'s comment block that the code never produced — with
  the lambda tiebreaker disabled it yields `6lambda5`, not `4lambda5`.
* **Polyacylium surface names (3 tests).** Tests pinned
  `malonylium`/`succinylium`/`glutarylium`. Those retained names are kept for
  general nomenclature only and the systematic name is the PIN
  (P-65.1.1.2.2 / P-66.6.3); `engine.py`'s `_RETAINED_ACID_STEM_TABLE` records
  that decision with citations, and the acid path deliberately emits
  `propanedioic acid`, never `malonic acid`. The expectations were therefore
  unreachable by construction. Four dead keys removed from
  `_RETAINED_DIACID_TO_DIACYLIUM`; `oxalic acid` stays because its retained
  name IS the PIN.

## 2026-08-01 — instrumentation and a second correctness gate

* **`diagnostics.py`** (new). Off unless `OPENCHEM_NAMER_DEBUG` is set or a
  `capture()` scope is open. Records every point where a charged molecule is
  handed back to the plan-search neutralizer, attributed to the gate that let
  it go (`unclaimed` / `ambiguous` / `partial_claim` / `charge_sum_mismatch` /
  `render_failed`), plus per-renderer attempted/succeeded/failed counters.
  The counters live in their own module so `charge_perception` keeps its
  documented "no module-level mutable state" invariant.

  The attribution immediately corrected the working model: instrumenting only
  the render site would have missed most of the inventory, because the benzyl
  cation, phenyl anion and guanidinium never reach a renderer at all.
* **Full InChIKey as a second round-trip gate** in `benchmarks/naming`.
  Compare the FULL key, never the 14-character skeleton block: guanidinium and
  neutral guanidine share skeleton `ZRALSGWEFCBTJO` and differ only in the
  final protonation character. It found on arrival that two of the four
  standing benchmark failures are tautomers, not wrong molecules.
* Benchmark scoring gained a per-molecule HTML report and a run-to-run delta
  that lists regressions first, so a swap — one molecule fixed, another
  broken, headline score unmoved — cannot hide.

## 2026-08-01 — severity-A fixes (wrong molecule)

Fourteen inputs that named the wrong compound. All are pinned in
`tests/test_namer_known_defects.py`, which runs in the **default** suite.

* **Ring polyacylium** (D-001, 7 cases). `_diacid_name_to_polyacylium` knew
  only `oxalic acid` and the chain `<parent>dioic acid`; ring parents arrive
  as `<ring>-<locants>-dicarboxylic acid`, so it returned `None` and every
  ring-based polyacylium named as its neutral aldehyde — the phthaloyl
  dication as `1,2-bis(oxomethyl)benzene`, i.e. phthalaldehyde. Added the
  `carboxylic acid` -> `carbonylium` rule (P-65.3.1).
* **`-ylium` / `-ide` locant** (D-005, 9 cases). `_render_simple_carbon`
  hardcoded `locant = 1`, true only for a terminal charge — which is all four
  compounds it was written against had, so the round-trip never caught it.
  `C[CH+]C` was named `propan-1-ylium` (it is propan-2-ylium) and
  `[CH2+]C1CCCCC1` was named `methylcyclohexan-1-ylium`, which moves the
  charge onto the ring. The renderer now asks the engine to name the skeleton
  as a **substituent anchored at the charged atom**: the free valence is the
  anchor that forces the parent to contain that atom and number it lowest,
  which is exactly what `-ylium`/`-ide` requires (P-31.1.4). Reuses the
  engine's own parent selection rather than reimplementing it.
* **Charge next to unsaturation** (D-002 family, 7 cases).
  `_classify_simple_carbon_charge` required every atom non-aromatic and every
  bond single, so benzyl/allyl/vinyl/propargyl/diphenylmethyl cations and
  anions were unclaimed — and unclaimed means neutralized, not left alone.
  Gate is now "all-carbon skeleton, charged atom not aromatic". Two guards
  were added after measurement showed the relaxed gate stealing the retained
  ring cations (`phenylium` had started coming out as `benzene-1-ylium`): the
  charge may not sit in an unsaturated ring, and a Kekule-written ring cation
  is not flagged aromatic by RDKit so the ring-saturation test is the one that
  matters.

Benchmark unchanged at 120/124 across all of the above, stereochemistry 11/11.

## 2026-08-01 — ring N-oxides in substituent position

D-024, the last open severity-A defect.  `[CH2+]c1cc[n+]([O-])cc1` came out as
`(pyridin-4-yl)methan-1-ylium 1-oxide`, which OPSIN cannot parse.

Additive nomenclature produces a TWO-WORD name, and a substituent has to end
in `-yl` so its parent can attach to it -- there is nothing to attach to the
end of the word "oxide".  The additive check in `engine.py` fired regardless
of output form, so it wrapped a cation core.

The fix is one condition: **the additive path declines in SUBSTITUENT output
form.**  The substitutive path already knew how to render the ring --
`1-(oxido)pyridin-1-ium-4-yl` -- it was simply never reached, because additive
claimed the molecule first.  Standalone output is untouched, so
`pyridine 1-oxide`, `pyridine-4-carboxylate 1-oxide`,
`trimethylamine oxide` and `dimethyl sulfoxide` all keep the additive form
that is correct for them.

With that in place the simple-carbon classifier no longer needs to refuse a
ring-embedded charge-separated group, so the guard added for D-018 is gone
again.  The obstacle was never the charge; it was the two-word name.

Two cheaper routes were tried first and both were wrong, which is why they are
recorded in `KNOWN_LIMITATIONS.md`: a curated ring entry keyed on the N-oxide
ring is dead data (the additive path strips the oxide before ring lookup), and
composing the name from parts means reimplementing substituent assembly for
one molecular shape.

Benchmark unchanged at 163/165 -- D-024 is not in the corpus, so this one is
verified by the defect table rather than by the score.

**The severity-A open list is now empty.**

## 2026-08-01 — poly-N-substituted guanidinium

D-025.  Guanidinium with more than one N-substituent was declined by the
classifier and fell through to the neutralizer, so `CNC(NC)=[NH2+]` came out
as `1-imino-N,N'-dimethylmethane-1,1-diamine` with the charge gone.

Guanidine numbers the charged (imino) nitrogen **2** and the two amino
nitrogens 1 and 3.  Lowest locants go to the more heavily substituted amino
nitrogen, which is what makes `CNC(=[NH2+])N(C)C` `1,1,3-trimethylguanidinium`
rather than `1,3,3-`.  Substituents are carved out, named as prefixes by the
engine, grouped by name, and emitted with multiplicity and alphabetical order:

  CNC(NC)=[NH2+]      -> 1,3-dimethylguanidinium
  CN(C)C(N)=[NH2+]    -> 1,1-dimethylguanidinium
  CNC(=[NH2+])N(C)C   -> 1,1,3-trimethylguanidinium
  CNC(N)=[NH+]C       -> 1,2-dimethylguanidinium
  CCNC(=[NH2+])NC     -> 1-ethyl-3-methylguanidinium

A lone substituent keeps the locant-free form (`methylguanidinium`): 1 and 3
are equivalent when only one is substituted, so it is unambiguous.

D-024 -- a ring N-oxide in substituent position -- remains open and is now
characterised in `KNOWN_LIMITATIONS.md`, including the two cheaper fixes that
were tried and rejected.

## 2026-08-01 — the last five open severity-A defects

Cleared the open list. Each had a different cause, and two of them turned out
to be one cause shared.

* **D-013, D-018 — the all-carbon gate.** `_classify_simple_carbon_charge`
  required EVERY atom to be carbon, far stronger than its own justification:
  the heteroatom motifs it exists to protect (acylium, iminium, amidinium) all
  have the heteroatom bonded directly to the charged atom, so checking the
  charged atom's own NEIGHBOURS suffices. The stronger form left any charge on
  a hetero-containing skeleton unclaimed, and unclaimed means neutralized --
  `[CH2+]c1ccncc1` came out as `4-methylpyridine`. Relaxing it also fixed the
  furyl, methoxy and hydroxy carbocations for free.

  Charge-separated groups elsewhere (nitro, azido) are now claimed rather than
  refused: they carry no net charge and are ordinary prefixes, but the coverage
  gate needs them accounted for. They must be OUTSIDE a ring -- a ring-embedded
  one makes the parent an additive two-word name (`pyridine 1-oxide`) that
  nothing can be spliced onto, which is D-024.

  Formylium is curated rather than classified: `_classify_acylium` demands no
  hydrogen on the `[C+]` and a single-bonded R, and the R=H member has one H
  and no R. Widening that pattern for a one-member family buys nothing.

* **D-015 — azolides.** Worse than dropping the charge: the plan search MOVED
  it, naming pyrrolide `1H-pyrrol-2-ide` with the charge on a ring carbon. The
  ring-anion classifier now covers nitrogen. The trap was the neutralization
  probe -- an aromatic ring N needs its hydrogen stated EXPLICITLY or the ring
  will not kekulize, and the failure presented as "not an aromatic ring anion",
  silently skipping the whole family. Imidazolide, tetrazolide and pyrazolide
  came along with it, moving from Hantzsch-Widman stems to retained PINs.

* **D-019 — diazoalkane ylides.** Net-neutral but carrying both a carbanion
  and a diazonium; `_classify_diazonium` claimed only the two nitrogens, so the
  coverage gate refused the molecule. Named as the carbanion's own `-ide` name
  plus `yldiazonium`, which delegates parent selection and numbering to the
  renderer that already gets them right. The attachment locant has to be
  restated -- `propan-2-idyl` lets OPSIN default the attachment to C1, giving a
  different molecule -- hence `propan-2-id-2-yldiazonium`.

* **D-020 — N-substituted guanidinium.** One substituent is named as a prefix
  on `guanidinium`. Two or more are declined rather than half-named (D-025),
  because the locants would have to be assigned across the guanidine skeleton.

Benchmark 162/165 -> **163/165**, diazomethane `no_prediction -> equivalent`.
Zero wrong structures, zero refusals, zero unparsable names: the only two
failures left are tautomers, and those are not errors.

## 2026-08-01 — the pyrazole stem in the partially-saturated path

D-023, severity B: right molecule, wrong ring stem. With no curated entry for
the partially-saturated 1,2-diazole ring, naming fell through to
Hantzsch-Widman, which spells it `1,2-diazole` — so 2-pyrazoline came out as
`4,5-dihydro-1H-1,2-diazole`. `pyrazole` is a retained ring name and the PIN
(P-25.2.1).

Only pyrazole was affected, which is worth knowing before assuming the hydro
path is broken generally. Imidazole and pyrrole already have curated
partially-saturated entries (`4,5-dihydro-1H-imidazole`,
`2,3-dihydro-1H-pyrrole`), and oxazole and thiazole get away without one
because their Hantzsch-Widman names — `1,3-oxazole`, `1,3-thiazole` — ARE the
preferred forms. Pyrazole is the only 5-ring in that set whose HW name differs
from its PIN, so it was the only one the gap could bite. Aromatic pyrazole was
never affected.

Two curated ring entries added beside the imidazoline one they mirror, with
`atom_locants` derived by OPSIN chloro-probing exactly as that entry documents.
For `4,5-dihydro-1H-pyrazole` locant 2 cannot be probed — it is the `=N-`, and
chlorinating it saturates the ring, so `2-chloro-…` resolves to pyrazolidine
instead; it is the one remaining atom and the one remaining locant.

This propagates through the whole pyrazolone family fixed in D-022: the
benchmark row is now `…-5-oxo-4,5-dihydro-1H-pyrazol-4-yl…`, and the edaravone
core is `3-methyl-1-phenyl-4,5-dihydro-1H-pyrazol-5-one`.

Knock-on, kept deliberately rather than worked around: a curated entry for the
2,3-dihydro-1H-pyrazole skeleton outranks the pre-composed `4-pyrazolone`
stem, so that ring now takes the systematic `4,5-dihydro-1H-pyrazol-4-one`.
That is the same treatment `5-pyrazolone` received in D-022 for being
semi-systematic rather than a PIN, so both pyrazolone stems now behave
consistently. Round-trip verified on both gates.

Benchmark unchanged at 162/165 — as expected for a severity-B fix, since both
forms denote the same molecule.

## 2026-08-01 — pre-composed retained rings in substituent position

D-022, severity A, and the last wrong structure in the corpus.

`5-pyrazolone` encodes C4's saturation only by convention. Put the ring in
substituent position and the name becomes `…-5-pyrazolon-4-yl`, which removes
the very hydrogen that made C4 sp3 — OPSIN then re-reads the whole ring as its
aromatic tautomer, a different species. Every senior characteristic group that
pushes the ring into substituent position hit it: amide, carboxylic acid,
nitrile. Only the benchmark's one pyrazolone row made it visible.

The retained lookup cannot detect this on its own, and that is worth recording
for whoever meets the shape again: `try_retained_name(ring_system, mol)`
receives the CARVED fragment, which is byte-identical to the standalone
molecule, and neither it nor the plan scorer in `strategy.py` is told the
output form. There is no structural signal to test.

What made a contained fix possible is that `5-pyrazolone` is semi-systematic
rather than a PIN — the PIN is the systematic `2,4-dihydro-3H-pyrazol-3-one`
form — so the engine's existing `_DATAFILE_PIN_INELIGIBLE_NAMES` gate is the
right home for it, next to tetralin/indan/chroman/isochroman. Declining the
stem outright sidesteps the missing context: the systematic path states the
saturation explicitly and is correct in BOTH positions.

That gate turned out to be wired into only one of the two branches that read
`_smiles_to_record`. The oxo fallback — the branch that matches rings keeping
an exocyclic =O, which is exactly where the pyrazolone family arrives — never
consulted it. Both branches now do.

Benchmark 161/165 -> **162/165**, and the wrong_structure count reaches
**zero**: every row the engine still answers, it answers with a name that
denotes the molecule it was given. The three remaining failures are two
tautomers and one refusal.

Knock-on worth stating: the systematic path spells the ring `1,2-diazole`
(Hantzsch-Widman) where `pyrazole` is the retained PIN. That is severity B,
pre-existing, and independent of this change — the hydro path already emitted
it — but routing the pyrazolone family through that path makes it far more
visible. Recorded in `KNOWN_LIMITATIONS.md`.

## 2026-08-01 — azide

D-016, severity A. `[N-]=[N+]=[N-]` named as `diiminoazanium`, which denotes
`N=[N+]=N` — a **cation**. The same one name came out for the azide anion
(q=−1) *and* for its conjugate acid HN3 (q=0), so a single confident answer
covered three different species and matched none of them.

No classifier claimed the N3 chain, so the plan search invented something.
Azide belongs with the other retained pseudohalides in the curated inorganic
table — cyanide, thiocyanate, cyanate, isocyanate, isothiocyanate are all
there — and simply was not. Two entries added: `azide` and, for the conjugate
acid, `hydrogen azide` (the PIN; OPSIN also accepts the retained "hydrazoic
acid").

The salt path inherited the fix for free: `[Na+].[N-]=[N+]=[N-]` was
`sodium diiminoazanium` and is now `sodium azide`. Organic azides were never
affected — `azidoethane` and `azidobenzene` go through the `azido` substituent
prefix, a separate path that was always correct.

Benchmark 160/165 -> **161/165**; polycharged 11/12 -> 12/12, which makes all
four charged-species categories perfect. One wrong structure now remains in
the whole 165-molecule corpus.

## 2026-08-01 — aromatic ring carbanions and guanidinium

Two more severity-A defects, both surfaced by the extended corpus.

* **D-003, aromatic ring carbanion.** `c1ccc[c-]c1` named as `cyclohexane`,
  losing the charge AND the aromaticity. `_classify_simple_carbon_charge`
  refuses an aromatic charged atom on purpose — a ring carbanion needs the
  ring parent's numbering, not a chain's — and nothing else claimed it.
  `_classify_aromatic_ring_anion` now does, emitting the plain `"ide"` hint so
  the existing renderer composes the name from the ring parent and the
  engine's own substituent numbering: `benzen-1-ide`, and it generalises to
  `naphthalen-1-ide`, `naphthalen-2-ide`, `pyridin-2-ide`, `pyridin-3-ide`.

  The gate took three attempts, and the two rejected ones are worth recording
  because they look sufficient. A **radical** test misses `[cH-]1cccc1`, which
  is closed-shell. "No hydrogen on the charged carbon" misses
  `Clc1ccc[c-]1Cl`, where a chlorine occupies the position rather than a
  proton having left it — and that arrives here as a lone fragment of a
  ferrocene salt, so it is not hypothetical. The gate that works is the one
  that matches the chemistry: **neutralize the site and check the ring is
  still aromatic.** Benzenide is a sigma carbanion, so putting the hydrogen
  back gives benzene; cyclopentadienide is a delocalised pi anion, so putting
  it back gives cyclopenta-1,3-diene, which is not aromatic and belongs to the
  retained-name path.

* **D-004, guanidinium.** `[NH2+]=C(N)N` named as
  `iminomethane-1,1-diamine`. `_classify_amidinium` requires the third
  substituent on the central carbon to be a CARBON, so guanidinium — whose
  third substituent is another amino nitrogen — fell through to the
  neutralizer. `guanidine` is a retained functional parent (P-66.4.1.2.1.2)
  and `guanidinium` its retained cation (P-73.1), so the name is emitted
  directly. Scope is the unsubstituted parent; `methylguanidinium` is recorded
  as D-020 rather than half-claimed, because with the refusal guard in place a
  classifier that claims what it cannot render raises instead of mis-naming.

`_splice_alkane_suffix` now elides a trailing `e` from any parent, not only
`-ane`: `ylium` and `ide` are vowel-initial, so `benzene` + `ide` is
`benzen-1-ide`. OPSIN accepts the unelided form too, but the elided one is the
PIN.

Benchmark 158/165 -> **160/165**; carbanion 7/8 -> 8/8, onium_ion 8/9 -> 9/9.

## 2026-08-01 — the neutralizer fall-through now refuses, selectively

Decided on measurement rather than principle. Over the benchmark corpus plus
the 69-probe sweep (193 molecules), `render_failed` occurred 0 times and
`partial_claim` once, while `unclaimed` occurred 35 times and was almost
always a molecule some other path names correctly.

So the first two raise and the third does not. A classifier that engaged with
a molecule and then could not finish can only produce a name for a different
molecule, because the coverage gate has already established which charges are
claimed. `unclaimed`, by contrast, is this module declining business that
belongs to the retained-ring path and friends — pyridinium, sulfonium,
betaine, nitrobenzene, phenylium.

Visible effect: `name_smiles("[CH2-][N+]#N")` raises instead of returning
`(azanylidyne)(methyl)azanium`, which was the methyldiazonium **cation** —
an invented hydrogen and a charge that is not in the input. On the benchmark
diazomethane moved `wrong_structure -> no_prediction`, so the score is
unchanged; the difference is that one of those two is honest.

## 2026-08-01 — indicated hydrogen survives the ring table (D-026)

The ring-table entry for `c1cn[nH]n1` was labelled `1H-1,2,3-triazole`, which
is the other tautomer — OPSIN parses `1H-` to `c1c[nH]nn1` — and the 1H form
had no entry at all. Both inputs therefore came back named as the 1H
structure, discarding the indicated hydrogen the caller supplied. A plain data
mislabel, not an algorithm defect: the 1,2,4-triazole and tetrazole entries
sitting beside it already distinguished their tautomers correctly.

Probing all 13 tautomer-sensitive azoles in the tables found no second case.
The purine family still normalises to `9H-purine` on purpose (see
`KNOWN_LIMITATIONS.md`); that is the only remaining place where an input
tautomer is not preserved.

This also corrects a claim made earlier in this branch. The two standing
benchmark failures were described as "tautomers, not errors" — true of
metformin, false of the triazole, where the engine really was substituting a
different structure. The mistake came from reading a matching InChIKey as
proof of correctness when InChI cannot distinguish mobile hydrogens at all.

## 2026-08-01 — benchmark corpus extended to 181

The last three fixes (D-024 ring N-oxide substituents, D-025 poly-N-substituted
guanidinium, D-026 tautomers) all had to be verified against the defect table
rather than the score, because the corpus contained nothing from those
families. Added 16 rows — `n_oxide` (6), `guanidinium` (5), `tautomer` (5) —
so those paths are now measured on every run.

Re-running the **as-vendored** engine against the extended corpus shows how
much each category actually discriminates, which is not uniform:
`guanidinium` 0/5 and `n_oxide` 4/6 then, both 100% now — those rows catch
their defects outright. `tautomer` scores 5/5 *both* times, because the
as-vendored engine emitted the bare name `1,2,3-triazole` for the 1H input
and OPSIN resolves a bare name to 1H, so it round-tripped by luck. D-026 is
caught by the pre-existing `heterocycle` row (the 2H form), not by the new
category; the new rows guard the 1,2,4-triazole and tetrazole pairs that were
already correct. Worth stating plainly: adding rows to a corpus does not by
itself mean the corpus can see the defect they were added for.

## 2026-09-17 — substituent naming: stereo, order, locants

Three defects, all in SUBSTITUENTS, all found from one user report (a fentanyl
and three tryptamines). None of them was visible to the naming benchmark,
which scores by OPSIN round trip: two produce a valid name for the right
molecule, and the third produces a name OPSIN parses perfectly into the wrong
enantiomer.

* **D-027 — a descriptor recomputed on the carved fragment.** Carving replaces
  the cut side with H, which reorders CIP priorities at any centre or double
  bond whose ranking depended on that side. The first carve already inherited
  the parent's ATOM descriptors; a NESTED carve started from the first
  fragment and recomputed there, and bonds never inherited at all. Measured on
  MPMI (`CN1CCC[C@@H]1Cc1c[nH]c2ccccc12`, an R centre): the first carve
  inherited R, the second recomputed S from `C[C@H]1CCCN1C`, and the name said
  `(5S)`. Every E/Z measured inside a substituent was inverted --
  `C/C=C(/C)c1ccc(cc1)C(=O)O` (Z) was named `4-[(2E)-but-2-en-2-yl]benzoic
  acid`. `_context_cip_maps` now reads each atom's and bond's descriptor as it
  holds in the molecule being named, inherited beating recomputed, and
  `_stamp_context_cip` copies both through the `GetMolFrags` map after
  checking it is injective and element-preserving. `StereoAnalysis` prefers an
  inherited E/Z the way it already preferred an inherited R/S.

* **D-028 — prefixes cited out of alphanumerical order.** `derive_sort_name`
  stripped only the OUTER bracket and the leading locant, so a nested bracket
  reached the key and `(` and `[` sort before every letter: acetyl fentanyl
  came out `N-[1-(2-phenylethyl)piperidin-4-yl]-N-phenylacetamide`. It also
  stripped any leading `di`/`tri`, filing `dimethylamino` under m against
  P-14.5.2 (`2-ethyl-4-(dimethylamino)benzoic acid`) and `diazenyl` under a.
  The key is now the letters of the complete name with locants, indicated
  hydrogen, italic heteroatom locants, stereodescriptors, `lambdaN` and
  `tert`/`sec` removed at every depth, and a leading multiplier removed only
  where it multiplies. Every other sorter -- the three first-alpha helpers,
  the ester, phosphite and anhydride class words, the acetamido handcraft --
  now reads that one key instead of sorting raw strings.

* **D-029 — a heterocyclyl free valence numbered by plan order.** P-31.1.4
  numbers a ring substituent by heteroatoms (b), indicated hydrogen (c), then
  the FREE VALENCE (d), ahead of the ene ending (e) and every detachable
  prefix (f). The free valence was scored nowhere, so the two N=1 directions
  of 1-methylpyrrolidine tied and plan order decided -- and since the carved
  fragment's C2 and C5 are symmetry-equivalent, which one was the attachment
  depended on the input's atom order. Hence `(1-methylpyrrolidin-5-yl)methanol`
  and, with prefixes deciding instead,
  `4-(1,2-dimethylpyrrolidin-5-yl)benzoic acid`.
  `_lowest_free_valence_numberings` keeps the heteroatom-optimal numberings
  and among them those giving the free valences the lowest locants.
  Three more instances turned up while writing the regression table, each
  measured against the pre-fix engine rather than assumed unchanged:
  `4-methylpiperidin-6-yl`, `2-methylfuran-5-yl`, and the pinned sulfolene row
  (now `sulfol-3-en-2-yl`; both names round-trip, so that one is a
  preferred-name change rather than a wrong molecule).

* **Structural perception, which is NOT naming.** A new `structural_groups`
  table (`data/functional_groups.json`) holds ring amines and the aromatic
  N-H, matched in their own pass and reachable only through
  `FGDetection.structural_features`. They are deliberately absent from
  `detected_fgs`, because everything there becomes a suffix or a prefix and a
  ring nitrogen added to it would put `amino` into piperidine's name. Every
  name in the 187-row corpus is unchanged.

Benchmark, on the corpus extended to 187 rows: **184/187 before (exact 82,
three `stereo_wrong`) -> 187/187 after (exact 87)**. The scorer gained a
`stereo_wrong` class for the same reason the app's verifier did: a name
carrying the OPPOSITE descriptor was being reported as "silently flattened".
Vendored suite: 3,255 passing, 16 skipped, 0 failing.

## 2026-09-17 — a bridged free valence, found by a held-out corpus (D-030)

The third ring class to show the D-029 rule, and the first to produce a
**wrong molecule** from it.

* **How it was found matters as much as what it was.** The 187-row
  regression corpus scores 187/187 both before and after this fix, so it
  could not have found this. A held-out corpus was added instead — 40 rows
  by a fixed PubChem CID stride, admitted by a filter settled in advance,
  with the engine never consulted during selection
  (`benchmarks/naming/build_heldout.py`). It found the defect on its first
  run, scoring 39/40 where the curated corpus scored 187/187.

* **D-030, severity A.** `CNC(C)CC12CC3CC(CC(C3)C1C1CCCCC1)C2` was named
  `1-(2-cyclohexyladamantan-5-yl)-N-methylpropan-2-amine`, which is
  `HQMBUZVFGUDZCC` and not the `RNYOSRZCHQLRMT` it was given. Locant 2 is
  adjacent to 1 and 3 but not to 5 in adamantane numbering, so the pair
  `(2-substituted, 5-yl)` describes a constitutional isomer rather than a
  non-preferred name. Bare adamantyl was always correct; the defect needs a
  second ring substituent to exist at all, which is why nothing had hit it.

* **The cause was a tie-break doing a rule's job.** D-029 fixed monocyclic
  heterocycles by FILTERING the candidate numberings. Bridged rings kept an
  older branch that only SORTED them, so the numbering giving the free
  valence the lowest locant merely landed last and won on "later-generated
  wins a tie" — which holds only while the scores tie. Any competing ring
  prefix outscores it, and P-31.1.4.2.4 ranks the free valence AHEAD of
  detachable prefixes. The fix deletes the branch: bridged rings now take
  the same filter as every other ring substituent, so the answer no longer
  depends on how ties are broken. That is what
  `_lowest_free_valence_numberings` already said when D-029 added it.

* **And the fix exposed a second latent defect**, which is the part worth
  reading. With the locant corrected to 1, three names became
  `adamantan-yl`: the `-yl` suffix elides locant 1, and elision is only well
  formed where the stem contracts to absorb it (`cyclohexan` →
  `cyclohexyl`). Whether the stem contracted was decided by a *different*
  predicate from the one performing the elision, so the two could disagree.
  They are one decision now —
  `assembly.render_free_valence_suffix(stem_contracts=...)` — and on a
  bridged ring the locant is load-bearing anyway, since adamantane 1 and 2
  are not equivalent and a bare `adamantyl` would be ambiguous between them.
  PubChem writes `1-adamantyl` for the same reason.

  A first attempt at this refused elision for ANY ring attachment, which
  regressed the pinned `4-(2-methylcyclohexyl)benzoic acid` to
  `...cyclohexan-1-yl`. A monocyclic carbocycle DOES contract, so the
  premise was wrong; coupling elision to the contraction is what handles
  both.

* **Five organoelement names in the regression corpus were malformed the
  same way** and are now well formed: `(trimethylsilan-yl)benzene` →
  `(trimethylsilan-1-yl)benzene`, and likewise for the phosphane, the
  siloxane, the phosphane oxide and betaine's `azanium-yl`. These are still
  not the preferred names — P-44.1.2 makes the silicon the parent, giving
  `trimethyl(phenyl)silane` — but a cited locant is the difference between a
  non-preferred name and a malformed one.

Benchmark: regression corpus **187/187 before and after**, with nothing
structurally regressed and 5 names reworded as above; held-out corpus
**39/40 → 40/40**. The defect table gains 8 rows (4 defect, 4 non-regression), and
D-030d pins the emitted `{...}` braces rather than correcting them, because
the enclosing-mark nesting is a separate serialization defect (P-16.3.2) and
both forms parse back to the same structure.

## 2026-09-17 — a fused free valence, where locant 1 is unreachable (D-031)

The third ring class, completing the rule D-029 and D-030 fixed for
monocyclic and bridged rings.

* **The plan predicted the wrong cause, and measuring it first is the only
  reason that cost nothing.** The prediction was that a ring numbered from
  the curated table exposes one canonical `atom_locants` map, leaving
  nothing to filter between — so the fix would have to generate
  symmetry-equivalent orientations. Measured: naphthalene already offers
  FOUR numberings, placing the attachment at 2, 3, 7 or 6, and the correct
  one is yielded first.

* **The cause was a fallback that abandoned the rule.** The branch filtered
  for "attachment at locant 1" and, finding none, yielded EVERY numbering.
  Locant 1 is simply not reachable on a fused ring, so that fallback handed
  the decision to the prefix band, which prefers the numbering giving
  methoxy the lower locant — the opposite of P-31.1.4.2.4, which ranks the
  free valence ahead of detachable prefixes. It now falls back to the same
  rule applied to what IS reachable: the lowest free-valence locant among
  the candidates.

* Generalised across five ring systems, each verified on canonical SMILES
  and full InChIKey, with the locant checked per skeleton rather than
  assumed constant: `naphthalen-2-yl`, `anthracen-2-yl`,
  `phenanthren-3-yl`, `quinolin-2-yl` (its nitrogen holds 1), and
  `4-methylnaphthalen-2-yl`. A substituted monocyclic phenyl still reaches
  locant 1 and is pinned unchanged, as is the ester case where the PARENT
  changes and the substituent numbering must not.

Benchmark: regression corpus **187/187, exact 87 → 89** (both naproxen rows
`equivalent` → `exact`, and no other name moved); held-out corpus 40/40
unchanged. Vendored suite: 3271 passing, 16 skipped, 0 failing. The defect
table gains 10 rows (3 defect, 7 generalisation and non-regression).

## 2026-09-17 - the plan budget is two budgets (D-032)

Not a ranking defect, and that distinction is the whole entry. The
seniority logic scored the silicon parent at 5000 against benzene's 561 and
would have preferred it instantly -- but no silicon plan was ever generated,
because the plan search had already spent its entire 20-plan budget on
benzene's NUMBERING variants. A candidate that does not exist cannot lose on
the merits, and the output looks like a considered choice.

* **Measured first, with the cap lifted so the real counts are visible:**

        plans for ONE parent hypothesis    median 4   p90 36   max 96
        total plans per molecule           median 7   p90 65   max 138
        distinct hypotheses per molecule   median 1            max 10

  The single counter capped at 20 was REACHED by 67 of the 189 molecules
  that produce a top-level trace -- a third of the corpus naming from a
  truncated search. In the worst cases every slot went to one parent:
  nitrobenzene, thiophenol, triphenylphosphine and phenylboronic acid each
  spend 20 plans on benzene numberings and propose a single hypothesis.

* **It bought nothing.** Runtime is not driven by the plan count: the
  slowest molecule in the corpus (a steroid, 2.2 s) produces 17 plans, while
  the 138-plan molecule takes 0.02 s. After the change the whole
  227-molecule set still names in about 7 s.

* **Two budgets now** (`_PlanBudget`): `_TOTAL_PLAN_BUDGET = 512` as the
  work bound, against a measured maximum of 138, and
  `_PLANS_PER_HYPOTHESIS = 128` as the anti-starvation bound, against a
  measured maximum of 96. Both sized with headroom rather than at the
  observed maximum, because a threshold fitted to the cases in hand is not a
  validated threshold. `_parent_hypothesis_key` defines what counts as the
  same hypothesis -- parent type, element, atom set, PCG and naming method,
  deliberately NOT the emitted name, object identity or canonical SMILES,
  and deliberately not the numbering, which is the thing being expanded.

  The tier ordering already encoded this insight for a different starvation
  -- decomposition handlers run before substitutive so a small substitutive
  space cannot starve a functional-class plan -- and ordering cannot solve
  this one, because the competing parents come from the same handler.

* **Four names, three of them now exact:** `trimethyl(phenyl)silane`,
  `triphenylphosphane` and `diphenyliodanium` match PubChem verbatim, and
  triphenylphosphine oxide moves to `oxotri(phenyl)phosphane` -- right
  parent, with the `tri(phenyl)` enclosing marks still to fix as a separate
  serialization defect.

* **Eight vendored tests pinned the pre-fix parent, and the ENGINE was right
  rather than the tests.** `test_recursive_aryl_heavy` states "ring beats
  heteroatom_center" as design intent and guards it with three tests named
  `_unchanged`. That inverts the Blue Book cascade. BlueBookV2.pdf p. 375,
  P-44.1.2, verbatim: "The senior parent structure, whether cyclic or
  acyclic, has the senior atom in accordance with the seniority of classes
  (see P-41) expressed by the following decreasing element order: N > P >
  As > Sb > Bi > Si > Ge > Sn > Pb > B > Al > Ga > In > Tl > O > S > Se >
  Te > C. This criterion is applied to select the senior atom in parents and
  to choose between rings and chains."

  Carbon is last. P-44.1.2.1 adds that "a single senior atom is sufficient
  to give seniority to the parent hydride", and the same page gives
  Si(CH3)4 -> tetramethylsilane (PIN) "(Si is senior to C)" and
  [silanediyldi(ethane-2,1-diyl)]bis(silane) (PIN) "(Si is senior to C, see
  P-44.1.2)". The ring-over-chain rule at P-44.1.2.2 applies only "when a
  ring and a chain contain the same senior element", which a phenylsilane
  does not.

  So `(silyl)benzene` became `phenylsilane`, and likewise
  `phenylbismuthane`, `phenylplumbane` and `phenylstibane`. Every one
  round-trips on canonical SMILES and full InChIKey, which is why the old
  forms survived: a round trip cannot see preference. The updated tests keep
  their real subject -- R21-A is about the carved ring coming back as
  benzene rather than cyclohexane, R22-B about a Pb/Bi/Sb fragment being
  nameable at all -- and assert it separately from the full string.

  The three phosphane bracketing rows moved to inputs carrying a principal
  characteristic group, because P-44.1.1 outranks the senior-atom criterion
  and keeps the parent on the carbon chain. That makes the phosphanyl
  substituent appear deliberately instead of incidentally, and exercises two
  steps of the cascade instead of one.

Benchmark: regression corpus **187/187, exact 89 -> 92**; held-out corpus
40/40 unchanged; nothing structurally regressed. Vendored suite 3306
passing, 0 failing -- the first entirely clean run of this branch, because
the OPSIN input-file collision fixed in the previous commit had been
costing one to eight spurious failures per run.
`tests/test_namer_plan_budget.py` pins the mechanism rather than the names,
and was mutation-tested -- collapsing every plan into one bucket kills 6 of
its 14 assertions.

## 2026-09-17 - a mononuclear parent must not cite locant 1 (D-033)

The counterpart to D-030, out of the same paragraph, and only visible
because D-030 was fixed first.

P-29.2 method (2) (BlueBookV2.pdf p. 301): the free-valence locants "are as
low as is consistent with any established numbering of the parent hydride
and, EXCEPT FOR MONONUCLEAR PARENT HYDRIDES or the suffix 'ylidyne', the
locant '1' must be cited". So one rule requires `adamantan-1-yl` to carry
its locant and forbids `azanium-1-yl` from carrying one. The engine had both
wrong, in opposite directions.

* **`2-(trimethylazanium-1-yl)acetate` -> `2-(trimethylazaniumyl)acetate`**,
  which is PubChem's string exactly. A mononuclear parent also has nothing
  to contract -- the engine stores `alkyl_stem == stem` for these, measured
  as `silan` and `azanium` -- so the chain test the contraction used,
  `stem == alkyl_stem + "an"`, could never match and the locant was cited
  by default.

* **Method (1) is restricted BY NAME to four elements**, which is why this
  is a short element list rather than a guess: "recommended primarily for
  saturated acyclic and monocyclic hydrocarbon substituent groups and for
  the mononuclear hydrides of silicon, germanium, tin, and lead". It
  replaces the "ane" ending, so silane gives `silyl`:

        NC[Si](C)(C)C          (trimethylsilyl)methanamine
        OCC[Si](C)(C)C         2-(trimethylsilyl)ethanol
        OC(=O)C[Si](C)(C)C     (trimethylsilyl)acetic acid
        Nc1ccc(cc1)[Si](C)(C)C 4-(trimethylsilyl)benzen-1-amine

  all previously `trimethylsilan-1-yl`. `silyl` is also the universal
  chemical prefix for a TMS group, so this is the one every reader expects.

  Phosphorus is deliberately absent from that list and keeps `phosphanyl`:
  it takes method (2), where the mononuclear exception drops the LOCANT and
  not the ending. The same page notes method (1) "is no longer applicable
  to boron prefixes". A pinned row holds the phosphorus case precisely so
  the contraction cannot spread to every mononuclear heteroatom.

Still not preferred, and recorded rather than forced: hexamethyldisiloxane
comes out `trimethyl(trimethylsiloxy)silane` where PubChem writes
`trimethyl(trimethylsilyloxy)silane`. The O-bridge assembly combines the
contracted stem with `oxy` and drops the `yl` between them. All three forms
round-trip on both gates, so this is a preference difference in a code path
that would need understanding first, not a defect to patch blind.

Benchmark: regression corpus **187/187, exact 92 -> 93**; held-out 40/40
unchanged; nothing structurally regressed.

## 2026-09-17 - the nesting order of enclosing marks cycles (D-034)

P-16.5.4 (BlueBookV2.pdf p. 134), verbatim: "When multiple types of
enclosing marks are required, the nesting order is as follows:
{[({[( )]})]}". Read from the inside out that is ( ) then [ ] then { } then
( ) AGAIN -- there is no deepest level.

* `_choose_brackets` returned braces for anything that already contained
  braces, commenting "already at the deepest level IUPAC defines", which
  produced `{...{...}...}`. P-16.5.4.1.5 addresses exactly that: when the
  order "results in consecutive enclosing marks of the same level, the next
  level of enclosing mark is used".

* **The Blue Book ships its own test vector**, Fig. 1.3: a six-step chain
  built one enclosure at a time, whose step (e) encloses a `{...}` prefix in
  PARENTHESES. That single row is the whole defect, and it is now pinned in
  `tests/test_namer_enclosing_marks.py` along with the other five.

* **The exemptions matter as much as the order.** P-16.5.4.1.2 ignores
  square brackets that are part of a parent structure -- ring fusion, spiro
  fusion, ring assembly, von Baeyer -- and P-16.5.4.1.1 ignores the
  parentheses of added indicated hydrogen. The old code used plain character
  membership, so `1,4-dioxaspiro[4.5]decan-8-yl` counted as a level and came
  out `N-{1,4-dioxaspiro[4.5]decan-8-yl}-...` when it should be parentheses.
  Von Baeyer SUPERSCRIPT locants render as `0^{3,8}`, whose braces are
  notation rather than marks; three benchmark names contain them.

Six names fixed, three in each corpus:

    atenolol      2-{4-{...}phenyl}acetamide -> 2-(4-{...}phenyl)acetamide
    novel triazole sulfonamide, novel spiro amide
    cid55000, cid56000, cid58000

Conformance over the 227 benchmark names went from 8 violations to 2. The
two survivors come from other assemblers and are recorded rather than
patched here: omeprazole's two-word `... sulfoxide` form, which is a
functional-class-versus-substitutive defect (P-66) and wrong for a bigger
reason; and a tertiary-amine prefix path that emits `[(ethyl)]` -- a simple
prefix wrapped twice, where it needs no marks at all.

GETTING THIS WRONG TWICE IS THE PART WORTH READING. Two ad-hoc conformance
checkers written while fixing this were both subtly wrong, in opposite
directions. The first asked for a monotonically increasing level, which
flags the correct `(` around a `{`. The second compared each mark with its
ENCLOSING mark, which flags an `(oxo)` sitting several levels deep that
encloses nothing and is therefore correctly a parenthesis. The rule is about
how deep a mark's CONTENTS nest, not about what surrounds it. Either version
would have sent someone off to "fix" names that were already right, which
is why the committed test pins the book's examples rather than a checker's
output -- and why the stage-3 linter gets a frozen acceptance corpus before
it is allowed to gate anything.

D-030d earned its keep here. That row deliberately pinned the wrong
enclosing mark with a note that fixing the nesting rule would break it; it
broke, in this branch, which is how the follow-up was found rather than
forgotten.

Benchmark: regression corpus **187/187, exact 93**, held-out 40/40, nothing
structurally regressed and no name's meaning changed -- PubChem writes these
with brackets throughout, so its own strings cannot become exact matches.

## 2026-09-17 - the isotope hyphen depends on what follows (D-035)

P-82.2.1 (BlueBookV2.pdf p. 852): "Immediately after the parentheses there
is neither space nor hyphen, except that when the name, or a part of a name,
includes a preceding locant, a hyphen is inserted." The book's own PIN for
the plain case is `1,2-di[(13C)methyl]benzene`.

The engine keyed the hyphen off whether the ISOTOPE LABEL carried a locant,
which is a different question entirely, so any locanted label got a hyphen:
`(1-2H)-methanol`, `(1-13C)-methane`. The decision now looks at the part
that follows, and because that part does not exist yet where the label is
appended, it is deferred until the name is assembled.

The exception is why this is not just "delete the hyphen": an
indicated-hydrogen marker IS a preceding locant, so `(2-13C)-1H-indole`
keeps its hyphen and has a pinned row saying so.

Neither of the two corpus rows can become an exact match, and that is a
fact about the reference rather than the names: PubChem answers
`deuteriomethanol` and `carbane`, both of which discard the isotope
altogether -- which `build_corpus._trusted_pubchem_name` already documents
as a reason it drops ground truth. They are `PUBCHEM_NOT_PREFERRED`
candidates for the adjudication table.

Benchmark: 187/187 and 40/40 unchanged, exact 93, nothing structurally
regressed.

## 2026-09-17 - a retained name is not automatically a preferred name (D-036)

`retained_pins` asserted PIN status for 292 names while citing a rule for
31. 161 of the entries were harvested from OPSIN's name-to-structure
dictionary, where presence means a name can be READ -- a different fact
from IUPAC preferring it. This is the shape `KNOWN_LIMITATIONS.md` already
records for the triazole entry, where a test written from the table agreed
with the table.

Entries now carry `pin_status` with the evidence beside it, and
`benchmarks/naming/adjudication.toml` holds the quotations. The container
keeps its name for now; what changed is that it no longer asserts by
omission.

### Audited only where it matters, and only 22 entries

Instrumenting which names a retained plan actually WINS gave the scope: 55
of the 227 benchmark names come from a retained plan, but 33 of those come
from the ring table -- benzene, pyridine, furan, naphthalene, 1H-indole,
morpholine, oxolane, 9H-purine and the rest, nearly all genuine retained
PINs that must not be touched. Only 22 come from this registry.

The other 274 entries stay UNKNOWN and behave exactly as before. Refusing
them on no evidence is the mirror image of the original defect: the answer
to "asserted without evidence" is not "denied without evidence".
`tools/retained_name_audit.py` reports that backlog so it stays visible.

### Demoted, with the quotation that settles each

    butyraldehyde   -> butanal                       P-66.6.1
    chloroform      -> trichloromethane              P-61.3.4
    isobutane       -> 2-methylpropane               P-61.2.1
    triethylamine   -> N,N-diethylethanamine         P-66.4.1 (derived)
    trimethylamine  -> N,N-dimethylmethanamine ...   p. 98
    camphor         -> 1,7,7-trimethylbicyclo[...]   P-101.8.4
    caffeine        -> systematic                    (absent from the book)
    ibuprofen       -> systematic                    (an INN, absent)

P-61.3.4 is the cleanest of them, verbatim: "The retained names 'bromoform'
for HCBr3, 'chloroform' for HCCl3, and 'iodoform' for HCI3 are acceptable in
general nomenclature. Preferred IUPAC names are substitutive names."

### Two names I had filed the wrong way round

P-22.1.3 settles both, and neither matches intuition:

* **`toluene` IS a preferred IUPAC name** -- "Toluene and xylene are
  preferred IUPAC names, but are not freely substitutable". What is
  restricted is SUBSTITUTION, not the bare name. A sweep that demoted every
  retained name would have broken it, which is the argument for auditing
  entry by entry.
* **`1,4-xylene` is the PIN**, not `1,4-dimethylbenzene`: "xylene (1,2-,
  1,3-, and 1,4-isomers, PINs)". So PubChem is right on that row and the
  engine is not. Left OPEN: the registry has no xylene entry, so this needs
  one ADDED rather than a status changed -- the opposite direction from
  everything else here.

`mesitylene` sits in the same paragraph with a third status again -- general
nomenclature only, `1,3,5-trimethylbenzene (PIN)` -- and both engines
already give the PIN.

### Two vendored tests asserted camphor was a PIN, on a citation that is not
### about ketones

`test_retained_terpenes.py` is a careful module: it probed a dozen terpene
names, found that bornane, pinane and p-menthane are NOT PINs, and kept
them out of the curated ring table for exactly that reason. It made one
exception, for camphor, citing "Chapter P-66.6.3 and Table 28.1".

Checked: **P-66.6.3 is "Chalcogen analogues of aldehydes"**, and `camphor`
appears on exactly two pages of the entire book -- 641 and 1000 -- so it is
not in Table 28.1 either. Page 641 uses it as an alias for a systematic
PIN; page 1000, in P-101 (natural products, semisystematic by construction),
prints three names for this very structure:

    (1R,4R)-bornan-2-one / (+)-camphor /
    (1R,4R)-1,7,7-trimethylbicyclo[2.2.1]heptan-2-one

The third is what the engine now emits. The module's central finding stands;
its one exception rested on a citation that does not support it -- the same
failure as caffeine's P-31.1.3, in a different file.

### And dropping caffeine exposed the next defect

With the retained name gone, the systematic path emits
`1,3,7-trimethyl-2,6-dioxo-1H-purine`: the ring ketones become `oxo`
PREFIXES where the principal characteristic group should take the `-dione`
SUFFIX, which is why it is not PubChem's `1,3,7-trimethylpurine-2,6-dione`.
That is PCG assignment, the same layer as warfarin, and is pinned as
emitted (D-036o) rather than patched here.

Benchmark: regression corpus **187/187, exact 93 -> 97**; held-out 40/40
unchanged; nothing structurally regressed. Seven names changed, five of them
to exact. The eighth change is chloroform going exact -> equivalent, because
PubChem's own string for that row is the non-preferred one -- the single
clearest reason this benchmark cannot be scored on PubChem agreement alone.

## 2026-09-17 - two curated ring names were not the preferred ones (D-037)

Both verbatim, and both one-line data changes:

    p. 150 (Table 2.2) and p. 449   "1,2-oxazole (PIN)  isoxazole"
    p. 208                          "1-benzofuran (PIN)  benzofuran"

p. 211 adds that isoxazole, isothiazole, thiazole and oxazole, "although
permitted in general nomenclature, are not retained" as fusion parent
components, and p. 376 uses `(1-benzofuran-2-yl)phosphane (PIN)`.

Both were inconsistent with their own neighbours rather than with a rule
nobody had applied. The plain-oxazole entry in the same table already said
`1,3-oxazole`; `1-benzothiophene` and `1,3-benzothiazole` sit either side of
benzofuran carrying their locants. The `1-` is not decoration -- it is what
distinguishes 1-benzofuran from 2-benzofuran, and p. 208 lists both.

`isobenzofuran` came along for free and is now `2-benzofuran`, the other half
of that same line.

Benchmark: regression corpus **187/187, exact 97 -> 98** (benzofuran becomes
exact; sulfamethoxazole moves to the right ring name through the substituent
form, and its remaining difference from PubChem is the `benzene-1-sulfonamide`
locant, where the ENGINE is right -- p. 104 and p. 513 cite the locant
whenever another substituent is present). Held-out 40/40 unchanged.

## 2026-09-17 - the stereo-validation cache remembered two wrong things

`_validate_stereo_via_opsin` caches whether an R/S-bearing name parses, for
the life of the process. It was keyed on the name alone, while the answer
also depends on `strip_modes`; and it cached INCONCLUSIVE results. When
nothing parses, the pass cannot tell "no stripping rescues this name" from
"OPSIN cannot run" -- no JRE on PATH looks identical -- so one call made
without Java stripped the stereodescriptors and remembered it, and every
later call in the process returned the stripped name after Java became
available. Keyed on `(name, strip_modes)` now, and only a verdict OPSIN
confirmed is cached. Found by auditing every cache on the naming path; the
test that pins it fails under the old behaviour.

## 2026-09-18 - naming round 4: preference by the book's criteria, and parents the engine could not reach

Every target was settled against BlueBookV2.pdf BEFORE its code changed
(`benchmarks/naming/adjudication.toml`, schema 2: each rule quoted once with
its page, rows referencing it), and every fix carries a `D-0xx` row set in
`tests/test_namer_known_defects.py` -- the defect, generalisation rows, a
converse, and a negative control -- mutation-checked by reverting the fix and
watching the rows go red. D-038 to D-082. The commit messages carry the
detail; this is the map.

**Evaluation discipline.** The round-3 held-out set is now USED (its rows were
fix targets) and says so in `heldout.meta.json`. A fresh one, `heldout2.json`,
was drawn by the same filter before anything in the round was looked at,
hashed, and LOCKED: the stage tool refuses to load it outside
`--final-evaluation`, and a test fails if another script names it. Its first
draw admitted 15 rows because PubChem's 503s were skipped as missing records;
503s are now retried, and that draw was discarded unseen.

**The comparator (stage 5, D-038, D-041).** Plans are ranked by a typed key.
`LegacyScoreKey` wrapped the old float and was proved decision-identical on
both corpora (0 names and 0 winning hypotheses changed) before
`NomenclaturePreferenceKey` replaced it: declared tiers built from the same
components the float summed. Every reorder was enumerated. It found the
alphanumerical tie-break keyed on FG TYPE (every carbon prefix was "z", so
P-14.5.1's own printed example came out wrong), numbering compared as locant
SUMS, cid19000's fusion candidate generated and outranked, and naming methods
ranked by guesswork where P-52.2.4.1 decides fusion versus von Baeyer.

**Numbering (D-039..D-041).** An `[nH]` pins the tautomer, not the orientation:
uniquifying the ring match dropped carbazole's mirror numbering (held-out
cid4000 was numbered from the far ring) and the `1H-` of indol-2-yl. P-14.3.4's
locant-1 omissions applied to the charged renderers.

**Retained parents and the registry (D-042..D-044).** Phenol, aniline,
benzaldehyde and acetaldehyde are substitutable PINs; the xylenes were ADDED.
The registry gains typed evidence and applicability fields, and
`tools/retained_name_audit.py` FAILS CLOSED on impossible claims (a PIN backed
only by a parser, a whole-molecule-only name used as a parent). Eight names
were demoted, SUCCINIMIDE among them: this file had called it "a genuine PIN
with a correct P-66.2 citation"; the cited paragraph prints
`pyrrolidine-2,5-dione (PIN)` and forbids substituting succinimide.

**Principal groups (A5, D-045..D-058).** P-58.2's procedure for indicated,
added and hydro hydrogen, one planner instead of a guess per route (maleimide,
caffeine's `3,7-dihydro-1H-purine-2,6-dione`, pyrimidine-4,6(1H,5H)-dione);
15 hand-written ring-ketone entries corrected to it. Sulfonic esters by
functional class, C-bound N+ as the aminium suffix, P-44.1.1's count of
principal groups as its own tier (chloroquine's pentane-1,4-diamine), the
alcohol/phenol and amine families merged, diazonium as a suffix on its
carbon parent ("toluene-1-diazonium" did not parse).

**Serialization (A9, D-059..D-064).** Enclosing marks by form rather than an
allowlist; alkoxy contracted only for methoxy..butoxy and phenoxy
(`(acetyloxy)`, never acetoxy); locant order italic before numeral
(P-14.3.5 -- the code said the reverse and cited another rule); amido prefixes
by method (1); the one-substitutable-position rule; benzyl, anilino and
carbamoyl as preferred prefixes; carbamic acid's substituents unlocanted.

**Round 3's carry-overs (A10, D-065) and saturated rings (A8, D-066).**
Peroxides and disulfides by substitutive method (1); sulfoxides and sulfones
as `(methanesulfinyl)methane`; diacyl dihalides; the amine oxide's `N-`
locant. A saturated heteromonocycle takes its Hantzsch-Widman or retained
saturated name over a hydro form (P-31.1.4.2.4).

**Fused saturated parents (A7, D-067..D-074).** P-58.2 extended to
single-bonded suffixes and free valences, but only on atoms with no hydrogen
in the lowest-indicated-hydrogen mancude parent; P-14.3.4.5's omission of
hydro locants; anthrone; ring `carbo-` suffixes keep locant 1. A new
`ring_naming/fusion_locants.py` fills fusion carbons the ring table leaves
out (161 of 186 complete entries reproduced; the rest are table errors or
special numberings, which it declines). ELEVEN table locant maps were stored
inverted -- the dihydrofuran and dihydropyrrole named a different molecule --
and are fixed under a shape guard.

**Nitrogen cores and heteroatom centres (A6, D-075..D-082).** Substituted
hydrazides, amidines and guanidines take N/N'/N'' by role; one shared namer
for urea, thiourea, guanidine, carbamic acid and single-centre parents, with
a seniority gate and lowest-locant prime order; condensed guanidines as
imidodicarbonimidic diamides (metformin's relative had been a different
molecule); silanols, boron and pnictogen oxoacids, phosphanones (additive
"phosphane oxide" declined: P-74.2.1.4 makes the lambda5-phosphanone the PIN)
and diazenes. A primed numbered locant is `N'1`: OPSIN reads `N1'` as another
position, and held-out cid55000 came back a different molecule.

**Architecture (A11, A12).** One active strategy per call, in the cache key,
with every fallback construction site gone and a source scan against new
ones. The carve stamps each fragment atom with its origin and every prefix
entry carries that map, so a substituent's own numbering reaches a caller's
atoms (`fragment_origin`, `PrefixEntry.atom_origin`).

**Tests that were wrong, not the engine.** 25 vendored test files changed
this round (433 lines in, 87 out, most of it new rows); every expectation
that MOVED was moved to the form the book prints on a cited page, and
several had been written from a code comment's claim rather than from the
book. The vendored suite ended the round with 0 failures.

Benchmark: regression **187/187 round-trip throughout; PubChem verbatim 98 ->
101/187**; the used held-out set 40/40, verbatim 14 -> 16/40. The fresh
held-out result is in `BENCHMARK_HISTORY.md`. What is still open is in
`KNOWN_LIMITATIONS.md`, "Open after naming round 4".

## 2026-09-19 - naming round 5

**Atom ownership on the tree (N2).** The executor's plan-level "no silent
atom drop" check asked only whether the UNION of a plan's claims covered the
molecule, and it ran before the tree existed; round 4 dropped atoms twice past
it. `ownership.py` checks the TREE the substitutive executor is about to
return, at every recursion depth: every heavy atom owned by exactly one node
(parent, suffix group or prefix), a suffix owning only elements its form names
(round 4's "hydroxymethane" for trimethylsilanol), and nothing outside the
parent's connected component. `PrefixEntry.claimed_atoms` carries the
provenance, stamped from the plan assignment that produced each entry
(`ClaimingPrefixList`, so none of the 19 construction sites had to change).
Suffix FGs now record their SMARTS context atoms (`context_atoms`: the plain
`[#6]` of an amine's R or a ketone's two R), which is what the first
measurement needed -- all 30 double-owned levels on the tuning corpora were a
suffix counting its neighbours. Enforced in the app (a violating plan fails
closed, never emitting the name), strict under test. No name changed.

**General fusion nomenclature (N3).** A fused ring system with no retained
name was named by fusion only through one narrow route (a [1,3]-dihetero or
mono-hetero five-ring on a known base), which also chose the wrong parent
("furo[2,3-b]thiophene" for thieno[2,3-b]furan) and invented names
("selenolo[2,3-b]selenofuran"); everything else fell to a von Baeyer name or
none. Measured on the book's own P-25 examples: 13 of 125 ortho- and
peri-fused systems exact. Two new modules build the name the book's way:
`ring_naming/fusion_general.py` (component vocabulary -- Hantzsch-Widman
monocycles, benzo-heterocycles, the retained polycycles of Tables 2.7 and 2.8
with their traditional numberings -- P-25.3.2.4 parent seniority, first-order
attached components, fusion descriptors, P-25.3.8 omissions) and
`ring_naming/fusion_orientation.py` (the P-25.3.2.3 drawing -- every permitted
ring shape as the compass directions its sides face -- and P-25.3.3
numbering from it). The class is stated in the module and refused outside it
with a code; a refusal whose fusion name needs a second-order or multiparent
construction may not be answered by the older fusion route.

On the way: OPSIN "arylGroups" stems were read as whole ring names
("quinolizin", "arsindol"); a stem regains its 'e' where OPSIN's own fusion
prefixes show the parent has one. "naphthacene" is "tetracene" (p. 199). The
P-58 planner treats P, As and Sb as it treats N. Mirror numberings of one
fusion name travel together on one parent, so the suffix and prefixes choose
between them -- found by an atom-order permutation test, when the ring
atoms' order had been choosing.

The ring table's "1,3-benzodioxole" is general nomenclature: "Omission of
indicated hydrogen is also permitted in general nomenclature ... for example
1,3-benzodioxole, rather than 2H-1,3-benzodioxole" (P-25.7.1.3.1, p. 260).
It is now "2H-1,3-benzodioxole" by the table's existing pin_eligible swap. 31
vendored expectations moved with N3, each to the book's form and each
round-tripped: the old route's own tests pinned its names (no indicated
hydrogen on a dioxole CH2, "[1,3]dioxolo[4,5-b]benzene" for a benzo name,
naphthalene as parent over a dithiole), and three von Baeyer names were
pinned for systems P-52.2.4.1 gives fusion names.

The preference key gains `indicated_hydrogen_locants`, after the heteroatoms
and before the suffix, as P-14.4 (b) orders them (p. 74). Without it the ring
table's per-numbering variants were chosen on a substituent's locant
("4-chloro-3H-perimidine", where the PIN is 9-chloro-1H-perimidine). A parent
name that leaves the hydrogen out ranks below every name that states one,
not as the empty -- lowest -- set, which would have handed "9H-fluorene"'s
place back to the table's bare "fluorene". Nine vendored perimidine
expectations moved; no tuning-population name changed.

**Candidate generation (N4).** Three constructions the engine lacked, each
diagnosed first as the plan asked -- the bis-guanidine, methylenebis(phosphonic
acid) and the N'-acyl hydrazides were three mechanisms, not one:

* `multiplicative.py`, P-15.3 / P-51.3. A `MultiplicativePlan` type existed and
  nothing built one, so "phenoxybenzene" stood for 1,1'-oxydibenzene. The
  decomposition is read off the molecule's symmetry: a class of bonds whose
  ends fall in the same two symmetry classes is cut, and the cut must leave one
  linker and n identical units. The units must carry the senior parent, the
  linker no group as senior as theirs ("bis(phenyldiazenyl)methanone (PIN)
  [not 1,1'-carbonylbis(2-phenyldiazene)]"), and no unit is an alkane. Each
  unit is named once, carrying a marker where the linker was, so the engine's
  own numbering gives the linker the lowest locant; the unit is then cut out
  of the MARKED name, because reassembling it without the marker re-ran locant
  omission and wrote "diethanol" for "di(ethan-1-ol)". 22 of the book's PINs
  come out as printed. Declined with a reason outside the built class
  (substituted, ring-centred or unsymmetrical linkers; double-bonded units;
  Si-O-Si, which is a disiloxane chain).
* The P-44.1.2 senior-atom tier, `parent_senior_atom` in the preference key:
  "N > P > As > ... > Si > ... > C", which "is applied ... to choose between
  rings and chains" (p. 375) before ring over chain. Without it a flat ring
  bonus named "(hydrazinyl)benzene" for phenylhydrazine (PIN), and
  hydrazinecarboxamide, its N-substituted forms and hydrazinecarboxylic acid
  were all named on carbon. It also gives "2-(trimethylsilyl)pyridine" (N over
  Si). With it: "phenylhydrazine" drops its "1" (P-14.3.4 (b)), a carbamic
  acid or carbamate on a hydrazine N is refused ("not carbazic acid"), the
  hydrazide pattern admits a carbonyl whose other neighbour is a hydrazine N
  ("hydrazinecarbohydrazide (PIN)"), and "-C(=O)NHNH2" is "hydrazinecarbonyl".
  The ownership guard caught the tier's first draft: a hydrazide's own N-N was
  taken as the hydrazine parent of a "carbohydrazide" suffix, owning its
  carbonyl twice. That reading is now dropped at plan generation.
* Sulfamic acids: "sulfamic acid" (p. 703; "amidosulfuric acid" is the
  inorganic form) and "N-methylsulfamic acid", with the N-locant P-67.1.2.4.1
  cites -- derived, since the book prints no substituted sulfamic acid.

**The OPSIN registry gate and four retained parents (N5).** A name whose
RECORD came from OPSIN's parse dictionary -- the 1,824-name
`retained_names_from_opsin.json`, or one of the 174 registry entries copied
from it -- is emitted only when the registry types it with NORMATIVE_RULE
evidence (`engine.retained_gate_refusal`, the rule itself in
`data_loader.retained_record_refusal`). "fluorouracil" became
5-fluoropyrimidine-2,4(1H,3H)-dione, "triethanolamine" the multiplicative
2,2',2''-nitrilotri(ethan-1-ol), "tabun" a systematic name. The gate reads
where a record came from, never its spelling: azepane's SMILES carries
OPSIN's "hexamethyleneimine" in the registry and the engine's own "azepane"
is untouched. An audited demotion is a fact about a NAME, so it now binds
every table that spells it -- ring naming's curated table was handing out
"adenin-9-yl" and "hypoxanthine" as ring names after the whole-molecule
lookup had stopped, and once that was gated, OPSIN's ring vocabulary offered
"2-aminohypoxanthine" for guanine. Bare 7H-xanthine then had no name at all:
the oxo-on-mancude derivation waited for a ring mol it never reads, and now
gives 3,7-dihydro-1H-purine-2,6-dione.

Retained parents: "oxamide (PIN)" and "oxalohydrazide (PIN)" (pp. 644, 667),
N-substituted as "N1,N2-bis(cyanomethyl)oxamide (PIN)" (p. 653); "silicic
acid" and "disilicic acid" (pp. 698, 720) in the main-group oxoacid table,
with its esters and anions ("tetraethyl silicate", derived from p. 710).
Si-O-Si is the a(ba)n parent disiloxane (P-21.2.3.1): a new candidate for
every end-to-end alternating chain at standard valence ("chlorodisiloxane",
"disiloxanecarboxylic acid (PIN)", "methyldiboroxane", a branched siloxane
on its longest chain), and a heteroatom chain of an element that can also be
a one-atom centre now competes with that centre on P-44.3's length
("methyldisilane", "1,2-dimethyldiphosphane"). Boron had been excluded
because "OPSIN does not support polyborane parent hydrides"; OPSIN parses
"tetramethyldiboroxane", the book's own PIN (p. 731). A first draft named a
nucleotide diphosphate "1,3-dioxodiphosphoxanyl"; a P(V) is not an a-term
atom.

**Principal-group seniority and assignment (N6).** Four classes, each
measured first as candidate-absent or misassigned:

* Urea below the amides. "Amides from carboxylic acids, including formamide,
  are senior to urea" (P-66.1.6.1.1.5, p. 660), and the engine's amide
  patterns matched urea's carbonyl as a carboxamide, so every one of the
  book's five examples came out as a substituted urea ("N-(3-formamidopropyl)
  urea", which the book names only to reject). A carbonyl between two
  acyclic nitrogens, neither bonded to another N, is now a urea group -- a
  ring or hydrazine N keeps it a carboxamide ("piperidine-1-carboxamide",
  "hydrazinecarboxamide") -- and the urea route steps aside for any amide.
  The ("urea", "amine") subsumption had been in the table with no urea group
  to act for it.
* A chain-terminal amidine is "amino" + "imino" (P-66.4.1.3.2). The demoted
  amidine was a "carbamimidoyl" prefix whose carbon the chain also named, so
  "4-carbamimidoylbutanoic acid" was a WRONG MOLECULE, one carbon too long,
  and its N-substituted relatives either that or an inverted seniority. The
  ownership guard did not see it: the prefix claimed its nitrogens and its
  name carried the carbon. "methyl 4-(dimethylamino)-4-(ethylimino)butanoate
  (PIN)" is now as printed.
* Silanols: the single-centre route counts other alcohols (P-44.1.1) before
  preferring Si (P-44.1.2) instead of declining on any, takes any singly
  bonded substituent ("(methylamino)silanetriol (PIN)", p. 748), and names a
  bare silanol. Widening the alcohol pattern to Si-OH was tried first and
  produced "2-hydroxyethan-1-ol" for a silanol-alcohol: reverted.
* Hydroxamic acids are N-hydroxy amides ("N-hydroxycyclohexanecarboxamide
  (PIN) (not cyclohexanecarbohydroxamic acid)", p. 587), N-substituted ones
  included; the OH oxygen is the prefix's, which the ownership guard
  enforced on the first attempt.
* Enols take the -ol suffix ("3,4-dihydronaphthalen-1-ol (PIN)", p. 535).

**Numbering (N7).** A hydro-named parent's orientations reached the
preference key with no hydro locants, so two of them tied and the first
enumerated won -- "1,2,5,6-tetrahydropyridine-4-carboxylic acid" (and
MPTP) for 1,2,3,6-. P-14.4 ranks '(e)(i) ... hydro/dehydro prefixes ... and
ene and yne endings' together, after suffixes and added hydrogen and before
detachable prefixes (pdf pp. 74-75). The retained hydro route now records
the atoms its hydro prefix covers (`NamedParent.hydro_atoms`), and the
strategy ranks their locants under each plan's numbering.

The same tie was behind "(1,6-dihydropyridin-1-yl)acetic acid" for
"pyridin-1(2H)-yl (preferred prefix)" (p. 479), which round 4 had put down
to the free valence missing from the preference key. The candidate was
generated all along; the prefix tier broke the tie in the wrong direction.
Every N7 case is also named from shuffled atom orders, a Kekule SMILES and
randomly rooted SMILES (`tests/test_namer_numbering.py`).

**Serialization (N8).** Every candidate was classified first -- lexical
spelling, retained-prefix status, PIN preference or prefix construction --
and only the five lexical ones were built, because only they can leave the
candidate, its interpretation and its ranking untouched. The stage artifact
confirms it: 5 names changed across the three tuning populations and 0
winning hypotheses.

* A prefix of ONE stem ending in "ylidene" is simple, so P-16.5.1.3 leaves
  it bare: "2-sulfanylidene-1,3-thiazolidin-4-one", "3-propylidene-2-
  benzofuran-1(3H)-one". That rule encloses a prefix carrying its OWN locant
  ("propan-2-yl"), not the parent's, which a blanket "-idene" entry had been
  doing. "phenylmethylidene" has two stems and stays enclosed.
* Unenclosing them let a prefix/parent junction reach the elision rule for
  the first time, which emitted "2-methylidenoxolane". Elision belongs at a
  stem/suffix junction: "2-sulfanylideneoxolane-3-carbonitrile (PIN)".
* P-16.5.1.3.1: "the first cited substituent never has enclosing marks
  unless it includes a locant" -- "[hydroxydi(methyl)silyl]acetic acid". The
  legibility exception for ether prefixes was catching "hydroxy", which is
  the O-H prefix, not an ether one.
* P-14.3.4.5, built for an all-carbon chain or ring and for an a(ba)n chain:
  "hexamethyldisiloxane", "hexachloroethane",
  "tetramethyldiboroxane (PIN)" (p. 731), and "hexachlorobenzene" and
  "octamethyltrisiloxane" with them. Two different substituents are not "in
  the same way" and keep their locants. The engine supplies the structural
  half (no parent position still carries hydrogen); assembly adds the naming
  half (one prefix name accounts for all of them). The first draft tested only
  "no atom carries a hydrogen", which is weaker than "every substitutable
  position is substituted" -- an aromatic ring N or a fusion carbon passes it
  for free -- and the vendored suite caught three names it made ambiguous or
  wrong: 1,5-dimethyl-1H-tetrazole, a hexamethyl cyclotriphosphazene, and
  1,1,2,2-tetramethylhydrazine. Unsaturated parents are out for want of a
  printed example.
* P-63.2.2.2's contracted alkoxy prefixes are "fully substitutable", and the
  test for a ring asked whether the FRAGMENT held one anywhere rather than
  whether the ATTACHMENT atom was in a ring -- so an acyclic chain carrying
  a distant aryl ring was refused the contraction (h2cid53500).
* P-66.3, verbatim: "pentanehydrazide ..., not pentanohydrazide". The
  connecting 'o' stays wherever the stem is not a parent hydride's --
  "acetohydrazide (PIN)", "benzohydrazide (PIN)", "pyridine-4-carbohydrazide".

Classified OUT of this stage, with the reason recorded: tert-butyl (a
retained prefix, and it moves the alphanumerical citation order, so it is
not ranking-neutral), Boc, "propane-2-sulfonyl", "ethanethioamido",
"phosphoryl" and the substituted carbamimidoyl prefix.

**The usable registry backlog is audited (N9).** Alex's decision of
2026-09-19 scoped it to the 75 entries the OPSIN gate lets through that
carried no typed status. Each now has one, with the rule quoted: 33 PIN
(azulene, 9H-fluorene, carbonic acid, formamide, hydrazine, hydroxylamine,
ammonia, chalcone, the 20 amino acids of Table 10.4, ...), 6 demoted because
the book prints another name as the PIN (acrylamide, butyramide,
propiononitrile, citric acid, N,N-dinitromethanamine, and `pyrrolizine`,
whose PIN is `1H-pyrrolizine`), and 36 demoted because the book never prints
the name at all. 0 names changed in the three tuning corpora, as the N5
report predicted for entries no corpus reaches.

Three entries were REMOVED because they bound a name to the WRONG
STRUCTURE: "L-proline" on D-proline, "L-threonine" on L-allothreonine,
"L-isoleucine" on L-alloisoleucine, two of them carrying `source:
"bluebook"`. Each name had a second, correct entry, which is the only reason
the audit noticed. Typing the wrong one would have printed "L-proline" for
D-proline with a page citation attached. Two tests now check what nothing
checked: every registry name is parsed by OPSIN and must denote the
registry's own structure (exact where OPSIN fixes the stereocentres; three
nucleobase tautomers are listed as visible exemptions), and no name may be
bound to two structures. The gate's vocabulary test was rewritten to state
the rule it always meant -- a vocabulary name passes only where the registry
types it with normative evidence, which "ammonia" now is.


## 2026-09-20 - naming round 6: amides and esters of cyanic acid

Found by the functional-groups v3 cross-check, which showed the engine
perceiving methyl thiocyanate as a plain nitrile. Measured, all before any
change: `NC#N` was `aminomethanenitrile` where the Blue Book retains
`cyanamide (PIN)` (P-66.1.6.2, pdf p. 663), `CCN(CC)C#N` was
`(diethylamino)methanenitrile` for the book's `diethylcyanamide (PIN)`,
`CC(C)SC#N` was `[(propan-2-yl)sulfanyl]methanenitrile` for the book's
`propan-2-yl thiocyanate (PIN)` (p. 629), and `N#CSCCC(=O)O` was
`3-(cyanosulfanyl)propanoic acid` for `3-(thiocyanato)propanoic acid (PIN)`
(p. 604). The molecules were right in every case; the names were not the
preferred ones.

Four changes, each pinned by D-094: `cyanamide` is a registry entry typed PIN
with the page quoted, and a substituted one is named by
`_name_cyanamide_functional_parent` on the shared N-core builder with no
locant (the N is the only position, as in the book's own examples); an O- or
S-bonded cyano group is `cyanato` / `thiocyanato` (a subsumption entry over
`nitrile`, which was logged as "Unknown FG overlap ... Treating as ambiguity"
and won), named as an ester, `_name_cyanic_ester_functional_parent`; the
`cyanato`/`thiocyanato` PREFIXES replace `cyanooxy`/`cyanosulfanyl`, and
`thiocyanato` is enclosed as the book prints it, by an EXACT match because
`isothiocyanato` contains the word and is printed bare.

Stage artifact `r6-cyano`: 0 names changed on regression, heldout and
heldout_v2, which contain no cyano compound. `heldout_v3` was not consulted.


## 2026-09-20 - naming round 7: acid anions, and the charged classes the corpora never contained

Found by the round-5 integration run, not by any corpus: a carboxylate or sulfonate beside a neutral OH, NH2 or
SH was named as if that group were principal. Salicylate was `2-oxidooxomethylphenol` (a different molecule,
withheld by the round-trip gate); lactate was `1-oxido-1-oxopropan-2-ol` (round-trips, wrong, nothing catches it).

**The cause was a missing owner between two guards.** `_classify_acidic_anion` deferred every "mixed charged +
neutral" case to plan search, and plan search's `_carved_acid_anion_sites` excluded carboxylate as "handled by the
dedicated path". Nothing claimed it. `charge_perception.acid_anion_route` is now the one function both routes ask
(P-41: anions outrank acids, and everything below an acid is a prefix): `classifier` for a pure anion or one beside
groups junior to an acid, `carved` for another neutral acid or a nitro group, None for a genuine other ion. The
carved route's acid FG is taken from perception on an index-preserving neutral view, and its PCG restriction now
covers the whole anion-variant family for an acid FG.

**Also fixed, all from a 108-row panel of charged species built by class** (`benchmarks/naming/charged_panel.toml`,
frozen, with its baseline and adjudication beside it):

* a zwitterion with one carboxylate and one NEUTRAL COOH was named as the dianion, a wrong molecule from a route
  that owned the site: in ANION mode the suffix now sits only on the charged instances of a type that has both;
* a zwitterion with a NEGATIVE net charge (glutamate and aspartate at pH 7) had no owner, because perception sees a
  charged carboxylic acid only when the charges cancel: the carved route takes it (`2-azaniumylpentanedioate`);
* the retained anion names the book prints (`methoxide`, `ethoxide`, `propoxide`, `butoxide`, `tert-butoxide`,
  `phenoxide`, `glycinate`), in the curated whole-molecule table; the chiral amino acids are deliberately NOT there;
* an amide anion is an acyl group on the parent anion `azanide` (`acetylazanide`, pdf p. 810);
* identical organic `-ate` anions in a salt take a multiplying prefix (`calcium diacetate`, `bis(...)` for a
  substituted one), while `disulfate` and `diphosphate` stay unmultiplied because they are different ions.

**Measured against the frozen baseline:** wrong molecules 13 to 0, non-preferred names 42 to 9, exact 45 to 90,
ownership holes 47 to 0 (two phosphorus-acid rows are a DECLARED unsupported edge). The stage artifact changes 0 of
307 names against the round baseline at every stage; the vendored suite is 4,515 passed, the default naming set
2,907 passed. D-095 to D-099 hold 79 rows, each red before its fix, with converses that differ by reason.

Two instrumentation hooks, neither of which changes a result: `classify_charges(claims_out=...)` and
`diagnostics.record_route`, which is what let `perception/charge_ownership.py` compare the routes that would claim a
site with the route the engine actually took. That comparison found a fourth owner the static model had not heard of
(the curated inorganic table answers first, so `carbamate` was never a hole).

## 2026-09-21 - naming round 8: polyacids, guanidines, azoles, and what ordinary compounds showed

The plan was four workstreams and one carried-over wrong structure; a limitations pass then fixed the defects its own
probing found. Every fix has D-rows (D-100 to D-129, 337 rows, each red before its fix, with converses that differ by reason),
a mutation check with the equivalent mutants written into the code, and its own commit; every stage ran
`tools/naming_ref_compare.py` against its predecessor with a manifest of the changes it expected.

**Planned work.**

* **W1, polyacids.** The chain choice for three or more C-anchored suffix groups (P-65.1.2.2.1, pdf p. 579) is an exo-skeleton parent
  candidate (`_with_exo_skeleton_candidates`) that the generator never offered, so `2-hydroxypropane-1,2,3-tricarboxylic acid`,
  `pentane-1,3,5-tricarboxylic acid` and `ethane-1,1,2,2-tetracarboxylic acid` are named as the book prints them. The classifier route
  gained a SITE-LEVEL charge ledger (`_balance_the_charge_ledger`): every acid group on that route is a deprotonated site, so a neutral
  `carboxy` word there is `carboxylato`, and the citrate trianion is `2-hydroxypropane-1,2,3-tricarboxylate` (a wrong molecule before).
* **W5, the one wrong structure of round 7's fresh set:** an isothiourea whose demoted prefix was serialized without the enclosure
  P-16.5.1.3.1 requires (`[amino(sulfanyl)methylidene]amino`); the enclosure rule applies to a substituent's own prefixes too.
* **W2, condensed guanidines and ureas** (P-66.1.6.1.4, P-66.4.1.2): `diimidotricarbonimidic diamide`, `2-imidodicarbonic diamide`,
  the n >= 5 skeletal-replacement names (`3,5,7-triimino-2,4,6,8-tetraazanonane-1,9-diimidamide`, unsubstituted chains only, guarded),
  and the metforminium and biguanidium cations (a wrong molecule and a dication name for a monocation).
* **W3, protonated azoles and cations:** the ring carve keeps a protonated nitrogen a target (`1H-imidazol-3-ium`, `1H-benzimidazol-3-ium`,
  `1H-pyrazol-2-ium`, saturated protonated rings get their retained names), a ring cation outranks every uncharged suffix
  (`_ring_cation_locants` joins the suffix tier), tetrazolium and N-oxide cations, and the salt route for a net-positive component that
  holds a carboxylate (lysinium, histidinium).
* **W4, the round-5 open list:** the imide parent (`N-acetylbenzamide`), N'-acyl hydrazides and a hydrazide never ranked above an acid
  (`3-hydrazinyl-3-oxopropanoic acid`), and pseudoketones (P-64.3.2): a carbonyl on a ring, azo or silicon heteroatom is 'one' (the
  group definitions gained `context_indices`, a declared heteroatom root of a substituent that the group does not claim).

**Limitations pass, each a class no corpus contained.** The `e` of `ene`/`yne` elides before `amide` and `amine` (`prop-2-enamide`); an
alkoxy on a nitrogen is `methoxy` (`_contracted_alkoxy`); an amide or amine whose nitrogen carries an alkoxy is an amide or an amine
(four group definitions; the azinite generator declines a nitrogen with no oxo); a carbonyl between two ring nitrogens is a pseudoketone;
nitrate and nitrite esters and acyclic carbonic diesters are esters (`compute_nitric_ester_name`, `compute_carbonic_ester_name`); an acyclic
onium cation outranks the groups beside it (`_onium_centre_band`); a mixed-class polyanion is owned by the carved route with `sulfonato` and
`oxido` prefixes; two adjacent acyclic ketones are a dione; the acyl prefix of a ring-nitrogen amide is `piperidine-1-carbonyl`.

**Other.** `RoundTrip.TAUTOMER` (a name that reads back as another tautomer is shown, not withheld: `docs/ARCHITECTURE.md`, dated 2026-09-21);
`derived_name_for_structure` raises on an embedded `NAMING ERROR`; the multiplicative route declines instead of crashing on a half-molecule that
will not sanitise (carbonyldiimidazole); a pyrene/perylene/phenalene-type interior locant in the former CAS form is a DECLARED deviation
(`benchmarks/naming/known_deviations.toml`, guarded). The engine's own tests: vendored suite 5,195 passed; the default naming set and the D-table
1,057 passed with 14 expected failures (the open rows). See `KNOWN_LIMITATIONS.md` ("Open after naming round 8") for every open row and
`BENCHMARK_HISTORY.md` for the measurements.

## 2026-09-22 - naming round 9: a source-backed battery first, then a ledger of 13, 9 fixed

Round 9 ran an instruments stage BEFORE any fix: a Blue Book PDF harvest (1129-row tuning population, `bluebook_tuning.json`),
an ordinary-compound battery (`battery_r9.toml`, 306 rows: dipeptides, salts, dyes, reagents, sugars, vitamins, ChEMBL drugs),
and a 2000-row frequency census. 13 findings were admitted into a hash-frozen ledger (`admissions_r9.toml`) in one step at the
end of that stage; the guard (`tests/test_admissions_r9.py`) checks item count against a declared cap and set-immutability,
never a hardcoded number -- "never do those hardcoded guards again, they don't serve that much of a function" (Alex,
2026-09-22), after which the check was rewritten from `if slots != 8` to a structural validation. Three of the plan's eight
seed hypotheses (a charged acid substituent, a ketone-parent enclosure, N,N-guanidinium) were RULED OUT by live testing and
are not in the ledger -- the instruments stage doing its job.

**9 of 13 admitted items fixed, each own commit, each verified via OPSIN round-trip and a stage comparison against the whole
1129-row Blue Book tuning population showing 0 structural regressions and only its own admitted rows changed:**

* **carbodiimide** (D-130, PARTLY): `multiplicative.py`'s `_name_decomposition` checks `_linker_has_carbonyl` for a C=O in a
  multiplicative linker (P-15.3.3.2.2) but had nothing for a C=N; DCC named as a saturated `1,1'-[methylenebis(azanediyl)]
  dicyclohexane` instead of the carbodiimide. New `_linker_has_imine` declines the same way; the engine falls back to a
  structurally correct substitutive name. Reaching the printed PIN ("dicyclohexylmethanediimine", P-62.3.1.4) needs imine FG
  perception, which is empty (`Perception(mol).fgs.detected_fgs`) for this structure in every context tried, not only the
  multiplicative one -- stays open.
* **carbamimidoyl-locant** (D-131): `engine.py`'s `_role_primes` assigned N/N' primes by chemical role alone, so two
  carboximidamide instances at the SAME parent position collided onto one prime pair; OPSIN read both substituents as the
  same group. Instances sharing a position are now ordered by anchor atom index, each later one shifted two more prime marks.
* **naphthalene-ring-drop** (D-132, no PIN claimed): `_divalent_linker`'s shortest-path walk between two multiplicative
  attachment atoms took the direct one-bond ortho route across a fused ring, letting the WHOLE other ring pass the existing
  `_in_benzene` check (which only asks "is this atom part of SOME lone benzo ring", true for every atom of a fused system) as
  merely "off the path, and aromatic" -- silently dropping 4 of naphthalene's 10 ring atoms. New `_fused_ring_count` declines
  whenever the linker's skeleton spans more than one SSSR ring; verified with converses that a SINGLE non-fused ring and a
  peri-fused attachment geometry both still work correctly.
* **sulfinyl-bromide** (D-133, wrong molecule -> honest failure): the `{R}sulfonyl`/`{R}sulfinyl` substituent shortcut in
  `engine.py` assumed S carries exactly one substituent beside its oxo oxygens; a hypervalent S (=O)(=N-)(Br)(N<) let the
  shortcut silently keep whichever neighbour `GetNeighbors()` reached first and drop the rest -- both the bromine and the S=N
  double bond vanished. New `_sulfonyl_sulfinyl_has_single_substituent` declines when S has more than one non-oxo substituent;
  no route exists yet to NAME a sulfinimidoyl/sulfonimidoyl halide, so the result is `RoundTrip.PARSER_FAILED`, an honest
  failure instead of a plausible-looking wrong structure.
* **phosphine-oxide-trihydrazide** (D-134, no PIN claimed): `_linker_name` strips a terminal oxo atom from a multiplicative
  linker's "skeleton" before naming it (needed so the oxo belongs to its own ketone/carbonyl component), but nothing checked
  whether a P=O being stripped should have blocked the construction the way a C=O or C=N already can -- a P(V) phosphine
  oxide named as a trivalent P(III) "phosphanetriyl". New `_linker_has_phosphine_oxide` mirrors the carbonyl/imine checks;
  `_PHOSPHINE_OXIDE` is a documented local constant since no functional-group entry exists to measure a real seniority from.
* **peptide-acyl-naming** (D-135, target P-103.3.2): new module `perception/fg/peptide_acyl.py`, a closed table of the 20
  proteinogenic amino acids (exact canonical structure, stereo included, built from OPSIN-verified retained names) matched
  against a dipeptide's cut amide bond; on a match, emits the retained acyl-plus-parent form ("glycylalanine", the book's own
  worked example, verbatim) instead of fully systematic substitutive nomenclature. Also handles proline as the C-terminal
  residue (a tertiary amide, H=0, since proline's ring N is already secondary before acylation) as a second base shape beyond
  the open-chain one. 14/20 of the battery's dipeptide rows now reach the retained form; the other 6 all involve threonine or
  isoleucine, whose battery-generated SMILES specify only the alpha-carbon stereocentre, and the module correctly declines
  rather than guesses the unspecified diastereomer. D-027z (round 4's fix) is documented as SUPERSEDED, not regressed: a
  plain natural-amino-acid dipeptide's retained form now correctly outranks the systematic style round 4 picked before this
  convention existed in the engine.
* **charge-alkynyl-dianion** (D-136, no PIN claimed): `_classify_alkynyl_anion` (charge_perception.py) covered the mono-anion
  `[C-]#C` only; the symmetric dianion `[C-]#[C-]` has no neutral carbon at all, so the mono-anion gate correctly declined
  and nothing claimed the shape, dropping both charges to plain "ethyne". Extended to detect and pre-cook `"ethynediide"`.
* **charge-phosphide-anion** (D-137, target P-73): no classifier existed for phosphorus-centred anions at all, unlike carbon
  and nitrogen. New `_classify_phosphide_anion` / `_render_phosphide_anion` reach the printed PIN
  ("1-phosphabicyclo[2.2.2]octan-1-uide") using the same "name as substituent, strip 'yl', append suffix" technique as
  `_render_simple_carbon`, with a phosphorus-specific neutralization (`_neutralized_site_changes`) that REMOVES the anion's
  own H rather than keeping it, and suffix "uide" (a skeletal-replacement parent takes the P-73 linking "u"). **Gated to RING
  phosphorus only**: a first version also claimed an ACYCLIC phosphide (`C[P-]C`, "dimethylphosphanide") that was already
  named correctly through a different, pre-existing route, and rendered it wrong (`dimethylphosphan-1-uide`) -- caught by the
  stage comparison against the tuning population before the commit, fixed with the ring gate, pinned as a converse test.
* **charge-imine-anion** (D-138, no PIN claimed): a gap between the amine-anion and amide-anion classifiers, neither of
  which covers an imine-type nitrogen anion (the amine-anion classifier's own gate requires a SINGLE N-C bond and correctly
  declines an imine's double bond). New `_classify_imine_anion` / `_render_imine_anion` mirror the amine-anion pair exactly,
  plus a new `("imine", OutputForm.ANION): "iminide"` SUFFIX_VARIANT_TABLE entry (assembly.py) mirroring `"amine"`/`"aminide"`.

**4 items deferred to round 10, each already diagnosed** (recorded in `KNOWN_LIMITATIONS.md`, "Open after naming round 9",
not re-opened as new findings): the carbamimidate-oxime-swap prefix-bracketing ambiguity (fix identified, deferred for its
regression risk across all substituent naming); methylene blue's phenothiazine numbering (phenothiazine is registered in
`ring_naming/fusion_general.py`'s `POLYCYCLES` for automorphism matching but has no `_TRADITIONAL` atom-mapped override,
unlike its anthracene/acridine/xanthene analogues); fluorescein's spiro-xanthene numbering (a DIFFERENT defect from
phenothiazine's -- xanthene itself IS correctly in `_TRADITIONAL`, so the bug is in how `spiro.py` numbers it combined with
its spiro partner, not yet isolated); and a polycarbocation needing the multiplicative and charge-perception machinery to
work together, which no existing pattern in the codebase does yet.

## 2026-09-22 - naming round 10: closing all 4 deferred items, and each one deeper than round 9's own diagnosis

Round 9's own diagnoses turned out to be starting points, not final answers, for three of the four items --
each traced further before any fix was written, and each landed somewhere more precise than what round 9
recorded.

* **phenothiazine-dye-locant** (D-139, D-140): round 9 diagnosed this as a missing `_TRADITIONAL` entry for
  phenothiazine in `fusion_general.py`. That diagnosis was incomplete -- adding the entry (verified correct
  against OPSIN as a structure oracle: `10-methyl-10H-phenothiazine` places the methyl on N,
  `phenothiazin-5-ium` protonates S) had ZERO effect on methylene blue's actual output. The real bug is a
  THIRD function, `ring_naming/retained_lookup.py`'s `_build_numbering_from_atom_locants`: its bond-generic
  substructure-match fallback (built to recover a curated ring's numbering when a substituent shifts the
  Kekule pattern) was gated to require every ring atom aromatic, including the N/S bridge -- non-aromatic on
  the isolated curated-key SMILES, but aromatic in methylene blue's actual extended-conjugation form. Fixed by
  relaxing the gate to "every CARBON aromatic". Engine now emits
  `[7-(dimethylamino)phenothiazin-3-ylidene]di(methyl)azanium chloride` for methylene blue, matching PubChem's
  own name verbatim. Phenoxazine shares the identical defect and fix, proven by direct testing.
* **spiro-xanthene-dye-locant** (D-141): round 9 correctly noted xanthene's own `_TRADITIONAL` entry is
  right, unlike phenothiazine's gap. What it hadn't isolated: `data_loader.py`'s `_RING_CURATED_SMILES` entry
  for xanthene covered only 9 of its 14 real ring positions -- harmless for a bare or substituted xanthene,
  but `spiro.py`'s numbering-combination gate (`len(atom_to_loc) == total_atoms`) never passed for
  fluorescein with 5 positions missing, so the combined numbering came back empty and substituent locants
  fell through to a generic, UNPRIMED, out-of-range walk. Fixed by completing the table with the four fusion
  positions and the bridge oxygen's own locant, derived from this table's own bond topology against
  `fusion_general.py`'s already-verified numbering. Engine now emits
  `3',6'-dihydroxyspiro[1,3-dihydro-2-benzofuran-1,9'-xanthene]-3-one` for fluorescein, matching its real
  IUPAC name exactly -- including a second latent defect (the lactone's own locant) fixed as a side effect.
* **charge-polycarbocation**: `_classify_polycarbon_charge` already existed and already covered this exact
  multi-charged-carbon shape, but its guard checked the WHOLE MOLECULE for any aromatic atom and any
  non-single bond rather than the charged atoms' own -- two saturated isopropyl cations attached to (not part
  of) a benzene ring tripped the guard on the ring's aromatic bonds. Narrowed to the charged atoms' scope; the
  classifier now engages and claims both charges, but no renderer composes a name for two independently-
  attached substituent cations on a shared aromatic parent yet -- a genuinely different shape from the
  linear-chain cases the renderer was built for. Per this project's own "refusal guard", the engine now RAISES
  instead of falling through to the wrong neutral name, converting the admitted wrong-molecule defect into a
  visible, honest failure (the same outcome class as D-133). PubChem's own name for the exact structure is on
  file (`bb-db0d904b9c97`, "2,2'-(1,3-phenylene)di(propan-2-ylium)") for whichever future round builds the
  render-side machinery.
* **carbamimidate-oxime-swap** (D-142): round 9 diagnosed "a prefix-bracketing ambiguity" and correctly
  deferred it for its regression risk. Diagnosis confirms the description exactly, and more: the engine's
  internal tree was right the whole time (methoxy and hydrazinyl, both correctly on the methanimine carbon)
  -- the wrong OUTPUT STRING left the trailing "methoxy" unbracketed after "(hydrazinyl)"'s closing paren, and
  OPSIN's grammar read the adjacency as one nested substituent instead of two siblings, a real wrong molecule
  once parsed back despite the engine's own tree never being wrong. No existing enclosure rule covered a
  carbon-centered one-carbon STANDALONE parent with a non-leading "-oxy" prefix (the closest two rules are
  each out of scope for a different reason: one fires only in SUBSTITUENT form for a different prefix class,
  the other only for heteroatom-CENTER parents). Round 8's own ketone-parent check missed this shape entirely
  because it tested with "phenyl" (no adjacency ambiguity) and because a ketone+"-oxy" case sidesteps the
  whole construction via an ester/carbamate route an imine lacks. Fixed by bracketing a non-leading "-oxy"
  simple prefix on any one-carbon chain parent, any output form -- a narrowly new rule. A second, independent
  instance of the exact same bug (methanamine, not methanimine; a different prefix pair) was found during
  diagnosis and fixed as the same side effect, pinning that the rule is general rather than a methanimine
  patch.

**Discovery-only extension of round 9's B3 frequency census** (no fix attempted; recorded in
`KNOWN_LIMITATIONS.md`, "Open after naming round 10"): 6 of the round 5-8 backlog's still-open shapes measured
against the same frozen 2000-structure sample. Two clear the admission threshold by a wide margin (a
ring-nitrogen acyl on a chain parent at 5.3x threshold, a multiparent fusion hub at 2.3x) -- real,
reproducible evidence where round 8's own notes said only "found by probing, not investigated". Four are
genuinely rare (0/2000): an a(ba)n Si-NH-Si chain, a symmetric 1,2-diketone (benzil), a diacyl peroxide, a
xanthate ester.

**Process note.** Every fix in this round followed the same routine: D-rows red first, converses that differ by reason, a
mutation check with the equivalent mutants written into the code, a stage-comparison run against the whole 1129-row Blue
Book tuning population BEFORE the commit and never chained to it, one commit per item. That discipline caught the
phosphide-anion regression above BEFORE it ever reached a commit -- the stage comparison is not a formality.

## 2026-09-23 - naming round 11: two fixes, two backlog rows already resolved, one re-diagnosed deeper

Re-verified every candidate directly against the current engine before admitting or dropping it -- the same
discipline round 9 applied to its own seed hypotheses. Two of five candidates this round looked at were
already fixed by other rounds' general work, never reflected back into `KNOWN_LIMITATIONS.md` until now.

* **ketone-parent enclosure** (D-143): `assembly.py`'s `_assemble_substitutive` had two existing one-carbon-
  parent P-16.5.1.3.1 enclosure rules, but neither reached a one-carbon KETONE parent in STANDALONE form --
  round 9's own re-test of this shape (F5) used a single ring substituent, which needs no enclosure at all,
  so it was ruled out without finding the actual gap (two DISTINCT ring substituents).
  `(morpholin-4-yl)phenylmethanone` left its second, simple "phenyl" prefix unbracketed. Fixed by mirroring
  the existing heteroatom-center block, scoped to a ketone's own `suffix_groups` base_form ("one"). Severity
  C -- OPSIN parses the unbracketed form too -- but the single most common open shape in the whole backlog,
  measured at 8.4% of the census.
* **carbamimidoyl N'/N,N split** (D-091v, moved from OPEN): the existing "N'-substituted carbamimidoyl"
  special case required the amino N to be a bare, unsubstituted NH2, so a substituted amino N
  (`4-[(dimethylamino)(ethylimino)methyl]benzoic acid`) fell through to the generic recursive path instead
  of the book's own printed form (p. 676, verbatim: `4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid`).
  Generalized to carve 0/1/2 substituents off the amino N too, but gated to require the imino N ALSO
  substituted before firing: an amino-only-substituted, imino-bare fragment round-trips via OPSIN in
  isolation, but is genuinely APPEARS_AMBIGUOUS when the same shape attaches directly to a GUANIDINIUM
  parent instead -- exactly the shape D-103a/c's metformin-cation fixture already chose the decomposed form
  for, on purpose. A first version without this gate regressed both D-103 rows; caught by the known-defects
  suite before commit, kept as permanent non-regression tests.

**Two backlog rows re-tested and found already resolved**, fixed as side effects of other rounds' own work
and never reflected back into this document:

* **ring-nitrogen acyl prefix on a ring/chain parent** (round 8's open row, round 10's own census measured
  it at 2.65%): the documented repro (`OC(=O)c1ccc(cc1)C(=O)N1CCCCC1`) now emits the correct
  `4-(piperidine-1-carbonyl)benzoic acid` directly, verified for piperidine, morpholine and pyrrolidine.
* **the polyacid-anion charge ledger** (round 7's own two findings): citrate's trianion now emits the
  printed PIN (`2-hydroxypropane-1,2,3-tricarboxylate`), bare and as the trisodium salt; the biguanidium
  dication now correctly RAISES instead of silently naming the wrong molecule -- the same refusal-guard
  class as D-133.

**One row re-diagnosed deeper and re-deferred**: a charged acid group inside a carved SUBSTITUENT tree is
still broken (round 8's row, confirmed live), traced this round to its actual root cause --
`_carved_acid_group_fgs` (`engine.py`) already computes the correct anionic prefix form for a demoted
acid-anion site on the "carved" route, but that value is never threaded into the recursive substituent-
naming call that renders a nested acid-anion group, whose own fresh `Perception()` does not detect a
charged chalcogen as an FG at all. Measured broader than round 8 documented: it affects a demoted
CARBOXYLATE the same way as a demoted SULFONATE -- the round's own first spot-check of the carboxylate case
looked "already correct" but turned out to be going through an entirely different mechanism (the homogeneous
classifier route's blunt string-level regex repair, which only fires when every deprotonated site shares one
acid class). Not rushed: the fix touches the same recursive substituent-naming path several existing special
cases (including this round's own carbamimidoyl fix) already sit beside.

**Census extension B** (discovery only, `KNOWN_LIMITATIONS.md` "Open after naming round 11"): 6 more
still-unmeasured round 7-8 backlog shapes, same frozen 2000-structure sample. One clears the frequency floor
(a fused aromatic ring cation, 1.8%, but a coarse proxy needing manual triage before it names an actual
defect); the other five are rare (<=0.25%, several 0/2000) -- real evidence most of what remains in the
round 7-8 backlog is genuinely uncommon.

## 2026-09-23 - naming round 12: a charged acid inside a substituent (D-144), and a triaged census signal

**D-144 (FIXED).** A deprotonated carboxylate or sulfonate on a carved SUBSTITUENT fragment was named
`2-oxido-2-oxoethyl` / `(oxidosulfonyl)methyl`; it is now `carboxylatomethyl` / `sulfonatomethyl`
(P-65.6.2.3.1, pdf p. 619). Root cause, from the round-11 trace and confirmed by spying on `_name_bound`:
on the carved acid-anion route the outer plan holds the right typed FG (`_carved_acid_group_fgs`, with
`prefix_form` from `_ANIONIC_ACID_PREFIX`), but the group inside a substituent is named by a recursive call
on the carved fragment (`CC(=O)[O-]`, SUBSTITUENT, attachment atom 0), whose fresh `Perception()` does not
see a charged chalcogen as an FG. `SubstitutivePath.generate_plans` now adds the same typed FGs for a
SUBSTITUENT-form fragment (`_substituent_acid_anion_fgs`), from the fragment's own atoms, for exactly the
classes in `_ANIONIC_ACID_PREFIX` (any other class would drop its charge; phosphonate stays on its declared-
unsupported path). It skips a group containing the attachment atom: a first version did not and
double-owned the atom on `[S-]c1ccccc1C(=O)[O-]` (`D-121u`), a failed plan and a NAMING ERROR fall-back.
Deliberately NOT the round-11 proposal to thread `prefix_form` into the recursive call: both the acid group
and its attachment carbon are inside the fragment, so nothing needs an outer-to-fragment index map.
Measured: ref-compare 1712 rows, 0 changed (no corpus row has this shape); 1 of 292 charged census rows
changes (an aminophosphonate zwitterion, MATCH); frozen impact 1 of 1126 `bluebook_frozen`, 0 of 40
`heldout_v6`. Tests: 3 FIXED rows (D-144a-c) plus 7 converse/invariant test functions (9 cases) in `test_namer_known_defects.py`;
six of the twelve cases that target the fix fail with the engine change removed, the other six are the converses and pass either way.

**W2, the fused-aromatic-ring-cation signal (round 11), triaged and NOT admitted.** 36 hits, 36 unique
structures: 28 name and read back, 8 embed `[NAMING ERROR ...]`. The engine over all 292 charged census rows
found 6 more cationic ring-system failures outside the proxy, in about ten different ring systems, the
largest 4/2000 (imidazo[1,2-a]pyridin-4-ium). Neutral parents name; the bridgehead/ring-N cation does not.
Recorded in `KNOWN_LIMITATIONS.md`, "Open after naming round 12".

**Tooling.** `tools/naming_stage_artifact.py --frozen-impact <sealed stage>` (`frozen_impact()`): names the
frozen populations with the working tree, compares with the sealed sidecar, prints only `unchanged` or
`changed_count=N of M`, exits 3 if anything moved. Tests use fake rows and assert nothing identifying is
printed (`tests/test_naming_frozen_impact.py`).

## 2026-09-24 - naming round 13: a wrong ring locant on a heterocyclic substituent, and a demoted ketone that claimed its aryl carbon

Started from a measurement: `tools/naming_census_scan.py` named all 2000 census rows and read each back, and the round's own
`tools/naming_ring_locant_sweep.py` did the same for every curated ring at every attachable position. Census 93.45% -> 94.80% -> 95.70% exact;
candidate wrong structures 2.40% -> 0.90%; embedded errors and refusals 1.90% -> 1.15%. Every starting row was WITHHELD by the application (the
read-back mismatch, or the embedded error), so each fix turns "no name" into a right name.

**D-145 (FIXED, 21 census rows).** `engine.py` `_lowest_free_valence_numberings.hetero_key` ranked the lowest COMBINED heteroatom locant set ahead of
the senior heteroatom at locant 1. A monocyclic hetero ring is numbered by Hantzsch-Widman (senior heteroatom = 1). For 1,3,4-thiadiazole
(S1,N3,N4) the alternative N1,N2,S4 has the lower set {1,2,4}, so the substituent was numbered as another heterocycle and its attachment carbon
came out `-3-yl`. Only a ring that carried a second substituent reached this filter (the bare ring goes through
`_heteroaryl_substituent_with_locant`, which weights seniority). Fix: for a monocyclic ring rank the senior heteroatom's locant first; a fused ring
keeps `together` first. 1,2,5-oxadiazole and 1,2,5-thiadiazole had the same shape.

**D-146, D-147 (FIXED, 6 census rows).** A ring with no `atom_locants` and a curated `substituent_form` ending in a digit returned that form
verbatim for every attachment (`2,3-dihydro-1,4-benzodioxin-2-yl` for any benzo carbon, `azepan-1-yl` for any carbon). The numbering computed just
above that early return already knew the real locant and discarded it; it is used now when it differs from the curated digit. Benzodioxine is fused
and the generic numbering mislabels the two positions next to the ring fusion, so it also gets an `atom_locants` table in `data_loader.py`,
derived from its bond topology as 1,3-benzodioxole's is.

**D-148 (FIXED).** The curated `1,2,5-oxadiazole` row in `data_loader.py` was keyed on `c1conn1`, which is 1,2,3-oxadiazole (the vendored
`test_retained_rings.py` had pinned the wrong pair). Key corrected to `c1cnon1`; parent and substituent are the systematic `1,2,5-oxadiazole`
(BlueBookV2.pdf p. 263: "1,2,5-oxadiazole (formerly called furazan)"), where real furazan used to come out `furazan`.

**D-149, D-150 (FIXED, 13 census rows and a silent half).** `_compute_prefix_assignments` Pass 1 built the `oxo` prefix of a DEMOTED ketone (anchor
already in the parent) from every off-parent atom of the group and dropped only heteroatom context; a ketone matches its two flanking carbons as
context, and the one off the parent chain (an aryl or cycloalkyl ipso carbon) was claimed by the `oxo` AND by the `phenyl` the structural pass
carved. `ownership.py`'s exactly-one-owner invariant rejected the plan, correctly. The same double claim silently killed the plan that named an
acid or amide as the parent, so `4-oxo-4-phenylbutanoic acid` came out `3-carboxy-1-phenylpropan-1-one`. Fix: a non-anchor carbon still in
`remaining` is not claimed when the group is suffix-eligible and its anchor is in the parent. The ownership check is unchanged.

**D-151 (OPEN, found by exposing it).** An ester of an acid that also carries a ring-nitrogen sulfonamide is named as a functional-class ester of
the piperidine (`ethyl 1-(4-carboxyphenylsulfonyl)piperidine`). Already there for plain methyl/ethyl esters; W2 stopped masking it for one census
row. 2 census rows (0.1%). Not fixed.

**Measured.** ref-compare against the pre-round tip: 1712 rows, 1 name changed (an isouronium cation, STRUCTURALLY_EQUIVALENT, both names read
back MATCH), 0 violations. Blind frozen impact: 0 for the W1-only engine, so the 1-of-40 (`heldout_v6`) and 1-of-1126 (`bluebook_frozen`) that
moved are W2's. Tests: 16 FIXED rows (D-145a to D-150c) and 28 converse and invariant cases in `test_namer_known_defects.py`, plus 3 provider
tests; the mutation checks fail 14 of the 24 W1 cases and 9 of the 20 W2 cases with the engine and data changes removed, the rest being converses.

## 2026-09-24 - naming round 14: ring-nitrogen sulfonamides, ring cations, stereo on retained substituents, derived fused-ring tables

Census 95.70% -> 97.95% exact (0 rows left `exact`), candidate wrong structures 0.90% -> 0.60%, embedded errors and refusals 1.15% -> 0.45%; the ring-locant
sweep's rings with a structurally wrong case 19 -> 9. Every fix is a cluster with ONE named root mechanism whose members were all re-run.

**D-151 (FIXED, broadened; 7 census rows).** `engine.py` `_compute_prefix_assignments`: a sulfonamide whose nitrogen is a RING atom outside the parent
(`_sulfonamide_is_ring_nitrogen_prefix`) claimed S, O, O and N and left the ring's carbons unclaimed, so every plan with the other side as parent died and
the engine named the ring as the parent (an acid lost its suffix, an ester became an ester of the piperidine). It is left to the structural carve, and the
sulfonyl/sulfinyl route writes `<ring>-N-sulfonyl` (P-65.3.2.3). **D-152 (3 rows).** The sulfamoyl prefix printed one shared `N,N-` block; each
substituent now carries its own locant.

**D-154..D-157 (9 of 14 ring-cation rows).** (D-154) `fusion_general.name_fusion_parents` refused any charged ring atom; a `_neutral_ring_copy` (same atom
indices, bicyclic systems only) names the skeleton and the engine adds `-ium` at the charged atom's locant. (D-155) `_shift_bridgehead_cation_charge`: a
ring-fusion `[n+]` beside an `[nH]` is the `[nH+]` cation. (D-156) `ring_naming/common.py` made a charged N with three ring bonds an indicated-hydrogen
target; and the curated quinolizidine row (`data_loader.py`) gave its nitrogen `4a` (it is 5). (D-157) `_standalone_or_cation`: the acid recursion for an
acyl or amido prefix runs at depth > 0, where `name` never promotes STANDALONE to CATION, so the ring cation lost its `-ium`.

**D-158 (18 rows), D-159 (3 rows).** The stereo-drop gate for retained names (`retained_plan_would_drop_stereo`) ran for STANDALONE only and did not read the
`_ParentCIPCode` stash on a carved fragment; a retained ring substituent (`oxolan-2-yl`) is a LEAF that never reads stereo. `_collect_stereo_descriptors` admits
tetrahedral stereo on a spiro parent at plain-integer locants, under the existing post-assembly OPSIN validation.

**D-160, D-161, D-153.** Locant tables for heptacene, octacene, nonacene and pentaphene to octaphene (each one of the numberings `fusion_general.name_fusion`
derives, P-25.3.3, pinned by a test), and for octahydro-1H-indole, hexahydrothieno[3,4-d]imidazole and `[1,2,4]triazolo[3,4-b][1,3]benzothiazole` (the numbering
of the mancude parent carried onto the skeleton). `monocyclic.name_systematic_monocyclic` recovers the Kekule bonds of an aromatic non-benzene carbocycle:
tropone was `cycloheptanone`. **D-162 recorded OPEN** (an N-hydroxy-N-alkyl amide in an ester loses its N-substituent).

**Measured.** ref-compare against the round-13 merge: 1712 rows, 1 name changed (`c1c[cH+][cH+]1`, `cyclobutane` -> `cyclobutene`, still not the printed
bis(ylium)), 0 violations. Blind frozen impact: unchanged for both populations, so no new final evaluation was scored. Driven check: 66/66 rows.

## 2026-09-24 -- naming round 15 (D-163): a nitro group on a ring nitrogen

Found on the molecule that started the post-round-14 program, 1,3-dinitro-1,3-diazetidine, which the app named
`oxido{3-[oxido(oxo)azaniumyl]-1,3-diazetidin-1-yl}(oxo)azanium`. That name reads back (so the census called it exact) and is not the name anybody uses.
RDX, HMX, TNAZ, N-nitropyrrolidine and the N-nitro azoles were all named that way.

**Cause.** `functional_groups.json`'s `nitro` pattern is `[NX3+](=O)([O-])[#6]`: it needs a CARBON neighbour, so a nitro nitrogen on a ring nitrogen belonged to
no group. Perception's acyclic-N+ azanium candidate (`perception/__init__.py`, +50, "yielded BEFORE rings") then offered it as a one-atom parent, and that
outranked the ring. **Fix.** A second `nitro` entry, `[NX3+](=O)([O-])[#7;R]`. Widening the existing pattern to `[#6,#7]` was tried first and is wrong: the
attachment carbon of a prefix-only group is found by a plain `[#6]` atom in the SMARTS text (`fg_detection.py`), and any other spelling silently drops the
attachment context -- `4-(nitromethyl)piperidine` stopped naming. Found by diffing a 20-structure battery against the unmodified engine: 14 ring-nitrogen rows
changed, every other row identical.

**Measured.** ref-compare against the round-14 merge: 1712 structures, 0 names changed, 0 violations. Census scan: 0 rows changed class or name (97.95% exact,
unchanged). Blind frozen impact: unchanged for both populations, so no new final evaluation was scored. **These three are not evidence for the fix**: none of the
existing corpora contains a ring N-nitro structure, so they show only that nothing else moved. The evidence is the nine `D-163` rows in
`tests/test_namer_known_defects.py`, each verified by OPSIN read-back in the vendored suite (5348 passed), and the battery diff above.

## 2026-09-25 -- naming round 16 (D-164, D-165): a nitro or nitroso group on an ACYCLIC nitrogen

Round 15 fixed the ring nitramines and recorded these open. `CN(C)[N+](=O)[O-]` was `(dimethylamino)(oxido)(oxo)azanium`, nitroguanidine was
`imino{[oxido(oxo)azaniumyl]amino}methanamine`, nitrourea `1-{[oxido(oxo)azaniumyl]amino}methanamide`, NDMA `1,1-dimethyl-2-oxohydrazine`, and
`CC(=O)N(C)[N+](=O)[O-]` `N-methyl-N'-oxido-N'-oxoacetohydrazide`, which OPSIN cannot read. All but the last read back, which is why no census row moved.
They are now `N-methyl-N-nitromethanamine`, `N-nitroguanidine`, `N-nitrourea`, `N-methyl-N-nitrosomethanamine` and `N-methyl-N-nitroacetamide`.

**Six changes, none sufficient alone.** (1) `functional_groups.json`: `secondary_amine`/`tertiary_amine` and `secondary_amide`/`tertiary_amide` entries whose nitrogen REQUIRES a
nitro (`$(N[NX3+](=O)[O-])`) or nitroso (`$(N[NX2]=O)`) neighbour by a recursive constraint. The neighbour must NOT be an atom of the match: as a `context_indices` atom
(the way the N-alkoxy amines do it) the nitro FG then loses the deconfliction (`Unknown FG overlap: tertiary_amine vs nitro`), and as a plain match atom the amine owns it twice.
(2) A `nitro` prefix group whose match is the nitro group's own three atoms with the neighbouring nitrogen a recursive constraint; without it the nitro nitrogen is still
offered as the azanium parent (`dimethyl(oxido)(oxo)azaniumamine`). (3) `engine.py` `_SMALL_FRAGMENT_PREFIXES_BY_ATTACHMENT` gains `("O=[NH+][O-]", "N"): "nitro"`: the
carve puts a hydrogen on the attachment nitrogen, so the fragment is not the `[N+]` of the fixed table; keyed by attachment element so a nitrate or nitrite fragment
attached at oxygen cannot take it. (4) A heteroatom-chain (N-N) parent may not take an `-amine` suffix on its own nitrogen: without it diethylnitrosamine was
`1,1-diethyl-2-oxohydrazin-1-amine`, which OPSIN cannot read. (5)/(6) `_name_urea_functional_parent` and `_name_guanidine_functional_parent` refuse an N-N bond because that
is a hydrazide; `_is_nitro_or_nitroso_nitrogen` exempts a nitro or nitroso nitrogen, which is a substituent.

**Measured.** Census scan (2000 rows): 97.95% exact before and after, ONE row moved (`census215625`, a nitroguanidine hydrazone, exact both times). ref-compare against the round-15
merge: 1712 structures, **4 names changed, all in the TUNING population and all N-nitro or N-nitroso** (`{methyl[oxido(oxo)azaniumyl]amino}(oxido)(oxo)azanium` -> `(dinitroamino)methane`,
`[(chloromethyl)(methyl)amino](oxido)(oxo)azanium` -> `1-chloro-N-methyl-N-nitromethanamine`, ...), each still reading back; listed in
`benchmarks/naming/stages/manifests/r16-release-candidate.toml`, 0 violations. **The blind frozen impact CHANGED** (`bluebook_frozen` 6 of 1126, `heldout_v6` unchanged), so the
frozen sets were scored ONCE (`r16-final-evaluation`), in aggregate, never by row: `bluebook_frozen` exact 505 -> 506, equivalent 540 -> 539, wrong_structure 22 -> 22, unparsable 46 -> 46,
no_prediction 13 -> 13; `heldout_v6` identical (13 exact, 25 equivalent, 2 wrong_structure). One equivalent name became exact and nothing got worse. 64-structure battery against the
unmodified engine: every N-nitro and N-nitroso row changed, every control row (nitroalkanes, nitroarenes, hydrazines, hydroxylamines, ureas, amidines, ring nitramines) identical.
**Evidence for the fix is the 18 rows D-164a..D-165h**, each verified by OPSIN read-back in the vendored suite. **Open** (`KNOWN_LIMITATIONS.md`): nitramide itself (D-166) and N-nitro /
N-nitroso carbamates (D-167).


## 2026-09-25 -- naming round 17 (D-166, D-167): nitramide and nitrous amide as PARENTS, and N-nitro / N-nitroso carbamates

Round 16 left two cases open, and reading the book for them showed that round 16's own names for the plain nitramines and nitrosamines were the book's NON-PIN alternative. P-67.1.2.6.3
(pdf p. 708), verbatim: "Nitramines are amides of nitric acid ... The class is composed of 'nitramide' (a shortened form of nitric amide), NO2-NH2, and the names of its derivatives are formed
by substitution ... Preferred IUPAC names for amides and hydrazides of nitric and nitrous acids are now systematically based on nitric or nitrous amide and hydrazide, in accordance with the
seniority order of classes rather than as nitro and nitroso amines; the latter names can be used in general nomenclature." Page 709 prints `(chloromethyl)(methyl)nitramide (PIN)` beside
`1-chloro-N-methyl-N-nitromethanamine`. So `CN(C)[N+](=O)[O-]` is now `dimethylnitramide`, NDMA `dimethylnitrous amide`, `N[N+](=O)[O-]` `nitramide` (it had no plan at all), and the two D-167
carbamates `ethyl nitrocarbamate` (was `[(nitroamino)(oxo)methoxy]ethane`) and `ethyl methyl(nitroso)carbamate` (was `1-(ethoxycarbonyl)-1-methyl-2-oxohydrazine`). The round-16 targets were
recorded as "NOT checked against the Blue Book"; the check was one search of the PDF.

**Two changes.** (1) `_name_nitramide_functional_parent`, on `_name_n_core_parent` like the cyanamide and sulfamic acid routes: an acyclic amino nitrogen carrying a nitro or nitroso group is the
one substitutable position of `nitramide` or `nitrous amide`, so its prefixes take no locant (`methyl(nitro)nitramide`, `bis(2-hydroxyethyl)nitrous amide`); nitric outranks nitrous, so with both on one
nitrogen the nitro group is the parent's. It declines when a group of the amide class or above sits elsewhere (`_N_CORE_PARENT_SENIORITY_LIMIT`), when the nitrogen is on a carbon doubly bonded to N, O or S
(an acyl, imidoyl or carbamoyl carbon, which the seniority check cannot always see: the guanidine route declines an amidrazone, and without this guard `census215625` was named `...carbamimidoyl]nitramide`),
on a cyano carbon (cyanamide), on a second all-single-bonded nitrogen (a hydrazine), and when the molecule has more than one such nitrogen (a multiplicative parent). A ring nitrogen is never this. The bare
parents are emitted by the same function. (2) `_build_carbamate_decomposition` took the nitro or nitroso nitrogen for the second nitrogen of a CARBAZATE and offered no functional-class plan, the refusal round 16
lifted for urea and guanidine; the predicate moves to `types.py` as `is_nitro_or_nitroso_nitrogen` (the lowest module both import) and `engine.py` uses the one implementation.

**Measured.** Census scan (2000 rows): 97.95% exact before and after, **0 rows changed** (the guard above was added because the first run moved one). ref-compare against master (`d1c08f3`): 1712 structures,
**3 names changed, all TUNING, each now equal to the name the book prints for it** (`isocyanatonitramide`, `methyl(nitro)nitramide`, `(chloromethyl)(methyl)nitramide`), listed in
`benchmarks/naming/stages/manifests/r17-release-candidate.toml`, 0 violations. **The blind frozen impact CHANGED** (`bluebook_frozen` 5 of 1126, `heldout_v6` unchanged), so the frozen sets were scored ONCE
(`r17-final-evaluation`), in aggregate: `bluebook_frozen` exact 506 -> 510, equivalent 539 -> 535, wrong_structure 22 -> 22, unparsable 46 -> 46, no_prediction 13 -> 13; `heldout_v6` identical; `bluebook_tuning`
exact 507 -> 510. Four equivalent names became exact and nothing got worse. Vendored suite 5404 passed; the app's source-scanning test files and the known-defects table 6581 passed. The evidence for the fix is
the rows `D-164a-d` and `D-165a-d` (retargeted to the PINs), `D-166a-h` and `D-167a-b`, each verified by OPSIN read-back, the printed ones quoted from the book.

**Not fixed, found on the way** (`KNOWN_LIMITATIONS.md`): the `-NH-NO2` and `-NH-NO` PREFIXES (D-168: the book prints `nitramido` and `nitrosoamino`, the engine writes `(nitroamino)` and, worse, the unparenthesised
`4-nitrosoaminobenzoic acid`); the nitric and nitrous HYDRAZIDES the same section names; ethylenedinitramine, whose two nitramide groups are a multiplicative parent; and the hypochlorous and bromous amides on p. 529.


## 2026-09-26 -- naming round 18 (D-168): the nitramido and nitrosoamino PREFIXES

Round 17 made the nitramide the PARENT and found, on the way, two prefix defects in the same section of the book. Where a nitramide is NOT the parent (a carboxylic acid or an amide elsewhere outranks it), P-67.1.4.3.2
(pdf p. 717) names the group: "The amide of nitric acid, O2N-NH2, is named 'nitramide' and the substituent group derived from this amide by the loss of one hydrogen atom is called 'nitramido' by applying
the general rule for naming amides", printed "-NH-NO2 nitramido (preselected prefix)" and "-NH-NO nitrosoamino (preselected prefix)". `OC(=O)c1ccc(N[N+](=O)[O-])cc1` was `4-(nitroamino)benzoic acid` and is
`4-nitramidobenzoic acid`; `OC(=O)c1ccc(NN=O)cc1` was `4-nitrosoaminobenzoic acid` and is `4-(nitrosoamino)benzoic acid`; two of either multiply as `3,5-dinitramidobenzoic acid` and
`3,5-bis(nitrosoamino)benzoic acid` (the second was `3,5-dinitrosoaminobenzoic acid`).

**Three small changes.** (1) `assembly._preferred_prefix_spelling` maps the bare word `nitroamino` to `nitramido`, next to `phenylamino` -> `anilino`, so every route that composes the prefix (an aryl or alkyl parent) gets
it; and `_name_heteroatom_fv_substituent` returns `nitramido` for a nitro-only N substituent, which is what makes the prefix inside an imino group (`(nitramidoimino)acetic acid`). (2) `nitrosoamino` leaves
`_SIMPLE_PREFIXES`: it is a substituted amino group and a compound prefix, and the allowlist entry is why it was never enclosed. (3) `nitramido` joins `_LEADING_PREFIX_WORDS`, so a longer word that starts with
it is compound and enclosed.

**A round-17 guard was too loose, found by probing multiples for this round.** Round 17 let a second nitrogen with any multiple bond through, meaning to admit `isocyanatonitramide`; a HYDRAZONE (`C=N-NH-NO2`)
has one too, and was named `[(phenylmethylidene)amino]nitramide`. The book names hydrazones of these acids on the HYDRAZIDE (`N'-hexylidenenitrous hydrazide (PIN)`), which is not attempted, so
`_is_hydrazone_type_nitrogen` (a nitrogen doubly bonded to a carbon with no second double bond) now declines, and the hydrazine name stays: `1-nitro-2-(phenylmethylidene)hydrazine`. Isocyanato and isothiocyanato
still take the nitramide parent.

**Measured.** Census scan (2000 rows): 97.95% exact before and after, **0 rows changed**. ref-compare against master (`ea2275f`): 1712 structures, **0 names changed**, 0 violations, so no visible population contains either
prefix. **The blind frozen impact CHANGED**, so the frozen sets were scored ONCE (`r18-final-evaluation`), in aggregate: `bluebook_frozen`, `heldout_v6` and `bluebook_tuning` are IDENTICAL to round 17's
(`bluebook_frozen` exact 510, equivalent 535, wrong_structure 22, unparsable 46, no_prediction 13), so some frozen names moved and no outcome class did. Vendored suite 5421 passed; the source-scanning test files
and the naming tests 6995 passed, with two `test_mol3d_viewer_backend.py` WebEngine tests failing during that long mixed run and passing on their own, twice, and on master's code. Each of the five changes was removed in
turn and a known-defects row failed. The evidence is the rows `D-168a-g` (each verified by OPSIN read-back) and the open rows `D-169a-c`.

**Not fixed** (`KNOWN_LIMITATIONS.md`): the nitric and nitrous HYDRAZIDES, queued as `D-169` with OPSIN-verified targets (`nitric hydrazide`, `nitrous hydrazide`, `N'-benzylidenenitric hydrazide`).


## 2026-09-26 -- naming round 19 (D-169): nitric and nitrous HYDRAZIDES as parents

Round 17 made the nitramide the parent and left the hydrazides, which the same section makes preselected parents. P-67.1.2.6.3 (pdf p. 708), verbatim: "Similarly, nitric hydrazide (I) and nitrous hydrazide (II) are preselected
names used as parent structures for generation of preferred IUPAC names", and p. 709 prints `N'-hexylidenenitrous hydrazide (PIN)`. `O2N-NH-NH2` was `nitrohydrazine` and is `nitric hydrazide`; `ON-NH-NH2` was
`1-amino-2-oxohydrazine` and is `nitrous hydrazide`; `CNN[N+](=O)[O-]` was `1-methyl-2-nitrohydrazine` and is `N'-methylnitric hydrazide`; a hydrazone was a hydrazine with an ylidene (`1-nitro-2-(propan-2-ylidene)hydrazine`)
and is `N'-(propan-2-ylidene)nitric hydrazide`. **The nitrogen that bears the nitro or nitroso group is N and the terminal one N'** (OPSIN reads `N'-methylnitric hydrazide` as `CNN[N+](=O)[O-]` and
`N,N'-dimethylnitric hydrazide` as `CN(NC)[N+](=O)[O-]`); N' may carry two single-bonded substituents or ONE double-bonded one, a hydrazone, named as an ylidene. A hydrazide outranks an alcohol (P-41), so
`OCCNN[N+](=O)[O-]`, an ethanol before, is `N'-(2-hydroxyethyl)nitric hydrazide`.

**One new namer and one extension.** `_name_nitric_hydrazide_functional_parent`, on `_name_n_core_parent` with fixed `N` / `N'` labels, runs after the nitramide route (which keeps every molecule whose second nitrogen is not a hydrazine
or hydrazone nitrogen). `_name_n_core_parent` gains `allow_ylidene`, so a nitrogen can carry a double-bonded substituent named as an ylidene; every other parent still refuses one. The route declines for a group of the hydrazide
class or above elsewhere (the limit is 1201: a carbon hydrazide, an amide, an acid, an ester), a nitrogen on a carbon doubly bonded to N, O or S or a cyano carbon, a triazane or a second nitro or nitroso group on N', a ring
nitrogen, and **a hydrazone whose carbon carries a heteroatom** (an amidine, a guanidine, an imidate or a hydrazonoyl halide, which are derivatives of a carbon acid: the first version named nitroaminoguanidine
`N'-(diaminomethylidene)nitric hydrazide` and a control row caught it). Seven changes (the ylidene refusal, the hydrazide-class limit, the carbon-acid neighbour, the triazane and second-acyl guard, the hydrazone-carbon heteroatom guard, the nitric-versus-nitrous choice and the dispatch) were each removed in turn and a table row failed; one guard (an isocyanate-type N') is dead behind the
nitramide route and is kept only so the function is right on its own, measured by removing it and seeing every row pass.

**Measured.** Census scan (2000 rows): 97.95% exact before and after, **0 rows changed class and 1 row changed name** (`census1625`, `CC(C)N(CCCN)N(O)N=O`, a nitrous hydrazide: `3-[2-hydroxy-2-nitroso-1-(propan-2-yl)hydrazinyl]propan-1-amine`
-> `N'-(3-aminopropyl)-N-hydroxy-N'-(propan-2-yl)nitrous hydrazide`, exact both times). ref-compare against master (`7562a6a`): 1712 structures, **0 names changed**, 0 violations. **The blind frozen impact CHANGED** (`bluebook_frozen`
1 of 1126, `heldout_v6` unchanged), so the frozen sets were scored ONCE (`r19-final-evaluation`), in aggregate: every population is IDENTICAL to round 18's (`bluebook_frozen` exact 510, equivalent 535, wrong_structure 22,
unparsable 46, no_prediction 13), so one frozen name moved and no outcome class did. Vendored suite 5443 passed; the source-scanning test files and the naming tests 7021 passed. The evidence is the rows `D-169a-k` and the 13
control rows (`test_a_senior_group_or_another_shape_keeps_its_name_over_a_nitric_hydrazide`), each fixed row verified by OPSIN read-back; the book's own hexylidene example is a frozen row and is not used.

**Round 18's stopgap is replaced.** `D-168g`, a hydrazone of nitramide, was pinned to the hydrazine name until this route existed; it is now `N'-(phenylmethylidene)nitric hydrazide` (the ylidene is spelled as the engine spells it everywhere,
`phenylmethylidene`, never `benzylidene`).

**Not fixed, found on the way** (`KNOWN_LIMITATIONS.md`): the SUBSTITUENT names of a hydrazone or hydrazine, queued as `D-170`. The book prints `3-amino-3-hydrazinylidenepropanoic acid (PIN)` (p. 682) and `nitrosohydrazinylidene (preselected
prefix)` (p. 717); the engine writes `3-amino-3-(aminoimino)propanoic acid` and `(R-aminoimino)` for the whole `=N-NH-R` family, of which round 18's `(nitramidoimino)` is one member.


## 2026-09-26 -- naming round 20 (D-170): the SUBSTITUENT `hydrazinylidene`

Found while fixing D-169 and queued there. P-66.4.1.2 (pdf p. 682), verbatim: "3-amino-3-hydrazinylidenepropanoic acid (PIN)"; p. 717 prints "nitrosohydrazinylidene (preselected prefix)". The engine's general `<R>imino` rule
(`_name_heteroatom_fv_substituent`, the `=N-R` case) read the whole `=N-NH-R` family as an imino group on an amino group: `OC(=O)CC(N)=NN` was `3-amino-3-(aminoimino)propanoic acid`, `OC(=O)CC(C)=NNC`
`3-(methylaminoimino)butanoic acid`, an acyl hydrazone `3-acetamidoiminobutanoic acid`, round 18's `D-168f` `(nitramidoimino)acetic acid`. OPSIN reads every one of them back to the right structure; they are not the name.

**One new helper.** `_hydrazinylidene_prefix` writes `hydrazinylidene` for `=N-N(R)(R')`, with N2's substituents cited at 2 (`2-methylhydrazinylidene`, `2,2-dimethylhydrazinylidene`, `2-ethyl-2-methylhydrazinylidene`,
`2-(4-chlorophenyl)hydrazinylidene`) and a lone nitro or nitroso group unlocanted, as the book prints it (`nitrosohydrazinylidene`). It returns None, and the imino form stays, for an azine (N2 unsaturated), a ring N2 and a
triazane. `assembly._is_simple_by_form` leaves the BARE group unenclosed, as the book prints it (`3-amino-3-hydrazinylidenepropanoic acid`); every substituted form is compound and enclosed. The helper's first version
called `carve_substituent` and `_assemble`, which are LOCAL imports of the function it was written beside: the NameError was swallowed by the helper's own `except Exception: return None`, so it "declined" everything but the
bare group and the first run looked half-right. Both are imported inside the helper now.

**Measured.** Census scan (2000 rows): 97.95% exact before and after, **0 rows changed class and 19 changed name**, all of them this prefix (acyl hydrazones `4-[(4-methylbenzamidoimino)methyl]phenol` ->
`4-{[2-(4-methylbenzoyl)hydrazinylidene]methyl}phenol`, aryl hydrazones, a fluorenone hydrazone) and every one exact both times. ref-compare against master (`9f5e745`): 1712 structures, **19 names changed, all in the tuning
population, all reading back, all listed in `benchmarks/naming/stages/manifests/r20-release-candidate.toml`, 0 violations**. **The blind frozen impact CHANGED** (`bluebook_frozen` 14 of 1126, `heldout_v6` unchanged), so the
frozen sets were scored ONCE (`r20-final-evaluation`), in aggregate: every population is IDENTICAL to round 19's (`bluebook_frozen` exact 510, equivalent 535, wrong_structure 22, unparsable 46, no_prediction 13). The tuning
population gained three exact names (`verbatim` 510 -> 513 of 1129), one of them the printed p. 682 PIN. Vendored suite: no failure in the 5450-odd tests (a `-q -q` run prints no summary line, so the count is from the
progress lines); the naming, docs and source-scanning test files 2378 passed. The evidence is the rows `D-170a-m` and five control rows, each fixed row verified by OPSIN read-back. Nine changes were each removed in turn and a
row failed for eight (the ring-N2 test alone is an equivalent mutant: a ring N2 is already declined by the substituent walk, and is kept so the function is right on its own).

**Not fixed, found on the way** (`KNOWN_LIMITATIONS.md`): the acyl hydrazones the census shows are named on a prefix here and on the wrong parent for the book (P-66.3.3 names the hydrazide, `N'-...-ylideneacetohydrazide`); an azine
(`C=N-N=C`) still reads `[(ethylidene)aminoimino]`.


## 2026-09-27 -- naming round 21 (D-173, D-178): the retained prefixes benzyl/benzylidene/benzylidyne, and amides of the halogen oxoacids

Alex asked to combine the round-20 backlog into one PR where feasible. Investigated all seven items; two had a clean, self-contained, book-verified fix; the
rest are recorded below with more citation detail than before, deliberately left open rather than guessed.

### D-173: `benzylidene` and `benzylidyne`, unenclosed and unsubstituted-only

P-29.6.1 (pdf p. 312), verbatim: "The traditional prefixes benzyl, benzylidene, benzylidyne are retained preferred prefixes, but are not to be substituted";
printed "2-benzylpyridine (PIN)" beside "2-(phenylmethyl)pyridine". `benzyl` ("phenylmethyl", bond order 1) was already handled by `_preferred_prefix_spelling`;
this round adds `benzylidene`/`benzylidyne` ("phenylmethylidene"/"phenylmethylidyne", bond orders 2/3). P-29.6.2.1 (p. 313): substituted (ring OR alpha position),
they revert to the systematic form, "carboxy(4-carboxyphenyl)methylidene (preferred prefix)".

**Two hand-built compound prefixes never pass through `merge_identical_prefixes`**, the only place `_preferred_prefix_spelling` used to run, so even plain
`benzyl` needed a direct call added at both sites: the `R-imino` prefix (`PARENT=N-R`, e.g. `3-(phenylmethylimino)butanoic acid` was wrong on its own, not only
on its ylidene kin) and the `(R-ylidene)amino` prefix (`PARENT-N=R`). D-168g (round 18's stopgap) and a round-20 control row moved to the new spelling; D-092u,
which demonstrated a two-stem ylidene prefix staying enclosed, moved to a substituted phenyl so it still demonstrates that.

**Measured.** Census scan (2000 rows): 97.95% exact before and after, **0 rows changed class and 10 changed name**, all this family and all exact both times
(acyl hydrazones, an imidazolone hydrazide, a heptanal ylidene, a benzonitrilium-style cation are among the corpus hits). ref-compare against master
(`7f2d8d2e`): 1712 structures, **2 changed** (one tuning row, one the `r8:S2-benzonitrilium` reference structure itself -- `benzylidyneazanium` for protonated
benzonitrile, a real, independently-curated row, not a synthetic test), both reading back, both listed in
`benchmarks/naming/stages/manifests/r21-release-candidate.toml`, 0 violations. **The blind frozen impact CHANGED** (`bluebook_frozen` 5 of 1126, `heldout_v6`
unchanged), so the frozen sets were scored ONCE (`r21-final-evaluation`), in aggregate: `bluebook_frozen` exact rose **510 -> 511** (one row moved
equivalent -> exact), every other bucket (`wrong_structure` 22, `unparsable` 46, `no_prediction` 13) unchanged; `heldout_v6` unaffected. The tuning population
also gained one exact name. Vendored suite: see below. The evidence is rows `D-173a-f`, each verified by OPSIN read-back; ten guards were each removed in turn
and a row failed.

### D-178: amides of the mononuclear halogen oxoacids

P-62.4 (pdf p. 528), verbatim: "compounds such as R-NH-Cl, R-NH-NO, and R-NH-NO2 are now named as derivatives of amides (see P-67.1.2.6)" -- the identical
reclassification rule round 17 built for the nitro and nitroso cases (nitramide, nitrous amide), extended here to a bare halogen. P-67.1.2.2 lists hypohalous,
halous, halic and perhalic acid (Cl, Br, F, I) as preselected names modified by prefix; P-67.1.2.6.1 turns any of them into an amide by replacing "acid" with
"amide". Printed (p. 529): "ethylhypochlorous amide (PIN)" beside "N-chloroethanamine", "methylbromous amide (PIN)" beside "N-bromosylmethanamine".

**One new `_name_hypohalous_amide_functional_parent`**, structured exactly like round 17's nitramide function (same carbon-acid-neighbour guard, same
`_N_CORE_PARENT_SENIORITY_LIMIT`). `CCNCl` was `(chloroamino)ethane` and is `ethylhypochlorous amide`; the fluorine, bromine and iodine analogues follow the
same rule (derived, not printed, for F and I). **Iodine alone climbs the oxidation ladder**: RDKit's own valence table accepts a neutral tri- or pentavalent
iodine bonded to an amino nitrogen and one or two double-bonded oxygens (`CNI=O` -> `methyliodous amide`, `CNI(=O)=O` -> `methyliodic amide`, the latter
previously **a NAMING ERROR with no name at all**), but refuses the identical shape for chlorine or bromine outright
(`Explicit valence for atom # 2 Cl, 3, is greater than permitted`). **The book's own bromous-amide example is therefore not reachable through this engine at
all** -- not merely unmeasured, but structurally unbuildable in RDKit's molecule model -- and is not attempted.

**Measured.** Census scan and ref-compare: **0 changes** (no N-halogen structure in either corpus). Ten guards (the formal-charge/ring check, the oxo-count ->
name table, the carbon-acid-neighbour decline, the per-nitrogen and per-molecule single-candidate caps, and the dispatch call itself) were each removed in turn
and a row failed for all ten. Evidence: rows `D-178a-m`.

### Investigated, not fixed

- **Hydrazones of carbon-acid hydrazides** (`CC(=O)NN=CCCCCC` is `1-acetyl-2-hexylidenehydrazine`; P-66.3.3 names the hydrazide,
  `N'-hexylideneacetohydrazide`). Unlike the nitric/nitrous hydrazide route (a self-contained function on `_name_n_core_parent`), a plain carbon acylhydrazide is
  a genuine FG-suffix (`fg:hydrazide`, seniority 1200, `smarts = "[CX3;!R;...](=O)[NX3;!R][NX3;!R]"` in `data/functional_groups.json`): its SMARTS requires
  BOTH nitrogens at `NX3` (three connections), which a hydrazone's terminal `=N-` fails (degree 2, `NX2`). Loosening the SMARTS and then rendering an
  N'-ylidene alongside the `-ohydrazide`/`-carbohydrazide` suffix touches the FG-suffix rendering pipeline broadly (Phase 6 of `_name_bound`, ~line 16097),
  which is general enough that a narrow, self-contained fix could not be found this round; recorded rather than guessed.
- **An azine, a triazane or a ring nitrogen on the second nitrogen of an `=N-N` group** still keeps the imino form; no book names for them were found this
  round either.
- **The book's own `hydrazin-1-yl` locant** (p. 717 versus p. 71) is left exactly as round 20 left it: an unresolved inconsistency in the source, not a code
  defect.
- **A cyano group on the nitramide nitrogen** (`N#CN(C)[N+](=O)[O-]`): P-66.1.6.2 (pdf p. 664), verbatim, retains `cyanamide` as the PIN for `NC-NH2` and
  permits substitution on the `-NH2`. Cyanamide and nitramide are both preselected amide-class parents (class 11) competing for the SAME nitrogen; the book
  prints no example resolving which wins, so no target is claimed and the guard that defers to the general path stays.
- **Ethylenedinitramine** (`O=[N+]([O-])NCCN[N+](=O)[O-]`, two nitramide groups) still keeps round 16's amine name, `N1,N2-dinitroethane-1,2-diamine`, which
  is NOT the PIN. A candidate PIN was derived and OPSIN-verified this round, `ethane-1,2-diylbis(nitramide)`, using the same multiplicative
  `<parent>-1,2-diylbis(...)` construction the book itself uses for other functional-parent pairs (p. 527's own
  `3,3'-[ethane-1,2-diylbis(azanylylidene)]dipropanoic acid`); it is not implemented, because nitramide is a hand-built functional parent rather than an
  ordinary suffix, and wiring it into `multiplicative.py`'s machinery is a separate piece of work. Recorded here so the next round starts from a verified
  target rather than a guess.


## 2026-09-27 -- naming round 22 (D-171): hydrazones of a carbon-acid hydrazide are named on the hydrazide

Round 21 investigated this and left it open, expecting a broad change to the FG-suffix rendering pipeline. It turned out to be one character.

P-66.3.3 prints the same pattern round 19 built for the nitric/nitrous hydrazide (P-67.1.2.6.3), "N'-hexylidenenitrous hydrazide (PIN)" (pdf p. 709):
`CC(=O)NN=CCCCCC` was `1-acetyl-2-hexylidenehydrazine` (a substituted hydrazine, the non-preferred general-nomenclature form) and is `N'-hexylideneacetohydrazide`.

**The cause.** The `fg:hydrazide` SMARTS (`data/functional_groups.json`) is
`[CX3;!R;...](=O)[NX3;!R][NX3;!R]` -- BOTH nitrogens required at `NX3` (three connections). The acyl-adjacent nitrogen of `R-C(=O)-NH-N=CR'R''` is `NX3`
(bonded to the carbonyl, H, and N), but the terminal nitrogen (`=N-CR'R''`) has only two connections (one single bond to N, one double bond to C) --
`NX2` -- so the SMARTS never matched a hydrazone at all, and the whole molecule fell through to a substituted-hydrazine parent.

**The fix.** The terminal nitrogen's clause becomes `[$([NX3;!R]),$([NX2;!R]=[#6])]`: NX3 as before, OR NX2 double-bonded specifically to a CARBON. The
carbon restriction matters: without it, an azo/triazene nitrogen (`-NH-N=N-R`, `NX2` too, but a different functional class entirely) would be
misclassified as a hydrazide's hydrazone (measured: `CC(=O)NN=NC`, an acylhydrazide-azo compound, briefly became `N'-(methylimino)acetohydrazide`
before the restriction, structurally correct by OPSIN read-back but the wrong class -- a genuine defect a control row now pins against).

**Nothing downstream needed touching.** Pass 2.5a ("PCG N-substituents"), the general machinery that already carves N-alkyl and N-aryl hydrazide
substituents and assigns N/N' role primes (`_role_primes`, P-66.3), reads `attachment_bond_order` off the actual bond and was already prepared to render
a bond-order-2 substituent as an ylidene -- it had simply never been offered one. The retained `benzylidene` spelling (round 21, D-173) is reached the
same way any other ylidene is, with no special case (`N'-benzylideneacetohydrazide`).

**A genuine bonus fix.** `CC(=O)NN=C(N)N` (a hydrazone carbon bearing two amino groups, the same shape D-169's own control rows pin as "not a guanidine
this engine's perception claims") was `(2-acetylhydrazinylidene)methanediamine` -- an AMINE chosen as parent over a HYDRAZIDE, which P-41's seniority
order never allows. It is now `N'-(diaminomethylidene)acetohydrazide`, matching the same amine-not-class-11 pattern D-169 had already established for
the nitric hydrazide.

**Measured.** Census scan (2000 rows): 97.95% exact before and after, **0 rows changed class and 40 changed name**, all this pattern (39 exact -> exact,
one same_connectivity -> same_connectivity, unrelated pre-existing stereo issue) -- the family is common in drug-like corpora, not a corner case.
ref-compare against master (`f9370fc8`): 1712 structures, **1 changed** (a `heldout_v5` row), reading back both ways, listed in
`benchmarks/naming/stages/manifests/r22-release-candidate.toml`, 0 violations. **The blind frozen impact CHANGED** (`bluebook_frozen` 1 of 1126,
`heldout_v6` 1 of 40), so the frozen sets were scored ONCE (`r22-final-evaluation`), in aggregate: every population is IDENTICAL to round 21's
(`bluebook_frozen` exact 511, `heldout_v6` exact 13). Vendored suite: 5488 passed (no fixture regression this round). Naming/docs/source-scanning
files 2405 passed. Two guards (the ylidene clause itself, the carbon restriction) were each removed in turn and a control row failed for both.

**Also found, not fixed:** plain thiohydrazides (`CC(=S)NN` is `(1-thioxoethyl)hydrazine`, not `acetothiohydrazide`) are a separate, pre-existing defect
independent of the hydrazone question -- the `fg:hydrazide` SMARTS matches only a carbonyl oxygen, with no generic chalcogen-swap path the way
carboxamide/carbothioamide share. Recorded in `KNOWN_LIMITATIONS.md`.


## 2026-09-27 -- naming round 23 (D-179): the chalcogen analogue thiohydrazide

Round 22 found this while fixing D-171 and left it open. P-66.3.4 (pdf p. 672), verbatim: "Chalcogen analogues of hydrazides are named substitutively
using suffixes formed by functional replacement, i.e., 'thiohydrazide', 'carbothiohydrazide' ..."; printed "propanethiohydrazide (PIN)" and
"benzenecarbothiohydrazide (PIN)" (both verbatim, matched exactly). `CC(=S)NN` was `(1-thioxoethyl)hydrazine` and is `ethanethiohydrazide`.

**The cause.** `fg:hydrazide`'s SMARTS matched only a carbonyl oxygen (`(=O)`); other suffix families (amide/thioamide, carboxylic/carbothioic acid)
already have their own separate chalcogen-analogue FG entries with the identical shape, but hydrazide had none. One new `thiohydrazide` FG entry mirrors
`hydrazide` exactly, `(=S)` for `(=O)`, keeping round 22's hydrazone-admitting terminal-nitrogen clause unchanged.

**Three more sites needed the new type name, all keyed on the literal string `"hydrazide"`:**
- `_N_BEARING_FG_TYPES` (Pass 2.5a's N-substituent carving) -- without it, every N-substituted or hydrazone thiohydrazide fell back to the pre-round
  wrong reading (`CC(=S)NNC` stayed `1-methyl-2-(1-thioxoethyl)hydrazine`).
- `_role_primes` -- without it, a single N'-substituted case got the WRONG prime, `N-methylethanethiohydrazide` instead of
  `N'-methylethanethiohydrazide` (the book's own convention, "the N bonded to the acyl carbon is N, the terminal one N'", P-66.3.1, applies unchanged
  to the chalcogen analogue).
- The anchor-in-parent guard around `_hydrazide_attaches_through_its_carbonyl` plus `_DEMOTED_AMIDE_TYPES_PREPROC` -- without these, a thiohydrazide
  anchored inside a longer acid chain (`NNC(=S)CCC(=O)O`) briefly emitted `4-hydrazinecarbonothioylbutanoic acid`, a WRONG STRUCTURE (the whole-group
  prefix `hydrazinecarbonothioyl` double-counts the anchor carbon when it is already IN the parent chain), caught by testing the anchor-in-parent shape
  before shipping, not by a printed example.

**One guard measured dead.** `_DEMOTED_AMIDE_TYPES_PREPROC`'s thiohydrazide entry was added for symmetry with `hydrazide`'s own entry, but every
anchor-in-parent shape tried (a chain, a ring, an N-substituted case, an ester's acid part) already reads correctly from the `_hydrazide_attaches_
through_its_carbonyl` guard alone; removing this one entry changes no row. Kept only so the function is right on its own, the same reasoning round 19
kept one dead nitric-hydrazide guard for.

**Measured.** Census scan (2000 rows): 0 rows changed class and 0 changed name -- the family is rare in a drug-like corpus, unlike round 22's
acylhydrazone-hydrazone family. ref-compare against master (`a1e623cd`): 1712 structures, **2 changed**, both the book's own printed examples
(`propanethiohydrazide`, `benzenecarbothiohydrazide`), both reading back, listed in `benchmarks/naming/stages/manifests/r23-release-candidate.toml`,
0 violations. **The blind frozen impact was UNCHANGED** on both `bluebook_frozen` (1126 rows) and `heldout_v6` (40 rows) -- the previous evaluation's
score (`r22-final-evaluation`) stands without re-scoring. Vendored suite: 5516 passed, no fixture regression. Naming/docs/source-scanning files 2417
passed. Nine guards (the FG entry itself, the carbon restriction on its hydrazone clause, and the three engine.py sites above, each split into their
two call sites) were each removed in turn and a row failed for eight of nine; the ninth is the dead preprocessing entry above.

**A cross-session note, not a code change.** A concurrent session was independently editing `docs/research/literature.toml` and adding
`benchmarks/thermophysical/` in this same working directory while this round measured its "before" baseline via `git stash`; the stash briefly swept
up their uncommitted work too. Recovered by restoring only this round's three files from the stash (`git checkout stash@{0} -- <path>` per file) and
diffing the stash against the restored files before dropping it, leaving the other session's newer, larger edit to that file untouched. Future
"before" baselines in a shared checkout should use a worktree or `git show <ref>:<path>` instead of `git stash`, which operates on the whole tree.

## 2026-10-05 -- naming round 24 (D-180, D-181, D-182): morphinans, a heptalene template, and Java for the engine's own OPSIN checks

Started from one molecule the app refused (a 3,14-diacetoxy-4,5-epoxy-6-oxo morphinan) and a 45-molecule battery of drugs and natural products named through
the app's own path (`derived_name_for_structure`). Before: 21 exact, 24 shown with "does not express stereochemistry", 1 refused. After: 41 exact.

**D-182 (the largest, and not in the engine): the app ran the engine without `java` on PATH.** The engine confirms stereo on a bridged or spiro parent by
parsing its own candidate name with OPSIN (`_validate_stereo_via_opsin`) and DROPS the descriptors when that fails. py2opsin shells out to a bare `java`, and the
app's managed JRE is on neither PATH nor JAVA_HOME, so every check failed and every bridged stereocentre was dropped: camphor came back `1,7,7-trimethylbicyclo[2.2.1]heptan-2-one`,
not `(1R,4R)-...`. The engine's own benchmarks and suites ran with Java on PATH, so none could see it. `naming_providers._java_on_path()` now wraps both engine
calls (`derived_name_for_structure`, `structure_annotation._name_ring_skeleton`). Mutation-checked: removing the wrapper fails `tests/test_derived_name_reaches_opsin.py`.

**D-181: the `heptalene` template was a 13-atom [8,7] skeleton** (`C1CCCC2CCCCCC2CC1`), so it never matched a real heptalene and fusion naming fell back to
`cyclohepta[7]annulene` as the parent: colchicine's core was `benzocyclohepta[7]annulene`, a name OPSIN reads as a different structure (the app withheld it). Now
`C1CCCCC2CCCCCC12`; colchicine is `N-[(7S)-1,2,3,10-tetramethoxy-9-oxo-5,6,7,9-tetrahydrobenzo[a]heptalen-7-yl]acetamide`. All 67 `POLYCYCLES` templates were then
checked against OPSIN's parse of their own name (atom count and ring sizes, skeleton isomorphism): no other mismatch. `tests/test_round24_polycycle_templates.py` pins the table.

**D-180: a retained parent MODIFIED by `didehydro` and an `epoxy` bridge.** P-13.8.1.1 (pdf p. 66) names morphine `4,5α-epoxy-17-methyl-7,8-didehydromorphinan-3,6α-diol`
on the retained parent `morphinan` (P-101.2). The retained lookup matched the saturated skeleton exactly, so levorphanol named and morphine, codeine, heroin,
hydromorphone, oxycodone, naloxone and thebaine fell to a von Baeyer pentacycle. New `ring_naming/retained_modified.py` (rank 45, like the methylenedioxy bridge):
strip at most one ether bridge, flatten ring double bonds into recorded `didehydro` locants, look the remainder up in the curated table, number by its `atom_locants`.
`epoxy` rides on a new `NamedParent.bridge_prefixes` and is alphabetized with the substituents by `_assemble_substitutive`, as the book cites it; `didehydro` is part of the
parent name. Only parents in `_MODIFIABLE` (morphinan) are eligible, because the book prints such a name for it.
Names are in `tests/test_round24_morphinan.py`, each read back through OPSIN with stereo.

**Measured.** Census (2000 rows): 1999 unchanged; one moved, a no-stereo 4,5-epoxymorphinan, von Baeyer name -> `1-bromo-4,5-epoxy-2-hydroxymorphinan-6-one`, which OPSIN reads
back with stereo the input lacks (exact -> same_connectivity, connectivity identical). Ref-compare 1712 structures, 0 names changed, 0 violations. Vendored suite passes.

**Left open (4 of 45).** atropine, scopolamine, galantamine and ibogaine are still shown with "does not express stereochemistry"; the cause was not diagnosed. The quaternary N-methyl morphinanium falls back to von Baeyer (charged systems are not eligible). A morphinan
N-oxide is named as an additive `17-oxide`, which OPSIN reads. The Blue Book also prints a furo-fused form for morphine; the epoxy form is used because OPSIN reads it back (the round-trip tests) and it is the book's own form for the demethyl example. Which of the two is the PIN was not settled.

## 2026-10-05 -- naming round 25 (D-183 to D-186): stereo kept on four natural products, and which ester of a polyester is the principal anion

Round 24 left two items open in `KNOWN_LIMITATIONS.md`; both were diagnosed first, and the four stereo losses turned out to have FOUR different causes, not one.

**D-183, atropine and scopolamine: a pseudoasymmetric descriptor poisoned the rest.** The engine writes `(1R,3r,5S)` (the lowercase `r` is P-91.2, stamped by `rdCIPLabeler`). OPSIN cannot read `r`/`s`, so
`_validate_stereo_via_opsin` rejected the candidate and its `bridged_or_spiro` mode stripped EVERY R/S, including the `1R,5S` OPSIN reads fine. New strip mode `pseudoasymmetric` (lowercase only) is tried first.
Both now keep what OPSIN can read: `(1R,5S)-8-methyl-8-azabicyclo[3.2.1]octan-3-yl 3-hydroxy-2-phenylpropanoate`. They still carry the "does not express stereochemistry" note, correctly: **tropine and pseudotropine
are the two C3 epimers and now share one name**, `(1R,5S)-8-methyl-8-azabicyclo[3.2.1]octan-3-ol`; the note is the only thing telling them apart. PubChem omits the pseudoasymmetric centre the same way.

**D-184, galantamine: the curated table had 8a and 12a swapped.** The entry's own comment says those two junctions were "deduced by topology", and only the probed locants were right. OPSIN settles it: `8a-chloro-...`
is a valency error (the quaternary carbon has no hydrogen), `12a-chloro-` lands on the aromatic carbon beside the CH2-N, and `(4aS,6R,8aS)-...-6-ol` reads as galantamine where the old `12aR` could not be parsed, so both
junction descriptors were stripped. Swapped back; galantamine now round-trips exactly as `(4aS,6R,8aS)-...`, PubChem's published set for natural galantamine. `test_fda_0605_galantamine_no_letter_suffix_stereo` had pinned the stripped `(6R)`-only name and its docstring blamed OPSIN; it is inverted and renamed `..._keeps_its_letter_suffix_stereo`.

**D-185, ibogaine: a bridged system named by FUSION has letter junction locants.** The descriptor gate admitted only plain integers for a bridged parent (right for von Baeyer names, which have no letters), so `6a` was
dropped before validation ever saw it. Admitted when the parent is not a von Baeyer or spiro name; the OPSIN validation still strips it if the name is unreadable. Ibogaine is now `(6R,6aS,7S,9S)-...`, exact.

**D-186, a polyester's principal anion followed the order its atoms were written in.** Equally scored plans fall to generation order, and the ester decompositions came out in atom order, so heroin and any diacetate of a
diol had a different name for each way of writing the SMILES (30 random SMILES each: 5 of 7 diester shapes tried gave two names). Now, on the EXECUTED trees (`_break_ester_tie`, the ester counterpart of
`_break_alphanumerical_tie`): (1) the senior ACID is the principal anion (P-65.6.3.3.3.2 method 2, "corresponding to that of acids"): a ring parent before a chain (P-44.1.2.2), then more skeletal atoms, then more
substituents (`_acid_seniority_key`); (2) among esters of the same acid, the alcohol component: ring parent before chain, then the lowest locant of its free valence, then its prefixes (P-31.1.4;
`_ester_alcohol_key`). `propyl` beats `propan-2-yl`, `hexan-2-yl` beats `hexan-3-yl`. A well-formed poly-ester reading (`dimethyl butanedioate`) is tried first and wins, as in the normal loop. Heroin moves to
`(5R,6S,9R,13S,14R)-6-(acetyloxy)-4,5-epoxy-17-methyl-7,8-didehydromorphinan-3-yl acetate`. At most four tied plans are executed (each alcohol can hold more esters, so the work multiplies); beyond four, or when a
component is not comparable (a retained acid other than formate/acetate/benzoate, a leaf alcohol), the order is RDKit's canonical class rank, which does not depend on atom order but is not a nomenclature rule.
**A first version ordered by the size of the acid side of the cut and was wrong**: for esters on one shared skeleton that side is nearly everything, and it made an acetate outrank a ring carboxylate (census rows
1404625, 1709625, 2069625). The ref-compare and census scan caught it; the executed-acid comparison replaced it.

**Not done: the book's PIN for a polyester is a different construction.** P-65.6.3.3.3.1 names identical anions multiplicatively, `ethane-1,2-diyl diacetate (PIN)`, `propane-1,2,3-triyl triacetate (PIN)`;
method 2 (acyloxy) is "acceptable in general nomenclature". The engine builds no multiplicative ester, so every polyester it writes is the accepted form, now at least a stable one.

## 2026-10-06 -- naming round 26 (D-187 to D-190): the esters of one polyol are named as the book names them

Round 25 left the book's PIN for a polyester unbuilt. P-65.6.3.3.3.1 (pdf p. 624) names the esters of ONE polyhydroxylic component with ONE acid functional-class-multiplicatively: `ethane-1,2-diyl diacetate (PIN)`, `propane-1,3-diyl bis(chloroacetate) (PIN)`, `propane-1,2,3-triyl triacetate (PIN)`; the acyloxy form the engine wrote (`2-(acetyloxy)ethyl acetate`) is "acceptable in general nomenclature" only. Building it meant naming a POLYVALENT organyl group, which nothing had asked of the generic substituent path, and that path was wrong in four ways. Measured first: OPSIN reads every identical-anion form (stereo and unsaturation included), and reads NONE of the different-anion forms.

**D-187, the multiplicative polyester (`polyol_ester`).** A new functional-class decomposition, the mirror image of the poly-acid reading (`polyester`: one acid, several alcohols): after cutting every ester O--C(alkyl) bond the alkyl carbons lie in ONE component, the acids are separate components, and they are the SAME acid. The alcohol component is carved as a bridging substituent with one free valence per ester and named `<organyl> <multiplied anion>`: `di`/`tri` for an unsubstituted anion, `bis`/`tris` for a substituted one (`bis(chloroacetate)`; the test is the anion's own tree, since `dichloroacetate` is a different anion), and an enclosed `di(prop-2-enoate)` where the name carries a locant. `_break_ester_tie` tries it before the single-ester readings, as it does the poly-acid one. Declined, so the molecule keeps its name: different acids, a senior group elsewhere, a second alcohol, a lactone, and any organyl group the generic path cannot name as one n-valent group (`_organyl_cites_valences`: the divalent group of `1,2-phenylenedi(propan-3,1-yl) diacetate` came out `3-(2-propylphenyl)propane-1-diyl`, one locant for two valences, which is a different molecule). Heroin is now `(5R,6S,9R,13S,14R)-4,5-epoxy-17-methyl-7,8-didehydromorphinan-3,6-diyl diacetate`.

**D-188, a polyvalent free valence was written with its multiplier twice.** `FREE_VALENCE_SUFFIXES` already carries `diyl` and `triyl`, and `render_free_valence_suffix` prepended `di`/`tri` as well: `ethan-1,2-didiyl`, `propan-1,2,3-tritriyl`, and `4yl` for four valences. Nothing reached it, because the multiplicative builder writes its own linkers. It now builds the word from the count of attachment points, and the parent keeps its terminal `e` before the consonant (`ethane-1,2-diyl`, `cyclohexane-1,4-diyl`).

**D-189, a divalent ring took the monovalent retained leaf.** `_generate_retained_plans` offered `phenyl`/`cyclohexyl` for a ring with TWO free valences, so hydroquinone's group was `phenyl`: a different molecule. A retained substituent form is one valence; with more the substitutive path names the group.

**D-190, the free valences were numbered by the first one alone.** For a ring substituent the numbering kept both directions once the first attachment was locant 1, and plan order chose: catechol was `1,6-phenylene`, 1,3-cyclopentanediol `cyclopentane-1,4-diyl`, pyrogallol `benzene-1,5,6-triyl`. P-31.1.4.2.4 ranks the free valences as a SET ahead of any prefix; polyvalent groups now go through the same lowest-set rule a hetero ring already had (`_lowest_free_valence_numberings`), and a chain compares the sets of both directions. Then P-29.6.1 (pdf p. 313): "`methanediyl` and `benzene-1,2-diyl` are not recommended in place of `methylene` and `1,2-phenylene`", and they stay substitutable, so a divalent benzene is `1,4-phenylene`, `2,6-dimethyl-1,4-phenylene`, and CH2 is `methylene`, `phenylmethylene`.

**Not built, with the evidence.** P-65.6.3.3.3.2 method (1), DIFFERENT anions on one polyol (`propane-1,2,3-triyl 1,2-diacetate 3-propanoate`, `1,4-phenylene acetate dichloroacetate`, `methylene acetate formate`), is the PIN, and OPSIN reads none of it: every form tried (with and without locants, `methanediyl`) is unparseable, the book's own five examples included. Those molecules stay on method (2) (`2,3-bis(acetyloxy)propyl propanoate`), which OPSIN confirms. Also not built: an organyl group that is itself multiplicative or a ring assembly (`1,2-phenylenedi(propan-3,1-yl)`, `[1,1'-biphenyl]-4,4'-diyl`, `oxydi(ethane-2,1-diyl)`), polyvalent groups on a branched skeleton (pentaerythritol), and the poly-acid/poly-alcohol mix of P-65.6.3.3.4 (`dimethyl ethane-1,2-diyl dibutanedioate`); all keep the acyloxy name they had.

**Measured.** Census, 2000 rows, master against this tree: the class distribution is identical (1958 exact, 97.90%; 14 same-connectivity, 12 candidate wrong structures, 9 visible failures, in both), and exactly THREE names change, all exact before and after: `ethane-1,2-diyl bis({[amino(phenyl)methylidene]amino}methanoate)` (was `2-({[amino(phenyl)methylidene]amino}(oxo)methoxy)ethyl ...`), `(pyren-1-yl)methylene diacetate` and `[(1S,2S,6R,7R)-4-(3-nitrophenyl)-3,5-dioxo-10-oxa-4-azatricyclo[5.2.1.0^{2,6}]dec-8-en-7-yl]methylene diacetate`. Ref-compare against master (1712 structures over r7, r8, mc, pop): TWO names change, `1-(butanoyloxy)ethyl butanoate` -> `ethane-1,1-diyl dibutanoate` and the held-out `3,4,5-tris(acetyloxy)-1,6-diisothiocyanatohexan-2-yl acetate` -> `1,6-diisothiocyanatohexane-2,3,4,5-tetrayl tetraacetate`, both read back by OPSIN on both sides: 0 violations against `r26-release-candidate.toml` (2 without it). A 73-molecule battery of polyol esters (diols to hexols, rings, phenylenes, stereo, unsaturation, and shapes that must NOT take the path) was read back by OPSIN: 73 of 73 the identical structure, stereo included. **The first battery run found the wrong numbering** (`1,6-phenylene`, `cyclohexane-1,6-diyl`, `benzene-1,5,6-triyl`), every one of which OPSIN also read as the right molecule: a round trip that passes is not a name that is right, and D-190 is what the battery's locants asked for. Fork suite 7189 passed, 9 failed: seven were the round 24/25 tests that pinned the acyloxy form (updated, then 246 ester-related tests pass), and two (`test_trindene_indicated_h_name`) fail identically on round 25's own commit `aa1059d`, so they are not this round's. App-side, the 45 registered naming-consumer test files: 2797 passed, 0 failed. The scripted app run on the diacetoxy-oxo morphinan: `VERDICT PASS`, the name `...-6-oxomorphinan-3,14-diyl diacetate`.

**Mutation matrix, and what it taught.** 28 mutants of the new rules and guards: 20 caught, 8 survived, and every survivor was read. (1) The acid-decline check duplicated `_has_error_children`, and four builder guards (distinct acyl/oxygen, ring bond, alkyl carbons in one component, ester O in its own component) were each implied, on every connected molecule, by "the components do not overlap and no atom is left over"; they were REMOVED rather than claimed, the builder is tested directly (macrocycle, two identical lactones, carbonate, stray fragment, two molecules, shared diacid), and 48 multi-ester census structures named before and after the removal differ in 0 names. (2) The last survivor, `polyol_ester` in `_break_ester_tie`'s gate, LOOKED equivalent and was not: when the polyol plan is built and then declines at execution (diethylene glycol, bisphenol A, pentaerythritol, any ether-linked diol), the gate is what lets round 25's comparison of the single-ester readings run, and without it 7 of 20 unsymmetric shapes moved to the canonical-rank fallback's choice (`...butan-2-yl acetate` for `...ethyl acetate`). Nothing tested it; four pinned names now do, and the final matrix is 23 of 23 caught. The first test written for that gate checked only that the name was STABLE, which the fallback also is, and the mutant survived it.

## 2026-10-06 -- a tie between von Baeyer numberings goes to the strategy layer, not to atom order

Found in naming round 25: `OC(=O)C1C2CCC(CC1O)N2C` was `3-hydroxy-8-methyl-8-azabicyclo[3.2.1]octane-2-carboxylic acid` for about half of its SMILES spellings and `...-4-carboxylic acid` for the rest, and cocaine likewise (`methyl (1S,2S,3S,5R)-...-2-carboxylate` or `methyl (1R,3S,4S,5S)-...-4-carboxylate`). Both names read back to the input, so only the tie-break was wrong, and no corpus could see it: a right name needs a symmetric skeleton AND a substituent on it.

**Cause.** `name_bridged` pins ONE numbering for every von Baeyer ring that has a heteroatom or a secondary bridge, because the heteroatom prefix and the unsaturation locant are written into the name text. `_choose_best_vb_locant_map` picked it by `score < best_score`, so on a tie the first numbering generated won, and generation order is sorted atom index. 8-azabicyclo[3.2.1]octane has two mirror numberings that tie on the heteroatom, unsaturation and locant-set scores, so the strategy layer was handed a single option and P-31.1.4 (lowest locants to the suffix, then the prefixes) never ran. Measured, not assumed: with the pin stripped, 40 of 40 random spellings give `-2-carboxylic acid`. The defect was wider than the two reported molecules: quinuclidin-3-ol came out `-3-ol`, `-5-ol` or `-8-ol`, and 7-azabicyclo[2.2.1]heptane-2,5-dicarboxylic acid `2,5` or `3,6`, depending on the spelling.

**Fix, in `ring_naming/bridged.py`.** (1) The two selectors (now `_best_vb_locant_maps` and `_best_vb_locant_maps_with_secondaries`) return EVERY map tied at the best score, and `name_bridged` pins all of them that write the SAME text (`_baked_name_parts`: secondary-bridge descriptor, double and triple bond locant pairs, heteroatom prefix). The text comparison is load-bearing and not decoration: the score ranks a bond by its lower locant but the name also cites the higher one, so `non-1-ene` and `non-1(8)-ene` tie. Pinning both let the strategy pick the second for `N1C2CCC=C1C(Cl)CC2` while the text said `2-chloro-9-azabicyclo[3.3.1]non-1-ene`, which OPSIN reads as a different molecule (12 of 24 spellings, measured with the filter neutralised). (2) A second tier in both scores, `_hetero_locants_by_element` (P-31.1.4.2.4): after the heteroatoms' locants taken together, the senior element takes the lower one. `2-oxa-5-azabicyclo[2.2.1]heptane` had come out as `5-oxa-2-aza...` in 12 of 24 spellings; those two numberings write different text, so (1) alone could not reach it. (3) The numbering that used to be the only option is pinned LAST. When the strategy layer cannot tell two numberings apart, the later-generated plan wins (the declared policy of `engine._search_plans` and `_break_alphanumerical_tie`), so offering the tie in generation order made the second numbering win the ties nothing can break. On round 25's atropine and scopolamine, whose tropane skeleton is meso, that gave `(1S,5R)-...` and `(1S,2S,4R,5R)-...` against the `(1R,5S)-...` and `(1R,2R,4S,5S)-...` their tests pin. Found by merging with #216 (master passed those tests, the merge did not); with the line removed they fail again.

**Measured, against master with round 25.** A 14-structure panel, 24 spellings each (random roots and random atom orders): 4 structures stable on master, 12 after. Cocaine, split `-2-` and `-4-carboxylate` on master once round 25 had settled its ester parent, is one name in 24 of 24. The census (2000 rows, canonical SMILES, OPSIN read-back): 4 names moved, every one `exact` before and after, and the class counts are identical (1958 exact, 14 same_connectivity, 7 unparsable, 11 mismatch_formula, 1 mismatch_same_formula, 8 naming_error, 1 refused). All four moved to a lower locant: `nonan-7-yl` to `nonan-3-yl`, `3,5-dichloro...2,4-diene` to `2,4-dichloro`, a dioxabicyclo[2.2.2]octene attached at 4 to attached at 1, a `dec-8-en-7-yl` to `-1-yl`. (Before item (3) it was nine; the other five were the meso tie below landing on its other face.) Ref-compare over 1712 panel structures: 2 names moved, both `bluebook_tuning` `dispiroter` rows that the engine cannot yet name in the book's form (neither the old nor the new name reads back), the spiro atom's locant on a 7-oxabicyclo[4.1.0]heptane component `5''` to `2''`; listed in `benchmarks/naming/stages/manifests/V1-vb-tie-break.toml`, 0 violations. Naming-consumer session 2680 passed, 0 failed; vendored suite 5532 passed, 0 failed, 0 skipped. Mutation-checked in `tests/test_namer_numbering.py` and `tests/test_round25_stereo_and_esters.py`: pinning only the first of the tie fails the substituent-tie cases, dropping the element tier fails `2-oxa-5-aza`, dropping the text comparison fails the read-back guard, dropping the pin order fails atropine and scopolamine.

**Round 24's cocaine row in `test_derived_name_reaches_opsin.py` pinned the defect.** It expected the carboxylate at 4 (`(1R,3S,4S,5S)-4-(methoxycarbonyl)-...octan-3-yl benzoate`), the second mirror numbering, chosen by atom order; round 25 swapped the row for borneol and recorded the defect. The tropane row is back, with the name that is now the same for every spelling: `methyl (1S,2S,3S,5R)-3-(benzoyloxy)-8-methyl-8-azabicyclo[3.2.1]octane-2-carboxylate` (12 of 12 atom orders through the app's own path; it reads back stereo-exact by InChIKey and the app's stereo check passes). The ester is a `carboxylate` and not a `...yl benzoate` because of round 25; the numbering is this change's. PubChem's cocaine SMILES is now one name in 24 of 24 spellings and is pinned in `tests/test_namer_numbering.py`.

**Left open, each measured identical to the base on the same spellings, so none is caused by this change.** (a) Numberings that tie on EVERY locant criterion (a meso skeleton: the imide `O=C(NN1C(=O)[C@@H]2[C@H](C1=O)[C@H]1C=C[C@@H]2C1)...`, `2,4-diphenyl-3-azabicyclo[3.3.1]nonan-9-ol`, the tricyclononene diester, tropine) still go by atom order, exactly as on master: `strategy._numbering_components` scores heteroatom, suffix and prefix locants and has no stereo-descriptor tier, so `(1R,2R,6S,7S)` against `(1S,2S,6R,7R)` is a coin flip (9/7, 12/4 and 12/4 of 16 spellings for the first three, tropine 12/12 of 24, the same counts and the same labels on master and here; the diester's two alkyl groups need locants on one side of the coin and none on the other). The rule that would settle it, CIP R before S at the first point of difference, is not implemented; it is consistent with the `(1R,5S)` and `(1R,2R,4S,5S)` that round 25 pins for atropine and scopolamine. (b) Tricyclic and larger cages use only `decompose_ring_system(...)[0]`, and the tied-score decompositions come back in an atom-index-dependent order, so 2-azaadamantane-type acids are named `2-aza`, `9-aza` or `10-aza` by spelling (six names, the same counts before and after). (c) The unsaturation tier ranks a bond by its lower locant, so `non-1-ene` against `non-1(8)-ene` is a tie decided by atom order (see the read-back guard); ranking compound locants needs a Blue Book rule not yet cited.

## 2026-10-06 -- when numberings tie, R takes the lower locant (P-14.4 (j))

A meso compound had two equally valid descriptor sets and the SMILES atom order chose: `C[C@H](O)[C@@H](C)O` was `(2R,3S)-butane-2,3-diol` or `(2S,3R)-butane-2,3-diol`, `C[C@H](Cl)[C@@H](C)Cl` and `C[C@H](Br)[C@@H](C)Br` the same two ways, `O[C@H]1CCCC[C@H]1O` `(1R,2S)-` or `(1S,2R)-`. OPSIN reads both forms to one structure, so nothing failed and no corpus row could see it.

**Cause.** The two numberings tie on every tier of the preference key (`strategy.preference_key`) and on P-14.4 (g), then fall to plan generation order, which follows atom order. Nothing implemented the criterion that settles it.

**The rule, as the book prints it** (BlueBookV2.pdf p. 79; the P-93 examples repeat it as "[see P-14.4 (j)]"): "when there is a choice for lower locants related to the presence of stereogenic centers", the lower locant goes to the CIP descriptors Z, R, M and r over E, S, P and s. The book's examples are decided by it: `(2R,4S)-2,4-difluoropentane`, `(2Z,5E)-hepta-2,5-dienedioic acid`, `(2R,3s,4S)-` and `(2R,3r,4S)-2,3,4-trichloropentanedioic acid`, and `(2Z,4S,8R,9E)-undeca-2,9-diene-4,8-diol`, where "the choice is between E and Z for position 2, not between R and S for position 4". (The task cited this as P-31.1.4.3.4, as did round 26's limitations note; in this PDF P-31.1.4 is the von Baeyer section, and the engine's own comments use that number for indicated hydrogen and heteroatom locants.)

**Fix, in `engine.py`, as the LAST criterion, after (g).** `_stereo_locant_key` reads a plan's `stereo_descriptors` (collected when the plan is generated, so no extra plan is executed to read them): the stereogenic units' locants first, then the descriptors' ranks in locant order, the first point of difference deciding. `_comparable_stereo` declines to compare candidates that do not describe the SAME stereogenic atoms, because a numbering that drops a descriptor (a junction locant a bridged or spiro parent cannot cite) has a shorter tuple and would win by length alone. It is applied in `_break_alphanumerical_tie`, where a name with no prefixes, which (g) cannot compare, is now compared on stereo when stereo can decide. Since naming round 26 (D-187) writes a polyol's diester as `<organyl>-diyl di<anion>`, the numbering of that `-diyl` group goes through the same function, which is how `(2R,3S)-butane-2,3-diyl diacetate`, the name the task asked about, becomes one name in every atom order with no stereo code in round 26. On round 26's tree without this change it was `(2S,3R)-butane-2,3-diyl diacetate` (stable, S-first), `(2S,4R)-pentane-2,4-diyl diacetate` likewise, and `cyclohexane-1,2-diyl diacetate` had two names, `(1R,2S)-` and `(1S,2R)-`.

**A tier on the ester route was built and removed.** Before round 26, `_break_ester_tie` named a meso diacetate by canonical rank: one name in 30 of 30 spellings, and S-first for 5 of 10 meso skeletons probed (`(2S,4R)-4-(acetyloxy)pentan-2-yl acetate`). An R-first tier there fixed all five and passed its tests, and on one skeleton nobody had tuned on, meso dipropylene glycol diacetate, it named `CC(=O)O[C@H](C)COC[C@H](C)OC(C)=O` `(2R)-1-[(2R)-2-(acetyloxy)propoxy]propan-2-yl acetate`, the R,R compound: OPSIN read back 6 of 7 stereoisomers with the tier and 7 of 7 without. A tie-break only chooses between trees that already exist, and one of the two candidates carried descriptors that do not describe the molecule (the alcohol component is named as a fragment of its own, and plans whose fragments print alike share a cache entry; the cis-1,3 diester showed the sharing from the other side, two plans, one set of descriptors). The tier was removed and `_break_ester_tie` has a comment saying why. After round 26 the diesters it was written for take the `-diyl` route, which has no such cache between its candidates. `test_every_stereoisomer_of_these_diesters_reads_back` is the guard; putting the tier back makes it fail on exactly that name.

**Measured, against master `f470933f` (which has #218 and round 26).** The 25 structures in `tests/test_namer_stereo_locant_tie.py` (18 pinned by name, 7 meso diesters pinned by their first descriptor), 13 spellings each (the written one and 12 random roots and atom orders, each checked to have the same InChIKey): with the key off, which is master's behaviour, all 18 named ones gave TWO names, and of the 7 diesters 2 gave two names, 3 gave one S-first name and 2 gave an R-first one by accident of rank; with the key on, the 18 give their one pinned name and the 7 give one R-first name. The 22 of those names OPSIN can read (3 carry a pseudoasymmetric `r`/`s`, which it cannot) read back to their structure, and so does every stereoisomer of five diester skeletons. Census (2000 rows, OPSIN read-back, master against this tree, `tools/naming_census_scan.py --out` run from separate directories, and a row-by-row diff of the two files): **4 rows moved, class counts identical** (1958 exact, 14 same_connectivity, 11 mismatch_formula, 1 mismatch_same_formula, 7 unparsable, 8 naming_error, 1 refused). Two are the von Baeyer meso skeletons that #218 lists as left open (a): the tricyclic imide `...(1S,2S,6R,7R)-3,5-dioxo-4-azatricyclo[5.2.1.0^{2,6}]dec-8-en-4-yl...` to `(1R,2R,6S,7S)-` and `(1S,2S,4R,5R)-2,4-diphenyl-3-azabicyclo[3.3.1]nonan-9-ol` to `(1R,2R,4S,5S)-`, both exact before and after. Two are older shapes: `6-{[(1S,5R)-3-hydroxyadamantan-2-yl]amino}adamantan-1-ol` to `(1R,5S)-` (unparsable before and after) and a `(2S,6R)-2,6-dimethylmorpholin-4-yl` to `(2R,6S)-` (exact). Each moved to R at the lower locant. Ref-compare (`naming_ref_compare.py --base f470933f --manifest benchmarks/naming/stages/manifests/P14-4j-stereo-tie.toml`, 1712 structures over r7, r8, mc and pop): 0 names changed, 0 violations; no standing population holds a meso pair, which is why no corpus could see this defect. Vendored suite (`tests/vendor/iupac_namer`, JRE on PATH): 5532 passed, 0 failed. Naming-consumer app session (`tools/naming_consumers.py --session app`): 2881 passed, 2 skipped (pre-existing), 15 xfailed, 0 failed. Mutation-checked in the new test file: flipping the rank table, ignoring the key in the numbering tie, comparing candidates that describe different atoms, letting stereo outrank (g), giving up on a name with no prefixes, putting descriptors before locants and not ordering them by locant each fail a named test, and putting the removed ester tier back fails the read-back guard on dipropylene glycol diacetate. One mutation is an EQUIVALENT mutant and no test can see it: running the no-prefix branch when the key cannot decide changes how many plans are executed, not which one wins.

**Not done, measured, in `KNOWN_LIMITATIONS.md`:** a meso compound whose two halves are each a candidate PARENT (an ether or amide of a meso diol) is still named by atom order, since the tie-break compares only the plans of one parent hypothesis; the acyloxy-form diesters round 26 leaves (multiplicative organyl groups) have no (j) tier and are chosen by canonical rank; the like-pair-before-unlike precedence of P-92.5.2.1 is not implemented. **Found on the way, not caused by this:** the R,S di-sec-butylbenzene is named as the R,R or the S,S, which OPSIN reads as a different stereoisomer (the app withholds it).

**It closes #218's "left open (a)".** #218 listed the von Baeyer meso skeletons (tropine, the imide, `2,4-diphenyl-3-azabicyclo[3.3.1]nonan-9-ol`, the tricyclononene diester) as decided by atom order for lack of a stereo-descriptor tier. Tried on a tree with both, before #218 reached master: tropine and pseudotropine go from 2 names each in 24 random SMILES to one, `(1R,5S)-`, and round 25's atropine and scopolamine pins hold; the census rows below are two of the others.

## 2026-10-06 -- the three von Baeyer ties the previous entry left open: meso skeletons, compound locants, and cages

The previous entry listed three numberings that still went by atom order, (a) a meso skeleton, (b) a tricyclic or larger cage, (c) `non-1-ene` against `non-1(8)-ene`. Each now has a Blue Book rule behind it, and each is the same name for every spelling that was measured.

**(a) A meso tie goes to the preferred stereodescriptor (P-14.4 (j)).** When two numberings tie on every locant criterion, the one whose CIP descriptors, read in locant order, prefer Z, R, M, r to E, S, P, s wins. `engine._break_alphanumerical_tie` sorts its candidates by `(locant_key, _stereo_locant_key(tree), -seq)`; a prefix-free tree gets `locant_key = ()` instead of aborting the comparison. This is general, not von Baeyer specific: the tie-break runs for every parent. The imide, `2,4-diphenyl-3-azabicyclo[3.3.1]nonan-9-ol` and tropane-3-ol are each one name in 24 of 24 spellings (`MESO_CASES`).

**(b) A cage is numbered from every decomposition that ties, superscripts before heteroatoms (P-23.2.6.2, P-23.3).** `vb_decompose.best_decompositions` returns all decompositions with the best score, where `_score_decomposition` now ranks the main ring's symmetric division (P-23.2.6.2.1) as well as coverage, main ring and main bridge. `bridged._best_vb_locant_maps_with_secondaries` numbers each one and scores the pairs by `(secondary-bridge superscripts as a set, in order, heteroatom locants, element order, unsaturation, substituent locants, all locants)`: P-23.3.1 fixes the hydrocarbon's numbering first and only then does the heteroatom set decide, so `2-aza`, `9-aza` and `10-aza` for the same 2-azaadamantane-type acid are one name. Element order is O, S, Se, Te, N, ... per P-23.3.2.2. (Earlier entries cite `P-31.1.4.2.4` for that order; the rule is P-23.3.2.2, and P-14.4 holds the general criteria. Those older citations are left as written.) `P-23.2.6.2.3` (fewest dependent secondary bridges) is not scored: the enumerator cannot produce a dependent bridge, so a criterion there could never fire; a mutation that added one passed every test, which is how that was found.

**(c) A compound locant ranks below a single one (P-31.1.4.2).** The unsaturation tier is `(-compound_count, -count, locants..., highs...)` (`preference.unsaturation_tier`): the numbering with the fewest compound locants such as `1(8)` wins, then the lowest locants ignoring the parentheses, then all of them. `bicyclo[4.2.0]octa-1(8),2,4-triene` is now `bicyclo[4.2.0]octa-2,4,6-triene` (24 of 24 spellings). The rewrite in `_recompute_ring_unsaturation_name` matched only a plain `-N-ene` locant, so a numbering chosen for its compound locant had its baked text and its numbering disagree; it now reads `N(M)` and rewrites from the final numbering, the all-compound case included.

**Measured.** Ref-compare over 1712 panel structures, base against this change: 25 names moved (23 read back on both sides, 2 on neither), 0 round-trip regressions, 0 fixes; all 25 are listed in `benchmarks/naming/stages/manifests/V2-vb-ties.toml` as MUST_CHANGE with the rule that moved them, 3 carrying a printed Blue Book name as `expected_name` (the book's own PIN, not the engine's output): the new name equals a printed target in those 3. Census scan over the same 2000 structures: 53 names moved, none changed class, and every class total is identical (1958 exact, 14 same_connectivity, 7 unparsable, 11 mismatch_formula, 1 mismatch_same_formula, 8 naming_error, 1 refused). Vendored suite 5532 tests: 5529 passed and 3 failed before three pinned names were updated, `bicyclo[4.2.0]octa-1(8),2,4-triene` to `octa-2,4,6-triene` (above) and `tricyclo[8.4.0.0^{4,9}]tetradeca-1(14),2,10,12-tetraene` to `tricyclo[8.4.0.0^{2,7}]tetradeca-1(14),8,10,12-tetraene` (twice), each reading back through OPSIN by InChIKey; the three files then pass, 82 tests with `tests/test_namer_numbering.py`.

**Mutation-checked in `tests/test_namer_numbering.py` (63 tests), each by undoing one fix and confirming the failure count:** best decomposition only (the old behaviour) 7 failed; symmetric division unscored 5; heteroatoms ranked above the superscripts 3; no stereo tier in the tie-break 10; compound count ignored 4; the rewrite reading only a plain locant again 2.

**Left open.** (a) The enumerator cannot produce a dependent secondary bridge, and a 28-atom tetracyclic such as the book's P-23.2.6.2.2 octacosane is beyond its cap, so that example is not matched. (b) A benzene ring inside a von Baeyer system is named from whichever Kekule form the input carries, so the ene locants of `C1=CC2=CC=CC=C2C3CCCCC13` are four names over 24 spellings (`1(14),8,10,12` 11, `2(7),3,5,8` 5, `2,4,6,8` 4, `1(10),8,11,13` 4, all read back); the base commit splits the same 11/5/4/4. That is a Kekule-form tie and no rule in this change reaches it. (c) The path that pins a heteroatom numbering still ranks an ene above a suffix, which sits uneasily with P-14.4 (c) before (e); it predates this change. (d) A spiro assembly can now prefer a fusion name over a von Baeyer component after the renumbering (census row 2048); that reads as the better name and is not guarded either way.

## 2026-10-06 -- "R precedes S" beyond the numbering: the citation order of prefixes, the parent of a meso compound, and the ester route (P-45.6.2, P-45.6.3, P-44.4.1.12)

The P-14.4 (j) entry above settled the NUMBERING of one parent. Reading the Blue Book's own stereo examples through the engine, and naming every stereoisomer of a few skeletons over random spellings of each, found three more choices that went by the order the SMILES atoms were written in. All read back through OPSIN, so no corpus could see them.

**1. The order two prefixes are cited in (P-45.6.3, BlueBookV2.pdf p. 427).** "When names based on alphanumerical order ... are the same, further choice depends on the alphabetic order of the stereochemical descriptors 'R' and 'S'": `1-[(1R)-1-bromoethyl]-1-[(1S)-1-bromoethyl]cyclopentane`, not S first. `derive_sort_name` sets the descriptors aside (P-14.5), and the sort that cites the prefixes was stable on it, so the order was the order the tree held them in. The R,S di-sec-butylbenzene, which the stereo cache fix made the right molecule, was `1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene` (the book's own example under (j)) or `3-[(2S)-butan-2-yl]-1-[(2R)-butan-2-yl]benzene` by spelling, 7 and 9 of 16; 1,3- and 1,4-bis(1-chloroethyl)benzene and the cyclopentane above did the same. The E/Z case was worse than unstable: criterion (g) broke the tie between equal sort names on name TEXT, and "E" sorts before "Z", so `1-[(1E)-prop-1-en-1-yl]-3-[(1Z)-prop-1-en-1-yl]benzene` put E at the lower locant, against (j). `assembly.stereo_citation_key` ranks a prefix name's descriptors in the order the name cites them with (j)'s own table (Z, R, M, r before E, S, P, s), and it is the second sort key at the three places assembly cites prefixes and in `engine._alphanumerical_locant_key`, so the order a name is written in and the locants (g) reads "for the substituent cited first" cannot disagree.

**2. Which half is the parent (P-45.6.2, p. 426; P-44.4.1.12, pp. 412-413).** A meso diether or diamide has two equal halves, either of which can be the parent, and the two names differ only in their descriptors: `{[(2R,3S)-3-phenoxybutan-2-yl]oxy}benzene` or `{[(2S,3R)-3-phenoxybutan-2-yl]oxy}benzene`, likewise `N-[(2R,3S)-3-benzamidobutan-2-yl]benzamide`, the 2,4-diphenoxypentane and the dibenzyloxybutane (each split 10 and 6, or 9 and 7, over 16 spellings). `_break_alphanumerical_tie` compares only the plans of one parent hypothesis, deliberately, and P-14.4 is a numbering rule; P-45.6.2 is the rule for choosing between two names that differ in nothing else: "the configurational symbols are compared and 'R' precedes 'S'". `engine._break_parent_stereo_tie` names each tied parent hypothesis as it would be named alone and, when the names are EQUAL once the descriptors are set aside (`_choose_by_configuration`, so a choice between two different names is never made on this ground), takes the one whose configuration is senior: the parent's own E/Z, then like before unlike (P-44.4.1.12.2: "like stereodescriptors such as 'RR', 'SS' have priority over unlike 'RS' and 'SR'"), then r over s, then R over S (`_parent_configuration_key`), then `stereo_citation_key` over the whole name. It engages only for a molecule that carries stereo (`_carries_stereo`), so an achiral molecule never pays for it, and a molecule with more than four tied hypotheses is left as before. **"Like" is judged only where the pair is unambiguous**, a parent with exactly two R/S descriptors; for more, the book pairs each centre with a reference descriptor from the digraph (P-92.5.2.1), which a name does not hold. The ether `CC(Cl)C(C)OC(C)C(C)Cl` is where like-before-unlike and R-first disagree: its halves can be (2S,3R) and (2S,3S), and the parent is now the like half, `(2S,3S)-2-chloro-3-{[(2R,3S)-3-chlorobutan-2-yl]oxy}butane`.

**3. The ester route.** The R-first tier in `_break_ester_tie` that was built and taken out of the P-14.4 (j) change, because it named meso dipropylene glycol diacetate as the R,R compound, is back (`_ester_alcohol_stereo_key`). It was not the tier. The session cache was keyed on `Chem.MolToSmiles` of a carved fragment, and a fragment's inherited CIP descriptors live in an atom property a SMILES cannot write (`context_stereo_key`, found and fixed in the stereo cache-key change, which also fixes the R,S di-sec-butylbenzene): the inner substituent fragment of either ester plan, `CC(=O)OC(C)C`, is the same text with its centre gone (the attachment carbon is capped), so the second plan reused the first plan's tree and its `(2R)`. With the key in place, meso dipropylene glycol diacetate is `(2R)-1-[(2S)-2-(acetyloxy)propoxy]propan-2-yl acetate` in every spelling, and every stereoisomer of six skeletons that were not tuned on (dipropylene and tripropylene glycol diacetate, the dibenzoate, a tartrate diacetate, the hexane-2,5-diyl and hydrobenzoin diacetates: 22 stereoisomers) is one name that reads back through OPSIN to the structure it came from.

**Measured.** Against the merge of the P-14.4 (j) change, master and the stereo cache fix (the tree these sit on): `tests/test_namer_stereo_parents_and_citation.py`, 51 tests, among them every stereoisomer of nine skeletons named over its spellings and read back; the census over 2000 rows (OPSIN read-back, `tools/naming_census_scan.py --out` from separate directories, row-by-row diff): **0 rows moved**, class counts identical, so the standing census holds none of these shapes either; ref-compare over 1712 structures (`benchmarks/naming/stages/manifests/P45-6-stereo-citation.toml`): 0 names changed, 0 violations; vendored suite: 5532 passed, 0 failed (5516 in the main run, and the 16 `test_tautomer_alignment.py` tests that skip without JAVA_HOME pass with it); naming-consumer app session: 3003 passed, 2 skipped (pre-existing), 15 xfailed, 0 failed. The Blue Book's own examples that apply: P-45.6.3, P-45.6.2 examples 2 and 3a and the (j) di-sec-butylbenzene come out as printed in every spelling; P-92.5.2.2 examples 1 to 3 (which OPSIN cannot read, so the structures were built with RDKit's CIP labeler) also. Mutation-checked, 16 mutants of the new rules: 13 failed a test at once, and three survived and were read (the citation key reading only the first descriptor group, the cross-parent comparison admitting names that differ in more than their descriptors, and the ester key's count slot), each now has a test that fails it, so 16 of 16.

**Not done, measured, in `KNOWN_LIMITATIONS.md`:** P-45.2.3, the parent chosen by the lowest locant set in order of citation, is not implemented, and none of the book's five FLAT examples for it is stable (the book's name 7, 5, 1, 6 and 7 times of 12); P-92.5.2.2 example 5's structure (13 centres) is named with four different chain descriptor sets over ten spellings on `66f112ed` and on this tree alike, so most are wrong, and OPSIN cannot arbitrate; like and unlike for a parent with three or more R/S descriptors; M and P in a prefix.



## 2026-10-06 -- two substituents that print as one SMILES are not one substituent: the naming session's cache key

`name_smiles('CC[C@@H](C)c1cccc([C@@H](C)CC)c1')`, the R,S di-sec-butylbenzene, returned `1,3-bis[(2R)-butan-2-yl]benzene` or `1,3-bis[(2S)-butan-2-yl]benzene` by the order its atoms were written in. OPSIN reads the first as the R,R compound and the second as the S,S, so both were names for a different stereoisomer. The Blue Book's own example under P-14.4 (j) (BlueBookV2.pdf p. 79) is the right name, `1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene (PIN)`. The app already withheld the wrong name (`derived_name_for_structure` raises "describes a different stereoisomer"), so a user saw no name rather than a wrong one.

**The cause is not the prefix merger,** which is where it was first looked for. Measured, not assumed: both prefixes reach `merge_identical_prefixes` already named `(2R)-butan-2-yl`, for the R,S input and the R,R input alike, and the merger correctly merges two equal strings. Carved at either ring bond, the two substituents are the same molecule, `CCCC` with the attachment on atom 3, because once the ring side is an H the centre is no longer a stereocentre; the inherited descriptor lives only in a `_ParentCIPCode` atom PROPERTY (stamped `R` on one and `S` on the other, which was right), and `MolToSmiles` cannot write a property. `engine._name_bound` keys the session cache on `Chem.MolToSmiles(mol)`, so the second lookup returned the first fragment's finished tree. With the lookup disabled the engine writes `1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene` in every spelling.

**Fix.** `extraction.context_stereo_key(mol)` writes the stamps a fragment carries, atoms and bonds, as a suffix (`|a3=R`; nothing for a fragment with none, so every unstamped fragment keeps exactly the key it had). `_name_bound` builds `fragment_key = smiles + context_stereo_key(mol)` and all 45 session-cache calls use it (one lookup, 44 stores, rewritten mechanically with a counted assertion); `smiles` itself stays the plain structure for the two curated oxoacid lookups and the error messages. Provenance (`_OcsOriginAtom`) is deliberately not in the key, or no two fragments would ever share an entry; two R,R substituents still share one, so the cache still hits. The other properties set on fragments (`_apsh_acyl`, `_carbanion`, `_orig_idx`) are local bookkeeping that never reaches `name()`, so `_ParentCIPCode` is the only property-carried naming input.

**Measured.** A sweep of nine substituent families on five parents (a 1,3-phenylene, an amine, an ether, an N-methylamine, a sulfide), every stereoisomer, five spellings each, every spelling checked to keep the isomer's InChIKey, every name read back through OPSIN: 2725 names. Before: 56 read back as another stereoisomer, in seven of the nine families and in nothing but a pair of the SAME substituent on the ring (on an amine, ether or sulfide one substituent becomes the parent, so nothing merges). After: 0 of 2725. The reported compound over 120 spellings: 63 are the book's name and 57 are the same two prefixes cited in the other order (below), all of them read back exact. A 15-shape probe of neighbours (diesters, tartaric acid, diol diacetates, a urea, amines, ethers), 25 spellings each on the base tree and on this one: identical except two. `1,3-bis(1-chloroethyl)benzene` R,S was a wrong isomer in 25 of 25 and now reads back; `CC[C@H](C)[C@H]1CC[C@@H]([C@H](C)CC)CC1` was `(1R,4S)-1,4-bis[(2S)-butan-2-yl]cyclohexane`, the same defect in a saturated ring, and is now `(1R,4S)-1-[(2R)-butan-2-yl]-4-[(2S)-butan-2-yl]cyclohexane`; OPSIN reads neither, so that one was checked against RDKit's CIP (the side chains are R and S, and each ring centre is paired with the side chain it carries). The round trip alone would not have found it.

**Mutation-checked in `tests/test_namer_stereo_cache_identity.py`** (22 tests; the failing case in every spelling, its converse, the app path, the premise that the two fragments print identically, the wiring, and a miniature of the sweep). Six breaks, each turns a test red: the key ignoring the stamps (the original defect, 12 tests), the key including provenance (2), leaving out bond stamps (1), the lookup going back to the plain SMILES (2), the store these molecules reach doing the same (2), and a store they never reach doing the same (1, an AST guard over every cache call in `engine.py`: the first draft of the file let that last one survive, and a store under the bare SMILES would be read by an unstamped fragment of the same SMILES). A first draft of the sweep itself found nothing (0 wrong in 1200), because its templates bonded the ring to the LAST atom of each substituent, so the "butan-2-yl" side was n-butyl; it was caught only by looking up the reported compound's own rows in the output. The sweep now contains the reported compound, and it is wrong on the base tree.

**Gates, measured on the merge commit `da1cfe0` (this branch with master through the von Baeyer ties, #226, merged in; naming round 26, #222, and #226 each landed on the same files while this was open), after earlier passes on the bases it was written against; none of the numbers moved.** The sweep: 56 of 2725 before, 0 after, on all three bases. The census (2000 rows, canonical SMILES, OPSIN read-back): 0 rows differ in name, read-back or class, and the class counts are identical (1958 exact, 14 same_connectivity, 11 mismatch_formula, 1 mismatch_same_formula, 7 unparsable, 8 naming_error, 1 refused). Ref-compare, `--base origin/master` (f7bc3c1, whose engine is the merge's parent 1cac2a0 with only CI and docs commits after it) against the merge commit: 1712 panel structures, 0 names changed, 0 violations, so `benchmarks/naming/stages/manifests/V3-stereo-cache-key.toml` lists no row; that says the populations hold no row of this shape, not that the change is a no-op, which is what the sweep is for. The neighbour probe (15 shapes, 25 spellings each, including round 26's polyol esters), run on the base before the von Baeyer ties came in: identical to the base except the two shapes above. Naming consumers, app session (46 files): 2905 passed, 2 skipped (a network test and a sources-guard exemption, both unrelated), 15 xfailed, 0 failed, with every strict xfail still holding. Vendored suite, run on its own with the JRE on PATH: 5532 passed, 0 failed (47 minutes; my test file is in the app session, not here). The tree-sweeping `_are_current` guards (`test_docs_are_current.py`, `test_sources_are_current.py`): 322 passed, 1 skipped.

**Left open, each measured identical on the base tree, so none is caused by this change (`KNOWN_LIMITATIONS.md`, "Open after the stereo cache fix").** (a) Prefixes that tie on their letters are cited in atom order, which P-14.5.4 (BlueBookV2.pdf p. 82) answers by the lowest locants at the first point of difference: the book's own `1-(pentan-2-yl)-4-(pentan-3-yl)benzene` is that name in 20 of 40 spellings on the base (it has no stereo, so this change cannot reach it), and the E,Z-propenyl pair is cited either way in 29 and 31 of 60 on the base tree. The fix makes the R,S compound reach this tie where it used to be a wrong name; both orders read back exact. (b) The P-14.4 (j) tie-break that master has had since the von Baeyer ties (#226, `engine._stereo_locant_key`) reads only the descriptors the PARENT carries, not those inside prefix substituents, so it does not decide this: with it merged in, the R,S compound is still 63 and 57 of 120 spellings and the E,Z pair 31 and 29 of 60, with E on locant 1 in every spelling where criterion (j) prefers Z. The unmerged branch `claude/amazing-grothendieck-ed467f` carries a tie-break of its own for the same rule, overlapping #226's; it was not tried against this case. Its `KNOWN_LIMITATIONS.md` has a bullet for this defect that blames "the prefix merger"; that diagnosis is wrong (above) and the bullet should go when it merges. Its strict xfail for the cis-1,3-cyclohexane diester is not moved by this change on this tree: the diester is named identically on the base and here in 25 of 25 spellings, measured before #226 came in. The branches were not tried merged. **Update, the same day:** (a)'s R,S and E,Z orders and (b) are closed by the entry above ("R precedes S" beyond the numbering), which cites the prefixes R before S and Z before E; what is still open is P-14.5.4 for prefixes that tie on their letters alone (`1-(pentan-2-yl)-4-(pentan-3-yl)benzene`).

## 2026-10-06 -- a group's bonding number and a prefix's nuclide are named (D-191, D-192)

The Blue Book's own P-45.2.3 examples 11 and 12 (BlueBookV2.pdf p. 422) were named by the engine as a DIFFERENT molecule each. Example 11, `3-[2-bromo-1-(λ5-phosphanyl)propyl]-5-chloro-4-(λ5-phosphanyl)hexanoic acid`, came out with `phosphanyl` for `λ5-phosphanyl` (C9H18BrClO2P2 read back for C9H22BrClO2P2); example 12, `4-(81Br)bromo-3-[1-(81Br)bromo-2-bromopropyl]-5-chlorohexanoic acid`, came out with no label on any bromine. Neither was recorded. Both are one defect met at several places, so each is fixed at the rule and not at the example.

**D-191. A group's bonding number was part of no name.** `_SINGLE_ATOM_SUBSTITUENT` is keyed on (element, charge, bond order), with no term for the atom's hydrogens, so a one-atom group named from a carved fragment was the ordinary prefix whatever its valence: `[PH4]`-, `[SH3]`-, `[SH5]`-, `[AsH4]`-, `[SeH3]`- and `[IH2]`- were `phosphanyl`, `sulfanyl`, `arsanyl`, `selanyl` and `iodo`, each read back with two to four hydrogens fewer. The book prints the number on the prefix, `(λ5-phosphanyl)`, `(λ6-sulfanyl)`, `(λ4-sulfanylmethyl)` (P-45.3, p. 423). Five places lost it, found by following one atom through every route that could name it, and each is fixed:

1. the carved one-atom route (`_name_single_atom_substituent`), from the atom's bonding number (`_hypervalent_group_name`: `valence - 1 + bond order` in a fragment whose cut bond became a hydrogen, which is 5 for `-PH4` and for `=PH3` alike), reusing the ring code's `_STANDARD_VALENCE`; it also names `=PH3` (`lambda5-phosphanylidene`), which the table had no entry for;
2. the oxo/thioxo fallback, which made `=SH2` and `=SH4` `thioxo` (read back as `=S`);
3. the ring-carbonyl synthesis, which promoted any terminal double-bonded chalcogen on a ring or ketone carbon to a thione whatever its hydrogens;
4. the thione, selone and tellone SMARTS, whose bare `(=S)`, `(=[Se])`, `(=[Te])` asked nothing of the chalcogen's connectivity (`=[SeH2]` was a selone); they are `(=[SX1])` and so on now;
5. the heteroatom-centre PARENT: `C[PH4]` was `methylphosphane`, `c1ccccc1[PH4]` `phenylphosphane`, `C[PH2](C)C` `trimethylphosphane`. They are `methyl-lambda5-phosphane`, `phenyl-lambda5-phosphane` and `trimethyl-lambda5-phosphane`, with the hyphen the book prints before a lambda descriptor (`triphenyl-λ5-phosphanone`, `pentamethoxy-λ5-phosphane`, pp. 769-770; `_needs_hyphen_before_stem`). Only a centre that still carries a hydrogen of its own takes the number: `CP(C)(C)(C)C` stays `pentamethylphosphane`, which OPSIN reads and which loses nothing (the book's `pentamethyl-λ5-phosphane` is D-195, open). **The hydrogen standing for a carved substituent's cut bond is not one of the molecule's**, and counting it was this change's first mistake: it moved 13 of 2000 census rows, every phosphoryl group among them (`(oxo)phosphanyl` to `(oxo)-lambda5-phosphanyl`), with the class table identical. The free valence's own hydrogen is discounted now.

**D-192. A nuclide on a one-atom prefix was named by nothing.** `collect_isotope_labels` labels the atoms of the PARENT and its suffix groups and drops the label of any other atom, so a labelled halogen, hydroxy, amino, sulfanyl, selanyl, oxo or imino prefix read back unlabelled. P-82.2.1 (p. 853) puts the nuclide in front of the group, `(81Br)bromo`, `(18O)hydroxy`, with no locant for one atom (P-82.6.1.2, p. 860). `isotope.isotopic_prefix` does, at the three places a one-atom prefix is built: the FG prefix, only when the prefix IS the name of the one atom it owns (`cyano` and `carboxy` own atoms of a group and are not labelled on a guess, D-193), the `halogen_prefix` role, and the carved one-atom route (`CO[81Br]` is `{[(81Br)bromo]oxy}methane`). Three consequences are in the book and are in assembly: a labelled one-atom prefix is not a compound one (no marks of its own, `4-(81Br)bromo-3-...`; enclosed when multiplied, `1,2-di[(81Br)bromo]ethane`, the book's `1,2-di[(13C)methyl]benzene`), it is cited before an otherwise identical plain one and never merged with it (P-82.2.2.1, p. 854: `1-(81Br)bromo-2-bromoethane`, not `1,2-dibromo...`), and a nuclide is not alphabetised (`derive_sort_name`, P-14.5, p. 80). That last was an existing defect: `(1-13C)methyl` was filed under "13cmethyl" and cited before `ethyl`, `1-[(1-13C)methyl]-2-ethylbenzene` for `1-ethyl-2-[(1-13C)methyl]benzene` (D-192r, D-192s; right molecule, wrong order). `is_nuclide_token` reads the element symbols from the periodic table once, because asking RDKit for a symbol it lacks (`R` of `(2R)`) logs a C++ violation each time, and tests that a mass number is not below the atomic number (`2S` is a stereodescriptor, not a sulfur of mass 2).

**Measured, against the unedited tree (`1030bc96`, an archive of it run in its own process).**

- **The two examples.** Example 11 and 12 as OPSIN reads the book's names: both now read back exact, and both are the book's PIN. In the canonical spelling the application names, both are the book's REJECTED order (D-191p, D-192p; D-194a, D-194b are the strict xfails for the book's): the parent chain is chosen by atom order, the P-45.2.3 gap already recorded, which the P-45.2.3 branch closes for them: with `claude/nice-franklin-ca57cd` (`c67d10b1`) and this change together, in a scratch copy, both are the book's name in 40 of 40 spellings, and six tests flip (see `KNOWN_LIMITATIONS.md`). Over 40 random spellings each, on this change alone: example 11 gives the book's name 19 times and the other 21 (its unlabelled `[PH2]` analogue 22 and 18), example 12 21 and 19, the P-45.4.1 ether 24 and 16; every name reads back exact.
- **The rows.** 45 FIXED rows and 10 OPEN rows in `tests/test_namer_known_defects.py`; of the 20 D-191 rows 17 read back as a different molecule before and none does now (the other three, D-191r to D-191t, are a phosphorus with one real hydrogen, read right before only because OPSIN supplies the hydrogen), of the 25 D-192 rows 23 did and none does now (D-192r and D-192s are the ordering rows). Every row's "former name" was run against the unedited tree, and every target, open ones included, is read back by OPSIN on canonical SMILES and InChIKey. 33 control rows (a group at its standard number, a phosphoryl group, an unlabelled prefix, a label on the parent) name identically before and after.
- **What the application does.** On the unedited tree with OPSIN present it WITHHELD both examples and two minimal shapes ("did not parse back to this structure"); with OPSIN absent (`opsin_available` forced false) it SHOWED them marked "Not verified: no offline parser available to check it". With the change all five shapes in `tests/test_naming_providers.py` are shown verified with an empty note, and the case still open (D-193a, `[15NH2]c1ccccc1`, named `aniline`) is still withheld.
- **Census, 2000 rows** (`tools/naming_census_scan.py`, OPSIN read-back; the baseline from an archive of the base commit, the edited tree from its own directory): class totals identical (1958 exact, 14, 11, 1, 7, 8, 1). Row by row: 3 rows moved, all of them a five-bonded phosphorus with one real hydrogen (`COc1ccc([PH](Cc2ccccc2)(c2ccccc2)c2ccc3ccccc3c2)cc1`, `Cc1ncc(C[PH](c2ccccc2)(c2ccccc2)c2ccccc2)c2c1OC(C)(C)OC2`, `COC(=O)[C@@H]1CCCN1C[PH](=O)[O-]`), `exact` before and after, the OPSIN read-back structure identical. The first version moved 13.
- **Reference comparison** (`tools/naming_ref_compare.py --base 1030bc96`, `benchmarks/naming/stages/manifests/D191-D192-lambda-and-nuclide-prefixes.toml`): 1712 structures, 2 names changed, both STRUCTURALLY_EQUIVALENT (a P and an As with one real hydrogen), 0 violations. The first version moved 8.
- **Suites.** The vendored suite, its own pytest process with the JRE on PATH and JAVA_HOME set: 5,632 passed and 0 failed in 31 minutes (the vendored half of the known-defects table among them: every FIXED row's engine output and every FIXED and OPEN target read back by OPSIN). The application session (`tools/naming_consumers.py --session app`): 3,181 passed, 2 skipped, 25 xfailed and 0 failed in 9 minutes (the 25 xfails are the 15 open rows that were there and these 10); `tests/test_namer_known_defects.py` alone is 1,553 passed and 25 xfailed.
- **Mutation-checked.** 21 undone fixes (each of the five lambda sites, the hyphen, the label at each of the three sites, the compound-prefix and `di[...]` rules, the sort name, both citation keys, the element lookup and the placeholder-hydrogen discount): 20 turn a test red. The survivor, the isotope key inside `_alphanumerical_locant_key`, is shadowed by the final `m.name` element, since `(` sorts before a letter; it is kept to mirror assembly's order. The first run of the matrix printed "OLD STRING NOT FOUND" for six mutants (the sources are CRLF), which tested nothing, and one that ran survived for a real reason (no row reached the carved route with a label): three rows were added.

**Open, each measured and in `KNOWN_LIMITATIONS.md` ("Open after D-191 and D-192"), none caused by this change:** a nuclide on an atom a retained parent name or a multi-atom prefix owns (D-193: `[15NH2]c1ccccc1` is `aniline`, wrong molecule; withheld by the application), P-45.2.3 examples 11 and 12 and P-45.4.1 (D-194, and P-45.4.1 to P-45.4.3 do not exist), a hypervalent centre with no hydrogen (D-195), the parent's descriptor placed before the prefixes where OPSIN cannot read it (D-196). The fork (`xaerogonzo/open-iupac-namer`) has not been ported: `engine.py`, `assembly.py`, `isotope.py` and `data/functional_groups.json`, plus the rows of `test_namer_known_defects.py`, which the port tool does not carry.


## 2026-10-06 -- one stereoisomer, one name: the parent chosen among chains that differ only in configuration

P-92.5.2.2 example 5's structure (BlueBookV2.pdf p. 900; 13 stereogenic centres, six equal arms on two quaternary carbons) was named by the order its atoms were written in. Over random spellings of that ONE stereoisomer, each checked by InChIKey: 13 names over 30 spellings on master `eb771e6d` (8 over 10 on `66f112ed`, as first reported); 16 over 30 once the session-cache fix (#229) was in; 4 over 30 with the "R precedes S" follow-up (#232); **1 over 40 now, the book's `(2R,3R,5R,7R,8R)-2,8-dichloro-4,4-bis[(2S,3R)-3-chlorobutan-2-yl]-6,6-bis[(2S,3S)-3-chlorobutan-2-yl]-3,7-dimethylnonan-5-ol`.** The note this replaces said "at most one set describes it", and that was true only of the first row: after the cache fix every descriptor in every one of the 16 names was RDKit's `rdCIPLabeler` label for the atom it describes (parent and prefixes, checked per atom), so they were sixteen CORRECT names of one molecule, each on a different one of its nine equal chains. Only the choice of chain was left to atom order, which no per-descriptor check or read-back can see and a count of names over spellings can.

**Cause: the choice was written (#232, `_break_parent_stereo_tie`) and did not engage here, for two reasons it could not have met on the diether and diamide it was built on.** (1) It named every tied parent hypothesis side by side up to a bound of four, and this molecule has nine; only four of them are different, since the two arms of a quaternary carbon that carry one configuration are one choice. (2) It compared two parents only when their names were equal "once the descriptors are set aside", by deleting the descriptor groups from the FINISHED text, and the descriptors decide how prefixes merge: the chain through one arm reads `4,4-bis[(2S,3R)-...]` and through another `4-[(2R,3R)-...]-4-[(2S,3R)-...]`. Measured separately: raising the bound alone changed nothing (the same four names in the same 12, 7, 6 and 5 of 30), so the first obvious blocker was not the blocker.

**Fix.** `engine._plan_identity(mol, plan)` writes the molecule as a canonical SMILES with every parent atom labelled by the ordinal of its locant (a carved fragment's inherited descriptors, which a SMILES cannot write, as isotopes), so hypotheses a configuration-preserving symmetry of the molecule relates are one, and the bound (now 12, which is three arms at each end all different, 3 x 3, with room; measured 15 ms per hypothesis compared on this molecule) counts distinct choices. `assembly.assemble_without_stereo(tree)` assembles with the two descriptor-writing sites suppressed (a `ContextVar`, reset in a `finally`), so the arms are alike and merge alike; `_choose_by_configuration` compares those. The choice itself (P-44.4.1.12.2, BlueBookV2.pdf p. 413: E/Z, like before unlike for exactly two descriptors, r before s, R before S) is #232's, unchanged. 9 hypotheses are 4 distinct ones here, and the chain it picks is the book's.

**Measured.** `tests/test_namer_stereo_parent_choice.py` (18 tests): the book's molecule over 24 spellings and its descriptors per atom against RDKit's whole-molecule labels (through each prefix's `atom_origin`, with every labelled centre described exactly once); eight more stereoisomers of the skeleton, among them `4s`, `4r`, `6s`, `6r` pseudoasymmetric ones, 4 spellings each; the defect kept alive (the tie-break switched off gives several names); nine chains are four choices; the four differ in nothing but configuration only when assembled without it; the bound counts distinct choices (4 holds, 3 does not); and `_plan_identity` on made-up plans. A wider sweep outside the file: 60 random stereoisomers of the skeleton, 4 spellings each, 60 of 60 one name and right per atom; the same sweep on the #232 tip gave 12 of 12 sampled isomers two to four names. Mutation-checked, 9 of 9 caught: the tie-break off, the equality back to the finished text, no deduplication, no stamp in the identity (caught only by the unit test on made-up plans: no molecule here reaches that path), suppression never on, suppression leaking past the call, the locant ordinal dropped from the identity, the naming method dropped from it, the bound back to 3.

**Gates.** `tools/naming_ref_compare.py --base origin/claude/p14-4j-follow-ups` (060ac90, the tree this sits on) against the working tree: 1712 structures over r7, r8, mc and pop, 0 names changed, 0 violations, against `benchmarks/naming/stages/manifests/V4-stereo-parent-choice.toml` (no row listed). The census, 2000 rows, canonical SMILES, OPSIN read-back, each side scanned from its own working directory: 0 of 2000 rows differ in name, read-back or class from either the #232 tip (060ac90) or master (1e2a3034), and those two agree with each other; the class counts are identical (12 candidate wrong structures, 0.60%; 9 visible failures, 0.45%, on all three). The vendored suite (its own pytest session, JRE on PATH and JAVA_HOME set): 5532 passed, 0 failed, 0 skipped. The naming-consumer app session: 3021 passed, 15 xfailed, 2 skipped, 0 failed over 49 files (the skips are unconditional: a test that hits the network and a data file with no literature source).

**Left open (`KNOWN_LIMITATIONS.md`).** (a) Like before unlike is judged only for a parent with exactly two R/S descriptors, so for example 5's five-descriptor chain the choice is made by R before S, which agrees with the book here; a case where the two disagree (an all-S chain against a mixed one) is not exercised by anything. (b) The Blue Book applies P-44.4.1.12 BEFORE P-45.2.1 (the number of substituents), and the engine applies the choice only between plans that tie on the whole preference key, whose `substituent_count` and `prefix_locants` tiers come first; two chains that differ in configuration AND in substituent count would be chosen on the count. Read off the book's order and the key's tiers, not measured to occur. (c) More than 12 distinct tied hypotheses are still left to atom order. (d) The stamp branch of `_plan_identity` has no molecule that reaches it, only a unit test.


## 2026-10-06 -- P-45.2.3: of two parent structures that tie, the one whose prefixes have the lower locants in their order of citation

"The preferred IUPAC name is based on the senior parent structure that has the lower locant or set of locants for substituents cited as prefixes to the parent structure (other than 'hydro/dehydro' prefixes) in their order of citation in the name" (BlueBookV2.pdf p. 419). It comes after P-45.2.1 (the maximum number of prefixes) and P-45.2.2 (the lower locant SET), and both are tiers of the preference key, so two plans that tie on the key have the same set and only the order of citation is left: `3-chloro-7-[(4-chloro-3-nitroquinolin-7-yl)sulfanyl]-4-nitroquinoline` reads `3,7,4`, its rival `4,7,3`. The engine took whichever parent its plan order gave first, and plan order follows the order the SMILES atoms were written in, so one molecule had two names and both read back to it: nothing failed and no corpus row could see it.

**The rule.** `engine._break_parent_stereo_tie` is now `_break_parent_tie`. It still names each tied parent hypothesis as it would be named alone (its own numbering tie-break first, then up to `_PARENT_TIE_HYPOTHESES` DISTINCT ones: 4 when this was written, 12 since #235 counts choices and not chains), and no longer returns at once for a molecule that carries no stereo. `_senior_by_citation_locants` reads `_citation_locants` of each tree (`_alphanumerical_locant_key` flattened, so the locants are read as the name writes them: `1,5,1,6` before `1,6,1,5`, `N,3` before `3,N` by `Locant.__lt__`) and keeps the trees with the lowest value. The groups are flattened, not compared one prefix at a time, because between two PARENTS the prefixes are split differently (the book's example 8). It engages only when every tree is the same parent once prefixes and descriptors are set aside (`_parent_name_alone`: `quinoline`, `heptanoic acid`), which is the guard `_choose_by_configuration` already had for P-45.6: the key does not hold every criterion that tells two different parents apart, and a lower locant must not stand in for one. Hydro prefixes are not in `tree.prefixes`, so "other than hydro/dehydro" holds by construction (checked on a tetrahydronaphthalene). When it rules some parents out, the survivor (or, among survivors, the one P-45.6 prefers, else the first) is returned, because falling through would name the TOP plan's parent, which may be one just ruled out. What it leaves tied goes to P-45.6 for a molecule that carries stereo, and to plan order otherwise, as before. P-45.3, P-45.4 and P-45.5, which the book places between P-45.2.3 and P-45.6, are not applied across parents.

**The book prints fifteen examples, not five (pp. 420-422).** Over 13 random spellings each, before and after: examples 1, 2, 3, 4, 5, 7, 8, 10, 14 and 15 had the book's name 7, 4, 5, 8, 10, 8, 7, 8, 8 and 6 times and have it 13 of 13; the other name, the one the book says is not preferred, was the rest. Example 13 was already 13 of 13 (the book frames it as a choice between two numberings of one chain). Examples 6 and 9 are blocked by a criterion that comes first and is not implemented, **P-44.4.1.1** (p. 401, "the senior ... principal chain has the greater number of multiple bonds"): `strategy._parent_selection_score` counts unsaturation INFIXES, so a `1,3-diene` and a `1,3,13-triene` tie in `parent_selection`, and the `unsaturation_locants` tier that sees them next is only meaningful between numberings of one parent and ranks the shorter set higher. The engine names both molecules as a diene with an ethenyl substituent on 13 of 13 spellings (`12-ethenyl-8-(3-ethyl-4-methylhex-5-en-1-yl)-11-methyltetradeca-1,3-diene`); a throwaway patch that counts the bonds an infix names makes this rule give the book's name for both on 13 of 13, so it covers them once the count is right. Not shipped: the count would change the parent wherever two chains of equal length differ in the number of multiple bonds, which has not been measured and needs its own census. Examples 11 and 12 could not be named at all until D-191 and D-192 (xaerogonzo/OpenChem-Studio#238, merged while this was open) made the engine write a `[PH4]` group's lambda number and a labelled bromine's label; with both, this rule gives the book's name for them too, on 13 of 13 spellings each (example 11 in the engine's `lambda5` spelling, where the book prints the glyph). That closes #238's open defects D-194a and D-194b, and the six tests that pinned the rejected order (D-191p, D-192p, D-194a, D-194b and two rows of `tests/test_naming_providers.py`) moved to the book's names with it. The three examples of P-45.5 (the name earlier in alphanumerical order, `bromo` before `dibromo`) tie on this rule by the book's own words and are still two names over the spellings (the book's name 7 of 13, 5 of 13 and 6 of 13).

**A wrong molecule the rule exposed, and the fix.** `N,N'-dibenzoylhydrazine` came out as `N-benzoylbenzohydrazide`, which OPSIN reads as the N,N-diacyl isomer; `CC(=O)NNC(C)=O` as `N-acetylacetohydrazide`. The vendored suite's `test_fixed_defect_round_trips_end_to_end[D-075f]`, `[D-088a]` and `[D-117e]` caught it. The cause was not the rule. A diacylhydrazine has two hydrazide groups that share one N-N, and `_role_primes` (the N and N' roles of a hydrazide, thiohydrazide or amidine group) processed the group of the OTHER parent as well, whose roles then overwrote the first's: for the parent that came out second the terminal nitrogen was cited as `N`. Plan order took the other parent first for the two symmetric molecules (24 of 24 spellings of each, on the tree before), so nothing there was wrong until `N`, which is lower than `N'`, met the wrong tree; for an unsymmetrical one it did not, and `O=C(C=Cc1ccc(F)cc1)NNC(=O)Cc1ccccc1` was the 2000-row census's one `mismatch_same_formula` row (`3-(4-fluorophenyl)-N-(phenylacetyl)prop-2-enehydrazide`, now `...-N'-(phenylacetyl)...`). `_role_primes` now skips a group whose acyl carbon is neither in the parent nor bonded to it. A tie-break is only as good as the worst tree it is offered (the ester route's R-first tier and the P-14.4 (j) cache key said the same): the choice cannot be tested without also reading the candidates back.

**Measured.** Against the tree it sits on (the merge of #227, #229 and master at #231). The census (2000 rows, canonical SMILES, OPSIN read-back): 3 rows moved, two of them this rule (`N` against a numeral, both `exact` before and after) and one the hydrazide fix (`mismatch_same_formula` to `exact`); 1958 to 1959 `exact`, 1 to 0 `mismatch_same_formula`, every other class identical. A canonical spelling cannot see an atom-order choice, so every census row was also named over 6 random spellings on both trees: 55 rows had more than one name before and 50 do now (this rule stabilised the two above, the hydrazide fix three `N`/`N'` rows; none was made unstable; no name appeared that the tree before did not already give for that row). The 50 are not this rule's: 26 name a polycyclic skeleton (von Baeyer numberings and double-bond positions), one is `N7` against `N9`, and 23 are other ties (spiro numberings, which end of a chain is the parent, `(phenylsulfinylsulfonyl)benzene` against `(phenylsulfonylsulfinyl)benzene`, a P-45.5 case). Each of the three rows the hydrazide fix stabilised was an `N` against an `N'` name for one molecule.. `tools/naming_ref_compare.py`: 5 of 1712 panel names changed, all in `bluebook_tuning`, all round-trip before and after, two of them the book's examples 3 and 15 now carrying the book's name; each is a `MUST_CHANGE` entry in `benchmarks/naming/stages/manifests/P45-2-3-citation-locants.toml`. Instrumented over the census, the rule was reached on 176 of 9,317 calls to the tie-break (at every recursion depth, substituent fragments included), decided 2, tied 174 (symmetric parents), and its same-parent guard never declined there, so what it does when it declines is tested only on made-up trees. `tests/test_namer_parent_citation_locants.py` pins the book's names over 16 spellings each, the same spellings splitting without the rule, both names of each pair read back to one molecule, the comparison and the wiring of `_break_parent_tie` on stand-ins, the hydrazide cases, and the open defects as strict xfails. One pinned name in `tests/test_namer_known_defects.py` changed (`CN(N=O)NN`): it was `2-amino-1-methyl-1-nitrosohydrazine` on 11 of 24 spellings and `1-hydrazinyl-1-methyl-2-oxohydrazine` on 13 before, both read back to one molecule, and is the second on all 24 now (`1,1,2` against `2,1,1`); the pin recorded the canonical spelling's name only. Gates, on the tree rebased onto master at #234 (#227 and #232 had merged while this was open; the naming code and tests were byte-identical to the tree the other numbers here were measured on): the naming-consumer app session (`tools/naming_consumers.py --session app`) 3079 passed, 2 skipped, 20 xfailed, the xfails including this file's five (P-44.4.1.1 and P-45.5, strict); the vendored suite, its own session, 5532 passed (the first run, before the hydrazide fix, was 3 failed of 5532); the rule's own file is 81 tests. CPU time to name the 2000 census rows, base and new run side by side so that the machine's load is the same for both: 315.0 s and 314.8 s, then with the launch order swapped 240.8 s and 240.3 s, so the rule costs nothing measurable (two single runs one after the other had read 362 s and 437 s, which was other sessions' load changing between them). Thirteen mutations are each killed by that file: the rule off, the higher locants winning, locants read group by group, no same-parent guard, no length guard, a parent the rule ruled out named anyway, the last survivor taken instead of the first, locants compared by their label (so `N` after a numeral), P-45.6 tried before P-45.2.3, a cap of one parent, the configuration comparison run for every molecule, `<=` for `<` in the survivor test, and the hydrazide skip removed. Four of them (the last survivor, P-45.6 first, the stereo gate, `<=`) survived the first version of the file, which tested the book's examples and the comparison but not `_break_parent_tie`'s own wiring; a real molecule cannot reach three tied parents with two surviving, so the wiring is tested over stand-in plans.

**Merged with D-191 and D-192 (xaerogonzo/OpenChem-Studio#238, which landed while this was open).** Its own limitations note predicted which six pins flip when both are in, and they did: D-191p and D-192p (the canonical spelling's rejected order), D-194a and D-194b (open until now; strict xfails that pass: moved to FIXED), and two rows of `tests/test_naming_providers.py`; every other test passed. Against master, which has #238: the census moves the same 3 rows, `tools/naming_ref_compare.py` changes the same 5 of 1712 panel names with 0 violations under the same manifest, and the naming-consumer app session is 3265 passed, 2 skipped, 28 xfailed. The new test file is 87 tests, with examples 11 and 12 pinned over 16 spellings each (without the rule they split, which is what closes D-194a and D-194b). The vendored suite on the merged tree, its own pytest session with the JRE on PATH and JAVA_HOME set: 5634 passed (5532 on this branch before the merge).

**Merged with the parent choice among chains that differ only in configuration (xaerogonzo/OpenChem-Studio#235).** Both changes rewrote `_break_parent_stereo_tie`: this one renamed it `_break_parent_tie` and put P-45.2.3 ahead of the configuration comparison, #235 counted DISTINCT hypotheses (`_plan_identity`, bound 12, so the nine equal chains of P-92.5.2.2 example 5 are four choices) and compared names assembled without descriptors. The merge keeps this change's names and steps and #235's identity and bound, and drops #235's "only a molecule that carries stereo" gate from the function's own scope, since P-45.2.3 has to reach achiral molecules and the configuration step keeps that gate for itself. **The two did not compose without a fix, and the tests said so:** `_citation_locants` read the prefixes with their descriptors, which decide how prefixes merge (`4,4-bis[...]` against `4-[...]-4-[...]`), so the four choices of example 5, which differ in nothing but configuration, had flattened locants `4,4,6,6` and `4,6,4,6`, and P-45.2.3 ruled two of them out before the configuration comparison saw them (#235's `test_nine_chains_are_four_choices` read 2 where it expects 4). The name was still the book's, 40 of 40 spellings, by that artefact. The book reads the locants "ignoring the configuration symbols" (P-45.6.2, p. 426), so `_citation_locants` now reads them with the descriptors set aside (`assembly.descriptors_set_aside`, which `assemble_without_stereo` uses too), `test_p_45_2_3_cannot_tell_the_four_choices_apart` pins it, and undoing it fails that test and #235's. The bound test of this change, written for 4, now reads the constant. Measured on the merged tree: both new test files 100 passed and 5 xfailed. (Found and fixed while merging #235 into this change, in a session that did only that; its resolution of the merge is what this paragraph describes.)

**Gates on the tree merged with master at `13ea375b` (#235, #238, #240, #241), each against master itself.** The census (2000 rows, canonical SMILES, OPSIN read-back, each side scanned from its own directory): the same 3 rows move, with the same class changes as before the merge. Over 7 spellings of every row, 55 had more than one name on master and 50 do now (the rule stabilised 2, the hydrazide fix 3 `N`/`N'` rows; none was made unstable, and no name appeared that master did not already give for that row), so #235 did not change what this rule does to the census. `tools/naming_ref_compare.py --base 13ea375b` with the same manifest: the same 5 of 1712 panel names change, 0 violations. The vendored suite, its own pytest session: 5634 passed. The naming-consumer app session: 3284 passed, 2 skipped, 28 xfailed. CPU time to name the census, master and this tree run side by side so that the machine's load is the same for both: 426.9 s and 431.9 s, then with the launch order swapped 412.5 s and 413.5 s, so the rule costs about 1% at most, inside the noise between the pairs.

**Not done, measured, in `KNOWN_LIMITATIONS.md` ("Open after P-45.2.3"):** P-44.4.1.1; P-45.5 (and P-45.3, P-45.4 across parents; P-45.4.1's own example is D-194c). The fork port (`open-iupac-namer`, `tools/fork_port.py`) and the `VENDORING.md` row come after this merges.

## 2026-10-07 -- naming round 27: the principal chain has the greater number of multiple bonds (P-44.4.1.1)

BlueBookV2.pdf p. 401: "the senior ring, ring system or principal chain has the greater number of multiple bonds". `strategy._parent_selection_score` counted unsaturation INFIXES, and one infix names every bond of its kind, so `1,3-diene` and `1,3,13-triene` tied; the `unsaturation_locants` tier is only meaningful between numberings of one parent and ranks the SHORTER set higher across parents, so the diene with an ethenyl substituent won on every spelling. It counts the bonds the infixes name now (capped at 99 so the band stays under one chain atom).

* P-45.2.3 examples 6 and 9 (`...tetradeca-1,3,13-triene`, `...deca-1,3,9-triene`) are the book's name on 13 of 13 spellings; that makes fourteen of the fifteen decided by P-45.2.3 (13 was already stable). Their stand-in test, the "not reached today" pin and the strict xfail are gone from `tests/test_namer_parent_citation_locants.py`.
* Measured. Census (2000 rows): 0 moved, 1959 exact before and after, class counts identical. `tools/naming_ref_compare.py` against the tree before: 1712 panel rows, 0 changed, 0 violations, so there is no stage manifest. A 700-molecule sweep of random branched C7-C13 skeletons with 2+ multiple bonds (fixed seed) moved 238 names; every one reads back to its structure through OPSIN, and in every one the parent has the same number of carbons and strictly more multiple bonds (none shorter, none with fewer). Mostly `-ylidene`/`methylidene`/`prop-1-en-2-yl` substituents that became a longer-unsaturated parent: `2-methyl-3,4-dimethylidenepent-1-ene` is `2,4-dimethyl-3-methylidenepenta-1,4-diene`, `4-ethylidene-2,3-dimethylhex-1-ene` is `4-ethyl-2,3-dimethylhexa-1,4-diene`. The census sample has no such shape, which is why it did not move.
* Not changed, and measured: a longer chain with fewer bonds is still the parent (`3-ethenylnon-1-ene`); rings (`(cyclohex-2-en-1-yl)benzene`) and the ene/yne-against-diene tie are as before. P-44.4.1.2 (the greater number of DOUBLE bonds: `hepta-1,6-diene` before `hept-1-en-6-yne`, p. 402) is still not implemented: `C=CCCC(CCC=C)CCC#C` is three names over 12 spellings, all reading back exact (`5-(but-3-yn-1-yl)nona-1,8-diene` is the book's rule); pinned as a strict xfail in `tests/test_namer_multiple_bonds_parent.py`.
* New `tests/test_namer_multiple_bonds_parent.py`; two of its tests fail on the tree before.

## 2026-10-07 -- naming round 27, second rule: of parents that tie on P-45.2.3, the name earlier in alphanumerical order (P-45.5)

BlueBookV2.pdf p. 424: "The preferred IUPAC name is the name that is earlier in alphanumerical order. Alphabetic letters are considered first in the order that they appear in the name ... Then, if still there is a choice, numerical locants are considered in the order of their appearance." It follows P-45.2.3 (P-45.3 and P-45.4 between them are not applied across parents), so its examples are the ones that tie there ("the locants appear in the name in the same order ... but 'bromo' ... is earlier alphabetically than 'dibromo'"). They were two names over the spellings, chosen by the order the SMILES atoms were written in.

* `engine._senior_by_alphanumerical_order` runs in `_break_parent_tie` on the parents P-45.2.3 left, before the configuration comparison, and compares `_alphanumerical_letters`: the finished name (descriptors set aside) reduced to its letters, in order. Removed: locants (including a fusion locant's letter, `4a`), the italic locants and element symbols (`N`, `Se`, the `H` of `1H`), fusion descriptors (`[3,2-a]`), and hydro/dehydro prefixes, which are "not included in the category of alphabetized detachable prefixes" (P-31.1.4.2.4, pdf p. 75; `hydroxy` and `hydrogen` stay). The multiplying prefix stays, which is what puts `bromo` before `dibromo`. Same-parent guard as for P-45.2.3.
* **It declines** a name that carries a nuclide, a bonding number (`lambda`/`λ`) or an embedded `NAMING ERROR`: P-45.3 and P-45.4 come before this rule and are not applied across parents, so deciding such a tie by letters would decide it by the wrong rule (P-45.2.3's examples 11 and 12, and P-45.5's example 5, are all of that kind and are unchanged); two different broken names are not ordered.
* The book's examples 1, 2 and 4 are its name on 13 of 13 spellings (7, 7 and 10 of 13 before). Example 3 is a cyclophane the engine does not name. Example 5 (nuclides) stays two names, 9 and 4 of 13, both reading back exact: open, pinned.
* Measured. Census (2000 rows): 0 moved, class counts identical. `tools/naming_ref_compare.py`: 1712 panel rows, 9 names changed, all in `bluebook_tuning`, all 9 listed in `benchmarks/naming/stages/manifests/P45-5-alphanumerical-order.toml` with the reason (one is the book's own example 2), 0 violations once listed, every one reading back before and after. A 500-molecule sweep of two substituted benzene rings joined by N, O, S or a carbon linker (fixed seed), each named over 6 spellings on both trees: 21 molecules had more than one name before and none has now; every one is now the letters-earliest of the names it had, none was made unstable, no name appeared that the tree before did not give for that molecule, every new name reads back exact. (A first sweep of random substituted alkanes never reached a tie, 0 unstable on both trees, and measured nothing.)
* Found by measuring, not by the book's examples: the first version left a fusion locant's `a` (`4a`), a fusion descriptor's letters and the hydro prefixes in the letters. The census had one row move (exact before and after) because of the last; the book says hydro prefixes are not alphabetized, and with them out the census row does not move.
* One pinned shape moved, found by the application's own naming tests and by neither the census nor the panel: `tests/fixtures/naming_cation_shapes.txt` had `C[N+](C)([O-])CC[N+](C)(C)C` as `dimethyl(oxido)[2-(trimethylazaniumyl)ethyl]ammonium`, which was only the name of the canonical spelling: over 16 spellings the tree before gave it and `{2-[dimethyl(oxido)azaniumyl]ethyl}tri(methyl)ammonium` 8 and 8, and now the second on all 16 (earlier letters), both reading back exact. The fixture is updated; the `tri(methyl)` form is the engine's, in both. `test_without_the_rule_the_same_spellings_give_two_names` in `test_namer_parent_citation_locants.py` switches P-45.5 off as well as P-45.2.3, because P-45.5 also decides five of those examples (7, 8, 9, 10, 15) once P-45.2.3 is gone.
* New `tests/test_namer_alphanumerical_order.py` (39 tests: the book's examples, the split without the rule, what the letters exclude, what declines, the comparison on made-up trees, and `_break_parent_tie`'s wiring between P-45.2.3 and P-45.6). Mutants: 14 of the rule and its letter reading, all killed; two survived the first version of the tests (a two-letter italic locant, and the rule being applied to all parents instead of P-45.2.3's survivors) and have tests now.

## 2026-10-07 -- naming round 28: a name keeps every nuclide (D-193), the lambda number of a single-bonded hypervalent centre (D-195), and the parent's bracket before the part it modifies (D-196)

D-193 was listed as four wrong molecules (`[15NH2]c1ccccc1` named `aniline`, `[15N]#CCC(=O)O` named `cyanoacetic acid`, ...). Measuring a labelled population showed it was not four cases: `isotope.collect_isotope_labels` dropped the label of any atom it could not locate, and every route that builds a name from parts of the molecule could lose a nuclide the same way, so the name read back as the unlabelled compound.

* **The guard.** `engine._check_nuclides_named` (called by `_name_smiles_bound` around the whole naming path) refuses a name that cites fewer atoms of a nuclide than the molecule has. `_nuclides_named` reads the isotope brackets and multiplies by the multiplier that encloses them (`1,2-di[(81Br)bromo]ethane` is two atoms; found when D-192m failed on a first version that counted brackets). A route nobody has found yet now raises, and the application shows a `NamingError`, instead of a name for another compound.
* **The routes that label their atoms.** `engine._isotope_atom_sites` (an atom a RETAINED parent name owns but does not number, alone of its element in the name: `(15N)aniline`, `4-chloro(15N)aniline`, `(18O)phenol`, `(15N)benzonitrile`; a suffix group's heteroatom of a systematic parent), `_isotopic_group_prefix` (a multi-atom prefix: `(15N)cyanoacetic acid`, `3-[(81Br)bromocarbonyl]propanoic acid`), `_isotopic_attachment_prefix` (the atom a heteroatom-rooted prefix hangs on: `(18O)methoxyacetic acid`), the hypohalous-amide parent (`dimethyl(81Br)hypobromous amide`), and `isotopic_prefix` itself, which now cites isotopic hydrogens on its atom with the atom's symbol as locant (`3-[(O-2H)hydroxy]propanoic acid`, `3-[(N,N-2H2)amino]propanoic acid`; OPSIN reads these and does not read `(2H)hydroxy`) and merges a second nuclide into an existing bracket (`[(1-13C,18O)methoxy]acetic acid`). A bare symbol is cited only when the element is alone in what it modifies (P-82.6.1.2): the first version labelled the nitrile CARBON of benzonitrile and OPSIN warned the position was ambiguous among seven carbons, and the ether route labelled one of two oxygens; both now stay unlabelled and are refused.
* **D-196 (placement).** `assembly._assemble_substitutive` cites the parent's bracket before the parent name, after the prefixes (`1-bromo(4-13C)butane`, `4-chloro(15N)aniline`) where it used to be the first thing in the name (`(4-13C)-1-bromobutane`, unreadable). `IsotopeLabel.at_suffix` marks a nuclide on a suffix group's heteroatom, cited before the suffix word after its locant: `1-phenylethan-1-(18O)one` (P-82.2.1, p. 853). A suffix with no locant keeps the front-of-name form.
* **D-195.** A hypervalent centre with no hydrogen and only single bonds takes its lambda number: `pentamethyl-lambda5-phosphane`, `pentamethoxy-lambda5-phosphane (PIN)` (p. 770), `pentaphenyl-lambda5-phosphane`, `pentamethyl-lambda5-arsane`, and `(tetramethyl-lambda5-phosphanyl)acetic acid`. A centre with a double bond already says its number and is unchanged.
* **Measured.** 400 census molecules with one atom labelled (13C, 15N or 18O on a random atom, or a deuterium on a heteroatom; fixed seed), named on master and on this tree and read back through OPSIN: master 89 exact, 86 wrong molecule, 205 unreadable, 20 naming errors; now 290 exact, 2 wrong, 40 unreadable, 20 naming errors, 48 refused. No name that was exact before changed. The two wrong are a label's locant on a bridged or polycyclic retained parent (a morphinan, a tetracyclo ring), where the engine's numbering is not OPSIN's; before, that locant was in front of the name and OPSIN could not read it, so it was invisible. Census (2000 rows): 0 moved. `tools/naming_ref_compare.py` against master: 1712 panel rows, 0 changed, so there is no stage manifest (the panels carry no isotope and no single-bonded hypervalent centre).
* New `tests/test_namer_nuclide_guard.py`; the closed rows moved from OPEN to FIXED in `tests/test_namer_known_defects.py` (D-193a to D-193d, D-195, D-196a, D-196b, with the routes found beside them as D-193e to D-193l, D-195b, D-195c, D-196c, D-196d); `tests/test_naming_providers.py`'s example of a withheld name moved from `aniline` (now named) to two deuteriums on an aromatic amine (refused). D-194c is the one row still open of the group.

## 2026-10-08 -- naming round 29, phase 1: P-45.3 and P-45.4 across parents (the bonding number and the isotopic modification of the substituents; D-194c)

BlueBookV2.pdf p. 423. After P-45.2.3 and before P-45.5, "the preferred IUPAC name is based on the senior parent structure that has" (P-45.3.1) the maximum number of substituent groups with the higher bonding number cited as prefixes and directly connected to the parent, then the higher number first (`lambda6` before `lambda4`); (P-45.3.2) their lower locant set; (P-45.4.1) the lowest locants for isotopically modified substituent groups; (P-45.4.2) for nuclides of higher atomic number; (P-45.4.3) of higher mass number. Until now a tie they would decide went to the configuration comparison and then to plan order, which follows the order the SMILES atoms were written in, and every pair read back to the same molecule, so nothing failed.

* `engine._senior_by_substituent_modification` compares ONE tuple in the book's order (`_substituent_modification_keys`), on the parents P-45.2.3 left and before `_senior_by_alphanumerical_order`; same-parent guard as for P-45.2.3. A prefix is "directly bonded through a hypervalent atom" when its leaf text, or its tree's own parent name, starts with `lambdaN-` (`_bonding_number_of_prefix`), and "isotopically modified" when its assembled name cites a nuclide anywhere in it (`_nuclides_named`, round 28).
* The book's examples, each one name over 16 spellings now: P-45.3.1 example 1 (7 and 6 of 13 before), example 3 (7 and 6), P-45.4.1 (7 and 6; D-194c over 40 spellings 24 and 16), P-45.4.2 (8 and 5 the WRONG way round) and P-45.4.3 (11 and 2 the wrong way round). P-45.5's example 5, which carries nuclides and which P-45.5 declined, is the book's name on all 16 (9 and 4 of 13 before): P-45.5 no longer declines a name with a nuclide (it still declines a bonding number and an embedded failure).
* **Not covered:** P-45.3.1 example 2 and P-45.3.2 (`2lambda5-diphosphan-1-yl`): the engine drops the lambda number of a multi-atom group, a defect of its own.
* Measured. Census (2000 rows): 0 moved. `tools/naming_ref_compare.py` against the tree before: 1712 panel rows, 0 changed. A sweep of 489 two-ring molecules with one or two isotopic labels on non-ring atoms (fixed seed), each named over 6 spellings on both trees: 18 molecules had more than one name before and 4 now, none was made unstable, every new name reads back; the 4 are two isotopic prefixes cited in either order within ONE parent (`2-[(1-14C)methyl]-1-[(1-13C)methyl]` or the reverse), a different rule. (A first sweep that labelled ring atoms measured nothing: 364 of 500 were unstable on both trees, because the ring numbering of a labelled substituent ring is a tie inside one parent, and it names the ring `cyclohexa-1,3,5-trien-1-yl`.)
* New `tests/test_namer_substituent_modification.py` (40 tests; 13 mutants of the rule killed, one of which, the plain set of isotopic locants, survived the first tests because the per-element locants shadowed it in every case written). D-194c moved from OPEN to FIXED in `tests/test_namer_known_defects.py`; the P-45.5 tests that pinned a nuclide name as declined (and example 5 as open) moved to the book's name.

## 2026-10-08 -- naming round 29, phase 2: where an isotopic label goes so that OPSIN reads it, and a labelled ring that is still the ring it is

After round 28, 40 of 400 labelled census molecules had a name OPSIN could not read. In 35 the name with the bracket removed read fine, so the LABEL's placement was the cause; the others were the engine's own `azin-3-yl`. A fifth cause, found while probing, sat under them.

* **A suffix whose locant is left out** (`butanamide`, `propanal`, `propanol`, `propanenitrile`, `nonanamide`) is written with it when it carries a nuclide, from the label's own anchor locant: `butan-1-(18O)amide`, `propan-1-(18O)al`, `propane-1-(15N)nitrile`, `N-(4-bromo-2-fluorophenyl)nonan-1-(18O)amide` (the exact forms OPSIN reads were tested against their rivals first: `(1-18O)butanamide`, `butanamide(18O)`, `(18O)-N-phenylbutanamide` are not read). A retained name that numbers nothing keeps the bare label and now cites it after the prefixes (`(18O)acetamide`, `2-chloro-N-phenyl(15N)acetamide`); `assembly._assemble_substitutive`.
* **Hydro prefixes**: the parent's bracket follows them, which are cited directly before the parent name (`_HYDRO_PREFIXED_STEM`): `3,4-dihydro(4-13C)quinolin-1(2H)-yl`, `5,6,7,8-tetrahydro(2-13C)naphthalene`, `2,3-dihydro(1-15N)-1H-indole`, `octahydro(1-15N)-1H-indole`.
* **An amino prefix**: `_isotopic_attachment_prefix` puts the label before the `amino` it modifies, `3-[benzoyl(N-2H)amino]propanoic acid` (`methyl(N-2H)amino` is read; `(N-2H)methylamino` is not).
* **A compound alkoxy** (`phenylmethoxy`, `2-methylpropoxy`, `4-chlorophenoxy`): the label goes before `oxy` on the UNcontracted form, `[(phenylmethyl)(18O)oxy]`; a bare stem keeps `(18O)methoxy`, and a stem with a nuclide bracket of its own merges, `(1-13C,18O)methoxy`.
* **A labelled ring** (`ring_naming.common._nuclide_free`): a ring is looked up by the canonical SMILES of its atoms, the tables hold natural-abundance rings, and a nuclide anywhere in a ring made it unrecognisable. Labelled benzene was `(6-13C)cyclohexa-1,3,5-triene`, labelled pyridine `(5-13C)azine`, labelled naphthalene `[NAMING ERROR: No valid naming plan found...]`, and labelled tetralin `(3-13C)bicyclo[4.4.0]deca-1(6),7,9-triene`, a name OPSIN reads as ANOTHER molecule. The lookup is made on the nuclide-free ring (the three ring extractors; zero cost when nothing is labelled), and the label is placed afterwards from the full molecule. This is also why a sweep that labelled ring atoms measured nothing in phase 1: 364 of 500 were unstable on both trees.
* **Measured.** The same 400 labelled molecules (13C/15N/18O on a random atom, or a deuterium on a heteroatom; fixed seed), round 28 -> now: exact 290 -> 331, OPSIN-unreadable 40 -> 10, naming errors 20 -> 8, wrong molecule 2 -> 2 (one fixed, one new), refused 48 -> 49; no name that was exact before changed. Census (2000 rows): 0 moved. `tools/naming_ref_compare.py` against phase 1: 1712 panel rows, 0 changed.
* **The new wrong molecule is not caused by this change**: `8-(methylsulfanyl)-5,9-dihydro(9-2H)-2H-purin-6-one` for a deuterium on a hydro-purinone's ring nitrogen. The label's locant (the engine's numbering of the hydro-named ring) is not OPSIN's; with the bracket in front of the name OPSIN could not read it at all. The other wrong one is the same class (`4,5-epoxy...(4-13C)morphinan-6-one`). Both are in the application's read-back, which withholds a name that does not read back.
* **Found and NOT fixed: D-197.** The carbonyl oxygen and the alkoxy oxygen of an ester are one name, `methyl (1-18O)acetate`, for two different molecules (the acid component is carved with both its oxygens, so the label cannot be told apart), and OPSIN reads neither. The sweep counted these as unreadable, so nothing flagged them. Pinned open in `tests/test_namer_known_defects.py` (D-197a, D-197b) with the forms OPSIN reads for each: `methyl prop-2-en-1-(18O)oate` and `methyl prop-2-en-1-(O-18O)oate`. Whether the book prints those is not known.
* **Still unreadable (10):** the ester and acid oxygens above, a label between two suffix groups (`heptane-2,4-dione`), a ring nitrogen that is also the attachment atom (`3-methyl(1-15N)piperidin-1-yl`), and `[4-(...)methyl](1-13C)phenyl`.
* New `tests/test_namer_label_placement.py` (78 tests; 13 of 14 mutants killed, the survivor equivalent: a bare `hydro` with no multiplier does not occur). The D-198 and D-199 rows in `tests/test_namer_known_defects.py` are the fixed cases (D-199b was a wrong molecule), D-197 the open one.

## 2026-10-08 -- naming round 30: the oxygens of a carboxyl group (D-197), what a ketone names (D-200), the infix's e before a nuclide (D-201), a nuclide in a fused ring (D-202)

Round 29 left three items it had diagnosed: D-197, "ring-nitrogen label locants" (a morphinan and a hydro-purinone) and an `azin-3-yl`. Measuring each again, **two of the diagnoses were wrong** (below), and what the measurements found instead was larger.

* **D-197 (the two oxygens of a carboxyl group).** The carbonyl and the hydroxyl oxygen of an acid are different atoms, and the hydroxyl is also the alkoxy oxygen of the ester the acid component is carved from (cut at the alkyl-oxygen bond, capped with hydrogen); neither was alone of its element in the group, so both fell back to `(1-18O)`. `_isotope_atom_sites` now separates the oxygen single-bonded to the carboxyl carbon, and `collect_isotope_labels(alkoxy_ok=...)` cites it with the element as its locant, as OPSIN reads it: `methyl (18O)acetate` / `methyl (O-18O)acetate`, `methyl prop-2-en-1-(18O)oate` / `-1-(O-18O)oate`, `(18O)acetic acid` / `(O-18O)acetic acid`, `methyl (O-18O)benzoate`, `hexadecyl 4-cyanobenzene-1-(O-18O)carboxylate`, both at once `methyl (18O,O-18O)acetate`. The free acid had the same defect and is fixed by the same test, so no tag on the carve is needed. A carboxylate is named from its neutral acid, so its oxygen never arrives charged: a charge test was written, then removed when the mutant without it changed no name.
* **D-200 (a ketone names only its oxygen).** `DetectedFG('ketone').atoms` holds the carbonyl, its oxygen AND its two neighbours. `_isotope_atom_sites` and the anchor map both read those as the suffix's, so the ring nitrogen of `CC(=O)[15N]1CCCCC1` was cited by `piperidin-1-yl` AND by `ethan-1-(15N)one`, and the aryl carbon an acetyl hangs on the same way (`1-{...(1-13C)phenyl}ethan-1-(13C)one`). WRONG MOLECULE (two 15N for one); `_atoms_named_by_suffix` keeps only what is double-bonded to the anchor. This was the "ring nitrogen that is also the attachment atom" and the "`(1-13C)phenyl`" of round 29's still-unreadable list.
* **D-201.** `_LOCANT_PREFIX_RE` skipped `-1-` and looked for a vowel, and met the nuclide's `(`. The bracket is skipped too: `prop-2-en-1-(18O)amide`, `prop-2-en-1-(18O)ol`, `but-2-yn-1-(18O)amide`, the elision of `prop-2-enamide` and `prop-2-en-1-ol`. Both spellings read back exact; this is for agreement with the unlabelled name.
* **D-202 (a nuclide in a fused ring).** Round 29 made `extract_ring_mol` look a ring up without its nuclides, but the fused, bridged and spiro namers read the ring from the molecule themselves; a 15N at a ring fusion left `[NAMING ERROR: No valid naming plan found for c1cn[15n]2cnnc2c1]` for `[1,2,4]triazolo[4,3-b]pyridazine`, and elsewhere a von Baeyer name (`2,7-diazatricyclo[7.4.0.0^{3,7}]trideca-...` for a pyrrolo[2,1-b]quinazoline). `ring_naming.name_ring_system` now takes the nuclide-free molecule once for every ring kind (the same object when nothing is labelled, so an unlabelled molecule costs nothing and cannot change). The label locants then come out as OPSIN numbers them: `(4-15N)[1,2,4]triazolo[4,3-b]pyridazine`, `(8-15N)[1,2,4]triazolo[1,5-a]pyrimidine`, `(3-15N)naphtho[2,1-d][1,3]thiazol-2-yl`.
* **The wrong diagnoses.** (1) The morphinan: `1-bromo-4,5-epoxy-2-hydroxy(4-13C)morphinan-6-one` IS the labelled molecule; OPSIN reads the morphinan name WITH stereochemistry the input does not have, so the sweep's full-InChIKey comparison called it wrong. Compared without stereo it is exact (and `(4-13C)` is the only locant of six tried that matches). (2) The hydro-purinone: `(9-2H)` is right (with `6H` OPSIN reads the labelled name back exact); the UNLABELLED name `8-(methylsulfanyl)-5,9-dihydro-2H-purin-6-one` is already another molecule (the indicated hydrogen is put at 2, where the structure has C=N, and the 6-oxo is left to the hydro prefixes). An unlabelled indicated-hydrogen defect, not a label; it is left open. (3) `azin-3-yl`: it appeared only in names of LABELLED pyridine substituents, before round 29's ring fix, and never unlabelled; the census rows that had it are `pyridin-3-yl`, `pyridin-2-yl`, `pyridin-4-yl`, `pyrimidin-2-yl` now and read back exact (tests added).
* **Measured.** The 400 labelled census molecules of rounds 28 and 29 (same seed), master -> now: exact 331 -> 348, OPSIN-unreadable 10 -> 3, naming errors 8 -> 0, wrong molecule 2 -> 2 (the two above, neither a label defect), refused 49 -> 47. A new population, 300 census molecules with one RING nitrogen labelled (a 15N, or a deuterium on an NH; fixed seed 3030, compared without stereo), master -> now: exact 269 -> 295, unreadable 16 -> 2, naming errors 11 -> 0, wrong molecule 3 -> 2, refused 1 -> 1; nothing exact on master became anything else, and 19 names that read back exact on both trees changed (18 were von Baeyer fallbacks on master, such as `2,7-diazatricyclo[7.4.0.0^{3,7}]trideca-...`, and are fused-ring names now; one gained its `1,4-dihydro`). **A first run of that population read 153 as unreadable and was discarded**: a second runner had been started in the same working directory (the py2opsin collision) and the names read fine when probed alone; the population was rerun with nothing else running. Census (2000 rows): 0 moved; `tools/naming_ref_compare.py` against master: 1712 panel rows, 0 changed, 0 violations.
* **Still unreadable, no form found.** A label on ONE oxygen of a multiplied suffix (`(2-18O)hexane-2,4-dione`, `(2-18O)-3-azabicyclo[3.2.0]heptane-2,4-dione`): OPSIN reads none of `hexane-2,4-di(18O)one`, `hexane-2-(18O),4-dione`, `(2-18O)hexane-2,4-dione` (it reads only the unconventional `hexane-2-(18O)one-4-one`), so there is no target to pin. The other unreadable rows of both populations name an unlabelled molecule OPSIN cannot read either (a bis-dioxolopyran, a pentacyclo imide, a 6-azauridine) or are the wrong-molecule pair above.
* New `tests/test_namer_carboxyl_oxygen_labels.py`; 11 of 12 mutants killed, the survivor (the charge test) equivalent and removed from the code. D-197 moves from the open table to FIXED in `tests/test_namer_known_defects.py` (a to d), with D-200 (a, b), D-201 and D-202.

## 2026-10-08 -- naming round 31: the indicated hydrogen of a hydro-named ring ketone (D-203)

Found in round 30, where a labelled sweep called `8-(methylsulfanyl)-5,9-dihydro(9-2H)-2H-purin-6-one` a label defect: the UNLABELLED name was already another molecule.

* **Cause.** `retained_lookup._try_derive_hydro_retained` aromatizes the ring, matches a curated purine and writes `5,9-dihydro-2H-purine`: the `2H` is the curated entry's DEFAULT indicated hydrogen, a placeholder for "some mancude tautomer", and here C2 is sp2 and C6 is the carbonyl. The P-58.2 planner (`indicated_hydrogen_p58.plan_hydrogens`) had the right answer (indicated hydrogen 6, hydro 5 and 9), but `_resolve` compared the OLD text with its plan ("the old description names an atom the plan cannot account for"), found the 2 outside what the plan described and declined, so the placeholder reached the name. OPSIN reads `...-5,9-dihydro-2H-purin-6-one` as a purine with a CH2 at C2.
* **Fix.** The check ignores the old text's indicated-hydrogen labels (`_HYDRO_IH`'s `ih` group) and still requires the HYDRO positions, which are read off the structure, to be among the atoms the plan describes, and every label to name an atom of the ring. `5,9-dihydro-6H-purin-6-one`, `5,7-dihydro-6H-purin-6-one`, `1,4,5,9-tetrahydro-6H-purin-6-one`, `1,4,5,7-tetrahydro-6H-purin-6-one`, `3,4,5,7-tetrahydro-6H-purin-6-one`, `1,4-dihydro-6H-purin-6-one`: seven tautomers of a purin-6-one that were another molecule, all read back exact now, and the labelled `(9-2H)` and `(9-15N)` names of round 30 keep their locants.
* **Measured.** Census (2000 rows), master -> now: 2 names move, both `mismatch_formula` -> `exact` (the purinone and a `1-methyl-6-nitro-1,3a,5,7a-tetrahydro-4H-imidazo[4,5-c]pyridin-4-one`), exact 1959 -> 1961, nothing else; `tools/naming_ref_compare.py` against master: 1712 panel rows, 0 changed, 0 violations. A new population of 178 odd tautomers of census molecules whose ring carbonyl sits on a fused ring (RDKit's tautomer enumerator, fixed seed 3131, compared without stereo): exact 167 -> 169, wrong molecule 7 -> 5, unreadable 4 -> 4, 2 names moved, none worse. The 5 wrong and 4 unreadable that remain are enol and imidol tautomers (`C(O)=N`, `C(=C(O)O)`) and ring systems OPSIN cannot parse, a different class.
* **The guard that was left.** The consistency check on the hydro positions fired for no molecule in 2178 (the census sample and the population), so a test that only names molecules cannot reach it; `test_the_hydro_positions_of_the_old_text_must_still_agree_with_the_plan` captures a real parent and alters its text. Mutants: 4 of 4 killed (placeholder never ignored; any old text accepted; hydro positions ignored too; an unknown label tolerated). Three of them SURVIVED the naming tests alone.
* New `tests/test_namer_hydro_ketone_indicated_hydrogen.py`; D-203 in `tests/test_namer_known_defects.py`.

## 2026-10-08 -- naming round 32: a benzo-fused bridged ring system with a ring heteroatom (D-204)

Found by reading the census rows that still name a DIFFERENT molecule (9 `mismatch_formula` of 2000 after round 31): two of them, and a third in the odd-tautomer population of round 31, were one scaffold.

* **Cause.** `ring_naming/benzo_fused_bridged.py` detects one aromatic six-ring ortho-fused to a macrocycle that a small bridge spans and emits `<hydro>-<bridge>-methano-benzocyclo[N]ene`, a CARBOCYCLE. Its scope guard counts rings, bridge length and macrocycle size and never reads an atom's element, so a ring oxygen, nitrogen or sulfur in the macrocycle was dropped without a word: `CC(=O)C1C(=O)NC2(C)CC1c1cc([N+](=O)[O-])ccc1O2` was `6-acetyl-9-methyl-3-nitro-5,6,7,8,9,10-hexahydro-5,9-methanobenzocycloocten-7-one`, which OPSIN reads as a carbocycle with no O and no N.
* **Fix.** A system whose non-benzene atoms are not all carbon is declined, and the generic bridged path (von Baeyer with replacement prefixes) names it: `12-acetyl-9-methyl-4-nitro-8-oxa-10-azatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-trien-11-one`, read back exact. **Not the preferred name**: P-25.4 would name it as a fusion-bridged system, `2,6-methano-1,3-benzoxazocine`; that is not built, so these are correct and non-preferred, and the day it is built the carbocycle module's guard is the place to route from.
* **Measured.** 114 skeletons (twelve benzo-fused bridged carbocycles, each non-aromatic ring atom replaced in turn by O, N or S), master -> now: wrong molecule 89 -> 0, exact 25 -> 114 (24 of the 25 were von Baeyer names already: positions the module declined for another reason); 20 carbocyclic controls (the same skeletons with a ketone): 20 exact before and after, no name moved; none of the 114 got worse. Census (2000 rows), master -> now: 2 names move, both `mismatch_formula` -> `exact` (exact 1961 -> 1963); `tools/naming_ref_compare.py` against master: 1712 panel rows, 0 changed, 0 violations.
* **Seen and not changed.** The carbocycle names the module still writes use an odd hydro multiplier (`5,6,7,8,9-pentahydro-5,9-methanobenzocycloheptene`); OPSIN reads them and they are exact, but hydro prefixes come in pairs (P-31.1.4.2.4) and a bridged parent's hydro description would need its own rule.
* New `tests/test_namer_benzo_bridged_heteroatoms.py`; 4 of 5 mutants killed, the survivor equivalent (a check restricted to the non-fusion atoms: the fusion atoms are benzene carbons by construction). D-204 in `tests/test_namer_known_defects.py`.

## 2026-10-09 -- naming round 33: the cation of a fused ring system (D-205) and the lettering of a ring fused on purine (D-206)

Found by reading the census rows that still fail after round 32: 8 `NAMING ERROR` rows (7 of them cationic fused heteroaromatics), 3 `sulfonamidate` anions that OPSIN reads as the neutral sulfonamide (the engine's names are right; not touched), and 7 unreadable names.

* **D-205.** `ring_naming.name_ring_system` returned nothing for the cation of a ring system whose neutral parent has ONE indicated hydrogen: `c1c[n+]2c([nH]1)[nH]c1ccccc12` carries two `[nH]` beside a bridgehead `[n+]`, a molecule no curated table holds, and the fused namers read the ring from the molecule. A ring system with nothing to offer that has an aromatic nitrogen cation is now tried once more on its NEUTRAL TWIN (`_neutral_twin`: the charge off, the protonation hydrogen off, and where two `[nH]` still remain, each dropped in turn, first that sanitises): the same atom indices, so the `-ium` locants and everything else are read from the full molecule afterwards. It runs only where the first pass found nothing, so no name that existed can move (a call-count test pins that).
* **D-206 (found verifying D-205).** The two imidazo[1,2-g]purin-ium rows came out as names OPSIN could not read, and the NEUTRAL ring had the same defect: `fusion_general._periphery_order` listed a component's peripheral atoms in the order of its locants, which is the order of the periphery wherever the numbering runs once round the ring system. Purine's does not (its fusion atoms are 4 and 5; the periphery runs 1, 2, 3, 4, 9, 8, 7, 5, 6), so the sides were a 1-2 ... g 7-8 where the book's are f 8-7, e 9-8: `6H-imidazo[1,2-g]purine` for the skeleton OPSIN calls `imidazo[2,1-f]purine`, read by OPSIN as another molecule. The periphery is now walked from the side 1-2 towards the lower neighbour (P-25.3.1.3) and used when it differs from the locant order, so a ring system numbered once round (naphthalene, indole, carbazole, acridine, benzimidazole) cannot move.
* **Measured.** (1) 300 census molecules with one pyridine-type ring N protonated, in a fused aromatic ring system (fixed seed 3333, compared without stereo), master -> now: exact 280 -> 288, naming errors 8 -> 0, wrong molecule 9 -> 9, unreadable 3 -> 3; 8 names moved, all `naming_error` -> `exact`, none worse. (2) 32 purine-fused ring systems OPSIN builds from `X[n,m-L]purine` names (13 prefixes x the letters a to i; 32 distinct structures): exact 21 -> 32 (9 unreadable, 1 wrong molecule and 1 naming error before), 0 regressed. (3) Census (2000 rows): 3 names move, all `naming_error` -> `exact` (the xanthinyl-imidazolium and the two imidazo[2,1-f]purin-ium rows; exact 1963 -> 1966); `tools/naming_ref_compare.py` against master: 1712 panel rows, 0 changed, 0 violations.
* **A first census with only D-205 moved the two imidazopurine rows from a visible error to a name OPSIN could not read**, and the neutral ring showed why; it is the reason D-206 is in this round rather than the next. Fixing the cation alone would have turned a refusal into an unverifiable wrong name.
* **Not changed, found here.** (a) 9 of the 300 protonated molecules are still wrong: the cation is LOST for 2-amido-thiazoles, 4,5,6,7-tetrahydrobenzothiazoles and pyrazolo[1,5-a]pyrimidines (`...-4,5,6,7-tetrahydro-1,3-benzothiazole` for the `[nH+]`; OPSIN reads the neutral compound) and a pyrimidin-1-ium comes out as `4,5-dimethoxy-6-sulfamoylpyrimidin-1-ium`; each its own route. (b) The bicyclic amidinium `C1C[N+]2=C(CCCCC2)NC1` and `C[N+]1=C(C)NCC1` (named `2,3-dimethyl-1,3-diazol-3-ium`, a dihydroimidazolium without its hydro prefixes) are not aromatic cations, and the twin is aromatic-only by design. (c) 5 census rows are still `NAMING ERROR`: two neutral tetracyclic fused systems (a pyrazolo-pyrido-pyrimidine and an imidazo-quinoxaline), the amidinium above, and two spiro-oxindole pyrano[2,3-c]pyrazoles.
* New `tests/test_namer_fused_cations.py` (6 of 7 mutants killed, the survivor a restriction to aromatic cations that no molecule reaches: a non-aromatic cation fails to sanitise as a twin anyway) and `tests/test_namer_purine_fusion_letters.py` (5 of 6 killed, the survivor equivalent: the walk already visits every atom once). D-205 and D-206 in `tests/test_namer_known_defects.py`.

## 2026-10-09 -- naming round 34: a partly saturated ring cation keeps its hydro prefixes (D-207)

Found by reading the first item round 33 left open: `C[N+]1=C(C)NCC1` was named `2,3-dimethyl-1,3-diazol-3-ium`, an imidazolium, where the molecule is an imidazolinium. It was not one molecule: it was every ring cation with a C=N+ and a saturated atom.

* **D-207.** Two helpers refused a ring at its first charged atom. `monocyclic._collect_hydro_locants` (the Hantzsch-Widman route) returned an empty list on a ring N+ before it asked whether that atom sat in a double bond, so the mancude parent was named with no hydro prefix (`azol-1-ium`, `1,3-oxazol-3-ium`, `1,3-diazinan-3-ium`). `retained_lookup._try_derive_hydro_retained` (the pyridine family) did the same, and then, for an N+ that had lost its substituent in the ring carve (`C[N+]1=CCCCC1` -> `C1=[N+]CCCC1`, a bare N+ with a RADICAL electron), could not aromatise the ring at all and fell to `azinan-1-ium`. The charge test now follows the double-bond test in both, and a charged ring is aromatised in a mode that clears the carve's H count and radical first.
* **Measured.** 1151 cations (32 cyclic imine / amidine / hydrazone ring skeletons of 4 to 8 members with N, O or S, each decorated with methyl, amino, hydroxy, phenyl or chloro on every ring carbon, then protonated or N-methylated at the ring N of the C=N; compared without stereo), master -> now: wrong molecule 1005 -> 0, exact 146 -> 1151, nothing exact became anything else.
* **Not changed, found here.** (a) These cations are exact but not in the preferred spelling: the five- and six-membered retained parents are not reached for a C=N+ (`3,4-dihydro-2H-azol-1-ium` where the neutral ring is `3,4-dihydro-2H-pyrrole`, `...-1H-1,3-diazol-3-ium` for `...-1H-imidazole`); `_try_derive_hydro_retained` finds the neutral `1H-pyrrole` but returns nothing after the lookup, and that was not followed. (b) A ring cation with an exocyclic double bond on a ring carbon (`C=C1CCC[NH+]=C1`) is still `5-methylideneazinan-1-ium`, a different molecule; its neutral ring is named. (c) The other items round 33 left open (the cation lost for 2-amidothiazoles, the non-aromatic bicyclic amidinium `C1C[N+]2=C(CCCCC2)NC1`, five census `NAMING ERROR` rows) are untouched.
* New `tests/test_namer_ring_iminium_hydro.py` (5 of 5 mutants killed; a sixth, the carve's formal charge cleared in the neutral mode, survived because the lookup does not need it, and was removed from the code). D-207 in `tests/test_namer_known_defects.py`.

## 2026-10-09 -- naming round 35: a ring cation on a curated fused parent keeps its -ium (D-208)

The first "still open" item of round 33: the cation was LOST for protonated 2-amido-thiazoles, tetrahydrobenzothiazoles and pyrazolo[1,5-a]pyrimidines. It was not three families but one cause.

* **D-208.** The ring-cation block in `engine.py` finds the locant of each charged ring atom in the parent's numbering (`atom_to_loc`) and `continue`d past one with none. A curated ring (`data_loader._RING_CURATED_SMILES`) lists `atom_locants` for the positions a substituent can take, and six entries left out the ring heteroatoms and fusion atoms (`c1nc2c(s1)CCCC2`: S1, N3, C3a, C7a), so the cation was printed as the neutral parent. The six tables are complete now (pyrazolo[1,5-a]pyrimidine N1, N4, N8; thiazolo[5,4-d]pyrimidine N1, S3, N4, N6; the 5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyrazine and -pyridine N1, N2, N4; 4,5,6,7-tetrahydro-1,3-benzothiazole S1, N3; 4,5,6,7-tetrahydrothieno[3,2-c]pyridine S1), each locant read back through OPSIN as the cation at that position. And a plan whose cationic ring atom has NO locant now returns an `ErrorTree` (the retry loop tries the next plan) rather than skipping the charge: the hexahydropyrido[2,1-a]isoquinoline entry, which is still incomplete, went from its neutral name to an exact von Baeyer cation name.
* **Measured.** 700 cations (the six parents, each decorated with methyl, amino, hydroxy, chloro, phenyl, acetyl or acetamido on every ring carbon, then protonated or N-methylated on each pyridine-type nitrogen, and the sp3 NH protonated), master -> now: wrong molecule 528 -> 0, unreadable 44 -> 0, exact 128 -> 700, nothing exact became anything else.
* **Not changed.** Thirteen other curated ring entries also list no locant for a ring heteroatom (listed by the test that guards the six); until each is completed their cations name by the next plan. The Hantzsch-Widman spelling and the exocyclic-ylidene ring cation of round 34 are untouched.
* New `tests/test_namer_curated_ring_cation_locants.py` (6 of 6 mutants killed). D-208 in `tests/test_namer_known_defects.py`.

## 2026-10-10 -- naming round 36: a ring cation with an exocyclic double bond keeps its hydro prefixes (D-209)

The "ylidene" item round 34 left open: `C=C1CCC[NH+]=C1` was `5-methylideneazinan-1-ium`, a piperidinium.

* **D-209.** `retained_lookup._try_derive_hydro_retained` collects the ring atoms that are saturated relative to the mancude parent (the hydro positions). A ring carbon with any double bond was a "genuine sp2 member" and skipped, which is right for the ring's own double bonds and wrong for a ylidene: the carbon holding `=CH2` is a hydro position (`3-methylidene-3,4,5,6-tetrahydropyridine`, hydro at 3,4,5,6). With it skipped the cation had three positions where the ring needs an even number, the derivation returned nothing, and the engine fell to the saturated hantzsch-widman ring. A ring carbon whose double bond goes out of the ring to a CARBON now counts (an exocyclic oxygen or nitrogen does not: that is the oxo and imino path, and counting it renamed `O=C1CCC[NH+]=C1`).
* **Measured.** 231 molecules (the 32 cyclic imine/amidine skeletons of round 34 with an exocyclic =CH2 on each CH2 ring carbon, their neutral rings and their protonated or N-methylated cations), master -> now: wrong molecule 37 -> 0, exact 194 -> 231, nothing exact became anything else; the round 34 population (1151) and round 35 population (700) re-run: unchanged, all exact.
* **Seen and not changed.** The neutral ring is still named by a curated entry, not the derivation; the derivation now names the same neutral ring if it is reached.
* New `tests/test_namer_ylidene_ring_cations.py` (2 of 2 mutants killed; a third, a ring carbon with a double bond both in and out of the ring, is a cumulene and was removed from the code). D-209 in `tests/test_namer_known_defects.py`.

## 2026-10-10 -- naming round 37: a fused ring system with a bridgehead N+ in a double bond is named (D-210)

The `NAMING ERROR` item round 33 left open (`C1C[N+]2=C(CCCCC2)NC1`) was one case of a class: any fused cation whose charge sits on a bridgehead nitrogen that is double-bonded into the ring, quinolizinium included.

* **D-210.** `fusion_general._neutral_ring_copy` makes the ring's +1 heteroatoms neutral so the fusion namer can read the graph, and a bridgehead N+ with three ring bonds and a double bond has no neutral copy with the same bonds (valence 4): "general fusion declined: the neutral ring graph does not sanitise". Such an atom is a pi atom of the cation, as the carbon of the isoelectronic carbocycle is, so two copies are made (`_iminium_copies`). The TWIN gives the namer a neutral graph with the N+=C bond made single (it reads atoms, rings and heteroatoms, never bond orders). The ANALOGUE replaces the bridgehead N+ by carbon for `plan_hydrogens`, which skips a neutral bridgehead nitrogen as non-pi: quinolizinium plans as naphthalene (no indicated hydrogen, `quinolizin-5-ium`), its tetrahydro cation as a tetralin skeleton. The `-ium` is added at the nitrogen's own locant by the existing ring-cation block. Bicyclic only: a bridgehead iminium in a tricyclic system, or beside another charge, stays unsupported, as the neutral-copy rule has it.
* **Measured.** 288 bicycles with a bridgehead N+ (aromatic pyridinium, pyrimidinium and imidazolium types fused to a 5-7 membered saturated ring; non-aromatic iminiums and amidiniums, with and without an N-substituent; each also with a methyl on every free ring carbon; the C=N+ ring 5 to 8 members), master -> now: naming error 190 -> 28, exact 98 -> 260, nothing exact became anything else. The 98 were von Baeyer names (`1-azabicyclo[6.2.0]dec-1(8)-en-1-ium`); the fusion names replace them where the fusion namer applies. The round 34 (1151), 35 (700) and 36 (231) populations re-run unchanged, all exact; three quaternary bridgehead ammoniums (`5-methylquinolizidin-5-ium`) keep their names.
* **Not changed, found here.** (a) The 28 left each contain a four-membered ring (fused azetidinium and diazetidinium: `C1CC[N+]2=C(C1)CC2`); the general fusion namer declines the ring. (b) The two charge placements of one amidinium are one ion (same InChIKey) and now both have exact names that differ (`...pyrimido[1,2-a]azepin-1-ium` for the charge on the imine nitrogen, `...-1H-pyrimido[1,2-a]azepin-5-ium` for the bridgehead): a canonical resonance form would give one name. (c) A tricyclic bridgehead iminium is untouched.
* New `tests/test_namer_bridgehead_iminium.py` (4 of 4 mutants killed; three more were equivalent or redundant and were removed from the code: the hydrogen RDKit supplies itself, a pi-capable test on the twin that is False either way, and a hydrogen test on an atom whose valence forbids one). D-210 in `tests/test_namer_known_defects.py`.

## 2026-10-10 -- naming round 38: a hydroxamic acid that is not the principal group keeps its carbon and its N-substituent (D-211, D-162)

The census review after round 37 (`naming_census_scan.py` with the new `delta` label) listed five rows that read back as another molecule; the first was an ester whose alcohol part carries `C(=O)N(O)Ar`, named `[(hydroxycarbamoyl)methyl](phenyl)methyl acetate` with the aryl gone. Probing it showed the defect was not about esters.

* **D-211.** `OC(=O)CC(=O)NO` (three carbons) was `3-(hydroxycarbamoyl)propanoic acid` (four). The prefix "hydroxycarbamoyl" includes the carbonyl carbon, and a chain that already names that carbon gains a phantom one; with an N-substituent the name is the same and the methyl is also gone. `_DEMOTED_AMIDE_TYPES_PREPROC` splits a demoted group whose carbon is in the chain into `oxo` + its heteroatom part (acyl halides, imidic acids, amides, hydrazides, thioamides, imidamides were added one at a time as each met this); `hydroxamic_acid` was not in it. Three places now carry the type: that split; `_DEMOTED_N_BEARING_FG_TYPES`, so the N-substituent (and the N-OH oxygen, a declared context atom) is left for the flood-fill and arrives as `hydroxy`/`methyl` on the nitrogen exactly as an N-methoxy's does; and `_DEMOTED_AMIDE_TYPES_EXEC` with its N-substituent test, for a group off the chain (`2-[hydroxy(methyl)carbamoyl]benzoic acid`). In a substituent, the chain trim that drops a hydroxamic carbon (`_TRIM_FG_TYPES`) is skipped when the nitrogen is substituted, because "hydroxycarbamoyl" has no place for the substituent: `2-[hydroxy(methyl)amino]-2-oxoethyl acetate`, as the N-methoxy amide already was.
* **D-162** (recorded open in round 14 with its target derived then) is the ester's-alcohol-part case of the same defect; the fixed engine writes that target, which is independent confirmation of it. Moved from the open table to the fixed one.
* **Measured.** 13 seeds, one of seven substituents on each free carbon (`naming_variants.py`, 336 structures; the three engine edits together): before, 44 exact and 292 another molecule (147 `same_formula_connectivity_change`, 61 `ring_atom_count_changed`, 26 `heteroatom_dropped:O`, 19 `other_formula_change`); after, 336 exact. None exact before is anything else now; one correct name changed spelling (`CC(=O)C(CC(=O)NO)C(=O)O`, the chain now the longer one). Census (2000 rows): 1,967 -> 1,968 exact, one row moved (`census322625`, wrong molecule -> exact), one name changed. Panels r7, r8, mc and the tuning populations (1,712 structures): 0 names changed, 0 violations. Blind frozen impact against the round-22 seal: `heldout_v6` 1 of 40 names changed (0 on the base engine), `bluebook_frozen` 64 of 1126 (64 on the base engine too, the drift of rounds 23-37, which had never been re-scored). **The frozen populations were therefore scored once (`stages/r38-final-evaluation.json`, records sealed by hash), as aggregates only:** `heldout_v6` 14 verbatim / 25 equivalent / 1 wrong molecule of 40 (round 22: 13 / 25 / 2); `bluebook_frozen` 523 verbatim / 524 equivalent / 21 wrong molecule / 45 unreadable / 13 no name of 1126, so 1047 read back to their input, 93.0% (round 22: 511 / 534 / 22 / 46 / 13, 1045). No wrong-molecule count rose and no row regressed structurally; no frozen row was read. The seal also resets the baseline the blind check compares against: it had reported "changed" for fifteen rounds on the unmodified engine and could not isolate any one round's effect.
* **Not changed, found here.** The census still has six rows that read back as another molecule. Three are sulfonamidate or nitro-bearing anions that OPSIN reads as the neutral compound (the engine's names are right; `delta` labels two `charge_lost`, one `charge_changed`). Three are real and separate: an N-acyl pyrazole-1-carboximidamide named as a methanamine (`NC(=NC(=O)c1ccccc1)n1cccn1` -> `benzamido(1H-pyrazol-1-yl)methanamine`, the C=N lost; also with an acetyl; recorded OPEN as D-212 with its target derived and read back), an isothiourea chain (`CON=C(N=C(N)S)c1ccccc1`), and a steroid oxime ether. One row is refused (a carboxylate: "charge perception claimed a 'acidic_anion_carboxyl'"), four are visible `NAMING ERROR`s (two spiro-oxindole pyrano[2,3-c]pyrazoles, two neutral tetracyclic fused systems), seven are unreadable by OPSIN.
* New `tests/test_namer_hydroxamic_prefix.py`: 26 names, each read back through OPSIN (5 of 5 live mutants killed; two further pieces written first, a skip of the N-OH oxygen in the `oxo` loop and a hand-off of it to the amino prefix, were redundant once the type joined `_DEMOTED_N_BEARING_FG_TYPES` and were removed). D-211 and the moved D-162 in `tests/test_namer_known_defects.py`; D-212 (open) in its open table. `tests/test_naming_providers.py` used D-162 as its example of a plain-looking name withheld by the read-back, as its docstring said it would have to move; it uses D-212.

## 2026-10-10 -- naming round 39: an acyl imine keeps its C=N, an N-ylidene amidine its double bond, an aminooxy group its parent once (D-212, D-213, D-214)

Round 38 closed its note with five wrong-molecule shapes still open. Probing the first three showed each was a family, not a row.

* **D-212.** `=N-C(=O)R` off the parent was written `acetamido`, whose bond is single: `O=C1CCCCC1=NC(C)=O` was `2-acetamidocyclohexan-1-one`, `OC(=O)CC(=NC(C)=O)C` was `3-acetamidobutanoic acid`, and the census row's N-acyl amidine on a ring nitrogen was a methanamine. Both acylamino paths in `_name_single_fg_substituent` now require every free-valence bond to be single; the double-bonded one falls to the `acylimino` branch (`(acetylimino)`, `(benzoylimino)`). The row's preferred form (`N'-benzoyl-...-1-carboximidamide`) is still not reached: no amidine suffix on a ring-N carbon. The name written is correct and reads back.
* **D-213.** A carbamimidoyl whose amino nitrogen is itself double-bonded (`ON=C(Ph)N=C(N)S`) cited that group as the single-bonded `N-(amino(sulfanyl)methyl)`. The builder now declines the shape and the ylidene-amino prefix names it (`{[amino(sulfanyl)methylidene]amino}`). Census row 356625.
* **D-214.** `R-NH-O-CH2-X` with a principal group on X took the O for one of the amine's substituents and attached the parent to the nitrogen, writing the parent twice: `CNOCC(=O)O` was `[(carboxymethoxy)(methyl)amino]acetic acid`; with a carboxylate it was refused. The compound amino prefix now requires the parent on the nitrogen; a parent on the O builds `[(R-amino)oxy]`. Census rows 1786625 (a steroid) and 1754625 (refused). Wider than the rows: every N-substituted aminooxy acid, ketone, nitrile or amide chain.
* **Measured.** Census 1968 -> 1972 exact; wrong-molecule rows 6 -> 3 (all charge, the sulfonamidate and nitro anions OPSIN reads as the neutral compound); the refused row is named; the four `NAMING ERROR` rows are unchanged. `tests/vendor` 5723 passed. The blind `--frozen-impact` check: heldout_v6, bluebook_frozen and fresh_v1 all unchanged, so no frozen set was re-scored and fresh_v1 was not touched.
* New `tests/test_namer_acylimino_aminooxy.py` (each name read back through OPSIN; 6 of 6 mutants killed). D-212 moved to the fixed table, D-213 and D-214 added. `tests/test_naming_providers.py` used D-212 as its withheld-by-read-back example; it now uses a sulfonamidate anion, an OPSIN misread no engine fix can make stale. `naming_stage_artifact.py --frozen-impact` takes a comma-separated list of stages, because fresh_v1 is sealed at its own.

## 2026-10-11 -- naming round 40: ring systems keep their heteroatoms, numbering, hydrogen and name (D-215 .. D-219)

The open list after round 39: four census `NAMING ERROR` rows, four unreadable names, and round 37's bridgehead-iminium remainder. Probing each showed a family.

* **D-215.** A spiro join of a bicycle and a heterocycle (`O=C1NC(=O)C2(N1)CC1CCC2C1`) was `tricyclo[5.4.2.1]undecane-1,3-dione`, every nitrogen gone. `name_bridged` could not number the heteroatoms and offered the carbocycle name anyway, which outranked the spiro name that was also offered. It now returns nothing it cannot cite; the spiro name stands (`spiro[imidazolidine-4,2'-bicyclo[2.2.1]heptane]-2,5-dione`). Census rows 167625 and 802625.
* **D-216.** "The attachment is locant 1" ranked above the heteroatom locants for a monocyclic heterocycle substituent, so an N-attached 1,2,4-triazine-3,5-dione was numbered with nitrogens at 1, 2 and 5: `4,6-dioxo-5,6-dihydro-1,2,4-triazin-1(4H)-yl`, a ring OPSIN cannot build. Only the walks that tie on the heteroatom rule are candidates for the shortcut: `3,5-dioxo-4,5-dihydro-1,2,4-triazin-2(3H)-yl`. Census row 150625.
* **D-217.** (a) A spiro partner is rebuilt atom by atom and lost the N-H of an aromatic azole, so `spiro[...pyrano[2,3-c]pyrazole]` could not be built (census rows 1044625, 1202625). (b) A tricycle of three monocycles needs a SECOND-order component: `fusion_general` now builds one level of it (`pyrrolo[3',2':5,6]pyrido[2,3-d]pyrimidine`, `pyrimido[5',4':4,5]pyrrolo[2,3-b]quinoxaline`; census rows 1852625, 1968625). It is tried only when no first-order name exists AND the von Baeyer fallback found none, and never for a methylenedioxy-bridged system, so no existing name moved (the first version changed a steroid acetonide from its von Baeyer name; the vendored suite's amcinonide partner test caught it).
* **D-218.** `1,4-dihydroquinoline` as the FIRST spiro partner was bracketed `[1,4]dihydroquinoline`, which OPSIN cannot read; only the hyphenated hydro prefix was recognised. Cited second (`3'-[1,2,3,4]tetrahydroquinoline`) both spellings read, so that slot keeps the bracketed form the pinned names use (the first version unbracketed both and failed D-159b and D-159c).
* **D-219.** A protonated or iminium nitrogen in a fused system with a four-membered ring has no fusion name (P-52.2.4.1), and the von Baeyer fallback refused every charge. A +1 N, O or S is now allowed (an arenium carbon still is not): `1-azabicyclo[5.2.0]non-1(7)-en-1-ium`. Round 37's population: 28 errors -> 0, 288 of 288 exact. Nine N-methylated 6-6 amidiniums changed from `(…-ium-1-yl)methane` to the von Baeyer name; all read back.
* **Not defects of the engine, left alone:** OPSIN cannot read `N1,N2` locants on `oxamide` (the book's PIN, p. 653), `oxobis[(propan-2-yl)oxy]phosphanyl` (it wants the multiplied group first), a CIP assignment on a bis-adamantane, and `bis([1,3]dioxolo)[4,5-b:4',5'-d]pyran`.
* **Measured.** Census 1968 -> 1978 exact (98.90%); visible failures 4 -> 0; the 3 wrong-molecule rows left are OPSIN charge misreads. `tests/vendor`: 5723 passed after the amcinonide fix. **Frozen sets** (blind `--frozen-impact`: heldout_v6 unchanged, bluebook_frozen 5 and fresh_v1 3 rows moved), scored once as aggregates: bluebook_frozen unparsable 45 -> 41, read back 1047 -> 1051, wrong 21 -> 21; fresh_v1 read back 1950 -> 1951 of 2000 (97.55%), unparsable 16 -> 14, wrong 17 -> 17, gate disagreement 10 -> 11.
* New `tests/test_namer_round40_ring_systems.py` (each name read back through OPSIN; 6 of 6 mutants killed). D-215 .. D-219 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-11 -- naming round 41: ring cations, cages and amidines on a ring nitrogen (D-220 .. D-224)

Round 40's open list was seven items; all seven are addressed.

* **D-220.** A tricyclic bridgehead iminium was refused because `fusion_general` declined a charged system of more than two rings. The limit is four rings now, and the neutral copy that carries the numbering is made by detaching the charge (`neutralise(detach)`), so the cation is described on its neutral twin and the hydro prefixes follow P-31.1.4.3.4. Bicyclic and tricyclic bridgehead iminiums and amidiniums read back; N-substituted fused cations now get the PIN shape (`1-methyl-9H-imidazo[1,2-a][1,3]benzimidazol-1-ium`) instead of `(...-ium-1-yl)methane`.
* **D-221, D-222.** Twelve curated ring entries had no heteroatom locants (so `name_bridged` and the fusion walk could not number their heteroatoms) and three were partial rings; they are completed (interior label `10c`, so the vendored ratchet stays at 15). Adamantane and cubane carried a numbering that was a mirror image of the book's; both are corrected, and each map is derived from the book's drawing.
* **Cation neutralisation in ring naming.** An aromatic O+/S+ and a five-atom ring iminium N+ are neutralised for the ring name (`_neutralize_ring_other_cations`), but only when no ring atom has an exocyclic double bond (D-209) and, for an iminium, only in a 5-atom ring (six-ring hydro locants moved otherwise). The retained spelling is used for furan, thiophene, pyrroline and imidazoline cations (`3,4-dihydro-2H-pyrrol-1-ium`, `4,5-dihydro-1H-imidazol-3-ium`) instead of the Hantzsch-Widman `azol`/`diazol` form.
* **Resonance forms.** `_canonical_amidinium_form` picks one drawing of a cyclic amidinium before naming, so the two resonance forms of one cation (same InChIKey) now get one name.
* **D-212 (final form).** An N-acyl amidine on a ring nitrogen is a carboximidamide: `N'-benzoyl-3,5-dimethyl-1H-pyrazole-1-carboximidamide`. The imidamide SMARTS excludes a carbon with three acyclic nitrogens so the guanidine shapes keep their names.
* **D-223.** A ring N as the third substituent of an amidinium (`C(=[NH2+])(N)N1CCCC1`) was classified as a neutral amidine: another molecule. It is the cation now.
* **D-224.** An amidinium beside a carboxylic acid was refused. The amidinium is the parent (a cation outranks an acid, P-41 Table 4.1) and the acid a `carboxy` prefix; the tail is named through its carboxylate, `3-carboxypropanamidinium`. A surrogate with two acid groups could not say which end was the amidinium and used to turn both into amidiniums; the round-trip test caught it.
* **App read-back.** `naming_providers.opsin_readable_spellings` offers OPSIN the spelling it reads for four names whose engine form is the book's (`N1,N2-...oxamide`, `oxobis[...]phosphanyl`, a bis-adamantane CIP, `bis([1,3]dioxolo)...pyran`); the name shown is still the engine's, and it is verified when the respelling reads back. The census and benchmark scans still read these four as unparsable.
* **Measured.** Census 1978 -> 1979 exact (98.95%), visible failures 0. `tests/vendor` 5745 passed. **Frozen sets:** heldout_v6 unchanged; fresh_v1 re-scored once, 1951 -> 1956 of 2000 reading back (97.8%), wrong structure 17 -> 15, unparsable 14 -> 11; bluebook_frozen re-scored, read back 1051 -> 1049, unparsable 41 -> 43, wrong 21 -> 21. **That bluebook movement is not this round's:** with every engine file of this round reverted to HEAD, the same two rows still differ from the r40 seal (counts only; no row was read), and none of the five toggles of this round's changes moved them. It was already in the merged round-40 state; the likeliest reason is that the r40 seal predates a late round-40 edit, but that was not established.
* New `tests/test_namer_round41_cations_cages.py` (each name read back through OPSIN). D-220 .. D-224 in `tests/test_namer_known_defects.py`; the D-212 row there and the pins of five other test files were updated after review, each new name reading back.

## 2026-10-11 -- naming round 42: a spiro parent keeps the stereochemistry of its junctions (D-225)

Round 41's census had 21 rows that were not exact; eight were one family, a spiro compound named without (some of) its stereodescriptors. Naming the stereoisomers of every spiro structure in the census showed how general it was: of 79, 35 read back exactly, 22 carried only some of their centres and 22 none.

* **D-225.** Two causes. (a) `spiro.py` rebuilt every locant of a fused partner from its number alone, so a junction atom lost its letter before the prime: the 10b centre of a pyrazolo[1,5-c][1,3]benzoxazine partner was cited `10'` and the 3a and 6a centres of a pyrrolo[3,4-c]pyrrole partner `3` and `6` (`3R,3S`: two centres at one locant, a name OPSIN cannot place). The letter is kept (`10b'`, `3a`). (b) The stereo stage admitted a spiro parent's descriptor at a plain integer locant only, and a spiro system with a bridged or fused partner is classed "bridged" by perception, so the branch written for spiro never saw it: the spiro bicyclo[2.2.1]heptane of the camphor hydantoin lost its bridgeheads `1'` and `4'`. The gate now also keys on the naming method (`_SPIRO_NAMING_METHODS`). The post-assembly OPSIN check is unchanged.
* **Measured.** Census 1979 -> 1987 exact (99.35%); the 8 rows are exact, none other moved. 79 stereoisomers of the census's spiro structures: exact 35 -> 73, stereo lost 22 -> 6, wrong stereoisomer 0 (the validator only checks that OPSIN parses a name, so this read-back is the check that no descriptor is wrong). `tests/vendor` 5745 passed. **Frozen sets** (blind `--frozen-impact`): heldout_v6 and bluebook_frozen unchanged, fresh_v1 5 rows moved and was re-scored once: read back 1956 -> 1961 of 2000 (98.05%), stereo lost 6 -> 2, unparsable 11 -> 10, wrong 15 -> 15.
* New `tests/test_namer_round42_spiro_stereo.py` (each name read back through OPSIN, stereo included; 2 of 2 mutants killed). D-225 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-11 -- naming round 43: amidinium zwitterions, dropped charges, pyrrolinium spelling, helicenes (D-226 .. D-228)

Round 42's open list: the amidinium refusals, the N-substituted pyrrolinium spelling, helicenes without a table, and 13 census rows that were not exact.

* **D-226.** An amidinium with a carboxylate (`NC(=[NH2+])CC(=O)[O-]`), a carboxyl on its own carbon (`NC(=[NH2+])C(=O)O`, whose surrogate acid is oxalic acid) or a second acid was refused. The amidinium is the parent and the other group a prefix (a cation outranks an acid and an anion, P-41 / P-73): `carboxylatoacetamidinium`, `3-carboxylatopropanamidinium`, `4-carboxylatobenzamidinium`, `carboxyformamidinium`, `carboxyacetamidinium`. The classifier claims the lone carboxylate with the amidinium; the carboxylate is protonated, the cation named, and the one `carboxy` word cited as `carboxylato`. A zwitterion with a second acid is still refused (which `carboxy` is the carboxylate cannot be said by a count).
* **D-227.** The census's "hydrogen" rows were not hydrogen: a thiolate or phenolate beside a group that outranks the thiol or alcohol (a nitrile, an aldehyde, an amide) was named as the neutral compound, the site a `hydroxy` / `sulfanyl` prefix and the charge in no word of the name (`N#CCCn1cnc2c([S-])ncnc21` was `3-(6-sulfanyl-9H-purin-9-yl)propanenitrile`). P-73 makes the anion the senior class, so the parent of the name would be the thiolate (`4-cyanobenzene-1-thiolate`); that needs the engine to pick its principal group by charge and is not done. The anion is cited as the `oxido` / `sulfido` prefix (`4-sulfidobenzene-1-carbonitrile`, OPSIN reads it), by a net under every route (`_restore_dropped_chalcogen_anion`, like the nuclide check) and in the charge-perception renderer for salts. Only when the neutral prefix occurs exactly as often as there are sites; a real OH beside the phenolate is a refusal. `thiocyanate` and the retained alkoxides are untouched.
* **N-substituted pyrrolinium (round 41's open item).** `C[N+]1=CCCC1` was `3,4-dihydro-2H-azol-1-ium`: the ring carved from its substituent has three bonds and no H, RDKit gave the N a radical electron, the neutral copy did not sanitise, and the retained lookup never happened. `1-methyl-3,4-dihydro-2H-pyrrol-1-ium`, `1,2,3-trimethyl-4,5-dihydro-1H-imidazol-3-ium`.
* **D-228.** The ring-locant sweep (round 14) listed penta- to octahelicene as table-less: 224 of their 260 cases named another isomer (`N-hexahelicenylacetamide`, no locant). The table is OPSIN's numbering, found by walking the periphery until the symmetry classes of `k-chloro<helicene>` agree (OPSIN cannot tell the two mirror atoms apart); the junction letters are filled by `fusion_locants.derive_fusion_locants`. Sweep: 224 wrong -> 0.
* **Not the engine's:** the cephem and morphinan census rows differ only because OPSIN adds the stereo a retained name implies; three charge misreads and three unparsable names are OPSIN limits.
* **Measured.** Census 1987 -> 1989 exact (99.45%), visible failures 0. `tests/vendor`: the full run was 5746 passed, 1 failed (`D-016y`: the first version of the dropped-anion net refused `thiocyanate`); after narrowing it the whole `test_known_defects.py` passes (2775), and the rest of the suite was not re-run. **Frozen sets** (blind `--frozen-impact`): heldout_v6 and bluebook_frozen unchanged; fresh_v1 moved 1 row and was re-scored once: read back 1961 -> 1962 of 2000, wrong 15 -> 14.
* New `tests/test_namer_round43_charge_and_cations.py` (each name read back through OPSIN; 8 of 8 mutants killed after a dead hook was removed and a salt case added). D-226 .. D-228 in the fixed table of `tests/test_namer_known_defects.py`; `ring_sweep_population.json` regenerated (the curated table changed).

## 2026-10-12 -- naming round 44: the anion is the parent, protonated acylhydrazones, E/Z on a branch, spiro ammonium stereo, two more ring tables (D-229 .. D-232)

Round 43's open list: the anion cited as a prefix, a protonated hydrazone that dropped its charge, E/Z lost on a methyl-branched alkenyl substituent, a spiro ammonium with no descriptors, and two table-less rings.

* **D-229.** An anion outranks every neutral class that is not an acid (P-41), so a thiolate or phenolate is the PARENT beside a nitrile, an aldehyde, an amide or a ketone: `4-cyanobenzene-1-thiolate`, `4-cyanobenzen-1-olate`, `9-(2-cyanoethyl)-9H-purine-6-thiolate`, `sodium 4-cyanobenzene-1-thiolate`. Round 43 kept the charge as an `oxido` / `sulfido` prefix. The carved-anion route (`engine.py`, ANION mode) restricted competing alcohol / thiol types to the carved site but let every other type win on its own seniority; it now drops them all, neutral acids included. The charge-perception renderer tries the engine's own anion route on the CHARGED molecule first (`_chalcogen_anion_as_parent`) and falls back to the prefix. It also corrects a wrong-group case: with a neutral COOH the ANION route took the acid as the parent and moved the charge to it (`OC(=O)c1ccc([O-])cc1` was `4-oxidobenzoate`; it is `4-carboxybenzen-1-olate`). `_restore_dropped_chalcogen_anion`, the round-43 net, stays: no route reaches it now, which is the point of a net.
* **D-230.** The `hydrazide` and `thiohydrazide` groups matched a charged N', so `C=[NH+]NC(=O)c1ccccc1` was `N'-methylidenebenzohydrazide`, the neutral compound. Their N' is neutral now, and the protonated acylhydrazone falls to the amide route that already writes `azaniumyl`: `benzamido(methylidene)azanium` (census row 1936625).
* **D-231.** `_collect_stereo_descriptors` found a double bond by its stereo flag. A substituent is carved with the cut side replaced by H, so a bond that stops being stereogenic there (`CH3-CH=C(CH3)-CH2-N` leaves two methyls on one end) has no flag, only the descriptor it inherits (`_ParentCIPCode`), which stereo perception reports and the collector ignored. `N-[(2E)-2-methylbut-2-en-1-yl]acetamide` and the Z form are two names (census row 1935625).
* **D-232.** A protonated amine (`[N@H+]`) has no configuration to cite (it inverts and exchanges its proton); only a quaternary N+ is a stable stereocentre. A descriptor was emitted for it, OPSIN could not place it, and the validation pass stripped every tetrahedral descriptor of the spiro parent with it. No descriptor is emitted at an N+ that carries H. The census's spiro structures, 79 stereoisomers read back through OPSIN with stereo: exact 73 -> 79.
* **Ring tables.** Octahydropyridazino[1,2-a][1,2]diazepine: the numbering `fusion_orientation.preferred_numberings` derives (a fusion heteroatom takes its own number, so the nitrogens are 5 and 11); sweep 28 of 34 wrong -> 0. Corrin: the numbering the Blue Book DRAWS (pdf p. 1158: C1-C19 with no 20, N21-N24 with the NH on N24); the fusion routine cannot derive it (a 15-membered ring needs a distorted shape). Checked against OPSIN: `k-chlorocorrin` at all 13 positions that carry a hydrogen is the same compound, full InChIKey, as chlorine on the table's atom k; sweep 10 of 33 wrong -> 0. (An earlier probe of OPSIN for corrin looked ambiguous because the atoms were matched by skeleton alone.)
* **Not an engine fix:** the cephem and morphinan census rows differ because OPSIN adds the stereo a retained name implies; the three charge misreads and three unparsable names are OPSIN's.
* **Measured.** Census 1989 -> 1991 (99.55%) exact, visible failures 0. `tests/vendor`: the full run (before the corrin table and the removal of one known-defects row) was 5759 passed, 2 failed, both the `D-232` row, whose harness compares canonical SMILES and so sees the nitrogen's tag; the row moved to the new test, where the InChIKey is compared. After the corrin table only the ring-table guards were re-run (`test_ring_table_locants`, the sweep test), which pass. **Frozen sets** (blind `--frozen-impact`): heldout_v6 and bluebook_frozen unchanged; fresh_v1 moved 6 rows and was re-scored once: read back 1962 -> 1964 of 2000, stereo lost 2 -> 0, wrong 14 -> 14, unparsable 10 -> 10.
* New `tests/test_namer_round44_parent_anion_and_stereo.py` (each name read back through OPSIN, stereo included; 6 of 6 mutants killed; the pyridazino and corrin cases pinned too). D-229 .. D-231 in the fixed table of `tests/test_namer_known_defects.py`; round 43's test no longer pins the prefix forms; `ring_sweep_population.json` regenerated.

## 2026-10-12 -- naming round 45: ring cation before a curated ketone suffix, an amidinium zwitterion with a second acid (D-233, D-234)

Round 44's open list: an amidinium zwitterion with a second acid, a curated ring cation OPSIN could not check, four names OPSIN cannot read as written, a quaternary N+ stereocentre OPSIN cannot place, and two bluebook_frozen rows that differ from the r40 seal.

* **D-233.** Camptothecin's pentacycle is a curated ring whose NAME carries its ketone (`...quinoline-3,14(4H)-dione`). A ring cation has no suffix group to put `-ium` before, so it was appended after the `dione`: `...-3,14(4H)-dion-6-ium`, which OPSIN cannot read (round 41's "a curated ring cation OPSIN cannot check"). `assembly.py` puts it before the ketone suffix, as it does before any other suffix (P-74): `1,12-dihydro-14H-pyrano[3',4':6,7]indolizino[1,2-b]quinolin-6-ium-3,14(4H)-dione`, `4-ethyl-4-hydroxy-...` (camptothecin protonated) and the N-methyl cation, all read back. Cations whose ketone is an `oxo` prefix (`7-oxoindolizidin-4-ium`) are unchanged.
* **D-234.** An amidinium with a carboxylate AND a neutral carboxylic acid was refused: protonating the carboxylate left two `carboxy` words, and a count cannot say which was the anion. The neutral acid is named as its methyl ester, whose prefix (`(methoxycarbonyl)`, or `4-methoxy-4-oxo` at the end of a chain) cannot be confused with the carboxylate's `carboxy`, and the two are mapped back: `3-carboxylato-4-hydroxy-4-oxobutanamidinium`, `3-carboxylato-5-carboxybenzamidinium`. A quaternary carbon carrying both acids is still refused.
* **The four OPSIN-limit names (tooling).** The engine's names are the book's and OPSIN reads them only respelt; the application's read-back already tried the respelling (round 41). `tools/naming_census_scan.py` now does too, only for a name OPSIN failed to parse and only after the original, so the census no longer counts them unparsable. The frozen-set scorer (`naming_stage_artifact.py`) is deliberately NOT changed, so its seals stay comparable with every earlier stage.
* **Measured, not fixed.** (a) A quaternary N+ stereocentre: OPSIN reads a descriptor only for an ACYCLIC one (`(R)-N-ethyl-N-methyl-N-propylanilinium`, `(NR)-...`, `(R)-ethyl(methyl)phenyl(propyl)azanium` all read back, the S forms read as the other enantiomer), and in no form for the N+ of a bridged parent (ipratropium: `(1R,5S,8r)`, `8s`, `8R`, `8S`, with and without `3r`, all fail to parse). So a bridged N+ stereocentre cannot be verified and stays unnamed; the acyclic one is a candidate. (b) bluebook_frozen's two differing rows: a counts-only blind check on the round-40 merge commit itself (`git archive`, run with that tree first on `PYTHONPATH`) differs from the r40 seal on the same 2 rows, so the seal was made before a late round-40 edit; rounds 41 to 44 did not cause it, and the r41 seal supersedes it.
* **Measured.** Census 1991 -> 1993 exact (99.65%), visible failures 0, unparsable 0 (3 -> 0). `tests/vendor`: 5763 passed. **Frozen sets** (blind `--frozen-impact`): all three unchanged, so none was re-scored; the stage list stays `r44-fresh-v1,r41-final-evaluation,r38-final-evaluation`.
* New `tests/test_namer_round45_cations_and_zwitterions.py` (each name read back through OPSIN; 4 of 4 mutants killed). D-233 and D-234 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-12 -- naming round 46: an anion beside a neutral group, imide / acylurea / sulfamide anions, a sulfamide prefix, and a charge guard (D-235 .. D-238)

Round 45's census was saturated (1993 of 2000, seven rows, all OPSIN artifacts), so the round looked for what the census could not show: it deprotonated ONE acidic site of every census molecule (sulfonamide NH,
carboxylic acid, phenol, thiol, tetrazole, imide, acylsulfonamide, sulfonic acid: 285 anions) and named each. 21 of the first 169 were wrong, in three families, all of them "the name has no charge".

* **D-235.** `CC(=O)Nc1ccc(S(=O)(=O)[N-]c2ncccn2)cc1` was `N-{4-[N-(pyrimidin-2-yl)sulfamoyl]phenyl}ethanamide` (census row 2072). The charge-conservation step in ANION mode restricts a type to its charged instances,
  but an AMIDE is not in the anion-variant family, so it competed on its own seniority, won, and the charged sulfonamide fell to a `sulfamoyl` prefix. An anion outranks every neutral class (P-41: anions 4, acids 7, amides 8), as
  the carved-anion branch already applied. `engine.py` now drops the types with no charged atom when a family type has a charged instance; a cation type is kept. `4-acetamido-N-(pyrimidin-2-yl)benzene-1-sulfonamidate`.
* **D-236.** No classifier claimed an N- with two heavy neighbours when one is an acyl or sulfamoyl group, so the plan search neutralised it: `O=C1CCC(=O)[N-]1` -> `pyrrolidine-2,5-dione`, a barbiturate -> the neutral trione,
  `CNS(=O)(=O)[N-]c1ccccc1` -> `sulfamoylmethane` (the phenyl gone as well), `CC(=O)[N-]C(=O)NC` -> a `NAMING ERROR`. New `_classify_azanide` / `_render_azanide` (`perception/charge_perception.py`): P-72.2.2.2 names the anion
  of an amide, hydrazide or imide with the parent `azanide` (`diacetylazanide`, `acetyl(methylcarbamoyl)azanide`, `(N-methylsulfamoyl)(phenyl)azanide`, the acyl groups named by the acid -> acyl trick `amide_anion` uses), and a ring
  nitrogen is the ring's own `-ide`, the substituent anchored at N with its `yl` changed (`2,5-dioxopyrrolidin-1-ide`, phthalimide, barbituric acid, a lactam, a cyclic carbamate). The ordinary sulfonamide anion (S bonded to carbon) is
  not claimed: the engine names it `-sulfonamidate` already. An acyclic ester or carbamate carbon is not claimed either (its acyl name is `methoxymethanoyl`, not `methoxycarbonyl`); it is refused.
* **D-237.** `[O-]C(=O)c1ccccc1NS(=O)(=O)N(C)C` was `2-(N,N-dimethylsulfamoyl)benzoate`, and `[O-]c1ccccc1NS(=O)(=O)N(C)C` `2-sulfamoylbenzen-1-olate`. A demoted sulfonamide group took the first nitrogen it found; a sulfamide has two,
  so the linking NH was dropped and the methyls were cited on the wrong atom. A sulfonyl with two nitrogens is named recursively: `2-[(dimethylaminosulfonyl)amino]benzoate`.
* **D-238.** The net under every fix of this kind: rounds 43 and 44 (alkoxides and thiolates) and this round (imides) each closed one shape and left the next the same way, because an unclaimed charge falls through to the neutraliser BY DESIGN
  (pyridinium and nitrobenzene are named by other paths). `_check_charge_named` (`engine.py`) refuses a single-fragment ion whose name has no word for its charge: `-ide` (not `amide` / `imide`), `-ate`, `sulfonato` / `oxido` prefixes for an
  anion, `ium` / `onio` for a cation. A salt (two fragments) and a zwitterion (net zero) are not judged. It refuses what it cannot name: saccharin's anion, an acyclic N-acyl carbamate.
* **Measured.** Census 1993 exact, unchanged, no row refused. The anion population: 285 anions, 21 of the first 169 wrong before, 4 flagged after, all thioamide / isothiourea thiolates (`NC([S-])=N...`, whose name cites `sulfanide`
  inside the chain and OPSIN cannot read). `tests/vendor`: 5769 passed (full run); the app's naming tests 3824 passed. **Frozen sets** (blind `--frozen-impact`): heldout_v6 unchanged; bluebook_frozen changed 4 of 1126
  and fresh_v1 2 of 2000, both re-scored once: heldout_v6 unchanged; bluebook_frozen re-scored once (r46-final-evaluation): wrong_structure 21 -> 17 and no_prediction 13 -> 17, four silent wrong molecules are refusals now, every other count identical; fresh_v1 moved 2 rows and was re-scored once (r46-fresh-v1): every outcome count identical. The stage list for `--frozen-impact` becomes `r46-fresh-v1,r46-final-evaluation,r38-final-evaluation`.
* New `tests/test_namer_round46_anions_beside_neutral_groups.py` (85 tests; each name read back through OPSIN with its charge, `-sulfonamidate` compared on neutral connectivity because OPSIN reads it neutral; 8 of 8 mutants killed).
  D-236 and D-237 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-13 -- naming round 47: the hydro prefixes of a protonated ring cation (D-239)

Round 46 looked for what the census could not show by deprotonating one site of every molecule. Round 47 did the same with the cations: it protonated ONE basic site of every census molecule (aromatic and
azole N, primary, secondary, tertiary amines, anilines, imines, amidines: 1036 cations) and read each name back through OPSIN with its charge. 5 were flagged, 11 were refused by round 46's charge guard
(protonated amidoximes, imidates, thioamides and exocyclic iminium cations: visible, not wrong), and the rest read back.

* **D-239.** `O=C1CCC=C2[NH2+]C=CCC12` was `5-oxo-1,4,6,7-tetrahydroquinolin-1-ium`. The NEUTRAL route was right (`5-oxo-1,4,4a,5,6,7-hexahydroquinoline-4-carboxylic acid`): `indicated_hydrogen_p58` plans the
  hydrogens, counting an exocyclic C=O as the saturated ring carbon it is once the ketone is a prefix, but it declined a charged ring atom, and a ring cation fell to the retained route's own count, which
  leaves out the sp3 fusion carbon 4a and the ketone carbon. A ring cation is named for its NEUTRAL skeleton plus `-ium` (P-73.1.1), so `_resolve` now plans on the deprotonated twin of a protonated ring N+
  (`_deprotonated_twin`: same atoms, the proton given back; a quaternary N+ has none to give back and is left to the old route; a fully saturated parent keeps its saturated retained name, `7-oxoindolizidin-4-ium`).
  The `5-oxo-4a,5-dihydroquinolin-1-ium` case read back as a DIFFERENT molecule before (`5-oxoquinolin-1-ium`), the others were unparsable.
* **Two earlier pins moved to the rigorous form**, both OPSIN-verified: round 45's `4-oxopyridin-1-ium` for `O=C1C=C[NH+]=CC1` is `4-oxo-3,4-dihydropyridin-1-ium`, and `5-oxo-2,3-dihydropyridin-1-ium` for
  `O=C1CCC[NH+]=C1` is `5-oxo-2,3,4,5-tetrahydropyridin-1-ium` (the oxo carbon and its neighbour are cited, as the neutral route cites them). The old spellings were OPSIN-lenient, not wrong molecules.
* **Measured.** Cation population 1036: 5 flagged -> 2 (both OPSIN limits: the bis([1,3]dioxolo)pyran and a bicyclo-heptyl phosphonate prefix); 11 refused, unchanged. Census 1993 exact, unchanged (two rows changed
  spelling, both still exact). App naming tests 3847 passed; `tests/vendor` and the known-defects file: 7399 passed (the full vendored suite and the known-defects file). **Frozen sets** (blind `--frozen-impact`): all three unchanged, none re-scored; the stage
  list stays `r46-fresh-v1,r46-final-evaluation,r38-final-evaluation`.
* New `tests/test_namer_round47_protonated_ring_cation_hydro.py` (each name read back through OPSIN with charge and stereo; 4 of 4 mutants killed). D-239 in the fixed table of `tests/test_namer_known_defects.py`;
  `tests/test_namer_round45_cations_and_zwitterions.py` and `tests/test_namer_ylidene_ring_cations.py` take the two moved pins.

## 2026-10-13 -- naming round 48: the cation and the indicated hydrogen on different nitrogens in a hydro azolium (D-240)

Round 47 left one open question: does a QUATERNARY ring N+ (no proton to give back) carry the hydro omission round 47 fixed for protonated cations? Round 48 measured it: it N-methylated ONE basic nitrogen of
every census molecule (1036 quaternary cations) and read each name back through OPSIN with its charge. The answer is no: no hydro omission, 3 flagged (2 OPSIN limits), 2 refused by the charge guard.

* **D-240.** The one real defect: `Cn1c[n+](C)c2CCCCc12` was `1,3-dimethyl-4,5,6,7-tetrahydro-1H-benzimidazol-1-ium`. An N-substituted [n+] takes the `-ium` and cannot also be the indicated-hydrogen site (the
  same rule that already gave `1,3-dimethyl-1H-benzimidazol-3-ium`), so `_retag_indicated_h` moves the `1H` to a neutral substituted nitrogen. It read only the START of the name, and a hydro block comes first
  (`4,5,6,7-tetrahydro-1H-...`), so a hydro parent was never retagged. The ring offered two candidates (the cation at 3, the cation at 1); the wrongly tagged one won on the lowest cation locant, and OPSIN reads
  its name as a molecule with a CH2 at C2 (`C[NH+]1CN(C2=C1CCCC2)C`). `retained_lookup.py` now looks past a leading hydro block (`_HYDRO_HEAD_RE`) and keeps it.
* **Measured.** Quaternary population 1036: 3 flagged -> 2 (both OPSIN limits: the bis([1,3]dioxolo)pyran and a bicyclo-heptyl phosphonate prefix), 2 refused, unchanged. Census 1993 exact, unchanged. App naming
  tests 3849 passed; `tests/vendor` and the known-defects file: 7402 passed (the full vendored suite and the known-defects file). **Frozen sets** (blind `--frozen-impact`): all three unchanged, none re-scored.
* New `tests/test_namer_round48_azolium_indicated_hydrogen.py` (34 tests; each name read back through OPSIN with its charge). **Mutants:** 1 of 3 killed. The two that survive are not distinguished by any structure
  found: the retagged candidate never beats its mirror-image numbering (it loses on the lowest indicated hydrogen, so dropping its hydro head changes no name), and `tetrahydro` is the only hydro prefix this path
  produces for an azolium (the multiplier alternation is the module's usual one). They are recorded, not claimed killed. D-240 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-13 -- naming round 49: the ions rounds 44 to 48 left refused or unreadable (D-241 .. D-245)

Round 48's open list, taken whole: the protonated amidoximes, imidates and thioamides the charge guard refuses, the thioamide thiolates, the N-acyl carbamate and saccharin anions, a neutral acid beside a sulfamide, and an
amidinium zwitterion with both acids on one carbon. OPSIN was asked FIRST which spellings it reads, and every candidate did (several equal to the input exactly), so each item became a rendering choice, not a question of
what can be verified.

* **D-241.** No classifier claimed an acyclic iminium `C=[NH+]` whose carbon carries O, S or another N (`NC(=[NH2+])OC`, `CC(=[NH2+])S`, `NC(=[NH+]O)C(Cl)(Cl)Cl`), so the plan search neutralised it and promoted the thiol, amine or
  hydroxylamine to the principal group: `1-iminoethane-1-thiol`, the neutral compound, which round 46's guard turned into a refusal. `_classify_iminium_hetero` / `_render_iminium_hetero` name the cation as the parent in the
  form the engine already wrote for `COC(=[NH2+])CC`: the group on the carbon as an `-ylidene` (`engine._fvi_*` / `carve_substituent`, the executor's own path) and the other substituents of N+ as prefixes,
  `(1-amino-2,2,2-trichloroethylidene)(hydroxy)azanium`. It runs after the amidinium classifier, which keeps its own (`CC(N)=[NH2+]`).
* **D-242.** An ester or carbamate carbon on an anionic N was acyl-like in nothing but name: the acid -> acyl trick names the carbonic monoester and gives `methoxymethanoyl`. `_alkoxycarbonyl_prefix` names the alkoxy group on its
  own and cites `carbonyl` (`acetyl(methoxycarbonyl)azanide`, `[(2-chloroethoxy)carbonyl](methyl)azanide`); a carbonate has no single such group and is declined. Saccharin's anion: the substituent namer returns
  `1,1,3-trioxo-1,2-benzothiazol-2(3H)-yl`, and the added hydrogen `(3H)` broke the locant parse; the anion has no such hydrogen, so it goes: `1,1,3-trioxo-1,2-benzothiazol-2-ide`.
* **D-243.** The single-atom prefix table named S- `sulfanide`, which is the parent hydride's anion (`disulfan-1-ide`) and unreadable as a prefix (`{[amino(sulfanide)methylidene]carbamoyl}benzene`); it is `sulfido`, as O- is
  `oxido`. And `amino` + `imino` ran together as `aminoimino` (OPSIN: `NN=C[S-]`, an N-N bond; `hydroxyimino` is the group =N-OH); the assembler brackets the second: `amino(imino)methanethiolate`.
* **D-244.** `_name_sulfamide_functional_parent` had no seniority check, unlike the urea and nitramide parents it mirrors. A sulfamide is the amide of sulfuric acid (class 11); an acid, ester or acid halide outside the core
  outranks it (P-41). It now takes `perception` and declines on any group of the amide class or above outside its atoms: `2-[(dimethylaminosulfonyl)amino]benzoic acid` (round 46's D-237 prefix). A nitrile, alcohol
  or ketone does not outrank it, and a carboxamide wins as the parent (`...benzamide`).
* **D-245.** `NC(=[NH2+])C(C)(C(=O)[O-])C(=O)O` was refused: the masked ester is a chain-end `3-methoxy-3-oxo`, but another prefix sits between them alphabetically (`3-methoxy-2-methyl-3-oxo`), so the adjacency
  regex missed it. The methoxy and oxo locants are matched on their own: `2-carboxylato-3-hydroxy-2-methyl-3-oxopropanamidinium`. A carboxylate beside TWO neutral acids is still refused.
* **Measured.** Every name above reads back through OPSIN to its input, charge included. Census 1993 exact, unchanged (4 rows changed spelling, all still exact; two are this round's: a sulfamide beside an acid and an
  exocyclic iminium). App naming tests 3960 passed (the full group on the final code, after three refusal pins were repointed); `tests/vendor` and the known-defects file: 7420 passed (the full vendored suite and the known-defects file). **Frozen sets** (blind `--frozen-impact`): heldout_v6 unchanged; bluebook_frozen moved 2 rows and
  fresh_v1 1, re-scored once: heldout_v6 unchanged; bluebook_frozen re-scored once (r49-final-evaluation): unparsable 43 -> 42 and equivalent 526 -> 527, every other count identical; fresh_v1 re-scored once (r49-fresh-v1): every outcome count identical. The stage list for `--frozen-impact` becomes `r49-fresh-v1,r49-final-evaluation,r38-final-evaluation`.
* New `tests/test_namer_round49_open_ions.py` (7 of 7 live mutants killed; an eighth, an amidinium exclusion in the new classifier, moved no name and was deleted as dead code). D-241 .. D-245 in the fixed table of
  `tests/test_namer_known_defects.py`. Three earlier tests pinned refusals this round turned into names and now pin the cases still refused: a carboxylate beside two neutral acids
  (`test_namer_round43_*`, `test_namer_round45_*`) and a pyrazolone anion (`test_namer_round46_*`).

## 2026-10-21 -- naming round 77: naphthyridine components, multiparent names, aromatic von Baeyer (D-351 .. D-354)

`ring.py` (scratch, `D:\_scratch\r60\r77`): one ring atom of each census molecule changed (aromatic CH -> N, N -> C, a saturated ring CH2 -> O/S/NH), 2,200 molecules, one to three atoms: clean to 0.3%. `fuse.py`: 19 polycyclic skeletons with up to three CH -> N and a varied five-ring heteroatom, 916 systems (1,443 with a methyl): 150 of 916 failed before.

* **D-351.** `POLYCYCLES` (the fusion constructor's components) had no naphthyridine, and `_LOCANT_NAMED_POLYCYCLES` was empty: a pyridine fused to a diaza bicycle had three equal pyridine parents ("a multiparent system"). The six `[1,5]` .. `[2,7]naphthyridine` are components (numbered by the fusion rules, Table 2.8's bracketed form); a naphthyridine alone keeps `1,8-naphthyridine`. A benzo-fused one is now `benzo[b][1,6]naphthyridine`, not `pyrido[4,3-b]quinoline` (two rings and two nitrogens is the senior parent); both read back.
* **D-352.** Two occurrences of the parent joined by ONE other component (P-25.3.4.1.2) were refused (`NEEDS_UNBUILT_CONSTRUCTION`): `_multiparent_name` builds `central[loc-letter:loc-letter']di<parent>` for a plain parent and one central component with one letter each, the lowest letters then the lowest locants, the first group the one with the lowest locants (`furo[2,3-b:5,4-c']dipyridine`, `9H-pyrrolo[2,3-b:5,4-c']dipyridine`). Anything else keeps the refusal.
* **D-353.** `_detect_vb_unsaturation` returned no bonds for a wholly aromatic system (`if ring_system.aromatic: return [], []`), so a fully aromatic system the fusion constructor declined was named a SATURATED von Baeyer cage (`2,5,9-triaza...tetracosane`): another molecule. The aromatic bonds are Kekulized and cited as enes (`...tetracosa-1(23),2,4,...-dodecaene`); valid and read back, not a PIN.
* **D-354.** `fusion_descriptor` returns no descriptor when the attached component's locants repeat a label (`pyreno[3a,3,5,4,3a-aklmn]phenanthridine`), which OPSIN cannot read.
* **Measured.** `fuse.py` 916 systems: 150 failures -> 0 after D-351..D-354 (naming errors 75 -> 0, wrong 40 -> 0, unparsable 1 -> 0); with a methyl on each, 1,443 of 1,443. Vendored suite 5989 passed.
* New `tests/test_namer_round77_ring_atom_scan_naphthyridine_components_and_multiparent_fusion.py`.

## 2026-10-20 -- naming round 76: a lone N-substituent on a later amide, and groups a plan may not take (D-344 .. D-350)

`deco.py`, `deco3.py`, `deco4.py` (scratch, `D:\_scratch\r60\r76`): ONE extra functional group (29 of them: OH, NH2, COOH, CONH2, CN, SO3H, NO2, esters, a phosphate, a peroxide, B(OH)2, SiMe3 ...) attached to a random C-H (`deco`) or N-H, O-H, S-H (`deco4`) of each census molecule, or two or three to a small scaffold (22 chains and rings, `deco3`); named, read back through OPSIN and compared on the standard InChIKey. Past the census it is a percent: 14 of 1,400 (`deco`), 13 of 1,800 (`deco3`), 35 of 2,100 (`deco4`).

* **D-344.** `_N_BEARING_FG_TYPES` has no primary `amide`, so a diamide's unsubstituted amide is not counted: `CCNC(=O)CC(C)C(N)=O` saw one position, `_n_needs_disambiguation` stayed False and `_n_sub_locant` returned a bare `N`, which is the first group's: `N-ethyl-2-methylbutanediamide` put the ethyl on the amide at C1. The other amides (and thioamides) of the parent are counted for the positions; a bare N stays where the substituted nitrogen is on the lowest-numbered group (`N-ethylbutanediamide`, pinned), every other cites its position: `N4-ethyl-2-methylbutanediamide`, on chains, benzenes and cyclohexanes.
* **D-345.** Two terminal `-thioic S-acid` suffixes were multiplied, `butanedithioic S-acid`, which OPSIN reads as ONE group (`C(=S)S`); no spelling of the two-group name is readable (`di(thioic S-acid)`, `bis(...)`, `S,S'-acid` all fail). `IUPACCanonical.accept_plan` declines a substitutive plan with two or more of them when one is terminal, so one takes the suffix and the other is `sulfanyl(oxo)methyl` (`3-[sulfanyl(oxo)methyl]propanethioic S-acid`); a ring's `benzene-1,2-dicarbothioic S-acid` is read and stays.
* **D-346.** `carbamate` is an ESTER (the functional-class route, or a `carbamoyloxy` prefix), but a plan with it as the PCG was accepted when a more senior group made the functional-class route decline: `2-(phosphonooxy)ethane-1-carbamate`, which OPSIN reads as the N-alkyl carbamate ANION. `accept_plan` declines a substitutive plan whose principal group is a carbamate, thiono- or dithiocarbamate. The next plan names it `1-(carbamoyloxy)-2-(phosphonooxy)ethane`: valid, not a PIN (a phosphate ester would be the parent, `2-(carbamoyloxy)ethyl dihydrogen phosphate`; not built).
* **D-347.** The `imidamide` group's second nitrogen is any `[NX3;!R;!$([NX3]-[#7])]`, which a nitro group's N+ satisfies: `C(=NO)[N+](=O)[O-]` was `N'-hydroxy-N-oxido-N-oxopiperidine-4-carboximidamide`. `!$([NX3+](=O)[O-])` joins it: `4-[(hydroxyimino)(nitro)methyl]piperidine`.
* **D-348.** `acetamido` + `oxy` was written `acetamidooxy` by three routes, which OPSIN reads as `acetamido` with the `oxy` dropped (`2-acetamidooxybenzoic acid` is 2-acetamidobenzoic acid: another molecule). `_preferred_prefix_spelling` (every prefix passes it) rewrites `([a-z]+amido)oxy` to `(\1)oxy`: `2-[(acetamido)oxy]benzoic acid`, `[(acetamido)oxy]di(ethoxy)(oxo)phosphane`, `[(acetamido)oxysulfonyl]benzene`.
* **D-349.** `R-O-O-O-H`: the carved `-O-OH` was named `hydroxyyl` and the whole `(hydroxyylperoxy)`, which OPSIN cannot read; the heteroatom-prefix route names it `(hydroperoxy)oxy`, and the peroxy contraction (`(Xoxy)oxy` to `Xylperoxy`) leaves `hydroper` alone.
* **D-350.** `_LEADING_PREFIX_WORDS` (the detachable prefixes that make a longer word a compound prefix, so enclosed) lacked `anilino`: `1-anilinoacetyl-2-methylhydrazine-1-phosphonic acid`, which OPSIN cannot parse after a locant, is `1-(anilinoacetyl)-...`. Two pinned names moved with it (`{1-[(anilinomethanethioyl)amino]butylidene}oxidanium`, round 57; read back).
* **Probe tests.** `tests/test_naming_probe_tool.py` kept its failed-top-plan example on the ethyl carbazate, whose carbamate plan is no longer tried; the molecule is `CCSC(S)=Nc1ccccc1` now, as the test's own docstring asks.
* **Measured.** `deco4` 35 -> 12 of 2,100 (what is left: a morphinan's stereo, a cephem's and a bis-dioxolopyran's, which OPSIN reads without, and a sulfonamidate anion OPSIN reads neutral); `deco3` 13 of 1,800 -> 1 of 1,400. Vendored suite 5975 passed; app namer tests 5596 passed; 11 of 11 mutants killed.
* New `tests/test_namer_round76_diamide_n_locants_and_groups_a_parent_cannot_take.py`.

## 2026-10-19 -- naming round 75: thio and seleno acid groups the name had no prefix for (D-340 .. D-343)

`swap.py` (scratch, `D:\_scratch\r60\r75`): ONE heavy atom of each census molecule is swapped for its congener (`O` to `S` or `Se`, `S` to `O` or `Se`, `N` to `P` or `As`, `C` to `Si` or `Ge`; a `chalc` mode keeps to the chalcogens), the result is named, read back through OPSIN and compared on the standard InChIKey. 600 any-element swaps (seed 1): 569 ok, 19 another molecule, 8 NAMING ERRORs, 4 unparsable. 1,600 chalcogen swaps (seeds 2 and 3): 59 NAMING ERRORs, 10 unparsable, 8 another molecule.

* **D-340.** The `sulfonothioamide` FG is `[NX3H2,NX2H1-]` (loosening it names `(aminosulfonothioyl)benzene` for an N-methyl one, which drops the N-substituent: tried, reverted), so a group `R-S(=O)(=S)-N<` or a thiosulfone `R-S(=O)(=S)-R'` fell to the carved fragment, whose free valence reads as `[SH]`: `{[NAMING ERROR: No valid naming plan found for CN[SH](=O)=S]}benzene`. 59 of 1,600. The `R-sulfonyl` / `R-sulfinyl` prefix path (`_name_heteroatom_fv_substituent`) counted only `=O`; `_sulfur_group_suffix` counts the terminal `=O`, `=S` and `=Se` and spells the suffix of P-65.3.1: `sulfonothioyl`, `sulfonoselenoyl`, `sulfinothioyl`, `sulfonodithioyl` (`4-(methylsulfonothioyl)aniline`). A mixed pair (`thio` and `seleno`) is left to the NAMING ERROR it was: built without the guard it names `sulfonodithioyl` and silently turns the Se into S.
* **D-341.** The same path for a selenium and a tellurium centre (`_CHALCOGEN_ACID_STEM`). `selenonamide` is `[NX3,NX2-]` with the prefix `selenonamido`, which OPSIN does not read and which, being a fixed prefix, dropped the N-substituent of an N-substituted one (`selenonamidobenzene` for `PhSe(=O)(=O)NHPh`). It is NH2-only like `seleninamide` and `aminoselenonyl` now, and the N-substituted ones take the prefix path: `[(benzeneselenonyl)amino]benzene`.
* **D-342.** `carbothioic_O_acid` had a group and a `carbothioate` ending; `C([O-])=[Se]` had neither and was `phenylselanylidenemethanolate`, which OPSIN reads as a hypervalent `[SeH]=C`. New FG `carboselenoic_O_acid`, the assembly endings (`carboselenoic O-acid` / `carboselenoate`), the anion and cation lists and the subsumption of the alcohol and phenol it overlaps: `5-(5-formylthiophen-2-yl)thiophene-2-carboselenoate`.
* **D-343.** `S-3,5-dimethylcyclohexyl ethanethioate`, `S-1,8-dimethyl-3,6-diaza...undecan-9-yl ethanethioate` and `S-(isoquinolin-1-yl)(phenyl)methyl ...` are not parsed by OPSIN: a locant list straight after the italic `S-`, or two enclosed prefixes side by side, ends the word. `_enclosed_after_bridge_locant` encloses the organyl in those two cases of the thioester, thionoester and carbamothioate shapes (`S-2-methylcyclohexyl` is read bare and stays).
* **Measured.** 600 any-element swaps (seed 1): 569 -> 577 ok. 1,600 chalcogen swaps (seeds 2 and 3): NAMING ERRORs 59 -> 2, unparsable 10 -> 1, another molecule 8 -> 6. Vendored suite 5967 passed; app namer tests (`test_namer*`, `test_naming*`) 5079 passed; naming gate 187/187; 12 of 12 mutants killed.
* New `tests/test_namer_round75_thio_and_seleno_acid_groups_in_prefixes_and_thioester_organyls.py`.

## 2026-10-19 -- naming round 74: stereo the name used to drop (D-337 .. D-339)

`stereo.py` (scratch, `D:\_scratch\r60\r74`): `EnumerateStereoisomers` gives each census molecule that has stereo a random OTHER stereoisomer; it is named, read back through OPSIN and compared on the full InChIKey, which carries the stereo layer. 600 isomers (seed 11): 527 ok, 73 another stereoisomer. The populations before this (ions, isotopes, tautomers) never changed a double bond's geometry.

* **D-337.** `_collect_stereo_descriptors` cites a C=N bond's E/Z only when its atoms are in the PARENT (`(1E)-N-hydroxyethanimine`). Named as an ylidene PREFIX, a hydrazone (`N'-benzylideneacetohydrazide`), a Schiff base (`2-[(benzylidene)amino]aniline`) or a ketimine is carved away from the bond it hangs from, and `carve_substituent` keeps the bond's code on nothing the name reads. `_with_ylidene_bond_descriptor` puts it back in front of the ylidene, at the three places that carve one (the structural prefix, `_name_heteroatom_fv_substituent`'s `(R-ylidene)amino`, and the hand-built `N-(ring-ylidene)amide` name): `N'-[(E)-phenylmethylidene]acetohydrazide`. A bond whose far end is in the parent is left to the parent's locant (cited once). An ylidene with descriptors of its own cites the new one at the locant of its attachment atom, `N'-[(1Z,2Z)-3-(2-methoxyphenyl)prop-2-en-1-ylidene]...`, since an unlocated one would read as either bond.
* **D-338.** The same for N=N, which never reached `_collect_stereo_descriptors` at all: the diazene parent (`_name_n_core_parent`, a leaf) and the `R-diazenyl` prefix are built by hand. `(E)-diphenyldiazene`, `4-[(Z)-phenyldiazenyl]phenol`.
* **D-339.** A sulfoxide sulfur with three different groups is a stereocentre, and the `R-sulfinyl` prefix is built from the carved R: it dropped the tag (omeprazole and esomeprazole had one name). The prefix cites the sulfur's CIP code, `[(S)-methylsulfinyl]benzene`. The same atom (S, Se, P, As) in a SUFFIX group, a sulfinamide's (Ellman's `2-methylpropane-2-sulfinamide`), has no locant: `_collect_stereo_descriptors` takes the group's atoms (`suffix_stereo_atoms`) and cites ONE such centre unlocated after the located ones, `(S)-2-methylpropane-2-sulfinamide`, `(2S,R)-butane-2-sulfinamide` (OPSIN reads both); two of them stay uncited. A group prefix built from a table (`aminosulfinyl`) takes its centre's code the same way. `_stereo_locant_key` ignores an unlocated descriptor, which does not depend on the numbering.
* **Not changed, and why.** The inherited `_ParentCIPCode` StereoPerception reads first for a double bond is NOT consulted by the new helper: a mutant that took only the local code was not told apart by 1,400 isomers or a dozen nested probes (the cut side of these bonds is an N or S, which ranks last either way).
* **Measured.** 600 isomers (seed 11): 73 -> 20 another stereoisomer; 2,100 more on the final code (seeds 11, 21, 22): 21, 18 and 20 of 700, all in the open list. Vendored suite and app namer tests below; 13 of 13 non-equivalent mutants killed.
* New `tests/test_namer_round74_double_bond_and_sulfoxide_stereo_in_prefixes_and_azo_parents.py`.

## 2026-10-19 -- naming round 73: the defects a non-canonical tautomer finds (D-334 .. D-336)

`tauto.py` (scratch, `D:\_scratch\r60\r73`): RDKit's `TautomerEnumerator` gives each census molecule another form of itself (an imidic acid for an amide, an exocyclic imine for an amine on an azole, a quinoid ring for a conjugated one); it is named and read back through OPSIN, and compared on `MolToInchiKey(options="/FixedH")`, because the standard key calls two tautomers one molecule. The ion populations (15,543 ions, re-run first as a baseline: 15,511 ok) have been saturated for rounds; this one is not.

* **D-334.** `_RETAINED_RING_SUBSTITUENT` contracts `benzene` + `-yl` to `phenyl` whenever the free valence is monovalent, whatever its bond order. A ring joined by a double bond is a quinoid ring: `(4-methylidenephenyl)methanediamine` reads as `C=C1CC=C(C=C1)C(N)N`, two hydrogens more. The contraction now requires a single bond; the name is `(4-methylidenebenzen-1-ylidene)methanediamine`, the spelling of the same ring with two methylidenes that was already `1,4-dimethylidenebenzene` (OPSIN reads both).
* **D-335.** `c1nncs1` and `c1nnco1` were curated without `atom_locants`. Without them the ring has no numbering to place an indicated hydrogen on, so `CN=c1[nH]nc(C)s1` was `2-methyl-5-(methylimino)-1,3,4-thiadiazole`, which OPSIN reads with the hydrogen on C2 (`CC1SC(N=N1)=NC`). The ring-locant sweep (`tools/naming_ring_locant_sweep.py`, 371 rings, 7,372 cases, 0 wrong before and after) moved both rings from "table_less" to "full"; the frozen population `benchmarks/naming/ring_sweep_population.json` was regenerated, which is the deliberate diff it asks for.
* **D-336.** Preprocessing C (a demoted `carboximidic_acid` whose anchor is in the parent) looped over EVERY atom of the group, not the anchor's neighbours, so an ether oxygen inside the imine's substituent (`=N-C6H4-OMe`) was cut as a second `hydroxy` of the anchor: `No bond between atoms 2 and 8`, and the plan left the aryl unclaimed. 9 names with an ErrorTree in 1,200 forms, all this. Only atoms bonded to the anchor are the group's `=N` and `-OH` now.
* **Refused, not fixed.** `_name_branch_as_prefix` names a branch as an ordinary single-bonded substituent; a guanidinium nitrogen joined to its group by a DOUBLE bond (`NC(=[NH+]CC)N=C(O)Nc1ccccc1`) gained a hydrogen, `1-[anilino(hydroxy)methyl]-2-ethylguanidinium`. It is declined there and the caller refuses the ion.
* **Measured.** 1,200 forms (seeds 21 to 23): 1,166 ok / 17 wrong / 9 naming errors / 5 other tautomer -> 1,187 / 5 / 0 / 5; 2,000 more forms (seeds 31 to 34) 1,987 ok, with 8 wrong that are OPSIN's reading of a charged phosphinite, a sulfonamidate anion and exotic bridgehead tautomers. Vendored and app namer suites below; 5 of 5 mutants killed.
* New `tests/test_namer_round73_tautomers_quinoid_rings_thiadiazole_hydrogen_and_imidic_acid_groups.py`.

## 2026-10-19 -- naming round 72: two labels, hydrazide nitrogens, added-hydrogen ketones, amide anions (D-329 .. D-333)

`iso2.py` (scratch) labels one atom of EACH of two elements per census molecule (c13+n15, c13+o18, o18+s34, d+c13; 300 each), and `iso.py` was run over the ion populations (`r70a`: anion, cation, quaternary, zwitterion, dianion, dication, betaine, quat_dication, trianion, trication; 40 each). The two-label rows failed the way the single-label ones did (no new kind of defect), plus five that were cheap:

* **D-329.** `_located`, the match for "a locant, then the suffix word", did not allow an added hydrogen, `-1(2H)-one`, so the suffix label fell back to the front of the name with the carbon's locant: `(1-18O)pyrrolo[1,2-c]pyrimidin-1(2H)-one`, which OPSIN cannot read. It is now `pyrrolo[1,2-c]pyrimidin-1(2H)-(18O)one`.
* **D-330.** A hydrazide's two nitrogens were both mapped to the anchor carbon's locant 1, so `CC(=O)[15NH]N` and `CC(=O)N[15NH2]` were BOTH `(1-15N)acetohydrazide`: one name for two molecules, and OPSIN reads neither. The book tells N-substituents apart as `N` and `N'`; OPSIN reads `(N-15N)acetohydrazide` and `(N'-15N)acetohydrazide`.
* **D-331.** `_bare_acyl_oxygen_label`: an acylamino prefix is the acid's name with `oic acid` rewritten to `amido`, so the acyl oxygen kept the acid's `-1-(18O)` citation, which OPSIN cannot read in an amido. For a plain chain the bare symbol before the stem is read and means the stem's oxygen. A ring keeps the located spelling (OPSIN reads `(18O)furan-2-carboxamido` as the FURAN's oxygen, a wrong molecule, and the nuclide guard refuses it).
* **D-332.** `_azanide_text` never cited the nitrogen it names: every labelled amide anion was refused. The label goes before the `azanide` (or `azanidyl`), after the groups on it; `azanide` is one nitrogen, so the bracket is unambiguous whatever nitrogens the groups hold.
* **D-333.** `_bare_acyl_label`: the acyl on an amide anion is built from the acid the same way as D-331, and a chain takes the oxygen bare before the stem, after its substituents (`[3-chloro(18O)propanoyl](ethyl)azanide`); the bracket belongs to the component that follows it, so an oxygen in a substituent is not mistaken for it.
* **Measured.** Ion populations 15N 302 -> 343 of 373 and 18O 325 -> 329 of 379; census 15N 323 -> 325 of 356 and 18O 315 -> 320 of 366; 13C and 2H 397 of 400 each, unchanged; two labels 13C+15N 270 -> 273 and 13C+18O 264 -> 266 of 300. Vendored suite 5945 passed, app namer tests 5174 passed; 7 of 7 mutants killed (two dead call sites and a dead condition were found by mutants and removed).
* New `tests/test_namer_round72_hydrazide_nitrogens_added_hydrogen_ketones_and_acyl_oxygens.py`.

## 2026-10-18 -- naming round 71: sulfur, oxygen and nitrogen nuclides in prefixes OPSIN can read (D-325 .. D-328)

Round 70's isotope population (`iso.py`, scratch) with the kinds `s34`, `cl37`, `br81` and `f18` (37Cl 95, 81Br 28 and 18F 48 census rows: every one read back), then `n15` and `o18` again. 34S: 104 ok, 7 charge-changed (a reader dropped the label), 27 refused of 138.

* **D-325.** `(34S)ethylsulfanyl`: OPSIN answers nothing alone and, inside a longer name, reads the unlabelled molecule (the worst case: it parses to another compound). `sulfanyl` is not contracted with its alkyl as `oxy` is, so the ether-prefix path's label goes before the `sulfanyl`: `ethyl(34S)sulfanyl`.
* **D-326.** The FG-prefix path labelled a one-atom prefix only when its name was the table's (`thioxo`), and the thione's own prefix is `sulfanylidene`; `oxo_fallback` never labelled. A `sulfonyl` / `sulfinyl` prefix takes the group's nuclides before the word (`methyl(34S)sulfonyl`; the two `=O` are one position), but a ring bonded through its nitrogen keeps `piperidin-1-yl(34S)sulfonyl` since OPSIN reads no label in `piperidine-1-(34S)sulfonyl`; the compound `sulfamoyl` likewise (`N,N-dimethyl(34S)sulfamoyl`).
* **D-327.** The compound amino prefix of a secondary or tertiary amine FG and of a demoted amide (`amide_n_sub`, bare and compound) never cited its nitrogen. It goes before the `amino`, after the groups on it: `methyl(15N)amino`. `_isotopic_attachment_prefix` takes `within=` so a nitrogen elsewhere in the molecule does not make the symbol ambiguous.
* **D-328.** A retained RING that has the element of a suffix atom (`pyridine-2-carboxamide`) made the bare `(15N)` ambiguous and the label was refused; it now takes the systematic parent's form with the locant of the ring atom the group hangs on, `pyridine-2-(15N)carboxamide` (the anchor of such a group, an unnumbered carbon, is addressed by its numbered neighbour). Not inside a bigger name: that is built by rewriting the ending (`5-methylfuran-2-(18O)carboxamido`), which OPSIN cannot read, and stays refused.
* **Measured.** 15N 287 -> 323 of 356 read back, 18O 289 -> 315 of 366 (the 27 `(2-18O)...dione` names stay unreadable, see KNOWN_LIMITATIONS), 34S 104 -> 134 of 138; 13C and 2H 397 of 400 each, unchanged. Vendored suite 5937 passed, app namer tests 5049 passed; 12 of 12 mutants killed (two survivors were dead code and are gone, and one gate was redundant with another).
* New `tests/test_namer_round71_chalcogen_and_amino_prefix_nuclides_and_suffix_locants.py`.

## 2026-10-18 -- naming round 70: nitrogen and oxygen nuclides in groups, acylamino prefixes and amines (D-322 .. D-324)

The isotope population of round 69 (`iso.py`, a scratch script) with `n15` and `o18` kinds: one labelled N or O per census molecule. 89 of 356 and 103 of 366 were refused, every one a visible refusal.

* **D-322.** Terminal atoms of one element on one neighbour with the same hydrogens (the two oxygens of a nitro group, a sulfonyl, a carboxylate; the nitro's `=O` and `O-` are one resonance form) are one position to a reader, but `_isotopic_group_prefix`, `_isotope_atom_sites` (the systematic suffix branch and the retained branch) counted two. They count once: `(18O)nitro`, `(18O2)nitro` for both, `propane-1-(18O)sulfonamide`, `4-methyl(18O)benzene-1-sulfonamide`. OPSIN calls `(18O)nitrobenzene` ambiguous but reads it, and the two resonance forms are one molecule; the pinned refusal became a name. A sulfonic acid's oxygens (`=O`, `=O`, `OH`) are not alone and stay refused: the first version emitted `(1-18O)propane-1-sulfonic acid`, which OPSIN cannot read.
* **D-323.** The two acylamino returns of `_name_single_fg_substituent` never cited the attachment nitrogen's nuclide (`_isotopic_attachment_prefix` exists for the plain amino prefix). A simple acyl is `(15N)acetamido` / `(15N)benzamido`; a compound acyl is the acylamino spelling `[3-(furan-2-yl)prop-2-enoyl(15N)amino]`, because OPSIN reads neither `(15N)5-methylfuran-2-carboxamido` nor `5-methylfuran-2-(15N)carboxamido` (`_amido_unless_labelled`). The acid the prefix is built from is the amide with its nitrogen turned into the hydroxyl oxygen (`SetAtomicNum(8)`, three places), which kept the nitrogen's isotope: `4-[(O-15O,15N)acetamido]benzoic acid`. Cleared.
* **D-324.** The nitrogen of an `-amine` suffix is the group's anchor, so no locant mapped to it (and a heteroatom anchor outside the numbering, the sulfur of `propane-1-sulfonamide`, likewise). It is addressed by the parent atom it hangs on, and only for atoms the suffix word can cite: `(15N)ethanamine`, `N-ethyl(15N)ethanamine`, `2-phenylethan-1-(15N)amine`, `phenyl(15N)methanamine`.
* **Measured.** 15N 267 -> 287 of 356 read back, 18O 263 -> 289 of 366; 13C 397 and 2H 397 of 400. Ion populations, census (1994 of 2000): no ion that was named became unnamed.
* New `tests/test_namer_round70_heteroatom_nuclides_in_groups_prefixes_and_amines.py`.

## 2026-10-18 -- naming round 69: nuclides on suffix carbons and ureas, and a mirrored benzo ring (D-317 .. D-321)

A new population: `iso.py` (a scratch script, not committed) puts a 13C on one carbon, or a 2H on one C-H, of 500 census molecules and of 40 ions per mode, names them and reads them back through OPSIN with the isotopic InChI key.

* **D-317.** `_isotope_atom_sites` listed the heteroatoms of a suffix group and nothing else, and the carbon of `-carboxamide`, `-carboxylic acid`, `-carbaldehyde` is in no numbered position of the parent, so a nuclide on it was dropped and the guard refused the name (`O=[13C](N)c1ccccc1`, `N[13C](N)=O`). The suffix carbon (the anchor of the only suffix group, when it carries a nuclide) is now cited before the suffix word with no locant: `pyridine-4-(13C)carboxamide`, `cyclohexane-1-(13C)carboxamide`, `4-chlorobenzene-1-(13C)carbaldehyde`. For benzene the label goes into the systematic suffix, `benzene-1-(13C)carboxamide`, and the retained rewrite leaves it alone: `(13C)benzamide` names seven carbons and OPSIN calls it ambiguous (as it does `(13C)benzonitrile`, which stays refused). `_name_n_core_parent` cites a nuclide on a urea, thiourea or guanidine core: `(13C)urea`, `N,N'-diethyl(13C)urea`, `(15N2)urea`, and one nitrogen of two by its locant, `(N-15N)urea`, `N-methyl(N'-15N)urea`, `(N''-15N)guanidine`. A name built from another by rewriting its ending (an acylamino or amido prefix) is not labelled this way (`depth > 0`): `-1-(13C)carboxamido` is unreadable, and it stays a refusal.
* **D-318 (wrong).** The secondary-amide pattern lists the carbon its nitrogen hangs on, so `_atoms_named_by_suffix` handed it to both the heteroatom-site set and the anchor map, and a nuclide on an N-phenyl or N-ethyl group was ALSO cited on the parent: `N-[(1-13C)phenyl](1-13C)acetamide`. Carbons are left out of both.
* **D-319 (wrong molecule, no nuclide in it).** `C1=CCc2ccccc2C1`'s `atom_locants` were mirrored in the benzo ring (5 bonded to 8a). The parent alone is symmetric, so OPSIN chloro-probing could not tell, and `fusion_locants` had already noted the entry; with a substituent on the 2/3 side of a 1,4-dione (`naphthalene-1,4-dione` is named through this entry) the benzo substituents were on the wrong side: **plumbagin `CC1=CC(=O)c2c(O)cccc2C1=O` was `8-hydroxy-2-methylnaphthalene-1,4-dione`**, `5-chloro-2-methyl...` and `8-chloro-2-methyl...` were exchanged. Corrected.
* **D-320 (wrong).** The polyester name leaves the alkyl locants out when the alphanumerical order reproduces the positions. Two alkyls that differ only by a descriptor the order ignores (`ethyl`, `(2-2H)ethyl`) tie, so the order they were written in said nothing: `(2-2H)ethyl ethyl 2-chlorobutanedioate` was read as the deuterium on C1. Such a pair always gets locants.
* **D-321.** `_HYDRO_PREFIXED_STEM` placed a nuclide after `di..deca` hydro prefixes; a steroid is `hexadecahydro`, and the bracket went in front of it, which OPSIN cannot read. Extended to `icosahydro`.
* **Measured.** Neutral 13C 488 -> 495 of 500 (the rest: sulfonamidate and morphinan read-back artifacts, a bis-dioxolo, an amide inside a bigger name), neutral 2H 496 of 500, ions 13C 379 of 387 with refusals 5 -> 1. Dianions, dications, betaines, zwitterions, cations, quaternary, anions, trianions, trications: no ion that was named became unnamed. Census 1994 of 2000.
* New `tests/test_namer_round69_nuclide_on_a_suffix_carbon_and_naphthoquinone_locants.py`.

## 2026-10-18 -- naming round 68: the cation is the parent, and a chain carbanion beside another anion (D-315, D-316)

* **D-316.** P-41 Table 4.1 ranks cations above acids, amides and alcohols. The plan search had that for a RING cation (round 8) and an `-aminium` suffix, and nothing for the rest: an acyclic iminium (`C=[NH+]Ar`), a hydrazinium (`[NH3+]N`), a nitrilium or a phosphonium ring beside a hydroxyl was a prefix (`azaniumylidene`, `azaniumylamino`) on the alcohol's or amide's parent, so the name ended in `-ol` or `-amide`, and a counter-ion word after it was read by OPSIN as an ESTER or acyl halide of that group (27 salts of the round-66 population read back as a different molecule). In the pcg loop a suffix option is skipped when the molecule has an acyclic N+ (a ring P+ or S+ too) that no atom of the suffix group holds, and no anion is present (an anion outranks a cation; a nitro group's O- counts, so D-109u keeps its `azanium`). The no-suffix plan then has the cation as its parent: `[(5-hexyl-2-hydroxyphenyl)methylidene](2-hydroxyphenyl)azanium perchlorate`, `(3,3,3-trichloro-2-hydroxypropanamido)azanium`. One pinned name moved, and reads back: the guanidinium beside a protonated amide, `(4-amino-4-oxidaniumylidenebutyl)(diaminomethylidene)azanium`. An O+ in the rule was tried and dropped: it moved four pinned names and made two hydroquinolinone esters unreadable.
* **D-315.** The ring-anion locants took a ring `[C-]` in round 67; a CHAIN `[C-]` (the enolate of a 2,4-dioxo acid, `CC(=O)[CH-]C(=O)C(=O)[O-]`) was refused with the carbanion in no word of the name. It takes the infix too: `1-oxido-1-oxopentan-3-id-2,4-dione` (OPSIN reads it).
* **Measured.** Dianions 278 of 280 (was 277), dications and quat-dications 1926 of 1930 (unchanged), the other modes unchanged. Salts 14,768 of 14,881 (was 14,736; the ones that read back as a different molecule fell from 31 to 6). Census 1994 of 2000, unchanged.
* New `tests/test_namer_round68_chain_carbanions_and_cation_parents.py`.

## 2026-10-17 -- naming round 67: the open items with a cause (D-309 .. D-314)

Round 66's open lists, read for what had a cause: the dications' ester refusals, the dianions' carbanions, the salts' `...-ol <anion>` readings, and a `NAMING ERROR` inside a neutral name that the isothiourea item had recorded.

* **D-309.** `CCSC(S)=NC`, `CCOC(S)=NC`, `SC(SCc1ccccc1)=NC` (S- or O-alkyl N-alkyl dithiocarbonimidates) were `({[NAMING ERROR: ...leaves heavy atoms [0] unclaimed]}sulfanyl)ethane`: Preprocessing C cites the demoted `=NH` of an imidic or imidothioic acid as `imino` through `oxo_fallback`, which names the bare N, and the N-methyl of `=N-CH3` was claimed by nothing. With an N-substituent the imido is a prefix with its substituents, `(methylimino)`. It is a RETRY: `_name_smiles_bound` names the molecule a second time, with `_IMIDO_RETRY.on`, only when the first name holds an error, because the prefix form would otherwise win names from plans that do not fail (`CN=C(S)NC` is D-101b's `{[(methylamino)(sulfanyl)methylidene]amino}methane`, and stays). Also the oxidanium-parent and salt-fragment instances of the same item.
* **D-310.** `FunctionalClassPath.generate_plans` emits no ester word pair when an ESTER has two cations: the acid half would have to be a cation parent beside an alkyl word, which the guard refuses (`X-yl Y-ium`). The substitutive route cites the ester as an acyloxy / oxo-alkoxy prefix (`...-1-oxoethoxy}...`), which OPSIN reads. A carbamate keeps its ester word (the first version took it too and wrote `[...]methanecarbamate`; a population run found it).
* **D-311.** The `-aminium` suffix was skipped for any molecule with a negative atom, so the nitro group's O- sent `COc1ccc([N+](=O)[O-])cc1C[NH2+]CCO` to `...azaniumyl}ethan-1-ol` and a salt's anion word read as an ester. A charge-separated nitro or N-oxide is not an anion there when a hydroxyl is present (D-109u pins `[2-(4-nitrophenyl)ethyl]azanium chloride`, which has none; the first version, without the hydroxyl test, moved seven pinned names).
* **D-312.** The ring-anion locants (`ring_n_minus_locants`) took ring N- only. A ring CARBANION (`[C-]`, `[c-]`) is cited the same way when it is not the parent's own anion: `...-4,5-dioxoazolidin-3-id-2-yl]benzen-1-olate`, `5-butyl-1-methyl-4,6-dioxo-1,3-diazin-5-id-2-thiolate`. The lone carbanion is still the stabilised-carbanion classifier's `...-3-ide`. One ring anion only, as for N.
* **D-313.** `_ANION_WORD_END` and the population tool's `_ANION_WORD` read `\d-id-`; a spiro name's `-2'-id-` has a prime. Now `\d'*-id-`: six spiro azolides beside a carboxylate or an ammonium were refused with both charges in the name.
* **D-314.** A zwitterion fragment beside `[Na+].[Cl-]` was asked for the anion form only if a suffix site could carry it, so a carved alkoxide fell to STANDALONE and the carbamate came out `[...-9-yl]methanecarbamate` (a wrong molecule, found by the salt population). `_choose_salt_fragment_form` adds `_carved_acid_anion_sites`, as the top-level promotion has since round 8.
* **Measured.** Dianions 277 of 280 (was 268), dications 1926 of 1930 (was 1913), quat-dications 1926 of 1930 (was 1913), betaines 1521 of 1523 (was 1518), zwitterions 1521 of 1523 (was 1519), cations 3141 of 3148, quaternary 3142 of 3148, anions 1399 of 1399, trianions 27 of 27, trications 630 of 631. Salts (14,881: every census ion with counter-ions) 14,736 (was 14,697); refusals 43 -> 6. Atom order: 567 ions in 5 random spellings each, 5 structures name differently (the Kekule form of a von Baeyer double-bond list, a spiro numbering tie), none a wrong molecule. Census 1994 of 2000, unchanged.
* New `tests/test_namer_round67_imido_prefix_ester_cations_ring_carbanions.py`.

## 2026-10-17 -- naming round 66: salts keep the charge of their organic ion (D-306 .. D-308)

Round 65 left the ion populations nearly exhausted, so this round built a new one: `tools/naming_ion_populations.py`'s single-site ions (anion, cation, quaternary) and its pairs (dianion, dication, quat_dication, betaine, zwitterion) each drawn WITH counter-ions (Na+, K+, NH4+, methylammonium, Ca2+; Cl-, Br-, acetate, mesylate, perchlorate, oxalate) and named as a salt: 14,881 salts, 14,697 read back after this round.

* **D-306.** `_check_charge_named` leaves a salt alone (two fragments), and `_choose_salt_fragment_form` asks a fragment for the cation or anion form only where a suffix-eligible group can carry the charge, so a protonated amidine (`NC(S)=[NH+]C(=NOCc1ccccc1)c1ccccc1`) or nitrile (`C#[NH+]`) beside `[Cl-]` fell to the neutral STANDALONE form and the counter-ion's word hid the lost charge: `hexadecyl 4-(azanylidynemethyl)benzoate chloride`. The same cation alone was named correctly. `_salt_fragment_with_its_charge` runs the guard on every charged fragment of more than one heavy atom (a zwitterion drawn beside `[Na+].[Cl-]` too, by polarity) and, when it fails, names the fragment the way it is named alone, which raises when that cannot keep the charge either.
* **D-307.** `_render_amine_anion` needs the `-aminide` suffix, and an anilide beside a group senior to the amine (a ketone, an amide, a ring amine) has none; `detect` then refused ("render_failed") and the plan search never saw the molecule. For an amine anion it now returns unclaimed instead, and the plan search cites the anion as the `azanidyl` prefix (`1-[(3-methylphenyl)azanidyl]propan-2-one`), which the guard accepts and OPSIN reads. 135 refusals of the salt population, and the same shape alone.
* **D-308.** `_ion_word_weight` counted `oxalate` as one anion word for two carboxylates, so `[O-]C(=O)C(=O)[O-]` was refused alone and, once D-306 judged a salt's fragment, `disodium oxalate` would have been too. The word counts for two.
* **Not defects (OPSIN, recorded so they are not rediscovered).** `...sulfonamidate` reads back as the NEUTRAL sulfonamide plus a bare metal atom, so every sulfonamide salt reads `charge_changed` (the single-anion mode compares neutral connectivity for the same reason); a cation named with a suffix-only charge-free ending (`...benzen-1-ol perchlorate`, `...phosphinic acid bromide`, `...propan-1-ol acetate`) is read as an ESTER or ACYL HALIDE of the alcohol or acid, because its charge is in a prefix (`azaniumylidene`, `oxidaniumylidene`) and the name has no `-ium` word; 27 salts, not changed.
* **Measured.** Salts 13,889 of 14,881 after the first two fixes (the all-modes run), 14,697 after the zwitterion check and the oxalate weight (the 184 left: 58 sulfonamidate readings, 27 ester or acyl-halide readings, 36 OPSIN-unreadable `oxidaniumyl` names, 43 refusals (30 dications of two onium sites, 12 dianions with a carbanion, 1 nitrile), 6 isothiourea tautomer-branch naming errors, and 14 of the morphinan, purinone and bis-dioxolo kinds earlier rounds recorded). Anions 1399 of 1399, dianions 268 of 280, betaines 1518 of 1523, zwitterions 1519 of 1523: none moved.
* New `tests/test_namer_round66_a_salt_fragment_keeps_its_charge.py`.

## 2026-10-17 -- naming round 65: a ring-cation acyl on an amide anion (D-305)

Round 64's open list: 52 of the betaine population's 56 refusals and 52 of the zwitterion's 55 were one shape, an amide anion `C(=O)[N-]` whose acyl group is a cationic ring (a pyridinium, a pyrazolium, a thiazolium).

* **D-305.** `_acyl_prefix_via_acid` (the acyl group on an anionic nitrogen, named by cutting the nitrogen off, putting an -OH where it was and naming the acid) named the acid with `OutputForm.STANDALONE`, which neutralised a ring cation: `methyl(pyridine-4-carbonyl)azanide`, refused by the guard. It names the acid with `_standalone_or_cation` (`4-carboxypyridin-1-ium`) and turns that into `pyridin-1-ium-4-carbonyl` (`3-bromopyridin-1-ium-5-carbonyl`); a name ending `aminium` is a suffix, not a ring cation, and keeps the `[(azaniumyl...)(oxo)methyl]` form it had. D-271's thiazolium sulfonamide is now `carbamoyl[4-(1,3-thiazol-3-ium-2-yl)phenylsulfonyl]azanide` (the acid is named as a cation too; OPSIN reads it back).
* **Measured.** Betaine 1518 of 1523 (was 1465), zwitterion 1519 of 1523 (was 1466); dianion 268 of 280, anions 1264 of 1399, cations, quaternary, dication, quat_dication, trianion and trication as before. See the verification lines at the end of this round.
* New `tests/test_namer_round65_cationic_acyl_on_an_amide_anion.py`.

## 2026-10-17 -- naming round 64: a lactam anion beside an acid anion (D-303, D-304)

Round 63's open list: the dianion, betaine and zwitterion populations still refused ions with a lactam's ring `[N-]` beside a carboxylate (34 of 280 dianions; `lactam` was in 12 of 17 refusals of that kind).

* **D-303.** `CC1CC(=O)[N-]C1C(=O)[O-]` was refused (the acid anion is the parent and the lactam `[N-]` was left out of the name, which the guard caught). The ring-anion locants of `SubstitutivePath.execute` took an aromatic `[n-]` and, since round 60, a lactam as a SUBSTITUENT; they now take a non-aromatic ring `[N-]` in every output form when it is the ONE ring anion of the parent. The assembler already put the infix before a suffix (`1H-indol-1-id-5-ol`): `3-methyl-5-oxopyrrolidin-1-id-2-carboxylate`, `(2-oxo-2,3-dihydro-1H-indol-1-id-3-yl)acetate`. Two ring anions with a lactam (`...-5-carbonitrile-1',2-diide`, `...-6-one-4,5-diide`) came out unparsable, a worse failure than the refusal: the lactam is left out then and the guard refuses.
* **D-304.** Round 63's stabilised-carbanion classifier returns when a CATION is bonded to the carbanion (a diazo carbon, `[CH-][N+]#N`, is an ylide); a nitro group's `N+` is bonded to the carbon of a nitro carbon acid and is charge-separated and neutral, so `COc1ccccc1Nc1nc(=O)[c-]([N+](=O)[O-])c(=O)[nH]1` was refused. The test skips the charge-separated atoms.
* **Measured.** Dianion 268 of 280 (was 246), betaine 1465 of 1523 (was 1436), zwitterion 1466 of 1523 (was 1437); anions 1264 of 1399 as before, cations, quaternary, dication, quat_dication, trianion and trication unchanged. See the verification lines at the end of this round.
* New `tests/test_namer_round64_lactam_anion_beside_an_acid_anion.py`.

## 2026-10-17 -- naming round 63: a guanidinium, an amidinium or a carbon acid beside another charge (D-299 .. D-302)

Round 62's open list: about 50 ions per pair mode still refused. Three classifiers (`_classify_guanidinium`, `_classify_amidinium`, `_classify_stabilised_carbanion`) claim a motif when it is the molecule's only charge, and detection refuses ('partial_claim') when a classification leaves a charged atom uncovered, so a second charge refused the whole molecule.

* **D-299.** `NC(N)=[NH+]CCC[C@H]([NH3+])C(=O)[O-]` (arginine as the zwitterion) was refused. The guanidinium classifier declines beside any other charge; the plan search names the group `(diaminomethylidene)azaniumyl`, which OPSIN reads: `(2S)-2-azaniumyl-5-[(diaminomethylidene)azaniumyl]pentanoate`.
* **D-300.** The amidinium declines the same way (its round-43 lone carboxylate stays its own case); its `=[NH2+]` was a neutral `imino` once the plan search named it, and the unclaimed-`=X` fallback now says `azaniumylidene`: `{2-[amino(azaniumylidene)methyl]phenyl}methanaminium`.
* **D-301.** `_name_ring_nitrogen_acyl_substituent` took an O-PROTONATED carbonyl for the neutral one (`pyrrolidine-1-carbonyl`), losing the cation: it requires a neutral oxygen, and the protonated amide is `(oxidaniumylidene)(pyrrolidin-1-yl)methyl`.
* **D-302.** A carbon acid beside a cation was refused in every case (`CC(=O)[CH-]C(=O)CC[NH3+]`, 57 of 57 in the zwitterion population): the stabilised-carbanion classifier needed the carbanion to be the only charge. The cations ride along in the claim and are cited as prefixes: `6-azaniumyl-2,4-dioxohexan-3-ide`. A second ANION is not this classifier's.
* **Measured.** Dications 1913 of 1930 (was 1877), quat_dication 1913 (was 1892), trication 629 of 631 (was 602), betaine 1436 of 1523 (was 1376), zwitterion 1437 of 1523 (was 1365); anions, cations, quaternary, dianion and trianion unchanged. Every named ion reads back to itself apart from the artifacts of round 60.
* New `tests/test_namer_round63_guanidinium_amidinium_and_carbon_acids_beside_other_charges.py`.

## 2026-10-16 -- naming round 62: a protonated carbonyl beside another cation is cited as what it is (D-295 .. D-298)

Round 61's open list named the biggest class of visible failures: an O- or S-protonated carbonyl beside a second cation. Of 1930 dications (round 61's tree), 786 were refused (amide 458 of 841, ester 306 of 355, acid 100 of 118, ketone 137 of 257); of 1523 betaines 212.

* **D-295.** The engine cited the carbonyl with the NEUTRAL prefix (`oxo`, `carbamoyl`, `carboxy`) and the guard refused the name for the cation it had lost. Round 59's restore swapped the single `oxo` of the NAME for `oxidaniumylidene`, which needed exactly one `oxo` and gave the charge to the wrong carbonyl when there were two (D-294). The unclaimed-`=O` fallback now names the atom it has, in the plan and when it executes: `=[OH+]` is `oxidaniumylidene`, `=[SH+]` `sulfaniumylidene`, where it stands.
* **D-296.** An O-protonated ester carbonyl was detected as `alkoxycarbonyl` (the neutral group's prefix, the charge ignored): it is `[ethoxy(oxidaniumylidene)methyl]`.
* **D-297.** `oxidaniumylidene` is a simple ylidene, so beside another prefix on a one-carbon parent it was unbracketed: `(2-azanidylphenyl)oxidaniumylidenemethanamine`, which OPSIN reads as another molecule. It is bracketed there in any output form.
* **D-298.** A multiplied one, `2,3-dioxidaniumylidene`, is unreadable: `2,3-bis(oxidaniumylidene)`.
* **Measured.** Dications 1877 of 1930 clean (was 1143; 51 refused, one unparsable, one `NAMING ERROR`: the isothiourea tautomer of round 60), quat_dication 1892 of 1930 (was 1447), trication 602 of 631 (was 277), betaine 1376 of 1523 (was 1309), zwitterion 1365 of 1523 (was 1119); anions, cations, quaternary, dianion and trianion unchanged. Three earlier expectations moved (a three-cation molecule that was refused is named; the D-290 spiro name has `2'-oxidaniumylidenespiro`; D-294's ester beside a ketone is named). See the verification lines at the end of this round.
* New `tests/test_namer_round62_protonated_carbonyls_beside_cations.py`.

## 2026-10-16 -- naming round 61: the azanidyl prefix and four ways the charge guard let a charge go (D-291 .. D-294)

The pair populations (`zwitterion`, `dianion`, `betaine`, `dication`, `quat_dication`, `trianion`, `trication`) take the kinds round 60 added to the single-charge modes: an alcohol and an anilide NH as acids, the oxygens of an ester, an acid, an aldehyde, an ether and an alcohol as bases (dianion grew from 173 to 280 ions, dication from 866 to 1930).

* **D-291.** An aryl `[NH-]` beside another anion was cited as `azanide` (`4-azanidebenzoate`, refused; in a longer name unreadable, 28 ions): `azanide` is the parent hydride anion, and the prefix OPSIN reads is `azanidyl`: `4-azanidylbenzoate`.
* **D-292 (a silent lost anion).** The guard dropped every group of bonded + and - atoms as a neutral dipole. A nitro carbon acid's `[c-][N+](=O)[O-]` is -1 over three atoms: one anion. `...-5-nitro-1,3-diazine-4,6-dione` stood for it beside an oxonium, the anion gone. A group whose charges do not cancel now counts as one centre of its net polarity.
* **D-293 (silent lost charges).** The multiplier pattern of the count test took `pentanamido` (`penta` + `nam` + `ido`), `dihydropyrido`, `pyridinium` (`di` + `n` + `ium`) and `dichloroacetate` (as a cation word) for multiplied ion words, so a name citing ONE cation counted five, and an O-protonated acid or ester beside another cation passed with its charge gone. `pyrido` was also an `oxido` anion word, so a lost ring anion passed. A multiplied word now counts for its own polarity, alkane stems and `pyri`-`dinium` are not multipliers, and `pyrido` is no `oxido`.
* **D-294.** `_restore_dropped_oxidanium` handed the `oxidaniumylidene` to the only `oxo` in the name; with an O-protonated ESTER (cited as `ethoxycarbonyl`, without an `oxo`) and a ketone, the ketone got the charge: the same neutral compound with a different cation. With another neutral C=O in the molecule it now leaves the name to the guard, which refuses it.
* **Measured.** Cations and quaternary 3148 each: 3139 and 3141 clean, the rest the same artifacts as round 60; anions 1399 (1264 clean, 135 refused); dianion 246 of 280 (34 refused); trianion 27 of 27; the pair modes with the new kinds have no silent wrong name left, only refusals and the artifacts of round 60. Census 1994 of 2000 exact. Vendored suite 5881 passed. 9 of 9 mutants killed.
* New `tests/test_namer_round61_azanidyl_prefix_and_guard_word_counts.py`.

## 2026-10-16 -- naming round 60: O-alkylated carbonyls, fused azolides, the acid anion as parent, a diacid that lost its acid (D-285 .. D-290)

Round 59's open list, and populations widened once more: `tools/naming_ion_populations.py` deprotonates an alcohol and an anilide NH, protonates the oxygen of an ester, an acid, an aldehyde, an ether and an alcohol (a sulfone has two oxygens, so no single site). Baseline on round 59's tree for the pair modes: betaine 21 embedded `NAMING ERROR`s, dianion one.

* **D-285.** `CC(NCC(=O)[O-])=[O+]C` was `({[NAMING ERROR: ... leaves heavy atoms [1] unclaimed]}amino)acetate`: the unclaimed-`=O` fallback claimed the O-alkylated oxygen as a bare `oxo` and left its methyl, and the carved group had no oxidanium parent because the perception gate counted the fragment's valence without the radical electrons that stand for the cut bond. Now `{[1-(methyloxidaniumylidene)ethyl]amino}acetate`; `S+` and `Se+` the same (`methylsulfaniumylidene`, `methylselaniumylidene`). An S-protonated thioamide beside another charge kept a neutral `thioxo`: `sulfaniumylidene`. The restore must not take `oxolan-2-yl` for the `oxo` prefix.
* **D-286.** A fused azolide as a SUBSTITUENT had no plan: the fused-ring namer neutralised only +1 atoms. An azolide (and a lactam anion in a ring) is its neutral ring less a hydrogen; the `-N-id-` infix of round 59 is placed from the real molecule: `[4-(2,4-dihydropyrano[2,3-c]pyrazol-2-id-4-yl)phenyl]azanium`, `{2-[(3-oxo-3,4-dihydro-2H-1,4-benzothiazin-4-id-2-yl)methyl]phenyl}acetate`.
* **D-287.** `[O-]C(=O)c1ccc(-c2cc[n-]n2)cc1` was `3-{4-[oxido(oxo)methyl]phenyl}-1H-pyrazol-1-ide`, the right molecule on the junior anion's parent (it also hid a sulfonamidate that OPSIN reads as neutral). `acid_anion_route` now takes an azolide or an amide's `[N-]` beside the acid anion like a cation: `4-(1H-pyrazol-1-id-3-yl)benzoate`, `4-(acetylazanidyl)benzoate`, `4-[(carbamoylazanidyl)sulfonyl]benzoate`. Four earlier expectations (rounds 56, 57, 59) changed to these.
* **D-288.** `[NH-]c1ccc([N+](=O)[O-])cc1` was `1-azanide-4-nitrobenzene` (the nitro counted as a second charge, so nothing claimed it): `4-nitrobenzen-1-aminide`. An anilide beside a dimethylaniline would put the `-aminide` on the wrong nitrogen and is refused.
* **D-289 (silent wrong molecule).** A monoamide of a diacid on an aminium or oxidanium parent: `C[NH2+]c1ccc(NC(=O)c2ccccc2C(=O)O)cc1` was `4-(benzene-1,2-dicarboxamido)-N-methylanilinium`, the carboxylic acid gone. The acid-based acylamino name is not used when the acyl carries a second carboxylic acid: `4-{[(2-carboxyphenyl)(oxo)methyl]amino}-N-methylanilinium`.
* **D-290 (wrong stereo).** The one-descriptor correction of round 59 is replaced by stamping the whole molecule's CIP codes on the carved fragment (`_ParentCIPCode`, carried through the atom map), so a branch of any number of centres is right, and a centre already cited is replaced and never cited twice. RDKit labels a deprotonated aromatic `[n-]` with other duplicate atoms than the neutral azole (and OPSIN); a spiro centre beside a pyrazolide read `S` where the neutral compound and OPSIN say `R`: the labels of a molecule with an aromatic `[n-]` are those of its `[nH]` view.
* **Measured.** Anions 1399 candidates (new kinds included): 1260 clean, 135 refused, 4 unparsable (an N-amino azole's `[NH-]`); cations and quaternary 3148: 3139 and 3141 clean, the rest the morphinan and bis([1,3]dioxolo)pyran OPSIN artifacts, the odd purinone tautomer, an isothiourea tautomer branch (`NAMING ERROR`, two ions) and a hydro-quinolinone OPSIN cannot read (two); betaine 629 of 725 clean (95 refused, the morphinan artifact), dianion 156 of 173 (17 refused), zwitterion 557 of 725 (166 refused, the morphinan artifact and an O-protonated lactam with an azolide), dication 659 of 866, quat_dication 713 of 866, trianion 15 of 15, trication 88 of 160 (the rest refused). Census 1994 of 2000 exact, unchanged (the six others are OPSIN artifacts). Vendored suite 5879 passed, 16 of 16 mutants killed.
* New `tests/test_namer_round60_oalkylated_carbonyls_fused_azolides_and_acid_anions.py`.

## 2026-10-16 -- naming round 59: azolide anions, onium prefixes, and a guard that counted words for charges (D-278 .. D-284)

Round 58's open list asked for sites the populations had never tried. `tools/naming_ion_populations.py` now deprotonates a selenol, a boronic and a phosphinic acid, protonates an N-oxide oxygen (not a nitro group), a selenoether and a phosphine oxide, makes TRIANIONS and TRICATIONS, and the pair modes take the acid and base kinds of rounds 51-58 as well. Two sites within two bonds of each other are one group drawn charge-separated (an azole's `[n-]` beside its own `[nH+]`), so those pairs are not made. Baseline on master with the new kinds: anions 1122 of 1123 (one refused), cations 2368 of 2386 (12 refused, 5 charge-changed, 1 wrong); the widened pair modes gave 40 wrong or charge-changed ions, and three charges 7 charge-changed ones.

* **D-278 (silent wrong molecule).** `O=C([O-])Cc1ccn[n-]1` was `1-(carboxylatomethyl)-1H-pyrazol-2-ide`, the substituent on a nitrogen. `_filter_indicated_h_numberings` accepted the atom at the `1H` locant only if it had an H or an outside substituent, and a deprotonated `[n-]` has neither, so only the numberings that put a ring CARBON at locant 1 survived. The `[n-]` is the NH slot. Separately, a ring anion as a SUBSTITUENT had no infix (the assembler said so in a comment) and the group was written neutral and on the wrong atom beside a cation: it is `-N-id-`, `trimethyl(1H-pyrazol-1-id-5-yl)ammonium`, and before a suffix `1H-indol-1-id-5-ol` (the trailing `1H-indol-5-ol-1-ide` OPSIN cannot read; the imidazole carboxamide `...-carboxamid-1-ide` neither). A carbanion with a ring HETERO neighbour (an oxazolone) is claimed by the stabilised-carbanion classifier (round 58 left it refused).
* **D-279.** `C[SH+]CC(=O)[O-]` took the sulfonium for an ETHER prefix (`methylsulfanyl`) and lost the charge: a charged chalcogen is no ether. It is `(methylsulfaniumyl)acetate`; `C[OH+]CC(=O)[O-]` is `(methyloxidaniumyl)acetate`.
* **D-280 (silent wrong charge).** (a) The guard grouped charged atoms on one carbon as ONE centre, so a sulfonium and a pyridinium nitrogen on a carbon were one word: centres are grouped per element. (b) `hexanoate` is `hexa` + `noate` to the multiplier pattern, which switched the count test off for the whole name; so did `tetraazatetracyclo` (`tetra` + `az` + `ate`): an ion word must end its word, and an alkane stem is no multiplier. (c) A multiplied word switched the count off ENTIRELY, so a third cation of a `...-1,4-diium` was never missed: a multiplied word now counts its multiplier. (d) An ester's final `ate` was an anion word in a zwitterion (the polarity test now strips it too; a leading digit or capital, `2-methoxy-4-...phenyl benzoate`, is ester-shaped). (e) One ion named by two words that end in a cation (`ethyl {...}(methyl)oxidanium`, an ester's alkyl in front of a cation parent) is refused.
* **D-281.** A ring cation beside an anion that is only a prefix (`Cc1ccc(N(C)[O-])c[nH+]1`) stayed STANDALONE, so the ring lost its `-ium` (the promotion to CATION needed a net charge above zero). A nitro group and an N-oxide are charge-separated and keep their form.
* **D-282.** An O-protonated carbonyl beside another charge had a neutral `oxo` (`{[(oxo)(phenylmethoxy)methyl]amino}`): it is `oxidaniumylidene`, which OPSIN reads, restored only when the name is short of cation words and `oxo` occurs once.
* **D-283.** A cation parent hydride (sulfanium) was offered the suffix of a group beside it (`dimethylsulfaniumcarboximidamide`, refused by round 58's guard); it now takes no carbon-anchored suffix that stands beside it: `[(imino)(methylamino)methyl](methyl)sulfanium`, `cyano(methyl)sulfanium`.
* **D-284 (silent wrong stereo).** A branch carved out beside an anionic nitrogen was labelled without the atom it was cut from: `C[NH+](C)[C@@H](C[N-]C(=O)C)c1ccccc1` cited `(2S)` for a centre that is R. The branch's lone centre now takes the label it has in the whole molecule.
* **Measured.** Anions 1123 of 1123, cations 2262 of 2267, quaternary 2261 of 2267, trianions 9 of 15 (the rest refused), trications 86 of 160 (the rest refused); the zwitterion, dianion, dication, betaine and quat_dication populations have no silent wrong name left but the morphinan stereo artifact (OPSIN adds the stereo a `morphinan` name implies) and the bis([1,3]dioxolo)pyran OPSIN limit. Census 1994 of 2000 exact (was 1993; the `N([O-])O` beside a pyridinium row is exact now), the six others are three stereo artifacts and three sulfonamidate OPSIN artifacts.
* New `tests/test_namer_round59_azolides_onium_prefixes_and_guard.py`; the tool tests gain five.

## 2026-10-16 -- naming round 58: carbon acids, an ester taken for an anion, a cation fused with a suffix (D-275, D-276, D-277)

Round 57's open list asked for sites the populations had never tried. `tools/naming_ion_populations.py` now deprotonates a 1,3-dicarbonyl CH and a malononitrile CH (the first CARBON acids), an enol, a
hydroxylamine, a sultam and a carbamate, and protonates or methylates a thioether sulfur. Baseline on master (with the new kinds added): anions 1121 ions, the new kinds giving 3 refused and 3 wrong carbon-acid anions
(two of the wrong ones the neutral ester of the guard's loophole) and cations 2245 ions with 3 wrong thioether cations.

* **D-275.** A carbanion stabilised by acceptors on a ring: the simple-carbon classifier refuses an aromatic charged atom (RDKit calls the barbiturate carbon aromatic) and a ring with a double bond (the fused
  indane-1,3-dione), and the aromatic-ring-anion classifier needs the neutral ring to stay aromatic. Nothing claimed it; the plan search neutralised the carbon. `_classify_stabilised_carbanion` takes a lone
  carbanion whose neighbours are all carbons and one of them carries a carbonyl, thiocarbonyl or nitrile; the renderer kekulises the molecule first, then uses the carbon `-ide` renderer:
  `2,4,6-trioxo-1,3-diazinan-5-ide`, `5-butyl-1-methyl-4,6-dioxo-2-sulfanyl-1,4,5,6-tetrahydropyrimidin-5-ide` (OPSIN reads both).
* **D-276 (silent wrong molecule).** The guard's anion word `ate` matched an ESTER's name: `COC(=O)CCC(=O)[c-]1nc(...)oc1=O` was `methyl 4-oxo-4-(5-oxo-2-phenyl-1,3-oxazol-4-yl)butanoate`, the neutral compound,
  and it passed. A name that opens with an alkyl or aryl word and a space and ends in `ate` is an ester's; its final `ate` is no longer an anion word. The carbanion beside a ring nitrogen is refused, visibly.
* **D-277.** `CNC(=N)[SH+]C` was `dimethylsulfaniumcarboximidamide`: a cation parent hydride fused with a suffix, never a name, and a different molecule. The guard refuses a cation hydride (`sulfanium`, `azanium`,
  `oxidanium`...) immediately followed by `carbox`/`carbon`. Separately, `_classify_sulfoxide_cation` now takes a sulfur with ONE carbon (the other group a sulfonyl or phosphoryl, a thiosulfonate S-oxide):
  `(benzenesulfonyl)(methoxy)(phenyl)sulfanium`.
* **Measured.** Anions 1118 of 1121 (three visible refusals: the oxazolone carbanion, a nitro-pyrimidinone carbanion, the `N([O-])O` census molecule), cations 2227 of 2245 and quaternary 2237 of 2245 (the rest visible refusals, OPSIN limits and the odd purinone tautomer), every multi-charge population 100%. Census 1993 exact, unchanged. Vendored suite and known-defects file 7510 passed. App naming group passed after the round 46 refusal test took a new example. 7 of 8 live mutants killed by the file's tests (the eighth's pattern did not match the mutation script; a unit test covers it).
* New `tests/test_namer_round58_carbon_acids_and_sulfonium_guard.py` (26 tests); three tool tests in `tests/test_naming_ion_populations.py`. D-275 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-15 -- naming round 57: the multi-charge ions that were still refused (D-271 .. D-274)

Round 56's open list: a protonated amidoxime beside a second cation (refused), the acylsulfonamide anion beside an azolium (refused since round 55), a sulfonamide anion with a second anion as the parent,
and O-acylated isothioureas. Two population modes were added first to look for more: `betaine` (a base N-methylated, an acid deprotonated; 89 ions) and `quat_dication` (171). They found nothing new
that was not already on the list: betaines 88 of 89 ok, quaternary dications 169 of 171.

* **D-271.** With a CATION in the molecule the plan search takes the cation as parent and writes the acylsulfonamide as the charge-free `N-carbamoylsulfamoyl` prefix. The anion is the senior class, so
  `_acyl_like_neighbour` treats a sulfonyl as acyl-like for the azanide when a cation is present (it required a second nitrogen on the sulfur): `carbamoyl[4-(1,3-thiazol-3-ium-2-yl)benzene-1-sulfonyl]azanide`.
* **D-272.** When another ANION is the parent, a sulfonamide whose own nitrogen is the anion was still the bare `sulfamoyl` prefix (no charge): the guard refused it. The compound-sulfamoyl branch of
  `SubstitutivePath.execute` now sends such a nitrogen to the recursive carve, and the engine's substituent naming has a block for a sulfonyl or an acyl group whose nitrogen is `[N-]`:
  `(R-azanidyl)sulfonyl`, `(R-azanidyl)carbonyl` (`_azanide_text` takes a `skip` set for the attachment atom). OPSIN reads both (measured).
* **D-273.** `_restore_dropped_oximium`: a single protonated oxime centre written with a neutral `hydroxyimino` has its prefix changed to `hydroxyazaniumylidene` (the same repair as round 54's oximate).
* **D-274.** `_classify_oxonium_urea` also claims an O+=C with ONE heteroatom on the carbon when an N-C(=O/S)-N urea group is elsewhere in the molecule (the urea group took the carbon).
* **Measured.** See the pull request for the census, vendored suite and app group on the final tree. 6 of 6 live mutants killed. Four non-exact census rows were re-read (listed in the pull request).
* New `tests/test_namer_round57_acyl_azanide_prefixes_and_second_cations.py` (31 tests); three tool tests in `tests/test_naming_ion_populations.py`. D-271 to D-273 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-15 -- naming round 56: two anions in one molecule, the guard that counts centres, a ketone ring cation with a cation suffix (D-268, D-269, D-270)

Round 55's open list: the dianion population's naming errors, a protonated amidoxime beside a second cation (charge lost), and the unreadable cationic ketone ring with an aminium suffix.

* **D-268.** A molecule with two anions names one as the parent and cites the other as a PREFIX. For a carboxylate, a phenolate and a thiolate that is `oxido(oxo)methyl`, `oxido`, `sulfido`; for an anionic
  nitrogen there was no prefix: the carved `CC(=O)[N-]` fragment went through the standalone anion route and failed (`NAMING ERROR: ... [NH-]`), and a sulfonamide anion beside a phenolate was named
  `[N-(4-oxidophenyl)sulfamoyl]methane` -- the sulfonamide charge DROPPED, with one `oxido` left in the name to satisfy the guard. OPSIN reads `azanidyl` (measured: `4-(acetylazanidyl)benzen-1-olate` ->
  the dianion); `_azanide_text` now composes the groups on the nitrogen for both the parent (`acetyl(methyl)azanide`, two groups) and the prefix (`acetylazanidyl`, one group), and the engine's substituent
  naming has a block for the carved `[NH-]` fragment (the carve gives the open valence its hydrogen).
* **D-269.** `_check_charge_named` asked whether the name had A word of each polarity, so D-268's name passed with one `oxido` for two anions. When the name never multiplies an ion word
  (`_MULTIPLIED_ION_WORD`: `dioxido`, `bis(azaniumyl)`, `1,4-diium`, `dioate`, `diolate`...) it needs at least as many anion words (or cation words) as there are charged centres of that polarity
  (charge-separated neutral groups and bonded +/- pairs excluded, as round 55). `azanidyl` joined the anion words. A name that multiplies a word is not judged by count, which is conservative.
* **D-270.** A curated ring whose name carries its ketone, cationic, with a cation SUFFIX: `...pyrimidin-4-on-1-ium-2-aminium`, unreadable. The cation suffix outranks the ketone, which becomes the prefix
  `oxo`: `7-methyl-4-oxo-4H-pyrido[1,2-a]pyrimidin-1-ium-2-aminium` (read back).
* **Measured.** Populations: anions 1046 of 1046, dianions 18 of 18, dications 169 of 171 (two protonated amidoximes refused, visibly, by D-269), zwitterions 88 of 89 (the one refusal is D-267's),
  cations 2061 of 2081 and quaternary 2074 of 2081 (the rest visible refusals or OPSIN limits). Census, vendored suite and app naming group are in the final numbers of the pull request. 7 of 7 live mutants killed.
* New `tests/test_namer_round56_two_anions_and_ion_counts.py` (26 tests). D-268 and D-270 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-15 -- naming round 55: three multi-charge ion populations, and the charge guard learns polarity (D-265, D-266, D-267)

Every earlier population changed ONE site, so an ion with two charges was reachable only by accident, and the charge guard judged the NET charge, which a zwitterion does not have. `tools/naming_ion_populations.py`
gained `zwitterion` (one acid site deprotonated and one base site protonated: 89 ions), `dianion` (two different acid sites: 18) and `dication` (two base sites: 171).

* **D-267.** The first run: an acylsulfonamide anion beside a thiazolium (`...S(=O)(=O)[N-]C(N)=O...[nH+]...`) was named `4-(N-carbamoylsulfamoyl)phenyl...thiazol-3-ium`: the anion dropped, the cation kept, a net-neutral
  name for a net-neutral molecule, so nothing judged it. `_check_charge_named` asks each polarity of a molecule that has both: the anion needs an anion word and the cation a cation word. A positive and a negative on
  BONDED atoms are one neutral dipole (an isocyanide, `Cl(=O)O` drawn `[Cl+]([O-])O`, an ylide) and count for neither: the first version of this guard did not know that and failed 33 vendored tests.
* **D-265.** `_ring_nitrogen_acyl` turns a ring group's name `...-1-yl` into `...e-1-carbonyl` ("piperidine-1-carbonyl"); for a cationic ring the stem ends in the `ium` infix, and the `e` landed after it:
  `4-methylpiperazin-4-iume-1-carbonyl`, which OPSIN cannot read. No `e` follows `ium`.
* **D-266.** A curated ring whose name carries its ketone (`pyrido[1,2-a]pyrimidin-4-on`), cationic, as a SUBSTITUENT: the assembly appended `-1-ium` after the ketone, `...-4-on-1-ium-2-yl`. The standalone
  form has it before (`...-1-ium-4-one`); the substituent form takes the same order.
* The population tool's dianion verdict allows for OPSIN reading `-sulfonamidate` as the neutral sulfonamide (each one in a name accounts for one charge the read-back lacks).
* **Measured.** The zwitterion population: 88 of 89 ok, the one refusal the D-267 case. Dianions and dications are listed in the final numbers below. Every new name reads back through OPSIN. 5 of 6 live mutants
  killed; the survivor (two kinds hitting the same atom) is dead protective code for today's site lists, which no pair overlaps.
* New `tests/test_namer_round55_multi_charge_ions.py`; seven tests for the new modes in `tests/test_naming_ion_populations.py`. D-265 and D-266 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-15 -- naming round 54: the limitations rounds 50 to 53 left open (D-256 .. D-264)

Round 53's open list, all of it: the ureas, the lactam and pyrazolone anions, the amidinium beside acids, the oxime anion, the strict-ownership double claim, an anion beside another charge, and an audit of
the engine's acyl blocks for the second-acid defect. Baseline on master (round 53 tree): anions 1042 of 1046; cations 2046 of 2081 (27 refused); quaternary 2059 of 2081.

* **D-256 (silent wrong molecule).** The audit of the acylamino blocks of `engine.py` found it: `[NH3+]c1ccc(NC(=S)CC(=O)O)cc1` was `{[hydroxy(thioxo)methyl]acetamido}`. Replacing a thioamide's N by OH makes a
  THIO acid, so the other acid was the only `carboxylic_acid` and became the parent, and the O and S swapped. A thioamide beside any second acid now goes to the generic path (`2-carboxy-1-thioxoethyl`).
  The oxo/oxo acylamino blocks were correct (measured on twelve shapes, all read back).
* **D-257.** `_classify_oxonium_urea`: an acyclic O+ double-bonded to a carbon that holds two heteroatoms (a urea, a carbamate, a guanidine-like carbonyl) is the cation parent, `(diaminomethylidene)oxidanium`,
  rendered by `_render_iminium_hetero` with `oxidanium` for the ending. A ring sulfoxide cation (`(1lambda4-thiolan-1-ylidene)oxidanium`) was checked through OPSIN and reads back.
* **D-258 (silent wrong molecule).** `_name_branch_as_prefix` cuts a branch off the molecule; a stereo centre (`[C@H]`) carries its hydrogen as an explicit count with implicit hydrogens off, so the cut left a
  RADICAL `[CH]1C=CCOC1`, which was named `oxan-3-yl`: the ring double bond lost. The carbon gets its implicit hydrogens back.
* **D-259 (silent stereo loss).** The same cut dropped the CIP descriptor of the attachment atom: `acetyl(butan-2-yl)azanide` for `CC[C@H](C)[N-]C(C)=O`, where the group on an oxygen is `[(2S)-butan-2-yl]oxy`.
  `_with_attachment_stereo` adds the label the centre has in the WHOLE molecule (its nitrogen is a ligand), in locant order with the group's own descriptors.
* **D-260.** A lactam anion the engine names with a ketone SUFFIX was `3,4-dihydroquinolin-2(1H)-on-1-ide`, which OPSIN cannot parse. The `ide` goes in as an infix before the suffix:
  `3,4-dihydroquinolin-1-id-2(1H)-one` (measured, read back). The charge guard's anion word learned the `-N-id-` infix.
* **D-261.** `_render_amidinium_zwitterion` masked at most ONE neutral acid as a methyl ester. It masks every one now, with at most one carboxylate (or none, for two or more acids), and reads back a repeated
  group (`bis(methoxycarbonyl)` -> `dicarboxy`): `3-carboxylato-2,2-dicarboxypropanamidinium`, `3,5-dicarboxybenzamidinium`.
* **D-262.** `_restore_dropped_oximate`: a deprotonated amidoxime the plan search wrote with a neutral `hydroxyimino` (`1-[1-(hydroxyimino)ethyl]pyrrolidine`, which the guard refused) cites `oxidoimino`, which
  OPSIN reads as the anion. Done only for a single O- on an oxime nitrogen whose neutral prefix occurs exactly once.
* **D-263.** `NC([S-])=NC(=O)c1ccccc1` claimed its carbonyl oxygen twice (strict ownership raised, the default mode renamed it via a second plan). The amide split in `SubstitutivePath.execute` put an `oxo` at the
  anchor for every chalcogen in the demoted group's atoms, defaulting the bond order to 2 for an oxygen that is not bonded to the anchor at all (the N-acyl substituent's carbonyl). It skips such an atom now.
  The name is `amino(benzoylimino)methanethiolate` in both modes.
* **D-264.** `_classify_azanide` required exactly one charge in the molecule. The anion is the senior class (P-41), so it is the parent and a CATION elsewhere is a prefix, as `4-(azaniumylmethyl)benzoate` is for
  a carboxylate: only one NEGATIVE charge is allowed, and the positive ones are claimed with it. `acetyl[4-(azaniumylmethyl)phenyl]azanide`.
* Also: enclosing marks in an iminium or oxonium prefix now nest `( )` in `[ ]` in `{ }`. The population tool's verdict normalises the sulfoxide cation's two drawings.
* **Measured.** Anions 1044 of 1046; cations 2061 of 2081, quaternary 2074 of 2081; NO wrong name in any population. Every new name reads back through OPSIN. Census 1993 exact, unchanged. Vendored suite and
  known-defects file: all passed. App naming group: all passed after five tests that pinned old refusals or names were repointed (round 43, 45, 46, 49, 52). 10 of 10 live mutants killed.
* New `tests/test_namer_round54_open_limitations.py` (60 tests). D-256 to D-264 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-15 -- naming round 53: nitrilium cations with a heteroatom, O-protonated sulfoxides, an acyl prefix that dropped its free acid (D-253, D-254, D-255)

Round 52's open list: 77 refused nitrilium cations and 6 refused O-protonated sulfoxides. Baseline on master (round 52 tree): cations 1964 of 2081 ok (108 refused); quaternary 2054 of 2081.

* **D-253.** `[NH+]#Cc1ccc(O)cc1`: the plan search promoted the hydroxy to the principal group and named the neutral nitrile, which the charge guard refused. The hydrocarbon nitriliums were named already (`benzylidyneazanium`).
  `_classify_nitrilium` takes a nitrilium (N+ triple-bonded to a carbon, no ring, at most one carbon on N) whose group holds a heteroatom; the cation is the parent (P-41) and the group an `ylidyne` prefix:
  `[(4-hydroxyphenyl)methylidyne]azanium`, `[(4-hydroxyphenyl)methylidyne](methyl)azanium`. `_render_iminium_hetero` and `_name_ylidene_group` follow a triple bond and expect `ylidyne`.
* **D-254.** An acyclic `C-S(=[OH+])-C` / `C-S(=[O+]R)-C` had no classifier. The same cation drawn with a single S-O bond is a sulfonium with a hydroxy or alkoxy substituent, which the engine names:
  `hydroxydi(methyl)sulfanium` (OPSIN reads it as `O[S+](C)C`; the ion population's verdict now treats the two drawings as one ion). A ring sulfur is not claimed (the recursive drive neutralises it).
* **D-255.** Found by the cation population beside D-253: `[NH3+]c1ccc(C(=O)CC(=O)O)cc1` was `4-propanedioylanilinium`. The engine's acyl substituent builds the acid by adding an OH at the attachment and turns its name
  into the acyl name; a SECOND acid in the fragment makes that a diacid and the name a diacyl group, which drops the free acid. The block now steps aside for such a fragment and the generic substituent path writes
  the carboxy: `4-(2-carboxy-1-oxoethyl)anilinium`. The same guard as D-250, in the engine rather than the azanide renderer.
* **Measured.** Cations 2046 of 2081, quaternary 2059 of 2081, anions 1042 of 1046 (unchanged); NO wrong name in the cation or quaternary population. Every name reads back through OPSIN. Census 1993 exact,
  unchanged. Vendored suite and known-defects file: all passed. App naming group: 2486 passed. 7 of 7 live mutants killed.
* New `tests/test_namer_round53_nitrilium_and_sulfoxide_cations.py` (32 tests); one verdict test in `tests/test_naming_ion_populations.py`. D-253 and D-255 in the fixed table of
  `tests/test_namer_known_defects.py` (D-254 is not: its name denotes the sulfonium drawing, which that table's SMILES comparison cannot hold).

## 2026-10-15 -- naming round 52: a second acid in an azanide's acyl group, the thioamide anion, a positive chalcogen taken for a carbonyl (D-250, D-251, D-252)

Round 51's open list asked for site patterns the ion populations had not tried. `tools/naming_ion_populations.py` now also deprotonates an acyclic amide, a urea, a thioamide, an oxime, a phosphonic and a sulfinic
acid, and protonates or methylates a thiocarbonyl sulfur, a sulfoxide oxygen, a phosphine and a nitrile nitrogen. Baseline on master: anions 1025 of 1046 ok (11 refused, 6 unparsable, 2 wrong, 2 naming errors);
cations 1969 of 2081 (101 refused, 2 wrong); quaternary 2046 of 2081 (22 refused, 5 wrong, 5 naming errors).

* **D-250.** An amide anion's acyl group is named by cutting the nitrogen off, naming the acid and turning its name into the acyl name. When the fragment held a SECOND acid (a glutaric or maleic half-amide) the name
  became a diacyl group, `(pentanedioyl)(...)azanide`, which OPSIN cannot read and which dropped the free acid. `_acyl_prefix_via_acid` declines such a fragment (any second carboxylic, thiocarboxylic or sulfonic acid) and
  `_render_azanide` falls back to the branch namer, which writes the carboxy as a prefix: `(4-carboxy-1-oxobutyl)(1,3-thiazol-2-yl)azanide`.
* **D-251.** A thioamide / thiourea anion (`CC(=S)[N-]C`) was claimed by `_classify_amine_anion`, which excludes a C=O neighbour but not a C=S one, and then could not render it: a refusal. The exclusion now covers C=S, so
  the azanide route names it, `ethanethioyl(methyl)azanide`, `aminomethanethioyl(phenyl)azanide`.
* **D-252.** The one wrong molecule of the round, and no refusal: S-protonated thiourea `NC(N)=[SH+]` was `thiocarbamoylsulfanium`. `=S` and `=O` in a suffix-group SMARTS match a POSITIVE chalcogen, so the `thioamide`
  group matched through the sulfonium sulfur, the sulfonium parent and the group both claimed that atom, and a nitrogen dropped out of the name. The same hole made `carbamoyloxidanium` of `CC(C)CNN(CC(C)C)C(N)=[OH+]`.
  The group-matching loop in `fg_detection.py` now drops a match that contains a positively charged O, S, Se or Te. `(diaminomethylidene)sulfanium`, `[amino(hydrazinyl)methylidene]sulfanium`.
* **Measured.** Anions 1042 of 1046 after the round; cations 1964 of 2081 and quaternary 2054 of 2081, with ZERO wrong names in either (the 108 and 18 refusals are visible: nitrilium cations with substituents and
  O-protonated sulfoxides and ureas). Every name reads back through OPSIN. Census 1993 exact, unchanged. Vendored suite and known-defects file: 7447 passed, 14 xfailed. App naming group: all passed after the
  site-pattern tests were made to ask for one kind. 4 of 4 live mutants killed.
* New `tests/test_namer_round52_acyl_groups_thioamides_and_chalcogen_cations.py` (27 tests); eight site-pattern tests in `tests/test_naming_ion_populations.py`. D-250 to D-252 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-15 -- naming round 51: the anion of a hydrazide, ring anions with an added hydrogen or a prime, and a nitro group beside a ring anion (D-248, D-249)

Round 50's open list asked for site patterns the ion populations had not tried. `tools/naming_ion_populations.py` now also deprotonates a lactam NH, a hydrazide NH, an azole NH and a hydroxamic acid, and
protonates or methylates the oxygen of an amide or a ketone. The baseline on master: anions 416 of 453 ok (18 naming errors, 11 unparsable, 8 refused); cations 1882 of 1909; quaternary 1881 of 1909.

* **D-248.** `CC(=O)[N-]N` and the other hydrazide anions were a `NAMING ERROR` (`[NH-]N` unnamed): the azanide classifier refused any neighbour that was not carbon or a sulfamoyl sulfur. A neutral nitrogen beside
  the anionic one is the hydrazide's other nitrogen, and the name is `acetyl(amino)azanide` (OPSIN reads it back; measured before the fix, together with `1-acetylhydrazin-1-ide`).
* **D-249.** A ring anion is the ring's substituent group with `yl` changed to `ide`, and the attachment locant was read by a regex that stopped at `3(2H)-` and at `1'-`. A group it could not read fell through
  to the parent-hydride splice (`1,3-benzothiazol-2(3H)-on-1-ide`: wrong locant, a spelling OPSIN cannot parse) or was refused (a spiro oxindole anion). The locant may now carry an added hydrogen or a prime.
  A nitro group elsewhere in the molecule (charge-separated, neutral overall) also hid the ring anion from `_classify_aromatic_ring_anion`, which counted its charges; it now uses the same
  `_charge_separated_neutral_atoms` the azanide classifier uses, and claims those atoms so the ownership check passes.
* **Measured.** Anions 451 of 453 after the round (the two left are recorded). Census 1993 exact, unchanged. Vendored suite and known-defects file: 7438 passed, 14 xfailed. App naming group: 2422 passed.
  4 of 4 live mutants killed. The round 46 test that pinned the pyrazolone anion as a refusal now pins a carboxylate beside two neutral acids on an amidinium.
* New `tests/test_namer_round51_nn_and_added_hydrogen_anions.py` (31 tests); six site-pattern tests in `tests/test_naming_ion_populations.py`. D-248 and D-249 in the fixed table of `tests/test_namer_known_defects.py`.

## 2026-10-14 -- naming round 50: a bare imino after any prefix, and the iminium cations round 49 left refused (D-246, D-247)

Round 49's open list asked whether the ion populations were saturated. The three scripts that had found rounds 46 to 49's defects (scratch folders and memory notes) became ONE tool,
`tools/naming_ion_populations.py` (`anion`, `cation`, `quaternary`; 26 tests in `tests/test_naming_ion_populations.py`), and the baseline on master measured it: anions 284 of 285 ok (1 wrong), cations 1034 of 1036 (1 refused, 1 OPSIN limit), quaternary cations 1033 of 1036 (2 refused, 1 OPSIN limit); after this round 285 of 285, 1035 of 1036 and 1035 of 1036, ZERO refusals, the one left in each cation population the bis([1,3]dioxolo)pyran OPSIN cannot read.

* **D-246.** The one wrong anion: `{[...]methyldiazenyl}iminomethanethiolate`, which OPSIN reads with an N-N bond. Round 49 had bracketed `imino` after `amino` and `hydroxy`; the rule is general. A bare `imino`
  right after ANY prefix runs together into a substituted imino group (measured through OPSIN: `methyliminomethanethiol` -> `CN=CS`, `methyl(imino)methanethiol` -> `CC(S)=N`), so the assembler encloses it whenever a
  prefix precedes it.
* **D-247.** The three refused cations: an N-sulfonyl iminium (`O=C1C(Cl)=CC(=[NH+]S(=O)(=O)Ar)c2ccccc21`, the cation of a quinone imine) and two QUATERNARY iminiums (`C[N+](...)=C(N)S`, no hydrogen on the nitrogen).
  Round 49's `_classify_iminium_hetero` now takes a nitrogen with no hydrogen (degree 3) and a SULFONYL on the nitrogen when the carbon bears only carbon; identical groups on the nitrogen are one multiplied prefix
  (`dimethylazanium`, not `(methyl)(methyl)`). `[amino(sulfanyl)methylidene]dimethylazanium`, `(3-chloro-4-oxo-1,4-dihydronaphthalen-1-ylidene)(4-chlorophenylsulfonyl)azanium`.
* **Two regressions the census caught on the first run, fixed before this PR.** The first widening claimed any iminium with a heteroatom on the nitrogen. A RING nitrogen (`c(=[N+]3CCOCC3)`, a morpholinium ylidene) has
  two ring arms that were carved as two separate `2-ethoxyethyl` substituents: the ring cut, a different molecule (2 census rows, exact -> mismatch_formula). And an acylhydrazone cation
  (`CC(=[NH+]NC(=O)C)C`), which the plan search already named correctly, was taken from it. The classifier now requires the nitrogen OUTSIDE any ring, and the nitrogen-side clause is a sulfonyl only.
* **Measured.** Every name reads back through OPSIN to its input, charge included. Census 1993 exact, unchanged. App naming tests 4024 passed (the full group on the final tree); `tests/vendor` and the known-defects file: 7429 passed (the full vendored suite and the known-defects file).
  **Frozen sets** (blind `--frozen-impact`): heldout_v6 and fresh_v1 unchanged; bluebook_frozen moved 1 row and was re-scored once: heldout_v6 and fresh_v1 unchanged; bluebook_frozen re-scored once (r50-final-evaluation): exact 523 -> 522 and equivalent 527 -> 528, every other count identical (one row's spelling moved, the same molecule). The stage list for `--frozen-impact` becomes `r49-fresh-v1,r50-final-evaluation,r38-final-evaluation`.
* New `tests/test_namer_round50_iminium_and_imino.py` (35 tests; 6 of 6 live mutants killed) and `tests/test_naming_ion_populations.py`. D-246 and D-247 in the fixed table of `tests/test_namer_known_defects.py`.
