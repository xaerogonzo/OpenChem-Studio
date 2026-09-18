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
