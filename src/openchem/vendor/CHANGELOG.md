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
