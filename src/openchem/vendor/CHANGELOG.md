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
